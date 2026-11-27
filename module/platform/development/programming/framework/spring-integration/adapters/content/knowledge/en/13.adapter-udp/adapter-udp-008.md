# Handling packet loss and UDP unreliability in Spring Integration

## Learning objectives

After this lesson, you will be able to:

- Accurately explain **UDP**'s limitations regarding delivery, ordering, duplication, acknowledgment, and load control.
- Distinguish between a packet that **never reached the socket**, a datagram that **arrived truncated**, a message **rejected during parsing**, and a message **received but failing business processing**.
- Use `deviceId`, `epoch`, and `sequence` to detect **missing sequence gaps**, while understanding why an observed gap does not prove permanent packet loss.
- Configure a UDP inbound adapter, `MessageChannel`, and service activator to validate, measure, and identify late-arriving or potentially duplicate packets.
- Design **ACKs, bounded retries, idempotency, and durable storage** when an event must not be lost.
- Decide when to accept UDP's *best effort* and when to use HTTP, JMS, AMQP, Kafka, files/SFTP, or another delivery mechanism.
- Test missing-packet, out-of-order, duplicate, network-error, and receiver-restart scenarios using observable steps.

This lesson belongs to the **Adapter UDP** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module connects external systems via inbound/outbound adapters, gateways, pollers, and `MessageChannel`, while establishing message contracts, error handling, and connection lifecycles with files, SFTP, HTTP, JMS, AMQP, Kafka, and databases. UDP is a clear illustration of the principle: **an adapter brings data into the message flow, but reliability depends on both the transport protocol and the business contract**.

## 1. The problem: device sends 1,000 events, collector processes only 990

A sensor sends measurements every second or faster over UDP to a Spring Boot collector:

~~~text
device=node-7;epoch=boot-42;seq=1001;value=26.5
device=node-7;epoch=boot-42;seq=1002;value=26.6
device=node-7;epoch=boot-42;seq=1003;value=26.5
device=node-7;epoch=boot-42;seq=1004;value=26.7
~~~

The collector runs `UnicastReceivingChannelAdapter`, receives `Message<byte[]>`, and forwards it into a `MessageChannel`. During an observation window, the sender reports calling send 1,000 times, while storage contains only 990 records.

**Do not immediately conclude that UDP dropped exactly 10 packets.** You must distinguish:

1. Did the sender **actually build and hand all 1,000 datagrams to the network stack**?
2. Did each datagram **reach the receiving host and arrive at the UDP socket**?
3. Did the UDP inbound adapter **read and emit a message** for each received datagram?
4. Did the `byte[]` converter **reject packets for bad size, framing, encoding, or schema**?
5. Did the service **write to the DB successfully**, or did a transaction fail or roll back?
6. Were there **retransmissions/duplicates**, **out-of-order** arrivals, or did the sender **reboot and reset its sequence**?

~~~mermaid
flowchart LR
    A["Sender<br/>sends datagram"] --> B["IP network / firewall / NAT"]
    B --> C["UDP socket<br/>and kernel buffer"]
    C --> D["UDP inbound adapter"]
    D --> E["MessageChannel"]
    E --> F["Decode + validate"]
    F --> G["Service + DB"]
    A -.-> L1["Measure send_attempt"]
    C -.-> L2["Measure received"]
    F -.-> L3["Measure rejected"]
    G -.-> L4["Measure committed"]
~~~

An unpersisted message may have been lost on the network, dropped before the socket, rejected in the converter, or failed downstream. The remediation for each case **is different**.

## 2. What does "unreliable" mean in UDP?

UDP is a connectionless datagram protocol providing none of TCP's retransmission or ordering guarantees. One send call corresponds to one datagram; the sender's OS can accept a send call while the datagram still never arrives.

| Property | Guaranteed by UDP? | Implication for Spring Integration |
|---|---|---|
| Datagrams delivered to receiver | **No** | If a packet is lost before the socket, the inbound adapter has no message to emit |
| Datagrams arrive in order | **No** | A handler may observe sequences 10, 12, then 11 |
| No duplicate packets at application layer | **No** | Retries or upstream mechanisms can duplicate data; receiver needs IDs to detect them |
| ACK from receiver | **No** | Must implement an application-layer ACK protocol or use compatible ACK options between endpoints |
| Retry on packet loss | **No** | Must define a retransmission policy, timeouts, and durable retention for retries |
| Backpressure to sender | **No** | When the receiver is overloaded, datagrams may be dropped without telling the sender |
| Durable storage/replay | **No** | Socket/kernel buffers are not durable queues |
| Per-datagram boundaries | **Yes** | Receiver reads discrete data units, not a TCP byte stream |
| UDP/IP checksum | Detects some transmission bit errors | Does not imply security, sender auth, or reliable delivery |

