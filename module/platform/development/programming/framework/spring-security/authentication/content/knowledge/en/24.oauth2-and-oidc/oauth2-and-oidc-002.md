# Roles of Client, Authorization Server, Resource Server, and End User in OAuth 2.0 / OpenID Connect

## 1. Problem: Who Does What When a User Logs In and Calls an API?

A task management application wants to let users **log in through a centralized identity system** and then **read reports via an API**. There are four actors with distinct responsibilities:

- **End user**: the person currently interacting, who can decide or be permitted by policy to allow the application to access a resource under their management.
- **Client**: the application wanting to access resources on the user's behalf, such as a task management web app or mobile app.
- **Authorization server (AS)**: the service that authenticates/approves permissions and issues tokens to the client, such as an identity system supporting OAuth 2.0/OIDC.
- **Resource server (RS)**: the service holding protected resources, such as a reports API, which receives and validates the access token before serving requests.

**Foundational distinction:** OAuth 2.0 primarily defines the mechanism for **delegated resource access authorization**. OpenID Connect (OIDC) is a **user identity authentication** layer built on OAuth 2.0; OIDC adds ID tokens and rules for verifying login information. Do not assume that seeing OAuth 2.0 means you already have a complete login protocol.

Per RFC 6749, OAuth 2.0 defines four **roles**: `resource owner`, `client`, `authorization server`, and `resource server`. When the `resource owner` is a person, that person is called an **end user**. In OIDC, other key terms are `End-User`, `Relying Party` (RP, i.e., OIDC client), and `OpenID Provider` (OP, an identity service acting as an authorization server supporting OIDC).

## 2. Responsibility and Trust Boundary Table

| Actor | Holds / Processes | Must Do | Must NOT Do |
| --- | --- | --- | --- |
| **End user / resource owner** | Identity, rights over data, decision to allow within policy | Interact with client; authenticate at AS/OP when requested; review permissions requested by the app | Send password to the client in Authorization Code flow; mint access tokens themselves |
| **Client / RP** | `client_id`, transaction session, state, code verifier; may hold a secret if confidential | Initiate authorization request, receive authorization code, exchange code for tokens, call RS; with OIDC validate ID token to create login session | Self-sign tokens impersonating the AS; send ID token as a bearer access token to an API; trust unverified token data |
| **Authorization server / OP** | Registered client details, authorization policies, authorize and token endpoints, signing keys | Authenticate end user when needed, evaluate requests and policies, issue access tokens and optionally refresh tokens; with OIDC issue ID tokens | Be assumed by default to store all API resources; issue tokens with unrestricted audience/scope |
| **Resource server** | Protected APIs/resources, access policies, information to validate tokens | Accept only valid access tokens for **its own API**, enforce authorization by scope/claim/business rules | Use a client-facing ID token as proof of API access; accept a token merely because the JWT decodes |

**Role assignment example:**
- User named An: `end user` and typically the `resource owner` of personal datasets.
- Web app `reports-web`: `client`; if using OIDC for login, it is also a `Relying Party`.
- Service `login.example.org`: `authorization server`; when providing OIDC, called an `OpenID Provider`.
- API `reports-api`: `resource server`.

Product or library names do not determine roles by themselves. A Spring Boot application can act as both an OAuth2 Client (calling other APIs) and a Resource Server (protecting its own APIs). A system may co-locate AS and RS in the same infrastructure, but must keep token issuance and resource-level authorization responsibilities separate.

## 3. Resource Owner and End User: Similarities and Differences

A **resource owner** in OAuth is an entity capable of granting access to a resource; it does not have to be an individual person. When a resource belongs to a user and that user approves access, the `resource owner` is the `end user`.

An **end user** in OIDC is the person authenticated by the OP, typically logging in through a browser. Do not conflate these three concepts:
1. **The authenticated user**: an end user whose identity is verified by the OP.
2. **The authorizing party**: could be the end user, an organization, or a preconfigured policy.
3. **The subject represented by the token**: depends on the grant and token type; could be a user, a client, or a service account.

For instance, the `client_credentials` grant is typically machine-to-machine communication: the client requests an access token based on its own identity/permissions or pre-established authorization. **There is no step where an end user enters a password or clicks consent**, nor is there necessarily an ID token. Do not force every OAuth 2.0 flow to involve an end user.

