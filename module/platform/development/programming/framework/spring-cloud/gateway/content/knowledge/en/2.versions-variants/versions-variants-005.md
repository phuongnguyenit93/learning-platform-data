# Cross-Referencing Starter Names and Configuration Prefixes Across Spring Cloud Gateway Versions

## 1. Why Must Both Starters and Configuration Prefixes Be Cross-Referenced?

**Spring Cloud Gateway** is the API Gateway of the Spring ecosystem, used to route requests to microservices via **route predicates**, apply **filter chains** to modify paths/headers, integrate with **service discovery**, and add mechanisms such as authentication, rate limiting, circuit breakers, retries, TLS, and traffic observability. During an upgrade, a configuration file may still be valid YAML yet no longer be read by Gateway because **the dependency name or configuration namespace has changed**.

Distinguish three layers of information:

1. **Spring Boot / Spring Cloud release train / Spring Cloud Gateway**: the version trio that must be compatible with each other. For example, Spring Cloud `2025.0.x` manages Gateway `4.3.x`, while `2025.1.x` manages Gateway `5.0.x`.
2. **Starter**: the Maven/Gradle artifact declared to build the Gateway application, such as `spring-cloud-starter-gateway-server-webflux`.
3. **Configuration prefix (property prefix)**: the path Spring Boot uses to bind properties, such as `spring.cloud.gateway.server.webflux.routes`.

> **Key takeaway:** starting from Gateway **4.3** (Spring Cloud **2025.0**), the new starter names and namespaces explicitly describe the **Server/Proxy Exchange** role and **WebFlux/Web MVC** technology. Old names were marked deprecated in the 4.3 transitional line; Gateway 5.x uses the new naming set. You cannot conclude a configuration key is still active simply because the application starts cleanly.

Lesson goal: identify the right dependency by version and web stack; accurately update prefixes for routes, filters, discovery, and operational properties; read legacy configurations and avoid ending up with a Gateway that creates no routes after an upgrade.

## 2. Cross-Reference Table by Version Line

The starters in the table share the `groupId` **`org.springframework.cloud`**. The prefix columns apply to **Gateway Server** configuration in `application.yml`/`application.properties`, not general Spring Boot prefixes.

| Gateway line | Typical Spring Cloud release train | Server WebFlux: starter | Server WebFlux: route prefix | Server Web MVC: starter and prefix |
|---|---|---|---|---|
| 2.x–3.1.x | Spring Boot 2 era trains, including `2021.0.x` for 3.1 | `spring-cloud-starter-gateway` | `spring.cloud.gateway.routes` | No official **Server MVC** variant in these lines |
| 4.0.x | `2022.0.x` | `spring-cloud-starter-gateway` | `spring.cloud.gateway.routes` | No Server MVC yet (introduced in 4.1) |
| 4.1.x–4.2.x | `2023.0.x`–`2024.0.x` | `spring-cloud-starter-gateway` | `spring.cloud.gateway.routes` | `spring-cloud-starter-gateway-mvc`, prefix `spring.cloud.gateway.mvc.*` |
| **4.3.x** | **`2025.0.x`** | **`spring-cloud-starter-gateway-server-webflux`** | **`spring.cloud.gateway.server.webflux.routes`** | **`spring-cloud-starter-gateway-server-webmvc`**, prefix **`spring.cloud.gateway.server.webmvc.*`** |
| **5.0.x** | **`2025.1.x`** | `spring-cloud-starter-gateway-server-webflux` | `spring.cloud.gateway.server.webflux.routes` | `spring-cloud-starter-gateway-server-webmvc`, prefix `spring.cloud.gateway.server.webmvc.*` |
| **5.1.x** | **`2026.0.x`** | `spring-cloud-starter-gateway-server-webflux` | `spring.cloud.gateway.server.webflux.routes` | `spring-cloud-starter-gateway-server-webmvc`, prefix `spring.cloud.gateway.server.webmvc.*` |

Key milestones to remember:

- Gateway **3.1** belongs to the Spring Boot 2 generation; Gateway **4.x** belongs to the Spring Boot 3 generation; Gateway **5.x** belongs to the Spring Boot 4 generation. Official examples: Spring Cloud `2025.0` is compatible with Spring Boot **3.5**, `2025.1` uses Spring Boot **4.x**, and `2026.0.0` released alongside Spring Boot **4.2.0**.
- Gateway **4.1** introduced Server MVC running on a Servlet stack (such as Tomcat/Jetty), while Server WebFlux uses Reactor Netty. They are two Gateway Server variants with different processing models.
- Gateway **4.3** is the rename milestone: old starters were marked deprecated, and old prefixes moved under new namespaces. Some example pages in the 4.3 docs still illustrate old paths; cross-check the **2025.0 release notes** and the **Configuration Properties** index for your exact version before copying.
- Gateway **5.0 and later** removed the deprecated old artifacts. For new projects, use the new starter names and prefixes matching your stack from the start.

Do not pick a standalone `spring-cloud-gateway` version when the Spring Cloud BOM manages another version. When upgrading, pick **compatible Spring Boot → Spring Cloud release train → BOM-managed Gateway**.

## 3. Starter Renames: Choosing WebFlux vs. Web MVC Correctly

| Role | Old starter/artifact | New name from Gateway 4.3 | Meaning |
|---|---|---|---|
| **Gateway Server WebFlux** | `spring-cloud-starter-gateway` | `spring-cloud-starter-gateway-server-webflux` | Reactive API gateway running on Spring WebFlux and Reactor Netty |
| **Gateway Server Web MVC** | `spring-cloud-starter-gateway-mvc` | `spring-cloud-starter-gateway-server-webmvc` | API gateway on Spring MVC using a Servlet runtime |
| **Proxy Exchange WebFlux** | `spring-cloud-gateway-webflux` | `spring-cloud-gateway-proxyexchange-webflux` | Uses `ProxyExchange` inside a web handler; not a standalone gateway server |
| **Proxy Exchange Web MVC** | `spring-cloud-gateway-mvc` | `spring-cloud-gateway-proxyexchange-webmvc` | Uses `ProxyExchange` on MVC; not synonymous with the Gateway Server MVC starter |

**Very easy naming trap to avoid:** `spring-cloud-starter-gateway-mvc` (with `starter`) was the older Gateway **Server MVC**; `spring-cloud-gateway-mvc` (without `starter`) belonged to **Proxy Exchange**. When upgrading, match by **module role**, not by blindly replacing the substring `mvc`.

Example declaring the new starter in Maven, with **a BOM already selecting a compatible Spring Cloud version**:

```xml
<!-- pom.xml: dependencyManagement section -->
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>2026.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<!-- pom.xml: Gateway Server WebFlux, Spring Cloud Gateway 5.1.x -->
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>
</dependencies>
```

This example uses release train `2026.0.0` (matching Spring Boot `4.2.0`); it is only for projects that have chosen that Boot generation. If using Server Web MVC, replace the artifact with `spring-cloud-starter-gateway-server-webmvc`. Do not put both Server starters into the same example expecting Gateway to auto-select the right variant.

In Gradle, the corresponding dependency declaration looks like:

```kotlin
dependencies {
    // After configuring a compatible Spring Cloud BOM in the build.
    implementation("org.springframework.cloud:spring-cloud-starter-gateway-server-webflux")
}
```

## 4. Exact Configuration Prefix Mapping Table

### 4.1. Server WebFlux: From the General Prefix to `server.webflux`

