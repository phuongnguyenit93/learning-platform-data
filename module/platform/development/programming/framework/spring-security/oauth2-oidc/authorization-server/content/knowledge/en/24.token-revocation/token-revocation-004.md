# Revoking Access Tokens, Refresh Tokens, and Related Authorizations

## 1. Context and Objectives

In the **Revocation** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, we learn how to revoke the use of **Access Tokens**, **Refresh Tokens**, and related **OAuth2Authorization** state. This knowledge fits within the broader objective: **designing, configuring, securing, testing, and operating an OAuth 2.0/OpenID Connect Authorization Server with Spring Security and Spring Authorization Server in a Spring Boot application**.

Suppose user Alice logs into the Portal application, receives an Access Token to call the Orders API, and receives a Refresh Token to extend her session. Later, Alice clicks "Log out from this device" or discovers that her device was lost. The system needs to answer accurately:

1. Will the current Access Token still be accepted by the Orders API?
2. Can the Refresh Token still be exchanged for a new Access Token?
3. If an authorization contains both tokens, does revoking one token invalidate the other?
4. If the Access Token is a JWT and the API only verifies signatures offline, how can near-real-time revocation be achieved?
5. How does revoking one of Alice's sessions differ from "log out from all devices"?

**Lesson objective:** understand RFC 7009, Spring Authorization Server's storage structure, how to design **revocation scope** and **cascade policy** according to business needs, distinguish revocation at the Authorization Server from enforcement at the Resource Server, and test error cases and race conditions.

### 1.1. Three Easily Confused Concepts

| Concept | Action | Primary Effect |
| --- | --- | --- |
| **Expiration** | Token reaches its expiration time | Token is no longer valid due to `exp` or TTL |
| **Revocation** | An authorized party actively invalidates the token | Stops further use of the token, to the extent observable by the Resource Server |
| **Logout / Session termination** | Ends the application/browser session or OIDC session | Does not necessarily revoke all previously issued OAuth2 tokens automatically |

Token revocation does not replace authentication, session management, API authorization, wiping credentials from devices, or account compromise detection. These layers must work together, yet they have different lifecycles.

## 2. RFC 7009 — OAuth 2.0 Token Revocation

**RFC 7009** standardizes how an OAuth client requests that the Authorization Server invalidate a token. With Spring Authorization Server, the default Token Revocation Endpoint is typically:

~~~text
POST /oauth2/revoke
~~~

Requests use `application/x-www-form-urlencoded`, containing the required parameter **token** and optionally **token_type_hint**. Confidential clients must authenticate using their registered client authentication method; public clients must still adhere to deployed client identification limits and policies.

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.com
Authorization: Basic <encoded-client-credentials>
Content-Type: application/x-www-form-urlencoded

token=<issued-refresh-token>&token_type_hint=refresh_token
~~~

| Parameter | Required? | Purpose |
| --- | --- | --- |
| `token` | Yes | The token string to revoke; treated as a sensitive credential |
| `token_type_hint` | No | Hints the token type, commonly `access_token` or `refresh_token` |
| Client authentication | Depends on client type/registered method, must follow policy | Proves which client is requesting revocation |

**`token_type_hint` is only a lookup optimization hint**, not proof that the token belongs to that type and not an instruction to ignore other token types. The server still verifies the actual token, client association, and policy. Do not allow an arbitrary hint to bypass permission checks.

### 2.1. Success Responses and Non-Disclosure

RFC 7009 specifies that the server responds with **HTTP 200** once a valid revocation request has been processed, even if the token does not exist or is already invalid:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
~~~

A success response typically needs no JSON body. This prevents turning the endpoint into an "oracle to probe whether a token is real".

**Do not infer that HTTP 200 means every Resource Server immediately stopped accepting the token.** It confirms the request was processed at the Authorization Server. If APIs only check JWTs offline or cache introspection responses for too long, the token may continue to be accepted until the cache expires or the token hits `exp`.

### 2.2. Errors and Non-Disclosing Behavior

Cases that may return errors include requests missing `token`, failed client authentication, or unsupported token types. RFC 7009 also defines the error **unsupported_token_type** when the Authorization Server does not support revoking the requested token type; other OAuth2 errors follow protocol semantics.

**Do not return 404 or a message like "user A's token exists"** merely to distinguish unknown tokens from real tokens. For tokens not owned by the submitting client, the server must reject or handle them without disclosing information per policy, providing no details that could be used to probe tokens.

### 2.3. What Does RFC 7009 Say About Related Tokens?

RFC 7009 allows a revocation request to apply to **related tokens based on the same authorization grant**. When a **Refresh Token** is revoked, the Authorization Server **SHOULD** revoke Access Tokens based on the same authorization grant if the server is capable of revoking Access Tokens. When an **Access Token** is revoked, the server **MAY** revoke the corresponding Refresh Token.

Those are protocol-level semantics; **do not assume the default implementation of every Spring Authorization Server version always enforces the same cascade policy**. Verify the behavior of your provider and proactively build a policy if business requirements call for synchronized revocation of the entire session/authorization.

## 3. Revocation Flow in the System

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Alice
    participant C as Portal / OAuth Client
    participant AS as Authorization Server
    participant DB as OAuth2AuthorizationService
    participant RS as Orders Resource Server
    U->>C: Select log out device
    C->>AS: POST /oauth2/revoke, refresh_token
    AS->>AS: Authenticate client; verify token ownership
    AS->>DB: Find and update authorization/token status
    DB-->>AS: Revocation state persisted
    AS-->>C: HTTP 200
    C->>C: Delete tokens from storage, end local session
    C->>RS: Request with old Access Token (if any)
    alt RS introspection or denylist received revocation
        RS-->>C: 401 invalid_token
    else RS only verifies JWT offline
        RS-->>C: May continue accepting until exp
    end
~~~

The diagram intentionally separates **updating state at the Authorization Server** from **the Resource Server actually rejecting the token**. These two are not identical if the system uses self-contained JWTs without checking revocation state.

