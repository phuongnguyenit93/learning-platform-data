# Artifact, Starter, and Configuration Namespace Changes

Spring Cloud Gateway is the entry point for microservices, where route predicates select requests, filter chains transform requests/responses, and components such as service discovery, load balancer, security, circuit breaker, and observability support operations. When upgrading the **SPRING_CLOUD_GATEWAY** module, check both Maven/Gradle dependencies and configuration namespaces together. A project may compile after changing versions yet still start up with old configuration, skip routes, or alter forwarded header behavior.

Starting with Spring Cloud 2025.0, Spring Cloud Gateway standardized module and starter names to distinguish the two usage models (**Server** and **ProxyExchange**) as well as the two web stacks (**WebFlux** and **WebMVC**). The old artifacts are marked deprecated and may emit warnings at application startup. At the same time, configuration prefixes were moved per module. Therefore, the upgrade must be executed as a coordinated change across dependencies, properties, and behavioral tests.

## Distinguish Modules Before Choosing Artifacts

Before changing dependency names, identify which model the application uses:

- **Gateway Server WebFlux**: a gateway that routes via route predicates and filter chains on Spring WebFlux/Reactor. This is the reactive option, using the Netty runtime provided by Spring Boot; it does not run inside a traditional Servlet container or use WAR packaging.
- **Gateway Server WebMVC**: a gateway server built on Spring MVC and the Servlet stack. Choose this module when the application architecture uses MVC.
- **Gateway ProxyExchange WebFlux/WebMVC**: a library that supports programmatic proxy exchange inside controllers or application handlers. This is not a drop-in starter replacement for a Gateway Server that declares routes via properties.

The new names make dependencies explicitly state the gateway type and web stack. Do not switch from WebFlux to WebMVC merely because the new artifact contains `webmvc`; that is an architectural change that can entail differences in runtime, filters, APIs, and how tests are written.

## Artifact and Starter Rename Mapping

The names below reflect the mapping published in the Spring Cloud 2025.0 release notes:

| Old artifact | New artifact | Use case |
|---|---|---|
| `spring-cloud-gateway-server` | `spring-cloud-gateway-server-webflux` | Gateway Server WebFlux implementation module |
| `spring-cloud-gateway-server-mvc` | `spring-cloud-gateway-server-webmvc` | Gateway Server WebMVC implementation module |
| `spring-cloud-starter-gateway` | `spring-cloud-starter-gateway-server-webflux` | Starter for Gateway Server WebFlux |
| `spring-cloud-starter-gateway-mvc` | `spring-cloud-starter-gateway-server-webmvc` | Starter for Gateway Server WebMVC |
| `spring-cloud-gateway-webflux` | `spring-cloud-gateway-proxyexchange-webflux` | ProxyExchange on WebFlux |
| `spring-cloud-gateway-mvc` | `spring-cloud-gateway-proxyexchange-webmvc` | ProxyExchange on WebMVC |

The Group ID for these Spring Cloud dependencies remains `org.springframework.cloud`. When an application uses a starter, declaring only the corresponding starter is usually sufficient; do not add the implementation module directly if the starter already brings it in. Declare module-level artifacts only when the project has an explicit reason to manage dependencies that way.

## Managing Versions with the Spring Cloud BOM

Do not set an arbitrary Gateway version separate from the Spring Cloud Release Train. Select the release train compatible with the application's Spring Boot version per the official compatibility matrix, then import the BOM so Spring Cloud modules share a aligned set of versions.

Maven example with Gateway Server WebFlux:

```xml
<properties>
    <spring-cloud.version>2025.0.x</spring-cloud.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>
</dependencies>
```

`2025.0.x` in the example is a placeholder to be replaced with the specific release version chosen by the project; do not copy this literal string into your build. If the application uses Gateway Server WebMVC, replace the starter with `spring-cloud-starter-gateway-server-webmvc`. With Gradle, apply the same principle by importing the BOM via your project's dependency management/platform mechanism and do not declare individual Gateway versions.

After changing dependencies, inspect the dependency tree to catch old artifacts still pulled in transitively. An internal library or another starter might still depend on the old name, so updating only the direct dependency line is not enough to conclude the upgrade is complete.

## Migrating Configuration Namespaces

