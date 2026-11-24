# Unit Testing a Provider Independently Before Wiring It into the HTTP Chain

## 1. Lesson Objectives

In Spring Security, `AuthenticationProvider` is where credentials are verified and where the decision is made on whether to produce a trusted `Authentication`. When writing a custom provider for an API key, OTP, internal account, or specialized mechanism, you should **test the provider directly before placing it into a SecurityFilterChain**. This isolation separates credential-handling bugs from filter, HTTP status, session, CSRF, or URL matcher bugs.

After this lesson you will know how to:

1. Clearly separate the responsibilities of **AuthenticationProvider**, **ProviderManager**, and **Servlet HTTP** components.
2. Design a JUnit 5 test suite covering both success and rejection branches, using **unauthenticated** inbound `Authentication` objects.
3. Use an in-memory fake store to run real provider logic without needing a web server or database.
4. Test `supports()`, `authenticate()`, account/key status, principal, authorities, exceptions, and credential protection.
5. Test `ProviderManager` minimally, then plan `MockMvc` testing after integrating the HTTP chain.

The example uses **Java 17+**, **Spring Security 6.5.x**, **JUnit Jupiter 5**, and Gradle. The files in sections 4–5 run as a regular Java Gradle project; `@SpringBootTest` and servlet containers are not used in the provider test suite.

## 1. Identifying the Boundary to Test

An HTTP request typically travels through this chain:

~~~text
HTTP request
  |
  +-- SecurityFilterChain
        |
        +-- Filter reads credentials from header/body/cookie
        +-- Creates untrusted Authentication token
        |
        v
     AuthenticationManager (ProviderManager)
        |
        +-- supports(token.getClass()) -> selects provider
        |
        v
     Custom AuthenticationProvider
        |
        +-- validates input and reads server-controlled data
        +-- checks credentials and account/key status
        +-- determines principal and GrantedAuthority from server
        |
        +-- failure -> AuthenticationException
        +-- success -> authenticated Authentication
        |
        v
     Filter places result into SecurityContext
        |
        +-- AuthenticationEntryPoint/FailureHandler for errors
        +-- AuthorizationFilter evaluates permissions
        +-- Controller handles request
~~~

**Provider unit tests** only need an input token, the real provider, and a test data store. When these tests pass, you know the core authentication branches adhere to the contract. They do not yet prove that the HTTP filter reads the right header or that clients receive 401/403. That is a separate test phase after integration.

### Three Test Levels to Distinguish

| Level | Real objects to execute | What bugs does it catch? | Needs HTTP? |
| --- | --- | --- | --- |
| **Provider unit test** | Token, `AuthenticationProvider`, verification and authority-mapping logic | Valid/invalid credentials, disabled account, excessive privileges, un-erased secrets | No |
| **Manager test** | `ProviderManager` and real provider | Broken `supports`, missing provider, misrouted provider coordination | No |
| **HTTP integration / MockMvc** | Security filter chain, authentication mechanism, entry point, authorization | Unread header, wrong filter order, 401/403, session/context/CSRF | Servlet layer yes, no real port needed |

For instance, if an HTTP request with a valid key gets 401, the cause could be an unregistered filter, wrong header name, `SecurityFilterChain` not matching the URL, provider rejection, or wrong entry point. An independent provider unit test rules out or confirms **one** major cause.

## 2. The AuthenticationProvider Contract

Primary interface:

~~~java
Authentication authenticate(Authentication authentication)
    throws AuthenticationException;

boolean supports(Class<?> authenticationType);
~~~

In `org.springframework.security.authentication.AuthenticationProvider`:

- **supports(Class<?>)** answers whether the provider **can consider** that token type. It does not check passwords, API keys, or permissions.
- **authenticate(Authentication)** returns an authenticated `Authentication` on success, and **throws AuthenticationException** when credentials are invalid or account status disallows login.
- A provider may **return null** if it cannot handle/decide on the token so the manager can try another provider per contract. Never arbitrarily return null when credentials were actually determined to be invalid.
- **ProviderManager** selects the appropriate provider. If no provider can support the token, the manager may throw `ProviderNotFoundException`.