### 3.1. Revocation Is Not a Synchronous HTTP Transaction with Every API

The Authorization Server can persist `invalidated=true` to the database, but other Resource Servers do not automatically learn of that change. To achieve a well-defined revocation latency, you must design one of these options: introspection, a denylist, event propagation, online authorization decisions, or limiting JWT lifetimes to be short.

Never claim "the token was revoked instantaneously across the entire system" without proving propagation time and caching behavior.

## 4. The OAuth2Authorization Model in Spring Authorization Server

Spring Authorization Server stores authorization state in **OAuth2AuthorizationService**. Each **OAuth2Authorization** record represents an authorization/grant and can hold related tokens and metadata.

Common fields:

- **id:** internal identifier of the authorization.
- **registeredClientId:** internal ID of the RegisteredClient; **different** from the public `client_id`.
- **principalName:** principal associated with the authorization.
- **authorizationGrantType:** grant that created the authorization, e.g., `authorization_code` or `client_credentials`.
- **authorizedScopes:** granted scopes.
- **attributes:** metadata used during the flow.
- **tokens:** Authorization Code, Access Token, Refresh Token, OIDC ID Token, or tokens of other grants, depending on context.

| Component | Role | Revocation Notes |
| --- | --- | --- |
| `OAuth2AuthorizationService` | Find, save, remove authorizations | Where validity state is mutated |
| `OAuth2Authorization` | Stores a grant/authorization and its tokens | Not synonymous with the user's entire login session |
| `OAuth2Authorization.Token` | Wraps token + metadata, can track invalidated state | `isActive()` is affected by expired/invalidated |
| `OAuth2AuthorizationService.findByToken(...)` | Finds authorization by token value | Must distinguish an invalidated token from a token not found |
| `OAuth2AuthorizationService.save(...)` | Saves updated authorization | Must consider multi-node consistency |
| `OAuth2AuthorizationService.remove(...)` | Deletes authorization | Terminates lookup/introspection for all tokens in the record |
| `OAuth2AuthorizationConsentService` | Manages user–client consent | Not a token store; revoking tokens does not auto-delete consent |

### 4.1. Token State Is More Than Just Unexpired/Expired

A token may have a valid timestamp yet be marked **invalidated**. In that case `Token.isActive()` returns false even though `exp` has not been reached. Conversely, an expired JWT whose record has not yet been cleaned up is still not considered active.

Concept:

~~~text
Active per OAuth2Authorization.Token:
    not expired
    AND not invalidated
    AND meets token status conditions

JWT accepted by Resource Server:
    signature, issuer, audience, time, scope... valid
    AND revocation state if Resource Server checks it
~~~

These two checks live in different components; **they do not automatically synchronize** when the Resource Server only has a JWT Decoder.

### 4.2. One Authorization Is Not "All Devices"

User Alice may log into Portal on both her phone and laptop, creating **two distinct OAuth2Authorizations**. Revoking the phone's authorization does not inherently remove the laptop's authorization. Revoking across all devices/accounts requires finding all related authorizations via a dedicated store/index and policy.

## 5. Token Revocation Endpoint Pipeline

Spring Authorization Server has dedicated components at the Token Revocation Endpoint:

~~~mermaid
flowchart TD
    A["POST /oauth2/revoke"] --> B["OAuth2TokenRevocationEndpointFilter"]
    B --> C["Converter reads token + token_type_hint"]
    C --> D["AuthenticationManager"]
    D --> E["OAuth2TokenRevocationAuthenticationProvider"]
    E --> F["Verify authenticated client"]
    F --> G["OAuth2AuthorizationService.findByToken"]
    G --> H{"Token belongs to valid client?"}
    H -->|No| X["OAuth2 error or non-disclosing handling"]
    H -->|Yes| I["Mark invalidated / update authorization"]
    I --> J["OAuth2AuthorizationService.save"]
    J --> K["HTTP 200"]
~~~

This is a conceptual pipeline. Specific converters/providers and check ordering should be verified against your exact Spring Authorization Server version. The filter handles HTTP; the provider validates OAuth2 conditions and uses the service to persist state.

### 5.1. Default Endpoint and Changing the Path

By default, the Token Revocation Endpoint uses the path **/oauth2/revoke**. In Spring Authorization Server 1.x versions providing the corresponding API, it can be configured as:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Configuration(proxyBeanMethods = false)
class RevocationEndpointSettings {

    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
                .issuer("https://auth.example.com")
                .tokenRevocationEndpoint("/oauth2/revoke")
                .build();
    }
}
~~~

When changing the endpoint, update discovery metadata, proxy routing, and client configuration. Do not build a custom REST controller for token revocation without OAuth2 client authentication and treat it as a safe replacement for RFC 7009.

### 5.2. Configuring Extension Points

`OAuth2AuthorizationServerConfigurer` lets you customize protocol endpoints per the version's API. For the Token Revocation Endpoint, customization typically involves request converters, authentication providers, and success/error handlers.

Do not place steps affecting revocation authority solely inside the converter: the converter primarily handles request structure. **Token ownership, client binding, cascade policy, auditing, and the decision to revoke** belong to the provider/service operating on authenticated data.

## 6. Distinguishing Revocation by Target Object

| Action | What Needs Invalidating | Desired Effect | What Is Not Yet Guaranteed |
| --- | --- | --- | --- |
| Revoke **Access Token** | A specific Access Token | Blocks API access using that token | Refresh Token may still be usable |
| Revoke **Refresh Token** | A specific Refresh Token | Blocks minting new Access Tokens from that refresh | Already-issued Access Token may still be accepted by APIs |
| Revoke **both Access + Refresh** | Both tokens in one authorization | Stops API access and renewal for that session | Offline JWTs and caches need an enforcement strategy |
| Revoke **OAuth2Authorization** | All tokens/state belonging to one authorization | Ends the grant along record boundaries | Other authorizations of the user are not automatically deleted |
| Revoke **all user sessions** | All matching authorizations + browser sessions | Logs out multiple devices per policy | Requires dedicated queries/indexes and a fan-out strategy |
| Revoke **OAuth2AuthorizationConsent** | Saved user–client consent | May require re-consent on the next grant | Does not revoke already-issued Access/Refresh Tokens |

