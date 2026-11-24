# Consistent Success and Failure Responses for a JSON Login API

> **Goal:** Design and implement JSON login responses in Spring Security so the frontend always understands the **outcome**, **HTTP status code**, **stable error code**, **display message**, and **returned data**. The same convention must apply consistently across errors raised in controllers, Spring MVC, and the Spring Security filter chain.

## 1. Why Does a JSON Login API Need a Response Contract?

When the frontend calls **POST /api/auth/login** with JSON username/password, the outcome can fall into many branches: valid login, malformed JSON, missing required fields, wrong password, unauthenticated call to a protected API, authenticated but lacking permissions, invalid CSRF token, or a server error.

A system lacking a convention might return **200** with **{"error":"Wrong password"}** on failed login; another branch might return **302** to an HTML login page, while filter errors return status **403** with an HTML body. The frontend has to guess each case, becomes hard to test, and easily mishandles errors.

**Principle:** the HTTP status communicates the exact outcome category; the JSON body has one unified structure; `code` is a stable machine key; `message` is a user-facing message; sensitive data and internal details are never exposed.

In this lesson, the example uses **Spring Boot 3.x, Spring Security 6.x, Java 17+, Spring MVC/Servlet**, and **JSON login with session cookies**. This is a concrete model to illustrate all response branches completely. If the app uses JWT/OAuth2 and stores no sessions, keep the response principle the same while changing the authentication persistence mechanism.

## 2. Choosing a Consistent JSON Format

Example convention for all API responses:

~~~json
{
  "success": true,
  "code": "LOGIN_SUCCESS",
  "message": "Login successful",
  "data": {
    "username": "alice"
  }
}
~~~

On failure:

~~~json
{
  "success": false,
  "code": "INVALID_CREDENTIALS",
  "message": "Invalid username or password",
  "data": null
}
~~~

Meaning of each field:

| Field | Data type | Rule |
| --- | --- | --- |
| **success** | boolean | true for succeeded operations; false for failed operations |
| **code** | string | Stable code for logic handling and i18n; never use message as a key |
| **message** | string | Readable message, never exposing stack traces or whether an account exists |
| **data** | object / array / null | Useful payload on success; null for errors in this example |

A consistent structure **does not mean every case returns 200**. HTTP status remains the standard signal for browsers, observability tools, API gateways, retry logic, and HTTP clients. The body supplements details per the contract.

### 2.1. Status Table to Standardize

| Scenario | HTTP status | Illustrative code | Meaning |
| --- | --- | --- | --- |
| Login succeeded | **200 OK** | LOGIN_SUCCESS | Valid authentication, session established |
| Missing username/password or bad JSON | **400 Bad Request** | INVALID_REQUEST / INVALID_JSON | Invalid client input |
| Wrong Content-Type sent | **415 Unsupported Media Type** | UNSUPPORTED_MEDIA_TYPE | Endpoint requires application/json |
| Username does not exist or wrong password | **401 Unauthorized** | INVALID_CREDENTIALS | Cannot authenticate; generic message |
| Calling a protected resource unauthenticated | **401 Unauthorized** | UNAUTHENTICATED | Client needs to log in |
| Authenticated but lacking permissions | **403 Forbidden** | FORBIDDEN | Client lacks authority |
| Missing, expired, or invalid CSRF token | **403 Forbidden** | CSRF_INVALID | Request rejected at the CSRF protection layer |
| Path does not exist | **404 Not Found** | NOT_FOUND | Resource or route does not exist |
| Unsupported HTTP method | **405 Method Not Allowed** | METHOD_NOT_ALLOWED | Wrong HTTP method used |
| Exceeded allowed login attempts, if rate-limited | **429 Too Many Requests** | RATE_LIMITED | Only returned when rate-limit policy actually triggers |
| Unexpected server error | **500 Internal Server Error** | INTERNAL_ERROR | Do not expose system internals |

Distinguishing **401** (not validly authenticated) from **403** (authenticated but unauthorized) is especially important. Missing or wrong CSRF tokens can also be blocked with 403 before the request reaches the controller. This case must not be confused with "wrong password".

