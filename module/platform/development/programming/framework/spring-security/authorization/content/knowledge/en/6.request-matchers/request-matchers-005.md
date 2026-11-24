# RegexRequestMatcher and When Regular Expressions Are Needed

> **Module:** Spring Security – authorization  
> **Group:** RequestMatcher  
> **Goal:** Understand when to use `RegexRequestMatcher`, which part of the HTTP request it matches against, how to combine HTTP methods and authorization, and how to avoid overly broad rules, broken escaping, wrong ordering, and coverage gaps.

## 1. The Real-World Problem

Consider an order-reading API. Intended policy: HTTP GET with a path containing **an ID of 1–8 ASCII digits** must require the `order:read` permission; other actions must not reuse read permission:

~~~http
GET /api/orders/42
GET /api/orders/1007?expand=items
GET /api/orders/ABC
GET /api/orders/42/approve
POST /api/orders/42
~~~

The `/api/orders/**` matcher is simple but broad: it can accept URLs containing letters, extra path segments, and privileged actions. When an HTTP policy **genuinely needs to distinguish path structure**, regular expressions are an option.

However, **matching a regex does not grant access**. The regex only answers "does the request have the shape/HTTP method this rule targets?". Afterwards, Spring Security must check `Authentication` and authorities, and the service must verify permission on **the specific order** (owner/tenant/status). A URL with a valid ID can still be an unauthorized request.

## 2. Where Does RequestMatcher Sit?

`RequestMatcher` is Spring Security's Servlet interface for testing an `HttpServletRequest`. `RegexRequestMatcher` is an implementation using `java.util.regex.Pattern`.

~~~text
HTTP request
    |
    v
FilterChainProxy
    |
    +--> securityMatcher: selects the first matching SecurityFilterChain
    |
    v
Filters in the selected chain
    |
    v
AuthorizationFilter
    |
    +--> requestMatchers: selects the first matching rule
    |
    v
AuthorizationManager: hasAuthority / hasRole / authenticated / denyAll
    |
    v
Controller / Service / resource-level policy
~~~

**Do not confuse the two places matchers are used:**

| Level | API | Meaning when regex does not match |
|---|---|---|
| Chain level | `http.securityMatcher(regexMatcher(...))` | This chain is not selected; only another matching chain will protect the request |
| Rule level | `authorizeHttpRequests(...).requestMatchers(regexMatcher(...))` | Spring Security tries the next rule **within the selected chain** |

In `authorizeHttpRequests`, **the first matching rule decides**; subsequent rules are not accumulated. With multiple `SecurityFilterChain`s, the highest-priority matching chain is the only one that runs. Therefore, a broad regex placed before a sensitive rule can prevent the sensitive rule from ever being evaluated.

## 3. Which String Does RegexRequestMatcher Actually Match Against?

According to the Spring Security 6.5 and 7.x JavaDoc, `RegexRequestMatcher` evaluates the URL concatenated from:

~~~text
servletPath + pathInfo + queryString
~~~

If a query string is present, a `?` is prepended before the query. For example, for a request with:

~~~text
contextPath = "/shop"
servletPath = "/api/orders"
pathInfo = "/42"
queryString = "expand=items"

Regex input:
  /api/orders/42?expand=items
~~~

**Important consequences:**

- `contextPath` is not part of the matched string. Do not prepend `/shop` to the regex merely because the deployment uses that context path.
- The query string **can affect** regex matching, unlike many standard path matchers that only inspect the path.
- HTTP method GET/POST is a separate condition on the matcher if configured, not inferred from the path regex.
- `RegexRequestMatcher` is **case-sensitive by default**; `/API/orders/42` does not automatically match `/api/orders/42`.
- `HttpFirewall`, the servlet container, reverse proxies, and handler mappings can transform URLs before the matcher sees them. Do not guess the behavior of double slashes, semicolons, encoded slashes, or URL rewrites without testing in a real environment.

### Key Example: Query String Causes a Rule to Miss

Pattern:

~~~regex
^/api/orders/[0-9]+$
~~~

This can match `/api/orders/42` but will **not** match `/api/orders/42?expand=items` under the URL concatenation above.

If an optional query is part of the requirement:

~~~regex
^/api/orders/[0-9]+(?:\?.*)?$
~~~

