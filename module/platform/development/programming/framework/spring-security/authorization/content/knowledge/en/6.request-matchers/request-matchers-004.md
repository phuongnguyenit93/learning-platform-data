# Path Variables, Wildcards, and Semantic Differences Across Matcher Types

**`RequestMatcher`** in Spring Security Servlet answers the question: *"Does the current HTTP request satisfy this match condition?"* It may inspect the path, HTTP method, or other criteria depending on the implementation. For path-based matchers, symbols like **`*`**, **`**`**, **`?`**, and **`{id}`** look similar across frameworks, but **not every matcher type interprets them the same way**.

For example, `/api/documents/{documentId}` can match a specific document and **extract** `documentId=42`. Meanwhile, `/api/documents/**` covers multiple sub-paths but typically **does not produce a named variable**. The regex `/api/documents/[0-9]+` constrains the ID to digits using *regular expression* syntax rather than `{documentId}` template syntax.

**Lesson objectives:**

1. Distinguish **segment**, **path variable**, **single-segment wildcard**, **multi-segment wildcard**, and **regex**.
2. Understand the scope, semantics, and version changes of **`PathPatternRequestMatcher`**, **`MvcRequestMatcher`**, **`AntPathRequestMatcher`**, **`RegexRequestMatcher`**, and custom matchers.
3. Know how to extract path variables for **resource-level authorization**, not merely URL matching.
4. Write and test rules to prevent unintended access caused by overly broad `/**`, query strings, servlet prefixes, or parser differences.

Primary context: **Spring Security 6.5.x, Spring MVC/Servlet, and Java 17+**. The lesson also highlights the direction of change in Spring Security 7; do not assume every project uses the same default implementation.

## 1. What Is RequestMatcher, and at Which Layer Does It Match?

The `org.springframework.security.web.util.matcher.RequestMatcher` interface accepts an `HttpServletRequest` and evaluates a match condition. Two notable operations:

```java
boolean matches(HttpServletRequest request);

RequestMatcher.MatchResult matcher(HttpServletRequest request);
```

- `matches(...)` returns a boolean: whether the request matches or not.
- `matcher(...)` can return a **`MatchResult`** containing match status and a **map of extracted variables**, if the implementation supports extraction. Do not assume every matcher exposes variables.
- A matcher only determines **whether the request belongs to the described set**; it **does not grant permissions itself**. Permissions are evaluated by the corresponding `AuthorizationManager`.

Matchers appear at **two levels**:

```java
http.securityMatcher("/api/**"); // Selects the SecurityFilterChain.

http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/documents/{documentId}")
        .hasAuthority("documents.read")
    .anyRequest().denyAll()
); // Selects the authorization rule inside the chain.
```

`securityMatcher` restricts which requests enter the **entire chain**; `requestMatchers` inside `authorizeHttpRequests` selects the **rule** within the chosen chain. A path matcher with the same pattern can be used in both places, but with different impact.

When there are multiple `SecurityFilterChain`s, `FilterChainProxy` selects the **first matching chain**. Inside a chain using `RequestMatcherDelegatingAuthorizationManager`, the **first matching** rule is applied; if that rule denies access, subsequent rules are not tried to find an easier permission.

## 2. Foundation: A URL Path Consists of Segments

Consider the request:

```text
GET /api/teams/alpha/documents/42?include=history
```

The **path** portion is `/api/teams/alpha/documents/42`. Slashes `/` separate **segments**:

```text
api | teams | alpha | documents | 42
```

The query string is `include=history`, **not a segment** of the path. Things commonly needing distinction:

- `/api/teams/alpha/documents/42`: path by segments.
- `/api/teams/alpha/documents/42?include=history`: URL with query; path-only matchers usually **do not** include the query in matching.
- `/api/teams/alpha/documents/42/comments/3`: more segments.
- `/api/teams/alpha/documents/42/`: trailing `/`; depending on parser/config, this may differ from without one.
- `/api/teams/Alpha/documents/42`: different letter case; many matchers are case-sensitive by default.
- `/api/teams/alpha/documents/a%2Fb`: contains percent-encoded characters; check **at which layer the path is decoded and split into segments**.

The path visible in the browser does not always match `servletPath`, `pathInfo`, or the path parsed by Spring MVC. **Context path** (e.g., deploying at `/portal`) and **servlet mapping** (e.g., `/mvc/*`) are two distinct factors; check the specific implementation.

## 3. PathPattern Syntax: Literals, `?`, `*`, `**`, and Named Variables

Spring Framework uses `PathPattern` for segment-based path matching; `PathPatternRequestMatcher` uses this mechanism in Spring Security 6.5+. Basic patterns:

| Pattern | PathPattern meaning | Matching examples | Non-matching examples |
| --- | --- | --- | --- |
| `/api/orders` | Literal, fixed path | `/api/orders` | `/api/orders/42` |
| `/api/orders/{orderId}` | Single segment, also captures `orderId` variable | `/api/orders/42` → `orderId=42` | `/api/orders/42/items` |
| `/files/*` | Any content within **one existing segment** | `/files/a.txt` | `/files/a/b.txt` |
| `/files/??.txt` | Two characters at `??` within **one segment** | `/files/ab.txt` | `/files/abcd.txt` |
| `/files/*.csv` | A filename ending in `.csv` within one segment | `/files/report.csv` | `/files/archive/report.csv` |
| `/api/orders/**` | Zero or more **segments at the end of the path** | `/api/orders`, `/api/orders/42/items` | `/api/users` |
| `/api/orders/{orderId:[0-9]+}` | One segment with regex value constraint and variable extraction | `/api/orders/42` | `/api/orders/abc` |
| `/files/{*filePath}` | Captures the **rest of the path** into a named variable | `/files/a/b.txt` → `filePath=/a/b.txt` | `/users/a/b.txt` |

