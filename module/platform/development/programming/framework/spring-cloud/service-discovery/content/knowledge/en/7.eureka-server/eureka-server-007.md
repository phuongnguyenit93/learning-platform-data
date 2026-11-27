# The /eureka/ Path, Context Path, and Client Access URLs

Eureka Server provides a REST API for Eureka Clients to register instances, send heartbeats, and fetch service lists. With default settings, the server typically listens on port `8761` and the API has the base path `/eureka/`. Therefore, the address clients normally use is `http://localhost:8761/eureka/`.

When deploying behind a reverse proxy, changing the port, or placing Spring Boot under a custom context path, the client URL must reflect the address clients can actually reach. Confusing the application's context path with the `/eureka/` base path is a common cause of `404` errors, connection errors, or clients failing to register. This lesson analyzes each part of the URL and how to configure the server, client, and proxy so they align.

## 1. Eureka Address Structure

A URL used by a Eureka Client typically takes the form:

```text
http(s)://<host>:<port>/<context-path>/eureka/
```

Where:

- `http` or `https` is the scheme the client uses to connect.
- `<host>` is a hostname or IP resolvable and reachable from the client's runtime environment.
- `<port>` is the port exposed by Eureka Server or the reverse proxy.
- `<context-path>` is the Spring Boot application's prefix if the server is deployed under a custom context path; omit this segment if none is set.
- `/eureka/` is the default REST API base path of Eureka Server.

Examples:

| Deployment setup | Client access URL |
| --- | --- |
| Eureka running locally, no context path | `http://localhost:8761/eureka/` |
| Context path is `/discovery` | `http://eureka.internal:8761/discovery/eureka/` |
| HTTPS via public domain | `https://eureka.example.com/eureka/` |
| Reverse proxy exposes `/registry` prefix | `https://gateway.example.com/registry/eureka/` |

Distinguish the last two segments of the URL: the context path is the web application prefix; `/eureka/` is Eureka's REST API path. If the context path is `/discovery`, the full path is `/discovery/eureka/`.

## 2. Default Eureka Server Configuration

A simple Eureka Server needs the server dependency and the `@EnableEurekaServer` annotation.

Example startup class:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.netflix.eureka.server.EnableEurekaServer;

@SpringBootApplication
@EnableEurekaServer
public class EurekaServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(EurekaServerApplication.class, args);
    }
}
```

Example `application.yml` for a server running locally:

```yaml
server:
  port: 8761

spring:
  application:
    name: eureka-server

eureka:
  instance:
    hostname: ${EUREKA_HOST:localhost}
  client:
    register-with-eureka: false
    fetch-registry: false
```

`register-with-eureka: false` and `fetch-registry: false` are appropriate for a standalone Eureka Server that does not register with itself and does not fetch the registry from peers. In a multi-node Eureka cluster, peer configuration must be set up separately; servers normally register with and fetch the registry from peers to synchronize. Do not copy these two `false` values to every node in a peer-aware cluster without considering the topology.

With the default configuration, Eureka Server accepts REST requests at `/eureka/`. Clients will use a URL with port `8761` and that base path.

## 3. Spring Boot Context Path

`server.servlet.context-path` sets a common prefix for the Spring Boot application's servlet endpoints. If configured as:

```yaml
server:
  port: 8761
  servlet:
    context-path: /discovery
```

The application's endpoints are placed under the `/discovery` prefix. Since the Eureka API already has the base path `/eureka/`, the full URL clients must call becomes:

```text
http://localhost:8761/discovery/eureka/
```

Some comparison examples:

| `server.servlet.context-path` | Eureka API URL |
| --- | --- |
| Not declared or root context | `http://localhost:8761/eureka/` |
| `/discovery` | `http://localhost:8761/discovery/eureka/` |
| `/platform/registry` | `http://localhost:8761/platform/registry/eureka/` |

The context path must start with `/`. Avoid adding a trailing `/` unnecessarily; keep consistent notation across configuration and reverse proxy rules.

### 3.1. Context Path Is Not Server Port

These two properties govern two separate parts:

- `server.port` determines which port the process listens on, e.g. `8761`.
- `server.servlet.context-path` determines the URL prefix of the web application, e.g. `/discovery`.

Changing the port does not automatically change the path; changing the context path does not automatically change the port. When a URL is unreachable, check both.

### 3.2. Management Port Is Not the Eureka API Port

If `management.server.port` is configured so Actuator runs on a separate port, that does not automatically move the Eureka REST API to the management port. Eureka Clients must still point to the application port serving the Eureka API.

For example:

