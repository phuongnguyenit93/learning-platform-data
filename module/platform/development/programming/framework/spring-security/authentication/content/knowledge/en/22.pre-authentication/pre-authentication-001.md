# Pre-authentication Model When Identity Is Verified by an Upstream System

## 1. Problem Statement and Learning Outcomes

In many enterprise systems, users log in **before** an HTTP request reaches the Spring Boot application. An SSO portal, identity-aware reverse proxy, API gateway, application server, or X.509 certificate authentication component has already verified the user. The downstream application needs to know **who is calling** and **what that caller is allowed to do**, without forcing the user to re-enter their password at every application.

Spring Security calls this **pre-authentication**. "Pre" means the identity has already been externally verified before entering Spring Security's user identification mechanism. It does **not** mean the application can trust any username string sent by the client.

After this lesson, you should be able to:

1. Draw the trust boundary between the browser/client, the upstream authentication system, and the Spring application.
2. Explain the flow of the principal and authorities when Spring Security uses pre-authentication.
3. Distinguish between `RequestHeaderAuthenticationFilter`, `PreAuthenticatedAuthenticationProvider`, and `UserDetailsService`.
4. Configure a Servlet/Spring MVC example that receives a principal from a header **set only by a trusted gateway**, and then enforce authorization in Spring Security.
5. Test scenarios for missing identity, non-existent users, authenticated users lacking permissions, and principal changes.
6. Recognize risks such as header spoofing, gateway bypass, stale session caching, and conflating authentication with authorization.

## 2. Who Is Responsible for What?

Overview model:

```text
Client / browser
    |
    | 1. SSO login, certificate authentication, or token submission
    v
Trusted identity gateway / reverse proxy
    | 2. Verify client credentials and session/token
    | 3. Strip any client-supplied identity headers
    | 4. Attach verified identity (e.g., X-Verified-User: alice)
    v
Internal channel accessible only to the gateway (TLS/mTLS + network policy)
    |
    v
Spring Boot (Servlet filter chain)
    | 5. Pre-auth filter extracts principal from request
    | 6. AuthenticationManager / provider maps principal to UserDetails + authorities
    | 7. Store successful Authentication in SecurityContext
    | 8. AuthorizationFilter evaluates endpoint permissions
    v
Controller / service
```

**Responsibility of the upstream system:** verify real identity, manage sessions/credentials, prevent spoofing, and forward the verified identity according to a clear contract.

**Responsibility of Spring Security:** receive identity information from **a source with an established trust boundary**, map it to the appropriate account and permissions, check account status (if required by design), build the `Authentication`/`SecurityContext`, and enforce authorization.

**Responsibility of deployment infrastructure:** the application must not be directly reachable from the Internet or from unauthorized network paths with a self-supplied header; every hop between the gateway and the application must be protected. Spring code alone cannot turn an HTTP header sent by an arbitrary caller into proof of authentication.

For example: if the application trusts `X-Verified-User: admin` while a client can connect directly to the application, any client only needs to send this header to impersonate an admin. That is a **trust boundary** flaw, not a minor Spring syntax mistake.

## 3. How Does Pre-authentication Differ from Login and Authorization?

| Concern to Address | Where It Happens in This Model | Result |
| --- | --- | --- |
| Verify password/MFA/SSO or certificate | Upstream authentication system | External identity is verified |
| Pass identity into internal request | Trusted gateway/proxy | Verified principal, e.g., stable user identifier |
| Create `Authentication` in Spring | Pre-authentication filter and provider | Spring Security holds mapped user information |
| Load permissions, check locked/disabled user | `AuthenticationUserDetailsService`/`UserDetailsService` and user checker | Appropriate authorities and account status |
| Decide whether endpoint/data is accessible | `AuthorizationFilter`, `authorizeHttpRequests`, method security | Allow or deny the action |

Two key takeaways:

- Spring Security can use the `AuthenticationManager` APIs even **without re-verifying a password**. Here, "authenticate" in the framework mainly means **processing an already-verified principal**, enriching it with required information, and producing an authentication result.
- Having an identity does not automatically grant full permissions. The gateway returning `alice` only tells us who is calling. Deciding whether `alice` has `ROLE_ADMIN` must still rely on a trustworthy authorization policy.

