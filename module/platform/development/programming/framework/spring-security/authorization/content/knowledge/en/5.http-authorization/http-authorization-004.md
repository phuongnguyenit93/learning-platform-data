# Declaration Order and First-Match Rule in HTTP Authorization (Spring Security)

> **Scope:** HTTP request authorization in Spring Security Servlet / Spring MVC applications using `SecurityFilterChain` and `authorizeHttpRequests`. Goal: understand **which rule is chosen when multiple matchers match**, why a misplaced rule can expose endpoints, and how to verify with Java 17+ and Spring Boot.

## 1. Core rule: evaluate in order, take the **first match**

In a Spring Security configuration such as:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
~~~

Spring Security evaluates **`RequestMatcher → AuthorizationManager`** pairs in **declaration order**, from top to bottom. Upon encountering the first matcher that recognizes the request, the system applies **that matcher's authorization rule** and **does not continue looking for a rule below just because the user was denied by the first rule**.

For example, request `GET /api/admin/users`:

1. `/public/**` does not match.
2. `/api/admin/**` matches → requires the `ROLE_ADMIN` authority per the default role convention.
3. The `/api/**` rule would also match by path, yet **is not evaluated** because a first match has already occurred.
4. If the user only has `ROLE_USER` → result is **DENY**, and it **does not fall back** to the `authenticated()` rule to be allowed.

**Sentence to remember:** *Spring Security does not automatically pick "the most specific rule" from a misordered list; order is part of the security policy itself*. Official documentation describes `AuthorizationFilter` processing these pairs in order and applying **only the first match**.

### How to read the configuration as conditionals

~~~text
if path matches "/public/**":
    permitAll
else if path matches "/api/admin/**":
    require ROLE_ADMIN
else if path matches "/api/**":
    require authenticated
else:
    denyAll
~~~

This is a way to interpret **precedence order** in the example, not that Spring Security literally executes this `if/else` code.

**Consequence:** if a general rule stands before a sensitive rule, the sensitive rule can become **unreachable** (*shadowed/unreachable rule*).

## 2. Misordering example that overly broadens admin access

Consider the **wrong** configuration:

~~~java
// WRONG: general rule shadows the admin rule.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
~~~

For request `GET /api/admin/users` from Bob who is logged in but **not an admin**:

- `/api/**` matches immediately on the first line → only `authenticated()` is required.
- Bob is logged in → **ALLOW at HTTP authorization**.
- `/api/admin/**` below is **never evaluated** for this URL.

This can create an unauthorized-access vulnerability if the service/controller lacks its own check layer. Never reassure yourself that "the admin rule is more specific so Spring will prioritize it"; Spring Security does not reorder declared rules by specificity.

The **correct** configuration:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
~~~

Now regular users accessing `/api/admin/users` are blocked right at the admin rule. `/api/profile` does not match admin, so it falls into `/api/**` and is allowed if logged in.

### Comparing the two orders

| Request | User | First rule (wrong) | Wrong HTTP outcome | First rule (right) | Right outcome |
| --- | --- | --- | --- | --- | --- |
| `GET /api/admin/users` | Bob logged in, lacks admin | `/api/** → authenticated` | ALLOW | `/api/admin/** → hasRole("ADMIN")` | DENY |
| `GET /api/admin/users` | Carol with `ROLE_ADMIN` | `/api/** → authenticated` | ALLOW | `/api/admin/** → hasRole("ADMIN")` | ALLOW |
| `GET /api/profile` | Bob logged in | `/api/** → authenticated` | ALLOW | `/api/** → authenticated` | ALLOW |
| `GET /unknown` | Bob logged in | `anyRequest() → denyAll` | DENY | `anyRequest() → denyAll` | DENY |

The table assumes the request entered the right `SecurityFilterChain` with no other barriers like CSRF, method security, or business conditions. An ALLOW decision at HTTP **does not prove the entire application will grant access** if further checks follow behind it.

## 3. "First match" does not mean "first allowing rule"

This is an especially dangerous misconception.

Suppose:

~~~java
.requestMatchers("/finance/**").hasAuthority("finance:read")
.requestMatchers("/finance/**").hasRole("MANAGER")
~~~

A user has `ROLE_MANAGER` but **not** `finance:read`:

1. The first matcher `/finance/**` matches.
2. Checking `hasAuthority("finance:read")` yields **DENY**.
3. Spring Security **does not try the second matcher** looking for another ALLOW.

