# DISCONNECT, RECEIPT, and confirming STOMP protocol operations

STOMP is a frame-based message protocol that runs over a bidirectional connection such as TCP or WebSocket. When a client wants to close the connection, merely closing the socket does not guarantee that the server has received the frames the client just sent. STOMP provides **DISCONNECT** and **RECEIPT** so that the client can request a confirmed session close at the protocol level.

These two frames have different roles:

- **DISCONNECT** tells the server that the client wants to end the STOMP session.
- **RECEIPT** is the server's response to a client frame that requested a receipt with the **receipt** header.
- With DISCONNECT, the client sends a receipt token, waits for the server to return the matching **receipt-id**, and only then closes the transport.
- RECEIPT confirms that the server has processed the corresponding frame at the protocol level. It does not by itself prove that a consumer has finished the business processing or that the data has been durably stored according to the broker's policy.

This lesson focuses on STOMP 1.2 and how the Spring Framework supports receipts through the WebSocket STOMP client.

## 1. Where DISCONNECT and RECEIPT fit in STOMP

STOMP defines the frames the client sends to the server and the frames the server sends back to the client. A frame has a command, headers, a blank line separating the headers from the body, and a NULL character terminating the frame. DISCONNECT and RECEIPT have no body.

~~~text
Client                                      STOMP Server
  |                                               |
  | CONNECT                                       |
  |---------------------------------------------->|
  |                                               |
  | CONNECTED                                     |
  |<----------------------------------------------|
  |                                               |
  | SEND / SUBSCRIBE / ACK / ...                  |
  |---------------------------------------------->|
  |                                               |
  | RECEIPT (if frame requested receipt)          |
  |<----------------------------------------------|
  |                                               |
  | DISCONNECT                                    |
  |---------------------------------------------->|
  |                                               |
  | RECEIPT                                       |
  |<----------------------------------------------|
  |                                               |
  | Close socket                                  |
~~~

In STOMP 1.2:

- The client can send the **receipt** header on every client frame except CONNECT.
- The server sends a **RECEIPT** frame when it has successfully processed a frame that requested a receipt.
- The RECEIPT frame must have a **receipt-id** header carrying exactly the receipt value the client sent.
- The receipt header of DISCONNECT is optional.
- If the client has sent DISCONNECT, the client must not send any more STOMP frames on that connection.

Destination and delivery semantics still depend on the server/broker. STOMP does not itself define that a destination named /queue or /topic must behave the same on every broker.

## 2. DISCONNECT: requesting to end the STOMP session

**DISCONNECT** is the frame the client uses to announce that it wants to end the STOMP session. The client can close the socket directly, but that does not guarantee that the server has received the earlier frames.

The DISCONNECT frame has no body and no required headers:

~~~text
DISCONNECT

^@
~~~

In the example, the notation **^@** represents a single NULL byte that terminates the frame. This is an illustrative notation in the protocol documentation, not a character string that must be sent verbatim.

### Closing the connection directly

If the client closes the TCP/WebSocket right after sending a SEND, the following can happen:

1. The client has written the SEND frame into a local buffer.
2. The socket is closed before the frame reaches the server.
3. The client receives no response from which to know whether the server received it.
4. The application does not know whether the message was processed by the server.

Therefore, closing the socket directly is appropriate when the application accepts an uncertain outcome or already has its own recovery mechanism.

### Closing the connection with confirmation

For a graceful disconnect, STOMP 1.2 recommends that the client:

1. Send DISCONNECT with a receipt header.
2. Wait for a RECEIPT with a matching receipt-id.
3. After receiving the RECEIPT, close the socket.

Example:

~~~text
DISCONNECT
receipt:disconnect-77

^@
~~~

The server responds:

~~~text
RECEIPT
receipt-id:disconnect-77

^@
~~~

The client closes the transport only after it has received the corresponding RECEIPT frame. The receipt value is a correlation token chosen by the client; use a value that is unique among the pending receipts to avoid matching a response incorrectly.

### Do not send frames after DISCONNECT

After sending DISCONNECT, the client MUST NOT send any more frames. Therefore, complete the operations that need to be sent before issuing DISCONNECT:

