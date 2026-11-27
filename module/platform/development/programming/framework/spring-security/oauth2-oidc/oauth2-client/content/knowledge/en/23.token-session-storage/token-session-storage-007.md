# 23.7. Serialization, TTL, and Cleaning Up Expired Token Data

## Lesson Objectives

In **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client**, receiving an access token is only the first step. The application must also manage **how token data is saved and restored (serialization)**, **storage lifetimes (TTL — Time To Live)**, and **rules for deleting old data** without losing still-valid refresh tokens.

A classic mistake is setting the TTL of the entire `OAuth2AuthorizedClient` equal to the access token's lifetime. If access token `A1` expires after 10 minutes while refresh token `R1` remains usable for days, deleting the authorized client at minute 10 wipes out `R1` as well. The application can no longer refresh tokens and may force the user through a brand-new Authorization Code flow.

The opposite mistake is equally dangerous: retaining every session and token forever expands credential exposure risk, consumes storage, accumulates dead records, and complicates privacy/retention compliance.

After this lesson, you can:

- Distinguish `OAuth2AuthorizedClient`, `SecurityContext`, OIDC principals, and pending Authorization Requests awaiting callbacks.
- Explain how state is serialized when using `HttpSession`, Spring Session Redis, or a database.
- Understand risks of Java serialization, JSON polymorphic deserialization, and serialized object graphs when upgrading Spring Security.
- Distinguish access token expiry, refresh token expiry, session idle timeout, data retention, and cache-key TTLs.
- Design cleanup logic that does not delete an authorized client merely because its access token expired when its refresh token is still usable.
- Structure Redis TTLs, custom JDBC schemas, and bounded scheduled cleanup batches.
- Mitigate races between refresh token rotation and cleanup jobs.
- Understand logout, account switching, token revocation, and cleanup across each storage type.
- Use `Clock` and integration tests to verify expiry/serialization without waiting in real time.
- Monitor cleanup with metrics/logs containing zero raw tokens.

## 1. Context: A Portal Stores Multiple Types of State

Suppose an **Employee Portal** uses Spring Security OAuth2 Login with an OpenID Provider (OP), then calls the **Orders API** using an access token.

~~~text
Browser
  └── Session cookie

Employee Portal
  ├── SecurityContext
  │   └── Authentication / OidcUser
  ├── OAuth2AuthorizedClient(corporate, Alice)
  │   ├── Access token A1
  │   └── Refresh token R1 (if issued by AS)
  └── Pending Authorization Request awaiting callback
      ├── state
      ├── PKCE code_verifier
      └── OIDC nonce if applicable

OpenID Provider / Authorization Server
  └── SSO session, grant/consent, token policy

Orders API / Resource Server
  └── Validates access token and business permissions
~~~

These are state types with **different purposes and lifetimes**. They must not all be deleted or extended by a single shared clock.

### 1.1. Comparison Table

| Data | Purpose | Who Determines Its Lifetime? |
|---|---|---|
| Access token | Calling Resource Servers | Authorization Server and token metadata |
| Refresh token | Requesting new access tokens | Authorization Server and rotation/revocation policies |
| `OAuth2AuthorizedClient` | Binds tokens to registration/principal | Client repository/service design and retention policy |
| `SecurityContext` / `Authentication` | Identifies logged-in Portal user | Application session/security mechanism |
| `HttpSession`/`WebSession` | State per browser session | Idle timeout, plus absolute lifetime if configured |
| OP SSO session | Supports SSO/reauthentication | OP policy |
| `OAuth2AuthorizationRequest` | Correlation during Authorization Code flow | Authorization transaction timeout |
| Stored claims of OIDC principal | Supports authentication/authorization | Session and data-minimization policies |

**An expired token does not mean the login session ended**, and a live session does not guarantee the access token is valid.

### 1.2. Illustrative Timeline

~~~text
09:00  Alice logs in via OIDC.
       Access token A1 lives 10 minutes.
       Refresh token R1 may remain valid for days.
       HttpSession idle timeout is 30 minutes.

09:08  Portal calls Orders API using A1.
09:10  A1 expires.
09:11  Portal can use R1 to obtain A2 if the AS accepts it.
09:25  Session stays alive as user remains active.
09:45  Session may expire due to idle timeout.
10:00  AS may still allow R1 per its policy.
~~~

Numbers are illustrative only. Depending on where authorized clients are stored, session expiry might simultaneously drop the Portal's copy of `R1` even though the AS has not revoked `R1`.

## 2. Which Objects Actually Need Serialization?

### 2.1. `OAuth2AuthorizedClient`

This object links a `ClientRegistration` with a principal name, an access token, and an optional refresh token.

~~~text
OAuth2AuthorizedClient
  clientRegistration = corporate
  principalName = alice
  accessToken
    tokenValue = A1
    tokenType = Bearer
    issuedAt = ...
    expiresAt = ...
    scopes = [...]
  refreshToken (if issued)
    tokenValue = R1
    issuedAt = ...
    expiresAt = may be null
~~~

Token values are **sensitive credentials**. A JSON or Java-serialized snapshot holds enough data for an attacker to replay the token unless sender-constraining mechanisms apply.

### 2.2. `SecurityContext` and OIDC Principals

After OIDC Login, `SecurityContext` may contain an `Authentication` such as `OAuth2AuthenticationToken`, with an `OidcUser` principal and claims like issuer, subject, email, groups, or roles.

This is **user authentication state at the Portal**, distinct from the access token stored in `OAuth2AuthorizedClient` for calling APIs.

Custom principals, authorities, or authentication details may hold non-serializable classes. Inspect **the entire real object graph**, not just the outer framework wrapper class.

