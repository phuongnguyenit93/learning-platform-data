# Runbook for External System Disconnection in Spring Integration Adapters

> **Chapter:** Production  
> **Topic:** Runbook for external system disconnection  
> **Module scope:** `SPRING_INTEGRATION_ADAPTERS` — operating Spring Integration inbound/outbound adapters, gateways, pollers, and `MessageChannel`; flows across File, SFTP, HTTP, JMS, AMQP, Kafka, and databases. This runbook focuses on detecting disconnections, containing blast radius, preserving messages, recovering safely, and verifying business outcomes.

## 1. Purpose, Scope, and How to Use This Runbook

An external connection outage produces more than error logs. Consequences include **halted data intake, growing backlogs, request/reply timeouts, unconfirmed tokens, redelivered messages, or business side effects executed without the app knowing the outcome**. In production, restoring connectivity while ignoring message state can be more dangerous than the initial outage.

This runbook answers four questions in strict order:

1. **Is there a real incident?** Is it a connectivity, authentication, config, or infra failure—or simply an empty source?
2. **What is the blast radius?** Which flows, tenants, partners, messages, and service commitments are affected?
3. **How do we keep data safe?** Should we stop, throttle, buffer, retry, or isolate a connector to avoid lost, duplicated, or reordered data?
4. **How do we recover and prove it?** Reconnecting **is not enough**; verify intake, processing, commits, acks/offsets, backlogs, and target state.

### 1.1. Target Audience

- **On-call/SRE/Production Support:** detect, triage, contain, recover, track SLOs, and coordinate incidents.
- **Integration Engineer:** inspect Spring Integration flows, endpoint lifecycles, channels, adapters, gateways, pollers, and error paths.
- **System Owner / Partner Owner:** verify external systems (SFTP servers, APIs, brokers, DBs, certificates, quotas) and coordinate controlled changes.
- **Business / Data Owner:** assess impact, approve replays, run compensations, or formally accept data loss per procedure.
- **Security / Compliance:** engage whenever credential leaks, spoofed certificates, unauthorized access, or data-integrity breaches are suspected.

This runbook **forbids** deleting data unilaterally, bypassing TLS/host-key verification, seeking offsets blindly, skipping dead-letter queues, or altering committed transactions. State-mutating actions require proper authorization, evidence, and rollback plans.

### 1.2. Entry Criteria When an Incident Begins

A minimum incident record must capture:

| Field | Example Entry | Why Needed |
|---|---|---|
| Incident ID | `INC-LAB-2026-011` | Links logs, decisions, and communications |
| Detected at | `2026-11-23T15:10:00+07:00` | Anchor for outage duration and SLAs |
| Flow/endpoint | `partner-orders-sftp-inbound` | Pinpoints exact Spring Integration endpoint |
| Source/target | `sftp.partner.example` / `orders-db` | Defines external boundaries |
| Environment | `production` / `region-a` | Prevents acting on the wrong environment |
| First failed operation | list remote files / connect / send / commit | Separates failure layers |
| Last known success | `2026-11-23T15:02:00+07:00` | Establishes impact window |
| Current backlog | 340 files, oldest 8 min | Estimates recovery time |
| Data semantics | at-least-once + business idempotency | Governs replay and ack rules |
| Incident commander | designated on-call role | Owns decisions and coordination |
| Evidence links | dashboards, traces, redacted logs | Diagnostics and audit trail |

**Names and figures above are hypothetical.** During live incidents, fill in real observed facts—never infer them from module names or lesson examples.

### 1.3. Definition of "Successful Recovery"

An incident is recovered only when **all three layers** pass:

1. **Connectivity:** transports/endpoints exchange traffic externally; credentials and TLS/host-key configs are valid.
2. **Technical progress:** messages flow in/out, retries stay controlled, abnormal error loops stop, and lag/backlogs begin draining.
3. **Business correctness:** messages validate and commit accurately; zero lost or out-of-contract duplicate effects; source–target reconciliation and backlog cleanup complete.

Warning: **"connection recovered" does not mean "incident resolved"**. A connector can reconnect yet pull only new data, skip backlogs, or mis-ACK older items.

## 2. Dependency Map and Disconnection Failure Modes

Spring Integration uses **`MessageChannel`** and endpoints to decouple external protocols from business handlers. Failures happen at intake, during channel handoff, at outbound adapters, in storage, or on reply paths.

### 2.1. Overview Map

~~~mermaid
flowchart LR
    EXTS["File/SFTP/HTTP/JMS/AMQP/Kafka/DB source"] --> IA["Inbound Adapter / Gateway"]
    IA --> CH["MessageChannel"]
    CH --> F["Filter / Transformer / Router / Service Activator"]
    F --> OA["Outbound Adapter / Gateway"]
    OA --> EXTT["External API/Broker/DB/File target"]
    IA --> ERR["Error handling / ErrorChannel"]
    F --> ERR
    OA --> ERR
    CH --> BUF["Queue / MessageStore if present"]
    BUF --> F
~~~

A single flow can chain multiple adapters. Always identify **which endpoint lost connectivity and where messages currently sit** before stopping a flow or replaying.

### 2.2. Six Incident Categories to Distinguish

| Failure Category | Common Signals | First Checks |
|---|---|---|
| **DNS/routing/network** | Unknown host, connection refused, reset, unreachable | DNS, routes, firewalls, endpoint/port, regional network |
| **Transport/TLS/SSH** | TLS handshake error, expired cert, SSH host-key mismatch | Cert/key validity, truststores, server identity |
| **Authentication/authorization** | HTTP 401/403, broker auth fail, DB login denied, SFTP permission denied | Credential rotations, roles, ACLs, token expiry |
| **Capacity/throttling** | 429, rising timeouts, broker flow control, DB pool exhausted | Rate limits, threads/pools, queue depth, sink saturation |
| **Protocol/configuration** | Wrong topic/queue/path, unsupported cipher, schema mismatch | Release config, endpoint addresses, contracts |
| **Semantic/business failure** | Validation failure, duplicates, stale versions, poison messages | Business events, schemas, idempotency—not necessarily disconnection |

**HTTP 404** or an empty poll does not automatically mean disconnection: 404 may mean a missing resource; empty file polls may mean partners haven't uploaded yet. Likewise, **broker connected** does not prove consumers hold partition assignments or handlers are committing.

### 2.3. Where Messages Sit Determines Recoverability

| Where Message Sits at Failure | Usually Recoverable? | Risk |
|---|---|---|
| Source SFTP/File intact | Re-readable if source retains it and filters allow | Premature deletion/rename/metadata marking |
| JDBC `READY`/outbox table | Yes if transactions/claims/leases are designed right | Stuck `CLAIMED` state, stale locks, double claims |
| JMS/AMQP durable queue | Depends on queue/message persistence, acks/tx | Premature acks, DLQ policies, expired TTLs |
| Kafka topic | Depends on retention, offsets, consumer groups | Premature offset commits, wrong replay bounds, rebalances |
| In-memory `QueueChannel` | **Not durable by default** | JVM crash loses queued/dequeued messages |
| Durable object/`MessageStore` | Reclaimable by claim ID | Expired tokens, premature GC, access permissions |
| Remote HTTP service committed | May require querying service state | Caller timeout leaves side-effect state unknown |

When you do not know where messages sit, **never bulk-replay**. Document uncertainty explicitly and investigate from authoritative sources.

## 3. Severity Classification, SLOs, and Decision Accountability

### 3.1. Reference Severity Table

| Level | Suggested Indicators | Response |
|---|---|---|
| **SEV-1 / Critical** | Total outage of critical flow, suspected high-value data loss/duplication, wide customer impact, suspected data leak | Page Incident Commander, engage Security/Business Owner as needed, preserve evidence, restrict risky changes |
| **SEV-2 / High** | Critical connector repeatedly down, backlog growing, SLO breach imminent | Coordinate on-call + system owners, prioritize containment and recovery |
| **SEV-3 / Medium** | Localized impact on one source/tenant with active buffering and margin | Triage, watch backlogs, plan structured fix |
| **SEV-4 / Low** | Brief self-healed glitch with zero business impact | Log event, track trends, improve alerting |

This is a **reference framework**, not a substitute for official org severity/SLO policies. When formal SLOs don't exist yet, state explicitly that interim thresholds approved by owners are in use.

### 3.2. Flow-Level SLIs/SLOs

Metrics more meaningful than "service alive":

- **Freshness:** elapsed time from source data availability to business commit.
- **Success rate:** business-contract completions / total work due.
- **Backlog age:** age of the oldest unprocessed work item.
- **End-to-end correctness:** reconciled matches vs. missing/duplicate/stale items.
- **Dependency availability:** valid connection ratio paired with real forward progress.
- **Recovery time:** elapsed time from detection to meeting business recovery criteria.

### 3.3. RTO, RPO, and Non-Guessing Boundaries

**RTO (Recovery Time Objective)** is the target duration to restore service. **RPO (Recovery Point Objective)** is the maximum acceptable data loss per design and contract. Never claim `RPO=0` simply because a broker has durable queues; premature acks, retention limits, consumer bugs, and non-transactional side effects can still lose data.

| Decision | Who Should Approve Under High Risk? |
|---|---|
| Throttle/pause a connector | Incident Commander / on-call per ops authority |
| Change credentials, certificates, network ACLs | Infrastructure/Security owner per workflow |
| Seek Kafka offsets, purge queues/DLQs, reset metadata | Data/Business Owner + Integration Owner with scope review |
| Replay side-effecting work | Business Owner + idempotency owner |
| Accept partial data loss or `UNKNOWN` state | Authorized business/compliance stakeholder |
| External incident notice to partners/customers | Communications / Incident Commander per policy |

**Principle:** favor **reversible, evidence-preserving actions** first; record who decided, why, scope, timestamp, and verification method.

## 4. Detection and Alerting: Watching the Right Signals

### 4.1. Do Not Rely Only on Stack Traces

Connectors can silently retry in the background without throwing to callers. Services can lose all external connectivity while worker threads stay running. Monitor **data-exchange behavior** alongside exception logs.

| Group | Signals Measured | Interpretation |
|---|---|---|
| Connection | connect success/failure, TLS/SSH handshakes, reconnect counts | Detects network/auth faults |
| Request | sent, received, 2xx/4xx/5xx, timeouts, p95/p99 latency | Detects slow target APIs/brokers |
| Polling | attempts, empty polls, last successful poll | Separates empty sources from dead pollers |
| Messaging | queue depth, unacked, retries, DLQ, Kafka lag | Detects backlogs and redeliveries |
| Business | last committed event, success/failure, duplicates suppressed | Confirms real forward progress |
| Storage | DB pools, transaction latency, SFTP file age, disk space | Pinpoints storage bottlenecks |
| Security | 401/403, cert expiry, token refresh failures | Separates expired credentials from network outages |

### 4.2. Three Priority Alerts

1. **No business progress:** due work exists at the source, yet the last business commit is stale.
2. **Backlog age SLO breach:** pending work age approaches or exceeds SLO.
3. **Sustained dependency failure:** connect/timeout/5xx/auth errors cross thresholds on an active flow with pending work.

An SFTP poller returning empty during off-hours when no files are expected shouldn't page unnecessarily. Tie alerts to **expected schedules/volumes** rather than merely "zero messages seen".

### 4.3. Sample Dashboard Snapshot

~~~text
Flow: partner-orders-sftp-inbound
Dependency: sftp.partner.example
Endpoint state: RUNNING
Last connection success: 15:02
Last business commit: 15:01
Connection failures / 5m: 24
Files waiting: 340
Oldest file age: 8m
Processing errors / 5m: 0
Retry attempts / 5m: 24
Unreconciled work: UNKNOWN
~~~

All numbers are **simulated**, not real production telemetry. Note: an endpoint can report `RUNNING` while failing every connect; "0 processing errors" isn't good news if zero messages ever reach handlers.

### 4.4. Conditional Alert Threshold Examples

Never hardcode one threshold across all systems. Example:

~~~text
WARN if oldestPendingAge > 0.7 × freshnessSLO
PAGE if oldestPendingAge > freshnessSLO
PAGE if expectedWork > 0 and successfulCommitCount = 0
     past agreed threshold
