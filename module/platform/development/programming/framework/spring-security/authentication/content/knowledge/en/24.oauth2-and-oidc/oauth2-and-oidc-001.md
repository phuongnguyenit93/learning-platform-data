# Distinguishing OAuth 2.0, OpenID Connect, and External Account Login

## 1. Goals and Common Pitfalls

In a Spring Security application, the following three concepts often appear side by side:

- **OAuth 2.0 (OAuth2)**: a protocol framework for **delegated resource access authorization**. An application can receive permission to access an API on behalf of a user, within a permitted scope and lifetime.
- **OpenID Connect (OIDC)**: an **identity authentication** layer built on top of OAuth 2.0. It adds a standardized way for an application to know who has signed in at an identity provider.
- **External account login** (social login/federated login, e.g., “Sign in with Google”): a **product feature** that sends the user from the application to an identity provider, receives the result, and creates an internal login session. This feature can be implemented using OIDC or using OAuth 2.0 combined with the provider's proprietary profile API, depending on what the provider actually supports.

For example: a user clicks **Sign in with Google**. The application has Google verify their identity via the OIDC flow, maps the Google identity to an internal account, and creates a Spring Security session. There is also the case where an application requests permission to read a Google calendar using OAuth 2.0 **without** signing the user into the application. These are two different business requirements.

After this lesson, the reader should be able to distinguish **access permissions**, **identity proof**, **application accounts**, **login sessions**, and the role of each mechanism in Spring Security; read an Authorization Code flow; configure an OIDC Login example with Java 17+; and know how to avoid impersonation, mistaken account linking, and token misuse.

## 2. Quick Comparison Using the Same Questions

| Aspect | OAuth 2.0 | OpenID Connect | External Account Login |
| --- | --- | --- | --- |
| Core question | “Which resources is the client allowed to access?” | “Which user has been authenticated by the provider?” | “Which **application** account will this person sign into?” |
| Purpose | Delegated authorization | Authentication + identity claims on top of OAuth2 | Login and identity-linking experience and workflow |
| Standard / specification | OAuth2 Framework and related RFCs | OIDC Core, Discovery, and related specifications | Not a single protocol |
| Primary proof | Access token for a resource server | ID token and OIDC verification flow | Verified provider identity + internal account mapping |
| Standard ID token? | **No**, OAuth2 alone does not require an ID token | **Yes**, the ID token is a JWT per OIDC | Yes when the provider uses OIDC; possibly no when the provider is OAuth2-only |
| User information | Not a mandatory goal of OAuth2 core | Standard claims: `sub`, `iss`, optionally `name`, `email`… | Depends on provider and application policy |
| Automatically creates internal permissions? | No | No | No; the application decides permissions itself |
| Automatically creates an application login session? | No | Not required | The application typically creates a session/cookie after successful authentication |

**Common confusion:** A valid access token for calling an API **does not automatically** prove that the client owns a trusted login session for the right user. OAuth2 core does not define a standard user login protocol; OIDC explicitly defines the authentication request, ID token, subject, issuer, and token validation.

When evaluating a design, ask these questions in order:

1. Who authenticates the end user?
2. What proof does the application receive, and how is it verified?
3. Which token is issued for which **intended recipient**?
4. By what key is the external identity linked to the local account?
5. Afterward, how does the application maintain the session and decide access permissions?

## 3. OAuth 2.0: Delegating API Access

### 3.1. Four Roles

OAuth 2.0 typically has four logical roles:

- **Resource owner:** the person or entity that owns or controls access to the resource.
- **Client:** the application wanting to access the resource; in the example, the calendar management application.
- **Authorization server (AS):** the server that requests consent/grants authorization and issues tokens to the client.
- **Resource server (RS):** the API holding the protected resources, which checks the access token to decide whether to serve the request.

For example: a user of a calendar management application allows the application to **read calendar events** from an external API. The client receives an access token with the corresponding scope and calls the API. There is no requirement that the calendar owner must use that same external account to sign into the calendar management application.

A token with a scope such as `calendar.read` describes the granted **access scope**, not “the user has `ROLE_ADMIN` in my system”. Provider scopes and application authorities belong to two separate policy spaces.

### 3.2. Authorization Code Flow (with PKCE)

