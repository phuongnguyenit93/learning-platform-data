# Verified Account Linking and Preventing Account Takeover

## 1. Context and scope

An application may allow users to sign in with a password, passkey, and multiple different OpenID Providers (OPs). A user might want to link a corporate account, a personal account, or a second login provider as a backup access method.

Federated account linking is the operation where an application attaches a federated identity to an existing internal account. When the user authenticates at an Identity Provider (IdP), the application uses the linked identifier to look up the right local account.

This is an operation that can alter account control. If an application automatically merges two accounts just because their emails match, an attacker can attach their own identity to a victim's account or hijack access to a pre-created account.

In a Spring system, roles must be clearly separated:

- Spring Security OAuth2 Client handles login with external IdPs, validates the OIDC response, and provides the OIDC principal.
- The application's Account/Identity service decides which internal account an external identity is linked to.
- Spring Authorization Server can act as an internal broker or OpenID Provider, issuing tokens to downstream applications after the user has been mapped to an internal account.

Spring Authorization Server does not provide a complete account-linking model out of the box. The application must manage links in its domain/account store and grant access only after full verification.

### Learning objectives

After this lesson, you will be able to:

1. Distinguish local account, external identity, IdP, and RP.
2. Identify a federated identity by issuer and subject.
3. Explain why email or username is not a linking key.
4. Design a linking flow requiring authentication of the existing account and verification of the new IdP.
5. Prevent CSRF, login CSRF, session swapping, and callback injection.
6. Recognize account pre-hijacking and auto-merge vulnerabilities.
7. Design schemas, unique constraints, and transactions for identity mapping.
8. Integrate Spring Security OIDC Login with an account-linking service.
9. Distinguish normal login flows from identity linking flows.
10. Design unlinking, recovery, auditing, notifications, and anti-takeover testing.

## 2. Roles and data to distinguish

| Component | Meaning | Example |
|---|---|---|
| Local account | Account managed by the application | account_id = 8f... |
| External identity | Identifier of a user at an IdP | issuer + subject |
| Identity Provider (IdP/OP) | Party authenticating users and issuing assertions | Corporate OIDC Provider |
| Relying Party (RP) | Application receiving assertions and creating internal sessions | Spring Security OAuth2 Client |
| Identity link | Record connecting an external identity to a local account | account_id ↔ issuer/sub |
| Internal Authorization Server | Issues tokens to downstream clients | Spring Authorization Server |

A person can have multiple external identities while still using a single local account. For example, a user links both a corporate account and a personal account to the same internal profile.

An external identity is not a local account. Email, display name, and avatar are profile attributes; they can change and should not determine account ownership.

## 3. OIDC identifier key: issuer combined with subject

With OpenID Connect, the stable identifier of an End-User at an issuer is the pair:

- iss: Issuer Identifier of the OpenID Provider.
- sub: Subject Identifier issued by the issuer.

OIDC Core specifies that `iss` and `sub` combined form the single stable identifier an RP can rely on. `sub` must be unique within the issuer and never reassigned to another End-User. Claims such as email, phone_number, preferred_username, and name do not carry the same stability or uniqueness guarantees.

Therefore, the application should use the logical key:

~~~text
FederatedIdentityKey = (issuer, subject)
~~~

Do not use `sub` alone because two different IdPs can issue the same subject value. Do not arbitrarily normalize the issuer by stripping paths, changing case, or removing trailing slashes; compare against the verified and trusted configured Issuer Identifier.

### 3.1. Subject is an opaque identifier

`sub` is a machine-readable identifier. Do not parse its structure, assume it contains an email or username, or allow users to manually input a subject to link.

The application only extracts `sub` from a verified ID Token. Never accept `iss` or `sub` from a form, query parameter, or browser JSON request.

### 3.2. Pairwise subjects and multiple Client Registrations

Some OPs use pairwise subject identifiers so different RPs cannot easily correlate the same user. In that case, the same End-User can receive different `sub` values depending on the sector/client context.

Do not assume a subject received from client registration A will match the subject from registration B. If the system uses multiple OIDC client registrations with the same IdP, define the sector identifier and identification strategy upfront. Use the right configured registration for the linking flow; if migrating registrations, follow a verified migration process at the IdP.

## 4. Why must accounts never be auto-linked by email?

Email is a contact attribute, not a federated identifier. OIDC Core explicitly states that an RP MUST NOT use email, phone_number, preferred_username, or name as a unique identifier.

Even when the IdP returns `email_verified=true`, that only reflects email verification status under the issuer's own policy. It does not prove the external identity belongs to the local account currently open in the browser, nor does it prove the holder of the local session has the right to add a new login method.

Email addresses can change over time, be recycled by an IdP after an old account closes, have different aliasing or normalization rules across systems, and be verified at one point in time while no longer controlled by the same person.

Therefore:

- Use the `(iss, sub)` pair as the external identity key.
- You may store email as a snapshot for display or notifications.
- Never use matching emails to automatically merge or link accounts.
- Never use `email_verified` as a substitute for re-authenticating the internal account.

