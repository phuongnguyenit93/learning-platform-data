# Publishing the Status Page, Health Address, and HTTPS Port

Eureka stores location information for each service instance and can also publish URLs so operators or other applications can access the instance's home page, status page, and health endpoint. With Spring Cloud Netflix Eureka Client, these URLs are configured through **eureka.instance** properties.

When an application runs over HTTPS, you need to publish the right secure port and protocol so consumers build valid URLs to the instance. At the same time, you must distinguish between the port serving business APIs and the Actuator management port if the application uses a separate management port. Misconfiguration can cause Eureka to display an unreachable address, or cause consumers to attempt HTTP calls to a service that only accepts HTTPS.

This article focuses on three tasks: publishing the status page URL, publishing the health-check URL, and declaring the HTTPS port in Eureka Client. It also clarifies the relationship between Actuator, the health status reported by Eureka Client, and TLS between the application and Eureka Server.

## 1. URLs That Eureka Can Publish

An instance can publish the following addresses:

| Property | Purpose | Example |
|---|---|---|
| Home page URL | Root page or landing page of the service | https://inventory.internal/ |
| Status page URL | Information/status page for operators | https://inventory.internal/actuator/info |
| Health check URL | Endpoint providing health information | https://inventory.internal/actuator/health |
| Service URL | Address and port consumers use to call the API | https://inventory.internal:8443 |

The home page, status page, and health URLs are published alongside the instance details in Eureka. They help dashboards or other components locate the corresponding endpoints. Simply declaring a URL does not mean Eureka Server will continuously poll that endpoint for health checks. The instance status update mechanism must be configured and understood separately.

Spring Cloud Netflix provides two ways to configure URLs:

- Use **url-path** properties when the URL can be constructed from the instance's host, port, and path.
- Use **url** properties when an absolute URL must be published, such as when endpoints run on a separate management port or sit behind a reverse proxy.

## 2. Publishing the Status Page and Health-Check URL

For a Spring Boot application using Actuator, the most common endpoints are:

- **/actuator/info:** provides application information; can serve as the status page.
- **/actuator/health:** provides overall health status.

The default paths can change if the application configures **management.endpoints.web.base-path**, **management.server.base-path**, or a servlet context path. Therefore, the published URL must match the actual endpoint.

### Configuring Relative Paths

If Actuator shares the same host and port as the service, you can declare relative paths:

~~~yaml
spring:
  application:
    name: inventory-service

management:
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: health,info

eureka:
  instance:
    status-page-url-path: /actuator/info
    health-check-url-path: /actuator/health
    home-page-url-path: /
~~~

In this example, Eureka Client builds the URLs from the instance details and the declared paths. The info and health endpoints must actually be enabled and reachable under the application's network configuration. Actuator only creates these endpoints when the appropriate dependency is present, typically **spring-boot-starter-actuator**.

If you change the base path—for example, setting it to **/manage**—update the paths accordingly:

~~~yaml
management:
  endpoints:
    web:
      base-path: /manage

eureka:
  instance:
    status-page-url-path: /manage/info
    health-check-url-path: /manage/health
~~~

Do not leave the default **/actuator/...** paths in place once the actual endpoints have moved to another path.

### Configuring Absolute URLs

When the status page or health endpoint lives on a different host, port, or path, declare absolute URLs:

~~~yaml
eureka:
  instance:
    status-page-url: https://inventory-01.internal:9443/actuator/info
    health-check-url: https://inventory-01.internal:9443/actuator/health
    home-page-url: https://inventory-01.internal:8443/
~~~

Absolute URLs are especially useful when:

- The management server runs on a separate port.
- The application sits behind a reverse proxy or ingress.
- The host accessed by consumers differs from the process's internal hostname.
- The published path includes a prefix added by a gateway or proxy.

The address must be reachable from wherever it will be used. Do not publish **localhost** if the Eureka Dashboard or consumers on other hosts need to access it, because localhost will point back to the caller's own machine.