Note also: a “Grant access” (consent) screen does not always appear. The authorization server may rely on organizational policy, previously granted permissions, or a prior confirmation experience. Not seeing a consent prompt does not mean authorization checks did not occur.

## 4. Client: The Application Requesting and Using Tokens

### 4.1. Client Is Not Synonymous with Browser

`Client` is the application participating in OAuth: a web backend, SPA, mobile app, desktop app, or service. **Browser/user-agent** is usually just the transport medium taking the user to the AS and back to the client in the Authorization Code flow.

For example, a user opens a web page in Chrome:
- **Chrome** is the user-agent.
- **The web backend** managing sessions and performing token exchange can be the OAuth client.
- **The Chrome user** is the end user.
- Not every HTTP request originating from a browser turns the browser into an independent OAuth client.

### 4.2. Confidential Client and Public Client

| Client Type | Where It Runs and Ability to Keep Secrets | Implication |
| --- | --- | --- |
| **Confidential** | Server-side component capable of keeping credentials secret | Can authenticate the client at the token endpoint with a secret or stronger mechanism; still must protect the code flow |
| **Public** | Browser-based SPA, mobile/desktop app distributed to user devices | Cannot treat a client secret embedded in code as secret; requires Authorization Code + PKCE and flow-binding safeguards |

`client_id` is a registration identifier, **not a secret**; `client_secret` is meaningful as a secret only when the client can protect it. A frontend SPA does not become a confidential client just because a `client_secret` string appears in the JavaScript bundle.

The client must properly configure registered `redirect_uri` values, request/response state, scopes, and token endpoints; send access tokens only to the intended RS. A backend serving a browser usually uses its own session for the UI; having an external API use access tokens does not mean the web app's session cookie stops existing.

## 5. Authorization Server and OpenID Provider

The authorization server handles the authorization protocol. Common responsibilities:

1. **Authorization endpoint**: receives requests from the client via the user-agent, authenticates the end user when needed, enforces policies/consent, and returns an authorization code via redirect.
2. **Token endpoint**: verifies the authorization code, `redirect_uri`, PKCE `code_verifier`, and client authentication (if applicable); then issues tokens.
3. **Token lifecycle**: determines issuer, lifetime, audience, scope, grant, and depending on the scenario refresh/revocation/introspection and security policies.
4. **Metadata/keys**: provides discovery metadata, JWKS if using signed tokens, and specification endpoints.
5. **OIDC additions**: issues **ID tokens** containing end-user authentication claims; may provide a `userinfo_endpoint` for the RP to read user info when appropriately authorized.

The AS may delegate password/MFA verification to an identity store or external system; therefore, **the AS is not necessarily the user database**. With OIDC, the OP must support proper authentication rules and ID token issuance, not merely act as an OAuth AS with an access-token endpoint.

**Distinguishing authentication from authorization:** The AS can confirm “who An is,” but the reports API must still decide whether An is allowed to read report #42. A `scope` like `reports.read` only represents the permission range granted at the token level; specific ownership/tenant rules remain the responsibility of authorization at the RS or business layer.

## 6. Resource Server: Where Data Is Actually Protected

The resource server receives requests such as:

~~~http
GET /api/reports/42 HTTP/1.1
Host: api.example.org
Authorization: Bearer eyJ...redacted
~~~

The RS must determine whether the token is valid to access **its API**. For a JWT access token, validation steps typically include allowed signature/algorithm, `iss` issuer, `exp` and `nbf` validity times, matching **`aud` audience**, as well as scope/claim/role and per-resource access permissions. For opaque tokens, the RS typically uses token introspection or a verification mechanism supported by the AS. The token format depends on the AS and the AS–RS contract; **an access token is not required to be a JWT**.

**Key milestone:** successfully parsing a JWT's Base64 payload is not token validation; an attacker can craft JWT data that is unsigned or signed with the wrong key. Checking scopes while skipping issuer/audience/signature checks is a security vulnerability.

If the token is valid but lacks the required permissions, the RS rejects the request. In the standard bearer token model: `401 Unauthorized` when the token is missing or invalid; `403 Forbidden` when the principal is authenticated but denied access. Actual scenarios may have differing response rules depending on standards/setup, so test against the specific service.

### Resource Server vs. User-Info Service

