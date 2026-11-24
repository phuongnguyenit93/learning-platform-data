# Building an AuthenticationProvider for a Custom Evidence Type

## 1. Objectives of This Capstone Practice

In Spring Security, applications usually authenticate with username/password, sessions, HTTP Basic, JWT, OAuth2/OIDC, or passkeys. However, some systems must accept **a custom type of evidence** from a device, an internal authorization workflow, or another verification service. Instead of stuffing the new code into `UsernamePasswordAuthenticationToken` and pretending it is a password, you can build a **custom Authentication token + custom AuthenticationProvider + custom authentication filter**, then wire them into `AuthenticationManager` and `SecurityFilterChain`.

This exercise follows the **one-time opaque proof** model, pre-issued for a fixed principal. An HTTP client sends the code via the `X-Lab-Proof` header. The server validates the proof by hash, expiration time, and consumed state; on success, it constructs a trusted `Authentication` with the `PROOF_READ` authority, granting access to a protected endpoint.

**This is a bearer-secret proof**, not cryptographic proof that the client owns a private key, not a passkey/FIDO2, and not SMS MFA. Anyone who learns the code before it is redeemed can spend it. Therefore you must protect **issuance, transport, storage, single-use redemption, and revocation**.

**Learning outcomes:**

1. Understand `Authentication`, `AuthenticationProvider`, `ProviderManager`, `SecurityContext`, and Servlet filter responsibilities accurately.
2. Implement an unauthenticated `ProofAuthenticationToken` and a trusted variant created **solely** by the provider after validating the proof.
3. Implement `supports(Class<?>)` for the exact token class and `authenticate(Authentication)` for all three outcomes: success, `null` when unsupported, and `AuthenticationException` on bad credentials.
4. Validate single-use proofs via digests, constant-time comparison, TTL, and atomic state in the lab.
5. Configure a stateless `SecurityFilterChain`, custom header filter, proper 401 responses, and authority-based authorization.
6. Run Spring Boot/Java 17+ and test the provider, HTTP authentication, replay protection, and credential clearing.
7. Clearly identify what is **insufficient for production**: token issuance, distributed DB transactions, rate limiting, key management, MFA assurance, and auditing.

**Example version set:** Java 17+, Spring Boot **3.5.16**, Spring Security **6.5.11**, Servlet/MVC, Maven, and JUnit 5. Boot BOM 3.5.16 officially manages Security 6.5.11. The example does not rely on Spring Security 7+ APIs; if you use another Boot/Security line, check compatibility and migration guides.

## 2. Framing the Problem: What Is the Custom Evidence?

Suppose an internal service issues **a single-entry gate token** to a user already verified over a trusted channel beforehand. The token:

- Is issued outside the HTTP API under test, via an already authenticated/authorized workflow.
- Is bound to an **internal account** and a specific purpose, such as `READ_ONE_DOCUMENT`.
- Has **high entropy** in production, a short TTL, and is **single-use**.
- Is delivered to the client over a secure channel and sent in an HTTPS header, **never** in a query string.
- Stores only its digest on the server; upon successful verification, its state transitions to **consumed**.
- Never self-grants ADMIN privileges or picks a principal from JSON sent by the client.

In **the lab**, we use a visible code `LAB-ONE-TIME-PROOF` so learners can run `curl`. This is a **fixed, non-secret fixture**; never use it or hardcoded issuance in real environments.

### 2.1. Distinguishing Four Commonly Confused Things

| Object | Meaning | Who Creates It | Trustworthy When Received from Client? |
| --- | --- | --- | --- |
| Raw proof | Unverified code/credential | A trusted issuer; a fixture in the lab | **Not yet** |
| Unauthenticated `ProofAuthenticationToken` | Container for the proof just read by the filter | Custom filter | **Not yet** |
| Authenticated `ProofAuthenticationToken` | Server-verified principal/authorities | Custom provider after proof validation | **Yes**, inside the trusted server boundary |
| `SecurityContext` | Authentication state of the current request/thread | Authentication filter/manager | Only after setting a verified Authentication |

It offers zero security if the filter does this immediately upon reading a header:

~~~java
// ANTI-PATTERN: never do this!
var principal = request.getHeader("X-User");
var trusted = UsernamePasswordAuthenticationToken.authenticated(
    principal, null, List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));
SecurityContextHolder.getContext().setAuthentication(trusted);
~~~

That **anti-pattern** blindly trusts client-supplied data; an attacker can change the header to impersonate any principal. The proper path goes through a provider that validates the proof and resolves the account/authorities from **server-side data**.

### 2.2. A One-Time Proof Differs from a Long-Lived Login Session

The lab allows access to **one HTTP request** sent with a valid proof; the proof is consumed immediately. The next request reusing that proof gets **401**. This is intended behavior, not a bug.

If a real app needs "sign in once, then browse multiple pages", build a **flow exchanging the proof for a secure session or another access token**, complete with session fixation protection, `SecurityContextRepository`, CSRF for session/cookies, and token audience/expiry/revocation. **Never turn a one-time proof into a reusable bearer token** merely for UI convenience.

## 3. Spring Security Architecture and Data Flow

~~~text
HTTP GET /api/secret
X-Lab-Proof: <opaque-proof>
          |
          v
ProofHeaderFilter (OncePerRequestFilter)
  - read header with length limit
  - create ProofAuthenticationToken.untrusted(proof)
          |
          v
AuthenticationManager (ProviderManager)
          |
          v