These two lines **do not** create "has permission OR is manager" logic, nor do they create "must have both permission AND manager" logic. They simply pick the first rule.

If the business logic wants **OR** (having either authority), you can use:

~~~java
.requestMatchers("/finance/**")
    .hasAnyAuthority("finance:read", "ROLE_MANAGER")
~~~

If it wants **AND** (having both authorities), on versions supporting `hasAllAuthorities` you can use:

~~~java
.requestMatchers("/finance/**")
    .hasAllAuthorities("finance:read", "ROLE_MANAGER")
~~~

The snippets above are **fragments** placed inside `authorizeHttpRequests`. When a policy involves resource attributes like tenant/ownership, use `access(customAuthorizationManager)` or a method/domain policy instead of trying to express it with two identical matchers.

**Summary:**

- **One selected matcher:** one rule for the request at the HTTP layer.
- **One rule can require multiple conditions:** combine them **inside the same rule/manager**.
- **Duplicate matchers do not automatically create OR/AND.**

## 4. Standard precedence order with multiple endpoint groups

An example document management API:

| Path | Meaning | Desired policy |
| --- | --- | --- |
| `/public/**` | Public content | `permitAll()` |
| `/api/admin/**` | System administration | `hasRole("ADMIN")` |
| `/api/reports/secret` | Sensitive report | `hasAuthority("report:read")` |
| `/api/reports/**` | Regular reports | `authenticated()` |
| `/api/**` | APIs without specific permissions | `denyAll()` |
| All other paths | Undeclared | `anyRequest().denyAll()` |

A safe order is:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/reports/secret").hasAuthority("report:read")
    .requestMatchers("/api/reports/**").authenticated()
    .requestMatchers("/api/**").denyAll()
    .anyRequest().denyAll()
);
~~~

In this example:

- `/api/admin/users` hits the admin rule before reaching `/api/**`.
- `/api/reports/secret` hits the rule requiring report-read permission before reaching `/api/reports/**`.
- `/api/reports/overview` hits the general reports rule.
- `/api/unknown-feature` is blocked by the `/api/** → denyAll()` rule.
- `/outside` matches no prior group and is blocked by `anyRequest().denyAll()`.

**Why have both `/api/**.denyAll()` and `anyRequest().denyAll()`?** In this example, they are equivalent in outcome for unlisted endpoints; the `/api/**` rule makes it clear to readers that uncategorized APIs are all blocked, while `anyRequest` is the overall catch-all. If you do not need to distinguish the group, you can keep just the final fallback.

### Rules for designing order

1. **Specific exceptions before broad rules**: `/api/admin/**` before `/api/**`.
2. **Sensitive permission checks before general login conditions**: `/api/reports/secret` before `/api/reports/**`.
3. **Explicit list of public paths**: only use `permitAll()` on genuinely public endpoints.
4. **Fallback at the end**: `anyRequest().denyAll()` so new endpoints do not open accidentally.
5. **Avoid meaningless duplicate matchers**: a later matcher already shadowed by an earlier rule is usually a sign of misordering.
6. **Test overlapping regions**, not just typical paths, because bugs happen when two or more patterns match together.

There is no formula like "longer path string always takes precedence." The **actual DSL order** decides whenever patterns overlap.

## 5. Matching by HTTP method: order still matters

In REST APIs, the same path pattern can require different permissions per method:

- `GET /api/documents/42` → `document:read`.
- `POST /api/documents` → `document:create`.
- `PATCH /api/documents/42` → `document:write`.
- `DELETE /api/documents/42` → `document:delete`.

You can use matchers with `HttpMethod`:

~~~java
import org.springframework.http.HttpMethod;

// Fragment inside authorizeHttpRequests:
.requestMatchers(HttpMethod.GET, "/api/documents/**")
    .hasAuthority("document:read")
.requestMatchers(HttpMethod.POST, "/api/documents")
    .hasAuthority("document:create")
.requestMatchers(HttpMethod.PATCH, "/api/documents/**")
    .hasAuthority("document:write")
.requestMatchers(HttpMethod.DELETE, "/api/documents/**")
    .hasAuthority("document:delete")
.requestMatchers("/api/documents/**")
    .denyAll()
~~~