## 3. Distinguishing the Status Page from Health Status

The status page and health check are related, yet serve two different purposes.

The **Status page URL** is a link for viewing application details or operational state. For example, **/actuator/info** can display build version, commit info, or configured release metadata. It does not necessarily reflect whether the application is fit to serve requests.

The **Health-check URL** is an endpoint providing health check results. With Actuator, **/actuator/health** returns an aggregated status from the configured HealthIndicators.

**Eureka instance status** is the status Eureka Client reports to the registry, such as UP, DOWN, OUT_OF_SERVICE, or another status depending on the mechanism. Publishing a health URL does not automatically mean Eureka Server actively polls that URL. If you want Actuator's status to be reflected in Eureka, you must enable Eureka Client's health-check integration.

~~~mermaid
flowchart TD
    APP["Spring Boot application"]
    APP --> INFO["Actuator /info"]
    APP --> HEALTH["Actuator /health"]
    HEALTH --> HC["HealthIndicator result"]
    HC -->|"eureka.client.healthcheck.enabled"| STATUS["Eureka Client instance status"]
    INFO --> META["Status page URL in Eureka metadata"]
    HEALTH --> URL["Health check URL in Eureka metadata"]
    STATUS --> REG[("Eureka Server")]
    META --> REG
    URL --> REG
~~~

To integrate Actuator's status with Eureka Client, configure:

~~~yaml
eureka:
  client:
    healthcheck:
      enabled: true
~~~

This property should be placed in **application.yml** or equivalent application configuration, not in **bootstrap.yml**. Placing it in the wrong configuration loading phase can cause the client to register before health status is properly initialized and publish an unintended status.

When integration is enabled, Eureka Client uses the application's health state to update the instance status via Spring Cloud Netflix's mechanism. This is distinct from merely publishing the health-check URL so dashboards or consumers know where the endpoint is.

### Choosing Appropriate HealthIndicators

Actuator can aggregate health from many components such as databases, disk space, or external dependencies. If the health endpoint depends on an external system, a dependency outage can mark the service unhealthy even if it can still handle some requests.

Clarify your health-check goals:

- **Liveness:** is the process still alive or does it need a restart?
- **Readiness:** is the instance ready to accept business requests?
- **Dependency health:** are dependent systems responding?
- **Registry status:** should consumers select this instance right now?

Avoid putting every dependency check into readiness if doing so pulls the entire service out of discovery while core capabilities still work. Select health indicator groups and published statuses according to your system's policy.

## 4. When the Management Server Uses a Separate Port

Spring Boot lets you run Actuator on a dedicated port via **management.server.port**. For example, business APIs run over HTTPS on port **8443**, while Actuator runs on port **9443**.

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: ${APP_KEYSTORE}
    key-store-password: ${APP_KEYSTORE_PASSWORD}
    key-store-type: PKCS12
    key-alias: inventory

management:
  server:
    port: 9443
    ssl:
      enabled: true
      key-store: ${APP_MANAGEMENT_KEYSTORE}
      key-store-password: ${APP_MANAGEMENT_KEYSTORE_PASSWORD}
      key-store-type: PKCS12
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: health,info

eureka:
  instance:
    non-secure-port-enabled: false
    secure-port-enabled: true
    secure-port: 8443
    home-page-url: https://inventory-01.internal:8443/
    status-page-url: https://inventory-01.internal:9443/actuator/info
    health-check-url: https://inventory-01.internal:9443/actuator/health
~~~

In this configuration:

- Port **8443** is the business API HTTPS port used by consumers.
- Port **9443** is the separate management port where Actuator serves info and health.
- Eureka advertises the service instance over secure port **8443**.
- The status page and health-check URLs are explicitly set to point to management port **9443**.

In this example, the management server also enables HTTPS via management.server.ssl configuration. Supply the separate keystore and password via a secret manager or environment variables, and ensure the certificate is valid for the hostname and port 9443. If the management port runs over HTTP, change the scheme in status-page-url and health-check-url to http and restrict access using an internal network or appropriate protection.