ProofAuthenticationProvider
  - supports(ProofAuthenticationToken.class)?
  - check token type and isAuthenticated=false
  - check proof in ProofStore
  - verify hash + TTL + one-time use
  - map subject + authorities SERVER-SIDE
          |
          +-- fail -> BadCredentialsException -> HTTP 401
          |
          +-- success -> ProofAuthenticationToken.trusted(...)
                               |
                               v
                 SecurityContextHolder.createEmptyContext()
                 context.setAuthentication(result)
                 SecurityContextHolder.setContext(context)
                               |
                               v
                  AuthorizationFilter: PROOF_READ?
                               |
                   +-----------+-----------+
                   |                       |
                   v                       v
                HTTP 200                 HTTP 403
                   |
                   v
         clear SecurityContext at end of request
         do not store session (STATELESS)
~~~

**Chain of responsibilities:**

- `OncePerRequestFilter`: translates an HTTP request into an `Authentication` request and handles HTTP failure responses. It never declares a token valid on its own.
- `ProviderManager`: asks which provider supports the token, calls `authenticate`, and returns the result or throws an exception.
- `AuthenticationProvider`: validates the proof, binds a known account and permitted authorities, and returns a trusted token.
- `SecurityContextHolder`: holds authentication **for the current request**, and must be cleared cleanly per lifecycle.
- `AuthorizationFilter`: checks whether the endpoint requires `PROOF_READ`. Successful authentication **does not imply** universal permissions.
- `SecurityContextRepository`: controls context persistence across requests; the lab uses `NullSecurityContextRepository` to **intentionally avoid creating sessions**.

### 3.1. The AuthenticationProvider Contract

Two methods:

~~~java
boolean supports(Class<?> authentication);
Authentication authenticate(Authentication authentication)
    throws AuthenticationException;
~~~

Inside the custom proof provider:

~~~java
@Override
public boolean supports(Class<?> type) {
    return ProofAuthenticationToken.class.isAssignableFrom(type);
}
~~~

`supports` returning `true` only means the provider **can attempt** to process that token type; it does not prove the proof is valid. Return rules:

| Case | `authenticate(...)` | Outcome |
| --- | --- | --- |
| Authentication token of **another** type | `null` (if called directly) | Defers to other providers; `ProviderManager` usually skips via `supports=false` |
| Proof token right type, valid code, unused, unexpired | Trusted `Authentication` | Manager succeeds |
| Proof token right type, wrong/expired/used code | Throw `BadCredentialsException` | Authentication fails |
| Proof token claiming `isAuthenticated=true` on input | Reject, never trust client | Blocks bypass |
| Verification store/service failure | `AuthenticationServiceException` or suitable fail-closed | Never fake success or return null to fall through to a weaker provider |

**Never `return null` for an invalid proof** inside the provider responsible for verifying it. `null` means "cannot decide / out of scope", whereas an invalid proof is a **failed authentication**.

### 3.2. Why Do You Need a Custom Authentication Token?

You could shoehorn an arbitrary string into `UsernamePasswordAuthenticationToken`, yet doing so easily blurs distinct mechanisms. A dedicated class:

- Makes explicit **this is a one-time proof**, not a password.
- Ensures `supports(Class<?>)` never accidentally intercepts username/password, OAuth2 bearer, or LDAP tokens.
- Separates untrusted requests from trusted results.
- Keeps authorities **empty** on input so only the provider attaches roles/scopes.
- Enforces rules blocking callers from manually calling `setAuthenticated(true)` to elevate trust.

`AbstractAuthenticationToken` is a solid base class: it handles authorities, details, `isAuthenticated()`, and `CredentialsContainer`, while you still define the principal, credentials, and safe constructors.

## 4. Designing a Safe ProofStore: Digest, TTL, and Atomic Consume

In the lab, the proof is "pre-issued" at startup. `ProofStore` records:

~~~text
proof_digest      = SHA-256(raw-proof)
subject_id        = learner
authority         = PROOF_READ
expires_at        = now + 30 minutes
used              = false
~~~

When receiving a code:

1. Ensure it is non-null, non-blank, and within max length.
2. Verify it has not expired against the **server clock**.
3. Compute its SHA-256 digest and compare against the stored digest with `MessageDigest.isEqual(...)`.
4. If matched, perform an atomic `compareAndSet(false, true)` so only one call succeeds within **a single JVM**.
5. Grant the trusted `Authentication` only after redemption succeeds.
6. Never emit the raw proof into logs, exception messages, responses, or `SecurityContext`.

**Why is a SHA-256 digest acceptable for sufficiently random proofs?** If the raw proof carries 128–256 bits of entropy, guessing from the hash is infeasible. For human-chosen passwords, **never** use plain SHA-256; use a proper `PasswordEncoder` (bcrypt, Argon2, PBKDF2, or scrypt per requirements).

**Do not confuse local atomicity with multi-server atomicity.** `AtomicBoolean` stops two threads in the same process from consuming a proof, but **cannot stop two replicas** from accepting it concurrently. Production uses DB transactions/conditional updates, appropriate Redis Lua scripts/atomic operations, unique constraints, and expirations; consumed state must be persisted durably.

### 4.1. Database Model for Multiple Proofs/Accounts

Reference design:

~~~text
one_time_auth_proof
  id
  subject_id                (FK internal account)
  digest                    (32-byte binary or domain-separated digest)
  purpose                   (e.g., READ_ONE_DOCUMENT)
  issued_at
  expires_at
  consumed_at nullable
  revoked_at nullable
  issuer_id
  audience/service
  account_version
  attempt_count
  metadata_sanitized
~~~

The verification transaction must check **digest, subject binding, purpose, audience, TTL, active account, and `consumed_at IS NULL`**, updating `consumed_at` atomically before issuing the principal. Under contention, only one request succeeds.

