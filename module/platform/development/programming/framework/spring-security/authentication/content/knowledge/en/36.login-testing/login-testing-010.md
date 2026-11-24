# Testing External Identities, Account Linking, and Provider Errors

When a Java application allows logging in with **Google, Microsoft Entra ID, an OpenID Connect (OIDC) Provider, or an OAuth2 service with a UserInfo API**, testing does not stop at verifying a request has an `Authentication` and returns HTTP 200. The application must also answer: who is this external identity by **immutable issuer/provider + subject**? Which local account is it linked to? Should auto-linking by email ever be allowed? When the provider denies login, expires a session, returns an error, or suffers an outage, does the application accidentally create a session or attach the wrong account?

This lesson belongs to the **Login Testing** group of **Spring Security - authentication**. The scope is **Spring Boot 3.5.x, Spring Security 6.5.x, Java 17+, Spring MVC/Servlet**, using `spring-security-test`, `MockMvc`, JUnit Jupiter, and a simple account-link store. It clearly separates **mocking identity to test domain/authorization** from **actually testing authorization code exchange and token verification with the IdP**, while covering negative tests, provider errors, state/nonce/issuer protection, preventing account takeover via auto-linking, and database consistency.

## 1. From external login to an application account: three distinct layers

| Layer | Subject | Role |
| --- | --- | --- |
| **Identity Provider** (IdP / OpenID Provider / OAuth2 provider) | User at the provider, session at the IdP | Verifies the external user per its protocols and policies |
| **Spring Security OAuth2 Login Client** | `ClientRegistration`, authorization request, callback, ID token/UserInfo, `OAuth2AuthenticationToken` | Executes OAuth2 Authorization Code/OIDC Login, sets `Authentication` and the app session |
| **Local account** | `account_id`, roles/tenant, status, and external identity bindings | Decides which business account is accessed, how linking/unlinking works, and final permissions |

A provider may report "alice logged in with email alice@example.test", yet the application still must resolve **the local account ID**. If the app automatically binds every matching email to one account, address changes, aliases, tenants, unverified claims, or misconfigured IdPs can lead to **account takeover**.

**Two non-equivalent forms of success:**

- **Provider authentication succeeded**: the OIDC ID token/UserInfo or OAuth2 identity was verified/accepted by the framework per configuration.
- **Local account session ready**: the app resolved the right account mapping, the account is not locked, policy/MFA requirements are satisfied, session/context is saved, and post-login output is returned.

Tests must observe both, especially when provider login succeeds **yet linking is rejected**.

## 2. Stable identity keys: OIDC uses (iss, sub), not email

### 2.1. OIDC — issuer and subject pair

Per section 5.7 of **OpenID Connect Core 1.0**, when a Relying Party needs a stable user identifier, the **`iss` + `sub`** pair from the ID token is the key with the right guarantees. `sub` only needs to be unique within one issuer; two different issuers can issue `sub=123` for two different people.

~~~text
IdP A: iss=https://issuer-a.example.test, sub=123   → Identity A
IdP B: iss=https://issuer-b.example.test, sub=123   → Identity B

Identity A ≠ Identity B

IdP A: iss=https://issuer-a.example.test, sub=456,
       email=shared@example.test                   → Identity C

Identity A ≠ Identity C, even though email may match.
~~~

**Never use email, `preferred_username`, `name`, `displayName`, or picture URL as the primary key for account linking.** They can change, be recycled, or be unverified. `email_verified=true` is an extra signal about email per provider semantics; **it is not** proof that the user controls the existing local account and consented to link.

Preconditions before trusting an `iss+sub` pair:

- The callback must pass through a **genuinely verified OAuth2/OIDC path**: authorization code, client binding, state, redirect URI, token endpoint, and ID token validation.
- Verify signatures against trusted keys, issuer, audience/client ID, validity window, and nonce where protocol requires; never use `Base64 decode` as validation.
- Never trust client-submitted JSON containing `iss`/`sub` to execute `linkAccount(...)`.
- Restrict issuers to configured providers; never fetch metadata or JWKS URLs arbitrarily from untrusted claims, which leads to SSRF/issuer confusion.
- Recognize `pairwise subject` models: the same person at an IdP may receive different `sub` values across clients/sectors. Never force `sub` comparisons across RPs/sectors without an IdP contract.

### 2.2. OAuth2 without an OIDC ID token

`oauth2Login()` also supports non-OIDC OAuth2 providers. There, user identity typically comes from UserInfo or a provider API via `OAuth2UserService`. Not every provider has a `sub` claim; for instance, a provider may supply a stable **numeric user ID** in an `id` attribute.

In that case, the key should look like:

~~~text
(controlled namespace/provider registration, stable provider user id)

oauth2:lab-social + id=5021
~~~

Using a registration ID in the namespace is only safe if the app **controls the registration → provider mapping**, and the `id` attribute comes from a **trusted configured endpoint/provider**. Never allow an attacker to submit `registrationId`/`userId` from the frontend and treat it as verified identity.

**Important:** pure OAuth2 is an authorization mechanism and does not define a global identity standard on its own. Never confuse a service's access token with an OIDC ID token intended for client login.

### 2.3. Proper data model

~~~text
LOCAL_ACCOUNT
    account_id (PK, UUID or non-reusable internal ID)
    email, status, tenant, roles, recovery policy
           │ 1
           ▼ N
EXTERNAL_ACCOUNT_LINK
    link_id (PK)
    account_id (FK → LOCAL_ACCOUNT.account_id)
    namespace (OIDC issuer or app-managed provider key)
    subject (stable external user identifier)
    created_at, last_verified_at, revoked_at, ...
    UNIQUE(namespace, subject)
~~~

One local account can bind multiple external identities, e.g., a corporate OIDC and a social provider. However, **each external identity may be linked to at most one local account at a time**.

Invariants:

1. `UNIQUE(namespace, subject)` is enforced by the database, not merely checked in code.
2. Never overwrite a mapping for an external identity already belonging to another account.
3. Re-linking the same account is **idempotent** or returns a deterministic outcome.
4. Removing a link does not accidentally delete the account or other links.
5. At least one valid login/recovery method must remain per policy.
6. If the local account is locked/deleted, a valid provider authentication does not reopen the local account.
7. All link/unlink operations require auditing plus owner checks, recent authentication, and CSRF/session binding per threat model.

## 3. Linking scenarios and account takeover risks

