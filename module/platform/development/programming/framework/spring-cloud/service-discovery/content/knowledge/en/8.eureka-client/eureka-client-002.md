# Connecting to Eureka Server via `serviceUrl.defaultZone`

## 1. Role of `serviceUrl.defaultZone`

In Spring Cloud Service Discovery, Eureka Client needs to know the address of the Eureka Server in order to register instances, send heartbeats, deregister, and fetch the registry. The `eureka.client.serviceUrl.defaultZone` property (commonly written in YAML as `eureka.client.service-url.defaultZone`) provides that address.

The value of this property is the root URL of the Eureka REST API, for example:

```text
http://localhost:8761/eureka/
```

This is a network address that the Eureka Client process can reach directly. It is not a service name in the registry, not the URL of a business API, and it does not by itself enable registration or registry fetching. Those behaviors are controlled by separate properties such as `register-with-eureka` and `fetch-registry`.

In the Spring Cloud Service Discovery module, `DiscoveryClient` and `ServiceRegistry` provide Spring-level APIs for discovering or registering services. With Eureka, Eureka Client uses `serviceUrl.defaultZone` to connect to the registry server to perform those operations.

## 2. Configuration in YAML

A service named `order-service` can declare the Eureka Server address as follows:

```yaml
spring:
  application:
    name: order-service

server:
  port: 8081

eureka:
  client:
    service-url:
      defaultZone: http://localhost:8761/eureka/
    register-with-eureka: true
    fetch-registry: true
```

In this configuration:

- `service-url.defaultZone` specifies the Eureka Server endpoint used by the client.
- `register-with-eureka: true` allows the client to register the application's instance in the registry.
- `fetch-registry: true` allows the client to fetch the registry to discover instances of other services.

The registration and registry-fetching flags are independent of each other. An application can register without fetching the registry if it does not call other services via discovery. Conversely, a consumer that only needs to look up services can disable registering itself.

### 2.1. Note on Capitalization in `defaultZone`

`serviceUrl` is a configuration map, where `defaultZone` is the key name. Because map keys are case-sensitive, keep `defaultZone` spelled with an uppercase `Z`. The example below easily causes configuration errors because the key has been changed:

```yaml
eureka:
  client:
    service-url:
      defaultzone: http://localhost:8761/eureka/
```

The `service-url` prefix can use kebab-case thanks to Spring Boot's relaxed binding; the `defaultZone` key inside the map must preserve its exact casing. When reading documentation or logs, you may also see the full form `eureka.client.serviceUrl.defaultZone`.

## 3. Configuration in `application.properties`

If your project uses properties files instead of YAML, declare it on a single line:

```properties
spring.application.name=order-service
server.port=8081

eureka.client.serviceUrl.defaultZone=http://localhost:8761/eureka/
eureka.client.register-with-eureka=true
eureka.client.fetch-registry=true
```

Both YAML and properties formats serve the same purpose. Choose the format that fits your project's configuration structure and avoid declaring the same property in multiple places with different values, because profiles or higher-priority configuration sources can override the value you are checking.

## 4. Where Should the URL Point?

A Spring Cloud Eureka Server typically runs on port `8761` and exposes the Eureka API under the `/eureka/` context path. Therefore, a common address is `http://<host>:8761/eureka/`. The port and context path may vary depending on your deployment configuration; the client must use the exact address that the server actually exposes.

Crucially, the URL must be reachable from the environment running the Eureka Client. `localhost` always refers to the machine or network namespace of the process calling that URL—not the user's machine or another container.

For example:

| Environment | Example URL | Reason |
|---|---|---|
| Client runs on the same machine as Eureka Server | `http://localhost:8761/eureka/` | Both processes share the network host |
| Client and server run in two containers on the same Docker network | `http://eureka-server:8761/eureka/` | Client reaches the server via DNS/service name on the network |
| Client runs on another machine in an internal network | `http://10.0.0.20:8761/eureka/` | Uses a server address routable from the client machine |
| Server exposes a secured endpoint | `https://discovery.example.internal/eureka/` | Client connects over HTTPS and must trust the server certificate |

