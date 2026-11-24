# Choosing Between LDAP, Certificates, Centralized SSO, or Container Integration

> **Context:** Java 17+ applications using **Spring Security on the Servlet stack**. When enterprise identity integration is needed, choosing LDAP, X.509 certificates, centralized sign-on (SSO), or Servlet container-managed authentication is not merely picking an API: each approach places trust boundaries, session lifecycles, authorization models, and operational responsibilities in a different place.

## 1. Start from Architectural Questions, Not from a Filter

Four concepts need to be separated clearly:

- **Identity store:** where users, groups, account status, and attributes are managed. LDAP/Active Directory often plays this role.
- **Authentication mechanism:** how identity evidence is verified, such as LDAP bind with a password, checking a client certificate already authenticated by TLS, or validating an Identity Provider (IdP) response.
- **Sign-on federation (federation / single sign-on):** the application trusts an IdP's authentication process so users do not have to enter passwords at every application. OIDC/SAML 2.0 are two common choices.
- **Authorization:** the application decides which principal is allowed to perform which action. LDAP groups, OIDC claims, SAML attributes, certificate details, or container roles are **inputs**; they do not replace the application's authorization policy.

For example, a company may still store employees in Active Directory while building SSO with an IdP that reads AD. The Servlet application then **does not need to bind to LDAP directly**; it can use OIDC to sign in and map identity/groups to `GrantedAuthority`. Therefore, LDAP and SSO are **not necessarily mutually exclusive choices**.

Before choosing, answer the following questions:

1. Are the users **browser-based employees**, **partners**, **devices**, **automated services**, or an application running on a pre-authenticated **application server**?
2. Is there an enterprise IdP supporting **OIDC** or **SAML 2.0**? Are MFA, passkeys, centralized session management, conditional access policies, or single logout required?
3. Must the application receive passwords directly, or can it redirect users to the IdP?
4. Where does permission data live, who updates it, how quickly must permissions be revoked, and is group synchronization from a directory needed?
5. Is TLS terminated at the application or at a reverse proxy/load balancer? Is the link from the proxy to the Servlet container trusted?
6. Is this a UI-rendering Servlet application, an API receiving bearer tokens, or service-to-service communication? Choose the right Spring Security mechanism for each type.
7. When the IdP, LDAP, or authentication system goes down, how must the application **fail closed**, how long may existing sessions persist, and who controls revocation?

Skipping these questions and simply turning on `formLogin()`, `x509()`, or `jee()` often leads to a configuration that appears to work while leaving trust boundaries unclear.

## 2. Comparison Table of the Four Integration Approaches

| Criterion | Direct LDAP / Active Directory | X.509 Certificate (client certificate) | SSO via IdP (OIDC / SAML 2.0) | Servlet container / pre-auth |
|---|---|---|---|---|
| Identity evidence | Usually username/password verified by LDAP bind | Client certificate + proof of private key possession in TLS handshake | Assertion/token issued by the IdP after sign-in | Principal already authenticated by the container/application server |
| Who handles sign-in? | Application receives credentials and interacts with the directory | TLS endpoint verifies certificate; application maps principal | IdP handles login and MFA; application validates the result | Managed by the container and realm/security domain |
| Best suited for | Internal apps needing LDAP/AD compatibility without an IdP yet; directory-based authentication tasks | Devices, mTLS environments, certain PKI/enterprise apps requiring certificate authentication | Enterprise browsers, multi-app suites, MFA, centralized login management | Legacy Java EE/Jakarta EE apps, container environments with an already managed realm |
| Operational dependencies | Directory, LDAP(S) connectivity, account/group schema | PKI/CA, cert issuance–renewal–revocation, TLS termination | IdP, metadata/discovery, signing keys, redirect URI, client registration | Container realm, role mapping, deployment, and application server trust zone |
| Application permissions | LDAP groups must be mapped to authorities | Certificate identifies the entity; permissions looked up from a registry/directory | Claims/attributes require verifying issuer, audience, and mapping permissions | Container roles must be mapped accurately to Spring authorities |
| Notable risks | App handles passwords, LDAP injection/misconfiguration, TLS, lockout, stale group membership | Trust chain, expired/revoked certs, wrong subject/SAN mapping, proxy spoofing | Token validation, account linking, redirect/state/nonce, session/logout, claim overtrust | Mistakenly trusting headers from clients, container bypass, mapping mismatch between app and server |
| Inherent SSO? | No | Not under a typical federation model | Yes, depending on IdP capabilities and policies | Possible within the same container/realm domain, not enterprise-wide federation by default |

