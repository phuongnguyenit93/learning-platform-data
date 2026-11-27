# WebSocket Routes and Real-Time Connection Management

> **Chapter:** API Gateway and AppSync  
> **Module:** `CLOUD_PROVIDERS_AWS` — exploring AWS from Regions/AZs, IAM, and VPCs to compute, storage, databases, integration, and serverless; practicing service selection, secure deployment, monitoring, resilience, and cost optimization.

Normally, a web application sends an HTTP request and receives an HTTP response; to check for new messages, the client must send another request or use another streaming mechanism. With **WebSocket**, the client and server establish **a long-lived bidirectional connection**, allowing either side to send messages without opening a new HTTP request for each event.

**Amazon API Gateway WebSocket API** provides a managed `wss://...` endpoint, routes incoming **messages** to backend integrations such as **AWS Lambda**, and lets the backend proactively push data to connected clients via the **API Gateway Management API** (`@connections`). It is a strong choice for chat, event-driven dashboards, live collaboration, device status, and real-time notifications.

However, API Gateway **does not automatically track** "user A is in chat room B," does not guarantee exactly-once delivery of business events, and does not persist offline messages. Your application must manage **connection IDs, identities, channel subscriptions, permissions, fan-out, retries, and state** in backend services like DynamoDB, Lambda, SQS, or EventBridge.

All API IDs, accounts, Regions, DynamoDB table names, and domains in the examples are **placeholders**, not existing resources. Infrastructure changes can incur charges; deploy only in authorized test environments.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **API Gateway WebSocket API** from HTTP API/REST API and AppSync subscriptions when choosing a real-time transport.
2. Describe the **HTTP Upgrade → `$connect` → messages → `$disconnect`** lifecycle and the best-effort limitations of disconnect events.
3. Design the **route selection expression** `$request.body.action`, the three special routes (`$connect`, `$disconnect`, `$default`), and custom routes.
4. Explain the difference between a **Lambda integration response** and a **server push to clients** via `@connections`.
5. Configure authentication at the WebSocket handshake, distinguish **IAM `execute-api:Invoke`** from **`execute-api:ManageConnections`**, and protect data by user and chat room.
6. Persist connection state in DynamoDB and handle **`410 Gone`**, heartbeats, TTLs, reconnects, and offline messages.
7. Read Node.js Lambda examples, JavaScript clients, CloudFormation fragments, and read-only AWS CLI diagnostic commands.
8. Estimate throughput, latency, connection counts, and costs, and test applications under connection-loss scenarios.

## 2. Why Use WebSockets?

### 2.1. HTTP Polling, Server-Sent Events, and WebSocket

| Mechanism | Direction | Characteristics | Best-fit use cases |
| --- | --- | --- | --- |
| **HTTP polling** | Client asks, server answers | Simple, but wastes requests even when no new data exists | Dashboards with low real-time urgency |
| **Long polling** | Client sends request, server holds until data arrives or timeout | Reduces empty polls, still must re-open requests | Notifications where newer protocols are constrained |
| **Server-Sent Events (SSE)** | Server → client over a long-lived HTTP connection | Convenient for one-way event streams | Progress updates, streaming output |
| **WebSocket** | **Client ↔ server** over one connection | Full-duplex; messages share the same WebSocket endpoint | Chat, live collaboration, telemetry, real-time status |

WebSockets are not inherently reliable at the **business layer**. TCP orders bytes within a living connection, yet **when networks drop**, server and client still need retries, idempotency, and replay of unacknowledged messages.

### 2.2. How Does API Gateway WebSocket Differ from AppSync?

| Need | API Gateway WebSocket API | AWS AppSync |
| --- | --- | --- |
| Protocol and model | App-defined WebSocket messages; routed by payload fields | GraphQL API with subscriptions or AppSync real-time/event features |
| Routing | `$connect`, `$disconnect`, `$default`, custom route keys | GraphQL schemas/resolvers/subscriptions or matching event model |
| User/room state | Application builds registry, authorization, and fan-out | Higher-level real-time abstractions; still requires auth and data design |
| Best fit | Full control over custom protocol, commands/rooms, and callback logic | Apps matching a GraphQL data model or AppSync real-time/event model |
| Backend management effort | Self-manage message routing, delivery, and connection registry | Abstractions can reduce boilerplate |

**Do not assume WebSocket is the only choice for real-time features.** When clients query/mutate GraphQL-modeled data and subscribe to changes, AppSync subscriptions may be simpler. When you need custom message protocols and independent routes, API Gateway WebSocket API gives finer control.

## 3. Reference Architecture: Client, API Gateway, Lambda, and DynamoDB

~~~mermaid
flowchart TB
    C1["Client A\nbrowser / mobile"] <-->|"WSS: $connect + messages"| GW["API Gateway\nWebSocket API + stage"]
    C2["Client B\nbrowser / mobile"] <-->|"WSS"| GW
    GW -->|"Route: $connect / $disconnect"| CONN["Lambda ConnectionHandler"]
    GW -->|"Route: join / sendMessage / $default"| MSG["Lambda MessageHandler"]
    CONN <-->|"Put/Delete state"| DDB["DynamoDB\nConnections + RoomMembers"]
    MSG <-->|"Query membership / check permissions"| DDB
    MSG -->|"POST @connections/{id}"| MGMT["API Gateway Management API\nHTTPS endpoint"]
    MGMT -->|"Push message"| GW
    EVENTS["SQS / EventBridge / workflow\non business events"] -->|"Async trigger"| PUSH["Lambda NotificationWorker"]
    PUSH -->|"Read subscriptions"| DDB
    PUSH -->|"POST @connections"| MGMT
~~~

*The diagram illustrates logical connections. API Gateway does not require all messages to hit a single Lambda; you can wire multiple Lambda integrations or other backends. Traffic from API Gateway to Lambda is an integration invocation, not the client WebSocket connecting directly to Lambda.*

**Sample chat flow:**

1. Client A connects to `wss://{api-id}.execute-api.{region}.amazonaws.com/{stage}`.
2. API Gateway processes the HTTP Upgrade and invokes the `$connect` route integration to authenticate and initialize state.
3. A sends JSON `{"action":"join","roomId":"lobby"}`; API Gateway selects route `join`.
4. Lambda checks whether the user is permitted to join the room and adds `connectionId` to the registry.
5. A sends `{"action":"sendMessage","roomId":"lobby","text":"Hello"}`.
6. Lambda queries connection IDs belonging to the room and calls the **Management API** to push to each active connection.
7. When client B receives the message on its open socket, B displays it and enforces ordering/idempotency per protocol.

**Crucial distinction:** Lambda does not hold open sockets in RAM between invocations. API Gateway holds the WebSocket connections, while the backend uses connection IDs and the callback API to send data back.

## 4. WebSocket Connection Lifecycle

### 4.1. HTTP Upgrade and the `$connect` Route

A client requests a connection over `wss://` (WebSocket over TLS). Before the WebSocket is accepted, API Gateway runs the **`$connect`** route integration.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as API Gateway WebSocket
    participant A as $connect authorizer
    participant L as $connect integration Lambda
    participant D as DynamoDB Connections
    C->>G: HTTPS Upgrade (WSS handshake)
    G->>A: Check $connect authorization (if configured)
    alt Denied
        A-->>G: Deny
        G-->>C: HTTP 401/403; socket not established
    else Allowed
        A-->>G: Principal/context
        G->>L: $connect event + connectionId
        L->>D: Save connectionId, userId, TTL
        L-->>G: statusCode 200
        G-->>C: WebSocket handshake complete
    end
~~~

Notes:

- Only after `$connect` succeeds does the client have an established WebSocket connection. If auth or the integration fails, the handshake is rejected.
- `connectionId` is assigned by API Gateway and provided in `event.requestContext.connectionId`.
- Clients must never generate or spoof connection IDs; the server always reads it from API Gateway's request context.
- **Do not push via `@connections` prematurely before `$connect` finishes**: the connection is not ready yet and returns **`410 GoneException`**. To send a welcome message, have the client send `join`/`ready` after the `open` event, or use an async workflow that pushes only once the connection is established.

### 4.2. Receiving a Message

While the connection is open, every message sent by the client goes through the **route selection expression**. API Gateway picks a matching custom route or `$default` and invokes its integration.

