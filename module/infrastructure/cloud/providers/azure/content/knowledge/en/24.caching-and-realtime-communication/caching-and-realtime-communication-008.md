# Client Authorization and Connection Group Management

A customer support application needs to push real-time order status updates. Buyers must only see alerts for **orders belonging to their own account**; support agents may join specific rooms assigned to them; supervisors may broadcast notifications to a group of users. If developers validate group names only in browser JavaScript, any user can edit the script to join another group and read unauthorized data.

With **Azure Web PubSub**, the right design separates three decisions:

1. **Who is the client?** The backend authenticates the user and device/session.
2. **What may the client do?** The backend grants minimal scoped permissions when minting the client access URL/token or via service management APIs.
3. **Which groups does the client belong to, and for how long?** The backend evaluates business permissions, orchestrates joining/leaving groups, and handles permission changes across the connection lifecycle.

Example:

```text
Browser (user: buyer-1042)
        |
        | 1. HTTPS /realtime/negotiate + application login token
        v
Application Backend
  - authenticate user
  - check membership / tenant policy
  - grant least-privilege roles only
        |
        | 2. Short-lived signed client access URL
        v
Azure Web PubSub Service
        |
        | 3. WebSocket connects to hub "orders"
        |
        +--> Group "tenant-a.order-1042" (permitted by backend)
        |
        +--X Group "tenant-b.order-9001" (denied)
        |
        v
Receives alerts for order 1042, never receives tenant B data
```

This lesson belongs to the **Caching and Real-time Communication** chapter of the `CLOUD_PROVIDERS_AZURE` module. The module covers the Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID through VNets, compute, storage, and data, while teaching deployment, monitoring, security, and cost control for application architectures. This lesson focuses on **Azure Web PubSub**—where **client roles, group permissions, and connection management** are first-class primitives—while contrasting **Azure SignalR Service** so the two models are never confused. Caches such as Azure Managed Redis/Redis can assist with short-lived metadata/presence lookups, yet **must never serve as the sole authorization authority**.

> Primary scope: Azure Web PubSub and the WebSocket client protocol. APIs, operation names, authentication methods, quotas, and features such as Private Endpoints vary by SDK, tier, region, and service version. Examples are explicitly labeled as runnable code or pseudocode. Never place real access tokens, connection strings, keys, or customer data in training code or logs.

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish **Azure Web PubSub resource**, **hub**, **connection**, **user**, **group**, and **role**.
2. Describe the flow: application authentication → backend issues client access URL/token → client opens WebSocket.
3. Explain the two core Azure Web PubSub client protocol permission groups: **join/leave group** and **send to group**.
4. Distinguish **client permissions** from **server/data-plane management permissions**.
5. Design multi-tenant room authorization following **least privilege** and server-side verification.
6. Manage joining/leaving groups from the backend or via the client protocol when granted scoped roles.
7. Handle multiple tabs/devices for the same user, reconnects, token expiry, and disconnect events.
8. Publish messages to targeted groups without accidentally broadcasting to the entire hub.
9. Manage permission changes and revoke active access when a user is removed from a room or tenant.
10. Handle **presence, group membership, and message delivery** with real-time semantics rather than assuming queue durability.
11. Contrast Azure Web PubSub with **Azure SignalR Service**, especially around group permissions and lifecycles.
12. Set up HTTPS/TLS, Microsoft Entra/managed identity for backends, metrics, and security runbooks.
13. Complete the hands-on exercise and test both allowed and denied paths.

## 2. Service boundaries: Web PubSub, SignalR, and caching

All three technologies can appear side by side in a real-time application, yet serve distinct roles:

| Technology | Primary purpose | Key concepts |
|---|---|---|
| **Azure Web PubSub** | Managed WebSocket/PubSub service for real-time apps with client protocol and group routing | Hub, user ID, connection ID, group, client roles, server-side APIs |
| **Azure SignalR Service** | Real-time scale-out for apps using ASP.NET Core SignalR and the SignalR model | SignalR Hub, Hub methods, `Context.User`, Groups, connection lifecycle |
| **Azure Managed Redis / Redis cache** | Fast in-memory data/cache access; can hold select short-lived states | Cache keys, TTL, invalidation; never replaces backend authorization |

A **Web PubSub group** is not a **SignalR group** despite sharing the word "group". Client-side roles like `webpubsub.joinLeaveGroup...` belong to the **Azure Web PubSub client protocol** and do not apply automatically to ASP.NET Core SignalR.

Likewise, Redis Pub/Sub or Redis caches are not Web PubSub WebSocket groups. Cached data can accelerate checks, yet deciding who enters a room must rest on verified identity and an authoritative permission source.

## 3. Core Azure Web PubSub concepts

| Concept | Explanation | Example |
|---|---|---|
| **Resource / service** | Azure resource managing WebSocket connections, endpoints, hubs, and capacity | `wps-customer-prod` |
| **Hub** | Logical namespace organizing connections, groups, and event handlers | `orders` |
| **Connection ID** | Identifier for one specific WebSocket connection managed by the service | `conn-8f2...` |
| **User ID** | Logical user identifier bound to connections via authentication/negotiate | `buyer-1042` |
| **Group** | Set of connections in a hub receiving group-routed broadcasts | `tenant-a.order-1042` |
| **Client role / permission** | Role allowing clients to run group commands in the Web PubSub protocol | `webpubsub.joinLeaveGroup.tenant-a.order-1042` |
| **Client access token / URL** | Short-lived credential letting a client connect to Web PubSub | Signed `wss://...` URL |
| **Server SDK / REST API** | Authoritative backend channel to manage connections/groups and publish messages | Add connection to group, send to group |
| **Event handler** | Callback/upstream endpoint handling connect/user events per config | Verify user on connect or handle client events |

**A group is a connection routing unit**, not an authorization table automatically built from customer records by Web PubSub. Your application must determine valid group memberships.

## 4. How do hub, user, connection, and group differ?

One user can open multiple browser tabs, a phone, and a laptop:

```text
Web PubSub resource: wps-customer-prod
└── Hub: orders
    ├── User: buyer-1042
    │   ├── Connection C1 (Chrome tab)
    │   ├── Connection C2 (mobile phone)
    │   └── Connection C3 (another tab)
    │
    ├── Group tenant-a.order-1042
    │   ├── Connection C1
    │   └── Connection C2
    │
    └── Group tenant-a.support-team
        └── Connection S1 (support agent)
```

Key distinctions:

- A **User ID** can map to **multiple connection IDs**.
- A **Connection ID** exists only for one specific connection; never use it as a persistent identity.
- **Group membership** tracks connections, not an automatic guarantee that "every device of a user always joins the same group".
- One connection can join **multiple groups** when permitted and within service limits.
- Identical group names in **two different hubs** are completely separate channels.
- When a connection drops and reconnects, its ID changes; the app must **restore valid memberships**.

To notify "only `buyer-1042`", choose user-targeting or group-targeting per business rules; never assume a user-named group automatically captures all current and future connections.

## 5. Multi-tenant scenario: who can enter which room?

Suppose a system serves two tenants:

```text
Tenant A
  ├── Buyer Alice: views order-1042
  ├── Buyer Bob: views order-1043
  └── Support A: views assigned orders

Tenant B
  └── Buyer Carol: views order-9001
```

Intended policy:

| Subject | Allowed group | Denied groups |
|---|---|---|
| Alice (tenant A, order 1042) | `tenant-a.order-1042` | `tenant-a.order-1043` unless authorized; all tenant B groups |
| Bob (tenant A, order 1043) | `tenant-a.order-1043` | Alice's groups unless shared |
| Support A | Actively assigned rooms | Tenant B rooms unless explicitly authorized cross-tenant |
| Carol (tenant B) | `tenant-b.order-9001` | All tenant A rooms |
| Backend notification publisher | Targets exact intended room | Never broadcasts hub-wide if content belongs to one room |

Never grant room access like this:

```text
Client sends roomId = "tenant-b.order-9001"
→ Backend blindly trusts roomId
→ Client joins the group
```