**Quick selection rules:**

- **Web-using employees with a capable IdP:** prefer **OIDC** for new applications (SAML 2.0 when required by the enterprise ecosystem).
- **Directory is the source of truth without an SSO service yet:** direct LDAP bind over a protected connection can be used; consider placing an IdP in front of the directory when feasible.
- **Devices/clients using mTLS or requiring certificate verification:** use X.509 alongside a mechanism to map certs to accounts/permissions; do not treat every CA-issued cert as an administrator.
- **Apps already running in a server with trusted container-managed security:** consider `jee()` integration to reuse the existing principal/roles, but only when the container truly authenticates and the app cannot be reached via a bypass path.
- **APIs receiving access tokens:** typically use `oauth2ResourceServer()` to **validate bearer access tokens**, not `oauth2Login()` as a substitute for API security. That is a different usage branch, even when sharing the same IdP.

## 3. LDAP: Direct Authentication with a Directory

### 3.1. Mechanism and Roles

**LDAP (Lightweight Directory Access Protocol)** is a protocol for querying/updating a directory; LDAP itself is not a browser SSO protocol. In the familiar username/password model:

```text
Browser → Servlet application's form login
           ↓
Spring Security AuthenticationManager
           ↓
LDAP authenticator → LDAP directory
           ↓                     ↓
     user DN resolved      bind with credentials
           ↓
     authentication succeeds
           ↓
     fetch groups/attributes, map authorities
           ↓
     SecurityContext and application HTTP session
```

Two common approaches:

- **Bind authentication:** the application resolves the user's DN, then binds to the directory using the user's password to verify; this is the common choice with LDAP/AD.
- **Password comparison:** some directories/architectures allow comparing the password attribute through a dedicated flow, but you should not assume passwords can be read or hashed client-side. Choose based on the directory's actual capabilities and policies.

The application may need a **least-privilege service account** to search DNs/read groups. Do not use a directory administrator account for routine queries. DN patterns, OU structures, and group schemas differ between OpenLDAP and Active Directory; `uid`, `sAMAccountName`, `userPrincipalName`, and `memberOf` are not unconditionally interchangeable.

**Transport protection:** use `ldaps://` with validated TLS or properly configured LDAP StartTLS; do not transmit passwords over plaintext LDAP. Verify trust stores, hostnames, timeouts, referrals, and firewall policies. TLS encryption alone does not mean user authentication or application authorization is correct.

### 3.2. Illustrative Configuration with Spring Security 6

With Spring Security Servlet, the `spring-security-ldap` module provides components such as `LdapBindAuthenticationManagerFactory`. Below is a **component configuration sample** for a system with an existing directory; it cannot run standalone without a Spring Boot app, LDAP dependency, host/base DN, and matching directory structure:

```java
// Required imports:
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.BaseLdapPathContextSource;
import org.springframework.ldap.core.support.LdapContextSource;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.ldap.LdapBindAuthenticationManagerFactory;

@Configuration
class LdapAuthConfiguration {
    @Bean
    BaseLdapPathContextSource ldapContextSource() throws Exception {
        LdapContextSource source = new LdapContextSource();
        source.setUrl(System.getenv("LDAP_URL")); // ldaps://directory...
        source.setBase(System.getenv("LDAP_BASE_DN"));
        source.afterPropertiesSet();
        return source;
    }

    @Bean
    AuthenticationManager ldapAuthenticationManager(
            BaseLdapPathContextSource contextSource) {
        var factory = new LdapBindAuthenticationManagerFactory(contextSource);
        factory.setUserDnPatterns("uid={0},ou=people");
        return factory.createAuthenticationManager();
    }
}
```

