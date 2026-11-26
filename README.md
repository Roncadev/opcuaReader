# opcuaReader

Client OPC UA per la lettura e il salvataggio di variabili da PLC su database (MSSQL, MariaDB, MySQL, PostgreSQL). Include una TUI interattiva (Textual) per esplorare i nodi OPC UA e un tool da riga di comando per la gestione della sicurezza dei certificati.

## Componenti principali

| File | Descrizione |
|------|-------------|
| `opcuaVariablesReader.py` | Applicazione TUI principale — esplora nodi, sottoscrizioni, lettura ciclica e scrittura su DB |
| `opcua_tool.py` | Tool CLI per gestione certificati e test connessione OPC UA |
| `app/utils/opcua_security.py` | Utility per certificati X.509 e sessioni sicure |
| `app/utils/opcua_utils.py` | Explorer asincrono per nodi OPC UA |
| `config/config.py` | Loader configurazione YAML |

## Requisiti

```bash
pip install -r requirements.txt
```

Dipendenze principali: `asyncua`, `textual`, `rich`, `pyyaml`, `pymysql`, `pyodbc`, `mysql-connector-python`, `cryptography`, `openpyxl`.

## Configurazione

Copia `config/config.yaml.example` in `config/config.yaml` e adattalo:

```yaml
destination_database:
  dt_type: 1        # 1=MSSQL, 2=MariaDB, 3=MySQL, 4=PostgreSQL
  host: 127.0.0.1
  port: 1433
  database: nome_db
  user: utente
  password: password

opcua:
  client:
    url: opc.tcp://10.0.0.1:4840/
    anonymous: false
    username: Admin
    password: secret
    security_mode: "Sign & Encrypt"   # None | Sign | Sign & Encrypt
    security_policy: Basic256SHA256   # None | Basic256 | Basic256Sha256 | ...
    read_interval_seconds: 15
    commessa: NOME_PROGETTO
```

> `config/config.yaml` è escluso da git. Non committare mai file con credenziali reali.

## Avvio TUI

```bash
python opcuaVariablesReader.py
```

## opcua_tool — gestione certificati

```bash
# Visualizza gli endpoint offerti dal PLC (sola lettura)
python opcua_tool.py --endpoints

# Genera un nuovo certificato client (validità 20 anni)
python opcua_tool.py --new-cert

# Scarica e trust il certificato del server (pinning)
python opcua_tool.py --save-server-cert

# Test login con le impostazioni di sicurezza in config.yaml
python opcua_tool.py --test

# Specifica un URL diverso da quello in config.yaml
python opcua_tool.py --endpoints --url opc.tcp://192.168.1.10:4840/
```

`--endpoints` e `--test` non modificano il PLC né il client in esecuzione. `--new-cert` conserva i file precedenti come `*.old_<timestamp>`.

## Struttura directory

```
opcuaReader/
├── app/
│   └── utils/
│       ├── opcua_security.py
│       └── opcua_utils.py
├── config/
│   ├── config.py
│   └── config.yaml.example
├── logs/                      # log rotanti (esclusi da git)
├── opcuaNodes/                # export nodi (escluso da git)
├── pki/                       # certificati (escluso da git)
├── opcuaVariablesReader.py
├── opcua_tool.py
└── requirements.txt
```