**Do not assume** logout = revoke Access Token = revoke Refresh Token = delete consent. Each action has a distinct goal and scope.

### 6.1. Single Access Token

Revoking only an Access Token is useful when:

- An Access Token is suspected leaked while the Refresh Token is separately protected.
- A downstream token issued for an API needs to be closed immediately.
- A policy wants to block the current token while still letting the client obtain fresh access through a valid flow.

However, if the Refresh Token remains active, the client can immediately request a new Access Token. To force re-authentication, you must consider **revoking the Refresh Token and/or authorization**.

### 6.2. Refresh Token and Replay Risk

Revoking a Refresh Token stops new token issuance along that refresh chain. If an unexpired Access Token exists in the same authorization, decide whether to **cascade revoke** the Access Token. RFC 7009 recommends that when revoking a Refresh Token, the server also invalidate Access Tokens in the same grant if capable.

Production policies for full-session logout or suspected Refresh Token compromise typically choose **revoking both Refresh and Access**. Do not merely delete the Refresh Token on the client while leaving the server accepting it.

### 6.3. Entire Authorization

An `OAuth2Authorization` can hold an Access Token, Refresh Token, and other grant-related tokens. Either removing the authorization via `remove` or marking individual tokens as invalidated can make tokens unfindable through the authorization store.

Both approaches involve trade-offs:

- **Invalidate metadata and keep the record:** convenient for tracing, auditing, enforcing token state, and controlled cleanup.
- **Remove the record:** simple when terminating the whole authorization, but loses state in this store; requires independent auditing if needed for investigations to avoid losing incident evidence.

For JWT Access Tokens verified solely offline by APIs, neither choice **automatically alters signed tokens residing on client devices**. APIs must have an additional state-checking mechanism or wait for expiration.

## 7. Designing Cascade Policies for Different Scenarios

Policies should not depend solely on "which token type was just submitted" but must consider **the business event, risk, and authenticated action scope**.

| Event | Recommended Revocation Scope | Rationale |
| --- | --- | --- |
| Single-device logout | Access + Refresh of that device's authorization | Prevents further use and renewal of the selected session |
| Client proactively rotating Access Token | Single Access Token, if policy permits | Refresh Token can continue; avoids forcing re-login |
| User reports lost device | All tokens/authorizations of the lost device | Prevent Refresh Token from continuing to operate |
| Refresh Token reuse detected | Affected token family/grant, potentially broader per risk policy | Indicator of stolen token or abnormal race |
| Account locked or compromised | All user authorizations, related sessions, and credential changes | Cuts off access across all devices |
| App access permission revoked | User–client authorizations; consider removing consent | Blocks old tokens and requires fresh grant/consent |
| Single downstream API revoked | Tokens with target audience/scope or related authorization | Avoids disrupting unrelated permissions unnecessarily |
| Client secret/certificate compromised | Client-wide authorizations, credentials, and bound tokens per risk | Proof the client's identity was compromised |

These rows are **design suggestions**. Determine which actions users may trigger themselves and which only administrators or security services are permitted to perform. Revocation APIs must authenticate callers and never let users arbitrarily specify someone else's authorization ID.

### 7.1. Having Overlapping Scopes Does Not Mean Revocation Permission

A client registered with many scopes does not have the right to revoke another client's tokens. Token ownership and authorization association are critical boundaries. Avoid building APIs like `POST /internal/revoke?clientId=...` that trust a `clientId` from the request.

### 7.2. There Is No "Safe-by-Default" Revocation Order for Every Architecture

An application ending a session needs to stop refreshes immediately, update access state, notify Resource Servers that need to know, and wipe local credentials. These operations may span different components; build idempotency, retries, and auditing so partial failures do not leave unintended active sessions.

## 8. JWTs, Opaque Tokens, and Post-Revocation Effectiveness

This is the most error-prone area when implementing revocation.

| Access Token Type / Verification Mode | What Happens When Authorization Server Marks Revoked | When Resource Server Sees It |
| --- | --- | --- |
| Opaque Token + online introspection | `active=false` if token state is invalidated | Near real-time, subject to network latency and caching |
| JWT + API checks signature/iss/aud/exp only | Old JWT still carries valid signature and expiry | Possibly until `exp`, even if DB shows invalidated |
| JWT + denylist by `jti`/token hash | API checks whether token is in revoked list | At denylist update/sync speed |
| JWT + introspection/online authorization check | API checks token status at AS or shared service | Near real-time if no stale cache |
| Short-lived JWT, no online state | Limits window old token remains usable | At most roughly remaining TTL, not immediate |

### 8.1. Why Revoking a JWT Cannot Alter an Issued Signature

A JWT is signed data residing on the client. Spring Authorization Server can mark the record in `OAuth2AuthorizationService` as invalidated, but it cannot "edit" the token on the client side or revoke a cryptographic signature via a database update alone.

An offline Resource Server typically knows only:

~~~text
valid signature
AND trusted issuer
AND matching audience
AND token not expired
AND appropriate scope/authorization
~~~

Without a **revocation validator**, the Resource Server has no knowledge that the token was marked invalidated in the authorization store.

### 8.2. Token-Status Enforcement Architecture

~~~mermaid
flowchart LR
    AS["Authorization Server"] -->|"Revoke / save invalidation"| DB["Authorization Store"]
    DB -->|"Introspection active=false"| RS1["Resource Server A"]
    AS -->|"Revocation event"| BUS["Event / Cache Invalidation"]
    BUS -->|"jti or token hash"| RS2["Resource Server B + Denylist"]
    AS -->|"JWT signed with short exp"| RS3["Resource Server C offline"]
    RS3 -->|"Only knows at exp"| END["Token expires"]
~~~