~~~text
SEND
destination:/app/orders
receipt:send-1001

{"orderId":"ORD-1001"}^@

DISCONNECT
receipt:disconnect-1001

^@
~~~

The client waits for the receipt for DISCONNECT and only then closes the socket. Do not send any more SEND, SUBSCRIBE, ACK, or STOMP heartbeat after DISCONNECT.

## 3. The receipt header and the RECEIPT frame

The **receipt** header asks the server to confirm the processing of a client frame. Its value is an arbitrary string supplied by the client.

Example of the client sending SEND:

~~~text
SEND
destination:/queue/orders
content-type:application/json
receipt:send-2026-001

{"orderId":"ORD-1001"}^@
~~~

The server returns:

~~~text
RECEIPT
receipt-id:send-2026-001

^@
~~~

You can use a receipt with many types of client frames, for example SEND, SUBSCRIBE, UNSUBSCRIBE, ACK, COMMIT, or DISCONNECT, as long as the server supports the corresponding semantics.

### receipt and receipt-id

| Header | Direction | Role |
|---|---|---|
| **receipt** | Client → Server | The client asks the server to send a confirmation for this frame. |
| **receipt-id** | Server → Client | The server returns the receipt value so that the client knows which frame has been confirmed. |

These two headers are not message-id or a subscription id:

- **message-id** identifies a MESSAGE frame delivered by the server.
- **subscription** identifies the subscription that receives the MESSAGE.
- **receipt** is the token that requests confirmation of a client frame.
- **receipt-id** is the token the server uses to respond to that request.

You should create receipt IDs that can be traced in logs, for example based on the operation type and a UUID. Do not reuse the same token for multiple pending operations because the client will find it hard to distinguish the responses.

### Which frames does the server process?

The server sends RECEIPT when it has successfully processed a client frame that requested a receipt. If the frame has an error, the server can send ERROR. When the ERROR relates to a frame that has a receipt, the server should include the corresponding receipt-id in the ERROR so that the client can identify the operation that caused the error.

Not every server or broker supports receipts for every command. Check the broker documentation and the STOMP version negotiated in CONNECTED.

## 4. What does RECEIPT confirm?

RECEIPT confirms that the server has processed the corresponding client frame. Because STOMP transmits frames in an ordered stream, a receipt also confirms that the server has received all the frames before the confirmed frame.

However, there is one very important point: **the earlier frames may still not have been fully processed**.

Example:

~~~text
SEND receipt:send-1
SEND
SEND
DISCONNECT receipt:disconnect-1
~~~

When the client receives the RECEIPT for disconnect-1, the client can conclude that the server has received the frames that came earlier in the stream and has processed the DISCONNECT frame. The client must not infer that all downstream work from the two SEND frames has completed.

Three levels need to be distinguished:

1. **The frame has left the client:** the transport has accepted the data from the application or the client library.
2. **The server has received/processed the frame:** confirmed at the STOMP level by RECEIPT.
3. **The business has completed:** a consumer or downstream service has processed the data and confirmed it according to a separate business contract.

RECEIPT belongs to the second level. The third level requires an ACK, a reply, a result event, or a specially designed business confirmation mechanism.

### A RECEIPT for SEND is not a consumer confirmation

When the client sends SEND with a receipt and receives a RECEIPT, that does not by itself prove:

- The message has been received by a consumer.
- The consumer has finished running its handler.
- The consumer's database has committed.
- All subscribers have received the broadcast.
- The message has been durably stored according to the broker's specific policy.

STOMP leaves the delivery semantics and the durability of a destination to the server implementation. If the application needs confirmation that a consumer has finished processing, design a reply or a result event with a correlation ID and a business event ID.

### RECEIPT for SUBSCRIBE

A receipt for SUBSCRIBE can be used to know that the server has processed the subscription request. This is useful when the client needs to wait for the subscription to be established before it starts publishing or performs the next operation.

However, a receipt for SUBSCRIBE is only meaningful when the broker supports it. Spring's built-in simple broker does not support receipts; if you need broker-level subscription confirmation, use a full-featured broker through the STOMP broker relay and verify the broker's support.

