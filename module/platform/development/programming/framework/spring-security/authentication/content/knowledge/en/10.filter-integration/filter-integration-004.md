# AuthenticationFilter and AuthenticationConverter in Spring Security

> **Scope:** Spring Security – authentication, topic **Filter Integration**. This lesson explains how `AuthenticationConverter` turns an HTTP request into an untrusted authentication request, how `AuthenticationFilter` coordinates `AuthenticationManager` and updates `SecurityContext`, how success/failure are handled, and how to place the filter properly in the security chain. The complete example uses **Java 17+**, **Spring Boot 4.1.2**, Spring Security Servlet, and an HTTP header API key strictly for a learning environment.

## 1. Why Shouldn't One Filter Both Read Headers and Authenticate Directly?

An application may receive credentials via form login, HTTP Basic, Bearer token, or a custom header. Credential formats vary, yet the processing pipeline is generally the same:

```text
HttpServletRequest
       |
       v
Extract evidence (username/password, API key, token...)
       |
       v
UNTRUSTED Authentication request
       |
       v
AuthenticationManager / AuthenticationProvider
       |
       +-- failure -> error handler
       |
       +-- success -> trusted principal + authorities
                                |
                                v
                        SecurityContext
                                |
                                v
                        Authorization
                                |
                                v
                        Controller / Service
```

If a custom filter reads `X-Role: ADMIN` and creates a principal with `ROLE_ADMIN` directly, a user can escalate privileges simply by modifying the request. If another filter builds an already-authenticated `UsernamePasswordAuthenticationToken` before comparing the password, the entire authentication step can be bypassed.

Spring Security separates responsibilities to prevent confusion:

| Component | Core responsibility | Must NOT implicitly do |
| --- | --- | --- |
| `AuthenticationConverter` | Converts an HTTP request into an unverified authentication request | Grant authorities from input |
| `AuthenticationFilter` | Selects requests, calls converter/manager, handles result and context | Replace the provider in verifying credentials |
| `AuthenticationManager` | Coordinates providers | Trust a request without verification |
| `AuthenticationProvider` | Verifies a specific credential type, returns trusted principal/authorities | Accept client-asserted roles |
| `SecurityContextHolder` | Holds the current context per strategy | Act as a long-term permissions store |
| `AuthorizationFilter` | Evaluates the caller against policy after authentication | Treat header presence as permission |

**Rule:** Converter **reads**. Manager/provider **verifies**. `AuthenticationFilter` **orchestrates**. Authorization **decides whether to permit the action**.

## 2. AuthenticationConverter: Contract and Three Outcomes

The `org.springframework.security.web.authentication.AuthenticationConverter` interface has one method:

```java
@Nullable
Authentication convert(HttpServletRequest request);
```

This is a shortened API signature; `HttpServletRequest` is in `jakarta.servlet.http`, `Authentication` is in Spring Security. The method can return:

| Value | Meaning | Typical `AuthenticationFilter` behavior |
| --- | --- | --- |
| `null` | No credential matching the mechanism recognized by the converter | Skips the authentication attempt, continues the filter chain |
| Unauthenticated `Authentication` | Evidence is present for a provider to check | Calls `AuthenticationManager.authenticate(...)` |
| Throws `AuthenticationException` | Malformed credential/scheme or rejected immediately at parsing | Invokes failure handler |

### Null Is NOT "Allow"

For example, `GET /api/data` without the `X-Demo-Key` header:

```text
Converter -> null
AuthenticationFilter -> chain continues, no authentication attempted
AuthorizationFilter -> requires authority "data:read"
Unauthenticated caller -> entry point returns 401 in the demo
```

If the endpoint accidentally has `permitAll()`, it can still be exposed. That is an **authorization rule** mistake, not a feature of the converter granting access.

### When Should It Throw an Exception?

A protocol should clearly define: *no credential present* may return null; *credential present but malformed* typically throws `BadCredentialsException` or a suitable subclass. For an API key header:

- Header absent: `null`.
- Single non-empty header of valid length: create an unauthenticated token.
- Empty, repeated, or overly long header: `AuthenticationException`.
- Properly formatted header with **wrong secret value**: converter still builds the token; the **provider** rejects it.

Do not let the converter query the key store itself and build an authenticated token; verification and authority assignment belong in the authentication provider layer.

## 3. Authentication Token Before and After Authentication

`Authentication` is an interface that can represent **both an unauthenticated request** and **an authenticated result**.

A proper request token typically has:

- `principal`: name or marker claimed by the caller, **unverified**.
- `credentials`: raw evidence awaiting verification.
- `authorities`: usually empty.
- `isAuthenticated() == false`.

A trusted result after the provider has:

- Principal looked up/confirmed from a server-side source.
- Authorities granted only by the verified provider/source.
- `isAuthenticated() == true`.
- Credentials hidden/erased from the result when appropriate.

