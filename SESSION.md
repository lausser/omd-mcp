the chatbot will run behind an Apache webserver. This is an example how the Apache frontend (which handles basic auth) forwards requests and the user session to the chatbot.

```
<Location /${OMD_SITE}/chatbot>
    ProxyPass http://127.0.0.1:###CONFIG_CHATBOT_TCP_PORT###/${OMD_SITE}/chatbot retry=0 disablereuse=On
    ProxyPassReverse http://127.0.0.1:###CONFIG_CHATBOT_TCP_PORT###/${OMD_SITE}/chatbot
    ProxyPreserveHost On
    RewriteRule .* - [E=PROXY_USER:%{LA-U:REMOTE_USER},NS]
    SetEnvIf Request_Protocol ^HTTPS.* IS_HTTPS=1
    SetEnvIf Authorization "^.+$" IS_BASIC_AUTH=1
    # without thruk cookie auth, use the proxy user from the rewrite rule above
    RequestHeader set X-WEBAUTH-USER "%{PROXY_USER}s"  env=IS_HTTPS
    RequestHeader set X-WEBAUTH-USER "%{PROXY_USER}e"  env=!IS_HTTPS
    # when thruk cookie auth is used, fallback to remote user directly
    RequestHeader set X-WEBAUTH-USER "%{REMOTE_USER}e" env=!IS_BASIC_AUTH
    SetEnvIf Authorization "^Bearer\s(.+)$" HasBearer=1
    RequestHeader unset Authorization env=!HasBearer

    ErrorDocument 503 /503.html?CHATBOT=on
</Location>
```
(Don't care about the variables in ###, these play no role yet. Focus on the X-WEBAUTH-USER, which is the username of somebody who has successfully logged in. This user name is lso known to Thruk and it will be used in the communication between the mcp and the Thruk api. Diffeent users may have different privileges regarding which hosts and services they can see through the Thruk API. And so different users can only send hosts and services into a scheduled downtime through the MCP if they are in the user's scope)

The chatbot should keep sessions, so that every user and every login gets a fresh session. When there is no input in  chatbot session for 15 minutes, then 
* any "submit" button should be disabled
* a message "session has ended after inactivity"
* any session state and connections to the mcp and the AI should be discarded

Also in the chatbots web ui the username should be displayed