## 5. RECEIPT differs from ACK, NACK, and ERROR

These frames are often confused because they all relate to confirmation or errors, but their direction and meaning differ.

| Frame | Direction | Purpose |
|---|---|---|
| **RECEIPT** | Server → Client | Confirms that the server has processed a client frame that has a receipt header. |
| **ACK** | Client → Server | Confirms that the client has consumed a MESSAGE in a subscription that uses explicit acknowledgment. |
| **NACK** | Client → Server | Reports that the client could not consume the MESSAGE. |
| **ERROR** | Server → Client | Reports a protocol error or a frame processing error; a STOMP 1.2 server closes the connection after ERROR according to the specification. |
| **CONNECTED** | Server → Client | Confirms that the STOMP connection has been established and the version negotiated. |

### ACK/NACK confirm message delivery

ACK/NACK relate to messages the server sends to the client through a subscription. The client only needs to send ACK when SUBSCRIBE uses:

- **ack:auto:** the server considers the message received as soon as it is sent to the client; the client does not send ACK.
- **ack:client:** the client sends ACK; the ACK is cumulative for the earlier unacknowledged messages of the subscription.
- **ack:client-individual:** ACK/NACK applies only to the corresponding message and does not acknowledge the earlier messages.

SUBSCRIBE example:

~~~text
SUBSCRIBE
id:orders-sub
destination:/queue/orders
ack:client-individual

^@
~~~

The server sends a MESSAGE with an ack header:

~~~text
MESSAGE
subscription:orders-sub
message-id:msg-901
ack:ack-token-901
destination:/queue/orders

{"orderId":"ORD-1001"}^@
~~~

The client confirms that the message has been processed:

~~~text
ACK
id:ack-token-901

^@
~~~

If the client cannot process it, it can send NACK:

~~~text
NACK
id:ack-token-901

^@
~~~

The server decides on redelivery, discard, or moving to a dead-letter queue according to the broker's policy.

### Can you request a receipt for ACK?

Yes. ACK is a client frame, so the client can add a receipt header if the broker supports it. In that case:

- ACK expresses that the client confirms it has consumed the MESSAGE.
- RECEIPT confirms that the server has processed that ACK frame.

These two things are different. A RECEIPT for ACK does not replace the acknowledgment meaning of ACK.

### ERROR and a missing receipt

If the server sends an ERROR related to a frame that has a receipt, the ERROR can carry a receipt-id to indicate the token of the frame that caused the error. STOMP 1.2 specifies that the server sends ERROR and then closes the connection.

If the client does not receive a RECEIPT before the timeout, it cannot conclude with certainty that the operation failed. It may be that the server did not receive the frame, the server processed it but the response was lost, the broker does not support receipts, or the connection was closed too early. Treat the result as undetermined and use idempotency/correlation to check before resending an operation that has side effects.

## 6. The complete graceful disconnect sequence

A client can use the following sequence when it finishes its work:

~~~text
1. Stop accepting new work at the application layer.
2. Complete or record the operations in progress.
3. Send the necessary final frames.
4. Send DISCONNECT with a unique receipt token.
5. Wait for a RECEIPT whose receipt-id matches the token.
6. Close the WebSocket/TCP socket.
~~~

Wire-level example:

~~~text
SEND
destination:/app/orders
receipt:send-order-1001
content-type:application/json

{"orderId":"ORD-1001"}^@

DISCONNECT
receipt:close-session-77

^@
~~~

Server responses:

~~~text
RECEIPT
receipt-id:send-order-1001

^@

RECEIPT
receipt-id:close-session-77

^@
~~~

In the example, the receipt for SEND confirms that the server has processed SEND. The receipt for DISCONNECT confirms that the server has processed DISCONNECT and cumulatively acknowledges the earlier frames it received. It still does not prove that a consumer has finished processing OrderCreated.

If the client only needs to close the session and accepts not waiting for confirmation, it can close the socket or use the ordinary disconnect API. If a graceful protocol shutdown is required, you must keep the transport open long enough to receive the right receipt.

