# OAuth2AuthorizationConsentService and the consent lifecycle

## 1. What is consent and why does the Authorization Server store it?

In an **OAuth 2.0/OpenID Connect (OIDC) Authorization Server** built with **Spring Security** and **Spring Authorization Server** on Spring Boot, **consent** (authorization approval) is the user's decision allowing a **client** to perform specific access scopes on their behalf within the boundaries of system policy.

For example: Alice logs in to the Authorization Server, and the <code>orders-web</code> application requests the scopes <code>orders.read</code> and <code>orders.write</code>. On the consent screen, Alice approves only <code>orders.read</code>. The server must remember Alice's valid choice for that specific client, while ensuring subsequent tokens do not contain <code>orders.write</code> merely because the client asked for it.

<code>OAuth2AuthorizationConsentService</code> is Spring Authorization Server's **contract for persisting and retrieving consent decisions**. It works alongside the <code>OAuth2AuthorizationConsent</code> model and the authorization workflow, rather than authenticating users or issuing tokens on its own.

After this lesson, you will be able to:

1. Distinguish **authentication**, **authorization**, **consent**, and token issuance.
2. Understand the data stored in <code>OAuth2AuthorizationConsent</code>, its composite key, and the three operations of <code>OAuth2AuthorizationConsentService</code>.
3. Describe the consent lifecycle from initial request, per-scope approval, reuse, scope expansion, and revocation through re-granting.
4. Configure an in-memory/JDBC service in Spring Boot; know which parts are for demos and which are production requirements.
5. Design a secure consent screen and revocation workflow that prevents consent spoofing.
6. Test consent separately from access token/refresh token revocation workflows.

### 1.1. Which questions does consent answer?

| Concept | Question | Example |
| --- | --- | --- |
| **Authentication** | Who is logged in? | User Alice is authenticated. |
| **Client registration** | Which permissions is the app registered to request? | <code>orders-web</code> is registered for <code>orders.read</code>, <code>orders.write</code>. |
| **Consent** | Which permissions did Alice approve for that client? | Alice approved <code>orders.read</code>. |
| **Authorization policy** | Does current policy permit this request? | Is Alice's account restricted or locked? |
| **Token issuance** | What permissions, for whom, and when does the server actually issue a token? | Access token holds only <code>orders.read</code>, audience Orders API. |
| **Resource authorization** | May Alice access a specific record? | Alice can read order 123 but cannot read Bob's order. |

Consent is **not** a form of login, does not prove a user owns every object, and does not replace scope enforcement policies on the Authorization Server or Resource Server.

## 2. Where ConsentService sits in the architecture

~~~mermaid
flowchart LR
    U["End-User: Alice"] --> B["Authorization endpoint / consent UI"]
    C["OAuth Client: orders-web"] --> B
    B --> P["Authorization Code request processing"]
    P --> RC["RegisteredClientRepository"]
    P <--> CS["OAuth2AuthorizationConsentService"]
    CS <--> DB["Consent storage"]
    P <--> AS["OAuth2AuthorizationService"]
    P --> T["Token issuance"]
    T --> API["Resource Server"]
~~~

Core models/components:

| Component | Contents and responsibility |
| --- | --- |
| <code>RegisteredClient</code> | Defines the client, authentication methods, grants, redirect URIs, requestable scopes, and <code>ClientSettings</code>. |
| <code>OAuth2AuthorizationConsent</code> | Consent record for **one principal and one registered client**, containing approved authorities. |
| <code>OAuth2AuthorizationConsentService</code> | Interface for retrieving, saving, and removing consent records. |
| <code>OAuth2Authorization</code> | State of an authorization/grant along with its tokens, metadata, and related info. |
| <code>OAuth2AuthorizationService</code> | Saves, finds, and updates authorization/token state; separate from storing consent. |
| <code>OAuth2AuthorizationServerConfigurer</code> | Registers filters/providers handling OAuth 2.0/OIDC endpoints; coordinates client, user, and consent checks. |

Most importantly: **the consent record remembers approval decisions**, whereas <code>OAuth2AuthorizationService</code> stores the state of issued authorizations/tokens. Both stores may share a database, yet **they must not be treated as a single table or a single revocation operation**.

## 3. The <code>OAuth2AuthorizationConsent</code> model

### 3.1. Three core data fields