SECURITY ALERT if unexplained certificate/host-key mismatch occurs
~~~

This is a **policy example**, not default Spring Integration alerting. Tune to suppress false positives, specify telemetry sources, and declare timezones.

## 5. Initial Response Procedure: The First 0–15 Minutes

In real incidents, the first reflex must NOT be restarting every instance. Bound the blast radius and stop state from worsening.

### 5.1. Minutes 0–2: Confirm and Preserve Evidence

- [ ] Open incident record capturing **detection time**, on-call owner, and affected flow.
- [ ] Check dashboards for **last success, error counts, backlog age, pending/acks**.
- [ ] Cross-check data schedules: does the source actually have work due?
- [ ] Record latest deploy/config versions and recent credential/cert rotations if known.
- [ ] Preserve traces/logs/error messages with **secrets redacted**; do not wipe queues or reset offsets yet.
- [ ] If TLS/SSH impersonation or credential compromise is suspected: **halt actions that leak data** and notify Security per procedure.

### 5.2. Minutes 2–5: Pinpoint the Failure

- [ ] Identify **direction:** inbound receive, outbound send, request/reply, or storage lookup.
- [ ] Identify **protocol:** File, SFTP, HTTP, JMS, AMQP, Kafka, JDBC.
- [ ] Locate the **first failing hop** rather than staring at the last handler exception.
- [ ] Classify: DNS / network / TLS / authn / authz / rate limit / schema.
- [ ] Check whether one endpoint or multiple partners/regions are failing together.
- [ ] Estimate the **affected work window** from last success to now; mark `UNKNOWN` if evidence is incomplete.

### 5.3. Minutes 5–10: Containment

- [ ] If producers outpace consumers, apply **rate limits, bounded buffers, or controlled intake pauses**.
- [ ] If failures carry ambiguous side effects, **stop dangerous automatic retries** or route to reconciliation state per policy.
- [ ] While queues/brokers still hold work, protect retention and prevent wrong acks/drops.
- [ ] For incomplete SFTP/File transfers, avoid renaming or deleting files before verification.
- [ ] On credential failures, stop brute-force retrying invalid secrets.
- [ ] Label work states clearly (`IN_FLIGHT`, `PENDING`, `UNKNOWN`, `RETRYABLE`, `QUARANTINED`) using reliable sources.

### 5.4. Minutes 10–15: Conditional Recovery

- [ ] Confirm root cause well enough to act safely: network, cert, token, quota, broker, DB pool, or code/config.
- [ ] Pick **one small, reversible change**: policy-aligned reconnect, config rollback, lowered concurrency, or approved failover endpoint.
- [ ] Define **abort criteria** if errors or duplicates spike afterward.
- [ ] Record approver, timestamp, before/after configs, and verification test.
- [ ] Confirm **one new canary message** completes end-to-end before releasing full backlog.
- [ ] Send an incident update stating current status and any remaining uncertainties.

### 5.5. Operational Timeline

~~~mermaid
flowchart LR
    DET["Detect + timestamp"] --> SCOPE["Scope impact"]
    SCOPE --> SAFE["Contain / preserve work"]
    SAFE --> DIAG["Diagnose first failing hop"]
    DIAG --> FIX["Small reversible recovery"]
    FIX --> TEST["End-to-end canary"]
    TEST --> BACKLOG["Controlled backlog drain"]
    BACKLOG --> RECON["Reconcile + verify"]
    RECON --> CLOSE["Close incident / postmortem"]
~~~

Exact minute marks aren't rigid: timing flexes with severity and access rights. The fixed rule is **never skip containment and data-safety checks just to reconnect faster**.

## 6. Connection Incident Decision Tree

### 6.1. Diagnosis by Failure Layer

~~~mermaid
flowchart TD
    A["No progress or elevated errors"] --> B{"Does source actually have work?"}
    B -->|No/Unclear| CHECK["Check schedule and source; do not report data loss hastily"]
    B -->|Yes| C{"Can a connection be established?"}
    C -->|No| NET["DNS/route/port/firewall, TLS/SSH, credentials"]
    C -->|Yes| D{"Is endpoint authorized to act?"}
    D -->|No| AUTH["401/403/ACL/topic/DB/SFTP permission"]
    D -->|Yes| E{"Being load-limited?"}
    E -->|Yes| THROTTLE["429, pool exhausted, broker flow control"]
    E -->|No| F{"Do messages reach handlers?"}
    F -->|No| ROUTE["Channel/endpoint state, filters, pollers, subscriptions"]
    F -->|Yes| G{"Did business commit succeed?"}
    G -->|No| BIZ["Schema, DB, handler, transactions, retry/DLQ"]
    G -->|Yes| H{"Are ack/offset and readback accurate?"}
    H -->|No| REC["Reconcile duplicate / unknown / late replies"]
    H -->|Yes| OK["Canary + backlog drain + verify SLA"]
~~~

### 6.2. Mandatory Questions Before Retrying

1. Was the message **unsent**, **sent but unacked**, or **business-committed without reply**?
2. Can the side effect safely re-run? Is there a durable business idempotency key?
3. Does source retention/TTL outlast retries and backlogs?
4. Are multiple workers/replicas active? Are locks/leases/consumer-group/partition ownerships clear?
5. Do sibling subscriber groups still need the message?
6. Will changing connection pools or endpoint URLs disrupt ordering, sessions, or replay state?
7. When pausing a connector, where will incoming data sit and **who owns retaining it**?

**Golden rule:** when business effects sit in **`UNKNOWN`**, never retry non-idempotent commands before querying real state or obtaining explicit approval.

### 6.3. Safe Operations Matrix

| Action | Caution Level | Rationale |
|---|---|---|
| Read dashboards / secret-redacted logs | Usually safe | Mutates no state |
| Check DNS/routes/health via side-effect-free probes | Usually safe | Still watch permissions and load |
| Lower concurrency/rates and pause new intake | Reversible | Watch source buffers/retention while paused |
| Restart a listener/connector | Needs planning | Can trigger redelivery, rebalances, lost in-memory state |
| Swap credentials/truststores/host keys | Security-controlled | Risks masking spoofing or breaking sibling links |
| Replay DLQ or outbox | Side-effect risk | Requires idempotency and exact scoping |
| Seek Kafka offsets, purge queues/files, reset metadata | High risk | Can lose or duplicate data |
| Disable TLS verification or SSH host-key checks | **Never execute** | Exposes systems to MITM/compromise |

### 6.4. Action Change Log

Every operational change needs **before state, hypothesis, change, verifier, rollback, and evidence**.

~~~yaml
incidentId: INC-LAB-2026-011
operation: "reduce-consumer-concurrency"
target: "orders-inbound-flow"
hypothesis: "DB pool saturation causes read timeout"
before: "4 workers, high DB wait"
change: "reduce to 2 workers via approved deployment configuration"
expected: "DB wait and retries decrease; committed throughput stabilizes"
rollback: "restore approved previous concurrency"
approvedBy: "incident-commander"
result: "PENDING"
evidence: "redacted-dashboard-link-placeholder"
~~~

This template is illustrative, **not a live execution log**; populate real observed evidence during operations.

## 7. HTTP Runbook: Inbound and Outbound Gateway Disconnections

HTTP fails in multiple ways: **unreachable host**, **TLS handshake error**, **server 4xx/5xx**, **network timeout after server received request**, and **caller gateway timing out before handler completes**. Know whether the flow receives inbound requests or calls external APIs.

### 7.1. Locate the Right Side

| Spring Integration Endpoint | Responsibility | Common Failure Points |
|---|---|---|
| **HTTP inbound gateway** | Accepts external requests and returns flow replies | Reverse proxies, payload limits, auth, thread pools, reply timeouts |
| **HTTP outbound gateway** | Calls external HTTP APIs and feeds responses into flow | DNS, TLS, connect/read timeouts, 429/5xx |
| **HTTP outbound adapter** | One-way send with no gateway reply contract | Unknown side effects on network timeouts |
| **Scheduled HTTP poll** | Poller triggers periodic HTTP fetches | Request rates, cursors/watermarks, empty poll vs. outage |

### 7.2. Signals and Safe Checks

- [ ] Confirm exact URL hostname, port, path, method, and environment—**never copy credentials into logs**.
- [ ] Distinguish **connect timeout** from **read/response timeout**; they carry very different business meanings.
- [ ] Check TLS certificate validity, truststores, SNI, proxies, DNS, and network paths.
- [ ] On **401/403**, inspect identity, scope/audience, key rotation, and policies; never self-escalate privileges.
- [ ] On **429**, honor `Retry-After` and allowed rate limits; never crank up retries.
- [ ] On **502/503/504**, check upstream/downstream health, circuit breakers, proxy timeouts, and server overload.
- [ ] Check whether messages on `requestChannel` reached the HTTP gateway and how reply/error channels route.
- [ ] Capture `requestId`, `correlationId`, and **side-effect status** from the target API for write operations.

### 7.3. Response Plan by Status Code

| Scenario | Containment | Recovery | Verification |
|---|---|---|---|
| DNS fails to resolve | Cut retries; check DNS scope | Restore proper DNS/config—never bypass TLS verification via raw IP | Resolve from same runtime network; canary call |
| TLS cert expired/mismatched | Keep cert validation enabled | Renew/fix chain/truststore per workflow | TLS handshake verifies target host |
| Expired token (401) | Pause auth-retry loops | Refresh/rotate credential via secret manager | Least-privilege request succeeds |
| 403 Forbidden | Check principal/scope/resource | Fix approved permissions—never swap in admin token | Positive/negative canaries behave properly |
| 429 Too Many Requests | Rate limit / bulkhead | Honor `Retry-After`; lower concurrency | 429s drop; latency/throughput stabilize |
| 5xx / timeout | Circuit breaker / backoff | Coordinate with target owner; failover if supported | End-to-end commit/readback; backlog drops |
| Inbound gateway reply timeout | Isolate slow requests | Check handlers and outbound deps; consider 202/`jobId` if contract permits | Response/error mapping and job state accurate |

### 7.4. "Server Committed While Caller Timed Out"

~~~mermaid
sequenceDiagram
    participant F as Spring Integration Flow
    participant G as HTTP Outbound Gateway
    participant S as Remote Service
    participant DB as Remote DB
    F->>G: CreateOrder(requestId=R100)
    G->>S: POST /orders R100
    S->>DB: Commit order R100
    DB-->>S: OK
    Note over G,S: Response lost or exceeds deadline
    G-->>F: Timeout / UNKNOWN
    F->>S: GET status by R100 (if contract supports it)
    S-->>F: Order R100 exists
    Note over F,S: Do NOT send a second create command
~~~

If the target API lacks **idempotency keys** or **status lookups**, classify items as `UNKNOWN` and run approved manual verification—never blindly declare retries safe.

### 7.5. Restoring the Flow

1. Run an authorized **read-only or canary** request without creating uncontrolled side effects.
2. Confirm retry/timeout policies weren't disabled or set so low they cascade failures.
3. Re-open traffic gradually (by tenant/partition/endpoint where possible).
4. Watch p95/p99, 429/5xx, in-flight counts, circuit breakers, and downstream commits.
5. For backlogged write commands, check `requestId`/`idempotencyKey` before retrying.
6. Reconcile accepted vs. committed vs. timed-out vs. `UNKNOWN` counts.

### 7.6. Classification Caveats

- HTTP **200** does not prove schema compliance or business success.
- HTTP **202** means accepted per API contract, not completed.
- HTTP **409** can mean version conflict or valid duplicate key; never retry endlessly.
- HTTP **4xx** usually requires fixing requests/permissions, not network retries.
- A request canceled by the caller may still be running on the server.

## 8. File/SFTP Runbook: Remote File Source Unavailable

File/SFTP inbound normally uses `SourcePollingChannelAdapter` polling a `MessageSource`—do not confuse it with a `PollingConsumer` reading `QueueChannel`. When a poller shows `RUNNING` yet emits zero files, inspect the source, filters, and "file complete" contract.

### 8.1. Sample Flow Map

