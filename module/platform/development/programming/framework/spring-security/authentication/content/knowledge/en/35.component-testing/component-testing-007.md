# Testing AuthenticationConverter, Malformed JSON, and Missing Input

## 1. Why Does AuthenticationConverter Need Its Own Test Suite?

In a Spring Security application with **JSON-based login**, a request such as `POST /auth/login` might carry a body like:

~~~json
{
  "username": "alice",
  "password": "correct-password"
}
~~~

However, real requests do not always contain valid JSON. Clients can send an empty body, missing braces, a JSON array instead of an object, a missing `username`, a `null` `password`, numeric values, extra fields, or a JSON object containing **two duplicate keys**. In those cases, the system should handle them **before** proceeding to password verification.

`AuthenticationConverter` is an extension point in **Spring Security Servlet**: it converts an `HttpServletRequest` into an **unauthenticated** `Authentication` object, or rejects an invalid request. `AuthenticationManager`/`AuthenticationProvider` is what verifies passwords, tokens, accounts, and status; the converter **should never confirm a login as successful itself**.

Without testing the converter:
- Malformed JSON can trigger a `500` instead of a controlled error.
- A body missing `password` can produce a token with `credentials=null` or an empty string.
- A JSON parser might silently coerce numbers to strings or ignore duplicate keys, making input validation ambiguous.
- The converter might swallow exceptions and return `null`, causing `AuthenticationFilter` to **skip** the login attempt instead of returning an error.
- A non-login URL might have its body read or authentication attempted unexpectedly by the converter.
- Tests checking only a `200` response will not detect whether the converter built the right `Authentication` type, kept `authenticated=false`, or leaked passwords into logs.

**After this lesson, you will be able to:**
1. Distinguish the three valid outcomes of a converter: `null`, an unauthenticated `Authentication`, and `AuthenticationException`.
2. Write unit tests with `MockHttpServletRequest`, JUnit 5, and AssertJ for valid JSON, syntax errors, wrong types, missing fields, duplicate fields, and excess data.
3. Write integration tests with `AuthenticationFilter` + `MockMvc` to verify the exact `400` / `401` / `200` response paths.
4. Ensure invalid JSON never invokes `AuthenticationManager`.
5. Enforce body-size/Content-Type limits, avoid parsing credentials on wrong endpoints, and avoid leaking credentials in errors.
6. Understand the difference between **payload validation**, **authentication**, and **authorization**; know when CSRF, rate limiting, and brute-force protection are needed.
7. Run a self-contained Java 17 / Spring Boot 3.3.x project with illustrative code, build/test commands, and reliable result expectations.

> **Scope:** Spring MVC/Servlet with `org.springframework.security.web.authentication.AuthenticationConverter`. For WebFlux, the equivalent API is `ServerAuthenticationConverter`, which receives `ServerWebExchange` and returns `Mono<Authentication>`; do not apply Servlet code as-is to reactive stacks.

## 2. Where Does AuthenticationConverter Fit in the Authentication Flow?

Diagram:

~~~text
HTTP POST /auth/login
        |
        v
SecurityFilterChain
        |
        v
AuthenticationFilter + RequestMatcher
        |
        +-- Request DOES NOT match -> skip filter, continue chain
        |
        v
AuthenticationConverter.convert(request)
        |
        +-- null -> do not attempt authentication, continue chain
        |
        +-- AuthenticationException -> failure handler, do not call Manager
        |
        +-- UsernamePasswordAuthenticationToken.unauthenticated(...)
                              |
                              v
                        AuthenticationManager
                              |
                 +------------+-------------+
                 |                          |
           Wrong credentials          Right credentials
                 |                          |
                 v                          v
         AuthenticationException      Authenticated token
                 |                          |
                 v                          v
           Failure handler             Success handler
                 |                          |
                 v                          v
         401 / generic error            200 / login result
~~~

Per the Spring Security Java API, `AuthenticationConverter` defines:

~~~java
@FunctionalInterface
public interface AuthenticationConverter {
    Authentication convert(HttpServletRequest request);
}
~~~

This is a **simplified form to explain the contract**, not verbatim framework source. Actual signatures may include nullability annotations and `@FunctionalInterface` depending on version. Returning `null` indicates **no authentication attempt was created**; an `AuthenticationException` can signal an invalid credential scheme/payload.

### 2.1. Distinguishing the three outcomes

| Request | Outcome the converter should produce | Next step |
| --- | --- | --- |
| `GET /public`, not a login endpoint | `null` | Filter does not handle login |
| `POST /auth/login` matching contract | `Authentication` with **`isAuthenticated=false`** | `AuthenticationManager` verifies |
| `POST /auth/login` JSON missing field/wrong type | Throw dedicated `AuthenticationException` | Failure handler returns controlled error |
| `POST /auth/login` right password but disabled account | Converter builds unauthenticated token | Manager/provider rejects based on account status |
| `POST /auth/login` valid username, wrong password | Converter builds unauthenticated token | Manager/provider rejects; do not let converter decide |
| `POST /auth/login` sends JWT/Bearer header while contract is JSON username/password | Do not silently fall back to another scheme | Chain policy determines whether it applies |

**Return `null` only when there is no authentication attempt the converter owns**, such as a non-matching path or HTTP method. Once the endpoint is matched and the body is **invalid**, report a clear error rather than swallowing it and returning null.

### 2.2. Testing each component at the right layer

- **Converter unit tests:** request → Authentication/exception. No database, real password hashing, servlet server, or Spring application context needed.
- **`AuthenticationManager`/Provider tests:** credentials + user store → successful/failed Authentication. No JSON body needed.
- **Filter tests:** converter result → Manager called or not; success/failure handlers, status, SecurityContext.
- **`MockMvc` integration tests:** send real HTTP POSTs through `SecurityFilterChain`, assert HTTP status/body/headers, no hidden sessions or auth bypasses.
- **Browser/E2E tests:** cookies/sessions, CSRF, CORS, and frontend behavior in a real browser; `MockMvc` does not replace an entire browser.

## 3. Designing the Contract for JSON Login

Define the contract upfront instead of letting the parser guess:

~~~http
POST /auth/login HTTP/1.1
Host: api.example.org
Content-Type: application/json; charset=UTF-8

{"username":"alice","password":"correct-password"}
~~~

Sample contract in this lesson:

