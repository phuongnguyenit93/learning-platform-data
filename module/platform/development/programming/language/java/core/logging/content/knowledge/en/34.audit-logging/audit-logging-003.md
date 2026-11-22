# Who Performed the Action in Audit Logging (Java)

## 1. What Does the Question “Who Did This?” Mean?

In **audit logging**, the question **“Who performed the action?”** needs to identify the **actor**: the authenticated identity, or an explicitly designated anonymous/system identity, that executed or ordered an action of security or business significance. A log line such as `INFO User updated profile` is not sufficient as an audit trail: it does not clarify the subject, the modified target, the effective permissions, the timestamp, or the final outcome.

Example:

```text
User user_42 logs in successfully
    │
    ▼
Request to change role of user_91
    │
    ▼
API checks permissions, updates, and commits
    │
    ▼
Audit event:
  actor.type=USER
  actor.id=user_42
  action=ASSIGN_ROLE
  target.type=USER
  target.id=user_91
  outcome=SUCCESS
```

In the event above, **user_42 is the performer**, and **user_91 is the affected target**. An ambiguous field like `userId=user_91` can mislead investigators.

This article focuses on how to reliably answer:

- Is the subject a **user, service account, automated task, or anonymous caller**?
- Who **initiated** it, who used the **execution credentials**, who was **impersonated**, and who **approved** it?
- Does the identity come from a **verified security context/token** or from a self-declared client header?
- Was the action **requested, denied, committed, or still waiting for a worker to process**?
- Is the actor ID stored alongside the issuer/tenant, target, event ID, and request/job/trace ID for correlation?
- Is the record trustworthy, tamper-evident, and stored in accordance with audit requirements?

**An actor is not synonymous with an IP address, user-agent, thread name, logger name, request ID, or trace ID.** Those pieces of information can assist an investigation, but they do not by themselves prove the identity of the performer.

## 2. Distinguishing Actor, Initiator, Executor, Subject, Target, and Approver

Terms like `subject` or `principal` can carry different meanings across IAM, Spring Security, and business domains. An audit schema should **explicitly define** these roles:

| Role | Meaning | Example |
| --- | --- | --- |
| **Actor / executor** | The identity performing the action at the boundary where the event is recorded | `user_42` or `svc_export` |
| **Initiator / requested_by** | The subject that initiated the processing chain, if the link is verified | `user_42` requesting an async export |
| **Effective identity** | The actual credential/principal used to call the backend and evaluate permissions | The worker's `svc_export` |
| **Effective subject / acted-for user** | The account on whose behalf the actor is authorized to operate | `user_91` in an impersonation session |
| **Target** | The resource or account being read, modified, or deleted | `report_17` or `user_91` |
| **Approver** | The person who approved a step in the workflow | `manager_7` |
| **Service/workload** | The application/process emitting the event | `report-worker` |
| **Authentication source** | The issuer/method that verified the actor | `idp_main`, `workload_identity` |
| **Correlation key** | Key linking the request, job, trace, and events | `req_101`, `job_22` |

**Executor ≠ initiator** in asynchronous scenarios: a user requests a report export, while a worker service actually generates the file. **Actor ≠ target** when an admin changes another person's permissions. **Approver ≠ executor** when one person approves and a separate service executes.

Do not record `initiated_by=user_42` just because a message queue payload contains an arbitrary `requestedBy` field sent by the client. The relationship between initiator and executor must come from an **authenticated step and protected metadata**, or else indicate that the relationship is unverified.

## 3. Actor Types and Identity Attribution Principles

### 3.1. Authenticated Users

The actor is an account authenticated by the system via a valid session, IdP, or verified token. Use a **canonical/stable actor ID** rather than storing only an email or display name: usernames can change, and emails can be recycled.

If an event has `actor.id=user_42`, you need to know whether this value was provided by the **security layer** after authentication or extracted by a controller from the request body. Only the former provides a trustworthy basis.

### 3.2. Service Accounts and Workload Identity

A microservice, batch job, system script, or worker running under a service identity must be recorded as **SERVICE**, rather than being attributed to a user account named `system_admin`.

