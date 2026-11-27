# Correlating Logs Between Inbound and Outbound in Spring Integration Adapters

## 1. The Problem: Inbound Received It, Why Hasn't Outbound Reached the Target?

A Spring Integration flow can start from an **HTTP inbound gateway, File/SFTP inbound adapter, JMS/AMQP/Kafka listener, or JDBC polling**. Messages traverse **MessageChannels, filters, transformers, routers, and service activators**, ending at an **outbound adapter/gateway**. When a partner reports “we sent the data yet never received the outcome,” operations must answer:

- Did inbound actually create a Spring `Message<?>`, or did a failure happen before that?
- Which endpoints, router branches, and queued channels did the record pass through?
- How many outbound calls occurred? Were duplicates caused by retries or two distinct business events?
- Does a successful `send` mean the broker ACKed, HTTP replied, the database committed, or merely that the channel accepted dispatch?
- When a timeout occurred, did the remote system already perform the business action?
- Did the message change IDs across a transformer, splitter/aggregator, or process/broker boundary?
- Why are logs in the downstream consumer missing the producer's `traceId` or `correlationId`?

**Correlation logging** designs log events along an integration journey so they can be **searched and stitched together with context**, without printing entire payloads. It combines **stable correlation IDs, unambiguous processing milestones, structured logs, header propagation, tracing context, and destination confirmation outcomes**.

This lesson belongs to the **Observability** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The focus is linking signals across inbound/outbound adapters, gateways, pollers, and MessageChannels when exchanging data over **file, SFTP, HTTP, JMS, AMQP, Kafka, and databases**, while respecting **message contracts, errors, retries, and connection lifecycles**.

**Expected outcome:** you can design and test a logging schema that links event chains from ingress to egress, separates attempts from completions, handles context loss across async/brokers, and pairs logs with metrics/tracing to investigate without leaking sensitive data.

> **Principle:** Correlation logs aid investigation; they **do not by themselves prove exactly-once processing, transaction commits, or immutable audits**. When business confirmation is needed, inspect state at the source/target and the corresponding idempotency, ACK, transaction, or reconciliation mechanisms.

## 2. Six Types of Identifiers You Should Not Mix Up

| Identifier | Created By | Proper Scope | What It Does Not Guarantee |
|---|---|---|---|
| **Business ID** | Business system | One order, file/batch, payment, or transaction | Not always safe to log; may constitute PII |
| **Correlation reference** | Integration layer per contract | Links logs/checkpoints belonging to one request or message chain | Not proof an event committed |
| **Trace ID** | OpenTelemetry/Micrometer tracing or compatible system | One trace spanning spans and services when context propagates | Neither an idempotency key nor a business ID |
| **Span ID** | Tracing instrumentation | One specific operation within a trace | Not stable across retries/hops; does not replace correlation |
| **Spring Message ID** | Spring Messaging per message | One `Message<?>` instance inside a JVM/flow | Can change on message rebuild, split, or broker receipt |
| **Attempt/delivery ID** | Integration code or transport | One target call attempt or one broker delivery | Not a unique business event |

You may also need **broker identities** such as Kafka `topic/partition/offset`, JMS message ID, or RabbitMQ delivery tag; these carry **protocol-specific** semantics and do not automatically equal business IDs or Spring Message IDs.

### 2.1. Practical Identification Rules

1. **Correlation reference** should be an *opaque* value without personal info or secrets, kept stable across checkpoints of the same journey.
2. **Attempt ID** must differ per outbound/retry call so one logical call is not mistaken for multiple transactions.
3. **Business ID** is governed by data classification; it may stay inside the domain store with a surrogate reference used in logs.
4. **Trace ID/Span ID** are managed by the tracing library; never overwrite them manually to “match” `correlationId`.
5. **Message ID** locates a message locally; when building new messages or crossing processes, rely on intentionally propagated correlation IDs.
6. **Idempotency key** is an anti-duplication contract, never guessed from log IDs without explicit domain design.

## 3. The Inbound → Outbound Journey and Its Boundaries

~~~mermaid
flowchart LR
    EXT[HTTP / File / SFTP / JMS / AMQP / Kafka / DB] --> IN[Inbound Adapter / Gateway]
    IN --> C1[Input Channel]
    C1 --> VAL[Filter / Validation]
    VAL --> T[Transformer]
    T --> R[Router]
    R --> C2[Outbound Channel]
    C2 --> OUT[Outbound Adapter / Gateway]
    OUT --> DST[Broker / API / File / DB]
    IN -. correlation_ref .-> LOG[Structured Logs]
    VAL -. correlation_ref .-> LOG
    T -. correlation_ref .-> LOG
    OUT -. correlation_ref + attempt_ref .-> LOG
    DST -. ACK / outcome .-> RECON[External Confirmation]
    LOG --> INVEST[Investigation]
    RECON --> INVEST
~~~

### 3.1. Status Milestones Are Not Synonyms

| Milestone | Example Log | Exact Meaning |
|---|---|---|
| **SOURCE_OBSERVED** | Poller spots eligible file | Item exists at source; not necessarily a Spring Message yet |
| **INGRESS_ACCEPTED** | HTTP gateway/consumer admits message into flow | Message accepted at a defined boundary |
| **VALIDATED** | Filter/validator accepts | Passed a specific validation rule |
| **TRANSFORMED** | Transformer produces output payload | Transformation succeeded at that endpoint |
| **OUTBOUND_ATTEMPTED** | Call/publish/upload begins | Send attempted; target receipt not yet proven |
| **TRANSPORT_CONFIRMED** | Broker ACK or protocol response | Target confirmed at transport/HTTP layer |
| **BUSINESS_COMPLETED** | Audit/status at target system | Completed per business contract; not always synchronous |
| **TERMINAL_FAILED** | Retries exhausted / routed to DLQ per policy | Event cannot continue in current workflow |
| **UNKNOWN_OUTCOME** | Timeout with uncertain side effects | Needs readback/reconciliation; never auto-retry blindly |

A one-way Kafka flow may finish at `TRANSPORT_CONFIRMED` for the producer, while `BUSINESS_COMPLETED` appears only after a downstream consumer finishes processing.

## 4. Define the Correlation Logging Contract Upfront

Before writing the first log statement, answer:

- **What is the tracked unit?** An HTTP request, a file, a broker message, a post-splitter item, or a batch?
- **Where is correlation minted?** Ingress edge, poller, adapter, or gateway?
- **Which system owns this ID?** Client, integration service, or business domain?
- **How far must it propagate?** Within one `IntegrationFlow`, across a broker, or to the final service?
- **When is a new correlation minted?** New journey, child message, replay, or compensating workflow?
- **Do retries share correlation?** Usually keep the logical event's correlation while issuing a new attempt ID.
- **How is completion defined?** Adapter send, target ACK, processing commit, or final callback?
- **What data is safe to log?** Never rely on raw payloads, URIs, file paths, or arbitrary message headers.

### 4.1. Recommended Log Fields

| Field | Meaning | Usage |
|---|---|---|
| `event` | Milestone like `INGRESS_ACCEPTED`, `OUTBOUND_ATTEMPTED` | Finite code-defined enum |
| `flow` | Flow name like `order-http-kafka` | Stable logical ID, no personal data |
| `component` | Endpoint/channel at checkpoint | Application-assigned name |
| `correlation_ref` | Cross-checkpoint reference | Verified opaque ID |
| `trace_id` / `span_id` | Tracing context | Taken from standardized instrumentation |
| `local_message_ref` | Local Spring Message ID | Never assume cross-process stability |
| `attempt_ref` | Single transport/target call | Fresh ref per new attempt |
| `source_type` / `target_type` | File/SFTP/HTTP/JMS/AMQP/Kafka/DB | Finite taxonomy |
| `stage` / `outcome` | Business milestones and results | Never dump raw exception text |
| `error_class` | `NETWORK_TIMEOUT`, `INVALID_SCHEMA`… | Finite taxonomy |
| `schema_version` | Message contract version | System allowlist |
| `duration_ms` | Duration of a defined segment | Never confuse with end-to-end |
| `retry_index` | Attempt ordinal | Consistent 0- or 1-based per contract |
| `external_receipt_ref` | ACK/response/commit reference when available | Safely classified metadata |
| `service` / `instance` | Log emitter source | Managed technical reference |

Not every log needs every field. Maintain **consistent semantics** so on-call engineers can stitch events without relying on log arrival order in async systems.

## 5. Example Timeline Sharing Correlation

~~~json
{"time":"2026-11-23T08:00:00.020Z","event":"INGRESS_ACCEPTED","flow":"orders-http-kafka","component":"httpOrderInbound","correlation_ref":"corr-7f92","local_message_ref":"msg-a","outcome":"accepted"}
{"time":"2026-11-23T08:00:00.028Z","event":"VALIDATED","flow":"orders-http-kafka","component":"validateOrder","correlation_ref":"corr-7f92","outcome":"accepted"}
{"time":"2026-11-23T08:00:00.034Z","event":"OUTBOUND_ATTEMPTED","flow":"orders-http-kafka","component":"publishOrders","correlation_ref":"corr-7f92","attempt_ref":"attempt-01","target_type":"kafka"}
{"time":"2026-11-23T08:00:00.049Z","event":"TRANSPORT_CONFIRMED","flow":"orders-http-kafka","component":"publishOrders","correlation_ref":"corr-7f92","attempt_ref":"attempt-01","target_type":"kafka","outcome":"confirmed"}
{"time":"2026-11-23T08:00:00.190Z","event":"BUSINESS_COMPLETED","flow":"orders-consumer-db","component":"storeOrder","correlation_ref":"corr-7f92","local_message_ref":"msg-b","target_type":"database","outcome":"committed"}
~~~

