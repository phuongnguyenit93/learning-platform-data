# Reading JSON Login Payloads with AuthenticationConverter

In **Spring Security for Servlet applications**, many frontends send login credentials in an HTTP request with a JSON body, such as `POST /api/login` with `{"username":"alice","password":"..."}`, instead of an HTML form with `username` and `password` fields. To integrate this request style while still leveraging Spring Security's authentication system, we must separate two responsibilities:

- **Reading the request and converting it into an unauthenticated Authentication object**: the job of `AuthenticationConverter`.
- **Verifying the username/password and deciding authentication**: the job of `AuthenticationManager` and `AuthenticationProvider`, not the converter.

Spring Security provides `AuthenticationFilter` to connect an `AuthenticationConverter` with an `AuthenticationManager`, a `RequestMatcher` identifying the login request, and handlers for success/failure outcomes. That way, the application can handle JSON safely **without manually checking passwords in a controller or granting roles from client-declared JSON**.

This lesson builds a JSON login flow for **Java 17+, Spring Boot 3.x, Spring Security 6.x, Servlet/MVC**: explaining the converter contract, complete Java class code, session vs stateless choices, CSRF, payload limits, data errors, MockMvc testing, and common security risks. The Spring code snippets require the appropriate dependencies; the standalone JDK program at the end specifically illustrates routing logic, without pretending to be a JSON parser or password verifier.

## 1. Architecture: From JSON Request to Authentication

### 1.1. Recommended Processing Flow

~~~text
Client
  |
  | POST /api/login
  | Content-Type: application/json
  | {"username":"alice","password":"secret"}
  v
Servlet Filter Chain
  |
  v
FilterChainProxy / matching SecurityFilterChain
  |
  v
CsrfFilter (if using cookie/session: must have valid CSRF token)
  |
  v
AuthenticationFilter
  |-- RequestMatcher: is this POST /api/login?
  |
  |-- AuthenticationConverter.convert(request)
  |       |
  |       +-- bounded JSON parsing
  |       +-- validate syntax/required fields
  |       +-- UsernamePasswordAuthenticationToken.unauthenticated(...)
  |               (NOT yet trusted)
  |
  |-- AuthenticationManager.authenticate(token)
  |       |
  |       +-- DaoAuthenticationProvider
  |               |-- UserDetailsService loads account
  |               |-- PasswordEncoder.matches(...) verifies password
  |               +-- returns authenticated Authentication
  |
  |-- on success:
  |       |-- sets SecurityContext
  |       |-- saves context via SecurityContextRepository if configured
  |       +-- AuthenticationSuccessHandler: HTTP response
  |
  +-- on failure:
          +-- AuthenticationFailureHandler: HTTP response
~~~

All steps take place within the **Servlet filters** ecosystem. A custom converter is not responsible for managing SecurityContext itself, writing sessions, deciding redirects, or verifying passwords.

### 1.2. Why Not Use the Converter Like a Controller?

For example, having a controller handle `POST /api/login` directly and call a repository to compare passwords often leads to rebuilding logic Spring Security already provides: encoder, account status, user cache, provider, authentication events, session fixation, security context, success/failure handlers, and authorization checks. If a controller is strictly required, you still need to orchestrate the steps via AuthenticationManager and handle the full security lifecycle; for JSON login in Servlet filters, `AuthenticationFilter + AuthenticationConverter` is usually cleaner and easier to extend.

### 1.3. Component Comparison

| Component | Input | Output / Responsibility | Does Not Do |
| --- | --- | --- | --- |
| `RequestMatcher` | HTTP request | Matches / does not match login endpoint | Parse JSON, authenticate password |
| `AuthenticationConverter` | `HttpServletRequest` | An **untrusted** `Authentication`, or `null` if inapplicable | Grant authenticated permissions |
| `AuthenticationFilter` | Matcher, converter, and manager | Coordinates authentication in the filter chain, invokes handlers | Replace providers to verify passwords itself |
| `AuthenticationManager` | Authentication request | Resulting Authentication or error | Read JSON body |
| `DaoAuthenticationProvider` | Username/password token | Checks UserDetails, PasswordEncoder, and account flags | Define HTTP JSON schema |
| `AuthenticationSuccessHandler` | Successful Authentication, request, response | Chooses HTTP status/JSON/redirect | Grant authorities requested by client |
| `AuthenticationFailureHandler` | AuthenticationException, request, response | Returns consistent HTTP error without leaking secrets | Allow request through on wrong password |
| `SecurityContextRepository` | SecurityContext/request/response | Saves/loads context per stateful/request-scoped strategy | Decide by itself whether client may log in |

## 2. Contract of AuthenticationConverter

The interface in Spring Security Servlet:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.authentication.AuthenticationConverter;

// API shape, not a standalone Java file:
public interface AuthenticationConverter {
    Authentication convert(HttpServletRequest request)
            throws AuthenticationException;
}
~~~

### What Object Should It Return?

For username/password, the appropriate result before authentication is:

~~~java
Authentication requestToken =
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, rawPassword);
~~~

This is a Spring Security 6.x factory method; import `org.springframework.security.authentication.UsernamePasswordAuthenticationToken`. At this point the token contains **unverified credentials**. Do not set `isAuthenticated=true`, do not assign `ROLE_ADMIN` from a client JSON field, and do not call the trusted-token factory merely because the username exists.

The filter then passes the token to `AuthenticationManager.authenticate(...)`. On success, the provider returns an Authentication with a valid principal, authorities, and authenticated state. The converter is **not proof of identity**.

