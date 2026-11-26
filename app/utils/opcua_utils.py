import asyncio
import logging
import os
import sys

from asyncua import ua
from asyncua.client.ua_client import UASocketProtocol
from asyncua.common.utils import wait_for
from asyncua.ua.uaerrors._base import UaError


# MONKEY PATCH: Fix TimeoutHint in OpenSecureChannelRequest
# Original asyncua implementation doesn't pass timeout to _send_request for open_secure_channel,
# causing it to default to 1s (1000ms), which is too short for Siemens S7-1500 crypto handshake.
async def patched_open_secure_channel(self, params):
    # self is the UASocketProtocol instance
    # logger.info(f"Using patched open_secure_channel with timeout={self.timeout}")
    request = ua.OpenSecureChannelRequest()
    request.Parameters = params
    if self._open_secure_channel_exchange is not None:
        raise UaError(
            "Two Open Secure Channel requests can not happen too close to each other. "
            "The response must be processed and returned before the next request can be sent."
        )
    self._open_secure_channel_exchange = params

    # FIX: Pass self.timeout explicitly to _send_request
    # Use at least 60s if configured timeout is small, just to be safe for this critical step
    timeout_to_use = self.timeout if self.timeout and self.timeout > 10 else 60

    # We call _send_request with timeout arg!
    await wait_for(self._send_request(request, timeout=timeout_to_use, message_type=ua.MessageType.SecureOpen), timeout_to_use)

    _return = self._open_secure_channel_exchange.Parameters
    self._open_secure_channel_exchange = None
    return _return

UASocketProtocol.open_secure_channel = patched_open_secure_channel

# Add project root to path if running directly
if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(current_dir))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

from asyncua import Client
from asyncua.crypto.security_policies import (
    SecurityPolicyBasic128Rsa15,
    SecurityPolicyBasic256,
    SecurityPolicyBasic256Sha256,
)

# 2026-11-23: certificate (20 years, AINIMA names), PLC certificate pinning, pki/ path
from app.utils import opcua_security as sec
from config.config import ConfigLoader