These are **synthetic logs**, not default output from Spring Integration. The two message IDs `msg-a` and `msg-b` differ because service B creates a new Spring Message. `BUSINESS_COMPLETED` in B is emitted only when code truly knows the transaction committed per contract.

**Never rely solely on timestamp ordering across two machines:** clock skew, log buffering, batch exporters, and network delays can deliver logs to collectors out of order. Use trace span relationships, event IDs, sequence/attempts, and source–target state to establish causality.

## 6. Issuing, Accepting, and Validating Correlation References

### 6.1. Trusted vs. External Sources

An HTTP client may send `X-Correlation-ID`; a Kafka producer may set header `correlationId`. Copying that raw value straight into logs lets clients:

- Inject newlines for **log injection**.
- Stuff emails, account numbers, or tokens into the ID field.
- Reuse another event's ID intentionally to pollute searches.
- Send huge strings that inflate log sizes and collector costs.

**Recommendation:** at untrusted boundaries, issue a **fresh internal correlation reference**; if preserving a client request ID is required, validate it strictly, store it in a separate field per policy, and never use it as identity/authorization evidence. Between trusted services, propagate verified opaque correlations per contract.

### 6.2. Java Helper for Safe ID Issuance

~~~java
import java.util.UUID;
import java.util.regex.Pattern;

public final class CorrelationRefs {
    private static final Pattern SAFE =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    private CorrelationRefs() {}

    public static String issueInternal() {
        return "corr-" + UUID.randomUUID();
    }

    public static String acceptTrustedOrIssue(Object candidate) {
        if (candidate instanceof String value
                && SAFE.matcher(value).matches()) {
            return value;
        }
        return issueInternal();
    }
}
~~~

**Note:** regex checks **format** only, not source trustworthiness. Call `acceptTrustedOrIssue` only on headers from partners/transports governed by explicit trust and validation policies. On public HTTP ingress, call `issueInternal()` instead of using regex to trust client-supplied values.

### 6.3. Never Use Log IDs for Authorization

A `correlation_ref` can be guessed or spoofed if sent across a network. Never use it as a credential, authorization token, or proof of “message already validated.” Business actions must still enforce authentication, authorization, and schema validation.

## 7. MessageHeaders and Path Through an IntegrationFlow

Spring Integration builds on Spring Messaging: a `Message<?>` has a **payload** and **headers**. You can carry `correlationRef` as an application header inside a flow, provided you do not confuse it with framework headers for request/reply or splitters/aggregators.

### 7.1. Commonly Confused Headers

| Header / Concept | Purpose |
|---|---|
| `MessageHeaders.ID` | Identifier of the current message instance |
| `MessageHeaders.TIMESTAMP` | Timestamp when the framework built message headers |
| `correlationRef` (custom) | Cross-checkpoint log reference per application contract |
| Integration correlation/sequence headers | Supports grouping, splitter/aggregator, ordering per flow |
| `replyChannel` / `errorChannel` | Internal routing; may hold Java objects |
| Trace context headers | Carries tracing info per standard/instrumentation |
| Transport-specific headers | Kafka topic/offset, HTTP method, JMS message ID… |

**Never use the aggregator's correlation header as a default alias for overall log correlation.** An aggregator may overwrite it for grouping. Keep a namespaced custom `correlationRef` and track its relationship to group IDs separately.

### 7.2. Headers Can Be Lost When Constructing New Messages

~~~java
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;

public Message<String> normalize(Message<String> incoming) {
    String normalized = incoming.getPayload().trim();

    return MessageBuilder.withPayload(normalized)
            .copyHeaders(incoming.getHeaders())
            .build();
}
~~~

This example copies headers within the **same application flow** subject to header policy. It is not a recipe for copying all headers over HTTP/Kafka/JMS: internal headers like reply/error channels may be non-serializable or unsuitable for external systems. Verify builder/version and header semantics in your project.

### 7.3. Checkpoints for Measuring Header Propagation

1. Inbound adapter/gateway constructs the Spring Message.
2. Enricher or interceptor issues `correlationRef` if missing.
3. Filters/routers/transformers preserve the header per contract when creating new messages.
4. Executor/queue boundaries preserve message data, yet do not guarantee thread-local MDC.
5. Splitters/aggregators alter message lineage; track parent–child relationships.
6. Outbound header mappers select which headers may leave onto the network.
7. The remote consumer extracts mapped headers and constructs a new message.

## 8. Attaching Correlation at Ingress: How Early Is Reasonable?

Attach correlation **as early as possible once ingress establishes a trusted identity**. Waiting until a downstream transformer leaves pre-transformer parse failures without an ID to link.

### 8.1. HTTP Inbound

An HTTP filter or interceptor can issue an internal correlation before the Spring Integration gateway accepts the request. The gateway then places this reference into the message via mapping/enrichment. **Failures before the gateway** (authentication, payload too large, malformed URL) must be logged at the HTTP server layer since no Spring Message exists yet.

### 8.2. File/SFTP/JDBC Pollers

When a poller picks up an item, assign correlation when **the message is created/accepted**; to link back to the scan/poll run itself, use a separate `poll_ref`. One poll can emit many messages, so **poll ID does not replace message correlation**.

### 8.3. JMS/AMQP/Kafka Listeners

The adapter constructs a Spring Message from a transport record; it can read correlation from headers/broker properties if the source is verified. If no valid ID exists, mint an internal reference and record its association with broker identity (topic/offset, JMSMessageID, delivery metadata) in authorized logs.

### 8.4. Never Mint a Fresh Correlation at Every Endpoint

If a flow generates new IDs at the transformer, router, and outbound adapter, on-call sees three disconnected log clusters for one business event. Define **reuse rules** and mint new IDs only at designed logical boundaries, e.g., an independent child workflow carrying `parent_correlation_ref`.

## 9. Structured Logging: Safe Projections Instead of Printing Messages

Writing `log.info("Message={}", message)` can print payloads and headers, including tokens, cookies, file paths, and PII. For safe correlation logs, build a **fresh log record** using only classified fields.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.Message;

public final class IntegrationCheckpointLog {
    private static final Logger LOG =
            LoggerFactory.getLogger(IntegrationCheckpointLog.class);

    private IntegrationCheckpointLog() {}

    public static void received(Message<?> message) {
        Object candidate = message.getHeaders().get("correlationRef");
        String ref = candidate instanceof String s
                && s.matches("[A-Za-z0-9_-]{1,64}")
                ? s : "missing";

        LOG.info(
                "event=INGRESS_ACCEPTED flow=orders "
                + "component=ordersInbound correlation_ref={} "
                + "payload_kind={}",
                ref,
                classifyKind(message.getPayload())
        );
    }

    private static String classifyKind(Object payload) {
        if (payload instanceof byte[]) return "binary";
        if (payload instanceof String) return "text";
        return "object";
    }
}
~~~

This snippet is a **minimal safe projection**: it never stringifies payloads, never prints all headers, and never dumps raw exception messages. In production, issue correlations via trusted ingress middleware, use genuinely structured logging fields, and normalize service/component/outcome from finite catalogs.

### 9.1. Events Must Be Independently Meaningful

Events like `INGRESS_ACCEPTED`, `VALIDATED`, `OUTBOUND_ATTEMPTED`, and `TRANSPORT_CONFIRMED` need **explicitly defined and tested emission points**. Never emit `BUSINESS_COMPLETED` from a checkpoint before the handler merely because the design diagram puts the final step next.

### 9.2. Never Turn Correlation IDs into Metric Labels

Metrics should use finite labels like `flow`, `component`, `protocol`, and `outcome`. `correlation_ref`, `message_ref`, `business_id`, and `attempt_ref` belong in **role-restricted logs/traces**, never as counter/timer tags because they cause extreme cardinality.

## 10. Java DSL: Attaching Correlation and WireTap Observation

In Java DSL, a flow can enrich a header at ingress and tee a message copy via **WireTap** to emit metadata logs:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class CorrelatedFlowConfiguration {
    @Bean
    IntegrationFlow ordersInboundFlow() {
        return IntegrationFlow.from("ordersInbound")
                .enrichHeaders(h -> h.headerFunction(
                        "correlationRef",
                        m -> CorrelationRefs.issueInternal()))
                .wireTap("safeObservabilityChannel")
                .transform(String.class, String::trim,
                        e -> e.id("normalizeOrder"))
                .channel("ordersForOutbound")
                .get();
    }
}
~~~

