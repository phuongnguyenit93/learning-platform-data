# External Identity Changes, Existing Sessions, and Handling Lost Authentication

## 1. The Problem in the Pre-authentication Model

With **pre-authentication**, an external system has already verified the user before the request reaches the Java application: an SSO portal, reverse proxy, application server, X.509 certificate authentication infrastructure, etc. Spring Security receives an externally confirmed identity, builds an `Authentication`, and typically enriches it with `GrantedAuthority` values from the application's user data.

The question for this lesson is: **if the external identity changes from Alice to Bob, or the external system can no longer authenticate the user, how must an `HttpSession` currently holding Alice be handled?** This is the synchronization problem between **the external identity source**, **`SecurityContext` in the request**, and **session-persisted state**.

After this lesson, you should be able to distinguish:

1. The external identity on the **current request** (verified by a trusted system).
2. The `Authentication` currently in `SecurityContextHolder`, which may just have been restored from `SecurityContextRepository`.
3. The data and lifecycle of `HttpSession`: session ID, `SPRING_SECURITY_CONTEXT`, business data, CSRF tokens, and other attributes.
4. Scenarios of **principal change**, **lost principal**, **role/permission change while principal stays the same**, **IdP/gateway failure**, and **session expiration**; these are not a single uniform event.
5. How to test that an old identity does not continue being authorized for new requests.

**Primary scope:** Spring Security **Servlet** with `AbstractPreAuthenticatedProcessingFilter` / `RequestHeaderAuthenticationFilter` and HTTP sessions. Reactive/WebFlux uses `SecurityWebFilterChain`, `WebSession`, and `ReactiveSecurityContextHolder` with different APIs; do not apply Servlet code verbatim to WebFlux.

## 2. Normal Flow and Where Stale Identity Appears

A typical model:

```text
Browser with JSESSIONID cookie
    |
    v
Gateway / IdP that verified credentials
    |  strips client-sent identity headers
    |  attaches trusted identity per request, e.g., SM_USER=alice
    v
Spring Security FilterChain
    |  restores SecurityContext from session (if any)
    |  pre-auth filter reads external identity
    |  AuthenticationManager / PreAuthenticatedAuthenticationProvider
    |  UserDetailsService loads authorities per policy
    v
Controller and AuthorizationFilter
```

`RequestHeaderAuthenticationFilter` only **reads the header value**; it **does not verify signatures, passwords, or SSO sessions**. Therefore, use it only when infrastructure guarantees the application cannot be reached directly with forged headers. If a client can send `SM_USER: admin` to the application, header-based pre-authentication is insecure.

When the application uses sessions, `SecurityContextRepository` may persist Alice's `Authentication` after the first request. On the next request, Spring Security restores Alice before the pre-auth filter decides whether it needs to re-read the identity.

### Three States to Observe

| Source | Example | Meaning |
| --- | --- | --- |
| `P_ext` | `alice` / `bob` / absent | Principal externally confirmed for the current request |
| `P_ctx` | `Authentication(name=alice)` / empty | Identity Spring Security is about to use to authorize access |
| `S` | `JSESSIONID=S1`, holding Alice's `SecurityContext` | State persisted across requests; may be stale |

Safety rule: requests must be processed based on **an identity still valid under current policy**. The fact that a session still exists **does not prove** the IdP or gateway still authenticates the user.

## 3. Default Behavior of the Pre-auth Filter

`AbstractPreAuthenticatedProcessingFilter` has several key properties:

