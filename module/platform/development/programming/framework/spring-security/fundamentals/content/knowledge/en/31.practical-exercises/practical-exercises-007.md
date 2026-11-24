# Observing, Reproducing, and Distinguishing 401, 403, CSRF, and CORS Errors

> **Capstone practice — Spring Security fundamentals.** This exercise uses a Spring Boot Servlet REST API, two accounts with different permissions, and a page calling the API from another origin to reproduce **401 Unauthorized**, **403 Forbidden due to authorization**, **403 Forbidden due to CSRF**, and **CORS/preflight errors**. The core goal is pinpointing **the exact filter, request, and condition causing the failure**, rather than guessing from the status code alone.

## 1. Target Outcomes

After this exercise, you will be able to:

1. Craft requests intentionally to trigger **401** when unauthenticated or sending invalid credentials.
2. Trigger **403 due to authorization** when an authenticated user lacks a role, proving the request passed CSRF validation.
3. Trigger **403 due to CSRF** when an authorized user sends a POST without a token, proving the user/role is not at fault.
4. Trigger **allowed/rejected CORS preflights** using `OPTIONS`, `Origin`, and `Access-Control-Request-*`, distinguishing a server HTTP error from **the browser blocking JavaScript from reading the response**.
5. Inspect DevTools Network, request/response headers, Spring Security logs, and test outputs to reach exact conclusions.

### Scenarios used

The sample API exposes `GET /api/tasks` to read and `POST /api/tasks` to create tasks. The `reader` account can read; the `editor` account can read and create. We **keep CSRF protection enabled** because the API can be called by browser apps and uses `HttpSession` to hold the CSRF token. We allow CORS strictly for `http://localhost:5500`, along with a toggle to disable CORS configuration when reproducing errors.

| Observed code/state | Reproduction condition | Target cause |
| --- | --- | --- |
| **401** | `GET /api/tasks` missing `Authorization` or with wrong password | Unauthenticated |
| **403 — authorization** | `reader` POSTs with a **valid** CSRF token | Authenticated, missing `ROLE_EDITOR` |
| **403 — CSRF** | `editor` POSTs without a CSRF token | State-changing request rejected by `CsrfFilter` |
| **403 — CORS preflight** | `OPTIONS` with an `Origin` not in the allowlist | `CorsFilter` blocks the origin from using the API |
| **Browser CORS error** | Cross-origin page calls API while CORS is disabled | Browser receives no matching CORS permission |
| **201** | `editor` POSTs with valid CSRF token and matching session | Passing control case |

**Remember:** status **403 does not say "because of CSRF" or "because of role."** Even a CORS preflight can return 403. You must cross-check the HTTP method, URL, token, credentials, origin, and which filter processed the request.

## 2. Request Model and Check Ordering

In Spring Security Servlet, requests traverse the security filter chain before reaching the controller. With CORS properly integrated, the flow simplifies to:

```text
Browser / curl
     |
     v
[CORS processing] ---- invalid Origin/preflight -------> CORS blocked
     |
     v
[CSRF processing] ---- unsafe method missing/bad token -> 403
     |
     v
[Authentication] ----- missing/wrong HTTP Basic --------> 401 (depends on request/filter)
     |
     v
[Authorization] ------ missing role/authority ----------> 403
     |
     v
Controller ---------------------------------------------> 200 / 201
```

This diagram shows **diagnostic relationships**, not every filter or a guarantee that all requests hit all four steps. On a POST missing a CSRF token, Spring Security may reject the request **before** checking HTTP Basic or roles. Thus, an unauthenticated POST without credentials can return **403 due to CSRF**, even though an unauthenticated GET returns **401**.

### What is 401 Unauthorized?

