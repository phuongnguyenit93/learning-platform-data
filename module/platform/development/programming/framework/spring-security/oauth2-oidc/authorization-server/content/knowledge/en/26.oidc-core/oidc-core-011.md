# Distinguishing Built-In OIDC Capabilities From Extensions You Must Implement

## Lesson Objectives

In the **OIDC Core and ID Token** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, this lesson helps you determine which parts of OpenID Connect (OIDC) an application built with **Spring Security**, **Spring Authorization Server**, and **Spring Boot** actually supports out of the box, which parts simply require enabling/configuring, which parts require business-logic extensions, and which parts belong to separate OIDC specifications.

OIDC is an identity layer on top of OAuth 2.0. A system that issues JWT access tokens and runs the Authorization Code Flow is not automatically an OIDC-compliant OpenID Provider. OIDC also specifies Discovery, ID Tokens, UserInfo, Authentication Requests, claims, logout, and numerous optional extensions.

The mere presence of a framework endpoint or configurer does not mean every requirement of the specification is fully implemented. For example:

- Spring Authorization Server 1.5.8 includes built-in OIDC Provider Configuration, UserInfo, and RP-Initiated Logout once OIDC is enabled.
- OIDC Dynamic Client Registration also has an implementation, yet the endpoint is **disabled by default** and requires a bearer access token with the right scopes.
- ID Tokens can be issued by the framework in the OIDC Authorization Code Flow, yet **`max_age`**, **`auth_time`**, ACR/MFA, pairwise subjects, dynamic claim release, or account linking policies may still require application logic.
- RP-Initiated Logout does not imply Session Management, Front-Channel Logout, or Back-Channel Logout exists.
- Request Objects, `claims` requests, `prompt`, locales, and optional OIDC parameters must be evaluated against the actual behavior of your version and configuration.

### Expected Outcomes

After this lesson, you will be able to:

1. Distinguish an OAuth 2.0 Authorization Server, OpenID Provider (OP), Relying Party (RP), and OAuth2 Resource Server.
2. Classify features as **built-in**, **built-in but must be enabled**, **requires configuration**, **requires custom implementation**, **separate specification**, or **unverified**.
3. List the OIDC endpoints included in Spring Authorization Server 1.5.8 and identify which are disabled by default.
4. Understand the boundaries among Provider Configuration/Discovery, ID Tokens, UserInfo, RP-Initiated Logout, and Dynamic Client Registration.
5. Use Spring Authorization Server extension points while preserving standard validators, authentication providers, and response handlers.
6. Recognize capabilities that do not appear automatically, such as `max_age` enforcement, `auth_time`, ACR/MFA policies, pairwise subjects, claim policies, front/back-channel logout, and federation.
7. Build a capability matrix, accurate metadata, and integration/conformance tests for your deployed version.
8. Avoid advertising or claiming an OIDC feature simply because the framework accepts a parameter or has a similarly named API.

> **Running scenario:** A company deploys **auth.example.com** using Spring Authorization Server. The product team wants to publish it as an OpenID Provider for **employee-portal**, **mobile-app**, and partners. Before release, the team must answer: Does Discovery work? Do ID Tokens follow the contract? Does UserInfo filter by scope? Does logout notify RPs? Who can use Dynamic Client Registration? Where are MFA and pairwise subject requirements enforced?

## 1. Distinguishing Specification Layers

### 1.1. OAuth 2.0 and OpenID Connect Solve Different Problems

| Component | Role | Primary Output |
|---|---|---|
| OAuth 2.0 Authorization Server | Issues access tokens to clients per grants and authorization policies. | Access tokens and related tokens. |
| OpenID Provider (OP) | Authenticates End-Users and provides the OIDC identity layer. | ID Tokens, UserInfo, and OIDC Provider Metadata. |
| Relying Party (RP) / OIDC Client | Sends Authentication Requests, verifies ID Tokens, and consumes identity. | Application login session. |
| OAuth2 Resource Server | Protects APIs using access tokens. | Decides whether API requests are permitted. |

A JWT containing a **`sub`** claim does not automatically become an ID Token. An ID Token must meet OIDC requirements for issuer, audience, timestamps, signature, `nonce` when applicable, and flow-mandated claims.

Likewise, an access token may be a JWT, yet clients must never use it as proof of OIDC login. Clients must verify an ID Token per OIDC Core.

### 1.2. OIDC Is Not a Single Endpoint

OIDC spans a family of related specifications:

| Specification | Scope |
|---|---|
| **OpenID Connect Core 1.0** | Authentication Requests, ID Tokens, UserInfo, claims, and authentication flows. |
| **OpenID Connect Discovery 1.0** | How an RP locates an OP's metadata. |
| **OpenID Connect Dynamic Client Registration 1.0** | Registering and reading client configurations dynamically. |
| **OpenID Connect RP-Initiated Logout 1.0** | RP asking the OP to log out an End-User. |
| **OpenID Connect Session Management 1.0** | Tracking/polling OIDC session state between RP and OP. |
| **OpenID Connect Front-Channel Logout 1.0** | OP notifying RPs of logout via the User Agent/browser. |
| **OpenID Connect Back-Channel Logout 1.0** | OP sending logout notifications directly to RPs over a back-channel. |
| **OpenID Connect Federation** | Establishing trust chains and metadata between OPs/RPs in a federation. |

Spring Authorization Server supports endpoints from several of these specs, yet you must never extrapolate from one spec to all of them. In particular, RP-Initiated Logout is independent of Session Management, Front-Channel Logout, and Back-Channel Logout.