class RobustClient(Client):
    """
    Client OPC UA customizzato per migliorare la compatibilità con server esigenti (es. Siemens S7-1500).
    Forza la selezione della UserTokenPolicy che corrisponde alla policy del canale sicuro,
    invece di prendere la prima disponibile.
    """
    def server_policy(self, token_type: ua.UserTokenType) -> ua.UserTokenPolicy:
        """
        Override del metodo originale per selezionare la policy corretta.
        """
        # Prima cerca una policy che corrisponda esattamente alla URI del canale sicuro corrente
        current_policy_uri = self.security_policy.URI

        # logger.debug(f"Ricerca UserTokenPolicy per tipo {token_type} compatibile con {current_policy_uri}")

        # 1. Cerca match esatto con la policy del canale
        for policy in self._policy_ids:
            if policy.TokenType == token_type:
                if policy.SecurityPolicyUri == current_policy_uri:
                    logger.info(f"Selezionata UserTokenPolicy ottimizzata: {policy.PolicyId} ({policy.SecurityPolicyUri})")
                    return policy

        # 2. Se non trova match esatto, prova a cercare una policy 'sicura' se siamo in modalità sicura
        # (es. preferisce Basic256Sha256 su Basic128Rsa15)
        preferred_policies = [
            "http://opcfoundation.org/UA/SecurityPolicy#Basic256Sha256",
            "http://opcfoundation.org/UA/SecurityPolicy#Aes256_Sha256_RsaPss",
            "http://opcfoundation.org/UA/SecurityPolicy#Basic256",
        ]

        for pref_uri in preferred_policies:
            for policy in self._policy_ids:
                if policy.TokenType == token_type and policy.SecurityPolicyUri == pref_uri:
                    logger.info(f"Selezionata UserTokenPolicy preferita: {policy.PolicyId} ({policy.SecurityPolicyUri})")
                    return policy

        # 3. Fallback al comportamento originale (prima policy che matcha il tipo)
        logger.warning(f"Nessuna UserTokenPolicy ottimizzata trovata. Fallback alla prima disponibile per {token_type}")
        return super().server_policy(token_type)

    async def connect(self) -> None:
        """
        Override di connect per gestire correttamente la priorità di autenticazione.
        Se è impostato uno username, usa autenticazione Username/Password anche se è presente un certificato client.
        Il certificato client serve per il canale sicuro (Application Identity), ma non necessariamente per l'User Identity.
        """
        logger.info("connect (RobustClient)")
        await self.connect_socket()
        try:
            await self.send_hello()
            await self.open_secure_channel()
            try:
                await self.create_session()
                try:
                    # FIX: Prefer Username/Password if set, otherwise try Certificate
                    # Asyncua standard usa il certificato se presente, ignorando username/password
                    if self._username:
                        logger.info(f"Autenticazione User Identity: Username/Password ({self._username})")
                        await self.activate_session(
                            username=self._username, password=self._password, certificate=None
                        )
                    else:
                        logger.info("Autenticazione User Identity: Certificato o Anonimo")
                        await self.activate_session(
                            username=self._username, password=self._password, certificate=self.user_certificate
                        )
                except Exception:
                    # clean up session
                    await self.close_session()
                    raise
            except Exception:
                # clean up secure channel
                await self.close_secure_channel()
                raise
        except Exception:
            # clean up open socket
            self.disconnect_socket()
            raise

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OPCUAExplorer:
    def __init__(self, url, anonymous=False, username=None, password=None, security_mode="None", security_policy="None"):
        self.url = url
        # Inizializziamo con watchdog lungo anche qui per coerenza
        self.client = RobustClient(url=self.url, watchdog_intervall=3600, timeout=60.0) # Imposto timeout generale nel costruttore
        # Aumentiamo i timeout interni di default anche qui
        self.client.secure_channel_timeout = 60000
        self.client.session_timeout = 60000

        # Forziamo anche il timeout sul protocollo interno se accessibile
        if hasattr(self.client, 'uaclient'):
            self.client.uaclient._timeout = 60.0 # Timeout generale richieste
            self.client.uaclient.secure_channel_timeout = 60000
            self.client.uaclient.session_timeout = 60000

        self.security_string = None
        self.security_mode_str = security_mode
        self.anonymous = anonymous
        self.username = username
        self.password = password

        # Configurazione Sicurezza
        if not anonymous:
            if username and password:
                self.client.set_user(username)
                self.client.set_password(password)

            # Stringa della policy da usare per il match con l'endpoint
            self.security_string = security_policy

            # Mappatura Security Policy per set_security
            # Utilizziamo direttamente le classi SecurityPolicy di asyncua
            policy_map = {
                "Basic128RSA15": SecurityPolicyBasic128Rsa15,
                "Basic256": SecurityPolicyBasic256,
                "Basic256SHA256": SecurityPolicyBasic256Sha256
            }

            # Se la policy richiesta non è nella mappa, la logghiamo
            if self.security_string != "None" and self.security_string not in policy_map:
                 logger.warning(f"Security Policy '{self.security_string}' non supportata. Disponibili: {list(policy_map.keys())}")

            # Mappatura Security Mode
            mode_map = {
                "None": ua.MessageSecurityMode.None_,
                "Sign": ua.MessageSecurityMode.Sign,
                "Sign & Encrypt": ua.MessageSecurityMode.SignAndEncrypt,
            }

            if self.security_string != "None" and self.security_string in policy_map:
                policy_class = policy_map[self.security_string]
                mode = mode_map.get(security_mode, ua.MessageSecurityMode.None_)

                # Configurazione Certificati
                cert_path = None
                key_path = None

                # Se è richiesta sicurezza (Sign o SignAndEncrypt), serve un certificato:
                # pki/ accanto ad ainima_client.py; se manca viene creato (20 anni,
                # nomi e ApplicationUri AINIMA). Per sostituirlo: opcua_tool.py --new-cert.
                if mode != ua.MessageSecurityMode.None_:
                    cert_path, key_path = sec.cert_paths()
                    if not (os.path.exists(cert_path) and os.path.exists(key_path)):
                        logger.info("Certificato client non trovato: ne creo uno nuovo (20 anni)...")
                        try:
                            info = sec.generate_client_certificate()
                            logger.info(f"Nuovo certificato client in {info['cert']}, valido fino al {info['not_after']:%Y-%m-%d}")
                        except Exception as e:
                            logger.error(f"Errore generazione certificato: {e}")

                # Imposta la sicurezza di base (fallback o per None)
                # if cert_path and os.path.exists(cert_path) and key_path and os.path.exists(key_path):
                     # Se abbiamo i certificati, usiamo la policy configurata o un default sicuro
                     # policy_to_use = policy_class if policy_class else SecurityPolicyBasic256Sha256
                     # self.client.set_security(policy=policy_to_use, certificate=cert_path, private_key=key_path, mode=mode)
                # else:
                     # Senza certificati, usiamo la policy configurata o un default sicuro
                     # policy_to_use = policy_class if policy_class else SecurityPolicyBasic256Sha256
                     # self.client.set_security(policy_to_use, certificate=None, private_key=None, server_certificate=None, mode=mode)

        self.connected = False

    async def _get_secure_endpoint(self):
        """
        Uses a temporary client to discover endpoints and find the one matching
        the configured security policy and mode.
        RETURNS: The matching EndpointDescription or None
        """
        selected_endpoint = None

        try:
            logger.info(f"Ricerca endpoint sicuro con policy: {self.security_string}")

            # Client temporaneo per discovery - isolato dal client principale
            # Alcuni server richiedono ApplicationUri anche per il discovery
            discovery_client = Client(url=self.url)
            discovery_client.application_uri = sec.APP_URI

            endpoints = []
            try:
                # Tentiamo prima con connect_and_get_server_endpoints che gestisce meglio
                # il caso di GetEndpoints senza sessione (se supportato dalla lib)
                endpoints = await discovery_client.connect_and_get_server_endpoints()
            except Exception as e:
                logger.warning(f"Metodo connect_and_get_server_endpoints fallito: {e!r}")
                # Fallback: prova connect() standard se il server lo permette
                try:
                    async with discovery_client:
                        endpoints = await discovery_client.get_endpoints()
                except Exception as e2:
                    logger.warning(f"Anche connect() standard fallito per discovery: {e2!r}")

            # Log degli endpoint trovati per debug
            logger.debug(f"Endpoint trovati: {len(endpoints)}")

            for endpoint in endpoints:
                # Controlla se la policy dell'endpoint contiene la stringa richiesta
                endpoint_policy = endpoint.SecurityPolicyUri
                endpoint_mode = endpoint.SecurityMode

                # Log ogni endpoint analizzato
                logger.debug(f"Analisi endpoint: {endpoint.EndpointUrl} - {endpoint_policy} - Mode:{endpoint_mode}")

                # Verifica Policy
                policy_match = False
                if self.security_string == "Basic256SHA256" and "Basic256Sha256" in endpoint_policy or self.security_string == "Basic256" and "Basic256" in endpoint_policy and "Sha256" not in endpoint_policy or self.security_string == "Basic128RSA15" and "Basic128Rsa15" in endpoint_policy or self.security_string == "None" and "None" in endpoint_policy:
                    policy_match = True

                # Verifica Mode
                mode_match = False
                target_mode = ua.MessageSecurityMode.None_

                if hasattr(self, 'security_mode_str'):
                    if self.security_mode_str == "Sign":
                        target_mode = ua.MessageSecurityMode.Sign
                    elif self.security_mode_str == "Sign & Encrypt":
                        target_mode = ua.MessageSecurityMode.SignAndEncrypt
                    else:
                        target_mode = ua.MessageSecurityMode.None_

                # Se il mode non è specificato (o è None), accettiamo quello che troviamo (fallback)
                # Ma se è specificato Sign o SignAndEncrypt, cerchiamo il match esatto
                if target_mode != ua.MessageSecurityMode.None_:
                    if endpoint_mode == target_mode:
                        mode_match = True
                else:
                    # Se l'utente ha scelto None, cerchiamo mode None
                    if endpoint_mode == ua.MessageSecurityMode.None_ or policy_match:
                        mode_match = True

                if policy_match and mode_match:
                    selected_endpoint = endpoint
                    break
                elif policy_match and selected_endpoint is None:
                     # Keep as fallback if we don't find exact mode match
                     selected_endpoint = endpoint

            return selected_endpoint

        except Exception as e:
            logger.warning(f"Errore generale durante la discovery degli endpoint: {e}")
            return None

    async def connect(self):
        try:
            logger.info(f"Tentativo di connessione a: {self.url}...")

            # RE-INSTANZIA IL CLIENT per garantire uno stato pulito per la connessione sicura
            # Impostiamo watchdog_intervall=3600 per evitare che il client provi a leggere lo stato del server
            # prima che la sessione sia completamente attivata (evita BadSessionNotActivated/BadSessionClosed su Siemens)
            self.client = RobustClient(url=self.url, watchdog_intervall=3600, timeout=60.0)
            self.client.secure_channel_timeout = 60000
            self.client.session_timeout = 60000
            if hasattr(self.client, "uaclient"):
                self.client.uaclient._timeout = 60.0
                self.client.uaclient.secure_channel_timeout = 60000
                self.client.uaclient.session_timeout = 60000

            # Application URI coerente con il certificato generato
            self.client.application_uri = sec.APP_URI
            self.client.product_uri = sec.APP_URI
            self.client.name = sec.APP_NAME

            # Riapplica configurazione utente
            if not self.anonymous and self.username and self.password:
                self.client.set_user(self.username)
                self.client.set_password(self.password)

            # Setup sicurezza
            if self.security_string and self.security_string != "None":

                policy_uri = None
                mode = ua.MessageSecurityMode.None_
                policy_class = None
                server_cert = None
                policy_map = {
                    "Basic128RSA15": SecurityPolicyBasic128Rsa15,
                    "Basic256": SecurityPolicyBasic256,
                    "Basic256SHA256": SecurityPolicyBasic256Sha256,
                    "None": None
                }

                # 1. Tentativo di Discovery
                endpoint = await self._get_secure_endpoint()

                if endpoint:
                    logger.info(f"Endpoint trovato: {endpoint.EndpointUrl} [{endpoint.SecurityPolicyUri}]")

                    # Aggiorna URL del client principale con quello ESATTO restituito dal server
                    # Siemens S7-1500 rifiuta la sessione se l'EndpointUrl non combacia al carattere (es. slash finale)
                    target_url = endpoint.EndpointUrl
                    if target_url != self.url:
                         logger.info(f"Aggiorno URL connessione da '{self.url}' a '{target_url}' per compatibilità stretta")
                         self.url = target_url

                         # Re-inizializziamo il client con il nuovo URL corretto
                         # Non possiamo settare server_url direttamente perché è read-only/property
                         # Dobbiamo ricreare l'oggetto client mantenendo le impostazioni
                         logger.info("Re-inizializzazione client con URL corretto...")
                         self.client = RobustClient(url=self.url, watchdog_intervall=3600, timeout=60.0)
                         # Aumentiamo i timeout interni del protocollo OPC UA
                         # secure_channel_timeout controlla il TimeoutHint della OpenSecureChannelRequest
                         self.client.secure_channel_timeout = 60000 # 60 secondi
                         self.client.session_timeout = 60000 # 60 secondi per la sessione

                         # Forziamo il timeout anche sull'oggetto uaclient e sul protocollo se esiste già
                         if hasattr(self.client, 'uaclient'):
                             self.client.uaclient._timeout = 60.0 # Timeout generale richieste (float secondi)
                             self.client.uaclient.secure_channel_timeout = 60000
                             self.client.uaclient.session_timeout = 60000
                             if self.client.uaclient.protocol:
                                 self.client.uaclient.protocol.timeout = 60.0

                         self.client.application_uri = sec.APP_URI
                         self.client.product_uri = sec.APP_URI
                         self.client.name = sec.APP_NAME

                         # Riapplica credenziali se presenti
                         if not self.anonymous and self.username and self.password:
                            self.client.set_user(self.username)
                            self.client.set_password(self.password)

                    policy_uri = endpoint.SecurityPolicyUri
                    mode = endpoint.SecurityMode
                    server_cert = endpoint.ServerCertificate
                else:
                    logger.warning(f"Discovery fallita o nessun endpoint trovato. Utilizzo configurazione manuale per {self.security_string}.")

                    # Mappatura manuale se discovery fallisce
                    policy_map = {
                        "Basic128RSA15": SecurityPolicyBasic128Rsa15,
                        "Basic256": SecurityPolicyBasic256,
                        "Basic256SHA256": SecurityPolicyBasic256Sha256,
                        "None": None
                    }

                    policy_class = policy_map.get(self.security_string)
                    server_cert = None

                    # Mappatura Mode manuale (dobbiamo recuperarlo da qualche parte o assumerlo)
                    # ConfigLoader passa security_mode come stringa in __init__, ma qui non l'abbiamo salvata in self!
                    # Dobbiamo recuperare il mode.
                    # FIX: Salviamo security_mode in __init__ o lo passiamo
                    # Per ora assumiamo SignAndEncrypt se non è None, dato che è quello che vuole l'utente
                    # Ma wait, OPCUAExplorer __init__ prende security_mode

                # Recupero Security Mode se siamo in fallback (dobbiamo averlo salvato in init)
                if not endpoint and policy_class:
                     # Recuperiamo il mode salvato (che aggiungerò in init)
                     if hasattr(self, 'security_mode_str'):
                        if self.security_mode_str == "Sign":
                            mode = ua.MessageSecurityMode.Sign
                        elif self.security_mode_str == "Sign & Encrypt":
                            mode = ua.MessageSecurityMode.SignAndEncrypt
                        else:
                            mode = ua.MessageSecurityMode.None_

                if (endpoint and policy_uri) or (policy_class and mode != ua.MessageSecurityMode.None_):
                    # Se abbiamo endpoint, dobbiamo convertire la policy URI in classe
                    if endpoint:
                        # Mappa URI a classi
                        uri_to_class = {
                            "http://opcfoundation.org/UA/SecurityPolicy#Basic128Rsa15": SecurityPolicyBasic128Rsa15,
                            "http://opcfoundation.org/UA/SecurityPolicy#Basic256": SecurityPolicyBasic256,
                            "http://opcfoundation.org/UA/SecurityPolicy#Basic256Sha256": SecurityPolicyBasic256Sha256
                        }
                        # Rimuoviamo spazi extra se presenti
                        clean_uri = endpoint.SecurityPolicyUri.strip()
                        policy_class = uri_to_class.get(clean_uri)

                        if not policy_class:
                             logger.warning(f"Policy URI sconosciuta: {clean_uri}, tento fallback su {self.security_string}")
                             policy_class = policy_map.get(self.security_string)

                    # 4. Verifica del certificato del PLC (pki/trusted_server_cert.der, se presente):
                    # il client parla solo con il PLC fidato, mai con chi si spaccia per lui.
                    if server_cert is None:
                        server_cert = sec.trusted_server_cert()
                    _pin_err = sec.check_server_certificate(server_cert)
                    if _pin_err:
                        logger.error(f"Certificato del PLC rifiutato: {_pin_err}")
                        raise ConnectionError(f"Certificato del PLC rifiutato: {_pin_err}")

                    # 5. Certificati del client (pki/ accanto ad ainima_client.py)
                    cert_path, key_path = sec.cert_paths()

                    if os.path.exists(cert_path) and os.path.exists(key_path):
                        # DEBUG: Log dettagliato pre-security
                        logger.info(f"Setting security with: PolicyClass={policy_class.__name__}, Mode={mode}, ServerCertLen={len(server_cert) if server_cert else 0}")

                        # Non carichiamo manualmente i certificati qui, lasciamo fare a set_security
                        # await self.client.load_client_certificate(cert_path)
                        # await self.client.load_private_key(key_path)

                        # Fix per bug asyncua set_security (non sempre carica i certificati in user_certificate)
                        await self.client.load_client_certificate(cert_path)
                        await self.client.load_private_key(key_path)

                        # Impostazione sicurezza
                        if policy_class:
                            await self.client.set_security(
                                policy=policy_class,
                                certificate=cert_path,
                                private_key=key_path,
                                server_certificate=server_cert,
                                mode=mode
                            )

                            # VERIFICA POST-SETTING
                            if hasattr(self.client, 'uaclient') and hasattr(self.client.uaclient, 'security_policy'):
                                current_policy = self.client.uaclient.security_policy
                                logger.info(f"Security Policy impostata: {type(current_policy)}")
                                logger.info(f"Security Mode impostato: {current_policy.Mode}")
                            else:
                                logger.warning("Impossibile verificare uaclient.security_policy")
                        else:
                            logger.error("Impossibile determinare la classe SecurityPolicy corretta")
                            raise ValueError("SecurityPolicy non valida o non supportata")
                    else:
                        logger.error("Certificati non trovati! Impossibile stabilire connessione sicura.")
                        raise FileNotFoundError("Certificato client o chiave privata mancanti in cartella pki/")

            # 5. Connessione finale
            # Aumentiamo il timeout a 120 secondi per reti lente o handshake complessi (Siemens)
            logger.info("Avvio handshake di connessione finale (Timeout 120s)...")
            await asyncio.wait_for(self.client.connect(), timeout=120.0)

            self.connected = True
            logger.info(f"Connesso con successo al Server OPC UA: {self.url}")
        except TimeoutError:
            self.connected = False
            msg = f"Timeout connessione: Il server a {self.url} non ha completato l'handshake entro 120 secondi."
            logger.error(msg)
            # Tentativo di pulizia
            try:
                await self.client.disconnect()
            except:
                pass
            raise ConnectionError(msg)
        except ConnectionRefusedError:
            self.connected = False
            msg = f"Connessione rifiutata: Assicurati che il PLC/Server sia attivo su {self.url}."
            logger.error(msg)
            raise ConnectionError(msg)
        except Exception as e:
            self.connected = False
            error_type = type(e).__name__
            msg = f"Errore di connessione [{error_type}]: {e!s}"
            logger.error(msg)
            raise ConnectionError(msg)

    async def disconnect(self):
        try:
            await self.client.disconnect()
            logger.info("Disconnesso dal Server OPC UA")
        except Exception as e:
            logger.error(f"Errore durante la disconnessione: {e}")
        finally:
            self.connected = False

    async def browse_nodes(self, node=None, level=0):
        """
        Naviga ricorsivamente e stampa i nodi a partire dal nodo dato.
        Se node è None, inizia dal nodo Root.
        """
        if node is None:
            node = self.client.nodes.root
            logger.info("Inizio scansione dal nodo Root")

        try:
            # Ottieni attributi del nodo per la visualizzazione
            node_class = await node.read_node_class()
            browse_name = await node.read_browse_name()
            node_id = node.nodeid

            # Stampa il nodo corrente con indentazione
            indent = "  " * level
            print(f"{indent}- [{node_class.name}] {browse_name.Name} ({node_id})")

            # Ottieni i figli
            children = await node.get_children()
            for child in children:
                await self.browse_nodes(child, level + 1)

        except Exception as e:
            indent = "  " * level
            print(f"{indent}! Errore scansione nodo {node}: {e}")

    async def browse_children(self, node=None):
        """
        Restituisce i figli di un nodo specifico.
        Se node è None, usa il nodo Root.
        Restituisce una lista di dizionari con info sul nodo.
        """
        if node is None:
            node = self.client.nodes.root

        try:
            children = await node.get_children()
            results = []
            for child in children:
                node_class = await child.read_node_class()
                browse_name = await child.read_browse_name()

                results.append({
                    "node": child,
                    "class": node_class.name,
                    "name": browse_name.Name,
                    "id": child.nodeid,
                    "value": None
                })
            return results
        except Exception as e:
            logger.error(f"Errore durante il browsing dei figli: {e}")
            return []

