# Comparing Predicate and Filter Default Changes When Upgrading Spring Cloud Gateway

When upgrading Spring Cloud Gateway, a route may still start up normally yet pick a different backend, stop matching a legacy URL, or handle headers differently. The root cause often lies in default behaviors of predicates, filters, the path parser, or the underlying HTTP layer bundled with the new version. Therefore, you should compare the actual behavior of the running version against the target version before deploying.

This article explains how to inventory and compare defaults affecting route predicates and filter chains. The focus is on Gateway Server WebFlux. If the application switches between Gateway Server WebFlux and Gateway Server MVC, treat that as a separate architectural migration: do not assume the two servers share the same set of predicates, filters, execution model, or default values.

## 1. Identify the Exact Two Versions to Compare

Do not infer the Spring Cloud Gateway version solely from the Spring Boot version. Gateway is managed through a Spring Cloud release train; the release train in turn has a compatibility matrix with Spring Boot and Spring Framework. Before comparing, record the exact values of:

- The Spring Boot and Spring Framework versions.
- The Spring Cloud release train version imported via the BOM.
- The actual resolved Gateway artifact version, such as `spring-cloud-starter-gateway` or the starter corresponding to the architecture in use.
- Any dependency overrides, direct dependencies, and profile configurations that could alter behavior.

Example of checking dependencies with Gradle:

```bash
./gradlew dependencyInsight \
  --dependency spring-cloud-gateway-server \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency spring-web \
  --configuration runtimeClasspath
```

With Maven, use `mvn dependency:tree` and filter for Gateway, Spring WebFlux, Spring Framework, and Reactor Netty artifacts. Save the output for both the current version and the target version. If dependencies are managed via a BOM, inspect the imported BOM instead of editing only a single starter's version.

Several common version ranges to guide verification:

| Platform branch | What to check during comparison |
|---|---|
| Gateway 3.x on Spring Boot 2 / Framework 5 | Check differences when moving to Boot 3 / Framework 6, especially foundational changes and Jakarta namespaces |
| Gateway 4.x on Spring Boot 3 / Framework 6 | Compare Gateway minor releases, release trains, and Spring Framework 6.x changes |
| Newer Gateway branches | Select the corresponding official BOM and compatibility matrix; do not mix Gateway, Boot, and Framework versions independently |

This table only guides which groups of changes to inspect; it does not replace the Spring Cloud compatibility matrix. There is no single list of default changes applicable to every upgrade: the outcome depends on the source/target version pair and application configuration.

## 2. Understand the Layers That Form Default Behavior

A running route is not governed solely by the YAML lines written directly inside that route. When comparing, inventory these layers as well:

1. **Route definition:** `id`, `uri`, `order`, predicates, and filters declared directly.
2. **Default filters:** filters configured under `spring.cloud.gateway.default-filters`, applied across multiple routes.
3. **Global filters:** `GlobalFilter` beans auto-configured by Gateway or supplied by the application; these can apply to all routes.
4. **HTTP headers filters:** `HttpHeadersFilter` instances that process headers before Gateway sends the request upstream, such as stripping hop-by-hop headers or generating forwarded headers.
5. **Platform configuration:** properties from Spring Boot, Spring Framework, WebFlux, Reactor Netty, load balancer, security, and other libraries.
6. **Dynamic route sources:** Java `RouteLocator`, `RouteDefinitionLocator`, discovery locator, or configurations loaded from Config Server and the deployment environment.

When multiple sources declare the same property, the effective value depends on Spring Boot's binding mechanism and configuration precedence order. Inspect `application.yml`, profile-specific files, environment variables, command-line arguments, and Java configuration. Reading only the default YAML in the repository can miss configuration actually running in production.

Distinguish three concepts:

- **Factory default value:** the value a predicate/filter factory uses when a parameter is omitted.
- **Effective configuration value:** the value after Spring binds properties, applies profiles, and resolves overrides.
- **Observed behavior:** the final outcome after combining routes, filters, global filters, the HTTP client, and external proxies.

Comparing all three layers helps avoid mistaking an environment configuration difference for a library default change.

## 3. Compare Route Predicates

