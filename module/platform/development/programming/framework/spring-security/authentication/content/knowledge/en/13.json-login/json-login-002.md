# Reading username and password from JSON with AuthenticationConverter in Spring Security

## 1. The Problem: JSON Login in a Servlet Application

When building a REST API or a frontend sending data via `fetch`/Axios, login credentials often reside in the **JSON HTTP request body** instead of form-urlencoded:

~~~http
POST /api/login HTTP/1.1
Host: localhost:8080
Content-Type: application/json
X-CSRF-TOKEN: <session-csrf-token>
Cookie: JSESSIONID=<session-cookie>

{"username":"student","password":"demo-password"}
~~~

The goal of the **data reading** step is to turn the request payload into an **unauthenticated** `Authentication`, and then hand it to `AuthenticationManager` for verification. The appropriate component in **Spring Security Servlet** is `org.springframework.security.web.authentication.AuthenticationConverter`. It can be paired with `AuthenticationFilter` to handle login POSTs.

Make sure to distinguish immediately:
- `AuthenticationConverter` **extracts, validates input structure**, and builds the authentication request. It **does not match the password** against the database, **does not encode passwords**, **does not issue JWTs**, and **does not save the session itself**.
- `AuthenticationManager` delegates the authentication request to an appropriate provider, such as `DaoAuthenticationProvider` using `UserDetailsService` and `PasswordEncoder`.
- `AuthenticationFilter` coordinates the matcher, converter, manager, success/failure handlers, and `SecurityContext` persistence.
- For JSON sent to the `SecurityFilterChain`, Spring MVC's `@RequestBody`/`HttpMessageConverter` **does not automatically apply to authentication filters**. If you choose the `@RestController` approach, you can use `@RequestBody`, but the implementer must explicitly handle authentication, `SecurityContext`, and the post-login session.

This hands-on lesson uses **Java 17+, Spring Boot 3.x, Spring Security 6.x, Servlet MVC, and session cookies**. A successful login returns JSON rather than redirecting. Sessions/cookies are a separate architectural choice; if you want JWT or stateless authentication, you need to build an independent token-issuing and verification flow.

## 2. How Does Spring Security Handle a JSON Login?

~~~text
POST /api/login, Content-Type: application/json
              |
              v
       SecurityFilterChain
       (CsrfFilter checks CSRF when using session cookies)
              |
              v
  AuthenticationFilter: do URL + HTTP method match?
              |
              v
  JsonLoginAuthenticationConverter.convert(request)
       - check Content-Type
       - read request.getInputStream() exactly once
       - Jackson maps JSON -> LoginJson
       - validate username/password
              |
              v
  UsernamePasswordAuthenticationToken.unauthenticated(...)
              |
              v
  AuthenticationManager (ProviderManager)
              |
              v
  DaoAuthenticationProvider
       UserDetailsService + PasswordEncoder
              |
        +-----+-----+
        |           |
     failure     success
        |           |
        v           v
  FailureHandler  SecurityContextHolder / SecurityContextRepository
        |           |
        v           v
   400/401/415   SuccessHandler: update session/CSRF, return 200 JSON
~~~

Use `UsernamePasswordAuthenticationToken.unauthenticated(username, password)` to signify that the credentials were just supplied by the client and have **not yet been verified**. Never construct a token with `authenticated=true` merely because the JSON is valid.

The `AuthenticationConverter` interface:

~~~java
public interface AuthenticationConverter {
    Authentication convert(HttpServletRequest request);
}
~~~

This method can:
- Return an unauthenticated `Authentication` if the request is valid.
- Return `null` when the converter cannot handle the request according to the designed protocol; for a login endpoint that already matched the matcher but has a bad body, it is usually better to throw a clear input error so the request does not fall through to another filter/controller.
- Throw an `AuthenticationException` if syntax or authentication data is invalid; the failure handler will decide the HTTP status and error body.