`MessageChannel.send(...)` returning `true` on the sender only indicates message dispatch per channel semantics. Even if the outbound UDP handler sends the datagram without throwing an exception, that still **does not confirm** the receiver received, parsed, or persisted the data.

### 2.1. Where can datagram loss occur?

- **Sender side:** improperly serialized data, wrong address/port, DNS failures, or no subscriber in the integration flow.
- **Sender socket layer:** kernel/send buffer limits, interface configuration, and local I/O errors.
- **Network path:** congestion, router/switch drops, firewall policies, NAT timeouts, unreassembled IP fragments.
- **Receiving host:** full kernel receive buffer, port not bound yet, stopped listener, or ongoing restart.
- **Spring Integration:** receive/dispatch errors, slow synchronous handlers, full downstream queues, mapper/framing errors.
- **Business layer:** invalid UTF-8/JSON, rejected data, DB errors, transaction rollbacks, or retries creating duplicates.

Name each failure category accurately. **A packet that never reaches the socket** cannot enter Spring Integration's `errorChannel` because the application never constructed a `Message` from it.

### 2.2. Do checksums and framing solve packet loss?

**No.** Checksums help detect certain bit corruptions in transit. Spring Integration UDP's **length check** option can prepend a length prefix so the receiver detects some datagrams truncated by a receive buffer.

Neither mechanism **asks the network to resend a datagram**, guarantees ordering, or confirms business processing. When a datagram is completely lost, the receiver has no bytes to check length against.

## 3. Why sequences aid observability but are not absolute proof

The UDP protocol provides no business sequence numbers. The sender can add them itself:

~~~text
device=node-7;epoch=boot-42;seq=1001;value=26.5
~~~

Where:

- **`device`**: device identifier per contract; must be authenticated if the environment requires it.
- **`epoch`**: identifier for a boot session or sequence generation, preventing confusion when the sender resets its counter.
- **`seq`**: monotonically increasing sequence number **within one epoch of one device**.
- **`value`**: business payload—in this example, a temperature or reading.

### 3.1. Scenarios you may encounter

| Received sequence | Observation | What cannot be concluded yet |
|---|---|---|
| 101, 102, 103 | Consecutive | Does not prove every prior packet arrived |
| 101, 103 | Missing gap at 102 | 102 might arrive late, sender skipped 102, or it was lost |
| 101, 103, 102 | 102 arrives after 103 | **Reordering** occurred; not necessarily packet loss |
| 101, 102, 102 | Same sequence appears twice | Possible duplicate/retry; requires ID/epoch to confirm |
| 101, 102, 1 | Sequence drops abruptly | Sender may have rebooted/reset or a stale packet arrived late |
| boot-42: 101, boot-43: 1 | New epoch started | Do not merge two counters into one continuous sequence range |

An observed **gap** should be marked as *gap observed*, not immediately as *permanent packet loss*. A system can wait through a **reordering window** by time or sequence count before estimating packet loss.

### 3.2. Sequence and event ID

To recognize duplicates across restarts, an event's key should be sufficiently stable, such as:

~~~text
(deviceId, epoch, seq)
~~~

If a sender has multiple independent streams, a **stream ID** may also be needed. If IDs can be reused after wrapping or resetting, define explicit epoch and rollover rules.

UDP source IP/port is unsuitable as a long-term key because it can change due to NAT, DHCP, mobile networks, or ephemeral ports; a single public IP can also represent multiple devices.

## 4. Designing three delivery expectation tiers

| Model | How it works | Strengths | Trade-offs |
|---|---|---|---|
| **Best effort** | Send UDP once, no ACK/retry required | Low latency and overhead; fits latest-value readings | Lost packets may never be recovered |
| **Application-level at-least-once** | Sender retains events, retries until matching ACK arrives | Can recover from many packet/ACK losses | Receiver may see duplicates; requires idempotency |
| **Exactly-once business effect** | At-least-once + unique key/transaction on receiver | Avoids duplicate business writes within design scope | Costs durable state and transaction coordination; not native to UDP |

Do not call the third option **UDP exactly-once delivery**. Both sides can achieve **once-only write effect** via DB idempotency, while the network may still deliver packets multiple times; correctness also depends on transactions, event identity, retention, replay, and other side effects.

**Choose based on data semantics:**

- Latest temperature sent periodically: losing some packets is usually acceptable; display the latest reading and monitor freshness.
- Cumulative counters: send the **current running total** instead of individual deltas for easier recovery after packet loss.
- Unlock commands, payments, or non-skippable business events: require processing confirmation, durable storage, deduplication, and usually a more reliable protocol/broker.
- Real-time audio/video: use adaptive codecs, jitter buffers, sequences, error correction, or specialized protocols rather than retransmitting stale packets.

## 5. Configuring the UDP inbound adapter and MessageChannel

This hands-on example uses **Spring Boot**, **Spring Integration IP**, **Java 17+**, and UDP port `12018`. With Spring Boot dependency management, typically add:

~~~xml
<!-- pom.xml: inside <dependencies> -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-ip</artifactId>
</dependency>
~~~

Create a flow receiving UDP and pushing bytes to a channel:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.ip.dsl.Udp;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class UdpLossDemoConfig {

    @Bean("udpRawTelemetry")
    public MessageChannel udpRawTelemetry() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow udpLossInboundFlow() {
        return IntegrationFlow.from(
                    Udp.inboundAdapter(12018)
                        .receiveBufferSize(2048)
                        .lengthCheck(false))
                .channel("udpRawTelemetry")
                .get();
    }
}
~~~

In the example:

1. `Udp.inboundAdapter(12018)` listens for unicast UDP datagrams.
2. `receiveBufferSize(2048)` is the capacity for reading **one datagram**, not a queue for multiple packets.
3. `lengthCheck(false)` matches senders using raw UTF-8 UDP. Only enable `lengthCheck(true)` when both sender and receiver use Spring Integration framing.
4. `DirectChannel` dispatches messages synchronously; handlers must have a clear policy if processing is slow or throws errors.
5. No poller is needed to read datagrams; the inbound adapter is socket-driven, whereas pollers are only needed for other sources like scheduled file/DB checks.

Increasing `receiveBufferSize` reduces the risk of *truncating large packets*, yet cannot recover packets lost on the network or datagrams dropped by the kernel due to a full socket receive queue.

## 6. Building the contract and parser to observe sequences

Sample payload:

~~~text
device=node-7;epoch=boot-42;seq=1001;value=26.5
~~~

Define the DTO:

~~~java
import java.math.BigDecimal;

public record TelemetryDatagram(
        String deviceId,
        String epoch,
        long sequence,
        BigDecimal value) {
}
~~~

Parser converting raw bytes to the DTO and rejecting invalid packets:

~~~java
import java.math.BigDecimal;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public final class TelemetryDatagramParser {

    private TelemetryDatagramParser() {}

    public static TelemetryDatagram parse(byte[] bytes) {
        if (bytes.length == 0 || bytes.length > 512) {
            throw new IllegalArgumentException(
                    "UDP payload length outside 1..512 bytes");
        }

        final String text;
        try {
            text = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes))
                    .toString();
        } catch (CharacterCodingException ex) {
            throw new IllegalArgumentException(
                    "Malformed UTF-8 telemetry", ex);
        }

        String[] parts = text.split(";", -1);
        if (parts.length != 4
                || !parts[0].startsWith("device=")
                || !parts[1].startsWith("epoch=")
                || !parts[2].startsWith("seq=")
                || !parts[3].startsWith("value=")) {
            throw new IllegalArgumentException(
                    "Unexpected telemetry schema");
        }

        String device = parts[0].substring("device=".length());
        String epoch = parts[1].substring("epoch=".length());
        String seqText = parts[2].substring("seq=".length());
        String valueText = parts[3].substring("value=".length());

        if (!device.matches("[A-Za-z0-9_-]{1,32}")
                || !epoch.matches("[A-Za-z0-9_-]{1,40}")
                || !seqText.matches("\\d{1,18}")
                || !valueText.matches("-?\\d{1,3}(\\.\\d{1,2})?")) {
            throw new IllegalArgumentException(
                    "Invalid telemetry field");
        }

        long seq = Long.parseLong(seqText);
        BigDecimal value = new BigDecimal(valueText);
        return new TelemetryDatagram(device, epoch, seq, value);
    }
}
~~~

The parser only guarantees **size, charset, schema, and field formatting**. It **does not** prove the datagram came from a legitimate device or arrived in order. In production, add message/device authentication, version checks, measurement thresholds, epoch checks, and per-source quotas.

With `lengthCheck(true)`, Spring Integration can use a 4-byte length prefix to detect truncated datagrams; using it requires compatible settings on both sender and receiver. The parser cannot recover bytes already lost before it is called.

## 7. Tracking gaps and late packets in a Service Activator

