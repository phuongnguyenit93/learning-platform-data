# 13.9. Handling Changed Emails, Unverified Emails, and Account Collisions

## 1. Is an Email Address the User's Login Identity?

Suppose **Employee Portal** uses **Spring Security OAuth 2.0 Client** for OpenID Connect (OIDC) login. A user just completed the Authorization Code Flow, Spring Security validated the ID Token, and created an `OidcUser` principal. The profile contains these claims:

~~~json
{
  "iss": "https://login.example.test/realms/company",
  "sub": "employee-0042",
  "preferred_username": "minh.nguyen",
  "name": "Nguyễn Văn Minh",
  "email": "minh.nguyen@example.test",
  "email_verified": true
}
~~~

An initial implementation might write:

~~~java
// Idea that should NOT be used as an identity-linking policy:
String email = oidcUser.getEmail();
User user = users.findByEmail(email)
    .orElseGet(() -> users.createWithEmail(email));
~~~

This snippet is brief, yet it raises dangerous questions:

- If the user **changes their email** in the identity system, can they still access their old data?
- If the IdP returns an email with `email_verified=false`, should that person be treated as owning the address?
- If an email is recycled for a new employee, could the new hire access the former employee's data?
- If two different IdPs report the same email, are they the same person?
- If a **local account** already exists with that email, should SSO login automatically link into that local account?
- If two concurrent login requests both see "user not found", will they create two duplicate accounts?
- If email is used to grant admin rights or pick a tenant, does changing email alter privileges without approval?

**Design principle:** for OIDC, the most reliable external identifier for linking accounts within an OP is the **`(iss, sub)` pair** taken from the verified identity. **Email is a profile/contact attribute**; `email_verified` indicates the OP verified the address under its process, yet **does not turn email into a safe universal auto-linking key across systems**.

This lesson focuses on **principals and authorization**, because mistakes in email linking can lead directly to **account takeover**, data exposure, or misgranted privileges. Examples use Java 17+, Spring Boot 3, and Spring Security 6 on **Servlet/Spring MVC**, though the identity rules apply equally to WebFlux. All hostnames and IDs are illustrative.

## 2. Separating Four Layers: Authentication, Identity, Profile, and Authorization

Never collapse these concepts into a single `email` column:

| Layer | Question to Answer | Typical Data |
|---|---|---|
| **Authentication** | Who was just authenticated by the OP under OIDC? | Verified ID Token, issuer, subject, timestamps, and auth context |
| **External identity** | Which Portal account does that identity link to? | `(issuer, subject)`, registration/provider, link state |
| **Profile/contact** | How do we address and contact the user? | Email, `email_verified`, name, `preferred_username`, phone, picture |
| **Authorization** | What can that person do inside the Portal? | Internal user ID, tenant membership, roles, permissions, resource ownership |

Example:

~~~text
OIDC Provider
  iss = https://login.example.test/realms/company
  sub = employee-0042
  email = minh.nguyen@example.test
           │
           │ Successful OIDC login + linking policy
           ▼
ExternalIdentity
  (issuer, subject) -> internalUserId = 8e23...
           │
           ▼
AppUser
  id = 8e23...
  status = ACTIVE
  displayName = Nguyễn Văn Minh
           │
           +--> ContactEmail (mutable, tracks verification status)
           │
           +--> TenantMembership + Roles/Permissions
~~~

**Logging in at the IdP does not grant Portal permissions.** Spring Security may mark the principal authenticated, while the Portal must still verify whether that identity **has been provisioned/linked** to an internal user, is active, and holds permission for the target resource.

## 3. Directly Relevant OIDC Claims

| Claim | Typical Meaning | Should It Be the Account Key? |
|---|---|---|
| `iss` | Issuer of the OP that issued the ID Token | Used alongside `sub` to namespace the identity |
| `sub` | Subject identifier of the user at the issuer | **Yes**, scoped under the issuer namespace |
| `email` | Profile email address | **No**, never as sole authentication key |
| `email_verified` | OP indicates email verification occurred per OP rules | No; signal about the email, not proof two accounts are one |
| `preferred_username` | Human-friendly username | No; mutable and can collide |
| `name` | Display name | No; not guaranteed unique |
| `picture` | Profile picture URL | No |
| `aud` | Intended audience of the ID Token | Used in ID Token validation, not as a user key |
| `auth_time`, `acr`, `amr` | Auth time/context/method, when supplied | Useful in step-up auth policies; never replaces subject |

### 3.1. `email_verified` Is Not Always Present

OIDC allows providers to return a Boolean `email_verified` claim when available. Applications must distinguish:

~~~text
email_verified = true
email_verified = false
email_verified = null / claim absent
~~~

**An absent claim** is not equivalent to `true`. If business logic requires a verified email, both `false` and `null` fail the check unless the organization holds **another controlled verification proof** on record.

Requesting the `email` scope does not guarantee the OP always releases both `email` and `email_verified`. Scopes are requests; actual output depends on the OP, user consent, client config, and claim release policies.

### 3.2. ID Token and UserInfo Are Not Browser-Submitted Data

In standard OIDC login, Spring Security validates the ID Token per required rules such as issuer, audience, signature, and expiration. It may then fetch additional claims from the **UserInfo endpoint** when permitted by the provider and grant.

The `sub` claim returned by UserInfo must match the ID Token's subject. If it does not, never use that UserInfo payload as the logged-in user's profile.

Avoid designs like:

~~~http
POST /login/map-user HTTP/1.1
Content-Type: application/json

{"email":"admin@example.test","email_verified":true,"sub":"admin"}
~~~

and immediately trusting that payload as proof of account ownership. Frontend-submitted JSON **never replaces** the OIDC principal created by Spring Security after a valid login.

### 3.3. Point-in-Time Nature of `email_verified`

`email_verified=true` reflects what the provider asserted **at the time/mechanism of claim issuance**. It does not automatically guarantee that:

- The email will never change.
- The address cannot be reassigned to someone else.
- The user continuously controls that mailbox at every future moment.
- A local account or an account at another IdP with the same email belongs to the same person.
- The user is still an active employee or holds admin rights.

The application must define the **trust level and lifetime** of each attribute based on the OP contract and business needs.

## 4. Why Identify by Issuer + Subject?

