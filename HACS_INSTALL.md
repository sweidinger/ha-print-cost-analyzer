# HACS Installation Guide

## Installation über HACS

1. Öffnen Sie HomeAssistant
2. Gehen Sie zu **HACS** → **Integrations**
3. Klicken Sie auf **"Durchsuchen & herunterladen"**
4. Suchen Sie nach **"3D Print Cost Analyzer"**
5. Klicken Sie auf **"Herunterladen"**
6. Starten Sie HomeAssistant neu

## Manuelle Installation

1. Laden Sie die neueste Version von GitHub herunter
2. Entpacken Sie die Datei in `/config/custom_components/print_cost_analyzer/`
3. Starten Sie HomeAssistant neu

## Nach der Installation

1. Gehen Sie zu **Einstellungen** → **Integrationen**
2. Klicken Sie auf **"+ Integration hinzufügen"**
3. Suchen Sie nach **"3D Print Cost Analyzer"**
4. Folgen Sie dem Konfigurationsassistenten

## Konfiguration

### Spoolman
- URL: `http://localhost:8000` (oder Ihre Spoolman-Instanz)
- Token: Optional, falls Ihre Spoolman-Instanz Authentifizierung erfordert

### Shelly Plugs
Fügen Sie für jeden Shelly Plug folgende Informationen hinzu:
- Plug ID: IP-Adresse (z.B. `192.168.1.100`)
- Name: Beschreibender Name (z.B. `Ender3 Plug`)
- Printer: Zugeordneter Drucker (z.B. `Ender3`)

### InfluxDB v2
- URL: `http://localhost:8086` (oder Ihre InfluxDB-Instanz)
- Token: Ihr InfluxDB API-Token
- Organisation: Name Ihrer Organisation
- Bucket: Name des Buckets für Druckdaten (z.B. `print_jobs`)

### Energiekosten
- Cost per kWh: Ihre Stromkosten pro kWh (Standard: 0.30€)

## Beispielkonfiguration

```yaml
# configuration.yaml
print_cost_analyzer:
  spoolman:
    url: "http://localhost:8000"
    token: "your-spoolman-token"
  
  shelly_plugs:
    - id: "192.168.1.100"
      name: "Ender3 Plug"
      printer: "Ender3"
    - id: "192.168.1.101"
      name: "Prusa Plug"
      printer: "Prusa"
  
  influxdb:
    url: "http://localhost:8086"
    token: "your-influxdb-token"
    org: "homeassistant"
    bucket: "print_jobs"
  
  energy_cost_per_kwh: 0.30
```

## Fehlersuche

### Häufige Probleme

1. **Integration wird nicht gefunden**
   - Stellen Sie sicher, dass die Dateien im richtigen Verzeichnis liegen
   - Starten Sie HomeAssistant neu

2. **Spoolman-Verbindung fehlgeschlagen**
   - Überprüfen Sie die Spoolman-URL
   - Stellen Sie sicher, dass Spoolman läuft

3. **Shelly Plug nicht erreichbar**
   - Überprüfen Sie die IP-Adresse
   - Stellen Sie sicher, dass der Plug im gleichen Netzwerk ist

4. **InfluxDB-Fehler**
   - Überprüfen Sie die Anmeldedaten
   - Stellen Sie sicher, dass der Bucket existiert

## Support

Für Support und Fragen:
- GitHub Issues: https://github.com/your-username/ha-print-cost-analyzer/issues
- HomeAssistant Community: https://community.home-assistant.io/