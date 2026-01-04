# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial release of 3D Print Cost Analyzer integration

## [1.0.0] - 2024-01-04

### Added
- **Spoolman Integration**: Automatic material cost calculation from Spoolman
- **Shelly Plug Entity Support**: Select individual Shelly power and energy entities
- **AMS-Unit Support**: Track filament usage across multiple AMS slots
- **InfluxDB v2 Integration**: Store and analyze historical print data
- **Dynamic Energy Pricing**: Choose between fixed price or entity-based pricing
- **Multi-Printer Support**: Configure multiple 3D printers
- **Complete Config Flow**: User-friendly setup with entity selectors
- **Comprehensive Sensors**: 
  - Total print cost tracking
  - Active spools monitoring
  - Energy consumption sensors
  - AMS status sensors
  - Dynamic energy cost sensor
- **Service Integration**: Manual print job entry service
- **HACS Compatibility**: Full HACS integration for easy installation
- **German Localization**: Complete German language support
- **Documentation**: Comprehensive README and installation guides
- **Dashboard Examples**: Lovelace dashboard templates
- **Error Handling**: Robust error handling and logging

### Technical Features
- **Async Operations**: Non-blocking API calls
- **Real-time Updates**: 60-second refresh interval
- **Data Validation**: Input validation and sanitization
- **Resource Management**: Proper cleanup of connections
- **Debug Logging**: Comprehensive debug information
- **Entity Caching**: Efficient entity state management

### Security
- **Token Security**: Secure handling of API tokens
- **Data Privacy**: No sensitive data logging
- **Input Sanitization**: Protection against injection attacks

### Documentation
- **README**: Comprehensive usage guide
- **HACS Install Guide**: Step-by-step installation
- **Issue Templates**: Bug report and feature request templates
- **Code Comments**: Detailed inline documentation
- **License**: MIT License with clear terms

### Breaking Changes
- None (initial release)

### Deprecated
- None

### Fixed
- None (initial release)

### Security
- None (initial release)

---

## Version History

### v1.0.0 (2024-01-04)
- 🎉 Initial public release
- ✨ Complete feature set implemented
- 📚 Full documentation provided
- 🏗️ HACS integration ready

---

## Planned Features (Future Releases)

### v1.1.0
- [ ] OctoPrint integration
- [ ] Klipper/Moonraker support
- [ ] Print quality metrics
- [ ] Maintenance cost tracking

### v1.2.0
- [ ] Mobile app companion
- [ ] Print time predictions
- [ ] Cost alerts and notifications
- [ ] Advanced analytics dashboard

### v1.3.0
- [ ] Multi-user support
- [ ] Print sharing features
- [ ] Cloud synchronization
- [ ] API for third-party integrations

---

## Support

For support, please:
1. Check the [documentation](README.md)
2. Search [existing issues](https://github.com/your-username/ha-print-cost-analyzer/issues)
3. Create a [new issue](https://github.com/your-username/ha-print-cost-analyzer/issues/new)
4. Join the [HomeAssistant Community](https://community.home-assistant.io/)

---

**Note**: This project is maintained by volunteers. Please be patient with support requests and consider contributing if you find this integration useful!