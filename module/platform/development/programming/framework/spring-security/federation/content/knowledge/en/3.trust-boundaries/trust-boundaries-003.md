# Distinguishing Partner-Asserted Identity from Application-Decided Permissions

> Module: **Spring Security – federation** · Parent topic: **Trust Boundaries**. This lesson focuses on the boundary between **identity credentials received from a partner** and **access authorization decisions made by the application**.

## Learning Objectives

After this lesson, you will be able to:

1. Explain why **a partner successfully authenticating a user** does not mean that user is permitted to use every function of the application.
2. Distinguish **identity claim**, **principal**, **external group/role**, **local account**, **permission**, and **authorization decision**.
3. Identify which point in an OIDC/SAML flow is **verifying credentials from a partner**, which point is **identity mapping**, and which point is **enforcing internal permission policy**.
4. Design identity mapping keyed by a stable issuer and subject, decoupled from email/display name; deny by default when no valid link or permission exists.
5. Implement a Spring Security example (Servlet, OIDC Login) where the IdP authenticates the user while the application grants business permissions itself.
6. Recognize privilege escalation risks caused by mistakenly trusting claims, confusing tenants, merging accounts by email, stale permission caches, or missing per-resource permission checks.

## 1. Scenario: Partner Authenticates, Application Decides Permissions

Company A operates the **Partner Orders Portal** for multiple suppliers. An employee of Supplier B signs in using an account at Supplier B's **Identity Provider (IdP)**. The IdP issues identity information via OIDC, for example:

~~~json
{
  "iss": "https://idp.partner-b.example/realms/business",
  "sub": "user-5f2c",
  "email": "buyer@partner-b.example",
  "email_verified": true,
  "groups": ["partner-admin"]
}
~~~

The claims above are **example data** inside an ID Token/UserInfo already processed per protocol; arbitrary JSON sent by the browser cannot be trusted. Assuming the RP has validly verified the token and issuer, the application can conclude: **this trusted IdP asserts that subject `user-5f2c` is the person who just authenticated**.

The application **cannot** conclude from this alone that:

- That subject belongs to the right **Supplier B account** in the internal database.
- The subject can view **Supplier C's orders**.
- The string `partner-admin` means the application's `APP_ADMIN` permission.
- The user can **approve payments**, **change prices**, or **view private data**.
- Permissions remain valid right now when the internal account has been locked.

**Core rule: The IdP has the authority to assert identity within the scope of the trust relationship; the application has the authority to decide access permissions for the resources it owns.** A partner may supply signals for authorization if there is an explicit agreement, but the application must interpret and control those signals under its own policy.

## 2. The Path from Identity Assertion to Authorization Decision

~~~text
[Browser / User]
         |
         | Redirect to sign in via OIDC or SAML
         v