In this lesson, we create a dedicated `HeaderKeyAuthentication` so we do not misuse `UsernamePasswordAuthenticationToken` meant for password logins. The converter can only build `presented(raw)`; the provider verifies it and creates `verified(actor)`.

Why is a custom type helpful? `AuthenticationProvider.supports(Class<?>)` uses the class type to decide which provider can handle it. If an API key masquerades as a username/password token, the DAO provider could be picked by mistake, causing protocol mismatches or bypassing authentication checks.

**You do not need a custom token for every project.** Form login, HTTP Basic, bearer/JWT, SAML, or OAuth2 should prefer Spring Security's standard filters and providers.

## 4. How Does AuthenticationFilter Work?

`org.springframework.security.web.authentication.AuthenticationFilter` is a servlet filter extending `OncePerRequestFilter`, supported by Spring Security since version 5.2. Two constructor forms:

```java
AuthenticationFilter(
        AuthenticationManager manager,
        AuthenticationConverter converter);

AuthenticationFilter(
        AuthenticationManagerResolver<HttpServletRequest> resolver,
        AuthenticationConverter converter);
```

These are shortened signatures, not standalone source code. The first form uses a single manager. The second solves selecting a manager based on the request (e.g., multiple identity realms) **without verifying the issuer or tenant by itself**.

General flow:

```text
AuthenticationFilter
    |
    +-- setRequestMatcher.matches(request) == false
    |       -> chain.doFilter, converter does not run
    |
    +-- matcher == true
            |
            v
        converter.convert(request)
            |
            +-- null -> chain.doFilter
            |
            +-- AuthenticationException -> failure handler
            |
            +-- unauthenticated Authentication
                        |
                        v
                 manager.authenticate(...)
                        |
                 +------+------+
                 |             |
              success        failure
                 |             |
          SecurityContext   Clear context
          Success handler   Failure handler
                 |
           Handler can
           continue chain,
           write response,
           or redirect
```

### RequestMatcher Should Be Narrow and Explicit

`filter.setRequestMatcher(RequestMatcher)` decides which URLs and methods the filter runs on. By default, a newly constructed `AuthenticationFilter` may match every request; if a custom converter misbehaves on a public endpoint, unexpected 401s can occur. Therefore, the demo matches `GET /api/data` specifically.

**A matcher does not replace authorization.** Even when the matcher does not match, `AuthorizationFilter` still protects the resource according to its rules.

### Choosing AuthenticationManagerResolver

If an API handles multiple issuers/tenants, a manager resolver may be needed. The resolver only selects **the appropriate verifier**; it must never select a "weaker" manager based solely on an unverified `X-Tenant-Id` header. Verifying the tenant/issuer also depends on tokens, routing contracts, and trusted data sources.

## 5. Success, Failure, and SecurityContextRepository

`AuthenticationFilter` has key setters:

| API | Role |
| --- | --- |
| `setRequestMatcher(...)` | Specifies which requests the filter processes |
| `setAuthenticationConverter(...)` | Replaces the request-to-token conversion strategy |
| `setAuthenticationManagerResolver(...)` | Selects a manager per request |
| `setSuccessHandler(...)` | Handles successful authentication |
| `setFailureHandler(...)` | Handles failed authentication |
| `setSecurityContextRepository(...)` | Determines how `SecurityContext` is stored after success |

### The Success Handler Can Stop or Continue the Request

`AuthenticationFilter` places the successful authentication into `SecurityContextHolder`, calls the repository to save the context, and then invokes `AuthenticationSuccessHandler`.

`AuthenticationSuccessHandler` has a regular method accepting request/response/authentication and an additional default method accepting `FilterChain`:

```java
void onAuthenticationSuccess(
        HttpServletRequest request,
        HttpServletResponse response,
        Authentication authentication);

default void onAuthenticationSuccess(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain chain,
        Authentication authentication);
```

These are shortened API signatures; the methods may declare `IOException` and `ServletException`. Form login handlers typically redirect. For an API that needs to **continue to the controller within the same request**, you can override the four-parameter form and call `chain.doFilter(...)`.

If you rely on a default handler that redirects, a valid API key might **never reach the controller**, even though authentication succeeded. That is why you must test actual HTTP output rather than only checking `Authentication.isAuthenticated()`.

### The Failure Handler Is Not Controller Advice

If the converter or provider throws `AuthenticationException`, `AuthenticationFilter` calls `AuthenticationFailureHandler` and clears the context. For the demo API, we return a generic HTTP 401 without echoing the raw exception message.

`@RestControllerAdvice` belongs to the MVC layer; many security filters run **before** MVC, so controller advice will not necessarily catch errors here. `ExceptionTranslationFilter` normally handles exceptions from authorization/downstream, whereas authentication filters have their own failure-handler path.