Example request:

~~~json
{
  "action": "sendMessage",
  "roomId": "lobby",
  "messageId": "msg-000123",
  "text": "What is my order status?"
}
~~~

The backend receives an event containing the message body and connection context. It can query data or publish async events, then push results back to users via `@connections`.

### 4.3. Closing Connections and `$disconnect`

Connections close when the client calls `close()`, loses network connectivity, hits idle/max timeouts, is closed by API Gateway, or is terminated by the backend via the Management API.

The **`$disconnect`** route runs **after** the connection closes and is **best effort**: there is no guarantee it always fires, arrives promptly, or succeeds in cleaning up every record.

Therefore:

- Use `$disconnect` to **attempt cleanup** of connection registry/membership records by `connectionId`.
- Add **TTL/cleanup** or periodic sweepers to remove stale connection IDs.
- Whenever `postToConnection` returns **`410 Gone`**, delete the stale connection safely.
- Never attempt to push WebSocket replies to the closing connection inside `$disconnect`.
- Never treat an uncleaned DynamoDB record as proof that a user is genuinely online.

### 4.4. Duration Quotas

Under standard API Gateway WebSocket API quotas, connections have roughly a **10-minute idle timeout** and a **2-hour maximum connection duration**. When either limit hits, clients must establish a new connection and will receive a new connection ID. Quotas vary by time and Region; verify the current **API Gateway quotas** page before deploying.

Applications commonly implement an **application-level heartbeat**—for example, sending `{"action":"ping"}` periodically to keep idle connections alive—paired with **reconnect using exponential backoff + jitter** when connections drop. Heartbeats cannot extend past the service's maximum connection lifetime.

## 5. Route Selection Expressions and Route Types

### 5.1. How Is a Route Key Selected?

When creating an API Gateway WebSocket API, you configure:

~~~text
Route selection expression: $request.body.action
~~~

For each **JSON text message** containing an `action` field, API Gateway uses its value to match a **route key**:

| Client sends | Selected route | Meaning |
| --- | --- | --- |
| `{"action":"join","roomId":"lobby"}` | `join` | Subscribe to a room |
| `{"action":"sendMessage","text":"Hi"}` | `sendMessage` | Send data to backend |
| `{"action":"ping"}` | `ping` if defined | Application-level heartbeat |
| `{"action":"unknown"}` | `$default` | No matching custom route |
| `{"payload":"x"}` | `$default` | No valid `action` value found |
| Non-JSON text | `$default` where supported by Gateway | Handle protocol errors cleanly |

**Never confuse route selection expressions with authorization.** Any connected client can send `action:"adminDelete"` if they guess the route name; the backend must still enforce business and data authorization regardless of which route ran.

### 5.2. Three Special Routes

| Route | When it runs | Appropriate responsibility |
| --- | --- | --- |
| **`$connect`** | During connection handshake | Authenticate/authorize, initialize connection registry, reject invalid handshakes |
| **`$disconnect`** | After connection closes (best effort) | Clean up connection/membership records, log status |
| **`$default`** | When no route matches or no route key is extracted | Return unknown-command error, handle fallback, bound payloads |

These three routes are not normal client actions invoked via JSON. Sending `{"action":"$disconnect"}` **does not** close the socket; clients close via WebSocket `close()`, or servers close via `deleteConnection` with proper IAM permissions.

### 5.3. Custom Routes

Applications typically define:

~~~text
join          → validate permissions and record membership
leave         → leave room
sendMessage   → validate, persist content, and fan-out
typing        → typing indicator (usually ephemeral, no long-term storage)
ping          → heartbeat / application keepalive
$default      → return unsupported-action error
~~~

Choose stable action names and validate JSON schemas in the backend. For sensitive commands like transferring permissions, deleting data, or bulk broadcasting, having a route **never replaces** IAM/business authorization and input validation.

## 6. Integration Responses vs. `@connections` Callbacks

A very common misconception is assuming that returning from Lambda:

~~~javascript
return { statusCode: 200, body: JSON.stringify({ ok: true }) };
~~~

automatically pushes `{"ok":true}` back to the WebSocket client like an HTTP API response. In API Gateway WebSocket API, Lambda return values depend on **integration response** and **route response** configuration.

### 6.1. Two Ways to Send Data to Clients

| Approach | Mechanism | When appropriate |
| --- | --- | --- |
| **Route response / integration response** | API Gateway maps integration output via configured route response | Direct reply to sender when two-way communication is configured |
| **Management API `postToConnection`** | Backend calls HTTPS `POST /@connections/{connectionId}` | Pushing to one or many clients, including after async processing |

By default, routes operate as **one-way** (client sends, backend runs, no automatic payload returned). To enable two-way responses, configure both route responses and integration responses; on WebSocket APIs, **the supported route response key is `$default`**. Mapping options vary by integration type.

**Most chat and notification architectures rely on the Management API**, because the backend must push messages to recipients other than the sender. API Gateway does not automatically broadcast messages to other connections on the API.

### 6.2. Management API Uses HTTPS, Not WSS

Clients connect over:

~~~text
wss://a1b2c3d4.execute-api.ap-southeast-1.amazonaws.com/prod
~~~

Backends send callbacks over:

~~~text
https://a1b2c3d4.execute-api.ap-southeast-1.amazonaws.com/prod
    └─ POST /@connections/{connectionId}
~~~

Primary `@connections` operations:

- **POST**: sends message bytes to an active connection.
- **GET**: retrieves supported connection metadata/status.
- **DELETE**: closes an active connection.

These **do not use normal HTTP API route permissions or endpoints**; the backend needs **IAM `execute-api:ManageConnections`** scoped to the right API ID, stage, and resource ARN.

With **custom domain names and API mappings**, the HTTPS callback URL may use a **base path mapping**—do not blindly append `/{stage}` to every custom-domain URL. The cleanest pattern is configuring an explicit `CALLBACK_ENDPOINT` per environment or deriving it carefully with awareness of custom domain mappings.

### 6.3. When Do You Get `410 Gone`?

`GoneException` (typically HTTP **`410`**) occurs when a `connectionId` is no longer active or not yet ready at callback time. Causes include:

- The client closed the browser tab or lost connectivity.
- The connection timed out and API Gateway closed it.
- The backend read a stale `connectionId` from DynamoDB.
- The backend pushed inside `$connect` before the handshake finished.

Proper handling: **mark the connection stale / delete it from the registry** and, if delivery is required, store the message in a queue or persistent inbox for retrieval on reconnect. Never retry indefinitely against a `Gone` connection.

### 6.4. Other Callback Errors

| Status | Typical meaning | Remediation |
| --- | --- | --- |
| **`403 Forbidden`** | Backend lacks `ManageConnections`, wrong ARN, or policy block | Check IAM role, API ID, stage, custom domain |
| **`410 Gone`** | Connection closed or nonexistent | Clean up registry; stop retrying |
| **`413 Payload Too Large`** | Payload exceeds API limits | Shrink payload, send a protected S3 reference/URL |
| **`429` / throttling** | Exceeded request/message throughput limits | Bounded concurrency, backoff + jitter, queuing |
| **`5xx` / timeout** | Transient service or network error | Bounded retries with application idempotency |

An HTTP `200` from `postToConnection` only means API Gateway accepted the callback—**it does not prove the client read, rendered, or processed the message**. When guaranteed delivery is required, clients must send **application-level acknowledgements** tracked by the server.

## 7. Connection Authentication and Authorization

### 7.1. Authenticating at `$connect`

API Gateway WebSocket APIs enforce access control on **`$connect`**, typically via IAM or a **Lambda `REQUEST` authorizer** where supported. Do not expect a REST/HTTP-style **Cognito User Pools authorizer** out of the box; validate Cognito JWTs inside a Lambda authorizer and return an IAM policy.

~~~mermaid
flowchart LR
    B["Client opens WSS"] --> A{"$connect authorizer"}
    A -->|"Deny"| X["Socket rejected"]
    A -->|"Allow + principalId"| C["$connect Lambda"]
    C --> REG["Registry connectionId ↔ userId"]
    REG --> OK["Handshake succeeds"]
    OK --> MSG["Custom routes"]
    MSG --> PERM{"Verify permissions per action/room"}
    PERM -->|"Allowed"| RUN["Execute business logic / push"]
    PERM -->|"Denied"| ERR["Push protocol error"]
