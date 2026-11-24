# Distinguishing User Authentication, Service Authentication, and Multi-Factor Authentication

> **Scope:** Spring Security Servlet/Spring MVC; Java 17+, Spring Boot 3.x, and Spring Security 6.x for runnable examples. This lesson compares three concepts—**user authentication**, **service/machine-to-machine authentication (M2M)**, and **multi-factor authentication (MFA)**—explaining credentials, principals, tokens, independent factors, step-up authentication, and integration options in Spring Security. The section on **Spring Security 7**'s new MFA APIs is marked separately to avoid version misuse.

## 1. Three Concepts, Two Subject Types, and One Assurance Level

Suppose an application has three scenarios:

- Alice opens her profile page and logs in with a password, passkey, or enterprise sign-in system.
- A batch worker with no human user directly calls the `/service/jobs` API on a schedule.
- Alice wants to change her account recovery method, and the system requires an extra authenticator check before allowing it.

The first case is **user authentication**; the second is **service authentication**; the third is **multi-factor authentication (MFA)**. MFA is **not a third account type**. It is a strategy for verifying an identity using multiple independent pieces of evidence, usually applied to **the logged-in user themselves**.

| Criterion | User authentication | Service authentication | MFA/step-up |
| --- | --- | --- | --- |
| Subject | Human user/account | Application, worker, backend, workload | Usually the current user |
| Question | "Who is logging in?" | "Which workload is calling?" | "Has this identity been proved strongly and recently enough?" |
| Credential | Password, passkey, OIDC login | Client secret, private key, certificate, workload credential | Additional factor such as TOTP, WebAuthn, hardware key |
| Common flow | Form login, OIDC Authorization Code + PKCE | OAuth2 `client_credentials`, mTLS, workload identity | MFA at login or challenge on sensitive actions |
| Post-auth permissions | ROLE_USER, ROLE_ADMIN, user permissions | Service scopes, workload roles | Adds **assurance/factor** metadata, does not replace business permissions |
| Interactive human? | Usually yes at login time | Usually no | Usually yes during verification challenge |
| Typical risks | Password reuse, session theft, account takeover | Secret exposure, token replay, overly broad service privileges | OTP phishing, factor bypass, weak recovery, replay |

**Authentication** verifies the subject. **Authorization** decides whether the subject has permission for an action and resource. **MFA** raises the confidence level of how the subject was verified. A logged-in user, even after MFA, must still pass role, owner, tenant, and domain checks.

## 2. Three Flows at the Architectural Level

### 2.1. Human user logging in

~~~text
Alice -> Browser/App
   |
   | Password, passkey, OIDC...
   v
Spring Security authentication filter or Identity Provider
   |
   +--> Check credentials and account status
   |
   v
User Authentication / user session / user access token
   |
   +--> userId, roles, tenant, permission claims
   |
   v
AuthorizationFilter / method security
   |
   +--> GET /user/profile: requires authenticated
   +--> GET /user/admin: requires ROLE_ADMIN
   +--> sensitive action: may need recent MFA
~~~

If the app uses form login, after success the Authentication can be stored in session. If using OIDC, the Identity Provider authenticates the user and the app receives identity info via the protocol; for APIs, access tokens must be verified by the Resource Server.

### 2.2. Service calling Service

~~~text
Report Worker
   |
   | client credentials (client secret/private_key_jwt/mTLS)
   v
Authorization Server
   |
   +--> Verify client/workload
   +--> Issue access_token with permitted scopes
   |
   v
Report Worker -> Authorization: Bearer <access_token>
   |
   v
Resource Server (Spring Security)
   |
   +--> Validate JWT or introspect opaque token
   +--> Check issuer, audience, expiry, scopes
   |
   v
Authentication of SERVICE, e.g. service:report-worker
   |
   +--> SCOPE_jobs.read
   |
   v
Authorization -> ALLOW / DENY
~~~

**Client credentials tokens represent the client/workload, not an end user by default.** If a worker performs tasks on Alice's behalf, that is a separate delegation problem that may require on-behalf-of or token exchange supported by the Authorization Server.

### 2.3. User needing MFA

~~~text
Alice logs in with password
   |
   v
Initial-level User Authentication
   |
   +--> GET /user/profile: may ALLOW
   |
   +--> POST /user/change-recovery
             |
             v
         Policy requires step-up
             |
             +--> Independent factor challenge (TOTP/WebAuthn)
             +--> Verifier checks factor, nonce, replay, binding
             +--> Record newly verified factor/assurance
             |
             v
         Check role + resource + freshness
             |
             v
          ALLOW / DENY
~~~

