# Protecting an API with HTTP Basic and Explaining the Chosen CSRF Policy

> **Capstone practical exercise — Spring Security fundamentals.** Build a Spring Boot REST API requiring HTTP Basic, distinguish an unauthenticated caller from an authenticated caller lacking permission, and explain **why the CSRF choice in this exercise fits a specific client type**. The exercise uses Spring Boot Servlet, Spring Security 6.x, Java 17+, HTTP clients such as `curl`, and JUnit/MockMvc.

## 1. Problem Statement, Requirements, and Security Scope

We build a **Notes API** service intended solely for **scripts and backend services**, with no browser login page, no session-cookie authentication mechanism, and no write API for users logged in directly through a browser.

The API has two operations:

| Method and URL | Behavior | Access policy |
| --- | --- | --- |
| `GET /api/notes` | List notes | `ROLE_READER` or `ROLE_EDITOR` |
| `POST /api/notes` | Create a JSON note | Only `ROLE_EDITOR` |
| Any other path/method | Outside the published API | Deny by default |

Two test accounts: `reader` has read permission and `editor` has read/write permissions. Passwords are **hashed with BCrypt** inside an in-memory `UserDetailsService` at application startup. The password values shown in the exercise are strictly for local testing; real systems must use a proper user/secret store and never hardcode secrets.

**Expected outcomes:**

- Missing or invalid credentials → `401 Unauthorized` (HTTP Basic usually includes `WWW-Authenticate`).
- Valid login but insufficient permission for the operation → `403 Forbidden`.
- `reader` lists notes successfully, cannot create notes.
- `editor` reads and creates notes successfully.
- Authenticated POST requests from scripts **do not require a CSRF token** because this service is designed **exclusively for non-browser clients**. This is a threat-model decision, not a universal rule that "HTTP Basic always disables CSRF."

## 2. How Does HTTP Basic Work?

HTTP Basic is a mechanism for sending credentials in HTTP. The client attaches a header:

```http
Authorization: Basic <base64(username:password)>
```

`Base64` is only encoding for transport, **not security encryption**. Anyone reading the header without TLS protection can recover the username/password. Therefore, **HTTPS is mandatory in real environments**. HTTP over `localhost` in the example below is for local testing only.

Overall flow:

```text
Client (curl/service)
  |
  | Authorization: Basic ...
  v
Spring SecurityFilterChain
  |
  +-- BasicAuthenticationFilter
  |       -> AuthenticationManager / AuthenticationProvider
  |       -> UserDetailsService
  |       -> PasswordEncoder.matches(...)
  |       -> creates valid Authentication on success
  |
  +-- AuthorizationFilter
  |       -> checks ROLE_READER / ROLE_EDITOR per request
  v
NotesController or 401 / 403
```

On an unauthenticated request to a protected endpoint, `BasicAuthenticationEntryPoint` can prompt the client for credentials via a `401` response with a `WWW-Authenticate: Basic ...` header. For valid requests, Spring Security places `Authentication` into `SecurityContext` **for request processing** so the authorization layer can make access decisions.

HTTP Basic does not by itself provide an authorization mechanism: **authentication** via username/password and **authorization** via roles/authorities are two separate steps. In Spring Security, `roles("READER")` creates the `ROLE_READER` authority; `hasRole("READER")` checks that authority. If using `hasAuthority("ROLE_READER")`, you must write the full name.

**Limitations of HTTP Basic:** credentials are typically sent on every request; there is no "server-side logout" equivalent to invalidating a session. Basic may be suitable for exercises or tightly controlled internal calls, but for broader systems consider short-lived tokens, OAuth2/mTLS, or other appropriate mechanisms.

## 3. Choosing the CSRF Policy from the Threat Model

**CSRF (Cross-Site Request Forgery)** occurs when an attacker causes an authenticated browser to send an unwanted request to another website/API. The risk specifically involves **credentials that browsers attach automatically to requests**, such as session cookies or **cached HTTP Basic credentials remembered by the browser**.

CSRF is distinct from authentication: the server may recognize the request as coming from "the right account," yet it is **not an action the user actually intended**. A CSRF token is a value required on state-changing requests in a place the browser will not automatically supply in a way attackers can exploit.

### Decision in this exercise

We choose:

- **Clients are strictly scripts/CLI/services** that explicitly set the `Authorization` header; there is no browser login session, no browser-initiated requests, and no reliance on automatic cookies.
- Use `SessionCreationPolicy.STATELESS`: Spring Security neither creates nor uses an `HttpSession` to store `SecurityContext` across requests.
- **Disable CSRF checks for this dedicated API service** via `csrf(csrf -> csrf.disable())` so `curl`/backends can POST when authenticated and authorized without a CSRF token endpoint.
- Keep **authentication, authorization, HTTPS, strong passwords, input validation, and proper logging**. Disabling CSRF does not mean disabling other protections.

**Mandatory condition:** This exercise applies only when the service genuinely **is not used as a browser-facing API with ambient credentials**. HTTP Basic credentials can be re-sent automatically by browsers after a user has logged in. Consequently, **being stateless does not make browser-based Basic auth immune to CSRF**.

| Client / credential mechanism | Can browsers attach credentials automatically? | CSRF approach |
| --- | --- | --- |
| CLI/service calling API with Basic explicitly sent by code | No browser in the flow | CSRF may be disabled if API usage is strictly scoped as designed |
| Web browser with cached HTTP Basic credentials | **Yes, possible** | **Keep CSRF protection** on state-changing requests; consider switching auth schemes |
| Browser logged in with session cookies | **Yes** | Keep CSRF protection (Spring Security default) |
| SPA using bearer tokens explicitly attached by JS with no cookies/ambient auth | Normally not attached automatically like cookies | Evaluate per actual architecture; still protect XSS, tokens, and CORS |

**Do not use flawed arguments:** "The API returns JSON so it doesn't need CSRF," "CORS is enabled so CSRF isn't possible," "There is no session so there is no CSRF," or "HTTP Basic never has CSRF." CORS mainly governs cross-origin browser reads/requests and is not a mechanism for confirming user intent on state-changing requests.

### When the problem changes

If users start calling the API from a browser, or the backend adds session/cookie credentials, you must **re-evaluate the configuration**. Either re-enable `csrf(Customizer.withDefaults())` and design CSRF token issuance/submission for POST/PUT/PATCH/DELETE requests, or adopt an appropriate login model. If an application serves both browser UI and machine APIs, you usually need **clearly partitioned `SecurityFilterChain`s** rather than disabling CSRF application-wide.

## 4. Organizing the Example and Dependencies

The example is a complete **Spring Boot Servlet application** with core Java classes. Place the three classes in a Java 17+ Spring Boot project using Spring Security 6.x:

```text
src/main/java/com/example/basicapi/
  BasicApiApplication.java
  ApiSecurityConfig.java
  NotesController.java

src/test/java/com/example/basicapi/
  BasicApiSecurityTest.java
```

In a Gradle Groovy project that already has the Spring Boot plugin and dependency management, add these dependencies:

```groovy
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

Use the Spring Boot/Java toolchain versions chosen by your project; for a fresh project, initialize via Spring Initializr and add the classes below. If your project already declares these dependencies or the test task config, do not duplicate them.

### `BasicApiApplication.java`

```java
package com.example.basicapi;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BasicApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(BasicApiApplication.class, args);
    }
}
```

This is the entry point. Other classes in package `com.example.basicapi` will be discovered by Spring Boot component scanning.

## 5. Configuring SecurityFilterChain, HTTP Basic, and CSRF

### `ApiSecurityConfig.java`

```java
package com.example.basicapi;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            // Accepts non-browser clients only; see threat model in section 3.
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .requestCache(cache -> cache.disable())
            .formLogin(form -> form.disable())
            .logout(logout -> logout.disable())
            .httpBasic(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/error").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/notes")
                    .hasAnyRole("READER", "EDITOR")
                .requestMatchers(HttpMethod.POST, "/api/notes")
                    .hasRole("EDITOR")
                .anyRequest().denyAll()
            )
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        // Demo passwords for local learning only.
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo-pass"))
            .roles("READER")
            .build();

        UserDetails editor = User.withUsername("editor")
            .password(encoder.encode("editor-demo-pass"))
            .roles("READER", "EDITOR")
            .build();

        return new InMemoryUserDetailsManager(reader, editor);
    }
}
```

**Explaining each decision:**

1. **`httpBasic(Customizer.withDefaults())`:** enables `BasicAuthenticationFilter` to read `Authorization: Basic ...`. Spring Security matches credentials against configured users.
2. **BCrypt `PasswordEncoder`:** does not store or compare plaintext passwords. Test passwords in source are strictly for repeatable practice. In production, load user data from a real identity store and keep secrets out of Git.
3. **`GET` and `POST` have separate rules:** holders of `ROLE_READER` or `ROLE_EDITOR` can read; only `ROLE_EDITOR` can create. `anyRequest().denyAll()` blocks out-of-scope methods/URLs instead of inadvertently permitting them.
4. **`STATELESS`:** does not store `SecurityContext` in `HttpSession`; each request is responsible for supplying credentials. This setting **does not automatically protect against CSRF**.
5. **`csrf(...disable())`:** appropriate solely because **the entire example application** is an API for non-browser clients. Never copy this line blindly into a browser/session application without re-evaluating.
6. **Disabling form login, logout, and request cache:** avoids unnecessary redirects/form flows for a CLI API. Server-side logout does not clear browser-cached HTTP Basic credentials anyway.
7. **`/error` permitted:** lets Spring Boot render API error responses; this does not expose application data. In production, ensure error responses do not leak stack traces or secrets.

> **Scope note:** This `SecurityFilterChain` matches the entire example application. If a larger app has both a browser/session UI and an API, restrict the API chain's matcher and create a separate chain protecting the UI. Never disable CSRF system-wide just because one non-browser API exists.

## 6. Creating a State-Mutating REST Controller

### `NotesController.java`

```java
package com.example.basicapi;

import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/notes")
public class NotesController {

    private final AtomicLong nextId = new AtomicLong();
    private final ConcurrentMap<Long, Note> notes = new ConcurrentHashMap<>();

    @GetMapping
    public List<Note> list() {
        return notes.values().stream()
            .sorted(Comparator.comparingLong(Note::id))
            .toList();
    }

    @PostMapping
    public ResponseEntity<Note> create(@RequestBody CreateNoteRequest body) {
        if (body.text() == null || body.text().isBlank()) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "text must not be blank"
            );
        }

        Note created = new Note(nextId.incrementAndGet(), body.text().trim());
        notes.put(created.id(), created);
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }

    public record CreateNoteRequest(String text) {}
    public record Note(long id, String text) {}
}
```

The controller has a **read-only `GET`** and a **data-creating `POST`**. Having endpoints with different side effects requires proving the intentionally chosen CSRF policy. Data stays only in RAM and disappears on restart; this is intentional for a learning example, not a production storage system.

`@RequestBody` requires the client to send properly formatted JSON; JSON itself does not stop CSRF. The controller checks `text` to reject blank values; real applications need comprehensive validation, length limits, note ownership checks, and consistent error handling.

## 7. Running and Testing with an HTTP Client

Start the application from the project directory containing the Gradle wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell, use `.\gradlew.bat bootRun`. Once running on `http://localhost:8080`, open another terminal and try the commands below. On Windows PowerShell, use `curl.exe` instead of `curl` if `curl` is a PowerShell alias.

### 7.1. Unauthenticated: 401

```bash
curl -i http://localhost:8080/api/notes
```

Expected status **`HTTP/1.1 401`** and an HTTP Basic challenge header, such as `WWW-Authenticate: Basic realm="Realm"`. Exact realm/header values depend on configuration, but the status must be 401 because the request lacks credentials.

### 7.2. Reader calling GET: 200

```bash
curl -i -u reader:reader-demo-pass http://localhost:8080/api/notes
```

Expected **`200 OK`**. With a freshly started app and no data added yet, the JSON body is:

```json
[]
```

`curl -u` builds the Basic header from username/password. In the localhost example, credentials are inline for convenience; in real environments, avoid putting passwords on the command line where shell history or process listings might expose them. Use `curl -u reader` to be prompted, or pull secrets from a secure store.

### 7.3. Reader calling POST: 403

```bash
curl -i -u reader:reader-demo-pass \
  -H 'Content-Type: application/json' \
  -d '{"text":"First note"}' \
  http://localhost:8080/api/notes
```

Expected **`403 Forbidden`**. Credentials are valid, but `reader` lacks `ROLE_EDITOR`. The controller creates no note. This is evidence separating **successful authentication** from **denied authorization**.