Each strategy needs a **revocation SLO** measured by tests: e.g., revocations must be reflected at APIs within a defined number of seconds or cache bound. Never commit to an SLO without an enforcement mechanism that meets it.

### 8.3. Introspection Caching

Caching reduces latency but can keep `active=true` in use after a token is revoked. Bound cache TTLs according to risk, provide cache invalidation where needed, never cache an active result past the token's expiration, and evaluate fail-open vs. fail-closed behavior if the Authorization Server is temporarily unreachable.

### 8.4. Denylists for JWTs

If a denylist is needed, store `jti` or a token hash (never raw tokens) along with the necessary expiry, issuer, and audience. Every API must check the appropriate state, and the denylist must be shared across nodes. Once a token expires, entries can be purged. Handle tokens missing `jti` per profile and prevent false matches across issuers.

## 9. Refresh Token Rotation, Reuse, and Token Families

### 9.1. Rotation Reduces Impact When a Refresh Token Is Stolen

With Refresh Token rotation, each successful use of a Refresh Token can issue a new Refresh Token while invalidating the old one. In Spring Authorization Server, you can configure:

~~~java
import java.time.Duration;

import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

TokenSettings tokenSettings = TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .refreshTokenTimeToLive(Duration.ofDays(7))
        .reuseRefreshTokens(false)
        .build();
~~~

`reuseRefreshTokens(false)` issues a new Refresh Token per policy. However, **rotation does not automatically imply detecting every reuse of an old Refresh Token** or auto-revoking an entire token family; those mechanisms depend on persisted history state and custom policies.

### 9.2. Distinguishing Two Scenarios

**Normal case:** the client uses Refresh Token R1 and receives R2; R1 is no longer usable. If the client accidentally resends R1, the request is rejected, though the system might not distinguish a client bug from an attacker.

**Suspected compromise:** R1 was already exchanged for R2, yet reappears from another source. If the system tracks chain/family relationships and device bindings, it can flag reuse, revoke the entire family, and force re-authentication.

Reliable reuse detection requires storing **token family relationships, issuance generations, old token status, timestamps, and risk signals**. Do not assume `OAuth2AuthorizationService.findByToken(R1, ...)` still locates the old token after rotation; implementations may retain only the newest token.

### 9.3. Race Conditions During Refresh

Two nodes may concurrently receive R1 and both attempt to exchange it for a new token. Without proper repository concurrency control, one refresh can overwrite state or mint multiple tokens unexpectedly.

Options:

- Use transactions, optimistic locking, or compare-and-set for family state.
- Ensure only a single Refresh Token consumption transaction is accepted per policy.
- Test across multiple nodes, concurrent requests, and network-error retries.
- Define any grace period very carefully if business logic must tolerate lost responses; never turn a grace period into unlimited replay.

**Merely using a JDBC repository does not prove atomicity meeting anti-reuse policies.** Test against your actual database, isolation level, and framework version.

## 10. Managing Related Authorizations and Revocation Scope

### 10.1. OAuth2Authorization ID Is Not a User Session ID

`OAuth2Authorization.id` is the record key for a single grant. A user can hold multiple authorizations across clients/devices. `principalName` can represent a user or a client depending on the grant.

If the user chooses "Log out all devices", the application must locate all authorizations belonging to the subject and relevant clients/devices. The default `OAuth2AuthorizationService` interface supports lookup by ID/token and **does not provide a built-in API to list all authorizations by principalName**. Production systems need a dedicated query repository/index or a controlled authorization management service.

### 10.2. Consent, Sessions, and ID Tokens Are Distinct Objects

- `OAuth2AuthorizationConsentService` stores consent between a user and a `RegisteredClient`; revoking tokens does not automatically remove consent.
- Browser HTTP sessions / Spring Security sessions are not automatically cleared when `OAuth2AuthorizationService` updates a token.
- An OIDC ID Token authenticates the user to the OIDC Client; revoking an Access Token is not the OIDC logout protocol.
- OIDC RP-Initiated Logout, Front-Channel/Back-Channel Logout, and session management are separate mechanisms requiring separate design.

### 10.3. Principles for Scoping Revocation

| Goal | Identification Condition |
| --- | --- |
| Revoke a single token | Specific token + authenticated client, token ownership |
| Revoke a single authorization | Authorization ID + verified subject/tenant/client |
| Revoke a single device | Server-managed device/session binding |
| Revoke all for a user | Trusted user identity + query across related authorizations |
| Revoke an entire compromised client | RegisteredClient internal ID + administrative policy |

Do not accept `authorizationId`, `principalName`, or `clientId` from a request and treat them as proof of caller authority to revoke. Enforce RBAC guards, tenant isolation, auditing, and anti-enumeration protections.

## 11. Java Example: Revoking the Right Authorization Scope

To revoke **both Access Token and Refresh Token** or an entire authorization upon an authenticated action, a trusted business service can use `OAuth2AuthorizationService` directly. The snippet below demonstrates:

- Distinguishing an Access Token-only revocation from revoking both Access + Refresh.
- Supporting termination of the entire authorization.
- Processing only records bound to the RegisteredClient ID and principal verified by the security layer.
- Recording invalidated state via `OAuth2Authorization.Builder.invalidate(...)` rather than mutating raw tokens manually.

### 11.1. Policy-Driven Revocation Service