Do this instead:

```text
Client requests roomId
→ Backend authenticates user
→ Queries permissions on tenant/order records
→ If valid, backend derives canonical group name
→ Grants scoped role / joins group
→ Otherwise returns 403, grants no permissions
```

## 6. Authentication vs authorization vs membership

Three distinct steps often conflated:

**Authentication — who are you?**

- Backend verifies bearer tokens, sessions, or cookies via Microsoft Entra ID or the app's identity provider.
- Produces a **verified user ID** for the Web PubSub connection.
- Never trust an arbitrary client-supplied user ID field.

**Authorization — what are you allowed to do?**

- Backend verifies the user belongs to the right tenant, may access the room/order, and may send or only receive.
- Grants scoped Web PubSub roles or manages membership via server SDK.
- Updates access whenever assignments, roles, or order states change.

**Membership — which rooms are you currently in?**

- Backend or client executes the join via permitted flows.
- The service routes group messages to active member connections.
- Membership follows the connection lifecycle and server controls.

**Being signed in** does not mean **permission to join any group**. **Being in a group** does not mean **permission to send to that group**. **Having send permission** does not authorize mutating business records in SQL/Cosmos DB.

## 7. Control plane, server data plane, and client protocol

Separate privileges by execution boundary:

```text
Azure Administrator (control plane)
  - creates Web PubSub resource
  - configures networking, hub/event handlers, roles
                |
                v
Application Backend (server data plane)
  - mints client access URLs
  - adds/removes connections/users from groups
  - sends messages to groups/users/connections
  - closes/revokes connections when supported
                |
                v
Browser/Mobile (client protocol)
  - opens WebSocket with issued URL
  - receives messages
  - joins/leaves and sends to groups when granted matching client roles
```

| Privilege | Who needs it | Never grant to |
|---|---|---|
| Azure Resource Manager resource admin | Infra/automation teams via RBAC | Browsers and mobile clients |
| Web PubSub server-side data-plane access | Backend with approved managed/service identity | Untrusted clients |
| Scoped client access URL / roles | Backend-authenticated end users | Unauthenticated users or other tenants |
| Business authorization | Backend APIs and authoritative data tier | Client-side JavaScript alone |

**Never embed Web PubSub connection strings or service access keys in web or mobile apps.** Service keys grant capabilities far exceeding any end client's needs.

## 8. Negotiate flow for issuing connection URLs

Applications typically expose a backend **negotiate** endpoint:

```text
1. Browser -- HTTPS GET /api/realtime/negotiate
   Authorization: Bearer <application access token>
                 |
                 v
2. Backend validates token, tenant, and roles
                 |
                 v
3. Backend mints client access URI:
   - target hub
   - trusted userId
   - minimal roles
   - short expiry
                 |
                 v
4. Backend returns signed URL over HTTPS, no-store
                 |
                 v
5. Browser opens WebSocket (wss://)
                 |
                 v
6. Web PubSub verifies token and establishes connection
```

Security requirements:

1. The negotiate API must **enforce authentication**; never accept `?userId=...` unverified and hand out URLs.
2. Never let clients pick arbitrary roles or scopes.
3. Mint only roles needed for rooms **verified by the backend**.
4. Keep URLs short-lived and treat them as **secrets**.
5. Mark responses containing URLs `no-store` to prevent intermediary caching.
6. Never log full URLs in access logs, frontend analytics, or stack traces.
7. Connect strictly over **WSS/TLS**, never unencrypted WS.
8. Force clients to re-negotiate on reconnect so permissions are re-evaluated.

## 9. Client access URLs/tokens are not admin accounts

A client access URL embeds a signed token binding hub, user, roles, and expiration per service rules. It authorizes **opening a WebSocket** and performing delegated client commands.

Design mistakes:

- Copying User A's token to test as User B.
- Issuing a 24-hour URL when a user could be removed from a room within minutes.
- Setting `userId` to a self-asserted client parameter.
- Sharing one generic token across all customers of a tenant.
- Returning the service connection string instead of a scoped client URL.
- Caching tokens in `localStorage` long-term to "skip negotiate".
- Printing full tokens to logs for debugging.

A leaked token can be replayed by anyone until it expires or is revoked via supported mechanisms. That makes **short expiry, TLS, client auth, and active revocation on permission changes** essential.

### Does token expiry immediately kill an active WebSocket?

Do not assume access token expiration automatically disconnects every live WebSocket at that exact second. Expiry primarily governs token acceptance per service semantics—especially during connection establishment and reconnects. **To cut off an online user's access immediately**, implement and test server-side revocation, group removal, and connection closure.

## 10. Client permissions in Web PubSub: two foundational groups

With the **Azure Web PubSub client protocol**, common roles are:

| Role pattern | Capability | Scope |
|---|---|---|
| `webpubsub.joinLeaveGroup` | Allows client to join/leave groups broadly | Broad across groups in the hub |
| `webpubsub.joinLeaveGroup.<group>` | Allows client to join/leave one specific group | Single named group |
| `webpubsub.sendToGroup` | Allows client to send messages to groups broadly | Broad across groups in the hub |
| `webpubsub.sendToGroup.<group>` | Allows client to send messages to one specific group | Single named group |

Replace `<group>` with the **exact group name** verified by the backend—never an arbitrary client-supplied wildcard.

**Role examples:**

```text
Viewer of order-1042:
  webpubsub.joinLeaveGroup.tenant-a.order-1042
  (no sendToGroup)

Agent chatting on order-1042:
  webpubsub.joinLeaveGroup.tenant-a.order-1042
  webpubsub.sendToGroup.tenant-a.order-1042

Server publisher:
  uses server SDK / data-plane permissions,
  NO broad client roles needed
```

### Roles do not replace business authorization

Even when a client holds `sendToGroup`, that does not prove message content is safe or that the user is authorized to **mutate order state**. If messages trigger business actions, the backend must re-authenticate and authorize inside the handler/API before executing.

## 11. Join/leave permissions differ from send permissions

An order status notification room typically only needs buyers to **receive updates**.

- When the backend **adds a connection to a group**, the client receives group broadcasts through active membership without necessarily needing self-join roles.
- If the client is allowed to issue `joinGroup` via the client protocol, it needs the matching **joinLeaveGroup** role.
- If the client is allowed to issue `sendToGroup`, it needs the matching **sendToGroup** role.
- If the client should only receive status alerts from the backend, **never grant `sendToGroup`**.

Common misconceptions:

| Statement | True or false? | Explanation |
|---|---|---|
| "Being in a group gives permission to send group messages." | False. | Membership and send permissions are separate. |
| "Having `sendToGroup` automatically joins the group." | False. | Send authorization does not grant group membership. |
| "Clients need `sendToGroup` to receive server broadcasts." | False. | Receiving broadcasts depends on group membership/routing. |
| "If a client knows the group name, it can join." | False. | Requires a matching role or an authorized server-side add. |
| "Servers using the admin SDK must request client roles." | False. | Server data-plane ops and client protocol roles are separate channels. |

## 12. Secure-by-default design: server-controlled membership

For sensitive multi-tenant data, the easiest model to lock down is **granting zero self-join permissions**. Clients authenticate with the backend, and the backend joins connections after verifying authorization.

```text
Client opens WebSocket with trusted user ID
           |
           v
Client → HTTPS POST /api/rooms/1042/join
           |
           v
Backend verifies:
  - valid user login?
  - belongs to tenant A?
  - authorized to view Order 1042?
  - connectionId belongs to calling user?
           |
           +-- No → 403, do not add
           |
           +-- Yes
                 |
                 v
      Server SDK AddConnectionToGroup
                 |
                 v
      Client receives events in authorized group
```

Pros:

- Backend retains full control over **join, leave, and auditing**.
- Clients cannot probe or join rooms outside verified sets.
- Viewers need no `joinLeaveGroup` role at all.
- Join decisions reflect current tenant and room state.
- Easy to layer in rate limiting and business audit logs.