The <code>OAuth2AuthorizationConsent</code> model stores:

1. <code>registeredClientId</code>: **internal ID of the <code>RegisteredClient</code>**, obtained via <code>registeredClient.getId()</code>. It differs from <code>registeredClient.getClientId()</code> used in OAuth requests.
2. <code>principalName</code>: principal name used by Spring Authorization Server to identify the consenting user/subject.
3. <code>authorities</code>: set of <code>GrantedAuthority</code> approved for the client–principal pair.

Example representation of a record:

~~~text
registeredClientId = "client-record-8f3c"
principalName      = "user-42"
authorities        = {"SCOPE_orders.read", "SCOPE_profile"}
~~~

<code>OAuth2AuthorizationConsent</code> does **not** hold access tokens, refresh tokens, login sessions, or user passwords. Nor is it an audit log of every button click on every request; normally it represents the **current consent state** of a client–principal pair.

### 3.2. Why do authorities have the <code>SCOPE_...</code> form?

Spring Security represents permissions as <code>GrantedAuthority</code>. In the consent model, approved scopes are typically mapped to authorities prefixed with <code>SCOPE_</code>:

~~~java
OAuth2AuthorizationConsent consent = OAuth2AuthorizationConsent
    .withId(registeredClient.getId(), principalName)
    .authority(new SimpleGrantedAuthority("SCOPE_orders.read"))
    .authority(new SimpleGrantedAuthority("SCOPE_profile"))
    .build();
~~~

This illustrates **how the record is structured**, not advice to call <code>save()</code> yourself to grant permissions without going through the consent workflow. Every recorded authority must originate from a server-verified user/policy decision.

Distinguish three things:

| Data | Example | Meaning |
| --- | --- | --- |
| Client requested scopes | <code>orders.read orders.write</code> | What is desired in the authorization request. |
| Client registered scopes | <code>orders.read</code>, <code>orders.write</code> | Upper bound permitted by <code>RegisteredClient</code>. |
| Persisted consent authority | <code>SCOPE_orders.read</code> | Permission the user approved in that client's context. |

A <code>GrantedAuthority</code> in consent is **not necessarily a user role** such as <code>ROLE_ADMIN</code>. Never copy roles from <code>Authentication.getAuthorities()</code> verbatim into consent; use the exact authority types expected by the authorization workflow.

### 3.3. The client–principal pair key

When retrieving a record, the API takes two parameters:

~~~java
OAuth2AuthorizationConsent existing =
    consentService.findById(registeredClient.getId(), principalName);
~~~

This has important consequences:

- Alice consenting to <code>orders-web</code> **does not mean** Alice consented to <code>billing-web</code>.
- Alice consenting to <code>orders-web</code> **does not mean** Bob is also considered to have consented.
- Passing <code>clientId</code> instead of <code>registeredClient.getId()</code> can cause wrong lookups, leading to repeated consent prompts or deleting the wrong record if identifiers collide.
- In multi-tenant systems, <code>principalName</code> must have a naming rule stable and collision-free across tenants/users; in the default schema, tenant is typically **not** a separate key column.

Never take <code>principalName</code> from a user-supplied query parameter during consent view/delete operations. Derive it from a trusted authentication session and enforce authorization checks.

## 4. API of <code>OAuth2AuthorizationConsentService</code>

The primary interface defines three operations:

~~~java
public interface OAuth2AuthorizationConsentService {
    void save(OAuth2AuthorizationConsent authorizationConsent);
    void remove(OAuth2AuthorizationConsent authorizationConsent);
    OAuth2AuthorizationConsent findById(
        String registeredClientId, String principalName);
}
~~~

| Method | Meaning | Common scenario |
| --- | --- | --- |
| <code>findById(clientRecordId, principalName)</code> | Looks up consent for a client–principal pair; returns <code>null</code> if none exists. | Before deciding whether to display consent. |
| <code>save(consent)</code> | Persists consent state (inserts or updates per implementation). | User completes a valid approval step. |
| <code>remove(consent)</code> | Deletes the consent record. | User withdraws stored approval or policy requires deletion. |

In default implementations, lookups are optimized for **one specific key pair**. This interface **has no standard <code>findAllByPrincipalName()</code> method**. If building a "Connected Applications" screen, design a suitable supplementary query layer or dedicated repository to list a user's consents.