Examples:

| Input to provider | Outcome to test |
| --- | --- |
| Right token type, valid and active key | `authenticated=true`, principal and authorities come from server |
| Right token type, wrong secret | `BadCredentialsException` |
| Right token type, nonexistent client ID | `BadCredentialsException` with safe message |
| Right token type, disabled key | `DisabledException` or policy-defined exception |
| Malformed token | Controlled rejection; no leaked parse errors or secrets |
| Different token type | `supports=false`, provider does not accept processing |
| Input token calls `setAuthenticated(true)` itself | Cannot be elevated to trusted |
| Successful result | Sensitive credentials are not retained unnecessarily |

**Principal** is the verified identity; **authorities** are effective permissions fetched from a server-controlled source. Strings in client-supplied headers or JSON **do not prove** the corresponding user or roles. Therefore tests must assert that authorities never come from self-asserted inputs.

### Why Avoid HTTP Statuses in Provider Tests?

`AuthenticationProvider` does not receive `HttpServletResponse`. It should report success or throw `AuthenticationException`; the filter, `AuthenticationEntryPoint`, and `AccessDeniedHandler` decide the HTTP response. Testing “wrong key returns 401” belongs to the HTTP layer. Testing “wrong key throws BadCredentialsException” belongs to the provider layer.

## 3. Designing a Test Matrix Before Coding

| Test | Condition | Key assertion |
| --- | --- | --- |
| U1 | Valid key, enabled=true | Result differs from input; true; right principal; only server-granted scopes |
| U2 | Wrong secret | `BadCredentialsException`; no trusted result |
| U3 | Nonexistent ID | `BadCredentialsException`; does not disclose ID/secret |
| U4 | Disabled key | Rejected even with correct secret |
| U5 | Null/blank/bad delimiter/too long | Safely rejected and credentials erased |
| U6 | Unsupported token | supports=false; authenticate does not handle it |
| U7 | Input calls `setAuthenticated(true)` | Throws error; state remains false |
| U8 | Valid key | Result retains no raw secret; input is erased |
| U9 | Provider executed | Does not set Authentication in `SecurityContextHolder` itself |
| M1 | ProviderManager contains provider | Calls provider and returns trusted result |
| M2 | Manager has only API key provider but gets password token | `ProviderNotFoundException` |

Test both **happy paths and negative paths**. A provider that accepts every secret can pass a single success test; negative tests with wrong, missing, disabled, and malformed keys are what expose vulnerabilities.

For time-bounded data, add tests for expired/revoked keys and an injected `Clock` to fix time. For tenants, add membership tests and least-privilege checks. Avoid hitting real databases or wall-clock time when the goal is verifying provider algorithms.

## 4. Gradle Project with a Real Provider, No HTTP Dependencies

The example uses an API key formatted as `clientId.secret`. `clientId` looks up the record, and `secret` is hashed and matched against the server-stored digest. The server-side record defines account, enabled, and scopes; the client cannot pick its own principal or authorities.

Create `settings.gradle`:

~~~groovy
rootProject.name = 'provider-unit-test-demo'
~~~

Create `build.gradle`:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'

    testImplementation platform('org.junit:junit-bom:5.12.2')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

This is a standalone Java project for running tests. When moving the logic into a Spring Boot application, let the application's BOM manage compatible Spring Security and JUnit versions instead of upgrading a single library independently.

### 4.1. Provider Code

Create file `src/main/java/example/auth/ApiKeyAuthentication.java`:

~~~java
package example.auth;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public final class ApiKeyAuthentication {

    private ApiKeyAuthentication() {
    }

    // Unauthenticated request token holding only the credential.
    public static final class ApiKeyRequestToken
            extends AbstractAuthenticationToken {

        private String presentedKey;

        public ApiKeyRequestToken(String presentedKey) {
            super(List.of());
            this.presentedKey = presentedKey;
            super.setAuthenticated(false);
        }

        @Override
        public Object getPrincipal() {
            return null;
        }

        @Override
        public Object getCredentials() {
            return presentedKey;
        }

        @Override
        public void setAuthenticated(boolean authenticated) {
            if (authenticated) {
                throw new IllegalArgumentException(
                    "Input token cannot authenticate itself"
                );
            }
            super.setAuthenticated(false);
        }

        @Override
        public void eraseCredentials() {
            super.eraseCredentials();
            presentedKey = null;
        }
    }

    // Server-controlled record.
    public record KeyRecord(
            String accountId,
            byte[] secretDigest,
            boolean enabled,
            List<String> scopes) {

        public KeyRecord {
            Objects.requireNonNull(accountId, "accountId");
            secretDigest = Objects.requireNonNull(
                secretDigest, "secretDigest"
            ).clone();
            scopes = List.copyOf(scopes);
        }

        @Override
        public byte[] secretDigest() {
            return secretDigest.clone();
        }
    }

    @FunctionalInterface
    public interface KeyStore {
        Optional<KeyRecord> findById(String clientId);
    }

    public static final class Provider implements AuthenticationProvider {

        private final KeyStore store;

        public Provider(KeyStore store) {
            this.store = Objects.requireNonNull(store);
        }

        @Override
        public boolean supports(Class<?> type) {
            return ApiKeyRequestToken.class.isAssignableFrom(type);
        }

        @Override
        public Authentication authenticate(Authentication authentication) {
            if (!(authentication instanceof ApiKeyRequestToken request)) {
                return null; // Other token type: this provider does not handle it.
            }

            try {
                if (request.isAuthenticated()) {
                    throw badCredentials();
                }

                String raw = (String) request.getCredentials();
                if (raw == null || raw.isBlank() || raw.length() > 512) {
                    throw badCredentials();
                }

                int dot = raw.indexOf('.');
                if (dot < 1 || dot == raw.length() - 1) {
                    throw badCredentials();
                }

                String id = raw.substring(0, dot);
                String secret = raw.substring(dot + 1);
                if (!id.matches("[A-Za-z0-9_-]{1,64}")) {
                    throw badCredentials();
                }

                KeyRecord record = store.findById(id)
                    .orElseThrow(ApiKeyAuthentication::badCredentials);

                if (!record.enabled()) {
                    throw new DisabledException("API key disabled");
                }

                byte[] providedDigest = digest(secret);
                byte[] expectedDigest = record.secretDigest();

                boolean accepted;
                try {
                    accepted = MessageDigest.isEqual(
                        providedDigest, expectedDigest
                    );
                } finally {
                    Arrays.fill(providedDigest, (byte) 0);
                    Arrays.fill(expectedDigest, (byte) 0);
                }

                if (!accepted) {
                    throw badCredentials();
                }

                List<GrantedAuthority> authorities = record.scopes()
                    .stream()
                    .map(scope -> (GrantedAuthority)
                        new SimpleGrantedAuthority("SCOPE_" + scope))
                    .toList();

                // Create trusted token ONLY after credentials are valid.
                return UsernamePasswordAuthenticationToken.authenticated(
                    record.accountId(),
                    null,
                    authorities
                );
            } finally {
                // Clear reference to secret on the input token.
                request.eraseCredentials();
            }
        }
    }

    private static BadCredentialsException badCredentials() {
        return new BadCredentialsException("Invalid API key");
    }

    private static byte[] digest(String secret) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(
                secret.getBytes(StandardCharsets.UTF_8)
            );
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }
}
~~~

**Design explanation:**

