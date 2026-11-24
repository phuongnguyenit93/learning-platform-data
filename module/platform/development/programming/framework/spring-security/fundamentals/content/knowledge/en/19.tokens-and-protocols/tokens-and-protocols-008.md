# OpenID Connect Adds Identity and ID Tokens on Top of OAuth2

> **Module:** Spring Security - Fundamentals  
> **Group:** Tokens and Protocols  
> **Focus:** OAuth 2.0 provides resource access authorization; OpenID Connect (OIDC) adds a **user identity authentication layer** on top of OAuth 2.0 using the `openid` scope, ID tokens, and mandatory verification rules.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain why an **OAuth 2.0 access token is not synonymous with an ID token** and is insufficient to standardize login.
- Identify the End-User, Relying Party (RP), OpenID Provider (OP), Authorization Server, and Resource Server.
- Read and understand `iss`, `sub`, `aud`, `exp`, `iat`, `nonce`, `auth_time`, `azp`, and optional claims in an ID token.
- Describe the OIDC Authorization Code Flow with `state`, `nonce`, and PKCE, and know where ID tokens are verified.
- Distinguish ID tokens, access tokens, refresh tokens, UserInfo, and local Spring `SecurityContext`.
- Configure a Spring Boot OAuth2/OIDC client with `oauth2Login()` and retrieve `OidcUser` in a controller.
- Test an OIDC principal with MockMvc `oidcLogin()` without **confusing** mock tests with signature/issuer/audience verification of real ID tokens.
- Apply account identification based on the `issuer + subject` pair and separate identity from roles/authorities.

## 2. What Does OAuth 2.0 Do and What Does It Lack for Login?

**OAuth 2.0** defines an authorization flow allowing a client to call protected APIs with an access token. For example, an app wants to read photos from a photo service:

~~~text
User consents to grant photo-read permission
       |
       v
Authorization Server issues access token to Client
       |
       v
Client calls Resource Server with access token
       |
       v
Resource Server checks permissions/scope and handles request
~~~

That process addresses **permission to use resources**. Plain OAuth 2.0 does not define a standard ID token telling the client for certain "which End-User was authenticated by an identity provider specifically for this client".

Many systems once used OAuth2 access tokens and a custom profile API to simulate login. While that can work within a proprietary system, it lacks common rules for interoperability: an access token may be an opaque string, a JWT whose audience is an API, or a format the client is not allowed to rely upon.

**OpenID Connect 1.0** closes this gap with an **identity layer on top of OAuth 2.0**: the RP sends an authentication request containing `openid`, and the OP authenticates the End-User and provides an **ID token** under standardized rules.

| Aspect | OAuth 2.0 | OpenID Connect |
| --- | --- | --- |
| Primary question | Which APIs may the client access and with what permissions? | Which End-User did the OP authenticate for the RP? |
| Components | Client, Resource Owner, Authorization Server, Resource Server | Adds RP, OP, End-User, and ID token |
| Required scope to signal flow | No universal "login" scope | `openid` marks an OIDC authentication request |
| Token serving primary goal | **Access token** | **ID token** intended for RP; still uses access tokens under OAuth2 |
| Standardized user identity | Not guaranteed from access token | Verified `iss` and `sub` in the ID token |
| Profile info | Depends on API/provider | Standard Claims and UserInfo endpoint when supported |
| Resource mechanism | Resource Server validates access token | OIDC does not replace resource server authorization |

**Do not say "OIDC replaces OAuth2".** OIDC reuses the authorization endpoint, token endpoint, redirect URI, authorization code, and security mechanisms of OAuth2 to add user authentication assertions.

## 3. Roles in an OIDC Flow

~~~text
               Browser / End-User
                       |
                       v
             Spring Boot App / RP
              (OIDC OAuth2 Client)
                       |
          authorization code request
                       |
                       v
            OpenID Provider (OP)
       Identity Provider / Authorization Server
                 |             |
               ID token     Access token
                 |             |
                 v             v
                RP        Resource Server
                 |        Protected API
                 v
           Local SecurityContext
           / HttpSession when used
~~~

