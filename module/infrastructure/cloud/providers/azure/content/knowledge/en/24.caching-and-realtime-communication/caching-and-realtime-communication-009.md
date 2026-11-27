# Integrating Java Backends with Real-time Services

An order management platform built with **Java Spring Boot** exposes APIs to place orders, approve payments, and track shipment status. When status changes, customers expect the web page to update immediately without reloading or polling a REST API every second. Likewise, operations dashboards need real-time alerts, customer support requires two-way chat, and collaborative tools must broadcast events across open browsers.

**Azure Web PubSub** lets backends push messages to clients over persistent WebSocket connections without self-managing thousands of WebSocket servers and fan-out infrastructure. With **Azure SignalR Service**, integration centers on SignalR hubs and the ASP.NET Core ecosystem. Java backends can participate in real-time architectures too, provided you select the right protocol/service instead of assuming a Java SignalR client library turns into a SignalR hub server.

This lesson belongs to the **Caching and Real-time Communication** chapter of the **CLOUD_PROVIDERS_AZURE** module. The module explores the Microsoft Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute, storage, and data, while teaching deployment, monitoring, security, and cost control for application architectures. Here the focus is **integrating Java backends with Azure real-time services**, designing event flows from business mutations to WebSocket sockets, protecting subscription/connection credentials, handling disconnects, and operating at scale.

Examples center on **Azure Web PubSub Service and Java/Spring Boot**. Azure SDK APIs evolve across versions; check SDK docs and pin dependencies before production builds. Examples use synthetic resources, users, and tenants and do not require provisioning or modifying Azure production environments.

## 1. Learning objectives

After this lesson, you will be able to:

- Distinguish **HTTP request-response**, **WebSockets**, **Server-Sent Events**, **polling**, and **message brokers**.
- Choose the right tool among **Azure Web PubSub**, **Azure SignalR Service**, **Azure Service Bus/Event Hubs**, and cache Pub/Sub.
- Explain **hub, client connection, connectionId, userId, group, service endpoint, negotiation endpoint, and event handler**.
- Design a Spring Boot backend that reads verified identities, issues **short-lived client access tokens/URLs**, and targets notifications to the right user/group.
- Distinguish **server-to-client messaging** from **client-to-server messaging** and know when an upstream event handler is needed.
- Use the Azure Java SDK to manage service clients, publish messages, and handle responses/errors.
- Enforce **group join/send permissions** by tenant, never letting clients choose arbitrary `userId` or roles.
- Understand real-time delivery limits: disconnects, retries, duplicate events, ordering, and state resynchronization.
- Apply **transactional outbox + Service Bus/workers** when database writes and notifications require high reliability.
- Design deployments, secrets/managed identities, Private Link/networking, logs, metrics, load tests, and cost estimates.
- Troubleshoot 401/403 errors, WebSocket handshakes, lost messages, hot groups, throttling, and dropped connections.

## 2. What does "real-time" mean?

In a traditional web app:

~~~text
Browser -- HTTP GET /orders/123 --> Java REST API
Browser <-- JSON order status --- Java REST API

5 seconds later:
Browser -- HTTP GET /orders/123 --> Java REST API
~~~

**Polling** means the client asks again on a fixed interval. It is simple and proxy-friendly, yet wastes requests when nothing changed and adds worst-case latency equal to the polling interval.

With real-time communication:

~~~text
Browser -- HTTPS negotiate --> Java REST API
Browser <-- connection URL/token -- Java REST API

Browser ====== WebSocket =====> Azure Web PubSub
                                  ^
                                  | Send notification
                           Java backend / worker
                                  ^
                                  |
                           Business state change
~~~

The browser holds a long-lived WebSocket connection; when an event occurs, the backend pushes an alert through Web PubSub. This **server push** model slashes perceived latency, yet **does not guarantee every message reaches the client** if the client is offline or the network drops.

### "Real-time" terms that often mislead

| Term | Meaning |
|---|---|
| **Low-latency delivery** | Minimizes time from event occurrence to client receipt |
| **Live connection** | Client and service keep an open WebSocket session |
| **Reliable event processing** | Retries, durability, DLQs, and replayability; never automatic from WebSockets alone |
| **Exactly-once business effect** | Prevents duplicate business side effects; requires idempotency/transaction design |
| **Strong consistency** | Reads freshest state per source consistency rules; never guaranteed by push alone |

The realistic goal is **fast UI updates** paired with **clean reconnect and state resync**—never promise fixed sub-millisecond delivery across all networks and traffic spikes.

## 3. Choosing a protocol: WebSocket, SSE, long polling

| Protocol | Data flow | Advantages | Typical limits |
|---|---|---|---|
| **HTTP polling** | Client queries on an interval | Simple, easy to cache/debug | Wasted requests, interval-bound lag |
| **Long polling** | Server holds HTTP request until data or timeout | Easy HTTP integration | Managing held requests, timeouts, and reconnects |
| **SSE (Server-Sent Events)** | Server → client HTTP stream | Clean one-way notifications; native browser `EventSource` | No binary or two-way channel like WebSockets |
| **WebSocket** | Bidirectional over a persistent connection | Chat, alerts, presence, collaborative UIs | Proxies/firewalls, lifecycle, auth/reconnect, scaling |
| **Broker / event stream** | Producer → broker → consumers | Durability, retries, service decoupling | Does not replace browser WebSocket delivery |

If an app only displays batch progress every 30 seconds, polling or SSE may suffice. For multi-user fan-out, group chat, or two-way signaling, WebSockets backed by a managed service usually fit better.

**WebSockets are neither a database nor a durable queue.** A message accepted by the service does not guarantee the client displayed or saved it.

## 4. Comparing related Azure services

| Service | Typical role | When a Java backend should use it |
|---|---|---|
| **Azure Web PubSub** | Managed WebSocket hubs, user/group/connection fan-out; server SDK & event handlers | Java/Spring Boot pushing live updates to browsers/mobile or handling WebSocket events |
| **Azure SignalR Service** | Scales SignalR hub connections; tightly bound to SignalR protocol and server model | Existing ASP.NET Core SignalR hubs, or Java acting as a compatible client |
| **Azure Service Bus** | Durable enterprise messaging, queues/topics, dead-lettering, retries | Reliable backend event processing before pushing real-time alerts |
| **Azure Event Hubs** | High-throughput telemetry/event stream ingestion | Consuming high-volume event streams, not direct browser chat sockets |
| **Azure Cache for Redis / Redis pub/sub** | Fast caching and pub/sub depending on product/tier | Caching/presence state or internal signals; never treat pub/sub as durable delivery |
| **Azure Functions** | Serverless event processing | Workers or event handlers forwarding alerts through Web PubSub |
| **Azure API Management** | API authentication, gateway, and policies | Securing REST negotiation/backend APIs; does not replace managed WebSocket hubs |

A **Java SignalR client** can connect to a SignalR hub hosted by a compatible server, yet adding a client dependency never turns Spring Boot into an ASP.NET Core SignalR hub server. When **a Java backend both emits and handles events**, **Azure Web PubSub** is usually the more direct fit for raw WebSockets and managed Pub/Sub.

In a complete architecture, services complement one another:

~~~text
Orders REST API (Java)
       |
       | Database transaction
       v
Azure SQL / Cosmos DB
       |
       | Outbox / domain event
       v
Service Bus / background worker
       |
       | Publish to connected clients
       v
Azure Web PubSub ----> Browsers / mobile clients
~~~

Here Service Bus handles durable event processing **before** WebSocket dispatch. Offline clients still need a fetch/resync path; Service Bus does not buffer notifications for disconnected browsers.

## 5. Azure Web PubSub: core building blocks

An Azure Web PubSub resource provides a service endpoint, **hubs**, client connections, and server-side APIs for publishing messages.

| Component | Description | Example |
|---|---|---|
| **Service instance** | Azure resource configured with SKU, region, network, keys, and identity | `webpubsub-commerce-dev` |
| **Hub** | Application logical namespace isolating connections and messages | `orders` |
| **Connection** | A WebSocket session with a `connectionId` | Browser tab A |
| **User ID** | Identity assigned by trusted server when issuing client tokens | `user-278` |
| **Group** | Connection subset for targeted fan-out | `tenant-a-orders` |
| **Client access token** | Temporary credential to connect to a hub | Token returned from backend negotiate |
| **Service client** | Server-side SDK/REST identity to send messages and manage groups | Java `WebPubSubServiceClient` |
| **Event handler** | Backend endpoint handling configured upstream events | `/webpubsub/events` |
| **Role / permission** | Client permission to join/leave or send to groups per model | `webpubsub.joinLeaveGroup.group-name` |

### A hub is not a database or schema

A hub like **`orders`** is a logical real-time namespace. Real order records stay in Azure SQL or Cosmos DB. Never infer that a client connected to a hub owns every business resource in the backend.

### Users and connections are not 1-to-1

One user can open three tabs or sign in from both phone and desktop:

~~~text
userId = user-278
   |
   +-- connectionId c-101  (browser tab 1)
   +-- connectionId c-102  (browser tab 2)
   +-- connectionId c-103  (mobile)
~~~

**Send to user** routes across all connections mapped to that user per service behavior. **Send to connection** targets one specific socket. **Send to group** targets active group members, and group membership can vary per connection.

## 6. Designing order notifications with a Java backend

Consider three roles:

- **Customer:** views only their own orders.
- **Merchant:** views orders belonging to their authorized store/tenant.
- **Operator:** monitors authorized operations dashboards.

A clean architecture:

~~~mermaid
flowchart LR
    B[Browser / Mobile] -->|HTTPS login + negotiate| A[Spring Boot API]
    A -->|Authn + tenant authz| DB[(Azure SQL / Cosmos DB)]
    A -->|Outbox event| Q[Service Bus]
    Q --> W[Java notification worker]
    W -->|Service SDK: sendToGroup / sendToUser| P[Azure Web PubSub]
    B <-->|WebSocket| P
    B -->|REST resync after reconnect| A
~~~

Steps:

1. Client signs in using the app's auth flow (e.g., OIDC/Entra).
2. Client calls **`POST /api/realtime/negotiate`** with a backend-verified session/JWT.
3. Backend extracts **`userId`** and **`tenantId`** from trusted claims and builds scoped connection permissions.
4. Backend returns a short-lived WebSocket URL and access token.
5. Client connects directly to Azure Web PubSub.
6. When an order updates and its DB transaction commits, the system emits a domain event.
7. A worker uses the Web PubSub server SDK to send notifications to authorized users/groups.
8. Client updates the UI or calls the REST API to fetch the latest authoritative state.

**Never emit `orderCreated` or `paid` before the database transaction commits** if the UI would display nonexistent state. For high reliability, use an outbox so crashes after commit never drop publishes.

## 7. Designing the message contract before writing WebSocket code

Never push raw database entities over WebSockets. Design a **small, stable, non-sensitive** event payload:

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt-6b9a",
  "type": "ORDER_STATUS_CHANGED",
  "tenantId": "tenant-a",
  "orderId": "order-102",
  "status": "SHIPPED",
  "occurredAt": "2026-11-20T10:20:00Z",
  "resourceVersion": 37
}
~~~

| Field | Purpose |
|---|---|
| **schemaVersion** | Producer/consumer schema compatibility |
| **eventId** | Deduplication key when needed |
| **type** | Event classification |
| **tenantId / orderId** | Resource identifiers requiring authorization |
| **status** | Display-safe state fields only |
| **occurredAt** | Event timestamp in UTC |
| **resourceVersion** | Lets clients detect versions and whether a refetch is needed |

### Notifications vs authoritative data sources

WebSocket events typically act as **change hints**, while backend REST APIs/databases remain the **source of truth**. Upon receiving `ORDER_STATUS_CHANGED`, clients can call **`GET /orders/{id}`** with authorization for full fresh data.

Benefits:

- Keeps PII and secrets off broad group broadcasts.
- Allows clean client recovery after reconnects.
- Keeps message schemas lean and versioned.
- Shields the UI from internal database schema churn.

An `eventId` **does not deduplicate automatically**: clients and servers must track or verify `eventId`/`resourceVersion` per idempotency rules.

## 8. Organizing hubs, users, and groups by tenant

In multi-tenant SaaS, avoid creating a separate hub **per order** without evaluating operational limits. A clean layout:

~~~text
Hub: orders
   |
   +-- Group: tenant-a-orders
   |      +-- merchant A browser
   |      +-- merchant A dashboard
   |
   +-- Group: tenant-b-orders
          +-- merchant B browser
          +-- merchant B mobile

Send to user: user-278
  --> delivers to all connections for that user per service identity
~~~

### Authorization rules

1. Users **must never pick arbitrary `tenantId`s** when requesting group joins.
2. Backends must verify group authorization before minting roles or adding connections.
3. When access is revoked, inspect **active connections**, unexpired tokens, and group memberships.
4. Never grant **`sendToGroup`** to browsers "just to test chat" when the use case is read-only notifications.
5. Never use an **`all-users`** group for tenant- or customer-private data.

**A group name is only a routing label**, never an authorization boundary on its own. Secure systems enforce permissions and role/group issuance from trusted backend identities.

### When should connections join groups?

Two options:

- **Server-managed group membership:** backend uses server SDK/APIs to add users/connections after checking permissions.
- **Client-managed with scoped roles:** backend mints roles restricted to authorized groups so browsers can issue matching join/leave frames.

For pure **server → client** alerts, server-managed membership or user targeting shrinks client privilege. When clients must join/leave dynamically, issue tight group-scoped roles, short TTLs, and strict tenant checks.

## 9. Negotiation endpoint: bridging identity to Web PubSub

Browsers should **never** hold service keys; they call the backend for a temporary URL and token.

~~~text
Browser (authenticated)
   |
   | POST /api/realtime/negotiate
   | Authorization: Bearer <APP_ACCESS_TOKEN>
   v
Java backend
   | Validate user identity + tenant membership
   | Select hub / roles / userId
   | Mint short-lived client access token
   v
{ "url": "wss://.../client/hubs/orders?...token..." }
   |
   v
Browser establishes WebSocket to Azure Web PubSub
~~~

### Two distinct credentials

| Credential | Holder | Capabilities |
|---|---|---|
| **Service credential / managed identity** | Trusted Java backend or worker | Server-side sends, group management, and token minting |
| **Client access token** | Authenticated browser/mobile client | Connects to a hub with granted scoped roles |

**Never return service connection strings or account keys from a negotiation endpoint.** Clients receive only short-lived tokens scoped to one connection/hub without choosing their own `userId` or roles.

### Risks of tokens in WebSocket URLs

Client access URLs carry tokens in the query string per the Web PubSub protocol. Never copy full URLs into logs, analytics, screenshots, support tickets, or HTTP referrers. Require HTTPS for negotiation, WSS for WebSockets, short token TTLs, and `no-store` cache headers.

**Token expiration generally governs new connection establishment; it does not automatically terminate every already-authenticated live connection at expiry.** True revocation requires explicit disconnect or role/membership removal per Web PubSub and application design.

## 10. Rules for safe token minting

When handling a negotiation request, the backend should:

1. Require authentication and validate signature, issuer, audience, expiry, and required claims.
2. Derive **`userId`** server-side; ignore client-supplied user IDs.
3. Load tenant/resource memberships from an authoritative source.
4. Select the hub from server-side configuration.
5. Mint tokens with a **short TTL** and minimal roles/groups.
6. Omit group-send roles for read-only listeners.
7. Set **`Cache-Control: no-store`** on the response.
8. Rate-limit negotiation per user/IP at the API gateway.
9. Log safe user references, correlation IDs, and outcomes—never the token.
10. Test that User A's token cannot join Tenant B's groups.

### Why never mint tokens in the frontend?

Signing client tokens in the browser would require shipping signing keys or service secrets into public code, letting any user mint arbitrary privileges. **Tokens must be minted exclusively by a trusted backend** or a properly configured service-supported auth mechanism.

### Tokens across multiple tabs

A single user can request multiple tokens for separate tabs/connections. Bound per-user connection counts if needed, yet never assume one user holds at most one WebSocket session.

## 11. Preparing Spring Boot and the Azure Java SDK

Lab stack:

~~~text
Java 17 or JDK version supported by your project and SDK
Spring Boot Web / Spring Security
Azure Web PubSub server SDK (Java)
Azure Identity SDK if using managed identity
Orders REST API + notification service
Browser WebSocket client / JavaScript
~~~

With Maven, declare **tested, compatible dependency versions**, such as:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
  </dependency>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-messaging-webpubsub</artifactId>
    <version>AZURE_WEBPUBSUB_SDK_VERSION</version>
  </dependency>
</dependencies>
~~~

This is a **`pom.xml` excerpt**, not a full buildable Maven project: you still need the Spring Boot BOM/parent, compiler settings, and production libraries. Replace **`AZURE_WEBPUBSUB_SDK_VERSION`** with a supported, tested release—never copy the placeholder literally expecting Maven to build. Verify SDK models and method signatures against your pinned version.

When using managed identity via `TokenCredential`, add **`azure-identity`**:

~~~xml
<dependency>
  <groupId>com.azure</groupId>
  <artifactId>azure-identity</artifactId>
  <version>AZURE_IDENTITY_VERSION</version>
</dependency>
~~~

**Never confuse the Java server SDK for publishing messages with a browser client SDK for opening WebSockets.** Each side holds completely different credentials and responsibilities.

## 12. Configuring the Web PubSub service client in Java

In a **lab** using a secret-store connection string, create and reuse the server SDK client as a singleton bean:

~~~java
package com.example.realtime;

import com.azure.messaging.webpubsub.WebPubSubServiceClient;
import com.azure.messaging.webpubsub.WebPubSubServiceClientBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class WebPubSubConfiguration {

    @Bean
    WebPubSubServiceClient webPubSubServiceClient(
            @Value("#{environment.getRequiredProperty('webpubsub.connection-string')}")
                String connectionString,
            @Value("#{environment.getProperty('webpubsub.hub', 'orders')}")
                String hubName) {
        return new WebPubSubServiceClientBuilder()
            .connectionString(connectionString)
            .hub(hubName)
            .buildClient();
    }
}
~~~

`WebPubSubServiceClientBuilder`, `connectionString`, `hub`, and `buildClient` follow the Azure Web PubSub Java server SDK pattern; verify exact signatures and transitive dependencies for your pinned SDK version. Never instantiate a new service client per HTTP request. Across multiple pods/instances, each backend instance holds its own reusable client targeting the shared Azure Web PubSub resource/hub.

### Illustrative `application.yml`

~~~yaml
webpubsub:
  hub: orders
  connection-string: ${WEBPUBSUB_CONNECTION_STRING}

spring:
  application:
    name: orders-backend
~~~

**`WEBPUBSUB_CONNECTION_STRING`** must come from secure app settings or a secret store, never committed to Git. In production, prefer **Microsoft Entra ID / managed identity** with data-plane RBAC where supported by your Web PubSub SDK and tier—configuring endpoint + `TokenCredential` per your pinned SDK rather than mixing service keys and managed identity casually.

### Service connection strings are high-sensitivity secrets

If a service key leaks, anyone holding it may exercise broad control over the service depending on policy. On a leak:

1. Assess the scope of compromised keys and services.
2. Rotate/revoke keys carefully without knocking offline backends down simultaneously.
3. Migrate credentials to Key Vault or managed identity.
4. Audit logs and recent access events.
5. Never merely remove a key from Git history—treat it as compromised and rotate it.

## 13. Java Spring Boot: negotiation controller

A sound negotiation endpoint must be **guarded by Spring Security** and trust only verified principals:

~~~java
package com.example.realtime;

import com.azure.messaging.webpubsub.WebPubSubServiceClient;
import com.azure.messaging.webpubsub.models.GetClientAccessTokenOptions;
import com.azure.messaging.webpubsub.models.WebPubSubClientAccessToken;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/realtime")
public class NegotiationController {
    private final WebPubSubServiceClient serviceClient;

    public NegotiationController(WebPubSubServiceClient serviceClient) {
        this.serviceClient = serviceClient;
    }

    public record NegotiationResponse(String url) {}

    @PostMapping("/negotiate")
    public ResponseEntity<NegotiationResponse> negotiate(
            Authentication authentication) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return ResponseEntity.status(401).build();
        }

        // Minimal example: principal authenticated by Spring Security.
        // Production must bind tenant and per-resource permissions.
        String trustedUserId = authentication.getName();

        GetClientAccessTokenOptions options =
            new GetClientAccessTokenOptions()
                .setUserId(trustedUserId);

        WebPubSubClientAccessToken token =
            serviceClient.getClientAccessToken(options);

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(new NegotiationResponse(token.getUrl()));
    }
}
~~~

**Executability note:** this illustrates Spring Boot 3 / Java 17+ and Azure Web PubSub SDK models; pin exact versions and verify package/method signatures of **`WebPubSubClientAccessToken`**. It omits the `SecurityFilterChain`, issuer/audience checks, and tenant authorization, so **do not treat it as a complete production endpoint**.

### Production additions required

- Block unauthenticated requests in `SecurityFilterChain`.
- For Bearer JWTs, verify **issuer, audience, signature, expiry**, and scopes—never decode JWTs without verifying signatures.
- Namespace `userId` consistently by system/tenant; if principal names are emails, prefer internal opaque IDs.
- Verify the user still belongs to the tenant/team and is authorized for orders.
- Bound token TTL per SDK support; never mint long-lived browser tokens.
- Rate-limit login/negotiation and enforce origin/CSRF checks when using cookies.
- Verify service role assignments and ensure logs never capture URLs or tokens.
- Omit group-send roles for notification-only clients.

### What if the client sends `tenantId`?

If the API receives:

~~~json
{"tenantId": "tenant-b", "group": "tenant-b-orders"}
~~~

treat it strictly as **untrusted input**. The backend must confirm the authenticated principal actually holds rights to `tenant-b` before minting tokens, assigning groups, or registering memberships. Never pass request fields directly as `userId` or roles.

## 14. Java backend pushing events to clients

For a non-sensitive system-wide announcement, the server SDK can publish to **all connections in a hub**:

~~~java
package com.example.realtime;

import com.azure.messaging.webpubsub.WebPubSubServiceClient;
import com.azure.messaging.webpubsub.models.WebPubSubContentType;
import org.springframework.stereotype.Service;

@Service
public class LiveAnnouncementService {
    private final WebPubSubServiceClient client;

    public LiveAnnouncementService(WebPubSubServiceClient client) {
        this.client = client;
    }

    public void announceMaintenance() {
        client.sendToAll(
            "Scheduled maintenance starts in 15 minutes.",
            WebPubSubContentType.TEXT_PLAIN
        );
    }
}
~~~

This illustrates **`sendToAll`**. Never send account balances, customer addresses, order details, or tenant-specific updates via **`sendToAll`**, because it reaches the entire hub.

### Targeting users or groups

In production, backends need **targeted delivery**:

~~~text
OrderStatusChanged(tenant-a, order-102)
    |
    +-- Notify user: tenant-a:user-278
    |
    +-- Notify group: tenant-a-orders
~~~

The Azure Web PubSub server SDK supports **user, group, and connection** operations depending on version. Always check method signatures for **`sendToUser`**, **`sendToGroup`**, **`addUserToGroup`**, **`removeUserFromGroup`**, or equivalents in your SDK docs rather than assuming identical parameter order across languages.

**Business workflow before sending**:

1. Confirm the event comes from a trusted server source.
2. Read `tenantId`, `orderId`, `resourceVersion`, and `eventId`.
3. Verify the target recipient/group is authorized.
4. Serialize the JSON payload matching the schema version.
5. Send via the server SDK and emit PII/secret-free metrics.
6. If publishing fails, let the worker/outbox retry per policy—never roll back committed DB state.

**A publish error after DB commit** must never be "fixed" by re-running the entire order-creation transaction if that risks duplicate orders or charges.

## 15. Browser creating a WebSocket session

After signing in, the browser calls the protected negotiation endpoint and opens the returned WebSocket URL:

~~~javascript
async function connectNotifications() {
  const res = await fetch("/api/realtime/negotiate", {
    method: "POST",
    credentials: "include",
    headers: {
      "Accept": "application/json"
    }
  });

  if (!res.ok) {
    throw new Error("Negotiation failed with HTTP " + res.status);
  }

  const payload = await res.json();
  const socket = new WebSocket(
    payload.url,
    "json.webpubsub.azure.v1"
  );

  socket.addEventListener("open", () => {
    console.info("Realtime connection established");
  });

  socket.addEventListener("message", (event) => {
    // May receive system/ack messages as well as application events.
    let frame;
    try {
      frame = JSON.parse(event.data);
    } catch {
      console.warn("Unknown message format");
      return;
    }
    handleRealtimeFrame(frame);
  });

  socket.addEventListener("close", () => {
    console.warn("Realtime disconnected; schedule reconnect");
  });

  socket.addEventListener("error", () => {
    console.warn("WebSocket error");
  });

  return socket;
}

function handleRealtimeFrame(frame) {
  if (frame.type !== "message") return;

  // Validate payload/schema to avoid rendering untrusted data.
  const data = frame.data;
  if (data?.type === "ORDER_STATUS_CHANGED") {
    // Typically call an authorized REST API to fetch fresh state.
    console.info("Order changed; refresh affected resource.");
  }
}
~~~

This browser snippet uses the **Web PubSub JSON subprotocol**. Confirm frame/payload shapes against your subprotocol, `dataType`, and client SDK. Raw WebSockets without this subprotocol frame messages differently. With the Web PubSub JSON protocol, **`type = message`** is only one frame type; handle **`system`/`ack`** frames as needed.

### Don't forget negotiation auth

`credentials: "include"` suits same-origin cookie sessions paired with CSRF protection. With Bearer access tokens, send the app token to **backend negotiation** via the `Authorization` header per security policy—**never copy the service key** into browser code.

### Real-world disconnects

Mobile apps switch networks, browser tabs suspend, proxies reap idle sockets, and user sessions expire. Apps must:

- Reconnect using capped **exponential backoff + jitter**.
- Re-call negotiation when a fresh token URL is required.
- Stop blind reconnect loops when the backend returns 401/403.
- Upon reconnecting, call **`GET /orders?updatedSince=...`** or fetch the latest snapshot to close gaps.
- Show a "reconnecting" indicator in the UI and fall back cleanly to polling when appropriate.

**Opening a WebSocket successfully does not prove a user will never miss events across reconnects.**

## 16. Reconnect, backoff, and state resynchronization

Client state diagram:

~~~mermaid
stateDiagram-v2
    [*] --> Disconnected
    Disconnected --> Negotiating: authenticated request
    Negotiating --> Connected: WebSocket opens
    Negotiating --> RetryWait: transient error
    Connected --> RetryWait: close/error
    RetryWait --> Negotiating: backoff expired
    Connected --> Resyncing: after successful reconnect
    Resyncing --> Connected: REST snapshot caught up
    Negotiating --> SignedOut: 401/403 or logout
    SignedOut --> [*]
~~~

Illustrative pseudocode, **not production-complete JavaScript**:

~~~text
attempt = 0
when websocket closes unexpectedly:
    while signedIn and not connected:
        delay = min(MAX_DELAY, BASE_DELAY * 2^attempt)
        sleep(delay + random jitter)
        request fresh negotiated URL
        try connect
        if connected:
            GET authorized REST snapshot since last resourceVersion
            attempt = 0
            break
        if auth failed permanently:
            stop and ask for sign-in
        attempt++
~~~

### UI state must never depend on a single event

Suppose the client last received `resourceVersion` **37**, dropped offline while versions 38 and 39 were emitted, and then reconnected. It may never receive 38/39 over Web PubSub. The client should:

1. Query the REST snapshot for the current order version.
2. Update local state/cache to authoritative truth.
3. If the server exposes durable event history, replay via cursor within authorized bounds.
4. Never trust a WebSocket stream alone as a durable event log.

**`resourceVersion`** detects stale/duplicate frames and gaps, provided the backend increments versions consistently inside transactions.

## 17. Comparing broadcast, user, and group messaging

| Send type | Recipients | When to use | Risk |
|---|---|---|---|
| **`sendToAll`** | All connections in hub | Global maintenance notices | Leaks private data if misused |
| **`sendToUser`** | Connections matching `userId` | Personal user alerts | Bad `userId` mapping; multi-tab behavior |
| **`sendToGroup`** | Connections in a group | Merchant dashboards, chat rooms | Broken group membership / tenant isolation |
| **`sendToConnection`** | One specific socket | Targeted ACK or limited diagnostics | Socket may drop; ID changes on reconnect |

### Group selection example

Merchant A in `tenant-a`:

~~~text
userId = tenant-a:user-278
group  = tenant-a:merchant:orders
~~~

Merchant B in `tenant-b`:

~~~text
userId = tenant-b:user-512
group  = tenant-b:merchant:orders
~~~

If an event belongs to a `tenant-a` order, publishing it to `tenant-b`'s group is a **critical authorization breach**, even if the payload contains only `orderId`.

### Never assume group membership lasts forever

WebSocket connections and memberships are ephemeral. On disconnect/reconnect, re-evaluate users and groups per service semantics and current permissions. Never treat Web PubSub group membership as your organization's authoritative membership database.

## 18. Client-to-server events and upstream event handlers

Not every app needs only server push. Chat and collaborative editing often require browsers to send messages to the backend.

Azure Web PubSub supports configuring **event handler endpoints** so the service forwards select **system/user events** upstream to your backend per supported protocols.

~~~text
Browser
   |
   | WebSocket message / client event
   v
Azure Web PubSub
   |
   | Upstream webhook / CloudEvents-style request
   v
Java event handler endpoint
   |
   +-- Validate event origin / signature or configured auth
   +-- Validate user permission and payload
   +-- Execute domain command / persist / publish
   |
   v
Azure Web PubSub service API -> client groups/users
~~~

### Events to understand

- **Connect events:** participate in approving connections and setting identity/metadata depending on handler setup.
- **Connected / disconnected events:** aid presence/diagnostics; verify lifecycle guarantees.
- **User events:** custom client messages routed upstream.
- **Service-side messages:** Java workers publish via the server SDK without needing user event handlers.

**Never treat JSON arriving at an event handler as a trusted business command** merely because Web PubSub called the webhook. Verify caller origin, user permissions, schemas, resource IDs, and payload limits.

### Event handlers are optional

If your app only pushes order updates from backend to browser, **you do not need an upstream event handler**. Use negotiation + the server SDK send APIs. Add event handlers only when client-to-server flows, custom connect hooks, or backend orchestration require them.

## 19. Securing and verifying Web PubSub event handlers

A public event endpoint can receive spoofed HTTP POSTs from attackers. When configuring upstream webhooks, the service uses CloudEvents metadata and **origin validation / abuse-protection handshakes**.

Verification checklist:

1. Dedicate a specific endpoint path solely to Web PubSub events.
2. Apply **validation supported by Azure Web PubSub** in the Java SDK or matching library—never rely on comparing an unverified custom header.
3. Validate event type, hub, `userId`/`connectionId`, and payload schema.
4. Reject oversized payloads, malformed JSON, and unexpected operations.
5. Execute commands only after mapping the connection/principal to a valid identity and tenant.
6. Set timeouts, retries, and idempotency since upstream calls can retry.
7. Log `eventId`/correlation IDs—never access tokens or raw personal payloads.

### Abuse-protection handshake

When registering an upstream URL on Web PubSub event handlers, Azure sends a **validation request** with headers such as **`WebHook-Request-Origin`**, expecting **`WebHook-Allowed-Origin`** in supported validation flows. This proves **URL ownership**—it does not replace signature, origin, or authorization verification for subsequent business events.

**Never write a Spring Controller returning 200 for every POST under `/events`** assuming that validates Web PubSub. Follow the Web PubSub event handler docs and your chosen SDK version for CloudEvents validation, and restrict upstream endpoints via private networking where supported.

## 20. Java event handler: application layering

A reliable event handler separates HTTP transport adaptation from domain services:

~~~text
WebPubSub upstream callback
        |
        v
HTTP adapter / protocol validator
        |
        v
Identity + tenant authorization
        |
        v
Command validation
        |
        v
Application service (Java)
        |
        +--> Azure SQL/Cosmos DB transaction
        +--> Outbox event
        |
        v
Response / acknowledgement per Web PubSub event contract
~~~

Java pseudocode example:

~~~java
public void onClientCommand(VerifiedWebPubSubEvent event) {
    // VerifiedWebPubSubEvent is an internal DTO created after
    // protocol/origin verification, NOT an Azure SDK class.
    String userId = event.trustedUserId();
    String tenantId = event.trustedTenantId();

    if (!permissions.canUpdateOrder(userId, tenantId,
                                     event.orderId())) {
        throw new AccessDeniedException("Not authorized");
    }

    commands.updateOrder(event.orderId(), event.requestedStatus());
    // Domain event is persisted via outbox; worker publishes post-commit.
}
~~~

This is **application-layer pseudocode**; add real DTOs, services, exception imports, transaction boundaries, validation, and protocol responses. **Do not try to import `VerifiedWebPubSubEvent` from the SDK**: it is a custom placeholder emphasizing that business logic must receive only verified events.

### Why shouldn't browsers push status changes straight to groups?

Having permission to send a WebSocket frame to a group **does not grant permission** to mutate order status in the database. Business state changes must pass through authorized APIs/command handlers with concurrency control, transactions, and auditing.

## 21. Transactional outbox: preventing lost alerts after DB commit

A classic anti-pattern:

~~~text
HTTP POST /orders/123/confirm
   |
   +-- UPDATE orders SET status='CONFIRMED'
   +-- COMMIT succeeds
   +-- Send Web PubSub notification  <-- Network timeout!
   |
   v
API updated state, yet browser receives no notification
~~~

Publishing **before commit** risks emitting events for transactions that later roll back, showing phantom state in the UI. Publishing **after commit** without durability loses notifications on transient failures.

### Transactional outbox pattern

~~~text
Java Orders API
    |
    | Database transaction
    +---- UPDATE Orders
    +---- INSERT OutboxEvents
    | COMMIT both atomically
    v
Database
    |
    | Poller / CDC / event bridge
    v
Service Bus (durable message)
    |
    v
Java notification worker
    |
    | Web PubSub SDK send
    v
Connected browsers
~~~

**Writing the outbox row and the order mutation in one database transaction** closes the gap between state persistence and event emission. Workers still require retries, ordering, idempotency, and duplicate handling; an outbox **does not** create exactly-once client delivery.

### Illustrative Java transactional service

