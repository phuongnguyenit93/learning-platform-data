# Custom RequestMatchers and Criteria to Avoid Missing Endpoints

> **Module:** Spring Security - authorization  
> **Group:** RequestMatcher  
> **Learning goal:** Know when to write a custom `RequestMatcher`, understand how matchers differ when selecting a `SecurityFilterChain` vs selecting `authorizeHttpRequests` rules, combine matchers with `AuthorizationManager` to preserve least privilege, and establish a checklist/tests proving critical endpoints are not left uncovered.

## 1. The Problem: An Unmatched Matcher Can Open a Path to Weaker Permissions

Suppose a report management system has:

```http
GET /api/reports/42
GET /api/reports/42?view=preview
POST /api/reports/42/export
GET /internal/metrics
```

Normal reading needs `reports:read`; sensitive preview needs **both** `reports:read` and `reports:preview`. The application might create a custom matcher that matches only when query parameter `view` equals `preview` and attach strong permissions to it. Yet if the controller accepts another alias/format to enable preview, the custom matcher fails to match and the request falls through to a general `authenticated()` rule, accidentally letting users without preview permission bypass HTTP protection.

Another error at a higher level: creating only a `SecurityFilterChain` scoped to `/api/**` without a fallback. When a request hits `/internal/metrics`, if no other chain matches, **none of the Spring Security filters in that configuration run**. An `anyRequest().denyAll()` inside the API chain cannot help URLs outside that chain.

Therefore, there are three boundaries never to confuse:

1. **Chain coverage:** Is the request protected by an appropriate `SecurityFilterChain`?
2. **Rule coverage:** Within that chain, does the selected rule require the right authority/role?
3. **Resource coverage:** After entering the service, does the principal have permission on the **actual object** (tenant, owner, ACL, status)?

A matcher only decides "does the request belong to this set?". It **does not replace** identity authentication, permission decisions, or business-resource checks.

## 2. Two Layers of First-Match: Select Chain, Then Select Rule

```text
HTTP request
   |
   v
DelegatingFilterProxy → FilterChainProxy
   |
   | (A) evaluates SecurityFilterChains in order
   |     selects the FIRST chain whose securityMatcher matches
   v
Selected SecurityFilterChain
   |
   | authentication, SecurityContext, CSRF, other filters
   v
AuthorizationFilter
   |
   | (B) evaluates requestMatchers in declaration order
   |     selects the FIRST rule whose matcher matches
   v
Rule's AuthorizationManager
   |
   +---- DENY -> AccessDeniedException / HTTP handler
   |
   +---- ALLOW -> controller -> service -> domain policy
```

| Matcher attachment point | Meaning | If `matches(request) == false` |
| --- | --- | --- |
| `http.securityMatcher(custom)` | Does this chain apply? | Try lower-priority chains; having no matching chain can leave the request unprotected by Spring Security |
| `authorizeHttpRequests(...requestMatchers(custom))` | Does this authorization rule apply? | Move to the next rule in **the same chain** |
| `web.ignoring()` | Skip Spring Security entirely for this URL | Should not be used casually for public endpoints; usually prefer `permitAll` |
| `@PreAuthorize`/domain policy | Another gate, at method or resource level | Cannot replace accurate HTTP chain/rule selection |

**First-match is not most-specific-match.** Spring Security does not combine all matching rules with AND by default. A broad rule placed before a narrow rule can prevent the narrow rule from ever running.

**Key takeaway:** if every chain has a narrow `securityMatcher`, do not expect an `anyRequest().denyAll()` inside each chain to protect the whole application. Include a fallback chain without a narrow path matcher when the goal is protecting all requests.

## 3. What Interface Is RequestMatcher?

In Spring Security Servlet 6.5, `org.springframework.security.web.util.matcher.RequestMatcher` is a functional interface; core contract:

```java
boolean matches(jakarta.servlet.http.HttpServletRequest request);
```

It also has default method `matcher(HttpServletRequest)` returning `RequestMatcher.MatchResult`, containing match status and a map of extracted path variables if the implementation supports them. `MatchResult` provides methods like `isMatch()`, `getVariables()`, and factories `match()`, `match(Map)`, `notMatch()`.

A simple lambda:

```java
import org.springframework.security.web.util.matcher.RequestMatcher;

RequestMatcher previewParam =
    request -> "preview".equals(request.getParameter("view"));
```

The line above only returns true when the parameter has the matching value. It does **not** check:
- Which URL/path is being called;
- Whether the request is GET or POST;
- Whether the user is authenticated;
- Whether the user holds `reports:preview`;
- Which tenant/owner the resource belongs to.

A lambda inherits the default `matcher(request)` behavior: it normally extracts no path variables, so `MatchResult#getVariables()` will not automatically contain `{id}` from a lambda implementing only `matches`. If path variables are needed, use a supporting path matcher or a custom class overriding `matcher`.

**Do not confuse `RequestMatcher` with `AuthorizationManager<RequestAuthorizationContext>`**. Matchers select a set of requests; managers check `Authentication` and make the decision.