`AuthenticationConverter` differs from Spring Core's `Converter<String, ...>` and Spring MVC's `HttpMessageConverter`. In WebFlux, the corresponding API is `ServerAuthenticationConverter`, which receives `ServerWebExchange`; do not directly use the Servlet example below in a reactive application.

## 3. Ways to Extract username/password: Choosing the Right Layer

| Component | Typical data source | When to use |
| --- | --- | --- |
| Default `UsernamePasswordAuthenticationFilter` | `request.getParameter("username")` and `getParameter("password")`, usually from form-urlencoded | Traditional HTML form login |
| `AuthenticationConverter` + `AuthenticationFilter` | Reads `HttpServletRequest` and creates a custom `Authentication` | JSON login endpoint running through the Spring Security filter chain |
| Spring MVC `@RequestBody LoginRequest` | Jackson parses JSON after reaching the controller | Login API implemented in a controller, responsible for its own authentication/context persistence |
| `ServerAuthenticationConverter` + `AuthenticationWebFilter` | Reads `ServerWebExchange` (reactive) | Spring Security WebFlux |

Simply changing `usernameParameter`/`passwordParameter` in form login configuration **does not** make the default `UsernamePasswordAuthenticationFilter` parse JSON automatically. `request.getParameter` is not the API for reading two properties from a JSON body. Avoid reading `HttpServletRequest.getInputStream()` across multiple filters; the body can usually be read only once unless a proper caching wrapper is used.

## 4. Complete Example: JSON Converter + AuthenticationFilter + Session

The following example uses an in-memory account for learning while presenting the minimal parts of a **JSON login with a session usable on subsequent requests**.

Create a Spring Boot 3.5 / Spring Security 6.5 project with Java 17 and these Maven dependencies:

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

Keep the parent/BOM and build plugins generated by Spring Initializr. This is a **dependencies snippet** to add to a Boot project, not a standalone `pom.xml` file.

File `src/main/java/com/example/jsonlogin/JsonLoginApplication.java`:

~~~java
package com.example.jsonlogin;

