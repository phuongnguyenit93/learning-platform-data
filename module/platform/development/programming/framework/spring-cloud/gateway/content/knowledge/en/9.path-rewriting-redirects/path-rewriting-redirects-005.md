# Escaping Replacement Characters in Spring Cloud Gateway YAML and Java DSL

## 1. Why Is the Same Rewrite Written Differently?

In **Spring Cloud Gateway**, requests pass through **route predicates** to select a route, and then **GatewayFilters** can transform paths or headers before forwarding to a microservice. The Gateway can also modify response headers, such as `Location` in a backend redirect. For example, a client calls `/public/orders/42` while the backend only expects `/orders/42`.

With `RewritePath` or `RewriteResponseHeader`, a **regular expression (Java regex)** identifies the segment to match, while a **replacement** determines the substituted content. Characters like `$`, `{`, and `\` are easily misunderstood because they travel through multiple layers:

1. **YAML**: parses scalars in plain, single-quoted, or double-quoted form.
2. **Spring Boot/Spring Cloud**: loads and binds configuration; `${property}` syntax may be interpreted as a configuration property placeholder.
3. **Java regex**: capture group `(?<segment>...)` is referenced via `${segment}` or `$1` in the replacement.
4. **Java DSL**: Java `String` literals have their own backslash escaping rules; Java strings normally do not need YAML-style placeholder protection.

The goal of this lesson is to write valid syntax, understand precisely **which layer processes each escape**, and avoid corrupting request paths, leaking backend URLs in redirects, or causing Gateway startup/runtime errors. These techniques support operating a microservices edge with authentication, rate limiting, circuit breakers, retries, TLS, service discovery, and request observability. They **do not replace** those security or resiliency mechanisms.

> **Quick rule of thumb:** Given regex `/public/(?<segment>.*)`, the final replacement at the Java regex layer is `/${segment}`. In **`application.yml`**, typically write `/$\{segment}`; in **Java DSL**, write `"/${segment}"`. This is the syntax shown in the Spring Cloud Gateway documentation for `RewritePath`.

### 1.1. Version and variant scope

The main examples use **Gateway Server WebFlux 4.3+/5.x**, declaring routes under `spring.cloud.gateway.server.webflux.routes`. For WebFlux 4.2 and earlier, the common prefix is `spring.cloud.gateway.routes`. WebFlux Java DSL uses `RouteLocatorBuilder`, whereas Gateway Server Web MVC uses `RouterFunction` with before-filters/after-filters. Do not mix WebFlux and Web MVC APIs merely because both carry the Spring Cloud Gateway name.

## 2. Regex and Replacement Syntax: Two Different Sides

Suppose we need to transform:

```text
Client:  GET /public/orders/42
Backend: GET /orders/42
```

Search pattern:

```regex
^/public/(?<segment>.*)$
```

- `^` and `$` in the **regex** anchor the start and end of the string.
- `(?<segment>.*)` is a named capture group `segment`, capturing `orders/42`.
- Replacement `/${segment}` joins `/` with the group contents, producing `/orders/42`.
- `$1` can substitute the first capture group if the regex uses unnamed `(...)`, though it breaks easily when group ordering changes.

| Token | Where does it appear? | Meaning |
|---|---|---|
| `(?<name>...)` | **Regex** side | Defines a named group `name` |
| `(...)` | **Regex** side | Defines a numbered group |
| `${name}` | Java regex **replacement** side | Substitutes value of named group `name` |
| `$1` or `$2` | **Replacement** side | Substitutes numbered group 1 or 2 |
| `{id}` | `Path`/`SetPath` URI template | **Not** regex group reference syntax |

The `$` in regex `...$` is an **end-of-string anchor**; it has nothing to do with group referencing like `${name}` in replacements.

## 3. Writing `RewritePath` in YAML

### 3.1. Shorthand form

```yaml
# application.yml – Gateway Server WebFlux 4.3+/5.x
server:
  port: 8080

spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-route
              uri: http://localhost:8081
              predicates:
                - Path=/public/orders/**
              filters:
                - RewritePath=^/public/(?<segment>.*)$, /$\{segment}
                - AddRequestHeader=X-Via-Gateway, true
```

For `GET /public/orders/42`, the `Path` predicate selects `orders-route` first; `RewritePath` turns the path into `/orders/42` before proxying to `http://localhost:8081`. The backend also receives the header `X-Via-Gateway: true`.

In YAML config, pay close attention to **`$\{segment}`**: the backslash before `{` prevents the configuration layer from misinterpreting the group reference before it reaches Java regex. You do not add this backslash in Java DSL.

### 3.2. Full `name/args` form

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-route
              uri: http://localhost:8081
              predicates:
                - Path=/public/orders/**
              filters:
                - name: RewritePath
                  args:
                    regexp: '^/public/(?<segment>.*)$'
                    replacement: '/$\{segment}'
```

This is an **alternative** syntax to the shorthand snippet, not something a route declares twice. The `name/args` form makes it easier to verify parameter names `regexp` and `replacement`. YAML single quotes keep the backslash intact in the scalar text; however, that does not mean Spring skips downstream configuration processing altogether.

### 3.3. Escaping table by YAML scalar style

Suppose you want to pass a replacement representing Java regex `/${segment}`:

| YAML style | Content in file | Notes |
|---|---|---|
| Plain | `replacement: /$\{segment}` | Concise style commonly used in examples |
| Single quoted | `replacement: '/$\{segment}'` | Preserves `\` inside scalar, readable |
| Double quoted | `replacement: "/$\\{segment}"` | YAML requires `\\` to produce one `\` |
| **Wrong** | `replacement: "/$\{segment}"` | `\{` is not a valid YAML escape in double quotes |
| Error-prone | `replacement: /${segment}` | May be interpreted by Spring as a `segment` property placeholder |

Never ask "how many backslashes?" without tracing the processing layers: **file text** → **YAML parse** → **Spring binding** → **Java regex replacement**. If configuration passes through Helm, CI templates, environment variables, or another YAML generator, verify those additional layers too.

## 4. Java DSL: Direct Group Syntax

In **Gateway Server WebFlux**, routes can be defined in Java:

```java
package com.example.gateway;

import org.springframework.cloud.gateway.route.RouteLocator;
import org.springframework.cloud.gateway.route.builder.RouteLocatorBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GatewayRoutes {
    @Bean
    RouteLocator routes(RouteLocatorBuilder builder) {
        return builder.routes()
            .route("orders-route", r -> r
                .path("/public/orders/**")
                .filters(f -> f
                    .rewritePath(
                        "^/public/(?<segment>.*)$",
                        "/${segment}")
                    .addRequestHeader("X-Via-Gateway", "true"))
                .uri("http://localhost:8081"))
            .build();
    }
}
```

In Java source, **`"/${segment}"`** is an ordinary `String` literal: Java has no `${...}` string interpolation syntax. That exact string goes straight to regex replacement processing.

A **common mistake** is copying the YAML form `/$\{segment}` verbatim into a Java string:

```java
// Wrong: \{ is not a valid escape in a Java String.
// .rewritePath("^/public/(?<segment>.*)$", "/$\{segment}")

// Correct:
.rewritePath("^/public/(?<segment>.*)$", "/${segment}")
```

If you write `"/$\\{segment}"` in Java source, Java constructs a replacement string containing an actual `\` character; Java regex treats it as an escape that **disables group referencing**. Therefore, when you need a group reference, simply write `"/${segment}"`.

### 4.1. Java regex containing backslashes

To match an all-digit ID, the logical regex contains `\d+`; in a **Java String** you must write `\\d+`:

```java
.rewritePath(
    "^/public/orders/(?<id>\\d+)$",
    "/orders/${id}")
```

| Regex intent | In single-quoted/plain YAML | In a Java `String` |
|---|---|---|
| `\d+` — digits | `\d+` | `"\\d+"` |
| `\.` — literal dot | `\.` | `"\\."` |
| `\?` — literal question mark | `\?` | `"\\?"` |
| `(?<id>...)` — named group | `(?<id>...)` | `"(?<id>...)"` |

In double-quoted YAML regexes, `\d` is also not a valid YAML escape, so you need `\\d` or single quotes instead.

### 4.2. Gateway Server Web MVC Java DSL

Gateway Server **Web MVC** has a different `rewritePath` before-filter and routing API:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;

import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.rewritePath;
import static org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions.uri;
import static org.springframework.cloud.gateway.server.mvc.handler.GatewayRouterFunctions.route;
import static org.springframework.cloud.gateway.server.mvc.handler.HandlerFunctions.http;

@Configuration
class MvcGatewayRoutes {
    @Bean
    RouterFunction<ServerResponse> ordersProxy() {
        return route("orders-route")
            .GET("/public/orders/**", http())
            .before(uri("http://localhost:8081"))
            .before(rewritePath(
                "^/public/(?<segment>.*)$",
                "/${segment}"))
            .build();
    }
}
```

The **Java String** layer in MVC still uses `"/${segment}"`. When combining MVC with `lb()`, verify before-filter ordering and load-balancer rules in the documentation for your exact version.

## 5. Named Groups, Numbered Groups, and Missing Groups

### 5.1. Two named groups

```text
Regex:        ^/api/v1/(?<resource>orders|items)/(?<id>\d+)$
Replacement:  /${resource}/${id}
Input:        /api/v1/orders/42
Output:       /orders/42
```

- In **YAML**, write `/$\{resource}/$\{id}` for the replacement.
- In **Java DSL**, write `"/${resource}/${id}"` for the replacement.
- In Java source, `\d+` in the regex must be written `"\\d+"`.

### 5.2. Numbered groups

```text
Regex:        ^/api/v1/(orders|items)/(\d+)$
Replacement:  /$1/$2
Input:        /api/v1/items/17
Output:       /items/17
```

`$1` and `$2` have no curly braces, so they normally do not clash with `${property}`. However, they break easily if a new capture group is inserted. For important routes, named groups are usually easier to maintain.

### 5.3. Referencing a non-existent group name

```yaml
# Wrong: regex only defines group 'name', while replacement asks for 'id'.
- RewritePath=^/api/(?<name>.*)$, /$\{id}
```

Java regex can throw `IllegalArgumentException` because no group named `id` exists. A route configuration that loads cleanly does not guarantee every request rewrites successfully; send real URLs that trigger the expression.

## 6. When You Want a Literal `$` Character

In Java `Matcher`, `$` in the replacement is group syntax. For a literal dollar sign, use `\$` in the **replacement value passed to the regex**. In Java source, write `"\\$"` to pass a single backslash:

```java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

String input = "price=42";
String regex = "(?<amount>\\d+)";

String withGroup = Pattern.compile(regex).matcher(input)
    .replaceAll("USD ${amount}"); // "price=USD 42"

String literalDollar = Pattern.compile(regex).matcher(input)
    .replaceAll("\\$"); // "price=$"

String replacement = Matcher.quoteReplacement("${amount}");
String exactLiteral = Pattern.compile(regex).matcher(input)
    .replaceAll(replacement); // "price=${amount}"
```

`Matcher.quoteReplacement(s)` converts `s` into a **literal** replacement: `$` and `\` are no longer treated as group-control characters. Use it only when you **do not want** capturing group interpolation; if you quote `"${amount}"` expecting the captured group value, the result will be wrong.

## 7. When `SetPath` or `StripPrefix` Is Simpler

Not every path change needs regex:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: product-route
              uri: http://localhost:8081
              predicates:
                - Path=/public/products/{id}
              filters:
                - SetPath=/products/{id}
```

`SetPath` uses the predicate's **URI template** variable `{id}`, not Java regex `${id}` or `$\{id}`. With `GET /public/products/42`, the backend receives `/products/42`.

| Goal | Suitable filter | Example |
|---|---|---|
| Drop first N segments | `StripPrefix` | `StripPrefix=1` |
| Set path from URI template variables | `SetPath` | `SetPath=/products/{id}` |
| Replace path via Java regex | `RewritePath` | `RewritePath=... , /$\{segment}` |
| Prepend fixed prefix | `PrefixPath` | `PrefixPath=/v1` |

`Path` predicates always participate in **route selection first**, while the filters above process the path after matching. Do not stack `RewritePath` and `StripPrefix` sequentially without tracing the exact path after each step.

## 8. Replacements When Rewriting Redirect Responses

### 8.1. `RedirectTo` vs. `RewriteResponseHeader`

**`RedirectTo`** returns a redirect directly from the Gateway, for example:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: docs-redirect
              uri: http://localhost:8081
              predicates:
                - Path=/old-docs
              filters:
                - RedirectTo=302, https://docs.example.test/new-docs
```

Here the redirect URL is a fixed configured value without regex group references. **`RewriteResponseHeader`**, by contrast, processes header values returned in the **backend response** after the Gateway proxies the request; `RewriteLocationResponseHeader` is a filter specifically tailored to the `Location` header.

### 8.2. Rewriting the `Location` header from an internal host to a public host

Suppose the backend returns:

```http
HTTP/1.1 302 Found
Location: http://backend.internal/orders/42
```

The Gateway wants to return `Location: https://api.example.test/orders/42`. You can configure:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-redirect
              uri: http://localhost:8081
              predicates:
                - Path=/orders/**
              filters:
                - name: RewriteResponseHeader
                  args:
                    name: Location
                    regexp: '^http://backend\.internal(?<path>/.*)$'
                    replacement: 'https://api.example.test$\{path}'
```

`(?<path>/.*)` captures the path part of the backend URL; the replacement in **YAML** uses `$\{path}`. `\.` in the regex matches the literal dots in the hostname. For redirects that also involve relative URLs, protocols, queries, and proxy headers, consider `RewriteLocationResponseHeader` or explicit logic instead of an overly broad regex.

Only rewrite to approved public hosts; never take arbitrary target hosts from clients or untrusted headers, as that can create an **open redirect**. Inbound/outbound TLS, OAuth2/JWT, and access control remain separate policies.

## 9. Common Errors

| Symptom | Cause | Resolution |
|---|---|---|
| "Could not resolve placeholder" error | YAML treats `${segment}` as a config placeholder | Use `$\{segment}` in YAML |
| YAML parser reports invalid escape | Double-quoted string contains `\{` or `\d` | Use single quotes/plain scalar or escape as `\\{`, `\\d` |
| Java `illegal escape character` | Java source has `"/$\{id}"` or `"\d+"` | Use `"/${id}"` and `"\\d+"` |
| Rewrite does not change path | Regex does not match actual path | Check predicate, regex, filter order, and backend path |
| Java `IllegalArgumentException` on group | Replacement references an undefined group | Re-check `(?<id>...)` and `${id}` |
| Java `IndexOutOfBoundsException` | `$2` used when regex has no second group | Fix group index or switch to named groups |
| Backend returns `404` after rewrite | Rewritten path does not match backend API | Log path before/after filter; verify backend |
| Redirect leaks internal hostname | Backend `Location` not rewritten | Use controlled `RewriteLocationResponseHeader` or `RewriteResponseHeader` |
| Discrepancy across encoded URLs | Proxy, WebFlux, and backend treat `%2F`/dot segments differently | Test across all layers and establish canonical paths |

## 10. Hands-on Testing

### 10.1. Testing request paths

You need a Gateway at `localhost:8080` with the Section 3 configuration and a **path-echoing** backend at `localhost:8081`. You can run:

```bash
curl -i 'http://localhost:8080/public/orders/42'
curl -i 'http://localhost:8080/public/orders/42/items/1'
curl -i 'http://localhost:8080/public/catalog/42'
curl --path-as-is -i 'http://localhost:8080/public/orders/a%2Fb'
```

The first two requests match the route and the backend is expected to receive `/orders/42` and `/orders/42/items/1`. The `/public/catalog/42` request does not match the sample predicate; for percent-encoded slashes, observe the **actual received path** rather than guessing the status. If the backend is not running, a connection failure differs from a non-matching regex.

### 10.2. Testing redirects

Have the backend return `302` with `Location: http://backend.internal/orders/42`, use the Section 8 configuration, and call:

```bash
curl -i 'http://localhost:8080/orders/42'
```

Do not use `-L` in the initial step: `curl -L` automatically follows redirects and can hide the `Location` header you need to inspect. After a successful rewrite, the client should receive `Location: https://api.example.test/orders/42`. Otherwise, inspect the actual backend response and the route's filter configuration.

### 10.3. Testing Java regex independently

The following Java snippet verifies that the regex and replacement work at the **Java layer**:

```java
import java.util.regex.Pattern;

public class RewriteCheck {
    public static void main(String[] args) {
        String source = "/public/orders/42";
        String regex = "^/public/(?<segment>.*)$";
        String replacement = "/${segment}";
        String result = Pattern.compile(regex)
            .matcher(source)
            .replaceAll(replacement);

        if (!"/orders/42".equals(result)) {
            throw new AssertionError(result);
        }
        System.out.println(result);
    }
}
```

A standalone Java check does not prove that YAML configuration bound properly or that the proxy forwarded the right path. Therefore, also test requests through a real Gateway and, in multi-tier systems, through a production-like reverse proxy/ingress.

## 11. Safety Principles When Rewriting Paths and Headers

1. **Separate matching from rewriting:** `Path` selects the route first; `RewritePath` modifies the request afterward. If the wrong route matches, changing the replacement will not fix matching.
2. **Constrain patterns:** prefer `(?<id>\d+)` when IDs are purely numeric; use `.*` intentionally and anchor with `^`/`$` when matching the whole path.
3. **Treat encoding as a boundary:** `%2F`, `%252F`, and `..` can be interpreted differently by different layers; never decode an entire string arbitrarily and rely on it for authorization.
4. **Protect redirects:** allow only valid hosts/schemes and inspect the `Location` header. Never treat URL rewriting as a substitute for access control or JWT validation.
5. **Avoid regex for simple tasks:** use `StripPrefix`/`SetPath` when simply dropping segments or setting paths via URI templates.
6. **Verify stack and version:** Server WebFlux and Server Web MVC have distinct APIs and property prefixes; use a Spring Cloud release train compatible with Spring Boot.
7. **Observe the full path:** selectively log route ID, path before/after filters, and response status; avoid logging tokens, cookies, or sensitive paths. When using `lb://`, discovery and load balancing must also be configured.
8. **Test retry/circuit breaker and TLS:** rewriting can change the downstream URL, but it does not make retries idempotent or fix TLS connections. Secure Actuator endpoints if used to inspect routes/filters.

## 12. Exercises and Answers

**Exercise 1.** Regex `/legacy/(?<rest>.*)` needs to rewrite to `/v2/<rest>`. Write the replacement in YAML and Java DSL.

**Answer:** YAML `/v2/$\{rest}`, Java DSL `"/v2/${rest}"`. The regex must define the `rest` group.

**Exercise 2.** Why might YAML `replacement: "/$\{rest}"` fail? How do you fix it?

**Answer:** `\{` is not a valid YAML double-quoted escape. Use `replacement: '/$\{rest}'` or `replacement: "/$\\{rest}"`.

**Exercise 3.** What is wrong with `rewritePath("/v1/(?<id>\\d+)", "/$\{id}")` in Java DSL?

**Answer:** The regex `\\d+` is right for Java source, whereas `\{id}` in the replacement is not a valid Java escape. Write `"/${id}"`.

**Exercise 4.** Does `SetPath=/products/{id}` use the same escaping rules as `RewritePath`?

**Answer:** No. `SetPath` uses the predicate's URI template `{id}`; `RewritePath` uses regex group `${id}`.

**Exercise 5.** The backend returns `Location: http://backend.internal/orders/9`. Should you use `RewritePath` to fix the client's redirect URL?

**Answer:** No. `RewritePath` modifies the **request path**; `RewriteResponseHeader` or `RewriteLocationResponseHeader` modifies the **response `Location`**.

**Exercise 6.** You want to pass the literal string `price=$5` into `Matcher.replaceAll`; how do you prevent `$5` from being treated as a group reference?

**Answer:** Use `Matcher.quoteReplacement("price=$5")` when a literal replacement is needed. Do not quote the entire replacement if your goal is to substitute a capturing group.

## 13. Official Documentation

- [Spring Cloud Gateway – RewritePath GatewayFilter (Server WebFlux)](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/rewritepath-factory.html): YAML `$\{segment}` example.
- [Spring Cloud Gateway – RewriteResponseHeader GatewayFilter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/rewriteresponseheader-factory.html): using regex/replacement on response headers.
- [Spring Cloud Gateway – SetPath GatewayFilter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/setpath-factory.html): `{id}` template vs. regex groups.
- [Spring Cloud Gateway – RewritePath Filter (Server Web MVC)](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/filters/rewritepath.html): MVC YAML and Java DSL.
- [Spring Cloud Gateway project – Java RouteLocatorBuilder example](https://spring.io/projects/spring-cloud-gateway): `rewritePath(..., "/${segment}")` in Java.
- [Oracle Java – Matcher](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/regex/Matcher.html): `$1`, `${name}`, and `quoteReplacement`.

**Key takeaway:** The final regex replacement target for group `segment` is `/${segment}`. In **Spring Cloud Gateway YAML**, write `/$\{segment}`; in **Java DSL**, write `"/${segment}"` directly. Clearly understanding the **YAML → Spring config → Java regex** boundary ensures accurate path and redirect-header rewriting while avoiding subtle escaping bugs.
