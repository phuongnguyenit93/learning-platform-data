# Alternative Paths, Other HTTP Methods, and Request Normalization Bugs

## 1. Why Is This an Authorization Vulnerability?

Spring Security can make access decisions based on **path and HTTP method**, while Spring MVC, the servlet container, or a reverse proxy must also interpret that same request to select a controller. If those layers interpret the path differently, or a rule only checks GET while an endpoint can handle DELETE/PATCH through another route, requests can reach sensitive functions under a weaker authorization rule than intended.

Consider a document management API:

| Actual Operation | Expected Endpoint | Minimum Permission |
| --- | --- | --- |
| Read document 42 | GET /api/documents/42 | DOC_READ |
| Read metadata via HEAD if supported | HEAD /api/documents/42 | DOC_READ |
| Edit document 42 | PATCH /api/documents/42 | DOC_EDIT |
| Delete document 42 | DELETE /api/documents/42 | DOC_DELETE |

A weak configuration might only check a path string or let unmatched requests fall into a `permitAll` branch. Then someone with only `DOC_READ` could reach the delete operation, or a path considered equivalent by the backend might fail to match the protection rule. Not every URL variant is accepted by the container/Spring; **a vulnerability exists only when a request actually reaches a sensitive handler without undergoing the corresponding permission check**.

Objectives of this lesson:

1. Identify forms of alternative paths, HTTP methods, and normalization differences that can create gaps between **security matchers** and **handler mappings**.
2. Understand built-in defenses (especially `FilterChainProxy` and `StrictHttpFirewall`), their limits, and how configuration can accidentally strip away protection.
3. Design authorization rules distinguishing **resource + action + HTTP method**, apply deny by default, and test requests passing through the entire filter chain and real proxy.
4. Distinguish **requests rejected at the firewall**, **no matching handler**, and **denied due to lacking permission**; HTTP status codes may vary, yet zero unauthorized side effects may occur.

## 2. Which Layers Does a Request Pass Through?

~~~text
Client sends request-target, e.g.:
  PATCH /gateway/api/documents/42
           |
           v
CDN / load balancer / reverse proxy
  (may rewrite prefix, redirect, decode, or block request)
           |
           v
Servlet container
  (requestURI, contextPath, servletPath, pathInfo, queryString)
           |
           v
Spring Security: FilterChainProxy + HttpFirewall
  -> selects SecurityFilterChain via securityMatcher
  -> selects authorizeHttpRequests rule via requestMatcher
           |
           v
Spring MVC: DispatcherServlet + HandlerMapping
  -> selects controller/method + path variables
           |
           v
Service + object/tenant permission check
~~~

Two mandatory questions to answer when auditing a system:

- **Which component interprets what path and method this request represents for authorization?**
- **Which component interprets what path and method this request represents for executing business logic?**

These representations must not be assumed identical:

| Property / Layer | Meaning and Risk |
| --- | --- |
| HTTP request-target | Raw string sent by client; may contain percent-encoding, dots, semicolons |
| Reverse proxy | May strip/add prefixes or rewrite URLs before Java receives them; upstream rules affect outcomes |
| `HttpServletRequest.getRequestURI()` | Includes context path and URI part per servlet contract; container decoding behavior must be verified |
| `getContextPath()`, `getServletPath()`, `getPathInfo()` | Components used to locate the servlet; interpretation differs by container/mapping |
| `getQueryString()` | Part after `?`, **not** part of the path automatically checked by `requestMatchers(String)` |
| `HttpFirewall` + `RequestMatcher` | Can reject abnormal requests, wrap requests, and normalize parts used for matching |
| Spring MVC `HandlerMapping` | Has its own rules for route matching, path variables, method mapping, and parsing config |

Spring Security uses `FilterChainProxy` with `HttpFirewall` to narrow discrepancies between containers and matchers. By default, **StrictHttpFirewall** rejects many non-normalized or dangerous URLs, as well as HTTP methods outside its allowlist. Suspicious requests may be rejected before reaching `AuthorizationManager`/controllers. Never treat adding multiple manual normalization passes as equivalent to a firewall: one layer may decode once and the next decode again, leading to different meanings. If a special URL is legitimately required, clearly determine how the proxy, container, firewall, and MVC behave before changing configuration.

## 3. Alternative Paths: Easily Overlooked Cases

The paths below are **suggested test cases**, not a claim that Spring Security lets them through by default. Each case must be observed against the real environment.

