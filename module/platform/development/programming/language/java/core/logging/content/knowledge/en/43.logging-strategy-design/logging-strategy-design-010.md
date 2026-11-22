# Recording Decisions — Designing a Logging Strategy for Java

## 1. What Is Recording Decisions?

When designing logging for a Java application, the development team must choose **which events to log, which levels to use, what format to store, where to route them, who has access, how long to retain them, and how to handle logging system failures**. If you only change code or configuration without recording the reasons, a few months later it becomes hard to explain why the API logs `ERROR` at the error handler instead of in the service, why some `DEBUG` logs are sampled, or why audit logs have a separate storage repository.

**Recording decisions** means creating structured documentation to preserve **the context, considered options, approved choice, rationale, consequences, owner, and verification evidence**. A common practice in software design is the **Architecture Decision Record (ADR)**. Multiple ADRs are compiled into a **decision register / decision log**, helping new team members and operations teams understand the history of choices.

Example:

~~~text
ID: LOG-001
Title: Log terminal ERROR only at the HTTP exception boundary
Status: ACCEPTED
Owner: API Platform
Context: The same SQLException is logged at repository, service, and controller
Decision: Intermediate layers preserve the cause; do not log and rethrow
Rationale: Avoid reporting three errors for a single failed request
Consequences: Error boundary must retain requestId and root cause
Acceptance: One failed request produces one terminal ERROR event
Review trigger: Changes to error handling or async architecture
~~~

This is a **design decision**, not a per-request log line. It can be stored as Markdown in version control. When a request actually runs, the application can emit an `ERROR` event carrying `eventCode`, `requestId`, and `Throwable`, without writing the entire ADR rationale into the log.

**Goal:** logging decisions must be **explainable, reviewable, implementable, testable, and replaceable** when technical or business conditions change.

## 2. Distinguishing Decision Records, Runtime Events, Audit, and Change Records

These four record types serve different purposes:

| Type | Question Answered | Example | Where Stored |
| --- | --- | --- | --- |
| **ADR** | Why did the team choose this logging strategy? | LOG-001: Log ERROR once at boundary | Technical documentation repo |
| **Runtime decision log** | Which branch handled this request? | ruleId=RISK_CHECK, outcome=DENY | Structured logs |
| **Security/audit trail** | Who performed or was denied an action requiring evidence? | Actor modified role | Audit channel with dedicated policy |
| **Change/incident record** | Who deployed, changed config, rolled back, and what was the outcome? | Switched to parser v2, rolled back due to schema conflict | Change ticket / runbook |

An ADR does not replace regulatory audit logs; an audit record does not fully explain why Logback, retention, or a schema was chosen. Likewise, runtime logs should not be used as an ADR repository: logs can be rotated/deleted according to retention and usually contain very high volumes of event data.

The proper relationship:

~~~text
Requirements + SLO + risks + security + budget
                    |
                    v
              Propose ADR
                    |
      review, compare options, approve
                    |
                    v
          Code / config / runbook
                    |
                    v
       Actual logs + metrics + traces
                    |
                    v
        Tests, monitoring, evidence
                    |
            context changed?
                    |
                    v
          New ADR supersedes old
~~~

As a result, an operator can trace back from a rule in Logback to the ADR and understand why it was designed that way, instead of guessing.

## 3. What Happens If Decisions Are Not Recorded?

- **Level drift:** new developers turn every exception into `ERROR` because they do not know the team previously agreed on `WARN` for successful recovery fallbacks.
- **Duplicate logs:** repository logs and throws, service logs and throws, error handler logs the same error again; dashboards count one failure as three.
- **Schema drift:** Logback changes `PatternLayout`, while the collector still runs the old Grok pattern, losing `requestId` or misparsing timestamps.
- **PII leakage:** someone adds the raw request body to `DEBUG` without knowing the policy forbids tokens/Cookies.
- **Retention conflict:** reducing `totalSizeCap` to save storage accidentally purges logs that still need to be preserved.
- **Hard to switch backends:** not recording why Log4j 2 or a JSON encoder was chosen leads to switching tools without knowing compatibility criteria.
- **Unclear accountability:** who approved fail-open, fail-closed, audit routing, and access permissions?
- **Lack of verification:** the team has a doc saying "every request must have a traceId" but never tests async tasks or error responses.
- **Not knowing when to revisit:** production volume grows many times over while sampling/retention remain based on old assumptions.
- **Repeated incidents:** lessons from previous incident responses are not turned into decisions and regression tests.

Recording decisions does not make logging automatically correct. It **clarifies what needs to be tested, what is allowed to change, and which risks must be accepted**.

## 4. When Does a Logging Choice Need Its Own ADR?

You do not need an ADR for every `log.info(...)` call. Record one when the decision:

1. Affects multiple services/teams or changes contracts with collectors, alerts, dashboards, and support.
2. Has multiple reasonable options with significant trade-offs.
3. Involves security, PII, audit, retention, legal hold, or data deletion rights.
4. Incurs significant operational cost or makes ingested data hard to roll back.
5. Changes the semantics of `eventCode`, severity, `traceId`, sampling, or log loss.
6. Introduces a new technology/backend or a provider dependency that is hard to replace.
7. Could make someone ask "why was it chosen this way?" months later.

Examples that **should be considered for an ADR**: choosing JSON Lines over text, choosing a separate audit channel, log loss policy when the queue is full, changing retention across the entire cluster. Examples that **may only need code review / config comments**: fixing a typo in a message, adding temporary `DEBUG` under an existing policy, renaming a local variable.

**Special case:** legal/security decisions may require separate approval even for small code changes. Do not use "few lines of code" as a reason to skip review.

Keep ADRs **short and focused on a single significant decision**. If one file simultaneously chooses the backend, sets retention, decides PII rules, and handles full queues, reviewing and superseding individual parts becomes very difficult.

## 5. Key Decisions in a Logging Strategy

| Topic | Question to Finalize | How to Verify |
| --- | --- | --- |
| **Event taxonomy** | Which events to log, and for what purpose? | Event catalog, fixtures |
| **Severity** | When to use INFO/WARN/ERROR? | Unit/integration tests |
| **Exception ownership** | Which layer logs the final error? | Count LogEvents, check cause |
| **Structured logging** | JSON or text? Schema and field types? | Parser/golden tests |
| **Correlation** | Where is requestId/traceId generated, how is it propagated? | HTTP + async tests |
| **Routing** | Which console, file, search, or audit sink? | Appender and collector tests |
| **Sampling/filtering** | Which events are sampled or dropped? | Volume, consistency tests |
| **Reliability** | When queue is full or sink is down: drop, retry, or block? | Failure injection |
| **Retention** | How long to keep in each store? Under what conditions to delete? | Lifecycle readback |
| **Privacy/security** | Which fields must not be logged, who can read them? | PII scanning, IAM |
| **Index/alerts** | Which backend mappings and alert thresholds? | Query/dashboard tests |
| **Ownership/operations** | Who approves, monitors, and rolls back? | Change record/runbook |
| **Cost/capacity** | Bytes/day, throughput, CPU, index replication? | Benchmarks, budgets |

Decisions about `DEBUG` sampling and security audit usually **should not be merged into the same rule**, because their retention and completeness requirements differ.

## 6. Minimum Fields of a Logging ADR

A good decision record needs:

- **ID and conclusion title:** e.g., `LOG-007 — Use JSON Lines for application logs`; avoid titles like "Logging research".
- **Status:** `PROPOSED`, `ACCEPTED`, `SUPERSEDED`, or a status agreed upon by the team.
- **Owner, reviewers, date:** who proposed it, who approved it, and when the decision was made.
- **Scope:** services, environments, log classes, sinks, affected parties, and exclusions.
- **Context:** the problem, current state data, incidents/budget/requirements.
- **Drivers/constraints:** performance, security, cost, legal, compatibility, recovery.
- **Alternatives:** genuinely viable options with pros/cons for each.
- **Decision:** a clear, actionable statement that can be implemented.
- **Rationale:** why the chosen option fits the context better than the alternatives.
- **Consequences:** benefits, drawbacks, costs, and unresolved risks.
- **Implementation references:** PR/config/schema/test/dashboard/runbook.
- **Acceptance criteria:** measurable conditions to confirm proper implementation.
- **Rollout/rollback:** canary, migration, how to revert if criteria are not met.
- **Review triggers:** incidents, legal changes, cost, schema, or topology changes.
- **Supersedes/superseded-by:** links if the decision replaces a previous one.

According to ADR practices from AWS, GOV.UK, and many architecture teams, **context, decision, and consequences** are the minimum core. The additional fields make logging decisions easier to operationalize because many components sit outside Java code.

**Do not let an ADR become a list of slogans.** "Logging must be secure" does not state what is forbidden, where redaction happens, or how to verify it.

## 7. Complete Markdown ADR Template

The illustrative example uses hypothetical data. It can be placed in `docs/adr/LOG-007-json-lines.md` of a project; the actual path should be determined by the team.

~~~markdown
# LOG-007 — Use JSON Lines for application logs

- Status: ACCEPTED
- Date: 2026-11-10
- Owner: Platform Observability
- Reviewers: API team, Security
- Scope: Java HTTP services; excludes audit sink
- Supersedes: None

## Context
Current text patterns differ across services.
Parsers at the collector frequently miss requestId and exceptions.
Some messages contain newlines and delimiter characters.

## Decision drivers
- Must include timestamp, service, severity, eventCode.
- Preserve requestId/traceId when context exists.
- Do not output password, token, Cookie, or raw request body.
- Service-by-service rollout with rollback support.

## Alternatives
A. Keep text + Grok at the collector.
B. Output JSON Lines with a versioned schema at the source.
C. Send binary events via a dedicated agent.

