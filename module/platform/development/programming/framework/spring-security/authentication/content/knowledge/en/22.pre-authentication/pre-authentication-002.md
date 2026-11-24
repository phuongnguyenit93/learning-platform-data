# AbstractPreAuthenticatedProcessingFilter and PreAuthenticatedAuthenticationToken in Spring Security

## 1. What Is Pre-authentication?

**Pre-authentication** is a model in which **an external system has already verified the user's identity before the request enters the Spring Security application**. The application receives the verified identity and then uses Spring Security to establish the `Authentication`, look up account status, and assign permissions to the request.

Common identity sources:

- A trusted reverse proxy/API gateway/SSO agent that has logged in the user and passes the username or subject via internal request metadata.
- A Servlet container that has authenticated the user and exposes `HttpServletRequest.getUserPrincipal()`.
- An X.509 client certificate infrastructure; Spring Security also provides a dedicated X.509 mechanism so you do not need to write a custom filter unless you have special requirements.
- An enterprise identity system with an explicit trust contract defining who issues identities and where proof is verified.

**Two distinct layers of assurance:** the upstream system is responsible for proving "who this caller is"; the downstream application checks whether that identity exists, is still active, and what it is allowed to do. The name "pre-authentication" **does not mean** Spring Security automatically trusts any header/cookie/parameter from the Internet, nor does it mean every account is automatically granted permissions.

In Spring Security Servlet, the core pair of classes for this lesson is:

- `AbstractPreAuthenticatedProcessingFilter`: an abstract filter that reads identity and credentials from `HttpServletRequest` and turns them into an authentication request for `AuthenticationManager`.
- `PreAuthenticatedAuthenticationToken`: an `Authentication` type representing both a pre-authentication request and an authenticated result. The same class has two constructors representing two distinct states.

This lesson uses Java 17+, Spring Boot 3.x, and Spring Security 6.x on **Servlet/Spring MVC** (`jakarta.servlet.*` APIs). Do not place `AbstractPreAuthenticatedProcessingFilter` into a Spring WebFlux `SecurityWebFilterChain`; reactive has different classes and contracts.

## 2. Architecture and Trust Boundary

Typical flow:

```text
Browser / client
    │ 1. Log in or present proof
    ▼
Identity provider / gateway / servlet container
    │ 2. Verify identity, strip spoofed metadata
    │ 3. Forward only the verified identity over a trusted channel
    ▼
Spring Security Servlet FilterChain
    │
    ▼
AbstractPreAuthenticatedProcessingFilter (subclass)
    │ getPreAuthenticatedPrincipal(request)
    │ getPreAuthenticatedCredentials(request)
    ▼
PreAuthenticatedAuthenticationToken (2 args, not yet authenticated)
    ▼
AuthenticationManager
    ▼
PreAuthenticatedAuthenticationProvider
    │ uses AuthenticationUserDetailsService<UserDetails>
    │ looks up account status and permissions
    ▼
PreAuthenticatedAuthenticationToken (3 args, authenticated)
    ▼
SecurityContext → AuthorizationFilter → Controller
```

**The most critical boundary is between the gateway and the application.** If a client can send `X-Verified-User: admin` directly to the application without passing through the authentication gateway, an attacker can impersonate `admin`. Only accept this kind of header when all of the following safeguards are in place:

1. The application cannot be reached directly from untrusted networks; connections to the backend are protected by network policy and TLS/mTLS where needed.
2. The gateway always **strips or overwrites** client-supplied identity headers, creating the header only after successful authentication.
3. The identity is normalized with length/format constraints; the backend rejects conflicting multi-value headers or client-asserted strings.
4. Header-supplied permissions are used only if the gateway is genuinely authoritative for permissions; it is safer to look up permissions from an application-managed data store.
5. Mechanisms exist to handle token expiration, revocation, logout, tenant isolation, and user switches; do not treat a header's presence on a connection as perpetual proof.

Validating header syntax at the backend **does not** prove the header came from the gateway. For OAuth2/OIDC or JWT models where the backend must itself verify signature, audience, issuer, and expiry, use the corresponding resource server mechanism instead of turning an unverified JWT into a pre-auth principal.