[Partner's IdP]
         |
         | ID Token / SAML assertion: "I authenticated this subject"
         v
+-----------------------------------------------------------+
| APPLICATION TRUST BOUNDARY (RP / SP)                      |
|                                                           |
| [1] Check signature, issuer, audience, expiry, flow       |
|                   |                                       |
| [2] Obtain external identity = issuer + subject           |
|                   |                                       |
| [3] Link to local account / tenant; check active status   |
|                   |                                       |
| [4] Load application-approved entitlements/permissions    |
|                   |                                       |
| [5] Check action + resource + tenant + context            |
|                   |                                       |
|           ALLOW or DENY                                   |
+-----------------------------------------------------------+
~~~

Separate these **five steps** to know where to place each check:

1. **Protocol verification:** Only accept valid credentials from an allowed IdP. An unverified claim is simply untrusted data.
2. **External identity recognition:** Extract a stable identifier within the IdP's context, typically the `iss` and `sub` pair for OIDC.
3. **Identity linking to an internal account:** Look up the user/partner/tenant registered by the application; it can deny even if the IdP authenticated successfully.
4. **Establishing internal permissions:** Load account status, roles, and permissions from an application-managed source or an approved permission-delegation contract.
5. **Per-request/per-resource decision:** Check whether the user has permission to perform this action on **this exact object** at this moment.

Key milestone: **authentication** verifies who is accessing, whereas **authorization** decides what that person is allowed to do. Federation lets an RP/SP rely on an IdP for authentication, but does not replace the RP/SP's business rules.

## 3. Types of Data: What Is Asserted vs. What Is Granted?

| Data / Concept | Primary Creator or Controller | What Can Be Concluded? | What Cannot Be Automatically Inferred? |
| --- | --- | --- | --- |
| OIDC `iss` + `sub` | IdP, after RP verifies ID Token | Identity of a subject at a specific issuer | Permission to read, edit, or delete data |
| Email, name, avatar | IdP / profile system | Attributes of the subject, depending on source/trustworthiness | Immutable link key, admin rights |
| `email_verified` | IdP per email verification policy | IdP asserts the address was verified under its mechanism | Internal account permitted to use all features |
| External `groups`, `roles` | IdP/partner or their directory | Group/role membership **in the partner's semantics** | Equivalent to internal `ROLE_ADMIN` |
| `acr` / `amr` / auth time | IdP | Reported authentication context/method, if RP processes it properly | Business permissions; higher default privilege |
| OAuth2 access token `scope` | Authorization Server per token context | Delegation scope of client/token for resource server | Permission for every user action in the RP |
| Local account, local partner ID | Managed by application | Account/business unit linked to the external identity | Every resource is accessible |
| `APP_ORDER_READ`, `APP_APPROVE_PAYMENT` | Application policy | Application-recognized permissions if account and conditions are valid | Skipping tenant and ownership checks |
| `ALLOW` / `DENY` decision | Application authorization layer | Whether an action on a specific resource is permitted | A permanent system-wide permission |

A **signed, valid claim** proves that *the issuer made that assertion*; a signature does not give **every claim payload the authority of application policy**. For instance, a partner may name an internal group `admin`, yet the application does not grant `APP_SUPER_ADMIN` because of it.

### Name Permissions After the Application

Instead of using an external group `partner-admin` directly as `ROLE_ADMIN`, define narrowly scoped internal permissions: `APP_ORDER_READ`, `APP_ORDER_CREATE`, `APP_ORDER_APPROVE`, `APP_PARTNER_USER_MANAGE`. Then the application decides which users/units receive which permissions.

That way, a partner renaming groups or reorganizing teams will not accidentally alter the meaning of a sensitive permission in the application.

## 4. Trust Boundaries in OIDC and SAML

### 4.1. OIDC: ID Token Is Proof of Authentication, Not a Blank Check

In the **OIDC Authorization Code Flow**, the RP redirects the browser to the IdP, receives an authorization code at the callback, exchanges the code via the back-channel, and then verifies the ID Token. Checks depend on the profile and client type, including:

- **Issuer `iss`:** Matches the configured IdP exactly; never accept an arbitrary user-chosen issuer while bypassing trust registration.
- **Audience `aud`:** Token was issued for the right client/RP; handle `azp` when required by the profile.
- **Signature and keys:** Verify using trusted keys of the issuer, not merely decoding the three parts of the JWT.
- **Expiration and validity:** Check `exp`, time constraints, nonce, and state/authorization request binding where applicable.
- **Return path:** Enforce exact redirect URI matching, use HTTPS outside local development, and apply OAuth2/OIDC flow protections.
- **Claim source:** UserInfo/additional claims must be properly bound to the authenticated subject; never trust client-sent headers or JSON in place of a verified token.

Only then read `sub`, look up the account, and evaluate permission policy. **ID Tokens are for the RP to authenticate the user; access tokens are for the resource server/API.** Never use an ID Token as a bearer API token, and never treat every `scope` as a business role.

### 4.2. SAML 2.0: Assertion Is Verified, Permissions Are Still Decided by the SP

With SAML, the Service Provider verifies the trusted issuer, signature, audience, recipient/destination, assertion validity window, AuthnRequest correlation (`InResponseTo` when applicable), subject confirmation conditions, and receipt at the ACS. When valid, the SP knows the IdP asserted a NameID/subject and attributes. **A SAML attribute named `Role=Manager` also does not automatically become `APP_APPROVE_PAYMENT`** unless the SP has a matching mapping policy.

OIDC and SAML differ in format and verification rules, but share the same boundary: **an assertion received from a partner ≠ internal permissions**.

### 4.3. Can External Groups Ever Be Used for Authorization?

**Yes**, if the application and partner have an explicit **delegated-authorization contract**: specific issuer/tenant, claim namespace, list of allowed groups, membership governance, review workflow, maximum permission ceiling, audit, change synchronization, and revocation mechanism. The application must still translate through a mapping table it controls, for example:

| Trusted Issuer | Agreed External Group | Maximum Local Permission | Additional Conditions |
| --- | --- | --- | --- |
| `partner-b` | `buyers-read-only` | `APP_ORDER_READ` | Account active, belongs to Partner B |
| `partner-b` | `buyers-create` | `APP_ORDER_CREATE` | Account active, belongs to Partner B |
| `partner-b` | `partner-admin` | Do not grant internal permissions by default | Separate approval and mapping if truly needed |
| Other issuer | Any | Never auto-grant | No trust contract |

External groups are only **one input** into a controlled decision. Every exception must be justifiable under an auditable policy.

## 5. Safely Linking Identities to Internal Accounts

### 5.1. Linking Key

A common design with OIDC:

~~~text
external_identity
--------------------------------------------------------------
issuer                                    subject      local_id
https://idp.partner-b.example/realms/biz   user-5f2c    user_104
https://idp.partner-c.example/realms/biz   user-5f2c    user_999
~~~

Even if two issuers use the same `sub`, they can be **two completely different people**. Therefore, never look up by subject alone. Conversely, never use email as the unique key because emails can change, be recycled, or be misconfigured. OIDC may issue **pairwise subjects**, where one person has a different `sub` across different RPs; never use `sub` to guess that two users are the same person across multiple applications.

Illustrative schema:

~~~text
external_identity(issuer, subject, local_user_id)
local_user(id, status, partner_id)
local_permission(local_user_id, permission)
partner_order(id, owner_partner_id, status)
~~~

Place a unique constraint on the `(issuer, subject)` pair, verify the account is active, and load the internal partner ID from the approved link. For multi-tenancy, represent tenant/trust policy consistently in the data layer and in every query; never infer tenant from a browser-supplied parameter.

### 5.2. Initial Account Provisioning (JIT Provisioning)

If the application supports Just-in-Time provisioning, **creating a local account does not mean automatically granting permissions**. A safe path could be:

1. Verify the OIDC/SAML assertion.
2. If the issuer/subject pair is not yet in the link table, create the account in `PENDING` status or reject it and require an approval workflow.
3. Only assign `partner_id` when backed by trusted evidence/contracts; never trust a `?partnerId=...` query string.
4. After HR/admin workflow approval, grant minimal permissions.
5. Every permission check verifies account status and resource scope.

This ensures **successfully authenticating with a new IdP** does not turn into a mechanism for any partner employee to self-join the application with elevated privileges.

### 5.3. Revoking and Changing Permissions

Employees leave a partner, change departments, or get their accounts locked: the IdP may update groups, but the application must ensure **internal permissions are revoked promptly**. This can use provisioning sync (such as SCIM where appropriate), revocation events, per-request database status checks, short TTLs, and session termination strategies. If `GrantedAuthority` is only assigned **once at login**, long-lived sessions can retain stale permissions; for sensitive actions, check up-to-date permissions at execution time or have a reliable invalidation mechanism.

## 6. Business Permission Check Formula

For the "view order" action, the permission decision should rely on all necessary conditions:

~~~text
ALLOW_VIEW_ORDER(user, order)
    = authenticated_and_verified(user)
      AND linked_local_account_exists(user.issuer, user.subject)
      AND local_account.status == ACTIVE
      AND local_account.permissions contains APP_ORDER_READ
      AND local_account.partner_id == order.owner_partner_id
      AND any_resource_specific_policy_is_satisfied
~~~

Being **authenticated** and **having the permission** are necessary but not sufficient when data belongs to multiple partners. Someone from Partner B may hold `APP_ORDER_READ`, yet only to view Partner B's orders. When querying data, constrain at the service/repository layer—for example, `WHERE order_id = :id AND owner_partner_id = :partnerIdFromLocalAccount`. Do not accept a partner ID from the request to decide scope, and do not merely hide buttons in the UI.

### Outcome Matrix

| Identity from IdP | Local Link | Local Permission | Order Belongs To | Decision |
| --- | --- | --- | --- | --- |
| Valid | Active account, Partner B | `APP_ORDER_READ` | Partner B | **ALLOW** |
| Valid | Active account, Partner B | `APP_ORDER_READ` | Partner C | **DENY** |
| Valid | Active account, Partner B | No `APP_ORDER_READ` | Partner B | **DENY** |
| Valid, claim `groups=["admin"]` | Active account, Partner B | No `APP_ORDER_READ` | Partner B | **DENY** |
| Valid | Unlinked / local disabled | Any external claim | Any | **DENY** |
| Invalid issuer/signature/audience | Untrusted | Any | Any | **REJECT AUTHENTICATION** |

In HTTP terms, "no authenticated session" usually leads to a login redirect in an OIDC web app; "signed in but lacking permission" usually results in **403 Forbidden**. The exact response depends on the entry point and client/API requirements.

## 7. Java 17 + Spring Security Example: Authenticating via OIDC, Sourcing Permissions from the Application

The example below is a **Servlet web application** using Spring Boot 3.3.x / Spring Security 6.x, running on Java 17 or later. The application acts as an **OIDC Relying Party**. The IdP authenticates the user; the application explicitly maps the identity into `GrantedAuthority` instances with the `APP_` namespace. The goal is to illustrate the permission boundary, not to build a custom IdP.

**To run a real integration**, you need an IdP with OIDC discovery, client ID, client secret, a valid redirect URI, and the subject of a permitted account in the test environment.

### 7.1. Project Structure

~~~text
federated-access-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/federatedaccess/
    │   ├── FederatedAccessApplication.java
    │   ├── LocalAccessService.java
    │   ├── SecurityConfig.java
    │   └── PartnerController.java
    └── resources/application.yml
~~~

`settings.gradle`

~~~groovy
rootProject.name = 'federated-access-demo'
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

### 7.2. Main

`src/main/java/com/example/federatedaccess/FederatedAccessApplication.java`

~~~java
package com.example.federatedaccess;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FederatedAccessApplication {

    public static void main(String[] args) {
        SpringApplication.run(FederatedAccessApplication.class, args);
    }
}
~~~

### 7.3. LocalAccessService: Application-Controlled Permission Source

`src/main/java/com/example/federatedaccess/LocalAccessService.java`

~~~java
package com.example.federatedaccess;

import java.util.Set;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class LocalAccessService {

    private final String trustedIssuer;
    private final String approvedSubject;

    public LocalAccessService(
            @Value("${spring.security.oauth2.client.provider.partner-idp.issuer-uri}")
            String trustedIssuer,
            @Value("${demo.approved-subject}") String approvedSubject) {
        this.trustedIssuer = trustedIssuer;
        this.approvedSubject = approvedSubject;
    }

    public Set<String> permissionsFor(String issuer, String subject) {
        // Simulates an internally approved (issuer, subject) link.
        if (trustedIssuer.equals(issuer) && approvedSubject.equals(subject)) {
            return Set.of("APP_ORDER_READ");
        }
        return Set.of(); // No valid link => no permissions.
    }
}
~~~

This is an **allow-list simulating internal data** so the lesson is self-contained, *not a permission storage mechanism for production*. In a real system, `LocalAccessService` queries a local database by issuer/subject pair, checking `ACTIVE`, tenant, partner ID, entitlements, and approval status. Partners cannot supply `APP_ORDER_READ` themselves to be granted permission.

### 7.4. SecurityConfig: Assigning Authorities from the Internal Source

`src/main/java/com/example/federatedaccess/SecurityConfig.java`

~~~java
package com.example.federatedaccess;

import java.util.HashSet;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            OAuth2UserService<OidcUserRequest, OidcUser> localOidcUserService)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers("/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/partner/orders")
                    .hasAuthority("APP_ORDER_READ")
                .anyRequest().denyAll()
            )
            .oauth2Login(oauth2 -> oauth2
                .userInfoEndpoint(userInfo -> userInfo
                    .oidcUserService(localOidcUserService)
                )
            )
            .build();
    }

    @Bean
    OAuth2UserService<OidcUserRequest, OidcUser> localOidcUserService(
            LocalAccessService accessService) {

        OidcUserService delegate = new OidcUserService();

        return userRequest -> {
            // Spring Security performs OIDC processing/verification before this step.
            OidcUser federatedUser = delegate.loadUser(userRequest);
            String issuer = federatedUser.getIdToken().getIssuer().toString();
            String subject = federatedUser.getSubject();

            // Only create authorities of THIS application from the internal source.
            Set<GrantedAuthority> localAuthorities = new HashSet<>();
            localAuthorities.add(new SimpleGrantedAuthority("APP_AUTHENTICATED"));
            for (String permission : accessService.permissionsFor(issuer, subject)) {
                localAuthorities.add(new SimpleGrantedAuthority(permission));
            }

            // Do not pass external groups/roles or SCOPE_ straight through
            // as business permissions of the application.
            return new DefaultOidcUser(
                localAuthorities,
                federatedUser.getIdToken(),
                federatedUser.getUserInfo()
            );
        };
    }
}
~~~

