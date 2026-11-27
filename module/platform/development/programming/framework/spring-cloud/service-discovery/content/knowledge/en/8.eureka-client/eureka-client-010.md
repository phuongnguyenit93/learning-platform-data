# Eureka Client HTTP Connection Options by Version

## Objectives

After this lesson, you will be able to:

- Distinguish the HTTP transport Eureka Client uses to call Eureka Server from the HTTP client used to call other microservices.
- Recognize transport selection changes across Spring Cloud Netflix generations.
- Configure RestTemplate, RestClient, WebClient, or Jersey according to the version in use.
- Set connect timeout, connection-request timeout, and socket/read timeout under the right property namespace.
- Configure proxy, TLS, authentication, and customize the HTTP request factory.
- Verify the actual transport initialized by the application and troubleshoot common connection errors.

## 1. Where Does Eureka Client Use HTTP?

Eureka Client communicates with Eureka Server over HTTP for operations such as instance registration, heartbeats, metadata updates, and registry fetching. This HTTP layer is Eureka Client's internal transport.

This transport is separate from the HTTP client business code uses to call order-service, inventory-service, or external APIs. For instance, an application might use WebClient to call business APIs while Eureka Client still uses RestTemplate or RestClient to talk to the registry. Enabling eureka.client.webclient.enabled only selects the transport for Eureka Client; it does not automatically switch all HTTP calls in the application to WebClient.

Transports available across Spring Cloud Netflix versions:

- **JerseyClient:** transport associated with older Netflix Eureka generations.
- **RestTemplate:** synchronous transport based on Spring Web.
- **RestClient:** newer synchronous HTTP client in Spring Framework.
- **WebClient:** Spring WebFlux HTTP client supporting the reactive model.

Which transport gets selected depends on the Spring Cloud Netflix version, dependencies on the classpath, and configuration flags. Therefore, never copy a property from an article written for a different version without checking your project's release train.

## 2. HTTP Client Selection Differences Across Versions

The following table summarizes the behavior described in official Spring Cloud Netflix documentation. This reflects selection across release branches; actual classpath dependencies can still affect auto-configuration conditions.

| Spring Cloud Netflix Branch | Default Transport | Notable Options |
| --- | --- | --- |
| 2.2.x (Hoxton) | Jersey is the default in this branch's documentation. | Can exclude Jersey from dependencies so Spring Cloud configures RestTemplate. |
| 3.0.x | RestTemplate is the default per 3.0.3 documentation. | Jersey can be added as an alternative. |
| 4.1.x | RestTemplate is the default. | WebClient can be selected via eureka.client.webclient.enabled=true; Jersey is an optional choice if its dependency is added. |
| 4.2.x – 4.3.x | RestTemplate remains the default. | RestClient can be enabled via eureka.client.restclient.enabled=true or WebClient via eureka.client.webclient.enabled=true. |
| 5.0.x – 5.1.x | RestClient is the default described in current documentation. | WebClient is selected when required modules are present and eureka.client.webclient.enabled=true; Jersey can still be used if added. RestTemplate is no longer listed among transports in 5.x documentation. |

### 2.2.x Branch: Jersey by Default

In the Hoxton/2.2.x branch, Spring Cloud Netflix documentation describes Jersey as the default HTTP client. If you want to avoid Jersey dependencies, you can exclude the Jersey artifacts from the Eureka Client starter so Spring Cloud auto-configures a RestTemplate-based transport.

Maven example excluding Jersey:

~~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    <exclusions>
        <exclusion>
            <groupId>com.sun.jersey</groupId>
            <artifactId>jersey-client</artifactId>
        </exclusion>
        <exclusion>
            <groupId>com.sun.jersey</groupId>
            <artifactId>jersey-core</artifactId>
        </exclusion>
        <exclusion>
            <groupId>com.sun.jersey.contribs</groupId>
            <artifactId>jersey-apache-client4</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~~

This configuration is meant for projects on older branches. Do not apply these exclusions blindly to newer branches; inspect the dependency tree of your exact version.

### 3.0.x – 4.1.x Branches: RestTemplate by Default

The 3.0.3 documentation describes RestTemplate as the default, with Jersey as an alternative when its dependency is added. The 4.1.x documentation continues using RestTemplate by default while explaining how to select WebClient using spring-boot-starter-webflux and the following flag:

~~~~yaml
eureka:
  client:
    webclient:
      enabled: true
~~~~

When an application has both Spring Web and WebFlux, this flag instructs Spring Cloud to choose WebClient for Eureka communication. If not enabled, RestTemplate remains the default in this branch's documentation.

### 4.2.x – 4.3.x Branches: Adding RestClient

The 4.2.x and 4.3.x branches add support for RestClient, though RestTemplate remains the default unless another transport is enabled.

To select RestClient, Spring Web must be on the classpath and you set:

~~~~yaml
eureka:
  client:
    restclient:
      enabled: true
~~~~

To select WebClient, add Spring WebFlux and set:

~~~~yaml
eureka:
  client:
    webclient:
      enabled: true
~~~~

According to the documented precedence order, when both Spring Web and WebFlux are present, webclient.enabled=true selects WebClient. If that condition is not met and restclient.enabled=true, RestClient is selected. If neither flag is enabled, RestTemplate is selected.

If Jersey dependencies are present and enabled, inspect auto-configuration conditions and transport selection logs. When you want to use a Spring HTTP client, you can explicitly set eureka.client.jersey.enabled=false to avoid Jersey being chosen unexpectedly.

### 5.x Branch: RestClient by Default

In Spring Cloud Netflix 5.0.x and 5.1.x documentation, Eureka Client uses RestClient, WebClient, or Jersey. RestTemplate is no longer listed among transports in this branch.

With Spring Boot 4, dependencies are modularized. If using only RestClient, add:

~~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-restclient")
}
~~~~

If you want to use WebClient, add the module:

~~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-webclient")
}
~~~~

When both modules are present, enable the flag below to pick WebClient; otherwise, RestClient is the documented default:

~~~~yaml
eureka:
  client:
    webclient:
      enabled: true
~~~~

Artifact names in the 5.x branch differ from spring-boot-starter-web and spring-boot-starter-webflux commonly seen in Spring Boot 3.x projects. Check dependency management for your Spring Boot and Spring Cloud release train before adding modules.

## 3. Choosing Transports and Dependencies Correctly

Before changing transports, inspect the Spring Boot and Spring Cloud Netflix versions managed by the BOM. Do not upgrade spring-cloud-starter-netflix-eureka-client individually or force a custom Spring Web version just to pull in a newer transport.

A safe workflow:

1. Identify the Spring Cloud release train and exact Spring Cloud Netflix version.
2. Inspect the dependency tree to see whether Jersey, Spring Web, WebFlux, RestClient, or WebClient is on the classpath.
3. Cross-check with your release branch's transport selection table.
4. Add only the required modules and set explicit selection flags if multiple transports exist.
5. Start the application and check the logs to see which transport the Eureka HTTP Client actually uses.
6. Test registration, heartbeats, registry fetching, and behavior when Eureka Server is temporarily unavailable.

Do not pull in WebFlux solely to use WebClient for Eureka if the application does not need the reactive ecosystem. Likewise, do not keep Jersey around simply because a legacy transitive dependency brought it in without any compatibility reason.

## 4. Configuring Eureka Server URLs and Lists

The Eureka Server address is configured via eureka.client.service-url. The defaultZone key is a case-sensitive map key; preserve camelCase:

~~~~yaml
eureka:
  client:
    service-url:
      defaultZone: https://eureka-a.internal:8761/eureka/,https://eureka-b.internal:8761/eureka/
~~~~

You can declare multiple URLs so the client has fallback Eureka endpoints. Ensure every URL has the right scheme, hostname, port, and context path for the environment. For production environments, use HTTPS when infrastructure requires traffic protection.

defaultZone specifies where the client connects; it does not choose RestTemplate, RestClient, or WebClient. The two configuration groups serve different roles.

## 5. Timeouts: Using the Right Properties per Transport and Version

Timeouts govern how long the application waits when establishing connections and reading responses from Eureka Server. Setting them too high can stall startup or background tasks for a long time when the network fails. Setting them too low can trigger false errors on high-latency networks.

Three common timeout settings:

| Property | Meaning |
| --- | --- |
| connect-timeout | Maximum time to establish a TCP connection to Eureka Server. |
| connect-request-timeout | Time to wait for obtaining a connection from the connection pool or waiting for a connection lease request. |
| socket-timeout | Time to wait for response data after the connection is established; commonly understood as read timeout. |

