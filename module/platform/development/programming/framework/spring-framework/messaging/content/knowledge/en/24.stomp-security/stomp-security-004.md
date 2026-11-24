# Subscribing, Unsubscribing, and Subscription Management

## Objective

In a WebSocket/STOMP application, a subscription describes a client registering to receive messages from a destination. The client sends a SUBSCRIBE frame to the server; when a matching message exists, the server sends a MESSAGE frame back to the client. When data is no longer needed, the client sends UNSUBSCRIBE to cancel the subscription.

After this article, you will be able to:

- Create subscriptions using the JavaScript library @stomp/stompjs.
- Manage subscription IDs and StompSubscription objects.
- Unsubscribe accurately and handle multiple subscriptions to the same destination.
- Re-subscribe after reconnecting.
- Manage subscriptions according to screen or feature lifecycles.
- Understand receipts, acknowledgments, and the limitations of the Spring simple broker.
- Test and diagnose common issues.

## 1. What is a subscription in STOMP?

STOMP is a frame-based messaging protocol. A client can both send messages using SEND and receive messages by sending SUBSCRIBE.

When a client sends SUBSCRIBE, the frame must include:

- destination: the address the client wants to listen to.
- id: the subscription identifier, unique within the scope of a STOMP connection.
- ack: optional, specifying the message acknowledgment mode as auto, client, or client-individual.

The server uses this information to register the client with the destination. Matching messages are sent back as MESSAGE frames. Each MESSAGE has a subscription header indicating which subscription received the message.

When the client sends UNSUBSCRIBE, the frame must contain an id matching the created subscription. After cancellation, the server stops sending messages via that subscription.

STOMP does not prescribe business semantics for destinations. For example, /topic/news and /queue/orders are destination strings; actual semantics are determined by the server or broker. In Spring, message broker configurations typically register prefixes such as /topic and /queue.

## 2. Lifecycle from connection to unsubscription

A typical lifecycle:

1. Create a STOMP client with the WebSocket endpoint.
2. Call activate() to begin connecting.
3. Wait for the server to return a CONNECTED frame.
4. Inside the onConnect callback, call subscribe() for each destination to monitor.
5. When receiving a MESSAGE, process the payload in the registered callback.
6. When the screen or feature no longer needs data, call unsubscribe() on the corresponding subscription.
7. When the application finishes completely, call deactivate() to close the connection and stop reconnecting.

You must distinguish between a WebSocket connection and a subscription. One connection can hold many subscriptions. Canceling one subscription does not close the connection; closing the connection terminates all subscriptions belonging to that session on the server.

Overview flow:

~~~text
Client                         Spring / STOMP server
  |                                      |
  | -------- CONNECT ------------------> |
  | <------- CONNECTED ----------------- |
  |                                      |
  | -------- SUBSCRIBE ----------------> |
  |          id, destination             |
  |                                      |
  | <------- MESSAGE ------------------- |  When a matching message arrives
  |                                      |
  | -------- UNSUBSCRIBE --------------> |
  |                 id                   |
  |                                      |
  | -------- DISCONNECT ---------------> |
~~~

## 3. Creating a subscription with @stomp/stompjs

Install the library:

~~~bash
npm install @stomp/stompjs
~~~

Minimal example:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
  brokerURL: "ws://localhost:8080/ws",
  reconnectDelay: 5000
});

let notificationSubscription;

client.onConnect = () => {
  notificationSubscription = client.subscribe(
    "/topic/notifications",
    (message) => {
      const notification = JSON.parse(message.body);
      console.log("New notification:", notification);
    }
  );
};

client.onStompError = (frame) => {
  console.error("STOMP error:", frame.headers["message"], frame.body);
};

client.activate();
~~~

Key points to understand:

- The client takes brokerURL as the WebSocket endpoint address registered by the server, e.g., /ws.
- activate() initiates the connection process; it does not mean the client is already CONNECTED.
- onConnect is invoked only after the STOMP connection succeeds and the client receives the CONNECTED frame.
- subscribe(destination, callback, headers) sends the subscription request and returns a StompSubscription object.
- The callback receives an IMessage. The content is usually in message.body; headers can be read via message.headers.

