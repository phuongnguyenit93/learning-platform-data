# Designing a Custom Authentication Token with Untrusted Input

## Lesson Objectives

In Spring Security, a request from HTTP, headers, cookies, a JSON body, or an external system can carry **self-asserted** data: a username, API key, OTP code, tenant, role, or service identifier. That data does not become proof of authentication merely because we placed it inside an object implementing the **Authentication** interface.

This lesson focuses on how to design a **custom Authentication token** for untrusted data, verify it with an **AuthenticationProvider**, and then produce an authenticated result that authorization steps can trust.

After this lesson, you will be able to:

1. Distinguish an **authentication request token** from an **authenticated result token** and explain the role of the **isAuthenticated** property.
2. Build your own token extending **AbstractAuthenticationToken** with a safe constructor, empty authorities in the input state, and a blocked **setAuthenticated(true)** method.
3. Write an **AuthenticationProvider** that reads the input token, verifies the secret against server-managed data, and returns a new token with a server-determined principal and authorities.
4. Wire the provider into **ProviderManager** and test the success flow, invalid credentials, and attempts to self-mark as trusted.
5. Recognize security pitfalls such as reading roles from JSON, trusting a client-supplied user ID, logging secrets, keeping credentials in the context, or putting a request token directly into SecurityContext.

## 1. Authentication Does Not Mean Authenticated

**Authentication** is both the data type representing an *authentication request* and the data type representing an *authenticated result*. The two states have different security meanings:

| Property | Before verification | After successful verification |
| --- | --- | --- |
| **isAuthenticated()** | **false** | **true** |
| **principal** | No trusted identity yet; may be a self-asserted username or null | Server-verified identifier/account |
| **credentials** | Secret sent for verification, e.g., API key | Should be erased or omitted if no longer needed |
| **authorities** | Empty; never accept authorities from the client | Authorities retrieved from a trusted server-side source |
| **data source** | HTTP header/body/cookie, data the caller could spoof | Result of verification through the provider and a trusted data store |
| **placed into SecurityContext?** | **No** as a logged-in identity | Yes, at the successful authentication integration point |

For example:

~~~http
GET /reports HTTP/1.1
Host: localhost:8080
X-API-Key: some-client-value
X-User: admin
X-Role: ROLE_ADMIN
~~~

Those three headers only prove that the client **sent those character strings**. The server must verify the API key or appropriate proof before inferring who is calling and what permissions they have. Never create a token with principal = **admin**, authority = **ROLE_ADMIN**, and authenticated = **true** simply because the request claims so.

When calling **AuthenticationManager.authenticate(requestToken)**, the manager forwards the token to a matching provider. The provider is responsible for transitioning from an *untrusted request* to a *trusted result* or rejecting it. HTTP-handling code must not assert identity on its own.

## 2. Processing Flow and Trust Boundary

~~~text
Untrusted source
  HTTP header / JSON / cookie / external message
       |
       v
[Validation of format, size, and presence]
       |
       v
Custom Authentication token
  isAuthenticated = false
  principal = unverified
  credentials = received secret
  authorities = []
       |
       v
AuthenticationManager (ProviderManager)
       |
       +---- selects AuthenticationProvider via supports(...)
       |
       v
AuthenticationProvider.authenticate(...)
       |
       +---- looks up server-controlled data
       +---- verifies credential
       +---- checks account status / tenant / permission scope
       |
       +---- failure --> AuthenticationException
       |
       +---- success --> creates a NEW result Authentication
                                isAuthenticated = true
                                principal = verified identity
                                credentials = null
                                authorities = authorities from server
                                       |
                                       v
                         Request SecurityContext
                                       |
                                       v
                         Authorization checks permissions
~~~

Merely passing a token through **AuthenticationManager** still does not mean the user is logged in for the HTTP request. **AuthenticationManager** returns the result; a filter/controller handles placing the result into **SecurityContextHolder**. If using sessions, you must also consider **SecurityContextRepository** and the context-saving policy. If using a stateless API, the next request must carry fresh authentication proof.

At this boundary there are two distinct concerns:

- **Authentication**: have the identity and credentials actually been verified?
- **Authorization**: is the verified identity allowed to access the resource?

A valid API key might produce an authenticated token with only **SCOPE_reports.read**; calling an endpoint that requires **SCOPE_reports.write** must still be denied.