Trade-offs:

- One API call / server operation per join or leave, depending on flow.
- Must prevent `connectionId` spoofing.
- Must handle races between join calls and disconnects.
- Every reconnect creates a new connection requiring re-verification.

Never treat a client-supplied `connectionId` as proof of ownership. Map connections to authenticated users using verifiable service/event-callback records, or use user-level APIs with tested semantics.

## 13. Client-controlled design: scoped roles and business guards

Highly interactive chat apps sometimes let clients join/leave rooms themselves once cleared by the backend. Here the backend mints **group-specific roles** rather than hub-wide permissions.

```text
Negotiate:
  user = agent-71
  allowed room = tenant-a.order-1042

Issued role:
  webpubsub.joinLeaveGroup.tenant-a.order-1042

Client:
  joinGroup("tenant-a.order-1042") → allowed
  joinGroup("tenant-b.order-9001") → denied
```

**Note:** this illustrates a negotiate decision; endpoint paths are application-defined. Roles must be embedded into the token/authorization by the backend using actual SDK APIs.

Limitations to manage:

- After business permissions are revoked, existing tokens may remain valid; servers must **remove membership, revoke, or close connections** as needed.
- Group names visible to clients are not secrets; never rely on obscurity for protection.
- If chat messages mutate state, server handlers must still enforce business authorization.
- Minting roles for dozens of rooms bloats token scope and complicates revocations.
- When memberships churn constantly, server-controlled joins are generally easier to enforce cleanly.

### Do viewers need join permissions?

Not necessarily. Viewers who only receive alerts can have their connections added directly by the backend. Choose based on UX, permission churn speed, and data sensitivity.

## 14. Role-based authorization matrix

Example order support platform:

| Business role | Join group | Send group message | Modify order |
|---|---|---|---|
| Buyer | Only rooms for orders they own | No by default; if chat enabled, scoped room + filtered messages | Only via authenticated business API |
| Support agent | Assigned rooms while assignment is active | Only authorized chat rooms | Only via business API and authz |
| Supervisor | Rooms in managed region/team | Send announcements per policy | Independent backend permissions |
| Operator / monitor | Dedicated observability group or server feed | No client send role needed | No |
| Backend publisher | Uses service SDK to target exact groups | Yes via server data plane | Per service identity and business policy |
| Unknown / unauthed user | No sensitive groups | No | No |

Never conflate **application RBAC** with **Azure RBAC**:

- Azure RBAC governs who manages the Web PubSub resource and executes backend server data-plane calls.
- Application RBAC/ABAC governs which end users enter which rooms.
- Web PubSub client roles constrain specific WebSocket protocol actions granted to a connection.

All three must align, yet none replaces the others.

## 15. Backend issuing client access URIs: .NET example

Conceptual example using **Azure.Messaging.WebPubSub** and **Azure.Identity**. The backend authenticates the caller via middleware and **determines** valid user IDs and groups itself—never reading unchecked role lists from requests.

```csharp
using Azure.Identity;
using Azure.Messaging.WebPubSub;

// Illustrative backend code: endpoint, hub, and principal already verified.
var endpoint = new Uri("https://wps-customer-lab.webpubsub.azure.com");
string hubName = "orders";
string userId = "buyer-1042";
string groupName = "tenant-a.order-1042";

// Backend/service identity must hold appropriate data-plane permissions.
var client = new WebPubSubServiceClient(
    endpoint,
    hubName,
    new DefaultAzureCredential());

// Allow client only to join/leave the authorized room.
// Omit sendToGroup if this is a read-only viewer.
Uri accessUri = client.GetClientAccessUri(
    userId: userId,
    roles: new[] { "webpubsub.joinLeaveGroup." + groupName },
    expiresAfter: TimeSpan.FromMinutes(5));

// Return accessUri.AbsoluteUri to the authenticated caller over HTTPS.
// Never log the URL/token or store it in source code.
```

**Runtime prerequisites:**

1. Backend project uses an SDK version supporting this constructor and `GetClientAccessUri`.
2. Endpoint and hub exist in the lab resource.
3. Backend principal holds data-plane permissions to generate access URIs per SDK auth model.
4. Backend verified that **`buyer-1042` is genuinely authorized to view `order-1042`**.
5. HTTPS negotiate response is protected with no-cache headers and omitted from public logs.
6. Client uses the signed URL to open the WebSocket **before expiration**.

If your SDK version uses a different overload, use the published equivalent—**never fall back to hardcoding service keys in browsers**. This snippet illustrates token minting only, not a complete endpoint with auth middleware.

## 16. Secure negotiate endpoint pseudocode

Authorization checks matter even more than the SDK call:

```text
GET /api/realtime/negotiate?orderId=ORD-1042

principal = VerifyApplicationAccessToken(request)
if principal is missing:
    return 401

tenantId = principal.tenantId
userId = principal.stableUserId
orderId = NormalizeAndValidate(request.orderId)

order = OrdersRepository.GetByTenantAndId(tenantId, orderId)
if order does not exist:
    return 404 or permitted non-disclosing response

if not Authorization.CanViewOrder(principal, order):
    return 403 or permitted non-disclosing response

group = CanonicalGroupName(tenantId, orderId)
roles = ["webpubsub.joinLeaveGroup." + group]  # if self-join enabled
signedUrl = WebPubSubService.GenerateClientAccessUrl(
    hub="orders",
    userId=userId,
    roles=roles,
    expiresIn=5minutes
)

return HTTPS 200 with:
    url = signedUrl
    group = group
    expiresInSeconds = 300
Cache-Control: no-store
```

**Pseudocode, not ready for direct deployment.** Add rate limiting, auditing, request validation, error handling, and CSRF protections if using cookie auth. Never trust `tenantId`, `userId`, or `roles` from client query strings or request bodies.

### Avoid leaking room existence

In sensitive systems, returning 403 vs 404 can leak whether an order ID exists. Pick a consistent error strategy and never return internal authorization details to unauthorized callers.

## 17. WebSocket client: connecting and receiving group messages

Browser example using the **Web PubSub JSON subprotocol**. The token URL is issued by an authenticated backend.

```javascript
// Assumes /api/realtime/negotiate is already authenticated.
// Never print the token URL to console/logs.
const response = await fetch("/api/realtime/negotiate?orderId=ORD-1042", {
  credentials: "include",
  cache: "no-store"
});

if (!response.ok) {
  throw new Error("Not authorized to establish real-time connection");
}

const { url, group } = await response.json();

// Azure Web PubSub client protocol with JSON messages.
const socket = new WebSocket(url, "json.webpubsub.azure.v1");
let nextAckId = 1;

socket.addEventListener("open", () => {
  socket.send(JSON.stringify({
    type: "joinGroup",
    group: group,
    ackId: nextAckId++
  }));
});

socket.addEventListener("message", (event) => {
  const frame = JSON.parse(event.data);

  if (frame.type === "message") {
    // Received payload only.
    // Render safely: avoid injecting untrusted HTML.
    renderNotificationAsText(frame.data);
  } else if (frame.type === "ack") {
    handleAcknowledgement(frame);
  }
});

socket.addEventListener("close", () => {
  // Stop sending, trigger reconnect with backoff and re-negotiate.
  scheduleAuthenticatedReconnect();
});
```

**`renderNotificationAsText`, `handleAcknowledgement`, and `scheduleAuthenticatedReconnect`** are illustrative stubs that the app must implement. This snippet demonstrates connection structure, **not a drop-in runnable script** without those helpers.

### Never treat client-side JavaScript as the final permission gate

Users can edit JavaScript in DevTools at will. The server must enforce allowed roles and groups; merely hiding a "Join tenant B" button provides zero security.

## 18. Client protocol: `joinGroup`, `leaveGroup`, `sendToGroup`

Illustrative JSON client protocol frames:

**Join group** — requires `joinLeaveGroup` permission when initiated by the client:

```json
{
  "type": "joinGroup",
  "group": "tenant-a.order-1042",
  "ackId": 1
}
```