**MFA is not a client-set boolean.** Headers like `X-MFA-Verified: true`, JSON `{"mfa":true}`, or client-sent roles never prove a second factor. Only a trusted verifier after completing a challenge may produce valid factor evidence.

## 3. User Authentication: Common Mechanisms

### 3.1. Form login and HTTP Basic

For username/password, Spring Security Servlet typically coordinates:

~~~text
Form/Basic Authentication Filter
   |
   +--> UsernamePasswordAuthenticationToken (unauthenticated)
   |
   v
AuthenticationManager / ProviderManager
   |
   v
DaoAuthenticationProvider
   |
   +--> UserDetailsService.loadUserByUsername(username)
   +--> PasswordEncoder.matches(rawPassword, storedHash)
   +--> Check locked/disabled/expired
   |
   v
Authenticated Authentication
   |
   v
SecurityContextHolder
   |
   v
AuthorizationFilter / @PreAuthorize
~~~

`UserDetailsService` **looks up the account**; it does not accept a raw password to match. `PasswordEncoder` checks credentials against the hash; the provider checks status and creates a trusted Authentication. Application authorization runs after authentication.

**Form login** fits browser/session web apps, yet requires managing CSRF, cookies, session fixation, logout, and timeouts. **HTTP Basic** suits learning or controlled APIs, though every request can carry Base64 username/password. **Base64 does not encrypt secrets**; use TLS and never put production credentials into source/logs.

### 3.2. OIDC and enterprise sign-in

In OpenID Connect, the application is typically an OIDC client and the Identity Provider authenticates the user. Authorization Code + PKCE is a common flow, involving redirects, state, nonce, and protocol-compliant token validation.

**Distinguish ID tokens from access tokens:**

| Token | Purpose |
| --- | --- |
| **ID token** | Informs the OIDC client about the user's authentication at the IdP; verify issuer, audience, nonce, and claims per flow |
| **Access token** | Grants access to APIs/Resource Servers; must have proper audience/scope and API-side validation |
| **Session cookie** | Browser/app session reference, not synonymous with a JWT |

**Do not send ID tokens to every API instead of access tokens.** With a Resource Server, the principal may be `Jwt`; with form login/DaoAuthenticationProvider, the principal is usually `UserDetails`. Never cast every Authentication principal to the same Java class.

### 3.3. Being logged in is not enough permission for data

Alice has `ROLE_USER`, yet `/orders/42` may belong to someone else. `authenticated()` only checks authentication status per framework policy, not record ownership. Enforce authorization by `accountId`, `tenantId`, action, and resource. Usernames/emails can change, so apps usually need stable IDs.

### 3.4. User session lifecycle

- Issued sessions may retain old Authentication/authorities after a role is revoked.
- Issued JWT access tokens may retain pre-change role claims until expiry/revocation or revalidation.
- Changing a password or locking an account in the database does not automatically invalidate every old session/token.
- Sensitive features need fresh re-authentication or time-bounded step-up, not just an existing session.

## 4. Service Authentication: No End User Logged In

### 4.1. Service principal and permission scope

A worker should have its own **service identity**, such as `service:report-worker`, with scope `jobs.read`. The server's job is to verify service identity from trusted credentials/tokens and then decide permissions.

| Info | User principal | Service principal |
| --- | --- | --- |
| Identifier | userId, user subject, tenant | client_id, service account, workload ID |
| Permissions | Roles, permissions, ownership | Scopes, service roles, resource permissions |
| Audit | Which user performed the action? | Which workload called, which environment, on whose behalf if delegated? |
| Credential | Password/passkey/OIDC | Client secret/private key/certificate/workload assertion |
| Revocation | Session/logout/password reset | Rotate credentials, revoke client/tokens, workload policy |

**A service does not become an admin merely because it runs on the backend.** Scope `SCOPE_jobs.read` does not equal `ROLE_ADMIN`, and a service's permission does not grant blanket access to every user's personal data.

### 4.2. OAuth2 client_credentials

Standard steps:

1. Service is registered as an OAuth2 client at the Authorization Server.
2. Service authenticates at the token endpoint using a permitted method, e.g. `client_secret_basic`, `private_key_jwt`, or mTLS.
3. Authorization Server issues an access token **to the client itself**, with approved scopes.
4. Service sends the Bearer token to the API.
5. Resource Server validates the token; authorization evaluates scopes and resources.

**Do not confuse client authentication at the token endpoint with Resource Server authentication when the token is used.** They are two separate checks at two boundaries. `client_id` and token `sub` must be interpreted per the issuer's contract; claim names do not turn a client into a human account.

### 4.3. Choosing workload credentials

