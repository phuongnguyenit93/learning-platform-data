# Controlling CSRF for Write or Delete Operations by Authentication Mechanism

## 1. Why Can Reading Actuator Succeed While Writing Gets 403?

Suppose you use a valid operations account: reading logger configuration succeeds, yet changing the log level is rejected. This does not yet prove the account lacks permissions. A state-changing operation must satisfy different conditions:

- The endpoint is enabled and exposed over HTTP.
- The request has a valid identity and is authorized.
- If the route requires anti-forgery protection, the CSRF token must be valid.
- The HTTP method, payload, and target resource must be valid.

CSRF is **Cross-Site Request Forgery**. The risk arises when a browser automatically sends credentials to a target site even though the account owner did not intend to perform the operation. Therefore, “logged in” does not mean “intended to change configuration”.

This article uses **Spring Boot 3.3.x, Spring Security 6.3.x, Servlet/Spring MVC, Java 21**; the application and Actuator share a port, default path `/actuator`. WebFlux has a different configuration API; do not copy `HttpSecurity` to a reactive application.

[Actuator 3.3 Documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security) confirms CSRF is enabled by default and declaring a custom `SecurityFilterChain` makes you responsible for configuring security for the rest of the application.

## 2. Distinguishing Identity, Permissions, and Anti-Forgery Protection

Imagine an admin page letting operators change log levels. The browser already holds a login session cookie. If another site causes the browser to send a request to the admin page and the cookie is sent automatically per browser policy, the server can still recognize that operator.

The server needs an extra value that an external site cannot supply on its own. With a CSRF token, the legitimate page retrieves the token and actively sends it back via a header or parameter on state-changing requests.

| Check layer | Question in the log-level change scenario |
| --- | --- |
| Authentication | Who is making the request? |
| Authorization | Does this user have operations permission? |
| CSRF | Does the request satisfy the session's anti-forgery mechanism? |
| Endpoint logic | Are the logger name and log level valid? |

A CSRF token does not replace a password or access token. A valid password does not replace a CSRF token on a route that requires tokens either.