## 3. How AbstractPreAuthenticatedProcessingFilter Works

The class is in package:

```java
org.springframework.security.web.authentication.preauth.AbstractPreAuthenticatedProcessingFilter
```

A subclass must override **two methods** that accept a Servlet request:

```java
@Override
protected Object getPreAuthenticatedPrincipal(HttpServletRequest request) {
    // Return the identity verified by the upstream source;
    // return null when no identity is present.
}

@Override
protected Object getPreAuthenticatedCredentials(HttpServletRequest request) {
    // Return processed proof or a NON-NULL dummy value
    // when the principal is valid and the external mechanism has no password here.
}
```

These are illustrative method signatures, not a standalone Java file. In Spring Boot 3.x, import the request from `jakarta.servlet.http.HttpServletRequest`, not the legacy `javax.servlet.*` package.

### 3.1. Conditions for Creating Authentication

- When the security context **does not yet hold** an `Authentication` object, the filter attempts to read the principal and credentials from the request.
- If the principal is `null`, the filter skips this authentication attempt by default and lets the chain continue. Use endpoint authorization rules to decide the outcome for requests without an identity.
- If a principal is present, the filter constructs `new PreAuthenticatedAuthenticationToken(principal, credentials)` and passes it to `AuthenticationManager.authenticate(...)`.
- The selected provider processes the token. Typically, the provider loads `UserDetails`, checks status, and returns an authenticated token with `GrantedAuthority` items.
- On success, the filter places the `Authentication` into `SecurityContext`, persists the context via `SecurityContextRepository`, and continues the chain. Long-term persistence behavior depends on the configured repository/session policy.
- On failure, the filter clears the authentication state just processed. By default `continueFilterChainOnUnsuccessfulAuthentication=true`, so an `AuthenticationException` may be swallowed for another mechanism to handle. Setting `false` rethrows the exception; **do not assume** that error is always translated into HTTP 401/403, because the filter's position in the chain also affects exception handling.

### 3.2. When the Request Already Has an Authentication

By default, the filter **does not re-authenticate** if the security context already holds an `Authentication`. This optimizes existing sessions, but can cause issues if the upstream pre-auth identity changes between requests.

Relevant properties:

| Setter Method | Meaning |
| --- | --- |
| `setAuthenticationManager(manager)` | Attaches a manager containing a provider that understands `PreAuthenticatedAuthenticationToken`. Essential configuration |
| `setCheckForPrincipalChanges(true)` | Compares the principal in the request against the current authentication, re-authenticating if changed |
| `setInvalidateSessionOnPrincipalChange(true)` | When principal-change checking is enabled, invalidates the old session on change; defaults to `true` |
| `setContinueFilterChainOnUnsuccessfulAuthentication(false)` | Immediately rethrows `AuthenticationException` when the manager fails, rather than continuing the chain |
| `setRequiresAuthenticationRequestMatcher(matcher)` | Restricts which requests the filter should process |
| `setAuthenticationDetailsSource(source)` | Attaches details (e.g., request metadata) to the token |
| `setSecurityContextRepository(repository)` | Selects where to persist the security context after successful authentication |

**Note:** `getPreAuthenticatedPrincipal` is not a function that authenticates the request itself. It only **extracts** identity from a channel already proven trustworthy by the architecture. If sessions are maintained, you must decide how to refresh permissions when an account is disabled, roles change, or the user logs out from SSO; enabling `checkForPrincipalChanges` only handles **principal changes**, not refreshing every permission or credential.

## 4. PreAuthenticatedAuthenticationToken: Distinguishing Request vs. Result

The class resides at:

```java
org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken
```

It extends `AbstractAuthenticationToken` and implements `Authentication`. It has **two constructors** with distinct security semantics:

| Construction | State | When Used |
| --- | --- | --- |
| `new PreAuthenticatedAuthenticationToken(principal, credentials)` | `isAuthenticated() == false` | Filter submits an authentication request to the manager |
| `new PreAuthenticatedAuthenticationToken(principal, credentials, authorities)` | `isAuthenticated() == true` | Provider returns the result after processing the request and verifying status/loading permissions |

