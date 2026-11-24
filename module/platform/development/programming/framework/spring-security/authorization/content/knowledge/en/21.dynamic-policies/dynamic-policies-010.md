# Storing Decision Reasons and Explaining Permissions Without Leaking Sensitive Data

## 1. The problem: why was access denied, yet what must not be disclosed?

In a Spring Security application with dynamic policies, users may encounter outcomes such as:

- Denied document edit because their role in the current tenant is insufficient.
- Denied document read because they are neither the owner nor hold a READ grant.
- Denied data export because the document is in a restricted state.
- Denied an operation because the policy just changed or membership was revoked.
- The system cannot verify permissions because the Policy Decision Point (PDP) is experiencing an error.

Users, support teams, and information security teams all need **decision explanations**. Yet an overly detailed response can itself become a new vulnerability:

~~~text
GET /tenants/north/documents/9843

Unsafe:
"You are not the owner. The owner is
 alice@private-company.example; the document belongs to tenant secret-merger;
 2 people in group finance-exec have been granted READ."

Safer for an unauthorized caller:
"Resource not found within your permitted access scope."
~~~

The first message confirms the document exists, reveals the owner, tenant name, authorized members, and org structure. An attacker can cycle IDs to **enumerate data** even without ever reading document contents.

Conversely, if everywhere logs only `DENY`, operations struggle to tell which rule triggered it, which policy version was running, or whether it was a grant/revoke race. Separate three outputs:

1. **Enforcement decision:** ALLOW, DENY, ERROR/INDETERMINATE, plus applicable scope.
2. **Internal audit record:** standardized reason code, policy revision, event/decision ID, and metadata **permitted to be stored**.
3. **External explanation:** minimal message matching the recipient's right to know without confirming out-of-scope resources.

**Guiding principle:** an explanation must never reveal more information than the verified access permission itself. Audit logs are also **a sensitive dataset**, requiring separate access control, retention limits, masking, and integrity verification.

## 2. Distinguishing policy decisions, reason codes, and user-facing messages

Example:

~~~text
Internal policy evaluation:
    effect          = DENY
    reasonCode      = RESOURCE_NOT_IN_AUTHORIZED_SCOPE
    policyVersion   = document-policy-v17
    decisionId      = 36c1...   (correlation only)
    resourceType    = Document
    action          = DOCUMENT_READ

External API:
    HTTP 404
    code            = RESOURCE_NOT_AVAILABLE
    message         = "Resource is unavailable within your access scope."
    requestId       = req-7814
~~~

**Internal reason codes** describe the policy branch. **Public codes** describe what the caller is allowed to know. The two codes do not have to map one-to-one. Multiple causes like "ID does not exist", "resource belongs to another tenant", and "missing READ ACL" can intentionally map to the same public response.

Comparison table:

| Data type | Audience | Granularity | Where stored/displayed? |
|---|---|---|---|
| Effect | PEP, service | ALLOW/DENY/ERROR | Authorization check result |
| Internal reason | PDP, authorized support | Blocked rule/branch code | Restricted audit store |
| Policy revision | Operations, compliance | Policy version/function | Audit/observability |
| Decision/request ID | Both internal and client | Non-secret lookup ID | Logs, responses if safe |
| Public explanation | Caller | Minimal, omits out-of-scope objects | HTTP body/UI |
| Diagnostic detail | Authorized personnel | May contain more sensitive details | Authenticated/audited support tools |
| Raw rule input | Generally do not store | May contain tokens, PII, ACLs | Transient processing only per data policy |

**A decision reason is not a verbatim exception message.** Never pass `exception.getMessage()` as a response or audit reason because exceptions from JPA, HTTP clients, or policy engines can contain SQL, URLs, account names, or business data.

## 3. Three disclosure tiers: public, support, and restricted security

A tiered model:

### Tier 1 — Ordinary callers

Report only functional permissions the caller is already allowed to see, or a generic message:
- `AUTHENTICATION_REQUIRED`.
- `ACTION_NOT_AVAILABLE`.
- `RESOURCE_NOT_AVAILABLE`.
- `AUTHORIZATION_TEMPORARILY_UNAVAILABLE`.
- `requestId` for contacting support.

Never tell an unauthorized caller the real owner, real tenant name, others' roles, SECRET classification, existing grants, internal rules, or anti-fraud policies.

### Tier 2 — Verified resource owners / tenant administrators

A verified owner can sometimes see more specific causes, such as:
- "Your document is locked and cannot be edited."
- "You need the DOCUMENT_SHARE permission in this workspace."
- "Download limit exceeded under workspace policy."

**Condition:** before showing detailed explanations, the system must **check an independent permission to view resource/policy details**. Never assume a rejected READ caller automatically has permission to inspect owners/ACLs.

### Tier 3 — Operations / information security

Authorized incident responders can access **minimized** audit reasons, policy versions, revocation sequences, tenant/actor references, and decision traces. Audit read access must follow need-to-know, strong authentication where appropriate, access logging, and export limits.

**Never expose an open `GET /why-denied?id=...` endpoint** returning detailed reasons to any user. Explanation endpoints are themselves **policy enforcement points** (PEPs) requiring protection, rate limiting, and anti-enumeration controls.

## 4. Threat model for "permission explanations"

Attackers can exploit:

| Channel | Potentially leaked data | Scenario |
|---|---|---|
| HTTP 403/404 body | Existence, owner, tenant, classification | Guessing IDs to enumerate objects |
| Response timing differences | Object existence, ACL rule count | Distinguishing nonexistent IDs from existing-but-forbidden ones |
| Log search UI | Tokens, emails, internal addresses, policy inputs | Under-privileged staff searching data |
| Log forwarding | Headers, raw JSON, secrets | Accidental shipping to third-party SIEM/vendors |
| Exception stack traces | SQL, schemas, internal endpoints, role names | Exposed in error responses |
| Tracing attributes | URLs containing tokens, sensitive resource IDs | Collectors visible to many teams |
| Metrics labels | User IDs, tenants, document IDs | High cardinality and identifier leaks |
| OPA decision logs | Full `input`/`result` | Decision logging enabled without masking |
| Support chatbots/tickets | Verbatim copied audit contents | Ticket recipient lacks clearance |
| CSV exports | Full decision history, ACL graphs | Exports not scoped to viewer |
| Reason caching | Actor A's explanation served to B | Keys missing subject/tenant/action |
| Multi-tenant admin UI | Another tenant's logs | Tenant filtering enforced only in frontend |

Data protection does not stop at HTTP responses. **Logs, traces, metrics, dashboards, backups, tickets, and exports** all fall inside the audit data access-control boundary.