~~~mermaid
flowchart LR
    PARTNER["Partner SFTP / Local directory"] --> SOURCE["File/SFTP MessageSource"]
    POLLER["Scheduler + Poller"] --> SOURCE
    SOURCE --> CH["MessageChannel"]
    CH --> PARSE["Validate / Parse"]
    PARSE --> DB["Business DB / Outbound Adapter"]
    SOURCE --> META["Accept-once metadata / filter"]
    PARSE --> ARCH["Archive / Quarantine per policy"]
~~~

### 8.2. Typical Symptoms

| Symptom | Hypothesis | Evidence to Collect |
|---|---|---|
| SFTP connect timeout | Network, DNS, server down, pool exhaustion | Endpoint URL, reachability, timeout class |
| SSH host-key mismatch | Server rotated key or MITM | Approved fingerprint, server owner |
| Authentication failed | Key/password rotated, account locked | Principal, key version, auth logs |
| Directory listing denied | Bad ACL/path/permissions | Remote path, list/read permissions |
| Poller ignores new files | Filter pattern, `lastModified`, accept-once metadata | Filter trace, remote listing, timestamps |
| Intermittent parse failures | Producer still uploading | Temp extensions, markers/renames, changing sizes |
| Files re-read after restart | Non-persistent or unshared metadata store | File ID/path, persisted filter state |
| Multiple replicas grab same file | Missing shared claim/lock | Instance IDs, claim records |

### 8.3. Remote Triage

- [ ] Verify DNS and SSH endpoints against approved configuration.
- [ ] Verify host fingerprints out-of-band with the owner—**never auto-accept new host keys**.
- [ ] Verify key/credential roles, validity, and remote folder permissions.
- [ ] Separate **list** success from **download** success and **parse/business commit** success.
- [ ] Inspect remote directory for real files, filename patterns, and ready markers.
- [ ] Check modified times/sizes/renames, UTC/timezones, and server clock skew if using age filters.
- [ ] Check local staging disk/quotas, file handles, streams, and session pools.
- [ ] Confirm whether remote and local filters persist metadata durably or only in RAM.

### 8.4. Safe Recovery by Root Cause

1. **Server unreachable:** leave files on source if producer retains them, back off pollers, coordinate with partner, never wipe seen-file metadata.
2. **SSH host key changed:** verify out-of-band with owner then update trust under change control; never disable verification.
3. **SFTP key expired:** rotate secret and test least-privilege identity; keep keys out of logs/tickets.
4. **Missing files due to pattern/filter:** run read-only listings and inspect metadata; never wipe the entire filter before checking processed history.
5. **Mid-upload files:** require producers to use temp names + atomic rename or ready markers; never parse incomplete files.
6. **Staging disk full:** pause downloads/throttle intake, free space per retention and owner approval; never delete uncommitted files.
7. **Stale SFTP sessions:** reconnect/validate sessions per adapter; verify clean transfer resumption.

### 8.5. Special Care for Streaming Adapters

An SFTP inbound streaming adapter can return an `InputStream` or session-backed stream. Closed streams cannot be re-read, and stream objects **aren't portable across JVMs**. If a handler fails mid-stream:

- Check whether the source file persists and transfers can restart.
- Close streams/sessions on every error path.
- For durable retries, stage complete files/objects in durable shared storage before marking received.
- Never persist an `InputStream` inside a durable `MessageStore` expecting post-restart deserialization.

### 8.6. Avoid Data-Destroying Shortcuts

**Never** delete remote files, move files to archive, or wipe accept-once filters just because connectivity returned. Follow this sequence:

~~~text
Confirm source file complete
  → Confirm file identity/checksum/business key
  → Confirm processed/unknown state
  → Process or idempotent replay
  → Business DB readback
  → Archive/delete only when completion contract permits
~~~

If partners auto-delete files on fixed retention, flag **source retention expiry** risk in the incident timeline and coordinate holding files before expiry.

### 8.7. Recovery Verification

- [ ] SFTP connects cleanly with verified host key.
- [ ] Can list and read an authorized test file.
- [ ] Complete files matching the pattern are picked up; temp files are ignored.
- [ ] Previously processed files cause zero duplicate side effects post-reconnect/restart.
- [ ] File backlog and age shrink; parsers/business handlers commit cleanly.
- [ ] Staging, metadata, and archives match reconciled state.

## 9. JMS Runbook: Listener Not Receiving or Broker Disconnected

Spring Integration's JMS message-driven inbound adapters rely on a **message listener container**. Queues can serve multiple competing consumers; topics follow distinct subscription semantics. **JMS session acknowledgement and transaction policies** govern redelivery when listeners stop.

### 9.1. Detection Signals

- Listener fails to connect or loops reconnects.
- Queue depth rises, consumer count drops, `received=0` while producers publish.
- Authentication errors, missing destinations, or provider-specific exceptions.
- Unacked/in-flight counts climb with zero business commits.
- DLQ spikes after a schema/code release.
- Outbound JMS gateway sends requests without receiving correlated replies.

### 9.2. Diagnostic Table

| Symptom | Possible Cause | Check |
|---|---|---|
| Broker refused connection | Network, broker down, wrong endpoint | Broker health/ports, DNS, routes |
| JMS authentication failed | Rotated credentials/ACLs | Principal and consume/publish permissions |
| Destination not found | Wrong queue/topic name, provisioning | Topology, environment, deploy diff |
| Consumer count = 0 | Listener/container stopped | Endpoint lifecycle, startup logs |
| Queue depth grows while consumers run | Slow handler, DB fault, poison message | Business latency, retries, DLQs |
| Continuous message redelivery | Rollbacks, missing commits, handler errors | Exceptions, attempt counts, tx configs |
| Reply timeout | Responder down, reply dest/correlation broken | Request IDs, `JMSReplyTo`, reply consumers |

### 9.3. Investigation Steps

1. Identify destination type: **JMS Queue or Topic**, durable/shared subscriptions if any.
2. Check **`ConnectionFactory`, sessions, listener containers**, and broker-side consumer counts.
3. Check authn/authz and TLS certificates if encrypted.
4. Compare **enqueued/dequeued/unacked**, DLQ counts, and last business commit.
5. Verify actual **ack mode or transaction manager**—never guess from Spring Integration handlers.
6. Check whether **one flow or all flows** sharing that broker are impacted.
7. If endpoints are stopped, verify who stopped them, `autoStartup`, and recent deploy events.

### 9.4. Containment

- If the broker is down, buffer on producers/outboxes where possible; avoid tight retry bursts.
- If handler bugs cause redelivery loops, throttle retries and route poison messages to DLQ per policy, preserving evidence.
- If the DB sink is overloaded, lower listener concurrency rather than adding consumers.
- Before pausing consumers, verify queue retention and message expiry limits.
- Never spin up duplicate-named queues or swap topics casually, splitting work streams.

### 9.5. Recovery

1. Restore broker/connectivity/credentials via owners while enforcing TLS and ACLs.
2. On listener reconnect, confirm exact **destinations and subscriptions**.
3. Run a canary message with a unique authorized business key and verify end-to-end.
4. Ramp concurrency gradually within downstream capacity.
5. Watch redeliveries/DLQs, as pre-outage in-flight messages will redeliver.
6. Reconcile accepted vs. committed vs. acked—never conclude solely from broker dequeues.

### 9.6. JMS Transactions and Redelivery

~~~mermaid
sequenceDiagram
    participant B as JMS Broker
    participant L as Listener
    participant DB as Business DB
    B->>L: Deliver Work W1
    L->>DB: Commit W1
    DB-->>L: OK
    Note over L: Process crash before JMS ack/commit
    B->>L: Redeliver W1 after recovery
    L->>DB: Check idempotency for W1
    DB-->>L: Already committed
    L-->>B: Acknowledge according to policy
~~~

**Warning:** JDBC transactions and JMS session transactions **do not automatically form one atomic transaction** simply because one Java method touches both. Strong coupling requires a real distributed transaction manager—or else inbox/outbox/idempotency/reconciliation.

### 9.7. Never Confuse Async Service Activators with Broker ACKs

If a listener pushes messages onto `ExecutorChannel` and returns **before business commit**, the container may consider dispatch successful and ack prematurely. A subsequent JVM crash loses work already gone from the broker. Either:

- Keep critical steps synchronous inside the ack/transaction scope, **or**
- Durably persist to another store/queue before acking, **or**
- Use framework- and broker-supported manual acks tested across failure paths.

### 9.8. JMS-Specific Exit Criteria

- [ ] Broker connections and listener consumer counts are stable.
- [ ] Queue depth/unacked return to acceptable levels; message expiry isn't threatening backlogs.
- [ ] Business commits climb and idempotency holds under redeliveries.
- [ ] DLQ stops abnormal growth; existing items have owners.
- [ ] For request/reply, correlations and reply destinations remain accurate.

## 10. AMQP/RabbitMQ Runbook: Connections, Channels, Consumers, and Flow Control

RabbitMQ uses **exchange → queue → consumer**, differing from Kafka's partitioned log and subtly from JMS. Outages leave **unacked** messages, lost publisher confirms, and redeliveries.

### 10.1. Relevant Topology

~~~text
Producer
   → AMQP outbound adapter/publisher
   → Exchange + routing key
   → Queue (durable/quorum/classic per choice)
   → Spring AMQP listener container
   → Spring Integration AMQP inbound adapter
   → MessageChannel → business handler
~~~

**Publisher confirms**, **consumer acknowledgements**, and **business commits** are three separate milestones. A publisher confirm reflects broker acceptance per config—not consumer processing.

### 10.2. Detection and Evidence Gathering

| Symptom | Where to Look | Caution |
|---|---|---|
| Connection refused/reset | Broker nodes, network, TLS | Never disable TLS |
| Channel closed | Protocol exceptions, resource limits, auth | Check exact exception and topology |
| Queue `messages_ready` climbs | Too few/slow consumers | Check business commits and unacked |
| High `messages_unacked` | High prefetch, hung handlers | Never restart blindly without checking in-flight |
| Publisher confirm timeout | Slow broker or dropped connection | Broker may still have persisted the message |
| Unroutable publish | Wrong exchange/binding/routing key | Do not equate send-OK with queue receipt |
| DLQ growth | Poison messages, retry/reject policy | Classify errors before replaying |
| Flow control / memory / disk alarms | Broker pressure | Throttle publish rates; engage broker admins |

### 10.3. Triage and Containment

1. Verify exact **vhost, exchange, queue, binding, and routing key** per environment.
2. Check queue existence, durability, TTL, and dead-lettering configs.
3. Capture **ready, unacked, consumer counts, and publish/deliver/ack rates** before changes.
4. On **broker memory/disk alarms**, throttle publishers and coordinate capacity—never keep flooding.
5. If consumers stopped, inspect connections, channels, listener containers, and auth.
6. If unacked stays high, inspect prefetch and handler durations; never assume unacked work finished.
7. If publisher confirms are lost, record `UNKNOWN` and retry using stable business event IDs.

### 10.4. Step-by-Step Recovery

- Restore broker topology, network, and credentials under change control.
- Verify queue bindings **and routing** with a valid canary message; connecting alone isn't enough.
- Resume publishers/consumers slowly while watching ready/unacked/ack rates.
- On redeliveries, verify DB idempotency and retry budgets.
- Watch DLQs, especially items routed via TTL/reject/overflow rules.
- Avoid bulk-purging queues or wiping DLQs just to shrink dashboard backlogs.

### 10.5. Prefetch and Recovery

High prefetch lets one consumer hoard many unacked deliveries. When it disconnects, the broker re-dispatches them simultaneously, spiking load on surviving consumers. Lowering prefetch during incidents **can** improve fairness, yet test throughput, latency, and round-trips—and note prefetch changes cannot fix a broken DB sink.

### 10.6. Retry/Requeue Loops

When handlers reject schema errors and brokers immediately requeue:

~~~text
Receive → schema fail → nack/requeue → receive → fail ...
~~~

Flows **burn CPU and connections making zero progress**. Enforce bounded retries, DLQs/quarantines, owners, and controlled replays. Where ordering matters, business owners must approve moving poison records to DLQs since gaps result.