### 1.3. Four Layers to Verify Before Claiming "OIDC Supported"

1. **Protocol surface:** endpoints, methods, request/response shapes, and metadata exist.
2. **Protocol semantics:** the server honors the actual meaning of parameters, claims, errors, and state transitions.
3. **Security policy:** authentication, consent, subject binding, token validation, sessions, and privacy satisfy policy.
4. **Interoperability:** real RPs can perform Discovery, sign in, validate ID Tokens, call UserInfo, log out, and handle errors.

Merely checking for HTTP 200 or JSON output from an endpoint does not prove a feature is compliant.

## 2. Built-In OIDC Matrix in Spring Authorization Server 1.5.8

Spring Authorization Server 1.5.8 provides the following OIDC endpoints once OIDC is enabled:

| Feature | Status in SAS 1.5.8 | Key Conditions / Limitations |
|---|---|---|
| OIDC Provider Configuration | Built-in, enabled with OIDC. | Metadata must reflect actual issuer, endpoints, and capabilities. |
| ID Token for OIDC Authorization Code Flow | Built-in. | Client must request **`openid`**; requires proper signing/JWK and client config. |
| OIDC UserInfo | Built-in, enabled with OIDC. | Bearer access token; requires **`JwtDecoder`** bean; default mapper pulls standard claims from ID Token per scope. |
| RP-Initiated Logout | Built-in, enabled with OIDC. | Uses **`SessionRegistry`**; verify session lifecycle and redirect validation. |
| OIDC Dynamic Client Registration / Client Read | Implemented, **disabled by default**. | Must enable endpoint; bearer token needs **`client.create`** or **`client.read`** scope; requires **`JwtDecoder`**. |
| JWK Set Endpoint | Built-in when a **`JWKSource<SecurityContext>`** bean exists. | Must manage key lifecycle, `kid`, rotation, and public JWKS. |
| OAuth2 Authorization Server Metadata | Built-in. | Distinct from OIDC Provider Configuration; never confuse the two metadata documents. |
| Custom OIDC claims in ID Token | Extension point available. | **`OAuth2TokenCustomizer<JwtEncodingContext>`** only adds/modifies claims; does not enforce authentication policies itself. |
| Custom UserInfo claims | Extension point available. | Replacement mapper must preserve scope filtering, `sub`, consent, and privacy. |
| Custom logout validation/behavior | Extension point available. | Must preserve redirect URI validation and session security. |

**Version scope of this lesson:** API and endpoint details in the Spring sections focus on **Spring Authorization Server 1.5.8**. If you use Spring Authorization Server 1.4.x, Spring Security 7.x Authorization Server, or another version, verify APIs and run integration tests against your exact dependencies.

### 2.1. Enabling OIDC in SecurityFilterChain

Skeleton configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer ->
            authorizationServer.oidc(Customizer.withDefaults())
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

This is the OIDC baseline configuration. A complete application also needs beans such as **`RegisteredClientRepository`**, **`OAuth2AuthorizationService`**, **`AuthorizationServerSettings`**, **`JWKSource<SecurityContext>`**, **`JwtDecoder`**, a login **`SecurityFilterChain`**, session management, and persistence.

When OIDC is enabled this way, SAS 1.5.8 configures Provider Configuration, Logout, and UserInfo endpoints. The Client Registration endpoint remains disabled by default.

### 2.2. Default Endpoints and Paths

| Endpoint | Typical Path in SAS 1.5.8 | Status |
|---|---|---|
| OIDC Provider Configuration | `/.well-known/openid-configuration` | Enabled when OIDC is enabled. |
| JWK Set | `/oauth2/jwks` | Configured when a `JWKSource` bean is present. |
| UserInfo | `/userinfo` | Enabled when OIDC is enabled; requires `JwtDecoder`. |
| RP-Initiated Logout | `/connect/logout` | Enabled when OIDC is enabled. |
| OIDC Client Registration / Read | `/connect/register` | Implemented but disabled by default; requires `JwtDecoder` and bearer scopes. |

Paths can be customized via **`AuthorizationServerSettings`**. Its builder exposes settings such as **`oidcUserInfoEndpoint(...)`**, **`oidcLogoutEndpoint(...)`**, and **`oidcClientRegistrationEndpoint(...)`**. If you change paths, Discovery metadata must reflect the updated paths.

### 2.3. JWKSource and JwtDecoder

The JWK Set endpoint is configured when the application registers a **`JWKSource<SecurityContext>`**. UserInfo and the OIDC Client Registration endpoint require a **`JwtDecoder`** bean in SAS 1.5.8.

Example:

~~~java
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configuration.OAuth2AuthorizationServerConfiguration;

@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
~~~

This is Spring Authorization Server's helper to build a decoder from a JWK source. In production, verify issuer, key source, algorithms, key rotation, and trust boundaries. Never use a JWK Set fetched from a request-supplied URL.

### 2.4. Distinguishing OIDC Provider Configuration From OAuth2 Authorization Server Metadata

These two metadata endpoints serve similar purposes yet are distinct protocol documents:

| Document | Standard | Contents |
|---|---|---|
| Authorization Server Metadata | RFC 8414 | OAuth2 endpoints and capabilities such as authorization endpoint, token endpoint, scopes, and grant types. |
| OpenID Provider Configuration | OpenID Connect Discovery 1.0 | OIDC issuer, authorization/token/JWKS/UserInfo endpoints, supported subject types, signing algorithms, claims, and OIDC capabilities. |