In OIDC, `sub` is a subject identifier issued by an OP within its issuer scope, not a global username. Two issuers can issue the same `sub` for two different people:

~~~text
Identity A:
  iss = https://login.company.example.test
  sub = 12345

Identity B:
  iss = https://login.partner.example.test
  sub = 12345
~~~

These two `(iss, sub)` pairs are distinct and **must never be treated as the same user**.

Similarly, a shared email:

~~~text
Identity A:
  iss = https://login.company.example.test
  sub = employee-0042
  email = minh@example.test

Identity B:
  iss = https://login.partner.example.test
  sub = partner-9911
  email = minh@example.test
~~~

is not enough to conclude they share an owner. Linking two external identities to one **internal user** must go through a verified workflow.

### 4.1. Subject Is Not an Employee ID or Email

Many OPs treat `sub` as an **opaque identifier**. Applications should:

- Store the exact verified value without truncating, changing case, or assuming a format.
- Never synthesize `sub` from email, username, or employee number.
- Keep `issuer` as the configured trusted OP identity rather than simplifying it to a bare hostname.
- Have a migration plan if the OP changes issuer, tenant, or subject issuance mode.

Some OPs issue different **pairwise subjects** for the same user across clients or sectors. Therefore, `(iss, sub)` should be understood as the **verified external identity for this client** per the provider's contract, not an ID shared across every application.

### 4.2. Distinguishing Principal Name from Business Key

In Spring Security, `Authentication.getName()` typically delegates to `OidcUser.getName()`, which defaults to `sub`. However, `user-name-attribute` can be configured to use `email` or `preferred_username`.

Therefore, **never treat `Authentication.getName()` as your sole internal key without checking the principal configuration**. With OIDC, extract the explicit issuer and subject from `OidcUser.getIdToken()` and map them to an **internal user ID**.

## 5. Five Common Account Scenarios

### 5.1. Scenario A: Email Changes, Subject Stays the Same

~~~text
First login:
  iss = https://login.example.test/realms/company
  sub = employee-0042
  email = minh.nguyen@example.test
  email_verified = true

Later login:
  iss = https://login.example.test/realms/company
  sub = employee-0042
  email = minh.tran@example.test
  email_verified = true
~~~

This is still **the same external identity** because `(iss, sub)` has not changed. The Portal should look up the linked internal user by that pair and preserve all valid orders, permissions, and history. Contact email updates follow an independent policy.

**Never create a new user simply because the new email is not in the database.** Nor should you necessarily route all sensitive alerts to the new email immediately if your organization requires a dedicated email verification workflow.

### 5.2. Scenario B: Unverified Email

~~~json
{
  "sub": "employee-0042",
  "email": "ceo@example.test",
  "email_verified": false
}
~~~

The user may have completed a valid OIDC login under their `sub` yet has not proved control over `ceo@example.test`. Never:

- Look up the CEO's account by email and attach the current external identity to it.
- Allow sensitive account recovery requests based solely on an unverified email.
- Grant admin roles or tenant membership based on an unverified email.
- Overwrite the verified contact email of another account.

You may place the user into a **restricted onboarding state**, require independent email verification, or follow an email-independent account-creation policy depending on business rules. What they are allowed to do meanwhile is an **authorization policy**, not an automatic consequence of OIDC authentication.

### 5.3. Scenario C: Recycled Email

~~~text
Last year:
  iss = https://login.example.test/realms/company
  sub = employee-old
  email = sales@example.test

This year:
  iss = https://login.example.test/realms/company
  sub = employee-new
  email = sales@example.test
~~~

This illustrates that **emails can change owners**, especially role-based addresses (shared mailboxes), departing staff, or transferred domains. If the Portal looks up by email and hands all old documents/orders to the new subject, that is **account takeover via mislinking**.

The safe handling is treating them as **two distinct external identities**. The new subject must be provisioned/linked under its own policy; the old account must be disabled via offboarding rather than transferring data ownership just because the mailbox matches.

### 5.4. Scenario D: Two Accounts with the Same Email

A Portal may have:

~~~text
Internal user A:
  ID = user-100
  linked identity = (company, employee-0042)
  email = minh@example.test

Internal user B:
  ID = user-200
  linked identity = (partner, partner-9122)
  email = minh@example.test
~~~

Two internal users sharing an email may be **two legitimately separate accounts** or a duplicate case requiring review. Never automatically merge data, roles, or tenant memberships to "deduplicate".

Email equality can act as a **hint for duplicate detection**, never sufficient proof to merge identities.

### 5.5. Scenario E: Local Account Existed Before Enabling SSO

The Portal has a local account with:

~~~text
user_id = user-100
email = minh@example.test
authentication = local password
~~~

After enabling OIDC, an external identity logs in with the same email:

~~~text
iss = https://login.example.test/realms/company
sub = employee-0042
email = minh@example.test
email_verified = true
~~~

**Never auto-link solely on matching email**, even if the OP emits `email_verified=true`. A safe workflow requires the user to **authenticate into the existing local account** first and then initiate IdP linking in a dedicated flow, or go through an administrative process that verifies ownership.

## 6. Decision Matrix When Receiving a Profile from OIDC

| Scenario | `(iss, sub)` Pair | Email | Recommended Behavior |
|---|---|---|---|
| Returning login | Already linked | Unchanged | Use existing internal user |
| Email changed | Already linked | Changed | Keep identity; update contact email per policy |
| Unverified email | Already linked | `email_verified=false/null` | Do not treat email as new proof; restrict email-dependent features if needed |
| New user | Unlinked | Unused | Provision if policy allows or require approval |
| Email matches another account | Unlinked | Matches one account | **Do not auto-link**; route to verification workflow |
| Email matches multiple accounts | Unlinked | Multiple matches | Do not pick the first account; never auto-merge |
| Two issuers share a `sub` | Two distinct pairs | May match or differ | Treat as two separate external identities |
| Linked subject disabled | Linked yet account locked | Any | Deny Portal access per account status |
| New issuer after migration | Unlinked under new key | Matches previous email | Controlled migration/linking; never infer from email |

This matrix is a **recommended application policy**, not default built-in behavior from Spring Security. The framework authenticates OIDC; the application decides provisioning, internal user mapping, and permissions.

## 7. Data Architecture: Email Is Not a Primary Key

A storage design can separate:

~~~text
app_user
  id (UUID, primary key)
  status (ACTIVE / PENDING / SUSPENDED / DISABLED)
  display_name
  created_at

external_identity
  id
  user_id (FK -> app_user)
  issuer
  subject
  linked_at
  UNIQUE (issuer, subject)

contact_email
  id
  user_id (FK -> app_user)
  email_original
  email_lookup
  verification_status
  verified_source
  verified_at
  is_primary
  observed_at

tenant_membership
  user_id
  tenant_id
  role / permissions
~~~

This separation ensures:

- External identity stays stable by `issuer + subject`.
- The internal account uses its **own ID** for orders, subscriptions, audits, ownership, and permissions.
- Email becomes a **contact address** that can change, lose verification, be replaced, or keep history rows.
- Multiple external identities can be attached to one internal user **after secure account linking**.
- Tenant memberships and roles do not shift automatically when email changes.

### 7.1. Sample SQL

The schema below uses PostgreSQL-like syntax to illustrate the principles; adjust column names/types to your project's database:

~~~sql
CREATE TABLE app_user (
    id UUID PRIMARY KEY,
    status VARCHAR(32) NOT NULL,
    display_name VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE external_identity (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_user(id),
    issuer VARCHAR(512) NOT NULL,
    subject VARCHAR(512) NOT NULL,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_external_identity UNIQUE (issuer, subject)
);

CREATE TABLE contact_email (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_user(id),
    email_original VARCHAR(320) NOT NULL,
    email_lookup VARCHAR(320) NOT NULL,
    verification_status VARCHAR(24) NOT NULL,
    verified_source VARCHAR(128),
    verified_at TIMESTAMPTZ,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_contact_email_lookup
    ON contact_email (email_lookup);

CREATE INDEX idx_contact_email_user
    ON contact_email (user_id);
~~~

**Why not place a system-wide `UNIQUE(email_lookup)` constraint?** Depending on the domain model, an email may appear on multiple accounts or an account may keep multiple contact emails. A global unique constraint on email makes code prone to **wrongly equating identities** or hitting unresolvable provisioning deadlocks. If your product enforces **one verified email per account within a tenant**, model that constraint scoped to **tenant + email type + status** with clear collision handling—and never treat that constraint as authentication proof for a logged-in caller.

Conversely, `UNIQUE(issuer, subject)` is essential: **one external identity must never link to two internal accounts simultaneously**. Relinking requires an authorized transaction and audit log, not an arbitrary row update.

### 7.2. Avoid Erasing Email Change History Immediately

In some systems, keeping **access-restricted audit records** of email changes helps investigate disputes:

~~~text
2026-01: user-100, email = minh.nguyen@example.test, verified=true
2026-06: user-100, email = minh.tran@example.test, verified=true
~~~

However, email is **personal data**. History retention must obey purpose limitation, retention windows, and access controls; never dump emails, ID Tokens, or full UserInfo into logs indefinitely.

## 8. Designing the Pipeline for Handling Email Claims from OIDC

A safe pipeline once Spring Security completes OIDC verification looks like:

~~~mermaid
flowchart TD
    A["Spring Security validates OIDC, creates OidcUser"] --> B["Read (iss, sub) from verified ID Token"]
    B --> C{"External identity already linked?"}
    C -->|Yes| D["Load app_user by internal ID"]
    C -->|No| E{"Is auto-provisioning allowed?"}
    E -->|No| F["Route to invitation / linking / approval"]
    E -->|Yes| G["Create new app_user in transaction with unique (iss,sub)"]
    G --> D
    D --> H{"User still ACTIVE?"}
    H -->|No| I["Block resource access or apply recovery workflow"]
    H -->|Yes| J["Inspect email and email_verified"]
    J --> K{"Email changed / unverified / collided?"}
    K -->|No| L["Update contact details per policy"]
    K -->|Yes| M["Mark pending or review; NEVER auto-merge"]
    L --> N["Apply tenant membership and permissions"]
    M --> N
    N --> O["Grant access per application policy"]
~~~

Key points:

1. **Always look up the external identity before email.** If the issuer+subject pair exists, the user already has a matching account even if their email changed.
2. **Never auto-link an unknown identity to another account solely on matching email.**
3. **Auto-provisioning is a product policy** that can be enabled or disabled; it is not an automatic requirement of OIDC login.
4. **Account status and permissions** are evaluated independently of `email_verified`.
5. **Collisions** need a resolution workflow that avoids disclosing another account's details to unprivileged users.

### 8.1. Decision Pseudocode

~~~text
identityKey = (validatedIdToken.iss, validatedIdToken.sub)
linked = externalIdentityRepository.find(identityKey)

if linked exists:
    user = userRepository.load(linked.internalUserId)
    if user disabled:
        deny access
    observeEmailClaims(user, email, emailVerified)
    authorize based on internal user, tenant and permissions
else:
    if autoProvisionAllowedForThisTrustedIssuerAndContext:
        create new internal user + identity mapping atomically
        do not attach it to a different existing user by matching email
    else:
        require invitation / explicit account linking / admin approval
~~~

**Note:** an issuer trusted for authentication is not automatically trusted to **grant membership, titles, or admin privileges**. Auto-provisioning requires dedicated rules such as invitations, tenant binding, or a managed employee directory.

## 9. Basic Spring Security OIDC Client Configuration

Example using provider ID and registration ID `company`:

~~~yaml
# application.yml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
            user-name-attribute: sub
~~~

`user-name-attribute: sub` picks subject as the principal name per provider configuration; **it does not create an external identity table or authorization policy by itself**. Using `iss+sub` inside your application service is the identity-linking step.

`OIDC_CLIENT_SECRET` must be supplied securely at runtime. Never commit real secrets to Git, emails, logs, or browsers. ID Tokens and claims in this lesson must come from Spring Security's validated pipeline, not JSON supplied by the frontend.

Servlet dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Example `SecurityFilterChain`:

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain portalSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

**Important:** `anyRequest().authenticated()` only requires the user to be authenticated at the IdP; it is **not enough** to guarantee an active internal account or permission to access Portal resources. Business APIs must check provisioning, mapping, and authorization as shown next. If the Portal needs to block unprovisioned users during login itself, use a dedicated integration point and clear error/onboarding policy.

## 10. Safely Reading Issuer, Subject, and Email from `OidcUser`

In Servlet, after a successful OIDC login:

~~~java
package com.example.portal.identity;

import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public record OidcIdentityKey(String issuer, String subject) {

    public static OidcIdentityKey from(OidcUser principal) {
        String issuer =
            principal.getIdToken().getIssuer().toString();
        String subject =
            principal.getIdToken().getSubject();
        return new OidcIdentityKey(issuer, subject);
    }
}
~~~

And separating email from verification status:

~~~java
package com.example.portal.identity;

import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public record ObservedEmail(
    String value,
    Boolean verified
) {
    public static ObservedEmail from(OidcUser principal) {
        return new ObservedEmail(
            principal.getEmail(),
            principal.getEmailVerified()
        );
    }

    public boolean isVerified() {
        return value != null
            && !value.isBlank()
            && Boolean.TRUE.equals(verified);
    }
}
~~~

In the Java record above, all three cases are handled accurately:

~~~java
new ObservedEmail("minh@example.test", true).isVerified();  // true
new ObservedEmail("minh@example.test", false).isVerified(); // false
new ObservedEmail("minh@example.test", null).isVerified();  // false
~~~

**Never infer** `verified=true` simply because an email appeared in UserInfo. Do not run `Boolean.parseBoolean` on arbitrary data and treat it as a trusted signal; rely on the validated principal and verify the OP's claim contract.

### 10.1. What Should the UI Display When the Claim Is Absent?

You can display:

~~~text
Contact address: Not provided
Email status: Unverified
Action: Verify email address
~~~

Avoid displaying "Email verified" merely because OIDC login succeeded. OIDC authenticates **identity at the OP**; it does not guarantee every profile claim meets the Portal's business rules.

## 11. Mapping `OidcUser` to an Internal User ID

A business service should **resolve the internal user via issuer+subject**, not via email:

~~~java
package com.example.portal.identity;

import java.util.UUID;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IdentityMappingService {

    private final ExternalIdentityRepository identities;
    private final AppUserRepository users;

    public IdentityMappingService(
        ExternalIdentityRepository identities,
        AppUserRepository users
    ) {
        this.identities = identities;
        this.users = users;
    }

    @Transactional(readOnly = true)
    public UUID requireActiveUserId(OidcUser principal) {
        OidcIdentityKey key = OidcIdentityKey.from(principal);

        UUID userId = identities
            .findUserId(key.issuer(), key.subject())
            .orElseThrow(() ->
                new AccountNotLinkedException());

        if (!users.isActive(userId)) {
            throw new AccountDisabledException();
        }

        return userId;
    }
}
~~~

`ExternalIdentityRepository`, `AppUserRepository`, `AccountNotLinkedException`, and `AccountDisabledException` are **application-defined** abstractions/domain types, not built-in Spring Security classes. This code illustrates the mapping flow rather than a complete JPA setup.

**Why not fall back to email when the identity is not found?**

~~~java
// Avoid:
return identities.findUserId(issuer, subject)
    .orElseGet(() -> users.findByEmail(principal.getEmail()).getId());
~~~

If a new subject happens to share someone else's email, that fallback **hands the old account's access to the new identity**. When unmapped, follow invitation, provisioning, or explicit account linking per policy.

### 11.1. Business APIs Must Use the Internal User ID

Illustrative controller:

~~~java
package com.example.portal.web;

import java.util.UUID;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import com.example.portal.identity.IdentityMappingService;

@RestController
public class AccountController {

    private final IdentityMappingService mapping;

    public AccountController(IdentityMappingService mapping) {
        this.mapping = mapping;
    }

    @GetMapping("/api/me/id")
    public UUID currentUserId(
        @AuthenticationPrincipal OidcUser principal
    ) {
        return mapping.requireActiveUserId(principal);
    }
}
~~~

This endpoint **only returns the internal user ID** to illustrate mapping; returning an ID to the frontend does not make it a secret, nor does it replace authorization on other endpoints.

For `/api/orders/{id}`, beyond resolving the internal user, the application must verify whether that user holds permission for that **specific order ID**. Never stop at `.authenticated()` or compare an email in the URL against the principal's email.

## 12. Handling Unlinked Accounts Right Inside OIDC Login

If the product forbids Portal access without an existing internal account, a **custom `OidcUserService`** in Servlet OAuth2 Login can check the mapping before completing login.

Example logic **accepting only already-linked external identities**:

~~~java
package com.example.portal.config;

import java.util.HashSet;
import java.util.Set;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import com.example.portal.identity.IdentityMappingService;

@Configuration
public class PortalOidcUserConfig {

    @Bean
    OAuth2UserService<OidcUserRequest, OidcUser> portalOidcUserService(
        IdentityMappingService mapping
    ) {
        OidcUserService delegate = new OidcUserService();

        return request -> {
            OidcUser oidcUser = delegate.loadUser(request);

            // Never look up by email: issuer + subject come from the ID Token.
            try {
                mapping.requireActiveUserId(oidcUser);
            } catch (RuntimeException e) {
                // Do not leak another person's email/account via login error.
                throw new OAuth2AuthenticationException(
                    new OAuth2Error("portal_account_not_available"),
                    "Portal account not available"
                );
            }

            Set<GrantedAuthority> authorities =
                new HashSet<>(oidcUser.getAuthorities());
            authorities.add(new SimpleGrantedAuthority("PORTAL_USER"));

            return new DefaultOidcUser(
                authorities,
                oidcUser.getIdToken(),
                oidcUser.getUserInfo(),
                "sub"
            );
        };
    }
}
~~~

Wiring the `SecurityFilterChain`:

~~~java
@Bean
SecurityFilterChain portalSecurity(
    HttpSecurity http,
    OAuth2UserService<OidcUserRequest, OidcUser> portalOidcUserService
) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/error").permitAll()
            .anyRequest().hasAuthority("PORTAL_USER"))
        .oauth2Login(login -> login
            .userInfoEndpoint(userInfo -> userInfo
                .oidcUserService(portalOidcUserService)))
        .build();
}
~~~

