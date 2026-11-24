# Distinguishing Management Endpoints from Business APIs

## 1. Two Different Needs in the Same Application

An order-management application must serve at least two groups of needs:

- Customers want to view orders, place orders, or request cancellations according to store rules.
- Operators want to know whether the application is healthy, which version is running, how processing metrics look, and whether operational settings need adjustment.

The first group belongs to **business APIs**: interfaces that execute or query domain capabilities. The second belongs to **management/operational interfaces**: helping observe, diagnose, and control a running application.

In Spring Boot, Actuator provides endpoints for operations. For instance, `health` returns application status information, while `loggers` lets you inspect and adjust logging levels. An application can still have custom-built operational tools outside Actuator.

**The crucial distinction is purpose and usage contract**, not merely URL prefix, HTTP method, or whether a caller has the job title “administrator”.

For example:

~~~text
GET  /api/orders/DEMO-001        → view a single order
POST /api/orders/DEMO-001/cancel → request order cancellation per business rules

GET  /actuator/health            → view application status
GET  /actuator/metrics           → discover application metrics
~~~

These paths illustrate the classification. They exist only when the application implements or configures them accordingly.

## 2. Comparing by Responsibility

| Criterion | Business API | Management / Operational Endpoint |
| --- | --- | --- |
| Primary question | What capabilities does the system provide to users or other systems? | How is the application running and how should it be operated? |
| Data subjects | Orders, products, payments, accounts | Health, build info, metrics, operational configuration |
| Typical consumers | User UI, mobile apps, partners, other services | Monitoring tools, health probes, operators |
| Key rules | Data ownership, valid states, business consistency | Scope of visible info, action permissions, infrastructure reachability |
| Consequence of misuse | Reading wrong data, modifying wrong orders, invalid transactions | Leaking technical info, unintended runtime changes, impacting availability |
| Contract to test | Input/output payloads, business rules and outcomes | Diagnostic content, exposure scope, access rights, operational tooling behavior |

### 2.1. “Used by an Admin” Is Not Enough to Classify

A store staff member authorized to issue refunds is still performing **refund business logic**. The refund API must validate the order, amount, permissions, and refund conditions, even if its URL starts with `/admin`.

Conversely, an automated probe calling `health` is not a shopping customer; it uses an operational interface even though no human logged in interactively.

To classify an endpoint, ask: **does the call’s outcome carry meaning in the business domain, or does it describe/adjust application operations?**

### 2.2. Returning JSON or Having a `status` Field Does Not Give the Same Meaning

Two illustrative responses:

~~~json
{"orderId":"DEMO-001","status":"DRAFT"}
~~~

~~~json
{"status":"UP"}
~~~

`DRAFT` is an order state in the business model. `UP` is a health status aggregated by the health subsystem. Read each endpoint’s contract to interpret its payload.

A healthy status response does not confirm an order was paid or cancellation rules ran properly. Conversely, successfully reading an order does not prove all application dependencies are healthy.

## 3. How Are Actuator Endpoints Structured?

### 3.1. Endpoint ID vs. HTTP Path

In Actuator, an endpoint has an ID, such as `health` or `info`, and may expose read/write operations. An Actuator endpoint does not mean exactly one URL; one endpoint can have multiple operations or sub-paths.

With default HTTP configuration, the `health` endpoint is typically reached via `/actuator/health`. Actuator also supports exposing suitable capabilities over other technologies such as JMX. The `@Endpoint` annotation and operation annotations form the dedicated mechanism for these management capabilities. See [Spring Boot 3.3 — Endpoint API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/annotation/Endpoint.html).

Business APIs in Spring MVC are usually written with `@RestController` and mappings such as `@GetMapping` or `@PostMapping`. Simply placing a controller under `/actuator/myOrders` does not make it an Actuator endpoint and does not apply Actuator exposure settings to it.

Therefore, keep distinct URL namespaces for both groups to avoid collisions and keep configuration clear. This is a design choice; the path string itself does not create security protection.

### 3.2. Operational Endpoints Can Also Mutate the Application

Do not assume “management” means read-only. For example, the `loggers` endpoint supports:

~~~text
GET  /actuator/loggers/{logger.name}  → view logging level
POST /actuator/loggers/{logger.name}  → set or clear configured logging level
~~~

Changing logging levels can affect log volume, cost, and emitted information. Thus, permission to view metrics should not automatically grant permission to modify log levels. See [Spring Boot 3.3 — Loggers REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/loggers.html).

Likewise, do not assume every read operation is harmless. Information about beans, configuration, threads, or memory can be sensitive. Evaluate the data and effect of each operation rather than looking only at `GET` vs. `POST`.

### 3.3. Reading Health Within Its Actual Check Scope

Health describes status based on configured components and checks. The `components` and `details` fields can be shown or hidden via configuration; not every caller needs full details.

A successful database connectivity check does not replace testing a complete order-placement flow. When you need to evaluate the ordering experience, verify the corresponding business flow separately. See [Spring Boot 3.3 — Health REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/health.html).

## 4. Separating Three Decisions: Enable, Expose, and Authorize

For an Actuator endpoint over HTTP, distinguish three questions:

1. **Is the endpoint enabled and eligible to be created?** Is it configured as enabled and are its required components present?
2. **Is it exposed over HTTP?** Is the endpoint included in HTTP web exposure?
3. **Is the caller allowed to access it?** Do authentication, authorization, and network rules permit this request?

These are three separate checkpoints, not three names for the same property.

### 4.1. Enabling an Endpoint Differs from Exposing It over HTTP

In Spring Boot 3.3.x, `management.endpoint.<id>.enabled` controls whether an endpoint is enabled. `management.endpoints.web.exposure.include` or `exclude` selects endpoints exposed over HTTP; `exclude` takes precedence when both match. By default, only `health` is exposed over HTTP.

Example:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