```yaml
server:
  port: 8761

management:
  server:
    port: 9001
  endpoints:
    web:
      exposure:
        include: health,info
```

In this configuration, the Eureka API remains on port `8761`; Actuator is served on port `9001` per the management settings. Do not set `defaultZone` to `http://localhost:9001/eureka/` unless you have intentionally designed custom routing for the Eureka API on that port.

## 4. Configuring the Address in Eureka Client

Eureka Client only needs the URL where Eureka Server is reachable from the client's environment. Example when the server uses the default port and no context path:

```yaml
spring:
  application:
    name: order-service

server:
  port: 8080

eureka:
  client:
    register-with-eureka: true
    fetch-registry: true
    service-url:
      defaultZone: ${EUREKA_SERVER_URL:http://localhost:8761/eureka/}
  instance:
    prefer-ip-address: true
```

Key points to note:

- `eureka.client.service-url.defaultZone` is the base URL of Eureka Server used by the client.
- `defaultZone` is the key name of the service URL map; preserve exact capitalization of `Z` as documented in Eureka/Spring Cloud Netflix.
- `register-with-eureka` enables registering the client application's instance.
- `fetch-registry` enables fetching the registry to discover other services.
- `prefer-ip-address` controls advertising the IP instead of the hostname in instance info; it does not change the server URL the client connects to.

If the server has context path `/discovery`, update the URL:

```yaml
eureka:
  client:
    service-url:
      defaultZone: ${EUREKA_SERVER_URL:http://localhost:8761/discovery/eureka/}
```

In production deployments, the URL is typically supplied via an environment variable:

```text
EUREKA_SERVER_URL=https://eureka.internal.example.com/discovery/eureka/
```

This allows the same client artifact to run locally, in Docker, or in production without modifying source code.

## 5. Where Must the Client Address Be Reachable From?

A common error is a URL that works when tested from the host machine, yet fails when the client runs inside a container or on another host.

### 5.1. Running Both Server and Client on a Local Machine

If both processes run directly on the same machine, the client can use:

```text
http://localhost:8761/eureka/
```

If Eureka Server uses context path `/discovery`:

```text
http://localhost:8761/discovery/eureka/
```

### 5.2. Client Running in Docker

Inside a client container, `localhost` points to the client container itself. If Eureka Server runs in another container on the same Docker network, use the server's service name or DNS alias:

```yaml
eureka:
  client:
    service-url:
      defaultZone: http://eureka-server:8761/eureka/
```

The name `eureka-server` must match the service name or network alias in Docker Compose. If Eureka Server runs on the host machine, use the hostname/IP reachable from the container according to your OS's Docker configuration; do not assume `localhost` inside a container refers to the host.

### 5.3. Client Running on Another Machine

Use a DNS name or IP of the Eureka Server machine that is reachable over the network:

```yaml
eureka:
  client:
    service-url:
      defaultZone: http://10.0.0.15:8761/eureka/
```

Ensure firewalls, security groups, and network policies allow the client to connect to the server port. If Eureka publishes an instance's hostname/IP to consumers, those instance addresses must also be reachable from consumers; being able to reach the registry server does not guarantee consumers can call the service instance.

## 6. Deploying Behind a Reverse Proxy or Ingress

In production, Eureka Server may sit behind a reverse proxy, ingress, or load balancer. Clients then normally access the external URL instead of the process's internal address.

Example public URL:

```text
https://gateway.example.com/registry/eureka/
```

There are two common ways to organize paths:

1. **The application itself has context path `/registry`:** Eureka Server receives internal requests at `/registry/eureka/`; the proxy forwards that path as-is.
2. **The proxy adds a prefix and rewrites the path:** Clients call `/registry/eureka/`, the proxy strips the `/registry` prefix and forwards the request upstream to `/eureka/`.

Both approaches work if proxy rules and client URLs match. Avoid situations where the proxy keeps the prefix while the application also adds a context path, turning requests into `/registry/registry/eureka/` or a nonexistent path.

With HTTPS termination at the proxy, clients use the `https` scheme and public hostname. The proxy must properly forward the REST methods and paths Eureka needs; authentication, TLS, and network access settings must be restricted appropriately. If Eureka servers run in a peer cluster, servers also need stable, reachable internal peer URLs; they do not necessarily use the same public URL intended for external clients.

When an application generates redirects or advertises URLs based on incoming requests, configure forwarded headers and proxy settings properly according to your Spring Boot version. Do not trust forwarded headers from untrusted sources.

## 7. Testing the Eureka URL via HTTP

After starting the server, test the REST API from the same network environment as the client.

With the default server:

```bash
curl -i -H "Accept: application/json" \
  http://localhost:8761/eureka/apps
```

With context path `/discovery`:

```bash
curl -i -H "Accept: application/json" \
  http://localhost:8761/discovery/eureka/apps
```

If the endpoint is protected by authentication, supply appropriate credentials when testing. A successful response indicates the request reached the right REST endpoint; an empty application list can still occur if no clients have registered yet.

You can check layer by layer:

1. Verify the Eureka Server process has started and is listening on the right port.
2. Determine the actual context path from the active configuration.
3. Combine the context path with `/eureka/` to form the base URL.
4. Call the `/apps` endpoint from the machine or container running Eureka Client.
5. Put that same base URL into `eureka.client.service-url.defaultZone`.
6. Check client logs to confirm registration and registry fetch requests succeed.

Do not rely solely on checking the URL in a browser on the host if clients run in a different network namespace. Run `curl` from the client container or machine to verify DNS, routing, and firewalls.

## 8. Diagnosing Common Errors

| Symptom | Possible cause | How to resolve |
| --- | --- | --- |
| Client reports connection refused | Server is not running, wrong port, bind address, or firewall block | Verify process, port `8761` (or actual port), and network path from the client. |
| Client receives `404 Not Found` | Wrong context path or missing `/eureka/` in URL | Cross-check `server.servlet.context-path` and REST API base path; test `/eureka/apps` or `<context-path>/eureka/apps`. |
| Works from host, but fails from Docker | Using `localhost` inside container or wrong service DNS | Use the service hostname on the Docker network or a host address reachable from the container. |
| Client registers, but cannot fetch registry | `fetch-registry` is disabled, wrong URL/credentials, or response blocked by proxy | Check `fetch-registry`, client logs, authentication, and proxy routing. |
| Eureka Dashboard opens, but client fails to register | Dashboard path is right, yet REST API URL or client property is wrong; server security blocks REST requests | Check `/eureka/apps`, `defaultZone`, and client access permissions. |
| Proxy returns `502` or `504` | Wrong upstream host/port, timeout, or proxy cannot reach server | Check upstream health, DNS, routing, and proxy timeouts. |
| Client keeps using old URL after changing context path | Profile or environment variable overrides config file | Inspect property sources, `EUREKA_SERVER_URL`, and active profiles. |

Some HTTP status codes help narrow down the issue:

- `404`: the server responded, but the path does not match or the endpoint is not mapped.
- `401`/`403`: the request reached the server/proxy, but lacks credentials or is blocked by policy.
- `502`/`504`: the reverse proxy did not receive a valid response from upstream or timed out.
- `Connection refused`/timeout: check process, port, DNS, routing, and firewall before checking paths.

## 9. Complete Configuration Examples

### 9.1. Eureka Server with Context Path `/discovery`

```yaml
spring:
  application:
    name: eureka-server

server:
  port: 8761
  servlet:
    context-path: /discovery

eureka:
  instance:
    hostname: ${EUREKA_HOST:localhost}
  client:
    register-with-eureka: false
    fetch-registry: false
```

The base URL of the Eureka API is:

```text
http://localhost:8761/discovery/eureka/
```

### 9.2. Eureka Client Connecting to the Server Above

```yaml
spring:
  application:
    name: order-service

server:
  port: 8080

eureka:
  client:
    register-with-eureka: true
    fetch-registry: true
    service-url:
      defaultZone: ${EUREKA_SERVER_URL:http://localhost:8761/discovery/eureka/}
  instance:
    prefer-ip-address: true
```

If the client runs in Docker, replace the default `localhost` with the Eureka Server's hostname on the Docker network, such as `http://eureka-server:8761/discovery/eureka/`.

## 10. Key Takeaways

- The default Eureka REST API base path is `/eureka/`; the default local URL is typically `http://localhost:8761/eureka/`.
- `server.servlet.context-path` prepends a common prefix before the base path, such as `/discovery/eureka/`.
- `server.port` and context path are independent settings; `management.server.port` does not automatically move the Eureka API.
- Clients configure the server URL via `eureka.client.service-url.defaultZone`; preserve the exact `defaultZone` key.
- The address must be reachable from the client's actual runtime environment; `localhost` inside a container refers to that container.
- Reverse proxies must properly forward scheme, host, port, and path; verify rewrite rules so prefixes are neither missing nor duplicated.
- Use `/eureka/apps` or `<context-path>/eureka/apps` to verify the REST endpoint from the client's network.

When the context path, `/eureka/` base path, and network addresses are configured consistently, Eureka Clients can register, send heartbeats, and fetch the registry reliably in both local and production environments.