- `ApiKeyRequestToken` takes no roles, contains no verified principal, and always starts with `authenticated=false`. Its setter blocks self-elevation to true.
- `supports()` only asserts that the provider knows how to handle `ApiKeyRequestToken`; it does not authorize accepting every token of that type.
- The provider validates format, looks up the record, checks key status, and then compares digests. On failure, it **throws an exception**; it never builds an `authenticated=false` token pretending to be a success result.
- The result is a **new** token with account and scopes from the record. All authorities are constructed server-side.
- `KeyRecord` clones the digest and copies scopes to prevent unintended mutation from fixtures or adapters.
- `finally` invokes `eraseCredentials()`. Since `String` is immutable, clearing the token's reference **does not guarantee wiping the entire secret from JVM memory**; avoid logging raw secrets and limit their lifetime.
- `MessageDigest.isEqual` compares digests. Real API keys require high-entropy generated secrets, proper key storage, rotation/revocation, rate limiting, and failure monitoring. **Never use plain SHA-256 as a replacement for PasswordEncoder on user passwords.**

Never let HTTP-handling code call `UsernamePasswordAuthenticationToken.authenticated(...)` directly with a principal or roles taken from JSON; the trusted factory does not verify credentials itself. Use it only where the provider has performed actual verification.

## 5. Writing Unit Tests Without Starting a Spring Context

Create file `src/test/java/example/auth/ApiKeyAuthenticationProviderTest.java`:

~~~java
package example.auth;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.ProviderNotFoundException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.junit.jupiter.api.Assertions.*;

class ApiKeyAuthenticationProviderTest {

    private ApiKeyAuthentication.Provider provider;

    @BeforeEach
    void setUp() {
        Map<String, ApiKeyAuthentication.KeyRecord> records = Map.of(
            "client-a",
            new ApiKeyAuthentication.KeyRecord(
                "svc-reports",
                digestForFixture("correct-secret"),
                true,
                List.of("reports.read")
            ),
            "blocked",
            new ApiKeyAuthentication.KeyRecord(
                "svc-blocked",
                digestForFixture("blocked-secret"),
                false,
                List.of("reports.read")
            )
        );

        ApiKeyAuthentication.KeyStore fakeStore =
            id -> Optional.ofNullable(records.get(id));

        provider = new ApiKeyAuthentication.Provider(fakeStore);
        SecurityContextHolder.clearContext();
    }

    @Test
    void validKeyProducesTrustedPrincipalAndServerScopes() {
        var input = new ApiKeyAuthentication.ApiKeyRequestToken(
            "client-a.correct-secret"
        );

        assertFalse(input.isAuthenticated());
        assertNull(input.getPrincipal());
        assertTrue(input.getAuthorities().isEmpty());

        Authentication result = provider.authenticate(input);

        assertNotNull(result);
        assertNotSame(input, result);
        assertTrue(result.isAuthenticated());
        assertEquals("svc-reports", result.getName());
        assertEquals(
            List.of("SCOPE_reports.read"),
            result.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .toList()
        );
        assertNull(result.getCredentials());
        assertNull(input.getCredentials());
        assertFalse(input.isAuthenticated());

        // Provider does not set SecurityContext itself.
        assertNull(
            SecurityContextHolder.getContext().getAuthentication()
        );
    }

    @Test
    void wrongSecretIsRejectedAndCredentialIsCleared() {
        var input = new ApiKeyAuthentication.ApiKeyRequestToken(
            "client-a.wrong-secret"
        );

        BadCredentialsException error = assertThrows(
            BadCredentialsException.class,
            () -> provider.authenticate(input)
        );

        assertEquals("Invalid API key", error.getMessage());
        assertNull(input.getCredentials());
        assertFalse(input.isAuthenticated());
    }

    @Test
    void unknownIdIsRejectedWithoutDisclosingSecret() {
        var input = new ApiKeyAuthentication.ApiKeyRequestToken(
            "unknown.any-secret"
        );

        BadCredentialsException error = assertThrows(
            BadCredentialsException.class,
            () -> provider.authenticate(input)
        );

        assertEquals("Invalid API key", error.getMessage());
        assertNull(input.getCredentials());
    }