### Meaning of null and Exceptions

| Result of `convert(...)` | When Appropriate | AuthenticationFilter Behavior |
| --- | --- | --- |
| Returns an unauthenticated Authentication | Request targets endpoint and payload is usable | Sent to AuthenticationManager |
| Returns `null` | Converter finds no applicable credentials; for requests outside login scope | No authentication attempt performed at that step |
| Throws `AuthenticationException` | Login request has invalid/missing payload or converter cannot complete per contract | Enters failure handling flow if exception occurs within filter processing |

One important piece of advice: **do not return `null` for every invalid JSON payload**. If the request has already been identified as `POST /api/login`, missing username/password is an input error that should receive a clear response per API policy. Returning null can let the request fall through to other filters with confusing results, without necessarily triggering the failure handler.

### Does the Converter Need to Check the URL Itself?

`AuthenticationFilter` can accept a `RequestMatcher` so it only invokes the converter on the right endpoint. Thus, URL/path/method should be defined explicitly in the filter configuration; a fallback check inside the converter can be helpful for component reuse, but **does not replace the filter's matcher**. If the filter uses an overly broad matcher, requests outside login scope may have their bodies read or be unexpectedly blocked.

## 3. Designing the JSON Login API Before Writing Code

Minimal contract for the example:

~~~http
POST /api/login HTTP/1.1
Content-Type: application/json
Cookie: JSESSIONID=...               (if session already exists)
X-CSRF-TOKEN: <valid-csrf-token>     (when CSRF is enabled)

{"username":"alice","password":"demo-only-password"}
~~~

The CSRF token line in the example is a **protocol-explanatory placeholder**, not a token usable in practice. With Spring Security 6, sending tokens via request attributes/headers and token handling (possibly including XOR masking) must match the application's `CsrfTokenRequestHandler` configuration; never hardcode tokens. A frontend using cookie-based login must have a mechanism to obtain and transmit a trusted token.

The demo mechanism returns:

| Scenario | HTTP | Example Response Body |
| --- | --- | --- |
| Valid username/password | 200 | `{"status":"ok","username":"alice"}` |
| Wrong username/password | 401 | `{"error":"invalid_credentials"}` |
| Malformed JSON or missing fields | 400 | `{"error":"invalid_request"}` |
| Non-JSON Content-Type | 415 | `{"error":"unsupported_media_type"}` |
| Body exceeds limit | 413 | `{"error":"payload_too_large"}` |
| Internal authentication flow error | 503 in demo | `{"error":"login_unavailable"}` |
| Missing CSRF token during session/cookie login | 403 | May be returned by CsrfFilter before converter |

These are **application-defined API conventions**, not hard-coded defaults of `AuthenticationConverter`. An application can choose different responses as long as they are consistent and do not enable account enumeration. In all cases, never echo back passwords, password hashes, or stack traces to the frontend.

### Why Limit the Body Size?

Reading an unbounded JSON body increases memory/CPU exhaustion risks, especially on login endpoints prone to attack. The example uses an **8 KiB** (8 × 1024 bytes) limit for a username/password payload; real applications pick a limit based on requirements and proxy/gateway layers. Reading up to `limit + 1` bytes lets you detect oversized payloads **even when Content-Length is omitted** or chunked encoding is used. Proxies/servers should still enforce their own request limits.

Other input requirements:

- Accept only `application/json` and compatible charset parameters if sent by clients.
- Username must be a non-blank string with an explicit length limit.
- Password must be a string; never `trim()` it automatically because whitespace can be part of a password.
- Accept only allowed API fields; never read role, authorities, enabled, or authenticated from the client to construct a token.
- Define handling for JSON with unknown fields, duplicate keys, trailing tokens, and wrong types.
- Do not retain passwords in request attributes, shared caches, or logs.
- Read the body in the converter **once**; Servlet input streams are not replayable by default.

## 4. Complete Converter Example with Jackson

Spring Boot Web typically auto-configures a Jackson `ObjectMapper` bean. The following example uses Jackson to deserialize a Java 17 record, check Content-Type, bound the body, validate fields, and produce an **unauthenticated** token.

Create `src/main/java/com/example/jsonlogin/JsonLoginAuthenticationConverter.java`:

~~~java
package com.example.jsonlogin;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import java.io.IOException;
import org.springframework.http.InvalidMediaTypeException;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.authentication.AuthenticationConverter;