| Component | Lab rule | Why |
| --- | --- | --- |
| Method/path | Exactly `POST /auth/login` | Do not turn other requests into login |
| Content-Type | `application/json`, UTF-8 | Do not parse form-data or `text/plain` as JSON |
| Body size | Maximum **4096 bytes** | Avoid reading huge bodies for login attempts |
| Root JSON | An **object**, not array/string/number | Easy schema verification |
| `username` | String, 3–64 chars, pattern `[A-Za-z0-9._@-]+` | Explicit lab rule, no coerced types |
| `password` | String, 8–128 chars, non-blank | Never issue a token missing credentials |
| Other fields | Disallowed in lab | Block mass assignment and ambiguous requests |
| JSON duplicate keys | Reject | Avoid "first wins" or "last wins" |
| Trailing JSON tokens after object | Reject | Prevent parser accepting first part and ignoring tail |
| Schema/syntax error | `400 Bad Request` | Client sent a login request violating contract |
| Invalid password/username | `401` with generic message | Do not reveal whether the account exists |
| Valid credentials | `200` in lab | Success demo only; no production session/token issued |

**Do not treat this table as a universal password policy for all products.** Usernames can be Unicode emails, phone numbers, UUIDs, or user handles; password policies should support length, passphrases, Unicode, and breached-password checks per product needs. Here inputs are constrained solely for repeatable tests.

### 3.1. Many kinds of malformed JSON

**Syntax error**:

~~~json
{"username":"alice","password":
~~~

**Missing field**:

~~~json
{"username":"alice"}
~~~

**Wrong type**:

~~~json
{"username":42,"password":"correct-password"}
~~~

**Null value**:

~~~json
{"username":"alice","password":null}
~~~

**Duplicate field**:

~~~json
{"username":"alice","password":"first","password":"second"}
~~~

**Wrong root shape**:

~~~json
["alice","correct-password"]
~~~

**Extra field**:

~~~json
{"username":"alice","password":"correct-password","role":"ADMIN"}
~~~

Samples may violate JSON schema or even be syntactically valid JSON. Do not test only `JsonParseException`, because an object missing a field is still **syntactically valid** JSON. Authentication risks span syntax, schema, and business validation.

## 4. Choosing Status Codes and Exceptions at the Right Layer

A converter **should not write the HTTP response itself**. It only returns an `Authentication` or throws `AuthenticationException`. An `AuthenticationFailureHandler` can classify outcomes:

| Result | Exception type | Sample HTTP |
| --- | --- | --- |
| Bad JSON / missing field / wrong Content-Type | `InvalidLoginRequestException` (`AuthenticationException` subclass) | 400 |
| Missing username or wrong password | `BadCredentialsException` from Provider | 401 |
| Account disabled/locked | `DisabledException` / `LockedException` | 401 or matching policy; response discloses no details |
| Success | Authenticated result from Manager | 200 in lab |
| Converter called on non-login endpoint | Returns `null` (not a JSON error) | Non-login endpoint proceeds through chain |
| Genuine unexpected server failure | System error logged safely | 5xx; never disguise as 400 and hide the bug |

In this lab, payload errors return a fixed body `{"error":"INVALID_REQUEST"}` and credential errors return `{"error":"BAD_CREDENTIALS"}`. Never echo usernames/passwords, raw bodies, parsing stack traces, or password hashes into responses. Never disclose "account exists" when credentials are wrong.

**HTTP authentication note:** HTTP `401` normally includes a `WWW-Authenticate` challenge if the API uses an HTTP authentication scheme. A JSON-login credential exchange is an application-specific contract; if your system uses HTTP challenge–response or combines Basic/Bearer, define/preserve the proper challenge per RFC 9110 and the actual filter chain. Do not return a fake `401` claiming `Bearer invalid_token` when the issue is a JSON password.

## 5. A Self-Contained Spring Boot 3.3.12 / Java 17 Project

This lab project accepts JSON login and demonstrates only the **authentication step**; it issues no access tokens or login cookies. This keeps the test suite focused on the converter and filter. The sample configuration uses `SessionCreationPolicy.STATELESS`, disables form login/Basic, and allows only `POST /auth/login`.

Structure:

~~~text
json-converter-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/jsonauth/
    │   ├── JsonAuthApplication.java
    │   ├── JsonLoginAuthenticationConverter.java
    │   └── SecurityConfig.java
    └── test/java/demo/jsonauth/
        ├── JsonLoginAuthenticationConverterTest.java
        ├── AuthenticationFilterTest.java
        └── JsonLoginHttpTest.java
~~~

### 5.1. Gradle and dependencies

`settings.gradle`:

~~~groovy
rootProject.name = 'json-converter-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.12'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
~~~

Spring Boot Starter Web brings Jackson for JSON parsing, Starter Security brings `AuthenticationFilter`/`AuthenticationConverter`, and Spring Security Test plus starter-test bring MockMvc/JUnit/AssertJ/Mockito. **There is no need to add a separate Jackson version** unless managed deliberately by your project BOM.

`src/main/java/demo/jsonauth/JsonAuthApplication.java`:

~~~java
package demo.jsonauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonAuthApplication.class, args);
    }
}
~~~

## 6. Writing JsonLoginAuthenticationConverter

**Implementation requirements:**
- Accept only a JSON POST to the exact path; wrong path/method → `null`, without reading the body.
- Never fall back to `request.getParameter("username")`: data lives in the JSON body.
- Read **at most 4097 bytes** to detect payloads exceeding 4096 bytes.
- Enable duplicate-key detection, verify root object, and check **trailing tokens**.
- Validate exact types, sizes, and fields. Never create an `Authentication` when the payload fails validation.
- Return `UsernamePasswordAuthenticationToken.unauthenticated(...)` so the Provider performs authentication.
- Never log raw request data, passwords, or exception details into responses.

`src/main/java/demo/jsonauth/JsonLoginAuthenticationConverter.java`:

~~~java
package demo.jsonauth;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

import jakarta.servlet.http.HttpServletRequest;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.http.MediaType;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.authentication.AuthenticationConverter;