### 4.1. Reading and interpreting approved scopes

Example in a service using **trusted** backend objects:

~~~java
public Set<String> findConsentedScopes(
        RegisteredClient registeredClient,
        String authenticatedPrincipalName,
        OAuth2AuthorizationConsentService consentService) {

    OAuth2AuthorizationConsent consent = consentService.findById(
        registeredClient.getId(), authenticatedPrincipalName);

    if (consent == null) {
        return Set.of();
    }

    return consent.getAuthorities().stream()
        .map(GrantedAuthority::getAuthority)
        .filter(authority -> authority.startsWith("SCOPE_"))
        .map(authority -> authority.substring("SCOPE_".length()))
        .collect(Collectors.toUnmodifiableSet());
}
~~~

This snippet returns **scopes stored in authority format**, without yet reconciling them against **currently** allowed scopes, account state, organizational policies, or the current OAuth request. When deciding token issuance, the server must constrain permissions across **all** applicable conditions. Never use a standalone <code>findById()</code> result to bypass those checks.

### 4.2. Deleting a consent record

~~~java
OAuth2AuthorizationConsent existing =
    consentService.findById(
        registeredClient.getId(), authenticatedPrincipalName);

if (existing != null) {
    consentService.remove(existing);
}
~~~

This is a **service-layer operation performed after authentication and ownership verification**. It must not be exposed directly as an endpoint like <code>DELETE /consents?principalName=alice</code> that trusts client-supplied data.

In particular, **deleting consent does not automatically invalidate already-issued access tokens/refresh tokens**. Section 8 analyzes the consequences and how to design a "Disconnect Application" feature.

## 5. Consent lifecycle in Authorization Code Flow

In an Authorization Code + PKCE flow, consent is a **decision step** after the server has verified the user, client, and authorization request context. It may not need to be displayed again if permissions were previously approved or client/server policy does not require it.

~~~mermaid
flowchart TD
    A["Client requests /oauth2/authorize with scopes"] --> B{"Valid client / redirect URI / grant / scopes?"}
    B -- No --> X["Reject per protocol"]
    B -- Yes --> C{"End-User authenticated?"}
    C -- No --> LOGIN["Log user in"] --> C
    C -- Yes --> D["Read consent by registeredClientId + principalName"]
    D --> E{"Is new or additional consent needed?"}
    E -- No --> F["Proceed with authorization per policy"]
    E -- Yes --> G["Display application and requested scopes"]
    G --> H{"Does user approve?"}
    H -- No --> DENY["Do not grant denied permissions; handle error per flow"]
    H -- Yes --> I["Verify and persist valid consent"]
    I --> F
    F --> CODE["Authorization code / token per grant"]
~~~

The condition "is consent needed" depends on <code>ClientSettings.requireAuthorizationConsent</code>, the request, stored consent, relevant scopes, and specific version/configuration. The diagram shows conceptual logic; do not interpret it as the exact execution order of every filter/provider across all versions.

### 5.1. First-time authorization

Suppose:

~~~text
Client: orders-web
Requested scopes: openid orders.read
Registered scopes: openid orders.read orders.write
Principal: user-42
Previous consent: none
requireAuthorizationConsent: true
~~~

Once the user logs in, the Authorization Server checks whether consent is needed. If so, the screen explains that <code>orders-web</code> wants to read orders. When Alice confirms, the service saves the approved permissions accordingly. Only after all other checks succeed does the server return an authorization code and allow the client to exchange it for tokens per protocol.

**Consent is an input condition, not an immediate command to mint tokens.** Having a record in the database does not allow a client to skip redirect URI, authentication, authorization code, or PKCE checks.

### 5.2. Returning with the same approved scopes

On the next authorization request for the same client and principal, the server looks up prior consent. If the requested scopes are already covered and policy allows reuse, the user may **not have to re-approve consent**.

Never assume "once consent exists, the user will never see the consent screen again": the server may require fresh consent due to policy, protocol rules, applicable OIDC parameters, or record revocation. Re-authenticating the user is also a separate decision from reusing consent.

### 5.3. Client requests additional scopes

Initially Alice approved:

~~~text
{"SCOPE_orders.read"}
~~~

After an upgrade, the client requests:

~~~text
orders.read orders.write
~~~