This is the common flow when a browser redirects the user to a provider, and the backend then exchanges the authorization code for tokens.

```text
Browser              Spring App (OAuth client)              Authorization Server       Resource API
  |                               |                                 |                     |
  | -- start account connection ->|                                 |                     |
  |                               |-- create state, PKCE challenge >|                     |
  |<--------------------- redirect to authorization endpoint -------|                     |
  |---------------------- sign in and consent --------------------->|                     |
  |<----------------------- redirect code + state ------------------|                     |
  |---- callback code + state --->|                                 |                     |
  |                               |-- verify state                  |                     |
  |                               |-- exchange code + PKCE verifier>|                     |
  |                               |<--------- access token ---------|                     |
  |                               |---- GET API + Bearer token -------------------------->|
  |                               |<---------------------- API data ----------------------|
  |<--------- result -------------|                                 |                     |
```

*Explanation of the values:*

- `authorization code` is a short-lived, single-use code exchanged for tokens at the token endpoint. **Do not** treat it as a user ID or an access token.
- `state` binds the callback to the original session/authorization request, protecting against forged requests and certain session/callback mix-up bugs. The application must store and validate this value properly.
- `PKCE` consists of a per-transaction secret `code_verifier` and a previously sent `code_challenge`, reducing the risk that someone else can exchange a stolen code. For public clients, PKCE is an especially critical safeguard; it should also be applied according to current capabilities/guidance for confidential clients.
- `redirect_uri` must be registered and strictly controlled. Redirecting to an untrusted domain can leak the code or alter the callback destination.
- `access token` is sent to the **resource server** over a protected channel (typically `Authorization: Bearer ...`); do not use it directly to determine the client's logged-in identity.
- `refresh token` may be issued to obtain a new access token when needed; not every flow or provider issues one.

**Example of an access token:** an application is granted permission by the user to read a list of files on an external system. Possessing that token does not mean the application must create a new account or automatically grant admin privileges to the user in the local database.

### 3.3. Access Tokens Can Be JWT or Opaque

OAuth2 does not require an access token to be a JWT. An access token can be an opaque string that must be checked via introspection; it can also be a JWT whose signature and claims are verified directly by the resource server, if the provider implements it that way.

For an API, validation must match the issuer and architecture: unexpired token, trusted issuer, signature/JWK if using JWT, valid audience/resource indicator, appropriate scope/permissions, and other security conditions. Do not merely “succeed at Base64-decoding” and trust the payload. A properly signed JWT whose `aud` targets a different service **must not** be automatically accepted by the current API.

## 4. OpenID Connect: Adding an Identity Authentication Layer

OIDC extends OAuth2 so that a **Relying Party (RP)** can verify the identity of a user authenticated by an **OpenID Provider (OP)**. Typically, the application sends an authorization request with a scope containing `openid`, receives an authorization code, exchanges the code at the token endpoint, and receives an **ID token** alongside the OAuth2-related tokens.

An ID token is a JWT containing standardized claims. Key claims:

| Claim | Meaning | What should the application do? |
| --- | --- | --- |
| `iss` | Issuer: identifier of the provider that issued the ID token | Match against the **exact configured issuer**; do not blindly trust another domain |
| `sub` | Subject: user identifier within the issuer's namespace | Use together with `iss` as the external identifier key in the OIDC model |
| `aud` | Audience: client ID or audiences receiving the token | Must contain the RP's expected client ID |
| `exp` | Expiration time | Reject expired ID tokens |
| `iat` | Time at which the token was issued | Validate according to protocol and policy requirements |
| `nonce` | Value binding the request/ID token when sent | Match the sent nonce to mitigate replay and flow-based session mix-up |
| `auth_time` | Time when the user authenticated, when present | Use for policies requiring re-authentication, if appropriate |
| `email`, `email_verified`, `name`, `picture` | Optional profile claims | Use only when provided; do not turn them into default login keys/permissions |

Before trusting an ID token, the client must use proper OIDC verification: issuer, audience, signature/algorithm, expiration, and constraints on `nonce`, `azp`, or related flow claims. Spring Security's standard libraries handle these steps; do not write custom code that decodes a JWT and grabs `sub` while skipping signature and issuer checks.

