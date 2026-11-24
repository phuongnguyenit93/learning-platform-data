# Choosing an AuthenticationProvider, Converter, or Filter Based on Integration Requirements

> **Scope:** Spring Security 6 on the **Servlet stack**, Java 17+, Spring Boot 3.x. This lesson helps you choose the right extension point when integrating API keys, custom identity systems, specialized HTTP headers, or non-default login flows: when to use an `AuthenticationProvider`, an `AuthenticationConverter`, a built-in authentication filter, or a custom `OncePerRequestFilter`. The focus is on separation of responsibilities, avoiding reimplementing existing mechanisms, controlling success/failure handling, and ensuring every request passes through the right `SecurityFilterChain`. Spring WebFlux has corresponding APIs, but does not directly use the Servlet classes covered here.

## 1. Quick Selection Rule: What Needs to Change?

Do not start by writing a new filter. Ask **which point in the existing authentication process does not meet the requirement**.

| Practical Need | Preferred Extension Point | Reason |
| --- | --- | --- |
| Credentials are received in a format already supported by the framework, but must be verified against a different source | Appropriate `AuthenticationProvider`, or an adapter for `UserDetailsService` | Verifying secrets/identity belongs to the **provider** layer, not HTTP parsing |
| Non-standard HTTP header/form/body that must be converted into an authentication request | `AuthenticationConverter` or the built-in mechanism's converter | Converts **HTTP request → unauthenticated Authentication** |
| Need to trigger authentication at a specific URL, manage success/failure, session, and context persistence | `AuthenticationFilter` / `AbstractAuthenticationProcessingFilter` if suitable | Filter manages **execution timing and HTTP lifecycle** |
| Every request carries custom credentials per a custom protocol; standard filters do not fit | Thin `OncePerRequestFilter`, delegating to converter + manager | Only write the layer that **reads the request and wires the flow**; do not put authentication business logic in the filter |
| Standard JWT or opaque bearer token authentication | `oauth2ResourceServer().jwt()` / `opaqueToken()` | Leverage standard resource server, validators, and entry points; **do not parse JWTs manually** |
| OAuth2/OIDC login via an identity provider | `oauth2Login()` and its client extension points | The framework already handles redirects, state, code exchange, and many security measures |
| Standard username/password form login | `formLogin()`, `DaoAuthenticationProvider`, `UserDetailsService`, `PasswordEncoder` | No custom filter is needed just to change where users are stored |
| Want to use roles/scopes of an authenticated identity to check permissions | `GrantedAuthoritiesMapper`, JWT authorities converter, authorization rules | **Authorization** is not a reason to write a new authentication filter |

**Summary:** Converter *reads and packages*, Provider *verifies*, Filter *decides when authentication is requested and how to integrate with HTTP*, `AuthenticationManager` *coordinates providers*. Hitting the right layer avoids duplicated logic, avoids misreading credentials, and simplifies testing.

## 2. Three Distinct Responsibilities in the Servlet Architecture

```text
HTTP request
    |
    v
Servlet container
    |
    v
DelegatingFilterProxy -> FilterChainProxy
                             |
                 selects first matching SecurityFilterChain
                             |
                             v
                    Authentication filter
                             |
                   AuthenticationConverter
                   reads header/body/cookie...
                             |
                             v
                Authentication token (unauthenticated)
                             |
                             v
                    AuthenticationManager
                    (typically ProviderManager)
                             |
                  selects AuthenticationProvider
                             |
                 +-----------+-----------+
                 |                       |
          authenticate() OK      AuthenticationException
                 |                       |
                 v                       v
       Valid Authentication        failure handler / 401
                 |
                 v
       creates/sets SecurityContext
       saves if policy requires
                 |
                 v
       AuthorizationFilter / controller
```

Simplified diagram: some framework filters may place the converter and processing logic in different classes, and exact ordering depends on the `SecurityFilterChain`. For per-request authentication, there are cases where context is **not persisted** across requests; for session-based login, it may **need to be persisted**.

### 2.1. Authentication Is Both a Request and a Result

`Authentication` can represent:

- **Unauthenticated request:** principal or credentials from the HTTP request, `isAuthenticated() == false`.
- **Authenticated result:** verified principal, authorities granted by a trusted server, `isAuthenticated() == true`.

In a partner integration example, the converter creates an **unauthenticated** token carrying the API key; the provider returns an **authenticated** token with principal `partner-A` and authority `ROLE_PARTNER` after verifying the key. Never trust any authority sent by the client in a header.

### 2.2. AuthenticationConverter: Only Converts Input Data

The `org.springframework.security.web.authentication.AuthenticationConverter` interface has the method:

```java
Authentication convert(HttpServletRequest request);
```

This is an **illustrative API signature**, not a standalone Java class. The converter may return `null` when the request does not contain the kind of credentials it handles; it may throw `AuthenticationException` when the data is present but malformed, depending on the designed contract.

A converter should **not** query the database itself, verify passwords/API keys itself, grant `ROLE_ADMIN` itself, open a session, or write the HTTP response. If the converter must read the body, note that the body stream can only be read once unless wrapped, and avoid breaking form/multipart parsing for downstream components.

### 2.3. AuthenticationProvider: Proves Identity

