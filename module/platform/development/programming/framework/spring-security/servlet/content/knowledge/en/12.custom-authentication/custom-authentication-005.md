# Restricting Path, HTTP Method, and Content-Type of a Login Endpoint in Spring Security Servlet

## 1. Context and Goals

When building a custom login endpoint—for example **POST /api/login** accepting JSON—we do not merely need to check username/password. We must also decide **which requests are actually allowed to trigger the authentication process**. An overly broad login filter can handle the wrong URLs, accept GET or PUT, try to parse HTML/forms as JSON, bypass CSRF, or execute multiple times if both Spring Security and the Servlet container register the filter.

Therefore, a custom login endpoint must be designed around at least three boundaries:

1. **Path:** strictly **/api/login**; do not automatically match every URL starting with /api/login, and do not accept /api/login/other.
2. **HTTP method:** strictly **POST**, because login transmits secrets and mutates authentication state. GET, HEAD, PUT, DELETE, and PATCH must never silently perform login.
3. **Content type (Content-Type):** strictly JSON per contract, such as **application/json** or **application/json;charset=UTF-8**; form data, text/plain, XML, and unknown content types are rejected before reading credentials.

Beyond those three conditions, there are **body size limits, structural validation, invalid-credential handling, CSRF/session fixation, avoiding secret logging, and post-login endpoint authorization**.

This lesson explains the difference between request matchers and authentication, how to return meaningful 400/401/403/405/413/415 status codes, and provides a **Java 17+ / Spring Boot 3.3.13 / Spring Security 6** project using Servlet SecurityFilterChain and a custom OncePerRequestFilter. Curl and MockMvc examples are included to demonstrate controlled path, method, and Content-Type enforcement.

**Scope:** **Spring Security Servlet** applications. In WebFlux, `SecurityWebFilterChain`, request APIs, and context management differ; do not copy Servlet code here verbatim.

## 2. Login Is an Endpoint with an HTTP Contract

Suppose the API publishes the contract:

~~~http
POST /api/login HTTP/1.1
Host: localhost:8080
Content-Type: application/json
X-CSRF-TOKEN: <csrf-token-from-current-session>
Cookie: JSESSIONID=<session-cookie>

{"username":"learner","password":"learner-pass"}
~~~

The two bracketed header values are **placeholders describing dynamically issued data**, not literal header values to send verbatim. The hands-on example includes commands to fetch a token and cookie via the `/csrf` endpoint before POSTing.

The system should accept only:

| Factor | Accepted | Rejected or Not Treated as Login |
| --- | --- | --- |
| Path | Exact /api/login path of the Servlet app | /api/login/extra, /api/login-debug, /other |
| Method | POST | GET, HEAD, PUT, PATCH, DELETE, OPTIONS unless covered by a separate contract |
| Content-Type | application/json, optionally with charset=UTF-8 | text/plain, application/x-www-form-urlencoded, multipart/form-data, application/xml, missing Content-Type |
| Body | JSON object with two well-formed string properties username and password | Malformed JSON, array, missing properties, non-string values |
| Body size | Within published threshold | Oversized payload |
| Credentials | Verified by AuthenticationManager | Wrong username/password, locked/expired user per policy |
| CSRF for browser sessions | Valid token per active mechanism | Missing or invalid token |

**Important:** enforcing the HTTP contract **does not mean** authentication succeeded. A POST request with the right path and Content-Type can still carry the wrong password, leading to **401**. Valid JSON can still receive **403** before reaching the login filter if the CSRF token is missing.

### Why Separate the Three Boundaries?

- **Path** determines which feature handles the request. If a filter applies to all `/api/**`, tokens/passwords could be misread on other endpoints.
- **Method** determines the operation. GET must have no login side effects and must never pass passwords in URL query strings.
- **Content-Type** declares the **request body** representation. It selects the parser and rejects formats the API does not support.
- **Body validation** ensures the data **inside** JSON has the right structure; `Content-Type: application/json` alone does not guarantee the body is valid JSON.
- **CSRF** is a separate safeguard when browsers automatically send cookies/credentials; it can run before the login filter.
- **Post-login authorization** controls resource access and cannot be replaced merely by validating the login method.

## 3. Distinguishing Request Path from Query String and Context Path

A URL can contain scheme, host, context path, servlet path, path info, and query string. When using Spring Security Servlet request matchers, understand which path the matcher observes in your deployment configuration.

For example, an app running at root context:

~~~text
http://localhost:8080/api/login?source=web
                      ^^^^^^^^^^  ^^^^^^^^^^
                      path        query string
~~~

Typically a matcher for **/api/login** inspects the path segment, **without treating the query string as part of the path name**. Thus **POST /api/login?source=web** can still enter the login filter, whereas **POST /api/login/extra** is not treated as login if the matcher uses an exact path.

If the app is deployed under context path **/shop**, the request URL is **/shop/api/login**, while Spring Security matchers typically operate on the in-app path **/api/login**. Do not write code comparing the full absolute URL against a fixed string containing hostname, port, or query string.

In Spring Security 6, you can use a `RequestMatcher` suited to your path/method configuration; **AntPathRequestMatcher** is used in this lesson for compatibility with the illustrated Spring Security 6 version. In newer Spring Security releases, recommended matcher APIs may change; real projects must match their actual version.

### Exact Path vs Broad Patterns

| Matcher / Intent | Example Matched | Risk |
| --- | --- | --- |
| /api/login (exact) | /api/login | Narrow scope, suited for login |
| /api/login/** | May include /api/login/other | Too broad if there is only one endpoint |
| /api/** | Many API endpoints | May misread non-login requests |
| /** | Almost all requests | Unsuitable for typical login filters |

**Good rule:** a filter may be registered in a SecurityFilterChain, but the logic identifying the **login endpoint** must use a narrow matcher. Do not rely on class names or a controller living under `/api` to assume the filter handles only the right URL.

### Multiple SecurityFilterChains?

If an application defines multiple chains via **securityMatcher(...)** and **@Order**, a request enters only the **first matching chain**. Placing a custom login filter in a chain that **does not match /api/login** prevents the filter from running even if its internal matcher is correct. Conversely, an API chain with an overly broad matcher can intercept requests ahead of another chain intended for login.

Verify both the **chain-level matcher** and the **login filter matcher**; they are two distinct filtering layers.

## 4. HTTP Method: Allow Only POST into the Authentication Flow

### Why Not GET?

GET is intended for reading resources and can be prefetched, cached, saved in browser history, or invoked by crawlers. Putting username/password in a query string—such as **GET /api/login?password=...**—easily leaks secrets through URL logs, history, and transit. A successful login can also establish a SecurityContext/session, so it **must not** be a side effect of GET.

**POST** is suited for carrying credentials in the request body and expressing the login action. However, POST **does not provide security by itself**: you still need HTTPS, CSRF where appropriate, input validation, brute-force protection, and session management.

### 405 Method Not Allowed and the Allow Header

If **/api/login** exists but disallows GET:

~~~http
HTTP/1.1 405 Method Not Allowed
Allow: POST
Content-Type: application/json

{"error":"method_not_allowed"}
~~~

**405** indicates the method is unsupported on that resource; the response should include an **Allow** header listing supported methods. In apps with dedicated OPTIONS/CORS handling, behavior may vary by policy. Never convert GET into POST or authenticate despite a disallowed method.

**HEAD and OPTIONS:** HEAD shares characteristics with GET and must never trigger login. OPTIONS may be used for CORS preflight or discovery; in this simple example, the login filter does not treat it as a login request. When CORS is enabled, let the CORS layer handle OPTIONS per policy instead of blindly returning 405 to required frontend preflights.

### Is Configuring requestMatchers(POST, "/api/login") Enough?

Not necessarily. Configuring:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(HttpMethod.POST, "/api/login").permitAll()
    .anyRequest().authenticated()
);
~~~

only declares an **authorization rule** for a class of requests. It does not determine whether a **custom filter** runs on GET, nor does it automatically return 405 with Allow. A filter written without a method matcher can still attempt to process GET before AuthorizationFilter gets its turn.

**Protect where credentials are actually read**: the login filter/controller must check the method and stop processing if it is wrong. Authorization rules and authentication filters should align, but neither replaces the other.

## 5. Content-Type: Restricting the Request Body Format

### Content-Type Is Not Accept

| Header | Declared By | Purpose |
| --- | --- | --- |
| **Content-Type: application/json** | Client | Body being sent is JSON |
| **Accept: application/json** | Client | Client wants response formatted as JSON |
| **Content-Type: application/json** on response | Server | Response body is represented as JSON |

A client can send:

~~~http
POST /api/login HTTP/1.1
Content-Type: text/plain
Accept: application/json

{"username":"learner","password":"learner-pass"}
~~~

Even though the body looks like JSON and Accept is `application/json`, **the request Content-Type is still text/plain**, violating the contract. A JSON-restricted endpoint should return **415 Unsupported Media Type** instead of guessing the body and authenticating.

Error example:

~~~http
HTTP/1.1 415 Unsupported Media Type
Content-Type: application/json

{"error":"unsupported_media_type"}
~~~

**Content-Type can carry parameters**, such as **application/json;charset=UTF-8**. Never compare with `equals("application/json")` on the raw header, as that falsely rejects valid JSON requests with parameters.

In Spring Framework, use **MediaType.parseMediaType(...)** to parse and **MediaType.APPLICATION_JSON.isCompatibleWith(actual)** to test compatibility. If strict policy is needed, check the charset and restrict vendor subtypes separately. This exercise accepts **application/json** (with or without **charset=UTF-8**) and rejects explicitly declared non-UTF-8 charsets.

### What About application/*+json?

Some APIs use media types with the **+json** suffix, like **application/problem+json** or **application/vnd.company+json**. They do not automatically fall under the example's **application/json**-only contract. If your API intends to support them, **publish an explicit allowlist** and test accepted types; never loosen unconditionally just because a string contains "json".

### Valid JSON Does Not Guarantee Valid Schema

Examples that have `Content-Type: application/json` yet must not be accepted:

~~~json
["learner","learner-pass"]
~~~

~~~json
{"username":"learner"}
~~~

~~~json
{"username":"learner","password":123}
~~~

~~~json
{"username":"learner","password":"learner-pass","isAdmin":true}
~~~

A login endpoint with a two-string-field contract should reject JSON arrays, missing password, numeric password, or extra fields when a strict schema is intended. The example checks **JsonNode.isObject**, **root.size() == 2**, string types, lengths, and non-blank values.

**400 Bad Request** is the right code when the media type is valid but JSON syntax/structure is invalid. **415** is an unsupported media type issue. Never lump all errors into 401, since 401 is for **credential authentication failure**.

## 6. Processing Order: Validate Shape Before Authenticating

An intentional JSON login flow follows this order:

~~~text
HTTP request
  |
  v
SecurityFilterChain matching request
  |
  v
CsrfFilter checks token if request requires CSRF
  |               \
  |                +-- wrong/missing --> 403, login filter has not run
  v
Custom login filter
  |
  +-- path != /api/login --> forward to next filter in chain
  |
  +-- matching path, method != POST --> 405 + Allow: POST
  |
  +-- POST, unsupported Content-Type --> 415
  |
  +-- POST + JSON, body too large --> 413
  |
  +-- POST + JSON, invalid syntax/schema --> 400
  |
  v
AuthenticationManager.authenticate(...)
  |
  +-- AuthenticationException --> 401 (generic error, do not leak account)
  |
  +-- success
          |
          +-- session fixation / CSRF authentication strategy
          +-- create SecurityContext containing Authentication
          +-- SecurityContextRepository.saveContext before response commits
          |
          v
        HTTP 200 + JSON without password
~~~

**Note on ordering:** if CSRF is enabled and the token is missing, a POST request may receive **403 before** the custom filter checks Content-Type or body. That is not a parser bug; it is the decision of a security filter running earlier. When testing 415, 400, or 413 individually, provide a **valid CSRF token** if required by the system.

For API systems that use neither cookies nor any browser auto-sent credentials, CSRF policy may differ. However, never disable CSRF just because "the endpoint is JSON" or "session policy is STATELESS"; analyze how clients send credentials, CORS, cookies, and the threat model.

## 7. Choosing the Extension Layer: Controller, AuthenticationFilter, or Custom Filter?

Spring Security offers multiple ways to build login. You do not need to write a filter at all costs.

| Option | Suitable When | What You Must Handle Yourself |
| --- | --- | --- |
| MVC controller with @PostMapping(consumes="application/json") | Login is truly an MVC API and you want request mapping / 405 / 415 | AuthenticationManager, explicit SecurityContext save, session protection, CSRF, and success/failure |
| AuthenticationFilter with AuthenticationConverter, RequestMatcher | You want most of Spring Security's authentication flow/hooks | Matcher, converter, handlers, SecurityContextRepository, and appropriate session strategy |
| Custom AbstractAuthenticationProcessingFilter | You want the base class's success/failure/session hooks | Matcher, attemptAuthentication, and related components |
| Custom OncePerRequestFilter | You want to make every HTTP contract boundary explicit in SecurityFilterChain | Managing **all** responses, authentication, saving context, and session strategies |