If the client is registered for <code>orders.write</code> and user/policy permits granting it, the Authorization Server must check the permissions **not yet approved**. It must not treat prior consent for <code>orders.read</code> as implicit approval for <code>orders.write</code>.

An implementation may display only the new scopes or summarize all requested scopes so the user clearly understands. If Alice declines the new permission, the server must handle the result per policy and protocol specification; **never add unapproved scopes to consent automatically**.

### 5.4. User denies

Clicking "Deny" must not create a new grant record. In Authorization Code Flow, the system normally returns an appropriate protocol error such as <code>access_denied</code> to the client following verified redirect rules.

Details that must be verified carefully:

- Never redirect to an arbitrary unverified <code>redirect_uri</code>.
- Never include sensitive information in protocol error responses.
- Never alter an existing consent record because a single request was denied, unless the product has a **separate, authenticated** revocation flow.
- Never issue tokens carrying unapproved permissions.

### 5.5. Withdrawing consent and re-granting later

The user chooses "Disconnect" in the connected-applications management section. The backend resolves the currently logged-in principal, target client, and existing record; then removes consent or updates state per the storage model. The next authorization request may prompt for fresh consent according to policy.

Any still-valid tokens must be handled **separately**. If the goal is immediate cutoff, add token revocation/control mechanisms rather than stopping at deleting the consent row.

## 6. How consent differs from authorization codes, refresh tokens, and login

To avoid design bugs, separate at least four lifecycles:

| Object | Created / when | Stored where | When it expires or is deleted |
| --- | --- | --- | --- |
| End-User login session | When user authenticates | Security context/session or equivalent infrastructure | Logout, expiration, or session policy |
| **Consent** | When user approves scopes for a client | <code>OAuth2AuthorizationConsentService</code> | Consent withdrawal, client/user deletion, or storage policy |
| Authorization code | After authorization request is approved | <code>OAuth2AuthorizationService</code> | Expiration, single use, or invalidation |
| Access token / refresh token | When token endpoint issues them | Token-type metadata/state and <code>OAuth2AuthorizationService</code> | Expiration, revocation, and related token controls |

A user can:

- **Still be logged in** while having revoked consent for a client.
- **Have logged out** while the consent record remains, avoiding re-prompting after the next login.
- **Still have consent** while the refresh token has expired or been revoked.
- **Have deleted consent** while an old JWT access token remains valid until expiry, if the Resource Server only checks signature/time without a revocation mechanism.

Consent normally relates to **End-User approval in user-facing flows**, typically Authorization Code. With **Client Credentials**, the client acts under its own application identity and there is no End-User in front of a consent screen; do not design an end-user consent UI as a default step for this grant. Client permissions must be governed through client registration, scopes, policies, and client authentication.

In OIDC, <code>openid</code>, <code>profile</code>, and <code>email</code> express authentication/identity claim requests. They follow their own consent/claim rules depending on provider configuration; **do not assume every OIDC scope is stored and displayed like a custom API scope**, and do not assert that consenting to <code>email</code> guarantees the ID Token always contains the <code>email</code> claim.

## 7. Configuring the service with Spring Authorization Server

### 7.1. Enabling consent requirement on RegisteredClient

<code>requireAuthorizationConsent(true)</code> is a setting on the **client**, not a global property of <code>OAuth2AuthorizationConsentService</code>.

~~~java
RegisteredClient ordersWeb = RegisteredClient.withId("orders-web-record-001")
    .clientId("orders-web")
    .clientSecret(encodedSecret)
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
    .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
    .redirectUri("https://orders.example.com/login/oauth2/code/orders-web")
    .scope(OidcScopes.OPENID)
    .scope("orders.read")
    .scope("orders.write")
    .clientSettings(ClientSettings.builder()
        .requireAuthorizationConsent(true)
        .build())
    .build();
~~~

The example uses a **confidential server-side web client** with a client secret encoded by an appropriate <code>PasswordEncoder</code>. Never put raw secrets in source code; if using a public client, configure appropriate client authentication and PKCE. <code>requireAuthorizationConsent</code> enables the corresponding consent policy; **it does not mean every request is guaranteed to show the consent page again**.

### 7.2. In-memory service for examples and experiments

~~~java
@Bean
OAuth2AuthorizationConsentService authorizationConsentService() {
    return new InMemoryOAuth2AuthorizationConsentService();
}
~~~