| Case | Desired behavior |
| --- | --- |
| IdP returns identity `(iss-A, sub-1)` already linked to `account-1` | Resolves cleanly to `account-1` if status/policy allow |
| New identity, no local account linked yet | Choose **new local account registration** or a proof-backed linking flow; never hijack an account with matching email |
| Logged-in user on `account-1` wants to add IdP B | Require **recent local authentication/step-up**, redirect to IdP B, verify callback, confirm intent, then write link atomically |
| Identity from IdP B already belongs to `account-2` | Return conflict; **never detach/move to `account-1`** |
| Matching email claim yet different `sub` | Never assume the same person or same account |
| Provider returns `email_verified=false` | Never use email for recovery/linking; follow verification policy |
| Provider changes display name/email | Keep mapping by stable provider ID; update profile separately if needed |
| One person has two identities from different providers | Can both point to the local account after both are verified and the owner confirms |
| Local account locked despite valid provider token | Reject local login; never auto-unlock |
| User wants to unlink the last method | Block or require setting up another recovery/method first |
| Two concurrent link requests for the same external identity | At most one owner via UNIQUE and transaction; never "last writer wins" |
| User A submits `accountId=B` in HTTP body to link | Must be rejected as IDOR; take owner from local authenticated session, never trust body |

### 3.1. Secure linking flow: verify both sides

~~~text
Browser has local session for account-1
       │
       ▼
Step 1: Re-auth/step-up for local account-1
       │ accountId taken from SecurityContext/session
       ▼
Step 2: Server creates pending link intent
       │ random state, expiry, local account id, operation=LINK
       ▼
Step 3: Redirect to IdP so user authenticates external identity
       │ OAuth2 authorization_code, state, PKCE/nonce per config
       ▼
Step 4: OIDC/OAuth2 callback verified by server
       │ issuer/provider + stable subject
       ▼
Step 5: Server checks pending intent, local owner & session binding
       │ no automatic email matching, no arbitrary client accountId
       ▼
Step 6: INSERT UNIQUE(namespace, subject) → account-1
       │  ├─ already belongs to account-1 → idempotent
       │  ├─ already belongs to account-2 → conflict, no relink
       │  └─ not yet present              → create new link
       ▼
Step 7: Audit + confirmation; preserve recovery path
~~~

A severe bug is treating **every OAuth2 login callback** as an account-linking request. Without a verified `pending link intent`, the callback should only proceed with **the login flow** for an existing identity or a safe registration flow.

**Never place client secrets, ID tokens, authorization codes, or access/refresh tokens inside a `pending link intent` exposed to URLs/logs.** OAuth2 `state` is a random value binding the flow and preventing CSRF/response injection; never embed predictable account IDs or credentials in raw `state`.

### 3.2. Email-based linking: why "matching email" is not enough

A provider may return `email=student@example.test`, yet:

- The email is unverified, recycled, or reassigned to a new employee.
- A local account uses the same email with a different real owner.
- Users have email aliases or different tenants sharing an address.
- Providers supply emails for contact purposes, not as a stable subject.
- The email may change after initial linking.

If the application automatically does:

~~~java
// WRONG: sees matching email and immediately wires accounts together.
String localAccountId =
        localUsers.findByEmail(externalUser.getAttribute("email"));
links.save(localAccountId, externalUser.getAttribute("sub"));
~~~

then an attacker can hijack local accounts via insufficiently trustworthy claims. The right approach uses stable external identities to resolve accounts; when merging/linking is needed, require both local proof and external proof, verify the owner, and maintain transactions and audits. If enterprise federation permits auto-provisioning/auto-linking, there must be a **very specific IdP/tenant policy contract** with dedicated tests, never a blanket email rule for all providers.

## 4. Three mandatory testing layers

| Layer | Tools | What it proves | **What it CANNOT prove** |
| --- | --- | --- | --- |
| **Unit/domain** | JUnit, Java service, fake repository | Unique external keys, ownership/conflicts, idempotency, account state/link logic | Truly signed tokens, HTTP callbacks, and state |
| **Spring MVC security/controller** | `MockMvc` + `oidcLogin()`, `oauth2Login()` | Controller/authorization reads the right principal, provider mapping, response, ACLs | Calling an IdP or actually verifying `iss/aud/nonce/signature` |
| **OAuth2/OIDC protocol integration** | Test IdP or local stub issuer/token/JWKS/UserInfo, HTTP client and browser/session | Authorization request, callback, token exchange, validation, session/cookies, errors/timeouts | That a production IdP will never change or suffer an outage |
| **E2E/contract with real provider** | Staging IdP and dedicated test accounts | Metadata compatibility, redirect URIs, MFA/consent, mTLS/proxy/sessions, real failure modes | Does not replace canary/negative/security tests and production observability |

**Very common trap:** using `oidcLogin()` and concluding "JWT signature, issuer, and nonce were properly verified". This helper **creates a mocked SecurityContext** per test parameters, calls no IdP, and does not cryptographically validate tokens. It is great for **post-authentication** logic, yet a separate protocol integration layer is required.

## 5. Which APIs does Spring Security provide?

### 5.1. Servlet OAuth2 Login configuration

Typical components in Spring Security 6.5:

- `HttpSecurity.oauth2Login(...)` configures OAuth2/OIDC authorization code login.
- `ClientRegistration` defines `registrationId`, client ID/secret, authorization URI, token URI, redirect URI, scopes, and issuer URI/JWK Set/UserInfo endpoints as applicable.
- `ClientRegistrationRepository` supplies the registrations the application permits.
- `OAuth2AuthorizationRequestRedirectFilter` builds the authorization request and redirects to `/oauth2/authorization/{registrationId}`.
- `OAuth2LoginAuthenticationFilter` handles the default callback `/login/oauth2/code/{registrationId}`.
- `OAuth2AuthorizedClientRepository` stores authorized client info per configured mechanism; distinct from the app's account links table.
- `AuthenticationSuccessHandler`/`AuthenticationFailureHandler` control success/failure responses.
- `OAuth2UserService`/`OidcUserService` can be customized to map claims into local principals per security policy.

There is **no** default assumption that "OAuth2AuthorizedClient equals a local account link". It represents an OAuth2 client's resource access grant/token, **separate** from mapping issuer+subject to a local account.

### 5.2. MockMvc helpers

`spring-security-test` provides:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.oauth2Login;
~~~

This shows imports line-wrapped after the package; in the complete files below, imports are written one line per statement for easy copying.