Email can assist in locating a profile to start a controlled account resolution workflow, but the linking decision must rely on strong proof that the external identity genuinely belongs to the owner of the internal account.

## 5. Security principles for account linking

A secure linking workflow must maintain the following invariants:

1. The user is authenticated into the local account before initiating linking.
2. For sensitive operations, the user must re-authenticate or step up using a method already attached to the local account.
3. The user completes a dedicated OIDC authentication transaction with the new IdP.
4. The callback is bound to the exact browser session, exact local account, and exact selected IdP.
5. The ID Token is verified before extracting issuer and subject.
6. One external identity belongs to at most one local account within the RP's scope.
7. There is no automatic merge path based solely on email or profile claims.
8. Linking/unlinking is audited and notified.
9. Unlinking must revoke login access for the removed external identity.
10. The database must enforce invariants with unique constraints and transactions, not just Java-layer checks.

NIST SP 800-63C-4 Section 3.8.1 requires that an RP SHALL require an authenticated session with the subscriber's account for any linking function. This session SHOULD require authentication using an existing federated identifier before linking a new federated identifier.

## 6. Threat model: how can an attacker hijack an account?

### 6.1. Auto-merge by email

The victim already has a local password account. The attacker creates or controls an external account using the same email as the victim. If the application automatically attaches that external identity to the local account with the matching email, the attacker gains another login method into the victim's account.

### 6.2. Account pre-hijacking

Account pre-hijacking occurs when an attacker acts before the victim completes account creation. One example is an attacker creating a local password account with the victim's email. Later, the victim logs in with an IdP and the application auto-merges by email. The internal account still retains the password known to the attacker, allowing the attacker continued access after the victim uses SSO.

USENIX Security 2022 research documented several pre-hijacking variants, including the Classic-Federated Merge Attack. Therefore, signup, login, and linking flows must be designed together; protecting only the link endpoint is insufficient.

### 6.3. Login CSRF or callback injection

An attacker initiates a login with their own IdP, then tricks the browser logged into the victim's local account into submitting that callback/authorization response. If the application does not bind the transaction to the session and linking intent, the attacker's external identity can be attached to the victim's account.

### 6.4. Session swapping

A user starts linking on account A. During the redirect to the IdP, the session changes, logs out, or switches to account B. If the callback simply reads the account ID from browser-submitted state or unbound data, the identity can be attached to the wrong account.

### 6.5. Race conditions

Two concurrent requests attempt to link an external identity to two local accounts. If the application only checks existence before inserting, both requests can pass the check and create conflicting links.

### 6.6. Fake IdP or issuer confusion

An attacker sends an arbitrary issuer, exploits an uncontrolled discovery URL, or tricks the application into confusing a callback from one IdP with another. The result can be trusting an identity issued by an unauthorized issuer.

## 7. Secure account linking flow

~~~mermaid
sequenceDiagram
    actor U as User
    participant APP as Application / RP
    participant DB as Account & Identity Store
    participant IDP as External OIDC Provider

    U->>APP: POST /account/identities/{provider}/link
    APP->>APP: Check CSRF and local session
    APP->>APP: Re-auth / step-up if policy requires
    APP->>DB: Create PendingLink bound to account + session + issuer
    APP-->>U: Redirect to OIDC Authorization Endpoint
    U->>IDP: Authentication Request + state + nonce + PKCE
    IDP->>IDP: Authenticate user at IdP
    IDP-->>U: Redirect callback + authorization code + state
    U->>APP: GET /login/oauth2/code/{registrationId}
    APP->>APP: Verify state, PKCE, ID Token, and nonce
    APP->>DB: Find PendingLink and verify session binding
    APP->>APP: Extract issuer + subject from verified ID Token
    APP->>DB: Transaction + unique (issuer, subject)
    DB-->>APP: Identity linked
    APP->>DB: Write audit + notification outbox
    APP-->>U: Preserve local account session and display result
~~~

The IdP callback only proves the user authenticated with the IdP. It does not by itself decide the target local account. The target local account must be determined from the server-side transaction created earlier.

## 8. Initiating linking from an authenticated local account

The endpoint initiating linking should be POST, have CSRF protection, and require an authenticated user:

~~~http
POST /account/identities/workforce/link HTTP/1.1
Host: app.example.com
Cookie: SESSION=...
X-CSRF-TOKEN: ...
Content-Type: application/x-www-form-urlencoded
~~~

The server performs:

1. Extract the local account ID from the authenticated principal.
2. Verify the account is active and not locked.
3. Verify the current authentication method is sufficiently strong per policy.
4. Require re-authentication/step-up if the operation is sensitive or the session is too old.
5. Verify the provider registration is in the allowlist.
6. Create a short-lived pending link transaction.
7. Redirect the browser to the authorization endpoint of the right provider.

Do not use GET to perform state changes. Never let the browser pass the target account ID directly in the request body to decide which account gets linked.