The following observer tracks the **highest sequence** seen per `deviceId + epoch`. It is for observability, not yet a financial-grade deduplicator or message recovery mechanism.

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.ip.IpHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class UdpSequenceObserver {

    private static final Logger log =
            LoggerFactory.getLogger(UdpSequenceObserver.class);

    // Demo: in-memory state, not durable across restarts.
    private final ConcurrentMap<String, Long> highestByStream =
            new ConcurrentHashMap<>();

    @ServiceActivator(inputChannel = "udpRawTelemetry")
    public void observe(Message<byte[]> message) {
        final TelemetryDatagram event;
        try {
            event = TelemetryDatagramParser.parse(message.getPayload());
        } catch (IllegalArgumentException ex) {
            log.warn("Rejected UDP telemetry: {}", ex.getMessage());
            return;
        }

        String sourceIp = message.getHeaders()
                .get(IpHeaders.IP_ADDRESS, String.class);
        String key = event.deviceId() + "|" + event.epoch();

        highestByStream.compute(key, (stream, previous) -> {
            if (previous == null) {
                log.info("First sequence in stream={}, seq={}, source={}",
                        stream, event.sequence(), sourceIp);
                return event.sequence();
            }

            if (event.sequence() > previous) {
                if (event.sequence() - previous > 1L) {
                    log.warn(
                        "GAP_OBSERVED stream={}, missing-range={}..{}",
                        stream, previous + 1L, event.sequence() - 1L);
                }
                return event.sequence();
            }

            log.info(
                "LATE_OR_DUPLICATE stream={}, seq={}, highest={}",
                stream, event.sequence(), previous);
            return previous;
        });

        // Deciding to write DB/ACK is a separate application step.
        // Do not treat highestByStream as a complete deduplication mechanism yet.
    }
}
~~~

For a given `device+epoch` key, `ConcurrentHashMap.compute(...)` updates state atomically within the process's map. However:

- A `seq` smaller than `highest` could be a **late packet**, not necessarily a duplicate. Distinguishing them requires storing seen sequences within a **bounded window**.
- A gap can be filled later when a delayed packet arrives. Apply a *grace period* or window before reporting "permanent loss".
- When running multiple instances, each instance sees a different subset of packets. Local in-memory state is **not cluster-wide data**.
- If a sender reboots and changes epoch, a new stream begins; if epoch stays unchanged while `seq` resets, the observer will misclassify it.
- Without evicting inactive streams, the map can grow unboundedly. Production must apply TTL/retention and cap stream count.
- Observation logic **does not replace unique constraints or idempotency** when duplicate writes are disallowed.

This example is for detection and tracking, not a complete at-least-once solution.

## 8. Sending test packets to observe gaps, reordering, and repeats

Start the application with the classes above, open PowerShell on the same host, and send sequences **1, 2, 4, 3, 4** in order:

~~~powershell
$client = [System.Net.Sockets.UdpClient]::new()

try {
    foreach ($seq in @(1, 2, 4, 3, 4)) {
        $text = "device=node-7;epoch=boot-42;seq=$seq;value=26.5"
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($text)

        [void]$client.Send(
            $bytes, $bytes.Length, "127.0.0.1", 12018)
    }
}
finally {
    $client.Dispose()
}
~~~

Over loopback when all packets arrive in send order, illustrative logs are:

~~~text
First sequence in stream=node-7|boot-42, seq=1
GAP_OBSERVED stream=node-7|boot-42, missing-range=3..3
LATE_OR_DUPLICATE stream=node-7|boot-42, seq=3, highest=4
LATE_OR_DUPLICATE stream=node-7|boot-42, seq=4, highest=4
~~~

**Interpreting the result accurately:** the example above **deliberately sends non-consecutive sequences** in the order `[1, 2, 4, 3, 4]`. It illustrates how the observer detects and classifies patterns, **not a measurement of real network packet loss**. When real UDP drops a datagram, no automatic "datagram dropped" log appears in Spring because no corresponding message exists.

Additional experiments:

1. Send `1, 2, 3, 4` to observe a normal consecutive stream.
2. Send `1, 3` and wait a reasonable interval to observe an unfilled gap.
3. Send `1, 3, 2` to observe how a gap can be closed by a late-arriving packet.
4. Resend `3` multiple times to verify the observer does not treat it as a newer message.
5. Change `epoch=boot-43` and send `seq=1` to simulate a device reboot.
6. Stop the listener, send a few sequences, start it again, and keep sending; observe the consequences of having no listening socket.

`UdpClient.Send` completing **does not prove** the receiver received anything. For network tests, combine packet captures at both sender and receiver, sequences, socket/adapter metrics, and DB write results.

## 9. Estimating packet loss using sequence numbers

When **you genuinely know the sender emitted a full consecutive range**, such as `seq=1..1000`, the receiving side can calculate:

~~~text
Expected sequence count   = 1000
Unique sequences received = 990
Unobserved sequence count = 10

Unobserved rate = 10 / 1000 = 1%
~~~

The **1%** here is the unobserved rate in the evaluated window, which approximates packet loss only if assumptions hold: the sender truly sent all 1,000 events in the same epoch; no sequences were skipped; the receiver waited past the reordering window; duplicates were removed; and versions/epochs were not mixed.

If the collector persisted 990 DB records while the inbound adapter received 998 datagrams, the 8 missing records **may be due to validation rejections or downstream errors**. Maintain separate metrics per stage:

| Suggested metric | Meaning |
|---|---|
| `udp_send_attempt_total` | How many datagrams the sender attempted to send |
| `udp_send_local_error_total` | Encoding/dispatch/socket send errors at the sender |
| `udp_receive_total` | How many messages the inbound adapter received and forwarded |
| `udp_invalid_payload_total` | Packets rejected for size, encoding, framing, or schema |
| `udp_sequence_gap_observed_total` | Initially observed sequence gaps |
| `udp_sequence_late_total` | Messages with sequence lower than highest seen |
| `udp_duplicate_confirmed_total` | True duplicates confirmed via ID/seen-set or DB unique key |
| `udp_business_committed_total` | Events successfully committed by business logic |
| `udp_ack_timeout_total` | Sender ACK wait timeouts when ACK is enabled |

Do not emit a new `deviceId` or `IP:port` metric label for unbounded numbers of devices; cardinality will explode. Use sampled traces/logs or appropriate aggregations instead.

## 10. Do ACKs and retries make UDP reliable?

**They can**, though the added reliability comes from the **application protocol**, durable state, and error handling implemented by both sides. UDP does not provide it automatically.

~~~mermaid
sequenceDiagram
    participant S as Sender
    participant N as UDP network
    participant R as Receiver
    participant D as Database

    S->>N: eventId=abc, seq=42
    N->>R: Datagram
    R->>D: Validate + idempotent INSERT
    D-->>R: Transaction committed
    R-->>S: ACK(eventId=abc)
    Note over S: If no ACK arrives before timeout
    S->>N: Retry same eventId=abc
    N->>R: Duplicate datagram may arrive
    R->>D: Check unique key / no-op
    R-->>S: ACK(eventId=abc) again
~~~

**An ACK protocol should clearly specify:**

- Is the ACK sent when the **socket receives the packet**, when the **parser succeeds**, or only after **transaction commit**?
- Which **event ID/sequence**, version, identity, and authentication info does the ACK contain?
- How long does the sender wait, how many retries are attempted, and are *exponential backoff + jitter* and rate limits applied?
- Where does the sender store events for retries across restarts? In RAM or a **durable outbox/queue**?
- How does the receiver handle receiving the same event multiple times?
- When an ACK is lost after the DB already committed, how will the retrying sender receive the ACK again?
- What is the retention period for deduplication IDs and pending state?

**Technical ACK differs from business ACK.** If the receiver replies immediately upon reading the datagram while the DB fails afterward, the sender may consider the event complete even though data was never saved.

### 10.1. Packet loss and ACK loss create two different scenarios

| Scenario | What sender sees | Receiver reality | Required handling |
|---|---|---|---|
| Datagrams never arrive | ACK timeout | No event | Sender retries per policy |
| Datagram arrives, ACK lost | ACK timeout | May already be committed | Sender retries; receiver is idempotent and re-ACKs |
| Datagram arrives, DB fails | ACK timeout or protocol NACK | Not committed | Retry after underlying error resolves |
| ACK arrives late | May already have retried | One or more copies reached receiver | Match ACK by ID, deduplicate |
| Sender restarts before ACK | Pending events lost if RAM-only | Receiver state unknown | Durable outbox and pending recovery |

A successful send call **does not confirm an ACK**, and a received ACK only carries the meaning of **the timing and contract** promised by the receiver.

### 10.2. ACKs supported by Spring Integration UDP

Spring Integration includes an optional **UDP application-level acknowledgment** mechanism between compatible endpoints, using settings such as `acknowledge`, ACK address/port, `ack-timeout`, and for multicast `min-acks-for-success` in supported versions.

When using this option, sender and receiver must both understand the library's ACK framing. It **does not automatically mean "database committed"**, does not turn UDP into a durable broker, and does not provide exactly-once effects for your business logic.

In multicast, **requiring ACKs from every receiver** risks an *ACK implosion* when hundreds/thousands of receivers respond simultaneously. `min-acks-for-success` only sets a **minimum ACK threshold** and does not guarantee every group member processed the event. Consider another reliable distribution mechanism when per-subscriber confirmation is required.

## 11. Receiver idempotency: how to prevent duplicate writes?

If a sender retries the same event, the receiver can receive multiple identical datagrams. An effective control is a **unique key in durable storage**.

PostgreSQL example:

~~~sql
CREATE TABLE udp_telemetry (
    device_id    text NOT NULL,
    epoch        text NOT NULL,
    seq          bigint NOT NULL,
    measured_val numeric(12, 2) NOT NULL,
    received_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (device_id, epoch, seq)
);
~~~

When receiving a validated event, write inside a transaction:

~~~sql
INSERT INTO udp_telemetry (device_id, epoch, seq, measured_val)
VALUES ('node-7', 'boot-42', 42, 26.5)
ON CONFLICT (device_id, epoch, seq) DO NOTHING;
~~~

If the key already exists, the duplicate record **is not inserted again**. If the system has other side effects like publishing to Kafka or calling HTTP, design those too so retries do not duplicate side effects; a unique constraint on one DB table does not automatically prevent side effects in external systems.