An OP may serve both. An OIDC RP should retrieve OIDC Provider Configuration via Discovery, then verify the issuer and endpoint metadata. Never substitute OAuth2 metadata for OIDC Discovery just because the JSON shares many field names.

## 3. Discovery: Built-In Endpoint, Metadata Still Needs Accuracy

### 3.1. Provider Configuration Endpoint

OIDC Discovery serves the Provider Configuration document, typically at:

~~~http
GET /.well-known/openid-configuration HTTP/1.1
Host: auth.example.com
Accept: application/json
~~~

Metadata includes fields such as:

- **issuer**
- **authorization_endpoint**
- **token_endpoint**
- **jwks_uri**
- **userinfo_endpoint**
- **end_session_endpoint** when a logout endpoint is enabled
- **response_types_supported**
- **subject_types_supported**
- **id_token_signing_alg_values_supported**
- **scopes_supported**
- **claims_supported**
- **grant_types_supported**
- Capability flags such as **claims_parameter_supported** or **request_parameter_supported** if supported by the OP.

Field names and requirements are defined by OIDC Discovery. Never add a flag just to make a client render a button or feature.

### 3.2. Customizing Metadata via Configurer

SAS provides **`providerConfigurationEndpoint(...)`** and **`providerConfigurationCustomizer(...)`** to customize the Provider Configuration response.

Example configuration placement:

~~~java
.oidc(oidc -> oidc
    .providerConfigurationEndpoint(providerConfiguration ->
        providerConfiguration.providerConfigurationCustomizer(
            providerConfigurationCustomizer
        )
    )
)
~~~

**`providerConfigurationCustomizer`** is an application-supplied component. Use it to add or adjust metadata only when the protocol implementation genuinely satisfies the advertised capability.

Never advertise:

- **`claims_parameter_supported=true`** if the server does not actually process `claims` requests.
- **`request_parameter_supported=true`** if Request Objects are not verified and processed.
- An ACR/AMR or signing algorithm that is not implemented.
- Front-channel/back-channel logout URIs when those protocols are unimplemented.
- Scopes or grant types that cannot actually be granted at the Token Endpoint.

Metadata is the OP's public contract. Whenever endpoints or capabilities change, re-check the Discovery document and run client interoperability tests.

### 3.3. Issuer Must Be Stable

Configuring the issuer:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .build();
}
~~~

The issuer must stay consistent across Discovery, ID Tokens, access tokens, and JWKS. Never let arbitrary incoming requests dictate the issuer when running multiple hostnames or an improperly trusted reverse proxy.

Clients compare **`iss`** in the ID Token against the discovered issuer. Changing the issuer alters the trust domain and requires an explicit migration.

## 4. ID Token: Framework Issues It, Application Owns Policy

### 4.1. An ID Token Is Not an Arbitrary JWT

An OIDC ID Token is a JWT with a strict contract. Core claims typically include:

| Claim | Meaning |
|---|---|
| **iss** | Issuer of the OP. |
| **sub** | End-User's Subject Identifier. |
| **aud** | Client ID or audience authorized to receive the ID Token. |
| **exp** | Expiration time of the ID Token. |
| **iat** | Issuance time of the ID Token. |
| **auth_time** | Time the End-User authenticated, when requested/applicable. |
| **nonce** | Value binding the Authentication Request to the ID Token if sent in the request. |
| **azp** | Authorized party when applicable, especially with multiple audiences. |
| **acr**, **amr** | Authentication Context Class Reference / Authentication Methods References when supported by the OP. |

SAS can issue ID Tokens in the OIDC Authorization Code Flow. The RP must still verify signature, issuer, audience, timestamps, `nonce`, and related OIDC rules. Never treat a decoded token as a verified token.

### 4.2. Adding Custom Claims with OAuth2TokenCustomizer

SAS provides **`OAuth2TokenCustomizer<JwtEncodingContext>`** to customize generated JWTs. When adding claims to ID Tokens, filter strictly by token type:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.oidc.endpoint.OidcParameterNames;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Bean
OAuth2TokenCustomizer<JwtEncodingContext> oidcTokenCustomizer() {
    return context -> {
        if (OidcParameterNames.ID_TOKEN.equals(
                context.getTokenType().getValue())) {

            // Pull only from a verified source permitted for disclosure.
            context.getClaims().claim("employee_tier", "standard");
        }
    };
}
~~~

This example only shows how to attach a claim; **`employee_tier`** must be backed by a real data source, consent/privacy policy, and RP contract. Never put sensitive data or unstable claims into ID Tokens just because the customizer allows it.

### 4.3. Customizer Does Not Enforce OIDC Semantics Automatically

| Requirement | Does Customizer Solve It Alone? | What Must Be Built |
|---|---|---|
| Add a department claim | Can attach the value. | Verify source, disclosure permission, and schema. |
| `max_age` | No. | Measure real authentication age; reauthenticate when exceeded. |
| `auth_time` | Can only write the claim. | Must persist the real authentication timestamp, never `iat`/`now`. |
| `acr` | Does not prove assurance itself. | Enforce authentication policy and emit only achieved ACRs. |
| `amr` | Does not know login methods automatically. | Record evidence of performed methods and emit accurately. |
| Pairwise `sub` | Does not compute sector-identifier mappings. | Build durable, irreversible, sector-stable subject mappings. |
| `nonce` | Not just an arbitrary custom claim. | Preserve request/authorization/token binding per standard flow. |
| Essential claims from `claims` param | No. | Parse, validate, satisfy, or reject per OIDC semantics. |

**Principle:** a claim is the output of policy enforcement. Never fabricate a claim to pretend a policy was enforced.