~~~java
import java.util.Objects;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.oauth2.server.authorization.OAuth2Authorization;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuthorizationRevocationPolicyService {

    public enum Mode {
        ACCESS_ONLY,
        ACCESS_AND_REFRESH,
        ENTIRE_AUTHORIZATION
    }

    private final OAuth2AuthorizationService authorizationService;

    public AuthorizationRevocationPolicyService(
            OAuth2AuthorizationService authorizationService) {
        this.authorizationService = authorizationService;
    }

    @Transactional
    public boolean revoke(
            String authorizationId,
            String trustedRegisteredClientId,
            String trustedPrincipalName,
            Mode mode) {

        OAuth2Authorization authorization =
                authorizationService.findById(authorizationId);

        if (authorization == null) {
            // Do not let a public API disclose whether the ID exists.
            return false;
        }

        // Trusted values MUST come from an authenticated/authorized
        // caller context, not arbitrary request data.
        if (!Objects.equals(
                    authorization.getRegisteredClientId(),
                    trustedRegisteredClientId)
                || !Objects.equals(
                    authorization.getPrincipalName(),
                    trustedPrincipalName)) {
            throw new AccessDeniedException(
                    "Authorization revocation is not permitted");
        }

        if (mode == Mode.ENTIRE_AUTHORIZATION) {
            authorizationService.remove(authorization);
            return true;
        }

        OAuth2Authorization.Builder builder =
                OAuth2Authorization.from(authorization);

        if (authorization.getAccessToken() != null) {
            builder.invalidate(authorization.getAccessToken().getToken());
        }

        if (mode == Mode.ACCESS_AND_REFRESH
                && authorization.getRefreshToken() != null) {
            builder.invalidate(authorization.getRefreshToken().getToken());
        }

        authorizationService.save(builder.build());
        return true;
    }
}
~~~

**This is an illustrative service, not a public endpoint allowing clients to pick arbitrary authorizations.** In production:

1. `authorizationId` must come from a verified session/device or an authorized administrative workflow, never blindly from a form/URL.
2. `trustedRegisteredClientId` is the **internal RegisteredClient ID**, not a caller-asserted `client_id`.
3. `trustedPrincipalName` must come from an authenticated principal or an admin-authorized target; never let a browser choose whose sessions to revoke.
4. Check tenant/device ownership, RBAC, auditing, rate limits, and CSRF protection if triggered from a browser session.
5. `ENTIRE_AUTHORIZATION` deletes the record, so independent auditing is required if incident history must be retained.
6. If the system uses other token types/grants, decide explicitly whether to invalidate Authorization Codes, Device Codes, or related tokens before terminating the authorization. Deleting the record ends store lookups but does not automatically terminate client-side sessions.
7. `@Transactional` provides atomicity only according to your actual transaction manager and repository configuration; it does not guarantee synchronization with caches, Resource Servers, or event buses.

### 11.2. Variant: Retaining the Record While Invalidating Multiple Tokens

If you need to retain the authorization for auditing, mark existing tokens as invalidated:

~~~java
OAuth2Authorization existing =
        authorizationService.findById(authorizationId);

if (existing == null) {
    // Handle with non-disclosing not-found policy.
    return;
}

// Ownership/tenant/RBAC checks are mandatory before this section.
OAuth2Authorization.Builder builder =
        OAuth2Authorization.from(existing);

if (existing.getAccessToken() != null) {
    builder.invalidate(existing.getAccessToken().getToken());
}

if (existing.getRefreshToken() != null) {
    builder.invalidate(existing.getRefreshToken().getToken());
}

if (existing.getAuthorizationCode() != null) {
    builder.invalidate(existing.getAuthorizationCode().getToken());
}

authorizationService.save(builder.build());
~~~

This is a **snippet inside an already-protected service**, not a standalone Java method; `authorizationService` and `authorizationId` come from the service context. Invalidating an Authorization Code is meaningful if the grant exchange has not completed, though it does not cover every other authorization type. For a complete termination policy, review tokens/metadata specific to OIDC, Device Authorization, Token Exchange, and custom grants.

### 11.3. Difference Between invalidate and remove

| Approach | Record Remains in Store? | Token Status in Store | Auditing |
| --- | --- | --- | --- |
| `builder.invalidate(token)` + `save` | Yes | Token marked inactive | Retains metadata history per retention |
| `authorizationService.remove(auth)` | No | Token no longer findable in authorization store | Needs auditing elsewhere |

Neither approach is stronger on its own if Resource Servers do not query the store. Coordinate with API verification mechanisms so revocation takes real effect.

## 12. Calling the Revocation Endpoint via HTTP

For a confidential client with a client secret registered with `CLIENT_SECRET_BASIC`, for example:

~~~bash
curl -i --request POST \
  --url 'https://auth-test.example.com/oauth2/revoke' \
  --user 'portal-client:<test-client-secret>' \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'token=<refresh-token-from-test-flow>' \
  --data-urlencode 'token_type_hint=refresh_token'
~~~

`--user` uses HTTP Basic client authentication. Strings in `<...>` are placeholders, not real credentials. When running tests with real tokens, keep tokens/secrets out of shell history, debug output, CI logs, and tickets. In automation, use proper credential injection rather than hardcoding.

### 12.1. Revoking an Access Token

~~~bash
curl -i --request POST \
  --url 'https://auth-test.example.com/oauth2/revoke' \
  --user 'portal-client:<test-client-secret>' \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'token=<access-token-from-test-flow>' \
  --data-urlencode 'token_type_hint=access_token'
~~~

If `token_type_hint` is omitted, the server must still process the request using its token lookup capability. The hint optimizes lookup; it does not validate the token or dictate related-token revocation policy.

### 12.2. Revocation Does Not Mean the Client Deleted Credentials

After HTTP 200, the client must:

- Delete Access Tokens/Refresh Tokens from session or device storage.
- Clear or update local `OAuth2AuthorizedClient` state if using Spring Security OAuth2 Client.
- Clear application cookies/sessions when the goal is logout.
- Stop any background scheduler from refreshing with the revoked token.
- Display the logout result without exposing token details.

Do not wait for token expiration to clear local credentials. Blocking the token server-side and stopping credential usage client-side are complementary responsibilities.

### 12.3. When the Client Has No Refresh Token

Not every grant issues a Refresh Token. With Client Credentials, typically only an Access Token exists. In that case, revoking the Access Token only blocks that token if the Resource Server observes revocation; the confidential client can still use its own credentials to obtain another token.

If client credentials are compromised, you must **disable the client, revoke/rotate secrets/certificates/keys and related tokens**, not just revoke a single Access Token.

