# Controlled Matchers Using Headers, Parameters, or Request Attributes

## 1. The Problem: Choosing the Right Rule from Request Data Without Turning That Data into Permissions

An HTTP request carries more than a path and HTTP method. It also carries **headers**, **query/form parameters**, **request attributes**, and data generated or forwarded by infrastructure. Spring Security lets you use these signals to select the right policy via `RequestMatcher`. However, this is an area where vulnerabilities easily arise if everything in the request is treated as trustworthy.

For example, suppose an application provides:

- `GET /api/reports`: view report list, requires `report:read`.
- `GET /api/reports?format=csv`: export reports, requires `report:export`.
- Header `X-Api-Version: v2`: requests the v2 protocol variant; it does **not** mean the sender is an administrator.
- Request attribute `internal.verifiedTenant` set by a server-side authentication component: can help identify a verified tenant if the producer and timing are trustworthy.

If the configuration only has a path matcher `/api/reports` with `report:read`, a request with `?format=csv` may reach export logic without requiring export permission. Conversely, implementing:

```text
if (header X-Role == ADMIN) -> allow
```

lets the sender forge the header. Both bugs stem from **mixing request classification with authorization decisions**.

### The Right Model

```text
                         HttpServletRequest
                  method, path, header, parameter,
                    server-generated attribute
                                  |
                                  v
                    [RequestMatcher.matches()]
                      classifies which rule /
                        branch the request fits
                                  |
                                  v
                         [AuthorizationManager]
                   Authentication + GrantedAuthority
                   + policy of the selected branch
                                  |
                                  v
                        [Service / Data policy]
                    tenant, owner, object, workflow
                                  |
                            ALLOW / DENY
```

**RequestMatcher decides "which request?"; AuthorizationManager and business policy decide "who can do what?".** A header/parameter may be used to select a branch requiring **stricter** permissions, but must never be used as proof that the permission was granted.

Goal after this lesson: understand the provenance and trust level of each field, use built-in or version-appropriate custom matchers, combine conditions safely, keep non-matching behavior fail-closed, and test spoofing/ambiguity scenarios.

## 2. API Structure and Key Fields

In Spring Security Servlet, `org.springframework.security.web.util.matcher.RequestMatcher` is a functional interface. Its core method:

```java
boolean matches(jakarta.servlet.http.HttpServletRequest request);
```

A matcher can inspect path, method, headers, parameters, or other `HttpServletRequest` information. It returns true/false for the match condition. Some implementations support extracting variables from match results via `matcher(request)` and `RequestMatcher.MatchResult`, though that capability is unnecessary when only checking true/false.

| Data type | Common retrieval | Who typically controls it? | Used for what? |
| --- | --- | --- | --- |
| HTTP method | `request.getMethod()` | Client chooses; server decides route | Selecting GET/POST/PATCH... operations |
| Path and servlet path | `getRequestURI()`, `getServletPath()`, `getPathInfo()` | Client chooses URL, server/router normalizes | Selecting an endpoint or endpoint group |
| Header | `getHeader(name)`, `getHeaders(name)` | Usually client-sent, sometimes proxy-added | API version, format, content negotiation |
| Parameter | `getParameter(name)`, `getParameterValues(name)`, `getParameterMap()` | Client sends query or form | Selecting a "preview/export" branch per contract |
| Request attribute | `getAttribute(name)` | Server-side Java component sets via `setAttribute` | Verified internal context |
| Dispatcher type | `getDispatcherType()` | Servlet container/internal dispatch | REQUEST/FORWARD/ERROR/ASYNC rules |
| Media type | `getContentType()`, `Accept` header | Client indicates desired payload/response type | Selecting data handling; not proof of permission |
| Remote IP / host | `getRemoteAddr()`, `getServerName()` | Infrastructure, proxies, and config affect it | Infrastructure-level controls within proper scope |

Without verification, fields like `X-User`, `X-Role`, `X-Internal`, `tenantId`, and `admin=true` are merely **input values**. Even though they look like security metadata, that does not turn them into `Authentication` or `GrantedAuthority`.

### 2.1. Three Information Sources to Distinguish

1. **Client-controlled:** arbitrary headers, query strings, form fields, paths, and most of the body. Anyone calling the HTTP API can send them. Use them only to **describe the request** and validate input.
2. **Infrastructure-asserted:** values added by a proxy, API gateway, or load balancer after **verification**. Only trustworthy if the server cannot be reached bypassing that boundary, client-supplied values are stripped/overwritten, and an explicit trust mechanism is configured.
3. **Server-verified:** attributes created by an internal filter/service from a verified token or data source. For example, a tenant ID verified from the principal and membership, not a client-asserted tenant.

You cannot trust a request attribute merely because its name starts with `internal.`. If code sets:

```java
request.setAttribute(
    "internal.verifiedTenant",
    request.getHeader("X-Tenant-Id")
);
```

without verifying membership, then even though the data lives in a server-side attribute, it still has an **untrusted origin**. Provenance and verification steps are the true trust boundary.

## 3. Header-Based Matchers: Exact Conditions, Not Authentication

### 3.1. Headers Can Classify Requests

Appropriate examples:

- `X-Api-Version: v2` used to select a protocol variant for normally authorized clients.
- `Accept: text/csv` describes output format; if the response is a sensitive data export, export permission is still required.
- `X-Requested-With: XMLHttpRequest` was historically used to identify client type, **insufficient as an authentication mechanism or CSRF replacement**.
- Proxy-routed headers may indicate a processing channel, provided a protective fallback path exists.

When using a header to open a sensitive security branch, consider cases where the header is **missing**, **invalid**, **duplicated**, **differently cased**, or modified by a proxy. Never assume "header present means internal."

### 3.2. Built-In `RequestHeaderRequestMatcher`

Spring Security provides `RequestHeaderRequestMatcher` to check a header name and optionally an expected value.

Illustrative integration snippet:

```java
import org.springframework.security.web.util.matcher.RequestMatcher;
import org.springframework.security.web.util.matcher.RequestHeaderRequestMatcher;

RequestMatcher anyVersionHeader =
    new RequestHeaderRequestMatcher("X-Api-Version");

RequestMatcher onlyV2 =
    new RequestHeaderRequestMatcher("X-Api-Version", "v2");
```

- The single-argument constructor checks the **presence** of the header regardless of value.
- The two-argument constructor checks a specific value supported by the matcher. Per JavaDoc, when multiple header values exist, this implementation compares the first value, so **it should not be used to verify a sensitive header that can be repeated**.
- This is request matching. If the principal lacks `report:read` or `report:export`, having `X-Api-Version: v2` alone does not bypass permission checks.

HTTP header names are handled case-insensitively per the protocol; header values may have their own semantics and normalization. Never write manual comparisons like `contains("admin")`, `startsWith("trusted")`, or blindly trim/lowercase every value and treat it as proof of privilege.

### 3.3. Repeated Headers and Multiple Values

Servlet APIs provide:

```java
String first = request.getHeader("X-Api-Version");
java.util.Enumeration<String> all =
    request.getHeaders("X-Api-Version");
```

`getHeader` typically returns one value; if multiple values exist and upstream/downstream components handle them differently, rule selection can **diverge from execution behavior**. This is a form of request-smuggling/ambiguity risk.

Example request with two header lines:

```http
GET /api/reports HTTP/1.1
Host: example.test
X-Api-Version: v2
X-Api-Version: v1
```

If security checks only the first value while the controller/gateway picks the last value, the "protected version" may not be the version executed. When a value controls sensitive behavior, define **a single valid form** or normalize at a trusted gateway/entry point before both security and business logic use it. Do not guess how the container folds repeated headers; test on your exact stack and proxy.

### 3.4. Headers Behind a Reverse Proxy

Headers like `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Proto`, or internal gateway headers are trustworthy only when the proxy path is properly secured, the proxy strips spoofed inbound headers, and the application is unreachable except through the allowed channel.

A request carrying:

```http
X-Internal: true
X-Role: ADMIN
X-Forwarded-For: 127.0.0.1
```

**does not automatically become an internal, admin, or localhost request.** Nor should `Origin` or `Referer` be used as primary proof of identity. CORS, CSRF, proxy trust, and authentication serve different concerns.

## 4. Parameter-Based Matchers: Query, Form, and Multi-Valued Parameters

### 4.1. What Does `getParameter` Actually Read?

For a Servlet request, `getParameter("format")` typically retrieves parsed query parameters and, depending on request/content type, form data. It **does not automatically parse arbitrary JSON bodies**.

Cases:

```http
GET /api/reports?format=csv HTTP/1.1
GET /api/reports?format=pdf HTTP/1.1
GET /api/reports?format=csv&format=pdf HTTP/1.1
GET /api/reports?format= HTTP/1.1
GET /api/reports HTTP/1.1
```

Results:

- With `format=csv`, the parameter exists with value `csv`.
- With `format=`, the parameter may exist with an empty string value, **which differs from an absent parameter**.
- With `format=csv&format=pdf`, the parameter has **multiple values**; reading only `getParameter` can miss the rest. Use `getParameterValues` to detect ambiguity when the contract allows only one.
- For a request without `format`, `getParameterMap().containsKey("format")` is false under standard behavior.

A JSON request:

```http
POST /api/reports HTTP/1.1
Content-Type: application/json

{"format":"csv"}
```

