# Path-Based Authorization Combined with HTTP Methods in Spring Security Servlet

## 1. Why Combine Both URL and HTTP Method?

An API can use the **same path** to perform operations with very different sensitivity levels. For example: reading the list of articles via `GET /api/articles`, creating an article via `POST /api/articles`, updating an article via `PUT /api/articles/42`, and deleting an article via `DELETE /api/articles/42`.

If the security policy merely says "the user can access `/api/articles/**`", it can easily **accidentally allow write/delete operations** for someone who should only have read permission. Conversely, if the ADMIN role is required across the entire prefix, public read requests or editor requests may be overly blocked.

In **Spring Security Servlet**, `authorizeHttpRequests` can combine a **path `RequestMatcher`** and **`HttpMethod`** to describe each permission accurately:

- `GET`, `HEAD`: typically used to read metadata/resources; can still contain sensitive data and are not automatically public.
- `POST`: typically used to create resources or perform side-effecting operations.
- `PUT`: typically used to replace/update resources.
- `PATCH`: typically used for partial updates.
- `DELETE`: typically used to delete.
- `OPTIONS`: may serve CORS preflight; must be handled under CORS policy rather than equated with business operations.

Key learning point: **authorization decisions must consider both "where is the request going?" and "what does the request intend to do?"**, then apply the *least privilege* principle and end with a **deny-by-default** rule.

This lesson targets **Spring Security 6.x, Spring MVC / Servlet stack, `HttpSecurity` and `SecurityFilterChain`, Java 17+**. WebFlux uses its own reactive API and does not transfer `HttpSecurity` directly to `ServerHttpSecurity`. The runnable example pins Spring Boot 3.3.5 as a learning baseline, not implying it is the latest or still under support; new applications must choose dependency versions matching support policies.

## 2. Where Does Request Authorization Happen in the Filter Chain?

Simplified diagram:

```text
HTTP request: PUT /api/articles/42
    |
Servlet container
    |
DelegatingFilterProxy -> FilterChainProxy
    |
Select SecurityFilterChain matching the request
    |
Authentication filters (HTTP Basic / bearer / form session ...)
    |
SecurityContextHolder holds Authentication (or anonymous)
    |
AuthorizationFilter
    |
authorizeHttpRequests -> RequestMatcher + AuthorizationManager
    |
match path + method -> hasRole / hasAuthority / authenticated / denyAll
    |
ALLOW -> DispatcherServlet -> Controller/Service
DENY  -> Spring Security handles Authentication/AccessDenied
```

**Authentication** answers "who is calling?"; **authorization** answers "is that caller permitted to perform this operation?". `authorizeHttpRequests` does not re-verify passwords itself; it uses the `Authentication` already placed in `SecurityContextHolder` by an authentication mechanism.

Depending on the request and configuration, insufficient authentication may return **401 Unauthorized** (for HTTP Basic APIs) or redirect to the login page (with form login). When authenticated but lacking permission, **403 Forbidden** is typically returned.

**Distinction:** `CsrfFilter` can return 403 before authorization even when the role is completely right. Do not infer "403 means missing role" without checking CSRF and the actual chain.

### Two Easily Confused Matcher Layers

- **`http.securityMatcher("/api/**")`**: decides whether the **entire `SecurityFilterChain`** is selected for the request.
- **`authorizeHttpRequests(...requestMatchers(...))`**: once a chain has been selected, decides **permissions for requests inside that chain**.

Putting `requestMatchers("/api/**")` inside a chain whose `securityMatcher` does not match will not make requests "jump" into that chain. And `FilterChainProxy` selects the **first matching chain in order**, rather than combining rules across all chains for a single request.

## 3. RequestMatcher Combining HTTP Method and Path