If the management server shares the same port as the API, you can use status-page-url-path and health-check-url-path instead of absolute URLs. If it uses a separate port, absolute URLs are usually easier to reason about because they explicitly state the host, scheme, and port.

## 5. Publishing the HTTPS Port to Eureka

When an instance serves only HTTPS, Eureka must be told that the service address should use the secure port. Common configuration:

~~~yaml
eureka:
  instance:
    non-secure-port-enabled: false
    secure-port-enabled: true
    secure-port: 8443
~~~

Meaning:

- **secure-port-enabled: true:** marks the instance's secure port as active.
- **secure-port: 8443:** declares the HTTPS port the instance uses.
- **non-secure-port-enabled: false:** does not publish the HTTP port as a valid service access port.

If the application serves both HTTP and HTTPS, you can configure both ports and their corresponding flags according to deployment policy. When you want consumers to use HTTPS only, do not leave metadata advertising an active HTTP port.

### Configuring TLS on the Spring Boot Application

An example TLS configuration:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: ${APP_KEYSTORE}
    key-store-password: ${APP_KEYSTORE_PASSWORD}
    key-store-type: PKCS12
    key-alias: inventory
~~~

Keystore locations and passwords should be injected from a secret manager or secure environment variables. Never commit passwords, private keys, or production keystores to the repository.

Eureka only publishes the port number and secure status; it does not enable TLS on the provider application itself. The provider must actually configure HTTPS with a valid certificate. If Eureka advertises 8443 while the application only listens for HTTP, consumers will fail to connect using the expected protocol.

## 6. Distinguishing HTTPS to the Service from HTTPS to Eureka Server

There are two independent TLS connections:

1. **Consumer to service instance:** governed by the provider's HTTPS configuration and the secure port properties in Eureka.
2. **Eureka Client to Eureka Server:** governed by the registry URL and the client's TLS/truststore configuration.

Example configuring a Eureka Server endpoint over HTTPS:

~~~yaml
eureka:
  client:
    service-url:
      defaultZone: https://eureka.internal:8761/eureka/
~~~

The defaultZone property specifies the address Eureka Client uses to communicate with Eureka Server. It does not make the advertised service instance use HTTPS. Conversely, setting secure-port-enabled on the instance does not enable HTTPS for the client's connection to the registry.

In environments using internal certificates or a private CA, the application's JVM must trust the server certificate. Configure a truststore and client certificate if your infrastructure requires mutual TLS. Verify hostname verification, the certificate chain, expiration dates, and secret read permissions at startup.

~~~mermaid
flowchart LR
    C["Order Service"] -->|"HTTPS to 8443"| I["Inventory Service"]
    I -->|"HTTPS registration/heartbeat"| E[("Eureka Server")]
    C -->|"HTTPS discovery query"| E
    M["Actuator management port 9443"] -.->|"Published health/status URL"| E
~~~

In the diagram, the connection from consumer to provider uses the HTTPS port published by the instance. The registry connection is a separate TLS stream. Management endpoints can live on a different port and be published via absolute URLs.

## 7. Paths, Context Path, and Reverse Proxies

Published URLs must match the paths that callers actually see. Several settings can alter paths:

- **server.servlet.context-path** adds a prefix for servlet applications.
- **management.endpoints.web.base-path** changes the Actuator prefix.
- A reverse proxy or ingress may add, strip, or rewrite prefixes.
- The management server may use a separate port or hostname.

For example, if an application has context path **/inventory** and Actuator base path **/manage**, the health endpoint may reside at **/inventory/manage/health** depending on how server and management contexts are configured. Verify the actual URL by sending a request from the consumer's or registry's network.

If a reverse proxy exposes an external address different from the application's internal address, you can use absolute status-page-url and health-check-url values to advertise URLs reachable by callers. Do not advertise an internal container hostname if consumers or the dashboard cannot resolve that hostname.