## 4. Prefer Built-In Matchers Before Customizing

| Requirement | Suggestion | Notes |
| --- | --- | --- |
| Path + HTTP method | `PathPatternRequestMatcher` in 6.5+ | Verify context path, servlet path, and parser |
| Both conditions must match | `AndRequestMatcher` | This is AND of **matchers**, not AND of authorities |
| Either of two request types | `OrRequestMatcher` | Avoid accidentally creating an overly broad branch |
| Exclude one request type | `NegatedRequestMatcher` | Negative space easily covers unexpected new routes |
| Truly special path regex | `RegexRequestMatcher` | Regex anchoring, encoding, and runtime normalization |
| Dispatcher type | `dispatcherTypeMatchers` in DSL | `REQUEST`, `ERROR`, `FORWARD`... |
| Query/header changing feature mode | Custom lambda or class | Cross-check against how the controller parses input |
| Checking role, tenant, owner | `AuthorizationManager` and domain policy | Never treat self-asserted headers/queries as proof of permission |

Since Spring Security 6.5, `PathPatternRequestMatcher` is the migration target for legacy matchers. Spring Security 7 no longer supports `AntPathRequestMatcher` and `MvcRequestMatcher` as previous lines did. When borrowing code from older docs, check dependency versions to avoid wrong assumptions about behavior.

For a sensitive capability, a dedicated path + method is usually easier to test and review than a custom matcher depending on multiple query/header signals. Before going custom, have a clear reason why built-in matchers cannot express the request set.

## 5. Criteria for a Safe Custom Matcher

A matcher at a security boundary should be:

1. **Exact scope:** does not catch other sensitive routes merely via a shared substring.
2. **Restricted to exact HTTP methods:** public GET must not imply public DELETE.
3. **Deterministic:** the same normalized request always yields the same result.
4. **Side-effect-free:** `matches` never writes data, sends emails, mutates sessions, or triggers commands.
5. **Never uses client input as permission proof:** an `X-Role: ADMIN` header is untrusted text.
6. **No DB/network calls to pick chains:** owner/tenant checks belong in managers/domain; an infrastructure failure must never turn into `match=false` and fall into a weaker policy.
7. **Not shadowed by broad rules:** custom matchers run before broader covering matchers whenever required permissions differ.
8. **Conservative fallback:** if a custom matcher misses a variant, the sensitive endpoint must not be opened by an overly broad `permitAll` or `authenticated`.
9. **Matches servlet topology:** accounts for context root, servlet prefix, and reverse-proxy rewrites.
10. **Backed by test evidence:** matcher unit tests, MockMvc/Servlet integration tests, and a URL × method × actor coverage matrix.

Especially distinguish two conclusions: "the request does not belong to this group" and "the request is denied." `matches == false` is the first conclusion; it is not automatically equivalent to DENY.

## 6. Specific Rules Before General Rules