For example: `actor.type=SERVICE`, `actor.id=svc_cleanup`, `trigger.type=SCHEDULE` for a data cleanup job. The person who originally created the schedule can be recorded in a separate **CREATE_SCHEDULE** event, but is not necessarily the one directly initiating each subsequent run.

### 3.3. User-Initiated Processing via a Service

A request is authenticated as user `user_42`, then enqueued for worker `svc_export` to execute:

```text
user_42 (authenticated)
   │
   ▼
API stores job_22, requested_by=user_42
   │
   ▼
Queue/DB with protected metadata
   │
   ▼
Worker runs with credential svc_export
   │
   ▼
Audit event:
  executor.type=SERVICE
  executor.id=svc_export
  initiated_by=user_42
  job_id=job_22
  action=EXPORT_REPORT
```

**Do not change the executor to `user_42` just to make reports look “cleaner”.** The user is the initiator, while the service is the executing subject in the worker. To establish end-to-end accountability, preserve the proven delegation/authorization link.

### 3.4. Impersonation and Delegated Actions

Support staff `support_8` is authorized to operate within the context of account `user_42`. The audit log must preserve both the **real actor `support_8`** and the **effective subject `user_42`**; recording only `actor=user_42` can wrongly attribute the staff member's actions to the user.

Depending on policy, you may also need delegation session ID, expiration, permission scope, approval, purpose, and reason. When there is no delegation, do not fabricate it; when it cannot be verified, explicitly record an unknown state.

### 3.5. Unauthenticated Callers

A rejected login attempt with username `admin` does **not** prove that `admin` accessed the system. The appropriate actor is **ANONYMOUS/UNAUTHENTICATED**, with outcome `DENIED`; `claimed_identifier=admin` is merely client-supplied data, which must be marked untrusted and handled with privacy considerations in mind.

## 4. Where Does Trustworthy Identity Come From?

Typical order of more trustworthy sources, depending on architecture:

1. **Security context** constructed after authentication/authorization inside the application.
2. **Verified session or bearer token/JWT** validated through a properly configured authentication library.
3. **Workload/service identity** authenticated by an appropriate mechanism (mTLS, platform identity, client credentials).
4. **Delegation/initiator information** from a job/workflow record created after authentication with access-controlled modification rights.

Sources that **do not by themselves authenticate an actor**:

- `X-User-ID`, `X-Authenticated-User`, or `X-Forwarded-User`, which a client can spoof.
- `X-Forwarded-For`, IP, or `User-Agent`: do not prove a real person.
- `createdBy` in a request body.
- `traceparent` or `X-Request-ID`: correlation metadata only.
- MDC containing client-supplied IDs or leaked values from a previous request.
- `Authorization` manually decoded **without verifying the token**.

If an API gateway is responsible for authentication and forwarding identity via headers, you must define the trust boundary: block bypass paths, strip client-supplied identity headers, secure/authenticate gateway-to-service connections, and define rules for handling invalid identities. Do not rely solely on “the internal network”.

### JWT/OIDC: `sub` Is Insufficient Without a Namespace

`sub` is typically meaningful **within the scope of an issuer**. Two IdP systems can issue the same `sub="123"` for two unrelated identities. To form a canonical actor, use the **(verified issuer, subject)** pair or map it to a stable internal user ID.

You must verify the signature, issuer, audience, time validity, and application-specific token requirements **before** using claims as evidence. A **client credentials** access token can represent a service rather than a human user. Do not assume every token with a `sub` claim belongs to `actor.type=USER`.

## 5. Designing a “Who Did What to Whom?” Schema

A structured event should distinguish at least:

| Field | Meaning |
| --- | --- |
| `event.id` | Event ID for duplicate/gap detection; does not by itself guarantee integrity |
| `event.time` | Timestamp of the action at the source, with explicit UTC/offset |
| `event.name` / `action` | Fixed action code such as `ASSIGN_ROLE` |
| `actor.type` | `USER`, `SERVICE`, `ANONYMOUS`, or a defined enum |
| `actor.id` | Canonical ID or a value explicitly indicating anonymous |
| `actor.issuer` / `auth.method` | Authentication source/method when available |
| `actor.authenticated` | Whether the subject is authenticated or merely a claimed identity |
| `initiated_by` | Initiating subject when backed by evidence |
| `effective_subject` | Account being acted on behalf of, if applicable |
| `tenant.id` | Tenant from a trusted context, properly namespaced |
| `target.type`, `target.id` | Affected resource |
| `outcome` | `SUCCESS`, `DENIED`, `FAILED`, or an explicit business status |
| `reason.code` | Reason code containing no secrets |
| `request_id`, `job_id`, `trace_id` | Correlation across steps |
| `source.service` / `source.instance` | Component emitting the event |
| `schema.version` | Schema/contract version |

Illustrative JSON example:

```json
{
  "event.id": "evt_501",
  "event.time": "2026-11-10T03:15:00Z",
  "event.name": "ASSIGN_ROLE",
  "actor.type": "USER",
  "actor.id": "user_42",
  "actor.issuer": "idp_main",
  "actor.authenticated": true,
  "target.type": "USER",
  "target.id": "user_91",
  "outcome": "SUCCESS",
  "request_id": "req_101",
  "source.service": "identity-api",
  "schema.version": 1
}
```

The field names here are an **illustrative schema**, not a claim of a mandatory standard for every system. You must define types, nullability, identifiers, namespaces, retention periods, and sensitivity levels. Clean JSON **does not** prove that the identity was verified or that the event was durably stored.

## 6. Do Not Confuse Target with Actor or Request with Outcome

Example of an admin granting a role:

```text
actor.id     = admin_7
action       = GRANT_ROLE
target.id    = user_91
role.granted = REPORT_VIEWER
outcome      = SUCCESS
```

Example of a data cleanup service:

```text
actor.type   = SERVICE
actor.id     = svc_cleanup
trigger.type = SCHEDULE
action       = DELETE_EXPIRED
target.type  = ARCHIVE_BATCH
outcome      = SUCCESS
```

Example of an approval workflow: there should be an **APPROVE** event with the approver as the actor and an **EXECUTE** event with the executor as the actor. Do not collapse `approver` and `executor` into a single `userId` field.

Similarly, **REQUESTED**, **AUTHORIZED**, **COMMITTED**, **DENIED**, **FAILED**, and **DELIVERED** are milestones with distinct semantics. An API returning 202/200 might only create a job without executing the business operation yet. If the audit log records “user exported report” at enqueue time, the record will be wrong if the worker fails.

## 7. Standalone Java 17 Example: Distinguishing User, Service, and Anonymous

The following program uses **plain JDK** without Spring/SLF4J. It creates sample actors assumed to have been **authenticated by a trust layer outside the program**, then emits events describing direct actions, delegated processing, internal tasks, and unauthenticated requests.

**Limitations:** `main` only instantiates illustrative objects; **the `Actor` constructor does not authenticate identities**. In a real application, never let clients supply actor IDs and treat them as truth. Stdout is also not a durable audit store.

Save the file as **`AuditActorDemo.java`**:

```java
import java.time.Instant;
import java.util.Objects;
import java.util.regex.Pattern;

public final class AuditActorDemo {
    private static final Pattern SAFE =
            Pattern.compile("[A-Za-z0-9_.:-]{1,80}");

    enum ActorType {
        USER, SERVICE, ANONYMOUS
    }

    record Actor(ActorType type, String id, String verifiedBy) {
        Actor {
            Objects.requireNonNull(type);
            checked(id);
            checked(verifiedBy);
        }
    }

    record AuditEvent(
            String eventId,
            Instant time,
            Actor executor,
            String initiatedBy,
            String action,
            String target,
            String outcome,
            String requestId) {
        AuditEvent {
            checked(eventId);
            Objects.requireNonNull(time);
            Objects.requireNonNull(executor);
            checked(initiatedBy);
            checked(action);
            checked(target);
            checked(outcome);
            checked(requestId);
        }
    }

    private static void checked(String value) {
        if (value == null || !SAFE.matcher(value).matches()) {
            throw new IllegalArgumentException("Invalid audit field");
        }
    }

    private static void emit(AuditEvent event) {
        System.out.printf(
                "time=%s event=%s actor_type=%s actor_id=%s "
                        + "verified_by=%s initiated_by=%s "
                        + "action=%s target=%s outcome=%s request_id=%s%n",
                event.time(),
                event.eventId(),
                event.executor().type(),
                event.executor().id(),
                event.executor().verifiedBy(),
                event.initiatedBy(),
                event.action(),
                event.target(),
                event.outcome(),
                event.requestId());
    }

    public static void main(String[] args) {
        Instant time = Instant.parse("2026-11-10T03:15:00Z");

        // Assume identities have already been authenticated at the trust layer.
        Actor user = new Actor(ActorType.USER, "user_42", "idp_main");
        Actor worker = new Actor(
                ActorType.SERVICE, "svc_export", "workload_identity");
        Actor anonymous = new Actor(
                ActorType.ANONYMOUS, "unknown", "none");

        // User directly requests an action.
        emit(new AuditEvent(
                "evt_001", time, user, "-",
                "REQUEST_EXPORT", "report_17", "SUCCESS", "req_101"));

        // Worker executes a job requested by an authenticated user.
        // initiatedBy is only valid when job metadata is protected.
        emit(new AuditEvent(
                "evt_002", time, worker, "user_42",
                "EXPORT_REPORT", "report_17", "SUCCESS", "req_101"));

        // Service acts on its own, with no initiating user.
        emit(new AuditEvent(
                "evt_003", time, worker, "-",
                "CLEANUP_EXPORT", "archive_4", "SUCCESS", "job_22"));

        // Failed login: do not use the self-declared name as the actor.
        emit(new AuditEvent(
                "evt_004", time, anonymous, "-",
                "LOGIN", "session", "DENIED", "req_102"));

        // Input containing newline characters is blocked before logging.
        try {
            new Actor(ActorType.USER, "admin\nFAKE", "idp_main");
        } catch (IllegalArgumentException ex) {
            System.out.println("untrusted_actor_id=rejected");
        }
    }
}
```

Compile and run with **JDK 17+**:

```bash
javac --release 17 AuditActorDemo.java
java AuditActorDemo
```

Exact stdout:

```text
time=2026-11-10T03:15:00Z event=evt_001 actor_type=USER actor_id=user_42 verified_by=idp_main initiated_by=- action=REQUEST_EXPORT target=report_17 outcome=SUCCESS request_id=req_101
time=2026-11-10T03:15:00Z event=evt_002 actor_type=SERVICE actor_id=svc_export verified_by=workload_identity initiated_by=user_42 action=EXPORT_REPORT target=report_17 outcome=SUCCESS request_id=req_101
time=2026-11-10T03:15:00Z event=evt_003 actor_type=SERVICE actor_id=svc_export verified_by=workload_identity initiated_by=- action=CLEANUP_EXPORT target=archive_4 outcome=SUCCESS request_id=job_22
time=2026-11-10T03:15:00Z event=evt_004 actor_type=ANONYMOUS actor_id=unknown verified_by=none initiated_by=- action=LOGIN target=session outcome=DENIED request_id=req_102
untrusted_actor_id=rejected
```

Explanation:

- `evt_001` describes the user requesting an export.
- `evt_002` has **executor `SERVICE svc_export`** and `initiated_by=user_42` from an evidenced workflow; it does not conflate the two roles.
- `evt_003` does not fabricate a user for an internal task.
- `evt_004` keeps `actor_type=ANONYMOUS` because the person attempting to log in is not verified.
- `checked(...)` uses a simple allowlist to block control characters when formatting key=value text; it **does not authenticate the actor** and does not replace a proper JSON encoder. In production, enforce parser-safe escaping/limits and data policies.
- The fixed timestamp is only to make output verification deterministic; real events require real-time timestamps and clock synchronization.
- The program does not implement transactions, retries, outbox, queues, TLS, or audit store access control. Do not treat a stdout example as tamper-resistant, durable evidence.

## 8. Spring Security: Extracting Identity from the Security Context