Spring Cloud Netflix documentation notes that the default for these HTTP timeouts is 180,000 ms (3 minutes) across the Spring transports mentioned. Set explicit values suited to your application's latency budget and network characteristics instead of relying on long defaults.

### 4.1.x: RestTemplate Timeouts

For the 4.1.x branch, use eureka.client.rest-template-timeout. All values are in milliseconds:

~~~~yaml
eureka:
  client:
    rest-template-timeout:
      connect-timeout: 5000
      connect-request-timeout: 8000
      socket-timeout: 10000
~~~~

This property group configures the RestTemplate transport. Do not use it expecting to control WebClient or a Jersey transport.

### 4.2.x – 4.3.x: RestTemplate and RestClient Timeouts

The 4.2.x–4.3.x branches have two separate configuration groups. If using RestTemplate:

~~~~yaml
eureka:
  client:
    rest-template-timeout:
      connect-timeout: 5000
      connect-request-timeout: 8000
      socket-timeout: 10000
~~~~

If using RestClient:

~~~~yaml
eureka:
  client:
    restclient:
      timeout:
        connect-timeout: 5000
        connect-request-timeout: 8000
        socket-timeout: 10000
~~~~

Both groups use milliseconds. Pick the group matching your actual transport. Configuring rest-template-timeout does not replace restclient.timeout, and vice versa.

### 5.x: Timeouts Under the eureka.client.timeout Namespace

In 5.1.x documentation, the timeout properties are published under eureka.client.timeout:

~~~~yaml
eureka:
  client:
    timeout:
      connect-timeout: 5000
      connect-request-timeout: 8000
      socket-timeout: 10000
~~~~

Values are in milliseconds. Do not copy rest-template-timeout or restclient.timeout directly from a 4.x project into a 5.x project without checking the target version's configuration properties.

### Choosing Timeout Values

The 5/8/10-second values in these examples are illustrative starting points, not universal standards for every system. When setting timeouts:

- Connect timeout should be shorter than the overall deadline for registration or registry fetching.
- Connection-request timeout should account for pool limits and concurrent requests.
- Socket timeout must be sufficient for large registry responses, especially during full registry fetches.
- Combined timeouts should align with retry/backoff policies so a network failure does not drag background tasks out indefinitely.
- Test under healthy registry conditions, high load, slow networks, and unreachable registries.

## 6. Connection Pools and Idle Connections

Eureka Client typically reuses HTTP connections for heartbeats and registry queries. Pooling reduces the overhead of opening new connections, though limits should be sized appropriately for concurrency and the number of Eureka Servers.

Several legacy properties in configuration properties may appear across branches:

| Property | Meaning | Unit |
| --- | --- | --- |
| eureka.client.eureka-connection-idle-timeout-seconds | Idle duration before a connection may be closed. | Seconds |
| eureka.client.eureka-server-total-connections | Total connection limit across all Eureka Servers. | Connections |
| eureka.client.eureka-server-total-connections-per-host | Connection limit per Eureka Server host. | Connections |
| eureka.client.eureka-server-connect-timeout-seconds | Connect timeout for the legacy transport group. | Seconds |
| eureka.client.eureka-server-read-timeout-seconds | Read timeout for the legacy transport group. | Seconds |

These legacy properties should not be treated as drop-in replacements for the RestTemplate/RestClient timeout namespaces in all versions. Applicability depends on the auto-configured transport and implementation. When moving to RestClient or WebClient, check the configuration properties and documentation for your exact version; never assume old pool limits automatically control new pools.

In environments where firewalls or NAT devices drop idle connections, pool idle durations must stay compatible with infrastructure timeouts. If a firewall drops connection state before the client notices, the client may fail on a half-closed connection. Monitor reset/closed connection logs and test registry refreshes to diagnose such issues.

## 7. Proxy, TLS, and HTTP Authentication

### HTTP Proxy

If Eureka Server is only reachable through a proxy, configure the supported proxy properties:

~~~~yaml
eureka:
  client:
    proxy-host: proxy.internal
    proxy-port: 8080
    proxy-user-name: eureka-client
    # proxy-password loaded from a secret store or environment variable
~~~~