**Never** let the client send `subject_id` and look up the user from that field. The subject must come from the server-verified proof record. For high-value tokens, consider `HMAC(serverPepper, proof)` to limit impact if DB hashes leak, paired with key rotation; exact design depends on threat model and key management.

## 5. Complete Spring Boot 3.5.16 / Java 17+ Project

The example comprises **one application Java file**, one provider test file, one HTTP integration test file, and `pom.xml`. The code redeems a single-use bearer proof with no anonymous issuance endpoint.

### 5.1. Structure

~~~text
custom-proof-provider/
├── pom.xml
└── src/
    ├── main/
    │   └── java/demo/proof/ProofApp.java
    └── test/
        └── java/demo/proof/
            ├── ProofProviderTests.java
            └── ProofHttpTests.java
~~~

### 5.2. pom.xml

~~~xml
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
    <artifactId>custom-proof-provider</artifactId>
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

Do not declare separate versions for individual Security JARs to avoid skew across `core/web/config/test`. With Spring Boot BOM 3.5.16, Spring Security 6.5.11 is managed consistently.

### 5.3. ProofApp.java — Complete Application

Create `src/main/java/demo/proof/ProofApp.java`:

~~~java
package demo.proof;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ProofApp {

    public static void main(String[] args) {
        SpringApplication.run(ProofApp.class, args);
    }

    @Bean
    ProofStore proofStore() {
        return new ProofStore();
    }

    @Bean
    ProofProvider proofProvider(ProofStore store) {
        return new ProofProvider(store);
    }

    @Bean
    SecurityFilterChain security(
            HttpSecurity http, ProofProvider provider) throws Exception {

        AuthenticationManager manager = new ProviderManager(provider);

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/secret")
                    .hasAuthority("PROOF_READ")
                .anyRequest().denyAll())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(context -> context
                .securityContextRepository(
                    new NullSecurityContextRepository()))
            // This lab only exposes GET, the proof is explicitly sent in a
            // header, and no cookie-based authentication is used.
            .csrf(AbstractHttpConfigurer::disable)
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .logout(AbstractHttpConfigurer::disable)
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(
                    new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
            .addFilterBefore(
                new ProofHeaderFilter(manager),
                UsernamePasswordAuthenticationToken.class
                    .getSuperclass() == null
                    ? org.springframework.security.web.authentication
                        .UsernamePasswordAuthenticationFilter.class
                    : org.springframework.security.web.authentication
                        .UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }

    @RestController
    static class Routes {

        @GetMapping("/api/health")
        String health() {
            return "ready";
        }

        @GetMapping("/api/secret")
        Identity secret(Authentication authentication) {
            return new Identity(
                authentication.getName(), "ONE_TIME_OPAQUE_PROOF");
        }
    }

    record Identity(String subject, String evidenceType) {}

    static final class ProofAuthenticationToken
            extends AbstractAuthenticationToken {

        private final Object principal;
        private Object proof;

        private ProofAuthenticationToken(
                Object principal,
                Object proof,
                Collection<? extends GrantedAuthority> authorities,
                boolean trusted) {
            super(authorities);
            this.principal = principal;
            this.proof = proof;
            super.setAuthenticated(trusted);
        }

        static ProofAuthenticationToken untrusted(String rawProof) {
            return new ProofAuthenticationToken(
                "unverified", rawProof, List.of(), false);
        }

        static ProofAuthenticationToken trusted(
                String userId,
                Collection<? extends GrantedAuthority> authorities) {
            return new ProofAuthenticationToken(
                userId, null, authorities, true);
        }

        @Override
        public Object getPrincipal() {
            return principal;
        }

        @Override
        public Object getCredentials() {
            return proof;
        }

        @Override
        public void eraseCredentials() {
            super.eraseCredentials();
            this.proof = null;
        }

        @Override
        public void setAuthenticated(boolean value) {
            if (value) {
                throw new IllegalArgumentException(
                    "Trusted tokens must be created by the provider");
            }
            super.setAuthenticated(false);
        }
    }

    static final class ProofStore {
        // Public lab FIXTURE: DO NOT use in production!
        static final String LAB_PROOF = "LAB-ONE-TIME-PROOF";

        private final byte[] digest = sha256(LAB_PROOF);
        private final AtomicBoolean used = new AtomicBoolean(false);
        private final Instant expiresAt =
            Instant.now().plus(Duration.ofMinutes(30));

        String verifiedSubject() {
            return "learner";
        }

        boolean redeem(String submitted) {
            if (submitted == null || submitted.isBlank()
                    || submitted.length() > 256
                    || !Instant.now().isBefore(expiresAt)) {
                return false;
            }

            byte[] supplied = sha256(submitted);
            if (!MessageDigest.isEqual(digest, supplied)) {
                return false;
            }

            // Guarantees atomicity only within a single process/JVM.
            return used.compareAndSet(false, true);
        }

        private static byte[] sha256(String value) {
            try {
                return MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
            } catch (NoSuchAlgorithmException impossible) {
                throw new IllegalStateException(impossible);
            }
        }
    }

    static final class ProofProvider implements AuthenticationProvider {
        private final ProofStore store;

        ProofProvider(ProofStore store) {
            this.store = store;
        }

        @Override
        public boolean supports(Class<?> type) {
            return ProofAuthenticationToken.class.isAssignableFrom(type);
        }

        @Override
        public Authentication authenticate(Authentication incoming)
                throws AuthenticationException {
            if (!(incoming instanceof ProofAuthenticationToken token)) {
                return null;
            }
            if (token.isAuthenticated()) {
                throw new BadCredentialsException("Invalid proof");
            }
            if (!(token.getCredentials() instanceof String raw)
                    || !store.redeem(raw)) {
                throw new BadCredentialsException("Invalid proof");
            }

            // Principal and authority come from SERVER data; never
            // trust client-supplied usernames or roles.
            return ProofAuthenticationToken.trusted(
                store.verifiedSubject(),
                List.of(new SimpleGrantedAuthority("PROOF_READ")));
        }
    }

    // Do not annotate with @Component/@Bean so Boot does not register
    // this filter a second time on the Servlet container outside SecurityFilterChain.
    static final class ProofHeaderFilter extends OncePerRequestFilter {
        private final AuthenticationManager manager;

        ProofHeaderFilter(AuthenticationManager manager) {
            this.manager = manager;
        }

        @Override
        protected void doFilterInternal(
                HttpServletRequest request,
                HttpServletResponse response,
                FilterChain chain)
                throws ServletException, IOException {

            String raw = request.getHeader("X-Lab-Proof");

            if (raw == null) {
                chain.doFilter(request, response);
                return;
            }

            if (raw.isBlank() || raw.length() > 256) {
                response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
                return;
            }

            ProofAuthenticationToken requestToken =
                ProofAuthenticationToken.untrusted(raw);
            Authentication verified;

            try {
                verified = manager.authenticate(requestToken);
            } catch (AuthenticationException failure) {
                // Do not log headers, credentials, or exception messages.
                SecurityContextHolder.clearContext();
                response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
                return;
            } finally {
                requestToken.eraseCredentials();
            }

            SecurityContext context =
                SecurityContextHolder.createEmptyContext();
            context.setAuthentication(verified);
            SecurityContextHolder.setContext(context);

            try {
                chain.doFilter(request, response);
            } finally {
                SecurityContextHolder.clearContext();
            }
        }
    }
}
~~~

### 5.4. Clean Up One Line for Readability Before Running

In `security(...)`, the `.addFilterBefore(...)` call above uses a ternary expression solely to highlight that the anchor **must be a Filter class**, not an Authentication token. **Replace that entire `.addFilterBefore(...)` block** with the simpler equivalent below before compiling:

~~~java
.addFilterBefore(
    new ProofHeaderFilter(manager),
    UsernamePasswordAuthenticationFilter.class);
~~~

Also add the import:

~~~java
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
~~~

**Never pass `UsernamePasswordAuthenticationToken.class` as the anchor to `addFilterBefore`**: a token is not a Servlet Filter. In this lab, the concise form above is recommended and should be used in the final project.

> The `csrf.disable()` configuration in the example is appropriate only because this is a **stateless, GET-only lab API that does not rely on automatically sent cookies** and expects the client to submit the secret explicitly in a header. If you convert the flow to sessions/cookies or add state-changing POSTs, re-evaluate CSRF rather than blindly copying `csrf.disable()`.

## 6. Testing the Provider Directly with JUnit 5

File `src/test/java/demo/proof/ProofProviderTests.java`:

~~~java
package demo.proof;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.*;

class ProofProviderTests {

    @Test
    void supportsOnlyCustomTokenType() {
        var provider =
            new ProofApp.ProofProvider(new ProofApp.ProofStore());

        assertTrue(provider.supports(
            ProofApp.ProofAuthenticationToken.class));
        assertFalse(provider.supports(
            UsernamePasswordAuthenticationToken.class));
    }

    @Test
    void unsupportedAuthenticationReturnsNullIfCalledDirectly() {
        var provider =
            new ProofApp.ProofProvider(new ProofApp.ProofStore());

        Authentication unrelated =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "password");

        assertNull(provider.authenticate(unrelated));
    }

    @Test
    void incorrectProofIsRejectedAndDoesNotConsumeValidProof() {
        var store = new ProofApp.ProofStore();
        var provider = new ProofApp.ProofProvider(store);

        assertThrows(BadCredentialsException.class,
            () -> provider.authenticate(
                ProofApp.ProofAuthenticationToken.untrusted("wrong")));

        Authentication success = provider.authenticate(
            ProofApp.ProofAuthenticationToken.untrusted(
                ProofApp.ProofStore.LAB_PROOF));

        assertTrue(success.isAuthenticated());
        assertEquals("learner", success.getName());
    }

    @Test
    void correctProofCreatesTrustedResultAndRejectsReplay() {
        var provider =
            new ProofApp.ProofProvider(new ProofApp.ProofStore());

        Authentication verified = provider.authenticate(
            ProofApp.ProofAuthenticationToken.untrusted(
                ProofApp.ProofStore.LAB_PROOF));

        assertTrue(verified.isAuthenticated());
        assertEquals("learner", verified.getName());
        assertNull(verified.getCredentials());
        assertTrue(verified.getAuthorities().stream()
            .anyMatch(a -> "PROOF_READ".equals(a.getAuthority())));

        assertThrows(BadCredentialsException.class,
            () -> provider.authenticate(
                ProofApp.ProofAuthenticationToken.untrusted(
                    ProofApp.ProofStore.LAB_PROOF)));
    }

    @Test
    void trustedInputCannotBeReauthenticatedAsRawProof() {
        var provider =
            new ProofApp.ProofProvider(new ProofApp.ProofStore());

        Authentication alreadyTrusted =
            ProofApp.ProofAuthenticationToken.trusted(
                "fake-principal",
                List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));

        assertThrows(BadCredentialsException.class,
            () -> provider.authenticate(alreadyTrusted));
    }
}
~~~