HTTP `401` means the request lacks acceptable credentials or has invalid credentials for accessing a protected resource. With HTTP Basic, the response typically includes:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
```

`WWW-Authenticate` is the authentication challenge signal. Do not read HTTP's label "Unauthorized" as "logged in but lacking permission"; that case is usually 403.

### What is 403 Forbidden due to authorization?

Authentication identified a principal, but `AuthorizationManager`/an authorization rule forbids the action. For instance, `reader` has `ROLE_READER` while the POST endpoint requires `ROLE_EDITOR`. This is **403 due to missing permission**, not a wrong password.

### What is 403 Forbidden due to CSRF?

`CsrfFilter` checks the CSRF token on state-changing requests like POST, PUT, PATCH, and DELETE when CSRF is enabled. A missing, expired, session-mismatched, or invalid token causes `403`. A bad token **does not turn into 401**. Check whether the request comes from a browser with auto-attached cookies/credentials to select the proper CSRF policy.

### What is CORS and why is it different from CSRF?

**CORS (Cross-Origin Resource Sharing)** is a browser mechanism deciding whether JavaScript at origin A may read responses from origin B. An origin consists of **scheme, host, and port**; thus `http://localhost:5500` and `http://localhost:8080` are different origins.

- For requests carrying an `Authorization` header, the browser usually sends an **`OPTIONS` preflight** first with `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers`.
- The server must return matching `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, and `Access-Control-Allow-Headers` headers before the browser proceeds with the actual request per Fetch/CORS rules.
- A simple request may actually be sent to the server, yet **JavaScript is still blocked by the browser from reading the response** if CORS disallows it. Therefore the API might return 200 in network/backend logs while the script sees `TypeError: Failed to fetch` or a CORS console error.
- `curl` does not enforce browser CORS policies. It can call the API successfully even while cross-origin scripts are blocked.
- **CORS is not a defense against CSRF, authentication, or authorization**. Allowing CORS does not bypass missing roles; CSRF protection is still needed when browsers automatically attach credentials such as cookies or cached HTTP Basic auth.

## 3. Building the Spring Boot Practice Application

Environment: **Java 17+**, Spring Boot **3.x** with Spring Security **6.x**, Gradle, and a Spring Boot Servlet project. Use Spring Initializr to create a project with `Spring Web`, `Spring Security`, and `Spring Boot Starter Test`, then add `spring-security-test`. The files below share one package and compile/run inside a **complete Spring Boot project**, not as standalone classes invoked directly with `javac`.

Structure:

```text
src/main/java/com/example/securitylab/
  SecurityLabApplication.java
  SecurityConfig.java
  TaskController.java
src/test/java/com/example/securitylab/
  SecurityLabTest.java
```

With Gradle Groovy, required dependencies:

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

In an existing Spring Boot project, keep its plugin configuration, Java toolchain, and BOM/versions; only add missing dependencies. The practice app stores data in RAM so it has no database dependency.

### `SecurityLabApplication.java`

```java
package com.example.securitylab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityLabApplication.class, args);
    }
}
```

Other Java files must share the `com.example.securitylab` package so Spring Boot finds controllers and configs via component scanning.

## 4. Configuring Authentication, Authorization, CSRF, and CORS

### `SecurityConfig.java`

```java
package com.example.securitylab;

import java.util.List;

import jakarta.servlet.DispatcherType;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            @Value("${lab.cors.enabled:true}") boolean corsEnabled
    ) throws Exception {

        if (corsEnabled) {
            // Integrate CORS before authentication/authorization steps.
            http.cors(Customizer.withDefaults());
        } else {
            // Disabled strictly to reproduce CORS errors in the lab.
            http.cors(AbstractHttpConfigurer::disable);
        }

        return http
            // Keep default CSRF; token is stored in HttpSession when needed.
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers("/csrf", "/error").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/tasks")
                    .hasAnyRole("READER", "EDITOR")
                .requestMatchers(HttpMethod.POST, "/api/tasks")
                    .hasRole("EDITOR")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("http://localhost:5500"));
        cors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        cors.setAllowedHeaders(List.of(
            "Authorization", "Content-Type", "X-CSRF-TOKEN"
        ));
        cors.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        source.registerCorsConfiguration("/csrf", cors);
        return source;
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        // Demo accounts strictly for localhost study.
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