Never place real passwords in committed configuration files. Confirm the proxy allows connections to all peer URLs and does not block Eureka API paths.

### TLS and Mutual TLS

When Eureka Server requires client certificates, enable TLS and configure the keystore/truststore:

~~~~yaml
eureka:
  client:
    tls:
      enabled: true
      key-store: /run/secrets/eureka-client.p12
      key-store-type: PKCS12
      key-store-password: LOAD_FROM_SECRET_STORE
      key-password: LOAD_FROM_SECRET_STORE
      trust-store: /run/secrets/eureka-trust.p12
      trust-store-type: PKCS12
      trust-store-password: LOAD_FROM_SECRET_STORE
~~~~

If no truststore is specified, Spring Cloud Netflix documentation notes that the JVM default truststore is used. The default keystore and truststore type is documented as PKCS12. Manage passwords through a secret store; never commit real secrets.

TLS protects the transport channel. With mutual TLS, the client presents a certificate so the server can authenticate the connection identity. Certificates, hostnames, and trust chains must match the Eureka Server configuration.

### HTTP Basic Authentication

Eureka documentation supports Basic Authentication when the defaultZone URL includes user/password credentials. However, credentials embedded in URLs can leak into logs, rendered configs, or observability tools. Use secret injection and protect configuration access.

Eureka has a limitation regarding per-server-URL credentials: Spring Cloud Netflix documentation notes that only the first set of credentials found is used. If you need more complex authentication, you can customize Eureka Client filters via DiscoveryClientOptionalArgs and ClientFilter, depending on the API supported by your branch.

## 8. Customizing the HTTP Request Factory

With RestTemplate/RestClient in supported branches, you can customize ClientHttpRequestFactory via the EurekaClientHttpRequestFactorySupplier bean. This is useful when tuning Apache HttpClient 5, connection pools, or request configuration according to infrastructure policies.

Spring Cloud Netflix 4.2.x/4.3.x and current documentation illustrate a hook for customizing Apache HttpClient 5:

~~~~java
@Configuration
public class EurekaHttpConfiguration {

    @Bean
    EurekaClientHttpRequestFactorySupplier.RequestConfigCustomizer
            requestConfigCustomizer() {
        return builder -> builder.setProtocolUpgradeEnabled(false);
    }
}
~~~~

This is a RequestConfig customization example; it is not mandatory for every application. Only add a customizer when you have a specific requirement and verify the API classes in your exact version.

Documentation also notes that if a suitable builder bean exists in the ApplicationContext, Eureka Client may use that builder to construct its underlying HTTP client. Consequently, when an application declares both a plain builder and an `@LoadBalanced` builder, check which bean gets injected into the Eureka transport. Never let interceptors or load-balancing settings intended for business calls accidentally apply to registry requests.

For WebClient, configure WebClient.Builder or its connector according to the Spring WebFlux and Spring Boot APIs. RestTemplate/RestClient timeout properties do not automatically apply to WebClient.

## 9. Verifying the Actual Transport at Startup

Do not rely on YAML alone to conclude which transport is active. Auto-configuration also depends on dependencies and bean conditions.

Verification steps:

1. Check the resolved spring-cloud-starter-netflix-eureka-client version from the BOM.
2. Inspect the dependency tree to confirm whether Jersey, Spring Web, WebFlux, or RestClient/WebClient modules are present.
3. Check eureka.client.jersey.enabled, eureka.client.restclient.enabled, and eureka.client.webclient.enabled if supported by your branch.
4. Read startup logs for transport messages—for example, whether the Eureka HTTP Client uses RestTemplate, RestClient, WebClient, or Jersey.
5. If unclear, run the application with auto-configuration debug logging or inspect bean condition evaluations with appropriate tooling.
6. Confirm the client registers, sends heartbeats, and fetches the registry once the transport is initialized.

You can use separate test configurations for each transport, but avoid toggling multiple flags at once and guessing the outcome. Change one option per test while keeping the URL and server environment constant for comparison.