~~~

**Distinguish clearly:**

- `$connect` authenticates **who is opening the connection**.
- Backend routes verify **whether that user may read a room, send a message, or touch current data**.
- Because connections live for up to hours, a token/JWT can expire or be revoked **after the handshake succeeds**. When immediate revocation is needed, enforce periodic revalidation, session TTLs, or call `deleteConnection` upon revocation.

### 7.2. Browser WebSockets Cannot Freely Add `Authorization` Headers

In standard browser JavaScript, `new WebSocket(url)` **cannot attach arbitrary `Authorization` headers** the way `fetch()` can. Common handshake patterns include:

- **Secure session cookies** when domain/cross-site rules and your authorizer support them.
- **Short-lived one-time connection tickets** minted by the backend and validated at `$connect`; if passed in a query string, guard against leaks in logs, analytics, proxies, and referrers.
- **WebSocket subprotocols** when supported and security-reviewed—never treat subprotocols as a secret hiding mechanism on their own.
- Native or server-to-server clients can sign requests or pass custom headers supported by the library and API Gateway authorizer.

Never place **AWS access/secret keys**, long-lived passwords, or persistent bearer tokens in URLs. Just because the transport uses `wss://` does not protect query parameters from appearing in logs.

### 7.3. IAM Permissions for the Management API

Example identity policy scoping a Lambda role strictly to **`POST`** callbacks on one API and stage:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PostToSpecificWebSocketConnections",
      "Effect": "Allow",
      "Action": "execute-api:ManageConnections",
      "Resource": "arn:aws:execute-api:ap-southeast-1:123456789012:a1b2c3d4/prod/POST/@connections/*"
    }
  ]
}
~~~

This is an **illustrative policy**, not a complete role: you also need `dynamodb:GetItem`, `dynamodb:Query`, `dynamodb:PutItem`, `dynamodb:DeleteItem`, and `logs:CreateLogStream`/`logs:PutLogEvents` as required. If calling `getConnection` or `deleteConnection`, grant `ManageConnections` for `GET`/`DELETE` resource paths too. `execute-api` ARNs differ from DynamoDB or Lambda ARNs.

**Never substitute `execute-api:Invoke` for `execute-api:ManageConnections`**; one governs invoking API routes, while the other governs Management API callbacks to connections.

## 8. Storing Connection State in DynamoDB

### 8.1. Why Do You Need a Registry?

API Gateway knows active **connection IDs**, but not which user owns which ID, which chat room they joined, which order they subscribed to, or which message they last processed. That is **application state**, commonly stored in DynamoDB for low latency, stateless server scaling, and serverless pay-per-use.

A simple **two-table** design:

| Table | Partition key | Sort key | Attributes |
| --- | --- | --- | --- |
| `Connections` | `connectionId` (String) | None | `userId`, `connectedAt`, `expiresAt` (TTL), minimal session metadata |
| `RoomMembers` | `roomId` (String) | `connectionId` (String) | `userId`, `joinedAt`, subscription metadata |

Sample items:

~~~json
{
  "Connections": {
    "connectionId": "ABC123=",
    "userId": "user-42",
    "connectedAt": 1795140000,
    "expiresAt": 1795150800
  },
  "RoomMembers": {
    "roomId": "lobby",
    "connectionId": "ABC123=",
    "userId": "user-42",
    "joinedAt": 1795140015
  }
}
~~~

These two JSON objects illustrate **Item attributes**, not table creation commands. One user can open **multiple browser tabs or devices**, so **`userId` cannot replace `connectionId`**. To notify all of a user's open devices, maintain a GSI on `userId` or a lookup mapping table to find every active `connectionId`.

### 8.2. Joining/Leaving Rooms and Fan-Out Queries

1. On `$connect`, persist the verified `connectionId + userId`.
2. On `join`, verify the user is allowed in `roomId`, then write `RoomMembers(roomId, connectionId)`.
3. On `sendMessage`, verify the sender is a member, **Query** by `roomId`, and push to the returned connection IDs.
4. On `leave`, delete the specific membership item.
5. On `$disconnect`, delete the connection item and all its memberships using your schema/index.

With `RoomMembers` keyed as shown, finding **every room for one `connectionId`** on disconnect requires a **GSI on `connectionId`** or a reverse-lookup mapping. Cleanup of a single hardcoded `lobby` room does not generalize to multi-room production apps.

### 8.3. DynamoDB TTL Does Not Delete Instantly

`expiresAt` can act as a **DynamoDB TTL attribute** in epoch seconds. DynamoDB TTL expires items **asynchronously**, rarely at the exact second of expiration. Therefore:

- Online presence must not rely solely on whether an item exists.
- When querying memberships, filter `expiresAt` in application logic if you must ignore expired items immediately.
- Keep `$disconnect`, `GoneException` cleanup, and background sweepers.
- TTL cleanup on `Connections` **does not automatically delete items in `RoomMembers`**; handle that via shared TTLs, streams, or sweepers.

### 8.4. Race Conditions and Newly Opened Connections

A `join` Lambda may run milliseconds after `$connect` wrote the connection item. In DynamoDB, use **`GetItem` with `ConsistentRead: true`** when reading immediately after a write on the **base table** (GSIs only support eventual consistency). Likewise, a member might leave right after a `Query` runs; callbacks will see `410 Gone` or deliver to a removed member unless checked at send time.

For strict ordering and membership invariants, design state machines, conditional writes, and version/epoch checks. Never treat "Query then POST" as an atomic transaction across DynamoDB and WebSocket callbacks.

## 9. Designing a Retry-Safe, Auditable Protocol

### 9.1. Clear Message Format

Client sends:

~~~json
{
  "action": "sendMessage",
  "requestId": "req-0199",
  "roomId": "lobby",
  "payload": {
    "text": "Order confirmed!"
  }
}
~~~

Server pushes:

~~~json
{
  "type": "message.created",
  "eventId": "evt-918273",
  "roomId": "lobby",
  "serverSequence": 27,
  "payload": {
    "senderId": "user-42",
    "text": "Order confirmed!"
  }
}
~~~

`requestId`, `eventId`, and `serverSequence` are **application-designed fields**, not generated by API Gateway. The server must allocate sequence numbers and IDs via a durable datastore when ordering matters rather than assuming Lambda invocations execute in global order.

### 9.2. Idempotency and Acknowledgements

To prevent client retries from creating duplicate messages:

- Require clients to generate a unique **`requestId`** and enforce deduplication via conditional writes with an idempotency TTL window.
- Persist important messages to DynamoDB or another datastore **before** fanning out.
- Include an **`eventId`** on pushed events so clients can send `ack` upon processing.
- On reconnect, clients send `lastSeenSequence` or a cursor so the backend can replay missed events from durable storage per policy.
- If a client receives a payload and drops before sending `ack`, the server may re-deliver it; clients must **deduplicate** by `eventId`.

**WebSocket transport does not guarantee business-level exactly-once delivery.** Build at-least-once delivery with deduplication for critical messages, or use at-most-once for ephemeral typing indicators and low-priority telemetry.

### 9.3. Never Stuff Large Payloads Inside Frames

API Gateway WebSocket APIs enforce limits such as **32 KiB per frame** and **128 KiB per message** (verify current quotas). For large reports or files, instead of pushing binaries over WebSocket:

1. Write the object to S3 with proper application permissions.
2. Push a small message containing `objectId` or a short-lived authorized download URL.
3. Have the client fetch the file over HTTPS with authentication, expiry, and checksums.

Never broadcast presigned URLs pointing to sensitive data into a room without verifying every recipient's permissions.

## 10. Node.js Lambda Example: Connect, Join Room, and Send Message

The example below illustrates a **single `lobby` room** using the **two DynamoDB tables** from Section 8. Its goal is demonstrating message flow—it is **not** a production chat server for thousands of connections. Assumptions:

- The API Gateway WebSocket API attaches a valid **Lambda `REQUEST` authorizer** to `$connect` returning `principalId`; without an authorizer, the handler rejects the handshake.
- Routes `$connect`, `$disconnect`, `$default`, `join`, and `sendMessage` point to the Lambda integration.
- Lambda environment variables `CONNECTIONS_TABLE`, `ROOM_MEMBERS_TABLE`, and `CALLBACK_ENDPOINT` are set.
- `CALLBACK_ENDPOINT` is the stage's **exact HTTPS Management API endpoint**, e.g., `https://a1b2c3d4.execute-api.ap-southeast-1.amazonaws.com/prod`, not `wss://...`.
- The IAM execution role grants DynamoDB permissions for the target tables/keys and `execute-api:ManageConnections` `POST` on the target API/stage.
- The deployment package bundles AWS SDK v3 dependencies (do not assume every SDK version is preinstalled in the runtime).
- DynamoDB `Connections` uses partition key `connectionId` (String). `RoomMembers` uses partition key `roomId` and sort key `connectionId` (String). When TTL is enabled, both tables use attribute `expiresAt`.

### 10.1. Illustrative Lambda Handler

~~~javascript
// Illustrative Node.js 20+ handler; supports only a single "lobby" room.
// Install dependencies: @aws-sdk/client-dynamodb,
// @aws-sdk/lib-dynamodb, @aws-sdk/client-apigatewaymanagementapi.
const { DynamoDBClient } = require("@aws-sdk/client-dynamodb");
const {
  DynamoDBDocumentClient,
  PutCommand, GetCommand, DeleteCommand, QueryCommand
} = require("@aws-sdk/lib-dynamodb");
const {
  ApiGatewayManagementApiClient,
  PostToConnectionCommand
} = require("@aws-sdk/client-apigatewaymanagementapi");

const db = DynamoDBDocumentClient.from(new DynamoDBClient({}));
const management = new ApiGatewayManagementApiClient({
  endpoint: process.env.CALLBACK_ENDPOINT
});
const CONNECTIONS = process.env.CONNECTIONS_TABLE;
const MEMBERS = process.env.ROOM_MEMBERS_TABLE;
const ROOM = "lobby";

const ok = () => ({ statusCode: 200 });
const now = () => Math.floor(Date.now() / 1000);

async function removeConnection(connectionId) {
  // Valid only because this example has a single "lobby" room.
  await db.send(new DeleteCommand({
    TableName: MEMBERS, Key: { roomId: ROOM, connectionId }
  }));
  await db.send(new DeleteCommand({
    TableName: CONNECTIONS, Key: { connectionId }
  }));
}

async function push(connectionId, message) {
  try {
    await management.send(new PostToConnectionCommand({
      ConnectionId: connectionId,
      Data: Buffer.from(JSON.stringify(message), "utf8")
    }));
    return true;
  } catch (error) {
    if (error.name === "GoneException"
        || error.$metadata?.httpStatusCode === 410) {
      await removeConnection(connectionId);
      return false;
    }
    // 403/429/5xx are not "gone": log and retry per policy.
    throw error;
  }
}

exports.handler = async (event) => {
  const routeKey = event.requestContext?.routeKey;
  const connectionId = event.requestContext?.connectionId;
  if (!connectionId) return { statusCode: 400 };

  if (routeKey === "$connect") {
    // principalId must come from a trusted authorizer, NEVER from body/query.
    const userId = event.requestContext?.authorizer?.principalId;
    if (!userId) return { statusCode: 401 };

    await db.send(new PutCommand({
      TableName: CONNECTIONS,
      Item: {
        connectionId,
        userId,
        connectedAt: now(),
        expiresAt: now() + 3 * 3600
      },
      ConditionExpression: "attribute_not_exists(connectionId)"
    }));
    return ok(); // Handshake not complete yet: do not push here.
  }

  if (routeKey === "$disconnect") {
    await removeConnection(connectionId);
    return ok(); // Disconnect is best effort; additional cleanup is still needed.
  }

  // Strongly consistent read after $connect on base table; never trust client userId.
  const state = await db.send(new GetCommand({
    TableName: CONNECTIONS,
    Key: { connectionId },
    ConsistentRead: true
  }));
  if (!state.Item || state.Item.expiresAt <= now()) {
    await push(connectionId, { type: "error", code: "SESSION_EXPIRED" });
    return ok();
  }

  let body;
  try {
    body = JSON.parse(event.body || "{}");
  } catch {
    await push(connectionId, { type: "error", code: "INVALID_JSON" });
    return ok();
  }

  if (routeKey === "join") {
    // Demo permits lobby only. Production: check current room ACLs.
    if (body.roomId !== ROOM) {
      await push(connectionId, { type: "error", code: "ROOM_DENIED" });
      return ok();
    }
    await db.send(new PutCommand({
      TableName: MEMBERS,
      Item: {
        roomId: ROOM,
        connectionId,
        userId: state.Item.userId,
        joinedAt: now(),
        expiresAt: state.Item.expiresAt
      }
    }));
    await push(connectionId, { type: "joined", roomId: ROOM });
    return ok();
  }

  if (routeKey === "sendMessage") {
    const text = body.text;
    if (body.roomId !== ROOM
        || typeof text !== "string"
        || text.length < 1 || text.length > 500) {
      await push(connectionId, { type: "error", code: "INVALID_MESSAGE" });
      return ok();
    }

    const membership = await db.send(new GetCommand({
      TableName: MEMBERS,
      Key: { roomId: ROOM, connectionId },
      ConsistentRead: true
    }));
    if (!membership.Item || membership.Item.expiresAt <= now()) {
      await push(connectionId, { type: "error", code: "NOT_A_MEMBER" });
      return ok();
    }

    const outgoing = {
      type: "message.created",
      roomId: ROOM,
      senderId: state.Item.userId,
      text
    };
    let cursor;
    do {
      const page = await db.send(new QueryCommand({
        TableName: MEMBERS,
        KeyConditionExpression: "roomId = :room",
        ExpressionAttributeValues: { ":room": ROOM },
        ExclusiveStartKey: cursor
      }));

      // Suitable only for small lab rooms.
      // Production: offload fan-out to SQS/workers with bounded concurrency.
      for (const member of page.Items || []) {
        if (member.expiresAt > now()) {
          await push(member.connectionId, outgoing);
        }
      }
      cursor = page.LastEvaluatedKey;
    } while (cursor);

    return ok();
  }

  await push(connectionId, {
    type: "error", code: "UNKNOWN_ACTION", routeKey
  });
  return ok();
};
~~~

### 10.2. Reading the Example Correctly

| Code section | What it demonstrates |
| --- | --- |
| `$connect` reads `authorizer.principalId` | Never trust a client-supplied `userId` |
| `PutCommand` on `Connections` | Records session by `connectionId` with an expiration for cleanup |
| `join` checks room and writes `RoomMembers` | Registry controls who receives room messages |
| `sendMessage` checks membership before publishing | Sending messages requires authorization, not just JSON validation |
| `QueryCommand` pagination on `roomId` | A room can span more than one DynamoDB query page |
| `PostToConnectionCommand` | Pushes a message to a specific connection via Management API |
| `GoneException` | Cleans up stale closed connections |
| `$disconnect` | Best-effort cleanup; never treat as a guaranteed callback |

**Intentional limitations of this example:**

1. Only **one `lobby` room** is supported; multi-room production systems need a GSI or reverse-lookup table to clean up all rooms on disconnect.
2. Fan-out runs **sequentially inside the route Lambda**, so large rooms will time out and increase costs. Production apps enqueue events to SQS/streams and fan out via workers with bounded concurrency and backoff.
3. `sendMessage` **does not persist messages**, allocate `eventId`, deduplicate `requestId`, or provide an offline inbox. Never use it as-is for critical transactional notifications.
4. Receiving `200` from `push` **does not prove the client processed the message**.
5. Text validation checks JavaScript `.length` (UTF-16 code units), **not UTF-8 byte size**, schemas, rate limits, or harmful content per production standards.
6. `removeConnection` deletes from two tables **non-transactionally**. If one fails, sweepers/TTL must clean up the remainder.
7. Multi-tenant privacy/ACLs must be added whenever rooms are non-public, grounded in server-side identity and trusted datastores.

### 10.3. Decoupling Fan-Out from the Route Integration

When rooms grow to thousands of subscribers, the API route should not synchronously loop over every recipient:

~~~mermaid
flowchart LR
    SEND["Client sends sendMessage"] --> GW["API Gateway WebSocket"]
    GW --> HANDLER["Lambda Validate + Persist"]
    HANDLER --> DB["DynamoDB: Messages/Idempotency"]
    HANDLER --> QUEUE["SQS / EventBridge / stream"]
    QUEUE --> WORKER["Fan-out workers\nbounded concurrency"]
    WORKER --> REG["DynamoDB: memberships"]
    WORKER --> MGMT["Management API @connections"]
    MGMT --> CLIENTS["Connected clients"]
    WORKER --> DLQ["DLQ / failed delivery tracking"]
~~~

In this pattern, the route integration quickly confirms **acceptance** per application protocol (e.g., an `accepted` ack) once persistence/enqueueing succeeds. Delivery happens asynchronously; monitor **queue age, worker failures, and fan-out throughput** against real-time SLOs.

## 11. JavaScript Client: Sending Actions and Handling Reconnects

Browser example:

~~~javascript
// Assumes $connect handshake has valid authentication configured.
// Never embed long-lived tokens in the URL in real applications.
const url = "wss://a1b2c3d4.execute-api.ap-southeast-1.amazonaws.com/prod";
let socket;
let retry = 0;
let reconnectTimer;

function openSocket() {
  socket = new WebSocket(url);

  socket.addEventListener("open", () => {
    retry = 0;
    socket.send(JSON.stringify({
      action: "join",
      roomId: "lobby"
    }));
  });

  socket.addEventListener("message", (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === "message.created") {
        console.log("Message:", data.senderId, data.text);
      } else {
        console.log("Server:", data);
      }
    } catch {
      console.warn("Unable to parse server message");
    }
  });

  socket.addEventListener("close", () => {
    // Exponential backoff + jitter, capped at 30 seconds.
    const base = Math.min(30000, 1000 * Math.pow(2, retry++));
    const jitter = Math.random() * 1000;
    reconnectTimer = setTimeout(openSocket, base + jitter);
  });

  socket.addEventListener("error", () => {
    // Browsers do not expose detailed handshake failure reasons here.
    console.warn("WebSocket error encountered; waiting for close/reconnect");
  });
}

function sendText(text) {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    throw new Error("Not connected; queue or retry at the application layer");
  }
  socket.send(JSON.stringify({
    action: "sendMessage",
    roomId: "lobby",
    requestId: crypto.randomUUID(),
    text
  }));
}

openSocket();
~~~

**Do not copy this snippet directly to production:** it does not handle auth ticket/cookie refresh, page unload, offline state, duplicate messages, stopping retries on permanent API shutdown, or **reconnect storms** after regional disruptions. Stop reconnecting on logout, wait for network online events, and cap total retry attempts/duration.

### 11.1. Why Does Reconnecting Assign a New Connection ID?

Each new WebSocket connection is a brand-new session in API Gateway with a **new `connectionId`**. Consequently, the client must:

1. Re-authenticate during the handshake.
2. Re-send `join`/`subscribe` after `open`.
3. Send a `lastSeenEventId` or `lastSeenSequence` cursor if replay is supported.
4. Handle duplicate deliveries if a message was processed right before the previous socket dropped.

Never store `connectionId` as a permanent **user identifier**. Use the stable `userId` from your auth system, treating `connectionId` as ephemeral transport session state.

### 11.2. Heartbeats and Presence

For many clients, you can add a `ping` route accepting:

~~~json
{
  "action": "ping",
  "clientTime": "2026-11-20T03:00:00Z"
}
~~~

The backend updates `lastSeenAt` or replies with `pong`. However:

- A recent `online` timestamp is only an **estimate**, not a guarantee the client can still receive pushes.
- Do not spam heartbeats every second; account for connection count, message billing, and cost.
- Browsers and mobile OSes throttle background tabs, sleep devices, or lose cellular signal.
- `$disconnect` can arrive late or never; combine TTLs, heartbeats, and `GoneException` cleanup.

## 12. Configuring WebSocket APIs with CloudFormation

The snippet below is an **illustrative fragment** showing API Gateway WebSocket and routing structure, **not a complete deployable stack**. Lambda/authorizer IAM roles, authorizer resources, invoke permissions, logging, stages, custom-domain mappings, and DynamoDB tables must all be declared in a real template.

~~~yaml
Resources:
  ChatWebSocketApi:
    Type: AWS::ApiGatewayV2::Api
    Properties:
      Name: chat-ws-example
      ProtocolType: WEBSOCKET
      RouteSelectionExpression: "$request.body.action"

  ChatIntegration:
    Type: AWS::ApiGatewayV2::Integration
    Properties:
      ApiId: !Ref ChatWebSocketApi
      IntegrationType: AWS_PROXY
      IntegrationUri: "LAMBDA_INVOKE_ARN_PLACEHOLDER"

  ConnectRoute:
    Type: AWS::ApiGatewayV2::Route
    Properties:
      ApiId: !Ref ChatWebSocketApi
      RouteKey: "$connect"
      AuthorizationType: CUSTOM
      AuthorizerId: "AUTHORIZER_ID_PLACEHOLDER"
      Target: !Join ["", ["integrations/", !Ref ChatIntegration]]

  DisconnectRoute:
    Type: AWS::ApiGatewayV2::Route
    Properties:
      ApiId: !Ref ChatWebSocketApi
      RouteKey: "$disconnect"
      Target: !Join ["", ["integrations/", !Ref ChatIntegration]]

  JoinRoute:
    Type: AWS::ApiGatewayV2::Route
    Properties:
      ApiId: !Ref ChatWebSocketApi
      RouteKey: "join"
      Target: !Join ["", ["integrations/", !Ref ChatIntegration]]

  MessageRoute:
    Type: AWS::ApiGatewayV2::Route
    Properties:
      ApiId: !Ref ChatWebSocketApi
      RouteKey: "sendMessage"
      Target: !Join ["", ["integrations/", !Ref ChatIntegration]]

  DefaultRoute:
    Type: AWS::ApiGatewayV2::Route
    Properties:
      ApiId: !Ref ChatWebSocketApi
      RouteKey: "$default"
      Target: !Join ["", ["integrations/", !Ref ChatIntegration]]

  ProdStage:
    Type: AWS::ApiGatewayV2::Stage
    Properties:
      ApiId: !Ref ChatWebSocketApi
      StageName: prod
      AutoDeploy: true
~~~

**To turn this into a real stack:**

- Replace `LAMBDA_INVOKE_ARN_PLACEHOLDER` with a valid `AWS_PROXY` API Gateway Lambda integration URI for your Region, account, and function.
- Define an `AWS::ApiGatewayV2::Authorizer` for the WebSocket API and reference the real `AuthorizerId` on `$connect`, along with identity sources and invoke permissions.
- Add `AWS::Lambda::Permission` allowing API Gateway to invoke the route Lambda with a narrowly scoped source ARN.
- Create a Lambda execution role granting DynamoDB, CloudWatch Logs, and `execute-api:ManageConnections` scoped to the created API and stage.
- Provision DynamoDB tables with TTL settings, CloudWatch Log Groups, stage logging, and alarms.
- With `AutoDeploy: true`, route/integration edits deploy immediately to the stage; production stacks need proper review, canary, and rollback controls.
- Configure custom domains, Route 53 records, and certificates if used, ensuring the callback endpoint reflects the active API mapping.

**Do not deploy this fragment verbatim**: placeholders are unresolved, Lambda/authorizer resources are absent, and required permissions are omitted. Use it to visualize the **API → Integration → Routes → Stage** structure.

## 13. Inspecting Resources with AWS CLI (Read-Only)

These commands make no modifications. You need read-only permissions on API Gateway API IDs, stages, routes, authorizers, and integrations in the target Region.

### 13.1. List WebSocket APIs

~~~bash
aws apigatewayv2 get-apis \
  --region ap-southeast-1 \
  --query "Items[?ProtocolType=='WEBSOCKET'].{Name:Name,Id:ApiId,Selection:RouteSelectionExpression,Endpoint:ApiEndpoint}" \
  --output table
~~~

Inspect `RouteSelectionExpression` against your message contract rather than assuming every API uses `$request.body.action`.

### 13.2. Inspect Routes and Integrations

~~~bash
aws apigatewayv2 get-routes \
  --region ap-southeast-1 \
  --api-id a1b2c3d4 \
  --query "Items[].{Key:RouteKey,Target:Target,Auth:AuthorizationType,Authorizer:AuthorizerId}" \
  --output table

