# Restricting HTTP Method, Content-Type, and Input Payload Size for JSON Login

> Scope: **Spring Security - authentication -> JSON Login**, **Spring Boot 3.x / Spring Security 6.x on Servlet**, Java 17+. This guide rejects login requests with the wrong method, wrong media type, or oversized payload *before* processing credentials. The example demonstrates a stateful `POST /api/login` endpoint with CSRF protection. Do not apply this session policy directly to WebFlux, JWT/bearer tokens, or OAuth2.

## 1. Input Contract: Define Before Writing Code

JSON login must have an explicit HTTP contract:

| Condition | Accepted value | Expected error |
| --- | --- | --- |
| Path | `/api/login` | Other paths must not be treated as the login endpoint |
| HTTP method | **`POST` only** | `405 Method Not Allowed` and header `Allow: POST` |
| Media type | `application/json` or `application/json; charset=UTF-8` | `415 Unsupported Media Type` if `Content-Type` is missing/wrong |
| Content-Encoding | Uncompressed or `identity` | `415` for other encodings in the example contract |
| Body size | **At most 8192 UTF-8 bytes (8 KiB)** | `413 Content Too Large` / `Payload Too Large` |
| JSON structure | Object with valid `username` and `password` | `400 Bad Request` |
| Credentials | Correct account and password | `401 Unauthorized` if authentication fails |
| CSRF for login using session cookies | Valid CSRF token | `403 Forbidden` if token is missing/invalid |
| Success | Valid body, CSRF, and credentials | `204 No Content` |

The **8192-byte threshold is an illustrative choice**, not a Spring Security default limit. Choose a threshold based on real payloads and update it consistently across gateway, app, and tests.

**Important distinction:** `Content-Type` describes the request body format declared by the client; only the JSON parser validates JSON syntax. `Accept` specifies the desired **response** format and does not replace `Content-Type`. `Content-Length` is the byte count declared by the client, not guaranteed proof of the payload size the app actually receives.

Why use POST only? Username/password in `GET` URLs easily leak into browser history, logs, analytics, proxies, and telemetry. GET also carries read semantics and is prone to unintended prefetching/caching/crawling. Neither POST nor JSON encrypts the wire: **HTTPS is still mandatory** when transmitting credentials.

## 2. At Which Layers Are Constraints Enforced?

In Spring MVC, `@PostMapping(path="/api/login", consumes="application/json")` enforces **method** and **media type**. It **does not automatically limit the number of bytes read from the HTTP request**. If an application uses `@RequestBody String` or `@RequestBody byte[]` and checks `length` afterward, MVC may have already allocated memory and read an oversized body before blocking it.

A proper model for synchronous Servlet MVC:

```text
Client
  |
  v
Gateway / reverse proxy / Servlet container
  | infrastructure-side body limits, timeouts, connection caps
  v
Spring Security filter chain
  |
  v
JsonLoginRequestGuardFilter
  |-- method other than POST ----------------> 405 + Allow: POST
  |-- wrong Content-Type or encoding --------> 415
  |-- Content-Length >8192 ------------------> 413 immediately
  |-- read at most 8193 bytes from stream
  |    '-- if 8193rd byte is seen -----------> 413
  |-- pass exact body <=8192 bytes onward
  v
CsrfFilter ----------------------------------> 403 if CSRF is invalid
  v
Spring MVC / Jackson ------------------------> 400 if JSON is invalid
  v
AuthenticationManager ----------------------> 401 if credentials are wrong
  |-- success: save SecurityContext
  '-- response ------------------------------> 204
```

In the example, the guard runs **before `CsrfFilter`**. Consequently, requests with the wrong method/media/size receive the guard's status code before CSRF is checked. If you order filters differently, a request missing a token might get `403` before reaching `415`; choose the order deliberately and test it.

**Two-step size checking is mandatory:** reject early when `Content-Length` already exceeds the threshold and **count actual bytes read** with a `MAX+1` limit. Chunked bodies may omit `Content-Length`. Java character count (`String.length()`) is not equivalent to UTF-8 byte count: Vietnamese diacritics or emojis often require multiple bytes.