This illustrates **ingress enrichment + checkpointing**. `ordersInbound` and `safeObservabilityChannel` require proper wiring/consumers in the application; WireTap does not perform logging or redaction by itself. If messages already carry correlation from a trusted service, use a **preserve-or-create** policy rather than overwriting unconditionally as in this fresh-ingress example.

### 10.1. Caveats When Using WireTap

- The tap branch still receives full payload/headers—**only a safe-projection consumer** may write to logs.
- Synchronous observation branches can slow business flows; async queues can overflow or drop logs.
- With WireTaps at multiple points, each must log distinct `component`/`stage` values rather than repeating “received.”
- If the logging branch fails, apply distinct policies for **diagnostic telemetry** vs. **mandatory auditing**.
- Never assume log counts equal unique business events when publish–subscribe or retries are involved.

## 11. MDC: Handy for Same-Thread Logs, Not a Message Header

Logging frameworks' **Mapped Diagnostic Context (MDC)** attaches fields to logs on the current thread. It is handy in synchronous handlers, yet **does not automatically cross** `ExecutorChannel`, other thread pools, poller tasks, or cross-process consumers.

### 11.1. Java MDC Scope with Cleanup

~~~java
import org.slf4j.MDC;

public final class MdcScope {
    private MdcScope() {}

    public static void runWithCorrelation(String correlationRef,
                                          Runnable task) {
        String prior = MDC.get("correlation_ref");
        try {
            MDC.put("correlation_ref", correlationRef);
            task.run();
        } finally {
            if (prior == null) {
                MDC.remove("correlation_ref");
            } else {
                MDC.put("correlation_ref", prior);
            }
        }
    }
}
~~~

This illustrates **restoring prior context** within a synchronous scope. `correlationRef` must already be sanitized—never an arbitrary HTTP header string. If code switches threads, fires delayed callbacks, or runs tasks outliving `task.run()`, implement proper context propagation.

### 11.2. Common MDC Mistakes

1. Calling `MDC.put` without `remove`: reused pool threads tag new requests with old IDs.
2. Relying on MDC without carrying IDs in `MessageHeaders`: correlation vanishes across queues/consumers.
3. Copying all headers from untrusted requests into MDC: spreads log injection or PII everywhere.
4. Mistaking MDC for distributed tracing: MDC does not create spans or link services by itself.
5. Setting MDC only at outbound: upstream filter/transformer errors lack IDs.
6. Setting context on the producer thread with no task wrapper/instrumentation on the executor.

**Right mindset:** store correlation references in the **message/transport contract**, and use MDC solely as **log presentation for the active execution segment**.

## 12. Async Channels and Preserving Causality

| Component | What Changes | How to Correlate Logs Properly |
|---|---|---|
| **DirectChannel** | Usually shares call stack/thread | Header and synchronous-scope MDC appear together |
| **QueueChannel** | Message waits for later consumer/poller fetch | Header travels with message; restore MDC at consumer |
| **ExecutorChannel** | Dispatcher/handler runs on thread pool | Propagate/instrument across executor and clean up context |
| **PublishSubscribeChannel** | Fans out to multiple subscribers, possibly async | Share parent correlation; add branch/attempt refs |
| **Splitter** | One message yields many children | Parent correlation + item/sequence reference |
| **Aggregator** | Many messages yield one result | Group correlation, completion state, and lineage |
| **Broker boundary** | Producer and consumer live in separate JVMs/processes | Transport header mapper/trace context + external broker identity |

### 12.1. Log Order Is Not Completion Order

In flows using `ExecutorChannel`, item B's `OUTBOUND_ATTEMPTED` log can appear before item A's `VALIDATED` log even though A arrived first. Correlate via correlation + attempt + **causal relations**, rather than sorting logs by timestamp and assuming sequential execution.

### 12.2. Queue Depth and Latency

Correlation logging should mark timestamps/metrics at **enqueue, dequeue, outbound attempt, and confirmation** when measuring end-to-end times. Handler timers exclude queue wait times. When message-level timing is restricted by data retention, use end-to-end histograms and queue age for SLOs.

## 13. W3C Trace Context and Micrometer/OpenTelemetry

**Trace ID** and **Span ID** link operations across components and services. Tracing systems commonly support W3C Trace Context (`traceparent`, and optionally `tracestate`/baggage per configuration).

**However**, inbound HTTP requests, JMS messages, and Kafka records do not automatically share identical propagation behavior; they require instrumentation/extractors/injectors matching your transport, libraries, and Spring Boot/Spring Integration/Micrometer version.

### 13.1. What Not to DIY

- Never copy an unvalidated `traceparent` string into logs as a trusted token.
- Never hardcode a fixed `spanId` for all endpoints.
- Never use trace ID as an idempotency key or business key.
- Never place emails, account IDs, or credentials in tracing baggage.
- Never assume `MessageHistory` is a distributed trace.

### 13.2. Correlation Logs and Tracing Complement Each Other

| Goal | Correlation Logs | Distributed Tracing |
|---|---|---|
| Group logs for one business journey | Strong when IDs propagate properly | Strong when spans/trace context are collected |
| Inspect latency between operations | Needs timestamps/metrics | Span timings are usually better suited |
| Track retries/replays hours apart | Works well with stable logical correlation | Need not share one trace; start a new trace and keep business correlation |
| Investigate when tracing samples out | Structured logs still remain | Trace may be absent due to sampling |
| Protect PII | Must classify IDs/fields | Must also classify attributes/baggage |
| Verify remote commit state | Requires external outcome evidence | A successful span alone does not prove business commit |

### 13.3. Parent/Child Decisions on Retries and Replays

For immediate retries within the same request, spans may appear as child/sibling attempts per instrumentation. For DLQ replays hours later, start a **new processing attempt/trace** while keeping **stable logical references** and an approved `replay_of`. Never force independent executions into one giant infinite trace.

## 14. Header Mapping Across Network Boundaries

Spring `MessageHeaders` can hold Java objects such as `replyChannel`, `errorChannel`, file references, or framework metadata; **never copy them wholesale** to HTTP, JMS, AMQP, Kafka, SFTP metadata, or DB columns.

### 14.1. Allowlist Principles

1. Define an **explicit list of public headers** per transport contract, such as `X-Correlation-Ref` and instrumentation-managed trace context.
2. Constrain data types, characters, lengths, header counts, and trust boundaries.
3. On the receiver, map back into **validated** application headers; never use them directly for authorization.
4. Exclude `Authorization`/`Cookie`, sessions, raw user identities, internal routing/channel objects, full `history`, or raw error details across boundaries.
5. Separate producer correlation from broker delivery metadata; log mappings at send/receive checkpoints.
6. Test serialization/deserialization against **actual client/adapter versions**.

### 14.2. Safe Mapping Pseudocode

~~~text
on_outbound(message, transport):
    correlation = require_valid_internal_correlation(message)
    external_headers = new_empty_header_map()
    external_headers["correlation-ref"] = correlation
    inject_trace_context_using_supported_instrumentation(external_headers)
    send_payload_using_contract(message.payload, external_headers)

on_inbound(external_record, trusted_transport):
    correlation = validate_and_accept_per_trust_policy(
        external_record.headers["correlation-ref"])
    if correlation is invalid or not trusted:
        correlation = issue_new_internal_ref()
    extract_trace_context_if_supported_and_trusted(external_record)
    create_message_with_approved_headers(correlation)
~~~

This is **pseudocode**, not a default Kafka/JMS/HTTP API. Each adapter has its own header naming/type rules, and W3C trace context propagation must use supported libraries.

## 15. HTTP Inbound Gateway → HTTP Outbound Gateway

### 15.1. Typical Milestone Sequence

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant A as Spring Integration Service
    participant B as Remote API
    C->>A: HTTP request
    Note over A: Issue internal correlation_ref
    A->>A: INGRESS_ACCEPTED / VALIDATED
    A->>B: Outbound request + approved correlation header
    Note over A: OUTBOUND_ATTEMPTED + attempt_ref
    alt Remote responds
        B-->>A: Status + response
        A->>A: TRANSPORT_CONFIRMED / APPLICATION_RESULT
        A-->>C: HTTP response
    else Timeout
        A->>A: UNKNOWN_OUTCOME / reconcile
        A-->>C: Error or async status per contract
    end
~~~

### 15.2. Fields to Log

| Checkpoint | Safe Log Fields |
|---|---|
| HTTP ingress | Route template, method, status class, internal correlation, request size bucket |
| Validation | Schema version, bounded reason code |
| Outbound begin | Target alias, attempt ID, timeout class |
| Outbound end | Status class, duration, approved response classification |
| Retry | New attempt ID, retry index, cause class |
| Client response | Status code, latency, outcome per gateway contract |

**Never log** raw request/response bodies, `Authorization`, cookies, query tokens, or full dynamic URLs just to stitch logs.

### 15.3. HTTP 200/202 and Timeouts Do Not Equal Completion

- HTTP `200` may be synchronous, yet business body/error codes still need verification.
- HTTP `202 Accepted` often means only that the remote side accepted async work.
- A timeout after sending a request is an **unknown outcome**; the remote may have committed.
- An outbound gateway producing a Spring reply Message may change the **local Message ID**; preserve correlation per contract.
- Client disconnects do not necessarily cancel remote side effects.

