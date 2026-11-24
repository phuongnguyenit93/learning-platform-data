# Trailing Slashes, Case Sensitivity, and Encoded Characters in RequestMatcher

## 1. Why Does the Same Endpoint Have Multiple URL Forms?

In a Spring Boot / Spring Security application, policy authors typically see a single clear route:

```text
GET /api/admin/users
```

Yet an HTTP client can send variants:

```text
GET /api/admin/users/
GET /API/ADMIN/users
GET /api/admin%2Fusers
GET /api/%61dmin/users
GET /api/admin//users
GET /api/admin/../public
GET /api/admin;v=1/users
```

Here, `%2F` is the percent-encoding of `/`; `%61` represents the letter `a`. Some variants are **rejected** by a layer ahead of the application, some fail to match the controller, and some are normalized and may route to the same logic. The outcome depends on **the Servlet container, proxy, firewall, RequestMatcher, Spring MVC configuration, and library versions**. Therefore, never claim that every URL in the list is handled identically.

The biggest risk is not merely a confusing 404 error. If **the authorization layer sees one path** while **the business-handling layer sees a different path**, the system can grant the wrong permissions: an administrative endpoint may slip through a broader rule via a URL variant, or a request may be checked against the pre-decoded path while the controller maps it after decoding.

**Lesson objectives**:

1. Understand the impact of **trailing slashes**: `/reports` and `/reports/`.
2. Understand **case sensitivity**: `/admin`, `/Admin`, `/ADMIN`.
3. Understand percent encoding, double encoding, encoded slashes, and path normalization.
4. Separate the roles of `StrictHttpFirewall`, `SecurityFilterChain`, `RequestMatcher`, and `@RequestMapping`.
5. Choose a safe canonical URL convention without breaking permission boundaries.
6. Write stable protection rules and test variants in both MockMvc and on a real HTTP stack.

Examples focus on **Spring Security Servlet/Spring MVC**, Java 17+. WebFlux uses different components. When multiple versions exist, cross-check your project's **resolved Spring Framework/Spring Security version** rather than applying an observation from one environment to every system.

## 2. Request Journey: Who Sees the URL at Each Step?

```text
Client/browser/curl
      │
      ▼
CDN / load balancer / reverse proxy
      │   May redirect, decode, collapse slashes, or reject.
      ▼
Servlet container
      │   requestURI, contextPath, servletPath, pathInfo...
      ▼
Spring Security FilterChainProxy + HttpFirewall
      │   Inspects/wraps requests and rejects dangerous URLs.
      ▼
Select SecurityFilterChain (securityMatcher)
      │
      ▼
AuthorizationFilter + requestMatchers
      │   First matching matcher decides the policy.
      ▼
DispatcherServlet + HandlerMapping
      │   Selects controller per Spring MVC mapping.
      ▼
Service/domain authorization
      │   Checks permission on exact object/tenant/owner.
      ▼
Business action / response
```

This is a conceptual diagram, not a substitute for the exact order of every filter customized by a project. Key points:

- **Proxy and container layers** may alter or reject a URL before Java code receives it.
- **`HttpFirewall`** is not an authorization rule; it blocks/normalizes unsafe requests before matchers inspect the path.
- **`securityMatcher`** selects which filter chain runs; if no chain matches, the request may go unprotected by Spring Security.
- **`requestMatchers`** decides permissions **inside** the chosen chain.
- **Spring MVC `@RequestMapping`** routes to controllers, and may follow different path-matching conventions if configuration diverges.
- **Service policy** must still check object/tenant permissions. A URL looking like an allowed resource does not prove access to a specific record.

**Principle:** requests used for security matching and for controller mapping must share **the same view of URL structure**. Ambiguous or unsupported URLs should be rejected explicitly rather than decoded/normalized repeatedly under conflicting rules.

## 3. Trailing Slash: /resource Does Not Default to /resource/

### 3.1. Two Different URLs at the Path Level

```text
/api/reports
/api/reports/
```

A trailing `/` changes the path string. Depending on configuration, the request may:

- Match the same handler and the same security rule.
- Match the security rule but miss the handler → potentially 404 after passing authorization.
- Miss the security rule and fall into deny fallback.
- Be redirected by a proxy/filter from the slashed form to the canonical form.
- Be rejected by an upstream layer if the system's convention requires exact URLs.

**Do not guess the behavior of `requestMatchers("/api/reports")` solely from the API name.** The outcome depends on the matcher implementation in use. With the default `PathPatternParser` in Spring Framework 6.x/7.x, arbitrary optional trailing-slash matching **is not enabled**.

### 3.2. Major Change in Spring Framework 6

In `PathPatternParser`:

```text
Spring Framework 6.x default:
  matchOptionalTrailingSeparator = false
  caseSensitive                 = true
```

Previously, some legacy configurations treated trailing slashes as optional by default. Spring Framework 6.0 changed the default and deprecated automatic trailing-slash matching for safety reasons; Framework 7.0 documentation introduces handling via `UrlHandlerFilter` instead of legacy optional trailing-slash matching.

Example with a parsed PathPattern under defaults:

```text
Pattern: /api/reports

Path: /api/reports      -> MATCH
Path: /api/reports/     -> NO MATCH
```

This is the result **for that specific pattern with the default parser**, not a claim that every `AntPathRequestMatcher`, custom matcher, or older Spring Security configuration behaves identically.

### 3.3. Recommendation: One Canonical URL Form

Pick a convention, for example:

```text
Canonical: GET /api/reports
Alias:     GET /api/reports/
```

