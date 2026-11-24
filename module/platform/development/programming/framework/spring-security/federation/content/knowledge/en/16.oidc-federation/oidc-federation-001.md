# OIDC Login in a Federated Identity Architecture

**OpenID Connect (OIDC)** is an identity authentication layer built on top of **OAuth 2.0**. In a *federation* architecture, an application does not ask users directly for their passwords; instead, it redirects them to a trusted **OpenID Provider (OP)**. The OP authenticates the user, obtains consent to share information, and issues an **ID Token** so that the **Relying Party (RP)** application knows the subject has been authenticated. When an **identity broker** is present, the broker can act as an **RP toward upstream IdPs** and as an **OP toward downstream applications**, bridging multiple identity sources (OIDC, SAML 2.0, LDAP/AD via adapters) into a single unified login interface.

This topic needs to be understood at **two levels**: (1) how a Java/Spring Security application performs **OIDC login** correctly according to the protocol; and (2) how an organization positions that application within a **federation and identity brokering** system so that trust boundaries, identities, sessions, and permissions are never conflated.

**Key takeaway:** OIDC verifies *the identity asserted by the OP*; the application still has to decide **whether to admit the user into the application** and **what they are allowed to do**. An **ID Token** is not an access token for arbitrary APIs; a **token issued by a broker** is not a copy of the upstream IdP's token or SAML assertion.

## 1. When Should You Use OIDC in a Federation Architecture?

Consider an organization that has:

- An application `portal.example.org` written with **Spring Boot/Spring Security**.
- An employee identity provider using SAML 2.0; a customer identity provider supporting OIDC; and partner organizations with their own IdPs.
- A broker `https://login.example.org/realms/enterprise` sitting in the middle, selecting an IdP by tenant/home realm, verifying the upstream result, creating a local/broker identity, applying policies, and issuing an **OIDC ID Token for the portal**.
- Internal APIs using access tokens with their own audiences, rather than using the ID Token as a bearer token.

A conceptual architecture:

~~~text
                 +----------------------+
                 |       Browser        |
                 +----------+-----------+
                            |
                       open /reports
                            v
                 +----------------------+
                 |   Portal (Spring)    |
                 |   OIDC RP / Client   |
                 +----------+-----------+
                            |
                  OIDC Authorization Code
                            |
                            v
                 +----------------------+
                 |    Identity Broker   |
                 |    OP for Portal     |
                 |    RP/SP for IdP     |
                 +---+----------+-------+
                     |          |
        upstream SAML|          |upstream OIDC
                     v          v
              +-----------+ +-----------+
              | Employee  | | Partner   |
              | IdP       | | IdP       |
              +-----------+ +-----------+

Portal only verifies Broker tokens against the broker issuer / JWKS.
Broker independently verifies upstream IdP messages and conditions.
~~~

**Not every OIDC deployment needs a broker**: if an application integrates with only a single OP, it can register an OIDC client directly with that OP. A broker pays off when you have multiple IdPs, centralized policies, organization-based discovery, centralized MFA/policies, account synchronization, or when you want downstream applications to integrate with only a single issuer.

### 1.1. Roles to Distinguish

| Term | Protocol Role | In This Example |
| --- | --- | --- |
| **End-User** | Human being authenticated. | Portal user. |
| **Relying Party (RP)** | OIDC application that receives and verifies the ID Token. | Spring Boot portal. |
| **OAuth 2.0 Client** | Client requesting an authorization code/token. | Also the portal on the downstream leg. |
| **OpenID Provider (OP)** | Authentication server issuing ID Tokens. | Identity broker toward the portal. |
| **Authorization Server (AS)** | Issues authorization codes and tokens per OAuth. | Broker on the downstream leg. |
| **Resource Server** | API verifying access tokens for resources. | Separate Reporting API. |
| **Identity Broker** | Intermediary authenticating with upstream IdPs and issuing downstream identities. | Enterprise broker. |
| **Upstream IdP** | Originating system authenticating the user to the broker. | SAML IdP or another OP. |
| **OIDC Client Registration** | Configuration of `client_id`, redirect URI, scope, provider/issuer, credentials. | `portal-web` at the broker. |

One component can play **two roles** across two different trust relationships. The broker is a **client/RP or SAML SP** when talking upstream, yet an **OP/AS** when talking to the portal. Do not substitute the portal's token verification rules for the broker's SAML assertion processing rules.

## 2. What Does OIDC Add on Top of OAuth 2.0?

OAuth 2.0 is primarily **delegated authorization for resource access**: a client receives an access token with scopes/audience/policies. OIDC adds **user authentication**, standardizing the **ID Token**, claims, and related discovery/userinfo/logout mechanisms.

| Message/Token | Purpose | Trusted Recipient | Notes |
| --- | --- | --- | --- |
| **Authorization Code** | One-time value the client exchanges for tokens at the token endpoint. | Client + Authorization Server within the right transaction. | Short-lived, bound to redirect URI/client and PKCE. |
| **ID Token** (OIDC) | Asserts that a subject was authenticated by the OP for this **RP/client**. | RP whose `client_id` is in `aud`. | Must verify issuer, audience, signature, time, and nonce when used. |
| **Access Token** (OAuth 2.0) | Authorizes calls to the corresponding resource server. | Resource server/API per audience/scope. | Does not by itself prove login to an RP. |
| **Refresh Token** (if issued) | Used to obtain new access tokens per policy. | Client and AS token endpoint. | Requires strict protection/rotation; do not expose casually to the browser. |
| **`state`** | Correlates the OAuth authorization response with the request, preventing redirect CSRF. | Client checks against stored state. | Not a JWT; do not use it as email/role. |
| **`nonce`** | Binds the ID Token to the authentication request, mitigating replay/substitution. | RP checks `nonce` in the token when sent. | Distinct from `state`; does not replace PKCE. |
| **PKCE `code_verifier`** | One-time secret for token exchange; AS verifies it matches `code_challenge`. | Client stores until code exchange; AS verifies. | Prevents code interception/injection within protocol scope. |

**An ID Token is not a substitute for API authorization.** A resource server should not accept the portal's ID Token as an access token merely because it is also a signed JWT. The `aud` of an ID Token is the **OIDC client**, whereas an access token targets an **API audience** and is governed by different policies. An OAuth access token may be a JWT or an opaque string: an application cannot assume every access token can be decoded by splitting on dots.

## 3. Authorization Code Flow with PKCE: The Standard Path for Web Login