The OIDC `UserInfo Endpoint` returns permitted identity information to the RP when presented with a suitable access token. It is also a protected resource endpoint, yet it is **not a business API that the client can use arbitrarily**. The reports API and UserInfo may reside on different services with different token audiences. Do not use the client's ID token to access the reports API.

## 7. Authorization Code + PKCE Flow: Tracing Each Role

This is the typical flow for applications with interactive end users, using `scope=openid` for OIDC. Study sequence:

~~~text
End user          Client / RP           Authorization Server / OP       Resource Server
   |                  |                            |                          |
   |-- Clicks "Sign in" ->|                        |                          |
   |                  |-- Create state, PKCE, nonce ->| (prepare request)     |
   |<-- Redirect to authorization endpoint --------|                          |
   |------------------ Follow browser ------------>|                          |
   |<----------------- Authenticate / consent -----|                          |
   |------------------ Callback code + state ----->| Client receives via browser |
   |                  |-- Exchange code + code_verifier --------------------->|
   |                  |        (connection to AS token endpoint)              |
   |                  |<-- access_token + id_token (OIDC) -- AS               |
   |                  |-- Bearer access_token ------------------------------->|
   |                  |<--------------------- API response -------------------|
   |<-- Display data -----|                        |                          |
~~~

To avoid misunderstanding from ASCII lines in the diagram, the actual connections are:
1. **End user → Client**: chooses an action requiring login/access.
2. **Client → user-agent → AS**: sends authorization request containing `client_id`, `redirect_uri`, `response_type=code`, scope, `state`, `code_challenge`; with OIDC, typically includes `nonce` per authentication design.
3. **AS ↔ End user**: AS performs login check (possibly SSO/MFA) and policy/consent.
4. **AS → user-agent → Client**: redirects back to `redirect_uri` with **authorization code** and `state` (or an error notice).
5. **Client → AS token endpoint**: exchanges code for tokens, sending `code_verifier` and client authentication if it is a confidential client.
6. **AS → Client**: returns access token; with OIDC Authorization Code flow includes ID token; may include refresh token per issuance conditions.
7. **Client → RS**: attaches **access token** in the `Authorization: Bearer ...` header to fetch data.
8. **RS → Client → End user**: RS validates token, applies authorization; client presents data to the user.

**Security responsibilities split by role:** AS validates token issuance; Client protects the authorization response, state, PKCE, and received tokens; RS must independently perform token validation and authorization for the API. Successful authentication at the AS never excuses the RS from checking permissions.

### 7.1. state, PKCE, and nonce Solve Different Problems

- **`state`**: data binding the request to the callback, helping prevent CSRF and transaction mix-ups. The client verifies the returned state matches the initiated transaction.
- **PKCE**: client generates a random `code_verifier`, sends `code_challenge` (preferring the `S256` method) in the authorization request, and sends the actual verifier in the token request. This makes stolen codes difficult to exchange for tokens. Public clients must use PKCE; RFC 9700 recommends it for confidential clients as well.
- **`nonce` (OIDC)**: a transaction value in the authentication request reflected in the ID token so the client can detect replayed or swapped tokens per OIDC rules. Nonce does not replace checking the ID token's signature, issuer, or audience.

Do not encode user passwords into these fields; do not send `code_verifier` in the authorization request when using S256. Values must be fresh, sufficiently random, and bound to the right transaction session.

## 8. Authorization Code, Access Token, ID Token, Refresh Token

| Component | Who Creates / Who Receives | What It Is Used For | What It Must NOT Be Used For |
| --- | --- | --- | --- |
| **Authorization code** | AS returns to client via callback | Client exchanges it for tokens at the token endpoint, bound by time/transaction | Calling RS as a Bearer token |
| **Access token** | AS issues to client; client sends to RS | Lets RS decide whether to accept the resource request within granted authorization | Inferring RP login identity on its own like an ID token |
| **ID token** (OIDC) | OP issues to RP/client | Asserts that the OP authenticated the end user along with identity claims; RP must verify | Acting as a Bearer token to access business APIs |
| **Refresh token** (if issued) | AS issues to permitted client; client sends to AS token endpoint | Requesting new access tokens per policy | Sending directly to RS or putting in URLs/public logs |

**Different audiences:**
- An ID token has `aud` targeting the **RP's client_id**.
- An access token is issued for acceptance by target RSs; audience/authorization details must be designed and validated per AS–RS policy.