- **Client secret:** easy to deploy yet needs a secret manager, rotation, and restricted distribution. Never embed in frontend/mobile apps.
- **private_key_jwt:** uses a private key to sign assertions; needs key rotation, audience/issuer/time binding, and protocol replay prevention.
- **mTLS:** client proves possession of certificate key at the TLS layer; needs CA, trust store, expiry, and revocation/binding management.
- **Cloud workload identity/federation:** issues short-lived credentials based on workload identity, reducing long-lived secret distribution.
- **API key:** a secret usually acting like a bearer credential; not automatically an OAuth2 access token and lacks built-in scopes/expiry/issuer validation.

In practice, mTLS/`private_key_jwt` can be used to obtain an OAuth2 access token, which is then used to call APIs. A workload identity never bypasses authorization at the target API.

### 4.4. JWT and opaque tokens

Spring Security OAuth2 Resource Server has two common options:

- **JWT:** `JwtDecoder` verifies signature and claims; configure issuer, audience, expiry, algorithm/kid/key rotation per system. Never trust payloads merely because Base64URL is readable.
- **Opaque token:** `OpaqueTokenIntrospector` verifies tokens via introspection or a provided mechanism; typically receives attributes/scopes from the Authorization Server.

Scope `jobs.read` is normally mapped to `SCOPE_jobs.read` in Resource Server `GrantedAuthorities`. When a token is valid yet lacks the scope, requests usually receive **403**, unlike invalid tokens which usually receive **401**.

### 4.5. Services acting on behalf of users are a special case

If Alice clicks a generate-report button and the backend calls another service, using a generic `client_credentials` token loses context on **which user requested it**, consent, and data scope. You need delegation/on-behalf-of/token-exchange policies or trusted user-context propagation and verification.

**Never mutate the `sub` claim in a JWT yourself, and never treat a `userId` in a request body as a new user authentication.** Audit both the actor (service) and subject (user) whenever delegation is allowed.

## 5. MFA: Multiple Independent Factors

MFA requires evidence from **at least two distinct factor categories**. The number of prompts/fields is not sufficient criteria.

| Category | Examples | What to understand |
| --- | --- | --- |
| **Something you know** | Password, PIN | Password + PIN still belong to the same knowledge category |
| **Something you have** | TOTP authenticator, security key, possessed certificate/device | Manual OTPs can be phished/relayed |
| **Something you are** | Biometrics used in trusted authentication | A face photo uploaded by a client is not an MFA factor |

Location/IP, unrecognized devices, or risk scores can inform authentication decisions, yet **do not substitute for an independent factor**. A cryptographic method can have multi-factor properties when combining device binding and proper user verification; the system must verify actual assurance.

### 5.1. Password + TOTP

A basic flow:

1. User logs in with password.
2. User has securely enrolled a TOTP authenticator with a protected seed.
3. Server requests a TOTP code at login or when performing a sensitive action.
4. Verifier checks time window, replay, rate limits, user/session binding, and enrollment state.
5. If valid, a trusted component records MFA assurance for the session/token within a defined lifetime.

**TOTP is not phishing-resistant.** Attackers can trick users into entering codes and relay them while valid. Never log TOTP codes/seeds and reject reused codes when policy requires replay prevention.

### 5.2. Passkeys and WebAuthn

WebAuthn/FIDO2 relies on public-key cryptography with credentials bound to the relying party/domain and challenge, offering stronger phishing resistance than manually typed OTPs. Passkeys can combine possession with local **user verification (UV)** via PIN/biometric.

**Do not treat every WebAuthn assertion as automatically MFA.** Assurance depends on authenticator type, UV flag, and policy. When an endpoint mandates user verification, the verifier must confirm UV actually occurred per protocol and trust requirements.

### 5.3. SMS/email codes, push, and recovery

SMS carries SIM-swap risks, email accounts can be compromised, and push prompts face fatigue attacks. While still used in certain contexts, they should not be equated with phishing-resistant authentication.

**Recovery is a sensitive authentication path.** Changing authenticators, adding devices, retrieving recovery codes, or resetting factors requires re-authentication, rate limits, auditing, notifications, and controls against account takeover. If recovery is too easy, attackers simply go through recovery to bypass MFA.

### 5.4. MFA at login vs. step-up authentication

- **MFA at login:** user completes multiple factors before receiving a session/token with sufficient assurance.
- **Action-based step-up:** user already has basic login, yet an action like changing passwords, transferring funds, adding admins, or changing recovery requires an additional factor *close to the time of the operation*.

Never treat an "MFA completed once" claim as permanent. Design **authentication time/freshness**, challenge binding, and expiry; overly old sessions may require re-authentication.

### 5.5. OIDC amr/acr