## Decision
Choose B for application logs.
Each logical event becomes one JSON object on a single line.
Use a JSON serializer to escape messages and exceptions.
Maintain a versioned schema contract; do not apply to the audit sink.

## Rationale
Reduces dependence on text positions and regex,
makes typed-field queries easier, and enables schema drift detection.

## Consequences
+ Easy to query by requestId, traceId, eventCode.
+ Fewer multiline errors when exceptions are escaped.
- Adds encoder/schema governance overhead.
- Collector and dashboards require migration.
- Requires PII and dynamic field controls.

## Acceptance
- Golden fixtures parse cleanly, one event per line.
- No secrets found in test output.
- Querying by requestId finds the event in the backend.
- Volume, latency, and parser errors are within approved thresholds.

## Rollout and rollback
Canary on one service, compare against baseline.
Roll back encoder/pipeline if criteria are not met.
Do not delete old data before sign-off.

## Review triggers
Backend change, parser incident, privacy policy update,
or ingest cost exceeding budget limits.
~~~

**Important:** The template is only a **hypothetical decision**; it does not claim the project has chosen JSON. Acceptance items are testing targets, **not measured results**. Implementers must distinguish between decision status and implementation status.

A good ADR can fit in a short Markdown file; detailed data and measurements can link to other documents rather than stuffing all log outputs into the ADR.

## 8. Lifecycle: Propose, Accept, Supersede

~~~text
New need / incident / change request
               |
               v
       DRAFT or PROPOSED
               |
     review & alternatives
               |
               v
            ACCEPTED
               |
     code/config/test, rollout
               |
            VERIFIED
               |
  conditions change / new evidence
               |
               v
     New ADR supersedes old ADR
               |
       old record: SUPERSEDED
~~~

Depending on convention, **VERIFIED** may be a separate implementation status rather than an ADR status. It is better to separate:

- **Decision status:** `PROPOSED`, `ACCEPTED`, `SUPERSEDED`.
- **Implementation status:** `NOT_STARTED`, `IN_PROGRESS`, `ROLLED_OUT`, `VERIFIED`, `ROLLED_BACK`.

Do not conflate `ACCEPTED` with `VERIFIED`. An approved ADR that has not been rolled out is **not** an active policy enforced in production.

**Preserving history:** When changing a meaningful choice, create a new ADR and link the supersession instead of silently rewriting the rationale of an accepted ADR. Fixing typos/URLs may be allowed by documentation convention, but changing a position must leave a historical trail.

For a choice that is not approved, keep its status as `PROPOSED` or `REJECTED` per process; do not treat code under a proposed PR as a production rule just because the pull request exists.

## 9. Decision Authority and Accountability

| Role | What to Review |
| --- | --- |
| Application owner | What needs to be logged for debugging and business support? |
| Platform/Observability | Schema, ingestion, index, query, quota, cost |
| SRE/Operations | Queue, backpressure, failure policy, incident runbook |
| Security | Secrets/PII, audit, tamper resistance, access control |
| Compliance/Legal | Retention, legal hold, data deletion rights under applicable law |
| Support | Is there a way to get requestId and look up events without exposing data? |
| Data/Analytics | Field types, consistency, and reliability of metrics |

An ADR should have an **accountable owner**, impact-appropriate reviewers, and a mechanism to resolve disagreements. Not every team needs to approve every minor change, but **changing audit retention or log read permissions** requires the appropriate authorized roles.

Do not use informal approvals like "discussed in chat" without a conclusion to replace a formal decision status. When formal approval is required, store a reference to the change/security review in the appropriate system.

## 10. Example Decision: Log Errors Once at the Boundary

A common anti-pattern:

~~~text
Repository: log.error(SQLException), throw
Service:    log.error(OrderCreationException), throw
Controller: log.error("request failed"), throw
Handler:    log.error("HTTP 500", exception)
~~~

A single logical failure is logged multiple times. Decision `LOG-001` could choose:

~~~text
Scope: Java HTTP services
Choice:
  - Repository/service propagate exceptions and preserve root cause.
  - Only the terminal boundary logs ERROR when an operation truly fails.
  - Expected 400 validations do not log full ERROR stack traces by default.
  - Successful fallbacks use a metric/WARN if degradation is significant.
Acceptance:
  - One failed request produces exactly one terminal ERROR event.
  - Includes requestId/eventCode and Throwable cause.
  - Two independent requests are still counted as two failures.
Exceptions:
  - Security/audit events serve a different purpose and must still be stored per policy.
~~~

The alternative is logging at multiple layers to make call-sites easier to spot. **Trade-off:** choosing the terminal boundary avoids noise but requires proper exception context propagation; if a middle layer swallows the cause, information is lost. Therefore, the ADR must be paired with tests that verify cause chain preservation and correlation context.

Do not treat **one multi-line stack trace** as multiple logging events. Do not suppress `ERROR` using regex matching on identical messages, because two different requests can have the same root cause.

## 11. Example Decision: Schema and Correlation

An illustrative logging schema:

~~~json
{
  "timestamp": "2026-11-10T03:30:05Z",
  "level": "ERROR",
  "service": "order-service",
  "eventCode": "ORDER_FAILED",
  "requestId": "req-42",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "outcome": "FAILED",
  "errorCode": "DEPENDENCY_UNAVAILABLE"
}
~~~

A schema ADR must decide:

1. Whether `timestamp` uses an offset/UTC; how event time differs from observed time.
2. Whether to preserve the original `severityText` (JUL `SEVERE`, Logback `ERROR`) and map to a standard `severityNumber`.
3. Whether field names and types are consistent across services.
4. Whether `requestId` is generated at the gateway/app, and whether client-sent headers are accepted.
5. How `traceId`/`spanId` are propagated via tracing instrumentation and W3C context.
6. Whether `eventCode` has a registry or uses arbitrary messages.
7. How exceptions/stack traces are encoded and protected.
8. Whether there is a `schemaVersion` and a migration/compatibility policy.
9. Which fields must be redacted or must not be ingested.
10. Who owns golden fixtures for collectors and dashboards.

The **OpenTelemetry Logs Data Model** defines `Timestamp`, `ObservedTimestamp`, `SeverityText`, `SeverityNumber`, `Body`, `Resource`, `Attributes`, and `TraceId`/`SpanId`. It can be used as a semantic mapping design reference, but do not assume a custom JSON with similar field names is a full standard OpenTelemetry `LogRecord`.

When an ADR states "every request must be searchable by requestId", verify end-to-end: HTTP response → Java MDC → Logback/Log4j 2 output → shipper/collector → backend query. Seeing MDC only in the controller is not enough.

## 12. Example Decision: Privacy, Retention, and Audit

Security/logging decisions often involve two hard-to-balance sets of constraints:

- **Need sufficient evidence:** investigation, attack detection, auditing, debugging, SLA.
- **Avoid over-retention:** personal data, tokens, access permissions, processing purpose, retention period, cost.

An ADR/retention policy should state:

- Log classes: debug, application, access, security, audit.
- Data to exclude at the source: passwords, access tokens, Cookies, raw payment data, secret keys.
- Conditionally allowed fields: `actorRef`, IP, `requestId`, route template; must have a stated purpose and access control.
- Separate or shared audit channel? If separate, why and how is routing verified?
- Retention periods by data type and applicable basis; when the age clock starts.
- Actual destinations: local file, stdout/container, collector queue, search index, object archive, snapshots, backups, exports.
- Whether valid **legal holds** exist; who places/lifts them and whether there is a review schedule.
- How data deletion/de-identification affects replicas and restores.
- Rules when storage is full: tiering/alerting, never silently deleting mandatory evidence.
- How enforcement is proven, not just storing a YAML policy file.

**Do not write in an ADR "retain for 90 days because it is standard" without justification.** Retention is a decision driven by law, contracts, and organizational needs; illustrative day counts carry no legal weight. Calling every event "audit" does not exempt all PII from deletion obligations either.

If there is security/PII risk, require review by the authorized teams and verifiable tests: synthetic secrets do not appear in logs, audit events reach the right sink, lifecycle policies run everywhere, and backup restores do not resurrect legitimately deleted data.

## 13. Example Decision: Sampling, Cost, and Durability

A decision saying "sample 10% DEBUG" is too brief, because it does not specify:

- Is that **10% of events**, **10% of requests**, or trace-level sampling?
- Will random per-line sampling break context within a single request?
- When `DEBUG` includes an important exception, should it be dropped?
- Does sampling apply to security/audit logs, and on what basis?
- Is before/after ingest cost estimated in bytes/day or only line count?
- When an incident requires higher diagnostics, how is it enabled, for how long, and who approves?
- Does it affect dashboards or alerts derived from logs?

Similarly, decisions to use `AsyncAppender` or queues:

| Question | Example Criteria to Finalize |
| --- | --- |
| When queue is full | Drop DEBUG, block producer, or spill-to-disk? |
| When collector is down | Retry for how long, where is the bounded buffer? |
| On JVM crash | Which logs can be lost in the memory queue? |
| On shutdown | Flush timeout and how unACKed data is handled? |
| When audit sink fails | Fail-open or fail-closed per policy? |
| Under backpressure | Request latency and resource limits? |

**Do not claim exactly-once / no loss** if the system only uses an asynchronous in-memory queue. Durability goals must define actual ACK boundaries and failure semantics; legal/audit requirements may demand a different path from application debug logs.

An ADR should record **baseline measurements** and approved limits; do not invent target numbers. If measurements are missing, keep it `PROPOSED` with a test plan rather than approving on gut feeling.

## 14. From ADR to Implementation and Verification

An ADR does not change code on its own. There should be a traceability path:

~~~text
ADR LOG-001: single terminal ERROR
       |
       +--> Service: preserve cause, no catch-log-rethrow
       +--> HTTP error handler: one ERROR with requestId/eventCode
       +--> Logback encoder: includes throwable and MDC
       +--> Integration test: logCount=1, root cause preserved
       +--> Metrics/alert: count logical failures, not stack lines
       +--> Runbook: query by requestId and eventCode