Step-by-step explanation:

1. The default `OidcUserService` receives the OIDC result and constructs the principal after Spring Security components process the login flow. You should not manually parse JWTs or declare an `X-User` header as authentication proof in its place.
2. `federatedUser.getIdToken().getIssuer()` and `getSubject()` are the **verified external identity in the flow**; we use them as the local lookup key.
3. `LocalAccessService.permissionsFor(...)` is where **the application decides entitlements**, rather than taking `groups` in the token as application permissions.
4. `APP_AUTHENTICATED` is merely a baseline authority representing a valid principal; **it must never be used to protect business data**. Even when there are no permissions, the authority set remains non-empty.
5. `DefaultOidcUser` is rebuilt with application authorities. A user not granted `APP_ORDER_READ` will **not** pass the `hasAuthority("APP_ORDER_READ")` rule.
6. `anyRequest().denyAll()` prevents undeclared endpoints from being accidentally exposed. Filters for OIDC login/callback handle the login routes.
7. This is **login-time mapping**; in production, you must address permissions being revoked while a session is active.

**Note on `APP_AUTHENTICATED`:** this is an illustrative name with no special default meaning in Spring Security. Being signed in is represented by `Authentication`; the baseline authority simply avoids creating an empty authority set. Business permissions are only specific, meaningful authorities such as `APP_ORDER_READ`.