**Leave group**:

```json
{
  "type": "leaveGroup",
  "group": "tenant-a.order-1042",
  "ackId": 2
}
```

**Send group message** — only for clients holding the matching `sendToGroup` permission:

```json
{
  "type": "sendToGroup",
  "group": "tenant-a.order-1042",
  "dataType": "json",
  "data": {
    "kind": "ChatMessage",
    "text": "I need support for this order"
  },
  "ackId": 3
}
```

### Role of `ackId`

`ackId` lets the client correlate **service acknowledgements** with join/leave/send commands. However, a service success ACK **does not** mean:

- Every client in the group is online.
- Every device received and rendered the content.
- The message was durably saved in a database.
- A support agent read or acted on the request.
- Any business command inside the payload was authorized and committed.

To confirm "read" or "processed", build **application-level acknowledgements / read receipts** backed by persistent state.

## 19. Handling ACKs and permission denials on the client

Clients should track pending commands by `ackId`:

```text
Pending:
  ackId=10 → join tenant-a.order-1042
  ackId=11 → send message to room
  ackId=12 → leave room

When ACK arrives:
  - match ackId
  - inspect success/error fields per protocol version
  - update UI status
  - if permission denied: never retry blindly
  - on reconnect: request fresh URL and resync membership
```

Errors to distinguish:

- **Permission denied:** user lacks the role or access was revoked.
- **Invalid group name / protocol:** malformed payload or syntax.
- **Connection closed:** token, network, server action, or lifecycle termination.
- **Transient network error:** eligible for reconnect with backoff.
- **Join acknowledged yet no messages appear:** no publisher yet, quiet group, backend sending to wrong hub/group, or joined after message was emitted.

Never loop retries on an unauthorized group hoping to "wait until granted". Permission changes must flow through the backend and business workflows.

## 20. Server-managed groups via SDK/REST

A backend with data-plane permissions can manage memberships without letting clients self-join:

```text
Authorized API request
   |
   v
Validate user + tenant + room + connection ownership
   |
   +-- AddConnectionToGroup(group, connectionId)
   |
   +-- RemoveConnectionFromGroup(group, connectionId)
   |
   +-- SendToGroup(group, payload)
   |
   +-- CloseConnection(connectionId) when needed
```

These are **conceptual operation names**, not guaranteed identical signatures across every SDK version. Some SDKs also provide **user-level** operations beyond per-connection calls; verify multi-device semantics carefully.

### Deliberate C# pseudocode

```csharp
// PSEUDOCODE: verify exact method names and arguments against your SDK version.
async Task ApproveAndJoinAsync(
    Principal actor, string connectionId, string roomId)
{
    var room = await rooms.LoadAsync(actor.TenantId, roomId);

    if (!policy.CanRead(actor, room))
        throw new ForbiddenException();

    if (!await connections.BelongsToUserAsync(connectionId, actor.UserId))
        throw new ForbiddenException();

    string group = CanonicalGroup(actor.TenantId, room.Id);

    await webPubSubAdmin.AddConnectionToGroupAsync(
        group, connectionId);
}
```

`connections.BelongsToUserAsync` is critical. If a client could pass someone else's `connectionId`, the backend could accidentally add **a victim's connection** into the wrong group.

## 21. Why must group names be canonicalized and tenant-scoped?

Names like `room-1042` are **unsafe** in multi-tenant apps because tenant A and tenant B can share overlapping order IDs.

Canonical naming example:

```text
tenant-a.order-1042
tenant-a.order-1043
tenant-b.order-1042
```

Yet canonical names **never grant authorization on their own**. The backend must verify:

1. Tenant ID comes from verified identity, never client-supplied strings.
2. Order/room belongs to that tenant.
3. User holds view/send rights at the time of the operation.
4. Group names are constructed from normalized components and validated against service limits.
5. Special characters, empty strings, delimiters, or Unicode differences cannot cause accidental collisions.
6. Include a version/prefix if group naming schemas evolve.
7. Backend and publishers share one canonical naming helper rather than duplicating divergent logic.

### Watch sensitive data in group names

Group names can surface in diagnostics, URLs, and logs. Never embed emails, phone numbers, access tokens, or support details inside group names. Use opaque IDs backed by protected lookup tables.

## 22. User-level vs connection-level group operations

Two scopes serve different goals:

**Connection-level:** targets one specific WebSocket connection.

- Ideal when Tab 1 watches Order A while Tab 2 of the same user watches Order B.
- Granular UI/session membership control.
- After reconnect, the old connection ID is invalid.
- Requires verifying `connectionId` ownership.

**User-level:** targets a logical user ID, potentially affecting multiple connections per API semantics.

- Ideal for broadcasting alerts across all devices of a user.
- Understand whether your SDK/API affects only currently connected sessions or carries additional semantics for new connections.
- When one user accesses multiple tenants/contexts, never confuse a global user ID with a tenant-scoped policy.
- Clarify whether logout, bans, or role changes apply to **all devices** or one session.

**Rule:** runbooks must state explicitly "remove connection C1 from group" vs "remove user U across active connections" and note tab impacts—never write vaguely "remove from room".

## 23. One user with multiple tabs and devices

Suppose `buyer-1042` has three active connections:

```text
C1 — Chrome, viewing order-1042
C2 — Safari, viewing order-1042
C3 — Mobile, viewing overall dashboard
```

Options:

- **By connection:** add C1 and C2 to the order group; skip C3.
- **By user:** server pushes general notifications to all connections of `buyer-1042` where appropriate.
- **By app session:** maintain trusted session-to-connection mappings to revoke a single device cleanly.

### Real-world race condition

1. Browser C1 requests to join.
2. C1 drops network; Web PubSub closes the connection.
3. Backend finishes authorization checks and tries adding C1 to the group.
4. The operation returns not-found or lifecycle errors because the connection already vanished.

Handling: treat disconnect/not-found as normal, log at an appropriate level, and never substitute another connection belonging to the user without verifying intent. On reconnect, the client re-negotiates and joins with its new connection.

## 24. Reconnect: new connections do not keep all old state

WebSockets are not immortal channels. Devices switch from Wi-Fi to 4G, browsers sleep, services scale, or servers close idle sockets.

```text
Connected C1, member of group G
        |
        v
Network disconnected
        |
        v
C1 closed / membership tied to C1 ends
        |
        v
Client re-negotiates
        |
        v
Connected C2 (new ID)
        |
        v
Backend re-checks current permissions
        |
        v
Join group G (if still authorized)
```

Requirements:

1. **Exponential backoff with jitter** for reconnects.
2. Request a **fresh client URL** if the previous URL expired.
3. Re-authenticate and re-authorize permissions **from scratch**.
4. Re-establish required memberships; never assume prior session state survived.
5. Display "joined room" only after receiving fresh confirmation.
6. Call a state API after reconnecting to recover any real-time events missed while offline.
7. Clean up old socket listeners so one UI never holds duplicate sockets.

Some client SDKs/protocols offer limited connection recovery or reliable delivery windows; never assume that provides durable message history or removes the need for offline state sync.

## 25. Revoking access when a user leaves a room or is blocked

**Scenario:** a support agent is unassigned from an order at 10:00 while their WebSocket remains connected.

Flipping `assigned=true` to `false` in the database **is not enough** if the connection remains in the group and keeps receiving messages. The system needs an **authorization revocation workflow**.

```text
Supervisor removes agent from order
          |
          v
DB transaction: revoke assignment
          |
          v
Authorization/revocation event
          |
          +-- invalidate cached permissions
          +-- revoke join/send ability if supported by API
          +-- remove active connection/user from group
          +-- optionally close affected connections
          |
          v
Verify no further sensitive group delivery
```

### Critical sequence of actions

- If the client still holds `joinLeaveGroup.G`, merely removing membership is insufficient: the client can rejoin itself. **Revoke permissions or close the connection**, depending on service APIs and risk level.
- Issued access URLs may still be unexpired; use short expirations and react proactively to access changes.
- Permission caches must be invalidated or tightly bounded by TTL/policy version.
- A message already in flight right before revocation may still arrive; **you cannot un-send already delivered data**. Factor this window into your threat model.
- Verify revocation across **all affected connections**, not just the active tab.