When retrying, use idempotency keys and/or readbacks per target API rather than looking for a log line missing a response and resending blindly.

## 16. File Inbound/Outbound: From File Reference to Business Result

File adapters do not receive correlation headers from remote partners. Designers must define the tracked unit:

1. **One file:** issue a reference when an eligible file is accepted.
2. **One batch within a file:** keep `parent_file_ref`, creating `batch_ref` when needed.
3. **Each record after a splitter:** keep parent correlation and add a separate item reference.

### 16.1. Checkpoints

| Step | Event | What Must Not Be Inferred |
|---|---|---|
| Scanner spots file | `SOURCE_OBSERVED` | File is completely ready to read |
| Inbound creates message | `INGRESS_ACCEPTED` | File parsed cleanly |
| Transformer parses | `VALIDATED` / `PARSE_FAILED` | Outbound sent |
| File outbound writes | `WRITE_ATTEMPTED` | File is durable or picked up by partner |
| Handoff confirmed | `TRANSPORT_CONFIRMED` (if defined by contract) | Remote business processing finished |

### 16.2. Protecting Data

**Never use raw filenames/paths as default correlation references or log fields.** Filenames can contain full names, account numbers, or tenants. Issue a system-generated opaque file ref and keep mappings in an ACL-protected store if needed. For large files or streams, never read payloads solely to compute correlation; consuming the stream breaks downstream handlers.

### 16.3. Accept-Once Filters and Restarts

Files can be re-read after restarts if metadata stores/filters change, or skipped if already marked processed. Correlation refs may be fresh per processing attempt while linking to a **logical file source** via a safe business key to identify duplicates/replays. Logs alone cannot replace idempotent file processing.

## 17. SFTP Inbound/Outbound: Poll Ref, File Ref, and Transfer Ref

SFTP combines **pollers** and **remote sessions**, so never assign one correlation across an entire poll run if one poll yields multiple files.

~~~text
poll_ref          = poll-2026-11-23-0800
file_correlation  = corr-1f83
transfer_attempt  = transfer-01
checkpoint        = SFTP_DOWNLOAD_ATTEMPTED
outcome           = transport-timeout
~~~

### 17.1. Key Milestones

- `POLL_STARTED` / `POLL_EMPTY` / `POLL_FAILED`: scheduler/source events; **no Spring Message exists yet**.
- `FILE_ELIGIBLE`: remote listing/filter matched a file.
- `DOWNLOAD_ATTEMPTED` / `DOWNLOAD_CONFIRMED`: client-side transfer outcome.
- `INGRESS_ACCEPTED`: file became a message in the flow.
- `OUTBOUND_ATTEMPTED` / `REMOTE_HANDOFF_CONFIRMED`: upload/rename/commit per remote contract.
- `BUSINESS_COMPLETED`: when the partner provides a callback/status/event confirming processing.

### 17.2. SFTP Timeouts and Partial Files

A transfer timeout can leave a temp file or partial bytes on the target. **Never log “sent success” simply because an upload call returned.** Verify remote size/checksum, temporary filename/rename semantics, idempotent delivery, and approved cleanup steps.

### 17.3. Never Log Sensitive SFTP Details

Log source/target aliases, transfer status, byte buckets, and correlation; exclude usernames, passwords, private keys, full paths, and filenames containing personal data. If a connection fails to open, only poll/session logs exist—**there is no message history** for an uncreated message.

## 18. JMS: JMSCorrelationID vs. Dedicated Logic Correlation

JMS supports metadata such as **`JMSMessageID`** and **`JMSCorrelationID`**. They help with request/reply and broker tracking, with caveats:

- `JMSMessageID` is assigned by the provider per send semantics; it is not the Spring Message ID.
- `JMSCorrelationID` may be set by producers/apps; its contents may be untrusted or serve as a request/reply link ID.
- A redelivered message may spawn a **new Spring Message** on the consumer with a different attempt context.
- JMS ACK/transaction commits differ from handlers logging “processed” before commit.

### 18.1. Inbound JMS

Log `broker_message_ref` (if policy permits), consumer destination alias, application correlation, delivery/redelivery indicator, and handler outcome. If a producer contract uses `JMSCorrelationID` across services, validate/normalize it before putting it into logs or MDC.

### 18.2. Outbound JMS

Log `OUTBOUND_ATTEMPTED` and sent/committed events per real API/session behavior. For request/reply, map request correlation to replies **via the appropriate gateway/JMS mechanism** instead of mixing reply correlation with business IDs.

### 18.3. ACK/Transactions and Duplicates

A record rolled back and reprocessed keeps the same logical correlation with a new attempt. Never report two completed orders just because two `HANDLER_STARTED` logs exist. Business outcomes require transaction/target confirmation and idempotency strategies.

## 19. AMQP/RabbitMQ: Routing, Delivery Tags, and Confirmations

In AMQP/RabbitMQ, messages have routing properties, headers, and bodies, with producers and consumers decoupled.

| Information | Scope | Role in Log Correlation |
|---|---|---|
| Application correlation header | Producer/consumer contract | Links logical events once validated |
| Exchange/routing key | Broker routing | Log only permitted aliases/values; not an ID by default |
| Delivery tag | Channel/session-scoped delivery | Never use as global correlation |
| Publisher confirm | Broker publish outcome per semantics | Transport milestone, not consumer completion |
| Consumer ACK/NACK | Delivery outcome at consumer | Pair with transaction/business outcome |
| DLQ/requeue metadata | Retry/failure path | Links attempt lineage and reason class |

### 19.1. Publish–Consume–Commit

Producers log `OUTBOUND_ATTEMPTED` before publishing and `TRANSPORT_CONFIRMED` upon receiving confirms. Consumers receive the message, extract correlation via configured mappers, and log `INGRESS_ACCEPTED` with a fresh attempt. If a consumer ACKs while side effects happen outside the transaction, verify those commits independently.

### 19.2. Poison Message Loops

A failing message can be NACKed/requeued repeatedly. Log analysis should reveal **one logical correlation + multiple delivery attempts**, backoff/rates, and DLQ routing—rather than concluding the publisher sent many independent messages.

## 20. Kafka: Linking Producer, Topic-Partition-Offset, and Consumer

Kafka provides clear transport milestones:

1. Producer calls `send` and starts a **send attempt**.
2. Producer callback receives metadata or failure per `acks`/client settings.
3. Record resides at a **topic/partition/offset** once brokered per semantics.
4. Consumer group polls/receives the record, processes it, and commits offsets per configuration.
5. Downstream business systems may still need to update a database or call another API.

### 20.1. Producer Logging

~~~json
{
  "event":"TRANSPORT_CONFIRMED",
  "flow":"order-publisher",
  "component":"ordersKafkaOutbound",
  "correlation_ref":"corr-7f92",
  "attempt_ref":"send-01",
  "target_type":"kafka",
  "topic_alias":"orders",
  "partition":2,
  "offset":1849,
  "outcome":"confirmed"
}
~~~

Values are **synthetic**, not default logs from Spring Kafka/Integration. Partition/offset helps trace a specific record, yet should never become per-message metric labels; enforce access controls on logs.

### 20.2. Consumer Logging

~~~json
{
  "event":"INGRESS_ACCEPTED",
  "flow":"order-consumer",
  "component":"ordersKafkaInbound",
  "correlation_ref":"corr-7f92",
  "local_message_ref":"msg-new",
  "consumer_attempt_ref":"consume-02",
  "topic_alias":"orders",
  "partition":2,
  "offset":1849,
  "retry_index":1
}
~~~

When consumers read `correlation_ref` from Kafka headers, use compatible header mapping/serialization and validate the value. Kafka record **keys** may contain customer IDs, so never log raw keys as correlation. `topic/partition/offset` is broker identity, not a business ID.

### 20.3. Offset Commit Does Not Prove Side Effects Completed

Depending on container settings, offsets may commit before/after processing or inside transactions. “Consumer lag = 0” and “offset committed” do not prove remote DBs/APIs succeeded. Place `BUSINESS_COMPLETED` where contract evidence exists and guard against duplicates/replays.

### 20.4. Header Tracing and Consumer Groups

W3C trace context over Kafka requires producer injection and consumer extraction via proper instrumentation. On replays from retry/DLQ topics, start a new trace while keeping logical correlation + `replay_of`; replays hours apart do not need to share one trace ID.

## 21. JDBC/Database Adapters: When a Row Becomes a Message

JDBC inbound polling, outbound updates, and request/reply gateways have **transaction boundaries** and **data units** distinct from brokers. One `SELECT` can return many rows, one row can go through multiple attempts, and an outbound call can succeed even if the DB processed-marker update fails.

### 21.1. Correlation Granularity

| Level | Reference | Purpose |
|---|---|---|
| One poll | `poll_ref` | Locate one scheduled query execution |
| One batch SELECT | `query_attempt_ref` | Track SQL execution, duration, row count |
| One logical row/event | `correlation_ref` | Link endpoints processing that item |
| One row retry | `processing_attempt_ref` | Distinguish retries/recovery |
| One DB transaction | `transaction_ref` or separate evidence | Link logs with commits/rollbacks where available |
| One outbound request | `delivery_attempt_ref` | Identify one remote call |

