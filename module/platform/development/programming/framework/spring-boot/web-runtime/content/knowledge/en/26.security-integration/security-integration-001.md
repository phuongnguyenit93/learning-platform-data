# Impact of spring-boot-starter-security on a Web Application

## 1. What Changes When You Add the Security Starter?

A Spring Boot project might have a controller that works fine before security is installed:

```java
@RestController
class HelloController {
    @GetMapping("/hello")
    String hello() {
        return "hello";
    }
}
```

When only `spring-boot-starter-web` is present, a `GET /hello` request typically returns HTTP 200 with body `hello` if there are no custom security components. However, after adding:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-security'
```

Spring Boot detects Spring Security on the classpath and **auto-configures security for the web application**. If the application does not provide an alternative configuration, many endpoints that were previously accessible without logging in will now **require authentication**; a browser may be redirected to a login page, while an API client may receive HTTP 401. Requests that modify data via POST/PUT/PATCH/DELETE may fail with **HTTP 403 due to a missing CSRF token**, even when the caller is already authenticated.

**Key point:** the starter does not merely add a Java library. It introduces a **security filter chain/web filter chain** and default authentication beans that affect HTTP requests, responses, cookies/sessions, error handling, tests, and frontend integration.

This article focuses on **Spring Boot 3.3.x, Spring Security 6.3.x, and Java 17+** for stable examples. For real production systems, you should track a supported Spring Boot branch and apply security fixes. Configuration in newer major versions may change packages/APIs.

## 2. Before and After Adding Spring Security

| Scenario | Without Spring Security (plain web defaults) | With starter-security, no custom configuration |
|---|---|---|
| `GET /hello` without credentials | Usually HTTP 200 | Usually HTTP 401 (API) or 302 to login (browser) |
| `GET /public` even though named “public” | No protection rules from Spring Security | May still require login because **path names do not automatically create exceptions** |
| Login | No Spring Security login flow | Supports form login and HTTP Basic |
| Default account | No `user` auto-created by Spring Security | In-memory user `user` and a randomly generated password for development |
| `POST /orders` from browser/client | Invokes controller if route is valid | May be blocked by authentication or **CSRF** before reaching the controller |
| Authentication/authorization | Implemented by the application or absent | Filter chain checks identity, authorities, and access rules |
| Response headers | Configured by framework/proxy/app | Spring Security adds default security headers |
| Static files and `/error` | Usually accessible if the path exists | Typically within protected scope by default, unless endpoints/routes are permitted |
| Actuator | Depends on whether actuator starter is present | Has separate auto-security policy for Actuator, especially the health endpoint |
| MockMvc tests | Can call endpoints directly | Tests must account for authentication, roles, CSRF, and the security filter chain |

It is important to distinguish between **starter defaults** and what happens after you define a `SecurityFilterChain` bean. Once a custom chain is defined, **Boot backs off from applying the entire default web chain**; at that point, access rules are your responsibility. This can cause vulnerabilities if a developer only permits one group of URLs and accidentally leaves other endpoints unprotected by any chain.

**Important exception:** login mechanisms (such as `/login`) need to be accessible before authentication; saying “every URL is strictly blocked” is an overstatement. Spring Boot 3.3 describes protecting **application endpoints** by default, including `/error`; when Actuator is present, auto-configuration typically permits health and secures other exposed Actuator endpoints.

## 3. Which Beans Does Spring Boot Auto-Configure?

On the Servlet/MVC stack, the Spring Boot 3.3 documentation describes the roles of:

- `SecurityAutoConfiguration` and accompanying web configuration: automatically integrates Spring Security with the servlet stack.
- `UserDetailsServiceAutoConfiguration`: provides a single-user in-memory `UserDetailsService` if no corresponding alternative authentication infrastructure is present.
- `DefaultAuthenticationEventPublisher`: publishes authentication events for systems with appropriate listeners/monitoring.
- Default `SecurityFilterChain`: requires authentication and enables login mechanisms suited to web clients.

On WebFlux, the equivalents are `ReactiveSecurityAutoConfiguration`, `ReactiveUserDetailsServiceAutoConfiguration`, `SecurityWebFilterChain`, and `ReactiveUserDetailsService`.

In the default dev configuration:
- Username: **`user`**.
- Password: randomly generated at startup, usually logged at WARN level as `Using generated security password: ...`.
- This password is **not a production password**, and it can change on restart.
- If logging is adjusted so that the `org.springframework.boot.autoconfigure.security` category does not print WARN logs, you may not see the password in the console even though the user is created.

You can set values for a test environment:

```properties
spring.security.user.name=demo
spring.security.user.password=local-demo-only
spring.security.user.roles=USER
```

However, plaintext passwords configured in source **must not be used in production**. Production must use a secret manager/identity provider, password hashing, rotation, and application-specific security policies. The `spring.security.user.*` properties apply to the **default user setup**; once you define your own `UserDetailsService` or another authentication mechanism, Boot adjusts auto-configuration and they may no longer be the actual account source.

### 3.1. Overriding the Default Web Chain Differs from Overriding the Default User

These are two separate decisions:

| Which bean do you add? | Main impact |
|---|---|
| `SecurityFilterChain` (MVC) | Boot backs off from **default web security rules**, but **does not automatically remove the default UserDetailsService** |
| `UserDetailsService`, `AuthenticationProvider`, or `AuthenticationManager` | Boot backs off from creating the corresponding default in-memory user |
| `SecurityWebFilterChain` (WebFlux) | Replaces/defines custom reactive access rules |
| `ReactiveUserDetailsService` / `ReactiveAuthenticationManager` | Replaces the default reactive user/authentication mechanism |
| Certain OAuth2 client/resource server/SAML dependencies | May cause default user auto-config to back off, depending on module type and stack |

**Do not assume:** “I have a `SecurityFilterChain`, so the generated user/password must have disappeared.” False: security rules and the user repository are auto-configured under separate conditions.

Also **do not assume** that adding starter-security automatically gives you a JWT/OAuth2/OpenID Connect/SAML provider or a database user table. Those features require other modules/configurations and a real identity source.

## 4. How Does an HTTP Request Flow Through the Filter Chain?

In Spring MVC/Servlet, security generally runs **before the controller**:

```text
Browser/API client
     │
     ▼
