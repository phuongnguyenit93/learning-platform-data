# Authorizing Retry and Resend Operations in Spring Framework Mail

In a production email-sending system built with Spring Framework Mail, delivery failures often lead to the request: "Let me click resend on this email." A seemingly simple **Retry** button can trigger sensitive side effects: duplicating invoices, resending expired verification codes, routing documents to unauthorized recipients, bypassing recipient consent, or exceeding SMTP provider limits.

**Authorizing retry and resend is not merely hiding or showing a button in the UI.** It is a policy at the server-side command boundary that determines **who may issue the request**, **which notification the action targets**, **whether state/failure class permits it**, **whether the recipient and content remain valid**, **when approval is required**, and **how outcomes must be audited, rate-limited, and recovered**.

This lesson introduces a production design pattern for Spring Framework Mail combining Spring Security, RBAC/ABAC, transactional outbox, idempotency, optimistic concurrency, cooldowns, dual-person approval, audit trails, and SMTP workers with dedicated service identities. The Java/SQL/HTTP examples are illustrative; domain classes and policies are application-implemented rather than built-in `JavaMailSender` APIs.

## 1. Why do these manual operations need protection?

An email may contain:

- Invoices and transaction details.
- OTPs, password-reset links, magic login links.
- Legal notices or personal data.
- PDFs, CSVs, or access-controlled documents.
- Marketing content governed by consent/frequency caps.
- Operational details intended only for an authorized staff group.

An improper resend/retry action can:

1. Leak tenant A data into tenant B's email.
2. Send duplicates making customers think they were double-charged.
3. Send expired tokens or security codes that are no longer valid.
4. Bypass suppression after a hard bounce or complaint.
5. Create spam when an operator clicks repeatedly.
6. Resend a notification already accepted by SMTP and awaiting delivery.
7. Corrupt operational history by losing who requested the resend.
8. Bypass SMTP quota/cooldown limits.
9. Let support accounts retrieve raw bodies or attachments unnecessarily.
10. Trigger a retry storm after an outage when multiple people act simultaneously.

Therefore, **the operational control plane** must stay separated from **the SMTP sending path**.

## 2. Automatic retry, manual retry, and resend are different

| Action | Initiator | Effect on notification | Purpose |
| --- | --- | --- | --- |
| Automatic retry | Worker/retry policy | Keeps `notificationId`, creates new `attemptId` | Recover from transient failure |
| Manual retry | Authorized operator | Keeps `notificationId`, schedules new attempt | Re-execute an incomplete intent |
| Resend | Authorized business role | **Creates a new notification**, links original | Intentionally send another copy |
| Replay/redrive | Event/queue operations tool | Depends on business handler | Re-run an event/workflow |

Do not call every action "retry." If the original is already `DELIVERED`, sending another copy is a **resend**, not retrying a failed send.

### Identity differences

```text
Manual retry:
  notificationId = N-1001
     attempt A1 -> transient error
     attempt A2 -> transient error
     attempt A3 -> manual retry -> SMTP accepted

Resend:
  original notificationId = N-1001
  new notificationId      = N-2002
  resendOf                = N-1001
  attempt B1              -> SMTP accepted
```

`notificationId` stays stable across retries; `attemptId` is new for every SMTP submission. Resending creates a new sending intent with an audit link back to the original.

## 3. Notification state determines what is permitted

An illustrative state machine:

```text
READY
  |
  v
PROCESSING
  |
  +--> SMTP accepted --------> SUBMITTED
  |                                 |
  |                                 +--> DELIVERED (provider event)
  |
  +--> Temporary failure ----> RETRY_WAIT
  |                                 |
  |                                 +--> PROCESSING
  |
  +--> Permanent failure ----> FAILED_PERMANENT
  |
  +--> Retry budget reached -> FAILED_EXHAUSTED
  |
  +--> Unknown outcome -----> AMBIGUOUS

Other states:
  CANCELLED / EXPIRED / SUPPRESSED / BOUNCED / COMPLAINED
```

This is an application model, not a default Spring Mail enum.

Distinguish clearly:

- **SUBMITTED**: SMTP transport/relay confirmed submission. Does not prove Inbox delivery.
- **DELIVERED**: a matching downstream event was reported by the provider.
- **BOUNCED**: email could not be delivered per provider report; may be hard or soft.
- **AMBIGUOUS**: uncertain whether the server accepted it, e.g., read timeout after SMTP `DATA`.
- **SUPPRESSED**: recipient is not permitted to receive under policy.
- **EXPIRED**: content or business action has passed its deadline.
- **FAILED_EXHAUSTED**: retry budget exhausted; only narrow policies allow intervention.

Never base the retry button solely on a `sent=false` column.

## 4. Three control layers for granting permission

A command must pass at least three layers:

1. **Authentication**: who is the actor, and how were they authenticated?
2. **Authorization**: does the actor have permission on this **action and resource**?
3. **Business policy**: do the notification, recipient, state, content, consent, expiry, and quota permit the action right now?

```text
Authenticated actor
      |
      v
RBAC authority + tenant/resource scope
      |
      v
State/failure class + consent/expiry
      |
      v
Cooldown/rate budget + approval
      |
      v
Atomic command + durable audit
      |
      v
Worker service account + SMTP
```

Holding a `MAIL_OPERATOR` role does not automatically grant permission to send every email in the system.

## 5. Designing action-based permissions

Authorities can be defined as:

| Permission | Meaning |
| --- | --- |
| `mail:read_metadata` | View filtered metadata |
| `mail:read_content` | View body/attachments under special scope |
| `mail:retry_request` | Request manual retry |
| `mail:resend_request` | Request resend |
| `mail:resend_approve` | Approve sensitive resends |
| `mail:retry_override` | Request narrow retry-budget override |
| `mail:cancel` | Cancel unsent jobs |
| `mail:audit_read` | Read audit history |
| `mail:policy_manage` | Modify policy configuration |
| `mail:worker_dispatch` | Internal privilege of sender workers |