## 13. Resource Server Integration for Effective Enforcement

### 13.1. Opaque Tokens via Introspection

A Resource Server using the Token Introspection Endpoint per **RFC 7662** can receive:

~~~json
{
  "active": false
}
~~~

when the Access Token is invalidated or no longer active. When using Spring Security Resource Server with opaque tokens, proper introspection lets the Resource Server observe the state stored by the Authorization Server.

Points to check:

- The Resource Server authenticates to the Introspection Endpoint.
- An `active=false` result causes the request to be rejected.
- `active=true` is not cached longer than the revocation SLO bound.
- If the AS/introspection service is unavailable, fail-open vs. fail-closed behavior must be decided by policy; sensitive endpoints should favor fail-closed.
- Tokens and introspection credentials are never logged.

### 13.2. Offline JWTs and Denylists

If the Orders API uses only a JWT decoder, you can add a validator checking `jti` or a token hash against a denylist. Flow:

~~~text
Authorization Server:
    revoke access token
    -> update authorization store
    -> publish revoke event with issuer + token ID/hash + expiry

Resource Server:
    verify signature/iss/aud/exp
    -> check if jti/hash is in denylist
    -> check scope/authorization
    -> accept or reject
~~~

**Transmit only safe identifiers**; never put raw Access Tokens on message buses or metrics. Revocation events need an issuer identifier to avoid token ID collisions across trust domains, along with clear retry, deduplication, and replay/delivery semantics. Across multiple nodes, denylist caches must converge within the desired window.

### 13.3. Short-Lived JWT Option

An architecture that does not require immediate Access Token revocation may opt for short JWT TTLs—such as a few minutes—while revoking the Refresh Token to stop renewal. Then the **maximum risk window** depends on the remaining JWT lifetime and factors like clock skew; never describe this as "immediate Access Token revocation".

Choose TTLs based on your threat model and SLA, not merely for convenience in reducing Token Endpoint load.

### 13.4. Token Binding Does Not Replace Revocation

DPoP (`cnf.jkt`) and mTLS certificate-bound tokens (`cnf.x5t#S256`) restrict who can present a leaked Access Token. However, if the corresponding private key/certificate is also compromised, an attacker can still present the token. **Sender constraints do not replace revocation, denylists, introspection, or TTLs.**

## 14. Logout, OpenID Connect, and Revoking Permissions

An OIDC Client may need to:

1. Clear the local login session.
2. Perform logout at the OpenID Provider if policy requires it.
3. Revoke Access Tokens/Refresh Tokens or the entire authorization.
4. Update state on APIs/devices being terminated.
5. If the user revokes application permissions, consider removing `OAuth2AuthorizationConsent` to require fresh consent on the next grant.

**Do not treat an OIDC ID Token as an Access Token** to send to a Resource Server. Nor is an OIDC Back-Channel Logout token a Refresh Token to pass to the RFC 7009 Revocation Endpoint.

### 14.1. Deleting Consent Does Not Invalidate Existing Tokens

`OAuth2AuthorizationConsentService.remove(consent)` manages the consent record and must not be treated as revoking all already-issued Access and Refresh Tokens. To terminate active access, revoke the authorization/tokens and ensure Resource Server enforcement.

### 14.2. Single-Device vs. All-Device Logout

| Requirement | Recommended Scope |
| --- | --- |
| Log out from current laptop | Authorization bound to the current laptop/session |
| Log out all devices | All authorizations belonging to the user across allowed clients/tenants |
| Revoke permissions of one app | User–client authorizations, consider consent |
| Lock account due to risk | Authorizations, sessions, and dependent credentials per runbook |

To identify a **device**, the architecture must maintain reliable session/device correlation. Do not infer devices solely from `User-Agent` or IP, as both can collide and change easily.

## 15. Testing the Token Revocation Endpoint with MockMvc

### 15.1. Checking HTTP 200 and Token State

Suppose the test fixture has created:

- A confidential `RegisteredClient` with `client_id=portal-client` and matching secret.
- An authorization that issued a Refresh Token.
- An injected `OAuth2AuthorizationService` holding the authorization record.

Condensed integration test example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.server.authorization.OAuth2Authorization;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TokenRevocationIntegrationTest {

    @Autowired MockMvc mvc;
    @Autowired OAuth2AuthorizationService authorizationService;

    @Test
    void revokingRefreshTokenMakesItInactive() throws Exception {
        String authorizationId = obtainAuthorizationIdFromTestFlow();
        OAuth2Authorization before =
                authorizationService.findById(authorizationId);

        assertThat(before).isNotNull();
        assertThat(before.getRefreshToken()).isNotNull();
        String refreshToken = before.getRefreshToken().getToken().getTokenValue();

        mvc.perform(post("/oauth2/revoke")
                .with(httpBasic("portal-client", "test-client-secret"))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("token", refreshToken)
                .param("token_type_hint", "refresh_token"))
            .andExpect(status().isOk());

        OAuth2Authorization after =
                authorizationService.findById(authorizationId);
        assertThat(after).isNotNull();
        assertThat(after.getRefreshToken().isActive()).isFalse();
    }

    private String obtainAuthorizationIdFromTestFlow() {
        // Fixture: create an authorization via a valid grant,
        // saving the ID from OAuth2AuthorizationService.
        throw new UnsupportedOperationException("Implement test fixture");
    }
}
~~~

This sample **does not run standalone**: it requires `spring-security-test`, an encoded client secret in `RegisteredClient`, `SecurityFilterChain`/Authorization Server beans, and a real fixture. It tests the case where the provider **keeps the record and marks the token invalidated**. If your version or custom policy **removes** the record, adjust the assertion to match that contract rather than assuming the record always remains.

### 15.2. You Must Test Effects Beyond the Endpoint

After revoking the Refresh Token, call:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic <encoded-client-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&
refresh_token=<revoked-refresh-token>
~~~

Expect the Refresh Token Grant to be rejected, typically with `invalid_grant`. If the project requires cascading, verify that the Access Token in the same authorization is no longer active in the store and that **the Resource Server actually rejects it** within the revocation SLO.