The last rule blocks path/method combinations not granted access. If the application must support both the collection URL `/api/documents` and subpaths `/api/documents/**`, verify whether the matcher covers the intended paths in **the Spring Security/Spring MVC version in use**; do not guess about slashes, root paths, or the path-pattern engine.

**Wrong order:**

~~~java
// WRONG: GET already falls into the general rule first.
.requestMatchers("/api/documents/**").authenticated()
.requestMatchers(HttpMethod.GET, "/api/documents/**")
    .hasAuthority("document:read")
~~~

A logged-in user lacking `document:read` can still pass the HTTP layer if the path was already matched by the broad first rule.

**Important note on HTTP methods:** Spring Security's matcher does not decide the business action by itself; update endpoints still need owner/tenant/status checks. For `POST`, `PUT`, `PATCH`, and `DELETE`, **CSRF** can reject requests independently of authorization if the application uses cookies/sessions. Thus, tests for method-specific rules must supply valid CSRF tokens when required by policy; never conclude a 403 came from the rule based on a request missing CSRF.

## 6. Plain Java 17: simulating first-match and shadowed rules

The standalone Java program below only simulates **selecting rules in order**; it does not replace Spring Security. Each `Rule` has `matches` to identify the request and `allows` to check permission. The key point: once the first rule matches, the program **returns immediately**, even when the result is `false`.

Create file **`FirstMatchDemo.java`**:

~~~java
import java.util.List;
import java.util.function.Predicate;

public class FirstMatchDemo {

    record Request(String path, boolean authenticated, boolean admin) {}

    record Rule(
        String name,
        Predicate<Request> matches,
        Predicate<Request> allows
    ) {}

    static boolean authorize(List<Rule> rules, Request request) {
        for (Rule rule : rules) {
            if (rule.matches().test(request)) {
                return rule.allows().test(request);
            }
        }
        return false; // No rule matched -> default deny in this example.
    }

    public static void main(String[] args) {
        Rule broad = new Rule(
            "/api/**",
            r -> r.path().startsWith("/api/"),
            Request::authenticated
        );

        Rule admin = new Rule(
            "/api/admin/**",
            r -> r.path().startsWith("/api/admin/"),
            Request::admin
        );

        Request bob = new Request("/api/admin/users", true, false);
        Request carol = new Request("/api/admin/users", true, true);
        Request stranger = new Request("/other", true, false);

        System.out.println("bad Bob: "
            + authorize(List.of(broad, admin), bob));
        System.out.println("good Bob: "
            + authorize(List.of(admin, broad), bob));
        System.out.println("good Carol: "
            + authorize(List.of(admin, broad), carol));
        System.out.println("unmatched: "
            + authorize(List.of(admin, broad), stranger));
    }
}
~~~

Compile/run with **JDK 17+** in the directory containing the file:

~~~bash
javac FirstMatchDemo.java
java FirstMatchDemo
~~~

**Exact stdout:**

~~~text
bad Bob: true
good Bob: false
good Carol: true
unmatched: false
~~~

Explanation:

- **Bad Bob = true**: the `/api/**` rule comes first and only asks whether Bob is logged in.
- **Good Bob = false**: the admin rule comes first, matches, and denies; the broad rule is not tried afterward.
- **Good Carol = true**: Carol has admin privileges so she passes the first rule.
- **Unmatched = false**: the example intentionally chooses default deny when nothing matches.

This is a `Predicate` simulation without real Spring matchers, authentication filters, or context paths. The example is valuable for proving the **evaluation flow**, while real matchers must be verified with integration tests.

## 7. Runnable Spring Boot Java 17+ example

Create a **Spring Boot 3.x** project (Java 17+, Maven), selecting **Spring Web** and **Spring Security**. The example uses **a single `SecurityFilterChain`** to isolate the first-match rule behavior without chain-order dependencies.

Create file:

`src/main/java/com/example/order/RuleOrderApplication.java`