### 21.2. Safe Log Milestones

~~~text
DB_POLL_STARTED       poll_ref=poll-17
DB_ROWS_SELECTED      poll_ref=poll-17 rows=25
INGRESS_ACCEPTED      correlation_ref=corr-c42 source_type=jdbc
OUTBOUND_ATTEMPTED    correlation_ref=corr-c42 attempt_ref=call-01
OUTCOME_UNKNOWN       correlation_ref=corr-c42 attempt_ref=call-01
RECONCILIATION_RESULT correlation_ref=corr-c42 outcome=confirmed
DB_MARKER_COMMITTED   correlation_ref=corr-c42 transaction_ref=tx-18
~~~

These are application-defined events. Emit `DB_MARKER_COMMITTED` only **after commit confirmation**, not merely when code calls `update(...)`.

### 21.3. SQL Logging Risks

Never use raw primary keys, emails, SQL statements with literal parameters, or whole rows as correlation log fields unless classified safe. Use **opaque references** or ACL-protected domain mappings. For stable references across retries, reuse an internal ID minted at event creation rather than reconstructing from PII fields.

### 21.4. Timeout Errors and Duplicate Transactions

A `DB poll → HTTP API → DB mark processed` flow can time out after the remote call succeeds yet before the local marker commits. The next poll re-reads the row. Use **idempotency keys, inbox/outbox, or readback/reconciliation** per architecture to decide whether to resend. Correlation logs show two attempts for one logical event; they do not prevent duplicates themselves.

## 22. Pollers: Linking Logs Before Any Spring Message Exists

An inbound adapter using a `poller` runs periodically over File, SFTP, JDBC, or `QueueChannel`. When a poll returns empty, **no message exists**, so message `correlationRef` cannot prove the poller is alive.

### 22.1. Distinguishing Poll Events from Message Events

~~~mermaid
sequenceDiagram
    participant P as Poller
    participant S as External Source
    participant A as Inbound Adapter
    participant H as Business Handler
    P->>A: poll(poll_ref)
    A->>S: query / scan / list
    alt Source empty
        S-->>A: No items
        A-->>P: POLL_EMPTY
    else Multiple items
        S-->>A: Item 1, Item 2
        A->>H: Message 1 + correlation_ref_1
        A->>H: Message 2 + correlation_ref_2
    else Connection error
        S-->>A: Transport error
        A-->>P: POLL_FAILED
    end
~~~

### 22.2. Designing ID Levels

- Each poll run gets a **`poll_ref`**, distinct from emitted message IDs.
- Each logical item gets its own **`correlation_ref`**.
- For batches, child messages carry **`parent_batch_ref`** and **`item_ref`** per policy.
- If the source already supplies a trusted ID, map it to a logical event reference instead of minting fresh ones on every attempt—still enforcing deduplication.

### 22.3. Diagnosing “Missing Correlation Logs”

Causes include no source data, poller failure before message creation, filters dropping all items, logger sampling, or collector failures. Check **last poll tick, empty/error counts, oldest source age, and poller lifecycle** before concluding messages were lost.

## 23. Splitters, Aggregators, and Branching: Lineage Correlation

In `splitter → item handlers → aggregator` flows, one parent message can spawn thousands of children. **Never rely on a single ID to cover all item and attempt details**.

### 23.1. Suggested Lineage Structure

~~~json
{
  "event":"ITEM_VALIDATED",
  "flow":"invoice-batch",
  "correlation_ref":"corr-batch-92",
  "parent_ref":"batch-92",
  "item_ref":"opaque-item-07",
  "processing_attempt_ref":"item-attempt-01",
  "component":"validateInvoice",
  "outcome":"accepted"
}
~~~

`item_ref` must be a log-safe reference, not an unclassified document or customer account number. When items contain sensitive data, log only `sequence_index` scoped within the protected batch.

### 23.2. Milestones to Record

1. `BATCH_ACCEPTED` — confirmed item count, schema, and batch reference.
2. `SPLIT_COMPLETED` — count of child messages produced.
3. `ITEM_VALIDATED`/`ITEM_REJECTED` — per item only when truly needed and sampled/bounded.
4. `BRANCH_DISPATCHED` — router branch selected from a fixed catalog.
5. `AGGREGATION_PENDING`/`AGGREGATION_COMPLETED`/`AGGREGATION_TIMED_OUT` — group state.
6. `OUTBOUND_CONFIRMED` — aggregate outcome, not automatically every item's outcome if target semantics differ.

### 23.3. Common Pitfalls

- Aggregators build a new result message; the group correlation header can differ from the application's correlation ref.
- One item timing out does not fail the whole batch if completion strategy allows partial results.
- A `PublishSubscribeChannel` sending to three subscribers does not prove all three succeeded just because dispatch logged.
- Item retries must get new attempt refs without overwriting prior lineage.
- For large batches, per-item logging inflates volume and exposure risk; prefer batch-level metrics and error-only logs.

## 24. Request/Reply Gateways: Linking Requests, Replies, and Callbacks

### 24.1. Synchronous Inbound Gateway

An HTTP/JMS gateway receives a request and awaits a reply from the integration flow. Logs should capture **request accepted, business handler result, reply constructed, and response delivered** per verifiable semantics.

### 24.2. Synchronous Outbound Gateway

An outbound gateway calls a remote service and receives a response:

~~~text
INGRESS_ACCEPTED       correlation_ref=corr-r17
GATEWAY_REQUEST_SENT   correlation_ref=corr-r17 attempt_ref=req-01
GATEWAY_REPLY_RECEIVED correlation_ref=corr-r17 attempt_ref=req-01 status_class=2xx
REPLY_TRANSFORMED      correlation_ref=corr-r17 result=accepted
CLIENT_RESPONSE_SENT   correlation_ref=corr-r17 http_status=200
~~~

A log named `CLIENT_RESPONSE_SENT` should claim only what the server framework actually knows. It does not prove network delivery all the way to the end client succeeded.

### 24.3. Async Callback Pattern

When a remote API returns `202 Accepted` and sends a callback later, the initial request finishes before the callback arrives. Persist the **correlation → external job reference mapping** in an authorized state store or outbox. Incoming callbacks bearing that reference require **authentication and validation** before linking back to logical correlation—never blindly trust self-asserted callback query params.

### 24.4. Reply Channels and Error Channels

Spring Integration stores `replyChannel`/`errorChannel` in headers for internal routing. These are not correlation IDs and may be Java objects. Never serialize/send them across brokers or into logs. Gateway reply messages may be newly built with different local Message IDs; preserve references via proper mapping.

## 25. ErrorMessage and Logging When Exceptions Occur

Depending on endpoint config, error handling, and protocol, failures in Spring Integration can route to `errorChannel` as `ErrorMessage`s. In some cases an **original message** is attached for reading metadata/correlation.

### 25.1. Example Extracting Error Context

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;

public void handleError(Message<?> inbound) {
    if (!(inbound instanceof ErrorMessage error)) {
        return;
    }

    Message<?> original = error.getOriginalMessage();
    String correlation = "missing";
    if (original != null) {
        Object value = original.getHeaders().get("correlationRef");
        if (value instanceof String ref
                && ref.matches("[A-Za-z0-9_-]{1,64}")) {
            correlation = ref;
        }
    }

    // Log safe metadata only; do not print ErrorMessage/original payload.
    auditSafeFailure(correlation, "PROCESSING_EXCEPTION");
}
~~~

`auditSafeFailure(...)` is an **illustrative application method**, not a Spring Integration API. When the original message is absent, fall back to request/transport context or an incident record—never fabricate a bogus correlation linking unrelated flows.

### 25.2. Errors Can Happen Before a Message Exists

- File/SFTP poll fails to open a session.
- HTTP request rejected before reaching the gateway.
- Kafka deserialization/converter fails before building a valid Spring Message.
- JMS/AMQP client cannot connect to the broker.
- JDBC query/connection fails before producing any row/message.

These cases need **poll/request/delivery attempt references** at the adapter/client layer rather than trying to read `MessageHistory` or `correlationRef` from a nonexistent message.

### 25.3. Never Log Payloads on Error

`Throwable.getMessage()` can contain HTTP bodies, raw records, SQL parameters, or URLs with tokens. Log normalized `error_class`/`exception_type`, component, attempt, and correlation; keep stack traces restricted per policy and never dump `error.getPayload()` or raw original messages.

## 26. Retries, Redeliveries, DLQ, and Idempotency: One Logical Event, Many Attempts

**Retries** are a common reason the same correlation appears multiple times in logs. Without attempt IDs and clear outcome semantics, dashboards easily count multiple deliveries as multiple business events.

### 26.1. Example: One Event Sent over HTTP Three Times

~~~text
correlation_ref=corr-e21 event=INGRESS_ACCEPTED
correlation_ref=corr-e21 attempt_ref=attempt-01 event=OUTBOUND_ATTEMPTED
correlation_ref=corr-e21 attempt_ref=attempt-01 event=REMOTE_TIMEOUT outcome=unknown
correlation_ref=corr-e21 attempt_ref=attempt-02 event=OUTBOUND_ATTEMPTED
correlation_ref=corr-e21 attempt_ref=attempt-02 event=REMOTE_UNAVAILABLE outcome=retryable
correlation_ref=corr-e21 event=RECONCILIATION_STARTED
correlation_ref=corr-e21 event=BUSINESS_COMPLETED outcome=confirmed
~~~