### Measuring success

Do not stop at verifying the backend returned HTTP 200. Test with a client: after revocation, attempt to rejoin/send and publish a non-sensitive test ping to the group; the revoked client must fail to rejoin and receive nothing once policy takes effect.

## 26. Event handlers: connect, connected, disconnected, and user events

Azure Web PubSub allows configuring **event handlers / upstream endpoints** for connection and message lifecycle events per supported modes.

Common event groups:

- **Connect:** fired during connection setup, allowing the backend to approve/reject and shape user/role/group context per supported handler contracts.
- **Connected:** notifies that the connection is established.
- **Disconnected:** notifies that the connection ended.
- **User events:** custom client events routed to the backend per protocol/handler configuration.

### Why handlers need security

- Webhooks/upstream endpoints receive service HTTP requests and must verify caller origin and supported authentication mechanisms.
- Never leave an event handler URL open anonymously trusting arbitrary payloads.
- When a connect handler returns roles/groups, derive them from **trusted policy**, never client-controlled strings.
- Handlers must tolerate retries, duplicates, and out-of-order deliveries per service semantics.
- Avoid long database transactions inside synchronous connect decisions.
- `Disconnected` events can arrive late or cannot serve as the sole presence source of truth; maintain TTL/cleanup reconciliation.

Never equate **"connected successfully"** with **"joined a group"**. Membership must be granted or accepted through its explicit flow.

## 27. Backend publishing messages to groups

Suppose the system consumes a status event from an Order worker:

```json
{
  "eventType": "OrderStatusChanged",
  "orderId": "ORD-1042",
  "status": "Shipped",
  "eventId": "evt-1042-shipped-1",
  "occurredAtUtc": "2026-11-20T09:00:00Z"
}
```

The backend:

1. Verifies the event comes from an authorized source.
2. Resolves tenant/order from an authoritative record—**never trusting a group name embedded in an untrusted event body**.
3. Builds group `tenant-a.order-1042`.
4. Calls the Web PubSub **server SDK send-to-group** with a sanitized payload.
5. Observes API status/latency and logs correlation and event IDs.
6. If message history is required, persists to DB/event store **beforehand or via outbox**.
7. For offline users, frontends fetch current state from the API on reconnect.

### Pseudocode

```text
onOrderStatusChanged(event):
    order = trustedRepository.get(event.orderId, event.tenantId)
    if order is null:
        raise or quarantine

    group = canonicalGroup(order.tenantId, order.id)
    payload = {
        eventType: "OrderStatusChanged",
        orderId: order.id,
        status: order.currentStatus,
        eventId: event.eventId
    }

    webPubSubServer.sendToGroup(hub="orders", group, payload)
    metrics.increment("realtime_publish_attempt")
```

**Send-to-group succeeding** does not mean every client received or read the alert. If proof is needed, implement app-level ACKs, persistent message stores, or explicit read tracking.

## 28. Never broadcast broader than necessary

Compare routing scopes:

| Target | Right operation | Risk if wrong |
|---|---|---|
| One specific connection | Send to connection | Wrong connection targets another user |
| All connections of one user | Send to user, when apt | Pushes to devices outside an intended session |
| Connections joined to a room | Send to group | Wrong group name → cross-tenant leak |
| All connections in the hub | Broadcast to hub/all | **Extremely dangerous** for private order data |

When payloads contain PII or order details, **never fall back to hub-wide broadcasts** if a group lookup fails. Abort the send, alert, and reconcile.

### Separate event notifications from sensitive payloads

A lean notification looks like:

```json
{
  "kind": "OrderChanged",
  "orderId": "ORD-1042",
  "version": 12
}
```

The frontend then calls an authorized HTTPS API for full details. This keeps sensitive data off real-time pipes, though you must balance API call rates, caching, and consistency.

## 29. Validating client-submitted content: preventing XSS and injection

If supporting chat or client-to-group sends:

- Validate **size, data types, content types, schemas, and encoding**.
- Cap text length and attachment metadata.
- Never render incoming text via `innerHTML` without sanitization.
- Never let clients self-tag messages as "system", "admin", or "paid" for the backend to trust.
- Never allow SQL queries, commands, or service credentials inside client messages.
- Enforce rate limits and anti-spam controls by user, IP, and tenant.
- Attach `senderUserId` from **verified identity**, never from payload claims.
- When moderation/auditing is required, route **client messages to a backend event handler** for validation before server republishing instead of granting open direct sends.
- Enforce CSRF/CORS on negotiate and backend APIs matching your auth model.

**`sendToGroup` governs routing scope only**—it never validates that chat content is safe or legitimate for recipients.

## 30. Do group messages persist while users are offline?

**Never treat an Azure Web PubSub group as a durable message queue.**

```text
10:00  Server sends "Order shipped" to group G
10:00  Browser A online, in G → receives alert
10:00  Browser B offline     → no built-in replay queue
10:03  Browser B reconnects  → must call API for current state
```

If business rules forbid **missing notifications**, combine stores:

```text
Order event
   |
   +-- Persist durable state / notification record
   |       |
   |       +-- API GET /notifications?since=cursor
   |
   +-- Publish real-time hint via Web PubSub
           |
           v
       Client updates UI
           |
           +-- On reconnect, fetches missed state/events
```

Maintain message IDs, cursors/sequences, idempotency, and retention in the app tier. WebSockets are a **near-real-time delivery channel**, not proof of durable storage.

## 31. Ordering, duplicates, and acknowledgements

Applications can encounter:

- Delayed messages due to network jitter.
- Client reconnects racing with API snapshot refreshes.
- Workers redelivering notifications with the same event ID.
- Two publishers updating state nearly simultaneously.
- Real-time pings reaching the UI before read replicas reflect the write.
- Protocol ACKs succeeding while UI rendering or user reading hasn't happened.

### Fault-tolerant design

1. Assign a unique business `eventId` per event.
2. Give entities a monotonically increasing **version** or commit marker.
3. Clients ignore events older than the currently applied version.
4. On detecting a version gap, call the API for authoritative state.
5. Deduplicate by `eventId` over a suitable window.
6. Never treat WebSocket arrival timestamps as authoritative business order.
7. Never treat a group spanning multiple connections as a totally ordered transaction log.

**Example:** if the client already rendered Order version 12 and version 11 arrives late, it must never revert UI state to version 11.

## 32. Presence and group membership: approximate state

An app wants to show "3 people online in this room." Yet connection counts do not equal user counts:

```text
Buyer A:
  2 WebSocket tabs → 2 connections, 1 user

Agent B:
  1 desktop app    → 1 connection, 1 user
```

The group holds 3 connections representing only 2 users. Moreover, network drops introduce lag between actual disconnects and cleanup events.

### Presence models

| Model | What it measures | Caveats |
|---|---|---|
| Service-level connection status | Whether a connection/user is online per supported API | Update lag and timeouts |
| App in-memory/cache map | Temporary list of connection IDs per user/group | Crashes, multi-instance drift, TTLs, stale leaks |
| Redis cache with TTL | Fast near-real-time presence lookup | Non-authoritative; needs expiry/refresh/reconciliation |
| Database membership | User is **authorized** in the room | Does not prove the user is currently online |
| Audit events | Who joined/left and when | Events can lag or duplicate; needs timestamps/IDs |

Never turn a presence/heartbeat cache into an authorization check; always validate sensitive actions against authoritative business policies.

## 33. Permission caching: speed requires invalidation

If every WebSocket join hits the database, the backend may cache `CanViewRoom(userId, roomId)` with a TTL. However, cached permissions become dangerous if revocations are ignored.

Example:

```text
10:00  Agent has access to room R → cache ALLOW for 15 min
10:01  Supervisor revokes access in DB
10:02  Agent rejoins room R → stale cache still returns ALLOW
```