These examples describe standard **PathPattern** semantics. When considering encoded paths, trailing slashes, servlet prefixes, or empty variables, do not turn this table into a guarantee for a matcher whose parser/config has not been verified.

### 3.1. `*` Is a Single-Segment Wildcard and Does Not Cross Slashes

`/projects/*/tasks` can match `/projects/alpha/tasks`. It **does not match** `/projects/alpha/team/tasks`, because `*` covers only the single segment between `projects` and `tasks`. A segment containing `*` generally **does not represent the absence of that segment**: `/projects/*/tasks` does not automatically match `/projects/tasks`.

A common misconception is using `*` and believing all directory levels are covered; in practice you must distinguish `*` and `**`. In security rules, the broader the wildcard, the more important it is to test negative paths.

### 3.2. `?` Matches Exactly One Character Within a Segment

With `/files/doc?.pdf`, `doc1.pdf` can match while `doc12.pdf` does not. `?` in **PathPattern** is a *single-character* wildcard; **`?` in an actual URL** after the path typically starts the **query string**. Do not conflate the two contexts.

In `/api/orders/42?include=history`, `?` is the **query delimiter**, not a wildcard character in path data. A path matcher typically inspects `/api/orders/42`; if permission depends on `include=history`, inspect the query separately via appropriate logic.

### 3.3. `**` Matches Multiple Segments, but PathPattern Restricts Placement

`/reports/**` covers `/reports`, `/reports/2026`, and `/reports/2026/11/export.csv`. In `PathPattern`, `**` **is only allowed at the end of a pattern** (similar to the catch-all variable `{*path}`). Examples:

```text
Valid in PathPattern:
  /reports/**
  /reports/{*remaining}
  /teams/{teamId}/documents/{documentId}

Invalid in PathPattern:
  /reports/**/export
  /**/admin/**
  /files/{*path}/download
```

The reason is that `PathPattern` avoids ambiguous multi-branch patterns like mid-path `**`; parsing rules are well-defined. **Some legacy Ant patterns allowed `**` in the middle**, so code that worked with `AntPathRequestMatcher` may **fail to parse** or change meaning after switching to `PathPatternRequestMatcher`.

If you need to match a route with an intermediate structure, design concrete URLs, split into several patterns, or use `RegexRequestMatcher`/custom matchers carefully instead of trying to "bring the Ant pattern as-is into PathPattern."

### 3.4. `{id}` Both Matches and Extracts

`/orders/{orderId}` describes **one required segment** and produces `orderId=42` from `/orders/42`. It **does not verify that the user is allowed to view order 42**. To make an authorization decision, you must combine the principal, extracted ID, resource metadata/tenant, and business policy.

If you want to match only numeric IDs at the matching step, `/orders/{orderId:[0-9]+}` uses regex **inside the segment**. However, regex does not replace data validation and authorization: `42` is syntactically valid, yet the user may still be forbidden from viewing that order.

### 3.5. `{*rest}` Differs from `**` by Capturing the Value

Two patterns can cover the tail of a path:

```text
/files/**          -> matches the rest, no automatic variable named "rest"
/files/{*rest}     -> matches the rest and captures the "rest" value
```

With `/files/2026/report.csv`, `{*rest}` can extract `rest=/2026/report.csv` (including the leading slash). Do not use this value as an unvalidated OS file path; restrict to a root directory, normalize paths, and prevent path traversal.

## 4. Four Common Matcher Types: Same RequestMatcher, Different Semantics

### 4.1. `PathPatternRequestMatcher` – The New Segment-Based Choice

**`org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher`** was introduced in Spring Security 6.5, using Spring Framework's `PathPattern`. It takes patterns relative to the **context path** and provides a builder supporting `basePath` for servlet prefixes.

Example in Spring Security 6.5+ configuration:

```java
import static org.springframework.security.web.servlet.util.matcher
        .PathPatternRequestMatcher.withDefaults;

PathPatternRequestMatcher.Builder paths = withDefaults();

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(paths.matcher(HttpMethod.GET, "/api/orders/{orderId}"))
        .hasAuthority("orders.read")
    .requestMatchers(paths.matcher(HttpMethod.POST, "/api/orders"))
        .hasAuthority("orders.create")
    .requestMatchers(paths.matcher("/public/**"))
        .permitAll()
    .anyRequest().denyAll()
);
```

This is a **configuration fragment**; it needs `HttpMethod` and `PathPatternRequestMatcher` imports, must live inside a `SecurityFilterChain` bean, and requires authentication setup. `PathPatternRequestMatcher.Builder#matcher(HttpMethod, String)` matches **both** method and path. With null method or the path-only overload, the rule does not restrict the HTTP method.

**Key points:**