| Variant | Example for document 42 | Risk to Verify |
| --- | --- | --- |
| Trailing slash | `/api/documents/42/` | Router and security matcher may differ on trailing slashes, especially after migrations or custom mappings |
| Multiple slashes | `/api//documents/42` | Proxy/container may collapse slashes while a raw-string rule does not |
| `.` or `..` segments | `/api/tmp/../documents/42` | One layer resolves dot-segments while another matches before normalization |
| URL-encoded characters | `/api/documents/%34%32` | Single decode resolves to ID 42; verify matcher and handler identify it identically |
| Encoded slash | `/api/documents%2F42` | Segment splitting before/after decode may differ; default firewall typically blocks |
| Double encoding | `/api/documents/%2534%2532` | Multiple decodes can alter meaning; never keep decoding manually to “fix” URLs |
| Semicolon / matrix params | `/api/documents/42;view=full` | Servlet, firewall, and MVC may strip or handle path parameters differently |
| Upper / lower case | `/API/documents/42` | Case sensitivity may differ between route, proxy, or custom matcher |
| Alias paths | `/v1/documents/42` or `/internal/documents/42` | Multiple URLs reach one business action while only one URL has a rule |
| Suffix / extension | `/api/documents/42.json` | Route/content negotiation or legacy routes may map to the same data |
| Context/servlet prefix | `/app/api/documents/42` | Confusing context path, servlet path, and patterns shifts protection scope |
| Proxy rewrite | `/gateway/documents/42` rewritten to `/api/documents/42` | Edge protection and in-app protection see different paths |
| Internal forward | A public endpoint forwards to a protected resource | Must check target dispatch/handler path, not just initial request path |
| Query altering action/object | `GET /api/documents/42?export=secret` | Path matchers do not inspect queries; business action may be more sensitive than ordinary GET |

**Decision checkpoint:** for each variant, record (a) what the proxy forwards, (b) whether the firewall accepts or rejects, (c) which `SecurityFilterChain` and rule matches, (d) which controller runs, and (e) where document/tenant permissions are checked. Do not infer a vulnerability merely because a URL looks “weird”.

### 3.1. Semicolons, Encoding, and Multiple Decodes

Spring Security documents risks from path parameters and differences in `servletPath`/`pathInfo` across servlet containers. The default `StrictHttpFirewall` is an important defense against unnormalized URLs, semicolons, encoded slashes, and many suspicious character patterns. If the application needs **matrix variables**, enabling `setAllowSemicolon(true)` is a security-impacting change; add tests cross-checking routes and permissions rather than merely adding a firewall exception so requests go through.

Similarly, never run `URLDecoder.decode` across the full path and match prefixes manually. `URLDecoder` is designed for `form-urlencoded` data, handles `+` signs differently from paths, and easily introduces an inconsistent extra decode pass. Decisions must rely on path representations **defined and verified by the framework**, where ambiguous or invalid requests are rejected.

### 3.2. Aliases and Rewrites Are Sometimes More Dangerous Than Encoded Payloads

Suppose both `/api/documents/{id}` and `/legacy/documents/{id}` call the delete service. If only `/api/**` belongs to a narrow `SecurityFilterChain`, the `/legacy/**` alias may fall into another chain or match no chain at all, depending on configuration. Likewise, a rule covering `/api/**` does not protect a separate servlet under `/admin-api/**`.

Inventory all entry points to sensitive business operations: controller mappings, legacy routes, versioning, proxy rewrites, secondary servlets, actuator/custom endpoints, and internal forwards. When using multiple `SecurityFilterChain`s, include a **catch-all chain for the remainder** and verify chain priority order. Within a chain, `authorizeHttpRequests` rules are ordered, **first matching rule wins**; a broad `permitAll` placed before restrictive rules shadows the rules below.

## 4. HTTP Methods and Method Conversion

One path does not uniquely represent one action. Examine each method and real mapping rather than applying read permissions to all requests sharing a URL.

| Method / Scenario | What to Check |
| --- | --- |
| GET | Read permission; GET endpoints should not create sensitive data mutations |
| HEAD | Spring MVC may serve HEAD via GET handlers; clearly define read permission and verify no side effects |
| POST | Create/execute action permission; never substitute GET permission |
| PUT, PATCH | Edit permission; sometimes the two methods hit different handlers |
| DELETE | Delete permission; test with a read-only principal to prove it is blocked |
| OPTIONS | CORS preflight checks cross-origin capability, **not** permission to perform the target operation |
| TRACE, CONNECT, unknown methods | Rarely needed in APIs; `StrictHttpFirewall` has a default method allowlist, do not open everything |
| Form POST with `_method=DELETE` | Takes effect only when `HiddenHttpMethodFilter` is enabled and runs; verify the method Security sees |
| `X-HTTP-Method-Override` or similar headers | Not automatic in all apps; if supported by a gateway/custom filter, it is a method-switching path that must be authorized and tested |