### Default Does Not Mean Session Login

`AuthenticationFilter` uses `RequestAttributeSecurityContextRepository` by default, **not automatically saving the context into `HttpSession`**. One request having a valid `Authentication` does not mean the next request remains authenticated.

If you want stateful login, you need an appropriate repository/session strategy, session fixation protection, CSRF/remember-me/logout, and an explicit lifecycle. If you want a stateless API, keep a request-scoped context or equivalent and send credentials on every request.

## 6. Placing AuthenticationFilter in the Right SecurityFilterChain

Key parts in Servlet Spring Security (general order, not listing every filter):

```text
SecurityContextHolderFilter
    |
Header/CORS/CSRF protection (as configured)
    |
LogoutFilter
    |
Custom AuthenticationFilter
    |
AnonymousAuthenticationFilter
    |
ExceptionTranslationFilter
    |
AuthorizationFilter
    |
Controller / Service
```

Spring Security guidance places custom authentication filters **after `LogoutFilter`**. Example:

```java
http.addFilterAfter(headerAuthenticationFilter, LogoutFilter.class);
```

This is an `HttpSecurity` configuration fragment, not a standalone Java class. Placing the filter **after `AuthorizationFilter`** can cause requests to be rejected before a principal exists. Placing it too early means `SecurityContextHolderFilter` or request-protection layers may not be properly initialized yet.

### A Filter Bean Can Accidentally Run Twice

Spring Boot can automatically register beans of type `jakarta.servlet.Filter` as **global servlet filters**. If that same bean is also added to a Spring Security chain, it can run twice or execute outside the security chain.

In the demo, `AuthenticationFilter` is instantiated **directly inside the `SecurityFilterChain` builder method** rather than declared as a separate `@Bean`. If a real project needs the filter as a Spring bean, consider `FilterRegistrationBean#setEnabled(false)` for global servlet registration, then add the filter to the desired chain.

### Multiple Filter Chains Do Not Share Matchers Automatically

A system can have separate API and browser chains via `@Order`/`securityMatcher`. `FilterChainProxy` picks **the first chain matching the request**. Adding a filter to the API chain does not add it to the browser chain. You must test chain order, public/private routes, stateless/stateful behavior, and error handlers per chain.

## 7. Complete Example: Spring Boot Java 17+ and Header API Key

Example goals:

1. Client sends `X-Demo-Key` in `GET /api/data`.
2. Converter validates header shape and returns a token with `isAuthenticated=false`.
3. Provider uses a server-configured key to verify the evidence and issues principal `service-client` with authority `data:read`.
4. Filter sets context and **continues the chain** via the four-parameter success handler.
5. Authorization rule enforces `hasAuthority("data:read")`.
6. Missing or invalid keys are rejected with 401; the public endpoint requires no credentials.
7. No HTTP session is created; every call to the protected endpoint requires the key header.

**Security note:** the demo key is not for production. Real applications need high-entropy random keys, hash/HMAC-at-rest storage, TLS, auditing, rate limiting, rotation, revocation, and per-client/tenant policies. Comparing SHA-256 digests in the demo **must not be used to store user-chosen passwords**.

### 7.1. Project Structure

```text
header-auth-demo/
├── pom.xml
└── src/main/java/com/example/headerauth/
    └── HeaderAuthApplication.java
```

The demo uses Spring Boot 4.1.2 with Boot-managed Spring Security versions. Java 17+ is the baseline requirement. Spring Security Servlet uses `jakarta.servlet.http`; this is **not** a WebFlux example.

### 7.2. File pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>header-auth-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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
```

The parent manages compatible dependencies. If your organization uses another Spring Boot line, check the Spring Security version and APIs selected by its BOM rather than pinning an incompatible version manually.

### 7.3. File HeaderAuthApplication.java

```java
package com.example.headerauth;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Collection;
import java.util.Enumeration;
import java.util.List;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationConverter;
import org.springframework.security.web.authentication.AuthenticationFilter;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.logout.LogoutFilter;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class HeaderAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(HeaderAuthApplication.class, args);
    }
}

final class HeaderKeyAuthentication extends AbstractAuthenticationToken {

    private final String principal;
    private String credentials;

    private HeaderKeyAuthentication(
            String principal,
            String credentials,
            Collection<? extends GrantedAuthority> authorities,
            boolean authenticated) {
        super(authorities);
        this.principal = principal;
        this.credentials = credentials;
        super.setAuthenticated(authenticated);
    }

    static HeaderKeyAuthentication presented(String rawKey) {
        return new HeaderKeyAuthentication(
                "unverified", rawKey, List.of(), false);
    }

    static HeaderKeyAuthentication verified(String actor) {
        return new HeaderKeyAuthentication(
                actor, null,
                List.of(new SimpleGrantedAuthority("data:read")),
                true);
    }