This option is easy to learn with and requires no database, but has limits:

- Restarts wipe in-memory consent records.
- Independent instances can observe different consents.
- Does not satisfy production requirements for data governance, backups, querying, or auditing.
- Should not be treated as durable authorization state storage in real systems.

### 7.3. JDBC service for durable consent persistence

Spring Authorization Server provides <code>JdbcOAuth2AuthorizationConsentService</code>:

~~~java
@Bean
OAuth2AuthorizationConsentService authorizationConsentService(
        JdbcTemplate jdbcTemplate,
        RegisteredClientRepository registeredClientRepository) {

    return new JdbcOAuth2AuthorizationConsentService(
        jdbcTemplate, registeredClientRepository);
}
~~~

With the standard JDBC implementation, prepare the schema supplied/compatible with **the Spring Authorization Server version in use**. The structure is typically based on the <code>oauth2_authorization_consent</code> table with columns:

| Column | Role |
| --- | --- |
| <code>registered_client_id</code> | Registered client record key. |
| <code>principal_name</code> | Approving principal. |
| <code>authorities</code> | Set of authorities serialized per the storage mechanism. |

The pair <code>(registered_client_id, principal_name)</code> is typically the **primary/unique key**, so each pair has one current consent state. Do not invent tables and column types by guessing; use the DDL/schema accompanying your exact version, controlled migrations, and tests against your real database engine.

**Simply swapping the service bean does not make a system production-ready.** The Authorization Server also needs client, authorization/token, and consent stores, transaction config, signing keys, and consistent backup/migration policies. Across multiple instances, they must share required state plus compatible issuers and keys.

### 7.4. When using Spring Boot auto-configuration

Depending on the Spring Boot version and declared beans, the system may provide default implementations. When an application **explicitly declares** an <code>OAuth2AuthorizationConsentService</code> bean, corresponding auto-configuration may skip creating its default bean due to <code>@ConditionalOnMissingBean</code> or similar mechanisms.

Verify actual runtime beans when moving from a demo to JDBC. Do not expect the framework to supply an in-memory service while also registering a custom service and assuming all endpoints share the same store. Boot namespaces for the authorization server and OAuth2 Client/Resource Server do not replace the Authorization Server's core model services.

## 8. Does revoking consent revoke access tokens?

**Never treat <code>consentService.remove(consent)</code> as an operation that revokes all tokens.** Consent and tokens live in different lifecycles and storage layers.

### 8.1. Two independent decisions

A "Disconnect Application" action often carries two product requirements:

1. **Stop reusing old consent for future authorizations:** delete/update consent; next time, consent must be evaluated again per policy.
2. **Block existing access as soon as possible:** revoke authorizations, refresh tokens, and/or access tokens depending on design and what each token type supports.

A self-contained JWT may still be accepted by Resource Servers as long as its signature, issuer, audience, <code>exp</code>, and other checks remain valid; deleting a consent row in the database **does not erase old JWT payloads**.

| Token type / mechanism | Effect of deleting consent | What is needed if early cutoff is required |
| --- | --- | --- |
| JWT access token, offline validation | Issued tokens may remain valid until <code>exp</code>. | Short-lived access tokens; denylist/revocation or centralized status checks when needed. |
| Reference/opaque token with introspection | Deleting consent alone does not automatically alter token state. | Revoke tokens/authorizations in the store queried by introspection. |
| Refresh token | Must not be assumed deleted along with consent. | Revoke refresh tokens and related authorizations per policy. |
| New authorization requests | Old consent is no longer available for reuse. | Reapply policy and prompt for consent when appropriate. |

RFC 7009 defines per-token revocation at the revocation endpoint; it does not automatically provide a universal "delete all tokens of a user for a client" operation. If full disconnection is required, design queries for related authorizations, revocation transactions, race handling with refresh tokens, auditing, and multi-instance consistency.

### 8.2. Safe "Disconnect" workflow pattern

~~~mermaid
sequenceDiagram
    participant U as User
    participant UI as Connected Applications page
    participant S as Consent management backend
    participant CS as ConsentService
    participant AS as AuthorizationService / token controls
    U->>UI: Click disconnect orders-web
    UI->>S: POST /account/consents/revoke (+ CSRF)
    S->>S: Verify session, get principal, authorize action
    S->>CS: findById(registeredClientId, principalName)
    S->>CS: remove(consent) if present
    S->>AS: Revoke tokens/authorizations per policy if required
    S-->>UI: Disconnect state applied