### The server can close the socket too early

STOMP 1.2 describes connection lingering: the server can keep a closed connection for a short time to support clients that connect/disconnect quickly. If the server closes its end of the socket too early, the client may not receive the final RECEIPT for DISCONNECT.

Therefore:

- Set a finite timeout for waiting for the receipt.
- When the timeout expires, record the disconnect state as unconfirmed.
- Do not send more frames on a connection that has sent DISCONNECT.
- If you need to continue, create a new connection and check the business state using an event ID or a status request.
- Do not resend a business command just because no receipt was received, unless the command has an idempotency key.

## 7. The Spring WebSocket STOMP client and receipt callbacks

Spring provides **WebSocketStompClient** and **StompSession** to send/receive STOMP over WebSocket. When you need to track receipts for a SEND or SUBSCRIBE operation, Spring provides **StompSession.Receiptable**.

For receipt tracking to work, configure a **TaskScheduler** for the client. The scheduler is used to track the receipt deadline. The default wait time is 15 seconds; it can be changed with the receipt time limit.

### Configuring the client and TaskScheduler

~~~java
ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
scheduler.setPoolSize(1);
scheduler.setThreadNamePrefix("stomp-receipt-");
scheduler.initialize();

WebSocketStompClient stompClient =
        new WebSocketStompClient(new StandardWebSocketClient());

stompClient.setTaskScheduler(scheduler);
stompClient.setReceiptTimeLimit(5_000L);
~~~

This configuration snippet needs the Spring WebSocket dependency and a running WebSocket STOMP endpoint. In a Spring application, you should manage the scheduler as a bean so that Spring manages its lifecycle and shutdown.

### Tracking the receipt of SEND

~~~java
public class OrderStompSessionHandler extends StompSessionHandlerAdapter {

    @Override
    public void afterConnected(
            StompSession session,
            StompHeaders connectedHeaders
    ) {
        session.setAutoReceipt(true);

        StompSession.Receiptable receipt = session.send(
                "/app/orders",
                "{\"orderId\":\"ORD-1001\"}"
        );

        receipt.addReceiptTask(headers -> {
            System.out.println(
                    "SEND processed; receipt-id="
                            + headers.getFirst("receipt-id")
            );
        });

        receipt.addReceiptLostTask(() -> {
            System.err.println(
                    "No RECEIPT received before the configured timeout"
            );
        });
    }
}
~~~

When **setAutoReceipt(true)** is enabled, Spring automatically adds a receipt header to the subsequent SEND and SUBSCRIBE operations. The result of send is a Receiptable, which lets you register:

- **addReceiptTask:** a callback that runs when the RECEIPT is received.
- **addReceiptLostTask:** a callback that runs when the wait time expires without a receipt having been received.
- **getReceiptId:** gets the receipt token attached to the operation.

If you do not enable auto receipt, set the receipt manually on StompHeaders before calling the corresponding send/subscribe overload. If there is no receipt header, you cannot register a receipt callback on the Receiptable.

### Tracking the receipt of SUBSCRIBE

~~~java
StompSession.Subscription subscription = session.subscribe(
        "/topic/orders",
        new StompFrameHandler() {
            @Override
            public Type getPayloadType(StompHeaders headers) {
                return String.class;
            }

            @Override
            public void handleFrame(StompHeaders headers, Object payload) {
                System.out.println("received=" + payload);
            }
        }
);

subscription.addReceiptTask(headers -> {
    System.out.println(
            "SUBSCRIBE processed; receipt-id="
                    + headers.getFirst("receipt-id")
    );
});

subscription.addReceiptLostTask(() ->
        System.err.println("Subscription receipt timed out")
);
~~~

Spring's subscription handle also supports receipt tracking. Only use this callback when the STOMP server really supports receipts for SUBSCRIBE. Spring's built-in simple broker does not support receipts; check the broker relay and the actual broker.

### A special note on DISCONNECT in StompSession