Meaning:

- `LDAP_URL`/`LDAP_BASE_DN` come from secure environment configuration and must have valid values at runtime. `uid={0},ou=people` is only an **illustrative directory structure** and must be replaced with the organization's real DN/search model.
- When the directory does not allow deriving the user DN from the username, configure **user search** instead of a DN pattern; if the directory requires a service bind to look up users, configure credentials via a secret manager.
- `AuthenticationManager` is created for integration into the `HttpSecurity` of the corresponding login processing chain. Simply defining this bean does not prove every chain/form login uses the right manager; explicit wiring and tests are required.
- In practice, you must configure **groups → `GrantedAuthority`**, enforce least-privilege authorization, and handle locked/deleted users; never grant `ROLE_ADMIN` merely because an LDAP bind succeeded.

Key test points are that a user belonging to a valid application group receives the right permissions, a user removed from a group does not retain permissions too long after refresh/session re-auth, and an unreachable directory does not fall back to anonymous-but-authorized.

### 3.3. When to Choose or Avoid Direct LDAP?

Choose it when integrating with existing LDAP infrastructure, with few applications, in a well-controlled internal environment, or when SSO is unavailable. Avoid choosing it merely because "users live in AD" if the enterprise already provides OIDC/SAML: reading AD via LDAP does not automatically provide MFA, account federation, single logout workflows, or centralized sign-on policies.

When migrating from LDAP login to SSO, maintain a separate **internal user ID** and link accounts using a stable, verifiable identifier; do not merge accounts solely by email if emails can change or be recycled.

## 4. X.509: Identification via Client Certificates and mTLS

### 4.1. The TLS Termination Point Defines the Trust Boundary

X.509 certificate login typically relies on **mutual TLS (mTLS)**:

```text
Client with certificate + private key
                 |
          TLS handshake
                 |
TLS endpoint validates chain, validity period, purpose, revocation policy
                 |
Servlet container receives authenticated certificate / principal
                 |
Spring Security X.509 pre-auth receives verified identity
                 |
Map identity → application user/authorities
                 |
Enforce authorization on endpoint
```

Unlike form login, the application does not receive a password on every login; however, it must answer **which certificates are trusted**, **which issuers are accepted**, **how expired/revoked certificates are handled**, and **which account a certificate subject maps to**.

There are two common architectures:

1. **TLS terminated at the Servlet container:** the container validates the client certificate and passes authenticated details to upper layers. Spring Security can use `x509()` to map the principal.
2. **TLS terminated at a gateway/reverse proxy:** the gateway validates the certificate, then forwards the authenticated result to the upstream over a trusted channel. In that case Spring Security **must not blindly trust** any header such as `X-Client-Cert` set by the client. The gateway must strip/overwrite incoming client headers, authenticate internally to the backend, and clearly define how the application verifies forwarded/pre-auth information.

**Key point:** A header string containing a subject DN or PEM does not prove a certificate was authenticated. The trust decision resides at TLS termination or the trusted connection layer.

### 4.2. How Does Spring Security Servlet Support X.509?

A configuration snippet inside a `SecurityFilterChain` when mTLS infrastructure is already in place:

```java
// Configuration snippet inside HttpSecurity, not a standalone class.
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/secure/**").authenticated()
        .anyRequest().denyAll())
    .x509(x509 -> x509
        .subjectPrincipalRegex("CN=(.*?)(?:,|$)")
        .userDetailsService(userDetailsService));
```