does not automatically turn the JSON `format` key into a request parameter. Body-dependent security decisions are best enforced in the business-handling layer after the body is parsed/validated; avoid custom matchers consuming `InputStream` and causing the controller to fail reading the body or read inconsistently twice.

### 4.2. `ParameterRequestMatcher` and Version Compatibility

Spring Security **6.4+** introduces `ParameterRequestMatcher` to match request parameters. Two common constructors:

```java
import org.springframework.security.web.util.matcher.ParameterRequestMatcher;

var anyFormat = new ParameterRequestMatcher("format");
var csvFormat = new ParameterRequestMatcher("format", "csv");
```

This is an **API snippet for Spring Security 6.4 and newer**. If your project is still on Spring Security 6.3, do not copy this class assuming it exists; use a Servlet-API-based lambda matcher or a version-compatible component instead.

Example **independent of `ParameterRequestMatcher`**, compatible with Spring Security 6.x custom matcher APIs:

```java
import org.springframework.security.web.util.matcher.RequestMatcher;

RequestMatcher anyExportFormat = request ->
    request.getParameterMap().containsKey("format");
```

The line above only classifies "has parameter `format`"; it neither validates values, checks the user, nor constrains path/method. Normally combine it with a path/method matcher or handle directly inside a lambda containing the full route selection criteria.

### 4.3. Parameter Pollution: Avoiding Weak Permission Branches

Consider two dangerous implementations:

```text
Security rule:
  if format=csv -> requires report:export
  otherwise -> only requires report:read

Controller:
  if format has any value -> runs export
```

If security checks exact equality to `csv` while the controller exports `pdf` too, `?format=pdf` can fall into the weaker read rule yet still execute export. This is a **policy mismatch** between how the matcher and controller interpret the action.

A stronger design:

- If **any** presence of the `format` parameter can trigger export, match **every request containing `format`** and require `report:export`.
- The controller validates `format` as a single valid value, rejecting empty strings, multiple values, or unknown formats before exporting.
- The branch without `format` only lists reports; no hidden logic triggers export based on unchecked headers or state.
- If there are multiple export styles, consider a separate route `GET /api/reports/export?format=csv` for clearer policy and easier testing.

### 4.4. Data Validation Is Not Authorization

Checks like "format must be csv/pdf," "limit must be positive," or "sortBy accepts only allowed columns" are **validation**. Checks like "this caller holds `report:export`," "allowed to export this tenant's data," or "row quota is respected" are **authorization/business policy**.

A request can have a valid format yet lack permission, or have export permission with an invalid format. Neither must perform the export. Never use validation matchers to implicitly grant permissions.

## 5. Request Attributes: Trustworthy Only When You Know Who Created Them, When, and From Where

### 5.1. Attributes Differ from Parameters

Servlet API:

```java
request.setAttribute("internal.verifiedTenant", verifiedTenantId);
Object value = request.getAttribute("internal.verifiedTenant");
```

An attribute is data attached to the `HttpServletRequest` object by server/container code. It is **not automatically created** just because a client sends `?internal.verifiedTenant=7` or a similarly named header.

However, a value sitting in an attribute does not prove it was **verified**. If a filter copies a user-supplied value into an attribute, its trustworthiness remains that of raw input. Document the producer's responsibility, data type, verification policy, and attribute lifecycle.

### 5.2. Example of a Verified Tenant Context

A sound processing flow:

```text
Bearer token or session
       |
       v
Authenticator creates Authentication
       |
       v
User membership/tenant verifier
       |
       v
Attach VerifiedTenantContext (internal object) to request
       |
       v
Matcher may use context to SELECT policy
       |
       v
AuthorizationManager still checks authority
       |
       v
Service/repository checks resource's tenant
```

If using an attribute to classify requests, prefer a dedicated internal object type rather than a `"true"` string or client-typed value. Yet even checking `instanceof VerifiedTenantContext` is insufficient if other code can instantiate this object without verifying data. Trust is established by **the creation workflow and execution path**, not just by class name.

### 5.3. Filter Order Trap

Crucially: `FilterChainProxy` must **select the SecurityFilterChain before filters inside that chain run**. Therefore:

- An attribute set by a **filter inside a chain** will **not exist in time** to affect `securityMatcher` when selecting that very chain.
- An attribute set by a filter running **before AuthorizationFilter** within a matching chain can be ready for `requestMatchers` rule selection (depending on real filter order).
- An attribute set by a controller or service after authorization has already run is **too late** to affect pre-controller decisions.
- An attribute set by a filter outside `FilterChainProxy` can exist at chain-selection time, but requires extra care regarding trust, filter registration, ordering, and all request paths.

**Never use an attribute set by a filter inside a chain as the condition to select that same filter chain.** That is a circular dependency bug: the matcher will always lack the data when evaluated.

