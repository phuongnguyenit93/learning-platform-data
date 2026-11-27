# Cross-Checking Supported Properties Against Your Release Train

In the `SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING` module, Spring Cloud LoadBalancer performs client-side load balancing: it receives a **service ID**, fetches `ServiceInstance` entries from discovery, optionally filters by health checks or routing policies, and selects an instance for `RestClient`, `WebClient`, or OpenFeign to send requests. When configuring different settings per service, an important question arises: **is the property we intend to use actually supported by the application's Spring Cloud Release Train?**

For example, `order-service` calls `inventory-service` and `payment-service`. We want `inventory-service` to run health checks more frequently while `payment-service` has a stricter retry policy. Simply placing a key in `application.yml` does not prove that the current library version recognizes that key or that the corresponding mechanism is enabled.

This lesson provides a version-verification method, distinguishes global/per-client scopes, examines key exceptions, and walks through verifying effective configuration. There is no single immutable property table valid for every Spring Cloud Release Train: treat the **actual resolved dependency version** as your verification baseline.

## Learning Objectives

After this lesson, you will be able to:

1. Identify the application's Spring Boot version, Spring Cloud Release Train, and `spring-cloud-commons`/`spring-cloud-loadbalancer` versions.
2. Locate the exact reference documentation and configuration properties catalog matching that version.
3. Classify global properties, properties overridable per `clientId`, per-service-ID map properties, and features that require Java configuration.
4. Compare differences across Spring Cloud Commons 4.1, 4.2, 4.3, and 5.0 branches instead of blindly copying configurations between projects.
5. Prove that a configuration is bound and genuinely affects discovery, health checks, retries, caching, instance selection, and error observability.

## 1. Lock Down the Exact Version Set Before Reading Documentation

A **Spring Cloud Release Train** is a coordinated set of Spring Cloud project versions released and managed to work together. Spring Cloud LoadBalancer is released within the Spring Cloud Commons ecosystem; therefore, you must check both the Release Train and the running artifact version.

Common branches for reference:

| Spring Cloud Release Train | Compatible Spring Boot Generation | Spring Cloud Commons Branch for Docs | Notes |
|---|---|---|---|
| `2023.0.x` (Leyton) | `3.2.x`, `3.3.x` per published service release milestones | `4.1.x` | Use Commons `4.1` docs, do not default to the latest page |
| `2024.0.x` (Moorgate) | `3.4.x` | `4.2.x` | Check `4.2` docs and configprops |
| `2025.0.x` (Northfields) | `3.5.x` | `4.3.x` | Check `4.3` docs and configprops |
| `2025.1.x` (Oakwood) | `4.0.x`; `4.1.x` from `2025.1.2` onward | `5.0.x` | Check `5.0` docs and configprops |