async def main():
    # Carica configurazione
    try:
        config_loader = ConfigLoader()
        # Usiamo la configurazione client perché ci stiamo connettendo come client
        opcua_config = config_loader.get_opcua_client_config()
        url = opcua_config.get('url')
        username = opcua_config.get('username')
        password = opcua_config.get('password')
        anonymous = opcua_config.get('anonymous', False)
        security_mode = opcua_config.get('security_mode', "None")
        security_policy = opcua_config.get('security_policy', "None")

        if not url:
            logger.error("URL Server OPC UA non trovato nella configurazione")
            # Fallback per test se config fallisce o è vuoto (opzionale)
            # url = "opc.tcp://10.0.0.1:4840/freeopcua/server/"
            return

        print(f"Tentativo di connessione a: {url}")
        print(f"Policy: {security_policy}, Mode: {security_mode}")
        explorer = OPCUAExplorer(
            url=url,
            anonymous=anonymous,
            username=username,
            password=password,
            security_mode=security_mode,
            security_policy=security_policy
        )

        try:
            await explorer.connect()
            print("\n--- Struttura Nodi OPC UA ---\n")
            await explorer.browse_nodes()
            print("\n-----------------------------\n")
        except ConnectionRefusedError:
             logger.error("Connessione rifiutata. Assicurati che il server OPC UA sia attivo e raggiungibile all'indirizzo specificato.")
        except Exception as e:
            logger.error(f"Si è verificato un errore: {e}")
        finally:
            await explorer.disconnect()

    except Exception as e:
        logger.error(f"Errore caricamento configurazione: {e}")

if __name__ == "__main__":
    asyncio.run(main())