This lesson uses **OncePerRequestFilter** so every path/method/media/body boundary is explicitly visible in code. In real products, prefer a **controller with proper consumes** or a standard authentication filter with extension points to reduce custom security code to maintain.

### Does Controller consumes Simplify the HTTP Contract?

A brief MVC routing snippet:

~~~java
// Illustrative fragment inside a @RestController that already has loginService.
@PostMapping(path = "/api/login", consumes = "application/json",
             produces = "application/json")
public LoginResponse login(@RequestBody LoginRequest body) {
    return loginService.login(body);
}
~~~

A controller can be selected by Spring MVC based on path, method, and consumes; mismatched MediaType usually returns 415, unsupported method usually returns 405. This is **only a fragment** without LoginResponse/LoginRequest/loginService definitions and does not handle session/CSRF/security itself, so it is not a standalone compilable program. **Filters run before MVC**; if a login filter indiscriminately processes every request, `@PostMapping(consumes=...)` on the controller **cannot protect that filter**.

## 8. Complete Spring Boot Project: JSON Login Exact Path + POST + application/json

### 8.1. Rules and Environment

Uses Java 17+, Maven, Spring Boot **3.3.13** (Spring Security 6), Spring Web, and Spring Security.

The demo accepts only:

- **POST /api/login**, Content-Type **application/json** with UTF-8.
- JSON object body with strictly String properties **username** and **password**.
- Body size at most **4096 bytes**.
- Sample accounts: **learner / learner-pass** with ROLE_USER; **admin / admin-pass** with ROLE_ADMIN.
- **GET /csrf** returns a CSRF token for the browser session prior to POST.
- **GET /me** requires a logged-in user; **GET /admin** requires ROLE_ADMIN.

The demo uses **HttpSessionSecurityContextRepository** to persist login across requests. CSRF **is enabled**, because browsers send session cookies automatically. After successful login, the example runs a session fixation strategy and refreshes the session's CSRF token; subsequent state-changing requests must fetch the new token as needed. Never create any HTTP endpoint returning password hashes, session IDs, or raw passwords.

### 8.2. Project Tree

~~~text
restricted-login-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/restrictedlogin/
    │   ├── RestrictedLoginApplication.java
    │   ├── SecurityConfig.java
    │   ├── JsonLoginFilter.java
    │   └── DemoController.java
    └── test/java/com/example/restrictedlogin/
        └── RestrictedLoginTest.java
~~~

### 8.3. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>restricted-login-demo</artifactId>
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
~~~

### 8.4. RestrictedLoginApplication.java

~~~java
package com.example.restrictedlogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RestrictedLoginApplication {

    public static void main(String[] args) {
        SpringApplication.run(RestrictedLoginApplication.class, args);
    }
}
~~~

Classes reside in the same `com.example.restrictedlogin` package so Spring Boot discovers configuration and controllers.

### 8.5. JsonLoginFilter.java

The following filter handles strictly **/api/login**. For other paths, it calls `filterChain.doFilter` so other endpoints proceed. If the path matches but the method is not POST, it returns 405. For POST, it validates Content-Type, body size, UTF-8, and JSON schema **before calling AuthenticationManager**.

~~~java
package com.example.restrictedlogin;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;
import org.springframework.web.filter.OncePerRequestFilter;

public final class JsonLoginFilter extends OncePerRequestFilter {

    private static final int MAX_BODY_BYTES = 4096;
    private static final RequestMatcher LOGIN_PATH =
        new AntPathRequestMatcher("/api/login");

    private final AuthenticationManager manager;
    private final ObjectMapper mapper;
    private final SecurityContextRepository repository;
    private final SessionAuthenticationStrategy sessionStrategy;

    public JsonLoginFilter(
            AuthenticationManager manager,
            ObjectMapper mapper,
            SecurityContextRepository repository,
            SessionAuthenticationStrategy sessionStrategy) {

        this.manager = manager;
        this.mapper = mapper;
        this.repository = repository;
        this.sessionStrategy = sessionStrategy;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        // 1. Accept only the exact login path. Do not touch other requests.
        if (!LOGIN_PATH.matches(request)) {
            chain.doFilter(request, response);
            return;
        }

        // 2. Only POST is allowed to perform authentication.
        if (!"POST".equals(request.getMethod())) {
            response.setHeader("Allow", "POST");
            sendJson(response, 405, Map.of("error", "method_not_allowed"));
            return;
        }

        // 3. Content-Type must be in JSON allowlist, UTF-8 charset if declared.
        String rawType = request.getContentType();
        if (rawType == null) {
            sendJson(response, 415, Map.of("error", "unsupported_media_type"));
            return;
        }

        MediaType actual;
        try {
            actual = MediaType.parseMediaType(rawType);
        } catch (IllegalArgumentException ex) {
            sendJson(response, 415, Map.of("error", "unsupported_media_type"));
            return;
        }

        if (!MediaType.APPLICATION_JSON.isCompatibleWith(actual)
                || (actual.getCharset() != null
                    && !StandardCharsets.UTF_8.equals(actual.getCharset()))) {

            sendJson(response, 415, Map.of("error", "unsupported_media_type"));
            return;
        }

        // 4. Read up to 4097 bytes to detect bodies exceeding 4096 bytes.
        byte[] body = request.getInputStream().readNBytes(MAX_BODY_BYTES + 1);
        if (body.length > MAX_BODY_BYTES) {
            sendJson(response, 413, Map.of("error", "payload_too_large"));
            return;
        }

        // 5. Reject bytes that are not valid UTF-8.
        String json;
        try {
            json = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(body))
                .toString();
        } catch (CharacterCodingException ex) {
            sendJson(response, 400, Map.of("error", "invalid_json"));
            return;
        }

        // 6. Parse JSON and disallow trailing JSON content.
        JsonNode root;
        try {
            root = mapper.readerFor(JsonNode.class)
                .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
                .readValue(json);
        } catch (JsonProcessingException ex) {
            sendJson(response, 400, Map.of("error", "invalid_json"));
            return;
        }

        // 7. Only an object with exactly two string properties.
        if (root == null || !root.isObject() || root.size() != 2
                || root.get("username") == null
                || root.get("password") == null
                || !root.get("username").isTextual()
                || !root.get("password").isTextual()) {

            sendJson(response, 400, Map.of("error", "invalid_login_body"));
            return;
        }

        String username = root.get("username").asText();
        String password = root.get("password").asText();

        if (username.isBlank() || username.length() > 100
                || password.isBlank() || password.length() > 256) {

            sendJson(response, 400, Map.of("error", "invalid_login_body"));
            return;
        }