In simpler architectures, rather than splitting filter chains by tenant attribute, select chains by clear path/method and evaluate tenant in the authorization manager/service using the verified principal.

### 5.4. Lifecycle and Dispatchers

A request may pass through `REQUEST`, `FORWARD`, `ERROR`, or `ASYNC` dispatches. Attributes can persist across phases, but never assume they share the same origin, value, or creation timing across dispatches. The protective layer must verify the attribute was established prior to the decision and define explicit policy for relevant dispatch types.

Never store an `HttpServletRequest` or its attributes in a `static` field, singleton bean, or global cache for reuse across requests. Likewise, do not confuse request attributes with `SecurityContextHolder` or `Authentication`: they are distinct mechanisms with different lifecycles and security semantics.

## 6. Combining Path, Method, Header, and Parameter Without Leaving Bypasses

### 6.1. Matchers Must Classify Actions Accurately

A standalone "has `format`" rule matches unrelated APIs like `/api/users?format=csv` too. If placed before other rules with a weaker permission, it can route requests into an unintended policy.

Combine criteria instead:

```text
GET
AND path == /api/reports
AND parameter "format" is present
    -> this is the export branch
    -> must have report:export

GET
AND path == /api/reports
AND "format" is absent
    -> this is the list branch
    -> must have report:read
```

In the DSL, sensitive rules must appear **before** broad GET rules, ending with `denyAll`. In real applications, if paths are mapped via Spring MVC or another servlet prefix, pick path matchers compatible with the router instead of raw `getRequestURI()` string checks that ignore context path.

### 6.2. Controlled Spring Security 6.x Configuration

This is **integration code** in a Spring Security Servlet 6.x app. It does not depend on `ParameterRequestMatcher`, illustrating a custom matcher compatible with Spring Security 6.3 as well. Real apps still need proper authentication and data controls.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.RequestMatcher;

@Configuration
public class ReportHttpSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        // This example assumes DispatcherServlet is mapped at root,
        // so servletPath == "/api/reports" for the target endpoint.
        RequestMatcher exportVariant = request ->
            "GET".equals(request.getMethod())
                && "/api/reports".equals(request.getServletPath())
                && request.getParameterMap().containsKey("format");

        http.authorizeHttpRequests(auth -> auth
            // Sensitive branch MUST be evaluated before the general read branch.
            .requestMatchers(exportVariant)
                .hasAuthority("report:export")
            .requestMatchers(HttpMethod.GET, "/api/reports")
                .hasAuthority("report:read")
            .anyRequest().denyAll()
        );

        return http.build();
    }
}
```

Understand thoroughly:

1. `GET /api/reports?format=csv` matches `exportVariant`, so `report:export` is required. An empty or unsupported `format` value still falls into the export-permission branch whenever the parameter exists; the controller then returns a validation error.
2. `GET /api/reports` without `format` goes to the `report:read` rule.
3. `POST /api/reports?format=csv` misses `exportVariant` because method is not GET; it also misses the GET rule and hits `denyAll()`.
4. All undeclared paths and methods are denied. With multiple `SecurityFilterChain`s, verify which chain covers the request; `anyRequest().denyAll()` applies only inside the chosen chain.
5. `getServletPath()` depends on servlet mapping. If the app runs under a special servlet prefix, update the matcher or use framework-supported path matcher APIs and test real URLs.
6. The code configures no authentication, CSRF, CORS, sessions, or resource server. Never treat an isolated snippet as complete production security configuration.

**Mandatory condition for this config to be safe:** export-triggering logic must **align exactly** with "parameter `format` is present." If export can also be triggered by `Accept: text/csv`, `?download=true`, or another URL, those paths need equivalent policies. Never allow a request to execute export after slipping into a weaker read rule.

### 6.3. Header Matcher Example for API Version Classification

Illustrative snippet:

```java
import org.springframework.security.web.util.matcher.AndRequestMatcher;
import org.springframework.security.web.util.matcher.RequestHeaderRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

RequestMatcher apiPathAndMethod = request ->
    "GET".equals(request.getMethod())
        && "/api/reports".equals(request.getServletPath());

RequestMatcher versionTwo =
    new RequestHeaderRequestMatcher("X-Api-Version", "v2");

RequestMatcher versionTwoReports =
    new AndRequestMatcher(apiPathAndMethod, versionTwo);