If `order-service` runs in its own container, configuring `localhost:8761` typically causes the client to look for Eureka Server inside the `order-service` container itself. When the server lives in another container, use a service name or hostname that the client container can resolve, and ensure both containers have appropriate network connectivity.

Do not confuse the Eureka Server URL with the URL of the registered application. For example, `http://order-service:8081/` is the business instance address; `http://eureka-server:8761/eureka/` is the registry address the client uses to register and query.

## 5. Using Environment Variables per Deployment Environment

The Eureka Server address often differs across development, testing, and production environments. You can externalize the URL to an environment variable so you do not have to modify source code when deploying:

```yaml
eureka:
  client:
    service-url:
      defaultZone: "${EUREKA_SERVER_URL:http://localhost:8761/eureka/}"
    register-with-eureka: true
    fetch-registry: true
```

When running the application, set `EUREKA_SERVER_URL` for each environment. If this variable is not set, Spring falls back to the default URL in the expression. For production, manage URLs and certificate details via deployment configuration or your organization's secret management system; never commit credentials to the repository.

You can also separate configurations with Spring profiles, such as `application-dev.yml` and `application-prod.yml`. Whether you use profiles or environment variables, verify the final resolved value that the application actually loads after all configuration sources are merged.

## 6. Configuring Multiple Eureka Server URLs

In environments with multiple Eureka Server endpoints, a zone can list multiple comma-separated URLs:

```yaml
eureka:
  client:
    service-url:
      defaultZone: "http://eureka-1:8761/eureka/,http://eureka-2:8761/eureka/"
```

This list provides multiple endpoints for Eureka Client to use when connecting to the registry. Whether operations continue smoothly when one endpoint fails also depends on retry behavior, client settings, and cluster state; listing multiple URLs does not guarantee requests will succeed if none of the servers are reachable.

In a Eureka cluster, the Eureka Servers must be configured with proper peer replication so the registry stays synchronized across nodes. Merely listing multiple URLs on the client does not create a cluster, does not configure replication automatically, and cannot fix a node that has lost connectivity to its peers.

In multi-region or multi-availability-zone setups, Eureka can use zone keys and corresponding region configuration to select the appropriate URL list. For a simple deployment with a single server group, `defaultZone` is usually the key you need. When designing for multiple regions, configure regions, availability zones, and service URLs consistently across clients and servers according to your actual architecture.

## 7. Relationship Between `defaultZone`, Registration, and Registry Fetching

`defaultZone` answers **where the client connects to Eureka Server**. The following two properties determine **what the client does with the registry**:

| Property | When enabled | When disabled |
|---|---|---|
| `eureka.client.register-with-eureka` | Registers the application's instance, renews its lease, and deregisters according to the client lifecycle | Does not register the application's instance with Eureka Server |
| `eureka.client.fetch-registry` | Fetches the registry to discover instances of other applications | Does not fetch the registry from Eureka Server |

Example configuration for a service that only provides APIs and does not call other services via discovery:

```yaml
eureka:
  client:
    service-url:
      defaultZone: http://eureka-server:8761/eureka/
    register-with-eureka: true
    fetch-registry: false
```

Example configuration for a component that only needs to discover other services:

```yaml
eureka:
  client:
    service-url:
      defaultZone: http://eureka-server:8761/eureka/
    register-with-eureka: false
    fetch-registry: true
```

In practice, a microservice typically both registers and fetches the registry, so both flags are usually enabled. A standalone Eureka Server typically disables both client features to avoid registering with or fetching the registry from itself; peer configuration in a cluster needs separate consideration.

## 8. Troubleshooting When Eureka Client Cannot Find the Server

When a client fails to register or cannot find services, troubleshoot in order from the URL down to the registry state:

1. **Check the effective configuration:** verify the active profile, the resolved `serviceUrl.defaultZone`, and that the `defaultZone` key is capitalized properly.
2. **Check the hostname and port:** from the exact environment where the client runs, verify that the hostname resolves and the Eureka Server port is reachable.
3. **Check the context path:** confirm the URL includes `/eureka/` or whatever context path the server uses. A wrong path can return `404` even when the host and port are reachable.
4. **Check the protocol:** use `http` or `https` matching the endpoint. For HTTPS, check the server certificate and JVM truststore if the client does not trust the server.
5. **Check Eureka Client logs:** look for messages about server connection, registration, heartbeats, and registry fetching; distinguish between DNS failures, timeouts, connection refused errors, and HTTP responses.
6. **Check server status:** confirm Eureka Server is running, its API endpoints are working, and the registry contains the expected instances.
7. **Check feature flags:** if the client does not appear on the dashboard, check `register-with-eureka`; if the client cannot find other services, check `fetch-registry` and the registry refresh interval.

Common symptoms:

| Symptom | Possible Cause | How to Check |
|---|---|---|
| `UnknownHostException` | Hostname cannot be resolved in the client environment | Check DNS, service name, and container networking |
| `Connection refused` | No process is listening at that host/port or the connection is rejected | Check the server, port mappings, and firewall |
| Timeout | Network path is blocked, server is overloaded, or endpoint is unresponsive | Check routing, firewall, server health, and server logs |
| HTTP `404` | Wrong context path or endpoint | Check `/eureka/` and context path configuration |
| HTTP `401` or `403` | Endpoint requires authentication or client lacks permissions | Check security policies and authentication configuration |
| Connection succeeds but services are missing | Client has not fetched the registry, application has not registered, or registry has not updated yet | Check both flags, instance state, and fetch interval |

You can test the endpoint from the client environment using an HTTP tool, for example:

```bash
curl -i http://eureka-server:8761/eureka/apps
```

This command is only a connectivity and registry-read test; exact output depends on security configuration, response format, and Eureka Server version. If the endpoint requires HTTPS or authentication, supply the corresponding options to the test tool. Being able to open the dashboard in a browser on your development machine does not prove that a production container can reach that URL as well.

## 9. Complete Example: Service Connecting to Eureka in a Docker Network

Suppose Eureka Server has the service name `eureka-server` listening on port `8761`, while `order-service` runs in another container on the same Docker network. The configuration on the `order-service` side can be:

```yaml
spring:
  application:
    name: order-service

server:
  port: 8081

eureka:
  client:
    service-url:
      defaultZone: "${EUREKA_SERVER_URL:http://eureka-server:8761/eureka/}"
    register-with-eureka: true
    fetch-registry: true
```

Here, the name `eureka-server` must match the DNS/service name provided by the Docker network. If you run the application directly on your development machine outside the Docker network, you can set `EUREKA_SERVER_URL` to a URL published to the host, such as `http://localhost:8761/eureka/` if that port is mapped.

After startup, you can verify in three steps: `order-service` logs show the client connecting and registering; the Eureka Server dashboard or registry API displays the `ORDER-SERVICE` instance; and a consumer with `fetch-registry: true` fetches the instance and can select it through discovery/load balancing.

## 10. Key Takeaways

- `eureka.client.serviceUrl.defaultZone` specifies the Eureka Server URL that Eureka Client connects to.
- Preserve the uppercase letter in the `defaultZone` map key; you can use `service-url` in YAML or `serviceUrl` in properties.
- The URL must be reachable from the client's runtime environment and must point to the exact context path of the Eureka API.
- `localhost` inside a container refers to that container itself; use a DNS/service name or routable hostname to connect to another container.
- You can specify multiple URLs for a zone, but you must configure peer replication and verify cluster retry/failover separately.
- `register-with-eureka` and `fetch-registry` are two independent capabilities; `defaultZone` only provides the connection address.

When `serviceUrl.defaultZone` is configured properly, Eureka Client can communicate with the registry. Whether an instance is registered, whether a consumer fetches the registry, and whether requests reach the right instance still depend on the feature flags, server health, network connectivity, and the application's load-balancing configuration.