        // 8. Only now request credential verification.
        try {
            Authentication verified = manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    username, password));

            // Integrate session policy for custom login.
            sessionStrategy.onAuthentication(verified, request, response);

            SecurityContext context =
                SecurityContextHolder.createEmptyContext();
            context.setAuthentication(verified);
            SecurityContextHolder.setContext(context);

            // Spring Security 6: must save explicitly if next request uses session.
            repository.saveContext(context, request, response);

            // Never return raw password or password hash.
            sendJson(response, 200, Map.of(
                "username", verified.getName(),
                "authenticated", true));

        } catch (AuthenticationException ex) {
            SecurityContextHolder.clearContext();
            // Generic message; never disclose whether the username exists.
            sendJson(response, 401, Map.of("error", "invalid_credentials"));
        }
    }

    private void sendJson(
            HttpServletResponse response,
            int status,
            Map<String, ?> body) throws IOException {

        response.setStatus(status);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        mapper.writeValue(response.getOutputStream(), body);
    }
}
~~~

**Key points in the filter:**

1. **new AntPathRequestMatcher("/api/login")** identifies the endpoint path rather than matching `/**` or `/api/**`.
2. Method branching occurs **after the path matches**: GET/PUT to `/api/login` returns 405 with `Allow: POST`. Requests to other paths are forwarded without being misread by the filter.
3. **MediaType.parseMediaType** accepts `application/json` with charset parameters rather than doing naive raw string comparisons. Only UTF-8 and allowlisted JSON are permitted.
4. **readNBytes(4097)** bounds the actual bytes read in the filter instead of trusting client-declared `Content-Length`. Bodies exceeding the threshold return 413 before parsing.
5. **CharsetDecoder** errors if the body is not valid UTF-8. JsonNode/strict reader handles JSON syntax; schema checks verify two String fields.
6. **AuthenticationManager** verifies username/password via its provider. Never compare passwords manually with `equals`.
7. **SessionAuthenticationStrategy** and **SecurityContextRepository** must be used explicitly because this is custom login, bypassing the default `formLogin` UsernamePasswordAuthenticationFilter.
8. **401** applies only to `AuthenticationException` during credential verification; method/media/body errors return their own statuses. This is the demo's API contract choice, not a rule forcing every app to return these exact error bodies.
9. **sendJson** sets JSON Content-Type on the response, distinct from the client-sent Content-Type.
10. **JsonLoginFilter is not annotated with @Component or @Bean** in the demo; it is added **once** to SecurityFilterChain. Both auto-registering as a Servlet filter and calling `addFilterBefore` risks running the filter twice.

**Example limitations:** checking a two-field JSON object and `FAIL_ON_TRAILING_TOKENS` does not automatically reject every duplicate-key JSON payload. In strict-schema production APIs, enable Jackson's duplicate detection and design clear input error handling. The example does not implement rate limiting, auditing, lockout, CORS, captcha, MFA, or distributed account controls; add those per your threat model.

### 8.6. SecurityConfig.java

~~~java
package com.example.restrictedlogin;