public final class JsonLoginAuthenticationConverter
        implements AuthenticationConverter {

    private static final int MAX_BODY_BYTES = 4096;
    private static final String LOGIN_PATH = "/auth/login";
    private final ObjectMapper mapper;

    public JsonLoginAuthenticationConverter(ObjectMapper objectMapper) {
        // ObjectMapper must be fully configured before sharing across threads.
        // copy() so the application-wide ObjectMapper is not mutated.
        this.mapper = objectMapper.copy()
                .enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION);
    }

    @Override
    public Authentication convert(HttpServletRequest request)
            throws AuthenticationException {

        // Reject requests for any other path or HTTP method.
        if (!"POST".equals(request.getMethod())
                || !LOGIN_PATH.equals(request.getServletPath())) {
            return null;
        }

        final MediaType mediaType;
        try {
            mediaType = MediaType.parseMediaType(
                    request.getContentType() == null
                            ? "" : request.getContentType());
        } catch (IllegalArgumentException invalidContentType) {
            throw invalid();
        }

        if (!MediaType.APPLICATION_JSON.isCompatibleWith(mediaType)
                || (mediaType.getCharset() != null
                    && !StandardCharsets.UTF_8.equals(mediaType.getCharset()))) {
            throw invalid();
        }

        final byte[] bytes;
        try {
            // readNBytes(4097) allocates at most 4097 bytes for the body,
            // enough to detect payloads exceeding the lab limit.
            bytes = request.getInputStream()
                    .readNBytes(MAX_BODY_BYTES + 1);
        } catch (IOException readFailure) {
            throw invalid();
        }

        if (bytes.length == 0 || bytes.length > MAX_BODY_BYTES) {
            throw invalid();
        }

        final JsonNode root;
        try (JsonParser parser = mapper.getFactory().createParser(bytes)) {
            root = mapper.readTree(parser);

            // Must not parse only the first object and ignore trailing data.
            if (root == null || !root.isObject()
                    || parser.nextToken() != null) {
                throw invalid();
            }
        } catch (JsonProcessingException malformedJson) {
            throw invalid();
        } catch (IOException parserFailure) {
            throw invalid();
        }

        // Lab contract permits exactly these two properties.
        JsonNode usernameNode = root.get("username");
        JsonNode passwordNode = root.get("password");

        if (root.size() != 2 || usernameNode == null
                || passwordNode == null
                || !usernameNode.isTextual()
                || !passwordNode.isTextual()) {
            throw invalid();
        }

        String username = usernameNode.textValue();
        String password = passwordNode.textValue();

        if (!username.matches("[A-Za-z0-9._@-]{3,64}")
                || password.length() < 8 || password.length() > 128
                || password.isBlank()) {
            throw invalid();
        }

        // This is only an UNAUTHENTICATED Authentication.
        // Do not setAuthenticated(true) or hash/compare passwords here.
        return UsernamePasswordAuthenticationToken.unauthenticated(
                username, password);
    }

    private static InvalidLoginRequestException invalid() {
        return new InvalidLoginRequestException();
    }

    public static final class InvalidLoginRequestException
            extends AuthenticationException {
        public InvalidLoginRequestException() {
            // Fixed message; never embed raw body or credentials.
            super("Invalid login request");
        }
    }
}
~~~

### 6.1. Reading each branch's correctness carefully

**Branch A — non-matching:** `GET /auth/login` or `POST /other` returns `null` before the parser touches the body. `AuthenticationFilter` has its own `RequestMatcher`, yet having the converter check method/path itself is also useful when unit testing or reusing the converter elsewhere.

**Branch B — wrong Content-Type:** `text/plain`, `application/x-www-form-urlencoded`, or missing Content-Type all produce a 400 error under the lab contract. Never parse the body as another type or fall back to form parameters. `MediaType.parseMediaType` supports `application/json;charset=UTF-8`; `application/json;charset=ISO-8859-1` is rejected by the lab.

**Branch C — oversized data:** `readNBytes(MAX_BODY_BYTES + 1)` bounds the bytes the converter buffers in memory. Web server/gateway request size limits must still be configured independently; do not assume this snippet alone prevents all streaming/DoS costs in layers ahead of the converter. Ingress rate limiting and timeouts are recommended.

**Branch D — Jackson:** enabling `STRICT_DUPLICATE_DETECTION` catches JSON objects with two `password` fields; checking `parser.nextToken()` detects a second JSON document appended right after the first. Without strict mode enabled, default behavior can let the last value **overwrite** the earlier one, which is not a safe contract for authentication.

**Branch E — schema:** `root.size()==2` and `isTextual()` block missing fields, nulls, objects/arrays/numbers/booleans, and extra fields like `role`. JSON `{"username":"alice","password":null}` is never treated as the string password `"null"`.

**Branch F — unauthenticated token:** `UsernamePasswordAuthenticationToken.unauthenticated` has `isAuthenticated()==false`. Only `AuthenticationManager` has the authority to turn the token into an authenticated result after verifying the password and account status.

**Specifically:** this converter accepts no cookie/header/token as a substitute credential. If a system supports multiple authentication schemes, design separate converters/filters and explicit request matchers; never "look for credentials anywhere" just to make a test pass.

### 6.2. Areas to expand for production

The lab contract uses ASCII usernames to isolate tests; production needs consistent email/Unicode/IDN policies without corrupting identities via arbitrary `trim`/lowercasing. Passwords are sensitive: never log them, never include them in metrics/exceptions, and let `ProviderManager` or a custom auth provider manage clearing and hash verification. For browser/session authentication, add CSRF, login CSRF protection, session fixation protection, and hardened cookie settings. For real APIs, use adaptive password hashing, MFA, rate limiting/throttling, and user-enumeration mitigations.

**Do not ignore `InputStream` read exceptions as "malformed client JSON".** In the lab we map stream read errors to 400 for a simple contract; production can distinguish connection/body-truncation errors from client syntax errors cleanly while still exposing no sensitive details.

## 7. Integrating AuthenticationFilter and AuthenticationManager

`AuthenticationFilter` has a constructor taking `AuthenticationManager` and `AuthenticationConverter`. The filter:
1. Matches the request.
2. Calls `convert(request)`.
3. If a token is returned → calls `AuthenticationManager.authenticate(token)`.
4. On success → invokes `AuthenticationSuccessHandler`.
5. On `AuthenticationException` → invokes `AuthenticationFailureHandler`.

The example configures **one** JSON authentication mechanism without creating cookies/sessions. This cleanly tests that invalid input never turns into an authenticated credential.

`src/main/java/demo/jsonauth/SecurityConfig.java`:

~~~java
package demo.jsonauth;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationFilter;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder encoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("lab-password-123"))
                        .roles("USER")
                        .build());
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider dao = new DaoAuthenticationProvider();
        dao.setUserDetailsService(users);
        dao.setPasswordEncoder(encoder);
        return new ProviderManager(dao);
    }

    @Bean
    JsonLoginAuthenticationConverter jsonConverter(ObjectMapper mapper) {
        return new JsonLoginAuthenticationConverter(mapper);
    }

    @Bean
    SecurityFilterChain security(
            HttpSecurity http,
            JsonLoginAuthenticationConverter converter,
            AuthenticationManager manager) throws Exception {

        AuthenticationFilter loginFilter =
                new AuthenticationFilter(manager, converter);

        loginFilter.setRequestMatcher(
                new AntPathRequestMatcher("/auth/login", "POST"));

        loginFilter.setSuccessHandler((request, response, auth) -> {
            response.setHeader("Cache-Control", "no-store");
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setStatus(200);
            response.getWriter().write(
                    "{\"status\":\"AUTHENTICATED\"}");
        });

        loginFilter.setFailureHandler((request, response, error) -> {
            boolean badInput = error instanceof
                    JsonLoginAuthenticationConverter.InvalidLoginRequestException;
            response.setHeader("Cache-Control", "no-store");
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setStatus(badInput ? 400 : 401);
            response.getWriter().write(
                    badInput
                            ? "{\"error\":\"INVALID_REQUEST\"}"
                            : "{\"error\":\"BAD_CREDENTIALS\"}");
        });

        return http
                // Stateless JSON login in lab only;
                // browser cookies/sessions are not used as credentials.
                .csrf(AbstractHttpConfigurer::disable)
                .sessionManagement(s -> s
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .requestCache(AbstractHttpConfigurer::disable)
                .formLogin(AbstractHttpConfigurer::disable)
                .httpBasic(AbstractHttpConfigurer::disable)
                .authorizeHttpRequests(a -> a
                        .requestMatchers(HttpMethod.POST,
                                "/auth/login").permitAll()
                        .anyRequest().denyAll())
                .addFilterAt(loginFilter,
                        UsernamePasswordAuthenticationFilter.class)
                .build();
    }
}
~~~

### 7.1. Configuration notes

- `DaoAuthenticationProvider` reads `UserDetailsService` and matches passwords with `PasswordEncoder`. The demo password is for local use only; hashes are stored via `DelegatingPasswordEncoder`.
- `AuthenticationFilter` is instantiated **inside `SecurityFilterChain`**, not annotated with `@Component`. That prevents Spring Boot from accidentally registering it as a standalone Servlet Filter outside `FilterChainProxy`, which would run it twice or out of order.
- `new AntPathRequestMatcher("/auth/login","POST")` enforces the exact HTTP method/path. The converter checks it too for direct testing.
- `addFilterAt(..., UsernamePasswordAuthenticationFilter.class)` places the JSON authentication filter at a predictable position in the Spring Security filter order; form login is disabled so two login filters do not both execute.
- `STATELESS` is a **lab policy**: a 200 response here means credentials were verified, **not** that cookies/sessions/JWTs were issued for subsequent requests. Production must design dedicated authentication/session/token issuance rather than treating a 200 status as persistent login.
- `csrf.disable()` is **only considered** because the demo uses no browser cookies/sessions/HTTP Basic as auto-sent credentials. If a real frontend uses session cookies, login CSRF and state-changing requests must still be protected; never copy that line into browser flows.
- The failure handler separates **payload errors** (400) from **wrong credentials** (401), both returning fixed bodies; never use `error.getMessage()`/`getCause()` as the response.
- Never create an authentication when the password is empty or fails schema checks. Never use user-provided `role`, `authenticated`, or `scope` to grant permissions.

### 7.2. Distinguishing JSON parser exceptions from auth exceptions

A converter may catch `JsonProcessingException` from Jackson, whereas `AuthenticationFilter` handles errors via `AuthenticationException`. Therefore, the converter **translates JSON errors** into a specific subclass of `AuthenticationException`; never let parser exceptions escape and turn into `500`.

Do not map **every** `RuntimeException` to invalid login. A `NullPointerException` from a bug, user-store connection errors, or configuration errors are **backend failures** needing 5xx and safe alarms rather than being masked as 400. Catch the right error types at the right layer.

## 8. Unit Testing the Converter with MockHttpServletRequest

Unit tests have major advantages: fast, no Spring context, no database/service activation, and no listening TCP port. `MockHttpServletRequest` lets you set the HTTP method, path, Content-Type, and request body.

`src/test/java/demo/jsonauth/JsonLoginAuthenticationConverterTest.java`:

~~~java
package demo.jsonauth;

import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;

import static org.assertj.core.api.Assertions.*;

class JsonLoginAuthenticationConverterTest {

    private final JsonLoginAuthenticationConverter converter =
            new JsonLoginAuthenticationConverter(new ObjectMapper());

    private static MockHttpServletRequest request(
            String method, String path, String contentType, String body) {

        MockHttpServletRequest req =
                new MockHttpServletRequest(method, path);
        req.setServletPath(path);
        if (contentType != null) {
            req.setContentType(contentType);
        }
        req.setContent(body.getBytes(StandardCharsets.UTF_8));
        return req;
    }

    private static MockHttpServletRequest json(String body) {
        return request("POST", "/auth/login",
                "application/json", body);
    }

    @Test
    void validJsonProducesUnauthenticatedToken() {
        Authentication auth = converter.convert(json("""
                {"username":"alice","password":"lab-password-123"}
                """));

        assertThat(auth).isInstanceOf(
                UsernamePasswordAuthenticationToken.class);
        assertThat(auth.isAuthenticated()).isFalse();
        assertThat(auth.getName()).isEqualTo("alice");
        assertThat(auth.getCredentials()).isEqualTo(
                "lab-password-123");
        assertThat(auth.getAuthorities()).isEmpty();
    }

    @Test
    void unrelatedPathOrMethodDoesNotAttemptAuthentication() {
        assertThat(converter.convert(request(
                "GET", "/auth/login", "text/plain", "not json")))
                .isNull();
        assertThat(converter.convert(request(
                "POST", "/unrelated", "text/plain", "not json")))
                .isNull();
    }

    @Test
    void malformedJsonFailsClosed() {
        assertThatThrownBy(() -> converter.convert(
                json("{\"username\":\"alice\",\"password\":")))
                .isInstanceOf(
                    JsonLoginAuthenticationConverter
                            .InvalidLoginRequestException.class);
    }

    @Test
    void missingUsernameOrPasswordIsRejected() {
        assertThatThrownBy(() -> converter.convert(
                json("{\"username\":\"alice\"}")))
                .isInstanceOf(
                    JsonLoginAuthenticationConverter
                            .InvalidLoginRequestException.class);
        assertThatThrownBy(() -> converter.convert(
                json("{\"password\":\"lab-password-123\"}")))
                .isInstanceOf(
                    JsonLoginAuthenticationConverter
                            .InvalidLoginRequestException.class);
    }

    @Test
    void emptyBodyAndNullAreRejected() {
        assertThatThrownBy(() -> converter.convert(json("")))
                .isInstanceOf(
                    JsonLoginAuthenticationConverter
                            .InvalidLoginRequestException.class);
        assertThatThrownBy(() -> converter.convert(
                json("{\"username\":\"alice\",\"password\":null}")))
                .isInstanceOf(
                    JsonLoginAuthenticationConverter
                            .InvalidLoginRequestException.class);
    }