The `org.springframework.security.authentication.AuthenticationProvider` interface typically has:

```java
Authentication authenticate(Authentication authentication)
        throws AuthenticationException;

boolean supports(Class<?> authentication);
```

`supports` describes the **token type** the provider handles; returning `true` does not obligate the provider to always succeed in authenticating. A provider can:

- return an authenticated `Authentication` when the credentials are valid;
- throw `BadCredentialsException` or an appropriate `AuthenticationException` subclass on failure;
- return `null` if it cannot authenticate the token under its contract, allowing `ProviderManager` to try another provider in a multi-provider setup.

A provider should not know about specific URLs/controllers, read the servlet request itself, or directly send a 401 response. The provider verifies data from the token and supplies a trusted principal/authorities.

### 2.4. Filter: Lifecycle Over HTTP

An authentication filter can:

1. Check which requests fall within the scope requiring authentication.
2. Pass the request to a converter or parse credentials per the contract.
3. Call `AuthenticationManager.authenticate(...)`.
4. On success, create a new `SecurityContext` and attach it to the holder; save the context if the policy/flow requires.
5. On failure, clear the context appropriately, invoke `AuthenticationFailureHandler` or return an appropriate entry point response.
6. Decide whether to **continue the filter chain** or **terminate the response** (e.g., a login endpoint returning JSON/redirect).

A filter is a high-privilege extension point: writing it in the wrong order can bypass authorization, overwrite an already authenticated user, leak secrets in logs, or cause clients to receive 200 even when authentication failed.

## 3. Decision Tree: Choose the Lowest Layer That Meets the Requirement

```text
New integration requirement?
   |
   +-- Is it standard OAuth2/OIDC/JWT/SAML2/LDAP/form login?
   |      |
   |      +-- Yes -> prefer built-in integration module,
   |                 custom converter/mapper/provider only at supported extension points
   |
   +-- Is the HTTP credential format already supported by the framework?
   |      |
   |      +-- Yes, only verification source differs -> provider / UserDetailsService
   |      |
   |      +-- No, but is there a filter that handles matching requests?
   |              |
   |              +-- Yes -> add an AuthenticationConverter
   |              +-- No -> use AuthenticationFilter with a request matcher,
   |                          or a thin OncePerRequestFilter
   |
   +-- Need to authenticate every HTTP request or a login exchange that creates a session?
          |
          +-- Every request -> stateless context, filter continues chain on success
          |
          +-- Login exchange -> success/failure handlers,
                                session strategy, saveContext, CSRF when needed
```

**Practical rule:** if you only need to verify passwords against a different database, do not start with `OncePerRequestFilter`. If you only rename the header carrying a credential, do not build a new `AuthenticationProvider` when an existing provider already verifies that exact token type. If you are handling JWTs, do not reimplement signature verification and `iss`/`aud`/`exp` checks in hand-rolled Java.

### Choosing by Integration Type

| Case | Recommendation | Avoid |
| --- | --- | --- |
| Users log in via form, data stored in an internal system | `UserDetailsService` or a specialized provider if verification logic goes beyond DAO | Reading the password in a custom filter and comparing strings manually |
| Certificate/TLS client authentication | Spring Security X.509 mechanism and container/proxy configuration | Trusting an arbitrary certificate header sent by the client |
| Partner API key in a custom header | Converter + provider + appropriate filter, or standard filter with converter | Calling `setAuthenticated(true)` as soon as a non-empty header string is seen |
| JWT issued by a standard IdP | `oauth2ResourceServer().jwt()`, decoder/validators/authorities mapper | Decoding the Base64 payload manually and trusting claims |
| Opaque token requiring introspection | Resource server opaque token + introspector | Treating any non-empty token as valid |
| Login returning JSON and creating a session | `AuthenticationFilter`/equivalent filter with success/failure handlers and `SecurityContextRepository` | Login controller only setting `SecurityContextHolder` and forgetting explicit save |
| Only need tenant permission checks or role mapping | Authorities mapper or authorization policy | Putting all authorization logic inside the provider |
| Changing the Authorization header format | Converter or appropriate authentication resolver | Rewriting the entire AuthenticationManager |

## 4. Coordinating ProviderManager and Multiple AuthenticationProviders

`ProviderManager` is the commonly used implementation of `AuthenticationManager`. It iterates through registered providers, checks `supports`, and attempts authentication per contract. Once a provider returns a valid result, the process can conclude; if no provider can handle the token, the system may throw `ProviderNotFoundException`.

Illustrative example:

```java
AuthenticationManager manager = new ProviderManager(
        new PartnerKeyAuthenticationProvider());
// This is a fragment: the provider class is defined in the full example below.
```

Do not write a provider that simply returns `true` for every `Authentication` type. If a provider claims to handle all tokens without actually verifying each type, you risk blocking other login flows or accidentally granting the wrong identity.

### A Provider Only Accepts Its Exact Token Type

```java
@Override
public boolean supports(Class<?> type) {
    return PartnerKeyAuthenticationToken.class.isAssignableFrom(type);
}
```

**Warning:** `supports` does not verify the validity of credentials by itself. It is only a provider selection condition. The `authenticate` logic must still verify the secret/signature, data source, expiration, account status, and related business constraints.

### Do Not Create a Valid Authentication from Untrusted Data