~~~

This is an illustrative **business design**, not an endpoint pre-built by Spring Authorization Server. The consent management UI must be built and secured separately. Ordering of save/delete/token-revocation steps must be coordinated so you do not report success halfway through when full disconnection was required.

### 8.3. Asynchronous scenarios and race conditions

Suppose Alice clicks "Disconnect" at the exact moment <code>orders-web</code> is exchanging a refresh token. If the implementation only deletes consent, the refresh request may still succeed. If token revocation is also implemented, account for write contention, transaction consistency, idempotent repeat revocations, and safe retries. Across multiple databases/external systems, atomicity may be limited; clearly define eventual state, reconciliation, and monitoring.

Never promise "instant revocation across all APIs" when the architecture still relies on offline-validated JWTs that do not check revocation state.

## 9. Designing a secure, clear consent screen

Spring Authorization Server lets you customize the consent UI/flow via hooks/configurers available in your version. The consent screen is **especially sensitive**: every piece of content and every parameter displayed or submitted must come from validated data.

### 9.1. What to display

The screen can present:

- **Registered application name** and client identifier so the user knows who they are granting permissions to. Avoid rendering an unverified display name parameter sent by the client in the request.
- **List of scopes** with clear descriptions: <code>orders.read</code> → "View orders you are permitted to access"; <code>orders.write</code> → "Create or update orders within your allowed scope".
- Clear distinction between previously granted permissions and **newly requested** permissions.
- Clear **Approve** and **Deny** buttons without pre-checked boxes designed to mislead users.
- Information on how to revoke permissions and how granted permissions are handled.

Never describe <code>orders.read</code> as "View all orders in the system" if the Resource Server still enforces ownership and tenant checks. Scope descriptions must accurately reflect real API policies.

### 9.2. Mandatory logic controls

The **set of approvable permissions** must be derived from:

~~~text
requested scopes
∩ valid scopes in RegisteredClient
∩ principal's current permissions/policies
∩ authorization flow constraints
~~~

This is a conceptual model; exact permission details also depend on standard OAuth2/OIDC configuration. If a form submits an <code>admin</code> scope or a client ID differing from the original request, the server must **reject** it rather than trusting the form.

Recommended layers of defense:

1. Authenticate the user via a valid session and bind the consent response to the pending **authorization request**.
2. Protect browser POST requests against **CSRF**, and address clickjacking/XSS/HTML escaping.
3. Validate <code>state</code>, client, redirect URI, and integrity of authorization data per protocol rules.
4. Keep access tokens, refresh tokens, client secrets, and authorization codes out of URLs and HTML outside their designed protocol usage.
5. Record appropriate audit metadata (who, which client, which scopes, timestamp, decision source) without logging credentials or raw tokens.
6. For consent-management endpoints, derive the acting subject from trusted authentication; never let users supply an arbitrary <code>principalName</code>.

**The consent UI is not where a client grants itself permissions.** All permissions from the form must be re-validated on the server before calling the persistence service.

## 10. Multi-tenancy, client changes, and data requirements

### 10.1. Preventing <code>principalName</code> collisions across tenants

A multi-tenant organization may have two users named <code>alice</code>, or a user's email/username may be reassigned. Using the bare string <code>alice</code> as the principal key across all tenants in the same consent store can accidentally reuse records across distinct entities.

Solutions depend on architecture, for example:

- Use a **stable, immutable** user ID scoped across the issuer, distinguishing tenants where needed.
- Map the authenticated principal name via controlled rules; never derive it from mutable emails or raw request parameters.
- For multiple issuers/tenants or differing consent models, design explicit namespaces and schemas rather than cramming tenant data into an unstructured string.

### 10.2. Changing client ID or registered scopes

<code>OAuth2AuthorizationConsent</code> references the **registered client record ID**, not the protocol client ID. If you delete and recreate a <code>RegisteredClient</code> with a new record ID, old consents will not automatically link to the new record, even if the OAuth <code>clientId</code> looks identical.

When modifying client registrations:

| Change | What to check |
| --- | --- |
| Adding a new scope | The client must be allowed to request it, and fresh consent must be handled appropriately. |
| Removing a scope from a client | Never issue tokens with a removed scope just because an old consent record still exists. |
| Changing <code>registeredClient.getId()</code> | Plan migration/cleanup for consents referencing the old ID. |
| Deleting a client completely | Handle orphaned consents, authorizations/tokens, and audit data per policy. |
| Switching tenants or changing principal identifiers | Prevent reusing consents that do not belong to the same subject. |

For transparency and traceability, never silently "upgrade" old consent permissions when changing what a scope means. For instance, changing <code>orders.read</code> from "read my own orders" to "read orders for the entire organization" is a policy and UX change requiring review of permissions, consents, and published disclosures.

### 10.3. Retention and auditing

Because consent represents a user–application relationship, it may carry dedicated data-protection requirements. Define retention/deletion policies when an account is deleted, a client is decommissioned, or a contract ends. **Consent history** (audit trail) and **current consent state** are two different datasets: if you need to prove who approved what and when, maintain a controlled audit log rather than expecting the current-state table to preserve history.

## 11. Testing the service and full lifecycle

### 11.1. API testing with the in-memory service

JUnit + AssertJ example verifying the client–principal pair key and save/remove operations:

~~~java
@Test
void consentIsScopedByRegisteredClientAndPrincipal() {
    OAuth2AuthorizationConsentService service =
        new InMemoryOAuth2AuthorizationConsentService();

    OAuth2AuthorizationConsent aliceOrders =
        OAuth2AuthorizationConsent
            .withId("orders-client-record", "alice-id")
            .authority(new SimpleGrantedAuthority("SCOPE_orders.read"))
            .build();

    service.save(aliceOrders);

    assertThat(service.findById("orders-client-record", "alice-id"))
        .isNotNull();
    assertThat(service.findById("orders-client-record", "bob-id"))
        .isNull();
    assertThat(service.findById("billing-client-record", "alice-id"))
        .isNull();

    service.remove(aliceOrders);

    assertThat(service.findById("orders-client-record", "alice-id"))
        .isNull();
}
~~~

This test verifies the **storage contract**, not the consent screen, grant validation, or revocation. In production, add equivalent tests against real JDBC/databases covering create/update/delete, transactions, and race conditions when concurrent requests update consent.

### 11.2. Integration test matrix

| Scenario | Expected outcome |
| --- | --- |
| Client A has no prior consent, requests valid scope | Displays/applies consent step per client/server policy. |
| User approves a subset of valid scopes | Consent record reflects approved permissions; issued tokens do not exceed granted scopes. |
| Requesting previously approved scopes again | Can reuse consent per policy without granting extra permissions. |
| Client requests an additional new scope | Does not auto-approve the new permission; handles consent per flow. |
| Client requests an unregistered scope | Rejects request per protocol without persisting new permissions. |
| User clicks "Deny" | Does not create consent for denied permissions; returns appropriate error response. |
| Bob requests the same client | Does not reuse Alice's consent record. |
| Alice requests client B | Does not reuse client A's consent record. |
| Forged consent POST / CSRF | Does not save consent; endpoint rejects per configured protection. |
| Revoke consent | Record is gone; subsequent authorization re-evaluates consent. |
| Revoke consent while old JWT is unexpired | Verifies exact chosen token revocation strategy; does not assume JWT expires automatically. |
| Restart Authorization Server using JDBC | Durable consent is read back properly. |
| Two instances sharing a database | Consistent consent decisions, no lost updates under concurrency. |
| Delete client or change registeredClient ID | Orphaned consent data handled per policy. |

At the HTTP level, use <code>MockMvc</code> or a real protocol client to exercise authentication, authorization endpoint, session, CSRF, consent submission, authorization code, and token endpoint. Assert both protocol responses and actual state in <code>OAuth2AuthorizationConsentService</code>.

**Note on mocking:** Simply stubbing <code>consentService.findById()</code> in a unit test does not prove an OAuth request selected the right client, scopes, or redirect URI. Similarly, mocking JWT authentication in a Resource Server skips JWT decoder checks; token validation requires its own integration tests.

### 11.3. Invariants worth asserting

A solid test suite should guarantee:

~~~text
Persisted consent scopes ⊆ Allowed scopes for this client and principal
Granted token scopes ⊆ Valid requested / authorized scopes
Consent(client A, user X) != Consent(client B, user X)
Consent(client A, user X) != Consent(client A, user Y)
Removing consent does not imply revocation of an already issued JWT
~~~