## 16. Complete Test Matrix

| # | Scenario | Expected Result |
| --- | --- | --- |
| 1 | Revoke valid Refresh Token with rightful client | HTTP 200; token no longer active |
| 2 | Revoke the same token a second time | HTTP 200, does not disclose existence |
| 3 | Revoke nonexistent token | HTTP 200 per RFC 7009 if request/client valid |
| 4 | Missing `token` parameter | OAuth2 `invalid_request` |
| 5 | Invalid client authentication | `invalid_client` or appropriate auth error |
| 6 | Client A attempts to revoke Client B's token | Disallow unauthorized revocation; do not leak ownership |
| 7 | `token_type_hint` differs from actual token | Server processes actual token correctly; hint cannot bypass checks |
| 8 | Revoke Access Token alone | Access Token invalidated; Refresh Token policy verified |
| 9 | Revoke Refresh Token sharing authorization with Access Token | Verify cascade per published policy |
| 10 | Revoke entire authorization | All tokens in the record blocked via authorization store |
| 11 | Two authorizations for the same user, revoke one | Remaining authorization unaffected if single-device policy |
| 12 | Log out all devices | All authorizations within user scope are revoked |
| 13 | Opaque token after revocation, introspection | `active=false` |
| 14 | Offline JWT after revocation | Demonstrates limit: API may accept until `exp` without revocation check |
| 15 | JWT with denylist | Resource Server rejects within committed SLO |
| 16 | Introspection cache still holds `active=true` | Test TTL/invalidation and stale behavior |
| 17 | Refresh rotation, reuse old token | Rejected; family reuse detection policy tested separately |
| 18 | Two concurrent refreshes across multiple nodes | No tokens issued against concurrency policy |
| 19 | AS restarts right after revocation | Revocation state remains effective with durable storage |
| 20 | AS/storage/introspection temporarily fails | No fail-open on high-security APIs |
| 21 | Revoke DPoP/mTLS-bound token | Both revocation state and key binding verified |
| 22 | Browser logout without token revocation | Test catches tokens still working if policy requires revocation |
| 23 | Delete consent without revoking tokens | Confirm these are independent operations |
| 24 | Client disabled or secret rotated | Remaining tokens/grants handled per security incident policy |

### 16.1. Error Tests Must Not Create Token-Probing Leaks

For unknown and already-revoked tokens, public responses should behave indistinguishably per RFC 7009. Never return a status or description containing token-specific subject, scope, or issuer when the caller lacks authority.

### 16.2. Multi-Node and Cache Effect Tests

In a multi-node environment:

1. Node A receives the revocation request.
2. Node B processes a Refresh Token Grant using the revoked token.
3. Node C handles introspection for the Access Token from the same grant.
4. Resource Server D checks the JWT via denylist/events.

Every component must produce outcomes consistent with policy. Cases like database replication lag, stale caches, delayed events, or concurrent requests need dedicated tests; safety cannot be inferred solely because service unit tests pass.

### 16.3. Testing the Contract Between AS and Resource Server

A valuable integration test issues a real Access Token from the test Authorization Server, calls the Orders API successfully, revokes the token, and calls the Orders API again. Measure the elapsed time from revocation success until the API rejects requests. Record this as **measured revocation latency**, not to be confused with token TTL.

## 17. Error Codes and Troubleshooting

| Symptom | Likely Causes to Check | Resolution |
| --- | --- | --- |
| `POST /oauth2/revoke` returns 404 | Wrong endpoint path or SecurityFilterChain/proxy routing | Check `AuthorizationServerSettings` and endpoints matcher |
| `invalid_client` | Wrong client auth or token does not belong to client | Check registration and client association without logging tokens |
| `invalid_request` | Missing token, malformed form, or duplicate params | Check converter and request |
| HTTP 200 but refresh still works | Store not persisting state, race, bad lookup, or buggy custom provider | Re-read authorization and test Refresh Token Grant |
| HTTP 200 but JWT still calls APIs | Resource Server verifies JWT offline | Add introspection/denylist or reduce TTL per policy |
| HTTP 200 but opaque token stays active | Stale introspection cache or inconsistent authorization store | Check cache TTL/cluster |
| Revoking one session drops multiple sessions | Query user scope too broad or deleted wrong authorization | Check device/client/session binding |
| Old Refresh Token accepted after rotation | Concurrency or `reuseRefreshTokens` setting | Test concurrently and inspect refresh family state |
| Revoke a token but refresh still mints new token | Only Access Token was revoked | Check cascade policy |
| Browser-triggered revoke vulnerable to CSRF | Admin API lacks CSRF or session protection | Add CSRF protection and verify subject |
| Admin-only revoke callable by client | Missing authorization/RBAC | Restrict internal policy endpoint |
| One API node rejects, another accepts | Unsynchronized denylist cache or replication lag | Check propagation and SLO |

Never debug by copying real Access/Refresh Tokens into logs or monitoring tools. Use correlation IDs, protected internal authorization IDs, safe token fingerprints/hashes, error types, and policy versions.

## 18. Operations, Observability, and Safety

### 18.1. Operational Metrics to Track

| Metric | Purpose |
| --- | --- |
| HTTP 200/4xx/5xx rates at Revocation Endpoint | Detect misconfigured clients and internal errors |
| Revocation request count by client/flow | Detect anomalies, abuse, and logout storms |
| Authorization store update latency | Measure state-change latency |
| Time from revoke to API rejection | Measure actual revocation SLO |
| Introspection cache hits and stale window | Balance latency and security |
| Refresh Token reuse attempts | Detect potential token theft/races |
| All-device / client-wide revocation rate | Detect incidents and policy bugs |
| Event/denylist sync across nodes | Prevent inconsistent revocation state |

Never use raw tokens, Refresh Tokens, client secrets, or sensitive identifiers as metric labels. When events must be correlated, use internal identifiers with restricted access and clear retention policies.