### 10.7. Never Treat Brokers as Business Proof

**Acked** messages don't prove downstream committed if listeners ack ahead of async work. Conversely, DB commits followed by lost acks cause redeliveries. Reconcile by business keys—not RabbitMQ counters alone.

### 10.8. AMQP-Specific Exit Criteria

- [ ] Publisher confirms/routing and consumers operate normally.
- [ ] Ready/unacked/connection errors stabilize; backlog age drops.
- [ ] Retry/requeue loops are eliminated or quarantined.
- [ ] DLQ has owners and sufficient TTL for investigation.
- [ ] Business DB readbacks show zero duplicate side effects.

## 11. Kafka Runbook: Broker Unreachable, Rebalances, Lag, and Offsets

Kafka consumer clients run internal poll loops; Spring Integration **message-driven Kafka inbound adapters** normally use listener containers. Consumer groups split **topic partitions**; lag and assignments can stay unhealthy even after networks recover.

### 11.1. Critical Symptoms

| Symptom | Hypothesis | Where to Look |
|---|---|---|
| Broker connect failures | DNS, TLS, SASL, bootstrap/listener addresses | Client logs, broker availability |
| Consumer group has zero active members | Listeners stopped, bad credentials | Group membership, app lifecycle |
| Continuous rebalances | Pod churn, poll intervals, slow processing | Assignment/rebalance metrics |
| Lag spikes on one partition | Hot key, poison record, slow handler | Per-partition lag, commits/processing |
| Offsets stop advancing | Handler errors, ack mode, commit failures | Consumer logs, business readbacks |
| Idle consumer despite many replicas | More consumers than partitions | Partition counts and assignments |
| DLT spikes | Deserialization/schema/processing errors | Error handlers, DLT status |
| Re-reading records post-restart | Uncommitted or reset offsets | Committed offsets, group state |

### 11.2. First Checks

- [ ] Confirm exact **bootstrap servers, cluster, topic, `group.id`, partition count**, and region.
- [ ] Verify TLS/SASL credentials and least-privilege topic/group ACLs.
- [ ] Inspect assignments and lag **per partition**, not just aggregate lag.
- [ ] Inspect listener container, error handler, retry topics/DLT, and backoffs.
- [ ] Identify which offsets **committed to Kafka** vs. **committed to business DB**.
- [ ] After recent deploys, check deserializer/schema versions and partition keys.
- [ ] Check whether slow handlers exceed poll intervals/timeouts and trigger rebalances.

### 11.3. Actions to Avoid

**Never** reset offsets to earliest/latest, change `group.id`, add partitions, delete topics, or skip bad offsets just to "zero out lag". Those actions can **reprocess entire histories or drop unprocessed messages**. Determine exact record ranges, business keys, retention, idempotency, and get approvals first.

### 11.4. Restoring Connectivity

1. Fix DNS/broker listeners/TLS/SASL/ACLs via owners.
2. Confirm listener containers join the group and **receive partition assignments**.
3. Verify a canary record and its consumer business commit.
4. Watch rebalance counts, poll/processing durations, commit errors, and lag.
5. Scale concurrency up to **assignable partitions**—not blindly adding replicas.
6. Handle stuck partitions/poison records via error handlers and DLTs per policy.
7. Reconcile business state against read/committed offsets.

### 11.5. Rebalances and Duplicates

~~~mermaid
sequenceDiagram
    participant K as Kafka Topic
    participant A as Consumer A
    participant DB as Business DB
    participant B as Consumer B
    K->>A: Record R offset 91
    A->>DB: Commit R
    DB-->>A: Success
    Note over A: Rebalance/crash before offset commit
    K->>B: Reassign partition; read R again
    B->>DB: Idempotent check R
    DB-->>B: Already applied
    B-->>K: Commit progress per container policy
~~~

Kafka offers strong processing semantics within its own transactions/configs, yet **does not automatically provide exactly-once across external HTTP/SFTP/DB systems**. External side effects still demand business idempotency and reconciliation.

### 11.6. Separating Throughput from Lag

One hot partition can drive aggregate lag up while all other partitions sit near 0. Adding workers past partition counts won't fix it—inspect key skew or business bottlenecks. If handlers block on DB locks, adding concurrency can worsen lag via lock contention.

### 11.7. Recovering When Offsets and Business State Diverge

| State | Risk | Recovery Direction |
|---|---|---|
| Business committed, offset uncommitted | Redelivery/duplicates | Idempotency; commit after verification |
| Offset committed, business uncommitted | Data loss if no re-emitter | Escalate, reconcile, replay strictly by approved keys/ranges |
| Source topic retention expired | Records gone from Kafka | Recover from valid outboxes/snapshots/backups or log gap |
| DLT holds failed records | Needs permanent/transient triage | Fix schema/code; controlled replay |
| `group.id` accidentally changed | Re-reads or skips per `auto.offset.reset` | Restore config; assess affected range |

### 11.8. Kafka-Specific Exit Criteria

- [ ] Group membership and partition assignments are stable.
- [ ] Zero abnormal rebalance loops; per-partition lag drops cleanly.
- [ ] Test records traverse business handlers and DB commits.
- [ ] DLT/retry topics have owners and zero loops.
- [ ] Offsets and business state reconciled across the incident window.

## 12. JDBC/Database Runbook: Disconnections or Pool Exhaustion

Databases serve as **sources** for JDBC polling, **sinks** for service activators/outbound gateways, or **MessageStores/outboxes/inboxes** for reliability. When DBs go down, both intake and business commits halt, with distinct consequences by role.

### 12.1. Symptoms

| Signal | Hypothesis | Distinguish By |
|---|---|---|
| Connection refused | DB node/service/route down | Network vs. DB health |
| Login/auth failed | Rotated credentials / revoked roles | Principal, secret version, role |
| Connection acquisition timeout | Exhausted pool, leaks, DB overload | Active/idle/pending pool, DB sessions |
| Query timeout | Slow SQL, locks, downstream stalls | Query plans, locks, timeouts |
| Deadlock/serialization failure | Transaction contention | Proper retries and ordering |
| Claim rows stuck `IN_PROGRESS` | Dead worker, active lease | Lease, owner, attempt count |
| Outbox pending climbs | Relay/broker or DB fault | Last publish, outbox lag |
| `MessageStore` retrieval error | Claim store offline / schema mismatch | Store health, serialization |

### 12.2. Biggest Danger on Restart

If an application:

1. Selects a `READY` row;
2. Updates it to `PROCESSING` and commits;
3. Hits a DB timeout or process crash;
4. Has no lease expiry/reclaim;

the task **stays stuck forever**. Conversely, retrying claims without conditional updates lets two workers run the same task.

### 12.3. Triage

- [ ] Identify DB role: **source, business sink, message store, claim registry, or outbox**.
- [ ] Check connection pool active/idle/wait/timeouts and DB server limits.
- [ ] Classify errors: network, login, deadlock, query timeout, or schema mismatch.
- [ ] Inspect active transactions and long-held locks within authorized bounds.
- [ ] Check recent deployments, migrations, or credential rotations.
- [ ] For JDBC polling, inspect `READY` queries, transactions, claims, and leases.
- [ ] For outboxes, check pending counts, oldest pending age, and relay health.
- [ ] For `MessageStore`, verify post-deploy schema/serializer compatibility.

### 12.4. Recovery

1. Coordinate with DB owners to restore service/connectivity/credentials—never widen privileges "just to test".
2. If pools exhaust from leaks or slow queries, **lower concurrency** and isolate lock-heavy tasks instead of merely raising pool size.
3. Confirm in-flight DB transactions rolled back or resolved accurately.
4. For JDBC polling, reclaim **validly expired leases**—never blindly reset all `IN_PROGRESS` rows to `READY`.
5. For outboxes, relays resume publishing **the same event ID**; consumers handle duplicates.
6. Verify a canary transaction and business readback.
7. Ramp speed gradually while watching pool saturation, lock waits, and commit latencies.

### 12.5. Sample Task-Claim State Machine

~~~text
READY
  → CLAIMED(owner, leaseUntil, version)
  → PROCESSING
  → COMPLETED
  or → RETRYABLE / FAILED

If lease expires:
  verify no valid worker still holds commit rights
  → conditionally reclaim checking version/lease
~~~

When old workers linger past lease expiry, **fencing/version checks at commit time** stop stale workers from overwriting newer workers' work.

### 12.6. JDBC-Specific Exit Criteria

- [ ] Connection pools and DB services stabilize without ongoing login/timeout errors.
- [ ] Core queries/transactions pass with verified business readbacks.
- [ ] Claim rows and outboxes progress with zero stuck tasks beyond policy.
- [ ] Duplicates and unknown transactions reconciled across the incident window.
- [ ] Handlers never mark items processed before commit.

## 13. Reading Spring Integration Internals When a Connector Fails

A flow can stay wedged **even after external connectors recover** due to channels, endpoint lifecycles, error handlers, schedulers, or gateway reply mappings. Inspect every link.

### 13.1. Which Endpoint Is Running?

| Component | Role | What to Check |
|---|---|---|
| **`SourcePollingChannelAdapter`** | Polls `MessageSource` (File/SFTP/JDBC) | Scheduler, trigger, `source.receive()`, filters, `maxMessagesPerPoll` |
| **`PollingConsumer`** | Receives from `PollableChannel` | `QueueChannel` depth, `receiveTimeout`, poller, handler |
| **Message-driven inbound adapter** | Listeners (JMS/AMQP/Kafka) | Listener container, connection, subscription, acks |
| **Inbound gateway** | Receives external requests and replies | HTTP mapping, reply timeout, error mapping |
| **Outbound adapter** | One-way external send | Send results, retry/ack semantics, error paths |
| **Outbound gateway** | Sends request and awaits reply | Send timeout, remote I/O timeout, correlation |
| **Service activator** | Runs business handler | Transactions, validation, idempotency |
| **`MessageChannel`** | Dispatches messages | Sync/async semantics (`Direct`/`Executor`/`Queue`/`PubSub`) |

### 13.2. Distinguish Send Errors from Handler Errors

**`DirectChannel`** invokes handlers on the sender thread. Synchronous handler exceptions can bubble back to adapters/gateways and drive transactions/acks when configured.

**`ExecutorChannel`** hands messages to an executor to run on another thread. When the adapter sees send succeed, **the handler has not necessarily finished**. Error handling and transaction contexts do not cross threads automatically; monitor error channels and completions separately.

**`QueueChannel`** holds messages for active polling. If an in-memory channel is lost on restart, never assume "the broker will redeliver" unless a durable source sits upstream with retry logic.

**`PublishSubscribeChannel`** fans out to multiple subscribers. If one branch fails after a sibling committed, replaying everything can duplicate effects on the already-succeeded branch.

### 13.3. Poller Alive Yet Making Zero Progress

- [ ] Are scheduler threads blocked by unrelated slow tasks?
- [ ] Do `FixedDelay`/`FixedRate`/Cron triggers fire on schedule?
- [ ] Is `maxMessagesPerPoll` set too low to drain backlogs?
- [ ] Does `MessageSource.receive()` return `null` because sources are empty or because filters reject everything?
- [ ] Do SFTP session/connect timeouts drag out every poll cycle?
- [ ] Are poller exceptions caught, logged, and swallowed by error handlers without alerting?
- [ ] If transaction advice is present, which exact scope does the transaction cover?

**`receiveTimeout`** on `PollableChannel` is **not an HTTP/SFTP network timeout**. When an external source won't connect, tweaking `QueueChannel` `receiveTimeout` accomplishes nothing.

### 13.4. Gateway Times Out While Handler Keeps Running

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant GW as Spring Integration Gateway
    participant CH as ExecutorChannel
    participant H as Handler
    C->>GW: Request R1
    GW->>CH: send(R1)
    CH->>H: async process
    Note over GW: Reply timeout
    GW-->>C: Timeout
    H->>H: Business commit R1
    H-->>GW: Late reply
    Note over GW,H: Caller gave up; retries risk duplicates
~~~

