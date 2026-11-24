# ACK, NACK, and transaction frames in STOMP according to broker capabilities

STOMP provides the ACK, NACK, BEGIN, COMMIT, and ABORT frames so that a client can acknowledge message processing and group send/acknowledge operations in a transaction on the message server side.

These frames only take effect when the broker supports them. Spring's simple broker implements only a subset of STOMP and does not support ACK, NACK, RECEIPT, and the corresponding transaction features. When explicit acknowledgement or transaction frames are needed, a Spring application usually has to relay STOMP to an external broker that supports those features.

Three layers must be distinguished:

- **STOMP protocol:** defines frame syntax and the meaning of ACK, NACK, and transactions.
- **Broker:** decides how redelivery, requeue, dead-letter, persistence, and transactions are executed.
- **Application:** decides when a message is considered successfully processed, how to prevent duplicates, and how to coordinate with a database or other services.

## 1. Message receiving flow and acknowledgement

A STOMP client subscribes to a destination with SUBSCRIBE. The ack header chooses how the server considers a message acknowledged.

~~~text
SUBSCRIBE
id:orders-sub
destination:/queue/orders
ack:client-individual

<NUL>
~~~

Valid ack values in STOMP 1.2:

| Value | Behavior |
| --- | --- |
| auto | The client does not need to send ACK. The server considers the message delivered when sending MESSAGE to the client. |
| client | The client must send ACK. One ACK acknowledges the specified message and all earlier messages on the same subscription that have not been ACKed/NACKed. This is cumulative acknowledgement. |
| client-individual | The client must send ACK for each message. ACKing one message does not acknowledge other messages. |

If the ack header is not specified, the default value is auto.

### Why can auto lose messages?

In auto mode, the server does not wait for the application to finish processing. When the server sends MESSAGE down the connection, it considers the message delivered. If the browser or client process stops before saving data or executing business logic, the message may already be considered consumed.

Example:

1. The broker sends MESSAGE to the client.
2. The client receives the frame into the socket.
3. The browser tab is closed before saving the data.
4. The broker has no ACK to know that the application did not process it.

For work that requires processing confirmation, use client or client-individual if the broker supports it.

### MESSAGE frame with an ack token

When a subscription requires explicit acknowledgement, the broker sends MESSAGE with an ack header. Example:

~~~text
MESSAGE
subscription:orders-sub
message-id:msg-42
ack:ack-42
destination:/queue/orders
content-type:text/plain

order-42
<NUL>
~~~

There are three different values:

- subscription: the ID of the registered subscription.
- message-id: the ID of the message issued by the server/broker.
- ack: the token used to acknowledge or reject the message.

In STOMP 1.2, ACK/NACK must use the value from the ack header of MESSAGE. Do not take message-id in place of the ack token on your own.

## 2. ACK: confirming a message has been processed

ACK notifies the server that the client has consumed the message. With STOMP 1.2, the ACK frame has a required header id:

~~~text
ACK
id:ack-42

<NUL>
~~~

The id value must match the ack header in the corresponding MESSAGE.

### ACK in each mode

With ack:client:

~~~text
MESSAGE
subscription:orders-sub
message-id:msg-41
ack:ack-41
destination:/queue/orders

order-41
<NUL>

MESSAGE
subscription:orders-sub
message-id:msg-42
ack:ack-42
destination:/queue/orders

order-42
<NUL>

ACK
id:ack-42

<NUL>
~~~

ACK for ack-42 also acknowledges message ack-41 that was sent earlier on the same subscription if it had not been ACKed/NACKed. This is cumulative behavior.

With ack:client-individual, ACK ack-42 acknowledges only the second message. Message ack-41 remains unacknowledged and can be redelivered if the connection is lost.

### When should ACK be sent?

The client should send ACK after completing the processing step that the application considers successful. For example, if processing includes saving an order to the database, commit the database before sending ACK to avoid acknowledging the message and then losing data if the database fails.

However, if the database has already committed and the connection is lost before the broker receives the ACK, the message can be delivered again. Therefore, the consumer needs idempotency or duplicate detection. ACKing once does not create exactly-once processing for the whole business operation.