Spring Boot applications using Spring Security typically have an `Authentication` object in the security context populated by an authentication filter. The following snippets require dependencies and security configuration and are **not standalone Java files**:

```java
org.springframework.security.core.Authentication auth =
        org.springframework.security.core.context.SecurityContextHolder
                .getContext().getAuthentication();

if (auth != null) {
    String name = auth.getName();
    // Map name according to the configured Authentication implementation.
    // Do not assume name is the canonical user ID.
}
```

**`auth != null` and `auth.isAuthenticated()` are not enough to prove a real user.** Some Spring Security configurations create an `AnonymousAuthenticationToken`, where `isAuthenticated()` can be `true`. You must identify the mechanism that actually authenticates the user/service and distinguish anonymous callers.

When using OAuth2 Resource Server JWT, you can extract the subject from a **`JwtAuthenticationToken` already verified by the resource server**:

```java
// Illustrative snippet; not a standalone application.
// auth has been created through a trusted security filter chain.
if (auth instanceof org.springframework.security.oauth2.server.resource
        .authentication.JwtAuthenticationToken jwtAuth) {
    org.springframework.security.oauth2.jwt.Jwt jwt = jwtAuth.getToken();
    String subject = jwt.getSubject();
    // Combine verified issuer + subject or map to an internal ID.
    // Classify USER/SERVICE according to the identity model, not just sub.
}
```

Key considerations:

- `getName()` may be a username, token subject, or service name depending on the authentication provider.
- `jwt.getSubject()` is only meaningful after signature/issuer/audience/expiry and token policies have been verified.
- A client credentials token can represent a **workload**, not a human user.
- Do not log tokens, raw `Authentication`, session secrets, or the full `Principal.toString()`.
- Session auth, API keys, and mTLS each have their own actor mapping rules; centralize this logic in an application-defined and tested **ActorResolver** component.
- If authentication is anonymous or the token is invalid, do not fabricate a `USER` actor by reading a name from the request.

Do not copy the HTTP security context pattern into an async worker and assume `ThreadLocal` still holds the user's identity. Verified metadata must be propagated properly.

## 9. Background Jobs, Message Consumers, and Scheduled Tasks

### Initial Request and Job Metadata

When a user triggers an asynchronous task:

1. Authenticate the user at the request boundary and obtain the canonical actor ID and tenant ID from a trusted context.
2. After authorization checks, persist the job record: `job_id`, `requested_by`, `tenant`, `action`, `target`, `request_id`.
3. Protect the job metadata and issuer/tenant bindings; clients must not be able to arbitrarily modify `requested_by`.
4. The worker authenticates with its service identity and reads the protected metadata.
5. The audit event at worker execution records the **executor service** and the **initiator** if the link is verified.
6. Include `operation_id` and an attempt ID to distinguish retries from new actions.

**Do not pass full user credentials/tokens into long-lived queues** just so the worker can log the actor. When downstream authorization is needed, use controlled delegation/token exchange with appropriate expiration.

### Schedules and System Triggers

A nightly job does not become an action of the person who created the schedule earlier. Record `actor=SERVICE(svc_cleanup)`, a `SCHEDULE` trigger, and the schedule/job ID. If the schedule is modified, emit an **UPDATE_SCHEDULE** event with the modifying user as the actor at that time.

### MDC/ThreadLocal and Cross-Contamination

Workers use thread pools; `SecurityContextHolder`/MDC may not propagate automatically or may leak if not restored. A trace ID also does not prove an actor. If using MDC to include an actor ID in logs, snapshot verified metadata per event and clean/restore it strictly within scope—never treat `MDC.get("actor")` from a log-consuming thread as proof.

## 10. Impersonation: Recording Both the Real Performer and the Acted-For User

A support agent `support_8` operates in impersonation mode for `user_42`:

```text
real_actor.type       = USER
real_actor.id         = support_8
effective_subject.id  = user_42
delegation.mode       = IMPERSONATION
delegation.session_id = imp_801
action                = UPDATE_CONTACT
target.type           = PROFILE
target.id             = profile_42
outcome               = SUCCESS
```

The audit log needs to show:

- **Who authenticated:** `support_8`.
- **Which permission/session was used:** the delegation session and permitting policy.
- **On whose behalf the action ran:** `user_42`.
- **Which resource changed:** `profile_42` and the actual outcome.
- **Who approved it:** if required by the workflow.
- **Purpose/expiry:** when needed for risk governance.

If an application only reads the effective principal during an impersonation session and logs `actor=user_42`, it hides the real operator. Conversely, do not fabricate delegation if support is simply viewing information using their own permissions. The fields `initiated_by`, `effective_subject`, and `approver` must maintain stable semantics.

## 11. Tenant, Issuer, and Identity Lifecycle

**Namespace:** the same string `user_42` can exist across multiple tenants or issuers. Use a canonical global ID or include the verified tenant/issuer. Do not take the tenant from a raw `X-Tenant-ID` header without verifying it against the actor's actual permissions.

**Renaming:** usernames, emails, and display names can change and be reused. Audits should retain non-reusable IDs; snapshot display names only if purpose and retention policies allow.

**Locked/deleted accounts:** historical events must still be explainable under policy. Do not delete audit trails needed for investigations just because an operational account was deleted, nor retain PII indefinitely without justification.

**Credential theft:** an audit log can prove a credential was used, not necessarily that the human owner of the credential personally performed the action. Investigations must distinguish between “verified credential/identity” and “proven human behind the keyboard”.

## 12. When Is an Action Considered SUCCESS?

An audit of **REQUESTED** does not mean **COMMITTED**. A request can be accepted and the job can later fail. A database transaction can roll back. Define clear milestones:

```text
Request authenticated
     │
     ▼
Authorization decision  → AUTHORIZED / DENIED
     │
     ▼
Start business action    → ATTEMPTED (if needed)
     │
     ▼
DB transaction commit    → COMMITTED / FAILED
     │
     ▼
Async delivery/notify    → DELIVERED / DELIVERY_FAILED
```

For auditing committed data changes, you can use a **transactional outbox**: write the business state and the outbox event within the **same DB transaction**. A publisher delivers the event after commit, requiring retry/deduplication and backlog monitoring. An outbox does not by itself guarantee end-to-end exactly-once delivery without full-chain mechanisms.

If an action is rejected before commit, emit a separate `DENIED` security event if needed. Do not log a false `SUCCESS` just because the controller received the request. If there are separate approver and executor roles, emit events with the appropriate actor at each milestone.

## 13. Audit Is More Than an Application Log Line

For an event to be trustworthy, you must protect:

- **Actor source:** obtained from a verified identity, not from client headers.
- **Event accuracy:** action/target/outcome determined by business logic at the right point.
- **Safe schema/encoder:** structured, escaping control characters and preventing log forging (CWE-117).
- **Separation of duties:** a service that only emits audit events must not by default be able to delete or modify historical logs.
- **Storage and retention:** append-only/immutable storage or an audit store meeting compliance requirements.
- **Collector authentication and transport:** protect the channel and tenant routing.
- **Loss/duplication detection:** event IDs, counts, queue drops, ingestion lag, and transaction reconciliation.
- **Timestamps:** both event time and ingestion time if needed, plus clock synchronization.
- **Configuration:** audit who changes filters, levels, destinations, masking, or retention.

Signatures/MACs/hash chains can help detect tampering if keys are protected and verification is properly implemented. However, **signing a fake actor ID taken from a request does not make it true**. Any evidence is only as trustworthy as its initial authentication source.

### Log Injection and Field Formatting

Writing a raw username containing `\nERROR user=admin` into plain-text logs can forge a new log line. Use a structured encoder and validate/escape inputs. Parameterized logging avoids some message-construction bugs, but placeholders **do not automatically escape CRLF** in every text formatter. Never use client input as a logger name, filename, event type, or source identity.

## 14. Protecting Personal Data and Secrets

Audit logs often require an actor ID, but there is no default reason to store:

- Passwords, OTPs, access/refresh tokens, cookies, API keys, or private keys.
- Raw JWTs, full `Authentication` or `Principal` objects, or full HTTP headers/bodies.
- URLs/query strings containing tokens or sensitive data.
- Emails, physical addresses, account numbers, or other sensitive data outside the audit purpose.
- Trace baggage or MDC containing PII copied onto every event.