- **End-User:** the end user being authenticated.
- **Relying Party (RP):** the application relying on the OIDC result; here, the Spring Boot OAuth2 Client.
- **OpenID Provider (OP):** the server authenticating the End-User and issuing ID tokens. In practice often called Identity Provider (IdP).
- **Authorization Server:** issues access tokens and related tokens under OAuth2; in OIDC, the OP serves this role.
- **Resource Server:** the API consuming the **access token** to decide resource access.
- **Client Registration:** the client's metadata at the OP: client ID, redirect URI, client authentication method, scopes, and related endpoints.

Do not mix up **who receives which token**: ID tokens belong to the RP, and access tokens belong to the appropriate Resource Server. Even a JWT with a valid signature can have the **wrong audience** and cannot stand in for another token's role.

## 4. What Is an ID Token?

An ID token is an OIDC assertion representing the End-User authentication result for a specific RP. An ID token is typically a **JWS-signed JWT**; in specialized configurations it may be an encrypted JWT (JWE) per the spec.

A JWS JWT typically has the structure:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

The payload of a signed JWT **is not encrypted**. Anyone holding the token string can Base64url-decode it to read claims, even without the signature verification key. Therefore, never store unnecessary secrets/PII in it and never log raw ID tokens.

**Illustrative payload** example, not a validly signed JWT:

~~~json
{
  "iss": "https://idp.example.invalid/tenant-a",
  "sub": "user-3812",
  "aud": "demo-web-client",
  "exp": 1900003600,
  "iat": 1900000000,
  "nonce": "random-nonce-correlating-a-request",
  "auth_time": 1899999970,
  "name": "Example User",
  "email": "user@example.invalid",
  "email_verified": true
}
~~~

The `.invalid` addresses and timestamps are for example only; they do not represent a currently usable token.

### Core Claims

| Claim | Mandatory in ID Token? | Meaning |
| --- | --- | --- |
| `iss` | Yes | Issuer identifier; RP must match trusted issuer exactly |
| `sub` | Yes | End-User's subject identifier within the issuer's scope |
| `aud` | Yes | Audience(s); must contain the `client_id` of the RP receiving the ID token |
| `exp` | Yes | Expiration time; expired tokens must be rejected |
| `iat` | Yes | Issued-at time; token age may be checked per policy |
| `nonce` | Conditional on flow/request | Binds ID token to authentication request; in code flow must verify if sent |
| `auth_time` | Conditional, e.g., when request uses `max_age` | Timestamp when the OP authenticated the End-User |
| `azp` | Conditional on multiple audiences | Authorized party; used per OIDC Core rules |
| `at_hash` | Depends on flow; optional in code flow | Can bind the access token to the ID token |
| `acr`, `amr` | Optional | Authentication context / methods if provided by OP |
| `email`, `name`, `picture`, `email_verified` | Optional | Standard profile claims, not administrative permissions |

OIDC does not guarantee every OP returns `email` or `name` in all cases. Scopes `profile`/`email`, consent, and provider policies affect which claims the RP receives.

### Proper Account Identification: The `(iss, sub)` Pair

`sub` is a subject identifier scoped to the issuer; do not infer from matching `sub` values across two OPs that they represent the same user.

~~~text
Issuer A: https://idp-a.example.invalid | sub=42
Issuer B: https://idp-b.example.invalid | sub=42

These MUST NOT automatically be treated as the same identity.
~~~

`email` can change or be recycled and is not an immutable stable key. When linking accounts, a generally sound choice is the `issuer + subject` pair, with explicit multi-issuer/multi-tenant linking policies. An OP may also issue different **pairwise subjects** to different clients to reduce cross-RP correlation.

## 5. OIDC Authorization Code Flow

For server-side web apps, the common model is the OIDC **Authorization Code Flow**, paired with PKCE per client policy.

~~~text
Browser             Spring Boot RP               OpenID Provider
   |                       |                             |
   | GET /me               |                             |
   |---------------------->|                             |
   |                       | redirect to authorization   |
   |<----------------------|                             |
   | GET /authorize?scope=openid&response_type=code...    |
   |----------------------------------------------------->|
   |                       |       Login / consent       |
   |                       |                             |
   | 302 /login/oauth2/code/demo?code=...&state=...       |
   |<-----------------------------------------------------|
   |---------------------->|                             |
   |                       | check state, exchange code   |
   |                       | POST /token: code + verifier |
   |                       |----------------------------->|
   |                       | access_token + id_token      |
   |                       |<-----------------------------|
   |                       | VERIFY ID TOKEN              |
   |                       | Build OidcUser, Authentication|
   |                       | SecurityContext/session      |
   |<----------------------|                             |
   | request authenticated |                             |