import java.util.List;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.CompositeSessionAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfAuthenticationStrategy;
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("learner-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(learner, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ObjectMapper mapper,
            UserDetailsService users,
            PasswordEncoder encoder) throws Exception {

        DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(encoder);
        AuthenticationManager manager = new ProviderManager(provider);

        SecurityContextRepository contextRepository =
            new HttpSessionSecurityContextRepository();

        CsrfTokenRepository csrfRepository =
            new HttpSessionCsrfTokenRepository();

        SessionAuthenticationStrategy sessionStrategy =
            new CompositeSessionAuthenticationStrategy(List.of(
                new ChangeSessionIdAuthenticationStrategy(),
                new CsrfAuthenticationStrategy(csrfRepository)
            ));

        JsonLoginFilter loginFilter = new JsonLoginFilter(
            manager, mapper, contextRepository, sessionStrategy);

        http
            .securityContext(context ->
                context.securityContextRepository(contextRepository))
            .csrf(csrf -> csrf.csrfTokenRepository(csrfRepository))
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/csrf").permitAll()
                .requestMatchers("/api/login", "/error").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .exceptionHandling(exception -> exception
                .authenticationEntryPoint(
                    new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .addFilterBefore(
                loginFilter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }
}
~~~

**Reading the configuration by goal:**

- **DaoAuthenticationProvider** verifies credentials with UserDetailsService and BCryptPasswordEncoder, without storing raw passwords in a database.
- **ProviderManager** is the AuthenticationManager used directly by the custom login filter.
- **HttpSessionSecurityContextRepository** is attached to both the login filter (save) and the chain's `securityContext` (load). Saving in one place while loading from another causes follow-up requests to lose login state.
- **CsrfTokenRepository** uses HttpSession; login POST passes through **CsrfFilter** before the custom filter. The example does not disable CSRF.
- **CompositeSessionAuthenticationStrategy** rotates the session ID appropriately to mitigate session fixation and refreshes the CSRF token after authentication. The custom filter must explicitly invoke `sessionStrategy.onAuthentication(...)`.
- **IF_REQUIRED** allows sessions when needed; the demo intentionally uses session login rather than a stateless token API.
- **requestMatchers("/api/login").permitAll()** allows unauthenticated requests to reach the login filter, without **automatically opening all methods/media types**. Those constraints are enforced by the filter.
- **/me** requires only authenticated; **/admin** requires ROLE_ADMIN. **anyRequest().denyAll()** reduces the risk of new endpoints accidentally becoming public.
- **HttpStatusEntryPoint(401)** returns status when an unauthenticated request hits a protected URL without redirecting to a form login page. No Basic challenge is used because `httpBasic` is disabled.
- **formLogin/httpBasic disabled** prevents other login mechanisms from accidentally claiming credentials in this exercise.
- **addFilterBefore** inserts the login filter before UsernamePasswordAuthenticationFilter's position in the chain's order. This is a Spring Security anchor position, not a claim that the formLogin filter is enabled.
- The filter is instantiated inside the configuration method—**not** declared as `@Bean` or `@Component`—to avoid the Servlet container auto-registering it a second time.

**Note on session fixation:** changing the session ID only makes sense when an appropriate session exists; in the example, `GET /csrf` creates a session before login. Production may also require concurrent session limits, session invalidation, remember-me, auditing, MFA, and specific policies; do not assume the sample CompositeSessionAuthenticationStrategy covers every login scenario.

### 8.7. DemoController.java

~~~java
package com.example.restrictedlogin;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/csrf")
    public Map<String, String> csrf(
            @RequestAttribute("_csrf") CsrfToken token) {

        return Map.of(
            "headerName", token.getHeaderName(),
            "token", token.getToken());
    }

    @GetMapping("/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @GetMapping("/admin")
    public Map<String, String> admin() {
        return Map.of("message", "admin-ok");
    }
}
~~~

**/csrf** is an endpoint supporting the CSRF session illustration: it reads the token placed by Spring Security in a request attribute and returns it to a client sharing the same session. Accessing the token can trigger deferred CSRF token generation/saving. For production frontends, consider the cookie/header model and never open CORS indiscriminately so untrusted sites can read the token.

**/me** reads the authenticated Authentication from the context. It does not accept raw username/password or try to invoke PasswordEncoder itself. **/admin** is protected by the `ROLE_ADMIN` rule.

This is a session-login example; if you need a sessionless bearer-token API, design OAuth2 Resource Server/token issuance under its own model rather than changing `IF_REQUIRED` to `STATELESS` and expecting `saveContext` to keep working across requests.

## 9. End-to-End HTTP Testing with curl

Start from the project directory:

~~~bash
mvn spring-boot:run
~~~

The example uses `http://localhost:8080` strictly **on a development machine**. With real credentials or over the Internet, **HTTPS** is mandatory. The following shell commands use bash syntax and **jq** to parse JSON; on PowerShell you can use `curl.exe` and `ConvertFrom-Json`, or use Postman/an equivalent HTTP client.

### 9.1. Fetch CSRF Token and Session Cookie

~~~bash
TOKEN=$(curl -sS -c cookies.txt http://localhost:8080/csrf | jq -r '.token')
~~~

`GET /csrf` can cause the server to create a session; **cookies.txt** records the session reference cookie so the subsequent POST sends it back for the same session. `TOKEN` is the token received in JSON, not a password or API-authorizing bearer token.

### 9.2. POST JSON Login Matching the Contract

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  -H "X-CSRF-TOKEN: $TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"username":"learner","password":"learner-pass"}' \
  http://localhost:8080/api/login
~~~

Expected **HTTP 200**, JSON with **username=learner**, **authenticated=true**. The server may rotate the session ID or update the session cookie. The command uses both **-b** and **-c** to send and save the rotated cookie for subsequent requests.

### 9.3. Use the Newly Logged-In Session

~~~bash
curl -i -b cookies.txt http://localhost:8080/me
~~~

Expected **200** with `username=learner`. Without sending the session cookie, an unauthenticated `GET /me` typically gets **401**.

~~~bash
curl -i http://localhost:8080/me
~~~

### 9.4. Wrong Method on the Exact Path

~~~bash
curl -i -b cookies.txt http://localhost:8080/api/login
~~~

Expected **405 Method Not Allowed**, header **Allow: POST**. The custom login filter does not turn GET into a login operation.

### 9.5. Wrong Content-Type with Valid CSRF

To isolate the media type error, fetch a fresh session/token from `GET /csrf` (the token from the prior login may have been rotated):

~~~bash
TOKEN=$(curl -sS -b cookies.txt -c cookies.txt \
  http://localhost:8080/csrf | jq -r '.token')

curl -i -b cookies.txt \
  -H "X-CSRF-TOKEN: $TOKEN" \
  -H "Content-Type: text/plain" \
  --data '{"username":"learner","password":"learner-pass"}' \
  http://localhost:8080/api/login
~~~

Expected **415 Unsupported Media Type**. Even though the body looks like JSON, the `text/plain` header violates the contract.

### 9.6. Malformed JSON Structure

~~~bash
curl -i -b cookies.txt \
  -H "X-CSRF-TOKEN: $TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"username":"learner"}' \
  http://localhost:8080/api/login
~~~

Expected **400 Bad Request** because the `password` field is missing. Syntactically invalid JSON, such as missing braces, also yields 400. If the CSRF token has already expired/rotated, the server may return 403 before body validation; fetch a fresh token to test the intended branch.

### 9.7. Valid JSON but Wrong Password

~~~bash
curl -i -b cookies.txt \
  -H "X-CSRF-TOKEN: $TOKEN" \
  -H "Content-Type: application/json;charset=UTF-8" \
  --data '{"username":"learner","password":"wrong-pass"}' \
  http://localhost:8080/api/login
~~~

With a valid CSRF token, expected **401 Unauthorized** with generic error **invalid_credentials**. Never disclose whether the user exists.

### 9.8. POST Missing CSRF

~~~bash
curl -i -b cookies.txt \
  -H "Content-Type: application/json" \
  --data '{"username":"learner","password":"learner-pass"}' \
  http://localhost:8080/api/login
~~~

Expected **403 Forbidden** from CSRF protection when no token is sent. That is intentional security behavior. Never fix it by disabling CSRF globally when endpoints use browser session cookies.

### 9.9. Similar-Looking Path

~~~bash
curl -i -b cookies.txt \
  -H "Content-Type: application/json" \
  --data '{"username":"learner","password":"learner-pass"}' \
  http://localhost:8080/api/login/extra
~~~

The custom login filter **ignores this path**. The final status depends on the app's authorization rules/handlers (typically 401 for anonymous or unmapped routes); what must be proven is that login logic does not run and no new session is saved. Never assume every unmatched path must return 404: `SecurityFilterChain` can deny before reaching MVC.

## 10. MockMvc Integration Testing

Create **src/test/java/com/example/restrictedlogin/RestrictedLoginTest.java**. The tests use **spring-security-test** to supply a valid CSRF token via **with(csrf())** when isolating method, Content-Type, body, or credential branches.

~~~java
package com.example.restrictedlogin;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class RestrictedLoginTest {

    @Autowired
    MockMvc mvc;

    private static final String VALID_BODY =
        "{\"username\":\"learner\",\"password\":\"learner-pass\"}";

    @Test
    void onlyExactLoginPathCanAuthenticate() throws Exception {
        mvc.perform(post("/api/login/extra")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID_BODY))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void getLoginReturns405AndAllowPost() throws Exception {
        mvc.perform(get("/api/login"))
            .andExpect(status().isMethodNotAllowed())
            .andExpect(header().string("Allow", "POST"))
            .andExpect(jsonPath("$.error")
                .value("method_not_allowed"));
    }

    @Test
    void wrongContentTypeReturns415() throws Exception {
        mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content(VALID_BODY))
            .andExpect(status().isUnsupportedMediaType())
            .andExpect(jsonPath("$.error")
                .value("unsupported_media_type"));
    }

    @Test
    void invalidJsonBodyReturns400() throws Exception {
        mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"learner\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error")
                .value("invalid_login_body"));
    }

    @Test
    void oversizedBodyReturns413() throws Exception {
        String bigBody = "x".repeat(4097);

        mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(bigBody))
            .andExpect(status().isPayloadTooLarge())
            .andExpect(jsonPath("$.error")
                .value("payload_too_large"));
    }

    @Test
    void missingCsrfReturns403BeforeCustomLoginFilter()
            throws Exception {

        mvc.perform(post("/api/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID_BODY))
            .andExpect(status().isForbidden());
    }

    @Test
    void wrongPasswordReturns401() throws Exception {
        mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"learner\","
                    + "\"password\":\"wrong-pass\"}"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error")
                .value("invalid_credentials"));
    }

    @Test
    void validJsonLoginCreatesSessionForNextRequest()
            throws Exception {

        MvcResult login = mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID_BODY))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("learner"))
            .andExpect(jsonPath("$.authenticated").value(true))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("learner"));

        mvc.perform(get("/admin").session(session))
            .andExpect(status().isForbidden());

        // New request does not carry the logged-in session.
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void csrfEndpointReturnsToken() throws Exception {
        mvc.perform(get("/csrf"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.headerName")
                .value("X-CSRF-TOKEN"))
            .andExpect(jsonPath("$.token").isString());
    }
}
~~~