**Decisions to understand:**

1. **HTTP Basic** requires requests to `/api/tasks` to include valid credentials. In production, **HTTPS** is mandatory: Base64 does not encrypt usernames/passwords. Passwords here are solely for learning—never put real credentials in URLs, logs, frontend code, or Git.
2. `reader` has `ROLE_READER`; `editor` has both `ROLE_READER` and `ROLE_EDITOR`. `hasRole("EDITOR")` checks for the `ROLE_EDITOR` authority. Valid authentication alone does not open all endpoints.
3. **CSRF is deliberately enabled**. With the default `HttpSessionCsrfTokenRepository`, the token is tied to the session and is valid only when submitted alongside the matching session cookie. Do not enable `SessionCreationPolicy.STATELESS` in this lab because we need to simulate browser/session flows.
4. `GET /csrf` is the lab endpoint for retrieving a CSRF token. `GET` is a safe method so it requires no CSRF token; accessing it grants neither read nor write permissions on tasks.
5. CORS permits only `http://localhost:5500`, never `*`; `allowCredentials(true)` allows that specific origin to send credentialed cross-origin requests in browsers. This **does not replace** Basic auth, roles, or CSRF tokens.
6. `lab.cors.enabled` defaults to `true`. Setting it to `false` disables Spring Security's CORS integration so we can observe the failure difference; that toggle is an experiment, not a fix.
7. `dispatcherTypeMatchers(ERROR).permitAll()` lets Spring Boot's error dispatches reach the error handler; `anyRequest().denyAll()` still blocks endpoints outside the described API.

**Security boundary:** Never carry demo passwords or fixed client origin lists into production. In real apps, design CORS/CSRF around actual origins, credential types, sessions, and protected data.

## 5. Shared Controller to Contrast All Four Failure Types

### `TaskController.java`

```java
package com.example.securitylab;

import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class TaskController {

    private final AtomicLong nextId = new AtomicLong();
    private final ConcurrentMap<Long, Task> tasks = new ConcurrentHashMap<>();

    // Force token materialization: GET returns the token for the current session.
    @GetMapping("/csrf")
    public CsrfView csrf(CsrfToken csrfToken) {
        return new CsrfView(
            csrfToken.getHeaderName(),
            csrfToken.getParameterName(),
            csrfToken.getToken()
        );
    }

    @GetMapping("/api/tasks")
    public List<Task> list() {
        return tasks.values().stream()
            .sorted(Comparator.comparingLong(Task::id))
            .toList();
    }

    @PostMapping("/api/tasks")
    public ResponseEntity<Task> create(@RequestBody NewTask body) {
        if (body.text() == null || body.text().isBlank()) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "text must not be blank"
            );
        }

        Task saved = new Task(nextId.incrementAndGet(), body.text().trim());
        tasks.put(saved.id(), saved);
        return ResponseEntity.status(HttpStatus.CREATED).body(saved);
    }

    public record CsrfView(
        String headerName, String parameterName, String token
    ) {}
    public record NewTask(String text) {}
    public record Task(long id, String text) {}
}
```

There is no role or CSRF logic inside the controller: **SecurityFilterChain enforces them before controller execution**. When blocked with 401/403, the task list stays unchanged. `GET /csrf` reads the live `CsrfToken` (when default CSRF is enabled) and returns token metadata for test clients. Token values can vary across reads, especially with Spring Security 6's default BREACH masking; always use the latest token paired with the matching session.

**Important:** `HttpSession` here supports storing the CSRF token. HTTP Basic authenticates requests via client-sent credentials; holding a session with a CSRF token **does not grant** write access. On POST, you still need valid credentials with `ROLE_EDITOR`.

## 6. Running the Lab and Recording Responses

