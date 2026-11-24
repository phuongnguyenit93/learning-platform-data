# RequestMatcher and Request Information Used for Matching

## 1. The Big Picture: What Question Does RequestMatcher Answer?

In Servlet-based Spring Security, every incoming HTTP request carries information such as the **HTTP method**, **path**, **servlet path**, **query string**, **headers**, **dispatcher type**, and many other attributes. The system needs to know which security filter chain a request belongs to, and which authorization rule applies within that chain. The key component that decides **whether a request satisfies a selection condition** is `RequestMatcher`.

The core idea is simple:

> RequestMatcher inspects an `HttpServletRequest` and answers whether the request matches the described condition. A match result is **not** a decision that the user is allowed to perform the action.

Examples:

- `GET /api/documents/42` matches the "GET on the document retrieval path" matcher.
- `DELETE /api/documents/42` does not match a GET-only matcher.
- A request matching the "GET document" matcher still needs `document:read` and an object-level policy for the actual document before data is returned.
- A self-sent header `X-Role: ADMIN` can be seen on the request, but it **does not prove** the caller has the admin role.

Illustrative flow:

```text
HTTP REQUEST
  method, URI/path, contextPath, servletPath, pathInfo,
  query, headers, dispatcherType, ...
                |
                v
         FilterChainProxy
         selects the first SecurityFilterChain
         with a matching RequestMatcher
                |
                v
         AuthorizationFilter
         selects authorization rule by
         requestMatchers(...) inside the chain
                |
                v
         AuthorizationManager
         reads Authentication if needed
         and decides ALLOW / DENY
                |
                v
         Service / Data policy
         tenant, owner, status, ...
```

**Distinguishing three different decisions**:

1. **Match:** Which criteria does this request satisfy? (`RequestMatcher`).
2. **Authorization:** Does the caller have permission for the selected action? (`AuthorizationManager` and policy).
3. **Object authorization:** Is the caller allowed to operate on the **specific** record/resource? (tenant, owner, status, sharing relationship conditions).

Keeping this separation clear helps avoid mistakes like "right URL means authorized" or "authenticated means allowed to read any ID."

## 2. The `RequestMatcher` API and What It Does Not Do

In Servlet Spring Security, the `org.springframework.security.web.util.matcher.RequestMatcher` interface accepts a `jakarta.servlet.http.HttpServletRequest` for matching.

The core signature is:

```java
boolean matches(HttpServletRequest request);
```

A matcher may examine one or more attributes of the request. It can be a built-in matcher for URL/path/method, a matcher based on conditional expressions, or a custom matcher. Some APIs also return a match result along with path variables; how that information is retrieved depends on the specific interface and Spring Security version.

**RequestMatcher does not by itself:**

- Authenticate passwords, login sessions, or JWTs.
- Check `GrantedAuthority` unless you intentionally write inappropriate logic into the matcher.
- Guarantee that a resource ID belongs to the currently authenticated tenant.
- Protect every endpoint merely because it appears in a single configuration line.
- Guarantee that all filter chains are executed sequentially.

Standard policy should let matchers determine **what kind of request it is**, and let managers/services handle **who has what permission**.

### 2.1. Table of Information Types from `HttpServletRequest`

| Information | Common API | What can it match? | Notes |
| --- | --- | --- | --- |
| HTTP method | `getMethod()` | GET, POST, PATCH, DELETE | Method names are case-sensitive per the protocol; configuration must be exact |
| Request URI | `getRequestURI()` | Request path inside the server | Usually includes context path, excludes query; do not use directly in place of every path matcher |
| Context path | `getContextPath()` | Prefix where the application is deployed | Can differ between local and production |
| Servlet path | `getServletPath()` | Portion of the path mapped to the servlet | Depends on servlet mapping |
| Path info | `getPathInfo()` | Remaining path after servlet path, if any | Can be `null` |
| Query string | `getQueryString()` | Data after the question mark in the URL | Not the path; raw string may need encoding handling |
| Parameter | `getParameter(...)` | Query or form fields parsed by the servlet | Does not read JSON fields by default |
| Request header | `getHeader(...)` | Content negotiation, API version... | Clients can arbitrarily set many headers |
| Content type | `getContentType()` | Payload type | Not proof of identity or permission |
| Dispatcher type | `getDispatcherType()` | REQUEST, FORWARD, ERROR, ASYNC... | Affects subsequent dispatches and policy |
| Host/scheme | `getServerName()`, `getScheme()` | Selecting domain/HTTPS when needed | Can be affected by proxies/forwarded headers |
| Remote address | `getRemoteAddr()` | Network-based control within appropriate scope | Often the proxy's IP, not user identity |
| Principal | `getUserPrincipal()`, Spring `Authentication` | Server-authenticated identity | Do not confuse with username from query/header |