~~~

Example decision register:

| ID | Summary | Decision status | Implementation status | Evidence |
| --- | --- | --- | --- | --- |
| LOG-001 | ERROR only at boundary | ACCEPTED | VERIFIED | One-error test |
| LOG-002 | No unnecessary secrets/PII | ACCEPTED | VERIFIED | Redaction test |
| LOG-003 | DEBUG sampling | PROPOSED | NOT_STARTED | Design draft |
| LOG-007 | JSON Lines application logs | ACCEPTED | ROLLOUT | PR, fixtures |
| LOG-009 | Separate audit pipeline | ACCEPTED | VERIFIED | Routing/ACL test |

These statuses and IDs are **hypothetical data** and do not claim any repository has implemented them. Links to PRs, configs, tests, and dashboards must be real links in production.

There is no need to force every runtime `LogEvent` to carry an ADR ID: `decisionId` can be linked from release notes/`schemaVersion`/config and the decision register. Attach an ADR ID to an event only when useful for traceability and without unreasonable overhead.

## 15. Standalone Java 17+: Decision Catalog and Logger

The following example illustrates two related but distinct tasks:

1. A small catalog holding three decisions with ID, status, owner, choice, rationale, and test.
2. Runtime only applies an **ACCEPTED** decision when emitting an `ERROR` event at the boundary. A `PROPOSED` decision is rejected.

The code uses **JDK 17 `java.util.logging`**, requiring no external libraries. An in-memory `Handler` counts `LogRecord` instances so stack trace line counts are not confused with event counts. This is **not a production ADR approval system**; real documents should live outside the code in a review/version-control repository.

Create the file **LoggingDecisionDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LoggingDecisionDemo {
    record Decision(String id, String status, String owner,
                    String choice, String rationale, String test) {}

    static final List<Decision> CATALOG = List.of(
        new Decision("LOG-001", "ACCEPTED", "platform",
            "BOUNDARY_ERROR_ONCE", "Avoid duplicate errors", "log-once-test"),
        new Decision("LOG-002", "ACCEPTED", "security",
            "REDACT_SECRET", "Minimize sensitive data", "pii-test"),
        new Decision("LOG-003", "PROPOSED", "observability",
            "SAMPLE_DEBUG", "Limit log volume", "sampling-test")
    );

    static final Logger LOG = Logger.getLogger("demo.strategy");
    static final List<LogRecord> RECORDS = new ArrayList<>();

    static Decision accepted(String id) {
        return CATALOG.stream()
            .filter(d -> d.id().equals(id)
                      && d.status().equals("ACCEPTED"))
            .findFirst()
            .orElseThrow(() ->
                new IllegalStateException("Decision not accepted"));
    }

    static void logTerminalFailure(String requestId, String eventCode) {
        Decision decision = accepted("LOG-001");

        LOG.log(Level.SEVERE, "strategyId=" + decision.id()
            + " requestId=" + requestId
            + " eventCode=" + eventCode + " outcome=FAILED",
            new IllegalStateException("dependency unavailable"));
    }

    public static void main(String[] args) {
        Set<String> ids = new HashSet<>();

        for (Decision d : CATALOG) {
            if (!ids.add(d.id()) || d.owner().isBlank()
                    || d.rationale().isBlank() || d.test().isBlank()) {
                throw new IllegalStateException("Invalid decision record");
            }

            System.out.println("decision " + d.id() + " status="
                + d.status() + " owner=" + d.owner()
                + " choice=" + d.choice());
        }

        System.out.println("accepted=" + CATALOG.stream()
            .filter(d -> d.status().equals("ACCEPTED")).count()
            + " proposed=" + CATALOG.stream()
            .filter(d -> d.status().equals("PROPOSED")).count());

        boolean proposedBlocked = false;
        try {
            accepted("LOG-003");
        } catch (IllegalStateException expected) {
            proposedBlocked = true;
        }
        System.out.println("proposedBlocked=" + proposedBlocked);

        Handler memory = new Handler() {
            { setLevel(Level.ALL); }

            @Override
            public void publish(LogRecord event) {
                if (isLoggable(event)) RECORDS.add(event);
            }

            @Override public void flush() {}
            @Override public void close() {}
        };

        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);
        LOG.addHandler(memory);

        try {
            String sensitive = "secret-demo-value";
            logTerminalFailure("req-42", "ORDER_FAILED");

            LogRecord event = RECORDS.get(0);
            System.out.println("loggedEvents=" + RECORDS.size());
            System.out.println("level=" + event.getLevel());
            System.out.println("message=" + event.getMessage());
            System.out.println("hasThrowable="
                    + (event.getThrown() != null));
            System.out.println("containsSecret="
                    + event.getMessage().contains(sensitive));
        } finally {
            LOG.removeHandler(memory);
            memory.close();
        }
    }
}
~~~

