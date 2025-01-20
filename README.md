# Zengge Mesh Component for Home Assistant
![alt text](https://github.com/SleepyNinja0o/home-assistant-zengge/blob/main/images/icon.png)<br/>
<br/>
Control your Zengge bluetooth mesh lights from Home Assistant!

## Install with HACS (recommended)

Do you have [HACS](https://hacs.xyz/) installed?
1. Add **Zengge Mesh** as custom repository.
   1. Go to: `HACS` -> `Integrations` -> Click menu in right top -> Custom repositories
   1. A modal opens
   1. Fill https://github.com/SleepyNinja0o/home-assistant-zengge in the input in the footer of the modal
   1. Select `integration` in category select box
   1. Click **Add**
1. Search integrations for **Zengge Mesh**
1. Click `Install`
1. Restart Home Assistant
1. Setup Zengge Mesh integration using Setup instructions below

### Install manually

1. Install this platform by creating a `custom_components` folder in the same folder as your configuration.yaml, if it doesn't already exist.
2. Create another folder `zenggemesh` in the `custom_components` folder. Copy all files from `custom_components/zenggemesh` into the `zenggemesh` folder.

### Setup
1. In Home Assistant click on `Settings`
1. Click on `Devices & services`
1. Click on `+ Add integration`
1. Search for and select `Zengge Mesh`
1. Enter you `username` and `password` you also use in the **Hao Deng** app
1. The system will download you light list and add them to Home Assistant
1. Once the system could connect to one of the lights your lights will show up as _available_ and can be controlled from HA   
1. Enjoy :)

## Troubleshooting
**As of right now, only the first place is retrieved from the Hao Deng servers, currently working on this**<br/><br/>
**Make sure that at least *1 device/light* is in *bluetooth range* of your Home Assistant server.**

If you run into issues during setup or controlling the lights please increase logging and provide them when creating an issue:

Add `custom_components.zenggemesh: debug` to the `logger` config in you `configuration.yaml`:

```yaml
logger:
  default: error
  logs:
     custom_components.zenggemesh: debug
```
Restart Home Assistant for logging to begin.<br/>
Logs can be found under Settings - System - Logs - Home Assistant Core<br/>
Be sure to click **Load Full Logs** in order to retrieve all logs.<br/>

## Credits
The majority of this work was based on the [home-assistant-awox](https://github.com/fsaris/home-assistant-awox) integration created by **@fsaris** .<br/>
Huge shotout to him for all his hard work!<br/><br/>

Also, many kudos to **@donparlor** and **@cocoto** for their continued support on this project!<br/>It is appreciated very much!