```

`AndRequestMatcher` requires **both matchers** to match. This is still only a branch-selection condition. If v2 is for regular users, the v2 rule must still require read permission; if v2 unlocks sensitive actions, the rule needs the corresponding sensitive permission.

To avoid duplicate-header risks, protocol version v2 should be resolved by a dedicated normalizer/validator or custom matcher checking all values before handler execution. Even clearer is separating versions in the path if the system permits.

### 6.4. AND, OR, NOT, and the First-Match Effect

A composite matcher can use `AndRequestMatcher`, `OrRequestMatcher`, or `NegatedRequestMatcher`. However:

- **AND** is suited to binding method, path, and classification signals together.
- **OR** should be used only when *each branch* genuinely requires equivalent permissions; if one branch is weaker, it can open a bypass.
- **NOT** easily produces unexpectedly broad request sets; pair it with a strict fallback.
- Matchers in `authorizeHttpRequests` generally select **the first matching rule**. A general rule before an export rule prevents the export rule from ever running.
- Across multiple filter chains, `securityMatcher` selects **the first matching chain**; chains are never evaluated sequentially after a match.

Wrong example:

```text
GET /api/reports (only needs report:read)
GET /api/reports?format=csv (needs report:export)
```

If the general GET rule comes first, export requests match the read rule first. Fix by putting the sensitive branch first or separating the export endpoint.

## 7. Standalone Java 17: Headers, Parameters, and Verified-Source Attributes

This program helps observe branch selection based on three signal types. It uses **simulated request classes** without Spring so it compiles standalone. Illustrated policy:

- Identify the export branch by method GET, path `/api/reports`, and **presence** of parameter `format`.
- Accept `format` only as **a single** value `csv` or `pdf`.
- Require **exactly one** `X-Api-Version: v2` header; the header only selects protocol, never granting permissions.
- Require authority `report:export`.
- Require a tenant context produced by a server-side verification step, never using an `X-Tenant-Id` header to grant permissions.

Save file `ControlledRequestMatcherDemo.java`:

```java
import java.util.List;
import java.util.Map;
import java.util.Set;

public class ControlledRequestMatcherDemo {
    record VerifiedTenant(String id) {}

    record RequestData(
        String method,
        String path,
        Map<String, List<String>> headers,
        Map<String, List<String>> parameters,
        Map<String, Object> attributes
    ) {}

    // Only describes which branch is being requested; does not grant permission.
    static boolean isExportIntent(RequestData request) {
        return request != null
            && "GET".equals(request.method())
            && "/api/reports".equals(request.path())
            && request.parameters() != null
            && request.parameters().containsKey("format");
    }

    static boolean hasSingleV2Header(RequestData request) {
        if (request == null || request.headers() == null) {
            return false;
        }
        List<String> versions =
            request.headers().get("X-Api-Version");
        return versions != null && versions.size() == 1
            && "v2".equals(versions.get(0));
    }

    static boolean hasValidFormat(RequestData request) {
        if (request == null || request.parameters() == null) {
            return false;
        }
        List<String> values =
            request.parameters().get("format");
        return values != null && values.size() == 1
            && Set.of("csv", "pdf").contains(values.get(0));
    }

    // This condition is meaningful only if VerifiedTenant is genuinely
    // created after a server-side verification step.
    static boolean sameVerifiedTenant(
            RequestData request, String currentTenant) {
        if (request == null || request.attributes() == null
                || currentTenant == null) {
            return false;
        }
        Object attribute =
            request.attributes().get("internal.verifiedTenant");
        return attribute instanceof VerifiedTenant verified
            && currentTenant.equals(verified.id());
    }

    static boolean canExport(
            RequestData request,
            Set<String> authorities,
            String currentTenant) {
        return isExportIntent(request)
            && hasSingleV2Header(request)
            && hasValidFormat(request)
            && authorities != null
            && authorities.contains("report:export")
            && sameVerifiedTenant(request, currentTenant);
    }

    static RequestData sample() {
        return new RequestData(
            "GET",
            "/api/reports",
            Map.of("X-Api-Version", List.of("v2")),
            Map.of("format", List.of("csv")),
            Map.of("internal.verifiedTenant",
                   new VerifiedTenant("tenant-A"))
        );
    }

    static void show(String name, boolean result) {
        System.out.println(name + ": " + result);
    }

