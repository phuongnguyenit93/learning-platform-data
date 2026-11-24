# Matching Paths Combined with HTTP Methods in Spring Security

A single URL can serve multiple operations: `GET /api/orders` reads a list, `POST /api/orders` creates an order, `PUT /api/orders/42` updates, and `DELETE /api/orders/42` deletes. If you only protect it with the pattern `/api/orders/**` and grant a broad permission, the application might let someone who should only have **read permission** perform write operations as well. Spring Security lets you combine a **path** with an **HTTP method** so each action is controlled separately.

This lesson belongs to the **Endpoint protection** group of **Spring Security - fundamentals**. The focus is how `RequestMatcher` evaluates **both path and method simultaneously**, how the **first-match rule** is applied, practical configuration in Java 17+ on Spring MVC/Servlet, testing permissions, and common points of confusion with CSRF, CORS, or Controller routing.

## 1. Distinction Between Path and HTTP Action

An HTTP method describes the intended operation on a resource:

| Method | Common usage | Example | Permission the application may require |
| --- | --- | --- | --- |
| `GET` | Read resource | `GET /api/orders` | `ORDER_READ` |
| `POST` | Create / trigger an action | `POST /api/orders` | `ORDER_CREATE` |
| `PUT` | Overwrite / update by API convention | `PUT /api/orders/42` | `ORDER_UPDATE` |
| `PATCH` | Partial update | `PATCH /api/orders/42` | Update permission, if the API supports it |
| `DELETE` | Delete resource | `DELETE /api/orders/42` | `ORDER_DELETE` |
| `HEAD` | Retrieve response metadata without body | `HEAD /api/orders` | Needs explicit policy if supported |
| `OPTIONS` | Query methods/capabilities; may be CORS preflight | `OPTIONS /api/orders` | Must consider preflight or endpoint purpose |

These are **HTTP conventions**, not business rules decided by Spring Security itself. An application might have `POST /api/orders/42/cancel` to cancel an order even if it does not use DELETE. Therefore, authorize according to the **actual endpoint contract**, rather than assuming every GET has no sensitive data or every POST requires the same permission level.

Distinguish three layers of responsibility:

1. **Routing** in Spring MVC/WebFlux: which Controller/handler receives the request? E.g., `@GetMapping("/api/orders")`.
2. **Authentication**: who does the request represent; is there a valid `Authentication`?
3. **Authorization**: is this `(HTTP method, path)` pair allowed to proceed with the current identity/authorities?

Spring Security normally evaluates permissions before a request reaches the Controller. Thus, a request **without a matching handler** can still be rejected by Spring Security before Spring MVC returns 404/405.

## 2. A Combined Method + Path Matcher Is a Two-Condition Check

In Servlet Spring Security, `authorizeHttpRequests` declares pairs of **match condition → authorization requirement**. For example:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**").hasAuthority("ORDER_READ")
.requestMatchers(HttpMethod.POST, "/api/orders").hasAuthority("ORDER_CREATE")
~~~

In each line:

- `HttpMethod.GET` or `HttpMethod.POST` restricts the exact method sent in the request.
- The pattern string `"/api/orders/**"` or `"/api/orders"` restricts the path.
- Only when **both method and path match** is the rule on that line selected for authorization evaluation.
- `hasAuthority("ORDER_READ")` checks for the exact authority `ORDER_READ` in `Authentication.getAuthorities()`; it does not automatically prepend `ROLE_` like `hasRole(...)`.

Comparison:

| Request | Matches GET /api/orders/** rule? | Matches POST /api/orders rule? |
| --- | :---: | :---: |
| `GET /api/orders/42` | Yes | No |
| `POST /api/orders` | No | Yes |
| `POST /api/orders/42` | No | No |
| `DELETE /api/orders/42` | No | No |
| `GET /api/users/42` | No | No |

For `GET /api/orders`, whether the pattern `/api/orders/**` includes the root path itself depends on the matcher type and version in use; **do not silently rely on a trailing `/**`** when the root path matters. In the complete example later, this lesson explicitly declares both `/api/orders` and `/api/orders/{id}`.

The following statement differs in scope:

~~~java
.requestMatchers(HttpMethod.GET).hasAuthority("READ_ANY_GET")
~~~

It selects **every GET request within the scope of the SecurityFilterChain**, including `GET /admin` if this chain handles that path. This is a method rule **without path restriction**; it cannot replace a two-condition matcher when per-API-group permissions are needed.

Conversely:

~~~java
.requestMatchers("/api/orders/**").authenticated()
~~~

this rule constrains only the **path** and applies to all matching HTTP methods. It does not distinguish GET from DELETE.

## 3. Spring Security Uses the First Matching Rule, Not Additive Rules Across Lines

Inside `authorizeHttpRequests(...)`, `AuthorizationFilter` evaluates `RequestMatcher → AuthorizationManager` pairs **in declaration order**. The **first matching rule** decides whether access is granted or denied.

Consider an error-prone configuration:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers(HttpMethod.DELETE, "/api/orders/{id}")
        .hasAuthority("ORDER_DELETE")
    .anyRequest().denyAll()
)
~~~

`DELETE /api/orders/42` immediately matches `/api/**`. If the user is authenticated, this rule lets it pass and **does not continue** down to the `ORDER_DELETE` line. The seemingly strict rule below has been neutralized by the overly broad rule above.

Reverse the order:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.DELETE, "/api/orders/{id}")
        .hasAuthority("ORDER_DELETE")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
)
~~~

The configuration above protects DELETE on that specific URL. However, other DELETE requests under `/api/**` still only require login; therefore, for APIs needing tight control, you should **list supported methods/paths and deny the rest**. `anyRequest().denyAll()` is a safe default in teaching examples.

An accurate way to read the rules:

~~~text
Scan top to bottom:
  1. Does the current matcher match both method and path?
     - No: evaluate the next matcher.
     - Yes: evaluate this line's permission condition.
  2. Permission condition satisfied? → allow through.
     Not satisfied? → deny.
  3. Do not keep trying later lines just because the user lacked permission on the matched line.
~~~

Hence, **not matching a matcher** differs from **matching a matcher but lacking permission**. The first case can fall through to a later rule; the second stops at the selected rule.

## 4. Sample Decision Table for an Orders API

Suppose the application has four main authorities: `ORDER_READ`, `ORDER_CREATE`, `ORDER_UPDATE`, and `ORDER_DELETE`.

| Request | Expected matcher | Required authority | Result when holding only `ORDER_READ` |
| --- | --- | --- | --- |
| `GET /api/orders` | GET + collection path | `ORDER_READ` | Allowed |
| `GET /api/orders/42` | GET + single-order path | `ORDER_READ` | Allowed |
| `POST /api/orders` | POST + collection path | `ORDER_CREATE` | Denied |
| `PUT /api/orders/42` | PUT + single-order path | `ORDER_UPDATE` | Denied |
| `DELETE /api/orders/42` | DELETE + single-order path | `ORDER_DELETE` | Denied |
| `PATCH /api/orders/42` | PATCH undeclared | `denyAll` | Denied |
| `GET /api/admin` | Path undeclared | `denyAll` | Denied |

"Allowed" here only means **passing HTTP authorization**. It does not guarantee the Controller exists, the resource is real, the data belongs to the user, or processing succeeds. For example, a user with `ORDER_READ` can still be denied when attempting to read another customer's order if the application adds per-resource permission checks.

## 5. Java 17+ Configuration Ready for a Spring MVC Application

The following example targets **Spring Boot 3.3.x / Spring Security 6.3.x**, Java 17+, a Servlet application using `spring-boot-starter-web` and `spring-boot-starter-security`. The goal is a small example where every method/path can be tested, rather than showing a DSL snippet without a Controller.

### 5.1. Gradle Dependencies

In a Spring Boot project that already has the Spring Boot plugin and dependency version management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This Gradle snippet is only the dependencies and test configuration to merge into an existing Spring Boot project's `build.gradle`. Do not create manual dependency/version management when the project already uses Spring Boot's management mechanism.

### 5.2. `EndpointPolicyApplication.java`

In `src/main/java/example/methodpath/EndpointPolicyApplication.java`:

~~~java
package example.methodpath;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EndpointPolicyApplication {
    public static void main(String[] args) {
        SpringApplication.run(EndpointPolicyApplication.class, args);
    }
}
~~~

This is the application entry point so Spring Boot automatically discovers `SecurityConfig` and `OrdersController` in the same package.

### 5.3. `SecurityConfig.java`

In `src/main/java/example/methodpath/SecurityConfig.java`:

~~~java
package example.methodpath;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                        "/api/orders", "/api/orders/{id}")
                    .hasAuthority("ORDER_READ")

                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("ORDER_CREATE")

                .requestMatchers(HttpMethod.PUT, "/api/orders/{id}")
                    .hasAuthority("ORDER_UPDATE")

                .requestMatchers(HttpMethod.DELETE, "/api/orders/{id}")
                    .hasAuthority("ORDER_DELETE")

                // All other methods on the order resource: deny.
                .requestMatchers("/api/orders", "/api/orders/**")
                    .denyAll()

                // All undeclared paths: deny.
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

The configuration keeps **Spring Security's default CSRF**, which matters when testing POST/PUT/DELETE. It uses HTTP Basic as the mechanism to produce a deterministic 401 response for unauthenticated requests; real projects may use form login, OAuth2 Resource Server, or another mechanism.

Note:

- `HttpMethod.GET` applies **to both paths** in the same call; hence both the list and detail endpoints require `ORDER_READ`.
- Each write method uses its corresponding authority; sharing the same path does not imply sharing the same default authority.
- `"/api/orders/{id}"` is a single-segment path variable pattern. Actual pattern engine/type names and detailed parsing behavior depend on Spring MVC + matcher version. This lesson uses simple patterns without relying on advanced differences of `**`.
- After the specific rules comes a **path-only `denyAll`** rule for unapproved methods on the orders API, followed by `anyRequest().denyAll()`.
- In a real application, policy may also need per-order permissions, record ownership, and order state alongside the coarse `ORDER_UPDATE` authority.

### 5.4. `OrdersController.java`

In `src/main/java/example/methodpath/OrdersController.java`:

~~~java
package example.methodpath;

import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrdersController {

    @GetMapping
    public List<String> list() {
        return List.of("ORD-101", "ORD-102");
    }

    @GetMapping("/{id}")
    public String find(@PathVariable String id) {
        return "order-" + id;
    }

    @PostMapping
    public ResponseEntity<String> create() {
        return ResponseEntity.status(HttpStatus.CREATED).body("created");
    }

    @PutMapping("/{id}")
    public ResponseEntity<Void> update(@PathVariable String id) {
        return ResponseEntity.noContent().build();
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable String id) {
        return ResponseEntity.noContent().build();
    }
}
~~~

The Controller returns static data for policy testing; it does not store, edit, or delete real data. Place all three files in the same package `example.methodpath`. For a project with its own package, change the package **consistently across all three files**.

The policy in `SecurityConfig` and the `@GetMapping/@PostMapping/...` annotations answer two independent questions:

- Spring Security determines whether the user **is allowed to pass through this URL + method**.
- Spring MVC determines **which Java method handles the request** once it has passed the filters.

If the two sides declare different things—for example, Security allows GET while the Controller only supports POST—a routing error can still occur after authorization passes. Conversely, a Controller having `@DeleteMapping` does not mean Spring Security automatically knows to require `ORDER_DELETE`.

## 6. Integration Testing Method + Path with MockMvc

A useful test suite must cover both **allowed paths** and **blocked paths**, especially **same path, different method**. Use `spring-security-test` to supply identities with specific authorities and to verify CSRF as well.

File `src/test/java/example/methodpath/EndpointMethodAuthorizationTest.java`:

~~~java
package example.methodpath;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class EndpointMethodAuthorizationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void anonymousCannotReadProtectedOrders() throws Exception {
        mvc.perform(get("/api/orders"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void readerCanGetListAndDetail() throws Exception {
        var reader = user("reader")
                .authorities(new SimpleGrantedAuthority("ORDER_READ"));

        mvc.perform(get("/api/orders").with(reader))
                .andExpect(status().isOk())
                .andExpect(content().json("[\"ORD-101\", \"ORD-102\"]"));

        mvc.perform(get("/api/orders/42")
                .with(user("reader")
                    .authorities(new SimpleGrantedAuthority("ORDER_READ"))))
                .andExpect(status().isOk())
                .andExpect(content().string("order-42"));
    }

    @Test
    void readerCannotPostToSamePathEvenWithCsrf() throws Exception {
        mvc.perform(post("/api/orders")
                .with(user("reader")
                    .authorities(new SimpleGrantedAuthority("ORDER_READ")))
                .with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    void creatorCanPostWithCsrf() throws Exception {
        mvc.perform(post("/api/orders")
                .with(user("creator")
                    .authorities(new SimpleGrantedAuthority("ORDER_CREATE")))
                .with(csrf()))
                .andExpect(status().isCreated())
                .andExpect(content().string("created"));
    }

    @Test
    void creatorCannotPostWithoutCsrf() throws Exception {
        mvc.perform(post("/api/orders")
                .with(user("creator")
                    .authorities(new SimpleGrantedAuthority("ORDER_CREATE"))))
                .andExpect(status().isForbidden());
    }

    @Test
    void writerCanPutButCannotDelete() throws Exception {
        mvc.perform(put("/api/orders/42")
                .with(user("writer")
                    .authorities(new SimpleGrantedAuthority("ORDER_UPDATE")))
                .with(csrf()))
                .andExpect(status().isNoContent());

        mvc.perform(delete("/api/orders/42")
                .with(user("writer")
                    .authorities(new SimpleGrantedAuthority("ORDER_UPDATE")))
                .with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    void deleterCanDeleteWithCsrf() throws Exception {
        mvc.perform(delete("/api/orders/42")
                .with(user("deleter")
                    .authorities(new SimpleGrantedAuthority("ORDER_DELETE")))
                .with(csrf()))
                .andExpect(status().isNoContent());
    }

    @Test
    void unlistedMethodFallsToDenyAll() throws Exception {
        mvc.perform(patch("/api/orders/42")
                .with(user("writer")
                    .authorities(new SimpleGrantedAuthority("ORDER_UPDATE")))
                .with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    void unrelatedPathDoesNotInheritOrderReadAuthority() throws Exception {
        mvc.perform(get("/api/admin")
                .with(user("reader")
                    .authorities(new SimpleGrantedAuthority("ORDER_READ"))))
                .andExpect(status().isForbidden());
    }
}
~~~

Run from the Spring Boot project directory that has a Gradle wrapper:

~~~bash
./gradlew test --tests '*EndpointMethodAuthorizationTest'
~~~

On Windows PowerShell/CMD:

~~~powershell
.\gradlew.bat test --tests "*EndpointMethodAuthorizationTest"
~~~

**Expected result:** 9 tests pass on the versions/dependencies listed above. This is an expectation derived from the code and the illustrated Spring Security contracts, **not a result executed in the reader's environment**. The tests use `MockMvc` integrated with the Spring Security filter chain configured by `@AutoConfigureMockMvc`. They do not require real user accounts because `user(...)` injects the test identity into the request.

The `readerCannotPostToSamePathEvenWithCsrf` test is the most direct verification of the topic: the path `/api/orders` does not change, yet switching from `GET` to `POST` changes the matcher and the required authority.

## 7. CSRF Can Block a Request Even When the Permission Matcher Is Right

Spring Security normally enables **CSRF** protection in Servlet applications. State-changing methods such as `POST`, `PUT`, `PATCH`, and `DELETE` require a valid CSRF token under default rules if the request falls within the scope of CSRF checking.

For the same user holding `ORDER_CREATE`:

~~~text
POST /api/orders  + ORDER_CREATE + valid CSRF   → can pass filters and enter Controller
POST /api/orders  + ORDER_CREATE + missing CSRF → can receive 403 before URL authorization
POST /api/orders  + ORDER_READ   + valid CSRF   → lacks ORDER_CREATE → denied
~~~

Therefore, when seeing `403` on a POST, **do not jump to concluding the method/path matcher is wrong**; check both permissions and CSRF requirements. In `MockMvc`, use `.with(csrf())` on write requests so permission tests are not blocked early due to missing CSRF.

CSRF and authorization serve two different purposes:

- **Method/path authorization**: who is allowed to perform this operation?
- **CSRF**: does the request carry suitable proof against a browser being abused to send requests with ambient credentials?

Do not disable `csrf` across the entire application just to make a POST test pass. For APIs that do not use browser cookies/sessions and have a different authentication model, a specific decision on CSRF scope may apply, but it must be based on the actual architecture rather than on seeing a 403 status.

## 8. OPTIONS and CORS Preflight Are Not a Real POST

A browser calling an API from another origin may send a **preflight** before sending the actual request:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

At the HTTP layer, this request has method **`OPTIONS`**. The `Access-Control-Request-Method: POST` header only describes the method the browser intends to send next; Spring Security **does not treat this preflight as a POST request** just because of that header. Therefore:

~~~java
.requestMatchers(HttpMethod.POST, "/api/orders").hasAuthority("ORDER_CREATE")
~~~

does not match the `OPTIONS` request.

If the API genuinely serves a cross-origin frontend, the right approach is to **configure CORS for valid origins, methods, and headers**, while letting preflight handling run before steps requiring identity. Spring Security provides CORS integration for that case.

Example addition to `SecurityConfig`, only if the application needs CORS:

~~~java
// Additional imports:
// import java.util.List;
// import org.springframework.web.cors.CorsConfiguration;
// import org.springframework.web.cors.CorsConfigurationSource;
// import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of("https://app.example.com"));
    config.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE"));
    config.setAllowedHeaders(List.of("Authorization", "Content-Type", "X-CSRF-TOKEN"));
    config.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    return source;
}
~~~

And add to the `HttpSecurity` configuration chain:

~~~java
.cors(Customizer.withDefaults())
~~~

This is an **integration snippet**, not a standalone Java program; place the bean and imports in the Spring configuration class from section 5. Allow only genuinely trusted origins, adjust headers and credentials according to your authentication mechanism, and test CORS in a browser. Cross-origin cookies are also subject to `SameSite`/`Secure` rules, and CORS does not replace CSRF.

**Do not use `requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()` as a generic CORS fix.** It does not validate allowed origins/methods/headers and does not replace preflight handling; furthermore, it lets every OPTIONS request in the matcher's scope pass through, which may not fit the API's requirements. For same-origin requests or real OPTIONS endpoints, define an explicit policy.

## 9. HEAD, PATCH, and Undeclared Methods

The authorization filter inspects the **actual HTTP method carried by the request**. If the configuration only specifies `GET`, Spring MVC may handle `HEAD` via `@GetMapping`, but a security matcher for **`HttpMethod.GET` does not automatically become a matcher for `HttpMethod.HEAD`**. If you want to allow HEAD, declare it explicitly:

~~~java
.requestMatchers(HttpMethod.HEAD, "/api/orders", "/api/orders/{id}")
    .hasAuthority("ORDER_READ")
~~~

Place this rule before the `denyAll` rules applying to orders. Conversely, if you do not want to support HEAD, keep `denyAll` and test it explicitly.

The same applies to `PATCH`: without a PATCH rule in the section 5 configuration, a `PATCH /api/orders/42` request is denied. When adding `@PatchMapping("/{id}")`, add the corresponding authorization rule, such as requiring `ORDER_UPDATE`, and verify CSRF.

For `TRACE` or other methods, whether they are allowed also depends on the web server/container. A `denyAll` policy is a defense at the Spring Security layer, not a guarantee that the request ever reaches the application. **Do not interpret "undeclared method is denied" as "always returns 403"** if the container rejects it earlier.

## 10. Path Patterns, Query Strings, and Servlet Context

`requestMatchers(HttpMethod.GET, "/api/orders/{id}")` uses a path pattern, not a full URL string. Common considerations:

- **Query string:** `GET /api/orders?status=OPEN` still has path `/api/orders`. Standard path matchers do not inspect `status` or `userId` values. If permissions depend on query parameters, separate authorization logic is needed.
- **Path variable:** `/api/orders/{id}` describes a variable path segment. Matching the URL **does not mean** the user may read every `id`; object-level permissions require additional checks.
- **Context path:** if the application is deployed under `/shop`, when writing Spring Security Servlet matchers, patterns are normally evaluated relative to the context path; do not manually prepend `/shop` to every matcher without checking actual configuration.
- **Servlet path:** if multiple Servlets exist or `DispatcherServlet` is mounted under a sub-path, you may need `MvcRequestMatcher.Builder.servletPath(...)` (on an applicable Spring Security 6.x line) or an appropriate matcher to clarify scope. Do not infer directly from the URL visible in the browser.
- **Trailing slashes and encoding:** `/api/orders/42` vs. `/api/orders/42/`, semicolons `;`, encoded paths, and letter case may be handled differently across matcher types and web server configurations. Test realistic variations of sensitive endpoints.
- **Matcher nature:** Spring Security may choose a Spring MVC-compatible matcher or another matcher depending on version and present beans. Do not take `AntPathRequestMatcher` rules and assume every version/matcher type handles edge cases identically.

When conditions beyond path/method are needed, you can supply a custom `RequestMatcher`. Make clear, however, that it only decides **whether the request falls within the rule's scope**; identity and permission conditions still belong to `AuthorizationManager`.

Illustrative example of adding a header check when genuinely required:

~~~java
RequestMatcher selectedRequests = request ->
        "GET".equals(request.getMethod())
        && "/api/reports/export".equals(request.getServletPath())
        && "true".equals(request.getHeader("X-Export-Requested"));

// Integrate into the DSL:
// .requestMatchers(selectedRequests).hasAuthority("REPORT_EXPORT")
~~~

This is a **custom snippet**, not the default approach for protecting orders. Relying on a client-controlled header must never be treated as proof of access rights; the `REPORT_EXPORT` authority must still be checked. The example only shows that a matcher can combine multiple request conditions.

## 11. Distinguishing `requestMatchers` from `securityMatcher`

Two similar-looking names operate at two different layers:

- `http.securityMatcher("/api/**")`: determines **whether a `SecurityFilterChain` applies to this request**.
- `authorizeHttpRequests(auth -> auth.requestMatchers(...))`: selects **an authorization rule inside the applied chain**.

Example:

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/orders")
            .hasAuthority("ORDER_READ")
        .anyRequest().denyAll()
    );
~~~

This configuration applies only to requests accepted by the `/api/**` chain. `anyRequest().denyAll()` inside this chain **does not automatically protect paths outside `/api/**`**. When using multiple `SecurityFilterChain` beans, Spring Security picks the matching chain in order; you must also protect requests outside the specialized chain so part of the application does not pass through without the intended security chain.

For a small application, the example in section 5 uses **one general chain** with `anyRequest().denyAll()`, making scope easy to verify. When an application splits multiple chains (API, Actuator, web UI), check chain order, chain-level matchers, and inner rules together.

## 12. 401, 403, 404, 405 Results Come from Different Layers

When debugging, trace the sequence:

~~~text
HTTP method + path
      ↓
Select SecurityFilterChain
      ↓
Authentication filters and protections (CSRF, CORS, ...)
      ↓
AuthorizationFilter → first matcher matching method + path
      ↓
Evaluate permission → allow / deny
      ↓
If allowed: DispatcherServlet selects Controller
      ↓
Controller executes or returns results like 404/405/2xx/5xx
~~~

In the HTTP Basic example:

| Symptom | Possible cause | What to inspect |
| --- | --- | --- |
| `401 Unauthorized` | No valid identity yet; authentication required | Authorization header, `AuthenticationEntryPoint` |
| `403 Forbidden` | Missing authority, hit `denyAll`, or CSRF failed | Selected matcher, current authorities, CSRF token |
| `404 Not Found` | Passed security, but no valid resource/handler | Path, Controller, specific mapping |
| `405 Method Not Allowed` | Passed security, but handler does not support the HTTP method | `@GetMapping` / `@PostMapping`, routing |
| Redirect to login | Application uses form login instead of HTTP Basic | `AuthenticationEntryPoint` mechanism |
| CORS response blocked | Invalid preflight origin/method/header or wrong CORS config | OPTIONS request, CORS configuration |

This table shows **common scenarios**, not a fixed one-to-one mapping between a security signal and an HTTP code. A `denyAll` at the Security layer can reject a `PATCH` request even when the Controller has no `@PatchMapping` at all, so the client may receive 403 instead of 405.

A helpful debugging signal is logging **which matcher matched first** and which `GrantedAuthority` values the principal holds. Increase logging selectively in development; avoid writing tokens, cookies, or sensitive credentials to logs.

## 13. Equivalent WebFlux Configuration with a Different API

If the application uses Spring WebFlux, do not copy `HttpSecurity` and `authorizeHttpRequests` from Servlet. WebFlux uses `ServerHttpSecurity.authorizeExchange(...)`, with method/path matchers in `pathMatchers`. **Illustrative configuration snippet**:

~~~java
return http
    .authorizeExchange(exchanges -> exchanges
        .pathMatchers(HttpMethod.GET, "/api/orders", "/api/orders/{id}")
            .hasAuthority("ORDER_READ")
        .pathMatchers(HttpMethod.POST, "/api/orders")
            .hasAuthority("ORDER_CREATE")
        .pathMatchers(HttpMethod.DELETE, "/api/orders/{id}")
            .hasAuthority("ORDER_DELETE")
        .anyExchange().denyAll()
    )
    .httpBasic(Customizer.withDefaults())
    .build();
~~~

The snippet must sit inside a `@Bean SecurityWebFilterChain`, with `ServerHttpSecurity http` and the corresponding WebFlux imports; it is **not a standalone Java program**. For your specific reactive version, check `pathMatchers(HttpMethod, ...)` usage and WebFlux CSRF/CORS protection. The core idea remains **matching both method and path first, then evaluating permissions**.

WebFlux uses Reactor's security context rather than assuming every request carries user data in a `ThreadLocal`-style `SecurityContextHolder`. When per-resource permissions are needed, use reactive-compatible authorization mechanisms and Publishers instead of blocking the thread.

## 14. Design Mistakes to Avoid

1. **Using path-only rules for all actions:** `requestMatchers("/api/orders/**").authenticated()` does not distinguish read/create/update/delete.
2. **Putting broad matchers first:** an `/api/**` rule matching early prevents later method-specific rules from ever applying.
3. **Defining no fallback:** new methods such as PATCH or HEAD can fall into an overly broad rule without an explicit `denyAll`.
4. **Authorizing globally by HTTP method alone:** `requestMatchers(HttpMethod.GET)` can accidentally grant read access to every resource, including sensitive URLs.
5. **Assuming Controller mappings decide permissions:** `@DeleteMapping` does not replace `hasAuthority("ORDER_DELETE")`; routing and authorization are checked independently.
6. **Blaming authorization for every 403:** write requests missing CSRF can be blocked before role/authority checks.
7. **Treating CORS preflight as a real POST:** `OPTIONS` is not `POST` even when it carries `Access-Control-Request-Method: POST`.
8. **Forgetting HEAD and path variants:** Spring MVC's handling of HEAD does not automatically open Spring Security's GET rule to HEAD.
9. **Confusing `requestMatchers` with `securityMatcher`:** a fallback inside a specialized chain does not cover requests outside that chain.
10. **Skipping object-level permissions:** `ORDER_READ` allows calling the read API, but does not prove the user may read every order.
11. **Relying on URL prefixes while ignoring methods:** `GET /api/orders` and `POST /api/orders` can require completely different authorities.
12. **Skipping negative tests:** every permission needs at least one request that must pass and one that must be denied; especially test same path, different method.
13. **Equating "method did not match" with "denied":** a non-matching matcher continues to the next rule; a matching matcher with insufficient authority stops at that rule.

## 15. Practice Exercises with Answers

Assume the following rules in order:

~~~java
.requestMatchers(HttpMethod.GET, "/api/documents/**")
    .hasAuthority("DOC_READ")
.requestMatchers(HttpMethod.POST, "/api/documents")
    .hasAuthority("DOC_CREATE")
.requestMatchers(HttpMethod.DELETE, "/api/documents/{id}")
    .hasAuthority("DOC_DELETE")
.requestMatchers("/api/documents", "/api/documents/**")
    .denyAll()
.anyRequest().denyAll()
~~~

**Question 1.** A user with only `DOC_READ` sends `GET /api/documents/8`. What happens?

Answer: the GET + `/api/documents/**` matcher matches, and the user has `DOC_READ`, so it **passes the authorization step**. Whether the Controller returns document 8 is a separate matter.

**Question 2.** The same user sends `DELETE /api/documents/8`. Does the GET rule apply?

Answer: no; the method differs. The DELETE rule matches and requires `DOC_DELETE`, so it is denied. If this is a browser request, CSRF could also block it earlier.

**Question 3.** A user with `DOC_CREATE` sends `POST /api/documents/8`. Since they have create permission, is it allowed?

Answer: no. The POST rule is only for `/api/documents`, which does not match `/api/documents/8`; the request falls through to `denyAll`.

**Question 4.** Why can putting `requestMatchers("/api/**").authenticated()` at the top break authorization?

Answer: the broad rule can become the first matching matcher for GET/POST/DELETE requests, causing the `DOC_READ` / `DOC_CREATE` / `DOC_DELETE` checks below to never be evaluated.

**Question 5.** Should you add `requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()` when a browser hits a CORS error?

Answer: do not treat that as a default fix. Configure proper CORS so preflight is handled before authentication checks, with the exact allowed origins, methods, and headers.

**Question 6.** In MockMvc, `POST /api/documents` with `DOC_CREATE` still receives 403. What should you check first?

Answer: besides the authority and matcher, check whether a valid CSRF token (`.with(csrf())`) was provided, since the example does not disable CSRF.

**Question 7.** To restrict `GET /api/documents/{id}` only to the document owner, is a method/path matcher enough?

Answer: not yet. The matcher identifies the endpoint; permission on record `id` must be enforced by business policy, such as in service/method security or an `AuthorizationManager` depending on architecture.

## 16. Pre-Production Checklist

- Have you listed every genuinely supported **method + path**, including special POST actions, PATCH, HEAD, and management endpoints?
- Are specific rules placed before broad rules, with `anyRequest().denyAll()` for the remainder?
- Do the authorities in `hasAuthority` match the exact strings granted to users? Did anyone accidentally change `hasAuthority("ORDER_READ")` to `hasRole("ORDER_READ")`?
- Does the security matcher configuration match the actual servlet/context/path scope?
- Have you tested the same path with multiple methods, for both authorized and unauthorized users?
- Have you tested CSRF on write operations and CORS preflight if there is a cross-origin frontend?
- Have you verified per-resource permissions, not just endpoint-level permissions?
- Have you tested similar paths, non-existent paths, undeclared methods, and multiple `SecurityFilterChain` beans if present?

**Principle to remember:** in Spring Security, an endpoint protection rule is a **`(RequestMatcher, AuthorizationManager)`** pair. A combined method-and-path matcher only selects the **kind of request**; the permission condition is evaluated only when that matcher is the **first match**. A complete policy must state the accepted methods, corresponding authorities, and how remaining requests are denied.

## Reference Documentation

- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): matcher ordering, paths, methods, `securityMatcher`, and `requestMatchers`.
- [Spring Security — CORS in Servlet](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): preflight processing order and Spring Security integration.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): protecting state-changing requests and CSRF scope.
- [Spring Security — MockMvc testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html): security test integration.
- [Spring Security — CSRF testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): providing CSRF tokens in MockMvc.
- [Spring Security — Reactive request authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): corresponding configuration in WebFlux.