**Critical ordering when ACK means "durably saved":**

1. Parse, check version/schema, and authenticate the sender.
2. Open an appropriate transaction.
3. Insert the record using the **idempotency key**; handle duplicates per policy.
4. Commit the transaction successfully.
5. Only then send the **business ACK** with the same event ID.

If an ACK is sent **before commit** and the process crashes, the sender may purge the pending event while the DB never saved it. If commit succeeds but the ACK is lost, the sender may retry; the receiver should return an ACK for the existing valid record if the contract allows.

**Never send NACKs to arbitrary untrusted datagrams** without source and size controls, because UDP source IPs can be spoofed and the system could become a UDP reflector.

## 12. Where does the sender store events for retries?

If the sender only keeps events in an in-memory `ConcurrentHashMap`, a process restart wipes out pending items. A more reliable pattern is a **durable outbox**:

~~~mermaid
flowchart TD
    A["Business source"] --> B["Persist event + outbox"]
    B --> C["Sender reads pending"]
    C --> D["UDP outbound handler"]
    D --> E["Network / Receiver"]
    E --> F["Validate + idempotent commit"]
    F --> G["ACK by event ID"]
    G --> H["Mark outbox complete"]
    C --> I{"ACK timeout?"}
    I -->|Yes| J["Bounded retry / backoff"]
    J --> D
~~~

Minimal fields in an outbox:

~~~text
event_id, destination, payload_bytes, attempt_count,
next_attempt_at, state, created_at, last_error
~~~

Rules:

- Delete or mark complete only upon receiving a valid **contract-compliant ACK**.
- On timeout, do not assume the packet was definitely lost; retry using the **same event ID**.
- Cap retry count/age and pending queue size; add metrics and handling for permanently undeliverable events.
- When sending to multiple destinations, store state per **event + destination** so one receiver's ACK does not satisfy all.
- Do not push schema-invalid payloads into infinite retries; deterministic errors usually require fixing data, not retransmission.
- When the sender restarts, reload pending items according to persisted state.

Spring Integration helps wire `MessageChannel` and adapters into this pipeline. However, reliable persistence and retry coordination require an appropriate DB/broker and transactions; an in-memory `QueueChannel` is not durable on its own.

## 13. Why are backoff and retry limits necessary?

If a collector goes down for 30 seconds, thousands of senders retrying continuously can overwhelm the collector the instant it returns.

A sound strategy usually includes:

| Measure | Purpose |
|---|---|
| **Reasonable ACK timeout** | Matches RTT and committed processing latency, avoiding premature timeouts |
| **Exponential backoff** | Increases intervals between consecutive retries |
| **Jitter** | Prevents many senders from retrying at the exact same instant |
| **Max attempts or max age** | Avoids retaining failing messages indefinitely |
| **Rate limiting** | Stays within network and receiver capacity |
| **Circuit breaker / controlled pause** | Sheds load when destination fails continuously, if applicable to architecture |
| **Dead-letter / quarantine** | Investigates failures unresolvable by retries |
| **Metrics and alerts** | Monitors pending queues, retry counts, ACK latency, commit rates |

Timeout values, retry counts, and retention must align with business requirements. "Latest-value" telemetry can discard stale readings; critical state-changing commands require stronger contracts.

## 14. Packet loss, reordering, and data handling policies

Handling depends not just on UDP, but also on **event semantics**:

| Data type | If one packet is lost | If a packet arrives late | Recommended handling |
|---|---|---|---|
| **Gauge**: current temperature | Next new reading supersedes it | Drop stale packet so it does not overwrite newer values | Update only when sequence/timestamp is newer |
| **Cumulative counter** | Next total reading compensates | Check for rollover/reset | Send running total and epoch |
| **Delta**: increment by +1 | Change may be lost permanently | Must preserve ordering/dedup logic | ACK/retry/idempotency or broker |
| **Command**: open/close device | Lost command is a severe failure | Late execution can be dangerous | Command ID, TTL, auth, post-execution ACK |
| **Realtime stream** | Loss can be partially concealed | Too-late packets are useless | Jitter buffer, sequences, late-drop policy |
| **Financial data** | Zero loss permitted | Must never apply twice | Durable transport, transactions, and idempotency |

If the business only needs the **latest state**, enforce a "newer sequence wins" rule. If you must **accumulate every delta**, dropping old packets corrupts totals and requires stronger delivery guarantees. Distinguish these two event types before writing retry logic.

### 14.1. Timestamps do not replace sequences

Timestamps help gauge freshness, yet clocks across devices can drift, jump, or resynchronize. Sequences within an epoch are better suited for detecting transmission-order gaps; timestamps remain useful alongside them for **event time**, deadlines, and data freshness.

### 14.2. Reorder window and memory limits