public final class JsonLoginAuthenticationConverter
        implements AuthenticationConverter {

    private static final int MAX_JSON_BYTES = 8 * 1024;
    private final ObjectMapper mapper;

    public JsonLoginAuthenticationConverter(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    // Record describing JSON input, with no roles/authenticated fields.
    public record LoginPayload(String username, String password) {}

    // Input error so the failure handler can select an appropriate HTTP status.
    public static final class LoginInputException
            extends AuthenticationException {

        private final int status;

        public LoginInputException(int status, String reason) {
            super(reason);
            this.status = status;
        }

        public LoginInputException(int status, String reason, Throwable cause) {
            super(reason, cause);
            this.status = status;
        }

        public int status() {
            return status;
        }
    }

    @Override
    public Authentication convert(HttpServletRequest request) {
        // AuthenticationFilter's matcher is the primary boundary.
        if (!"POST".equals(request.getMethod())) {
            return null;
        }

        String contentType = request.getContentType();
        try {
            if (contentType == null ||
                    !MediaType.APPLICATION_JSON.isCompatibleWith(
                            MediaType.parseMediaType(contentType))) {
                throw new LoginInputException(
                    415, "Unsupported login content type");
            }
        } catch (InvalidMediaTypeException ex) {
            throw new LoginInputException(
                415, "Unsupported login content type", ex);
        }

        byte[] body;
        try {
            // Do not read unboundedly even on requests without Content-Length.
            body = request.getInputStream().readNBytes(MAX_JSON_BYTES + 1);
        } catch (IOException ex) {
            // Operational I/O error; do not disguise as a wrong password.
            throw new AuthenticationServiceException(
                "Could not read login request", ex);
        }

        if (body.length > MAX_JSON_BYTES) {
            throw new LoginInputException(413, "Login body too large");
        }
        if (body.length == 0) {
            throw new LoginInputException(400, "Login body missing");
        }

        LoginPayload credentials;
        try {
            credentials = mapper.readerFor(LoginPayload.class)
                .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
                .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
                .readValue(body);
        } catch (JsonProcessingException ex) {
            throw new LoginInputException(400, "Invalid login JSON", ex);
        } catch (IOException ex) {
            throw new AuthenticationServiceException(
                "Could not parse login request", ex);
        }

        if (credentials == null ||
                credentials.username() == null ||
                credentials.username().isBlank() ||
                credentials.username().length() > 128 ||
                credentials.password() == null ||
                credentials.password().isEmpty() ||
                credentials.password().length() > 1024) {
            throw new LoginInputException(
                400, "Invalid login fields");
        }

        // Do not turn unverified username/password into a trusted token.
        return UsernamePasswordAuthenticationToken.unauthenticated(
            credentials.username(), credentials.password());
    }
}
~~~

### Reviewing the Code Decisions in Detail

1. `AuthenticationFilter` will be configured with a POST /api/login matcher. The `POST` check in the converter is only defense-in-depth. For other paths, the matcher prevents the converter from reading the body.
2. `MediaType.APPLICATION_JSON.isCompatibleWith(...)` checks Content-Type without requiring a rigid `"application/json"` string match, so parameters like `charset=UTF-8` do not automatically get rejected.
3. `readNBytes(MAX_JSON_BYTES + 1)` bounds the bytes read and detects oversized bodies. It does not replace request limits at the container, reverse proxy, and rate limiting layers.
4. `ObjectReader` enables `FAIL_ON_UNKNOWN_PROPERTIES` and `FAIL_ON_TRAILING_TOKENS` to reject extra fields or trailing JSON tokens after the object. Rejecting **duplicate JSON keys** requires separate strict duplicate detection configuration on the parser if the API requires it; do not assume these two flags alone suffice.
5. Username and password take exactly those two fields. The client cannot decide `isAuthenticated` or `GrantedAuthority`.
6. Never `trim` the password; leading/trailing whitespace may be valid password characters.
7. `LoginInputException` is an `AuthenticationException` so the filter routes it to the failure handler; the status stored inside the exception is merely demo policy. I/O errors are represented via a separate `AuthenticationServiceException`, avoiding disguising system errors as wrong credentials.
8. Use `UsernamePasswordAuthenticationToken.unauthenticated(...)` so the provider performs verification, without setting the context or returning an authenticated token in the converter.

**Note:** the `LoginPayload` record is short-lived but holds the plaintext password in memory during authentication. This is natural during password verification; keep its lifetime short, never log/serialize the object, and never place it in queues/caches. Java Strings cannot actively zero out their memory immediately; do not claim `eraseCredentials` guarantees erasing every String copy that ever existed.

### If You Want to Use a Different DTO

An application might name the field `email` instead of `username`, or accept a complex identifier; in that case change the record and mapping logic. However, **the converter must never grant permissions** based on a client-sent `role` field. If the authentication type differs from username/password, create the corresponding request token and use a compatible provider.

## 5. Configuring Spring Boot, AuthenticationFilter, and Provider

The example runs as **session-based login using JSON**: POST /api/login returns JSON and saves SecurityContext in the session; subsequent GET /api/me requests use the issued session cookie. **CSRF remains enabled** because cookies are sent automatically by browsers and carry cross-site request risks. For focus, accounts use `InMemoryUserDetailsManager`; production should replace this with a real account store and appropriate authentication/access control mechanisms.

### 5.1. Maven Dependencies

In a Spring Boot 3.x project with a compatible parent/BOM and run/test plugins, add the following dependencies. Versions of Spring artifacts should be managed by the Boot BOM.

~~~xml
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
~~~

`spring-boot-starter-web` typically already includes Jackson in common Spring Boot 3.x setups. If a project explicitly excludes Jackson, you must add the corresponding dependency or switch JSON libraries and configure the parser bean. For future Boot versions, verify against the actual classpath.

### 5.2. Application Entry Point

Create `src/main/java/com/example/jsonlogin/JsonLoginApplication.java`:

~~~java
package com.example.jsonlogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonLoginApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonLoginApplication.class, args);
    }
}
~~~

### 5.3. Complete SecurityConfig

Create `src/main/java/com/example/jsonlogin/SecurityConfig.java`:

~~~java
package com.example.jsonlogin;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationFilter;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