~~~java
package com.example.order;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class RuleOrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(RuleOrderApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .requestMatchers("/api/reports/secret")
                .hasAuthority("report:read")
            .requestMatchers("/api/reports/**").authenticated()
            .requestMatchers("/api/**").denyAll()
            .anyRequest().denyAll()
        ).httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo123"))
            .authorities("report:read")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("demo456"))
            .roles("USER")
            .build();

        UserDetails carol = User.withUsername("carol")
            .password(encoder.encode("demo789"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, bob, carol);
    }

    @RestController
    static class Api {

        @GetMapping("/public/ping")
        String ping() {
            return "pong";
        }

        @GetMapping("/api/admin/users")
        String adminUsers() {
            return "admin users";
        }

        @GetMapping("/api/reports/secret")
        String secret() {
            return "secret report";
        }

        @GetMapping("/api/reports/overview")
        String overview() {
            return "report overview";
        }

        @GetMapping("/api/unknown")
        String unknown() {
            return "should not be reached";
        }

        @GetMapping("/outside")
        String outside() {
            return "should not be reached";
        }
    }
}
~~~

### Interpreting authorities

- `alice` has the exact authority `report:read`, and does not automatically have `ROLE_ADMIN`.
- `bob` has `ROLE_USER` created by `roles("USER")`.
- `carol` has `ROLE_ADMIN` created by `roles("ADMIN")`. **`roles("ADMIN")` does not automatically create `report:read`**.
- The `hasRole("ADMIN")` rule requires `ROLE_ADMIN` by default convention.
- The `hasAuthority("report:read")` rule requires the exact string `report:read`.

There is no need to mix both permission types into one rule when the exercise only wants to show overlapping paths. In real projects, design permissions per resource rather than using one role to govern every action system-wide.

### Running the application

In the project directory:

~~~bash
# macOS / Linux
./mvnw spring-boot:run

# Windows PowerShell / Command Prompt
mvnw.cmd spring-boot:run
~~~

Once the server is ready on default port `8080`, try:

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/admin/users
curl -i -u bob:demo456 http://localhost:8080/api/admin/users
curl -i -u carol:demo789 http://localhost:8080/api/admin/users
curl -i -u bob:demo456 http://localhost:8080/api/reports/overview
curl -i -u bob:demo456 http://localhost:8080/api/reports/secret
curl -i -u alice:demo123 http://localhost:8080/api/reports/secret
curl -i -u carol:demo789 http://localhost:8080/api/reports/secret
curl -i -u bob:demo456 http://localhost:8080/api/unknown
curl -i -u bob:demo456 http://localhost:8080/outside
~~~

| Request | Expected HTTP status | First selected rule |
| --- | --- | --- |
| Public, anonymous | **200**, body `pong` | `/public/** → permitAll` |
| Admin, anonymous | **401** with HTTP Basic | `/api/admin/** → hasRole("ADMIN")`; unauthenticated |
| Admin, Bob | **403** | `/api/admin/**`; missing `ROLE_ADMIN` |
| Admin, Carol | **200**, body `admin users` | `/api/admin/**`; has `ROLE_ADMIN` |
| Overview, Bob | **200**, body `report overview` | `/api/reports/** → authenticated` |
| Secret, Bob | **403** | `/api/reports/secret`; missing `report:read` |
| Secret, Alice | **200**, body `secret report` | `/api/reports/secret`; has `report:read` |
| Secret, Carol | **403** | Secret rule, missing `report:read` even though Carol is ADMIN |
| Unknown API, Bob | **403** | `/api/** → denyAll` |
| Outside, Bob | **403** | `anyRequest() → denyAll` |

Expected outcomes are for **this example's HTTP Basic setup**, assuming no extra `SecurityFilterChain` or security filters are added. With form login, unauthenticated requests are usually redirected to the login page instead of returning 401. All endpoints above are GET and do not mutate data; if turned into mutating APIs, design CSRF and authorization accordingly.

**Demo safety:** the three passwords in the example code are purely for learning. In real environments, use a trusted identity store, proper secrets management, and send HTTP Basic only over **HTTPS**.

## 8. Two "first matching" layers: choosing the filter chain and choosing the rule inside

This distinction is essential when a system has **multiple `SecurityFilterChain`s**.

**Layer A — `FilterChainProxy` selects the chain:** Spring Security can hold multiple chains, each with an overall `RequestMatcher`. Chains are evaluated by priority (such as `@Order`). **The first chain matching the request is selected**; subsequent chains do not "supplement" filters or policies for that same request.

**Layer B — `AuthorizationFilter` inside the selected chain:** within the chain, `authorizeHttpRequests` `requestMatchers(...)` are evaluated **in declaration order**. The **first matching rule** is used.

~~~text
Request GET /api/admin/users
   |
   v