### 2.3. `OAuth2AuthorizationRequest`

Before the Authorization Code callback, the client needs correlation data such as `state`, the PKCE verifier, and the OIDC nonce when applicable.

~~~text
Start OAuth2 Login
  -> Create OAuth2AuthorizationRequest
  -> Save state/PKCE/nonce
  -> Redirect browser to OP
  -> Callback
  -> Load matching request and verify
  -> Token exchange
~~~

If the authorization request's TTL is too short, the returning callback may fail with missing/invalid state even though the OP authenticated the user.

If correlation data is kept too long, sensitive state/verifiers linger unnecessarily.

**The pre-callback Authorization Request repository is separate from the post-exchange Authorized Client repository.**

### 2.4. Do Not Serialize More Than Necessary

An application may not need to store the entire ID token, raw UserInfo JSON, or every claim inside a custom token store.

Define clearly:

- Which tokens must be stored to call APIs?
- Which claims are needed for session `Authentication`?
- Which fields are needed for only a single request?
- Which fields are personal data requiring separate retention/cleanup?

Minimal design reduces how many credentials can leak from session dumps, Redis backups, or database snapshots.

## 3. Token Storage Repositories and Services in Spring Security

### 3.1. Servlet: `OAuth2AuthorizedClientRepository`

An interface scoped to HTTP Servlet requests/responses, with implementations such as `HttpSessionOAuth2AuthorizedClientRepository`.

If authorized clients live in `HttpSession`:

~~~text
Alice's HttpSession
  └── OAuth2AuthorizedClient(corporate)
      ├── A1
      └── R1
~~~

When the session is invalidated or expires, session-backed data is dropped. This can be the exact right policy for web apps that never use tokens after the user leaves the session.

### 3.2. Service: `OAuth2AuthorizedClientService`

The service saves/loads/removes authorized clients by registration ID and principal name without requiring an `HttpServletRequest`.

Available options include:

- `InMemoryOAuth2AuthorizedClientService`.
- `JdbcOAuth2AuthorizedClientService`.
- Custom implementations backed by Redis, JDBC, or another store.

`AuthenticatedPrincipalOAuth2AuthorizedClientRepository` can coordinate delegating to a service for authenticated principals and another repository for anonymous ones, depending on wiring.

**Records stored outside the session can survive logout** unless the application explicitly cleans them up.

### 3.3. WebFlux/Reactive

WebFlux provides `ServerOAuth2AuthorizedClientRepository`, `ReactiveOAuth2AuthorizedClientService`, and reactive managers.

WebFlux `WebSession` differs from Servlet `HttpSession`. When using Spring Session Redis, verify the actual serializer and repository wired into your running stack.

### 3.4. Choosing Storage by Requirement

| Storage | Strengths | Risks to Control |
|---|---|---|
| In-memory | Simple for demos/tests | Lost on restart; not shared across nodes |
| `HttpSession` | Matches browser session lifecycle | Session timeout can drop refresh tokens |
| Spring Session Redis | Shared sessions across instances | Serializers, Redis TTL, backups, and access controls |
| JDBC service | Survives restarts | Needs cleanup, encryption, concurrency control |
| Custom Redis authorized client store | Fast TTLs/lookups | Wrong TTL can wipe `R1`; eviction differs from expiry |
| Custom encrypted DB | Explicit schema/retention/versioning | Must manage crypto, migrations, and locking yourself |

No single option fits every system. The choice depends on whether tokens must survive **outside the browser session**.

## 4. What Does Serialization Mean for Tokens?

Serialization converts objects into bytes, JSON, or columns for storage; deserialization reconstructs usable state.

~~~mermaid
flowchart TD
    A["OAuth2AuthorizedClient / Session state"] --> B["Serialization / DTO mapping"]
    B --> C["Ciphertext / bytes / JSON / columns"]
    C --> D["Redis / Database / Session store"]
    D --> E["Load + decryption + deserialization"]
    E --> F["Authorized client / SecurityContext"]
    F --> G["AuthorizedClientManager / API request"]
~~~

Risks:

1. **Confidentiality:** raw tokens exposed via Redis/database/backups/logs.
2. **Integrity:** tampered payloads or swapped registration/principal associations.
3. **Compatibility:** Spring Security upgrades making older objects unreadable.
4. **Availability:** serialization failures breaking login, sessions, or token retrieval.
5. **Performance:** bloated payloads increasing memory, network traffic, and CPU.

## 5. Java Native Serialization

Some session stores use Java serialization for session attributes.

For complex object graphs like `SecurityContext` holding custom principals/authorities, serializability depends on every nested object stored.

### 5.1. Common Issues

- `NotSerializableException` when a custom object does not implement `Serializable`.
- `InvalidClassException` when classes or `serialVersionUID` change.
- Renamed classes/packages after library upgrades.
- Opaque byte payloads that are hard to inspect or migrate across services.
- Java deserialization vulnerabilities if bytes come from untrusted sources.
- Payloads holding sensitive claims/tokens that cannot be treated as ordinary data.

**Never deserialize untrusted bytes with Java native serialization.** If you must use it, restrict allowed classes/serializers, secure storage, enforce integrity, and test compatibility.

### 5.2. Do Not Treat Framework Objects as a Long-Term Schema

Even though many Spring Security types implement `Serializable`, treating framework object graphs as a long-term token storage schema carries risks during rolling deployments or major upgrades.

Custom token stores are more stable when using **explicit DTOs** and versioned schemas.

## 6. JSON Serialization and Polymorphic Typing Risks

JSON is easy to inspect structurally, yet **does not protect credentials by itself**.

Example never to store unencrypted:

~~~json
{
  "registrationId": "corporate",
  "principalName": "alice",
  "accessToken": "ACCESS_TOKEN_RAW",
  "refreshToken": "REFRESH_TOKEN_RAW"
}
~~~

If a file or Redis snapshot is read, the tokens are exposed.

### 6.1. JSON Mappers Need a Safe Schema

Watch out for:

- Default typing allowing payloads to instantiate arbitrary classes.
- Polymorphic deserialization of custom `Authentication` types.
- Jackson modules/mixins mismatched with your Spring Security version.
- `Instant`, token types, scopes, enums, or nested values failing round-trips.
- Optional fields deserializing as `null` and accidentally wiping refresh tokens on updates.

When using Jackson for Spring Security types, use version-matched integrations/mixins and restrict allowed types. Never enable global permissive deserialization as a quick fix for an unreadable session.

### 6.2. Explicit DTOs Are Easier to Migrate

An application-owned DTO can evolve cleanly by version instead of coupling to internal framework class names.

Illustrative example:

~~~java
import java.time.Instant;
import java.util.Set;

public record StoredAuthorizedClientV1(
        int schemaVersion,
        String registrationId,
        String principalKey,
        String accessTokenCiphertext,
        String accessTokenType,
        Instant accessTokenIssuedAt,
        Instant accessTokenExpiresAt,
        Set<String> scopes,
        String refreshTokenCiphertext,
        Instant refreshTokenIssuedAt,
        Instant refreshTokenExpiresAt,
        Instant lastUsedAt,
        long recordVersion) {
}
~~~

This is a DTO for **custom storage**, not a required Spring Security API schema.

Meaning:

| Field | Purpose |
|---|---|
| `schemaVersion` | Read and migrate payloads across upgrades |
| `registrationId` | Selects client registration |
| `principalKey` | Binds tokens to the right user/service |
| `accessTokenCiphertext` | Encrypted token for storage |
| `accessTokenExpiresAt` | Tracks access token expiration |
| `refreshTokenCiphertext` | Encrypted refresh credential if present |
| `refreshTokenExpiresAt` | Nullable if the AS does not provide one |
| `lastUsedAt` | Inactivity-based retention when designed |
| `recordVersion` | Optimistic concurrency during rotation/cleanup |

### 6.3. Do Not Trust Client Metadata from Payloads

When reconstructing an authorized client from a custom DTO, fetch the active `ClientRegistration` from a trusted `ClientRegistrationRepository`.

Never let a serialized payload override issuer, token endpoint, or client authentication method simply because those fields were once serialized.

## 7. Encryption and Integrity for Token Stores

Access tokens and refresh tokens are credentials. In custom stores, encrypt token fields using AEAD (such as AES-GCM) or an organization-approved encryption service.

~~~text
Raw token
  -> AEAD encrypt with active key
  -> ciphertext + nonce + key identifier
  -> database/Redis

When needed:
  -> load record for the right principal
  -> verify/decrypt
  -> pass token to HTTP client for the intended Resource Server
~~~

Keep in mind:

- Never reuse nonces unsafely under the same key.
- Manage encryption keys via KMS/secret managers where appropriate.
- Plan key rotation and decrypting older records.
- Bind associated data (AAD) to registration and principal/tenant to prevent swapping ciphertexts across rows.
- Minimize where tokens appear in plaintext.
- Restrict access to DB, Redis, backups, and logs.

**Disk encryption alone does not replace application-level access control**; anyone with DB query rights can still read plaintext written by the app.

### 7.1. Backups Contain Credentials

A Redis RDB/AOF snapshot or database backup can still hold `R1` after the live record is cleaned up.

Enforce retention, encryption, access controls, and deletion/revocation procedures per policy. Never treat deleting a Redis key as proof the token disappeared from all backups.

### 7.2. Never Log Serialized Objects

Avoid:

~~~java
logger.info("authorizedClient={}", authorizedClient);
logger.info("sessionAttributes={}", sessionAttributes);
~~~

`toString()` or debug serializers can accidentally dump tokens, claims, or cookies. Log only controlled metadata.

## 8. Access Token Expiry Differs from Record TTL

An access token carries metadata:

~~~java
var accessToken = authorizedClient.getAccessToken();

Instant issuedAt = accessToken.getIssuedAt();
Instant expiresAt = accessToken.getExpiresAt();
~~~

`expiresAt` marks **when the access token expires**, not when the entire `OAuth2AuthorizedClient` must be deleted.

### 8.1. Clock Skew

Managers/providers may treat an access token nearing expiration as needing early refresh within a clock-skew window.

A token with only a few seconds left may expire before reaching the Orders API, so never check only `now < expiresAt` and assume the API will definitely accept it.

### 8.2. An Unexpired Access Token Can Still Be Rejected

An access token can be revoked or carry the wrong audience/issuer/scope. Resource Servers must still validate tokens and business permissions.

Client-side cleanup is not API-side token validation.

### 8.3. Different Grants Behave Differently

- `authorization_code`: may receive a refresh token depending on AS policy.
- `refresh_token`: uses the stored refresh token to request a new token.
- `client_credentials`: typically requests a new token via client authentication when the old one expires, often with no refresh token.

An expired `client_credentials` service record may be purged to trigger fresh issuance, factoring in manager/provider behavior and actual request rates.

## 9. Refresh Token Expiry May Be Unknown

An `OAuth2RefreshToken` may include issuance and expiration timestamps when supplied. However, OAuth 2.0 token responses do not mandate a universal refresh token expiry field in every case.

You may encounter:

~~~text
access_token.expiresAt = 2026-11-16T10:00:00Z
refresh_token.issuedAt = 2026-11-16T09:50:00Z
refresh_token.expiresAt = null
~~~