## 3. Runnable Spring Boot / Spring Security Example

In a **Spring Boot 3.x** project already configured with the Gradle plugin and Java 17+, add:

```groovy
// build.gradle - dependencies section
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Create the files under the same package `example.jsonlogin`.

### 3.1. Application Entry Point

**`src/main/java/example/jsonlogin/JsonLoginApplication.java`**

```java
package example.jsonlogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonLoginApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonLoginApplication.class, args);
    }
}
```

### 3.2. SecurityFilterChain Configuration

**`src/main/java/example/jsonlogin/SecurityConfig.java`**

```java
package example.jsonlogin;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfFilter;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    AuthenticationManager authenticationManager(
            AuthenticationConfiguration config) throws Exception {
        return config.getAuthenticationManager();
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            SecurityContextRepository repository) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/login").permitAll()
                .anyRequest().authenticated()
            )
            .csrf(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .securityContext(context -> context
                .securityContextRepository(repository))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .addFilterBefore(new JsonLoginRequestGuardFilter(), CsrfFilter.class);

        return http.build();
    }
}
```

This configuration disables default form login because a dedicated controller will accept JSON. It **keeps CSRF enabled**, since authentication uses session cookies. `JsonLoginRequestGuardFilter` is registered **once** via `addFilterBefore`; do not simultaneously add `@Component` or a `FilterRegistrationBean` for the same filter. The demo uses BCrypt to hash the in-memory password; demo credentials must never be used in production.

### 3.3. Filter Checking Method, Content-Type, and Actual Bytes Read

**`src/main/java/example/jsonlogin/JsonLoginRequestGuardFilter.java`**

```java
package example.jsonlogin;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ReadListener;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletInputStream;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletRequestWrapper;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.MediaType;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

final class JsonLoginRequestGuardFilter extends OncePerRequestFilter {
    static final int MAX_BODY_BYTES = 8192;

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String relativePath = request.getRequestURI()
                .substring(request.getContextPath().length());
        return !"/api/login".equals(relativePath);
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        if (!"POST".equals(request.getMethod())) {
            response.setHeader("Allow", "POST");
            response.sendError(405);
            return;
        }

        if (!isUtf8Json(request.getContentType()) ||
                !isIdentityEncoding(request.getHeader("Content-Encoding"))) {
            response.sendError(415);
            return;
        }

        // Reject early if the client already declared a size exceeding the threshold.
        if (request.getContentLengthLong() > MAX_BODY_BYTES) {
            response.sendError(413);
            return;
        }

        // Enforce limit by actual bytes read, even when Content-Length is absent.
        // MAX+1 reads just one extra byte to detect whether the threshold is exceeded.
        byte[] body = request.getInputStream().readNBytes(MAX_BODY_BYTES + 1);
        if (body.length > MAX_BODY_BYTES) {
            response.sendError(413);
            return;
        }