Compile and run with JDK 17:

~~~bash
javac LoggingDecisionDemo.java
java LoggingDecisionDemo
~~~

**Verified stdout:**

~~~text
decision LOG-001 status=ACCEPTED owner=platform choice=BOUNDARY_ERROR_ONCE
decision LOG-002 status=ACCEPTED owner=security choice=REDACT_SECRET
decision LOG-003 status=PROPOSED owner=observability choice=SAMPLE_DEBUG
accepted=2 proposed=1
proposedBlocked=true
loggedEvents=1
level=SEVERE
message=strategyId=LOG-001 requestId=req-42 eventCode=ORDER_FAILED outcome=FAILED
hasThrowable=true
containsSecret=false
~~~

### How to Read the Output

- `CATALOG` contains two `ACCEPTED` and one `PROPOSED` decision; `accepted("LOG-003")` does not return a valid decision, so `proposedBlocked=true`.
- `HashSet` checks that IDs are unique and that `owner`/`rationale`/`test` are non-blank. This does not replace real approval.
- `logTerminalFailure` only uses `LOG-001` and emits one JUL `LogRecord` with `strategyId`, `requestId`, `eventCode`, and `outcome`.
- `getThrown()!=null` proves the event has a `Throwable`; it **does not prove the `Throwable` has a nested `getCause()`**.
- `containsSecret=false` only checks that the **example message** does not contain the hypothetical string; it does not prove every exception, appender, and sink is safely redacted.
- `setUseParentHandlers(false)` prevents events from propagating to parent loggers in the test; actual production appender output may differ.

**Limitations:** `List`/`ArrayList` is not a durable ADR store or thread-safe across many requests. Use real logging classes and collectors, and test async, recovery, security, and output sinks. One code path calling `accepted()` does not automatically prevent other modules from using unapproved configs; review/deployment gates and system-wide tests are needed.

## 16. Using SLF4J, Logback, and Log4j 2

In a Spring Boot application with SLF4J 2.x, a terminal error can use the fluent API:

~~~java
// Fragment inside a class that has an SLF4J logger and defined variables.
log.atError()
   .addKeyValue("eventCode", "ORDER_FAILED")
   .addKeyValue("requestId", requestId)
   .addKeyValue("outcome", "FAILED")
   .setCause(exception)
   .log("Create order failed");
~~~

This is **not a standalone program**: it requires SLF4J dependencies, a backend, and defined `requestId` and `exception` variables. `addKeyValue` attaches metadata to the logging event; the backend/encoder must be configured appropriately to emit it as structured fields. Do not assume Logback/Log4j 2 is storing JSON just because the fluent API uses key-values.

Example **Logback text `PatternLayout`** with MDC:

~~~xml
<configuration>
  <appender name="CONSOLE"
      class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>%d{ISO8601} %-5level requestId=%X{requestId:-} %logger - %msg%n%ex{full}</pattern>
    </encoder>
  </appender>
  <root level="INFO">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
~~~

This is a text pattern, **not JSON Lines**. If the ADR chooses JSON, you must configure a compatible JSON encoder/layout and test the collector. Log4j 2 uses `ThreadContext` and `PatternLayout` / JSON Template Layout according to its own dependency/version; do not copy Logback XML classes into Log4j 2.

**MDC also needs a lifecycle:** set context early, clear it on time, and propagate across async/thread pools/Reactor per framework. You cannot fix missing `requestId` bugs in async code by writing an ADR without fixing the code and tests.

## 17. Recording Runtime Business Rule Decisions

Sometimes "recording decisions" also means the system must log **business processing decisions**: a rule engine allowing/denying, a feature flag selecting a branch, a fallback switching providers, or access being granted/denied. This is a **runtime decision event**, related to but distinct from a logging design ADR.

Example structured event:

~~~json
{
  "timestamp": "2026-11-10T03:30:05Z",
  "eventCode": "RISK_RULE_EVALUATED",
  "requestId": "req-42",
  "ruleId": "RISK_CHECK",
  "policyVersion": "v3",
  "outcome": "DENY",
  "reasonCode": "RULE_THRESHOLD_EXCEEDED"
}
~~~

The ADR decides **why** the runtime event must include `ruleId`, `policyVersion`, `outcome`, and `reasonCode`; the event itself proves **which branch a specific request took**.

Key considerations:

- Log a stable `reasonCode` instead of raw input containing PII.
- Do not expose secret thresholds, passwords, or security policy details to unauthorized users.
- Audit/security events may need preservation even when application logging is sampled.
- When retries or multiple rules run, distinguish per-rule evaluation from the final business outcome.
- Log the `policyVersion` actually in effect, not just the latest version in documentation.
- A runtime event needs the right `requestId`/`traceId` from context when available; do not use this ID in place of authentication.
- Do not put the entire ADR rationale into every log line, which bloats storage and leaks internal information.

