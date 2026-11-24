# Distinguishing OAuth 2.0 Authorization from OpenID Connect User Authentication

**Topic:** Spring Security – federation  
**Knowledge group:** SSO Protocols

## 1. The Core: Authorization Differs from Authentication

**OAuth 2.0 (authorization)** allows an application (client) to receive limited access to a protected resource or API through an Authorization Server. The question OAuth 2.0 solves is: **"Is this client allowed to call this resource, and with what scope?"**

**OpenID Connect (OIDC, authentication)** is a standardized identity authentication layer **built on top of OAuth 2.0**. The question OIDC solves is: **"Which user was just authenticated by the identity provider for this application?"** OIDC adds the **ID Token**, identity validation rules, standard claims, and (as needed) the **UserInfo endpoint**.

Examples:

- A photo-printing app requests permission to read photos in a user's account. Permission to call the photo API is an OAuth 2.0 problem.
- A user clicks "Sign in with company account"; the app needs to know with certainty which identity signed in. This is an OIDC problem.
- A system that both logs the user in and calls APIs on their behalf can use **both OIDC and OAuth 2.0 in the same session**.

**Common point of confusion:** The Authorization Server often must authenticate the user before asking for consent. That **does not turn pure OAuth 2.0 into a login protocol**: OAuth 2.0 does not define a unified identity proof for the client. Some services provide profile APIs or custom "login with OAuth" approaches, but interoperability and identity verification are not guaranteed by OAuth 2.0. OIDC standardizes that missing part.

## 2. Roles and Terminology

| Role/Concept | Meaning |
| --- | --- |
| **Resource Owner** | Entity capable of granting access to a resource, typically the user. |
| **Client** | Application wanting to call an API or authenticate a user. |
| **Authorization Server (AS)** | System issuing authorization codes, access tokens, and handling authorization steps. |
| **Resource Server (RS)** | API hosting the resources, validating access tokens and deciding whether to allow access. |
| **OpenID Provider (OP)** | Authorization Server that supports OIDC and issues ID Tokens. |
| **Relying Party (RP)** | OIDC client that relies on the OP's authentication result to create its own login session. |
| **Scope** | Permission scope requested by the client, e.g. "orders.read"; actual granting depends on system policy. |
| **Claim** | Attribute/assertion in a token or UserInfo response, e.g. "sub", "email", "iss". |

In real applications, one service can play multiple roles; for example, a backend can serve as both an **OIDC client/RP** for web login and an **OAuth 2.0 resource server** to protect APIs.

## 3. Direct Comparison

| Criterion | OAuth 2.0 | OpenID Connect |
| --- | --- | --- |
| Primary purpose | Authorizing access to APIs/resources | Authenticating users for the client |
| What is standardized? | Grants, authorization endpoint, token endpoint, and access token usage | Adds ID Token, identity claims, validation rules, UserInfo, discovery |
| Typical indicator | Client requests scopes like "orders.read" | Authorization request includes the **openid** scope to an OIDC-supporting OP |
| Key token | **Access token** sent to the resource server | **ID token** verified by the RP for the login event; may also include an access token |
| Party validating the token | Resource server for the access token | Relying Party/client for the ID token |
| Token format | Access token may be an opaque string or JWT; not a JWT by default | ID token is a JWT |
| Question after success | "What does this token allow access to?" | "Who was authenticated, by which issuer, for which client?" |
| Can there be no user? | Yes, e.g. the **client_credentials** grant for machine-to-machine calls | OIDC login is aimed at end users |

**OIDC does not replace OAuth 2.0:** it uses OAuth 2.0's authorization mechanisms while adding an authentication result. Conversely, a valid OAuth 2.0 access token **is not automatically** an ID token.

## 4. Authorization Code Flow: Same Foundation, Different Outcome

### 4.1. OAuth 2.0 for Authorizing API Calls

1. The client redirects the browser to the **authorization endpoint**, requesting scopes needed for the API (e.g. "orders.read").
2. The Authorization Server handles login if needed, policies, and user consent if applicable.
3. The browser is redirected back to the registered **redirect URI** with an **authorization code**.
4. The client exchanges the code at the **token endpoint**; uses **PKCE** to bind the code to the initial request.
5. The Authorization Server issues an **access token**, and optionally a refresh token depending on the client and policy.
6. The client calls the API using the HTTP header **Authorization: Bearer [access token]**.
7. The Resource Server validates the token, audience, expiration, and scopes/permissions, then allows or denies access.