This table is for **locating the right documentation branch**. Always confirm the exact version via dependency resolution; do not assume every Boot patch version pairs with every Spring Cloud patch version. Support status and new releases also change over time. Check the compatibility matrix and release history on the [Spring Cloud project](https://spring.io/projects/spring-cloud/) page before upgrading.

### 1.1. Check the Dependency Declaration File

In Maven, locate the Spring Cloud BOM in `pom.xml` or parent dependency management:

```xml
<properties>
    <!-- Illustrative value: replace with your project's Release Train -->
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
```

`2025.0.x` in the example above is only a **branch notation**, not a valid literal version to copy into a build. In a real project, replace it with a concrete existing release, such as `2025.0.1` if chosen per your team's upgrade policy.

In Gradle, look for the BOM or equivalent configuration, such as `mavenBom "org.springframework.cloud:spring-cloud-dependencies:<version>"` when using the Spring dependency-management plugin. Regardless of how it is declared, inspect the actually resolved artifacts because a direct dependency or another version-management configuration may override the expected result.

### 1.2. Check Resolved Dependencies

Example commands in a Maven project terminal:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.cloud:spring-cloud-commons,org.springframework.cloud:spring-cloud-loadbalancer
./mvnw help:effective-pom
```

Example with Gradle:

```bash
./gradlew dependencyInsight --dependency spring-cloud-commons --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-loadbalancer --configuration runtimeClasspath
```

If the project does not have a Maven/Gradle Wrapper, use the build tool installed on your machine. Record the exact versions, such as `spring-cloud-commons:4.3.z` and `spring-cloud-loadbalancer:4.3.z`, rather than only writing "Spring Cloud 2025". Both must be verified because LoadBalancer configuration involves property classes and auto-configuration components from both Commons and LoadBalancer.

## 2. Consult the Right Sources and Rank Confidence Levels

Check in the following order:

1. **Official documentation for the exact branch**: describes feature usage, scope, and prerequisites for taking effect.
2. **Configuration Properties for the same branch**: confirms key names, value types, descriptions, and defaults generated from that library version's metadata.
3. **Resolved artifact and source code at the matching tag**: inspect `@ConfigurationProperties`, `LoadBalancerProperties`, auto-configuration, or property usage code if docs are unclear.
4. **Application runtime behavior**: confirms the property is bound and produces the expected behavior. This is decisive proof for the current environment.

Official pages to open directly:

| Commons Branch | LoadBalancer Reference | Configuration Properties |
|---|---|---|
| `4.1` | [LoadBalancer 4.1](https://docs.spring.io/spring-cloud-commons/reference/4.1/spring-cloud-commons/loadbalancer.html) | [Configprops 4.1](https://docs.spring.io/spring-cloud-commons/reference/4.1/configprops.html) |
| `4.2` | [LoadBalancer 4.2](https://docs.spring.io/spring-cloud-commons/reference/4.2/spring-cloud-commons/loadbalancer.html) | [Configprops 4.2](https://docs.spring.io/spring-cloud-commons/reference/4.2/configprops.html) |
| `4.3` | [LoadBalancer 4.3](https://docs.spring.io/spring-cloud-commons/reference/4.3/spring-cloud-commons/loadbalancer.html) | [Configprops 4.3](https://docs.spring.io/spring-cloud-commons/reference/4.3/configprops.html) |
| `5.0` | [LoadBalancer of current stable release](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html) | [Configprops of current stable release](https://docs.spring.io/spring-cloud-commons/reference/configprops.html) |

At the time of writing, the unversioned `/reference/` links display Spring Cloud Commons **5.0.4**. They may point to a newer branch in the future, so check the **version shown at the top of the page** before using them and choose a source matching your resolved artifact/version if the header is no longer `5.0.x`. Do not treat the latest page as proof for a project on an older branch. Do not rely on milestone, release candidate, or snapshot docs to draw conclusions about a deployed GA release.

### 2.1. How to Read a Property from Documentation

For each key, record all four factors:

| Question | Information to Confirm | Example |
|---|---|---|
| **Does it exist?** | Is the key in configprops or the active artifact's metadata? | `spring.cloud.loadbalancer.health-check.interval` |
| **Scope?** | Global, overridable via `clients.<id>`, or a service-ID map? | `clients.inventory-service.health-check.interval` |
| **Activation conditions?** | Which dependency/bean/supplier/HTTP client does the feature require? | `HealthCheckServiceInstanceListSupplier` |
| **How to verify?** | How do logs, metrics, timings, responses, or instance lists change? | Health-check interval changes accordingly |

A key appearing in metadata only confirms **a binding mechanism exists**. If the service does not have a `HealthCheckServiceInstanceListSupplier`, setting `health-check.interval` will not make the system run periodic health checks automatically. Similarly, having `retry.max-retries-*` in YAML does not mean retries will definitely occur if the retry mechanism or required dependency is absent.

## 3. Distinguish Global vs. Per-Client Before Configuring

For the branches listed above, the typical syntax for per-service configuration is:

```text
spring.cloud.loadbalancer.<property>                   # Shared value
spring.cloud.loadbalancer.clients.<clientId>.<property> # Per-client value
```

`<clientId>` is the **LoadBalancer client name**, usually the exact service ID used by `RestClient`, `WebClient`, or OpenFeign, such as `inventory-service`. Shared values are merged with per-client configuration, and per-client configuration takes precedence when the property supports overriding. Each service ID has its own LoadBalancer context; in practice, the context is typically initialized on the first request to that service.

### 3.1. Important Global Exceptions

This is the group requiring special attention in the **Configuring Individual LoadBalancerClients** section of the docs:

| Property | Scope / Limit | Common Pitfall |
|---|---|---|
| `spring.cloud.loadbalancer.enabled` | **Global** LoadBalancer on/off switch | Cannot enable a single client when LoadBalancer is disabled globally |
| `spring.cloud.loadbalancer.retry.enabled` | **Global** retry permission flag; when enabled globally, retries can be disabled for a specific client, but when disabled globally, a client cannot turn them back on | Setting `clients.payment-service.retry.enabled=true` does not override global `retry.enabled=false` |
| `spring.cloud.loadbalancer.cache.enabled` | **Global** cache switch; when global caching is enabled, omitting caching for one client usually requires a custom supplier without `CachingServiceInstanceListSupplier` | Do not treat `clients.inventory-service.cache.enabled=false` as a reliable standalone toggle |
| `spring.cloud.loadbalancer.stats.micrometer.enabled` | **Global** LoadBalancer metrics toggle | Getting metrics for only one client requires another filtering/observability solution; do not assume global=false can be overridden per client |

For retries, configuring `max-retries-on-same-service-instance` or `max-retries-on-next-service-instance` per client is still meaningful **when retries are enabled application-wide and the stack supports retries**. The scope of these parameters differs from the scope of the `retry.enabled` toggle.

### 3.2. Properties Commonly Configurable Per Client

The following groups are documented in the linked branches; when applying them, still check metadata and activation conditions for the exact library version:

| Group | Example Properties | Meaning / Conditions |
|---|---|---|
| Health check | `health-check.initial-delay`, `health-check.interval`, `health-check.refetch-instances` | Adjusts schedule or refresh behavior of the health-check supplier; supplier must be configured |
| Retry | `retry.max-retries-on-same-service-instance`, `retry.max-retries-on-next-service-instance`, `retry.retryable-status-codes` | Limits attempts and defines retryable errors; must consider global enablement, retry implementation, and idempotency |
| Reactive retry | `retry.backoff.enabled`, `retry.backoff.min-backoff`, `retry.backoff.max-backoff`, `retry.backoff.jitter` | Applies to supported reactive backoff mechanisms; do not assume RestClient and Feign share the same behavior |
| Instance selection | `zone`, `hint`, `subset.size` | Takes effect only when the matching supplier/policy reads those values |
| Caching | `cache.ttl`, `cache.capacity` | Adjusts caching if enabled and read by the active cache mechanism |
| Discovery | `service-discovery.timeout` | Wait timeout for querying discovery, **not** the HTTP timeout to the target instance |

Notably, `health-check.path` and `hint` use a **per-service-ID map** syntax maintained by the documentation for backward compatibility:

```yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        path:
          default: /actuator/health
          inventory-service: /actuator/health/readiness
      hint:
        inventory-service: warehouse-a
```

The snippet above illustrates the map syntax across the checked documentation branches. It does not mean the application automatically picks instances by hint: a hint-handling supplier must be configured, and `inventory-service` needs matching `hint` metadata or appropriate selection logic. When upgrading major versions, re-verify how these maps bind in that version's docs and source code.

### 3.3. Properties Cannot Replace Java Configuration

The following example is **unfounded** if no corresponding property exists in metadata:

```yaml
# DO NOT use if you only guessed the key name
spring:
  cloud:
    loadbalancer:
      clients:
        inventory-service:
          algorithm: random
```

To switch `RoundRobinLoadBalancer` to `RandomLoadBalancer` solely for `inventory-service`, refer to `@LoadBalancerClient(name = "inventory-service", configuration = ...)` and declare the appropriate `ReactorLoadBalancer<ServiceInstance>`. Configuring via annotations/beans and configuring via `@ConfigurationProperties` are **two different mechanisms**; never assume every choice in Java has a matching YAML key.

Similarly, values like `connect-timeout` or `response-timeout` for `RestClient`, `WebClient`, or OpenFeign usually belong to the specific HTTP transport/client. Do not invent `spring.cloud.loadbalancer.clients.<id>.connect-timeout` assuming it configures the timeout to target instances. Read the timeout documentation for the exact HTTP client in use.

## 4. Sample Comparison Table Across Commons Branches

Convention: **Present** means the key/group appears in the checked branch's property catalog; **Not listed** means that catalog does not list it and it must be verified before use. These markers do not replace reading the exact patch version's source code or testing actual behavior.

| Property Group | Commons 4.1 | Commons 4.2 | Commons 4.3 | Commons 5.0 | Usage Conclusion |
|---|---|---|---|---|---|
| `health-check.interval` | Present | Present | Present | Present | Verify the health-check supplier is enabled |
| `health-check.path` | Present | Present | Present | Present | Check per-service-ID map syntax and health endpoint |
| `retry.enabled` | Present | Present | Present | Present | Remember global constraints and per-client disablement |
| `retry.max-retries-on-next-service-instance` | Present | Present | Present | Present | Check retry library and HTTP client type |
| `retry.backoff.*` | Present | Present | Present | Present | Expect backoff only when the matching retry mechanism supports it |
| `cache.enabled`, `cache.ttl` | Present | Present | Present | Present | Distinguish global enablement from concrete cache configuration |
| `stats.micrometer.enabled` | Present | Present | Present | Present | Requires `MeterRegistry` and global switch |
| `call-get-with-request-on-delegates` | Present | Present | Present | Present | Check how suppliers receive `Request` and delegate ordering |
| `service-discovery.timeout` | Present | Present | Present | Present | Applies only to discovery operations, does not replace HTTP timeouts |
| `api-version.*` | Not listed | Not listed | Not listed | Present | Branch-dependent feature; do not copy 5.0 config to 4.x without verification |

A notable difference is the `spring.cloud.loadbalancer.api-version.*` group: the Spring Cloud Commons `5.0` catalog lists keys such as `header`, `query-parameter`, `path-segment`, `required`, and `fallback-to-available-instances`, whereas the checked `4.1`, `4.2`, and `4.3` catalogs do not list this group. The LoadBalancer `5.0` documentation also describes API-version-based instance-selection suppliers. This is a practical example of why documentation must be pinned to the Release Train.

**Comparison warning:** "present in configprops" and "usable per client" are two different columns of information. `retry.enabled` appears in all four branches yet is a switch with global constraints; `health-check.interval` can be overridden per client yet takes effect only when a health-check supplier is present. Do not mark a property as "working properly" just because it exists in the catalog.

## 5. Example Configuring Two Services in the Same Application

Suppose `order-service` uses two service IDs: `inventory-service` and `payment-service`. The example below illustrates combining shared values with per-client overrides across the checked Commons branches:

```yaml
spring:
  cloud:
    loadbalancer:
      enabled: true

      # Enable retry capability globally.
      retry:
        enabled: true
        max-retries-on-same-service-instance: 0
        max-retries-on-next-service-instance: 1

      # Shared values; only effective when a HealthCheck supplier is present.
      health-check:
        initial-delay: 1s
        interval: 25s
        path:
          default: /actuator/health
          inventory-service: /actuator/health/readiness

      # Overrides per LoadBalancer client name / service ID.
      clients:
        inventory-service:
          health-check:
            interval: 10s
          retry:
            enabled: false

        payment-service:
          health-check:
            interval: 30s
          retry:
            max-retries-on-same-service-instance: 0
            max-retries-on-next-service-instance: 0
```

How to read this, assuming version and runtime mechanism support:

| Component | Expected Configuration Value | Verification Condition |
|---|---|---|
| `inventory-service` | `health-check.initial-delay=1s`, `health-check.interval=10s` | This service's health-check supplier must be present; `/actuator/health/readiness` endpoint must be reachable |
| `payment-service` | `health-check.initial-delay=1s`, `health-check.interval=30s` | Same health-check supplier requirement; without a path override, uses default path |
| `inventory-service` retry | Disabled individually even though global retry is enabled | Test with a retryable error and verify attempt count |
| `payment-service` retry | Caps retries on both same and next instance at `0` | Must also account for retry implementation; confirm actual request count in logs |

This scenario does **not** install health checks automatically. If periodic health checks are desired, create or select a configuration with `HealthCheckServiceInstanceListSupplier` (for example using `ServiceInstanceListSupplier.builder().withDiscoveryClient().withHealthChecks()` with a compatible stack). If your discovery registry already supplies health status and no independent health supplier is needed, do not enable extra health checks just to see the `interval` key work.

### 5.1. Counter-Example: Enabling Per-Client Retry When Global Is Disabled

```yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: false
      clients:
        payment-service:
          retry:
            enabled: true
```

Per the global constraint documented in the reference, the configuration above **does not re-enable retries** for `payment-service`. If the goal is to retry for some clients and not others, set global `retry.enabled=true`, then disable it on the excluded clients and verify retry behavior with a real test.

### 5.2. Counter-Example: Trying to Enable Cache for One Client When Global Is Disabled

```yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: false
      clients:
        inventory-service:
          cache:
            enabled: true
```

You cannot conclude from this configuration that `inventory-service` now has its own cache. Per the docs, the cache toggle is global; to use different supplier configurations per service, build a `ServiceInstanceListSupplier` per client and verify the cache delegate is created properly. The effect of `cache.ttl` also depends on the actual caching mechanism and whether discovery itself caches results.

## 6. Practical Workflow for Cross-Checking and Verification

### Step 1 — Build a Version Profile

From a Spring Boot application with `spring-cloud-starter-loadbalancer`, record:

- Exact Spring Boot version.
- Exact Spring Cloud BOM version.
- Resolved `spring-cloud-commons` and `spring-cloud-loadbalancer` versions.
- Client style in use: `RestClient`, `WebClient`, OpenFeign; retry dependency and version if present.
- Discovery implementation: Eureka, Consul, Kubernetes, `SimpleDiscoveryClient`, or custom supplier.

Example check sheet:

```text
Application: order-service
Spring Boot: 3.5.z
Spring Cloud BOM: 2025.0.z
spring-cloud-commons: 4.3.z
spring-cloud-loadbalancer: 4.3.z
HTTP clients: RestClient + WebClient + OpenFeign
Service IDs: inventory-service, payment-service
Reference docs: Spring Cloud Commons 4.3
```

The `z` placeholders in the sheet mark where to fill in the actual patch version, not literal versions to declare in a build.

### Step 2 — Select the List of Keys to Check

Include only keys that affect your requirements. For example:

```text
spring.cloud.loadbalancer.enabled
spring.cloud.loadbalancer.clients.inventory-service.health-check.interval
spring.cloud.loadbalancer.clients.inventory-service.retry.enabled
spring.cloud.loadbalancer.clients.payment-service.retry.max-retries-on-next-service-instance
spring.cloud.loadbalancer.health-check.path.inventory-service
spring.cloud.loadbalancer.cache.enabled
spring.cloud.loadbalancer.stats.micrometer.enabled
```

For each key, check existence, value type, default, configuration scope, and functional dependencies. Do not guess key names by extrapolating from a Java object or another library.

### Step 3 — Cross-Check the configprops Page and Behavioral Docs

Look up the **base key name** in the configprops page. Then read **Configuring Individual LoadBalancerClients** to see whether adding `clients.<clientId>` is supported or falls under an exception. Finally, read the feature documentation such as **Instance Health-Check**, **Caching**, **Retry**, or **Hint-Based Load-Balancing** to understand when the property takes effect.

For example, for `health-check.interval`, configprops gives the type and default; the health-check section confirms `HealthCheckServiceInstanceListSupplier` is required. For `stats.micrometer.enabled`, an appropriate `MeterRegistry` is needed alongside the property. For `retry.*`, check that the retry implementation works for your client stack, which events are retried, and the total call limit.

### Step 4 — Verify Configuration Binding

When Spring Boot Actuator is enabled in a lab environment, you can use the `configprops` endpoint to inspect bound `@ConfigurationProperties` beans; `env` helps trace property sources if needed. Expose these endpoints only in development environments or protected channels; keep secrets out of exposed output.

Child contexts for individual LoadBalancer clients may be created **lazily** on the first call. Therefore, if a per-service bean/configuration does not appear during initial inspection, invoke that service once and inspect again using your version's mechanism. If Actuator does not display every per-child-context value, use logs or behavioral tests to confirm rather than assuming a property was ignored just because one screen omits it.

### Step 5 — Verify Actual Runtime Behavior

Run controlled tests one by one:

| Test | Input | Expected Evidence |
|---|---|---|
| Health interval override | `inventory-service=10s`, `payment-service=30s` | When the health supplier is enabled, probe schedules/logs differ as configured |
| Global retry disabled | `retry.enabled=false`; client sets `true` | No retries generated by LoadBalancer |
| Global retry enabled, one client disabled | Global `true`; `inventory-service` `false` | A failing request to inventory is not retried by LoadBalancer; other clients follow their own config |
| Retry count | `payment-service.retry.max-retries-on-next-service-instance=0` | Attempt count matches current limit and policy |
| Stale discovery entry | Stop one instance while keeping stale discovery/cached list briefly | Error logs, cache/health check, and instance eviction timing match expectations |
| API version on older branch | Put 5.0-style `api-version.*` keys into a Commons 4.x project | Do not assume support; check metadata and behavior, or do not use the feature |

When testing retries, prefer read-only `GET` endpoints and simulate transient errors. Avoid automatically retrying non-idempotent write operations since that can duplicate transactions. When observing timeouts, check HTTP client timeouts and discovery wait times separately to avoid misattributing failures to LoadBalancer.

### Step 6 — Record Verification Results in a Team Table

A useful template to store alongside configuration decisions:

| Required Property | Checked Artifact/Version | In configprops? | Scope | Activation Condition | Runtime Evidence | Decision |
|---|---|---|---|---|---|---|
| `health-check.interval` | `spring-cloud-commons:4.3.z` | Yes | Overridable per-client | Health-check supplier | Probe timestamps | Use |
| `retry.enabled` | `spring-cloud-commons:4.3.z` | Yes | Global; can be disabled per client | Retry implementation | Attempt count | Keep global on, disable selectively |
| `api-version.header` | `spring-cloud-commons:4.3.z` | Not listed | Unconfirmed | Must verify feature per branch | None yet | Do not use in 4.3 config without proof |

The table above is just an illustrative template for the 4.3 branch; replace `z` and fill in actual runtime results when executing in your project. The "Decision" column should clearly state whether the key is kept, replaced with Java configuration, or temporarily omitted due to lack of support evidence.

## 7. Common Sources of Confusion When Upgrading Release Trains

### 7.1. Reading Latest Docs and Copying into an Older Project

A team sees `spring.cloud.loadbalancer.api-version.header` in the Commons 5.0 docs and immediately adds it to an application running Commons 4.3. The application may still start, yet that does not prove API-version-based instance selection is active. Remedy: use the 4.3 configprops page and 4.3 source code to confirm; if a feature available only in a newer branch is needed, plan an upgrade instead of leaving an ineffective key in YAML.

### 7.2. Configuring Health Checks Without Creating a Health-Check Supplier

Setting `spring.cloud.loadbalancer.clients.inventory-service.health-check.interval=10s` only configures a value. Periodic health checks require `HealthCheckServiceInstanceListSupplier` or a configuration that builds that supplier. If the application uses only the default discovery supplier without health checks enabled, there is no probe schedule to adjust. Inspect beans and the delegate chain before tuning intervals.

### 7.3. Confusing Service ID with Bean Name or Caller Application Name

The `clients.inventory-service` path applies to the LoadBalancer client calling `inventory-service`. It is not keyed by `order-service`'s `spring.application.name`. If OpenFeign uses `@FeignClient(name = "inventory-service")`, that name must match the configured ID. An arbitrary name such as `clients.order-service` will not affect inventory calls if LoadBalancer routes by another service ID.

### 7.4. Confusing Spring Cloud LoadBalancer Retries with Another Library's Retries

OpenFeign, Spring Retry, Reactor, HTTP clients, and resilience libraries may each have their own retry configuration. Verify which layer performs the retry, whether stacked retries occur, and what the total attempt count is. Changing `spring.cloud.loadbalancer.retry.max-retries-on-next-service-instance` does not guarantee other retry mechanisms change with it.

### 7.5. Confusing Discovery Timeout with HTTP Request Timeout

`spring.cloud.loadbalancer.service-discovery.timeout` governs calling service discovery; it does not directly replace connect/read/response timeouts on `RestClient`, `WebClient`, or OpenFeign. When a request is slow, measure instance-list retrieval time, selection time, connection time, and server response time separately.

### 7.6. Misunderstanding Metrics Scope

`spring.cloud.loadbalancer.stats.micrometer.enabled` is a global switch. To see failed request counts per service/instance, you need a `MeterRegistry`, actual metric emission, and appropriate tags. Do not assume a property like `clients.<id>.stats.micrometer.enabled=true` can enable metrics for one client when global metrics are off. When metrics are missing, inspect instrumentation and observability configuration before concluding requests bypass LoadBalancer.

## 8. Capstone Lab: Deciding Which Properties Are Safe to Use

**Context:** two environments run `order-service`. Environment A uses Spring Cloud `2024.0.x`/Commons `4.2.x`, and Environment B uses Spring Cloud `2025.1.x`/Commons `5.0.x`. Both call `inventory-service` and `payment-service` via `RestClient`, `WebClient`, or OpenFeign by service ID.

Lab instructions:

1. Record the exact patch versions in each environment using dependency-management tools.
2. Open the configprops and LoadBalancer reference pages corresponding to `4.2` and `5.0`; build a table for `health-check.interval`, `retry.enabled`, `retry.max-retries-on-next-service-instance`, `cache.enabled`, `stats.micrometer.enabled`, and `api-version.*`.
3. Mark the global/per-client/map scope of each key along with its activation prerequisites.
4. Call one service using `RestClient` and one using `WebClient` or Feign to confirm the service ID acts as the configuration `clientId`. Log the instance ID for each request.
5. Configure global retry enabled, disable retry for `inventory-service`, and cap retries for `payment-service`. Observe attempt counts when a GET endpoint returns transient errors.
6. If a health-check supplier is present, set different intervals for the two clients and verify probe timestamps. If no supplier is present, add the proper configuration before testing.
7. For `api-version.*`, use it only in Environment B after verifying the required implementation and dependencies; document why it cannot be copied directly to Environment A.
8. Compare logs, metrics, and response times; write a short decision summary on which keys to keep, drop, or replace with Java configuration.

**Completion criteria:** each selected key has a matching-branch documentation reference, a verified configuration scope, matching dependencies/suppliers, and runtime evidence. For keys absent from the running version, record "support unverified" and do not use them based solely on newer-version docs.

## 9. Checklist Before Promoting Configuration to Production

- [ ] Confirmed Spring Boot, Spring Cloud BOM, and resolved artifact versions.
- [ ] Used the LoadBalancer reference and configprops pages matching the active Commons branch.
- [ ] Checked whether each key is global, per-client, or a per-service-ID map.
- [ ] Reviewed exceptions for `enabled`, `retry.enabled`, `cache.enabled`, and `stats.micrometer.enabled`.
- [ ] Verified required suppliers for health checks, hints, zones, or custom selection policies.
- [ ] Checked retry dependencies/implementations per client type and capped total attempts.
- [ ] Separated discovery timeout from HTTP transport timeouts.
- [ ] Verified `clients.<clientId>` matches the actual service ID being called.
- [ ] Tested healthy instances, failing instances, and no-matching-instance cases.
- [ ] Recorded an evidence table: version, docs, property, scope, and test results.

## Official References

- [Spring Cloud — Compatibility and Release Train](https://spring.io/projects/spring-cloud/).
- [Spring Cloud Commons 4.1 — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/4.1/configprops.html) and [LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/4.1/spring-cloud-commons/loadbalancer.html).
- [Spring Cloud Commons 4.2 — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/4.2/configprops.html) and [LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/4.2/spring-cloud-commons/loadbalancer.html).
- [Spring Cloud Commons 4.3 — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/4.3/configprops.html) and [LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/4.3/spring-cloud-commons/loadbalancer.html).
- [Spring Cloud Commons 5.0.4 — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html) and [LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html) (check the version shown at the top of the page because the latest link can change).

The core of property cross-checking is tracking **the right version, the right scope, the right activation conditions, and real operational evidence**. That gives per-service load-balancing configuration a clear verification basis when combining discovery, health checks, routing policies, retries/timeouts, and different HTTP clients in a microservices system.
