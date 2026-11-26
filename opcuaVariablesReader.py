import asyncio
import concurrent.futures
import csv
import logging
import re
import os
import json
import time
from datetime import datetime, timedelta
from rich.markup import escape as rich_escape
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Tree, Static, Button, Input, Label, ListView, ListItem, RichLog, Checkbox, RadioSet, RadioButton
from textual.containers import Container, Horizontal, Vertical, Grid
from textual.screen import Screen
from textual.binding import Binding
from textual import on, work
from textual.reactive import reactive

from config.config import ConfigLoader
from app.utils.opcua_utils import OPCUAExplorer

# Configurazione logging per Textual (evita che scriva su stdout)
# Forza la riconfigurazione per essere sicuri che nessuno scriva su stdout
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

# Assicura che la cartella logs esista
log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# Implementazione Rotazione Log (CobrakaiOpcuaClient.log, _1.log, _2.log)
# Il più vecchio (2) viene cancellato, gli altri scalano
base_log_name = "CobrakaiOpcuaClient"
log_ext = ".log"
max_log_files = 2

# 0. Pulizia log vecchi (3, 4 e 5) se presenti dalla configurazione precedente
for i in range(3, 6):
    old_file = os.path.join(log_dir, f"{base_log_name}_{i}{log_ext}")
    if os.path.exists(old_file):
        try:
            os.remove(old_file)
        except OSError:
            pass

# 1. Rimuovi il file più vecchio se esiste (_3.log)
oldest_log = os.path.join(log_dir, f"{base_log_name}_{max_log_files}{log_ext}")
if os.path.exists(oldest_log):
    try:
        os.remove(oldest_log)
    except OSError:
        pass

# 2. Scala gli altri file (_4 -> _5, _3 -> _4, ..., _1 -> _2)
for i in range(max_log_files - 1, 0, -1):
    src = os.path.join(log_dir, f"{base_log_name}_{i}{log_ext}")
    dst = os.path.join(log_dir, f"{base_log_name}_{i+1}{log_ext}")
    if os.path.exists(src):
        try:
            if os.path.exists(dst):
                os.remove(dst)
            os.rename(src, dst)
        except OSError:
            pass

# 3. Rinomina il log corrente (base -> _1)
current_log = os.path.join(log_dir, f"{base_log_name}{log_ext}")
first_backup = os.path.join(log_dir, f"{base_log_name}_1{log_ext}")
if os.path.exists(current_log):
    try:
        if os.path.exists(first_backup):
            os.remove(first_backup)
        os.rename(current_log, first_backup)
    except OSError:
        pass