The outcome of this flow is the ability to access resources. The client **should not infer an OIDC-verified identity** merely from receiving an access token.

### 4.2. OIDC for User Login

1. The RP redirects the browser to the OP with an authorization request where **scope includes "openid"** (optionally adding "profile", "email").
2. The OP authenticates the user per its policy (password, passkey, MFA, existing SSO session...) and processes the request.
3. With the **Authorization Code Flow**, the OP redirects back to the RP with a code; the RP exchanges the code at the token endpoint.
4. The OP returns an **ID token** and usually an **access token**; refresh token depends on policy.
5. The RP **verifies the ID token**: signature, issuer, audience/client ID, expiration, and related conditions such as nonce if sent.
6. The RP obtains a stable identity from the **(iss, sub)** pair, maps it to an application account, and creates its own login session.
7. The RP may call the **UserInfo endpoint** with the access token when additional profile data is needed; the **sub** value from UserInfo must match the ID token.

The OIDC flow also includes an OAuth access token because a token mechanism is needed to fetch profile data or call APIs; **the ID token is the authentication data meant for the RP**. A successful login **does not mean** the user is allowed to do everything in the application: authorization by roles, policies, and business data must still be evaluated.

### 4.3. How Does SSO Relate?

When multiple applications trust the same OP, a user can navigate to a second application and be re-authenticated via the **login session at the OP** without re-entering credentials. Each application still maintains its own session/cookie and must still validate tokens according to the rules. **Single sign-on does not mean automatic synchronized logout**: logout at the RP, logout at the OP, and single logout require separate mechanisms and configurations.

## 5. Three Token Types That Must Never Be Equated

### Access Token – Used to Access Resources

- Consumed by the **resource server**; usually passed in the Bearer header.
- Can be an **opaque token** (the API needs introspection or an equivalent validation mechanism) or a **JWT** (the API verifies signature and claims).
- Scope, audience, expiration, issuer, and server policy determine access. Having a token **does not guarantee** all permissions.
- A resource server should only accept tokens **issued specifically for that API**; for JWTs, verify the appropriate **aud** claim.

### ID Token – Used to Prove an Authentication Event