- `oidcLogin()` returns `OidcLoginRequestPostProcessor`; supports `idToken(builder -> ...)`, `authorities(...)`, `oidcUser(...)`, and `clientRegistration(registration)`.
- `oauth2Login()` returns `OAuth2LoginRequestPostProcessor`; supports `attributes(attrs -> ...)`, `authorities(...)`, `oauth2User(...)`, and `clientRegistration(registration)`.
- Both build an `OAuth2AuthenticationToken`/principal for the request without verifying token signatures or querying a real UserInfo endpoint.
- `.with(oidcLogin())`/`.with(oauth2Login())` are placed on normal `get(...)`/`post(...)` builders.
- If link-management tests issue HTTP POSTs using cookie/session auth, remember `.with(csrf())` when CSRF is enabled.

**Difference:** `@WithMockUser` mocks a standard local principal and **does not** create an `OidcUser` with an ID token or an `OAuth2AuthenticationToken`. When domain logic reads issuer/sub, pick the matching OAuth2/OIDC post-processor instead of mocking only a username.

## 6. Java 17 demo: external identities can share a subject yet have different issuers

Before bringing in Spring, a standalone Java 17 program clearly illustrates why `(issuer, subject)` is the right data key.

File `ExternalIdentityKeys.java`:

~~~java
import java.util.HashMap;
import java.util.Map;

public class ExternalIdentityKeys {
    record ExternalId(String issuer, String subject) {
    }

    public static void main(String[] args) {
        var first = new ExternalId("https://issuer-a.test", "123");
        var second = new ExternalId("https://issuer-b.test", "123");

        Map<ExternalId, String> owners = new HashMap<>();
        owners.put(first, "account-one");
        owners.put(second, "account-two");

        System.out.println(first.equals(second));
        System.out.println(owners.get(first));
        System.out.println(owners.get(second));
        System.out.println(owners.size());
    }
}
~~~

Compile/run (JDK 17+):

~~~bash
javac --release 17 ExternalIdentityKeys.java
java ExternalIdentityKeys
~~~

**Exact** stdout:

~~~text
false
account-one
account-two
2
~~~

`record` derives `equals`/`hashCode` from **both issuer and subject**, so two users at two issuers sharing the same `sub` are not merged. This snippet only simulates **in-memory identification and mapping**, without running OAuth2/OIDC, HTTP, or a database.

## 7. Spring Boot 3.5 + Spring Security 6.5 demo: OIDC, OAuth2, and provider errors

The demo configures **two completely mocked client registrations** so tests run without Internet:

- `lab-oidc`: OIDC issuer `https://issuer.lab.invalid`, ID token with `iss`/`sub`.
- `lab-social`: non-OIDC OAuth2, stable user ID in the `id` attribute.

The `.invalid` domain is used to avoid confusion with real active IdPs. The app exposes `GET /api/external/identity`, which reads the Spring-provided principal and returns the identifier pair for **lab use**. In production, **never expose raw external subjects/issuers to UIs that do not need them**; responses should use application identifiers and privacy policies.

**Important demo limitation:** the registrations have fake provider URIs; running the app cannot complete a real callback without standing up a test issuer/token/JWKS/UserInfo server. Nevertheless, the `oidcLogin()/oauth2Login()` tests below run without an IdP because they mock the `SecurityContext`. Do not treat this as a production-ready account linking endpoint sample.

### 7.1. Dependencies

`build.gradle` (insert into a Spring Boot 3.5/Groovy DSL project with Boot plugin/BOM and Java 17+):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

`spring-boot-starter-oauth2-client` is required for `ClientRegistration`, `OAuth2LoginAuthenticationFilter`, and OAuth2/OIDC principals/authorized clients. When using the Spring Boot BOM, never hardcode a `spring-security-test` version differing from the runtime branch.

### 7.2. Single Spring Boot file containing the demo classes

Create `src/main/java/example/externallogin/ExternalLoginApplication.java`:

~~~java
package example.externallogin;

import java.io.IOException;
import java.util.HashMap;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class ExternalLoginApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExternalLoginApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class ExternalSecurityConfig {

    @Bean
    ClientRegistrationRepository clientRegistrations() {
        ClientRegistration oidc = ClientRegistration
                .withRegistrationId("lab-oidc")
                .clientName("OIDC Lab")
                .clientId("oidc-lab-client")
                .clientSecret("not-a-real-secret")
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                        AuthorizationGrantType.AUTHORIZATION_CODE)
                .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
                .scope("openid", "profile", "email")
                .authorizationUri("https://issuer.lab.invalid/authorize")
                .tokenUri("https://issuer.lab.invalid/token")
                .jwkSetUri("https://issuer.lab.invalid/jwks")
                .issuerUri("https://issuer.lab.invalid")
                .userNameAttributeName("sub")
                .build();

        ClientRegistration social = ClientRegistration
                .withRegistrationId("lab-social")
                .clientName("Social Lab")
                .clientId("social-lab-client")
                .clientSecret("not-a-real-secret")
                .authorizationGrantType(
                        AuthorizationGrantType.AUTHORIZATION_CODE)
                .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
                .scope("read:user")
                .authorizationUri("https://social.lab.invalid/authorize")
                .tokenUri("https://social.lab.invalid/token")
                .userInfoUri("https://social.lab.invalid/userinfo")
                .userNameAttributeName("id")
                .build();

        // .invalid URIs are for testing only; real login is not possible.
        return new InMemoryClientRegistrationRepository(oidc, social);
    }

    @Bean
    SecurityFilterChain security(
            HttpSecurity http,
            SafeExternalFailureHandler failureHandler)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/login",
                        "/oauth2/authorization/**",
                        "/login/oauth2/code/**")
                .permitAll()
                .anyRequest().authenticated());

        http.oauth2Login(oauth -> oauth
                .failureHandler(failureHandler));

        // Keep default CSRF for state-changing requests.
        // Real link/unlink needs owner session, CSRF, and step-up.
        return http.build();
    }
}

record ExternalIdentity(String namespace, String subject) {
    ExternalIdentity {
        if (namespace == null || namespace.isBlank()
                || subject == null || subject.isBlank()) {
            throw new IllegalArgumentException(
                    "External identity must have namespace and subject");
        }
    }
}

final class ExternalIdentityReader {
    private ExternalIdentityReader() {
    }

    static ExternalIdentity from(Authentication authentication) {
        if (!(authentication instanceof OAuth2AuthenticationToken oauth)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN);
        }