FilterChainProxy
   |
   +-- SecurityFilterChain @Order(1) securityMatcher("/api/**")
   |        MATCH -> selects API chain
   |             |
   |             +-- authorizeHttpRequests:
   |                   "/api/admin/**" -> hasRole("ADMIN")  [MATCH]
   |                   "/api/**"       -> authenticated()  [NOT EVALUATED]
   |
   +-- another fallback SecurityFilterChain               [NOT SELECTED]
~~~

**`http.securityMatcher(...)` vs `authorizeHttpRequests().requestMatchers(...)`:**

| API | Where applied | Effect |
| --- | --- | --- |
| `http.securityMatcher("/api/**")` | Selects **the entire SecurityFilterChain** | If the request does not match, this chain is not used |
| `authorizeHttpRequests().requestMatchers("/api/admin/**")` | Selects **a rule inside the selected chain** | Only evaluated after entering the chain |
| `anyRequest()` | Fallback **inside that chain** | Does not automatically protect requests outside the chain's `securityMatcher` |

If you configure only a single chain with `securityMatcher("/api/**")`, requests outside `/api/**` may **not be protected by Spring Security** unless another chain matches them. Hence official documentation recommends having a **fallback chain without `securityMatcher`** to cover the entire application.

### Multi-chain configuration example (fragment)

~~~java
// Fragment in a @Configuration class, using Java 17+ and Spring Security.
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());
    return http.build();
}

@Bean
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .anyRequest().denyAll()
    );
    return http.build();
}
~~~

Relevant imports include `org.springframework.context.annotation.Bean`, `org.springframework.core.annotation.Order`, `org.springframework.security.config.annotation.web.builders.HttpSecurity`, `org.springframework.security.config.Customizer`, and `org.springframework.security.web.SecurityFilterChain`. This is a configuration fragment **replacing the single-chain example**; do not place it alongside the Boot example in section 7 without handling duplicate beans.

In the API chain, `anyRequest()` refers only to **requests already routed into the API chain**; it does not cover `/outside`. The fallback chain handles requests that did not enter the API chain. If you reverse priority so the general fallback runs first, the API chain may never be used and specific rules get shadowed.

### Do not confuse with security filter ordering

Inside a chain, filters such as authentication filters and the authorization filter run in an order built by Spring Security. **Filter order** is a separate concern from the **matcher/rule order** studied here. Do not tweak filter order to fix a `requestMatchers("/api/**")` rule placed before `/api/admin/**`.

## 9. Real-world matchers: paths, methods, and servlet dispatches

### Path patterns are not arbitrary URL strings

`requestMatchers("/api/**")` accepts path patterns and delegates to the appropriate `RequestMatcher` mechanism. Behavior can depend on version, Spring MVC integration, and the selected matcher type. Therefore:

- Test `/api/admin`, `/api/admin/`, and `/api/admin/users` if they are meaningful in real routing.
- Test URLs with special characters, normalized paths, encoded paths, and multiple servlets.
- Do not assume query parameters are part of the path pattern. If `/api/reports?private=true` means something different from `/api/reports?private=false`, use a policy inspecting the request context rather than expecting a path matcher alone to distinguish them.
- When using a context path, reverse proxy, or URL rewrite, verify the actual path seen by Spring Security.
- In multi-servlet applications, check `MvcRequestMatcher`, `PathPatternRequestMatcher`, or servlet-path-aware matchers for your version.

**There is no default priority for "longer matchers."** A shorter pattern placed earlier can shadow a longer pattern.

### Method matchers and general rules

~~~java
// Fragment:
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("orders:read")
.requestMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("orders:write")
.requestMatchers("/api/orders/**").denyAll()
~~~

If `requestMatchers("/api/orders/**").authenticated()` is placed at the top, every request in that group can pass through the "login only" rule and skip the GET/POST-specific permissions.

### FORWARD, ERROR, and ASYNC dispatches

Servlets can have request dispatches besides normal `REQUEST`. Spring Security documentation illustrates declaring `dispatcherTypeMatchers(FORWARD, ERROR).permitAll()` **when the application genuinely needs it** for rendering/error pages. However, overly broad declarations can create unintended access exceptions. Define the target, order, and test dispatch types in your own application; never blindly copy `permitAll` onto all dispatches.

### Multiple SecurityFilterChains and login state

