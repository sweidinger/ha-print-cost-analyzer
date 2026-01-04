name: Release v2024.8.0
body: |
  ## 🎉 3D Print Cost Analyzer v2024.8.0

  Diese Version löst das bekannte HACS-Kompatibilitätsproblem mit Home Assistant 2024.8+.

  ### ✨ Neues Feature
  - **Direct ZIP-Download**: Umgehung von HACS-Version-Checks
  - **Home Assistant 2024.8+**: Offizielle Kompatibilität
  - **Verbesserte Fehlerbehandlung**: Stabile Installation

  ### 🔧 Installationsoptionen

  #### Methode 1: ZIP-Download (empfohlen)
  ```bash
  # Download und Entpacken
  wget https://github.com/sweidinger/ha-print-cost-analyzer/archive/refs/tags/v2024.8.0.zip
  unzip v2024.8.0.zip
  
  # Kopieren nach HomeAssistant
  cp -r ha-print-cost-analyzer-master/custom_components/print_cost_analyzer /config/custom_components/
  
  # HomeAssistant neustarten
  docker restart homeassistant
  ```

  #### Methode 2: Manuel kopieren
  ```bash
  git clone https://github.com/sweidinger/ha-print-cost-analyzer.git
  cp -r ha-print-cost-analyzer/custom_components/print_cost_analyzer /config/custom_components/
  ```

  ### 📋 Was wurde gefixt

  - **HACS-Kompatibilität**: Repository.json für ZIP-Download
  - **Version-Detection**: Home Assistant 2024.8+ Unterstützung
  - **Installation**: Vereinfachte Installation mit mehreren Methoden

  ### 🔗 Links

  - **ZIP-Download**: https://github.com/sweidinger/ha-print-cost-analyzer/archive/refs/tags/v2024.8.0.zip
  - **Repository**: https://github.com/sweidinger/ha-print-cost-analyzer
  - **Issues**: https://github.com/sweidinger/ha-print-cost-analyzer/issues

  ### 🎯 Ziel

  Stabile und benutzerfreundliche 3D-Druck-Kostenanalyse für alle Home Assistant Versionen!

prerelease: true
draft: false