Standalone example illustrating object semantics, requiring a project with Spring Security dependencies (placed in `TokenDemo.java`):

```java
import java.util.List;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;

public class TokenDemo {
    public static void main(String[] args) {
        var requestToken =
                new PreAuthenticatedAuthenticationToken("alice", "UPSTREAM_VERIFIED");

        var resultToken = new PreAuthenticatedAuthenticationToken(
                "alice",
                "UPSTREAM_VERIFIED",
                List.of(new SimpleGrantedAuthority("ROLE_READER")));

        System.out.println("request authenticated = " + requestToken.isAuthenticated());
        System.out.println("result authenticated = " + resultToken.isAuthenticated());
        System.out.println("result authority = "
                + resultToken.getAuthorities().iterator().next().getAuthority());
    }
}
```

When running `TokenDemo` with Spring Security on the classpath, the exact stdout is:

```text
request authenticated = false
result authenticated = true
result authority = ROLE_READER
```

**Never** let a controller or custom filter take an unverified username/header and use the three-argument constructor to self-promote `authenticated=true`. That constructor checks no password, signature, or trustworthiness. It merely represents the state asserted by the component constructing the object; only an appropriately designed and controlled provider or authentication component may create an authenticated result.

`getPrincipal()` returns the identity being processed, typically a username in the request and a `UserDetails` after the provider loads the user; `getCredentials()` may be a dummy value from the upstream mechanism and does not mean password. `getAuthorities()` holds the permissions **in the result token**, while `getDetails()` is source-dependent metadata. Do not confuse `details` with `authorities`, or use unverified metadata to self-grant roles.

## 5. PreAuthenticatedAuthenticationProvider and UserDetailsService

`PreAuthenticatedAuthenticationProvider` is an `AuthenticationProvider` that supports `PreAuthenticatedAuthenticationToken`. It assumes identity proof verification already completed at the upstream system, so it **does not check passwords like `DaoAuthenticationProvider`**.

The provider typically invokes:

```java
AuthenticationUserDetailsService<PreAuthenticatedAuthenticationToken>
```

To load information associated with the received `Authentication`. If the system already has a name-based `UserDetailsService`, `UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken>` adapts the token-receiving interface to the username-receiving interface. User details carry permissions from DB/LDAP or a trusted source, while allowing account status checks for locked, disabled, or expired accounts according to policy.

Example of wiring the provider (this is a **code snippet** inside a configuration method, not a standalone program):

```java
PreAuthenticatedAuthenticationProvider provider =
        new PreAuthenticatedAuthenticationProvider();

provider.setPreAuthenticatedUserDetailsService(
        new UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken>(
                userDetailsService));

AuthenticationManager manager = new ProviderManager(provider);
```

`ProviderManager` invokes providers in order, selects one supporting the token type, and handles the result or exception accordingly. In this example there is only one provider, so there is no username/password fallback. Plan carefully if an application simultaneously supports form login, HTTP Basic, sessions, and pre-auth: each filter needs a proper manager, clear filter ordering, and a policy preventing untrusted pre-auth data from entering another mechanism.

Another option is `PreAuthenticatedGrantedAuthoritiesUserDetailsService`: it extracts authorities from `token.getDetails()` when details implement `GrantedAuthoritiesContainer`. Use this only when upstream **is genuinely authorized to define roles** and the transport path is protected; never blindly trust roles received from a client-sent header. If permissions belong to the application, loading them via `UserDetailsService` is usually easier to govern and revoke.

## 6. Spring Boot 3 + Spring Security Servlet Example

This example illustrates the full chain: a trusted gateway authenticates the user and supplies the `X-Verified-User` header; the backend accepts requests only from the gateway. In **unit/integration tests** you can set the header manually to simulate the gateway, but in production **do not run this configuration on a backend port directly exposed to clients**.

Create a Spring Boot 3.x, Java 17+, Spring MVC/Servlet project (no WebFlux). In `build.gradle` of a project with the Spring Boot plugin and dependency management, include:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