    @Test
    void wrongTypesAndRootShapeAreRejected() {
        assertThatThrownBy(() -> converter.convert(
                json("{\"username\":42,\"password\":\"lab-password-123\"}")))
                .isInstanceOf(
                    JsonLoginAuthenticationConverter
                            .InvalidLoginRequestException.class);
        assertThatThrownBy(() -> converter.convert(
                json("[\"alice\",\"lab-password-123\"]")))
                .isInstanceOf(
                    JsonLoginAuthenticationConverter
                            .InvalidLoginRequestException.class);
    }

    @Test
    void duplicateKeysAndTrailingJsonAreRejected() {
        assertThatThrownBy(() -> converter.convert(json("""
                {"username":"alice","password":"abc-12345678",
                 "password":"lab-password-123"}
                """)))
                .isInstanceOf(
                    JsonLoginAuthenticationConverter
                            .InvalidLoginRequestException.class);

        assertThatThrownBy(() -> converter.convert(json("""
                {"username":"alice","password":"lab-password-123"}
                {"second":"object"}
                """)))
                .isInstanceOf(
                    JsonLoginAuthenticationConverter
                            .InvalidLoginRequestException.class);
    }

    @Test
    void extraFieldsCannotControlRoles() {
        assertThatThrownBy(() -> converter.convert(json("""
                {"username":"alice","password":"lab-password-123",
                 "role":"ADMIN"}
                """)))
                .isInstanceOf(
                    JsonLoginAuthenticationConverter
                            .InvalidLoginRequestException.class);
    }

    @Test
    void incorrectContentTypeIsRejected() {
        assertThatThrownBy(() -> converter.convert(request(
                "POST", "/auth/login", "text/plain",
                "{\"username\":\"alice\",\"password\":\"lab-password-123\"}")))
                .isInstanceOf(
                    JsonLoginAuthenticationConverter
                            .InvalidLoginRequestException.class);
    }

    @Test
    void emptyOrShortCredentialsAreRejected() {
        assertThatThrownBy(() -> converter.convert(json("""
                {"username":"","password":"lab-password-123"}
                """)))
                .isInstanceOf(
                    JsonLoginAuthenticationConverter
                            .InvalidLoginRequestException.class);
        assertThatThrownBy(() -> converter.convert(json("""
                {"username":"alice","password":"  "}
                """)))
                .isInstanceOf(
                    JsonLoginAuthenticationConverter
                            .InvalidLoginRequestException.class);
    }

    @Test
    void oversizedBodyIsRejected() {
        String payload = "{\"username\":\"alice\",\"password\":\""
                + "x".repeat(5000) + "\"}";
        assertThatThrownBy(() -> converter.convert(json(payload)))
                .isInstanceOf(
                    JsonLoginAuthenticationConverter
                            .InvalidLoginRequestException.class);
    }
}
~~~

### 8.1. What is verified?

The 11 unit tests above test only the **converter**:
- For valid JSON, builds an `Authentication` with exact principal/credentials, unauthenticated, and **no authorities granted**.
- Malformed JSON / missing fields / `null` / array / number / extra fields / duplicate fields / trailing JSON / oversized body all raise a **controlled authentication exception**.
- Wrong path/method returns `null` without parsing the body.
- Passwords are not encoded, compared, or granted roles by the converter itself; the Provider handles that step.

Tests can also use parameterized tests (JUnit 5 `@ParameterizedTest` + `@MethodSource`) to cover dozens of JSON inputs. In this document cases are written explicitly so learners can easily see **one assertion per risk**.

### 8.2. Why not test only `assertNotNull(authentication)`?

Checking `notNull` does not prove:
- `authentication.isAuthenticated() == false`;
- Username came from the right field rather than a query parameter;
- Password was not dropped, trimmed, or re-encoded;
- No `ROLE_ADMIN` was self-attached;
- Invalid input fails to create a token and never calls the Manager;
- Large bodies are not read unboundedly.

Good unit tests cover **both state and negative behavior**, not just type checks.

## 9. Filter-Level Unit Tests: Bad JSON Never Touches AuthenticationManager

A faulty converter can still be miswired by a misconfigured filter. We can verify that `AuthenticationFilter` **never calls `AuthenticationManager`** when the converter throws an exception, and that the failure handler runs.

`src/test/java/demo/jsonauth/AuthenticationFilterTest.java`:

~~~java
package demo.jsonauth;

import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.web.authentication.AuthenticationFilter;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

class AuthenticationFilterTest {

    @Test
    void invalidPayloadDoesNotCallAuthenticationManager()
            throws Exception {

        AuthenticationManager manager = mock(AuthenticationManager.class);
        var converter =
                new JsonLoginAuthenticationConverter(new ObjectMapper());
        AuthenticationFilter filter =
                new AuthenticationFilter(manager, converter);

        filter.setRequestMatcher(
                new AntPathRequestMatcher("/auth/login", "POST"));
        filter.setFailureHandler((request, response, error) ->
                response.setStatus(400));

        MockHttpServletRequest request =
                new MockHttpServletRequest("POST", "/auth/login");
        request.setServletPath("/auth/login");
        request.setContentType("application/json");
        request.setContent(
                "{\"username\":\"alice\"}"
                        .getBytes(StandardCharsets.UTF_8));

        MockHttpServletResponse response =
                new MockHttpServletResponse();

        filter.doFilter(request, response, (req, res) -> {
            throw new AssertionError("Must not continue on bad JSON");
        });

        assertThat(response.getStatus()).isEqualTo(400);
        verifyNoInteractions(manager);
    }
}
~~~

**Explanation:** if the converter built a token despite missing `password`, `Manager.authenticate(...)` could be called, failing `verifyNoInteractions(manager)`. The 400 status comes solely from the **test's failure handler**, isolating converter/filter behavior. This test does not verify real passwords or JSON response bodies; Section 10 tests those through the Spring context/`MockMvc`.

You can add a positive case verifying that the Manager receives an unauthenticated token:

~~~java
// Extension snippet (not a standalone @Test class):
// verify(manager).authenticate(argThat(auth ->
//     auth != null && !auth.isAuthenticated()
//     && "alice".equals(auth.getName())));
~~~

That verification only makes sense when you actually execute a valid request and stub the mock `AuthenticationManager` to return an authenticated result. Do not copy this comment and assume you have a runnable test.

## 10. MockMvc Integration Tests: HTTP 400, 401, 200