| Task | Gateway 4.2 and earlier | Gateway 4.3+ (new name) |
|---|---|---|
| Declare routes | `spring.cloud.gateway.routes` | `spring.cloud.gateway.server.webflux.routes` |
| Default filters for routes | `spring.cloud.gateway.default-filters` | `spring.cloud.gateway.server.webflux.default-filters` |
| Auto-create routes from service discovery | `spring.cloud.gateway.discovery.locator.enabled` | `spring.cloud.gateway.server.webflux.discovery.locator.enabled` |
| Global CORS configuration | `spring.cloud.gateway.globalcors.cors-configurations` | `spring.cloud.gateway.server.webflux.globalcors.cors-configurations` |
| Downstream HTTP client | `spring.cloud.gateway.httpclient.connect-timeout` | `spring.cloud.gateway.server.webflux.httpclient.connect-timeout` |
| Enable Gateway metrics | `spring.cloud.gateway.metrics.enabled` | `spring.cloud.gateway.server.webflux.metrics.enabled` |
| Gateway Redis RateLimiter properties | `spring.cloud.gateway.redis-rate-limiter.*` | `spring.cloud.gateway.server.webflux.redis-rate-limiter.*` |
| Enable/disable Gateway Server | `spring.cloud.gateway.enabled` | `spring.cloud.gateway.server.webflux.enabled` |

The pattern is replacing `spring.cloud.gateway.` with `spring.cloud.gateway.server.webflux.` **for Gateway Server WebFlux properties**. This is **not a global search-and-replace** across every key containing `gateway`: Spring Boot, Spring Security, Actuator, or Proxy Exchange namespaces must be handled separately.

### 4.2. Server Web MVC: From `mvc` to `server.webmvc`

| Task | Gateway 4.1–4.2 | Gateway 4.3+ |
|---|---|---|
| Declare routes | `spring.cloud.gateway.mvc.routes` | `spring.cloud.gateway.server.webmvc.routes` |
| Enable/disable Gateway Server MVC | `spring.cloud.gateway.mvc.enabled` | `spring.cloud.gateway.server.webmvc.enabled` |
| Declare routes as a map | `spring.cloud.gateway.mvc.routes-map` | `spring.cloud.gateway.server.webmvc.routes-map` |
| Declare trusted proxies | `spring.cloud.gateway.mvc.trusted-proxies` | `spring.cloud.gateway.server.webmvc.trusted-proxies` |

Here the replacement is `spring.cloud.gateway.mvc.` → `spring.cloud.gateway.server.webmvc.`. Do not switch MVC to WebFlux just to match a property name: an MVC app runs on Servlet, whereas WebFlux runs on Reactor Netty; filter APIs and many operational capabilities also differ.

### 4.3. What Does Not Change Under This Rule?

- **`spring.application.name`**, **`server.port`**, **`server.ssl.*`**, **`management.*`**, and **`spring.security.*`** belong to Spring Boot or other components. For example, inbound server TLS is normally configured under `server.ssl.*`; never change it to `spring.cloud.gateway.server.webflux.server.ssl.*`.
- Keys inside a route such as `uri`, `predicates`, `filters`, `Path`, `StripPrefix`, `AddRequestHeader`, `Retry` are **route contents**, not property prefixes. Detailed filter configurations can still differ between WebFlux and MVC, so check the filter documentation for the exact variant.
- `spring.cloud.gateway.proxy-exchange.webflux.*` and `spring.cloud.gateway.proxy-exchange.webmvc.*` belong to **Proxy Exchange**; they are not used to declare route lists for Gateway Server.
- The prefix `spring.cloud.gateway.server.webflux.metrics.*` controls Gateway's metrics feature. **Metric names** (e.g., `spring.cloud.gateway.requests`) do not necessarily change alongside the configuration prefix.

## 5. Migration Example: Server WebFlux 4.2 → 4.3/5.x

Suppose the Gateway receives `GET /api/catalog/items`, forwards it to service `http://localhost:8081` under path `/catalog/items`, and attaches header `X-Gateway: edge`.

**Old configuration (Gateway 4.2, starter `spring-cloud-starter-gateway`):**

```yaml
# application.yml — Gateway Server WebFlux 4.2
server:
  port: 8080
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-route
          uri: http://localhost:8081
          predicates:
            - Path=/api/catalog/**
          filters:
            - StripPrefix=1
            - AddRequestHeader=X-Gateway, edge
      discovery:
        locator:
          enabled: false
      httpclient:
        connect-timeout: 2000
      metrics:
        enabled: true
```

**New configuration (Gateway 4.3+, starter `spring-cloud-starter-gateway-server-webflux`):**