**`null` does not mean the refresh token lasts forever or is already expired.** It means the application does not have an explicit expiry timestamp in the held object.

The AS can still enforce:

- Absolute expiry.
- Inactivity timeout.
- Revocation.
- Consent withdrawal.
- Client disabling.
- Refresh token rotation.
- Reuse detection.
- Rules bound to session/tenant/client.

### 9.1. AS-Specific Metadata

Some AS implementations return custom fields for refresh expiry. If you use them:

1. Follow the AS's exact contract.
2. Confirm units (seconds/milliseconds vs. absolute timestamp).
3. Handle missing fields gracefully.
4. Never apply one provider's custom logic to all other providers.
5. Avoid guessing expiry by decoding opaque refresh tokens.

### 9.2. Retention When Refresh Expiry Is Unknown

An application can adopt a policy like "delete records after 30 days of inactivity", but that is a **data-retention policy**, not a claim that `R1` expired at the AS.

Accept the trade-off: users may need to reauthorize even when the AS would still have accepted the refresh token.

## 10. Session TTL Is Independent from Token TTL

Illustrative example:

| Component | Hypothetical Lifetime | What Happens Upon Expiry? |
|---|---|---|
| Access token `A1` | 10 minutes | API rejects expired token |
| Refresh token `R1` | Per AS, possibly many days | AS rejects refresh once invalid |
| Portal `HttpSession` idle timeout | 30 minutes | Session may be invalidated |
| OP SSO session | Per OP | OP may require re-login |
| Pending authorization request | A few minutes | Callback lacks correlation data |
| DB authorized client retention | Per app policy | Record may be deleted even if AS hasn't revoked |

### 10.1. Session-Backed Authorized Clients

If tokens are stored inside `HttpSession`, losing the session drops the token record. This fits well when the app only calls APIs during an active browser session.

If a scheduled job must call APIs on the user's behalf after the browser closes, session-scoped storage is insufficient; design offline access/consent, service storage, and dedicated security policies.

### 10.2. Session Idle Timeout vs. Absolute Session Lifetime

Idle timeout measures inactivity. Absolute lifetime (if implemented) caps total duration since login.

Never treat refreshing an access token as proof the user recently reauthenticated. Authentication freshness or step-up requires dedicated OIDC request parameters/claims and policies.

### 10.3. OP Session vs. Portal Session

Portal logout or session timeout does not guarantee the OP SSO session ended. Conversely, OP session expiry does not automatically delete Portal authorized client records.

## 11. Cleanup Rules: Do Not Delete Too Early

The key question before deleting an authorized client record:

**Can this record still be used to call APIs or obtain a valid refreshed access token?**

| Access Token | Refresh Token | Typical Decision |
|---|---|---|
| Unexpired | Absent | Keep while still needed |
| Unexpired | Present | Keep |
| Expired | Absent | Eligible for deletion after grace/retention |
| Expired | Present, valid | **Keep to refresh** |
| Expired | Present, unknown expiry | **Do not delete solely due to access token expiry** |
| Expired | Present, known expiry passed | Eligible for deletion |
| Unexpired | Refresh token expired | May keep access token until it expires |
| Any | Revocation/disconnect confirmed | Clean up per policy |
| Any | User account deleted or unauthorized | Clean up per account/privacy policy |

### 11.1. Anti-Pattern: TTL Equal to Access Token Expiry

If `A1` expires in 10 minutes and `R1` remains valid for days:

~~~text
Redis key:
  authorized-client:corporate:alice
TTL:
  600 seconds

Value:
  accessToken=A1
  refreshToken=R1
~~~

When Redis evicts the key at 10 minutes, the client loses **both `A1` and `R1`**.

If your policy relies on keeping `R1` for refreshes, this design is broken.

### 11.2. Never Run a Query Deleting All Expired Access Tokens

Avoid:

~~~sql
DELETE FROM oauth2_authorized_client_store
WHERE access_expires_at < NOW();
~~~

It deletes records that still hold valuable refresh tokens.

### 11.3. Grace Period

To delete unrefreshable records safely, use a cutoff:

~~~text
cutoff = now - 5 minutes
~~~

This delays cleanup to reduce races with in-flight requests. It **does not extend access token validity at the AS**.

### 11.4. When Refresh Expiry Is Unknown

Never treat `null` as expired. Without a deliberate inactivity or maximum-retention policy, cleaning up based purely on access expiry breaks refresh flows.

## 12. State Machine for Tokens and Cleanup

~~~mermaid
flowchart TD
    A["Authorized client record"] --> B{"Is access token still usable?"}
    B -->|Yes| C["Keep for authorized usage"]
    B -->|No| D{"Is refresh token present?"}
    D -->|No| E["Cleanup candidate per policy"]
    D -->|Yes| F{"Is refresh token definitely invalid?"}
    F -->|Unknown / usable| G["Keep so manager can attempt refresh"]
    F -->|Confirmed expired/revoked| H["Cleanup candidate"]
    G --> I{"Refresh succeeded?"}
    I -->|Yes| J["Save A2 and R1/R2 accordingly"]
    I -->|No| K["Failure handling; no blind retries"]
    E --> L["Clean up after grace/retention"]
    H --> L
~~~

This is a client-side policy. Whether a token is actually accepted by the AS/RS must still be verified through protocol exchanges and server policies.

## 13. Java Example: Policy Identifying Expired Unrefreshable Records

Assuming `StoredAuthorizedClientV1` above:

~~~java
import java.time.Instant;

public final class AuthorizedClientCleanupPolicy {

    private AuthorizedClientCleanupPolicy() {}