Spring Cloud 2025.0 changed configuration prefixes to match the new module names. Find and migrate properties across every configuration source used by the application, including `application.yml`, `application-*.yml`, `.properties` files, Config Server, environment variables, Helm values, ConfigMaps, test fixtures, and deployment manifests.

| Module | Old prefix | New prefix |
|---|---|---|
| Gateway Server WebFlux | `spring.cloud.gateway.*` | `spring.cloud.gateway.server.webflux.*` |
| Gateway Server WebMVC | `spring.cloud.gateway.mvc.*` | `spring.cloud.gateway.server.webmvc.*` |
| ProxyExchange WebFlux | `spring.cloud.gateway.proxy.*` | `spring.cloud.gateway.proxy-exchange.webflux.*` |
| ProxyExchange WebMVC | `spring.cloud.gateway.proxy.*` | `spring.cloud.gateway.proxy-exchange.webmvc.*` |

The suffix following the prefix is preserved for the corresponding property, though you should still check the target release train documentation because certain properties may change or be removed independently of the prefix rename.

For example, Gateway Server WebFlux configuration before upgrading:

```yaml
spring:
  cloud:
    gateway:
      enabled: true
      routes:
        - id: orders-api
          uri: lb://orders-service
          predicates:
            - Path=/api/orders/**
          filters:
            - StripPrefix=1
      discovery:
        locator:
          enabled: true
      httpclient:
        connect-timeout: 2000
```

After migrating to the new namespace:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          enabled: true
          routes:
            - id: orders-api
              uri: lb://orders-service
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
          discovery:
            locator:
              enabled: true
          httpclient:
            connect-timeout: 2000
```

In the example, the route still has the same `id`, URI, predicate, filter, and timeout. The change is in the configuration prefix location. For Gateway Server WebMVC, move the property group from `spring.cloud.gateway.mvc` to `spring.cloud.gateway.server.webmvc`. For ProxyExchange, choose the right `proxy-exchange.webflux` or `proxy-exchange.webmvc` branch matching the application's web stack.

## Using Properties Migrator During the Transition

The Spring Cloud 2025.0 release notes suggest using `spring-boot-properties-migrator` to support old prefixes during the transition period. You can temporarily add this dependency to the runtime classpath to receive diagnostics for legacy properties at startup and assist migration.

Maven example:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-properties-migrator</artifactId>
    <scope>runtime</scope>
</dependency>
```

Read all startup messages, migrate the reported properties to the new prefixes, and restart the application. Once finished, remove `spring-boot-properties-migrator` from the build. This is a temporary migration aid and should not be kept long-term as a substitute for updating source configurations.

Do not rely solely on the application starting successfully. Verify actual routes through Actuator or integration tests, as old properties might no longer drive the new module the way the project expects.

## Auditing Forwarded and X-Forwarded Header Changes

A behavioral change that must be reviewed when upgrading is handling `Forwarded` and `X-Forwarded-*` headers. Per the Spring Cloud 2025.0 release notes, this feature is disabled by default in the corresponding fix releases to avoid trusting headers sent by unidentified sources.

If Gateway receives traffic through an ingress, reverse proxy, or load balancer and needs these headers to determine the host, scheme, or client address, you must explicitly configure trusted proxies using a regular expression:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          trusted-proxies: '10\.0\.0\..*'
```

For Gateway Server WebMVC, the corresponding property is `spring.cloud.gateway.server.webmvc.trusted-proxies`. Replace the sample expression with the actual address range or pattern of proxies under your control. Do not use a pattern that allows every source such as `.*`, because client requests can spoof forwarded headers and corrupt host, scheme, or IP information used by the application for security and logging.

After upgrading, test request flows through the real ingress/proxy in a staging environment. Confirm that Gateway trusts headers only from declared proxies and downstream receives the `Forwarded`/`X-Forwarded-*` values as designed.

## Controlled Upgrade Process

Perform each step in order so you can pinpoint the cause if build or runtime behavior changes:

1. **Capture baseline**: record the Spring Boot version, Spring Cloud Release Train, active artifacts, route configuration, filters, discovery, load balancer, security, and forwarded headers. Record representative test requests along with their current results.
2. **Choose the target release train**: check the Spring Boot/Spring Cloud compatibility table and release notes of intermediate versions. Do not jump across a major release without reading breaking changes of the relevant release trains.
3. **Update dependencies**: import the compatible BOM, switch to the new starter/module matching WebFlux, WebMVC, or ProxyExchange, and inspect the dependency tree to eliminate unintended deprecated artifacts.
4. **Update property prefixes**: migrate namespaces across all configuration sources. Use Properties Migrator temporarily if needed to diagnose old keys, then remove the helper dependency.
5. **Review security and proxies**: configure `trusted-proxies` when forwarded headers are needed; re-check Spring Security, TLS termination, CORS, and headers added by ingress.
6. **Run tests**: verify route predicates, filter chains, path/header transformations, service discovery, `lb://` load balancing, rate limiting, circuit breakers, retries, timeouts, TLS, and metrics/tracing.
7. **Trial deployment and observation**: deploy to staging or a limited set of instances; compare status codes, upstreams, latency, logs, and metrics against the baseline before rolling out broadly.