~~~java
@Service
public class OrderApplicationService {
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public OrderApplicationService(
            OrderRepository orders, OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void confirmOrder(
            String trustedTenantId, String orderId) {
        Order order = orders.findAuthorizedOrder(
            trustedTenantId, orderId
        );

        order.confirm();
        orders.save(order);

        outbox.save(OutboxEvent.orderStatusChanged(
            trustedTenantId, orderId,
            order.getVersion(), "CONFIRMED"
        ));
    }
}
~~~

**This is an architectural skeleton**, not standalone compilable code; supply imports, repository implementations, transaction managers, entities/schemas, and error handling. With Cosmos DB, transactions and batches must respect **logical partition** boundaries and SDK transactional batch APIs—never assume JPA `@Transactional` automatically spans Cosmos DB partitions.

### What should the worker do?

1. Receive/poll events from the outbox or Service Bus.
2. Validate schema, tenant, `eventId`, and `resourceVersion`.
3. Resolve authorized recipients/groups from trusted state.
4. Send the Web PubSub message.
5. Mark the event complete only after the service API accepts the send per contract.
6. On transient errors, retry with backoff; on severe config/permission errors, alert or dead-letter.
7. Use idempotency to avoid duplicate side effects if an event replays.

Never delete a newly written outbox record just because an HTTP response to the caller failed; manage outbox state independently per runbook.

## 22. Delivery semantics: sent does not mean received

A managed WebSocket service can confirm a **server API request** succeeded while:

- The user disconnected just before the packet arrived.
- The browser received the frame and crashed before rendering/saving it.
- One user has multiple connections behaving differently across tabs.
- A worker retried the same event and sent a duplicate alert.
- A message arrived during a brief reconnect gap.

### Three distinct acknowledgment levels

| Level | Who confirms? | What it proves |
|---|---|---|
| **Backend event recorded** | Database / outbox | Notification intent is durably persisted |
| **Web PubSub service accepted send** | Service API / SDK | Service accepted the send command per API contract |
| **Application client processed event** | Browser / mobile app | UI/client code handled the event (only if explicit client ACK exists) |

**Client acknowledgments** must be built explicitly when needed: client sends an ACK with `eventId`, and the backend validates and persists it. Even with ACKs, disconnects and retries can cause duplicates, so business effects must stay idempotent.

### Event ordering

If an order transitions:

~~~text
PENDING -> CONFIRMED -> SHIPPED -> DELIVERED
~~~

multiple workers, connections, or regions can deliver frames out of order under edge conditions. Never assume Web PubSub guarantees global ordering across all users, groups, and producers.

Mitigation:

- Store a monotonically increasing **`resourceVersion`** per order.
- Clients ignore events older than their currently displayed version.
- On a version gap, fetch the REST snapshot.
- Never allow stale events to regress state backward.

For complex state transitions, backend validation remains the ultimate truth.

## 23. Presence: online/offline is an approximate signal

A chat app wants to display who is online. You can observe connection/group events and lifecycle hooks per Web PubSub capabilities.

### Watch false assumptions

- One user opens **multiple tabs and devices**.
- Disconnect callbacks can lag or drop in some failure modes.
- A live WebSocket tab does not prove a human is watching the screen.
- Going offline does not mean the backend should delete all subscriptions.
- Presence usually aggregates by `userId`, not `connectionId`.

Model:

~~~text
userId = user-278
  c-1 connected, c-2 connected -> online
  c-1 closed, c-2 connected    -> still online
  c-2 closed                   -> offline after grace period
~~~

When presence matters, combine a TTL-backed state store (such as a cache per architecture), heartbeats/lifecycle events, and reconciliation. **Redis/cache presence does not replace Web PubSub group membership**, and vice versa.

### Privacy design

Online status can be sensitive. Expose it only to authorized viewers and honor "invisible" or privacy settings if required by the product.

## 24. CORS, Origin, WSS, and networking

Typical deployment topology:

~~~text
Browser/Client
   |
   | HTTPS negotiate
   v
App Service / AKS Spring Boot API
   |
   | Service SDK HTTPS, RBAC/secret
   v
Azure Web PubSub service
   ^
   | WSS over client WebSocket
Browser
~~~

Four distinct network paths:

1. **Browser → Java API:** HTTPS, CORS, and authentication for REST negotiation.
2. **Browser → Web PubSub:** WSS, client tokens, service endpoint, origin/network rules.
3. **Java API/worker → Web PubSub:** HTTPS SDK calls over server networking and identity.
4. **Web PubSub → Java event handler:** HTTPS upstream callbacks only when event handlers are configured.

### CORS is not WebSocket authorization

CORS governs browser HTTP fetch/XHR calls. WebSocket handshakes and **`Origin`** follow separate rules—verify **Web PubSub allowed origins** / equivalent settings alongside tokens. Non-browser clients can spoof any `Origin` header; **Origin checks alone never secure data**.

When an SPA runs on a different domain from the Spring Boot API:

- Allowlist explicit origins—never combine wildcards with credentialed cookies recklessly.
- Enforce CSRF protection for cookie-based sessions.
- Require HTTPS/WSS everywhere, never plain HTTP.
- Test redirects, `SameSite` cookie attributes, and token acquisition.

### Private Endpoints and client paths

When your service/region/SKU supports **Private Endpoints** or public network restrictions:

- Identify whether browsers sit on the public Internet or inside a VNet/VPN.
- An internal backend Private Endpoint does not let public Internet browsers reach a private-only endpoint.
- Check Private DNS zones, routes, firewalls/proxies, and certificate hostnames.
- If public browsers need WebSockets, preserve a valid public client path by design.

**Never disable public network access on a service serving public browsers before verifying the full connectivity architecture.** One firewall toggle can sever thousands of live WebSockets.

## 25. Managed identity, Azure RBAC, and Key Vault

Two common credential approaches for Java backends:

| Option | Pros | Caveats |
|---|---|---|
| **Connection string / service key** | Easy in labs; broad SDK compatibility | Long-lived secret requiring storage and rotation |
| **Microsoft Entra ID / managed identity** | Eliminates static secrets; principal-level audits; least privilege | Requires SKU/API/SDK support, data-plane roles, network access |

### Production recommendations

1. Enable managed identity on App Service / AKS workloads appropriately.
2. Assign the least-privilege **Web PubSub data-plane role** for sending messages and minting tokens.
3. Configure the SDK with endpoint + `TokenCredential` where supported by your Java SDK version.
4. When keys are still required, keep them in Key Vault via secret references.
5. Separate identities for the **REST API**, **notification worker**, and **infra provisioning** when needed.
6. Test roles using the real runtime identity—never debug as Owner and forget to drop privileges.

**Azure Contributor on a resource group does not authorize an application identity to send/receive messages on the Web PubSub data plane.** Keep management-plane and data-plane RBAC distinct.

### AKS Workload Identity note

On AKS, use **Microsoft Entra Workload ID** with Kubernetes service-account federation rather than injecting a shared service principal secret across every pod. Verify `azure-identity`/SDK compatibility, token audiences, and role assignments.

### Key rotation

When rotating service keys:

- Inventory all backend instances and slots using the old key.
- Update Key Vault secrets and refresh/restart apps cleanly.
- Verify SDK sends and negotiations succeed.
- Revoke the old key only after every instance switches over.
- Watch for 401/403 errors, retries, and alerts.

Existing client access tokens follow their own lifecycles. **Key rotation and client disconnects** interact via token-signing behavior—test in a lab and prepare a runbook before rotating in production.

## 26. Deploying Java backends: App Service, AKS, or Functions

Azure Web PubSub complements—never replaces—your Java backend. Java backends can run on:

| Platform | Strengths | Watch out for |
|---|---|---|
| **Azure App Service** | Simple Spring Boot JAR/container hosting, managed identity, monitoring | VNet Integration, app settings, scale-out, health probes |
| **AKS** | Microservices, workload identity, autoscaling | Pod lifecycles, retries, max concurrent requests, network policies |
| **Azure Container Apps** | Container hosting and serverless-style scaling | Identity, ingress/networking, cold starts, event consumers |
| **Azure Functions (Java)** | Short-lived Service Bus/Event Grid event workers | Hosting constraints, cold starts, retries, SDK reuse |
| **Azure VM** | Full OS control | Higher patching, HA, and scaling overhead |

### Environment invariants

~~~text
DEV:
  WEBPUBSUB_HUB=orders-dev
  Web PubSub instance=dev
  Backend DB/Service Bus=dev
  Identity/RBAC=dev

STAGING:
  WEBPUBSUB_HUB=orders-staging
  Web PubSub instance=staging (or isolated per policy)
  Backend DB/Service Bus=staging
  Identity/RBAC=staging

PRODUCTION:
  WEBPUBSUB_HUB=orders
  Web PubSub instance=production
  Backend DB/Service Bus=production
  Identity/RBAC=production
~~~

**Changing only the hub name does not isolate environments** if a token/service key can access multiple hubs or staging backends read production databases/queues.

### App Service deployment workflow

1. Build the Spring Boot JAR/container once; record Git SHA and artifact digest.
2. Provision Web PubSub and networking via IaC.
3. Grant managed identity data-plane roles or configure Key Vault secrets.
4. Deploy to staging with matching hub, endpoint, and roles.
5. Smoke-test negotiation, WSS handshakes, targeted sends, and reconnects.
6. Verify multi-instance behavior and metric baselines.
7. Promote the exact same artifact to production after approval.
8. Monitor connection counts, send failures, and app errors post-rollout.

With App Service deployment slots, verify slot stickiness for **Web PubSub endpoints, secrets, and tenant data settings**—a slot swap becomes dangerous if staging starts pushing alerts to production users.

## 27. Provisioning Web PubSub via Portal and Azure CLI

In the Azure Portal:

1. Select **Azure Web PubSub** in the target subscription and resource group.
2. Provision in a region close to workloads/clients meeting data residency rules.
3. Choose SKU/tier/capacity per documentation and estimates.
4. Configure network access, allowed origins, and identity/keys.
5. Configure hubs/event handlers if upstream events are needed.
6. Assign data-plane roles to the backend managed identity.
7. Record non-sensitive endpoint hostnames and resource IDs—never paste service keys into docs.

### Reading metadata with the CLI

~~~bash
az login
az account set --subscription "<LAB_SUBSCRIPTION_ID>"

RG="<LAB_RESOURCE_GROUP>"
SERVICE="<WEBPUBSUB_RESOURCE_NAME>"

az webpubsub show \
  --resource-group "$RG" \
  --name "$SERVICE" \
  --query "{name:name,location:location,sku:sku.name,hostName:hostName}" \
  --output json
~~~

This read-only command works once the **`az webpubsub`** command/extension is installed. Never run **`az webpubsub key list`** into shared logs, as it prints service keys. With Reader-only access, you can still complete the design sections without provisioning resources.

### Creating a billable lab service

**Sample command** once budget, region, and SKU are approved:

~~~bash
az webpubsub create \
  --resource-group "<LAB_RESOURCE_GROUP>" \
  --name "<UNIQUE_LAB_WEBPUBSUB_NAME>" \
  --location "<AZURE_REGION>" \
  --sku "Standard_S1"
~~~

**Do not run without checking current SKU/region availability, quotas, pricing, and lab lifetime.** CLI flags/extensions evolve across versions—check **`az webpubsub create --help`** first. Even an idle real-time resource can accrue capacity charges per tier.

## 28. Scaling, connection capacity, and backpressure

Real-time workloads behave differently from HTTP:

- **Concurrent connections:** every tab, browser, and device can hold an open socket.
- **Messages/second:** one event can fan out to thousands of sockets.
- **Payload size:** large frames amplify bandwidth and billing.
- **Hot groups:** huge groups receive rapid updates continuously.
- **Reconnection peaks:** after an outage, thousands of clients negotiate at once.
- **Regional latency:** distant users incur higher RTT.

### Rough load sizing

Assumptions:

~~~text
5,000 online users
1.5 WebSocket connections per user on average
=> 7,500 concurrent connections

100 notifications/second
80 connections per fan-out on average
=> 8,000 deliveries/second in this estimation model
~~~

These figures are a **hypothetical capacity exercise**, not official Web PubSub limits or billing units. The service meters messages and connections by its own definitions—verify current SKUs, metrics, pricing, and benchmarks.

### Worker backpressure

If every DB update triggers 1,000 Web PubSub sends, workers can overwhelm themselves. Apply:

- Batching/coalescing status updates where business rules allow.
- Bounded worker pools, queue prefetch limits, and rate controls.
- Exponential backoff with jitter for transient errors.
- No infinite retries on 401, 403, or invalid-group errors.
- Lean payloads carrying `eventId`/`resourceVersion` instead of huge aggregates.
- Dead-lettering and reconciliation for unprocessed backend messages.

Never scale AKS pods infinitely when the real bottleneck is **Web PubSub quotas, SDK throttling, networking, or the backend database**.

## 29. Metrics, logging, and alerting

Operational dashboards must cover both the **Web PubSub service** and the **Java backend**:

| Area | Signals to track | Meaning |
|---|---|---|
| WebSocket sessions | Connected/disconnected sockets, peak count | Capacity, churn, reconnect storms |
| Client traffic | Server-to-client messages, sizes, errors | Fan-out, limits, throughput |
| Service APIs | Send requests, failures, throttling/429s | SDK or service issues |
| Negotiation API | Request rate, 401/403, latency, 5xx | Auth or token-minting failures |
| Upstream callbacks | Event success/failure/latency, retries | Client command and webhook health |
| Message backlog | Service Bus depth, oldest message age, DLQ | Is the outbox worker keeping pace? |
| Client UI | Reconnect counts, time-to-first-update, resync errors | End-user experience |
| Java worker | CPU, thread pools, HTTP client stats, exceptions | Application bottlenecks |
| Security | Unusual token minting, group join denials | Credential abuse or authz gaps |
| Cost | Concurrent connections, messages, egress, logs | Budgeting and rightsizing |

Azure Monitor metrics and diagnostic categories vary by SKU, region, and service version. **Never assume every metric name in the table exists verbatim in Azure Monitor**: combine service metrics, Application Insights, and custom app telemetry to cover these signals.

### Correlation IDs

An order flow can trace:

~~~text
REST requestId
   |
   +-- DB transaction / outbox eventId
   |
   +-- Service Bus messageId
   |
   +-- Java worker attempt
   |
   +-- Web PubSub send result
   |
   +-- Client eventId/resourceVersion
~~~

This answers: "When did the order commit, did the worker receive it, did the service accept the send, and did the UI reconnect?"

**Never put raw service tokens, WebSocket URLs, or PII into correlation fields.** Log **`eventId`** and opaque user references instead.

## 30. Threat model for real-time connectivity

| Threat | Attack / failure vector | Mitigation |
|---|---|---|
| Exposed token | Client access URL leaked in logs/screenshots | Short TTL, log redaction, HTTPS/WSS |
| Exposed service key | Connection string committed to repo | Managed identity, Key Vault, rotation |
| Cross-tenant subscribe | Client passes another `tenantId`/group | Server-side tenant authz, tightly scoped group roles |
| Spoofed business event | Browser sends `ORDER_PAID` | Backend command authorization + DB transactions |
| Replay / duplicate events | Worker retries or reconnects | `eventId`/`resourceVersion`, idempotency |
| Flood / reconnect storm | Tab floods or massive reconnect bursts | Rate limits, quotas, backoff, capacity sizing |
| Backend bypass | Open internal API or unverified webhook | Private networking/identity, event validation |
| XSS | Script steals negotiation token from SPA | CSP, output encoding, browser hardening |
| Stale membership | Revoked user keeps active socket | Explicit disconnect/revalidation, short TTLs |
| Sensitive broadcast | `sendToAll` leaks order/customer data | User/group targeting, minimal payloads |

### Pre-release security tests

1. Anonymous negotiation → 401.
2. Wrong-issuer/audience or expired JWT → 401.
3. Tenant A user requests Tenant B group → 403.
4. Read-only client attempts to send to a group → denied by role.
5. Revoked user with an active socket → disconnect/revalidation verified.
6. Service key absent from source, logs, container images, and shared traces.
7. Spoofed POST to event handler → blocked before business logic.
8. Reconnect never escalates roles beyond current policy.
9. `GET /orders/{id}` still enforces tenant/resource authorization.
10. Disallowed network origins/paths are blocked per design.

## 31. Java example: pushing JSON to an order group

Unlike the **`sendToAll`** snippet in section 14, multi-tenant apps must target only backend-authorized groups:

~~~java
package com.example.realtime;

import com.azure.messaging.webpubsub.WebPubSubServiceClient;
import com.azure.messaging.webpubsub.models.WebPubSubContentType;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;

@Service
public class OrderNotificationPublisher {
    private final WebPubSubServiceClient client;
    private final ObjectMapper json;