## 8. Protecting the Status Page and Health Endpoint

Actuator can expose version info, dependency states, and environment details. Do not leave all management endpoints open to the Internet.

A restricted exposure configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: when_authorized
~~~

Endpoint exposure and access authorization are two separate concerns. Spring Security, firewalls, security groups, or network policies must restrict who can invoke these endpoints. If the health endpoint is protected by authentication, ensure whatever performs the check has valid credentials. Never assume Eureka Server automatically holds credentials to call a health URL simply because the URL is registered.

Key principles:

- Expose only the endpoints that are strictly necessary.
- Do not leave env, configprops, heapdump, threaddump, or sensitive endpoints publicly accessible.
- Hide detailed health info when callers are unauthenticated.
- Restrict health endpoints to internal networks or protected proxies.
- Use TLS for transport carrying sensitive operational data.
- Never put passwords, tokens, or secrets into URLs or Eureka metadata.

## 9. Verifying Published URLs and Ports

After the provider starts, verify both the registry data and real network reachability.

1. Confirm the application is listening on the expected HTTP/HTTPS port.
2. Check Actuator info and health from a network reachable by the URL consumers.
3. Open the Eureka Dashboard or query the registry to inspect the service ID and instances.
4. Confirm statusPageUrl and healthCheckUrl point to the right scheme, host, port, and path.
5. Confirm the instance is marked secure and the HTTPS port matches the business API.
6. If using a separate management port, verify Actuator URLs point to that management port.
7. From a consumer, call the API over HTTPS and verify that the certificate is trusted.
8. If using HTTPS to Eureka Server, separately verify registry connectivity and truststore setup.

### Quick Diagnostic Table

| Symptom | Possible Cause | How to Fix |
|---|---|---|
| Status URL returns 404 | Wrong base path, context path, or URL path | Check the actual Actuator endpoint and the status-page-url-path property |
| Health URL is unreachable | Wrong host, management port, or firewall rule | Use an absolute URL and test from the right network |
| Eureka advertises HTTP even though the service only supports HTTPS | Secure port flag not enabled or non-secure port still published | Enable secure port, disable non-secure port if needed |
| Consumer HTTPS connection fails | Provider has not enabled SSL or certificate is invalid | Check server SSL, trust chain, and hostname |
| Eureka Client cannot connect to Eureka Server | Wrong registry URL, TLS, or truststore | Check defaultZone, CA, and registry certificate |
| Instance stays UP even though health endpoint fails | Health-check integration not enabled or health indicator does not reflect failure | Check eureka.client.healthcheck.enabled and Actuator config |
| Instance is DOWN even though API still works | Health indicator checks an unnecessary dependency or transient failure | Review readiness and HealthIndicators |

## 10. Configuration Principles

- Use status-page-url-path and health-check-url-path when endpoints share the same host/port and have stable paths.
- Use status-page-url and health-check-url when management port, hostname, or reverse proxy differs from the service address.
- Ensure Actuator endpoints are created, exposed, and accessible within the proper network scope.
- Distinguish between publishing a health URL and syncing health status via Eureka Client.
- Enable eureka.client.healthcheck.enabled in application configuration if you want Actuator health to update Eureka status.
- Enable secure-port-enabled and set secure-port when serving over HTTPS; disable the non-secure port if consumers should not use HTTP.
- Configure actual SSL on the provider; Eureka only stores port and URL metadata.
- Configure TLS/truststore for the Eureka Server connection independently from the service instance's TLS.
- Test URLs from the caller's network, not just from the provider's localhost.
- Protect management endpoints and never publish secrets in metadata.

When status URLs, health endpoints, and secure ports are published accurately, Eureka provides consistent metadata so operators can inspect instances and consumers can connect over the right protocol. Remember that URL metadata, client-reported health status, and TLS configuration are three related yet independent pieces; configuring each for its exact role prevents unreachable endpoints and accidental routing over HTTP.