## 5. UserInfo: Built-In, Yet Claim Sources May Need Extension

### 5.1. Default UserInfo Mapper

SAS 1.5.8 includes **`OidcUserInfoEndpointFilter`** and **`OidcUserInfoAuthenticationProvider`**. The default mapper extracts standard claims from the ID Token based on the scopes authorized in the flow.

The UserInfo endpoint is an OAuth2 protected resource:
- The client sends a Bearer access token.
- The endpoint verifies the access token.
- SAS 1.5.8 requires a **`JwtDecoder`** bean.
- The response returns claims produced by the mapper.

### 5.2. When Do You Need a Custom Mapper?

You need a custom mapper when:
- Profiles must come fresh from a database or LDAP directory.
- Domain-specific claims are required.
- Claim visibility depends on tenant, privacy settings, or consent.
- You need mapping between internal user IDs and stable OIDC subjects.
- Policy prohibits returning profiles for disabled/deprovisioned users.
- Claims must be gated by additional scopes or policies.

**`OidcUserInfoEndpointConfigurer.userInfoMapper(...)`** receives **`OidcUserInfoAuthenticationContext`** and returns **`OidcUserInfo`**. When replacing the default mapper, the application itself must maintain scope filtering, mandatory **`sub`**, claim omission, and privacy rules.

### 5.3. Clients Must Verify Subject Binding

Per OIDC Core, UserInfo Responses must contain **`sub`**. The RP must compare this **`sub`** against the ID Token's **`sub`** for an exact match; on mismatch, discard the response.

Having the mapper return the right **`sub`** is not enough—the RP must check it. This prevents mixing access tokens and ID Tokens from two different sessions or users.

## 6. RP-Initiated Logout: Built-In Does Not Mean Ecosystem-Wide Logout

### 6.1. Built-In Endpoint

SAS 1.5.8 includes the OIDC RP-Initiated Logout endpoint, typically defaulted to:

~~~http
GET /connect/logout?id_token_hint=...&post_logout_redirect_uri=... HTTP/1.1
Host: auth.example.com
~~~

Clients can also use Spring Security OAuth2 Client's **`OidcClientInitiatedLogoutSuccessHandler`** to redirect users to the OP logout endpoint.

SAS's **`OidcLogoutAuthenticationProvider`** uses **`SessionRegistry`** to locate **`SessionInformation`** for the End-User and perform logout. When using **`SessionRegistryImpl`**, documentation recommends registering **`HttpSessionEventPublisher`** so session lifecycle events stay up to date.

### 6.2. What RP-Initiated Logout Does Not Solve Automatically

RP-Initiated Logout defines how an RP asks the OP to log out. It does not automatically provide:

- Logout notifications to every currently signed-in RP.
- Front-Channel Logout through the browser.
- Back-Channel Logout via direct HTTP requests from OP to RP.
- OIDC Session Management iframe/session state.
- Revocation of all issued access tokens and refresh tokens.
- Logout from upstream Identity Providers or federation systems.
- Clearing application sessions across all devices/replicas without a matching session strategy.

Session Management, Front-Channel Logout, and Back-Channel Logout are separate specifications. If "log out of every app" is required, implement RP notifications, session management, and token revocation accordingly.

### 6.3. Configuring SessionRegistry

Example using Spring Security's default session registry:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.session.SessionRegistryImpl;
import org.springframework.security.web.session.HttpSessionEventPublisher;

@Bean
SessionRegistry sessionRegistry() {
    return new SessionRegistryImpl();
}

@Bean
HttpSessionEventPublisher httpSessionEventPublisher() {
    return new HttpSessionEventPublisher();
}
~~~

This configures session tracking; it does not create front/back-channel logout. In clustered deployments, choose a distributed session registry/session strategy so logout lookups do not depend on a single node's local memory.

## 7. Dynamic Client Registration: Implemented, Disabled by Default

### 7.1. OIDC Client Registration Endpoint in SAS 1.5.8

SAS 1.5.8 provides **`OidcClientRegistrationEndpointConfigurer`**, supporting:
- Client Registration requests.
- Client Read requests.
- Custom converters/providers.
- Custom response/error handlers.

The endpoint is **disabled by default**. This is intentional: most deployments do not want arbitrary registrars creating new clients.

The endpoint is an OAuth2 protected resource:
- Registration requests require an access token with scope **`client.create`**.
- Client Read requests require an access token with scope **`client.read`**.
- A **`JwtDecoder`** bean is required for this endpoint.
- The default endpoint path is typically **`/connect/register`**.

### 7.2. Enabling the Endpoint