Run the project in a terminal with CORS enabled by default:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Examples use `http://localhost:8080` strictly for localhost. When using `curl` in PowerShell, invoke `curl.exe` (to avoid the Windows PowerShell alias). Multi-line Bash blocks use `\` for line continuation; in PowerShell, write **one line** or use PowerShell's line continuation. All examples below assume the server runs on port 8080 with no port conflict.

### Case A — 401 due to missing authentication

```bash
curl -i http://localhost:8080/api/tasks
```

Expected status **401 Unauthorized** and challenge header `WWW-Authenticate: Basic ...`. Because the request lacks `Authorization`, Spring Security cannot authenticate a principal to reach the role-protected GET endpoint.

Try a wrong password:

```bash
curl -i -u reader:wrong-password http://localhost:8080/api/tasks
```

Expected **401**, distinct from logging in validly without sufficient permission.

Control check with valid credentials:

```bash
curl -i -u reader:reader-demo-pass http://localhost:8080/api/tasks
```

Expected **200 OK**. With a freshly started server and no tasks created yet, body:

```json
[]
```

### Case B — 403 due to CSRF, even with an authorized user

`editor` is allowed to POST, yet try sending a request **without a CSRF token**:

```bash
curl -i -u editor:editor-demo-pass \
  -H 'Content-Type: application/json' \
  -d '{"text":"Created without CSRF token"}' \
  http://localhost:8080/api/tasks
```

Expected **403 Forbidden**. Here the CSRF filter rejects the unsafe request before the controller runs. Do not assume missing roles just because you see 403; `editor` has `ROLE_EDITOR`.

If you send a POST **with neither credentials nor a CSRF token**, filter ordering may trigger 403 CSRF before 401 authentication. To reproduce a clean 401, use an unauthenticated GET as in Case A.

### Case C — Fetching a CSRF token for the right session

Use a cookie jar to save `JSESSIONID` from the token-issuing response:

```bash
curl -i -c cookies.txt http://localhost:8080/csrf
```

Example body structure (the real token is a long random string):

```json
{
  "headerName": "X-CSRF-TOKEN",
  "parameterName": "_csrf",
  "token": "<actual-token-from-server>"
}
```

Copy the **real `token` value** from the response; do not pass the placeholder literally. `-c cookies.txt` saves cookies returned by the server. For subsequent POST requests, pass **`-b cookies.txt` to send back that exact cookie**, along with the matching `X-CSRF-TOKEN` header.

**Common mistakes to avoid:**
- Sending the CSRF token without its paired session cookie → usually **403**.
- Sending the session cookie without the token → **403**.
- Wrong header token or a token from a different session → **403**.
- A valid token **does not replace** HTTP Basic credentials or access permissions.

### Case D — 403 due to missing role (CSRF already passed)

`reader` has valid credentials yet **lacks the EDITOR role**. Send both the valid CSRF token and matching session:

```bash
curl -i -b cookies.txt -u reader:reader-demo-pass \
  -H 'Content-Type: application/json' \
  -H 'X-CSRF-TOKEN: <actual-token-from-server>' \
  -d '{"text":"Reader cannot create"}' \
  http://localhost:8080/api/tasks
```

Expected **403 Forbidden**. This time the CSRF token was valid, so the rejection comes from `hasRole("EDITOR")`, completely different from Case B. Since both return 403, compare request headers, username/role, and CSRF token/session to tell them apart.

### Case E — Control case: editor creates successfully

Using **the same cookie jar and valid token** as above, switch credentials to `editor`:

```bash
curl -i -b cookies.txt -u editor:editor-demo-pass \
  -H 'Content-Type: application/json' \
  -H 'X-CSRF-TOKEN: <actual-token-from-server>' \
  -d '{"text":"Authorized task"}' \
  http://localhost:8080/api/tasks