Run inside the project directory:

~~~bash
mvn test
~~~

**What the tests verify:**

- Path `/api/login/extra` is **not** treated as login; with the demo's denyAll/entry point config and anonymous user, it is rejected.
- GET on the right path returns **405** with `Allow: POST`.
- POST with `Content-Type: text/plain` returns **415**.
- POST with JSON missing a field returns **400**.
- Payloads over 4096 bytes return **413**.
- POST missing CSRF returns **403**, before reaching the login filter.
- POST with valid JSON but wrong password returns **401**.
- Valid POST + valid CSRF creates a SecurityContext saved in the session; `GET /me` with the same session succeeds, `GET /admin` as `ROLE_USER` returns **403**, and `GET /me` without a session returns **401**.
- `GET /csrf` provides a token for clients sharing the same session.

**Note on testing unmatched paths:** the final HTTP status comes from the demo's authorization rule, not from `JsonLoginFilter` itself returning 401. To assert the filter never calls `AuthenticationManager` for other paths in larger systems, add controlled mocks/spies or authentication-attempt metrics; do not rely solely on status codes.

### Testing Parameterized Content-Types

Beyond the tests above, add a case for **application/json;charset=UTF-8** to confirm the media-type parser accepts valid parameters, and **application/json;charset=ISO-8859-1** to confirm 415 per demo policy. When frontends need **application/vnd.company+json**, update the allowlist intentionally and retest; never silently allow all subtypes.

## 11. Why @PostMapping Alone Is Not Enough to Protect a Custom Filter

Suppose a login controller has:

~~~java
@PostMapping(path = "/api/login", consumes = "application/json")
public ResponseEntity<?> login(@RequestBody LoginRequest request) {
    // Illustrative fragment; requires LoginRequest and appropriate login logic.
    return ResponseEntity.ok().build();
}
~~~

In MVC, `@PostMapping` and `consumes` provide good request mapping. However, if you **also** configure a custom filter on `/**` that reads passwords and invokes `AuthenticationManager` before entering `DispatcherServlet`, controller mapping annotations cannot stop that filter from running on `GET /api/login` or `POST /api/other`.

When using a filter:

- Choose a narrow matcher **inside the filter** or use `AuthenticationFilter` with an exact `RequestMatcher`.
- Select the appropriate `SecurityFilterChain` **at the chain level**.
- Maintain consistent authorization rules **at the request level**.
- Never let the filter read the body of other endpoints; servlet bodies can generally only be read once without an appropriate wrapper.
- If 405/415 is required by contract, explicitly define which component returns them (MVC or filter) rather than relying on a `permitAll` rule.

## 12. Why Not Check Content Type Using request.getHeader("Accept") Alone?

**Accept** represents the format the client wants in the response; it does not prove the request body is JSON. A request can send `Accept: application/json` alongside `Content-Type: application/x-www-form-urlencoded`. Conversely, a client sending `Content-Type: application/json` with `Accept: */*` still sends a valid JSON body.

In the demo:

- To decide **whether to parse a JSON login body**, inspect `Content-Type`.
- To decide **what format the response returns**, you can inspect `Accept` or publish that the API always returns JSON per contract.
- To validate **JSON data**, parse and validate the body.
- To verify **identity**, call `AuthenticationManager`.
- To check **permissions**, use `authorizeHttpRequests` and/or method security.

These four questions are distinct; mixing them can cause false 401s, false 415s, or misread bodies.

## 13. 400, 401, 403, 405, 413, 415: Do Not Collapse All Errors into 401

| Status | Typical Condition in Demo | Practical Meaning |
| --- | --- | --- |
| **200 OK** | Contract-compliant POST, valid CSRF, valid credentials | Login succeeded |
| **400 Bad Request** | Invalid JSON syntax/schema, wrong username/password types | Invalid request body |
| **401 Unauthorized** | Wrong credentials, or accessing login-protected resource without session | Authentication not accepted |
| **403 Forbidden** | POST missing CSRF, or logged-in user lacking ROLE_ADMIN | Security/authorization policy denied |
| **405 Method Not Allowed** | GET/PUT/... sent to exact /api/login | Method unsupported; includes `Allow: POST` |
| **413 Content Too Large** | JSON body over 4096 bytes | Server rejected payload size |
| **415 Unsupported Media Type** | Content-Type text/plain, XML, form, or missing header | Request body type not in allowlist |

**Error ordering is not immutable.** `CsrfFilter` running before `JsonLoginFilter` can return 403 for a POST missing a token even if the body also has the wrong Content-Type. In CORS-enabled systems, preflight OPTIONS can be handled earlier than the custom filter. Therefore, tests for every status must construct requests satisfying earlier conditions to isolate the branch under test.

**413 and 415 are not password errors.** Never invoke `AuthenticationManager` when you already know the payload is oversized or the media type is unsupported.

**401 from the login endpoint** must never disclose whether the username exists, account status, hashes, or overly detailed "right/wrong password" messages. Generic responses mitigate username enumeration; protected internal audits can distinguish causes at an appropriate level.

## 14. Session, CSRF, Cookies, and Saving SecurityContext in Custom Login

When writing a custom authentication filter instead of using the standard form login filter, **succeeding in the current request does not automatically keep the next request logged in**.

Flow to understand:

~~~text
POST /api/login (valid CSRF + right credentials)
  |
  +-- AuthenticationManager creates Authentication
  +-- SessionAuthenticationStrategy handles login-related session
  +-- SecurityContextHolder.setContext(context)
  +-- SecurityContextRepository.saveContext(context, request, response)
  |
  +-- response 200, session cookie is maintained
          |
          v