## 3. Designing a Token with AbstractAuthenticationToken

**AbstractAuthenticationToken** belongs to package **org.springframework.security.authentication**. This class implements the common parts of **Authentication**, including authorities, authenticated state, details, and sensitive-data erasure handling.

When creating a custom token, make the invariants explicit:

- **Created from external input:** public constructors/factories must only produce **isAuthenticated() == false**.
- **Input authorities:** empty, with no way to pass arbitrary authorities from the request into the input token constructor.
- **Trusted result:** created only after successful verification inside a trusted provider or authentication mechanism; use a separate factory, preferring restricted visibility.
- **No self-elevation:** override **setAuthenticated(true)** to throw **IllegalArgumentException**. You can accept **setAuthenticated(false)** per the interface contract.
- **Secrets:** avoid putting the raw password/API key into **principal**, **details**, the token name, logs, exceptions, JSON responses, or the authenticated token.
- **Immutable verified contents:** the principal and authorities fields of the trusted result should be fixed; if permissions need updating, create a new authenticated result based on trusted verification.

Be especially careful with the two constructors/factory styles of Spring Security's built-in tokens. For example, **UsernamePasswordAuthenticationToken.unauthenticated(...)** creates an unauthenticated request, whereas **UsernamePasswordAuthenticationToken.authenticated(...)** creates a trusted result under the **caller's responsibility**. The factory that creates an authenticated token **does not verify the password itself**. If HTTP-handling code accidentally calls the trusted factory with user data, that is a logic vulnerability.

### Why Prevent Clients from Setting isAuthenticated = true?

**isAuthenticated** is part of the trust contract used by other components. A value of **true** indicates that the object has passed the application's authentication process. If a request could directly construct an authenticated token and put it into the context, it could bypass credential verification. Relying solely on the Java type **Authentication** or the presence of a principal is not enough to infer authentication.

**supports(Class<?>)** is also not a credential verification step: it only determines which *token type* a provider can handle. Actual verification must live inside **authenticate(...)**.

## 4. Runnable Example: Custom API-Key Token and AuthenticationProvider

We will build a small Java 17+ example focused on the authentication flow without needing to start a web server:

- The input is an **API key** sent by the client, treated as *untrusted*.
- **ApiKeyToken.unauthenticated(...)** creates an object with credentials but no principal/authorities yet.
- **ApiKeyProvider** checks the SHA-256 of the submitted value against a server-stored sample, using an appropriate byte-array comparison.
- If it matches, the provider creates **ApiKeyToken.verified(...)** with principal **reporting-service**, authority **SCOPE_reports.read**, and no raw API key retained.
- If it does not match, the provider throws **BadCredentialsException**. The flow issues no authenticated Authentication.
- Finally, the demo attempts to call **setAuthenticated(true)** directly on an input token and receives an error.

**Security limitations of the example:** the key **training-api-key** and the in-memory hash value are for illustration only. A real system must issue API keys with sufficient entropy using a CSPRNG, store an appropriate hash/HMAC or token verifier, manage secrets outside source code, and support revocation, rotation, and rate limiting. SHA-256 in the example does not turn a guessable key into a strong secret.

### 4.1. Gradle Project

Create a Java 17 Gradle project with **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.ApiKeyDemo'
}
~~~

The example pins Spring Security version 6.5.11 to illustrate a concrete API contract. When integrating into a Spring Boot project with a dependency-managing BOM, you should normally let the BOM select consistent versions for Spring Security components.

Create file **src/main/java/example/ApiKeyDemo.java**:

~~~java
package example;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;
import java.util.Collection;
import java.util.List;
import java.util.Objects;