    public static void main(String[] args) {
        RequestData valid = sample();

        show("export intent", isExportIntent(valid));
        show("one v2 header", hasSingleV2Header(valid));
        show("valid format", hasValidFormat(valid));
        show("export allowed",
            canExport(valid, Set.of("report:export"), "tenant-A"));
        show("read permission only",
            canExport(valid, Set.of("report:read"), "tenant-A"));

        RequestData duplicateFormat = new RequestData(
            "GET", "/api/reports",
            Map.of("X-Api-Version", List.of("v2")),
            Map.of("format", List.of("csv", "pdf")),
            valid.attributes()
        );
        show("duplicate still export intent",
            isExportIntent(duplicateFormat));
        show("duplicate format rejected",
            canExport(duplicateFormat,
                Set.of("report:export"), "tenant-A"));

        RequestData duplicateHeader = new RequestData(
            "GET", "/api/reports",
            Map.of("X-Api-Version", List.of("v2", "v1")),
            valid.parameters(),
            valid.attributes()
        );
        show("duplicate header rejected",
            canExport(duplicateHeader,
                Set.of("report:export"), "tenant-A"));

        RequestData forgedRole = new RequestData(
            "GET", "/api/reports",
            Map.of(
                "X-Api-Version", List.of("v2"),
                "X-Role", List.of("ADMIN")
            ),
            valid.parameters(), valid.attributes()
        );
        show("forged role header grants nothing",
            canExport(forgedRole,
                Set.of("report:read"), "tenant-A"));

        RequestData unverifiedAttribute = new RequestData(
            "GET", "/api/reports",
            valid.headers(), valid.parameters(),
            Map.of("internal.verifiedTenant", "tenant-A")
        );
        show("unverified attribute rejected",
            canExport(unverifiedAttribute,
                Set.of("report:export"), "tenant-A"));

        show("other tenant rejected",
            canExport(valid,
                Set.of("report:export"), "tenant-B"));
    }
}
```

Compile and run on JDK 17 or newer:

```bash
javac ControlledRequestMatcherDemo.java
java ControlledRequestMatcherDemo
```

Expected output:

```text
export intent: true
one v2 header: true
valid format: true
export allowed: true
read permission only: false
duplicate still export intent: true
duplicate format rejected: false
duplicate header rejected: false
forged role header grants nothing: false
unverified attribute rejected: false
other tenant rejected: false
```

**Why do these results matter?**

1. A valid v2 header and valid parameter only describe the request shape; export is still disallowed if the authority is missing.
2. A repeated parameter **is still an export intent** (must not fall into the read branch), yet validation rejects it because exactly one value is required.
3. A repeated v2 header is rejected because the illustrated rule requires a single value; this eliminates ambiguity across parsers.
4. The `X-Role: ADMIN` header is never converted into a `GrantedAuthority`. A subject holding only `report:read` still cannot export.
5. A string attribute `"tenant-A"` does not match a `VerifiedTenant` object; more importantly, in a real app you **must verify who created `VerifiedTenant` before trusting it**.
6. Even with export permission, a mismatched tenant context still denies access.

**Example limitations:** the two `record` types only model data; they do not verify tokens, proxies, or databases. Because the demo code instantiates `VerifiedTenant` inside `sample()`, never treat that as proof that such an object can be trusted when created elsewhere. In a real project, only verified authentication/policy components may build a valid context, and the service still verifies the tenant of the data being exported.

## 8. Testing Matchers in Spring Security

### 8.1. Test the Matcher in Isolation Before Testing Authorization

With `MockHttpServletRequest` from Spring Test, you can construct concrete requests and invoke `matches()`. The following is a **fragment inside a JUnit test with Spring Test/Spring Security dependencies**:

```java
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.util.matcher.RequestHeaderRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

RequestMatcher v2 =
    new RequestHeaderRequestMatcher("X-Api-Version", "v2");

MockHttpServletRequest request =
    new MockHttpServletRequest("GET", "/api/reports");
request.addHeader("X-Api-Version", "v2");

boolean matches = v2.matches(request);
// matches should be true under this test configuration.
```

Corresponding tests must cover missing headers, wrong values, multi-valued headers, and off-route requests if combined with a path matcher. For request attributes, test when the filter sets the attribute and the distinction between verified attributes and values copied from headers.

### 8.2. Safety Matrix: Match and Authorize Are Two Separate Steps

| Request | Expected matcher | Permission/extra checks | Expectation |
| --- | --- | --- | --- |
| `GET /api/reports` | List branch | `report:read` | Can read when authorized |
| `GET /api/reports?format=csv` | Export branch | `report:export`, tenant scope | Export only if authorized |
| `GET /api/reports?format=pdf` | Export branch | `report:export`, validation | Must not fall back to read permission |
| `GET /api/reports?format=` | Export branch | Export permission + input validation | Reject empty format |
| `GET /api/reports?format=csv&format=pdf` | Export branch | Reject multi-valued input if contract is single-valued | Must not go through read branch |
| `GET /api/reports?format=csv` + only `report:read` | Export branch | Missing export permission | 403 (assuming authenticated) |
| Header `X-Role: ADMIN` | Does not alter authorities | Must check principal | No privilege escalation |
| Repeated v2 version header | Version branch per validation policy | Ambiguity check | Never execute actions based on divergent values |
| Request with `internal.verifiedTenant` set by trusted filter | Policy branch if set before matcher | Tenant/permission | Per policy |
| Client-supplied tenant header copied into attribute | Must not be treated as verified | Membership/tenant policy | Reject if unverified |
| JSON body parameter while matcher reads `getParameter` | Does not become parameter automatically | Other rule or service validation | Must not bypass permission |
| Request outside `securityMatcher("/api/**")` | Another chain/fallback | Default deny | Must not slip outside Spring Security |

When testing a rule, be clear about **which condition is under test**. A 403 caused by CSRF does not prove the authorization matcher blocked the request. For POST/PATCH/DELETE in CSRF-enabled apps, supply a valid CSRF token when testing authorization branches; test CSRF in separate cases.

### 8.3. MockMvc Test for the Export Branch

Illustrative snippet in a test environment already having `MockMvc`, controllers, and fixtures:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// User has read permission but lacks export permission.
mockMvc.perform(get("/api/reports")
        .param("format", "csv")
        .with(user("reader").authorities(
            new SimpleGrantedAuthority("report:read"))))
    .andExpect(status().isForbidden());
```