Spring Boot 3.3 has property `spring.mvc.hiddenmethod.filter.enabled` defaulting to `false`. If you enable `HiddenHttpMethodFilter` to support HTML forms, verify filter ordering so the **effective method is resolved before authorization evaluation**, and support only the chosen override styles. Never assume an arbitrary header always takes effect or is always ignored. If a proxy can rewrite methods, test both in front of and behind the proxy.

For CORS, preflight OPTIONS typically carry no auth cookies, so handle CORS in the proper order (Spring Security has built-in `cors` support). Do not fix preflight errors by blindly opening all OPTIONS on every route; OPTIONS negotiates cross-origin access while **actual GET/POST/PATCH/DELETE requests must still pass authorization**. CORS constrains browser behavior in cross-origin contexts, not API authentication/authorization.

**CSRF is a separate control from authorization.** When testing POST/PUT/PATCH/DELETE with CSRF protection enabled, a missing token can block the request before permission rules run. Supply valid CSRF in tests intentionally checking permissions; conversely, test CSRF as a separate case. Never use “403 from missing CSRF” as proof that the `DOC_DELETE` rule is right.

## 5. Designing Clear Rules in Spring Security 6.x

For Servlet/Spring Boot 3.x applications, model permissions by **method and route**. The snippet below is configuration code inside a Spring Security app (requiring corresponding dependencies, `Authentication`, and controllers), not a standalone Java program run with plain `javac`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class DocumentSecurityConfig {

    @Bean
    SecurityFilterChain documentSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            // Each action has its own authority.
            .requestMatchers(HttpMethod.GET,
                "/api/documents", "/api/documents/{id}")
                .hasAuthority("DOC_READ")
            .requestMatchers(HttpMethod.HEAD,
                "/api/documents", "/api/documents/{id}")
                .hasAuthority("DOC_READ")
            .requestMatchers(HttpMethod.POST, "/api/documents")
                .hasAuthority("DOC_CREATE")
            .requestMatchers(HttpMethod.PATCH, "/api/documents/{id}")
                .hasAuthority("DOC_EDIT")
            .requestMatchers(HttpMethod.DELETE, "/api/documents/{id}")
                .hasAuthority("DOC_DELETE")

            // Undeclared methods/routes are not opened automatically.
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
~~~

The example config permits only the listed methods/paths; if the product requires PUT, aliases, or public pages, declare explicit rules and test accordingly. Do not treat this snippet as a complete setup for authentication, CSRF, CORS, sessions, OAuth2, or multiple `SecurityFilterChain`s. In particular, if additional narrow chains use `securityMatcher`, verify **every entry point is covered**; an `anyRequest` rule in chain A does not mean requests not matching chain A are handled by chain A.

Note that matcher mechanics can differ depending on Spring Security version, presence of Spring MVC, servlet mappings, and how `RequestMatcher`s are constructed. With multiple servlets or custom paths, use matchers aligned with `servletPath` and test **matching the real route config**. Never mix homegrown Regex/Ant/MVC rules without proving they share the exact semantics of `HandlerMapping`. In multi-tenant systems or systems with per-document permissions, add controls at the **service/method layer** based on the loaded object (e.g., combining `@EnableMethodSecurity` and `@PreAuthorize`); a user with `DOC_READ` still has no right to view another tenant's document merely from matching a URL.

Accompanying principles:

- Prefer route/method allowlists; place broad/`anyRequest` rules last and choose `denyAll` or tight product-policy controls.
- Keep the default `StrictHttpFirewall` unless an analyzed and tested business need requires changing it.
- Do not use `web.ignoring` for dynamic APIs; for public content, consider `permitAll` so requests still traverse other security filters.
- Ensure proxies only trust `Forwarded`/`X-Forwarded-*` headers from trusted sources; never let clients dictate context path, host, or scheme in ways affecting security rules.
- If legitimate URL aliases exist, protect **every alias** with equivalent permissions, or normalize/route them to the same verified endpoint before entering the app.
- Never derive permissions from query strings, self-declared headers, manually concatenated paths, or client-sent “preferred methods”; use `Authentication`/`AuthorizationManager` and service-layer decisions.

## 6. Standalone Java 17+ Example: Clearly Seeing Overly Broad Rule Bugs

The following example has no Spring dependency; it simulates a **fixed** document path to compare two policies. `weakPolicy` intentionally contains a bug: applying `DOC_READ` to every method on the main path and allowing remaining paths by default. `strictPolicy` enforces rules by method, rejects other paths, and refuses override requests in this simple model. **Do not use `strictPolicy` as a URL normalizer for a real application**: Spring MVC/`HttpFirewall` must handle routing and parsing; the example only demonstrates writing permission checks and testing variants.

Save as **AuthorizationRouteDemo.java**:

~~~java
import java.util.Set;

public class AuthorizationRouteDemo {
    record Request(String method, String path, boolean overrideRequested) {}

    private static final String DOCUMENT_PATH = "/api/documents/42";

    // Counter-example: read permission applies to all methods, unknown paths open by default.
    static boolean weakPolicy(Request request, Set<String> authorities) {
        if (DOCUMENT_PATH.equals(request.path())) {
            return authorities.contains("DOC_READ");
        }
        return true;
    }

    // Test model for one fixed route: accepts only explicit methods and paths.
    static boolean strictPolicy(Request request, Set<String> authorities) {
        if (request == null || authorities == null
                || request.method() == null || request.path() == null
                || request.overrideRequested()
                || !DOCUMENT_PATH.equals(request.path())) {
            return false;
        }

        return switch (request.method()) {
            case "GET", "HEAD" -> authorities.contains("DOC_READ");
            case "PATCH" -> authorities.contains("DOC_EDIT");
            case "DELETE" -> authorities.contains("DOC_DELETE");
            default -> false;
        };
    }

    private static void check(String label, Request request,
                              Set<String> authorities,
                              boolean weakExpected, boolean strictExpected) {
        boolean weak = weakPolicy(request, authorities);
        boolean strict = strictPolicy(request, authorities);
        if (weak != weakExpected || strict != strictExpected) {
            throw new AssertionError(label + ": unexpected decision");
        }
        System.out.println(label + " | weak=" + result(weak)
                + " | strict=" + result(strict));
    }

    private static String result(boolean allowed) {
        return allowed ? "ALLOW" : "DENY";
    }

    public static void main(String[] args) {
        Set<String> reader = Set.of("DOC_READ");
        check("GET canonical", new Request("GET", DOCUMENT_PATH, false),
                reader, true, true);
        check("DELETE with read", new Request("DELETE", DOCUMENT_PATH, false),
                reader, true, false);
        check("POST with read", new Request("POST", DOCUMENT_PATH, false),
                reader, true, false);
        check("HEAD with read", new Request("HEAD", DOCUMENT_PATH, false),
                reader, true, true);
        check("trailing slash", new Request("GET", DOCUMENT_PATH + "/", false),
                reader, true, false);
        check("encoded digits", new Request("GET", "/api/documents/%34%32", false),
                reader, true, false);
        check("double slash", new Request("GET", "/api/documents//42", false),
                reader, true, false);
        check("dot segment", new Request("GET", "/api/tmp/../documents/42", false),
                reader, true, false);
        check("method override", new Request("GET", DOCUMENT_PATH, true),
                reader, true, false);
        check("PATCH with edit", new Request("PATCH", DOCUMENT_PATH, false),
                Set.of("DOC_EDIT"), false, true);
        check("DELETE with delete", new Request("DELETE", DOCUMENT_PATH, false),
                Set.of("DOC_DELETE"), false, true);
        check("TRACE with read", new Request("TRACE", DOCUMENT_PATH, false),
                reader, true, false);
        check("GET anonymous", new Request("GET", DOCUMENT_PATH, false),
                Set.of(), false, false);
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac --release 17 AuthorizationRouteDemo.java
java AuthorizationRouteDemo
~~~

Exact stdout when running the program:

~~~text
GET canonical | weak=ALLOW | strict=ALLOW
DELETE with read | weak=ALLOW | strict=DENY
POST with read | weak=ALLOW | strict=DENY
HEAD with read | weak=ALLOW | strict=ALLOW
trailing slash | weak=ALLOW | strict=DENY
encoded digits | weak=ALLOW | strict=DENY
double slash | weak=ALLOW | strict=DENY
dot segment | weak=ALLOW | strict=DENY
method override | weak=ALLOW | strict=DENY
PATCH with edit | weak=DENY | strict=ALLOW
DELETE with delete | weak=DENY | strict=ALLOW
TRACE with read | weak=ALLOW | strict=DENY
GET anonymous | weak=DENY | strict=DENY
~~~

Notes on interpretation:

- `weakPolicy` is an **intentionally unsafe counter-example**: DELETE with read permission still ALLOWs; an alternate path receives ALLOW via the default branch.
- `strictPolicy` assigns clear permissions per method with no permissive fallback. HEAD is granted read permission **as an illustrative choice**, not a requirement that every API must support HEAD.
- The `overrideRequested` variable is only a simulation flag: in real deployments, the system must choose **not to support method override** or use a controlled mechanism so every layer sees the same effective method. No standard HTTP API generates this flag automatically.
- `strict=DENY` for encoded/dot paths proves **the simulated rule rejects non-canonical strings**, not that real servlets or firewalls return the exact same HTTP code. A URL blocked with 400 or unmapped 404 can still be a safe outcome.
- The example only uses resource ID 42 to show the logic clearly. Real applications must handle path variables and permissions **per object/tenant**, never hard-coding an ID list.

## 7. Integration Testing Must Cover Both Matchers and Handlers

### 7.1. Functional and Security Matrix

Execute across each identity group (anonymous, `DOC_READ`, `DOC_EDIT`, `DOC_DELETE`, admin if any) and each published route. Keep real methods/paths matching production.

| Test | Outcome to Prove |
| --- | --- |
| `DOC_READ` + `GET /api/documents/42` | Allowed to read if object/tenant permissions hold |
| `DOC_READ` + `DELETE /api/documents/42` | Does not delete, does not invoke delete service |
| `DOC_READ` + `PATCH /api/documents/42` | Does not modify data, even with valid CSRF |
| `DOC_DELETE` + `DELETE /api/documents/42` | Allowed if object/tenant permissions and business conditions hold |
| Unregistered method | Does not match a broad rule branch and does not invoke sensitive handler |
| HEAD on GET route | Behaves per declared policy; never accidentally runs write logic |
| Valid OPTIONS preflight | Handled by CORS per config, never means granting permission for real DELETE/PATCH |
| `POST _method=DELETE` when filter enabled | Both Security and handler evaluate DELETE; read permission is insufficient |
| `X-HTTP-Method-Override` header when app/gateway supports it | Consistent effective method, checked against the right authority |
| Alias, trailing slash, double slash, dot-segment | Blocked or properly authorized after routing; no bypass |
| Encoded slash/percent, semicolon, double encoded | Blocked by firewall/container or handled consistently; no sensitive data leaked |
| Context path, secondary servlet, proxy rewrite | Real path still enters the right `SecurityFilterChain`/rule |
| One route with ID and query selecting another tenant | Service checks target resource's tenant/owner |
| Internal forward/error dispatch | Appropriate dispatcher is protected; never accidentally routes to sensitive endpoint |
| Multiple filter chains / overlapping rules | Proves first chain and first rule match intended selection |

**Do not demand every malformed request return 403.** `StrictHttpFirewall` may return a request error (typically 400 depending on config), MVC may return 404/405, authentication may produce 401 or a redirect. The security criterion is: no successful unauthorized access, no side effects, and no sensitive data returned. For the exact case of an authenticated principal, existing route, and missing permission, 403 is typically a reasonable expectation.

### 7.2. MockMvc Tests Through `SecurityFilterChain`

In a Spring Boot project, use `spring-security-test`, Spring Boot test, and `MockMvc` attached to the real context. The snippet below is an **integration test excerpt** (not standalone Java; depends on the app's `SecurityFilterChain` and APIs):

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentRoutingSecurityIT {

    @Autowired MockMvc mvc;

    @Test
    @WithMockUser(authorities = "DOC_READ")
    void readPermissionCannotDelete() throws Exception {
        mvc.perform(delete("/api/documents/42").with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "DOC_READ")
    void readPermissionCannotPatch() throws Exception {
        mvc.perform(patch("/api/documents/42").with(csrf()))
            .andExpect(status().isForbidden());
    }
}
~~~

For real endpoints, add assertions that **the delete/edit service was not called** (appropriate spy/mock) or compare database state before and after. Add positive-direction tests: a `DOC_DELETE` principal can validly delete, `DOC_EDIT` can validly PATCH; if everything returns 403 due to CSRF or a non-existent route, the test suite has not proven permissions. Ensure `MockMvc` applies Spring Security filters; `@AutoConfigureMockMvc` registers filters in standard Boot setups, whereas manually built `MockMvc` requires `springSecurity()` to avoid testing controllers directly and skipping the chain.

### 7.3. Testing Real Servers Behind a Proxy

`MockMvc` does not fully simulate URL decoding of the HTTP connector, servlet container, or reverse proxy rewrites. Therefore add tests in a staging/test environment with **the same proxy and servlet container/config as production**, using an HTTP client capable of sending raw request-targets when supported.

- Send GET, HEAD, POST, PATCH, DELETE to main routes and aliases, verifying permission rules and corresponding handlers.
- Send paths with trailing slashes, double slashes, dots/percent signs, semicolons, and double encoding; record actual results at proxy, firewall, MVC, and side effects.
- Verify context path, servlet path, and rewrites; test `RequestMatcher`s on both narrow and fallback chains.
- If the frontend uses method overrides, test variants with/without the filter, filter ordering, and CSRF.
- Test that the proxy accepts forwarding headers only from trusted hops; requests from the Internet injecting headers must not alter route/tenant scope.

Non-standard request paths may be auto-normalized by HTTP clients before sending. When testing dot-segments, choose a tool that preserves the raw request-target (e.g., `curl` with `--path-as-is` for internal tests), and log the request received by the proxy to verify the intended payload was actually tested.

### 7.4. Checking Object-Level Authorization

Even when `SecurityFilterChain` matches accurately, `/api/documents/42` could return an object belonging to another tenant. Authorizing solely by `DOC_READ`/`DOC_EDIT`/`DOC_DELETE` does not solve **IDOR/BOLA**. Verify object ID, tenant/owner, object state, and actual action at the service layer, e.g., via method security or a policy service. Test the same user while changing IDs/tenants and using different aliases; every path to the same object must enforce the same policy outcome.

## 8. How to Investigate When Tests Reveal Discrepancies

1. **Verify the real request:** method, raw request-target, forwarding/override headers, and the URL forwarded by the proxy to Java. Do not log tokens/secrets to public logs.
2. **Verify the firewall:** was the request rejected by `StrictHttpFirewall`, wrapped for matching, or passed onward? If `RequestRejectedException` occurs, do not “fix” it by disabling the firewall before understanding the cause.
3. **Verify the selected chain:** `securityMatcher` and `SecurityFilterChain` order. Prove that aliases do not fall into a chain missing rules.
4. **Verify the first matching rule:** GET/POST/PATCH/DELETE rules in proper order; does a broad `permitAll` shadow narrow rules?
5. **Verify handler and service:** where MVC routes the same request; whether the real action is read, export, modify, or delete; where object/tenant permissions are checked.
6. **Verify the outcome:** HTTP code, returned body, data mutations, and audit records. Judge success by the principle **zero side effects or data leaks when unauthorized**, not just receiving 403.

Common mistakes include comparing paths with `startsWith`, comparing raw strings after manual decoding, reading the HTTP method before an override filter runs, permitting unlisted paths, relying on CORS or CSRF as if they were authorization, using a single filter chain covering only `/api/**` while forgetting aliases, or skipping real tests behind a reverse proxy.

## 9. Acceptance Criteria and Official References

A solid protection setup for this lesson's scope must demonstrate: **(1)** every route to a sensitive function is covered by an appropriate `SecurityFilterChain`; **(2)** methods and business actions map to the right authorities; **(3)** path variants do not create matching-vs-routing gaps enabling bypasses; **(4)** abnormal requests are rejected or handled consistently; **(5)** object/tenant permissions are verified at the service layer; **(6)** tests verify both HTTP responses and absence of side effects.

Official documentation to cross-check against your framework version:

- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): matcher ordering, HTTP methods, `SecurityFilterChain`, default deny.
- [Spring Security – HttpFirewall](https://docs.spring.io/spring-security/reference/servlet/exploits/firewall.html): URL differences, `StrictHttpFirewall`, HTTP method allowlist.
- [Spring Security – CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): handling preflight before authentication/authorization.
- [Spring Security – Spring MVC test integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/): applying security filters in `MockMvc`.
- [Spring Boot 3.3 – Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): configuring `spring.mvc.hiddenmethod.filter.enabled`.

Overarching rule: **the same business operation must demand the same permissions regardless of whether callers pick route aliases, different HTTP methods, or altered request formatting; whenever an explicit permission check is absent, deny access.**