- Patterns start with `/` and are written relative to the context path.
- `basePath` is used when requests share a servlet path prefix, e.g., `basePath("/mvc")`.
- Supports `{var}`, `{var:regex}`, `{*rest}`, and returns variables via `RequestMatcher.MatchResult`.
- Ensure the related `HandlerMapping` uses a **`PathPatternParser` compatible** with the matcher. `withDefaults()` uses parser defaults; if MVC customizes the parser, align them so controller and security matching agree.
- Recommended replacement in Spring Security 6.5 for `AntPathRequestMatcher`/`MvcRequestMatcher` when preparing to upgrade to Spring Security 7.

### 4.2. `MvcRequestMatcher` – Matching by Previous-Generation Spring MVC Semantics

`org.springframework.security.web.servlet.util.matcher.MvcRequestMatcher` uses **`HandlerMappingIntrospector`** to align with Spring MVC's matching semantics, supporting variables. It was useful in projects already using earlier MVC integration.

Characteristics:

- Matching is tied to how Spring MVC configures handler mappings and parsers.
- If DispatcherServlet is not mapped at default `/` and has a **custom servlet path**, you must declare the proper `servletPath`/builder so routes across servlets are not confused.
- You can use `MvcRequestMatcher.Builder(introspector).servletPath("/mvc")` in compatible 6.x versions.
- As of **Spring Security 6.5**, `MvcRequestMatcher` is **deprecated for removal**; documentation recommends migrating to `PathPatternRequestMatcher`. Spring Security 7 no longer uses it as the default matcher.

Legacy project example (migration illustration, **not recommended for new code**):

```java
MvcRequestMatcher.Builder mvc = new MvcRequestMatcher.Builder(introspector)
    .servletPath("/mvc");

RequestMatcher matcher = mvc.pattern("/orders/{orderId}");
```

To upgrade, consider `PathPatternRequestMatcher.withDefaults().basePath("/mvc").matcher("/orders/{orderId}")` and re-verify all URI/servlet mappings in integration tests; do not just swap class names and assume every case behaves identically.

### 4.3. `AntPathRequestMatcher` – Legacy Ant Syntax

`org.springframework.security.web.util.matcher.AntPathRequestMatcher` applies Ant-style patterns to the `servletPath + pathInfo` portion of the request; **it ignores the query string**. It uses `AntPathMatcher` (with optimizations for simple `/**` patterns).

Legacy example:

```java
RequestMatcher legacy = AntPathRequestMatcher.antMatcher("/api/**");
```

Notes:

- `/api/**` in the dedicated Ant path matcher can match `/api`, `/api/`, and child paths.
- Ant-style handles `*`, `?`, `**`, `{var}`, and nested syntax differently from `PathPattern`; notably **mid-path `**` can be accepted** under Ant, whereas `PathPattern` disallows it.
- Default constructors/matchers are generally **case-sensitive**, though overloads can configure otherwise; do not assume all matchers are case-insensitive.
- In **Spring Security 6.5**, this class is also **deprecated for removal**, and Javadoc recommends using `PathPatternRequestMatcher`. Do not introduce new usages in long-term designs merely because legacy code uses it.

### 4.4. `RegexRequestMatcher` – Java Regular Expression Syntax

`org.springframework.security.web.util.matcher.RegexRequestMatcher` uses **Java regex**, not `PathPattern` or Ant templates:

```java
import static org.springframework.security.web.util.matcher
        .RegexRequestMatcher.regexMatcher;

RequestMatcher onlyNumericId = regexMatcher(
    HttpMethod.GET, "/api/orders/[0-9]+"
);
```

It can restrict the HTTP method, e.g., GET. Regex `[0-9]+` matches "one or more ASCII digits"; to match a literal dot, escape it properly in regex/Java string syntax.

**Important difference regarding queries:** Per Javadoc, `RegexRequestMatcher` matches against **`servletPath + pathInfo + queryString`** (if a query exists, `?` is appended to the string). By contrast, `AntPathRequestMatcher` ignores the query, and path-based matchers generally examine only the path.

Therefore, the pattern `/api/orders/[0-9]+` may match `GET /api/orders/42` **but fail to match** `GET /api/orders/42?preview=true` with `RegexRequestMatcher`, because the matched string includes the query. Write regexes scoped appropriately or use a path matcher and inspect queries in a separate policy.

Do not apply Ant thinking like `/api/orders/**` to `RegexRequestMatcher`: in regex, `*` is a quantifier on **the immediately preceding element**, and consecutive `**` is invalid or means something else. Multi-segment regex looks like `/api/orders/.*`; however, `.*` is overly broad and easily opens unintended paths.

### 4.5. Custom RequestMatcher and Composite Matchers

If you need to evaluate **a trusted host**, header, query, method, IP, or other request state that path matchers cannot express, you can write a custom `RequestMatcher`:

```java
RequestMatcher previewRequest = request ->
        "GET".equals(request.getMethod())
        && "/api/reports".equals(request.getServletPath())
        && "true".equals(request.getParameter("preview"));
```

This is a **Servlet application snippet**, illustrating only how to create a lambda for the `RequestMatcher` functional interface (for simple paths and default mapping). In practice, handle `pathInfo`, context/servlet path, duplicate query parameters, and untrusted inputs; if path variables are needed from a custom matcher, implement `matcher(request)` returning an appropriate `MatchResult`.