To distinguish `late` from `duplicate`, a receiver can keep seen sequences in a **bounded window** (for example, by time or the last 256 sequences). Once old events age out of the window, the system may no longer have enough state to verify prior arrival.

Never keep every sequence forever in RAM. For transactions requiring reliability, use IDs and durable storage with an appropriate **unique constraint** to enforce idempotency.

## 15. Managing lifecycle and shutdown with UDP

A UDP inbound adapter only receives while its socket is listening. When a service stops, restarts, redeploys a container, or a port is blocked by a firewall, the sender may still call `send()` without error while the receiver gets no messages.

~~~mermaid
sequenceDiagram
    participant S as UDP sender
    participant A as Old receiver
    participant B as New receiver
    S->>A: seq=100
    Note over A: stop / shutdown
    S-->>A: seq=101 (may be lost)
    Note over B: start + bind socket
    S->>B: seq=102
    Note over B: observer detects missing gap 101
~~~

You must manage:

1. **Actual readiness**: application startup does not mean the listener has bound. Observe `UdpServerListeningEvent` or `isListening()` per your version's API.
2. **Stop/start window**: datagrams arriving while no listener exists are not replayed automatically.
3. **In-flight work**: if downstream uses `ExecutorChannel` or queues, stopping the listener does not mean all messages have committed.
4. **Rolling deployments**: if packet loss during instance handovers is unacceptable, guarantee delivery at the sender/orchestrator or move to a broker.
5. **Multicast**: group joins/network memberships and interfaces can change on restart; verify joins and test packet reception.

`SO_TIMEOUT` only governs the wait duration of one socket `receive()` call; it **does not make the sender retry**, prevent packet loss while stopped, or replace business processing timeouts.

## 16. Security: ACKs and retries can be abused

A UDP endpoint receiving packets from untrusted sources must consider:

- **Source IP/port can be spoofed** on some networks. Never authenticate devices solely via `ip_address` or `ip_packetAddress`.
- **Returning ACKs larger than requests** creates UDP reflection/amplification risk. Keep replies small, rate-limit, and validate sources/messages.
- **Replay:** replaying an old datagram can trigger duplicate side effects without event IDs, nonces/epochs, and deduplication.
- **Flooding:** large volumes of datagrams can fill socket buffers, queues, and logging pipelines. Bound byte sizes, rates, source counts, and CPU usage.
- **Malformed payloads:** parsers must check UTF-8, size, schema, and value ranges before expensive work.
- **Sensitive data:** plain UDP is unencrypted. Use appropriate authentication/encryption or protected networks when needed.
- **Forged ACKs:** if a sender trusts unauthenticated ACKs, it may drop pending events the real receiver never saw; bind ACKs to event IDs and trusted sources.

Never deploy an unauthenticated public echo/ACK service, and never use ephemeral source ports as long-term identities.

## 17. Layer-by-layer diagnostics when suspecting packet loss

| Symptom | Where to inspect | Useful evidence |
|---|---|---|
| Sender logs success but receiver has no logs | IP/port, DNS, firewall, routes, NAT, socket bind | Packet captures at both ends |
| Loss occurs only on large payloads | PMTU, IP fragmentation, receive-buffer-size | Datagram length, packet capture, framing config |
| Loss occurs under high load | Kernel UDP queue, CPU, synchronous handlers, executor backlog | UDP drop counters, send/receive rates, handler duration |
| Gap appears then gets filled | UDP reordering or concurrent processing | Sequences, event time, and reorder window |
| Same event appears multiple times | Sender retries, app workflow, event duplication | Event ID, attempt count, unique key |
| DB missing records even though adapter received | Parser, filter, transactions, DB/broker outage | Reject/commit metrics, exceptions, and rollbacks |
| ACK timeout while DB has record | ACK lost or delayed after commit | Receiver logs by event ID and idempotency |
| Missing data after deploy | Receiver not ready, stopped socket, UDP load balancer | Lifecycle/readiness and sequence gaps |
| Multicast received by A but not B | Membership, IGMP, interface, switch/router, TTL | Captures/IGMP joins on each host |

**Separate three critical statements:**

- "Sender called send" does not prove "receiver received".
- "Receiver got a datagram" does not prove "message is valid".
- "Message is valid" does not prove "business work committed".

Separating these lets you place metrics and recovery at the right layer.

## 18. Meaningful testing

### 18.1. Testing parser and observer

Test deterministic inputs:

- `seq=1,2,3`: no gap reported.
- `seq=1,3`: reports gap 2.
- `seq=1,3,2`: sequence 2 arrived late; must not be declared permanently lost.
- `seq=1,2,2`: observer detects stale/possible duplicate; deduplication needs seen state.
- `epoch=boot-42, seq=100` then `epoch=boot-43, seq=1`: do not merge the two epochs.
- Payload >512 bytes, invalid UTF-8, bad schema: parser rejects without writing business records.