The files live under `src/main/java/com/example/preauth/` with package `com.example.preauth`.

### 6.1. Subclass Reading Identity from a Trusted Header

**`GatewayPreAuthFilter.java`**

```java
package com.example.preauth;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.web.authentication.preauth.AbstractPreAuthenticatedProcessingFilter;

public final class GatewayPreAuthFilter extends AbstractPreAuthenticatedProcessingFilter {

    @Override
    protected Object getPreAuthenticatedPrincipal(HttpServletRequest request) {
        String user = request.getHeader("X-Verified-User");
        if (user == null || !user.matches("[A-Za-z0-9._-]{1,64}")) {
            return null;
        }
        return user;
    }

    @Override
    protected Object getPreAuthenticatedCredentials(HttpServletRequest request) {
        return "UPSTREAM_VERIFIED";
    }
}
```

Explanation: the filter only reads the header and checks username format. No API here proves the gateway actually authenticated the user. The string `UPSTREAM_VERIFIED` is a **non-empty dummy value**, not a password or cryptographic proof. The standard provider requires non-`null` credentials for a valid principal; it does not compare the dummy string. That is why security must be enforced at the ingress boundary.

Production applications must also forbid/normalize multi-value headers, enforce ingress controls, and bind canonical identities per the contract with the IdP. The regex is merely a minimal example and may not fit emails, long UUID subjects, or Unicode characters. Do not use values from `X-Forwarded-User` or custom headers until a clear trust model is established.

### 6.2. Configuring Provider, Filter Chain, and User

**`SecurityConfig.java`**

```java
package com.example.preauth;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.Http403ForbiddenEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.core.userdetails.UserDetailsByNameServiceWrapper;
import org.springframework.security.web.context.NullSecurityContextRepository;

@Configuration
public class SecurityConfig {

    @Bean
    UserDetailsService userDetailsService() {
        var alice = new User(
                "alice",
                "PREAUTH_ONLY_NO_LOCAL_LOGIN",
                List.of(new SimpleGrantedAuthority("ROLE_READER")));
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, UserDetailsService userDetailsService) throws Exception {

        var provider = new PreAuthenticatedAuthenticationProvider();
        provider.setPreAuthenticatedUserDetailsService(
                new UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken>(
                        userDetailsService));
        AuthenticationManager manager = new ProviderManager(provider);

        var filter = new GatewayPreAuthFilter();
        filter.setAuthenticationManager(manager);
        filter.setCheckForPrincipalChanges(true);
        filter.setContinueFilterChainOnUnsuccessfulAuthentication(true);
        filter.setSecurityContextRepository(new NullSecurityContextRepository());

        return http
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .securityContext(context -> context
                        .securityContextRepository(new NullSecurityContextRepository()))
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint(new Http403ForbiddenEntryPoint()))
                .authorizeHttpRequests(requests -> requests
                        .anyRequest().authenticated())
                .addFilterBefore(filter, UsernamePasswordAuthenticationFilter.class)
                .build();
    }
}
```

Explanation of each decision:

1. `UserDetailsService` in this example contains only `alice` with `ROLE_READER`; permissions are not granted from a header. The password in the demo data is an unused placeholder for pre-auth and **is not used for password login**. In real systems, query DB/LDAP and enforce account policies.
2. `PreAuthenticatedAuthenticationProvider` turns the request token into an authenticated result with authorities after loading `UserDetails`. No `PasswordEncoder` is needed because the user was already verified upstream.
3. `GatewayPreAuthFilter` is instantiated **inside** the filter chain configuration, avoiding becoming a `Filter` bean that Spring Boot would register a second time in the servlet container. If a filter bean is strictly required, disable automatic container registration with `FilterRegistrationBean.setEnabled(false)`.
4. `addFilterBefore(..., UsernamePasswordAuthenticationFilter.class)` places the filter into the Spring Security Servlet chain at a deterministic position; do not register it as a `@Component` servlet filter running outside the security chain.
5. `SessionCreationPolicy.STATELESS` + `NullSecurityContextRepository` keeps the demo from persisting authentication across HTTP sessions: **each request requires a fresh upstream identity**. Avoid assuming `setCheckForPrincipalChanges(true)` alone creates a session re-validation mechanism; depending on the application, session and permission policies must be designed explicitly.
6. When the header is missing/invalid or the account does not exist, no valid authentication is present and the protected endpoint denies access. `Http403ForbiddenEntryPoint` is chosen because this is a pre-auth-only demo; no login challenge is implemented. Error handling differs between 401 and 403 depending on protocol, UX, and entry point.
7. The demo does not enable `httpBasic()` or `formLogin()`. If another mechanism is enabled, analyze all request paths to avoid accidentally allowing bypass of upstream authentication rules.
8. The demo endpoint is read-only (GET), so the default CSRF configuration remains intact. Real applications with state-changing operations, cookies/sessions, or browser frontends must evaluate CSRF and proper token handling.