This configuration selects `health` and `info` for HTTP exposure when those endpoints are available. It does not create an order API and does not grant callers a security role. See [Spring Boot 3.3 — Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

A variant clarifying the two decisions:

~~~yaml
management:
  endpoint:
    info:
      enabled: false
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Even though `info` appears in `include`, it remains disabled by the `enabled` setting. `include` does not revive a disabled endpoint. Corresponding properties are listed in [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

### 4.2. Authentication and Authorization Remain Separate Responsibilities

**Authentication** identifies who the caller is. **Authorization** determines what that caller is allowed to view or execute.

If Spring Security is on the classpath, Spring Boot provides default security configuration. When an application defines its own `SecurityFilterChain`, do not assume Boot’s default Actuator protection rules remain intact: custom configuration must cover the URLs that need protection. See [Spring Boot 3.3 — Spring Security](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html).

**Illustrative policy example for design**, not Spring Boot defaults:

| Caller | Granted capability |
| --- | --- |
| Shopper | View/act on orders within permitted scope |
| Health probe | Read minimal health result needed for orchestration |
| Monitoring tool | Read approved metric endpoints |
| Operations staff with change rights | Execute specific authorized operational actions |

A “shopper” role must never imply application management rights; nor should an operations role automatically allow reading every customer’s orders.

### 4.3. When You Need to Separate Security Rule Groups

In a Servlet application, `EndpointRequest` builds matchers targeting actual Actuator endpoints. `EndpointRequest.toAnyEndpoint()` also includes the links page at the base path; `EndpointRequest.to("health")` can target the health endpoint specifically. This is safer than assuming every deployment uses one hardcoded path prefix. See [Spring Boot 3.3 — EndpointRequest API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.html).

Multiple `SecurityFilterChain` beans can separate management and business policies. Keep in mind:

- Which filter chain matches a request is decided by matchers and order priority.
- A chain matching only Actuator does not protect the remaining business URLs.
- An appropriate chain must cover the rest; leaving requests unmatched by any chain can leave them unprotected by Spring Security.
- Rules for a read operation do not imply write operations work the same way; mechanisms like CSRF also depend on the authentication model.

These are design guidelines, not a complete configuration to copy blindly into every app. Multiple filter chains are documented in [Spring Security — Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html).

## 5. Same Port vs. Separate Port: Changing Access Path While Keeping Meaning

In common deployments, business APIs and Actuator HTTP endpoints can share one port:

~~~text
127.0.0.1:8080
├── /api/orders/demo   → sample order data
└── /actuator/health   → application health
~~~

You can set `management.server.port` to move management endpoints to a separate port. `management.endpoints.web.base-path` changes the Actuator path prefix. For example:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 8081
  endpoints:
    web:
      base-path: /manage
~~~

Without another root path setting, health moves to `http://localhost:8081/manage/health`. Business APIs stay on the main application port.

Separating the port supports dedicated network routing and access policies, yet **a different port number does not make it private automatically**. Verify bind addresses, published ports, reverse proxies, firewalls, and access rules.

Do not change the base path just to “hide the URL” and treat that as authentication. Nor do you need two separate applications or two Java processes merely to use two ports. Port, address, and base-path options are described in [Spring Boot 3.3 — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

## 6. Experiment: Seeing Both Endpoint Groups Clearly

The following experiment targets **a Spring Boot 3.3.x test project, Java 17 or newer**, with Gradle wrapper, dependency version management, and `bootRun` available. It is not a change to apply across unrelated modules.

The test project uses only Web and Actuator—no Spring Security, no database, and default context path. It binds only to loopback to observe local behavior.

### 6.1. Dependencies and Application Code

Dependency snippet to add to the project’s `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Create `src/main/java/example/boundary/EndpointBoundaryDemoApplication.java`:

~~~java
package example.boundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class EndpointBoundaryDemoApplication {
    @GetMapping("/api/orders/demo")
    public OrderView demoOrder() {
        return new OrderView("DEMO-001", "DRAFT");
    }

    public record OrderView(String orderId, String status) {
    }

    public static void main(String[] args) {
        SpringApplication.run(EndpointBoundaryDemoApplication.class, args);
    }
}
~~~

This is a complete Java file in the project described. The order is hardcoded for demonstration, reading no customer records and writing to no database. The GET endpoint simply returns sample data.

Actuator provides `health` via its own mechanism; the code above declares only the business API. There is no custom controller method for `/actuator/health`.

### 6.2. Run A: Same Port

Set `src/main/resources/application.yml`:

~~~yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Run in the project directory:

~~~powershell
.\gradlew.bat bootRun
~~~

In another terminal window, read the sample data:

~~~powershell
curl.exe --silent --show-error http://127.0.0.1:8080/api/orders/demo
~~~

Expected JSON fields and values:

~~~json
{"orderId":"DEMO-001","status":"DRAFT"}
~~~

JSON field order has no business significance. This is the HTTP response body, not a line printed by Java to stdout.

Next, read health:

~~~powershell
curl.exe --silent --show-error http://127.0.0.1:8080/actuator/health
~~~

If current health checks pass and details are not enabled, the typical response is:

~~~json
{"status":"UP"}
~~~

Both requests hit the same process and port, yet serve two distinct contracts.

You can call `/actuator/info` because it is exposed over HTTP. Content comes from `InfoContributor` beans; if the project contributes nothing, the result may simply be `{}`. Exposure does not generate build info by itself. See [Spring Boot 3.3 — Info REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/info.html).

### 6.3. Run B: Dedicated Management Port

Stop the application. Replace all YAML from Run A with the configuration below and restart:

~~~yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  server:
    address: 127.0.0.1
    port: 8081
  endpoints:
    web:
      exposure:
        include: health,info
~~~

This time, call the address matching each group:

~~~powershell
curl.exe --silent --show-error http://127.0.0.1:8080/api/orders/demo
curl.exe --silent --show-error http://127.0.0.1:8081/actuator/health
~~~

In the standard test configuration above, the expected outcome matrix is:

| Port | Path | Result |
| --- | --- | --- |
| 8080 | `/api/orders/demo` | 200, sample order data |
| 8081 | `/actuator/health` | 200 when health is UP |
| 8080 | `/actuator/health` | 404, endpoint moved to management port |
| 8081 | `/api/orders/demo` | 404, that business API does not exist on the management server |
| 8081 | `/actuator/env` | 404, not exposed over HTTP in this configuration |

To inspect only the status code for one case:

~~~powershell
curl.exe --silent --output NUL --write-out "%{http_code}" http://127.0.0.1:8080/actuator/health
~~~

Expected output:

~~~text
404
~~~

Using `curl.exe` invokes the curl binary on Windows, avoiding PowerShell’s alias differences. The 404 results above apply when there is no colliding controller, URL-rewriting proxy, or extra configuration.

A management port returning healthy status alone does not prove the business path through the main port and proxy works. Verify the actual path used by users as well.

### 6.4. Observing Access Control Conditionally

The example omits Spring Security so mapping differences can be seen in isolation. In a real secured project, an unauthorized request may be intercepted before reaching the endpoint.

Avoid absolute rules such as “404 always means not exposed” or “403 always means wrong role”. Outcomes also depend on filter chains, CSRF, error handlers, and proxies. Inspect config, credentials, and logs instead of inferring a single cause from one HTTP status code.

When using multiple ports in containers or on servers, verify port publishing and the address reachable by monitoring tools. Loopback inside one container is not automatically a loopback reachable by other containers.

## 7. Classifying Easily Confused Cases

### 7.1. Cancelling Orders, Clearing Caches, and Changing Log Levels

- **Cancel order:** modifies a business object’s state; requires cancellation rules, ownership checks, and consistency guarantees.
- **Clear an operational cache:** alters how the application serves traffic and can trigger load spikes; requires operational policy and impact assessment.
- **Change log level:** adjusts diagnostic behavior; not a purchase transaction, yet still an operation with side effects.

Never turn order cancellation into an Actuator endpoint to bypass authentication or business validation. Nor should you leave operational actions public simply because they do not directly edit the orders table.

If “clear cache” is actually part of a user-defined business data refresh workflow, analyze the specific contract. An action’s name alone does not dictate the entire design.

### 7.2. Both Callers Are Internal Services

A payment service calling an API to record payment outcomes interacts with business logic. Prometheus scraping metrics interacts with operational capabilities. Both may be machine-to-machine calls and both need appropriate identity and permissions.

The word “internal” describes deployment scope; it does not replace defining who is permitted to do what.

### 7.3. Custom-Built Operational Tools

An application may need custom operational capabilities. When using Actuator, design an endpoint whose data and operations fit Actuator’s model, then configure exposure and authorization accordingly.

If you use a regular HTTP controller for an operational tool, it must still be protected under the application’s controller/security config. Never assume `management.endpoints.web.exposure.include` governs a controller just because its URL contains “manage”.

Management payloads should describe what needs to be observed or controlled, avoiding dumping every field of business objects or internal configuration merely for convenience.

## 8. Common Misconceptions and How to Check

| Misconception | How to check |
| --- | --- |
| Every URL starting with /admin is Actuator | Determine whether it is a controller or Actuator endpoint, then check its purpose |
| Adding Actuator creates order-creation APIs | Inspect business code; Actuator does not know order rules |
| Including an endpoint means anyone can call it | Check exposure, security, and network path separately |
| Port 8081 is automatically private | Inspect bind address, network routes, proxies, and access control |
| Health UP means all orders process properly | Identify what health checks; test business flows separately |
| Only POST requests need protection | Evaluate both read payloads and side-effecting operations |
| One Actuator chain protects the whole app | Verify chains covering business APIs and remaining paths |
| Internal APIs can skip per-order authorization | Verify caller identity and data-level permissions |

### Self-Practice

1. Classify: view cart, read health, change log level, staff refund, system scraping metrics. Explain by purpose rather than URL prefix.
2. An endpoint is enabled but not in HTTP exposure. Does granting a role to an account make that URL appear?
3. With the separate-port config in the example, predict the four port/path pairs before running curl.
4. Change management base path to `/manage`. State the new health URL and explain why the order API does not need to change.
5. Users call the order API successfully while health reports a dependency `DOWN`. State what information is needed before concluding the app is “healthy” or “broken”.

**Comparison hints:** cart and refunds are business; health, metrics, and log levels are operational. Authorization does not replace exposure. Check actual port/base-path settings. Health and a single business call provide evidence across different scopes.
