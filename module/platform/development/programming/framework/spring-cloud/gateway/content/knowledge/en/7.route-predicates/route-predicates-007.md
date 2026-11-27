# After, Before, and Between: time- and timezone-based routing in Spring Cloud Gateway

When building **SPRING_CLOUD_GATEWAY**, you may want to open an API starting at a specific time, route requests to a promotional backend during a time window, or stop accepting traffic on a route after a deadline. **After**, **Before**, and **Between** are three **Route Predicate Factories** that let Spring Cloud Gateway select routes based on the **current time at Gateway**.

This lesson belongs to the **Route Predicates** chapter and focuses on syntax, timestamp semantics, timezones, matching boundaries, and testing. Only after a route is selected does Gateway execute the filter chain, transform paths/headers, and forward to the service. Authentication, rate limiting, circuit breakers, retries, TLS, and request observability still require separate configuration; they are not guaranteed merely because a time predicate matched.

> **Version scope:** YAML examples use the common configuration style of **Spring Cloud Gateway Server WebFlux 4.x** with the `spring.cloud.gateway.routes` key. Namespaces, starters, and declarations in **Gateway Server MVC** or other release lines may differ. Always check official documentation for the exact **Gateway version, Spring Cloud release train, and variant** you are running.

## 1. At which step do time predicates operate?

Gateway receives an HTTP request, inspects the routes in its routing table, evaluates predicates, and picks a matching route according to ordering rules. For a route with `After`, `Before`, or `Between`, Gateway compares the **current time of the Gateway process** against the configured timestamp.

~~~mermaid
flowchart TD
    A["Client sends HTTP request"] --> B["Gateway evaluates Route set"]
    B --> C{"Do Path, Method, Header... match?"}
    C -->|No| N["Evaluate next Route"]
    C -->|Yes| D{"Does After / Before / Between match current time?"}
    D -->|No| N
    D -->|Yes| E["Select Route"]
    E --> F["GatewayFilter chain: auth-related filters, path/header, limit, retry..."]
    F --> G["Routing / service discovery / downstream"]
    G --> H["Response to client"]
    N --> I{"Another Route?"}
    I -->|Yes| B
    I -->|No| J["No Gateway route matched; typically 404 if no other handler"]
~~~

This diagram is a conceptual model: a Spring Security `WebFilter` can reject a request **before** route selection; inside the Gateway filter chain, filters can also short-circuit without calling downstream.

Time predicates are evaluated **when inspecting each request**; they are not `cron` jobs, do not start/stop services automatically, and do not modify `RouteDefinition` on a schedule. A cached route can transition from **non-matching** to **matching**, or vice versa, simply as real time passes without redeclaring the route.

## 2. Exact definitions of After, Before, and Between

Let `now` be the instant Gateway uses to evaluate the predicate, `T` be a configured timestamp, and `T1` and `T2` be the two bounds of an interval:

| Factory | Condition for route match | Shortcut syntax | Practical meaning |
|---|---|---|---|
| `After` | `now > T` | `After=T` | Matches route only **after** timestamp T |
| `Before` | `now < T` | `Before=T` | Matches route only **before** timestamp T |
| `Between` | `T1 < now < T2` | `Between=T1,T2` | Matches route only **inside** interval (T1, T2) |

Comparisons here are **strict**: an instant **exactly equal** to a boundary does not match.

- `After` does not accept a request if the current time has **not yet passed** the timestamp.
- `Before` does not accept a request if the current time has **reached or passed** the timestamp.
- `Between` requires `T1` to be **earlier than** `T2` and normally excludes both boundary instants.

In practice, the probability of a request landing on the exact boundary nanosecond/second may be low, yet you must treat this as an actual property of the predicate. If you need boundary rules that are **inclusive** of the start or end instant, design additional fallback routes or a custom predicate rather than assuming `Between` is a closed interval.

### Why not use the client's time?

A client can send a `Date` header, pass a timestamp query parameter, or change its device timezone. Those values are **not the time source** used by these three predicates by default. Routes are matched against time in the Gateway environment, so controlling the Gateway clock and timezone logic matters far more than the API caller's clock.

## 3. Time syntax: ISO-8601 and `ZonedDateTime`

The time factories in Gateway Server WebFlux use Java's time model such as `java.time.ZonedDateTime`. Pass an **ISO-8601 timestamp with offset/timezone information**, rather than an ambiguous local time string.