The group `(?:\?.*)?` allows a literal `?` and the trailing query. Inside a **Java string**, backslashes must be escaped:

~~~java
String pattern = "^/api/orders/[0-9]+(?:\\?.*)?$";
~~~

Note: permitting query string syntax does not mean authorizing arbitrary `expand` or `mode` parameters. If a parameter exposes additional data, business policy must still verify it.

## 4. API for Creating RegexRequestMatcher

Factory methods exist since Spring Security 5.8 and are shown in official 6.x/7.x documentation:

~~~java
import org.springframework.http.HttpMethod;
import org.springframework.security.web.util.matcher.RegexRequestMatcher;

// Inspect regex only, no method restriction.
RegexRequestMatcher allMethods =
        RegexRequestMatcher.regexMatcher(
                "^/api/orders/[0-9]+(?:\\?.*)?$");

// Restrict both GET and regex.
RegexRequestMatcher onlyGet =
        RegexRequestMatcher.regexMatcher(
                HttpMethod.GET,
                "^/api/orders/[0-9]+(?:\\?.*)?$");

// Using constructor accepting method as a string.
RegexRequestMatcher onlyPost =
        new RegexRequestMatcher(
                "^/api/orders/[0-9]+(?:\\?.*)?$",
                "POST");

// Only when case-insensitive matching is required.
RegexRequestMatcher caseInsensitive =
        new RegexRequestMatcher(
                "^/api/orders/[0-9]+(?:\\?.*)?$",
                "GET",
                true);
~~~

This is a **snippet belonging to a Spring Security Servlet project**, not a plain JDK program. Always verify overloads against your active dependency version when upgrading.

Common static import syntax:

~~~java
import static org.springframework.security.web.util.matcher.RegexRequestMatcher.regexMatcher;
~~~

You can then call `regexMatcher(HttpMethod.GET, pattern)`.

**Do not enable case-insensitivity casually.** It makes the matcher accept additional URL spellings, while routing/controllers/gateways may not share the same convention. Test exact case sensitivity in both security and controllers.

## 5. When Is Regex a Reasonable Choice?

Regex is valuable when **segment format is an essential part of the HTTP rule** and ordinary path matchers cannot express it clearly enough.

### Case A: A Numeric-Only ID with Bounded Length

~~~regex
^/api/orders/[0-9]{1,8}(?:\?.*)?$
~~~

Matches a 1–8 digit segment. Rejects `ABC`, nine-digit IDs, or `/42/approve`. The controller itself should still parse and validate the ID; regex acts as the request-group classification layer.

### Case B: Report Version with Explicit Period

~~~regex
^/api/reports/20[0-9]{2}/Q[1-4](?:\?.*)?$
~~~

This structure accepts a `20xx` year and quarters `Q1` through `Q4`. Format precision does not mean the caller is allowed to view all reports.

### Case C: Slug with Restricted Character Set

~~~regex
^/api/catalog/[A-Za-z0-9_-]{3,24}(?:\?.*)?$
~~~

Restricts slugs to 3–24 ASCII Latin letters, digits, underscores, or hyphens. If the application supports Vietnamese/Unicode in paths, this regex may be too narrow. Do not enforce ASCII rules unless business requirements call for them.

### Case D: A Finite Group Sharing the Same Policy

~~~regex
^/api/(?:invoices|receipts)/[0-9]+(?:\?.*)?$
~~~

Combine only when both resource types **genuinely share the exact same permissions and conditions**. If `invoice:read` differs from `receipt:read`, two separate rules are easier to audit than one branching regex.

### Cases Where Regex Should Not Be Used

| Goal | Usually preferred |
|---|---|
| All paths under `/api/**` require login | Path matcher + `authenticated()` |
| `/admin/**` requires ADMIN role | Path matcher + `hasRole("ADMIN")` |
| `GET /orders/{id}` requires read permission | Method/placeholder path matcher and service policy |
| ID must be a Java `long` | MVC binding/validation |
| JSON body must have valid fields | DTO + Bean Validation |
| Query `?mode=export` requires a different permission | Custom RequestMatcher/AuthorizationManager or service policy |
| Order owner must be the caller | Object-level authorization, owner/tenant-scoped repository |
| Which scopes a JWT token holds | Authentication converter + authorization rule |
| All unknown URLs must be blocked | `anyRequest().denyAll()` and filter-chain fallback |

