# Configuring management.server.port and Network Bind Address

## 1. What Decisions Make Up Management Infrastructure?

A service may accept business requests from an external network while allowing only operational tools on the same machine to read Actuator. To express that intent, you must distinguish the **port accepting connections** from the **network address the server binds to**.

- **Port** identifies the connection endpoint on an IP address, such as `8080` or `9091`.
- **Bind address** selects the local network interface used to accept connections. A listener is defined by an address and a port.
- **HTTP path** such as `/actuator/health` is handled after the connection reaches the appropriate server.
- **Endpoint enabling/exposure and authorization** decide which endpoints can be used and who is allowed to call them.

In Spring Boot **3.3.x**, Actuator shares the application's HTTP port by default. To separate the management entry point, configure `management.server.port`; to have management listen only on a specific address, use `management.server.address` together with a management port different from the main port. [Spring Boot 3.3 HTTP management configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

Separating the management port still runs within the same application/JVM. It does not create an independently deployed service, nor does it isolate CPU or memory resources from the application.

## 2. Four Properties to Read Together

| Property | Meaning |
| --- | --- |
| `server.port` | HTTP port of the main application server |
| `server.address` | Address the main application server binds to in order to accept connections |
| `management.server.port` | Selects the HTTP port for the management area |
| `management.server.address` | Dedicated bind address for the management area when using a separate port |

Example of two entry points:

```text
Main application: bind address 0.0.0.0, port 8080
Management:       bind address 127.0.0.1, port 9091
```