GET /me + same session cookie
  |
  +-- SecurityContextHolderFilter/repository loads saved context
  +-- Authentication has valid identity
  +-- authorization for /me
~~~

In Spring Security 6, **SecurityContextHolderFilter** does not automatically save every context change when the request finishes. Calling `setContext` without an appropriate `saveContext` may let the current request know the user while subsequent requests lose login state.

**Session fixation:** login elevates the privilege level of a session. When a session existed before login, you need a session ID rotation policy or equivalent protection. A custom filter does not automatically inherit every hook of `UsernamePasswordAuthenticationFilter`, so the exercise invokes the session strategy explicitly.

**CSRF:** browsers automatically send session cookies under matching conditions, so login POSTs and state-changing operations require CSRF consideration. The demo retains CSRF and exposes `GET /csrf`. If custom login rotates the CSRF token on success, clients must fetch the new token before the next POST.

**Cookie attributes:** production requires HTTPS/`Secure`, `HttpOnly`, appropriate `SameSite`, session timeout, and proper logout. Never log `JSESSIONID` or put it in URLs.

**MFA/rate limits:** real login endpoints may need MFA, brute-force throttling, lockouts/alerts, anomaly detection, and account protection policies. Restricting path/method/media shrinks the error surface, **but does not replace those controls**.

## 15. Notable Implementation Differences and Nuances

### 15.1. Should RequestMatcher Replace the Content-Type Check?

No. A `RequestMatcher` can combine path and method, or even inspect headers, yet **JSON parsing and validation** must still run before authentication. If you put Content-Type into the matcher and let the filter skip completely when the media type is wrong, the request can fall through to `authorizeHttpRequests` and return inconsistent 401/403/404 codes instead of 415 per API contract.

In the demo, the matcher matches only the path; method and media type are checked inside to produce clear status codes.

### 15.2. Does requestMatchers(...).permitAll "Open Login to Every Method"?

`permitAll` governs **authorization** if a request reaches that step; it does not force a custom filter to authenticate wrong methods. Nor does it stop a custom filter from running; returning 405 requires explicit design in the filter or MVC mapping. In the demo, the filter blocks non-POST methods before reaching the controller.

### 15.3. Should CSRF Be Disabled for /api/login?

Not as a knee-jerk reaction. If login creates a session using browser cookies, login CSRF and CSRF for post-login actions still require analysis. The demo keeps CSRF globally to illustrate this. If an app is a stateless token API not using cookies/browser auto-sent credentials, a different policy may apply, backed by a threat model and security tests.

### 15.4. Should GET /api/login Be Allowed to Render a Form?

In traditional **form login** apps, `GET /login` may be a public HTML page while `POST /login` performs authentication. In this lesson's **JSON API login**, `/api/login` serves strictly for POST authentication; if a separate HTML page is needed, place it on another route like `GET /login-page` to avoid ambiguity.

### 15.5. Should application/x-www-form-urlencoded Be Accepted Instead of JSON?

Yes, **if that is an intentional contract**. Built-in `UsernamePasswordAuthenticationFilter` reads form parameters using its own mechanism by default; custom JSON login should not silently fall back to forms when Content-Type is wrong. If supporting both, publish both media types, two parsers, CSRF tests, and clear precedence rules.

### 15.6. Must JSON Bodies Always Be Under 4096 Bytes?

No. The 4096 threshold is an **illustrative value** for two short strings. In real systems, choose a limit based on contract, header/proxy limits, DoS resilience, and i18n needs. Never allow unbounded bodies into an object mapper or log entire bodies when investigating errors.

### 15.7. Should 404 Be Returned Instead of 401 for Unknown Paths?

That is a security/API design decision. In the demo, unknown paths hit `anyRequest().denyAll()` and anonymous callers get 401 from the entry point; controllers may never be invoked. If you want 404 for non-existent routes, design rules/exception handling intentionally instead of relying on the login filter to guess.

### 15.8. Should Content-Length Be Used as the Sole Check?

No. Clients may omit `Content-Length` (chunked transfer), or the header may not reflect actual bytes across all paths. The demo bounds **the actual bytes read** via `readNBytes(MAX_BODY_BYTES+1)`, detecting overflows even without `Content-Length`.

### 15.9. Should Unicode Characters in Username/Password Be Validated?

Define an explicit policy: length, normalization, allowed characters, and consistent Unicode handling. Never automatically trim or alter user-entered passwords, as whitespace can be valid in passwords. The demo rejects only all-whitespace or oversized values; production needs a concrete contract and must consider username canonicalization.

### 15.10. Should Accept Be Validated?

If an API contract only returns JSON and a client sends an incompatible `Accept`, the server can apply content negotiation and return `406 Not Acceptable`. The demo fixes JSON responses for brevity; this lesson focuses on **request Content-Type**, without claiming full `Accept` negotiation support.

## 16. Troubleshooting

| Symptom | Common Cause | How to Verify |
| --- | --- | --- |
| GET /api/login also performs login | Custom filter checks only path, forgot method | Check POST condition inside filter |
| POST /api/login/extra performs login | Matcher `/**` or `/api/login/**` too broad | Use exact path matcher and negative-path tests |
| POST text/plain still logs in | JSON parser invoked without Content-Type validation | MediaType allowlist, test 415 |
| POST application/json;charset=UTF-8 rejected | Comparing Content-Type string with `equals` | Parse `MediaType` instead of raw string equality |
| Malformed JSON causes 500 | Unhandled parse/schema errors | Return 400; validate types, lengths, fields |
| Huge body consumes server memory | Unbounded byte reads, trusting Content-Length | Enforce limits at gateway/container and filter |
| Valid login POST receives 403 | Missing or invalid CSRF token | `GET /csrf`, same-session cookie, send `X-CSRF-TOKEN` |
| Login succeeds yet /me returns 401 | Only called `SecurityContextHolder`, forgot `saveContext` or lost cookie | Check repository, session ID, and follow-up request |
| Wrong password returns 400 | Mixing credentials with request body errors | Separate 400 schema errors from 401 auth errors |
| Login endpoint returns 302 redirect | `formLogin` entry point or another chain intervened | Inspect `SecurityFilterChain`, `formLogin`/`httpBasic`, `exceptionHandling` |
| Filter runs twice | `@Component`/`@Bean` caused Servlet registration plus `SecurityFilterChain` addition | Register once, inspect chains |
| /api/login never enters filter | Chain `securityMatcher` did not match, wrong filter order | Check first matching chain and filter insertion |
| Proxy drops Content-Type/CSRF/headers | Gateway modified or failed to forward headers/cookies | Inspect proxy config; never log raw secrets |
| OPTIONS preflight gets 405/403 | CORS not configured for cross-origin frontend | Configure CORS/OPTIONS explicitly without loosening blindly |

