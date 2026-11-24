# Authorization Code Flow and Building Identity in the Application

## 1. Lesson Objectives

When a user chooses **Sign in with Google** or an enterprise Identity Provider (IdP), a Spring Boot application typically does not receive the user's password directly. The browser is redirected to the IdP to log in. Afterward, the IdP returns a short-lived **authorization code**. The application uses that code to obtain tokens, verifies the required information, and creates a login session within the application itself.

This lesson explains two interconnected parts:

1. **Authorization Code flow:** login request, redirect, `state` verification, exchanging `code` for tokens, error handling, and attack prevention.
2. **Building identity in Spring Security:** from ID Token/OIDC claims or OAuth2 UserInfo to `OidcUser`/`OAuth2User`, `Authentication`, `SecurityContext`, application session, internal permissions, and linking with a local account.

After this lesson, you will be able to describe accurately who is responsible at each step, use `oauth2Login()` in Spring Security Servlet, read the logged-in user's identity, recognize the boundaries of each token type, and test key scenarios.

**Scope:** the focus is on a Spring Boot application **logging users in via Authorization Code**, with OIDC as the standard case for identity authentication. This differs from a pure API application that only validates bearer access tokens with `oauth2ResourceServer()`.

## 2. Distinguishing OAuth 2.0 Authorization Code and OpenID Connect

OAuth 2.0 defines an **authorization** mechanism for a client to obtain an access token and call protected resources. Core OAuth 2.0 does not standardize how user identity is represented for application login.

**OpenID Connect (OIDC)** extends OAuth 2.0 to **authenticate users**. When a client requests the `openid` scope, the OIDC Provider issues an **ID Token** containing identifying and authentication claims; the client must validate the ID Token before treating it as a trusted login result.

| Term | Purpose | Used to establish login identity? |
| --- | --- | --- |
| `authorization code` | Short-lived, single-use code delivered by the browser to the callback so the client can exchange it for tokens | No. The code is protocol material, not identity yet |
| `access token` | Allows the client to call APIs/resource servers matching its scope and audience | Not by default. Access tokens are for resource servers, not a substitute for ID Tokens |
| `id_token` (OIDC) | Token containing `iss`, `sub`, `aud`, expiration, and user authentication details | Yes, **after validation** per OIDC rules |
| `refresh token` | Requests a new access token without re-running user interaction if the provider issues one | Not standalone proof of identity |
| `UserInfo` (OIDC) | Endpoint returning additional user claims via an access token | Supplements profile; must ensure `sub` matches the ID Token |
| Application `session cookie` | Lets the browser carry the app session ID on subsequent requests | Used by the app to restore an already created login, not an ID Token |
| `Spring Security Authentication` | Object holding principal, authorities, and authenticated status in `SecurityContext` | The representation of identity and permissions **inside the application** |

Some providers allow “Login with ...” using only OAuth 2.0 + a user profile API, without an ID Token. Spring Security still supports this via `DefaultOAuth2UserService` and `OAuth2User`, though the application must understand the provider's specific contract. To build consistent identities across multiple IdPs, prefer OIDC whenever possible.

## 3. Roles in the Authorization Code Flow

- **Resource Owner / End User:** the person using the browser and signing in at the IdP.
- **User Agent:** the browser carrying redirects across domains, which must not be given the client secret.
- **OAuth Client / Relying Party (RP):** the Spring Boot application receiving the callback, exchanging the code, and creating its own session.
- **Authorization Server / OpenID Provider (OP):** the system authenticating the user, returning the authorization code, and issuing tokens.
- **Resource Server / UserInfo endpoint:** where access-token-protected data lives; may be the same system as or separate from the authorization server.

High-level diagram:

```text
Browser                 Spring Boot (OAuth Client)             IdP / OIDC Provider
   |                             |                                      |
   |-- GET /private/me --------->|                                      |
   |<--- 302 /login ------------|                                      |
   |-- GET /oauth2/authorization/google ------------------------------->|
   |                             |  (Spring creates state, nonce, PKCE*)|
   |<--- 302 to /authorize ------|                                      |
   |------------------------ GET /authorize?... ----------------------->|
   |                             |                           Login/MFA/consent
   |<------------------ 302 redirect_uri?code=...&state=... ----------|
   |-- GET /login/oauth2/code/google?code=...&state=... -->|
   |                             |-- POST /token (back channel) ------->|
   |                             |<-- access_token, id_token*, ... ----|
   |                             |   Protocol/ID Token validation       |
   |                             |   OidcUser + Authentication         |
   |                             |   SecurityContext + local session   |
   |<--------- 302 /private/me --|                                      |
   |-- GET /private/me + session cookie -->|                            |
   |<-- 200, authenticated identity -------|                            |
```

Asterisk `*`: `nonce` and `id_token` belong to OIDC; PKCE depends on client type/policy and should be used per modern OAuth guidance. Not every OAuth 2.0 provider issues an ID Token.

Key point: **the authorization code travels through the browser, whereas exchanging the code for tokens happens directly from the backend to the token endpoint** (for server-side web apps). The browser typically only receives the application's session cookie; there is no need to keep access tokens or ID Tokens in JavaScript to maintain server-side login.

## 4. Step-by-Step Flow, from Initial Request to Authenticated Session

### Step 1. User Accesses a Protected Resource

For example, the user opens `GET /private/me`. `SecurityFilterChain` sees that the endpoint requires `authenticated()` while the request lacks a valid Authentication. With `oauth2Login()`, Spring Security can redirect the browser to the login page and then to the configured provider.

A direct option is the link:

```text
GET /oauth2/authorization/google
```

`google` is the **registrationId** in `ClientRegistrationRepository`, not necessarily the protocol name. If there are multiple IdPs, the app can have `google`, `corporate`, `partner`, each registration having its own issuer/client credentials and redirect URI.

### Step 2. Spring Builds the Authorization Request and Redirects the Browser

In Servlet, `OAuth2AuthorizationRequestRedirectFilter` coordinates `OAuth2AuthorizationRequestResolver` and `ClientRegistrationRepository`. It creates the authorization request with common fields:

- `response_type=code`: requests the Authorization Code flow.
- `client_id`: identifies the application registered with the IdP.
- `redirect_uri`: exact registered callback URI, e.g., `https://app.example.com/login/oauth2/code/google`.
- `scope=openid profile email` when using OIDC.
- `state`: unpredictable value binding the authorization response to the pending login request, helping prevent login CSRF.
- `nonce` (OIDC when used): binds the ID Token to the authentication session, preventing replay.
- `code_challenge` / `code_challenge_method=S256` when using **PKCE**.

Spring stores the pending authorization request using `AuthorizationRequestRepository`. In standard Servlet flows, `HttpSessionOAuth2AuthorizationRequestRepository` uses the HTTP session. This cookie **does not prove the user is logged in yet**; it maintains protocol state and enables callback matching.

Spring then returns HTTP `302 Location: https://idp.example/authorize?...`. The browser actually navigates to the IdP.

### Step 3. IdP Authenticates the User

The IdP performs login, MFA, SSO/session checks, and may prompt for consent. **The Spring application does not see the user's password** at this step.

On success, the IdP redirects the browser back to the registered callback URI with `code` and `state`. On failure or user denial, the callback may carry `error` and `state` instead of `code`.

Syntax example (illustrative values only, not valid):

```http
HTTP/1.1 302 Found
Location: https://app.example.com/login/oauth2/code/google?code=ONE_TIME_CODE&state=RANDOM_STATE
```

Do not put real codes or tokens in logs, analytics, crash reports, or external URLs. Best practices also include an appropriate `Referrer-Policy`, HTTPS, and limiting third-party assets on the callback page.