Valid examples illustrating the format:

~~~text
2027-06-01T09:00:00+07:00[Asia/Ho_Chi_Minh]
2027-06-01T02:00:00Z
2027-05-31T22:00:00-04:00[America/New_York]
~~~

All three strings represent **the exact same instant**:

| Representation | Displayed local time | Corresponding UTC |
|---|---|---|
| Ho Chi Minh City | `2027-06-01 09:00:00 +07:00` | `2027-06-01 02:00:00Z` |
| UTC | `2027-06-01 02:00:00Z` | `2027-06-01 02:00:00Z` |
| New York during `-04:00` season | `2027-05-31 22:00:00 -04:00` | `2027-06-01 02:00:00Z` |

When comparing, `isAfter`/`isBefore` logic compares absolute instants on the timeline. **Different timezones do not alter the real ordering of instants**, provided the timestamps are parsed properly.

### How do Offset and Zone ID differ?

- **Offset** such as `+07:00` indicates how far local time differs from UTC at **the written timestamp**.
- **Zone ID** such as `Asia/Ho_Chi_Minh` or `America/New_York` identifies regional timezone rules, including historical changes and daylight saving rules if applicable.
- **`Z`** at the end of an ISO-8601 timestamp represents the UTC offset `+00:00`.

Example:

~~~text
2027-06-01T09:00:00+07:00[Asia/Ho_Chi_Minh]
           |        |
           |        +-- Zone ID: Asia/Ho_Chi_Minh region
           +----------- Offset at that timestamp: +07:00
~~~

You can omit the Zone ID when using an offset if the parser in your version accepts that format; including an explicit offset and appropriate Zone ID helps maintainers see **both the local time and the applicable region**.

**Do not write:** `2027-06-01T09:00:00` expecting Gateway to infer Vietnam time. A string without an offset/zone lacks enough information to parse a `ZonedDateTime` under standard syntax.

### Be careful with Daylight Saving Time (DST)

Some regions like `America/New_York` change offsets seasonally. Thus, `09:00` in New York may correspond to `14:00Z` in winter (`-05:00`) or `13:00Z` in summer (`-04:00`). `Asia/Ho_Chi_Minh` currently uses `+07:00` in contemporary scenarios.

On DST transition days, **skipped** or **repeated local times** can exist. When scheduling in a DST region:

1. Determine the **specific date** and Zone ID per business rules.
2. Compute the offset valid on that date instead of assuming one fixed offset year-round.
3. Avoid nonexistent or ambiguous local times, or resolve ambiguity by choosing an explicit instant/offset.
4. Verify the UTC conversion before putting it into configuration.

For example, `2027-01-15T09:00:00-05:00[America/New_York]` and `2027-07-15T09:00:00-04:00[America/New_York]` both express 09:00 in the New York region on two dates in different seasons. These are **two distinct instants**, not two ways of writing the same instant.

## 4. After: starting routing after a timestamp