Both ID tokens and access tokens may use JWT format in a given implementation, yet **having the same format does not mean having the same purpose**. Always check the proper token type/use-case, issuer, signature, lifetime, and audience. Do not store sensitive tokens in logs, query strings, or places readable by untrusted JavaScript.

## 9. How the Roles Appear in Spring Security

Spring Security offers feature modules: **OAuth2 Client**, **OAuth2 Login** (built on Client), and **OAuth2 Resource Server**. **Authorization Server** is a separate responsibility, handled either by an external Identity Provider or **Spring Authorization Server**. Adding client/resource-server starters **does not automatically create an authorization server**.

| Logical Role | Java Application Capability / Configuration | Common Usage |
| --- | --- | --- |
| Client/RP (web servlet) | `spring-boot-starter-oauth2-client`, `oauth2Login()`, `ClientRegistrationRepository` | Web app redirects to OP, handles callback, creates login session |
| Client calling APIs | `oauth2Client()`, `OAuth2AuthorizedClientManager` | Service/backend obtains and attaches Bearer access tokens when calling APIs |
| Resource Server (servlet) | `spring-boot-starter-oauth2-resource-server`, `oauth2ResourceServer(o -> o.jwt(...))` | REST API validates tokens, scopes, and authorization |
| Authorization Server/OP | Managed IDP or separately configured Spring Authorization Server | Exposes authorize/token/JWKS/discovery, issues tokens |
| End user | Interactive user, may become an `OidcUser` principal at the RP | Not a separate service/bean in the OAuth protocol |

For **reactive WebFlux**, the roles are identical, but the Java APIs change to `ServerHttpSecurity`, `SecurityWebFilterChain`, `ReactiveClientRegistrationRepository`, and corresponding OAuth2 configurations; do not copy the servlet code below verbatim for reactive apps.

### 9.1. Spring Boot Client/RP Configuration Example (Illustrative, Requires an OP)

A Servlet web app using Java 17+, Spring Boot 3.3.x, and dependencies:

~~~groovy
// Excerpt of build.gradle dependencies; requires a configured Spring Boot 3.3.x project.
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Security filter chain:

~~~java
// SecurityConfig.java in a Spring Boot Servlet application; complete Java class.
package demo.client;

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
                .authorizeHttpRequests(authorize -> authorize
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }
}
~~~

Example `application.yml` (host and client registration are illustrative only; requires a real/provisioned OP in a lab environment):

~~~yaml
server:
  port: 8080
spring:
  security:
    oauth2:
      client:
        registration:
          reports-web:
            provider: training-op
            client-id: reports-web
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid, profile
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          training-op:
            issuer-uri: https://login.example.org/realms/training
~~~

The environment must supply the `OIDC_CLIENT_SECRET` variable; never commit real secrets. The OP must expose valid discovery metadata and have the client registered with a matching redirect URI; HTTPS is mandatory in real environments. The standard login initiation link is `/oauth2/authorization/reports-web`, and the default callback is `/login/oauth2/code/reports-web`. With the `openid` scope, Spring Security uses the OIDC flow and validates the ID token per the OP configuration.

**Example limitations:** the snippet above demonstrates client-side responsibility; it does not provide an OP at the illustrative domain and cannot execute a full flow without a real OP and client registration. PKCE for confidential clients and transaction-binding policies must be configured/verified according to your Spring Security version; do not conclude that declaring `oauth2Login()` alone automatically enforces every RFC 9700 recommendation.

### 9.2. Resource Server Example Accepting Bearer JWT

In a separate Spring Boot API, the minimal Spring Boot dependencies are:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

File `src/main/java/demo/api/ApiApplication.java`:

~~~java
package demo.api;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ApiApplication {
    public static void main(String[] args) {
        SpringApplication.run(ApiApplication.class, args);
    }

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/me")
                            .hasAuthority("SCOPE_reports.read")
                        .anyRequest().permitAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }

    @GetMapping("/api/me")
    public Map<String, String> me(@AuthenticationPrincipal Jwt jwt) {
        return Map.of("subject", jwt.getSubject(), "status", "authorized");
    }
}
~~~

Separate `application.yml` for the API:

~~~yaml
server:
  port: 8081
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.org/realms/training
~~~