Import `org.springframework.security.core.authority.SimpleGrantedAuthority` in the test. This is not a standalone program; real security config and endpoints are required. A corresponding test for a user with `report:export` must verify format, tenant, data scope, and not just a 200 response. If the export endpoint triggers an asynchronous job, protect both job creation and downloading the resulting artifact.

### 8.4. Testing Filter/Attribute Boundaries

Several critical scenarios:

- Attribute set by a filter **before AuthorizationFilter**: does the authorization matcher see it?
- Attribute set by a controller: does a pre-controller matcher see it? Do not expect it to.
- Attribute set by a filter **inside a chain** yet used to select that chain's `securityMatcher`: creates a circular dependency and must be redesigned.
- Request passing through `FORWARD`, `ASYNC`, or `ERROR` dispatches: is the attribute still valid, and which rule applies?
- A filter copying from `X-Tenant-Id`: is the principal verified as a member of that tenant before the attribute is used?
- Two filters setting the same attribute name: which owns the final value, and can it be overwritten?
- Data added by a reverse proxy vs a client spoofing a header with the same name: which value actually reaches the application?

Never accept tests that rely solely on synthetic requests pre-populated with "trusted" attributes while skipping the server-side attribute creation workflow.

## 9. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `X-Role: ADMIN` to grant permissions | Client self-escalates privileges | Use only verified Authentication/authorities |
| Matching `format=csv` while controller exports all formats | Other formats fall into read rule | Match all export intents or split endpoints |
| Broad list rule placed before export rule | Export rule never selected | Sensitive rules first, default deny |
| Using `getParameter` and ignoring multi-values | Security and controller may read different values | Use `getParameterValues` and single-value policy |
| Treating `format=` as absent | Unclear branch, weak validation | Distinguish presence from valid value |
| Assuming JSON body populates `getParameter` | Matcher misses the actual action | Parse/validate at the right layer or split routes |
| Trusting an attribute just because it's named `internal.*` | Value actually copied from unverified header | Verify producer and provenance |
| Using an in-chain attribute to select that chain | Attribute does not exist at selection time | Change chain criteria or place earlier properly |
| Treating client `X-Forwarded-For` as internal IP | Spoofed network origin | Proxy trust and inbound header filtering |
| Repeated headers parsed differently per layer | Selected rule diverges from execution | Reject ambiguous inputs / canonicalize in one place |
| Matcher checks only header, ignoring method/path | Accidentally matches other endpoints | Combine scoped criteria |
| Overly broad OR composition | Weaker branch opens access against policy | Express AND/OR clearly, test branches |
| Testing only `matches()` | Does not prove permissions or data protection | Add HTTP/service/data integration tests |
| Fixing policy errors with `permitAll` | Errors turn into open access | Fail closed on protected operations |
| Treating `RequestHeaderRequestMatcher` as authentication | Header match does not prove principal | Separate authentication from request classification |
| Copying `ParameterRequestMatcher` into Security 6.3 | API/version compile error | Use custom matcher in 6.3; class exists in 6.4+ |

## 10. Checklist for Designing Controlled Matchers

1. **Identify the action** the matcher classifies: list, export, preview, version routing, or content negotiation.
2. **Map the request contract:** HTTP method, path, query/form parameters, headers, content type, servlet mapping, dispatcher type.
3. **Document data provenance** for each signal: client-set, trusted-proxy-set, or server-side filter/service verified.
4. **Pick minimal criteria:** path and method usually come first; add headers/parameters only when the action truly changes.
5. **Distinguish presence from validity:** a present parameter may not have a valid value; a present header may not be single-valued.
6. **Block ambiguity:** repeated values, empty values, unusual encoding, and parser differences must be handled explicitly.
7. **Never use client signals as permissions:** rely only on trusted Authentication/authorities to decide who has permission.
8. **Place sensitive rules before broad rules** and include a deny fallback for undeclared requests.
9. **Check filter ordering** if relying on attributes; especially distinguish `securityMatcher` from `requestMatchers`.
10. **Maintain object policies** at the service/data layer: tenant, owner, data scope, and status.
11. **Write unit and integration tests** for both matching and final access decisions, including multiple headers, multiple parameters, missing/invalid values, dispatchers, and proxies.
12. **Review against your Spring Security version** when upgrading, especially matcher APIs and pattern parsers.