`MockMvc` boots the web application context and Spring Security filter chain without a TCP port. This is ideal for testing the `AuthenticationFilter` contract, error handler, and provider with demo data.

`src/test/java/demo/jsonauth/JsonLoginHttpTest.java`:

~~~java
package demo.jsonauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class JsonLoginHttpTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validCredentialsReturn200() throws Exception {
        mvc.perform(post("/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"alice",
                                 "password":"lab-password-123"}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("AUTHENTICATED"))
                .andExpect(header().string("Cache-Control", "no-store"));
    }

    @Test
    void badPasswordReturns401WithoutUsernameLeak() throws Exception {
        mvc.perform(post("/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"alice",
                                 "password":"wrong-password-123"}
                                """))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.error").value("BAD_CREDENTIALS"));
    }

    @Test
    void malformedJsonReturns400() throws Exception {
        mvc.perform(post("/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"alice\",\"password\":"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("INVALID_REQUEST"));
    }

    @Test
    void missingPasswordReturns400() throws Exception {
        mvc.perform(post("/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"alice\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("INVALID_REQUEST"));
    }

    @Test
    void wrongJsonTypeReturns400() throws Exception {
        mvc.perform(post("/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"alice",
                                 "password":12345}
                                """))
                .andExpect(status().isBadRequest());
    }

    @Test
    void duplicatePasswordFieldReturns400() throws Exception {
        mvc.perform(post("/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"alice",
                                 "password":"lab-password-123",
                                 "password":"wrong-password-123"}
                                """))
                .andExpect(status().isBadRequest());
    }

    @Test
    void contentTypeTextPlainReturns400() throws Exception {
        mvc.perform(post("/auth/login")
                        .contentType(MediaType.TEXT_PLAIN)
                        .content("""
                                {"username":"alice",
                                 "password":"lab-password-123"}
                                """))
                .andExpect(status().isBadRequest());
    }

    @Test
    void trailingJsonObjectReturns400() throws Exception {
        mvc.perform(post("/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"alice",
                                 "password":"lab-password-123"}
                                {"extra":true}
                                """))
                .andExpect(status().isBadRequest());
    }
}
~~~

**Expectation: 8 integration tests pass** with the described project/config when run against compatible dependency versions. The tests distinguish:
- **400**: payload fails the JSON contract.
- **401**: payload is valid, yet credentials are rejected by the provider.
- **200**: provider verifies the password against the hash in `InMemoryUserDetailsManager`.

These tests do not assert "a session was issued", because **the lab issues no session/token**. For real production flows, test cookies, session fixation, CSRF, and token issuance rather than treating a 200 response as proof of a persistent user session.

**Never modify tests to accept 500 for malformed JSON.** If a Jackson/Spring error leaks out as 500, fix the converter/failure handler to handle expected input errors; unexpected backend errors must still raise 5xx alarms.

## 11. Running the Full Project and Observing Behavior

Requirements: JDK 17+ and Gradle compatible with Spring Boot 3.3.x. If the project includes a Gradle Wrapper, use `./gradlew` or `gradlew.bat` instead of `gradle`.

~~~bash
# In the project directory:
gradle test
gradle bootRun
~~~

From another terminal, send a valid JSON request with curl to **localhost**, using only the demo password:

~~~bash
curl -i \
  -H 'Content-Type: application/json' \
  --data '{"username":"alice","password":"lab-password-123"}' \
  http://localhost:8080/auth/login
~~~

Expected response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{"status":"AUTHENTICATED"}
~~~

Try JSON missing `password`:

~~~bash
curl -i \
  -H 'Content-Type: application/json' \
  --data '{"username":"alice"}' \
  http://localhost:8080/auth/login
~~~

Expected:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{"error":"INVALID_REQUEST"}
~~~

Try a wrong password:

~~~bash
curl -i \
  -H 'Content-Type: application/json' \
  --data '{"username":"alice","password":"wrong-password-123"}' \
  http://localhost:8080/auth/login
~~~

Expect 401 with:

~~~json
{"error":"BAD_CREDENTIALS"}
~~~

**Output note:** the status/headers/body above show the **intended lab contract**. Additional headers inserted by Spring Security and the web container may appear; the HTTP/1.1 vs HTTP/2 status line varies by client. Do not treat these snippets as actual captured runtime logs. Never print raw bodies/passwords to logs in production, and never put real passwords into shell history via `curl --data`.

### 11.1. Expected test summary

With the project above:
- 11 tests in `JsonLoginAuthenticationConverterTest`.
- 1 test in `AuthenticationFilterTest`.
- 8 tests in `JsonLoginHttpTest`.
- **Expected total: 20 tests.**

This is a **logical expectation**, not proof that tests were executed in the current environment. When running them, if results differ, read the test runner's error details and inspect dependency versions, `SecurityFilterChain` matchers, and JSON parser settings; never "quick-fix" by deleting negative tests.

## 12. Testing Request Boundaries and Parser Failures

Core cases to add when upgrading from lab to production:

| Case | Input | Safe result |
| --- | --- | --- |
| Empty body | 0 bytes | 400 |
| Whitespace-only body | `"   "` | 400 |
| JSON syntax wrong | Missing `}` / `"` | 400 |
| JSON `null` root | `null` | 400 |
| JSON array root | `[]` | 400 |
| JSON number root | `123` | 400 |
| JSON top-level string | `"hello"` | 400 |
| `username` missing | Only `password` | 400 |
| `password` missing | Only `username` | 400 |
| `username` null | `"username":null` | 400 |
| `password` null | `"password":null` | 400 |
| Wrong field type | Number/boolean/array/object | 400, do not coerce to String |
| Duplicate JSON fields | Two `password` fields | 400 |
| Trailing JSON | Two JSON documents | 400 |
| Unexpected fields | `"isAdmin":true` | 400, never grant authority |
| Invalid username format | Disallowed by lab contract | 400 |
| Password too short/empty | Fails lab contract | 400 |
| Body over 4096 bytes | Over limit | 400 or 413 per production contract |
| Missing Content-Type | Unknown body encoding | 400 or 415 per production contract |
| `application/x-www-form-urlencoded` | Form body | Do not fall back to JSON login |
| `application/json;charset=UTF-8` | Valid JSON | Parsed |
| `application/json;charset=ISO-8859-1` | Violates lab UTF-8 policy | 400 or 415 |
| Query has `username/password` | Empty body | 400, never read query instead of body |
| GET /auth/login | Wrong method | Converter returns null |
| POST /other | Wrong path | Converter returns null |
| Wrong password | Valid JSON | 401, never reveal whether user exists |
| Account disabled | Valid JSON | Provider blocks, generic response per policy |
| Right password | Valid JSON | Only Manager authenticates |
| Body with invalid UTF-8 | Bad byte sequence | 400, never silently replace characters |
| Request stream fails mid-read | `InputStream` throws `IOException` | Controlled failure per contract; never leak cause |
| Concurrent requests | Multiple independent requests | Share no mutable parse state or credentials |