Then explicitly decide whether the alias will:

1. **Be rejected/not matched:** simple and strict for APIs requiring exact URLs.
2. **Be intentionally redirected** to the canonical URL; ensure proxies and security handle pre- and post-redirect consistently.
3. **Be supported as a second route** if the product needs compatibility with legacy clients; both must share **the same policy** and be tested.

Do not fix a single endpoint by enabling broader global matching; altering the global parser can affect other sensitive URLs.

### 3.4. If Both Forms Genuinely Must Be Supported

An explicit way to declare **both paths** in both Spring MVC and HTTP authorization:

```java
// Spring MVC controller fragment:
@GetMapping({"/api/reports", "/api/reports/"})
public List<ReportView> listReports() {
    return reportService.listVisibleReports();
}
```

And in the corresponding Spring Security configuration:

```java
.requestMatchers(
        HttpMethod.GET,
        "/api/reports",
        "/api/reports/"
).hasAuthority("report:read")
```

These are two **integration fragments** requiring dependencies, controllers, services, imports, and a `SecurityFilterChain`. Listing explicitly is usually easier to reason about than assuming "two URLs are automatically equivalent." If business rules only permit one form, do not open the other.

### 3.5. Redirecting with UrlHandlerFilter in Supported Versions

Spring Framework **6.2+** includes `UrlHandlerFilter` to handle trailing slashes via redirects or request wrapping. Example for an API expecting no trailing slash:

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.filter.UrlHandlerFilter;

// Filter creation fragment, not a SecurityFilterChain:
UrlHandlerFilter filter = UrlHandlerFilter
        .trailingSlashHandler("/api/reports/**")
        .redirect(HttpStatus.PERMANENT_REDIRECT)
        .build();
```

The filter must be **registered in the right order**, per Spring Framework docs: after `ForwardedHeaderFilter` (if used) and before security filters / Servlet request-path processing. The example above **only constructs the filter**; it does not register it or set its order. Wrapping requests (`wrapRequest()`) is also an option, but you must understand how the path changes for downstream filters.

HTTP **308 Permanent Redirect** preserves HTTP method and body per HTTP semantics. For state-changing operations, design clear canonical URLs and test client behavior; do not rely on redirects as an authorization layer or assume all clients automatically follow redirects.

**Specifically:** handling trailing slashes does not mean allowing ambiguous URLs such as `%2F`, `//`, or `../`. That is a separate issue belonging to the firewall/path normalization.

## 4. Case Sensitivity: /Admin Is Not Necessarily /admin

### 4.1. PathPatternParser Default

`PathPatternParser` uses `caseSensitive = true` by default. Therefore, with that parser:

```text
Pattern: /api/admin/**

/api/admin/users     -> MATCH
/api/Admin/users     -> NO MATCH
/API/admin/users     -> NO MATCH
/api/ADMIN/users     -> NO MATCH
```

Distinguish **URL path** from **host** in a URL: domain names are generally case-insensitive per DNS rules, whereas **paths** can be case-sensitive. Never turn a property of domain names into an assumption about paths.

### 4.2. Why Can a Mismatch Here Be Dangerous?

Suppose a controller is customized to be **case-insensitive** and handles both:

```text
/api/admin/users
/api/ADMIN/users
```

Meanwhile, the security matcher matches only lowercase, followed by an overly broad fallback:

```java
.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .requestMatchers("/api/**").authenticated()
)
```

If MVC actually routes `/api/ADMIN/users` to the admin controller while the security matcher misses the admin rule, the request might only have to pass `authenticated()`. **This is a risky configuration scenario, not a claim that default Spring MVC necessarily behaves this way.**

Changing the fallback to `denyAll()` turns unmatched URLs into denials, reducing the risk of exposing access through path variants.

### 4.3. Should You Configure Case-Insensitive Matching App-Wide?

Usually **no**—not merely to work around one client's URL typo. If business requirements demand case-insensitive URLs, you must:

- Align the exact same policy across proxy, container, security matchers, and MVC handler mappings.
- Test collisions between routes whose names differ only by case.
- Never blindly lowercase **resource IDs, tokens, signatures, or verification codes**: such data may be case-sensitive.
- Keep admin protection active across all valid variants.
- Establish canonical URLs where possible instead of accepting arbitrary uncontrolled variants.

`PathPatternParser#setCaseSensitive(false)` exists in some versions, but changing the parser is not a "one-line fix everywhere" in Spring Security; configure it only when you understand matchers, MVC, and security consequences. For new applications, **keeping default case sensitivity** is usually easier to audit.

## 5. Percent Encoding: Encoded Characters Are Not Merely Alternate Spellings

### 5.1. Percent Encoding Basics

In a URI, certain octets can be represented as `%HH` (two hex digits). Examples:

| Sequence in request target | Meaning after percent decode | What to watch out for |
| --- | --- | --- |
| `%2F` or `%2f` | `/` | Slash is a **path segment delimiter**, risking structural changes |
| `%5C` | `\` | Backslash can cause path confusion |
| `%2E` | `.` | Dot segments may relate to path traversal |
| `%25` | `%` | Related to **double encoding** risks |
| `%3B` | `;` | Semicolon/path parameters can affect matching |
| `%61` | `a` | Ordinary letter, but decoder/matcher must agree |
| `%00` | NUL | Must not enter business path processing |
| `%20` | Space | May be valid in some URLs/resource naming |

Not every percent-encoded value is malicious, nor can you **assume** every encoded path is accepted by Spring Security. Default firewall policies primarily block ambiguous/dangerous representations. The final outcome also depends on what URL the container/proxy passes to Spring.

### 5.2. Encoded Slash %2F: Same Bytes, Different Structure

Two requests:

```text
/api/admin/users
/api/admin%2Fusers
```

can be seen differently:

- If a layer **decodes** `%2F` into `/` before matching, the path gains an extra segment.
- If another layer keeps the encoded form when splitting segments, `admin%2Fusers` may remain inside a single segment.
- If the firewall blocks encoded slashes, the request is rejected **before reaching authorization matchers**.

Discrepancies among how the proxy, Servlet container, security filter, and handler mapping view the path can cause **authorization bypass** bugs. That is why `StrictHttpFirewall` disallows encoded slashes by default.

**Do not "fix" this by casually calling `setAllowUrlEncodedSlash(true)`.** Enabling encoded slashes requires a threat model, understanding the entire stack, testing all sensitive paths, and a genuine business reason. Usually a better solution is choosing an ID format without `/`, or passing identifiers through another mechanism with a clear contract.

### 5.3. Double Encoding

A sequence such as:

```text
%252F
```

after **one** percent-decode becomes `%2F`; after a **second** decode it becomes `/`. When a proxy decodes once and a service decodes again, the two layers no longer see the same URL. `StrictHttpFirewall` disallows encoded percent `%25` by default precisely because of this class of risk.

Never loop "decode until no `%` remains" or manually decode across multiple layers. For routing, rely on a consistent parser/HTTP stack and decode data only at the layer receiving values with an explicit contract.

### 5.4. Encoded Dots, Path Traversal, and Normalized Paths

Forms like:

```text
/api/admin/../public
/api/admin/%2E%2E/public
/api/admin//users
/api/admin\users
```

require careful testing. Dots `.`/`..`, multiple slashes, backslashes, or encoded versions of them can be normalized differently by proxies and containers. Never patch them with `String.replace(...)` to "fix" authorization.

A safer approach:

1. Reject non-canonical/ambiguous URLs at the firewall layer unless clearly needed.
2. Design security matchers and MVC handlers on the same path-parsing foundation.
3. Define a **deny-by-default** fallback.
4. Run tests through the full deployed stack.
5. Still enforce object-level permissions in services instead of relying solely on URLs.

### 5.5. Semicolons and Matrix/Path Parameters

A semicolon in a path can act as a path parameter delimiter in certain standards/mechanisms, for example:

```text
/api/admin;mode=preview/users
/api/reports;v=1
```

Layers may preserve, strip, or interpret segment parameters differently. `StrictHttpFirewall` typically rejects semicolons by default. If an application has a valid reason to use matrix variables, align path parsing and security matching around the same model rather than loosening the firewall globally just to make one URL work.

### 5.6. Do Not Use URLDecoder to Make Manual Routing Decisions

`java.net.URLDecoder` is designed for **application/x-www-form-urlencoded** and converts `+` into spaces. It is **not** a replacement for Servlet/Spring path parsers. Code like this must never be used to make authorization decisions:

```java
// DO NOT use as an HTTP authorization policy:
String path = java.net.URLDecoder.decode(
        request.getRequestURI(), java.nio.charset.StandardCharsets.UTF_8);