Conditions can be composed using `AndRequestMatcher`, `OrRequestMatcher`, and `NegatedRequestMatcher`. However, complex combinations can make policy hard to read; prefer focused matchers alongside tests for adverse cases.

## 5. Comparison Table of Error-Prone Differences

| Aspect | PathPatternRequestMatcher | MvcRequestMatcher (6.x legacy) | AntPathRequestMatcher (legacy) | RegexRequestMatcher |
| --- | --- | --- | --- | --- |
| Language | Segment-based Spring `PathPattern` | Spring MVC mapping semantics via introspector | Ant-style path pattern | Java regular expression |
| `{id}` | Named segment; extracts variable | Can extract template variable per MVC | Supports Ant-style templates | **Does not** treat `{id}` as a named template |
| Mid-path `**` | **Invalid** in PathPattern | Depends on MVC strategy/version | Can be valid in Ant | `**` is not equivalent to a path wildcard |
| `{*rest}` | Named catch-all at the end | Depends on MVC parser/config | Not the same PathPattern contract | Not a built-in regex syntax |
| Query string | Path matcher, does not inspect query automatically | Per MVC path semantics | Ignores query | **Matched string may include query** |
| Case sensitivity | Per parser config (case-sensitive by default) | Per MVC config | Per constructor (case-sensitive by default) | Case-sensitive by default; configurable |
| Servlet path | `basePath`/context-path rules | `servletPath` matters | `servletPath + pathInfo` | `servletPath + pathInfo + query` |
| HTTP method combination | Builder accepts `HttpMethod` | Method configurable | Has method overload | Has method overload |
| Guidance for new code | **Preferred where applicable** | Deprecated for removal 6.5 | Deprecated for removal 6.5 | Use when regex is genuinely needed |
| Key tests needed | Pattern parsing, variables, encoded paths | DispatcherServlet/parser alignment | Legacy matching, query ignoring | Regex escaping, query, full-string matching |

**Never replace one matcher with another without re-verifying the set of matched requests.** "Looking like the same pattern" does not prove the same policy.

## 6. RequestMatcher and Path Variables: MatchResult Differs from Controller @PathVariable

A Spring MVC controller can declare:

```java
@GetMapping("/api/documents/{documentId}")
public DocumentDto getDocument(@PathVariable String documentId) {
    return service.read(documentId);
}
```

The controller receives `documentId` **after mapping the request to the method**. Meanwhile, Spring Security HTTP authorization may need the ID **before the request is dispatched to the controller**. `RequestMatcher.MatchResult#getVariables()` places pattern variables into `RequestAuthorizationContext#getVariables()` for rules to use.

These are **two separate matches at two different layers**; matching variable names are a convention to keep consistent, not a single Java object shared automatically.

Example with `PathPatternRequestMatcher`:

```java
PathPatternRequestMatcher.Builder path = PathPatternRequestMatcher.withDefaults();

RequestMatcher byId =
    path.matcher(HttpMethod.GET, "/api/documents/{documentId}");
```

For `GET /api/documents/42`, the matcher can extract `documentId=42`. But if the client calls `GET /api/documents/42/history`, the single-segment pattern above **does not match**. To route history, define a separate pattern and appropriate policy.

### 6.1. Using Variables for Dynamic Authorization, Not Just URL Matching

Example using `AuthorizationManager<RequestAuthorizationContext>` combined with an application-defined business service:

```java
@Bean
SecurityFilterChain docsSecurity(
        HttpSecurity http,
        DocumentAccessPolicy documentAccessPolicy
) throws Exception {

    PathPatternRequestMatcher.Builder paths =
            PathPatternRequestMatcher.withDefaults();

    AuthorizationManager<RequestAuthorizationContext> canReadDocument =
            (authentication, context) -> {
                Authentication user = authentication.get();

                if (user == null
                        || user instanceof AnonymousAuthenticationToken
                        || !user.isAuthenticated()) {
                    return new AuthorizationDecision(false);
                }

                String documentId = context.getVariables().get("documentId");
                boolean granted = documentId != null
                        && documentAccessPolicy.canRead(
                                user.getName(), documentId);

                return new AuthorizationDecision(granted);
            };

    http.authorizeHttpRequests(auth -> auth
        .requestMatchers(
                paths.matcher(
                    HttpMethod.GET, "/api/documents/{documentId}"
                )
        ).access(canReadDocument)
        .anyRequest().denyAll()
    );

    return http.build();
}
```

**This is a Spring integration fragment, not a standalone program.** Required imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
```

`DocumentAccessPolicy` is a **custom bean/service**, e.g., `boolean canRead(String subject, String documentId)`, which must read trusted data to check owner, tenant, sharing, and document state. Never infer access merely because an ID is numeric or the user supplied it.

Technical notes:

1. Uses `documentId` from the **matched matcher's variables**.
2. Uses Spring-verified `Authentication` to identify the subject.
3. Rejects anonymous users; `Authentication#isAuthenticated()` alone is not enough to distinguish all "anonymous" tokens in Spring Security.
4. The resource service checks permissions on **the actual document** from a trusted data source.
5. Add rules for list, upload, export, delete actions, and method security if needed; `GET /api/documents/{documentId}` does not cover every entry point to the data.