This snippet relies on `scope`/`scp` in the access token, which Spring Security normally maps to authorities prefixed with `SCOPE_`. Only a token containing `reports.read` satisfies `SCOPE_reports.read`; if the OP issues a different claim structure, you must configure a converter. **Production deployments must validate the audience intended for the API and specific security requirements**; merely having `issuer-uri` does not mean every `aud` policy is enforced as expected. JWT verification requires valid issuer discovery/JWKS. The illustrative domain does not exist to serve live flows.

Commands to observe once you have a real AS and a valid access token for the API:

~~~bash
# Without bearer credential: expect 401 from the protected endpoint.
curl -i http://localhost:8081/api/me

# With a valid access token matching issuer/audience/permissions:
curl -i -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  http://localhost:8081/api/me
~~~

The second command returns data only when the token and policy match; `YOUR_ACCESS_TOKEN` is merely an illustrative placeholder, not a usable token. The API does not need to know the end user's password or hold a client secret just to validate an appropriate access token.

## 10. Standalone Java 17: Inspecting the Responsibility Diagram

The following exercise only prints a **role diagram** to help remember who is responsible for each step. It does not generate tokens, perform cryptography, and is **not a real OAuth server/client**. Create `OAuthRolesDemo.java`:

~~~java
import java.util.List;

public class OAuthRolesDemo {
    record Role(String name, String responsibility) {}