These are application-chosen names, not authorities generated automatically by Spring Security.

Separate permissions for **reading content** and **re-sending**. An operator may need to retry by notification ID without reading OTPs, invoice PDFs, or private content.

## 6. Suggested role matrix

| Role | Metadata | Manual retry | Resend | Approve | Policy |
| --- | --- | --- | --- | --- | --- |
| Support viewer | In scope | No | No | No | No |
| Support agent | Assigned ticket | Per narrow policy | Permitted transactional only | No | No |
| Mail operator | Assigned tenant | Yes for eligible failures | Conditional | Cannot self-approve | No |
| Mail supervisor | Assigned tenant | Yes | Yes | Can approve others | Restricted |
| Platform admin | Per delegated scope | Conditional | Conditional | Per workflow | Limited |
| Retry worker | Leased jobs | Automatic only | Cannot initiate resends | No | No |

This illustrates **least privilege**. Never use a `ROLE_ADMIN` role as a master key bypassing consent, expiry, tenant isolation, or ownership checks.

## 7. ABAC: authorization depends on the specific notification

An operator holds `mail:resend_request`, while the target carries:

```text
tenantId              tenant-42
category              ORDER_CONFIRMATION
status                DELIVERED
containsSensitiveDoc  true
recipientSuppressed   false
expiresAt             none
customerTicketId      TICKET-8123
```

The decision should further check:

- Does the actor belong to tenant 42 or hold delegated access?
- Is the ticket assigned to this actor?
- Does the content include sensitive documents requiring approval?
- Does the recipient have an opt-out, bounce, complaint, or suppression?
- Does the email still match the latest business state?
- How many resends occurred within the cooldown window?
- Is the SMTP provider currently in a circuit breaker/cooldown?

With ABAC, **permission on an action** does not mean **every resource is valid**.

## 8. Multi-tenancy and preventing BOLA/IDOR

An endpoint like:

```text
POST /api/v1/mail-notifications/{id}/retry
```

must look up the resource within the authenticated tenant scope:

```sql
SELECT id, tenant_id, status, version, category
FROM mail_notification
WHERE id = :notification_id
  AND tenant_id = :authorized_tenant_id;
```

Never trust `tenantId` from a JSON request body as authorization proof. The tenant must come from the authenticated principal, verified membership/delegated scope, or trusted server-side context.

Hard-to-guess UUIDs **are not an authorization boundary**. When a target belongs to another tenant, the API may return 404 if policy requires concealing resource existence rather than letting callers probe IDs.

If an operator manages multiple tenants, scope lists must be checked on every command.

## 9. Manual retry only for eligible failure classes

| Failure class | Examples | Handling |
| --- | --- | --- |
| `TRANSIENT_NETWORK` | Connect timeout/network glitch pre-submit | Retry after inspection |
| `SMTP_TEMPORARY` | 421, 451, provider throttling | Retry with backoff/cooldown |
| `CONFIGURATION` | Wrong credentials or TLS config | Retry only after fixing root cause |
| `PERMANENT_RECIPIENT` | Invalid address | Do not retry same email |
| `CONTENT_POLICY` | MIME too large, disallowed attachment | Fix content/workflow first |
| `EXPIRED` | OTP/token/deadline expired | Do not retry old payload |
| `SUPPRESSED` | Unsubscribe or complaint | Do not bypass |
| `AMBIGUOUS` | Timeout after SMTP DATA | Reconcile; avoid duplicates |
| `SUBMITTED/DELIVERED` | SMTP accepted or provider delivered | Do not retry; consider separate resend |
| `UNKNOWN` | Insufficient evidence | Investigate |

A **Retry All Failed** button ignoring failure classes causes futile re-submissions or spam.

## 10. Manual retry on the same notification

Workflow:

1. Authenticate the operator.
2. Check authority and tenant/resource scope.
3. Inspect status, last failure class, and retry policy.
4. Check expiry, suppression, consent, and cooldown.
5. Check attempt count and required approval.
6. Persist command/audit durably.
7. Use an atomic state transition to schedule the next attempt.
8. Return `ACCEPTED`; **never call SMTP inside the HTTP request**.
9. Worker executes under lease and provider quota.
10. Audit attempt outcome.

If the notification is in `RETRY_WAIT` with an automatic retry imminent, a manual retry may merely adjust `nextAttemptAt` per policy; never create two concurrent attempts for the same logical job.

## 11. Resend creates a new notification

Resend is a decision to send an additional copy:

```text
Original:
  notificationId = N-1001
  status = DELIVERED

Authorized resend:
  operationId = OP-9001
  reason = CUSTOMER_REQUEST
  requestedBy = operator-17

New:
  notificationId = N-2002
  resendOf = N-1001
  status = READY
```

Never mutate the original from `DELIVERED` back to `READY`; doing so corrupts submission history and reporting. The new resend carries its own status, attempts, and provider event IDs.

Store `resendOfNotificationId`, `reasonCode`, `ticketId`, `requestedBy`, `approvalId`, and content/version policy.

### Which content does a resend use?

- **Documents/invoices**: usually requires the validly issued immutable snapshot.
- **Order confirmation**: choose original snapshot or current template per policy.
- **OTP/password reset**: never copy old tokens; trigger a new token/workflow.
- **Marketing**: check consent/suppression **at resend time**.
- **Status notices**: verify old content still accurately reflects current state.

"Resend raw MIME" is not a universal solution.

## 12. SUBMITTED differs from DELIVERED, and both differ from retryable

If `JavaMailSender.send(...)` finishes normally, the current SMTP hop accepted the submission. The recipient might still not see it due to downstream deferral, filtering, quarantine, or bouncing.

When a user reports not receiving an email:

1. Look up the provider message ID/SMTP queue ID if available.
2. Inspect delivery/deferred/bounced events.
3. Check whether the message was suppressed.
4. Inspect provider logs/delays.
5. Consider resending only under authorized policy and cooldown.