aws apigatewayv2 get-integrations \
  --region ap-southeast-1 \
  --api-id a1b2c3d4 \
  --query "Items[].{Id:IntegrationId,Type:IntegrationType,Uri:IntegrationUri,Timeout:TimeoutInMillis}" \
  --output table
~~~

If a route is named `join` but the client sends `{"action":"enterRoom"}`, it will miss `join` and fall into `$default`. Verify `RouteKey`, route selection expressions, and integration targets before blaming DynamoDB.

### 13.3. Inspect Authorizers and Stages

~~~bash
aws apigatewayv2 get-authorizers \
  --region ap-southeast-1 \
  --api-id a1b2c3d4 \
  --output json

aws apigatewayv2 get-stages \
  --region ap-southeast-1 \
  --api-id a1b2c3d4 \
  --query "Items[].{Name:StageName,AutoDeploy:AutoDeploy,AccessLog:AccessLogSettings}" \
  --output json
~~~

`get-authorizers` displays authorizer settings, not secrets or whether a specific client token is valid. `get-stages` confirms clients are connecting to the same stage you are inspecting.

### 13.4. Inspect Metadata of an Active Connection

~~~bash
aws apigatewaymanagementapi get-connection \
  --region ap-southeast-1 \
  --endpoint-url https://a1b2c3d4.execute-api.ap-southeast-1.amazonaws.com/prod \
  --connection-id "EXAMPLE_CONNECTION_ID"
~~~

This is a **read-only `GET` call** to the Management API requiring `execute-api:ManageConnections` permission for `GET`. A **`410 Gone`** response means the connection no longer exists (or is not ready); **`403`** points to IAM/ARN or endpoint URL mismatches. Never look up arbitrary production user connection IDs without authorization.

### 13.5. Inspect DynamoDB Schemas Without Reading Customer Data

~~~bash
aws dynamodb describe-table \
  --region ap-southeast-1 \
  --table-name Connections

aws dynamodb describe-time-to-live \
  --region ap-southeast-1 \
  --table-name Connections

aws dynamodb describe-table \
  --region ap-southeast-1 \
  --table-name RoomMembers
~~~

Verify the real key schema and TTL attribute. Never assume `RoomMembers` items automatically vanish when `Connections` items expire—the two tables are independent.

## 14. Observability: Metrics, Logs, and Tracing

Real-time systems must separate **connection health**, **message delivery**, **backend correctness**, and **cost**.

| Layer | What to measure | Diagnostic questions |
| --- | --- | --- |
| **API Gateway** | Connect attempts/counts, message counts, API errors, integration latency, throttling per supported metrics | Are clients able to complete handshakes and route messages? |
| **Lambda integrations** | Invocations, errors, duration, concurrency, throttles | Are route handlers running and completing cleanly? |
| **DynamoDB** | RCU/WCU, throttled requests, Query latency, hot partitions | Is a large room's partition key throttling? |
| **Management API** | Successful `POST`s, `403`/`410`/`429`/`5xx`, callback latency | Are there IAM errors, stale connections, or callback throttles? |
| **SQS / workers** | Queue depth, oldest message age, DLQs, delivery retries | Is fan-out keeping pace with publish rates? |
| **Client** | Reconnects, time-to-first-message, `lastSeen` sequence, app ack latency | Are users actually receiving events? |
| **Cost** | Connection minutes, message counts/sizes, Lambda/DynamoDB/Logs/network | Is real-time traffic staying within budget? |

**Log `connectionId`, anonymized/protected `userId`, `requestId`, and `eventId`** to trace end-to-end flows. Never log tokens, passwords, full query URLs containing credentials, or sensitive message bodies outside approved security policies.

### 14.1. Access Logs and Execution Logs

API Gateway WebSocket APIs support stage logging and metrics per account configuration:

- Grant API Gateway permission to write to CloudWatch Logs per AWS documentation.
- Configure an **access log format** including request ID, `routeKey`, `connectionId`, status, and integration status where supported.
- Enable execution logging intentionally, and **never log payloads containing sensitive data** unless explicitly permitted.
- Set retention policies and read permissions, filtering out noisy `ping`/`typing` logs.

Never treat a `200` on `$connect` as proof a client will still be online an hour later; connections have finite lifetimes and drop unpredictably.

### 14.2. Defining Practical SLOs

Example chat application SLOs:

~~~text
99% of messages are accepted and durably persisted by the server
within 500 ms when the backend is healthy.

99% of messages are delivered to currently active connections
within 3 seconds, excluding offline or disconnected clients.

Every event carries an eventId, and clients can replay
unacknowledged events upon reconnect within the retention window.
~~~

These numbers are **hypothetical targets**. Define clearly whether "delivered" means Gateway accepted the `POST`, the WebSocket client received bytes, or the client **acknowledged processing**. You cannot measure SLOs accurately if those three definitions are conflated.

## 15. Cost, Quotas, and Capacity Planning

### 15.1. Primary Cost Drivers

| Component | Costs to calculate |
| --- | --- |
| **API Gateway WebSocket** | Sent/received message counts, message size billing increments, and **connection minutes** |
| **Lambda** | Invocations, duration, memory/concurrency across both route handlers and fan-out workers |
| **DynamoDB** | On-demand request units or provisioned capacity, storage, GSIs, streams, backups |
| **SQS / EventBridge** | Publish/consume requests, retries, DLQs, and throughput volume |
| **CloudWatch** | Log ingestion, storage, metrics, alarms |
| **Networking / other** | Data transfer out, KMS, VPC endpoints / NAT Gateways if required by architecture |

Suppose **10,000 connections stay open an average of 30 minutes/day**:

~~~text
Connection-minutes/day = 10,000 × 30 = 300,000
Connection-minutes/30 days = 9,000,000
~~~

That covers only connection duration—**not total spend**. Heartbeat and typing messages also multiply message counts rapidly: 10,000 clients × 1 heartbeat/minute × 30 minutes = **300,000 heartbeat messages/day**, before counting `pong` callbacks or business traffic.

For fan-out:

~~~text
A room has 1,000 connected recipients.
One event is pushed to all recipients.
→ Generates roughly 1,000 outgoing messages
  (excluding retries, errors, and multi-frame messages).
~~~

One inbound event does not equal one billable message. Build a **fan-out multiplier** dashboard and per-user rate limits so one noisy user sending hundreds of messages per minute does not explode costs.

### 15.2. Technical Quotas to Know

Per API Gateway WebSocket quotas documentation, common limits include:

- Connection idle timeout around **10 minutes**; maximum connection lifetime **2 hours**.
- Maximum message size **128 KiB**; maximum frame size **32 KiB**.
- Account/Region quotas on new connections/second, callback throughput, route integration timeouts, and throttling; defaults can change and some quotas are adjustable.
- WebSocket API is not intended for streaming huge binary payloads or large files like a self-managed WebSocket server.

**Never hardcode these quota figures as a permanent SLA.** For production, check current published quotas, Service Quotas, expected peak load, target AWS Region, and how API Gateway meters message size increments. Use **chunking or S3 transfers** for large payloads.

### 15.3. Reconnect Storms and Hot Partitions

If 50,000 clients disconnect simultaneously and reconnect at once:

1. `$connect` handshakes, authorizer calls, and Lambda concurrency spike sharply.
2. DynamoDB registry writes surge.
3. Clients immediately send `join` and fire membership queries together.
4. Token validation, databases, and downstream services suffer abnormal load.

Mitigations: exponential backoff **with jitter**, admission control/throttling, DynamoDB capacity planning, safe token caching, retry budgets, and graceful UX fallbacks. For huge rooms, a single partition key `roomId=lobby` can become a **hot partition**; consider **sharding room memberships** and partitioning worker fan-out instead of simply increasing Lambda memory.

## 16. Data Security and Recipient Authorization

### 16.1. Never Rely on `connectionId` Alone

A `connectionId` is only a callback address—**not proof that the holder may see every message**. Before pushing sensitive payloads:

- Resolve which verified user owns the connection from server-side state.
- Confirm the user currently holds permission for the target resource, topic, or room.
- Never trust a room ID or recipient list supplied directly in a client payload without validation.
- When a user logs out or loses permissions, remove memberships and close active connections.
- Isolate environments, stages, accounts, and IAM roles; a role permitted `ManageConnections` on one API should not control others.