import java.io.IOException;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationConverter;
import org.springframework.security.web.authentication.AuthenticationFilter;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.CompositeSessionAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfAuthenticationStrategy;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.security.web.savedrequest.NullRequestCache;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class JsonLoginApplication {

    public static void main(String[] args) {
        SpringApplication.run(JsonLoginApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        // For illustration only; real apps use an appropriate user store.
        return new InMemoryUserDetailsManager(
            User.withUsername("student")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider = new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(provider);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationManager authenticationManager,
            ObjectMapper objectMapper) throws Exception {

        // Repository used both to SAVE after login
        // and to LOAD on subsequent session-based requests.
        SecurityContextRepository contextRepository =
            new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository()
            );

        // Because cookie/session is used, POST login still needs a CSRF token.
        CsrfTokenRepository csrfRepository = new HttpSessionCsrfTokenRepository();

        AuthenticationFilter jsonLoginFilter = new AuthenticationFilter(
            authenticationManager,
            new JsonLoginAuthenticationConverter(objectMapper)
        );

        // Only handle POST /api/login; GET /api/me does not read JSON login.
        jsonLoginFilter.setRequestMatcher(
            new AntPathRequestMatcher("/api/login", "POST")
        );

        // AuthenticationFilter does not save the context automatically unless configured.
        jsonLoginFilter.setSecurityContextRepository(contextRepository);

        // AuthenticationFilter has no SessionAuthenticationStrategy setter.
        // The demo invokes the appropriate strategies when authentication succeeds:
        SessionAuthenticationStrategy onLogin = new CompositeSessionAuthenticationStrategy(
            List.of(
                new ChangeSessionIdAuthenticationStrategy(),
                new CsrfAuthenticationStrategy(csrfRepository)
            )
        );

        jsonLoginFilter.setSuccessHandler((request, response, authentication) -> {
            onLogin.onAuthentication(authentication, request, response);
            response.setStatus(HttpServletResponse.SC_OK);
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.getWriter().write("{\"status\":\"ok\"}");
        });

        jsonLoginFilter.setFailureHandler((request, response, failure) -> {
            int status = (failure instanceof InvalidLoginRequest bad)
                ? bad.httpStatus()
                : HttpServletResponse.SC_UNAUTHORIZED;
            // Do not disclose the password or whether the username does not exist.
            response.setStatus(status);
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.getWriter().write("{\"error\":\"login_failed\"}");
        });

        http
            .csrf(csrf -> csrf.csrfTokenRepository(csrfRepository))
            .securityContext(security ->
                security.securityContextRepository(contextRepository))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers(HttpMethod.POST, "/api/login").permitAll()
                .anyRequest().authenticated()
            )
            .exceptionHandling(ex -> ex.authenticationEntryPoint(
                (request, response, reason) ->
                    response.sendError(HttpServletResponse.SC_UNAUTHORIZED)
            ))
            .requestCache(cache -> cache.requestCache(new NullRequestCache()))
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            // Register the filter at the default login filter position in the filter chain.
            .addFilterAt(jsonLoginFilter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }

    // JSON contract: {"username":"...","password":"..."}
    public record LoginJson(String username, String password) {
    }

    static final class JsonLoginAuthenticationConverter implements AuthenticationConverter {
        private final ObjectMapper objectMapper;

        JsonLoginAuthenticationConverter(ObjectMapper objectMapper) {
            this.objectMapper = objectMapper;
        }

        @Override
        public Authentication convert(HttpServletRequest request) {
            String rawType = request.getContentType();
            if (rawType == null) {
                throw new InvalidLoginRequest(415, "Content-Type required");
            }

            MediaType type;
            try {
                type = MediaType.parseMediaType(rawType);
            } catch (IllegalArgumentException ex) {
                throw new InvalidLoginRequest(415, "Unsupported Content-Type", ex);
            }
            if (!MediaType.APPLICATION_JSON.isCompatibleWith(type)) {
                throw new InvalidLoginRequest(415, "Expected application/json");
            }

            LoginJson credentials;
            try {
                credentials = objectMapper.readerFor(LoginJson.class)
                    .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
                    .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
                    .readValue(request.getInputStream());
            } catch (IOException ex) {
                throw new InvalidLoginRequest(400, "Malformed login JSON", ex);
            }

            if (credentials == null
                    || credentials.username() == null
                    || credentials.username().isBlank()
                    || credentials.username().length() > 128
                    || credentials.password() == null
                    || credentials.password().isEmpty()
                    || credentials.password().length() > 1024) {
                throw new InvalidLoginRequest(400, "Missing or invalid credentials");
            }

            // NEVER create an authenticated=true token here.
            // Do not trim or modify the password; keep it intact for PasswordEncoder matching.
            return UsernamePasswordAuthenticationToken.unauthenticated(
                credentials.username(), credentials.password()
            );
        }
    }

    static final class InvalidLoginRequest extends AuthenticationException {
        private final int httpStatus;

        InvalidLoginRequest(int httpStatus, String message) {
            super(message);
            this.httpStatus = httpStatus;
        }

        InvalidLoginRequest(int httpStatus, String message, Throwable cause) {
            super(message, cause);
            this.httpStatus = httpStatus;
        }

        int httpStatus() {
            return httpStatus;
        }
    }

    @RestController
    static class ApiController {

        @GetMapping("/api/csrf")
        Map<String, String> csrf(HttpServletRequest request) {
            // CsrfFilter puts the CsrfToken into a request attribute.
            CsrfToken token = (CsrfToken) request.getAttribute(
                CsrfToken.class.getName()
            );
            return Map.of(
                "headerName", token.getHeaderName(),
                "token", token.getToken()
            );
        }

        @GetMapping("/api/me")
        Map<String, String> me(Authentication authentication) {
            return Map.of("username", authentication.getName());
        }
    }
}
~~~

### Analyzing Key Points in the Example

**1. The converter only accepts structurally valid input.** `MediaType.parseMediaType` handles `application/json` with a `charset` parameter. Jackson reads the request stream, maps the exact two fields of the record, and rejects undeclared JSON fields and trailing JSON tokens. If values are missing or the body is malformed, the converter throws `InvalidLoginRequest`; the failure handler returns 400. A non-JSON media type returns 415.

**2. The unauthenticated token goes to the manager.** There `DaoAuthenticationProvider` retrieves the encoded password from `UserDetailsService` and uses `BCryptPasswordEncoder` to match it. The client cannot send or choose an `authenticated` flag or a list of authorities. The message for wrong username/password is intentionally identical, returning 401.

**3. The matcher bounds the processing scope.** `AuthenticationFilter` only runs the converter on `POST /api/login`. JSON login must not "accidentally" read from every request. `.addFilterAt(...)` uses a position known to Spring Security; the filter is created locally inside `SecurityFilterChain`, avoiding registering an extra servlet filter outside the security chain via `@Bean`.

**4. Sessions require two-sided configuration.** `AuthenticationFilter` can place the result into `SecurityContextHolder` for the current request; so that the next request restores the session, pass the same `SecurityContextRepository` to the filter (for saving) and configure `HttpSecurity.securityContext` (for loading). The example uses `DelegatingSecurityContextRepository` combining request attributes and the HTTP session.

**5. Session fixation and CSRF do not disappear when switching to JSON.** Because the example uses cookies/sessions, `CsrfFilter` remains enabled. `ChangeSessionIdAuthenticationStrategy` rotates the session ID after authentication; `CsrfAuthenticationStrategy` clears the old CSRF token so a new token is issued in the next flow. In Spring Security 6.x's `AuthenticationFilter`, these strategies are called inside the example's success handler; if you use another custom filter, configure its lifecycle properly. After login, the frontend must fetch a new CSRF token before the next POST.

**6. A 200 response is not a JWT.** The JSON `{"status":"ok"}` only indicates that authentication succeeded; the application continues recognizing the user via the session cookie. Without keeping the cookie, a subsequent `GET /api/me` returns 401. To achieve stateless JWTs, you need to add token-issuing, signing, expiration, and resource-server token validation; never assume JSON login automatically produces a JWT.

**7. Sample code is scoped for learning.** In-memory user/password, missing rate limiting, monitoring, MFA, multi-session management, and business length policies. A real app must replace this with a user store/identity provider, environment-appropriate cookie configuration (Secure/HttpOnly/SameSite), HTTPS, and brute-force protection. If designing concurrent session control, use `SessionRegistry` and the corresponding strategies consistently, rather than just adding `maximumSessions` and assuming the filter picks it up automatically.

## 5. Manual Testing from a Client

Run the Maven wrapper in the project directory:

~~~bash
./mvnw spring-boot:run
~~~

Windows: `mvnw.cmd spring-boot:run`. Because this is a Spring Boot app with dependencies, do not run `javac JsonLoginApplication.java` standalone.

First fetch the session cookie and CSRF token:

~~~bash
curl -i -c cookies.txt http://localhost:8080/api/csrf
~~~

Example response **shape** (the token and cookie change every time):

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"headerName":"X-CSRF-TOKEN","token":"<issued-token>"}
~~~