Use a **field allowlist**, canonical IDs, and reason codes instead of free-form messages containing secrets. When IP/device info is needed for security, record it as metadata under its own policy; IP does not replace the actor. Restrict search/export/delete permissions, apply appropriate retention, and protect backups and CSV exports as well.

Do not let `request_id` or `actor.id` become unbounded-cardinality metric labels; doing so can spike costs and overload observability systems.

## 15. Common Implementation Mistakes

| Symptom | Likely Cause | Remediation |
| --- | --- | --- |
| Log shows admin, but token belongs to another user | Using `X-User-ID` from the request | Map from the verified principal |
| Failed login attributed to `admin` actor | Confusing claimed username with authenticated identity | Use `ANONYMOUS` actor, separate claimed identifier |
| Retried job records user as executor | Not separating user initiator and worker identity | Keep `SERVICE` executor and `initiated_by` |
| Support acts on behalf of customer, audit only shows customer | Reading effective subject as actor | Record real actor and delegation context |
| Tenant A has audit IDs from Tenant B | MDC/ThreadLocal leak or tenant from header | Context save/restore and verified tenant |
| Transaction rolls back, but audit says SUCCESS | Logging before commit | Log at commit milestone, outbox, or explicit status |
| One action counted multiple times | Retries/duplicate messages | Operation ID, event ID, deduplication |
| Cannot find user after rename | Storing only username/email | Canonical stable ID + namespace |
| Service account treated as a human user | Assuming JWT `sub` is always `USER` | Classify properly in the identity model |
| Audit events lost when disk/collector overloaded | Queue drops, sink errors, un-drained buffers | Delivery metrics, durable path if needed |
| Admin deletes their own audit trail | Ingest and delete permissions not separated | RBAC, immutable copy, tamper alerts |
| Trace ID exists, but actor is unknown | Trace only provides correlation | Resolve actor at the authentication boundary |
| HTTP 200 returned, but no actual operation occurred | Async accepted or rollback | Distinguish requested vs. committed |
| Events merged across two IdPs | Storing `sub` without issuer | Use verified issuer + subject |
| Actor string injects fake log lines | CRLF not neutralized | Structured encoding and validation |

## 16. Testing Actor Attribution

A minimal test matrix:

| Scenario | Expected Actor | Required Links |
| --- | --- | --- |
| User changes a role | `USER user_42` | Target `user_91`, outcome after commit |
| User requests export, worker executes | `SERVICE svc_export` in worker | `initiated_by user_42` if evidenced |
| Cron runs automatically | `SERVICE svc_cleanup` | Schedule/job ID, no fabricated user |
| Support impersonates user | `USER support_8` as real actor | Effective subject `user_42` + delegation |
| Anonymous attempts login | `ANONYMOUS` | Claimed username only as untrusted metadata |
| Service B calls Service A | `SERVICE svc_b` at A | Attach original user only with trusted delegation |

**Important negative tests:**

1. Send `X-User-ID: admin` without valid credentials: must not attribute to `admin`.
2. Two tenants/issuers with the same user ID string: must not be conflated as the same person.
3. Username containing newlines, control characters, and oversized payloads: must not forge logs or overflow.
4. Two consecutive requests on the same thread pool: MDC and actor must not leak.
5. Worker processes a job after the original request ends: initiator remains accurate if metadata was protected.
6. Impersonation: real actor, effective subject, session, and approval are recorded separately.
7. Transaction rollback: no false `COMMITTED`/`SUCCESS` event.
8. Worker retry: audit includes an operation ID to distinguish one action from multiple attempts.
9. Full queue/broken collector: reports dropped event count or backpressure, rather than silently pretending events were saved.
10. Read-only audit role cannot modify/delete history or read other tenants.
11. User renames/locks account: historical events remain queryable by stable ID.
12. Use **fake/canary** tokens to verify they do not leak into files, collectors, SIEMs, dashboards, or exports.