~~~

### Authorization Request

A request carries these parameters:

~~~text
GET https://idp.example.invalid/authorize
  response_type=code
  client_id=demo-web-client
  redirect_uri=https://app.example.invalid/login/oauth2/code/demo
  scope=openid profile email
  state=opaque-random-state
  nonce=opaque-random-nonce
  code_challenge=base64url(SHA256(code_verifier))
  code_challenge_method=S256
~~~

This illustrates parameter meaning; **it is not a percent-encoded URL and contains no real cryptographic values**. The framework/library constructs valid URLs and secure random values.

- `openid`: mandatory so the OP recognizes this as an OIDC authentication request.
- `response_type=code`: OP returns an authorization code on redirect; RP exchanges the code at the token endpoint.
- `state`: correlates the callback with the initiating request, defending against login CSRF / authorization response injection.
- `nonce`: binds the ID token to the authentication request; must be verified per flow rules.
- **PKCE:** client retains `code_verifier`, sends `code_challenge` upfront, and proves possession of the verifier when exchanging the code. Usually uses method `S256`.
- `redirect_uri`: must be validated by the OP against client registration; never accept arbitrary attacker redirect URLs.

Do not use the implicit flow for new designs merely to "receive the ID token directly in the browser". Authorization Code + PKCE avoids exposing tokens on the front-channel and strengthens defense against code interception.

### Token Response

The OP may return:

~~~json
{
  "access_token": "opaque-or-jwt-access-token",
  "token_type": "Bearer",
  "expires_in": 600,
  "id_token": "signed-oidc-id-token",
  "refresh_token": "optional-refresh-token"
}
~~~

Values are **descriptive placeholders**. Whether a refresh token is issued depends on grant, scope, consent, and provider policy.

| Token | Primary Consumer | Usage |
| --- | --- | --- |
| **ID token** | RP / OIDC client | Verifies whom the OP authenticated; audience is the RP |
| **Access token** | API / Resource Server | Lets the API evaluate permissions/scopes per token |
| **Refresh token** | Token endpoint / Authorization Server | Requests new access tokens per lifetime/rotation/revocation policy |

Never put an ID token in `Authorization: Bearer` to access an API merely because it is a signed JWT. If a Resource Server needs the caller's login identity, it must still verify an **access token intended for that API** and use appropriate claim/authority mappings.

## 6. ID Token Validation: "Decode" Is Completely Different from "Verify"

Base64url decoding checks neither signature, issuer, audience, nor whether the token was altered. An RP must never treat unverified data in a JWT as trusted authentication.

ID token verification checklist per OIDC Core and application configuration:

1. **Signature + algorithm:** trust configured issuer keys/JWKS; verify signature and algorithm per trust policy. Never arbitrarily accept `alg=none`.
2. **Issuer `iss`:** must match the known issuer **exactly**, without substring/hostname heuristics.
3. **Audience `aud`:** must contain the RP's `client_id`. Tokens validly signed yet issued for another client must be rejected. Handle `azp` if multiple audiences exist per OIDC Core.
4. **Timestamps:** verify `exp`, `iat`, clock skew policy, and `auth_time`/`max_age` when required.
5. **Request binding:** compare callback `state`, the sent `nonce` with the ID token's value, and use PKCE properly when exchanging the code.
6. **Token response/flow:** verify the result came from the expected grant/token endpoint and client registration; check `at_hash` when required by flow/claims.
7. **UserInfo:** if calling this endpoint, `sub` in the UserInfo response must equal `sub` in the ID token; never merge another user's profile.

**Never roll your own JOSE/JWT validator by splitting on dots and Base64 decoding** in production code. Spring Security provides OAuth2/OIDC client libraries. Your test plan must still cover wrong `iss`, wrong `aud`, expired `exp`, forged signatures, and mismatched `nonce` using trusted OIDC test fixtures.

### JWKS, `kid`, and Key Rotation

OPs typically publish public keys via `jwks_uri` in discovery metadata. The RP uses matching keys and supported signing algorithms to verify the JWS. The `kid` header usually helps select the key. When the OP rotates keys, the client needs an appropriate JWKS refresh/caching policy.