An Identity Provider may convey authentication methods/references via `amr` or authentication context via `acr`. **Exact values are not universal defaults**; values like `pwd`, `otp`, `mfa` depend on the IdP and contract.

Only trust factor/assurance claims **after the token or session is verified from a trusted source**, matching issuer/audience/time and freshness policy. For Resource Servers, assurance info must live in the **access token/introspection** or be queried via a trusted channel; never trust a client-supplied ID token misused as an API token.

## 6. How Does Spring Security Integrate These Different Flows?

| Feature/API | Role |
| --- | --- |
| `formLogin`, `httpBasic` | Username/password authentication with matching user store/provider |
| `UserDetailsService` | Looks up account, password hash, authorities, and status |
| `DaoAuthenticationProvider` | Coordinates lookup and `PasswordEncoder` |
| `oauth2Login` | Application acts as OAuth2/OIDC client for human login |
| `oauth2Client` | Application actively obtains access tokens to call APIs, including client credentials |
| `oauth2ResourceServer` | API receives Bearer tokens and verifies JWTs/opaque tokens |
| `SecurityFilterChain` | Selects filters and authorization rules for each request group |
| `@EnableMethodSecurity` | Enables annotation-based authorization on services/methods |
| MFA mechanism/IdP step-up | Verifies independent factors and updates user assurance level |

An application can be both an OAuth2 Client and a Resource Server simultaneously, yet **never mix issuing tokens, using tokens, and verifying tokens**. `oauth2ResourceServer` does not issue access tokens itself; a Resource Server does not call `UserDetailsService` itself to verify a JWT.

### 6.1. MFA in Spring Security 6

With Boot 3/Security 6, systems commonly rely on an IdP supporting MFA and check verified assurance, or use a dedicated flow with challenges/verifiers and protected security contexts. Example snippet only illustrating policy once **Jwt is already verified**:

~~~java
// Snippet — not a complete application; depends on IdP contract.
boolean hasPasswordAndOtp(Jwt verifiedJwt) {
    List<String> methods = verifiedJwt.getClaimAsStringList("amr");
    return methods != null
        && methods.contains("pwd")
        && methods.contains("otp");
}
~~~

This reads claims of a **specific IdP**; it is not TOTP verification itself. You must check signed tokens, issuer, audience, `auth_time`, expiry, resource context, and real policy. Never read `amr` claims from unverified request JSON.

### 6.2. Built-in MFA in Spring Security 7

Spring Security 7 introduces `FactorGrantedAuthority` and multi-factor rules alongside one-time-token/step-up mechanisms. **The snippet below is for Spring Security 7 only**; do not mix it into the Boot 3/Security 6 project below:

~~~java
// Spring Security 7 only — snippet, needs supporting imports/beans.
@EnableMultiFactorAuthentication(authorities = {
    FactorGrantedAuthority.PASSWORD_AUTHORITY,
    FactorGrantedAuthority.OTT_AUTHORITY
})
@Configuration
class WebMfaConfig {

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .oneTimeTokenLogin(Customizer.withDefaults());

        return http.build();
    }
}
~~~

The idea is that **each factor is recorded only after the corresponding mechanism performs real verification**, and authorization can require both the password factor and the one-time-token factor. Delivery, enrollment, sessions, and policies still need full implementation; adding one annotation does not make a complete production MFA system.

## 7. Runnable Demo: Basic User, Bearer Service, Fail-Closed MFA

The demo uses **Spring Boot 3.x, Spring Security 6.x, Java 17+**. It exercises three points:

1. User calls `/user/profile` and `/user/admin` via HTTP Basic with user store/BCrypt.
2. Service calls `/service/jobs` via a Bearer opaque token; the token is verified by an **in-memory introspector for localhost only** so no Authorization Server is needed while learning.
3. `/user/high-risk` requires authority `MFA_VERIFIED`, **yet the demo never grants this authority**, because no factor verifier is implemented. The endpoint always blocks password-only users.

**The in-memory introspector only simulates token validation in this lesson**; it does not issue OAuth2 `client_credentials` tokens and does not verify issuer, expiry, revocation, or an external IdP. It is strictly **not a configuration for production**. Production must replace it with real JWT validation/introspection and token verification policies. The tests below do not prove a real MFA system is implemented.

### 7.1. Dependencies and files