Insecure example:

```java
// ANTI-PATTERN; not a standalone Java file.
String username = request.getHeader("X-User");
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(
        UsernamePasswordAuthenticationToken.authenticated(
                username, null, List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))));
SecurityContextHolder.setContext(context);
```

If the header can be sent by the client itself, any user can impersonate an admin. Even when there is an authenticating reverse proxy in front, the application must verify the **trust boundary**: which trusted proxies are allowed to add the header, whether the proxy strips client-supplied headers, whether the connection between proxy and backend is protected, and whether the data is tamper-proof.

## 5. Choosing a Built-In Filter or Writing a Custom OncePerRequestFilter?

### 5.1. AuthenticationFilter: A Reusable Composite Component

`org.springframework.security.web.authentication.AuthenticationFilter` takes an `AuthenticationManager` and an `AuthenticationConverter`. It is suitable when you need to authenticate at an endpoint matched by a `RequestMatcher` with explicit success/failure handlers, such as a **login/exchange endpoint**.

```java
// Illustrative fragment in Spring Security configuration, not a standalone file.
AuthenticationFilter filter =
        new AuthenticationFilter(authenticationManager, converter);

filter.setRequestMatcher(
        new AntPathRequestMatcher("/auth/exchange", "POST"));

filter.setSuccessHandler((request, response, authentication) -> {
    response.setStatus(HttpServletResponse.SC_OK);
});

filter.setFailureHandler((request, response, exception) -> {
    response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
});
```

For real-world use, you must place the filter into the right `SecurityFilterChain` and review CSRF, error handling, security context persistence, and session strategy. The classes to import are `AuthenticationFilter`, `AntPathRequestMatcher`, `HttpServletResponse`, along with their corresponding dependencies.

**Common pitfall:** an authentication filter used for a **login endpoint** may **terminate the response in its success handler**, rather than continuing by default to a controller like a per-request header filter for resources. If you want a request with credentials to continue to `AuthorizationFilter` and the controller, choose a filter with a suitable lifecycle or write a very thin adapter.

### 5.2. OncePerRequestFilter for Custom Per-Request API Authentication

`OncePerRequestFilter` helps implement a filter that runs once under dispatch conditions managed by the framework. It does **not automatically** know how to authenticate, save context, or return security errors. If you use it, make sure to:

- Restrict registration only to the chain/URLs that need handling;
- Use a dedicated converter for parsing;
- Call an `AuthenticationManager` configured with a dedicated provider;
- Set the authenticated `SecurityContext` only after the provider returns a result;
- Choose stateful/stateless and repository explicitly;
- Handle `AuthenticationException` without leaking secrets;
- Continue `FilterChain.doFilter` when valid;
- Avoid registering the filter twice (both as a global servlet filter and as a security filter).

Use the thin filter as an **adapter**; do not turn it into a secret-checking service, user store, or authorization engine.

### 5.3. Controlling Filter Position

Authentication must be established **before** the request reaches the authorization step. For example:

```java
http.addFilterBefore(
        new PartnerKeyFilter(authenticationManager, converter),
        UsernamePasswordAuthenticationFilter.class);
```

This is a configuration snippet, not a standalone file. Choose the anchor based on the actual filter configuration; if the chain does not use form login, you still need to verify the order and how the framework positions filters by anchor class. Never place a custom authentication filter after `AuthorizationFilter`, because authentication would happen too late to grant access.

**Important:** Spring Boot can automatically register any bean of type `jakarta.servlet.Filter` with the Servlet container. If you also add it via `http.addFilterBefore`, the filter can run **twice at two levels**. The runnable example below **instantiates the filter directly inside SecurityConfig without declaring it as `@Component` or `@Bean`**, to avoid auto-registration.

## 6. Runnable Example: Partner Sends X-Partner-Key on Every Request

We will implement a demo API with `GET /partner/me`. The client sends a secret via the `X-Partner-Key` HTTP header; the converter only reads the header, the provider verifies the secret and returns principal `partner-A`, the filter attaches authentication to the request, and authorization permits the protected endpoint.

**Learning goal:** a complete example separating `AuthenticationConverter`, `AuthenticationProvider`, and `OncePerRequestFilter`. Do not treat the demo's hard-coded key as a production strategy; real API keys require high entropy, secure storage, rotation, rate limiting, and must never be exposed in logs.

### 6.1. Project Structure and Gradle

Requires **JDK 17+**, **Gradle 8.5** (or a suitable wrapper), Spring Boot **3.3.5**, and Spring Security 6.x managed by Boot:

```text
partner-key-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/
    DemoApplication.java
    PartnerKeyAuthenticationToken.java
    PartnerKeyConverter.java
    PartnerKeyAuthenticationProvider.java
    PartnerKeyFilter.java
    SecurityConfig.java
    DemoController.java
  src/test/java/demo/
    PartnerAuthenticationTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'partner-key-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
```

This is a Gradle Groovy DSL configuration. No JWT/OAuth2 libraries are needed for the demo because it only illustrates integrating a **custom secret key**; when handling real bearer JWTs, use Spring Security Resource Server.

### 6.2. Bootstrap Class