if (path.startsWith("/api/admin")) {
    // ...
}
```

This easily creates a state where "security checked one string while the controller processed another" and risks double decoding. Use framework-supported `RequestMatcher`/`HttpFirewall` and test against the contract.

## 6. StrictHttpFirewall: The Layer That Rejects Ambiguous Requests

Spring Security Servlet provides `HttpFirewall`, typically using `StrictHttpFirewall` as the default implementation. It does not replace authentication/authorization, but reduces the risk of inconsistent URL parsing.

### 6.1. Request Categories Blocked by Default

Per modern `StrictHttpFirewall` Javadocs, defaults include rejecting:

- Encoded slashes `%2F`, backslashes `\`/`%5C`, and encoded percent `%25`.
- Semicolons in paths, unsafe characters like NUL, and certain control characters.
- Certain unnormalized URLs and other anomalous structures.
- HTTP methods, header names/values, parameter names/values, or hostnames violating configured firewall policy.

This list names **representative categories**, not an exhaustive copy of every rule across every version. Check the Javadoc matching your exact version for defaults and active setters. For example, `setAllowUrlEncodedSlash`, `setAllowBackSlash`, `setAllowSemicolon`, and `setAllowUrlEncodedPercent` exist in corresponding releases, yet strict defaults are an intentional security choice.

### 6.2. REJECT, DENY, and NOT_FOUND Are Different

| Scenario | Typical handling mechanism | Interpretation |
| --- | --- | --- |
| `/api/admin%2Fusers` blocked by firewall | `HttpFirewall` / `RequestRejectedException` | **REJECT** because the request target is unacceptable |
| `/api/ADMIN/users` misses admin rule, hits `denyAll` fallback | `AuthorizationFilter` | **DENY** because no policy permits it |
| `/api/reports/` passes authorization but has no MVC handler | `DispatcherServlet` | **NOT_FOUND** because the route does not exist |
| `/api/admin/users` matches admin rule, user lacks role | `AuthorizationFilter` | **DENY** due to insufficient privileges |
| `/api/reports` matches read rule and handler, resource ID not owned by user | Service/domain policy | **DENY** by object-level permission |

**Do not equate these outcomes with fixed HTTP status codes.** Requests hitting `RequestRejectedException` are often translated by a firewall/host handler into a specific status (e.g., 400 depending on config), while an authorization denial can become 403 or a login redirect, and a missing handler can return 404. To test security properly, verify **which layer blocked the request**, rather than merely seeing 403/404.

### 6.3. Should You Relax the Firewall Configuration?

By default, **no**. Before loosening any policy:

1. Identify the real business requirement: does an ID truly need to contain a slash, or did a client simply send a malformed URL?
2. Trace the path proxy → container → firewall → MVC, checking how each layer decodes/normalizes.
3. Limit the scope of any change if possible and verify it does not expose admin/private URLs.
4. Add raw HTTP tests with uppercase/lowercase percent encoding, double encoding, dot-segments, and semicolons.
5. Analyze impacts on caches, routers, WAFs, logs, and object-level authorization.
6. Document the reason, owner, security review process, and rollback strategy.

Enabling an "allow" setter merely because tests fail or return 400 is a dangerous reflex: that initial error may be a protection working as intended.

## 7. PathPatternRequestMatcher and Avoiding MVC/Security Drift

Spring Security has several `RequestMatcher` implementations, including `PathPatternRequestMatcher`, `MvcRequestMatcher`, and legacy Ant-style matchers. Which implementation is chosen and which code path `requestMatchers(String)` takes can vary by Spring Security version, presence of Spring MVC, and application configuration.

### 7.1. Why Understand PathPattern?

Spring MVC uses parsed `PathPattern`/`RequestPath` to process paths segment by segment. This approach decodes/sanitizes individual segments rather than decoding the entire path string and accidentally changing the segment count.

With common patterns:

| Pattern | Meaning under default PathPattern |
| --- | --- |
| `/api/reports` | Exact route, does not automatically accept a trailing slash |
| `/api/reports/` | Route ending with a slash |
| `/api/reports/*` | One child segment under reports |
| `/api/reports/**` | The reports route and descendant segments per `**` semantics |
| `/api/reports/{id}` | Single segment bound to variable `id` |
| `/api/admin/**` | Admin group and corresponding descendants |

Caution: `/api/reports/**` is a **broader rule** than `/api/reports` and can match many paths. Do not append `/**` after a public prefix merely to "fix a trailing slash" if it accidentally grants access to sensitive sub-endpoints.

### 7.2. Configuration Example Using PathPatternRequestMatcher

In Spring Security versions supporting the API (e.g., 6.5+), you can choose the matcher explicitly:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;

@Configuration
public class RouteSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        var paths = PathPatternRequestMatcher.withDefaults();

        return http.authorizeHttpRequests(auth -> auth

            // Admin rule before other routes.
            .requestMatchers(paths.matcher("/api/admin/**"))
                .hasRole("ADMIN")

            // Declare only the canonical form of the reports route.
            .requestMatchers(paths.matcher(HttpMethod.GET, "/api/reports"))
                .hasAuthority("report:read")

            // Undeclared paths/methods are denied.
            .anyRequest().denyAll()
        ).build();
    }
}
```

This is a **configuration class for a Spring Boot/Spring Security project**, not standalone-runnable with `javac`. It assumes the project has authentication and controllers configured; it does not separately handle CSRF/login/CORS. Verify `PathPatternRequestMatcher` imports and factory APIs against your actual version, especially if the project is still on 6.3/6.4 or has multiple Servlets.

When using parsed matchers, ensure compatibility with MVC's `PathPatternParser` and Servlet mapping. If the project customizes case sensitivity or parser options, check how to build matching matchers/builders; do not assume `withDefaults()` automatically knows every customization.

### 7.3. Safety of Broad Matchers

Example to avoid:

```java
.requestMatchers("/api/**").permitAll()
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

`AuthorizationFilter` evaluates the **first matching matcher**. Admin requests already match `/api/**`, so the later admin rule is never evaluated. This is an ordering bug, independent of slash/encoding issues.

With fallback:

```java
.requestMatchers("/api/admin/**").hasRole("ADMIN")
.requestMatchers("/api/reports").hasAuthority("report:read")
.anyRequest().denyAll()
```

an unmatched variant will be denied at HTTP authorization (assuming the request reaches this chain). Never swap `denyAll` for `permitAll` to "allow all URL variants."

### 7.4. securityMatcher Selects the Chain Before requestMatchers

`http.securityMatcher("/api/**")` limits the **SecurityFilterChain scope**, unlike `requestMatchers` inside `authorizeHttpRequests`. If you define only a chain for `/api/**` and no other chain matches a variant URL, requests outside the chain may **go unprotected by Spring Security**.

With multiple chains:

- Provide a **fallback SecurityFilterChain** without a restrictive matcher if the entire app needs protection.
- Verify `@Order` and which chain gets selected.
- Test case and slash variants at **both chain selection** and **authorization rule** levels.
- Do not assume `anyRequest().denyAll()` inside an `/api/**` chain blocks a request that never matched that chain.

## 8. Building a Safe Canonical URL Convention

A "convention" does not just say "use lowercase, no trailing slash." It must specify how non-conforming requests are handled.

### 8.1. Recommended API Convention

| Aspect | Example convention | When client sends another form |
| --- | --- | --- |
| Static route literals | Lowercase: `/api/reports` | Do not arbitrarily lowercase the entire path |
| Trailing slash | No trailing slash on resource endpoints | Explicitly choose reject/404/308 redirect or alias |
| Encoded slash/backslash | Disallowed in route paths | Keep default firewall rejection |
| Dot segments/double slash | Disallow unnormalized paths | Reject instead of repeatedly auto-fixing |
| Resource IDs | Use UUIDs or IDs without dangerous separators | Validate IDs in service; never rely on unguessable IDs instead of authorization |
| HTTP method | Define GET/POST/PATCH/DELETE per use case | Do not implicitly open other methods |
| Query parameters | Never use queries to disguise privileged routes | Authorize by route and action, validate queries separately |
| Fallback | `anyRequest().denyAll()` | No rule means no access granted |

Conventions only hold when **proxy, container, Security, and MVC all enforce them together**, and exceptions are tested.

### 8.2. Should You Manually Lowercase URLs Before Security?

Do not write a custom filter to do:

```java
// Anti-pattern: do not use as a route decision mechanism.
String normalized = request.getRequestURI().toLowerCase();
if (normalized.startsWith("/api/admin")) {
    // ...
}
```

Because `toLowerCase()` across the whole URL also alters **IDs, tokens, slugs, and signatures** that may be case-sensitive. Furthermore, `startsWith("/api/admin")` matches `/api/administrator`, not an exact admin segment.

If policy requires literal route segments to be lowercase, let the router/handler validate and reject invalid variants while preserving **path variable values**. For prefix matching, use a segment-aware `RequestMatcher` rather than raw string checks.

### 8.3. Combining with Object-Level Permissions

Even when the matcher handles the URL accurately:

```text
GET /api/documents/d42
```

`document:read` still does not prove the caller has permission to read `d42`. In the service, verify tenant, owner, ACL, reviewer, status, or corresponding business logic. Object-level protection is an **additional layer** whenever URLs/clients can specify IDs.

### 8.4. Do Not Leak Sensitive URL Details in Errors

You can log internal reason codes like `FIREWALL_REJECT_ENCODED_SLASH` or `AUTHZ_DENY_NO_MATCH`, without returning policy details, owner, tenant, or stack traces to callers. Avoid logging raw request targets containing tokens or query secrets. When diagnosing encoding issues, log sanitized/bounded representations alongside a request ID.

## 9. Standalone Java 17+: Observing Path Variants

The program below simulates **an intentionally strict policy**. It uses `java.net.URI` to separate raw paths from decoded paths and a minimal set of rejection rules for illustration. **This is not an implementation of Spring Security or StrictHttpFirewall**: it does not simulate Servlet containers, reverse proxies, firewall setters, or filter chain selection. In particular, the simulated rules block only **a few** representative encoding patterns and are insufficient for production protection.

Create file `PathVariantAuthorizationDemo.java`:

```java
import java.net.URI;
import java.util.Locale;
import java.util.Set;

public class PathVariantAuthorizationDemo {

    private static boolean suspiciousRawPath(String raw) {
        if (raw == null || !raw.startsWith("/")
                || raw.contains("//")
                || raw.contains("\\")
                || raw.contains(";")) {
            return true;
        }

        String lower = raw.toLowerCase(Locale.ROOT);
        return lower.contains("%2f")  // encoded /
                || lower.contains("%5c") // encoded backslash
                || lower.contains("%25") // encoded percent
                || lower.contains("%2e") // encoded dot
                || lower.contains("%3b") // encoded semicolon
                || lower.contains("%00"); // encoded NUL
    }

    private static boolean hasRole(Set<String> authorities, String role) {
        return authorities != null
                && authorities.contains("ROLE_" + role);
    }

    static String decide(String target, Set<String> authorities) {
        URI uri;
        try {
            uri = URI.create(target);
        } catch (IllegalArgumentException e) {
            return "REJECT";
        }

        String raw = uri.getRawPath();
        if (suspiciousRawPath(raw)
                || uri.isAbsolute()
                || uri.getRawAuthority() != null
                || uri.getRawQuery() != null
                || uri.getRawFragment() != null) {
            return "REJECT";
        }

        // Conceptual illustration only: URI.getPath() decodes percent sequences.
        // Real Spring apps must let HttpFirewall + RequestMatcher
        // and MVC process paths, never using this function to protect URLs.
        String path = uri.getPath();

        // Distinguish exact segments, do not use startsWith("/api/admin").
        if (path.equals("/api/admin")
                || path.startsWith("/api/admin/")) {
            return hasRole(authorities, "ADMIN") ? "ALLOW" : "DENY";
        }

        // Canonical report URL: trailing slash is not accepted.
        if (path.equals("/api/reports")) {
            return authorities != null && authorities.contains("report:read")
                    ? "ALLOW" : "DENY";
        }

        return "DENY";
    }

    public static void main(String[] args) {
        Set<String> user = Set.of("ROLE_USER", "report:read");
        Set<String> admin = Set.of("ROLE_ADMIN", "report:read");

        System.out.println("reports-canonical="
                + decide("/api/reports", user));
        System.out.println("reports-trailing-slash="
                + decide("/api/reports/", user));
        System.out.println("reports-uppercase="
                + decide("/API/reports", user));
        System.out.println("admin-ordinary-user="
                + decide("/api/admin/users", user));
        System.out.println("admin-admin-user="
                + decide("/api/admin/users", admin));
        System.out.println("admin-trailing-slash="
                + decide("/api/admin/", user));
        System.out.println("admin-case-variant="
                + decide("/api/ADMIN/users", user));
        System.out.println("admin-encoded-letter-user="
                + decide("/api/%61dmin/users", user));
        System.out.println("admin-encoded-letter-admin="
                + decide("/api/%61dmin/users", admin));
        System.out.println("admin-encoded-slash="
                + decide("/api/admin%2Fusers", admin));
        System.out.println("double-encoded-slash="
                + decide("/api/admin%252Fusers", admin));
        System.out.println("double-slash="
                + decide("/api/admin//users", admin));
        System.out.println("semicolon-path="
                + decide("/api/admin;v=1/users", admin));
        System.out.println("unknown-path="
                + decide("/api/administrator", admin));
    }
}
```

Compile and run with **JDK 17 or newer**:

```bash
javac PathVariantAuthorizationDemo.java
java PathVariantAuthorizationDemo
```

Stdout output:

```text
reports-canonical=ALLOW
reports-trailing-slash=DENY
reports-uppercase=DENY
admin-ordinary-user=DENY
admin-admin-user=ALLOW
admin-trailing-slash=DENY
admin-case-variant=DENY
admin-encoded-letter-user=DENY
admin-encoded-letter-admin=ALLOW
admin-encoded-slash=REJECT
double-encoded-slash=REJECT
double-slash=REJECT
semicolon-path=REJECT
unknown-path=DENY
```

**Explanation:**

1. `/api/reports` can be read by a user with `report:read`, whereas `/api/reports/` is a different route under the **single canonical path** convention.
2. `/api/admin/users` requires `ROLE_ADMIN`, while `ROLE_USER` is insufficient.
3. `/api/%61dmin/users` after decoding the letter `a` is classified into the admin branch in the demo, so access is **not** granted to regular users. In real Spring, paths also depend on firewall/parser/container; this lesson does not recommend decoding paths manually like the demo code.
4. `%2F` and `%25` return `REJECT` in the simulation because the input contains dangerous encoding patterns. The demo does not represent all `StrictHttpFirewall` rules.
5. `/api/administrator` is not a child of `/api/admin`; checking segment boundaries avoids granting admin privileges via an overly broad string prefix.
6. `DENY` means the simulated matcher/policy denied access; `REJECT` means the input filter **written for this lesson** rejected it. These are not HTTP status codes.

**Note on Java URL parsing:** `URI.getRawPath()` preserves percent-encoded forms, while `URI.getPath()` returns the decoded path. On a real server, never replace `HttpServletRequest`/`HttpFirewall`/`PathPatternRequestMatcher` with this snippet. To test edge cases, send requests through the real proxy, container, and Spring stack.

## 10. Variant Testing Matrix for RequestMatcher

### 10.1. First Define Expected Behavior for Each Category

Suppose the API intentionally has:

```text
GET /api/reports                 -> report:read
GET /api/admin/users             -> ROLE_ADMIN
All other URL/method variants   -> deny or reject unless explicitly supported
```

The matrix should test:

| Request target | What to verify | Safe outcome per convention |
| --- | --- | --- |
| `/api/reports` | Canonical path + read permission | Allowed when user has `report:read` |
| `/api/reports/` | Trailing slash | Rejected or intentionally redirected |
| `/API/reports` | Different casing | Not automatically equivalent |
| `/api/admin/users` | Sensitive endpoint | Only ADMIN role + additional policy |
| `/api/admin/users/` | Trailing slash inside admin area | Must not downgrade role requirement |
| `/api/ADMIN/users` | Case variant | Must not fall into public rule |
| `/api/admin%2Fusers` | Encoded slash | Blocked by firewall by default in compliant stacks |
| `/api/admin%252Fusers` | Double encoding | Must not decode into an open path |
| `/api/admin%2fusers` | Lowercase hex | Same encoded-slash risk |
| `/api/admin;v=1/users` | Semicolon/path parameters | Must not bypass admin rule |
| `/api/admin//users` | Double slash | Must not bypass admin policy |
| `/api/admin/../reports` | Dot segments | Must not downgrade privileges via differing normalization |
| `/api/%61dmin/users` | Encoded letter | If routed to admin, must still require admin |
| `/api/administrator` | False prefix | Must not be confused with `/api/admin/` |
| `/api/reports?admin=true` | Query string does not change path | No admin privileges from query parameter |
| `POST /api/reports` | Wrong HTTP method | Do not use GET permission to grant POST |

The table above describes **security goals**, not guaranteed default status codes or behavior across every version. The goal of testing is to ensure requests **never reach sensitive handlers without sufficient permissions**, whether via firewall rejection, matcher denial, or handler mismatch.

### 10.2. MockMvc Tests for Normal Paths

This is a **fragment** of a Spring Boot MVC test with Spring Security Test, `MockMvc`, controllers/fixtures, and corresponding imports:

```java
@Test
@WithMockUser(authorities = "report:read")
void canonicalReportPathCanReachHandler() throws Exception {
    mockMvc.perform(get("/api/reports"))
            .andExpect(status().isOk());
}

@Test
@WithMockUser(authorities = "report:read")
void trailingSlashDoesNotGainReportAccess() throws Exception {
    mockMvc.perform(get("/api/reports/"))
            .andExpect(status().isForbidden());
}

@Test
@WithMockUser(roles = "USER")
void userCannotReachAdminEndpoint() throws Exception {
    mockMvc.perform(get("/api/admin/users"))
            .andExpect(status().isForbidden());
}
```

The expected `200`/`403` statuses only hold **with the allowlist config from Section 7**, existing handlers returning appropriate statuses, no alias in the matcher, and no other interfering filter. In another project, a trailing slash might return 404 or an intentional redirect; write assertions matching that contract. Do not confuse "no controller matched" with "authorization was fully enforced" simply because the response is 404.

### 10.3. Testing Encoded Paths Must Run Over Real HTTP

`MockMvc` is not a full Servlet container or reverse proxy. A request builder containing `%2F` may not reproduce how production proxies/containers decode, reject, or rewrite the request-target. Therefore:

1. Test normal paths, trailing slashes, and casing with MockMvc at the framework level.
2. Run integration tests against a real embedded server, and also through a reverse proxy if deployed behind one.
3. Send encoded request-targets with **exact raw bytes** from a suitable HTTP tool, preventing the client from auto-normalizing or following redirects unexpectedly.
4. Check differences across firewall, matcher, and handler layers; inspecting only the response status is insufficient to prove no bypass exists.
5. For admin requests, assert **sensitive handlers are never invoked** when lacking permission, e.g., using an audit/test spy.
6. Whenever firewall or parser settings change, re-run the entire matrix.

Example curl commands merely to illustrate preserving the sent URL:

```bash
curl --path-as-is -i "http://localhost:8080/api/admin%2Fusers"
curl --path-as-is -i "http://localhost:8080/api/admin/../reports"
curl --path-as-is -i "http://localhost:8080/api/ADMIN/users"
```

`curl --path-as-is` prevents curl from stripping certain path components before sending, though it **does not bypass** server-side proxy/container/firewall layers. When encountering redirects in tests, avoid following them automatically so you can distinguish the initial response from the target URL response. Only run in authorized test environments.

### 10.4. Testing HTTP Chain Selection

If the app has:

```java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().denyAll());
```

a path with different casing or encoding may not match `securityMatcher` the same way as the canonical URL. Also test the case where **no chain matches**; a fallback chain must actually protect remaining requests. Do not test only `authorizeHttpRequests` inside the API chain and conclude the application is secure.

## 11. Troubleshooting by Symptom

| Symptom | Possible cause | Investigation path |
| --- | --- | --- |
| `/api/reports` works, `/api/reports/` returns 404 | MVC does not auto-match trailing slash | Inspect `@RequestMapping`, parser, redirect policy |
| Trailing slash returns 403 instead of 404 | Matcher misses, fallback denies | Check first evaluated rule and chain |
| `/API/reports` gives different result from `/api/reports` | Case-sensitive path matching | Check parsers in MVC and Security |
| Uppercase variant reaches admin | MVC/security mismatch + broad fallback | Check overlapping chains/rules |
| `%2F` rejected before controller | StrictHttpFirewall or container | Inspect sanitized exceptions/logs; do not loosen firewall hastily |
| `%252F` yields unpredictable results | Double encoding across layers | Inspect proxy decoding, container, app code |
| `/api/admin//users` behaves differently | URL normalization or path parser | Test raw requests through deployed stack |
| `/api/administrator` demands admin role | `startsWith("/api/admin")` ignores segment boundaries | Use proper `RequestMatcher` |
| Request gets 403 before permission evaluation | CSRF, firewall, or different chain | Isolate each filter/policy |
| Exact path works yet handler runs outside Security | No matching SecurityFilterChain | Check `securityMatcher`/`@Order` and fallback |
| Cross-tenant data still leaked despite right matcher | Missing object authorization | Add policy at service/repository layer |
| MockMvc passes but production differs | Proxy/container decodes/normalizes differently | Integration test through identical HTTP stack |

**How to read logs:** distinguish requests blocked by `RequestRejectedException`, unmatched matchers, `AuthorizationDenied`, missing authentication, or missing MVC handlers. Never log raw requests containing tokens/PII. If verification is needed, enable controlled logging in a test environment rather than altering global rules.

## 12. Dangerous Troubleshooting Reactions

1. **Enabling global optional trailing-slash matching** just because one endpoint needs an alias: can alter rules across the whole application and introduce MVC/Security drift.
2. **Putting `/**` first with `permitAll`** to "make more URLs work": accidentally exposes secured endpoints.
3. **Using `.toLowerCase()` on the entire URL**, including IDs/slugs/tokens: mutates data and can mix up users or resources.
4. **Allowing `%2F`, `%25`, `%5C`** in `StrictHttpFirewall` just to pass a test: weakens security boundaries before understanding the decoding pipeline.
5. **Decoding paths multiple times** with `URLDecoder` or custom regex: creates discrepancies between policy and controller.
6. **Comparing raw prefixes with `startsWith("/admin")`**: matches `/administrator` and non-segment boundaries.
7. **Assuming 404 is always safe**: a handler or exception may have leaked internal data before returning an error; test side effects.
8. **Assuming 403 always comes from hasRole/hasAuthority**: could be CSRF or another filter; identify the exact blocking layer.
9. **Assuming MockMvc always reproduces proxy/Servlet container behavior**: it suits framework testing, not raw HTTP end-to-end encoding tests.
10. **Protecting only one SecurityFilterChain** without a fallback: variant URLs may fall outside the chain's scope.
11. **Relying on hard-to-guess paths** instead of object-level permissions: BOLA/IDOR still applies.
12. **Relying on redirects as access control**: redirects are merely canonical URL policy; authorization must still run on the target request.

## 13. Standard Implementation Workflow for Sensitive Route Groups

### Step 1 — List Allowed URLs and Variants Explicitly

Write a contract for each HTTP method + path:

```text
GET /api/reports             -> authenticated + report:read
GET /api/admin/users         -> ROLE_ADMIN
GET /api/reports/            -> reject / redirect / explicit alias?
GET /API/reports             -> reject or explicitly supported?
Encoded slash in URI path    -> reject by default
All other path/methods       -> deny by default
```

Every `?` in the example is a decision to finalize before deployment. Never let frameworks or proxies implicitly decide policy on behalf of the product.

### Step 2 — Record Parser and Matcher Strategy

Identify Spring Framework/Security versions, Servlet container, whether Spring MVC is present, any custom `PathPatternParser`/`MvcRequestMatcher`/`AntPathRequestMatcher`, and the number of `SecurityFilterChain`s. Do not assume an implementation merely from calling `requestMatchers("...")` in source code.

### Step 3 — Choose Single-Pass Canonicalization at the Right Boundary

For trailing slashes, decide clearly between reject, redirect, or alias; if using `UrlHandlerFilter`, register it in the right order. For encoded separators/path traversal, keep the firewall strict; do not decode manually across multiple layers.

### Step 4 — Protect Sensitive Routes Before Broad Rules

Example structure:

```java
.requestMatchers("/api/admin/**").hasRole("ADMIN")
.requestMatchers(HttpMethod.GET, "/api/reports")
    .hasAuthority("report:read")
.anyRequest().denyAll()
```

If there are multiple filter chains, chain selection must also be tested with URL variants.

### Step 5 — Align Controller Mappings

If only one canonical URL is supported, the controller should map only that URL; if aliases are needed, add them intentionally. Especially review trailing slashes and case sensitivity after upgrading Spring Framework 5.x → 6.x/7.x.

### Step 6 — Write Tests per Layer and Across the Full Request Chain

Matcher/policy unit tests → MockMvc integration → embedded server → proxy end-to-end, including encoding and sensitive paths. Express expected results as **whether sensitive handlers are allowed/disallowed**, along with which layer blocked them.

### Step 7 — Review URL-Related Configuration Changes

A change to proxy rewrites, firewall setters, `UrlHandlerFilter`, MVC path parsers, or `SecurityFilterChain` can affect authorization without touching business code. Treat these as security changes and re-run the test matrix.

## 14. Self-Check Questions

**Question 1.** With the default `PathPatternParser` in Spring Framework 6.x, does `/api/reports` automatically match `/api/reports/`?

**Answer:** No. Default `matchOptionalTrailingSeparator=false`. To support both, choose an explicit alias/redirect or intentional configuration and test it.

**Question 2.** Does `/api/admin/**` match `/API/ADMIN/users` by default?

**Answer:** No under default case-sensitive `PathPatternParser`. End-to-end behavior depends on the actual matcher/handler; crucially, the fallback must never grant access to variant URLs.

**Question 3.** Do `%2F` and `%2f` have the same percent-encoding meaning?

**Answer:** Yes, hex digits in percent encoding are case-insensitive; both represent the slash octet. `StrictHttpFirewall` disallows encoded slashes by default on the Servlet stack.

**Question 4.** Why is `/api/admin%2Fusers` dangerous when different layers decode differently?

**Answer:** One layer may treat `admin%2Fusers` as a single segment while another decodes it into two segments `admin/users`. If policy and handler parse differently, permissions can be misapplied.

**Question 5.** Should you enable `setAllowUrlEncodedSlash(true)` just so clients can call APIs with slashes in IDs?

**Answer:** No. You must evaluate risks across proxy/container/firewall/router. Usually it is better to use another ID format or API design rather than opening the global firewall unreviewed.

**Question 6.** Why shouldn't `/api/administrator` be matched using a raw `startsWith("/api/admin")` check?

**Answer:** Because that checks a string prefix rather than a path segment; it misclassifies `administrator`. Use a segment-aware RequestMatcher.

**Question 7.** The security rule for `/api/reports` returns DENY on a trailing slash while the controller still has an alias. Should you add `/api/**.permitAll()` to fix it?

**Answer:** No. Declare the alias with the same permission, perform a canonical redirect, or drop alias support. Opening a public wildcard can expose other endpoints wrongly.

**Question 8.** An HTTP request carries `%252F`; why must you think about double decoding?

**Answer:** One decode can yield `%2F` and a second decode yields `/`. If layers decode a different number of times, policy and handler see different path structures.

**Question 9.** If a MockMvc test with `%2F` passes, is production behind a reverse proxy guaranteed safe?

**Answer:** No. MockMvc does not fully simulate raw request-targets, proxies, or Servlet containers. Run integration tests against the deployed stack, especially after firewall/parser/rewrite changes.

**Question 10.** Does a 404 error prove the request was properly authorized?

**Answer:** No. There may simply be no handler after passing security, or the request was altered elsewhere. Tests must verify unauthorized requests never reach sensitive actions and object policies still hold.

**Conclusion:** *A URL is only safe when every layer interprets it consistently.* With `RequestMatcher`, explicitly define trailing slashes, case sensitivity, and percent encoding; keep `StrictHttpFirewall` strict, avoid ad-hoc path decoding, use `denyAll` fallbacks, manage `SecurityFilterChain` scopes carefully, and test the full raw HTTP stack. Accurate path matching is necessary, but it never replaces object-level permissions.

## Official References

- Spring Security 6.5 — Authorize HttpServletRequests and request matching: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security 7.0 — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/authorize-http-requests.html
- Spring Security — Java configuration; securityMatcher versus requestMatchers: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — StrictHttpFirewall API (7.x): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/firewall/StrictHttpFirewall.html
- Spring Framework 6.2 — PathPatternParser API, trailing slash and case-sensitive defaults: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/web/util/pattern/PathPatternParser.html
- Spring Framework — Mapping Requests, PathPattern syntax: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html
- Spring Framework — Servlet path matching, segment decoding and URL parsing: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/handlermapping-path.html
- Spring Framework — UrlHandlerFilter and filter ordering: https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html
- Spring Framework 6.2 — UrlHandlerFilter API: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/filter/UrlHandlerFilter.html
- Spring Security — MockMvc integration test: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
