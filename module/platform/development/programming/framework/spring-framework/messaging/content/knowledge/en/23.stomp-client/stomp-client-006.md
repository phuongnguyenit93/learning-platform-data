# Subscribing, Unsubscribing, and Subscription Management

## Objectives

In WebSocket/STOMP applications, a subscription describes a client registering to receive messages from a destination. The client sends a SUBSCRIBE frame to the server; when matching messages exist, the server sends MESSAGE frames to the client. When data is no longer needed, the client sends UNSUBSCRIBE to cancel the subscription.

After this lesson, you can:

- Create subscriptions using the `@stomp/stompjs` JavaScript library.
- Manage subscription IDs and `StompSubscription` objects.
- Cancel the right subscription and handle multiple subscriptions to the same destination.
- Re-register subscriptions after reconnecting.
- Manage subscriptions according to screen or feature lifecycles.
- Understand receipts, acknowledgments, and limitations of Spring's simple broker.
- Test and diagnose common issues.

## 1. What is a subscription in STOMP?

STOMP is a frame-based messaging protocol. A client can both send messages with SEND and receive messages by sending SUBSCRIBE.

When the client sends SUBSCRIBE, the frame must include:

- destination: the address the client wants to listen to.
- id: subscription identifier, unique within the scope of one STOMP connection.
- ack: optional, specifies message acknowledgment mode as auto, client, or client-individual.

The server uses this information to register the client on the destination. Matching messages are sent back as MESSAGE frames. Each MESSAGE has a subscription header indicating which subscription received the message.

When the client sends UNSUBSCRIBE, the frame must contain an id matching the created subscription. After unsubscribing, the server stops sending messages through that subscription.

STOMP does not define the business semantics of destinations. For example, `/topic/news` and `/queue/orders` are destination strings; actual semantics are decided by the server or broker. In Spring, message broker configuration typically registers prefixes such as `/topic` and `/queue`.

## 2. Lifecycle from connection to unsubscription

A typical lifecycle:

1. Create a STOMP client with the WebSocket endpoint.
2. Call `activate()` to start connecting.
3. Wait for the server to return a CONNECTED frame.
4. In the `onConnect` callback, call `subscribe()` for each destination to monitor.
5. Upon receiving MESSAGE, process the payload in the registered callback.
6. When the screen or feature no longer needs data, call `unsubscribe()` on the corresponding subscription.
7. When the application shuts down completely, call `deactivate()` to close the connection and stop reconnecting.

Distinguish the WebSocket connection from subscriptions. One connection can hold multiple subscriptions. Canceling one subscription does not close the connection; closing the connection terminates all subscriptions belonging to that session on the server.

Conceptual flow:

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

- Client takes `brokerURL` as the WebSocket endpoint address registered by the server, e.g., `/ws`.
- `activate()` initiates the connection process; it does not mean the client is already CONNECTED.
- `onConnect` is invoked only after the STOMP connection succeeds and the client receives the CONNECTED frame.
- `subscribe(destination, callback, headers)` sends a subscription request and returns a `StompSubscription` object.
- The callback receives an `IMessage`. The content is typically in `message.body`; headers can be read via `message.headers`.

Call `subscribe` after the client is connected. The `@stomp/stompjs` Client API checks connection state when `subscribe` is called; calling it too early can throw an error because there is no active STOMP handler yet.

## 4. Subscription IDs and the StompSubscription object

Every subscription has an `id`. STOMP requires distinct IDs for subscriptions on the same connection. A client can subscribe to the same destination multiple times, but each subscription must have its own ID.

With `@stomp/stompjs`, if no `id` is passed in headers, the library generates an ID automatically:

~~~javascript
const subscription = client.subscribe(
  "/topic/orders",
  (message) => console.log(message.body)
);

console.log(subscription.id);
~~~

An explicit ID can be set when needing to correlate with a separate management system:

~~~javascript
const subscription = client.subscribe(
  "/topic/orders",
  (message) => console.log(message.body),
  { id: "orders-screen" }
);
~~~