    public static boolean mayDeleteExpiredUnrefreshable(
            StoredAuthorizedClientV1 client,
            Instant cutoff) {

        if (client.accessTokenExpiresAt().isAfter(cutoff)) {
            return false;
        }

        if (client.refreshTokenCiphertext() == null) {
            return true;
        }

        return client.refreshTokenExpiresAt() != null
                && !client.refreshTokenExpiresAt().isAfter(cutoff);
    }
}
~~~

Explanation:

1. Access token is still after cutoff: do not delete under this rule.
2. Access token expired and no refresh token: eligible for deletion.
3. Refresh token exists with unknown expiry: do not delete purely on access expiry.
4. Refresh token has a known expiry past cutoff: eligible for deletion if access token is also past cutoff.

**This is custom storage logic**, not a built-in Spring Security method.

It does not yet cover user disconnect, revocation, maximum retention, or migration logic when a registration changes issuer/client ID.

## 14. Custom JDBC Schema and Cleanup

A custom store can design its own table:

~~~sql
CREATE TABLE oauth2_authorized_client_store (
    id                  BIGSERIAL PRIMARY KEY,
    registration_id     VARCHAR(100) NOT NULL,
    principal_key       VARCHAR(255) NOT NULL,
    access_token_ct     BYTEA NOT NULL,
    access_expires_at   TIMESTAMPTZ NOT NULL,
    refresh_token_ct    BYTEA,
    refresh_expires_at  TIMESTAMPTZ,
    last_used_at        TIMESTAMPTZ,
    record_version      BIGINT NOT NULL DEFAULT 0,
    UNIQUE (registration_id, principal_key)
);
~~~

This is **illustrative DDL for PostgreSQL/custom stores**. Never assume it is `JdbcOAuth2AuthorizedClientService`'s built-in schema.

### 14.1. Cleanup Without Deleting Usable Refresh Tokens

Illustrative query:

~~~sql
DELETE FROM oauth2_authorized_client_store
WHERE access_expires_at < :cutoff
  AND (
       refresh_token_ct IS NULL
       OR (
           refresh_expires_at IS NOT NULL
           AND refresh_expires_at < :cutoff
       )
  );
~~~

If `refresh_token_ct` is present while `refresh_expires_at` is `NULL`, this query will not delete the record based on access expiry alone.

To enforce maximum record age or inactivity limits, add an **explicitly defined** condition, noting it may require users to reauthorize.

### 14.2. Batch Cleanup to Avoid Heavy Load

PostgreSQL example:

~~~sql
WITH candidates AS (
    SELECT id
    FROM oauth2_authorized_client_store
    WHERE access_expires_at < :cutoff
      AND (
          refresh_token_ct IS NULL
          OR (
              refresh_expires_at IS NOT NULL
              AND refresh_expires_at < :cutoff
          )
      )
    ORDER BY access_expires_at, id
    LIMIT :batch_size
    FOR UPDATE SKIP LOCKED
)
DELETE FROM oauth2_authorized_client_store t
USING candidates c
WHERE t.id = c.id;
~~~

This is custom SQL running inside an appropriate transaction; placeholders `:cutoff` and `:batch_size` require binding via e.g. `NamedParameterJdbcTemplate`.

### 14.3. Index Supporting Cleanup

~~~sql
CREATE INDEX idx_oauth_client_access_exp
ON oauth2_authorized_client_store (access_expires_at);
~~~

Evaluate query plans, row counts, refresh/update frequency, and index write overhead.

### 14.4. Do Not Apply Directly to the Default Schema

`JdbcOAuth2AuthorizedClientService` uses Spring Security's own schema and column mapping. Before running SQL cleanup directly, inspect the actual DDL and how the service maps rows. Never assume the default schema has `refresh_expires_at` like the custom example table.

## 15. Scheduled Cleanup Job

Spring `@Scheduled` can run periodic cleanup, but cleanup policy is an application responsibility, not an automatic guarantee of the authorized client service.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class AuthorizedClientCleanupJob {

    private final AuthorizedClientCleanupRepository repository;
    private final Clock clock;

    public AuthorizedClientCleanupJob(
            AuthorizedClientCleanupRepository repository,
            Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }

    @Scheduled(
            fixedDelayString =
                    "${security.oauth2.cleanup.delay-ms:900000}")
    public void cleanup() {
        Instant cutoff = Instant.now(clock)
                .minus(Duration.ofMinutes(5));

        int deleted = repository.deleteExpiredUnrefreshable(
                cutoff, 500);

        // Record count metric only; never log tokens.
        recordCleanupMetric(deleted);
    }

    private void recordCleanupMetric(int deleted) {
        // Hook into the application's metrics system.
    }
}
~~~

Custom repository contract:

~~~java
import java.time.Instant;

public interface AuthorizedClientCleanupRepository {
    int deleteExpiredUnrefreshable(Instant cutoff, int maxRows);
}
~~~

Clock configuration:

~~~java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
public class SchedulingConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

These snippets show the architecture; `deleteExpiredUnrefreshable` must be backed by proper SQL/Redis operations and safe transactions.

### 15.1. Running Across Multiple Instances

With three Portal instances, `@Scheduled` on each node can trigger three concurrent jobs.

Consider distributed locking, leader election, a dedicated job service, or batch queries using row locks/`SKIP LOCKED` where appropriate.

Never assume Spring scheduling runs only once cluster-wide by default.

### 15.2. Bounding Volume

Cleanup should:

- Delete in batches.
- Enforce time/load limits.
- Avoid long-held transactions.
- Emit metrics for rows deleted and backlog.
- Alert if deletion counts spike abnormally.
- Never run unbounded cleanup loops on request threads.
- Never write raw tokens into job logs.

## 16. Redis TTL and Eviction