## 5. Designing stable reason codes, avoiding free-form strings

Use short, governed, versioned enums/code sets:

~~~text
ALLOW_OWNER
ALLOW_ACTIVE_SHARE
ALLOW_TENANT_ADMIN

DENY_UNAUTHENTICATED
DENY_TENANT_MEMBERSHIP
DENY_ACTION_NOT_ALLOWED
DENY_RESOURCE_NOT_VISIBLE
DENY_OBJECT_PERMISSION
DENY_RESOURCE_RESTRICTED
DENY_POLICY_CONSTRAINT
DENY_EXPLICIT_RULE

ERROR_POLICY_UNAVAILABLE
ERROR_POLICY_INPUT_INVALID
ERROR_POLICY_VERSION_UNSUPPORTED
ERROR_EVALUATION_FAILED
~~~

The list above is an **illustrative application design**, not a built-in Spring Security enum. Separate `ERROR` from `DENY` to distinguish missing permissions from operational faults, while ensuring neither lets sensitive actions proceed.

A good code should:
- Have stable semantics with no dynamic data.
- Describe **the cause category**, not a specific subject or resource.
- Include the policy/rule revision so it remains interpretable over time.
- Be sufficient for authorized investigations without exposing raw ACLs.
- Have a security-reviewed mapping table to public codes.
- Never embed exception messages, SQL fragments, or document titles into the code itself.
- Have a documented precedence contract when multiple rules deny.

**Never name a code `DENY_OWNER_alice@example.com` or `TENANT_acquisition_2026_LOCKED`.** The code name itself leaks data.

## 6. When multiple rules deny simultaneously, which reason is recorded?

A PDP may encounter several failures at once:
- Actor lacks tenant membership.
- Actor lacks `DOCUMENT_WRITE` role.
- Document is locked.
- WRITE share was revoked.

Three approaches:
1. **First-failure:** record the reason of the first mandatory condition that failed, in defined policy order.
2. **Primary + secondary:** record one primary code and a **controlled** set of secondary codes for internal audits.
3. **Bounded decision trace:** record rule IDs and outcomes if investigations require them, with separate access control and retention.

Do not force the PDP to **fetch additional sensitive data** solely to explain a denial to an unauthorized caller. For instance, once tenant membership fails, return `DENY_TENANT_MEMBERSHIP` and **do not** look up the owner's name or that document's grant list.

Check ordering also prevents leaks: authentication → tenant membership → role/action → resource tenant → ACL/object → business state. If the caller may not know the resource exists, stop early rather than recording a trace like "SECRET document owned by CEO".

Reordering policies can change reason codes even while the effect stays DENY. Attach the policy version and test rather than treating reason codes as immutable identifiers for business events.

## 7. Minimal audit schema: sufficient for investigations without payloads

A record can be designed as:

~~~json
{
  "eventSchemaVersion": 1,
  "eventType": "AUTHORIZATION_DECISION",
  "eventId": "evt-2026-7f13",
  "requestId": "req-7814",
  "decisionId": "dec-a9f2",
  "occurredAt": "2026-11-05T05:30:00Z",
  "outcome": "DENY",
  "reasonCode": "DENY_OBJECT_PERMISSION",
  "policyId": "documents-access",
  "policyVersion": "v17",
  "actorRef": "pseudonymized-actor-42",
  "tenantRef": "tenant-ref-08",
  "resourceType": "Document",
  "resourceRef": "opaque-doc-ref",
  "action": "DOCUMENT_READ",
  "enforcementPoint": "DocumentQueryService.read",
  "decisionSource": "local-pdp",
  "executionOutcome": "BLOCKED"
}
~~~

**This is an illustrative schema, not a default Spring/OPA object.** In production:
- `occurredAt` comes from the server clock with explicit timezone.
- `eventId`/`decisionId` must never be treated as credentials.
- `actorRef` may require pseudonymization if user IDs are PII.
- `tenantRef` and `resourceRef` can also be sensitive; granularity depends on audit store access controls.
- `resourceType`, `action`, and `policyVersion` are generally helpful for analytics and debugging.
- `executionOutcome` separates **the decision** from **whether execution/commit succeeded**.
- Add `durationMs`, `serviceName`, `traceId`, or ACL revision when needed, without dumping every field "just in case".

**Never store by default** full `Authentication`, `SecurityContext`, `HttpServletRequest`, entire `Document` entities, request/response bodies, access tokens, or full policy inputs. Those objects can carry secrets and PII; logging them creates a hard-to-govern data copy.

## 8. Structured JSON logging and value normalization

Prefer fixed fields over string concatenation:

~~~json
{
  "event": "authz.decision",
  "outcome": "DENY",
  "reason": "DENY_ACTION_NOT_ALLOWED",
  "policyVersion": "v17",
  "action": "DOCUMENT_WRITE",
  "resourceType": "Document",
  "requestId": "req-7814"
}
~~~

This is far easier to query, alert on, and aggregate than strings like "Alice lacks permission because...". Guidelines:
- An **allowlist** of fields with fixed data types.
- Enums for outcome/reason/action; validate PDP data before logging.
- Length caps and newline/Unicode control filtering for request-derived fields.
- Logger/encoder escapes newlines, tabs, quotes, and delimiters; never concatenate raw user data into log lines.
- Avoid duplicate keys/schema drift that mislead SIEM pipelines.
- Never let clients set `eventType`, `reasonCode`, or `policyVersion`.
- Separate PDP reasons from network exceptions; never attach arbitrary `error.getMessage()`.

When dynamic metadata is required, enforce per-field allowlists and classification. Untrusted inputs such as URL paths, user agents, or header request IDs must be **bounded and sanitized**; never assume a JSON logger automatically controls volume or trustworthiness.

## 9. Redact, mask, pseudonymize: not all the same operation

| Technique | Approach | When appropriate? | Limitations |
|---|---|---|---|
| **Omit/allowlist** | Never emit sensitive fields | Best default | Requires designing schema upfront |
| **Redaction** | Remove the field entirely | Tokens, passwords, secret contents | Loses ability to investigate that field |
| **Mask** | Replace with `[REDACTED]` | Proving a field was scrubbed | Data can still leak via other fields |
| **Pseudonymization** | Reference token reversible via restricted mechanism | Auditing actor/resource without real names | Still counts as personal data requiring protection |
| **Keyed HMAC** | Deterministic alias from ID using secret key | Correlating audits per actor without raw ID | Must protect/rotate keys, prevent replay/mapping leaks |
| **Encryption at rest** | Encrypt stored logs | Audit stores holding legitimate sensitive fields | Does not replace access control/retention |
| **Plain hash** | SHA-256 of raw email/user ID | Usually **insufficient** to hide guessable IDs | Vulnerable to dictionary/brute-force on small ID spaces |