Here `userDetailsService` must be provided by the application and map the identity authenticated from the certificate to an account with appropriate roles. The CN regex is a **simple example for learning how processing works**; new applications should prefer a clear, unique identifier aligned with PKI policy (often in Subject Alternative Name), avoiding blind reliance on CN which may collide or be misinterpreted.

Spring Security's `x509()` layer **does not replace trust chain validation at the TLS endpoint**. Do not treat a certificate valid under any CA in the trust store as sufficient for all permissions.

### 4.3. PKI Checklist When Choosing Certificates

- Is the issuing CA trusted and restricted to issuing certificates only to the intended group? Are CAs separated for users, machines, and services?
- Does the certificate have the appropriate EKU/key usage for **client authentication**? Are chain and hostname/service policies checked when needed?
- Is the private key stored in hardware/a secure keystore? Is there a procedure for lost devices, account lockouts, renewal, and certificate rotation?
- Is there a **revocation** process using CRL/OCSP or a clearly defined compensating policy? Check validation timing and behavior when revocation sources are unreachable.
- Does each certificate map to **a single unique identity**? If a user replaces their certificate, are their account and permissions preserved accurately?
- If a proxy terminates TLS, can clients call the upstream directly with a spoofed certificate header? Does the proxy strip/overwrite incoming headers and protect the backend channel?

Certificates are especially suited for **services/devices** and high-assurance environments, but deploying them to all user browsers can incur high provisioning, device support, and UX costs. Do not confuse **mTLS authenticating a client** with **OIDC/SAML user login sessions**: the two mechanisms can complement each other.

## 5. SSO: OIDC and SAML 2.0 for Enterprise Applications

### 5.1. What Problem Does SSO Solve?

In an SSO architecture, the Servlet application acts as a **Relying Party / client** and delegates the login screen to an **Identity Provider**. The IdP can integrate with AD/LDAP behind the scenes, enforce MFA, passkeys, device policies, and manage sign-in centrally.

With **OpenID Connect (OIDC)** over the OAuth 2.0 Authorization Code flow, the typical browser flow is:

```text
Browser → GET /me on the application
                 |
     No session on the application
                 |
Spring Security redirects → IdP /authorize (state, nonce, ...)
                 |
      User authenticates at the IdP
                 |
IdP redirects browser to registered URI with authorization code
                 |
Spring Security exchanges code, validates token/ID token
                 |
      Create Authentication and HTTP session in the application
                 |
       Browser accesses the permitted resource
```

OIDC authenticates identity based on the **ID token** and issuer metadata. An `access token` issued for an API is not itself an ID token and should not be used as proof of OIDC login outside the proper verification flow. **OAuth 2.0 alone is an authorization framework, not a complete authentication protocol**; OIDC adds the identity verification layer.

**SAML 2.0** is also common in established enterprise systems, especially when partners/IdPs only support SAML, exchanging SAML assertions, metadata, ACS URLs, and XML signatures. It has a different trust model from OIDC; never replace audience, recipient, time, signature, and replay checks with trusting an email field.

### 5.2. Runnable Example with Spring Boot 3.x + Real OIDC IdP

This example is a **complete application in Java code and dependency declarations**, buildable with Java 17/Gradle; successful sign-in requires a **real OIDC IdP** with a valid issuer URI, client registration, redirect URI, and secret. Without an IdP you cannot expect login to run; that is an infrastructure dependency, not a missing code snippet.

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

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
```

**`src/main/java/demo/identity/IdentityApplication.java`**

```java
package demo.identity;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class IdentityApplication {
    public static void main(String[] args) {
        SpringApplication.run(IdentityApplication.class, args);
    }

    @GetMapping("/")
    public String home() {
        return "Identity integration demo";
    }

    @GetMapping("/me")
    public Map<String, String> me(@AuthenticationPrincipal OidcUser user) {
        return Map.of(
            "subject", user.getIdToken().getSubject(),
            "issuer", user.getIdToken().getIssuer().toString()
        );
    }
}
```

**`src/main/java/demo/identity/SecurityConfig.java`**

```java
package demo.identity;

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
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
```

**`src/main/resources/application.yml`**

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile,email
        provider:
          corp:
            issuer-uri: ${OIDC_ISSUER_URI}
```