Typical DSL syntax:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/articles/**")
        .hasAnyRole("READER", "EDITOR", "ADMIN")
    .requestMatchers(HttpMethod.POST, "/api/articles")
        .hasAnyRole("EDITOR", "ADMIN")
    .requestMatchers(HttpMethod.DELETE, "/api/articles/*")
        .hasRole("ADMIN")
    .anyRequest().denyAll());
```

This is a **configuration snippet**, requiring placement inside a method configuring `HttpSecurity` and importing `org.springframework.http.HttpMethod`. When Spring MVC is present, matcher selection may use MVC-aware matchers; when MVC is absent, pattern matching can differ. Always test actual patterns with the framework/version in use.

A `requestMatchers(HttpMethod.GET, "/api/articles/**")` matches only when **the method is GET** and the path matches the pattern. It does **not automatically apply** to POST/PUT/DELETE on the same URL. `requestMatchers("/api/articles/**")` specifies no method and therefore can match multiple methods depending on the pattern.

### Reading Path Forms

| Pattern | Common Intent | Pitfall |
|---|---|---|
| `/api/articles` | Collection URL, e.g., GET list / POST create | Must not assume it is always covered cleanly by every `/**` matcher across all technologies |
| `/api/articles/*` | One trailing segment, e.g., `/api/articles/42` | Not intended for `/api/articles/42/comments` |
| `/api/articles/**` | Multiple segments under the prefix, depending on matcher | Broader than necessary if the endpoint has sensitive sub-branches |
| `/api/**` | All API URLs under the prefix | If applied too early, can shadow specific rules |
| `/**` | Many paths across the application | Use only when system endpoints and defaults/fallbacks are well understood |

**Do not equate Spring MVC patterns, Ant-style patterns, and regular expressions.** Syntax and matching capability differ across `MvcRequestMatcher`, `AntPathRequestMatcher`, or `PathPatternRequestMatcher`, versions, and configuration. The main example in section 9 uses simple single-segment routes to firmly test boundaries.

Paths in authorization normally **do not include the query string as part of the path pattern**. For example, `GET /api/articles/42?preview=true` is still the same corresponding route path; if `preview=true` exposes extra sensitive data, a dedicated business policy is needed rather than treating query parameters as a separate path.

### Method Matching Must Be Exact

`HttpMethod.GET` does not mean "all safe methods"; `HttpMethod.HEAD` and `HttpMethod.OPTIONS` are distinct values. The framework may support HEAD in an MVC controller equivalently to GET for HTTP semantics, yet a security matcher restricted to GET **should not be assumed to automatically allow HEAD**. If you want to allow HEAD, declare a policy and test it explicitly.

For PATCH, PUT, and DELETE, clients can use method override mechanisms if the app configures `HiddenHttpMethodFilter` or a proxy supports it. Therefore inspect the **effective method seen by Spring Security**, not merely an HTML form showing POST. Do not enable method override or trust untrusted headers casually.

## 4. Critical Rule: Specific to General Order

`authorizeHttpRequests` evaluates declared matchers **in order**, using the first matching rule to make the decision. Thus:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.DELETE, "/api/articles/*")
        .hasRole("ADMIN")
    .requestMatchers(HttpMethod.GET, "/api/articles/*")
        .hasAnyRole("READER", "EDITOR", "ADMIN")
    .requestMatchers("/api/articles/**")
        .authenticated()
    .anyRequest().denyAll())
```

The sample above has an issue: the last rule for all methods of `/api/articles/**` only requires authenticated, so unlisted methods like PATCH or POST to an unexpected URL can slip through to MVC if a route matches. MVC may ultimately return 404/405, yet **you should never rely on non-existent controllers as a security policy**; when a new route is added later, access may accidentally become too broad.

An even more dangerous anti-pattern:

```java
// WRONG if DELETE should be for ADMIN only:
.requestMatchers("/api/**").authenticated()
.requestMatchers(HttpMethod.DELETE, "/api/articles/*").hasRole("ADMIN")
```

The general rule earlier already matched DELETE, so the ADMIN rule below becomes unreachable for that request. This commonly happens when a team adds a "more secure-looking" rule at the bottom of the config without noticing a broad matcher blocking it above.

### Stricter Configuration

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public").permitAll()
    .requestMatchers(HttpMethod.GET, "/api/articles", "/api/articles/*")
        .hasAnyRole("READER", "EDITOR", "ADMIN")
    .requestMatchers(HttpMethod.POST, "/api/articles")
        .hasAnyRole("EDITOR", "ADMIN")
    .requestMatchers(HttpMethod.PUT, "/api/articles/*")
        .hasAnyRole("EDITOR", "ADMIN")
    .requestMatchers(HttpMethod.DELETE, "/api/articles/*")
        .hasRole("ADMIN")
    .requestMatchers("/api/articles", "/api/articles/*")
        .denyAll()
    .anyRequest().denyAll())
```

Once all intended methods/paths have rules, the rest is **deny all**. This reduces the risk of a new controller being accidentally exposed when nobody updates authorization config. However, you must **update tests** whenever adding valid endpoints, including public health and actuator if enabled by policy.

### Why Have Both a Prefix Fallback and anyRequest?

`requestMatchers("/api/articles", "/api/articles/*").denyAll()` expresses the intent "all other methods on these two route forms are blocked"; `anyRequest().denyAll()` protects all undeclared URLs. In terms of effective runtime behavior in the example project, `anyRequest().denyAll()` already blocks unlisted URLs; the extra prefix rule makes it clear in code review that unpermitted methods on articles are explicitly denied.

## 5. hasRole, hasAuthority, and Permissions

Spring Security has two common rule forms:

- `hasRole("ADMIN")` typically checks an authority carrying the `ROLE_ADMIN` prefix in default configurations.
- `hasAnyRole("EDITOR", "ADMIN")` accepts one of the corresponding authorities.
- `hasAuthority("article:write")` checks the exact authority string without automatically adding a prefix.
- `hasAnyAuthority("article:read", "article:write")` permits when one of the specified permissions is present.
- `authenticated()` only requires the request to have a qualifying authentication, **without guaranteeing the user may edit/delete**.
- `permitAll()` passes the authorization step for matching requests, **without bypassing CSRF, other filters, or business logic**.
- `denyAll()` denies all requests matching the rule.

Example:

```java
.requestMatchers(HttpMethod.POST, "/api/articles")
    .hasAuthority("article:create")
.requestMatchers(HttpMethod.DELETE, "/api/articles/*")
    .hasAuthority("article:delete")
```

Fine-grained authority rules generally fit systems with functional permissions. Roles can represent a **permission bundle** and may need mapping/hierarchy per business rules. Never pass `hasRole("ROLE_ADMIN")` out of habit when the default prefix already prepends `ROLE_`, as that can misconfigure or throw an exception depending on the API.

**Tenant/ownership note:** `DELETE /api/articles/42` with role EDITOR or authority `article:delete` is still not enough to confirm that the article **belongs to the organization/user the requester is allowed to manage**. Resource-level authorization must be checked in the service, such as via `@PreAuthorize` or a service policy querying data by principal/tenant. HTTP rules are only the outer layer of defense.

## 6. Deciding 401, 403, and CSRF Errors

A practical behavior table when designing integration tests:

| Request | Authentication | Rule | Expectation |
|---|---|---|---|
| Private GET | No credentials | requires auth/role | 401 with HTTP Basic API, or login redirect with form-based |
| Private GET | Wrong credentials | Authentication fails | 401 with Basic challenge/entry point |
| Private GET | Valid Reader | hasRole(READER) | Allowed, if controller exists |
| POST create | Valid Reader | hasAnyRole(EDITOR,ADMIN) | 403 after valid CSRF |
| POST create | Valid Editor, with CSRF | hasAnyRole(EDITOR,ADMIN) | Allowed |
| POST create | Valid Editor, missing CSRF | CsrfFilter may block before authorization | Typically 403 |
| DELETE item | Valid Editor | hasRole(ADMIN) | 403 even with CSRF |
| DELETE item | Valid Admin, with CSRF | hasRole(ADMIN) | Allowed |
| Undeclared PATCH | Valid Admin | denyAll | 403 |
| Unpermitted nested GET path | Valid Admin | denyAll | 403 |

**Important:** 403 does not point to a single cause. When testing role permissions, send a **valid CSRF token** on POST/PUT/PATCH/DELETE before concluding 403 came from authorization. When testing CSRF, intentionally omit the token on a request where the user already holds the required role.

### Keep CSRF When Credentials Are Sent Automatically by Browsers

Form login and many websites use cookies/sessions, requiring CSRF protection along the trust boundary. With HTTP Basic, browsers can also auto-attach the Authorization header for an origin after being challenged, so **do not assume Basic is completely free of CSRF risk**. In the runnable example, CSRF is **not disabled**, and MockMvc uses `with(csrf())` for state-changing requests.

If an API uses bearer tokens explicitly attached by JavaScript/mobile clients in the Authorization header without auto-sent credentials, a different CSRF policy may apply, though it requires concrete analysis. Never copy `csrf(AbstractHttpConfigurer::disable)` unconditionally just to make a POST test return 201.

## 7. Multiple SecurityFilterChains: Mind the Boundary Before Authorization

A system may use two chains:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/articles/**")
                .hasAuthority("SCOPE_articles.read")
            .requestMatchers(HttpMethod.POST, "/api/articles")
                .hasAuthority("SCOPE_articles.write")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
        .build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}
```

The snippet above **illustrates two beans in a project with appropriate OAuth2 Resource Server imports and dependencies**, not standalone runnable code using only web/security starters. Bearer JWTs require configuring issuer/JWK, signature/audience/claims validation, and proper authority mapping. The scope strings are illustrative policy names.

The core point is **chain order and matchers**: `/api/**` is handled by the API chain first, while unmatched URLs can be handled by the web chain. A misplaced `securityMatcher("/api/v1/**")` causes `/api/v2/**` to fall into the fallback with a different policy; therefore test all prefixes thoroughly.

When using multiple chains, **`requestMatchers` in one chain do not grant permissions to requests that never enter that chain**. Missing a fallback chain can also leave an endpoint outside Spring Security if it matches no `SecurityFilterChain`. In real environments, test "unexpected paths" as well rather than only known URLs.

## 8. CORS Preflight, HEAD/OPTIONS, Path Bugs, and Forwards

HTTP method authorization often runs into the following situations:

### CORS OPTIONS

Browsers may send:

```text
OPTIONS /api/articles
Origin: https://frontend.example
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization, content-type
```

This is a **preflight**, not the actual article-creation request. If the chain blocks OPTIONS before CORS is configured, the frontend may report a "CORS error" even when the POST with a token actually has permission.

The preferred solution is proper CORS integration via `http.cors(...)` and configuring `CorsConfigurationSource` or Spring MVC CORS, restricting valid origins/methods/headers. **Do not allow all OPTIONS from every origin by default with a broad rule** if the app has strict policies. CORS is a browser control, **not a substitute for authorization**, and passing preflight does not mean the actual POST is permitted.

### HEAD

An MVC GET endpoint can serve HEAD under MVC mechanics, yet a GET security matcher should not be assumed to include HEAD automatically. If the API intends to support HEAD, declare `requestMatchers(HttpMethod.HEAD, ...)` with an explicit policy and test it. Do not accidentally open HEAD to endpoints leaking inappropriate metadata.

### URL Encoding and Path Normalization

- Paths containing `%2F`, multiple slashes, `;`, `..` segments, case differences, or servlet context paths can be handled differently by the container, firewall, or MVC.
- Never write custom security checks like `request.getRequestURI().startsWith("/admin")` assuming it equals framework `requestMatchers("/admin/**")`.
- When behind a reverse proxy or context path, test both external real-world URLs and internal security paths received by the application.
- `HttpFirewall`/Servlet container may reject malformed requests before reaching authorization, which is the proper outcome rather than "bypassing rules".

### ERROR and FORWARD Dispatches

After authorization, a request may go through `ERROR` or `FORWARD` dispatches. Some apps need explicit policies for error handling or view rendering; avoid granting blanket access with `permitAll("/**")` just to fix a 403 error page. Understand dispatcher types and configure filter mappings/authorization appropriately per framework.

### Path Variables and Query Parameters

If the URL is `GET /api/articles/42`, the security matcher knows the request targets the item route; it does not know whether article 42 is confidential, which tenant it belongs to, or whether it is published. Checks like "only the author and admin may edit drafts" must rely on live data inside service/authorization logic, not merely path strings.

## 9. Complete Example: Java 17, Spring Boot 3.3.5, Maven, and MockMvc

This example creates a simple Spring MVC Servlet application with three accounts: `reader`, `editor`, and `admin`. Authorization is based on **exact HTTP method and URL**, independent of having a shared controller across methods. The demo chooses HTTP Basic so tests clearly show 401 instead of form-login redirects, while **keeping default CSRF** to demonstrate that CSRF 403 differs from role 403.

**Note:** Spring Boot 3.3.5 is an illustrative dependency baseline for Spring Security 6 syntax and Java 17; it does not imply it is the newest or recommended production release at all times. In practice, use a security-supported release and review release notes.

### 9.1. Project Structure

```text
method-path-authorization/
├── pom.xml
└── src/
    ├── main/java/example/methodpath/
    │   ├── MethodPathApplication.java
    │   ├── SecurityConfig.java
    │   └── ArticleController.java
    └── test/java/example/methodpath/
        └── MethodPathAuthorizationTest.java
```

### 9.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>method-path-authorization</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 9.3. Spring Boot Application

File `src/main/java/example/methodpath/MethodPathApplication.java`:

```java
package example.methodpath;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MethodPathApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodPathApplication.class, args);
    }
}
```

### 9.4. SecurityConfig: Declaring Method + Path Rules

File `src/main/java/example/methodpath/SecurityConfig.java`:

```java
package example.methodpath;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .roles("READER")
                .build(),
            User.withUsername("editor")
                .password(encoder.encode("editor-pass"))
                .roles("EDITOR")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers(HttpMethod.GET,
                    "/api/articles", "/api/articles/*")
                    .hasAnyRole("READER", "EDITOR", "ADMIN")
                .requestMatchers(HttpMethod.POST, "/api/articles")
                    .hasAnyRole("EDITOR", "ADMIN")
                .requestMatchers(HttpMethod.PUT, "/api/articles/*")
                    .hasAnyRole("EDITOR", "ADMIN")
                .requestMatchers(HttpMethod.DELETE, "/api/articles/*")
                    .hasRole("ADMIN")
                .requestMatchers("/api/articles", "/api/articles/*")
                    .denyAll()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .build();
    }
}
```

**Explanation and boundaries:**

- Reader only has `ROLE_READER`, Editor has `ROLE_EDITOR`, Admin has `ROLE_ADMIN`. In this lesson, GET is for all three roles; editor/admin may write; only admin may DELETE. This is an illustrative policy with no hidden role hierarchy.
- `formLogin(AbstractHttpConfigurer::disable)` prevents unauthenticated API requests from being redirected to a form-based HTML login page. `httpBasic(...)` lets tests send Basic credentials easily and receive HTTP 401 when appropriate.
- CSRF **is not disabled**. POST/PUT/DELETE from MockMvc need `with(csrf())`, separating CSRF errors from role errors. For Basic APIs used in browsers, keeping CSRF is a cautious choice; production must design the CSRF token lifecycle for actual clients.
- Do not add a broad `requestMatchers("/api/**").authenticated()` rule in front of the role rules.
- `anyRequest().denyAll()` blocks URLs outside the permitted list; when adding valid endpoints, you must add rules and tests.
- Fixture passwords are hashed with BCrypt. Hardcoded passwords in the example are strictly for tests, never for real accounts.
- `SecurityFilterChain` sits in the Servlet module; if multiple chains exist, specify matchers and priority by design.

### 9.5. Controller Representing HTTP Operations

File `src/main/java/example/methodpath/ArticleController.java`:

```java
package example.methodpath;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ArticleController {

    @GetMapping("/public")
    public String publicPage() {
        return "PUBLIC_OK";
    }

    @GetMapping("/api/articles")
    public String allArticles() {
        return "ARTICLES";
    }

    @GetMapping("/api/articles/{id}")
    public String oneArticle(@PathVariable String id) {
        return "ARTICLE:" + id;
    }

    @PostMapping("/api/articles")
    @ResponseStatus(HttpStatus.CREATED)
    public String create(@RequestBody String title) {
        return "CREATED:" + title;
    }

    @PutMapping("/api/articles/{id}")
    public String update(@PathVariable String id, @RequestBody String title) {
        return "UPDATED:" + id + ":" + title;
    }

    @DeleteMapping("/api/articles/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable String id) {
        // Demo does not persist to a database; authorization is checked first.
    }
}
```

The controller simply returns response strings to observe permissions. It **does not implement real save/edit/delete** or object-level authorization. In a real application, check tenant, owner, article state, input validation, business transactions, and audit logging.

### 9.6. MockMvc Tests Distinguishing Role, Method, Path, and CSRF

File `src/test/java/example/methodpath/MethodPathAuthorizationTest.java`:

```java
package example.methodpath;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.head;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MethodPathAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsOpen() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("PUBLIC_OK"));
    }

    @Test
    void anonymousReaderRouteRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/articles"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidBasicCredentialIsRejected() throws Exception {
        mvc.perform(get("/api/articles")
                .with(httpBasic("reader", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readerMayReadCollectionAndIndividualArticle() throws Exception {
        mvc.perform(get("/api/articles")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("ARTICLES"));

        mvc.perform(get("/api/articles/42")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("ARTICLE:42"));
    }

    @Test
    void readerCannotCreateEvenWithValidCsrf() throws Exception {
        mvc.perform(post("/api/articles")
                .with(httpBasic("reader", "reader-pass"))
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("Example"))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorMayCreateAndUpdate() throws Exception {
        mvc.perform(post("/api/articles")
                .with(httpBasic("editor", "editor-pass"))
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("Example"))
            .andExpect(status().isCreated())
            .andExpect(content().string("CREATED:Example"));

        mvc.perform(put("/api/articles/42")
                .with(httpBasic("editor", "editor-pass"))
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("Revised"))
            .andExpect(status().isOk())
            .andExpect(content().string("UPDATED:42:Revised"));
    }

    @Test
    void editorCannotDeleteEvenWithCsrf() throws Exception {
        mvc.perform(delete("/api/articles/42")
                .with(httpBasic("editor", "editor-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanDelete() throws Exception {
        mvc.perform(delete("/api/articles/42")
                .with(httpBasic("admin", "admin-pass"))
                .with(csrf()))
            .andExpect(status().isNoContent());
    }

    @Test
    void missingCsrfBlocksEvenAnAuthorizedEditor() throws Exception {
        mvc.perform(post("/api/articles")
                .with(httpBasic("editor", "editor-pass"))
                .contentType(MediaType.TEXT_PLAIN)
                .content("Example"))
            .andExpect(status().isForbidden());
    }

    @Test
    void undeclaredPatchMethodIsDeniedEvenForAdmin() throws Exception {
        mvc.perform(patch("/api/articles/42")
                .with(httpBasic("admin", "admin-pass"))
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("Change"))
            .andExpect(status().isForbidden());
    }

    @Test
    void nestedPathIsNotCoveredBySingleSegmentRule() throws Exception {
        mvc.perform(get("/api/articles/42/comments")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void headIsNotGrantedByExplicitGetOnlyRule() throws Exception {
        mvc.perform(head("/api/articles/42")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isForbidden());
    }
}
```

**Why each assertion group is needed:**

- Missing/wrong credentials: HTTP Basic entry point yields **401**, rather than assuming the controller threw an error.
- GET reader: verifies the lower role can read the collection and items.
- POST reader: has valid CSRF yet still **403** for lacking Editor/Admin role.
- POST/PUT editor: has CSRF and role, allowed into MVC/controller; status/body match code.
- DELETE editor: valid CSRF yet still denied by the ADMIN rule.
- DELETE admin: has CSRF and role, controller returns 204.
- POST editor missing CSRF: rejected by CSRF, **must not** be used to prove the role is wrong.
- Unpermitted PATCH, deeply nested path, and HEAD: **`denyAll`** fallback blocks unpermitted methods/paths even when the principal is admin.
- Public test shows `permitAll()` allows requests without authentication, while other filters may still run per policy.

**Expectation:** 12 tests pass in an environment with matching dependencies/illustrative code. This is a **static check of the lesson, not a log of tests actually executed**. If MVC matcher behavior differs in your project's version, test failures are evidence to fix the real config—never disable authorization/CSRF just to "turn tests green".

### 9.7. Commands to Run

In the project directory with `pom.xml`, JDK 17+ and Maven with resolvable dependencies are required:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

When the server runs on default port 8080 (if free), you can observe read operations:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/articles
curl -i -u reader:reader-pass http://localhost:8080/api/articles
curl -i -u reader:reader-pass http://localhost:8080/api/articles/42
```

Expected status/body results respectively:

```text
GET /public                           -> 200 PUBLIC_OK
GET /api/articles (anonymous)         -> 401
GET /api/articles (reader)            -> 200 ARTICLES
GET /api/articles/42 (reader)         -> 200 ARTICLE:42
```

**Do not immediately run curl POST/PUT/DELETE in this example while omitting the CSRF token**, and conclude the methods are blocked by security roles: without a CSRF token, you usually only see a 403 from `CsrfFilter`. Use MockMvc `with(csrf())` as in section 9.6, or implement a proper CSRF token fetch/submit mechanism for a real client.

Credentials `reader-pass`/`editor-pass`/`admin-pass` are fixtures; never deploy them to the public Internet, and never record real credentials in shell history or logs.

## 10. Guide to Reviewing Policies Before Deployment

### Step 1 — List the Action Matrix per Resource

Example for an article resource:

| Endpoint | Method | Reader | Editor | Admin |
|---|---|---|---|---|
| `/api/articles` | GET | Allow | Allow | Allow |
| `/api/articles/{id}` | GET | Allow | Allow | Allow |
| `/api/articles` | POST | Deny | Allow | Allow |
| `/api/articles/{id}` | PUT | Deny | Allow | Allow |
| `/api/articles/{id}` | DELETE | Deny | Deny | Allow |
| `/api/articles/{id}` | PATCH | Deny | Deny | Deny (not yet implemented) |
| `/api/articles/{id}/comments` | GET | Deny | Deny | Deny (not yet implemented) |

The matrix should be maintained alongside the API spec and integration tests. When adding PATCH, add a method-scoped rule, controller route, and allow/deny role tests. Do not rely on "admin has all permissions" if policy requires endpoints to be allowed only when explicitly declared.

### Step 2 — Check Matcher Order

- Public/specific rules before general rules.
- HTTP-method-scoped rules must come **before** path-only rules of overlapping scope.
- `/api/**` or `anyRequest()` rules normally go at the end and must be intentional.
- Also check similar prefixes like `/api/article`, `/api/articles-old`, `/api/admin`, servlet context path, and lowercase/uppercase.

### Step 3 — Check Responses and Prerequisites

- 401/redirect when missing authentication;
- 403 when authenticated but missing authority;
- 403 from CSRF when an unsafe request lacks a token;
- 404/405 only when an authorized request reaches MVC without a matching route/method — never treat 404/405 as a strong enough security policy;
- CORS preflight properly configured without accidentally exposing the whole API;
- Explicit decisions for HEAD/OPTIONS.

### Step 4 — Check Permissions at Resource/Service Layer

HTTP path + method only check the outer layer. Add logic for owner, tenant, field-level access, article state, or business rules right where data is manipulated. Do not treat `hasRole("EDITOR")` as sufficient to update someone else's article.

### Step 5 — Test Unexpected Paths Too

Write tests for undeclared methods, deeply nested paths, different prefixes, requests missing roles, wrong credentials, missing CSRF, other filter chains, and URLs behind proxies. Defaulting to `denyAll` surfaces misconfigurations as failing tests rather than silently opening access.

## 11. Common Mistakes

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Reader DELETE still gets processed | Broad `authenticated()` rule placed before ADMIN DELETE rule | Move specific method+path rule earlier, keep deny-by-default |
| Editor POST gets 403 despite right role | Missing CSRF token or different security matcher than expected | Send valid CSRF in test, check which chain is selected |
| GET to readable endpoint returns 401 | Missing credentials, expired session, or wrong HTTP Basic | Distinguish authentication vs. authorization |
| Same URL GET 200 but PUT 403 | Each method has its own rule or CSRF | This may be the right policy; inspect permissions and CSRF |
| Right role name yet rule still 403 | Wrong `ROLE_` prefix or authorities differ from design | Check `Authentication.getAuthorities` and `hasRole`/`hasAuthority` |
| Correct POST rule never gets used | Broad path rule before it already matched | Inspect `requestMatchers` order |
| New endpoint accidentally exposed | Overly broad `authenticated()`/`permitAll()` fallback | Use `anyRequest().denyAll()` and add tests when opening endpoints |
| New endpoint keeps getting 403 | `denyAll` fallback active without a valid rule declared | Add explicit method+path rule and tests |
| HEAD handled differently from GET | Security matcher matches methods separately | Declare/test HEAD if needed |
| CORS OPTIONS rejected | CORS not integrated before relevant security policy | Configure CORS properly, test preflight from valid origin |
| Encoded/forwarded paths behave unexpectedly | Servlet firewall/`PathPattern`/proxy handles URLs differently | Test real URLs, check effective method/path |
| `@WithMockUser` passes but production fails | Mock principal test skips auth flow/cookie/token | Use MockMvc with Basic/form/bearer matching real app |
| Authorized user edits another tenant's data | Missing object-level authorization | Check ownership/tenant in service and data |
| Same URL gets different policy moving between `/api` and `/web` | Wrong `SecurityFilterChain` matchers/order | Test chain selection and fallback |

**Debugging principle:** first record the actual method, actual path, selected chain, `Authentication` and authorities, CSRF outcome, and first matching rule. Do not stare only at status codes or controller names and edit randomly.

## 12. End-of-Lesson Checklist

- [ ] Clear matrix of endpoint x HTTP method x permission/access context exists.
- [ ] `requestMatchers(HttpMethod.X, "...")` specifies exact methods for sensitive actions.
- [ ] Specific rules precede general rules; no broad `authenticated()` shadows role rules.
- [ ] Each `SecurityFilterChain`'s `securityMatcher` has the right prefix and order.
- [ ] Undeclared methods/paths fall into `denyAll()`, without relying on 404/405.
- [ ] `hasRole` and `hasAuthority` are chosen accurately according to `Authentication` mapping.
- [ ] API clients and authentication entry points return appropriate statuses (401/403 or form-login redirect).
- [ ] CSRF is analyzed per client credential mechanism; for browser cookie/form/Basic, never disable arbitrarily.
- [ ] CORS preflight, HEAD, OPTIONS, encoded paths, proxy/context paths, and forward/error dispatches are tested if used.
- [ ] Service-layer authorization checks ownership, tenant, and business conditions.
- [ ] Integration tests cover both allow and deny paths per method, plus unknown method/path tests.
- [ ] Never log credentials; keep proper audit logging for write/delete actions.

### Self-Check Questions

**1.** `requestMatchers("/api/**").authenticated()` appears before `requestMatchers(HttpMethod.DELETE, "/api/articles/*").hasRole("ADMIN")`. Can an authenticated Reader reach the DELETE route?  
**Answer:** The broad rule earlier can match and pass the authorization step for Reader, leaving the ADMIN rule unused. That is a misconfiguration; order properly and use a `denyAll` fallback.

**2.** Why can GET and DELETE on the same `/api/articles/42` have different permissions?  
**Answer:** `RequestMatcher` can inspect both HTTP method and path simultaneously. Reading an article carries different risk from deleting it.

**3.** An Editor POST without CSRF receives 403. Can you conclude the Editor lacks create permission?  
**Answer:** No. `CsrfFilter` may have rejected it before authorization. Send a valid CSRF token and then verify the role rule.

**4.** What authority name does `hasRole("ADMIN")` check by default?  
**Answer:** Usually `ROLE_ADMIN`, unless the system customized role prefix/authority mapping.

**5.** When do `HEAD` or `OPTIONS` need their own rules?  
**Answer:** When the API/client/framework uses them and there is a specific security decision; do not assume a GET matcher automatically permits HEAD or CORS preflight.

**6.** Why is `anyRequest().denyAll()` usually good for sensitive resources?  
**Answer:** New routes/methods are blocked until developers deliberately declare permissions and add tests.

**7.** On `POST /api/articles`, is the Editor role alone enough to prevent an Editor from creating articles in another tenant?  
**Answer:** No. HTTP rules know method/path/authorities but do not verify data ownership/tenant themselves; business-layer checks are required.

**Conclusion:** designing HTTP authorization in Spring Security Servlet with **method + path** should be written like an action matrix: **specific rules first, explicit methods, appropriate authorities, deny-by-default last**. Combine this with CSRF, CORS, authentication entry points, and object-level authorization so the policy is both accurate and free of unintended privilege expansion.