### 4.1. Distinguishing User Identity from User Profile

- `sub` identifies the subject within the scope of `iss`. One person can have **multiple** subjects across different providers; some OPs issue pairwise subjects, which can differ across clients according to OP rules.
- `email` is an attribute that can change, be absent, or be unverified. Even with `email_verified=true`, an email does not grant access to an existing internal account on its own.
- `name` and `picture` are primarily display data. Do not use them as account-linking keys.
- `email_verified` proves that the provider applied its own email verification process, **not** that the email owns any given local account or is permitted into a tenant.

Example ID token **illustrating a payload after validation**, not a real token:

```json
{
  "iss": "https://accounts.example-idp.com",
  "sub": "user-93742",
  "aud": "demo-client-id",
  "exp": 1893456000,
  "iat": 1893452400,
  "email": "alice@example.org",
  "email_verified": true
}
```

**Store the pair `(iss, sub)` rather than storing only `sub`.** If the application supports multiple issuers, the same `sub` string from two issuers does not represent the same person.

### 4.2. How Is UserInfo Different from an ID Token?

OIDC defines a **UserInfo Endpoint** to fetch additional user claims using an appropriate access token. UserInfo is for profile data; the ID token is the authentication proof intended for the RP. If calling UserInfo, ensure that the subject in the response matches the validated subject from the ID token as required by OIDC. Do not treat the response of an arbitrary profile URL as an ID token.

OIDC provides discovery metadata at a standard path and a JWK Set to locate provider configuration and verification keys. The application should use the issuer chosen in configuration and standard libraries; do not take an arbitrary issuer or JWK URL from a user request and fetch it for validation.

## 5. Commonly Confused Values

| Value | Created by | Where is it used? | Should NOT be used to… |
| --- | --- | --- | --- |
| Authorization code | Authorization server | Client exchanges code for tokens | Call APIs or identify the user directly |
| Access token | Authorization server | Resource server checks API access permissions | Replace an ID token to authenticate login at the RP |
| ID token (OIDC) | OpenID Provider | Relying Party confirms the user has logged in | Call APIs not configured to accept ID tokens |
| Refresh token | Authorization server, if issued | Client uses with token endpoint to request new tokens | Send to a resource server or an untrusted frontend |
| App session cookie | Application | Browser sends to continue the application session | Prove access permissions for a provider's API |
| Local user ID | Application | Database primary key, audit, account relationships | Replace identity verification from the provider |

Separate these three events:

1. **The user is authenticated by the provider:** can produce an OIDC ID token.
2. **The client is authorized to call an API:** the client holds an access token with the right scope/audience.
3. **The application logs the user into its own system:** maps the external identity, applies internal account checks, and creates an `Authentication` and appropriate session/persistence mechanism.

A product may perform all three, but they are distinct steps with different preconditions.

## 6. What Does “Login with Google” Actually Do?

Consider the “Sign in with an external account” feature on a website:

```text
User in the application
    |
    | Clicks "Sign in with Google"
    v
Application initiates OIDC Authorization Code flow
    |
    v
Google authenticates the user (and handles consent if needed)
    |
    v
Application receives callback; Spring Security verifies state,
exchanges authorization code, validates ID token
    |
    v
Extracts issuer + subject from verified identity
    |
    +-- Found linked identity -------------> retrieves local_user_id
    |
    +-- Not found -------------------------> safe registration / linking policy
    |
    v
Checks local user: active? tenant? role? policy?
    |
    v
Creates application Authentication / session
    |
    v
User accesses features according to INTERNAL permissions
```

**External login does not mean entering a password into the application.** The application should not ask for the Google password to verify it itself; the provider handles credentials within the appropriate redirect protocol. The application should normally never receive the provider's password.

This feature also **does not automatically prove the user has an internal admin role**. An ID token with `email=admin@example.org`, even if the email is verified, is still not enough to grant `ROLE_ADMIN` unless the application applies its account and authorization policies.

### 6.1. Must Social Login Use OIDC?

No. If the provider supports OIDC, it is usually the best choice for **authentication** thanks to standardized ID token/issuer/subject/Discovery. However, some services support OAuth2 authorization and a profile API under a proprietary contract; an application can use an OAuth2 flow and query the profile API to build a login feature. In that case:

- OAuth2 core itself **does not** standardize login proof.
- You must explicitly verify which provider, which profile endpoint, how a stable user ID is determined, the access token scope, and the transport channel.
- Do not assume there will be an ID token or standard `iss`/`sub` claims if the provider does not implement OIDC.
- Normalize the provider-specific identity, without inventing an OIDC-like issuer value without a contract.

Thus, “OAuth2 login” in API/framework names sometimes describes a **workflow that can lead to login**, not that OAuth2 itself has become an authentication protocol with ID tokens.

## 7. Mapping External Accounts to Internal Accounts

This is the part often skipped when people only demo clicking a login button.

Suppose the database has:

```sql
CREATE TABLE app_user (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    display_name VARCHAR(200) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE external_identity (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    app_user_id BIGINT NOT NULL REFERENCES app_user(id),
    provider_key VARCHAR(512) NOT NULL,
    provider_subject VARCHAR(255) NOT NULL,
    UNIQUE (provider_key, provider_subject)
);
```

The design above is an **illustrative schema**; you must add tenant, audit, data policies, and migrations as required by your system. For OIDC, `provider_key` is typically the **verified issuer**, and `provider_subject` is `sub` from the ID token. For an OAuth2-only provider, use a controlled provider/registration namespace and a stable user ID per the provider's contract (do not treat it as an OIDC `sub`).

Safe workflow:

1. Complete login/receive the provider identity using an official library; only process the information **after** the necessary callback, token, or response has been verified.
2. Look up `external_identity` by the external identity key. If it already exists, retrieve `app_user_id` and check `active`/tenant/permissions before allowing login.
3. If it does not exist yet, apply product policy: automatically create a new account if allowed, ask the user to choose to create an account, or offer to **link** with an already signed-in internal account.
4. When linking, require proof of control over both the **internal account session** and the **external identity**; for sensitive actions, require re-authentication. Write the relationship record inside a transaction, relying on the UNIQUE constraint to handle concurrent access.
5. If the user unlinks, ensure an appropriate login recovery method remains, audit the change, and revoke tokens when necessary.

**Do not automatically link two accounts solely because their emails match.** Emails can be reused, changed, transferred to another owner, lack `email_verified`, or fail to prove a relationship to the local account. An “account merge” feature must have explicit consent/ownership proof and a dedicated policy.

**Do not mix external permissions with internal permissions.** Scopes like `profile`/`email` or a provider group claim do not inherently correspond to `ROLE_USER`/`ROLE_ADMIN`. If you want to map IdP groups to roles, use managed mappings, a trusted claim source, and clear revocation support.

### 7.1. Example of Two Providers with the Same Email

Suppose OIDC provider A issues `iss=https://idp-a.example`, `sub=123`; provider B issues `iss=https://idp-b.example`, `sub=123`. The two accounts represent **different identities** even though `sub` collides. Conversely, the same user may have different `sub` values at two providers. The application must connect them through a verified linking flow, not by guessing via name or email.

## 8. Spring Security: Three Distinct Feature Groups

For Spring Security Servlet (Java 17+, Spring Boot 3.x, Spring Security 6.x), look at the following API names to see which problem the system is solving:

| Spring Security API | Role | Example |
| --- | --- | --- |
| `http.oauth2Login(...)` | Web application signs users in via a provider, supporting OIDC login and appropriate OAuth2 login integrations | “Sign in with Google”, creating an authenticated principal/session |
| `http.oauth2Client(...)` + `OAuth2AuthorizedClient` | Application acts as an OAuth2 client, holding granted tokens to call external APIs under delegation | Reading calendars/files from a provider's API |
| `http.oauth2ResourceServer(...)` | Application's API **receives a Bearer access token** and validates the token as configured | REST backend accepting JWT/opaque access tokens |
| `oauth2Login().userInfoEndpoint(...)` | Customizes how user info is fetched and mapped after login | `OAuth2UserService`, `OidcUserService` |
| `OAuth2AuthenticationToken` | Login result in Spring Security | Holds principal, authorities, registration ID |
| `OidcUser` and `OAuth2User` | Principal after OIDC login or OAuth2 provider profile | Reads identity/profile with the appropriate type |