**Hashing does not equal anonymization.** Emails, tenant codes, and user IDs often have predictable value spaces; their SHA-256 hashes can be reversed by guessing. If a stable alias is needed, consider HMAC with keys stored in KMS/Vault and key rotation/versioning—remembering that HMAC still links an actor's actions over time, so access restrictions remain mandatory.

Never mask by **replacing only the last 4 characters** of a long token/ID and call it safe. Combining fields like IP, timestamp, tenant, and action can still re-identify individuals.

**The best protection is neither generating nor transmitting unnecessary fields**, rather than logging everything and hoping a downstream pipeline strips it.

## 10. Data typically excluded from audits and logs

Per the OWASP Logging Cheat Sheet, pay special attention to data such as:
- Passwords, OTPs, recovery codes, API keys, session tokens, OAuth access/refresh tokens.
- Cookies, session identifiers, or signed presigned URLs.
- Private keys, secrets, database credentials, and connection strings.
- Financial data, payment cards, account numbers, health information.
- Personal profiles or sensitive identifiers; addresses/emails lacking legitimate need.
- Internal-only file paths, internal service hostnames, schemas/SQL queries revealing structure.
- Document contents, SECRET folder names, owners, ACL/SID lists.
- Data classified higher than the logging system is authorized to hold.

This does **not** mean every actor ID must be stripped: forensic audits often need a controlled identifier. Decisions must follow **purpose, classification, legality, and access control**; log retention and access must match organizational obligations.

A DENY decision on a sensitive document **never justifies** copying the document into logs just to "make debugging easier".

## 11. What can be explained without raw data?

An investigative record can be sufficient with:
- Policy ID/version and reason code.
- Action/resource type, opaque resource reference.
- Protected subject/tenant references.
- Decision timestamp, request/trace/decision ID.
- PEP name and enforcement outcome.
- Membership/ACL revision when relevant.
- Trust/freshness indicator of evaluated data.
- Error category **if** evaluation failed to complete.

Example:

~~~text
decisionId=dec-a9f2
outcome=DENY
reason=DENY_ACTION_NOT_ALLOWED
policy=documents-access@v17
action=DOCUMENT_DELETE
resourceType=Document
pep=DocumentCommandService.delete
execution=BLOCKED
~~~

Authorized support staff can conclude "policy v17 denied action DELETE" without reading the owner's name, document contents, or other users' roles.

If deeper investigation is needed, use an **authenticated, audited lookup service** to resolve opaque references when authorized. Never dump raw attributes into general logs merely to skip controlled lookups.

## 12. Spring Security: Authorization Events aid observability without replacing business audits

Spring Security provides `AuthorizationEventPublisher` and `SpringAuthorizationEventPublisher` to publish authorization events, including `AuthorizationDeniedEvent`. Per Spring Security documentation, `AuthorizationGrantedEvent` is **not published by default** because volume can be high; enable selectively if needed.

Example configuration:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationEventPublisher;
import org.springframework.security.authorization.SpringAuthorizationEventPublisher;

@Configuration
class AuthorizationEventsConfiguration {

    @Bean
    AuthorizationEventPublisher authorizationEventPublisher(
            ApplicationEventPublisher applicationEventPublisher) {
        return new SpringAuthorizationEventPublisher(
                applicationEventPublisher);
    }
}
~~~

This is a **Spring Security integration snippet**, not a standalone Java 17 program. Configure security appropriately in your project and check APIs for your exact version.

Listening to events:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;

@Component
class AuthorizationDeniedObserver {

    @EventListener
    public void onDenied(AuthorizationDeniedEvent<?> event) {
        // Emit DENY signal to designed metrics/telemetry.
        // DO NOT logger.info("{}", event.getObject());
        // DO NOT logger.info("{}", event.getAuthentication().get());
        // If auditing is needed, map to an allowlisted schema and reason
        // returned by the domain policy over a controlled channel.
    }
}
~~~

**Two crucial points:**
1. The event signals that an authorization check was denied, yet **does not automatically carry domain reason codes from custom PDPs**. If you need `DENY_OWNER_SCOPE` or a policy revision, design a dedicated domain metadata/decision record channel rather than assuming Spring events know the rule cause.
2. `getObject()` can be a secured object, method invocation, or request/context; `getAuthentication()` can hold principals/authorities/credentials. **Never log whole objects** via `toString()`. Extract only allowlisted fields or emit a coarse event.

Enabling granted events on every request creates noise, consumes resources, and bloats audit storage. Be selective by business risk—such as admin grants, sensitive exports, or break-glass actions—and verify API versions because event-publishing predicates can vary across versions.

## 13. Authentication events differ from authorization events

Distinguish:
- **Authentication success/failure:** login, token/credential validation; events like `AuthenticationSuccessEvent`, `AuthenticationFailureEvent` under matching configuration.
- **Authorization allow/deny:** whether an actor was allowed to perform an action on a resource.
- **Business execution:** the PEP allowed it, yet did the transaction succeed, write the file, commit, or roll back?

An HTTP 403 can result from method policies, missing CSRF on protected routes, or other constraints; never label every 403 as `DENY_OBJECT_PERMISSION` without a clear decision source.

**Never use passwords, tokens, or authentication exception messages as authorization audit reasons.** Authentication and authorization serve distinct tracing goals. Correlate them via request/trace IDs and safe subject aliases, keeping log read permissions separate as needed.

## 14. PDP and PEP need two outcomes, not just one log

Separate:
- **PDP Decision record:** "given verified inputs, policy v17 returned DENY due to `DENY_ACTION_NOT_ALLOWED`".
- **PEP Enforcement record:** "service blocked execution, never called `repository.update`".
- **Business outcome:** "transaction committed" or "rolled back" when the decision was ALLOW.

Example:

~~~json
{
  "decisionId": "dec-123",
  "policyVersion": "v17",
  "effect": "ALLOW",
  "reasonCode": "ALLOW_OWNER"
}
~~~

and:

~~~json
{
  "decisionId": "dec-123",
  "pep": "DocumentCommandService.rename",
  "action": "DOCUMENT_WRITE",
  "executionOutcome": "ROLLED_BACK",
  "errorCategory": "OPTIMISTIC_CONFLICT"
}
~~~

A PDP returning ALLOW **does not prove the mutation committed**. The PEP may block due to obligations, DB version conflicts, transaction rollbacks, or storage failures. Incident analysis requires both decision and enforcement records.