import jakarta.servlet.http.HttpServletResponse;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        // For learning ONLY. Never hardcode production passwords.
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-only-password"))
                .roles("USER")
                .build());
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(List.of(provider));
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        // Choose persistence via HTTP session for this example.
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationManager manager,
            ObjectMapper mapper,
            SecurityContextRepository repository) throws Exception {

        JsonLoginAuthenticationConverter converter =
                new JsonLoginAuthenticationConverter(mapper);
        AuthenticationFilter jsonFilter =
                new AuthenticationFilter(manager, converter);

        jsonFilter.setRequestMatcher(
            new AntPathRequestMatcher("/api/login", "POST"));

        // Custom AuthenticationFilter needs an appropriate repository so login
        // is persisted across HTTP requests, not only on the current thread.
        jsonFilter.setSecurityContextRepository(repository);

        // Change session ID when a session already existed before login,
        // mitigating session fixation risk in a cookie-based model.
        jsonFilter.setSessionAuthenticationStrategy(
            new ChangeSessionIdAuthenticationStrategy());

        jsonFilter.setSuccessHandler((request, response, authentication) -> {
            response.setStatus(HttpServletResponse.SC_OK);
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            mapper.writeValue(response.getWriter(), Map.of(
                "status", "ok",
                "username", authentication.getName()));
        });

        jsonFilter.setFailureHandler((request, response, exception) -> {
            int status;
            String error;

            if (exception instanceof
                    JsonLoginAuthenticationConverter.LoginInputException input) {
                status = input.status();
                error = switch (status) {
                    case 400 -> "invalid_request";
                    case 413 -> "payload_too_large";
                    case 415 -> "unsupported_media_type";
                    default -> "invalid_request";
                };
            } else if (exception instanceof AuthenticationServiceException) {
                status = HttpServletResponse.SC_SERVICE_UNAVAILABLE;
                error = "login_unavailable";
            } else {
                status = HttpServletResponse.SC_UNAUTHORIZED;
                error = "invalid_credentials";
            }

            response.setStatus(status);
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            mapper.writeValue(response.getWriter(), Map.of("error", error));
        });

        http.securityContext(context -> context
                .securityContextRepository(repository))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST, "/api/login").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
                .anyRequest().denyAll())
            .exceptionHandling(ex -> ex.authenticationEntryPoint(
                (request, response, exception) ->
                    response.sendError(HttpServletResponse.SC_UNAUTHORIZED)))
            .addFilterAt(jsonFilter, UsernamePasswordAuthenticationFilter.class);

        // Do not call csrf.disable(): cookie-based sessions require CSRF protection.
        // Do not enable formLogin(): the demo app uses only custom JSON login.
        return http.build();
    }
}
~~~

The configuration above illustrates Spring Security 6.x APIs; constructors/setters of `DaoAuthenticationProvider` may be marked deprecated in newer 6.x releases, and other releases may provide a constructor accepting `UserDetailsService`. Choose initialization syntax matching your locked project version; the **core contract** remains a provider using an encoder, a manager verifying credentials, and a filter using a converter.

Several key points:

1. `new AuthenticationFilter(manager, converter)` connects the converter to a **real** AuthenticationManager; nowhere does the converter compare passwords itself.
2. `setRequestMatcher(...)` restricts matching **strictly to POST /api/login**. A GET /api/login request is not treated as a JSON authentication attempt.
3. `addFilterAt(jsonFilter, UsernamePasswordAuthenticationFilter.class)` places the custom filter at the conventional username/password filter position. This example does not also enable `formLogin()` to avoid two filters handling the same mechanism. If the project has form login or multiple chains, explicitly design matchers and ordering instead of inadvertently replacing other filters.
4. `SecurityContextRepository` is configured **on both AuthenticationFilter and HttpSecurity**, so saving and loading context across requests stays consistent. Merely calling `SecurityContextHolder.setContext(...)` in custom code is not enough for a login session to survive to the next request.
5. `ChangeSessionIdAuthenticationStrategy` is chosen for the session-based example; real applications must cross-check session fixation protection, concurrent session controls, and the system's session authentication strategy.
6. The success handler returns only JSON and the authenticated username; **never return passwords, hashes, cookies/session IDs, or the entire principal**.
7. The failure handler distinguishes **request errors** (400/413/415), **invalid credentials** (401), and certain service errors (503), without revealing whether a user exists.
8. `CsrfFilter` still protects POST login. If the frontend fails to send a valid CSRF token, the request can be rejected before the converter even runs.
9. `AuthenticationFilter` in the example is a dedicated login path; an API does not become stateless merely by using JSON instead of HTML.

**Notable limitation:** For applications using remember-me, OAuth2 login, multiple security chains, or session concurrency, a custom AuthenticationFilter must integrate the corresponding extra strategies/handlers properly. Do not assume replacing `UsernamePasswordAuthenticationFilter` with another filter automatically preserves all traditional form login features.

### 5.4. Endpoint to Check Session After Login

Create `src/main/java/com/example/jsonlogin/CurrentUserController.java`:

~~~java
package com.example.jsonlogin;

import java.security.Principal;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentUserController {

    @GetMapping("/api/me")
    public Map<String, String> me(Principal principal) {
        return Map.of("username", principal.getName());
    }
}
~~~

The endpoint is protected with `authenticated()`, so in a properly configured request flow `principal` is a valid principal. Expected response once Alice has logged in:

~~~json
{"username":"alice"}
~~~

This represents the JSON content, without committing to specific whitespace/serialization layout if the mapper is customized. When unauthenticated, the demo's entry point returns 401.

## 6. Testing Requests and Understanding Session/CSRF Lifecycle

After running the project with the appropriate Maven wrapper:

~~~bash
./mvnw spring-boot:run
~~~

The client sends body:

~~~json
{
  "username": "alice",
  "password": "demo-only-password"
}
~~~