# Configura il logging con il nuovo nome base
logging.basicConfig(
    level=logging.INFO, 
    filename=current_log, 
    filemode="w", 
    force=True,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

class ConfigScreen(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Indietro")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Label("Modifica Configurazione OPC UA", classes="title"),
            Label("IP Server:"),
            Input(placeholder="127.0.0.1", id="ip_input"),
            Label("Porta Server:"),
            Input(placeholder="4840", id="port_input"),
            Label("URL Client (opc.tcp://...):"),
            Input(placeholder="opc.tcp://...", id="url_input"),
            Label("Commessa/Cliente:"),
            Input(placeholder="Commessa", id="commessa_input"),
            Label("Tempo di lettura (sec):"),
            Input(placeholder="30", id="read_interval_input"),
            Label("Numero di records (0=continuo):"),
            Input(placeholder="5", id="read_records_input"),
            Label("Modalità:"),
            Container(
                RadioSet(
                    RadioButton("Normal Run", id="run_normal"),
                    RadioButton("Debug", id="run_debug"),
                    id="run_mode_set",
                ),
                id="run_mode_box",
            ),
            Label("", classes="spacer"),
            Label("Subscription - Publishing Interval (ms):"),
            Input(placeholder="3000", id="sub_publish_ms_input"),
            Label("Subscription - Sampling Interval (ms):"),
            Input(placeholder="3000", id="sub_sampling_ms_input"),
            Label("Soglia globale (Deadband):"),
            Input(placeholder="1.0", id="deadband_global_input"),
            # Sezione Sicurezza
            Label("Tipo Autenticazione:", id="security_title"),
            Horizontal(
                Vertical(
                    Label("Security Mode:"),
                    RadioSet(
                        RadioButton("None", id="mode_none"),
                        RadioButton("Sign", id="mode_sign"),
                        RadioButton("Sign & Encrypt", id="mode_sign_encrypt"),
                        id="mode_set"
                    ),
                    classes="security-col"
                ),
                Vertical(
                    Label("Security Policy:"),
                    RadioSet(
                        RadioButton("None", id="policy_none"),
                        RadioButton("Basic128RSA15", id="policy_b128"),
                        RadioButton("Basic256", id="policy_b256"),
                        RadioButton("Basic256SHA256", id="policy_b256sha256"),
                        id="policy_set"
                    ),
                    classes="security-col"
                ),
                id="security-container"
            ),
            Label("Username (opzionale):", id="user_label"),
            Input(placeholder="Username", id="user_input"),
            Label("Password (opzionale):", id="pass_label"),
            Input(placeholder="Password", password=True, id="pass_input"),
            Button("Salva Configurazione", variant="success", id="save_btn"),
            classes="config-container"
        )
        yield Footer()

    def on_mount(self) -> None:
        self.config_loader = ConfigLoader()
        config = self.config_loader.get_config()
        server = config.get('opcua', {}).get('server', {})
        client = config.get('opcua', {}).get('client', {})
        
        self.query_one("#ip_input", Input).value = str(server.get('ip', ''))
        self.query_one("#port_input", Input).value = str(server.get('port', ''))
        self.query_one("#url_input", Input).value = str(client.get('url', ''))
        self.query_one("#commessa_input", Input).value = str(client.get('commessa', ''))
        self.query_one("#read_interval_input", Input).value = str(client.get('read_interval_seconds', 30))
        self.query_one("#read_records_input", Input).value = str(client.get('read_records', 0))
        run_mode = str(client.get("run_mode", "normal") or "normal").strip().lower()
        if run_mode == "debug":
            self.query_one("#run_debug", RadioButton).value = True
        else:
            self.query_one("#run_normal", RadioButton).value = True
        self.query_one("#sub_publish_ms_input", Input).value = str(client.get("subscription_publishing_interval_ms", 3000))
        self.query_one("#sub_sampling_ms_input", Input).value = str(client.get("subscription_sampling_interval_ms", 3000))
        self.query_one("#deadband_global_input", Input).value = str(client.get("deadband_global", 1.0))
        
        self.query_one("#user_input", Input).value = str(client.get('username', ''))
        self.query_one("#pass_input", Input).value = str(client.get('password', ''))
        
        # Carica Security Mode
        mode = client.get('security_mode', 'None')
        if mode == 'None': self.query_one("#mode_none", RadioButton).value = True
        elif mode == 'Sign': self.query_one("#mode_sign", RadioButton).value = True
        elif mode == 'Sign & Encrypt': self.query_one("#mode_sign_encrypt", RadioButton).value = True
        
        # Carica Security Policy
        policy = client.get('security_policy', 'None')
        if policy == 'None': self.query_one("#policy_none", RadioButton).value = True
        elif policy == 'Basic128RSA15': self.query_one("#policy_b128", RadioButton).value = True
        elif policy == 'Basic256': self.query_one("#policy_b256", RadioButton).value = True
        elif policy == 'Basic256SHA256': self.query_one("#policy_b256sha256", RadioButton).value = True

        # anonymous è True se mode è 'None'
        self.update_auth_fields(mode == 'None')

    def update_auth_fields(self, anonymous: bool) -> None:
        """Abilita o disabilita i campi di autenticazione in base alla modalità selezionata."""
        self.query_one("#user_input", Input).disabled = anonymous
        self.query_one("#pass_input", Input).disabled = anonymous
        self.query_one("#user_label", Label).visible = not anonymous
        self.query_one("#pass_label", Label).visible = not anonymous
        
        # La sezione sicurezza rimane visibile perché contiene i selettori
        self.query_one("#policy_set", RadioSet).disabled = anonymous

    @on(RadioSet.Changed, "#mode_set")
    def on_mode_changed(self, event: RadioSet.Changed) -> None:
        is_anonymous = (event.pressed.id == "mode_none")
        if is_anonymous:
            # Se la modalità è None, forza anche la policy a None
            self.query_one("#policy_none", RadioButton).value = True
        self.update_auth_fields(is_anonymous)

    @on(Input.Changed, "#ip_input")
    def on_ip_changed(self, event: Input.Changed) -> None:
        if event.input.has_focus:
            url_input = self.query_one("#url_input", Input)
            port = self.query_one("#port_input", Input).value
            ip = event.value
            url_input.value = f"opc.tcp://{ip}:{port}/"

    @on(Input.Changed, "#port_input")
    def on_port_changed(self, event: Input.Changed) -> None:
        if event.input.has_focus:
            url_input = self.query_one("#url_input", Input)
            ip = self.query_one("#ip_input", Input).value
            port = event.value
            url_input.value = f"opc.tcp://{ip}:{port}/"

    @on(Input.Changed, "#url_input")
    def on_url_changed(self, event: Input.Changed) -> None:
        if event.input.has_focus:
            url = event.value
            match = re.match(r"opc\.tcp://([^:/]+)(?::(\d+))?", url)
            if match:
                new_ip = match.group(1)
                new_port = match.group(2)
                
                ip_input = self.query_one("#ip_input", Input)
                if ip_input.value != new_ip:
                    ip_input.value = new_ip
                
                if new_port:
                    port_input = self.query_one("#port_input", Input)
                    if port_input.value != new_port:
                        port_input.value = new_port

    @on(Button.Pressed, "#save_btn")
    def save_config(self):
        ip = self.query_one("#ip_input", Input).value
        port = self.query_one("#port_input", Input).value
        url = self.query_one("#url_input", Input).value
        commessa = self.query_one("#commessa_input", Input).value
        read_interval_raw = self.query_one("#read_interval_input", Input).value
        read_records_raw = self.query_one("#read_records_input", Input).value
        run_mode_set = self.query_one("#run_mode_set", RadioSet)
        run_mode = "normal"
        if run_mode_set.pressed_button and str(run_mode_set.pressed_button.label).strip().lower() == "debug":
            run_mode = "debug"
        sub_publish_ms_raw = self.query_one("#sub_publish_ms_input", Input).value
        sub_sampling_ms_raw = self.query_one("#sub_sampling_ms_input", Input).value
        deadband_global_raw = self.query_one("#deadband_global_input", Input).value
        
        # Recupera Security Mode e Policy selezionata
        mode_set = self.query_one("#mode_set", RadioSet)
        security_mode = "None"
        if mode_set.pressed_button:
            security_mode = str(mode_set.pressed_button.label)
        
        # Se mode è None, allora è anonimo
        anonymous = (security_mode == "None")
        
        username = self.query_one("#user_input", Input).value
        password = self.query_one("#pass_input", Input).value
        
        security_policy = "None"
        if not anonymous:
            policy_set = self.query_one("#policy_set", RadioSet)
            if policy_set.pressed_button:
                security_policy = str(policy_set.pressed_button.label)
        
        config = self.config_loader.get_config()
        config['opcua']['server']['ip'] = ip
        try:
            config['opcua']['server']['port'] = int(port)
        except ValueError:
            pass
        
        config['opcua']['client']['url'] = url
        config['opcua']['client']['commessa'] = commessa
        try:
            read_interval_seconds = int(str(read_interval_raw).strip() or "30")
        except ValueError:
            read_interval_seconds = 30
        if read_interval_seconds < 1:
            read_interval_seconds = 30
        try:
            read_records = int(str(read_records_raw).strip() or "0")
        except ValueError:
            read_records = 0
        if read_records < 0:
            read_records = 0
        config['opcua']['client']['read_interval_seconds'] = read_interval_seconds
        config['opcua']['client']['read_records'] = read_records
        config['opcua']['client']['run_mode'] = run_mode
        try:
            subscription_publishing_interval_ms = int(str(sub_publish_ms_raw).strip() or "3000")
        except ValueError:
            subscription_publishing_interval_ms = 3000
        if subscription_publishing_interval_ms < 0:
            subscription_publishing_interval_ms = 3000
        try:
            subscription_sampling_interval_ms = int(str(sub_sampling_ms_raw).strip() or "3000")
        except ValueError:
            subscription_sampling_interval_ms = 3000
        if subscription_sampling_interval_ms < 0:
            subscription_sampling_interval_ms = 3000
        try:
            deadband_global = float(str(deadband_global_raw).strip() or "1.0")
        except ValueError:
            deadband_global = 1.0
        if deadband_global < 0:
            deadband_global = 1.0
        config['opcua']['client']['subscription_publishing_interval_ms'] = subscription_publishing_interval_ms
        config['opcua']['client']['subscription_sampling_interval_ms'] = subscription_sampling_interval_ms
        config['opcua']['client']['deadband_global'] = deadband_global
        config['opcua']['client']['anonymous'] = anonymous
        config['opcua']['client']['username'] = username
        config['opcua']['client']['password'] = password
        config['opcua']['client']['security_mode'] = security_mode
        config['opcua']['client']['security_policy'] = security_policy
        
        if self.config_loader.save_config(config):
            self.notify("Configurazione salvata!", severity="information")
        else:
            self.notify("Errore durante il salvataggio!", severity="error")

class TextualHandler(logging.Handler):
    """Handler di logging per reindirizzare i log al widget RichLog di Textual."""
    def __init__(self, log_widget: RichLog):
        super().__init__()
        self.log_widget = log_widget

    def emit(self, record):
        try:
            msg = self.format(record)
            try:
                self.log_widget.write(msg, markup=False, highlight=False)
            except TypeError:
                self.log_widget.write(rich_escape(msg))
        except Exception:
            return

class BrowserScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Indietro"),
        ("r", "refresh_node", "Aggiorna"),
        ("e", "export_variables", "Estrai Nodi"),
        ("d", "read_opcua", "Read OPC UA"),
        ("c", "load_database", "Carica DB"),
        ("t", "test_database", "Test DB"),
    ]

    CSS = """
    BrowserScreen {
        layout: vertical;
    }
    #main-content {
        layout: horizontal;
        height: 1fr;
    }
    #tree-view {
        width: 50%;
        height: 100%;
        border: solid green;
    }
    #details-view {
        width: 50%;
        height: 100%;
        border: solid blue;
        padding: 1;
    }
    #log-panel {
        height: 10;
        border: solid red;
        background: black;
        color: white;
    }
    .label-key {
        color: yellow;
        text-style: bold;
    }
    .label-val {
        color: white;
    }
    """

    def __init__(self, explorer: OPCUAExplorer, read_mode: bool = False):
        super().__init__()
        self.explorer = explorer
        self.root_node = None
        self.log_handler = None
        self.selected_tree_node = None
        self.selected_opcua_node = None
        self.selected_node_name = None
        self.read_mode = read_mode
        self._read_started_from_mode = False
        self._read_running = False
        self._stop_after_current_read = False
        self._stop_read_event = asyncio.Event()
        self._read_plan_cache = {}
        self._db_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._db_conn = None
        self._db_conn_dt_type = None
        self._db_conn_fingerprint = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Horizontal(
            Tree("Root", id="tree-view"),
            Vertical(
                Label("Dettagli Nodo", classes="title"),
                Static(id="details-panel"),
                id="details-view"
            ),
            id="main-content"
        )
        yield RichLog(highlight=True, markup=True, id="log-panel")
        yield Footer()

    async def on_mount(self) -> None:
        # Configura il logging per catturare i messaggi di asyncua
        log_panel = self.query_one("#log-panel", RichLog)
        self.log_handler = TextualHandler(log_panel)
        formatter = logging.Formatter('%(levelname)s: %(message)s')
        self.log_handler.setFormatter(formatter)
        
        # Aggiunge l'handler sia al logger globale che a quello di asyncua
        logging.getLogger().addHandler(self.log_handler)
        logging.getLogger("asyncua").addHandler(self.log_handler)
        logging.getLogger("asyncua").setLevel(logging.INFO)
        logging.getLogger("asyncua.client").setLevel(logging.INFO)
        logging.getLogger("asyncua.client.ua_client").setLevel(logging.WARNING)

        tree = self.query_one(Tree)
        tree.show_root = False
        self.load_root()

    async def on_unmount(self) -> None:
        # Rimuove l'handler per evitare perdite di memoria o log in schermate sbagliate
        if self.log_handler:
            logging.getLogger().removeHandler(self.log_handler)
            logging.getLogger("asyncua").removeHandler(self.log_handler)
        try:
            await self._close_db_connection_async()
        except Exception:
            pass
        try:
            self._db_executor.shutdown(wait=False)
        except Exception:
            pass

    @work
    async def load_root(self):
        tree = self.query_one(Tree)
        details_panel = self.query_one("#details-panel", Static)
        log_panel = self.query_one("#log-panel", RichLog)
        
        # Piccolo ritardo per permettere il rendering della UI
        await asyncio.sleep(0.5)
        
        try:
            log_panel.write("[bold cyan]>>> Inizio procedura di connessione...[/bold cyan]")
            # Stato caricamento nel pannello dettagli (evitiamo notifiche di sistema se possibile)
            msg = f"Tentativo di connessione a {self.explorer.url}..."
            details_panel.update(f"[bold yellow]{msg}[/bold yellow]")
            
            # Connessione
            if not self.explorer.connected: 
                 await self.explorer.connect()
            
            # Carica figli di root
            try:
                self.root_node = self.explorer.client.nodes.root
                # Verifica che root sia leggibile
                await self.root_node.read_browse_name()
            except Exception as e:
                import logging
                logging.getLogger("cobrakai_OPCUA_Browser").error(f"Errore accesso root node: {e}", exc_info=True)
                raise Exception(f"Impossibile accedere al nodo Root: {e}")

            await self.expand_node(tree.root, self.root_node)
            tree.root.expand()
            
            # Se la connessione va a buon fine, nascondi log e non mostrare notifiche
            log_panel.display = "none"
            success_msg = "Connesso con successo al PLC!"
            details_panel.update(f"[bold green]{success_msg}[/bold green]\n\nSeleziona un nodo nell'albero a sinistra per vederne i dettagli.")
            
        except ConnectionError as e:
            import logging
            logging.getLogger("cobrakai_OPCUA_Browser").error(f"Eccezione durante la connessione: {e}", exc_info=True)
            error_msg = f"ERRORE DI CONNESSIONE:\n\n[bold red]{str(e)}[/bold red]\n\n[yellow]Suggerimenti:[/yellow]\n1. Verifica che l'URL sia corretto\n2. Controlla Username e Password\n3. Assicurati che il PLC sia raggiungibile via rete"
            self.notify("Errore di connessione (vedi dettagli)", severity="error", timeout=10)
            details_panel.update(error_msg)
        except Exception as e:
            import logging
            logging.getLogger("cobrakai_OPCUA_Browser").error(f"Eccezione inaspettata durante la connessione: {e}", exc_info=True)
            error_msg = f"ERRORE INASPETTATO:\n\n[bold red]{type(e).__name__}: {e}[/bold red]"
            self.notify("Errore inaspettato (vedi dettagli)", severity="error", timeout=10)
            details_panel.update(error_msg)

    async def expand_node(self, tree_node, opcua_node):
        """Carica i figli di un nodo OPC UA nell'albero Textual"""
        try:
            children = await self.explorer.browse_children(opcua_node)
            for child in children:
                # Crea etichetta nodo: [Class] Name
                label = f"[{child['class']}] {child['name']}"
                
                # Aggiungi al tree
                new_node = tree_node.add(
                    label,
                    data={"node": child["node"], "name": child["name"], "class": child["class"]},
                    allow_expand=True,
                )
                
                # Se non ha figli (es. Variabile semplice), potremmo disabilitare expand, 
                # ma browse_children controlla già. 
                # Per performance, non carichiamo ricorsivamente qui.
        except Exception as e:
            tree_node.add(f"Errore: {e}")

    @on(Tree.NodeExpanded)
    @work
    async def on_node_expanded(self, event: Tree.NodeExpanded) -> None:
        node = event.node
        if node.data: # Se ha un nodo OPC UA associato
            if not node.children: # Carica solo se non ha già figli caricati
                data = node.data
                opcua_node = data.get("node") if isinstance(data, dict) else data
                await self.expand_node(node, opcua_node)

    @on(Tree.NodeSelected)
    @work
    async def on_node_selected(self, event: Tree.NodeSelected) -> None:
        node = event.node
        data = node.data
        opcua_node = data.get("node") if isinstance(data, dict) else data
        if opcua_node:
            self.selected_tree_node = node
            self.selected_opcua_node = opcua_node
            if isinstance(data, dict):
                self.selected_node_name = data.get("name")
            details = f"[bold]Nome:[/bold] {node.label}\n"
            details += f"[bold]ID:[/bold] {opcua_node.nodeid}\n"
            
            if isinstance(data, dict):
                node_class_name = str(data.get("class", "") or "")
                if node_class_name:
                    details += f"[bold]Classe:[/bold] {node_class_name}\n"
            
            self.query_one("#details-panel", Static).update(details)

    def action_export_variables(self) -> None:
        self._schedule_close_db_connection()
        tree_node, opcua_node, selected_name = self._get_current_tree_selection()
        if not opcua_node:
            self.notify("Seleziona un nodo prima di estrarre", severity="warning", timeout=4)
            return
        self.export_variables(opcua_node, selected_name)

    def action_read_opcua(self) -> None:
        self._schedule_close_db_connection()
        tree_node, opcua_node, selected_name = self._get_current_tree_selection()
        if not opcua_node:
            self.notify("Seleziona un nodo prima di leggere", severity="warning", timeout=4)
            return
        self.read_opcua(opcua_node, selected_name)

    def action_refresh_node(self) -> None:
        self._schedule_close_db_connection()
        try:
            tree = self.query_one("#tree-view", Tree)
            try:
                tree.clear()
            except Exception:
                pass
            self.load_root()
        except Exception:
            pass

    def action_load_database(self) -> None:
        tree_node, opcua_node, selected_name = self._get_current_tree_selection()
        if not opcua_node:
            self.notify("Seleziona un nodo prima di caricare", severity="warning", timeout=4)
            return
        self.load_database(opcua_node, selected_name)

    def action_test_database(self) -> None:
        self._schedule_close_db_connection()
        _, opcua_node, selected_name = self._get_current_tree_selection()
        self.test_database(opcua_node, selected_name)

    def _schedule_close_db_connection(self) -> None:
        try:
            asyncio.get_running_loop().create_task(self._close_db_connection_async())
        except Exception:
            pass

    async def _db_run(self, func, *args):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._db_executor, lambda: func(*args))

    def _db_cfg_fingerprint(self, db_cfg: dict) -> tuple:
        dt_type = int((db_cfg or {}).get("dt_type", 1) or 1)
        host = str((db_cfg or {}).get("host", "") or "").strip()
        port_raw = (db_cfg or {}).get("port", None)
        try:
            port = int(port_raw) if port_raw is not None and str(port_raw).strip() != "" else 0
        except Exception:
            port = 0
        database = str((db_cfg or {}).get("database", "") or "").strip()
        user = str((db_cfg or {}).get("user", "") or "").strip()
        driver = str((db_cfg or {}).get("driver", "") or "").strip()
        return dt_type, host, port, database, user, driver

    def _db_ping_sync(self, conn, dt_type: int) -> bool:
        try:
            if dt_type == 1:
                cur = conn.cursor()
                cur.execute("SELECT 1")
                cur.fetchone()
                return True
            if dt_type in (2, 3):
                cur = conn.cursor()
                cur.execute("SELECT 1")
                cur.fetchone()
                return True
        except Exception:
            return False
        return False

    def _db_close_sync(self) -> None:
        conn = getattr(self, "_db_conn", None)
        if conn is None:
            return
        try:
            conn.close()
        except Exception:
            pass
        self._db_conn = None
        self._db_conn_dt_type = None
        self._db_conn_fingerprint = None

    async def _close_db_connection_async(self) -> None:
        await self._db_run(self._db_close_sync)

    def _db_open_connection_mssql_sync(self, db_cfg: dict):
        import pyodbc

        dt_type = int(db_cfg.get("dt_type", 1) or 1)
        host = str(db_cfg.get("host", "") or "").strip()
        database = str(db_cfg.get("database", "") or "").strip()
        user = str(db_cfg.get("user", "") or "").strip()
        password = str(db_cfg.get("password", "") or "")

        port_raw = db_cfg.get("port", None)
        try:
            port = int(port_raw) if port_raw is not None and str(port_raw).strip() != "" else 0
        except Exception:
            port = 0
        if port <= 0:
            port = self._mssql_default_port(dt_type)

        if not host or not database or not user:
            raise RuntimeError("config destination_database incompleta (host/database/user)")

        installed = [str(d) for d in (pyodbc.drivers() or [])]
        candidates: list[str] = []
        configured_driver = db_cfg.get("driver")
        if configured_driver is not None and str(configured_driver).strip():
            candidates.append(str(configured_driver).strip())
        else:
            def ver(d: str) -> int:
                m = re.search(r"ODBC Driver\s+(\d+)\s+for\s+SQL\s+Server", d, flags=re.IGNORECASE)
                return int(m.group(1)) if m else -1

            modern = sorted(
                [d for d in installed if re.search(r"ODBC Driver\s+\d+\s+for\s+SQL\s+Server", d, flags=re.IGNORECASE)],
                key=ver,
                reverse=True,
            )
            candidates.extend(modern or ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server"])

        if "\\" in host:
            server_variants = [host]
        else:
            server_variants = []
            if port:
                server_variants.append(f"tcp:{host},{port}")
                server_variants.append(f"{host},{port}")
            server_variants.append(f"tcp:{host}")
            server_variants.append(f"{host}")

        variants = [
            "Encrypt=no;TrustServerCertificate=yes;",
            "Encrypt=yes;TrustServerCertificate=yes;",
            "",
        ]
        last_error: Exception | None = None
        for driver in candidates:
            if not driver:
                continue
            for server in server_variants:
                for extra in variants:
                    try:
                        return pyodbc.connect(
                            f"DRIVER={{{driver}}};"
                            f"SERVER={server};"
                            f"DATABASE={database};"
                            f"UID={user};"
                            f"PWD={password};"
                            "Connection Timeout=15;"
                            + extra,
                            autocommit=False,
                            timeout=5,
                        )
                    except Exception as e:
                        last_error = e
                        continue
        installed_msg = ", ".join(installed) if installed else "(nessun driver ODBC trovato da pyodbc)"
        raise RuntimeError(
            "Connessione a SQL Server fallita. "
            f"Driver rilevati: {installed_msg}. "
            f"Server: {', '.join(server_variants)}. "
            f"Ultimo errore: {type(last_error).__name__}: {last_error}"
        )

    def _db_open_connection_mysql_sync(self, db_cfg: dict):
        try:
            import pymysql
        except Exception as e:
            raise RuntimeError(f"pymysql non disponibile: {e}")

        dt_type = int(db_cfg.get("dt_type", 2) or 2)
        host = str(db_cfg.get("host", "") or "").strip()
        database = str(db_cfg.get("database", "") or "").strip()
        user = str(db_cfg.get("user", "") or "").strip()
        password = str(db_cfg.get("password", "") or "")

        port_raw = db_cfg.get("port", None)
        try:
            port = int(port_raw) if port_raw is not None and str(port_raw).strip() != "" else 0
        except Exception:
            port = 0
        if port <= 0:
            port = self._mssql_default_port(dt_type)

        if not host or not database or not user:
            raise RuntimeError("config destination_database incompleta (host/database/user)")

        return pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            charset="utf8mb4",
            autocommit=False,
        )

    def _db_ensure_connection_sync(self, db_cfg: dict) -> tuple[bool, str]:
        logger = logging.getLogger("cobrakai_OPCUA_Browser")
        fp = self._db_cfg_fingerprint(db_cfg)
        dt_type = int((db_cfg or {}).get("dt_type", 1) or 1)
        if self._db_conn is not None and self._db_conn_fingerprint == fp:
            if self._db_ping_sync(self._db_conn, dt_type):
                return True, ""
            self._db_close_sync()

        self._db_close_sync()
        try:
            if dt_type == 1:
                conn = self._db_open_connection_mssql_sync(db_cfg)
            elif dt_type in (2, 3):
                conn = self._db_open_connection_mysql_sync(db_cfg)
            else:
                return False, f"dt_type non supportato: {dt_type} (supportati: 1 MSSQL, 2 MariaDB, 3 MySql)"
        except Exception as e:
            logger.error(f"DB connect: errore dt_type={dt_type}: {type(e).__name__}: {e}")
            return False, f"{e}"

        self._db_conn = conn
        self._db_conn_dt_type = dt_type
        self._db_conn_fingerprint = fp
        logger.info(f"DB connect: ok dt_type={dt_type}")
        return True, ""

    def _db_test_connection_only_sync(self, db_cfg: dict) -> tuple[bool, str]:
        fp = self._db_cfg_fingerprint(db_cfg)
        dt_type = int((db_cfg or {}).get("dt_type", 1) or 1)
        ok, err = self._db_ensure_connection_sync(db_cfg)
        if not ok:
            return False, err
        ok_ping = self._db_ping_sync(self._db_conn, dt_type)
        self._db_close_sync()
        self._db_conn_fingerprint = fp
        return (True, "") if ok_ping else (False, "ping fallito")

    def _db_write_rows_mssql_sync(self, conn, table_name: str, rows: list[dict]) -> tuple[bool, str]:
        cols = [
            ("Level", "INT NULL"),
            ("NodeId", "NVARCHAR(512) NOT NULL"),
            ("NomeVariabile", "NVARCHAR(512) NULL"),
            ("NomeS7protocolname", "NVARCHAR(512) NULL"),
            ("NodeClass", "NVARCHAR(64) NULL"),
            ("BrowseName", "NVARCHAR(256) NULL"),
            ("DisplayName", "NVARCHAR(256) NULL"),
            ("Tipo", "NVARCHAR(128) NULL"),
            ("Valore", "NVARCHAR(MAX) NULL"),
            ("opcuasoglia", "NVARCHAR(5) NULL"),
        ]

        def _b(s: str) -> str:
            return f"[{s}]"

        full_table = f"dbo.{_b(table_name)}"
        full_table_obj_id = f"dbo.{table_name}"

        drop_sql = f"IF OBJECT_ID(N'{full_table_obj_id}', N'U') IS NOT NULL DROP TABLE {full_table};"
        create_cols_sql = ", ".join([f"{_b(n)} {t}" for (n, t) in cols])
        create_sql = (
            f"CREATE TABLE {full_table} ("
            "[id] INT IDENTITY(1,1) NOT NULL PRIMARY KEY, "
            f"{create_cols_sql}"
            ");"
        )

        insert_cols = ["Level", "NodeId", "NomeVariabile", "NomeS7protocolname", "NodeClass", "BrowseName", "DisplayName", "Tipo", "Valore", "opcuasoglia"]
        insert_cols_sql = ", ".join(_b(c) for c in insert_cols)
        placeholders = ", ".join("?" for _ in insert_cols)
        insert_sql = f"INSERT INTO {full_table} ({insert_cols_sql}) VALUES ({placeholders});"

        def _get(row: dict, k: str) -> str:
            v = row.get(k, "")
            return "" if v is None else str(v)

        values = []
        for r in rows:
            try:
                level = r.get("level", None)
                level_int = int(level) if level is not None and str(level).strip() != "" else None
            except Exception:
                level_int = None

            nid = r.get("node_id", "")
            try:
                nome_var = self._make_nome_variabile_from_node_id(nid)
            except Exception:
                nome_var = ""
            try:
                nome_s7 = self._make_s7_protocol_name_from_node_id(nid)
            except Exception:
                nome_s7 = ""

            t_raw = r.get("type", r.get("python_type", ""))
            t_str = str(t_raw or "").strip().lower()
            if t_str == "int":
                soglia_str = "1"
            elif t_str == "float":
                soglia_str = "0.1"
            else:
                soglia_str = "0"

            values.append(
                (
                    level_int,
                    str(nid),
                    nome_var,
                    nome_s7,
                    _get(r, "node_class"),
                    _get(r, "browse_name"),
                    _get(r, "display_name"),
                    _get(r, "type"),
                    _get(r, "value"),
                    soglia_str,
                )
            )

        try:
            cur = conn.cursor()
            cur.execute(drop_sql)
            cur.execute(create_sql)
            try:
                cur.fast_executemany = True
            except Exception:
                pass
            if values:
                cur.executemany(insert_sql, values)
            conn.commit()
            return True, ""
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            return False, f"errore db: {type(e).__name__}: {e}"

    def _db_write_rows_mysql_sync(self, conn, table_name: str, rows: list[dict]) -> tuple[bool, str]:
        cols = [
            ("Level", "INT NULL"),
            ("NodeId", "VARCHAR(512) NOT NULL"),
            ("NomeVariabile", "VARCHAR(512) NULL"),
            ("NomeS7protocolname", "VARCHAR(512) NULL"),
            ("NodeClass", "VARCHAR(64) NULL"),
            ("BrowseName", "VARCHAR(256) NULL"),
            ("DisplayName", "VARCHAR(256) NULL"),
            ("Tipo", "VARCHAR(128) NULL"),
            ("Valore", "LONGTEXT NULL"),
            ("opcuasoglia", "VARCHAR(5) NULL"),
        ]

        def _b(s: str) -> str:
            return f"`{s}`"

        drop_sql = f"DROP TABLE IF EXISTS {_b(table_name)};"
        create_cols_sql = ", ".join([f"{_b(n)} {t}" for (n, t) in cols])
        create_sql = (
            f"CREATE TABLE {_b(table_name)} ("
            f"{_b('id')} INT NOT NULL AUTO_INCREMENT PRIMARY KEY, "
            f"{create_cols_sql}"
            ") CHARACTER SET utf8mb4;"
        )

        insert_cols = ["Level", "NodeId", "NomeVariabile", "NomeS7protocolname", "NodeClass", "BrowseName", "DisplayName", "Tipo", "Valore", "opcuasoglia"]
        insert_cols_sql = ", ".join(_b(c) for c in insert_cols)
        placeholders = ", ".join(["%s"] * len(insert_cols))
        insert_sql = f"INSERT INTO {_b(table_name)} ({insert_cols_sql}) VALUES ({placeholders});"

        def _get(row: dict, k: str) -> str:
            v = row.get(k, "")
            return "" if v is None else str(v)

        values = []
        for r in rows:
            try:
                level = r.get("level", None)
                level_int = int(level) if level is not None and str(level).strip() != "" else None
            except Exception:
                level_int = None

            nid = r.get("node_id", "")
            try:
                nome_var = self._make_nome_variabile_from_node_id(nid)
            except Exception:
                nome_var = ""
            try:
                nome_s7 = self._make_s7_protocol_name_from_node_id(nid)
            except Exception:
                nome_s7 = ""

            t_raw = r.get("type", r.get("python_type", ""))
            t_str = str(t_raw or "").strip().lower()
            if t_str == "int":
                soglia_str = "1"
            elif t_str == "float":
                soglia_str = "0.1"
            else:
                soglia_str = "0"

            values.append(
                (
                    level_int,
                    str(nid),
                    nome_var,
                    nome_s7,
                    _get(r, "node_class"),
                    _get(r, "browse_name"),
                    _get(r, "display_name"),
                    _get(r, "type"),
                    _get(r, "value"),
                    soglia_str,
                )
            )

        try:
            cur = conn.cursor()
            cur.execute(drop_sql)
            cur.execute(create_sql)
            if values:
                cur.executemany(insert_sql, values)
            conn.commit()
            return True, ""
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            return False, f"errore db: {type(e).__name__}: {e}"

    def _db_write_rows_sync(self, table_name: str, rows: list[dict]) -> tuple[bool, str]:
        dt_type = int(getattr(self, "_db_conn_dt_type", 0) or 0)
        conn = getattr(self, "_db_conn", None)
        if conn is None:
            return False, "connessione non inizializzata"
        if dt_type == 1:
            return self._db_write_rows_mssql_sync(conn, table_name, rows)
        if dt_type in (2, 3):
            return self._db_write_rows_mysql_sync(conn, table_name, rows)
        return False, f"dt_type non supportato: {dt_type}"

    def request_graceful_quit(self) -> bool:
        if not self._read_running:
            return False
        self._stop_after_current_read = True
        try:
            self._stop_read_event.set()
        except Exception:
            pass
        try:
            details_panel = self.query_one("#details-panel", Static)
            details_panel.update(
                "[bold yellow]Uscita richiesta[/bold yellow]\n\n"
                "Completo la lettura in corso e poi termino."
            )
        except Exception:
            pass
        return True

    def _get_current_tree_selection(self):
        try:
            tree = self.query_one("#tree-view", Tree)
        except Exception:
            tree = None

        tree_node = None
        if tree is not None:
            tree_node = getattr(tree, "cursor_node", None) or getattr(tree, "selected_node", None)

        if tree_node is None:
            tree_node = getattr(self, "selected_tree_node", None)

        if tree_node is None:
            return None, None, ""

        data = getattr(tree_node, "data", None)
        opcua_node = data.get("node") if isinstance(data, dict) else data
        selected_name = data.get("name") if isinstance(data, dict) else ""

        if not selected_name:
            try:
                label = getattr(tree_node, "label", "")
                label_text = getattr(label, "plain", None)
                if label_text is None:
                    label_text = str(label)
                label_text = str(label_text)
                match = re.match(r"^\[[^\]]+\]\s*(.*)$", label_text)
                if match:
                    label_text = match.group(1)
                selected_name = label_text.split(" = ", 1)[0].strip()
            except Exception:
                selected_name = ""

        return tree_node, opcua_node, selected_name

    def _sanitize_export_name(self, name: str) -> str:
        name = str(name or "")
        name = re.sub(r"[\x00-\x1F]", "", name).strip()
        name = re.sub(r"[<>:\"/\\\\|?*]", "_", name)
        name = re.sub(r"[\s_]+", "_", name).strip()
        name = re.sub(r"_+", "_", name)
        name = name.strip(" ._")
        if not name:
            name = "OPCUA_Node"
        if len(name) > 120:
            name = name[:120].rstrip(" .")
        return name

    def _extract_node_name_for_filename(self) -> str:
        try:
            node = getattr(self, "selected_tree_node", None)
            if not node:
                return ""

            label = getattr(node, "label", "")
            label_text = getattr(label, "plain", None)
            if label_text is None:
                label_text = str(label)
            label_text = str(label_text)

            match = re.match(r"^\[[^\]]+\]\s*(.*)$", label_text)
            if match:
                label_text = match.group(1)

            label_text = label_text.split(" = ", 1)[0].strip()
            return label_text
        except Exception:
            return ""

    def _make_export_output_path(self, commessa: str, node_name: str) -> str:
        base_dir = os.path.join(os.getcwd(), "opcuaNodes")
        os.makedirs(base_dir, exist_ok=True)

        commessa_stem = self._sanitize_export_name(commessa).strip()
        node_stem = self._sanitize_export_name(node_name)

        if commessa_stem:
            output_dir = os.path.join(base_dir, commessa_stem)
            os.makedirs(output_dir, exist_ok=True)
            file_name = f"OPCUA_{commessa_stem}_{node_stem}.json"
            return os.path.join(output_dir, file_name)

        file_name = f"OPCUA_{node_stem}.json"
        return os.path.join(base_dir, file_name)

    def _truncate_excel_cell(self, value: object) -> object:
        if value is None:
            return None
        s = str(value)
        if len(s) > 32767:
            return s[:32760] + "..."
        return value

    def _is_variable_simple_type_row(self, row: dict) -> bool:
        node_class = str(row.get("node_class", "Variable") or "").strip().lower()
        if node_class and node_class != "variable":
            return False
        t = row.get("type", row.get("python_type", ""))
        t = str(t or "").strip().lower()
        return t in {"int", "bool", "float", "str"}

    def _make_nome_variabile_from_node_id(self, node_id: str) -> str:
        s = str(node_id or "")
        s = s.replace('ns=3;s="', "")
        s = s.replace('"."', "_")
        s = s.replace('"[', "_")
        s = s.replace(']."', "_")
        s = s.replace('[', "_")
        s = s.replace(']', "")
        if s.endswith('"'):
            s = s[:-1]
        return s

    def _make_s7_protocol_name_from_node_id(self, node_id: str) -> str:
        s = str(node_id or "")
        s = s.replace('ns=3;s="', "")
        s = s.replace('"."', ".")
        s = s.replace('"[', "[")
        s = s.replace(']"."', "].")
        s = s.replace('"', "")
        return s

    def _dedupe_headers(self, names: list[str]) -> list[str]:
        seen = {}
        out = []
        for n in names:
            base = str(n or "").strip() or "Variabile"
            if base in seen:
                seen[base] += 1
                out.append(f"{base}_{seen[base]}")
            else:
                seen[base] = 1
                out.append(base)
        return out

    def _make_variabili_json_path(self, commessa: str, node_name: str) -> str:
        base_json_path = self._make_export_output_path(commessa, node_name)
        base = os.path.splitext(base_json_path)[0]
        return base + "_Variabili.json"

    def _make_table_name_from_variabili_json(self, variabili_json_path: str) -> str:
        base = os.path.splitext(os.path.basename(variabili_json_path))[0]
        if base.endswith("_Variabili"):
            base = base[: -len("_Variabili")]
        if base.startswith("OPCUA_"):
            base = base[len("OPCUA_") :]
        base = re.sub(r"[^0-9A-Za-z_]+", "_", base).strip("_")
        if not base:
            base = "OPCUA_Table"
        if len(base) > 120:
            base = base[:120].rstrip("_")
        return base

    def _load_variabili_json_sync(self, variabili_json_path: str) -> tuple[list[dict], str]:
        if not os.path.exists(variabili_json_path):
            return [], f"file non trovato: {variabili_json_path}"
        try:
            with open(variabili_json_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as e:
            return [], f"impossibile leggere json: {type(e).__name__}: {e}"
        rows = payload.get("rows", [])
        if not isinstance(rows, list):
            return [], "formato json non valido: 'rows' non è una lista"
        out = []
        for r in rows:
            if isinstance(r, dict):
                out.append(r)
        out.sort(key=lambda d: str(d.get("node_id", "") or ""))
        return out, ""

    def _mssql_default_port(self, dt_type: int) -> int:
        defaults = {1: 1433, 2: 3306, 3: 3306, 4: 5432}
        return defaults.get(int(dt_type or 0), 0)

    def _load_database_mysql_sync(
        self,
        db_cfg: dict,
        table_name: str,
        rows: list[dict],
    ) -> tuple[bool, str]:

        logger = logging.getLogger("cobrakai_OPCUA_Browser")
        try:
            import pymysql
        except Exception:
            pymysql = None

        try:
            import mysql.connector  # type: ignore
        except Exception:
            mysql = None
        else:
            mysql = mysql.connector

        dt_type = int(db_cfg.get("dt_type", 2) or 2)
        if dt_type not in (2, 3):
            return False, f"dt_type non supportato per MySQL/MariaDB: {dt_type} (supportati: 2 MariaDB, 3 MySql)"

        host = str(db_cfg.get("host", "") or "").strip()
        database = str(db_cfg.get("database", "") or "").strip()
        user = str(db_cfg.get("user", "") or "").strip()
        password = str(db_cfg.get("password", "") or "")

        port_raw = db_cfg.get("port", None)
        try:
            port = int(port_raw) if port_raw is not None and str(port_raw).strip() != "" else 0
        except Exception:
            port = 0
        if port <= 0:
            port = self._mssql_default_port(dt_type)

        if not host or not database or not user:
            return False, "config destination_database incompleta (host/database/user)"

        logger.info(
            f"DB connect: destination_database dt_type={dt_type} host={host} port={port} database={database} table={table_name}"
        )

        cols = [
            ("Level", "INT NULL"),
            ("NodeId", "VARCHAR(512) NOT NULL"),
            ("NodeClass", "VARCHAR(64) NULL"),
            ("BrowseName", "VARCHAR(256) NULL"),
            ("DisplayName", "VARCHAR(256) NULL"),
            ("Tipo", "VARCHAR(128) NULL"),
            ("Valore", "LONGTEXT NULL"),
        ]

        def _b(s: str) -> str:
            return f"`{s}`"

        drop_sql = f"DROP TABLE IF EXISTS {_b(table_name)};"
        create_cols_sql = ", ".join([f"{_b(n)} {t}" for (n, t) in cols])
        create_sql = (
            f"CREATE TABLE {_b(table_name)} ("
            f"{_b('id')} INT NOT NULL AUTO_INCREMENT PRIMARY KEY, "
            f"{create_cols_sql}"
            ") CHARACTER SET utf8mb4;"
        )

        insert_cols = ["Level", "NodeId", "NodeClass", "BrowseName", "DisplayName", "Tipo", "Valore"]
        insert_cols_sql = ", ".join(_b(c) for c in insert_cols)
        placeholders = ", ".join(["%s"] * len(insert_cols))
        insert_sql = f"INSERT INTO {_b(table_name)} ({insert_cols_sql}) VALUES ({placeholders});"

        def _get(row: dict, k: str) -> str:
            v = row.get(k, "")
            return "" if v is None else str(v)

        values = []
        for r in rows:
            try:
                level = r.get("level", None)
                level_int = int(level) if level is not None and str(level).strip() != "" else None
            except Exception:
                level_int = None
            values.append(
                (
                    level_int,
                    _get(r, "node_id"),
                    _get(r, "node_class"),
                    _get(r, "browse_name"),
                    _get(r, "display_name"),
                    _get(r, "type"),
                    _get(r, "value"),
                )
            )

        if pymysql is not None:
            try:
                conn = pymysql.connect(
                    host=host,
                    port=port,
                    user=user,
                    password=password,
                    database=database,
                    charset="utf8mb4",
                    autocommit=False,
                )
            except Exception as e:
                logger.error(
                    f"DB connect: errore destination_database dt_type={dt_type} host={host} port={port} database={database}: {type(e).__name__}: {e}"
                )
                return False, f"connessione fallita: {type(e).__name__}: {e}"
            logger.info(
                f"DB connect: ok destination_database dt_type={dt_type} host={host} port={port} database={database}"
            )
            try:
                with conn.cursor() as cur:
                    cur.execute(drop_sql)
                    cur.execute(create_sql)
                    if values:
                        cur.executemany(insert_sql, values)
                conn.commit()
                logger.info(f"DB write: ok table={table_name} rows={len(values)}")
                return True, ""
            except Exception as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                logger.error(f"DB write: errore table={table_name}: {type(e).__name__}: {e}")
                return False, f"errore db: {type(e).__name__}: {e}"
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

        if mysql is None:
            return False, "driver MariaDB/MySQL non trovato (installare pymysql o mysql-connector-python)"

        try:
            conn = mysql.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                charset="utf8mb4",
                autocommit=False,
            )
        except Exception as e:
            logger.error(
                f"DB connect: errore destination_database dt_type={dt_type} host={host} port={port} database={database}: {type(e).__name__}: {e}"
            )
            return False, f"connessione fallita: {type(e).__name__}: {e}"
        logger.info(f"DB connect: ok destination_database dt_type={dt_type} host={host} port={port} database={database}")

        try:
            cur = conn.cursor()
            cur.execute(drop_sql)
            cur.execute(create_sql)
            if values:
                cur.executemany(insert_sql, values)
            conn.commit()
            logger.info(f"DB write: ok table={table_name} rows={len(values)}")
            return True, ""
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.error(f"DB write: errore table={table_name}: {type(e).__name__}: {e}")
            return False, f"errore db: {type(e).__name__}: {e}"
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _load_database_mssql_sync(
        self,
        db_cfg: dict,
        table_name: str,
        rows: list[dict],
    ) -> tuple[bool, str]:
        logger = logging.getLogger("cobrakai_OPCUA_Browser")
        try:
            import pyodbc
        except Exception as e:
            return False, f"pyodbc non disponibile: {e}; installa: pip install pyodbc"

        dt_type = int(db_cfg.get("dt_type", 1) or 1)
        if dt_type != 1:
            return False, f"dt_type non supportato: {dt_type} (supportato: 1 MSSQL)"

        host = str(db_cfg.get("host", "") or "").strip()
        database = str(db_cfg.get("database", "") or "").strip()
        user = str(db_cfg.get("user", "") or "").strip()
        password = str(db_cfg.get("password", "") or "")

        port_raw = db_cfg.get("port", None)
        try:
            port = int(port_raw) if port_raw is not None and str(port_raw).strip() != "" else 0
        except Exception:
            port = 0
        if port <= 0:
            port = self._mssql_default_port(dt_type)

        if not host or not database or not user:
            return False, "config destination_database incompleta (host/database/user)"

        logger.info(
            f"DB connect: destination_database dt_type={dt_type} host={host} port={port} database={database} table={table_name}"
        )

        installed = [str(d) for d in (pyodbc.drivers() or [])]
        candidates: list[str] = []
        configured_driver = db_cfg.get("driver")
        if configured_driver is not None and str(configured_driver).strip():
            candidates.append(str(configured_driver).strip())
        else:
            def ver(d: str) -> int:
                m = re.search(r"ODBC Driver\s+(\d+)\s+for\s+SQL\s+Server", d, flags=re.IGNORECASE)
                return int(m.group(1)) if m else -1

            modern = sorted(
                [d for d in installed if re.search(r"ODBC Driver\s+\d+\s+for\s+SQL\s+Server", d, flags=re.IGNORECASE)],
                key=ver,
                reverse=True,
            )
            candidates.extend(modern or ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server"])

        if "\\" in host:
            server_variants = [host]
        else:
            server_variants = []
            if port:
                server_variants.append(f"tcp:{host},{port}")
                server_variants.append(f"{host},{port}")
            server_variants.append(f"tcp:{host}")
            server_variants.append(f"{host}")

        cols = [
            ("Level", "INT NULL"),
            ("NodeId", "NVARCHAR(512) NOT NULL"),
            ("NodeClass", "NVARCHAR(64) NULL"),
            ("BrowseName", "NVARCHAR(256) NULL"),
            ("DisplayName", "NVARCHAR(256) NULL"),
            ("Tipo", "NVARCHAR(128) NULL"),
            ("Valore", "NVARCHAR(MAX) NULL"),
        ]

        def _b(s: str) -> str:
            return f"[{s}]"

        full_table = f"dbo.{_b(table_name)}"
        full_table_obj_id = f"dbo.{table_name}"

        drop_sql = f"IF OBJECT_ID(N'{full_table_obj_id}', N'U') IS NOT NULL DROP TABLE {full_table};"
        create_cols_sql = ", ".join([f"{_b(n)} {t}" for (n, t) in cols])
        create_sql = (
            f"CREATE TABLE {full_table} ("
            "[id] INT IDENTITY(1,1) NOT NULL PRIMARY KEY, "
            f"{create_cols_sql}"
            ");"
        )

        insert_cols = ["Level", "NodeId", "NodeClass", "BrowseName", "DisplayName", "Tipo", "Valore"]
        insert_cols_sql = ", ".join(_b(c) for c in insert_cols)
        placeholders = ", ".join("?" for _ in insert_cols)
        insert_sql = f"INSERT INTO {full_table} ({insert_cols_sql}) VALUES ({placeholders});"

        def _get(row: dict, k: str) -> str:
            v = row.get(k, "")
            return "" if v is None else str(v)

        values = []
        for r in rows:
            try:
                level = r.get("level", None)
                level_int = int(level) if level is not None and str(level).strip() != "" else None
            except Exception:
                level_int = None
            values.append(
                (
                    level_int,
                    _get(r, "node_id"),
                    _get(r, "node_class"),
                    _get(r, "browse_name"),
                    _get(r, "display_name"),
                    _get(r, "type"),
                    _get(r, "value"),
                )
            )

        tried: list[str] = []
        last_error: Exception | None = None
        conn = None
        used_driver = ""
        used_extra = ""
        used_server = ""
        variants = [
            "Encrypt=no;TrustServerCertificate=yes;",
            "Encrypt=yes;TrustServerCertificate=yes;",
            "",
        ]
        for driver in candidates:
            if not driver or driver in tried:
                continue
            tried.append(driver)
            for server in server_variants:
                for extra in variants:
                    try:
                        conn = pyodbc.connect(
                            f"DRIVER={{{driver}}};"
                            f"SERVER={server};"
                            f"DATABASE={database};"
                            f"UID={user};"
                            f"PWD={password};"
                            "Connection Timeout=15;"
                            + extra,
                            autocommit=False,
                            timeout=5,
                        )
                        used_driver = driver
                        used_extra = extra
                        used_server = server
                        break
                    except Exception as e:
                        last_error = e
                        continue
                if conn is not None:
                    break
            if conn is not None:
                break

        if conn is None:
            installed_msg = ", ".join(installed) if installed else "(nessun driver ODBC trovato da pyodbc)"
            logger.error(
                f"DB connect: errore destination_database dt_type={dt_type} host={host} port={port} database={database}: {type(last_error).__name__}: {last_error}"
            )
            return (
                False,
                "Connessione a SQL Server fallita. "
                f"Driver rilevati: {installed_msg}. "
                f"Server: {', '.join(server_variants)}. "
                f"Ultimo errore: {type(last_error).__name__}: {last_error}",
            )
        logger.info(f"DB connect: ok destination_database dt_type={dt_type} host={host} port={port} database={database}")
        if used_driver:
            logger.info(f"DB connect: driver={used_driver} extra={'default' if not used_extra else used_extra}")
        if used_server:
            logger.info(f"DB connect: server={used_server}")

        try:
            cur = conn.cursor()
            cur.execute(drop_sql)
            cur.execute(create_sql)
            try:
                cur.fast_executemany = True
            except Exception:
                pass
            if values:
                cur.executemany(insert_sql, values)
            conn.commit()
            logger.info(f"DB write: ok table={table_name} rows={len(values)}")
            return True, ""
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.error(f"DB write: errore table={table_name}: {type(e).__name__}: {e}")
            return False, f"errore db: {type(e).__name__}: {e}"
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _load_database_sync(
        self,
        db_cfg: dict,
        table_name: str,
        rows: list[dict],
    ) -> tuple[bool, str]:
        dt_type = int(db_cfg.get("dt_type", 1) or 1)
        if dt_type == 1:
            return self._load_database_mssql_sync(db_cfg, table_name, rows)
        if dt_type in (2, 3):
            return self._load_database_mysql_sync(db_cfg, table_name, rows)
        return False, f"dt_type non supportato: {dt_type} (supportati: 1 MSSQL, 2 MariaDB, 3 MySql)"

    def _test_database_connection_mssql_sync(self, db_cfg: dict) -> tuple[bool, str]:
        logger = logging.getLogger("cobrakai_OPCUA_Browser")
        try:
            import pyodbc
        except Exception as e:
            return False, f"pyodbc non disponibile: {e}; installa: pip install pyodbc"

        dt_type = int(db_cfg.get("dt_type", 1) or 1)
        if dt_type != 1:
            return False, f"dt_type non supportato: {dt_type} (supportato: 1 MSSQL)"

        host = str(db_cfg.get("host", "") or "").strip()
        database = str(db_cfg.get("database", "") or "").strip()
        user = str(db_cfg.get("user", "") or "").strip()
        password = str(db_cfg.get("password", "") or "")

        port_raw = db_cfg.get("port", None)
        try:
            port = int(port_raw) if port_raw is not None and str(port_raw).strip() != "" else 0
        except Exception:
            port = 0
        if port <= 0:
            port = self._mssql_default_port(dt_type)

        if not host or not database or not user:
            return False, "config destination_database incompleta (host/database/user)"

        installed = [str(d) for d in (pyodbc.drivers() or [])]
        candidates: list[str] = []
        configured_driver = db_cfg.get("driver")
        if configured_driver is not None and str(configured_driver).strip():
            candidates.append(str(configured_driver).strip())
        else:
            def ver(d: str) -> int:
                m = re.search(r"ODBC Driver\s+(\d+)\s+for\s+SQL\s+Server", d, flags=re.IGNORECASE)
                return int(m.group(1)) if m else -1

            modern = sorted(
                [d for d in installed if re.search(r"ODBC Driver\s+\d+\s+for\s+SQL\s+Server", d, flags=re.IGNORECASE)],
                key=ver,
                reverse=True,
            )
            candidates.extend(modern or ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server"])

        if "\\" in host:
            server_variants = [host]
        else:
            server_variants = []
            if port:
                server_variants.append(f"tcp:{host},{port}")
                server_variants.append(f"{host},{port}")
            server_variants.append(f"tcp:{host}")
            server_variants.append(f"{host}")

        logger.info(
            "DB connect test: destination_database "
            f"dt_type={dt_type} host={host} port={port} database={database} servers={', '.join(server_variants)} "
            f"drivers={', '.join(candidates) if candidates else '(none)'}"
        )

        tried: list[str] = []
        last_error: Exception | None = None
        conn = None
        variants = [
            "Encrypt=no;TrustServerCertificate=yes;",
            "Encrypt=yes;TrustServerCertificate=yes;",
            "",
        ]
        for driver in candidates:
            if not driver or driver in tried:
                continue
            tried.append(driver)
            for server in server_variants:
                for extra in variants:
                    try:
                        conn = pyodbc.connect(
                            f"DRIVER={{{driver}}};"
                            f"SERVER={server};"
                            f"DATABASE={database};"
                            f"UID={user};"
                            f"PWD={password};"
                            "Connection Timeout=10;"
                            + extra,
                            autocommit=True,
                            timeout=5,
                        )
                        break
                    except Exception as e:
                        last_error = e
                        continue
                if conn is not None:
                    break
            if conn is not None:
                break

        if conn is None:
            installed_msg = ", ".join(installed) if installed else "(nessun driver ODBC trovato da pyodbc)"
            logger.error(
                f"DB connect test: errore destination_database dt_type={dt_type} host={host} port={port} database={database}: {type(last_error).__name__}: {last_error}"
            )
            return (
                False,
                "Connessione a SQL Server fallita. "
                f"Driver rilevati: {installed_msg}. "
                f"Server: {', '.join(server_variants)}. "
                f"Ultimo errore: {type(last_error).__name__}: {last_error}",
            )
        try:
            conn.close()
        except Exception:
            pass
        logger.info(f"DB connect test: ok destination_database dt_type={dt_type} host={host} port={port} database={database}")
        return True, ""

    def _test_database_connection_mysql_sync(self, db_cfg: dict) -> tuple[bool, str]:
        logger = logging.getLogger("cobrakai_OPCUA_Browser")
        try:
            import pymysql
        except Exception:
            pymysql = None

        try:
            import mysql.connector  # type: ignore
        except Exception:
            mysql = None
        else:
            mysql = mysql.connector

        dt_type = int(db_cfg.get("dt_type", 2) or 2)
        if dt_type not in (2, 3):
            return False, f"dt_type non supportato per MySQL/MariaDB: {dt_type} (supportati: 2 MariaDB, 3 MySql)"

        host = str(db_cfg.get("host", "") or "").strip()
        database = str(db_cfg.get("database", "") or "").strip()
        user = str(db_cfg.get("user", "") or "").strip()
        password = str(db_cfg.get("password", "") or "")

        port_raw = db_cfg.get("port", None)
        try:
            port = int(port_raw) if port_raw is not None and str(port_raw).strip() != "" else 0
        except Exception:
            port = 0
        if port <= 0:
            port = self._mssql_default_port(dt_type)

        if not host or not database or not user:
            return False, "config destination_database incompleta (host/database/user)"

        logger.info(f"DB connect test: destination_database dt_type={dt_type} host={host} port={port} database={database}")

        if pymysql is not None:
            try:
                conn = pymysql.connect(
                    host=host,
                    port=port,
                    user=user,
                    password=password,
                    database=database,
                    connect_timeout=10,
                    charset="utf8mb4",
                    autocommit=True,
                )
            except Exception as e:
                logger.error(
                    f"DB connect test: errore destination_database dt_type={dt_type} host={host} port={port} database={database}: {type(e).__name__}: {e}"
                )
                return False, f"connessione fallita: {type(e).__name__}: {e}"
            try:
                conn.close()
            except Exception:
                pass
            logger.info(f"DB connect test: ok destination_database dt_type={dt_type} host={host} port={port} database={database}")
            return True, ""

        if mysql is None:
            return False, "driver MariaDB/MySQL non trovato (installare pymysql o mysql-connector-python)"

        try:
            conn = mysql.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                connection_timeout=10,
                charset="utf8mb4",
                autocommit=True,
            )
        except Exception as e:
            logger.error(
                f"DB connect test: errore destination_database dt_type={dt_type} host={host} port={port} database={database}: {type(e).__name__}: {e}"
            )
            return False, f"connessione fallita: {type(e).__name__}: {e}"
        try:
            conn.close()
        except Exception:
            pass
        logger.info(f"DB connect test: ok destination_database dt_type={dt_type} host={host} port={port} database={database}")
        return True, ""

    def _test_database_connection_sync(self, db_cfg: dict) -> tuple[bool, str]:
        dt_type = int((db_cfg or {}).get("dt_type", 1) or 1)
        if dt_type == 1:
            return self._test_database_connection_mssql_sync(db_cfg)
        if dt_type in (2, 3):
            return self._test_database_connection_mysql_sync(db_cfg)
        return False, f"dt_type non supportato: {dt_type} (supportati: 1 MSSQL, 2 MariaDB, 3 MySql)"

    @work
    async def load_database(self, opcua_node, selected_name: str) -> None:
        details_panel = self.query_one("#details-panel", Static)
        logger = logging.getLogger("cobrakai_OPCUA_Browser")
        started_at = datetime.now().astimezone().isoformat(timespec="seconds")
        try:
            config_loader = ConfigLoader()
            client_cfg = config_loader.get_opcua_client_config()
            commessa = str(client_cfg.get("commessa", "") or "").strip()
            db_cfg = config_loader.get_destination_database_config()
        except Exception:
            commessa = ""
            db_cfg = {}

        full_json_path = self._make_export_output_path(commessa, selected_name)
        variabili_json_path = self._make_variabili_json_path(commessa, selected_name)
        table_name = self._make_table_name_from_variabili_json(variabili_json_path)
        table_name_vars = f"{table_name}_variables"
        dt_type = int((db_cfg or {}).get("dt_type", 1) or 1)

        details_panel.update(
            "[bold yellow]Caricamento Database in corso...[/bold yellow]\n\n"
            f"Inizio: {started_at}\n"
            f"File completo: {full_json_path}\n"
            f"File variabili: {variabili_json_path}\n"
            f"Tabelle: {table_name}, {table_name_vars}"
        )

        details_panel.update(
            "[bold yellow]Caricamento Database: verifica connessione...[/bold yellow]\n\n"
            f"Tabelle: {table_name}, {table_name_vars}"
        )
        ok_conn, conn_err = await self._db_run(self._db_ensure_connection_sync, db_cfg)
        if not ok_conn:
            logger.error(f"DB connect test: fallito tables={table_name},{table_name_vars}: {conn_err}")
            self.notify("Errore connessione DB", severity="error", timeout=10)
            details_panel.update(
                "[bold red]Caricamento Database: errore connessione[/bold red]\n\n"
                f"Tabelle: {table_name}, {table_name_vars}\n"
                f"{conn_err}"
            )
            return

        details_panel.update(
            "[bold yellow]Caricamento Database: creazione files nodi...[/bold yellow]\n\n"
            f"File completo: {full_json_path}\n"
            f"File variabili: {variabili_json_path}\n"
            "Creo/aggiorno i file come 'Estrai Nodi'..."
        )
        await asyncio.sleep(0)
        await self._export_variables_impl(opcua_node, selected_name)

        rows_full, err_full = await asyncio.to_thread(self._load_variabili_json_sync, full_json_path)
        if not rows_full:
            logger.error(f"DB load: annullato file={full_json_path} tables={table_name},{table_name_vars}: {err_full or 'nessuna riga'}")
            self.notify("Caricamento Database fallito", severity="error", timeout=10)
            details_panel.update(
                "[bold red]Caricamento Database: annullato[/bold red]\n\n"
                f"File sorgente (completo): {full_json_path}\n"
                f"{err_full or 'Nessuna riga trovata'}"
            )
            return

        vars_rows = [r for r in rows_full if self._is_variable_simple_type_row(r)]
        if not vars_rows:
            logger.error(f"DB load: annullato filtro _variables rows_full={len(rows_full)}")
            self.notify("Caricamento Database fallito (nessuna variabile semplice)", severity="error", timeout=10)
            details_panel.update(
                "[bold red]Caricamento Database: annullato[/bold red]\n\n"
                f"Nessuna variabile semplice (int/bool/float/str) trovata in {len(rows_full)} righe totali."
            )
            return

        logger.info(
            f"DB load: start dt_type={dt_type} file={os.path.basename(full_json_path)} tables={table_name},{table_name_vars} rows_full={len(rows_full)} rows_vars={len(vars_rows)}"
        )
        details_panel.update(
            "[bold yellow]Caricamento Database: connessione e scrittura...[/bold yellow]\n\n"
            f"File completo: {full_json_path}\n"
            f"File variabili: {variabili_json_path}\n"
            f"Righe complete: {len(rows_full)}\n"
            f"Righe _variables: {len(vars_rows)}\n"
            f"Tabelle: {table_name}, {table_name_vars}"
        )

        ok, db_err = await self._db_run(self._db_write_rows_sync, table_name, rows_full)
        if not ok:
            logger.error(f"DB load: errore table={table_name}: {db_err}")
            try:
                await self._close_db_connection_async()
            except Exception:
                pass
            self.notify("Errore Caricamento Database", severity="error", timeout=10)
            details_panel.update(
                "[bold red]Caricamento Database: errore[/bold red]\n\n"
                f"Tabella: {table_name}\n"
                f"{db_err}"
            )
            return

        ok_vars, db_err_vars = await self._db_run(self._db_write_rows_sync, table_name_vars, vars_rows)
        if not ok_vars:
            logger.error(f"DB load: errore table={table_name_vars}: {db_err_vars}")
            try:
                await self._close_db_connection_async()
            except Exception:
                pass
            self.notify("Errore Caricamento Database (tabella _variables)", severity="error", timeout=10)
            details_panel.update(
                "[bold red]Caricamento Database: errore _variables[/bold red]\n\n"
                f"Tabella: {table_name_vars}\n"
                f"{db_err_vars}"
            )
            return

        logger.info(f"Tabelle {table_name} rec. {len(rows_full)}; {table_name_vars} rec. {len(vars_rows)}")
        finished_at = datetime.now().astimezone().isoformat(timespec="seconds")
        details_panel.update(
            "[bold green]Caricamento Database completato[/bold green]\n\n"
            f"Inizio: {started_at}\n"
            f"Fine: {finished_at}\n"
            f"File completo: {full_json_path}\n"
            f"File variabili: {variabili_json_path}\n"
            f"Tabella completa: {table_name} ({len(rows_full)} righe)\n"
            f"Tabella filtrata: {table_name_vars} ({len(vars_rows)} righe)"
        )
        self.notify(
            f"Tabella {table_name} ({len(rows_full)}), {table_name_vars} ({len(vars_rows)})",
            severity="information",
            timeout=8,
        )

    @work
    async def test_database(self, opcua_node, selected_name: str) -> None:
        details_panel = self.query_one("#details-panel", Static)
        logger = logging.getLogger("cobrakai_OPCUA_Browser")
        started_at = datetime.now().astimezone().isoformat(timespec="seconds")
        try:
            config_loader = ConfigLoader()
            client_cfg = config_loader.get_opcua_client_config()
            commessa = str(client_cfg.get("commessa", "") or "").strip()
            db_cfg = config_loader.get_destination_database_config()
        except Exception:
            commessa = ""
            db_cfg = {}

        variabili_json_path = self._make_variabili_json_path(commessa, selected_name or "")
        table_name = self._make_table_name_from_variabili_json(variabili_json_path)
        dt_type = int((db_cfg or {}).get("dt_type", 1) or 1)

        details_panel.update(
            "[bold yellow]Test connessione DB...[/bold yellow]\n\n"
            f"Inizio: {started_at}\n"
            f"dt_type: {dt_type}\n"
            f"Tabella: {table_name}"
        )
        ok, err = await self._db_run(self._db_test_connection_only_sync, db_cfg)
        if not ok:
            logger.error(f"DB connect test: fallito table={table_name}: {err}")
            self.notify("Test connessione DB fallito", severity="error", timeout=10)
            details_panel.update(
                "[bold red]Test connessione DB: errore[/bold red]\n\n"
                f"dt_type: {dt_type}\n"
                f"Tabella: {table_name}\n"
                f"{err}"
            )
            return

        logger.info(f"DB connect test: ok dt_type={dt_type}")
        self.notify("Test connessione DB OK", severity="information", timeout=6)
        details_panel.update(
            "[bold green]Test connessione DB: OK[/bold green]\n\n"
            f"Inizio: {started_at}\n"
            f"dt_type: {dt_type}\n"
            f"Tabella: {table_name}"
        )

    def _load_node_ids_from_variabili_xlsx_sync(self, xlsx_path: str) -> tuple[list[str], str]:
        try:
            from openpyxl import load_workbook
        except Exception as e:
            return [], f"openpyxl non disponibile: {e}"

        if not os.path.exists(xlsx_path):
            return [], f"file non trovato: {xlsx_path}"

        try:
            wb = load_workbook(filename=xlsx_path, read_only=True, data_only=True)
        except Exception as e:
            return [], f"impossibile aprire xlsx: {type(e).__name__}: {e}"

        try:
            ws = wb.active
            header_row_idx = None
            nodeid_col_idx = None

            for r in range(1, min(ws.max_row, 50) + 1):
                for c in range(1, min(ws.max_column, 50) + 1):
                    v = ws.cell(row=r, column=c).value
                    if v is None:
                        continue
                    if str(v).strip().lower() == "nodeid":
                        header_row_idx = r
                        nodeid_col_idx = c
                        break
                if nodeid_col_idx is not None:
                    break

            if nodeid_col_idx is None:
                return [], "colonna 'NodeId' non trovata nel file"

            node_ids: list[str] = []
            seen = set()
            empty_streak = 0
            for (v,) in ws.iter_rows(
                min_row=(header_row_idx or 1) + 1,
                min_col=nodeid_col_idx,
                max_col=nodeid_col_idx,
                values_only=True,
            ):
                if v is None or str(v).strip() == "":
                    empty_streak += 1
                    if empty_streak >= 200:
                        break
                    continue
                empty_streak = 0
                s = str(v).strip()
                if s in seen:
                    continue
                seen.add(s)
                node_ids.append(s)

            return node_ids, ""
        finally:
            try:
                wb.close()
            except Exception:
                pass

    async def _load_node_ids_from_variabili_xlsx(self, xlsx_path: str) -> tuple[list[str], str]:
        return await asyncio.to_thread(self._load_node_ids_from_variabili_xlsx_sync, xlsx_path)

    async def _get_or_build_read_plan_from_variabili_xlsx(
        self, xlsx_path: str
    ) -> tuple[list[str], list[str], list, str]:
        if not os.path.exists(xlsx_path):
            self._read_plan_cache.pop(xlsx_path, None)
            return [], [], [], f"file non trovato: {xlsx_path}"

        try:
            mtime = os.path.getmtime(xlsx_path)
        except Exception:
            mtime = None

        client = getattr(self.explorer, "client", None)
        client_id = id(client)
        cached = self._read_plan_cache.get(xlsx_path)
        if (
            cached
            and cached.get("mtime") == mtime
            and cached.get("client_id") == client_id
            and cached.get("node_ids")
            and cached.get("headers")
            and cached.get("nodes")
        ):
            return cached["node_ids"], cached["headers"], cached["nodes"], ""

        node_ids, xlsx_err = await self._load_node_ids_from_variabili_xlsx(xlsx_path)
        if not node_ids:
            self._read_plan_cache.pop(xlsx_path, None)
            return [], [], [], xlsx_err or "nessun NodeId trovato"

        headers = [self._make_nome_variabile_from_node_id(nid) for nid in node_ids]
        headers = self._dedupe_headers(headers)
        nodes = [client.get_node(nid) for nid in node_ids]

        self._read_plan_cache[xlsx_path] = {
            "mtime": mtime,
            "client_id": client_id,
            "node_ids": node_ids,
            "headers": headers,
            "nodes": nodes,
        }
        return node_ids, headers, nodes, ""

    async def _read_values_batched(
        self,
        client,
        nodes: list,
        details_panel: Static,
        output_csv_path: str,
        read_idx: int,
        read_total: int | None,
        batch_size: int = 100,
        timeout_s: float = 60.0,
    ) -> tuple[list, bool, str, dict]:
        sem = asyncio.Semaphore(50)

        async def read_one(n):
            async with sem:
                try:
                    return await asyncio.wait_for(n.read_value(), timeout=timeout_s)
                except Exception:
                    return None

        all_values = []
        had_error = False
        first_error = ""
        total = len(nodes)
        read_total_label = "∞" if not read_total else str(read_total)
        one_shot_ok = 0
        one_shot_time = 0.0
        per_node_used = 0

        details_panel.update(
            "[bold yellow]Read OPC UA: lettura in corso...[/bold yellow]\n\n"
            f"Output: {output_csv_path}\n"
            f"Lettura: {read_idx + 1}/{read_total_label}\n"
            f"Modalità: richiesta unica ({total} variabili)"
        )
        await asyncio.sleep(0)

        try:
            t0 = time.perf_counter()
            all_values = await asyncio.wait_for(client.read_values(nodes), timeout=timeout_s)
            one_shot_time = round(time.perf_counter() - t0, 3)
            one_shot_ok = 1
            return all_values, False, "", {
                "read_mode": "one_shot",
                "one_shot_ok": one_shot_ok,
                "one_shot_time": one_shot_time,
                "error": "",
            }
        except Exception as e:
            one_shot_time = round(time.perf_counter() - t0, 3)
            one_shot_ok = 0
            had_error = True
            first_error = f"{type(e).__name__}: {e}"

        for start in range(0, total, batch_size):
            end = min(start + batch_size, total)
            details_panel.update(
                "[bold yellow]Read OPC UA: lettura in corso...[/bold yellow]\n\n"
                f"Output: {output_csv_path}\n"
                f"Lettura: {read_idx + 1}/{read_total_label}\n"
                f"Modalità: batch ({batch_size})\n"
                f"Batch: {start + 1}-{end}/{total}"
            )
            await asyncio.sleep(0)

            batch_nodes = nodes[start:end]
            try:
                batch_values = await asyncio.wait_for(client.read_values(batch_nodes), timeout=timeout_s)
            except Exception as e:
                had_error = True
                if first_error == "":
                    first_error = f"{type(e).__name__}: {e}"
                per_node_used = 1
                batch_values = await asyncio.gather(*[read_one(n) for n in batch_nodes])

            all_values.extend(batch_values)

        read_mode = "one_to_one" if per_node_used else "batch"
        return all_values, had_error, first_error, {
            "read_mode": read_mode,
            "one_shot_ok": one_shot_ok,
            "one_shot_time": one_shot_time,
            "error": first_error,
        }

    async def _collect_variable_node_ids_fast(
        self,
        root_node,
        details_panel: Static,
        started_at: str,
        start_perf: float,
        output_path: str,
        max_concurrent: int = 50,
        browse_batch_size: int = 100,
    ):
        client = self.explorer.client
        semaphore = asyncio.Semaphore(max_concurrent)

        root_node_id = ""
        try:
            root_node_id = root_node.nodeid.to_string()
        except Exception:
            root_node_id = str(getattr(root_node, "nodeid", ""))

        rows = []
        variables_seen = set()
        visited = set()
        queue = [(root_node_id, 0)]

        browse_errors = 0
        total_browsed = 0
        last_ui_update = time.perf_counter()

        try:
            root_class = await root_node.read_node_class()
        except Exception:
            root_class = None

        if root_class is not None and getattr(root_class, "name", "") == "Variable":
            try:
                bn = await root_node.read_browse_name()
                browse_name = getattr(bn, "Name", "") or str(bn)
            except Exception:
                browse_name = ""

            try:
                dn = await root_node.read_display_name()
                display_name = getattr(dn, "Text", "") or str(dn)
            except Exception:
                display_name = ""

            if root_node_id and root_node_id not in variables_seen:
                variables_seen.add(root_node_id)
                rows.append(
                    {
                        "level": 0,
                        "node_id": root_node_id,
                        "node_class": "Variable",
                        "browse_name": browse_name,
                        "display_name": display_name,
                    }
                )

        while queue:
            batch = queue[:browse_batch_size]
            queue = queue[browse_batch_size:]

            batch_new = []
            for node_id, level in batch:
                if not node_id or node_id in visited:
                    continue
                visited.add(node_id)
                batch_new.append((node_id, level))

            if not batch_new:
                continue

            results = await self._browse_batch(batch_new, semaphore)
            total_browsed += len(batch_new)

            for parent_id, parent_level, refs, ok, err in results:
                if not ok:
                    browse_errors += 1
                    if browse_errors <= 20:
                        logging.getLogger("cobrakai_OPCUA_Browser").warning(
                            f"Browse fallito su {parent_id}: {err}"
                        )

                for ref in refs:
                    try:
                        child_id = ref.NodeId.to_string()
                    except Exception:
                        child_id = ""

                    if not child_id:
                        continue

                    try:
                        node_class_name = ref.NodeClass.name
                    except Exception:
                        node_class_name = ""

                    if node_class_name == "Variable":
                        if child_id in variables_seen:
                            continue
                        variables_seen.add(child_id)
                        try:
                            browse_name = f"{ref.BrowseName.NamespaceIndex}:{ref.BrowseName.Name}"
                        except Exception:
                            browse_name = ""

                        try:
                            display_name = ref.DisplayName.Text
                        except Exception:
                            display_name = ""

                        rows.append(
                            {
                                "level": parent_level + 1,
                                "node_id": child_id,
                                "node_class": node_class_name,
                                "browse_name": browse_name,
                                "display_name": display_name,
                            }
                        )

                    if node_class_name in ("Object", "Variable"):
                        queue.append((child_id, parent_level + 1))

            now = time.perf_counter()
            if now - last_ui_update >= 0.5:
                elapsed = now - start_perf
                details_panel.update(
                    "[bold yellow]Read OPC UA: raccolta NodeId...[/bold yellow]\n\n"
                    f"Inizio: {started_at}\n"
                    f"Output: {output_path}\n\n"
                    f"Nodi visitati: {len(visited)}\n"
                    f"Nodi browsati: {total_browsed}\n"
                    f"Variabili trovate: {len(rows)}\n"
                    f"Elapsed: {elapsed:.1f}s"
                )
                last_ui_update = now

        stats = {
            "visited_nodes": len(visited),
            "browsed_nodes": total_browsed,
            "browse_errors": browse_errors,
        }
        return rows, stats

    def _write_excel_from_payload(self, payload: dict, output_xlsx_path: str) -> tuple[bool, str]:
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Alignment, Font, PatternFill
            from openpyxl.utils import get_column_letter
        except Exception as e:
            return False, f"openpyxl non disponibile: {e}"

        os.makedirs(os.path.dirname(output_xlsx_path) or os.getcwd(), exist_ok=True)
        if os.path.exists(output_xlsx_path):
            try:
                os.remove(output_xlsx_path)
            except Exception:
                pass

        wb = Workbook()
        ws = wb.active
        ws.title = "OPCUA"

        columns = ["level", "node_id", "nome_variabile", "nome_s7_protocol", "node_class", "browse_name", "display_name", "type", "value", "opcuasoglia"]
        headers = ["Liv", "NodeId", "NomeVariabile", "NomeS7protocolname", "NodeClass", "BrowseName", "DisplayName", "Tipo", "Valore", "opcuasoglia"]
        ws.append(headers)

        header_font = Font(bold=True, color="FFFFFFFF")
        header_fill = PatternFill("solid", fgColor="FF2F5597")
        header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for idx, _ in enumerate(headers, start=1):
            c = ws.cell(row=1, column=idx)
            c.font = header_font
            c.fill = header_fill
            c.alignment = header_alignment

        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"

        col_widths = [6, 42, 46, 16, 12, 28, 32, 14, 80, 14]
        for idx, w in enumerate(col_widths, start=1):
            ws.column_dimensions[get_column_letter(idx)].width = w

        rows = payload.get("rows", [])
        s7_col_idx = columns.index("nome_s7_protocol") + 1
        s7_max_len = len(headers[columns.index("nome_s7_protocol")])
        built_rows = []
        for r in rows:
            row_out = []
            for k in columns:
                if k == "node_class":
                    v = self._truncate_excel_cell(r.get(k, "Variable"))
                elif k == "nome_variabile":
                    v = self._truncate_excel_cell(
                        self._make_nome_variabile_from_node_id(r.get("node_id", ""))
                    )
                elif k == "nome_s7_protocol":
                    v = self._truncate_excel_cell(
                        self._make_s7_protocol_name_from_node_id(r.get("node_id", ""))
                    )
                    try:
                        l = len(str(v)) if v is not None else 0
                        if l > s7_max_len:
                            s7_max_len = l
                    except Exception:
                        pass
                elif k == "opcuasoglia":
                    t_raw = r.get("type", r.get("python_type", ""))
                    t_str = str(t_raw or "").strip().lower()
                    if t_str == "int":
                        v = "1"
                    elif t_str == "float":
                        v = "0.1"
                    else:
                        v = "0"
                    v = self._truncate_excel_cell(v)
                elif k == "type":
                    v = self._truncate_excel_cell(r.get("type", r.get("python_type", "")))
                else:
                    v = self._truncate_excel_cell(r.get(k, ""))
                row_out.append(v)
            built_rows.append(row_out)

        for row_out in built_rows:
            ws.append(row_out)

        if s7_max_len > 0:
            auto_w = float(s7_max_len) + 2.0
            if auto_w < 16:
                auto_w = 16
            ws.column_dimensions[get_column_letter(s7_col_idx)].width = auto_w

        body_alignment = Alignment(vertical="top", wrap_text=False)
        value_alignment = Alignment(vertical="top", wrap_text=True)
        last_col = len(headers)
        for row_idx in range(2, ws.max_row + 1):
            for col_idx in range(1, last_col + 1):
                c = ws.cell(row=row_idx, column=col_idx)
                c.alignment = value_alignment if col_idx == last_col else body_alignment

        try:
            wb.save(output_xlsx_path)
        except Exception as e:
            return False, str(e)
        return True, ""

    @work
    async def export_variables(self, opcua_node, selected_name: str) -> None:
        await self._export_variables_impl(opcua_node, selected_name)

    async def _export_variables_impl(self, opcua_node, selected_name: str) -> dict:
        try:
            config_loader = ConfigLoader()
            client_cfg = config_loader.get_opcua_client_config()
            commessa = str(client_cfg.get("commessa", "") or "").strip()
        except Exception:
            commessa = ""

        details_panel = self.query_one("#details-panel", Static)
        started_at = datetime.now().astimezone().isoformat(timespec="seconds")
        start_perf = time.perf_counter()
        output_path = self._make_export_output_path(commessa, selected_name)
        output_xlsx_path = os.path.splitext(output_path)[0] + ".xlsx"
        details_panel.update(
            "[bold yellow]Estrazione variabili in corso...[/bold yellow]\n\n"
            f"Inizio: {started_at}\n"
            f"Nodo: {opcua_node.nodeid}\n"
            f"Commessa: {commessa}\n"
            f"Output: {output_path}"
        )

        rows, stats = await self._collect_variables_fast(
            root_node=opcua_node,
            details_panel=details_panel,
            started_at=started_at,
            start_perf=start_perf,
            output_path=output_path,
            max_concurrent=50,
            browse_batch_size=100,
            read_batch_size=200,
        )

        finished_at = datetime.now().astimezone().isoformat(timespec="seconds")
        elapsed_seconds = time.perf_counter() - start_perf

        payload = {
            "meta": {
                "started_at": started_at,
                "finished_at": finished_at,
                "elapsed_seconds": round(elapsed_seconds, 6),
                "elapsed_ms": int(elapsed_seconds * 1000),
                "root_node_id": str(opcua_node.nodeid),
                "commessa": commessa,
                "variables": len(rows),
                "output_file": os.path.basename(output_path),
                "output_excel_file": os.path.basename(output_xlsx_path),
                **stats,
            },
            "columns": ["level", "node_id", "node_class", "browse_name", "display_name", "type", "value"],
            "rows": rows,
        }

        with open(output_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")

        excel_ok, excel_err = self._write_excel_from_payload(payload, output_xlsx_path)
        output_xlsx_vars_path = os.path.splitext(output_xlsx_path)[0] + "_Variabili.xlsx"
        vars_rows = [r for r in rows if self._is_variable_simple_type_row(r)]
        payload_vars = {"rows": vars_rows}
        excel_vars_ok, excel_vars_err = self._write_excel_from_payload(payload_vars, output_xlsx_vars_path)
        output_json_vars_path = os.path.splitext(output_xlsx_vars_path)[0] + ".json"
        payload_vars_json = {
            "meta": {
                "started_at": started_at,
                "finished_at": finished_at,
                "elapsed_seconds": round(elapsed_seconds, 6),
                "elapsed_ms": int(elapsed_seconds * 1000),
                "root_node_id": str(opcua_node.nodeid),
                "commessa": commessa,
                "variables": len(vars_rows),
                "filter": "simple_types(int,bool,float,str)",
                "output_file": os.path.basename(output_json_vars_path),
            },
            "columns": ["level", "node_id", "node_class", "browse_name", "display_name", "type", "value"],
            "rows": vars_rows,
        }
        with open(output_json_vars_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(payload_vars_json, f, ensure_ascii=False, indent=2)
            f.write("\n")
        payload["meta"]["variables_simple_types"] = len(vars_rows)
        payload["meta"]["output_excel_variables_file"] = os.path.basename(output_xlsx_vars_path)
        payload["meta"]["output_json_variables_file"] = os.path.basename(output_json_vars_path)

        details_panel.update(
            "[bold green]Estrazione completata[/bold green]\n\n"
            f"Inizio: {started_at}\n"
            f"Fine: {finished_at}\n"
            f"Elapsed: {elapsed_seconds:.3f}s\n\n"
            f"Variabili trovate: {len(rows)}\n"
            f"File: {output_path}\n"
            f"Excel: {output_xlsx_path if excel_ok else 'ERRORE'}\n"
            f"Excel Variabili: {output_xlsx_vars_path if excel_vars_ok else 'ERRORE'}\n"
            f"JSON Variabili: {output_json_vars_path}"
        )
        if excel_ok and excel_vars_ok:
            self.notify(f"Creati JSON+XLSX (+Variabili) ({elapsed_seconds:.3f}s)", severity="information", timeout=6)
        elif excel_ok and not excel_vars_ok:
            self.notify(f"JSON+XLSX ok, XLSX Variabili errore: {excel_vars_err}", severity="warning", timeout=8)
        else:
            self.notify(f"JSON ok, XLSX errore: {excel_err}", severity="warning", timeout=8)
        return {
            "commessa": commessa,
            "output_path": output_path,
            "output_xlsx_path": output_xlsx_path,
            "output_xlsx_vars_path": output_xlsx_vars_path,
            "output_json_vars_path": output_json_vars_path,
            "excel_ok": excel_ok,
            "excel_vars_ok": excel_vars_ok,
        }

    @work
    async def read_opcua(self, opcua_node, selected_name: str) -> None:
        if self._read_running:
            self.notify("Read OPC UA già in esecuzione", severity="warning", timeout=4)
            return
        self._read_running = True
        self._stop_after_current_read = False
        try:
            self._stop_read_event.clear()
        except Exception:
            pass
        logger = logging.getLogger("cobrakai_OPCUA_Browser")
        try:
            try:
                config_loader = ConfigLoader()
                client_cfg = config_loader.get_opcua_client_config()
                commessa = str(client_cfg.get("commessa", "") or "").strip()
                try:
                    read_interval_seconds = int(str(client_cfg.get("read_interval_seconds", 30)).strip() or "30")
                except ValueError:
                    read_interval_seconds = 30
                if read_interval_seconds < 1:
                    read_interval_seconds = 30
                try:
                    read_records = int(str(client_cfg.get("read_records", 0)).strip() or "0")
                except ValueError:
                    read_records = 0
                if read_records < 0:
                    read_records = 0
                run_mode = str(client_cfg.get("run_mode", "normal") or "normal").strip().lower()
                debug_subscription = run_mode == "debug"
                try:
                    subscription_publishing_interval_ms = int(
                        str(client_cfg.get("subscription_publishing_interval_ms", 3000)).strip() or "3000"
                    )
                except ValueError:
                    subscription_publishing_interval_ms = 3000
                if subscription_publishing_interval_ms < 0:
                    subscription_publishing_interval_ms = 3000
                try:
                    subscription_sampling_interval_ms = int(
                        str(client_cfg.get("subscription_sampling_interval_ms", 3000)).strip() or "3000"
                    )
                except ValueError:
                    subscription_sampling_interval_ms = 3000
                if subscription_sampling_interval_ms < 0:
                    subscription_sampling_interval_ms = 3000
                try:
                    deadband_global = float(str(client_cfg.get("deadband_global", 1.0)).strip() or "1.0")
                except ValueError:
                    deadband_global = 1.0
                if deadband_global < 0:
                    deadband_global = 1.0
            except Exception:
                commessa = ""
                read_interval_seconds = 30
                read_records = 0
                debug_subscription = False
                subscription_publishing_interval_ms = 3000
                subscription_sampling_interval_ms = 3000
                deadband_global = 1.0

            details_panel = self.query_one("#details-panel", Static)
            started_at = datetime.now().astimezone().isoformat(timespec="seconds")
            start_perf = time.perf_counter()

            base_path = os.path.splitext(self._make_export_output_path(commessa, selected_name))[0]
            output_csv_path = base_path + "_DATI.csv"
            input_xlsx_path = base_path + "_Variabili.xlsx"

            details_panel.update(
                "[bold yellow]Read OPC UA: preparazione...[/bold yellow]\n\n"
                f"Inizio: {started_at}\n"
                f"Nodo: {opcua_node.nodeid}\n"
                f"Commessa: {commessa}\n"
                f"Input: {input_xlsx_path}\n"
                f"Modalità: {'Debug' if debug_subscription else 'Normal Run'}\n"
                f"Publishing (ms): {subscription_publishing_interval_ms}\n"
                f"Sampling (ms): {subscription_sampling_interval_ms}\n"
                f"Deadband globale: {deadband_global}\n"
                f"Output: {output_csv_path}"
            )
            await asyncio.sleep(0)

            if os.path.exists(output_csv_path):
                try:
                    os.remove(output_csv_path)
                except PermissionError:
                    self.notify(
                        "File CSV bloccato: chiudi il file e riprova",
                        severity="warning",
                        timeout=8,
                    )
                    details_panel.update(
                        "[bold yellow]Read OPC UA: impossibile scrivere il CSV[/bold yellow]\n\n"
                        "Il file sembra aperto o bloccato da un altro programma.\n\n"
                        f"Chiudi il file e riprova:\n{output_csv_path}"
                    )
                    return
                except Exception:
                    pass

            if not os.path.exists(input_xlsx_path):
                details_panel.update(
                    "[bold yellow]Read OPC UA: file variabili non trovato[/bold yellow]\n\n"
                    f"Input: {input_xlsx_path}\n"
                    "Creo il file variabili con 'Estrai variabili'..."
                )
                await asyncio.sleep(0)
                await self._export_variables_impl(opcua_node, selected_name)

            if not os.path.exists(input_xlsx_path):
                self.notify("File variabili non creato", severity="error", timeout=10)
                details_panel.update(
                    "[bold red]Read OPC UA: annullato[/bold red]\n\n"
                    f"Non trovo il file variabili:\n{input_xlsx_path}"
                )
                return

            details_panel.update(
                "[bold yellow]Read OPC UA: caricamento lista variabili...[/bold yellow]\n\n"
                f"Inizio: {started_at}\n"
                f"Nodo: {opcua_node.nodeid}\n"
                f"Commessa: {commessa}\n"
                f"Input: {input_xlsx_path}\n"
                f"Modalità: {'Debug' if debug_subscription else 'Normal Run'}\n"
                f"Publishing (ms): {subscription_publishing_interval_ms}\n"
                f"Sampling (ms): {subscription_sampling_interval_ms}\n"
                f"Deadband globale: {deadband_global}\n"
                f"Output: {output_csv_path}"
            )
            await asyncio.sleep(0)
            node_ids, headers, nodes, xlsx_err = await self._get_or_build_read_plan_from_variabili_xlsx(
                input_xlsx_path
            )
            if not node_ids:
                self.notify("Nessuna variabile da leggere (file _Variabili.xlsx)", severity="warning", timeout=10)
                details_panel.update(
                    "[bold yellow]Read OPC UA: annullato[/bold yellow]\n\n"
                    f"Input: {input_xlsx_path}\n"
                    f"Errore: {xlsx_err or 'nessun NodeId trovato'}"
                )
                return

            details_panel.update(
                "[bold yellow]Read OPC UA: preparazione...[/bold yellow]\n\n"
                f"Inizio: {started_at}\n"
                f"Nodo: {opcua_node.nodeid}\n"
                f"Commessa: {commessa}\n"
                f"Input: {input_xlsx_path}\n"
                f"Variabili da leggere: {len(node_ids)}\n"
                f"Modalità: {'Debug' if debug_subscription else 'Normal Run'}\n"
                f"Publishing (ms): {subscription_publishing_interval_ms}\n"
                f"Sampling (ms): {subscription_sampling_interval_ms}\n"
                f"Deadband globale: {deadband_global}\n"
                f"Output: {output_csv_path}"
            )
            client = self.explorer.client

            try:
                f = open(output_csv_path, "w", encoding="utf-8", newline="")
            except PermissionError:
                self.notify(
                    "File CSV bloccato: chiudi il file e riprova",
                    severity="warning",
                    timeout=8,
                )
                details_panel.update(
                    "[bold yellow]Read OPC UA: impossibile scrivere il CSV[/bold yellow]\n\n"
                    "Il file sembra aperto o bloccato da un altro programma.\n\n"
                    f"Chiudi il file e riprova:\n{output_csv_path}"
                )
                return
            except Exception as e:
                self.notify("Errore apertura CSV", severity="error", timeout=8)
                details_panel.update(
                    "[bold red]Read OPC UA: errore[/bold red]\n\n"
                    f"File: {output_csv_path}\n"
                    f"Errore: {type(e).__name__}: {e}"
                )
                return

            with f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "started_at",
                        "finished_at",
                        "exec_time",
                        "read_mode",
                        "one_shot_ok",
                        "one_shot_time",
                        "error",
                        *headers,
                    ],
                    extrasaction="ignore",
                    dialect="excel",
                )
                writer.writeheader()

                # Costruisci parcheggio (data image) e subscription
                data_image: dict[str, dict] = {}
                try:
                    initial_values = await client.read_values(nodes)
                except Exception:
                    # Se la lettura iniziale fallisce, inizializza con None
                    initial_values = [None] * len(nodes)
                now_ts = time.time()
                for nid, val in zip(node_ids, initial_values):
                    data_image[nid] = {"value": val, "timestamp": now_ts}

                details_panel.update(
                    "[bold yellow]Read OPC UA: attivazione subscription...[/bold yellow]\n\n"
                    f"Variabili: {len(node_ids)}\n"
                    f"Modalità: {'Debug' if debug_subscription else 'Normal Run'}\n"
                    f"Output: {output_csv_path}"
                )
                await asyncio.sleep(0)

                outer_self = self
                sub_logger = logging.getLogger("cobrakai_OPCUA_Subscription")

                class _Handler:
                    async def datachange_notification(self_inner, node, val, data):
                        try:
                            nid = node.nodeid.to_string()
                        except Exception:
                            nid = str(node)
                        data_image[nid] = {"value": val, "timestamp": time.time()}
                        if debug_subscription:
                            ts = datetime.now().astimezone().isoformat(timespec="milliseconds")
                            name = outer_self._make_nome_variabile_from_node_id(nid)
                            sub_logger.info(f"SUB {ts} {name} = {val}")

                handler = _Handler()
                try:
                    subscription = await client.create_subscription(100, handler)
                    sub_handle = await subscription.subscribe_data_change(nodes)
                except Exception as e:
                    self.notify("Errore creazione subscription", severity="error", timeout=8)
                    details_panel.update(
                        "[bold red]Read OPC UA: errore subscription[/bold red]\n\n"
                        f"{type(e).__name__}: {e}"
                    )
                    return

                read_total = read_records if read_records > 0 else None
                read_idx = 0
                schedule_wall_start = None
                schedule_perf_start = None
                try:
                    while True:
                        if read_total is not None and read_idx >= read_total:
                            break
                        if schedule_wall_start is None:
                            schedule_wall_start = datetime.now().astimezone()
                            schedule_perf_start = time.perf_counter()
                        read_started = datetime.now().astimezone()
                        read_started_str = read_started.isoformat(timespec="seconds")
                        t0 = time.perf_counter()

                        # Snapshot dal parcheggio
                        snapshot = {nid: data_image.get(nid, {}).get("value") for nid in node_ids}

                        read_finished = datetime.now().astimezone()
                        read_finished_str = read_finished.isoformat(timespec="seconds")
                        elapsed_ms = int((time.perf_counter() - t0) * 1000)
                        exec_time = round(elapsed_ms / 1000.0, 3)

                        read_total_label = "∞" if read_total is None else str(read_total)
                        logger.info(
                            f"Read OPC UA {read_idx + 1}/{read_total_label} - snapshot exec_ms={elapsed_ms} mode=subscription vars={len(snapshot)}"
                        )

                        row = {
                            "started_at": read_started_str,
                            "finished_at": read_finished_str,
                            "exec_time": exec_time,
                            "read_mode": "subscription",
                            "one_shot_ok": 0,
                            "one_shot_time": 0.0,
                            "error": "",
                        }
                        for nid, name in zip(node_ids, headers):
                            val = snapshot.get(nid)
                            row[name] = "" if val is None else str(val)
                        writer.writerow(row)
                        f.flush()

                        details_panel.update(
                            "[bold yellow]Read OPC UA: lettura in corso...[/bold yellow]\n\n"
                            f"Output: {output_csv_path}\n"
                            f"Variabili: {len(headers)}\n"
                            f"Lettura: {read_idx + 1}/{'∞' if read_total is None else read_total}\n"
                            f"Ultima lettura: {read_started_str} → {read_finished_str} ({elapsed_ms} ms)"
                        )

                        read_idx += 1
                        if self._stop_after_current_read:
                            break
                        if read_total is None or read_idx < read_total:
                            try:
                                next_target_perf = (schedule_perf_start or time.perf_counter()) + (read_idx * read_interval_seconds)
                                remaining = next_target_perf - time.perf_counter()
                                if remaining > 0:
                                    await asyncio.wait_for(self._stop_read_event.wait(), timeout=remaining)
                                    break
                            except asyncio.TimeoutError:
                                pass
                finally:
                    try:
                        await subscription.unsubscribe(sub_handle)
                    except Exception:
                        pass
                    try:
                        await subscription.delete()
                    except Exception:
                        pass

            if read_total is not None:
                finished_at = datetime.now().astimezone().isoformat(timespec="seconds")
                details_panel.update(
                    "[bold green]Read OPC UA: completato[/bold green]\n\n"
                    f"Inizio: {started_at}\n"
                    f"Fine: {finished_at}\n"
                    f"Commessa: {commessa}\n"
                    f"Input: {input_xlsx_path}\n"
                    f"Variabili lette: {len(headers)}\n"
                    f"Output: {output_csv_path}"
                )
                await asyncio.sleep(0)
                self.notify("Read OPC UA completato (CSV creato)", severity="information", timeout=6)
            elif self._stop_after_current_read:
                finished_at = datetime.now().astimezone().isoformat(timespec="seconds")
                details_panel.update(
                    "[bold green]Read OPC UA: completato[/bold green]\n\n"
                    f"Inizio: {started_at}\n"
                    f"Fine: {finished_at}\n"
                    f"Commessa: {commessa}\n"
                    f"Input: {input_xlsx_path}\n"
                    f"Variabili lette: {len(headers)}\n"
                    f"Output: {output_csv_path}"
                )
                await asyncio.sleep(0)
                self.app.exit()
        finally:
            self._read_running = False

    async def _browse_batch(self, node_ids_with_level, semaphore):
        client = self.explorer.client

        async def browse_one(node_id: str, level: int):
            async with semaphore:
                try:
                    node = client.get_node(node_id)
                    refs = await node.get_children_descriptions()
                    return node_id, level, refs, True, ""
                except Exception as e:
                    return node_id, level, [], False, f"{type(e).__name__}: {e}"

        tasks = [browse_one(node_id, level) for node_id, level in node_ids_with_level]
        return await asyncio.gather(*tasks)

    async def _collect_variables_fast(
        self,
        root_node,
        details_panel: Static,
        started_at: str,
        start_perf: float,
        output_path: str,
        max_concurrent: int = 50,
        browse_batch_size: int = 100,
        read_batch_size: int = 200,
    ):
        client = self.explorer.client
        semaphore = asyncio.Semaphore(max_concurrent)

        root_node_id = ""
        try:
            root_node_id = root_node.nodeid.to_string()
        except Exception:
            root_node_id = str(getattr(root_node, "nodeid", ""))

        rows = []
        variables_seen = set()
        visited = set()
        queue = [(root_node_id, 0)]

        browse_errors = 0
        total_browsed = 0
        last_ui_update = time.perf_counter()

        try:
            root_class = await root_node.read_node_class()
        except Exception:
            root_class = None

        if root_class is not None and getattr(root_class, "name", "") == "Variable":
            try:
                bn = await root_node.read_browse_name()
                browse_name = getattr(bn, "Name", "") or str(bn)
            except Exception:
                browse_name = ""

            try:
                dn = await root_node.read_display_name()
                display_name = getattr(dn, "Text", "") or str(dn)
            except Exception:
                display_name = ""

            if root_node_id and root_node_id not in variables_seen:
                variables_seen.add(root_node_id)
                rows.append(
                    {
                        "level": 0,
                        "node_id": root_node_id,
                        "node_class": "Variable",
                        "browse_name": browse_name,
                        "display_name": display_name,
                        "type": "",
                        "value": "",
                    }
                )

        while queue:
            batch = queue[:browse_batch_size]
            queue = queue[browse_batch_size:]

            batch_new = []
            for node_id, level in batch:
                if not node_id or node_id in visited:
                    continue
                visited.add(node_id)
                batch_new.append((node_id, level))

            if not batch_new:
                continue

            results = await self._browse_batch(batch_new, semaphore)
            total_browsed += len(batch_new)

            for parent_id, parent_level, refs, ok, err in results:
                if not ok:
                    browse_errors += 1
                    if browse_errors <= 20:
                        logging.getLogger("cobrakai_OPCUA_Browser").warning(
                            f"Browse fallito su {parent_id}: {err}"
                        )

                for ref in refs:
                    try:
                        child_id = ref.NodeId.to_string()
                    except Exception:
                        child_id = ""

                    if not child_id:
                        continue

                    try:
                        node_class_name = ref.NodeClass.name
                    except Exception:
                        node_class_name = ""

                    if node_class_name == "Variable":
                        if child_id in variables_seen:
                            continue
                        variables_seen.add(child_id)
                        try:
                            browse_name = f"{ref.BrowseName.NamespaceIndex}:{ref.BrowseName.Name}"
                        except Exception:
                            browse_name = ""

                        try:
                            display_name = ref.DisplayName.Text
                        except Exception:
                            display_name = ""

                        rows.append(
                            {
                                "level": parent_level + 1,
                                "node_id": child_id,
                                "node_class": node_class_name,
                                "browse_name": browse_name,
                                "display_name": display_name,
                                "type": "",
                                "value": "",
                            }
                        )

                    if node_class_name in ("Object", "Variable"):
                        queue.append((child_id, parent_level + 1))

            now = time.perf_counter()
            if now - last_ui_update >= 0.5:
                elapsed = now - start_perf
                details_panel.update(
                    "[bold yellow]Estrazione variabili in corso...[/bold yellow]\n\n"
                    f"Inizio: {started_at}\n"
                    f"Output: {output_path}\n\n"
                    f"Nodi visitati: {len(visited)}\n"
                    f"Nodi browsati: {total_browsed}\n"
                    f"Variabili trovate: {len(rows)}\n"
                    f"Elapsed: {elapsed:.1f}s"
                )
                last_ui_update = now

        variables = [r for r in rows if r.get("type", "") == "" and r.get("value", "") == ""]

        for i in range(0, len(variables), read_batch_size):
            batch_vars = variables[i : i + read_batch_size]
            batch_nodes = [client.get_node(v["node_id"]) for v in batch_vars]

            try:
                values = await client.read_values(batch_nodes)
                for var, val in zip(batch_vars, values):
                    var["value"] = str(val)
                    var["type"] = type(val).__name__
            except Exception:
                for var in batch_vars:
                    try:
                        node = client.get_node(var["node_id"])
                        val = await node.read_value()
                        var["value"] = str(val)
                        var["type"] = type(val).__name__
                    except Exception:
                        var["value"] = ""
                        var["type"] = ""

            now = time.perf_counter()
            if now - last_ui_update >= 0.5:
                elapsed = now - start_perf
                details_panel.update(
                    "[bold yellow]Estrazione variabili in corso...[/bold yellow]\n\n"
                    f"Inizio: {started_at}\n"
                    f"Output: {output_path}\n\n"
                    f"Nodi visitati: {len(visited)}\n"
                    f"Nodi browsati: {total_browsed}\n"
                    f"Variabili trovate: {len(rows)}\n"
                    f"Valori letti: {min(i + read_batch_size, len(variables))}/{len(variables)}\n"
                    f"Elapsed: {elapsed:.1f}s"
                )
                last_ui_update = now

        stats = {
            "visited_nodes": len(visited),
            "browsed_nodes": total_browsed,
            "browse_errors": browse_errors,
        }
        return rows, stats

    async def _collect_variables_recursive(self, node, rows, visited, level: int) -> None:
        try:
            node_id = node.nodeid.to_string()
        except Exception:
            node_id = str(getattr(node, "nodeid", ""))

        if node_id and node_id in visited:
            return
        if node_id:
            visited.add(node_id)

        try:
            node_class = await node.read_node_class()
        except Exception:
            node_class = None

        is_variable = False
        if node_class is not None:
            try:
                is_variable = node_class.name == "Variable"
            except Exception:
                is_variable = False

        if is_variable:
            browse_name = ""
            display_name = ""
            try:
                bn = await node.read_browse_name()
                browse_name = getattr(bn, "Name", "") or str(bn)
            except Exception:
                browse_name = ""

            try:
                dn = await node.read_display_name()
                display_name = getattr(dn, "Text", "") or str(dn)
            except Exception:
                display_name = ""

            value_str = ""
            value_type = ""
            try:
                value = await node.read_value()
                value_str = str(value)
                value_type = type(value).__name__
            except Exception:
                value_str = ""
                value_type = ""

            rows.append(
                {
                    "level": level,
                    "node_id": node_id,
                    "node_class": "Variable",
                    "browse_name": browse_name,
                    "display_name": display_name,
                    "type": value_type,
                    "value": value_str,
                }
            )

        try:
            children = await node.get_children()
        except Exception:
            children = []

        for child in children:
            await self._collect_variables_recursive(
                child,
                rows=rows,
                visited=visited,
                level=level + 1,
            )

    def _render_table(self, rows) -> str:
        headers = ["Liv", "NodeId", "BrowseName", "DisplayName", "Tipo", "Valore"]
        max_value_len = 200

        def trim(s: str) -> str:
            if s is None:
                return ""
            s = str(s)
            if len(s) > max_value_len:
                return s[: max_value_len - 1] + "…"
            return s

        data = []
        for r in rows:
            data.append(
                [
                    str(r.get("level", "")),
                    trim(r.get("node_id", "")),
                    trim(r.get("browse_name", "")),
                    trim(r.get("display_name", "")),
                    trim(r.get("type", "")),
                    trim(r.get("value", "")),
                ]
            )

        widths = [len(h) for h in headers]
        for row in data:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], len(cell))

        def fmt_row(row):
            return "| " + " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)) + " |"

        sep = "|-" + "-|-".join("-" * w for w in widths) + "-|"
        out_lines = [fmt_row(headers), sep]
        out_lines.extend(fmt_row(row) for row in data)
        return "\n".join(out_lines)

    async def on_unmount(self) -> None:
        if self.log_handler:
            try:
                logging.getLogger().removeHandler(self.log_handler)
            except Exception:
                pass
            try:
                logging.getLogger("asyncua").removeHandler(self.log_handler)
            except Exception:
                pass

        try:
            if getattr(self, "explorer", None) and getattr(self.explorer, "connected", False):
                await self.explorer.disconnect()
        except Exception:
            pass