There is no general rule saying "RequestMatcher always uses all of these fields." **A matcher only inspects the attributes defined by its implementation**. A typical path matcher does not treat `?role=ADMIN` as a permission; a method matcher does not inspect the body on its own.

### 2.2. Three Path Parts to Distinguish

Suppose the application runs under context path `/portal`; the application's servlet receives the request `GET /portal/api/documents/42?expand=true`.

We can view it as:

```text
HTTP method       GET
Request URI       /portal/api/documents/42
Context path      /portal
Query string      expand=true
Application path  /api/documents/42
```

The exact values of `servletPath` and `pathInfo` depend on the servlet mapping. With a typical Spring MVC mapping, the servlet path may be `/api/documents/42` and path info null; when the servlet is mapped under a different prefix, they may be split differently.

**Do not arbitrarily strip string prefixes** and use that as a security boundary. Built-in matchers know how to handle paths according to their semantics, whereas manual string matching code must account for context path, servlet path, URL encoding, trailing slashes, and path normalization.

### 2.3. Path and Query Are Two Different Types of Data

`GET /api/documents/42?download=true` still has the **same path** as `GET /api/documents/42`. If a matcher only checks path and method, these two requests usually produce the same match result.

If the `download=true` parameter changes the business behavior to **data export or sensitive file download**, do not place the entire security responsibility on a generic path matcher and assume the query is checked automatically. You may need a dedicated endpoint/HTTP method, a `RequestMatcher` with carefully designed parameter conditions, or additional business policy. When the action changes substantively, a separate route such as `GET /api/documents/42/download` is usually easier to verify.

Never use a `?admin=true` parameter, an `X-Role` header, or any client-supplied field as proof of granted authorization.

## 3. Types of RequestMatcher and How to Choose

Spring Security provides multiple approaches. Available API names and usage recommendations vary by version; consult the documentation for your Spring Security version, especially when migrating from legacy matchers to newer path patterns.

| Approach | Use when | What to check |
| --- | --- | --- |
| `requestMatchers(HttpMethod, "...")` in the DSL | Matching HTTP method and path using the mechanism configured by the framework | Correct method, path, servlet mapping, and order |
| Spring MVC-based matcher | Wanting matching compatible with Spring MVC routing | `HandlerMappingIntrospector` and servlet path when multiple servlets exist |
| PathPattern-based matcher | Wanting to use Spring's path pattern syntax | Parser/path base configuration and framework version |
| Ant-style pattern matcher | Legacy projects or compatibility requirements | Wildcard semantics, deprecation/version |
| `RegexRequestMatcher` | Needing a specific regular expression | Overly broad regex, anchoring, and encoding |
| Custom matcher | Special request conditions not available out of the box | Do not create a bypass via client-controlled headers/query |
| Composite matchers (AND, OR, NOT) | Selection based on multiple criteria | Correct grouping, negation, and scope |

For new project code, prefer the **simple DSL and the matcher recommended for the current version**; do not blindly copy class names from tutorials for older versions. In Spring Security 6.x releases, the matcher family related to MVC/Ant/PathPattern has undergone changes and transitions. The important question is not just "what class is this?", but **how does it interpret paths, servlet path, method, and encoded paths in your specific application?**

### 3.1. Common Pattern Forms