```yaml
# application.yml — Gateway Server WebFlux 4.3/5.x
server:
  port: 8080
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-route
              uri: http://localhost:8081
              predicates:
                - Path=/api/catalog/**
              filters:
                - StripPrefix=1
                - AddRequestHeader=X-Gateway, edge
          discovery:
            locator:
              enabled: false
          httpclient:
            connect-timeout: 2000
          metrics:
            enabled: true
```

**What changed:** `routes`, `discovery`, `httpclient`, and `metrics` moved from under `gateway` to `gateway.server.webflux`. **What stayed the same:** the structure inside each route, path predicates, filters, and their arguments. `StripPrefix=1` removes the `/api` segment; the backend receives `/catalog/items`. If the backend is not running yet, a downstream connection error is a separate issue from routes failing to load.

You can test once the Gateway and sample backend are running:

```bash
curl -i http://localhost:8080/api/catalog/items
```

When configured properly, Gateway selects `catalog-route`, forwards to `localhost:8081/catalog/items`, and sends header `X-Gateway: edge`. Check the backend logs to confirm the path and header; the final HTTP status code is determined by the backend and filters.

## 6. Migration Example: Server MVC 4.2 → 4.3/5.x

**Old — Gateway Server MVC 4.2:**

```yaml
spring:
  cloud:
    gateway:
      mvc:
        routes:
          - id: orders-route
            uri: http://localhost:8082
            predicates:
              - Path=/orders/**
            filters:
              - StripPrefix=1
```

**New — Gateway Server Web MVC 4.3+:**

```yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: orders-route
              uri: http://localhost:8082
              predicates:
                - Path=/orders/**
              filters:
                - StripPrefix=1
```

Also swap the starter `spring-cloud-starter-gateway-mvc` → `spring-cloud-starter-gateway-server-webmvc`. With `GET /orders/42`, `StripPrefix=1` causes the backend to receive `/42`. This example uses a filter supported by both lines to illustrate the **namespace difference**, without implying every WebFlux filter has an identical MVC counterpart.

## 7. Safe Upgrade Sequence for a Real Gateway System

1. **Lock down versions:** verify Spring Boot, Spring Cloud BOM, actual Gateway version, and Server type (**WebFlux** or **Web MVC**). Inspect Maven's `dependency:tree` or Gradle's `dependencies` if the project has multiple modules pulling transitive dependencies.
2. **Swap the starter by exact role:** WebFlux → `spring-cloud-starter-gateway-server-webflux`; MVC → `spring-cloud-starter-gateway-server-webmvc`. In Gateway 4.3, old names may still work as deprecated; 5.x uses the new names.
3. **Migrate the full Gateway Server configuration namespace:** beyond `routes`, audit properties for `default-filters`, discovery, CORS, timeouts, load balancer, rate limiter, metrics, trusted proxies, etc. Consult `Configuration Properties` for the **exact version**.
4. **Keep non-Gateway configurations separate:** `server.ssl.*` for inbound TLS, Spring Security for authentication/authorization, `management.*` for Actuator. Outbound HTTP client TLS **toward backends** resides under `spring.cloud.gateway.server.webflux.httpclient.ssl.*`, so keep the two connection ends distinct.
5. **Cross-check feature dependencies:** `lb://service-id` requires a DiscoveryClient and appropriate load balancer; CircuitBreaker, RedisRateLimiter, and Actuator may require their own starters/libraries and configuration. Renaming prefixes does not automatically install those components.
6. **Use transition tools only when needed:** the 2025.0 release notes mention `spring-boot-properties-migrator` to help transition deprecated properties. Use it to detect/migrate old configuration during the upgrade, then move all keys to the new namespace and remove runtime migration reliance. Avoid maintaining the same route under **both old and new prefixes**, which can cause overrides or ambiguity over which config takes effect.
7. **Verify runtime behavior:** inspect loaded routes, send test URLs, verify path/header mutations, check `lb://`, retry/circuit breaker, TLS to backends, and metrics. Only expose Actuator endpoints for diagnostics with proper access controls.

### 7.1. How to Investigate When Gateway Starts Up but Returns 404

