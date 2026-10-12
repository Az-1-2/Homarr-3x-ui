# Homarr-3x-ui
A widget that shows system stats, number of clients, inbounds, online, and enabled, total download and upload, and lists all clients in a neat little widget in your Homarr dashboard. This is a small Docker container that collects the necessary data from 3x-ui via the api and provides it to Homarr in a way it can interpret, as Homarr is currently unable to do it directly. 

# Install Steps
1. Copy the [Compose](https://github.com/Az-1-2/Homarr-3x-ui/blob/main/docker-compose.yml) file into a file into a new directory
2. If you don't already, explicitly define a network for Homarr named "homarr" in its compose file, as Homarr-3x-ui must be on the same Docker network as your Homarr deployment in order to pass information to it. Here is an example.
```
networks:
  homarr:
    name: homarr
    driver: bridge
    ipam:
      config:
        - subnet: 172.31.0.0/24
```
Note: Remember to add this somewhere in your Homarr's compose:
```
networks:
  - homarr
```


3. Fill in the Env variables for you 3x-ui token and url. To get an api token in 3x-ui, go to your panel, panel settings, authentication, and api token. Once there, click to create a new token with the name "Homarr-3x-ui" and copy the generated token and put it into the associated environment variable
4. Once done, go to your homarr dashboard and to the custom api widgets section, then find Homarr-3x-ui in the workshop and install it. You do not need to add credentials, as it is set to access Homarr-3x-ui internally through the shared docker network.

If you have any questions, feel free to open an issue :)