Never trust a JWK URL injected by an attacker into a JWT header; the root of trust comes from configured trusted issuer/provider settings, not from the presented token itself.

### Email and `email_verified` Do Not Grant Permissions

`email_verified=true` indicates the OP verified the email under its policy; **it does not mean this person holds `ROLE_ADMIN`**. Identity and authorization are two separate layers. Business authorities must come from a trusted authorization policy.

## 7. What Is UserInfo and How Does It Differ from an ID Token?

The OIDC UserInfo endpoint can return Standard Claims about the End-User when the RP calls it with a suitable access token:

~~~text
RP -> UserInfo endpoint
       Authorization: Bearer <access-token>
    <- JSON: sub, name, email, picture...
~~~

Key distinctions:

- **ID token**: authentication message for the RP, carrying mandatory claims such as `iss`, `sub`, `aud`.
- **UserInfo**: supplemental profile claim source depending on OP, scopes, and consent; does not replace ID token verification.
- **Subject consistency**: `sub` from UserInfo **must match** the ID token's `sub`; if they differ, reject the UserInfo data.
- **Not all claims are guaranteed**: requesting `email` scope does not guarantee an `email` field always appears in every environment.

Do not use profile data as an authority-granting mechanism merely because it came from UserInfo.

## 8. Spring Security and OAuth2/OIDC Roles

In Spring MVC/Servlet:

| Spring Security Configuration | Responsibility |
| --- | --- |
| `oauth2Login()` | App acts as RP/client: redirects to OP, handles code callback, exchanges tokens, authenticates OIDC user |
| `oauth2Client()` | Client obtains and uses access tokens to call external APIs |
| `oauth2ResourceServer().jwt()` | App acts as Resource Server: verifies JWT **bearer access tokens** intended for the API |
| `oauth2ResourceServer().opaqueToken()` | App acts as Resource Server: token introspection |
| `formLogin()` | App handles username/password and local authentication flows itself |

Commonly encountered components:

- `ClientRegistrationRepository` holds client ID, provider metadata, scopes, and redirect URI.
- `OAuth2AuthorizationRequestRedirectFilter` initiates the authorization redirect.
- `OAuth2LoginAuthenticationFilter` handles the `/login/oauth2/code/{registrationId}` callback and establishes the authenticated principal.
- `OidcIdTokenDecoderFactory` and related components build ID token decoders per configuration.
- `OidcUser`/`OidcIdToken` represent the principal and ID token processed by OIDC login.
- `OAuth2AuthorizedClient` models access/refresh tokens bound to a client registration.
- `SecurityContext` (optionally persisted in `HttpSession`) holds local app authentication state.

Spring Security does not automatically treat the `openid` scope as `ROLE_USER` or admin authority. If business roles are needed, map them from a trusted source and test them.

## 9. Spring Boot / Java 17 Example with OIDC Client and MockMvc Tests

We will build a Spring MVC app with `oauth2Login()` and a `GET /me` endpoint reading `OidcUser`. The example uses dummy `.invalid` endpoints to run **MockMvc tests without needing an external IdP**.

**Explicit limitation:** The tests mock an OIDC principal and do not perform code exchange or real JWS verification. For interactive browser login, replace the URLs/provider/client secrets with a valid IdP.

### 9.1. File Structure

~~~text
oidc-login-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/oidc/
    │   ├── OidcLoginApplication.java
    │   ├── SecurityConfig.java
    │   └── ProfileController.java
    ├── main/resources/
    │   └── application.yml
    └── test/java/demo/oidc/
        └── OidcLoginTest.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'oidc-login-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

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
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 9.2. Main Application

File `src/main/java/demo/oidc/OidcLoginApplication.java`:

~~~java
package demo.oidc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OidcLoginApplication {
    public static void main(String[] args) {
        SpringApplication.run(OidcLoginApplication.class, args);
    }
}
~~~

### 9.3. Spring Security Filter Chain

File `src/main/java/demo/oidc/SecurityConfig.java`:

~~~java
package demo.oidc;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

`/health` is public; `/me` requires authentication. `oauth2Login()` uses client registration to perform OIDC login. There is no need to enable `oauth2ResourceServer()` when the goal is solely browser login via an OP.

### 9.4. Controller Reading Subject