Key assertions:

- Verify supported vs. unsupported token types.
- Unsupported token called directly returns `null`, whereas an invalid proof of the right type throws `BadCredentialsException`.
- Valid proof produces a trusted principal with only the `PROOF_READ` authority.
- Raw proof is never retained in `getCredentials()` of the authenticated result.
- Replays are rejected.
- Provider rejects a pre-authenticated token fabricated on input.

**Unit test scope:** each test instantiates a fresh `ProofStore` so one test consuming the proof does not break subsequent tests depending on run order. For production persistence, test DB transactions/multi-replica setups and races separately.

## 7. Testing HTTP/Filter/SecurityContext with MockMvc

File `src/test/java/demo/proof/ProofHttpTests.java`:

~~~java
package demo.proof;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProofHttpTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicHealthIsAccessibleWithoutProof() throws Exception {
        mvc.perform(get("/api/health"))
            .andExpect(status().isOk())
            .andExpect(content().string("ready"));
    }

    @Test
    void missingProofCannotAccessProtectedResource()
            throws Exception {
        mvc.perform(get("/api/secret"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidProofGetsUnauthorizedWithoutPrincipal()
            throws Exception {
        mvc.perform(get("/api/secret")
                .header("X-Lab-Proof", "wrong"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validProofGrantsOneRequestAndReplayFails()
            throws Exception {
        mvc.perform(get("/api/secret")
                .header("X-Lab-Proof",
                    ProofApp.ProofStore.LAB_PROOF))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.subject").value("learner"))
            .andExpect(jsonPath("$.evidenceType")
                .value("ONE_TIME_OPAQUE_PROOF"));

        mvc.perform(get("/api/secret")
                .header("X-Lab-Proof",
                    ProofApp.ProofStore.LAB_PROOF))
            .andExpect(status().isUnauthorized());
    }
}
~~~

### 7.1. Verified Properties

| Test | What It Proves |
| --- | --- |
| GET /api/health without proof | Public route works |
| GET /api/secret without proof | Authorization/entry point returns 401 |
| GET /api/secret invalid proof | Provider/filter rejects without creating a trusted principal |
| GET /api/secret valid proof, then reuse | First request receives server authority; second request is blocked as replay |

The project has **5 unit tests + 4 HTTP integration tests = 9 tests**.

**Never use `@WithMockUser` as a substitute for these tests:** that helper injects a mock principal directly into `SecurityContext` and **does not prove the real `ProofAuthenticationProvider` ran**. Send the custom header through the filter and verify the resulting request as above.

### 7.2. Running Tests

In the project directory with JDK 17+ and Maven:

~~~bash
mvn clean test
~~~

When dependency resolution and compilation succeed, the **expected** summary is:

~~~text
Tests run: 9, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

This is **expected output for the example project**, not a log captured from the reader's machine. Maven also prints additional plugin and JDK-specific output.

### 7.3. Running Locally Over HTTP

Start the app in a fresh JVM (proof not yet consumed):

~~~bash
mvn spring-boot:run
~~~

Call the public endpoint:

~~~bash
curl -i http://localhost:8080/api/health
~~~

Call the protected endpoint without a proof:

~~~bash
curl -i http://localhost:8080/api/secret
~~~

Expect HTTP 401. Then use the **demo fixture**:

~~~bash
curl -i -H "X-Lab-Proof: LAB-ONE-TIME-PROOF" \
  http://localhost:8080/api/secret
~~~

Expect HTTP 200 with a body equivalent to:

~~~json
{"subject":"learner","evidenceType":"ONE_TIME_OPAQUE_PROOF"}
~~~

Send **the exact same command a second time**: HTTP 401 because `ProofStore` already consumed the proof.

Once you have executed one successful request in **the same JVM**, the next attempt must fail; to demonstrate fresh issuance in the lab, restart the process so `ProofStore` reinitializes. **This is strictly lab behavior and must never be used as a production proof-reset mechanism**; in production, consumed proofs must never reactivate on server restart.

Warning: local HTTP/`curl` is strictly for lab work. Real environments must use HTTPS, high-entropy codes, and never print raw proofs into shell history, logs, proxies, or issue trackers.

## 8. Standalone Java 17: Simulating Digest Comparison and Single-Use

To understand the single-use mechanism **without Spring Boot**, create `OneTimeProofRulesDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicBoolean;

public class OneTimeProofRulesDemo {

    static byte[] digest(String value) {
        try {
            return MessageDigest.getInstance("SHA-256")
                .digest(value.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(ex);
        }
    }

    static final class OneTimeStore {
        private final byte[] expected = digest("proof-example");
        private final AtomicBoolean used = new AtomicBoolean(false);
        private final Instant expiresAt;

        OneTimeStore(Instant createdAt) {
            this.expiresAt = createdAt.plus(Duration.ofMinutes(10));
        }

        boolean redeem(String value, Instant now) {
            return value != null
                && now.isBefore(expiresAt)
                && MessageDigest.isEqual(expected, digest(value))
                && used.compareAndSet(false, true);
        }
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-06T00:00:00Z");
        OneTimeStore store = new OneTimeStore(now);

        System.out.println("wrong=" + store.redeem("bad", now));
        System.out.println("first=" + store.redeem("proof-example", now));
        System.out.println("replay=" + store.redeem("proof-example", now));

        OneTimeStore expired = new OneTimeStore(now);
        System.out.println("expired=" +
            expired.redeem("proof-example", now.plusSeconds(601)));
    }
}
~~~

Run:

~~~bash
javac --release 17 OneTimeProofRulesDemo.java
java OneTimeProofRulesDemo
~~~

**Exact stdout:**

~~~text
wrong=false
first=true
replay=false
expired=false
~~~

This code intentionally uses a fixed `proof-example` **solely for easy execution**, never as a real security credential. `AtomicBoolean` is safe only within a single JVM; multi-replica deployments require consistent shared storage/transactions.

## 9. Why Not Use a Filter That Checks Raw Headers and Calls setAuthenticated(true)?

A common mistake:

~~~java
// ANTI-PATTERN, never use in production!
if ("some-secret".equals(request.getHeader("X-Proof"))) {
    var result = UsernamePasswordAuthenticationToken.authenticated(
        request.getHeader("X-User"),
        null,
        List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));
    SecurityContextHolder.getContext().setAuthentication(result);
}
~~~

Problems:

- The server trusts the client-supplied username and role.
- The secret is hardcoded and compared naively, risking source leaks.
- No TTL, purpose, account binding, or replay protection.
- No rate limiting, auditing, or lifecycle controls.
- No dedicated provider to unit-test or swap proof verification safely.
- Easy to confuse providers and skip state checks.
- If placed too late in the security chain, authorization may have already executed.
- Risk of failing to clear context properly when servlet threads are reused.

**The lab design** separates the filter (transport), manager (orchestration), provider (decision), store (proof state), and authorization (policy enforcement) so every layer can be tested independently.

## 10. Why Choose OncePerRequestFilter and Where to Place It?

`OncePerRequestFilter` is a Spring Web abstraction ensuring a filter runs once per request dispatch per its semantics. Inside Spring Security:

- Must run **after `SecurityContextHolderFilter` prepares the context** and before authorization.
- Can be placed before `UsernamePasswordAuthenticationFilter` (a registered order anchor) or per filter-ordering guidance.
- Never put `@Component` on the filter **while also** adding it via `HttpSecurity.addFilterBefore/After`, because Spring Boot auto-registers Servlet filter beans separately, causing **double execution**.
- The filter should only extract the proof, wrap an untrusted token, and call the manager.
- Authentication failures must be handled explicitly; exceptions thrown before `ExceptionTranslationFilter` **must not be assumed** to convert into 401 automatically without explicit failure handling.
- On success, set a fresh `SecurityContext` and clear it after the request to prevent leaking authentication across requests.
- For stateless APIs, do not save the context; subsequent requests must bring fresh evidence or an exchanged credential.
- If implementing session-creating login, add `SessionAuthenticationStrategy` and `SecurityContextRepository.saveContext(...)` per Spring Security 6, not merely `SecurityContextHolder.setContext(...)`.

**Fixing the filter chain line:** the final `addFilterBefore(...)` call must use **`UsernamePasswordAuthenticationFilter.class`** as its anchor, not an Authentication token class. Confusing a "token" with a "filter" is a common compile error.

## 11. Stateless and CSRF: Never Copy Configs Blindly

In the lab:

- The evidence-handling endpoint is **GET**.
- Credentials travel in an **explicit client-sent header**, not an auto-sent HTTP cookie.
- `NullSecurityContextRepository` saves no authenticated context.
- No browser login session is created.
- Therefore, the demo may disable CSRF on **this specific security chain**.

When expanding into a web app with cookie-based sessions, CSRF remains essential for POST login, logout, and state changes. Never apply a blanket "REST APIs don't need CSRF" across all architectures.

If adding a POST `/api/proof/redeem` endpoint to exchange a proof for a cookie:

1. Identify which credentials the browser sends automatically.
2. Block CSRF/login CSRF per threat model.
3. Build the authenticated context only after proof verification.
4. Call `SessionAuthenticationStrategy` to mitigate fixation and enforce session policies.
5. Call `SecurityContextRepository.saveContext(context, request, response)` to persist the session.
6. Issue cookies with appropriate `Secure`, `HttpOnly`, and `SameSite` flags.
7. Invalidate the one-time proof in a DB transaction before issuing the session, accounting for races/retries.
8. Audit, limit concurrent sessions, and support logout/revocation.

**Never** store the raw proof in the session, response body, or success-event payloads.

## 12. Extending to Other Evidence Types

| Evidence | Custom Input Token | What Provider Must Verify |
| --- | --- | --- |
| Opaque one-time voucher | Custom `ProofAuthenticationToken` | Entropy, digest, TTL, account binding, single use |
| TOTP | Custom OTP token, usually an **additional factor** | Enrolled secret, time step, replay/rate limit, MFA state |
| HMAC challenge response | Challenge token + signature/HMAC | Nonce, key binding, timestamp/audience, anti-replay |
| mTLS client certificate | X.509 or pre-auth token | TLS chain, CA trust, revocation, subject mapping |
| WebAuthn/passkey | Appropriate WebAuthn tokens/ceremonies | Challenge, RP ID, origin, signature, UV, credential binding |
| Third-party signed assertion | Proper SAML/OIDC/JWT validation | Issuer, audience, signature, time, nonce/state, policy |
| Hardware device attestation | Custom attestation token | Certificate chain/vendor trust, challenge freshness, device binding |

**Prefer framework/standard protocols** for OAuth2/OIDC/SAML/WebAuthn/X.509 instead of inventing custom crypto or authentication protocols. Custom providers fit genuinely bespoke evidence with independently reviewable and testable verification logic.

### 12.1. An Opaque Voucher Is Not Phishing-Resistant

The lab proof is merely a bearer secret. It can be phished, stolen by malware, or copied before redemption. If **phishing-resistant authentication** is required, use an origin/RP-bound cryptographic challenge/response such as standard WebAuthn—never call an OTP or one-time voucher a passkey.

### 12.2. Custom Factors Should Usually Be Step-Up, Not Standalone Login

If building MFA, validating a single OTP **must never yield a fully authenticated user** when policy requires both password and OTP. Model the verified primary factor, freshness, challenge-bound OTP, session binding, and MFA-aware authorization explicitly. Never let a simple one-time code become a weaker login path than passwords/passkeys.

## 13. Vulnerabilities You Must Actively Prevent

| Risk | Scenario | Mitigation |
| --- | --- | --- |
| **Principal spoofing** | Client sends `X-User: admin` | Resolve subject from verified store; never trust headers |
| **Role escalation** | Client sends `role=ADMIN` | Derive authorities solely from server policy |
| **Replay** | Submitting a valid proof multiple times | Atomic consume, TTL, purpose binding |
| **Race condition** | Two parallel requests hit two replicas | Distributed transaction / conditional update |
| **Guessing** | Short, predictable proofs | CSPRNG ≥128 bits entropy, rate limits, no enumeration |
| **Leakage** | Codes in URLs, logs, APM | Header over HTTPS; header allowlist/redaction |
| **Stolen bearer proof** | Credential copied before use | TLS, short TTL, strict audience, device/risk context |
| **Confused deputy** | Proof issued for service A accepted by B | Audience/service binding |
| **Account takeover** | Low-assurance proof grants full login | Step-up/assurance policies, no downgrade |
| **Revocation gap** | Account locked yet proof still works | Check active account/version at redemption time |
| **DoS** | Attacker floods proof guesses | Rate limit per source/account risk, metrics |
| **Session leak** | Reused thread carries old SecurityContext | Clear context, `NullSecurityContextRepository` when stateless |
| **Filter double-registration** | Boot registers Filter bean outside chain | Never `@Component` filters added via `addFilterBefore` |
| **Wrong chain/matcher** | Custom proof API accidentally `permitAll` | Default `denyAll`, test security matchers |
| **Information leakage** | Responses distinguish unknown/expired/used | HTTP 401 + generic message; categorize in internal audit |
| **Test backdoor** | Fixed fixture accidentally ships to prod | Profile/env gating, external secret issuance |

### 13.1. Proof Issuance Must Be Protected Separately

The practice project **has no `/issue-proof` endpoint**, because issuing codes to users **is a separate security problem**. Production should generate codes via `SecureRandom`, for example 32 bytes Base64URL-encoded:

~~~java
// Java 17 fragment, not a complete token-issuance API.
byte[] random = new byte[32];
new java.security.SecureRandom().nextBytes(random);
String rawProof = java.util.Base64.getUrlEncoder()
    .withoutPadding().encodeToString(random);
~~~

Never store plaintext codes in the database after issuance; deliver them only to authenticated subjects over trusted channels. If the DB leaks, digests of high-entropy codes resist brute force, though storage and access still require protection.

### 13.2. Header Parsing and Request Smuggling

`X-Lab-Proof` needs character and length bounds. In production, also decide how to handle requests with **multiple headers of the same name**, comma-joined values, or proxy case/whitespace normalization; reject ambiguity rather than concatenating secrets. Never trust an `X-Verified-User` header sent directly from the Internet when only an internal proxy should emit it.

Requests reaching the backend through a reverse proxy require clear trust boundaries. When trusting client certificates or pre-auth identities from a gateway, the gateway must **strip spoofed headers** from external requests before adding verified headers.

## 14. ProviderManager, Provider Order, and Authentication Events

`ProviderManager` normally tries `AuthenticationProvider` instances in order:

- If `supports(type)=false`, skip the provider.
- If the provider returns `null`, try the next provider.
- If the provider returns a non-null authenticated result, stop and return it.
- On standard `BadCredentialsException`, the manager may continue to subsequent providers supporting the same token; design so it **cannot fall back to a weaker mechanism** for the same account.
- On critical account-status/service exceptions, the manager stops early; never use fallback to bypass locked/disabled accounts.
- If no provider handles the token, `ProviderNotFoundException` is thrown.
- `ProviderManager` normally calls `eraseCredentials()` on trusted results implementing `CredentialsContainer` before returning.

**Important note on events:** a manually constructed `new ProviderManager(provider)` does not automatically attach an application event publisher. To emit `AuthenticationSuccessEvent` or failure events, call `manager.setAuthenticationEventPublisher(authenticationEventPublisher)` with the proper bean. Avoid emitting duplicate events from both provider/filter and manager.

Example fragment in a configuration having the publisher bean:

~~~java
ProviderManager manager = new ProviderManager(proofProvider);
manager.setAuthenticationEventPublisher(authenticationEventPublisher);
~~~

Never log raw `ProofAuthenticationToken` objects or `AuthenticationException.getMessage()` values that might carry secrets; audits should log event type, timestamp, proof type, protected internal account ID, outcome, and correlation ID.

## 15. Additional Tests for Production

### 15.1. Essential Unit Tests

- [ ] `supports` returns true for the custom token and false for `UsernamePasswordAuthenticationToken`/JWT tokens.
- [ ] Valid proof returns `Authentication` with `authenticated=true`, right principal, and minimal authorities.
- [ ] Invalid proof throws `BadCredentialsException`, never `return null`.
- [ ] Forged already-authenticated input tokens are rejected.
- [ ] No credentials retained on authenticated tokens, no inputs logged.
- [ ] Empty/null/oversized proofs are rejected.
- [ ] Expired proofs per server clock fail.
- [ ] Replaying a proof after success fails.
- [ ] Concurrent multi-threaded replay succeeds for at most one request.

### 15.2. HTTP/Security Integration

- [ ] Public health endpoint works without a proof.
- [ ] Protected resources with missing/invalid proofs return 401.
- [ ] Valid proof populates `SecurityContext` properly and passes authorization.
- [ ] Proof cannot be reused for a second access.
- [ ] Requests retain no authenticated session after completion.
- [ ] Unlisted endpoints are not left exposed outside the security chain.
- [ ] Proof never appears in responses, logs, traces, or metrics.
- [ ] If filter order changes, verify the provider still runs before authorization.
- [ ] If browser cookies are introduced, re-enable appropriate CSRF/session policies.

### 15.3. Multi-Instance and Operations

- [ ] Two replicas receiving the same proof commit at most one.
- [ ] DB/Redis outages fail closed, never returning success.
- [ ] Clock skew/bounds evaluated; TTL checked against server time.
- [ ] Consumed/revoked state never "resurrects" after restarts.
- [ ] Rate limiting, request size limits, and WAF/gateway controls are tested.
- [ ] Issuer/audience/purpose bindings verified; locked accounts cannot authenticate.
- [ ] Expired proof cleanup, retention, and auditing exist.
- [ ] Categorized failure metrics exist without using raw proofs as labels.
- [ ] Secrets in storage/backups/CI/logging are protected.
- [ ] Threat modeling, penetration testing, and code review completed before production.

## 16. Troubleshooting Common Failures

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| `ProviderNotFoundException` | Wrong `supports` token class; manager missing provider | Test `supports`, check wiring and filter |
| `ClassCastException` | Provider casts wrong token type | Check `instanceof` and `supports` |
| Right header yet 401 on first call | Token already consumed, expired, or differs from fixture | Restart lab to reset fixture; never reset consumed proofs in prod |
| Valid proof returns 403 | Authentication succeeded yet lacks required authority | Check server-side authority mapping |
| Missing header does not return 401 | Endpoint `permitAll`/wrong matcher or different entry point | Default deny, test missing proof |
| No `SecurityContext` in controller | Filter placed after authorization or context cleared early | Check filter order and chain |
| Request after valid proof gets 401 | Lab is intentionally one-time + stateless | Design an explicit exchange flow if sessions are needed |
| `HttpSession` created accidentally | Repository/session policy not stateless or another filter | Inspect session creation across the chain |
| Filter invoked twice | Filter is `@Bean`/`@Component` and `addFilterBefore` | Register solely inside `SecurityFilterChain` |
| Bad proof returns null and another provider authenticates | Wrong fallback semantics | Throw `BadCredentialsException`, restrict fallback |
| Provider succeeds from `userId` header | Broken trust boundary | Load subject from verified store |
| `ROLE_ADMIN` sent by client | Authority injection | Derive roles from server policy |
| Race between two replicas | `AtomicBoolean` is JVM-local only | Centralized transaction/compare-and-set |
| `@WithMockUser` passes when provider is broken | Test bypasses manager/filter | Send real requests with custom proof |
| Logout/browser flow breaks after adding sessions | Missing context save, fixation, or CSRF | Use proper `SessionAuthenticationStrategy`/`Repository` |
| Putting token in query URL to debug | Logs/referrers/history leak secrets | Use HTTPS headers, redaction, safe telemetry |

## 17. Self-Check Questions

1. Why create a dedicated `ProofAuthenticationToken` instead of stuffing the code into a username/password token?
2. What does `supports(Class<?>)` check, and does it verify the proof value itself?
3. When should `authenticate(...)` return `null`? Why must an invalid proof not return `null`?
4. Is a one-time bearer proof phishing-resistant like WebAuthn?
5. Why must clients never supply the principal or authorities in an authenticated result?
6. Why should only the provider construct trusted tokens?
7. Can a one-time proof be reused across multiple HTTP GET calls?
8. Over what scope does `AtomicBoolean` guarantee single-use?
9. Across three replicas, how must `consumed_at` be stored to prevent races?
10. SHA-256 digests fit 256-bit random codes, yet why are they unsuitable for short passwords?
11. Why is `NullSecurityContextRepository` used in this lab?
12. Why should a custom filter not be registered twice as a Servlet Filter bean?
13. Why must the filter run before authorization?
14. How does a 401 for missing/invalid proof differ from a 403 for insufficient authority?
15. When converting the flow to cookie-based login, what session fixation/CSRF/`saveContext` pieces must be added?
16. Why test HTTP through filters rather than relying solely on `@WithMockUser`?
17. Which attacks do issuer, audience, and purpose bindings prevent?
18. Should you use a custom provider or standard protocols for OIDC, SAML, and WebAuthn?
19. How do you ensure revoked/used proofs cannot reactivate after a restart?
20. If the proof-verification DB loses connectivity, should behavior be fail-open or fail-closed?

**Conclusion:** an `AuthenticationProvider` for custom evidence must **separate untrusted evidence from trusted results**, declare exact token types in `supports(...)`, validate proofs in `authenticate(...)`, return server-derived trusted principals/authorities, handle invalid/expired/replayed inputs safely, and wire filter, manager, and security context in the proper order. This single-use lab teaches the contract; production demands high-entropy issuance, distributed atomic state, rate limiting, session/assurance management, and auditing.

## 18. Official References

- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — AuthenticationProvider Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html)
- [Spring Security 6.5 — ProviderManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html)
- [Spring Security 6.5 — AbstractAuthenticationToken Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AbstractAuthenticationToken.html)
- [Spring Security 6.5 — Servlet Architecture, Adding Filters](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — NullSecurityContextRepository](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/NullSecurityContextRepository.html)
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Boot 3.5 — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html)
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