### 12.1. Multipart/form data is not a JSON credential

Some apps support both `POST /login` HTML forms and `POST /auth/login` JSON. Design **two separate request matchers/converters**, never guessing via "if JSON parse fails, try `request.getParameter`". That kind of fallback can cause a single request to be interpreted differently across the gateway, servlet container, and application. Every endpoint accepting credentials must be clearly documented and tested.

### 12.2. Content-Length is not a sufficient limit

A request using `Transfer-Encoding: chunked` may have no upfront `Content-Length`. Checking only `request.getContentLengthLong() > 4096` and then parsing the entire body can still read huge amounts of data. The sample converter uses `readNBytes(4097)` to detect exceeding the limit, while production also needs request body limits and timeouts configured at the gateway/container.

### 12.3. Duplicate fields and parser differences

The JSON specification allows the syntax, yet expects unique object member names for interoperability. Parser A might take the first value, Parser B might take the last, and a WAF might see a different value from the backend. For **authentication** fields, such discrepancies are dangerous. Enable duplicate detection and test requests through the real gateway so layers never interpret payloads differently.

### 12.4. JSON numbers or objects are not valid usernames/passwords

The following is **invalid** per contract:

~~~json
{"username":{"value":"alice"},"password":["one","two"]}
~~~

If using Jackson databinding into a DTO with `String username`, some configurations/coercions can turn numbers or booleans into text. For JSON credentials, checking `JsonNode.isTextual()` enforces explicit types. If using DTOs, enable strict validation and disable coercion rather than assuming `@NotNull` alone blocks every wrong-type input.

## 13. Testing Security Properties Beyond JSON

Strong payload validation is still insufficient if the overall login flow lacks protection:

### 13.1. Login CSRF and browser cookies

The lab above is **stateless** and creates no session cookies. If a real application uses session cookies or browsers auto-send credentials, **login CSRF** is a distinct risk. Spring Security protects state-changing requests with CSRF tokens by default. Never disable CSRF system-wide merely because an API uses JSON bodies: strict JSON parsing shrinks attack surface, yet does not replace CSRF defense and CORS/Origin policies.

### 13.2. Rate limiting, brute force, account enumeration

Clients can send completely valid JSON while trying unlimited passwords:
- Rate-limit by IP, account ID/username, device, and tenant, combined with abuse-detection policies.
- Return generic responses for nonexistent usernames and wrong passwords.
- Control differences in timing, messages, metrics, and side channels.
- Never write passwords or raw bodies into access logs, application exceptions, APM, test logs, or analytics.
- User-chosen passwords must be hashed with an adaptive `PasswordEncoder` alongside proper reset/lockout policies.

### 13.3. Mass assignment and credential leakage

Never parse client-supplied fields like `roles`, `authorities`, `enabled`, or `authenticated` into an `Authentication`:
- The converter uses only `username` and `password`.
- The provider reads roles and account status from a trusted source.
- The failure handler never echoes the raw request body in `error_description`.
- Never pass passwords into response JSON, cookies, URLs, redirects, or logs.
- After authentication succeeds, erase credentials in the manager/context per policy; avoid keeping raw passwords longer than necessary.

### 13.4. Never let a generic exception swallow application bugs

An anti-pattern:

~~~java
// ILLUSTRATION OF HOW NOT TO WRITE IT:
try {
    return parser.parse(request);
} catch (Exception everything) {
    return null;
}
~~~

Parse errors get turned into "no login attempt", or backend bugs get hidden. Instead:
- Catch `JsonProcessingException`/`IOException` in the parser as request errors per policy.
- Translate them into a specific `AuthenticationException` type.
- Let the system log/alert other server errors per policy; never send stack traces to clients.
- Test the converter's `null` and exception behaviors separately.

## 14. When to Use Unit Tests, MockMvc, and Real Integration Tests?

| Test layer | What bugs it catches | What it does NOT prove |
| --- | --- | --- |
| Pure unit with `MockHttpServletRequest` | JSON syntax/schema, method/path, unauthenticated token | Filter is properly wired into the chain |
| Filter unit with Mockito Manager | Bad JSON never calls auth manager, failure handler | Real Provider/DB/web configuration |
| `@SpringBootTest + @AutoConfigureMockMvc` | Spring Security chain, HTTP status/body, demo Provider | Full TLS/proxy/browser/CSRF |
| Controller/contract tests | Content-Type, error JSON, auth headers per policy | Production username/password lifecycle |
| Browser E2E on HTTPS staging | Cookies/CSRF/CORS/network behavior | Multi-server workflows/data races if unconfigured |
| Gateway/container tests | Content size, encoding, proxy normalization, rate limits | Per-object business permissions unless tested separately |

A strong test suite tests **business invariants independent of framework mechanics**: missing passwords must not authenticate; wrong types must not become principals; wrong passwords must not receive success responses; JSON with duplicate keys must not be interpreted differently by a security boundary and downstream layer.

To write durable tests:
1. Assert outputs/side effects rather than every internal method call.
2. Use dummy test data; never write real passwords/tokens into logs.
3. Name tests after the scenario and expected security outcome.
4. Separate fast unit tests from heavy integration tests.
5. Use `@ParameterizedTest` when testing dozens of JSON variants.
6. Add boundary tests: 4096/4097 bytes, passwords of 7/8/128/129 characters.
7. Re-verify filter ordering and `RequestMatcher` after upgrading Spring Security versions.
8. Ensure a converter returning `null` on non-login paths **never** opens a protected endpoint accidentally.

## 15. Real-World Bugs and How to Fix Them