Never log old/new document titles merely because an update failed. Use stable action/resource references and error categories.

## 15. API explanations: one-way error mapping without exposing object existence

A mapping table:

| Internal outcome | Suggested public HTTP/code | What to avoid |
|---|---|---|
| Unauthenticated | 401 / `AUTHENTICATION_REQUIRED` | Revealing which users exist |
| Insufficient functional role, known action | 403 / `ACTION_NOT_AVAILABLE` | Listing others' roles |
| Resource not found **within permitted scope** | 404 / `RESOURCE_NOT_AVAILABLE` | Confirming resource exists in another tenant |
| Object ACL DENY on unviewable resource | 404 / `RESOURCE_NOT_AVAILABLE` | Naming owner/classification |
| Resource locked, caller allowed to see it | Possibly 409 / `RESOURCE_NOT_EDITABLE` | Returning detailed status to callers forbidden to view resource |
| PDP timeout / error | 503 / `AUTHORIZATION_UNAVAILABLE` | Falling back to ALLOW; returning stack traces |
| Rule not applicable / abstain | Deny per combining policy | Treating `null` as ALLOW |

This is a **suggested API design**, not Spring Security's default mapping. In some domains, 403 for resource ACL DENY is fine once the caller is already authorized to know the resource exists. Threat-model it: the primary goal is **not confirming the existence or attributes of out-of-scope resources**.

A Problem Details response:

~~~json
{
  "type": "https://api.example/problems/resource-not-available",
  "title": "Resource not available",
  "status": 404,
  "code": "RESOURCE_NOT_AVAILABLE",
  "requestId": "req-7814"
}
~~~

With Spring Framework `ProblemDetail`, non-standard fields like `code` and `requestId` are configured as application extensions. Never include `reasonCode=DENY_TENANT_MISMATCH` or real tenant names in responses when doing so reveals the object exists in another tenant.

## 16. Not only content: HTTP status, timing, and payload size can also leak

Even with identical messages, a caller can probe IDs and measure:
- 404 returning in 5ms for nonexistent IDs vs. 403 in 150ms for ACL-protected IDs.
- JSON errors varying in field count or length by reason.
- Rate limits or cache-hit patterns differing when a resource exists.
- Detail endpoints issuing different redirects/challenges for cross-tenant objects.

Constant-time authorization is not always required; that depends on resource sensitivity and enumeration scenarios. For confidential objects, however:
- Return the same public response class for "does not exist" and "out of scope".
- Never load/serialize out-of-scope resources.
- Avoid intentional timing branches dependent on owner/ACL graphs where avoidable.
- Rate-limit by identity/IP/service context under an appropriate policy.
- Test enumeration using both existing and nonexistent IDs, checking status/body/headers and latency distributions.
- Never put secrets in `Location`, `WWW-Authenticate` details, or custom error headers.

**Masking text while leaving status codes different can still leak.** Conversely, never claim timing reveals nothing without measuring it.

## 17. Decision IDs and request IDs: enabling support without exposing raw reasons

Communication pattern:

~~~text
User:
  "Unable to open document."
UI:
  "Resource is unavailable within your access scope."
  "Request ID: req-7814"
Authorized support:
  looks up req-7814 -> dec-a9f2 ->
  effect=DENY, reason=DENY_ACTION_NOT_ALLOWED,
  policy=documents-access@v17
~~~

Request IDs should:
- Be generated unpredictably or at minimum contain no PII/secrets.
- Carry no access capability; used only for policy-governed lookup.
- Prevent users from guessing another request's ID to read its audit.
- Avoid reuse across distinct requests or trust boundaries.
- Have suitable retention and indexing for support workflows.
- Correlate across HTTP, services, PDPs, and background workers when needed.

**A correlation ID is not a capability token to view logs.** Support tools must always verify agent/tenant/ticket entitlement before querying. Never build an endpoint where "knowing requestId lets you view the entire decision JSON".

## 18. Pseudonymizing actors/resources for log correlation

Storing raw emails, `userId`s, and `documentId`s in logs is rarely necessary. When analyzing DENY frequencies for the same actor, use a stable actor reference.

Approaches:
1. **Internal opaque ID:** map user account → random ID, keeping the mapping table separately secured.
2. **Keyed HMAC:** derive token from server secret, tenant namespace, and canonical identifier.
3. **One-time alias:** random per request; great for privacy, though cannot group an actor long-term.
4. **Encrypted identifier:** encrypted with managed keys when authorized investigations require decryption.

With HMAC, ensure:
- Strong keys stored in KMS/secrets manager, never in source code/logs.
- Canonical byte representation with issuer/tenant namespacing to avoid collisions/conflating users.
- Key versioning to support rotation and alias updates.
- Controls over cross-time tracking and who may query.
- Never use plain hashes on guessable data like emails or account numbers.
- Never claim pseudonymized data is "non-personal data" under every regulation.

Raw identifiers may be retained in a tightly controlled audit store if justified and needed for investigations; the key is **access restriction and retention**, not forcing one pseudonymization method on every system.

## 19. OPA decision logs: never enable them and ship raw inputs

Open Policy Agent can emit **decision logs** containing policy queries, inputs, results, bundle metadata, and decision IDs. If the PEP sends principal emails, JWT-derived claims, resource owners, or classifications in `input`, default decision logs will capture those attributes.

OPA provides masking policies at `data.system.log.mask` to remove or replace fields in events **before logs are shipped**. Illustrative Rego example:

~~~rego
package system.log

mask contains "/input/accessToken"

mask contains "/input/resource/confidentialTitle"

mask contains {
    "op": "upsert",
    "path": "/input/subject/email",
    "value": "[REDACTED]"
}
~~~

This syntax is **Rego v1-style** and must be tested against your OPA version and real decision event structure. OPA masking JSON Pointers have specific supported path constraints; check official docs before production rollout.

Operational rules:
- **Avoid sending tokens in PDP inputs whenever possible**; PDPs need minimal verified subjects/attributes.
- When policy-specific attributes are required, apply input/trace masking per data classification.
- Mask both `input` **and** `result` if results carry sensitive explanations/obligations.
- Test masking against nested arrays, optional fields, renamed fields, and new policy versions.
- Do not protect only remote uploads: if console logging or custom plugins are enabled, verify every sink.
- Enforce access control, retention, TLS, and log routing on OPA collectors.
- Never treat `decision_id` automatically as a secret or token; it is primarily for correlation, yet audit lookups still need access control.