To answer "**why did the architecture choose to log this field?**", check the ADR. To answer "**why was this request denied?**", query runtime/audit events with appropriate permissions.

## 18. Linking ADRs to Testing and Monitoring

| Decision | Required Testing / Monitoring | Common Pitfalls |
| --- | --- | --- |
| LOG-001 Single ERROR | One failed request creates one terminal ERROR with cause | Counting stacktrace lines as events |
| JSON schema v2 | Golden fixtures, types/escaping, index readback | Valid JSON but wrong field names |
| Response correlation | Response header requestId matches logs, no async mix-up | MDC leaking across thread context |
| Secret redaction | Synthetic secrets absent from output sinks | Exception message still leaks token |
| DEBUG sampling | Distribution/volume per rule, no audit loss | Per-line sampling breaks traces |
| Security audit routing | Events reach right sink with proper read permissions | Appender additivity leaks audit to debug |
| Retention | Retained for full term and deleted on schedule per policy | Deleting local files only, ignoring index/backups |
| Full queue policy | Failure injection when collector is slow/offline | Silent drops with no metric |
| Parser migration | Old/new fixtures, data contract, backend queries | Old regex misparses new logs |
| Runtime decision event | Accurate ruleId/version/outcome, no raw PII | Accidentally logging actor/user input |

**Test at the right layer:** unit tests verify event logic, integration tests verify Logback/Log4j 2, pipeline tests verify collector/index, and operational tests verify retention/restore and runbooks.

Acceptance of "one `ERROR` per failed request" does not mean **security audit logs cannot be written**. Signals with different purposes can coexist; tests must distinguish event types.

Beyond tests, maintain **drift monitoring**: log volume/day, parser error rate, missing `requestId`, audit routing errors, retained bytes/age, full queue/drop counts, and incident lookup time. If an ADR assumed 1 GB/day and production reaches 30 GB/day, trigger a review instead of silently editing the number in the document.

## 19. Rollout, Rollback, and Evidence of Applied Decisions

A practical workflow:

1. Gather incidents or requirements; measure baselines for log volume, parser errors, time-to-diagnose, and cost.
2. Write the ADR with alternatives and known risks.
3. Review with application, platform, SRE, and security/compliance based on impact.
4. `ACCEPTED` once approved with acceptance criteria; this does not mean deployed.
5. Open PRs changing code/config, linked to the ADR.
6. Test event schema, failure paths, PII, correlation, async, and routing.
7. Canary by service/environment, monitor metrics, and compare against baseline.
8. Verify at the **final destination** (index/backend), not just console lines.
9. If criteria fail, roll back encoder/config/routing per plan; handle already-ingested data if schemas conflict.
10. Record evidence and implementation status; update runbooks/dashboards.
11. When risks or conditions change, create a new ADR to supersede.

**Paths to PRs/tests/configs must be real paths** in the project. Do not fabricate "evidence" by writing `DONE` in an ADR before testing.

Some decisions are hard to roll back: changing retention may have already deleted data; changing schemas has already created documents; modifying audit routing may leave gaps. For these, require separate migration and backup/legal reviews—do not assume rolling back code automatically restores lost data.

## 20. When to Re-evaluate a Decision

- An incident cannot locate logs by `requestId` or `traceId`.
- Major version upgrades of frameworks/backends: JUL, SLF4J, Logback, Log4j 2, Spring Boot.
- Changes to shippers, collectors, index templates, data streams, or schemas.
- Traffic growth causes full queues, collector event loss, or budget overruns.
- Secrets/PII discovered in logs or incorrect read permissions.
- Changes to retention, audit, or data deletion regulations/contracts.
- Adding Kafka, async jobs, microservices, tenants, or deployment regions.
- A sampling choice drops data needed for investigation.
- Team ownership changes, or actual implementation diverges from the ADR.
- Metrics hit agreed review thresholds (parser errors, missing fields, drop counts).

**Do not edit the historical rationale of an old ADR to "match the present".** Write a new ADR with the new context, explicitly state it supersedes the old record, detail migration consequences, and specify how to verify after the change.

A quality review must answer "do the original assumptions still hold?" rather than just adding a line saying "Reviewed on date ...".

## 21. Anti-Patterns When Recording Decisions

**Recording only the choice, not the rationale.** "Use Logback" does not explain why, whether Log4j 2/JUL were evaluated, the cost, or the ease of change.

**Missing owner or status.** A Markdown file without an approver or clear `PROPOSED` vs. `ACCEPTED` status easily creates shadow policies.

**`ACCEPTED` but not deployed.** Decision status and implementation status must be separated, backed by real tests and evidence.

**Rewriting an old ADR when changing direction.** Destroys history; supersede and link instead.

**Writing too many trivial ADRs.** The decision log becomes a list of config typos that nobody reads. Choose impactful decisions.

**Creating one giant ADR.** Hard to separately review privacy, retention, routing, and sampling; split by trade-off.

**Missing acceptance criteria.** "Log enough detail" or "no log loss" cannot be tested. Define concrete event fields, scope, drop semantics, and tests.

