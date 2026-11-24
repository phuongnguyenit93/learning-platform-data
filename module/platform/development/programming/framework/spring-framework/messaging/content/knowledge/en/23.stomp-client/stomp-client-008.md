# Receipt Callbacks, Timeouts, and Simple Broker Limitations

When using STOMP, a client can ask the server to confirm that a frame has been processed by adding a **receipt** header. The server returns a **RECEIPT** frame with a matching **receipt-id** header. Spring provides callbacks so the application knows whether the receipt arrived or timed out.

Receipts are useful when you need to know a **SUBSCRIBE** command has been processed by the broker before the client proceeds to send messages, or when confirming the broker has accepted a **SEND** frame. However, a receipt does not prove a consumer has received the message or finished business processing. Spring's simple broker does not support receipts, so these callbacks only work when the server/broker actually supports that feature—typically an external broker via a STOMP broker relay.

## 1. Receipts in the STOMP protocol

A STOMP client can attach a **receipt** header to any client frame except **CONNECT**. The header value is a client-chosen identifier. When the server successfully processes a frame requesting a receipt, it sends **RECEIPT** and places that value in the **receipt-id** header.

Example of a client requesting a receipt for SUBSCRIBE:

~~~text
SUBSCRIBE
id:orders-subscription
destination:/topic/orders
receipt:orders-subscription-ready

^@
~~~

If the server supports receipts and processes SUBSCRIBE successfully, the response looks like:

~~~text
RECEIPT
receipt-id:orders-subscription-ready

^@
~~~

The client matches **receipt-id** against the sent identifier to determine which operation was confirmed. When multiple SENDs or SUBSCRIBEs are pending concurrently, each operation should use a unique receipt ID within the connection scope.

A receipt can also be requested for SEND:

~~~text
SEND
destination:/queue/orders
receipt:order-send-42
content-type:text/plain

create-order-42
^@
~~~

The server returns **RECEIPT** once the SEND frame has been processed according to the server/broker's semantics. That does not mean a consumer has received the message, run handler code, or committed a business transaction.

## 2. What does a receipt confirm?

According to STOMP 1.2, RECEIPT confirms the server has processed the corresponding client frame. Because STOMP delivers frames over an ordered stream, a receipt also serves as a cumulative acknowledgment that preceding frames were received by the server. However, those earlier frames might not have finished processing yet.

Three signals must be distinguished:

| Signal | Meaning | Does not prove |
| --- | --- | --- |
| **RECEIPT** | Server processed the frame requesting a receipt, such as SEND or SUBSCRIBE | Consumer received the message or completed business logic |
| **ACK** | Consumer confirmed consuming a MESSAGE on a subscription using explicit ACK mode | An arbitrary SEND operation was processed by the broker |
| **ERROR** | Server reported an error processing a frame or protocol violation | Operation succeeded |

If the requirement is knowing a subscription was registered by the broker before publishing, a receipt on SUBSCRIBE is the right signal when the broker supports it. If the requirement is knowing the recipient processed an order, design a separate business response, such as an event carrying **correlationId** or a reply message after the service completes. Do not use RECEIPT as a substitute for business confirmation.

## 3. Why are receipts important for SUBSCRIBE?

A common scenario is a client connecting, subscribing to **/topic/orders**, and immediately sending a request that causes the server to broadcast a message to that topic. If the subscription has not been processed by the broker before the message is broadcast, the client may miss the first message.

With a broker supporting receipts, the client can:

1. Send SUBSCRIBE with a receipt ID.
2. Wait for RECEIPT with the matching receipt-id.
3. Only after the success callback runs, send the request that triggers the broadcast.

This synchronizes on broker confirmation instead of waiting an arbitrary guessed duration. **setTimeout(..., 500)** or **Thread.sleep(500)** does not prove the subscription is ready; processing times vary with load and network conditions.

A SUBSCRIBE receipt confirms the server processed the subscription registration frame. It does not replace subscribe permission checks, nor does it guarantee future business messages will always be delivered if the connection drops or the destination has non-persistent semantics.

## 4. Spring's simple broker does not support receipts

Spring can run an in-memory simple broker via **enableSimpleBroker("/topic", "/queue")**. This is a convenient starting option, but it only supports a subset of STOMP commands. The simple broker does not support **ACK**, **RECEIPT**, and several other features; it is also unsuitable for clustering.

Example configuration:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
}
~~~