```

Expected **201 Created**. If this is the first task since startup:

```json
{"id":1,"text":"Authorized task"}
```

Call `GET` again as `reader` to observe the new record:

```bash
curl -i -u reader:reader-demo-pass http://localhost:8080/api/tasks
```

Expected **200 OK**, listing the newly created task. The ID may differ if earlier creation attempts succeeded. This control check confirms the controller works so you don't mistake every 403 for a broken API.

### Quick comparison

| Case | Credentials | CSRF token/session | Endpoint permission | Expected HTTP |
| --- | --- | --- | --- | --- |
| A: GET no auth | Missing | Not needed for GET | Not reached | 401 |
| A: GET wrong password | Invalid | Not needed for GET | Not reached | 401 |
| A: GET reader | Valid | Not needed for GET | Sufficient | 200 |
| B: POST editor | Valid | **Missing** | Sufficient | 403 due to CSRF |
| D: POST reader | Valid | **Valid** | **Missing** | 403 due to authorization |
| E: POST editor | Valid | **Valid** | Sufficient | 201 |

## 7. Reproducing CORS Preflight Separately

When a web page at `http://localhost:5500` calls the API at `http://localhost:8080` with an `Authorization` header, the browser issues a preflight because `Authorization` is not a CORS-safelisted request header. Preflights typically look like:

```http
OPTIONS /api/tasks HTTP/1.1
Origin: http://localhost:5500
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

### Case F — Preflight from an allowed origin

Inspect the raw response with `curl` (simulating a preflight to inspect headers, not replacing a browser):

```bash
curl -i -X OPTIONS http://localhost:8080/api/tasks \
  -H 'Origin: http://localhost:5500' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
```

With CORS enabled, a valid preflight typically returns **200 OK**, carrying `Access-Control-Allow-Origin: http://localhost:5500` and allowed methods/headers. No Basic credentials are sent in the preflight. A passing preflight **does not mean** the subsequent GET/POST has passed authentication, authorization, or CSRF.

### Case G — Preflight from a rejected origin

Change the origin to an address **outside the allowlist**:

```bash
curl -i -X OPTIONS http://localhost:8080/api/tasks \
  -H 'Origin: http://localhost:5501' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: authorization,content-type,x-csrf-token'
```

With the lab's `CorsFilter`, the response is typically **403** with an indicator like `Invalid CORS request`. This is a 403 **due to CORS**, requiring no logged-in user and carrying no implication about missing roles. To confirm, change the origin back to `5500` with allowed headers/methods: the preflight passes.

### Case H — Disabling CORS and observing browser blocking

Stop the server and restart with a property **strictly for this lab**:

```bash
./gradlew bootRun --args='--lab.cors.enabled=false'
```

Re-run the Case F preflight. Without `CorsFilter` approving the origin, `OPTIONS` may hit security and return 401/403, or the server fails to send the required CORS headers. **Do not rely on one fixed status code** in this mode. The decisive signal is that the response does not authorize the origin/header/method, so the browser refuses to proceed or expose results under CORS rules.

By contrast, a request to **the same endpoint using `curl`** can still return 200 with Basic credentials:

```bash
curl -i -u reader:reader-demo-pass \
  -H 'Origin: http://localhost:5500' \
  http://localhost:8080/api/tasks
```

`curl` does not enforce CORS. Thus "curl gets 200 while the browser gets a CORS error" is completely expected and does not mean authorization is misconfigured. Restart without the property or with `--lab.cors.enabled=true` to re-enable CORS for the next tests.

## 8. Inspecting CORS Errors in Browser and DevTools

To observe this directly, serve an HTML page from a **different origin** such as `http://localhost:5500`. You can use VS Code Live Server or, with Python 3, run inside a directory containing the HTML file:

```bash
python -m http.server 5500
```

Create `cors-lab.html` in the served directory with this demo content (localhost learning credentials only):

```html
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>CORS Lab</title></head>
<body>
  <button id="load">Call GET /api/tasks</button>
  <pre id="result"></pre>
  <script>
    document.getElementById("load").addEventListener("click", async () => {
      const output = document.getElementById("result");
      try {
        const response = await fetch("http://localhost:8080/api/tasks", {
          method: "GET",
          // Demo only: never embed real credentials in frontend code.
          headers: {
            Authorization: "Basic " + btoa("reader:reader-demo-pass")
          },
          credentials: "include"
        });
        output.textContent =
          "HTTP " + response.status + "\n" + await response.text();
      } catch (error) {
        output.textContent = error.name + ": " + error.message;
      }
    });
  </script>
</body>
</html>
```