Next, using the **actual token value** just received, send it along with the cookie, not the literal placeholder:

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  -H 'Content-Type: application/json' \
  -H 'X-CSRF-TOKEN: <issued-token>' \
  -d '{"username":"student","password":"demo-password"}' \
  http://localhost:8080/api/login
~~~

Expected `200 OK` and body:

~~~json
{"status":"ok"}
~~~

Use the updated session cookie after login:

~~~bash
curl -i -b cookies.txt http://localhost:8080/api/me
~~~

Expected `200 OK` and body:

~~~json
{"username":"student"}
~~~

Trying a wrong password with a valid CSRF token returns `401 Unauthorized`. If the CSRF token is missing on the login POST, `CsrfFilter` blocks before the converter and returns `403 Forbidden`. If `Content-Type` is `text/plain` with a valid CSRF token, it returns `415 Unsupported Media Type`. Sending malformed JSON or missing fields returns `400 Bad Request`. After a successful login, the old CSRF token is cleared; before a state-changing POST, call `GET /api/csrf` again to obtain a new token.

For a browser frontend, you must retain cookies on same-origin requests (or configure `credentials`/CORS/SameSite appropriately in multi-origin designs). **Never** store passwords in localStorage, request logs, URLs/query strings, or error messages.

## 6. Testing with Spring Security Test and MockMvc