Redis provides automatic key TTLs, yet the TTL must match **record lifecycle**, not necessarily access token expiry.

### 16.1. Key Holding a Usable R1

~~~text
SET authorized-client:corporate:alice encrypted-value EX 600
~~~

If the key holds `A1/R1` and `R1` can still refresh after 600 seconds, this command deletes `R1` prematurely.

### 16.2. Session-Scoped TTL

With Spring Session Redis, session keys follow the session lifecycle. This works well when token data only needs to live while the browser session is valid.

However, if offline/background access is required, store tokens outside the session with an independent policy.

### 16.3. TTL When Refresh Expiry Is Known

If the AS provides reliable refresh token expiry, record TTL can factor in:

- Refresh expiry.
- Access expiry if later.
- Grace period.
- Data-retention policy.
- Clock skew.
- Rotation updating tokens and expiries.

Do not slide the TTL forward endlessly on every read if retention policy enforces an absolute maximum age.

### 16.4. Unknown Refresh Expiry

Use an approved inactivity or maximum-retention policy, without assuming `R1` expired merely because its expiry field is absent.

Make clear that retention-driven deletion may require the user to reauthorize.

### 16.5. Eviction Differs from Expiry

Even with a long TTL, Redis can evict keys under memory policies. Evaluate eviction policies, persistence, replication, backups, and failover if the token store must be durable.

Never assume a Redis cache is a durable token repository for every use case.

## 17. Refresh Token Rotation and Races with Cleanup

Suppose the current record is `A1/R1` and the AS enforces refresh token rotation:

~~~text
Request A: load A1/R1
Request B: load A1/R1

A: refresh(R1) -> A2/R2
B: refresh(R1) -> invalid_grant or reuse detection
~~~

If Request B writes `A1/R1` back after A saved `A2/R2`, the system loses the newer refresh token.

### 17.1. Cleanup Racing with Refresh

~~~text
Cleanup: finds A1/R1 based on stale snapshot
Request A: refreshes R1 -> saves A2/R2
Cleanup: deletes record even though it was updated
~~~

Ensure deletion conditions are rechecked inside the executing transaction, not based on a stale snapshot.

### 17.2. Optimistic Locking

With a custom table having `record_version`:

~~~sql
UPDATE oauth2_authorized_client_store
SET
    access_token_ct = :access_ct,
    access_expires_at = :access_expires_at,
    refresh_token_ct = :refresh_ct,
    refresh_expires_at = :refresh_expires_at,
    record_version = record_version + 1
WHERE id = :id
  AND record_version = :expected_version;
~~~

If 0 rows are updated, the record changed concurrently; reload and decide the next step.

Never retry the token endpoint endlessly with an old refresh token, especially when the AS rotates tokens.

### 17.3. When the Response Omits a New Refresh Token

If a refresh response succeeds with `A2` and no `R2`, Spring Security's standard provider preserves the stored `R1`.

Never overwrite `R1` with `null` from the response. Conversely, when the AS returns `R2`, save `R2` and replace `R1` per rotation.

### 17.4. TTL Alone Is Insufficient

TTL does not protect atomicity when multiple requests refresh the same record simultaneously. Concurrency control must be designed independently of expiry policies.

## 18. Role of `OAuth2AuthorizedClientManager`

The manager coordinates providers and authorized client storage.

Examples:

- `DefaultOAuth2AuthorizedClientManager` for Servlet requests.
- `AuthorizedClientServiceOAuth2AuthorizedClientManager` for service/background use outside Servlet requests.
- `DefaultReactiveOAuth2AuthorizedClientManager` for WebFlux requests.
- `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` for reactive background/service use.

### 18.1. The Manager Is Not a Cleanup Scheduler

When `A1` expires and `R1` exists, the manager/provider uses `R1` to get `A2`. If a cleanup job already deleted `A1/R1`, the manager has no token left to refresh.

### 18.2. Failure Handlers and `invalid_grant`

When the AS rejects a refresh token with `invalid_grant`, several Spring Security managers/handlers remove the authorized client in specific situations.

Exact behavior depends on implementation and configuration. Never treat every network error as revocation, and never retry an AS-rejected refresh token endlessly.

### 18.3. 401/403 from Resource Servers Is Not Expiry Cleanup

An API may return 401 due to wrong audience/issuer or revocation. 403 typically means missing scope/business permissions.

Never wipe the entire session/token store because of an unclassified HTTP error.

## 19. Logout, Disconnect, and Account Switching

### 19.1. Local Logout

If authorized clients live in `HttpSession`, invalidating the session normally drops them. If tokens live in an external `OAuth2AuthorizedClientService`, logout does not automatically delete them.

### 19.2. Local Deletion vs. Token Revocation

`removeAuthorizedClient` removes application-side data without calling the AS revocation endpoint automatically.

When a user disconnects a provider, you may need to:

- Remove the local authorized client.
- Revoke tokens at the AS if supported and required by policy.
- Handle sessions/cookies.
- Unlink the account association.
- Review caches, backups, and retention.

### 19.3. Account Switching

Alice logs out and Bob logs in within the same browser. If the store retains Alice's token and a controller mistakenly uses it for Bob, that is a token-ownership bug.

Bind tokens strictly to registration/principal, clean up on account switches, and rely on OIDC-verified user identities.

### 19.4. Multi-Issuer and Tenancy

OIDC `sub` is unique only within its `iss`. Two OPs can issue the same `sub` to two different people.

When designing `principalKey`, use a trusted internal identity mapped from `iss` + `sub` (and tenant if applicable). Never use unverified self-asserted emails as a system-wide key.

## 20. Serialization Across Spring Security Upgrades