When callers retry, enforce **`requestId`/`idempotencyKey`** to check state and prevent duplicate effects. Never "fix" this by setting all timeouts to infinity.

### 13.5. `errorChannel` and Transport Failures

Spring Integration provides **`ErrorMessage`**, error channels, advice chains, and error handlers. Yet:

- Exceptions may be **rethrown**, **routed as `ErrorMessage`**, or **caught and swallowed**.
- An error flow that only logs **does not guarantee** broker rollback/redelivery.
- Async failures may never reach the original sender.
- `MessageHeaders` can carry `errorChannel`/`replyChannel` while still needing sensitive-data protection.
- Exact **ack/commit** timing must be verified against your concrete adapter/container.

**Right practice:** trace a single business key/trace ID through **receive → channel send → transform → handler → DB/outbound → ack/reply**, identifying the last step proven successful and first step proven failed.

### 13.6. Endpoint Lifecycles and Control Authority

Spring Integration lifecycle controls (such as start/stop endpoints or Control Bus if configured) can pause/resume flows. However, **never assume** every endpoint stops instantaneously or safely halts in-flight work. Bean names, registries, control commands, and runtime permissions depend on your app and version—follow owner-provided runbooks.

**Never** fire ad-hoc commands into a production Control Bus without verifying target, privileges, and side effects.

## 14. Retries, Backoff, Timeouts, Circuit Breakers, and Bulkheads

Resilient designs **recover from transient faults** without turning brief blips into retry storms that crush targets.

### 14.1. Four Retry Layers to Coordinate

| Layer | Example | Risk When Stacked Uncontrolled |
|---|---|---|
| HTTP client retry | Retries connect/read timeouts | Repeats side-effecting commands |
| Spring Integration advice/error handler | Retries message handler | Multiplies client retries |
| Broker redelivery / retry topic | JMS/AMQP requeues, Kafka retries | Poison loops, DLT backlogs |
| Business/job scheduler | Re-enqueues `FAILED` tasks | Re-submits same work repeatedly |

If each layer retries up to **3 times**, downstream calls multiply via nested loops; **never assume 3 is the effective retry budget**. Designate **one primary retry owner** per error type while other layers simply report status or enforce bounded handoffs.

### 14.2. Suggested Retry Policy Table

| Error | Retry? | Condition |
|---|---|---|
| Transient DNS / connection reset | Conditional | Backoff retries respecting scope and quotas |
| HTTP 503/504 | Conditional | Never duplicate side effects when outcome is `UNKNOWN` |
| HTTP 429 | Yes | Honor `Retry-After` and shed load |
| HTTP 400/422 | Usually no | Fix request/schema first |
| HTTP 401/403 | No tight retries | Fix credentials/policies; security review |
| TLS/SSH host identity mismatch | **Never retry past verification** | Verify with owner/certs/keys |
| DB deadlock / serialization failure | Conditional | Safe transaction-boundary retries within budget |
| Broker unavailable | Yes | Backoff, producer outboxes, durable buffers |
| Poison message | Bounded / no | Quarantine/DLQ with owner |

### 14.3. Backoff + Jitter

Policy pattern:

~~~text
attempt 1: retry after short delay
attempt 2: exponential increase + jitter
attempt 3: increase up to configured cap
attempt N: stop automatic retry; quarantine/escalate

Never busy-loop with zero delay when the dependency is unavailable.
~~~

This is not default Spring Retry or Spring Integration config. Ground real parameters in target SLAs, quotas, and idempotency.

### 14.4. Circuit Breakers

When a dependency fails consistently, circuit breakers shed calls to protect threads and connections. Yet an **OPEN** breaker does not guarantee messages are safely stored. Verify:

- Where do rejected calls sit?
- Do callers get errors/fallbacks or durable buffering?
- Are **business `UNKNOWN`** outcomes separated from unsent errors?
- Can half-open probes create duplicate side effects?
- When the circuit closes, can targets absorb the accumulated backlog?

### 14.5. Bulkheads and Bounded Queues

Cap concurrent calls per outbound endpoint so one failing partner cannot exhaust all app threads. For bounded `QueueChannel`/`ExecutorChannel`, define full behavior: wait, reject, persist to durable broker, or return controlled errors. **Never use unbounded heap queues** to hide backlogs; JVM crashes lose buffered work.

### 14.6. Timeout Layering

~~~text
Business deadline
  >= / related to
  gateway reply timeout
  + outbound connect/read timeout
  + retry/backoff budget
  + handler/transaction execution time
~~~

Stages do not always sum linearly across implementations. Define a clear **end-to-end deadline** so inner timeouts never wastefully exceed outer budgets. Remember: a local timeout **does not cancel remote transactions**.

### 14.7. Fix Root Causes First

If DB pools exhaust from long transactions, more retries only stack more waiting threads. If target APIs return 429, raising concurrency backfires. If Kafka rebalances from slow handlers, tune processing/partitioning/acks instead of cranking session timeouts forever.

## 15. Data Correctness: ACKs, Commits, Duplicates, and Reconciliation

A production runbook needs a **data correctness** policy, not just network recovery. Almost every multi-hop integration has gaps between receive, process, and acknowledge.

### 15.1. Work-Item State Map

~~~text
SOURCE_AVAILABLE
  → DELIVERED
  → VALIDATED
  → BUSINESS_COMMITTED
  → TRANSPORT_ACKNOWLEDGED
  → RETENTION_OR_CLEANUP_ELIGIBLE

Exception states:
  RETRYABLE, UNKNOWN, DUPLICATE, QUARANTINED, EXPIRED, RECONCILE_REQUIRED
~~~

This is an **application state model** for runbook clarity, not a built-in Spring Integration enum. Names vary in production; never collapse distinct milestones together.

### 15.2. Failure-Window Matrix

| Last Confirmed Step | Unconfirmed Step | Risk | Action |
|---|---|---|---|
| Source has `READY` file/row | Receive failed | Pending data | Preserve source, fix connector, re-fetch |
| Message in in-memory `QueueChannel` | Business uncommitted | JVM restart loses buffer | Check durable sources; don't assume broker redelivery |
| Broker delivered | Handler uncommitted | Redelivery possible | Retry/idempotency, preserve DLQ policies |
| DB committed | Broker ack/offset unconfirmed | Post-restart duplicates | Dedupe business keys; ack after check |
| HTTP request sent | No reply | `UNKNOWN` external effect | Query status/idempotency; never blind-retry |
| Claim Check token published | Claim content unreachable | Missing/expired claim | Reconcile store, retention, and permissions |
| Business committed | Outbox event unpublished | Missing downstream event | Relay outbox; idempotent publish |
| Business committed | Cleanup/ack incomplete | Leftovers or redeliveries | Finalize per policy without corrupting state |

### 15.3. Idempotency by Business Key

**Technical message IDs** can change on retries or recreated messages. Deduplicate using stable business keys:

~~~text
sourceSystem + tenantId + operation + businessEntityId + version
~~~

If a partner sends the same order twice under two filenames, keying by **filename** fails to block duplicates; keying by **partner + documentId/orderId + version** protects properly when contracts specify once-per-version processing.

### 15.4. Illustrative Inbox/Outbox Schema

~~~sql
CREATE TABLE integration_inbox (
    consumer_name VARCHAR(120) NOT NULL,
    business_key VARCHAR(200) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    result_ref VARCHAR(200),
    PRIMARY KEY (consumer_name, business_key)
);