Modernization rule: prefer **Authorization Code Flow** combined with **PKCE (S256)**, HTTPS transport, and exact registered redirect URIs. Avoid new designs based on the **Implicit Flow** that pass tokens directly via the browser URL fragment. For server-side Spring Boot, the client can be a confidential client using client secret/private key authentication; **PKCE remains an additional layer of protection** and does not imply dropping client authentication if the OP requires it.

~~~text
Browser                    RP / Spring Boot               OP / Broker
  |                               |                              |
  | GET /private                  |                              |
  |------------------------------>|                              |
  |                               | generate state, nonce,       |
  |                               | verifier; compute PKCE S256  |
  |<------------------------------|                              |
  | 302 /authorize?...state=...&code_challenge=...                |
  |------------------------------------------------------------->|
  |                               |                      authenticate
  |                               |                      upstream IdP
  |<-------------------------------------------------------------|
  | 302 https://portal.example.org/login/oauth2/code/broker
  |                  ?code=...&state=...
  |------------------------------>|                              |
  |                               | match state, find orig req   |
  |                               |                              |
  |                               | POST /token (code + verifier)|
  |                               |----------------------------->|
  |                               |<-----------------------------|
  |                               | id_token, access_token      |
  |                               |                              |
  |                               | Verify ID Token              |
  |                               | iss/aud/signature/time/nonce |
  |                               | bind issuer+sub => account   |
  |                               | SecurityContext / session    |
  |<------------------------------|                              |
  | 302 /private                 |                               |
~~~

Detailed flow:

1. The user requests a protected resource at the RP.
2. Spring Security triggers `/oauth2/authorization/broker` (by registrationId), creates an `OAuth2AuthorizationRequest` and an unpredictable `state`; when using PKCE it generates `code_verifier` and `code_challenge=S256(verifier)`; and generates `nonce` if used.
3. The RP redirects the browser to the **OP's authorization endpoint**, including `response_type=code`, `client_id`, `redirect_uri`, `scope` containing `openid`, state, PKCE challenge, and appropriate OIDC parameters.
4. The broker selects the upstream IdP, authenticates/receives the result, and decides to issue a code to the RP. **The portal never directly sees the SAMLResponse or upstream credentials** if the broker is doing its job properly.
5. The browser returns to the **RP's redirect URI** with `code` and `state`; the code is not an identity and must not be used directly as a session.
6. Spring verifies the transaction via the authorization request repository, `state`, and registration; the RP backend sends the code together with `code_verifier` to the token endpoint.
7. The OP validates the client/challenge, code, and redirect URI and issues an ID Token and access token (plus a refresh token if policy grants one).
8. The RP verifies the ID Token, extracts `iss`+`sub`, looks up the local account and internal policy, builds the `Authentication`/authorities, and stores the `SecurityContext`/session.
9. Subsequent requests can use the RP session cookie; the access token is stored server-side if the RP needs to call APIs on the user's behalf.

**OIDC login is not simply redirecting to an OP page and receiving JSON containing an email.** Server-side/secure-client token exchange and verification are what substantiate the identity.

### 3.1. Example HTTP Messages Along the Flow

Login request at the portal:

~~~http
GET /oauth2/authorization/broker HTTP/1.1
Host: portal.example.org
~~~

An illustrative authorization request (line wraps are for readability only):

~~~text
GET https://login.example.org/realms/enterprise/protocol/openid-connect/auth
  ?response_type=code
  &client_id=portal-web
  &redirect_uri=https%3A%2F%2Fportal.example.org%2Flogin%2Foauth2%2Fcode%2Fbroker
  &scope=openid%20profile%20email
  &state=<cryptographically-random-state>
  &nonce=<cryptographically-random-nonce>
  &code_challenge=<base64url-sha256-verifier>
  &code_challenge_method=S256
~~~

The angle-bracketed strings are **illustrative placeholders**, not usable live values. The specific authorization endpoint must come from OP metadata; the path above only assumes an OP with a similar path structure.

Browser callback:

~~~http
GET /login/oauth2/code/broker?code=<one-time-code>&state=<returned-state> HTTP/1.1
Host: portal.example.org
Cookie: JSESSIONID=<browser-session-cookie>
~~~

The RP matches state/binding **before** using the authorization code. The token request is **server-to-server**; never embed the client secret in HTML pages or browser JavaScript. If `error=access_denied`/login_failed occurs, the application must handle the failure path and not assume an ID Token is present.

### 3.2. What Passes Through the Browser vs. What the Backend Stores

The browser can observe the **authorization request**, code, and state during navigation; therefore you need TLS, exact redirect URIs, referrer/token leak protection, single-use codes, PKCE, and session binding. The backend retains the **original authorization request**, nonce, code verifier, and sensitive client credentials/tokens according to server-side policy; never let `code_verifier` or client secrets leak into query URLs or public logs.

If two tabs log in simultaneously, each authorization transaction needs an **independent state/nonce/verifier**, properly correlated with the browser session. Never store a single shared "last login state" that causes tab A's callback to use tab B's verifier. Session fixation protection rotating the cookie after login must also be tested.

## 4. Discovery: How Does the RP Learn the OP's Endpoints and Keys?

OpenID Connect Discovery uses the **issuer URL** to fetch metadata. Example hypothetical issuer:

~~~text
https://login.example.org/realms/enterprise
~~~

A discovery document has a structure similar to:

~~~json
{
  "issuer": "https://login.example.org/realms/enterprise",
  "authorization_endpoint": "https://login.example.org/realms/enterprise/authorize",
  "token_endpoint": "https://login.example.org/realms/enterprise/token",
  "jwks_uri": "https://login.example.org/realms/enterprise/jwks",
  "userinfo_endpoint": "https://login.example.org/realms/enterprise/userinfo",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public", "pairwise"],
  "id_token_signing_alg_values_supported": ["RS256"]
}
~~~

This is **illustrative metadata JSON**, not a live OP endpoint. Depending on the product, well-known discovery paths follow different rules when the issuer contains a path; let Spring Security's Discovery library handle this per spec instead of concatenating strings arbitrarily to guess endpoints.

The RP must verify that **`metadata.issuer` matches the configured issuer and `iss` in the ID Token exactly**. `jwks_uri` provides public verification keys; when the OP rotates signing keys, the RP should cache/refresh the JWKS appropriately but **never fetch keys from an arbitrary URL supplied by an attacker's token or header**. Never set `issuer-uri` from a query parameter sent by the browser: that can cause SSRF or IdP mix-up.