## 10. Common Errors

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| ClassNotFoundException or missing HTTP client class | Missing corresponding module or artifact from the wrong Spring Boot generation. | Inspect the dependency tree and artifact names for 4.x/5.x branches. |
| Application still uses RestTemplate despite adding WebClient | eureka.client.webclient.enabled not set, or WebFlux missing from classpath. | Check the property and WebFlux/WebClient modules. |
| 4.2/4.3 does not switch to RestClient | eureka.client.restclient.enabled not set or Spring Web missing. | Check the flag and resolved dependencies. |
| Jersey is still selected unexpectedly | Jersey is on the classpath and the Jersey flag remains enabled. | Check dependency tree; set eureka.client.jersey.enabled=false if wanting a Spring HTTP client. |
| Timeout properties have no effect | Using the wrong version namespace or configuring the wrong transport. | Cross-check 4.1, 4.2/4.3, and 5.x; verify the active transport. |
| Connect timeout error | Wrong hostname/port, DNS, firewall, proxy, or server not running. | Test name resolution and TCP connectivity from the application's environment. |
| Socket/read timeout error | Slow server response, large registry payload, or unstable network. | Measure response times, check server logs, and tune timeouts carefully. |
| SSL handshake error | Truststore missing CA, expired certificate, hostname mismatch, or bad client certificate. | Check certificate chain, SANs, expiration, and mutual TLS settings. |
| HTTP 401/403 | Wrong credentials or server authentication/CSRF policy. | Check security configuration and client permissions. |
| Connections frequently dropped when idle | Firewall/NAT closes connections before pool timeout. | Align idle timeouts and watch for connection resets. |
| Client registers but registry fetch fails | Transport succeeds on some requests but is blocked on another endpoint or payload. | Check access permissions, proxy routing, fetch logs, and Eureka Server responses. |

## 11. Configuration Selection Checklist

- [ ] Identified compatible Spring Cloud Netflix and Spring Boot versions.
- [ ] Selected transport according to your release branch's documentation.
- [ ] Dependencies include only the required HTTP client modules.
- [ ] No unintended legacy Jersey artifacts remain on the classpath.
- [ ] defaultZone points to the right endpoint and preserves defaultZone camelCase.
- [ ] Timeouts use the right namespace and millisecond/second units.
- [ ] Connection pool settings match peer count and registration/fetch traffic.
- [ ] Proxy, TLS, and authentication match actual infrastructure.
- [ ] Secrets are loaded from a secret store, never committed to the repository.
- [ ] Startup logs confirm the expected transport was selected.
- [ ] Tested registration, heartbeats, registry fetching, and connection loss scenarios.
- [ ] Verified configuration does not inadvertently affect HTTP clients used for business requests.

## Key Takeaways

- Eureka Client's HTTP transport serves only communication with Eureka Server; it is not the application's general-purpose HTTP client.
- 2.2.x used Jersey by default in older docs; 3.0.x–4.1.x default to RestTemplate; 4.2.x–4.3.x add RestClient as an option; 5.x switches the default to RestClient.
- eureka.client.webclient.enabled selects WebClient for Eureka communication when required dependencies are on the classpath.
- Timeout properties vary by version: rest-template-timeout, restclient.timeout, or eureka.client.timeout.
- Timeout values in Spring HTTP client groups use milliseconds; legacy properties ending in -seconds use seconds.
- Proxy, TLS, authentication, and connection pooling should always be verified alongside the actual active transport.
- Always confirm the active transport via the dependency tree and startup logs, not merely by reading YAML files.

## Official References

- [Spring Cloud Netflix 2.2.8 – Eureka Client](https://docs.spring.io/spring-cloud-netflix/docs/2.2.8.RELEASE/reference/html/)
- [Spring Cloud Netflix 3.0.3 – Eureka Client](https://docs.spring.io/spring-cloud-netflix/docs/3.0.3/reference/html/)
- [Spring Cloud Netflix 4.1 – Features](https://docs.spring.io/spring-cloud-netflix/reference/4.1/spring-cloud-netflix.html)
- [Spring Cloud Netflix 4.2 – Features](https://docs.spring.io/spring-cloud-netflix/reference/4.2/spring-cloud-netflix.html)
- [Spring Cloud Netflix 4.3 – Features](https://docs.spring.io/spring-cloud-netflix/reference/4.3/spring-cloud-netflix.html)
- [Spring Cloud Netflix 5.1 – Features](https://docs.spring.io/spring-cloud-netflix/reference/5.1/spring-cloud-netflix.html)
- [Spring Cloud Netflix 5.1 – Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/5.1/configprops.html)