With this configuration, clients can subscribe and receive normal broadcasts. But if a client sends SUBSCRIBE with a receipt header, the simple broker does not return a RECEIPT frame. In Spring's Java STOMP client, the operation times out and the **addReceiptLostTask** callback is invoked if a TaskScheduler is configured.

That does not necessarily mean the subscription was rejected. The server may have processed the subscription while the simple broker simply lacks receipt support. Therefore, do not use a receipt timeout to conclude that the simple broker failed to create the subscription.

When the application needs receipts, ACK/NACK, or standalone broker capabilities, configure an external STOMP broker such as RabbitMQ or ActiveMQ and enable **enableStompBrokerRelay(...)** for the corresponding destinations. Check the broker's documentation because exact support and semantics depend on the product.

## 5. Configuring Spring WebSocketStompClient

Spring provides **WebSocketStompClient** to connect to a STOMP server over WebSocket. Receipt tracking requires a **TaskScheduler** to schedule expirations. By default, a receipt is considered expired after **15,000 milliseconds (15 seconds)** if no response is received.

The scheduler and client can be declared as Spring beans:

~~~java
package com.example.messaging;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.messaging.WebSocketStompClient;

@Configuration
public class StompClientConfiguration {

    @Bean
    public ThreadPoolTaskScheduler stompClientTaskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("stomp-client-");
        return scheduler;
    }

    @Bean
    public WebSocketStompClient webSocketStompClient(
            TaskScheduler stompClientTaskScheduler) {

        WebSocketStompClient client =
                new WebSocketStompClient(new StandardWebSocketClient());

        client.setTaskScheduler(stompClientTaskScheduler);
        client.setReceiptTimeLimit(10_000);
        return client;
    }
}
~~~

In the example, the wait time is set to 10 seconds with **setReceiptTimeLimit(10_000)**. If this method is not called, the default is 15 seconds. The scheduler's lifecycle is managed by Spring; there is no need to call **initialize()** manually when the bean is created by the container.

**setTaskScheduler(...)** is also used for the STOMP client's heartbeats. Receipt tracking specifically needs the scheduler to run timeout tasks. Without a configured scheduler, the client has no mechanism to track receipt deadlines and may throw an error when attempting to register receipt callbacks.

## 6. Using callbacks in the Spring Java STOMP client

Every call to **StompSession.send(...)** or **StompSession.subscribe(...)** returns a handle of type **StompSession.Receiptable** or **StompSession.Subscription**. The handle lets you register two callbacks:

- **addReceiptTask(...)**: runs when the server returns the matching RECEIPT.
- **addReceiptLostTask(...)**: runs when no RECEIPT is received within the configured time.

Automatic receipts can be enabled for subsequent send and subscribe operations:

~~~java
session.setAutoReceipt(true);
~~~

Then register callbacks on the returned handle:

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
                System.out.println("Order event: " + payload);
            }
        });

subscription.addReceiptTask(() ->
        System.out.println("Broker processed the SUBSCRIBE frame"));

subscription.addReceiptLostTask(() ->
        System.err.println("No SUBSCRIBE receipt before timeout"));
~~~

Similarly, when sending a message:

~~~java
StompSession.Receiptable send = session.send(
        "/topic/order-events",
        "order-created");

send.addReceiptTask(() ->
        System.out.println("Broker processed the SEND frame"));

send.addReceiptLostTask(() ->
        System.err.println("No SEND receipt before timeout"));
~~~

Both examples above assume the STOMP server/broker supports receipts. With Spring's simple broker, the success callback is not invoked because the broker sends no RECEIPT; after the configured duration, the timeout callback is called.

### 6.1. Requesting receipts only for needed operations

**setAutoReceipt(true)** automatically adds a receipt header to all subsequent **send** and **subscribe** operations on the session. This is convenient when most operations need tracking, but it can generate unnecessary receipts and timers.

If a receipt is needed only for a specific SUBSCRIBE or SEND, add the header manually. Example:

~~~java
StompHeaders headers = new StompHeaders();
headers.setDestination("/topic/orders");
headers.setId("orders-subscription");
headers.setReceipt("orders-subscription-ready");

StompSession.Subscription subscription = session.subscribe(
        headers,
        new StompFrameHandler() {
            @Override
            public Type getPayloadType(StompHeaders headers) {
                return String.class;
            }

            @Override
            public void handleFrame(StompHeaders headers, Object payload) {
                System.out.println(payload);
            }
        });