### STOMP 1.1 and STOMP 1.2 differ on the ACK header

| Version | ACK header |
| --- | --- |
| STOMP 1.1 | Uses message-id and subscription |
| STOMP 1.2 | Uses id, with the value taken from the ack header of MESSAGE |

The client and broker can negotiate the version via CONNECT/STOMP and CONNECTED. When supporting multiple versions, let the STOMP client library handle wire-format differences; do not send headers from another version yourself.

## 3. NACK: rejecting or reporting inability to process a message

NACK is a negative acknowledgement. The client sends NACK when it cannot process a message:

~~~text
NACK
id:ack-43

<NUL>
~~~

In STOMP 1.2, the id header must match the ack token on MESSAGE. NACK can also carry a transaction header.

NACK tells the broker that the message was not consumed successfully. However, STOMP does not mandate a single redelivery policy. The broker may:

- Put the message back on the queue for redelivery.
- Deliver the message to another consumer.
- Discard the message.
- Move the message to a dead-letter queue.
- Apply a retry delay, delivery limit, or custom policy.

The exact behavior depends on the broker, destination, and subscription configuration.

### NACK with client and client-individual

In ack:client, NACK has a cumulative effect on the specified message and the earlier messages on the same subscription that have not yet been ACKed/NACKed.

In ack:client-individual, NACK applies only to the specified message. Other messages keep their own acknowledgement states.

Therefore, if a consumer processes multiple messages in parallel and one message fails, client-individual is usually easier to control. With cumulative mode, ACKing/NACKing one message can affect the messages before it.

### Do not use NACK as an infinite retry loop

If the error is transient, NACK and redelivery may be appropriate. If the message has bad data or violates the schema, sending NACK continuously can create a hot loop.

An error-handling policy should define:

- Maximum number of attempts.
- Backoff interval between attempts.
- Condition to distinguish transient errors from data errors.
- Dead-letter destination.
- How to record message ID, correlation ID, and delivery count.
- Operational procedures to inspect and replay messages from the DLQ.

Some brokers have their own headers showing the redelivery count or dead-letter reason. These are not standard headers shared across every STOMP server.

## 4. BEGIN, COMMIT, and ABORT: broker-side transactions

STOMP 1.2 defines transaction frames to group send and acknowledge operations. A transaction is created within a STOMP connection and identified by a transaction ID.

Start a transaction:

~~~text
BEGIN
transaction:tx-1

<NUL>
~~~

Send and ACK/NACK operations can participate in the transaction with the transaction header:

~~~text
SEND
destination:/queue/audit
transaction:tx-1
content-type:text/plain

processed:order-42
<NUL>

ACK
id:ack-42
transaction:tx-1

<NUL>
~~~

Complete the transaction:

~~~text
COMMIT
transaction:tx-1

<NUL>
~~~

If you want to cancel the transaction:

~~~text
ABORT
transaction:tx-1

<NUL>
~~~

### What does a transaction group?

According to STOMP 1.2, a transaction applies to sending messages and acknowledging messages. For example, a consumer can:

1. Receive a message with explicit ack.
2. Start transaction tx-1.
3. Send an event to the audit destination, attached to transaction tx-1.
4. ACK the received message, also attached to tx-1.
5. COMMIT tx-1.

If the broker supports transactions according to the specification, sending the event and the ACK are processed atomically within the scope of the broker transaction.

| Outcome | Meaning on the broker side |
| --- | --- |
| COMMIT succeeds | The SENDs and ACK/NACKs attached to the transaction are applied transactionally |
| ABORT | The operations added to the transaction are canceled according to broker semantics |
| Connection closes while transaction is uncommitted | STOMP 1.2 requires uncommitted transactions to be implicitly aborted |
| Broker fails mid-commit | The outcome observed by the client depends on the broker, connection recovery, and receipt; check state before retrying |

The transaction ID must be specified in BEGIN, COMMIT, and ABORT. The ID used in SEND, ACK, and NACK frames must point to a transaction already opened on the same connection. Within the same connection, transaction IDs must be distinct.