**Recommended debugging workflow:**

1. Reproduce with a request specifying clear method/path/Content-Type and **test credentials**.
2. Identify which `SecurityFilterChain` is selected.
3. Check whether CSRF/CORS stops the request before the custom filter.
4. Check path matcher (exact match?), then method.
5. Verify media allowlist, charset, and byte count.
6. Parse/validate schema before `AuthenticationManager`.
7. If reaching auth, check `UserDetailsService`, `PasswordEncoder`, and `AuthenticationException`s.
8. On auth success, verify `SessionAuthenticationStrategy` and `repository.saveContext` before response commit.
9. Verify follow-up requests send the right-scoped cookie and the session remains valid.
10. Lock behavior with MockMvc/integration tests; never fix errors by disabling security globally.

## 17. Practice Exercises

### Exercise A — Distinguishing Matcher and Authorization

A custom filter uses matcher `/**`, while security config only has `permitAll` on `POST /api/login`. Can a `GET /api/users` request have its body read by the filter before reaching `AuthorizationFilter`?

**Answer:** Yes. The `permitAll` rule does not constrain filters running earlier. You must restrict the filter using an exact path/method matcher or enforce the contract inside.

### Exercise B — Content-Type and Accept

A request sends **Content-Type: text/plain**, **Accept: application/json**, and a JSON body. Which header determines whether to parse the JSON login body? Under a JSON-only contract, which status fits?

**Answer:** Check **Content-Type**, and return 415 because `text/plain` is unsupported; `Accept` only describes the desired response.

### Exercise C — Can Charsets Be Accepted?

A `POST /api/login` request sends **Content-Type: application/json;charset=UTF-8**. Why is string equality against `"application/json"` wrong?

**Answer:** Media types can include valid parameters. Use `MediaType.parseMediaType` and check compatibility/charset policy.

### Exercise D — 405 or 401?

An unauthenticated user calls **GET /api/login**. In the demo, why is the response 405 instead of 401?

**Answer:** The request matches the exact login path, and the filter enforces the method contract before requiring authentication; `GET` is unsupported, so it returns 405 + `Allow: POST`. If a filter does not handle this case, the status can differ depending on authorization config.

### Exercise E — CSRF Runs Before Media Validation

`POST /api/login` with `Content-Type: text/plain` and no CSRF token. Can the demo return 403 instead of 415? Why?

**Answer:** Yes. `CsrfFilter` rejects the request before `JsonLoginFilter` inspects the media type. To test 415, you must send a valid CSRF token.

### Exercise F — Accessing an Unknown Path

Will `POST /api/login/extra` with valid JSON credentials log in? Is it guaranteed to return 404?

**Answer:** It will not log in, because the exact `/api/login` matcher rejects `/api/login/extra`. The final status is determined by `SecurityFilterChain`/authorization/MVC, and is not always 404.

### Exercise G — Login Succeeds but Next Request Loses State

A custom filter calls `manager.authenticate` and `SecurityContextHolder.setContext`, returns 200, yet skips `saveContext`. Why can `GET /me` with the cookie still return 401?

**Answer:** In Spring Security 6 with explicit save, `setContext` for the current request does not persist the session automatically. You must call `repository.saveContext` before the response commits and use the matching repository to load it.

### Exercise H — Body Limits and Encoding

A client sends `Content-Type: application/json` with a 5000-byte body or non-UTF-8 bytes. What does the demo return?

**Answer:** A body over 4096 bytes returns 413; if within size yet invalid UTF-8 encoding, it returns 400. Missing CSRF can return 403 earlier.

### Exercise I — Writing an Insufficient-Permission Test

After `learner` logs in successfully, that session calls `GET /admin`. What status is returned? Does it mean the password was wrong?

**Answer:** 403 because `learner` holds `ROLE_USER` whereas the endpoint requires `ROLE_ADMIN`; the password was already verified successfully earlier.

### Exercise K — Multi-Chain Deployment Thinking

Chain `@Order(1)` matches `/api/**` and chain `@Order(2)` matches `/**`, yet custom `JsonLoginFilter` was added only to the second chain. Will `POST /api/login` pass through the filter in the second chain?

**Answer:** No, because the first chain already matched. You must place the filter in the chain handling `/api/login` or fix the matcher/ordering strategy.

## 18. Pre-Release Checklist for a Custom Login Endpoint

- [ ] Only the exact **login path** is processed; similar paths, query strings, and deployment context paths are tested.
- [ ] Only the exact **HTTP method** is accepted; other methods cannot trigger `AuthenticationManager`.
- [ ] **405 + Allow** or an equivalent method-error contract is published and tested.
- [ ] Request **Content-Type** is in the allowlist; `Accept` is never confused with `Content-Type`.
- [ ] Valid Content-Type parameters are supported; clear policies exist for UTF-8, vendor `+json`, multipart/form, and empty bodies.
- [ ] JSON is parsed and validated for schema, data types, lengths, and body size before authentication.
- [ ] **400/401/403/405/413/415** are distinguished by root cause and filter ordering.
- [ ] Raw usernames/passwords, sensitive bodies, session cookies, CSRF tokens, `Authorization` headers, and access tokens are never logged.
- [ ] HTTPS, rate limiting, brute-force monitoring, and account protection are properly designed.
- [ ] CSRF is analyzed by client/session/cookie; never disabled by default just because the endpoint is JSON.
- [ ] When custom login uses sessions, `SessionAuthenticationStrategy`, `setContext`, and **`saveContext`** are invoked before response commit.
- [ ] Session fixation protection, CSRF rotation, cookie attributes, and logout/session timeouts are verified.
- [ ] Filter is not registered twice across the Servlet container and Spring Security chain.
- [ ] Filter is not placed in the wrong `SecurityFilterChain` when multiple chains exist.
- [ ] Tested wrong path, wrong method, wrong media type, malformed JSON, oversized payload, wrong password, missing CSRF, valid login, and post-login permissions.
- [ ] Illustrative parameters (body size, sample passwords, in-memory users) are replaced with proper production design.

**Conclusion:** For custom login, enforce **exact URL → exact HTTP method → exact Content-Type → valid JSON body → valid credentials**, remembering that CSRF and other filters may decide earlier. Authorization rules do not automatically constrain all filters, and `@PostMapping(consumes=...)` does not protect a filter running before MVC. Spring Security provides official extension points; when writing a custom filter yourself, you are responsible for matchers, error responses, session protection, and safely saving the SecurityContext.