**Do not try a plain curl POST and conclude the converter is broken because you see 403.** The demo model uses session cookies and **keeps CSRF enabled**. The frontend must obtain a valid CSRF token, maintain the same session/cookie, and send the token according to the configured CSRF repository/handler convention. The sample code does not expose a browser CSRF token endpoint because the focus is on the converter; you can use MockMvc with `csrf()` in section 8 to test authentication independently of the UI.

If you have a valid CSRF token provided by the application and the matching session cookie, an illustrative request looks like:

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  -H 'Content-Type: application/json' \
  -H 'X-CSRF-TOKEN: REPLACE_WITH_VALID_TOKEN' \
  -d '{"username":"alice","password":"demo-only-password"}' \
  http://localhost:8080/api/login
~~~

`REPLACE_WITH_VALID_TOKEN` is a placeholder. A token cannot be fabricated by typing an arbitrary string. With Spring Security 6 and the default XOR-CSRF mechanism, how the frontend receives/sends tokens must match the actual handler configuration. When login succeeds, the client keeps the session cookie; a GET /api/me request with that cookie typically returns Alice's username.

If building a real browser frontend, you must also decide: SameSite, Secure, HttpOnly cookies; CSRF token exposure; CORS allowlist if cross-origin; cache policy for login responses; session expiration; logout; session fixation; rate limiting/MFA. Never choose `csrf().disable()` just to make a demo POST run easier while still authenticating with cookies.

### Distinguishing JSON Login and JWT Login

| Model | After POST /api/login | Where Do Subsequent Requests Get Identity? |
| --- | --- | --- |
| Session example in this lesson | Handler returns JSON, context is saved via HttpSession repository | Valid session cookie and SecurityContextRepository |
| Stateless Bearer/JWT API | Login mechanism may return a properly issued token via a dedicated component | Client sends Bearer token on each request; resource server verifies token |
| JSON login without saving context/token | 200 response does not automatically create persistent login state | Subsequent request may be anonymous again |

**`AuthenticationConverter` does not issue JWTs, sign tokens, or make an endpoint stateless.** If the system wants OAuth2/OIDC or bearer tokens, choose the proper architecture instead of inventing unverified/non-revocable token strings.

## 7. How JSON Errors Enter the Filter

### 7.1. Malformed JSON

~~~http
POST /api/login
Content-Type: application/json