### Step 4. Callback Must Match the Initiated Authorization Request

`OAuth2LoginAuthenticationFilter` handles this path by default:

```text
/login/oauth2/code/{registrationId}
```

The filter identifies the registration, retrieves the pending authorization request, and compares `state` against the callback. A callback with no matching request, wrong `state`, or an error code must result in **login failure**; never construct a principal directly from query parameters.

This is also why you should not arbitrarily alter authorization request storage, cookie/session settings, or callback routing in multi-node deployments. If `state` is lost due to misconfigured sessions, even valid callbacks cannot be processed.

### Step 5. Backend Exchanges Authorization Code for Tokens

The application sends a `POST` request to the **IdP's token endpoint** over a server-to-server channel. Depending on client type, it uses the registered client authentication method such as `client_secret_basic` or `private_key_jwt`. If PKCE applies, it also sends `code_verifier` so the IdP can verify it against the initial challenge. The authorization code must match the client and redirect URI, and is typically short-lived and single-use.

Illustrative format:

```http
POST /token HTTP/1.1
Host: idp.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=ONE_TIME_CODE&redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Fgoogle
```

The illustration omits client authentication or the PKCE verifier; in a real app, Spring Security sends the required parameters and credentials per `ClientRegistration`.

An OIDC token response typically includes `access_token`, `token_type`, `expires_in`, `id_token`; `refresh_token` is present only when issued by the provider/policy. For plain OAuth 2.0, an ID Token may not exist.

### Step 6. Validate ID Token and Load User Information

For OIDC, the client must verify the protocol result, including as applicable:

1. ID Token signature using a trusted key (per configured algorithm and key policy).
2. `iss` matches the expected IdP issuer; do not trust an arbitrary issuer supplied by the callback.
3. `aud` contains the appropriate client ID; handle `azp` when required by the protocol.
4. `exp`, `iat`, and relevant time constraints.
5. `nonce` matches the earlier request if sent.
6. Additional checks per profile/response type/provider.

Spring Security OIDC relies on `OidcAuthorizationCodeAuthenticationProvider` and `OidcUserService`; normally you do not need to write a custom JWT verifier in controllers. When calling the UserInfo endpoint for profile data, `sub` must match the ID Token. Never trust JSON from a user-supplied UserInfo URL or rely on unverified Base64-decoded claims.

**ID Tokens let the app identify the user; access tokens are for calling APIs.** Sending an ID Token as a bearer token to an API is not an equivalent substitute for an access token.

### Step 7. Spring Security Creates Principal and Authentication

After successful token exchange/validation, Spring creates the user principal:

- OIDC: `OidcUser`, typically `DefaultOidcUser`, exposing the ID Token, claims, and UserInfo (if loaded).
- Non-OIDC OAuth 2.0: `OAuth2User` from `OAuth2UserService`, typically `DefaultOAuth2UserService`.
- Login result as an `OAuth2AuthenticationToken` holding the principal, authorities, `authenticated=true`, and `authorizedClientRegistrationId`.

This step turns “the IdP authenticated the user” into **“the application holds a valid Authentication”**. Security rules like `authenticated()`, `hasRole(...)`, or method security now have data to evaluate.

A typical Authentication contains:

```text
Authentication (OAuth2AuthenticationToken)
├── principal: OidcUser
│   ├── idToken: iss, sub, aud, exp, ...
│   ├── userInfo: profile claims if present
│   └── authorities: OIDC_USER, SCOPE_* or mapped roles
├── authenticated: true
└── authorizedClientRegistrationId: google
```

Depending on the Spring Security version and mapper, the exact set of authorities may vary. `SCOPE_profile` does not mean `ROLE_ADMIN`.

### Step 8. Linking Identity to an Internal Account (If Needed by the App)

An app might only need `OidcUser` to know who is logged in; however, most products have internal accounts, authorization, private data, user status, tenants, and policies separate from the IdP.