An API may choose **RFC 9457 Problem Details** for errors instead of the illustrative structure above. Both approaches are sound as long as the team agrees clearly on the contract, status codes, and client behavior; never randomly mix multiple body formats within the same API surface.

## 3. Actual Processing Flow of JSON Login

~~~text
Client
  |
  | POST /api/auth/login, Content-Type: application/json
  | Session cookie + CSRF token (if logging in with session)
  v
Spring Security Filter Chain
  |-- Invalid/missing CSRF -----> 403 JSON (CSRF_INVALID)
  |-- Access check -------------> allow request to login
  v
Spring MVC / JSON deserialization
  |-- Invalid JSON body --------> 400 JSON (INVALID_JSON)
  |-- Missing field ------------> 400 JSON (INVALID_REQUEST)
  v
AuthenticationManager
  |-- Wrong credentials --------> 401 JSON (INVALID_CREDENTIALS)
  |-- Valid --------------------> create SecurityContext
  v
Save SecurityContext to session
  |
  v
200 JSON (LOGIN_SUCCESS) + session cookie
~~~

Errors in the **filter chain** usually happen before Spring MVC resolves a controller. Therefore, a standalone **@RestControllerAdvice** cannot guarantee that every 401/403 returns JSON. You must configure **AuthenticationEntryPoint** and **AccessDeniedHandler** in Spring Security, while handling parse/validation errors in Spring MVC.

A successful login only means **AuthenticationManager** accepted the credentials. For subsequent requests to continue recognizing the user in the session model, you must save the **SecurityContext** via **SecurityContextRepository**; merely returning 200 JSON without saving the context can still leave the next call returning 401.

## 4. Practical Spring Boot Example with a Response Contract

### 4.1. Project Setup