Servlet container (Tomcat/Jetty)
     │
     ▼
DelegatingFilterProxy
     │
     ▼
FilterChainProxy
     │
     └── Select SecurityFilterChain matching the request
             │
             ├── Load/manage SecurityContext
             ├── Security headers
             ├── CSRF checks by method/config
             ├── Authentication: session / HTTP Basic / form login / ...
             ├── Authorization: role/authority/URL rule
             └── Exception translation → 401/403/login redirect
                     │
                     ▼
              DispatcherServlet
                     │
                     ▼
                @Controller
                     │
                     ▼
                HTTP response
```

**Exact filter order and names depend on configuration**, so the diagram above is a logical model and does not guarantee that all filters are always present in a fixed order. Common classes on Servlet include `FilterChainProxy`, `SecurityContextHolderFilter`, `CsrfFilter`, `BasicAuthenticationFilter`, `UsernamePasswordAuthenticationFilter`, `ExceptionTranslationFilter`, and `AuthorizationFilter`.

General flow:
1. Security finds the chain matching the URL/method; if multiple chains exist, typically the first matching chain is selected.
2. The authentication mechanism reads credentials (session, Authorization Basic/Bearer, form fields, etc. depending on config) and populates `Authentication` in `SecurityContext`.
3. Authorization checks whether the user is allowed to proceed; when a rule requires `authenticated()`, anonymous users generally do not pass.
4. For requests requiring CSRF protection, the token is also verified. **Valid authentication does not exempt a request from CSRF**.
5. Only when all relevant rules allow it does the controller handle the request.

`Authentication` represents the principal, credentials (handled according to policy), authorities, and authenticated status. `Authorization` decides access permissions. **Authenticated does not mean Authorized**: a logged-in user can still receive 403 if they lack the `ADMIN` or `EDITOR` role.

An authentication failure usually results in `401 Unauthorized` for APIs using HTTP Basic; HTML users may be redirected to login. An authenticated user with insufficient permissions usually receives `403 Forbidden`. However, status codes can differ due to entry points, Accept headers, exception handlers, and custom config; always test your application's actual responses.

## 5. Why Does a Browser See a Login Page While curl Receives 401?

Spring Boot uses content negotiation/authentication entry points to decide the default behavior of a web app:
- A browser sending `Accept: text/html` is usually directed to `/login` via a `302` redirect if not authenticated.
- An API client usually sends `Accept: application/json` and may receive `401` with a `WWW-Authenticate: Basic ...` header when credentials are missing.
- If valid `Authorization: Basic ...` credentials are sent, a data-reading request may be permitted.
- If the username/password is wrong, the response is usually `401`; do not turn “wrong password” into `500` in custom authentication.

**Do not treat a 302 redirect as a controller error.** The request is typically intercepted by filters before reaching the handler. A browser automatically follows the redirect and displays the login page instead of the endpoint body, leading beginners to think the route disappeared.

Intentional test example:

```bash
curl -i -H 'Accept: application/json' http://localhost:8080/private
curl -i -H 'Accept: text/html' http://localhost:8080/private
```

The corresponding results in the default configuration are usually 401 and 302 to login; do not hardcode exact redirect headers or URLs when the framework/custom config can change them.

## 6. Complete Example A: MVC Application Before Custom Security

This example uses **Spring Boot 3.3.13 + Java 17 + Gradle** and requires no database. Initially **do not create `SecurityConfig`** so you can observe real auto-configuration behavior. Then add the custom chain in Section 8 and tests in Section 9.

Initial structure:

```text
security-starter-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/securitydemo/SecurityStarterApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/securitydemo/SecurityRulesTest.java  # Created in Section 9
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/resources/application.properties`** at the initial stage:

```properties
server.port=8080
# Do not set spring.security.user.* yet so you can observe the generated password.
```

**`src/main/java/com/example/securitydemo/SecurityStarterApplication.java`:**

```java
package com.example.securitydemo;

import java.security.Principal;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityStarterApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityStarterApplication.class, args);
    }
}

@RestController
class DemoController {

    @GetMapping("/public")
    String publicPage() {
        return "public content";
    }

    @GetMapping("/account")
    Map<String, String> account(Principal principal) {
        return Map.of("name", principal.getName());
    }

    @PostMapping(
            path = "/notes",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<SavedNote> save(
            @RequestBody NoteInput input,
            Principal principal) {
        // Demo does not write to a database; only illustrates authorization/CSRF conditions.
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new SavedNote(principal.getName(), input.text()));
    }
}

record NoteInput(String text) {}
record SavedNote(String owner, String text) {}
```

This is **one valid Java file**, with only `SecurityStarterApplication` as the top-level `public class`; the remaining controller and records in the same package are picked up by Boot component scan. Because there is no custom `SecurityFilterChain` bean yet, starter-security by default still protects **`/public`, `/account`, and `/notes`**.

**Run:**

```bash
gradle bootRun
```

If the project has the Gradle Wrapper: `./gradlew bootRun` (Linux/macOS) or `.\gradlew.bat bootRun` (Windows PowerShell). JDK 17+ and a Gradle version compatible with Boot 3.3.13 are prerequisites to run. The console will show the generated password for this startup run if the logger is at an appropriate WARN level.

### 6.1. Verifying the Difference Just by Adding the Dependency

**Without credentials:**

```bash
curl -i -H 'Accept: application/json' http://localhost:8080/public
curl -i -H 'Accept: application/json' http://localhost:8080/account
```

Despite the name `/public`, both requests will typically require authentication from security and return **HTTP 401** in an API client context. The controller has not been invoked.

**With default credentials:** replace `<GENERATED_PASSWORD>` with the exact password from the current run's log:

```bash
curl -i -u 'user:<GENERATED_PASSWORD>' \
  http://localhost:8080/account