Never create a duplicate simply because a submitted email is waiting on provider delivery events.

## 13. AMBIGUOUS SMTP outcomes require special guards

A scenario:

```text
Application                      SMTP relay
    |                                  |
    |---- MIME + DATA terminator ----->|
    |                                  | Queued already?
    |<---- final reply lost -----------X
    |
    +--> read timeout
         Outcome unknown
```

A client timeout does not prove the server failed to receive the message. Retrying could send a second email.

Policies may specify:

- `AMBIGUOUS` is blocked from routine manual retry permissions.
- Operators must inspect provider logs/queue IDs if available.
- Require a reconciliation window or approval.
- If business demands a retry, explicitly record duplicate risk and rationale.
- Never turn `AMBIGUOUS` into `NOT_SENT` just to light up a Retry button.

The SMTP MIME `Message-ID` does not guarantee automatic server-side deduplication.

## 14. Consent and suppression are guards that cannot be bypassed arbitrarily

An operator authorized to resend **must not** implicitly be able to:

- Send marketing after unsubscribe.
- Continue sending after hard bounces/complaints.
- Send expired OTPs/tokens.
- Send notifications contradicting current business state.
- Bypass active quiet hours/frequency caps.
- Send documents whose sharing access was revoked.
- Use an old address after the customer verified a new one.

If an organization has a dedicated workflow to resolve suppressions, assign a specialized permission; never turn `mail:resend_request` into suppression removal rights.

## 15. Separating human operators from service identities

**Human operator**:

- Authenticated (MFA for sensitive actions).
- Holds authority scoped by role/tenant/ticket.
- Submits durable commands and supplies reasons.
- Audited for actor/session/approval.
- Needs no SMTP credentials.

**Mail worker**:

- Runs under a dedicated service principal.
- Claims jobs from durable storage via leases.
- Reads only necessary artifacts.
- Calls `JavaMailSender` using SMTP credentials from a secret manager.
- Never fabricates resend commands on its own.
- Records attempt outcomes under ownership/version checks.
- Rechecks mutable eligibility conditions.

Never forward the HTTP `SecurityContext`/JWT wholesale into `@Async` workers or the outbox to "preserve operator privileges."

## 16. Spring Security method authorization

Modern Spring Security example:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

Service boundary:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class MailOperationsService {

    private final MailCommandHandler handler;

    public MailOperationsService(
            MailCommandHandler handler) {
        this.handler = handler;
    }

    @PreAuthorize("hasAuthority('mail:retry_request')")
    public MailOperationReceipt requestRetry(
            UUID notificationId,
            String reason,
            String idempotencyKey) {

        return handler.requestRetry(
            notificationId, reason, idempotencyKey
        );
    }

    @PreAuthorize("hasAuthority('mail:resend_request')")
    public MailOperationReceipt requestResend(
            UUID notificationId,
            String reason,
            String idempotencyKey) {

        return handler.requestResend(
            notificationId, reason, idempotencyKey
        );
    }
}
```

`MailCommandHandler` and `MailOperationReceipt` are application abstractions.

Here `@PreAuthorize` enforces **coarse-grained permissions**. The command handler still must check tenant scope, resource state, consent, content category, cooldown, approval, and idempotency. A single authority check is insufficient.

## 17. Actor identity must be verified on the server

A domain actor:

```java
public record MailActor(
    String subjectId,
    UUID tenantId,
    Set<String> authorities,
    boolean mfaSatisfied
) {}
```

A provider:

```java
public interface MailActorProvider {
    MailActor currentActor();
}
```

An implementation extracts from Spring Security's verified `Authentication`, mapping custom principals/JWT claims to `MailActor`.

Never read `actorId`, `tenantId`, `roles`, or `mfaSatisfied` from a request body and treat them as authenticated truth. With token-based authentication, verify issuer/audience, tenant scope, and grant semantics per your actual security configuration.

## 18. Authorization policy at the application layer

```java
public interface MailOperationPolicy {

    void requireRetryAllowed(
        MailActor actor,
        MailNotification notification,
        RetryRequest request
    );

    void requireResendAllowed(
        MailActor actor,
        MailNotification original,
        ResendRequest request
    );
}
```

A policy concept:

```java
public void requireRetryAllowed(
        MailActor actor,
        MailNotification target,
        RetryRequest request) {

    requireAuthority(actor, "mail:retry_request");
    requireTenantMembership(actor, target.tenantId());
    requireAllowedCategory(actor, target.category());
    requireRetryableStatus(target.status());
    requireRetryableFailureClass(target.lastFailureClass());
    requireNotExpired(target.expiresAt());
    requireNoSuppression(target);
    requireAttemptBudget(target);
    requireCooldownElapsed(target.lastManualActionAt());
    requireValidReason(request.reasonCode());
}
```

The `require...` helpers illustrate business enforcement. If any rule fails, create no attempt, update no outbox row, and do not invoke SMTP.

This logic must execute server-side and pair with transactional/conditional updates to prevent races.

## 19. Preventing TOCTOU when state changes between check and update

Risk:

```text
Operator sees FAILED_TRANSIENT
         |
         v
Authorization check passes
         |
         +--> another worker submits message
         |    status becomes SUBMITTED
         |
         v
Manual retry updates status to READY
         |
         v
Duplicate submit
```

This is *time-of-check to time-of-use*.

Mitigation:

- Validate inside a short transaction.
- Query the resource scoped by authorized tenant.
- Use optimistic `version` or conditional SQL.
- Block `PROCESSING`/`SUBMITTED` states.
- Enforce unique idempotency keys per command.
- Re-evaluate mutable eligibility prior to SMTP submission.
- Verify worker ownership/attempt tokens when recording outcomes.

Never rely on data loaded in the UI minutes earlier.

## 20. Conditional SQL for manual retry

PostgreSQL example:

```sql
UPDATE mail_notification
SET status = 'RETRY_WAIT',
    next_attempt_at = NOW(),
    version = version + 1,
    last_manual_requested_by = :actor_id,
    updated_at = NOW()