### 7.5. Controller: Observing Identity and Blocking Features by Permission

`src/main/java/com/example/federatedaccess/PartnerController.java`

~~~java
package com.example.federatedaccess;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PartnerController {

    @GetMapping("/")
    public String home() {
        return "Open /me, then try /partner/orders";
    }

    @GetMapping("/me")
    public Map<String, Object> me(
            @AuthenticationPrincipal OidcUser user,
            Authentication authentication) {

        List<String> authorities = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return Map.of(
            "issuer", user.getIdToken().getIssuer().toString(),
            "subject", user.getSubject(),
            "localAuthorities", authorities
        );
    }

    @GetMapping("/partner/orders")
    public List<String> orders() {
        // Simulated data, DOES NOT contain real orders.
        return List.of("demo-order-001", "demo-order-002");
    }
}
~~~

- `/me` is solely for debugging/learning and lets any **authenticated** user observe which authorities they currently have. In real deployments, remove debug endpoints or restrict data.
- `/partner/orders` returns sample data only when `SecurityFilterChain` sees `APP_ORDER_READ`. Someone who signs in successfully without internal approval will see the baseline authority and **be denied** when calling the orders path.
- In real business logic, never return all orders just because `APP_ORDER_READ` is present: the service/repository must check **which partner the order belongs to** before returning data. The controller example here uses two mock strings to focus on the identity/permission boundary.