File `src/main/java/demo/oidc/ProfileController.java`:

~~~java
package demo.oidc;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/health")
    public String health() {
        return "ok";
    }

    @GetMapping("/me")
    public Map<String, String> me(
            @AuthenticationPrincipal OidcUser principal) {
        String sub = principal.getIdToken().getSubject();
        String email = principal.getIdToken()
            .getClaimAsString("email");

        return Map.of(
            "subject", sub,
            "email", email == null ? "" : email
        );
    }
}
~~~

The controller does not return the raw ID token. `subject` is the principal's ID according to the OP, not the email. If account-linking across multiple issuers is needed, the application must also store the verified issuer.

### 9.5. Dummy Client Registration for Tests

File `src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          demo:
            provider: demo-idp
            client-id: demo-client
            client-secret: placeholder-not-for-production
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          demo-idp:
            authorization-uri: https://idp.example.invalid/authorize
            token-uri: https://idp.example.invalid/token
            jwk-set-uri: https://idp.example.invalid/jwks
            user-info-uri: https://idp.example.invalid/userinfo
            user-name-attribute: sub
~~~

The `.invalid` URLs do not serve real logins. They are explicitly declared so Spring does not have to call OIDC Discovery against a fake issuer when building the MockMvc test context. In real environments, prefer provider `issuer-uri` published by the OP (and client ID/secret managed via secret management) if discovery is supported.

### 9.6. Test Using `oidcLogin()`

File `src/test/java/demo/oidc/OidcLoginTest.java`:

~~~java
package demo.oidc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OidcLoginTest {

    @Autowired
    MockMvc mvc;

    @Test
    void healthIsPublic() throws Exception {
        mvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(content().string("ok"));
    }

    @Test
    void meRequiresLogin() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void oidcPrincipalContainsSubject() throws Exception {
        mvc.perform(get("/me")
                .with(oidcLogin().idToken(token -> token
                    .claim("sub", "user-42")
                    .claim("email", "alice@example.invalid")
                )))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.subject").value("user-42"))
            .andExpect(jsonPath("$.email")
                .value("alice@example.invalid"));
    }
}
~~~

Line-wrapped static imports are valid because Java terminates import statements at the semicolon. `oidcLogin()` builds a mock OIDC principal attached to the request, suitable for testing a Spring MVC controller reading `OidcUser` from `SecurityContext`.

Run at project root with JDK 17+ and Gradle 8.x:

~~~bash
gradle test
~~~

**Expected** result: three tests pass. This is an analysis from the sample code, **not an execution log**.

| Request | Authentication | Expectation |
| --- | --- | --- |
| `GET /health` | Anonymous | HTTP 200, body `ok` |
| `GET /me` | Anonymous | Redirect to login |
| `GET /me` | Mock `oidcLogin()` with `sub=user-42` | HTTP 200, JSON with expected subject/email |

**MockMvc limitation:** There is no code exchange at a token endpoint, no real OP issuing an ID token, and no verification of JWS/JWKS, `iss`, `aud`, `exp`, or `nonce` on a real ID token. To verify those steps, integration tests with a test IdP or a controlled setup exercising JWT decoders/protocol validation are needed.

### 9.7. Replacing with a Real OP

If the OP supports Discovery, example production/test configuration looks like:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            client-id: CLIENT_ID_FROM_SECURE_CONFIGURATION
            client-secret: CLIENT_SECRET_FROM_SECURE_CONFIGURATION
            scope:
              - openid
              - profile
              - email
        provider:
          corporate:
            issuer-uri: https://real-issuer.example.org/realm/demo
~~~

**This is a configuration template**, not a live public OP. Use a real issuer URI and supply client secrets via environment/secret manager safely; never hardcode production secrets in source code. When using `issuer-uri`, the framework may call Discovery while initializing registrations, so the URL must be reachable.

With registration ID `corporate`, the default flow can start at `/oauth2/authorization/corporate` and receive callbacks at `/login/oauth2/code/corporate`. The OP must allow the registered redirect URI; proxy/HTTPS/forwarded headers must be configured properly to generate the right public base URL.

## 10. Spring Security Authorities Are Not Derived Automatically from Every OIDC Claim

OIDC authenticates **identity**, while business authorization is another layer.

- `sub`: whom the OP authenticated (within this issuer).
- `scope`: OAuth2 client/token permission conditions.
- `GrantedAuthority`: abstraction used by Spring Security in authorization rules.
- `ROLE_ADMIN`, `document:edit`, tenant permissions: mapped trusted application/IdP policies.

Spring Security provides `OidcUserAuthority` to represent ID token/UserInfo claims. When custom authority mapping is needed, use `GrantedAuthoritiesMapper` or customize the OIDC user service, backed by policies and independent tests.

~~~java
// ILLUSTRATIVE SNIPPET, not a standalone Java class.
// "trustedMapper" is an application-defined bean.
http.oauth2Login(oauth2 -> oauth2
    .userInfoEndpoint(userInfo -> userInfo
        .userAuthoritiesMapper(trustedMapper)
    )
);
~~~

Never automatically grant a user `ROLE_ADMIN` because `email_verified=true` or their email ends with a specific domain. If permissions are truly managed by the IdP, accurately trust the issuer, client, claim mapping, audience, and revocation policy. When business permissions live in an internal database, read them via an appropriate policy layer after identity is authenticated.

### Java 17 Demo: Subject Must Accompany Issuer

File `OidcIdentityKey.java`, a Java 17 program independent of Spring:

~~~java
import java.util.Objects;

public record OidcIdentityKey(String issuer, String subject) {

    public OidcIdentityKey {
        Objects.requireNonNull(issuer);
        Objects.requireNonNull(subject);
    }

    public static void main(String[] args) {
        OidcIdentityKey a =
            new OidcIdentityKey("https://a.invalid", "42");
        OidcIdentityKey b =
            new OidcIdentityKey("https://b.invalid", "42");
        OidcIdentityKey aAgain =
            new OidcIdentityKey("https://a.invalid", "42");

        System.out.println(a.equals(b));
        System.out.println(a.equals(aAgain));
    }
}
~~~

Run:

~~~bash
javac OidcIdentityKey.java
java OidcIdentityKey
~~~

Exact stdout:

~~~text
false
true
~~~

This demo illustrates a composite identity key; it **does not** verify an ID token. In real systems, `issuer`/`subject` must only be taken from an authentication already verified by the OIDC client library.

## 11. Discovery and Provider Metadata

OPs commonly publish OIDC metadata at `.well-known/openid-configuration` per Discovery rules. Metadata may include:

| Metadata Key | Role |
| --- | --- |
| `issuer` | OP name used to match `iss` |
| `authorization_endpoint` | Address handling authorization requests |
| `token_endpoint` | Endpoint exchanging authorization codes for tokens |
| `jwks_uri` | Public key set for verifying ID token signatures |
| `userinfo_endpoint` | Endpoint retrieving profile claims if supported |
| `response_types_supported` | Response types supported by the OP |
| `id_token_signing_alg_values_supported` | ID token signing algorithms supported by the OP |
| `end_session_endpoint` | Logout endpoint if supported/published by the OP |

An issuer may contain a path/realm; never construct discovery URLs with non-standard ad-hoc string concatenation. Optional endpoints may be absent; never assume every OP provides UserInfo or logout identically.

Security rule: **trust the configured issuer**, verify metadata and perform validation against that issuer; never extract a provider URL from an unverified token and treat it as a trusted source.

## 12. State, Nonce, PKCE: Three Different Protection Layers

| Component | Bound Where? | Goal |
| --- | --- | --- |
| `state` | Authorization request and callback | Correlates request/response, prevents login CSRF |
| `nonce` | Authentication request and ID token | Prevents ID token replay/substitution |
| PKCE `code_verifier`/`code_challenge` | Authorization request and token request | Protects authorization code exchange if code is stolen |

Enabling PKCE **does not** let you skip `state` or `nonce` validation. `nonce` also **does not** replace signature/issuer/audience verification. Use a maintained OAuth2/OIDC client library rather than hand-rolling the entire state machine and token validation in controllers.

## 13. Common Mistakes

| Mistake | Risk | Correct Approach |
| --- | --- | --- |
| Using an access token instead of an ID token | Confusing API permissions with login proof | Separate tokens and audiences |
| Missing `openid` scope | Request is not an OIDC login | Configure OIDC client properly |
| Base64-decoding ID token and trusting claims | Forged or tampered tokens trusted | Verify JWS, issuer, audience, expiry, and bindings |
| Checking only `sub`, ignoring issuer | Merging users from different OPs | Use `iss + sub` |
| Using email as identity key | Email can change/be recycled/be absent | Use verified subject |
| Not checking `aud` | Accepting tokens meant for another client | Audience must include the RP's client ID |
| Calling APIs with an ID token | API receives the wrong token type | Send an appropriate access token |
| Treating `email_verified` as admin role | Excessive privilege grant | Authorization policy and trusted mapping |
| Omitting `state`, `nonce`, or PKCE | Increased flow/replay attack risk | Use standard library and configuration |
| Treating MockMvc `oidcLogin()` as real JWT testing | Misses issuer/JWKS/nonce bugs | Test against real OP or dedicated security integration |
| Accepting arbitrary issuer/redirect URI from user input | Token confusion / open redirect | Use registered issuer/redirect allowlists |
| Logging raw ID/access tokens | Leaking credentials/PII | Redact logs, protect token storage |

## 14. Knowledge Self-Check

**Question 1.** Can a client holding an OAuth2 access token treat it as an OIDC ID token?

**Answer:** No. Access tokens target a Resource Server/API; ID tokens are authentication assertions for the RP with dedicated claims and validation.

**Question 2.** Without the `openid` scope, is a request an OIDC authentication request?

**Answer:** No. It may be a valid OAuth2 authorization request, but there is no obligation to return an OIDC ID token.

**Question 3.** Do two tokens with `sub=42` from different issuers belong to the same account?

**Answer:** You cannot conclude that; evaluate the `iss + sub` pair and account-linking policy.

**Question 4.** Why must a token with a valid signature still have `aud` checked?

**Answer:** Because the OP can sign tokens for other clients; an RP must accept only tokens intended for its own client ID.

**Question 5.** Are `state`, `nonce`, and PKCE three ways of doing the same thing?

**Answer:** No. `state` binds the callback to the request; `nonce` binds the ID token to the authentication request; PKCE protects the authorization code exchange.

**Question 6.** Does a passing `oidcLogin()` test prove real JWT signing/issuer/nonce validation works?

**Answer:** No. Mock principal tests do not exchange codes with an OP or verify real token signatures.

**Question 7.** Does `email_verified=true` automatically grant administrative permissions?

**Answer:** No. It is merely a profile claim per OP policy; business permissions must be granted and mapped separately.

## 15. Checklist for Implementing OIDC Login in Spring Security

- [ ] RP is registered at the OP with accurate `client_id`, redirect URI, and client authentication method.
- [ ] Requests include `openid`, using code flow and PKCE per client policy.
- [ ] `state`, `nonce`, callback correlation, and HTTPS are configured properly.
- [ ] ID token signature/algorithm, `iss`, `aud`, `exp`, and conditional claims are verified.
- [ ] `OAuth2AuthorizedClient`/`OidcUser` are used in their proper roles instead of manual JWT parsing.
- [ ] ID tokens are never sent as bearer tokens to a Resource Server.
- [ ] If using UserInfo, `sub` is verified to match the ID token.
- [ ] Account linking relies on `issuer + subject`, not email alone.
- [ ] Authority mapping and business policies are defined independently.
- [ ] Access/refresh/ID tokens and client secrets are never logged.
- [ ] Both MockMvc unit/integration tests and end-to-end OIDC tests against a real OP exist.
- [ ] Local session/logout, IdP SSO session, and token revocation are designed separately.

## 16. Summary and References

**OAuth2 is the authorization foundation; OIDC adds the identity authentication layer and ID tokens on top of it.** A verified ID token tells the RP who (`iss + sub`) the OP authenticated, which client (`aud`) the token is intended for, and for what time window (`iat`/`exp`). Access tokens remain for APIs; refresh tokens are for obtaining new tokens. In Spring Security, `oauth2Login()` handles the OIDC client flow, whereas `oauth2ResourceServer()` validates API access tokens.

Official documentation:

- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [OAuth 2.0 Authorization Framework — RFC 6749](https://www.rfc-editor.org/rfc/rfc6749)
- [PKCE — RFC 7636](https://www.rfc-editor.org/rfc/rfc7636)
- [Spring Security — OAuth2 Login Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html)
- [Spring Security — Testing OIDC Login](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
- [Spring Security — Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