The API **StompSession.disconnect(StompHeaders)** lets you pass the headers of DISCONNECT, but the method returns **void** and does not provide a Receiptable to wait for a receipt like send/subscribe do. In the Spring client implementation, the disconnect operation sends the frame and then resets/closes the transport connection. Therefore, you should not regard adding a receipt header to this call as a complete procedure for waiting for a RECEIPT.

If the mandatory requirement is to send DISCONNECT, receive the matching RECEIPT, and only then close the socket, use a STOMP client/transport that explicitly supports keeping the connection open to wait for the receipt, or manage the transport lifecycle yourself. With an ordinary StompSession, use disconnect() to close the session per Spring's API, and understand that it does not provide a callback to wait for a receipt for DISCONNECT.

## 8. Spring simple broker and external broker relay

Spring has a built-in simple broker for development and testing. It stores subscriptions in memory and broadcasts messages to the matching clients. The simple broker supports only part of the STOMP protocol and does not support ACK, receipts, and some other commands.

If the application needs:

- Receipts for SEND/SUBSCRIBE/DISCONNECT.
- Explicit ACK/NACK.
- Broker persistence, redelivery, or dead-letter.
- Multiple application nodes sharing a broker.
- Advanced delivery semantics.

Use a full-featured broker that supports STOMP and configure the **STOMP broker relay**. A specific broker may support additional headers or its own semantics; always check the documentation for the correct version of the broker.

Do not infer that receipts work just because the application has enabled STOMP over WebSocket. Receipt is a capability of the STOMP server/broker that the client is connecting to.

## 9. Server-side disconnect events in Spring

On the Spring WebSocket server side, **SessionDisconnectEvent** is published when the STOMP/WebSocket session ends. The event can occur because the client sent DISCONNECT or because the WebSocket transport closed.

A session can publish SessionDisconnectEvent more than once. The listener that handles this event must be idempotent, for example only remove the session state if the session still exists and do not repeat side effects.

Example:

~~~java
@Component
public class StompSessionEvents {

    private final SessionRegistry sessionRegistry;

    public StompSessionEvents(SessionRegistry sessionRegistry) {
        this.sessionRegistry = sessionRegistry;
    }

    @EventListener
    public void onDisconnect(SessionDisconnectEvent event) {
        sessionRegistry.removeIfPresent(event.getSessionId());
    }
}
~~~

**SessionDisconnectEvent is not a RECEIPT.** It is an internal server-side application event reporting that the session has ended. It does not prove that the client received a RECEIPT frame and does not confirm that a business message was processed by a consumer.

If you need to audit a client's request for a graceful disconnect, you can record the receipt token and the processing result at the protocol/broker layer. Do not use the disconnect event as a substitute for a protocol receipt.

## 10. Timeout, retry, and idempotency

A receipt timeout is a common situation in network systems. The client may not receive a receipt because:

- The broker has not processed the frame.
- The broker processed it but the response was lost.
- The connection was cut before the frame reached the server.
- The server does not support receipts for that command.
- The server closed the connection too quickly after DISCONNECT.
- The client-side scheduler or receipt time limit is configured inappropriately.

On a timeout, the operation's state is **undetermined**. You should not assume by default that the operation failed and immediately resend a command that has side effects.

### A safe handling pattern

1. Every business command has a stable eventId or idempotency key.
2. The client attaches a separate receipt token to the frame to correlate the protocol response.
3. If a RECEIPT is received, record that the server has processed the frame according to STOMP semantics.
4. If a timeout or transport error occurs, keep the state undetermined.
5. Reconnect if needed and query the business state by eventId.
6. Only resend when the consumer/server can deduplicate or when you determine with certainty that the command has not been applied.

The receipt token and the eventId have different purposes:

| Value | Scope | Purpose |
|---|---|---|
| receipt | STOMP frame | Correlates a client frame with a RECEIPT. |
| receipt-id | STOMP response | Indicates which receipt request the server confirmed. |
| eventId | Business contract | Identifies the event/command in order to deduplicate and query the result. |
| correlationId | Request/reply flow | Links a request with a response or related operations. |

Do not use receipt-id as a long-lived business key. A receipt belongs to a single STOMP exchange and does not replace the event ID.

## 11. Common mistakes