### 16.2. Protecting Tenants and Chat Rooms

In SaaS systems, do not key solely on `roomId` if two tenants could pick the same room name. Use composite keys such as:

~~~text
PK = TENANT#tenant-17#ROOM#room-123
SK = CONN#connection-ABC
~~~

Always read the tenant ID from a **trusted authorization context**. Never treat a client-supplied `tenantId` as proof of access. For tenant-scoped fan-out, enforce data-layer condition keys/policies and auditable logging.

### 16.3. Protecting Message Payloads

- Enforce size limits, schema formats, character validation, and per-user/IP/connection rate limits.
- Prevent message payloads from driving arbitrary backend commands, IAM actions, or unvalidated DynamoDB keys.
- Encrypt data at rest and manage KMS key policies where required.
- Avoid broadcasting secrets into public rooms.
- Define message retention/deletion rules aligned with privacy requirements.
- Guard against replay attacks and cross-site WebSocket hijacking (CSRF-equivalent) if handshakes rely on cookies: validate `Origin` and session bindings strictly.

**WSS uses TLS to encrypt client ↔ Gateway traffic in transit**, but does not replace IAM, backend authorization, or encryption at rest in DynamoDB/S3.

## 17. Common Troubleshooting Table

| Symptom | Likely cause | Priority checks |
| --- | --- | --- |
| **Browser fails to open WebSocket** | Wrong `wss://`/stage URL, TLS/custom domain issue, `$connect` auth denied | Browser console/network, stage, `$connect` authorizer logs |
| **Handshake returns `403`** | Invalid IAM SigV4, Lambda authorizer Deny, or resource policy block | Authorizer, `$connect` integration, API permissions |
| **Client reaches `open`, but actions get no reply** | Missing custom route, wrong route selection expression, or one-way route response | `get-routes`, `$default` logs, verify `postToConnection` calls |
| **Backend returns `200`, client sees no body** | Missing route response / integration response configuration | Check two-way route response or push via Management API |
| **`postToConnection` returns `403`** | Lambda role lacks `ManageConnections`, wrong ARN, or wrong endpoint/stage | IAM policy, resource ARN, callback endpoint URL |
| **`postToConnection` returns `410`** | Client closed, stale ID, or handshake incomplete | Clean up connection; deliver on reconnect if required |
| **Frequent `429` while publishing** | Unbounded fan-out exceeding message/callback throttles | SQS workers, concurrency caps, retry/backoff |
| **Connections close after idle periods** | Idle timeout or client network drop | Application heartbeat, reconnect, resume |
| **Connections drop every couple of hours** | Gateway maximum connection duration | Planned reconnect and resubscribe |
| **User misses messages after reconnecting** | No offline persistence/replay or forgot to re-join room | Message persistence, cursors, acks, subscriptions |
| **Rooms accumulate dead `connectionId`s** | `$disconnect` is best effort, slow TTL, `410` not cleaned | Sweeper/TTL, `GoneException` cleanup on membership table |
| **Same message appears twice** | Retries, Lambda async redelivery, or client reconnect/replay | Idempotency via `requestId`/`eventId` |
| **Two users receive messages out of order** | Concurrent routes/Lambdas/workers processing simultaneously | Per-room sequence numbers in datastore, client reordering |
| **DynamoDB throttling on a single-key room** | Hot partition on `roomId` during fan-out queries | Key sharding, partitioned workers, capacity scaling |
| **Lambda times out on `sendMessage`** | Synchronous fan-out to too many connections or slow DB/API | Persist + enqueue to async workers with bounded concurrency |
| **Revoked user keeps receiving messages** | Existing socket still open without revalidation/revocation | Remove memberships, check permissions on publish, delete connection |

### 17.1. Four-Step Diagnostic Flow

1. **Handshake:** Inspect `$connect` events, authorizer results, and whether the HTTP upgrade succeeded.
2. **Routing:** Is the message body valid JSON with the right `action`? Did `$default` fire? Was the integration invoked?
3. **State:** Does the registry hold a valid `connectionId` and membership, and what do TTL/authorization checks say?
4. **Callback:** Was `postToConnection` called against the right endpoint and stage, what HTTP status did it return, and did the client ack?

Never "test-fix" issues by removing authorizers or granting `AdministratorAccess` to Lambda—that hides IAM/stage mistakes and opens severe security holes.

## 18. Lab Testing Guidelines

Lab goal: two **authenticated** clients join `lobby`, exchange messages, close one connection, and observe cleanup and reconnect behavior.

### 18.1. Preparation

1. Provision an API Gateway **WebSocket API** in a lab account with route selection expression `$request.body.action`.
2. Create `$connect`, `$disconnect`, `$default`, `join`, `sendMessage`, a `$connect` authorizer, and Lambda integrations.
3. Create DynamoDB `Connections` and `RoomMembers` tables with TTL on `expiresAt` if enabled.
4. Assign least-privilege IAM roles and configure the stage's exact `CALLBACK_ENDPOINT`.
5. Enable CloudWatch Logs/metrics with short retention; keep real credentials out of screenshots.
6. Prepare two authorized browsers or WebSocket clients with valid handshake credentials.

### 18.2. Test Steps

| Step | Action | Expected outcome |
| --- | --- | --- |
| 1 | Clients A and B connect to `wss://.../lab` | Both receive `open`; `$connect` records two `connectionId`s |
| 2 | A and B send `{"action":"join","roomId":"lobby"}` | Both memberships saved; both receive `joined` callback |
| 3 | A sends `sendMessage` | Both A and B receive the message on open sockets |
| 4 | Send `{"action":"unknown"}` | `$default` handles it and pushes a protocol error |
| 5 | B calls `close()` | `$disconnect` may run; backend best-effort cleans registry |
| 6 | A sends another message after B closes | B receives nothing; any stale B callback returns `410` and cleans up |
| 7 | B reconnects and re-joins | B gets a new `connectionId` and resubscribes |
| 8 | Inspect CloudWatch and DynamoDB | Logs and connection/cleanup state appear without sensitive tokens |

Never run heavy load tests or intentionally drop production connections on live stages. Labs create billable resources: clean up the **WebSocket API, Lambdas, DynamoDB tables, log groups, and supporting resources** per policy without deleting real data.

### 18.3. Intentional Failure Testing

- Send invalid JSON to verify `$default` and error payloads.
- Send `join` for an unauthorized room to confirm the server refuses membership.
- Trigger a callback against a disconnected ID in lab to verify `410 Gone` cleanup.
- Burst messages from a client to test connection throttling and application rate limiting.
- Simulate network drops and measure backoff/reconnect timing, duplicate/lost messages, and resume latency.
- Test with a revoked token to ensure `$connect` rejects it and active sockets follow your revocation policy.

## 19. Architecture Case Study: Order Status Notifications

### 19.1. Requirements

An e-commerce application tracks orders for shoppers. When the backend changes `orderStatus` to `SHIPPED`, clients should receive a real-time notification. If the client is offline, opening the app later must still show the accurate current order status.

### 19.2. Proposed Architecture

~~~mermaid
flowchart LR
    ORDER["Order Service\nRDS/DynamoDB"] -->|"Persist state + outbox/event"| BUS["EventBridge / SQS"]
    BUS --> WORK["Notification Worker Lambda"]
    WORK --> LOOK["Connection Registry\nby userId"]
    WORK -->|"POST @connections"| GW["API Gateway WebSocket"]
    GW --> CLIENT["Web/mobile client"]
    CLIENT -->|"GET current status"| API["HTTP API"]
    API --> ORDER
~~~

**Core principle:** The **source of truth** is the Order Service/database, not the connection registry. Real-time events make the UI snappy, yet on reconnect clients still query `GET /orders/{id}` (or a sync endpoint) to reconcile the latest state.

### 19.3. Permissions and Delivery Flow

1. `$connect` authorizer verifies the user ID.
2. Registry maps `userId` to multiple `connectionId`s (tabs/devices).
3. Worker consumes order events and checks the **authorized owner** in server-side order data.
4. Worker fans out `order.updated` to all active connections for that user.
5. Client can ack `eventId`, then query the source-of-truth API to ensure UI state is consistent.
6. On `410 Gone` or offline clients, **order state is never lost**; events can be replayed if needed, and the client fetches fresh status upon reopening.