Open `http://localhost:5500/cors-lab.html`, then click the button:

1. **With CORS enabled:** the **Network** tab typically shows an `OPTIONS` preflight (unless cached) followed by a `GET` returning `200`; the page reads the JSON. Preflight/actual responses include the matching CORS headers.
2. **With CORS disabled:** the **Console** tab reports a CORS policy error; the script sees `TypeError` or `Failed to fetch`. The **Network** tab shows the preflight or response missing required headers. Responses do not carry a special "CORS error" HTTP status code.
3. **With a disallowed origin:** if you move the page to `http://localhost:5501`, the preflight is rejected immediately because only origin `5500` is allowed. Never change the allowlist to `*` just to make the error vanish.
4. **When calling POST from a browser:** allowed CORS only permits the cross-origin call; you still need a user with sufficient role and a CSRF token matching the session. Never disable CSRF to fix a CORS error.

> **Demo warning:** Credentials in JavaScript are strictly for reproducing behavior on localhost; in real applications never embed Basic usernames/passwords or secrets in frontend source. Browsers manage credentials/cookies according to their own policies; choose an appropriate authentication architecture before deploying.

### Distinguishing in DevTools

In **Network**, select a request and read in order:

- **Request URL, Method, Origin:** is it the actual `GET`/`POST` or an `OPTIONS` preflight? Are host, port, and protocol exact?
- **Status and response headers:** `401` with `WWW-Authenticate` points to authentication; `403` requires more evidence; preflight needs matching `Access-Control-Allow-*` headers.
- **Request headers:** was `Authorization` sent? Is `X-CSRF-TOKEN` present and accurate? Was the session cookie sent? Which `Access-Control-Request-Headers` did the preflight ask for?
- **Console:** browser CORS block messages describe origin access denial; JavaScript may be unable to inspect the actual status/body.
- **Server logs/tests:** confirm which filter rejected the request. A single console error alone cannot distinguish CSRF from authorization.

## 9. Automated Testing with MockMvc

`spring-security-test` provides `httpBasic(...)` and `csrf()` to test the filter chain without manually copying tokens. `csrf()` creates a **valid CSRF token for the test request**; use it only in tests, not as a substitute for real client token handling in production.

### `SecurityLabTest.java`

```java
package com.example.securitylab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
    .header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
    .jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
    .status;

@SpringBootTest(properties = "lab.cors.enabled=true")
@AutoConfigureMockMvc
class SecurityLabTest {

    @Autowired
    MockMvc mvc;

    @Test
    void getWithoutCredentialsIs401() throws Exception {
        mvc.perform(get("/api/tasks"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void getWithWrongPasswordIs401() throws Exception {
        mvc.perform(get("/api/tasks")
                .with(httpBasic("reader", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readerCanGetTasks() throws Exception {
        mvc.perform(get("/api/tasks")
                .with(httpBasic("reader", "reader-demo-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void editorPostWithoutCsrfIs403() throws Exception {
        mvc.perform(post("/api/tasks")
                .with(httpBasic("editor", "editor-demo-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"No token\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void readerPostWithCsrfStill403() throws Exception {
        mvc.perform(post("/api/tasks")
                .with(httpBasic("reader", "reader-demo-pass"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"Missing role\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorPostWithCsrfIs201() throws Exception {
        mvc.perform(post("/api/tasks")
                .with(httpBasic("editor", "editor-demo-pass"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"Allowed\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.text").value("Allowed"));
    }

    @Test
    void allowedOriginPreflightPasses() throws Exception {
        mvc.perform(options("/api/tasks")
                .header(HttpHeaders.ORIGIN, "http://localhost:5500")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "authorization,content-type,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "http://localhost:5500"));
    }

    @Test
    void otherOriginPreflightIsForbidden() throws Exception {
        mvc.perform(options("/api/tasks")
                .header(HttpHeaders.ORIGIN, "http://localhost:5501")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "authorization,content-type,x-csrf-token"))
            .andExpect(status().isForbidden());
    }
}
```