- Is a **JWT** issued by the OP **for the client/RP**, not a license to call APIs.
- Important claims include: **iss** (issuer), **sub** (subject identifier), **aud** (must include the RP's client_id), **exp** (expiration), **iat** (issued-at time). **nonce** must be checked if the RP sent a nonce; **auth_time**, **acr**, **amr** may be present depending on the case.
- Merely **Base64URL-decoding to read the JSON** is not enough; you must verify the signature with a trusted key, approved algorithm, and binding claims.
- **sub** must be interpreted within the scope of **iss**. Email can change, be reused, or not be provided; do not use email as a unique identifier key.
- Do not pass an ID token as **Bearer** when calling an API simply because both ID tokens and access tokens can look like JWTs.

### Refresh Token – Requesting New Tokens

- When present, the client uses the refresh token at the token endpoint to request a new access token per the Authorization Server's policy.
- A refresh token **is not an ID token** and **must not be sent to a resource server**.
- Store carefully, restrict access, and apply rotation/sender constraints when appropriate; never log tokens.

Example: if an ID token has **aud = web-client**, while the API requires **aud = api://orders**, the API must reject that ID token even if the signature is valid. **A valid signature is only part of the condition for accepting a token.**

## 6. Spring Security: Choosing the Right Feature

Spring Security provides distinct roles:

| Scenario | Spring Security Feature | Input/Output |
| --- | --- | --- |
| Web login with an OIDC-capable IdP | **oauth2Login()** and client registration with **openid** scope | Verifies ID token, creates Authentication with **OidcUser** |
| OAuth 2.0 client needing to call an API | **oauth2Client()** / OAuth2AuthorizedClient | Manages authorization and access tokens to call APIs |
| API validating Bearer JWT | **oauth2ResourceServer().jwt()** | Verifies JWT access token, creates Authentication with **Jwt** principal |
| API validating opaque token | **oauth2ResourceServer().opaqueToken()** | Introspection via Authorization Server |
| Issuing codes/tokens/ID tokens | Dedicated authorization server/OP service | Not the responsibility of **oauth2Login()** or **resource server** |

**Note:** When a client registration includes the **openid** scope, Spring Security switches to OIDC handling (e.g. **OidcUserService**). Without this scope, OAuth 2.0-based login uses a provider profile-fetching mechanism (e.g. **DefaultOAuth2UserService**) and **lacks standard OIDC authentication guarantees**.

### 6.1. Example Configuration: Spring Boot 3.x, Spring Security 6.x, Java 17+

The following example is for **an existing Spring Boot project** (Servlet/MVC). It includes an OIDC login page and an API protected by JWT access tokens. You need to register the client on a real OP, configure the redirect URI, and have the OP issue tokens with matching audience/scope; **the code cannot log in to the illustrative "example.org" domain**.

Required dependencies in the **dependencies** section of pom.xml (project using a compatible Spring Boot parent/BOM):

~~~xml
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
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

**application.yml** – replace the issuer with the real OP URL; supply client ID/secret via environment variables or a secret manager, never hard-code secrets into Git:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          training:
            provider: training
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid, profile, email
        provider:
          training:
            issuer-uri: https://login.example.org/realms/training
      resourceserver:
        jwt:
          issuer-uri: https://login.example.org/realms/training
          audiences:
            - api://training-api
~~~

- Spring uses **issuer-uri** to discover metadata/trusted keys from a compatible provider. The OP must expose a valid discovery endpoint.
- Register the client's redirect URI on the OP, which by Spring default is **{baseUrl}/login/oauth2/code/{registrationId}**; with registrationId "training", the application typically uses **/login/oauth2/code/training**.
- Login initiation URL provided by Spring: **/oauth2/authorization/training**.
- The "audiences" entry requires JWTs for the API to contain **api://training-api**. Configure the OP to issue tokens with that audience; do not assume the ID token or every access token satisfies it.
- The **openid/profile/email** scopes serve login; the API example below requires the **data.read** scope from a **separate, appropriate access token**. Scope names are a system convention and must be permitted by the OP.

**SecurityConfig.java** (example package **com.example.demo**):

~~~java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http.securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasAuthority("SCOPE_data.read"))
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(AbstractHttpConfigurer::disable);
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

**DemoController.java** (same package):

~~~java
package com.example.demo;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/me")
    public String me(@AuthenticationPrincipal OidcUser user) {
        return "OIDC subject: " + user.getSubject();
    }

    @GetMapping("/api/data")
    public String data(@AuthenticationPrincipal Jwt jwt) {
        return "API subject: " + jwt.getSubject();
    }
}
~~~

In a Spring Boot application with a **@SpringBootApplication** class in package **com.example.demo** (or a parent package), run with **mvn spring-boot:run** after configuring the OP, client, and environment variables. This is a **complete configuration and controller snippet to place into a Boot project**, not a standalone Maven project since it still requires a parent pom.xml, main class, and running IdP.

**Accurate behavior explanation:**

1. Unauthenticated browser visits **/me**: the web filter chain redirects to the OIDC login flow. After successful authentication, the controller receives **OidcUser** and returns the verified subject (string depends on the account, no fixed stdout).
2. Request **GET /api/data** carries a **valid Bearer JWT access token** with audience **api://training-api** and scope **data.read**: the API chain creates a **Jwt** principal and returns the subject from the access token.
3. Missing/expired/wrong-issuer or wrong-audience tokens typically result in **401 Unauthorized**; an accepted token lacking **SCOPE_data.read** results in **403 Forbidden**.
4. An ID token issued for the web client **cannot be used as an access token** to call **/api/data**.
5. CSRF is disabled **only on the stateless Bearer-token API** in the example; the web chain retains default CSRF protection for state-changing operations. Do not mechanically disable CSRF across the entire application.

If the application only performs web login, the API JWT chain is unnecessary. If the application is only an API, **oauth2Login()** is unnecessary. If the access token is opaque, replace the JWT configuration with corresponding introspection.

### 6.2. Application Access Permissions Differ from Login Result

Once you have an **OidcUser**, you can map **(issuer, subject)** to an internal user table, load roles or permissions from the business system, and then decide read/write permissions on data. **Successful login does not implicitly grant admin permissions**. Even if the IdP returns group/role claims, the application must understand the semantics of those claims and apply a trusted policy.