A distributed session store may contain `Authentication`/Principal instances serialized using classes from an older version.

When upgrading Spring Security or your app:

- Class/package names may change.
- JSON mixins/modules may change.
- `serialVersionUID` may become incompatible.
- Custom principals may gain or lose fields.
- Serialized payloads may fail to deserialize.

### 20.1. Rolling Deployments

If Portal A runs the old version and Portal B runs the new version, both may read/write the same Redis sessions. Incompatible serializers/schemas cause node-dependent errors for users.

Before rolling out:

1. Identify your production serializer.
2. Test round-trips using realistic fixtures with fake tokens replacing real credentials.
3. Test reading old-version payloads on new code.
4. Test mixed-version nodes for rolling deployments.
5. Prepare migration or session-draining strategies.
6. Never log raw serialized payloads on errors.

### 20.2. Do Not Fix Deserialization by Widening Default Typing

If Jackson does not know how to instantiate an `Authentication`, never enable unrestricted polymorphic typing allowing arbitrary classes in payloads.

Instead, use controlled, version-matched mappers/modules/mixins or move to an explicit schema.

### 20.3. When Older Schemas Lack Refresh Expiry

If the AS previously omitted refresh expiry, migrated rows may still have `refreshExpiresAt == null`.

Never backfill `now` or access expiry into the new field; doing so can cause cleanup to delete still-valid refresh tokens.

## 21. Metrics, Logging, and Auditing

Cleanup must be observable without exposing tokens.

Illustrative metrics:

~~~text
oauth2_authorized_client_records_total
oauth2_authorized_client_cleanup_deleted_total
oauth2_authorized_client_cleanup_backlog
oauth2_authorized_client_deserialization_failures_total
oauth2_authorized_client_refresh_invalid_grant_total
oauth2_authorized_client_store_bytes
oauth2_authorized_client_cleanup_duration_seconds
~~~

Never put access tokens, refresh tokens, JWT assertions, ID tokens, or raw session IDs in metric labels.

### 21.1. Audit Events

Example:

~~~text
event=AUTHORIZED_CLIENT_REMOVED
reason=EXPIRED_UNREFRESHABLE
registrationId=corporate
recordReference=opaque-id
deletedCount=1
timestamp=...
~~~

Avoid:

~~~text
access_token=eyJ...
refresh_token=...
session_cookie=...
serialized_client=...
~~~

### 21.2. Anomaly Signals

- Record counts grow without bound.
- Cleanup backlog climbs.
- Deserialization failures spike after deploys.
- Users are forced to re-login exactly when access tokens expire.
- `invalid_grant` spikes during parallel refreshes.
- Different nodes hold different authorized clients.
- Redis evictions drop tokens prematurely.
- Cleanup jobs delete excessive rows immediately after deployment.

## 22. Testing TTL and Serialization

### 22.1. Expiry Matrix

| Test Case | Expected Behavior |
|---|---|
| `A1` valid, no `R1` | Keep |
| `A1` expired, no `R1` | Eligible for cleanup after grace |
| `A1` expired, `R1` valid | **Keep** |
| `A1` expired, `R1` expiry `null` | **Do not delete on access expiry alone** |
| `A1` expired, `R1` known expiry passed | Eligible for cleanup |
| `A1` valid, `R1` known expiry passed | Do not delete usable access token under this rule alone |
| Refresh succeeds `A1/R1 → A2/R2` | Persist `A2/R2` |
| Refresh response returns `A2` without `R2` | Preserve `R1` per provider semantics |
| Cleanup runs concurrently with refresh | Never delete the newer record |
| User disconnects | Clean up per policy |
| Redis key evicted | Handle missing authorized client per contract |

### 22.2. Use `Clock` Instead of Real Sleeping

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-16T10:00:00Z"),
        ZoneOffset.UTC);
~~~

Injecting `Clock` into policies/jobs makes expiry tests deterministic without `Thread.sleep(...)`.

### 22.3. Serialization Round-Trip Tests

1. Construct an authorized client and `Authentication` with dummy tokens.
2. Serialize through the production serializer.
3. Deserialize back.
4. Verify registration, principal, scopes, token type, and timestamps.
5. Verify refresh token survived accurately.
6. Test payloads missing optional fields.
7. Test legacy schema payloads.
8. Test custom principals/authorities if stored in sessions.
9. Verify error paths log zero credentials.

### 22.4. Integration Tests for Cleanup/Refresh Races

Set up a test store, two refresh requests, and a cleanup job. After the race, verify the record survives if `A2/R2` was saved rather than being deleted by the stale-snapshot cleanup job.

Never use production tokens or replay real refresh tokens against a live production AS just to test reuse detection.

## 23. Troubleshooting

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| Users re-login after exactly 10 minutes | Entire record TTL equals access token lifetime | Redis TTL and storage policy |
| `A1` expired, yet fails to refresh | `R1` was cleaned up prematurely | Repository/service and cleanup job |
| Refreshes once then fails | `R2` not saved or `R1` lost | Rotation, success handler |
| Tokens remain in DB after logout | External non-session store | Cleanup/logout policy |
| Redis session deserialization fails after upgrade | Class/serializer mismatch | Schema/version/mixins |
| Node A has token, Node B does not | In-memory store or unshared sessions | Backing store wiring |
| DB grows endlessly | Missing retention/cleanup | Job, indexes, policy |
| Cleanup deletes new `A2/R2` | Race on stale snapshot | Transactions/CAS |
| `invalid_grant` spikes | Rotation reuse, expiry, revocation | Concurrency and AS policy |
| Refresh expiry is `null` | AS does not provide metadata | Never treat `null` as expired |
| Redis keys vanish before TTL | Eviction/flush/failover | Redis policy/durability |
| API returns 401 | Issuer, audience, expiry, revocation | Resource Server validation |
| API returns 403 | Scope/business permissions | Do not refresh by default |
| Tokens appear in logs | Serializers/debug header dumps | Redaction and credential hygiene |