        String registration = oauth.getAuthorizedClientRegistrationId();

        // In real login, OidcUser is trusted ONLY AFTER the framework
        // has verified the ID token with the configured provider.
        if ("lab-oidc".equals(registration)
                && oauth.getPrincipal() instanceof OidcUser oidc) {
            var idToken = oidc.getIdToken();
            if (idToken.getIssuer() == null
                    || !("https://issuer.lab.invalid")
                        .equals(idToken.getIssuer().toString())
                    || idToken.getSubject() == null
                    || idToken.getSubject().isBlank()) {
                throw new ResponseStatusException(HttpStatus.FORBIDDEN);
            }
            return new ExternalIdentity(
                    idToken.getIssuer().toString(),
                    idToken.getSubject());
        }

        // Non-OIDC: app determines stable ID via provider mapping.
        if ("lab-social".equals(registration)
                && !(oauth.getPrincipal() instanceof OidcUser)) {
            Object id = oauth.getPrincipal().getAttribute("id");
            if (!(id instanceof String || id instanceof Number)
                    || id.toString().isBlank()) {
                throw new ResponseStatusException(HttpStatus.FORBIDDEN);
            }
            return new ExternalIdentity("oauth2:lab-social",
                    id.toString());
        }

        throw new ResponseStatusException(HttpStatus.FORBIDDEN);
    }
}

@RestController
class ExternalIdentityController {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/api/external/identity")
    Map<String, String> identity(Authentication authentication) {
        ExternalIdentity key = ExternalIdentityReader.from(authentication);
        // LAB ONLY: Never return raw external IDs in production responses.
        return Map.of("namespace", key.namespace(),
                "subject", key.subject());
    }
}

@Component
class SafeExternalFailureHandler implements AuthenticationFailureHandler {

    private static final Logger LOG =
            LoggerFactory.getLogger(SafeExternalFailureHandler.class);

    @Override
    public void onAuthenticationFailure(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception) throws IOException {

        // Classify only allowlisted error codes; DO NOT log exception,
        // callback URL, authorization code, token, or raw error.
        String category = "PROVIDER_LOGIN_FAILED";
        if (exception instanceof OAuth2AuthenticationException oauthError
                && "access_denied".equals(
                        oauthError.getError().getErrorCode())) {
            category = "USER_DENIED_CONSENT";
        }

        LOG.warn("security_event={} category={}",
                "EXTERNAL_LOGIN_FAILURE", category);

        // Generic response; never leak upstream error_description.
        response.sendRedirect(
                request.getContextPath() + "/login?external_error");
    }
}

// ONLY simulates unique ownership within a single process.
// DO NOT wire this link method directly to an HTTP endpoint!
final class AccountLinkRegistry {
    private final Map<ExternalIdentity, String> owners =
            new HashMap<>();

    synchronized LinkOutcome linkAfterBothProofs(
            String verifiedLocalAccountId,
            ExternalIdentity verifiedExternalIdentity) {
        if (verifiedLocalAccountId == null
                || verifiedLocalAccountId.isBlank()) {
            throw new IllegalArgumentException(
                    "Verified local account required");
        }

        String current = owners.putIfAbsent(
                verifiedExternalIdentity, verifiedLocalAccountId);

        if (current == null) {
            return LinkOutcome.CREATED;
        }
        if (current.equals(verifiedLocalAccountId)) {
            return LinkOutcome.ALREADY_LINKED;
        }
        throw new AccountLinkConflictException();
    }

    synchronized String ownerOf(ExternalIdentity id) {
        return owners.get(id);
    }
}

enum LinkOutcome {
    CREATED, ALREADY_LINKED
}

class AccountLinkConflictException extends RuntimeException {
    AccountLinkConflictException() {
        super("External identity is already linked");
    }
}
~~~

**This is a compilable Java file when the project has the right dependencies**, containing only one public top-level class `ExternalLoginApplication`. `AccountLinkRegistry` simulates in-memory state only and **must never be called from a request carrying a client-declared `verifiedLocalAccountId`**. The method name emphasizes the precondition, yet the demo code **does not generate two-sided authentication proof**. In production, a trusted orchestrator must verify recent local login + fresh external callback/state before calling the domain service; the DB must enforce unique constraints and transactions across multiple instances.

**Why not build a `POST /api/link?accountId=...` for the demo?** Such an endpoint is far too easy to copy into an IDOR/account-takeover vulnerability. Domain linking should be tested separately; real HTTP linking requires a pending-intent/session-binding mechanism that cannot be modeled safely with just an `accountId` parameter.

### 7.3. Running the demo

With the Gradle wrapper present:

~~~bash
./gradlew bootRun
~~~

Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

`GET http://localhost:8080/public` returns:

~~~text
public
~~~

`GET /oauth2/authorization/lab-oidc` produces an HTTP redirect toward `https://issuer.lab.invalid/authorize` with `client_id`, `state`, `redirect_uri`, etc. This is **only the start of the flow**; the browser cannot actually finish because the issuer is a fake domain. Tests for `/api/external/identity` must use Spring Security Test post-processors as in section 8, or replace `.invalid` with a valid IdP environment and client secret managed by a secret manager.

## 8. JUnit + MockMvc test suite: OIDC, OAuth2, and linking

Create `src/test/java/example/externallogin/ExternalLoginApplicationTest.java`:

~~~java
package example.externallogin;