| Symptom | Check First | Resolution |
|---|---|---|
| Returns `404` even though `application.yml` defines routes | Do the starter, Gateway version, and `routes` prefix match? | Use `gateway.routes` on 4.2 and earlier; `gateway.server.webflux.routes` or `gateway.server.webmvc.routes` on 4.3+ matching the active stack |
| Route exists but fails to call service | `uri`, DNS, port, service registry, load balancer dependency | Check backend, `lb://service-id`, and DiscoveryClient; do not immediately blame the rename |
| Request reaches backend with wrong path | `Path`, `StripPrefix`, `RewritePath`, filter order | Trace path before/after filters; with `StripPrefix=1`, `/api/a` becomes `/a` |
| Headers or retry/circuit breaker behave unexpectedly | Did the route match, is the filter supported on this stack, are dependencies present? | Check filters and libraries for your version; do not guess from filter names alone |
| Metrics do not appear | `metrics.enabled` config, Actuator/Micrometer, endpoint exposure | Update to the right prefix and check the corresponding observability tooling |

In **Server WebFlux**, once the appropriate Actuator Gateway endpoint is configured, you can inspect routes via `/actuator/gateway/routes`. Keep administrative endpoints separate from public traffic and restrict access in real environments.

## 8. Three Self-Check Scenarios

**Scenario A.** A project upgrades from Spring Cloud `2024.0`/Gateway `4.2` to `2025.0`/Gateway `4.3` while keeping `spring-cloud-starter-gateway` and `spring.cloud.gateway.routes`. What needs to change?

**Answer:** change the starter to `spring-cloud-starter-gateway-server-webflux`; migrate WebFlux properties to `spring.cloud.gateway.server.webflux.*`, starting with `routes`. Then audit other properties such as discovery, httpclient, and metrics. The 4.3 line is a deprecation/migration phase; do not treat temporary compatibility with old config as ready for a 5.x upgrade.

**Scenario B.** An application runs on Servlet/Tomcat and previously used `spring-cloud-starter-gateway-mvc`; a teammate proposes switching to `spring-cloud-starter-gateway-server-webflux` because the new name is more common. Is that proposal right?

**Answer:** no. The matching variant is `spring-cloud-starter-gateway-server-webmvc`; the new route namespace is `spring.cloud.gateway.server.webmvc.routes`. Switching to WebFlux means changing the entire web stack, not just renaming an artifact.

**Scenario C.** A Gateway Server WebFlux 5.x application has two route lists: `spring.cloud.gateway.routes` and `spring.cloud.gateway.server.webflux.routes`. Which one should be kept?

**Answer:** standardize on **`spring.cloud.gateway.server.webflux.routes`**. Remove duplicate configuration under the old prefix after verifying all values to avoid relying on migration mechanisms or causing unintended overrides.

## 9. Official Reference Documentation

- [Spring Cloud 2025.0 Release Notes — Gateway 4.3 starter and namespace changes](https://github.com/spring-cloud/spring-cloud-release/wiki/Spring-Cloud-2025.0-Release-Notes).
- [Spring Cloud Gateway 4.2 — Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/4.2/configprops.html): `spring.cloud.gateway.*` and `spring.cloud.gateway.mvc.*` prefixes.
- [Spring Cloud Gateway 4.3 — Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/4.3/configprops.html): shows the transition between old and new namespaces.
- [Spring Cloud Gateway 5.1 — Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/5.1/configprops.html): new Server WebFlux/Web MVC prefixes.
- [Gateway 5.0 — WebFlux starter](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/starter.html) and [Gateway 5.0 — Web MVC starter](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webmvc/starter.html).
- [Gateway 5.0 — Proxy Exchange](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-proxy-exchange.html): distinguishing Proxy Exchange from Gateway Server.
- [Spring Cloud 2026.0.0 release announcement](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/): Gateway 5.1.0 corresponds to train 2026.0.0 and Boot 4.2.0.

**Remember:** check **version → starter → web stack → prefix** in that exact order. Two configurations with identical route/filter syntax can still behave differently if placed under the namespace of a different version or variant.