    public static void main(String[] args) {
        List<Role> roles = List.of(
                new Role("End user", "requests and logs in at AS/OP"),
                new Role("Client", "requests code, exchanges token, calls API"),
                new Role("Authorization server", "authenticates, authorizes, and issues tokens"),
                new Role("Resource server", "validates access token and protects API")
        );

        roles.forEach(r ->
                System.out.println(r.name() + ": " + r.responsibility()));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac OAuthRolesDemo.java
java OAuthRolesDemo
~~~

Exact output:

~~~text
End user: requests and logs in at AS/OP
Client: requests code, exchanges token, calls API
Authorization server: authenticates, authorizes, and issues tokens
Resource server: validates access token and protects API
~~~

The learning takeaway is **separating responsibilities into four logical entities**. In real systems, when writing code, use vetted OAuth 2.0/OIDC SDKs/libraries (such as Spring Security); do not invent custom ways to sign, verify, or store tokens based on this diagram.

## 11. Three Scenarios Comparing Roles

### A. Web App Reading an API with User Presence

An clicks “View report” on `reports-web`. The web app redirects An to the OP, receives the code, exchanges it for tokens, and sends the access token to `reports-api`. If An already has an SSO login at the OP, the password entry step may be skipped, yet the OP's role does not change.

- An: end user/resource owner (if An has authority over the data).
- `reports-web`: OAuth Client + OIDC RP.
- OP: authorization server authenticating/issuing tokens.
- `reports-api`: resource server protecting the reports.

### B. Nightly Batch Job Calling an API Without an End User

`nightly-export` runs on a schedule and uses `client_credentials` to request a token. There is no browser, redirect, or end-user login ID token.

- `nightly-export`: confidential client and may act as a machine-authorized principal.
- AS: authenticates the client and issues an access token per scope/policy.
- RS: validates the job's token/permissions and handles the API request.
- End user: does not participate in this transaction.

### C. A Spring Boot App Acting as Both Client and Resource Server

A gateway exposes `/api/admin` to external clients while simultaneously calling `billing-api` using its own token. The same process can hold two roles:
- For `/api/admin`, the gateway is a **resource server**.
- When the gateway calls `billing-api`, the gateway is a **client**.
- `billing-api` is the **resource server** in the second relationship.
- The AS/OP may be the same provider, though client registrations and audience/access policies may differ.

Therefore, **draw roles per HTTP/token relationship**, rather than attaching a single fixed label to the entire system.

## 12. Common Mistakes and Consequences

1. **“The client is the user.”** Wrong: the client is the application; the end user is the person using it. The browser acts as user-agent, not necessarily as the OAuth client.
2. **“The authorization server holds the reports, so it grants API reads directly.”** Wrong: the AS issues tokens per policy; the RS manages the API and must check both the token and specific resource access permissions.
3. **“Once logged in with OIDC, the access token and ID token are interchangeable.”** Wrong: the ID token targets the RP, while the access token targets the RS; their audiences and purposes differ.
4. **“The resource server can trust any parseable JWT.”** Wrong: you must verify signature, issuer, expiration, audience, and permissions; never accept forged tokens or tokens issued for another API.
5. **“`scope=openid` means permission to read all profile data.”** Wrong: `openid` triggers an OIDC authentication request; data scopes/claims and RS authorization are separate layers.
6. **“There must be a consent popup on every turn.”** Wrong: the AS can apply previously granted permissions or organizational policies; the client must not try to bypass AS rules.
7. **“SPAs keep secrets safe because JavaScript is minified.”** Wrong: code distributed to browsers cannot safely keep a client secret; use the public-client pattern with PKCE.
8. **“Password grant is faster.”** Per RFC 9700, the Resource Owner Password Credentials grant **must not be used** in modern designs; never collect user passwords through a client to exchange for tokens.
9. **“Implicit flow is the default choice for frontends.”** RFC 9700 recommends avoiding the implicit grant due to token leakage/replay risks; prefer Authorization Code + PKCE with proper controls.
10. **“Spring Security Resource Server automatically creates `/authorize` and `/token` endpoints.”** Wrong: that is the AS's responsibility; the Resource Server starter only helps validate tokens and protect resources as configured.
11. **“A client with a valid token can always view every record under that scope.”** Wrong: the RS must check tenant, ownership, business roles, and per-object policies when required.
12. **“Send the refresh token to the API to extend a request.”** Wrong: a refresh token is a credential for the AS token endpoint, not for the RS.

## 13. Self-Check Questions

**Question 1.** When an end user signs in on the OP's page, which component must validate the ID token before using identity information for the app session?  
**Answer:** The OIDC client/Relying Party. The OP issues the ID token; the client validates it per OIDC rules.

**Question 2.** When an API receives `Authorization: Bearer ...`, who must ensure the token was issued specifically for this API and has sufficient scope?  
**Answer:** The resource server, via its token validation and authorization pipeline.

**Question 3.** A service uses `client_credentials` with no interactive user. Is a mandatory role missing?  
**Answer:** No; OAuth includes grants that do not require end-user interaction at token issuance time.

**Question 4.** `reports-web` is a web frontend and `reports-api` is an internal backend. Can the same backend be configured as both client and resource server?  
**Answer:** Yes, because roles depend on the transaction type; you must clearly design the tokens/audiences and corresponding security filter chains.

**Question 5.** The OP issues an ID token with `aud=reports-web`. Should this ID token be sent to `reports-api` as an access token?  
**Answer:** No. The ID token is intended for the RP; the RS requires an access token issued for the appropriate resource.

**Question 6.** An access token has a verified signature and is unexpired, yet `aud` lists only API A; can API B accept it?  
**Answer:** No if the token is not intended for B per policy; a valid signature does not automatically expand audience scope.

### Checklist When Reading OAuth/OIDC Architectures

- [ ] Identify who the end user/resource owner is and whether they participate in the transaction.
- [ ] Clearly name the client and its client type (public/confidential).
- [ ] Identify the AS/OP; distinguish login from token issuance.
- [ ] Identify each protected RS and its expected audience.
- [ ] Match each token to its recipient: ID token → RP, access token → RS, refresh token → AS.
- [ ] For user-interactive flows, use Authorization Code + PKCE, and validate state, nonce/ID token if using OIDC.
- [ ] For machine-to-machine flows, consider client credentials and dedicated permission policies.
- [ ] Evaluate permissions inside the API, avoiding reliance on a mere “logged in” state.
- [ ] Do not log authorization codes, secrets, access/refresh tokens, or sensitive information.

## 14. Specifications and Spring Documentation

- [RFC 6749 — OAuth 2.0 Authorization Framework, `1.1 Roles](https://www.rfc-editor.org/rfc/rfc6749#section-1.1): official definition of the four OAuth roles.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): End-User, OP, RP, ID tokens, and validation rules.
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): the PKCE mechanism.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): recommendations on Authorization Code, PKCE, and flows to avoid.
- [Spring Security — OAuth2 Client, Login, Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/): how Spring Security applications fulfill each role.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): examples of Bearer JWT validation.

**Key takeaway:** **End users** interact/are authenticated; **clients** request authorization and use tokens; **authorization servers** issue tokens per policy; **resource servers** validate tokens and protect data. OIDC adds ID tokens so the **client** knows who was just authenticated, while API access permissions must still be enforced by the **resource server**.