- When `SecurityContext` **does not yet have an `Authentication`**, the filter extracts principal/credentials from the request and passes them to `AuthenticationManager`. `PreAuthenticatedAuthenticationProvider` typically uses `AuthenticationUserDetailsService` to load the user and permissions; it trusts that original authentication already completed externally.
- If `SecurityContext` **already has an `Authentication`**, the filter **does not re-authenticate by default**. Consequently, an external principal change may be ignored when reusing a session.
- `setCheckForPrincipalChanges(true)` instructs the filter to compare the principal on the incoming request against the current identity; when a change is detected, the filter re-runs pre-authentication.
- `setInvalidateSessionOnPrincipalChange(true)` specifies invalidating the current session when a principal change is detected before authenticating the new identity; this property **defaults to true when change checking is enabled**. Setting it explicitly makes the policy easier to audit.
- `setContinueFilterChainOnUnsuccessfulAuthentication(true)` is the default: when `AuthenticationManager` fails, the chain can continue so another mechanism can handle it. This **does not mean the request is granted access**; the final decision still rests on authorization. If the system allows only pre-authentication, configure an explicit failure path and HTTP status response.
- With `RequestHeaderAuthenticationFilter`, `setExceptionIfHeaderMissing(true)` is the default and a **missing header** can raise `PreAuthenticatedCredentialsNotFoundException`. Do not treat that exception as an automatic command to log out every related session. If missing headers are allowed via `setExceptionIfHeaderMissing(false)`, a separate policy is needed to block stale authentication data.

**Limitation:** `checkForPrincipalChanges` primarily detects *principal* changes; it **does not automatically detect** that Alice's account was locked, Alice's permissions were revoked, or Alice's SSO session at the IdP was terminated if the request still carries the same string `alice`.

### Dangerous Default: Old Session Masks New Principal

```text
R1: Gateway -> SM_USER=alice, client has S1 or no session yet
    Spring Security creates Authentication(alice), stores in S1.

R2: Gateway -> SM_USER=bob, client still sends cookie S1
    checkForPrincipalChanges=false:
       context already has Alice -> filter may skip Bob -> request sees Alice
    checkForPrincipalChanges=true, invalidateSessionOnPrincipalChange=true:
       detects change -> invalidates S1 -> authenticates Bob -> saves new context if any

R3: Gateway can no longer verify anyone; client still sends Alice's S1
    NEVER assume Alice's session means an active valid identity.
    Missing external identity must be blocked and handled independently.
```

## 4. Analyzing Identity Change and Lost Authentication Scenarios

| Scenario | What Commonly Happens | Required Outcome |
| --- | --- | --- |
| Alice → Bob, same cookie | Session still holds Alice | Clear old context, invalidate or separate Alice's session, authenticate Bob and load Bob's permissions |
| Alice → no trusted principal | Browser still holds JSESSIONID | Block request; clear/revoke local context per policy, never fall back to old Alice |
| Alice remains Alice but role is revoked | Principal string unchanged | Reload/update permissions via TTL, version, or policy check; do not rely solely on `principalChanged` |
| Alice is locked at IdP | Gateway must stop asserting Alice | Block once signal is invalid; if immediate revocation is required, add back-channel/session revocation |
| Gateway/IdP unresponsive | No fresh authentication proof | Fail closed; 401/503 per protocol and error type, never use an untrusted identity cache |
| Local session expires, IdP still authenticates Alice | No local `SecurityContext` left | Re-authenticate pre-auth Alice from fresh request; may create a new local session |
| User logs out of application | Local session and context cleared | Next request re-logs in only if external system still authenticates; local logout does not equal SSO logout |
| User logs out of IdP | IdP session revoked | Gateway must stop emitting identity or send revocation event; invalidate local session per desired assurance level |

A display-name change like `Alice Nguyen` → `Alice N.` is not necessarily a user switch. Identify users by a **namespaced stable ID** (e.g., issuer + subject + tenant) rather than mutable/reusable display names or emails. `principalChanged(request, currentAuthentication)` can be overridden when the system's identity structure requires custom comparison; thoroughly test every branch of that comparison.

### Distinguishing 401, 403, and 503

- **401 Unauthorized:** the request lacks valid authentication and needs a re-authentication step. Suitable for APIs when a policy-required external identity signal is missing.
- **403 Forbidden:** recognized but lacking sufficient permissions; or when you intentionally configure `Http403ForbiddenEntryPoint` in a pre-auth model (that entry point returns 403). Do not assume every pre-auth failure automatically returns 403.
- **503 Service Unavailable:** the external system is failing and cannot render a fresh authentication decision; return only when the application knows for certain it is a dependency outage. Access must still be denied.
- **302 redirect:** may suit browser UIs behind an SSO gateway as part of login flows; APIs generally need explicit error codes.

**Never return 200 with a stale identity** just because the external system is down.

