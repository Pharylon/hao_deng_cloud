# Hao Deng Cloud Component for Home Assistant


<img src="https://play-lh.googleusercontent.com/RlOT4SdOj8mLhbOJPwyv_VHqY72vAQzJdGq1YKB2yIufEPIKaYIk1SKODkOTZLnjBg" width="100" height="100"> <img src="https://m.media-amazon.com/images/I/414M0i-ED-L.jpg" width="100" height="100">

Control your Hao Deng Lights mesh lights from Home Assistant! This integration allows you to
control the above lights that you'd normally use through the Hao Deng App.

## Important Notes

* This integration is in beta. Please open an issue if you have any problems!
* This integration uses the cloud. If you don't have a wifi bridge, this won't work (ie, if you can control your lights with the Hao Deng app when you're away from home, you're good. If you have to be at your house to use it, you're not good)
* As of right now, lights are only read in on server start. So when you add or modify lights (including adding them to groups) they will not be automatically updated and you'll need to restart home assistant (this is definitely a feature coming, but we're in beta right now!)
* The Magic Cloud API doesn't seem to be able to handle more than 5 or so light updates at a time. This can make the lights stutter out of sync when updating a lot at once (I, personally, have 16 of these in my Great Room so I've really noticed!). To get around this issue, use the Hao Deng app to add your lights to groups that mirror the groups and rooms in your home. This allows the integration to "batch" those lights in a single group and makes everything flow better. For insance, I have a light group in Home Assisstant for my 16 Great Room lights. I put all those lights in a group in the Hao Deng app as well, and now they can be controlled in sync much better!

## Installation with HACS (recommended)
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
1. Search for and select `Hao Deng Cloud`
1. Enter you `username` and `password` you also use in the **Hao Deng** app
1. The system will download you light list and add them to Home Assistant
1. Once the system could connect to one of the lights your lights will show up as _available_ and can be controlled from HA   
1. Enjoy :)

## Troubleshooting
**This integration requires the cloud**
1. Make sure it works through the Hao Deng app (this integration does not work unless you can control your lights through that app) when bluetooth is off, or you're out of bluetooth range of your lights
2. Make sure your country code is correct
3. Make sure you have the newest version of this integration installed
4. Restart your server once if you've made any chages to your lights recently
5. Before submitting an issue, add `custom_components.hao_deng_cloud: debug` to the `logger` config in you `configuration.yaml`:

```yaml
logger:
  default: error
  logs:
     custom_components.hao_deng_cloud: debug
```
Restart Home Assistant for logging to begin.<br/>
Logs can be found under Settings - System - Logs - Home Assistant Core<br/>
Be sure to click **Load Full Logs** in order to retrieve all logs and submit those with any issues.<br/>

## Credits
Credit to 
**@SleepyNinja0o** started work on a bluetooth integration and had to give it up as it was unstable. However, I used his authentication
code and got a lot of other helpful tidbits from his repo. Huge shotout to him for all his hard work!<br/><br/>

<!-- Also, many kudos to **@donparlor** and **@cocoto** for their continued support on this project!<br/>It is appreciated very much! -->