### 7.4. Editor calling POST: 201 without a CSRF token

```bash
curl -i -u editor:editor-demo-pass \
  -H 'Content-Type: application/json' \
  -d '{"text":"First note"}' \
  http://localhost:8080/api/notes
```

Expected **`201 Created`**. If this is the first note since startup:

```json
{"id":1,"text":"First note"}
```

No `X-CSRF-TOKEN` header or `_csrf` parameter is in the command. The request **is allowed because the caller is authenticated, holds the EDITOR role, and CSRF was deliberately disabled for this non-browser API**. A successful POST does not prove that disabling CSRF is safe for browsers.

Call GET again as `reader`:

```bash
curl -i -u reader:reader-demo-pass http://localhost:8080/api/notes
```

Expected **`200 OK`**, with the newly created note in the body. If prior creation requests ran, the ID and note count will differ.

### 7.5. Wrong password: 401

```bash
curl -i -u reader:wrong-password http://localhost:8080/api/notes
```

Expected **`401 Unauthorized`**, not 403. The client has not authenticated successfully, so execution never reaches role checks as a valid user.

**Note when running in PowerShell:** multi-line Bash commands use `\` for line continuation. In PowerShell, run the same command on **one line** or use PowerShell's line-continuation syntax; do not leave trailing `\` characters as in Bash.

## 8. Automated Testing with JUnit and MockMvc

Alongside `curl`, HTTP-layer security tests catch unintended policy regressions. The `spring-security-test` dependency adds the `httpBasic(...)` helper; the tests below traverse the actual Spring Security filter chain.

### `BasicApiSecurityTest.java`

```java
package com.example.basicapi;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
    .jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
    .status;