Only use an explicit ID when the application guarantees its uniqueness within a connection. If multiple components share the ID `"orders-screen"`, the server may reject duplicate subscription IDs or unsubscribing may target the wrong subscription. For most applications, letting the library generate IDs automatically is simpler.

`StompSubscription` has two key members:

- `id`: the ID used for the subscription.
- `unsubscribe(headers?)`: method that sends an UNSUBSCRIBE request for that subscription.

Retain the `StompSubscription` object after subscribing so it can be cleanly canceled when needed.

## 5. Unsubscribing

The preferred way is calling `unsubscribe()` on the object returned by `subscribe()`:

~~~javascript
const subscription = client.subscribe(
  "/topic/notifications",
  (message) => console.log(message.body)
);

// When notifications are no longer needed:
subscription.unsubscribe();
~~~

Additional headers can be passed to the UNSUBSCRIBE frame:

~~~javascript
subscription.unsubscribe({
  receipt: "unsubscribe-notifications-1"
});
~~~

Another approach is calling `client.unsubscribe(id)` directly:

~~~javascript
client.unsubscribe(subscription.id);
~~~

The direct approach is useful when the application stores only IDs rather than full subscription objects. However, keeping the subscription object usually makes code clearer and less prone to ID mix-ups.

UNSUBSCRIBE only cancels the subscription with the matching ID. If the same destination has three subscriptions with three different IDs, canceling one subscription does not automatically cancel the other two.

Only call `unsubscribe` while the client is still connected. Once the WebSocket has closed, the server cleans up subscriptions attached to the terminated session; old subscription objects no longer represent active registrations on a new connection.

## 6. Managing multiple subscriptions

When a screen needs to receive multiple event types, storing subscriptions in a `Map` makes lifecycle management clear:

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

The key in the `Map` is an application-chosen name to manage the feature; `destination` is the STOMP address; `subscription.id` is the protocol ID generated by the library or provided by the application. These three concepts serve different purposes.

The `addSubscription` function above proactively rejects registration when the client is disconnected. If the application needs to remember intended subscriptions prior to connecting, store the desired configuration separately and perform the subscriptions inside `onConnect`.

## 7. Avoiding duplicate registrations

A common mistake is calling `subscribe` on every component render or every time an initialization function runs again. After several renders, a single message can trigger callbacks multiple times because multiple subscriptions exist for the same destination.

How to prevent this:

- Place subscription calls in a spot with a clear lifecycle, such as after connecting or when a screen mounts.
- Save the handle returned by `subscribe`.
- Check current state before creating a new subscription.
- Cancel subscriptions when the component or screen is no longer used.
- Use distinct IDs for independent subscriptions.
- Avoid creating a new global subscription every time a UI event occurs.

Two subscriptions to the same destination can be intentional, such as two independent UI sections monitoring the same topic. In that case, manage them as two separate registrations and unsubscribe them individually.

## 8. Reconnecting and re-registering subscriptions

When a connection drops, the old STOMP session ends and that session's subscriptions become invalid. `@stomp/stompjs` can automatically reconnect according to `reconnectDelay`, but the application must still re-register needed destinations inside `onConnect`.

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

Do not call `subscribe` once before `client.activate()` and assume the library automatically restores all registrations. Put subscription logic inside `onConnect` or use a subscription manager that recreates registrations after each connection.

If you have dynamic subscriptions, keep a list of destinations the user currently wants to watch. Once reconnect succeeds, iterate over that list and create new subscriptions. When the user unwatches while disconnected, remove the destination from the desired list so it is not re-registered on the next connection.

Example demand-driven management model:

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

In this example, `desiredSubscriptions` is the business state the application wants to maintain. `liveSubscriptions` holds only handles of the current connection. Separating the two kinds of state helps the application restore registrations after reconnecting without mistakenly keeping handles from an old session.

## 9. Managing subscriptions by UI lifecycle

In SPA interfaces, a subscription is often tied to a screen or component. When the screen appears, subscribe to receive data; when the screen is destroyed, cancel the subscription.

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