Create a Spring Boot 3.x project with Gradle Wrapper/plugin, Java 17+, and dependency management. In the existing `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

The block above is **not a standalone build.gradle**. File structure:

~~~text
src/main/java/com/example/identitymodes/
  IdentityModesApplication.java
  SecurityConfig.java
  IdentityController.java

src/test/java/com/example/identitymodes/
  IdentityModesTest.java
~~~

### 7.2. IdentityModesApplication.java

~~~java
package com.example.identitymodes;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IdentityModesApplication {
    public static void main(String[] args) {
        SpringApplication.run(IdentityModesApplication.class, args);
    }
}
~~~

### 7.3. SecurityConfig.java

~~~java
package com.example.identitymodes;

import java.util.List;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    OpaqueTokenIntrospector demoIntrospector() {
        return token -> {
            if (!"demo-service-token".equals(token)) {
                throw new BadOpaqueTokenException("invalid_token");
            }

            return new DefaultOAuth2AuthenticatedPrincipal(
                "service:report-worker",
                Map.of(
                    "sub", "service:report-worker",
                    "client_id", "report-worker",
                    "scope", "jobs.read"
                ),
                List.of(new SimpleGrantedAuthority("SCOPE_jobs.read"))
            );
        };
    }

    @Bean
    @Order(1)
    SecurityFilterChain serviceChain(
            HttpSecurity http,
            OpaqueTokenIntrospector introspector) throws Exception {

        http
            .securityMatcher("/service/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/service/jobs")
                    .hasAuthority("SCOPE_jobs.read")
                .requestMatchers(HttpMethod.GET, "/service/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth -> oauth
                .opaqueToken(opaque -> opaque.introspector(introspector))
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain userChain(HttpSecurity http) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/user/profile")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/user/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/user/high-risk")
                    .hasAuthority("MFA_VERIFIED")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );

        return http.build();
    }
}
~~~

**Key explanations:**

- `UserDetailsService` and `PasswordEncoder` authenticate human accounts using BCrypt hashes.
- `demoIntrospector` accepts a localhost-only dummy token and returns a **service** principal, not Alice.
- `serviceChain` has `securityMatcher("/service/**")` and `@Order(1)`; it enables only Bearer token Resource Server authentication.
- `/service/jobs` requires `SCOPE_jobs.read`, while `/service/admin` requires `ROLE_ADMIN`, which the demo token lacks.
- `userChain` is the fallback chain at `@Order(2)`; `/public` allows anonymous access, `/user/profile` requires login, `/user/admin` requires ROLE_ADMIN.
- `/user/high-risk` requires `MFA_VERIFIED`; **no user is granted this marker**, because there is no factor verifier. This fail-closed policy shows where real step-up is needed.
- `anyRequest().denyAll()` blocks undeclared URLs. Never use broad `permitAll` or `web.ignoring` to fix permission errors.
- `STATELESS` in the demo avoids reading SecurityContext from HttpSession on subsequent requests. It **does not automatically enable JWT/MFA**.
- The demo uses only GET; CSRF is not disabled. When adding POST/PUT/DELETE, assess CSRF by client/credential transport.

### 7.4. IdentityController.java

~~~java
package com.example.identitymodes;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/public")
    public String publicInfo() {
        return "public";
    }

    @GetMapping("/user/profile")
    public String userProfile(Authentication authentication) {
        return "user:" + authentication.getName();
    }

    @GetMapping("/user/admin")
    public String userAdmin() {
        return "human-admin";
    }

    @GetMapping("/user/high-risk")
    public String highRisk() {
        return "high-risk";
    }

    @GetMapping("/service/jobs")
    public String serviceJobs(Authentication authentication) {
        return "jobs:" + authentication.getName();
    }

    @GetMapping("/service/admin")
    public String serviceAdmin() {
        return "service-admin";
    }

    @GetMapping("/unknown")
    public String unknown() {
        return "should-not-be-exposed";
    }
}
~~~

The Controller only reads the principal's name for demonstration. Never cast every principal to `UserDetails`, and never return credentials/secrets/tokens in HTTP responses.

### 7.5. Running and comparing results

From the directory containing Gradle Wrapper:

~~~bash
./gradlew bootRun
# Windows:
gradlew.bat bootRun
~~~

From another terminal on localhost:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/user/profile
curl -i -u alice:alice123 http://localhost:8080/user/profile
curl -i -u alice:alice123 http://localhost:8080/user/admin
curl -i -u admin:admin123 http://localhost:8080/user/admin
curl -i -u alice:alice123 http://localhost:8080/user/high-risk
curl -i http://localhost:8080/service/jobs
curl -i -H "Authorization: Bearer demo-service-token" http://localhost:8080/service/jobs
curl -i -H "Authorization: Bearer wrong-token" http://localhost:8080/service/jobs
curl -i -H "Authorization: Bearer demo-service-token" http://localhost:8080/service/admin
curl -i -u alice:alice123 http://localhost:8080/service/jobs
curl -i -u alice:alice123 http://localhost:8080/unknown
~~~

With the exact demo app and no proxies/custom handlers:

| Request | Expected status | Why? |
| --- | --- | --- |
| Anonymous GET `/public` | **200** | permitAll |
| Anonymous GET `/user/profile` | **401** | User chain requires Basic credentials |
| Alice valid Basic `/user/profile` | **200** | Body `user:alice` |
| Alice valid Basic `/user/admin` | **403** | ROLE_USER lacks ROLE_ADMIN |
| Admin valid Basic `/user/admin` | **200** | Body `human-admin` |
| Alice valid Basic `/user/high-risk` | **403** | No verified MFA evidence |
| Anonymous GET `/service/jobs` | **401** | Bearer authentication missing |
| Valid demo Bearer `/service/jobs` | **200** | Body `jobs:service:report-worker` |
| Invalid Bearer `/service/jobs` | **401** | Introspector rejects |
| Demo Bearer `/service/admin` | **403** | Scope jobs.read does not equal ROLE_ADMIN |
| Alice Basic `/service/jobs` | **401** | Service chain does not authenticate with Basic |
| Alice Basic `/unknown` | **403** | Fallback denyAll |

401/403 codes and error bodies depend on `AuthenticationEntryPoint`/`AccessDeniedHandler` if the app uses custom handlers. These values are **expected HTTP results**, not measured Java stdout.

**Never use demo passwords or bearer tokens on real networks.** Both HTTP Basic and bearer tokens require TLS protection; keep secrets out of source code, logs, shell history, and traces. The demo's literal token has no cryptographic validation, expiry, or revocation.

## 8. MockMvc Tests: Distinguishing Principal and MFA Policy

Create `src/test/java/com/example/identitymodes/IdentityModesTest.java`:

~~~java
package com.example.identitymodes;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class IdentityModesTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicIsAnonymous() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void userBasicChecksPassword() throws Exception {
        mvc.perform(get("/user/profile"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/user/profile")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(content().string("user:alice"));

        mvc.perform(get("/user/profile")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void humanAccountNeedsAdminRoleForAdminEndpoint()
            throws Exception {
        mvc.perform(get("/user/admin")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/user/admin")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk())
            .andExpect(content().string("human-admin"));
    }

    @Test
    void serviceBearerCreatesDifferentPrincipal() throws Exception {
        mvc.perform(get("/service/jobs"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/service/jobs")
                .header(HttpHeaders.AUTHORIZATION, "Bearer demo-service-token"))
            .andExpect(status().isOk())
            .andExpect(content().string("jobs:service:report-worker"));

        mvc.perform(get("/service/jobs")
                .header(HttpHeaders.AUTHORIZATION, "Bearer invalid"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void userBasicCannotBecomeService() throws Exception {
        mvc.perform(get("/service/jobs")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void serviceScopeDoesNotGrantAdminRole() throws Exception {
        mvc.perform(get("/service/admin")
                .header(HttpHeaders.AUTHORIZATION, "Bearer demo-service-token"))
            .andExpect(status().isForbidden());
    }

    @Test
    void passwordOnlyDoesNotSatisfyMfa() throws Exception {
        mvc.perform(get("/user/high-risk")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void authorizationRuleCanRecognizeTrustedFactor()
            throws Exception {
        mvc.perform(get("/user/high-risk")
                .with(user("alice").authorities(
                    new SimpleGrantedAuthority("ROLE_USER"),
                    new SimpleGrantedAuthority("MFA_VERIFIED")
                )))
            .andExpect(status().isOk())
            .andExpect(content().string("high-risk"));
    }

    @Test
    void unknownRouteIsDenied() throws Exception {
        mvc.perform(get("/unknown")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());
    }
}
~~~

Run tests:

~~~bash
./gradlew test
# Windows:
gradlew.bat test
~~~

**Do not misunderstand the MFA test:** `SecurityMockMvcRequestPostProcessors.user(...)` **mocks an Authentication** to test authorization. It does not perform password login, does not verify TOTP/WebAuthn, and does not confirm the system has real MFA. The test only proves that once a trusted component grants authority `MFA_VERIFIED`, the rule allows access. Production requires dedicated verifiers and tests for enrollment, challenge binding, factor freshness, replay, and recovery.

The Basic and Bearer tests exercise the demo's filter paths. Statuses are **expectations from the code**; run Gradle on a real project to verify the build.

## 9. Production Example: OAuth2 Client and Resource Server

### 9.1. Service actively obtaining tokens via client_credentials

Configuration for an **application calling another API** with `spring-boot-starter-oauth2-client`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          report-worker:
            provider: company-idp
            client-id: ${WORKER_CLIENT_ID}
            client-secret: ${WORKER_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope: jobs.read
        provider:
          company-idp:
            token-uri: https://idp.example.test/oauth2/token
~~~

The YAML above is a **configuration example**; it does not send requests itself and requires a real IdP. The app must also use OAuth2 Client support/`OAuth2AuthorizedClientManager` or an equivalent integration to fetch and attach access tokens to outgoing requests. Protect client secrets with a secret manager and rotate them; choose the right service principal for the token lifecycle rather than randomly reusing a browser user's identity.

### 9.2. Resource Server verifying JWTs from an issuer

An API **receiving** tokens can configure:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/company
~~~

With `spring-boot-starter-oauth2-resource-server` and SecurityFilterChain:

~~~java
// Snippet inside HttpSecurity configuration:
http.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults()));
~~~

Production requires a **real issuer** and appropriate audience validators/scope rules. Never declare `issuer-uri` alone and assume the API verified every business claim; test audience, expiry, scopes, key rotation, and access tokens meant for other APIs.

### 9.3. Resource Server verifying opaque tokens via introspection

Depending on the IdP, replace the demo introspector with `SpringOpaqueTokenIntrospector` or Spring Boot config:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

The Resource Server uses **its own** credentials to call the introspection endpoint; that is a distinct boundary from the worker credentials used at the token endpoint. When introspection fails or a token is inactive, reject per policy rather than falling back to permitAll.

## 10. Distinguishing 401, 403, and Assurance Levels

| Scenario | Common interpretation |
| --- | --- |
| No user credentials sent to Basic-protected endpoint | **401** (authentication required) |
| User sends wrong password | **401** |
| Service sends invalid/expired token | **401** from Bearer mechanism |
| Valid service token yet missing scope | **403** (authorization denied) |
| Alice logged in yet lacks ROLE_ADMIN | **403** |
| Alice logged in with password, has not completed MFA policy | May be **403** or **redirect/challenge** per MFA/entry point mechanism |
| POST without CSRF token when CSRF enabled | May be **403**, independent of MFA |
| User completed MFA yet lacks resource permission | Still **403** or corresponding denial |
| Request matches no SecurityFilterChain | May be **unprotected** if fallback chain is missing |

**Never infer solely from status codes.** In the demo, user and service use two chains with different entry points. In a web app with form login, missing authentication can return a 302 redirect to login instead of 401. In managed MFA frameworks, a missing factor can trigger a challenge flow rather than JSON 403.

## 11. Security Across the Identity Lifecycle

### 11.1. User lifecycle

Registration, email verification, setting password hashes, locking/disabling, MFA enrollment, recovery, password changes, session revocation, and auditing all affect authentication. `UserDetailsService` does not implement all of these tasks by itself.

### 11.2. Workload lifecycle

Provisioning client IDs/workload identities, least-privilege scopes, secret/certificate rotation, token expiry, client revocation, environment isolation, auditing, and least privilege. Short-lived tokens shrink theft impact; sender-constrained tokens may be needed depending on the threat model.

### 11.3. MFA lifecycle

Enrollment must enforce user binding; verifiers must check nonces/challenges, expiry, and replay; session/token assurance must expire; adding/changing factors and recovery are high-risk actions. Never put OTP codes/seeds in logs, metrics, or URLs.

### 11.4. Tokens and authorities can go stale

Changing a role in the database does not automatically change roles inside already-issued JWTs; locking a service client does not automatically invalidate active tokens unless revocation is implemented; completing MFA once does not remain valid forever for step-up. Implement **revalidation and revocation** mechanisms matched to business sensitivity.

## 12. Common Mistakes

### 12.1. Thinking MFA is a service account

MFA is a process that raises a subject's assurance. A service identity remains a service identity; a user identity remains a user identity.

### 12.2. Treating client_credentials as user delegation

A client-credentials access token represents the client, with no user subject by default. When a service acts on a user's behalf, explicit delegation and auditing are required.

### 12.3. Sharing one secret across all workers

Compromising one secret opens too much access. Separate service identities, scopes, environments, and rotation.

### 12.4. Trusting a JWT merely because the payload is readable

Signature, issuer, audience, time, and policy validation are mandatory, not just Base64 decoding.

### 12.5. Using broad `.authenticated()` without distinguishing subjects

An authenticated service can satisfy `authenticated()` without having user permissions. Check scopes/roles/principal types/issuers, resources, and delegation.

### 12.6. Calling two passwords/PINs MFA

Both are knowledge factors and thus do not prove two independent factor categories.

### 12.7. Accepting client-sent MFA markers

An `X-MFA-Verified` header or `MFA_VERIFIED` role from a request cannot substitute for factor verification.

### 12.8. Granting MFA_VERIFIED inside UserDetailsService

If UserDetails always includes this marker, a password alone satisfies the rule, defeating step-up. Markers must be granted by a trusted verifier mechanism with freshness.

### 12.9. Treating TOTP as phishing-resistant

Manually entered codes can be relayed. WebAuthn provides stronger domain binding when implemented properly.

### 12.10. Using ID tokens as access tokens

ID tokens serve the OIDC client; APIs must accept access tokens with the right audience/scopes.

### 12.11. Skipping CSRF because login used MFA

MFA and CSRF defend against different threats; session/browser flows still require an appropriate CSRF policy.

### 12.12. Forgetting a fallback chain

`securityMatcher("/service/**")` matches only service paths. Without a chain protecting the rest, other URLs can fall outside Spring Security.

### 12.13. Testing only the happy path

Test anonymous requests, wrong passwords, invalid tokens, missing scopes, missing roles, missing factors, invalid issuer/audience, stale assurance, and ownership; never treat 200 alone as proof of security.

## 13. Self-Check Questions

**Question 1.** A cron job uses OAuth2 `client_credentials`. Is it a user or a service?

**Answer:** Service/client identity, not representing an end user by default.

**Question 2.** Are a password + PIN definitely MFA?

**Answer:** No. Both are knowledge factors.

**Question 3.** Does `SCOPE_jobs.read` equal `ROLE_ADMIN`?

**Answer:** No. Rules check the exact authority per scope/role mapping.

**Question 4.** Can a `ROLE_USER` user who completed MFA read another tenant's orders?

**Answer:** No if ownership/tenant policy denies it. MFA does not replace authorization.

**Question 5.** Can a worker send `X-Service: admin` to be treated as an admin?

**Answer:** No. Identity and authorities must come from verified credentials/tokens.

**Question 6.** A JWT has a valid-looking payload yet an invalid signature—what should the API do?

**Answer:** Reject the token; never treat claims as trusted.

**Question 7.** Does a Resource Server issue access tokens itself when `.oauth2ResourceServer(...)` is enabled?

**Answer:** No. It verifies tokens; the Authorization Server issues them and the OAuth2 Client uses them.

**Question 8.** Is a client-submitted token with claim `amr=["pwd","otp"]` enough to prove MFA?

**Answer:** No. You must verify token source/signature and IdP contract, user binding, and freshness.

**Question 9.** Why should you never return the raw `Authentication` as JSON?

**Answer:** It can expose credentials/tokens, internal principals, and metadata not meant for clients.

**Question 10.** Why does a MockMvc test attaching a user with an MFA marker not prove OTPs are checked?

**Answer:** That is mocked authorization; a real factor verifier and end-to-end tests are still missing.

**Question 11.** How does MFA at login differ from step-up?

**Answer:** Login MFA requires factors before issuing a session; step-up requires an extra factor at the time of a sensitive action, potentially requiring recent authentication.

**Question 12.** Why is client secret rotation important for services?

**Answer:** It limits credential exposure windows and lets compromised workloads be revoked.

**Question 13.** Does every passkey automatically prove MFA?

**Answer:** No. It depends on the authenticator and user verification/policy state.

**Question 14.** When a service must act on Alice's resources, is `client_credentials` alone sufficient?

**Answer:** Not necessarily. You may need user delegation/on-behalf-of alongside owner/tenant checks and auditing.

**Question 15.** Can Spring Security 7 factor authorities be copied straight into Boot 3/Security 6?

**Answer:** Not verbatim. Check versions; the example above is a Spring Security 7 snippet only.

## 14. Official Reference Documentation

- Spring Security — **Authentication Architecture**: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — **Username/Password Authentication**: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/index.html
- Spring Security 6.5 — **OAuth2 Resource Server**: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/
- Spring Security 6.5 — **Opaque Token**: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html
- Spring Security — **OAuth2 Client/client_credentials**: https://docs.spring.io/spring-security/reference/servlet/oauth2/index.html
- Spring Security — **OAuth2 Login**: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html
- Spring Security 7 — **MFA (FactorGrantedAuthority)**: https://docs.spring.io/spring-security/reference/servlet/authentication/mfa.html
- Spring Security — **Authorization / Request Security**: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- OWASP — **Multi-Factor Authentication Cheat Sheet**: https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html
- NIST SP 800-63B — **Authenticator Management**: https://pages.nist.gov/800-63-4/sp800-63b.html

**Remember:** **User authentication** verifies humans; **service authentication** verifies workloads, usually with no end user; **MFA** uses independent factors to raise an identity's assurance level. Regardless of how authentication happens, Spring Security still needs authorization checking **principal, role/scope, resource, tenant, and assurance**. Never mistake a service token for a user token, and never treat MFA as administrative privilege.
