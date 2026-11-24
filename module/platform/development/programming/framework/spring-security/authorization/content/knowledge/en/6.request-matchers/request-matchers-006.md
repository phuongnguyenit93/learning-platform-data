# Context Path, Servlet Path, Base Path, and the Actual Address Being Matched

A common situation in Spring Security: the browser accesses `https://example.com/shop/orders/42`, the `@GetMapping("/orders/{id}")` controller works as expected, yet `requestMatchers("/shop/orders/**")` fails to match as intended. Or the application sits behind a reverse proxy at `/edge/shop`, while the `SecurityFilterChain` checks `/api/**`. Usually the root cause is not roles or authorities, but **matching against the wrong path layer**.

This lesson explains four concepts that are often confused: **context path**, **servlet path**, **base path**, and the **actual request address**. The focus is `RequestMatcher` on **Spring Security Servlet**, especially `PathPatternRequestMatcher` since Spring Security 6.5, legacy MVC matchers, `securityMatcher`, `authorizeHttpRequests`, and reverse proxies. The goal is to pinpoint the exact request path seen by the application and write policies for the right path, without using ad-hoc string matching that introduces vulnerabilities.

## 1. An HTTP Request Has Multiple "Paths"

Suppose the browser requests:

~~~text
GET https://example.test/shop/orders/42?view=summary
~~~

Assume the Servlet app is deployed with **context path `/shop`** and uses `DispatcherServlet` at the default `/` mapping. In a typical Servlet mapping, the observable values are:

| Source | Example value | Meaning |
| --- | --- | --- |
| External browser URL | `https://example.test/shop/orders/42?view=summary` | Includes scheme, host, path, and query string. |
| `request.getRequestURI()` | `/shop/orders/42` | URI path seen by the Servlet container, **including context path**, **excluding query string**. |
| `request.getContextPath()` | `/shop` | Prefix locating the web application within the container. |
| `request.getServletPath()` | `/orders/42` | Portion determined by the Servlet API per servlet mapping; with default `/` mapping, typically the path inside the app. |
| `request.getPathInfo()` | `null` | Remaining path outside the servlet mapping, if that mapping type produces a remainder. |
| `request.getQueryString()` | `view=summary` | Separate query, **not** a default component of path matchers. |
| Path relative to context | `/orders/42` | This is the path form `PathPatternRequestMatcher` uses for matching. |
| Controller mapping | `/orders/{id}` | Declared relative to `DispatcherServlet`'s mapping scope. |

With `PathPatternRequestMatcher`, the matcher `/orders/**` matches the URL above **because the `/shop` context is stripped from the path used for matching**. Conversely, writing `/shop/orders/**` puts the context path into the pattern and easily causes the rule to miss.

A short diagram:

~~~text
Browser URL: https://example.test/shop/orders/42?view=summary
                 |             |      |          |
                 |             |      |          +-- query: view=summary
                 |             |      +-- route: /orders/42
                 |             +-- context path: /shop
                 +-- scheme/host, NOT part of regular path matchers