This is an **illustrative timeline**. If the first request might have committed, firing attempt 2 without idempotency/reconciliation risks duplicate side effects. `BUSINESS_COMPLETED` is not necessarily produced by attempt 2.

### 26.2. Separate Outcome Layers

| Layer | Suggested Fields |
|---|---|
| Logical event | `correlation_ref`, `event_type` |
| Source delivery | `delivery_ref`, `redelivery_index` |
| Processing invocation | `processing_attempt_ref`, `retry_index` |
| Target call | `outbound_attempt_ref` |
| Business outcome | `completion_status`, `evidence_ref` |
| Replay from DLQ | `replay_ref`, `replay_of`, `reason_class` |

### 26.3. Correlate to Investigate, Use Idempotency to Protect

Correlation does not stop duplicates. An idempotency key can derive from a **verified business command identity per policy**, and need not match `correlation_ref`. Deduplication belongs to the domain/receiver and transaction strategy.

### 26.4. Dead-Letter Queues

When a message enters a DLQ, log at minimum:

- Original logical correlation if available and permitted.
- DLQ transport ref / topic / queue alias.
- Reason class, attempt count, and final status.
- Reference to the original event in an authorized store.

On replay, issue a **new attempt/replay ref**, preserve lineage, and start a fresh trace context if appropriate. DLQs can hold sensitive payloads; never dump DLQ bodies into logs for reconciliation.

## 27. Clocks, Timestamps, and Measuring End-to-End Latency

### 27.1. Timestamps Across Machines Are Not Absolute

Collectors may receive logs from producer B before producer A even when A executed first, due to log queues, network delays, batching, sampling, and clock skew. Store UTC timestamps and monitor clock drift, yet **never** rely on timestamp sorting alone to prove causality.

### 27.2. Durations with Clear Start and End Points

| Duration | Start | End |
|---|---|---|
| **Inbound latency** | Request/record arrives at adapter layer | Spring Message accepted |
| **Queue wait** | Enqueued | Consumer starts processing |
| **Handler duration** | Handler invoked | Handler returns/throws |
| **Outbound latency** | Target call started | Protocol response/confirm/timeout |
| **End-to-end latency** | Logical event accepted/source-ready | Business completion per contract |

Within one JVM, measure elapsed duration using a **monotonic clock/timer**; wall-clock timestamps support correlation and timelines. Never subtract log timestamps across two hosts as high-precision latency without accounting for clock skew.

### 27.3. Never Log Arbitrary Source Timestamps as Trusted Fact

External records can carry malformed `eventTime`, wrong timezones, future dates, or tampered values. When measuring freshness, validate inputs and distinguish `source_event_time` from system-recorded `received_at`.

## 28. Combining MessageHistory, Micrometer, and Tracing

### 28.1. MessageHistory Is the Local Path

When enabled and headers are preserved, `MessageHistory` lists the Spring Integration components traversed by a message. It shows which router/transformer/handler may have seen the message, **not** latency or remote ACK proof.

### 28.2. Micrometer Metrics Are Aggregates

Monitor:

| Signal | Usage |
|---|---|
| Ingress/egress attempts | Compare counts, spot drift |
| Handler failures/retries | Spot error spikes without counting attempts as unique events |
| Queue depth/oldest age | Spot bottlenecks between inbound and outbound |
| Poller last tick/empty/error | Distinguish no data from stopped pollers |
| Transport confirm rate | Evaluate publishes/uploads/calls |
| Consumer lag/DLQ | Track broker backlogs and terminal failures |
| Business completion SLI | Verify end-to-end service targets |

**Never put `correlation_ref` in meter tags**; keep IDs in logs/traces. For distributed tracing, use instrumentation compatible with Spring Boot/Micrometer/OpenTelemetry and protocol header mappers.

### 28.3. A Well-Observed Flow

~~~mermaid
flowchart TD
    A[SLI alerts on end-to-end delay] --> B[Metrics: queue / poller / adapter]
    B --> C[Trace context: service and span]
    C --> D[Structured logs by correlation_ref]
    D --> E[Local MessageHistory / checkpoint IDs]
    E --> F[Broker ACK / DB commit / HTTP result]
    F --> G[Reconciliation and remediation]
~~~

Each layer answers a different question; correlation logs are **investigative links**, replacing neither metric alerts nor target state authorities.

## 29. Security and Data Protection in Correlation Logs

### 29.1. IDs Themselves Can Be Sensitive Data

Correlation IDs containing emails, phone numbers, account numbers, filenames, URLs, or raw business IDs can leak PII. Unsalted hashes of low-entropy emails/phone numbers can also be dictionary-attacked. To map sensitive IDs safely, use **system-issued opaque references** or key-managed HMACs vetted by privacy review.

### 29.2. Fields to Exclude

- Raw payloads, HTTP request/response bodies, Kafka/JMS/AMQP bodies.
- `Authorization`, `Cookie`, OAuth access/refresh tokens, API keys, SSH private keys.
- Full File/SFTP paths containing customer names, tenants, or accounts.
- SQL bind values, database rows, customer data.
- Exception messages embedding bodies/URLs/secrets.
- Full Spring `MessageHeaders` or `MessageHistory` exported across networks.
- Unvalidated client-supplied IDs; newline/control characters enabling log injection.

### 29.3. Layered Safety Techniques

1. **Omission/allowlist:** build structured log objects strictly from required fields.
2. **Validation:** restrict character sets, length, and enum values.
3. **Separation:** govern diagnostic logs and audit records under separate policies.
4. **RBAC/retention:** restrict access to logs, exports, and data lifecycles.
5. **Size/rate limits:** bound costs and prevent log floods during retry storms.
6. **No raw fallback:** when sanitizers/parsers fail, emit an error class instead of dumping input.
7. **Transport boundary control:** propagate only approved headers.

### 29.4. Correlation Logs Are Not Authorization Proof

A sender can replay a previously seen `correlationRef`. Never use it to decide “message already authenticated,” “payment approved,” or “authorized to read data.” Rely on real authentication, authorization, message validation, and trusted business state.

## 30. Sample Log Contract: From Source to Target

Teams can standardize a finite taxonomy:

| Event | When Emitted | Required Fields |
|---|---|---|
| `POLL_STARTED` | Poll scheduler starts | flow, poll_ref, source_type |
| `POLL_EMPTY` | Poll finishes with zero items | flow, poll_ref, outcome |
| `INGRESS_ACCEPTED` | Valid transport-level inbound message created | correlation_ref, flow, component |
| `VALIDATION_REJECTED` | Filter/schema rejects | correlation_ref, bounded reason |
| `BRANCH_SELECTED` | Router picks destination | correlation_ref, branch enum |
| `OUTBOUND_ATTEMPTED` | Call/publish/upload begins | correlation_ref, attempt_ref, target |
| `TRANSPORT_CONFIRMED` | Target ACKs per protocol | correlation_ref, attempt_ref, receipt |
| `REMOTE_TIMEOUT` | Uncertain whether remote committed | correlation_ref, attempt_ref, unknown |
| `BUSINESS_COMPLETED` | Evidence of business completion exists | correlation_ref, evidence_ref |
| `TERMINAL_FAILED` | Retries exhausted / routed to fail state | correlation_ref, reason, attempts |
| `DLQ_ENQUEUED` | Broker accepts DLQ publish | correlation_ref, DLQ ref |
| `REPLAY_STARTED` | Approved replay initiated | correlation_ref, replay_ref, replay_of |

### 30.1. Distinguish Outcomes by Layer

`TRANSPORT_CONFIRMED` should include `confirmation_scope` when ambiguous—such as `broker_publish`, `remote_http_response`, or `file_handoff`. Emit `BUSINESS_COMPLETED` only when target/transaction logic supports that conclusion, preventing dashboards from confusing `2xx` with business success.

### 30.2. End-to-End Example: File → Kafka → JDBC

~~~text
09:00:00 POLL_STARTED         poll_ref=p-01 source=file
09:00:01 INGRESS_ACCEPTED     correlation_ref=corr-abc source=file
09:00:02 VALIDATED            correlation_ref=corr-abc component=parseInvoice
09:00:03 OUTBOUND_ATTEMPTED   correlation_ref=corr-abc attempt_ref=k-01 target=kafka
09:00:04 TRANSPORT_CONFIRMED  correlation_ref=corr-abc attempt_ref=k-01
09:00:09 INGRESS_ACCEPTED     correlation_ref=corr-abc source=kafka
09:00:11 DB_UPDATE_ATTEMPTED  correlation_ref=corr-abc attempt_ref=db-01
09:00:12 BUSINESS_COMPLETED   correlation_ref=corr-abc evidence_ref=tx-opaque
~~~

These are **synthetic** data and illustrative timestamps. Missing log lines do not automatically mean message loss; check collectors, sampling, broker lag, transactions, and external state.