**Pre-authentication and bearer-token authentication are not identical.** If every request carries a JWT and the Spring application itself verifies the signature, issuer, audience, and expiry before creating a `JwtAuthenticationToken`, then Spring is still **verifying the authentication proof itself** as a resource server. In header-based pre-authentication, Spring typically trusts the authentication result already performed by the gateway; the username string itself carries no cryptographic proof for Spring to verify.

## 4. Spring Security Components (Servlet)

Typical classes for this mechanism reside in `org.springframework.security.web.authentication.preauth`.

### 4.1. `AbstractPreAuthenticatedProcessingFilter`

This is the base class for filters that receive an externally authenticated principal. Subclasses implement:

```java
protected Object getPreAuthenticatedPrincipal(HttpServletRequest request);
protected Object getPreAuthenticatedCredentials(HttpServletRequest request);
```

These two signatures are **API excerpts**, not a standalone Java program. The base class inspects the current `SecurityContext`, extracts the principal/credentials from the request when needed, creates a `PreAuthenticatedAuthenticationToken` to pass to `AuthenticationManager`, and processes the result.

Notable settings:

- `setCheckForPrincipalChanges(true)`: checks for principal changes across requests, instead of always keeping the old authentication if `SecurityContext` is already populated.
- `setInvalidateSessionOnPrincipalChange(true)`: option controlling whether to invalidate the session when the principal changes; the class default is `true`.
- `setContinueFilterChainOnUnsuccessfulAuthentication(...)`: defaults to `true`, allowing the filter chain to continue when the authentication manager throws an `AuthenticationException`. If set to `false`, the exception is thrown immediately and error handling must be arranged accordingly.
- `setSecurityContextRepository(...)`: specifies how the context is persisted after successful pre-auth. Do not rely on session assumptions when designing a stateless system.

By default, if the context already holds an Authentication, the filter does not need to re-process the principal on every request. In a model relying on fresh identity from a gateway, this can cause stale sessions to introduce confusion unless session and principal-change strategies are reviewed.

### 4.2. `RequestHeaderAuthenticationFilter`

This subclass extracts the username from a request header. The default header name is `SM_USER` (for Siteminder compatibility). It can be changed to `X-Verified-User` via `setPrincipalRequestHeader(...)`.

- By default, a missing principal header raises `PreAuthenticatedCredentialsNotFoundException`; `setExceptionIfHeaderMissing(false)` allows ignoring a missing header and letting the authorization mechanism decide.
- If no separate credentials header is specified, the filter uses a dummy string for credentials. This is **not a password** and the pre-auth provider does not verify it.
- The filter **does not verify whether the header was actually set by the gateway**. That guarantee must come from the network architecture, proxy, and trusted protocol.

Other scenarios may use `RequestAttributeAuthenticationFilter`, `J2eePreAuthenticatedProcessingFilter`, or an X.509-specific filter. The extraction mechanism differs, but the principle of separating **upstream identity proof** from **downstream Spring Security authorization** is the same.

### 4.3. `PreAuthenticatedAuthenticationToken`

This is an `Authentication` implementation representing an authentication request based on a principal already verified by another system. The filter typically constructs this token before passing it to the manager; the provider returns an authenticated Authentication with the appropriate authorities.

Do not manually build an "authenticated" token from an untrusted header and place it directly into `SecurityContextHolder`. Doing so bypasses both identity provenance and the permission-loading/account-checking pipeline.

### 4.4. `PreAuthenticatedAuthenticationProvider`

This provider handles `PreAuthenticatedAuthenticationToken` and invokes an `AuthenticationUserDetailsService<PreAuthenticatedAuthenticationToken>`. It does not re-check the user's password, because the pre-auth contract assumes the upstream system already did so.

Typically, the provider loads `UserDetails` and authorities and then checks account status (e.g., disabled, locked, expired) via `UserDetailsChecker`. If the principal does not exist, user loading can fail. Putting `ROLE_ADMIN` into an untrusted header and blindly trusting it is not a safe authorization strategy.

### 4.5. `UserDetailsByNameServiceWrapper`

This is an adapter that allows the provider to use a traditional `UserDetailsService.loadUserByUsername(...)` when receiving a principal via an Authentication token. It is suitable when permission data lives in a database/LDAP or a managed internal identity store.

If the upstream system supplies verified authorities, Spring Security provides other utilities such as `PreAuthenticatedGrantedAuthoritiesUserDetailsService`. Either way, you must clearly design **which permission source is authoritative**, how role names are normalized, the permission lifecycle, and when data must be refreshed.

## 5. Detailed Request Flow

Suppose user `alice` has logged in successfully at the gateway and calls `GET /api/me`.