## 5. Example Servlet Configuration: Syncing Principal and Rejecting Lost Identity

The example below uses **Java 17+, Spring Boot 3.x, Spring Security 6.x**. It is a complete illustrative application when placed in a Boot Servlet project with the listed dependencies; use `MockMvc` to test, and **do not expose the demo HTTP port directly to the Internet**. Use the `SM_USER` header only when a trusted reverse proxy has genuinely authenticated the user, stripped client-sent spoofed headers, and blocked paths bypassing the proxy.

In `build.gradle` of a Spring Boot project configured with compatible plugin and BOM versions:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

Create `src/main/java/example/PreAuthDemoApplication.java`:

```java
package example;

import java.io.IOException;
import java.security.Principal;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsByNameServiceWrapper;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.logout.SecurityContextLogoutHandler;
import org.springframework.security.web.authentication.preauth.AbstractPreAuthenticatedProcessingFilter;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
public class PreAuthDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PreAuthDemoApplication.class, args);
    }

    @Bean
    UserDetailsService demoUsers() {
        // Illustrative data: pre-auth does NOT verify this password.
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password("{noop}unused")
                .roles("USER").build(),
            User.withUsername("bob")
                .password("{noop}unused")
                .roles("USER").build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, UserDetailsService users) throws Exception {

        var repository = new HttpSessionSecurityContextRepository();

        var lookup =
            new UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken>(
                users);
        var provider = new PreAuthenticatedAuthenticationProvider();
        provider.setPreAuthenticatedUserDetailsService(lookup);

        // Do not declare this filter as a separate @Bean:
        // avoid Spring Boot registering it twice outside the security chain.
        var preauth = new RequestHeaderAuthenticationFilter();
        preauth.setPrincipalRequestHeader("SM_USER");
        preauth.setAuthenticationManager(new ProviderManager(provider));
        preauth.setSecurityContextRepository(repository);
        preauth.setCheckForPrincipalChanges(true);
        preauth.setInvalidateSessionOnPrincipalChange(true);
        preauth.setExceptionIfHeaderMissing(true);

        return http
            .securityContext(context ->
                context.securityContextRepository(repository))
            .authorizeHttpRequests(auth ->
                auth.anyRequest().authenticated())
            .exceptionHandling(errors ->
                errors.authenticationEntryPoint(
                    new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
            // Block missing external signal even when session still holds Alice.
            .addFilterBefore(
                new RequireExternalIdentityFilter(repository),
                AbstractPreAuthenticatedProcessingFilter.class)
            .addFilterAt(
                preauth, AbstractPreAuthenticatedProcessingFilter.class)
            .build();
    }

    static final class RequireExternalIdentityFilter
            extends OncePerRequestFilter {

        private final HttpSessionSecurityContextRepository repository;

        RequireExternalIdentityFilter(
                HttpSessionSecurityContextRepository repository) {
            this.repository = repository;
        }

        @Override
        protected void doFilterInternal(
                HttpServletRequest request,
                HttpServletResponse response,
                FilterChain chain)
                throws ServletException, IOException {

            String externallyVerified = request.getHeader("SM_USER");
            if (externallyVerified == null
                    || externallyVerified.isBlank()) {

                var logout = new SecurityContextLogoutHandler();
                logout.setSecurityContextRepository(repository);
                logout.logout(request, response,
                    SecurityContextHolder.getContext().getAuthentication());

                response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
                return;
            }
            chain.doFilter(request, response);
        }
    }
}

@RestController
class IdentityProbeController {

    @GetMapping("/whoami")
    String whoami(Principal principal) {
        return principal.getName();
    }
}
```

**Key purpose of the code:**