In a resource server, Spring Security typically converts each scope in a JWT into an authority prefixed with **SCOPE_**; for example, scope **data.read** becomes **SCOPE_data.read**. This is an API permission-control mechanism, not an indicator that a browser performed an OIDC login.

## 7. Mandatory Security Checks in Production Deployments

1. **Use Authorization Code Flow and PKCE**; public clients must use PKCE, and confidential clients should use PKCE per RFC 9700. Use the **S256** method. Avoid implicit flow and Resource Owner Password Credentials (ROPC) in new designs.
2. **Request/response binding:** protect the redirect URI, verify **state**/appropriate CSRF protection, use **nonce** when applicable, and check nonce in the ID token if sent. Never build a custom callback that bypasses the library's verification mechanisms.
3. **Verify the ID token at the RP:** signature/algorithm, **iss**, **aud = client ID**, **exp**, and requirements for nonce, azp, and authentication time depending on context. Never trust a JWT merely because its payload can be read.
4. **Verify the access token at the API:** signature/JWKS or introspection, expiration, **issuer**, **API-specific audience**, scope/permissions, and the right token type for the purpose. In Spring Boot, configuring **issuer-uri** does not mean business audiences are checked automatically; add **audiences** or an appropriate validator.
5. **Protect secrets and tokens:** TLS, secret manager, reasonably short token lifetimes, secure storage, and never log access/ID/refresh tokens or sensitive data.
6. **Identity stability:** use the **(iss, sub)** pair as the federated identifier; do not assume **email** is always present, verified, or immutable. The **email** scope is only a claim request and does not guarantee the OP returns it completely.
7. **Distinguish sessions:** the SSO session on the OP, the application session, and the access/refresh token lifecycle are distinct states; logout, session expiration, permission revocation, and reauthentication must be designed separately.

## 8. Scenario Exercises and Answers

**Scenario A:** An application reads the user's calendar using an access token, without receiving an ID token. Can it claim "OIDC-compliant login completed"?  
**Answer:** Not yet. The application has obtained OAuth 2.0 API calling authorization; it lacks OIDC identity proof verified for the client itself.

**Scenario B:** After OIDC login, the client receives an ID token with **aud = portal-web**. Can it be used to call the **orders-api** API?  
**Answer:** No. The ID token is for the RP. The API requires an access token issued for the API, verifying the corresponding audience and permissions.

**Scenario C:** A nightly service fetches reports using **client_credentials**. "Who logged in"?  
**Answer:** This grant authenticates/authorizes a machine-to-machine client, and does not represent an end-user login via OIDC.

**Scenario D:** Two applications share an OP; accessing the second application does not prompt for a password again. Why must the ID token still be verified?  
**Answer:** The OP may reuse the SSO session, but each RP must verify the response specifically intended for its own client before creating a local session; SSO does not eliminate identity proof verification.

**Scenario E:** A JWT access token has a valid signature and is unexpired, but **aud** targets a different API.  
**Answer:** The current API must reject the token; checking only the signature and exp is insufficient.

## 9. Protocol Selection Checklist

- **Only need a system to call APIs under granted permissions:** OAuth 2.0 (access token + resource server).
- **Need federated user login/SSO:** OpenID Connect on OAuth 2.0 (ID token + OIDC validation).
- **Need both login and API calls:** OIDC for authentication at the RP, OAuth 2.0 access tokens for each resource server.
- **Need internal authorization:** apply the application's roles/permissions/policies in addition to authentication and token scope checks.
- **Machine-to-machine without an end user:** consider OAuth 2.0 client_credentials; do not infer an OIDC login.

**Remember:** **OAuth 2.0 = what the application is allowed to do with a resource. OIDC = which user was authenticated for the application.** ID tokens target the client/RP; access tokens target the API/resource server.

## 10. Reference Standards

- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, OIDC Code Flow, claims, and validation rules.
- [RFC 6749 – OAuth 2.0](https://www.rfc-editor.org/rfc/rfc6749): roles, grants, and tokens.
- [RFC 9700 – OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): PKCE, CSRF, and current security recommendations.
- [Spring Security – OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): OIDC login and client registration.
- [Spring Security – JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): validating JWT access tokens, issuer, scope, and audience.
- [Spring Boot – OAuth 2.0](https://docs.spring.io/spring-boot/reference/security/oauth2.html): client and resource server configuration.