Keep three layers separate:

- **External identity:** a subject verified by the IdP.
- **Local account:** an internal user record with an application-owned ID.
- **Authorization:** roles/permissions/tenants determined by application policy.

For OIDC, the durable linking key is typically the **pair (`iss`, `sub`)**. `sub` is only unique within an issuer, so identical `sub` values from two different IdPs must never be assumed to be the same person.

Mapping diagram:

```text
Validated OIDC ID Token: iss=https://login.example/realm-a, sub=user-9021
                     |
                     v
external_identity(issuer, subject)  --unique--> local_user_id=UUID
                     |
                     v
app_user(id, status, tenant, ...)
                     |
                     v
membership + role_policy + resource authorization
```

Email, display name, or avatar are mutable profile fields; **never use an unverified email to auto-merge into an existing account**. Even with `email_verified=true`, linking existing accounts between an IdP and an app requires a transparent policy to prevent account takeover when emails can be reassigned.

Creating/linking a local identity must be handled transactionally with unique constraints:

1. Read `iss`, `sub` from the **verified ID Token**.
2. Look up `external_identity` using both values together.
3. If already linked, load the internal user; check disabled/locked/tenant status.
4. If not yet linked, follow product policy: create a new account, require an invitation, require admin approval, or ask the user to link to an existing account via a separate authenticated session.
5. Save the link record under a unique constraint so concurrent logins cannot create duplicate identities.
6. Load authorities from an approved authorization source and supply them to Spring Security.
7. Do not casually store access tokens, ID Tokens, or client secrets in user/profile tables.

**Illustrative** table schema, to be adapted to your database:

```sql
CREATE TABLE app_user (
    id UUID PRIMARY KEY,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE external_identity (
    issuer VARCHAR(500) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    user_id UUID NOT NULL REFERENCES app_user(id),
    PRIMARY KEY (issuer, subject)
);

CREATE INDEX ix_external_identity_user_id ON external_identity(user_id);
```

These tables do not authenticate OIDC by themselves; they only record the relationship to a user already verified at the protocol layer.

### Step 9. SecurityContext, Session, and Authorized Client

When OAuth2 login succeeds, Spring Security places the Authentication into the request's `SecurityContextHolder` and persists the context via the configured `SecurityContextRepository`/authentication success mechanism. For server-side web apps using sessions, subsequent requests can restore the Authentication via the session cookie.

At the same time, Spring may store **authorized client** information—such as access/refresh tokens—via `OAuth2AuthorizedClientRepository` or `OAuth2AuthorizedClientService`. This is a separate responsibility from storing `SecurityContext`.

| Storage | What It Holds | When Used |
| --- | --- | --- |
| `AuthorizationRequestRepository` | Pending authorization request, `state`, protocol data | During redirect to IdP and callback handling |
| `SecurityContextRepository` | Succeeded Authentication used across app requests | Checking whether the user is logged in and authorized |
| `OAuth2AuthorizedClientRepository/Service` | Client registration + issued OAuth access/refresh tokens | When the app needs to call a resource server on the user's behalf |
| Local user database | Internal ID, issuer/subject mapping, status, and roles | Application-owned identity and policies |

There is no need to issue a custom application JWT just for a server-rendered app to know a user is logged in. A session cookie may suffice. If an app issues its own internal tokens, that is **an additional design** covering signing, audience, lifetime, rotation, and logout/revocation; it does not happen automatically just because `oauth2Login()` succeeded.

## 5. Key Spring Security Servlet Classes and Endpoints