### 18.2. Protecting the Revocation Endpoint

- Require HTTPS; never accept tokens via query string.
- Enforce client authentication, client ownership, and per-grant policies.
- Apply rate limiting; block brute force and token enumeration.
- Handle errors without disclosing token/user identity.
- Never log Revocation Request bodies or `Authorization` headers.
- Do not open CORS to arbitrary origins without explicit justification and controls.
- If cookie-based internal logout/revoke endpoints exist, protect against CSRF and session fixation.
- Separate a user's right to revoke their own session from an administrator's right to revoke another client/user.

### 18.3. Incident Runbook When a Refresh Token Is Compromised

A practical procedure may include:

1. Confirm the incident and identify the relevant authorization/device/client using trusted metadata.
2. Invalidate the current Refresh Token and its token family if policy supports it.
3. Revoke Access Tokens in the same authorization; enforce via denylist/introspection or known risk window.
4. Terminate affected login sessions as needed.
5. If client credentials/private keys were compromised, rotate or disable credentials.
6. Bring Resource Servers to a state where the token is rejected within SLO.
7. Audit unusual activity, scopes/audiences, refresh reuse, and any access post-revocation.
8. Wipe tokens from client storage, clear caches, and verify actual state.

Do not delete audit records before preserving necessary evidence, while adhering to privacy and retention policies. If revocation fails mid-way, provide controlled retries, idempotency, and operational alerts.

## 19. Production Deployment Checklist

1. **Endpoint:** `/oauth2/revoke` is enabled with client authentication matching each client type.
2. **RFC 7009:** form-encoded POST, optional `token_type_hint`, HTTP 200 does not disclose token existence.
3. **Ownership:** token belongs to the authenticated client; admin APIs enforce RBAC/tenant checks.
4. **Revocation scope:** distinguish access-only, refresh+access, authorization, device, and user-wide.
5. **Cascade policy:** clear decision on Refresh Tokens and Access Tokens in the same grant.
6. **Authorization store:** invalidation persists durably; all nodes observe consistent state.
7. **JWT:** accept offline validation limits or implement a denylist/online check.
8. **Opaque:** introspection returns `active=false`; caching does not violate SLO.
9. **Rotation:** `reuseRefreshTokens(false)` only configures rotation; it does not replace token-family detection.
10. **Concurrency:** concurrent refresh/revoke operations are tested and transactionally sound.
11. **Sessions/consent:** logout, authorization revocation, and consent removal are kept distinct.
12. **Token binding:** DPoP/mTLS does not replace revocation.
13. **Privacy:** never write tokens/secrets to logs; audit using protected metadata.
14. **Monitoring:** measure propagation latency, errors, stale caches, and reuse attempts.
15. **Recovery:** incident response, bulk revocation, and post-revocation verification runbooks exist.
16. **Tests:** cover both the endpoint and Resource Server/multi-node effects.

## 20. Exercises and Self-Assessment Questions

**Exercise A — RFC 7009.** A client sends a nonexistent token to the Revocation Endpoint, while the client is authenticated and the request is valid. Which HTTP status should the server return? Why not return "token not found"?

**Exercise B — Single-Device Logout.** Alice has a laptop and a phone, each with its own authorization. Design the record/device association and command to revoke only the laptop without affecting the phone.

**Exercise C — Cascade.** Alice has Access Token A and Refresh Token R in the same authorization. The user requests a complete logout. Describe the target state for A and R, and determine what the Resource Server must do if A is an offline JWT.

**Exercise D — JWT vs. Opaque.** A system needs revocations reflected at APIs within a short window. Compare introspection with a JWT denylist and short-lived JWTs across latency, availability, caching, and complexity.

**Exercise E — Refresh Token Reuse.** R1 was exchanged for R2. R1 appears again from another IP/device. Design the family state, incident signals, and revocation strategy. Explain why simply enabling `reuseRefreshTokens(false)` is not enough.

**Exercise F — Authorization vs. Consent.** A user revokes application permissions and wants to be prompted for consent again next time. Which records/tokens need handling? Why is deleting consent alone insufficient?

**Exercise G — Multi-Node.** Node A receives revoke, Node B receives refresh, Node C receives introspection, and Resource Server D uses a JWT denylist. Design tests verifying no path continues granting or accepting access outside the SLO.

**Review Questions:**

1. Which parameters does RFC 7009 require, and what is the role of `token_type_hint`?
2. Why does the server return HTTP 200 for a nonexistent token?
3. Does revoking an Access Token always revoke the Refresh Token?
4. What does RFC 7009 recommend when a Refresh Token is revoked?
5. How does `OAuth2AuthorizationService` differ from `OAuth2AuthorizationConsentService`?
6. Does `OAuth2Authorization.Token.isActive()` reflect invalidation?
7. Why can an offline JWT still call APIs successfully after revocation at the Authorization Server?
8. What must a Resource Server using introspection watch out for when caching `active=true`?
9. Why can a single user have multiple `OAuth2Authorization` records?
10. What do token families and rotation mean when Refresh Token reuse is detected?
11. Does `@Transactional` automatically ensure API caches see revocations immediately?
12. Does revoking an authorization automatically log out an OIDC browser session?
13. Why is `client_id` in a request insufficient to permit administrative revocation?
14. Which tests prove actual revocation propagation time?

## 21. References

- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7009, Section 2 — Token Revocation](https://www.rfc-editor.org/rfc/rfc7009#section-2)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)

**Remember:** Token revocation has three layers that cannot be skipped: **the Authorization Server updates state**, **policy determines which related tokens/authorizations must also be terminated**, and **Resource Servers actually reject revoked tokens**. Revoking a Refresh Token blocks renewal; revoking an Access Token is effective at APIs only if APIs are aware of that state; removing `OAuth2Authorization` does not automatically delete browser sessions, consent, or all other authorizations of the user. Always clearly define scope, cascading, consistency, propagation time, and test end-to-end from the HTTP Revocation Endpoint to APIs.