    public OrderNotificationPublisher(
            WebPubSubServiceClient client,
            ObjectMapper json) {
        this.client = client;
        this.json = json;
    }

    record OrderNotice(
        int schemaVersion,
        String eventId,
        String type,
        String orderId,
        String status,
        long resourceVersion
    ) {}

    public void publishToTenant(
            String trustedTenantId,
            String eventId,
            String orderId,
            String status,
            long resourceVersion) throws JsonProcessingException {
        // Group name is derived server-side from verified tenantId.
        String groupName = trustedTenantId + "-orders";
        OrderNotice notice = new OrderNotice(
            1, eventId, "ORDER_STATUS_CHANGED",
            orderId, status, resourceVersion
        );

        String payload = json.writeValueAsString(notice);
        client.sendToGroup(
            groupName,
            payload,
            WebPubSubContentType.APPLICATION_JSON
        );
    }
}
~~~

This illustrates a **notification publisher decoupled from REST Controllers**. Verify the **`sendToGroup`** overload and **`WebPubSubContentType`** enum against your pinned **`azure-messaging-webpubsub`** version; this sample omits the Service Bus worker, retries, group setup, and `SecurityFilterChain`. **Never call this straight from an uncommitted transaction** when alerts represent completed events; use the worker/outbox pattern from section 21.

### Group membership must be established first

For clients to receive messages sent to **`tenant-a-orders`**, the backend/service must add the connection/user to that group, or grant the client a scoped join role so it joins explicitly. **Publishing to a group name does not subscribe users automatically.**

With client-managed joins, issue exact **`webpubsub.joinLeaveGroup.<group>`** roles matching service syntax—never broad wildcards. With server-managed membership, the backend validates permissions and adds/removes connections across connect, reconnect, and revocation.

### JSON contract must match the client

The browser in section 15 inspects **`frame.data.type`**. When sending **`APPLICATION_JSON`**, the JSON subprotocol frames the payload according to service/client schema rules. Verify exact frame structures with your SDK/protocol rather than assuming plain-text strings and JSON messages behave identically.

## 32. Troubleshooting matrix

| Symptom | Likely cause | Check |
|---|---|---|
| Negotiate returns 401 | Unauthenticated, expired session, bad JWT | Spring Security filter, issuer/audience, auth logs |
| Negotiate returns 403 | Missing tenant/role permission | Principal, tenant membership, policy |
| WebSocket handshake 401/403 | Bad/expired client token, wrong hub/role | Token TTL, trusted `userId`, service config |
| WebSocket 404 or invalid host | Wrong URL, hub, or service endpoint | Negotiate URL, service region/hostname |
| Browser reports CORS while REST works | Mismatched negotiate origin or rejected preflight | Browser Network tab, API CORS/SameSite |
| REST negotiate OK, WebSocket fails | WSS blocked by proxy/firewall, origin, TLS, network | DevTools WS, DNS, public/private network rules |
| Client connects but misses group messages | Didn't join group, wrong group/role | Membership, send target, user/connection IDs |
| User A receives Tenant B event | Bad group mapping or authz | Halt publishing, audit identity/groups, add negative tests |
| Send API returns 401/403 | Bad service key or identity lacks data-plane role | Credentials, RBAC, SDK scope |
| Send API returns 429/throttled | Service/plan capacity, burst/retry storm | Service metrics, messages/connection, backpressure |
| UI misses state after reconnect | WebSockets are not durable | REST resync, event versioning |
| UI receives duplicate events | Worker retries, multiple sessions | `eventId`/`resourceVersion`, idempotency |
| UI displays stale state | Out-of-order frames or stale cache | Resource version, authoritative GET |
| Event handler retried repeatedly | HTTP validation/timeout or bad response | Handler logs, auth, event contract |
| Staging App Service pushes to prod | Wrong connection/hub/backend config | Sticky slot settings, environment isolation |
| All clients drop after key rotation | Uncoordinated auth/key rollover | Key rotation runbook, token lifecycle |

**Investigate layer by layer in order:** browser/network → negotiation/auth → Web PubSub connection → group membership → backend publish → outbox/broker → source-of-truth DB. A WebSocket error is not automatically a Java bug.

## 33. Scenario A: negotiation succeeds, yet WebSocket returns 403

**Context:** Java API returns 200 with a WebSocket URL, yet the browser's handshake fails with 403.

### Checks to run

1. Was the URL/token truncated or double-encoded in transit to the client?
2. Did the token expire via browser caching or excessive delay between negotiation and connect?
3. Does the hub in the URL match the configured Web PubSub hub?
4. Are allowed origins or service network policies blocking the browser?
5. Was the token signed with the right service credential/identity config?
6. Does the backend identity hold sufficient data-plane roles for minting tokens?
7. Is the endpoint private-only while the browser sits on the public Internet?

### Runbook

- Use non-sensitive request/correlation IDs to match negotiation logs with service metrics.
- Probe with a test client in the lab using a freshly negotiated token.
- Compare service hostname/hub against production configuration.
- If auth is misconfigured, fix server-side token/role settings—never hand the service key to the browser to "test".
- If networking blocks the handshake, verify topology before altering firewalls.
- Re-test and confirm targeted group delivery reaches the right user.

**Never log full token-bearing URLs** into the Browser Console or server diagnostics during investigation.

## 34. Scenario B: a merchant receives another tenant's alerts

**Context:** a merchant in `tenant-b` receives **`ORDER_STATUS_CHANGED`** for a `tenant-a` order because the backend trusted a browser-supplied `groupName` during negotiation.

### Root cause

The application **trusted client-supplied group/`tenantId` input** instead of binding to the verified principal and database permissions. Even without PII, leaking `orderId`/status across tenants is a security incident.

### Runbook

1. Disable or restrict affected group join/send permissions immediately.
2. Audit issued token roles, active memberships, and exposed recipients.
3. Revoke/disconnect sessions and rotate credentials if needed.
4. Fix negotiation so the server derives groups strictly from verified tenant memberships.
5. Enforce resource-ownership checks on every business command.
6. Add negative tests proving `tenant-a` cannot join `tenant-b`, even when tampering with requests or replaying tokens.
7. Assess data exposure scope, audit trails, and incident response steps.

**Never merely rename groups to harder strings**: group names are neither secrets nor authorization controls.

## 35. Scenario C: order updated in DB, yet UI receives no alert

**Context:** REST endpoint returned 200 and the database shows `SHIPPED`, yet the dashboard still shows `CONFIRMED`.

### Correlation trace

~~~text
Order DB row status SHIPPED?
        |
        v
Outbox record exists and committed?
        |
        v
Worker received event / Service Bus message?
        |
        v
Worker Web PubSub send succeeded?
        |
        v
Client connected + in the right group?
        |
        v
Client parsed event with matching schema/version?
        |
        v
REST resync/UI update succeeded?
~~~

### Likely causes

- Code published directly after commit and timed out **without an outbox**.
- Worker hit serialization/auth errors and dead-lettered the message.
- Browser was offline when the message went out.
- Merchant reconnected without re-joining the group.
- Client received version 38 yet a cache/guard served stale version 37.

### Remediation

- With an outbox, replay unprocessed records by unique `eventId` without duplicating orders.
- Improve worker retries, backoff, and DLQ handling.
- Add REST resync so the UI never relies exclusively on notifications.
- Track **time from DB commit to client display** and alert on SLO breaches.
- Never roll back database state just to force a WebSocket alert resend.

## 36. Scenario D: thousands of clients reconnect simultaneously

**Context:** a brief Web PubSub regional/network blip recovers, and tens of thousands of browser tabs call negotiation within one second, driving 429/5xx errors on the Java backend.

### Problems

- REST negotiation spikes, hammering auth and identity providers.
- Backend/Key Vault/DB tenant-membership lookups surge simultaneously.
- Huge numbers of WebSocket handshakes open at once.
- Retried event deliveries pile up in worker queues.

### Remediation

1. Implement exponential backoff **with jitter** on clients.
2. Rate-limit negotiation endpoints with clear retry guidance.
3. Cap reconnect attempts and prompt re-login on 401.
4. Cache membership safely with short TTLs where appropriate.
5. Size Web PubSub connections/throughput for **peak**, not just averages.
6. Trim payloads or throttle non-critical notifications under overload.
7. Ensure browsers **resync** via REST after reconnecting.

**Never let 10,000 clients retry every 100 ms indefinitely**: retry storms trigger secondary outages right as the service recovers.

## 37. Lab: Spring Boot Orders real-time

This lab has two tiers:

- **Design and local testing:** requires no Azure provisioning if you lack a subscription or permissions.
- **Azure sandbox:** uses a budget-approved lab Web PubSub resource, identity, and backend.

### Business requirements

Build **Orders Live** featuring:

- Spring Boot REST API returning order status and exposing **`/api/realtime/negotiate`**.
- A Web PubSub hub named **`orders`**.
- Merchant A's browser viewing alerts in **`tenant-a-orders`**.
- Merchant B's browser viewing **`tenant-b-orders`**.
- When an order status changes, the server pushes **`ORDER_STATUS_CHANGED`** scoped by tenant.
- Disconnected browsers reconnect and resync state via REST.
- Zero real credentials in source code or logs.

### Part A: build the flow matrix

| Flow | Caller | Receiver | Authn/authz |
|---|---|---|---|
| HTTP login | Browser | Identity provider / backend | OIDC/JWT/cookie per design |
| HTTP negotiate | Browser | Spring Boot | Valid principal, tenant membership |
| WSS connect | Browser | Azure Web PubSub | Client access token for hub/roles |
| Group membership | Browser / backend | Azure Web PubSub | Server verifies allowed group |
| DB status change | Trusted API | Azure SQL / Cosmos DB | Business rules + transaction |
| Outbox / worker | Database / Service Bus | Java notification worker | Managed identity / queue roles |
| Server send | Worker | Web PubSub service | Server identity / service credential |
| Browser fetch latest | Browser | Spring Boot | Resource-level authorization |

**Check question:** which flows may touch production data? **None in this lab**; every endpoint, tenant, and resource must stay inside the sandbox.

### Part B: create the local Java project

1. Create a Java 17+ Spring Boot project matching supported Spring/SDK versions.
2. Add Spring Web, Security/OAuth Resource Server, and the Azure Web PubSub SDK.
3. Add **`WebPubSubConfiguration`** from section 12.
4. Add **`NegotiationController`** from section 13.
5. Add **`OrderNotificationPublisher`** from section 31.
6. Implement `GET /orders/{id}` validating principal and tenant.
7. Use synthetic in-memory orders for the lab instead of real customer data.
8. If no Azure resource is available, mock the SDK service layer and unit-test negotiation, auth, and targeting logic.

### Part C: environment configuration

For an Azure lab with Key Vault or secure app settings:

~~~text
SERVICE_ENV=lab
WEBPUBSUB_HUB=orders
WEBPUBSUB_CONNECTION_STRING=<FROM_SECRET_STORE_ONLY>
ORDER_BACKEND_DATA_SOURCE=mock-or-lab-database
APP_VERSION=lab-1.0.0
~~~

**This illustrates environment variables**, not a real secret file. Align variable names with Spring Boot relaxed property binding, as **`WEBPUBSUB_HUB`** and **`webpubsub.hub`** require verified mapping—never assume every host binds every key automatically.

### Part D: run the browser test client

1. Sign in as a `tenant-a` user.
2. Call the negotiation endpoint; confirm 200 and **`Cache-Control: no-store`**.
3. Open the WebSocket with the returned URL.
4. If using client-managed joins, join only `tenant-a-orders` with its scoped role; if server-managed, let the backend add membership.
5. Trigger a test event for `tenant-a` from the backend/worker.
6. Confirm Browser A receives **`ORDER_STATUS_CHANGED`** matching the frame/protocol contract.
7. Confirm Browser B receives no `tenant-a` events.
8. Disconnect Browser A, update mock order state, reconnect, and resync via REST.

### Part E: test negative cases

| Case | Action | Expected outcome |
|---|---|---|
| 1 | Anonymous call to negotiate | 401 |
| 2 | User A requests token for User B | Server ignores or rejects spoofed input |
| 3 | Tenant A requests Tenant B's group | 403 or no role issued |
| 4 | Expired token used for a new socket | Handshake rejected by service |
| 5 | Read-only browser tries sending group message | Denied by role/policy |
| 6 | WebSocket drops between two events | Client fetches REST snapshot and updates |
| 7 | Worker redelivers duplicate `eventId` | UI neither reverts state nor duplicates effects |
| 8 | Transient service send error | Worker retries/alerts without losing outbox row |
| 9 | Missing group membership after reconnect | Test catches gap and restores membership |
| 10 | Backend permissions revoked | Cannot keep querying other-tenant orders |

Never test permissions using two real customer accounts by poking unauthorized data; use dedicated lab accounts and synthetic data.

### Part F: lab evidence table

| Evidence | What to record |
|---|---|
| Module/platform | Spring Boot/Java/SDK versions, Web PubSub tier and region |
| Identity | Auth method, principal/tenant mapping, service roles |
| Negotiation | HTTP status, token TTL config, `no-store`, and log redaction |
| Connection | WebSocket open/close, subprotocol, group join |
| Delivery | `eventId`, exact tenant targeting, observed latency |
| Reconnect | Backoff and accurate REST state resync |
| Negative tests | Cross-tenant, anonymous, and expired-token denials |
| Durability | Outbox/Service Bus design or documented omission |
| Monitoring | Connections, service sends, errors, 429s, backlog |
| Cost | Assumed concurrent connections, messages, and cleanup |

### Clean up the lab environment

- Delete only the Web PubSub resource, Key Vault secrets, and test services **created and owned by this lab**.
- Never delete shared resource groups or rotate production keys.
- Disconnect test clients and purge test records per retention.
- Clear any accidentally saved local credentials from shell history or artifacts.
- Verify subscription billing, tags, and remaining resources are clean.

## 38. CI/CD integration and automated testing

Never rely purely on manual WebSocket clicks. CI/CD can validate across layers:

~~~mermaid
flowchart TD
    A[Commit Java + IaC + message schema] --> B[Build + unit tests]
    B --> C[Security and dependency scanning]
    C --> D[Deploy dev/sandbox]
    D --> E[Test negotiation and identity]
    E --> F[Test WS connect + tenant groups]
    F --> G[Test send, reconnect and resync]
    G --> H[Test worker retries and idempotency]
    H --> I{Staging approval?}
    I -- No --> J[Stop and investigate]
    I -- Yes --> K[Promote same artifact]
    K --> L[Monitor production SLO + cost]
~~~

### Unit tests

- Backend blocks anonymous negotiation.
- Principal in `tenant-a` maps solely to `tenant-a` groups, ignoring client-supplied groups.
- Domain events carry `schemaVersion`, `eventId`, and `resourceVersion`.
- Worker retries transient faults while never looping infinitely on invalid authz.
- Notification publisher never calls `sendToAll` for private events.
- Order mutations and outbox rows commit in the same database transaction per chosen store.

### Integration tests

- Tokens are accepted by Web PubSub on the target hub.
- Group assignment handles multiple connections for one user cleanly.
- Server SDK targeted sends reach authorized clients only.
- Mid-send disconnects never leave stale UI state after resync.
- Spoofed event-handler POSTs never execute business commands.
- Missing data-plane roles fail cleanly and fire alerts.
- Staging never connects to production Web PubSub or backends.

### Load tests

Verify:

1. Ramp concurrent connections up to approved caps.
2. Measure negotiation throughput during a reconnect storm.
3. Test fan-out across one large group and many small groups.
4. Measure worker send p95 latency, 429s, and queue backlog.
5. Measure browser time-to-update and UI memory under burst traffic.
6. Confirm scaling out Java/AKS pods creates zero duplicate business side effects.

Never exceed shared-environment quotas or cause a DoS; load tests need explicit capacity plans and budgets.

## 39. Cost and budgeting for real-time architectures

Managed real-time systems accrue costs across multiple layers:

| Item | Cost drivers |
|---|---|
| **Azure Web PubSub service** | SKU/tier, units/capacity, connections, and messages per pricing model |
| **Java backend** | App Service plans, AKS nodes, Container Apps, or Functions usage |
| **Azure Service Bus** | Queues/topics, message operations, broker tier |
| **Database** | SQL/Cosmos DB writes, outbox storage, reads for resync |
| **Networking** | Egress, Private Link/Private Endpoints, DNS, NAT per topology |
| **Observability** | Application Insights / Log Analytics ingestion, retention, alerts |
| **Security** | Key Vault operations, identity/admin infrastructure |
| **CI/CD** | Build runners, container registry/artifacts, integration/load tests |

### Never confuse connection counts with user counts

One user can open multiple tabs and devices: **5,000 active users rarely equals 5,000 concurrent connections**. Likewise, billable service messages do not always equal backend send API calls—one broadcast fans out into many client deliveries, so check current tier pricing definitions.

### Sample sizing table

| Metric | Hypothetical value | Where to measure |
|---|---:|---|
| Daily active users | 20,000 | Product analytics |
| Peak concurrent users | 5,000 | Usage/traffic models |
| Avg connections/user | 1.5 | Client telemetry |
| Peak connections | 7,500 | Multiplication + headroom |
| Backend events/s | 100 | Service Bus/outbox metrics |
| Avg recipients/event | 80 | Group membership distribution |
| Estimated fan-out/s | 8,000 | Events × recipients |
| Avg payload bytes | 500 | Serialized event samples |
| Reconnect peak | Needs load test | WebSocket churn/history |

**These figures are completely hypothetical**, not official prices or limits. Pick tiers, unit counts, regions, autoscaling, and DR only after measuring real traffic.

### Cost optimization

- Avoid re-emitting unchanged states.
- Coalesce progress events (e.g., 1%, 2%, 3% → push every 5% where reasonable).
- Never stream huge JSON entities over WebSockets.
- Target only required users/groups.
- Close idle connections and eliminate reconnect loops.
- Pair REST snapshots with client caches instead of pushing every field change.
- Tune Service Bus/outbox retries and curb DLQ growth.
- Set tags, budgets, and alerts; tear down lab resources promptly.

**Budget alerts do not automatically halt all billing.** Even an idle Web PubSub instance accrues capacity charges per provisioned tier.

## 40. Production-readiness checklist

- [ ] Confirmed the real-time use case requires WebSockets rather than polling or SSE.
- [ ] Compared Web PubSub, SignalR, Service Bus, and Redis pub/sub against Java backend needs.
- [ ] Selected region, SKU/tier, and capacity from peak concurrent connections and fan-out.
- [ ] Pinned compatible Java SDK, dependency, and JDK versions.
- [ ] Reused service clients rather than creating one per request.
- [ ] Secured negotiation endpoints with HTTPS and full principal authentication.
- [ ] Derived `userId`, `tenantId`, and roles server-side, never trusting client input.
- [ ] Set short TTLs and `no-store` on client access tokens; zero tokens in logs.
- [ ] Configured managed identity or Key Vault for server credentials.
- [ ] Verified data-plane RBAC separately from management-plane RBAC.
- [ ] Scoped group memberships by tenant and restored them on reconnect.
- [ ] Blocked hub-wide broadcasts of PII or tenant-specific alerts.
- [ ] Added protocol/origin validation, authorization, and idempotency to event handlers.
- [ ] Versioned message schemas with `eventId`/`resourceVersion` and zero secrets.
- [ ] Coordinated DB commits and notifications via outbox/workers where durability matters.
- [ ] Implemented reconnect backoff + REST resync in UIs.
- [ ] Enforced resource/tenant authorization on all business APIs.
- [ ] Tested anonymous, wrong-tenant, expired-token, and revoked-role negative cases.
- [ ] Instrumented end-to-end observability from DB commit → Service Bus → Web PubSub → client.
- [ ] Alerted on send errors, 429s, connection churn, negotiation failures, and queue backlogs.
- [ ] Tested public/private network topology from both browsers and backends.
- [ ] Isolated dev/staging/prod identities, hubs/instances, event sources, and secrets.
- [ ] Enforced tested CI/CD artifacts, approvals, canaries/rollbacks, and data compatibility.
- [ ] Documented runbooks for key rotation, failover/reconnect storms, and incident response.
- [ ] Benchmarked peak connections, message sizes, and fan-out alongside cost estimates.

## 41. Self-check questions

1. How do polling, SSE, and WebSockets differ in data flow and connection management?
2. When should a Java backend pick Azure Web PubSub instead of Azure SignalR Service?
3. Can Azure Service Bus replace Web PubSub to push straight to browsers?
4. How do hub, group, `userId`, and `connectionId` differ?
5. How many WebSocket connections does one user with three tabs typically open?
6. What must the negotiation endpoint verify before returning a token?
7. Why must browsers never receive the service connection string?
8. Does client access token expiration automatically close all existing connections?
9. Why can you never trust a `groupName` sent by the browser?
10. How do server-managed memberships differ from client-managed joins?
11. When do browsers need `sendToGroup` permissions, and when should they be omitted?
12. What kind of failure is calling `sendToAll` for private invoice alerts?
13. How does the JSON subprotocol differ from raw WebSocket message framing?
14. When a browser receives `ORDER_STATUS_CHANGED`, why should it fetch a REST snapshot?
15. Which WebSocket messages can be missed during a disconnect?
16. How do `resourceVersion` and `eventId` prevent stale and duplicate event bugs?
17. How does an outbox close the gap between database commit and publish?
18. Does an outbox guarantee exactly-once delivery to browsers?
19. Why do Service Bus workers need retries, DLQs, and idempotency?
20. Does online/offline presence prove a user is actively looking at the screen?
21. Do CORS and WebSocket `Origin` replace token authentication?
22. Does a backend Private Endpoint let public Internet browsers reach a private-only service?
23. Does Azure RBAC Contributor automatically grant Web PubSub data-plane send permissions?
24. How do managed identity, Service Bus, and Key Vault work together in a Java worker?
25. How can a staging deployment slot accidentally send alerts to production users?
26. How can a reconnect storm overload the negotiation API?
27. Before scaling AKS pods, which limits must you measure on Web PubSub and the database?
28. Does the backend's send-call count always equal the number of messages delivered to clients?
29. What should you inspect when negotiate returns 200 yet the WebSocket handshake returns 403?
30. Which timestamps are needed to measure time from DB commit to UI update?
31. Does rolling back a Java app revoke already-minted tokens or undo sent events?
32. Why keep message payloads small and schema-versioned?
33. Where does a client-to-server chat app need a backend event handler?
34. When does a simple push application not need an upstream event handler?

## 42. References

- [Azure Web PubSub overview](https://learn.microsoft.com/azure/azure-web-pubsub/overview) — managed WebSockets and use cases.
- [What is Azure Web PubSub?](https://learn.microsoft.com/azure/azure-web-pubsub/overview#what-is-azure-web-pubsub-service) — architectural components and protocols.
- [Azure Web PubSub Java quickstart](https://learn.microsoft.com/azure/azure-web-pubsub/quickstart-pubsub-java) — Java service SDK and publishing messages.
- [Azure Web PubSub client protocol](https://learn.microsoft.com/azure/azure-web-pubsub/concept-client-protocols) — raw WebSocket/JSON subprotocol and client events.
- [Azure Web PubSub client access tokens](https://learn.microsoft.com/azure/azure-web-pubsub/concept-client-access-token) — client connections, roles, and scopes.
- [Azure Web PubSub event handlers](https://learn.microsoft.com/azure/azure-web-pubsub/concept-service-internals#event-handler) — upstream connect/user events and callback security.
- [Azure Web PubSub security best practices](https://learn.microsoft.com/azure/azure-web-pubsub/concept-security) — authorization and secure connections.
- [Azure Web PubSub Java SDK](https://learn.microsoft.com/java/api/overview/azure/messaging-webpubsub-readme) — Java server SDK and model types.
- [Azure Web PubSub monitoring](https://learn.microsoft.com/azure/azure-web-pubsub/howto-monitor-azure-web-pubsub) — connections, diagnostics, and Azure Monitor.
- [Azure SignalR Service overview](https://learn.microsoft.com/azure/azure-signalr/signalr-overview) — SignalR hubs and service models.
- [Azure Service Bus documentation](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-messaging-overview) — durable messaging, queues, and topics.
- [Microsoft Entra workload identity for AKS](https://learn.microsoft.com/azure/aks/workload-identity-overview) — Java pod identity.
- [Spring Security OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html) — bearer token validation.
- [Azure CLI az webpubsub](https://learn.microsoft.com/cli/azure/webpubsub) — managing service metadata and provisioning.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — estimating backend and managed real-time costs.

**Conclusion:** Integrating Java backends with real-time services on Azure takes far more than opening a WebSocket and calling `sendToAll`. A resilient system requires **authenticated negotiation, short-lived client tokens, tenant-scoped group/user targeting, credential-managed Java SDK usage, post-commit event pipelines, client reconnect/resync, and end-to-end observability down to `eventId`**. Azure Web PubSub offloads WebSocket management and fan-out, yet never replaces **databases, Service Bus/outboxes, business authorization, or recovery policies**. Designed cleanly from the start and verified with tests and metrics, real-time features scale reliably while protecting data and budgets.