| Component | Role |
| --- | --- |
| `ClientRegistration` | IdP config: client ID/secret, scopes, authorization URI, token URI, redirect URI, issuer/JWKs |
| `ClientRegistrationRepository` | Looks up `ClientRegistration` by registrationId |
| `OAuth2AuthorizationRequestRedirectFilter` | Starts login and redirects the browser to the IdP |
| `OAuth2AuthorizationRequestResolver` | Builds the authorization request, `state`, and related parameters |
| `AuthorizationRequestRepository` | Stores/matches requests while awaiting the callback |
| `OAuth2LoginAuthenticationFilter` | Handles the authorization code callback |
| `OAuth2LoginAuthenticationProvider` | Handles standard non-OIDC OAuth2 login |
| `OidcAuthorizationCodeAuthenticationProvider` | Handles OIDC login via Authorization Code |
| `OAuth2UserService` / `OidcUserService` | Fetches and converts user info per provider type |
| `OAuth2AuthenticationToken` | Resulting Authentication in the application |
| `SecurityContextHolder` / `SecurityContextRepository` | Holds/restores authentication per request/session |
| `OAuth2AuthorizedClientRepository` | Manages authorized clients used when calling external APIs |

Default paths to remember:

```text
/oauth2/authorization/{registrationId}    # start login
/login/oauth2/code/{registrationId}       # callback handled by Spring Security
/login                                    # default login page when needed
```

If you change `authorizationEndpoint().baseUri(...)` or `redirectionEndpoint().baseUri(...)`, you must update both the login-initiation link and the redirect URI registered at the IdP. Do not add a custom controller that manually reads `code` to “finish login” while Spring Security is responsible for handling callbacks.

## 6. Runnable Java 17+ Spring Boot Project with a Real OIDC IdP

This example uses **Spring Boot 3.5.16**, Spring Security Servlet, and Google as the OIDC Provider. This is a specific version to keep the lab reproducible; when building new systems, choose a supported Spring Boot branch.

**Prerequisites for running the real login flow:** create an OAuth/OIDC client in Google Cloud, set the exact authorized redirect URI, and obtain the client ID/secret. The Java code compiles once Maven dependencies are downloaded. You cannot complete a real login session using fake credentials alone.

Structure:

```text
oidc-code-flow/
├── pom.xml
├── src/main/resources/application.yml
├── src/main/java/demo/oidc/LoginApplication.java
└── src/test/java/demo/oidc/LoginApplicationTest.java
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
    <artifactId>oidc-code-flow</artifactId>
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
            <artifactId>spring-boot-starter-oauth2-client</artifactId>
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
```

Create `src/main/resources/application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          google:
            client-id: "${OIDC_CLIENT_ID}"
            client-secret: "${OIDC_CLIENT_SECRET}"
            authorization-grant-type: authorization_code
            scope: openid, profile, email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
server:
  port: 8080
```

Spring Boot/Spring Security includes default metadata for the `google` registration. For an enterprise IdP, add provider config/issuer discovery and use a dedicated registration. Never commit client secrets to the repository. When running behind a reverse proxy, ensure `{baseUrl}` resolves to the public host and HTTPS using trusted forwarded-headers configuration.

In Google Cloud, register the exact redirect URI:

```text
http://localhost:8080/login/oauth2/code/google
```

Create `src/main/java/demo/oidc/LoginApplication.java`:

```java
package demo.oidc;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class LoginApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoginApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public", "/error").permitAll()
                .requestMatchers("/private/**").authenticated()
                .anyRequest().denyAll())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }

    @GetMapping("/")
    public Map<String, String> home() {
        return Map.of("login", "/oauth2/authorization/google");
    }

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/private/me")
    public Map<String, String> currentIdentity(
            @AuthenticationPrincipal OidcUser user) {
        return Map.of(
            "issuer", user.getIdToken().getIssuer().toString(),
            "subject", user.getSubject());
    }
}
```

Once OIDC login succeeds, `@AuthenticationPrincipal OidcUser` is one way to read the identity built by Spring Security in a request handler. The two returned fields illustrate the `issuer + subject` linking key. Production apps typically return a local ID on internal endpoints rather than exposing raw profile/token data.

When running on a development machine, set environment variables first (example syntax for Bash):