    @Override
    public Object getPrincipal() {
        return principal;
    }

    @Override
    public Object getCredentials() {
        return credentials;
    }

    @Override
    public void eraseCredentials() {
        super.eraseCredentials();
        credentials = null;
    }

    @Override
    public void setAuthenticated(boolean value) {
        if (value) {
            throw new IllegalArgumentException(
                    "Only provider may verify credentials");
        }
        super.setAuthenticated(false);
    }
}

// Converter only transforms the request into an unauthenticated token.
final class HeaderKeyConverter implements AuthenticationConverter {

    @Override
    public Authentication convert(HttpServletRequest request) {
        Enumeration<String> headers =
                request.getHeaders("X-Demo-Key");

        if (!headers.hasMoreElements()) {
            return null;
        }

        String rawKey = headers.nextElement();

        if (headers.hasMoreElements()
                || rawKey == null
                || rawKey.isBlank()
                || rawKey.length() > 256) {
            throw new BadCredentialsException("Invalid key format");
        }

        return HeaderKeyAuthentication.presented(rawKey);
    }
}

// Single provider that grants principal and authority after verification.
final class HeaderKeyProvider implements AuthenticationProvider {

    private final byte[] expectedHash;

    HeaderKeyProvider(String expectedKey) {
        this.expectedHash = sha256(expectedKey);
    }

    @Override
    public Authentication authenticate(Authentication request) {
        if (!(request instanceof HeaderKeyAuthentication keyToken)
                || keyToken.isAuthenticated()) {
            throw new BadCredentialsException(
                    "Invalid authentication request");
        }

        Object presented = keyToken.getCredentials();

        if (!(presented instanceof String raw)
                || !MessageDigest.isEqual(
                        expectedHash, sha256(raw))) {
            throw new BadCredentialsException("Invalid API key");
        }

        return HeaderKeyAuthentication.verified("service-client");
    }

    @Override
    public boolean supports(Class<?> type) {
        return HeaderKeyAuthentication.class.isAssignableFrom(type);
    }

    private static byte[] sha256(String input) {
        try {
            return MessageDigest.getInstance("SHA-256")
                    .digest(input.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(ex);
        }
    }
}

@Configuration(proxyBeanMethods = false)
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        String expectedKey = System.getenv("DEMO_API_KEY");
        if (expectedKey == null || expectedKey.length() < 16) {
            throw new IllegalStateException(
                    "Set DEMO_API_KEY to at least 16 chars");
        }

        AuthenticationManager manager =
                new ProviderManager(new HeaderKeyProvider(expectedKey));

        AuthenticationFilter filter = new AuthenticationFilter(
                manager, new HeaderKeyConverter());

        filter.setRequestMatcher(request ->
                "GET".equals(request.getMethod())
                        && "/api/data".equals(request.getServletPath()));

        filter.setSecurityContextRepository(
                new RequestAttributeSecurityContextRepository());

        // Four-parameter form continues the chain to authorization/controller.
        filter.setSuccessHandler(new AuthenticationSuccessHandler() {

            @Override
            public void onAuthenticationSuccess(
                    HttpServletRequest request,
                    HttpServletResponse response,
                    Authentication authentication) throws IOException {
                response.setStatus(HttpServletResponse.SC_OK);
            }

            @Override
            public void onAuthenticationSuccess(
                    HttpServletRequest request,
                    HttpServletResponse response,
                    FilterChain chain,
                    Authentication authentication)
                    throws IOException, ServletException {
                chain.doFilter(request, response);
            }
        });

        filter.setFailureHandler((request, response, ex) ->
                response.sendError(
                        HttpServletResponse.SC_UNAUTHORIZED));

        return http
                .sessionManagement(session -> session
                        .sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .securityContext(context -> context
                        .securityContextRepository(
                                new RequestAttributeSecurityContextRepository()))
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint(
                                new HttpStatusEntryPoint(
                                        HttpStatus.UNAUTHORIZED)))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/ping").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/data")
                                .hasAuthority("data:read")
                        .anyRequest().denyAll())
                // Do not declare the filter as a global servlet @Bean.
                .addFilterAfter(filter, LogoutFilter.class)
                .build();
    }
}

@RestController
class DemoController {