Use Spring Initializr to create a **Spring Boot 3.x** project, Java **17 or newer**, with **Spring Web** and **Spring Security** dependencies. The example below uses namespace **com.example.demo** and corresponding classes under **src/main/java/com/example/demo/**. The Spring Initializr project already includes **DemoApplication** containing **@SpringBootApplication** and `main`; no bootstrap changes needed.

Add to **src/main/resources/application.properties**:

~~~properties
server.port=8080
demo.user.password=${DEMO_USER_PASSWORD}
~~~

Locally, supply **DEMO_USER_PASSWORD=demo-pass** before running. Never put real passwords into source files. Localhost HTTP in the example is for practice only; **production must use HTTPS**, verify certificates, and set **Secure**, **HttpOnly**, and **SameSite** cookies appropriate to the architecture.

### 4.2. Create a Shared Response Type

File **ApiResponse.java**:

~~~java
package com.example.demo;

import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.ALWAYS)
public record ApiResponse<T>(
        boolean success,
        String code,
        String message,
        T data) {

    public static <T> ApiResponse<T> ok(
            String code, String message, T data) {
        return new ApiResponse<>(true, code, message, data);
    }

    public static <T> ApiResponse<T> fail(
            String code, String message) {
        return new ApiResponse<>(false, code, message, null);
    }
}
~~~

Java 17 **record** types are supported for JSON serialization by Jackson in Spring Boot. The **@JsonInclude(ALWAYS)** annotation ensures the **data** field appears even when null, even if the application globally excludes null fields. For every failure branch, **ApiResponse.fail(...)** produces the exact same shape.

### 4.3. Writing JSON from Filters or Handlers Before Spring MVC

Filter-layer security handlers do not return **ResponseEntity** like controllers. We use **ObjectMapper** to write the JSON body directly.

File **JsonHttp.java**:

~~~java
package com.example.demo;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.springframework.http.MediaType;

public final class JsonHttp {
    private JsonHttp() {}

    public static void write(
            ObjectMapper mapper,
            HttpServletResponse response,
            int status,
            ApiResponse<?> body) throws IOException {
        response.setStatus(status);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setHeader("Cache-Control", "no-store");
        mapper.writeValue(response.getOutputStream(), body);
    }
}
~~~

Sharing **ApiResponse** and **JsonHttp** across security branches avoids cases where **401** returns HTML while **400** returns JSON. The **Cache-Control: no-store** header prevents caching responses containing account info. The login response never returns passwords, password hashes, or the full internal principal.

### 4.4. Spring Security Config: 401/403 JSON, JSON Login, and Session

File **SecurityConfig.java**:

~~~java
package com.example.demo;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.CompositeSessionAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfAuthenticationStrategy;
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.security.web.csrf.InvalidCsrfTokenException;
import org.springframework.security.web.csrf.MissingCsrfTokenException;
import jakarta.servlet.DispatcherType;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(
            PasswordEncoder encoder,
            @Value("${demo.user.password}") String rawPassword) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode(rawPassword))
                        .roles("USER")
                        .build());
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(provider);
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    CsrfTokenRepository csrfTokenRepository() {
        return new HttpSessionCsrfTokenRepository();
    }

    @Bean
    SessionAuthenticationStrategy sessionAuthenticationStrategy(
            CsrfTokenRepository csrfTokens) {
        return new CompositeSessionAuthenticationStrategy(List.of(
                new ChangeSessionIdAuthenticationStrategy(),
                new CsrfAuthenticationStrategy(csrfTokens)));
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ObjectMapper mapper,
            SecurityContextRepository contexts,
            CsrfTokenRepository csrfTokens) throws Exception {

        http
            .csrf(csrf -> csrf.csrfTokenRepository(csrfTokens))
            .securityContext(s -> s.securityContextRepository(contexts))
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers("/error").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/auth/csrf").permitAll()
                .requestMatchers(HttpMethod.POST, "/api/auth/login").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint((req, res, ex) ->
                    JsonHttp.write(mapper, res, 401,
                        ApiResponse.fail("UNAUTHENTICATED",
                            "Please log in")))
                .accessDeniedHandler((req, res, ex) -> {
                    boolean csrfProblem =
                        ex instanceof MissingCsrfTokenException
                        || ex instanceof InvalidCsrfTokenException;
                    JsonHttp.write(mapper, res, 403,
                        ApiResponse.fail(
                            csrfProblem ? "CSRF_INVALID" : "FORBIDDEN",
                            csrfProblem
                                ? "Invalid CSRF token"
                                : "You do not have permission to perform this action"));
                }))
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .requestCache(AbstractHttpConfigurer::disable)
            .logout(logout -> logout
                .logoutUrl("/api/auth/logout")
                .logoutSuccessHandler((req, res, auth) ->
                    JsonHttp.write(mapper, res, 200,
                        ApiResponse.ok(
                            "LOGOUT_SUCCESS",
                            "Logout successful", null))));

        return http.build();
    }
}
~~~

The configuration expresses key decisions:

1. **formLogin** and **httpBasic** are disabled so no redirects to HTML pages or Basic challenges occur outside the JSON contract.
2. **AuthenticationEntryPoint** returns **401 JSON** when unauthenticated. **AccessDeniedHandler** returns **403 JSON** when lacking permissions or when CSRF fails. Spring Security uses this handler for **CsrfFilter** under the configuration above.
3. **HttpSessionSecurityContextRepository** persists `Authentication` across requests via session cookies. Because the example does not issue JWTs, **STATELESS** policy is **not** enabled.
4. **ChangeSessionIdAuthenticationStrategy** rotates the session ID on login to prevent session fixation. **CsrfAuthenticationStrategy** invalidates the old CSRF token after login; the client must fetch a new token for subsequent POSTs.
5. **DaoAuthenticationProvider** compares passwords via **BCryptPasswordEncoder**. The in-memory user serves this lesson, not a production account management model.
6. Endpoint **/api/admin** requires **ROLE_ADMIN**. The sample user only has **ROLE_USER**, illustrating a **403** response after authentication.
7. Spring Security handles logout at **POST /api/auth/logout** and returns **200 JSON** via `logoutSuccessHandler`. The logout request must also include a valid CSRF token.

Note: JSON login is implemented in a custom controller, so the example manually invokes **SessionAuthenticationStrategy** and saves **SecurityContext**. Spring Security's built-in login filters usually perform these steps automatically per their configuration.

### 4.5. Controller: JSON Login, CSRF, and Protected APIs

File **AuthController.java**:

~~~java
package com.example.demo;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/auth")
public class AuthController {
    private final AuthenticationManager authenticationManager;
    private final SecurityContextRepository contexts;
    private final SessionAuthenticationStrategy sessions;