```bash
export OIDC_CLIENT_ID="registered-client-id"
export OIDC_CLIENT_SECRET="client-secret-from-secret-manager"
mvn spring-boot:run
```

Open a browser to:

```text
http://localhost:8080/private/me
```

Expected outcome:

1. The browser is redirected to the login page if unauthenticated.
2. After selecting Google, the browser goes to the authorization endpoint with `state` and OIDC parameters managed by Spring.
3. After login/consent, the browser returns to `/login/oauth2/code/google`.
4. Spring exchanges the code, processes OIDC, and creates a session; the browser may be redirected back to `/private/me`.
5. The endpoint returns JSON such as `{"issuer":"https://accounts.google.com","subject":"<subject-issued-by-IdP>"}`. **Actual subject values vary per account**; this only shows the data shape, not a fixed output to hard-code.

Note: `/public` returns the exact body `public` without requiring login. Location headers, cookies, and IdP responses vary by environment, so the exercise does not mock a fixed auth code or token.

## 7. Testing Controllers and Policies with MockMvc

To test the Spring code without logging into real Google, use `spring-security-test` with `oidcLogin()`. This places a simulated OIDC principal into the test request's security context; it **does not verify token signatures**, nor does it send a browser through an IdP.

Create `src/test/java/demo/oidc/LoginApplicationTest.java`:

```java
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

@SpringBootTest(properties = {
    "spring.security.oauth2.client.registration.google.client-id=test-client",
    "spring.security.oauth2.client.registration.google.client-secret=test-secret"
})
@AutoConfigureMockMvc
class LoginApplicationTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publicRouteWorksWithoutLogin() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void authenticatedOidcUserProvidesIssuerAndSubject() throws Exception {
        mvc.perform(get("/private/me")
            .with(oidcLogin().idToken(token -> token
                .issuer("https://issuer.example")
                .subject("subject-123"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.issuer").value("https://issuer.example"))
            .andExpect(jsonPath("$.subject").value("subject-123"));
    }

    @Test
    void anonymousBrowserIsPromptedToSignIn() throws Exception {
        mvc.perform(get("/private/me").accept("text/html"))
            .andExpect(status().is3xxRedirection());
    }
}
```

Run from the project directory:

```bash
mvn test
```

Expected outcome: three tests pass. With Spring Boot 3.5.16, the code uses `@AutoConfigureMockMvc` from the Spring Boot test library. Having the test endpoint return the right `issuer`/`subject` proves how the controller reads the OIDC principal and basic security rules; **it is not a full test of the Authorization Code flow**.

Integration tests against a real provider should additionally verify: redirect URI, state validation, token exchange, ID Token/nonce validation, consent denial behavior, session/logout, and behavior behind ingress/proxies. Never use mocked `oidcLogin()` to conclude that JWT signatures or token endpoints are securely configured.

## 8. Where the Application Maps Local Accounts and Authorities

There are two common extension points:

**`OidcUserService`:** receives `OidcUserRequest` with the ID Token and access token, loads user info, and returns an `OidcUser`. The application can wrap a default `OidcUserService` to read `iss`/`sub`, look up or provision a local account, check status, and return normalized principal/authorities. If provisioning happens at this step, database transactions, unique constraints, and race handling are required.

**`GrantedAuthoritiesMapper`:** converts authorities received from the provider/OIDC user into authorities used by the application. For example, `OIDC_USER` and `SCOPE_email` do not automatically become `ROLE_EDITOR`. The mapper can query an internal permissions store based on the verified issuer/subject.

A **condensed configuration snippet showing only the hook**, not a standalone Java file:

```java
@Bean
SecurityFilterChain appSecurity(
        HttpSecurity http,
        GrantedAuthoritiesMapper roles) throws Exception {

    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated())
        .oauth2Login(oidc -> oidc
            .userInfoEndpoint(userInfo -> userInfo
                .userAuthoritiesMapper(roles)))
        .build();
}
```