**How credentials enter the request** determines the policy, not the technology name alone. Cookie and Basic cases are explained in [Spring Security's CSRF overview documentation](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html).

| Mechanism on write/delete routes | Appropriate policy |
| --- | --- |
| Form login, receiving a session cookie | Keep CSRF and send token when changing state |
| JWT stored in an auth cookie, auto-sent by browser | Still need to consider CSRF; JWT does not stop cookies from auto-sending |
| HTTP Basic usable by browsers and cached credentials | Keep CSRF or design routes dedicated to machine clients |
| Bearer actively placed in `Authorization` by client only, no identity accepted from cookies/Basic | Can exempt CSRF within an isolated and verified scope |
| Same URL accepting both cookies and Bearer | Do not exempt the entire URL merely because Bearer is supported |

`SessionCreationPolicy.STATELESS` only specifies Spring Security's session usage policy. It does not stop another filter from reading a JWT from a cookie and does not change how browsers auto-send credentials. Thus, statelessness alone is insufficient grounds to disable CSRF.

Testing with curl also does not prove a URL is only for curl. Consider all ways the same route can authenticate in a real deployment, including proxies or custom filters.

## 3. Read Operations vs. State-Changing Operations

One endpoint can contain both reads and writes:

| HTTP example | Effect |
| --- | --- |
| `GET /actuator/loggers/com.example.actuatorcsrf.probe` | Read logger configuration |
| `POST /actuator/loggers/com.example.actuatorcsrf.probe` | Change or clear the explicitly configured log level |
| `GET /actuator/caches` | Read cache information |
| `DELETE /actuator/caches/books` | Evict entries in the cache named `books` |

POST sets `configuredLevel`, while POST with `{}` clears the explicit level to inherit from the parent; see [loggers 3.3 API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/loggers.html). DELETE empties the cache without deleting the `CacheManager` bean or cache definition; see [caches 3.3 API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/caches.html).

In default CSRF configuration, `GET`, `HEAD`, `OPTIONS`, `TRACE` are excluded from token checks. The remaining methods, commonly `POST`, `PUT`, `PATCH`, `DELETE`, require a token unless exempted. This does not grant access or guarantee the endpoint supports all those methods.

Do not design `GET /clear-cache` to avoid sending tokens. Hiding write operations in GET breaks the assumption that reading data causes no state change.

Also distinguish:

- Clearing cache data uses HTTP `DELETE`.
- Clearing an explicit log level still uses HTTP `POST` with `{}`.

CSRF is decided by the HTTP request and active policy, not by the verb in the operation name.

## 4. Option A: Keeping CSRF When Using Cookies or Basic

The example uses Basic for convenient command-line testing while **keeping CSRF**. It illustrates both sending identity and maintaining a session holding the CSRF token.

These are files for **a minimal Spring Boot 3.3.x project already initialized with Gradle Wrapper and the Spring Boot plugin**. Spring code requires dependencies; do not run standalone `javac SecurityConfig.java`. Use only configuration set A or B in a given test run.

### 4.1. Dependencies and Test Configuration

In `build.gradle`, use Spring Boot dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/resources/application.yml`:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,loggers,caches

spring:
  security:
    user:
      name: ops
      password: ${OPS_PASSWORD}
      roles: OPS

logging:
  level:
    com.example.actuatorcsrf.probe: INFO
~~~

The `OPS_PASSWORD` environment variable provides the password at runtime. Do not place real operations passwords in committed files. The example exposes only three endpoints for the experiment.

Create the Java files under `src/main/java/com/example/actuatorcsrf/`.

`DemoApplication.java`:

~~~java
package com.example.actuatorcsrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books");
    }
}
~~~

The cache bean gives DELETE a real resource to test. `@EnableCaching` is not needed just to access this cache directly; that annotation enables interception of calls to cache-annotated methods.

### 4.2. Two Filter Chains With Clear Scope

`SecurityConfig.java`:

~~~java
package com.example.actuatorcsrf;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class SecurityConfig {
    @Bean
    @Order(1)
    SecurityFilterChain actuatorChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasRole("OPS")
            )
            .httpBasic(withDefaults())
            .csrf(withDefaults());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/ops/csrf").hasRole("OPS")
                .anyRequest().denyAll()
            )
            .httpBasic(withDefaults())
            .csrf(withDefaults());
        return http.build();
    }
}
~~~

The first chain applies to Actuator; the second chain takes the rest. Only the first matching chain is used; chains do not stack policies. In A, even health requires the OPS role: this is a choice for the test lab.

`hasRole("OPS")` checks authority `ROLE_OPS`. Setting `roles: OPS` creates the matching role for the test user. Granting permission does not bypass the CSRF filter.

A real application needs specific rules for business routes instead of `denyAll()`. Do not omit the fallback chain and expect auto-configuration to continue protecting every URL.

### 4.3. Issuing Tokens Through a Regular Admin Route

`CsrfController.java`:

~~~java
package com.example.actuatorcsrf;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CsrfController {
    public record TokenView(String headerName, String token) {
    }

    @GetMapping("/ops/csrf")
    ResponseEntity<TokenView> csrf(CsrfToken csrfToken) {
        TokenView body = new TokenView(
            csrfToken.getHeaderName(),
            csrfToken.getToken()
        );
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(body);
    }
}
~~~

`/ops/csrf` is an application controller, not a built-in Actuator endpoint. It is accessible only to OPS and returns `Cache-Control: no-store`.

With the defaults used here, the expected token resides in the HTTP session. Reading `getToken()` realizes the token if it was deferred earlier. The client must keep the session cookie from fetching the token and send the token back in the returned header.

Spring Security 6 masks tokens with random values to mitigate BREACH risk. Do not substitute the session cookie string, a self-generated UUID, or a token from another session. Use the token provided by the server's mechanism. Repositories, request handlers, and deferred tokens are explained in [Servlet CSRF documentation for branch 6.3](https://raw.githubusercontent.com/spring-projects/spring-security/6.3.x/docs/modules/ROOT/pages/servlet/exploits/csrf.adoc).

If using `CookieCsrfTokenRepository` for a JavaScript UI, you must align the repository, header reading, and token handling with the frontend. Merely having a cookie holding the token is not enough: the client must also actively place the token into the header the server checks. The current example uses the default session-based repository, not the SPA cookie repository.

### 4.4. Testing POST and DELETE From PowerShell

In the terminal running the application:

~~~powershell
$env:OPS_PASSWORD = 'local-demo-only'
.\gradlew.bat bootRun
~~~

This password is only for the local test application. Open a second PowerShell terminal:

~~~powershell
$pair = 'ops:local-demo-only'
$encoded = [Convert]::ToBase64String(
    [Text.Encoding]::UTF8.GetBytes($pair)
)
$basicHeaders = @{ Authorization = "Basic $encoded" }
$base = 'http://localhost:8080'
$loggerUrl = "$base/actuator/loggers/com.example.actuatorcsrf.probe"

$read = Invoke-WebRequest -UseBasicParsing `
    -Uri $loggerUrl -Headers $basicHeaders
$read.StatusCode
~~~

The last expression returns `200`; `configuredLevel` is initially `INFO`. Reading needs no CSRF token, yet still needs authentication.

Send POST with the right account, without a token:

~~~powershell
try {
    Invoke-WebRequest -UseBasicParsing `
        -Uri $loggerUrl -Method Post `
        -Headers $basicHeaders -ContentType 'application/json' `
        -Body '{"configuredLevel":"DEBUG"}' | Out-Null
} catch {
    [int]$_.Exception.Response.StatusCode
}
~~~

In this test application, the result is `403`. Do not fix it with `permitAll()`: identity was not what the test request lacked.

Fetch the token, keep the cookie, and send it back:

~~~powershell
$tokenResponse = Invoke-WebRequest -UseBasicParsing `
    -Uri "$base/ops/csrf" -Headers $basicHeaders `
    -SessionVariable opsSession
$token = $tokenResponse.Content | ConvertFrom-Json

$writeHeaders = @{ Authorization = "Basic $encoded" }
$writeHeaders[$token.headerName] = $token.token

$changed = Invoke-WebRequest -UseBasicParsing `
    -Uri $loggerUrl -Method Post `
    -Headers $writeHeaders -WebSession $opsSession `
    -ContentType 'application/json' `
    -Body '{"configuredLevel":"DEBUG"}'
$changed.StatusCode

$deleted = Invoke-WebRequest -UseBasicParsing `
    -Uri "$base/actuator/caches/books" -Method Delete `
    -Headers $writeHeaders -WebSession $opsSession
$deleted.StatusCode
~~~

The two statuses are `204` and `204` respectively. Having no response body is normal. Reading the logger again via GET will show `configuredLevel` is `DEBUG`.

In the example, the session holds the CSRF token; the Basic header continues supplying identity on every request. Do not infer that merely carrying the received cookie automatically replaces Basic.

To clear the explicit log level, send POST with the same headers and session, and body `{}`:

~~~powershell
Invoke-WebRequest -UseBasicParsing `
    -Uri $loggerUrl -Method Post `
    -Headers $writeHeaders -WebSession $opsSession `
    -ContentType 'application/json' -Body '{}' | Out-Null
~~~

If the goal is restoring a previous explicit log level, set that old value back explicitly rather than using `{}`.

## 5. Verifying Both Failure and Success

To test CSRF, keep account, URL, and body unchanged while varying the token or session. A single POST returning 204 only proves one success path.

Create `src/test/java/com/example/actuatorcsrf/ActuatorCsrfTest.java` for option A:

~~~java
package com.example.actuatorcsrf;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "spring.security.user.password=test-only")
@AutoConfigureMockMvc
class ActuatorCsrfTest {
    private static final String LOGGER =
        "/actuator/loggers/com.example.actuatorcsrf.probe";
    private static final String BODY = "{\"configuredLevel\":\"DEBUG\"}";

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;
    @Autowired CacheManager cacheManager;

    private Cache books;

    @BeforeEach
    void seedCache() {
        books = cacheManager.getCache("books");
        assertNotNull(books);
        books.put("isbn", "draft");
    }

    @Test
    void getDoesNotRequireCsrfToken() throws Exception {
        mvc.perform(get(LOGGER).with(httpBasic("ops", "test-only")))
            .andExpect(status().isOk());
    }

    @Test
    void postWithoutTokenIsForbidden() throws Exception {
        mvc.perform(post(LOGGER)
                .with(httpBasic("ops", "test-only"))
                .contentType(MediaType.APPLICATION_JSON).content(BODY))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithInvalidTokenIsForbidden() throws Exception {
        mvc.perform(post(LOGGER)
                .with(httpBasic("ops", "test-only"))
                .with(csrf().asHeader().useInvalidToken())
                .contentType(MediaType.APPLICATION_JSON).content(BODY))
            .andExpect(status().isForbidden());
    }

    @Test
    void tokenFromControllerWorksWithItsSession() throws Exception {
        MvcResult result = mvc.perform(get("/ops/csrf")
                .with(httpBasic("ops", "test-only")))
            .andExpect(status().isOk())
            .andReturn();

        JsonNode token = mapper.readTree(
            result.getResponse().getContentAsString()
        );
        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(post(LOGGER)
                .with(httpBasic("ops", "test-only"))
                .session(session)
                .header(token.get("headerName").asText(),
                        token.get("token").asText())
                .contentType(MediaType.APPLICATION_JSON).content(BODY))
            .andExpect(status().isNoContent());
    }

    @Test
    void validCsrfDoesNotGrantOpsRole() throws Exception {
        mvc.perform(post(LOGGER)
                .with(user("reader").roles("READER"))
                .with(csrf().asHeader())
                .contentType(MediaType.APPLICATION_JSON).content(BODY))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfDoesNotAuthenticateAnonymousRequest() throws Exception {
        mvc.perform(post(LOGGER)
                .with(csrf().asHeader())
                .contentType(MediaType.APPLICATION_JSON).content(BODY))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void deleteWithoutTokenDoesNotEvictCache() throws Exception {
        mvc.perform(delete("/actuator/caches/books")
                .with(httpBasic("ops", "test-only")))
            .andExpect(status().isForbidden());
        assertNotNull(books.get("isbn"));
    }

    @Test
    void deleteWithTokenEvictsCache() throws Exception {
        mvc.perform(delete("/actuator/caches/books")
                .with(httpBasic("ops", "test-only"))
                .with(csrf().asHeader()))
            .andExpect(status().isNoContent());
        assertNull(books.get("isbn"));
    }
}
~~~

Run in the test project:

~~~powershell
.\gradlew.bat test --tests com.example.actuatorcsrf.ActuatorCsrfTest
~~~

Eight tests are expected to pass. Do not pin the full Gradle log because paths, timings, and warnings depend on the environment.

The `csrf()`, `asHeader()`, and `useInvalidToken()` helpers are documented in [CSRF testing documentation](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html). The test retrieving the token from the controller also tests a real token with its matching session, rather than relying solely on request post-processors.

`user("reader")` simulates an identity to isolate authorization checks; it does not test Basic passwords. MockMvc does not fully simulate browser cookies, SameSite, or CORS. If a web UI exists, also test login and token submission flows in a browser.

## 6. Option B: Management Route Accepting Only Bearer Headers

Suppose machine tooling performs operational tasks with access tokens. Choose this option only when you control all conditions:

- Tokens come solely from the `Authorization: Bearer ...` header.
- The route accepts no identity from sessions, JWT cookies, Basic, or proxy-injected identity headers.
- Tokens are verified and carry operational permissions.
- The CSRF exemption stays within the selected endpoints; other web routes keep their own policies.

**B replaces A**, do not add another `@Order(1)` chain alongside A. Keep `DemoApplication` and exposure/cache configuration. Add the following line inside `dependencies`:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
~~~

Replace `spring.security.user` configuration with:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OPS_ISSUER_URI}
~~~

`OPS_ISSUER_URI` must be a real issuer in the test environment with proper discovery/JWK configuration. B requires token-issuing infrastructure; do not substitute an arbitrary string for a valid JWT. Depending on system policy, add audience checks so tokens are only accepted for the intended service.

Replace `SecurityConfig.java` with:

~~~java
package com.example.actuatorcsrf;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.NullSecurityContextRepository;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class SecurityConfig {
    @Bean
    @Order(1)
    SecurityFilterChain machineActuatorChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher(EndpointRequest.to("loggers", "caches"))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .securityContext(context -> context
                .securityContextRepository(new NullSecurityContextRepository())
            )
            .requestCache(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .formLogin(AbstractHttpConfigurer::disable)
            .logout(AbstractHttpConfigurer::disable)
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasAuthority("SCOPE_actuator.write")
            )
            .oauth2ResourceServer(resource -> resource
                .bearerTokenResolver(new DefaultBearerTokenResolver())
                .jwt(withDefaults())
            )
            .csrf(AbstractHttpConfigurer::disable);
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(EndpointRequest.to("health")).permitAll()
                .anyRequest().denyAll()
            )
            .csrf(withDefaults());
        return http.build();
    }
}
~~~

The `csrf(...disable)` call belongs to the chain matching only `loggers` and `caches`, including their subpaths. Health is permitted to be read in the fallback chain; other routes are denied. `/ops/csrf` from A is not opened in B and can be removed from test project B.

Both reads and writes on the two selected endpoints require `SCOPE_actuator.write`. This is a simple rule for operational tooling in this article; real applications may split read/write permissions. Under default scope mapping, scope `actuator.write` becomes authority `SCOPE_actuator.write`; do not pass that string to `hasRole`.

`DefaultBearerTokenResolver` by default reads Bearer from the Authorization header, without enabling token extraction from body/query. You can cross-check in [resolver source on branch 6.3](https://raw.githubusercontent.com/spring-projects/spring-security/6.3.x/oauth2/oauth2-resource-server/src/main/java/org/springframework/security/oauth2/server/resource/web/DefaultBearerTokenResolver.java).

An implementation detail: the OAuth2 Resource Server DSL on branch 6.3 automatically registers a CSRF exemption for requests where the resolver detects a Bearer token. That exemption **does not replace token verification**, nor does it automatically exempt all cookie requests. In B, CSRF is explicitly disabled on the narrow chain so the machine-route policy is clear; no app-wide exemption is needed. See [OAuth2ResourceServerConfigurer on branch 6.3](https://raw.githubusercontent.com/spring-projects/spring-security/6.3.x/config/src/main/java/org/springframework/security/config/annotation/web/configurers/oauth2/server/resource/OAuth2ResourceServerConfigurer.java).

### Verifying B

After configuring the issuer and obtaining a token with the required scope, put the token in the `OPS_ACCESS_TOKEN` environment variable in the test terminal:

~~~powershell
$bearerHeaders = @{
    Authorization = "Bearer $env:OPS_ACCESS_TOKEN"
}
$response = Invoke-WebRequest -UseBasicParsing `
    -Uri 'http://localhost:8080/actuator/loggers/com.example.actuatorcsrf.probe' `
    -Method Post -Headers $bearerHeaders `
    -ContentType 'application/json' `
    -Body '{"configuredLevel":"DEBUG"}'
$response.StatusCode
~~~

With a valid, sufficiently scoped token, `204` is expected without needing a CSRF token. Never print access tokens to logs.

| POST/DELETE scenario within B's scope | Expected |
| --- | --- |
| No Bearer, even with an old session cookie | 401 |
| Sending Basic only | 401 |
| Expired or invalid-signature Bearer | 401 |
| Valid Bearer missing required scope | 403 |
| Valid Bearer, sufficient scope, valid payload, existing resource | Operation executes; example above returns 204 |

If an old cookie lets a write succeed without Bearer, B's preconditions are not met: check the matching chain, custom filters, and proxies.

Spring Security Test's `jwt()` helper mocks a JWT identity; it does not prove signature, issuer, or expiration are checked. Add requests with real signed tokens and expired/bad-signature tokens to test the actual authentication path.

## 7. Exemptions Must Follow Authentication Boundaries

You can use `ignoringRequestMatchers(...)` if only certain routes in a chain are guaranteed not to rely on auto-sent credentials. You must verify authentication behavior on the exact ignored URLs.

Do not ignore all of `/actuator/**` inside a chain that still allows Basic or admin sessions to write data: browser flows would lose token checks too.

Do not write a custom rule “if an Authorization header is present, skip CSRF” while still falling back to cookies when the token is invalid. A client-supplied header does not prove the intended authentication mechanism succeeded.

If the same endpoint must accept both cookies and Bearer, keep CSRF for the cookie flow or separate access endpoints/authentication policies. When mixing Resource Server DSL, consider framework-registered exemptions as well; merely adding `csrf(withDefaults())` does not mean Bearer requests are forced to send tokens.

Changing `management.endpoints.web.base-path` changes URLs. The `EndpointRequest` matcher follows endpoints instead of hardcoding prefixes, yet you still must test actual paths. If using a separate management port or context, verify policies in that context; do not assume the article's two chains cover every deployment layout.

## 8. Diagnosing Errors Without Weakening Policy

### 8.1. Two Requests Both Returning 403 May Have Different Causes

In A:

1. OPS sends POST missing a token: CSRF can block before authorization.
2. READER sends POST with a valid token: passes CSRF but lacks the role.
3. OPS uses a token from another session: token mismatch.
4. Session and token are valid but body is invalid: may reach the endpoint and be rejected due to payload.

Do not infer the entire cause from status codes alone. Compare controlled requests and observe the server.

In a local test app, you can temporarily enable:

~~~yaml
logging:
  level:
    org.springframework.security.web.csrf: DEBUG
~~~

Merge into the existing `logging.level` block, without creating two duplicate `logging` keys. Correlate missing/invalid token messages with the active security chain and permissions. Lower the log level after investigating; avoid logging credentials.

| Symptom | Where to check |
| --- | --- |
| GET works, same OPS's POST gets 403 | Missing token or wrong session? |
| Valid token, READER still gets 403 | Are roles/authorities right? |
| Unauthenticated POST also gets 403 in A | CSRF may block first; use a valid token to isolate authentication |
| Expired Bearer gets 401 in B | Check token verification, do not fix with CSRF tokens |
| 404/405 after passing security | Exposure, endpoint name, HTTP method, resource |
| 400/415 after passing security | Body, parameters, Content-Type |

Filters can block before MVC, so even a wrong URL can receive 401/403. The table is an investigation guide, not a one-to-one mapping between error codes and causes.

### 8.2. Reasoning Errors That Lead to Misconfiguration

- **“With CORS we don't need CSRF.”** Some cross-origin requests can still be sent even if the external page cannot read the response. Blocking reads does not mean blocking state changes.
- **“Accepting only JSON or DELETE is always safe.”** Preflight and Content-Type checks help, yet you must consider the authentication mechanism, other write routes, and method overrides if any.
- **“JWT means exempt from CSRF.”** Ask whether the token is in an explicit header or an auto-sent cookie.
- **“Having SameSite/HttpOnly/Secure is enough.”** HttpOnly limits JavaScript cookie reading, Secure limits transport, SameSite depends on site relationships. They do not grant permissions or supply valid CSRF tokens on their own.
- **“Internal networks don't involve browsers.”** A browser on a machine inside that network can still send requests; evaluate the real usage model.
- **“Disabling CSRF made it 204 so security is fixed.”** A success path does not prove unauthenticated, unauthorized, or forged requests are rejected.
- **“GET needs no CSRF so open all Actuator GETs.”** Read permissions and sensitive data still require dedicated policies.

CSRF in this article is an HTTP mechanism. JMX has its own access policy; HTTP CSRF headers do not protect the JMX channel.

## 9. Self-Check Exercises

1. For A, change the token to an arbitrary string while keeping Basic valid. Explain why the result differs from a request with a real token.
2. Obtain tokens from two sessions and swap the token and cookie. Where does the token–session relationship break?
3. Send DELETE to cache `books` as OPS without a token, then send with a valid token. Check both HTTP status and cache entries.
4. Keep a valid token, switch identity to READER. Why does the token not elevate permissions?
5. Choose B but add a filter reading JWT from a cookie. Why must the CSRF exemption basis be reconsidered?
6. Switch to STATELESS while still authenticating via cookie. Which condition of CSRF risk still exists?

You have mastered this lesson when you choose policies based on **how credentials are sent**, verify authentication/authorization/CSRF independently, and scope exemptions to the right routes instead of simply disabling checks to make a POST succeed.