subscription.addReceiptTask(() ->
        System.out.println("Orders subscription is registered"));

subscription.addReceiptLostTask(() ->
        System.err.println("Orders subscription receipt timed out"));
~~~

For SEND, use the **send(StompHeaders, Object)** overload:

~~~java
StompHeaders sendHeaders = new StompHeaders();
sendHeaders.setDestination("/topic/order-events");
sendHeaders.setReceipt("order-event-42");

StompSession.Receiptable receipt = session.send(
        sendHeaders,
        "order-created");

receipt.addReceiptTask(() ->
        System.out.println("Order event accepted by broker"));

receipt.addReceiptLostTask(() ->
        System.err.println("No broker receipt for order event"));
~~~

Only call **addReceiptTask** or **addReceiptLostTask** when the operation actually has a receipt header. If auto-receipt is not enabled and no header was set manually, the handle has no receipt ID and Spring may throw **IllegalArgumentException** when registering a callback.

## 7. Callbacks and errors in StompSessionHandler

A receipt timeout is a separate event. When the broker sends **ERROR**, the client needs to handle the ERROR frame. When WebSocket/TCP disconnects or a transport error occurs, the transport callback must handle it.

**StompSessionHandlerAdapter** is the right adapter for receiving these events. Example:

~~~java
StompSessionHandlerAdapter handler = new StompSessionHandlerAdapter() {

    @Override
    public void afterConnected(
            StompSession session,
            StompHeaders connectedHeaders) {

        session.setAutoReceipt(true);

        StompSession.Subscription subscription = session.subscribe(
                "/topic/orders",
                new StompFrameHandler() {
                    @Override
                    public Type getPayloadType(StompHeaders headers) {
                        return String.class;
                    }

                    @Override
                    public void handleFrame(
                            StompHeaders headers,
                            Object payload) {
                        System.out.println("Received: " + payload);
                    }
                });

        subscription.addReceiptTask(() ->
                System.out.println("SUBSCRIBE confirmed"));

        subscription.addReceiptLostTask(() ->
                System.err.println("SUBSCRIBE receipt expired"));
    }

    @Override
    public void handleFrame(StompHeaders headers, Object payload) {
        System.err.println(
                "Broker ERROR: " + headers.getFirst("message")
                        + " - " + payload);
    }

    @Override
    public void handleTransportError(
            StompSession session,
            Throwable exception) {
        System.err.println("STOMP transport error: " + exception.getMessage());
    }
};
~~~

**afterConnected** runs only after the STOMP session receives CONNECTED. The adapter's **handleFrame** receives ERROR frames; the adapter defaults to String as the payload type for ERROR. **handleTransportError** handles transport errors such as lost connections or frame read/write failures.

Do not treat these callbacks as a single state:

- Receipt success callback: server confirmed the frame.
- Receipt lost callback: receipt was not received before the deadline.
- ERROR frame: server reported a protocol or processing error.
- Transport error: connection or frame transmission failed.

If the server sends ERROR for a frame carrying a receipt header, STOMP allows ERROR to carry the corresponding **receipt-id** so the client can correlate the error with the original operation. The broker may close the connection after ERROR; handle the error and reconnect according to client lifecycle.

## 8. Using receipts with @stomp/stompjs in the browser

With the **@stomp/stompjs** JavaScript client, the **watchForReceipt(receiptId, callback)** API listens for a RECEIPT with the matching receipt-id. Register the callback before sending the operation and pass the same receipt ID in the header.

Example waiting for subscription confirmation:

~~~javascript
const receiptId = "orders-sub-" + crypto.randomUUID();

const timeoutId = window.setTimeout(() => {
    console.warn("No SUBSCRIBE receipt within 15 seconds");
}, 15000);

client.watchForReceipt(receiptId, (frame) => {
    window.clearTimeout(timeoutId);
    console.log(
        "Subscription processed:",
        frame.headers["receipt-id"]
    );
});

client.subscribe(
    "/topic/orders",
    (message) => {
        console.log("Order event:", message.body);
    },
    {
        id: "orders-subscription",
        receipt: receiptId
    }
);
~~~

Example sending a message with a receipt:

~~~javascript
const receiptId = "order-send-" + crypto.randomUUID();

const timeoutId = window.setTimeout(() => {
    console.warn("No SEND receipt within 15 seconds");
}, 15000);

client.watchForReceipt(receiptId, (frame) => {
    window.clearTimeout(timeoutId);
    console.log("Broker receipt:", frame.headers["receipt-id"]);
});