**Wrong** configuration:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/reports/**").authenticated()
    .requestMatchers(previewMatcher)
        .hasAuthority("reports:preview")
    .anyRequest().denyAll()
);
```

Every preview request under `/api/reports/**` already matches the first `authenticated()` rule. Any regular logged-in user passes the HTTP check, and the preview rule has no effect.

Reversing the order is necessary:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(previewMatcher)
        .hasAuthority("reports:preview")
    .requestMatchers("/api/reports/**")
        .hasAuthority("reports:read")
    .anyRequest().denyAll()
);
```

However, if preview **must require both read and preview permissions**, `reports:preview` alone is insufficient. Use a composite authorization manager or suitable policy. Moreover, if the preview matcher misses an input variant that the controller still treats as preview, the `reports:read` fallback is also insufficient; unify the request contract or keep a guard in the service.

**Do not try to make a custom matcher "hard to bypass" by flipping everything to `denyAll` and opening a few overly broad exceptions.** It is better to model capabilities, routes, and permissions completely with an explicit fallback.

## 7. Spring Security 6.5+ Example: Custom Matcher and Combined Permissions

Suppose endpoint GET `/api/reports/{id}` has `?view=preview` as an extra mode. Build the preview matcher as an AND of path/method and query:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
import org.springframework.security.web.util.matcher.AndRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

@Configuration
public class ReportSecurityConfiguration {

    @Bean
    SecurityFilterChain reportChain(HttpSecurity http) throws Exception {
        var paths = PathPatternRequestMatcher.withDefaults();

        RequestMatcher readReport =
            paths.matcher(HttpMethod.GET, "/api/reports/{id}");

        RequestMatcher previewReport = new AndRequestMatcher(
            readReport,
            request -> "preview".equals(request.getParameter("view"))
        );

        AuthorizationManager<RequestAuthorizationContext> readAndPreview =
            AuthorizationManagers.allOf(
                AuthorityAuthorizationManager
                    .<RequestAuthorizationContext>hasAuthority("reports:read"),
                AuthorityAuthorizationManager
                    .<RequestAuthorizationContext>hasAuthority("reports:preview")
            );

        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(previewReport).access(readAndPreview)
            .requestMatchers(readReport).hasAuthority("reports:read")
            .anyRequest().denyAll()
        );

        return http.build();
    }
}
```

**This is a Spring configuration snippet, not a standalone `javac` program.** It omits specific authentication mechanisms (JWT/session/form), controllers, CSRF, resource policies, or error handling.

Explanation:
- `PathPatternRequestMatcher` restricts GET to the report path with a single ID segment.
- `AndRequestMatcher` additionally classifies preview mode.
- `AuthorizationManagers.allOf` requires **both authorities**, not OR.
- The narrow matcher precedes the general read matcher.
- `anyRequest().denyAll()` rejects unlisted requests **within the current chain**.

**Important limitation:** the controller might handle aliases like `view=PREVIEW`, duplicate parameters, or an `Accept` header differently from the custom matcher. If any variant triggers preview while the matcher misses it, a user with only `reports:read` may hit the general rule. For sensitive capabilities, align the request parser and add service checks or use a dedicated URL.

## 8. Dedicated Routes Are Often Better Than Sensitive Query Conditions

Instead of one multi-mode endpoint:

```text
GET /api/reports/{id}?view=preview
GET /api/reports/{id}?view=normal
```

consider:

```text
GET  /api/reports/{id}          -> reports:read
GET  /api/reports/{id}/preview  -> reports:read + reports:preview
POST /api/reports/{id}/export   -> reports:read + reports:export
```

Benefits:
- Path/method matching is straightforward to prove.
- No disagreement over duplicate/default/case-variant queries.
- CI can maintain dedicated tests per operation.
- API gateways and logs clearly distinguish capabilities.
- Adding a new mode is easier to review.
- Domain policies receive actor/resource and check tenant/owner uniformly.

Splitting every query into a separate URL is not mandatory; however, when a query or header changes the authorization level, routing clarity is a major security advantage.

## 9. Writing a RequestMatcher Class That Must Return MatchResult

If you need to preserve the `{id}` path variable for a downstream manager, write a concrete class:

```java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpMethod;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

public final class PreviewReportMatcher implements RequestMatcher {

    private final RequestMatcher reportGet =
        PathPatternRequestMatcher.withDefaults()
            .matcher(HttpMethod.GET, "/api/reports/{id}");

    @Override
    public boolean matches(HttpServletRequest request) {
        return matcher(request).isMatch();
    }

    @Override
    public MatchResult matcher(HttpServletRequest request) {
        MatchResult pathResult = reportGet.matcher(request);

        if (!pathResult.isMatch()) {
            return MatchResult.notMatch();
        }
        if (!"preview".equals(request.getParameter("view"))) {
            return MatchResult.notMatch();
        }
        return MatchResult.match(pathResult.getVariables());
    }
}
```

This is an integration Java class **requiring Spring Security/Jakarta Servlet dependencies** and only valid on 6.5+ with `PathPatternRequestMatcher`; it does not run on standalone JDK. It only determines matching, never deciding whether the actor is authorized.

Notes:
- `reportGet.matcher(request)` obtains `MatchResult` and path variables if provided by the library.
- `matches` delegates to `matcher` for a single consistent result. Avoid circular recursion when overriding.
- `MatchResult.match(pathResult.getVariables())` preserves the `id` variable.
- `getParameter("view")` may not capture every way the controller triggers preview; test thoroughly.
- The `id` variable remains **URL input**, not a verified authorized resource.
- If policy needs to load the document/report, use a manager or domain service within a trusted scope.

A matcher class can be unit-tested independently of Authentication, while the manager/policy is tested across actors and objects.

## 10. Mistake: Putting Permissions Inside matches() Logic

**Unsafe** example:

```java
RequestMatcher adminArea = request ->
    "/api/admin".equals(request.getHeader("X-Role"));
```

Headers are client-controlled data. A client can send any value; it cannot prove the user is an admin. Worse, the matcher may fail to match and let the request drop into a weak fallback, causing a bypass.

Another flawed pattern:

```java
RequestMatcher ownDocument = request ->
    request.getParameter("ownerId").equals(
        request.getParameter("currentUserId"));
```

Both values can be set by the client, completely unbound from a trusted principal or DB data. The right way:
1. Matchers identify the route/method.
2. Authentication supplies the verified actor ID.
3. Domain service loads the tenant-scoped object from a trusted data source.
4. Policy verifies owner/grant/status before reading or writing.

**Never query the DB inside a matcher just to check ownership.** That mixes rule selection with domain decisions, is hard to reuse, and easily fails open if an I/O error returns `false`. A custom `AuthorizationManager` is the right extension point when complex decisions are needed in the authorization layer.

## 11. Request Conditions Prone to Matcher-Controller Drift

Suppose the controller supports multiple input forms:

```http
GET /api/reports/42?view=preview
GET /api/reports/42?view=PREVIEW
GET /api/reports/42?view=preview&view=normal
GET /api/reports/42?view=normal&view=preview
GET /api/reports/42?view=preview%20
GET /api/reports/42
Accept: application/vnd.example.preview+json
```

Verify:
- Does the matcher read `getParameter` or `getParameterValues`? What does the controller use?
- How are empty, whitespace, and differing-case values handled?
- For duplicate queries, is first, last, multi-value, or rejection applied?
- Do `Accept`/`Content-Type` headers alter sensitive responses?
- Can a request omitting `view` still return preview by default?
- Do the reverse proxy or Servlet container normalize/URL-decode differently?

**Do not assert that all variants above must match preview.** Results must follow the application contract, yet **every path that actually triggers the preview capability must be bound by the same policy**.

If parsing cannot be unified, reject ambiguous requests and design separate routes. Never let filter decoding diverge from controller decoding.

## 12. And, Or, and Negated: Combining Scopes, Not Combining Permissions

- `AndRequestMatcher(A,B)`: true only when A **and** B match.
- `OrRequestMatcher(A,B)`: true when A **or** B matches.
- `NegatedRequestMatcher(A)`: true when A does not match.

Example:

```java
RequestMatcher preview = new AndRequestMatcher(
    reportGet,
    request -> "preview".equals(request.getParameter("view"))
);
```

Here AND applies to **request conditions**. To require both `reports:read` and `reports:preview`, use `AuthorizationManagers.allOf(...)` or an equivalent policy. Using `hasAnyAuthority("reports:read","reports:preview")` is an OR and lets a user with only one permission pass.

`NegatedRequestMatcher` requires extra caution: "everything except /public" is a huge set that changes whenever the team adds routes. Use negation only when exclusion rules are proven and paired with a strict fallback; never use it as a default for admin authorization.

## 13. Fallback Chains and the Risk of Having No SecurityFilterChain

Only an API chain:

```java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        );
    return http.build();
}
```

Then `GET /internal/metrics` does not match `/api/**`. If the app has no other chain, that request may go unprotected by Spring Security. Although `anyRequest().authenticated()` is present in the config, it **only** applies within the selected API chain.

Unscoped fallback chain:

```java
@Bean
@Order(2)
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .anyRequest().denyAll()
    );
    return http.build();
}
```

This is a directional snippet; full beans, authentication/CSRF, and real routes must be configured. In apps with a public website, specific public rules may precede `denyAll`. Crucially, the fallback **must not** use a narrow path matcher that creates coverage gaps.

**Chain order:** if an `/api/**` chain sits ahead of an `/api/admin/**` chain, the admin chain may never be chosen for admin URLs. Fix: narrow chains before broad chains, or enforce strong admin rules inside the shared API chain. Chain selection affects **all filters**, not just authorization rules.

## 14. Servlet Path, Context Root, and Proxy Rewrites

A request might have:

```text
External URL     https://example.com/portal/mvc/api/reports/42
Context root     /portal
Servlet path     /mvc
MVC mapping      /api/reports/42
App-relative     /mvc/api/reports/42
```

`PathPatternRequestMatcher` in 6.5+ typically uses patterns excluding the context root while accounting for the servlet prefix. For instance:

```java
var mvc = PathPatternRequestMatcher.withDefaults()
    .basePath("/mvc");

RequestMatcher readReport =
    mvc.matcher(HttpMethod.GET, "/api/reports/{id}");
```

If a custom matcher manually uses `request.getRequestURI().startsWith("/api/")`, it can fail when `requestURI` contains `/portal/mvc`. Conversely, hardcoding an external `/gateway` prefix can fail once the proxy rewrites it.

Inspect runtime requests: `contextPath`, `servletPath`, `pathInfo`, `requestURI`, framework parser, and proxy rewrites. Run tests against deployments matching real configuration rather than guessing from the browser URL.

## 15. Be Careful with GET/HEAD/POST/PATCH/DELETE/OPTIONS

One path can map completely different operations. If a custom matcher inspects only the path:

```java
RequestMatcher bad = request ->
    request.getRequestURI().contains("/api/reports/");
```

then `hasAuthority("reports:read")` can apply even to delete/export endpoints. This is a missing-method bug, and `contains` also matches unintended URLs.

Use method-specific matchers:

```java
var paths = PathPatternRequestMatcher.withDefaults();

RequestMatcher read =
    paths.matcher(HttpMethod.GET, "/api/reports/{id}");

RequestMatcher delete =
    paths.matcher(HttpMethod.DELETE, "/api/reports/{id}");

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(delete).hasAuthority("reports:delete")
    .requestMatchers(read).hasAuthority("reports:read")
    .anyRequest().denyAll()
);
```

If controllers automatically support HEAD via GET, test HTTP HEAD. OPTIONS CORS preflight should use standard CORS configuration, never loosening `permitAll("/api/**")` for all methods just to silence browser errors. For cookie/session POST/PATCH, CSRF tests must send valid tokens when the goal is verifying permissions, avoiding CSRF 403s masking authorization errors.

## 16. Dispatcher Types and Requests with the Same URL but Different Flows

An HTTP request can pass through `REQUEST`, `FORWARD`, `ERROR`, or `ASYNC` dispatches depending on Servlet/runtime. `AuthorizationFilter` may inspect these dispatches depending on configuration. For example, a controller throws an exception and the container dispatches to `/error`; a deny on an ERROR dispatch can alter the response from the original error.

Spring Security allows dispatcher-type rules per policy:

```java
import static jakarta.servlet.DispatcherType.ERROR;
import static jakarta.servlet.DispatcherType.FORWARD;

http.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(ERROR, FORWARD).permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
```

This is only one architectural choice, **not a recommendation to open all dispatches unconditionally**. If the app forwards to sensitive endpoints, verify the real execution path and never allow bypassing permission gates. For custom matchers, dispatcher type is one dimension of requests to test.

## 17. Endpoint Inventory Is Not Just @GetMapping

An application's surface also includes:
- MVC controller mappings with class-level prefixes and GET/POST/PUT/PATCH/DELETE.
- Other servlets besides `DispatcherServlet`, e.g., legacy/admin/upload.
- Spring Boot Actuator or a separate management port/context.
- OAuth2 login callbacks, login/logout, error handling, and framework endpoints.
- GraphQL endpoints `/graphql`, where one URL hosts many operations and field-level policies.
- WebSocket handshakes, with separate message/channel authorization.
- Static resources and file downloads; avoid serving private data as static content.
- Export/PDF, signed URLs, and bulk/batch operations.
- Reverse proxy routes, gateway rewrites, or aliases.
- Custom filters that may handle and respond before controllers.
- Internal endpoints like `/internal/**`.

Therefore, scanning only one set of controllers does not prove the entire HTTP surface is protected. Especially if the management server uses a separate port, MockMvc tests on the main app do not verify security on the management port.

## 18. Coverage Matrix for a Real Application

| Endpoint or group | Method | Chain | Matcher/rule | Minimum permission | Domain policy | Negative test |
| --- | --- | --- | --- | --- | --- | --- |
| `/api/public/info` | GET | API/web | Public path GET | Public | No private data leak | POST not automatically public |
| `/api/reports/{id}` | GET | API | Read matcher | `reports:read` | Tenant + read grant | Missing read DENY |
| `/api/reports/{id}?view=preview` | GET | API | Narrow custom preview | Read + preview | Tenant + preview grant | Read-only DENY |
| `/api/reports/{id}/export` | POST | API | Export matcher | `reports:export` and policy | Audit, quota, owner | Read-only DENY |
| `/api/admin/users` | GET/PATCH | Admin/API | Admin matcher | `ROLE_ADMIN` | Admin scope/tenant | Regular user DENY |
| `/internal/metrics` | GET | Fallback/management | Ops matcher | Ops/private policy | Do not expose config | Anonymous DENY |
| `/error` | ERROR | Web/fallback | Dispatcher policy | Per error contract | Do not leak secrets | Original error not wrongly masked |

Every row must be **verified by tests running against the application**, not just assumed from design docs. For private resources, beyond HTTP rules, verify that a user with the right authority is still denied for objects in another tenant.

A pragmatic definition of "sufficient coverage":

```text
For every request in the application's private surface:
  1. A matching SecurityFilterChain exists.
  2. The chosen chain has the right rule/policy.
  3. The first matching rule is no weaker than functional requirements.
  4. The actor comes from trusted authentication.
  5. The actual resource is checked for owner/tenant/ACL/status.
  6. Commands with side effects run only after policy ALLOW.
```

A finite test suite cannot exhaustively prove every URL variant. Yet an inventory matrix + positive/negative tests + servlet integration + gateway review sharply reduces the risk of gaps.

## 19. Standalone Java 17+: Wrong Rule, Right Rule, and Uncovered Chain

The plain Java example below **simulates** first-match, combined permissions, and a fallback chain. It does not implement Servlet, Spring Security, or `PathPatternParser`; requests and actors are pre-trusted test data.

Save file `MatcherCoverageDemo.java`:

```java
import java.util.List;
import java.util.Set;
import java.util.function.Predicate;

public class MatcherCoverageDemo {
    record Request(String method, String path, String view) {}
    record Actor(boolean authenticated, Set<String> authorities) {}
    record Rule(String name, Predicate<Request> matcher,
                String requirement) {}

    static boolean allowed(Actor actor, String requirement) {
        if (requirement.equals("DENY")) return false;
        if (requirement.equals("READ")) {
            return actor.authenticated()
                && actor.authorities().contains("reports:read");
        }
        if (requirement.equals("READ_AND_PREVIEW")) {
            return actor.authenticated()
                && actor.authorities().contains("reports:read")
                && actor.authorities().contains("reports:preview");
        }
        throw new IllegalArgumentException(requirement);
    }

    static String decide(List<Rule> rules, Actor actor,
                         Request request) {
        for (Rule rule : rules) {
            if (rule.matcher().test(request)) {
                return (allowed(actor, rule.requirement())
                    ? "ALLOW" : "DENY") + " via " + rule.name();
            }
        }
        return "DENY via no-rule";
    }

    static boolean reportGet(Request request) {
        return request.method().equals("GET")
            && request.path().startsWith("/api/reports/");
    }

    static boolean previewGet(Request request) {
        return reportGet(request)
            && "preview".equals(request.view());
    }

    public static void main(String[] args) {
        Actor reader = new Actor(true, Set.of("reports:read"));
        Actor specialist = new Actor(true,
            Set.of("reports:read", "reports:preview"));

        Request preview = new Request(
            "GET", "/api/reports/42", "preview");
        Request normal = new Request(
            "GET", "/api/reports/42", "normal");
        Request write = new Request(
            "POST", "/api/reports/42", "normal");
        Request internal = new Request(
            "GET", "/internal/metrics", "");

        Rule general = new Rule(
            "general", MatcherCoverageDemo::reportGet, "READ");
        Rule special = new Rule(
            "preview", MatcherCoverageDemo::previewGet,
            "READ_AND_PREVIEW");
        Rule deny = new Rule(
            "api-fallback", r -> true, "DENY");

        List<Rule> wrong = List.of(general, special, deny);
        List<Rule> safe = List.of(special, general, deny);

        System.out.println("Wrong reader preview: "
            + decide(wrong, reader, preview));
        System.out.println("Safe reader preview: "
            + decide(safe, reader, preview));
        System.out.println("Safe specialist preview: "
            + decide(safe, specialist, preview));
        System.out.println("Safe reader normal: "
            + decide(safe, reader, normal));
        System.out.println("Safe reader POST: "
            + decide(safe, reader, write));

        boolean apiChain =
            internal.path().startsWith("/api/");
        System.out.println("Internal covered by API chain: "
            + apiChain);
        System.out.println("Internal without fallback chain: "
            + (apiChain ? "COVERED" : "NO_SECURITY_CHAIN"));
        System.out.println("Internal with fallback chain: "
            + (apiChain ? "COVERED" : "DENY"));
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac MatcherCoverageDemo.java
java MatcherCoverageDemo
```

**Exact** stdout:

```text
Wrong reader preview: ALLOW via general
Safe reader preview: DENY via preview
Safe specialist preview: ALLOW via preview
Safe reader normal: ALLOW via general
Safe reader POST: DENY via api-fallback
Internal covered by API chain: false
Internal without fallback chain: NO_SECURITY_CHAIN
Internal with fallback chain: DENY
```

Analysis:
1. The wrong order lets the general read rule allow preview before checking the stricter rule.
2. The right order denies a reader lacking preview permission.
3. The specialist holding both authorities passes the preview rule.
4. Normal report GET still requires read permission.
5. POST is not opened merely because GET on the same path allows reading.
6. `/internal/metrics` falls outside the simulated `/api/**` chain, demonstrating why a fallback chain is essential to protect all endpoints.

**Limitation:** `startsWith` in this program is a minimal simulation and does not handle servlet paths, URL encoding, regex, parser versions, or dispatches. Never reuse this function in place of library matchers in production.

## 20. Unit Testing RequestMatcher with MockHttpServletRequest

With compatible Spring Security + Spring Test, test a real matcher:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
import org.springframework.security.web.util.matcher.AndRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;
import static org.assertj.core.api.Assertions.assertThat;

class PreviewMatcherTest {
    private final RequestMatcher report =
        PathPatternRequestMatcher.withDefaults()
            .matcher(HttpMethod.GET, "/api/reports/{id}");

    private final RequestMatcher preview =
        new AndRequestMatcher(
            report,
            req -> "preview".equals(req.getParameter("view"))
        );

    @Test
    void matchesOnlyPreviewGet() {
        MockHttpServletRequest yes =
            new MockHttpServletRequest("GET", "/api/reports/42");
        yes.setServletPath("/api/reports/42");
        yes.setParameter("view", "preview");

        MockHttpServletRequest wrongMode =
            new MockHttpServletRequest("GET", "/api/reports/42");
        wrongMode.setServletPath("/api/reports/42");
        wrongMode.setParameter("view", "normal");

        MockHttpServletRequest wrongMethod =
            new MockHttpServletRequest("POST", "/api/reports/42");
        wrongMethod.setServletPath("/api/reports/42");
        wrongMethod.setParameter("view", "preview");

        assertThat(preview.matches(yes)).isTrue();
        assertThat(preview.matches(wrongMode)).isFalse();
        assertThat(preview.matches(wrongMethod)).isFalse();
    }
}
```

**This is a test snippet**, not standalone JDK. It requires `spring-security-web`, Spring Test, JUnit, and AssertJ at matching versions; `PathPatternRequestMatcher` may also require mock request paths configured according to your parser/version mechanism. When direct mocking does not fully simulate the Servlet pipeline, use `MockMvc`/embedded server to verify runtime behavior. Never conclude a production rule is right or wrong based solely on an improperly constructed mock path.

Custom matcher matrix:
- GET report with `view=preview` → MATCH.
- GET report with `view=normal` → NO MATCH.
- POST report with `view=preview` → NO MATCH.
- GET another path with `view=preview` → NO MATCH.
- GET missing `view` → per defined contract.
- GET with `view=PREVIEW`, duplicate params, or encoded values → must have an explicit decision and test.
- URL with servlet prefix or reverse-proxy rewrite → test on real topology.

Specifically, `matcher.matches() == false` only proves one rule was not picked; **you must also test that the fallback truly DENIES or demands the right permission**.

## 21. Integration Testing: Not Just 403, Prove the Blocking Point

Spring Security Test supports `MockMvc` and mock Authentications:

```java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@Test
void readerDeniedPreview() throws Exception {
    mvc.perform(get("/api/reports/42")
            .param("view", "preview")
            .with(user("alice").authorities(
                new SimpleGrantedAuthority("reports:read")
            )))
       .andExpect(status().isForbidden());
}

@Test
void specialistCanReadPreview() throws Exception {
    mvc.perform(get("/api/reports/42")
            .param("view", "preview")
            .with(user("alice").authorities(
                new SimpleGrantedAuthority("reports:read"),
                new SimpleGrantedAuthority("reports:preview")
            )))
       .andExpect(status().isOk());
}
```

These are integration snippets requiring `MockMvc`, JUnit, `SimpleGrantedAuthority`, `spring-security-test`, a controller with real handlers, fixtures, and policies permitting valid users. If no handler exists, you cannot prove the matcher from a 404 alone; if domain policy denies even the specialist, the 200 test cannot pass until proper fixtures are provided.

Control tests needed:
- Reader with only read → preview DENY, normal ALLOW.
- Specialist with both read and preview → preview ALLOW.
- User with only preview, lacking read → DENY.
- Anonymous → DENY on private report.
- POST/PATCH/DELETE with only read → DENY.
- User with right authority but different tenant/owner → domain DENY.
- URL outside API chain → fallback DENY if private.

**False positive:** a POST returning 403 due to a missing CSRF token does not prove the write rule. When testing write authorization in CSRF-enabled apps, build valid requests with `with(csrf())` and assert the target has no side effects when denied.

## 22. Dimensions to Fuzz / Property-Test

Commonly overlooked variants:
- Root path, sub-paths, trailing slash, and double slash.
- HTTP methods `GET/HEAD/POST/PUT/PATCH/DELETE/OPTIONS`.
- URL encoded/decoded characters, duplicate queries, and casing.
- Non-default `ContextPath` and `ServletPath`.
- `REQUEST/ERROR/FORWARD/ASYNC` dispatches.
- Multi-valued headers or differing media types.
- Reverse proxy rewrites/forwarded headers.
- Controller route aliases, legacy servlets, actuator/management paths.
- Export/download/bulk endpoints with stronger capabilities than read.
- Custom matchers returning false due to system errors or unusual inputs.

Desired properties:

```text
P1: Any request capable of triggering preview must require
    reports:read AND reports:preview.

P2: A write request must never be allowed merely by read permission.

P3: Every private endpoint must belong to a SecurityFilterChain.

P4: Any URL variant reaching the same sensitive handler
    must never receive a lower permission requirement.

P5: Failures in data policy verification must never become
    ALLOW or an unintentionally weak fallback.
```

Property tests are helpful for finding discrepancies between matchers and controllers, though they do not replace endpoint inventories and real-deployment testing. Even 100% code coverage of `matches` does not prove a system is free of URL bypasses.

## 23. Diagnosing an Endpoint That "Was Not Blocked"

When an under-privileged client gets through:

1. After reverse proxy/Servlet processing, what are the real `requestURI`, `contextPath`, `servletPath`, and `pathInfo`?
2. Which `SecurityFilterChain` did `FilterChainProxy` select? Did any chain match?
3. Does `securityMatcher` have the right servlet prefix and HTTP method?
4. Inside that chain, do custom `requestMatchers` match before broad rules?
5. Does the request trigger functionality via an alias/header/query that the matcher did not check?
6. Does the selected rule require the right authority? Was `hasAnyAuthority` confused with AND?
7. Did Authentication obtain authorities from a trusted source, or did the user self-assert via input?
8. If HTTP passed, does the service check real tenant/owner/ACL/status?
9. If the response is 403, could it be CSRF or another handler rather than the custom matcher?
10. Does any custom filter, GraphQL resolver, scheduler, or non-HTTP entry point bypass this checkpoint?

You can enable Spring Security logging in dev/test to observe chain/rule selection; never log raw tokens, passwords, full private responses, or sensitive info. Audits should record normalized actor ID, action, resource ID, decision, and safe reason codes.

## 24. Common Mistakes and Fixes

| Mistake | Consequence | How to handle |
| --- | --- | --- |
| Using `contains("/admin")` | Wrong or overly broad match | Tested PathPattern/regex |
| Forgetting HttpMethod | Read permission applies to write too | Method-specific matcher |
| Placing custom matcher first but fallback is `permitAll` | Unmatched variants can bypass | Strict fallback, guard in service |
| Placing narrow matcher after `/api/**.authenticated()` | Narrow rule is shadowed | First-match ordering |
| Granting permissions from self-asserted query/header | Privilege escalation | Authentication + manager/policy |
| Running SQL in `matches` and catching errors to return false | Falls into weaker rule/chain | Separate authorization and fail closed |
| Narrow `securityMatcher` without fallback | Endpoints outside chain go unprotected | Fallback SecurityFilterChain |
| General API chain placed before admin chain | Admin chain never applies | Narrow chain first or strong rule in shared chain |
| Misunderstanding context/servlet path | Rules miss real URLs | Base path and integration tests |
| Testing only that admin has access | Misses regular users sneaking in | Negative tests with low roles |
| Testing 403 without CSRF | False positive | Valid requests and verify exact deny point |
| Scanning only MVC controllers | Misses actuator, framework, other servlets | Runtime and gateway inventory |
| Missing object policy | IDOR/BOLA even when URL is protected | Tenant/owner/ACL in use case |
| Overly broad `web.ignoring()` | Missing security filters/headers | Prefer `permitAll` if truly public |

## 25. Checklist Before Merging a Custom RequestMatcher

1. What scope does the requirement cover: method, path, query/header, dispatcher, and servlet context?
2. Is the matcher used for chain selection or rule selection? What is the corresponding order?
3. Are there real URLs matching no chain? Does the fallback chain protect all private routes?
4. Does any broad rule above shadow the narrow rule?
5. When the custom matcher returns false, which rule receives the request and are its permissions strict enough?
6. Is any client-controlled input treated as proof of authority/ownership?
7. Can a sensitive capability be triggered through a different request interpretation?
8. Does a policy requiring two permissions use AND instead of OR?
9. Are real resource permissions checked in the service?
10. Are there tests with other methods, duplicate queries, encoded paths, servlet prefixes, and dispatchers?
11. Are there negative tests for insufficient permissions, cross-tenant access, and locked resources?
12. Are there tests ensuring denied commands produce zero side effects?
13. Are there integration tests on a runtime matching production and the chosen version?
14. Can you observe which chain/rule denied without leaking tokens/secrets?
15. When adding a new route, are the inventory and tests updated in the same pull request?

### Self-Check Questions

**1.** A custom matcher for `view=preview` returns false, yet the controller still returns preview via another alias. Will the request automatically DENY?  
→ **No.** It may fall through to a rule below; update the predicate, input contract, and add a guard in the use case.

**2.** A `securityMatcher("/api/**")` chain has `anyRequest().denyAll()`. Does that chain deny `/internal/metrics`?  
→ **No**, because the chain is not selected. Another/fallback chain is required.

**3.** Does `AndRequestMatcher(reportPath, previewParam)` already require both authorities?  
→ **No.** That is only an AND of request conditions. Permissions require `AuthorizationManagers.allOf` or an equivalent policy.

**4.** Does testing only `previewMatcher.matches(request)==false` on POST prove POST cannot reach the controller?  
→ **No.** You must verify the next selected rule, fallback, and runtime handler.

**5.** A POST test returns 403 without a CSRF token; does it prove DELETE/POST permissions work?  
→ **No.** The error may be due to CSRF; use a valid request and control tests.

**6.** A URL has `/portal` as context root and `/mvc` as servlet path. For PathPattern, should the pattern include the context root?  
→ **No**. Patterns are typically app-relative without context root; they may need servlet prefix or `basePath("/mvc")`.

**7.** A user has `reports:read` yet report 42 belongs to another tenant. If the HTTP matcher allows it, can they read it?  
→ **No**. A domain policy on the actual resource is required.

**8.** Why are MockMvc tests for one rule still insufficient to guarantee no endpoints are missed?  
→ Other servlets, management ports, or framework routes may exist; you need an entry-point inventory, chain coverage, and real-stack testing.

## Conclusion

A custom `RequestMatcher` only decides **which set a request belongs to**. Protecting endpoints requires at least three proofs: **the right chain is selected**, **the first matching rule/manager enforces proper least privilege**, and **domain policy checks the actor against the real resource**. Reduce vulnerabilities by preferring standard path/method matchers, keeping custom predicates short and deterministic, using conservative fallbacks, adding negative tests, and maintaining an endpoint inventory as the system evolves.

## Official References

- [Spring Security 6.5 — RequestMatcher API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/util/matcher/RequestMatcher.html) — `matches`, `matcher`, and `MatchResult`.
- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html) — custom matchers, first-match, `AuthorizationManager`.
- [Spring Security 6.5 — Java Configuration: securityMatcher vs requestMatchers](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html) — chain selection and fallback.
- [Spring Security 6.5 — AuthorizationManagers Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManagers.html) — `allOf` and `anyOf`.
- [Spring Security 6.5 — PathPatternRequestMatcher Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/servlet/util/matcher/PathPatternRequestMatcher.html).
- [Spring Security 6.5 — MockMvc Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html).
- [Spring Security 6.5 — Servlet Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html).
