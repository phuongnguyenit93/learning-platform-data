# Reconnecting, Resubscribing, and Restoring Application State

## 1. Why reconnecting is not enough?

In a STOMP application, the WebSocket connection and STOMP session have their own lifecycles. When the network fluctuates, a browser switches networks, the server restarts, or the broker pauses temporarily, the current connection may close. The client must establish a new STOMP session to continue exchanging messages.

However, **a successful reconnect does not mean application state has been restored**. A new session does not automatically carry over:

- Subscriptions from the old session.
- Messages emitted while the client was offline.
- Business state currently displayed by the client.
- Commands sent where the client does not yet know whether the server processed them.
- The last position the client processed in an event stream.

Therefore, three separate concerns must be handled:

1. **Reconnect**: re-create the transport and STOMP session after losing connection.
2. **Resubscribe**: re-register all destinations to listen to after the broker confirms the new session.
3. **State recovery**: resynchronize data, detect event gaps, deduplicate messages, and reconcile pending commands.

A client displaying "connected" right after STOMP CONNECTED is insufficient. For applications with important data, include a "synchronizing" state and only transition to "ready" after synchronization completes.

## 2. Distinguishing connection layers and failures

A STOMP over WebSocket flow typically spans these layers:

| Layer | Components | Possible failures |
|---|---|---|
| Network | Wi-Fi, mobile network, proxy, load balancer | Network loss, timeout, idle connection closed. |
| WebSocket | Browser WebSocket or SockJS transport | Socket closed, handshake error, proxy drops connection. |
| STOMP | CONNECT, CONNECTED, SUBSCRIBE, MESSAGE | Broker sends ERROR, heartbeat timeout, session terminated. |
| Application | Store, cache, event handler, sync API | Stale data, missed events, duplicate or out-of-order events. |

Heartbeats detect an unresponsive connection; they do not store missed messages and do not automatically recover business state.

Two types of reconnect must also be distinguished:

- **Client reconnect**: the client creates a new WebSocket/STOMP session and must resubscribe.
- **Broker relay reconnect**: in a Spring configuration using a broker relay, Spring automatically restores the system connection to the broker when possible. Client connections are not automatically restored on behalf of browsers; clients must perform their own reconnect.

Spring emits events such as `SessionConnectEvent`, `SessionConnectedEvent`, and `SessionDisconnectEvent` to observe session lifecycles. `SessionConnectedEvent` is published after the broker sends CONNECTED. `SessionDisconnectEvent` is sometimes published multiple times for the same session, so server-side cleanup must be idempotent.

## 3. Automatic reconnection with STOMP.js

The `@stomp/stompjs` library has built-in reconnect support. The `reconnectDelay` property specifies the wait time between connection attempts in milliseconds; the default is 5,000 ms. Set it to 0 to disable automatic reconnection.

Exponential backoff can be used to gradually increase wait times when the broker or network is unavailable:

~~~javascript
import { Client, ReconnectionTimeMode } from "@stomp/stompjs";

const client = new Client({
    brokerURL: "wss://app.example.com/ws",
    reconnectDelay: 1000,
    reconnectTimeMode: ReconnectionTimeMode.EXPONENTIAL,
    maxReconnectDelay: 30000,
    connectionTimeout: 8000,
    heartbeatIncoming: 10000,
    heartbeatOutgoing: 10000
});

client.activate();
~~~

With this configuration, the client begins retrying after roughly 1 second; exponential backoff increases the delay between attempts and caps it at 30 seconds. Tune values to match system recovery time and broker limits. If many clients disconnect simultaneously, backoff reduces the load caused by everyone reconnecting incessantly. If jitter is needed to keep clients from retrying at the same instant, add an attempt-spreading policy at the application layer.

Do not instantiate a new `Client` object every time the socket closes. Manage a single client instance for the component or application lifecycle and let the library drive the reconnect loop. Creating multiple instances can spawn duplicate connections and duplicate subscriptions.

## 4. Resubscribing inside onConnect

This is the most important STOMP.js rule: the `onConnect` callback runs after **every successful STOMP connection**, including the initial connection and all subsequent reconnects. The library does not automatically re-register destinations subscribed in the previous session. Therefore, place all required `subscribe` calls inside `onConnect`.