## 11. Practice Exercises

### Exercise 1 — Identify Trust Boundaries

Classify `X-Role`, `X-Api-Version`, `format=csv`, `internal.verifiedTenant`, `Authorization: Bearer ...`, and `X-Forwarded-For` as "client-asserted data," "infrastructure data if verified," or "verified application data." Explain why the `Authorization` header is also merely a credential that **must be authenticated**, not proof upon reading the raw header.

### Exercise 2 — Fix a Bypassed Export Rule

Suppose the controller exports whenever the `format` parameter is present, while security requires `report:export` only when `format=csv`. Redesign the matcher so csv, pdf, empty strings, and repeated values can never fall into the `report:read`-only branch. Write the before/after request-and-result matrix.

### Exercise 3 — Run Java 17

Run `ControlledRequestMatcherDemo.java`. Add cases for missing v2 header, empty string parameter, and a POST request with `format`. Predict stdout and verify. Explain why a forged role header does not alter `Set<String> authorities`.

### Exercise 4 — Attribute Ordering

Design a filter that verifies the tenant for the principal and creates a `VerifiedTenantContext` object. Explain where it must run if authorization matchers need the attribute, and why you cannot rely on a filter inside a chain to select that chain. Test with `MockMvc` instead of injecting fake attributes directly in tests.

### Exercise 5 — Controlling Repeated Headers

Create a request with two `X-Api-Version` headers. Use `getHeaders` to detect multiple values and reject when only one is allowed. Test with a real proxy/gateway if your system has multiple tiers, since they may fold headers differently.

### Exercise 6 — End-to-End Security Review

Add the `report:export` permission to an API. Audit the HTTP branch, query tenant scoping, asynchronous job export, artifact download URL, caching, and auditing. Prove a user holding only `report:read` cannot download exported content via any path.

## 12. End-of-Lesson Self-Check

1. **Does `RequestMatcher` returning true mean the user has permission?** No. It only confirms the request matches the classification condition.
2. **Can a client-sent header be used to select API version?** Yes, but not as proof of identity/role, and repeated/invalid values must be handled.
3. **What does `RequestHeaderRequestMatcher("X-Api-Version")` check?** That the header is present, without requiring value `v2`.
4. **Is `ParameterRequestMatcher` available in all Spring Security 6.x versions?** No; it was introduced in 6.4.
5. **Why is `getParameter("format")` insufficient to detect ambiguity?** Because a parameter can have multiple values; use `getParameterValues` when enforcing single-valued contracts.
6. **Does a JSON field `format` automatically become a Servlet parameter?** No.
7. **Why can a request attribute still be untrustworthy?** The server might copy it from client data without verification; you must know the producer and provenance.
8. **Can a filter inside a chain set an attribute to select that very chain?** You cannot rely on it; chain selection occurs before filters inside the chain execute.
9. **If a controller exports both csv and pdf while the matcher protects only csv, what is the risk?** Pdf can fall into a weaker read rule; policy must protect all export intents.
10. **Why must you match method + path + secondary signal together?** To avoid applying another endpoint's rule merely because it shares the same header/parameter.
11. **Does having `report:export` permit exporting another tenant's data?** No; the service/repository must still enforce object scope.
12. **Does a 403 test prove the matcher is correct?** No; 403 can come from CSRF, another rule, or missing authentication—test each layer with appropriate fixtures.

**Remember:** headers, parameters, and request attributes help Spring Security **identify the request type** to pick the right policy. They are safe only when you know **data provenance, lifecycle timing, and how to handle ambiguous values**. Never turn self-asserted headers/queries into permissions; combine path/method matchers, check verified authorities, and enforce tenant/resource permissions in the business layer.

### References

- [Spring Security – Authorize HttpServletRequests / Custom Matcher](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – RequestMatcher API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/util/matcher/RequestMatcher.html)
- [Spring Security – RequestHeaderRequestMatcher API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/util/matcher/RequestHeaderRequestMatcher.html)
- [Spring Security – ParameterRequestMatcher API (since 6.4)](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/util/matcher/ParameterRequestMatcher.html)
- [Spring Security – Servlet Architecture / FilterChainProxy](https://docs.spring.io/spring-security/reference/servlet/architecture.html)