This is an **alternative** to the `SecurityFilterChain` in Section 9, not a second chain to keep alongside it in the same project. Imports for this DSL block are the classes from the earlier `SecurityFilterChain` example plus `OAuth2UserService`, `OidcUserRequest`, and `OidcUser`.

**Important notes:**

- The example only grants `PORTAL_USER` when a mapping exists and the internal account is active; it **does not** grant admin roles or tenant permissions.
- All domain exceptions are translated into a generic login error in this illustration. In production, catch only **expected business exceptions**; database/network failures must be handled, monitored, and alerted properly rather than silently treated as unprovisioned accounts. Never use a broad catch to mask infrastructure failures.
- Replacing the principal with `DefaultOidcUser` must preserve the ID Token, UserInfo, and necessary original authorities. Never grant admin authorities simply because a new email appeared.
- Depending on your product model, unlinked users may need a **dedicated onboarding flow** instead of failing login. In that case, ensure the security boundary restricts them solely to the onboarding pages and blocks business APIs until linked.

## 13. Auto-Provisioning New Users: Conditions and Transactions

Not every product requires pre-invitation/approval before every login. If the Portal is designed to auto-provision from a managed corporate OP, still enforce these controls:

1. The OP/issuer must belong to a **configured trusted allowlist**, never dynamically selected from untrusted requests.
2. There must be an explicit **account-creation rule** (e.g., tenant invitation, employee roster, or controlled entitlement), not email domain alone.
3. Create the internal user and external identity within the **same transaction**.
4. Enforce **UNIQUE(issuer, subject)** in the database to handle races.
5. On email match, **never auto-merge** with an older internal user.
6. Audit account creation events and policy sources without storing tokens/secrets in audit logs.
7. Grant minimal baseline permissions initially; elevated privileges must go through controlled approval.