In Spring Security 6.5, `AuthorizationManager#check(...)` is deprecated in favor of `authorize(...)`. The `AuthorizationManager` lambda in the example uses the compatible Spring Security 6.5 contract; review signatures when upgrading major versions.

### 6.2. Path Variables Are Not Proof of Identity or Authority

This rule is **dangerous** if the system fails to bind the principal:

```text
Request: GET /api/users/admin/settings
Path variable: userId="admin"
=> Must not infer the caller is an admin.
```

A variable in the URL is **client-chosen input**. Compare it against trusted `Authentication` and business conditions. Even if `/api/users/{userId}` checks `authentication.name == userId`, ensure this ID is truly the user's canonical ID, which may not equal email/username/subject claims across different issuers.

## 7. Select Matchers by HTTP Method, Not Only Path

For `/api/documents/{documentId}`:

- `GET` may require `documents.read`.
- `PATCH` may require `documents.edit`.
- `DELETE` may require `documents.delete`.

Do not place `requestMatchers("/api/documents/**").hasAuthority("documents.read")` in front if you want to check mutations separately: a method-unrestricted matcher will match POST, PATCH, and DELETE before stricter rules are evaluated.

Example:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(
        paths.matcher(HttpMethod.DELETE, "/api/documents/{documentId}")
    ).hasAuthority("documents.delete")

    .requestMatchers(
        paths.matcher(HttpMethod.PATCH, "/api/documents/{documentId}")
    ).hasAuthority("documents.edit")

    .requestMatchers(
        paths.matcher(HttpMethod.GET, "/api/documents/{documentId}")
    ).hasAuthority("documents.read")

    .anyRequest().denyAll()
);
```

Result table when the principal has **only `documents.read`**:

| Request | Matching rule/method | HTTP authorization result |
| --- | --- | --- |
| `GET /api/documents/42` | GET + `{documentId}` | ALLOW |
| `PATCH /api/documents/42` | PATCH + `{documentId}` | DENY |
| `DELETE /api/documents/42` | DELETE + `{documentId}` | DENY |
| `GET /api/documents/42/versions` | Matches none of the three single-segment rules | DENY by fallback |
| `GET /api/documents` | Matches none of the three rules expecting an ID | DENY by fallback |
| `GET /api/documents/abc` | Matches `{documentId}` if no regex constraint | ALLOW at URL layer; controller/service may reject invalid ID |

The table describes only **rule-level authorization** for the example; actual HTTP outcomes also depend on CSRF, authentication, controllers, and resource policies.

## 8. Standalone Java 17: Distinguishing Single-Segment, Multi-Segment, and Regex

The program below uses **Java SE 17** with no Spring dependencies. It uses explicit Java regexes to **simulate three semantics**:

- Single segment `{id}`: `^/reports/[^/]+$`.
- Zero or more trailing segments `/**`: `^/reports(?:/.*)?$`.
- Numeric ID segment `{id:[0-9]+}`: `^/reports/[0-9]+$`.

**This is a learning model**, not a replacement implementation for `PathPatternRequestMatcher`. In real tests, use the Spring matcher aligned with your project's servlet request and parser.

Create file **`PathWildcardDemo.java`**:

```java
import java.util.List;
import java.util.regex.Pattern;

public class PathWildcardDemo {

    static final Pattern ONE_SEGMENT =
            Pattern.compile("^/reports/[^/]+$");

    static final Pattern ALL_DESCENDANTS =
            Pattern.compile("^/reports(?:/.*)?$");

    static final Pattern NUMERIC_ID =
            Pattern.compile("^/reports/[0-9]+$");

    record Request(String method, String path, String query) {
        String pathAndQuery() {
            return query == null ? path : path + "?" + query;
        }
    }

    static boolean matches(Pattern pattern, String path) {
        return pattern.matcher(path).matches();
    }

    public static void main(String[] args) {
        List<String> paths = List.of(
                "/reports",
                "/reports/42",
                "/reports/42/items",
                "/reports/abc",
                "/reports/42/"
        );

        for (String path : paths) {
            System.out.println(
                    path
                    + " | one=" + matches(ONE_SEGMENT, path)
                    + " | deep=" + matches(ALL_DESCENDANTS, path)
                    + " | numeric=" + matches(NUMERIC_ID, path)
            );
        }

        Request withQuery =
                new Request("GET", "/reports/42", "download=true");

        System.out.println("path-only: "
                + matches(NUMERIC_ID, withQuery.path()));
        System.out.println("path+query full regex: "
                + matches(NUMERIC_ID, withQuery.pathAndQuery()));
        System.out.println("GET numeric: "
                + ("GET".equals(withQuery.method())
                   && matches(NUMERIC_ID, withQuery.path())));
        System.out.println("POST numeric: "
                + ("POST".equals(withQuery.method())
                   && matches(NUMERIC_ID, withQuery.path())));
    }
}
```

Compile/run with JDK 17+:

```bash
javac PathWildcardDemo.java
java PathWildcardDemo
```

Exact stdout:

```text
/reports | one=false | deep=true | numeric=false
/reports/42 | one=true | deep=true | numeric=true
/reports/42/items | one=false | deep=true | numeric=false
/reports/abc | one=true | deep=true | numeric=false
/reports/42/ | one=false | deep=true | numeric=false
path-only: true
path+query full regex: false
GET numeric: true
POST numeric: false
```

**Explanation of each case:**

1. `/reports` has no ID segment, so `one=false`, while the simulated trailing `/**` matches zero child segments: `deep=true`.
2. `/reports/42` has one numeric ID segment: all three conditions are true.
3. `/reports/42/items` has an extra segment: only the multi-segment condition is true.
4. `/reports/abc` has one segment but is non-numeric: `one=true`, `numeric=false`.
5. `/reports/42/` has a trailing slash, differing from the illustrated single-segment pattern; real PathPattern also depends on parser/trailing-separator policy.
6. Query `download=true` does not alter the **path**; a regex running on **path+query** like `RegexRequestMatcher` must account for the query, so an end-anchored expression may fail to match.
7. GET and POST methods can be distinguished independently of the path.

**Do not treat this simulated output as an absolute security truth table** for Ant/MVC/PathPattern/Regex matchers across all versions. It illustrates the questions to put into tests for real matchers.

## 9. Tricky URLs: Trailing Slashes, Encoding, Semicolons, Case, and Queries

In practice, a path matcher sits atop multiple normalization layers:

```text
Client URL
 -> reverse proxy / WAF
 -> servlet container: path decoding, normalization, mapping
 -> Spring Security: FilterChainProxy + RequestMatcher
 -> Spring MVC: HandlerMapping / @RequestMapping
 -> service / repository
```

If the **proxy, Spring Security, and Spring MVC interpret URLs differently**, security rules may inspect one resource while the controller handles another. That is why you must never write a matcher using simple string comparison and assume it aligns with MVC routing.

### 9.1. Trailing Slash

`/api/items/42` and `/api/items/42/` can behave differently depending on the matcher/parser. Modern Spring Framework versions do not treat the two paths as equivalent by default across all configurations.

**Recommendation:** choose a clear canonical path, test with/without trailing slash in integration tests, and do not rely on framework auto-redirects or normalization without verifying. A bypass can occur if the matcher rejects strictly while the controller accepts another variant via separate configuration.

### 9.2. Encoded Slashes and Path Traversal

`%2F` is a percent-encoded slash. Segment-based path parsers may handle encoded paths differently from decoding the whole string and splitting; servlet containers/proxies may also block or normalize URLs according to their own policies.

Test variants such as:

```text
/api/files/a%2Fb
/api/files/a/b
/api/files/%2e%2e/secret
/api/files/../secret
/api/files/a%252Fb
```

Never claim an encoded path combination "definitely matches/does not match" without knowing the container, firewall, and matcher. Never use a path variable directly as an OS filesystem path: normalize and enforce directory boundaries after appropriate decoding.

### 9.3. Matrix Variables, Semicolons in Segments

Spring MVC supports **matrix variables** like `/cars/42;color=red`. Depending on configuration, `StrictHttpFirewall` may block semicolons and disallowed URL characters before matchers run. If the application intentionally uses matrix variables, align the firewall, parser, request matcher, and controller—never disable security checks casually.

### 9.4. Case Sensitivity

Is `/Admin/report` necessarily the same as `/admin/report`? No. Many path matchers are case-sensitive by default; some constructors/parsers allow configuring otherwise. If URLs are altered in case by a proxy or container, test it. Never write `/admin/**` and assume all casing variants are equally protected.

### 9.5. Query Strings and Parameter Order

A path matcher `/download/{id}` generally does not distinguish `/download/42?format=csv` from `/download/42?format=pdf` at the URL path matching step. If PDF export permissions differ from CSV, apply a **query/format-aware policy** in the right place.

Never use an uncontrolled regex over the entire URL just to read a query parameter: parameter order, escaping, repeated parameter names, and encoding easily cause unexpected behavior. Prefer `request.getParameter(...)` with validation or a strongly typed policy service.

## 10. Context Path and Servlet Path: Same Pattern, Different Scope

Suppose deployed at:

```text
Context path:  /portal
Servlet path:  /mvc
Endpoint:      /orders/42
Request URI:   /portal/mvc/orders/42
```

There are two prefixes involved:

- **`/portal`** is the application's context path, typically **omitted from** `PathPatternRequestMatcher` patterns.
- **`/mvc`** is the servlet path (if DispatcherServlet is mapped there). The matcher must be configured with the right prefix/`basePath` matching the path it actually inspects.
- The trailing `/orders/42` is the path handled by the controller.

With `PathPatternRequestMatcher`, matchers sharing a servlet path can be grouped:

```java
PathPatternRequestMatcher.Builder mvc =
        PathPatternRequestMatcher.withDefaults()
                .basePath("/mvc");

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(mvc.matcher(HttpMethod.GET, "/orders/{orderId}"))
        .hasAuthority("orders.read")
    .anyRequest().denyAll()
);
```

Do not add `/portal` to the pattern just from looking at the browser URL. With legacy `MvcRequestMatcher`, `setServletPath("/mvc")` served a similar role with a different API; with `AntPathRequestMatcher`, matching runs on `servletPath + pathInfo`.

**When multiple Servlets exist**, a matcher auto-created from a String may be ambiguous. Explicitly specify the servlet path and appropriate matcher instead of assuming the same `/admin` means the same across all servlet mappings.

## 11. Rule Order and Broad Wildcards: The Security Boundary

If you write:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
)
```

Then `GET /api/admin/audit` already matches `/api/**`, so the rule below **never runs**. This is a **first-match-wins** bug, not a regex or URI variable bug.

Fix:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers(HttpMethod.GET, "/api/documents/{documentId}")
        .hasAuthority("documents.read")
    .anyRequest().denyAll()
)
```

Additionally:

- Never assign `/**` to `permitAll` in a chain containing sensitive endpoints.
- Never assume `documents.read` grants access to **every** document; if policy requires owner/tenant checks, verify by ID.
- Never place DELETE/POST rules after a permissive method-unrestricted wildcard.
- Lacking an explicit fallback rule can cause hard-to-reason-about behavior; `anyRequest().denyAll()` makes designs auditable.
- If using multiple `SecurityFilterChain`s, also inspect `securityMatcher` and `@Order`: rules inside a chain **have no effect** on requests that do not enter that chain.

## 12. Upgrade Notes: Spring Security 6.5 → 7

**The method name `requestMatchers(String...)` is not a promise to use one matcher type forever.**

- In Spring Security 6.x projects, creating matchers from Strings can select an implementation based on whether Spring MVC is present, configuration, and registered builders. Traditional 6.x docs describe `MvcRequestMatcher` when MVC is present and `AntPathRequestMatcher` when MVC is absent.
- **Spring Security 6.5** introduces `PathPatternRequestMatcher` and its migration guide explains how to prepare for using it.
- **Spring Security 7** switches to `PathPatternRequestMatcher` by default; `AntPathRequestMatcher` and `MvcRequestMatcher` are no longer supported options on this path.
- Because `PathPattern` restricts `**` to the end, patterns like `/**/admin/**` that worked under Ant may become **invalid** when migrating. Before updating, check the parser and re-test the entire URL set.
- With explicit matchers, import the exact class you intend to use. With String-generated matchers, read the documentation for your running Spring Security version and verify which implementation the DSL chooses.

In an active project, write **tests for actual match outcomes** rather than relying on class names or guesswork. When upgrading major versions, keep those tests to catch semantic regressions.

## 13. Minimum Test Suite for Path Matchers in a Real API

Suppose the rules are:

```text
GET    /api/documents/{documentId}          -> documents.read
PATCH  /api/documents/{documentId}          -> documents.edit
GET    /api/documents/{documentId}/history  -> documents.history
GET    /public/**                           -> permitAll
anyRequest                                -> denyAll
```

Required tests:

| Input | Verification plan |
| --- | --- |
| `GET /api/documents/42` | Matcher captures exactly one segment; variable `documentId=42` |
| `GET /api/documents/42/history` | Not mis-matched by single-segment rule; matches history |
| `PATCH /api/documents/42` | Does not fall into read permission |
| `DELETE /api/documents/42` | Matches neither GET nor PATCH rule; fallback deny |
| `GET /api/documents` | No ID; does not match `{documentId}` |
| `GET /api/documents/abc` | With plain `{documentId}` it may match, requiring validation/other policy |
| `GET /api/documents/42?include=history` | Path matcher may still match ID 42; check query in separate logic |
| `GET /api/documents/42/` | Verify actual trailing slash behavior |
| `GET /API/documents/42` | Verify actual case sensitivity |
| `GET /api/documents/a%2Fb` | Verify encoded slash across container/firewall/parser |
| `GET /public/help` | `permitAll` for the intended public path |
| `GET /publicity/help` | **Not** accidentally permitted by `/public/**` |
| `GET /api/admin/secret` | Not wrongly permitted by broad `/api/**` wildcard |
| With context path/servlet path | Path matcher uses the right namespace without dropping/duplicating prefix |
| With HTTP OPTIONS/CORS | CORS filter/authorization behaves by design, not accidental deny/allow |
| With Servlet `ERROR`/`FORWARD` dispatch | Verified against intentionally configured dispatch policy |

Do not test only with a principal **that has permission**. Test anonymous users, authenticated users lacking permission, wrong scope/role prefixes, and paths very close to allowed patterns.

### Testing Actual Matchers with MockMvc / Spring Security Test

After configuring a Spring Boot test context with controllers and `spring-security-test`, you can write tests (illustrative snippet, **not a standalone runnable file**):

```java
mvc.perform(get("/api/documents/42")
        .with(user("alice").authorities(
                new SimpleGrantedAuthority("documents.read"))))
    .andExpect(status().isOk());

mvc.perform(patch("/api/documents/42")
        .with(user("alice").authorities(
                new SimpleGrantedAuthority("documents.read")))
        .with(csrf()))
    .andExpect(status().isForbidden());
```

`isOk()` assumes the controller in the test returns 200 on success. If the controller does not exist, a request passing authorization may still return 404. For POST/PATCH/DELETE, `with(csrf())` separates CSRF errors from authorization errors when CSRF is enabled.

To test **the matcher itself**, you can use `MockHttpServletRequest` in Spring Test to call `matcher.matches(request)` and inspect `matcher.matcher(request).getVariables()`, remembering to set `servletPath`/`contextPath` to match the real runtime.

## 14. Common Mistakes and Fixes

| Mistake | Why it's wrong | How to fix |
| --- | --- | --- |
| Using `*` to match multiple URL levels | `*` only represents content within one segment | Use `/**` if descendants are truly intended, or more specific routes |
| Putting `**` in the middle of a PathPattern | PathPattern disallows mid-pattern catch-all | Split patterns or use a tested alternative matcher |
| Using `{id}` and assuming the ID is valid/authorized | Path variable is just client data | Validate ID and check owner/tenant/permission server-side |
| Using `RegexRequestMatcher` with Ant pattern `/api/**` | Regex `*` is not a path wildcard | Write accurate Java regex and test query/method |
| Using `RegexRequestMatcher` with `/api/orders/[0-9]+` and URLs with query fail | RegexRequestMatcher can include the query string | Handle query/regex intentionally or use a path matcher |
| Assuming String `requestMatchers` is always Ant | Implementation depends on version/config | Check Spring Security version; use explicit matcher if needed |
| Forgetting servlet path with multiple servlets | Security and MVC may inspect different prefixes | Configure `basePath`/`servletPath` properly |
| Adding context path into PathPattern | Causes prefix duplication and failed matches | Write patterns relative to the context path |
| Placing `/api/** permitAll` before admin rules | Broad rule matches first and shadows admin rule | Specific first, fallback last |
| Using `path variable` directly as an unchecked file path | Allows traversal/escaped paths | Normalize, restrict root, validate server-side |
| Assuming `@GetMapping` always uses the same parser as Spring Security | Config/versions can diverge | Align parser/Matcher and integration tests |
| Testing only paths with standard slashes | Can leak via slash/encoding/case variants | Test URL edge cases and canonical routing |
| Using one path-only matcher for all methods | GET read can open mutations | Combine HTTP method with separate rules |
| Disabling firewall to make unusual requests "work" | Alters the attack surface | Understand root cause, fix specific policy, never disable wholesale |

## 15. Self-Check Questions

**1. Does `/api/orders/*` match `/api/orders/42/items`?**  
No under PathPattern single-segment wildcards; it does not cross slashes.

**2. Does `/api/orders/**` differ from `/api/orders/{orderId}`?**  
Yes. `/**` can match multiple segments (including zero trailing segments); `{orderId}` requires exactly one segment and binds a variable name.

**3. Can `/api/**/admin` be used in PathPattern?**  
No; `**` must be at the end of a PathPattern. An older Ant pattern may differ, so test when migrating.

**4. Does `GET /api/orders/42?expand=true` necessarily behave differently under RegexRequestMatcher?**  
Potentially yes. RegexRequestMatcher evaluates a string containing path and query; a regex anchored to the end of the path may not match when a query is present. With path matchers, queries are usually handled separately.

**5. Does `{userId}` from the URL prove the caller is that user?**  
No. You need trusted authentication and a policy checking relationship/tenant.

**6. In Spring Security 6.5, which matcher is recommended to replace AntPathRequestMatcher/MvcRequestMatcher?**  
`PathPatternRequestMatcher`.

**7. Having `documents.read`, is `GET /api/documents/42` guaranteed to view document 42?**  
No. If business rules require owner/share/tenant checks, document 42 must be checked further.

**8. Why should `/api/orders/42/` and `/api/orders/42` be tested separately?**  
Trailing-slash matching can differ by parser/config; never assume equivalence.

**9. Does `requestMatchers(HttpMethod.GET, "/api/orders/**")` apply to POST?**  
No; it matches GET. POST requires its own rule or fallback handling.

**10. Do `securityMatcher` and `requestMatchers` using the same pattern have the same effect?**  
No. One selects the **SecurityFilterChain**, and the other selects an **authorization rule within the chosen chain**.

## Practical Summary

- **`*` and `?`** apply only to characters within a single segment; **`**`** covers trailing segments; **`{id}`** matches one segment and extracts a variable; **`{*rest}`** captures the remaining path in PathPattern.
- **`PathPatternRequestMatcher`** follows PathPattern syntax and is the recommended direction in Spring Security 6.5+/7. **`MvcRequestMatcher`** and **`AntPathRequestMatcher`** are legacy/deprecated in 6.5. **`RegexRequestMatcher`** uses Java regex with different matched-string semantics, especially regarding queries.
- **A successful match does not mean allowed**. Spring Security still evaluates authorities, and many applications must additionally check resource/tenant/owner.
- **Always test on the real stack**: HTTP method, path segments, trailing slashes, case, encoded URLs, context/servlet paths, parser, queries, and rule order.
- **Do not guess the default matcher solely from the name `requestMatchers`**; check your version and configuration.

## References

- [Spring Security 6.5 – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 – Migrate to PathPatternRequestMatcher](https://docs.spring.io/spring-security/reference/6.5/migration-7/web.html)
- [Spring Security 6.5 – PathPatternRequestMatcher Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/servlet/util/matcher/PathPatternRequestMatcher.html)
- [Spring Security 6.5 – AntPathRequestMatcher Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/util/matcher/AntPathRequestMatcher.html)
- [Spring Security 6.5 – MvcRequestMatcher Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/servlet/util/matcher/MvcRequestMatcher.html)
- [Spring Security 6.5 – RegexRequestMatcher Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/util/matcher/RegexRequestMatcher.html)
- [Spring Framework – Mapping Requests and PathPattern syntax](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html)