Call subscribe after the client is connected. The Client API of @stomp/stompjs checks the connection state when subscribe is called; calling it too early can throw an error because no active STOMP handler exists yet.

## 4. Subscription id and the StompSubscription object

Each subscription has an id. STOMP requires distinct IDs for subscriptions on the same connection. A client may subscribe to the same destination multiple times, but each subscription must have its own id.

With @stomp/stompjs, if no id is passed in headers, the library generates an id automatically:

~~~javascript
const subscription = client.subscribe(
  "/topic/orders",
  (message) => console.log(message.body)
);

console.log(subscription.id);
~~~

You can set an explicit id when you need to correlate with a custom management system:

~~~javascript
const subscription = client.subscribe(
  "/topic/orders",
  (message) => console.log(message.body),
  { id: "orders-screen" }
);
~~~

Use an explicit id only when the application can guarantee its uniqueness within a connection. If multiple components use the same id orders-screen, the server may reject the duplicate subscription id or unsubscribing may target the wrong subscription. For most applications, letting the library auto-generate IDs is the simpler choice.

StompSubscription has two important members:

- id: the id used for the subscription.
- unsubscribe(headers?): method that sends an UNSUBSCRIBE request for that subscription.

Keep the StompSubscription object after subscribing so you can unsubscribe cleanly when needed.

## 5. Unsubscribing

The preferred approach is to call unsubscribe() on the object returned by subscribe():

~~~javascript
const subscription = client.subscribe(
  "/topic/notifications",
  (message) => console.log(message.body)
);

// When notifications are no longer needed:
subscription.unsubscribe();
~~~

You can pass additional headers to the UNSUBSCRIBE frame:

~~~javascript
subscription.unsubscribe({
  receipt: "unsubscribe-notifications-1"
});
~~~

Another approach is to call client.unsubscribe(id) directly:

~~~javascript
client.unsubscribe(subscription.id);
~~~

The direct approach is useful when the application stores only the id instead of the entire object. However, keeping the subscription object usually makes code easier to read and less prone to id mix-ups.

UNSUBSCRIBE cancels only the subscription with the matching id. If the same destination has three subscriptions with three different IDs, canceling one subscription does not automatically cancel the other two.

Call unsubscribe only while the client is still connected. Once the WebSocket closes, the server cleans up subscriptions attached to the terminated session; an old subscription object no longer represents an active subscription on a new connection.

## 6. Managing multiple subscriptions

When a screen needs to receive multiple event types, storing subscriptions in a Map keeps lifecycle management clear:

~~~javascript
const subscriptions = new Map();

function addSubscription(key, destination, callback) {
  if (!client.connected) {
    throw new Error("STOMP client is not connected");
  }

  if (subscriptions.has(key)) {
    return subscriptions.get(key);
  }

  const subscription = client.subscribe(destination, callback);
  subscriptions.set(key, subscription);
  return subscription;
}

function removeSubscription(key) {
  const subscription = subscriptions.get(key);

  if (!subscription) {
    return;
  }

  if (client.connected) {
    subscription.unsubscribe();
  }

  subscriptions.delete(key);
}
~~~

Usage:

~~~javascript
addSubscription(
  "orders",
  "/topic/orders",
  (message) => renderOrder(JSON.parse(message.body))
);

addSubscription(
  "alerts",
  "/user/queue/alerts",
  (message) => renderAlert(JSON.parse(message.body))
);

// When leaving the screen:
removeSubscription("orders");
removeSubscription("alerts");
~~~

The key in the Map is an application-chosen name for managing the feature; destination is the STOMP address; subscription.id is the protocol id generated by the library or supplied by the application. These three concepts serve different purposes.

The addSubscription function in the example above proactively rejects subscribing when the client is not yet connected. If the application needs to remember a desire to subscribe before connecting, store the desired configuration separately and perform the subscription in onConnect.

## 7. Avoiding duplicate registrations

A common mistake is calling subscribe every time a component renders or every time an initialization function is re-invoked. After several renders, a single message can trigger the callback multiple times because multiple subscriptions exist for the same destination.

How to prevent this:

- Place the subscribe call in a lifecycle-controlled location, such as after connecting or when the screen mounts.
- Save the handle returned by subscribe.
- Check the current state before creating a new subscription.
- Unsubscribe when the component or screen is no longer in use.
- Use different IDs for independent subscriptions.
- Avoid creating a new global subscription every time a UI event occurs.

Having two subscriptions to the same destination can be intentional, for instance when two independent UI sections monitor the same topic. In that case, manage them as two separate registrations and cancel them separately.

## 8. Reconnecting and re-subscribing

When a connection drops, the old STOMP session ends and that session's subscriptions are no longer valid. @stomp/stompjs can automatically reconnect according to reconnectDelay, but the application must still re-subscribe to the required destinations in onConnect.

Example:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
  brokerURL: "ws://localhost:8080/ws",
  reconnectDelay: 5000
});

let ordersSubscription;
let alertsSubscription;

client.onConnect = () => {
  // onConnect runs again after each successful reconnect.
  ordersSubscription = client.subscribe(
    "/topic/orders",
    (message) => renderOrder(JSON.parse(message.body))
  );

  alertsSubscription = client.subscribe(
    "/user/queue/alerts",
    (message) => renderAlert(JSON.parse(message.body))
  );
};

client.onWebSocketClose = () => {
  // Handles from the old session no longer represent active subscriptions.
  ordersSubscription = undefined;
  alertsSubscription = undefined;
};

client.activate();
~~~

Do not call subscribe only once before client.activate() and assume the library will automatically restore all subscriptions. Put subscription logic inside onConnect or use a subscription management layer that can recreate registrations after each connection.

If you have dynamic subscriptions, store the list of destinations the user currently wants to watch. When reconnecting succeeds, iterate over that list and create new subscriptions. When the user unwatches while disconnected, remove the destination from the desired list so it is not re-subscribed on the next connection.

Example of a demand-driven management model:

~~~javascript
const desiredSubscriptions = new Map();
let liveSubscriptions = new Map();

function watch(key, destination, callback) {
  desiredSubscriptions.set(key, { destination, callback });

  if (client.connected && !liveSubscriptions.has(key)) {
    const subscription = client.subscribe(destination, callback);
    liveSubscriptions.set(key, subscription);
  }
}

function unwatch(key) {
  desiredSubscriptions.delete(key);

  const subscription = liveSubscriptions.get(key);
  if (client.connected) {
    subscription?.unsubscribe();
  }

  liveSubscriptions.delete(key);
}

client.onConnect = () => {
  liveSubscriptions.clear();

  for (const [key, item] of desiredSubscriptions) {
    const subscription = client.subscribe(
      item.destination,
      item.callback
    );
    liveSubscriptions.set(key, subscription);
  }
};

client.onWebSocketClose = () => {
  liveSubscriptions.clear();
};
~~~

In this example, desiredSubscriptions represents the business state the application wants to maintain. liveSubscriptions contains only the handles of the current connection. Separating these two states lets the application restore registrations after reconnecting without mistakenly retaining handles from an old session.

## 9. Managing subscriptions by UI lifecycle

In SPA interfaces, subscriptions are usually tied to a screen or component. When the screen appears, subscribe to receive data; when the screen is destroyed, unsubscribe.

Example using an initializer and cleanup function:

~~~javascript
function mountOrdersScreen(client) {
  const subscription = client.subscribe(
    "/topic/orders",
    (message) => renderOrder(JSON.parse(message.body))
  );

  return function cleanup() {
    if (client.connected) {
      subscription.unsubscribe();
    }
  };
}
~~~

Usage:

~~~javascript
const cleanupOrders = mountOrdersScreen(client);

// When leaving the screen:
cleanupOrders();
~~~

In React, similar logic can be called from useEffect and return the cleanup function. Note that the client must be connected before the effect subscribes. If the connection completes after the component mounts, integrate the component with the connection state and perform the subscribe inside onConnect or when the state transitions to connected.

Do not put subscribe directly in the component body because the component body can run many times. Use an effect or a lifecycle-management service to avoid duplicate registrations.

## 10. Receipts and subscription confirmation

STOMP allows clients to add a receipt header to a frame, after which the server can return a RECEIPT frame to confirm it processed that frame.