Mitigations:

1. Keep permission TTLs short relative to sensitivity.
2. Invalidate cache entries when assignments or roles change.
3. For high-privilege actions, query the **authoritative source** or check a policy version.
4. Bind cache keys to **tenantId + userId + roomId + role/policy version**.
5. Never cache results from unauthenticated requests.
6. Enforce **fail-closed** behavior for sensitive permissions when Redis/cache is unavailable.
7. Never key permission caches solely by `roomId` in multi-tenant apps.
8. Monitor denial rates, invalidation lag, and stale authorization incidents.

Caching aids performance—never let it let a revoked user keep reading private data.

## 34. Azure SignalR Service: groups have different semantics

When using **ASP.NET Core SignalR**, connection groups are typically managed via **Hub methods** and `IGroupManager` or SignalR Service management APIs.

ASP.NET Core Hub example:

```csharp
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.SignalR;

[Authorize]
public sealed class OrderHub : Hub
{
    private readonly IOrderAccessPolicy _policy;

    public OrderHub(IOrderAccessPolicy policy)
    {
        _policy = policy;
    }

    public async Task JoinOrder(string orderId)
    {
        string? userId = Context.UserIdentifier;
        if (userId is null ||
            !await _policy.CanViewOrderAsync(userId, orderId))
        {
            throw new HubException("Not authorized for this order");
        }

        string group = _policy.CanonicalGroupFor(userId, orderId);
        await Groups.AddToGroupAsync(Context.ConnectionId, group);
    }

    public Task LeaveOrder(string groupName)
    {
        // Production code should derive/verify groupName server-side.
        return Groups.RemoveFromGroupAsync(
            Context.ConnectionId, groupName);
    }
}

// IOrderAccessPolicy is an application interface, not built into SignalR.
```

**This is a partial illustrative snippet** requiring an `IOrderAccessPolicy` implementation, DI registration, and auth config. For `LeaveOrder`, avoid trusting client-supplied group names directly in production; derive and verify the room from IDs/context.

### Differences from Web PubSub

| Web PubSub | SignalR |
|---|---|
| Uses JSON client protocol with `webpubsub.joinLeaveGroup...` and `sendToGroup...` roles | App defines Hub methods and authorization in ASP.NET Core; does not use Web PubSub roles |
| Clients can self-join with Web PubSub roles, or servers manage membership | Clients invoke Hub methods; servers validate and call `Groups.AddToGroupAsync` |
| Service server SDK manages groups/users/connections | SignalR Hub context / management SDK manages them under SignalR semantics |
| Access URI/token and hub belong to the Web PubSub service | SignalR negotiate/access tokens and Hub endpoints carry distinct semantics |

**Pick the service first, then match the SDK/permission model.** Never copy Web PubSub JSON protocol payloads into a SignalR client expecting them to work.

## 35. Microsoft Entra ID, managed identity, and Azure RBAC

For backends managing Azure Web PubSub:

- Prefer **managed identity** when supported by the service and SDK.
- Grant the appropriate Azure RBAC **data-plane role** at the resource scope to the backend.
- Restrict control-plane resource, networking, and key management to infrastructure teams.
- Avoid plaintext service access keys/connection strings in app settings whenever identity auth works.
- When keys must be used, store them in Azure Key Vault / secret managers and rotate regularly.
- Never grant resource data-plane roles to end-user browsers just to let them join groups.
- Browsers connect using **controlled client access URLs** minted after application authentication.
- Room authorization still rests on dedicated backend databases/policies.

**Azure Contributor on a resource group** does not mean "every client can view every group." **Enabling managed identity** does not automatically grant send permissions either—verify role assignments, scopes, and data-plane operations.

### Client apps using Microsoft Entra login

A clean pattern:

```text
Browser → Entra authentication → application bearer token
    → Backend API negotiate validates user and tenant
    → Backend issues Web PubSub client access URL
    → Browser opens WebSocket
```

An Entra token for your application API and a Web PubSub client access token **are not interchangeable**. Respect each token's audience, issuer, scope, lifetime, and protocol.

## 36. TLS, networking, and Private Endpoints

Layers to verify:

1. **HTTPS** for application negotiate/APIs.
2. **WSS** for browser → Web PubSub.
3. Exact resource/hub endpoints and DNS resolution.
4. Network restrictions / public vs private access per SKU/tier.
5. Backend Private Endpoint / VNet connectivity where required and supported.
6. NSGs, Azure Firewall, UDRs, NAT, and outbound egress paths.
7. Can Internet browser clients still reach the endpoint if public access is locked down?
8. Are token scopes and client roles valid?
9. Can the service reach and authenticate to upstream event handlers?
10. Certificate and hostname validation must never be disabled as a "quick fix".

**Private Endpoints do not provide authorization**—they only alter network routing. If Web PubSub allows private VNet access only, **external browsers outside the VNet cannot connect**; finalize client public/private topology before locking down access.

Never assume every tier/region supports identical networking features. Check the live feature matrix first.

## 37. Service limits, performance, and quotas

Capacity depends on:

- **Concurrent connections**.
- Inbound/outbound message rates and payload sizes.
- Join/leave/reconnect frequency.
- Group count, connections per group, and per-hub/tier caps.
- Bandwidth/egress and service units/capacity.
- Backend authentication and negotiate throughput.
- Upstream event handler processing speed.
- Wide fan-out, especially groups holding tens of thousands of sockets.
- Reconnect retry storms after network or service glitches.

### Fan-out multiplies outbound traffic

Illustrative example:

```text
Backend sends 1 message to a group of 10,000 connections
→ Generates up to 10,000 outbound real-time deliveries
  (depending on active connections and service behavior).
```

**One send call does not equal one outbound message.** Factor recipient counts and payload sizes into capacity and cost models.

### Reconnect storms

When 20,000 clients drop and reconnect at once:

- Backend negotiate endpoints can saturate.
- Every client fetches a fresh token and rejoins groups.
- Group control operations spike.
- Redis/DB authorization queries surge.
- Outbound traffic, CPU, and latency degrade.

Use jitter, balanced short token TTLs (not so short they force constant re-negotiation), safe auth caching, capacity planning, and load testing within tier limits.

## 38. Monitoring connections, groups, and permissions

Production observability should pair **service metrics** with **business authorization telemetry**.

| Signal | Operational question | Source |
|---|---|---|
| Connected clients / current connections | How many WebSockets are active? | Azure Monitor metrics on Web PubSub resource |
| Connection opens / closes / failures | Are disconnects or reconnects climbing? | Resource metrics/diagnostics + client telemetry |
| Incoming / outgoing messages | Are traffic spikes or drops occurring? | Service metrics |
| Server / API send failures | Are publishers succeeding? | Backend logs + service diagnostics |
| Join / leave success / failure | Are clients denied roles or sending bad frames? | Client ACKs/errors + server audits |
| Unauthorized join / send attempts | Is someone probing other groups? | Backend authz logs, protocol errors, security alerts |
| Active group memberships | Which connections belong to which rooms? | App mappings/lifecycles; service APIs where supported |
| Token issuance / expiration | Is negotiate over-issuing scopes? | Backend audit logs (never store tokens) |
| Revocation delay | How fast do revoked clients stop receiving data? | Security tests + audit metrics |
| Send-to-group latency / p95 | How fast is real-time UX? | Backend timings + client E2E telemetry |
| Missed state after reconnect | Is UI showing stale data post-offline? | App reconnect/sync metrics |

**Azure Monitor does not automatically expose a "per-group user membership count" metric.** Build reconciled application counters or query management APIs where supported.

### Correlation IDs

Chain IDs end-to-end:

```text
Order eventId=evt-1042-shipped-1
  → backend publish operation ID
  → Web PubSub target hub/group
  → client received eventId
  → client state refresh requestId
```

Never use access tokens or raw client URLs as correlation IDs. Log **hashes or opaque IDs** per policy to minimize exposure.

## 39. Cost and group scalability

Cost components include:

- Web PubSub tier/capacity, concurrent connections, and message meters per pricing model.
- Outbound fan-out across large groups.
- Backend App Service / Functions / AKS / Container Apps for negotiate and event handlers.
- Databases / Redis storing room authorization, memberships, and state.
- Private Endpoints, network egress, firewalls/NAT, and DNS.
- Azure Monitor logs, Application Insights, and retention.
- Persistent notification stores / Service Bus if supporting offline catch-up.
- Load testing and operational overhead.

| Design choice | Impact |
|---|---|
| One group per order | Strong data isolation; more group names and lifecycle tracking |
| One shared group per tenant | Fewer groups, yet leaks data if buyers cannot view every tenant order |
| Hub-wide broadcast | Simple to code, high privacy risk and massive fan-out |
| Large payloads per update | Higher bandwidth/cost and latency; prefer lean hint + API fetch |
| Frequent reconnects | Drives up token minting, connection churn, and group ops |
| Long-TTL permission caches | Cuts DB reads, increases stale-authorization risk |

Never reduce group count by sacrificing **tenant isolation**. Use the Azure Pricing Calculator and real service telemetry—never guess bills from a single connection number.

## 40. Runbook: Client A can join Tenant B's group

**Severity:** cross-tenant data leak risk—highest priority.

### Investigation

1. Record incident ID, UTC timestamps, and sanitized user/tenant IDs.
2. Never emit sensitive payloads in production to reproduce the bug.
3. Inspect the negotiate endpoint: does it verify principal and tenant claims?
4. Inspect group-naming code: did it accept a client-supplied `roomId` blindly?
5. Inspect minted token roles: was overly broad `webpubsub.joinLeaveGroup` issued?
6. Check server-side `AddConnectionToGroup`: does it validate connection ownership?
7. Check permission caches: stale entries or missing tenant ID in cache keys?
8. Inspect active group subscriptions/memberships for out-of-scope connections.
9. Audit logs to identify which payloads may have been exposed.
10. Escalate per incident response and privacy policies.

### Remediation

- Revoke roles/joins and remove/close affected connections per service capabilities.
- Disable or restrict the flawed negotiate path until patched.
- Reissue tokens with tightly scoped, short-lived roles.
- Enforce tenant-aware authorization and canonical group naming.
- Flush/invalidate permission caches and deploy the approved fix.
- Run negative cross-tenant tests and inspect monitoring.
- Never try to "wipe every group" to hide an incident; preserve audit trails and assess real blast radius.

### Takeaway

**Group names are not passwords.** Permissions must bind to verified users, tenants, and resources enforced by the backend and service.

## 41. Runbook: permissions revoked, yet client keeps receiving messages

**Symptom:** an agent is removed from a room, yet an open browser tab continues receiving alerts.

### Possible causes

- Backend updated the database only without removing active group membership.
- Access token/role remains valid.
- Agent automatically rejoins because `joinLeaveGroup.G` was not revoked.
- User holds multiple active connections; only one was removed.
- Permission cache was not invalidated.
- Revocation event lagged or failed inside a worker.
- Message was already dispatched right before revocation and arrived slightly later.

### Steps

1. Compare exact timestamps of the policy change and message dispatch.
2. Identify all active connections belonging to the user.
3. Revoke scoped permissions or close connections where supported.
4. Remove active group memberships.
5. Invalidate authorization caches.
6. Force re-negotiation or re-authentication.
7. Attempt to rejoin and send: both must be rejected.
8. Emit a non-sensitive lab event; verify the revoked client receives nothing.
9. Record end-to-end revocation latency and inspect race windows.
10. Add alerts for failed revocation workflows.

**Limitation:** data already rendered on a client screen before revocation cannot be clawed back. Minimize sensitive payloads and bound permission lifetimes up front.

## 42. Runbook: reconnect succeeds, yet group messages stop arriving

**Symptom:** UI reports "Connected", yet order updates stop after a mobile network handoff.

### Investigation

1. Did the new connection receive a different ID from the old one?
2. Did the client fetch a fresh access URL if the old URL expired?
3. Is the client using the right hub and subprotocol?
4. Did the backend issue matching roles under current policies?
5. Did the client send `joinGroup`, or did the server re-add the new connection?
6. Did the join ACK report success or permission denied?
7. Is the backend publisher targeting the exact hub and group name?
8. Is client code misfiltering or failing to parse the payload?
9. Are Private Endpoints, DNS, or network rules blocking traffic?
10. Were messages sent while the client was offline? If so, an API catch-up call is needed.

### Remediation

- Re-negotiate and re-authorize room access.
- Rejoin on the current connection and wait for ACK or server membership confirmation.
- Resync current state from the durable API.
- Enforce `eventId`/`version` checks for duplicates and out-of-order frames.
- Use reconnect backoff—never tight infinite loops.
- Track post-handoff failure counts and reconnect latency.

**Takeaway:** an open WebSocket does not mean the new connection rejoined old groups. Every reconnect requires **state rehydration**.

## 43. Exercise: tenant-isolated order notification system

**Scenario:** create a lab Azure Web PubSub resource with hub `orders` and three test users:

- Alice in tenant A, viewing Order 1042.
- Bob in tenant A, viewing Order 1043.
- Carol in tenant B, viewing Order 9001.

Authorization requirements:

| User | Allowed to join/receive | Client-side send |
|---|---|---|
| Alice | `tenant-a.order-1042` | No |
| Bob | `tenant-a.order-1043` | No |
| Carol | `tenant-b.order-9001` | No |
| Server publisher | Sends to backend-verified groups | Server-side operation |

### Tasks

1. Diagram browser → negotiate API → Web PubSub → groups → backend publisher.
2. Provision the lab resource/hub within approved permissions and budget; confirm tier and endpoint.
3. Configure least-privilege backend identity and server-side permissions.
4. Seed test authorization records for Alice, Bob, and Carol.
5. Build the negotiate endpoint reading user/tenant from verified principals.
6. Mint tokens carrying **only the `joinLeaveGroup` role for the authorized group** (or use server-controlled membership).
7. Omit `webpubsub.sendToGroup` for all three viewers.
8. Connect Alice to Web PubSub via the JSON client protocol.
9. Join `tenant-a.order-1042`; confirm success ACK.
10. Attempt to join `tenant-b.order-9001` using Alice's connection; confirm denial.
11. Attempt a client `sendToGroup` into Alice's room; confirm denial without send role.
12. Have Bob and Carol join their authorized groups.
13. Backend publishes one `OrderStatusChanged` event solely to Alice's group.
14. Confirm Alice receives it while Bob and Carol receive nothing.
15. Open a second tab for Alice and contrast connection-level vs user-level membership.
16. Disconnect the first tab and reconnect; verify new connection ID and membership restoration.
17. Revoke Alice's access, remove memberships/close connections, and verify she cannot rejoin.
18. Enable diagnostics/metrics and sanitized logs.
19. Tamper with the group name in frontend JS; verify backend/service never grants access.
20. Simulate publishing while Alice is offline; call the state API upon reconnect.
21. Measure send operations and recipient counts to estimate fan-out and cost.
22. Verify no token URLs appear in logs, Git, or browser analytics.
23. Write a cross-tenant join incident runbook.
24. Clean up dedicated lab resources without touching shared infrastructure.

### Test data

**Message sent to Alice:**

```json
{
  "eventId": "evt-lab-order-1042-shipped",
  "eventType": "OrderStatusChanged",
  "orderId": "ORD-1042",
  "version": 7,
  "status": "Shipped"
}
```

**Expected delivery:**

```text
Alice connection C1 in tenant-a.order-1042 → receives
Alice C2 if not joined                     → not expected to receive
Bob tenant-a.order-1043                    → must not receive
Carol tenant-b.order-9001                  → must not receive
```

**Negative authorization tests:** Alice attempts to join `tenant-b.order-9001`, send to an unauthorized group, or pass Carol's `userId` to negotiate. Backend/service must reject every attempt without issuing URLs or roles.