1. The browser holds a session/credential with the gateway. The gateway verifies it for this request.
2. The gateway strips any client-side identity headers and sets `X-Verified-User: alice` on the internal request sent to Spring.
3. `FilterChainProxy` selects the `SecurityFilterChain` for the request. The pre-auth filter reads the principal `alice`.
4. The filter creates a `PreAuthenticatedAuthenticationToken` with principal `alice` and dummy credentials and invokes `AuthenticationManager`.
5. `PreAuthenticatedAuthenticationProvider` receives the token, uses the user details service to load account `alice`, obtaining `ROLE_USER` and the account status.
6. The provider returns an authenticated Authentication. The filter stores the Authentication in the request's `SecurityContext` and, depending on configuration, may save it to `SecurityContextRepository`.
7. `AuthorizationFilter` evaluates the rule requiring an authenticated user for `/api/me`. The rule passes, and the controller reads `Principal.getName()` as `alice`.

For `GET /api/admin`, if `alice` lacks `ROLE_ADMIN`, the request is rejected with **403 Forbidden** even though her identity is valid. If a request lacks an identity, an API configuration typically returns **401 Unauthorized**. These status codes depend on entry point and access-denied handling configuration; the example below explicitly configures the 401 path.

## 6. Java 17+ Example: Spring Boot MVC Receiving Identity from a Gateway

The self-contained example below uses **Spring Boot 3.5.16**, Spring Security 6.x, and Java 17+. It uses MVC/Servlet to apply the `RequestHeaderAuthenticationFilter`/`PreAuthenticatedAuthenticationProvider` classes directly. The actual gateway sits **outside** this project; therefore, the example only verifies the identity-mapping portion inside Spring via local requests/tests. **Do not expose this application to an untrusted network with header-based pre-auth without a real protecting gateway.**

Project structure:

```text
preauth-demo/
├── pom.xml
├── src/main/java/demo/preauth/PreAuthDemoApplication.java
└── src/test/java/demo/preauth/PreAuthDemoApplicationTests.java
```

Create `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>preauth-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

Create `src/main/java/demo/preauth/PreAuthDemoApplication.java`:

```java
package demo.preauth;

import java.security.Principal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsByNameServiceWrapper;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class PreAuthDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PreAuthDemoApplication.class, args);
    }
}

@Configuration
@EnableWebSecurity
class SecurityConfig {
    @Bean
    UserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}not-used")
            .roles("USER")
            .build();
        UserDetails bob = User.withUsername("bob")
            .password("{noop}not-used")
            .roles("USER", "ADMIN")
            .build();
        return new InMemoryUserDetailsManager(alice, bob);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, UserDetailsService users) throws Exception {

        UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken>
            lookup = new UserDetailsByNameServiceWrapper<>();
        lookup.setUserDetailsService(users);

        PreAuthenticatedAuthenticationProvider provider =
            new PreAuthenticatedAuthenticationProvider();
        provider.setPreAuthenticatedUserDetailsService(lookup);

        RequestHeaderAuthenticationFilter preAuth =
            new RequestHeaderAuthenticationFilter();
        preAuth.setPrincipalRequestHeader("X-Verified-User");
        preAuth.setExceptionIfHeaderMissing(false);
        preAuth.setAuthenticationManager(new ProviderManager(provider));
        preAuth.setCheckForPrincipalChanges(true);
        preAuth.setSecurityContextRepository(
            new NullSecurityContextRepository());

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(context -> context
                .securityContextRepository(new NullSecurityContextRepository()))
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(
                    new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .addFilterBefore(preAuth, UsernamePasswordAuthenticationFilter.class)
            .build();
    }
}

@RestController
class ApiController {
    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/api/me")
    String currentUser(Principal principal) {
        return principal.getName();
    }