WHERE id = :notification_id
  AND tenant_id = :authorized_tenant_id
  AND version = :expected_version
  AND status IN (
      'FAILED_TRANSIENT',
      'FAILED_EXHAUSTED',
      'RETRY_WAIT'
  )
  AND attempt_count < :authorized_attempt_limit
  AND (
      last_manual_action_at IS NULL
      OR last_manual_action_at <= :cooldown_cutoff
  )
RETURNING id, version;
```

`FAILED_EXHAUSTED` should only be eligible if policy granted a special retry budget; `authorized_attempt_limit` must be calculated server-side, **never** accepted blindly from an HTTP request.

This query handles only the atomic state guard. The service must still validate failure class, consent, category, approval, and idempotency before mutating. If the update returns 0 rows, return a conflict/re-evaluate rather than falling back to an unconditional update.

## 21. Resend by inserting a new record, never resetting the original

Illustrative schema:

```sql
CREATE TABLE mail_notification (
    id                      UUID PRIMARY KEY,
    tenant_id               UUID NOT NULL,
    category                VARCHAR(50) NOT NULL,
    status                  VARCHAR(40) NOT NULL,
    recipient_ref           VARCHAR(200) NOT NULL,
    content_version         VARCHAR(80),
    resend_of_notification  UUID,
    requested_by            VARCHAR(200),
    version                 BIGINT NOT NULL DEFAULT 0,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

When resending:

```text
Original N-1001:
  status = DELIVERED
  resend_of_notification = null

New N-2002:
  status = READY
  resend_of_notification = N-1001
  requested_by = operator-17
  content_version = approved snapshot
```

Create the notification/outbox intent and audit operation inside one transaction. Never overwrite the original's accepted/delivered history.

Production schemas also require durable recipient/content references, policy versions, idempotency keys, approvals, business events, and retention metadata.

## 22. Manual commands require idempotency keys

If an operator double-clicks, an HTTP gateway retries, or a response times out, the backend must not create two resends.

Example request:

```http
POST /api/v1/mail-notifications/3f4.../resend
Idempotency-Key: 9fb541b4-0f92-4dd6-a67d-7b5a8fb6cf1b
Content-Type: application/json

{
  "reasonCode": "CUSTOMER_REQUEST",
  "ticketId": "T-8123"
}
```

The truncated path ID is illustrative only.

A deduplication scope:

```text
tenantId
+ authenticated actorId or service principal
+ actionType
+ originalNotificationId
+ idempotencyKey
```

If the key matches with the exact same semantic payload, return the previously created operation receipt. If the key matches with a different payload, return conflict.

Idempotency must be durable across restarts and multiple instances (unique constraints/transactions), not just an in-memory `Map`.

## 23. Resends with fresh keys still need cooldowns

An idempotency key prevents duplicates for **the same intent**, not an operator deliberately issuing 20 requests with 20 new keys.

You therefore need:

- Per-notification resend cooldowns.
- Per-recipient frequency caps.
- Per-actor action budgets.
- Per-tenant quotas.
- Provider rate budgets.
- Approval thresholds.
- Time-window deduplication if business policy requires it.

Do not use `originalNotificationId` as an absolute unique key forbidding all future resends forever: two customer requests on different days may be legitimate intents. Define clear policies on windows and reasons.

## 24. API commands should not invoke SMTP directly

Endpoint:

```http
POST /api/v1/mail-notifications/{id}/retry
Idempotency-Key: ...

{
  "reasonCode": "INCIDENT_RESOLVED",
  "ticketId": "INC-42"
}
```

Or:

```http
POST /api/v1/mail-notifications/{id}/resend
Idempotency-Key: ...

{
  "reasonCode": "CUSTOMER_REQUEST",
  "ticketId": "T-8123"
}
```

Once the command is durably persisted:

```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "operationId": "OP-9001",
  "status": "ACCEPTED",
  "notificationId": "N-2002",
  "requestedAction": "RESEND"
}
```

`202 Accepted` confirms the command was accepted for processing—it **does not** prove SMTP accepted, delivered, or opened the email. An operation/notification status endpoint exposes the eventual outcome.

If approval is required, the command may stay in `PENDING_APPROVAL` with no `READY` send job created yet.

## 25. HTTP status codes and policy responses

| Scenario | Typical code | Explanation |
| --- | --- | --- |
| Unauthenticated | 401 | Authentication required |
| Missing action/scope | 403 | Forbidden |
| Resource existence must not be disclosed | 404 | Prevents cross-tenant probing |
| State/version changed | 409 | Conflict |
| Invalid input/reason | 400/422 | Validation failure |
| Rate limit/cooldown | 429 | May include `Retry-After` |
| Approval required | 202 with `PENDING_APPROVAL` | Not sent yet |
| Durable command accepted | 202 | Command queued |
| Same key, identical payload | Return original receipt | No extra operation created |
| Same key, different payload | 409 | Idempotency conflict |

APIs should return consistent error codes without leaking SMTP secrets, raw MIME, or other tenants' email addresses in error messages.

## 26. Thin controllers in Spring Boot

```java
@RestController
@RequestMapping("/api/v1/mail-notifications")
public class MailOperationsController {

    private final MailOperationsService operations;

    public MailOperationsController(
            MailOperationsService operations) {
        this.operations = operations;
    }

    @PostMapping("/{id}/retry")
    public ResponseEntity<MailOperationReceipt> retry(
            @PathVariable UUID id,
            @RequestHeader("Idempotency-Key") String key,
            @RequestBody RetryRequest request) {

        MailOperationReceipt result =
            operations.requestRetry(
                id, request.reasonCode(), key
            );

        return ResponseEntity.accepted().body(result);
    }

    @PostMapping("/{id}/resend")
    public ResponseEntity<MailOperationReceipt> resend(
            @PathVariable UUID id,
            @RequestHeader("Idempotency-Key") String key,
            @RequestBody ResendRequest request) {

        MailOperationReceipt result =
            operations.requestResend(
                id, request.reasonCode(), key
            );

        return ResponseEntity.accepted().body(result);
    }
}
```

DTOs:

```java
public record RetryRequest(String reasonCode) {}
public record ResendRequest(String reasonCode) {}

public record MailOperationReceipt(
    UUID operationId,
    UUID notificationId,
    String status
) {}
```

This is an illustrative skeleton omitting validation annotations, ticket/approval fields, error handling, tenant scope, and transaction boundaries.

**Authorization decisions must live in the service/policy layer**, not only in controllers, because the same command may be called from internal endpoints or other workflows.

## 27. Watch out for proxies and self-invocation with @PreAuthorize

Spring method security usually executes via AOP proxies. If a bean calls its own annotated method via `this.requestRetry(...)`, the interceptor can be bypassed under standard proxy configuration.

Anti-pattern:

```java
@Service
public class MailOperationService {

    public void internalOperation(UUID id) {
        this.requestRetry(id); // May bypass proxy.
    }

    @PreAuthorize("hasAuthority('mail:retry_request')")
    public void requestRetry(UUID id) {
        // Mutation.
    }
}
```

Design guidance:

- Place the authorized boundary on a bean invoked through the Spring proxy.
- Never expose unaudited mutation paths.
- Guard domain commands with a deeper policy service.
- Enforce transactional/conditional state checks inside handlers.
- Test both external API calls and internal call paths.

Even if an annotation were bypassed due to a technical flaw, **business policy checks** must still protect critical state.

## 28. Never carry HTTP Authentication into workers

Workers may execute minutes later or on a different JVM. Never serialize full `Authentication` objects, session cookies, or JWTs into the outbox.

```text
HTTP authenticated actor
          |
          v
Authorize + create durable operation
          |
          +--> actorId / tenantId
          +--> action / reason / ticket
          +--> approvalId
          |
          v
DB COMMIT
          |
          v
Mail worker with service identity
          |
          +--> Claim job
          +--> Recheck eligibility/lease
          +--> Send by JavaMailSender
          +--> Persist outcome
```

The worker does not need to impersonate the HTTP user. It holds infrastructure permissions to process **validly accepted jobs**. `TaskDecorator` assists trace/MDC propagation, not durable authorization.

## 29. Approval / maker-checker for sensitive actions

Some actions should require two people:

- Resending documents containing sensitive personal data.
- Re-sending a large batch/campaign.
- Overriding cooldowns/retry budgets during an incident.
- Retrying notifications with an `AMBIGUOUS` outcome.
- Changing recipients when documents belong to someone else.
- Actions in high-sensitivity tenant/regulatory scopes.

Flow:

```text
Requester
   |
   v
Create operation
   |
   v
PENDING_APPROVAL
   |
   +--> REJECTED / EXPIRED -> no send
   |
   +--> Approved by another authorized actor
                           |
                           v
                  Revalidate current policy
                           |
                           v
                  Create durable send intent
                           |
                           v
                      SMTP worker
```

**Requesters must never approve their own requests** when maker-checker requires separation of duties.

Approvals carry expiration timestamps and bind tightly to tenant, notification, action, reason, recipient, and content fingerprint—never acting as a blanket permission to send arbitrarily later.

## 30. Revalidate at approval time and execution time

While awaiting approval:

- The recipient may unsubscribe.
- The original notification may report `DELIVERED`.
- The requester/approver may lose permissions.
- The ticket may close.
- Document access permissions may be revoked.
- OTPs or business deadlines may expire.

Policies must therefore re-evaluate at approval decision time and prior to creating the send intent. When the worker actually submits, it must also recheck mutable conditions such as suppression, expiry, and recipient eligibility.

Approval records can store:

```text
approvalId
operationId
requestedBy
approvedBy
approvedAt
expiresAt
tenantId
targetNotificationId
action
payloadFingerprint
reason/ticket
policyVersion
```

Never let the requester alter the recipient/content post-approval while reusing the existing approval.

## 31. Rate limits, cooldowns, and budgets

| Guard | Function |
| --- | --- |
| Per-actor command limit | Stops one person from flooding requests |
| Per-notification cooldown | Prevents back-to-back resends |
| Per-recipient frequency cap | Protects recipients |
| Per-tenant quota | Enforces tenant isolation |
| SMTP provider rate limit | Honors account/domain quotas |
| Manual resend daily cap | Limits manual blast radius |
| Max attempts | Prevents infinite retries |
| Backoff + jitter | Dampens retry storms |
| Business expiry | Prevents sending stale content |

Manual retries must never bypass provider quotas silently. If `mail:retry_override` exists, it should override only **specific named guards** with strict scope/time bounds—never bypassing consent or tenant isolation.

Never stall workers with `Thread.sleep` for cooldowns. Persist `nextAttemptAt` and let schedulers pick jobs up when due.

## 32. Control plane and data plane

Architecture:

```text
Admin UI / API
      |
      v
Spring Security
      |
      v
MailOperationsService
  - RBAC + ABAC
  - Tenant/resource scope
  - State/failure policy
  - Idempotency/cooldown
  - Approval/audit
      |
      v
Durable command/outbox transaction
      |
      v
Sender worker with service identity
  - Claim/lease
  - Eligibility recheck
  - Rate limit
  - Build MimeMessage
  - JavaMailSender.send(...)
  - Persist status
```

Benefits:

- HTTP requests never hang on SMTP timeouts.
- SMTP credentials never reach the admin UI.
- Operation states are durable.
- Crashed workers recover via leases.
- Commands are audited before side effects occur.
- UI privileges never turn an operator directly into an SMTP relay.

## 33. Auditing must record both allowed and denied actions

Suggested event names:

```text
mail.retry.requested
mail.retry.denied
mail.resend.requested
mail.resend.pending_approval
mail.resend.approved
mail.resend.rejected
mail.operation.accepted
mail.operation.executed
mail.smtp.attempted
mail.smtp.submitted
mail.smtp.failed
mail.smtp.ambiguous
```

Example audit record:

```json
{
  "eventType": "mail.resend.requested",
  "operationId": "OP-9001",
  "actorId": "operator-17",
  "tenantId": "tenant-42",
  "action": "RESEND",
  "targetNotificationId": "N-1001",
  "reasonCode": "CUSTOMER_REQUEST",
  "ticketId": "T-8123",
  "decision": "PENDING_APPROVAL",
  "policyVersion": "v5",
  "timestamp": "2026-11-12T11:00:00Z"
}
```

Never write raw OTPs, bodies, attachments, SMTP passwords, or access tokens into audits. Use recipient references/masked addresses per access policy.

**Audit durability:** if the DB command commits while the log collector is down, you still need to trace the actor and decision. Store audit events in the DB in the same transaction or via a transactional outbox for later delivery to the audit system.

## 34. Operation records and unique keys

Illustrative schema:

```sql
CREATE TABLE mail_operation (
    id                      UUID PRIMARY KEY,
    tenant_id               UUID NOT NULL,
    action_type             VARCHAR(30) NOT NULL,
    target_notification_id  UUID NOT NULL,
    new_notification_id     UUID,
    actor_id                VARCHAR(200) NOT NULL,
    reason_code             VARCHAR(100) NOT NULL,
    ticket_id               VARCHAR(200),
    idempotency_key         VARCHAR(200) NOT NULL,
    payload_fingerprint     VARCHAR(100) NOT NULL,
    status                  VARCHAR(40) NOT NULL,
    approval_id             UUID,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (
        tenant_id,
        actor_id,
        action_type,
        target_notification_id,
        idempotency_key
    )
);
```

This is not a prebuilt Spring Mail schema. Enforce length limits on idempotency keys, service-principal scoping, retention policies, audit event history, and operation-receipt replay semantics.

Create the operation, resend intent, and audit inside an appropriate transaction, and never emit a send job while approval remains incomplete.

## 35. Recipient, From, and Bcc require strict policies

A resend API must never accept and trust arbitrary values:

```json
{
  "to": "attacker@example.net",
  "bcc": ["hidden@example.net"],
  "from": "ceo@example.com"
}
```

These sensitive fields must remain application-controlled:

- `To` derived from verified recipients on the business resource.
- `Cc`/`Bcc` determined strictly by approved policies.
- `From` selected from provider accounts/verified sender aliases.
- Attachment references checked for tenant and read authorization.
- `Reply-To` governed by its own routing policy.
- Any recipient change must pass through a new verification workflow.

**Resend permission does not grant permission to change the recipient.** Routing an invoice to a new address may require account/email-ownership verification and approval.

## 36. Security email resends must not copy old tokens

For OTP/password reset/email verification:

- Tokens carry TTLs.
- Tokens may be single-use or already revoked.
- Old emails may carry dead URLs.
- Replaying raw MIME yields useless messages or security risks.
- Users may currently be under request-flooding attacks.

Proper workflow:

```text
Authorized user/security recovery request
         |
         v
Identity service validates state, rate, risk
         |
         v
Issue/rotate token according to policy
         |
         v
Create NEW notification intent
         |
         v
Mail worker sends through normal quota
```

A support operator should not gain read access to raw OTPs/tokens merely to handle "resends." Issuing new security tokens belongs to authentication/identity flows, not general mail-operator permissions.

## 37. Changing recipients should be a separate workflow

When a customer asks "Send the invoice to a new address":

1. Verify the request comes from the legitimate account/authorized person.
2. Verify ownership of the email address or valid business grounds.
3. Check consent/suppression.
4. Ensure the document matches the right person and version.
5. Apply approval if policy requires.
6. Create a new notification targeting the verified recipient.
7. Audit the recipient change and reason.

Never simply let operators pass an arbitrary `toOverride` through a resend API.

## 38. UI capabilities are for presentation only

The UI may receive:

```json
{
  "canRequestRetry": true,
  "canRequestResend": false,
  "retryRequiresReason": true,
  "resendRequiresApproval": true,
  "explanations": ["RESEND_NOT_ALLOWED_FOR_FAILED_ORIGINAL"]
}
```

The interface can display:

```text
Notification N-1001
Status: FAILED_TRANSIENT
Failure: SMTP_TEMPORARY
Manual retry: Allowed
Resend: Not allowed
Next automatic retry: 10:45 UTC
Cooldown until: 10:43 UTC
```

Capability flags evaluated at view time are not permanent permits. The backend must **re-evaluate on click** because notification status, roles, and consent can change.

Hiding buttons does not protect APIs when clients call endpoints directly.

## 39. UI confirmations prevent mistaken actions

When resending `SUBMITTED` or `DELIVERED` emails, the UI should clarify:

- **Retry failed send:** finishes the same unsuccessful notification.
- **Send another copy:** creates a new notification; the recipient may see two emails.
- **Reissue secure link:** triggers a new security workflow/token.

Example:

```text
Action: Send another copy
Original status: DELIVERED
Recipient: masked
Category: ORDER_CONFIRMATION
Reason: CUSTOMER_REQUEST
Effect: A new notification will be created
Warning: Recipient may receive a duplicate
```

Confirmation dialogs reduce operator errors but never replace server-side authorization, cooldowns, and idempotency.

## 40. Category-specific policies

| Category | Retry | Resend |
| --- | --- | --- |
| TRANSACTIONAL | On transient failures | On authorized customer request |
| SECURITY | Via recovery policy | Never copy old tokens; reissue |
| MARKETING | Subject to consent/suppression | Heavily restricted, enforce frequency caps |
| OPERATIONAL | Per incident policy | Per incident runbook |
| LEGAL/COMPLIANCE | Dedicated workflow | May require approval |

Policies also depend on tenant, jurisdiction, document class, and business context. Never allow high-level roles to bypass mandatory rules automatically.

## 41. Break-glass overrides must be narrow, time-bound, and audited

During major incidents, operators occasionally need to override limits such as retry budgets after fixing SMTP credentials.

A break-glass policy should enforce:

- Mandatory ticket/justification.
- MFA or strong authentication.
- Explicit scope: tenant/category/notification/provider.
- Named guard being overridden.
- Automatic expiration.
- Approval/post-incident review.
- Alerts to security/operations.
- Immutable audit records.
- No expansion of access to unrelated message contents.

Never maintain a permanent "super-admin bypass all" flag. Never bypass tenant isolation, consent, or token-verification workflows.

## 42. Monitoring manual operations

Suggested metrics:

| Metric | Meaning |
| --- | --- |
| `mail_manual_retry_requests_total` | Manual retry commands |
| `mail_resend_requests_total` | Resend commands |
| `mail_operation_denied_total` | Denied commands by reason |
| `mail_operations_pending_approval` | Approval backlog |
| `mail_resend_approved_total` | Approved resends |
| `mail_retry_attempts_total` | Actual execution attempts |
| `mail_resend_submitted_total` | SMTP-accepted resends |
| `mail_ambiguous_operations_total` | Outcomes needing investigation |
| `mail_idempotent_replay_total` | Deduplicated requests |
| `mail_policy_override_total` | Override actions |

Metric names are custom application examples, not Spring Mail defaults.

Use only low-cardinality tags such as action, category, and outcome. Never use recipient email, notification ID, or ticket ID as metric labels.

Alerts should watch spikes in manual resends, high denied-operation counts, unusual approval backlogs, and SMTP error rates following manual retry waves.

## 43. Testing authorization at the service and API layers

A suite of unit/integration tests:

1. Viewers lack retry/resend permissions.
2. Support agents act only on assigned tickets.
3. Same role in a different tenant is denied.
4. `SUBMITTED` notifications cannot be retried.
5. `FAILED_TRANSIENT` can be retried when eligible.
6. `FAILED_PERMANENT`/`SUPPRESSED`/`EXPIRED` are blocked.
7. `AMBIGUOUS` requires approval or dedicated policy.
8. Expired-token resends never copy raw tokens.
9. Unsubscribing after the original blocks resends.
10. Missing reason/ticket records no durable command.
11. Requesters cannot self-approve.
12. Expired/revoked approvals cannot execute.
13. Idempotent replays create no extra jobs.
14. Same idempotency key + differing payload returns conflict.
15. Actors with mail action rights lacking content-read rights cannot view raw bodies.
16. Service actors cannot arbitrarily trigger resends via internal APIs.

Spring Security tests can use `@WithMockUser` for simple authorities or mocked JWTs/custom principals when tenant claims are required. Tests must exercise actual paths traversing method-security proxies.

## 44. Testing race conditions and DB atomicity

Scenarios:

- Two operators concurrently retry the same notification.
- Manual retry races with automatic retry.
- Double-clicking resend creates only one new notification for the same idempotency key.
- Two approvers click approve simultaneously; only one executes.
- Notification transitions to `SUBMITTED` before the retry command commits.
- Recipient unsubscribes while approval is pending.
- Actor permissions are revoked before execution.
- Worker crashes after SMTP acceptance before DB update.
- Stale worker with expired lease attempts to overwrite status.
- Audit operation and outbox mutation remain consistent within the transaction.

These tests require a database with real concurrency semantics; mocking every repository call to return success cannot verify duplicates or races.

## 45. SMTP integration tests should use a test server

An end-to-end test:

```text
Authorized API command
      |
      v
Durable operation/outbox
      |
      v
Worker claim
      |
      v
JavaMailSender
      |
      v
GreenMail SMTP capture server
      |
      v
Captured MimeMessage
```

Key assertions:

- Unauthorized commands: no new job, no send.
- Retry: keeps original notification ID, creates new attempt.
- Resend: creates new notification ID with `resendOf`.
- Duplicate idempotency key: no second email.
- Suppressed/expired/pending approval: not sent yet.
- Correct authorized recipient, no unauthorized `Bcc`/`From` overrides.
- Audit records actor/reason/ticket/approval.
- Temporary SMTP failure triggers retry backoff.
- SMTP acceptance transitions to `SUBMITTED`, never auto-marking `DELIVERED`.

Never use production SMTP accounts or real recipient addresses in CI.

## 46. Manual retry runbook

1. Identify notification ID, actor, and tenant/ticket scope.
2. Read status, last failure class, attempt history, and `nextAttemptAt`.
3. If `PROCESSING`, inspect owner/lease instead of adding claims.
4. If `RETRY_WAIT`, check whether an automatic retry is imminent.
5. If `FAILED_TRANSIENT`/`FAILED_EXHAUSTED`, confirm the root cause is resolved.
6. If `FAILED_PERMANENT`, fix underlying data/config first.
7. If `AMBIGUOUS`, inspect provider queue IDs/logs and duplicate risk.
8. If `SUBMITTED`/`DELIVERED`, do not retry; evaluate a separate resend.
9. Verify recipient, consent, suppression, and deadlines.
10. Record reason/ticket and obtain approval when required.
11. Submit idempotent command.
12. Monitor the operation, SMTP outcome, and downstream events.

Never run raw SQL `UPDATE mail_notification SET status='READY'` as routine operations, because it bypasses authorization, auditing, and state transitions.

## 47. Runbook for customer resend requests

1. Verify the requester is authorized to receive a copy.
2. Locate the original notification and category/content version.
3. Verify whether the original is `SUBMITTED`/`DELIVERED` or `AMBIGUOUS`.
4. Check whether it is merely a provider delay.
5. Check snapshots, attachments, and token expirations.
6. Check current consent/suppression/recipient eligibility.
7. If the address changed, switch to the verified recipient-change workflow.
8. Review resend history and cooldowns.
9. Verify authority, tenant scope, and approval requirements.
10. Record reason/ticket and create an operation with an idempotency key.
11. Create a new notification linked via `resendOf`.
12. Track worker SMTP submission and provider events.

The goal is an intentional copy without erasing history, misdelivering, or bypassing business policies.

## 48. Common anti-patterns

| Anti-pattern | Consequence | Alternative |
| --- | --- | --- |
| Only hiding the Retry button | API can be called directly | Server-side authorization |
| Checking only `ROLE_ADMIN` | Bypasses tenant, state, consent | RBAC + ABAC |
| Operators calling `JavaMailSender` directly | Hard to audit, exposes transport secrets | Durable commands/workers |
| Retrying every `FAILED` state | Permanent error loops | Failure-class policies |
| Retrying `SUBMITTED`/`DELIVERED` | Duplicate sends | Create new resend notification |
| Resend resets original to `READY` | Corrupts history | Insert new record with `resendOf` |
| Resending old OTPs/tokens | Expired tokens/security risk | Identity workflow reissue |
| Letting operators fill `To`/`Bcc`/`From` freely | Data leaks/open relay | Verified sender/recipient sources |
| Omitting tenant filter in queries | Cross-tenant access | Tenant-scoped lookups |
| In-memory idempotency | Restarts break deduplication | Durable unique keys |
| No cooldowns/attempt budgets | Spam/retry storms | Quotas/backoff |
| Ignoring unsubscribes | Violates consent | Recheck eligibility |
| Requester self-approval | Defeats maker-checker | Independent approver |
| Approvals unbound to payloads | Recipient altered post-approval | Immutable fingerprints |
| Updating without CAS/version | Races and duplicates | Atomic transitions |
| Treating HTTP 202 as sent | False reporting | Operation/attempt statuses |
| Treating SMTP accepted as delivered | False reporting | Provider events |
| Retrying post-DATA timeouts as unsent | Duplicates | `AMBIGUOUS`/reconciliation |
| Logging OTPs, raw HTML, attachments | Data leakage | Minimized audit/telemetry |
| Using log collector as sole audit store | Lost when collector fails | Durable audit records |

## 49. Production rollout roadmap

1. Separate automatic retries, manual retries, and resends clearly.
2. Build a state machine covering transient, permanent, ambiguous, submitted, and suppressed states.
3. Define action-level authorities instead of a single generic role.
4. Apply ABAC over tenant/resource/category/ticket/consent/deadlines.
5. Place Spring Security method authorization on command services.
6. Add authoritative policy checks inside transactions.
7. Use optimistic versions/conditional SQL for retries.
8. Make resends insert new notifications while keeping originals immutable.
9. Enforce durable idempotency keys and operation receipts.
10. Enforce cooldowns, quotas, and retry budgets.
11. Add maker-checker approvals for sensitive cases.
12. Run workers under dedicated service identities without HTTP tokens.
13. Durably audit actors, reasons, approvals, and state transitions.
14. Revalidate eligibility before SMTP whenever data can change.
15. Let UI display capabilities/confirmations without replacing backend enforcement.
16. Test denied/allowed paths, cross-tenant checks, concurrency, ambiguity, and audits.
17. Add metrics/alerts and incident runbooks.

## 50. Pre-authorization checklist

- [ ] Is the actor authenticated through an appropriate mechanism?
- [ ] Does the actor hold the exact authority for **retry** or **resend**?
- [ ] Does the actor have scope over the specific tenant/resource/ticket?
- [ ] Do the status and failure class allow the action?
- [ ] Does the original have an `AMBIGUOUS` outcome or pending delivery?
- [ ] Are `Recipient`/`From`/`Bcc` resolved from trusted sources?
- [ ] Are consent, suppression, complaints, and business expiry still valid?
- [ ] Does a security email require issuing a fresh token?
- [ ] Are cooldowns, quotas, and retry budgets satisfied?
- [ ] Are reason/ticket/approval requirements complete?
- [ ] Are idempotency keys and expected versions verified?
- [ ] Does the audit record commit alongside the command mutation?
- [ ] Does the worker enforce leases/ownership and recheck eligibility?
- [ ] Does the API return `ACCEPTED`/`PENDING` rather than claiming `DELIVERED`?
- [ ] Are logs/metrics free of credentials, OTPs, and raw MIME?

## 51. Takeaways

- **Automatic retries** belong to workers/policies; **manual retries** resume existing notifications; **resends** create new notifications.
- Action authorization equals authentication + RBAC/ABAC + business policies, never roles alone.
- Tenant scope must be enforced inside resource queries; UUIDs do not replace authorization.
- Retry by state and failure class—never blindly retry all errors.
- `SUBMITTED`/`DELIVERED` do not belong in retry flows; sending another copy requires resending.
- `AMBIGUOUS` after SMTP `DATA` requires reconciliation due to duplicate risks.
- Expired OTPs/reset links must never be resent by copying raw emails.
- Resend never grants permission to ignore unsubscribes/suppressions/consent.
- `@PreAuthorize` is a coarse-grained gate; domain policies and atomic DB updates protect the real decision.
- Never trust actor/roles/tenant passed in request bodies as authentication sources.
- Durable idempotency prevents double-clicks and gateway retries.
- Resends create new notifications with `resendOf`; originals keep immutable status history.
- Approvals are time-bound, separate requester from approver, and bind immutable payloads.
- Workers run under service identities rather than passing operator JWTs through async queues.
- Audits of actors/reasons/tickets/approvals must be durable and data-protected.
- Manual actions remain subject to rate limits, cooldowns, and provider quotas.
- HTTP 202 signals operation accepted, not SMTP delivered.
- Always revalidate permissions and eligibility when state may have mutated.

**Core principle:** In production Spring Framework Mail systems, retry and resend are **authorized, policy-governed, audited, and idempotent business commands**, not two buttons wired straight to `JavaMailSender.send(...)`. Keep retries on the original notification, create new notifications for resends, guard tenants/recipients/consent, and delegate SMTP execution to workers holding dedicated infrastructure privileges. That design makes operations auditable, curbs misdelivery and duplicates, and prevents support tools from becoming security vulnerabilities.