    @Test
    void disabledKeyIsRejectedEvenWhenSecretMatches() {
        var input = new ApiKeyAuthentication.ApiKeyRequestToken(
            "blocked.blocked-secret"
        );

        assertThrows(
            DisabledException.class,
            () -> provider.authenticate(input)
        );
        assertNull(input.getCredentials());
    }

    @Test
    void malformedInputIsRejectedSafely() {
        List<String> badInputs = List.of(
            "",
            "client-a",
            ".secret",
            "client-a.",
            "bad id.secret",
            "client-a." + "x".repeat(600)
        );

        for (String raw : badInputs) {
            var input = new ApiKeyAuthentication.ApiKeyRequestToken(raw);
            assertThrows(
                BadCredentialsException.class,
                () -> provider.authenticate(input)
            );
            assertNull(input.getCredentials());
        }

        var nullInput = new ApiKeyAuthentication.ApiKeyRequestToken(null);
        assertThrows(
            BadCredentialsException.class,
            () -> provider.authenticate(nullInput)
        );
        assertNull(nullInput.getCredentials());
    }

    @Test
    void requestTokenCannotMarkItselfAuthenticated() {
        var input = new ApiKeyAuthentication.ApiKeyRequestToken(
            "client-a.correct-secret"
        );

        assertThrows(
            IllegalArgumentException.class,
            () -> input.setAuthenticated(true)
        );
        assertFalse(input.isAuthenticated());
        assertTrue(input.getAuthorities().isEmpty());
    }

    @Test
    void supportsOnlyItsTokenType() {
        assertTrue(provider.supports(
            ApiKeyAuthentication.ApiKeyRequestToken.class
        ));
        assertFalse(provider.supports(
            UsernamePasswordAuthenticationToken.class
        ));
        assertNull(provider.authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                "someone", "password"
            )
        ));
    }

    @Test
    void providerManagerCallsTheRealProvider() {
        ProviderManager manager = new ProviderManager(List.of(provider));

        Authentication result = manager.authenticate(
            new ApiKeyAuthentication.ApiKeyRequestToken(
                "client-a.correct-secret"
            )
        );

        assertTrue(result.isAuthenticated());
        assertEquals("svc-reports", result.getName());
        assertNull(result.getCredentials());
    }

    @Test
    void providerManagerRejectsUnsupportedTokenType() {
        ProviderManager manager = new ProviderManager(List.of(provider));

        assertThrows(
            ProviderNotFoundException.class,
            () -> manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "someone", "password"
                )
            )
        );
    }

    private static byte[] digestForFixture(String secret) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(
                secret.getBytes(StandardCharsets.UTF_8)
            );
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(ex);
        }
    }
}
~~~

### 5.1. What Makes This Test Suite Meaningful?

**Not mocking the provider:** `provider.authenticate` is real code, from parsing to digest comparison and authority mapping. `fakeStore` merely replaces the database/secret store; data fixtures are explicit and free of I/O. If you mock `provider.authenticate` to return a canned success token, you have not tested the provider.

**Checking both input and output:** input starts with `false`, null principal, empty authorities; result is a **different object**, `true`, principal `svc-reports`, and only authority `SCOPE_reports.read`. There is no chance of taking `ROLE_ADMIN` from the client.

**Dedicated negative paths:** wrong secret, unknown ID, disabled, malformed. Testing only valid keys is insufficient; an “accept all” bug would still pass the happy path.

**Credential cleanup:** after both success and failure, the request token holds no reference to the raw key. The result also holds no credentials. This is an assertion on reference lifecycles, not a test of physically wiping data from the heap.

**Separation of responsibilities:** tests confirm the provider does not set `SecurityContextHolder` itself. The filter/controller is what attaches Authentication to the request after the manager succeeds.