### 8.1. Re-authentication and step-up

Linking an additional login method can help a user recover an account, but it also opens another path for an attacker. Therefore, require re-authentication using a method already attached to the local account before linking.

Depending on risk, you can require re-entering the current password, passkey or MFA verification, re-authenticating via an already-linked federated identity, or additional verification by a help desk/controlled recovery workflow.

Do not treat having just logged in with the new IdP as proof of control over the old local account.

## 9. Pending link transactions and session binding

Do not put account ID, email, or link authorization in modifiable query parameters. Create a server-side transaction:

~~~java
public record PendingIdentityLink(
    String stateHash,
    UUID localAccountId,
    String localSessionBinding,
    String registrationId,
    String expectedIssuer,
    Instant createdAt,
    Instant expiresAt,
    LinkStatus status
) {
}
~~~

This is an illustrative model. The transaction should hold a hash of the state or an unpredictable transaction identifier, the local account ID taken from the authenticated principal, a browser session binding token, the registration ID and expected issuer, creation/expiration timestamps, and status PENDING/CONSUMED/EXPIRED/FAILED.

State does not contain raw account IDs. Sensitive data is stored server-side; never trust state contents sent back by the browser unless verified by Spring Security.

### 9.1. State, nonce, and PKCE

In the OIDC Authorization Code Flow:

- `state` binds the authorization response to the request and browser session.
- `nonce` binds the ID Token to the authentication request, helping prevent replay.
- PKCE binds the authorization code to the client that initiated the request.

Values must be per-transaction, unpredictable, single-use, and bound to the browser session. Never use a static state or nonce. Never disable state/nonce checks just to make callbacks work.

Spring Security OAuth2 Login already includes mechanisms to manage authorization requests and verify responses. If customizing `AuthorizationRequestResolver` or `AuthorizationRequestRepository`, preserve those checks and ensure the pending link transaction is bound to the same session.

For public clients, Spring Security automatically uses PKCE when the registration is configured as public. For confidential clients, if policy requires PKCE, enable it with an authorization request customizer:

~~~java
@Bean
OAuth2AuthorizationRequestResolver authorizationRequestResolver(
        ClientRegistrationRepository registrations) {

    DefaultOAuth2AuthorizationRequestResolver resolver =
        new DefaultOAuth2AuthorizationRequestResolver(
            registrations,
            DefaultOAuth2AuthorizationRequestResolver
                .DEFAULT_AUTHORIZATION_REQUEST_BASE_URI);

    resolver.setAuthorizationRequestCustomizer(
        OAuth2AuthorizationRequestCustomizers.withPkce());

    return resolver;
}
~~~

Attach this resolver to `oauth2Login` via `authorizationEndpoint(...).authorizationRequestResolver(...)`. If supported by the IdP, you can add `prompt=login` or `max_age` for linking flows; always verify `auth_time` when `max_age` is requested. Never overwrite `state`, `nonce`, or `code_verifier` managed by Spring Security.

### 9.2. Expiration and single-use consumption

Pending links should have a short TTL, such as a few minutes depending on UX and policy. Upon callback success or terminal failure, the transaction must be consumed or closed. Replayed callbacks must not create additional links.

Do not keep pending links indefinitely in the session. Delete transactions when the user cancels, logs out, switches local accounts, or the session expires.

## 10. Configuring trusted OIDC providers in Spring Security

Allow only IdPs pre-configured by administrators. Never accept arbitrary issuer/discovery URLs from the browser.

Spring Boot configuration example:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          workforce:
            provider: workforce-idp
            client-id: app-linking-client
            client-secret: SECRET_FROM_SECRET_MANAGER
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          workforce-idp:
            issuer-uri: https://idp.example.com
~~~

The application uses issuer discovery to retrieve the authorization endpoint, token endpoint, and JWKS URI. In production, use HTTPS, manage client secrets in a secret manager, pin issuers/registration IDs, enforce exact redirect URI matching, and never let users choose an arbitrary issuer or discovery URL.

### 10.1. Never dynamically fetch keys from an issuer inside a token

Never trust `iss`, `jku`, `x5u`, or URLs supplied by JWT headers/claims themselves to fetch keys. Use the configured issuer and the JWKS endpoint obtained from verified discovery.

If the system supports multiple issuers, maintain a clear binding between registration ID, issuer, callback URI, and token validation policy to prevent mix-ups.

## 11. Verifying the ID Token before linking

Extract the external identity only after OIDC authentication succeeds and the ID Token has been verified.

Important OIDC checks include:

- The ID Token signature is valid under a key from the trusted issuer.
- `iss` exactly matches the configured/discovered Issuer Identifier.
- `aud` contains the `client_id` of the registration being processed.
- `azp` is verified when present and as required by OIDC.
- `exp` has not expired.
- `iat` is within acceptable bounds.
- `nonce` matches the nonce sent in the authentication request.
- `auth_time` is verified when `max_age` was requested or `auth_time` is required.
- Signing algorithm is in the registration's allowlist.

