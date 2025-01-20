# Hao Deng Cloud Component for Home Assistant


<img src="https://play-lh.googleusercontent.com/RlOT4SdOj8mLhbOJPwyv_VHqY72vAQzJdGq1YKB2yIufEPIKaYIk1SKODkOTZLnjBg" width="100" height="100"> <img src="https://m.media-amazon.com/images/I/414M0i-ED-L.jpg" width="100" height="100">

Control your Hao Deng Lights mesh lights from Home Assistant! This integration allows you to
control the above lights that you'd normally use through the Hao Deng App



## Install with HACS (recommended)
se
Do you have [HACS](https://hacs.xyz/) installed?
1. Add **Hao Deng Cloud Component** as custom repository.
   1. Go to: `HACS` -> `Integrations` -> Click menu in right top -> Custom repositories
   1. A modal opens
   1. Fill https://github.com/Pharylon/hao_deng_cloud in the input in the footer of the modal
   1. Select `integration` in category select box
   1. Click **Add**
1. Search integrations for **Hao Deng Cloud**
1. Click `Install`
1. Restart Home Assistant
1. Setup Hao Deng Cloud integration using Setup instructions below

### Install manually

1. Install this platform by creating a `custom_components` folder in the same folder as your configuration.yaml, if it doesn't already exist.
2. Create another folder `hao_deng_cloud` in the `custom_components` folder. Copy all files from `custom_components/hao_deng_cloud` into the `hao_deng_cloud` folder.

### Setup
1. In Home Assistant click on `Settings`
1. Click on `Devices & services`
1. Click on `+ Add integration`
1. Search for and select `How Deng Cloud`
1. Enter you `username` and `password` you also use in the **Hao Deng** app
1. The system will download you light list and add them to Home Assistant
1. Once the system could connect to one of the lights your lights will show up as _available_ and can be controlled from HA   
1. Enjoy :)

## Troubleshooting
**As of right now, only the first place is retrieved from the Hao Deng servers, currently working on this**<br/><br/>
**Make sure that at least *1 device/light* is in *bluetooth range* of your Home Assistant server.**

If you run into issues during setup or controlling the lights please increase logging and provide them when creating an issue:

Add `custom_components.hao_deng_cloud: debug` to the `logger` config in you `configuration.yaml`:

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
Credit to 
**@SleepyNinja0o** started work on a bluetooth integration and had to give it up as it was unstable. However, I used his authentication
code and got a lot of other helpful tidbits from his repo. Huge shotout to him for all his hard work!<br/><br/>

<!-- Also, many kudos to **@donparlor** and **@cocoto** for their continued support on this project!<br/>It is appreciated very much! -->