A STOMP transaction is not a system-wide transaction. It does not automatically include a database, HTTP request, file, or another broker.

## 5. Combining ACK and SEND in the same transaction

A common use case is to consume a message and then publish a result. If you only ACK first and then SEND afterwards, what can happen is:

1. The broker receives ACK and removes the message from the queue.
2. The application loses the connection before SENDing the result.
3. The original message was acknowledged, yet the result event was never emitted.

If you only SEND first and then ACK afterwards, what can happen is:

1. The broker receives the result SEND.
2. The application loses the connection before ACKing the original message.
3. The original message is redelivered and the application may send the result again.

A STOMP transaction lets you attach both SEND and ACK to the same transaction:

~~~text
MESSAGE
subscription:orders-sub
message-id:msg-42
ack:ack-42
destination:/queue/orders

order-42
<NUL>

BEGIN
transaction:tx-42

SEND
destination:/queue/processed
transaction:tx-42
content-type:text/plain

processed:order-42
<NUL>

ACK
id:ack-42
transaction:tx-42

COMMIT
transaction:tx-42

<NUL>
~~~

If the broker fully supports transaction semantics, the broker applies both operations on commit. If the transaction is aborted, the broker cancels the SEND and does not apply the ACK; the original message may be delivered again according to the delivery policy.

This only protects the broker operations that participate in the transaction. If the processing also writes to a database, the database is not automatically inside the STOMP transaction.

## 6. What does RECEIPT confirm?

A client can request a receipt with the receipt header on a frame. Example:

~~~text
COMMIT
transaction:tx-42
receipt:commit-42

<NUL>
~~~

The broker responds:

~~~text
RECEIPT
receipt-id:commit-42

<NUL>
~~~

RECEIPT indicates that the server has processed the corresponding frame. With COMMIT, a receipt is useful to know that the broker has processed the commit request.

However, a receipt is not confirmation that a downstream consumer has processed a business event, that a database has updated, or that a downstream service has completed. It also does not by itself replace a recovery mechanism if the connection is lost before the client receives the receipt.

If the client sends COMMIT and then loses the connection before receiving RECEIPT, the client may not know whether the commit was applied by the broker or not. When retrying, you need to design idempotent operations or check the transaction/message status as supported by the broker.

## 7. Limitations of Spring's simple broker

Spring's simple broker is enabled with:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.enableSimpleBroker("/topic", "/queue");
}
~~~

The simple broker stores subscriptions in the memory of the application instance and emits messages to connected subscribers. It is suitable for simple pub/sub needs.

The simple broker supports only a subset of STOMP. It does not support ACK, NACK, RECEIPT, and the corresponding advanced broker features. Therefore, you should not enable ack:client or send BEGIN/COMMIT/ABORT and expect the simple broker to provide transactional acknowledgement.

The fact that the STOMP decoder recognizes the ACK or BEGIN command does not mean the broker handler executes that command's semantics. Parsing frames and broker support are two different things.

When explicit acknowledgement, redelivery, transactions, durable subscriptions, or dead-letter queues are needed, use an external broker and Spring's STOMP broker relay.

## 8. Using STOMP broker relay with an external broker

Relay configuration:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");

    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("broker.internal")
            .setRelayPort(61613)
            .setClientLogin("web-client")
            .setClientPasscode("external-secret")
            .setSystemLogin("spring-system")
            .setSystemPasscode("system-secret");
}
~~~

The Spring relay forwards STOMP frames between WebSocket clients and the broker over TCP. The external broker is what decides ACK/NACK, transaction, redelivery, persistence, and dead-letter semantics.

Before deploying, check the documentation of the specific broker:

- Does the broker support STOMP 1.2 or which version?
- Does it support ack:auto, client, and client-individual?
- Which headers do ACK/NACK use according to the negotiated version?
- Does NACK requeue, drop, or move to a DLQ?
- Does it support BEGIN/COMMIT/ABORT?
- Does a transaction group both SEND and ACK/NACK?
- Do transaction IDs have limits or timeouts?
- Are there limits on unacknowledged messages, prefetch, or inflight messages?
- Are there delivery counts, retry delays, and dead-letter policies?
- Does it support receipts for COMMIT?