1. `RequestHeaderAuthenticationFilter` reads the header placed on the request by **a trusted gateway**; it does not verify header origin itself. The illustrative `UserDetailsService` is only used to look up users and roles, not to check passwords in pre-auth.
2. `setCheckForPrincipalChanges(true)` compares the principal on every request. `setInvalidateSessionOnPrincipalChange(true)` prevents carrying Alice's session over to Bob. If you choose `false`, you must explicitly resolve the risk of Alice's session attributes remaining in Bob's session.
3. Use the **same** `HttpSessionSecurityContextRepository` for both the chain's security context and the pre-auth filter for consistent saving/reading. In Spring Security 6, do not assume a filter setting `SecurityContextHolder` is automatically persisted across requests; custom filters must save via an appropriate repository.
4. `RequireExternalIdentityFilter` runs before the pre-auth filter. When the header is missing/blank, it clears the security context, invalidates the local session, and terminates the request with 401. Consequently, a prior session is **never** accepted as substitute authentication proof.
5. `HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)` defines the response when an unauthenticated request reaches a protected resource. Cases where exceptions occur **inside the authentication filter itself** must be checked separately per failure-handler configuration; do not assume every filter exception is automatically converted to 401 by the entry point.
6. `RequireExternalIdentityFilter` is an **illustrative safeguard for a pre-auth-only route set**. Applications with health endpoints, callbacks, or multiple `SecurityFilterChain` beans must restrict its scope and filter ordering accordingly to avoid unintentionally blocking public endpoints.

**Security limitation of the sample code:** checking a header does not prove the header is genuinely trustworthy. Network isolation, proxy-to-app authentication, stripping client-sent headers, stable principal resolution, and policies preventing caching of expired auth headers must be enforced in the deployment architecture. Do not use this sample to expose a backend port where clients can send `SM_USER` arbitrarily.

## 6. Testing Identity Switches, Session Retention, and Lost External Signal