## Commands to Verify Dependencies and Configuration

With Maven, inspect the Gateway dependency tree:

```bash
mvn dependency:tree -Dincludes=org.springframework.cloud
```

With Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Search for old prefixes in the repository with a text search tool, for example:

```bash
rg -n "spring\.cloud\.gateway(\.mvc|\.proxy)?\." .
```

The search command only covers files in the current repository. Check Config Server, secret/config stores, environment variables, and deployment manifests separately if they are managed elsewhere. After making changes, re-run the search to confirm old keys have been handled or have a documented compatibility reason.

## Common Post-Upgrade Issues

| Symptom | Possible cause | Resolution |
|---|---|---|
| Build cannot find old starter or warns of deprecated artifact | Dependency not updated to new name or mismatched release train | Pick the right release train, update starter/module per the mapping table, and check the dependency tree |
| Application starts but routes do not appear | YAML still uses old prefix or property is placed under the wrong WebFlux/WebMVC branch | Move namespace to match the active module, check effective config and routes via Actuator |
| Route exists but requests go to the wrong upstream | Route/filter changed unexpectedly or new configuration was not loaded | Compare route id, URI, predicates, filters, and route ordering against baseline |
| Host, scheme, or client IP changes after upgrade | Forwarded headers are no longer trusted by default or trusted proxy is misconfigured | Identify real proxies and set appropriate `trusted-proxies`; verify headers at ingress and downstream |
| `ClassNotFoundException` or `NoSuchMethodError` | Spring Cloud/Spring Boot modules are on mismatched versions or old dependencies remain on the classpath | Use a compatible BOM, remove duplicate dependencies, and inspect the runtime dependency tree |
| ProxyExchange does not behave like Gateway Server | Picked ProxyExchange artifact instead of Server starter or vice versa | Determine whether the application needs route declarations or programmatic proxy exchange, then pick the right module |

## Pre-Completion Checklist

- [ ] Spring Boot and Spring Cloud Release Train are within the compatibility matrix.
- [ ] Starter/module has been renamed to match WebFlux, WebMVC, or ProxyExchange.
- [ ] No deprecated artifacts remain outside intentional transitional cases.
- [ ] Configuration prefixes have been migrated across files, Config Server, environment variables, and deployment configs.
- [ ] Properties Migrator has been removed after resolving warnings.
- [ ] `trusted-proxies` accurately reflects trusted proxies if the application uses Forwarded headers.
- [ ] Routes, filters, discovery, load balancing, security, resilience, TLS, and observability have been tested.
- [ ] Staging matches baseline results before full rollout.

## References

- [Spring Cloud 2025.0 Release Notes — Spring Cloud Gateway breaking changes](https://github.com/spring-cloud/spring-cloud-release/wiki/Spring-Cloud-2025.0-Release-Notes): module/starter rename table, property prefixes, and trusted proxies notes.
- [How to Include Spring Cloud Gateway](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/starter.html): Gateway Server WebFlux starter and runtime requirements.
- [Spring Cloud Gateway Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/configprops.html): property list by WebFlux and WebMVC namespaces.

When upgrading Spring Cloud Gateway, choose the right module type first, align artifacts with the release train, migrate all configuration namespaces, and re-verify behavior at the proxy boundary. These are essential steps so that route predicates, filter chains, service discovery, and security mechanisms continue operating properly after dependency and property renames.