The same application **can** both log users in with OIDC and use an authorized client to call a provider's API; however, do not enable resource server just because you have “Login with Google”. Resource server protects an API using access tokens **intended for that API**, rather than treating a website's ID token as a Bearer access token.

With Spring WebFlux, the conceptual names are similar, but it uses `ServerHttpSecurity`/`SecurityWebFilterChain` and reactive APIs. The examples below are for Servlet/MVC only; do not copy `HttpSecurity` into WebFlux.

## 9. Spring Boot Example: OIDC Login with Google

This example builds **a sample web application using Google OIDC login**, displaying the provider registration and subject after login. It demonstrates framework integration; to run it for real, you need an OAuth client ID/secret from a Google Cloud project and a registered redirect URI. The sample app does not yet include a database mapping internal accounts, so it **should not be considered a complete production account-linking feature**.

### 9.1. Dependencies

In a Spring Boot 3.x project with the Spring Boot Gradle plugin and dependency management, `build.gradle` can include:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

`spring-boot-starter-oauth2-client` brings in the OAuth2/OIDC client libraries; if you are only building a website login, you do not need to start with `spring-boot-starter-oauth2-resource-server`.

### 9.2. Configuring Client Registration

Create `src/main/resources/application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          google:
            client-id: ${GOOGLE_CLIENT_ID}
            client-secret: ${GOOGLE_CLIENT_SECRET}
            scope:
              - openid
              - profile
              - email
```

In this example, Spring Boot/Spring Security provides default provider settings for Google. From the `google` registration ID, Spring Security uses the provider's corresponding endpoints. Never use dummy secret values as production credentials; supply them via environment variables or a secret manager, and never commit `client-secret` to Git.

Register the **redirect URI** in the provider's OAuth client configuration, for example when running locally:

```text
http://localhost:8080/login/oauth2/code/google
```

Default callback template: `{baseUrl}/login/oauth2/code/{registrationId}`. When deploying behind a reverse proxy, ensure the public `baseUrl` and scheme/host are configured properly to avoid redirect URI mismatches. Production requires HTTPS, secret management, and forwarded-headers configuration that **trusts only authorized proxies**.

The `openid` scope activates OIDC; `profile`/`email` request additional claims that the provider may return according to its policy. Requesting the `email` scope **does not** guarantee that an email is always present or always verified.

### 9.3. SecurityFilterChain

Place the Java files in `src/main/java/com/example/externallogin/`.

**`ExternalLoginApplication.java`**

```java
package com.example.externallogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ExternalLoginApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExternalLoginApplication.class, args);
    }
}
```

**`SecurityConfig.java`**

```java
package com.example.externallogin;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(requests -> requests
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }
}
```

`oauth2Login(...)` configures the redirect/authorization callback flow, code exchange, user info loading, and OIDC validation when the provider/registration is appropriate. It does not make the website receive Google passwords. By default, Spring Security can generate a login provider selection page for the configured client registrations.

**Do not unconditionally disable CSRF** when building a website that uses browser sessions. CSRF, state, SameSite cookies, session fixation, TLS, and logout must be evaluated based on the application type. The example retains Spring Security's default configuration for these protections.

### 9.4. Controller Reading the Login Result

**`ProfileController.java`**

```java
package com.example.externallogin;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class ProfileController {

    @GetMapping("/")
    public String index() {
        return "Sign in at /oauth2/authorization/google";
    }

    @GetMapping("/me")
    public Map<String, String> me(Authentication authentication) {
        if (!(authentication instanceof OAuth2AuthenticationToken login)) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        OAuth2User user = login.getPrincipal();
        Map<String, String> result = new LinkedHashMap<>();
        result.put("registrationId", login.getAuthorizedClientRegistrationId());

        if (user instanceof OidcUser oidcUser) {
            result.put("type", "OIDC");
            result.put("issuer", oidcUser.getIdToken().getClaimAsString("iss"));
            result.put("subject", oidcUser.getIdToken().getSubject());
        } else {
            result.put("type", "OAuth2 provider profile");
            result.put("providerUserId", user.getName());
        }

        return result;
    }
}
```

Key takeaways:

- `OAuth2AuthenticationToken` is the authentication object created by Spring Security after a successful flow; `getAuthorizedClientRegistrationId()` indicates which client registration was used (e.g., `google`). This is a **local configuration name**, not an issuer itself.
- If the principal is an `OidcUser`, we read `iss` and `sub` from the ID token that the framework has already validated. These two values are suitable as the lookup key for external accounts in the OIDC model.
- If the provider is OAuth2-only, `OAuth2User.getName()` depends on the ID attribute configured for the provider profile. It is **not** standard OIDC proof; the application must understand the provider's profile contract.
- The example only exposes minimal identifier fields and **does not** return access tokens, refresh tokens, or the full ID token to the frontend. In production, return the appropriate local user ID/permissions after handling internal account mapping.

### 9.5. Running Locally

Set environment variables in the appropriate shell before running the project. On Linux/macOS:

```bash
export GOOGLE_CLIENT_ID='your-client-id'
export GOOGLE_CLIENT_SECRET='your-client-secret'
./gradlew bootRun
```

On PowerShell:

```powershell
$env:GOOGLE_CLIENT_ID = 'your-client-id'
$env:GOOGLE_CLIENT_SECRET = 'your-client-secret'
.\gradlew.bat bootRun
```

Open this URL in your browser:

```text
http://localhost:8080/oauth2/authorization/google
```

The page will redirect to Google. After signing in and completing the callback, visit:

```text
http://localhost:8080/me
```

An **illustrative response structure** (actual issuer and subject depend on the provider):

```json
{
  "registrationId": "google",
  "type": "OIDC",
  "issuer": "https://accounts.google.com",
  "subject": "some-provider-subject"
}
```

This is a sample response, not output captured from running with a real user account. **Do not** include real emails, subjects, or secrets in articles or production logs.

## 10. Testing Spring Security Without Calling a Real Provider

With `spring-security-test`, you can simulate an authenticated user via `oidcLogin()` to test controllers and authorization without connecting to real Google during tests. This tests **post-login application logic**; it does not test HTTP redirects, code exchange, or provider JWK retrieval.

Create `src/test/java/com/example/externallogin/ProfileControllerTest.java`:

```java
package com.example.externallogin;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "spring.security.oauth2.client.registration.google.client-id=test-client",
        "spring.security.oauth2.client.registration.google.client-secret=test-secret"
})
@AutoConfigureMockMvc
class ProfileControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void showsValidatedOidcIdentityToAuthenticatedUser() throws Exception {
        mvc.perform(get("/me").with(oidcLogin()
                        .idToken(token -> token
                                .claim("iss", "https://idp.example")
                                .claim("sub", "subject-42"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.type").value("OIDC"))
                .andExpect(jsonPath("$.issuer").value("https://idp.example"))
                .andExpect(jsonPath("$.subject").value("subject-42"));
    }

    @Test
    void protectedEndpointRedirectsAnonymousUserToLogin() throws Exception {
        mvc.perform(get("/me"))
                .andExpect(status().is3xxRedirection());
    }
}
```

Run `./gradlew test` (Windows: `.\gradlew.bat test`) in a Boot project with a Gradle wrapper. **Expected** result: both tests pass when properly configured. Tests using `oidcLogin()` inject a simulated principal through Spring Security Test; they **cannot** prove ID token validation against a provider. Separate integration tests with a mock/controlled OIDC provider are needed to verify state, callback, signature, issuer, audience, expiry, logout, and failure paths.

When testing callbacks end-to-end, do not use results from `oidcLogin()` to conclude that the provider's state/nonce protections are properly enforced in production; unit/controller tests and protocol tests have different scopes.

## 11. Customizing Post-Login Account Handling

Spring Security provides two common extension points:

- `DefaultOAuth2UserService` / `OAuth2UserService<OAuth2UserRequest, OAuth2User>` for OAuth2 profile providers (non-OIDC).
- `OidcUserService` / `OAuth2UserService<OidcUserRequest, OidcUser>` for OIDC login, when you need to load and transform user details/claims.

When integrating an internal database, you can wrap a default service, let it load/validate the provider data via the standard flow, and then **after successful authentication** query the `external_identity` table, check the local account, and attach internal authorities to the principal according to policy. For linking workflows, handle the case where no local account exists yet with a dedicated page/flow; do not arbitrarily assign roles from an email.