```

Expected result if the password is correct: HTTP 200 and JSON like:

```json
{"name":"user"}
```

Using `-u` on the command line can expose credentials in shell history/process lists; this is only acceptable in a local lab with a development-generated password. Never log or copy production passwords into documentation.

**Authenticated POST without a CSRF token:**

```bash
curl -i -u 'user:<GENERATED_PASSWORD>' \
  -H 'Content-Type: application/json' \
  -d '{"text":"my note"}' \
  http://localhost:8080/notes
```

With default web app CSRF protection, a POST request without a token usually receives **403 Forbidden**. That is not a JSON mapping error: `CsrfFilter` can reject it before the controller reads `NoteInput`.

**To POST successfully from a browser with a session**, you must use the appropriate CSRF token mechanism for your UI/frontend (hidden form field or corresponding header/token repository). The test in Section 9 uses `spring-security-test` to provide a valid token rather than hardcoding a token.

### 6.2. What Has Not Changed?

Adding starter-security **does not automatically**:
- Create a users table in a database.
- Define the `EDITOR` role for the app.
- Connect to an OAuth2/OIDC provider or issue JWTs.
- Secure HTTPS connections if you have not configured TLS/ingress.
- Design per-record/per-tenant permissions or replace validation.
- Rate-limit all brute-force attempts, lock accounts, or control bots/rate limits.
- Allow arbitrary CORS origins.
- Make application state transactional or encrypt all session data.

The starter provides valuable security building blocks and defaults, but **production security policies must still be designed, tested, and operated by developers**.

## 7. A “Public URL” Does Not Automatically Grant Access

A common mistake is naming a controller `/public`, `/health`, or `/login-info` and assuming Spring Security automatically knows which endpoints should be open.

In the default security configuration, **all application endpoints require authentication**, except endpoints serving the authentication flow or specific auto-config rules. To allow guest access, the application must declare a rule such as `requestMatchers("/public").permitAll()`. Setting `permitAll` **does not remove security filters**; other applicable protections such as security headers and CSRF can still operate where appropriate.

Distinction:

```java
// Syntax illustration inside authorizeHttpRequests only:
.requestMatchers("/public").permitAll()
.requestMatchers("/admin/**").hasRole("ADMIN")
.anyRequest().authenticated()
```

Each matcher is an **authorization rule**, not an endpoint registration. A Spring MVC controller must still have the corresponding `@GetMapping`. Rules are evaluated in the appropriate declaration order; placing a broad match before a specific match can shadow an important rule. Do not paste the snippet above as a standalone Java file.

**Static resources:** files under `src/main/resources/static` are served by Boot's web infrastructure, but Spring Security may protect them by default. If CSS/JS/logos for the login page need to be public, permit the exact static paths using `PathRequest.toStaticResources().atCommonLocations()` or specific matchers. Do not use `web.ignoring()` indiscriminately just to make CSS load when `permitAll` is sufficient.

## 8. Replacing the Default Policy with the Application's SecurityFilterChain

Suppose the goals are:
- `GET /public` is open to guests.
- `GET /account` requires an authenticated user.
- `POST /notes` requires the `EDITOR` role **and** a valid CSRF token.
- Unlisted requests are denied.
- Login supports form login and HTTP Basic for the demo.
- Demo passwords are hashed with BCrypt instead of stored in plaintext in `UserDetailsService`.

Create a **new file** `src/main/java/com/example/securitydemo/SecurityConfig.java`:

```java
package com.example.securitydemo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class SecurityConfig {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/account").authenticated()
                .requestMatchers(HttpMethod.POST, "/notes").hasRole("EDITOR")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(Customizer.withDefaults());

        // Keep CSRF ON by default. Do not call csrf.disable().
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${demo.security.editor-password}") String rawPassword) {

        UserDetails editor = User.withUsername("editor")
                .password(encoder.encode(rawPassword))
                .roles("EDITOR")
                .build();

        return new InMemoryUserDetailsManager(editor);
    }
}
```

And add to **`application.properties`**:

```properties
# Local password for learning only; never keep this fallback in prod.
demo.security.editor-password=${DEMO_EDITOR_PASSWORD:local-only-change-me}
```

**Explanation:**

1. A `SecurityFilterChain` bean exists → Boot no longer applies the default web chain. **These rules are now the application's responsibility.**
2. A `UserDetailsService` bean exists → Boot no longer creates the default `user` account; the example uses `editor`.
3. `BCryptPasswordEncoder` hashes the password before placing it into `UserDetails`. The demo code reads a raw password from config for convenient local testing, not as a production identity storage architecture.
4. `hasRole("EDITOR")` checks the authority using the `ROLE_EDITOR` convention. `.roles("EDITOR")` on `UserDetails` creates the corresponding authority.
5. `anyRequest().denyAll()` is **fail-closed**: unlisted URLs will be rejected. In practice, if using form login and static/login/logout routes, you need to add rules and test according to requirements. This sample prioritizes illustrating API security.
6. `httpBasic(...)` allows testing with curl; `formLogin(...)` supports browser login. The authentication entry point determines 401 vs redirect depending on the request.
7. CSRF is not disabled. A POST with the right role but missing CSRF still fails.

**Important note on default login:** Spring Security has a mechanism that generates the `/login` page and processes login POSTs when `formLogin` is enabled; `anyRequest().denyAll()` should not be assumed to automatically block special endpoints managed by security filters. If customizing the login page, paths, or multiple filter chains, you must explicitly declare `permitAll` for the required login routes/assets and write browser integration tests. Custom application endpoints are not permitted automatically.

**Command to run after adding config:**

```bash
gradle bootRun
```

You can set `DEMO_EDITOR_PASSWORD` locally instead of using the fallback (for example by exporting it in your shell). In production, you must remove the fallback and use secrets/an identity provider.

### 8.1. Comparing Responses After Customization

**Public endpoint is now open:**

```bash
curl -i http://localhost:8080/public
```

Expected HTTP 200 and body:

```text
public content
```

**Account endpoint requires login:**

```bash
curl -i -H 'Accept: application/json' http://localhost:8080/account
```

Expected HTTP 401 in an API scenario without credentials.

**Authenticated as user editor:**

```bash
curl -i -u editor:local-only-change-me \
  -H 'Accept: application/json' http://localhost:8080/account
