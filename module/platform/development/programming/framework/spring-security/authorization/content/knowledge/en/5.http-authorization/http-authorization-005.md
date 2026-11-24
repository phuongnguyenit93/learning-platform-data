# Specific Rules Before General Rules

> **Topic:** Spring Security - authorization  
> **Knowledge area:** HTTP Authorization  
> **Goal:** Understand why `requestMatchers` ordering decides whether a request is allowed or denied, place narrow exceptions before general rules when they can match the same request, distinguish `SecurityFilterChain` selection order from rule order inside `authorizeHttpRequests`, and write tests proving no sensitive endpoint is shadowed by an overly broad rule.

## 1. A small ordering bug can become a permission vulnerability

Suppose an application has three paths:

- `GET /api/reports/public/help`: anyone can read it.
- `GET /api/reports/admin/audit`: only admins can read it.
- `GET /api/reports/annual`: users with `reports:read` can read it.

A configuration that looks reasonable at a glance:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/reports/**")
        .hasAuthority("reports:read")
    .requestMatchers(HttpMethod.GET, "/api/reports/admin/**")
        .hasRole("ADMIN")
    .requestMatchers(HttpMethod.GET, "/api/reports/public/**")
        .permitAll()
    .anyRequest().denyAll()
);
```

However, `GET /api/reports/admin/audit` **already matches** the broad pattern `/api/reports/**` in the first rule. If Alice has `reports:read` without being an admin, Alice can pass the HTTP authorization step for the admin endpoint. The `hasRole("ADMIN")` rule below is not used to "tighten" the earlier decision.

Similarly, an anonymous visitor sending `GET /api/reports/public/help` also hits the first rule checking `reports:read` and gets denied, even though `permitAll()` appears below.

**Core lesson:** with `authorizeHttpRequests`, rules are generally tried **in declaration order; the first rule whose request matcher matches decides at the HTTP layer**. Spring Security does not automatically sort from "longest path" to "shortest path"; nor does it combine the results of every matching rule with AND by default.

## 2. Proper fix: put narrow cases before broad cases

For the same three routes, write:

```java
http.authorizeHttpRequests(auth -> auth
    // Narrow public exception, for GET only.
    .requestMatchers(HttpMethod.GET, "/api/reports/public/**")
        .permitAll()

    // Sensitive area must be checked before the general pattern.
    .requestMatchers(HttpMethod.GET, "/api/reports/admin/**")
        .hasRole("ADMIN")

    // Remaining GET reports require the general read permission.
    .requestMatchers(HttpMethod.GET, "/api/reports/**")
        .hasAuthority("reports:read")

    // Other methods/paths are not opened automatically.
    .anyRequest().denyAll()
);
```

Expected outcomes, with the default role prefix `ROLE_`:

| Request | Identity | First matching rule | HTTP decision |
| --- | --- | --- | --- |
| `GET /api/reports/public/help` | Anonymous | `/api/reports/public/**` | ALLOW via `permitAll` |
| `GET /api/reports/admin/audit` | `ROLE_ADMIN` | `/api/reports/admin/**` | ALLOW |
| `GET /api/reports/admin/audit` | `reports:read`, no admin | `/api/reports/admin/**` | DENY |
| `GET /api/reports/annual` | `reports:read` | `/api/reports/**` | ALLOW |
| `GET /api/reports/annual` | Anonymous | `/api/reports/**` | DENY |
| `POST /api/reports/public/help` | Anonymous | `anyRequest` | DENY |
| `PATCH /api/reports/annual` | `reports:read` | `anyRequest` | DENY |
| `GET /api/unknown` | Logged in | `anyRequest` | DENY |

Key point: `/api/reports/public/**` should not be opened for every HTTP method if the feature only makes GET public. Using `requestMatchers(HttpMethod.GET, ...)` expresses the intent: **both path and HTTP operation determine whether the rule matches**.

Beyond HTTP checks, if a report belongs to a specific tenant or has status constraints, the service still needs per-record permission checks. `ALLOW` on `hasAuthority("reports:read")` is not a license to read every object.

## 3. Accurate mental model: find the first matching rule, then evaluate it

A simplified representation of `RequestMatcherDelegatingAuthorizationManager`:

```text
request = (HTTP method, path, dispatch type, ...)
rules = [rule1, rule2, ..., ruleN]

for rule in rules in declaration order:
    if rule.matcher.matches(request):
        return rule.authorizationManager.authorize(authentication, request)

return result determined by fallback/no-match policy
```

The snippet above is only **pseudocode describing first-match**, not the complete Spring Security source code. Real implementations also handle `Supplier<Authentication>`, exceptions, matcher context, abstain/deny decisions, and other version-specific details. What you must understand is: once a first matching rule is selected, the system **does not proceed to try rules below** merely because the first rule's manager denied access.

Here is an easy trap:

```text
Rule 1: /api/**        -> authenticated()
Rule 2: /api/admin/**  -> hasRole("ADMIN")
```

A `GET /api/admin/users` request matches rule 1. If logged in, it passes the check at rule 1. Rule 2 adds no admin requirement. Reversing the order:

```text
Rule 1: /api/admin/**  -> hasRole("ADMIN")
Rule 2: /api/**        -> authenticated()
```

Now a request to `/api/admin/users` is handled by rule 1; only other API requests go to rule 2.

**Do not sort mechanically by character count.** The criterion is the coverage of the matcher and the desired policy. Two disjoint rules can be placed in any order with the same outcome; two overlapping rules requiring different decisions need an intentional order.

## 4. Narrow vs broad matchers: thinking in sets

Treat each `RequestMatcher` as a set of requests it can match.

- Set `A`: all `GET /api/reports/public/**`.
- Set `B`: all `GET /api/reports/**`.
- Set `C`: all `GET /api/**`.

With path matching syntax as above and standard request path handling, conceptually `A ⊂ B ⊂ C`. Since `A` lies inside `B`, placing `B` first leaves rule `A` below with no chance to process requests belonging to `A`.

Permission example:

```text
GET /api/reports/public/help
  ├─ matches public/**        -> permitAll
  ├─ matches reports/**       -> reports:read
  └─ matches api/**           -> authenticated

If public/** is first: permitAll.
If reports/** is first: requires reports:read.
If api/** is first: requires only authenticated.
```

**There is no automatic "more specific matcher wins" rule.** Outcomes change when order changes. More specific does not always mean more restrictive: `permitAll` is a **less restrictive** exception, yet it still needs to come before the general permission rule if the resource is genuinely public.

### What counts as "more specific"?

During configuration review, examine the combination of:
- **HTTP method:** `GET` is narrower than all methods.
- **Path:** `/api/admin/users/**` is narrower than `/api/admin/**`.
- **Dispatcher type:** `ERROR` or `FORWARD` can create cases distinct from the main request.
- **Custom matcher attributes:** host, headers, media type, or other predicates if the project actually uses them.
- **Intended policy:** if two matchers both match yet require the exact same policy, order creates no permission difference at that point.

Do not define "specific" by a longer string. A custom matcher can match more broadly by method/header than its path string suggests. Verify actual matcher behavior instead of guessing from names.

## 5. Two different levels of ordering: selecting SecurityFilterChain vs selecting a rule

A subtle detail of Spring Security Servlet is that **chain ordering** and **authorization rule ordering within a chain** are completely different.

```text
HTTP request
    |
    v
DelegatingFilterProxy / FilterChainProxy
    |
    | 1. Select FIRST SecurityFilterChain whose securityMatcher matches
    v
Selected SecurityFilterChain
    |
    | authentication, context, other security filters
    v
AuthorizationFilter
    |
    | 2. Select FIRST requestMatcher whose rule matches
    v
AuthorizationManager -> ALLOW / DENY
```

| Level | Common API | Selected in order | Consequence |
| --- | --- | --- | --- |
| Chain selection | `http.securityMatcher(...)` combined with `@Order` on `SecurityFilterChain` | First matching chain in `FilterChainProxy`'s list | Subsequent chains do not stack protections |
| HTTP rule selection inside a chain | `authorizeHttpRequests(...requestMatchers(...))` | First matching rule | Subsequent rules are not ANDed on |
| Method-level policy | `@PreAuthorize`, `@PostAuthorize` | Spring AOP interceptors by pointcut/order | Separate check layer occurring on matching method calls |
| Service-layer policy | Business policy by actor/resource | Per written code/use case | Must explicitly protect object/tenant/invariants |

A common mistake is creating chain A for `/api/**` and chain B for `/api/admin/**`, thinking "chain B will additionally check admin role." If A comes first, B may never be selected for `/api/admin/**`.

## 6. Multiple SecurityFilterChains example: admin API must match chain first

Suppose an application has an admin API using its own mechanism and a regular API:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class MultipleChainsSecurity {

    @Bean
    @Order(1)
    SecurityFilterChain adminApi(HttpSecurity http) throws Exception {
        http.securityMatcher("/api/admin/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasRole("ADMIN")
            );
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain regularApi(HttpSecurity http) throws Exception {
        http.securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated()
            );
        return http.build();
    }
}
```

**This is a structural snippet**, not a complete application config: it omits authentication methods, CSRF, session, error handling, and protection for routes outside `/api/**`. Key points:

1. `/api/admin/users` matches both `/api/admin/**` and `/api/**`, yet the admin chain comes first thanks to `@Order(1)`.
2. `/api/documents` does not match the admin chain, so it is handled by the regular API chain.
3. For the admin chain, `anyRequest().hasRole("ADMIN")` applies to all requests **belonging to the admin chain**.
4. For the regular chain, `authenticated()` only confirms authentication level, not functional or object permissions.
5. **If a fallback chain is missing**, a URL outside all `securityMatcher`s may go unprotected by any Spring Security filter chain. An explicit fallback must be designed.

If you swap `@Order` so the `/api/**` chain comes before the admin chain, the admin API may only require login and never reach the admin rule. Do not confuse this issue with `requestMatchers` order inside a single chain.

When you do not genuinely need multiple chains with different authentication mechanisms, a single chain with narrow rules before broad rules is usually easier to audit. Multiple chains should only be used when clear security boundaries exist, such as separate web sessions and bearer APIs.

## 7. Security-complete configuration: explicit public, functional rules, then fallback

A readable way to organize rules:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class HttpAuthorizationConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            // 1. Public endpoints that genuinely need to be public.
            .requestMatchers(HttpMethod.GET, "/actuator/health")
                .permitAll()
            .requestMatchers(HttpMethod.GET, "/api/docs/public/**")
                .permitAll()

            // 2. Sensitive areas or narrow exceptions.
            .requestMatchers("/api/admin/**")
                .hasRole("ADMIN")
            .requestMatchers(HttpMethod.DELETE, "/api/docs/**")
                .hasAuthority("document:delete")
            .requestMatchers(HttpMethod.PATCH, "/api/docs/**")
                .hasAuthority("document:edit")
            .requestMatchers(HttpMethod.GET, "/api/docs/**")
                .hasAuthority("document:read")

            // 3. Broad rules only if intentional.
            .requestMatchers("/api/profile/**")
                .authenticated()

            // 4. Closed by default.
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
```

The snippet above illustrates **ordering**. In a real application, `/actuator/health` may use a separate management context/port; match the actual paths. Login/bearer mechanisms, exception handling, CORS, and CSRF must also be configured properly. Specific resources still need business policies.

Read in order:
- `GET /api/docs/public/guide` hits `permitAll()` before the `/api/docs/**` rules.
- `DELETE /api/docs/42` hits `document:delete` before general docs rules.
- `GET /api/docs/42` hits `document:read`.
- `GET /api/admin/users` hits the admin area and requires `ROLE_ADMIN`.
- `GET /api/profile/me` requires authentication.
- `POST /api/unknown` falls into `denyAll`.

Note that `.requestMatchers("/api/admin/**").hasRole("ADMIN")` covers all HTTP methods on the admin API. That is an intentional choice; if the admin API needs different permissions for GET and POST, define narrower HTTP-method rules ahead of it and use a fallback for the rest.

## 8. Common scenario: public GET while writes must stay protected

Suppose the product has a public page:

```text
GET    /api/articles/42  -> public
POST   /api/articles     -> editor
PATCH  /api/articles/42  -> editor
DELETE /api/articles/42  -> administrator
```

Dangerous configuration:

```java
.requestMatchers("/api/articles/**").permitAll()
.requestMatchers(HttpMethod.POST, "/api/articles/**").hasRole("EDITOR")
.requestMatchers(HttpMethod.DELETE, "/api/articles/**").hasRole("ADMIN")
```

The first rule **does not restrict the HTTP method**, so POST/DELETE can also hit `permitAll` at the HTTP authorization step. The rules below become ineffective for matching requests.

A clearer design:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/articles/**")
        .permitAll()
    .requestMatchers(HttpMethod.HEAD, "/api/articles/**")
        .permitAll() // If HEAD is also public per contract.
    .requestMatchers(HttpMethod.DELETE, "/api/articles/**")
        .hasRole("ADMIN")
    .requestMatchers(HttpMethod.POST, "/api/articles/**")
        .hasRole("EDITOR")
    .requestMatchers(HttpMethod.PATCH, "/api/articles/**")
        .hasRole("EDITOR")
    .anyRequest().denyAll()
);
```

In practice, verify whether `POST /api/articles` matches `/api/articles/**` under your version's matcher strategy; for maximum certainty, declare the exact path `/api/articles` for POST. Do not migrate from Ant-style to `PathPattern` without testing root paths, subpaths, trailing slashes, and other cases.

Especially for CORS-enabled APIs, do not open all methods on a path just to make preflight work. Configure CORS/preflight cleanly instead of putting `permitAll("/api/**")` on all requests.

## 9. anyRequest(): the final general catch-all rule

`anyRequest()` typically acts as the catch-all for all requests not handled by preceding rules. Options:

- `anyRequest().denyAll()`: deny by default. Suitable for APIs that only expose listed routes.
- `anyRequest().authenticated()`: by default all remaining routes require an authenticated user; **does not guarantee** functional roles/permissions.
- `anyRequest().permitAll()`: unlisted routes are opened publicly at the authorization step; use only if that is genuinely the product policy.

For systems requiring strict access control, **default deny** prevents new routes from accidentally opening when a developer adds a controller and forgets a rule. However, if an app has many general endpoints, a team may intentionally use `authenticated()` as fallback and protect features at the method/domain layer; document the policy and test it.

`anyRequest()` is the catch-all for the scope of `authorizeHttpRequests` in the selected chain; it does not replace `securityMatcher` and does not extend the chain's scope to all URLs. Always place `anyRequest` last; DSLs can detect rules declared after a catch-all as invalid instead of continuing normally.

Example:

```java
// Good: specific rules first, catch-all last.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
```

Here `GET /api/admin/users` requires the admin role, while `GET /api/tasks` only requires authentication **at the HTTP layer**. If `/api/tasks` has user-specific read permissions, the service must perform further checks.

## 10. "Specific first" does not mean sorting longer strings before shorter strings

Consider:

```text
GET /api/invoices/123
GET /api/invoices/search
GET /api/invoices/admin/export
```

A search endpoint can overlap with `/{id}` depending on route mapping. A `RequestMatcher` covering `/api/invoices/*` can intersect with `/api/invoices/search`. If different permissions are required, make it explicit:
- Matcher for exact `/api/invoices/search`.
- Matcher for export/admin path.
- Matcher for invoice details by ID.
- Policy by HTTP method.
- Tenant/owner scope and resource permissions in the service.

A rule that "looks narrower" can actually have broader scope due to wildcards, custom matchers, or servlet path configuration. Measure with real matcher tests.

When two rules are **disjoint**, order does not change the decision:
- `GET /api/articles/**`
- `POST /api/orders/**`

When two rules overlap yet share **the same policy**, order may not change ALLOW/DENY; still, keep the structure easy to review and maintain.

**Quantitative takeaway:** policy authors must visualize the set of requests each matcher covers, rather than merely counting path segments.

## 11. Understand the difference between path matching and business permission

A request matcher typically decides based on **path, HTTP method, or request attributes**. It does not verify business data inside the resource itself.

Suppose:

```java
.requestMatchers(HttpMethod.GET, "/api/projects/*/documents/**")
    .hasAuthority("document:read")
```

A user with `document:read` passes the request guard. However:
- Does the project ID in the URL belong to that user's tenant?
- Does the document ID actually belong to that project?
- Does the user have a grant on that specific document?
- Has the document been archived or marked confidential?
- Is there a download/export endpoint with different permissions?

These questions require an actor–resource–context policy in the service or a custom `AuthorizationManager` with trusted facts. A URL rule does not turn any `/{id}` into object-level authorization.

Service example (integration snippet, not a standalone class):

```java
@PreAuthorize("hasAuthority('document:read')")
public DocumentView readDocument(long projectId, long documentId) {
    Actor actor = actorResolver.requireActor();

    Document document = repository.findByIdAndProjectIdAndTenantId(
        documentId, projectId, actor.tenantId()
    ).orElseThrow(DocumentNotFoundException::new);

    if (!documentPolicy.canRead(actor, document)) {
        throw new AccessDeniedException("Not allowed");
    }

    return mapper.toView(document);
}
```

Types `Actor`, `Document`, `DocumentView`, repository, policy, and mapper belong to the application; the example shows responsibilities and is not built into Spring. Putting narrow rules in the right place **and** checking the object inside the use case are both required to prevent IDOR/BOLA.

## 12. Standalone Java 17+: simulating first-match, broken then fixed

The example below requires no Spring and does not try to replicate `PathPatternRequestMatcher`. It accurately simulates **scanning top-to-bottom and picking the first matching rule** using exact paths or `/**` prefixes. The goal is to see how a single reordering changes outcomes even with the exact same set of rules.

Save as file `FirstMatchRulesDemo.java`:

```java
import java.util.List;
import java.util.Set;

public class FirstMatchRulesDemo {

    record Actor(boolean authenticated, Set<String> authorities) {}

    record Request(String method, String path) {}

    record Rule(
            String name,
            String method,
            String pathPattern,
            String requirement
    ) {
        boolean matches(Request request) {
            if (!method.equals("*") && !method.equals(request.method())) {
                return false;
            }

            if (pathPattern.equals("/**")) {
                return true;
            }
            if (pathPattern.endsWith("/**")) {
                String root = pathPattern.substring(
                    0, pathPattern.length() - 3
                );
                return request.path().equals(root)
                    || request.path().startsWith(root + "/");
            }
            return request.path().equals(pathPattern);
        }

        boolean allows(Actor actor) {
            return switch (requirement) {
                case "PERMIT_ALL" -> true;
                case "DENY_ALL" -> false;
                case "AUTHENTICATED" -> actor.authenticated();
                default -> actor.authenticated()
                    && actor.authorities().contains(requirement);
            };
        }
    }

    static String decide(
            List<Rule> rules, Actor actor, Request request
    ) {
        for (Rule rule : rules) {
            if (rule.matches(request)) {
                String decision = rule.allows(actor)
                    ? "ALLOW" : "DENY";
                return decision + " via " + rule.name();
            }
        }
        return "DENY via no-match";
    }

    public static void main(String[] args) {
        Actor anonymous = new Actor(false, Set.of());
        Actor reader = new Actor(true, Set.of("reports:read"));
        Actor admin = new Actor(true, Set.of("ROLE_ADMIN"));

        Request publicReport = new Request(
            "GET", "/api/reports/public/help"
        );
        Request adminReport = new Request(
            "GET", "/api/reports/admin/audit"
        );
        Request annualReport = new Request(
            "GET", "/api/reports/annual"
        );
        Request writeReport = new Request(
            "PATCH", "/api/reports/annual"
        );

        Rule generalRead = new Rule(
            "reports-general", "GET",
            "/api/reports/**", "reports:read"
        );
        Rule adminOnly = new Rule(
            "reports-admin", "GET",
            "/api/reports/admin/**", "ROLE_ADMIN"
        );
        Rule publicOnly = new Rule(
            "reports-public", "GET",
            "/api/reports/public/**", "PERMIT_ALL"
        );
        Rule denyFallback = new Rule(
            "fallback", "*", "/**", "DENY_ALL"
        );

        // WRONG: general rule shadows the special exceptions.
        List<Rule> wrong = List.of(
            generalRead, adminOnly, publicOnly, denyFallback
        );

        // RIGHT: specific exceptions first, general rule last.
        List<Rule> fixed = List.of(
            publicOnly, adminOnly, generalRead, denyFallback
        );

        System.out.println("Wrong reader-admin: "
            + decide(wrong, reader, adminReport));
        System.out.println("Wrong anonymous-public: "
            + decide(wrong, anonymous, publicReport));
        System.out.println("Wrong admin-admin: "
            + decide(wrong, admin, adminReport));

        System.out.println("Fixed reader-admin: "
            + decide(fixed, reader, adminReport));
        System.out.println("Fixed admin-admin: "
            + decide(fixed, admin, adminReport));
        System.out.println("Fixed anonymous-public: "
            + decide(fixed, anonymous, publicReport));
        System.out.println("Fixed reader-annual: "
            + decide(fixed, reader, annualReport));
        System.out.println("Fixed anonymous-annual: "
            + decide(fixed, anonymous, annualReport));
        System.out.println("Fixed reader-PATCH: "
            + decide(fixed, reader, writeReport));
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac FirstMatchRulesDemo.java
java FirstMatchRulesDemo
```

**Exact** output:

```text
Wrong reader-admin: ALLOW via reports-general
Wrong anonymous-public: DENY via reports-general
Wrong admin-admin: DENY via reports-general
Fixed reader-admin: DENY via reports-admin
Fixed admin-admin: ALLOW via reports-admin
Fixed anonymous-public: ALLOW via reports-public
Fixed reader-annual: ALLOW via reports-general
Fixed anonymous-annual: DENY via reports-general
Fixed reader-PATCH: DENY via fallback
```

Meaning:
1. In the wrong order, a user with only `reports:read` gets into the admin URL; that is **unintended privilege escalation**.
2. Anonymous visitors cannot read the public report even though the app wrote a `permitAll` rule below.
3. Even an admin can be denied when lacking `reports:read`, because the admin rule never gets a turn.
4. After fixing, the admin and public rules apply before the general reports rule.
5. `PATCH` matches no `GET` rule and is rejected by the `denyAll` fallback.

**Demo limitations:** the hand-written `Rule.matches` only handles exact paths and `/**` suffixes; it cannot replace Spring MVC matchers, and lacks servlet paths, queries, URL decoding, dispatcher types, security contexts, JWTs, or caches. In Spring, **test the matcher of the version you run** instead of carrying demo `matches` functions into production.

## 13. Tracing a request's outcome step by step

Assume the correct configuration from section 2.

### Scenario A — GET public report

```text
GET /api/reports/public/help
1. requestMatchers(GET, "/api/reports/public/**")? YES
2. permitAll() -> ALLOW at HTTP authorization
3. Do not evaluate admin/report-read rules below
4. Controller/service continues per other filters and protections
```

`permitAll()` does not mean disabling all security. CSRF, sessions, authentication filters, or custom filters can still run as configured. For read-only GETs, CSRF is normally not required, though handlers must still avoid non-standard side effects.

### Scenario B — Regular user calls admin URL

```text
GET /api/reports/admin/audit
1. public matcher? NO
2. admin matcher? YES
3. hasRole("ADMIN") -> requires ROLE_ADMIN
4. Alice only has reports:read -> DENY
5. Do not try general "/api/reports/**" to obtain ALLOW
```

This is the crucial point: **DENY at the selected rule does not make the engine try the next rule**.

### Scenario C — User with permission reads regular report

```text
GET /api/reports/annual
1. public matcher? NO
2. admin matcher? NO
3. general reports matcher? YES
4. hasAuthority("reports:read") -> ALLOW
5. Service still checks tenant, owner, visibility if the resource is restricted
```

### Scenario D — Undeclared method

```text
PATCH /api/reports/annual
1. Any GET matchers? NO
2. anyRequest()? YES
3. denyAll() -> DENY
```

Never assume a GET rule for a path also protects or allows POST/PATCH/DELETE on that same path. Permissions must be defined for each kind of operation.

## 14. permitAll, authenticated, hasAuthority, hasRole, and denyAll are distinct decisions

| Rule | Meaning at the HTTP authorization step | What it does not guarantee |
| --- | --- | --- |
| `permitAll()` | Permits matching requests without requiring a specific authority | Does not disable all filters; does not promise methods/services won't deny |
| `authenticated()` | Requires an identity considered authenticated by Spring Security trust rules | Does not check roles/permissions or resource access |
| `fullyAuthenticated()` | Requires full authentication, not just remember-me | Does not replace business policies |
| `hasAuthority("x")` | Checks authority string `x` | Does not infer role hierarchy unless configured |
| `hasRole("ADMIN")` | By default checks the `ROLE_ADMIN` authority | Does not guarantee access across all tenants/objects |
| `denyAll()` | Denies all requests reaching this rule | Does not protect URLs outside the `SecurityFilterChain` |
| Custom manager | Decides by application-defined logic | Only valid if facts and matcher order are accurate |

One role does not automatically carry every permission just because its name sounds "higher." For instance, `ROLE_ADMIN` and `reports:read` are two distinct authorities; `hasRole("ADMIN")` checks `ROLE_ADMIN` by default, while `hasAuthority("reports:read")` looks for that exact string.

Such confusion often leads teams to "fix" issues by loosening `/api/**.permitAll()`. That only masks an immediate config bug and can open a much larger hole. Find the rule actually selected and verify the principal has the right authority.

## 15. Specific rule before general rule in an admin screen

Another common configuration:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/dashboard/status")
        .permitAll()
    .requestMatchers("/dashboard/admin/**")
        .hasRole("ADMIN")
    .requestMatchers("/dashboard/**")
        .authenticated()
    .anyRequest().denyAll()
);
```

This flow has three goals:
- Allow viewing public status without logging in.
- Enforce stricter permissions on the admin area.
- Require login for the rest of the dashboard.

If `/dashboard/**.authenticated()` is moved up first, logged-in users can reach `/dashboard/admin/**` without passing the admin role check at the HTTP layer. If `/dashboard/**.hasRole("USER")` is placed first, the public status page can be blocked.

**Not every admin route should be allowed simply for having ROLE_ADMIN**. For example, pages modifying permissions or executing transactions may require MFA, approval, separation of duties, and resource policies. The HTTP layer is only one part of the decision chain.

## 16. Overlapping cases easily overlooked

### 16.1. Admin before general API

Wrong:

```java
.requestMatchers("/api/**").authenticated()
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

Right for protecting admin separately:

```java
.requestMatchers("/api/admin/**").hasRole("ADMIN")
.requestMatchers("/api/**").authenticated()
```

### 16.2. Public read-only API before permission-protected API

Wrong:

```java
.requestMatchers("/api/catalog/**").hasAuthority("catalog:read")
.requestMatchers(HttpMethod.GET, "/api/catalog/public/**").permitAll()
```

If public is genuinely an exception to the catalog rule, reverse these two rules. Also restrict the HTTP method so POST/PATCH are not opened on the public path.

### 16.3. Exact endpoint before prefix

```java
.requestMatchers(HttpMethod.GET, "/api/users/me")
    .authenticated()
.requestMatchers(HttpMethod.GET, "/api/users/**")
    .hasRole("ADMIN")
```

If "me" lets ordinary users view their own profile, `/me` must go before the broad admin area. Still, the service must bind the profile to the **actual principal**, never letting clients swap the ID to another user.

### 16.4. Special path vs parameterized path

```java
.requestMatchers(HttpMethod.GET, "/api/orders/search")
    .hasAuthority("orders:search")
.requestMatchers(HttpMethod.GET, "/api/orders/*")
    .hasAuthority("orders:read")
```

Test for real when a controller has both `/search` and `/{orderId}`. Wildcard matchers and path variable matching can depend on how Spring Security selects matchers in the current version.

### 16.5. Health check before login-required rule

```java
.requestMatchers(HttpMethod.GET, "/healthz").permitAll()
.anyRequest().authenticated()
```

Exposing health is a deployment decision, not a default. Endpoints exposing sensitive details like dependencies, env, or metrics require dedicated permissions and access restrictions.

### 16.6. Error/forward dispatches

If an application must allow error pages to render even for denied requests, a rule for dispatcher types such as `ERROR`/`FORWARD` with an appropriate scope may be needed. Place this rule before `anyRequest` when justified and test its behavior. Never open all dispatches automatically just to eliminate 403 errors without understanding the impact.

## 17. Spring matchers must be tested with real URLs

There are matcher variants such as path patterns for Servlet/MVC, `AntPathRequestMatcher` in older versions/apps, and custom `RequestMatcher`s. Different Spring Security versions have different conventions/recommendations for matchers. **There is no guarantee** that `/api/items/**` behaves identically across every stack, servlet path, and configuration.

Dimensions worth testing:
- Exact path `/api/items`, subpath `/api/items/42`, trailing slash `/api/items/`.
- Path segment `*` vs `**` and path variable `{id}` in the actual framework/matcher.
- Servlet path/context path when deployed under a prefix.
- HTTP methods HEAD/OPTIONS vs GET, and method override if the application supports it.
- Paths with encoded characters, dots, non-standard separators, or confusing strings.
- Dispatcher types such as REQUEST/ERROR/FORWARD/ASYNC.
- Reverse proxy/path rewrites before the request reaches the Servlet container.
- Whether MVC controller mappings and Security matchers actually agree on the path.

Do not take `MockMvc` passing on one clean URL as proof that ugly variants cannot bypass it. Tests should cover paths actually accepted by both the application and reverse proxy. If you have a custom matcher, test it independently before using it as a security boundary.

## 18. RequestMatchers are not additive rules

A configuration like:

```java
.requestMatchers("/api/orders/**").authenticated()
.requestMatchers("/api/orders/**").hasAuthority("orders:read")
```

**Does not mean** "must be logged in **and** have orders:read." The first matcher already matches every URL in the same set, so the second rule never gets a chance to decide.

To require an authority, in normal Spring Security contexts `hasAuthority("orders:read")` on a trusted `Authentication` already covers the authority loaded from the appropriate authentication mechanism. If a policy requires a special authentication level alongside a permission, use a composite `AuthorizationManager`, method policy expression, or appropriate helper instead of writing two identical matchers hoping they stack.

You can build a custom rule combining conditions:
- Has authority `orders:read`.
- Is a member of the tenant.
- Meets the required MFA level.
- Resource is within readable scope.

Still, avoid stuffing every object condition into a request matcher before you even have the real resource; service/policy layers are usually a clearer place.

## 19. Matcher order does not change overall filter processing order

Another misconception: putting `permitAll` at the top skips `CsrfFilter`, authentication filters, `CorsFilter`, or an unrelated custom filter. `authorizeHttpRequests` only defines rules for the **request authorization step** of the selected chain.

For example:
- `POST` can still be blocked by CSRF in a session-based app even if the later matcher is `permitAll`.
- An invalid Bearer token may be rejected by an authentication filter before `permitAll` logic has a chance to let a public request through, depending on filter/token handling.
- CORS preflight may need configuration before authorization, because OPTIONS requests do not carry cookies/tokens the same way main requests do.
- A custom filter before `AuthorizationFilter` can return a response or throw an exception regardless of rules defined below.

Thus, if a test sees 401/403, you cannot conclude "the specific rule did not beat the general rule" until you identify which **chain**, **filter**, **matcher**, **authentication**, and **handler** actually participated.

## 20. Test matrix: proper order requires both positive and negative tests

Take the configuration in section 2. Create the following test suite:

| Request | Principal | Expected |
| --- | --- | --- |
| GET public report | Anonymous | ALLOW |
| GET public report | Logged in | ALLOW |
| GET admin report | `ROLE_ADMIN` | ALLOW |
| GET admin report | Only `reports:read` | DENY |
| GET admin report | Only `ROLE_USER` | DENY |
| GET annual report | `reports:read` | ALLOW |
| GET annual report | Only `ROLE_ADMIN` | DENY if not mapped to `reports:read` |
| GET annual report | Anonymous | DENY |
| PATCH annual report | `reports:read` | DENY |
| POST public report | Anonymous | DENY |
| GET undeclared route | Logged in | DENY |

The two tests most effective at catching ordering bugs:
1. **A user with only general permissions cannot access a privileged endpoint** (verifies no bypass).
2. **Anonymous users still reach genuinely public endpoints** (verifies exceptions are not shadowed).

If you only test that an admin user succeeds on the admin endpoint, you may **miss** that an ordinary user can also get in due to a `/api/**.authenticated()` matcher placed earlier.

### MockMvc example testing HTTP rules

The snippet below is a **Spring Security Test snippet**, not a standalone Java program: it requires `MockMvc`, real controllers or suitable fixtures, the `spring-security-test` dependency, and the `SecurityFilterChain` configuration under test.

```java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@Test
void readerCannotAccessAdminReport() throws Exception {
    mvc.perform(get("/api/reports/admin/audit")
            .with(user("alice").authorities(
                new SimpleGrantedAuthority("reports:read")
            )))
       .andExpect(status().isForbidden());
}

@Test
void adminCanAccessAdminReport() throws Exception {
    mvc.perform(get("/api/reports/admin/audit")
            .with(user("admin").roles("ADMIN")))
       .andExpect(status().isOk());
}

@Test
void anonymousCanReadPublicReport() throws Exception {
    mvc.perform(get("/api/reports/public/help"))
       .andExpect(status().isOk());
}
```

The tests above assume the endpoints exist, return 200 when permitted, and no other handler/policy denies them; JUnit, `SimpleGrantedAuthority`, and test configuration imports are not shown in full. In real applications, verify whether the controller/service was invoked to distinguish HTTP DENY from business-policy denial.

### Testing that methods are not accidentally opened

For `POST/PATCH/DELETE` routes, besides testing "lacks permission," also confirm **no side effects occur**. If CSRF is enabled, supply a valid CSRF token for non-bearer tests so a 403 passing due to missing CSRF does not mask an authorization ordering bug.

```java
// Illustrative snippet inside a test with MockMvc configured.
mvc.perform(patch("/api/reports/annual")
        .with(csrf())
        .with(user("reader").authorities(
            new SimpleGrantedAuthority("reports:read")))
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"title\":\"changed\"}"))
   .andExpect(status().isForbidden());
```

If the PATCH endpoint does not exist, the response may be 404/405; build real fixtures/controllers and assert the exact contract instead of forcing 403 mechanically.

## 21. Testing multiple SecurityFilterChains: avoiding "broad chain shadows admin chain"

Suppose there are:
- Chain A: `securityMatcher("/api/**")`, `@Order(1)`, requires authenticated.
- Chain B: `securityMatcher("/api/admin/**")`, `@Order(2)`, requires admin.

Then admin requests enter chain A first. Testing the admin URL with a merely authenticated user catches the hole. Fix by putting chain B first, or moving the specific admin rule into chain A.

**Do not check only the HTTP status**; know which chain was selected:
- Enable Spring Security logs in dev/test environments when needed.
- Observe the matched filter chain.
- Write tests for anonymous, reader, admin, and requests outside all chains.
- Define a fallback chain if the system requires all requests to pass through Spring Security.
- Check differences between management port/actuator, MVC app, and external API gateway.

You can inspect `FilterChainProxy` in tests to check active chains under an appropriate setup, though avoid overly implementation-coupled tests when behavioral tests suffice. For security bugs, contract tests + resource policy tests + matcher config tests are more reliable than just reading annotations.

## 22. Migration and maintenance: adding a new route can alter old rules' meaning

A change that "looks like just adding an endpoint" can create an overlap:

**Initially:**

```java
.requestMatchers("/api/docs/**").hasAuthority("document:read")
.anyRequest().denyAll()
```

**Added later:**

```java
.requestMatchers("/api/docs/**").hasAuthority("document:read")
.requestMatchers("/api/docs/admin/**").hasRole("ADMIN")
.anyRequest().denyAll()
```

The admin line placed afterward can have no effect on admin requests. Code review must ask **which existing matchers is the new route a subset of?** If it is a subset and needs a different policy, move the narrow rule above.

A sound change process:

1. List the route, method, and desired permissions.
2. Identify existing `requestMatchers` covering the new route, especially `/api/**` and `anyRequest`.
3. Place the new rule before broader matchers **if they overlap and policies differ**.
4. Run representative tests for both new and old rules, not only happy paths.
5. Verify you did not accidentally open the same path for other HTTP methods.
6. With multiple chains, check which chain is selected **before** editing rules inside a chain.
7. Check method/domain policies; URL ALLOW is not a substitute for data-level permissions.

**Review tip:** broad wildcard `permitAll()` and `authenticated()` rules should be treated as high-risk change points, because they can shadow many sensitive rules beneath them.

## 23. Service-layer authorization still bears responsibility for the data

Even if HTTP rule ordering is completely right, `GET /api/reports/42` can still suffer from IDOR if a user with `reports:read` can read another tenant's object. Therefore, multi-layered defense should look like:

```text
HTTP layer:
  GET /api/reports/** -> reports:read

Application layer:
  actor = verified principal + tenant context
  report = load id=42 within actor's authorized tenant
  check actor canRead(report)
  ensure content/status/visibility rules
  then serialize report

Data layer:
  query scoped, least-privilege DB access,
  consistency for concurrent changes
```

Placing `/api/reports/admin/**` before `/api/reports/**` is necessary for HTTP authorization when two rules overlap; it does not solve per-document, per-invoice, or per-project permissions.

For list and export endpoints, filter by scope **directly in the query** where appropriate. Loading thousands of records and filtering afterward can leak metadata, break pagination, and cause N+1 queries. Likewise, file download or presigned URL endpoints need the same policy as metadata endpoints.

## 24. 401, 403, and 404 depend on where denial happened

Do not guess the rule wrongly from status alone:

| Case | Cause | Typical HTTP |
| --- | --- | --- |
| Anonymous hits login-required endpoint | Lacks valid authentication | 401 for bearer API; may redirect for form login |
| Logged in but lacks authority | Authorization rule denies | Usually 403 |
| Invalid CSRF token on session write | Blocked by `CsrfFilter` | Usually 403 |
| Resource does not exist | Domain/query not found | 404 |
| Resource exists but existence should be hidden from unauthorized users | Resource policy | May be 404 or 403 per contract |
| Request has no controller mapping | No endpoint to serve it | 404/405 depending on method/mapping |
| No matching chain or custom filter responds | Chain/filter config | App-dependent; may be a vulnerability if unprotected |

`ExceptionTranslationFilter` coordinates `AuthenticationEntryPoint` and `AccessDeniedHandler` for security exceptions passing through its handling scope. Controller advice, proxies, custom filters, and committed responses can alter the outcome. Verify the **actual rule and chain**, rather than attributing every 403 to "wrong order."

## 25. Typical mistakes and fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `/api/**.authenticated()` before `/api/admin/**.hasRole("ADMIN")` | Regular users pass HTTP admin checks | Put admin matcher first or pick the right chain |
| `/public/**.permitAll()` after `/**.authenticated()` | Public endpoints require login | Put public exceptions first |
| `/api/**.permitAll()` before specialized rules | Nullifies many HTTP restrictions | Limit public by path/method, deny fallback |
| Public `GET` declared without `HttpMethod` | May open write methods too | Permit only needed GET/HEAD, test POST/PATCH |
| Two identical matchers expecting AND | Second rule is never applied | Write one combined rule or policy |
| Chain `/api/**` before chain `/api/admin/**` | Admin chain is never selected | Order `@Order` with narrow chain first |
| No fallback chain | URLs outside chains may go unprotected by Spring Security | Design an appropriate/default chain |
| Using `authenticated()` as functional permission | Any logged-in user reaches sensitive routes | Use roles/authorities and resource policies |
| Thinking `hasRole("ADMIN")` matches literal `ADMIN` | Unexpected DENY | Understand default `ROLE_` prefix |
| Protecting only URLs, skipping services | Jobs/GraphQL/HTTP bypasses reach use cases | Method/domain policies and test alternate entry points |
| Testing only admin happy paths | Fails to catch readers entering admin | Negative tests with lower authorities |
| Testing 403 without CSRF token | False positive on authorization | Supply valid CSRF, verify denial point |
| Ignoring path rewrites/trailing slashes | Matcher differs from real controller | Test with real servlet path/proxy/version |
| Checking role while skipping tenant scope | IDOR/BOLA | Query and policy on object/tenant |
| Reordering without testing old routes | Public/private regressions | Request × method × principal matrix |

## 26. Review checklist when seeing new requestMatchers

Before merging a `SecurityFilterChain` or `authorizeHttpRequests` change:

1. **Which chain handles the URL?** Check `securityMatcher` and `@Order`, especially with overlapping chains.
2. **Which matcher matches first?** Trace representative requests before reading permissions beneath it.
3. **Is there a broader matcher above it?** If so, the new rule might never be used.
4. **Do public exceptions specify the right method/path?** Do not accidentally make POST/DELETE public.
5. **Are admin and sensitive features before broad fallbacks?** Negative-test with ordinary users.
6. **Is `anyRequest` declared last with an intentional denial level?**
7. **For roles/authorities, do prefixes and permissions map right?** `ROLE_ADMIN` differs from `reports:read`.
8. **Are routes outside SecurityFilterChain protected?** If not, why?
9. **Have path edge cases been tested?** Root path, subpath, slash, method, context path, custom matchers.
10. **Do HTTP ALLOWs have domain policies by resource/tenant?**
11. **Do tests isolate CSRF/authentication/CORS noise?** Prove the authorization rule itself blocks.
12. **Did adding a new route change public/private behavior of old routes?** Run regression tests.
13. **Are audit and logs enough to identify which chain/rule denied without leaking secrets?**

### Self-check exercises

**Question 1:** Given the rules:

```java
.requestMatchers("/admin/**").hasRole("ADMIN")
.requestMatchers("/**").authenticated()
```

Does a user with `ROLE_USER` accessing `/admin/users` pass HTTP authorization?  
→ **No.** The admin rule matches first and the user lacks `ROLE_ADMIN`.

**Question 2:** If you swap the two rules in Question 1, what happens?  
→ `/**.authenticated()` matches first. Logged-in users pass HTTP authorization on admin URLs; the rule below does not tighten it. This is a dangerous bug.

**Question 3:** You have `GET /public/help` that must be public, with fallback `anyRequest().authenticated()`. What goes first?  
→ `requestMatchers(HttpMethod.GET, "/public/**").permitAll()` before the catch-all. Only open intended methods.

**Question 4:** An app has `/api/**` chain at `@Order(1)` and `/api/admin/**` chain at `@Order(2)`. Is the admin rule in the second chain guaranteed to apply?  
→ **No.** The `/api/**` chain matches first. Fix the chain order or put the admin rule in the selected chain.

**Question 5:** A user has `reports:read`, yet report 42 belongs to another tenant. The HTTP matcher allows `GET /api/reports/**`. Can the user read report 42?  
→ **No**, if the domain policy scopes by tenant properly. General HTTP permissions do not replace object authorization.

**Question 6:** A POST test returns 403 and the team concludes it was because the POST matcher requires editor role. Is that conclusion certain?  
→ **Not yet.** 403 can come from CSRF, authentication, or another stage. Tests must hold a valid request constant and vary the authority to verify.

**Question 7:** You put `requestMatchers("/api/reports/**").hasAuthority("reports:read")` before `requestMatchers("/api/reports/public/**").permitAll()`. Can anonymous users read public reports?  
→ **No** under first-match because the general matcher matches first. Move the narrow rule above.

**Conclusion:** Whenever multiple HTTP rules can match the same request, **declaration order is part of the security policy**. Place narrow exceptions/scopes before broad matchers when different outcomes are needed, without expecting the framework to pick "the most specific path" automatically. Also verify both **`SecurityFilterChain` order** and **`requestMatchers` order**, always keep an intentional fallback, and test cases that ought to be denied.

## References

- [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — Servlet Architecture / SecurityFilterChain](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html)
- [Spring Security 6.5 — RequestMatcherDelegatingAuthorizationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/access/intercept/RequestMatcherDelegatingAuthorizationManager.html)
- [Spring Security 6.5 — Testing HTTP Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html)