    @GetMapping("/public/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/api/data")
    String data(Authentication authentication) {
        return "hello " + authentication.getName();
    }
}
```

### Explaining the Code by Role

**Custom token:** `presented(rawKey)` has `isAuthenticated=false` and no authorities. `verified("service-client")` is called only by the provider after key verification, assigning `data:read` from the **server**. Overriding `setAuthenticated(true)` prevents callers from arbitrarily marking a presented token as trusted. Never put JPA entities or secrets in the principal.

**Converter:** Returns null if no header exists, throws an exception if the header is malformed, and returns an unauthenticated token when one valid-looking header is present. It does not compare keys and does not trust any `X-Role` header.

**Provider:** Uses `MessageDigest.isEqual` to compare digests; this only illustrates comparing an **API key**, not password hashing suitable for low-entropy passwords. Production keys must be strongly randomly generated, stored as controlled digests/HMACs, with revocation/rotation and rate limiting.

**Manager:** `ProviderManager` recognizes `HeaderKeyAuthentication` because the provider declares `supports(...)`. Never construct an authenticated `UsernamePasswordAuthenticationToken` just because a header has data.

**Filter:** The matcher limits it to `GET /api/data`. Missing header -> converter returns null -> filter continues, yet authorization still denies. Invalid key -> provider throws `BadCredentialsException` -> failure handler returns 401.

**Success handler:** The four-parameter form calls `chain.doFilter`. Without this step, a default handler could return a redirect instead of letting the controller handle the request. The filter sets the context in the holder before the chain continues.

**Context/repository:** Uses the request-attribute repository and `STATELESS` so login is not persisted across sessions. The client must present the credential again on each `GET /api/data`.

**Authorization:** Only the `hasAuthority("data:read")` rule grants access. `anyRequest().denyAll()` prevents other URLs from being unexpectedly left open. The config does not arbitrarily disable CSRF; the demo only uses GET.

## 8. Running the Application and Verifying HTTP

To run with Maven:

```bash
export DEMO_API_KEY='local-demo-key-not-for-production'
mvn spring-boot:run
```

If using the Maven wrapper from Spring Initializr:

```bash
export DEMO_API_KEY='local-demo-key-not-for-production'
./mvnw spring-boot:run
```

Windows PowerShell:

```powershell
$env:DEMO_API_KEY = 'local-demo-key-not-for-production'
./mvnw.cmd spring-boot:run
```

This key is **strictly for localhost**, never deploy it on the public Internet. Once the server is running on port 8080, open another terminal:

```bash
curl -i http://localhost:8080/public/ping

curl -i -H 'X-Demo-Key: local-demo-key-not-for-production' \
  http://localhost:8080/api/data

curl -i http://localhost:8080/api/data

curl -i -H 'X-Demo-Key: wrong-key' \
  http://localhost:8080/api/data
```

| Request | Expected result | Explanation |
| --- | --- | --- |
| `GET /public/ping` without key | HTTP 200, body `pong` | Endpoint is `permitAll` |
| `GET /api/data` valid key | HTTP 200, body `hello service-client` | Provider verifies, grants `data:read` |
| `GET /api/data` no key | HTTP 401 | Converter null, authorization/entry point rejects |
| `GET /api/data` wrong key | HTTP 401 | Provider rejects via failure handler |
| `GET /api/data` empty key | HTTP 401 | Converter rejects format |
| `POST /api/data` | Rejected | Filter only matches GET; `denyAll`/CSRF applies |

Error headers/bodies depend on configuration and framework version, so do not expect a fixed JSON error payload. The example key may appear in terminal history; in real production environments, use proper secret handling and HTTPS.

### Flow of a Valid GET

```text
GET /api/data + valid X-Demo-Key
            |
            v
Matcher true
            |
            v
Converter -> unauthenticated HeaderKeyAuthentication
            |
            v
ProviderManager -> HeaderKeyProvider
            |
            v
Digest matches -> verified HeaderKeyAuthentication
            |
            v
AuthenticationFilter sets SecurityContext
            |
            v
SuccessHandler -> chain.doFilter
            |
            v
AuthorizationFilter checks data:read
            |
            v