Do not simply decode the JWT and read its payload. The ID Token must go through full validation; never use an access token in place of an ID Token to identify the user.

### 11.1. Role of Spring Security OidcUserService

Spring Security provides `OidcUserService` for OIDC Login. The framework uses it to handle UserInfo when needed and return an `OidcUser`. `OidcIdTokenDecoderFactory` supplies the `JwtDecoder` used for ID Token signature verification.

When using default Spring Security OAuth2 Login, keep the framework's validation intact. If customizing the decoder, user service, or authorization request resolver, preserve issuer, audience, signature, expiry, nonce, and related checks.

### 11.2. Extracting identity from the verified ID Token

After authentication succeeds, extract:

~~~java
OidcUser oidcUser = ...; // Principal created by Spring Security after OIDC validation

OidcIdToken idToken = oidcUser.getIdToken();

String issuer = idToken.getClaimAsString(IdTokenClaimNames.ISS);
String subject = idToken.getSubject();

String email = idToken.getClaimAsString(IdTokenClaimNames.EMAIL);
Boolean emailVerified =
    idToken.getClaim(IdTokenClaimNames.EMAIL_VERIFIED);
~~~

The `issuer` and `subject` values are the identity data. `email` and `email_verified` are only optional attributes; never use them to select the local account.

## 12. Designing the external identity table

A straightforward schema:

~~~sql
CREATE TABLE external_identity (
    id                  UUID PRIMARY KEY,
    local_account_id    UUID NOT NULL,
    issuer              VARCHAR(1024) NOT NULL,
    subject             VARCHAR(255) NOT NULL,
    registration_id     VARCHAR(100) NOT NULL,
    email_snapshot      VARCHAR(320),
    email_verified      BOOLEAN,
    linked_at           TIMESTAMP NOT NULL,
    linked_by           VARCHAR(255),
    status              VARCHAR(30) NOT NULL,
    CONSTRAINT fk_external_identity_account
        FOREIGN KEY (local_account_id)
        REFERENCES local_account(id),
    CONSTRAINT uq_external_identity_issuer_subject
        UNIQUE (issuer, subject)
);

CREATE INDEX ix_external_identity_account
    ON external_identity(local_account_id);
~~~

UUID and timestamp types can be adjusted for your database. The unique constraint on `(issuer, subject)` ensures one external identity cannot be attached to two local accounts.

Both `issuer` and `subject` columns must be compared with OIDC case-sensitive semantics. Do not lowercase, trim, or canonicalize values before storing. If the database defaults to a case-insensitive collation, choose an appropriate case-sensitive collation/storage type or build a binary key from the raw values.

`registration_id` helps auditing identify which client configuration verified the identity. It does not replace issuer/subject as the federated key.

### 12.1. Store email only as a snapshot

If you need to display the linked account, you can store an email snapshot and `email_verified` flag at the time of linking. Do not use these columns to look up or identify the identity on subsequent logins.

If the user changes their email at the IdP, the identity key remains intact as long as issuer and subject do not change.

### 12.2. Enforcing the unique constraint

Do not merely call `existsByIssuerAndSubject` before inserting. Two concurrent requests can both observe "does not exist." The unique constraint is the final safeguard; the service must catch conflict errors and return a safe outcome.

## 13. Transaction service for linking identities

The service accepts only an OIDC principal verified by the framework and the local account ID obtained from the authenticated session:

~~~java
@Service
@RequiredArgsConstructor
public class AccountIdentityLinkService {

    private final ExternalIdentityRepository identities;
    private final TrustedProviderRegistry providers;
    private final AccountRepository accounts;

    @Transactional
    public LinkResult link(
            UUID localAccountId,
            String registrationId,
            OidcIdToken idToken) {

        LocalAccount account = accounts
            .findActiveById(localAccountId)
            .orElseThrow(AccountNotAvailableException::new);

        String issuer = idToken.getClaimAsString("iss");
        String subject = idToken.getSubject();

        providers.requireExpectedIssuer(registrationId, issuer);

        ExternalIdentity existing =
            identities.findByIssuerAndSubject(issuer, subject)
                .orElse(null);

        if (existing != null) {
            if (existing.getLocalAccountId().equals(localAccountId)) {
                return LinkResult.ALREADY_LINKED;
            }

            throw new IdentityAlreadyLinkedException();
        }

        ExternalIdentity identity = ExternalIdentity.link(
            localAccountId,
            issuer,
            subject,
            registrationId,
            idToken.getClaimAsString("email"),
            Boolean.TRUE.equals(
                idToken.getClaim("email_verified")));

        identities.save(identity);

        return LinkResult.LINKED;
    }
}
~~~

This is an illustrative skeleton. Domain, repository, and exception classes belong to the application.

### 13.1. Validating provider/issuer

`TrustedProviderRegistry` must map the registration ID to the configured issuer. Compare the issuer in the verified ID Token against the expected issuer of the registration. Never let the callback choose the target issuer itself.