@SpringBootTest
@AutoConfigureMockMvc
class BasicApiSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void missingCredentialsReturns401() throws Exception {
        mvc.perform(get("/api/notes"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readerCanRead() throws Exception {
        mvc.perform(get("/api/notes")
                .with(httpBasic("reader", "reader-demo-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void incorrectPasswordReturns401() throws Exception {
        mvc.perform(get("/api/notes")
                .with(httpBasic("reader", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readerCannotCreate() throws Exception {
        mvc.perform(post("/api/notes")
                .with(httpBasic("reader", "reader-demo-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"Denied\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorCanCreateWithoutCsrfToken() throws Exception {
        mvc.perform(post("/api/notes")
                .with(httpBasic("editor", "editor-demo-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"Allowed\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.text").value("Allowed"));
    }
}
```

Run from the directory containing the Gradle wrapper:

```bash
./gradlew test
```

The tests are independent of execution order: no test assumes a specific `id` or an empty list after another test creates a note. On success, Gradle finishes with **BUILD SUCCESSFUL** (duration and task counts may vary). There is no fixed stdout string to memorize.

**Significance of the final test:** editor POST succeeds **without attaching a CSRF token**, proving the policy is active. It is also an important reminder: if the API later allows browser usage with HTTP Basic, this test must be revisited under the new threat model rather than assuming the old configuration stays safe.

## 9. If the Client Is a Browser: The CSRF Decision Must Change

Suppose a user opens the application in a browser and the browser caches HTTP Basic credentials. A malicious site could trick the browser into sending requests to the application's endpoints. Because the browser **can automatically attach remembered Basic credentials**, the server could authenticate that request as the real user.

Therefore, for browser-facing applications:

1. **Do not copy** this exercise's `csrf(csrf -> csrf.disable())`.
2. Keep Spring Security CSRF protection (the default), e.g. `csrf(Customizer.withDefaults())`, and design how the frontend retrieves and submits the token on state-changing operations.
3. With CSRF enabled, a `POST` with valid credentials/role but **without a valid token** is typically rejected with **403** by the CSRF filter; exact outcomes depend on filter ordering and request handling.
4. For standard web apps, consider `formLogin`/OIDC with protected session cookies, CSRF tokens, and proper cookie attributes. If an API serves both scripts and browsers, define separate, clearly scoped security chains and test each chain.
5. CORS, `SameSite`, JSON content types, and marking an application "stateless" are only supplementary factors—none replace CSRF protection when browsers automatically attach credentials.

Illustrative **directional change for a browser application** (do not plug alongside the API config above):

```java
// Illustrative snippet for a browser-facing application configuration:
// Replace disabling CSRF with:
.csrf(Customizer.withDefaults())
// And design the frontend to receive and send a valid token for POST, PUT, PATCH, DELETE.
```

The token must be supplied in a way browsers do not attach automatically when another site initiates a request, such as an `X-CSRF-TOKEN` header sent by the legitimate UI. Session security, login/logout, XSS prevention, and cookie attributes must still be designed holistically.

## 10. Checklist Beyond the Learning Environment

| Concern | What the example did | What real usage requires |
| --- | --- | --- |
| Password | BCrypt with in-memory demo users | Database/IdP/secret manager, password policies, and account lifecycle |
| Transport | `http://localhost` for study | End-to-end HTTPS; proper proxy/TLS configuration |
| Authorization | Endpoint-level roles | Data-level owner/tenant checks in service/domain layers |
| CSRF | Disabled strictly for non-browser only | Verify actual clients; enable CSRF whenever browsers use ambient credentials |
| Session | Stateless SecurityContext | Ensure no other component implicitly creates cookies/sessions |
| Abuse protection | No rate limiting | Rate limiting, brute-force monitoring, auditing, and appropriate lockouts |
| Credentials | Demo values in source/commands | No hardcoding, never log Authorization headers |
| API contract | Simple GET/POST and JSON | Validation, body size limits, error contract, idempotency where needed |
| Operability | In-memory store, non-persistent | Persistence, safe logging, metrics, and integration testing |

Never use HTTP Basic over plain HTTP outside localhost; Base64 provides zero confidentiality. Avoid storing real system users/passwords in repositories or CI output. If behind a reverse proxy or API gateway, verify it does not log the `Authorization` header.

## 11. Self-Assessment and Troubleshooting

**Review questions:**

1. Why does an unauthenticated request return 401, while `reader` creating a note returns 403?
2. Why does `roles("EDITOR")` match `hasRole("EDITOR")` even though the actual authority is `ROLE_EDITOR`?
3. Which mechanism processes the Basic header and which decides GET/POST permissions?
4. Why is `SessionCreationPolicy.STATELESS` insufficient to conclude "there is no CSRF" when the client is a browser?
5. What exact assumption allowed us to disable CSRF in this exercise? What must change if the API gets called from a web app?
6. Why do CORS or `Content-Type: application/json` not replace CSRF tokens?
7. If you need instant credential revocation or per-client scoped permissions, is HTTP Basic still an appropriate choice?

**Troubleshooting hints for failing tests:**

- **Always 401:** check username/password, user store, whether the Basic header is sent or stripped by a gateway, and HTTPS configuration.
- **403 despite right password:** check `ROLE_...`/`hasRole`, HTTP method/URL matchers, and the account's authorities.
- **POST 403 even with EDITOR:** another chain might enable CSRF, the matcher/role doesn't match, or the active config differs from the exercise. Inspect filters and responses instead of reflexively disabling CSRF.
- **Redirect to login page:** form login may still be enabled or the request hits a different chain; this exercise's API must return HTTP status codes directly.
- **POST returns 400/415:** check the JSON body and `Content-Type: application/json`; these are distinct from 401/403.
- **GET doesn't show notes:** confirm POST returned 201, the app wasn't restarted, and you are hitting the same instance; this example stores data in RAM only.

**Completion criteria:** Runnable code in Spring Boot Servlet; all five key security tests pass; evidence of 401, 403, 200, and 201 requests; ability to explain the Basic flow; and a documented decision explaining **"disabling CSRF for a non-browser-only API" together with the boundary "Basic used in browsers still carries CSRF risk."**

## 12. Official Documentation for Deeper Study

- [Spring Security — HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html): challenge/response, `BasicAuthenticationFilter`, and `httpBasic` configuration.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): protection rules, CSRF tokens, and browser client considerations.
- [Spring Security — CSRF Overview](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html): why stateless apps and browser Basic auth can still be vulnerable to CSRF.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): request matching, `hasRole`, `denyAll`.
- [Spring Security — Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): MockMvc, authentication, and authorization tests.

**Key takeaway:** HTTP Basic handles credential verification on each request, while Spring Security authorization decides whether an endpoint may be invoked. **CSRF policy must be driven by client type and how credentials are transmitted**, not by protocol names, statelessness, or JSON formatting.