In the runtime environment, set `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, and `OIDC_ISSUER_URI` via an appropriate secret/configuration mechanism. `OIDC_ISSUER_URI` must be the IdP's issuer, typically with HTTPS and a discovery endpoint. At the IdP, register the client's redirect URI matching the application's actual URL; when running locally on port 8080, the sample URI is `http://localhost:8080/login/oauth2/code/corp` (local only; production requires HTTPS).

With a project using Gradle Wrapper:

```bash
./gradlew bootRun
```

Open `http://localhost:8080/` to see the public text. Accessing `http://localhost:8080/me` triggers an OIDC login redirect when no session exists. After a valid sign-in, the JSON response looks like:

```json
{
  "subject": "stable-id-issued-by-idp",
  "issuer": "https://idp.example.test"
}
```

Actual values depend on the IdP. In production applications, returning issuer/subject to the client as in this example is not always necessary; the example merely illustrates a **stable identifier for account linking**. Never log ID tokens, access tokens, refresh tokens, client secrets, or session cookies.

### 5.3. SSO Security Rules

- **OIDC:** use Spring Security's protocol library to validate signature, `iss`, `aud`, expiration, `state`/`nonce`, and flow constraints; do not parse JWTs manually and trust claims. Accept only configured issuers; manage signing key/JWKS rotation and fail-closed behavior when metadata is unsafe.
- **Authorization Code + PKCE:** choose the flow suited to the client type and IdP configuration; do not switch to implicit flow for "faster login."
- **Account linking:** identify users by the combination `issuer + subject` (OIDC) or a stable identifier guaranteed by the SAML contract. Emails/names can change; do not merge accounts based on matching emails without verification.
- **Groups/roles:** claims from the IdP must have clear semantics, provenance, and policy. Claims like `scope` or `email_verified` do not automatically equal `ROLE_ADMIN`. Use an allowlist for permission-mapping rules and reject elevated privileges when claims are missing/invalid.
- **SAML:** validate issuer, audience, signature, destination/recipient, time conditions, and `InResponseTo`/replay protection per the profile in use; keep metadata/certificate rotation current. Never construct an `Authentication` from decoded but unverified XML.
- **Sessions and logout:** `oauth2Login()` typically uses the Servlet application's session after the callback; logging out of the application session does not guarantee logout from all applications/the IdP. Plan session idle timeout, CSRF, `Secure`/`HttpOnly`/`SameSite` cookies, and RP-initiated logout/Single Logout if required.
- **APIs:** if an API only accepts access tokens, configure a **resource server** validating JWT or opaque tokens according to a separate contract. Do not assume an OIDC browser session exists on the API service.

## 6. Container-Managed Authentication and Pre-Authentication

### 6.1. When the Container Already Authenticates the User

An application server can manage realms, login, and user roles through deployment configuration (e.g., Java EE/Jakarta EE, realms integrated with LDAP/Kerberos, or platform security). The Servlet API then provides these concepts:

- `HttpServletRequest.getUserPrincipal()`: the principal provided by the **container**.
- `HttpServletRequest.isUserInRole("ADMIN")`: role information confirmed by the container under its model.
- Deployment security configuration: `web.xml`/security constraints, realm/role mapping, or application server specifics depending on the environment.

Spring Security supports **JEE pre-authentication** via configuration in `HttpSecurity`. Example of a chain snippet when a container principal and proper role mapping already exist:

```java
// Illustrative snippet inside HttpSecurity configuration; requires a real container realm.
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated())
    .jee(jee -> jee.mappableRoles("USER", "ADMIN"));
```