Discovery helps configure endpoints, but **does not automatically validate any token** if issuer, audience, signature, or transaction state fails verification.

## 5. ID Token: Contents and Verification

An ID Token is usually a **signed JWT** issued by the OP for the RP. An *illustrative* payload:

~~~json
{
  "iss": "https://login.example.org/realms/enterprise",
  "sub": "pairwise-6f13a8",
  "aud": "portal-web",
  "exp": 1794024000,
  "iat": 1794023700,
  "auth_time": 1794023600,
  "nonce": "random-value-bound-to-this-login",
  "acr": "urn:example:assurance:level2",
  "amr": ["pwd", "mfa"],
  "email": "member@example.org",
  "email_verified": true
}
~~~

This JSON data is **not a signed token**, and the timestamps are merely example numbers; you cannot paste it into an API to log in. The RP **must not** trust claims from a self-decoded JWT payload without passing the full verifier.

### 5.1. Key Claims

| Claim | Meaning | Verification/Application |
| --- | --- | --- |
| **`iss`** | OP that issued the token. | **Exact match** with configured/discovered issuer. |
| **`sub`** | Subject identifier scoped to the issuer. | Combine **`iss` + `sub`** as the identity binding key; do not use email as the sole key. |
| **`aud`** | Audience of the ID Token. | Must contain the **RP's `client_id`**; handle multiple audiences and `azp` per spec. |
| **`exp`** | Token expiration. | Reject expired tokens; allow only a small controlled clock skew. |
| **`iat`** | Issued-at timestamp. | Sanity-check and bound maximum age per application policy. |
| **`nonce`** | Associates the ID Token with the authentication request. | If nonce was sent, it must be present and match the **exact stored nonce**; use separate state/nonce per transaction. |
| **`auth_time`** | Time when the user authenticated at the OP. | Important for `max_age`/reauth/step-up. |
| **`acr`** | Authentication context class / assurance level. | Use only when OP and RP have an assurance contract; do not infer from arbitrary strings. |
| **`amr`** | Authentication methods used. | Only partial assurance data; does not automatically mean "MFA is sufficient for every transaction". |
| **`email`, `email_verified`** | Contact information. | Does not replace `iss+sub`, and "verified" depends on OP trust policy. |
| **`azp`** | Authorized party in relevant cases. | Check client per OIDC rules when present or required. |
| **`sid`** (when present) | OP session identifier for certain logout protocols. | Distinct from `sub`, RP cookies, and access tokens; not always present. |

**Technical verification must include** signature/allowed algorithms/JWKS of the **exact OP**, issuer, audience, timestamps, nonce, and any other conditions/claims required by the application. Avoid JWT algorithm confusion, inappropriate `alg=none`, treating `kid` as a filesystem path/URL, and skipping `azp` checks when multiple audiences exist.

In the Authorization Code Flow, **OIDC Core makes nonce optional in some cases**, yet **if a nonce was sent, it must be verified**. Do not claim nonce is mandatory for every response type; equally, do not remove CSRF state and PKCE just because nonce is optional. Some servers/frameworks choose to send nonce consistently to strengthen binding.

### 5.2. UserInfo Does Not Replace the ID Token

`userinfo_endpoint` is an OP resource endpoint. The RP can call it using the **access token** to retrieve profile attributes that the user/OP agreed to share. When using UserInfo, **`sub` in UserInfo must match `sub` in the ID Token**; otherwise reject the UserInfo result to prevent token substitution. Do not use UserInfo email/name as identification evidence independent of the ID Token.

Profile claims may change over time; if `email` changes, local account binding by `iss+sub` remains unambiguous. An application that does not need UserInfo can rely on the ID Token for authentication info and required claims; avoid unnecessary external endpoint calls on the login path.

### 5.3. Subject Identifiers: Public and Pairwise

OIDC can issue a **public subject** (same `sub` across multiple clients under an issuer) or a **pairwise subject** (different `sub` across clients/sector identifiers to reduce unwanted correlation). If the portal and another application receive two different `sub` values from the same OP, that may be **spec-compliant** pairwise design, not a login bug.

Therefore never assume `sub` is an enterprise-wide employee ID or can be used directly to join across multiple applications. When accounts must be linked, use a controlled account-linking workflow at the broker/IAM with appropriate consent and policy, rather than auto-merging by email.

## 6. Trust Boundaries of an Identity Broker

A broker connects upstream and downstream via **two independent transactions**, rather than acting as a mere HTTP proxy forwarding tokens.

~~~text
           Trust relationship U                  Trust relationship D
  Upstream IdP <---- OIDC/SAML ----> Broker <---- OIDC ----> Portal
  - issuer U                        - RP/SP     - issuer B     - client portal
  - keys/certs U                    - policy    - keys B      - JWKS broker
  - subject U                       - mapping   - subject B   - aud portal
  - authn context U                            - own ID Token
~~~

**On the upstream side:**

- If upstream is **SAML 2.0**: the broker acts as a SAML SP, receives the assertion at ACS, and verifies the IdP signature, issuer, audience (targeting the **broker SP**), conditions, subject confirmation, `InResponseTo`, and replay.
- If upstream is **OIDC**: the broker acts as an OIDC RP, runs Authorization Code, and verifies the ID Token `iss/aud/exp/nonce` and other OIDC rules.
- If upstream uses LDAP/AD or custom auth: the broker is responsible for authenticating via the adapter per policy; the portal must not blindly trust all claims merely because the adapter reported "success".

**On the downstream side:**

- The broker mints **its own OIDC authorization code/tokens**, using the **broker's issuer**.
- The downstream ID Token has `aud=client_id` of the portal and a `sub` issued by the broker for the portal, which may be pairwise; it does not have to equal the SAML NameID or upstream subject.
- The portal verifies the **broker's signature/JWKS** and broker issuer; the portal **does not need and usually does not have** the private keys/metadata of every upstream IdP.

### 6.1. Why Not Forward the Upstream ID Token Intact?

Suppose the upstream OP issues an ID Token:

~~~text
iss = https://idp.partner.example
aud = broker-upstream-client
sub = upstream-user-77
~~~

Yet the downstream portal registered with the broker expects:

~~~text
iss = https://login.example.org/realms/enterprise
aud = portal-web
sub = broker-subject-981
~~~