`src/main/java/demo/DemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 6.3. A Token with Two States: Unauthenticated and Authenticated

`src/main/java/demo/PartnerKeyAuthenticationToken.java`:

```java
package demo;

import java.util.Collection;
import java.util.List;

import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public final class PartnerKeyAuthenticationToken
        extends AbstractAuthenticationToken {

    private final String principal;
    private final String credentials;

    private PartnerKeyAuthenticationToken(
            String principal,
            String credentials,
            Collection<? extends GrantedAuthority> authorities,
            boolean authenticated) {
        super(authorities);
        this.principal = principal;
        this.credentials = credentials;
        super.setAuthenticated(authenticated);
    }

    public static PartnerKeyAuthenticationToken presented(String rawKey) {
        return new PartnerKeyAuthenticationToken(
                null, rawKey, null, false);
    }

    public static PartnerKeyAuthenticationToken verified(String partnerId) {
        return new PartnerKeyAuthenticationToken(
                partnerId,
                null,
                List.of(new SimpleGrantedAuthority("ROLE_PARTNER")),
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
}
```

**Design point:** the request token carries the secret with `isAuthenticated() == false`. The resulting token is created only by the provider after verification, has a **server**-assigned principal and role, and does not return the secret in credentials.

In a real application, a token class might also hold a verified issuer, tenant, credential identifier, scopes, expiration, or audit metadata. However, never let the client set `authenticated=true` or authorities from unverified data.

### 6.4. Converter Reads Only the Header Without Authenticating

`src/main/java/demo/PartnerKeyConverter.java`:

```java
package demo;

import java.util.Enumeration;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.authentication.AuthenticationConverter;

public final class PartnerKeyConverter implements AuthenticationConverter {

    @Override
    public Authentication convert(HttpServletRequest request) {
        Enumeration<String> headers =
                request.getHeaders("X-Partner-Key");

        if (!headers.hasMoreElements()) {
            return null;
        }

        String raw = headers.nextElement();

        if (headers.hasMoreElements()
                || raw == null
                || raw.isBlank()
                || raw.length() > 256) {
            throw new BadCredentialsException(
                    "Invalid integration credential");
        }

        return PartnerKeyAuthenticationToken.presented(raw);
    }
}
```

The converter rejects blank, oversized, or multiple separate header values to avoid ambiguity. It does **not** query a database and does **not** grant permissions. Returning `null` when the header is absent means "the converter did not receive a credential", not that the request is `permitAll`: downstream authorization can still return 401.

A production system must also decide rules for **multiple values combined into a single header**, control characters, canonicalization, Unicode, and size limits. Never log the raw header on error.

### 6.5. Provider Verifies the Secret and Grants Identity

`src/main/java/demo/PartnerKeyAuthenticationProvider.java`:

```java
package demo;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;

public final class PartnerKeyAuthenticationProvider
        implements AuthenticationProvider {

    // For local demo only. Never hard-code production secrets!
    private static final byte[] EXPECTED =
            "dev-only-key-123".getBytes(StandardCharsets.UTF_8);

    @Override
    public Authentication authenticate(Authentication authentication)
            throws AuthenticationException {

        if (!(authentication instanceof PartnerKeyAuthenticationToken)) {
            return null;
        }

        Object candidate = authentication.getCredentials();

        if (!(candidate instanceof String raw)
                || !MessageDigest.isEqual(
                        raw.getBytes(StandardCharsets.UTF_8), EXPECTED)) {
            throw new BadCredentialsException(
                    "Invalid integration credential");
        }

        return PartnerKeyAuthenticationToken.verified("partner-A");
    }

    @Override
    public boolean supports(Class<?> authentication) {
        return PartnerKeyAuthenticationToken.class
                .isAssignableFrom(authentication);
    }
}
```

`MessageDigest.isEqual` avoids comparing secrets with `String.equals` in the example. It does not replace length-limiting policies, rate limiting, or secure API key storage; in particular, checking for overly long or malformed headers must be done in the converter/proxy.

**Production must differ from the example:** API keys must be high-entropy random secrets, have lifecycle/expiry/revocation, be stored hashed or verified via a trusted verification service, be transmitted over HTTPS, and never appear in logs. Do not treat having `MessageDigest.isEqual` as proof that the system is secure enough.

The illustrative provider does not read `HttpServletRequest`, does not send responses, and does not decide which endpoints are accessible. That allows testing the provider independently of the web layer.

### 6.6. Thin Filter, Continues Chain on Success

`src/main/java/demo/PartnerKeyFilter.java`:

```java
package demo;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.AuthenticationConverter;
import org.springframework.web.filter.OncePerRequestFilter;

public final class PartnerKeyFilter extends OncePerRequestFilter {

    private final AuthenticationManager manager;
    private final AuthenticationConverter converter;

    public PartnerKeyFilter(AuthenticationManager manager,
                            AuthenticationConverter converter) {
        this.manager = manager;
        this.converter = converter;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        try {
            Authentication candidate = converter.convert(request);

            if (candidate != null) {
                Authentication verified = manager.authenticate(candidate);

                SecurityContext context =
                        SecurityContextHolder.createEmptyContext();
                context.setAuthentication(verified);
                SecurityContextHolder.setContext(context);
            }

        } catch (AuthenticationException exception) {
            SecurityContextHolder.clearContext();
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        try {
            chain.doFilter(request, response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
```

The filter only receives the request, invokes the converter/manager, sets the context, and forwards the request. It contains no secret validation. **With the stateless design** in section 6.7, `saveContext` is not called to persist into a session; subsequent requests must supply the header themselves. When the header is missing, the filter does not set an `Authentication`, leaving `AuthorizationFilter`/the entry point to handle the login requirement.

**Why does catch only wrap converter + manager, and not the entire chain?** Authentication errors from downstream components must be handled by downstream Spring Security mechanisms per their contract; you should not turn every exception thrown by a controller into a 401 from the custom filter. In this demo, the filter catches `AuthenticationException` raised during its own execution and returns 401 without revealing the secret.

**Why clear the context at the end of the request?** To avoid retaining custom authentication state once processing finishes. `SecurityContextHolderFilter` also manages the holder lifecycle; this extra clear is explicit in the demo filter, not a replacement for the framework. For async dispatches or logic propagating context to background threads, you must design specifically around `SecurityContextHolderStrategy` and proper propagation tools rather than relying on thread-locals persisting indefinitely.

### 6.7. Registering the Filter in the Right SecurityFilterChain

`src/main/java/demo/SecurityConfig.java`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.context.NullSecurityContextRepository;

@Configuration
public class SecurityConfig {

    @Bean
    AuthenticationManager partnerAuthenticationManager() {
        return new ProviderManager(
                new PartnerKeyAuthenticationProvider());
    }

    @Bean
    @Order(1)
    SecurityFilterChain partnerChain(
            HttpSecurity http,
            AuthenticationManager partnerAuthenticationManager)
            throws Exception {

        http.securityMatcher("/partner/**");

        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        http.securityContext(context -> context
                .requireExplicitSave(true)
                .securityContextRepository(
                        new NullSecurityContextRepository()));

        http.requestCache(cache -> cache.disable());

        http.exceptionHandling(errors -> errors
                .authenticationEntryPoint((request, response, exception) ->
                        response.sendError(
                                HttpStatus.UNAUTHORIZED.value())));

        http.authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated());

        http.addFilterBefore(
                new PartnerKeyFilter(
                        partnerAuthenticationManager,
                        new PartnerKeyConverter()),
                UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public").permitAll()
                        .anyRequest().denyAll())
                .build();
    }
}
```

The configuration defines two chains:

- Priority 1 chain matches `/partner/**`, does **not** use sessions to store authentication, and runs `PartnerKeyFilter` before authorization. Every partner endpoint requires an authenticated caller.
- The final chain catches the rest; it only permits `/public` and denies all other URLs. Do not use a `permitAll` fallback that makes new URLs public by accident.
- The example's `AuthenticationManager` has only one provider dedicated to `PartnerKeyAuthenticationToken`. Do not use it to authenticate username/password for another part of the application unless you design an appropriate multi-provider manager.
- **Do not declare `PartnerKeyFilter` as `@Component` or `@Bean`.** It is instantiated solely inside the security chain so Spring Boot does not auto-register it a second time as a global Servlet filter.

The demo only uses GET endpoints. If extending to POST/PUT/DELETE, you must design CSRF appropriately for the protocol/client: do not disable CSRF across the entire application just because a custom header exists. For server-to-server APIs that are not cookie-based and have an analyzed threat model, you may consider scoping CSRF policy only to that chain.

### 6.8. Controller Returns Server-Verified Identity

`src/main/java/demo/DemoController.java`:

```java
package demo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/partner/me")
    public String partnerMe(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }
}
```

The controller **does not read X-Partner-Key** and does not verify secrets itself. It simply receives the authentication established by Spring Security. `getName()` in the demo returns `partner-A`, assigned by the provider, not a username sent by the client.

### 6.9. MockMvc Tests Each Boundary

`src/test/java/demo/PartnerAuthenticationTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PartnerAuthenticationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsAvailable() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));
    }

    @Test
    void missingKeyIsUnauthorized() throws Exception {
        mvc.perform(get("/partner/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void validKeyGetsServerAssignedIdentity() throws Exception {
        mvc.perform(get("/partner/me")
                        .header("X-Partner-Key", "dev-only-key-123"))
                .andExpect(status().isOk())
                .andExpect(content().string("partner-A"));
    }

    @Test
    void wrongKeyIsUnauthorized() throws Exception {
        mvc.perform(get("/partner/me")
                        .header("X-Partner-Key", "wrong-key"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void twoHeaderValuesAreRejected() throws Exception {
        mvc.perform(get("/partner/me")
                        .header("X-Partner-Key",
                                "dev-only-key-123", "other"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticationIsNotPersistedToNextRequest()
            throws Exception {
        mvc.perform(get("/partner/me")
                        .header("X-Partner-Key", "dev-only-key-123"))
                .andExpect(status().isOk());

        mvc.perform(get("/partner/me"))
                .andExpect(status().isUnauthorized());
    }
}
```

Expected result with the demo configuration: **6 JUnit tests PASS**, covering a public endpoint, missing header, valid header, wrong secret, two header values, and a subsequent request no longer having authentication. The last test proves stateless behavior, not relying on the previous successful request's result.

To test the provider in isolation, you can instantiate it directly and call `authenticate(PartnerKeyAuthenticationToken.presented(...))` in a unit test; meanwhile, MockMvc proves the filter/converter/manager/authorization are wired together over HTTP. **Testing the provider alone does not prove the filter is registered in the right position.**

### 6.10. Running the Demo and Testing with curl

Inside the `partner-key-demo` directory after installing a compatible JDK and Gradle:

```bash
gradle test
gradle bootRun
```

If using the wrapper, run `./gradlew test`/`./gradlew bootRun` (macOS/Linux) or `.\gradlew.bat test`/`.\gradlew.bat bootRun` (Windows). From another terminal:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/partner/me
curl -i -H 'X-Partner-Key: dev-only-key-123' \
     http://localhost:8080/partner/me
curl -i -H 'X-Partner-Key: wrong-key' \
     http://localhost:8080/partner/me
```

Expected results:

| Request | HTTP status | Body on success |
| --- | --- | --- |
| `GET /public` | **200** | `public` |
| `GET /partner/me`, no header | **401** | — |
| `GET /partner/me`, valid key | **200** | `partner-A` |
| `GET /partner/me`, wrong key | **401** | — |

This is a hard-coded demo key with **no real security value**. In production, transmit secrets over TLS, restrict logging at load balancers/APM, manage credential lifecycles, isolate permissions per partner, and enforce rate limits. Never send real API keys to untrusted services or paste them into public documentation.

## 7. Choosing AuthenticationFilter Instead of OncePerRequestFilter

There is no single "better filter" answer for all cases. Choose according to the **required HTTP behavior**:

### Login/exchange endpoint

A `POST /auth/exchange` request can receive credentials from a converter, have a provider verify them, and have the filter create a session or emit a response depending on the design. `AuthenticationFilter` with `RequestMatcher`, `AuthenticationSuccessHandler`, `AuthenticationFailureHandler`, and `SecurityContextRepository` is a strong candidate.

Mandatory questions: does the success handler return JSON or a redirect? Is session fixation protection needed? CSRF? Is explicit context saving needed? If login returns a token, how is the token signed and how does expiration/revocation work? An `AuthenticationFilter` does not automatically turn a custom token into a trustworthy JWT.

### Per-request API key

A per-request filter **must** continue the chain after successful authentication so the controller receives `Authentication`. If you use `AuthenticationFilter` for this flow, you must understand the success handler lifecycle because many success handlers **terminate the response**. When no suitable configuration option fits, a small `OncePerRequestFilter` like in section 6 can be easier to reason about and test.

### Standard bearer token already in use

If requests use `Authorization: Bearer <JWT>` issued by a reputable IdP, prefer:

```java
// Spring Security configuration fragment, requires OAuth2 Resource Server dependencies:
http.oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
```

Resource server handles signature verification, expiration, and appropriate validators, then creates authentication through the standard mechanism. Depending on your infrastructure, configure `JwtDecoder`, issuer/audience validators, and roles/scopes mapping. Do not copy the API key demo to manually "authenticate" JWTs by Base64-decoding the payload while skipping signature and claim validation.

### Customizing data after authentication

If the integration only needs to map claims/roles/tenant after identity is already authenticated, the right extension point is usually an authorities converter/mapper or an authorization service. Do not create a second authentication filter with authority to swap identities just to turn `scope=read` into `ROLE_READER`.

## 8. SecurityContext Lifecycle and Explicit Save

`SecurityContextHolder` manages the authentication currently in use for the active request. In Spring Security 6, `SecurityContextHolderFilter` typically handles loading from `SecurityContextRepository` and clearing the holder, without automatically saving every context change when `requireExplicitSave(true)`.

### Stateless integration

In the demo:

```java
http.sessionManagement(sm -> sm
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

http.securityContext(sc -> sc
        .securityContextRepository(new NullSecurityContextRepository()));
```

No session authentication is persisted. A new request must send a valid header. `SecurityContextHolder` is populated for the current request so authorization can read it, but it does not survive as "logged in" on subsequent requests. This is a natural choice for machine-to-machine header credentials and supports revocation when the server re-verifies the key per request, depending on caching/verification backend.

### Stateful login

When you want custom login to create a session, in addition to successful authentication you typically must:

1. Choose an appropriate repository for loading/saving, such as `HttpSessionSecurityContextRepository` or a session-backed `DelegatingSecurityContextRepository`.
2. Execute the appropriate session authentication strategy, including session fixation protection and session policies.
3. Create a new `SecurityContext` and set the authenticated `Authentication`.
4. Call `securityContextRepository.saveContext(context, request, response)` **before the response commits** if the flow does not auto-save.
5. Test a second request carrying only the session cookie without resending credentials.

Do **not** simply call `SecurityContextHolder.setContext(context)` and assume it will be saved because `SessionCreationPolicy.IF_REQUIRED` is active. Session policy and repository/save logic are two separate decisions. If using a standard filter, check which mechanisms it already provides to avoid double-saving or duplicating the session strategy.

## 9. AuthenticationException and HTTP Errors: Handling at the Right Layer

A provider can throw:

- `BadCredentialsException` when the key is wrong or unacceptable;
- `AuthenticationServiceException` when the identity verification system cannot operate;
- `LockedException`/`DisabledException`/`CredentialsExpiredException` for appropriate account states;
- other specialized `AuthenticationException` subclasses when the system has multi-step authentication.

Do not respond to clients with the full `exception.getMessage()`, raw headers, tokens, or information revealing whether an account exists. For APIs, a generic 401 is typically used for invalid credentials; for infrastructure errors, emit internal metrics/telemetry and return a contract-compliant response (possibly 5xx/503 depending on design) without leaking details.

### 401 vs 403

| Scenario | Nature | HTTP in Demo API |
| --- | --- | --- |
| No credential but URL requires authentication | Unauthenticated | 401 |
| Key present but wrong | Authentication failure | 401 |
| Key valid, lacking required role | Authorization failure | Typically 403 |
| POST blocked due to missing CSRF token | CSRF protection | Typically 403 |
| Provider encounters data store error | Authentication infrastructure error | Per policy; do not disguise as "wrong password" in telemetry |

`ExceptionTranslationFilter` and `AuthenticationEntryPoint` handle cases arising at the right point in the filter chain, but **a custom authentication filter can run before them**. Therefore, the filter must catch/route its own `AuthenticationException` using an appropriate failure handler or response. Do not assume any error thrown from any filter automatically turns into a 401.

### Protecting Processing Time and Header Length

For API keys/secrets, bound input size and use appropriate comparison/verification operations. Apply rate limiting, timeouts for external identity services, circuit breakers when needed, and avoid overly detailed distinguishing responses. Do not misuse `MessageDigest.isEqual` as a substitute for secret management; it is only a single component at the comparison level.

## 10. Multi-Chain, Ordering, and Avoiding Bypass

When an application has multiple `SecurityFilterChain`s, `FilterChainProxy` selects the **first chain whose matcher matches**. If a custom filter lives only in the `/partner/**` chain, it will not run on `/admin/**` or `/api/**` unless configured in another chain.

```text
@Order(1) securityMatcher("/partner/**")
          -> PartnerKeyFilter -> authenticated()

@Order(2) matches all remaining requests
          -> permitAll("/public") -> denyAll() for other URLs
```

Common pitfalls:

- Placing a match-all fallback **before** the partner chain, preventing the specialized chain from ever being selected.
- Configuring `requestMatchers("/partner/**")` only in authorization while forgetting `securityMatcher` when a dedicated filter policy is needed.
- Registering a custom filter as `@Component` so it runs outside `FilterChainProxy` or runs twice.
- Adding the filter after authorization, causing requests to fail with 401 before the filter has a chance to create an Authentication.
- Protecting only `/partner/me` while a newly added `/partner/admin` endpoint falls into a default `permitAll()` chain.
- Using `web.ignoring()` instead of `permitAll()` for endpoints that still need security headers/filter chain execution.
- Assuming the converter always returns a token; when the header is absent, the converter typically returns `null` and authorization must still protect the endpoint.

The test suite should cover **non-existent** endpoints, **new endpoints under the prefix**, URLs outside the partner scope, and requests without headers. Do not test only the provider in isolation.

## 11. Comparing Six Extension Approaches Through Concrete Problems

### Scenario A: Changing the Username/Password Account Store

Moving from embedded H2 to LDAP or a legacy user database while still accepting standard username/password. If only the user lookup source changes, use `UserDetailsService`/an existing provider or adapter. Do not write a custom form login filter when the request structure has not changed.

### Scenario B: Proprietary Secret Header Requiring Per-Request Verification

Needs a converter to read the header, a provider to verify the secret, a filter that continues after success, and an explicit stateless policy. This is the demo problem. If upstream already supports a standard protocol, prefer built-in modules over inventing a new authentication protocol.

### Scenario C: JWT Token from an Identity Provider

Needs signature, issuer, audience, expiration, algorithm, and key rotation verification. Use OAuth2 Resource Server `jwt()` and customize the decoder/validators/authority converter. Do not call `Base64.getDecoder()` manually and trust `sub`/`roles`; Base64 only encodes text, it does not verify signatures.

### Scenario D: Browser Redirect to an OIDC Provider

Use `oauth2Login()`, configuring client registration and appropriate handlers. Steps like `state`, redirect URI, authorization code, PKCE, and session/CSRF have specific security requirements. Do not implement a simple header filter to replace this entire flow.

### Scenario E: Authenticating Reverse Proxy Supplying a User Header

A header like `X-Authenticated-User` is trustworthy **only after** infrastructure guarantees clients cannot spoof it, the proxy always strips/overwrites the header, and the backend only accepts connections from authenticated proxies. Pre-auth integration or an appropriate provider may be needed, but this is a trust boundary that must be verified—not "see header, grant role".

### Scenario F: Only Business Authorization Needed After Authentication

Once a trusted principal exists and you need to check "can partner A edit invoice X?", implement an authorization policy/service; do not turn the authentication provider into a place that queries every business object. Authentication answers **who**, authorization answers **what they are allowed to do**.

## 12. Systematic Troubleshooting

If a client sends the right key but gets 401:

1. **Check chain selection:** Does `/partner/me` match the right chain containing `PartnerKeyFilter`?
2. **Check position:** Does the filter run before `AuthorizationFilter`? Is it auto-registered twice?
3. **Check converter:** Is the header name right, stripped/modified by a proxy, or duplicated? Never log the raw secret.
4. **Check manager:** Is the provider registered with the right `AuthenticationManager`?
5. **Check `supports`:** Does the token returned by the converter match the class accepted by the provider?
6. **Check provider:** Secret verification, partner status, store timeouts, expiry/rotation.
7. **Check result:** Does the provider return `Authentication.isAuthenticated() == true` with server-assigned principal/authorities?
8. **Check context:** Did the filter place the authenticated token in `SecurityContextHolder` before continuing the chain?
9. **Check policy:** Are the URL's `authenticated()`/`hasRole(...)` rules configured as intended?
10. **Check response:** Was `AuthenticationException` handled by the filter at its position? Is a 403 caused by authorization or CSRF rather than credentials?
11. **Check next request:** Stateless means every request needs the header; do not assume a user remains logged in because an earlier test sent the key.
12. **Check deployment:** HTTPS, reverse proxy, duplicate filters, dispatch mapping, cluster secret rotation, and permissions.

A dangerous failure variant is when the provider throws an error, but the filter catches it and **continues the chain as if it succeeded**. Failure flows must stop or route to a failure handler properly; never manually set `authenticated=true` just to "make the demo work".

### Observing Logs at the Right Level

You can temporarily enable DEBUG for Spring Security in development:

```properties
logging.level.org.springframework.security=DEBUG
```

Never enable logs containing credentials in production. A log line like "Securing GET /partner/me" does not prove the provider was called or the key was verified; use unit tests for providers, MockMvc for the filter chain, and safely designed server-side metrics.

## 13. Design and Testing Checklist

| Question | Pass Criteria |
| --- | --- |
| Changing verification source only or HTTP protocol too? | Choose provider/adapter if only changing backend; converter/filter if HTTP input differs |
| Is there a standard framework integration? | Leverage Spring Security modules before writing custom code |
| What does the converter do? | Parses & validates input structure, returns **unauthenticated** token or null |
| What does the provider do? | Verifies secret/identity, checks status, returns trusted Authentication or throws exception |
| Does the custom token have the right lifecycle? | Client cannot self-establish `authenticated=true` and roles |
| Where does the filter run? | Runs only on the necessary chain, before authorization, no double auto-registration |
| Missing header case? | Grants no Authentication; protected endpoint returns 401 via entry point |
| Wrong/duplicate header case? | Rejects safely without leaking secret |
| Valid case? | Controller sees server-assigned principal/authority |
| Stateful or stateless? | Explicitly choose repository, session policy, explicit save if needed, test independent requests |
| Infrastructure errors? | Telemetry, timeout/failure strategy, safe public response |
| Protocol and secrets? | HTTPS, rate limit, key rotation/revocation, secret management, log redaction |
| Authorization? | Separated from authentication, test 403/roles and deny-by-default |
| Migration/provider swap? | Test both old and new tokens/providers, fail closed when unrecognized |

## 14. Self-Check

1. **What should you choose if you want to load passwords from a different database while keeping standard form login?** Usually start with `UserDetailsService` or a compatible provider; do not write a custom HTTP filter.
2. **May an AuthenticationConverter return an authenticated token on its own?** It should not when merely converting untrusted input; the provider/manager must verify first.
3. **Should an AuthenticationProvider read HttpServletRequest and write HTTP responses?** No; providers should be transport-independent.
4. **Does AuthenticationFilter automatically continue to the controller after success in every configuration?** No; the success handler can terminate the response, making it better suited to login endpoints than some per-request authentication patterns.
5. **When does OncePerRequestFilter have a valid reason to exist?** When no standard filter fits, requiring a thin HTTP adapter to invoke converter/manager and continue the chain.
6. **Why shouldn't you handle JWTs manually by decoding the payload?** A readable payload does not mean the token's signature, issuer, audience, expiration, and algorithm have been verified.
7. **Should seeing an X-User header grant ROLE_ADMIN?** No, unless the trust boundary proves clients cannot spoof the data and role mapping is verified.
8. **Does a custom filter also need to be registered as a Servlet Filter bean?** Usually no; once added to a SecurityFilterChain, duplicate auto-registration must be avoided.
9. **What does stateless mean for authentication on the second request?** Credentials must be supplied on the new request; previous context is not automatically retrieved from HttpSession.
10. **Does custom session login need saveContext?** With explicit save, flows that do not auto-save must call `SecurityContextRepository.saveContext(...)` before the response commits.
11. **Is it right for a filter to continue the chain as successful when the provider throws BadCredentialsException?** Wrong; failures must be handled and the request must never proceed with an untrusted identity.
12. **Must an application write a new provider just to assign business roles/scopes?** No. In many cases an authorities mapper or authorization rules are sufficient.

**Remember:** Extend at the **smallest layer that satisfies the requirement**: `AuthenticationConverter` turns HTTP input into an unauthenticated token, `AuthenticationProvider` verifies credentials and returns a trusted identity, the authentication filter coordinates request/success/failure lifecycle, `AuthenticationManager` selects the provider, and authorization enforces permissions. Prefer standard Spring Security integrations when available; write custom filters only when genuinely necessary, limit their scope, protect secrets, choose session policies explicitly, and test real requests through the filter chain.