**Real manager:** the final two tests invoke a real `ProviderManager`; distinguishing supported tokens from `ProviderNotFoundException` for other token types.

The tests do not use Mockito, `@SpringBootTest`, `@WebMvcTest`, or `MockMvc` because that is not yet the layer being verified.

### 5.2. Running the Tests

From the directory containing `build.gradle` and the Gradle wrapper:

~~~bash
./gradlew test
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

If the project lacks a wrapper but Gradle is installed, use `gradle test`. You can run the single class:

~~~bash
./gradlew test --tests example.auth.ApiKeyAuthenticationProviderTest
~~~

The test snippet above defines **9 `@Test` methods**; the malformed case also loops over multiple strings inside one method. On success, Gradle finishes with **BUILD SUCCESSFUL**; the HTML report is typically at `build/reports/tests/test/index.html`.

**Actual test results** must be confirmed by running the Gradle command in your project environment; the lesson content illustrates test methods and expected outcomes, not proof that the app is already HTTP-integrated.

### 5.3. Running a Single Case When Failures Occur

~~~bash
./gradlew test --tests example.auth.ApiKeyAuthenticationProviderTest.wrongSecretIsRejectedAndCredentialIsCleared
~~~

If this case fails, inspect provider logic and fixture data rather than spinning up a servlet container right away. If all provider tests pass while HTTP requests still fail, move on to testing the filter and chain configuration.

## 6. Testing ProviderManager Separately Before HTTP Integration

Direct provider tests **do not verify** whether the manager can actually select the provider. Therefore add a small test layer using the real manager:

~~~java
ProviderManager manager = new ProviderManager(List.of(provider));

Authentication result = manager.authenticate(
    new ApiKeyAuthentication.ApiKeyRequestToken(
        "client-a.correct-secret"
    )
);
~~~

`ProviderManager` relies on `supports` and `authenticate` results. If no provider handles it, it can throw `ProviderNotFoundException`.

Distinguish:

- **Right token type, wrong secret:** provider supports it but rejects via `BadCredentialsException`.
- **Different token type, no provider supports it:** configuration or token type error with `ProviderNotFoundException`.
- **Provider supports token type but returns null:** manager may try another provider. This is not the example's default way of rejecting a wrong secret.
- **Disabled key:** `DisabledException` is a status failure; when a manager has multiple providers, stop/continue behavior by exception type must be tested against the actual setup.

If the application has multiple providers, such as API key and username/password, add manager-level cases for **exact ordering**, token types, and fallback. Never confuse `supports=true` with valid credentials.

`ProviderManager` also handles erasing credentials on the authenticated result (when implementing `CredentialsContainer`) and publishing authentication events when configured. Direct provider tests do not automatically exercise these management behaviors; add manager-level tests if the application depends on them.

## 7. What Still Needs Testing When Wiring into SecurityFilterChain?

Once provider unit tests and manager tests pass, the next step is HTTP testing:

1. **Reading credentials:** does the filter read `X-API-Key` properly and handle missing, duplicate, or oversized headers?
2. **Filter chain:** does the request hit the right `SecurityFilterChain`, `securityMatcher`, and filter position?
3. **Success path:** does the filter take the result from `AuthenticationManager`, put the authenticated `Authentication` into the request's `SecurityContext`, and continue processing properly?
4. **Failure path:** does the entry point/failure handler turn `AuthenticationException` into a sensible 401 without leaking the key?
5. **Authorization:** can an authenticated token with `SCOPE_reports.read` access a read endpoint while being denied on a write endpoint requiring another scope?
6. **Lifecycle:** is SecurityContext cleared after the request without leaking into another request/thread?
7. **Session policy:** API keys are usually stateless; if an application intentionally uses sessions, you must test the repository, login/logout, and session fixation accordingly.
8. **CSRF/CORS/TLS/reverse proxy:** these are web/deployment layer and threat-model properties, not proven by provider unit tests.