Examples of intent (actual wildcard semantics must be verified per matcher type):

```text
/api/documents          -> collection endpoint
/api/documents/*        -> typically intended for one sub-segment like /42
/api/documents/**       -> typically intended for any number of sub-segments
/api/admin/**           -> group of admin endpoints
/public/**              -> content allowed to be public
```

Do not assume `*`, `**`, and `{id}` behave identically across every matcher type. Spring MVC `PathPattern` has specific rules on where `**` can appear; regex has an entirely different syntax. Do not use an overly broad wildcard just because it "passes the first test."

### 3.2. Spring MVC and Multiple Servlets

In a Spring MVC project, you can use a matcher compatible with MVC mappings; when there are multiple servlets or a servlet mapped under a dedicated prefix, you must specify the **servlet path** or choose the appropriate matcher type. The path shown in the browser alone does not tell you which matcher will apply.

An application might have a main servlet at `/`, a secondary servlet at `/legacy/*`, and another DispatcherServlet at a different prefix. The same string `/api/**` can be interpreted differently if matcher construction and servlet mapping are inconsistent. Test with requests through a real server or `MockMvc` configured closely to the application.

### 3.3. Custom Matchers: What Conditions Are Appropriate?

You can define a custom matcher when you need to classify requests by method, a version header, or a specific request attribute:

```java
import org.springframework.security.web.util.matcher.RequestMatcher;

RequestMatcher clientRequestsV2 =
    request -> "v2".equals(request.getHeader("X-Api-Version"));
```

This snippet **only checks the header**. It does not validate the header, does not guarantee which API the request belongs to, and does not grant permission. If used to select a route requiring a separate policy, the non-matching branch must have a safe fallback; never interpret `X-Api-Version: v2` as a role or authority.

Custom matchers involving paths should be especially careful with context path, servlet path, encoding normalization, special characters, and potential discrepancies between the security filter and the actual router. If a suitable built-in path matcher is available, use it instead of manually assembling `getRequestURI()` and doing string checks.

### 3.4. Do Not Confuse a Matcher with Permission Checks

Example:

```text
M = request has method DELETE, path /api/documents/42
A = principal has authority document:delete
O = principal is allowed to delete document 42 in the current tenant

ALLOW = M AND A AND O
```

Here, M helps **select the policy**. M provides no information that A or O holds. Nor does a request "matching DELETE" mean it has passed CSRF or has been authenticated.

## 4. Two Places Matchers Are Used in Spring Security Have Different Meanings

### 4.1. `securityMatcher` Selects the Scope of an Entire SecurityFilterChain

A Servlet application can declare multiple `SecurityFilterChain` beans. `FilterChainProxy` selects the **first matching chain** in order. Once a chain is selected, subsequent chains are not executed sequentially to "add extra layers of protection."

For example, if a chain only matches `/api/**`, a request to `/admin/export` will not enter that chain. An `anyRequest().denyAll()` **inside the API chain** does not protect `/admin/export`. You need a fallback chain or an appropriate coverage design.

### 4.2. `requestMatchers` Selects Authorization Rules Within the Chosen Chain

Inside `authorizeHttpRequests`, matchers are generally evaluated **in declaration order**, and the **first matching** rule is used. If a broad rule is placed before a narrow rule, the narrow rule may never run:

```text
Dangerous:
  /api/**            -> authenticated
  /api/admin/**      -> hasRole("ADMIN")

Safer:
  /api/admin/**      -> hasRole("ADMIN")
  /api/reports/**    -> appropriate permission
  anyRequest         -> denyAll
```

An authenticated user is not automatically allowed to call administrative endpoints. You must test cases where narrow and broad rules overlap.

### 4.3. Spring Security 6 Servlet Example