        // Original stream was consumed: wrap it so Jackson can read the body properly.
        chain.doFilter(new BufferedRequest(request, body), response);
    }

    private static boolean isUtf8Json(String header) {
        if (header == null) {
            return false;
        }
        try {
            MediaType type = MediaType.parseMediaType(header);
            return "application".equalsIgnoreCase(type.getType())
                    && "json".equalsIgnoreCase(type.getSubtype())
                    && (type.getCharset() == null
                    || StandardCharsets.UTF_8.equals(type.getCharset()));
        } catch (IllegalArgumentException ex) {
            return false;
        }
    }

    private static boolean isIdentityEncoding(String encoding) {
        return encoding == null || "identity".equalsIgnoreCase(encoding.trim());
    }

    // Illustrative for synchronous Servlet MVC; do not use as an async wrapper.
    private static final class BufferedRequest extends HttpServletRequestWrapper {
        private final byte[] body;

        BufferedRequest(HttpServletRequest request, byte[] body) {
            super(request);
            this.body = body;
        }

        @Override
        public int getContentLength() {
            return body.length;
        }

        @Override
        public long getContentLengthLong() {
            return body.length;
        }

        @Override
        public ServletInputStream getInputStream() {
            ByteArrayInputStream input = new ByteArrayInputStream(body);
            return new ServletInputStream() {
                @Override
                public int read() {
                    return input.read();
                }

                @Override
                public boolean isFinished() {
                    return input.available() == 0;
                }

                @Override
                public boolean isReady() {
                    return true;
                }

                @Override
                public void setReadListener(ReadListener listener) {
                    throw new UnsupportedOperationException(
                        "Only synchronous Servlet reads are supported");
                }
            };
        }

        @Override
        public BufferedReader getReader() {
            return new BufferedReader(new InputStreamReader(
                getInputStream(), StandardCharsets.UTF_8));
        }
    }
}
```

**Explanation of key safeguards:**

- `"POST".equals(request.getMethod())` rejects other methods before the request reaches authentication logic; returns `Allow: POST` per the `405` contract.
- `MediaType.parseMediaType` parses the media type and parameters instead of doing a literal string match on `"application/json"` (which would wrongly reject `application/json;charset=UTF-8`). The example intentionally **rejects** `text/plain`, `application/x-www-form-urlencoded`, `application/problem+json`, or non-UTF-8 charsets.
- Restricting `Content-Encoding` in the demo avoids confusing compressed byte counts with the JSON body. If an application actually decompresses requests, it must enforce the **post-decompression size limit** at the exact layer performing decompression.
- `getContentLengthLong()` enables fast rejection of declared large bodies; `readNBytes(8193)` protects when the header is missing or lower than what the Servlet delivers. The filter **never reads the entire request unboundedly**.
- The wrapper preserves the verified `byte[]` so Jackson still sees the body. If a filter reads the stream and then calls `chain.doFilter(request, response)` with the original request, the controller may see EOF.
- The example handles **sync Servlet**. With async/non-blocking I/O you need a protocol-compliant `ReadListener` wrapper, or a dedicated ingress/stream-limiting solution. `setReadListener` throws an exception in this illustration to avoid pretending to support async.

**Verify URL consistency:** `shouldNotFilter` compares against the URI stripped of context path. If proxy rewrites, trailing slashes, matrix parameters, URL encoding, or method overrides cause MVC to treat another URL as the login endpoint, normalize/reject those variants or align the matcher with the router. Never let any URL reach the login controller while bypassing the size guard.

### 3.4. Controller Authenticating After Passing the Filter

**`src/main/java/example/jsonlogin/JsonLoginController.java`**

```java
package example.jsonlogin;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class JsonLoginController {
    private final AuthenticationManager manager;
    private final SecurityContextRepository repository;
    private final SessionAuthenticationStrategy sessionStrategy =
            new ChangeSessionIdAuthenticationStrategy();

    public JsonLoginController(AuthenticationManager manager,
                               SecurityContextRepository repository) {
        this.manager = manager;
        this.repository = repository;
    }

    public record LoginPayload(String username, String password) {}

    @PostMapping(path = "/login", consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Void> login(@RequestBody LoginPayload payload,
                                      HttpServletRequest request,
                                      HttpServletResponse response) {
        if (payload == null
                || payload.username() == null
                || payload.password() == null
                || payload.username().isBlank()
                || payload.password().isBlank()
                || payload.username().length() > 128
                || payload.password().length() > 1024) {
            return ResponseEntity.badRequest().build();
        }

        Authentication authenticated;
        try {
            authenticated = manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    payload.username(), payload.password()));
        } catch (AuthenticationException ex) {
            // Do not reveal whether the username or password was wrong.
            SecurityContextHolder.clearContext();
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
        }

        // With a custom controller, apply the session strategy and save the context.
        sessionStrategy.onAuthentication(authenticated, request, response);
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authenticated);
        SecurityContextHolder.setContext(context);
        repository.saveContext(context, request, response);
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/me")
    public String me(Authentication authentication) {
        return authentication.getName();
    }
}
```

`@PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)` is a second constraint at MVC; `@RequestBody` only parses after the guard has bounded bytes. The controller checks null/blank and per-field lengths, an **independent validation layer** from the overall size cap.

Because this is a custom stateful login in Spring Security 6, the illustrative code explicitly calls `SessionAuthenticationStrategy` and `SecurityContextRepository.saveContext`. Production must account for the full CSRF token lifecycle, login/logout, session fixation, session concurrency, auditing, and standard authentication hooks; do not claim this minimal controller covers a complete session management policy.

## 4. Testing with MockMvc

The following tests use the **real Spring Security filter chain**: do not use `@WithMockUser` to simulate being logged in, as doing so would not test the JSON credential-receiving flow.

**`src/test/java/com/example/jsonlogin/JsonLoginBoundaryTest.java`**

```java
package example.jsonlogin;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.nio.charset.StandardCharsets;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class JsonLoginBoundaryTest {
    @Autowired
    MockMvc mvc;

    private static final String VALID_JSON =
        "{\"username\":\"alice\",\"password\":\"demo-pass\"}";

    @Test
    void wrongMethodsReturn405AndAllowHeader() throws Exception {
        mvc.perform(get("/api/login"))
            .andExpect(status().is(405))
            .andExpect(header().string("Allow", "POST"));

        mvc.perform(put("/api/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID_JSON))
            .andExpect(status().is(405))
            .andExpect(header().string("Allow", "POST"));

        mvc.perform(delete("/api/login"))
            .andExpect(status().is(405));
    }

    @Test
    void missingOrWrongContentTypeReturns415() throws Exception {
        mvc.perform(post("/api/login")
                .with(csrf().asHeader())
                .content(VALID_JSON))
            .andExpect(status().is(415));

        mvc.perform(post("/api/login")
                .with(csrf().asHeader())
                .contentType(MediaType.TEXT_PLAIN)
                .content(VALID_JSON))
            .andExpect(status().is(415));

        mvc.perform(post("/api/login")
                .with(csrf().asHeader())
                .contentType("application/json; charset=ISO-8859-1")
                .content(VALID_JSON))
            .andExpect(status().is(415));
    }

    @Test
    void unsupportedContentEncodingReturns415() throws Exception {
        mvc.perform(post("/api/login")
                .contentType(MediaType.APPLICATION_JSON)
                .header("Content-Encoding", "gzip")
                .content(VALID_JSON))
            .andExpect(status().is(415));
    }

    @Test
    void oversizedBodyReturns413() throws Exception {
        String oversized = VALID_JSON + " ".repeat(8193);

        mvc.perform(post("/api/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content(oversized))
            .andExpect(status().is(413));
    }

    @Test
    void sizeIsMeasuredInUtf8Bytes() throws Exception {
        String json = "{\"username\":\"alice\",\"password\":\"demo-pass\","
                + "\"pad\":\"" + "ộ".repeat(3000) + "\"}";
        assertTrue(json.length() < 8192);
        assertTrue(json.getBytes(StandardCharsets.UTF_8).length > 8192);

        mvc.perform(post("/api/login")
                .with(csrf().asHeader())
                .contentType(MediaType.APPLICATION_JSON)
                .content(json))
            .andExpect(status().is(413));
    }

    @Test
    void exactly8192BytesIsAccepted() throws Exception {
        int padding = 8192
                - VALID_JSON.getBytes(StandardCharsets.UTF_8).length;
        String exact = VALID_JSON + " ".repeat(padding);
        assertEquals(8192, exact.getBytes(StandardCharsets.UTF_8).length);

        mvc.perform(post("/api/login")
                .with(csrf().asHeader())
                .contentType(MediaType.APPLICATION_JSON)
                .content(exact))
            .andExpect(status().isNoContent());
    }

    @Test
    void utf8JsonWithParameterCanAuthenticateAndPersistSession()
            throws Exception {
        MvcResult result = mvc.perform(post("/api/login")
                .with(csrf().asHeader())
                .contentType("application/json; charset=UTF-8")
                .content(VALID_JSON))
            .andExpect(status().isNoContent())
            .andReturn();

        MockHttpSession session =
                (MockHttpSession) result.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void missingCsrfStillReturns403() throws Exception {
        mvc.perform(post("/api/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID_JSON))
            .andExpect(status().isForbidden());
    }

    @Test
    void badJsonIs400AndBadCredentialIs401() throws Exception {
        mvc.perform(post("/api/login")
                .with(csrf().asHeader())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{not-json"))
            .andExpect(status().isBadRequest());

        mvc.perform(post("/api/login")
                .with(csrf().asHeader())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"alice\",\"password\":\"wrong\"}"))
            .andExpect(status().isUnauthorized());
    }
}
```

Run from the **Spring Boot example project**:

```bash
./gradlew test --tests example.jsonlogin.JsonLoginBoundaryTest
./gradlew bootRun
```

On Windows use `gradlew.bat`. When successful, the class above has **9 `@Test` methods passing**. This is a **code-based expectation**, not a claim that it was executed in this environment.

### Meaning of the Assertions

- `405` proves the wrong method is rejected even when the URI is `/api/login`.
- `415` distinguishes missing/wrong `Content-Type` from malformed JSON. JSON-looking text tagged `text/plain` must still be blocked.
- `413` at the upper boundary and `204` at exactly 8192 bytes test for **off-by-one** errors. The `ộ` character test illustrates the difference between Java code units and UTF-8 bytes.
- `400` happens after passing method/media/size checks when Jackson fails to parse; `401` happens when JSON is valid but authentication fails.
- `csrf().asHeader()` is a test utility. A real web client must have a mechanism to obtain the CSRF token and send it in a header; using JSON is **not a reason to disable CSRF** with session cookies.
- The `GET /api/me` request after login uses the newly created session, verifying that the body was replayed and authentication was persisted. Observing `204` on POST alone is not enough to validate the whole flow.

**Testing limitations:** `MockMvc` does not perfectly simulate an HTTP client sending a real chunked body, slow transmission, mid-stream disconnects, Tomcat behavior, or a reverse proxy. Additional tests over a real HTTP path are needed after configuring infrastructure.

## 5. Observing Real HTTP Traffic and Responses

You can verify from DevTools Network or an HTTP client (over HTTPS), with a validly issued CSRF token and cookie.

**Valid method + Content-Type + JSON + CSRF:**

```http
POST /api/login HTTP/1.1
Host: example.test
Content-Type: application/json; charset=UTF-8
X-CSRF-TOKEN: <valid-token>
Cookie: JSESSIONID=<session-id>

{"username":"alice","password":"demo-pass"}
```

Angle-bracket placeholders are for documentation only. In practice the client computes `Content-Length` automatically. Success returns `204 No Content`; the next request sends the session cookie and `GET /api/me` has body:

```text
alice
```

**Wrong method:** `GET /api/login` returns `405`, with `Allow: POST`. **Wrong media type:** `POST /api/login` with `Content-Type: text/plain`, even if the body looks like JSON, returns `415`. **Oversized body:** a request of 8193 bytes returns `413`. When testing, use demo data and never log real passwords, active CSRF tokens, or session IDs.

## 6. Common Design Mistakes

| Insufficient approach | Why it is problematic | How to fix |
| --- | --- | --- |
| Only comparing `Content-Length <= 8192` | Chunked bodies may omit the header; stream data is not yet counted | Use the header for early rejection **and** cap actual bytes read |
| `@RequestBody String` then checking `String.length()` | MVC may have already read a huge body; Java UTF-16 code units are not UTF-8 bytes | Block before parsing; measure bytes |
| `@RequestBody byte[]` then checking | The entire body may have already been allocated before the check | Read at most `MAX+1` bytes or block at ingress |
| Only adding `@PostMapping(consumes="application/json")` | Constrains method/media, does not cap body size | Add a body guard and infrastructure limits |
| `server.tomcat.max-http-form-post-size=8KB` | Mainly applies to **form POSTs**, not a comprehensive JSON body limit | Enforce Servlet JSON body limits separately |
| `server.max-http-request-header-size` | Limits headers, not the body | Separate the body limit |
| Assuming `Content-Type: application/json` guarantees valid JSON | Header is a client claim, not a parse result | Jackson validates and returns `400` |
| Reading the stream to measure it then passing the original request onward | The stream has been consumed; Jackson hits EOF | Replay the exact bounded bytes |
| Relying only on `Accept` or a `.json` path suffix | Does not define the request body format | Validate `Content-Type` |
| Disabling CSRF because the app uses JSON | Session cookies are still sent automatically by the browser | Keep CSRF for stateful login and provide tokens properly |
| Registering the guard twice | Filter order may break and the body is read multiple times | Register exactly once |
| Blocking oversized bodies only in the application | Proxy/container may still buffer/hold huge bodies beforehand | Align limits at the gateway/ingress |
| Placing a byte limit before decompression and assuming it suffices | A small compressed body can decompress into massive data | Cap decompressed bytes at the decompression layer |

**Body limits do not replace data validation.** Even if the body is only 8 KiB, you still need null/blank checks, per-field length bounds, JSON schema checks, and field count/JSON depth limits where appropriate. In addition, you need rate limiting, login attempt monitoring, timeouts, connection caps, avoiding logging request bodies containing passwords, and proper account policies. Never use body limits as the sole defense against credential stuffing or denial-of-service.

**CORS/OPTIONS:** the pattern above is for **same-origin**. A cross-origin SPA's browser may require an `OPTIONS` preflight before `POST`. If deploying cross-origin, configure CORS at the proper layer **before the guard**, allow only necessary origins/headers/methods, handle preflight separately, and still require POST for login. Never treat OPTIONS as a login attempt and never open `Access-Control-Allow-Origin: *` for credentialed cookie requests.

**Compressed requests:** the sample rejects `Content-Encoding: gzip`. If a proxy or the app intentionally decompresses requests, apply the body limit to the **post-decompression** size and guard against decompression bombs. **Paths:** the filter's matcher must align with how MVC/ingress handles path rewrites, slashes, semicolon parameters, and URL-encoded characters so limits cannot be bypassed.

## 7. Separating Responsibilities Across Layers

```text
Gateway / reverse proxy: max body, connection count, request timeout
Servlet container: HTTP framing, parser, header limits
Spring Security filter: method/media/byte guard, CSRF, authorization
Spring MVC + Jackson: route, consumes, JSON parse, binding, validation
AuthenticationManager: identity verification and account policies
```

Limits enforced earlier by infrastructure may cause requests to receive a different status/body than the application produces. For example, `server.tomcat.max-http-form-post-size` is Tomcat's form data setting; `server.tomcat.max-swallow-size` limits how much request body is swallowed during error handling; `spring.codec.max-in-memory-size` is a setting typically associated with **WebFlux** and does not automatically protect a Servlet `@RequestBody` controller with this 8 KiB JSON limit.

With `Transfer-Encoding: chunked` or requests without Content-Length, **counting actual bytes** is mandatory. When requests are decompressed by infrastructure, clearly define which layer is responsible for bounding the final byte count consumed by the application. In production systems, prefer bounding the body close to the network edge to avoid wasting bandwidth/connections before the request reaches Java code.

## 8. Completion Checklist

- [ ] `POST /api/login` is the only method for login; other request methods return `405` and `Allow: POST`.
- [ ] Only `application/json` (optionally with `charset=UTF-8`) is accepted; missing/wrong `Content-Type` returns `415`.
- [ ] Every login request is bounded by **actual bytes read**, even without `Content-Length`.
- [ ] An **8192-byte** body is allowed through, **8193 bytes** receives `413`, including multi-byte Unicode.
- [ ] Bodies passing the guard are still read intact by Jackson.
- [ ] Syntax-invalid JSON receives `400`; wrong credentials receive `401`; missing CSRF receives `403`.
- [ ] No variant path/HTTP method can reach the login controller while bypassing the guard.
- [ ] CSRF, HTTPS, cookies/sessions, ingress body limits, timeouts, and rate limits are verified independently.
- [ ] MockMvc results are distinguished from real HTTP testing behind a reverse proxy.
- [ ] Bodies containing passwords, real CSRF tokens, or real session IDs are never logged, echoed, or stored.

### References

- [Spring Framework — Mapping Requests (Servlet MVC)](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html)
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security — CSRF for JavaScript applications](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security — MockMvc CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Boot — Common Application Properties (Tomcat)](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [MDN — HTTP 405](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/405), [HTTP 413](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/413), [HTTP 415](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/415)