A **pseudocode** model to clarify business logic, not standalone runnable Spring Security code:

```text
verified = springSecurityOidcLoginResult()
identityKey = (verified.issuer, verified.subject)

link = externalIdentityRepository.find(identityKey)
if (link exists) {
    user = localUserRepository.findById(link.localUserId)
    require user.active && tenantPolicyAllows(user)
    issueLocalSessionFor(user)
} else {
    require allowedRegistrationOrExplicitLinkingFlow()
    // Create account or link only after the required proof/consent.
    finishOnboardingOrLink()
}
```

The reason this is pseudocode: the API/controller handling unlinked requests, database transactions, principal mapping, exception handling, and session persistence must be designed for the application's architecture. In particular, **do not** catch every `OAuth2AuthenticationException` and manually create a session when issuer/subject have not been verified.

## 12. Security: What Can Go Wrong?

### 12.1. Login CSRF and Callback Swapping

If the application does not bind the callback to the authorization request initiated by the same browser, an attacker can try to trick a victim into signing into the wrong account. `state` and secure storage of the authorization request defend against this class of attack; PKCE adds protection for the code; OIDC's `nonce` binds the ID token to the authentication request when used. Do not disable default safeguards just to “make login work quickly”.

### 12.2. Confusing Tokens or Recipients

- **ID tokens** are for the RP to authenticate the user. Do not send them instead of access tokens to APIs that expect access tokens.
- **Access tokens** are for resource servers. An access token from another provider, or with a mismatched audience, is not a valid credential for your application's API.
- **Refresh tokens** are sensitive and should be stored securely on the backend as appropriate for the client type; do not return them in a JSON response to the browser as profile fields.
- Never log tokens in URLs, query strings, exceptions, access logs, or analytics.

### 12.3. Confusing Issuer or Subject

If the application accepts an ID token from an issuer not on the trusted list, or uses only `sub` without pairing it with the issuer, accounts can be linked to the wrong user. With multiple providers/tenants, define an explicit list of allowed issuers and store separated identity keys.

### 12.4. Risks of Auto-Linking by Email

An email can change, be reclaimed/reused, or match a local user's email without proving control of the internal account. Auto-merging by email can cause account takeover. Only link according to a policy requiring proof of ownership, a user-consented action, and a transaction protected by a unique constraint.

### 12.5. Authentication and Authorization Are Two Steps

External login only proves the user completed the flow with the provider. Afterward, you must still check the internal account, roles, tenant, suspended/deleted status, resource access rules, and policy-driven MFA/step-up requirements.

A user who successfully signs in with Google **does not** inherently have permission to view data belonging to everyone with an email in the same domain. Likewise, never treat `profile` or `email` scopes as administrative privileges.

### 12.6. Sessions, Logout, and Revocation

After `oauth2Login()`, Spring Security typically maintains a web session via a server-side security context and cookie. Logging out of the application does not automatically log out of Google/the IdP; conversely, logging out at the IdP does not automatically destroy every application session. Single logout must be designed using standard/provider-supported mechanisms with proper redirects and validation. When an internal account is locked or its permissions change, the application needs a policy to update or revoke the corresponding sessions.

In multi-instance deployments, define the session repository, secure cookies, lifetimes, and login recovery policies. If using an SPA frontend without a traditional backend session, choose an appropriate secure login/token architecture instead of simply copying the MVC flow.

## 13. Guide to Choosing a Mechanism Based on Requirements

| Practical Requirement | Main Components | Expected Outcome |
| --- | --- | --- |
| User clicks “Sign in with Google” on a website | OIDC authorization code + `oauth2Login` + account mapping | Verified user identity → local principal/session |
| Application reads a user's calendar on another service | OAuth2 client, scopes, access token, and refresh if available | Delegated API call |
| Mobile app/SPA calls backend REST API with a token from a trusted AS | Resource server, Bearer access token validation | API accepts/rejects based on issuer/audience/scope |
| Receiving identities from multiple tenants or providers | OIDC issuer validation and `(iss,sub)` mapping | No account collision across providers/tenants |
| Provider only supports OAuth2 and a proprietary profile API | OAuth2 flow + verified profile API, clear provider contract | External login via provider-specific integration |
| Linking Google to an account created with a local password | Linking flow with re-auth/consent and transaction | One local user with multiple valid external identities |