Run:

```bash
./gradlew test
```

PowerShell: `.\gradlew.bat test`. The suite covers **8 scenarios**. All pass when the Spring Boot/Java/dependency environment matches and the app uses the classes above; Gradle usually prints `BUILD SUCCESSFUL` on success. There is no fixed stdout beyond the asserted status codes and JSON fields.

**Strength of isolated tests:** Both `editorPostWithoutCsrfIs403` and `readerPostWithCsrfStill403` expect **403**, yet the underlying causes are cleanly isolated via inputs. The 403 preflight test intentionally sends no credentials, proving a 403 can happen **even before authentication**.

## 10. Enabling Logs to Pinpoint the Filter and Root Cause

To observe the filter chain in a study environment, add to `src/main/resources/application.yml`:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
```

When finer detail is needed and **strictly locally**, temporarily use `TRACE` for the relevant namespace. Logger implementation, Spring Security version, and filter chain config affect exact messages; **never depend on a specific log line** as an API contract.

Verification workflow when hitting 403:

1. Record the **method, path, Origin, user/role, CSRF token, and session cookie** of the failing case (never paste real secrets/tokens into shared logs).
2. Try an unauthenticated GET to trigger a clean 401 and confirm the HTTP Basic entry point.
3. Try `editor` POST **without a token** to reproduce 403 CSRF; verify the control case with a valid token + matching session yields 201.
4. Try `reader` POST **with a valid token** to reproduce 403 authorization; switch to `editor` keeping the same token/session to verify 201.
5. For cross-origin browser requests, check whether `OPTIONS` runs before the actual request. Inspect CORS headers on the response; run the same request via `curl` and compare.
6. If rejection occurs before the controller, do not debug business logic before identifying which filter denied the request.

**Avoid logging sensitive data:** never enable TRACE in production just to chase routine bugs; if troubleshooting requires logs, restrict scope/duration and mask `Authorization`, `Cookie`, CSRF tokens, and PII.

## 11. Diagnostic Table: Same Status, Different Fixes

| Symptom | Independent verification | How to fix |
| --- | --- | --- |
| GET returns **401**, has `WWW-Authenticate` | Test both valid and invalid credentials | Check Basic header, password encoder, user store, authentication config |
| POST returns **403**, CSRF token/cookie missing | `editor` with role still gets 403; adding matching-session token yields 201 | Issue/attach token on unsafe methods; keep CSRF when browsers use ambient credentials |
| POST returns **403**, CSRF already valid | `reader` gets 403, `editor` gets 201 | Update role/authority/matcher/policy if business rules require a change |
| OPTIONS preflight returns **403** | Switch between Origin 5500 and 5501 | Configure allowlist for required origin, methods, headers; apply CORS before auth |
| Browser reports **CORS**, `curl` on same API returns 200 | Inspect Network tab, preflight, `Access-Control-Allow-Origin` | Fix server CORS policy; never disable authentication or CSRF |
| Browser cannot read actual 401/403 | Response lacks CORS headers or preflight fails | Fix CORS first so the browser can read responses, then address the real 401/403 |
| POST unexpectedly returns 403 without Basic auth | CSRF filter may reject before Basic auth | Use an unauthenticated GET to test 401; supply token to observe the auth layer |
| POST with valid token still returns 403 | Does token match the session? Does user hold the role? | Separate checks: verify session/token first, then principal/authority |

### Key practical rules

- **401:** first ask "did authentication succeed?".
- **403:** ask "is the CSRF token valid?" first, then ask "does the principal have permission?"; also check whether the request was a preflight from a rejected origin.
- **CORS:** ask "is this the browser blocking access by origin, or an HTTP response JavaScript can read?".
- **CSRF:** ask "does the browser automatically attach credentials to the request?"; never ask only "is the API stateless?".
- **Preflight:** browsers can send `OPTIONS` **without credentials**; configure CORS properly so preflights don't accidentally become authentication failures.
- **Never fix errors by turning off security:** `permitAll()` does not fix CSRF, `csrf.disable()` does not fix CORS, and `allowedOrigins("*")` does not fix authentication or authorization.

## 12. Extension Exercises with Clear Acceptance Criteria

### Exercise A — Investigating "both return 403"

Execute in order: (1) `editor` POST without token, (2) `reader` POST with valid token, (3) `editor` POST with valid token. Capture request headers and statuses; write a one-sentence explanation for **each 403** without vague phrasing like "Spring Security blocked it."

**Pass** if you have evidence of case (3) returning 201 and clearly distinguish `CsrfFilter` from the authorization decision.

### Exercise B — Investigating "curl works, browser doesn't"

Run the lab with CORS enabled and disabled. From origin `5500`, inspect preflight/actual requests in Network; run `curl` directly to the API with the same credentials; compare.

**Pass** if you explain why `curl` ignores browser CORS policies, identify the `OPTIONS` request, and pinpoint the missing or mismatched `Access-Control-Allow-Origin` header.

### Exercise C — Distinguishing origin from cookie/session

Change only the HTML page origin port from `5500` to `5501`; do not touch the API. Observe the preflight getting blocked and restore `5500`. Next, fetch a CSRF token in one session and attempt a POST using **another session** to observe the 403 CSRF failure.

**Pass** if you never confuse **CORS origin** with **the session storing the CSRF token**. An allowed origin does not make session A's token valid inside session B.

### Exercise D — Writing a reproducible bug report

For each failure type, record: URL, method, Origin (if any), whether credentials were sent, role, whether CSRF token/cookie matched, expected status, actual status, Network/log evidence, and the fix. Mask real passwords/tokens. A good report lets someone else reproduce the exact failure without guessing.

## 13. Common Conceptual Mistakes

- **"403 = wrong role."** Wrong: 403 can also come from CSRF, CORS preflights, and other denial mechanisms.
- **"A CORS error means the server never received the request."** Not always: preflight can stop the real request, yet for non-preflighted requests the server may process it while the browser blocks JS from reading the response.
- **"Disabling CSRF fixes CORS errors."** Wrong: the two policies solve two completely different problems.
- **"Enabling CORS lets browsers call the API without logging in."** Wrong: CORS grants neither credentials nor permissions.
- **"HTTP Basic is stateless so CSRF is impossible."** Wrong: browsers can automatically re-send cached Basic credentials; evaluate whether ambient credentials exist.
- **"401 and 403 are interchangeable."** Do not swap them: each status carries distinct semantics affecting client behavior; inspect the filter chain to return the right error.
- **"Testing with curl proves CORS works."** Insufficient: curl does not enforce CORS; inspect preflight/response headers and browser behavior.
- **"Copying the CSRF token is enough."** Wrong: tokens are normally bound to a specific session; preserve the cookie and avoid stale or cross-session tokens.

## 14. Foundational Documentation

Consult documentation matching your exact **Spring Security version**:

- [Spring Security — Exception Handling](https://docs.spring.io/spring-security/reference/servlet/architecture.html): filter roles, security processing order, and exception translation.
- [Spring Security — HTTP Basic](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html): `BasicAuthenticationFilter` and authentication entry point.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): authorization matchers, roles, authorities, and `denyAll`.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): `CsrfFilter`, CSRF tokens, and browser considerations.
- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): handling preflights before Spring Security and CORS integration.
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): SOP, Origin, preflight, and `Access-Control-Allow-*`.

**Overall completion criteria:** A running localhost application, tests reproducing 401, 403 authorization, 403 CSRF, allowed/blocked CORS preflights, observing browser CORS errors when CORS is disabled, and explaining why **the same 403 status can originate from different processing layers**.