In React, similar logic can be called from `useEffect` returning a cleanup function. Note that the client must be connected before the effect subscribes. If the connection completes after the component has mounted, integrate the component with connection state and perform the subscription in `onConnect` or when state transitions to connected.

Do not place `subscribe` directly in the component body because the component body can execute multiple times. Use an effect or a lifecycle-managed service to avoid duplicate registrations.

## 10. Receipts and subscription confirmation

STOMP allows clients to add a `receipt` header to a frame, after which the server can return a `RECEIPT` frame confirming the corresponding frame was processed.

With `@stomp/stompjs`, you can register a callback with `watchForReceipt` before sending a frame that has a `receipt` header:

~~~javascript
const receiptId = "orders-subscribe-001";

client.watchForReceipt(receiptId, (frame) => {
  console.log("Server confirmed:", frame.headers["receipt-id"]);
});

const subscription = client.subscribe(
  "/topic/orders",
  (message) => console.log(message.body),
  { receipt: receiptId }
);
~~~

Receipts are useful when the application needs confirmation that the server has processed a frame before taking the next step. A receipt is a protocol-layer confirmation; it does not prove the client-side callback processed a message, does not confirm a business transaction committed, and does not by default prove data was durably saved.

Not every broker supports receipts. Spring's simple broker only supports a subset of STOMP and does not support receipts. If using the simple broker, do not build application flows that depend on RECEIPT. Verify the capabilities of your broker before implementing.

If you need to know when Spring finishes processing SUBSCRIBE with the simple broker, you can monitor `brokerChannel` with an `ExecutorChannelInterceptor` and handle `afterMessageHandled`. `SessionSubscribeEvent` only notifies that Spring received the SUBSCRIBE frame; it is not a receipt confirming the broker finished processing the registration.

## 11. Acknowledgments when receiving messages

The `ack` header of SUBSCRIBE determines how the client acknowledges messages:

| Mode | Meaning |
| --- | --- |
| auto | Server considers the message delivered as soon as it is sent to the client; client does not need to send ACK. |
| client | Client sends ACK after processing; ACKs are cumulative within the subscription. |
| client-individual | Client acknowledges each message individually. |

Example using `@stomp/stompjs` with a broker supporting acknowledgment:

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

ACK should only be sent after the application completes the processing step it intends to confirm. If ACK is sent before saving data or finishing the work, a subsequent error may cause the application to lose the chance to reprocess the message.

When the broker supports redelivery, unacknowledged messages may be redelivered after connection loss. Therefore, consumers should be designed with idempotent processing: if the same message arrives a second time, the business outcome remains correct.

ACK/NACK capability depends on the broker. Spring's simple broker does not support `client`/`client-individual` acknowledgment modes; it only implements a simple subset of STOMP. If ACK, NACK, or redelivery is required, use a broker relay to a dedicated broker and check that broker's exact semantics.

## 12. Closing the client and cleaning up subscriptions

When only stopping reception for one message type while keeping the connection alive, call `subscription.unsubscribe()`.

When stopping the entire client and preventing reconnection, call:

~~~javascript
await client.deactivate();
~~~

`deactivate()` runs the disconnection process and returns a Promise that resolves once deactivation finishes. This is the appropriate method when leaving a page, logging out, or no longer needing the STOMP client.

There is no need to send separate UNSUBSCRIBE frames for every subscription before closing the entire connection. When the session ends, the server cleans up subscriptions associated with that session. However, if keeping the connection open for other destinations, unsubscribe individually from destinations no longer needed.

Do not use `forceDisconnect()` for normal shutdown flows. This API closes the WebSocket directly, skipping the STOMP DISCONNECT sequence and potentially causing the server to detect the disconnect later. Use it only in special recovery situations where the connection cannot be closed normally.

## 13. Security and destination control

Knowing a destination does not mean having permission to subscribe to it. The server must authenticate the user and check SUBSCRIBE permissions.

Key considerations:

- Do not let everyone subscribe to every topic just because a destination does not hold secret data.
- Enforce permissions by user, tenant, room, or resource.
- Use user-specific destinations for personal data, such as `/user/queue/notifications` when aligned with Spring configuration.
- Do not trust `userId`, `role`, or `tenantId` passed by the client in headers/payloads.
- Limit subscription counts and wildcard scopes to prevent clients from creating excessive registrations.
- On logout, close the client and clear subscription state in the UI layer.
- Do not log tokens, cookies, or sensitive payloads in STOMP debug logs.

When using Spring Security, configure message authorization for SEND and SUBSCRIBE destinations. Authorization rules must apply both to messages entering controllers and messages going directly to the broker.

## 14. Testing subscriptions

An integration test should verify both subscribing and unsubscribing:

1. Start the Spring application with the WebSocket/STOMP endpoint.
2. Connect the STOMP client and wait for `onConnect`.
3. Subscribe to destination `/topic/test`.
4. Send a message from the server to `/topic/test`.
5. Verify the callback receives the right payload.
6. Call `subscription.unsubscribe()`.
7. Send another message to `/topic/test`.
8. Verify the unsubscribed callback does not receive the new message.
9. Re-establish the connection and verify `onConnect` re-registers the required destination.

Additional test cases:

- Two subscriptions to the same destination with different IDs.
- Two subscriptions to the same destination where only one is unsubscribed.
- Intentionally registering duplicate IDs within the same session.
- Subscribing while the client is not connected.
- Sudden connection drop and reconnect.
- User unsubscribes while offline.
- Broker rejects an invalid destination or frame.
- Client lacks permission to SUBSCRIBE to a private destination.
- Receipts or ACK only when the broker under test supports those features.

To test callback logic, you can mock the message handler. However, to verify destinations, SUBSCRIBE/UNSUBSCRIBE frames, reconnects, and security, integration tests against a real STOMP endpoint are necessary.

## 15. Common pitfalls

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| `subscribe()` reports client not connected | Calling `subscribe` before CONNECTED | Move the call into `onConnect` or wait for connected state. |
| One message triggers callback multiple times | Multiple subscriptions to the same destination | Save handles, prevent duplicate registrations, and unsubscribe old ones. |
| `unsubscribe()` does not cancel the right registration | Wrong ID used or handle mix-up | Call `unsubscribe()` on the exact `StompSubscription` object. |
| Reconnect succeeds but no messages arrive | Did not resubscribe after the new CONNECTED | Re-register inside `onConnect` on every successful connection. |
| Messages arrive after leaving screen | Cleanup did not run or handle was not saved | Tie subscriptions to component lifecycle and invoke cleanup. |
| Receipt callback does not fire | Broker does not support receipts or watcher registered at the wrong time | Check broker; call `watchForReceipt` before sending the frame with `receipt`. |
| ACK/NACK rejected | Broker does not support the chosen ack mode | Check broker capabilities; Spring simple broker does not support ACK/NACK. |
| Client receives another tenant's messages | Server does not enforce SUBSCRIBE permissions | Apply destination authorization and authenticate users. |
| Old subscription recreated after reconnect even though user unwatched | Desired subscription list was not updated | Remove the destination from `desiredSubscriptions` when canceling. |

## 16. Takeaways

- SUBSCRIBE registers to receive messages; UNSUBSCRIBE cancels a subscription by ID.
- Each subscription on the same connection needs a unique ID; `@stomp/stompjs` auto-generates an ID if omitted.
- `subscribe()` returns `StompSubscription`; prefer calling `unsubscribe()` on this handle.
- Call `subscribe` after CONNECTED; use `onConnect` to re-register after every reconnect.
- Store desired state and current connection handles separately when managing dynamic subscriptions.
- Receipts, ACK, and NACK depend on the broker; Spring's simple broker does not support receipts or acknowledgments.
- Cancel subscriptions following screen lifecycle; use `deactivate()` when closing the entire STOMP client.
- Securing SUBSCRIBE is as important as securing SEND; the server must enforce destination access rights.

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