This hook can replace the `securityFilterChain` bean in the earlier example when the application provides a `GrantedAuthoritiesMapper`. Do not declare two similar filter chains with overlapping matchers. If you need to call APIs/databases to fetch roles during authentication, a custom `OAuth2UserService`/`OidcUserService` is generally better suited than a complex mapper.

**Logical order for building identity in the application:**

```text
Validated ID Token
    |
    +--> issuer + subject  ---> local identity mapping (unique)
    |                              |
    |                              +--> localUserId
    |                              +--> enabled/locked status
    |                              +--> tenant membership
    |                              +--> app roles / permissions
    |
    +--> OidcUser + mapped authorities
                   |
                   v
           OAuth2AuthenticationToken
                   |
                   v
              SecurityContext
                   |
                   v
        Authorization & Controller
```

Why not use `email` as the primary identifier? Emails can change, be unverified, or belong to someone else after reassignment; `iss + sub` is the OIDC identity key designed for RPs. With multiple tenants/realms, require the exact issuer rather than matching arbitrary domain names to merge users.

## 9. `state`, `nonce`, PKCE, and Security Controls

| Mechanism | What It Protects Against | Where Applied |
| --- | --- | --- |
| `state` | Binds the authorization response to the client-initiated request; prevents login CSRF/mix-up under the proper model | Initiation request and callback; store/compare state |
| `nonce` | Binds the ID Token to the OIDC request, preventing ID Token replay | OIDC authorization request and ID Token validation |
| PKCE `S256` | If the code is intercepted/leaked, an attacker lacks the matching code verifier to exchange it for tokens | Authorization request carries challenge; token request carries verifier |
| Client authentication | Confirms valid client identity at the token endpoint, per registered client type | Server-side token exchange |
| Exact redirect URI matching | Prevents sending the authorization code to unauthorized endpoints | IdP registration and callback |
| `iss`/`aud`/signature/expiry validation | Rejects ID Tokens with wrong issuer/client or expired/tampered payloads | OIDC token verification |
| HTTPS + cookie security | Prevents leaking codes, sessions, and credentials over the network | Browser ↔ app ↔ IdP |
| User/account authorization | Logged-in users can only perform permitted actions | Application security policy |

**Key implementation points:**

- Use **Authorization Code + PKCE** as required for the client type and modern best practices; do not use the Implicit flow in new designs.
- Do not send client secrets, refresh tokens, access tokens, or ID Tokens to browser JavaScript when using a server-side session architecture.
- Do not treat query parameters like `state`, `code`, or `id_token` directly as proof of user login while skipping validation/exchange.
- Prevent open redirects: never pass an unverified post-login target from query parameters into `Location`.
- For multiple IdPs, prevent issuer and client registration mix-ups; callbacks must bind to the exact authorization request/provider.
- Configure proper session cookie policies: HTTPS, `Secure`, `HttpOnly`, `SameSite` aligned with real redirect flows; enforce session fixation protection, logout, and CSRF.
- Do not disable CSRF globally just because OAuth2 Login is used. Apps with session cookies and state-changing actions still need appropriate CSRF protection.
- For apps behind a reverse proxy, process `Forwarded`/`X-Forwarded-*` **only from trusted proxies**. Wrong base URLs often cause redirect URI mismatches and can lead to severe vulnerabilities if arbitrary host headers are trusted.
- Never log authorization codes, client secrets, refresh tokens, session cookies, or full ID Tokens. Monitor login failures by error category without exposing sensitive data.