## 31. Testing Correlation Helpers and Log Payloads

### 31.1. JUnit for ID Format and Generation

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class CorrelationRefsTest {
    @Test
    void createsOpaqueReference() {
        String ref = CorrelationRefs.issueInternal();
        assertTrue(ref.startsWith("corr-"));
        assertFalse(ref.contains("@"));
        assertTrue(ref.length() <= 64);
    }

    @Test
    void rejectsUnsafeCandidate() {
        String ref = CorrelationRefs.acceptTrustedOrIssue(
                "foo\nFAKE-LOG-EVENT");
        assertTrue(ref.startsWith("corr-"));
        assertFalse(ref.contains("\n"));
    }
}
~~~

This test verifies only **ID shape handling**. It does not prove an HTTP sender is trustworthy or that correlation propagates across a broker. Use `acceptTrustedOrIssue` strictly per the trust policy in section 6.

### 31.2. Testing Log Structure

Build synthetic inputs containing `accessToken`, `password`, `customerEmail`, nested JSON, Kafka keys, sensitive filenames, and CR/LF. Capture handler log output and verify:

- Logs contain only allowlisted fields and enum values.
- Zero synthetic secret/PII markers appear.
- A single request keeps the same correlation across internal checkpoints.
- Retries mint distinct attempt IDs without arbitrarily minting new logical correlations.
- Arbitrary headers are not forwarded over the network.
- Parse failures never fall back to raw payload logging.
- Async executions never retain the previous message's MDC.

### 31.3. Test Cases Where No Message Appears

For pollers, test `POLL_EMPTY`/`POLL_FAILED` independently of `INGRESS_ACCEPTED`, since not every poll emits a Spring Message. For pre-auth HTTP errors or Kafka deserialization errors, ensure technical events emit even without message correlation.

## 32. End-to-End Test Matrix by Adapter

| Test Case | Input / Condition | What Must Be Proven |
|---|---|---|
| **HTTP happy path** | Request → outbound 2xx | Correlation spans ingress, outbound, reply; accurate outcome |
| **HTTP 202 async** | Remote accepts without finishing | Logs separate `accepted` from `completed` |
| **HTTP timeout** | Remote may have committed | `UNKNOWN_OUTCOME`; no blind retries |
| **File parser reject** | Malformed file schema | Source/correlation ref logged once message exists; no file path/body |
| **SFTP poll empty** | No remote files | Poll logged; no fake message correlation minted |
| **SFTP interrupted transfer** | Partial file upload | Transfer attempt + resume/readback per policy |
| **JMS rollback** | Same message redelivered | Logical ref stays stable if supported by contract; new attempt |
| **AMQP requeue** | Poison message redelivered many times | Deliveries separated from terminal failure; no body logged |
| **Kafka new process** | A publishes, B consumes | Header mapped / trace extracted properly; local Message ID differs |
| **Kafka DLQ replay** | Replay hours later | Replay ref and lineage recorded; does not force old trace |
| **JDBC retry** | DB status uncommitted, remote processed | Idempotency/reconciliation prevents duplicate side effects |
| **ExecutorChannel** | Handler runs on worker thread | Context restored cleanly; no MDC leakage |
| **Splitter/aggregator** | Multi-item batch | Parent/child lineage traceable; result history not treated as all items |
| **Filter discard** | Rejected payload | Reason code and correlation appear on discard branch |
| **Logger/collector down** | Missing logs | Business flow and telemetry-failure policy verified |

### 32.1. You Do Not Need One Unified Protocol Test Framework

Each adapter has unique semantics. Testing Kafka broker acks differs from HTTP responses; testing JDBC transactions differs from file handoffs. Still, you can reuse **common assertions on correlation headers, safe log schemas, attempt uniqueness, and outcome taxonomies**.

## 33. Runbook CORR-01 — No Outbound Log Found for an Inbound Event

**Trigger:** `INGRESS_ACCEPTED` exists, yet no matching `OUTBOUND_ATTEMPTED`/`BUSINESS_COMPLETED` appears for that correlation.

1. Confirm you are querying the **internal correlation** over the right time range, service/instance, and environment.
2. Check **sampling, log levels, collector health, and dropped logs** before assuming the event vanished.
3. Inspect history/checkpoints: did a filter discard it? Which branch did the router choose? Did a transformer throw?
4. For `QueueChannel`/`ExecutorChannel`, inspect backlog, executor queues/rejections, in-flight counts, and consumer health.
5. For splitters/aggregators, inspect parent/child refs and group completion/timeouts.
6. At the outbound adapter, inspect client attempts, error channels, retries/DLQ, connectivity, and target timeouts.
7. Check whether header propagation was lost in a custom `MessageBuilder`, header mapper, or broker boundary.
8. Across services, inspect broker record ID/offset/ACK and receiver logs by transport identity + trusted correlation.
9. Verify target/business state via authorized readback; missing outbound logs **do not prove** the target was untouched.
10. Record incident, root cause, owner, evidence, and instrumentation/logic fixes; add regression tests.

### 33.1. Decision Tree

~~~mermaid
flowchart TD
    A[INGRESS_ACCEPTED exists] --> B{Searched right time range / service?}
    B -->|No| C[Fix query / collector scope]
    B -->|Yes| D{Post-validation checkpoint exists?}
    D -->|No| E[Filter / transformer / error flow]
    D -->|Yes| F{Async queue/backlog exists?}
    F -->|Yes| G[Queue age / executor / consumer health]
    F -->|No| H{Outbound attempt exists?}
    H -->|No| I[Router / header lost / logs sampled]
    H -->|Yes| J{External confirmation exists?}
    J -->|Unclear| K[Retry / DLQ / remote reconciliation]
    J -->|Yes| L[Business completion / target readback]
~~~

## 34. Runbook CORR-02 — Logs Show Duplicate Sends or Timeouts

**Trigger:** one logical `correlation_ref` shows two or more outbound attempts, or the remote side reports a duplicate despite only one logged `send`.

1. Group by logical correlation and **verified** business event reference.
2. Order `attempt_ref`s, transport delivery IDs, retry indices, and timeout/ACK timestamps.
3. Cross-check retry policy (backoff, max attempts, exception classifier) and broker redelivery possibilities.
4. At the target, inspect **idempotency keys, transaction logs, business status, and receipts**.
5. If outcomes remain unclear, mark `UNKNOWN_OUTCOME` until reconciled; never replay immediately.
6. Identify whether duplicates came from source duplication, timeout retries, consumer rollbacks, connector timeouts, or operator replays.
7. Separate **attempt counts** from **unique confirmed events** in metrics and audits.
8. If duplicate side effects occurred, perform approved business remediation rather than deleting logs.
9. Fix idempotent receiver, outbox/inbox, or transaction boundaries if the root cause is architectural.
10. Add tests covering timeouts after remote commit and redeliveries before commit.

## 35. Dashboards and Alerting Supporting Correlation Logging

### 35.1. Three-Tier Dashboard

| Tier | Panels / Information | Purpose |
|---|---|---|
| **Business SLI** | Unique completion %, p95 end-to-end, oldest pending age | Is the flow meeting business demand? |
| **Flow/adapter** | Ingress, filters, channel queues, outbound attempts, confirms, retries, DLQ | Which stage is failing or backed up? |
| **Case investigation** | Search by correlation, trace, broker ref, attempt | Trace a specific incident |

### 35.2. Useful Alerts

- Ingress events arrive while outbound confirmations drop anomalously (given sufficient traffic).
- Queue/broker backlog age exceeds SLO even when error counts look low.
- Rate of `UNKNOWN_OUTCOME` or timeouts rises; remote systems may have committed.
- Retries/redeliveries climb while unique business completions stall.
- Correlation propagation breaks between two services in integration tests or synthetic probes.
- Log/metric exporters drop data; never treat **no data** as 0 errors.

**Never build alerts where each correlation ID is its own metric series.** Correlation belongs in log indexes/trace search; metrics use low-cardinality flow, component, protocol, and outcome tags.

### 35.3. Logging Coverage Is Not Business Success

A dashboard showing “100% of messages have correlation” proves instrumentation coverage of measured events—**not** that every message was processed accurately. Pair it with confirmations, correctness checks, and contract SLOs.

## 36. Common Anti-Patterns

| Anti-Pattern | Consequence | Solution |
|---|---|---|
| Using raw emails/filenames as correlation | Leaks PII across logs/metrics | Opaque internal ref with ACL-protected mapping |
| Using `MessageHeaders.ID` across services | Loses linkage when new messages are built | Dedicated contract correlation header |
| Minting a new ID in every handler | Impossible to stitch flows | Preserve correlation; mint only attempt/branch IDs |
| Using trace ID as idempotency key | Replays and sampling break semantics | Dedicated business idempotency key |
| Putting correlation IDs in Micrometer tags | High cardinality | Keep IDs in structured logs/tracing |
| Relying solely on MDC across executors | Lost or mixed IDs across threads | Message headers + context propagation + cleanup |
| Copying all `MessageHeaders` over Kafka/HTTP | Leaks secrets/topology, breaks serialization | Header allowlist/mapper |
| Logging entire `Message<?>` on errors | Leaks payloads/headers | Safe projection, reason enum |
| Logging `BUSINESS_COMPLETED` right after `send()` | False success when broker/remote fails | Emit on contract ACK/commit |
| Omitting `attempt_ref` on retries | Counts retries as separate business events | Logical correlation + distinct attempt IDs |
| Inferring causal order from timestamps | Fails under async and clock skew | Trace relationships / attempts / sequences |
| Ignoring pre-Message errors | Blind to poll/parse failures | Adapter/poller/client event refs |
| Forcing multi-day replays into one trace | Giant traces, broken session semantics | Fresh trace keeping lineage/`replay_ref` |
| Retrying timeouts without readback | Duplicate side effects | Idempotency, reconciliation |
| Logging transport ACK only | Blind to downstream business results | Completion events / target evidence |