This is an **integration configuration**, not a standalone compilable Java program. Assume the application has already configured an appropriate authentication mechanism and authorities are provided by a verified server/IdP.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class DocumentHttpSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http.securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/admin/**")
                    .hasAuthority("admin:read")
                .requestMatchers(HttpMethod.GET, "/api/documents/*")
                    .hasAuthority("document:read")
                .requestMatchers(HttpMethod.POST, "/api/documents")
                    .hasAuthority("document:create")
                .requestMatchers(HttpMethod.DELETE, "/api/documents/*")
                    .hasAuthority("document:delete")
                .anyRequest().denyAll()
            );
        return http.build();
    }

    @Bean
    SecurityFilterChain fallbackChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/public/ping")
                .permitAll()
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
```

Meaning:

1. `@Order(1)` prioritizes evaluating the API chain first. `securityMatcher("/api/**")` scopes the entire chain to handle only requests matching the API prefix.
2. Once a request enters the API chain, subsequent classification rules are based on **HTTP method and path**.
3. `GET /api/documents/42` requires `document:read`; `DELETE /api/documents/42` requires `document:delete`. GET and DELETE must not be treated as having the same permission level merely because the path is the same.
4. `GET /api/admin/users` requires `admin:read`; other unlisted admin actions remain denied.
5. Requests that do not enter the API chain still hit the fallback chain, which only permits one defined public endpoint.
6. The configuration does not yet show JWT/form login, CSRF, CORS, or error entry points; these must be configured according to the real application architecture.

Especially for applications using cookies/sessions, **CSRF** is a separate protection layer for state-changing requests. Do not disable CSRF just to make POST/DELETE tests pass.

### 4.4. A Non-Matching Matcher Does Not Mean the Request Is Allowed

Suppose `GET /api/documents/42` matches the GET rule and is checked for `document:read`. If changed to `PUT /api/documents/42`, the GET rule does not match. If the chain ends with `denyAll`, PUT is blocked. If instead it ends with `anyRequest().authenticated()`, any logged-in user might accidentally be allowed through on PUT even without an update policy.

Therefore, two questions must be tested independently: **which route matches?** and **how are non-matching routes handled?**

## 5. Standalone Java 17: Experimenting with Matching Method, Path, Context Path, and Query

To clearly see which fields affect the outcome, let's first use plain Java. This example **simulates a custom matcher for this lesson** and does not replicate every detail of Spring Security's built-in matchers.

Save the entire program as `RequestMatchingDemo.java`:

```java
import java.util.Map;
import java.util.regex.Pattern;

public class RequestMatchingDemo {
    private static final Pattern DOCUMENT_DETAIL =
        Pattern.compile("/api/documents/[0-9]+");

    record DemoRequest(
        String method,
        String contextPath,
        String servletPath,
        String pathInfo,
        String queryString,
        Map<String, String> headers
    ) {}

    static boolean matchesGetDocument(DemoRequest request) {
        if (request == null || !"GET".equals(request.method())
                || request.servletPath() == null) {
            return false;
        }

        // Simulation convention: match servletPath + pathInfo.
        // Do not include contextPath, queryString, or headers.
        String path = request.servletPath()
            + (request.pathInfo() == null ? "" : request.pathInfo());

        return DOCUMENT_DETAIL.matcher(path).matches();
    }

    static DemoRequest of(String method, String servletPath) {
        return new DemoRequest(
            method, "", servletPath, null, null, Map.of()
        );
    }

    static void show(String name, DemoRequest request) {
        System.out.println(name + ": " + matchesGetDocument(request));
    }

    public static void main(String[] args) {
        show("get document 42",
            of("GET", "/api/documents/42"));

        show("post same path",
            of("POST", "/api/documents/42"));

        show("non numeric id",
            of("GET", "/api/documents/abc"));

        show("query does not change path",
            new DemoRequest(
                "GET", "", "/api/documents/42", null,
                "role=ADMIN", Map.of()
            ));

        show("context path separate",
            new DemoRequest(
                "GET", "/portal", "/api/documents/42", null,
                null, Map.of()
            ));

        show("path info appended",
            new DemoRequest(
                "GET", "/portal", "/api", "/documents/42",
                null, Map.of()
            ));

        show("header does not grant path match",
            new DemoRequest(
                "GET", "", "/api/documents/42", null,
                null, Map.of("X-Role", "ADMIN")
            ));

        show("trailing slash",
            of("GET", "/api/documents/42/"));

        show("different prefix",
            of("GET", "/private/documents/42"));

        show("missing request", null);
    }
}
```

Run commands on JDK 17+:

```bash
javac RequestMatchingDemo.java
java RequestMatchingDemo
```

Exact stdout output:

```text
get document 42: true
post same path: false
non numeric id: false
query does not change path: true
context path separate: true
path info appended: true
header does not grant path match: true
trailing slash: false
different prefix: false
missing request: false
```

**Explanation of each group:**

- `POST` does not match the GET rule even with the same URL.
- The demo regex only accepts numeric IDs and matches the full path; `/api/documents/abc` or a trailing `/` does not match.
- `?role=ADMIN` and the `X-Role` header are not used to alter the path match result: the client cannot grant permissions via those two fields. The line "header does not grant path match: true" means the **GET path already matched**; it does not mean the request was granted admin privileges.
- `contextPath=/portal` is not included in the path portion of this example, so deploying the app under a prefix does not change the simulated result.
- The `servletPath=/api`, `pathInfo=/documents/42` case demonstrates why both components need to be considered together under certain servlet mappings.

**Important limitation:** real matchers in Spring Security may apply different policies for path normalization, handling slashes, semicolons, URL encoding, and servlet mappings. The `Pattern.compile` example here is plain Java for building a mental model; **do not directly substitute it for framework-supported RequestMatchers**.

## 6. Choosing Request Information to Match: Right Intent, Right Trust Boundary

### 6.1. HTTP Method and Path: The Most Commonly Needed Pair

A single URI can handle multiple actions:

| Request | Common action | Example permission |
| --- | --- | --- |
| `GET /api/orders/123` | Read an order | `order:read` |
| `PATCH /api/orders/123` | Update certain fields | `order:update` |
| `DELETE /api/orders/123` | Delete/cancel order | `order:delete` |
| `POST /api/orders/123/approve` | Approve order | `order:approve` |

If a matcher only checks `/api/orders/**` and uses an overly broad `authenticated()`, any logged-in user could invoke cancel/approve operations even if they only have read access. Always check the method alongside the path when meanings and permissions differ.

HTTP HEAD, OPTIONS, and CORS preflight must be evaluated according to application behavior. Do not assume `OPTIONS` is automatically allowed to perform arbitrary actions; preflight is part of the browser mechanism, not proof of authentication or business authorization.

### 6.2. Header, Query, Host, and IP: Only Trust What Is Proven

A matcher can inspect headers, host, or query parameters, but those are **request input data**. Clients can typically control many of these fields. Never conclude a user has permission just because of:

```text
X-Role: ADMIN
X-Tenant-Id: tenant-7
?isInternal=true
X-Forwarded-For: 10.0.0.1
```

If the system uses a reverse proxy/gateway, only trust headers controlled by the trusted proxy, with mechanisms to strip spoofed client-sent values and properly configured forwarded-header handling. Even an internal IP or valid host does not replace user authentication and resource authorization checks.

`Accept`, `Content-Type`, or a `format` parameter can be used to classify processing type, but **a sensitive export operation must still require a dedicated permission**. Also note that `getParameter(...)` parses query/form data; it is not a JSON body reader by default.

### 6.3. Be Careful with URL Normalization

Situations like `%2F` (encoded slash), `..`, semicolons, double slashes, UTF-8 sequences, path portions after servlet mapping, or proxy rewrites can cause **the security layer and the router to interpret paths differently** if configuration is inconsistent.

A classic risk is "security checks path A while the controller actually executes path B." Therefore:

1. Prefer matchers compatible with the framework's router and application version.
2. Do not manually decode URLs multiple times in a way that differs from the Servlet container.
3. Configure the firewall and routing deliberately; avoid relaxing unusual URL protections just to make a single test case pass.
4. Test along the real HTTP path including proxy, context path, and servlet mapping.
5. Sensitive permission decisions must be checked at the service/data layer even after the route has matched.

### 6.4. Multiple DispatcherTypes and Internal Forwards

A Servlet request can undergo different dispatch types, such as `REQUEST`, `FORWARD`, `ERROR`, or `ASYNC`. Spring Security has rules for handling these dispatches; exact handling depends on configuration and version.

For example, an application needing to render an error page or an internal view forward may run into issues if a security rule applies to secondary dispatches unexpectedly. You should not solve this by mechanically applying `permitAll()` to all dispatcher types.

If you truly need to allow specific internal dispatches, configure the corresponding matcher intentionally—for example configuring `dispatcherTypeMatchers(...)` per the documentation for your version—and verify through tests that **direct external requests** still cannot access sensitive functionality. An internal `FORWARD` does not absolve the target handler of its resource protection responsibilities.

## 7. Combining Matchers Conditionally: AND, OR, NOT

When a route must be selected by multiple attributes, we can express logical conditions:

```text
M1 = method is GET
M2 = path under /api/reports/**
M3 = header X-Api-Version equals v2

GET_V2_REPORT = M1 AND M2 AND M3
```

Matcher combinators corresponding to AND, OR, and NOT may exist in the Spring Security API depending on the version. However, **combining matchers only clarifies which requests are selected for policy evaluation**; it does not by itself guarantee that the selected branch's policy is tight enough.

### 7.1. Order Can Change the Outcome

Suppose a chain has these rules:

```text
Rule A: GET /api/reports/**              -> hasAuthority("report:read")
Rule B: GET /api/reports/export           -> hasAuthority("report:export")
```

If A comes before B and matcher A covers export, a user with only `report:read` can reach the export endpoint without going through the export rule (unless another gate exists). Reordering them:

```text
Rule B: GET /api/reports/export           -> hasAuthority("report:export")
Rule A: GET /api/reports/**              -> hasAuthority("report:read")
Other                                     -> denyAll
```

This is a very clear example of **the same request and the same principal producing different applied policies due to matcher order**. Tests must exercise both a user with only `report:read` and a user with `report:export`.

### 7.2. A Negated Matcher Is Not a Default-Deny Policy

If `NOT /public/**` is used to select a group of requests, check the exact remainder and whether any sensitive endpoints fall inside the negated set. Negation can easily create a broader match region than intended. Prefer explicit, positive path groups ending with a default deny.

### 7.3. Do Not Put User Permissions Inside a Custom RequestMatcher

A RequestMatcher that reads `Authentication` to decide whether to match a route easily mixes **request classification** with **authorization decisions**. This makes rule ordering unpredictable and hard to debug: if the matcher fails to match due to a missing permission, the request may fall through to another weaker rule.

Instead, separate them:

```text
RequestMatcher: method/path/query pattern determines which route
AuthorizationManager: Authentication, authority, functional policy
Service/repository: tenant, owner, status, actual data
```

If authorization depends on request attributes or resources, use an `AuthorizationManager` or business policy with trusted inputs; do not try to solve it by turning a matcher into a second authorization system.

## 8. Methodical Testing of RequestMatcher

### 8.1. Matrix of Match and Authorization Checks to Verify Separately

| Request | Expected matcher | Authorization decision after match |
| --- | --- | --- |
| `GET /api/documents/42` | GET document | Requires `document:read` |
| `POST /api/documents/42` | Not GET document | Another POST rule or default deny |
| `DELETE /api/documents/42` | DELETE document | Requires `document:delete` |
| `GET /api/documents/abc` | Depends on whether route pattern accepts string ID | Do not skip object check |
| `GET /api/documents/42?role=ADMIN` | Usually same GET path matcher | Do not grant admin via query |
| `GET /portal/api/documents/42` with context path /portal | Matches according to how matcher resolves app path | Still requires read permission |
| `GET /api/reports/export` | Export matcher must take precedence if sensitive | Requires `report:export` |
| `GET /api/documents/42/` | Depends on matcher/router slash semantics | Do not assume allowed |
| `PATCH /api/documents/42` | Does not match GET/DELETE | Dedicated update rule or deny |
| `GET /private/admin` outside API chain | Fallback/protective chain | Must not accidentally slip through |
| `FORWARD` to sensitive handler | Depends on dispatcher policy | Must not bypass functional/object permissions |
| Encoded URL or double slash | Depends on firewall/router | Handling must be consistent and safe |

Each row should have **two assertions**: which matcher the request selects, and whether the user is allowed or denied after the manager and business policy run. Never treat "matcher returns true" as a complete security test.

### 8.2. Unit Testing a RequestMatcher in Isolation

For custom or built-in matchers, you can use `MockHttpServletRequest` from Spring Test to construct a request with method, servlet path, context path, headers, query, and dispatcher type, then test `matches(...)`.

The following is **illustrative code inside a test with the Spring Test dependency**:

```java
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.util.matcher.RequestMatcher;

// requestMatcher is the matcher already created in the test.
MockHttpServletRequest request =
    new MockHttpServletRequest("GET", "/api/documents/42");

request.setContextPath("");
request.setServletPath("/api/documents/42");
request.addHeader("X-Role", "ADMIN");

boolean matched = requestMatcher.matches(request);
```

The `matched` outcome depends on the matcher supplied by the test. You cannot assert true/false for every matcher from this snippet; write assertions appropriate to the rule under test. `MockHttpServletRequest` is a testing utility, not a user authentication mechanism.

### 8.3. Integration Testing with MockMvc

With Spring MVC, `MockMvc` and `spring-security-test` help verify the `SecurityFilterChain`, matcher ordering, and authorization outcomes. Test helpers like `user(...)` or `jwt(...)` create a simulated context: they do not prove real JWT signatures or passwords are being verified.

Example body of **an integration test with MockMvc and controller already configured**:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// A user with only read permission must not pass the separate export rule:
mockMvc.perform(get("/api/reports/export")
        .with(user("reader").authorities(
            new SimpleGrantedAuthority("report:read"))))
    .andExpect(status().isForbidden());
```

This test is only valid if the export endpoint exists, the application configured the export rule before the broad report read rule, and no other mechanism masks the result. `SimpleGrantedAuthority` is `org.springframework.security.core.authority.SimpleGrantedAuthority`. This snippet is **not standalone** and requires a full application/test environment.

For POST/PATCH/DELETE, if CSRF is enabled, you must provide a valid CSRF token when testing **access permissions**; otherwise a 403 may come from CSRF rather than proving the matcher or authority was checked properly.

### 8.4. When Behind a Reverse Proxy and Context Path

Testing locally at `/api/**` is insufficient if production deploys at `/portal/api/**`, uses URL rewrites, or relies on forwarded headers. Run at least one test along the real HTTP path or an equivalent integration environment, observing:

- Actual `requestURI`, `contextPath`, `servletPath`, and `pathInfo`.
- Which matcher is selected in which chain.
- Which controller the router actually executes.
- The authorization decision and actual data returned.

Do not log raw tokens/cookies or sensitive data merely to debug matchers. Log request ID, method, normalized path template, rule code, and outcome, while controlling exposure of resource IDs/identifiers.

## 9. Common Configuration Mistakes and How to Fix Them

| Mistake | Why is it dangerous? | How to fix |
| --- | --- | --- |
| Using `securityMatcher("/api/**")` without a fallback | URLs outside API may bypass Spring Security | Cover all paths that need protection |
| High-priority chain matching `/**` too broadly | Downstream admin/API chains never run | Check `@Order` and matcher scope |
| Placing broad read matcher before sensitive export | Export receives weaker read permission | Place specific rules first |
| Matching only path, ignoring method | GET, DELETE use wrong permission | Match by HTTP method as well |
| Treating query string as part of path pattern | Tests and reality diverge | Distinguish path, query, and parameter |
| Stripping `getRequestURI()` manually instead of context path | Wrong match when deployed under a prefix | Use matchers suited to servlet mapping |
| Using group name or client header as permission | Client self-escalates privileges | Derive authentication and authority from verified sources |
| Assuming wildcards behave the same in MVC/Ant/regex | Routes drift or become overly broad | Test actual matcher syntax used |
| Allowing all `FORWARD`/`ERROR` unchecked | Can create paths outside policy | Design dispatcher policy intentionally |
| Testing 403 without CSRF | Misattributing the denial reason | Separate CSRF and authorization tests |
| Testing only `matches`, not permissions | Match is right but permission is wrong | Unit match + integration authorization |
| Protecting only URLs, not records | IDOR/BOLA | Enforce tenant/owner/state at service/data |
| Relaxing firewall for unusual encoded URLs | Security/router interpret path differently | Align path handling and test edge cases |
| Using `authenticated()` for sensitive routes | Any logged-in user can call them | Specific permission + default deny |

## 10. Workflow When Adding an Endpoint

1. **Define the action and permission:** e.g., `document:download` for downloading a file, not merely "authenticated user."
2. **Determine the request shape:** method, path, path variables, query, content type, servlet mapping, and production context path.
3. **Choose the chain:** which `SecurityFilterChain` does the request belong to, is there a fallback, and is there a broader chain ahead of it?
4. **Choose the matcher:** prefer path/method matchers compatible with MVC/router; use custom matchers only when additional conditions are truly needed.
5. **Set the right order:** narrow/sensitive routes before broad routes, deny the rest.
6. **Attach the authorization rule:** specific authority/role; `ROLE_`, `SCOPE_`, and permission conventions must be consistent.
7. **Check object policy:** load the actual document and verify tenant, owner, sharing, status, and other conditions.
8. **Test thoroughly:** with/without permission, different methods, tampered query/headers, context path, slashes/encoding, undeclared routes, and export/secondary endpoints.
9. **Observe after deployment:** if new 401/403 errors appear, diagnose whether it is authentication, matcher, CSRF, permission, or object policy—never immediately switch to `permitAll()`.
10. **Review during upgrades:** matcher implementations or pattern parsers may change; tests should catch significant path differences.

## 11. Self-Check Questions

1. **What does `RequestMatcher` check?** Whether an `HttpServletRequest` satisfies a selection condition; matching itself is not authorization.
2. **Why should GET and DELETE on the same URI have separate rules?** They are two actions with different risks and required permissions.
3. **Does `?role=ADMIN` turn a GET path matcher into admin privilege?** No. Query data is client-controlled input, not an authority.
4. **What is the difference between `securityMatcher` and `requestMatchers`?** The first selects the scope of the entire chain; the second selects authorization rules inside the chosen chain.
5. **What if two SecurityFilterChains match the same request?** The first matching chain in order is used; other chains do not run cumulatively.
6. **Does `anyRequest().denyAll()` in an API chain protect all non-API URLs?** No. Appropriate chains must cover them.
7. **Why do servlet path and context path matter?** Because the path shown in the browser and the path used by the matcher may differ depending on deployment and servlet mapping.
8. **Should the `X-Role` header be used as an authorization condition?** No; users can send forged headers unless a trusted authentication mechanism establishes authorities on the server.
9. **Why can matcher order cause security bugs?** A broad rule before a narrow rule can shadow sensitive conditions.
10. **Why are matcher unit tests alone insufficient?** They do not prove authentication, authorities, object policies, and side effects have been handled.
11. **When should you use a custom matcher?** When selection depends on request attributes that built-in matchers cannot express, and the trusted data boundary is understood.
12. **When a request matches `/api/documents/42` and the user has `document:read`, are they guaranteed to read it?** No; the service must still check owner, tenant, status, and object-level permissions.

**Remember:** `RequestMatcher` helps Spring Security **choose the right processing path and the right rule** based on HTTP request information. Real security comes from **knowing exactly what information is being matched**, **the order and scope of matchers**, **never turning client data into authorities**, and **continuing to evaluate permissions on the actual resource after the matcher has matched**.

### Official References

- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Java Configuration and Multiple HttpSecurity](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security – Servlet Architecture and FilterChainProxy](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security – RequestMatcher API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/util/matcher/RequestMatcher.html)