class MainMenu(Screen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Container(
            Label("CobrakAi OPC UA Client", id="main-title"),
            ListView(
                ListItem(Label("🛠️  Configurazione"), id="opt-config"),
                ListItem(Label("🌐 Browser OPC UA"), id="opt-browser"),
                ListItem(Label("� Read OPC UA"), id="opt-read"),
                ListItem(Label("�� Esci"), id="opt-exit"),
            ),
            id="menu-container"
        )
        yield Footer()

    @on(ListView.Selected)
    def on_list_view_selected(self, event: ListView.Selected):
        if event.item.id == "opt-config":
            self.app.push_screen(ConfigScreen())
        elif event.item.id == "opt-browser":
            self.start_browser()
        elif event.item.id == "opt-read":
            self.start_browser(read_mode=True)
        elif event.item.id == "opt-exit":
            self.app.exit()

    def start_browser(self, read_mode: bool = False):
        config_loader = ConfigLoader()
        client_config = config_loader.get_opcua_client_config()
        url = client_config.get('url')
        anonymous = client_config.get('anonymous', False)
        username = client_config.get('username')
        password = client_config.get('password')
        security_mode = client_config.get('security_mode', 'None')
        security_policy = client_config.get('security_policy', 'None')
        
        if not url:
            self.notify("URL non configurato!", severity="error")
            return

        explorer = OPCUAExplorer(
            url, 
            anonymous=anonymous, 
            username=username, 
            password=password,
            security_mode=security_mode,
            security_policy=security_policy
        )
        self.app.push_screen(BrowserScreen(explorer, read_mode=read_mode))

class OPCUAClientApp(App):
    CSS = """
    #main-title {
        text-align: center;
        text-style: bold;
        color: green;
        margin: 2;
    }
    #menu-container {
        align: center middle;
    }
    ListView {
        width: 50%;
        height: auto;
        border: solid green;
    }
    .title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    .config-container {
        align: center middle;
        width: 60%;
        height: auto;
        border: solid magenta;
        padding: 2;
    }
    Input {
        margin-bottom: 1;
    }
    #security_title {
        color: yellow;
        text-style: bold;
        margin-top: 1;
    }
    #security-container {
        height: auto;
        border: solid yellow;
        padding: 1;
        margin-bottom: 1;
    }
    #run_mode_box {
        border: solid yellow;
        padding: 0 1;
        height: auto;
        margin-bottom: 1;
    }
    .security-col {
        width: 50%;
        height: auto;
    }
    RadioSet {
        border: none;
        height: auto;
    }
    RadioButton {
        height: 1;
    }
    .checkbox-label {
        margin-left: 1;
        color: yellow;
    }
    .spacer {
        height: 1;
    }
    """
    
    BINDINGS = [("q", "quit", "Esci")]

    def action_quit(self) -> None:
        screen = getattr(self, "screen", None)
        if screen is not None and hasattr(screen, "request_graceful_quit"):
            try:
                if screen.request_graceful_quit():
                    return
            except Exception:
                pass
        self.exit()

    def on_mount(self) -> None:
        self.push_screen(MainMenu())

if __name__ == "__main__":
    # Logger dedicato per i messaggi di lifecycle
    lifecycle_logger = logging.getLogger("cobrakai_OPCUA_Browser")
    lifecycle_logger.info("--> OPCUA Browser - START  <--")
    
    app = OPCUAClientApp()
    app.run()
    
    lifecycle_logger.info("--> OPCUA Browser - STOP  <--")