If a route enters a different chain, the authentication mechanism can differ: HTTP Basic, form login, bearer token, session, etc. Thus, when a URL gives an unexpected 401/403, check **which chain matched first**, rather than only reading rules in the chain you assumed was active. For granted authorities, verify `Authentication#getAuthorities()` from a trusted source; never rely on roles sent by the frontend.

## 10. Testing to catch ordering bugs before deployment

A useful test suite should include both **properly allowed** and **properly denied** cases. Minimum tests for the example:

| Test | Caller | Endpoint | Expected |
| --- | --- | --- | --- |
| Public route | Anonymous | `GET /public/ping` | 200 |
| Admin blocked | Bob `ROLE_USER` | `GET /api/admin/users` | 403 |
| Admin allowed | Carol `ROLE_ADMIN` | `GET /api/admin/users` | 200 |
| Sensitive report blocked | Bob `ROLE_USER` | `GET /api/reports/secret` | 403 |
| Sensitive report allowed | Alice `report:read` | `GET /api/reports/secret` | 200 |
| Broad rule takes effect | Bob | `GET /api/reports/overview` | 200 |
| Undeclared API blocked | Bob | `GET /api/unknown` | 403 |
| Out-of-scope URL blocked | Bob | `GET /outside` | 403 |
| Admin lacks report permission automatically | Carol | `GET /api/reports/secret` | 403 |