**Practical rule:** If `requestMatchers(HttpMethod.GET, "/api/orders/{id}")` already expresses the policy sufficiently, prefer it and let the controller handle ID typing. Choose regex when it solves a real requirement, not merely to make configuration look "strict."

## 6. Reading Metacharacters Correctly

| Regex symbol | Meaning | Example |
|---|---|---|
| `^` | Start of string | `^/api/` |
| `$` | End of string | `[0-9]+$` |
| `[0-9]` | One ASCII digit | `[0-9]{1,8}` |
| `[A-Za-z]` | ASCII Latin letter | `[A-Za-z]+` |
| `{m,n}` | Occurrences from m to n | `[0-9]{1,8}` |
| `+` | One or more | `[0-9]+` |
| `*` | Zero or more | `[A-Z]*` |
| `?` | Optional component | `(?:...)?` |
| `(?:...)` | Non-capturing group | `(?:pdf|csv)` |
| `\?` | Literal question mark | `(?:\?.*)?` |
| `\.` | Literal dot | `\.csv` |
| `.` | Any character in regex (with some newline exceptions) | `.*` |
| `|` | Alternation (OR) | `(?:GET|POST)` |

Symbols `\?` and `\.` must become `\\?`, `\\.` when written as Java string literals.

### 6.1. Dot Is a Wildcard, Not a Literal Period

Non-standard pattern:

~~~regex
^/reports/[0-9]+.csv$
~~~

`.` can match a character other than a dot; to require an actual `.csv` extension, use:

~~~regex
^/reports/[0-9]+\.csv$
~~~

Corresponding Java string:

~~~java
"^/reports/[0-9]+\\.csv$"
~~~

### 6.2. Be Careful with `.*` and `.+`

Pattern:

~~~regex
^/api/orders/.+$
~~~

can match `/api/orders/42/approve` because `/` falls within `.+`. If the rule enforces `order:read`, the approve endpoint could be evaluated under the read rule.

When you only want **one segment**, `[^/]+` is narrower. If the ID format is known, `[0-9]{1,8}` is even clearer. Never use `.*` to "fix" a matcher failure without understanding the root cause.

### 6.3. Anchors Do Not Replace Verification

Using `^...$` makes full-string matching explicit; with Java's `Pattern.matcher(input).matches()`, `matches()` itself also requires matching the entire input. Anchors help readability and reuse in other contexts, yet an anchored regex can still be overly broad or assign the wrong permission.

## 7. Practical Spring Security Servlet Configuration

Suppose the application uses Spring Boot 3.x, Spring Security 6.x, HTTP Basic, and authorities granted from a trusted source:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.RegexRequestMatcher;

@Configuration
public class OrderSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        RegexRequestMatcher numericOrderGet =
                RegexRequestMatcher.regexMatcher(
                        HttpMethod.GET,
                        "^/api/orders/[0-9]{1,8}(?:\\?.*)?$");

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(numericOrderGet)
                    .hasAuthority("order:read")
                .requestMatchers("/api/orders/**")
                    .denyAll()
                .anyRequest().denyAll()
        );

        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

This is a **project configuration class**, not standalone-compilable with JDK 17 alone. The application must provide controllers, an authentication provider, dependencies, and any required public rules. A JWT-based API should use a Bearer Resource Server configuration and verify scopes/permissions appropriately rather than copying HTTP Basic mechanically.

**Reading the three rules:**

1. `GET /api/orders/42`: regex + method match → requires authority `order:read`.
2. `GET /api/orders/42?expand=items`: regex allows query → still requires `order:read`.
3. `GET /api/orders/ABC`, `POST /api/orders/42`, `GET /api/orders/42/approve`: miss the specific rule → `/api/orders/**` denies them.
4. Remaining URLs → `anyRequest().denyAll()` fallback **inside this chain**.
5. A user with `order:read` must still pass the service policy checking the order's tenant/owner.

### Wrong Order: Broad Rule Shadows the Regex Rule