import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public final class ApiKeyDemo {

    private ApiKeyDemo() {
    }

    /*
     * One token serves both phases, but only the trusted provider
     * may call the verified(...) factory on the success path.
     */
    static final class ApiKeyToken extends AbstractAuthenticationToken {

        private final String principal;
        private String rawKey;

        private ApiKeyToken(
                String principal,
                String rawKey,
                Collection<? extends GrantedAuthority> authorities,
                boolean verified) {
            super(authorities);
            this.principal = principal;
            this.rawKey = rawKey;
            // Call on superclass so setAuthenticated(true) stays closed
            // to code holding the input token.
            super.setAuthenticated(verified);
        }

        public static ApiKeyToken unauthenticated(String incomingKey) {
            if (incomingKey == null || incomingKey.isBlank()) {
                throw new IllegalArgumentException("API key must be present");
            }
            return new ApiKeyToken(null, incomingKey, List.of(), false);
        }

        // Non-public trusted factory; called by the provider AFTER verification.
        private static ApiKeyToken verified(
                String accountId,
                Collection<? extends GrantedAuthority> authorities) {
            Objects.requireNonNull(accountId, "accountId");
            Objects.requireNonNull(authorities, "authorities");
            return new ApiKeyToken(accountId, null, authorities, true);
        }

        @Override
        public Object getPrincipal() {
            return principal;
        }

        @Override
        public Object getCredentials() {
            return rawKey;
        }

        @Override
        public void setAuthenticated(boolean authenticated) {
            if (authenticated) {
                throw new IllegalArgumentException(
                    "Cannot trust input token via setAuthenticated(true)"
                );
            }
            super.setAuthenticated(false);
        }

        @Override
        public void eraseCredentials() {
            super.eraseCredentials();
            rawKey = null;
        }
    }

    static final class ApiKeyProvider implements AuthenticationProvider {

        // Digest of the sample key, computed from server-held data.
        private final byte[] expectedDigest;

        ApiKeyProvider(String configuredKey) {
            this.expectedDigest = sha256(configuredKey);
        }

        @Override
        public Authentication authenticate(Authentication authentication) {
            if (!(authentication instanceof ApiKeyToken token)) {
                return null; // Other providers can handle other tokens.
            }

            try {
                if (token.isAuthenticated()) {
                    throw new BadCredentialsException("Invalid API key");
                }

                String suppliedKey = (String) token.getCredentials();
                if (suppliedKey == null) {
                    throw new BadCredentialsException("Invalid API key");
                }

                byte[] suppliedDigest = sha256(suppliedKey);
                boolean matches;
                try {
                    matches = MessageDigest.isEqual(
                        suppliedDigest, expectedDigest
                    );
                } finally {
                    Arrays.fill(suppliedDigest, (byte) 0);
                }

                if (!matches) {
                    throw new BadCredentialsException("Invalid API key");
                }

                // Principal and authorities come from the server, NOT from input.
                return ApiKeyToken.verified(
                    "reporting-service",
                    List.of(new SimpleGrantedAuthority("SCOPE_reports.read"))
                );
            } finally {
                // Do not let the request token retain credentials longer than needed.
                token.eraseCredentials();
            }
        }

        @Override
        public boolean supports(Class<?> authenticationType) {
            return ApiKeyToken.class.isAssignableFrom(authenticationType);
        }
    }

    private static byte[] sha256(String value) {
        try {
            return MessageDigest.getInstance("SHA-256")
                .digest(value.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }

    public static void main(String[] args) {
        ProviderManager manager = new ProviderManager(List.of(
            new ApiKeyProvider("training-api-key")
        ));

        ApiKeyToken request = ApiKeyToken.unauthenticated("training-api-key");
        System.out.println("before=" + request.isAuthenticated());

        Authentication result = manager.authenticate(request);
        System.out.println("after=" + result.isAuthenticated());
        System.out.println("principal=" + result.getName());
        System.out.println(
            "authorities=" + result.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .toList()
        );
        System.out.println(
            "credentials_absent=" + (result.getCredentials() == null)
        );

        try {
            manager.authenticate(ApiKeyToken.unauthenticated("wrong-key"));
        } catch (BadCredentialsException ex) {
            System.out.println("invalid=rejected");
        }

        try {
            ApiKeyToken.unauthenticated("unverified")
                .setAuthenticated(true);
        } catch (IllegalArgumentException ex) {
            System.out.println("self_trust=rejected");
        }
    }
}
~~~

From the directory containing **build.gradle** and the Gradle wrapper, run:

~~~bash
./gradlew run --quiet
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat run --quiet
~~~

Stdout output of the program:

~~~text
before=false
after=true
principal=reporting-service
authorities=[SCOPE_reports.read]
credentials_absent=true
invalid=rejected
self_trust=rejected
~~~

The program requires the Spring Security library on the Gradle classpath; it cannot be compiled with just **javac ApiKeyDemo.java** without adding the dependency JARs.

### 4.2. Step-by-Step Explanation of Decisions in the Code

**A. Public factory only creates untrusted input.** The **unauthenticated(...)** method takes neither a principal nor authorities from the caller. It only accepts the raw key and creates a token with empty authorities and status false. The **isBlank()** check is minimal input validation, not authentication.

**B. Never let arbitrary code elevate state via a setter.** Overriding **setAuthenticated(true)** throws **IllegalArgumentException**. Inside the private constructor, calling **super.setAuthenticated(verified)** is confined to token-creation logic. The **verified(...)** factory is non-public, and the architectural rule is that only the provider calls it after credential matching. Restricting factory visibility helps prevent programming mistakes; it does not replace code review since trusted inner/enclosing classes can still construct trusted tokens.

**C. The provider does not trust a token just because it has the right class.** The provider checks that the token is the expected type, is still unauthenticated, has credentials, and has a key matching server-side data. If not, **BadCredentialsException** terminates the authentication flow; no principal/authorities are granted.

**D. The trusted result is a new object.** The provider does not call **request.setAuthenticated(true)** and does not attach roles directly onto the request token. It creates a result that no longer holds the raw key, with a principal representing the verified identity and authorities decided by the server.

**E. Credential cleanup.** **ApiKeyProvider** calls **eraseCredentials()** on the request token in **finally**, even on failure. **ProviderManager** also erases credentials by default on the returned result when the result implements **CredentialsContainer**. In the example, the result already holds no key. Because Java Strings are immutable, setting the rawKey field to null only drops the token's reference and **does not guarantee erasing the secret from every String copy currently in memory**. Limiting data lifetime and avoiding logging remain essential.

**F. Digests are compared against server data.** **MessageDigest.isEqual(...)** is used to compare digests. This is a technique to illustrate API key verification, not enough to protect a low-entropy key. In a real system, use strong randomly generated keys and design a schema storing hashes/HMACs, checking scopes, revocation status, expiration dates, and rate limits.

**G. Only the provider returns authenticated.** **ProviderManager** finds the provider via **supports(Class<?>)** and calls **authenticate(...)**. Having **supports** return true does not mean the credentials are valid. If multiple providers support a token, **ProviderManager** may try subsequent providers according to its contract; multi-provider designs must clearly define ordering and rejection conditions.

## 5. Invariants That Should Be Tested

A secure custom token must guarantee the following properties:

| Scenario | Expectation |
| --- | --- |
| Created from syntactically valid raw API key | **isAuthenticated=false**, empty authorities, unverified principal |
| Client sends extra self-asserted roles or accountId | No way to pass self-asserted roles into the input token constructor |
| Code calls **setAuthenticated(true)** on input | **IllegalArgumentException** |
| Wrong credentials | **AuthenticationException**; no trusted token returned |
| Valid credentials | Provider returns a **new** token, authenticated=true, principal and authorities decided by server |
| Trusted result | Contains no raw credentials |
| Provider queried with another class | **supports(...)** returns false |
| Subsequent request without credentials in a stateless model | Does not automatically inherit the previous request's result |
| Endpoint requires higher authority | Authorization denies even though Authentication is valid |

You can add unit tests for the provider using a mock credential store: valid/invalid key, revoked key, invalid tenant, locked account, server-side updated authorities. Do not *mock* the provider to directly return a trusted token and treat that as testing credential verification.

## 6. Integrating the Token into a Real Servlet Application

The Gradle example above illustrates the **authentication core**. In an HTTP application, you need an authentication mechanism (filter or controller) responsible for reading the request, creating an untrusted token, calling the manager, and then placing the **resulting Authentication** into the context upon success.

The following snippet is **illustrative code inside an already-configured authentication filter**, not a standalone Java class:

~~~java
// rawHeader is read from request.getHeader("X-API-Key").
// authenticationManager and request/response come from the filter.
Authentication requestToken =
    ApiKeyToken.unauthenticated(rawHeader);

Authentication verified =
    authenticationManager.authenticate(requestToken);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);

// The filter chain continues processing within the authenticated context.
// For stateless applications: ensure the context is cleared at the end
// of the request; do not store it in HttpSession just because the token is authenticated.
~~~

To make this work in your own project, the token class should be organized as a type with appropriate visibility rather than a demo nested class; dependencies, imports, and filter-chain handling must be provided by the application.

### What the Filter/Controller Must Handle Beyond the Example

1. **Read only defined input sources:** for example, accept only a single **X-API-Key** header per the API contract. Enforce length limits; decide explicitly how to handle duplicate, missing, or malformed headers. Do not let an **X-Role** header influence authorities.
2. **Distinguish HTTP errors:** missing/invalid credentials typically return **401 Unauthorized**; authenticated but lacking sufficient privileges typically return **403 Forbidden**. Do not expose keys, hashes, or verification data in responses.
3. **Choose a session policy:** API keys are usually re-verified on every request under a **STATELESS** model. Do not use HttpSession to store raw keys. If intentionally designing session-based login, consider **SessionAuthenticationStrategy** and **SecurityContextRepository.saveContext(...)**.
4. **Clear SecurityContext:** custom filters should manage lifecycle safely, e.g., **try/finally** to prevent leaking Authentication across requests/threads. Do not skip the authorization-enforcing filter chain.
5. **Match SecurityFilterChain:** the filter must be in the right position and in the right chain that needs protection. For framework-assisted mechanisms, you can use **AbstractAuthenticationProcessingFilter** with success/failure handlers and an appropriate repository/session strategy configuration.
6. **Every relevant request needs authentication:** if the application is stateless, having a controller call **authenticate** on a login endpoint and return 200 does not make other endpoints automatically recognize the user. Authentication must be present in the SecurityContext of the **request accessing the resource**.
7. **Restrict key capabilities:** manage scopes, expiry, revocation/rotation, account/tenant relationships, and log events with secrets stripped. Being able to use a key does not implicitly grant all permissions of the account.

### Difference Between an API Key Token and a Pre-Authentication Token

Some systems receive identity from a reverse proxy or an mTLS gateway that has already verified certificates. Even if the component behind the gateway says “this user is verified”, the application must still determine **whether to trust that gateway and transport channel**. A header like **X-User** from the Internet does not become safe just because you put it into a class named **PreAuthenticated...**.

External data remains untrusted at the application boundary until the source and trust policy are verified. If a proxy is a trusted component, you must ensure direct clients cannot forge/overwrite that header, internal connections are protected, and the server-side authenticator grants authorities only after verifying the appropriate conditions.

## 7. When a Token Carries Multiple Fields: Tenant, OTP, Device, or Other Credentials

The API key example uses a single credential. A custom token can also carry:

- **tenantId**: only the requested tenant; it does not yet prove the user belongs to that tenant.
- **username/email**: a self-asserted identifier, not yet an authenticated principal.
- **OTP**: must be verified for expiration, binding to the user/challenge, attempt count, and replay protection.
- **deviceId**: client-supplied information; must not be treated as a trusted device without cryptographic proof.
- **request metadata**: IP or user agent can assist risk evaluation, but requires proxy source verification and must not be used as sole proof.

A sample design:

~~~text
UntrustedTenantLoginToken:
  requestedTenant = from JSON
  claimedUsername = from JSON
  password = from JSON
  authenticated = false
  authorities = []

Provider:
  1. verify password using PasswordEncoder and server user store
  2. check that user belongs to requestedTenant
  3. check user status, MFA/OTP if required
  4. retrieve effective authorities of user in tenant from server
  5. return new token with principal = verifiedUserId,
     tenantId = verifiedTenantId, authorities = verifiedRoles
~~~

Do not use **requestedTenant** directly as the tenant in the trusted token before checking membership. Likewise, do not copy **requestedRoles** into **GrantedAuthority**. **Authentication details** may hold metadata for auditing, but it is not the place to store passwords or feed self-asserted roles into authorization logic.

If a standard provider already covers the credential mechanism, prefer using it. For example, standard username/password normally uses **UsernamePasswordAuthenticationToken** and **DaoAuthenticationProvider**; a custom token adds value when you genuinely need a different credential model or metadata, not merely to rename a class.

## 8. Protecting Trust Over Time

An authenticated token **does not mean permissions remain valid forever**. With long sessions or cached tokens, permissions/account status can be revoked after the initial authentication. The design must decide:

- **When to re-verify credentials:** every request, every login, or by TTL/cache?
- **When to refresh authorities:** on request or when user data changes?
- **When to revoke:** locked account, rotated key, expired token, removed tenant membership?
- **Across multiple instances:** are caches, key stores, and revocation policies consistent?
- **Access scoping:** are the roles/scopes in the trusted result appropriate for the endpoint and tenant context?

Do not treat **isAuthenticated=true** as an all-access pass. Every endpoint still needs explicit authorization, preferring least privilege.

### Input and Secret Controls

- Limit input length and allowed character types before creating a token. Never pass unvalidated strings directly into SQL queries, file paths, or bean names.
- If the credential is a password, use **PasswordEncoder.matches(...)** against a stored hash; avoid plaintext comparisons, rolling your own password algorithm, or plain SHA-256 hashing for passwords.
- If the credential is a high-entropy API key, store digests/HMACs with a proper management strategy, avoid logging full keys; consider a key identifier for efficient lookup before comparing the secret.
- Handle errors with generic messages, reducing information leakage about whether a user/key exists. Rate-limit attempts and monitor failures.
- Never store raw credentials in **SecurityContext**, arbitrary cookies, logs, MDC, exception messages, or telemetry events.

## 9. Ten Common Mistakes

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Creating a custom token from JSON with **isAuthenticated=true** | Bypasses the authentication boundary | Input tokens are always false |
| Public constructor accepting **authorities** from client | Role injection; clients can grant themselves permissions | Only the provider looks up authorities from the server |
| Accepting principal **admin** from a header and treating it as verified | Identity spoofing | Verify credentials and map the principal from the server |
| Calling **setAuthenticated(true)** after parsing JSON | Turns untrusted data into trusted | Only the provider returns an authenticated result |
| Provider only checks **supports(...)** and returns success | No actual proof verified | Verify credentials inside **authenticate(...)** |
| Returning an authenticated=false token instead of an error on wrong credentials | Caller may mistakenly treat it as success | Throw **AuthenticationException** when actually rejecting |
| Returning a trusted token that still holds the raw API key/password | Secret lives too long in context/session | Erase credentials and limit lifetime |
| Reading **X-Role** to create **GrantedAuthority** | Authorization bypass | Authorities must come from the server store |
| Creating a valid result but forgetting to set **SecurityContext** | Downstream endpoints do not see Authentication | Filter/controller integrates context properly |
| Reusing a trusted token from session without a revocation policy | Revoked permissions may still take effect | Define TTL, invalidation, and recheck policies |

## 10. Self-Check Questions

**Question 1.** A controller reads JSON containing username/password/roles and creates a custom Authentication with **isAuthenticated=true**. What is the main problem?

**Answer:** the controller let client-supplied data cross the trust boundary without verification by an AuthenticationProvider; in particular, the roles field must never be used to grant authorities directly.

**Question 2.** Why does **supports(ApiKeyToken.class)** returning true not mean the API key is valid?

**Answer:** supports only determines that the provider handles that token type, whereas the authenticate method is what must match credentials against trusted data.

**Question 3.** A provider verifies the key as valid and then calls **requestToken.setAuthenticated(true)**. How should this be improved?

**Answer:** create a **new** result token, with server-determined principal/authorities and no raw key; the input token must not allow marking itself trusted.

**Question 4.** The API key is valid, but the client requests **SCOPE_reports.write** via a header while the server only grants **SCOPE_reports.read**. Can the client write reports?

**Answer:** no. Successful authentication does not alter the authorities granted by the provider/server; authorization must deny the missing permission.

**Question 5.** Why does **eraseCredentials()** on a String not guarantee removing the secret completely from the JVM?

**Answer:** Strings are immutable; dropping the token's reference does not immediately erase other copies or memory contents. Limiting storage/transmission/logging of secrets is still necessary.

**Question 6.** A JSON login endpoint calls **AuthenticationManager.authenticate(...)** and receives a result with true. Will the next GET request automatically have Authentication?

**Answer:** not necessarily. The result must be integrated into SecurityContext with the right lifecycle; if persisting across a session, a repository is required, whereas stateless setups must authenticate every request.

**Question 7.** If a user logs in validly for tenant A but also sends tenant B in the JSON, what should happen?

**Answer:** the provider must verify membership/tenant access from a trusted source; never attach tenant B to the trusted result simply because the user sent B.

## Official Documentation

- [Spring Security 6.5 — Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [AbstractAuthenticationToken API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AbstractAuthenticationToken.html)
- [Authentication interface API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/Authentication.html)
- [AuthenticationProvider API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html)
- [ProviderManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html)
- [Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