Predicates are combined with an AND condition within the same route. A route is selected only when all of its predicates match. When multiple routes can match the same request, route `order` and specific conditions decide which route wins. Consequently, a small change in matching behavior can send a request to another route even though the old route configuration still exists.

### Path: trailing `/` and the pattern parser

`Path` is a top-priority predicate to test when upgrading. Trailing slash matching behavior involves both the Gateway version and Spring Framework's pattern parser. In Spring Framework 6, `PathPatternParser` no longer matches an optional trailing separator by default as before. However, do not deduce all Gateway behavior from this platform change alone: each Gateway version has its own configuration for the Path predicate, which may include a `matchTrailingSlash` parameter.

Suppose a route is declared as:

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: order-detail
          uri: lb://order-service
          predicates:
            - Path=/api/orders/{id}
```

Test each of the following requests separately on both versions:

| Request | What to verify |
|---|---|
| `/api/orders/42` | Does the canonical path match |
| `/api/orders/42/` | Is the trailing `/` still accepted |
| `/api/orders/42/items` | Does the pattern unintentionally match a deeper path |
| `/API/orders/42` | Did case-sensitivity rules change |
| `/api/orders/a%2Fb` | Does encoded slash handling match backend and proxy expectations |

Do not rely on a request returning `404` alone to conclude that the Path predicate did not match. The request may have matched the route while the upstream returned `404`; inspect the route ID, routing logs, and post-filter path.

If both trailing-slash and non-trailing-slash forms are valid API paths, explicitly declare both patterns using the syntax of your Gateway version, or normalize URLs at a controlled layer. Example configuring multiple patterns within a single Path predicate:

```yaml
predicates:
  - Path=/api/orders/{id},/api/orders/{id}/
```

Do not declare two separate `Path` lines in the same route to represent two alternatives: separate predicates in a route are combined together, requiring the request to satisfy both. After making changes, test URLs both with and without the trailing `/`.

### Other predicates that need representative test cases

| Predicate | Defaults or behaviors to compare | Recommended test cases |
|---|---|---|
| `Host` | How hostname patterns are matched and how host is extracted from the request | Primary host, subdomain, mixed-case host, request without a valid host |
| `Method` | Accepted method set; whether undeclared methods get caught by another route | GET, HEAD, POST, OPTIONS, and unsupported methods |
| `Header` | Header name, regex expression, and handling of missing headers | Valid header, case differences, missing header, values with special characters |
| `Query` | Distinguishing presence of a query parameter vs regex-matched values | Missing parameter, empty parameter, repeated parameters, Unicode or encoded values |
| `Cookie` | Cookie parsing and regex matching | Missing cookie, multiple cookies, values containing characters needing escaping |
| `RemoteAddr` | Actual peer address vs address supplied by a trusted proxy | Direct call, via ingress, via multiple proxies, and spoofed forwarding headers |
| `Between` | Time boundaries, timezones, and day/hour transitions | Before boundary, exact boundary, after boundary, non-UTC timezones, and DST if applicable |
| `Before` / `After` | Whether boundaries are inclusive or exclusive by version | Request right before, at the exact timestamp, and right after the mark |
| `Weight` | Group, weights, route selection, and impact when routes change | Multiple routes in one group, distribution ratio under load, and when a route is removed |
| `XForwardedRemoteAddr` | Header used to determine client address and proxy trust | Multi-address chains, untrusted proxies, and client-supplied headers |

For `RemoteAddr` in particular, never trust arbitrary `X-Forwarded-For` values sent directly by clients. If Gateway sits behind a proxy, use only a resolver and trusted proxy count matching the real topology. Misconfiguration can cause predicates to route based on spoofed addresses, affecting ACLs, rate limiting, or tenant isolation.

For `Between`, `Before`, and `After`, use timestamps with explicit timezones and test right at the boundaries. A route working in a UTC environment may match differently in an environment using a local timezone if timestamp configurations are inconsistent.

## 4. Compare the Filter Chain

Filters can modify the request before calling upstream or modify the response before returning to the client. When upgrading, verify parameter values, execution order, and effects on bodies/headers.

### Filter ordering and scope

Filters declared in routes, `default-filters`, and `GlobalFilter` beans can all participate in request processing. Gateway combines compatible filters and sorts them by `Ordered`. Pre-filters execute in ascending order; post-filters execute as the chain unwinds, typically in reverse order. Do not infer order solely from YAML line position if a filter defines its own `order`.

Example default filter configuration:

```yaml
spring:
  cloud:
    gateway:
      default-filters:
        - AddRequestHeader=X-Gateway, edge
        - RemoveRequestHeader=X-Internal-Debug