In the same project, file `src/test/java/com/example/jsonlogin/JsonLoginApplicationTests.java`:

~~~java
package com.example.jsonlogin;

import jakarta.servlet.http.HttpSession;
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
class JsonLoginApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void loginJsonSucceedsAndIsRememberedBySession() throws Exception {
        MvcResult result = mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"student\",\"password\":\"demo-password\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"))
            .andReturn();

        HttpSession session = result.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/api/me").session((MockHttpSession) session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("student"));
    }

    @Test
    void wrongPasswordIsRejected() throws Exception {
        mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"student\",\"password\":\"wrong\"}"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("login_failed"));
    }

    @Test
    void malformedJsonIsBadRequest() throws Exception {
        mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void missingPasswordIsBadRequest() throws Exception {
        mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"student\"}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void formEncodedInputIsNotAcceptedAsJsonLogin() throws Exception {
        mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("username", "student")
                .param("password", "demo-password"))
            .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void missingCsrfIsForbiddenBeforeAuthentication() throws Exception {
        mvc.perform(post("/api/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"student\",\"password\":\"demo-password\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void protectedResourceNeedsAuthentication() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Run:

~~~bash
./mvnw test
~~~

**Expected when environment and dependencies are configured properly:** the tests pass. Passing tests verify three separate things: JSON parsing, provider authentication, and restoring authentication via the session. These are sample integration tests that need to be **executed in a real project**; reading documentation does not replace running tests. CSRF and failed-login tests ensure there is no bypass branch when the converter receives invalid requests.

If the application has multiple `SecurityFilterChain` beans, verify that the right chain receives `/api/login`; an overly narrow `securityMatcher` can prevent the filter-backed endpoint from ever running.

## 7. Common Mistakes When Reading JSON Login

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Using `request.getParameter("username")` with a JSON body | Returns null or fails to read credentials | Use Jackson to read `getInputStream()` in `AuthenticationConverter` |
| Assuming `@RequestBody` runs inside `AuthenticationFilter` | The filter runs before the Spring MVC controller | Use a converter for filters; `@RequestBody` is only for MVC handlers |
| Creating `UsernamePasswordAuthenticationToken` in the authenticated state | Unverified client is treated as logged in | Call `unauthenticated(username,password)` then `AuthenticationManager.authenticate` |
| Having the converter query the DB and compare passwords with `equals` | Bypasses the provider/encoder mechanism and is hard to audit | Only build the token; delegate verification to `DaoAuthenticationProvider` and `PasswordEncoder` |
| Omitting `setRequestMatcher` | AuthenticationFilter may be applied too broadly | Match only the login method/path |
| Reading the body in multiple filters then parsing again | The InputStream is already consumed | Read in only one place, or use a controlled caching wrapper |
| Not distinguishing JSON errors from wrong passwords | Hard to operate the API; may leak user information | 400/415 for invalid structure/media type, generic 401 for wrong credentials |
| Not saving `SecurityContext` after authentication | Subsequent requests revert to 401 even though login returned 200 | Configure `SecurityContextRepository` for both saving and loading |
| Using session cookies while globally disabling CSRF | Opens a CSRF surface on the API | Keep CSRF tokens, control CORS/cookies, and rotate tokens on login |
| Ignoring session fixation and session control | Increases risk when reusing an existing session | Use an appropriate session strategy; apply concurrency policy if needed |
| Logging the entire JSON login payload | Leaks passwords | Redact credentials; log safe status and metadata |
| Treating JWT as an automatic result of JSON login | Frontend assumes it has a token while the server only created a session | Clearly design session-based and token-based as two distinct flows |

## 8. Hardening for Production

- **Input limits:** constrain HTTP body size at the proxy/servlet container; enforce product-specific username/password length bounds; reject extra JSON fields or malformed structures; never read unboundedly from the request.
- **Preserve passwords verbatim:** do not call `trim()`, lowercase, or Unicode-normalize passwords before comparison unless your product protocol has a documented, consistent rule. Do not print exceptions/causes containing raw bodies to logs.
- **HTTPS and cookies:** use HTTPS, `HttpOnly` and `Secure` cookies in production, `SameSite` matched to your threat model, and an exact CORS allowlist; do not allow arbitrary origins to send credentials.
- **Brute-force protection:** rate-limit by account/IP according to appropriate rules, with monitoring and alerting; consider MFA for sensitive accounts; do not distinguish "user does not exist" from "wrong password" in public responses.
- **Architecture-matched CSRF:** if the frontend uses session cookies (automatically attached), keep CSRF enabled. If the API is purely stateless using Bearer tokens in headers with no cookies acting as credentials, the CSRF policy may differ; evaluate all auth mechanisms before disabling it.
- **Do not conflate with authorization:** login only verifies identity; every endpoint still needs `authorizeHttpRequests` or method security. Never trust `roles` or `isAdmin` fields sent by the client.
- **End-to-end testing:** test Content-Type, JSON null, JSON arrays, missing/extra fields, encoding, oversized requests, wrong passwords, CSRF, session fixation, post-login cookies, session expiration, and logout.
- **Library versions:** example APIs target Spring Security 6.x. When upgrading to Spring Security 7.x, re-check matchers and authentication/session APIs against the corresponding version's documentation.

## 9. Self-Check Questions

1. Why does the default `UsernamePasswordAuthenticationFilter` usually fail to read `{"username":"..."}` from an HTTP JSON body?
2. In `AuthenticationConverter`, why must you return `UsernamePasswordAuthenticationToken.unauthenticated`?
3. At which step does `AuthenticationConverter` differ from `DaoAuthenticationProvider`?
4. Why is a 200 response from JSON login not enough to prove the next request is logged in?
5. If session cookies are used, why might `POST /api/login` still require a CSRF token?
6. When is using `@RequestBody` in a controller appropriate, and what extra step is required to persist `SecurityContext`?
7. Why should you not register the same `AuthenticationFilter` both as a standalone servlet filter and as a filter inside Spring Security?

## 10. References

1. Spring Security 6.5 — Servlet authentication architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
2. Spring Security 6.5 API — `AuthenticationConverter`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AuthenticationConverter.html
3. Spring Security 6.5 API — `AuthenticationFilter`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AuthenticationFilter.html
4. Spring Security 6.5 — Username/password authentication and `DaoAuthenticationProvider`: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/
5. Spring Security 6.5 — Session management / context persistence: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
6. Spring Security 6.5 — CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
7. Spring Security — Testing with MockMvc: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html

**Remember:** When a login endpoint accepts JSON inside the **Servlet SecurityFilterChain**, place request parsing in `AuthenticationConverter`, send an **unauthenticated** token to `AuthenticationManager`, and explicitly configure success/failure, SecurityContext, session, and CSRF according to the chosen authentication mechanism.