### Acceptance criteria

- Authenticated user IDs and tenants come strictly from backend identity, never client input.
- Each client receives only authorized group messages.
- Read-only viewers never receive `sendToGroup` roles.
- Clients cannot escalate roles by editing requests or JavaScript.
- Reconnects create new connections with verified membership restoration.
- Revocations terminate both active connections and rejoin capability.
- Private payloads are never broadcast hub-wide.
- Durable state store/API recovers updates missed offline.
- Logs and costs are monitored with zero leaked tokens.
- Test report documents both positive and negative (denied) test results.

## 44. Production checklist before enabling real-time groups

**Identity and authorization**

- [ ] Backend authenticates users and verifies tenants.
- [ ] Unchecked `userId`, `role`, or `groupName` from clients is never trusted.
- [ ] Group names are canonicalized, tenant-scoped, and free of secrets.
- [ ] Client roles are scoped strictly to required groups; avoid broad wildcards unless needed.
- [ ] Read-only viewers lack direct send permissions.
- [ ] Server data-plane credentials never appear on the frontend.
- [ ] Token URLs are short-lived, delivered over HTTPS, and never logged.
- [ ] Revocation, connection close/leave, and cache invalidation are implemented.

**Connectivity and correctness**

- [ ] Reconnects use backoff and re-negotiate.
- [ ] New connection IDs are never treated as persistent sessions.
- [ ] Revocation policies handle all active devices/tabs.
- [ ] Critical data exposes durable APIs/history to recover offline gaps.
- [ ] `eventId`/versions prevent duplicates and stale UI regressions.
- [ ] Protocol ACKs are never treated as user read receipts.
- [ ] Unknown group lookups never fall back to hub-wide broadcasts.
- [ ] Backend/APIs enforce business authorization on all mutations.

**Operations and safety**

- [ ] Azure RBAC / managed identities follow least privilege.
- [ ] TLS/DNS/private networking tested from the real runtime.
- [ ] Upstream event handlers authenticate callers.
- [ ] Metrics/logs/alerts cover connects, auth errors, joins/leaves, and send failures.
- [ ] Synthetic cross-tenant deny and revocation tests exist.
- [ ] Reconnect storms and fan-out load tested.
- [ ] Cost model accounts for connections, outbound messages, compute, and monitoring.
- [ ] Incident runbooks and operational owners assigned.

## 45. Self-check questions

**Q1.** In Azure Web PubSub, how do a hub and a group differ?

**Answer:** A hub is a logical namespace organizing connections, groups, and event handlers; a group is a subset of connections inside one hub receiving broadcasts targeted by group name.

**Q2.** Are `userId` and `connectionId` the same?

**Answer:** No. One user can hold multiple connections; `connectionId` identifies one specific WebSocket and changes on reconnect.

**Q3.** Does being authenticated allow a user to join any group?

**Answer:** No. The backend must verify tenant/room permissions before issuing roles or managing membership server-side.

**Q4.** What does `webpubsub.joinLeaveGroup.<group>` allow?

**Answer:** Allows the client to join/leave that specific group via the Web PubSub client protocol when legitimately granted.

**Q5.** Does `webpubsub.sendToGroup.<group>` automatically let a client receive messages from that group?

**Answer:** No. Send permissions and group membership are separate concepts.

**Q6.** Does a read-only viewer need `sendToGroup`?

**Answer:** No. Servers can publish to the group; viewers only need active membership in the authorized group.

**Q7.** Should browsers hold the Web PubSub service connection string?

**Answer:** Never. Service keys/connection strings belong on backends or in secret managers; frontends receive scoped client access URLs.

**Q8.** Why shouldn't clients pass `userId` to the negotiate API?

**Answer:** Users could impersonate others to mint unauthorized tokens/roles; `userId` must come from a verified principal.

**Q9.** Are hard-to-guess group names enough for security?

**Answer:** No. Group names are not secrets; enforce roles and server-side authorization.

**Q10.** Alice holds a role for group A and edits JS to join group B. What should happen?

**Answer:** Service/backend denies it because her token lacks scoped permission for B.

**Q11.** An agent is removed from a group while still holding a join role. What is the risk?

**Answer:** The agent can immediately rejoin; revoke permissions or close affected connections per design.

**Q12.** Does token expiration guarantee all live WebSockets close immediately?

**Answer:** Never assume that. Implement proactive revocation and connection closure when access changes.

**Q13.** Why must clients rejoin groups after reconnecting?

**Answer:** The old connection ended, and the new connection starts with a new ID and empty membership state.

**Q14.** A user has two tabs, with only Tab 1 in the group; does send-to-group reach Tab 2?

**Answer:** No. Membership is per-connection/topology; verify exact semantics if using user-level APIs.

**Q15.** Does a backend send-to-group success mean the user read the message?

**Answer:** No. You need application-level read receipts or API/status stores.

**Q16.** When a user is offline, does Web PubSub queue all group messages for later replay?

**Answer:** Never treat it as a durable queue. Use a persistent notification store and a catch-up API.

**Q17.** Can a Redis cache be the sole authority for room permissions?

**Answer:** No. Permission caches rely on TTLs/invalidation and never replace authoritative policies.

**Q18.** Why must permission cache keys include the tenant ID?

**Answer:** To prevent permission collisions across users or rooms sharing identical IDs in different tenants.

**Q19.** When WebSocket join ACKs succeed yet no messages arrive, what should you inspect?

**Answer:** Hub/group names, publish timing, active membership, publisher scope, client parsing, and socket health.

**Q20.** Should you broadcast hub-wide if a group lookup fails?

**Answer:** Never. That risks leaking private data to unauthorized users.

**Q21.** Do Web PubSub group permissions apply automatically to SignalR Hub methods?

**Answer:** No. SignalR uses its own Hub/Groups and framework authorization model.

**Q22.** Does Azure RBAC Contributor determine which orders a buyer can view?

**Answer:** No. Azure RBAC governs Azure resources/data planes; application authorization validates business records.

**Q23.** Does a Private Endpoint authorize a client lacking group roles?

**Answer:** No. Network reachability and authorization are independent layers.

**Q24.** How can a 10,000-connection group amplify outbound costs?

**Answer:** One send fans out into up to 10,000 deliveries; estimate recipients, payload sizes, tier limits, and real billing meters.

**Q25.** If Order version 11 arrives after version 12, what should the frontend do?

**Answer:** Never overwrite newer state with older data; enforce version/event ID guards and refresh authoritative state when needed.

**Q26.** Why shouldn't disconnect events serve as absolute proof of presence?

**Answer:** Networks and event pipelines incur lag, and events can arrive late or duplicate; combine TTLs, heartbeats, and reconciliation.

**Q27.** If a client holds `sendToGroup`, can the backend skip validating business commands?

**Answer:** No. Web PubSub roles only gate protocol sends; business logic must still validate, authenticate, and authorize commands.

**Q28.** Why does having multiple devices per user complicate revocation?

**Answer:** You must act across all active connections or use appropriate user-level operations, not just one tab's `connectionId`.

**Q29.** What signals point to a reconnect storm?

**Answer:** Sharp spikes in new connections, negotiate requests, join operations, backend CPU/latency, and authorization lookups.

**Q30.** What is the minimum acceptance bar for multi-tenant group permissions?

**Answer:** Authorized users receive room alerts; cross-tenant joins fail; read-only viewers cannot send; reconnects and revocations are tested; zero access URLs or private data leak.

**Summary:** **Client authorization and connection group management** in Azure Web PubSub combine **application authentication, scoped client roles, server-authorized membership, and WebSocket lifecycle control**. Groups are not authorization mechanisms on their own, connections are not users, ACKs are not read receipts, and real-time delivery is not message persistence. A secure system **blocks cross-tenant joins/sends, revokes active access, re-authorizes after reconnects, broadcasts strictly to intended targets, and monitors errors, quotas, and costs**. Similar server-side authorization principles apply to **Azure SignalR Service**, though its APIs and permission model differ from Web PubSub.