**`PreAuthApplication.java`**

```java
package com.example.preauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PreAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(PreAuthApplication.class, args);
    }
}
```

**`WhoAmIController.java`**

```java
package com.example.preauth;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {

    @GetMapping("/whoami")
    public String whoami(Principal principal) {
        return principal.getName();
    }
}
```

These Java files form a complete Spring Boot program when placed in a Boot 3.x project with the plugin, dependencies, and main class in the proper package. Header verification belongs to **the external gateway system**, so the example is only complete regarding Spring Security wiring; it is not a production SSO solution until the trust boundary is deployed.

### 6.3. Testing filter → provider → SecurityContext → controller

Use Spring Boot Test and MockMvc to test internal code without deploying a real reverse proxy. File `src/test/java/com/example/preauth/PreAuthIntegrationTest.java`:

```java
package com.example.preauth;

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
class PreAuthIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void acceptsKnownTrustedPrincipal() throws Exception {
        mvc.perform(get("/whoami").header("X-Verified-User", "alice"))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }

    @Test
    void rejectsRequestWithoutPrincipal() throws Exception {
        mvc.perform(get("/whoami"))
                .andExpect(status().isForbidden());
    }

    @Test
    void rejectsUnknownPrincipal() throws Exception {
        mvc.perform(get("/whoami").header("X-Verified-User", "mallory"))
                .andExpect(status().isForbidden());
    }

    @Test
    void rejectsMalformedPrincipal() throws Exception {
        mvc.perform(get("/whoami").header("X-Verified-User", "alice,bob"))
                .andExpect(status().isForbidden());
    }
}
```

Run in a Gradle project with the wrapper:

```bash
./gradlew test
```

On Windows use `.\gradlew.bat test`. These tests are expected to pass in a Boot 3.x project with the dependencies above; this is an **expectation for the illustrative code**, not a claim that tests were executed in this repository. The header in MockMvc is simulated **already-verified** upstream data; this test only verifies that the application consumes the data properly, **not** that a real gateway prevents spoofing. Add ingress/network-policy tests in an integration environment.

In an **isolated** test environment you can send:

```bash
curl -i http://localhost:8080/whoami
curl -i -H 'X-Verified-User: alice' http://localhost:8080/whoami
```

With the demo above, the first request is expected to return `403 Forbidden`; the second is expected to return `200 OK` with body `alice`. For the same reason, **do not** expose the demo port so clients can arbitrarily set headers themselves; production must place an authenticated gateway in front.

## 7. Who Checks What Exactly?

Responsibilities must be separated to avoid misinterpreting the word "authenticated":

| Component | Verifies proof such as password/token/certificate? | Handles identity and permissions? |
| --- | --- | --- |
| IdP / gateway / container | **Yes**, per upstream protocol and trust contract | May normalize subject and claims |
| `AbstractPreAuthenticatedProcessingFilter` | **No**; only extracts principal/credentials | Builds unauthenticated token and calls manager |
| `PreAuthenticatedAuthenticationProvider` | **Does not re-verify** upstream password | Uses `AuthenticationUserDetailsService` to load user, check policy status, build result token |
| `AuthorizationFilter` and access rules | Does not perform login | Checks endpoint access permissions |
| `SecurityContextHolder` | Does not create identity proof | Holds the authentication for the current execution flow |