The symbol <code>⊆</code> means "subset of or equal to." Permission invariants should be evaluated after applying specific policies and grant types; certain authorities stored for OIDC may have different semantics/representations than API scopes depending on version and configuration.

## 12. Common issues and troubleshooting

### Issue 1: Users are prompted for consent on every login

Check whether <code>OAuth2AuthorizationConsentService</code> is in-memory and getting reset; whether the client record ID or <code>principalName</code> changes every time; whether the server runs multiple instances with separate stores; whether new scopes are actually being requested; and whether policy forces re-consent.

Never disable <code>requireAuthorizationConsent</code> simply to mask a data bug. Identify why the system fails to find prior consent.

### Issue 2: Consent exists, yet tokens still lack the scope

Stored consent **does not guarantee** a scope is always granted. Check actual requested scopes, registered scopes, grant type, Authorization Server policy, user choice on the current request, and token customization logic. Never inject a scope into a JWT merely because it appears in the consent table.

### Issue 3: User clicked Disconnect, yet the API still accepts the token

This can be expected behavior when an old JWT remains unexpired and the Resource Server validates offline only. Compare against product requirements, token lifetimes, revoke/introspection/denylist mechanisms, and refresh tokens. If the product promises instant disconnection, implement real revocation rather than deleting consent alone.

### Issue 4: JDBC save fails or reads consent inconsistently

Check version-matched schema, connection pools, transactions, composite primary key, data type of the <code>authorities</code> column, DB permissions, and multi-node behavior. If using custom mappers/serializers, test round-trip serialization of authorities.

Never automatically "skip consent" when the database errors out: a storage failure is never a reason to grant extra permissions. Handle errors safely and fail closed.

### Issue 5: Exposing or mixing up another user's consent

Audit principal keys, tenant scoping, registered client record IDs, custom list/revoke queries, session ownership, and what data the frontend is permitted to submit. Consider revoking improperly issued tokens and reviewing audit logs per your security incident response process.

## 13. Applied exercise

Design an Authorization Server for three clients:

- Client **reporting-web** using Authorization Code + PKCE, requesting <code>openid</code>, <code>reports.read</code>, and when needed <code>reports.export</code>.
- Client **admin-portal** under the same issuer but with its own <code>registeredClientId</code>.
- Client **batch-job** using Client Credentials to execute system tasks.

Complete the following tasks:

1. Propose a <code>RegisteredClient</code> structure and <code>ClientSettings.requireAuthorizationConsent</code> for <code>reporting-web</code>. Explain which clients genuinely require End-User consent.
2. Initially, Alice grants only <code>reports.read</code>. Describe the <code>OAuth2AuthorizationConsent</code> record and why <code>reports.export</code> is not automatically granted.
3. When the client additionally requests <code>reports.export</code>, describe the checks required before updating consent and issuing tokens.
4. Build the JDBC service and migration for the consent table, explaining why the key should be based on the registered client record ID and a stable principal.
5. Design a "Disconnect reporting-web" feature with CSRF protection, principal ownership checks, and policy-compliant token revocation.
6. Write one unit test verifying client/principal isolation, one integration test for scope boundaries, and one integration test for revocation when access tokens are JWTs.
7. When the system runs across three instances and two tenants share the username <code>alice</code>, prove that consents cannot leak across tenants.

Your design answer should clearly explain **what permissions consent stores, under which key, when it is re-prompted, where it is stored, and how it differs from token revocation**.

## 14. References

- [Spring Authorization Server — Core Model / <code>OAuth2AuthorizationConsent</code>](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): consent model, service, and storage implementations.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): configuring the authorization endpoint, OIDC, and Java DSL.
- [Spring Authorization Server — Getting Started](https://docs.spring.io/spring-authorization-server/reference/getting-started.html): client registration, consent, and required beans.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): <code>GrantedAuthority</code>, <code>AuthorizationManager</code>, and authorization models.
- [RFC 6749, §4.1 — Authorization Code Grant](https://www.rfc-editor.org/rfc/rfc6749#section-4.1): OAuth 2.0 authorization flow and resource owner approval.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): token revocation mechanism, distinct from storing consent.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): scopes and consent in OIDC.