To run with `MockMvc`, add the **`spring-security-test`** dependency to the test classpath, use `@SpringBootTest` + `@AutoConfigureMockMvc`, and place tests in the project containing the Boot class from section 7. This is a **test class fragment** (needs corresponding imports and package):

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class RuleOrderSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(roles = "USER")
    void nonAdminCannotCallAdmin() throws Exception {
        mvc.perform(get("/api/admin/users"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanCallAdmin() throws Exception {
        mvc.perform(get("/api/admin/users"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(roles = "USER")
    void nonReaderCannotCallSecret() throws Exception {
        mvc.perform(get("/api/reports/secret"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void readerCanCallSecret() throws Exception {
        mvc.perform(get("/api/reports/secret"))
            .andExpect(status().isOk());
    }
}
~~~

Notable imports: `org.springframework.boot.test.context.SpringBootTest`, `org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc`, `org.springframework.beans.factory.annotation.Autowired`, `org.springframework.test.web.servlet.MockMvc`, `org.springframework.security.test.context.support.WithMockUser`, `org.junit.jupiter.api.Test`, `org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get`, and `org.springframework.test.web.servlet.result.MockMvcResultMatchers.status` (the last two are usually `static` imports).

**Why are negative tests critical?** If someone accidentally moves `/api/**.authenticated()` above the admin or secret rule, the 200 tests for admin/Alice still **pass**, while Bob's 403 test **fails**. This is why testing "denied properly" is just as important as testing "allowed properly".

### Additional tests worth writing

- Requests **without authentication** to admin/report endpoints.
- Requests at **the intersection of two patterns**, such as the admin prefix and API prefix.
- Every **HTTP method** on the same resource path.
- A URL without a controller or newly added: must not be opened by an overly broad default rule.
- Multiple chains: URLs matching only the API chain, only the fallback, or both.
- Resource instances from another tenant or owner: test at the method/domain layer.
- `FORWARD/ERROR` dispatches if the real application uses them and added `dispatcherTypeMatchers`.

Do not check status 200 alone; assert the response content and appropriate side effects to prove the right endpoint ran, especially when the system uses complex routers/gateways.

## 11. How to debug when a rule seems "not to work"

A practical diagnostic workflow:

1. **Identify the actual request:** HTTP method, path, context path, dispatcher type, URL rewritten by proxy.
2. **Identify the first matching chain:** inspect `@Order` and `http.securityMatcher` across all `SecurityFilterChain`s.
3. **Within that chain, list rules in exact order:** number from 1, noting the matcher and attached policy.
4. **Find the first matcher matching the request:** do not skip broad lines like `/api/**` or `/**`.
5. **Evaluate that first line's policy:** is the user authenticated, what actual roles/authorities exist, what conditions does a custom manager check.
6. **Pinpoint what returned the error:** HTTP `AuthorizationFilter`, method security, CSRF filter, authentication entry point, or business logic. A 403 is not always caused by a missing role.
7. **Add a negative test** to lock down the policy before changing order/rules.

You can enable Spring Security logging in development to observe filter chain selection and authorization, e.g., configuring `DEBUG` or `TRACE` logging for `org.springframework.security`. However, logs may contain security-sensitive data: enable selectively, never log credentials/tokens, and turn off overly verbose levels when not needed.

**Do not "fix" a 403 by moving `permitAll()` to the top or inserting `.anyRequest().permitAll()`**. Such changes can nullify many critical rules.

## 12. Common pitfalls table

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Putting `/api/**.authenticated()` before `/api/admin/**.hasRole(...)` | Ordinary users pass the HTTP check for admin | Move admin first |
| Putting `/reports/**` before `/reports/secret` | Sensitive report rule is shadowed | Move secret first |
| Writing two matchers on the same path expecting OR | Second rule is never evaluated | Use one rule with `hasAnyAuthority` or a composite manager |
| Writing two matchers on the same path expecting AND | Does not combine conditions as intended | Use one rule checking all conditions |
| Assuming deny will "try the next rule" | Leads to wrong policy assumptions | Remember **first matching**, not first granting |
| Putting `/**.permitAll()` at the top | Shadows every rule after it | Only expose endpoints intentionally |
| Setting `anyRequest().authenticated()` for all unknown URLs | New APIs may open to any logged-in account | Choose `denyAll()` fallback where appropriate |
| Configuring only a chain with `securityMatcher("/api/**")` | Other URLs may go unprotected by Spring Security | Add an unscoped fallback chain |
| Assuming the API chain's `anyRequest` covers `/outside` | Misunderstands chain scope | Distinguish the two matcher layers |
| Testing only that admin requests return 200 | Fails to detect regular users slipping through | Test both 200 and 403 |
| Ignoring HTTP methods and CSRF | Misdiagnoses 403 causes or exposes write methods | Test method-specific rules and CSRF |
| Protecting only HTTP without checking owner/tenant | Users with route permission read wrong records | Add resource-instance checks |

## 13. Self-check questions

**Question 1.** With `requestMatchers("/api/**").authenticated()` before `requestMatchers("/api/admin/**").hasRole("ADMIN")`, Bob (logged in, not admin) calls `/api/admin/users`. Which rule is used?  
**Answer:** `/api/**.authenticated()`; this is an ordering vulnerability because the admin rule is shadowed.

**Question 2.** If the first matching rule returns DENY, does Spring Security continue searching for a second rule to allow it?  
**Answer:** **No** in the `authorizeHttpRequests` first-matching-rule mechanism.

**Question 3.** Do two lines with the same matcher `/finance/**`, one `hasAuthority("finance:read")` and one `hasRole("MANAGER")`, create OR logic?  
**Answer:** No. Use `hasAnyAuthority("finance:read", "ROLE_MANAGER")` or a combined manager.

**Question 4.** `/api/reports/secret` matches two matchers: specific secret and general `/api/reports/**`. Which line goes first?  
**Answer:** The specific secret line first, because it requires a more sensitive permission.

**Question 5.** Does `anyRequest().denyAll()` catch URLs outside that chain's `securityMatcher("/api/**")`?  
**Answer:** **No**. It only applies after the chain has been selected.

**Question 6.** Why must we test a non-admin user calling an admin endpoint?  
**Answer:** To detect when a broad rule placed earlier unintentionally lets requests through, while admin 200 tests still pass.

**Question 7.** Is it safe to put `/api/docs/**.authenticated()` before an `HttpMethod.DELETE` matcher on the same path?  
**Answer:** No, if DELETE must require `document:delete`. The broad rule shadows the specialized rule.

**Question 8.** When there are multiple `SecurityFilterChain`s, where does precedence live?  
**Answer:** `FilterChainProxy` selects the first matching chain by priority; inside the selected chain, `AuthorizationFilter` selects the first matching rule by declaration order.

**Remember:** **Order is policy**. When matchers can overlap, **specific and sensitive** rules must be declared **before** broad matchers; once the first matcher matches, ALLOW/DENY is decided by that rule. Always maintain an appropriate **default deny** fallback and test both authorized and unauthorized callers.

## Official documentation

- Spring Security — Authorize HTTP Requests (matcher/rule pair ordering): https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Java Configuration (multiple SecurityFilterChains, securityMatcher, and requestMatchers): https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — Servlet Architecture (FilterChainProxy and security filters): https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security 6.5 — HttpSecurity API (matcher ordering note): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/builders/HttpSecurity.html
- Spring Security — Method Security (service-layer authorization after HTTP): https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