~~~javascript
import { Client } from "@stomp/stompjs";

const subscriptions = new Map();

const client = new Client({
    brokerURL: "wss://app.example.com/ws",
    reconnectDelay: 5000,
    heartbeatIncoming: 10000,
    heartbeatOutgoing: 10000,

    onConnect: () => {
        setConnectionStatus("synchronizing");

        // This is a new STOMP session. Re-create all needed subscriptions.
        subscriptions.clear();

        const ordersSubscription = client.subscribe(
            "/user/queue/orders",
            (message) => {
                handleOrderMessage(JSON.parse(message.body));
            }
        );

        subscriptions.set("orders", ordersSubscription);

        const alertsSubscription = client.subscribe(
            "/user/queue/alerts",
            (message) => {
                handleAlertMessage(JSON.parse(message.body));
            }
        );

        subscriptions.set("alerts", alertsSubscription);

        // After registering to receive events, resynchronize data.
        void synchronizeApplicationState();
    },

    onWebSocketClose: () => {
        subscriptions.clear();
        setConnectionStatus("reconnecting");
    },

    onStompError: (frame) => {
        reportBrokerError(frame.headers["message"], frame.body);
    }
});

client.activate();
~~~

Functions `setConnectionStatus`, `handleOrderMessage`, `handleAlertMessage`, `synchronizeApplicationState`, and `reportBrokerError` are application business functions to be implemented against your actual store and APIs.

In the example, subscription handles are kept in a `Map` so subscriptions can be canceled or updated when needed. When the WebSocket closes, handles from the old session no longer represent active subscriptions. After a new CONNECTED, register again using new handles.

Do not call `subscribe` simultaneously from multiple places such as component initialization, reconnect callbacks, and state recovery callbacks. Pick a single owner for registration, typically `onConnect`, to avoid duplicate subscriptions.

## 5. Tracking connection state

Represent connection state explicitly in both UI and application logic:

| State | Meaning | Appropriate behavior |
|---|---|---|
| `connecting` | Establishing initial connection. | Show connecting indicator; do not send STOMP-dependent commands yet. |
| `connected` | STOMP CONNECTED received. | Can register subscriptions; data may not be synced yet. |
| `synchronizing` | Subscriptions created and application is recovering data. | Buffer events; avoid showing ready state too early. |
| `ready` | Baseline data synced up to a known cursor/version. | Allow normal realtime business flows. |
| `reconnecting` | Socket/session lost and client will retry connecting. | Show temporary status; retain existing data but mark it potentially stale. |
| `sync-error` | Connection may be up, but data synchronization failed. | Retry sync or prompt user to retry; do not pretend data is fresh. |
| `closed` | Application intentionally stopped the client. | Stop reconnecting. |

STOMP.js provides `onConnect`, `onDisconnect`, `onWebSocketClose`, `onWebSocketError`, `onHeartbeatLost`, and `onChangeState`. Use the callbacks matching the events you need to observe. `onDisconnect` reflects a clean DISCONNECT; when a socket drops abruptly, the client will not always receive a DISCONNECT receipt, so monitor `onWebSocketClose`.

Do not equate an open WebSocket with a ready STOMP session. Wait for the broker to send CONNECTED and the `onConnect` callback to run before sending messages or registering subscriptions.

## 6. Heartbeats and dead-connection detection

STOMP heartbeats help both sides detect an inactive connection. STOMP.js has two main properties:

- `heartbeatOutgoing`: interval for sending heartbeats from client to server.
- `heartbeatIncoming`: interval at which the client expects heartbeats from the server.

The current STOMP.js default is 10,000 ms for each direction; set to 0 to disable that direction. Heartbeats are exchanged only when both sides negotiate and support heartbeats per the STOMP version.

~~~javascript
const client = new Client({
    brokerURL: "wss://app.example.com/ws",
    heartbeatOutgoing: 10000,
    heartbeatIncoming: 10000,
    heartbeatToleranceMultiplier: 2,

    onHeartbeatLost: () => {
        setConnectionStatus("reconnecting");
    }
});
~~~