CREATE TABLE integration_outbox (
    event_id VARCHAR(180) PRIMARY KEY,
    business_key VARCHAR(200) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    publish_status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
~~~

This is an illustrative schema, **not a ready migration**, omitting retry/claim/version columns. When domain tables and inbox/outbox share one DB, bundle mutations in **one DB transaction**. Still, local DB transactions cannot roll back remote HTTP calls, SFTP renames, or broker publishes.

### 15.5. Reconcile Against Sources of Truth

Over `[last known good, first fully recovered]`, inventory:

1. Work **emitted by sources** per file manifests, outboxes, broker logs, or API registers.
2. Work **received** by adapters.
3. Work **committed** at targets.
4. Work **acked/offset-committed/marked processed** per transport.
5. Work **routed to DLQ/quarantine** or still pending.
6. **`UNKNOWN` work**: dropped connections, lost ACKs/replies, or missing logs.

Never reconcile purely by **raw counts** when one file holds multiple orders, messages carry batches, or fan-out splits branches. Match by business keys, versions, scopes, and tenants.

### 15.6. States Requiring Manual Verification

- **`UNKNOWN_PAYMENT`/`UNKNOWN_ORDER`:** remote effect may have committed; verify by business reference.
- **`OFFSET_AHEAD_OF_COMMIT`:** Kafka skipped uncommitted records; build an approved replay plan.
- **`FILE_ARCHIVED_BUT_NOT_COMMITTED`:** source transitioned prematurely; restore files under audit.
- **`DLQ_WITHOUT_ORIGINAL_PAYLOAD`:** Claim Check expired; cannot replay from token alone.
- **`DUPLICATE_WITH_CONFLICTING_PAYLOAD`:** same idempotency key with altered content; resolve versions/conflicts.

### 15.7. Post-Reconciliation Summary Metrics

A report might look like:

~~~text
Expected distinct business keys:      2,000
Confirmed committed keys:             1,970
Retryable/pending keys:                  20
Quarantined with owner:                   8
UNKNOWN pending manual review:            2
Confirmed unintended duplicate effects:  0
~~~

Numbers are **examples**. While any `UNKNOWN` remains, report **connectivity restored while data reconciliation stays open**—never mark fully `CLOSED` before policy-compliant resolution.

## 16. Security: Certificates, Identities, and Connection Permissions

During outages, on-call staff face pressure to "just make it work". Yet server verification failures can signal **spoofing attacks, misrouting, or unauthorized changes**.

### 16.1. Strictly Forbidden

- Disabling **TLS certificate validation**, hostname checks, or SSH host-key verification to bypass handshake errors.
- Swapping in broad admin credentials instead of service credentials just to verify requests.
- Pasting raw passwords, access tokens, SFTP private keys, or secret-bearing DB URLs into tickets/chats/logs.
- Opening production firewalls to all IPs/CIDRs without scope or expiry.
- Logging full PII-bearing payloads "for easier debugging".
- Bypassing per-tenant authorization during retries/replays.
- Trusting partner-asserted `requesterId`/`tenantId` headers without source verification.

### 16.2. TLS/SSH Mismatch Runbook

1. Confirm the **target host** matches authoritative config; check DNS/routing changes.
2. Collect **non-sensitive** fingerprints/certificate metadata and handshake errors.
3. Contact the system/partner owner **out-of-band** to confirm planned rotations.
4. Once verified, update truststores/`known_hosts` through change control.
5. Run minimal verification and log an audit entry.
6. If unverified, **fail closed**, escalate to Security, and withhold sensitive traffic.

### 16.3. Credential Expiry Runbook

1. Check credential versions and expirations in the authorized secret manager.
2. Compare rotation timestamps against the first failed attempt.
3. Verify principal permissions/scopes on exact target resources without over-privileging.
4. Rotate/refresh credentials via approved workflows—never hardcode or store in Markdown.
5. Verify **positive and negative authorization**: valid operations succeed; unauthorized ones still fail.
6. Watch sibling flows sharing the secret for side effects.

### 16.4. Network Incidents Can Masquerade as Security Incidents

Mispointed DNS, proxy cert swaps, changed broker ACLs, or OAuth audience mismatches all feel like "server down". Classify **network vs. authentication vs. authorization vs. server identity** before touching firewalls, TLS, or credentials.

### 16.5. Watch Stale Data After Credential Revocations

When revoking a compromised service account, copies or tokens may linger in **brokers, message stores, claim references, DLQs, or staging files**. Recovery must verify who can read or replay leftover data—not just issue new credentials and forget copies.

## 17. Controlled Production Change Checklist

### 17.1. Pre-Change Preparation

- [ ] Identified **systems of record** and message states in the outage window.
- [ ] Proposed change has proper authorization and scope.
- [ ] Captured **before state**: configs, versions, metrics, pending/offsets, data state.
- [ ] Documented a root-cause hypothesis rather than "trying a restart".
- [ ] Minimal, reversible change prepared wherever possible.
- [ ] Assessed risks of duplicates, data loss, reordering, or secret exposure.
- [ ] Canary/readback checks and abort thresholds defined.
- [ ] Relevant owners notified.

### 17.2. During Execution

1. Record change/incident ID, owner, and timestamp.
2. Apply **one controlled change at a time** where incident pacing allows.
3. Watch connection failures, business commits, backlog age, retries, DLQs, and duplicates immediately afterward.
4. If duplicates or unknown side effects rise, halt ramp-up and gather evidence.
5. Retain investigative artifacts until reconciliation finishes.

### 17.3. Post-Change Verification

- [ ] Dependency handshakes, authn, and authz pass.
- [ ] Endpoints restarted in the right flow and environment.
- [ ] Canary completed full business commit and readback.
- [ ] Zero retry storms, queue memory pressure, or duplicate file reads beyond contract.
- [ ] Backlog drains safely within SLO bounds.
- [ ] Advance to **recovery/reconciliation** only with concrete evidence.

### 17.4. Rollbacks

A **config-only rollback** does not undo committed data. If a change caused messages to send or commit, app rollbacks never erase business outcomes. Verify transaction states, offsets/queue positions, and replay safety independently.

### 17.5. Operational Change Record Template

~~~yaml
incidentId: INC-LAB-2026-011
changeId: CHG-LAB-009
targetFlow: orders-http-outbound
beforeVersion: "v1"
afterVersion: "v2"
reason: "approved TLS truststore rotation"
scope: "one external partner endpoint"
dataSafety:
  pendingWorkLocation: "durable-outbox"
  replayPolicy: "idempotency required"
  estimatedUnknownEffects: "PENDING_REVIEW"
validation:
  transportHandshake: "PENDING"
  canaryBusinessCommit: "PENDING"
  sourceTargetReconciliation: "PENDING"
rollback: "restore approved v1 configuration after evaluating in-flight work"
approval: "recorded incident owner placeholder"
~~~

**Never mark `PASS` before testing.** This is a fill-in template, not a completed change record.

## 18. Draining Backlogs and Replaying in Proper Order

Once connectivity returns, accumulated backlogs hit the pipeline. Launching full worker concurrency immediately can re-crash recovering downstreams, sparking retry storms and scrambling order.

### 18.1. Steps to Re-Open Traffic

1. Confirm sources remain intact and readable.
2. Bucket work into **new, pending, retryable, unknown, DLQ, already committed**.
3. Run a canary with a dedicated business key and verify source–target readback.
4. Open at **low concurrency** and observe commit throughput/latency.
5. Ramp up while sinks retain headroom and retry storms stay absent.
6. Isolate poison messages without skipping ordering-critical events.
7. Reconcile outage-window data rather than processing only fresh arrivals.
8. Return to steady state once data correctness and SLOs hold.

### 18.2. Estimating Backlog Drain Time

With initial backlog **B work items**, incoming rate **λ items/s**, and sustainable commit throughput **μ items/s** (`μ > λ`):

~~~text
approximateDrainTimeSeconds = B / (μ - λ)
~~~

Example:

~~~text
B = 12,000 items
λ = 30 items/s
μ = 70 committed items/s
net drain = 40 items/s
approximate drain time = 300 s ≈ 5 minutes
~~~

This is an **idealized steady-state estimate**, ignoring retries, batching, ordering, hot partitions, remote throttling, and quotas. When `μ <= λ`, backlogs **never drain**; adding workers will not raise `μ` when the sink is saturated.

### 18.3. Backlog Age Matters More Than Count Alone

A queue of 1,000 brand-new messages may be healthy, while 100 messages waiting 2 hours breach SLAs. Track **oldest unprocessed age**, per-work-type deadlines, and on-time completion ratios.

### 18.4. Principle of Minimal Replay

- **Replay only affected business keys**—avoid re-scanning entire histories unnecessarily.
- Keep **`idempotencyKey` and `eventVersion`** invariant when re-emitting past work.
- For fan-outs, isolate failing subscribers rather than forcing committed branches to redo work.
- For Kafka, never reset consumer-group offsets globally when only one partition/range failed without approval.
- For SFTP/File, distinguish partially parsed, fully committed, and untouched files.
- For `UNKNOWN` HTTP commands, verify status before re-creating.
- For DLQs, fix schemas/code or dependencies before replaying.

### 18.5. Prioritizing by Risk Tier

| Work Group | Processing Priority | Constraint |
|---|---|---|
| Read-only query awaiting response | Retryable within TTL/deadline | Never serve stale/expired data |
| Verified uncommitted business command | Retry when safe | Enforce idempotency and source state |
| `UNKNOWN` business command | Reconcile first | Never auto-replay |
| Stale-version event | Do not overwrite newer state | Audit/repair per business rules |
| DLQ poison message | Fix root cause then controlled replay | Owner, attempt cap, checksum/version |
| Incomplete file | Wait for producer completion | Marker/rename/size contract |

### 18.6. When to Pause Replay

Pause or throttle down if:

- Business duplicates/conflicts cross safety limits.
- Target 429/5xx rates climb alongside throughput.
- DB pool saturation or lock waits spike sharply.
- Kafka rebalances loop or offset/commit state goes erratic.
- SFTP/file sources hit retention expiry, checksum mismatches, or modified files.
- DLQ grows rapidly without known cause.

### 18.7. Concluding Backlog Drain

Do not wait for queue depth = 0 on continuous-intake systems. Measure **steady-state age/lag, commit throughput, and correctness**, then reconcile any remaining `UNKNOWN`/quarantined items.

## 19. Dashboards and Post-Incident Telemetry Evidence

For a runbook to work, every critical flow needs a dashboard **anchored to business outcomes**. Adapter counters measure transport only—never final business proof.

### 19.1. Minimum Metric Set

| Metric | Suggested Dimensions | Question Answered |
|---|---|---|
| `dependency_connection_failures_total` | flow, dependency, error class, region | How many connect errors occur? |
| `dependency_reconnect_attempts_total` | connector type, dependency | How long/hard is it reconnecting? |
| `outbound_request_duration` | target, method/operation, outcome | Are calls slow or timing out? |
| `poll_attempts` / `empty_polls` | source, endpoint | Is the poller alive or stalled? |
| `message_received_total` | flow, connector | Is real work entering the app? |
| `business_committed_total` | flow, result class | Are real business outcomes committing? |
| `message_retry_total` | reason, stage | Where do retries cluster? |
| `message_duplicate_suppressed_total` | consumer, source | Are redeliveries/duplicates elevated? |
| `message_dead_letter_total` | flow, category | What work needs triage? |
| `queue_depth` / `consumer_lag` | queue, group, partition | How large and skewed is the backlog? |
| `oldest_pending_age` | source, priority | Is freshness SLO breached? |
| `message_inflight_unacked` | connector, consumer | Is work lingering unacked? |
| `connection_pool_active` / `wait` | datasource/client | Are pools congested? |
| `last_successful_business_commit` | flow | When was the last verified commit? |
| `unreconciled_work_count` | flow, severity | How many items remain `UNKNOWN`? |

**Metric names are naming examples**, not defaults auto-emitted with exact labels by Spring Integration/Spring Boot. Map to your real Micrometer, tracing, and broker metrics while controlling label cardinality.

### 19.2. Labels to Avoid

Never put **`requestId`, tokens, `claimId`, full filenames, raw URLs with query secrets, emails, or `customerId`** into high-cardinality or sensitive metric labels. Use bounded dimensions: `flow`, `operation`, `sourceType`, `region`, `outcome`, `errorClass`. Individual IDs belong in access-controlled logs and traces.

### 19.3. Correlating Four Charts in One Time Window

~~~text
A. Dependency errors / minute       ↑ spikes at 15:03
B. Received vs committed / minute   received = 0, committed = 0
C. Backlog depth + oldest age       ↑ climbs steadily
D. Retry, DLQ, duplicate rate       retries ↑, DLQ steady
~~~

Upon recovery:

~~~text
A. Dependency errors                ↓ returns to baseline
B. Committed throughput             ↑ exceeds arrival rate during drain
C. Backlog/oldest age               ↓ returns below SLO
D. DLQ/duplicate/unknown            stabilizes with assigned owners
~~~

If A drops yet B stays at 0, the incident is **not** resolved—inspect channels, handlers, and transactions.

### 19.4. Structured Log Sample

~~~json
{
  "incidentId": "INC-LAB-2026-011",
  "flow": "partner-orders-sftp-inbound",
  "dependencyType": "SFTP",
  "dependencyAlias": "partner-sftp-lab",
  "endpoint": "orders-inbound-adapter",
  "stage": "CONNECT",
  "outcome": "TRANSIENT_FAILURE",
  "errorClass": "ConnectTimeout",
  "businessKeyRef": "redacted-or-hashed",
  "retryAttempt": 3,
  "traceId": "TRACE-LAB-018",
  "occurredAt": "2026-11-23T15:05:00+07:00"
}
~~~

This log is **illustrative**, not a default framework format. Keep secrets and raw payloads out of incident tickets; link to access-controlled audit stores.

### 19.5. Unified Outcome Vocabulary

Adopt shared terminology across operations and engineering:

| Outcome | Meaning |
|---|---|
| **`CONNECTED`** | Handshake/connection succeeded; processing not proven |
| **`DELIVERED`** | Work reached an endpoint, channel, or broker |
| **`COMMITTED`** | Business transaction satisfied completion criteria |
| **`ACKNOWLEDGED`** | Transport recorded progress |
| **`RETRYABLE`** | Eligible for retry per policy |
| **`PERMANENT_FAILURE`** | Do not auto-retry without fixing root cause |
| **`UNKNOWN`** | Cannot verify whether side effects occurred |
| **`RECONCILED`** | State verified against source of truth |
| **`QUARANTINED`** | Work isolated awaiting owner |

Never use a vague **`SUCCESS`** across connect, send, and business commit without specifying which layer succeeded.

## 20. Incident Communications and Shift Handovers

Runbooks guide technical recovery, while prolonged incidents also require **accurate, concise, speculation-free updates** so business teams understand risks, scope, and next steps.

### 20.1. Incident-Open Notice Template

~~~text
INCIDENT: [INC-ID] – [Flow/Dependency]
Detected at: [timestamp timezone]
Confirmed impact: [source/target, capability, tenant/scope]
Symptoms: [connection / timeout / backlog / no business progress]
Data state: [committed / pending / unknown; do not guess counts]
Containment: [actions taken, scope]
Investigating: [top hypothesis and evidence]
Owner: [on-call/partner owner/incident commander]
Next update: [per official incident cadence]
~~~

**Never** claim "zero data loss" before reconciliation, nor leak internal hostnames/secrets over unauthorized channels.

### 20.2. Progress Update Template

~~~text
Status: INVESTIGATING / CONTAINED / RECOVERING / RECONCILING
New evidence: [verified event or metric]
Connection state: [DOWN / PARTIAL / UP]
Business progress: [commit rate, last success, backlog trend]
Outstanding unknown: [count or UNKNOWN]
Changes applied: [change ID, owner, rollback path]
Remaining risks: [retries, duplicates, loss, retention expiry, security]
Next step: [one concrete action]
~~~

### 20.3. Connectivity-Restored / Reconciliation-Open Notice Template

~~~text
Connectivity to [dependency] is restored and a canary completed end-to-end.
Backlog is draining within projected SLO bounds.
Messages in window [from, to] are still undergoing reconciliation;
zero missing/duplicate work is not yet fully confirmed.
Reconciliation owner: [owner].
Incident remains in RECOVERING/RECONCILING status.
~~~

### 20.4. Incident-Close Template

~~~text
Incident [ID] closed at [timestamp].
Root cause: [confirmed or best-supported root cause].
Verified connectivity and business path:
  [transport tests, canary, commit readback, backlog, reconciliation].
Data summary:
  [expected, committed, replayed, quarantined, unknown].
Residual risks and owners:
  [if any, per handover procedure].
Corrective actions:
  [action, owner, due date].
~~~

If any `UNKNOWN` items remain, record **connectivity resolved while data-reconciliation work items remain open** under proper governance—never delete questionable records just to close dashboards.

### 20.5. Shift Handover Checklist

- [ ] Incident ID, severity, service/flow, and owners.
- [ ] Last known good, outage window, and connection recovery time.
- [ ] Active changes and rollback steps.
- [ ] Queue depth/lag/oldest age, retries/DLQ, business commit rate.
- [ ] List of messages/ranges still `UNKNOWN` or quarantined.
- [ ] Actions **forbidden** until formal approval.
- [ ] External system/partner contacts and response status.
- [ ] Next actions with owners and verification criteria.

### 20.6. Responsibility Boundary Between Incident Commander and Engineer

Engineers provide **evidence and technical options**, never unilaterally accepting business data loss. Incident Commanders set priorities and approve changes within authority; Security or Business Owners step in whenever changes touch secrets, money, personal data, or business consistency.

## 21. Full Tabletop Drill: SFTP Outage, RabbitMQ Backlog, Slow DB

### 21.1. Simulated System Context

The **Partner Orders Pipeline** pulls CSV files from SFTP, validates schemas, queues work items in RabbitMQ, and runs multiple workers writing orders to a test PostgreSQL DB. Post-commit results trigger a secondary HTTP service. This is an **educational scenario**; zero real production incidents are implied by these numbers.

~~~mermaid
flowchart LR
    PARTNER["Partner SFTP"] --> POLL["SFTP inbound poller"]
    POLL --> PARSE["Validate / Split file"]
    PARSE --> OUT["AMQP outbound adapter"]
    OUT --> QUEUE["orders.work queue"]
    QUEUE --> A["Consumer A"]
    QUEUE --> B["Consumer B"]
    A --> DB[("Orders DB")]
    B --> DB
    DB --> HTTP["HTTP Outbound Gateway"]
    HTTP --> TARGET["Partner Status API"]
    POLL --> META["Persistent metadata"]
    A --> ERR["Error / DLQ / Audit"]
    B --> ERR
~~~

**Required design properties:** files mark complete only after contractual business writes succeed; RabbitMQ enforces durable queues/ack policies; DB enforces unique business keys; HTTP side effects use idempotency/status lookups.

### 21.2. Simulated Timeline

| Time | Event | Evidence |
|---|---|---|
| 15:00 | Normal flow | Low file age, steady business commits |
| 15:03 | SFTP connection resets | Connection error count climbs |
| 15:05 | Poller stays `RUNNING` with zero new files | Last successful SFTP poll freezes |
| 15:08 | Partner reports uploading a new batch | Source backlog confirmed |
| 15:10 | On-call opens incident | First failing hop is SFTP receive |
| 15:13 | Cuts retries; checks host/cert/credentials | Leaves source files untouched |
| 15:17 | SFTP connectivity restored | Canary list/download passes |
| 15:18 | Poller feeds accumulated files into flow | Broker work queue climbs |
| 15:19 | DB pool hits ceiling | Handler timeouts, RabbitMQ unacked climb |
| 15:22 | Lowers consumer concurrency | DB waits drop; commits stabilize |
| 15:28 | Backlog starts draining | Commit throughput exceeds arrivals |
| 15:37 | Business data reconciled | Pending/unknown items classified |

### 21.3. Correct Recovery Steps

**Step A — Do not reset SFTP filters.** Identify which files committed pre-outage before any replay; metadata filters are hints, not replacements for business DB readbacks.

**Step B — Preserve raw source files.** If partner uploads are active, await ready markers/renames; never read partial files just because the poller reconnected.

**Step C — Emit idempotent work.** If RabbitMQ producer calls timed out, brokers may still have persisted events. Keep event IDs/business keys stable so consumers deduplicate.

**Step D — Pace downstream load.** Once SFTP recovers and RabbitMQ fills while DB is stressed, raising AMQP concurrency worsens contention. Throttle down and watch real commit throughput.

**Step E — Reconcile reply-less HTTP calls.** When orders committed to DB yet status API calls timed out, mark HTTP effects `UNKNOWN`—never resend non-idempotent commands.

**Step F — Final check:** SFTP source counts, valid row counts, broker queue/DLQ states, DB unique business keys, and remote HTTP states must reconcile per contract.

### 21.4. Two Dangerous Mistakes If Rushed

**Mistake 1 — Resetting all files to "unprocessed".** If 40% of files created orders pre-outage, wiping metadata and re-running creates duplicates wherever business logic lacks idempotency.

**Mistake 2 — Scaling workers way up to clear backlog.** The DB pool is already saturated; extra workers multiply locks, timeouts, and redeliveries, aging backlogs further and complicating reconciliation.

### 21.5. Minimum Evidence to Close the Case Study

- [ ] Valid SFTP host identity and file-ready contract upheld.
- [ ] Source file inventory for the incident window with per-file processing status.
- [ ] RabbitMQ published/delivered/acked/DLQ counts reconciled by business events—not raw totals alone.
- [ ] DB contains exactly one outcome per unique business key.
- [ ] `UNKNOWN` HTTP commands have status queries or assigned owners.
- [ ] Fresh business commits appear and oldest backlog age drops below SLO.
- [ ] Quarantined items carry reasons, owners, and replay plans.
- [ ] Post-incident config changes include rollback refs, audits, and root-cause notes.

## 22. Pre-Production Runbook Verification Matrix

This test suite focuses on **operability and recovery**, not merely parser unit tests. Run scenarios in an authorized test/game-day environment with **before/after states** and evidence—never mark `PASS` without executing.

### 22.1. Connectivity, Identity, and Error Classification

| ID | Scenario | Expected Outcome |
|---|---|---|
| **RB-01** | HTTP target DNS fails to resolve | Classified DNS/network, bounded retry, zero leaked secrets |
| **RB-02** | HTTP connect timeout | Never assumes remote received request |
| **RB-03** | HTTP read timeout after remote DB commit | Marked `UNKNOWN`; status query/idempotency precedes retry |
| **RB-04** | HTTP 429 with `Retry-After` | Throttles rate; zero retry storm |
| **RB-05** | HTTP 401 from expired token | Safe credential refresh/rotation; no brute-force retries |
| **RB-06** | HTTP 403 from true permission denial | Never escalates privileges; alerts owner |
| **RB-07** | TLS cert mismatch | Fails closed, verifies with owner, never disables validation |
| **RB-08** | SFTP host-key mismatch | Blocks unverified connection; never auto-accepts |
| **RB-09** | SFTP key expired | Rotates right service principal; never logs private key |
| **RB-10** | Empty inbound file poll when source has no files | Does not raise false outage alerts |

### 22.2. Files, Polling, and Storage

| ID | Scenario | Expected Outcome |
|---|---|---|
| **RB-11** | 10-minute SFTP connect timeout | Backoff/alerts without tight retry loops |
| **RB-12** | Mid-upload file not yet renamed | Incomplete file never parsed |
| **RB-13** | Poller `RUNNING` yet filters skip new files | Identifies filter/metadata cause without blind resets |
| **RB-14** | Two replicas spot the same file | Shared claims/metadata + idempotency block duplicates |
| **RB-15** | SFTP stream fails mid-download | Closes session/stream with safe re-read path |
| **RB-16** | Local staging disk full | Pauses/throttles intake without deleting uncommitted files |
| **RB-17** | In-memory `QueueChannel` holds work during JVM crash | Acknowledges limit; durable source/reconciliation handles recovery |
| **RB-18** | Claim Check token intact while original payload TTL expired | Missing claim detected; never falsely acks success |

### 22.3. JMS, RabbitMQ, and Kafka

| ID | Scenario | Expected Outcome |
|---|---|---|
| **RB-19** | JMS broker restarts | Listener reconnects to right destination; safe redelivery |
| **RB-20** | JMS listener stops on credential failure | Classifies auth error; restores least-privilege access |
| **RB-21** | JMS commits DB then dies before ack | Business idempotency prevents duplicates |
| **RB-22** | JMS error handler swallows exception | Test exposes real ack/retry semantics to prevent silent loss |
| **RB-23** | RabbitMQ publisher confirm lost | Marks `UNKNOWN`; retries with stable event ID |
| **RB-24** | RabbitMQ high unacked from prefetch | Finds slow workers; tunes with verification |
| **RB-25** | RabbitMQ poison message loops requeues | Retry budget/DLQ breaks loop |
| **RB-26** | Kafka broker unreachable | Retries/backoffs; listener recovers assignments |
| **RB-27** | Kafka consumer group continuously rebalances | Diagnoses partitions/processing time without offset resets |
| **RB-28** | Kafka DB commits before offset commit | Redelivery produces zero duplicate effects |
| **RB-29** | Kafka offset ahead of business state | Flagged as data-gap incident; approved replay |
| **RB-30** | Kafka 3 partitions, 5 consumers | Never claims all 5 consumers are active |

### 22.4. Databases, Business Logic, and Recoverability

| ID | Scenario | Expected Outcome |
|---|---|---|
| **RB-31** | DB connection pool exhausted | Sheds load/optimizes rather than only raising retries |
| **RB-32** | Transient DB deadlock | Transaction retries per policy idempotently |
| **RB-33** | JDBC task `CLAIMED` when worker dies | Lease reclaim enforces versioning/fencing |
| **RB-34** | Outbox commits before relay publishes | Retries same event ID; zero lost messages |
| **RB-35** | HTTP command commits before reply timeout | Reconciliation/lookup prevents double execution |
| **RB-36** | DLQ replay after schema fix | Targeted replay yields accurate business state |
| **RB-37** | Fan-out: one branch committed, sibling failed | Never forces succeeded branch to duplicate work |
| **RB-38** | Business event arrives out of version order | Never overwrites newer state with stale data |
| **RB-39** | Rolling deploy with unacked messages | Graceful stop/redelivery per contract |
| **RB-40** | Re-opening backlog too fast triggers DB 503/timeouts | Backpressure/circuit breakers stabilize targets |
| **RB-41** | Connector rollback attempted after side effects | Does not blindly claim external business state rolled back |
| **RB-42** | `UNKNOWN` items remain after reconnect reconciliation | Incident is not prematurely marked fully data-recovered |

### 22.5. Observability and Human Controls

| ID | Scenario | Expected Outcome |
|---|---|---|
| **RB-43** | Endpoint `RUNNING` while business commits = 0 | No-progress alert catches failure |
| **RB-44** | Empty polls when no input scheduled | Does not trigger sustained false pages |
| **RB-45** | Source retention nearing expiry before recovery | Warning fires and source hold coordinated |
| **RB-46** | Incident log contains access token | Redaction/ACL cleanup and policy handling |
| **RB-47** | Operator attempts DLQ purge pre-reconciliation | Runbook blocks action and demands approval |
| **RB-48** | Shift handover with active backlog/unknowns | Captures owner, evidence, next steps, and rollback |
| **RB-49** | Transport canary passes while business DB has zero writes | Whole incident is not marked resolved |
| **RB-50** | Partner reports recovered while metrics show errors | Investigation continues grounded in end-to-end evidence |

### 22.6. Test-Case Report Template

~~~yaml
testCase: RB-35
flow: "orders-http-outbound"
scenario: "Remote commit succeeds but reply is lost"
expected: >
  The request enters UNKNOWN status; business state is checked using
  the same stable idempotency key before any retry.
actual: "Fill after experiment"
result: PENDING
evidence: "lab://tests/RB-35"
owner: "integration-lab"
verifiedAt: null
~~~

This YAML is **documentation-only**, not a repository file to create. Never flip `result` to `PASS` without inspecting real remote state and business DB outcomes.

### 22.7. Useful Testing Order

1. **Network layer:** timeouts, DNS, TLS, authentication.
2. **Connector layer:** listener/poller startup, subscriptions, channel/error mappings.
3. **Data layer:** retries, acks, offsets, idempotency, business commits.
4. **Infra layer:** broker/DB restarts, worker crashes, rolling deploys.
5. **Operations layer:** backlog drains, alerts, incident communications, rollbacks.

**Negative/fault-injection** tests expose far more bugs than single happy-path requests. Always isolate test environments and datasets before injecting deliberate faults.

## 23. Game Days: Periodic Disconnection Drills

Runbooks untested in drills often harbor false assumptions about **endpoint lifecycles, broker acks, source retention, or target limits**. Game days prove runbooks work—never create unapproved production outages.

### 23.1. Prerequisites Before a Drill

- [ ] Isolated test environment with scoped permissions, separate from prod data and credentials.
- [ ] Dedicated **test dataset** with unique business keys and known expected outputs.
- [ ] Assigned facilitator and authorized operator.
- [ ] Abort/rollback criteria and test-data cleanup plan.
- [ ] Metric/log/trace dashboards active and free of secrets.
- [ ] Baseline snapshot of configs and test state.
- [ ] Fault-injection scope approved; never impact live partners without consent.

### 23.2. Five Priority Drills

| Drill | Simulated Fault | What to Observe |
|---|---|---|
| **G1 – SFTP unavailable** | Test server blocks connections for a bounded window | Backoff, alerts, file readiness, post-recovery readback |
| **G2 – HTTP timeout after commit** | Mock delays or drops response after persisting | `UNKNOWN` state, idempotency, remote status |
| **G3 – Broker restart** | JMS/AMQP test broker restarts | Redelivery, acks, duplicate suppression, backlogs |
| **G4 – Kafka rebalance** | Stop one test consumer member | Assignments, offsets, lag, ordering |
| **G5 – DB pool saturation** | Cap connections or slow test DB | Bulkheads, backpressure, zero retry storms |

### 23.3. Detailed Drill G2: Lost Response After DB Commit

**Input:** `CreateOrder` request with `idempotencyKey = ORDER-TEST-0099`.

**Fault injection:** mock remote service persists the order and deliberately stalls until caller times out before returning. Never hit live payment or production order endpoints.

**Objectives:**

1. Gateway reports timeout/`UNKNOWN` instead of "unprocessed".
2. Retry controller keeps the identical `idempotencyKey`.
3. Service echoes the saved outcome or exposes status lookup.
4. Business DB holds **one** order for the test key.
5. Audit captures timestamps for send, commit, timeout, status lookup, and reconciliation.

**FAIL criteria:** handler creates two orders, loses `UNKNOWN` tracking, or catches errors and reports fake success.

### 23.4. Detailed Drill G3: Broker Fault Between Receive and ACK

1. Publish one valid message with a stable business ID.
2. Let consumer receive and write to DB.
3. Crash/disconnect **before acknowledgement** in the test environment.
4. Restore broker/consumer.
5. Observe redelivery per policy.
6. Confirm DB holds exactly one business effect.
7. Check DLQ and attempt counts; zero infinite loops.

Whenever a test cannot control exact crash timing deterministically, record **test scope limitations** rather than claiming proven exactly-once.

### 23.5. Runbook Evaluation Metrics

| Criterion | How to Measure |
|---|---|
| **Time to detect** | First failure until alert becomes visible |
| **Time to classify** | Time to pinpoint the true first failing hop |
| **Time to contain** | Time until system stops worsening data state |
| **Time to reconnect** | Until connections and canaries pass |
| **Time to business recovery** | Until commits/lag meet recovery thresholds |
| **Time to reconcile** | Until every item in the incident window is classified |
| **Operator error count** | Out-of-scope or unapproved actions, if any |
| **Replay correctness** | Missing/duplicate/stale business keys post-drill |

### 23.6. Post-Drill Follow-Up

Record what **the runbook said should happen** vs. **what actually happened**. Update instructions, owners, dashboards, alerts, and coding practices in the next improvement cycle. **Do not turn this section into editing lessons of other modules in STEP 4**; this is guidance for learners.

## 24. Postmortems, Corrective Actions, and Closing the Reliability Loop

Connectivity incidents usually have a clear **trigger** (expired cert, downed broker node, API rate limit), yet **data blast radius exceeds the trigger** whenever retries, acks, retention, or idempotency fall short. Postmortems must capture both the trigger and amplifying conditions.

### 24.1. Postmortem Structure

1. **Summary:** service, start/end timestamps, severity, overall impact.
2. **Customer/business impact:** affected flows, volumes, delays, failures, unreconciled items.
3. **Timeline:** timestamped facts linked to evidence sources.
4. **Detection:** which alerts fired and which missed.
5. **Root cause and contributing factors:** network, TLS, credentials, configs, code, brokers, DB, retries, partner dependencies.
6. **Data correctness:** expected/committed/missing/duplicate/unknown/quarantined counts.
7. **Mitigation and recovery:** changes made, effectiveness, rollbacks.
8. **What went well / poorly:** strengths and gaps in runbooks, coordination, and telemetry.
9. **Corrective actions:** code/config/monitoring/runbook/test fixes with owners and due dates.
10. **Follow-up validation:** test or game day proving actions closed the gap.

### 24.2. Separate Triggers from Amplifying Factors

Example:

~~~text
Trigger:
  Partner SFTP server rotated host keys without planned notification.

Contributing factor A:
  No advance alerting on certificate/key rotation.

Contributing factor B:
  Poller retried continuously without proper backoff.

Contributing factor C:
  Source file retention was shorter than the outage window.

Contributing factor D:
  Processed metadata was not reconciled during recovery.

Corrective actions:
  (1) Partner change notifications + owner workflow.
  (2) Backoff/circuit breakers + no-progress alerts.
  (3) Retention SLAs / outboxes / durable staging.
  (4) Replay checklists + idempotency/reconciliation tests.
~~~

These details are examples, not a real incident. Teams must avoid blaming causes without supporting evidence.

### 24.3. Criteria for Strong Corrective Actions

| Too Vague | Verifiable |
|---|---|
| "Improve monitoring" | "Add alert when oldest SFTP file age breaches SLO during intake hours; drill RB-11" |
| "Make retries safer" | "Cap retry budgets on HTTP 503/429 keeping `idempotencyKey`; test RB-03/RB-04" |
| "Fix Kafka" | "Stabilize partition assignment and commit policies; run rebalance game day RB-28" |
| "Handle failures" | "Separate transient vs. permanent, assign DLT owner, test poison loop RB-25" |
| "Improve DB" | "Monitor DB pool waits, throttle concurrency on saturation, test RB-31" |
| "Ensure no duplicates" | "Unique business key + inbox tx; fault-injection tests RB-21/RB-23/RB-28" |

### 24.4. Every Action Needs an Owner and Closing Evidence

Each action requires:

- Target and connector scope.
- Owning team/role.
- Org-aligned due date.
- Change type: code, config, capacity, permissions, ops, or partner contract.
- Test/rehearsal proving the fix.
- Rollback/risk assessment.

Never close corrective actions merely because a PR merged or deployed; actions guarding against data loss/duplication require verification tests or equivalent proof.

### 24.5. Runbook Review Cadence

Review runbooks whenever changing:

- Brokers, HTTP clients, SFTP/JDBC connectors, or Spring Integration versions.
- Error handlers, retry advice, ack/offset policies, or transaction strategies.
- Multi-instance topologies, partitions, queues, or consumer groups.
- Credentials, TLS/SSH key-rotation policies, or external partners.
- Retention settings across Kafka, files, object stores, or DLQs.
- Or whenever an incident/game day reveals missing or wrong guidance.

## 25. One-Page On-Call Checklist and Summary

### 25.1. 60-Second Pre-Action Checklist

- [ ] I know the **flow, environment, first failing hop**, and last-known-good time.
- [ ] I know whether the source still holds data and where messages sit.
- [ ] I checked network/TLS/auth/capacity **before** restarting.
- [ ] I am NOT disabling TLS/SSH checks or widening permissions against policy.
- [ ] I have NOT purged queues/DLQs/files or reset offsets/metadata without approval.
- [ ] I know which messages are **`COMMITTED`, `ACKED`, `UNKNOWN`, `RETRYABLE`**.
- [ ] I verified idempotency and reconciliation plans before replaying.
- [ ] I have a canary, abort threshold, rollback path, and owner.
- [ ] I watch **business commits** and **backlog age**, not just connection status.
- [ ] I log evidence and update the incident before shift handover.

### 25.2. Quick Protocol Matrix

| Protocol | Connection Check | What to Protect | Recovery Signal |
|---|---|---|---|
| **File/SFTP** | SSH key/session, path, poller, file-ready filter | Remote files, accept-once metadata, staging | New files process once; backlog age drops |
| **HTTP** | DNS/TLS/auth, 429/5xx, connect/read timeouts | `UNKNOWN` side effects, idempotency keys | Canary + status readback pass; 5xx drops |
| **JMS** | Broker/session/listener, destinations, auth | Acks/transactions/redelivery, DLQs | Business commits steady; queue depth normalizes |
| **AMQP** | Connection/channel/exchange/queue/binding | Publisher confirms, unacked, requeue/DLQ | Acks + commits healthy; ready/unacked drop |
| **Kafka** | Broker/SASL/TLS, group assignments, lag | Offsets/commits/rebalances, DLT, retention | Per-partition lag drops; business commits match |
| **JDBC** | DB/connection pools/queries/locks | Transactions, claims/leases/outboxes | Queries/commits stable; stuck tasks drop |

### 25.3. Three Post-Recovery Pillars

~~~text
TRANSPORT
  Connections/TLS/authentication OK
  Endpoints/listeners/pollers/channels active

DATA DELIVERY
  Backlog/lag shrinking per SLO
  Retries/DLQs/offsets/acks show zero unresolved anomalies

BUSINESS CORRECTNESS
  Committed results verified via readback
  Duplicates/missing/stale/UNKNOWN items reconciled
  Incident actions and owners handed over
~~~

### 25.4. Self-Check Questions

1. Why can an endpoint report `RUNNING` yet process zero messages?
2. How does an **HTTP connect timeout** differ from an **HTTP read timeout post-commit**?
3. If an SFTP host key changes unexpectedly, what must happen before updating `known_hosts`?
4. When an SFTP poller reconnects, why shouldn't you bulk-reset accept-once metadata?
5. Why can't an in-memory `QueueChannel` replace durable JMS/RabbitMQ queues?
6. What ACK risk arises when a JMS listener returns immediately after pushing to `ExecutorChannel`?
7. Does a RabbitMQ publisher confirm prove the downstream DB committed?
8. Can high Kafka lag on one partition be solved solely by adding consumers?
9. If a Kafka offset committed while the DB lacks the result, what procedure is required?
10. When a database pool is exhausted, what happens if you crank up retries?
11. Why do DLQ/replays require business keys and explicit owners?
12. What state should mark a sent message whose reply was lost?
13. Does an `OPEN` circuit breaker automatically save messages from being lost?
14. During high backlogs, should you focus on received or committed throughput?
15. What conditions must hold before declaring **business recovered**?

**Hints:** (1) lost connectivity/filter/handler; (2) one never connected while the other may have executed remotely; (3) verify out-of-band via independent channel; (4) duplicate risk; (5) lacks broker durability/redelivery; (6) ack before business commit; (7) no; (8) no—inspect partition/keys/sink; (9) reconciliation and approved replay; (10) worsens congestion; (11) prevent duplicate effects and poison loops; (12) `UNKNOWN`; (13) no; (14) committed throughput alongside backlog age; (15) canary, forward progress, SLOs, and verified correctness.

### 25.5. Conclusion

**An external disconnection runbook** is far more than a reconnect procedure. In Spring Integration Adapters, failures can start at **File/SFTP `MessageSource`s, HTTP gateways, JMS/AMQP listeners, Kafka consumer groups, or JDBC connection pools**, then ripple across `MessageChannel`, handlers, retries, transactions, DLQs, and target systems.

To operate safely, follow **detect → pinpoint → contain → fix root cause → canary → controlled backlog drain → reconcile → handover/postmortem**. Distinguish **received, sent, processed, committed, and acked**, because gaps between them cause data loss or duplicates even after links come back up.

**Final principle:** *Restoring the connection is only step one; true production recovery is proven only when business flows advance cleanly, incident-window data is reconciled, and every retry/replay is explainable, verifiable, and risk-controlled.*