Add `src/test/java/example/PreAuthFlowTests.java`; `@AutoConfigureMockMvc` activates the security filter chain in the test environment. Tests pass headers directly to simulate the gateway **post-authentication**, not to prove the gateway resists spoofing.

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PreAuthFlowTests {

    @Autowired
    MockMvc mvc;

    @Test
    void principalChangeInvalidatesOldSessionAndUsesBob() throws Exception {
        MvcResult aliceResult = mvc.perform(
                get("/whoami").header("SM_USER", "alice"))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"))
            .andReturn();

        MockHttpSession oldSession =
            (MockHttpSession) aliceResult.getRequest().getSession(false);
        assertNotNull(oldSession);

        MvcResult bobResult = mvc.perform(
                get("/whoami")
                    .session(oldSession)
                    .header("SM_USER", "bob"))
            .andExpect(status().isOk())
            .andExpect(content().string("bob"))
            .andReturn();

        assertTrue(oldSession.isInvalid());

        MockHttpSession bobSession =
            (MockHttpSession) bobResult.getRequest().getSession(false);
        assertNotNull(bobSession);
        assertNotSame(oldSession, bobSession);
    }

    @Test
    void missingExternalIdentityRejectsExistingLocalSession()
            throws Exception {
        MvcResult aliceResult = mvc.perform(
                get("/whoami").header("SM_USER", "alice"))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"))
            .andReturn();

        MockHttpSession oldSession =
            (MockHttpSession) aliceResult.getRequest().getSession(false);
        assertNotNull(oldSession);

        mvc.perform(get("/whoami").session(oldSession))
            .andExpect(status().isUnauthorized());

        assertTrue(oldSession.isInvalid());

        mvc.perform(get("/whoami"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void independentRequestsDoNotSharePrincipals() throws Exception {
        mvc.perform(get("/whoami").header("SM_USER", "alice"))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));

        mvc.perform(get("/whoami").header("SM_USER", "bob"))
            .andExpect(status().isOk())
            .andExpect(content().string("bob"));
    }
}
```

Run tests in a Spring Boot module containing the dependencies:

```bash
./gradlew test --tests "example.PreAuthFlowTests"
```

Windows PowerShell: `.\gradlew.bat test --tests "example.PreAuthFlowTests"`.

When all three tests pass, the confirmed expectations are: Bob cannot reuse Alice's `Authentication` on a principal change, Alice's session is invalidated, missing external identity returns 401 even if the old cookie still exists, and two independent requests do not share identities. `MockMvc` does not print these values to stdout; they are verified by JUnit assertions. This is an integration test against mock servlets, not a test of real gateway/SSO infrastructure.

### Additional Tests Needed for Production Deployment

| Test | Input | Core Assertion |
| --- | --- | --- |
| Principal change with same cookie | S1/Alice → S1/Bob | Bob sees Bob; S1 is invalidated; Alice's private data never appears |
| No principal change | S1/Alice → S1/Alice | Remains Alice; session not needlessly destroyed if policy allows retention |
| Missing/blank header | S1/Alice → header absent/blank | 401 (or designed fail-closed outcome); no access under Alice |
| Principal absent from user directory | Non-existent user header | Authentication fails, prior account not kept; verify failure-path status |
| Permissions change while principal unchanged | Alice USER → Alice's ADMIN role revoked | ADMIN access denied within committed revocation window |
| Concurrent switch Alice → Bob | Two near-simultaneous requests, same cookie | No data leak; race condition and version/session handled per policy |
| SSO logout | IdP revokes SSO session | New requests lose old authentication; if immediate required, handle back-channel event |
| Gateway/IdP outage | No fresh authentication proof | 401 or 503, never fall back to old principal |
| Attacker injects header | Client sends `SM_USER: admin` | Proxy strips/overwrites header, or backend rejects direct access |
| Session timeout | S1 expires, gateway still valid | Can re-authenticate via valid request; lost session attributes not restored |

An **already-authorized, in-flight** request when permissions are revoked may still finish depending on consistency policy. Changes at the IdP generally affect only subsequent requests unless the system can abort running transactions. Never claim per-request principal checking provides instant revocation for work already executing.

## 7. Session and Permission Consistency Policies

### 7.1. Choosing Security Context Storage

**Local session model:** `HttpSessionSecurityContextRepository` persists `SecurityContext` across requests. Pros: fewer repeated lookups; cons: must handle principal switches, stale permissions, IdP logouts, and distributed sessions. On user switches, invalidating the session prevents attributes such as shopping carts, personal filters, CSRF tokens, or old form data from leaking to Bob.

**Per-request re-authentication model:** do not rely on sessions to retain principals; applicable when the gateway supplies trustworthy proof on *every* request and policy allows it. `SessionCreationPolicy.STATELESS` can replace context persistence in some apps, yet merely switching to STATELESS **does not** authenticate headers on its own nor replace checking identity provenance. Systems using bearer tokens/JWTs follow a different authentication mechanism than pre-auth headers.

### 7.2. Permissions Change While Name Stays the Same

`principalChanged` detects Alice → Bob, and **does not automatically ensure** role updates when Alice stays Alice. If Alice loses `ROLE_ADMIN` in the directory while the local `Authentication` still holds the old authority, stale privileges persist.

Common strategies: re-validate permissions per request where required; check an identity/permission version at the gateway or repository; use short cache TTLs; revoke or invalidate sessions on update events; and explicitly test **maximum time to permission change propagation**. Choose based on load, latency, security requirements, and IdP capabilities; never call TTL instant revocation.

### 7.3. Local Logout vs. Upstream Logout

`SecurityContextLogoutHandler` typically clears local authentication and can invalidate `HttpSession`. It **does not automatically terminate** the IdP session. If the gateway still authenticates Alice on the next request, pre-auth may immediately log Alice back in; true SSO logout requires the IdP/gateway's protocol (e.g., front-channel/back-channel logout per product/protocol) and handling external redirects/cookies.

Likewise, when the IdP signals logout while the app still holds a local session, tie revocation events to issued sessions, or ensure new requests always demand a still-valid signal. Across multiple nodes, invalidating a session on one node alone may not purge corresponding sessions on other nodes.

### 7.4. Multi-Attribute Principals

Comparing usernames alone is insufficient with multi-tenancy, multiple issuers, renamed accounts, or recycled usernames. Design an immutable, namespaced ID; keep `Authentication.getName()`, user-mapping data, and `principalChanged` logic consistent. Never silently treat two principals sharing an email across different issuers/tenants as the same user.

## 8. Common Implementation Mistakes

1. **Trusting headers from the Internet:** users set `SM_USER: admin` and escalate privileges. Fix: backend accepts connections only via trusted gateway; gateway strips all client-supplied identity values and writes verified values; protect internal communication.
2. **Leaving principal-change checks disabled:** Alice's session exists, gateway switches to Bob, yet app keeps using Alice. Fix: enable `setCheckForPrincipalChanges(true)` or use a re-validation model with equivalent guarantees.
3. **Keeping a session across user switches without auditing private data:** Bob may see Alice's state. Fix: prefer invalidating sessions on switch; if retention is mandatory, copy only vetted attributes and test ownership of every value.
4. **Equating a missing header with safe logout:** without a guard, the session may still retain old authentication; filter exceptions alone do not guarantee durable cleanup. Fix: enforce explicit policy for missing/blank/invalid external identity before protected resources are accessed.
5. **Assuming `continueFilterChainOnUnsuccessfulAuthentication(false)` also handles `principal=null`:** that setting concerns errors from `AuthenticationManager` and does not replace a missing-identity policy. Fix: handle missing principals in a dedicated branch.
6. **Conflating principal change with permission change:** when Alice stays Alice with changed roles, name comparison still reports "unchanged." Fix: refresh authorities via appropriate revocation/version/TTL mechanisms.
7. **Calling `SecurityContextHolder.clearContext()` thinking all requests are logged out:** that only affects the current thread's context; it does not automatically erase context saved in the session/repository. Fix: use proper logout/repository flows and invalidate sessions when needed.
8. **Reading sessions across multi-node requests without policy sync:** one node revoked, another still holds auth. Fix: consistent session store/revocation and multi-node test scenarios.
9. **Registering the pre-auth filter twice:** once as Boot's Servlet `Filter` bean, once inside `SecurityFilterChain`. Fix: instantiate the filter inline in chain config or disable servlet auto-registration when the filter is a bean meant only for the security chain.
10. **Mixing up status codes:** missing authentication returning 200, or upstream outage still serving admin privileges. Fix: define 401/403/503 clearly, ensure authorization rejects untrusted states.
11. **Failing to test with the same cookie:** testing Alice with her own cookie and Bob with his own cookie misses principal-change bugs. Fix: test user switch on S1 itself, while verifying business data in the session does not bleed across.
12. **Assuming IP address or User-Agent proves the same user:** these are not authentication identifiers; NAT, proxies, and devices change. Use an IdP-verified ID over a trusted channel.

## 9. Design and Verification Checklist

- [ ] Identified the sole system responsible for **primary authentication** and how the backend verifies the trusted path.
- [ ] Stable principal identifier defined, with issuer/tenant where needed, and consistent comparison rules.
- [ ] Clear knowledge of which `SecurityContextRepository` stores authentication and when sessions are created/destroyed.
- [ ] When Alice → Bob on the same cookie, Alice's context and private session data are no longer used for Bob.
- [ ] When external identity is **missing, blank, expired, or untrusted**, requests are denied even if a local session exists.
- [ ] Distinguished principal changes from role updates, account locks, logout, and upstream outages.
- [ ] Explicit revocation-latency requirements defined: next request, few-minute TTL, back-channel, or immediate revocation.
- [ ] Tested 401/403/503, failure handlers, concurrent requests, session timeouts, and multi-node behavior matching production architecture.
- [ ] Never expose tokens, session cookies, credentials, or full `SecurityContext` in logs; use request/correlation IDs and properly sanitized user IDs.

**Technical conclusion:** in pre-authentication, local `Authentication` is a snapshot of state accepted at one moment, not perpetual proof that the IdP still authenticates the same user. Checking principal changes and handling sessions are essential; **lost external identity and permission changes require dedicated policies**.

## 10. Official Documentation

- Spring Security — Pre-Authentication Scenarios: https://docs.spring.io/spring-security/reference/servlet/authentication/preauth.html
- Spring Security — `AbstractPreAuthenticatedProcessingFilter` API, especially `setCheckForPrincipalChanges` and `setInvalidateSessionOnPrincipalChange`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/AbstractPreAuthenticatedProcessingFilter.html
- Spring Security — `RequestHeaderAuthenticationFilter` API and `exceptionIfHeaderMissing`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/RequestHeaderAuthenticationFilter.html
- Spring Security — `PreAuthenticatedAuthenticationProvider` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/PreAuthenticatedAuthenticationProvider.html
- Spring Security — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — Handling Logouts: https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html
- Spring Security — `SecurityContextLogoutHandler` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/logout/SecurityContextLogoutHandler.html
