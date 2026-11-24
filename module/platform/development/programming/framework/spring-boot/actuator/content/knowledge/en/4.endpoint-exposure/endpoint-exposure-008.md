# Customizing Endpoint Paths with base-path and path-mapping

## 1. Distinguishing Endpoint Names from HTTP Addresses

A system may need to use `/manage` as its management area, or need the health check address to be `/healthcheck` to match deployment tooling. Actuator allows configuring these addresses without having to write extra controllers just to forward requests.

This article applies to **Spring Boot 3.3.x**, referencing documentation 3.3.13. Two properties must be distinguished:

| Property | Role | Example |
| --- | --- | --- |
| `management.endpoints.web.base-path` | Common prefix for Actuator endpoints over HTTP | `/manage` |
| `management.endpoints.web.path-mapping.<id>` | Maps an endpoint's ID to a custom path segment | `health=status` |

By default, the prefix is `/actuator` and the individual path segment is usually derived from the ID. Thus ID `health` is accessed via `/actuator/health`. When changing both properties as in the table above, the path becomes `/manage/status`. [Customizing HTTP Management Paths in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html#actuator.monitoring.customizing-management-server-context-path).

Keep three concepts separate:

- **ID:** identifier such as `health`, used in enable/disable and exposure configuration.
- **Mapped path:** HTTP address such as `/manage/status`.
- **Data and operations:** the endpoint still checks health; its functionality does not change because the path name changed.

Spring Boot also has an API model distinguishing endpoints by ID and mapped path. [`PathMappedEndpoints` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/PathMappedEndpoints.html).

## 2. Changing Only the Common Prefix with base-path

Suppose the application shares port 8080, with no application context path. Configuration:

```yaml
management:
  endpoints:
    web:
      base-path: /manage
      exposure:
        include:
          - health
          - info
```

HTTP paths change according to the new prefix:

| Endpoint | Default path | Path after configuration |
| --- | --- | --- |
| `health` | `/actuator/health` | `/manage/health` |
| `info` | `/actuator/info` | `/manage/info` |

`base-path` changes the common part, so there is no need to declare each endpoint individually just to replace `actuator`. Unexposed endpoints do not automatically appear simply because there is a new prefix.

Equivalent example in `application.properties`:

```properties
management.endpoints.web.base-path=/manage
management.endpoints.web.exposure.include=health,info
```

These are two representations of the same configuration; use one consistent format in an application. Web management properties are grouped under the `management.endpoints.web` prefix. [`WebEndpointProperties` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/endpoint/web/WebEndpointProperties.html).

Changing the prefix does not automatically create the old address as an alias or an HTTP redirect rule. With a test application having no extra mappings, after switching to `/manage`, call `/manage/health` instead of `/actuator/health`.

## 3. Changing Each Endpoint's Path with path-mapping

Example changing `health` to `status` and `metrics` to `meters`, while using the `/manage` prefix:

```yaml
management:
  endpoints:
    web:
      base-path: /manage
      exposure:
        include:
          - health
          - metrics
      path-mapping:
        health: status
        metrics: meters
```

Result when the endpoints are eligible to run:

| Endpoint ID | Mapped value | HTTP path |
| --- | --- | --- |
| `health` | `status` | `/manage/status` |
| `metrics` | `meters` | `/manage/meters` |

Note the details:

- Write the mapping key as the original ID: `health:`, not `status:`.
- In the example, the value `status` is only the individual path segment; do not repeat `/manage` in that value.
- The exposure list still contains `health`, `metrics`. Do not change it to `status`, `meters`.
- If you need to set an individual enabled state, still use `management.endpoint.health.enabled`; do not invent an enablement key for the path name `status`.

If you only need to change `health` individually and keep the default prefix, the shorter configuration is:

```properties
management.endpoints.web.path-mapping.health=status
```

With this standalone configuration, the address is `/actuator/status`. Changing only the mapping segment does not automatically remove the `/actuator` prefix.

### Operation Paths Under an Endpoint

The `metrics` endpoint has an operation to read a single metric following the pattern `/{metric.name}`. When the endpoint's root mapping becomes `meters`, an example URL to read a metric becomes:

```text
GET /manage/meters/jvm.memory.used
```

The `jvm.memory.used` part is the selected metric name, not an endpoint ID to declare in `path-mapping`. The metric selection structure still belongs to the metrics API; actual data depends on the meters the application has registered. [Metrics Endpoint Metric-Reading API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

## 4. Composing Paths When Sharing the Application Port

To determine the address, you must account for the application's base path in addition to the two Actuator properties.

Composition model, with appropriate `/` separators:

```text
Application base path
    + Actuator base-path
    + endpoint mapping segment or default ID
    + operation path segment, if any
```

### 4.1. Servlet Applications

With Spring MVC/Servlet, when sharing the port, the relevant base path is `server.servlet.context-path`.

```yaml
server:
  port: 8080
  servlet:
    context-path: /shop

management:
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health
      path-mapping:
        health: status
```

Address of `health` in the example:

```text
http://localhost:8080/shop/manage/status
```

If you call `http://localhost:8080/manage/status`, you omitted the `/shop` segment. These examples assume no additional servlet path configuration or proxy URL rewriting.

### 4.2. Reactive Applications

With Spring WebFlux, when sharing the port, consider `spring.webflux.base-path` instead of `server.servlet.context-path`:

```yaml
server:
  port: 8080

spring:
  webflux:
    base-path: /api

management:
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health
      path-mapping:
        health: status
```

Address in the reactive example:

```text
http://localhost:8080/api/manage/status
```

The Servlet and Reactive configuration snippets are two independent cases. There is no need to set both kinds of base paths simultaneously "just to make sure it works."

The relationship between application path and `management.endpoints.web.base-path` is stated in [Spring Boot 3.3 Property Catalog](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#appendix.application-properties.actuator).

## 5. When Separating to a Dedicated Management Port

If the management port **differs** from the application port, the management server's base path is configured with `management.server.base-path`. Do not append the application server's context path onto the management URL.

Servlet example:

```yaml
server:
  port: 8080
  servlet:
    context-path: /shop

management:
  server:
    port: 9091
    base-path: /ops
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health
      path-mapping:
        health: status
```

Read each layer:

| Component | Value |
| --- | --- |
| Application port | `8080` |
| Application context path | `/shop` |
| Separate management port | `9091` |
| Management server base path | `/ops` |
| Web endpoint prefix | `/manage` |
| Mapped segment for health | `status` |

Resulting management URL:

```text
http://localhost:9091/ops/manage/status
```

Do not compose it as `http://localhost:9091/shop/ops/manage/status`. `/shop` belongs to the application server configuration in the example, whereas the management URL uses its own base path.

`management.server.base-path` requires a separate management port; `management.endpoints.web.base-path` remains the endpoint prefix inside that management area. [Management Server Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#appendix.application-properties.actuator).

Quick deduction table from the examples, all mapping `health=status`:

| Case | Final URL |
| --- | --- |
| Shared port, no app base path, Actuator `/manage` | `http://localhost:8080/manage/status` |
| Shared port Servlet, context `/shop`, Actuator `/manage` | `http://localhost:8080/shop/manage/status` |
| Shared port WebFlux, base `/api`, Actuator `/manage` | `http://localhost:8080/api/manage/status` |
| Separate port 9091, management base `/ops`, Actuator `/manage` | `http://localhost:9091/ops/manage/status` |

## 6. Moving an Endpoint to the Root and the Effect on the Discovery Page

If `/healthcheck` is needed right at the root, in an application sharing the port with no extra base path:

```yaml
management:
  endpoints:
    web:
      base-path: /
      exposure:
        include: health
      path-mapping:
        health: healthcheck
```

New address:

```text
http://localhost:8080/healthcheck
```

If you keep the default `base-path` and only map `health=healthcheck`, the result will be `/actuator/healthcheck`. It is `base-path: /` that moves Actuator's prefix to the root. If the application has a context path, that base still applies; for example, Servlet sharing a port with `/shop` will have `/shop/healthcheck`.

### The Discovery Page Is Not the health Endpoint

Actuator normally has a link discovery page at the common prefix: `/actuator` by default; with `base-path=/manage`, the links can be found at `/manage`, with the corresponding base path/port.

In the shared-port example above, when setting Actuator's prefix to `/`, this discovery page is disabled to avoid conflicting with the application's root mapping. That does not mean the `/healthcheck` endpoint is disabled. Nor can you conclude that URL `/` will return 404, because the application may have its own home page. [Actuator Link Discovery Page](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.hypermedia).

There is a difference to consider when separating ports: in **Spring MVC 3.3.13**, the link-registration code still allows the discovery page when a separate management port is active and discovery is enabled, even when the endpoint prefix is at the root. Therefore, the auto-disable conclusion above is limited to the shared-port case. This is a direct deduction from [link registration conditions in Spring MVC 3.3.13 code](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/endpoint/web/servlet/WebMvcEndpointManagementContextConfiguration.java), which is more detailed than the short description in the user guide.

If the requirement is to intentionally disable the discovery page, explicitly set the following property rather than inferring from the path:

```properties
management.endpoints.web.discovery.enabled=false
```

When moving endpoints near the root, choose paths that do not collide with business controllers or other endpoints. For example, do not map two different endpoints both to `status`.

## 7. Hands-on Verification of Old and New Paths

### Conditions of the Test Exercise

Use a Spring Boot 3.3.x application that has a main class with `spring-boot-starter-web` and `spring-boot-starter-actuator`, Java 17 or higher. No controller needs to be added to customize paths.

Test application assumptions:

- Uses HTTP port 8080, no context path.
- No Spring Security or proxy altering results.
- No controller colliding with the URLs being tested.
- No other configuration source overriding values; overall health status is `UP`.

The following results are expected results under these conditions.

### Hands-on Configuration

Use the following content in `src/main/resources/application.yml` of the test application:

```yaml
server:
  port: 8080

management:
  endpoints:
    enabled-by-default: false
    web:
      base-path: /manage
      exposure:
        include:
          - health
          - metrics
      path-mapping:
        health: status
        metrics: meters
  endpoint:
    health:
      enabled: true
    metrics:
      enabled: true
```

Start the application using the project's normal launch method. In PowerShell on Windows, run sequentially:

```powershell
curl.exe --silent --output NUL --write-out "%{http_code}\n" "http://localhost:8080/manage/status"
curl.exe --silent --output NUL --write-out "%{http_code}\n" "http://localhost:8080/actuator/health"
curl.exe --silent --output NUL --write-out "%{http_code}\n" "http://localhost:8080/manage/health"
curl.exe --silent --output NUL --write-out "%{http_code}\n" "http://localhost:8080/manage/meters"
```

Expected stdout when running the four commands in exact order:

```text
200
404
404
200
```

Explanation:

- `/manage/status` uses the right new prefix and new mapped segment.
- `/actuator/health` uses the old address.
- `/manage/health` updated the prefix but still uses the old individual path segment.
- `/manage/meters` is the new path of endpoint ID `metrics`.

The commands use `--output NUL` to discard the body and print only the HTTP code, each followed by a newline. To inspect health data:

```powershell
curl.exe --silent "http://localhost:8080/manage/status"
```

Under `UP` status without details disclosed, the commonly seen JSON response is:

```json
{"status":"UP"}
```

Path configuration does not guarantee the application is always healthy; the health API reflects component statuses and may contain further details. [`health` API Structure](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/health.html).

To verify that the metric-selection operation is preserved:

```powershell
curl.exe --silent "http://localhost:8080/manage/meters/jvm.memory.used"
```

Check the corresponding `name` field, rather than trying to match the memory value which changes over time. If you need to test the URL tables in section 4 or 5, use each configuration independently and restart the application before testing.

## 8. What Changing Paths Does Not Automatically Do

### Does Not Change Enablement or Exposure Decisions

`base-path` and `path-mapping` select the address. The endpoint still must be enabled, exposed over HTTP, and satisfy required component creation conditions. Changing the path of `metrics` does not undo `management.endpoint.metrics.enabled=false` or `web.exposure.exclude=metrics`. [Endpoint Exposure Conditions](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing).

### Does Not Change IDs in JMX

Both properties reside under `management.endpoints.web` and adjust web paths. Do not conclude that the health MBean is renamed to `status`. JMX has its own naming/domain mechanism and must be configured separately. [Endpoint MBean Names over JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

### Does Not Automatically Update Callers or Endpoint Protection

After changing URLs, review places holding old addresses: deployment platform health checks, monitoring tools, operational scripts, proxy rules, and security rules written against specific URLs.

Renaming `/actuator` to a hard-to-guess name does not replace authentication, authorization, or connection restrictions. If Spring Security is present, verify protection rules still apply to the new paths; do not remove protection just to make curl commands succeed.

The URLs in this article are direct application addresses. When a proxy adds/strips prefixes or changes external ports, distinguish the caller-facing URL from the URL the application actually receives.

## 9. Common Mistakes and Verification Order

| Symptom | What to check |
| --- | --- |
| Changed to `/manage` yet still calling `/actuator/health` | Update the URL prefix |
| Calling `/manage/health` after mapping `health=status` | Use the new mapped segment `status` |
| Using `include=status` and not seeing health | The exposure list must use ID `health` |
| Calling `/manage/status` in a Servlet app with `/shop` context | Prepend `/shop` when sharing the port |
| Separated port yet still calling port 8080 | Use the management port and its base path |
| Discovery page missing when sharing port with `base-path=/` | Test a specific endpoint; root discovery page is disabled |
| File has new URLs yet app still uses old URLs | Check active profiles, effective values, and latest restart |

Configuration sources such as environment variables or command-line arguments can override file contents. For example, `--management.endpoints.web.base-path=/ops` can make the actual prefix differ from `/manage` in YAML. [Spring Boot Configuration Source Order](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

When encountering an error, write down the facts: **protocol, port, app base path, base-path, ID, path-mapping, enable/expose state**. Then compute the URL before editing configuration. A 404 code only indicates the requested resource was not found in that situation; if there is a security filter or proxy, also check how they process the request.

## 10. Computing URLs Before Running

**Scenario 1:** No app base path, `base-path=/ops`, `path-mapping.health=ready`, shared port 8080.

Address: `http://localhost:8080/ops/ready`. The endpoint ID remains `health`; the name `ready` in this example does not automatically create a readiness group.

**Scenario 2:** Servlet with `/billing` context, shared port 8080, `base-path=/monitor`, no custom mapping for health.

Address: `http://localhost:8080/billing/monitor/health`.

**Scenario 3:** Application port 8080 has `/billing` context, separate management port 9091 has `management.server.base-path=/internal`, `base-path=/monitor`, mapping `health=alive`.

Address: `http://localhost:9091/internal/monitor/alive`. Do not add `/billing`.

**Scenario 4:** No app base path, shared port, `base-path=/`, mapping `health=healthcheck`.

Address: `http://localhost:8080/healthcheck`; Actuator's root discovery page is disabled, while the health endpoint can still function when conditions are met.