## 24. Practical Scenarios

### A. TTL Too Short

`A1` lives 10 minutes; `R1` is valid for 14 days. The Redis key storing `A1/R1` has a 600-second TTL.

**Conclusion:** if the app needs to refresh after 10 minutes, this TTL deletes `R1` too early. Set retention intentionally per lifecycle.

### B. Session Timeout While AS Has Not Revoked

The Portal uses `HttpSessionOAuth2AuthorizedClientRepository`. Sessions expire after 30 minutes of inactivity.

**Conclusion:** session data disappears even though the AS has not revoked `R1`. This reflects storage policy, not token expiry.

### C. JDBC Without Cleanup

The authorized client table accumulates stale records from inactive users, some with refresh tokens of unknown expiry.

**Conclusion:** implement a retention/inactivity policy and batched cleanup; never delete every row based solely on access expiry.

### D. Concurrent Refresh and Cleanup

A refresh request saves `A2/R2` while cleanup reads the older `A1/R1` row.

**Conclusion:** use transactions, conditional deletion, or record versioning to protect newer tokens.

### E. Library Upgrade Breaks Sessions

New Spring Security nodes fail to deserialize custom principals written by older nodes.

**Conclusion:** run compatibility tests, plan migrations, or drain sessions. Never enable permissive deserialization.

### F. User Disconnect

Alice disconnects the OP, yet `R1` remains in the DB.

**Conclusion:** delete the local record, handle AS revocation, and govern backup/cache retention per policy.

### G. Refresh Token Without Expiry

`R1` has `expiresAt == null`.

**Conclusion:** do not treat `R1` as expired. If storage duration must be bounded, enforce an explicit retention policy and accept users may need to reauthorize.

### H. Token Leaked in Session Dump

Debug logging prints the full `OAuth2AuthorizedClient`.

**Conclusion:** stop logging credentials, scope exposure, handle affected tokens per security procedure, and add redaction tests.

## 25. Self-Check Questions

**Q1.** Is the access token's `expiresAt` the moment the entire `OAuth2AuthorizedClient` must be deleted?

**Answer:** No. The refresh token may still be valid to obtain a new access token.

**Q2.** Does `OAuth2RefreshToken.getExpiresAt() == null` mean the token lives forever?

**Answer:** No. The client simply lacks explicit expiry info; the AS still enforces expiry and revocation policies.

**Q3.** Are `HttpSession` TTL and access token lifetime the same?

**Answer:** No. One governs the app's session lifecycle, the other governs token validity.

**Q4.** Why can setting a Redis TTL equal to access token lifetime cause bugs?

**Answer:** The key stores both access and refresh tokens; Redis may delete a still-usable refresh token.

**Q5.** Does `JdbcOAuth2AuthorizedClientService` implement all project retention policies automatically?

**Answer:** Never assume so. Inspect the implementation/schema and build appropriate cleanup.

**Q6.** Does JSON serialization encrypt tokens automatically?

**Answer:** No. JSON containing raw tokens is still plaintext secret data.

**Q7.** Why shouldn't you treat Spring Security's object graph as an immutable long-term storage schema?

**Answer:** Classes, fields, serializers, and versions change, breaking compatibility during upgrades and rolling deployments.

**Q8.** What happens if cleanup races with refresh token rotation?

**Answer:** The job can delete the newer `A2/R2` if acting on a stale snapshot. Use transactions/versioning.

**Q9.** Does deleting a local authorized client revoke tokens at the AS?

**Answer:** Not automatically. Revocation is a separate operation.

**Q10.** Is Redis eviction the same as TTL expiration?

**Answer:** No. Eviction drops keys early due to memory policies before TTL expires.

**Q11.** Why inject `Clock`?

**Answer:** Deterministic expiry/grace testing without real wall-clock waits or sleeps.

**Q12.** Should you log raw access tokens to debug cleanup?

**Answer:** No. Log registration IDs, record references, and controlled error categories.

**Q13.** Does a 403 response from an API prove the token store TTL is wrong?

**Answer:** No. 403 typically indicates insufficient scopes, authorities, or business permissions.

**Q14.** Can a user log out while their authorized client remains in the service store?

**Answer:** Yes. Non-session stores may require separate cleanup.

## Takeaways

- **Serialization** determines how tokens, `Authentication`, and sessions are persisted and restored. Payloads can hold sensitive credentials and claims; enforce explicit schemas, security, versioning, and safe deserialization.
- **Access token expiry, refresh token expiry, session TTL, and data retention are distinct concepts.** Never collapse them into a single TTL clock.
- **Never delete an entire authorized client merely because the access token expired while a usable refresh token exists.** This is the golden rule of token cleanup.
- **Unknown refresh token expiry means neither expired nor immortal.** Retention policies must be defined deliberately.
- **Redis TTLs, JDBC cleanup, and `HttpSession`/`WebSession` lifecycles must match each storage type and use case**; never assume the framework cleans up every store automatically.
- **Refresh token rotation can race with cleanup**, requiring transactions, compare-and-swap, or conditional deletes to protect fresh tokens.
- **Logout/local deletion does not equal AS revocation.** Account for sessions, service stores, caches, and backups.
- **Never log raw tokens, serialized sessions, or credentials**, including in metrics, traces, or debug output.
- **Use `Clock` and integration tests** to validate expiry, serialization migrations, and concurrent cleanup/refresh before production rollout.