| Symptom | Common cause | Proper fix |
| --- | --- | --- |
| Malformed JSON returns 500 | JSON exception not converted to auth exception by converter | Catch specific parse errors and map to 400 |
| Missing password still creates token | Checked null without checking schema/type/empty | Validate required fields, types, and lengths before creating token |
| JSON with 2 passwords still logs in | Parser allows duplicate keys | Enable strict duplicate detection |
| JSON with trailing object still succeeds | Parser reads only first document | Call `nextToken()` to verify EOF |
| `{"username":42}` treated as `"42"` | Databinding/coercion | Parse `JsonNode` and check `isTextual()` |
| Form params work on JSON login | Fallback from body to `getParameter` | Enforce one canonical credential source |
| Converter tests pass yet HTTP 404 | Wrong filter matcher/order/path | Inspect chain and `RequestMatcher` |
| Error 403 on POST login | CSRF still enabled for browser flow | Protect/send token properly; never disable CSRF unconditionally |
| Error 401 for malformed JSON | Failure handler merges credential and payload errors | Distinguish `InvalidLoginRequestException` |
| Server returns 200 for wrong password | Manager stub returns success regardless of input | Manager unit tests and MockMvc using real provider |
| Unexpected `ROLE_ADMIN` appears | Client roles trusted | Server-side authority mapping |
| Large request body causes memory pressure | Unbounded parsing | Bounded read + gateway/body limit + timeout |
| Credentials leak into logs | Logging raw requests, bodies, exceptions | Redaction, logging allowlist, retention |
| Passes on MockMvc yet gateway returns 413 | Gateway has a different limit | Align contracts and test end-to-end |
| `NullPointerException` becomes 400 | Overly broad `catch(Exception)` | Separate client parsing from server bugs |
| Login 200 yet next request still unauthenticated | Endpoint only returns 200 without issuing session/token | Design explicit session/token lifecycle |
| Duplicate converter/filter runs twice | Both `@Component` and `addFilter` used | Register filter exactly once |
| Cookie/JWT sent automatically while CSRF disabled | Confusing JSON format with threat model | Apply CSRF based on auth transport |

## 16. Self-Check Exercises

**Question 1.** When does `AuthenticationConverter.convert()` return `null`?  
**Answer:** When the converter **does not make an authentication attempt** for the request, such as an out-of-scope request. For malformed login JSON, throw a specific `AuthenticationException` instead of returning null to ignore the error.

**Question 2.** JSON `{"username":"alice"}` is syntactically valid—should it produce a `UsernamePasswordAuthenticationToken`?  
**No.** It is missing `password` per the contract and must be rejected before calling the Provider.

**Question 3.** The parser reads JSON `{"password":"A","password":"B"}`. Should it use the last value?  
**No.** Reject duplicate keys because ambiguous interpretation across parsers/proxies/validators can lead to bypasses.

**Question 4.** Should the converter return a token with `isAuthenticated=true` right after reading JSON containing a password?  
**Serious mistake.** The converter does not verify passwords; only the Manager/Provider has authority to authenticate and create an authenticated result.

**Question 5.** Must a wrong password and malformed JSON share the exact same HTTP status?  
**No.** You can classify invalid payloads as 400 and invalid credentials as 401 per the API contract, while still avoiding leaking whether a username exists.

**Question 6.** Does checking `Content-Length < 4096` guarantee the request does not exceed 4096 bytes?  
**Not yet.** Chunked requests may have no known length upfront; bound the actual bytes read and configure limits at the gateway/container.

**Question 7.** Does a `MockMvc` test returning 200 prove the browser keeps a session after login?  
**No.** The stateless lab issues no session. For login to persist across subsequent requests, implement and test explicit session/token issuance.

**Question 8.** Does `@SpringBootTest` replace converter unit tests?  
**Not completely.** Unit tests verify every branch quickly and precisely; integration tests verify wiring/filters/error responses. Both layers complement each other.

**Question 9.** A JSON object contains `{"username":"alice","password":"correct","role":"ADMIN"}`. Should `role` be read into authorities?  
**No.** Authorities must come from a trusted user store/policy; the lab rejects fields outside the schema.

**Question 10.** `JsonParseException` escapes the converter and returns 500. Who should turn it into a 400 error?  
**The converter or parsing adapter** recognizes the client error and converts it into a dedicated exception; the handler returns the appropriate generic status/body. Never catch every runtime exception blindly.

## 17. Checklist Before Deploying a JSON AuthenticationConverter to Production

- [ ] Handles only the exact endpoint/method/content type; out-of-scope requests return null without reading the body.
- [ ] JSON parser uses UTF-8, enforces body-size limits, appropriate depth/constraints, and strict duplicate-key detection.
- [ ] Disallows trailing JSON, non-object roots, and silent field-type coercion.
- [ ] Required fields, lengths/formats, and null/blank values are explicitly validated.
- [ ] Converter produces only unauthenticated tokens; never grants roles/authorities from client input.
- [ ] JSON errors never become 500, never succeed, and never invoke `AuthenticationManager`.
- [ ] Credential failures return generic statuses with no user enumeration and no raw password/exception leakage.
- [ ] HTTP filter/request matcher/CSRF/session policies fit the real browser or machine-to-machine use case.
- [ ] `PasswordEncoder`, `UserDetailsService`, account lock/expiry/disabled checks, MFA, and rate limiting are enforced.
- [ ] Unit tests cover missing/null/wrong type/duplicate/extra/trailing/oversized/bad Content-Type.
- [ ] Filter tests confirm Manager is never called on bad payloads.
- [ ] `MockMvc` tests verify 200/400/401 along with exact bodies/headers/side effects per contract.
- [ ] Never log request credentials; protect TLS, observability, gateway limits, and retention.
- [ ] Test through reverse proxies/containers to catch differences in parsing, size limits, and encoding.
- [ ] Never copy a stateless demo as production login sessions without real token/session issuance.

## 18. Official Documentation

- [Spring Security 6.3 — AuthenticationConverter API](https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/web/authentication/AuthenticationConverter.html): `convert(HttpServletRequest)`, `null`, and `AuthenticationException`.
- [Spring Security 6.3 — AuthenticationFilter API](https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/web/authentication/AuthenticationFilter.html): converter, manager, request matcher, success/failure handlers.
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `Authentication`, `AuthenticationManager`, `AuthenticationProvider`, context.
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html): `DelegatingPasswordEncoder` and password hashes.
- [Spring Security — Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/index.html): MockMvc, SecurityFilterChain, and request test helpers.
- [Jackson Core — JsonParser](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-core/2.17.2/com/fasterxml/jackson/core/JsonParser.html): parsing, duplicate detection.
- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259.html): syntax/semantics, UTF-8, uniqueness of object member names.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): authentication error handling, throttling, account enumeration, credential protection.
- [OWASP — Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html): allowlist, syntactic/semantic validation, and server-side limits.

**Conclusion:** `AuthenticationConverter` is the **boundary that translates an HTTP request into an authentication attempt**, not the place that decides whether a password is right. Out-of-scope requests → `null`; valid login JSON → unauthenticated `Authentication`; malformed JSON/missing input → controlled `AuthenticationException`. Test all three branches separately, test that the filter never calls the Manager on bad payloads, and test with `MockMvc` that `400` differs from `401`; only then do you prevent invalid input from turning into an authenticated principal or opaque server error.