If the broker passes the upstream token verbatim to the portal, **the token's issuer and audience do not match the downstream trust relationship**. A portal that accepts it by disabling `iss`/`aud` validation is a dangerous design prone to **token substitution / confused deputy**. The broker must issue its own token for the downstream transaction or use a **standardized and properly implemented token exchange mechanism**, never mutating claims while retaining the old signature.

**Do not "turn a SAML assertion into a JWT" by Base64-decoding it and copying NameID into `sub`**. That bypasses the SAML signature and condition semantics. The broker must verify SAML first, map to an internal broker identity, and then issue a new OIDC token aligned with downstream policy.

### 6.2. Identity Mapping at the Broker and the Application

A mapping may look like:

~~~text
upstream_identity_binding
  upstream_type    = SAML
  upstream_issuer  = urn:example:idp:employees
  upstream_subject = immutable-nameid-789
  broker_user_id   = broker-user-24

downstream_identity_binding
  broker_issuer    = https://login.example.org/realms/enterprise
  broker_subject   = pairwise-6f13a8
  client_id        = portal-web
  app_user_id      = user-42
  tenant           = tenant-acme
~~~

Binding records must be created and maintained through secure workflows. `email`/display name alone is insufficient to auto-merge upstream/downstream identities, especially when an IdP can recycle emails or an organization has multiple tenants with overlapping names.

**Do not confuse an internal broker user ID with the public downstream `sub`**: the broker may choose a pairwise subject. The portal can rely only on the issued and verified `iss+sub` together with its binding policy, and should not infer the upstream source from the subject string.

### 6.3. Can a Broker Elevate, Preserve, or Downgrade Assurance?

`acr`, `amr`, `auth_time`, and `max_age`/step-up requirements must be interpreted based on a **trust contract**. If upstream SAML authenticated with a password while downstream requires MFA, the broker **must not fabricate `amr=["mfa"]` just because the user holds a corporate account**. The broker can trigger step-up authentication upstream or perform an additional factor itself if policy allows, then emit claims that reflect reality.

Conversely, an RP should not treat an unagreed `acr` string as sufficient authority to approve a payment. **Authentication assurance is not synonymous with application authorization**.

## 7. Selecting the Upstream IdP in a Multi-Organization Environment

A federation system often needs **home realm discovery (HRD)**: the user chooses an organization, enters a domain hint, or visits a tenant-specific login URL, and the broker selects the IdP.

For example:

~~~text
portal.example.org/tenant/acme
    -> OIDC login to broker (client=portal-web)
    -> broker determines tenant=acme from config/transaction
    -> broker redirects to SAML IdP-A

portal.example.org/tenant/partner
    -> OIDC login to the same broker
    -> broker selects upstream OIDC IdP-B
~~~

**The source of truth for routing** must be a tenant/IdP allowlist configuration and protected transaction state; never use an arbitrary issuer URL supplied by the browser to trigger discovery. `login_hint`, `domain_hint`, email suffixes, or query parameters should serve only as **hints**, never as proof of tenant/issuer/role.

On callback, the broker must bind the upstream response to the **exact IdP selected for that transaction**, and then issue a downstream token stamped with the right tenant/subject. At the RP, `state`, nonce, registrationId, and tenant policy must also match the initiated request. This reduces the risk of **IdP mix-up**, account confusion, and cross-tenant data access.

### 7.1. What About Multiple OIDC Registrations at the Portal?

Spring Security supports multiple `ClientRegistration` entries, each with its own `registrationId`, `client-id`, and issuer/OP—for example, `broker-employees` and `broker-partners`. Never treat `registrationId` as proof that the returned token came from the right IdP: **the token's `iss` and signature** must still match the registration. If the broker is a single issuer that handles upstream routing itself, the portal may need only one registration; that is often a key benefit of identity brokering.

## 8. Java/Spring Boot: Registering an OIDC Client

Example project using **Spring Boot Servlet, Java 17+**, with appropriate Maven or Gradle management, using these dependencies:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

This is a **`dependencies` snippet inside a Gradle project that already configures plugins/repositories/version management**, not a complete build.gradle file. Spring Security will use **OAuth2 Client** and **OIDC login**; `spring-security-saml2-service-provider` is unnecessary if the **portal only knows the OIDC broker**. The SAML service provider library belongs on the **broker** side if the broker accepts upstream SAML and that functionality is implemented with Spring Security.