{"username":"alice","password":
~~~

Jackson throws a parse error, and the converter converts it to `LoginInputException(400, ...)`. If it passes a valid CSRF filter, AuthenticationFilter invokes the failure handler and returns a public body like `{"error":"invalid_request"}`. Never log the entire malformed body because it may contain a password.

### 7.2. Valid JSON but Wrong Password

~~~json
{"username":"alice","password":"not-the-password"}
~~~

The converter still builds an **unauthenticated** token. `DaoAuthenticationProvider` checks the password and throws the appropriate `AuthenticationException`; the failure handler returns a generic 401. This is an **authentication failure**, distinct from a JSON structural error.

### 7.3. Client Sends role or authenticated

~~~json
{
  "username": "alice",
  "password": "demo-only-password",
  "authorities": ["ROLE_ADMIN"],
  "authenticated": true
}
~~~

Because the demo converter enables `FAIL_ON_UNKNOWN_PROPERTIES`, this body is rejected with 400. Even if an API chooses to ignore unknown fields, **never turn those permission fields into an authenticated token**; authorities must come from the provider/trusted source.

### 7.4. Mismatched Content-Type

If `text/plain` or `application/x-www-form-urlencoded` is sent to an endpoint accepting only JSON, the converter reports 415 via the configured exception. A Spring MVC controller can use `@RequestBody` and `consumes=...`, but **AuthenticationFilter runs in the filter chain before the controller**, so media type checking in the converter does not rely on `@RequestBody` validation.

### 7.5. Oversized Body

With an 8192-byte limit, payloads exceeding 8192 bytes are rejected by the converter with 413 before deserialization. The limit is measured in **bytes**, not Java char count or Unicode code point count.

### 7.6. Non-AuthenticationException Exceptions

`AuthenticationConverter.convert(...)` declares only unchecked `AuthenticationException` in its API. If code lets `IOException` or `RuntimeException` escape unconverted, the system may bypass the expected failure handler and return a different response or leak details if error handling is poorly configured. The example catches Jackson/IO errors and maps them to appropriate exceptions, while **not masking all operational errors as 401 wrong password**.

### 7.7. Body Already Consumed by Another Filter

Servlet input streams do not by default allow multiple components to read the full body. If a logging filter reads the JSON before AuthenticationFilter without providing a truly replayable wrapper, the converter may see an empty input. Merely using `ContentCachingRequestWrapper` does not automatically guarantee downstream components read from the cache; you must understand the specific wrapper contract, avoid logging sensitive bodies, and test filter ordering.

## 8. Testing with MockMvc: Must Pass Through Real Filters

A `@WithMockUser` test pre-populating an Authentication **does not prove the converter read JSON, the provider verified the password, or the context was saved**. A properly focused test sends `POST /api/login` with JSON and a valid CSRF token, then observes the response, session, and `GET /api/me`.

Create `src/test/java/com/example/jsonlogin/JsonLoginIntegrationTest.java`:

~~~java
package com.example.jsonlogin;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class JsonLoginIntegrationTest {

    @Autowired MockMvc mvc;

    @Test
    void correctJsonLoginPersistsAuthenticationInSession()
            throws Exception {

        MvcResult login = mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"username":"alice","password":"demo-only-password"}
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"))
            .andExpect(jsonPath("$.username").value("alice"))
            .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"));
    }

    @Test
    void wrongPasswordIs401() throws Exception {
        mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"username":"alice","password":"wrong"}
                    """))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("invalid_credentials"));
    }

    @Test
    void invalidJsonIs400() throws Exception {
        mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{not valid json"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error").value("invalid_request"));
    }

    @Test
    void unknownFieldCannotGrantRole() throws Exception {
        mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "username":"alice",
                      "password":"demo-only-password",
                      "authorities":["ROLE_ADMIN"]
                    }
                    """))
            .andExpect(status().isBadRequest());
    }

    @Test
    void tooLargeJsonIs413() throws Exception {
        String body = "{\"username\":\"alice\",\"password\":\""
                + "x".repeat(8200) + "\"}";

        mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(body))
            .andExpect(status().isPayloadTooLarge());
    }

    @Test
    void missingCsrfIsRejectedBeforeConverterSuccess()
            throws Exception {
        mvc.perform(post("/api/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"username":"alice","password":"demo-only-password"}
                    """))
            .andExpect(status().isForbidden());
    }

    @Test
    void unauthenticatedGetMeIs401() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

**Note on status matcher:** `status().isPayloadTooLarge()` is available in Spring Test versions providing code 413. If a specific Spring Test version lacks this matcher, check status code 413 with `status().is(413)`. To avoid version dependence, you can use `status().is(413)` directly in tests. Assertions hold only if the project uses the exact chain, converter, provider, repo, and failure handler from the example.

### What Do the Test Expectations Prove?

| Test | What It Proves |
| --- | --- |
| Valid JSON + session | Converter creates appropriate token; provider authenticates; AuthenticationFilter saves context; subsequent GET reads principal |
| Wrong password | Converter parses JSON, **provider** rejects credentials |
| Invalid JSON | Converter returns 400 input error via failure handler |
| Client-supplied authorities field | Request schema prevents client from adding permissions |
| Oversized body | Byte limit is enforced before deserialization |
| POST without CSRF | CsrfFilter protects cookie-based login |
| Unauthenticated GET /api/me | Authorization denies, entry point returns 401 |

To test filter ordering and harder edge cases, add tests for `Content-Type: text/plain`, missing password, overly long username, invalid session cookie, session fixation, and sequential requests. For the converter with a mocked `AuthenticationManager`, you can assert the input token has `isAuthenticated=false` and carries no trusted authorities.

### Verifying the Right SecurityFilterChain Is Actually Selected

In multi-chain applications, `securityMatcher("/api/**")` and `@Order` can cause login requests to enter a different chain. When a test returns 404/403 despite valid JSON, verify the filter is registered on the chain matching `POST /api/login` and is not handled earlier by another filter/entry point. Never tweak `permitAll()` recklessly to mask a wrong matcher.

## 9. Standalone Java 17: Simulating the Parse-or-Skip Decision

The following program runs **with JDK 17 only**, illustrating distinguishing three branches: skipping requests not matching login, rejecting wrong media type/body size, or forwarding a valid request to authentication. It **does not parse JSON, does not check passwords, and does not replace Spring Security**; those functions are already implemented in the framework code above.

Save file `JsonLoginRoutingDemo.java`:

~~~java
public class JsonLoginRoutingDemo {
    private static final int MAX_BYTES = 8 * 1024;

    static String route(String method, String path,
                        String contentType, int byteCount) {
        if (!"POST".equals(method) || !"/api/login".equals(path)) {
            return "SKIP";
        }
        if (contentType == null ||
                !contentType.startsWith("application/json")) {
            return "REJECT 415";
        }
        if (byteCount > MAX_BYTES) {
            return "REJECT 413";
        }
        if (byteCount == 0) {
            return "REJECT 400";
        }
        return "CONVERT -> AUTHENTICATE";
    }

    public static void main(String[] args) {
        System.out.println(route("GET", "/api/login",
                "application/json", 80));
        System.out.println(route("POST", "/api/login",
                "text/plain", 80));
        System.out.println(route("POST", "/api/login",
                "application/json", 9000));
        System.out.println(route("POST", "/api/login",
                "application/json", 0));
        System.out.println(route("POST", "/api/login",
                "application/json", 80));
    }
}
~~~

Compile and run commands:

~~~bash
javac JsonLoginRoutingDemo.java
java JsonLoginRoutingDemo
~~~

Exact stdout:

~~~text
SKIP
REJECT 415
REJECT 413
REJECT 400
CONVERT -> AUTHENTICATE
~~~

`route` uses `startsWith("application/json")` **only for simple simulation** and must not be copied into a production converter: an invalid Content-Type with that prefix would still be accepted. In real Spring code, use `MediaType.parseMediaType(...)` and check compatibility.

## 10. Security Issues Related to JSON Login

### 10.1. CSRF in Cookie-Based Authentication

JSON does not inherently protect against CSRF. If browsers automatically send authentication cookies and the API has side effects, an appropriate CSRF policy is required. Browser cross-origin restrictions, CORS, and SameSite cookies help but **do not replace CSRF evaluation**. Login also carries login-CSRF risk, where an attacker forces a victim's browser to log into an attacker-controlled account. Thus the example retains `CsrfFilter` and tests that missing CSRF returns 403.

Do not configure `csrf().disable()` globally just because the frontend sends `application/json`. If building a stateless API using Bearer tokens in headers, CSRF can be evaluated differently; tie the decision to the **actual credential mechanism**, not the body format.

### 10.2. Never Create an Authenticated Token Inside the Converter

**Wrong:**

~~~java
// DO NOT use: client is unauthenticated yet a trusted token is created.
return UsernamePasswordAuthenticationToken.authenticated(
    username, null, List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));
~~~

`authenticated(...)` requires the caller to already have a trusted basis to authenticate and grant authorities. In a converter reading input from the Internet, the data has not yet been verified by a provider. Use `unauthenticated(...)` to go through the proper password/account-lock/encoder verification chain.

### 10.3. Do Not Compare Passwords Directly or Store Plaintext

AuthenticationProvider must use `PasswordEncoder.matches(...)` with a secure hash from the user store; never use `raw.equals(storedHash)`, and never hash passwords manually with `MessageDigest.getInstance("SHA-256")` without an appropriate KDF/salt/cost. `BCryptPasswordEncoder` in the demo represents one choice; real products must select cost and migration according to security policy.

### 10.4. Do Not Log Credentials

All of the following logging practices are risky:

- Logging the full login JSON body.
- Logging an Authentication request token containing credentials.
- Logging error messages accompanied by passwords.
- Writing login payloads into tracing/APM, request replay, access logs, or uncontrolled crash reports.

Log only necessary, restricted metadata such as request ID, general error code, and processing duration; never use username/password as a sole correlation key in unprotected environments.

### 10.5. Rate Limiting, MFA, and Brute Force

The converter only bounds schema/size; it **does not solve credential stuffing**. Production login endpoints need rate limiting, abuse monitoring, sensible account lockout, MFA/passkeys where appropriate, anomaly detection, and username enumeration controls. Strive to keep responses for wrong username and wrong password identical; never return information letting attackers learn which accounts exist.

### 10.6. Session Fixation and Cookie Policy

With cookie-based sessions, an appropriate session fixation policy is required after authentication. The example sets `ChangeSessionIdAuthenticationStrategy` on the custom filter to handle pre-existing sessions. You also need timeout policies, logout, `Secure`/`HttpOnly`/`SameSite` cookie flags, HTTPS, and session store protection. If the application already has a complex session management strategy, use **the exact strategy configured by the system**, avoiding a separate instance that breaks concurrency/session registry behavior.

### 10.7. Do Not Trust JSON Fields Containing Tenant or Role

If login requires a tenant/organization, the tenant chosen by the client is **a requested input**, not proof of access to that tenant. The provider/identity service must verify the user belongs to the chosen tenant; never add `ROLE_ADMIN` from the payload. In multi-tenant setups, the user store and SecurityContext must preserve clear, trusted identity/tenant data.

### 10.8. Body Size and JSON Parser

The 8 KiB limit in the converter reduces memory exhaustion risk, but does not replace proxy/container max request size, nesting limits, duplicate-key policy, timeouts, request concurrency limits, and a WAF if needed. Jackson parsing from input bodies can cause CPU spikes on crafted JSON; consider setting parser constraints according to actual security requirements. Never build a manual JSON parser with split/regex for credentials.

## 11. Common Issues and How to Handle Them

| Symptom | Likely Cause | How to Verify |
| --- | --- | --- |
| POST /api/login returns 403 despite valid JSON | CsrfFilter rejected before authentication | Send valid CSRF token; check repository and session |
| Converter does not run | Filter matcher has wrong URL/method, wrong chain, filter not added | Inspect selected SecurityFilterChain and AuthenticationFilter position |
| Converter receives empty body | Another filter already consumed stream, client sent no body | Inspect input stream, filter order, logging |
| Login returns 400 | Malformed JSON/schema, null password field, data exceeds field limits | Check validation, actual client JSON, Content-Type |
| Login returns 415 | Content-Type is not application/json or media type syntax error | Send proper Content-Type, check charset |
| Login returns 413 | Body exceeds 8 KiB | Check payload limits and see what extra data client sends |
| Login returns 401 with right password | Misconfigured provider/encoder/UserDetailsService, disabled user | Test AuthenticationManager, BCrypt hash, account status |
| Login returns 200 but GET /api/me returns 401 | Context not saved, session cookie lost, stateless policy | Check SecurityContextRepository on filter and chain, Set-Cookie, and follow-up request cookie |
| Login returns 200 but browser sees no user | Client dropped cookie, cross-origin, SameSite/Secure/CORS, session timeout | Trace request cookies and browser policies |
| Converter returns null on invalid JSON | Returned null instead of throwing AuthenticationException | Distinguish inapplicable request from malformed payload |
| Adding roles from payload and API "still works" | Created trusted token before verification | Use only unauthenticated tokens and trusted providers |
| Login/filter runs twice | Filter registered twice in container + security chain, or formLogin also enabled | Inspect filter registration and matchers |
| Custom filter runs on wrong Basic/Bearer requests | Overly broad matcher or overlapping chains | Configure exact securityMatcher/requestMatcher |
| HTTP error exposes stack trace | Unwrapped exception / error layer returns details | Configure failure handler to return generic error and log safely |
| WithMockUser test PASSES but real login FAILS | Test bypasses converter/provider | Use MockMvc posting JSON + csrf and session assertions |
| Passwords with whitespace rejected | Converter trimmed/normalized password | Preserve raw password input; check null/empty appropriately |

### How Does AuthenticationFilter Differ from UsernamePasswordAuthenticationFilter?

Traditional `UsernamePasswordAuthenticationFilter` reads username/password via **request parameters** (suited to form-urlencoded) and has dedicated handling for form login configuration. It does not read JSON bodies with Jackson by default. `AuthenticationFilter` brings the `AuthenticationConverter` abstraction to separate extracting data from the request from authentication itself. When building JSON login, placing a custom converter into AuthenticationFilter is usually cleaner than reading the body directly and manually setting SecurityContext in a controller.

### Why Not Use @RequestBody and @Valid in the Converter?

`@RequestBody` and many `@Valid` features are argument resolution/validation mechanisms of **Spring MVC controllers**. AuthenticationFilter runs in the Servlet Filter layer **before the request reaches DispatcherServlet**, so you cannot assume controller annotations will automatically parse/validate JSON for the converter. To use Bean Validation, you can invoke a validator manually or extract validation into a service, while keeping input/exception control inside the filter. In the example, the record and validation conditions are written explicitly inside the converter.

## 12. Self-Check Questions and Exercises

**Exercise 1.** Why shouldn't `AuthenticationConverter` create `UsernamePasswordAuthenticationToken.authenticated(...)` directly from JSON?

**Answer:** Because JSON is untrusted data; the converter only translates credentials, while the provider must verify them using UserDetailsService/PasswordEncoder. Creating a trusted token directly bypasses verification and can grant unauthorized permissions.

**Exercise 2.** A client sends malformed JSON to POST /api/login. Should the converter return null or throw AuthenticationException?

**Answer:** For a request already matching the login endpoint, throw an appropriate AuthenticationException so the failure handler produces an intentional error response. `null` is only appropriate when no authentication attempt applies under the designed contract.

**Exercise 3.** A developer uses `@PostMapping("/api/login")` with `@RequestBody` and expects AuthenticationFilter to automatically receive the DTO object. Is that right?

**Answer:** No. AuthenticationFilter runs before the Spring MVC controller. The converter must read, parse, and validate HttpServletRequest itself (or delegate to a filter-level component), not rely on controller `@RequestBody`.

**Exercise 4.** The converter receives `{"username":"alice","password":"good","roles":["ADMIN"]}`. Why must client-supplied roles be rejected or ignored?

**Answer:** Clients have no authority to self-declare verified authorities. Roles and permissions must be granted by a trusted source/provider after authentication. In the strict JSON schema example, unknown fields are rejected with 400.

**Exercise 5.** A login POST has valid JSON and the right password, but lacks a CSRF token; the system uses cookies/sessions. Can it return 403?

**Answer:** Yes. CsrfFilter can reject the POST before the converter runs. JSON does not exempt a request from CSRF; a valid token is required per the application's csrf repository/handler mechanism.

**Exercise 6.** `AuthenticationManager` returns success, the success handler writes 200 JSON, yet subsequent GET /api/me always gets rejected. What should be checked?

**Answer:** Check whether the context was saved to the right SecurityContextRepository, whether the chain shares the same repository, whether the session cookie is sent/received, and whether any stateless policy discards persistence.

**Exercise 7.** Why does the body limit use `readNBytes(limit + 1)` instead of just inspecting Content-Length?

**Answer:** Content-Length may be absent or the request may use chunked transfer; reading up to limit+1 bytes detects oversized payloads without buffering the entire body in RAM.

**Exercise 8.** A custom filter logs the request body before AuthenticationFilter, causing the converter to always receive empty input. Does the problem lie in AuthenticationManager?

**Answer:** No. The Servlet body stream was already consumed before the converter read it. Design logging not to record credentials and control wrappers/filter ordering; do not modify PasswordEncoder to handle stream errors.

**Exercise 9.** A user logs in via JSON and the application wants to issue a Bearer token for a SPA. Is it AuthenticationConverter's job to issue/sign JWTs?

**Answer:** No. The converter only turns the request into an Authentication request. Token issuance, expiry, revocation, key protection, and resource server validation are separate components/processes.

**Exercise 10.** Why is `@WithMockUser` insufficient to test the converter?

**Answer:** That annotation injects a pre-built Authentication into the test, bypassing body parsing and provider credential verification. You must send a real JSON POST through MockMvc and verify status, errors, and SecurityContext/session.

## 13. Pre-Production Checklist for JSON Login

- [ ] Confirm the **right SecurityFilterChain** and `RequestMatcher` for POST login, without blocking or accidentally matching other endpoints.
- [ ] Converter only parses requests and returns an **unauthenticated Authentication**, never reading roles/authorities from the client.
- [ ] Bound Content-Type, body size, username/password lengths; validate JSON schema, and read the input stream once.
- [ ] Use a trusted `AuthenticationManager`/provider and appropriate `PasswordEncoder`; never compare passwords manually.
- [ ] Design 400/401/413/415/503 responses and messages that do not leak usernames or credentials.
- [ ] If using **session cookies**, keep CSRF protection, session fixation controls, logout, cookie flags, and repository persistence consistent.
- [ ] If choosing **stateless tokens**, separately design token issuance, key rotation, TTL, validation, and revocation; do not assume JSON implies stateless.
- [ ] Never log request bodies, passwords, hashes, session IDs, or Authentications containing credentials.
- [ ] Rate limiting, abuse monitoring, MFA, and security auditing belong to a broader policy layer than the converter.
- [ ] Test valid JSON, wrong password, invalid JSON, unknown fields, oversized bodies, CSRF, follow-up session requests, and multiple security chains.
- [ ] Account for API/constructor differences across Spring Security 6.x versions; lock and test against the actual target version.

**Remember:** `AuthenticationConverter` is the **translation gate from HTTP JSON to an untrusted Authentication request**; `AuthenticationFilter` coordinates the matcher, AuthenticationManager, and handlers to complete the login flow. Keeping this boundary clear lets the system support JSON frontends while reusing Spring Security's password verification, authorization, and SecurityContext lifecycle.