```

Expected HTTP 200:

```json
{"name":"editor"}
```

**Authorized POST but missing CSRF:**

```bash
curl -i -u editor:local-only-change-me \
  -H 'Content-Type: application/json' \
  -d '{"text":"hello"}' http://localhost:8080/notes
```

Expected HTTP 403 due to CSRF protection. When using the `csrf()` test helper, a request with the same body can return HTTP 201 and JSON:

```json
{"owner":"editor","text":"hello"}
```

The outputs above are based on the exact demo config without a custom global exception handler; headers/whitespace may vary. Do not write frontend JavaScript pretending to have a CSRF token: for real browsers, integrate the CSRF token repository/form/header per the Spring Security documentation.

## 9. Testing Security with MockMvc and spring-security-test

A common testing mistake: unit tests invoke the controller method directly and see 200, while production requests return 401/403 from the filter chain. To test **real HTTP behavior**, use `@SpringBootTest`, `@AutoConfigureMockMvc`, `spring-security-test`, and status/response assertions.

**Create `src/test/java/com/example/securitydemo/SecurityRulesTest.java`** after adding `SecurityConfig.java`:

```java
package com.example.securitydemo;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "demo.security.editor-password=only-for-test"
})
@AutoConfigureMockMvc
class SecurityRulesTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsOpen() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk());
    }

    @Test
    void accountRequiresAuthentication() throws Exception {
        mvc.perform(get("/account")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void correctBasicCredentialsCanReadAccount() throws Exception {
        mvc.perform(get("/account")
                        .with(httpBasic("editor", "only-for-test")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("editor"));
    }

    @Test
    void editorPostWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/notes")
                        .with(httpBasic("editor", "only-for-test"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"text\":\"hello\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void editorPostWithCsrfIsCreated() throws Exception {
        mvc.perform(post("/notes")
                        .with(httpBasic("editor", "only-for-test"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"text\":\"hello\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.owner").value("editor"));
    }

    @Test
    void authenticatedUserWithoutEditorRoleIsForbidden() throws Exception {
        mvc.perform(post("/notes")
                        .with(user("viewer").roles("VIEWER"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"text\":\"hello\"}"))
                .andExpect(status().isForbidden());
    }
}
```

Run:

```bash
gradle test
```

**Expected:** all 6 tests pass if code/config match. This is an **expected outcome, not verified execution output**. The tests are valuable because they separately check:
- Guests can access `/public`.
- Guests are rejected at `/account`.
- Users with valid credentials are authenticated.
- CSRF blocks unsafe requests even when the role is right.
- A valid CSRF token allows proceeding to the controller.
- An authenticated user lacking the role still gets 403.

`with(user("viewer").roles("VIEWER"))` from spring-security-test **mocks a principal in MockMvc**; it does not prove a viewer account exists in a database. To verify real user repositories/authentication, test separately with credentials/controlled integration mocks.

**Do not use `@WithMockUser`/`user()` to replace all end-to-end authentication tests**, because they skip testing password encoders, OAuth2 flows, bearer token validation, or session stores. They are very useful for isolating authorization rules from authentication.

## 10. Spring WebFlux Is Also Affected, but the Filter Mechanism Differs

If an application only has `spring-boot-starter-webflux` and adds `spring-boot-starter-security`, the reactive stack is also protected by default. However, you do not use Servlet `SecurityFilterChain`/`HttpSecurity` to protect a WebFlux server; the corresponding types are:

| Spring MVC / Servlet | Spring WebFlux / Reactive |
|---|---|
| `HttpServletRequest` | `ServerWebExchange` / `ServerHttpRequest` |
| `FilterChainProxy` and servlet filters | `WebFilterChainProxy` and `WebFilter` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `HttpSecurity` | `ServerHttpSecurity` |
| `UserDetailsService` | `ReactiveUserDetailsService` |
| `InMemoryUserDetailsManager` | `MapReactiveUserDetailsService` |
| `authorizeHttpRequests` | `authorizeExchange` |
| `requestMatchers` | `pathMatchers` / `matchers` |
| `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` |

### 10.1. Standalone WebFlux Example (Java 17+)

Create a **separate project** `webflux-security-demo` so you do not accidentally run MVC due to having starter-web on the same classpath.

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/resources/application.properties`:**

```properties
server.port=8081
demo.security.reactive-password=${DEMO_READER_PASSWORD:local-reader-only}
```

**`src/main/java/com/example/reactivesecurity/ReactiveSecurityApplication.java`:**

```java
package com.example.reactivesecurity;

import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class ReactiveSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityApplication.class, args);
    }
}

@RestController
class ReactiveController {

    @GetMapping("/public")
    Mono<Map<String, String>> publicEndpoint() {
        return Mono.just(Map.of("message", "public webflux"));
    }

    @GetMapping("/private")
    Mono<Map<String, String>> privateEndpoint() {
        return Mono.just(Map.of("message", "private webflux"));
    }
}

@Configuration(proxyBeanMethods = false)
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchange -> exchange
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/private").authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService users(
            PasswordEncoder encoder,
            @Value("${demo.security.reactive-password}") String password) {

        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode(password))
                .roles("READER")
                .build();

        return new MapReactiveUserDetailsService(reader);
    }
}
```

The minimal project structure consists of `build.gradle`, the Java file above, and `application.properties`. In the code, only `ReactiveSecurityApplication` is a top-level public class; other classes in the same package can all be component-scanned.

Run `gradle bootRun` in the WebFlux project. Test:

```bash
curl -i http://localhost:8081/public

curl -i -H 'Accept: application/json' \
  http://localhost:8081/private

curl -i -u reader:local-reader-only \
  http://localhost:8081/private
```

Corresponding expectations:
- HTTP 200, JSON `{"message":"public webflux"}`.
- HTTP 401 when no credentials are provided in an API context.
- HTTP 200, JSON `{"message":"private webflux"}` when reader is authenticated.

**Do not call `block()` in a WebFlux handler to obtain the authentication context.** For reactive pipelines, Spring Security uses the reactive context; if you need the principal in a handler, use a framework-supported `Principal`/`Mono<Principal>` argument or `ReactiveSecurityContextHolder` per contract.

In WebFlux, method security must also be configured reactively as required. Do not copy MVC's `SecurityFilterChain(HttpSecurity)` as-is and assume it secures a reactive server.

## 11. CSRF: Why Does a POST Fail Even When Logged In?

**Cross-Site Request Forgery (CSRF)** is a situation where a victim's browser automatically sends credentials such as a session cookie to another website due to an action triggered by an attacker. If the server only checks the cookie without verifying user intent, data-modifying requests can be exploited.

Spring Security **enables CSRF protection by default** for many web applications (both Servlet and WebFlux) on HTTP methods not considered safe. Typically GET/HEAD/OPTIONS/TRACE are considered safe; POST/PUT/PATCH/DELETE must include a valid CSRF token when this mechanism applies.

```text
Browser with session cookie
    │
    ├── GET /account                  → Read data (usually does not require CSRF)
    │
    └── POST /notes + cookie
            ├── valid token           → proceed to authorization/controller
            └── missing/invalid token → usually HTTP 403
```

**Common misconceptions:**
- `401 Unauthorized` usually means authentication is required/missing or credentials are invalid.
- `403 Forbidden` can be caused by a **missing role** or a **missing/invalid CSRF token**. You cannot tell the cause from status 403 alone.
- HTTP Basic with a browser **is not automatically exempt from CSRF** because browsers can automatically send cached credentials under appropriate mechanisms; decisions must be based on a threat model.
- **Stateless** does not automatically mean CSRF-safe if the browser still attaches credentials automatically.
- Using only a JWT in `Authorization: Bearer` attached by script/app with no ambient credentials sent automatically may have a different CSRF risk than cookie sessions, but this requires genuine analysis rather than disabling CSRF simply under a "REST API" label.
- CORS and CSRF are two different mechanisms. Allowing origins does not replace CSRF defense.
- GET should not modify state with business side effects; if GET performs a money transfer or deletes data, default CSRF exemption on safe methods will not save a broken design.

For Thymeleaf/MVC forms, render the CSRF token via the Spring Security/template engine integration; for SPAs, there must be an appropriate token-delivery contract when using cookie-based authentication. Never hardcode tokens into static HTML or the repo.

### 11.1. Should You Call `csrf.disable()`?

Do not treat this as a quick fix for every HTTP 403:

```java
// API example ONLY, NOT production advice:
http.csrf(csrf -> csrf.disable());
```

This snippet belongs to Servlet `HttpSecurity` only; WebFlux uses `ServerHttpSecurity` and a different API. Only consider disabling/ignoring CSRF on a **scope proven not to be vulnerable via browser ambient credentials**, such as certain truly stateless machine-to-machine bearer token APIs. If the same app has both browser sessions and API tokens, separate the chains/matchers and keep CSRF for the browser part.

Some webhook endpoints using their own HMAC signatures and no session cookies may need a different policy; verifying the request signature matters more than “disabling CSRF to make it work”. Every exception must be tested.

## 12. Sessions, Cookies, Authentication, and Logout

When form login is enabled, Spring Security can store the `SecurityContext` in the HTTP session to recognize the user on subsequent requests; the browser holds a session ID cookie such as `JSESSIONID` (depending on Servlet container/config). General flow:

```text
GET /account (anonymous)
     │
     └── Redirect to login
             │
          POST credentials + CSRF token
             │
             ▼
       Authentication success
             │
          SecurityContext
             │
       HttpSession / cookie session id
             │
GET /account + cookie → Authenticated by session
```

Distinguish between:
- **Authentication mechanism**: form login, HTTP Basic, JWT/Bearer/OAuth2.
- **Session policy**: use/create HTTP session when needed, limit sessions, or stateless.
- **Cookie flags**: `Secure`, `HttpOnly`, `SameSite` per requirements/deployment.
- **CSRF**: protect state-changing requests when credentials can be sent automatically by the browser.
- **Session fixation protection**: change/rotate session ID per policy on authentication.
- **Logout**: invalidate session, clear context, and/or revoke tokens per mechanism—not just hiding the logout button.

Do not assume HTTP Basic always uses a session or never uses a session across all configurations; other Spring Security components like request cache and security context persistence also play a role. If an API is truly stateless, design `SessionCreationPolicy.STATELESS` and token authentication properly (Servlet) and test that sessions are not created unexpectedly, but do not disable CSRF carelessly if auto-sent cookies are used.

**Warning:** a public endpoint does not mean data security is finished. `permitAll()` allows access without authentication, so do not return sensitive data at that URL; object/tenant authorization remains a business-layer responsibility.

## 13. Security Headers: Improved Defaults, but Not Every Safeguard

Spring Security can add several default HTTP response headers, for example:
- `X-Content-Type-Options: nosniff` prevents MIME sniffing in many browsers.
- Anti-clickjacking policies (`X-Frame-Options` per appropriate default).
- Cache-control headers preventing caching of sensitive content in default cases.
- `Strict-Transport-Security` (HSTS) is typically emitted only when the request is recognized as secure.
- Other headers depending on version/config.

**Do not assume every security header is enabled.** `Content-Security-Policy` (CSP), `Permissions-Policy`, third-party framing policies, TLS cipher suites, certificate rotation, rate limiting, or WAF usually require separate configuration.

If TLS terminates at a proxy, the application needs to recognize the public scheme properly via **forwarded headers from a trusted proxy**, or set security headers at the edge per policy. If you allow clients to spoof `X-Forwarded-Proto`, logic determining whether a request is secure can break. Never use unverified `Forwarded` headers to drive security-sensitive redirects or cookie flags.

You can inspect headers with `curl -i`, but verifying HTTPS, HSTS, and browser behavior requires testing **through real infrastructure** rather than MockMvc alone.

## 14. CORS: starter-security Does Not Automatically Open Cross-Origin Access

When a frontend at `https://app.example.test` calls a backend at `https://api.example.test`, the browser enforces **CORS**. Adding starter-security does not automatically “allow origins”, and security filters can affect **OPTIONS preflight** requests.

**CORS preflight** requests may not carry session cookies; if security requires authentication on them before CORS is processed, the browser reports a CORS failure even though the API works via curl. Register CORS at the appropriate layer and integrate it with Spring Security, for example on Servlet:

```java
// Configuration snippet inside SecurityFilterChain:
http.cors(Customizer.withDefaults());
```

To define allowed origins/methods/headers according to business policy, provide a `CorsConfigurationSource` bean:

```java
// Code snippet inside a @Configuration class (requires corresponding imports).
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of("https://app.example.test"));
    config.setAllowedMethods(List.of("GET", "POST"));
    config.setAllowedHeaders(List.of("Content-Type", "X-CSRF-TOKEN"));
    config.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/**", config);
    return source;
}
```

This snippet is **not a standalone Java file**; it requires importing `List`, `CorsConfiguration`, `CorsConfigurationSource`, and `UrlBasedCorsConfigurationSource` from Spring Web. It is a conceptual example; production requires carefully evaluating methods, headers, credentials, max-age caching, and CSRF token delivery. Do not combine `allowedOrigins("*")` with credentials carelessly. Do not blindly reflect `Origin` into `Access-Control-Allow-Origin` without an allowlist.

**CORS does not replace authentication/authorization.** Any non-browser client can send HTTP requests even if not on the CORS allowlist; the server must still authenticate and authorize via Spring Security.

## 15. Static Resources, Error Pages, and Actuator

### 15.1. Static Assets

When Boot serves `/css/site.css` or `/js/app.js` from `src/main/resources/static`, those URLs can still pass through the security chain. If you need to serve a login page before authentication, the corresponding CSS/JS/logo should be deliberately marked **`permitAll`**.

With Spring Boot MVC, a suitable matcher when Boot dependencies are enabled:

```java
// Snippet inside authorizeHttpRequests(...):
.requestMatchers(
    PathRequest.toStaticResources().atCommonLocations()
).permitAll()
```

This `PathRequest` belongs to `org.springframework.boot.autoconfigure.security.servlet.PathRequest` in Boot 3.3. Do not “ignore all security” with `web.ignoring()` just to display images if `permitAll` works: ignoring can prevent security filters/headers from applying to those responses.

### 15.2. Error Pages and `/error`

If a handler throws an exception, the error dispatch can go through security mechanisms. Boot 3.3 describes applications as protected by default, **including `/error`**. When creating a custom `anyRequest().denyAll()` chain or multiple chains, test:
- Does a nonexistent endpoint (404) display 404 properly?
- Does a failing endpoint (500) accidentally return 401/403 instead of the original error?
- Does the error page leak stack traces/PII?
- Does an unauthenticated user enter a redirect loop between the error and `/login`?

You do not need to expose detailed errors publicly. You can configure an error dispatch policy with an appropriate matcher to preserve correct status codes without leaking debug content to users.

### 15.3. Actuator: Special Considerations When Creating a Custom Chain

If `spring-boot-starter-actuator` is added, Boot provides management endpoints such as `/actuator/health`, `/actuator/metrics`, `/actuator/env`, etc. However:
- Not every endpoint is **exposed** over HTTP. Per Boot 3.3, typically only health is exposed by default.
- When Spring Security is present and there is **no custom SecurityFilterChain**, Boot auto-security typically permits health and secures other exposed Actuator endpoints.
- When you **create a custom SecurityFilterChain**, Boot backs off from auto-security; **you must control Actuator access** in your chain (or a separate chain).
- Exposure and authorization are **two different layers**: `management.endpoints.web.exposure.include=*` does not automatically make those endpoints safely public.

One approach to writing rules in an app with Actuator is using `EndpointRequest` instead of hardcoding `/actuator/**`:

```java
// Illustration inside authorizeHttpRequests(...) with actuator on classpath:
.requestMatchers(EndpointRequest.to("health")).permitAll()
.requestMatchers(EndpointRequest.toAnyEndpoint()).hasRole("OPS")
.anyRequest().authenticated()
```

In Boot 3.3 MVC, `EndpointRequest` comes from `org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest`. The code above is a fragment; do not paste it directly into the example project without actuator and the OPS role. If the management server uses a separate port/context, the design needs additional testing of the corresponding security chains.

## 16. Method-Level Security Is Not Automatically Enabled by the Starter Alone

URL-based authorization is not always enough. A service method may be called by multiple controllers, schedulers, or message consumers. Spring Security provides method-level authorization, but **it must be explicitly enabled**.

With Spring MVC/Servlet:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {}
```

Then:

```java
@Service
class ReportService {
    @PreAuthorize("hasRole('ADMIN')")
    String exportSensitiveReport() {
        return "report content";
    }
}
```

The snippets above are **class fragments**; they require `@Configuration`, `@EnableMethodSecurity`, `@Service`, `@PreAuthorize` imports and an appropriate package. When properly configured and called through a Spring bean/proxy, authorization can be checked before execution. **Self-invocation** calling a protected method from another method on the same object can bypass proxy-based interception; test the actual invocation architecture.

For reactive method security, use `@EnableReactiveMethodSecurity` and the corresponding reactive contract; do not unconditionally copy a blocking service onto the Netty event loop. Pay attention to `ReactiveSecurityContextHolder` and context propagation across reactive operators.

Having starter-security alone **does not mean every method is automatically protected** or that `@PreAuthorize` annotations work without proper enablement/configuration.

## 17. Multiple SecurityFilterChains: Avoiding Unprotected Paths

A hybrid application might need:
- `/api/**` using Bearer tokens, stateless.
- `/web/**` using form login/session/CSRF.
- `/actuator/**` restricted to the OPS role or an internal network.

In MVC, you can create multiple `SecurityFilterChain` beans with `@Order` and `http.securityMatcher(...)`. **`FilterChainProxy` selects only the first chain matching the request**. `authorizeHttpRequests().requestMatchers(...)` **does not select the chain**; it selects access rules **inside the chosen chain**.

```text
GET /api/orders
    │
    ▼
SecurityFilterChain matching:
    1. /api/** ? YES → API chain
    2. /web/** ? not evaluated
    3. catch-all ? not evaluated
    │
    ▼
Authentication + authorization of the API chain
```

**Major risk:** if you only create one chain with `securityMatcher("/api/**")` and have no catch-all, URLs outside `/api/**` may **not go through any security chain**. Because Spring Boot sees the `SecurityFilterChain` bean you declared, Boot's default chain no longer protects the rest automatically. You must design a fallback chain for all URLs within the app's scope and test negative cases.

Similarly in WebFlux: `SecurityWebFilterChain` has `securityMatcher` and selection ordering. Never place a broad `permitAll` rule before a restricted rule expecting the restricted rule to be evaluated later.

## 18. Authentication Schemes and Adding Other Starters

`spring-boot-starter-security` solves the security foundation, but production may require:

| Use case | Commonly used components | What must be designed |
|---|---|---|
| Traditional username/password website login | Form login, user store/identity provider, session/CSRF | Password hashing, session fixation, logout, rate limiting |
| Machine-to-machine API with JWT | OAuth2 Resource Server + JWT decoder/issuer validation | Signature, issuer, audience, expiry, authorities mapping |
| Social/enterprise login | OAuth2 Client / OpenID Connect | Authorization code flow, redirect URI, scopes, session/security context |
| SAML login | SAML2 service provider support | Metadata/cert rotation, assertions, recipient/audience |
| Backend-to-backend Basic | HTTP Basic with TLS and credential management | Secret rotation, credential caching, brute-force prevention |
| Reverse proxy auth | Trusted identity headers or token forwarding | Proxy trust boundary, signed identity, never trust client-sent headers |

Do not turn on `csrf.disable()` just because OAuth2 is present. Browser flows using cookies/sessions have a different threat model than bearer-only APIs. Do not treat `@PreAuthorize("hasRole('ADMIN')")` as a substitute for object-level authorization (e.g., whether an ADMIN of tenant A may view tenant B's data).

A `UserDetailsService` only describes how to look up a user/authorities by username in certain authentication providers. It does not automatically implement MFA, account lockout, identity proofing, email confirmation, or token issuance. Those requirements need separate mechanisms.

## 19. Troubleshooting After Adding spring-boot-starter-security

| Symptom | Common cause | What to check |
|---|---|---|
| Previously `/hello` returned 200, now returns 401 | Starter enabled default authentication requirement | Create a SecurityFilterChain for desired URL policy; do not remove starter |
| Browser always redirects to `/login` | Form login entry point selected for unauthenticated HTML client | Check `Accept`, session/authentication, and login routes |
| curl works with Basic, but POST gets 403 | Missing/invalid CSRF token or insufficient role | Check security logs; test `with(csrf())` and authorities |
| Generated user still exists after custom `SecurityFilterChain` | Default user config was not replaced by an authentication bean | Declare real UserDetailsService/provider or auth manager |
| Login page CSS/JS fail to load | Static assets still require login in security chain | Permit the exact static resource paths |
| `@PreAuthorize` does not work | Method security not enabled, or self-invocation | `@EnableMethodSecurity`, check bean/proxy |
| Spring Boot WebFlux app ignores `SecurityFilterChain(HttpSecurity)` | Confused Servlet security with reactive security | Use `SecurityWebFilterChain(ServerHttpSecurity)` |
| CORS preflight OPTIONS fails | CORS not processed before authorization or origin not allowlisted | Enable CORS integration and origin/header policy |
| Redirect to login instead of JSON 401 | Content negotiation/entry point suited for HTML | Check Accept header, custom AuthenticationEntryPoint if API-only |
| Login succeeds then session is lost | Cookie flags/path, session store, or proxy/TLS config | Trace session ID, security context persistence, and cookie policy |
| 404/500 turned into 401/403 | Error dispatch also goes through security | Test `/error`/dispatcher handling; configure deliberate error policy |
| Actuator metrics become public after adding custom chain | Boot auto-security backed off, app rule too broad | Use EndpointRequest and test management access |
| Password from log does not work | App uses custom UserDetailsService or password changed on restart | Check beans/auto-config and active profile |
| 403 despite having ROLE_EDITOR in database | Authority mapping / hasRole vs hasAuthority mismatch | Check `ROLE_` prefix, loaded authorities, and selected chain |
| User is “authenticated” yet reads wrong tenant data | Only URL/role check exists, missing object-level authorization | Check ownership/tenant in service/repository |

**Controlled debugging:** in development, you can raise logging for `org.springframework.security` to see chains/matchers/denials, e.g., `logging.level.org.springframework.security=DEBUG`. Do not enable DEBUG/TRACE broadly in production: URL/authentication event details can be sensitive and log volume high. Never log passwords, tokens, raw session IDs, or security contexts containing PII.

## 20. Checklist for Adding the Security Starter to an Existing Application

1. **Identify the stack:** MVC/Servlet or WebFlux/Reactive; distinguish `SecurityFilterChain` from `SecurityWebFilterChain`.
2. **Inventory endpoints:** public, authenticated, role-restricted, admin, actuator, static, login, logout, error, and management port.
3. **Design authentication:** real user store/identity provider, password encoder, MFA/credential rotation where needed; remove dev generated passwords before production.
4. **Define authorization:** at minimum `anyRequest().authenticated()` or an appropriate deny-all strategy; do not forget a default/catch-all when using multiple chains.
5. **Keep CSRF aligned with threat model:** browser cookies/sessions need protection; do not disable just to get POST 200.
6. **Review CORS:** allowed origins/methods/credentials, preflight integration; CORS does not replace auth.
7. **Review sessions/cookies:** session fixation, secure/httpOnly/sameSite, logout/invalidation, and proxy/TLS.
8. **Test 401, 403, 302, 200, 201:** guest, user, wrong role, missing/valid CSRF, login/logout, and static resources.
9. **Test Actuator and errors:** prevent exposing management endpoints or turning every 404 into an unintended login redirect.
10. **Enable method security if needed:** verify `@PreAuthorize` actually runs and has no self-invocation bypass.
11. **Security headers/TLS:** verify HSTS/HTTPS in reality, add CSP and configure trusted proxies if needed.
12. **Observe and verify rollout:** configure audit metrics, test behind gateway after deploy, verify no chain bypass paths exist.
13. **Do not overuse permitAll/ignoring:** open only truly public resources; do not replace all rules with `web.ignoring()`.
14. **Keep dependencies updated:** monitor Spring Boot/Spring Security advisories and apply patches regularly.

## 21. Self-Check Questions

**Q1:** Does adding starter-security automatically make `/public` public?  
**Answer:** No. Without custom configuration, application endpoints generally require authentication. To open one, you must explicitly permit it.

**Q2:** Why does curl GET work after logging in while POST still returns 403?  
**Answer:** CSRF protection checks unsafe HTTP methods; it could also be authorization. You must distinguish role denial from a missing/invalid CSRF token.

**Q3:** If a custom `SecurityFilterChain` exists, does the default user still exist?  
**Answer:** It might. The default web chain and default authentication user auto-config have separate back-off conditions. To replace the user, declare an appropriate authentication bean.

**Q4:** Is using `SecurityFilterChain(HttpSecurity)` in WebFlux right?  
**Answer:** Not for a reactive server. WebFlux uses `SecurityWebFilterChain(ServerHttpSecurity)` and `ReactiveUserDetailsService` where needed.

**Q5:** Without cookies, using only client-attached Bearer tokens, can CSRF be disabled?  
**Answer:** It can be considered in pure token APIs with no ambient browser credentials, but you must evaluate the threat model, client types, and all enabled auth schemes; never disable automatically based on the name API.

**Q6:** If there are two chains and `securityMatcher("/api/**")` is the only chain, is `/admin/**` protected?  
**Answer:** You cannot assume so. Unmatched paths may not be processed by Spring Security because Boot's default chain has backed off; a catch-all chain is required.

**Q7:** When creating a custom chain, who controls Actuator?  
**Answer:** The application must explicitly declare policy for Actuator/management endpoints because Boot auto-security backs off when a custom chain exists, and exposure must also be checked.

## 22. Official References

1. Spring Boot 3.3.13 — **Spring Security**: default user/password, default web protection, MVC/WebFlux, and how to override: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
2. Spring Boot 3.3.13 — **Actuator Endpoints**: exposure and security when creating a custom SecurityFilterChain: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
3. Spring Security — **Architecture**: DelegatingFilterProxy, FilterChainProxy, and SecurityFilterChain: https://docs.spring.io/spring-security/reference/servlet/architecture.html
4. Spring Security — **Authorize HttpServletRequests**: authorizeHttpRequests and requestMatchers: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
5. Spring Security — **CSRF**: when tokens are needed, cookie/browser threat model: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
6. Spring Security — **MockMvc with CSRF**: using `csrf()` in tests: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
7. Spring Security — **WebFlux Security**: ServerHttpSecurity, WebFilter, and SecurityWebFilterChain: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html

**Summary:** `spring-boot-starter-security` introduces authentication/authorization and web security defaults **as soon as it is added to the classpath**. The effects show up in 401/302 responses, role-based 403s, CSRF 403s, login/logout, sessions, headers, Actuator, and tests. To move to production, **properly define SecurityFilterChain/SecurityWebFilterChain**, provide users/identities from an appropriate source, keep CSRF aligned with your threat model, ensure no URL falls outside security policy, and thoroughly test before and after adding the starter.