Example **illustrative code inside a test class that already has MockMvc, filters, and endpoints**:

~~~java
mockMvc.perform(get("/reports")
        .header("X-API-Key", "client-a.correct-secret"))
    .andExpect(status().isOk());

mockMvc.perform(get("/reports")
        .header("X-API-Key", "client-a.wrong-secret"))
    .andExpect(status().isUnauthorized());
~~~

This snippet is not a standalone Java class. The application must configure the corresponding filter, matchers, endpoints, and test support. With Spring Boot Servlet, you typically use `spring-security-test` at the version managed by the Spring Boot BOM and `MockMvc` to run slice/integration tests.

Independent provider tests **do not need** `spring-security-web` or `spring-security-test`; add those only when actually testing HTTP.

## 8. Common Test Design Mistakes

### 8.1. Asserting Only No Exception

~~~java
assertDoesNotThrow(() ->
    provider.authenticate(
        new ApiKeyAuthentication.ApiKeyRequestToken(
            "client-a.correct-secret"
        )
    )
);
~~~

This does not verify the result: the provider could return null, return an unauthenticated token, wrong principal, or wrong authorities. Assert all fields of the trusted result on the happy path.

### 8.2. Mocking the Exact Logic Under Test

~~~java
// Illustrates a weak test when the provider is the subject under test.
when(provider.authenticate(any())).thenReturn(fakeSuccess);
~~~

This test only verifies mock configuration. Mock `KeyStore`, `Clock`, I/O services, or use controlled fakes; run the **real provider**.

### 8.3. Testing Only Valid Credentials

A buggy provider might return authenticated for both valid and invalid credentials. Negative-path tests must verify rejection, safe error messages, and that no trusted result is produced.

### 8.4. Taking Authorities from an Untrusted Request

If an input token holds self-asserted `roles` and the provider copies them straight into `GrantedAuthority`, clients can escalate their own privileges. Tests should send a request claiming high privileges while the server record grants only low privileges, then assert only server privileges are returned. The API key example above omits an inbound role field to eliminate this attack vector at the token structure itself.

### 8.5. Confusing supports with Successful Authentication

`supports(ApiKeyRequestToken.class) == true` does not prove any key is valid. It only states that the provider can inspect the token. `authenticate` logic must still genuinely verify the secret.

### 8.6. Returning null for Every Error

For a provider that determined a credential is wrong, `BadCredentialsException` is clearer than always returning null. If using multiple providers supporting the same token type, returning null can cause the manager to try another provider; fallback policies must be considered deliberately.

### 8.7. Using Wall-Clock Time or Real Databases in Unit Tests

If checking expiry, inject a fixed `Clock`. If checking lookup, fake the repository/`KeyStore`. Tests relying on sleeping, network, or external databases are slow and flaky; leave real adapters for separate integration tests.

### 8.8. Overclaiming from Green Results

Passing provider unit tests does not prove the system has HTTPS, rate limiting, CSRF, CORS, session policies, safe logging, proper `SecurityFilterChain` config, or right 401/403 behavior. You must implement tests at the next appropriate layer.

### 8.9. Testing Internals Instead of Behavior

Do not force the provider to invoke helpers in an arbitrary order if that order has no security impact. Test outcomes from inputs and defined rules. However, whether **status is checked before or after verification**, information disclosure levels, data-store query counts, and secret handling can carry security significance; test them explicitly when required.

### 8.10. Logging Raw Credentials on Test Failure

Avoid printing `Authentication.toString()`, request headers, or exceptions containing raw secrets to the console. For diagnostics, log only the error type, correlation ID, test state, and anonymized IDs. Never turn CI test logs into a store of passwords/API keys.

## 9. Test Ideas for Enterprise Providers

The API key sample is intentionally simple. When real providers support users, tenants, OTPs, devices, or third-party tokens, expand the matrix per policy:

| Topic | Cases to include |
| --- | --- |
| **Account status** | Enabled, disabled, locked, expired |
| **Credential** | Invalid, valid, revoked, expired, rotated |
| **Tenant** | User belongs to tenant A, request claims tenant B: reject |
| **Scopes/roles** | Server permissions change, request self-asserts roles: no extra grant |
| **OTP** | Valid challenge, expired, wrong code, replay, attempt limit exceeded |
| **Trust source** | Headers from reverse proxy trusted only when channel/proxy verified |
| **Data store outage** | Never fail-open to an authenticated result; controlled internal logging |
| **Multi-provider** | Ordering, null fallback, account errors, parent manager |
| **Observability** | No passwords/API keys/CSRF/session IDs leaked in logs or exceptions |

For example, expiry tests should take a fixed `Clock` rather than sleeping; credential-computation tests must use known inputs and proper encoding/verification tools. For passwords, use `PasswordEncoder.matches` against server-stored hashes rather than string comparison or direct SHA-256.

## 10. Checklist Before Wiring the Provider into HTTP

A provider is sufficiently tested in isolation when you have automated proof for:

- Input token has **isAuthenticated=false**, no trusted authorities, and cannot self-elevate.
- Valid credentials -> authenticated result, principal/authorities from server source.
- Invalid credentials, unknown, disabled, malformed -> fail safely, no trusted result.
- `supports` matches the exact token type; other token types are not mishandled.
- Result retains no raw credentials; request credentials are cleared as far as possible.
- Provider has no dependency on `SecurityContextHolder` or servlets itself.
- Real `ProviderManager` selects the provider and reports missing provider when unsupported.
- Tests are repeatable with no dependency on HTTP, real databases, network ports, or random clocks.

Afterward, wire the provider into `AuthenticationManager` and `SecurityFilterChain`, and add `MockMvc`/integration tests for filters, SecurityContext, authorization, 401/403, and request lifecycles. When a failure occurs, you will know whether it belongs to **credential verification**, **provider coordination**, or the **HTTP layer**.

## 11. Self-Check Questions

**1.** A provider unit test with a valid key returns `authenticated=true`. Have you proven the HTTP endpoint returns 200?  
**Answer:** No; filters, chains, context, and authorization need separate tests.

**2.** Why is `assertDoesNotThrow(provider.authenticate(...))` insufficient?  
**Answer:** The provider could still return null, return a false token, or grant wrong permissions.

**3.** `supports(UsernamePasswordAuthenticationToken.class)` returns false in an API key provider: does that mean the password is wrong?  
**Answer:** No; the provider does not handle that token. A manager lacking the corresponding provider may throw `ProviderNotFoundException`.

**4.** What should be faked in provider unit tests?  
**Answer:** Fake data stores or external services; run the **real provider** to test verification algorithms and authority mapping.

**5.** A user sends role `ROLE_ADMIN` in the request while the server only grants `reports.read`. What authorities should the result have?  
**Answer:** Only server-granted authorities, e.g. `SCOPE_reports.read`; never accept self-asserted roles.

**6.** Provider tests pass, yet HTTP returns 500 for a wrong API key. Where do you check first?  
**Answer:** The filter and failure handler/entry point handling `AuthenticationException`, once provider unit tests for invalid keys are confirmed passing.

**7.** Why test `ProviderManager` separately?  
**Answer:** `supports`, provider list and ordering, null results, and exceptions can make coordination behave differently from calling one provider directly.

## References

- [Spring Security 6.5 — Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — AuthenticationProvider API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html)
- [Spring Security 6.5 — ProviderManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html)
- [Spring Security 6.5 — AuthenticationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationManager.html)
- [Spring Security 6.5 — AbstractAuthenticationToken API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AbstractAuthenticationToken.html)
- [JUnit Jupiter 5.12.2 User Guide](https://docs.junit.org/5.12.2/user-guide/)