With @stomp/stompjs, you can register a callback with watchForReceipt before sending the frame containing the receipt header:

~~~javascript
const receiptId = "orders-subscribe-001";

client.watchForReceipt(receiptId, (frame) => {
  console.log("Server acknowledged:", frame.headers["receipt-id"]);
});

const subscription = client.subscribe(
  "/topic/orders",
  (message) => console.log(message.body),
  { receipt: receiptId }
);
~~~

Receipts are useful when the application needs confirmation that the server processed a frame before proceeding to the next step. A receipt is a protocol-level acknowledgment; it does not prove that the client-side callback processed a message, does not confirm a business transaction committed, and does not by default prove data was persisted durably.

Not all brokers support receipts. The Spring simple broker supports only a subset of STOMP and does not support receipts. If using the simple broker, do not build application flows that depend on RECEIPT. Check the capabilities of the broker in use before implementing.

If you need to know when Spring has finished processing SUBSCRIBE with the simple broker, you can observe brokerChannel with an ExecutorChannelInterceptor and handle it in afterMessageHandled. SessionSubscribeEvent only notifies that Spring received the SUBSCRIBE frame; it is not a receipt confirming the broker has finished processing the subscription.

## 11. Acknowledgments when receiving messages

The ack header of SUBSCRIBE specifies how the client acknowledges messages:

| Mode | Meaning |
| --- | --- |
| auto | The server considers the message delivered when sent to the client; the client does not need to send ACK. |
| client | The client sends ACK after processing; ACK is cumulative within the subscription. |
| client-individual | The client acknowledges each message individually. |

Example using @stomp/stompjs with a broker that supports acknowledgments:

~~~javascript
const subscription = client.subscribe(
  "/queue/tasks",
  async (message) => {
    try {
      await processTask(JSON.parse(message.body));
      message.ack();
    } catch (error) {
      message.nack();
    }
  },
  { ack: "client-individual" }
);
~~~

ACK should only be sent after the application finishes the processing step it wants to confirm. If you ACK before persisting data or completing work, a subsequent error may cost the application its chance to reprocess the message.

When a broker supports redelivery, unacknowledged messages may be redelivered after a connection drops. Therefore, consumers should be designed to be idempotent: if the same message arrives a second time, the business outcome remains correct.

ACK/NACK support depends on the broker. The Spring simple broker does not support client/client-individual acknowledgment modes; it only handles a simple STOMP subset. If you need ACK, NACK, or redelivery, use a broker relay to a dedicated broker and check that broker's specific semantics.

## 12. Closing the client and cleaning up subscriptions

When you only want to stop receiving one message type while keeping the connection open, call subscription.unsubscribe().

When you want to stop the entire client and prevent reconnection, call:

~~~javascript
await client.deactivate();
~~~

deactivate() executes the disconnection process and returns a Promise that resolves once deactivation completes. This is the right approach when the application navigates away, logs out, or no longer needs the STOMP client.

There is no need to send a separate UNSUBSCRIBE for every subscription before closing the entire connection. When the session ends, the server cleans up subscriptions attached to that session. However, if you keep the connection open to use other destinations, you must cancel each subscription that is no longer needed.

Do not use forceDisconnect() for normal shutdown flows. This API closes the WebSocket directly, skipping the STOMP DISCONNECT sequence, and can cause the server to detect the disconnect later. Use it only in special recovery situations when the connection cannot close normally.

## 13. Security and destination control

Knowing a destination does not equate to having permission to subscribe to that destination. The server must authenticate the user and verify SUBSCRIBE permissions.

Key points to keep in mind:

- Do not allow everyone to subscribe to every topic just because a destination contains no confidential data.
- Check permissions by user, tenant, room, or resource.
- Use user-specific destinations for personal data, such as /user/queue/notifications when appropriate for the Spring configuration.
- Do not trust userId, role, or tenantId passed by the client in headers/payloads.
- Limit the number of subscriptions and wildcard scope to prevent clients from creating excessive registrations.
- On logout, close the client and clear subscription state at the UI layer.
- Do not log tokens, cookies, or sensitive payloads in STOMP debug logs.

If using Spring Security, configure message authorization for SEND and SUBSCRIBE destinations. Authorization rules must apply both to messages entering controllers and messages going directly to the broker.