The snippet above is **not a complete Java application**; merely adding `jee()` does not make the container authenticate requests. The container must populate a trusted principal on `HttpServletRequest` and declare the proper roles. Mappable roles must be tested so Spring Security sees the expected authorities, including the difference between `ADMIN` and `ROLE_ADMIN` at the application layer.

### 6.2. Pre-Auth Trust Boundaries

Only use pre-auth when you are certain that:

1. The **upstream layer** actually performed authentication, and **there is no direct call path** to the backend bypassing the authentication layer.
2. Any forwarded identity headers, if used, are **stripped/overwritten** at a trusted proxy; external clients cannot self-assert `X-User` to gain privileges.
3. There is a clear identity/role mapping contract and account lifecycle. Non-existent, revoked, or roleless principals must be handled **fail closed**.
4. Error paths, async dispatches, multiple `SecurityFilterChain`s, and management URLs have no `permitAll` branch accidentally bypassing pre-auth.
5. Tests distinguish container roles from Spring Security authorities, avoiding an "authenticated" state where roles fail to map or default to administrative access.

If the application deploys on Spring Boot embedded Tomcat **without configuring a container realm**, container pre-auth is usually meaningless. In new applications, direct OIDC can be clearer to operate than relying on legacy server security.

## 7. Access Control: Common Ground Across All Four Approaches

**Successful authentication does not mean permitted operations.** Whether identity comes from LDAP, certificates, OIDC/SAML, or the container, the backend still needs resource- and business-based authorization checks.

Mapping design examples:

| Source | Trusted identity | Initial group/permission data | Application rule |
|---|---|---|---|
| LDAP | DN/entry ID of bind-authenticated user | Directory groups via controlled query | Only allowlisted groups become `ROLE_REPORT_READER` |
| X.509 | Cert principal/SAN verified by TLS | Typically no business permissions inside the cert | Look up internal account, check active status + roles |
| OIDC | Verified ID token `iss + sub` | Groups/entitlement claims if reliably issued by IdP | Mapper checks issuer, claim scope, and role policy |
| SAML 2.0 | Stable NameID/subject per IdP agreement | Signed attributes with valid audience/conditions | Mapper follows dedicated SAML contract |
| Container | Trusted principal and container roles | Realm/role mapping | Only allowed roles become authorities |

**Best practices:**

- Maintain a stable **internal user/account ID**, distinguishing source and namespace. Two `minh` usernames from two directories/issuers must not be treated as the same person without a verified link.
- Apply **least privilege** and deny by default, especially for administrative roles. Roles inside groups or tokens must be interpreted structurally: never infer them via `startsWith("admin")` or similar-looking group names.
- Define **permission revocation latency**. Claims in ID tokens or roles in sessions can lag behind the directory. For sensitive permissions, consider short sessions, re-auth, centralized policy lookups, or invalidation mechanisms.
- Record audit logs with `issuer/provider`, stable subject, request ID, authorization decision, and timestamp; never log passwords, raw bearer tokens, client certificate private keys, or secrets.
- In multi-source systems, avoid a single filter that "tries everything until something succeeds" without policy. Separate URL groups/chains by protocol with explicit ordering, especially between browser sessions and machine-to-machine APIs.

## 8. Choosing an Integration Approach by Scenario

### Scenario A — Employee Portal, Multiple Apps, MFA

**Prefer OIDC SSO** if the IdP supports the standard and the enterprise already uses it. The application gets `oauth2Login()`, controlled claim/permission mapping, session/CSRF handling, and refresh/logout planning. If the IdP only supports SAML 2.0 or policy mandates SAML, use `saml2Login()` with appropriate metadata/signature validation. The directory can remain the identity source behind the IdP without the backend receiving LDAP passwords directly.

### Scenario B — Single Internal App with LDAP/AD, No IdP Yet