This is a server-side description. Binding a socket to a local address/port differs from the client choosing a destination address to connect to. [How the system binds a socket to an address](https://learn.microsoft.com/en-us/windows/win32/winsock/binding-a-socket). Callers do not use `0.0.0.0` as the advertised service address; they use the server's reachable real address, corresponding domain name, or `127.0.0.1` when calling locally.

`management.server.address` requires a separate management port. You cannot set only this property to separate Actuator's bind address while still sharing the application server/port. [Server and management server property reference](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

### Shared-Port Case

Standalone example:

```yaml
server:
  port: 8080
  address: 127.0.0.1

management:
  endpoints:
    web:
      exposure:
        include: health
```

`management.server.port` is not set, so management HTTP endpoints share the application's entry point. With the default path and an eligible endpoint, you can call:

```text
http://127.0.0.1:8080/actuator/health
```

When configuring `server.address=127.0.0.1` in this shared case, the local listening scope affects both business HTTP and management, not just Actuator.

## 3. Example: Separating the Port and Restricting Management Listening to Local

Place in `src/main/resources/application.yml` of a web application that already has Actuator:

```yaml
server:
  port: 8080
  address: 0.0.0.0

management:
  server:
    port: 9091
    address: 127.0.0.1
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include: health
  endpoint:
    health:
      enabled: true
```

The configuration expresses two separate intents:

1. Business HTTP has an entry point across local IPv4 addresses on port `8080`.
2. Management HTTP uses port `9091`, bound to the IPv4 loopback address `127.0.0.1`.

This example explicitly enables and exposes only `health`. There is no need to select all endpoints just to test the management port.

Equivalent configuration in properties format:

```properties
server.port=8080
server.address=0.0.0.0
management.server.port=9091
management.server.address=127.0.0.1
management.endpoints.enabled-by-default=false
management.endpoint.health.enabled=true
management.endpoints.web.exposure.include=health
```

Address to call directly from the process's same network environment:

```text
http://127.0.0.1:9091/actuator/health
```

Opening port 9091 does not automatically enable every endpoint. Enabling/exposure decisions still must be satisfied before the corresponding endpoints exist. [Actuator endpoint availability conditions](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing).

If another monitoring machine needs access, you must choose an appropriate bind address and have a network path to it. Merely changing the URL on the monitoring machine does not make a loopback listener accept remote connections.

## 4. Choosing the Bind Address Based on Where Callers Actually Run

### 4.1. Loopback and Specific Network Addresses

| Illustrative Value | Meaning When Binding an IPv4 Listener | Appropriate Use Case |
| --- | --- | --- |
| `127.0.0.1` | Accepts loopback connections within the local network environment | Operational tools running on the same host or same network namespace |
| `0.0.0.0` | Wildcard address to listen on local IPv4 interfaces | Needs to accept across multiple interfaces and access scope is designed |
| `192.168.10.20` | Binds to a specific address already assigned to the machine | Machine has a dedicated management interface bearing that address |

`192.168.10.20` is only an example: replace it with an IP that actually belongs to the running environment. Do not enter the **monitoring machine's** IP into the **application machine's** bind address. The bind address selects the receiver's local address, not an allowlist of client IPs.

IPv4 loopback belongs to the address range used to loop back to the same host, not representing a remote machine. [IPv4 loopback address specification in RFC 1122](https://www.rfc-editor.org/rfc/rfc1122.html#section-3.2.1.3).

The examples use IPv4 explicitly. IPv6 has its own addresses and listening rules; do not infer from `0.0.0.0` that all IPv6 interfaces are also open. When using the name `localhost`, also consider whether it resolves to an IPv4 or IPv6 address.

### 4.2. Listening Does Not Equal Reachable From Everywhere

Suppose management listens on an internal IP. A request from another machine still has to pass through routing, firewalls, platform network rules, and an intermediary server (proxy) if present, before reaching the HTTP server.

Therefore:

- A private network IP does not create user authentication by itself.
- `0.0.0.0` does not create a public IP address or open firewall rules.
- A public domain name does not change which address the JVM bound the listener to.
- Separating the port helps choose an independent network scope, but appropriate endpoint exposure and protection policies are still needed.

Before choosing an address, clearly describe the caller: a process on the application machine, another container, a monitoring machine on the LAN, or a system through a proxy. The answer determines where to listen.

## 5. Check the Listener First, Check the Endpoint Second

### Hands-On Prerequisites

Use Spring Boot 3.3.x, Java 17 or newer; Java 21 is suitable. The application already has a main startup class, `spring-boot-starter-web`, and `spring-boot-starter-actuator`.

Use the configuration in section 3; run directly on Windows, without going through a container or proxy yet. Assumptions:

- Ports 8080 and 9091 are not already used by another process.
- No Spring Security or custom filters alter the response.
- No context path, custom base path, conflicting controller path, or additional health path on the main port.
- Health status is `UP`, with no other configuration source overriding it.

Restart the application after changing the configuration. The outputs below are expected results under these conditions.

### 5.1. Observe Ports and Addresses Currently Listening

In PowerShell:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8080,9091 |
    Select-Object LocalAddress, LocalPort, OwningProcess
```

Verify that port 9091 has a listener bound to `127.0.0.1`, then check the process ID (PID) via `OwningProcess`. Do not use a fixed PID from documentation for comparison; PIDs and line order change across runs. This command reads OS TCP state and does not yet prove that the endpoint returns data. [`Get-NetTCPConnection` documentation](https://learn.microsoft.com/en-us/powershell/module/nettcpip/get-nettcpconnection?view=windowsserver2025-ps).

If the port appears but belongs to a different PID, identify the right process before concluding that your application configuration is in effect.

### 5.2. Call Health on the Management Port

```powershell
curl.exe --silent --show-error --max-time 3 --output NUL --write-out "%{http_code}\n" "http://127.0.0.1:9091/actuator/health"
```

Expected stdout is:

```text
200
```

The command prints an HTTP code followed by a newline and discards the body. To read the content:

```powershell
curl.exe --silent --show-error --max-time 3 "http://127.0.0.1:9091/actuator/health"
```

Typical response when healthy and details are hidden:

```json
{"status":"UP"}
```

### 5.3. Verify the Application Port Does Not Retain the Same Endpoint

```powershell
curl.exe --silent --show-error --max-time 3 --output NUL --write-out "%{http_code}\n" "http://127.0.0.1:8080/actuator/health"
```

Under the above assumptions, expected stdout:

```text
404
```

Key point to understand: port 8080 still has an HTTP server, but this request is not served as a health endpoint there. This is an **HTTP response**, different from being unable to connect to the port.

If you intentionally configure additional paths for health or have a controller/proxy providing a similar path, the result may differ; check that configuration separately.

### 5.4. Distinguish Network Errors From Endpoint Errors

| Observation | Investigation Direction |
| --- | --- |
| Cannot connect or timed out | Listener, destination address, port, routing, firewall |
| HTTP 404 | Right port and path; is the endpoint enabled/exposed |
| HTTP 401 or 403 | Authentication, authorization, and protective filters |
| Health response with unhealthy status | Reached the API; check health components |

When curl receives no HTTP response and `--write-out` prints `000`, do not treat it as an HTTP code returned by Actuator. Read stderr and curl's exit code. curl keeps the response code at 0 when no response code has been received from the server. [Meaning of curl response codes](https://curl.se/libcurl/c/CURLINFO_RESPONSE_CODE.html). Avoid repeatedly editing `include` to troubleshoot a listener that cannot even accept connections.

## 6. Reading Addresses Correctly in Containers and Behind Proxies

### Containers Have Their Own Network Namespace

In a container model using an isolated bridge network, `127.0.0.1` inside the container points to the container's own network environment. A management listener bound only to loopback inside the container does not automatically become a listener on the host's loopback.

Two configuration layers must be separated:

1. The address/port the Java process listens on **inside the container**.
2. The address/port the platform publishes **on the host or across the deployment network**.

For example, the Docker port publishing specification `127.0.0.1:19091:9091` expresses that host port 19091 on loopback forwards to container port 9091. It does not alter the JVM's listener configuration. In a standard bridge model, the process inside the container must also listen on an interface capable of receiving forwarded traffic; binding exclusively to container loopback does not satisfy that.

This is an example analyzing layers, not a complete deployment command. Other network modes such as shared network namespaces must be evaluated according to the actual configuration. [How Docker publishes and maps ports](https://docs.docker.com/engine/network/port-publishing/).

### Proxies or Published Ports Differing From Internal Ports

An external address like `https://monitor.example.com/actuator/health` may go through a proxy to internal HTTP listener 9091. The port and protocol seen by the user do not necessarily match the JVM listener directly.

Therefore, when troubleshooting, record both hops: **caller → proxy/published port** and **proxy → application**. If the proxy is on another machine, a management configuration bound only to loopback on the application machine does not allow that proxy to connect directly.

## 7. Special Values and Limits of Port Separation

### Sharing, Separate Port, Dynamic Port, or Disabling Management HTTP

With a fixed application port of 8080 in the example:

| `management.server.port` Value | Meaning |
| --- | --- |
| Unset | Uses the application port |
| `8080` | Still uses the same port; does not create separation merely because it is declared |
| `9091` | Uses a management port different from the application port |
| `0` | Requests dynamically choosing an available port; must read the actual port after startup |
| `-1` | Disables serving management endpoints over HTTP |

Spring Boot's configuration API explicitly defines the meaning of `0` and `-1`; leaving it unset allows using the main server port. [`ManagementServerProperties` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/web/server/ManagementServerProperties.html).

Do not call a URL with `:0` as if 0 were the actual allocated port. With dynamic ports, inspect logs or server information after startup. Detecting the actual port is described in the [embedded web server guide](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html).

Configuration to disable management HTTP:

```properties
management.server.port=-1
```

This is not a command to stop the JVM or disable all business HTTP. Nor does it decide JMX exposure; JMX has its own enablement and exposure list settings. [Management over JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

### A Different Port Does Not Automatically Mean HTTPS

The examples in this lesson use HTTP without TLS configuration. Choosing port number 8443 or 9443 does not automatically enable HTTPS. When TLS is needed for the separate management area, corresponding SSL must be configured; choosing certificates and connection scope are separate decisions.

### A Healthy Management Listener Does Not Prove a Healthy Business Listener

When management has a separate server/port, a check on the management port can succeed even if the main web infrastructure is having trouble accepting connections. Therefore, design checks suited to operational goals; do not use a single health result on a separate port as sole proof that all business serving paths work. [Spring Boot notes on health and a separate management port](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

## 8. Common Configuration Mistakes

| Mistake | How to Think About Fixing It |
| --- | --- |
| Setting a separate management address while keeping the same port | Choose a different management port before needing an independent listener |
| Assigning the monitoring machine's IP to `management.server.address` | Choose a local IP of the application machine; filter clients at the appropriate policy layer |
| Assigning an IP that does not exist on the machine | Check addresses actually assigned to real network interfaces |
| Calling `localhost` from a different machine | `localhost` is the caller's machine; use the application machine's address for remote access |
| Confusing container loopback with host loopback | Identify the network namespace at each hop |
| Changing the port in a file while the app still listens on the old port | Check profiles, environment variables, startup arguments, and the most recent restart |
| Port already in use by another process | Identify the occupying process or choose an appropriate port instead of just retrying the URL |

Spring Boot has precedence among configuration sources. For example, `--management.server.port=9191` can override `9091` in a file. In that case, inspect the effective value rather than looking at only one YAML file. [Configuration source precedence](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

Concise investigation flow: verify **process → listener/IP/port → network path → protocol/path → enablement/exposure → access permissions → health data**. Checking hop by hop avoids modifying endpoint config for an error occurring before HTTP ever reaches the application.

## 9. Self-Check Before Choosing a Configuration

**Scenario 1:** The application runs directly on a host, operational tools run on the same host, and business HTTP needs to accept connections over the LAN.

You can choose `server.address=0.0.0.0`, `server.port=8080`, and a separate management listener `127.0.0.1:9091`; then choose which endpoints are allowed to be exposed.

**Scenario 2:** The monitoring machine is a different host on the internal network. Management is currently bound to `127.0.0.1:9091`.

Changing the URL on the monitoring machine will not be enough. You must design a connection path and management listener that can accept on an appropriate interface, along with corresponding network policies and access permissions.

**Scenario 3:** The file sets 9091, but logs show the management area running on 9191.

Check higher-precedence configuration sources, profiles, and startup arguments; confirm the listener and PID before editing the URL.

**Scenario 4:** The management port returns health successfully, but users cannot reach the service on the application port.

Check the business listener and serving infrastructure separately. A successful connection to the separate management area only proves the management hop just tested.