## 10. Common Errors and How to Isolate Root Causes

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `redirect_uri_mismatch` at IdP | Callback in `ClientRegistration` differs from registered address; wrong HTTP/HTTPS, host, port, or path | Verify the **exact** redirect URI and public base URL behind proxies |
| Callback reports missing/lost `state` | Session holding authorization request is gone; wrong cookie; multiple nodes not sharing sessions; mismatched state | Check `AuthorizationRequestRepository`, session/cookie settings, and routing |
| Login returns to callback without an ID Token | Provider supports only plain OAuth2; missing `openid` scope | If OIDC is needed, configure the provider and `openid` scope properly |
| `invalid_client` at token endpoint | Wrong client ID/secret, client auth method, or client registration | Verify credentials and token authentication method |
| `invalid_grant` on code exchange | Code expired/already used, mismatched redirect URI, wrong PKCE verifier | Exchange only once; check expiry, URI, and PKCE |
| Invalid ID Token | Wrong issuer, audience, nonce, expiration, or signature/key | Check metadata/clock skew/client registration; never disable validation |
| Handler has `OAuth2AuthenticationToken` yet user cannot access admin page | `ROLE_ADMIN` not mapped or local user is restricted | Distinguish authentication from authorization; inspect authorities |
| User has the right email but links to the wrong account | Using unverified/unstable email instead of issuer+sub | Design an identity link table and verify ownership |
| Subsequent requests after callback are treated as anonymous | Session not retained/saved properly, cookie not sent back, stateless session policy | Inspect `SecurityContextRepository`, cookies, and node/session store |
| Login works but API returns 401 on access token | OAuth2 Login session differs from Resource Server bearer JWT; token lacks matching audience | Configure `oauth2ResourceServer()` on the API if needed and send the right token |
| Re-logging in as another user still shows old permissions | Stale session/unclear permission refresh and logout policies | Check session invalidation, account links, and authority caching |

Effective debugging order: check that the redirect uses the right client registration → check that the callback preserves `state` and cookies → check that token exchange succeeds → check that the ID Token/user claims are valid → check who the principal in `SecurityContext` is → check app roles and local account links. Do not jump straight to editing `hasRole(...)` when the actual failure occurs at token exchange.

## 11. Self-Check Questions

1. **Why does a callback containing `code` still not prove who the user is?** The code is only a grant issued for a client/flow; the app must still match the request/`state`, exchange the code at the token endpoint, and validate the authentication result.
2. **Distinguish `id_token` and `access_token`?** An ID Token proves the OIDC result to the client after validation; an access token is used to call the corresponding resource server.
3. **Who creates Spring's `Authentication`?** Spring Security's OAuth2/OIDC login components after receiving and validating tokens and loading the principal; controllers only read the result.
4. **Does Spring Security automatically create an account in `app_user`?** No. That is an optional product step built by the application.
5. **Why use (`iss`, `sub`) instead of `email` to link users?** Subject is stable within an issuer's scope; emails can change, be unverified, or be reassigned.
6. **Is `ROLE_ADMIN` automatically derived from the `email` scope?** No. OAuth scopes and application roles are separate authority sources requiring explicit mapping.
7. **After the callback, how does the next request stay logged in?** A `SecurityContextRepository`/session mechanism restores the Authentication from the session cookie or configured state store.
8. **Has a test using `oidcLogin()` verified ID Token signatures?** No. It injects a simulated principal into the request to test controller/authorization handling.
9. **If an API is only protected with bearer JWTs, is `oauth2Login()` required?** Not necessarily. An API resource server typically uses `oauth2ResourceServer()` to validate access tokens sent on each request.

## 12. Official Documentation

- Spring Security OAuth 2.0 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html
- Spring Security OAuth 2.0 Login – core configuration: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security OAuth 2.0 Login – advanced configuration and hooks: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security OAuth 2.0 Client – Authorization Code: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html
- Spring Security Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- OIDC Core 1.0 specification: https://openid.net/specs/openid-connect-core-1_0.html
- OAuth 2.0 Security Best Current Practice (RFC 9700): https://www.rfc-editor.org/rfc/rfc9700
- PKCE (RFC 7636): https://www.rfc-editor.org/rfc/rfc7636