You can use **LDAP bind** over TLS with explicit group mapping, paired with rate limiting, lockout policy, auditing, and session/CSRF protection. If multiple apps later require MFA and SSO, plan to move authentication to an IdP. Avoid building a DIY "SSO" by sharing passwords or cookies across apps.

### Scenario C — Devices/B2B Apps Communicating via mTLS

Use **X.509 client certificates** when the organization operates a PKI and certificate lifecycle. Choose a stable identity from SAN or a standardized identifier, map machine or organization accounts/permissions, and authorize per API. If the client also needs end-user permissions, transport-level mTLS does not itself tell you **who the end user is**; supplementary tokens/SSO may be needed.

### Scenario D — App Running in an Application Server with Mandatory Realm

Use **container pre-auth/`jee()`** if the container is an actively operated and tested security boundary. Every request must pass through container protection; role mapping and container failures must be handled; never trust client-supplied headers. When migrating to an embedded server or microservices, re-evaluate the architecture rather than copying `jee()` mechanically.

### Scenario E — SPA or Mobile Calling an API with Access Tokens

Do not use a web app's `oauth2Login()` as a universal decoder for bearer tokens. A Spring Security API can use:

```java
// Configuration snippet for a Spring Security Servlet API.
// Valid only with appropriate resource-server and issuer/audience configuration.
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/**").authenticated()
        .anyRequest().denyAll())
    .oauth2ResourceServer(oauth2 ->
        oauth2.jwt(org.springframework.security.config.Customizer.withDefaults()));
```

This is a **resource server**: its purpose is validating access tokens sent to the API. It requires the `spring-boot-starter-oauth2-resource-server` dependency plus issuer/JWK source configuration and audience validation per the security contract. It is **not** a direct login mechanism among the four options, though it is frequently confused when integrating with a shared IdP.

## 9. Can Multiple Identity Sources Be Combined?

Yes, but combining them requires **clear structural boundaries**, not merely enabling multiple filters on a single chain and hoping they work.

For example, a Servlet application might have:

- `/portal/**`: web session + OIDC SSO for employees.
- `/api/**`: resource server accepting bearer tokens issued by the right issuer with the API's audience.
- `/device/**`: mTLS for registered devices, authorizing by certificate identity.
- `/legacy/**`: container pre-auth handling in a specialized application environment.

You can design multiple `SecurityFilterChain` beans with explicit `securityMatcher(...)` and `@Order`, but you must verify which chain matches each URL, ensure fallback does not accidentally `permitAll`, and confirm there are no bypasses via prefixes/forwards/rewrites. Do not accept an mTLS certificate for an employee account merely because the subject CN matches an email, nor grant admin privileges to an OIDC user based on an unverified claim.

An application can also use LDAP as a **group data source** after OIDC sign-in. In that case directory lookups must use least-privilege read access, appropriately TTL-bounded caching, and explicit handling when the directory is failing while token claims remain valid.

## 10. Testing, Failure Modes, and Acceptance Questions

### 10.1. Testing Matrix by Mechanism

| Approach | Normal authentication case | Failure cases to handle safely | Authorization case |
|---|---|---|---|
| LDAP | Valid user password binds successfully over TLS | Wrong password, disabled account, missing DN, directory timeout, invalid TLS cert | User outside admin group has no admin access; revoked group does not keep access past expiry |
| X.509 | Valid certificate from trusted CA, accurate mapping | Expired/revoked/untrusted cert, missing cert, unmapped SAN, spoofed gateway header | Valid certificate on an unprivileged account must receive 403 |
| OIDC | Valid auth code, accurate ID token issuer/audience, session created | Wrong `state`/`nonce`, invalid redirect URI, expired token, unknown issuer, bad signature/JWKS, IdP offline | Missing group claim or disabled user receives no elevated privileges |
| SAML 2.0 | Signed assertion with valid audience, recipient, and time conditions | Invalid signature, replay, invalid time window, untrusted issuer, failed metadata rotation | Do not trust role attributes from an unverified assertion |
| Container | Container authenticates principal + roles accurately | Missing principal, realm error, direct-to-backend bypass, spoofed header | Unmapped container role or missing required role → deny |