### 13.2. Handling already-linked identities

- If the identity is already linked to the same local account, return an idempotent result.
- If the identity is already linked to another account, reject and route to a verified recovery/account merge workflow.
- Do not reveal details of the target account to unauthorized callers.
- Never automatically move an identity between two accounts solely because of a matching email.

### 13.3. Handling race conditions

When an insert hits a unique constraint violation, re-read the identity in an appropriate transaction and classify the outcome: already linked to the same account or conflicting with another account. Never swallow the database error and report linking succeeded.

If using a notification outbox, write the outbox event in the same transaction as the identity link so notifications are not lost if the process stops mid-flight.

## 14. Integrating Spring Security OAuth2 Login

Spring Security provides OAuth2 Login via the Authorization Code Flow. With OIDC, the `openid` scope causes the framework to use OIDC-specific components such as `OidcUserService`.

Configuration example:

~~~java
@Configuration
@EnableWebSecurity
@RequiredArgsConstructor
class FederatedLoginSecurityConfig {

    private final AuthenticationSuccessHandler
        accountLinkAwareSuccessHandler;

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/login/**", "/oauth2/**").permitAll()
                .requestMatchers("/account/identities/**").authenticated()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .userInfoEndpoint(userInfo -> userInfo
                    .oidcUserService(new OidcUserService()))
                .successHandler(accountLinkAwareSuccessHandler));

        return http.build();
    }
}
~~~

This is a condensed configuration. The application needs `ClientRegistrationRepository` and the corresponding OAuth2 Client components.

`OidcUserService` is used to load/normalize the OIDC principal. Persisting the link must happen in the account-linking service after confirming the right pending link transaction; avoid writing links directly inside `OidcUserService` since it also runs during normal logins.

## 15. Distinguishing login callbacks from link callbacks

An OIDC callback can serve two different intents:

- **Login:** the user wants to sign into the application using an external identity.
- **Link:** the user is already signed into a local account and wants to add an external identity to the current account.

Do not distinguish the two intents solely via a query parameter like `mode=link`. Link intent must be stored in a server-side pending transaction bound to the local account and browser session.

When the callback succeeds:

1. Spring Security verifies the authorization response and creates an OIDC Authentication.
2. The success handler looks up the pending link transaction matching the verified callback.
3. Verify the transaction is unexpired/unused and still bound to the right local session.
4. Verify the local account is still active and the user still has permission to link.
5. Invoke `AccountIdentityLinkService` with the verified ID Token.
6. Record audit/notification events.
7. Preserve or restore the local account authentication.
8. Redirect to the identity management page.

### 15.1. Do not unintentionally turn the external principal into the local account

OAuth2 Login by default creates an Authentication from the external principal. In the linking flow, the success handler must distinguish pending links from normal logins and prevent the external principal from replacing the local account session.

Pseudocode for the success handler:

~~~java
HttpSession session = request.getSession(false);

if (session != null
        && authentication instanceof OAuth2AuthenticationToken oauth2
        && oauth2.getPrincipal() instanceof OidcUser externalUser
        && pendingLinkRepository.hasValidatedCallback(request, session)) {
    PendingIdentityLink pending =
        pendingLinkRepository.consumeValidatedCallback(request, session);

    accountIdentityLinkService.link(
        pending.localAccountId(),
        pending.registrationId(),
        externalUser.getIdToken());

    localSessionRestorer.restore(
        pending.localAccountId(), request, response);
    return;
}

normalLoginSuccessHandler.onAuthenticationSuccess(
    request, response, authentication);
~~~

This is pseudocode illustrating the flow, not a copy-paste-ready class. `pendingLinkRepository` only returns a transaction after Spring Security has verified the authorization response and state/session binding. `localSessionRestorer` must reload the local principal from the account store and save the SecurityContext via `SecurityContextRepository`; never accept a principal/account ID from the browser.

You can store the local account ID and session binding in the server-side pending transaction, then reconstruct/restore the local Authentication through the application's session mechanism. If the original session was lost or the current account no longer matches the transaction, cancel linking and require the user to start over.

Never store Authentication or account IDs in browser-managed cookies without proper integrity/binding.

### 15.2. If using a separate callback

An application may design a separate callback endpoint for linking or a custom authorization request resolver/repository. Even then, you must preserve code exchange, state, PKCE, nonce, ID Token validation, issuer binding, and redirect URI validation. Never build a custom "decode JWT and insert" callback that bypasses the OIDC client pipeline.

## 16. Normal login flows must also use safe identity mapping

When a user logs in via an IdP, the application looks up the external identity by the issuer/subject pair:

- If already linked, load the corresponding local account and create a local session.
- If not found, apply the published provisioning policy.
- If the email matches another local account, do not automatically attach the identity to that account.
- If connecting to an existing profile is needed, route to account resolution/recovery with strong proof.

Never use display name, email, or username to look up a local account and treat that as login permission.

### 16.1. Just-in-time provisioning

If the product allows creating a new local account when a federated identity does not exist yet, create a new account and attach the newly verified `(iss, sub)` identity. Never use a matching email as grounds to merge into another account.

If the organization requires account pre-provisioning, there must be a trust agreement and sufficiently strong attributes to resolve the exact subscriber. NIST SP 800-63C-4 Section 3.8.2 requires RPs to ensure required attributes are sufficient to uniquely identify the subscriber and never link an account to a federated identifier that does not belong to the subscriber.

## 17. Account linking differs from account merging

**Linking** attaches an additional login method to the same local account. **Merging** transfers data, permissions, transactions, or history from two different local accounts into one account.

The two operations carry different risks. Linking a verified external identity does not prove that two local accounts share the same owner.

If merging is required, require the user to prove control over both local accounts or use an approved recovery/identity proofing workflow; clearly display the data and permissions to be transferred; check tenant/role/ownership conflicts; use an audited transaction; notify when appropriate; and preserve investigation/rollback capabilities per policy.

Never merge solely because two accounts share the same email, name, phone number, or avatar.

## 18. Preventing account pre-hijacking in signup and recovery

Account pre-hijacking often starts before the victim completes registration. A secure design requires:

- Verifying email through a dedicated workflow before using email as a recovery or critical contact channel.
- Never auto-merging local-password accounts and federated accounts based on matching emails.
- Never allowing an unverified external identity to gain permissions on an existing local account.
- When emails collide, directing the user to sign into the existing account and explicitly link the new identity.
- If the user no longer has access to the old account, using controlled recovery/identity resolution.
- Never letting a pre-created account with an unverified email automatically become the target of a federated login.
- Auditing and notifying login method changes.

If the external identity is already linked to another account, inform the caller that the identity cannot be linked. Never disclose the email, name, or status of the target account if the user is not authorized to view that information.

## 19. Unlinking, recovery, and accounts with no remaining login methods

Unlinking is also a sensitive operation. Before removing an identity:

1. Require a valid local session and re-authentication per policy.
2. Verify the identity requested for removal actually belongs to the current local account.
3. Check whether the account still has another login or recovery method.
4. If this is the last method, require adding a new method first or routing to verified recovery.
5. Delete/disable the mapping inside a transaction.
6. Reject all future logins via the removed identity.
7. Revoke associated sessions/tokens per policy.
8. Record an audit entry and send a notification.

NIST SP 800-63C-4 requires RPs to disallow access to an account via a removed federated identifier. NIST also requires notification when adding a new federated identifier or removing an identifier while the account is retained.

If an account has no remaining federated identifier, alternative authenticator, or recovery path, the application must have a clear policy. It can disable the account pending investigation/recovery or terminate it per retention policy.

## 20. Spring Authorization Server in an identity broker architecture

~~~mermaid
flowchart TB
    U[End-User]
    IDP1[Corporate OIDC IdP]
    IDP2[Consumer OIDC IdP]
    APP[Identity Broker Application]
    MAP[(Local Account + External Identity Store)]
    SAS[Spring Authorization Server]
    CLIENT[Downstream OAuth/OIDC Clients]
    API[Resource Servers]

    U --> IDP1
    U --> IDP2
    IDP1 --> APP
    IDP2 --> APP
    APP <--> MAP
    APP --> SAS
    SAS --> CLIENT
    CLIENT --> API
~~~

In this model, Spring Security OAuth2 Client authenticates the user at the upstream IdP; the account store maps the external identity to the local account; Spring Authorization Server issues internal tokens to downstream clients; Resource Servers validate internal tokens against the system's issuer, audience, and policy.

`RegisteredClient` represents an OAuth/OIDC application calling the Authorization Server. It is not a user's external identity record. Never store user account links in `RegisteredClient` or `ClientSettings`.

### 20.1. Subject of internal tokens

Downstream clients should receive a stable local subject of the system, such as an opaque local account ID. Never use email or upstream `sub` as the internal subject if you want users to be able to link multiple IdPs without changing their identity across downstream applications.

When a user links another IdP, the local account does not change; therefore, the internal subject does not need to change either. Do not broadcast upstream issuer/subject if downstream clients have no need or authorization to receive that data.

### 20.2. Authorization does not rely solely on linked identities

The fact that an IdP is linked only proves a login method attached to the account. It does not inherently grant roles, tenant memberships, or admin rights from the IdP's claims.

Apply separate policies for external groups, organizations, domains, and roles. Map claims only after verifying the issuer, audience, claim source, and trust agreement.

## 21. Controlling authorization requests and re-authentication at the IdP

Where supported by the provider, the application can request fresh authentication using OIDC parameters such as:

- `prompt=login` to ask the OP to repeat the login step.
- `max_age` to limit the age of the authentication; when used, the RP must verify `auth_time` in the ID Token.
- `acr_values` to request an appropriate authentication context if supported by the IdP with agreed semantics.

These are requests sent to the IdP; compliance depends on the OP. Do not treat adding `prompt=login` alone as sufficient if the IdP does not re-verify the authenticator or if policy requires specific MFA.

For the local account, re-authentication with an existing authenticator remains a separate control layer. If the provider does not support step-up, the application must use another local method or reject linking per risk policy.

## 22. Testing account linking and takeover resistance

### 22.1. Identity tests

| Scenario | Expected outcome |
|---|---|
| Same issuer + subject | Resolves same external identity |
| Same subject, different issuer | Two distinct external identities |
| Same email, different issuer/subject | Does not auto-link |
| email_verified=false | Does not affect identity key |
| Email changes, issuer/subject unchanged | Still resolves right local account |
| Subject already linked to another account | Rejects link, does not merge |
| Different pairwise subject due to registration/sector | Does not assume same identity |

### 22.2. OIDC transaction tests

- Invalid, missing, or replayed state.
- Invalid or already-used nonce.
- Mismatched PKCE verifier.
- ID Token with invalid signature or disallowed algorithm.
- Issuer does not match registration.
- Audience does not contain client_id.
- Expired ID Token.
- Auth time too old when max_age is requested.
- Callback from a different registration.
- Tampered Redirect URI or issuer.
- Expired pending link or mismatched session binding.

### 22.3. Local account and session tests

- Unauthenticated user calls link endpoint.
- Missing or invalid CSRF token.
- Session switched accounts after starting linking.
- User logs out before callback.
- Local account locked during redirect.
- Link callback without a pending transaction.
- External login callback submitted into link flow.
- Re-authentication fails.
- Session fixation protection and session rotation after sensitive operations.

### 22.4. Persistence and concurrency tests

- Two requests concurrently link the same identity to the same account.
- Two different accounts concurrently link the same issuer/subject.
- Identity already exists on the same account (idempotent).
- Identity already exists on another account (conflict).
- Database unique constraint triggers properly.
- Notification outbox rolls back in the same transaction when insert fails.
- Unlink concurrent with login.
- Login after unlink must be rejected.

### 22.5. Account pre-hijacking tests

Simulate the scenario:

1. Attacker creates a local account using the victim's email without proving ownership.
2. Victim logs in with an IdP having the same email.
3. System must not auto-merge.
4. Victim must log in/recover the local account through an appropriate workflow before linking the IdP.
5. Attacker must not retain any login method into the account after the victim completes verification.

## 23. Auditing, notifications, and observability

Events to record:

~~~text
IDENTITY_LINK_STARTED
IDENTITY_LINK_REAUTH_REQUIRED
IDENTITY_LINK_VALIDATION_FAILED
IDENTITY_LINK_CREATED
IDENTITY_LINK_ALREADY_EXISTS
IDENTITY_LINK_CONFLICT
IDENTITY_LINK_EXPIRED
IDENTITY_UNLINK_STARTED
IDENTITY_UNLINKED
IDENTITY_LOGIN_SUCCEEDED
IDENTITY_LOGIN_REJECTED
ACCOUNT_RECOVERY_REQUIRED
~~~

Audit records should include local account ID, registration ID, issuer, subject fingerprint/hash if minimizing identifier exposure, correlation ID, transaction ID, timestamp, outcome, and re-auth level achieved.

Never log raw ID Tokens, access tokens, refresh tokens, client secrets, or session cookies. Email snapshots must also follow PII policies.

### 23.1. Notifications

Notify the user when an identity is added or removed. The message should state which provider was added/removed, timestamp, device/session if available, actions to take if the user did not perform it, and trusted recovery/support channels.

Notifications must never contain tokens, authorization codes, or direct login links.

### 23.2. Metrics

Monitor link successes/failures per registration ID, conflicts where an identity already belongs to another account, state/nonce/issuer/audience validation failures, link attempts without re-auth, unlink attempts when no alternative method remains, account recovery after conflict, and unique constraint/transaction rollback errors.

Never use email, subject, or account ID as high-cardinality metric labels.

## 24. Common implementation mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using email as the federated key | Wrong person linked or account takeover | Use exact issuer + subject |
| Auto-merging when email_verified=true | Attacker can retain login access to account | Require local session and re-authentication |
| Linking without logging into local account | Attacker can choose target account | Take account from authenticated principal |
| Using account_id in query to link | Target account altered via tampering | Store target account server-side |
| Skipping state/nonce/PKCE checks | Callback injection and replay | Preserve OIDC transaction binding |
| Trusting issuer from browser/JWT header | Issuer confusion | Use provider allowlist and trusted discovery |
| Linking inside OidcUserService for all logins | Normal logins can unintentionally alter account mappings | Perform linking in dedicated flow/success handler |
| Link callback replacing local Authentication | User switched accounts or lost context | Restore local principal after linking |
| Checking exists before inserting without constraint | Race condition | Unique constraint and transaction |
| Linking identity already owned by another account | One identity accesses multiple accounts | Reject and route to recovery/merge |
| Unlinking the last login method | Account accidentally locked out | Require alternative method/recovery |
| Not notifying on link/unlink | User fails to notice takeover | Auditing and notifications |
| Putting upstream sub into internal token | Leaks IdP identifier and complicates provider changes | Use stable local subject |
| Trusting group/role claims directly | Privilege escalation | Map via trust policy |

## 25. Production checklist

### Account and identity model

- [ ] Local account and external identity are separate entities.
- [ ] OIDC identity key is the exact `(iss, sub)` pair.
- [ ] Subject is treated as an opaque identifier.
- [ ] Never use email, username, name, or phone as the federated key.
- [ ] Email and email_verified are only profile snapshots.
- [ ] Unique constraint exists on issuer/subject.
- [ ] Index exists to look up identities by local account.
- [ ] Pairwise subjects and multiple registrations have been accounted for.

### Link flow

- [ ] Linking starts only from an authenticated local session.
- [ ] Link initiation endpoint uses POST and CSRF protection.
- [ ] Re-authentication/step-up is enforced per risk policy.
- [ ] Providers and issuers are in an allowlist.
- [ ] Pending transaction binds local account, browser session, and registration.
- [ ] State, nonce, and PKCE are per-transaction and single-use.
- [ ] Callback uses only the verified OIDC pipeline.
- [ ] ID Token issuer, audience, signature, expiry, and nonce are validated.
- [ ] Auth time is checked if max_age is requested.
- [ ] Callback does not overwrite local account Authentication.
- [ ] Link service accepts identities only from a verified OIDC principal.

### Persistence and account lifecycle

- [ ] Link is written inside a transaction.
- [ ] Race conditions are prevented by a unique constraint.
- [ ] Identities already belonging to another account are rejected.
- [ ] Account merging has a dedicated verification workflow.
- [ ] Unlinking disables login access for the removed identity.
- [ ] Unlinking the last method is disallowed without recovery.
- [ ] Proper auditing, notifications, and outbox exist.
- [ ] Account recovery exists for losing all access methods.

### Spring and Authorization Server

- [ ] Spring Security OAuth2 Client uses OIDC Login for upstream IdPs.
- [ ] OidcUserService only loads/normalizes the principal; domain service decides linking.
- [ ] OAuth2 success handler distinguishes login from server-side link intent.
- [ ] Spring Authorization Server issues tokens based on the local principal.
- [ ] RegisteredClient is not used to store user identity links.
- [ ] Internal token subject is stable, not using email/upstream subject.
- [ ] Downstream roles/claims are mapped according to a dedicated policy.

### Testing and operations

- [ ] Tests exist for email collisions and account pre-hijacking.
- [ ] Tests exist for state/nonce/PKCE and issuer mix-up.
- [ ] Tests exist for wrong audience, signature, and expired tokens.
- [ ] Tests exist for session swapping and callback replay.
- [ ] Concurrency tests exist for the same external identity.
- [ ] Tests exist for unlinking and login after unlink.
- [ ] Metrics, audits, alerts, and runbooks exist.
- [ ] Logs contain no tokens, session cookies, or raw credentials.

### Core takeaways

Account linking is the operation of attaching an additional federated identifier to a local account. With OIDC, the identity key must be the verified **issuer and subject** pair. Email, including `email_verified`, is not sufficient proof to automatically merge two accounts.

The user must have an authenticated session with the local account and should re-authenticate with an existing method before linking. The OIDC callback must be bound to the transaction and browser session, and only then is the ID Token used to extract issuer/subject. The database needs unique constraints and transactions to prevent race conditions or one external identity being attached to multiple accounts.

In Spring Security, OAuth2 Client/OIDC Login handles upstream authentication; the account-linking service is responsible for deciding mappings; Spring Authorization Server can issue downstream tokens based on the local account principal. Separating these three responsibilities prevents external logins from accidentally replacing local sessions or granting access to the wrong account. Linking, unlinking, and recovery all require auditing, notifications, and account takeover testing.

## References

- [OpenID Connect Core 1.0 incorporating errata set 2 — ID Token Validation](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation)
- [OpenID Connect Core 1.0 incorporating errata set 2 — Claim Stability and Uniqueness](https://openid.net/specs/openid-connect-core-1_0.html#ClaimStability)
- [NIST SP 800-63C-4 — Digital Identity Guidelines: Federation and Assertions](https://pages.nist.gov/800-63-4/sp800-63c.html)
- [NIST SP 800-63C-4 — Section 3.8.1 Account Linking](https://pages.nist.gov/800-63-4/sp800-63c.html#sec-account-linking)
- [OWASP Authentication Cheat Sheet — Secure Federated Account Linking](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#secure-federated-account-linking)
- [OWASP Authentication Cheat Sheet — Require Re-authentication for Sensitive Features](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#reauthentication)
- [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html)
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security — Advanced OAuth2 Login Configuration and OidcUserService](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Sudhodanan and Paverd — Pre-hijacked Accounts, USENIX Security 2022](https://www.usenix.org/conference/usenixsecurity22/presentation/sudhodanan)