    @GetMapping("/api/admin")
    String admin() {
        return "admin";
    }
}
```

**Explanation of key choices:**

- `preAuth` is instantiated **locally inside `SecurityFilterChain`**, avoiding declaring it as a Servlet Filter `@Bean` that Spring Boot would accidentally auto-register outside the Spring Security filter chain.
- `UserDetailsByNameServiceWrapper` connects the pre-auth provider to the `alice`/`bob` account list. The password `{noop}not-used` is only test data to make `UserDetails` complete; this flow **does not check that password**. Do not use `{noop}` in real systems.
- `setExceptionIfHeaderMissing(false)` lets `/public` run when no identity header is present; `/api/**` routes still require authentication.
- `SessionCreationPolicy.STATELESS` and `NullSecurityContextRepository` express the choice **not to persist Spring Security authentication across HTTP sessions**. Each request is authenticated by the gateway and Spring re-maps the principal. If sessions are used in production, policies are needed for principal change, logout, expiry, and permission updates.
- `HttpStatusEntryPoint(UNAUTHORIZED)` defines the 401 behavior when authentication is required but the request has no valid principal.
- `formLogin` and `httpBasic` are disabled because this example accepts identity only from the gateway; adding a secondary login mechanism within the same trust path could create a way to bypass upstream controls.
- `addFilterBefore(preAuth, UsernamePasswordAuthenticationFilter.class)` places the filter in the authentication region, before authorization. `UsernamePasswordAuthenticationFilter` is used as an **ordering anchor** even though form login is disabled.
- The rules in `authorizeHttpRequests` perform **authorization**. `bob` has `ROLE_ADMIN`; `alice` only has `ROLE_USER`. `hasRole("ADMIN")` checks the `ROLE_ADMIN` authority.

### Running Locally on a Development Machine

Inside the `preauth-demo` directory:

```bash
mvn spring-boot:run
```

In another terminal (only for **local environments** or equivalent test paths; the commands with headers here intentionally simulate the gateway):

```bash
curl -s http://localhost:8080/public
curl -s -H "X-Verified-User: alice" http://localhost:8080/api/me
curl -s -H "X-Verified-User: bob" http://localhost:8080/api/admin
curl -i http://localhost:8080/api/me
curl -i -H "X-Verified-User: alice" http://localhost:8080/api/admin
curl -i -H "X-Verified-User: unknown" http://localhost:8080/api/me
```

The first three response bodies, in order:

```text
public
alice
admin
```

The remaining three requests illustrate these outcomes:

| Request | Expected | Reason |
| --- | --- | --- |
| `/api/me` without header | HTTP 401 | No principal provided by upstream |
| `/api/admin` as `alice` | HTTP 403 | Valid principal present, missing `ROLE_ADMIN` |
| `/api/me` as `unknown` | HTTP 401 | Provider could not find account in user store |

Error headers/bodies depend on how Spring Boot constructs responses; here we check the HTTP status. `curl -s` does not add a trailing newline, so running them consecutively may print bodies next to each other on screen.

**Limitation of the demo:** anyone able to reach `localhost:8080` and set the `X-Verified-User` header can impersonate a user. The demo illustrates why **a gateway and blocking direct connections are mandatory** in actual deployments; it is not a standalone production security configuration.

## 7. Integration Testing with MockMvc

Create `src/test/java/demo/preauth/PreAuthDemoApplicationTests.java`:

```java
package demo.preauth;

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
class PreAuthDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void trustedPrincipalIsMappedToSpringAuthentication() throws Exception {
        mvc.perform(get("/api/me")
                .header("X-Verified-User", "alice"))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void authenticatedUserMayLackAuthority() throws Exception {
        mvc.perform(get("/api/admin")
                .header("X-Verified-User", "alice"))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin")
                .header("X-Verified-User", "bob"))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    void missingOrUnknownPrincipalIsNotAuthorized() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/me")
                .header("X-Verified-User", "unknown"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void publicEndpointNeedsNoIdentityHeader() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }
}
```

Run:

```bash
mvn test
```

Expected result: all four tests pass. These tests prove that **Spring's** filter/provider/authorization components work together properly. They **do not prove** that the gateway verified the identity or prevented external header spoofing. That requires integration/security testing at the network boundary with a real gateway.

To test the separation of responsibilities, you can add a test verifying that a client sending `X-Verified-User: bob` directly to the backend in a staging environment **cannot connect** (for example, the connection is refused by the firewall). This test must run at the infrastructure layer; a `MockMvc` test cannot simulate a firewall or mTLS.

## 8. Mandatory Controls When Taking Pre-auth to Production

### 8.1. The Identity Source Must Be Trustworthy

The gateway design must satisfy all of the following simultaneously:

1. **Verify requests arriving from clients**: SSO session, OAuth/OIDC login, client certificate, or an organization-approved upstream method.
2. **Strip all client-sent identity headers** before setting new values. Never use a "keep if client already sent it" rule.
3. **Define the contract headers explicitly**, rejecting duplicate headers, empty values, invalid characters, and unverified identities. Prefer a stable, non-reusable user ID over a display name.
4. **Lock down backend ingress**: private network, firewall/security group, service mesh policy, mTLS, or equivalent peer verification. Ensure no alternate access path (other HTTP/HTTPS listeners, sidecars, debug ports, secondary ingresses, internal DNS) bypasses the gateway.
5. **Protect every hop** and preserve only gateway-generated headers. Trusting `X-Forwarded-*` or an unverified IP address is insufficient to authenticate a user.
6. **Restrict/audit header-setting privileges** across intermediate reverse proxies; establish consistent handling for retries, failovers, caching, and multi-proxy chains.
7. **Test fail-closed behavior** when the gateway or identity service fails: never turn an unverified request into a default user.

A stronger design uses a token assertion **signed** by the upstream system and requires the backend to verify the signature, audience, issuer, and expiration. In that case, the backend is verifying cryptographic proof rather than merely trusting a username header; select the appropriate Spring Security mechanism (typically OAuth2 Resource Server when using standard JWTs).

### 8.2. Identity and Permissions Must Have Separate Rules

- **Principal/subject:** choose a stable user key; clearly define the mapping from IdP username/email/subject to the internal user. Avoid auto-provisioning high-privilege accounts from upstream-supplied strings.
- **Authorities:** if sourced internally, keep them updated with the user store; if provided by the gateway, trust them only when the permission source is protected like the principal and has signing/sync/normalization rules.
- **Account status:** decide whether a user disabled/locked in the app should be blocked even if their SSO session is still active. The example in section 6 uses `UserDetailsService` as the local source.
- **Tenant:** do not infer tenant access from a standalone principal or `X-Tenant` header. Every access to sensitive data must verify the principal–tenant binding.
- **Object-level authorization:** `hasRole("ADMIN")` is a coarse-grained check; service/data-layer policies are still needed when users access resources belonging to others.

### 8.3. Session Lifecycle and Principal Changes

In **stateful** applications, the Spring Security session may retain a previously created Authentication. You must decide:

- When the gateway reports a new user within the same browser/session, does the application update the Authentication and invalidate the old session?
- When permissions are revoked, how long does the permission cache or session allow old permissions to persist?
- When the gateway logs out or SSO expires, are downstream sessions invalidated as well?
- When the backend has multiple nodes, do all nodes handle the Principal/authorities consistently?

In `AbstractPreAuthenticatedProcessingFilter`, `checkForPrincipalChanges` is a relevant tool, but it **does not replace** designing logout, session expiry, token revocation, and permission management. The example in section 6 uses stateless mode to avoid storing authentication from a prior request.

### 8.4. CSRF, CORS, Logging, and API Access Permissions

Pre-auth does not handle CSRF automatically. If the application uses a login cookie at the gateway and the browser sends cookies automatically, state-changing endpoints must still evaluate CSRF according to the threat model. The example only has GET endpoints, so disabling CSRF was unnecessary. CORS only controls cross-origin browser reads/requests by policy; CORS is not a mechanism that proves a header was verified by the gateway.

In logs/tracing, record a correlation ID and the necessary principal identifier, minimizing PII. Do not log cookies, raw SSO assertions, bearer tokens, or the entire SecurityContext. Avoid making authorization decisions based solely on logs or a descriptive role header.

## 9. What If the Application Uses Spring WebFlux?

The `RequestHeaderAuthenticationFilter` and `AbstractPreAuthenticatedProcessingFilter` classes above are **Servlet** APIs, built on `HttpServletRequest` and the Servlet `FilterChain`. Do not register them into a WebFlux `SecurityWebFilterChain`.

With WebFlux, the trust boundary model remains the same, but the APIs differ:

- `ServerAuthenticationConverter` can extract gateway-verified data from `ServerWebExchange` to create an authentication request.
- `AuthenticationWebFilter` and `ReactiveAuthenticationManager` process it in the reactive chain.
- `ReactiveSecurityContextHolder` places the Authentication into the Reactor Context for downstream components to read.
- For X.509 client certificates, Spring Security provides `ServerHttpSecurity.x509(...)` and `ReactivePreAuthenticatedAuthenticationManager` in the reactive X.509 guide.

This distinguishes the **model** from the **implementation API**. Do not reuse the Java Servlet snippet from section 6 verbatim in WebFlux. Nor should any username header in WebFlux be considered safe without a gateway trust boundary.

## 10. Symptoms, Causes, and Fixes

| Symptom | What to Check | Resolution |
| --- | --- | --- |
| User adds a header themselves and accesses another account | Backend exposed directly; gateway fails to strip/overwrite header | Lock down network paths to the backend and enforce identity header control at the gateway |
| Missing header triggers an early filter error | `RequestHeaderAuthenticationFilter` throws on missing header by default | Review `exceptionIfHeaderMissing` and configure appropriate fail-closed/response behavior |
| HTTP 401 even though gateway reports logged in | Header missing/mismatched name, principal not found, account locked, or wrong filter chain | Trace a single request through the gateway, matchers, filters, and user store |
| HTTP 403 even with an Authentication | Principal is valid but lacks permissions | Check authorities, `ROLE_` prefix, matchers, and resource policies |
| Switched SSO account but backend still sees old user | Session/`SecurityContext` retains previous Authentication; principal changes not checked | Check session strategy, `checkForPrincipalChanges`, invalidation, and logout |
| "ADMIN" header grants user admin privileges | Wrongly trusting a role header or unguarded mapping | Load authorities from a verified/controlled source; verify tenant and account |
| Pre-auth filter runs twice | Servlet Filter `@Bean` auto-registered in addition to being added to `SecurityFilterChain` | Configure only inside the security filter chain or intentionally disable servlet auto-registration |
| Application sees no user in `SecurityContextHolder` | Filter did not run, skipped by securityMatcher, or provider failed | Inspect active filter chain, filter ordering, `UserDetailsService`, and relevant logs |
| Unclear whether 401, 403, or redirect occurs | Authentication entry point/exception handling inherited from another config | Configure dedicated entry point and authorization handling as needed by the API |
| Running WebFlux with a Servlet filter | Mixing Servlet and reactive stacks | Use the corresponding reactive APIs |

A useful debugging sequence:

1. First confirm **who verified** the user upstream and what exact header is actually delivered to the backend.
2. Check whether the request hits the intended `SecurityFilterChain`; multiple chains have different matchers.
3. At the pre-auth filter, is the principal extracted? Is there an existing Authentication in the context causing the filter to skip?
4. Does the provider receive the expected `PreAuthenticatedAuthenticationToken` and load the right account/authorities?
5. At authorization, which rule rejects it? Never conclude 403 means "SSO is broken" when the real cause is missing permissions.

## 11. Self-Check Questions

1. **Why is an HTTP header containing a username not proof of authentication on its own?** Because a client can fabricate it unless a trusted proxy verifies the request, strips forged headers, and ensures the backend only accepts traffic from the proxy.
2. **Who verifies the password in a header-based pre-auth model?** The upstream system. `PreAuthenticatedAuthenticationProvider` processes an already-trusted principal, primarily loading the user/authorities and checking account status without re-authenticating the password.
3. **Is an identified user guaranteed access to `/api/admin`?** No. Authorization still checks authorities and policies; an authenticated user without `ROLE_ADMIN` receives 403.
4. **Why should `RequestHeaderAuthenticationFilter` not arbitrarily be both declared as a `@Bean` and added with `addFilterBefore`?** Because Spring Boot can auto-register a Servlet Filter bean outside `FilterChainProxy`, causing the filter to execute twice or in the wrong position.
5. **Are a missing header and a header with value `unknown` the same?** No. The former may not trigger an authentication attempt; the latter may pass through the provider and fail because the user is not found. An application can configure both to return 401.
6. **Does using `SessionCreationPolicy.STATELESS` automatically make the gateway trustworthy?** No. It only affects how Spring stores security state; the upstream trust boundary must still be protected.
7. **When using Spring WebFlux, do you keep `RequestHeaderAuthenticationFilter` as-is?** No. You need the reactive APIs of `SecurityWebFilterChain`/`AuthenticationWebFilter` and the Reactor Context.

## 12. Official Documentation

- Spring Security, Pre-Authentication Scenarios: https://docs.spring.io/spring-security/reference/servlet/authentication/preauth.html
- `AbstractPreAuthenticatedProcessingFilter` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/AbstractPreAuthenticatedProcessingFilter.html
- `RequestHeaderAuthenticationFilter` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/RequestHeaderAuthenticationFilter.html
- `PreAuthenticatedAuthenticationProvider` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/PreAuthenticatedAuthenticationProvider.html
- Spring Security Servlet Architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security Java Configuration: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security Reactive X.509: https://docs.spring.io/spring-security/reference/reactive/authentication/x509.html