Specifically, `PreAuthenticatedAuthenticationToken("alice", "UPSTREAM_VERIFIED")` is **not yet authenticated** because `isAuthenticated=false`. `PreAuthenticatedAuthenticationToken(userDetails, ..., authorities)` is **marked authenticated** when returned by the provider. Overall correctness depends on both: the upstream system actually verifying identity **and** the backend accepting input only from the trusted upstream.

Note on account status: creating `UserDetails` that always returns enabled/active even when an account is locked removes an application-layer safeguard. Production implementations must define the status source, sync latency, and session/permission revocation policy; the provider cannot know on its own that an account was locked in an external system unless the `UserDetails` source reflects it.

## 8. Two Common Identity-Provisioning Strategies

### 8.1. Servlet Container Already Sets the Principal

If the container actually enforces container-managed authentication, a subclass can read:

```java
@Override
protected Object getPreAuthenticatedPrincipal(HttpServletRequest request) {
    var principal = request.getUserPrincipal();
    return principal == null ? null : principal.getName();
}

@Override
protected Object getPreAuthenticatedCredentials(HttpServletRequest request) {
    return "CONTAINER_VERIFIED";
}
```

These are method snippets to place in a subclass, not a standalone runnable program. `J2eePreAuthenticatedProcessingFilter` is built in for this case. **Do not assume** `request.getUserPrincipal()` is always populated on every embedded servlet container; container authentication must be configured first. Application code or another filter attaching a `Principal` to the request without verification does not produce trustworthy proof.

### 8.2. Gateway Passes Username via HTTP Header

Once ingress is protected, Spring Security includes `RequestHeaderAuthenticationFilter`, which can replace writing a custom subclass when you only need to read a single header. According to documentation, it defaults to the `SM_USER` header and can be configured via `principalRequestHeader`. However, this class itself **does not prove the header is authentic**. Choosing the built-in class or a subclass only changes extraction, not the need for gateway verification.

**Choose a custom subclass when** you need to extract the principal from a verified request attribute, apply custom identity normalization, or enforce a strict request-filtering contract. **Choose a built-in class when** the protocol is already natively supported (X.509, container, trusted request header) to avoid reinventing the filter.

## 9. Handling Errors, Sessions, and Identity Changes

Key scenarios:

| Scenario | What to Interpret / Test |
| --- | --- |
| No principal present | Filter skips authentication; authorization/entry point decides the response |
| Header present but user does not exist | Provider/user details service does not grant authentication; do not auto-create user/roles from header |
| Account is disabled or locked | Must be rejected per `UserDetails` loading/checking policy |
| Upstream did not authenticate yet still set header | Impersonation vulnerability **outside** the filter's scope; must be fixed at ingress |
| Principal changes within session | Consider `setCheckForPrincipalChanges(true)` and invalidation; verify session/tenant isolation |
| User permissions change while principal stays the same | May require refreshing `UserDetails`, session, or token; principal-change checks alone are insufficient |
| `AuthenticationManager` throws exception | Depending on `continueFilterChainOnUnsuccessfulAuthentication`, other mechanisms, and filter position, the chain continues or the error propagates |
| Multiple auth mechanisms | Bind filter chains by URL with explicit ordering; avoid fallbacks that accidentally allow bypass |

For **stateless** setups like the example, context is not persisted across sessions; subsequent requests wishing to be authenticated must continue passing through upstream to receive an identity. For **stateful sessions**, choose an appropriate `SecurityContextRepository`, accounting for session fixation and synchronized logout. `SecurityContextHolderFilter` in modern Spring Security generally requires **explicit saving** of the context; the pre-auth filter provides `setSecurityContextRepository` to support this when needed. Manually calling `SecurityContextHolder.getContext().setAuthentication(...)` alone is usually insufficient to persist state across requests.

Distinguish ordinary credential failures from pre-auth: a pre-auth-only application may choose `Http403ForbiddenEntryPoint` to return 403 when a request arrives unauthenticated; a REST service using bearer tokens or an interactive UI may choose a different entry point. Do not claim a single HTTP status applies to every configuration.