1. **Closing the socket right after SEND and assuming the server received the message.** A TCP/WebSocket close does not provide STOMP processing confirmation for the earlier frames.
2. **Sending DISCONNECT without waiting for a receipt when a graceful shutdown is needed.** The client may close the connection before the server receives the final frames.
3. **Sending more frames after DISCONNECT.** STOMP 1.2 forbids the client from sending more frames on that connection.
4. **Confusing a receipt with ACK.** RECEIPT confirms that the server processed a client frame; ACK confirms that the client consumed a MESSAGE.
5. **Thinking RECEIPT means the consumer finished processing.** A receipt does not confirm downstream business processing or a database commit.
6. **Thinking a receipt for the last frame confirms that all earlier frames have finished processing.** A receipt is a cumulative acknowledgment that the earlier frames have been received by the server; they may not yet have been fully processed.
7. **Not matching receipt-id with the receipt token.** You may mistake responses when multiple operations are pending.
8. **Using the same receipt token for multiple pending requests.** The client finds it hard to distinguish the receipts.
9. **Enabling setAutoReceipt but not configuring a TaskScheduler.** Spring needs a scheduler to track receipt timeouts.
10. **Not handling addReceiptLostTask.** When no receipt is received, the application does not know whether the operation had a result.
11. **Assuming the simple broker supports receipts.** Spring's built-in simple broker does not support receipts and ACK; you need a full-featured broker when using those features.
12. **Using StompSession.disconnect(StompHeaders) as an API that waits for a receipt.** The method returns void and does not provide a Receiptable; the Spring client closes the transport after sending DISCONNECT.
13. **Treating SessionDisconnectEvent as a protocol receipt.** It is a server-side lifecycle event, can be published multiple times, and needs idempotent handling.
14. **Retrying immediately after a receipt timeout.** The result may be undetermined; you need an eventId, idempotency, and a state check before resending.
15. **Not checking broker-specific semantics.** STOMP standardizes frames, but command support and delivery semantics still depend on the server.

## 12. Key takeaways

- **DISCONNECT** requests ending the STOMP session.
- **RECEIPT** is the server's response to a client frame that has a receipt header; receipt-id must match the receipt value.
- For a graceful disconnect, send DISCONNECT with a receipt, wait for the matching RECEIPT, and then close the socket.
- After sending DISCONNECT, the client must not send any more frames.
- RECEIPT confirms processing at the protocol level and is a cumulative acknowledgment that the server has received the earlier frames; it does not prove that all downstream work has completed.
- **ACK/NACK** confirm whether the client has or has not consumed a MESSAGE; their meaning differs from RECEIPT.
- Spring's StompSession supports Receiptable for SEND/SUBSCRIBE; it needs a TaskScheduler and has timeout tracking.
- The built-in simple broker does not support receipts; you need to check the capabilities of the external broker.
- StompSession.disconnect(StompHeaders) does not provide a Receiptable to wait for a DISCONNECT receipt.
- SessionDisconnectEvent is a server lifecycle event, not a RECEIPT.
- When a receipt times out, treat the result as undetermined; use an idempotency key and check the business state before retrying.

When building a STOMP client, decide clearly which operations need a receipt, which operations need a business ACK, and when the transport can be closed. Use receipts to confirm the protocol, use events/replies to confirm the business, and only close the connection after completing the shutdown sequence that the application requires.

## References

- [STOMP Protocol Specification 1.2 — Header receipt, DISCONNECT and RECEIPT](https://stomp.github.io/stomp-specification-1.2.html)
- [Spring Framework 6.2 — STOMP Client](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/client.html)
- [Spring Framework 6.2 — StompSession API](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/messaging/simp/stomp/StompSession.html)
- [Spring Framework 6.2 — StompSession.Receiptable API](https://docs.spring.io/spring-framework/docs/6.2.x-SNAPSHOT/javadoc-api/org/springframework/messaging/simp/stomp/StompSession.Receiptable.html)
- [Spring Framework 6.2 — Simple Broker](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/handle-simple-broker.html)
- [Spring Framework 6.2 — Application Context Events](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/application-context-events.html)