Controller -> "hello service-client"
```

If the key is wrong, the controller is not called. If the key is missing, the converter does not attempt authentication, yet policy still denies access.

## 9. How Does Converter Differ from Provider and Authorization?

Several seemingly similar questions belong to different responsibilities:

| Question | Component |
| --- | --- |
| Is the header present? | Converter |
| Are there ambiguous duplicate headers? | Converter |
| Is the key still valid and unrevoked? | Provider/identity service |
| Which client owns the key? | Provider/trusted source |
| Which permissions are granted to the client? | Provider/authority mapping |
| Is the request allowed to call `GET /api/data`? | `AuthorizationManager` |
| Which tenant's records may the client read? | Domain authorization |
| Should a session be saved on login success? | Filter and `SecurityContextRepository` |
| Should an invalid key return 401/redirect/JSON? | Failure handler/entry point |

A raw key does not prove a user ID or tenant passed in a query parameter. The key store must map to a stable client/actor/tenant, and authorization must check record scope. The demo's `Authentication.getName()` returns `service-client`, but a principal name is not automatically a stable data key.

**No privilege escalation from input:** Never read `X-Role: ADMIN` and turn it into `SimpleGrantedAuthority("ROLE_ADMIN")` inside the converter. Authorities are valid only when assigned by an authoritative source after verification.

## 10. Comparison with AbstractAuthenticationProcessingFilter and OncePerRequestFilter

`AbstractAuthenticationProcessingFilter` is the base class for many login mechanisms, especially interactive browser/form flows. It includes the `attemptAuthentication` hook, success/failure handlers, session authentication strategy, remember-me integration, and other lifecycle hooks. `AuthenticationFilter` is a composition of components—converter + manager + handlers—avoiding subclassing a filter just to change how credentials are read.

The two classes are **not completely equivalent**. When migrating from an `AbstractAuthenticationProcessingFilter` subclass to `AuthenticationFilter`, review session fixation protection, saved requests, event publishing, remember-me, security context persistence, and post-success behavior rather than merely renaming the class.

A custom `OncePerRequestFilter` can suit logging, metrics, or specialized non-authentication policies. However, if you implement authentication yourself, you must manually manage:

- When to evaluate matchers and credentials?
- What untrusted token to build?
- Which manager/provider to invoke?
- Clearing context on failure?
- Which repository to save context into?
- Whether to continue the filter chain after success?
- Where authentication/authorization errors are translated into responses?
- Whether servlet registration causes double execution?

When all those questions belong to authentication, using `AuthenticationFilter` is usually clearer.

## 11. Prefer Standard Mechanisms When No Special Requirement Exists

Spring Security provides standard mechanisms such as:

- `httpBasic` and `BasicAuthenticationFilter`.
- `formLogin` and `UsernamePasswordAuthenticationFilter`.
- `oauth2ResourceServer().jwt(...)`, `BearerTokenAuthenticationFilter`, and JWT validation/converters.
- OAuth2 Login, SAML, and other supported authentication flows.

**There is no need to write a custom Basic converter or hand-verify JWT signatures in a few lines of code** when the framework already handles the protocol: header parsing, challenges, issuer, audience, expiry, signature, key rotation, error handling, and edge cases.

A custom `AuthenticationFilter` is useful when you have a specialized credential mechanism that needs to plug into Spring Security's manager/provider pipeline. While this lesson uses `X-Demo-Key`, in production evaluate whether a standard identity protocol or gateway with built-in API key support is safer and easier to operate.

### Do Not Confuse Bearer Tokens with API Keys

A bearer access token may carry signatures, issuer, audience, and scopes; an API key is typically an opaque secret managed by your system. The two have different lifecycles, storage, and revocation semantics. Never replace `BearerTokenAuthenticationFilter` with a custom converter that just reads the header and treats any non-empty token as valid.

## 12. Stateful, Stateless, and Saving SecurityContext

One authenticated request does not mean subsequent requests are also authenticated. In the demo:

```text
Request 1: GET /api/data + valid key -> 200
Request 2: GET /api/data no key -> 401
```

Because of `SessionCreationPolicy.STATELESS` and `RequestAttributeSecurityContextRepository`, the result applies only to the current request. **No login session is created automatically.**

For a browser app using cookies:

- Use a repository that persists to HTTP session when appropriate.
- Design login success handler redirects/responses appropriately.
- Keep CSRF protection for state-changing operations.
- Account for session fixation, concurrent sessions, logout, and remember-me.
- Never store raw credentials in the session.
- Know when `SecurityContext` is saved; in modern Spring Security, explicit saves can matter.

For token/JWT APIs:

- Each request must verify the token or consult trusted token introspection.
- Context can be request-scoped; token TTL and revocation are separate mechanisms.
- Permissions must be checked per request and resource; auth success does not grant all permissions.
- Never fall back to a cookie session unintentionally.

## 13. Error Handling: Filter Failure Handler vs. Entry Point

Both cases can return HTTP 401, yet take different paths:

```text
Header present but invalid
    Converter -> token
    Provider -> AuthenticationException
    AuthenticationFilter.failureHandler -> HTTP 401

Header absent
    Converter -> null
    Filter -> chain continues
    AuthorizationFilter rejects anonymous
    ExceptionTranslationFilter -> AuthenticationEntryPoint -> HTTP 401
