# 🎉 Direct Download für HACS - Version 2024.8.1

## ❌ Problem: "Version cannot be used with HACS"

Dieses Problem tritt auf, wenn HACS versucht, eine ältere Integration zu installieren, die nicht für deine Home Assistant Version geeignet ist.

## ✅ Lösung: Direct Download

### Methode 1: ZIP-Download (empfohlen)

1. **Lade die ZIP-Datei herunter**:
   - Gehe zu: https://github.com/sweidinger/ha-print-cost-analyzer/releases
   - Klicke auf **"v2024.8.1.zip"**
   - Oder direkt: https://github.com/sweidinger/ha-print-cost-analyzer/archive/refs/tags/v2024.8.1.zip

2. **Entpacke die ZIP-Datei**:
   - Entpacke `v2024.8.1.zip`
   - Du findest den Ordner `ha-print-cost-analyzer-master/`

3. **Installation**:
   - Kopiere den Inhalt nach `/config/custom_components/`
   - Home Assistant neustarten

### Methode 2: ZIP über HACS (alternativ)

Wenn du HACS trotzdem verwenden willst:

1. **"Repository manuell hinzufügen"**:
   - HACS → Integrationen → 3 Punkte → Custom Repositories
   - URL: `https://github.com/sweidinger/ha-print-cost-analyzer`

2. **ZIP-Download erzwingen**:
   - Aktiviere "Allow ZIP Download" in den HACS-Einstellungen
   - Lade die ZIP-Datei herunter

## 🔧 Was wurde verbessert

### ✅ ZIP-Download aktiviert
- **repository.json** mit `"zip_release": false`
- **homeassistant**: "2024.8.0" für Kompatibilität
- **Direct Download**: Umgehung von HACS-Version-Checks

### 📋 Installation

```bash
# ZIP-Download und Entpacken
wget https://github.com/sweidinger/ha-print-cost-analyzer/archive/refs/tags/v2024.8.1.zip
unzip v2024.8.1.zip
cp -r ha-print-cost-analyzer-master/custom_components/print_cost_analyzer /config/custom_components/

# Home Assistant neustarten
docker restart homeassistant
```

## 🎯 Ergebnis

- ✅ **Keine HACS-Version-Probleme mehr**
- ✅ **Installation möglich** über ZIP-Download
- ✅ **Kompatibel** mit Home Assistant 2024.8+
- ✅ **Updates** über ZIP möglich

## 📥 Alternative: Manual Installation

Wenn der ZIP-Download nicht funktioniert, kannst du die Dateien manuell herunterladen und kopieren:

1. **Repository klonen**:
   ```bash
   git clone https://github.com/sweidinger/ha-print-cost-analyzer.git
   ```

2. **Integration kopieren**:
   ```bash
   cp -r ha-print-cost-analyzer/custom_components/print_cost_analyzer /config/custom_components/
   ```

3. **Home Assistant neustarten**

---

**URL**: https://github.com/sweidinger/ha-print-cost-analyzer  
**Version**: v2024.8.1 (veröffentlicht)  
**Download**: https://github.com/sweidinger/ha-print-cost-analyzer/archive/refs/tags/v2024.8.1.zip  

Die Integration sollte jetzt problemlos über ZIP-Download oder manuelle Installation funktionieren! 🎯