import jakarta.servlet.http.HttpServletRequest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.*;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oauth2Login;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ExternalLoginApplicationTest {

    @Autowired MockMvc mvc;
    @Autowired ClientRegistrationRepository registrations;

    private ClientRegistration oidc() {
        return registrations.findByRegistrationId("lab-oidc");
    }

    private ClientRegistration social() {
        return registrations.findByRegistrationId("lab-social");
    }

    @Test
    void publicEndpointIsAccessible() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void startsAuthorizationRedirectWithoutCallingProvider()
            throws Exception {
        mvc.perform(get("/oauth2/authorization/lab-oidc"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string("Location",
                    containsString(
                            "https://issuer.lab.invalid/authorize")));
    }

    @Test
    void oidcPrincipalUsesIssuerAndSubject() throws Exception {
        mvc.perform(get("/api/external/identity")
                .with(oidcLogin()
                        .clientRegistration(oidc())
                        .idToken(token -> token
                                .issuer("https://issuer.lab.invalid")
                                .subject("subject-a")
                                .claim("email", "shared@example.test"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.namespace")
                    .value("https://issuer.lab.invalid"))
            .andExpect(jsonPath("$.subject").value("subject-a"));
    }

    @Test
    void sameEmailWithDifferentSubjectIsDifferentIdentity()
            throws Exception {
        mvc.perform(get("/api/external/identity")
                .with(oidcLogin()
                        .clientRegistration(oidc())
                        .idToken(token -> token
                                .issuer("https://issuer.lab.invalid")
                                .subject("subject-b")
                                .claim("email", "shared@example.test"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.subject").value("subject-b"));
    }

    @Test
    void rejectsUnexpectedOidcIssuer() throws Exception {
        mvc.perform(get("/api/external/identity")
                .with(oidcLogin()
                        .clientRegistration(oidc())
                        .idToken(token -> token
                                .issuer("https://other.lab.invalid")
                                .subject("subject-a"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void nonOidcProviderUsesConfiguredStableId() throws Exception {
        mvc.perform(get("/api/external/identity")
                .with(oauth2Login()
                        .clientRegistration(social())
                        .attributes(attrs -> {
                            attrs.put("id", "social-5021");
                            attrs.put("email", "shared@example.test");
                        })))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.namespace")
                    .value("oauth2:lab-social"))
            .andExpect(jsonPath("$.subject").value("social-5021"));
    }

    @Test
    void localMockUserCannotImpersonateExternalIdentity()
            throws Exception {
        mvc.perform(get("/api/external/identity")
                .with(user("local-user")))
            .andExpect(status().isForbidden());
    }

    @Test
    void sameExternalKeyCannotMoveToAnotherLocalAccount() {
        AccountLinkRegistry links = new AccountLinkRegistry();
        ExternalIdentity external =
                new ExternalIdentity("https://issuer.lab.invalid",
                        "subject-a");

        assertEquals(LinkOutcome.CREATED,
                links.linkAfterBothProofs("account-a", external));

        assertEquals(LinkOutcome.ALREADY_LINKED,
                links.linkAfterBothProofs("account-a", external));

        assertThrows(AccountLinkConflictException.class,
                () -> links.linkAfterBothProofs(
                        "account-b", external));

        assertEquals("account-a", links.ownerOf(external));
    }

    @Test
    void sameSubjectFromTwoIssuersIsNotSameLink() {
        AccountLinkRegistry links = new AccountLinkRegistry();
        ExternalIdentity a =
                new ExternalIdentity("https://issuer-a.test", "123");
        ExternalIdentity b =
                new ExternalIdentity("https://issuer-b.test", "123");

        assertEquals(LinkOutcome.CREATED,
                links.linkAfterBothProofs("account-a", a));
        assertEquals(LinkOutcome.CREATED,
                links.linkAfterBothProofs("account-b", b));
        assertEquals("account-a", links.ownerOf(a));
        assertEquals("account-b", links.ownerOf(b));
    }

    @Test
    void failedProviderLoginGetsGenericRedirect() throws Exception {
        SafeExternalFailureHandler handler =
                new SafeExternalFailureHandler();
        MockHttpServletRequest request =
                new MockHttpServletRequest();
        MockHttpServletResponse response =
                new MockHttpServletResponse();

        // Error description intentionally contains a fake canary.
        OAuth2AuthenticationException failure =
                new OAuth2AuthenticationException(
                        new OAuth2Error(
                                "server_error",
                                "CANARY_NOT_TO_BE_SHOWN",
                                null));

        handler.onAuthenticationFailure(request, response, failure);

        assertEquals(302, response.getStatus());
        assertEquals("/login?external_error",
                response.getRedirectedUrl());
        assertFalse(response.getContentAsString()
                .contains("CANARY_NOT_TO_BE_SHOWN"));
    }
}
~~~

**Expectation:** 10 `@Test` methods, including 7 via MockMvc, 2 for the account-link domain, and 1 for the custom provider failure handler. All run **offline** with mock registrations; they do not claim the program logged into a real IdP or verified token signatures.

Run with Gradle:

~~~bash
./gradlew test --tests example.externallogin.ExternalLoginApplicationTest
~~~

Expected result when the project has the right dependencies and configuration is 10 tests passing; the example code is written for Spring Security 6.5 APIs, yet no actual build run is claimed here. If a test fails, read the root cause/test report rather than disabling the Security filter chain to make it pass.

### 8.1. Why use `oidcLogin().idToken(...)`?

It lets you construct fixtures with test-controlled `iss`, `sub`, and email:

~~~java
mvc.perform(get("/api/external/identity")
        .with(oidcLogin()
                .clientRegistration(oidc())
                .idToken(t -> t
                        .issuer("https://issuer.lab.invalid")
                        .subject("subject-a")
                        .claim("email", "student@example.test"))));
~~~

This snippet sits inside a test method that has `MockMvc mvc` and an `oidc()` method returning the registration. It does not perform HTTP `/oauth2/authorization/...` or callback `/login/oauth2/code/...`; Spring Test **merely provides a principal** for the current request. The controller's issuer/sub mapping logic is tested; verifying JWS, issuer/audience, and nonce requires tests at another layer.

### 8.2. Why include a negative issuer test?

Even if the app relies on framework OIDC validation, the mapping layer should avoid accidentally accepting an identity from a namespace outside the allowlist. The `rejectsUnexpectedOidcIssuer` test uses a fake fixture with a mismatched issuer to test **defense-in-depth at the domain layer**.

**It is not a test proving a real IdP issued a badly signed token.** Because `oidcLogin()` mocks the security principal, the test skips most protocol validation; thus the negative test here only verifies the controller rule.

### 8.3. Role of AccountLinkRegistry

The `linkAfterBothProofs(...)` method models the invariant:

~~~text
external identity has no owner yet     → CREATED
external identity belongs to owner     → ALREADY_LINKED
external identity belongs to another   → CONFLICT
~~~

`synchronized` guarantees atomicity **within one Java instance only**. An application running across multiple servers must use DB transactions/a unique index on `(namespace, subject)` and handle insert conflicts; never rely on unlocked "SELECT then INSERT" alone against races.

Registry tests **do not simulate and do not guarantee** local-owner verification, session binding, OAuth2 state, recent-auth, or CSRF checks. Those are **service preconditions**; production must only invoke the service once a trusted coordinator has verified sufficient proof. Never add an HTTP endpoint directly accepting a client-supplied `verifiedLocalAccountId` or boolean `isVerified`.

### 8.4. Provider errors do not equal password errors

In OAuth2/OIDC, failures can come from user consent denial, IdP downtime, token endpoint timeouts, invalid client config, state mismatch, or ID token validation failure. Not all of them are "wrong user password".

`SafeExternalFailureHandler` classifies only known errors and returns a generic redirect. Never take raw `exception.getMessage()`, `OAuth2Error.getDescription()`, authorization codes, access tokens, or callback URLs and put them into responses/logs. Never log tokens or raw JWT claims when debugging.

**Limitation:** unit tests calling the handler directly only prove that when the handler is invoked with an exception it returns a clean response. They do **not** prove every real error callback reaches that handler; callback integration tests with an underlying IdP stub are required.

## 9. Testing real provider flows with a local IdP stub: what must be verified?

An OAuth2/OIDC protocol test must **initiate the request from the application**, go through real redirects and callbacks, and can use a mock authorization server in the test environment with endpoints:

~~~text
/.well-known/openid-configuration
/oauth2/authorize
/oauth2/token
/oauth2/jwks
/oauth2/userinfo
~~~

Exact addresses and URL structures depend on the IdP mock framework. Use `WireMock`, `MockWebServer`, a test OIDC provider container, or a test authorization server; **never** expect the `.invalid` URIs from the demo to respond at a token endpoint.

A minimal **authorization code flow** test must verify:

1. `GET /oauth2/authorization/{registrationId}` redirects to the authorization endpoint of **the right trusted provider**.
2. The redirect includes `client_id`, `redirect_uri`, `response_type=code`, `scope`, and random `state`; plus PKCE challenge/nonce when required by policy and spec.
3. The server saves the authorization request/`state` in a repository bound to the session.
4. The test IdP receives the code challenge and returns an authorization code bound to the exact client/user/redirect/PKCE; disallows code reuse.
5. Callback `GET /login/oauth2/code/{registrationId}?code=...&state=...` checks state and session correlation, and exchanges the code at the token endpoint.
6. The token response contains an ID token or access token matching the flow. For OIDC, the ID token has a valid signature, `iss`/`aud`/`exp`/`iat`/nonce matching expectations; JWK Set comes from the trusted issuer.
7. For non-OIDC, the userinfo API returns a stable provider user ID; namespace mapping is accurate.
8. Before creating local sessions/roles, the app applies account linking/status/policies; never auto-link on email alone.
9. Post-login redirect sends the browser to a safe page; no open redirects.
10. Session context is restored on follow-up requests, cookie flags match policy, and the local account is accurate.

**Every API/OIDC mock principal test skips steps 1–7**, so name them accurately: "controller mapping test", not "full OIDC security test".

### 9.1. Negative protocol scenarios

| Code | Simulated fault at provider/callback | Expected behavior |
| --- | --- | --- |
| R01 | Missing callback `state` | Rejected, no authenticated session created |
| R02 | Callback `state` differs from saved request | Rejected, callback not accepted |
| R03 | Session A's `state` submitted in session B | Blocked, no wrong-user linking |
| R04 | Expired or already-exchanged authorization code | Token endpoint returns error, no session created |
| R05 | Token endpoint HTTP 500/503 or timeout | Generic failure, correlation ID; no token/code logged |
| R06 | Token endpoint returns `invalid_client` | Client secret not leaked, no fallback to another client |
| R07 | Wrong redirect URI or client mismatch | Callback/account binding cannot proceed |
| R08 | Invalid ID token signature or disallowed `alg=none` | Rejected, claims not used as identity |
| R09 | ID token issuer differs from configured issuer | Rejected, never selects JWKs from untrusted `iss` |
| R10 | ID token audience lacks valid client ID | Rejected |
| R11 | Expired ID token `exp` / invalid `nbf` | Rejected |
| R12 | Missing or mismatched OIDC nonce when flow requires it | Rejected |
| R13 | JWKS endpoint timeout/key rotation | Follows cache/refresh policy; never "accept without verify" |
| R14 | UserInfo returns different `sub` from ID token (OIDC) | Rejected per OIDC consistency requirement |
| R15 | UserInfo has email only, no stable ID | No auto-linking/creating privileged account |
| R16 | User denies consent: `error=access_denied` | Generic response; no local login created |
| R17 | IdP returns `error_description` with newlines/secrets | Raw description not logged/echoed |
| R18 | Provider returns same email for two different `sub`s | Local accounts not merged |
| R19 | Different provider and tenant yet same `sub` | External identities not merged |
| R20 | Provider changes email/name after linking | Binding stays on stable ID, never relinked |
| R21 | Two clients/sector identifiers, different pairwise `sub`s | Handled per client/sector mapping; never forced |
| R22 | Provider login succeeds yet local account disabled | No usable session created |
| R23 | DB error writing link after callback | Transaction rolls back, no login to wrong account |
| R24 | Two concurrent link requests for same identity | Unique constraint guarantees at most one owner |

### 9.2. Testing network errors without leaking secrets

For provider timeouts or HTTP 500s:

- Log only event codes, endpoint categories or configured provider IDs, and correlation IDs; **never log** `authorization_code`, ID/access/refresh tokens, client secrets, session IDs, or raw state.
- Never return raw `OAuth2Error`/stack traces to browsers.
- Limit retries; **never auto-replay an authorization code** after an indeterminate token-endpoint outcome, because codes are single-use.
- When the issuer is unreachable, never fall back to verifying an "unsigned ID token" or trusting email in the body.
- If offering another login method, present a safe choice; never automatically bypass MFA or account-link verification.
- Monitor outage rates, provider latency, and login failure categories without putting user attributes/secrets into metric tags.

## 10. Testing multi-provider linking and preventing IDOR

### 10.1. Local identity and external identity are two namespaces

~~~text
local account #123
     │
     ├─ OIDC issuer A / sub xyz
     │
     └─ OAuth2 provider B / user id 5021

local account #456
     └─ OIDC issuer A / sub abc
~~~

A local account ID is an application-created business identifier, **not taken from the IdP's `sub`, email, or session ID**. When a user logs back in via one of the links, the app looks up the mapping in `EXTERNAL_ACCOUNT_LINK` and loads local user/roles.

If the system has multiple tenants, block cross-tenant linking even when issuer/subject are technically valid; namespace by tenant when identities are genuinely distinct. Never pass a client-supplied tenant directly into SQL mappings without verifying it against the session/authorization.

### 10.2. Adding another provider link requires *fresh external proof*

A user logged into account #123 cannot simply submit "my external user ID is xyz" and get linked. They must go through a **fresh provider authorization flow** (or equivalent server-verified proof). If an attacker learns a victim's `sub` from logs/URLs, submitting arbitrary `sub` values must never grant control over an external identity.

### 10.3. Local proof and "confused deputy"

If a user clicks "Link Microsoft" yet their local session expires mid-flow, the callback might arrive after another user logs into the same browser. **Never blindly attach the callback identity to whichever account happens to be logged in at callback time**. Store a pending intent bound to the exact account, session, and expiration at initiation, and verify it on callback.

Scenario to test:

~~~text
session A, local owner=account-123 → begin link, state=S
session A expires
session B, local owner=account-456 → callback with state=S

Expected: reject, NOT link external user to account-456.
~~~

When supporting both "login by external identity" and "link external identity to logged-in account", distinguish `operation=LOGIN` from `operation=LINK` in trusted server state. Otherwise, a normal login callback could accidentally link an identity to another user's account.

### 10.4. Unlinking and recovery

Unlinking must require the current local owner and step-up when needed; never let user A unlink B's link by submitting B's `linkId`. After unlinking:

- The external identity can no longer access the local account via that mapping.
- Previously issued local sessions/tokens may remain valid; apply a separate revocation policy.
- You may need to revoke the app's OAuth2 authorized client; unlinking a local mapping **does not automatically sign out all IdP sessions**.
- Ensure at least one working login/recovery method remains, or provide a trusted recovery flow.
- Audit the action without storing access tokens/client secrets/authorization codes.

## 11. HTTP errors, account conflicts, and UX responses

Classify errors cleanly so users and QA know what failed:

| Group | Examples | Suggested UX / HTTP |
| --- | --- | --- |
| User denies consent | `access_denied` | "You canceled signing in with the provider."; still no session created |
| IdP timeout/maintenance | `server_error`, HTTP 5xx, timeout | Temporary notice, allow retrying a fresh flow, do not reuse code |
| Callback broken state/nonce | CSRF/response injection | Do not log in; generic notice and audit security event |
| Invalid token | Bad signature, issuer, audience, expiry | Reject; never decode and trust claims |
| UserInfo missing stable ID | Provider API changed | Do not link; report provider issue, never auto-match email |
| External identity belongs to another account | UNIQUE conflict | Do not reassign owner; require support/owner verification |
| Local account disabled/locked | Local account policy | Create no local session even if IdP authenticated |
| Local user lacks role/tenant | Authorization | May return 403 at protected resource, distinct from invalid OIDC token |
| Pending link/session expired | Link intent timeout | Restart verification flow, never reuse state |
| Database outage during linking | Incomplete transaction | Never report link succeeded; safe retry via idempotency |
| Client registration wrong redirectURI | Misconfiguration | Show generic config error; inspect sanitized internal audit |

**Never use raw provider error descriptions as HTTP bodies or log messages.** A provider/callback page may inject unexpected strings containing PII, tokens, newlines, or markup. Map errors to a **finite set of internal codes**, such as `PROVIDER_UNAVAILABLE`, `EXTERNAL_LOGIN_FAILED`, `LINK_CONFLICT`, `LINK_INTENT_EXPIRED`, and return a server-generated correlation ID.

### Login error is not a password error

In OAuth2 login, the user typically never enters their IdP password into the RP app. The RP should not say "Wrong Google/Microsoft password" when the IdP rejected the request due to consent, state, client config, network, MFA, or tokens. Internal cause classification must rely on provider error categories with clear trust boundaries, never guessing from message strings.

## 12. Storage consistency in production

### 12.1. Database UNIQUE is mandatory

A **logical DDL illustration** (adjust to your dialect and real migrations):

~~~sql
CREATE TABLE external_account_link (
    link_id            VARCHAR(36) PRIMARY KEY,
    local_account_id   VARCHAR(36) NOT NULL,
    issuer_namespace   VARCHAR(255) NOT NULL,
    external_subject   VARCHAR(255) NOT NULL,
    created_at         TIMESTAMP NOT NULL,
    UNIQUE (issuer_namespace, external_subject)
);

CREATE INDEX idx_link_by_local_account
    ON external_account_link(local_account_id);
~~~

Add a foreign key from `local_account_id` to the real accounts table, audit/soft-deletion columns if used, length/collation handling, and PII policies. Never use `ON CONFLICT DO UPDATE SET local_account_id = EXCLUDED.local_account_id` to "win the race": that transfers ownership without proof.

If using soft deletes, design the unique constraint for active links appropriately for your dialect, avoiding two "active" rows with the same key or relinking while an identity is disputed.

### 12.2. Races and idempotency

A **wrong** approach:

~~~text
Request A: SELECT key -> absent
Request B: SELECT key -> absent
Request A: INSERT key → account-1
Request B: INSERT key → account-2
~~~

Checking only in code lets both requests pass. The unique constraint makes one insert fail; the server must translate that to **LINK_CONFLICT** or an idempotent outcome if the owner matches. Even with `SERIALIZABLE`/locks, handle retries and deadlocks cleanly. Write audits only after the transaction genuinely commits.

### 12.3. Changing mappings / merging accounts

When a user merges two local accounts, never automatically transfer all external identities just because emails match. The workflow may need proof of ownership for both local accounts, protection against session confusion, active link conflict checks, transaction/approval/auditing, and a rollback plan. In B2B systems, an external identity may belong to another tenant despite matching email; enforce tenant-scoped linking policies.

## 13. End-to-end testing matrix

| ID | Scenario | Expectation |
| --- | --- | --- |
| E01 | Valid OIDC issuer/sub, already linked to local A | Local account A |
| E02 | Same issuer, different sub, email matches local A | **Do NOT auto-link A** |
| E03 | Different issuer, same sub | Two distinct external identities |
| E04 | Non-OIDC provider valid stable ID | Resolves to right provider namespace |
| E05 | Non-OIDC missing stable ID attribute | Rejected, never falls back to email |
| E06 | Unknown registrationId | Rejected/never silently mapped |
| E07 | ID token issuer mismatches configured issuer | Rejected |
| E08 | Wrong ID token audience/client ID | Rejected |
| E09 | Bad JWT signature/untrusted JWK | Rejected |
| E10 | Expired ID token/wrong nonce | Rejected |
| E11 | Callback missing/wrong state | Rejected, no session created |
| E12 | Session A's state submitted in session B | Rejected |
| E13 | User denies consent | Generic failure, no local session created |
| E14 | IdP timeout or 5xx | No login, no token/client secret leak |
| E15 | Provider token exchange error | Authorization code not reused, audit category logged |
| E16 | Provider changes email yet keeps stable ID | Binding unchanged |
| E17 | Provider has `email_verified=false` | No email auto-link |
| E18 | Identity already linked to A requested to link to B | Conflict, owner stays A |
| E19 | A links same identity a second time | Idempotent |
| E20 | A is linking, local session expires | Callback rejected, never linked to another user |
| E21 | Two concurrent links for same external ID | DB UNIQUE: at most one owner |
| E22 | User A tries to unlink link belonging to B | Rejected as IDOR |
| E23 | User unlinks last login method | Policy denies or requires recovery |
| E24 | Local account locked, IdP auth succeeds | No usable local login created |
| E25 | MockMvc `oidcLogin()` passes yet integration ID token invalid | Two tests at two layers reported distinctly |
| E26 | OAuth2 callback success handler throws | Local session not reported complete without checks |
| E27 | Untrusted redirect URL | No open redirect, no authorization code leak |
| E28 | Server saves authorized client yet DB link uncommitted | Local account not reported linked |
| E29 | IdP repeatedly times out | Reasonable throttling/circuit breaker, no insecure fallback |
| E30 | Retry after provider outage | Fresh flow/state/code created, idempotent result |
| E31 | Pairwise subject differs across two OIDC clients | Not forced as same account without IdP rule |
| E32 | Tokens/provider claims appear in logs | Blocked by security canary/log redaction policy |

These tests span unit, MockMvc, protocol integration, concurrency, and E2E. Each layer carries distinct value; a passing mock-principal test **does not replace** real issuer signature/nonce tests.

## 14. Common mistakes when writing OAuth2/OIDC linking tests

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Testing with `@WithMockUser` when controller requires `OidcUser` | Fails to model right principal/OIDC claims | Use `oidcLogin()` and ID token fixture |
| Calling `oauth2Login()` and claiming token signatures are valid | Skips cryptographic verification | Use local IdP/stub + real callback |
| Using email as the key in the link table | Easy to merge unrelated accounts | OIDC: `iss+sub`; non-OIDC: trusted provider ID |
| Using `sub` alone across two issuers | Cross-provider collisions | Add issuer namespace |
| Letting client send `accountId` in link request | IDOR/account takeover | Take owner from verified local session |
| Reassigning owner via unconditional UPDATE | Hijacks accounts in races | UNIQUE + conflict/approval |
| Not binding pending state to local session | Callback attaches wrong owner | Signed/server-side intent, state/session binding |
| Not checking expired intents | Replay/link after user abandoned flow | TTL and single-use intent |
| Sending raw provider errors to UI/logs | Leaks client secrets/tokens/PII and log injection | Allowlisted codes, generic response |
| Mocking userInfo/email without stable ID | Cannot tell who the real user is | Require stable immutable provider ID |
| Disabling CSRF on cookie-session link/unlink | Cross-site actions | Keep CSRF, recent-auth/step-up |
| Disabling all verification when IdP is down | No safe recovery/backup auth policy | Design safe fallback, never skip verification |
| Using real URIs in networked unit tests | Slow/flaky tests, secret leaks | Local stub/`.invalid` fixtures, separate provider contract tests |
| Counting "oauth2Login mock passed" as full login E2E | Skips state/nonce/aud/iss and browser sessions | Report test tier accurately, add integration tests |
| Using an in-memory HashMap across 3 nodes | Link races and data loss on restart | Database transaction + UNIQUE |
| Storing raw ID/access/refresh tokens in account link table | Unnecessary, widens blast radius | Store minimal stable identity and separate authorized client |
| Testing against real providers with personal emails | Sensitive data and non-reproducible | Dedicated test accounts/fixtures, secrets manager |

## 15. Acceptance checklist

- [ ] Issuer/provider namespace and stable subject clearly defined; OIDC uses `iss+sub`.
- [ ] No auto-linking solely because email/username/displayName match.
- [ ] Separate local account ID and DB `UNIQUE(namespace,subject)`, avoiding cross-tenant confusion.
- [ ] Linking requires recent local proof + fresh external proof, pending intent, and state/session binding.
- [ ] Client-sent account ID, issuer, or subject are never accepted as verified proof.
- [ ] Provider/OIDC and non-OIDC simulated separately with `oidcLogin()`/`oauth2Login()`.
- [ ] MockMvc has Spring Security filters enabled; `@WithMockUser` is not equated with OIDC.
- [ ] Tests cover cross-issuer, same-email/different-sub, conflicts, idempotency, and missing IDs.
- [ ] Provider errors tested via handler (non-leaking response/logs) and real callbacks via local IdP.
- [ ] Protocol integration verifies state, code, PKCE/nonce, issuer, audience, signature, expiry, and UserInfo stable IDs.
- [ ] Tests cover IdP outages, timeouts, invalid clients, user consent denial, and rotating keys.
- [ ] Local account status, MFA, roles, and sessions apply after IdP auth; OIDC success alone grants no privileges.
- [ ] Link/unlink has CSRF, step-up, auditing, and prevents locking out the account when removing the last method.
- [ ] Concurrent linking races handled atomically by DB, not just synchronized Maps.
- [ ] Secrets/tokens/codes/client secrets never enter logs, traces, metrics, or error responses.
- [ ] Plans exist for recovery, provider migration, pairwise-sub, account merges, and monitoring.

## 16. References

- [Spring Security 6.5 — Testing OAuth 2.0 / OIDC with MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/oauth2.html)
- [Spring Security 6.5 — OAuth2 Login](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/core.html)
- [Spring Security 6.5 — OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/advanced.html)
- [Spring Security 6.5 — OAuth2 LoginConfigurer API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/oauth2/client/OAuth2LoginConfigurer.html)
- [Spring Security 6.5 — OidcUser API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/core/oidc/user/OidcUser.html)
- [Spring Security 6.5 — OAuth2AuthenticationToken API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/authentication/OAuth2AuthenticationToken.html)
- [Spring Security 6.5 — OIDC Test Request PostProcessor](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestPostProcessors.html)
- [Spring Security 6.5 — ClientRegistration](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/core.html)
- [OpenID Connect Core — Claim Stability and Uniqueness (`5.7)](https://openid.net/specs/openid-connect-core-1_0.html#ClaimStability)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