    public AuthController(
            AuthenticationManager authenticationManager,
            SecurityContextRepository contexts,
            SessionAuthenticationStrategy sessions) {
        this.authenticationManager = authenticationManager;
        this.contexts = contexts;
        this.sessions = sessions;
    }

    public record LoginRequest(String username, String password) {}
    public record LoginView(String username) {}
    public record CsrfView(String headerName, String token) {}

    @GetMapping("/csrf")
    public ApiResponse<CsrfView> csrf(
            @RequestAttribute("_csrf") CsrfToken token) {
        return ApiResponse.ok("CSRF_READY", "CSRF token is ready",
                new CsrfView(token.getHeaderName(), token.getToken()));
    }

    @PostMapping("/login")
    public ResponseEntity<ApiResponse<?>> login(
            @RequestBody LoginRequest body,
            HttpServletRequest request,
            HttpServletResponse response) {

        if (body == null
                || body.username() == null || body.username().isBlank()
                || body.password() == null || body.password().isBlank()) {
            return ResponseEntity.badRequest().body(
                    ApiResponse.fail("INVALID_REQUEST",
                            "Username and password are required"));
        }

        Authentication authenticated;
        try {
            authenticated = authenticationManager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            body.username(), body.password()));
        } catch (AuthenticationException ex) {
            return ResponseEntity.status(401).body(
                    ApiResponse.fail("INVALID_CREDENTIALS",
                            "Invalid username or password"));
        }

        sessions.onAuthentication(authenticated, request, response);
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authenticated);
        SecurityContextHolder.setContext(context);
        contexts.saveContext(context, request, response);

        return ResponseEntity.ok(
                ApiResponse.ok("LOGIN_SUCCESS", "Login successful",
                        new LoginView(authenticated.getName())));
    }
}
~~~

The controller executes sequentially: validate input; call **AuthenticationManager**; normalize login errors to **401**; apply session protection; create and save **SecurityContext**; then return **200 JSON**. Wrong username and wrong password must not return different messages, limiting account enumeration.

File **PrivateController.java**:

~~~java
package com.example.demo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PrivateController {

    public record ProfileView(String username) {}

    @GetMapping("/api/me")
    public ApiResponse<ProfileView> me(Authentication authentication) {
        return ApiResponse.ok("PROFILE_OK", "Profile loaded successfully",
                new ProfileView(authentication.getName()));
    }

    @GetMapping("/api/admin")
    public ApiResponse<String> admin() {
        return ApiResponse.ok("ADMIN_OK", "Admin API accessed",
                "admin");
    }
}
~~~

An unauthenticated client calling **GET /api/me** is blocked in Spring Security with **401 JSON**, never reaching the controller. User **alice** after login calling **GET /api/me** receives **200 JSON**; calling **GET /api/admin** returns **403 JSON** due to lacking the role, also before reaching the controller.

### 4.6. Standardizing Bad JSON Errors in Spring MVC

File **ApiExceptionHandler.java**:

~~~java
package com.example.demo;

import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.HttpMediaTypeNotSupportedException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiResponse<Void>> invalidJson(
            HttpMessageNotReadableException ex) {
        return ResponseEntity.badRequest().body(
                ApiResponse.fail("INVALID_JSON",
                        "Body must be valid JSON"));
    }

    @ExceptionHandler(HttpMediaTypeNotSupportedException.class)
    public ResponseEntity<ApiResponse<Void>> unsupportedMedia(
            HttpMediaTypeNotSupportedException ex) {
        return ResponseEntity.status(415).body(
                ApiResponse.fail("UNSUPPORTED_MEDIA_TYPE",
                        "Please send Content-Type: application/json"));
    }
}
~~~

**@RestControllerAdvice** handles Spring MVC errors, especially JSON parse errors occurring **before login() is invoked**. If you add Bean Validation (**@Valid**, **@NotBlank**, ...) to the DTO, add a **MethodArgumentNotValidException** handler returning **400** with the same structure. Error handling must never turn a server error into **200** or return raw exception messages containing sensitive data.

### 4.7. Standardizing Remaining Routing Errors