**Do not push payment details or PII inside WebSocket payloads** when clients only need an ID and status. Keep pushes minimal (`orderId`/`status`) and serve full details over authenticated HTTP APIs.

### 19.4. RTO, RPO, and Availability

If the real-time channel degrades while the HTTP API and database remain healthy, users simply **stop receiving live pushes** temporarily while still viewing current status via polling—a clean **degraded mode**. Multi-Region DynamoDB, SQS replay, cross-Region failover, and backups must be engineered around application RTO/RPO targets rather than assuming WebSockets provide them automatically.

## 20. Practice Exercises

### Exercise 1 — Which Route Runs?

An API uses `$request.body.action` with custom routes `join`, `sendMessage`, and `$default`.

~~~json
{"action":"join","roomId":"lobby"}
~~~

**Hint:** Invokes `join`. Sending `{"action":"deleteEverything"}` without a matching route falls through to `$default`. Backends must still validate schemas and authorization.

### Exercise 2 — Responses Back to the Client

A route Lambda returns `{statusCode:200,body:"done"}`, yet the browser receives no message. Why?

**Hint:** WebSocket integration return values do not automatically push to clients by default. Check route response / integration response setup for two-way communication, or push via `postToConnection`.

### Exercise 3 — `410 Gone`

Inside the `$connect` Lambda, a developer calls `postToConnection` to send a welcome greeting and gets `410`. Moving the greeting to when the client sends `join` succeeds. Explain why.

**Hint:** The handshake is still in progress while the `$connect` integration runs, so the connection is not ready in the Management API yet. Pushing after the socket reaches `open` and sends its first message avoids this race condition.

### Exercise 4 — Cleaning Up After Network Drops

A client loses network abruptly so `$disconnect` never fires. A day later, `RoomMembers` still contains the old `connectionId`. Propose a cleanup design.

**Hint:** `$disconnect` is best effort; combine per-table TTLs, background sweepers, and cleanup on `410` callback errors. Remember DynamoDB TTL is asynchronous and does not automatically delete items from separate membership tables.

### Exercise 5 — Securing Chat Rooms

An unauthorized client sends `{"action":"join","roomId":"room-private-1"}`. Since the `join` API Gateway route exists, may the server write the membership?

**Hint:** No. Route selection only dispatches to the backend; the backend must check ACLs using the verified `userId`, `roomId`, and tenant before persisting membership.

### Exercise 6 — Counting Messages

A room has 100 online members. Each sends two messages per minute, and the backend broadcasts every message to all members. Roughly how many incoming and outgoing messages occur per minute, ignoring retries?

**Hint:** Incoming = `100 × 2 = 200`. Broadcasting each message to all 100 members produces roughly `200 × 100 = 20,000` outgoing messages. Notice the **fan-out** cost multiplier—it is not 200 outgoing!

### Exercise 7 — Token Expires While Socket Stays Open

A JWT has a 15-minute lifetime, while a WebSocket connection lives longer. After 20 minutes, the user's room access is revoked. Why is authenticating only at `$connect` insufficient?

**Hint:** The socket stays open after the handshake; enforce permission checks per action/room, revalidate auth/sessions periodically, or actively revoke memberships and close connections upon revocation.

### Exercise 8 — Choosing AppSync vs. API Gateway WebSocket

Team A builds a GraphQL app with data-driven subscriptions. Team B uses custom JSON messages (`join`, `typing`, `sendMessage`) with SQS workers pushing updates. Which service should each team evaluate?

**Hint:** Team A should evaluate **AppSync** for its GraphQL/real-time abstractions; Team B should evaluate **API Gateway WebSocket** for direct control over custom routes, registries, callbacks, and fan-out. Both should still compare costs, auth, quotas, and operations.

### Exercise 9 — Preventing Lost Notifications

Order Service emits `SHIPPED`, but all of the user's WebSocket connections are offline. How do you ensure order status is still accurate when the user reopens the app?

**Hint:** Persist authoritative state in the database with an authenticated fetch API. WebSocket is a **fast notification channel**; if guaranteed delivery of events is needed, store events/inboxes with cursors, acks, and replay.

## 21. Production Deployment Checklist

- [ ] API Gateway configured with `ProtocolType=WEBSOCKET`, route selection expression, and stage.
- [ ] Defined `$connect`, `$disconnect`, `$default`, and all required custom routes.
- [ ] Valid `$connect` authentication configured, avoiding token leaks in URLs and enforcing revocation/revalidation policies.
- [ ] Backend checks user/tenant/resource authorization for **every action**, not only at handshake.
- [ ] Lambda IAM role scoped strictly to required DynamoDB tables and `execute-api:ManageConnections` for the exact API/stage/methods without broad wildcards.
- [ ] HTTPS callback endpoint matches the exact stage or custom domain API mapping.
- [ ] Registry/room schema supports multi-device users and multiple rooms, with disconnect/`410` cleanup and TTL/sweepers.
- [ ] Critical messages are persisted with `eventId`/idempotency, client acknowledgements, and reconnect resume logic.
- [ ] Fan-out uses queues, bounded concurrency, retries/backoff, DLQs, and telemetry instead of huge synchronous loops in route Lambdas.
- [ ] Tested message size/frame limits, timeouts, heartbeats/reconnects, and browser auth constraints.
- [ ] API Gateway, Lambda, DynamoDB, and worker metrics, access logs, CloudWatch alarms, and costs are monitored.
- [ ] Payloads and logs are sanitized; WSS, encryption at rest, and tenant-level authorization are enforced.
- [ ] Tested `410 Gone`, `403`, throttling, invalid actions, network drops, reconnect storms, and cold starts.
- [ ] Lab cleanup procedures, isolated staging/production environments, and rollback plans are in place.

## 22. Key Takeaways

**API Gateway WebSocket API** gives you a managed bidirectional endpoint, **not a complete chat server out of the box**. Remember:

1. **`$connect`** authenticates and records connection state before the handshake completes; **`$disconnect`** is *best-effort* cleanup.
2. **Route selection expressions** such as `$request.body.action` dispatch messages to `join`, `sendMessage`, or `$default`.
3. Backends push to clients via the **Management API `@connections`** using **`execute-api:ManageConnections`**; Lambda return codes do not automatically become WebSocket pushes.
4. **Connection registries, room memberships, authorization, offline state, and delivery guarantees** belong to your application—typically backed by DynamoDB and event queues.
5. **`410 Gone`, reconnects, TTLs, heartbeats, throttling, message size caps, and fan-out costs** are normal operational realities that must be designed upfront.

A solid real-time channel does more than minimize latency—it **never corrupts business state when clients go offline, retry, or lose connectivity**. Separate your **source of truth**, **event distribution**, and **WebSocket delivery**, and measure each layer against clear SLOs and budgets.

### Official AWS Documentation

- [API Gateway WebSocket API overview](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-websocket-api-overview.html) — architecture, routing, and WebSocket connections.
- [WebSocket route keys: connect, disconnect, default](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-websocket-api-route-keys-connect-disconnect.html) — connection lifecycle and special routes.
- [WebSocket route selection expressions](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-websocket-api-route-selection-expressions.html) — routing via `$request.body.action`.
- [WebSocket route responses](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-websocket-api-route-response.html) — one-way vs. two-way integration responses.
- [Use the @connections commands in your backend service](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-how-to-call-websocket-api-connections.html) — Post/Get/Delete connections, callback URLs, IAM.
- [Control access to WebSocket APIs](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-websocket-api-control-access.html) — IAM and Lambda authorizers on `$connect`.
- [API Gateway quotas](https://docs.aws.amazon.com/apigateway/latest/developerguide/limits.html) — message/frame limits, connection duration, throughput, and timeouts.
- [Logging and monitoring in API Gateway](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-websocket-api-logging.html) — access and execution logs.
- [DynamoDB Time to Live](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/TTL.html) — TTL and asynchronous item expiration.
- [AWS API Gateway pricing](https://aws.amazon.com/api-gateway/pricing/) — WebSocket connections/messages and billing units.
- [AWS AppSync Developer Guide](https://docs.aws.amazon.com/appsync/latest/devguide/what-is-appsync.html) — alternative GraphQL and real-time patterns.