```

These filters apply broadly to routes covered by that configuration. If a specific route needs to preserve a removed header or requires a different header value, check filter order and scope to avoid conflicts. Do not assume route-declared filters always run before or after all global filters.

For custom filters, explicitly declare `getOrder()` or implement `Ordered` whenever order is part of the contract. Verify ordering through logs containing route IDs and correlation IDs, not merely bean names.

### Filters with notable default parameters

Several defaults frequently have a direct impact on production behavior:

| Filter | Common default values in Gateway Server WebFlux | What to check when upgrading |
|---|---|---|
| `Retry` | Default retries is 3; default method is GET; default series is 5XX; default exceptions include I/O errors and timeouts; backoff is not enabled automatically | Re-check retry count, methods, status series, exceptions, backoff, jitter, and whether the body is replayable |
| `RequestRateLimiter` with Redis limiter | `replenishRate`, `burstCapacity`, and `requestedTokens` typically default to 1 if omitted | Confirm key resolver, token units, Redis script, rejection response, and effective per-route values |
| `DedupeResponseHeader` | Default strategy is typically `RETAIN_FIRST` | Check duplicate headers added by both upstream and Gateway, especially CORS headers |
| `StripPrefix` | Number of segments to strip must be configured in the filter; do not rely on an implicit value for routes | Check incoming path, forwarded path, and trailing `/` cases |
| `RewritePath` | Regex and replacement supplied by configuration | Check YAML escaping, capture groups, encoded paths, and the path received by the backend |
| `CircuitBreaker` | Does not automatically create circuit breakers for every route just because the starter is present; routes must declare the filter and proper config | Check circuit breaker name, open/closed state, fallback, and implementation timeouts |
| `SetPath`, `PrefixPath`, `AddRequestHeader`, `SetRequestHeader`, `RemoveRequestHeader` | Values to modify are specified in filter parameters | Check headers/paths before and after the filter, ordering across filters, and impact on request signatures |

Values in this table are common reference checkpoints, not a guarantee that every minor release, starter, or implementation keeps them unchanged. Verify directly against the metadata and source code of the resolved Gateway artifact in both versions. In particular, `RequestRateLimiter` may use a limiter other than Redis; in that case, defaults and token calculations depend on the configured implementation.

### Retry: small changes can generate heavy load

Do not treat retry as a free reliability boost. For instance, a GET request returning 5XX may be retried under default configuration. When upgrading, if the retry count, method set, or exception set changes, upstream traffic during outages can spike dramatically.

Example explicit configuration to avoid implicit dependence on defaults:

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-read
          uri: lb://catalog-service
          predicates:
            - Path=/catalog/**
          filters:
            - name: Retry
              args:
                retries: 2
                methods: GET
                series: SERVER_ERROR
                exceptions:
                  - java.io.IOException
                  - java.util.concurrent.TimeoutException
```

This example restricts retries to GET requests and server errors. For POST/PUT or requests with bodies, enable retry only when an idempotency key or mechanism guaranteeing no duplicate transactions is in place. If backoff is used, calculate total wait time and attempt counts so they do not exceed the client deadline. Retry must also be evaluated alongside circuit breakers to avoid amplifying load while an upstream is degraded.

### RequestRateLimiter: verify keys and limit units

Rate limit values are meaningful only when the key resolver returns the right key. A shared key for all clients can cause every user to share one bucket; an IP-based key can fail if Gateway does not handle forwarded headers properly.