Some errors like **404**, **405**, or unexpected errors can pass through Spring Boot's **/error** mechanism instead of controller advice. File **ApiErrorController.java** shows how to convert servlet-container errors forwarded to **/error** into the same format:

~~~java
package com.example.demo;

import jakarta.servlet.RequestDispatcher;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.boot.web.servlet.error.ErrorController;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiErrorController implements ErrorController {

    @RequestMapping("/error")
    public ResponseEntity<ApiResponse<Void>> error(
            HttpServletRequest request) {
        Object raw = request.getAttribute(
                RequestDispatcher.ERROR_STATUS_CODE);
        int status = raw instanceof Integer value ? value : 500;

        String code = switch (status) {
            case 400 -> "INVALID_REQUEST";
            case 404 -> "NOT_FOUND";
            case 405 -> "METHOD_NOT_ALLOWED";
            case 415 -> "UNSUPPORTED_MEDIA_TYPE";
            default -> "INTERNAL_ERROR";
        };
        String message = switch (status) {
            case 400 -> "Invalid request";
            case 404 -> "Resource not found";
            case 405 -> "HTTP method not supported";
            case 415 -> "Unsupported media type";
            default -> "Server could not process the request";
        };

        return ResponseEntity.status(status).body(
                ApiResponse.fail(code, message));
    }
}
~~~

This approach suits a pure-JSON API demo. In apps serving both HTML pages and REST, scope the JSON policy by API namespace, path, or content negotiation so browser error pages are not altered. Not every exception forwards to **/error**; branches handled by other frameworks or middleware must be verified separately.

## 5. Testing the API and Verifying HTTP Status + Body

### 5.1. Starting the App

With a Linux/macOS shell and the Maven wrapper generated by Spring Initializr:

~~~bash
export DEMO_USER_PASSWORD=demo-pass
./mvnw spring-boot:run
~~~

On Windows PowerShell:

~~~powershell
$env:DEMO_USER_PASSWORD = "demo-pass"
.\mvnw.cmd spring-boot:run
~~~

### 5.2. Fetching the CSRF Token Before Login

Because the example stores authentication in a session cookie, **POST /api/auth/login requires a CSRF token**. The GET endpoint provides the token via JSON; the client must preserve the cookie/session across requests.

~~~bash
curl -i -c cookies.txt -b cookies.txt http://localhost:8080/api/auth/csrf
~~~

Illustrative body (actual token varies):

~~~json
{
  "success": true,
  "code": "CSRF_READY",
  "message": "CSRF token is ready",
  "data": {
    "headerName": "X-CSRF-TOKEN",
    "token": "<actual-token>"
  }
}
~~~

Copy the actual **data.token** value. **Do not** copy the illustrative placeholder inside angle brackets; it is not a valid token.

### 5.3. Successful and Failed Login

On a shell with **jq**, you can extract the token automatically:

~~~bash
TOKEN=$(curl -sS -c cookies.txt -b cookies.txt http://localhost:8080/api/auth/csrf | jq -r '.data.token')
curl -i -c cookies.txt -b cookies.txt -H "Content-Type: application/json" -H "X-CSRF-TOKEN: $TOKEN" --data '{"username":"alice","password":"demo-pass"}' http://localhost:8080/api/auth/login
~~~

Expected **HTTP 200**:

~~~json
{
  "success": true,
  "code": "LOGIN_SUCCESS",
  "message": "Login successful",
  "data": {
    "username": "alice"
  }
}
~~~

To demonstrate **401** for a wrong password, fetch a valid CSRF token (after a successful login the token was rotated), then send a wrong password:

~~~bash
TOKEN=$(curl -sS -c cookies.txt -b cookies.txt http://localhost:8080/api/auth/csrf | jq -r '.data.token')
curl -i -c cookies.txt -b cookies.txt -H "Content-Type: application/json" -H "X-CSRF-TOKEN: $TOKEN" --data '{"username":"alice","password":"wrong"}' http://localhost:8080/api/auth/login
~~~

Expected **HTTP 401** and body:

~~~json
{
  "success": false,
  "code": "INVALID_CREDENTIALS",
  "message": "Invalid username or password",
  "data": null
}
~~~

The test above reuses the already logged-in session; a failed login does not automatically clear an earlier session by default. In real tests, use a fresh cookie jar for each independent scenario so prior login state does not affect results.

### 5.4. Checking Protected APIs and Authorization

Using the session cookie from the successful login:

~~~bash
curl -i -b cookies.txt http://localhost:8080/api/me
curl -i -b cookies.txt http://localhost:8080/api/admin
~~~

Expected:

- **GET /api/me** returns **200**, **code=PROFILE_OK**, **data.username=alice**.
- **GET /api/admin** returns **403**, **code=FORBIDDEN**, because the sample account only has **ROLE_USER**.
- With a fresh cookie jar, **GET /api/me** returns **401**, **code=UNAUTHENTICATED**.

### 5.5. Checking Malformed JSON and CSRF Failure

Malformed JSON body with a valid token:

~~~bash
TOKEN=$(curl -sS -c cookies.txt -b cookies.txt http://localhost:8080/api/auth/csrf | jq -r '.data.token')
curl -i -c cookies.txt -b cookies.txt -H "Content-Type: application/json" -H "X-CSRF-TOKEN: $TOKEN" --data '{"username":' http://localhost:8080/api/auth/login
~~~

Expected **400**, **code=INVALID_JSON**. If you omit the CSRF header while sending the POST, **CsrfFilter** blocks it before parsing JSON; you will normally receive **403**, **code=CSRF_INVALID**. This is expected behavior: to test JSON errors specifically, first send a request that passes the CSRF layer.

### 5.6. Logout

Once you have a valid session, fetch a new token and call:

~~~bash
TOKEN=$(curl -sS -c cookies.txt -b cookies.txt http://localhost:8080/api/auth/csrf | jq -r '.data.token')
curl -i -c cookies.txt -b cookies.txt -H "X-CSRF-TOKEN: $TOKEN" -X POST http://localhost:8080/api/auth/logout
curl -i -b cookies.txt http://localhost:8080/api/me
~~~

Expected: the logout request returns **200** with **code=LOGOUT_SUCCESS** and **data=null**; the subsequent **/api/me** request returns **401** because the session was invalidated. Testing logout requires the same cookie jar and the token issued for that session.

The curl commands use HTTP on **localhost** for this lesson. Never run a password-accepting endpoint over HTTP in deployment; always use HTTPS. Commands containing sample passwords should not be replaced with real passwords because process lists, shell history, or monitoring tools may record them.

## 6. What Should Automated Tests Verify?

A good test checks **both status and body**, not just "the request ran". With Spring Security, **MockMvc** and **spring-security-test** are common ways to verify responses; when testing end-to-end, pay attention to cookie jars/sessions and CSRF as shown above.

Suggested test matrix:

| Test | Input | Expected status | Expected code |
| --- | --- | --- | --- |
| Valid login | Valid JSON, valid CSRF | 200 | LOGIN_SUCCESS |
| Wrong password | Valid JSON, wrong credentials, valid CSRF | 401 | INVALID_CREDENTIALS |
| Non-existent user | Valid JSON, unknown username, valid CSRF | 401 | INVALID_CREDENTIALS |
| Missing username | JSON missing field, valid CSRF | 400 | INVALID_REQUEST |
| Syntax-invalid JSON | Malformed body, valid CSRF | 400 | INVALID_JSON |
| Missing CSRF | Login POST without valid CSRF | 403 | CSRF_INVALID |
| Unauthenticated call to /api/me | GET without valid session | 401 | UNAUTHENTICATED |
| User lacking role calling /api/admin | GET with ROLE_USER session | 403 | FORBIDDEN |
| Missing path | GET to non-existent route | 404 | NOT_FOUND |
| Valid logout | POST with session and CSRF | 200 | LOGOUT_SUCCESS |
| Calling /api/me after logout | GET with invalidated session | 401 | UNAUTHENTICATED |

Useful assertions: **Content-Type: application/json** header, values of **success**, **code**, **message**, and presence of **data**; verify there is no HTML body, unexpected redirect, or password in the response. For internal errors, verify the body only has a generic message while technical details live in internal logs keyed by trace/request ID.

Keep each test isolated so an earlier session does not affect later tests. Specifically for POST requests, when testing payload errors, send valid CSRF first; when testing CSRF, intentionally omit or corrupt the token.

## 7. Common Mistakes and How to Fix Them

### 7.1. Always Returning HTTP 200 with success=false

This makes it hard for clients, API gateways, and operations dashboards to distinguish success from failure; retries or analytics easily break. **Fix:** use **400/401/403/429/500** matching the cause while keeping the error code in the body.

### 7.2. Driving Frontend Logic from message Text

Messages can change language or phrasing. **Fix:** branch on **status** and a stable **code** such as **INVALID_CREDENTIALS**; `message` is only for display or user guidance.

### 7.3. Writing Only @RestControllerAdvice and Assuming 401/403 Are Handled

**AuthenticationEntryPoint** and **AccessDeniedHandler** can emit responses before Spring MVC; missing configuration often yields a different body format or a redirect. **Fix:** unify the response writer across both filters and controllers.

### 7.4. Distinguishing "Account Does Not Exist" from "Wrong Password"

Returning two distinct messages gives attackers a signal to enumerate usernames. **Fix:** use the same **INVALID_CREDENTIALS** code and generic message; apply attempt throttling, logging, and appropriate monitoring.

### 7.5. Returning 200 Success While the Next Call Always Returns 401

In Spring Security 6, controller code that authenticates manually must explicitly save **SecurityContext** if sessions are used to maintain authentication. **Fix:** use **SecurityContextRepository.saveContext(...)** and matching session configuration. If choosing a stateless/token API, replace this with issuing and verifying credentials/tokens by design rather than mixing the two models.

### 7.6. Disabling CSRF Because POST /login Returned 403

When an app uses session cookies for browser authentication, CSRF is a real risk. **Fix:** issue tokens, send the token in a header with the session, and fetch a new token after login/logout as configured. Only consider omitting CSRF when the authentication model does not rely on credentials automatically sent by the browser and the threat model has been evaluated.

### 7.7. Returning Internal Technical Errors in message

Never push exceptions, stack traces, SQL queries, passwords, security tokens, or internal class names to clients. **Fix:** use public error codes and generic messages in the body; keep technical details in controlled logs/traces.

### 7.8. Standardizing Bodies While Forgetting 404/405/415 and Proxy Errors

Errors can originate in the router, servlet container, security filters, or gateway. **Fix:** build a scenario table, verify with real tools, and standardize at the layer where each error arises; document exceptions returned by reverse proxies or third parties.

## 8. Design Rules for Real Projects

1. **Lock the API contract**: choose a response envelope or Problem Details; define code, message, data, and versioning.
2. **Use accurate HTTP statuses**: 200 for login success; 400 for invalid input; 401 for authentication failure; 403 for missing permissions/CSRF; 429 only when rate limiting applies.
3. **Protect information**: never return passwords, hashes, stack traces, or account existence signals; never log credentials.
4. **Separate layers**: filters handle Security 401/403, MVC advice handles parsing/validation, and error handling handles routing or container errors.
5. **Persist post-login auth properly**: sessions are saved, cookies are securely configured, or tokens are issued according to the chosen model.
6. **Design for the frontend**: inspect `code` to display messages, navigate to login on UNAUTHENTICATED, show permission denied on FORBIDDEN, and avoid infinite auto-retries on INVALID_CREDENTIALS.
7. **Production hardening**: enforce HTTPS, verify certificates, set Secure/HttpOnly/SameSite cookies, keep CSRF for cookie auth, enforce rate limiting, and verify CORS for exact origins.
8. **Test every error path**: verify status/body for success, controller failure, Security failure, bad requests, and server errors.

## 9. References

- [Spring Security — Username/Password Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/): AuthenticationManager, DaoAuthenticationProvider, UserDetailsService, and PasswordEncoder.
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): saving SecurityContext when a controller authenticates manually; session management.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF requirements on POST and using tokens with JavaScript applications.
- [Spring Security — Exception Handling](https://docs.spring.io/spring-security/reference/servlet/architecture.html): filter ordering and handling authentication/authorization errors.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): standard HTTP error format usable instead of an envelope depending on project contract.
