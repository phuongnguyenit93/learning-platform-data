# Logging Login, Consent, Token Issuance, and Revocation Events

In an OAuth 2.0 / OpenID Connect Authorization Server, recording who logged in, which client requested access, which scopes the user approved, and which tokens were issued or revoked helps operations teams investigate incidents and demonstrate access history. This data also supports detecting anomalous behavior, such as a client suddenly requesting sensitive scopes or an account repeatedly failing to log in.

With Spring Security and Spring Authorization Server, events occur at multiple points in the authentication and authorization lifecycle. Spring Security provides a mechanism to publish authentication events; Spring Authorization Server stores consent and authorization state through dedicated services. Therefore, recording points must be placed at the right business boundaries, with the meaning of each event clearly defined.

## 1. Distinguishing Operational Logs from Audit Logs

Operational logs help answer how the system is performing: how long a request took, which endpoint returned an error, or whether the database is slow. Audit logs answer questions about security actions: who performed the action, what action occurred, with which client, at what time, and with what outcome.

Both types of data can be emitted as structured logs, but their retention and storage requirements differ:

| Criterion | Operational Log | Audit Log |
|---|---|---|
| Purpose | Diagnosing errors and monitoring performance | Investigating and proving security activities |
| Content | Endpoint, processing duration, error code, trace ID | Subject, client, action, outcome, scopes, reason code |
| Integrity | Can be rotated and sampled according to operational policy | Requires modification/deletion controls, access controls, and retention periods |
| Level of detail | Intended for engineering diagnostics | Sufficient to reconstruct the event without exposing secrets |

Do not log passwords, client secrets, authorization codes, access tokens, refresh tokens, ID Tokens, or PKCE verifiers in any type of log. Do not serialize entire **Authentication**, request, response, or **OAuth2Authorization** objects for logging: these objects may contain credentials or personal data.

## 2. Identifying Recording Points in the OAuth2/OIDC Lifecycle

An Authorization Server typically needs to track at least the following event groups:

| Event | Appropriate Recording Point | Key Business Data |
|---|---|---|
| Login success/failure | Spring Security authentication events | Subject, authentication method, outcome, reason code |
| OAuth2 client authentication | Client authentication point | Client ID, client authentication method, outcome |
| Consent granted/updated/removed | **OAuth2AuthorizationConsentService** | Principal, client ID, changed set of authorities/scopes |
| Token issued | State change saved via **OAuth2AuthorizationService** | Principal, client ID, grant type, token type, scopes |
| Token revoked | Token state transition to invalidated in authorization | Token type, token fingerprint, actor, and reason |
| Authorization removed | **OAuth2AuthorizationService.remove** | Internal authorization ID, client ID, removal reason |

Spring does not provide a single audit event covering all of the actions above. You need to combine Spring Security's authentication events with the two storage abstractions of Spring Authorization Server.

It is also necessary to separate user login from client authentication. When a client sends **client_secret_basic**, **private_key_jwt**, or another client authentication method, that is an OAuth2 client authentication, not a user login. Merging both into **LOGIN_SUCCEEDED** will make reports misleading. Classify them into separate event types.

## 3. Designing the Audit Event Structure

Events should be standardized into a common structure so they can be written to an audit table, a centralized logging system, or an event queue. A record can include the following fields:

| Field | Meaning |
|---|---|
| **event_id** | Unique identifier of the event |
| **event_type** | For example **LOGIN_FAILED**, **CONSENT_GRANTED**, **TOKEN_ISSUED**, **TOKEN_REVOKED** |
| **occurred_at** | UTC timestamp when the event occurred |
| **outcome** | **SUCCESS**, **FAILURE**, or **REJECTED** |
| **subject_ref** | Normalized or pseudonymized user identifier |
| **client_id** | Associated OAuth2 client |
| **grant_type** | Grant type, if the event relates to token issuance |
| **scopes** | List of granted or changed scopes, per data policy |
| **token_type** | **access_token**, **refresh_token**, or **id_token** |
| **token_fingerprint** | One-way fingerprint of the token, not the raw token value |
| **reason_code** | Standardized reason code, not an arbitrary exception message |
| **correlation_id** / **trace_id** | Links the event to the request and trace |
| **source_ip** / **user_agent** | Source information if collection is permitted by policy |

Example of an access token issuance event:

~~~json
{
  "event_id": "01JQ8X5K7M2P4R6T9V0W",
  "event_type": "TOKEN_ISSUED",
  "occurred_at": "2026-11-16T14:20:31Z",
  "outcome": "SUCCESS",
  "subject_ref": "user-7f31",
  "client_id": "web-portal",
  "grant_type": "authorization_code",
  "token_type": "access_token",
  "scopes": ["openid", "profile"],
  "token_fingerprint": "hmac-sha256:8a4f...",
  "correlation_id": "req-9c2d"
}
~~~

**token_fingerprint** can be generated using HMAC-SHA-256 with a secret key dedicated to auditing. This allows identifying whether two records relate to the same token without storing the raw token. Do not use fingerprints as metric labels because the number of distinct values can be very large.

Log only the necessary fields. **subject_ref** can be an internal ID or pseudonymized value instead of an email address and real name. If scopes need to be logged, only log normalized scope names permitted by policy. Do not log all claims of an ID Token or access token.

## 4. Recording Logins with Spring Security Events

Spring Security has **AuthenticationEventPublisher** to publish events such as **AuthenticationSuccessEvent** and subclasses of **AbstractAuthenticationFailureEvent**. You can listen to these events using **@EventListener**:

~~~java
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.UserDetails;

@Component
public class AuthenticationAuditListener {

    private final AuditRecorder auditRecorder;

    public AuthenticationAuditListener(AuditRecorder auditRecorder) {
        this.auditRecorder = auditRecorder;
    }

    @EventListener
    public void onSuccess(AuthenticationSuccessEvent event) {
        Authentication authentication = event.getAuthentication();

        // Only record user login events according to application rules.
        if (!isInteractiveUserLogin(authentication)) {
            return;
        }

        auditRecorder.loginSucceeded(safeSubject(authentication));
    }

    @EventListener
    public void onFailure(AbstractAuthenticationFailureEvent event) {
        Authentication authentication = event.getAuthentication();

        if (!isInteractiveUserLogin(authentication)) {
            return;
        }

        auditRecorder.loginFailed(
                safeSubject(authentication),
                safeReasonCode(event.getException())
        );
    }

    private boolean isInteractiveUserLogin(Authentication authentication) {
        // Adjust if the application uses a custom principal type.
        return authentication != null
                && authentication.getPrincipal() instanceof UserDetails;
    }

    private String safeSubject(Authentication authentication) {
        // subjectReference is an application function to pseudonymize/normalize the identifier.
        return subjectReference(authentication.getName());
    }

    private String safeReasonCode(Exception exception) {
        if (exception instanceof BadCredentialsException) {
            return "BAD_CREDENTIALS";
        }
        if (exception instanceof LockedException) {
            return "ACCOUNT_LOCKED";
        }
        return "AUTHENTICATION_PROVIDER_ERROR";
    }
}
~~~

The snippet above illustrates the integration point. **AuditRecorder** and **subjectReference** are application components that must be implemented according to the actual authentication mechanism. The example uses **UserDetails** to identify a user principal; if the application uses a custom principal type, replace this condition with the corresponding rule. An **AuthenticationSuccessEvent** can be emitted during client authentication or for another principal type; therefore, do not assume every event is a user login.