**Do not conclude safety merely because a request returns 200/302/403.** You must verify the actual principal, which provider handled it, `Authentication`/`GrantedAuthority`, and which resource executed. For example, OIDC may return 302 to the IdP when unauthenticated — that is normal login flow, not the application "returning protected data."

### 10.2. Testing Sessions and Account Lifecycle

1. Create test users with low and high privileges; check responses/authorities before and after changing groups/roles.
2. Revoke permissions at the source and observe **how long until the session/token loses effect**; compare against security requirements.
3. For LDAP, induce directory/TLS/timeout failures on staging; the app must never fall back to granting privileges.
4. For OIDC/SAML, test cert/signing-key rotation, clock skew, logout, session fixation, CSRF, cookies, and login redirect loops.
5. For mTLS, test expired certificates, trust-store rotation, identity mapping, proxy bypass, and revocation policy.
6. For containers, test security constraints across **all URLs/dispatches**, role mapping, and direct access to any embedded container if present.
7. In audit logs, store only information needed for investigation (issuer + subject/account ID, source, request ID, outcome); never store credentials/tokens/secrets.

### 10.3. Knowledge Check Questions

**Q:** "Our company already has Active Directory, so are we forced to choose LDAP login?"

**A:** No. AD can serve as the identity store for an IdP; the application can choose OIDC/SAML SSO to gain MFA and centralized policies. Choose based on users, UX, security, and operations.

**Q:** "Does every certificate signed by the internal CA have admin rights?"

**A:** No. TLS authenticates the certificate, whereas permissions must be mapped from identity to account/roles under a separate policy.

**Q:** "If a client sends `X-User: alice` through a gateway, can Spring Security treat them as logged in?"

**A:** No, unless a complete pre-auth mechanism operates through a trusted proxy, the proxy strips/overwrites client headers, the backend is protected, and mapping is verified. Self-declared client headers are not proof of authentication.

**Q:** "Once `oauth2Login()` is enabled, are APIs receiving bearer tokens automatically secured too?"

**A:** No. `oauth2Login()` manages browser sign-in and sessions; an API resource server needs to validate access tokens, issuer/audience, and appropriate scopes/authorities.

## 11. Pre-Implementation Decision Checklist

- [ ] Identify the client type accurately: human browser, machine/device, service-to-service, or container-managed.
- [ ] Map trust boundaries across the proxy, TLS termination, IdP, directory, container, and Spring Security.
- [ ] Select the right identity store and authentication protocol; do not confuse an LDAP directory with SSO.
- [ ] Define a stable identity key, account linking workflow, and role/authority mapping.
- [ ] Establish provisioning, rotation, and revocation policies for secrets/certificates/signing keys and accounts.
- [ ] Define fallback/timeout/HA/fail-closed behavior when the identity source is unavailable.
- [ ] Test unprivileged users, disabled accounts, and revoked groups/roles.
- [ ] Test sessions, logout, cookies/CSRF, revocation, and token lifetime limits.
- [ ] Verify the reverse proxy cannot pass spoofed principals/headers to the backend.
- [ ] Maintain minimal audit logging without exposing passwords/tokens/private keys.
- [ ] With multiple chains, document and test which URL uses which provider; default fallback is deny by default.

**Conclusion:** **LDAP** fits when the application needs to verify credentials against a directory; **X.509/mTLS** fits when identity is bound to certificates and PKI infrastructure; **OIDC/SAML SSO** fits when an enterprise IdP manages sign-in, MFA, and federation; **container pre-auth** fits when the application server is a trusted authentication boundary. Whichever option you choose, Spring Security Servlet must still map identities to accurate authorities, protect trust boundaries, and enforce authorization per resource.