client.publish({
    destination: "/topic/order-events",
    headers: {
        receipt: receiptId,
        "content-type": "text/plain"
    },
    body: "order-created"
});
~~~

**watchForReceipt** must be called when the client is STOMP-connected. Use a unique receipt ID per pending operation. The example uses **crypto.randomUUID()** in a browser secure context.

The timeouts in both JavaScript examples are application-created timers; StompJS does not automatically turn that timeout into a broker failure confirmation. When the timer fires, the operation may still have been processed by the broker or the receipt may arrive late. The receipt watcher callback may still receive the frame if it arrives later; the application should manage operation state and clean up timers properly.

If the server is Spring's simple broker, StompJS also receives no RECEIPT. The timer will report expiration after 15 seconds, but that does not indicate whether the subscription was created.

## 9. Timeouts and how to choose a timeout value

For Spring's Java client, **setReceiptTimeLimit(long)** accepts the number of milliseconds before a receipt is considered expired. The default is 15,000 ms. The timeout should be long enough to tolerate normal network latency, broker load, and processing time, yet not so long that the UI or workflow hangs indefinitely.

Example:

~~~java
stompClient.setReceiptTimeLimit(8_000);
~~~

An 8-second value is just an example; measure latency in real environments before picking a production timeout. Factors to consider:

- Latency from browser to Spring server.
- Latency from Spring relay to broker.
- Broker load and subscription count.
- Proxies, load balancers, or networks that may delay frames.
- Heartbeats and client reconnect state.
- Whether the broker actually supports receipts for that frame type.

A timeout does not cancel the sent frame. When a timeout occurs, the client only knows it has not received confirmation within the time limit. The broker may already have processed the frame while the response was lost or delayed. Consequently, retrying SEND can create duplicate messages.

For non-idempotent operations, attach an **idempotency key** or business request ID to the payload/header so the server can detect duplicate requests. Do not automatically retry payment creation, order creation, or non-repeatable actions simply because of a receipt timeout.

## 10. Graceful disconnect with a receipt

STOMP allows requesting a receipt on the **DISCONNECT** frame. The client can wait for confirmation before closing the socket to reduce the risk of closing the connection too early while prior frames are still in flight to the server.

Example per STOMP 1.2:

~~~text
DISCONNECT
receipt:disconnect-77

^@
~~~

The server may reply:

~~~text
RECEIPT
receipt-id:disconnect-77

^@
~~~

Only after receiving the receipt does the client close the socket. However, the STOMP specification also notes that the server might close the socket so quickly that the client fails to receive the DISCONNECT RECEIPT in time. If application-level shutdown guarantees are needed, design explicit timeouts and fallbacks.

Spring's **StompSession.disconnect()** API is a convenience disconnect operation and does not return a **Receiptable**. If you need to track a DISCONNECT receipt, use an API/protocol path capable of sending a DISCONNECT frame with a receipt and observing the RECEIPT frame before closing the transport; do not assume calling disconnect() automatically triggers a receipt callback.

## 11. Differences between Receipt and ACK/NACK

Receipt and ACK/NACK are often confused because both are acknowledgment frames, yet they apply to two different steps.

**RECEIPT** confirms the server processed a client frame requesting confirmation. For instance, SUBSCRIBE was accepted or SEND was processed by the broker.

**ACK/NACK** relates to a message delivered to a consumer. When SUBSCRIBE uses **ack:client** or **ack:client-individual**, the consumer sends ACK after processing the message; if unable to process, it can send NACK. **ack:auto** mode requires no explicit ACK from the client.

~~~text
SUBSCRIBE
id:orders-consumer
destination:/queue/orders
ack:client-individual

^@

MESSAGE
subscription:orders-consumer
message-id:msg-42
destination:/queue/orders

order-42
^@

ACK
id:ack-42

^@
~~~

In STOMP 1.2, ACK uses an **id** header taken from the MESSAGE frame's **ack** header. Client libraries may provide dedicated ACK/NACK APIs instead of constructing frames manually.

Spring's simple broker does not support ACK, RECEIPT, and several other commands. If delivery semantics based on ACK/NACK are needed, use a broker supporting those features and configure the subscription accordingly. Receipts do not make messages durable and do not replace ACK.

## 12. Handling timeouts safely

When a receipt does not arrive, log enough information for diagnosis:

- Receipt ID and STOMP command (SEND, SUBSCRIBE, or DISCONNECT).
- Destination and session ID if available.
- Send timestamp, configured timeout, and timeout timestamp.
- WebSocket/STOMP connection state and latest heartbeat.
- Broker type and whether STOMP receipt support is enabled.
- Whether any ERROR frame or transport error occurred before the timeout.

Do not log credentials or sensitive payload contents. Receipt IDs should be logged alongside correlation IDs to cross-reference with broker logs if needed.

Before retrying, classify the situation:

1. Simple broker does not support receipts: timeout callback is expected behavior. Use application-level confirmation or an external broker.
2. Broker supports receipts but the connection closed: handle the transport error and reconnect; the prior operation may be in an indeterminate state.
3. Broker supports receipts and connection is alive, but responses are slow: check load and adjust timeouts based on metrics.
4. Broker sent ERROR: handle the error by frame and destination; do not treat it as an ordinary timeout.
5. SEND may have been processed by the broker while the receipt was lost: use an idempotency key before retrying to avoid duplicate messages.

## 13. Common pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| **addReceiptTask** is not invoked | Server did not send RECEIPT or receipt ID mismatched | Check receipt header, broker support, and received frames |
| **addReceiptLostTask** runs after 15 seconds | Default receipt timeout is 15 seconds; server may not support receipts | Check whether simple broker or external broker relay is used |
| Spring throws error registering callback | Operation has no receipt header or TaskScheduler is not configured | Enable auto-receipt or set header manually; configure scheduler before connecting |
| Subscription still receives messages despite receipt timeout | Simple broker may have processed subscription without receipt support | Do not use timeout as proof that subscription failed |
| Client sends request right after SUBSCRIBE and misses first event | Broker had not processed subscription before publish | On a receipt-capable broker, wait for SUBSCRIBE receipt before sending request |
| SEND receipt succeeds but user sees no outcome | Receipt only confirms server processed the SEND frame | Check routing, subscriptions, consumer, and business response |
| Retry after timeout creates duplicate messages | Initial frame may already have been processed by the broker | Use idempotency keys and deduplication on server/consumer |
| ERROR frame arrives instead of RECEIPT | Broker rejected frame or detected protocol error | Handle ERROR separately; inspect destination, permissions, and headers |

## 14. Testing receipts

A valuable integration test should run against a real STOMP broker if the feature under test is receipts. The simple broker cannot prove receipts work because it does not support that command.

Scenarios to test:

1. Connect successfully and register SUBSCRIBE with a receipt; verify the success callback runs exactly once.
2. Send SEND with a receipt; verify the callback receives the matching receipt.
3. Two operations pending concurrently; verify receipt IDs are not mixed up between the two callbacks.
4. Set a short timeout in tests; verify the lost callback runs when the broker returns no receipt.
5. With the simple broker; verify no success callback runs and the timeout is recorded properly.
6. Broker returns ERROR; verify the handler handles ERROR separately.
7. Disconnect WebSocket while waiting for a receipt; verify transport error is handled and operation state becomes indeterminate.
8. Retry a SEND after timeout; verify the idempotency key prevents duplicate processing.
9. For SUBSCRIBE, wait for the receipt before triggering the next publish step and verify the client receives the first event.

In tests, use short timeouts to reduce runtime, but not so low that tests flake due to scheduling or slow CI. Do not use Thread.sleep as proof that a receipt arrived; wait for callbacks using a latch, future, or test framework synchronization mechanism.

## 15. References

- [STOMP 1.2 Specification — Header receipt and RECEIPT frame](https://stomp.github.io/stomp-specification-1.2.html): rules for receipt, receipt-id, cumulative confirmation semantics, ACK/NACK, and DISCONNECT.
- [Spring Framework — STOMP Client](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html): WebSocketStompClient, setAutoReceipt, Receiptable callbacks, TaskScheduler, and default timeouts.
- [Spring Framework — External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html): simple broker limitations and switching to broker relay.
- [StompSession Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/stomp/StompSession.html): send, subscribe, and setAutoReceipt APIs.
- [StompSession.Receiptable Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/stomp/StompSession.Receiptable.html): receipt success and lost callbacks.
- [StompClientSupport Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/stomp/StompClientSupport.html): TaskScheduler and receiptTimeLimit.
- [@stomp/stompjs Client API](https://stomp-js.github.io/api-docs/latest/classes/Client.html): watchForReceipt and browser-side callbacks.