~~~java
// WRONG CONFIGURATION for the order-reading policy:
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/orders/**").authenticated()
        .requestMatchers(numericOrderGet).hasAuthority("order:read")
        .anyRequest().denyAll()
);
~~~

`GET /api/orders/42` already matches the `authenticated()` rule, so the `order:read` rule below **never runs**. This is a "first match wins" authorization bug, not a regex engine bug. Place specific rules first, while still ensuring later rules do not accidentally open sensitive endpoints.

### No Regex Needed If You Only Want an ID Placeholder

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/orders/{id}")
            .hasAuthority("order:read")
        .anyRequest().denyAll()
);
~~~

This is usually shorter and easier to maintain for standard routes with typed controller IDs. Path matching has its own semantics and is not identical to regex at every boundary (query, URL encoding, trailing slash).

## 8. Query String: The Most Error-Prone Part

Because `RegexRequestMatcher` sees the query string, choose an explicit design intent.

**Intent A – Query does not determine policy:** use a regex with an optional query portion like `(?:\\?.*)?` in a Java string, while the controller/service still validates every parameter. For example, `?expand=items` might expose sensitive data; require additional permissions if business logic demands it.

**Intent B – Want pure path-based matching:** use `requestMatchers` with standard path patterns instead of embedding query logic into regex.

**Intent C – Query determines action:** if `?mode=export` requires export permission while `?mode=view` only needs read permission, a custom `RequestMatcher` or service policy inspecting **parsed** parameters is usually clearer.

Short custom matcher example in a Servlet application:

~~~java
import org.springframework.security.web.util.matcher.RequestMatcher;

RequestMatcher exportMode = request ->
        "GET".equals(request.getMethod())
        && "/api/orders".equals(request.getServletPath())
        && "export".equals(request.getParameter("mode"));
~~~

This is not a standalone runnable program. Requests may have repeated query keys, different encodings, empty values, or defaults; define clear policy and test variants. Never treat a client-supplied `tenantId` parameter as proof of access to that tenant.

**Security point:** Allowing `?mode=export` in a URL regex does not prove the user holds `order:export`; check the actual action/authority in the authorization policy.

## 9. Regex at securityMatcher Level and the Risk of Requests Falling Outside Chains

If you put a regex in `http.securityMatcher`:

~~~java
http.securityMatcher(
        RegexRequestMatcher.regexMatcher("^/api/v[0-9]+/.*$"))
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated());
~~~

then **only** requests matching the regex enter this chain. If `GET /admin/users` or `GET /debug` matches no other chain, they may **go unprotected by any Spring Security filter chain**.

`anyRequest().authenticated()` or `anyRequest().denyAll()` **does not protect URLs outside the chain-level matcher**.

With multiple chains, a fallback chain is usually placed last:

~~~java
@Bean
@Order(99)
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .anyRequest().denyAll());
    return http.build();
}
~~~

This snippet is meaningful inside a Spring configuration class, requiring imports and properly `@Order`-annotated chains. The fallback has no `securityMatcher`, so by default it covers all requests not claimed by earlier chains. If placed before specialized chains, it can shadow them. Lacking a fallback is a potential coverage flaw even if regexes inside specialized chains are written perfectly.

If the application does not require distinct filter/authentication mechanisms, a single chain with multiple `requestMatchers` is usually easier to audit than multiple chains with overlapping regexes.

## 10. Regex Does Not Replace Owner/Tenant Permissions

A user having `order:read` and a URL `/api/orders/42` matching the regex **is not enough** to view order 42. You must also verify:

- Does the order exist and belong to the user's tenant?
- Is the user the owner or a shared recipient?
- Do the role/permissions apply to that order type and status?
- Does an expansion query expose fields beyond the user's permissions?
- Does the policy need updating if the user's permissions were recently revoked?

Example service method:

~~~java
@PreAuthorize(
    "hasAuthority('order:read') " +
    "and @orderPolicy.canRead(authentication, #id)"
)
public OrderDto getOrder(long id) {
    return orderQueryService.find(id);
}
~~~

This is an illustrative method depending on `@EnableMethodSecurity`, the `orderPolicy` bean, and a real service/repository. The `#id` parameter name must be resolvable. The policy checks tenant/owner from server-side sources rather than inferring record permissions from clean IDs or token scopes.

## 11. Encoding, Normalization, and Firewall

URLs can be represented in many forms:

~~~text
/api/orders/42
/api/orders/42/
/api//orders/42
/api/orders/%34%32
/api/orders/42;param=x
/API/orders/42
/shop/api/orders/42
/api/orders/42?expand=items
~~~

Do not assume they are strictly equivalent or strictly distinct across every environment. Reverse proxies, servlet containers, MVC mappings, and Spring Security `HttpFirewall` may normalize or reject some forms.

Specifically:

- `contextPath` like `/shop` is not included in `RegexRequestMatcher`'s concatenated string per JavaDoc.
- If a proxy rewrites paths, check the URL the Servlet actually receives, not only the external browser URL.
- `StrictHttpFirewall` may reject unusual URL forms; never relax firewall settings just so a pattern catches encoded slashes or semicolons.
- Security and MVC must interpret URLs consistently; if each layer interprets them differently, rule bypasses become possible.
- Never "quick-fix" with `.*orders.*`: it can broaden permissions far beyond intent.

Use integration tests through proxies/test servlet mappings when the system uses special URL rewrites, checking both controller outcomes and security rules.

## 12. ReDoS and Regex Maintainability

Java `Pattern` can use backtracking. Patterns with overlapping repetitions or ambiguous branches can consume massive CPU on near-matching failing inputs.

Classic pattern to avoid without good reason:

~~~regex
^(a+)+$
~~~

At the authorization layer, matchers run frequently and on client-controlled inputs. Therefore:

1. Never build regexes from client-submitted parameters.
2. Use static, code-reviewed, readable patterns.
3. Choose narrow character classes and bounded quantifiers, such as `[0-9]{1,8}`.
4. Avoid `.*` and nested repetition groups unless genuinely needed.
5. Enforce URL/request size limits at the proxy/servlet.
6. Benchmark complex patterns with long failing boundary inputs.
7. Prefer path matchers when only prefixes/placeholders are needed.

Complex regexes do not automatically make a system "safer." Correct **policy** and negative tests matter far more than the number of characters in a pattern.

## 13. Testing RegexRequestMatcher Directly

Example test in a project with JUnit 5, Spring Test, and Spring Security:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.util.matcher.RegexRequestMatcher;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RegexMatcherTest {

    private final RegexRequestMatcher matcher =
            RegexRequestMatcher.regexMatcher(
                    HttpMethod.GET,
                    "^/api/orders/[0-9]{1,8}(?:\\?.*)?$");

    static MockHttpServletRequest req(
            String method, String servletPath, String queryString) {
        MockHttpServletRequest request =
                new MockHttpServletRequest(method, servletPath);
        request.setServletPath(servletPath);
        if (queryString != null) {
            request.setQueryString(queryString);
        }
        return request;
    }

    @Test
    void acceptsNumericId() {
        assertTrue(matcher.matches(req("GET", "/api/orders/42", null)));
    }

    @Test
    void acceptsQueryStringWhenConfigured() {
        assertTrue(matcher.matches(
                req("GET", "/api/orders/42", "expand=items")));
    }

    @Test
    void rejectsAlphabeticId() {
        assertFalse(matcher.matches(
                req("GET", "/api/orders/A42", null)));
    }

    @Test
    void rejectsWrongMethod() {
        assertFalse(matcher.matches(
                req("POST", "/api/orders/42", null)));
    }

    @Test
    void rejectsExtraPathSegment() {
        assertFalse(matcher.matches(
                req("GET", "/api/orders/42/approve", null)));
    }
}
~~~

This is a **Spring project test**, not a standalone JDK example. Note `MockHttpServletRequest.setServletPath`: setting only the request URI does not necessarily populate the Servlet fields the matcher reads in the way you might expect. Explicitly test query strings and methods.

### Negative Test Suite to Include

| Scenario | Numeric-ID GET regex matches? | Policy expectation |
|---|---|---|
| `GET /api/orders/42` | Yes | Check `order:read` |
| `GET /api/orders/42?expand=items` | Yes with optional-query pattern | Check read permission and any expansion permission |
| `GET /api/orders/A42` | No | Later rule denies if invalid |
| `GET /api/orders/123456789` | No | Must not pass via a broad rule |
| `POST /api/orders/42` | No due to method | Needs separate POST rule or deny |
| `GET /api/orders/42/approve` | No | Do not reuse read permission to approve |
| `GET /API/orders/42` | No under case-sensitive config | Verify against real routing |
| `GET /api/orders/42/` | No with above pattern | Check trailing slash and MVC |
| `GET /api/orders/00042` | Yes | Whether leading zeros are valid is a validation concern |
| User lacks `order:read`, valid URL | Yes | Authorization denies |
| User has `order:read` but wrong tenant | Yes | Service/object policy denies |
| URL outside all `SecurityFilterChain`s | No chain | Design fallback to protect |

Matcher tests returning true/false **do not prove** HTTP status codes. Test with `MockMvc` against real existing controllers to prove users lacking permission are denied and permitted users proceed per policy. A URL returning 404 because no controller exists **does not prove** a security filter protected it.

## 14. Standalone Java 17 Example: Simulating Method, Regex, and Fallback

The plain Java program below simulates the concept of `RegexRequestMatcher` without Spring Security. It concatenates `servletPath + pathInfo + ?queryString`, checks the HTTP method, picks the first matching rule, and shows a denying fallback. **This is a simulation**, not testing real `Authentication`, `HttpFirewall`, CSRF, Servlet, or object policies.

Save file `RegexRoutingDemo.java`:

~~~java
import java.util.List;
import java.util.regex.Pattern;

public class RegexRoutingDemo {
    record Request(String method, String servletPath, String pathInfo,
                   String queryString) {
        String urlForMatch() {
            return servletPath
                    + (pathInfo == null ? "" : pathInfo)
                    + (queryString == null ? "" : "?" + queryString);
        }
    }

    record Rule(String name, String method, Pattern pattern, String policy) {
        boolean matches(Request request) {
            return (method == null || method.equals(request.method()))
                    && pattern.matcher(request.urlForMatch()).matches();
        }
    }

    static String choose(Request request, List<Rule> rules) {
        for (Rule rule : rules) {
            if (rule.matches(request)) {
                return rule.name() + " -> " + rule.policy();
            }
        }
        return "NO_RULE";
    }

    static void show(String label, Request request, List<Rule> rules) {
        System.out.println(label + ": " + choose(request, rules));
    }

    public static void main(String[] args) {
        List<Rule> rules = List.of(
                new Rule("numeric GET", "GET",
                        Pattern.compile("^/api/orders/[0-9]{1,8}(?:\\?.*)?$"),
                        "REQUIRE order:read"),
                new Rule("orders fallback", null,
                        Pattern.compile("^/api/orders(?:/.*)?(?:\\?.*)?$"),
                        "DENY"),
                new Rule("global fallback", null,
                        Pattern.compile("^.*$"), "DENY")
        );

        show("numeric", new Request("GET", "/api/orders/42", null, null), rules);
        show("with query", new Request("GET", "/api/orders/42", null,
                "expand=items"), rules);
        show("split servlet path", new Request("GET", "/api", "/orders/42",
                null), rules);
        show("letters", new Request("GET", "/api/orders/A42", null, null), rules);
        show("wrong method", new Request("POST", "/api/orders/42", null, null), rules);
        show("extra path", new Request("GET", "/api/orders/42/approve",
                null, null), rules);
        show("too many digits", new Request("GET", "/api/orders/123456789",
                null, null), rules);
        show("uppercase path", new Request("GET", "/API/orders/42",
                null, null), rules);
        show("outside orders", new Request("GET", "/internal/health",
                null, null), rules);
    }
}
~~~

Run commands:

~~~bash
javac --release 17 RegexRoutingDemo.java
java RegexRoutingDemo
~~~

Exact output:

~~~text
numeric: numeric GET -> REQUIRE order:read
with query: numeric GET -> REQUIRE order:read
split servlet path: numeric GET -> REQUIRE order:read
letters: orders fallback -> DENY
wrong method: orders fallback -> DENY
extra path: orders fallback -> DENY
too many digits: orders fallback -> DENY
uppercase path: global fallback -> DENY
outside orders: global fallback -> DENY
~~~

**Explanation:** The first three lines match the numeric-ID GET regex; cases with letters, wrong method, extra path, or overly long IDs are rejected by the orders fallback. `/API/...` differs in casing so it misses the default regex. `/internal/health` hits the global fallback.

The text `REQUIRE order:read` here is **only a policy label**, not proof the user is actually allowed. In real Spring Security, `AuthorizationManager` checks authorities from `Authentication` and the service checks the resource.

## 15. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
|---|---|---|
| `^/api/orders/.*$` attached to `order:read` | Can capture approve/delete actions too | Narrow regex and explicit method |
| Ignoring query string | Requests with `?x=1` miss the rule | Optional query pattern or path matcher |
| Using `.` instead of `\.` | Matches unintended characters | Escape properly in regex and Java |
| Forgetting `\?` in URL regex | Question mark treated as a quantifier | Use `\\?` in Java strings |
| Not restricting GET/POST | POST may be handled by a read rule | Factory with `HttpMethod` |
| Placing broad rule before regex | Regex rule is never evaluated | Specific rule with right policy first |
| Using regex in `securityMatcher` without fallback | Requests may bypass security chains | Catch-all chain at the end |
| Assuming ID regex proves ownership | IDOR/BOLA | Tenant/owner policy in service |
| Using `.*` and nested quantifiers | Overmatching or CPU exhaustion | Bounded classes, benchmark |
| Building regex from client input | Regex injection, ReDoS | Static patterns |
| Relaxing firewall so unusual URLs match | Opens routing bypass risks | Keep strict normalization, test |
| Testing only valid URLs | Misses negative edge cases | Matrix of path/method/query/authority |
| Treating 404 as a Spring Security deny | Endpoint might simply not exist | Test chain, matcher, and real controller |

## 16. Review Checklist

- [ ] Is regex genuinely needed over a standard path matcher?
- [ ] Do you understand `servletPath + pathInfo + ?queryString` and context path?
- [ ] Are methods restricted when actions have different permissions?
- [ ] Are `\?`, `\.`, and backslashes properly escaped in Java strings?
- [ ] Should matching be case-sensitive or case-insensitive? Tested?
- [ ] Does the pattern have anchors and narrow segment bounds without abusing `.*`?
- [ ] Is rule order right: specific first, deny fallback last?
- [ ] If regex is in `securityMatcher`, is there a fallback chain for out-of-scope URLs?
- [ ] Have you tested URLs with queries, wrong methods, invalid IDs, oversized IDs, trailing slashes, strange paths, and encoding?
- [ ] Are permissions based on real authorities, not client-submitted IDs or tenants?
- [ ] Are there service-level checks for owner/tenant and business action?
- [ ] Has the pattern been reviewed for ReDoS and input length?
- [ ] Does the system use a gateway, custom servlet path, or reverse proxy rewrite? Tested end-to-end?

**Remember:** `RegexRequestMatcher` helps **identify an HTTP request with a specific shape**. It is only one link in authorization; a complete policy also requires chain coverage, rule order, authentication/authorities, and resource-level permissions.

## 17. Self-Check Questions

**1. Does RegexRequestMatcher only inspect the path and ignore the query string?**  
No. The JavaDoc describes matching `servletPath + pathInfo + queryString`; if a query exists, the string includes `?`.

**2. Will `^/api/orders/[0-9]+$` definitely match `/api/orders/42?expand=items`?**  
No; the query string can prevent that pattern from matching. Use a pattern with an optional query or a path matcher when only the path matters.

**3. How do you restrict a regex to HTTP GET?**  
Use `RegexRequestMatcher.regexMatcher(HttpMethod.GET, pattern)` in versions supporting this factory.

**4. Why can `.+` make read permission apply too broadly?**  
It can consume slashes and segments after the ID, including `/approve`.

**5. What happens if a regex in `securityMatcher` does not match?**  
That chain is not selected; if no other chain or fallback matches, the URL may fall outside Spring Security filters.

**6. Are a valid URL ID and `order:read` authority enough to read any order?**  
No. You must check owner/tenant and resource scope.

**7. Should regex be used to validate JSON body data or export permissions by query?**  
It should not be used as the sole validator/policy; use DTO validation, custom matchers, and service authorization as appropriate.

**8. Why must you test `?`, uppercase letters, POST, and extra slashes?**  
Because regex/method/path matching can yield different outcomes and cause privileged rules to be bypassed.

## 18. Official Sources

- Spring Security – Authorize HttpServletRequests, *Matching Using Regular Expressions*: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security – RegexRequestMatcher JavaDoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/util/matcher/RegexRequestMatcher.html
- Spring Security – Java Configuration and securityMatcher: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security – HttpFirewall: https://docs.spring.io/spring-security/reference/servlet/exploits/firewall.html
- Java SE 17 – java.util.regex.Pattern: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html