### 13.1. Race Conditions with Two Concurrent Callbacks

Suppose the browser sends two authorization flows close together, or application-level retries occur:

~~~text
Request A: find(iss,sub) -> not found
Request B: find(iss,sub) -> not found
Request A: creates app_user A + external_identity
Request B: creates app_user B + external_identity
~~~

Relying only on `findBy...` before inserting can create two users. Use a **database unique constraint** and transaction:

~~~text
transaction:
  check/find external identity
  create app_user (if policy allows)
  insert external_identity(issuer, subject, user_id)
commit
~~~

When the second request hits a unique constraint violation, roll back that transaction and **re-read the validly created identity**—never overwrite the mapping by email or auto-merge two users.

In production, classify retryable errors carefully; racing on a unique constraint does not mean every persistence error should be retried indefinitely.

### 13.2. Disabled Users and Auto-Provisioning

An external identity already linked to a **DISABLED/SUSPENDED** user must never be re-created as a brand-new user just because a query filtered for active users found nothing. Queries must distinguish:

~~~text
linked identity does not exist
linked identity exists, yet account is disabled
linked identity was unlinked/revoked
~~~

These states carry different security consequences. Specifically, **disabled** must block Portal privileges even if the OP still authenticates the user.

## 14. Email Changes: Update Profile, Never Change Data Ownership

A typical sequence after an identity is linked:

~~~mermaid
sequenceDiagram
    participant OP as OIDC Provider
    participant Portal as Employee Portal
    participant Identity as Identity Service
    participant DB as User Database

    OP-->>Portal: OIDC principal with iss, sub, new email
    Portal->>Identity: Resolve (iss, sub)
    Identity->>DB: Query external_identity
    DB-->>Identity: internalUserId = user-100
    Identity->>DB: Observe email and verification claims
    Identity->>Identity: Apply contact email policy
    Identity-->>Portal: user-100 and email status
    Portal->>DB: Check permissions for user-100
    DB-->>Portal: Membership/permissions
    Portal-->>Portal: Continue session with same internalUserId
~~~

Operational rules can be:

- If the new email is verified from a trusted OP and policy permits syncing, update the **contact email** on the **same internal user**.
- If the new email is unverified, retain the previously verified contact email and mark the new email as **pending verification**.
- If the new email already appears on another account, flag a **collision**; never merge or transfer ownership.
- If the email claim disappears, never delete the internal user or external identity. Keep the old contact info with explicit verification status/source.
- If a business process uses email as a local login username, handle updates separately in the local authentication layer.

### 14.1. Difference Between "Verified by OP" and "Verified by Portal"

The Portal may send its own confirmation email to verify mailbox control. When doing so, record the **verification source**:

~~~text
email = minh@example.test
status = VERIFIED
source = OIDC_PROVIDER_COMPANY
observed_at = ...
verified_at = ...
~~~

or:

~~~text
email = minh@example.test
status = VERIFIED
source = PORTAL_EMAIL_CHALLENGE
verified_at = ...
~~~

The two sources may carry different trust levels depending on business rules. Avoid collapsing everything into a single `isEmailVerified` boolean unable to answer **who verified it, when, whether it is still valid, and whether it can be revoked**.

## 15. Unverified Emails: What Restrictions Apply and How to Verify?

Having `email_verified=false` does not necessarily invalidate OIDC login: the **authenticated subject** may still be valid. Yet that email **is not trustworthy enough** for features relying on mailbox ownership.

Example matrix:

| Feature | Valid OIDC Login, Unverified Email |
|---|---|
| Display user's own basic info | Allowed per account permissions |
| View orders belonging to linked internal user | Check permissions/ownership; do not rely on email |
| Change primary contact email | May require verifying the new address |
| Receive invoices/alerts with sensitive data | Consider blocking until the new email is verified |
| Link with a local account by email | **Do not allow automatically** |
| Grant admin role because email matches an admin address | **Never allow** |
| Auto-join tenant by email domain | **Insufficient proof** |

### 15.1. Portal-Driven Email Verification Flow

When the product verifies mailboxes itself, implement:

1. An **authenticated** user requests adding/changing the contact email on their own internal account.
2. The server generates a **random, one-time token** bound to the internal user ID, target email, purpose, and expiration.
3. The server sends the confirmation link/token to that email over an appropriate channel.
4. When the user completes it, the server validates the token and exact **`user + email + purpose`** binding.
5. Update the verified contact email inside a transaction and invalidate old tokens.
6. If the email already belongs to another account, never silently reassign or merge; route to collision resolution.

Never use a **JWT ID Token** or **OAuth access token** as a makeshift email verification code. An email verification token is a distinct business credential; store a hash of the random token where appropriate and never put the raw value in logs.

### 15.2. Never Leak Other Users' Details in Error Messages

Instead of:

~~~text
This email belongs to user Nguyễn Văn Minh,
account ID=user-100, who holds the PORTAL_ADMIN role.
~~~

use a generic response:

~~~text
Unable to complete linking this address.
Please use the verification workflow or contact support.
~~~

Duplicate account details and access evidence should be visible only to **authorized support personnel**.

## 16. Account Collisions: Detection Does Not Mean Auto-Merge

A collision can be detected when a new external identity arrives with a matching email:

~~~text
New external identity:
  iss = https://login.company.example.test
  sub = employee-8888
  email = shared@example.test
  email_verified = true

Existing internal user:
  id = user-100
  linked = (https://login.legacy.example.test, legacy-042)
  email = shared@example.test
~~~

The system can record:

~~~text
POTENTIAL_DUPLICATE_EMAIL
  candidate_external_identity = (issuer, subject)
  matching_contact_email = shared@example.test
  resolution = REVIEW_REQUIRED
~~~

Yet **never** run automatically:

~~~sql
-- Dangerous example: NEVER perform solely based on matching email.
UPDATE external_identity
SET user_id = 'user-100'
WHERE issuer = 'https://login.company.example.test'
  AND subject = 'employee-8888';
~~~

Doing so would immediately hand **all of the old account's data and roles** to the new external identity.

### 16.1. Collision Resolution Policies

Collisions can be categorized as:

- **Two identities genuinely belong to one person**: require an evidence-backed linking workflow.
- **Two different people using a shared mailbox**: keep two internal users and forbid using that email as account ownership proof.
- **Recycled email**: never transfer ownership of the old account.
- **Faulty imported data**: fix data with auditing, never auto-merge.
- **Local account and SSO account sharing an email**: require authenticating both accounts or an authorized support workflow.
- **Compromised account / suspected fraud**: freeze linking, assess risk, and inspect active sessions.

No single SQL "merge by email" query is safe for all scenarios above.

## 17. Secure Account Linking

If a user genuinely owns two external identities and wants to share one internal account, require **proof of control over both sides** or an equivalent administrative workflow.

Example explicit linking flow:

~~~mermaid
sequenceDiagram
    actor U as User
    participant Portal as Portal
    participant OP1 as Provider A
    participant OP2 as Provider B
    participant DB as Identity Database

    U->>Portal: Log in with Provider A
    Portal->>OP1: OIDC authorization flow
    OP1-->>Portal: Valid identity A
    Portal->>DB: A -> internal user-100
    U->>Portal: Request to link Provider B
    Portal->>Portal: Check account/session and reauthentication policy
    Portal->>OP2: OIDC flow proving control of identity B
    OP2-->>Portal: Valid identity B
    Portal->>DB: Verify B is not linked to another user
    Portal->>DB: Transaction links B -> user-100 + audit
    Portal-->>U: Linking complete
~~~

Required controls:

1. User must hold a **valid Portal session** for the target internal user; require **recent reauthentication** near linking time.
2. The new external identity must be proved through a **separate OIDC login** against the new IdP with verified state/nonce/PKCE and redirect URI.
3. Never accept browser-entered `issuer` and `sub` to "link accounts".
4. Reject or route to review if the new identity **is already linked to another internal user**.
5. Transaction must enforce `UNIQUE(issuer, subject)` and record a linking audit event.
6. Preserve the target internal user's existing permissions; never union roles from two accounts merely due to linking.
7. If unlinking is allowed, ensure the user retains a safe login/recovery method to avoid accidental permanent lockout.

**Warning about dual login flows:** standard OAuth2 login can overwrite the current `Authentication` when the callback finishes. An account-linking feature must preserve proof of the **authenticated target internal user** via state/session or an integrity-protected linking transaction. Never implement it as "after callback, take the emails of both principals and merge"; design a clear boundary between primary login and proof-of-possession for the second identity.

### 17.1. Is Linking an Account via Email Verification Sufficient?

Mailbox control can be **one supporting signal**, yet it usually does not prove someone owns another account holding sensitive history/roles. If a product offers **email-based account recovery/linking**, evaluate email recycling risk, OP assurance level, verification timing, MFA/step-up, user alerts, and anti-takeover controls. For privileged accounts, require stronger verification than email confirmation alone.

## 18. Email Domain and Tenant Authorization

A classic mistake:

~~~java
// NEVER use as the sole condition for granting tenant access:
if (user.getEmail().endsWith("@example.test")) {
    grantAuthority("TENANT_ADMIN");
}
~~~

Issues:

- The email might be unverified.
- The email domain might belong to a shared mailbox, alias, or partner account.
- The user might change emails while tenant membership has not changed.
- Not every employee of an organization is automatically granted Portal access.
- Simple string matching cannot replace enterprise tenant/role policies.

A better design:

~~~text
OIDC verified principal
   -> (issuer, subject)
   -> internal user ID
   -> Portal-managed tenant memberships
   -> user roles and permissions within the tenant
   -> per-resource authorization
~~~

Email domain may serve as an **onboarding tenant hint** if policy allows, yet **never automatically grants admin or data permissions**.

### 18.1. Authorization Must Rely on Trusted Sources

If the Portal relies on groups/roles from an IdP, map claims/authorities from verified sources, trusted audience/issuer, and explicit role-mapping policies. Never let clients send `{"role":"ADMIN"}` from the frontend and treat it as an authority.

Example application-side access control:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/admin/**").hasAuthority("PORTAL_ADMIN")
    .anyRequest().authenticated()
);
~~~

`PORTAL_ADMIN` must be granted through a dedicated authorization pipeline, never simply because email or `preferred_username` equals a specific value.

Even when a route only requires `PORTAL_USER`, the service layer must check **ownership** or **tenant membership** on each business record.

## 19. Normalizing Emails for Lookup: Proceed with Caution

Emails are often queried case-insensitively, yet **you cannot apply arbitrary transformations across every domain/mailbox**.

For example:

~~~text
MINH.NGUYEN@EXAMPLE.TEST
minh.nguyen@example.test
~~~

A lookup policy may treat both spellings as equivalent under an organization's contract. However, transformations such as:

- Stripping dots in the local part.
- Stripping `+` suffixes.
- Removing non-ASCII characters.
- Automatically folding Unicode or rewriting the entire local part.

do not hold true across all email providers.

Recommendations:

1. **Store the original email** for display and permitted investigations.
2. Maintain an **`email_lookup`** normalized under an **explicit policy**, minimally handling input whitespace and appropriate domain casing.
3. Never use a normalized email as an external identity key.
4. When a match is found, treat it as a **candidate collision**, never auto-linking.
5. Ensure Unicode/IDN/case-folding rules align with your real providers and mail infrastructure.

For instance, `alice+finance@example.test` and `alice@example.test` **may** deliver to the same mailbox on some providers, yet you cannot assume that for every email domain. Stripping plus-suffixes to merge accounts can merge unrelated users.

## 20. Advanced Cases

### 20.1. IdP Changes Issuer or Tenant

If an OP moves from:

~~~text
https://login.old.example.test/realms/company
~~~

to:

~~~text
https://login.new.example.test/realms/company
~~~

the `(iss, sub)` pair also changes even if `sub` looks identical. **Never auto-connect the two identities by email.**

A migration requires a trusted mapping source, transition window, validation across users, rollback plan, and auditing. If legacy data was wrongly linked by email, perform targeted remediation rather than broadening merge rules.

### 20.2. Pairwise Subjects Change per Client

An OP may issue a different `sub` for the same person when the Portal changes client registration or sector configuration. That event requires a verified migration or linking plan; never use `preferred_username`/email to "guess" all old subjects.

### 20.3. User Deleted or Locked at the IdP

When the OP denies login, the Portal should not rely on cached email in the database to keep issuing identities. For still-valid Portal sessions, design revocation/session expiration and `ACTIVE` status checks commensurate with risk.

**An earlier OIDC login session does not prove an employee still holds access today.** If business rules require immediate permission updates, use provisioning/deprovisioning hooks and appropriate session lifetimes.

### 20.4. Email Dropped from UserInfo on a Later Login

If the OP stops returning email due to changed scopes or policies, the Portal should not:

- Overwrite email with an empty string and wipe contact info unexpectedly.
- Delete the account or external identity.
- Look up another account simply because email is null.

Distinguish **claim absent in this observation** from **provider confirmed the old email was revoked**. Profile update policies may prompt for re-verification or notify the user.

### 20.5. Using Email for Local Password Reset

If the Portal still supports local username/password alongside SSO, email password reset is a **separate authentication flow**. Never let an OIDC principal with a matching email change a local account's password without going through verified account linking/reauthentication or a strong recovery policy.

## 21. Testing All Branches of the Identity Policy

Because account-linking bugs have severe impact, test **business decisions** independently of HTTP OIDC login wiring:

| Case | Input | Expected Outcome |
|---|---|---|
| Returning login | Same issuer+subject, email unchanged | Same internal user |
| Email changed | Same issuer+subject, verified new email | Same internal user; update contact per policy |
| Unverified email | Linked identity, `email_verified=false` | Do not link elsewhere; restrict email-dependent actions |
| Missing verified claim | `email_verified=null` | Never default to true |
| Email matches another account | New subject, email matches old user | Do not auto-link |
| Two issuers share subject | Different issuers, same `sub` | Two distinct external identities |
| Recycled email | New subject, same email | Never transfer old account privileges |
| Disabled account | Valid identity, user disabled | Grant no Portal permissions |
| Two concurrent callbacks | Same issuer+subject creating new user | Only one external identity mapping succeeds |
| UserInfo missing email | Valid `issuer+sub` | Do not lose identity; handle missing profile per policy |
| Email changed, fixed roles | Same identity | Do not auto-grant/revoke roles solely from email |
| Linking identity already bound to another user | B already linked elsewhere | Reject or manual review; never overwrite |

### 21.1. Unit Tests for `email_verified`

Example testing the `ObservedEmail` helper with JUnit 5:

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ObservedEmailTest {

    @Test
    void missingVerifiedClaimMustNotBeTrusted() {
        ObservedEmail email =
            new ObservedEmail("minh@example.test", null);
        assertFalse(email.isVerified());
    }

    @Test
    void explicitlyFalseVerifiedClaimMustNotBeTrusted() {
        ObservedEmail email =
            new ObservedEmail("minh@example.test", false);
        assertFalse(email.isVerified());
    }

    @Test
    void verifiedEmailMustHaveNonEmptyValue() {
        assertFalse(new ObservedEmail(null, true).isVerified());
        assertFalse(new ObservedEmail(" ", true).isVerified());
        assertTrue(new ObservedEmail("minh@example.test", true).isVerified());
    }
}
~~~

These are unit tests of **Java logic**, not OIDC ID Token validation tests. In integration tests, Spring Security Test can simulate principals via `oidcLogin()`; to test issuer, callback, token exchange, and OIDC discovery end-to-end, use an appropriate test environment or mock IdP server.

### 21.2. Test Distinguishing Issuer+Subject Pairs

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class OidcIdentityKeyTest {

    @Test
    void sameSubjectFromTwoIssuersIsDifferentIdentity() {
        OidcIdentityKey company =
            new OidcIdentityKey("https://login.company.test", "42");
        OidcIdentityKey partner =
            new OidcIdentityKey("https://login.partner.test", "42");

        assertNotEquals(company, partner);
    }
}
~~~

To test provisioning race conditions, unit-testing `findBy...` is not enough: write a database integration test with the **real unique constraint** and concurrent transactions/rollbacks.

## 22. Troubleshooting: When Users Report "I Lost My Account"

| Symptom | Likely Cause | Where to Investigate |
|---|---|---|
| Changed email, old orders vanished | System looked up user by email, creating a new account | Compare before/after issuer+subject and internal user mappings |
| Two accounts with same email merged wrongly | Auto-linked by email or overly aggressive normalization | Inspect linking audits, roll back, restore data permissions |
| SSO login accessed a local account's data | Fallback queried local user by email | Remove auto-link, require proof of ownership of both accounts |
| `email_verified=false` still got admin rights | Authorization relied on email/domain | Inspect role/tenant membership source and verification policy |
| `email_verified` absent yet UI says "verified" | Defaulted null to true or buggy condition | Inspect claim mapping and `Boolean.TRUE` check |
| Two IdPs share `sub` causing collision | Used `sub` alone as global unique key | Add issuer namespace and migrate data |
| Issuer change treated user as brand-new | External identity key changed | Evidence-based identity migration/linking |
| Two concurrent callbacks created two users | Check-then-insert without unique constraint | Transactions and `UNIQUE(issuer, subject)` |
| Locked user still accesses API | Checked `authenticated` only, skipped internal status | Authorization layer and session/revocation checks |
| Email claim missing after IdP update | Scope/consent/UserInfo changed | Check provider and missing-data policy |
| SSO succeeds, Portal blocks account | Unprovisioned, unapproved link, or disabled user | Distinguish successful authentication from Portal access |
| Linking old account fails | New identity already linked to another user | Audited dispute handling; never overwrite |

**Never log full ID Tokens, access tokens, refresh tokens, session cookies, or raw personal data for debugging.** You can log **event IDs, configured issuer, mapping status codes, policy-pseudonymized internal user IDs, and error categories** with appropriate access/retention controls.

## 23. Security and Incident Response When Wrong Merging Is Found

If you discover an external identity was mislinked to another account due to email matching, treat it as an **authorization/data incident**, not merely a profile bug.

Coordinate with operations/security teams to:

1. **Stop ongoing unauthorized access**: temporarily disable suspicious mappings or related sessions/permissions per approved procedure.
2. **Determine scope**: which external identities, internal users, tenants/resources, and time window were impacted.
3. **Inspect audits and integrity**: data reads/writes, granted permissions, email/role changes.
4. **Restore accurate mappings**: based on issuer+subject and verified evidence, never guessing from email.
5. **Evaluate active tokens/sessions** and revoke/log out/expire as needed.
6. **Fix the root cause**: remove find-by-email-and-link logic, add uniqueness/transactions, add collision tests and manual review workflows.
7. **Handle notification obligations** under applicable security policies and data regulations.

If data was written into the wrong account, simply "unlinking the identity" may not suffice; assess whether permissions or records were altered and must be reverted.

## 24. Pre-Deployment Checklist

| Question | Expected Requirement |
|---|---|
| Where does the OIDC principal come from? | OIDC login verified by Spring Security, never self-declared JSON |
| What is the external identity key? | `(issuer, subject)` |
| Does the app have its own internal user ID? | Yes; used for ownership and business data |
| Is email used as a primary/linking key? | No |
| Are `email_verified=true/false/null` distinguished? | Yes |
| What if the email claim is missing? | Identity stays intact; policy handles missing profile fields |
| What if email changes? | Keep internal user by identity; update contact email appropriately |
| What if an email collides? | Never auto-merge; route to review/linking flow |
| Can two IdPs with same sub/email collide? | No; issuer namespace is preserved |
| What if a new identity is already linked elsewhere? | Cannot overwrite arbitrarily; blocked by unique constraint |
| Does auto-provisioning enforce conditions? | Yes, by issuer/tenant/invitation and least privilege |
| Can a disabled user keep accessing the app? | No, even if IdP login succeeds |
| Do business APIs enforce authorization? | Yes, by internal ID, tenant, resource, and permissions |
| Does account linking require reauthentication and audits? | Yes, scaled to account sensitivity |
| Are transactions/uniqueness guarding race conditions? | Yes, `UNIQUE(issuer, subject)` |
| Are changed, unverified, recycled, and colliding emails tested? | Yes, with explicit test cases |
| Does logging avoid unnecessary tokens/emails? | Yes, aligned with personal data policies |

## 25. Self-Practice Exercises

### Exercise 1 — Email Changes, Subject Stays the Same

~~~text
Day 1: iss=company, sub=A42, email=minh.nguyen@example.test
Day 2: iss=company, sub=A42, email=minh.tran@example.test
~~~

**Question:** Should you create a new internal account and transfer all orders to it?

**Solution:** No. Look up the mapping by issuer+subject to preserve the internal user; update contact details per policy. Ownership/permissions do not change merely because email changed.

### Exercise 2 — Matching Email, Different Subject

~~~text
Existing: iss=company, sub=OLD, email=sales@example.test
New:      iss=company, sub=NEW, email=sales@example.test
~~~

**Question:** Can you automatically link subject `NEW` to account `OLD` because `email_verified=true`?

**Solution:** No. Email may be recycled or a shared mailbox. Require evidence-backed provisioning/linking and verify the old account rather than handing over access automatically.

### Exercise 3 — Unverified Email

~~~json
{"sub":"guest-101","email":"admin@example.test","email_verified":false}
~~~

**Question:** Is a valid OAuth2 Login enough to call `/admin`?

**Solution:** No. Enforce authorization policies and roles/permissions from trusted sources. An unverified email is even further from proof of admin rights.

### Exercise 4 — Local Account with Matching Email

~~~text
Local account user-100: minh@example.test
New OIDC identity B: minh@example.test, verified=true
~~~

**Question:** Which workflow is safer than auto-linking?

**Solution:** Have the user authenticate into the existing local account, perform a separate OIDC login proving control of identity B, and link inside a transaction after confirming B is not bound to another account. For sensitive accounts, add reauthentication/step-up or admin review.

### Exercise 5 — Two Concurrent Requests

Two callbacks for the same `(issuer, subject)` hit two nodes, and both see no existing mapping.

**Question:** What prevents creating two accounts?

**Solution:** Transactions combined with `UNIQUE(issuer, subject)`. On conflict, roll back the losing request and re-read the created mapping—never merge by email.

## 26. Summary

In **Spring Security OAuth 2.0/OIDC Client** applications, **email is not an immutable login identifier**. It can change, be absent, be unverified, be recycled, or appear across multiple accounts and IdPs. `email_verified=true` indicates address verification per the OP; it is **not** sufficient proof to auto-link accounts and **does not grant access permissions**.

A durable design uses **`(iss, sub)` from the verified OIDC principal** to locate the **external identity**, maps it to the Portal's **internal user ID**, and independently checks **account status + tenant membership + permissions**. Email, `preferred_username`, and name belong in the profile/contact layer with their own verification status, history, and policies.

When email changes, **preserve identity and ownership**; when email is unverified, **never use it as new proof**; when emails collide, **never auto-merge or auto-link**. Provisioning, linking, unlinking, and identity migrations require transactions, uniqueness constraints, authorization checks, audits, and conflict resolution. A clear boundary between **authentication**, **identity mapping**, **profile**, and **authorization** is the key to preventing account takeover in multi-provider federated login applications.