```

Not every authentication filter error is handled by `ExceptionTranslationFilter`. Likewise, `@RestControllerAdvice` is not guaranteed to catch exceptions thrown from security filters before the controller.

HTTP 403 usually indicates the caller is authenticated but lacks an authority. A rate limiter may return 429; IDP/DB outages may require 5xx/503 per policy. Do not infer from HTTP 401 whether the password was wrong or the user exists.

Public responses should be neutral, never exposing raw `ex.getMessage()`, credential headers, or database details. Internal logging can record the error type and correlation ID without secrets. Define protocol-level failure recovery rather than silently granting reduced privileges when the auth backend fails.

## 14. Security Hardening for Custom Converters/Filters

Items to evaluate if bringing an API key design into production:

1. **TLS:** credentials sent in headers can still be intercepted over plain HTTP.
2. **Key source:** generate high-entropy random secrets with separate key IDs, and check expiration and revocation.
3. **Storage:** store hashed/HMACed keys in a controlled store; never keep plaintext keys in code, committed configs, or logs.
4. **Comparison:** avoid plain string `equals` when timing leaks matter; constant-time digest comparison is one layer of defense, not a replacement for rate limiting.
5. **Request limits:** enforce policies on header length, duplicate headers, encoding, and normalization.
6. **Rate limiting:** defend against key brute-forcing and hashing/backing-store DoS.
7. **Stable principal ID:** bind keys to server-side account/client IDs and tenants.
8. **Least privilege:** grant only defined permissions; enforce owner/resource authorization on endpoints.
9. **Rotation/revocation:** reject old keys within SLA windows and keep cache invalidation bounded.
10. **No secret logging:** raw headers, passwords, bearer tokens, and session cookies must never appear in traces.
11. **No unintended `permitAll`:** a null converter result must never become anonymous access to a protected path.
12. **Filter order:** specify the chain and position with proper authentication/CSRF support.
13. **Multiple providers:** accept only token types matching the contract; avoid ambiguous provider fallbacks.
14. **Session policy:** keep stateless/stateful explicit; do not mix header auth with unintended long-lived sessions.
15. **Error responses:** generic to clients, rich telemetry for operations, no account/key leakage.
16. **Version updates:** track current Spring Security dependencies and advisories regularly.

### Do Not Call SHA-256 of a Key "Password Hashing"

The demo uses a SHA-256 digest to illustrate comparing an **API key expected to have high entropy**. For human-chosen passwords, use a `PasswordEncoder` like BCrypt, Argon2, or equivalent with a work factor; raw SHA-256 is far too fast for that purpose. The two problems are not interchangeable.

## 15. Testing Matrix Across Converter, Provider, Filter, and Authorization

| Layer | Case | What to verify |
| --- | --- | --- |
| Converter | No header | `convert(req) == null` |
| Converter | Single well-formed header | Unauthenticated token, empty authorities |
| Converter | Empty header | `BadCredentialsException` |
| Converter | Two headers or too long | Rejected |
| Converter | Has `X-Role: ADMIN` | Does not grant role from input |
| Provider | Valid API key | Server-assigned principal, `data:read` authority |
| Provider | Invalid API key | Not authenticated |
| Provider | Unsupported token type | `supports(...) == false` |
| Provider | Client attempts passing trusted token | Does not bypass verification |
| Filter | Matcher does not match | Converter is not called |
| Filter | Success with continue handler | Controller invoked exactly once |
| Filter | Failure | `SecurityContext` holds no trusted result |
| HTTP | Public endpoint anonymous | 200 |
| HTTP | Protected endpoint valid key | 200, expected body |
| HTTP | Protected endpoint missing/invalid key | 401 |
| HTTP | Authenticated but lacks authority | 403 |
| HTTP | Wrong method/path | Not opened automatically |
| Context | Next request without key | Does not retain authenticated session from prior request |
| Chain | Two `SecurityFilterChain`s | Right chain selected by matcher/order |
| Registration | Filter bean both auto-registered and `addFilter` | No double invocation |
| Safety | Logs/errors | No raw keys, passwords, or tokens leaked |
| Tenant | Tenant A key accessing tenant B resource | Rejected by domain policy |
| Revocation | Revoked key | New requests rejected |

### Notes for Writing Integration Tests

With Spring Security Test and MockMvc, start the actual `SecurityFilterChain` rather than calling the controller directly. Separately test both **missing header** (converter returns null) and **invalid header** (provider throws an exception), as they go through two different handlers.

Test the default success handler pitfall: if you omit the four-parameter override, the filter may fail to forward the request to the controller. Assert the response body `hello service-client`, not just a vague success status.

Test multi-chain setups: if a real app has two chains, a request matching the first chain will not run the second. Verify the filter is not accidentally attached to browser login or public endpoints.

## 16. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Converter builds an authenticated token | Verification bypass | Converter returns untrusted `presented`, provider returns `verified` |
| Converter assigns roles from request | Privilege escalation | Provider loads trusted authorities |
| Converter returns null on `permitAll` endpoint | Exposes data | Fix authorization rules |
| Forgetting `setRequestMatcher` | Filter processes too many URLs | Match specific path/method |
| Using username/password token type for API key | May pick wrong provider | Custom token type or standard DSL |
| Bypassing `AuthenticationManager` | Reimplementing authentication | Call manager/provider |
| Placing filter after `AuthorizationFilter` | Rejected before principal exists | Check filter order |
| Default success handler on REST data API | Redirects or never reaches controller | Handler that continues chain |
| Filter auto-registered twice | Request runs through filter twice | Avoid servlet `@Bean` filter alongside `addFilter` |
| Not picking the right repository | Lost state or unintended persistence | Explicit context/session policy |
| Assuming every 401 comes from converter | Wrong debugging path | Distinguish failure handler vs. entry point |
| Relying on `@RestControllerAdvice` for security failures | Filter errors missed | Use security handlers |
| Disabling CSRF unconditionally | Browser cookies exposed to CSRF | Keep policy for state-changing requests |
| Passing key in query string | Leaks in URL/history/logs | Send credential in header + TLS |
| Low-entropy SHA-256 key | Easily guessed | Strong random keys and rotation |
| Not testing duplicate headers | Proxy/app parsing mismatch | Enforce header format limits |
| Trusting `getName()` as account ID | Breaks on rename/tenant overlap | Use stable IDs |
| Not testing statelessness | Unintended sessions appear | Request 2 without key must be rejected |
| Mutating `SecurityContextHolder` in converter | Context leakage | Leave it to the filter |
| Skipping actual chain tests | Passes unit tests, fails in prod | MockMvc/integration filter tests |

## 17. Self-Check Questions

**Question 1.** What does `AuthenticationConverter.convert` returning null mean?  
**Answer:** No authentication attempt is created from that request; the filter continues, and authorization still applies.

**Question 2.** Should a converter seeing `X-Role: ADMIN` assign `ROLE_ADMIN`?  
**Answer:** No. Roles from the client are untrusted; only a verified provider/authority source decides permissions.

**Question 3.** Why is `AuthenticationManager` needed after the converter?  
**Answer:** To verify the credential using the right provider and produce an authenticated result.

**Question 4.** Does `setRequestMatcher` grant permissions for a URL?  
**Answer:** No. It only decides whether the filter handles that request; permissions belong to authorization.

**Question 5.** Why is the four-parameter success handler useful for APIs?  
**Answer:** It can call `chain.doFilter` so the request proceeds to authorization and the controller.

**Question 6.** Why doesn't a valid-key request #1 make a keyless request #2 valid?  
**Answer:** Because the demo is stateless and uses a request-attribute context without saving a session.

**Question 7.** What can happen if you use a `@Bean` filter and `http.addFilterAfter` together?  
**Answer:** The filter can be registered to run twice or execute outside the Spring Security chain.

**Question 8.** Do a wrong header and a missing header go to the same handler?  
**Answer:** Not necessarily. An invalid key goes through the filter's failure handler; a missing key typically goes through authorization/entry point.

**Question 9.** When should you choose a manager resolver?  
**Answer:** When selecting a manager based on trusted context, such as multiple realms/issuers; never allow bypasses via a self-declared tenant header.

**Question 10.** Should a custom `AuthenticationFilter` verify JWT signatures manually from an arbitrary string?  
**Answer:** No, when Spring Security OAuth2 Resource Server already provides standard decoders and validation.

**Question 11.** Can an authenticated caller with `data:read` automatically read every tenant's data?  
**Answer:** No. Owner/tenant checks are still required in domain policy.

**Question 12.** Does `@RestControllerAdvice` catch all authentication failures from filters?  
**Answer:** No. Security filters run before MVC and use their own failure handlers and entry points.

## Conclusion

`AuthenticationConverter` converts an HTTP request into an **unverified `Authentication`**. `AuthenticationFilter` uses a matcher to decide when to convert, invokes `AuthenticationManager`/`AuthenticationProvider`, updates `SecurityContext`, and hands outcomes to success/failure handlers. Only then do `AuthorizationFilter` and domain policies decide what the caller may do.

A sound security integration requires **a narrow request matcher, a provider matching the credential type, a handler suited to REST vs. browser, accurate filter ordering, a context repository aligned with the session model, and tests for both missing and invalid credentials**.

**Remember:** *Converter reads evidence. Provider verifies. Filter manages outcomes. Authorization enforces permissions.*

### Official Documentation

- [Spring Security — AuthenticationConverter API](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/web/authentication/AuthenticationConverter.html)
- [Spring Security — AuthenticationFilter API](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/web/authentication/AuthenticationFilter.html)
- [Spring Security — AuthenticationSuccessHandler API](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/web/authentication/AuthenticationSuccessHandler.html)
- [Spring Security — Servlet Architecture / Adding Filters](https://docs.spring.io/spring-security/reference/7.0/servlet/architecture.html)
- [Spring Security — SecurityContext persistence](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/persistence.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/architecture.html)
- [Spring Boot 4.1.2 – release](https://github.com/spring-projects/spring-boot/releases/tag/v4.1.2)