**Selection rule:** If the application needs to **know who is signing in**, prefer OIDC with standard issuer/subject when supported by the provider. If it needs **permission to call an API**, use an OAuth2 access token with appropriate scope/audience. If it needs “external account login”, you must also design the step that **maps the identity to a local account and assigns internal permissions**.

## 14. Self-Check Questions and Scenarios

1. An application only receives an access token to read Google Calendar. Why is this not proof that a user has signed into the website? If login is desired, what components must be added?
2. An ID token has `sub=123` from issuer A and another ID token has `sub=123` from issuer B. Should they map to the same account? Explain.
3. A user has `email_verified=true` with an email matching a local admin. Should `ROLE_ADMIN` be granted automatically or the accounts be linked? Design a safe workflow.
4. Distinguish the usage of `ID token` and `access token` when an application both logs users in with OIDC and calls an external API.
5. A Spring Boot API receives a Bearer JWT from a client, but only `oauth2Login()` is enabled. Which mechanism is missing to protect the API? What constraints must an accepted token satisfy?
6. When `redirect_uri_mismatch` or `invalid_state_parameter` errors occur, what elements should be inspected across the browser session, callback, proxy, and provider?
7. Write an integration test against a controlled provider to prove the application rejects an ID token with the wrong issuer, wrong audience, expired timestamp, and a response with a mismatched state. Explain why MVC-level `oidcLogin()` tests are insufficient.

## 15. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| “OAuth2 = login” | Confuses delegated authorization with user authentication | Distinguish OAuth2 and OIDC; clarify the request's purpose |
| Calling an API with an ID token | Token targets the wrong audience/resource | Use the access token issued for that API |
| Extracting JWT payload and trusting `sub` | May trust forged tokens or wrong issuer/audience/expiry | Use a proper OIDC/JWT validator library for the flow |
| Storing only `sub` | Two issuers can issue the same sub | Use the `(iss,sub)` pair in OIDC |
| Using email as an immutable identifier key | Account mix-up/takeover when email changes | Use provider subject; require ownership proof when linking |
| Auto-granting `ROLE_ADMIN` from scope/email | Application authorization flaw | Map roles from internal sources or vetted policies |
| Disabling `state`/CSRF/PKCE to avoid errors | Vulnerable to callback tampering/login CSRF/code interception | Fix redirect, session, and provider configuration properly |
| Returning access/refresh tokens in `/me` response | Leaks credentials capable of calling APIs | Return only needed metadata; store tokens securely |
| Assuming app logout = provider logout | User still has an IdP session and re-logs in without a password | Design sessions and single logout explicitly if supported |
| Enabling `oauth2ResourceServer` to “fix login” | Confuses client login with resource-server validation | Enable the right security capability per path |
| Ignoring redirects behind a reverse proxy | Callback has wrong host/scheme, potentially widening security risk | Configure proxy/forwarded headers from trusted sources and registered URIs |

## 16. Key Takeaways and References

- **OAuth2 = delegated authorization:** access tokens govern resource access permissions.
- **OIDC = authentication on top of OAuth2:** ID tokens carry issuer, subject, and audience, and must be properly validated.
- **External account login = a business workflow:** authenticate at the provider, map the user into the system, check permissions, and create a session.
- **Do not blindly trust emails/roles from profiles.** Account linking requires a stable identity and ownership verification.
- **Spring Security offers distinct capabilities:** `oauth2Login`, `oauth2Client`, and `oauth2ResourceServer` address different problems, though a system may combine them.

Read more in the official documentation: [Spring Security Servlet OAuth2 Login Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html), [OAuth2 Login Advanced](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html), [Testing OAuth2/OIDC with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html), [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html), [OAuth 2.0 Authorization Framework (RFC 6749)](https://www.rfc-editor.org/rfc/rfc6749), [OAuth 2.0 PKCE (RFC 7636)](https://www.rfc-editor.org/rfc/rfc7636), and [OAuth 2.0 Security Best Current Practice (RFC 9700)](https://www.rfc-editor.org/rfc/rfc9700).