**Putting real PII/secrets in documents.** Git history persists even if lines are deleted later; use synthetic data and access controls.

**Assuming reading an ADR replaces code review.** Actual config, code, collectors, and policies must stay in sync.

**Disabling audit logs to reduce duplicates or volume.** Audit/security events are a different class from diagnostic stack traces; never disable them without evaluation.

**Changing code only, forgetting the pipeline.** The app emits JSON while the backend still parses old text; contract tests must reach the destination.

**Optimizing cost without considering retention/forensics.** Cutting logs is no excuse to delete mandatory evidence or retain PII too long.

**No review triggers.** A decision that makes sense at low traffic can fail when scale changes.

## 22. Exercise: Building a Decision Register for a Java API

A Java service exhibits these symptoms:

~~~text
- Text logs have different patterns across services.
- The same exception is logged as ERROR in both service and controller.
- Support cannot look up requestId from HTTP responses.
- DEBUG accounts for most of the log volume.
- Unclear where audit logs are stored and for how long.
- Collector occasionally overloads with no drop/retry policy.
~~~

How to proceed:

1. Split the problems into scoped decisions: error ownership, event schema/correlation, diagnostic volume, audit/retention, and reliability.
2. For each decision, measure a baseline if available; do not fabricate numbers in an ADR as production metrics.
3. List at least two viable options, including pros/cons, costs, and risks.
4. Identify owners/reviewers: API, Observability, Security/Compliance.
5. Write context, decision, rationale, consequences, tests, rollout, rollback, and review triggers.
6. Keep items awaiting approval as `PROPOSED`; do not treat them as deployed just because code is written.
7. Once `ACCEPTED`, link the ADR to the corresponding PRs, configs, and tests.
8. Canary with synthetic requests; measure `ERROR` count, parser correctness, log volume, missing `requestId`, and audit routing.
9. Record implementation status honestly based on evidence.
10. If a decision is no longer suitable, create a new ADR to supersede it instead of deleting history.

A new team member should be able to read the register and answer: **when do we log ERROR, why do we use this format, who approves retention, and how do we verify the system enforces it correctly**.

## 23. Checklist Before Closing a Logging ADR

- [ ] Has ID, clear title, scope, and owner.
- [ ] Records context, requirements, metrics, or assumptions.
- [ ] Includes real alternatives and both positive and negative trade-offs.
- [ ] Concrete, implementable, and verifiable decision.
- [ ] Approved by the right roles for security/privacy/retention when applicable.
- [ ] `PROPOSED`/`ACCEPTED`/`SUPERSEDED` clearly defined.
- [ ] Separates decision status from rollout/verification status.
- [ ] Links to real code/config/schema/tests/dashboards/runbooks.
- [ ] Has measurable acceptance criteria, not just slogans.
- [ ] Includes migration, canary, and rollback if changing multiple systems.
- [ ] No PII/secrets in the decision record.
- [ ] Evaluated audit, retention, legal hold, queue failure, and sampling.
- [ ] Has review triggers and a history-preserving supersession process.
- [ ] Decision register is maintained and matches the running system.

**Conclusion:** In **Logging Strategy Design**, "Recording Decisions" means preserving **why** logging choices were made and **how to verify them**. ADRs explain context, alternatives, decisions, rationale, consequences, and accountability; the decision register connects them to Java configuration, collectors, tests, and operations. Runtime logs remain the evidence of what happened, not a substitute for architecture decision documentation.

## 24. References

- [AWS Prescriptive Guidance — ADR process](https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/adr-process.html): context, decision, consequences, status, and decision log.
- [AWS Prescriptive Guidance — ADR FAQ](https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/faq.html): owner, review, and minimum contents.
- [GOV.UK — Documenting Architecture Decisions](https://gds-way.digital.cabinet-office.gov.uk/standards/architecture-decisions.html): version control and reasons for recording decisions.
- [Martin Fowler — Architecture Decision Record](https://martinfowler.com/bliki/ArchitectureDecisionRecord.html): short records, lifecycle, supersession.
- [Google Cloud — Architecture Decision Records](https://docs.cloud.google.com/architecture/architecture-decision-records): context, options, reasons, implementation consequences.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): event attributes, data to exclude, protection, and retention.
- [OpenTelemetry Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/): Timestamp, ObservedTimestamp, SeverityText/Number, Body, Resource, and Attributes.
- [SLF4J Manual](https://www.slf4j.org/manual.html): fluent API, key-value fields, and Throwable.
- [Logback Manual — Architecture](https://logback.qos.ch/manual/architecture.html): hierarchy, additivity, and backend layout.
- [Logback Manual — Layouts](https://logback.qos.ch/manual/layouts.html): MDC/pattern.
- [Apache Log4j 2 — Architecture](https://logging.apache.org/log4j/2.x/manual/architecture.html): LoggerConfig, routing, and Appenders.
- [Oracle Java SE 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): LogRecord and Throwable in the runnable example.