getRequestURI()       = /shop/orders/42
getContextPath()      = /shop
PathPatternRequestMatcher sees path relative to context = /orders/42
Sensible matcher      = /orders/**
Error-prone matcher   = /shop/orders/**
~~~

The values of `servletPath` and `pathInfo` **depend on the servlet mapping style** (`/`, `/mvc/*`, exact mapping, extension mapping, etc.). Never blindly assume `getServletPath()` is the full URL minus context path, nor that `getPathInfo()` is always non-null.

## 2. What Is Context Path? It Is Not an Arbitrary Prefix in requestMatchers

The **context path** is the path attached to the *entire web application* in the Servlet container. In Spring Boot on the Servlet stack, the standard property is:

~~~yaml
server:
  servlet:
    context-path: /shop
~~~

If an endpoint in the app is defined as `GET /orders/42`, a client directly accessing the server calls `GET /shop/orders/42`. In the Servlet API, `getContextPath()` normally returns `/shop`. If deployed at the root context, the result is typically the **empty string `""`**, not a slash `/`.

`PathPatternRequestMatcher` expects patterns **relative to the context path**. For example, in a Spring Boot 3 project with Spring Security **6.5+** providing `PathPatternRequestMatcher`, this is a valid configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;

@Configuration
public class ContextPathSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        PathPatternRequestMatcher.Builder paths =
                PathPatternRequestMatcher.withDefaults();

        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(paths.matcher(HttpMethod.GET, "/orders/**"))
                .hasAuthority("ORDER_READ")
            .requestMatchers(paths.matcher(HttpMethod.GET, "/public/**"))
                .permitAll()
            .anyRequest()
                .denyAll()
        );

        return http.build();
    }
}
~~~

This is a **Spring configuration**, requiring corresponding Spring Boot/Spring Security dependencies and a properly designed authentication provider; it does not compile standalone with `javac` without Spring libraries. It assumes `DispatcherServlet` is at the default `/` mapping, with no special servlet prefix and no gateway rewrite altering the request path.

With `server.servlet.context-path=/shop`, `GET /shop/orders/42` falls under the `/orders/**` rule if it passes earlier filters and `Authentication` has `ORDER_READ`. `GET /shop/public/info` falls under the public rule. Distinguish **matching the URL** from **being allowed to act on Order 42**: the rule only requires general read authority; the service must still verify owner/tenant on the actual record.

**Do not change the pattern to `/shop/orders/**` merely because Chrome displays `/shop`.** The context path is determined by deployment; the matcher intentionally strips it. You can deploy the same artifact under `/staging` instead of `/shop` while keeping the `/orders/**` pattern.

### When Do getRequestURI() and the Matched Path Differ?

According to the Servlet API, `getRequestURI()` contains the context path. If you write by hand:

~~~java
// DO NOT do this for Spring Security authorization:
boolean allowed = request.getRequestURI().startsWith("/orders/");
~~~

then `/shop/orders/42` fails to match even though the true path inside the application is `/orders/42`. A "fix" using `contains("/orders/")` is even worse: it can match unintended paths. Use a `RequestMatcher` with verified semantics rather than manual `requestURI` string checks as a security policy.

## 3. What Is Servlet Path? How Does It Differ from Context Path?

The **servlet path** describes the portion tied to the mapping of an `HttpServlet`, notably `DispatcherServlet` in a Spring MVC application. Two illustrative cases:

### Case A — DispatcherServlet Uses Default `/` Mapping

~~~text
Browser:       /shop/orders/42
contextPath:   /shop
servletPath:   /orders/42
pathInfo:      null
app path:      /orders/42
MVC mapping:   /orders/{id}
~~~

Here `PathPatternRequestMatcher.withDefaults().matcher("/orders/**")` works cleanly for the context-relative path. No separate `basePath` is needed.

### Case B — DispatcherServlet Is Mapped with Prefix `/mvc/*`

Suppose a Servlet is registered at `/mvc/*` to serve Spring MVC, while the application is deployed at context `/shop`:

~~~text
Browser:       /shop/mvc/orders/42
contextPath:   /shop
servletPath:   /mvc
pathInfo:      /orders/42
app path:      /mvc/orders/42
MVC mapping:   /orders/{id}  (inside DispatcherServlet)
~~~

When writing `PathPatternRequestMatcher`, **the `/shop` context is stripped**, but **the `/mvc` servlet prefix remains in the path to be matched**. Two equivalent approaches in the example:

~~~java
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;

// Using Spring Security 6.5+ with MVC-compatible parser/matcher:
PathPatternRequestMatcher.Builder builder =
        PathPatternRequestMatcher.withDefaults();

// Approach 1: write the full context-relative path
var fullPattern = builder.matcher("/mvc/orders/**");

// Approach 2: configure a shared prefix for a servlet
var servletPaths = builder.basePath("/mvc");
var relativePattern = servletPaths.matcher("/orders/**");
~~~

This is a **matcher-building snippet for an application with a servlet prefix**, not a standalone Java class and it does not register the Servlet itself. With `basePath("/mvc")`, `matcher("/orders/**")` corresponds to `/mvc/orders/**`. `basePath` is a **mechanism in the matcher builder to reuse a prefix**, not a property that changes where the application is deployed.

Do not confuse them:

- `/shop` = **context path**, omitted from `PathPatternRequestMatcher`.
- `/mvc` = **servlet mapping prefix**, must appear in the path checked by `PathPatternRequestMatcher`, directly or via `basePath`.
- `/orders/{id}` = **route inside Spring MVC**, usually declared relative to `DispatcherServlet`.

**Version/compatibility constraint:** In Spring Boot 3.5, the `spring.mvc.servlet.path` property for changing the DispatcherServlet path is noted in documentation as **incompatible with the default `PathPatternParser` strategy**. Thus, the `/mvc/*` prefix example here describes a **compatibly configured Servlet mapping**; do not blindly set `spring.mvc.servlet.path=/mvc` in a default Boot 3.5 project and assume Spring MVC and Security will work together. If a non-default servlet prefix is needed, verify the routing/matcher strategy, Servlet registration method, and exact version via integration tests.

## 4. Base Path: At Least Three Completely Different Meanings

The term "base path" is often used for things at different layers. Always state clearly which one you mean.

| Usage of base path | Example | Belongs to | Impact on matcher |
| --- | --- | --- | --- |
| Servlet **context path** | `server.servlet.context-path=/shop` | App deployment address in the Servlet container. | `PathPatternRequestMatcher` matching **excludes** it. |
| Servlet mapping path/prefix | `/mvc/*` | `DispatcherServlet` registration. | The `/mvc` prefix **is included** in `PathPatternRequestMatcher` path matching. |
| `PathPatternRequestMatcher.Builder.basePath` | `.basePath("/mvc")` | Configuration of the **matcher builder** only. | Builds matchers with a shared prefix; does not alter the app's URL. |
| API-level prefix in controller | `@RequestMapping("/api/v1")` | How Spring MVC routes endpoints. | Part of the **in-app** route; usually must appear in the pattern. |
| Reverse proxy/gateway external prefix | `/edge` | Routing layer in front of the Java app. | Affects in-app requests **only if the proxy passes the prefix to the app or forwarded-header processing alters the request wrapper**. |
| WebFlux base path | `spring.webflux.base-path` | Spring WebFlux/reactive stack. | Not a Spring MVC Servlet context/servlet path; does not apply directly to `HttpServletRequest`. |

For example, with context path `/shop`, default servlet, and controller route `/api/v1/orders`:

~~~text
External direct URL     /shop/api/v1/orders
Context path            /shop
App path                /api/v1/orders
Controller route        /api/v1/orders
PathPattern matcher     /api/v1/orders
~~~

If you change a controller route from `/api/v1` to `/api/v2`, you are changing an **endpoint prefix**, not the context path. Security policies using `/api/v1/**` must be updated, unlike changing the deployment context from `/shop` to `/portal`.

**Team/documentation naming rule:** use precise labels like "Servlet context path," "servlet mapping prefix," "API route prefix," "proxy external prefix," and "matcher builder basePath" instead of just saying "base path." This greatly reduces mistakes when moving from local to staging/production.

## 5. The Browser URL Is Not Necessarily the URI the Backend Sees

When a request passes through a reverse proxy, ingress, or API gateway, **the external URL is not necessarily `getRequestURI()` in Spring Boot**. Example:

~~~text
Browser:
  GET https://public.example/edge/shop/api/orders/42

Gateway:
  route /edge/... -> backend
  strip prefix /edge

Backend Servlet app:
  contextPath=/shop
  requestURI=/shop/api/orders/42
  request path relative to context=/api/orders/42

Spring Security PathPatternRequestMatcher:
  matcher("/api/orders/**")
~~~

In this hypothetical setup, `/edge/shop/api/orders/**` is **wrong** on the backend: it includes both the external prefix stripped by the proxy and the context path. What must be matched is the **address that reaches the Servlet container**, after configured and trusted transformations.

A different architecture might **not strip the prefix**, or rewrite upstream to `/api/orders/42` with context root `""`, or inject prefixes via forwarded headers. Then the path mapping differs: **there is no single universal formula from browser URL to matcher** without knowing how the proxy actually forwards requests.

### Forwarded Headers Complicate the Picture Further

Many reverse proxies send `Forwarded`, `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-Prefix`, or similar information. Spring Boot has the property:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

This setting allows the framework to process forwarded information in appropriate environments; how the wrapper modifies `scheme`, `host`, `contextPath`, or URL must be verified for your setup and version. **Never treat headers sent by arbitrary Internet clients as a source of truth about where a request came from.** Accept forwarded headers only when set by a trusted gateway/proxy, and strip/overwrite untrusted values at the network boundary.

When `ForwardedHeaderFilter` or equivalent handling is active, the request object seen by app layers can reflect applied forwarded info. Therefore, when debugging, log **request fields at the relevant position** and check the reverse proxy and ingress config, instead of guessing from a user's browser screenshot.

Never fix a production 403 by using `permitAll("/**")` or adding `/**` to a security matcher to "cover every prefix." That can accidentally expose admin endpoints when the real bug was merely a wrong path.

## 6. What Does RequestMatcher Actually Receive and Match?

At the interface level, `RequestMatcher` receives an `HttpServletRequest`. However, the **concrete matcher** decides which part of the request is used and how patterns are parsed. Examples:

| Matcher / mechanism | What to note |
| --- | --- |
| `PathPatternRequestMatcher` (Spring Security 6.5+, default in 7.x) | Path pattern **relative to context path**; `basePath` can be configured to include servlet prefix. Coordinates with compatible Spring MVC `PathPatternParser`. |
| `MvcRequestMatcher` (legacy, deprecated in 6.5) | Based on Spring MVC `HandlerMappingIntrospector`; pattern relative to **servlet path** in MVC context, may need `setServletPath` with multiple servlets or prefix mappings. |
| `AntPathRequestMatcher` (legacy, deprecated toward 7.x) | Uses Ant mechanism and its own semantics around `servletPath + pathInfo`; do not assume identical semantics to PathPattern matchers. |
| `RegexRequestMatcher` | Must verify exact input string, flags, and regex expression; watch out for anchors and encoded paths. |
| Custom `RequestMatcher` | Can inspect host, method, headers, query... but must be written safely and tested for edge cases. |

**Version note:** In Spring Security **6.x**, `.requestMatchers(String...)` may rely on a matcher chosen by the framework based on classpath/MVC setup or configuration. Moving to **Spring Security 7.x**, the migration guide explains the Java DSL switches to `PathPatternRequestMatcher` and expects context-relative paths (including servlet prefix when needed). Therefore, when an old pattern suddenly "stops matching" after an upgrade, **do not just copy the same pattern string**; verify the actual matcher, servlet prefix policy, and test requests with real URIs.

For clarity in Spring Security 6.5+, you can pass an explicit `RequestMatcher` rather than relying on the auto-selection of the `String` overload:

~~~java
PathPatternRequestMatcher.Builder matcher =
        PathPatternRequestMatcher.withDefaults();

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(matcher.matcher("/api/orders/**"))
        .hasAuthority("ORDER_READ")
    .anyRequest().denyAll()
);
~~~

Corresponding Spring imports/config are required; this is a **fragment plugged into HttpSecurity**, not a standalone file. If MVC uses a custom parser, ensure the PathPattern matcher aligns with the parsing rules used by the handler mapping; do not mix incompatible parsers and assume two routing layers share identical semantics.

### Why Not Use Hand-Written String Comparisons?

A policy like:

~~~java
// DO NOT use to protect endpoints:
boolean isAdmin = request.getRequestURI().startsWith("/admin");
~~~

not only gets confused by context paths, but also mis-matches `/administrator` or `/admin-other` by ignoring segment boundaries. Cases like `%2F`, `%2e`, repeated slashes `//`, `;` (matrix/path parameters), URL-encoded Unicode, or Servlet container path normalization can create further discrepancies between request reception, MVC routing, and security matchers.

**Recommendation:** use `PathPatternRequestMatcher` or a framework-compatible matcher; keep `StrictHttpFirewall`/Spring Security's firewall enabled and never loosen encoded-slash/semicolon checks just to make one URL work; test unusual paths across the entire filter/handler chain. If normalizing at a proxy, verify alignment between proxy and app so a path is not treated as public by the gateway and private by the backend.

## 7. `securityMatcher` and `requestMatchers` Must Share the Same Path Picture

Spring Security has two levels of matching:

1. **`http.securityMatcher(...)`** determines which **SecurityFilterChain** owns the request. `FilterChainProxy` picks the first matching chain in order.
2. **`authorizeHttpRequests(...requestMatchers(...))`** determines which **authorization rule** applies within the chosen chain, also by first matching rule.

This matters even more than a 403 error: **if no SecurityFilterChain matches the actual path, the request may bypass Spring Security's security filters entirely**. `anyRequest().denyAll()` only blocks requests **already covered by that chain**.

Example for an app at context `/shop` and default servlet:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    PathPatternRequestMatcher.Builder paths =
            PathPatternRequestMatcher.withDefaults();
    http.securityMatcher(paths.matcher("/api/**"))
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(paths.matcher("/api/public/**")).permitAll()
            .requestMatchers(paths.matcher("/api/orders/**"))
                .hasAuthority("ORDER_READ")
            .anyRequest().denyAll());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .anyRequest().denyAll());
    return http.build();
}
~~~

This is a **code fragment inside a Spring `@Configuration` class** (needing imports for `@Bean`, `@Order`, `PathPatternRequestMatcher`, `SecurityFilterChain`, `HttpSecurity`), excluding login/token config or controllers. The two beans are an **alternative architectural setup** to the single-chain config above, not meant to be pasted together blindly without controlling matchers and `@Order`.

- `GET /shop/api/orders/42` → app path `/api/orders/42` → API chain, then `ORDER_READ` rule.
- `GET /shop/api/public/version` → API chain → public rule → allowed at HTTP layer.
- `GET /shop/web/home` → misses API chain, enters fallback chain → DENY.

If you **add `/shop` into `securityMatcher("/shop/api/**")`** when `/shop` is just the context path, the API chain may never be selected for intended requests. The fallback chain ensures **safe denial** instead of letting requests escape Spring Security completely, though users will still see 403/401 until the matcher policy is fixed.

When an app has a `/mvc` servlet prefix, update both the **chain matcher** and the **authorization rule matchers** so both interpret `/mvc/...` paths consistently via `PathPatternRequestMatcher`. Do not fix only one side. Mixing legacy `MvcRequestMatcher` on one side and `PathPatternRequestMatcher` on the other increases semantic drift, especially during upgrades.

## 8. Special Example: Coordinating Controller Path, Context Path, and Servlet Prefix

Suppose:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {
    @GetMapping("/{id}")
    String get(@PathVariable String id) {
        return "order " + id;
    }
}
~~~

This is a **Spring MVC snippet**, needing Spring Web imports and a real controller setup. `@RequestMapping("/orders")` does not by itself determine an absolute browser URL; the result also depends on deployment.

| Deployment | Browser URL path | Context-relative app path | Sensible PathPattern matcher |
| --- | --- | --- | --- |
| Root context, default servlet | `/orders/42` | `/orders/42` | `/orders/**` |
| Context `/shop`, default servlet | `/shop/orders/42` | `/orders/42` | `/orders/**` |
| Context `/shop`, servlet prefix `/mvc/*` | `/shop/mvc/orders/42` | `/mvc/orders/42` | `/mvc/orders/**` or `basePath("/mvc")` + `/orders/**` |
| External prefix `/edge` stripped by proxy, context `/shop` | `/edge/shop/orders/42` | Backend receives `/shop/orders/42` → app path `/orders/42` | `/orders/**` |
| Controller uses `@RequestMapping("/api/v1/orders")`, context `/shop` | `/shop/api/v1/orders/42` | `/api/v1/orders/42` | `/api/v1/orders/**` |

Each row assumes a compatible Servlet/gateway configuration. Simply having the proxy keep the prefix instead of stripping it, or applying `ForwardedHeaderFilter` with prefix info, can change observed values. **This table is a conceptual model**, not a substitute for testing real requests in a running environment.

### Practical Debugging: Print the Exact 4 Fields, Don't Guess

In a development environment you can place temporary logging in a Servlet `Filter` or controller to inspect:

~~~java
// Snippet inserted into Servlet/Spring MVC code with HttpServletRequest request:
System.out.println("requestURI = " + request.getRequestURI());
System.out.println("contextPath = " + request.getContextPath());
System.out.println("servletPath = " + request.getServletPath());
System.out.println("pathInfo = " + request.getPathInfo());
~~~

Do not log tokens, cookies, sensitive info, or full query strings indiscriminately. Logs inside a controller **only see requests that passed security filters**, so if a request is blocked before the controller, observe at a properly placed filter/trace or use Spring Security DEBUG logging in a safe environment. In systems with proxy/forwarded filters, note **at which position in the filter chain** you log so you know whether the path is raw container path or wrapper-updated values.

When verifying configuration, log both the external URL received by the proxy (at the gateway) and the upstream path forwarded by the proxy. Looking at only one of the two is not enough.

## 9. Standalone Java 17+ Example: Seeing the Path Components

The following program **does not use Spring and does not implement a real `RequestMatcher`**. It simulates three requests with known Servlet API fields, strips the context path, and checks a `/**` prefix **only for simple normalized sample paths**. It does not decode/normalize URLs, nor handle multiple mapping styles, firewalls, or encoded slashes. **Do not copy this demo function to replace Spring Security matchers in production.**

Save with the exact filename **`RequestPathComponentsDemo.java`**:

~~~java
public class RequestPathComponentsDemo {
    record Example(String requestUri, String contextPath,
                   String servletPath, String pathInfo) {
        String insideApplication() {
            if (!contextPath.isEmpty() && !requestUri.equals(contextPath)
                    && !requestUri.startsWith(contextPath + "/")) {
                throw new IllegalArgumentException("Invalid sample context");
            }
            return requestUri.substring(contextPath.length());
        }
    }

    static boolean matchesTrailingWildcard(String actual, String pattern) {
        if (!pattern.endsWith("/**")) {
            throw new IllegalArgumentException("Demo supports /** only");
        }
        String prefix = pattern.substring(0, pattern.length() - 3);
        return actual.equals(prefix) || actual.startsWith(prefix + "/");
    }

    public static void main(String[] args) {
        Example normal = new Example(
                "/shop/orders/42", "/shop", "/orders/42", null);
        Example prefixed = new Example(
                "/shop/mvc/orders/42", "/shop", "/mvc", "/orders/42");
        Example behindProxy = new Example(
                "/shop/api/orders/42", "/shop", "/api/orders/42", null);

        System.out.println("Default requestURI: " + normal.requestUri());
        System.out.println("Default contextPath: " + normal.contextPath());
        System.out.println("Default servletPath: " + normal.servletPath());
        System.out.println("Default pathInfo: " + normal.pathInfo());
        System.out.println("Default app path: " + normal.insideApplication());
        System.out.println("Default /orders/**: "
                + matchesTrailingWildcard(normal.insideApplication(), "/orders/**"));
        System.out.println("Incorrect /shop/orders/**: "
                + matchesTrailingWildcard(normal.insideApplication(), "/shop/orders/**"));
        System.out.println("Prefixed servletPath: " + prefixed.servletPath());
        System.out.println("Prefixed pathInfo: " + prefixed.pathInfo());
        System.out.println("Prefixed app path: " + prefixed.insideApplication());
        System.out.println("Prefixed /mvc/orders/**: "
                + matchesTrailingWildcard(prefixed.insideApplication(), "/mvc/orders/**"));
        System.out.println("Incorrect prefixed /orders/**: "
                + matchesTrailingWildcard(prefixed.insideApplication(), "/orders/**"));
        System.out.println("Proxy external path: /edge/shop/api/orders/42");
        System.out.println("Proxy backend requestURI: " + behindProxy.requestUri());
        System.out.println("Proxy backend app path: " + behindProxy.insideApplication());
    }
}
~~~

Compile and run on JDK 17 or newer:

~~~bash
javac --release 17 RequestPathComponentsDemo.java
java RequestPathComponentsDemo
~~~

Standard output:

~~~text
Default requestURI: /shop/orders/42
Default contextPath: /shop
Default servletPath: /orders/42
Default pathInfo: null
Default app path: /orders/42
Default /orders/**: true
Incorrect /shop/orders/**: false
Prefixed servletPath: /mvc
Prefixed pathInfo: /orders/42
Prefixed app path: /mvc/orders/42
Prefixed /mvc/orders/**: true
Incorrect prefixed /orders/**: false
Proxy external path: /edge/shop/api/orders/42
Proxy backend requestURI: /shop/api/orders/42
Proxy backend app path: /api/orders/42
~~~

**Takeaway:** the same business route `/orders/42` can have different `requestURI`s depending on context/servlet mappings. With context `/shop`, the context-relative pattern is `/orders/**`. When the `/mvc` servlet prefix is present, the path `PathPatternRequestMatcher` inspects is `/mvc/orders/42`. When the proxy strips `/edge`, the backend does not see `/edge` in the illustrated `requestURI`.

The demo's `matchesTrailingWildcard` check **only illustrates prefix matching on normalized strings**; it does not replace `PathPatternParser`, `HttpFirewall`, or Spring Security's `RequestMatcher`. The `javac`/`java` commands above run standalone on the JDK; the earlier `HttpSecurity` examples require a Spring project and dependencies.

## 10. Testing RequestMatcher with the Real Path, Not Just the Response

A `get("/orders/42")` test in a default local setup **does not prove** the system still authorizes properly when deployed under `/shop` or with `/mvc`. With `spring-security-test`, MockMvc can simulate `contextPath`:

~~~java
// Snippet in a Spring Boot + MockMvc integration test,
// assuming GET /orders/{id} controller exists and security chain is active.
mvc.perform(get("/shop/orders/42")
        .contextPath("/shop")
        .with(user("alice").authorities(
            new SimpleGrantedAuthority("ORDER_READ"))));
// If controller/data are valid, the request passes HTTP checks;
// still assert appropriate status/body/business authorization.
~~~

The test snippet needs Spring Security Test, MockMvc, static imports, and corresponding app configuration; it is not a standalone program. Rather than asserting only HTTP 200, design **DENY test cases** at the filter/service layer, and test headers/routes with accurate request fields.

Minimum test matrix:

| Scenario | Path seen by browser / app | Expectation |
| --- | --- | --- |
| Root context, default servlet | `/orders/42` / `/orders/42` | Rule `/orders/**` matches. |
| Context `/shop` | `/shop/orders/42` / `/orders/42` | Rule `/orders/**` matches; `/shop/orders/**` typically does not. |
| Context `/shop`, servlet `/mvc/*` | `/shop/mvc/orders/42` / `/mvc/orders/42` | PathPattern matcher with `/mvc` prefix matches. |
| Wrong servlet prefix | App path `/mvc/orders/42`, rule `/orders/**` | Fails to match PathPattern; requires right rule and DENY fallback. |
| Gateway strips `/edge` | External `/edge/shop/api/orders/42`, backend `/shop/api/orders/42` | Backend rule `/api/orders/**` matches. |
| Request with query | `/shop/orders/42?view=summary` | Path rule does not change because of query. |
| Different HTTP method | `POST /shop/orders/42` | `GET` rule does not grant permission to POST. |
| Similar false prefix | `/shop/orders-admin/42` | `/orders/**` rule must not match `/orders-admin/**`. |
| Encoded path, double slash, semicolon | Variants accepted or rejected by gateway/container | Must ensure consistent handling by matcher and MVC; test firewall/proxy. |
| No chain matches | Request enters no security chain | **Spring Security bypass risk**; needs an appropriate fallback chain. |
| Right path but missing `ORDER_READ` | `/shop/orders/42` | DENY at authorization. |
| Has `ORDER_READ` but different tenant | Same valid URL path | DENY at resource/service layer. |

A **chain selection** test is also essential when deploying multiple `SecurityFilterChain`s: having `anyRequest().denyAll()` in the fallback ensures stray routes are denied instead of slipping outside Spring Security. If a URL has no controller, 404 proves neither rule correctness nor failure; to distinguish them, add a test controller fixture or invoke the matcher directly with a `MockHttpServletRequest` populated with accurate `contextPath`, `servletPath`, and `pathInfo`.

### Tip: Testing a Matcher Directly with MockHttpServletRequest

In a unit test using `spring-test` and `spring-security-web` 6.5+, you can construct a mock request and invoke it directly:

~~~java
MockHttpServletRequest request =
        new MockHttpServletRequest("GET", "/shop/orders/42");
request.setContextPath("/shop");
request.setServletPath("/orders/42");

RequestMatcher matcher =
        PathPatternRequestMatcher.withDefaults()
                .matcher(HttpMethod.GET, "/orders/**");

boolean matched = matcher.matches(request);
// expected true with the illustrative request data and matcher
~~~

This is a **Spring-dependent test snippet** requiring imports for `MockHttpServletRequest` (`org.springframework.mock.web`), `RequestMatcher`, `PathPatternRequestMatcher`, and `HttpMethod`; it does not run with plain JDK. To test a servlet prefix, set URI `/shop/mvc/orders/42`, `setContextPath("/shop")`, `setServletPath("/mvc")`, `setPathInfo("/orders/42")`, and use `basePath("/mvc").matcher("/orders/**")`.

Direct matcher tests are great for ruling out path bugs, yet **not sufficient for the whole application**: you need integration tests for filter chains, MVC routing, authentication, proxy rewrites, and business data as needed.

## 11. Common Mistakes Across Different Deployment Environments

1. **Entering context path twice:** `server.servlet.context-path=/shop` and then using `PathPatternRequestMatcher("/shop/orders/**")`. → For PathPattern, write `/orders/**`.
2. **Forgetting servlet mapping prefix:** MVC actually at `/mvc/*`, yet PathPattern matcher is just `/orders/**`. → Use `basePath("/mvc")` or the full context-relative path `/mvc/orders/**`.
3. **Treating browser URL as backend `getRequestURI()`:** proxy strips/adds prefixes. → Compare request paths at gateway and backend, check forwarded headers.
4. **Confusing matcher `basePath` with `server.servlet.context-path`:** changing basePath neither changes the app URL nor creates a context path.
5. **Thinking `requestMatchers("/api/**")` configures whole-chain selection:** actually `securityMatcher` scopes the chain; rule matchers only live inside it.
6. **Omitting a fallback SecurityFilterChain:** paths matching no chain can bypass Spring Security. → Place a final chain covering all requests with a safe default.
7. **Using `getRequestURI().startsWith(...)` as security logic:** fails to strip context, mis-matches segment boundaries, and risks encoded-path issues. → Use verified matchers and an appropriate firewall.
8. **Relying on legacy `MvcRequestMatcher` while upgrading to Spring Security 7 untested:** servlet prefix semantics changed explicitly. → Migrate to PathPattern matchers and specify prefixes deliberately.
9. **Blindly setting `spring.mvc.servlet.path` in Boot 3.5 with default PathPatternParser:** has compatibility issues. → Check version docs, pick a compatible routing strategy, and run full-stack tests.
10. **Trusting `X-Forwarded-Prefix` sent directly by clients:** can trick the app about scheme/host/path. → Trust forwarded headers only from controlled proxies, stripping untrusted headers.
11. **Fixing 403 with `permitAll("/**")`:** removes the authorization layer instead of fixing the prefix/matcher. → Diagnose chain, request fields, and authorities.
12. **Testing only controller status in root context:** misses deployments with context/servlet prefixes, proxies, encoded paths, queries, and HTTP methods.
13. **Equating host/query with path matchers:** standard URL pattern matchers do not check hostname, port, or query; if policy depends on them, use appropriate matchers/logic.
14. **Forgetting resource conditions:** `ORDER_READ` only permits the action type; it does not verify which tenant Order 42 belongs to.

## 12. Checklist for Designing Policies in Prefix-Based Applications

Before merging a Spring Security configuration using URL matchers, answer with evidence:

1. **Which URL does the client call?** Record scheme, host, path, and query at the public entry point; do not treat query as path.
2. **How does the gateway forward the request?** Does it strip/add prefixes, rewrite paths, and are backend servlet context and forwarded headers trustworthy?
3. **What are the actual `getRequestURI`, `getContextPath`, `getServletPath`, and `getPathInfo`?** Log temporarily at the right place rather than guessing.
4. **Which Matcher implementation is in use?** `PathPatternRequestMatcher`, `MvcRequestMatcher`, Ant, Regex, or custom; which Spring Security version?
5. **Relative to which layer are patterns written?** For PathPattern, omit context path; include servlet prefix in the path or `basePath` if needed.
6. **Are there multiple SecurityFilterChains?** Which `securityMatcher` wins, what is `@Order`, and does a fallback cover unmatched requests?
7. **Within the chosen chain, which rule wins?** Specific `requestMatchers` first, methods controlled, `anyRequest` set to the right policy?
8. **If the URL is allowed, is the caller permitted to act on the record?** Owner/tenant/state policies in the service must be independent of path matching.
9. **Have you tested real deployment context/servlet/proxy setups?** At least one ALLOW case, one DENY case, one wrong-prefix case, and one fallback case.
10. **Are unusual paths handled consistently?** Encoded slashes, dots, double slashes, semicolons, proxy normalization, and HttpFirewall.

**Core takeaway:** *Context path* locates the application in the Servlet container; *servlet path* reflects how requests reach the Servlet; `PathPatternRequestMatcher.Builder`'s *basePath* is only a helper to define matcher prefixes; the *actual address being matched* is the path seen by the concrete request matcher **after appropriate runtime transformations**, which is not necessarily the browser URL. With `PathPatternRequestMatcher`, **omit the context path, account for any servlet prefix, and verify rules on real requests**. Only the right path matcher ensures the rule applies; enforcing resource-level permissions remains the service's additional responsibility.

### Official Documentation

- [Spring Security 6.5 — Migration: servlet path prefix and PathPatternRequestMatcher](https://docs.spring.io/spring-security/reference/6.5/migration-7/web.html)
- [Spring Security — Authorize HttpServletRequests and RequestMatcher](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — PathPatternRequestMatcher API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/servlet/util/matcher/PathPatternRequestMatcher.html)
- [Spring Framework — MVC Path Matching and Servlet API](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/handlermapping-path.html)
- [Spring Boot 3.5 — Common Application Properties: servlet context/servlet path/forward headers](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