## 10. Common Mistakes

1. **Trusting client-sent headers.** If the backend accepts `X-Verified-User: admin` directly, impersonation is possible even with syntactically valid Spring Security code. You must verify the gateway and block bypass paths.
2. **Calling the three-argument constructor directly in a filter.** Marking a token `authenticated=true` from an unverified identity can bypass the manager/provider. Use the two-argument constructor for requests.
3. **Returning `getPreAuthenticatedCredentials() == null` for a valid principal.** The standard provider may reject it. Use a non-null dummy when upstream passes no password to the backend.
4. **Confusing `UserDetailsService` with a login mechanism.** The service only loads users and permissions; proof was already verified upstream. `AuthenticationManager`/`PreAuthenticatedAuthenticationProvider` must be in the pipeline.
5. **Failing to restrict the source of authorities.** A self-asserted `ROLE_ADMIN` header is insufficient for the backend to grant roles; only use claims/roles from an explicitly trusted source.
6. **Registering the same filter twice.** When a filter is a Spring bean and also added to `HttpSecurity`, Spring Boot may auto-register it in the container; instantiate it inline or disable container registration.
7. **Not handling principal/session changes.** When SSO switches users while an old session still holds the old authentication, identity mix-ups can occur. Consider `checkForPrincipalChanges` and session invalidation.
8. **Swallowing all exceptions and permitting `permitAll()`.** By default the filter may let the chain continue after errors, so authorization must still protect resources; fallback behavior must be intentionally designed.
9. **Using the wrong web stack.** `AbstractPreAuthenticatedProcessingFilter` is a Servlet filter; WebFlux has a different reactive pipeline, so do not use this class in `SecurityWebFilterChain`.
10. **Skipping trust-boundary tests.** MockMvc setting a header only proves backend processing works. You must verify the gateway strips/overwrites headers and the network blocks direct backend access.

## 11. Self-Practice Exercises

1. Write a subclass based on `request.getUserPrincipal()` and explain how the container authenticates the user before the request reaches Spring Security. Compare pros/cons against a gateway header.
2. Use `UserDetailsService` to load permissions from a database and lock `alice`'s account. Write a test verifying the locked account cannot access `/whoami` even when the gateway sends a valid identity.
3. Send a `X-Verified-User: bob` request after authenticating `alice` in a stateful session. Toggle `checkForPrincipalChanges`, inspect the outcome and session invalidation behavior.
4. Write an ingress-boundary test: a spoofed header sent from the Internet must be stripped or rejected by the gateway; only requests arriving via the internal identity-enriched path are accepted by the backend. The goal is to prove **authentication provenance**, not just header format.
5. Compare the two- and three-argument constructors of `PreAuthenticatedAuthenticationToken`; explain why the `isAuthenticated` boolean is not cryptographic proof of identity.

## 12. Key Takeaways

- `AbstractPreAuthenticatedProcessingFilter` **extracts** pre-auth identity from a Servlet request, constructs a request token, and invokes `AuthenticationManager`.
- Two-argument `PreAuthenticatedAuthenticationToken` represents an **unauthenticated request**; three-argument represents an **authenticated result** with permissions.
- `PreAuthenticatedAuthenticationProvider` uses `AuthenticationUserDetailsService` to load users and authorities; this is not password authentication.
- Effectiveness depends on a **trusted upstream**, backend permission and account-status policies, and `SecurityContext` lifecycle management.
- When no trustworthy pre-authentication source exists, **do not** add a header and treat it as login. Use an appropriate Spring Security authentication mechanism instead.

**Official reference documentation:** Spring Security Pre-Authentication Scenarios (https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/preauth.html); `AbstractPreAuthenticatedProcessingFilter` Javadoc (https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/AbstractPreAuthenticatedProcessingFilter.html); `PreAuthenticatedAuthenticationToken` Javadoc (https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/authentication/preauth/PreAuthenticatedAuthenticationToken.html); Spring Security Servlet Architecture (https://docs.spring.io/spring-security/reference/servlet/architecture.html); Spring Security Authentication Persistence (https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html).