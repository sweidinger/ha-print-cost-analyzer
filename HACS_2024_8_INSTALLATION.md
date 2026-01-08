# 🔧 Home Assistant 2024.8+ HACS Installation Guide

## ❌ Problem: "The version cannot be used with HACS"

Dieses Problem tritt auf, wenn Home Assistant versucht, eine Custom Component zu laden, die eine **Mindestversion** für Home Assistant 2024.8 oder neuer benötigt.

## ✅ Lösung: Version 2024.8.1

Die Integration **v2024.8.1** ist jetzt veröffentlicht und kompatibel mit Home Assistant 2024.8+!

## 🚀 Installation mit v2024.8.1

### Schritt 1: Repository neu laden
```bash
# Lade die neueste Version herunter
cd /tmp
git clone https://github.com/sweidinger/ha-print-cost-analyzer.git
```

### Schritt 2: Kopieren
```bash
# Kopiere die Integration in dein HomeAssistant Config
cp -r ha-print-cost-analyzer/custom_components/print_cost_analyzer/ /config/custom_components/
```

### Schritt 3: Home Assistant **wichtig neustarten**
```bash
# Methode 1: Über Developer Tools
# Home Assistant → Developer → Restart

# Methode 2: Kommandozeile (Docker)
docker restart homeassistant

# Methode 3: Kommandozeile (SystemD)
sudo systemctl restart home-assistant
```

### Schritt 4: Installation
1. HACS → Integrationen → Custom Repositories
2. "3D Print Cost Analyzer" suchen und installieren
3. Nach Installation: Home Assistant neustarten

## 📋 Version-Check

Nach der Installation kannst du die Version überprüfen:
1. Einstellungen → Integrationen → "3D Print Cost Analyzer"
2. Version sollte **2024.8.1** anzeigen

## 🔧 Troubleshooting

### Falls Probleme auftreten:

1. **Cache löschen:**
   ```bash
   rm -rf /config/.storage/core.config_entries
   rm -rf /config/custom_components/.cache
   ```

2. **Cache neu laden:**
   ```bash
   # Browser-Cache leeren
   STRG+F5 oder CMD+SHIFT+R
   ```

3. **Entwickler-Logs prüfen:**
   - Einstellungen → System → Logs
   - Nach Fehlern wie `Failed to load integration`

## 🎯 Was wurde verbessert?

### ✅ Version-Kompatibilität
- **homeassistant: ">=2024.8.0"** in Requirements
- **Manifest-Version**: "2024.8.1" für HA-Kompatibilität
- **Kein Versions-Check**: Entfernt, der HACS-Fehler verursacht hat

### ✅ Stabile Installation
- **Keine manuellen Versionen** mehr
- **Automatische Updates** über HACS möglich
- **Kompatibel mit HA 2024.8+**

---

**URL**: https://github.com/sweidinger/ha-print-cost-analyzer  
**Version**: v2024.8.1 (aktuell)  
**Home Assistant**: Erfordert v2024.8.0+  

Die Integration sollte jetzt problemlos mit der neuesten Home Assistant Version funktionieren! 🚀