Ensure that **AuthenticationManager**/**ProviderManager** is using **AuthenticationEventPublisher**. Spring Boot auto-configuration usually provides this mechanism; if you create a **ProviderManager** manually, check and configure the corresponding publisher. For custom authentication mechanisms, verify that the component actually publishes events or add a recording point where authentication completes.

For failed logins, record only standardized reason codes such as **BAD_CREDENTIALS**, **ACCOUNT_LOCKED**, or **AUTHENTICATION_PROVIDER_ERROR**. Do not log the user's password, request credentials, or the full exception message, as the message may contain sensitive data.

## 5. Recording Consent via OAuth2AuthorizationConsentService

Spring Authorization Server uses **OAuth2AuthorizationConsentService** to read, save, and remove a principal's consent for a registered client. This is the appropriate boundary for auditing changes to approved permissions.

You can wrap the existing implementation with a decorator. Example handling when saving consent:

~~~java
public void save(OAuth2AuthorizationConsent consent) {
    OAuth2AuthorizationConsent previous = delegate.findById(
            consent.getRegisteredClientId(),
            consent.getPrincipalName()
    );

    delegate.save(consent);

    if (!sameAuthorities(previous, consent)) {
        if (previous == null) {
            auditRecorder.consentGranted(consent);
        } else {
            auditRecorder.consentUpdated(previous, consent);
        }
    }
}
~~~

When removing consent, record the event after the storage operation succeeds:

~~~java
public void remove(OAuth2AuthorizationConsent consent) {
    delegate.remove(consent);
    auditRecorder.consentRemoved(consent);
}
~~~

The complete decorator must implement and delegate all three methods of **OAuth2AuthorizationConsentService**: **findById**, **save**, and **remove**. **sameAuthorities** is an application function that compares the set of authorities before and after saving. Only record **CONSENT_UPDATED** when the permission set actually changes to avoid creating duplicate records when the same consent is re-saved.

When writing the audit record, extract **registeredClientId**, **principalName**, and the necessary authorities from the consent. You can normalize authorities into scope names according to your application's conventions. Do not log the consent screen content, the entire request, or unnecessary personal data.

**remove** indicates that the consent was removed from the store, but the method itself does not necessarily indicate who requested it or why. If you need to distinguish between user-initiated revocation, administrator revocation, or a system cleanup process, pass the actor context and reason code from the calling business service. Do not infer the actor solely from the fact that the **remove** method was called.

## 6. Recording Token Issuance and Revocation via OAuth2AuthorizationService

**OAuth2AuthorizationService** manages the state of granted authorizations. Key methods include **findById**, **findByToken**, **save**, and **remove**. A decorator around the service used by the Authorization Server can compare the state before and after saving to detect new tokens or tokens transitioning to an invalidated state.

Example decorator skeleton:

~~~java
public final class AuditingAuthorizationService
        implements OAuth2AuthorizationService {

    private final OAuth2AuthorizationService delegate;
    private final AuditRecorder auditRecorder;

    public AuditingAuthorizationService(
            OAuth2AuthorizationService delegate,
            AuditRecorder auditRecorder) {
        this.delegate = delegate;
        this.auditRecorder = auditRecorder;
    }

    @Override
    public OAuth2Authorization findById(String id) {
        return delegate.findById(id);
    }

    @Override
    public OAuth2Authorization findByToken(
            String token,
            OAuth2TokenType tokenType) {
        return delegate.findByToken(token, tokenType);
    }

    @Override
    public void save(OAuth2Authorization authorization) {
        OAuth2Authorization previous =
                delegate.findById(authorization.getId());

        delegate.save(authorization);

        // Compare tokens and metadata before/after saving.
        // Record TOKEN_ISSUED or TOKEN_REVOKED on appropriate state transitions.
        auditRecorder.recordAuthorizationTransitions(
                previous,
                authorization
        );
    }

    @Override
    public void remove(OAuth2Authorization authorization) {
        delegate.remove(authorization);
        auditRecorder.authorizationRemoved(authorization);
    }
}
~~~

**recordAuthorizationTransitions** is the application's audit logic. When implementing it, inspect the tokens in **OAuth2Authorization** including access token, refresh token, and ID Token; compare presence, fingerprints, and metadata before and after saving. Only record **TOKEN_ISSUED** when a new token is created or a new token replaces an old one according to defined rules. This also helps identify new access token issuances in the refresh token flow.

Do not record **TOKEN_ISSUED** solely because **OAuth2TokenGenerator** was called. The generator indicates that a token was created during processing, but saving the authorization may fail afterward. Recording after **OAuth2AuthorizationService.save** succeeds reflects that the token has been persisted in the server's authorization state. If you need to prove that the response was sent to the client, that is a separate event at the HTTP layer; do not interpret a successful save as proof that the client definitely received the response.

To detect revocation, check the metadata transition of a token to invalidated. Do not rely solely on the condition "token is no longer active" to conclude it was revoked: expired tokens are also inactive. Distinguish **isInvalidated()** from **isExpired()** or other states. When a token is marked invalidated, record **TOKEN_REVOKED** along with token type, client ID, subject, fingerprint, and reason code if known.

The **remove** method can be used to delete an entire authorization. Record **AUTHORIZATION_REMOVED** after the deletion succeeds and distinguish this event from revoking an individual access token or refresh token. If the deletion was triggered by a data cleanup job, record the system actor and the corresponding reason code.

The decorator must wrap the exact **OAuth2AuthorizationService** instance configured for Spring Authorization Server. If the application uses JDBC or a custom implementation, keep that implementation as the delegate so storage behavior does not change. Avoid creating two independent services where the processing flow writes to one place while the audit flow reads from another.

## 7. Ensuring Audit Semantics and Integrity

The timing and meaning of each event type must be standardized. For example:

- **LOGIN_SUCCEEDED**: Spring Security successfully authenticated a principal belonging to the user login group.
- **CONSENT_GRANTED**: a new consent was successfully saved.
- **CONSENT_UPDATED**: the set of permissions in the consent changed and was saved.
- **TOKEN_ISSUED**: a new token was persisted in the authorization.
- **TOKEN_REVOKED**: a token's metadata transitioned to the invalidated state.
- **AUTHORIZATION_REMOVED**: an authorization was removed from the store.

A token revocation request may not find the token, or the token may have already been revoked earlier. The protocol may return a success response according to the endpoint's rules, but the audit log should not record that the token state just changed if no actual state transition occurred. If you need to track revocation requests as well, record a separate event such as **TOKEN_REVOCATION_REQUESTED** and record the processing outcome independently.

If audit records are stored in a database, you can use an append-only table where the application only has insert privileges, or a transactional outbox to write audit events in the same transaction as authorization/consent changes. This reduces the risk of business data being committed while the audit event is lost. If audit events are sent to an external system, use an outbox or controlled retry mechanism; avoid calling a slow network service directly in the token issuance path.

Do not silently ignore audit write failures for mandatory events. The policy when the audit store fails must be clearly defined: reject the sensitive operation to preserve audit requirements, or persist to a durable queue for retry. Which option to choose depends on the system's availability and compliance requirements. Alerts should be configured when the audit queue backs up or writes fail.

Protect the audit store with read access controls, encryption in transit and at rest, clear retention periods, and monitoring of all access to audit data. For tamper-resistance requirements, you can use an append-only store, separation of duties between the application and administrators, or batch integrity verification mechanisms. Do not grant routine update/delete privileges on audit records to the Authorization Server's runtime account.

## 8. Combining Logs, Traces, and Metrics

Use structured JSON logs so centralized systems can filter by **event_type**, **client_id**, **subject_ref**, and **correlation_id**. Set timestamps in UTC and standardize the format across services. Attach a correlation ID or trace ID across login, authorization request, token request, and revocation operations to investigate a multi-step flow.

You can create metrics counting successful/failed logins, granted consents, and issued/revoked tokens. Metrics should only use labels with a bounded set of values, such as **event_type**, **outcome**, **grant_type**, or a normalized client group. Do not put usernames, IPs, token fingerprints, or correlation IDs into metric labels because that creates very high cardinality and increases storage costs.

When reading IP addresses from proxy headers, only trust headers written by trusted reverse proxies and configure the proxy list properly. Do not assume every **X-Forwarded-For** value from a client is accurate. For user agents and IP addresses, only collect them when there is a clear purpose, and restrict access permissions and retention periods according to data policy.

Configure sensitive data masking at the HTTP and logging layers. The query string of the authorization endpoint may contain an authorization code or state; the token endpoint and revocation endpoint may receive credentials in headers or bodies. Do not log the raw request URL, Authorization header, form body, or response body of these endpoints without a filter that strips sensitive data.

## 9. Notes on JWT Revocation and Resource Servers

With JWT access tokens, a resource server can verify the signature and token expiration locally without querying the Authorization Server on every request. When the Authorization Server marks a token as invalidated in the authorization store, a resource server that only checks the JWT signature locally may not be aware of the revocation yet.

If fast revocation enforcement is required, the architecture must include a mechanism for the resource server to check token status, such as using opaque tokens with introspection, a synchronized blocklist, or an equivalent revocation-check mechanism. Another option is to use short-lived access tokens to limit the window during which a token remains accepted. An audit log recording **TOKEN_REVOKED** helps with investigation and reconciliation, but the audit record itself does not cause resource servers to automatically reject already-issued JWTs.

## 10. Testing Audit Events

Tests should verify both that events are emitted and that sensitive content is not leaked:

1. Both successful and failed logins produce the correct event type; client authentication is not misclassified as a user login.
2. Initial consent produces **CONSENT_GRANTED**; scope changes produce **CONSENT_UPDATED**; consent removal produces **CONSENT_REMOVED**.
3. Exchanging an authorization code for an access token produces a token issuance event after the authorization is successfully saved.
4. The refresh token flow records the new access token and the rotated refresh token if rotation is configured.
5. Revoking an active token produces **TOKEN_REVOKED**; an expired token is not mistakenly recorded as newly revoked.
6. Removing an authorization produces **AUTHORIZATION_REMOVED**, distinct from revoking a single token.
7. Audit store failures or backed-up outbox records are handled according to defined policy and trigger alerts.
8. Logs do not contain raw passwords, client secrets, authorization codes, PKCE verifiers, access tokens, refresh tokens, or ID Tokens.

When events are placed at the right points in the authentication, consent, and authorization lifecycle, operations teams can trace Authorization Server activity while keeping tokens and credentials secret. A consistent audit structure also helps connect logs with traces, detect anomalies, and meet audit requirements during OAuth 2.0/OpenID Connect operations.