### 7.6. OIDC Configuration

`src/main/resources/application.yml`

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          partner:
            provider: partner-idp
            client-id: ${PARTNER_OIDC_CLIENT_ID}
            client-secret: ${PARTNER_OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          partner-idp:
            issuer-uri: ${PARTNER_OIDC_ISSUER_URI}

demo:
  approved-subject: ${PARTNER_ALLOWED_SUB}
~~~

The configuration above uses **environment variables**. Register a confidential OIDC web client with the IdP, local redirect URI:

~~~text
http://localhost:8080/login/oauth2/code/partner
~~~

The default login initiation endpoint is `/oauth2/authorization/partner`. Use the real issuer URL, HTTPS, and client credentials per IdP configuration; never commit the client secret. `PARTNER_ALLOWED_SUB` must be the stable subject **of an internally approved person**, not an email or display name.

You can run with Gradle installed on your machine or a project with a suitable Gradle Wrapper:

~~~bash
gradle bootRun
~~~

The application runs/signs in successfully only when environment variables are set properly and the IdP is reachable. This is an **IdP-dependent integration**, so there is no fixed JSON output or subject across all environments.

### 7.7. Observations to Prove the Boundary

1. Configure `PARTNER_ALLOWED_SUB` to match the subject of an internally approved test account. Sign in at `/me`: you see `APP_AUTHENTICATED` and `APP_ORDER_READ`.
2. Open `/partner/orders`: receive the *mock* order list.
3. Sign in with a different subject from the same IdP. `/me` still shows a **valid issuer and subject** along with baseline authority `APP_AUTHENTICATED`, but **without `APP_ORDER_READ`**.
4. Open `/partner/orders` again: get **403 Forbidden** (authenticated, but lacking permission).
5. If issuer, audience, or callback configuration is invalid, the OIDC flow does not complete authentication; that is an **authentication/trust validation** failure, distinct from a 403 caused by missing local permissions.
6. If the partner assigns `groups=["partner-admin"]` to an unapproved person, application permissions **still do not increase** because the example does not use that claim to assign permissions.

From this test emerges a concrete verification criterion: **two users both authenticated by the same IdP can receive different access decisions because their local permissions differ**.

## 8. Checking Permissions on the Resource, Not Only on the URL

The `hasAuthority("APP_ORDER_READ")` filter in the example only answers "does the user have the general permission to read orders?". When the endpoint is `GET /partner/orders/{orderId}`, the decision also needs an **ownership or tenant boundary**:

~~~java
// Illustrates logic at the service layer; not a standalone runnable class.
boolean canReadOrder(LocalAccount account, PartnerOrder order) {
    return account.active()
        && account.permissions().contains("APP_ORDER_READ")
        && account.partnerId().equals(order.ownerPartnerId());
}
~~~

One Spring Security approach is enabling `@EnableMethodSecurity` and using `@PreAuthorize` for authority conditions at the service layer, while checking partner/ownership inside the same service/repository. Do not rely on `@PreAuthorize("isAuthenticated()")` alone for multi-tenant data, and never accept `partnerId` from the request as a source of authority. Even if the UI hides the "View order" button, the API must still reject unauthorized access.

If business requirements demand immediate revocation effect, loading permissions solely in `OidcUserService` at login is insufficient. Add live permission checks at the service layer, session invalidation, or bounded refresh mechanisms; weigh latency, database load, and consistency.

## 9. Common Implementation Mistakes and How to Fix Them

| Mistake | Why It Is Dangerous | How to Fix |
| --- | --- | --- |
| Decoding a JWT and immediately trusting `role=admin` | Decoding does not verify signature/issuer/audience; claims may lack authority to grant internal permissions | Use standard OIDC/SAML verification libraries; controlled local permission mapping |
| Treating `email` as a unique identifier key | Emails change or get recycled; account takeover risk from wrong linking | Key by `(issuer, subject)` with an explicit account linking workflow |
| Looking up by `sub` without issuer | Two IdPs can issue the same subject | Bind issuer and trust contract/tenant into the link |
| Mapping every `groups=admin` to `ROLE_ADMIN` | Partner "admin" may only administer their own tenant | Namespace and use an approved allow-list mapping; least privilege |
| Using `SCOPE_openid` / `SCOPE_email` as business permissions | OAuth/OIDC scopes are not equivalent to order-reading permissions | Use application permissions like `APP_ORDER_READ`, checked separately |
| Granting permissions by default to unlinked users | Any partner employee with an IdP account can gain access | Deny/JIT pending, require approval |
| Checking only `authenticated()` | Successful login gets mistaken for "full access" | Check permissions and resource ownership |
| Checking only client-supplied `partnerId` | Changing a request parameter exposes another tenant's data | Read partner ID from the local account, constrain data queries |
| Minting authorities at login and keeping them forever | Revoked users keep using old sessions | Re-check status/permissions or invalidate sessions |
| Hiding features only on the frontend | API can still be called directly | Enforce authorization on the backend |
| Merging permissions from multiple IdPs without separating issuers | Mixes semantics and organizational boundaries | Separate trust policies per issuer/tenant |
| Automatically "fixing" issuer or signature errors by disabling validation | Turns a config error into an authentication vulnerability | Fix IdP/client/redirect/JWKS; never disable verification |

### Do Not Equate "Trusted Partner" with "Every Claim from the Partner Has Maximum Authority"

Trust should be described by **scope**: who may issue credentials, which credential type, for which RP, which subjects may link, which claims may serve as authorization inputs, and what permission ceiling is allowed. Trusting an IdP for authentication **is not** automatically a contract allowing that IdP to grant every permission in every application.

## 10. Verification Lab (Learner QA)

With a test IdP and two valid accounts, run the Section 7 demo. Prepare subject A on the local allow-list and subject B without local permissions. Record results per the table below:

| Test | Setup | Expected Outcome |
| --- | --- | --- |
| T1 – Valid identity, local permission present | Log in as A; set `PARTNER_ALLOWED_SUB=A` | `/me` has `APP_ORDER_READ`, `/partner/orders` succeeds |
| T2 – Valid identity, no local permission | Log in as B | `/me` shows subject B, `/partner/orders` returns 403 |
| T3 – External admin claim present | IdP grants admin group to B (if environment allows) | B still lacks `APP_ORDER_READ` |
| T4 – Invalid IdP | Misconfigure issuer/callback in test environment | Sign-in blocked; no permissions granted by skipping checks |
| T5 – Duplicate subject, different issuer | Simulate two external identities with different issuers and same subject | Do not resolve to the same local account just because `sub` matches |
| T6 – Different tenant/partner | Same permission, but order belongs to another partner | Service denies based on ownership |
| T7 – Account disabled | Local account changes `ACTIVE` to `DISABLED` | Sensitive requests denied once revocation policy takes effect |
| T8 – Unlinked | New subject logs in validly via IdP | Not automatically granted read/approval data permissions |

**Completion criteria:** explain why T2/T3 return 403 even though the IdP authenticated the user; why T5 is an issuer boundary violation; and why T6 must still deny even when the application-level authority is valid.

## 11. Self-Assessment Questions

1. **If an ID Token is validly signed and contains `groups=["admin"]`, should you immediately use `hasRole("ADMIN")`?** No. A signature only proves origin and integrity; claim meaning and internal permissions must be mapped per policy.
2. **Why are `iss` and `sub` typically paired to link an OIDC account?** `sub` is scoped to the issuer; email alone or subject alone easily confuses people/tenants.
3. **What if a user has no local account yet signs in successfully at the IdP?** We only know they were authenticated by the IdP. The application denies business permissions or enters the appropriate provisioning/approval workflow.
4. **If someone has `APP_ORDER_READ`, can they view all orders?** No. Ownership, tenant, status, and resource policies must still be checked.
5. **Why might revoking permissions in the database not immediately strip permissions from an existing session?** Some applications snapshot authorities at login; re-verification or session invalidation per policy is required.
6. **When can external groups be used as an authorization input?** When there is a trust contract, issuer/tenant constraints, approved mapping, sync mechanism, and audit; the application remains the decision maker.

## Takeaways

> **The partner answers "who is this person according to my system". The application answers "what is this person, once linked to an internal account, permitted to do with my specific resource".**

Keep **verified external identity → local identity link → local entitlement → resource-level authorization** separated so federation scales sign-in without handing over full business control to partners.

### Official Documentation for Deeper Study

- [Spring Security – OAuth2 Login, Advanced Configuration and Authority Mapping](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Security – OAuth2 Login, Login Flow and Client Registration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – SAML2 Login](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html)
- [OpenID Connect Core 1.0 – ID Token, Subject, and Verification](https://openid.net/specs/openid-connect-core-1_0.html)