Example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer configurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(configurer.getEndpointsMatcher())
        .with(configurer, authorizationServer ->
            authorizationServer.oidc(oidc ->
                oidc.clientRegistrationEndpoint(Customizer.withDefaults())
            )
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

This snippet only turns on the endpoint. It is not a complete, safe public registration policy.

### 7.3. Registrar Client and Scopes

An existing registrar client can use Client Credentials to obtain an initial access token with scope **`client.create`**. If the registrar needs to read registrations after creating them, grant **`client.read`** as well per policy.

~~~java
import java.util.UUID;

import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;

RegisteredClient registrar = RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("client-registrar")
        .clientSecret(passwordEncoder.encode(registrarSecret))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("client.create")
        .scope("client.read")
        .build();
~~~

This illustrates registrar configuration; secrets must be securely managed and production **`RegisteredClientRepository`** must persist durably. Never grant **`client.create`** to ordinary apps just because they need login.

To obtain the initial access token, the registrar uses the **`client_credentials`** grant with scope **`client.create`**. Registration requests send this bearer token to the Client Registration endpoint. When reading a registration, use an access token granted **`client.read`**. These scopes are privileged registrar permissions—never include them in end-user client scopes.

Example request for an initial access token:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_REGISTRAR_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=client.create
~~~

The registrar must be registered for the **`client_credentials`** grant with only the necessary administrative scopes. Never use an end-user's access token as an initial access token for this endpoint.

### 7.4. Dynamic Registration Still Requires Dedicated Policy

Before opening this endpoint, decide:
- Who is allowed to create clients?
- Can clients freely pick grant types, redirect URIs, authentication methods, and scopes?
- Are redirect URI allowlists, domain verification, and reviews enforced?
- Who may read or update registrations?
- How are registration access tokens stored and rotated?
- Are quotas, rate limits, auditing, tenant boundaries, and abuse detection in place?
- How are public vs. confidential clients distinguished?
- Which registration metadata fields are writable?
- When a client is compromised, who disables, rotates, or revokes it?

Never enable Dynamic Client Registration in production merely to "have the OIDC endpoint." This endpoint alters the trust boundary and can let attackers register malicious OAuth clients if registrar policies are weak.

## 8. Optional OIDC Core Features Requiring Separate Evaluation

OIDC Core defines many OPTIONAL parameters. OPTIONAL means an OP may decline to support them; if advertised as supported, the OP must enforce their semantics accurately. Never confuse parsing a parameter into additional parameters with full protocol support.

| Feature | Standard Meaning | How to Evaluate in SAS 1.5.8 |
|---|---|---|
| `prompt` | Controls login, consent, account selection, or silent requests. | Verify Authorization Endpoint, login entry point, consent, and error redirect behavior for your version. |
| `max_age` / `auth_time` | Re-auth when authentication is too old; ID Token includes `auth_time`. | Requires a trusted authentication timestamp and reauthentication policy; a customizer only writes the claim. |
| `login_hint` | Identity hint. | May need login UI integration; strictly forbidden as a credential. |
| `id_token_hint` | Session/subject hint using a previously issued ID Token. | Must check trust, client/session binding, and real behavior. |
| `acr_values` | Requested authentication context. | Requires ACR mapping and real step-up authentication. |
| `claims` request parameter | Requests specific claims in ID Token/UserInfo. | Requires parser, essential-claim handling, consent, and claim policy; do not assume full support just because a mapper emits custom claims. |
| `request` / Request Object | JWT carrying authorization parameters. | Verify JAR support, signatures, encryption, client trust, and parameter precedence. |
| `request_uri` | Reference to a Request Object. | Distinguish OIDC Request URI from PAR URI; check SSRF and trust. |
| `ui_locales` | UI language preferences. | Login/consent UI must actually localize. |
| `display` | UI presentation hint. | Never weaken browser security to support popup/touch modes. |
| Pairwise subject | Distinct `sub` per sector/client grouping. | Requires durable subject mapping, sector identifiers, and privacy policies; never derive from simple custom claims. |

### 8.1. Prompt and max_age

OIDC Core specifies semantics for **`prompt=none`**, **`prompt=login`**, **`prompt=consent`**, and **`prompt=select_account`**. For example, **`prompt=none`** must show no UI; if login/consent/selection is needed, return an OIDC error.

**`max_age`** requires the OP to reauthenticate if the real authentication is too old; when used, the ID Token must include **`auth_time`**. Never use ID Token issuance time as `auth_time` if the user did not reauthenticate.

Spring Authorization Server offers extension points at the Authorization Endpoint, yet that does not mean all interaction semantics work out of the box. Inspect the login filter chain, SSO cookies, consent UI, account selection, session state, and error callbacks.

### 8.2. Claims Parameter and UserInfo Mapper

The **`claims`** request parameter can request claims in the ID Token or UserInfo with **`essential`**, **`value`**, and **`values`** attributes. This request directly impacts privacy and consent.

A custom **`userInfoMapper`** can return claims, yet it is not by itself a full implementation of the **`claims`** parameter:
- Parse JSON and validate structure.
- Check whether the client is permitted to request each claim.
- Check whether essential claims can be satisfied.
- Apply consent and privacy rules.
- Return errors or responses per OIDC semantics.
- Set **`claims_parameter_supported`** metadata accurately to match capabilities.

### 8.3. Pairwise Subject

OIDC supports public and pairwise subject identifiers. Pairwise subjects restrict RPs from correlating the same user's activity across sectors.

To implement pairwise subjects, the OP needs stable subject mappings keyed by sector identifier/client grouping, `sector_identifier_uri` handling, and lifecycle management when redirects or client groupings change. Never hash an email on every ID Token issuance, because emails change and unsalted/unkeyed hashes can be reversed.

If an SAS application uses a custom subject mapper, ensure ID Token, UserInfo, authorization storage, logout sessions, and profile APIs share the exact same subject mapping.

## 9. Separate Specifications Never to Assume Built-In

### 9.1. Session Management and Front/Back-Channel Logout

RP-Initiated Logout has an endpoint in SAS, whereas Session Management, Front-Channel Logout, and Back-Channel Logout are separate specifications.

| Mechanism | Channel | Additional Responsibility |
|---|---|---|
| RP-Initiated Logout | RP → OP | OP terminates its corresponding session. |
| Session Management | Browser/iframe and OP | Session state / check-session protocol. |
| Front-Channel Logout | OP → RP via User Agent | RP handles logout requests in the browser context. |
| Back-Channel Logout | OP → RP directly | RP validates Logout Tokens and terminates sessions server-side. |

If you need to log out all RPs, implement RP notifications and session correlation per those specifications. Never assume **`OidcLogoutEndpointConfigurer`** provides them automatically.

### 9.2. Federation

OIDC Federation defines trust chains, entity statements, metadata policies, and trust anchors. This is a different trust layer from simply using an upstream OIDC provider for login.

Spring Security OAuth2 Client can integrate an upstream OP; that does not turn your Authorization Server into an OIDC Federation entity. Standards-compliant federation requires dedicated federation components and trust-chain/policy verification.

### 9.3. CIBA, FAPI, and Specialized Profiles

- **CIBA (Client Initiated Backchannel Authentication):** a dedicated back-channel authentication flow; do not confuse it with the Device Authorization Grant.
- **FAPI:** security profiles adding strict requirements for PAR/JAR, sender-constrained tokens, signing, encryption, request validation, and security controls.
- **OpenID Connect Native SSO / industry profiles:** carry dedicated requirements for clients, devices, and sessions.
- **Pairwise subject:** requires dedicated mapping and policies as described earlier.

Supporting OAuth2 Device Authorization Grant or PAR does not automatically confer CIBA or FAPI conformance. Each profile requires evaluation and testing against its specific specification.

## 10. Spring Authorization Server Extension Points

SAS structures endpoint configurers in stages:
1. **Pre-processing:** `AuthenticationConverter` parses the HTTP request.
2. **Main processing:** `AuthenticationProvider` validates and executes the protocol.
3. **Post-processing:** success/error handlers produce the response.
4. **Policy/customization:** validators, mappers, token customizers, or application services.

| Endpoint / Component | Typical Extension Points | Used For |
|---|---|---|
| Authorization Endpoint | `authorizationRequestConverter`, `authenticationProviders`, `setAuthenticationValidator`, `consentPage`, error handler | Request validation, interaction policy, consent. |
| Provider Configuration | `providerConfigurationCustomizer` | Discovery metadata. |
| UserInfo | `userInfoMapper`, provider, response/error handler | Dynamic claims, scope/privacy filtering. |
| RP-Initiated Logout | Logout validator, provider, response/error handler | Redirect validation and session/logout policy. |
| Client Registration | Registration converter/provider/response handler | Registration policy and client metadata. |
| ID Token | `OAuth2TokenCustomizer<JwtEncodingContext>` | Permitted issued claims. |
| Session | `SessionRegistry`, session strategy | Tracking and terminating OP sessions. |

### 10.1. Never Accidentally Replace Default Validation

SAS's default Authorization Code Request validator checks **`redirect_uri`** and **`scope`**. If the application calls **`setAuthenticationValidator(...)`**, retain all necessary default validators or compose them with your custom validator.

Structural example:

~~~java
Consumer<OAuth2AuthorizationCodeRequestAuthenticationContext> validator =
        customBusinessValidator
            .andThen(OAuth2AuthorizationCodeRequestAuthenticationValidator
                .DEFAULT_SCOPE_VALIDATOR);
~~~

This snippet shows composing a custom validator with the default scope validator. Verify exact ordering and which default validators to retain against your version/API. Never drop redirect URI, PKCE, or client validation to simplify an extension.

### 10.2. Custom Providers Must Delegate or Preserve Standard Behavior

When replacing a default provider, understand the full contract it handles. A custom provider cannot merely accept requests; it must preserve checks for:
- `RegisteredClient` and client authentication.
- Redirect URI, response type, scope, and grant.
- Consent, authorization state, and PKCE.
- Token generation and authorization persistence.
- Error mapping and protocol responses.

If you only need to add a policy, prefer a decorator/wrapper or validator hook to keep the standard provider intact rather than rewriting the entire flow.

### 10.3. Customizability Does Not Mean Built-In Support for Every Extension

Extension points are tools for applications to implement semantics themselves. They do not automatically supply:
- Request Object JWT verification.
- Pairwise subject calculation.
- ACR/MFA assurance engines.
- Dynamic claim authorization.
- Front/Back-Channel Logout.
- Federation trust chains.
- Conformance certification.

Each extension needs dedicated design, implementation, security review, and tests.

## 11. Building a Deployment Capability Matrix

A capability matrix must be tied to the **exact running artifact, version, and configuration**, not just architecture slides.

Example:

| Capability | SAS 1.5.8 Baseline | Current Deployment | Evidence |
|---|---|---|---|
| OIDC Discovery | Built-in when OIDC enabled | Supported | Discovery response + issuer tests |
| Authorization Code + ID Token | Built-in | Supported | RP integration test |
| UserInfo | Built-in; requires `JwtDecoder` | Supported | Bearer + scope + `sub` test |
| RP-Initiated Logout | Built-in; uses `SessionRegistry` | Supported with limitations | Browser session/logout test |
| Dynamic Client Registration | Implemented, disabled by default | Disabled | Configuration review |
| `prompt=none` | Verify behavior by version/filter chain | Not yet verified | Browser E2E |
| `max_age` / `auth_time` | Requires custom policy/state | Custom implementation | Authentication timestamp test |
| ACR/MFA | Requires assurance policy | Not implemented | Step-up conformance test |
| Pairwise `sub` | Requires subject mapping | Not implemented | Multi-client subject tests |
| `claims` request parameter | Verify support/extension | Not verified | Claim request tests |
| Front-Channel Logout | Separate specification | Not implemented | RP logout tests |
| Back-Channel Logout | Separate specification | Not implemented | Logout Token verification tests |
| OIDC Federation | Separate component | Not implemented | Trust-chain tests |

Recommended statuses:

- **SUPPORTED:** implemented and backed by integration/conformance evidence.
- **CUSTOM_IMPLEMENTED:** custom-built by the application and tested.
- **DISABLED:** framework includes it, yet the endpoint/feature is turned off.
- **NOT_SUPPORTED:** deployment does not provide the feature.
- **NOT_VERIFIED:** lacks evidence; must not be advertised as supported.

Never label a system **OIDC-compliant** solely because a few endpoints respond. Specify the profile, specification version, test suite, and advertised optional features.

## 12. Interoperability and Conformance Testing

### 12.1. Discovery Tests

- [ ] Discovery URL is reachable via the public issuer.
- [ ] `issuer` matches the `iss` claim in ID Tokens exactly.
- [ ] `authorization_endpoint`, `token_endpoint`, `jwks_uri`, and `userinfo_endpoint` are accurate.
- [ ] Metadata never advertises disabled endpoints.
- [ ] Supported signing algorithms match actual keys and JWT encoder capabilities.
- [ ] `claims_supported`, `subject_types_supported`, and `grant_types_supported` never overstate capabilities.
- [ ] Reverse proxies/ingress never corrupt scheme, host, or path.

### 12.2. ID Token Tests

- [ ] `openid` scope is requested and handled properly.
- [ ] ID Token signature verifies against the issuer's JWKS.
- [ ] `iss`, `sub`, `aud`, `exp`, and `iat` are accurate.
- [ ] `nonce` is verified when the request sent one.
- [ ] `auth_time` is present when `max_age` is requested and reflects real authentication.
- [ ] `acr`/`amr` reflect only actually performed methods/assurance.
- [ ] RP rejects tokens with wrong issuer, audience, nonce, or signature.
- [ ] Custom claims respect consent/privacy and leak no internal data.

### 12.3. UserInfo Tests

- [ ] Requires a valid Bearer access token.
- [ ] Expired/revoked tokens are rejected.
- [ ] Scope mapping is accurate.
- [ ] `sub` is always present and matches the ID Token.
- [ ] Optional claims are omitted when absent or disallowed.
- [ ] Custom mapper never bypasses authorization state.

### 12.4. Logout Tests

- [ ] RP can send logout requests to the OP.
- [ ] `post_logout_redirect_uri` is validated against client registration.
- [ ] OP session is actually terminated.
- [ ] `SessionRegistry` updates on session destruction/timeout.
- [ ] Tested across multiple tabs, devices, and nodes.
- [ ] If front/back-channel logout is advertised, separate tests cover each protocol.
- [ ] Access/refresh token survival and revocation are tested separately; session logout does not prove tokens were revoked.

### 12.5. Dynamic Client Registration Tests

If DCR is enabled:

- [ ] Registrar holds a bearer token with scope `client.create`.
- [ ] Client Read requires scope `client.read`.
- [ ] Registration access tokens are never public or shared uncontrolled.
- [ ] Redirect URIs, grant types, scopes, and client auth methods are checked by policy.
- [ ] Registration metadata cannot create open redirects or client impersonation.
- [ ] `RegisteredClient` persistence survives restarts and works across instances.
- [ ] Auditing, quotas, rate limits, and disable/rotation workflows exist.
- [ ] Endpoint prevents registrars from reading or modifying registrations outside their scope.

## 13. Security When Publishing OIDC Capabilities

### 13.1. Metadata Must Be Honest

Inaccurate metadata breaks interoperability and can widen trust boundaries. Examples:
- Advertising `claims_parameter_supported=true` while ignoring essential claims.
- Advertising `end_session_endpoint` when the logout endpoint fails to terminate sessions.
- Advertising signing algorithms absent from the key source.
- Advertising `subject_types_supported` containing `pairwise` while every client receives the same public subject.
- Enabling Dynamic Client Registration without registrar governance.

### 13.2. Never Confuse Authentication With Authorization

OIDC authenticates users; OAuth2 authorizes resource access. The ID Token tells the client who authenticated; the access token authorizes API calls per audience, scopes, and policy.

Never use ID Tokens to call APIs. Never use access tokens as login proof in place of ID Tokens. Never put API scopes into ID Tokens and assume the Resource Server checked permissions.

### 13.3. Claims and Privacy

- Issue only necessary claims.
- Scopes are not an unlimited license to dump all PII.
- UserInfo responses must filter by scope, consent, and policy.
- Never log raw ID Tokens, access tokens, authorization codes, nonces, or PII-bearing request objects.
- `sub` must remain stable and never be reassigned to someone else.
- Pairwise subjects require dedicated mappings and must never be derived from email.

### 13.4. Session and Token Lifecycle

- Logging out of an OP session does not automatically revoke all access tokens.
- Revoking a token does not automatically log out all RP sessions.
- Front/back-channel logout requires verifying logout messages/tokens and preventing replay.
- Refresh token rotation, revocation, and session invalidation require dedicated policies.
- Multiple Authorization Server instances require shared session/authorization state and consistent key configuration.

## 14. Hands-On Exercise

**Scenario:** **auth.example.com** runs Spring Authorization Server 1.5.8 and aims to provide OIDC for **employee-portal**, **mobile-app**, and **partner-console**.

### Requirements

1. Enable OIDC and verify the Provider Configuration endpoint.
2. Configure the issuer and JWK source; issue ID Tokens for the Authorization Code Flow.
3. Verify the `JwtDecoder` bean for UserInfo.
4. Run UserInfo with the default mapper, then add a custom mapper for dynamic profiles and scope filtering.
5. Configure RP-Initiated Logout and `SessionRegistry`; explicitly decide whether session logout revokes access tokens.
6. Keep Dynamic Client Registration disabled initially; if needed, enable the endpoint and grant `client.create`/`client.read` strictly to a registrar service.
7. Draft a capability matrix for `prompt`, `max_age`, `auth_time`, `acr_values`, `claims`, `request`, and pairwise `sub`.
8. Implement `max_age` and `auth_time` backed by a trusted authentication timestamp.
9. Define an ACR/AMR policy for MFA/step-up; never copy `acr_values` directly into the ID Token.
10. If pairwise subjects are needed, design sector mappings and migrations.
11. If ecosystem-wide logout is required, scope Session Management, Front-Channel, and Back-Channel Logout as dedicated projects.
12. Run browser E2E and OIDC conformance tests, clearly documenting unsupported/disabled features.

**Completion criteria:** metadata documentation matches implementation; ID Tokens and UserInfo are verified by RPs; logout semantics are accurately documented; DCR enforces registrar authorization; and every optional extension has a recorded status and test evidence.

## 15. Pre-Handoff Checklist

- [ ] Locked the baseline Spring Authorization Server / Spring Security version.
- [ ] Clearly separated OAuth2 Authorization Server, OP, RP, and Resource Server roles.
- [ ] OIDC is explicitly enabled and the Discovery endpoint is tested.
- [ ] `issuer` is stable and matches metadata and ID Tokens.
- [ ] `JWKSource` and `JwtDecoder` are properly configured.
- [ ] ID Token claims, signatures, and `nonce` are validated per OIDC Core.
- [ ] UserInfo requires Bearer access tokens and filters claims by scope.
- [ ] RP verifies UserInfo `sub` matches ID Token `sub`.
- [ ] RP-Initiated Logout is tested with `SessionRegistry`.
- [ ] Front/back-channel logout or session management is not claimed unless implemented.
- [ ] Dynamic Client Registration remains disabled unless registrar governance is in place.
- [ ] If DCR is enabled, `client.create`/`client.read` follow least privilege.
- [ ] `max_age`/`auth_time` rely on a trustworthy authentication timestamp source.
- [ ] ACR/AMR reflect genuine assurance and methods.
- [ ] `claims`, Request Objects, `login_hint`, `prompt`, and `acr_values` are tested against your version.
- [ ] Pairwise subjects have durable mappings if advertised in metadata.
- [ ] Discovery metadata never advertises unimplemented features.
- [ ] Default validators/providers are preserved when extending endpoints.
- [ ] Capability matrix includes statuses and evidence.
- [ ] Appropriate integration, browser E2E, and conformance tests exist.
- [ ] Tokens, nonces, codes, PII, and sensitive request objects are excluded from logs.
- [ ] Owners and runbooks exist for key rotation, session logout, client registration, and deprovisioning.

## Summary

Spring Authorization Server 1.5.8 provides a practical OIDC foundation: Provider Configuration, ID Tokens for the OIDC Authorization Code Flow, UserInfo, and RP-Initiated Logout. Dynamic Client Registration is also implemented yet disabled by default, requires bearer tokens with `client.create`/`client.read` scopes, and must be guarded by registrar policies. UserInfo and the Client Registration endpoint require a `JwtDecoder`; the JWK Set endpoint requires a `JWKSource`.

APIs for customizers, mappers, providers, validators, and session registries let you extend the framework, yet they do not implement all OIDC semantics automatically. `max_age`, `auth_time`, ACR/MFA, `claims` requests, Request Objects, pairwise subjects, session management, front/back-channel logout, and federation each require dedicated evaluation. Advertise a capability as supported only when metadata, runtime behavior, and integration/conformance tests all prove it.

## References

1. [Spring Authorization Server 1.5.8 — Overview](https://docs.spring.io/spring-authorization-server/reference/overview.html): protocol endpoints and list of implemented specifications.
2. [Spring Authorization Server 1.5.8 — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): enabling OIDC, Provider Configuration, Logout, UserInfo, and Client Registration endpoints.
3. [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): configurers, defaults, UserInfo, Logout, and Dynamic Client Registration.
4. [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, `Authorization`, `SessionRegistry`, and core components.
5. [Spring Authorization Server — How-to: Customize the OpenID Connect 1.0 UserInfo response](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-userinfo.html): default mapper and custom UserInfo claims.
6. [Spring Authorization Server — How-to: Register a client dynamically](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-dynamic-client-registration.html): enabling DCR, registrar clients, initial access tokens, and scopes.
7. [OpenID Connect Core 1.0 incorporating errata set 2](https://openid.net/specs/openid-connect-core-1_0.html): Authentication Request, ID Token, UserInfo, claims, and protocol semantics.
8. [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): Provider Configuration metadata and capability advertisement.
9. [OpenID Connect Dynamic Client Registration 1.0](https://openid.net/specs/openid-connect-registration-1_0.html): Client Registration and Client Read protocols.
10. [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html): RP-initiated OP logout.
11. [OpenID Connect Session Management 1.0](https://openid.net/specs/openid-connect-session-1_0-final.html): session state and RP/OP session management.
12. [OpenID Connect Front-Channel Logout 1.0](https://openid.net/specs/openid-connect-frontchannel-1_0.html): logout notifications via User Agent.
13. [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0-final.html): direct logout notifications from OP to RP.
14. [OpenID Connect Conformance Testing](https://openid.net/certification/): test profiles and conformance evidence for OpenID implementations.