Do not set heartbeats too short in systems with many clients, since each connection requires periodic task handling. Proxies or load balancers also have their own idle timeouts; heartbeat configuration must fit the timeouts of network layers.

Browsers may throttle timers when tabs are in the background. STOMP.js supports a Web Worker-based heartbeat strategy in browser environments to improve heartbeat stability for background tabs. This is an operational option, not a replacement for reconnection and state recovery.

Heartbeats detect failures faster than waiting solely for TCP timeouts, but do not guarantee that events emitted during the disconnection window will be replayed.

## 7. Refreshing tokens before each connection attempt

A reconnect may occur after an access token has expired. If the application authenticates STOMP CONNECT via a token in headers, use `beforeConnect` to fetch a fresh token before each connection attempt:

~~~javascript
const client = new Client({
    brokerURL: "wss://app.example.com/ws",
    reconnectDelay: 5000,

    beforeConnect: async () => {
        const token = await refreshAccessToken();

        client.connectHeaders = {
            Authorization: "Bearer " + token
        };
    },

    onConnect: () => {
        registerSubscriptions();
    }
});
~~~

This snippet assumes the backend has an interceptor or STOMP CONNECT authentication mechanism that reads the `Authorization` header. For Spring applications authenticating via HTTP handshake and cookies/sessions, refresh the HTTP session or cookie according to the application's login mechanism; STOMP CONNECT headers are not HTTP headers of the WebSocket handshake.

Do not put tokens or passwords in URLs, as URLs commonly appear in logs, browser history, and monitoring systems. Do not log full CONNECT headers or raw STOMP frames in production if they contain sensitive information.

If refreshing the token fails because the user logged out or the refresh token expired, stop reconnecting per authentication policy and transition the application to a re-login state. Avoid retrying indefinitely with expired credentials.

## 8. Recovering application state from a snapshot

Subscriptions only deliver new messages after they become active. They do not automatically replay all missed history. For displayed data such as order lists, notifications, balances, or task statuses, provide a snapshot API to load the current state from the server.

Basic procedure:

1. After STOMP CONNECTED, register required subscriptions.
2. If the broker supports STOMP RECEIPT for SUBSCRIBE, wait for the receipt confirming the broker processed the subscription.
3. While loading the snapshot, temporarily buffer newly arrived events.
4. Call the API to fetch a snapshot carrying a version or sequence number.
5. Replace local state with the snapshot.
6. Apply buffered events whose sequence is greater than the snapshot version, in exact order.
7. If a sequence gap is detected, ask the server to replay events from the last cursor or fetch a new snapshot.
8. Only mark the application ready once state is synchronized.

Example snapshot API response:

~~~json
{
  "version": 1842,
  "orders": [
    {
      "id": "ORD-1001",
      "status": "SHIPPED"
    }
  ]
}
~~~

Example event carrying its own sequence and id:

~~~json
{
  "eventId": "evt-7f3a",
  "sequence": 1843,
  "type": "ORDER_STATUS_CHANGED",
  "orderId": "ORD-1001",
  "status": "DELIVERED"
}
~~~

The snapshot version and event sequence must belong to the same server-defined ordering scope, such as per user, tenant, or stream. Do not use client timestamps as absolute ordering because clocks across machines can drift.

STOMP RECEIPT can confirm the broker processed the SUBSCRIBE frame if supported. Receipts do not prove business data is synchronized and do not replace snapshots/replays. If the broker does not support receipts, use an appropriate application synchronization protocol and understand its consistency boundaries.

## 9. Preventing duplicate and out-of-order events

After reconnecting, the application may receive duplicate events due to broker redelivery, producer retries, or server-side replay mechanisms. For business-significant events, design idempotent consumers.

An event should contain at minimum:

- A unique `eventId` to identify the event.
- A `sequence` or `version` to determine order within a stream.
- An `aggregateId` or entity key to identify which object the event affects.
- `type` and a clearly defined payload schema.

Processing rules:

1. Ignore events with sequence less than or equal to the last applied sequence.
2. If the next sequence equals current sequence plus one, apply the event.
3. If the sequence jumps forward with a gap, pause applying that stream and request a replay or snapshot.
4. If `eventId` was already processed, do not execute side effects again.
5. Update cursor/version after changing state successfully.

If multiple aggregates have independent sequences, do not compare sequences across different aggregates. Cursors must be bound to the exact stream or partition for which the server guarantees ordering.

## 10. Recovering sent commands with unknown outcomes

A tricky scenario is when the client sends STOMP SEND and the socket closes before a response arrives. The client does not know whether the server received the command. Resending immediately could execute the operation twice.

For commands with business effects such as creating orders, payments, submitting requests, or changing status:

- Attach a unique `commandId`/idempotency key to every command.
- Persist pending commands on the client if recovery across page reloads is needed.
- Have the server store processing results by `commandId` and refuse to execute side effects a second time.
- After reconnecting, have the client query the `commandId` status before deciding whether to resend.
- Remove the command from the outbox only once the server confirms the business outcome.

STOMP RECEIPT only confirms the broker processed the corresponding frame per the protocol; it does not automatically prove a database business transaction committed or downstream consumers finished. When business outcome guarantees are needed, the server must return an application-layer acknowledgment with an explicit `commandId` and status.

Exactly-once processing cannot be achieved through reconnect and resubscribe alone. In practice, it requires combining at-least-once delivery, idempotency, and durable cursor persistence.

## 11. Subscription receipts and when to mark ready

STOMP supports the `receipt` header for frames such as SUBSCRIBE and SEND. STOMP.js lets you register a callback via `watchForReceipt` and then send the frame with a `receipt` header:

~~~javascript
const receiptId = "orders-subscription-" + Date.now();

client.watchForReceipt(receiptId, () => {
    console.log("Broker confirmed SUBSCRIBE");
    // You can start the snapshot sync step here.
});

client.subscribe(
    "/topic/orders",
    handleOrderMessage,
    { receipt: receiptId }
);
~~~

Register the watcher before sending SUBSCRIBE so an early receipt is not missed. Receipt support and exact processing semantics depend on the broker. When using a broker without receipt support, do not assume the subscription is active merely because `subscribe` returned.

Even after receiving the receipt, the application still needs to complete snapshot/replay and drain the event buffer before switching state to ready.

## 12. Intentional disconnection

Two cases must be distinguished:

- **Unintentional disconnect**: network or server failure; the client should keep reconnecting if the application is still active.
- **Intentional close**: user logs out, closes the app, or component unmounts; stop reconnecting and release resources.

With STOMP.js, call `deactivate()` to stop the reconnect loop and close the active connection:

~~~javascript
async function logoutMessaging() {
    setConnectionStatus("closed");
    subscriptions.clear();
    await client.deactivate();
}
~~~

Do not call `deactivate()` merely upon receiving `onWebSocketClose` during a temporary network disruption; doing so terminates automatic reconnection. When re-enabling later, call `activate()` according to the application lifecycle.

In React or component frameworks, create the client inside a single owner, register callbacks once, and call `deactivate` when that owner unmounts. Avoid creating additional clients or subscriptions on every render.

## 13. Server-side Spring: tracking sessions and idempotent cleanup

A Spring server can listen to STOMP session events:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.messaging.SessionConnectedEvent;
import org.springframework.web.socket.messaging.SessionDisconnectEvent;

@Component
public class StompSessionLifecycleListener {

    @EventListener
    public void onConnected(SessionConnectedEvent event) {
        // Broker returned CONNECTED; STOMP session is ready.
        // You can update presence or metrics.
    }

    @EventListener
    public void onDisconnected(SessionDisconnectEvent event) {
        // Cleanup must be idempotent because the event may fire multiple times.
        // Extract session id from message headers if needed.
    }
}
~~~

Do not treat a single disconnect event as proof the user logged out completely. A user may have multiple sessions across tabs or devices. Presence management should count or track sessions per user and only mark offline when no valid sessions remain. Cleanup must tolerate duplicate events, session timeouts, and rapid reconnects.

## 14. Testing reconnect and state recovery

Do not test only the normal server startup path. Simulate the following scenarios:

| Scenario | Expected outcome to verify |
|---|---|
| Network drops then recovers | Client reconnects and `onConnect` callback runs again. |
| Broker restart | Client detects session loss and reconnects once broker is ready. |
| WebSocket proxy timeout | Heartbeat or close event triggers reconnect. |
| Token expires while offline | Token is refreshed or client transitions to login-required state. |
| Multiple consecutive reconnects | No duplicate subscriptions or extra `Client` instances are created. |
| Events emitted while client offline | Snapshot/replay brings state to the latest version. |
| Events delivered twice | Idempotency prevents duplicate side effects. |
| Events arrive out of order or missing sequence | Client detects gap and requests resynchronization. |
| SEND interrupted before result arrives | `commandId` determines whether command ran or needs resending. |
| Logout while reconnecting | `deactivate` stops further attempts. |
| Multiple tabs logged in simultaneously | Each session subscribes independently; presence and broadcasts behave properly. |

During testing, record timestamps, client state, STOMP session id, reconnect count, active subscription count, cursor/version, and `commandId`. Do not log access tokens, passcodes, or sensitive payloads.

## 15. Reference recovery flow

~~~mermaid
flowchart TD
    A["WebSocket or heartbeat lost"] --> B["Mark reconnecting"]
    B --> C["Client retries connection with backoff"]
    C --> D{"Received STOMP CONNECTED?"}
    D -->|No| C
    D -->|Yes| E["Re-register all subscriptions"]
    E --> F["Wait for SUBSCRIBE receipt if broker supports it"]
    F --> G["Buffer new events and load snapshot/cursor"]
    G --> H{"Sequence gap detected?"}
    H -->|Yes| I["Replay events or load new snapshot"]
    I --> H
    H -->|No| J["Apply new events, deduplicate"]
    J --> K["Reconcile pending commands"]
    K --> L["Mark ready"]
~~~

This ordering cleanly separates transport recovery from business recovery. If the broker does not support receipts, replace step F with the designed application sync mechanism; do not skip determining when subscriptions actually take effect.

## 16. Common pitfalls

- **Reconnecting without resubscribing:** the new STOMP session has no subscriptions. Put registrations in the callback that runs after every CONNECTED.
- **Subscribing in multiple callbacks:** one destination gets registered multiple times and event handlers run repeatedly. Centralize subscription ownership in one place.
- **Marking connected as soon as WebSocket opens:** broker has not sent CONNECTED or state is not synced yet. Separate connecting, connected, synchronizing, and ready.
- **Assuming offline messages automatically replay:** standard STOMP subscriptions are not an event log. Use snapshots or cursor-based replays.
- **Applying events without checking versions:** duplicate or out-of-order events can regress or corrupt state. Use `eventId` and `sequence`.
- **Resending commands with unknown outcomes:** server may have processed them before the socket closed. Use idempotency keys and query command status.
- **Skipping token refresh:** repeated reconnects with expired credentials. Refresh credentials before each attempt when required by your auth architecture.
- **Calling deactivate on temporary network loss:** client stops auto-reconnecting. Only call `deactivate` when intentionally shutting down the client.
- **Non-idempotent cleanup:** server may receive multiple disconnect events for the same session. Design cleanup to withstand repeated calls.

## 17. Takeaways

Reconnecting creates a new STOMP session; resubscribing restores the message stream; snapshots/replays and cursors restore business state. With STOMP.js, configure `reconnectDelay` and heartbeats, place all subscriptions inside `onConnect`, monitor `onWebSocketClose`, and use `deactivate` for intentional shutdown. To prevent lost or duplicate event processing, the server must provide versioned/sequenced snapshots or replays, and the client needs idempotency and `commandId` tracking for uncertain commands. Mark the application ready only after subscriptions and data are synchronized.

## References

- [STOMP.js — Using StompJs](https://stomp-js.github.io/guide/stompjs/using-stompjs-v5.html)
- [STOMP.js — Client API](https://stomp-js.github.io/api-docs/latest/classes/Client.html)
- [Spring Framework — STOMP Application Context Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html)
- [Spring Framework — STOMP Client](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html)