When testing, define the **expected actor/target/outcome** upfront, verify the event was actually persisted as required, and collect evidence. A line printed to the console does not prove the entire pipeline works.

## 17. Recommended Java Architecture

```text
HTTP Security Filter / Message Auth
  │
  └─ Verify token, session or workload credential
       │
       ▼
 ActorResolver (canonical actor ID, type, issuer, tenant)
       │
       ▼
 Application Service (authorization + business action)
       │
       ├─ Business transaction / outbox if needed
       ▼
 AuditEventBuilder (actor, initiator, action, target, outcome)
       │
       ▼
 Trusted Audit Sink / Collector
       │
       ▼
 Protected Audit Store + Search/Investigation
```

- **Security layer** authenticates the source and prevents controllers from picking actor IDs from the request body.
- **ActorResolver** is an application-built abstraction, not a default JDK/Spring class; it is responsible for normalizing identity/tenant/issuer.
- **Business layer** knows the true outcome milestone and target.
- **Audit builder** enforces the defined schema and event codes, controlling external data.
- **Audit sink** protects transport, storage, retention, and view/edit/delete permissions.
- **Investigators** distinguish credential identity from the human operator and correlate events via job/operation/trace IDs.

Beyond HTTP, message consumers, batch jobs, admin CLIs, migrations, and scheduled tasks must each have an appropriate actor model. Never reuse the user from “the most recent request” for background operations.

## 18. Investigation Workflow: Who Deleted the Resource?

An evidence-based investigation flow:

1. Identify the target/resource ID and the actual change in business data.
2. Find the corresponding audit event **at the `COMMITTED` milestone**, not just `REQUESTED`.
3. Check `actor.type`, `actor.id`, verified issuer, and tenant.
4. If the actor is `SERVICE`, follow the job/operation ID to check for a trusted `initiated_by`.
5. If impersonation was used, check the real actor, effective subject, and delegation session.
6. Cross-reference access logs, application logs, traces, and transaction/outbox records.
7. Check for retries/duplicates, clock drift, queue drops, tampering, or log-deletion permissions.
8. Report the confidence level: “a credential was used” differs from “a specific human definitely performed the action”.

Example of a cautious conclusion:

> “According to the post-commit audit event emitted by identity-api, the credential authenticated with canonical actor ID user_42, issuer idp_main, executed GRANT_ROLE on user_91 at 03:15 UTC. There is no independent evidence confirming that the account owner personally operated the session.”

## 19. Checklist for Answering “Who Performed the Action?”

- [ ] Defined actor/executor, initiator, effective subject, target, and approver.
- [ ] Actor is sourced from a verified security context or workload identity, not raw headers.
- [ ] Distinguishes `USER`, `SERVICE`, `ANONYMOUS`, and authentication source.
- [ ] Actor ID is stable, not just an email/display name; includes issuer/tenant namespace.
- [ ] Actor is not confused with the user/resource that is the target.
- [ ] For impersonation, both real actor and acted-for user are present.
- [ ] For background jobs, executor is the service, and initiator is attached only when the link is protected.
- [ ] For cron jobs, the schedule creator is not attributed as the actor of every run.
- [ ] Includes event ID and appropriate operation/job/request/trace IDs.
- [ ] Outcome reflects the actual processing milestone, without confusing accepted with committed.
- [ ] Protects against log forging and excludes unnecessary credentials/PII.
- [ ] Enforces RBAC, retention, integrity, and detection of lost/modified events.
- [ ] Tested anonymous, multi-tenant, impersonation, rollback, retry, and sink failure scenarios.
- [ ] Investigation guidelines distinguish credential identity from the human behind it.

**Key takeaway:** to answer **“who performed the action?”**, record the **authenticated identity at the right boundary**, separate the **initiating user** from the **executing service** and the **acted-for account**, and bind them to the **actual action, target, and outcome**. IP addresses, trace IDs, header names, or attempted login usernames cannot substitute for authentication evidence.

### References

- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [NIST SP 800-92 — Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final)
- [Spring Security — Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/index.html)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Oracle — Java 17 records](https://docs.oracle.com/en/java/javase/17/language/records.html)