Suppose the new backend version at `http://localhost:9091` should only receive `/api/catalog/**` **after** 09:00 on 2027-06-01, Ho Chi Minh City time.

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-after
          uri: http://localhost:9091
          predicates:
            - Path=/api/catalog/**
            - 'After=2027-06-01T09:00:00+07:00[Asia/Ho_Chi_Minh]'
          filters:
            - StripPrefix=1
~~~

Meaning:

- 08:59:59.999 in the specified timezone: `After` does not match yet.
- **09:00:00.000 exact boundary**: `After` still does not match.
- 09:00:00.001: `After` can match, provided `Path` also matches and the route is evaluated/selected.

`After` does not mean "every day after 09:00"; it is **a single fixed date-time instant**. Once 2027-06-01 passes, it continues matching on subsequent days until the route/configuration changes.

### Expanded declaration

~~~yaml
predicates:
  - name: Path
    args:
      patterns:
        - /api/catalog/**
  - name: After
    args:
      datetime: '2027-06-01T09:00:00+07:00[Asia/Ho_Chi_Minh]'
~~~

The `datetime` field belongs to the `After` factory configuration. Writing it in expanded form helps during reviews and avoids confusion with other values in a single YAML string.

## 5. Before: routing only before a deadline

Suppose the `/api/legacy/**` route is valid only **before** 18:00 on 2027-06-30, Ho Chi Minh City time.

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: legacy-before
          uri: http://localhost:9092
          predicates:
            - Path=/api/legacy/**
            - 'Before=2027-06-30T18:00:00+07:00[Asia/Ho_Chi_Minh]'
~~~

- A request at 17:59:59.999 can match.
- A request at **18:00:00.000 exact boundary** does not match.
- Requests after 18:00 do not match this route.

Expanded form:

~~~yaml
predicates:
  - name: Path
    args:
      patterns:
        - /api/legacy/**
  - name: Before
    args:
      datetime: '2027-06-30T18:00:00+07:00[Asia/Ho_Chi_Minh]'
~~~

**`Before` does not disable the application's HTTP endpoint globally.** If another route still matches the same `Path`, requests can pass through that route; if no route or handler matches, the result is usually 404. Sunsetting a feature may also require enforcement at the backend or authorization layer, especially if the downstream remains reachable through other paths.

## 6. Between: routing within a time window

For example, a promotion accepts requests between **09:00 and 10:00 on 2027-06-01**, in `Asia/Ho_Chi_Minh`:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: promotion-window
          uri: http://localhost:9093
          predicates:
            - Path=/api/offers/**
            - 'Between=2027-06-01T09:00:00+07:00[Asia/Ho_Chi_Minh],2027-06-01T10:00:00+07:00[Asia/Ho_Chi_Minh]'
          filters:
            - StripPrefix=1
            - AddRequestHeader=X-Campaign,summer
~~~

Expanded form expressing the same goal:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: promotion-window
          uri: http://localhost:9093
          predicates:
            - name: Path
              args:
                patterns:
                  - /api/offers/**
            - name: Between
              args:
                datetime1: '2027-06-01T09:00:00+07:00[Asia/Ho_Chi_Minh]'
                datetime2: '2027-06-01T10:00:00+07:00[Asia/Ho_Chi_Minh]'
          filters:
            - StripPrefix=1
            - AddRequestHeader=X-Campaign,summer
~~~

The fields `datetime1` and `datetime2` represent the **start** and **end** instants, respectively. `datetime1` must be **before** `datetime2`; reversing them or setting both equal is logically invalid for the factory and can cause route loading or startup to fail.

| Time in `Asia/Ho_Chi_Minh` | `Between` matches? | Explanation |
|---|---|---|
| 08:59:59.999 | No | Not yet after start time |
| **09:00:00.000** | **No** | Equal to start boundary |
| 09:00:00.001 | Yes | Inside window |
| 09:30:00 | Yes | Inside window |
| 09:59:59.999 | Yes | Before end boundary |
| **10:00:00.000** | **No** | Equal to end boundary |
| 10:00:00.001 | No | Past the window |

**A `Between` interval does not repeat daily.** To repeat 09:00–10:00 every day, you need a scheduler, configuration update mechanism, or a custom predicate designed for recurring schedules. A `Between` with two fixed timestamps has no "every day" rule.

### Windows crossing midnight

A 22:00–02:00 overnight window must use **two different dates**:

~~~yaml
predicates:
  - Path=/api/night-service/**
  - 'Between=2027-10-12T22:00:00+07:00[Asia/Ho_Chi_Minh],2027-10-13T02:00:00+07:00[Asia/Ho_Chi_Minh]'
~~~

If both timestamps were written with the same date 10/12, `02:00` would be earlier than `22:00` and invert the interval. The example above applies only to **that single stated night**.

## 7. Combining time with Path, Method, and route order

Predicates in the **same route** normally combine with **AND**: the route matches only when path/method and time conditions are all satisfied. Example:

~~~yaml
predicates:
  - Path=/api/offers/**
  - Method=GET
  - 'Between=2027-06-01T09:00:00+07:00[Asia/Ho_Chi_Minh],2027-06-01T10:00:00+07:00[Asia/Ho_Chi_Minh]'
~~~

`POST /api/offers/42` does not match this route even if it arrives at 09:30, because `Method=GET` fails.

When **multiple routes can match**, route `order` decides which route is evaluated first. Lower `order` values take precedence; never rely on YAML file order to handle overlapping routes.

### Designing before – during – after and fallback

Example with three different backends for the same path:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: offers-before
          order: -10
          uri: http://localhost:9091
          predicates:
            - Path=/api/offers/**
            - 'Before=2027-06-01T09:00:00+07:00[Asia/Ho_Chi_Minh]'

        - id: offers-promotion
          order: -10
          uri: http://localhost:9092
          predicates:
            - Path=/api/offers/**
            - 'Between=2027-06-01T09:00:00+07:00[Asia/Ho_Chi_Minh],2027-06-01T10:00:00+07:00[Asia/Ho_Chi_Minh]'

        - id: offers-after
          order: -10
          uri: http://localhost:9093
          predicates:
            - Path=/api/offers/**
            - 'After=2027-06-01T10:00:00+07:00[Asia/Ho_Chi_Minh]'

        - id: offers-fallback
          order: 100
          uri: http://localhost:9094
          predicates:
            - Path=/api/offers/**
~~~

At the two **exact boundary instants** 09:00:00 and 10:00:00, none of the three time-predicated routes match because comparisons are strict. The `offers-fallback` route with a higher `order` can still accept the request when the others do not match.

Outside those boundaries, the time routes do not overlap, so sharing `order=-10` introduces no selection conflict in this example. Fallback behavior should match business needs: serving a waiting page, an expiration notice, or routing to a safe backend. If no fallback is wanted, anticipate what happens when **no route matches**.

| Time (Vietnam time) | Expected route | Backend |
|---|---|---|
| 2027-06-01, 08:59:00 | `offers-before` | `localhost:9091` |
| 2027-06-01, exact 09:00:00 | `offers-fallback` | `localhost:9094` |
| 2027-06-01, 09:15:00 | `offers-promotion` | `localhost:9092` |
| 2027-06-01, exact 10:00:00 | `offers-fallback` | `localhost:9094` |
| 2027-06-01, 10:00:01 | `offers-after` | `localhost:9093` |

**Note:** Fixed dates in this lesson are only for learning configuration. If you run the example at a different time, route matching will reflect **Gateway's real date and time**, not the simulated timestamps in the table.

## 8. Sources of time skew in multi-Gateway systems

For a single Gateway instance, the current time comes from **the system clock of the process running Gateway**. In a multi-instance cluster behind a load balancer, each instance has its own clock:

~~~mermaid
flowchart LR
    C["Client"] --> L["Load balancer"]
    L --> A["Gateway A\nClock: 08:59:59"]
    L --> B["Gateway B\nClock: 09:00:02"]
    A --> X["Time predicate: may not match yet"]
    B --> Y["Time predicate: may already match"]
~~~

If two nodes' clocks drift by a few seconds near a boundary, the same logical request can go to different backends depending on which instance receives it.

Operational measures:

- Synchronize clocks using **NTP or a reliable time-sync mechanism**; monitor clock drift across nodes and time sources.
- Configure timestamps with **explicit offset/Zone ID**, never relying on the default timezone of a host, container, or browser.
- Verify route configuration and documentation across **all instances** so one node doesn't run updated routes while another holds stale cache/config.
- Design buffers, fallbacks, or transition mechanisms that tolerate a few milliseconds/seconds of skew if the business is sensitive to start/end boundaries.
- If legal validity or payment cutoffs require millisecond precision, enforce them at a **backend with centralized time and business state**, rather than treating a gateway predicate as the sole proof.

### Evaluation time is not necessarily downstream processing time

Gateway evaluates predicates before the filter chain and downstream forwarding complete. A request arriving near the end of a window can **match at route selection**, yet reach downstream after the deadline has passed. Conversely, requests can only be selected based on when Gateway evaluates them, not when a transaction is actually committed in the backend. Business logic like promotional pricing, token validity, payments, or sensitive access controls should enforce business time checks where the transaction executes.

## 9. Common configuration mistakes

| Mistake | Common consequence | Resolution |
|---|---|---|
| Using `2027-06-01T09:00:00` without offset/zone | Fails to parse as `ZonedDateTime` in relevant configuration | Add `+07:00[Asia/Ho_Chi_Minh]` or UTC `Z` |
| Writing `09:00` and confusing UTC with Vietnam time | Route turns on/off **7 hours** off from intent | Convert local time to the exact instant |
| `Between` has `datetime2` before `datetime1` | Inverted interval; route initialization may fail | Supply two strictly increasing instants |
| Using `Between` for a daily recurring schedule | Active only during one specific date-time span | Design a recurring scheduler or custom predicate |
| Treating `Between` as a closed interval | Requests on exact boundaries do not match | Plan a fallback and test boundaries |
| Using shortcut without a comma between timestamps | Factory receives missing parameter | Use expanded syntax `datetime1`/`datetime2` |
| Wrong date when window crosses midnight | End ends up before start | Put `datetime2` on the next day |
| Wrong zone/offset during DST | Converted UTC instant differs from expectation | Use the right Zone ID/offset for that date and verify the instant |
| Gateway finds no route and assumes expiration | Might be missing dependency, wrong namespace, bind error, or unrefreshed route | Separate **route existence** errors from **predicate mismatch** |
| Node A accepts while Node B rejects | Clock skew, different config/cache versions, or route order | Check NTP, configs, and state on every node |

### Why quote timestamps in YAML?

Values containing `:`, square brackets `[...]`, `+`, and strings with commas should be wrapped in quotes so both readers and the YAML parser handle them consistently:

~~~yaml
predicates:
  - 'After=2027-06-01T09:00:00+07:00[Asia/Ho_Chi_Minh]'
  - 'Before=2027-06-30T18:00:00+07:00[Asia/Ho_Chi_Minh]'
~~~

This example only illustrates quoting; placing **both After and Before** in the same route requires **both to match simultaneously**, forming an intersecting time range. For a simple time window, `Between` usually expresses intent more clearly.

Valid YAML alone does not guarantee the route builds cleanly: factory names, parameter types, `ZonedDateTime` validity, and runtime conditions still need verification by Gateway.

## 10. How to test practically without changing the server clock

Never alter the system clock of a development or production Gateway machine just to wait for `After` or `Between` to match. The safe approach is to **generate relative timestamps around the current time** in your test environment.

Example using **JShell** (available in a compatible JDK) to print `Between` values around execution time:

~~~java
import java.time.*;
import java.time.format.*;

var zone = ZoneId.of("Asia/Ho_Chi_Minh");
var now = ZonedDateTime.now(zone);
var start = now.minusMinutes(5);
var end = now.plusMinutes(30);

System.out.println("After=" + start.format(DateTimeFormatter.ISO_ZONED_DATE_TIME));
System.out.println("Before=" + end.format(DateTimeFormatter.ISO_ZONED_DATE_TIME));
System.out.println("Between=" +
    start.format(DateTimeFormatter.ISO_ZONED_DATE_TIME) + "," +
    end.format(DateTimeFormatter.ISO_ZONED_DATE_TIME));
~~~

Run `jshell` from a terminal with a JDK and enter the snippet above. Copy the printed `Between=...` string into a test route; restart or refresh configuration using the mechanism supported by that Gateway version. **The generated timestamps are only valid for the ~35-minute window created**, so run tests right away; if expired, generate new values.

Assuming a test downstream at `localhost:9090` exposes `GET /orders/42` and logs path/headers:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: test-time-window
          uri: http://localhost:9090
          predicates:
            - Path=/api/orders/**
            - Method=GET
            # Replace the value below with the Between=... string generated via JShell:
            - 'Between=2027-06-01T09:00:00+07:00[Asia/Ho_Chi_Minh],2027-06-01T10:00:00+07:00[Asia/Ho_Chi_Minh]'
          filters:
            - StripPrefix=1
            - AddRequestHeader=X-Gateway-Test,time-window
~~~

In actual testing, **you must replace** the fixed `Between=...` line with the newly generated output; otherwise the request may not fall inside the test window.

Send:

~~~bash
curl -i http://localhost:8080/api/orders/42
curl -i -X POST http://localhost:8080/api/orders/42
~~~

Expected behavior when the backend is running, Gateway listens on 8080, config is loaded, and the GET request is inside the window:

- **GET** matches `Path`, `Method`, and `Between`; downstream receives `GET /orders/42` with header `X-Gateway-Test: time-window`.
- **POST** does not match `Method=GET` on this route, even within the window; if no other route or handler exists, it normally returns 404.
- If GET returns 5xx, check downstream connectivity, DNS/TLS, filters, and logs; **a 5xx does not prove the time predicate failed**.

### Testing negative cases

In a separate test environment, you can generate an `After` timestamp in the future (route does not match yet) or a `Before` timestamp in the past (route has expired) from `ZonedDateTime.now(zone)`. Inspect the route list to confirm the route still exists even though requests don't match. Then switch back to valid timestamps and confirm the route accepts requests.

To test **exact boundary seconds**, testing against the real system clock is often flaky due to network latency and scheduling. When high precision is needed, use **isolated time-logic tests that accept an injectable `Clock`**, or a custom predicate designed for `Clock` injection; do not assume built-in factories expose a YAML option to override the clock.

## 11. Operating alongside other Gateway components

Time predicates decide **which route is selected**, while other critical capabilities remain configured separately:

| Component | Relationship with time predicates | What to verify |
|---|---|---|
| `Path`, `Method`, `Host` | Combine with `After`/`Before`/`Between` in the same route via AND | A request matching the time window but wrong path/method is still excluded from the route |
| Route `order` and fallback | Determines evaluation order when multiple routes match | Boundary windows and overlapping routes yield clear outcomes |
| `StripPrefix`, `RewritePath`, header changes | Execute after route selection | Backend receives expected path/headers |
| Service discovery, `lb://` | Chooses downstream instance after route resolution | Service is registered, load balancer is configured, and instances are healthy |
| Authentication / authorization | May run at `WebFilter` or appropriate filter layer | Requests failing route match are still handled securely as required |
| Rate limiting | Throttles requests per policy at/after integration layer | Excess traffic cannot bypass limits through a fallback route |
| Circuit breakers and retries | Manage upstream errors and resilience | Avoid unbounded retries; test timeouts, fallbacks, and error codes |
| TLS | Protects client → Gateway and Gateway → downstream | Certificates, trust, and HTTPS do not depend on predicate matches |
| Metrics, logs, tracing | Record routes, requests, errors, and latency | Distinguish route mismatch from downstream errors and inter-node clock skew |

For example, a promotion route gated only by `Between` **is not a user authentication mechanism**. Anyone meeting the path/method conditions and reaching Gateway during that window can select the route unless authentication/authorization policies are enforced. For promotions involving money or sensitive data, the backend must enforce exact business rules.

### Does a schedule transition require a config refresh?

- **No refresh is needed** merely because the clock crosses from before a timestamp to after it; the predicate evaluates current time on the next request.
- **A config update workflow is needed** if you change timestamp values, add/remove routes, or alter URIs/filters in the configuration source. If the app only reads static config at startup, a restart or supported reload mechanism is required.
- With multiple instances, verify every node received the updated configuration. An unrefreshed node may still hold an old timestamp and behave differently.

If using Actuator to inspect/refresh routes, expose only the needed management endpoints per your version's docs and protect them with proper access controls.

## 12. Checklist before deploying time-based routes to production

- [ ] Confirmed **Gateway version and variant**; YAML syntax matches the running version.
- [ ] Chose `After`, `Before`, or `Between` for a one-time rule, not mistaking it for a daily recurring schedule.
- [ ] Timestamps are written in **ISO-8601** with **explicit offset/Zone ID**.
- [ ] Converted timestamps to **UTC** to verify the intended instant.
- [ ] For DST regions, checked transition dates, offsets, and ambiguous/nonexistent local times.
- [ ] `datetime1` in `Between` is **earlier than** `datetime2`; overnight windows span two dates properly.
- [ ] Accounted for **strict boundary inequalities** and defined fallback behavior if needed.
- [ ] Verified AND combinations with `Path`, `Method`, and route `order` precedence.
- [ ] Synchronized Gateway clocks; multiple instances share consistent configuration/cache state.
- [ ] Tested matching requests, wrong path/method, outside time window, and backend failures.
- [ ] Authentication, rate limiting, retries/circuit breakers, TLS, and request observability have their own policies.
- [ ] Sensitive decisions about payments, access permissions, and expirations are enforced at the backend or authoritative component.

## Official references

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — check **After Route Predicate Factory**, **Before Route Predicate Factory**, and **Between Route Predicate Factory** for your **exact version/variant**.
- [Spring Cloud Gateway project](https://spring.io/projects/spring-cloud-gateway) — entry point for project docs and release information.
- [Java ZonedDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html) — representing, parsing, and comparing timezone-aware instants.
- [Java DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html) — ISO-8601 and `ISO_ZONED_DATE_TIME` formatting.

**Key takeaway:** `After` requires **after the timestamp**, `Before` requires **before the timestamp**, and `Between` requires **strictly between two timestamps**. All three evaluate Gateway's local clock and compare real instants; operating reliably requires explicit timezones, boundary handling, and multi-instance verification.
