import os

import yaml


class ConfigLoader:
    def __init__(self, config_file="config.yaml"):
        """
        Inizializza il ConfigLoader.
        
        :param config_file: Nome del file di configurazione (default: config.yaml)
        """
        # Ottieni il percorso assoluto della directory corrente dove si trova questo script
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_path = os.path.join(current_dir, config_file)
        self._config = self._load_config()

    def _load_config(self):
        """
        Carica il file YAML.
        """
        if not os.path.exists(self.config_path):
            default_config = {
                "opcua": {
                    "server": {
                        "ip": "",
                        "port": 4840,
                    },
                    "client": {
                        "url": "",
                        "anonymous": True,
                        "username": "",
                        "password": "",
                        "security_mode": "None",
                        "security_policy": "None",
                        "commessa": "",
                        "read_interval_seconds": 30,
                        "read_records": 0,
                        "run_mode": "normal",
                        "subscription_publishing_interval_ms": 3000,
                        "subscription_sampling_interval_ms": 3000,
                        "deadband_global": 1.0,
                    },
                },
                "destination_database": {
                    "dt_type": 1,
                    "host": "",
                    "port": 0,
                    "database": "",
                    "user": "",
                    "password": "",
                },
            }
            try:
                with open(self.config_path, "w") as file:
                    yaml.dump(default_config, file, default_flow_style=False)
            except Exception:
                pass
            return default_config

        with open(self.config_path) as file:
            try:
                return yaml.safe_load(file)
            except yaml.YAMLError as exc:
                print(f"Errore nel parsing del file YAML: {exc}")
                return {}

    def save_config(self, config_data):
        """
        Salva la configurazione nel file YAML.
        
        :param config_data: Dizionario con la nuova configurazione
        """
        try:
            with open(self.config_path, 'w') as file:
                yaml.dump(config_data, file, default_flow_style=False)
            self._config = config_data
            return True
        except Exception as e:
            print(f"Errore durante il salvataggio della configurazione: {e}")
            return False

    def get_config(self):
        """
        Restituisce l'intera configurazione come dizionario.
        """
        return self._config

    def get_opcua_server_config(self):
        """
        Restituisce la configurazione specifica del server OPC UA.
        """
        return self._config.get('opcua', {}).get('server', {})

    def get_opcua_client_config(self):
        """
        Restituisce la configurazione specifica del client OPC UA.
        """
        return self._config.get('opcua', {}).get('client', {})

    def get_destination_database_config(self):
        return self._config.get("destination_database", {}) or {}

# Esempio di utilizzo (se eseguito come script principale)
if __name__ == "__main__":
    config = ConfigLoader()
    print("Configurazione completa:", config.get_config())
    print("IP Server OPC UA:", config.get_opcua_server_config().get('ip'))