Do not infer a broker's capabilities just because it opens a STOMP port or the Spring relay starts up successfully. The relay forwards the protocol; it does not add missing broker features on its own.

### Distinguishing application destinations from broker destinations

In a Spring configuration there are usually two groups of destinations:

- /app/** are routed to the application's @MessageMapping methods.
- /topic/** and /queue/** are forwarded to the broker.

A client's STOMP transaction frames apply to broker operations that the client sends directly and that the broker supports. Messages going through /app/** controllers are an application processing flow. Do not assume a transaction ID sent by the client automatically wraps controller methods, database transactions, or messages that the server sends through the relay's system connection.

## 9. Distinguishing STOMP transactions from Spring @Transactional and JMS transactions

These mechanisms have different goals and scopes:

| Mechanism | Scope | Who controls it |
| --- | --- | --- |
| STOMP BEGIN/COMMIT/ABORT | SENDs and ACK/NACKs participating in a transaction on a STOMP connection | STOMP client and broker |
| Spring @Transactional | Transactions managed by the Spring transaction manager for methods/services | Spring application |
| JMS local transaction | Operations on a transacted JMS Session | JMS client/container |
| JTA/XA | Multiple XA resources enlisted in a distributed transaction | Transaction coordinator |

STOMP is a wire-level protocol. It does not implicitly invoke Spring's PlatformTransactionManager. Conversely, an @Transactional method in a controller does not automatically turn a STOMP ACK frame into an operation within the same broker transaction.

If the system uses a STOMP broker relay to a JMS broker, a STOMP client's transaction also depends on the broker's STOMP adapter and how the broker maps operations to internal resources. Do not treat a STOMP transaction and a JMS Session transaction as the same API.

## 10. Designing a safe consumer when ACKing/NACKing

### Acknowledge after processing succeeds

With explicit ack mode, the common processing order is:

1. Receive MESSAGE.
2. Validate the payload and access permissions.
3. Execute the business logic.
4. Persist the state or result durably.
5. Send ACK.

If the business logic fails transiently, send NACK or let the connection close depending on the broker semantics. If the error is unrecoverable, put the message in the DLQ or mark it as failed according to the broker workflow.

### Idempotency and duplicate detection

The broker can redeliver a message when the client loses its connection, the ACK does not reach the broker, or the transaction is aborted. Therefore, the consumer should use a message ID, business key, or idempotency key to recognize that a message has already been processed.

For example, when processing a payment command, the database can store a unique request ID. If the message is delivered again, the consumer checks that the ID is already completed and does not perform the charge again.

### Cumulative ACK needs care during parallel processing

With ack:client, ACKing one message acknowledges all earlier messages on the same subscription. If the application processes in parallel and a later message finishes before an earlier message, ACKing the later message can mistakenly acknowledge an earlier message that is still being processed.

For parallel processing, consider client-individual if the broker supports it. If using cumulative mode, maintain processing/ack order or redesign concurrency.

### Prefetch and unacknowledged limits

Some brokers send multiple messages to a client ahead of time before receiving ACKs. The number of inflight messages can be controlled by prefetch or a similar broker limit.

If the client processes slowly, too many inflight messages can increase memory, redelivery time, and the number of messages held on the connection. Configure limits according to processing capacity and target latency. The configuration names and semantics are broker-specific.

## 11. Java 17+ example: parsing ACK/NACK and transaction frames with Spring StompDecoder

The following example uses StompDecoder to read STOMP 1.2 frames. It helps observe the command, destination, subscription, ack token, id, and transaction header.

The program only parses frames; it does not connect to a broker and does not execute ACK or COMMIT.

Create the file src/main/java/example/StompAckTransactionFrameDemo.java:

~~~java
package example;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.List;

import org.springframework.messaging.Message;
import org.springframework.messaging.simp.stomp.StompDecoder;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;

public class StompAckTransactionFrameDemo {

    private static void decode(String label, String frame) {
        StompDecoder decoder = new StompDecoder();
        List<Message<byte[]>> messages = decoder.decode(ByteBuffer.wrap(
                frame.getBytes(StandardCharsets.UTF_8)));

        if (messages.size() != 1) {
            throw new IllegalStateException(label + ": expected one frame, got "
                    + messages.size());
        }

        StompHeaderAccessor headers =
                StompHeaderAccessor.wrap(messages.get(0));

        System.out.println(label + ".command=" + headers.getCommand());
        System.out.println(label + ".destination=" + headers.getDestination());
        System.out.println(label + ".subscription="
                + headers.getSubscriptionId());
        System.out.println(label + ".ackToken=" + headers.getAck());
        System.out.println(label + ".id="
                + headers.getFirstNativeHeader("id"));
        System.out.println(label + ".transaction="
                + headers.getFirstNativeHeader("transaction"));
    }

    public static void main(String[] args) {
        decode("subscribe", "SUBSCRIBE\nid:orders-sub\n"
                + "destination:/queue/orders\nack:client-individual\n\n\u0000");

        decode("message", "MESSAGE\nsubscription:orders-sub\n"
                + "message-id:msg-42\nack:ack-42\n"
                + "destination:/queue/orders\ncontent-type:text/plain\n\n"
                + "order-42\u0000");

        decode("begin", "BEGIN\ntransaction:tx-1\n\n\u0000");

        decode("send", "SEND\ndestination:/queue/audit\n"
                + "transaction:tx-1\ncontent-type:text/plain\n\n"
                + "processed:order-42\u0000");

        decode("ack", "ACK\nid:ack-42\ntransaction:tx-1\n\n\u0000");

        decode("commit", "COMMIT\ntransaction:tx-1\n\n\u0000");

        decode("nack", "NACK\nid:ack-43\n\n\u0000");

        decode("abort", "ABORT\ntransaction:tx-2\n\n\u0000");
    }
}
~~~

Create pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>stomp-ack-transaction-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>7.0.10</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>example.StompAckTransactionFrameDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Run from the directory containing pom.xml:

~~~bash
mvn -q clean compile exec:java
~~~

Stdout output:

~~~text
subscribe.command=SUBSCRIBE
subscribe.destination=/queue/orders
subscribe.subscription=orders-sub
subscribe.ackToken=client-individual
subscribe.id=orders-sub
subscribe.transaction=null
message.command=MESSAGE
message.destination=/queue/orders
message.subscription=orders-sub
message.ackToken=ack-42
message.id=null
message.transaction=null
begin.command=BEGIN
begin.destination=null
begin.subscription=null
begin.ackToken=null
begin.id=null
begin.transaction=tx-1
send.command=SEND
send.destination=/queue/audit
send.subscription=null
send.ackToken=null
send.id=null
send.transaction=tx-1
ack.command=ACK
ack.destination=null
ack.subscription=null
ack.ackToken=null
ack.id=ack-42
ack.transaction=tx-1
commit.command=COMMIT
commit.destination=null
commit.subscription=null
commit.ackToken=null
commit.id=null
commit.transaction=tx-1
nack.command=NACK
nack.destination=null
nack.subscription=null
nack.ackToken=null
nack.id=ack-43
nack.transaction=null
abort.command=ABORT
abort.destination=null
abort.subscription=null
abort.ackToken=null
abort.id=null
abort.transaction=tx-2
~~~

The output shows that MESSAGE contains the ack token ack-42, while ACK uses the native header id with the same value. The transaction ID is read from the transaction header of BEGIN, SEND, ACK, COMMIT, and ABORT.

## 12. Integration testing with a real broker

StompDecoder only checks syntax and how Spring parses headers. To verify that a broker supports acknowledgement or transactions, you need an integration test with the exact broker/version/configuration of the runtime environment.

A test scenario should include:

1. Open a STOMP connection and negotiate the version.
2. SUBSCRIBE with ack:client-individual.
3. Send a message to the destination.
4. Confirm that MESSAGE has an ack header.
5. ACK the message and confirm that the broker does not redeliver it.
6. Send another message and then NACK it; verify requeue, redelivery, or DLQ according to policy.
7. BEGIN a transaction, SEND an audit message, and ACK the original message in the same transaction.
8. COMMIT and verify that both operations have been applied.
9. Repeat with ABORT; verify that SEND is canceled and the original message has not been acknowledged.
10. Disconnect while the transaction is uncommitted; verify that the broker aborts the transaction according to STOMP 1.2.
11. Test losing the connection before/after COMMIT to check the case where the client does not receive RECEIPT.
12. Check inflight/prefetch limits, retry count, and DLQ.

You should run both the happy path and network failures. Results must be verified on the real broker or consumer, not just from client logs.

## 13. Common mistakes

1. **Using ACK with ack:auto.** An auto subscription does not require ACK; the server already considers the message delivered when sending MESSAGE.
2. **Using message-id instead of the ack token in STOMP 1.2.** ACK/NACK must use the id header matching the MESSAGE ack header.
3. **Using STOMP 1.1 ACK headers on a STOMP 1.2 connection.** 1.1 uses message-id/subscription; 1.2 uses id.
4. **Assuming NACK always redelivers.** The broker may requeue, deliver to another consumer, drop, or dead-letter.
5. **Using ack:client during parallel processing.** A cumulative ACK may acknowledge an earlier message that is still being processed.
6. **Assuming the simple broker supports ACK/NACK.** Spring's simple broker does not support explicit ack/receipt.
7. **Sending BEGIN/COMMIT to the simple broker and expecting a transaction.** The decoder recognizing the frame does not mean the simple broker executes the transaction.
8. **Using a transaction ID on a different connection.** A transaction belongs to the connection that opened it.
9. **Forgetting to attach the transaction header to SEND/ACK/NACK.** Those operations will not belong to the open transaction.
10. **Thinking COMMIT RECEIPT confirms business processing.** A receipt confirms that the server processed the frame; it does not prove the database or downstream service has finished.
11. **Thinking a STOMP transaction includes the database.** Transaction frames only group message broker operations according to broker capabilities.
12. **Thinking @Transactional automatically controls STOMP ACK.** The Spring transaction manager and STOMP broker transactions are two separate mechanisms.
13. **Not handling connection loss around COMMIT.** The client may not know whether the commit was applied; idempotency and recovery are needed.
14. **Not limiting retries or handling poison messages.** Repeated NACKs can create a loop and high load.
15. **Not checking the broker version/capabilities.** The same frame can have different semantics or limits across brokers.

## 14. Deployment checklist

- Negotiate and verify the STOMP version.
- Choose ack:auto, client, or client-individual according to processing requirements.
- With STOMP 1.2, take the ACK/NACK id from the MESSAGE ack header.
- Only send ACK after the application completes the processing step that needs protection.
- Use NACK according to the broker's verified retry/DLQ policy.
- Verify that the broker supports ACK/NACK, receipt, and transaction frames.
- Only group SEND and ACK/NACK when the broker supports the required transaction semantics.
- Keep the transaction ID within the same STOMP connection and do not reuse IDs within that connection.
- Use RECEIPT to know that the broker processed a frame, not as business acknowledgement.
- Use idempotency to tolerate redelivery and an unknown COMMIT outcome due to connection loss.
- Test a real broker with ACK, NACK, COMMIT, ABORT, reconnect, and DLQ.
- Do not assume a STOMP transaction automatically includes Spring @Transactional, a database, or a JMS Session transaction.

## 15. References

- [STOMP Protocol Specification 1.2](https://stomp.github.io/stomp-specification-1.2.html)
- [Spring Framework 7.0 – External Broker Relay](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework 7.0 – Simple Broker](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/handle-simple-broker.html)
- [Spring Framework – StompDecoder Javadoc](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/messaging/simp/stomp/StompDecoder.html)
- [Spring Framework – StompHeaderAccessor Javadoc](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/messaging/simp/stomp/StompHeaderAccessor.html)