## 14. Testing subscriptions

An integration test should verify both subscribing and unsubscribing:

1. Start the Spring application with a WebSocket/STOMP endpoint.
2. Connect a STOMP client and wait for onConnect.
3. Subscribe to destination /topic/test.
4. Send a message from the server to /topic/test.
5. Verify the callback receives the expected payload.
6. Call subscription.unsubscribe().
7. Send a subsequent message to /topic/test.
8. Verify the canceled subscription's callback does not receive the new message.
9. Re-establish the connection and verify onConnect re-subscribes to the required destinations.

Additional test cases:

- Two subscriptions to the same destination with different IDs.
- Two subscriptions to the same destination while canceling only one.
- Intentionally registering a duplicate id within the same session.
- Subscribing when the client is not yet connected.
- Unexpected disconnect and reconnect.
- User unsubscribes while offline.
- Broker rejects an invalid destination or frame.
- Client lacks permission to SUBSCRIBE to a private destination.
- Receipt or ACK only when the broker under test supports that feature.

To test callback logic, you can mock the message handler. However, to verify destinations, SUBSCRIBE/UNSUBSCRIBE frames, reconnection, and security, an integration test against a real STOMP endpoint is needed.

## 15. Common errors

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| subscribe() reports client is not connected | Calling subscribe before CONNECTED | Move the call into onConnect or wait for the connected state. |
| One message triggers the callback multiple times | Multiple subscriptions exist on the same destination | Store handles, prevent duplicate registration, and cancel old subscriptions. |
| unsubscribe() does not cancel the right subscription | Using the wrong id or mixing up handles | Call unsubscribe() on the exact StompSubscription object. |
| Reconnect succeeds but no messages arrive | Not re-subscribing after the new CONNECTED | Re-subscribe inside onConnect on every successful connection. |
| Messages arrive after leaving the screen | Cleanup did not run or handle was not stored | Tie the subscription to component lifecycle and call cleanup. |
| Receipt callback does not run | Broker does not support receipts or watcher registered at the wrong time | Check broker support; call watchForReceipt before sending the frame with receipt. |
| ACK/NACK is rejected | Broker does not support the chosen ack mode | Check broker capabilities; Spring simple broker does not support ACK/NACK. |
| Client receives messages from another tenant | Server does not verify SUBSCRIBE permissions | Enforce authorization on destinations and authenticate users. |
| Old subscription is recreated after reconnect even though the user unwatched it | Desired subscription list was not updated | Remove the destination from desiredSubscriptions when canceling. |

## 16. Key takeaways

- SUBSCRIBE registers to receive messages; UNSUBSCRIBE cancels a subscription by id.
- Each subscription on the same connection needs a distinct id; @stomp/stompjs auto-generates one if no id is passed.
- subscribe() returns a StompSubscription; prefer calling unsubscribe() on this handle.
- Call subscribe after CONNECTED; use onConnect to re-subscribe after each reconnect.
- Store desired state and current connection handles separately when managing dynamic subscriptions.
- Receipt, ACK, and NACK depend on the broker; the Spring simple broker does not support receipts or acknowledgments.
- Cancel subscriptions according to screen lifecycle; use deactivate() when closing the entire STOMP client.
- Securing SUBSCRIBE is just as important as securing SEND; the server must check destination access permissions.

## References

- [@stomp/stompjs — Client API](https://stomp-js.github.io/api-docs/latest/classes/Client.html)
- [@stomp/stompjs — StompSubscription API](https://stomp-js.github.io/api-docs/latest/interfaces/StompSubscription.html)
- [STOMP Protocol Specification 1.2 — SUBSCRIBE](https://stomp.github.io/stomp-specification-1.2.html#SUBSCRIBE)
- [STOMP Protocol Specification 1.2 — UNSUBSCRIBE](https://stomp.github.io/stomp-specification-1.2.html#UNSUBSCRIBE)
- [STOMP Protocol Specification 1.2 — ACK and NACK](https://stomp.github.io/stomp-specification-1.2.html#ACK)
- [Spring Framework — Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html)
- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework — Authorization](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authorization.html)
- [Spring Framework — Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html)