## 37. Practice Scenarios with Guided Resolutions

### Scenario A — HTTP Accepted Order, Nothing Appears in Kafka

Ingress logs show `corr-01`, yet no Kafka publish confirm appears.

**Resolution:** trace validate/transform/router checkpoints, inspect `QueueChannel`, outbound attempt IDs, producer callbacks, serialization errors, and broker availability. Never conclude Kafka received the record merely because a channel send returned true.

### Scenario B — Kafka Consumer Lacks Producer's Trace

Service A has a trace ID; service B consumes the record and starts a new trace ID while correlation IDs still match.

**Resolution:** check producer inject/consumer extract of tracing context, header mappers/serializers, and instrumentation on both services. Correlation already stitches the case in logs; fix tracing configuration rather than copying raw context manually.

### Scenario C — SFTP Poller Has Zero Correlation Logs

No new files download because remote authentication fails before the adapter creates any message.

**Resolution:** log `poll_ref`/session events with reason class `AUTH_FAILURE` and verify remote connectivity. Never expect `MessageHistory` or correlation headers for a message that was never created.

### Scenario D — Same JMSCorrelationID Across Two Different Messages

Two producers collide on `JMSCorrelationID` due to short timestamp-based IDs.

**Resolution:** review contract uniqueness/trust and never merge business events solely on `JMSCorrelationID`. Mint sufficiently unique opaque IDs and keep `JMSMessageID`/delivery attempts distinct.

### Scenario E — HTTP Timed Out Yet Payment Already Processed

Logs show `OUTBOUND_ATTEMPTED` followed by a timeout; an operator wants to retry immediately.

**Resolution:** record `UNKNOWN_OUTCOME` and check the idempotency key and remote state via an approved API. If remote committed, log confirmation/reconciliation rather than creating a second transaction.

### Scenario F — Correlation Lost After a Transformer

Custom code built `MessageBuilder.withPayload(...).build()` without preserving application headers.

**Resolution:** fix header propagation in the same-process flow and add tests. Avoid blindly copying framework headers across brokers; use a contract allowlist mapper.

### Scenario G — MDC Bleeds Into the Next Message

An executor pool reuses threads; message B's logs show message A's correlation.

**Resolution:** use context-aware executors/instrumentation and MDC scopes with cleanup/restore. Keep correlation inside the message and test sequential and concurrent message flows.

### Scenario H — Splitter Emits 500 Items, Aggregator Misses 3

Logs only hold batch correlation, hiding which items failed to complete.

**Resolution:** add parent/item lineage refs or safe sequence indices, per-item outcomes, and aggregation state/timeouts. Never print the entire batch to find 3 items or expect result history to hold every item path.

### Scenario I — JMS Redeliveries Produce 50 “Processed” Logs

A message rolls back repeatedly while the handler logs `PROCESSED` before transaction commit.

**Resolution:** rename the pre-commit log to `PROCESSING_ATTEMPTED` and emit `BUSINESS_COMPLETED` only after commit confirmation, separating redelivery attempts from unique outcomes. Test rollbacks explicitly.

### Scenario J — Kafka Keys Containing Emails Used as Metric Tags

Metric dashboards explode with millions of `kafka_key` series and leak customer data.

**Resolution:** remove unbounded/sensitive labels, keep bounded flow/target/outcome tags, and move opaque correlation to role-restricted logs/traces. Handle the data exposure incident per policy.

### Scenario K — File Outbound Writes File Yet Partner Hasn't Processed It

The app logs `FILE_SENT` right after writing to a local path while the partner hasn't read it yet.

**Resolution:** distinguish local write, remote handoff/rename, and business completion, adding callbacks/status checks if required by contract. Never equate outbound adapter success with end-to-end completion.

### Scenario L — Batch Database Polls Reprocess Rows After Crash

A DB poller selects rows, calls an API successfully, and the JVM crashes before marking rows processed; the next poll re-reads them.

**Resolution:** link both attempts via an authorized logical row reference, check remote outcomes, and enforce idempotency. Build durable checkpoints/outboxes or reconciliation as required; logs alone do not prevent duplicates.

### Scenario M — Tracing Sampled Out, Investigation Still Needed

A rare failing message lacks spans in the tracing backend due to sampling, yet structured logs hold correlation.

**Resolution:** look up logs by opaque reference, endpoint events, broker identity, and error class; use metrics to gauge scope. Never enable production-wide raw payload logging.

### Scenario N — ErrorMessage Lacks Original Message

An error handler lacks `originalMessage` at the failing checkpoint, leaving logs without correlation.

**Resolution:** inspect error flows and adapter/client context, preserving correlation at request/delivery attempts where permitted; before any Spring Message exists, use source poll/client refs. Never attach fabricated IDs to error events.

## 38. Design, Testing, and Operations Checklist

### 38.1. Contract Design

- [ ] Defined logical event, correlation reference, and ID-issuing owner?
- [ ] Distinguished business ID, trace ID, Spring Message ID, and attempt ID?
- [ ] Enforced trust boundaries and format validation on external ingress?
- [ ] Defined unambiguous `attempted/confirmed/completed/unknown/failed` taxonomy?
- [ ] Identified logging points when pollers/clients fail **before creating a Message**?
- [ ] Defined lineage for splitters/aggregators and DLQ replays?
- [ ] Implemented idempotency/reconciliation independent of correlation logs?

### 38.2. Flow and Adapter Configuration

- [ ] Application headers preserved across transformers/routers/filters per contract?
- [ ] `QueueChannel`/`ExecutorChannel` configured with context propagation and MDC cleanup?
- [ ] `WireTap` emits only safe projections, never raw `Message`?
- [ ] HTTP logs route templates—no tokens, bodies, or full URIs?
- [ ] File/SFTP uses opaque file references—no raw paths or secrets?
- [ ] JMS/AMQP reflects accurate broker message/delivery/ack semantics?
- [ ] Kafka uses proper header mapping, topic/partition/offset, and confirm semantics?
- [ ] JDBC marks queries, transactions, and commits at the right boundaries?
- [ ] Outbound header mappers forward only allowlisted headers and approved trace context?

### 38.3. Testing

- [ ] Tested fresh ingress, trusted producers, and untrusted/malformed headers?
- [ ] Verified logs contain zero synthetic secrets/PII or dangerous newline/control characters?
- [ ] Verified headers survive creating new messages?
- [ ] Verified retries mint new attempt IDs while preserving logical correlation?
- [ ] Tested timeouts after remote commit and redeliveries/replays?
- [ ] Verified split/aggregate branch lineage is traceable?
- [ ] Verified async threads never mix MDC across messages?
- [ ] Distinguished `no data` from `message lost` when telemetry fails?
- [ ] Treated message history/metrics/traces as supplements, never replacements for external state?

### 38.4. Incident Operations

- [ ] Queried the right flow, service, instance, time range, and correlation?
- [ ] Checked collectors, sampling, and dropped logs before assuming message loss?
- [ ] Inspected queue depth/age, retries/DLQ, and adapter health?
- [ ] Gathered ACK/commit/callback/transaction evidence at the target?
- [ ] Assigned owner and readback for `UNKNOWN_OUTCOME` before retrying?
- [ ] Never logged raw payloads during debugging or exception handling?
- [ ] Documented root cause, action items, tests, and closure evidence?

## 39. Conclusion

**Correlating logs between inbound and outbound** is an **observability contract**: each integration journey carries a sufficiently stable correlation ID, each attempt carries its own ID, each checkpoint has clear semantics, and every final outcome is confirmed at the proper layer. In Spring Integration, header propagation across `MessageChannel`s, transformers, routers, queues, gateways, and brokers must be designed intentionally; MDC and tracing help contextualize logs, yet never replace application headers or message contracts.

Across **File, SFTP, HTTP, JMS, AMQP, Kafka, and JDBC**, teams must respect protocol-specific milestones such as polls, file handoffs, request/reply, broker ACKs, offset commits, and database transactions. A log line reading `OUTBOUND_ATTEMPTED` or `TRANSPORT_CONFIRMED` does not prove `BUSINESS_COMPLETED`. Combining **sanitized structured logs, opaque correlation references, attempt/lineage IDs, Micrometer metrics, MessageHistory/tracing, and destination state verification** lets operations teams connect inputs to outputs, investigate retries and timeouts accurately, and reduce the risk of duplicated or lost data.
