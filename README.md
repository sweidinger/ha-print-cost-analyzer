# 3D Print Cost Analyzer

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![HACS](https://img.shields.io/badge/HACS-Default-blue.svg)](https://hacs.xyz/)
[![HomeAssistant](https://img.shields.io/badge/HomeAssistant-2024.1+-green.svg)](https://www.home-assistant.io/)

Eine umfassende HomeAssistant Integration zur Kostenauswertung von 3D-Drucken mit Spoolman, Shelly Plugs und InfluxDB.

## ✨ Features

- 🧵 **Materialkosten**: Automatische Auslesung aus Spoolman (`price_per_kg`)
- ⚡ **Energiekosten**: Entity-basierte Überwachung von Shelly Plugs
- 📊 **Historische Daten**: Speicherung in InfluxDB v2
- 🖨️ **Multi-Drucker Support**: Unterstützung für mehrere 3D-Drucker
- 🎯 **AMS-Unit Kompatibilität**: Filament-Tracking mit AMS-Slots
- 💰 **Dynamische Strompreise**: Fix oder Entity-basiert
- 🏠 **HACS-Integration**: Einfache Installation und Updates

## 🚀 Installation

### Über HACS (Empfohlen)

1. Öffnen Sie HomeAssistant → **HACS** → **Integrationen**
2. Klicken Sie auf **"Durchsuchen & herunterladen"**
3. Suchen Sie nach **"3D Print Cost Analyzer"**
4. Klicken Sie auf **"Herunterladen"** und starten Sie HomeAssistant neu

### Manuell

1. Laden Sie das Repository herunter:
   ```bash
   git clone https://github.com/your-username/ha-print-cost-analyzer.git
   ```
2. Kopieren Sie den Ordner nach `/config/custom_components/print_cost_analyzer/`
3. Starten Sie HomeAssistant neu

## ⚙️ Konfiguration

### 1. Spoolman & InfluxDB
- Spoolman URL und Token
- InfluxDB v2 Verbindungsdetails

### 2. Energiekosten
- **Fixer Preis**: z.B. 0.30€/kWh
- **Entity**: Dynamische Preis-Entity (z.B. `sensor.strompreis`)

### 3. Entity-Auswahl
- **Shelly Power Entities**: z.B. `sensor.shelly_plug_power`
- **Shelly Energy Entities**: z.B. `sensor.shelly_plug_energy`
- **AMS Entities**: z.B. `sensor.ams_slot1_filament`

## 📊 Sensoren

Die Integration erstellt automatisch folgende Sensoren:

| Sensor | Beschreibung |
|--------|-------------|
| `sensor.total_print_cost` | Gesamtkosten aller Drucke |
| `sensor.active_spools` | Aktive Spools (aus Spoolman) |
| `sensor.total_prints` | Gesamtzahl der Drucke |
| `sensor.energy_cost_per_kwh` | Aktueller Strompreis |
| `sensor.shelly_[entity]_power` | Shelly Leistungsaufnahme |
| `sensor.shelly_[entity]_energy` | Shelly Energieverbrauch |
| `sensor.ams_[entity]` | AMS-Status & Filament |

## 🎨 Dashboard

Beispiel-Lovelace-Dashboard ist enthalten:

```yaml
type: entities
title: 3D Druck Kostenübersicht
entities:
  - sensor.total_print_cost
  - sensor.active_spools
  - sensor.energy_cost_per_kwh
  - sensor.shelly_ender3_power
  - sensor.ams_slot1_filament
```

## 🔧 Services

### Manuelle Druckaufnahme
```yaml
service: print_cost_analyzer.add_print_job
data:
  printer: "Ender3"
  duration: 3600
  material_used: 25.5
  spool_id: "123"
  energy_consumed: 0.15
```

## 📈 Datenstruktur

### InfluxDB Schema
```
Measurement: print_job
Tags:
  - printer: Druckername
  - spool_id: Spool-ID
Fields:
  - duration: Druckdauer (Sekunden)
  - material_used: Materialverbrauch (Gramm)
  - energy_consumed: Energieverbrauch (kWh)
```

## 🐛 Fehlerbehebung

### Häufige Probleme

1. **Spoolman-Verbindung fehlgeschlagen**
   - URL und Token überprüfen
   - Spoolman-Status prüfen

2. **Shelly Entities nicht gefunden**
   - Entity-IDs in HomeAssistant überprüfen
   - Shelly-Konfiguration prüfen

3. **InfluxDB-Fehler**
   - Verbindungsdaten überprüfen
   - Bucket-Berechtigungen prüfen

## 🤝 Beiträge

Beiträge sind willkommen! Bitte:

1. Forken Sie das Repository
2. Erstellen Sie einen Feature-Branch (`git checkout -b feature/amazing-feature`)
3. Committen Sie Ihre Änderungen (`git commit -m 'Add amazing feature'`)
4. Pushen Sie zum Branch (`git push origin feature/amazing-feature`)
5. Erstellen Sie einen Pull Request

## 📄 Lizenz

Dieses Projekt ist unter der MIT-Lizenz lizenziert - siehe [LICENSE](LICENSE) Datei für Details.

## 🙏 Danksagungen

- [HomeAssistant](https://www.home-assistant.io/) für die hervorragende Plattform
- [Spoolman](https://github.com/Donkie/spoolman) für das Filament-Management
- [Shelly](https://www.shelly.cloud/) für die Smart-Steckdosen
- [InfluxDB](https://www.influxdata.com/) für die Zeitreihen-Datenbank

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/your-username/ha-print-cost-analyzer/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-username/ha-print-cost-analyzer/discussions)
- **HomeAssistant Community**: [Forum Thread](https://community.home-assistant.io/)

---

⭐ Wenn Ihnen diese Integration gefällt, geben Sie ihr einen Star auf GitHub!