Observer unit tests need no sockets; to verify Spring Integration binders/headers, run integration tests with a real UDP client.

### 18.2. Testing network and overload

In a **controlled lab environment**, run a sender emitting consecutive sequences and track **how many the sender actually generated/sent**. Measure at the receiver how many unique sequences arrived after the reorder window. Simulate network loss with test-environment network-impairment tools or lab firewalls, then compare packet captures on both sides.

Avoid testing network impairments on production networks. Merely sending `1,2,4` only simulates a **sequence gap**, not proof that the network dropped datagram 3.

### 18.3. Testing retry after ACK loss

1. Receiver receives event `abc` and commits it to the DB.
2. In a test environment, intentionally withhold the first ACK.
3. Sender times out and resends **the same event ID**.
4. Receiver identifies the duplicate via unique key and does not insert a second row.
5. Receiver returns the proper ACK; sender marks the pending item complete.
6. Restart sender/receiver while items are pending to verify durability and recovery behavior.

This is a meaningful integration test for an at-least-once model. Checking `UdpClient.Send` alone is insufficient to validate the whole protocol.

## 19. Comprehensive practice exercise

Design an application performing **receive UDP telemetry → validate → persist to database → send business ACK**, with the contract:

~~~text
v=1;device=node-7;epoch=boot-42;seq=1042;value=26.5
~~~

Implementation steps:

1. Add `v` to the parser and validate version before constructing the DTO.
2. Configure `Udp.inboundAdapter(12018)`, receiving `Message<byte[]>` and validating size/UTF-8/schema.
3. Track **highest sequence** to observe gaps; then design a **seen window** to distinguish late packets from duplicates within a bounded range.
4. Persist events into a DB with `PRIMARY KEY(device, epoch, seq)` or a suitable idempotency key; use transactions to prevent duplicate writes.
5. Send the ACK meaning "durably saved" only after commit; if a valid duplicate event already exists, return an ACK for the same event ID.
6. On the sender, maintain a pending outbox, retrying with timeout/backoff/jitter and a retry cap.
7. Simulate packet loss, ACK loss, a 10-second receiver stop, sender restarts, and schema-invalid payloads. Record metrics at every step.
8. Compare the effort and effectiveness against publishing directly to Kafka/AMQP/JMS or calling HTTP with business ACKs.

**Self-assessment questions:**

- Why does `MessageChannel.send() == true` not mean the collector persisted the event?
- Why is `seq=10, 12` insufficient to conclude `11` is permanently lost?
- When receiving a sequence lower than `highest`, how do you distinguish late from duplicate?
- Why must the sender retry with the same event ID?
- If the ACK is lost after DB commit, how do you prevent retries from creating extra rows?
- Why does an in-memory `QueueChannel` not guarantee preserving events across a process crash?
- Why does increasing the UDP receive buffer not recover datagrams lost in transit?
- With multicast, why does an ACK from one receiver not guarantee every receiver succeeded?
- When should you accept best effort, and when must you choose a reliable broker/transport?
- If the source is file/SFTP/DB using a poller followed by outbound UDP, where should retry state live so polled events are not lost?

## 20. References

- [Spring Integration Reference — UDP Adapters](https://docs.spring.io/spring-integration/reference/ip/udp-adapters.html): unicast/multicast, length check, ACK, inbound/outbound UDP adapters.
- [Spring Integration Reference — IP Configuration Attributes](https://docs.spring.io/spring-integration/reference/ip/endpoint-reference.html): receive buffer, acknowledgment, timeout, and error channel.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): semantics of `DirectChannel`, executor, and queue channels.
- [RFC 768 — User Datagram Protocol](https://www.rfc-editor.org/rfc/rfc768): UDP datagram definition.
- [RFC 8085 — UDP Usage Guidelines](https://www.rfc-editor.org/rfc/rfc8085): guidelines for safe UDP use, packet sizes, congestion, retransmission, and timeouts.
- [RFC 8900 — IP Fragmentation Considered Fragile](https://www.rfc-editor.org/rfc/rfc8900): risks of relying on IP fragmentation.

## Conclusion

**UDP does not guarantee that datagrams arrive, arrive in order, arrive without duplicates, or are processed successfully.** In Spring Integration, inbound/outbound adapters and `MessageChannel` provide the structure to connect and process messages, yet cannot recover a datagram lost before reaching the application.

Start with a **payload contract carrying ID/epoch/sequence**, measure send/receive/validate/commit independently, and distinguish transient gaps from long-term missing data. When the application requires higher reliability, implement business ACKs, bounded retries, a durable outbox, and idempotency—or choose HTTP, JMS, AMQP, Kafka, or another suitable transport. The right solution depends on whether the business **can discard stale readings** or **must record every single event**.
