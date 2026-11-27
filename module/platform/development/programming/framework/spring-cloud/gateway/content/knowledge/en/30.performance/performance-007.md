# Reducing Predicate and Regular Expression Overhead

## 1. Why Does Route Matching Become a Performance Issue?

In a microservices architecture, **Spring Cloud Gateway** is the entry point for many APIs: the Gateway inspects each HTTP request, selects a route using **route predicates**, executes a **filter chain** to transform paths/headers, enforces authentication and rate limiting, and forwards traffic to services via static URIs or service discovery. Under high concurrency, even small operations during route selection can accumulate into substantial CPU time.

For example, suppose a system defines hundreds of routes and several use regular expressions to distinguish `Host`, `Header`, or `Query`. A very broad configuration:

~~~yaml
predicates:
  - Path=/**
  - Header=X-Partner-Code,^(.*a){3,}.*$
  - Query=search,.*(gold|silver|platinum).*
~~~

forces the Gateway to run repeated checks over client-controlled strings. If a regex allows **heavy backtracking** on crafted input, a single small request can burn excessive CPU (**Regular Expression Denial of Service, ReDoS**). On the other hand, merely seeing a regex does not mean it is slow: actual impact depends on the pattern, input, evaluation count, and Java/framework version.

This lesson, **"Reducing Predicate and Regular Expression Overhead,"** belongs to the **Performance** chapter of the **SPRING_CLOUD_GATEWAY** module. We optimize **route selection** without breaking route correctness, authorization, rate limiting, circuit breakers, retries, TLS, or observability.

After this lesson, you will be able to:

1. Build a cost model from **candidate routes × predicates × per-predicate complexity**.
2. Distinguish `Path`/`Host` patterns from Java regexes in `Header`/`Cookie`/`Query`.
3. Replace overly broad regexes with narrow constraints, parameter presence checks, or string comparisons when appropriate.
4. Understand `Pattern.compile`, `Matcher`, and regex patterns prone to backtracking.
5. Write a custom `RoutePredicateFactory` with input bounds and zero blocking I/O.
6. Measure p50/p95/p99, throughput, CPU, allocations, and route correctness across diverse cases.
7. Roll out optimizations with canaries, regression suites, and rollback plans without accidentally opening unauthorized routes.

> **Scope:** Main examples use **Spring Cloud Gateway Server WebFlux** and Reactor Netty. Gateway Server Web MVC uses WebMvc.fn/Servlet with corresponding predicate APIs, yet **does not use the same `ServerWebExchange` or WebFlux factory classes**. The principles for reducing regex/backtracking overhead apply to both stacks.

## 2. Where Do Predicates Run in the Request Flow?

~~~mermaid
flowchart TD
    C["HTTP client"] --> M["Gateway Server WebFlux<br/>RoutePredicateHandlerMapping"]
    M --> R{"Evaluate runtime routes<br/>per configuration/order"}
    R -->|"Route A doesn't match"| N["Check next candidate route"]
    N --> R
    R -->|"A route matches"| F["Combined GlobalFilter + GatewayFilter"]
    F --> L["Routing / lb:// / HttpClient"]
    L --> B["Backend service"]
    R -->|"No route matches"| E["No Gateway route<br/>other handler or 404"]
    B --> O["Response"]
~~~

**Predicates decide whether a route is selected. Filters run after a route is selected.** Therefore, if the goal is rejecting non-matching requests quickly, placing path checks in a **`Path` predicate** usually makes more sense than deferring all classification to a post-selection filter.

Per Spring Cloud Gateway Server WebFlux docs, predicates on a single route combine with **AND** logic. Multiple values inside one predicate such as `Method=GET,HEAD` or `Path=/orders/**,/products/**` express **OR** choices within that factory.

### 2.1. A Conceptual Cost Model, Not a Spring Formula

Suppose each request performs:

\[
T_{\mathrm{routing}}\approx T_{\mathrm{dispatch}}
  + \sum_{r\in C(q)}\sum_{p\in P_r(q)} T_p(q)
  +T_{\mathrm{bookkeeping}}
\]

Where:

- `q`: an incoming request.
- `C(q)`: the runtime candidate routes actually evaluated before picking a route or concluding no match.
- `P_r(q)`: the predicates invoked for route `r`.
- `T_p(q)`: the cost of one predicate on that request's data.

This is an **intuitive model**; it does not claim the Gateway always linearly scans every route in all versions or declarations. Route caches, ordering, predicate composition, matching, and JIT optimizations all influence real execution. Always measure on your **actual running artifact and config**.

An illustrative calculation:

~~~text
100 route candidates × 3 predicates each × 5 μs average
= 1,500 μs = 1.5 ms
~~~

This is **not a measured Spring Cloud Gateway benchmark**. It merely illustrates how a small cost multiplied by many evaluations adds up. Conversely, if the backend takes 300 ms, shaving a few microseconds off predicates matters far less than tuning connection pooling or timeouts.

### 2.2. Unmatched Requests Also Burn CPU

If a gateway holds 300 routes, a `GET /does-not-exist` request may traverse many checks before returning 404. During path scans or bad-traffic bursts, **requests matching zero routes** can represent a huge share of traffic.

Do not benchmark only successful backend hits: include **hits**, **misses**, requests matched by fallback routes, and long/unusual inputs.

### 2.3. Route-Matching Cost Differs from Filter and Downstream Costs

| Cost source | Example | Route predicate cost? |
| --- | --- | --- |
| Matching path/method/header/query | Matching `Path=/api/orders/**` | Yes |
| Regex against a client header | `Header=X-Partner-Code,...` | Yes |
| Reading/caching body for `ReadBody` | Decoding a JSON request | Yes, and potentially heavy |
| JWT verification in Spring Security | Checking signature/audience | Not a route predicate by default |
| `RequestRateLimiter` via Redis | Quota key and Redis round trip | `GatewayFilter`, not a typical predicate |
| Rewriting response bodies | Buffers/codecs | Filter |
| TLS handshake, DNS, TCP connect | Reactor Netty / backend | Transport/downstream |
| Retries / circuit breakers | Multiple attempts or fallbacks | Filter/downstream |

If a flame graph shows most time going to TLS, JSON parsing, or Redis, tuning regexes on rarely hit routes **will not noticeably improve end-to-end latency**. Optimize based on data.

## 3. Identifying Which Predicates Actually Need Regex

Server WebFlux route predicate factories do not share the same internal matching engine.

| Predicate | Inspected data | Primary pattern language | When to choose |
| --- | --- | --- | --- |
| `Method` | HTTP method | Method list | Splitting GET/POST/HEAD |
| `Path` | Request path | Spring path patterns / URI templates | Routing by prefix/segment |
| `Host` | HTTP Host | Ant-style host patterns | Virtual hosts/subdomains |
| `Header` | Header name/value | Java regex for value | Only when inspecting values |
| `Query` | Query parameter | Can check **presence** alone, or regex | Routing by presence/value |
| `Cookie` | Cookie name/value | Java regex for value | Only when justified; never as auth |
| `RemoteAddr` | Remote socket address | CIDR | Network routing by trusted address |
| `After/Before/Between` | Request timestamp | `ZonedDateTime` | Time windows, no regex needed |
| `ReadBody` | Decoded body | Custom Java predicate | Only when metadata cannot decide |

Spring Cloud Gateway docs describe `Host` as **Ant-style with dot separators**, and `Path` as **Spring path patterns**—**not Java regex syntax**. For instance, `/api/orders/{id}` is a URI template pattern, not something requiring `.matches("...")`.

### 3.1. Drop Regex When You Only Need Query Presence

Unnecessary:

~~~yaml
# Verbose when you only need to know the query key exists
- Query=download,.*
~~~

Replace with:

~~~yaml
# Checks that the download parameter is present
- Query=download
~~~

**Yet semantics are not identical in every case.** The single-argument form checks key presence; the regex form matches values (including empty strings or multi-value behavior depending on version). Switch only when **the business contract truly checks presence**, and add tests for `?download`, `?download=`, and duplicate keys.

### 3.2. Use `Path` When Splitting by Prefix

Do not build a custom predicate just to run:

~~~java
Pattern.compile("^/api/catalog/.*")
       .matcher(requestPath)
       .matches();
~~~

on every request when the Gateway already supports:

~~~yaml
predicates:
  - Path=/api/catalog/**
~~~

`Path` expresses routing intent clearly and uses Spring's built-in matching. That is not a claim it is **always** faster than every regex on every JVM, yet it avoids overly broad custom patterns, redundant recompilation, and manual URL-encoding pitfalls.

### 3.3. Avoid String/Regex Tricks When Matching HTTP Methods

~~~yaml
predicates:
  - Method=GET,HEAD
~~~

is far simpler than `Header=X-HTTP-Method-Override,...` or reading request bodies to infer the method. If your app supports method overrides, enforce them carefully at the security/routing boundary per contract—never blindly trust client-supplied override headers.

### 3.4. Never Use Broad Wildcards to "Reduce Predicate Count"

Replacing:

~~~yaml
predicates:
  - Path=/api/payments/**
  - Method=POST
~~~

with:

~~~yaml
predicates:
  - Path=/**
~~~

might match **slightly faster in some cases** while letting unintended requests reach the backend. That is an unacceptable optimization: **correctness and security are hard constraints**; performance comes after.

## 4. Java Regex: Compilation, Matching, and Memory

A regex incurs cost across multiple stages:

1. **Compiling** the pattern string into a `Pattern` structure.
2. **Allocating a `Matcher`** for the input value.
3. **Matching** the input, potentially backtracking across branches.
4. **Allocations and GC** from intermediate objects and strings.

With `java.util.regex.Pattern`:

~~~java
// Convenient, yet recompiles the regex on every call:
boolean ok = Pattern.matches("^[A-Za-z0-9_-]{1,32}$", value);
~~~

Per Javadoc, `Pattern.matches(regex, input)` is equivalent to `Pattern.compile(regex).matcher(input).matches()`. For repeated patterns on the request hot path, **compiling once and reusing** is usually better:

~~~java
import java.util.regex.Pattern;

private static final Pattern SAFE_PARTNER_CODE =
        Pattern.compile("[A-Za-z0-9_-]{1,32}");

boolean ok = value != null
        && value.length() <= 32
        && SAFE_PARTNER_CODE.matcher(value).matches();
~~~

### 4.1. `Pattern` Can Be Shared; `Matcher` Cannot

| Object | Safe usage |
| --- | --- |
| `Pattern` | Immutable/thread-safe; store in `static final` or config objects |
| `Matcher` | Create per request/check; **not thread-safe** |
| Input string | Bound length and charset per contract |
| Mutable buffers/caches | Never share across threads without concurrency control |

**Wrong:**

~~~java
// DO NOT share a single Matcher across request threads.
private static final Matcher SHARED_MATCHER =
        SAFE_PARTNER_CODE.matcher("");

// SHARED_MATCHER.reset(clientValue).matches();
~~~

`Matcher` holds mutable state (index, capture groups, prior match results); sharing it causes data races and inconsistent routing. In WebFlux, concurrent requests run across multiple event-loop threads.

### 4.2. Do Not Blame Built-In Factories Without Profiling

When declaring a regex containing a **comma inside a quantifier `{1,32}`**, use expanded syntax so the comma is not parsed as a shortcut argument separator:

~~~yaml
predicates:
  - name: Header
    args:
      header: X-Partner-Code
      regexp: '^[A-Za-z0-9_-]{1,32}$'
~~~

**Do not assume the Gateway definitely calls `Pattern.compile` on every request.** Whether a built-in factory compiles at route creation or match time is a **version-specific implementation detail**. Use CPU profiles, JFR, and benchmarks on your exact release; if compilation does not appear on the hot path, replacing it with a custom factory purely to "cache the regex" adds maintenance cost for zero gain.

### 4.3. `matches()` and `find()` Differ

~~~java
Pattern p = Pattern.compile("partner");
p.matcher("partner").matches();       // true
p.matcher("x-partner-x").matches();   // false
p.matcher("x-partner-x").find();      // true
~~~

`matches()` checks the **entire** input; `find()` searches for a substring. Java regex also supports `^` and `$` anchors. When swapping patterns, check how the factory invokes `Matcher` and preserve the exact accepted input set. Adding `.*` "to make matching easier" widens the regex and invites backtracking.

### 4.4. Input Length Matters More Than Pattern Appearance

Even a simple pattern like `[a-z]+` runs fast on a 12-character header, yet burns CPU on huge headers. Therefore:

- Bound request-line, header, and URI sizes at public ingress and HTTP servers.
- Bound header, query, and cookie lengths explicitly before running custom regexes.
- Limit parameter value counts, repeated headers, and cookie counts.
- Never guess a `max-header-size` property name across all Spring Boot/Netty versions; check configuration metadata.
- Never "normalize" weird inputs in a way that accidentally accepts requests meant to be rejected.

## 5. ReDoS and Catastrophic Backtracking

Java's `Pattern` uses a backtracking regex engine. Certain patterns allow **many ways to partition the same string**, forcing the engine to explore vast branches before failing.

Famous example:

~~~regex
^(a+)+$
~~~

For short strings of `'a'`, it matches quickly. With many `'a'`s followed by **one invalid character**, the engine explores exponentially many partitions across nested loops—the classic ReDoS risk flagged by OWASP.

**Never run unbounded long-input benchmarks against dangerous regexes on a production Gateway.** This lesson teaches how to **identify and eliminate bad patterns**, not how to attack or overload a system.

### 5.1. Warning Signs of Explosive Regex Cost

| Warning sign | Illustrative example | Risk |
| --- | --- | --- |
| Repetition inside repetition | `(a+)+` | Many ways to split identical characters |
| Overlapping alternation inside repetition | `(a|aa)+` | Combinatorial grouping |
| Repeated `.*` segments | `.*foo.*bar.*` | Backtracking on long inputs, especially near-misses |
| Optional inside repetition | `(a?)+` | Many ways to match empty segments |
| Unreviewed regex pasted into config | Operator-supplied pattern | Widens matching or causes CPU spikes |
| Regex supplied by clients | `Pattern.compile(queryParam)` | Clients control both CPU work and routing policy |

Not every pattern with `.*` is exponential, and not every alternation is bad. Yet every pattern showing these signs should be **reviewed and tested with near-miss failing inputs**.

### 5.2. Simplifying with an Equivalent Expression

If the requirement is simply **one or more `'a'` characters**, replace:

~~~regex
^(a+)+$
~~~

with:

~~~regex
^a+$
~~~

Both describe strings of one or more `'a'`s here, while the simplified version eliminates nested repetition. For real inputs, verify newlines, Unicode, case sensitivity, and matcher invocation semantics.

Likewise, if the contract requires a 1–32 ASCII code, prefer:

~~~regex
^[A-Za-z0-9_-]{1,32}$
~~~

instead of:

~~~regex
^.*[A-Za-z0-9_-].*$
~~~

**Note that these two patterns do not have identical semantics**: the first enforces strict structure and length. Use it only when **the API contract specifies** that shape, and test against valid existing traffic before switching.

### 5.3. Anchors, Character Classes, and Bounded Length

Evaluate tactics in order:

1. Can you avoid regex altogether? Use `Method`, `Path`, `Host`, or string equality.
2. If regex is needed, can a **character class** replace alternation?
3. Can you bound length with `{min,max}`?
4. Can you anchor to avoid substring scanning?
5. Can you drop unused capturing groups?
6. Can you cap input length before running the regex?
7. Do you have tests for valid, invalid, empty, oversized, and near-miss inputs?

Specifically, checking a small enum like `partner`/`internal` needs no custom regex:

~~~java
private static boolean allowedChannel(String value) {
    return "partner".equals(value) || "internal".equals(value);
}
~~~

This is easy to review and free of backtracking; in YAML route configs, a fixed `^(partner|internal)$` regex may still be simple enough. Never build a custom factory solely for a tiny pattern that hasn't shown up in profiling.

### 5.4. Possessive Quantifiers and Atomic Groups: Only When Equivalence Is Proven

Java provides:

~~~regex
a*+
a++
(?>a+)
~~~

These cut backtracking by **refusing to give back matched characters** the way greedy quantifiers do. However, that can change which inputs match if a later part of the pattern needs those characters. Never turn every `*` into `*+` out of habit and assume it is a safe optimization.

Example:

~~~regex
a+a
a++a
~~~

These two expressions are **not equivalent** on input `"aa"`: the possessive version refuses to yield an `'a'` to the trailing `a`. Write **correctness tests** before benchmarking, or use simple string checks when business logic permits.

### 5.5. Regex Deadlines: HTTP Timeouts Do Not Interrupt Regex CPU

Downstream connect/response timeouts bound network operations, **not Java regex CPU execution** reliably. An event-loop thread stuck in deep backtracking may not even process timers or cancellations on time.

Stronger defenses:

- **Keep dangerous regexes out of route definitions** (code review, static analysis, schema validation).
- **Bound input sizes** before any regex executes.
- Use linear-time string checks, minimal matchers, or an engine with guaranteed runtime bounds when genuinely required.
- Run near-miss stress tests inside isolated environments with process timeouts.
- Use edge quotas/WAFs to curb abusive inputs, while **never substituting rate limits for fixing bad regexes**.

## 6. Ordering Predicates: Cheap, Selective Checks First

A route with:

~~~yaml
predicates:
  - Path=/api/catalog/**
  - Method=GET
  - Header=X-Partner-Code,^[A-Za-z0-9_-]{1,32}$
  - Query=mode,^(full|summary)$
~~~

requires **all conditions to pass**. In theory, when checks compose sequentially with `Predicate.and(...)`, Java **short-circuits** on the first `false`, skipping later checks. Still, **never treat YAML line order as an optimization guarantee across every release, route source, or custom predicate**; verify how the Gateway materializes routes and measure with tests and profiling.

### 6.1. Weighing Cost Against Rejection Probability

Suppose incoming requests hit:

| Condition | Assumed cost | Rejection rate |
| --- | ---: | ---: |
| `Method=GET` | Very low | 30% |
| `Path=/api/catalog/**` | Low | 90% |
| `Header=X-Partner-Code,regex` | Medium | 20% of remaining requests |
| Custom predicate calling an external service | Very high | Should not sit on routing hot path |

When short-circuiting works as expected, placing **cheap, highly selective conditions** early helps. Yet "cheapest" is not always best: an ultra-cheap check that returns true 99.9% of the time saves less work than a slightly costlier `Path` predicate that rejects 90% of traffic.

To formalize intuition, minimize **expected evaluation cost**:

\[
E[T]=c_1+p_1c_2+p_1p_2c_3+\cdots
\]

where `c_i` is the cost of predicate `i` and `p_i` is the conditional pass probability reaching the next check. This assumes **deterministic ordering and short-circuiting**, not an automatic measurement of live Gateway internals.

### 6.2. Never Change Semantics Just to Drop a Predicate

When optimizing routes:

- Keep `Method` if the API forbids `POST`.
- Keep `Host` if routing splits virtual hosts, even though clients can set `Host` headers.
- Keep `Header` when required by the routing contract; do not confuse it with authentication.
- Keep `Query` if backend behavior depends on `mode`.
- Never relax `Path=/api/admin/**` to `Path=/**` just to cut matching work.
- Never remove security filters or backend authorization to make p99 look prettier.

Every optimization requires a **regression matrix** proving valid requests reach the right backend and invalid requests never slip into another route.

### 6.3. Many Routes Sharing Broad Wildcards Multiply Evaluations

Example route set:

~~~yaml
- id: route-a
  order: 10
  predicates:
    - Path=/**
    - Header=X-Service,^catalog$
- id: route-b
  order: 20
  predicates:
    - Path=/**
    - Header=X-Service,^billing$
- id: route-c
  order: 30
  predicates:
    - Path=/**
    - Header=X-Service,^shipping$
~~~

Every route accepts any path and dispatches by header. Beyond extra predicate evaluations, routing **solely on client-controlled headers** carries security risks; if the API protocol allows, partition by path prefix:

~~~yaml
- id: route-a
  order: 10
  predicates:
    - Path=/api/catalog/**
- id: route-b
  order: 20
  predicates:
    - Path=/api/billing/**
- id: route-c
  order: 30
  predicates:
    - Path=/api/shipping/**
~~~

This is a **URL contract redesign**, not a drop-in equivalent swap. Apply it only when clients accept the new paths, backend/security policies are updated, and a migration plan exists.

### 6.4. Route Order Can Speed Up Hot Paths Yet Alter Routing Behavior

The Gateway uses `order` to break ties among multiple matching routes, with lower values evaluated first. Putting a high-traffic route first **can** trim evaluations for common traffic, yet it can also **hijack traffic** meant for a more specific route.

Example:

~~~text
Route A: Path=/api/**             order=0
Route B: Path=/api/admin/**       order=10
~~~

Admin requests match Route A first and never reach Route B. Sound optimization ensures the **admin route always wins** (e.g., smaller order on B or disjoint predicates) before minimizing predicate evaluations.

Measure **hits**, **misses**, and **overlaps**, asserting route ID markers and recorded backend calls in tests.

## 7. Config Lab: Replacing a Nested Regex with a Simple Regex

Assume an HTTP service `catalog-backend` at `127.0.0.1:9191`. Example contract:

- Accept only `GET /api/catalog/**`.
- Requests must carry `X-Catalog-Key` with **one or more** ASCII letters, digits, underscores, or hyphens.
- Query `mode` must be `full` or `summary`.
- Response header carries `X-Matched-Route: catalog` to confirm which route matched.

This header is a **routing marker**, not authentication. In production, real keys/tokens must be verified by dedicated security policies.

### 7.1. Baseline: Poor Configuration to Replace

~~~yaml
# Gateway Server WebFlux 5.x - example NEEDING IMPROVEMENT
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog
              order: 0
              uri: http://127.0.0.1:9191
              predicates:
                - Path=/api/catalog/**
                - Method=GET
                # Nested repetition: do not keep this pattern.
                - Header=X-Catalog-Key,^([A-Za-z0-9_-]+)+$
                - Query=mode,^(full|summary)$
              filters:
                - AddResponseHeader=X-Matched-Route,catalog
~~~

In the bad pattern, `([A-Za-z0-9_-]+)+` nests two repetitions over the identical character set. On near-miss inputs that fail at the end, the engine can explore vast backtracking branches.

### 7.2. Optimized: Same Value Language, Far Fewer Branches

~~~yaml
# Gateway Server WebFlux 5.x - improved equivalent route
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog
              order: 0
              uri: http://127.0.0.1:9191
              predicates:
                - Path=/api/catalog/**
                - Method=GET
                - Header=X-Catalog-Key,^[A-Za-z0-9_-]+$
                - Query=mode,^(full|summary)$
              filters:
                - AddResponseHeader=X-Matched-Route,catalog
~~~

For valid header values under this contract, both regexes accept **one or more characters from the exact same ASCII set**, while the second removes nested repetition. Neither **bounds maximum length yet**: enforce max length at the edge or in a bounded custom predicate if required.

**Do not run both routes with the same ID/path inside one Gateway.** Swap configurations sequentially in the same test deployment, restart/reload cleanly, and verify active runtime routes. Only **one** `catalog` route definition exists per run.

### 7.3. WebFlux 4.2/4.3 Namespace

Gateway Server WebFlux 4.2/4.3 uses the older prefix:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog
          uri: http://127.0.0.1:9191
          predicates:
            - Path=/api/catalog/**
            - Method=GET
            - Header=X-Catalog-Key,^[A-Za-z0-9_-]+$
            - Query=mode,^(full|summary)$
          filters:
            - AddResponseHeader=X-Matched-Route,catalog
~~~

Never mix WebFlux 4.x's `spring.cloud.gateway.routes` with WebFlux 5.x's `spring.cloud.gateway.server.webflux.routes`. Newer starters use `spring-cloud-starter-gateway-server-webflux`, whereas older 4.x projects used `spring-cloud-starter-gateway`; align a **compatible Spring Boot / Spring Cloud BOM** and verify actual runtime routes.

### 7.4. Testing Valid, Invalid, and Near-Miss Inputs

~~~bash
# Matches route: 200 if backend is ready
curl -i "http://127.0.0.1:8080/api/catalog/items/42?mode=full" \
  -H "X-Catalog-Key: partner_42"

# Invalid header charset: does not match this route
curl -i "http://127.0.0.1:8080/api/catalog/items/42?mode=full" \
  -H "X-Catalog-Key: partner!"

# Invalid query: does not match this route
curl -i "http://127.0.0.1:8080/api/catalog/items/42?mode=other" \
  -H "X-Catalog-Key: partner_42"

# Wrong method: does not match this route
curl -i -X POST "http://127.0.0.1:8080/api/catalog/items/42?mode=full" \
  -H "X-Catalog-Key: partner_42"
~~~

With **only one route** and no other handler, negative cases typically return 404 (not necessarily 400/403). When a fallback route exists, negative inputs may **land on that other route**. Therefore verify **route markers + backend request counts**, not just HTTP status.

The commands above use short inputs. **Never send multi-thousand-character repeated strings at a dangerous baseline regex.** Analyze patterns first; if stress-testing ReDoS resilience is required, run inside an isolated process/cgroup with input caps, deadlines, and kill controls.

### 7.5. Before-and-After Regression Table

| Case | `X-Catalog-Key` | `mode` | Method | Expected in both configs |
| --- | --- | --- | --- | --- |
| R1 | `partner_42` | `full` | GET | Match |
| R2 | `ABC-9` | `summary` | GET | Match |
| R3 | `a` | `full` | GET | Match |
| R4 | empty string | `full` | GET | No match |
| R5 | `partner!` | `full` | GET | No match |
| R6 | `partner_42` | `other` | GET | No match |
| R7 | `partner_42` | `full` | POST | No match |
| R8 | missing header | `full` | GET | No match |
| R9 | `partner_42` | missing | GET | No match |
| R10 | `partner_42` | `full` | GET, different path | No match |

If a new regex changes the outcome on any case where the contract did not change, **the optimization is not finished**, even if p99 dropped. Also test Unicode, newlines, duplicate headers, and URL encoding per your proxy layer.

## 8. When Should You Write a Custom `RoutePredicateFactory`?

For a simple exact header check, `^partner$` is already straightforward. However, if many routes use regexes merely to check fixed values and you need **explicit length caps and duplicate-header policies**, a custom factory clarifies the contract and eliminates regexes.

Spring Cloud Gateway Server WebFlux supports creating a component extending `AbstractRoutePredicateFactory<Config>` and overriding `apply(Config)`.

### 8.1. Example: `BoundedChannelRoutePredicateFactory`

`src/main/java/demo/gateway/predicate/BoundedChannelRoutePredicateFactory.java`:

~~~java
package demo.gateway.predicate;

import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.function.Predicate;

import org.springframework.cloud.gateway.handler.predicate.AbstractRoutePredicateFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;

@Component
public final class BoundedChannelRoutePredicateFactory
        extends AbstractRoutePredicateFactory<
            BoundedChannelRoutePredicateFactory.Config> {

    private static final Set<String> ALLOWED =
            Set.of("partner", "internal");
    private static final int MAX_LENGTH = 16;

    public BoundedChannelRoutePredicateFactory() {
        super(Config.class);
    }

    @Override
    public Predicate<ServerWebExchange> apply(Config config) {
        // Read and validate config ONCE when building the predicate.
        String expected = Objects.requireNonNull(
                config.getExpected(), "expected");

        if (!ALLOWED.contains(expected)) {
            throw new IllegalArgumentException(
                    "Unsupported channel: " + expected);
        }

        // Lambda runs per request: zero blocking I/O.
        return exchange -> {
            List<String> values = exchange.getRequest()
                    .getHeaders().get("X-Channel");

            // Contract: must have EXACTLY ONE header value.
            if (values == null || values.size() != 1) {
                return false;
            }

            String actual = values.get(0);
            return actual != null
                    && actual.length() <= MAX_LENGTH
                    && expected.equals(actual);
        };
    }

    public static final class Config {
        private String expected;

        public String getExpected() {
            return expected;
        }

        public void setExpected(String expected) {
            this.expected = expected;
        }
    }
}
~~~

**How it works:**

1. Spring registers the factory bean via `@Component`.
2. When materializing a route, `apply(config)` ensures `expected` is in the allowlist.
3. Per request, the predicate reads `X-Channel`, enforces count and length limits, and compares via `String.equals`.
4. No regex runs, no `Matcher` is allocated, and no Redis/HTTP/DB call occurs on the route-selection path.
5. Disallowed config values fail fast instead of silently accepting them.

**Semantics change warning:** Built-in `Header=X-Channel,^partner$` may handle multiple header values differently depending on implementation; the custom factory above intentionally **rejects duplicate headers**. That is an **intentional policy change**—do not declare them identical without testing duplicate headers.

### 8.2. Using the Factory in YAML

In Gateway Server WebFlux 5.x:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: partner-catalog
              uri: http://127.0.0.1:9191
              predicates:
                - Path=/api/catalog/**
                - Method=GET
                - name: BoundedChannel
                  args:
                    expected: partner
              filters:
                - AddResponseHeader=X-Matched-Route,partner-catalog
~~~

The name `BoundedChannel` is derived from `BoundedChannelRoutePredicateFactory` per Gateway naming conventions. Use `name/args` syntax since this example factory declares no shortcut fields. For 4.2/4.3, move routes under `spring.cloud.gateway.routes`.

**Only write a custom factory when there is proven need**: if built-ins are already fast, correct, and secure, adding custom Java classes increases maintenance overhead without meaningful CPU savings.

### 8.3. Unit Test Without an HTTP Server

~~~java
package demo.gateway.predicate;

import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;

import static org.assertj.core.api.Assertions.assertThat;

class BoundedChannelPredicateTest {
    @Test
    void acceptsOnlyOneShortApprovedValue() {
        var factory = new BoundedChannelRoutePredicateFactory();
        var config =
                new BoundedChannelRoutePredicateFactory.Config();
        config.setExpected("partner");
        var predicate = factory.apply(config);

        var good = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/catalog/items/42")
                        .header("X-Channel", "partner"));

        var missing = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/catalog/items/42"));

        var wrong = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/catalog/items/42")
                        .header("X-Channel", "Partner"));

        var repeated = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/catalog/items/42")
                        .header("X-Channel", "partner", "internal"));

        assertThat(predicate.test(good)).isTrue();
        assertThat(predicate.test(missing)).isFalse();
        assertThat(predicate.test(wrong)).isFalse();
        assertThat(predicate.test(repeated)).isFalse();
    }
}
~~~

This unit test verifies custom predicate logic; **it does not verify YAML binding**, route order, or backend forwarding. Still write an HTTP integration test running the Gateway on a random port with `MockWebServer`/WireMock to check actual route IDs and targets.

### 8.4. If Dynamic Regex Is Needed in a Custom Factory

Accept patterns only from **trusted configuration sources**, backed by review/static validation and complexity limits. When config provides a pre-approved static expression, compile it inside `apply(config)`:

~~~java
final Pattern accepted = Pattern.compile(config.getRegexp());
return exchange -> {
    String header = exchange.getRequest()
            .getHeaders().getFirst("X-Approved-Code");
    return header != null
            && header.length() <= 32
            && accepted.matcher(header).matches();
};
~~~

This is an **illustrative standalone snippet**, not a drop-in addition to `BoundedChannelRoutePredicateFactory` (which has no `getRegexp()`). It shows compiling once instead of per request, **which still does not make a dangerous regex safe**: a pattern with catastrophic backtracking compiled once can still hang the CPU inside `Matcher.matches()`.

## 9. Methodical Benchmarking: Don't Optimize on Gut Feeling

Predicate optimizations should be evaluated from **microbenchmarks** up to **HTTP integration/load tests**. Each layer answers a different question:

| Layer | Purpose | Limitations |
| --- | --- | --- |
| Pure Java benchmark | Compare `String.equals`, precompiled `Pattern`, repeated `Pattern.compile` | Excludes route selection, Netty, and app-wide GC |
| Gateway HTTP benchmark | Measure hit/miss requests through Gateway + stub backend | Includes HTTP parsing, client/server/network, and JVM warm-up |
| Production-like load | Measure p99, CPU, throughput, memory with realistic route counts and traffic | More noise; harder to isolate predicate cost alone |
| CPU profiling / JFR | Spot regex/backtracking or hot-path allocations | Sampling overhead; requires accurate call-stack reading |
| Regression / integration | Prove identical routes/headers/backends are chosen | Does not prove faster speed on its own |

### 9.1. Microbenchmarking with JMH

JMH measures Java hot paths after warm-up, avoiding common traps of ad-hoc `System.nanoTime()` loops.

Example class in **a dedicated benchmark module**:

~~~java
package demo.benchmark;

import java.util.concurrent.TimeUnit;
import java.util.regex.Pattern;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 3)
@Measurement(iterations = 5)
@Fork(2)
public class ChannelMatchBenchmark {

    private static final Pattern CHANNEL_PATTERN =
            Pattern.compile("^partner$");

    @Param({"partner", "other", "partnerX"})
    public String value;

    @Benchmark
    public boolean stringEquals() {
        return "partner".equals(value);
    }

    @Benchmark
    public boolean precompiledRegex() {
        return CHANNEL_PATTERN.matcher(value).matches();
    }

    @Benchmark
    public boolean compileOnEveryCall() {
        return Pattern.matches("^partner$", value);
    }
}
~~~

To run JMH, add `jmh-core` and the `jmh-generator-annprocess` annotation processor for your JMH version and configure a separate benchmark harness. This lesson **did not run this benchmark**, so no measured nanosecond numbers are claimed.

These three methods share the **desired logic** for the three test values: only `partner` matches. Yet JMH results do not guarantee the built-in `HeaderRoutePredicateFactory` scales identically, because the factory handles HTTP headers and route composition as well.

**JIT warning:** In tiny benchmarks, HotSpot may inline or constant-fold branches; use diverse parameter values, sufficient warm-up, multiple forks, and a profiler. Avoid running JMH on noisy shared CI runners; compare on identical hardware, GC, and JDK.

### 9.2. Never Run Dangerous Regexes Under Unbounded Stress

A common mistake is testing `^([A-Za-z0-9_-]+)+$` with a 10,000-character near-miss string just to "measure the delta." With ReDoS, a single iteration can stall the CPU and hang CI or the test runner.

Instead:

- Catch bad patterns via code review and static analysis first.
- Use short, strictly bounded inputs if demonstrating a regression.
- Measure throughput with long valid inputs using the safe replacement pattern.
- Run any ReDoS stress verification inside an **isolated resource-capped environment** with strict deadlines and kill controls—never on a public gateway.

### 9.3. HTTP Load Tests: Three Mandatory Request Groups

A Gateway benchmark should cover:

| Group | Request | Purpose |
| --- | --- | --- |
| **Hit** | `GET /api/catalog/items/42?mode=full`, valid key header | Route match + backend response |
| **Miss-path** | `GET /not-a-route?mode=full` | Route-matching cost when no route matches |
| **Miss-near-regex** | Matching path/method/query with short invalid header | Candidate route reaches regex and then fails |
| **Overlap** | Multiple routes eligible to match | Route ordering and candidate evaluation cost |
| **Long-but-bounded** | Long header within approved limits | Allocation/CPU near max allowed input |

Benchmarks running only hit requests miss miss-path costs during URI bot scans and near-regex costs when clients send invalid values.

### 9.4. Hold Confounding Factors Constant

1. Identical JVM/JDK patch, Spring Boot, Gateway BOM, and OS/kernel.
2. Identical Netty event loops, connection pools, heap/direct memory, and GC.
3. Identical fast, steady stub backend; zero external Internet calls.
4. Identical TLS mode (plain HTTP in lab, matching TLS in production-like tests).
5. Identical route count, ordering, filters, retry/rate-limit/security policies.
6. Identical concurrency/arrival rate and hit/miss/near-miss ratios.
7. Adequate warm-up and **multiple repeated runs**.
8. Never enable DEBUG wiretap/request logging on one side and disable it on the other.
9. Never change route predicates and backend/client pools at the same time when attributing cause.
10. Run positive/negative routing tests before and after to verify the benchmark **measures identical behavior**.

**Never compare p99 directly across two load runs with different traffic mixes.** A stricter route returning 404 faster skips proxying, which is a semantic change rather than pure CPU savings.

### 9.5. Metrics to Capture

| Metric | Why it matters | Caveat |
| --- | --- | --- |
| Requests/sec and status breakdown | Throughput and expected outcome mix | 404s in negative tests are not system failures |
| p50/p95/p99 HTTP latency | Tail latency under concurrency | p99 is noisy if sample counts are tiny |
| Gateway CPU usage / CPU-seconds per request | Compute cost per request | Watch container CPU throttling/steal |
| Allocations/s, GC pauses | Are regexes/strings/matchers churning objects? | Differing heap/GC settings skew results |
| Reactor Netty event-loop lag | Detects synchronous predicates stalling threads | Comparable only on identical workloads |
| Downstream call count | Detects misrouting or unintended retries | One client request can trigger multiple retries |
| Route hit distribution | Verifies route ordering and fallbacks | Unmatched requests may not appear in route metrics |
| Rejected header/URI sizes | Verifies input caps | Never log raw inputs containing secrets |

In WebFlux, **CPU-heavy synchronous predicates can stall the Netty event loop**. A slow regex delays not only that request, but other requests sharing that event loop. Do not treat `subscribeOn(boundedElastic())` as a blanket fix for predicates: standard route predicates are synchronous, and shifting threads neither cures ReDoS nor preserves route semantics automatically.

## 10. Observing Routing Without Creating a New Bottleneck

### 10.1. Gateway Metrics Do Not Isolate Predicate Time

Spring Cloud Gateway exports metrics like `spring.cloud.gateway.requests` via the Gateway metrics filter when Actuator and version-appropriate metrics config are enabled. This meter tracks requests **processed by a matched route's filter chain**, typically tagged with route ID, status, method, and outcome.

However, a request **matching no route** may never reach the Gateway metrics filter. Therefore, **never rely solely on this metric for total inbound request volume or predicate-miss costs**.

To observe the full picture:

- Netty HTTP server metrics or an inbound `WebFilter`/observation at request entry.
- Gateway route-level metrics for matched requests.
- Backend/stub metrics to track forwarded requests.
- JFR/CPU sampling highlighting `Pattern.matcher`, route predicates, or custom code stacks.

### 10.2. Example: Enabling Metrics in WebFlux Gateway 5.x

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          metrics:
            enabled: true

management:
  server:
    address: 127.0.0.1
    port: 9090
  endpoints:
    web:
      exposure:
        include: "health,metrics,prometheus"
~~~

This assumes `spring-boot-starter-actuator` is present; add `micrometer-registry-prometheus` for `/actuator/prometheus`. Endpoints may require authentication per Security configuration; **never expose this management port to the Internet**.

Gateway WebFlux 5.x config properties list `spring.cloud.gateway.server.webflux.metrics.enabled`. In Gateway 4.x, property names and defaults may differ; inspect config metadata and confirm metrics actually populate.

### 10.3. Avoid High Cardinality When Measuring

**Do not enable path tags carrying raw user URIs** just to measure predicates: millions of `/items/{id}` values explode time-series counts. Likewise, never attach raw header values, session IDs, tokens, user IDs, or query strings as metric labels.

Prefer bounded labels:

~~~text
routeId = catalog
method = GET
status = 200
outcome = SUCCESS
requestClass = hit | miss-path | miss-regex
~~~

`requestClass` is a **custom-designed** label, not a built-in Gateway default. If classifying misses, instrument at the appropriate pre-routing layer with sampling/bounds. Never turn metrics into raw request logging.

### 10.4. Use JFR / CPU Profilers for Attribution

When p99 rises while the backend stub responds quickly:

1. Check Gateway process CPU and container throttling.
2. Capture a sampled CPU profile in an **authorized environment**.
3. Look for stacks involving `java.util.regex.Pattern`, `Matcher`, factories, or custom predicates.
4. Check allocations for `Matcher`s, strings, and buffers.
5. Compare against baseline on the exact same workload and JDK.
6. Fix patterns and input caps before tuning thread counts.

Never turn on Netty body/header wiretap in production "to measure performance"—it risks leaking cookies/tokens and skews benchmark results. Logging inside every predicate on the hot path also creates fresh overhead.

### 10.5. Bound Custom Predicate Instrumentation

To count how often a custom predicate runs, register a Micrometer `Counter` **once per route ID / factory name**—never create meters tagged per request.

~~~java
// Pseudocode - meter registered once in component:
predicateEvaluations.increment();
return cheapCheck(exchange);
~~~

This is illustrative only. **Never assume `Counter.increment()` is zero-cost**: in hot microbenchmarks, dense instrumentation can shift results. Cross-check with JFR sampling and an uninstrumented baseline.

## 11. Large-Scale Route Configs: Avoiding Wasted Evaluations

### 11.1. Runtime Routes Do Not Come Only from `application.yml`

The Gateway can load route definitions from:

- Static YAML/properties.
- Java `RouteLocator` beans.
- Config Server or dynamic repositories.
- Discovery locator (auto-generating routes from a service registry).

Counting entries in `application.yml` misses dynamic routes. A Gateway with discovery enabled can synthesize many routes, and replicas may hold differing revisions or caches.

Inspect **actual runtime route counts, IDs, orders, and predicates** via a secured management endpoint. Across multiple replicas, check each instance when suspecting drift.

### 11.2. Optimize Route Topology Rather Than Hand-Tuning Every Regex

Architectural options:

| Symptom | Approach | Caveat |
| --- | --- | --- |
| Many routes use `Path=/**` and filter by header regex | Partition paths by service if API contract permits | Can alter public API contract; needs migration |
| Duplicate routes sharing predicates and URIs | Merge if semantics truly match | Preserve per-branch filters, security, and quotas |
| Duplicate service-discovery routes | Audit discovery locator config and route ID generation | Avoid deleting routes needed by services |
| Multiple regexes parsing the same header | Validate once at edge or custom per-request cached logic | Never build global caches holding credentials |
| Low-priority route with very broad match | Separate explicit fallback and set proper order | Never let fallbacks bypass auth |
| Bad traffic mostly hitting unknown paths | Edge WAF/ingress policies and sound rate limiting | Never substitutes for fixing ReDoS regexes |

Focus on reducing **candidate evaluations** and **cost per evaluation** while preserving semantics. If business contracts require routing by Header/Query, never force clients to change URLs based on an unmeasured performance guess.

### 11.3. Route Caching Is Not Per-Request Result Memoization

Gateway Server WebFlux caches materialized route definitions/runtime routes. That **does not mean** `matches(exchange)` results are memoized globally for every incoming request.

Never build a naive map like:

~~~java
// WRONG idea: different users may hit the same path with different tokens/hosts.
Map<String, Boolean> matchedByPath = new HashMap<>();
~~~

When routes depend on Host, method, headers, query params, time, IP, or auth context, caching by **path alone** picks the wrong route. Conversely, caching by full request key creates high cardinality, memory bloat, and sensitive-data risks; it is rarely a safe optimization.

### 11.4. Dynamic Route Refresh Does Not Fix a Bad Regex

`RefreshRoutesEvent` or `POST /actuator/gateway/refresh` reloads route caches from their current source; it **does not cure a slow regex** and does not guarantee every Gateway replica immediately activates the new revision.

When replacing an old regex in production:

1. Validate config syntax and regexes before committing.
2. Commit versioned route definitions with rollback support.
3. Refresh each Gateway replica via your orchestration mechanism.
4. Verify runtime routes on each replica contain the new pattern revision.
5. Run positive/negative checks and canary traffic.
6. Monitor p99, CPU, mapping errors, and backend destinations.

Never equate "cache refreshed" with "optimization verified" before measuring live traffic.

## 12. Optimizing Predicates Within Security Boundaries

### 12.1. `Header` and `Host` Are Not Verified Identities

Example:

~~~yaml
predicates:
  - Host=admin.example.test
  - Header=X-Internal-User,^true$
~~~

does not prove a request is authenticated. Clients can spoof `Host` or custom headers across many network paths. Never remove **Spring Security**, backend authorization, mTLS, or network allowlists just because route matching looks "fast."

Routing predicates pick a destination; **authentication and authorization** decide who may do what. Test each layer independently.

### 12.2. `X-Forwarded-*` and IP Evaluation Cost

`RemoteAddr` matches CIDR ranges against the remote socket address. Behind an ingress, the peer is usually the proxy; `XForwardedRemoteAddr` or custom resolvers must verify **trusted proxy hops**, never blindly trusting client-supplied XFF headers.

When optimizing:

- Never replace `RemoteAddr` with a raw XFF string prefix check because it is "faster."
- Never set `trustAll` just to skip proxy-chain verification.
- Measure in real ingress topologies and test spoofed headers.
- When IP allowlisting is a security boundary, enforce it at the network/edge too, not solely in a Gateway predicate.

### 12.3. Request Bodies, Cookies, and Sensitive Payloads

`ReadBody` decodes and caches request bodies prior to routing, costing far more than `Method`/`Path`. If routing depends on data inside JWTs, cookies, or bodies:

- Consider adjusting contracts so routing uses metadata rather than large bodies.
- Cap body sizes and content types.
- Protect sensitive data; avoid needless payload caching or logging.
- Verify downstream filters/backends can still read the body after the predicate runs.
- Never treat a regex on a cookie as session authentication.

A predicate parsing JSON just to read one `"type"` field can decode the entire payload. If unavoidable, prove the cost is acceptable, handle malformed/oversized bodies safely, and avoid parsing the same payload repeatedly across predicates.

### 12.4. Rate Limiting and Retries Can Mask Benchmark Results

Rate limiters running after route selection add Redis/key-resolution cost on matched requests. Retries can generate **multiple downstream attempts per incoming request**. Therefore:

- In predicate-focused micro/HTTP benchmarks, use a stub backend and remove or fix unrelated filters across **both configurations**.
- In production-like load tests, keep security, rate limiting, circuit breakers, and retries enabled and measure end-to-end.
- Never disable limiters or auth in production to test "faster regexes" if doing so opens an attack vector.
- Whenever performance improves, verify downstream attempt counts did not simply drop because requests misrouted or failed early.

## 13. Regression Testing: Faster Must Still Route Correctly

### 13.1. Three Criteria for a Successful Optimization

A predicate change passes only when:

1. **Correctness:** valid and invalid requests route strictly according to the approved contract.
2. **Safety:** no dangerous regexes or unbounded inputs can stall CPU, and no unauthorized path opens.
3. **Performance:** CPU, allocations, or tail latency measurably improve under representative load.

**Never judge correctness from HTTP 200 alone**: a request might hit a fallback route, wrong backend, or local controller.

### 13.2. Equivalence Test Matrix for Two Regexes

The two patterns from Section 7:

~~~regex
^([A-Za-z0-9_-]+)+$
^[A-Za-z0-9_-]+$
~~~

demonstrate eliminating nested repetition within the same contract. A small deterministic unit test:

~~~java
package demo.gateway.predicate;

import java.util.List;
import java.util.regex.Pattern;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class RegexEquivalenceTest {

    private static final Pattern LEGACY =
            Pattern.compile("^([A-Za-z0-9_-]+)+$");
    private static final Pattern OPTIMIZED =
            Pattern.compile("^[A-Za-z0-9_-]+$");

    @Test
    void bothPatternsAgreeForSmallRepresentativeInputs() {
        List<String> inputs = List.of(
                "a", "abc", "A9_2", "CAT-007",
                "", "bad!", "hello world", "é", "Z?");

        for (String value : inputs) {
            boolean before = LEGACY.matcher(value).matches();
            boolean after = OPTIMIZED.matcher(value).matches();
            assertThat(after)
                    .as("Different decision for: " + value)
                    .isEqualTo(before);
        }
    }
}
~~~

This is a **small bounded-input unit test**; it does not mathematically prove equivalence across all infinite strings, and must never feed huge strings into the legacy regex. For simple expressions like this, structural regex review is primary proof while the test catches syntax slips.

### 13.3. Testing After Replacing `Header` with a Custom Factory

`BoundedChannelRoutePredicateFactory` from Section 8 intentionally **rejects duplicate headers** and caps length. Write an explicit test table:

| Request header | Built-in `Header=X-Channel,^partner$` | Custom `BoundedChannel(expected=partner)` |
| --- | --- | --- |
| `X-Channel: partner` | Matches per contract | Matches |
| `X-Channel: Partner` | No match (case-sensitive) | No match |
| Missing `X-Channel` | No match | No match |
| `X-Channel: partnerX` | No match | No match |
| Two values `partner` and `internal` | Depends on built-in multi-value handling | **No match** intentionally |
| Value longer than 16 | Depends on regex | No match per input cap |

Never document the two as having "identical semantics" if duplicate headers and length limits differ. Align input caps with API clients and backends.

### 13.4. Integration Testing Through a Real HTTP Gateway

Use `@SpringBootTest(webEnvironment = RANDOM_PORT)` with `WebTestClient` and a random-port backend stub (`MockWebServer` or WireMock). For a valid request:

~~~java
client.get()
        .uri("/api/catalog/items/42?mode=full")
        .header("X-Catalog-Key", "partner_42")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals(
                "X-Matched-Route", "catalog");
~~~

This is an **integration assertion snippet**, assuming `client` targets the Gateway HTTP server and the backend stub returns 200. Full tests should also verify the **recorded backend request** (method, path, headers, request count) and ensure no unintended retries occurred.

Negative cases such as header `partner!`, missing `mode`, or wrong method/path must:

- Not match the `catalog` route (no matching marker header).
- Not call the route's backend **in a single-route fixture**.
- When fallbacks exist, assert the fallback route ID/target rather than assuming every negative returns 404.

### 13.5. Property Tests and Boundary Inputs

A thorough suite can use a **fixed-seed** generator producing ASCII strings of length 0–64 to compare old vs. new logic across categories:

~~~text
length=0
length=1
length=16
length=32
length=33
contains disallowed punctuation
contains spaces
contains Unicode
repeated headers
duplicate query values
different Host/method/path
~~~

**Use only short, bounded inputs against dangerous legacy regexes.** Against the safe replacement pattern, test longer strings up to Gateway limits to verify input bounds and error handling. Log seeds so failures are reproducible.

### 13.6. When a Test Gets "Faster" Because a Filter Was Skipped

If after an optimization:

~~~text
Before: 200 OK + JWT authorized + backend request
After:  404 Not Found with zero backend calls
~~~

latency drops sharply, yet the behavior is **broken**. Likewise, a wildcard route missing `Method=POST` could return fast cached 200s on GETs while failing to persist writes.

Benchmarks must therefore track **functional success per input group**, not just aggregate response latency.

## 14. Regexes Are Not Only in Predicates: Distinguish `RewritePath` and Filters

Other components also use regexes:

- `RewritePath` `GatewayFilter` transforms URIs **after the route matches**.
- `RewriteResponseHeader` transforms response headers by pattern.
- Custom security/validation filters may run regexes on JWT claims, `Host`, paths, or bodies.
- Servlet/WebFlux filters at other layers may inspect inputs as well.

If CPU profiles show `Pattern.matcher` inside `RewritePath`, tuning a `Header` predicate will not fix it.

### 14.1. Comparing the Two Stages

~~~text
Incoming request
    ↓
Path/Header/Query RoutePredicateFactory  ← selects route; matching cost
    ↓
GatewayFilter: RewritePath(regex)        ← edits URI; filter cost
    ↓
NettyRoutingFilter → backend
~~~

Do not turn a filter regex into a predicate just to cut CPU: they serve **different purposes**. To avoid a rewrite step, align public/backend URI contracts or use `StripPrefix`/`SetPath` when equivalent, testing URL encoding, path variables, and route priorities carefully.

### 14.2. When Can `StripPrefix` Replace `RewritePath`?

If you only need to drop one leading path segment:

~~~text
Client:  /api/orders/42
Backend: /orders/42
~~~

`StripPrefix=1` can be simpler than a regex:

~~~yaml
filters:
  - StripPrefix=1
~~~

However, if rewriting restructures segments, renames paths, preserves specific suffixes, or modifies components conditionally, `StripPrefix` is not equivalent. **Test the exact path received by the backend**, especially with encoded slashes and repeated slashes.

Never claim every non-regex built-in filter beats regex filters in every release: benchmark against your actual implementation and workload.

### 14.3. Security Filter Regexes Still Need Review

Especially risky are regexes **entered by operators through a control plane** to match client-controlled headers. If an admin API accepts unvalidated `Header=...` or `RewritePath=...` rules, one bad pattern can roll out to every replica simultaneously.

Control planes should enforce:

1. Schema validation and allowlists of factory names/arguments.
2. Regex syntax validation, pattern-construct allowlists, or static ReDoS checks.
3. Input caps at ingress and inside custom predicates.
4. Approval/audit trails plus versioning and rollback.
5. Correctness tests before publishing a route refresh.
6. CPU/event-loop monitoring after rollout.

**Never let public requests supply regexes for the Gateway to compile.** Building a route predicate directly from client-supplied regexes invites both ReDoS and client-controlled routing bypasses.

## 15. Troubleshooting Predicate Performance Incidents

| Symptom | Possible cause | Where to investigate |
| --- | --- | --- |
| CPU spikes on requests with strange headers | Header regex with nested repetition/backtracking | CPU profile, inspect pattern, input caps |
| p99 rises while backend latency stays flat | Route scanning or synchronous predicates/filters | JFR, Gateway hit/miss mix, event-loop lag |
| Gateway is slow when returning 404 | Many candidate routes failing to match | Measure miss-path, count runtime routes, route order |
| Normal GETs are fast; rare queries are slow | `Query` regex or duplicate query parameter values | Near-miss tests, query length/value counts |
| CPU/request rises after adding routes | More candidate routes and predicate evaluations | Compare route IDs/counts, topology, flame graphs |
| Regex benchmark is fast yet Gateway stays slow | Bottleneck in TLS/Redis/filters/Netty/GC | Compare microbenchmark vs. HTTP/JFR |
| Switching `^([A-Za-z]+)+$` to `^[A-Za-z]+$` didn't help | Regex wasn't the hot path or inputs were always short | Find real bottleneck before further regex tuning |
| CPU didn't drop with a custom predicate | Built-in factory already compiled efficiently; overhead is elsewhere | Check live profiles and correctness tests |
| Long headers get 431/400 before Gateway routes | HTTP server/ingress rejected by size limit | Separate HTTP parser rejections from predicate misses |
| Gateway starts matching unintended routes | Broadened regex/wildcard or dropped `Method`/`Host` | Routing regression matrix, backend markers |
| Valid routes rejected after adding length cap | Legacy API contract permitted longer inputs | Verify max lengths, migration, client impact |
| One node still burns CPU after route refresh | Replica hasn't applied the new regex revision | Inspect active route revisions per node and refresh logs |
| 404 benchmark numbers jump unexpectedly fast | Test is measuring fast-fail misses rather than route hits | Separate statuses and backend call counts |
| Throughput drops when `DEBUG` is enabled | Log formatting/I/O or wiretap bottleneck | Compare logging profiles, sampling; turn off raw logs |
| Event loop stalls inside `Matcher.matches()` | Near-miss input triggering backtracking | Roll back pattern, block input at edge, ReDoS review |
| Memory climbs after adding `ReadBody` | Body decoding/caching during route matching | Payload caps, codecs, concurrency, profiling |
| Metrics time series explode suddenly | Raw paths/queries/tokens used as labels | Remove high-cardinality tags, cap labels |
| Auth bypassed after `Host`/`RemoteAddr` optimization | Predicate treated as security policy | Separate Spring Security/auth from routing tests |

### 15.1. Ordered Diagnostic Runbook

1. **Verify runtime routes**: route IDs, `order`, predicates, version; check recent dynamic/discovery routes.
2. **Verify workload**: breakdown of hits, misses, near-misses, malformed, and long inputs.
3. **Isolate downstream**: use a fast stub backend and verify downstream call counts.
4. **Check server-side CPU**: check for saturation or container throttling.
5. **CPU profile**: share of samples in regex/predicates vs. filters/transport.
6. **Audit regexes**: nested repetition, overlapping alternation, broad `.*`, or user-supplied patterns.
7. **Check input caps** at ingress/Netty and inside custom predicates.
8. **Make the smallest change** preserving semantics.
9. **Run regression + performance suites** with identical test profiles and arrival rates.
10. **Roll out reversibly** while watching p99, CPU, 4xx/5xx, and route selection in production-like traffic.

Never expose unrestricted Gateway Actuator endpoints to the Internet to debug. A secured read-only management endpoint suffices to inspect route inventories; write/refresh operations belong behind a secured control plane.

## 16. Designing A/B Experiments That Don't Fool You

### 16.1. Define Clear Traffic Mix Groups

| Group | Example share | Condition | Expected outcome |
| --- | ---: | --- | --- |
| H1 | 50% | Valid Path + Method + Header + Query | Matches route + backend 200 |
| M1 | 20% | Path outside route | No route match |
| M2 | 15% | Valid Path/Method, short wrong Header | No match |
| M3 | 10% | Valid Path/Method/Header, wrong Query | No match |
| B1 | 5% | Valid input near max length | Matches cleanly, stable latency |

This is a **hypothetical traffic mix for benchmark design**, not real production traffic proportions. If production logs show 90% miss-path traffic, adjust the test mix accordingly.

**Outputs to record:** counts per group, response statuses, route markers, downstream calls, p95/p99, CPU/container throttling, allocations, and configuration revision. Never collapse all statuses into one undifferentiated average.

### 16.2. Experimental Conditions for Fair Comparison

One test plan:

~~~text
Build A: Gateway 5.x, legacy regex (only small controlled test traffic)
Build B: identical binary/dependencies, optimized regex

Warm-up:
  same request count, same arrival rate, backend returns identical body

Measurement:
  same traffic mix, same route count, same CPU/memory limits
  multiple repeated runs; record confidence/variance where available

Correctness gate:
  identical route ID / backend destination
  identical allow/deny decisions
  identical CORS/CSRF/rate-limit security per contract

Performance gate:
  compare CPU/request, p95/p99, failure/timeout rates
~~~

Run Build A with a dangerous legacy pattern **only in an isolated environment with short reviewed inputs**—never send long crafted near-miss inputs at a live user-facing Gateway. Once a regex is known to have ReDoS, **fix it immediately** via change control rather than keeping it around for production benchmarks.

### 16.3. Sample Reporting Table — Not Measured Data

| Field | Baseline | Optimized | Assessment |
| --- | --- | --- | --- |
| Config revision | `v1` | `v2` | Confirm identical code/BOM |
| Route count | From runtime | From runtime | Must match if only regex changed |
| CPU-seconds / 1k requests | Measured | Measured | Reduction is a positive signal |
| p99 hit | Measured | Measured | Must not exceed SLO |
| p99 miss | Measured | Measured | Often more sensitive to matching cost |
| Backend attempts | Measured | Measured | No unintended change |
| Route-match regression tests | PASS/FAIL | PASS/FAIL | Must PASS |
| ReDoS / static analysis | Warnings? | Warnings? | Never deploy dangerous patterns |

Never fill estimated numbers into tables as if they were real measurements. Good results on a laptop **do not confirm** identical behavior inside containers with CPU throttling, many routes, and TLS.

### 16.4. When Optimization Shows No Improvement

If CPU stays high yet JFR no longer shows samples in regex matching:

- Inspect path matching and how many routes are actually evaluated.
- Inspect codecs/serialization, Netty HTTP client pooling, DNS/TLS.
- Inspect Redis rate limiters and timeout/retry budgets.
- Inspect access logs, tracing exporters, and metric tags.
- Inspect allocations/GC and Netty direct memory.

Stop "optimizing regexes" just because that was the initial hypothesis once data shows the bottleneck moved elsewhere.

## 17. Production Rollout Checklist for Optimized Predicates

- [ ] Verified via benchmarks/profiles that route matching is truly a hot path, rather than guessing.
- [ ] Separated predicate cost from `GatewayFilter`, Spring Security, Redis, and transport costs.
- [ ] Audited runtime route count and sources, not just entries in static YAML.
- [ ] Verified predicates combine with AND/OR per contract without shifting route priority/overlap unintentionally.
- [ ] Preferred `Method`/`Path`/`Host`/CIDR/Query presence when semantics match instead of custom regexes.
- [ ] Audited Java regexes for nested repetition, overlapping alternation, backreferences, and backtracking.
- [ ] Bounded input lengths, header counts, and query parameter counts at edge/server and inside custom code.
- [ ] Never accepted arbitrary regexes from public client requests.
- [ ] Precompiled `Pattern`s for repeated custom regexes; never shared `Matcher`s across threads.
- [ ] Never cached route matches by path alone when Host/Header/Method/Query/IP also participate.
- [ ] Kept DB/Redis/HTTP/blocking I/O out of synchronous custom predicates.
- [ ] Kept Gateway Server WebFlux classes separate from Web MVC classes.
- [ ] Used `name/args` syntax for regexes containing commas inside quantifiers to avoid argument mis-parsing.
- [ ] Passed unit, route integration, and security tests both before and after changing regexes.
- [ ] Verified negative cases do not match or forward in single-route fixtures.
- [ ] Verified exact **route ID and backend** on fallback/overlap routes, not merely HTTP status.
- [ ] Tested Time/`RemoteAddr`/`ReadBody` predicates with representative data and trust boundaries.
- [ ] Used JMH only for pure Java comparisons; ran real HTTP load tests against Gateway + stub backend.
- [ ] Included hit/miss/near-match workloads, multiple concurrency levels, and full latency distributions.
- [ ] Held JDK, hardware, route count, CPU/memory limits, TLS mode, and instrumentation constant across benchmarks.
- [ ] Kept raw paths, queries, headers, and tokens out of metric labels and PII out of wiretap logs.
- [ ] Placed Gateway Actuator behind a secured read-only management plane.
- [ ] Enforced validation, revisions, per-replica refreshes, canaries, and rollbacks for dynamic route changes.
- [ ] Configured SLOs on p95/p99, CPU per request, error rates, and event-loop stall alerts.

## 18. Self-Check Questions

**1. Why is `Path=/api/orders/**` usually preferable to a custom regex `^/api/orders/.*`?**

Because the `Path` predicate is purpose-built for URL paths, expresses intent clearly, follows Spring URI-template matching rules, and avoids hand-rolling/compiling regexes. Still, benchmark actual impact on your exact release.

**2. Does compiling a `Pattern` once prevent ReDoS?**

No. It eliminates **repeated compilation** cost, yet `Matcher.matches()` can still backtrack exponentially on a dangerous pattern.

**3. Can `Pattern` and `Matcher` be shared across requests?**

`Pattern` is immutable/thread-safe and can be shared; `Matcher` is stateful and not thread-safe, so create a fresh `Matcher` per evaluation.

**4. Why might dropping `Method=POST` make a benchmark "faster" yet fail acceptance?**

Because requests meant to be rejected can reach the backend; that changes **route semantics and weakens access boundaries** rather than optimizing equivalent work.

**5. What does a benchmark miss if it sends only matching requests?**

It misses the cost of non-matching requests, especially when the Gateway scans many candidate routes or evaluates regexes on near-miss inputs before failing.

**6. Why isn't `spring.cloud.gateway.requests` alone enough to measure all predicate misses?**

Because the Gateway metrics filter usually runs in the filter chain **after route selection**; unmatched requests may never pass through it. Combine HTTP server metrics with CPU profiling.

**7. Does the `Host` predicate use Java regex like `Header`?**

Not the same syntax: docs define `Host` as Ant-style host patterns, whereas `Header`, `Query`, and `Cookie` evaluate Java regexes on their values.

**8. Why can `a++a` behave differently from `a+a`?**

The possessive quantifier `++` will not backtrack to yield a character for the trailing `a`; such a change can alter the accepted language.

**9. Should you replace `RequestRateLimiter` with a regex "allowing only good clients" to go faster?**

No. Regex predicates carry no reliable quota state and do not authenticate identity. Rate limiting requires dedicated quota enforcement alongside authentication and trust boundaries.

**10. With multiple matching routes, why is changing `order` to save CPU risky?**

Because a broader route can match before a more specific one, changing backend, filters, and security policies. Verify ordering via route IDs and downstream targets.

## 19. Official References and Further Reading

1. [Spring Cloud Gateway Server WebFlux 5.0 — Route Predicate Factories](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/request-predicates-factories.html): AND composition, `Path`/`Method`/`Host`/`Header`/`Query`/`Cookie`/`RemoteAddr`/`ReadBody`.
2. [Spring Cloud Gateway Server WebFlux 4.2 — Route Predicate Factories](https://docs.spring.io/spring-cloud-gateway/reference/4.2/spring-cloud-gateway/request-predicates-factories.html): checking WebFlux 4.x behavior and config prefixes.
3. [Spring Cloud Gateway 5.0 — Developer Guide](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/developer-guide.html): building `AbstractRoutePredicateFactory<Config>`.
4. [Spring Cloud Gateway 5.0 — Predicate/Filter Configuration](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/configuring-route-predicate-factories-and-filter-factories.html): shortcut vs. full `name/args` syntax.
5. [Spring Cloud Gateway 5.0 — Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/5.0/configprops.html): namespaces, metrics, and defaults by version.
6. [Spring Cloud Gateway Server WebFlux — Global Filters and Metrics](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/global-filters.html): route-specific metrics and filter ordering.
7. [Java SE — `Pattern` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/regex/Pattern.html): precompilation, `Pattern.matches`, thread safety, quantifiers, and atomic groups.
8. [Java SE — `Matcher` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/regex/Matcher.html): mutable state and thread-safety rules of `Matcher`.
9. [OWASP — Regular Expression Denial of Service](https://wstg.owasp.org/latest/4-Web_Application_Security_Testing/07-Injection/28-Regular_Expression_Denial_of_Service/): risks of exponential backtracking.
10. [OWASP — Denial of Service Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html): input size limits, CPU exhaustion, and avoiding catastrophic regexes.
11. [JMH — OpenJDK Microbenchmark Harness](https://openjdk.org/projects/code-tools/jmh/): JVM microbenchmarking methodology.
12. [Spring Framework — `WebTestClient`](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): HTTP testing with response assertions, suited for Gateway integration tests.

**Remember:** To cut predicate overhead in Spring Cloud Gateway, **measure first**, **eliminate unnecessary route/predicate evaluations**, **prefer specialized checks**, and **avoid regexes with dangerous backtracking**. In custom code, reuse `Pattern` while instantiating `Matcher` per check; bound inputs and never block the WebFlux event loop. An optimization only succeeds when **route selection and security remain intact** alongside measurable improvements in **CPU, allocations, or p95/p99** under a representative workload.
