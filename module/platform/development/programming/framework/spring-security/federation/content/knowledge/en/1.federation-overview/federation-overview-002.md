# Single Sign-On (SSO) and Its Relationship with Identity Federation

> **Context:** Spring Security – federation (identity federation), **Federation Overview** section.

## Learning Objectives

After this lesson, you will be able to:

1. Correctly explain **Single Sign-On (SSO)**, **identity federation**, authentication, and authorization.
2. Distinguish the login session at the **Identity Provider (IdP)** from each application's own session; understand why SSO can happen but is not guaranteed on every access.
3. Describe the SSO flow with OpenID Connect (OIDC) and compare it with SAML 2.0.
4. Configure a Spring Security application acting as a **Relying Party/OIDC Client** to sign in via an IdP.
5. Recognize trust boundaries, user mapping strategies, and common security mistakes.

## 1. Real-World Problem: One Employee, Multiple Applications

An employee uses an **HR Portal**, **CRM**, and **Support Portal**. All three applications need to know who is accessing them, but should not store three independent passwords themselves. The enterprise can use an IdP (such as an organization's identity management system) to authenticate employees. If the employee just signed in to the HR Portal and the IdP session is still valid, when visiting the CRM, the IdP can confirm the user immediately without asking for a password again: this is the **SSO experience**.

If the Support Portal is operated by another partner, the enterprise and the partner must establish a trust relationship, protocol, and identity acceptance rules so that the partner accepts authentication results from the enterprise's IdP. That is **identity federation**. When the Support Portal's login flow redirects the user to the IdP and the IdP reuses the existing session, **federation enables SSO across organizational boundaries**.

The two concepts complement each other but are not synonymous:

- **SSO** describes the *experience*: authenticating once and accessing multiple applications without usually re-entering credentials while sessions/security conditions remain valid.
- **Federation** describes the *trust relationship and how identity is exchanged*: one party accepts authentication evidence issued by another party.
- An internal system can have SSO without needing identity federation between two organizations. A federated system can also require re-authentication or MFA every time due to policy; therefore, not every access is "passwordless".

## 2. Roles and Terms to Distinguish

| Term | Meaning in This Lesson | Example |
| --- | --- | --- |
| **User / End User** | The user accessing the application. | An employee opening the CRM. |
| **Identity Provider (IdP)** | The party that authenticates users, manages login sessions, and issues identity information/assertions. | Enterprise IdP. |
| **Relying Party (RP)** | An application that trusts the authentication result of an OpenID Provider under OIDC. | CRM using OIDC Login. |
| **Service Provider (SP)** | Common term in SAML for an application receiving SAML assertions. | Partner portal using SAML. |
| **Client Registration** | Configuration of the relationship between an application and a provider: client ID, redirect URI, scopes, issuer… | The `corp` registration in Spring Boot. |
| **Authentication** | Establishing identity or verifying evidence about a user. | Signing in with password + MFA at the IdP. |
| **Authorization** | Deciding whether an authenticated user is allowed to perform an action. | Only HR staff can view salary data. |
| **Trust relationship** | Technical/policy agreement for an application to accept identities from a specific IdP. | RP configures issuer, client ID, verification keys. |

**Key point:** "Authenticated by the IdP" does not mean "allowed to use every resource". The application must still check access rights based on its own requirements and policies.

### Three Scenarios for Comparison

| Scenario | Federation? | SSO Experience? |
| --- | --- | --- |
| Two applications in the same organization use a central login service, with no trust relationship with external organizations. | Not necessarily cross-organization federation. | Possible, thanks to reusing the IdP session. |
| A partner portal trusts the enterprise's IdP, but the user must re-authenticate due to mandatory policy. | Yes. | Not "seamless" on that access. |
| A partner portal trusts the enterprise's IdP and the IdP uses an active session. | Yes. | Usually yes, if security conditions allow. |

## 3. How Does SSO Work in a Federation Model?

Imagine two applications **App A** and **App B**, each registered as a separate OIDC Client at the same IdP.

~~~text
User Browser                    App A / App B                   IdP
        |                           |                            |
        |-- access App A ---------->|                            |
        |<-- redirect to login -----|                            |
        |------------------------ sign in / MFA ---------------->|
        |<------------------- result via redirect ---------------|
        |-- callback to App A ----->|-- exchange code / verify ->|
        |                           |<-- ID Token / tokens ------|
        |<-- App A's own session ---|                            |
        |                           |                            |
        |-- access App B ---------->|                            |
        |<-- redirect to login -----|                            |
        |---------------------- request to IdP ----------------->|
        |<-- IdP reuses session if eligible ---------------------|
        |-- callback to App B ----->|-- exchange code / verify ->|
        |                           |<-- ID Token / tokens ------|
        |<-- App B's own session ---|                            |
~~~

On the first visit, the user actually needs to sign in with the IdP. Afterward, the browser typically keeps the IdP's session cookie according to the IdP's policy. When App B redirects the browser to the IdP, the IdP can recognize this session and complete the request without asking for a password again. Each application still establishes **its own application session** after processing the result from the IdP.

Important consequences to remember:

- **App A's session cookie is not shared with App B.** SSO typically happens because the IdP authenticates the user for multiple applications, and each application manages its own session.
- **Do not arbitrarily share ID Tokens or Access Tokens across applications.** Tokens have specific audiences, scopes, lifetimes, and purposes.
- If the IdP session expires, the user is prompted to re-authenticate, or MFA is required, visiting App B can still display a login prompt.
- If the user has an active session in App A, the expiration of the IdP session does not automatically invalidate App A's session immediately; that depends on the application's session lifetime and sync/logout mechanisms.

### How Long Does "Sign In Once" Last?

There is no universal SSO duration across all applications. It is affected by the **IdP session**, **each application's session**, re-authentication conditions (risk-based authentication, MFA, `max_age`/`prompt=login` in OIDC when used), cookie policies, and the browser's ability to maintain sessions across domains. Therefore, SSO requirements should be defined in terms of verifiable behaviors and policies, rather than promising "sign in once forever".

## 4. Protocols: SAML 2.0, OIDC, and OAuth 2.0

| Mechanism | Primary Purpose | Typical Data / Flow | Common Context |
| --- | --- | --- | --- |
| **SAML 2.0 Web Browser SSO** | Transmits authentication info between IdP and SP. | SAML AuthnRequest/Response containing XML assertion, digitally signed. | Enterprise SSO and many traditional B2B integrations. |
| **OpenID Connect (OIDC)** | Identity authentication layer built on OAuth 2.0. | Authorization Code Flow, ID Token (usually JWT), user claims. | Web apps, mobile apps, modern systems. |
| **OAuth 2.0** | Authorizes access to resources/APIs. | Access token, scopes, token endpoint. | Client calling APIs on behalf of a user or application. |

**Very important distinction:** OAuth 2.0 itself is an *authorization* framework; it is not a standard specification for "logging in a user". When standardized user identity authentication is needed, use **OIDC** (`openid` scope and ID Token verification) or an equivalent authentication protocol. Access tokens are for the **resource server/API**; ID Tokens are for the **OIDC Client/RP**, and ID Tokens must not be sent as bearer tokens to call APIs.

### 4.1. OIDC Authorization Code Flow (Server-Side Web Application)

1. The user requests a protected page at the RP.
2. The RP constructs a request to the IdP's authorization endpoint with `client_id`, `redirect_uri`, `scope=openid`, `state`, and appropriate security parameters.
3. The IdP checks the session and may require login/MFA/consent to share information.
4. The IdP redirects the browser back to the registered callback with an **authorization code** and `state`.
5. The RP validates `state` and uses back-channel HTTPS to exchange the code at the token endpoint.
6. The RP verifies the ID Token, especially the issuer (`iss`), audience (`aud`), signature, expiration (`exp`), and nonce when applicable; the library also handles other protocol constraints.
7. The RP maps the received identity to an internal user/permissions per policy; Spring Security stores the `Authentication` in the security context and manages the application session.
8. Subsequent requests to the RP can use the RP session without repeating the entire flow. When entering another RP, the IdP can reuse the IdP session: that enables SSO.

**PKCE** binds the authorization code to the client that initiated the request; it should be used according to client type and current security profiles. `state` protects the return flow from request mix-ups, and `nonce` binds the ID Token to the OIDC authentication session when applicable. You should not manually implement token verification or callback handling when Spring Security already supports it.

### 4.2. SAML 2.0 Web Browser SSO

Conceptually equivalent flow: the SP redirects the user to the IdP with an **AuthnRequest** (if SP-initiated); the IdP returns a **SAML Response/Assertion** via the browser to the SP's **Assertion Consumer Service (ACS)**; the SP verifies the signature and assertion conditions and then creates an application session. Pay attention to **entity ID/issuer**, trusted certificates, audience, recipient, `InResponseTo`, time validity, and ACS configuration. OIDC and SAML differ in objects/credential formats; do not apply OIDC JWT verification assumptions directly to SAML XML assertions.

## 5. Identity Federation Involves More Than a Login Protocol

A proper federation relationship requires answering:

1. **Whom to trust?** Which issuers/IdPs, environments/tenants, and verification key sets does the application accept? Never accept an arbitrary issuer supplied by the request itself.
2. **What to verify?** Signatures, recipients, callbacks, lifetimes, request correlation, and authentication/MFA assurance requirements.
3. **Who is the internal account?** Rely on stable identifiers from the IdP, not merely display names or email addresses.
4. **What are they allowed to do?** Roles and permissions granted on the application side or through an approved mapping policy.
5. **How are account changes/departures handled?** Provision/deprovision workflows, group/role sync, session invalidation, auditing, and re-authentication requirements.
6. **What if the IdP has an outage?** Timeout handling, error messages, and operational strategies without opening authentication bypasses.

### Identifier Key: issuer + subject

In OIDC, a secure identifier for matching accounts is typically designed from **issuer (`iss`) + subject (`sub`)** within the registered RP context, rather than using `email` alone. Emails can change, be reused, or remain unverified; even if `email_verified` is present, it does not replace all policy checks. With pairwise subjects, the same person can have different `sub` values across different RPs, so **never assume all applications will receive the same subject**.

~~~text
Internal mapping table (illustrative)
provider_issuer                         external_subject        local_user_id
https://idp.example.org/realms/acme     u-7c93a1                1842
~~~

After authentication, Spring Security knows which principal is signed in. Mapping the principal to a business account, granting department permissions, or creating an account Just-in-Time (JIT) is **the application's decision**, requiring clear rules. Never automatically grant admin permissions just from an email matching a company domain.

## 6. Spring Security Example: Application Acting as an OIDC Relying Party

Standalone example using **Java 17 + Spring Boot 3.3.x / Spring Security 6.x**, Servlet application style (Spring MVC). This is an RP application, **not an IdP implementation**. To complete sign-in, you need a real OIDC IdP with a working discovery endpoint and a corresponding registered client.

### 6.1. Project Structure

~~~text
sso-federation-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/federationdemo/
    │   ├── FederationDemoApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── resources/application.yml
~~~

`settings.gradle`

~~~groovy
rootProject.name = 'sso-federation-demo'
~~~

`build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
}
~~~

The three dependencies have distinct roles: **Web** receives HTTP requests; **Security** enforces endpoint protection policies; **OAuth2 Client** provides OAuth2 Login/OIDC flows, client registration, and callback handling. If you only want a REST API receiving bearer access tokens from other clients, that is an **OAuth2 Resource Server** scenario and has a different configuration from this login example.

### 6.2. Bootstrap Application

`src/main/java/com/example/federationdemo/FederationDemoApplication.java`

~~~java
package com.example.federationdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FederationDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(FederationDemoApplication.class, args);
    }
}
~~~

### 6.3. Enable OAuth2 Login and Protect Resources

`src/main/java/com/example/federationdemo/SecurityConfig.java`

~~~java
package com.example.federationdemo;

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
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

- Path `/` is public; `/me` is protected by the remaining rule.
- `oauth2Login` sends unauthenticated users into the login flow via the configured OIDC provider.
- Spring Security handles the default endpoints and callbacks; **no custom controller is needed to handle the authorization code**.
- This sample only requires sign-in; sensitive endpoints must add appropriate **role/permission-based authorization**. The `authenticated()` rule does not imply business permissions.
- For session-based applications using forms/HTTP POST, keep default CSRF protection; do not disable CSRF just to "fix a login error".

### 6.4. Display the Verified Identity

`src/main/java/com/example/federationdemo/DemoController.java`

~~~java
package com.example.federationdemo;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "Open /me to sign in through the IdP";
    }

    @GetMapping("/me")
    public Map<String, String> me(@AuthenticationPrincipal OidcUser user) {
        return Map.of(
            "issuer", user.getIssuer().toString(),
            "subject", user.getSubject()
        );
    }
}
~~~

`OidcUser` represents a user authenticated via OIDC; the example outputs only **issuer and subject** to observe the trust relationship. Do not return access tokens, full ID Tokens, refresh tokens, or sensitive claims in demo endpoints or production logs.

### 6.5. Declare the OIDC Client and IdP

`src/main/resources/application.yml`

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp-idp
            client-id: YOUR_CLIENT_ID
            client-secret: YOUR_CLIENT_SECRET
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
              - email
        provider:
          corp-idp:
            issuer-uri: https://idp.example.org/realms/acme
~~~

These are **sample values**, not a live IdP. Replace `issuer-uri` with the real issuer URL published by your IdP, and inject `client-id`/`client-secret` via environment variables or a secret manager when deploying, avoiding committing secrets to Git. For an IdP with OIDC discovery, Spring can fetch endpoints and public keys from the issuer's metadata; the issuer and HTTPS must be configured/verified accurately.

On the IdP side, create a confidential web client and register the redirect URI for the local environment:

~~~text
http://localhost:8080/login/oauth2/code/corp
~~~

`corp` is the `registrationId`, not a username. Default login initiation endpoint:

~~~text
http://localhost:8080/oauth2/authorization/corp
~~~

The default callback URI uses the pattern `{baseUrl}/login/oauth2/code/{registrationId}`. When running behind a reverse proxy, ensure the base URL, HTTPS, host, and forwarded headers reflect the correct public URL; the redirect URI **must match the IdP's allow-list policy**.

### 6.6. Run and Observe

With Gradle installed on the machine (or the corresponding Gradle Wrapper generated for the project):

~~~bash
gradle bootRun
~~~

Once the IdP and client are configured properly:

1. Open `http://localhost:8080/`: receive the public message.
2. Open `http://localhost:8080/me`: the application directs you into the OIDC flow; the IdP authenticates the user if no suitable session exists.
3. After a valid callback, `/me` returns JSON containing the real user's `issuer` and `subject`. Values depend on the IdP and account, so there is **no fixed stdout/JSON to copy**.
4. Register a second RP application at the same IdP, with its own client ID and redirect URI. Access the second RP in the same browser while the IdP session is still valid to observe SSO. **A single RP alone does not prove cross-application SSO.**

Without a valid client/issuer, the application may fail to start or fail to complete sign-in; that is an external integration condition, not proof that SSO is working.

## 7. Three Session Layers and Logout Lifecycle

Three states must be kept separate:

| State | Managed By | Effect |
| --- | --- | --- |
| **IdP session** | IdP in the browser / IdP system. | Allows the IdP to identify an already-authenticated user when another RP redirects there. |
| **RP/App A session** | App A / Spring Security and App A's session infrastructure. | Allows subsequent requests to App A to be recognized without returning to the IdP every time. |
| **RP/App B session** | App B. | Independent from App A; can only be created after App B processes an appropriate authentication result. |

**Local logout** from App A typically clears App A's session, but **does not automatically destroy the IdP session or App B's session**. Returning to App A while the IdP session persists can cause the user to sign back in immediately via SSO. **Single Logout (SLO)** is a separate capability depending on protocol, IdP/RP support, and deployment configuration (for example, RP-initiated logout with OIDC or SAML logout). Do not promise "logging out of one app logs out everywhere" unless it has been designed and tested.

If the business requires departing employees to lose access immediately, deleting the account at the IdP alone is insufficient to guarantee every RP session ends at once. You must consider RP session TTL, revocation policies, compatible back-channel/front-channel logout mechanisms, and internal permission disabling.

## 8. Security and Operational Checkpoints

1. **Issuer and audience:** Trust only configured issuers; verify audience/client ID and required claims. Never trust a token just because JWT decoding succeeds.
2. **Signatures and timestamps:** Use standard libraries to verify signatures, trusted keys/JWKS, `exp`, `nbf`, and reasonable clock skew; handle signing key rotation.
3. **State, nonce, PKCE, callback:** Follow the appropriate OIDC/OAuth2 profile; lock down the redirect URI allow-list, defend against CSRF/login CSRF and open redirects.
4. **TLS and cookies:** Use HTTPS in deployments, set appropriate Secure/HttpOnly/SameSite attributes on session cookies; understand browser policies affecting SSO flows.
5. **Authorization separate from authentication:** Do not automatically assign admin roles just because the IdP returns an email or arbitrary group; define permission sources, mapping rules, tenant boundaries, and privilege de-escalation.
6. **Account linking:** Prefer stable identifiers (`iss` + `sub` within RP context) and verification policies before linking existing accounts; prevent account takeover caused by naive email-only matching.
7. **Secret management:** Protect client secrets, refresh tokens, and session stores; apply least privilege to scopes; do not write tokens or sensitive PII to logs.
8. **MFA and re-authentication policies:** SSO reduces password re-entry but does not mean skipping MFA. For risky operations, enforce strong authentication or re-authentication per IdP policy.
9. **Availability and monitoring:** The IdP becomes a shared dependency; monitor discovery errors, JWKS failures, redirect mismatches, clock sync, and configuration changes.
10. **Scope of responsibility:** OIDC/SAML attests identity to the RP; resource access checks inside the application must still exist and be tested independently.

## 9. Hands-On Exercise and Acceptance Criteria

Set up **RP A** and **RP B** with separate client registrations at the same test IdP (each RP having its exact redirect URI). Follow this sequence:

| Test | Action | Expected Result to Verify |
| --- | --- | --- |
| Initial sign-in | Open RP A in a fresh/unauthenticated window. | Browser goes to IdP; after authentication, RP A has a valid session. |
| SSO | Keep the IdP session, open RP B. | IdP can pass through without re-entering password; RP B creates its own session. MFA may still be required by policy. |
| Session separation | Log out locally at RP A, keep IdP session. | RP A loses its session; RP B is not necessarily affected; revisiting A may re-authenticate quickly via IdP. |
| IdP logout | Clear/end the IdP session as supported by the IdP. | A *new* authentication must satisfy IdP policy; existing live RP sessions may still work until expiration/revocation. |
| Resource protection | Call a business API without permission despite being signed in. | RP denies access per authorization rules, not granting rights merely due to SSO. |
| Misconfiguration | Try a mismatched redirect URI or issuer. | Login flow is rejected; never "skip verification to make it work". |
| Identity attribute change | Change email/display name at IdP, keep subject stable. | User mapping is not mismatched to another person just because the email changed. |

When evaluating, distinguish **observable events** (whether another login prompt appeared, which sessions remain alive) from **root causes** (IdP policy, cookies, MFA, TTL, logout). Do not extrapolate from a single test on one browser to conclude that all users/browsers receive identical SSO behavior.

## 10. Common Misconceptions

**"SSO means apps share one password."** No. SSO is an authentication mechanism/experience through a shared trust anchor; applications should not receive or store the IdP password.

**"With federation, you will definitely never have to sign in again."** False. Federation establishes trust; the IdP can still require re-authentication due to session expiration, MFA, risk changes, or application requests.

**"An OAuth2 Access Token is standard user proof for login."** Incorrect. Access tokens grant permission to call resource servers; use OIDC and ID Tokens when standard OIDC identity authentication is needed.

**"App B can reuse App A's session cookie."** Normally no, and it should not be designed that way. Two applications create separate sessions; the IdP helps complete authentication with minimal user interaction.

**"Receiving an email from the IdP is enough to merge any accounts."** No. Email is not an immutable identifier key; linking rules based on issuer/subject and verification policies are required.

**"Logging out of one app logs out of all."** Not by default. Single Logout must be designed and tested per IdP/RP.

**"Configuring Spring Security oauth2Login means you already have an IdP system."** No. `oauth2Login` configures the application as an OIDC/OAuth2 client; the IdP is a separate system and must be registered/trusted.

## Key Knowledge Summary

- **SSO** is about reducing re-authentication prompts when accessing multiple applications.
- **Federation** is about parties accepting authentication results from a trusted identity source; federation is often the foundation for providing cross-boundary SSO.
- **OIDC/SAML** transfer identity evidence from the IdP to the RP/SP; **OAuth2** focuses on resource authorization.
- **The IdP session and each application's session are independent**; logout and permission revocation must be designed separately.
- **Spring Security oauth2Login** helps an RP participate in OIDC login, while the application remains responsible for account mapping, authorization, and session security.

### Official References

- [Spring Security – OAuth2 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html)
- [Spring Security – OAuth2 Login / OIDC](https://docs.spring.io/spring-security/reference/servlet/oauth2/)
- [Spring Security – SAML 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