OPA supports remove/upsert operations in masking policies and records erased/masked paths. **Never assume enabling decision logging automatically masks sensitive inputs.** Configure masking to match your exact schema.

References: [OPA Decision Logs](https://www.openpolicyagent.org/docs/management-decision-logs) and [OPA Configuration](https://www.openpolicyagent.org/docs/configuration).

## 20. Controlling Spring Security debug logging

DEBUG/TRACE levels in Spring Security help diagnose filter chains, method invocations, and rule matching, yet **must not be left broadly enabled in production** just to see why requests are DENIED.

Risks include:
- Request paths/queries containing sensitive data.
- Principals/authorities or exception details logged by libraries/apps.
- Heavy log volume overwhelming storage and exposing policy structure.
- Debug left enabled after an incident, causing prolonged data collection.

Good practices:
1. Default to minimal structured decision logs and metrics.
2. Enable DEBUG selectively by service/category for an approved time window.
3. Inspect actual log output in test/staging before enabling in production.
4. Redact headers like `Authorization`, `Cookie`, `Set-Cookie`, and URLs with signed tokens.
5. Maintain a runbook to auto-disable debug, restrict access, and audit who enabled it.
6. Never use `Authentication.toString()` or `HttpServletRequest.toString()` as user explanations.
7. Never log full JPA entities, ACL/`GrantedAuthority` lists, or unnecessary exception objects.

**Spring Authorization Events do not replace an audit system with reason codes.** When business reasons are needed, design the PDP/PEP decision model and metadata upfront.

## 21. Relationship to PEP–PDP and dynamic policies

For dynamic policies:
- **PDP** knows which rules produced ALLOW/DENY, the policy revision, and data sources.
- **PEP** knows which endpoint/service enforced the decision, whether side effects ran, and what can be disclosed.
- **PIP** knows attribute provenance (owner, membership, ACL, state), yet must not dump whole objects into logs.
- **PAP** knows who edited, approved, published, and rolled back policies.

You can separate:
~~~text
PDP:
  EvaluationResult(effect, internalReasonCode, ruleVersion, decisionId)

PEP:
  check effect == ALLOW
  enforce obligations and resource/action binding
  publish safe enforcement event
  map public explanation from internal result

Audit sink:
  store allowed schema, with retention/access control
~~~

Never scatter public reason mapping across individual controllers. A shared **`ExplanationMapper`** keyed by resource class and caller disclosure level prevents endpoints from leaking varying amounts of information.

Nor should all user-facing messaging be pushed into the PDP: the PDP decides under policy; the PEP/API gateway knows **who receives the message and their clearance to view explanations**. A remote PDP may return a detailed reason to a calling service without implying HTTP callers may see that reason.

## 22. Where to place audit checkpoints to capture both cause and outcome?

Three valuable points:
1. **After policy evaluation:** event contains effect/reason/version, before execution outcome.
2. **After enforcement gate:** event records whether the request was blocked or allowed to proceed.
3. **After transaction/side effect:** event records commit/rollback, download/export/queue status.

Link them via `decisionId`/`traceId`, without necessarily emitting every event on every request at extreme throughput. Choose granularity by risk, business need, applicable law, and performance—for example, logging full DENYs on sensitive operations, sampling routine ALLOWs, while always auditing grants/revocations or break-glass actions per policy.

When writing events via transactions/outboxes, note:
- Policy DENY audits may occur **outside any business transaction** since no transaction started.
- An ALLOW audit followed by transaction rollback must reflect `ROLLED_BACK`—never use ALLOW as proof that a DB change succeeded.
- If auditing is mandatory under policy, audit sink outages may block the operation or rely on a durable local outbox per contract.
- Writing raw logs synchronously on the request thread adds latency; async logging risks data loss, requiring a reliability model.
- Queue consumers must protect audit data and deduplicate across retries/idempotency.

Never write "effect=ALLOW, status=SUCCESS" the moment the PDP returns ALLOW before the repository has even run.

## 23. Transactions, TOCTOU, and reason freshness

A decision:

~~~text
T1: policy v17 -> ALLOW because actor is owner
T2: ownership transfers to someone else
T3: PEP still WRITES using T1's decision
~~~

The audit from T1 **accurately explains the past**, yet does not prove the T3 operation remained valid under current data. To prevent confusion:
- Record decision time and resource/ACL revision when needed.
- For owner-only WRITEs, use guarded SQL binding actor+tenant+owner+status+version at the mutation boundary.
- For grants/ACLs in separate tables, define transactions/isolation and lock/revision protocols.
- Re-check when actions run via queues/batches where policies may change.
- Never use cached ALLOWs beyond published TTL/revocation semantics.
- Record actual execution status and optimistic conflicts separately from the PDP's reason.

If `ALLOW_OWNER` is recorded and the operation is later blocked by a stale version, audits must show **an initial authorization ALLOW whose operation did not commit**. Never rewrite historical logs to match the final state; emit a linked event reflecting the progression.

## 24. Securing the audit store itself

Audit stores are high-value targets because they can map permissions, tenant structure, access patterns, and admin activity.

Minimum design:
- **RBAC/ABAC** on audit reads, scoped by tenant/role/case/ticket.
- Principle of least privilege for collectors and investigators.
- Encryption in transit and at rest, with proper key management.
- Purpose-bound retention/destruction per legal/contractual policy; avoid indefinite retention.
- Tamper resistance/integrity per requirements: append-only, signed records, digest chains, or immutable storage.
- Separate permissions to read, modify retention, delete, or export audits.
- Audit **access to the audit store itself**; alert on bulk or cross-tenant queries.
- Backups, exports, replicas, search indexes, and third-party SIEMs must follow the same classification.
- Correction/masking mechanisms if sensitive data is accidentally logged, covering replicas and backups per policy.

Never treat "audits are internal-only" as sufficient. A support agent may view reasons for a ticket in tenant A while being forbidden to query all policy decisions in tenant B.

### Purpose-bound retention

Different events carry different value:
- Routine DENYs may require shorter retention than admin role grant/revoke events.
- Security incident events may follow dedicated investigative retention rules.
- Aggregated authz metrics can be retained longer than actor-level details.
- Raw debug logs should have short TTLs and be excluded from routine exports.

**Never prescribe fixed retention numbers** without organizational legal policy. Design pipelines to enforce per-category retention and support deletion/legal holds upon valid request.

## 25. Metrics and tracing: never turn identifiers into labels

A good metric:

~~~text
authorization_decisions_total{
  service="documents",
  action="READ",
  effect="DENY",
  reason="DENY_OBJECT_PERMISSION"
} 1284
~~~

A metric to avoid:

~~~text
authorization_decisions_total{
  email="alice@company.example",
  documentId="123456789",
  accessToken="eyJ..."
} 1
~~~

Adding user IDs/resource IDs to metric labels creates **high cardinality**, high cost, and data leaks into dashboards. Use bounded-cardinality enums/rule groups/services/actions/effects. Detailed per-actor/resource analysis belongs inside access-controlled audit stores.

With OpenTelemetry tracing:
- Never place raw `Authorization` headers into span attributes.
- Include only `decisionId`/policy version or categorized outcome/reason codes.
- Ensure baggage is never used to carry secrets or propagate into untrusted services.
- On errors, status descriptions and exception events must omit secret payloads.
- Account for trace sampling when compliance demands zero lost audit events; **trace sampling does not replace audit guarantees**.

## 26. Standalone Java 17: storing internal reasons, explaining externally safely

This demo uses plain Java 17. It includes a small PDP returning effect/reason, a PEP allowing execution only when effect is ALLOW, an audit formatter **allowlisting** permitted fields, and a public explanation mapper omitting owner/tenant from denial messages.

**This is a mechanism example**, with no Spring, database, real logger, or identity verification. In production, actor/resource objects must come from trusted authentication/PIPs; the example uses hardcoded fixtures to demonstrate the logic.

Create `SafeDecisionAuditDemo.java`:

~~~java
import java.util.Set;

public class SafeDecisionAuditDemo {
    enum Action { READ, WRITE }
    enum Effect { ALLOW, DENY, ERROR }

    enum Reason {
        OWNER_MATCH,
        ROLE_INSUFFICIENT,
        RESOURCE_NOT_VISIBLE,
        RESOURCE_RESTRICTED,
        PDP_UNAVAILABLE
    }

    record Actor(String id, String tenant, Set<Action> actions) { }
    record Resource(long id, String tenant, String owner, boolean locked) { }
    record Input(Actor actor, Resource resource, Action action) { }
    record Decision(Effect effect, Reason reason, String policyVersion) { }

    @FunctionalInterface
    interface Pdp {
        Decision decide(Input input);
    }

    static final class LocalPdp implements Pdp {
        @Override
        public Decision decide(Input input) {
            if (input == null || input.actor() == null
                    || input.resource() == null || input.action() == null) {
                return new Decision(
                        Effect.DENY, Reason.RESOURCE_NOT_VISIBLE, "docs-v3");
            }

            Actor actor = input.actor();
            Resource resource = input.resource();

            if (actor.tenant() == null
                    || resource.tenant() == null
                    || !actor.tenant().equals(resource.tenant())) {
                return new Decision(
                        Effect.DENY, Reason.RESOURCE_NOT_VISIBLE, "docs-v3");
            }
            if (actor.actions() == null
                    || !actor.actions().contains(input.action())) {
                return new Decision(
                        Effect.DENY, Reason.ROLE_INSUFFICIENT, "docs-v3");
            }
            if (resource.locked() && input.action() == Action.WRITE) {
                return new Decision(
                        Effect.DENY, Reason.RESOURCE_RESTRICTED, "docs-v3");
            }
            if (actor.id() != null && actor.id().equals(resource.owner())) {
                return new Decision(
                        Effect.ALLOW, Reason.OWNER_MATCH, "docs-v3");
            }
            return new Decision(
                    Effect.DENY, Reason.RESOURCE_NOT_VISIBLE, "docs-v3");
        }
    }

    static final class Pep {
        private final Pdp policy;
        private int executed;

        Pep(Pdp policy) {
            this.policy = policy;
        }

        String attempt(Input input) {
            Decision decision;
            try {
                decision = policy.decide(input);
                if (decision == null
                        || decision.effect() == null
                        || decision.reason() == null
                        || decision.policyVersion() == null) {
                    decision = new Decision(
                            Effect.ERROR, Reason.PDP_UNAVAILABLE, "unknown");
                }
            } catch (RuntimeException failure) {
                decision = new Decision(
                        Effect.ERROR, Reason.PDP_UNAVAILABLE, "unknown");
            }

            // Audit uses only allowlisted enums and fixed metadata.
            String audit = "audit outcome=" + decision.effect()
                    + " reason=" + decision.reason()
                    + " policy=" + decision.policyVersion();
            System.out.println(audit);

            String publicResponse;
            if (decision.effect() == Effect.ALLOW) {
                executed++;
                publicResponse = "public status=200 code=OK";
            } else if (decision.effect() == Effect.ERROR) {
                publicResponse =
                        "public status=503 code=AUTHORIZATION_UNAVAILABLE";
            } else {
                // Every DENY returns a generic message in the demo.
                publicResponse =
                        "public status=404 code=RESOURCE_NOT_AVAILABLE";
            }
            System.out.println(publicResponse);
            return audit + "|" + publicResponse;
        }

        int executed() {
            return executed;
        }
    }

    public static void main(String[] args) {
        Actor owner = new Actor("an", "north",
                Set.of(Action.READ, Action.WRITE));
        Actor reader = new Actor("binh", "north",
                Set.of(Action.READ));
        Resource doc = new Resource(42, "north", "an", false);
        Resource otherTenant =
                new Resource(42, "south", "alice@example.com", false);
        Resource locked = new Resource(43, "north", "an", true);

        Pep pep = new Pep(new LocalPdp());
        pep.attempt(new Input(owner, doc, Action.READ));
        pep.attempt(new Input(reader, doc, Action.WRITE));
        pep.attempt(new Input(owner, otherTenant, Action.READ));
        pep.attempt(new Input(owner, locked, Action.WRITE));

        Pep errorPep = new Pep(input -> {
            throw new IllegalStateException(
                    "Sensitive backend detail must not be returned");
        });
        String result = errorPep.attempt(
                new Input(owner, doc, Action.READ));

        System.out.println("no-secret-exposed="
                + !result.contains("Sensitive backend detail"));
        System.out.println("executed-count=" + pep.executed());
    }
}
~~~

Run:

~~~bash
javac SafeDecisionAuditDemo.java
java SafeDecisionAuditDemo
~~~

Exact stdout:

~~~text
audit outcome=ALLOW reason=OWNER_MATCH policy=docs-v3
public status=200 code=OK
audit outcome=DENY reason=ROLE_INSUFFICIENT policy=docs-v3
public status=404 code=RESOURCE_NOT_AVAILABLE
audit outcome=DENY reason=RESOURCE_NOT_VISIBLE policy=docs-v3
public status=404 code=RESOURCE_NOT_AVAILABLE
audit outcome=DENY reason=RESOURCE_RESTRICTED policy=docs-v3
public status=404 code=RESOURCE_NOT_AVAILABLE
audit outcome=ERROR reason=PDP_UNAVAILABLE policy=unknown
public status=503 code=AUTHORIZATION_UNAVAILABLE
no-secret-exposed=true
executed-count=1
~~~

Analysis:
- For the document owner and valid READ action, the PEP executes once.
- Missing role/action, wrong tenant, and locked document each yield **distinct internal reasons**.
- All three DENYs present **the same public code** so policies or document existence are not disclosed in the demo.
- PDP errors map to ERROR, skipping execution and withholding the exception message externally.
- Final `executed` equals 1, confirming DENY/ERROR requests caused zero illustrative side effects.

**Limitations and production adjustments:**
- In the demo, `Actor` is built in code rather than through Spring Authentication; never treat client-declared values as trusted actors.
- The demo's audit formatter prints to console for visibility. Production needs structured loggers, correlation IDs, protected sinks, and retention.
- `Decision.policyVersion` is an internal string; if received from a remote PDP, **validate/allowlist/cap** it before logging. Never trust arbitrary strings returned by a remote service.
- A `null` decision or malformed response must never turn into ALLOW.
- Returning HTTP 404 for every DENY in the demo is an anti-enumeration choice, not mandatory for every API; once a caller is authorized to see a resource, specific codes/messages may be chosen per policy.
- An ALLOW decision alone is not enough to write to the DB if owner/ACLs change after the check; transactions/guards remain necessary.

## 27. Spring example: safe permission explanation mapper

You can define an API-layer mapper:

~~~java
public record PublicAuthorizationError(
        String code, String message, String requestId) { }

public final class AuthorizationExplanationMapper {

    private AuthorizationExplanationMapper() { }

    public static PublicAuthorizationError denied(
            String requestId) {
        return new PublicAuthorizationError(
                "RESOURCE_NOT_AVAILABLE",
                "Resource is unavailable within your access scope.",
                requestId);
    }

    public static PublicAuthorizationError unavailable(
            String requestId) {
        return new PublicAuthorizationError(
                "AUTHORIZATION_UNAVAILABLE",
                "Unable to verify permissions at this time.",
                requestId);
    }
}
~~~

This is a **Java class snippet**, not a complete controller/exception handler. Request IDs must come from a controlled, validated correlation context rather than unbounded client strings.

A `@RestControllerAdvice` or Spring Security `AccessDeniedHandler` can invoke the mapper depending on where exceptions originate. Note:
- Exceptions from service-layer method security can be handled differently from servlet filter exceptions.
- `ExceptionTranslationFilter` is not a catch-all for every JPA/PDP error.
- An `AccessDeniedException` does not carry business reasons by itself; reasons should come from the decision domain or event correlation.
- Never expose raw exception messages as public explanations.
- On JSON endpoints, standardize error codes, content types, and response sizes to prevent leaks from needless variations.

## 28. Audit reasons when the PDP decides across multiple sources

If the PDP consults roles, ACLs, tenant memberships, project policies, and resource status, causes may include:
- Invalid input.
- Missing or inactive membership.
- Mismatched role/action.
- Resource not in target tenant.
- Grant revoked/expired.
- Document locked/legal hold.
- Time or classification rule failed.
- PIP/DB timeout, insufficient data to evaluate.

A sound outcome table:

| Situation | Effect | Internal reason | Public response for unauthorized caller |
|---|---|---|---|
| Missing tenant membership | DENY | `DENY_TENANT_MEMBERSHIP` | Generic, does not confirm tenant |
| Wrong action role | DENY | `DENY_ACTION_NOT_ALLOWED` | Action unavailable or generic |
| Document in another tenant | DENY | `DENY_RESOURCE_NOT_VISIBLE` | Generic 404 |
| READ share revoked | DENY | `DENY_OBJECT_PERMISSION` | Generic 404 |
| Resource LOCKED | DENY | `DENY_RESOURCE_RESTRICTED` | Generic; details only for authorized viewers |
| Classification rule | DENY | `DENY_POLICY_CONSTRAINT` | Generic |
| PIP unavailable | ERROR | `ERROR_PIP_UNAVAILABLE` | Generic 503 |
| Input missing trusted fields | ERROR or DENY per contract | `ERROR_POLICY_INPUT_INVALID` | Never leaks internal fields |
| ALLOW via owner | ALLOW | `ALLOW_OWNER` | No broad explanation needed |
| ALLOW via share | ALLOW | `ALLOW_ACTIVE_SHARE` | Show caller only their own grant if appropriate |

Avoid splitting reasons too finely if the reason code itself lets callers infer unauthorized resources. Reason codes are shared only with audiences authorized at that tier.

## 29. Audit integrity and interpretability over time

Dynamic policies evolve continuously. A v17 event can differ from v18 even with identical action/actor/resource. Audits must capture enough to reconstruct **the permitted context** and understand historical versions.

Helpful metadata:
- Policy ID + immutable revision/hash.
- PEP and PDP deployment/build versions.
- Verified resource/ACL/membership versions or timestamps when relevant.
- Decision timestamp, enforcement timestamp, commit status.
- Data source identifier (never secret DSNs).
- Reason code schema version.
- OPA policy bundle revision if used.
- PIP consistency level or cache freshness when decisions depend on dynamic data.

**Never promise that having `policyVersion` lets you replay the exact decision** unless matching input/data snapshots were kept or PIP data stayed unchanged. Storing full snapshots for replay can leak PII and exceed needs; consider testing policies in dedicated environments with synthetic fixtures and minimized traces.

Audit records must resist unauthorized modification per business requirements. Logging systems can use immutable storage, append-only stores, audit writer separation, and integrity hashes—yet permissions and keys must still be secured. Never assume a plain text log file is strong "legal evidence" merely because it has timestamps.

## 30. Testing: right decisions and zero data leaks

Mandatory matrix:

| Case | Internal audit | Public output / enforcement |
|---|---|---|
| ALLOW owner | `ALLOW_OWNER` reason | Action executes properly; no excess metadata leaked |
| DENY role/action | `DENY_ACTION_NOT_ALLOWED` reason | Never executes; safe message |
| DENY cross-tenant | `DENY_RESOURCE_NOT_VISIBLE` reason | Never confirms resource existence |
| DENY ACL READ | Object permission reason | Never reveals owner name/SID list |
| DENY SECRET/LOCKED document | Restricted reason | Never sends classification to unauthorized callers |
| Nonexistent resource ID | Not visible/not found reason per policy | Matches out-of-scope resource response when required |
| PDP timeout | ERROR category | Never executes; 5xx/503, no stack trace |
| Missing/null result | ERROR/abstain per contract | Never defaults to ALLOW |
| Exception containing secret | Raw message not logged | Secret absent from responses, logs, traces |
| Log injection | Fields with newlines/Unicode controls | Event never creates forged log lines |
| `AuthorizationDeniedEvent` | Event emitted when configured | Listener never logs full auth/object |
| Granted events | Intentional sampling/config | Does not grow unboundedly |
| OPA input has nested PII | Mask/remove verified | Remote/console logs free of PII |
| Mask policy missing path | Test fails | Blocks unsafe rollout |
| Tenant A views tenant B audits | Blocked | Cannot see other tenant's reasons/details |
| Multi-row audit export | Proper scope and rate limits | Never leaks out-of-scope tokens/ACLs |
| Policy v17 vs v18 | Version recorded | Public mapping remains stable/accurate |
| Audit sink outage | Telemetry/fallback per contract | Does not violate mandatory audit obligations |
| ACL revoke and stale cache | Revision/decision trace present | Never reuses ALLOW past SLA |
| Retrying same request | Clear correlation/idempotency | Never duplicates side effects |
| Read/list/export/download | Audited per risk | Never leaks data via side channels |

### Anti-enumeration testing

Prepare at least three ID classes:
1. Nonexistent ID.
2. Existing ID belonging to another tenant.
3. Existing ID within the tenant without actor ACL.

For callers unauthorized to know those three objects exist, assert that response codes, bodies, headers, redirects, and error messages **reveal zero unauthorized differences**. Measure timing distributions if required by the threat model. Never run unauthorized probing scripts against production; execute in a controlled test environment.

### Logging/redaction testing

Capture output from test loggers:
- Absent of `Authorization: Bearer`, cookies/sessions, fake emails, secret titles, or raw bodies.
- Events carry valid reason enums, policy revisions, and request IDs.
- Values containing `\n`, `\r`, quotes, or Unicode controls are properly encoded/bounded.
- When exceptions are thrown, `Throwable.toString()` is not serialized into general audits.
- Verified across **console logs, remote collectors, traces, and decision logs**, not just app logs.

## 31. Review workflow for changing a reason code or explanation

When updating policies or adding reasons:
1. Identify **who may read** the new reason (public, tenant admin, security ops).
2. Check whether the reason could leak resource existence, owner, tenant, groups, or anti-fraud rules.
3. Add codes to enums/contracts rather than arbitrary dynamic strings.
4. Define precedence when multiple rules deny simultaneously.
5. Update public mappings; test 403/404 and ERROR handling.
6. Add only genuinely needed audit fields with classification and retention.
7. Verify OPA masking/schemas/log collectors for the new fields.
8. Update security reviews, unit tests, integration tests, and data-leakage tests.
9. Deploy by policy version, monitoring DENY rates and log volumes.
10. When rollbacks occur, older audits remain interpretable under older reason schema versions.

A seemingly harmless change from "Access unavailable" to "This document belongs to Finance and has not been shared with you" can dramatically boost data enumeration. Reviewing error copy is just as important as reviewing SQL access predicates.

## 32. Implementation checklist

- [ ] Clear separation between effect, internal reason, public message, and execution outcome.
- [ ] Every public explanation matches the caller's right to know, revealing no unauthorized owner/tenant/ACL.
- [ ] Internal reason codes use enums/allowlists, free of PII, SQL, or exception text.
- [ ] Precedence defined when multiple policies/rules deny at once.
- [ ] Minimal, versioned audit schema with action/resource type/policy revision and correlation.
- [ ] Never log full `Authentication`, `SecurityContext`, request bodies, tokens, entities, or ACL graphs.
- [ ] Redaction/masking tested across **all channels**: application, OPA, console, SIEM, traces, exports.
- [ ] Actor/resource references use pseudonymization or proper access controls, never weak hashes for guessable IDs.
- [ ] Never treat `requestId`/`decisionId` as authorization to read audits.
- [ ] Explanation APIs enforce authentication, authorization, rate limiting, and tenant scoping.
- [ ] Separate 401, 403, 404, and PDP/PIP errors under policies that hide object existence.
- [ ] Spring `AuthorizationDeniedEvent` used safely; granted events enabled selectively if needed.
- [ ] Custom PDP reasons recorded via domain contracts rather than assuming Spring events know rule details.
- [ ] PEP never executes on DENY, ERROR, null, timeout, or malformed responses.
- [ ] ALLOW decisions bind to exact actor–tenant–action–resource with freshness/TOCTOU guards when needed.
- [ ] Decision and enforcement/commit logs are linked without being conflated.
- [ ] Log stores encrypted with tenant/role/case read controls, retention, access auditing, and export controls.
- [ ] Metric labels omit user IDs/document IDs/tokens and avoid high cardinality.
- [ ] Enumeration, log injection, cross-tenant audits, stale revocations/caches, and incident rollbacks tested.
- [ ] Policy versioning, reason-code review, and data-leakage checks run before release.

**Conclusion:** A solid authorization system knows not only **whether to allow or deny**, but also **why** for testing, operations, and investigations. Yet "good explanations" **never mean "maximum disclosure"**. Store internal reason codes and policy revisions inside protected audit stores, link decisions to enforcement outcomes, map to minimal public messages aligned with the caller's right to know, and verify every channel across logs/traces/OPA/exports. Without a valid ALLOW decision, the PEP must fail closed; with ALLOW, still protect the exact resource and state at execution time.

## Official references

- [Spring Security — Authorization Events](https://docs.spring.io/spring-security/reference/servlet/authorization/events.html): configuring `AuthorizationEventPublisher`/`SpringAuthorizationEventPublisher`, denied events, and granted-event publishing policies.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `AuthorizationManager`, authorization results, and interception points.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@PreAuthorize`, custom policy beans, method enforcement, and proxies.
- [Spring Security — Authentication Events](https://docs.spring.io/spring-security/reference/servlet/authentication/events.html): distinguishing authentication success/failure from authorization decisions.
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): exception translation/filter chains and security boundaries.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): data to omit from logs, sanitization, log injection, transport/storage/access/retention protection.
- [OPA — Decision Logs](https://www.openpolicyagent.org/docs/management-decision-logs): `decision_id`, input/result, masking/redaction, and sinks.
- [OPA — Configuration](https://www.openpolicyagent.org/docs/configuration): log reporting, masking/dropping decisions.
- [OWASP API Security Top 10 (2023) — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): ID enumeration and unauthorized resource access risks.