File `src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          broker:
            provider: broker
            client-id: portal-web
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          broker:
            issuer-uri: https://login.example.org/realms/enterprise
~~~

This is a **configuration sample** with a hypothetical OP and `client-id`. A live application requires an active OP issuer/discovery endpoint, a registered client, a **client secret loaded from a secret manager/environment**, and an exact redirect URI registered at the OP. Never commit secrets to the repository. If the OP supports/requires PKCE for confidential clients, configure PKCE explicitly using the appropriate `ClientRegistration.ClientSettings.requireProofKey` API for your version and verify that the authorization request includes `code_challenge_method=S256`; **do not assume Spring enables PKCE for every confidential client without verifying**. Public clients without a client secret have different settings and do not fit confidential server-side security assumptions.

In this configuration, having **`openid`** in `scope` is what distinguishes OIDC from plain OAuth login. When the `openid` scope is present, Spring Security uses OIDC components such as `OidcUserService`; if `openid` is omitted, a response cannot be treated as OIDC login merely because the provider has "identity" in its name.

### 8.1. SecurityFilterChain

File `src/main/java/example/portal/SecurityConfig.java`:

~~~java
package example.portal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**", "/error").permitAll()
                .requestMatchers("/admin/**").hasAuthority("app:admin")
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

When the right dependencies and registration are supplied, Spring Security uses common endpoints:

| Endpoint at RP | Purpose |
| --- | --- |
| **`GET /oauth2/authorization/broker`** | Initiates login, prepares the authorization request/state, and redirects to the OP. |
| **`GET /login/oauth2/code/broker`** | Receives the code/state callback and performs token exchange/verification. |
| `GET /login` | Default login page or custom page leading to the OP as configured. |
| `POST /logout` | Local logout when enabled with appropriate CSRF/session policy; **does not guarantee OP/upstream logout**. |

Default endpoint names can be customized via the DSL. **`/login/oauth2/code/broker` is not a SAML ACS `/login/saml2/sso/{registrationId}`**; the two protocols have different messages, filters, and validation rules.

This `SecurityConfig` code **does not yet implement a local admission gate or role mapping**. It illustrates enabling OIDC login and some authorization rules; if the application needs account locking or custom entitlements, logic must be added at the appropriate extension point.

### 8.2. Reading the Verified OIDC Principal

File `src/main/java/example/portal/WhoAmIController.java`:

~~~java
package example.portal;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {

    @GetMapping("/me")
    public Map<String, String> me(
            @AuthenticationPrincipal OidcUser principal) {

        String issuer = principal.getIdToken().getClaimAsString("iss");
        String subject = principal.getSubject();

        return Map.of("issuer", issuer, "subject", subject);
    }
}
~~~

In an application logged in via OIDC and protecting `/me`, Spring provides an `OidcUser` containing the ID Token/claims that passed through `oauth2Login` processing. Here it **displays only issuer/subject for learning**, without returning the raw ID Token or access token to the client. This endpoint is not an admin authorization service; its purpose is to inspect the identity pair.

Never let a controller accept `issuer` and `subject` POSTed by the client and treat them as a verified principal; read them from the server-side `Authentication`. This code is part of a Spring project and cannot be compiled with `javac` using Java SE alone without libraries.

### 8.3. PKCE in Spring Security

For **public clients**, Spring Security includes logic to use PKCE when the client has no secret and `client-authentication-method=none` under the proper configuration. For **confidential clients**, PKCE can be enabled explicitly via `ClientRegistration.ClientSettings.requireProofKey(true)` (exact API/builder varies by version). Verify that the OP supports `S256` and that the actual request contains `code_challenge`; do not assume `client_secret` replaces PKCE or that `scope=openid` enables PKCE automatically in every version.

Spring Security stores `OAuth2AuthorizationRequest` and related attributes via `AuthorizationRequestRepository` (typically backed by `HttpSession`) to match `state`, redirect URI, and the PKCE verifier. In multi-instance deployments, use a shared session/repository or consistent routing; never delete `state`/PKCE to "fix" multi-tab callback errors.

## 9. Local Accounts, Permissions, and JIT Provisioning After OIDC Login

A verified ID Token **does not grant unrestricted portal access**. The application may have locked accounts, unprovisioned users, missing role assignments, or tenant mismatches.

### 9.1. Mapping `iss` + `sub` to a Local Account

~~~text
Verified OIDC identity:
    issuer  = https://login.example.org/realms/enterprise
    subject = pairwise-6f13a8

Federated identity binding:
    (issuer, subject) -> local_user_id = user-42

Local account:
    status    = ACTIVE
    tenant_id = tenant-acme
    roles     = [REPORT_VIEWER]
~~~

**Never use email as the sole unique key**; email can change, be recycled, or remain unverified according to the RP's policy expectations. When a broker changes its issuer or switches from public `sub` to pairwise `sub`, a controlled re-linking process is required; never auto-merge solely because emails match.

### 9.2. When Should the SP Grant Entry?

| Local Status/Policy | Valid OIDC ID Token? | Portal Decision |
| --- | --- | --- |
| `ACTIVE`, authorized for the application | Yes | Establish session with approved authorities. |
| `LOCKED` or `DISABLED` | Yes | Deny application login; do not treat "OP succeeded" as unlocking the account. |
| `PENDING_APPROVAL` | Yes | Grant no business permissions; optionally show a limited waiting-for-approval page. |
| No local account, JIT disabled | Yes | Deny by default. |
| No account, JIT enabled per policy | Yes | Create/find account solely by issuer+sub, unique constraint, least privilege, avoiding reactivation of locked accounts. |
| ACTIVE account missing `reports:read` | Yes | May allow login, but the reporting API returns 403. |
| Does not belong to requested tenant | Yes | Deny permissions for that tenant. |
| Status/entitlement DB unavailable | Yes | **Fail closed** for mandatory authorization checks. |

In Spring Security, the extension point `oauth2Login(oauth2 -> oauth2.userInfoEndpoint(userInfo -> userInfo.oidcUserService(...)))` lets you run an `OAuth2UserService<OidcUserRequest, OidcUser>`: you can delegate to the default `OidcUserService`, then apply **local account admission**, map authorities, and return an appropriate `OidcUser` or throw `OAuth2AuthenticationException` when denied. You must preserve the framework's ID Token verification and retain the original `iss/sub`; never construct a fake principal from `email` to bypass trust.

Distinguish **ID Token claims** from **approved app entitlements**. `groups` can serve as an input when a mapping and trust contract exist, but local deny/lock rules must win, and a default `ROLE_USER` must not automatically grant access to every resource. Multi-tenant APIs also require **resource ownership and tenant checks** after login.

### 9.3. Runnable Java 17: OIDC Identity and Local Policy

The standalone example below assumes the ID Token **has already been verified externally**; it illustrates account binding via `iss+sub`, deny decisions, and per-tenant permissions. It does not parse JWTs or replace an OIDC validator.

File **`OidcIdentityPolicyDemo.java`**:

~~~java
import java.util.Map;
import java.util.Set;

public class OidcIdentityPolicyDemo {

    record IdentityKey(String issuer, String subject) {}
    record Account(String localUserId, String tenantId,
                   boolean enabled, Set<String> permissions) {}

    static String authorize(
            IdentityKey verifiedIdentity,
            String requestedTenant,
            String permission,
            Map<IdentityKey, Account> bindings) {

        Account account = bindings.get(verifiedIdentity);
        if (account == null) {
            return "NO_BINDING";
        }
        if (!account.enabled()) {
            return "ACCOUNT_BLOCKED";
        }
        if (!account.tenantId().equals(requestedTenant)) {
            return "TENANT_DENIED";
        }
        if (!account.permissions().contains(permission)) {
            return "PERMISSION_DENIED";
        }
        return "ALLOW:" + account.localUserId();
    }

    public static void main(String[] args) {
        String broker = "https://login.example.org/realms/enterprise";
        IdentityKey alice = new IdentityKey(broker, "pairwise-A");
        IdentityKey bob = new IdentityKey(broker, "pairwise-B");

        Map<IdentityKey, Account> bindings = Map.of(
                alice, new Account("user-42", "tenant-acme", true,
                                   Set.of("reports:read")),
                bob, new Account("user-57", "tenant-acme", false,
                                 Set.of("reports:read"))
        );

        System.out.println(authorize(
                alice, "tenant-acme", "reports:read", bindings));
        System.out.println(authorize(
                bob, "tenant-acme", "reports:read", bindings));
        System.out.println(authorize(
                alice, "tenant-acme", "reports:write", bindings));
        System.out.println(authorize(
                alice, "tenant-other", "reports:read", bindings));
        System.out.println(authorize(
                new IdentityKey("https://idp.other.example", "pairwise-A"),
                "tenant-acme", "reports:read", bindings));
    }
}
~~~

Run with Java 17:

~~~bash
javac OidcIdentityPolicyDemo.java
java OidcIdentityPolicyDemo
~~~

**Exact stdout:**

~~~text
ALLOW:user-42
ACCOUNT_BLOCKED
PERMISSION_DENIED
TENANT_DENIED
NO_BINDING
~~~

The final line proves that the same `sub=pairwise-A` string from a **different issuer** is never assumed to be the same local account. The middle lines show that a valid token neither overrides a local account lock nor grants extra permissions. The code omits JWT parsing, PKCE, nonce, sessions, DB sync, and token revocation: those belong to other layers. `verifiedIdentity` must never be taken from headers/JSON sent by the browser.

## 10. Resource Server: Use an Access Token, Not an ID Token

Suppose the portal calls `reports-api.example.org` after login:

~~~text
Browser -- session cookie --> Portal (OIDC RP)
                                  |
                             Access Token
                                  |
                                  v
                         Reports API (Resource Server)
                         - validate issuer
                         - validate audience=reports-api
                         - validate signature/expiry
                         - enforce scope + tenant + resource
~~~

In a separate **Spring Security Resource Server**, you can configure `spring-boot-starter-oauth2-resource-server` and:

~~~java
http.authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated())
    .oauth2ResourceServer(oauth2 -> oauth2
        .jwt(org.springframework.security.config.Customizer.withDefaults()));
~~~

This is a **configuration fragment inside an `HttpSecurity` method**, not a standalone class. You must configure the JWT decoder/issuer and an **audience validator per token contract**, rather than enabling JWT signature validation and assuming the API audience/tenant is always valid. The broker's access token must have an audience/scope intended for the API; if the broker does not issue an API token with the right audience, use a standards-based and policy-approved OAuth flow/token exchange—**do not send the portal's ID Token to the API**.

### 10.1. Be Careful with Token Exchange and Downstream Propagation

Identity brokering for authentication is **different** from calling APIs "on behalf of" a user. A broker may issue an ID Token for the portal and an access token for a specific API, or the portal may need to obtain another token issued by an AS trusted by that API. Passing the raw upstream access token straight to downstream APIs is usually wrong because **audience, issuer, scope, and consent** differ. Perform token exchange/delegation only when there is a clear protocol, trust policy, and API support.

**Do not store access tokens or refresh tokens in localStorage or logs when using a server-side BFF**. The backend-for-frontend pattern stores sensitive tokens server-side while the browser holds only an appropriate HttpOnly/Secure session cookie, reducing token exposure via XSS. CSRF protection is required for state-changing requests using session cookies.

## 11. Login Sessions and Logout in Federation

There are at least **three distinct session lifecycles**:

| Session | Owned By | What Expiration/Logout Affects |
| --- | --- | --- |
| RP browser `HttpSession`/SecurityContext | Portal | Access to the portal with that cookie. |
| OIDC session at Broker OP | Identity broker | SSO capability across multiple downstream RP apps. |
| Login session at upstream IdP | SAML/OIDC IdP | Broker's ability to re-authenticate or SSO into other services. |

**Logging out of the portal does not automatically log out of the upstream IdP.** If only `JSESSIONID` is cleared, the browser can reopen the portal, get redirected to the broker, and **log right back in without entering a password** because the OP/upstream session is still alive.

### 11.1. Local Logout vs. RP-Initiated Logout

- **Local logout:** invalidates the RP session/cookie and `SecurityContext`; does not guarantee the OP or upstream loses its session.
- **OIDC RP-initiated logout:** if supported by the OP, the RP redirects the browser to the **end-session endpoint** using `id_token_hint` and a registered/allowlisted post-logout redirect URI per profile/OP.
- **Broker-to-upstream logout:** the broker may invoke a separate flow with the SAML/OIDC IdP, though not every upstream supports or agrees to it; handle fan-out policy and partial states.
- **Front-channel/back-channel logout:** depends on OP/RP and application capabilities; logout messages/tokens must be verified per spec and sessions managed strictly by `sid`/`iss`/`sub`. **Do not assume enabling `oauth2Login` enables every kind of logout**.
- **Already-issued JWT access tokens:** local logout does not revoke stateless JWTs at APIs. Use short TTLs, revocation/introspection/session versioning, or equivalent mechanisms.

In **Spring Security Servlet**, `OidcClientInitiatedLogoutSuccessHandler` supports RP-initiated logout when the OP publishes the required metadata; do not confuse it with the **reactive** class `OidcClientInitiatedServerLogoutSuccessHandler`. Configuration must match your version, registration, and post-logout URI. Never take `post_logout_redirect_uri` from an unchecked query parameter because of open redirect risks.

### 11.2. Token Lifetime Differs from Session Lifetime

An ID Token's `exp` means the token is no longer accepted by the RP during **new token validation**. It **does not automatically mean** the RP HTTP session must terminate at that exact second of `exp`; application session management is a separate policy. Similarly, a living refresh token or OP session does not authorize API access if the account has been locked at the portal. When rapid revocation is needed, check local status, session revocation, and current API authorization.

## 12. Securing OIDC Transactions: Threat-by-Threat Checklist

| Risk | Core Mitigation |
| --- | --- |
| **Login CSRF** | Verify tamper-resistant `state`, bind transaction to browser session; reject callbacks without an originating request. |
| **Authorization code interception/injection** | **PKCE S256**, exact-match redirect URI, proper client authentication, short-lived single-use codes. |
| **ID Token substitution/replay** | Signature/issuer/audience/time/nonce validation and transaction binding. |
| **Mix-up between two OPs/IdPs** | Pin issuer/registration to the transaction, match metadata `issuer` and token `iss` exactly. |
| **JWT algorithm confusion** | Allowlist signature algorithms, use the right OP JWKS, reject `alg=none`, never fetch `jku` from JWT headers. |
| **SSRF via discovery** | Operator-managed issuers/endpoints, HTTPS, and egress policy; never follow user-supplied URLs. |
| **Open redirect** | Exact registered redirect URIs; internal/allowlisted post-login return routes and session-bound state. |
| **Token leakage via browser/logs** | Never put access/refresh tokens in URLs, logs, or referrers; use HttpOnly/Secure cookies for server sessions. |
| **CSRF on API sessions** | Do not disable CSRF globally just because OIDC is used; design cookies and CSRF protection for state-changing requests. |
| **Cross-tenant data leak** | Use issuer/sub mapping and tenant entitlements; enforce ownership/resource checks on the backend. |
| **Account auto-provision bypass** | Policy-driven JIT, unique binding, lock history checks, tenant approval, least privilege. |
| **Key rotation/compromise** | Cache JWKS with refresh/monitoring, handle revoked keys; never "disable signature checks" during rotation. |
| **Proxy/hostname mismatch** | Configure trusted forwarded headers, HTTPS public base URL, and exact callbacks. |
| **Multi-node session loss** | Shared HttpSession/authorization request store or safe routing; never drop state/nonce to work around errors. |
| **UserInfo subject mismatch** | Verify `userinfo.sub == id_token.sub`; never map users by email from another response. |

**Do not "simplify" OIDC by moving JWT verification into frontend JavaScript and trusting an `X-User` header on the backend**. The backend needs an identity authenticated by the framework or a valid token for the exact audience and trust context. Application security still requires CSRF/XSS/session controls, HTTPS, least privilege, and auditing.

## 13. Troubleshooting by Boundary and Real-World Errors

| Symptom | Likely Failure Location | How to Diagnose |
| --- | --- | --- |
| Clicking Login returns 404 on `/oauth2/authorization/broker`. | Missing registrationId, `oauth2Login` not enabled, or wrong filter chain. | Check dependencies, `broker` registration, filter chain, and login endpoint. |
| Redirect URI mismatch at OP. | Registered URI differs from portal runtime URI. | Compare `{baseUrl}/login/oauth2/code/broker`, scheme/host/port, and proxy headers. |
| `invalid_client` during code exchange. | Wrong client secret/authentication method or unregistered client. | Check secret manager/registration and OP logs; do not expose secrets. |
| `invalid_grant` at token endpoint. | Expired/reused code, wrong PKCE verifier, mismatched redirect URI. | Check correlation ID, code TTL, per-transaction verifier, and clock sync. |
| State mismatch or missing authorization request. | Lost session cookie, SameSite issue, multiple tabs, or load balancer hitting another node. | Check callback cookie, session store, and state repository. |
| Issuer validation fails. | Metadata `issuer` differs from ID Token `iss` or wrong OP selected. | Compare exact HTTPS issuer, tenant, discovery, and registration. |
| Audience validation fails. | ID Token intended for another client (broker/upstream) or wrong client-id. | Compare `aud` and `client_id`; **never disable audience validation**. |
| Signature/JWKS error. | Signing key rotation, stale JWKS cache, mismatched `kid`, wrong algorithm. | Check trusted OP metadata/JWKS, refresh policy, and rotation timing. |
| UserInfo returns a different user. | Wrong access token used or OP returns mismatched `sub`. | Compare `UserInfo.sub` against ID Token; reject on mismatch. |
| Upstream IdP login succeeds, yet portal entry fails. | Broker mapping/policy, downstream OIDC callback, or account admission. | Pinpoint which leg failed; never equate upstream success with downstream success. |
| Login succeeds, then feature returns 403. | Insufficient local role/tenant/permission. | Check authorization and approved entitlements; do not "swap ID Tokens" to fix permissions. |
| Account has the right email but lands in the wrong local user. | Mapping by email instead of `iss+sub`. | Fix identity binding and migration process; audit merges. |
| Immediately auto-logs back in right after logout. | Local logout only while OP/upstream session remains active. | Distinguish local, RP-initiated, and broker/upstream logout. |
| API returns 401 even though portal is logged in. | Missing access token, wrong API audience, or API requires different scopes. | Inspect **access token** `aud`/`scope` and resource server config. |
| Two tenants pick the wrong IdP. | Home realm routing relies on URL/email hints without transaction binding. | Check HRD allowlist, issuer, and tenant binding. |

**Sensible debugging order:** (1) URL/registration/OP discovery → (2) `state` and session cookie → (3) PKCE/client/token exchange → (4) ID Token signature/issuer/audience/time/nonce → (5) broker identity mapping → (6) local admission → (7) Spring session/authorization → (8) API token audience/resource permissions. Log **error codes and correlation IDs**, never tokens, cookies, or secrets.

## 14. Required Test Suite Before Production

| Test Case | Expected Outcome |
| --- | --- |
| OIDC code flow with trusted test OP and valid `state`/PKCE/nonce. | Login succeeds and creates local Authentication per policy. |
| Callback with `state` from another browser. | Rejected; no login CSRF. |
| Callback reusing an already-exchanged code. | Token endpoint rejects; no second login. |
| Wrong or missing PKCE `code_verifier` when challenge is required. | Token exchange rejected. |
| ID Token `iss` differs from metadata/registration. | Rejected. |
| `aud` does not contain portal client ID. | Rejected even when signature is valid. |
| Expired or not-yet-valid ID Token per policy. | Rejected. |
| ID Token `nonce` does not match sent request. | Rejected. |
| ID Token signed by a key outside trusted OP JWKS. | Rejected. |
| OP rotates JWKS signing key per spec. | Trust updates safely per policy without failing open. |
| UserInfo `sub` differs from ID Token `sub`. | Reject using UserInfo data. |
| Two OPs share the same email but have different `iss+sub`. | Never auto-merge local accounts. |
| Broker uses upstream SAML and downstream OIDC. | Broker verifies SAML; portal accepts only broker issuer/portal audience tokens. |
| Portal directly receives upstream ID Token with `aud=broker-client`. | Rejected. |
| Local account is LOCKED while broker OIDC succeeds. | Application access denied. |
| User is ACTIVE but lacks reporting entitlement. | Resource denied, typically 403. |
| Token has wrong API audience. | Resource Server rejects; ID Token cannot substitute. |
| Multi-tab login in same session returning out of order. | Independent state/nonce/PKCE per transaction; no identity mix-up. |
| Callback hits a different node than the initiating node. | Shared state succeeds or fails closed; never drop state. |
| Broker loses upstream session while portal retains local session. | Correct TTL/logout/re-auth policy behavior without guessing which session was revoked. |
| Local logout while OP session remains active. | Application acknowledges scope and does not claim whole federation logged out. |
| Redirect URI or post-logout URL points to an unregistered external host. | Rejected; no open redirect. |
| Upstream IdP sends weak assurance while portal requires MFA. | Broker does not fabricate claims; triggers step-up or denies. |

Tests must use a **valid test OP/IdP and controlled signed tokens**. A unit test that only parses JWT payloads does not prove OIDC authentication is correct. Include real browsers (cookies/SameSite), reverse proxies, token endpoints, accounts, and API authorization.

## 15. Misconceptions to Avoid

1. **"OAuth2 = OIDC."** No; OIDC is an identity layer on OAuth 2.0 with an ID Token and identity verification rules.
2. **"An Access Token proves the user logged into the portal."** Do not use an access token for RP login in OIDC designs; use an ID Token and the OIDC flow.
3. **"An ID Token can call any API."** False: an ID Token's audience is the RP, while APIs use access tokens scoped to the resource server.
4. **"Decoding email from a JWT is enough."** False: you must verify signature/issuer/audience/expiration/nonce.
5. **"Email is a stable, unique identifier."** False: use `iss+sub` as the canonical key.
6. **"`sub` is always identical across all clients and IdPs."** False: there are public/pairwise subjects and issuer scoping.
7. **"The broker just forwards the upstream ID Token to the portal."** False: trust/issuer/audience differ across the two legs; the broker issues its own downstream token.
8. **"The broker trusts SAML NameID without verifying the assertion."** False: the broker must verify signature/conditions/subject confirmation/replay.
9. **"A client secret means PKCE is unnecessary."** Not true; PKCE should be enabled/verified for Authorization Code Flow per policy.
10. **"`state`, `nonce`, and PKCE are all the same thing."** False: they mitigate different risks at different steps.
11. **"Take the issuer URL from a user form and run discovery."** Dangerous: SSRF/mix-up; use an OP allowlist/config.
12. **"If the IdP group says admin, the portal always grants admin."** False: application/tenant permissions require approved mapping and local policy.
13. **"Logging in via a broker means the portal needs no authorization."** False: tenant/ownership/business policies remain the RP/API's responsibility.
14. **"Local logout clears every OP/upstream session."** False: sessions are separate and logout can be partial.
15. **"`oauth2Login` automatically makes the app an OAuth2 Resource Server."** False: client login and API JWT verification are two separate roles.
16. **"If JWKS rotation breaks, temporarily skip signature verification."** False: handle key lifecycle safely; never fail open.
17. **"Successful OIDC means JIT creates an ACTIVE user unconditionally."** False: enforce local admission, approval, status checks, and locked-account bypass prevention.
18. **"SAML and OIDC share the same callback URL."** False: SAML ACS receives `SAMLResponse`, while the OIDC callback receives an authorization code and state.

## 16. Federation Architecture Implementation Checklist

1. Does the RP have a **specific OIDC trust relationship** with the broker/OP, with the right `issuer-uri`, `client_id`, redirect URI, and `openid` scope?
2. Are Authorization Code + PKCE S256, TLS, per-transaction state, and nonce (when required) in use?
3. Is the ID Token validated for **issuer, signature/JWKS, aud/azp, exp/iat, and nonce** per profile?
4. If UserInfo is used, is `sub` checked against the ID Token?
5. Are local users identified by **`iss+sub`**, rather than email or self-asserted roles?
6. If the broker accepts upstream SAML, does it validate SAML signature, audience, conditions, subject confirmation/`InResponseTo`, and replay?
7. Does the broker **mint its own** downstream ID Token with the right `iss`, `aud`, subject, and assurance policy?
8. Are HRD/tenant mapping policies and IdP mix-up protections enforced without trusting user-supplied issuer URLs?
9. Are JIT/account admission/entitlement policies, revocation, and deny-precedence enforced?
10. Do APIs accept **audience-specific access tokens** rather than the portal's ID Token?
11. Are proxies, callback URIs, SameSite/Secure cookies, and session stores tested in realistic deployments?
12. Are there separate policies for local logout, RP-initiated logout, OP/upstream logout, and token revocation?
13. Have multi-tab logins, IdP failures, broker outages, key rotation, refresh token expiry, and database failures been tested?
14. Are logs/audits keyed by correlation ID without storing raw tokens, cookies, secrets, or PII?

## 17. Self-Check Questions

1. **How does OIDC differ from OAuth 2.0?** — OIDC standardizes user authentication via the **ID Token** and rules on claims/issuer/client.
2. **What are the broker's two roles?** — **RP/SP** when trusting upstream and **OP/AS** when issuing downstream.
3. **Which token logs a user into an RP?** — A verified **ID Token** bound to the OIDC transaction.
4. **Which token is used to call a protected API?** — A valid **Access Token** scoped to the API's audience/scopes.
5. **What is the stable OIDC identity key?** — The **`iss` + `sub`** pair; not email.
6. **Why must `aud` contain the portal's `client_id`?** — Because the token is only valid for authenticating to that designated RP.
7. **What do `state`, `nonce`, and PKCE do?** — State protects correlation/CSRF, nonce binds the ID Token to the authentication request, and PKCE binds code exchange to the initiating client.
8. **Can an upstream ID Token be sent straight to a downstream RP?** — No in standard brokering; issuer/audience and trust differ.
9. **Must a SAML NameID equal the OIDC `sub` issued by the broker?** — No; the broker performs identity mapping and may issue pairwise subjects.
10. **Does enabling `oauth2Login` check LOCKED local accounts and tenant permissions?** — No; you must wire in admission and authorization separately.
11. **When an ID Token expires, do all RP HttpSessions vanish immediately?** — Not automatically; session policy is independent.
12. **Does portal logout guarantee upstream IdP logout?** — No; that requires separate logout orchestration and protocol support.

## References

- [OpenID Connect Core 1.0 — Authorization Code Flow, ID Token Validation, UserInfo, Subject Types](https://openid.net/specs/openid-connect-core-1_0.html)
- [OpenID Connect Discovery 1.0 — issuer, metadata, JWKS](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [OAuth 2.0 Security Best Current Practice — RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html)
- [OAuth 2.0 PKCE — RFC 7636](https://www.rfc-editor.org/rfc/rfc7636.html)
- [Spring Security — OAuth2/OIDC Servlet Login Overview](https://docs.spring.io/spring-security/reference/servlet/oauth2/index.html)
- [Spring Security — Advanced OAuth2 Login, OidcUserService, and UserInfo](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Security — Client Authorization Grants / PKCE](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html)
- [Spring Security — OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html)