Example Redis limiter configuration with explicit values:

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: public-api
          uri: lb://public-api
          predicates:
            - Path=/public/**
          filters:
            - name: RequestRateLimiter
              args:
                redis-rate-limiter.replenishRate: 20
                redis-rate-limiter.burstCapacity: 40
                redis-rate-limiter.requestedTokens: 1
```

The example above only illustrates Redis limiter parameters; the application still needs an appropriate `KeyResolver` configured and a healthy Redis instance. When comparing versions, also test unresolved keys, Redis timeouts, and responses when requests are rejected. Do not use an IP from a header not authenticated by a trusted proxy as the rate-limit key.

## 5. Compare Header Filters and Header Forwarding

Headers are prone to unexpected changes because Gateway applies filters at multiple layers. Check at least:

- **Hop-by-hop headers:** Gateway includes a filter that strips hop-by-hop headers before sending requests upstream. Check headers such as `Connection`, `Keep-Alive`, `Proxy-Authenticate`, `Proxy-Authorization`, `TE`, `Trailer`, `Transfer-Encoding`, and `Upgrade` in the proper protocol context. WebSocket has its own upgrade handling; do not manually strip or inject handshake headers just to make regular requests work.
- **Forwarded headers:** verify how `Forwarded` and `X-Forwarded-*` headers are generated, appended, or preserved. Cross-check `for`, `host`, `port`, `proto`, and `prefix` against the actual proxy topology.
- **Duplicate headers:** check CORS headers, `Set-Cookie`, `Cache-Control`, `Vary`, and headers added by both Gateway and upstream. Do not apply one blanket dedupe strategy to all headers; `Set-Cookie` has multi-value semantics and needs careful handling.
- **Sensitive headers:** confirm that tokens, internal cookies, and identity headers are not forwarded to services outside the trust boundary.
- **Casing and encoding:** header names are case-insensitive per HTTP, yet custom code or downstream systems may handle them poorly. Test values containing Unicode, commas, and multiple header values.

If Gateway sits behind an ingress or load balancer, accept forwarded headers only from trusted proxies. Allowing clients to send `X-Forwarded-For` or `X-Forwarded-Proto` directly without sanitizing headers at the trusted edge can cause the application to log wrong IPs, construct fake HTTPS URLs, or bypass address-based security policies.

## 6. Build a Default Comparison Table for Source and Target Versions

Do not write only “changed” or “unchanged”. For each predicate/filter in use, record the configured value, the artifact's default value, and the actual request result.

| Field to record | Example |
|---|---|
| Route ID | `order-detail` |
| Component | `Path` predicate |
| Source / target version | Resolved Gateway artifact version |
| Configured value | `/api/orders/{id}` |
| Source / target default | `matchTrailingSlash` and parser behavior per version |
| Test request | `/api/orders/42/` |
| Source / target result | matched route ID, status, and upstream path |
| Impact | compatibility, security, upstream load, or observability |
| Remediation | explicitly declare pattern or normalize path |

You can maintain this table inside the upgrade pull request so reviewers see which routes are affected and why configuration changes are required.

### Minimum test matrix

| Group | Test cases |
|---|---|
| Path predicate | canonical path, trailing slash, deeper path, casing, encoded path |
| Host / Header / Query / Cookie | matching, non-matching, missing, repeated, and special characters |
| Method | GET, HEAD, POST, OPTIONS, and unsupported methods |
| RemoteAddr / forwarded | direct call, through each proxy, multiple addresses, and spoofed headers |
| Time predicates | before boundary, on boundary, after boundary, timezone, and DST if applicable |
| Route order / Weight | multiple matching routes, priority route, load distribution, and removed route |
| Request filters | headers/paths before and after filter, auth context, retry, and rate limit |
| Response filters | status, duplicate headers, CORS, body streaming, upstream errors, and committed response |
| Global/default filters | routes with and without custom filters, custom filters, and pre/post ordering |

A test that asserts only the status code is usually insufficient. Record the matched route ID, upstream URI, method, path, key headers, and the actual number of requests reaching the backend. For retry or weight, use an upstream request counter to verify behavior rather than observing only the final response.

## 7. Write Regression Tests for Routes

Create tests for edge cases before changing dependencies. For WebFlux applications, `WebTestClient` can send requests through Gateway running in the test context; the target backend can be replaced with a stub server or mock service with a request counter.

Example test skeleton for two path forms:

```java
@AutoConfigureWebTestClient
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GatewayPathCompatibilityTest {

    @Autowired
    WebTestClient client;

    @Test
    void routesCanonicalOrderPath() {
        client.get()
            .uri("/api/orders/42")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void handlesTrailingSlashAccordingToApiContract() {
        client.get()
            .uri("/api/orders/42/")
            .exchange()
            .expectStatus().isOk();
    }
}
```

This is an illustrative skeleton. You need to initialize an upstream stub, configure a dynamic port, and assert responses per the service contract. If the API intentionally rejects trailing slashes, the second test must verify the status and matched route according to that policy instead of forcing it to return `200`.

To test the filter chain, the upstream stub can echo back the request method, path, and non-sensitive headers as JSON. The test then verifies what Gateway actually sent. For response filters, make the upstream return duplicate headers or a multi-part stream to verify Gateway preserves response semantics.

Run the exact same test suite against both source and target dependencies. If profiles or dynamic routes are used, load equivalent configuration in both runs. Do not use two different fixture sets, as that makes the comparison meaningless.

## 8. Safe Upgrade Process

1. **Lock versions:** record the BOM, Boot, Framework, Gateway, and HTTP client dependencies of both current and target versions.
2. **Inventory routes:** export all static routes, Java routes, discovery routes, and routes loaded from external config. Record `order`, predicates, filters, and metadata.
3. **Collect effective configuration:** merge profiles, environment variables, command-line flags, and Config Server settings. Flag properties that rely on defaults.
4. **Prioritize sensitive components:** Path/trailing slash, `RemoteAddr`, forwarded headers, Retry, RequestRateLimiter, CircuitBreaker, response rewrites, and streaming.
5. **Run regression tests on source version:** save route IDs, upstreams, statuses, headers, upstream call counts, and processing times as a baseline.
6. **Bump BOM on a dedicated branch:** do not override individual Spring Framework or Gateway dependencies unless the compatibility matrix requires it. Resolve compile/configuration warnings and API changes before evaluating runtime behavior.
7. **Run the same tests on target version:** compare each result against the baseline. For any discrepancy, determine whether it is an intentional change, a default change, or environment configuration drift.
8. **Explicitly declare critical defaults:** specify the values the system depends on, such as path patterns, retries, rate limits, and header strategies. Document the rationale so future upgrades do not have to guess.
9. **Canary and observe:** monitor route distribution, 4xx/5xx errors, retry counts, rate limit rejections, circuit breaker state, latency, and upstream requests.
10. **Complete or rollback:** expand rollout only when route and filter behavior satisfy the contract. Keep the ability to roll back dependencies and configuration together.

## 9. Pre-Merge Review Checklist

- [ ] Resolved Gateway version matches the BOM and Boot/Framework compatibility matrix.
- [ ] Direct configs, `default-filters`, global filters, and HTTP headers filters have all been compared.
- [ ] Path predicates have been tested with trailing slashes, encoded paths, and case sensitivity.
- [ ] `Host`, `Method`, `Header`, `Query`, `Cookie`, `RemoteAddr`, and time predicates have tests covering active routes.
- [ ] Route order and weights do not divert requests to a different backend.
- [ ] Retries have appropriate methods, attempt counts, status/exceptions, and backoff; non-idempotent requests are protected.
- [ ] Rate limiter has a trusted key resolver, correct token units, and Redis failure behavior tested.
- [ ] Header forwarding and hop-by-hop headers are tested through the real proxy topology; spoofed headers are not trusted.
- [ ] Custom filters have explicit ordering and do not write responses twice or unintentionally consume streaming bodies.
- [ ] Source/target regression tests use identical fixtures and compare route IDs, upstreams, headers, bodies, and backend call counts.
- [ ] Canary has sufficient metrics and logs to detect behavioral changes after rollout.

A safe upgrade requires knowing exactly which request matches which route and which filter altered the request/response. When key values are inventoried, explicitly declared, and tested on both source and target versions, default changes become observable differences that can be addressed before impacting production.
