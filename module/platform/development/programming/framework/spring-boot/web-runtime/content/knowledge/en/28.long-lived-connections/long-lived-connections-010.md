# Impact of Timeouts, Load Balancing, and Graceful Shutdown on Long-Lived Connections

## 1. Real-World Problem: An Open Connection Does Not Live Forever

A Spring Boot system pushes real-time events via **Server-Sent Events (SSE)** or **WebSocket**. Locally, clients receive updates smoothly. After deploying behind NGINX, an ingress, or a cloud load balancer, connections drop after one minute of silence. During rolling deployments, some clients lose sessions, duplicate events, or miss events. When scaling from two to four pods, existing connections remain piled onto the old pods. Operators enabled `graceful shutdown`, yet long-lived WebSockets still get severed right as pods terminate.

Those issues happen **even when Spring controllers and business logic are completely right**. Long-lived connections span multiple concurrent lifecycles:

- TCP/TLS lifecycles across hops.
- HTTP request/response or HTTP/2 stream lifecycles.
- Post-HTTP-Upgrade WebSocket lifecycles.
- Proxy/LB backend connection lifecycles and idle timeouts.
- Instance/pod lifecycles covering readiness, deregistration, draining, and SIGTERM.
- Application subscription, subscriber, and event-source lifecycles.
- Business lifecycle: which event/command had the client processed before disconnecting?

**Learning objectives**:
1. Distinguish **idle timeout, request timeout, read timeout, connection lifetime, TCP keepalive**, and application heartbeats.
2. Understand how NGINX, AWS ALB, ingress, and proxy hops impact SSE, WebSocket, and HTTP/2.
3. Explain why load balancers do not rebalance live WebSockets automatically, and why sticky sessions do not replace shared state.
4. Master **Spring Boot graceful shutdown**, readiness, preStop hooks, connection draining, and Kubernetes termination budgets.
5. Build a runnable **Java 17+ Spring Boot WebFlux demo**: SSE streaming, readiness state, and proactive connection draining.
6. Design reconnect with backoff, resume/replay via `Last-Event-ID` or sequence/ack, and duplicate/gap handling.
7. Verify with `curl`, logs/metrics, timeout tests, and pre-production rollout drills.

> **Version note:** Hands-on examples use Spring Boot **3.5.x**, Java 17+, `spring-boot-starter-webflux`, Reactor Netty, and Spring Framework 6.2. Boot 3.5 documentation notes that **graceful shutdown is enabled by default** for supported embedded web servers; YAML still declares `server.shutdown: graceful` to make intent explicit. In older Boot versions, defaults may differ—never assume identical defaults across every version.

## 2. "Long-Lived Connections" Come in Different Forms

| Type | Mechanism | How Client/Server Exchange Data | Key Caveats |
|---|---|---|---|
| HTTP/1.1 keep-alive | Reuses a TCP connection across multiple requests | Independent request/response pairs over one connection | Idle keep-alive timeout is not the lifetime of a streaming response |
| HTTP/2 | Multiple **streams** share one connection | Multiplexed request/response, with PING and GOAWAY | Closing one connection affects many concurrent streams |
| SSE | One long-open `text/event-stream` HTTP response | Server → client, event by event + heartbeats | Proxy buffering/idle timeouts; clients can reconnect |
| WebSocket | Handshake upgrading to a bidirectional protocol | Client ↔ server via frames, ping/pong/close | Connection pins to one backend; state must recover on reconnect |
| Long polling | Request waits until data arrives or times out, then client sends another | Intentional chain of long requests | Read/request timeouts and request rates; not literally a permanent socket |
| HTTP streaming/NDJSON | Body emitted incrementally | One long response, over HTTP/1.1 or HTTP/2 | Flush/buffering, demand, cancellation, timeouts |

An SSE stream may travel over HTTP/2 from browser → CDN while the CDN uses HTTP/1.1 to the backend. Thus **protocols can differ at each hop**. "Enabling HTTP/2 in the browser" does not prove the backend speaks HTTP/2.

**SSE is not WebSocket.** SSE is one-way server-to-client using EventSource with built-in browser reconnection. WebSocket is bidirectional with its own ping/pong and close codes. Every long-lived connection must handle dropped networks and backend redeploys.

## 3. Which Layers Does a Connection Traverse?

~~~text
Browser / mobile app / CLI
     |
     | TLS / HTTP/2 / WebSocket / SSE
     v
CDN or edge proxy
     |
     | Dedicated connection and idle/lifetime policies
     v
Cloud LB / ingress / reverse proxy
     |
     | Backend keep-alive / Upgrade / HTTP stream
     v
Spring Boot instance A
     |
     +-- Servlet async / WebFlux subscription / WebSocket session
     |
     +-- DB / Redis / event broker / message bus
~~~

Each hop can enforce:
- **New connection** deadlines such as TCP connect or TLS handshake timeouts.
- Idle timeouts when **no bytes** flow for a given window.
- Read/write timeouts between I/O operations.
- Request duration or upstream response timeouts.
- Maximum connection lifetimes, even while traffic flows.
- Queue, connection pool, and circuit-breaker policies.
- Deregistration/draining timeouts when an instance leaves the LB.

What the client sees is rarely **a single end-to-end TCP socket from browser to JVM**: proxies terminate one socket and open another. Sending application heartbeats only helps if bytes **flush through every hop** you intend to keep alive.

### Simple Rule on Which Hop Breaks First

Suppose:
- Client → ALB idle timeout: 60 seconds.
- ALB → NGINX or proxy read response timeout: 75 seconds.
- Backend emits data every 120 seconds.

The path will be cut **before the backend emits its next message**. Raising only a Spring timeout accomplishes nothing while forgetting the hop with the lowest threshold.

Do not treat those numbers as universal defaults. They are verifiable examples for NGINX and AWS ALB; **always check the exact configuration of your active LB/proxy versions**.

## 4. Distinguishing Timeout Types

| Name/Mechanism | What Does It Measure? | Is It the Max Lifetime of the Entire Long Connection? |
|---|---|---|
| **Connect timeout** | Time to establish TCP/TLS or acquire a connection per client | No |
| **Read timeout / proxy_read_timeout** | Silence duration between successive upstream reads | Usually no; steady streams can live much longer |
| **Write/send timeout** | Duration unable to send data to the peer | No, though slow clients can trigger disconnects |
| **Idle timeout** | Silence period on a connection/hop | Not an absolute lifetime |
| **HTTP request/async timeout** | Processing deadline for a request or async request per component | Can sever an SSE response even while bytes flow, depending on stack |
| **Connection max lifetime / keepalive duration** | Maximum age of a connection since creation | Yes; can close even active connections |
| **LB deregistration delay** | Wait time for a target to stop serving and drain existing traffic | Not an idle timeout |
| **Graceful shutdown timeout** | Budget to wait for in-flight work on app stop | Caps shutdown duration; does not handle infinite streams alone |
| **TCP keepalive** | Kernel/OS-level probes after inactivity | Does not replace SSE heartbeats, WebSocket pings, or all LB idle timers |
| **Application heartbeat** | Periodic message/comment/ping sent by protocol/app | Resets idle timers, yet cannot bypass maximum lifetimes |

**Important:** Spring MVC async request timeout, NGINX read timeout, and client HTTP response timeout **are not the same clock**. `server.tomcat.connection-timeout`, for instance, relates to Tomcat accepting connection/HTTP request data and should not be assumed to govern "SSE response limits" universally.

Use explicit names in operational docs: `client_connect_timeout`, `proxy_upstream_read_timeout`, `lb_idle_timeout`, `sse_heartbeat_interval`, `app_grace_period`. Vague labels like `"timeout=60s"` invite confusion and tweaking the wrong layer.

## 5. Idle Timeouts and Heartbeats: Why Does It Drop Every 60 Seconds?

Suppose NGINX proxies WebSocket. NGINX docs state `proxy_read_timeout` defaults to **60 seconds** and measures **intervals between two read operations from upstream**, not total response duration. For WebSocket, NGINX also notes that if upstream transmits nothing within that window, the connection closes; periodic server WebSocket ping frames keep it alive.

Similarly, AWS Application Load Balancer has a **default 60-second connection idle timeout** in current docs. When traffic satisfying ALB's rules stops, client or target connections close. ALB also has a distinct **HTTP client keepalive duration**, defaulting to **3600 seconds** in docs, measuring total connection age since establishment and **never resetting** on traffic.

### Idle Timeout vs. Maximum Connection Age

~~~text
Connection opens at T0
  |
  +-- every 20s a heartbeat arrives → resets idle timer (if hop sees bytes)
  |
  +-- reaches LB maximum connection age → may be forced to close
~~~

Heartbeats therefore save connections from **idle timeouts**, yet never make connections immortal. Clients must always be ready to reconnect after max age, pod restarts, proxy upgrades, network errors, or server shutdowns.

### Choosing Heartbeat Interval H

Set `H` **well below the smallest idle timeout** across relevant hops, leaving headroom for jitter, GC pauses, scheduler delays, network buffering, and flush latency.

**Experimental** example values, not universal constants:
- SSE heartbeat or event every **20s**.
- ALB idle timeout **60s**.
- NGINX `proxy_read_timeout: 75s`.

`H=20s` leaves comfortable margin under both 60s and 75s, **provided heartbeats actually traverse those hops**. If `proxy_buffering` holds back SSE comments, Java heartbeats never reach the client/LB on time; inspect bytes at every hop.

Never pick `H=59s` just because `idle=60s`: minor jitter will drop the connection. Conversely, never send every 100 ms across hundreds of thousands of clients unnecessarily: doing so wastes bandwidth, CPU, wakeups, and cost.

## 6. Protocol-Correct Heartbeats: SSE, WebSocket, and HTTP/2

### SSE: Event or Comment Heartbeat

SSE uses `Content-Type: text/event-stream`. A data event looks like:

~~~text
event: price
id: 194
data: {"sku":"SKU-1","price":120}

~~~

A blank line terminates an SSE event. A line starting with `:` is a **comment**; EventSource fires no business callback for comments, yet its flushed bytes keep the path active:

~~~text
: heartbeat

~~~

In Spring WebFlux you can emit comments via:

~~~java
// Fragment inside a reactive SSE pipeline.
Flux<ServerSentEvent<String>> heartbeats =
    Flux.interval(Duration.ofSeconds(20))
        .map(n -> ServerSentEvent.<String>builder()
            .comment("heartbeat")
            .build());
~~~

This is only a fragment; `Flux`, `ServerSentEvent`, and `Duration` imports belong in your service/controller. When merging heartbeats with business events, preserve ordering/cursors and verify serialization, buffering, and cancellation. **Comment heartbeats must never alter the `Last-Event-ID` of business events.**

### WebSocket: Ping/Pong and Application-Level Heartbeats

WebSocket defines **protocol PING/PONG control frames** per RFC 6455. Servers/frameworks can send pings and expect pongs to verify peer health and satisfy proxy idle timers. The browser JavaScript `WebSocket` API **does not let apps manually send WebSocket protocol PING frames** like a server library; when client-originated pings are needed, send an application message such as `{"type":"ping"}` with a matching `pong` reply.

Protocol ping/pong and application-message heartbeats are not strictly identical. Proxies/LBs observe wire bytes, yet do not assume every L7 gateway credits every ping type equally against its idle timer.

### HTTP/2: PING and GOAWAY

HTTP/2 defines **PING frames** to measure RTT or check idle connections, and **GOAWAY frames** to stop opening new streams before closing a connection. However, **AWS ALB explicitly states that HTTP/2 PING frames do not reset ALB's connection idle timeout**. Thus periodic client HTTP/2 PINGs alone do not keep a stream alive across ALB. Emit real data counted as activity by the LB and verify per provider.

HTTP/2 GOAWAY is part of **connection shutdown**, not confirmation that the app persisted all business messages. An active HTTP/2 SSE stream can still be cut once its underlying connection closes.

## 7. Configuring NGINX for SSE: Avoiding Buffering and Idle Read Timeouts

The **fragment** below assumes a working `spring-runtime:8080` upstream/DNS and valid NGINX `server` block; it is not a complete copy-paste production config:

~~~nginx
location /events {
    proxy_pass http://spring-runtime:8080;

    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

    # Never buffer SSE chunks before pushing to clients.
    proxy_buffering off;

    # Maximum wait BETWEEN consecutive upstream reads.
    proxy_read_timeout 75s;
}
~~~

Explanation:
- `proxy_buffering off` forwards streamed bytes immediately instead of filling internal buffers first. NGINX enables proxy buffering by default; turn it off only on streaming routes to preserve proxy efficiency elsewhere.
- `proxy_read_timeout 75s` bounds silence between consecutive upstream reads—it does **not** mean "SSE dies after 75s total".
- `proxy_http_version 1.1` shows HTTP/1.1 to upstream, especially useful alongside upgrades; defaults vary across NGINX releases, so check your version's docs.
- `X-Forwarded-*` headers must only be trusted by Spring Boot when coming from trusted proxies; never blindly trust client-supplied headers.

When responses carry `X-Accel-Buffering: no`, NGINX disables buffering for that response unless configured to ignore the header. Still **verify** proxy settings and never expect one header to fix every upstream CDN.

**Do not randomly inject `Connection: keep-alive` into SSE responses** or treat it as a heartbeat. HTTP/1.1 keep-alive reuses sockets without sending periodic bytes through proxies. In HTTP/2, connection-specific headers like `Connection` have strict rules and must not be emitted HTTP/1.1-style.

## 8. NGINX for WebSocket: Forward Upgrade Headers Properly

WebSocket normally starts with an HTTP/1.1 Upgrade handshake. Reverse proxies must forward hop-by-hop headers properly. Official NGINX pattern:

~~~nginx
# Place inside http context, outside server blocks.
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

# Inside server/location:
location /ws/ {
    proxy_pass http://spring-runtime:8080;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_set_header Host $host;
    proxy_read_timeout 75s;
}
~~~

This **config fragment** spans two scopes; keep `map` in `http`, never inside `location`. Defaults vary by NGINX version; explicit settings here clarify HTTP/1.1 Upgrade mechanics.

If upstream sends zero frames past `proxy_read_timeout`, NGINX can close the WebSocket even though the client's TCP socket looks open. Configure proper ping/pong and test end-to-end.

Do not rely on `proxy_buffering off` alone as a cure for a broken WebSocket handshake; forwarding Upgrade headers and keeping post-upgrade traffic alive are **two separate concerns**.

## 9. Cloud Load Balancers: At Least Three Easily Confused Clocks

Example from **AWS Application Load Balancer** documentation:
1. **Connection idle timeout:** defaults to 60s; closes connections silent past ALB's idle rules.
2. **HTTP client keepalive duration:** defaults to 3600s; total client connection lifetime that does not reset on traffic. Upon expiry, ALB closes per HTTP version (e.g., `GOAWAY` on HTTP/2).
3. **Target deregistration delay:** configured on the **target group**, governing connection draining when removing targets—unrelated to idle timeout or client keepalive.

These defaults reflect documentation at the time of writing, **not measurements of your account's configuration**. Infrastructure, Terraform/CloudFormation, or console edits frequently override defaults.

### Two Hops Can Have Different Timeouts

~~~text
Browser --[ALB client connection]--> ALB
                                      |
                                      +--[ALB target connection]--> Pod
~~~

When the browser reconnects or ALB switches targets, **a new socket** can land on a different pod. Even with cookie sessions, an existing WebSocket never migrates seamlessly to a new pod.

If upstream Boot abruptly closes a connection while ALB still thinks it can reuse it, ALB may return `502 Bad Gateway`. Aligning idle/keepalive policies and graceful closes reduces failures without eliminating every race condition.

## 10. Load Balancing: Once Bound to a Backend, a WebSocket Does Not Auto-Migrate

Consider two pods:

~~~text
                  +--> Pod A: 8,000 WebSocket connections
Client -> LB -----|
                  +--> Pod B: 2,000 WebSocket connections
~~~

After scaling out Pod C and Pod D, **open sockets on Pods A and B stay pinned to their current backends**; standard LBs pick backends only when new connections or requests arrive. They cannot "live-migrate an active TCP/WebSocket connection" the way they route independent HTTP requests.

Consequences:
- Round-robin on **new handshakes** does not rebalance **existing active connections**.
- Scaling out does not immediately shed load from heavily loaded existing pods.
- Deploying or scaling in Pod A forces A's clients to reconnect unless specialized protocol migration exists.
- LB weights or CPU-based autoscaling may lag behind actual open socket counts.
- Persistent connections slow rolling updates or get cut when grace deadlines expire.

Monitor **active connection count per instance**, messages/sec, memory/socket, CPU, event-loop lag, and concurrent reconnects—not RPS alone.

### Are Sticky Sessions the Solution?

**Session affinity** (cookie/hash/source-IP) can route a client's new requests to the same pod in some setups, yet:
- An already open socket is already pinned to one backend without needing stickiness.
- When a pod fails or drains, stickiness cannot keep that pod alive.
- Clients change IPs, cookies expire, and ingress LBs follow their own rules.
- Stickiness masks local-only state and complicates failover.
- Reconnecting to another pod still requires recovering state and cursors.

Whenever WebSocket sessions hold subscription lists, topic memberships, or permissions in RAM, **design explicit state recovery**. Redis/pub-sub, brokers, durable event logs, databases, or external session stores fit depending on state type; never mistake sticky sessions for a message bus.

## 11. Shared State and Event Ordering After Reconnect

Common failure sequence:

~~~text
T1 Pod A emits event #100
T2 Client receives #100 then loses WebSocket
T3 Event #101 is emitted while client is offline
T4 Client reconnects and LB routes to Pod B
T5 Pod B starts from event #102
=> Client misses #101 without replay/cursor
~~~

Other failure modes:
- Pod B replays #100 and the client applies it twice.
- Two publishers/consumers observe different event orderings.
- Client resends a command after missing an ack; server applies a duplicate side effect.
- On NGINX/LB timeout, no close event reaches the client cleanly, leaving state "unknown".

### SSE and Last-Event-ID

SSE lets events carry an `id:` field:

~~~text
id: 101
event: update
data: {"version":101}

~~~

Browser `EventSource` sends `Last-Event-ID` on reconnect. **Yet that header/cursor does not make Spring Boot replay data automatically.** The server must:
1. Assign durable, meaningful stream event IDs.
2. Retain the event log/offsets long enough.
3. Read `Last-Event-ID` or cursor per contract.
4. Replay events after the confirmed offset and transition into live streaming with zero gaps between the two phases.
5. Define policies for stale cursors, truncated logs, or revoked permissions.

A stream built solely with `Flux.interval` counting from 0 per connection **cannot support resume**. The demo in this lesson deliberately **omits event IDs** so it never creates a false impression of replay support.

### WebSocket Needs Its Own Protocol

WebSocket has no automatic `Last-Event-ID`. Applications can exchange messages like:

~~~json
{"type":"subscribe","topic":"orders","afterSequence":101}
~~~

The server verifies authorization, replays from `afterSequence`, and then delivers live events. Clients deduplicate by event ID and acknowledge processed offsets. Avoid races between "replaying up to now" and "subscribing live" by using transactional cursors or broker semantics for critical workflows.

When a client sends a side-effecting command (e.g., payment), losing the WebSocket afterward **does not prove the command wasn't executed**. Attach command IDs / idempotency keys and query operation status rather than blindly retrying non-idempotent commands with fresh keys.

## 12. What Does Spring Boot 3.5 Graceful Shutdown Actually Guarantee?

Per **Spring Boot 3.5** documentation:
- Graceful shutdown **is enabled by default** for embedded Tomcat, Jetty, Reactor Netty, and Undertow across both Servlet and reactive apps.
- It runs during `ApplicationContext` closure, in an early `SmartLifecycle` stop phase.
- During the grace period, existing requests **are given a chance to finish**, while new requests are rejected per server policy.
- Wait budget is configured via `spring.lifecycle.timeout-per-shutdown-phase`, e.g., `30s`.
- Rejection behavior varies by server: Tomcat/Jetty/Reactor Netty stop accepting at the network layer; Undertow in Boot 3.5 docs can respond with 503.
- Persistent connections can make new-request rejection behave differently across servers.

Explicit configuration:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

`server.shutdown: graceful` explicitly documents Boot 3.5's default; `immediate` disables the grace period, which is **a poor choice for services with long-lived state or streams**.

### Why Graceful Shutdown Alone Is Not Enough for Infinite WebSocket/SSE

An SSE `Flux.interval(...)` does not finish naturally within 30s unless canceled or stopped by app logic. WebSockets likewise can stay open indefinitely. Waiting on in-flight requests that never finish within the deadline forces termination once grace expires.

**Graceful shutdown is not live connection migration**, nor does it **guarantee 100% of events reach clients before process exit**. If zero loss is required, use external event stores, client cursors/acks, and replay/reconciliation.

Never crank grace periods from 30s to several hours thinking it preserves sockets: rollouts will stall, Kubernetes will force-kill pods past termination grace, and deployment pipelines will time out.

## 13. Connection Draining Must Begin Before SIGTERM When Needed

For long-lived connections, split termination into two stages:

**Stage A — Proactive application draining:**
1. Mark the instance `NOT_READY` before stopping the process.
2. Wait long enough for readiness/endpoint/LB target propagation.
3. Reject **new business streams and handshakes**.
4. Send an application-level "server draining" notice or WebSocket close code `1001 Going Away` where appropriate.
5. Gracefully close active SSE/WS streams so clients reconnect through the LB.
6. Persist cursors/checkpoints and finish in-flight work within deadline.

**Stage B — Platform stop:**
7. Platform sends `SIGTERM`.
8. Spring Boot graceful shutdown rejects new requests and waits out the grace window for in-flight work.
9. After the deadline, the platform may force-kill the process.
10. Clients reconnect to healthy instances and restore subscriptions and cursors.

The framework does not execute steps 1–6 automatically. **Application-level draining is your system's responsibility** whenever streams are infinite.

### Do Not Confuse Readiness and Liveness

- **Readiness**: should this instance receive **new traffic**?
- **Liveness**: is the process broken and needing **restart**?
- **Startup probe**: how long may the app take to start?

During draining, readiness turns false while liveness stays true until shutdown finishes. Making liveness turn false alongside readiness causes Kubernetes to restart or kill the instance **too early**, severing draining connections.

Spring Boot Actuator exposes readiness/liveness health groups via `ApplicationAvailability`. In Kubernetes, `/actuator/health/readiness` and `/actuator/health/liveness` are commonly wired to probes. When using a separate management port, note that probes may not reflect the main web server port; `management.endpoint.health.probes.add-additional-paths=true` can expose them on the main port per Boot docs.

## 14. Kubernetes terminationGracePeriodSeconds: One Budget Covering preStop Too

Example pod termination flow:

~~~text
Pod receives termination request
   |
   +-- Kubernetes marks endpoint terminating, updates LB/endpoints
   +-- preStop hook (if declared and container still running)
   |     +-- app flips readiness/draining
   |     +-- waits for propagation / notifies clients
   |
   +-- SIGTERM delivered to process
   |     +-- Spring Boot graceful shutdown
   |
   +-- Pod hits termination grace deadline if still running
         +-- process may be forcefully killed
~~~

Endpoint updates, hooks, and routing changes can **overlap in time**; this diagram shows concepts, not a strict cluster-wide sequential guarantee.

**`terminationGracePeriodSeconds` is the total budget** for pod termination—not "`preStop` gets N seconds and then Spring Boot gets another N seconds" by default. If `preStop` takes 15s, the app wants 30s graceful shutdown, plus propagation delay, a 30s total budget easily runs out. Align deadlines so the platform **never kills** the app before draining finishes.

### Kubernetes YAML Fragment

~~~yaml
spec:
  terminationGracePeriodSeconds: 60
  containers:
    - name: runtime
      image: example/runtime:demo
      ports:
        - containerPort: 8080
      readinessProbe:
        httpGet:
          path: /ready
          port: 8080
        periodSeconds: 2
        failureThreshold: 1
      livenessProbe:
        httpGet:
          path: /live
          port: 8080
~~~

This is a **PodSpec fragment**, not a complete Deployment. Section 15's demo has `/ready` but **no `/live`**; to pair this fragment with the demo, add a liveness endpoint or point to an existing one. **Never deploy this fragment as-is** without real images, security, resource limits, liveness probes, and termination hooks. Production normally uses standard Actuator probes.

If `preStop` calls a drain endpoint, isolate that endpoint from public traffic or restrict it to the control plane. **Never expose an unauthenticated "disconnect all clients" endpoint to the internet.**

## 15. Runnable Example: WebFlux SSE with Proactive Application Stream Draining

This example builds one application:
- `GET /events` holds an SSE stream open, emitting a `tick` event every 2 seconds.
- `GET /ready` returns **200 READY** when accepting new streams and **503 DRAINING** when draining.
- `GET /status` returns JSON showing draining state and active stream count.
- `POST /demo/drain` flips the draining flag and signals **open SSE streams to complete**.
- Afterward, new `GET /events` requests fail with 503. To reset to a fresh state, **restart the demo app**.

This is a **local operational demo**, not a production WebSocket gateway. The core lesson is **controlled application-level closing** rather than waiting for a process kill.

### 15.1. Creating the Project

In Spring Initializr, select:
- Spring Boot **3.5.x**, Java 17+, Gradle.
- Dependency **Spring Reactive Web** (`spring-boot-starter-webflux`).
- Omit MVC starter so Boot does not choose Servlet stack.

In a Boot 3.5 project with Gradle plugin and dependency management, dependencies block:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

This is only a fragment, not a complete `build.gradle`.

### 15.2. Complete Java Source Code

Create `src/main/java/demo/streams/StreamLifecycleApplication.java`:

~~~java
package demo.streams;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

@SpringBootApplication
@RestController
public class StreamLifecycleApplication {

    private final AtomicBoolean draining = new AtomicBoolean(false);
    private final AtomicInteger activeStreams = new AtomicInteger(0);
    private final Sinks.One<String> drainSignal = Sinks.one();

    public static void main(String[] args) {
        SpringApplication.run(StreamLifecycleApplication.class, args);
    }

    @GetMapping(value = "/events",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> events(
            ServerHttpResponse response) {

        response.getHeaders().setCacheControl("no-store");

        // Hint NGINX not to buffer SSE responses, if config allows.
        response.getHeaders().set("X-Accel-Buffering", "no");

        return Flux.defer(() -> {
            if (draining.get()) {
                return Flux.<ServerSentEvent<String>>error(
                    new ResponseStatusException(
                        HttpStatus.SERVICE_UNAVAILABLE, "draining")
                );
            }

            activeStreams.incrementAndGet();

            return Flux.interval(
                    Duration.ZERO, Duration.ofSeconds(2))
                .map(n -> ServerSentEvent.<String>builder()
                    .event("tick")
                    .data("tick-" + n)
                    .build())
                .takeUntilOther(drainSignal.asMono())
                .doFinally(signal -> activeStreams.decrementAndGet());
        });
    }

    @GetMapping("/ready")
    public ResponseEntity<String> ready() {
        if (draining.get()) {
            return ResponseEntity
                .status(HttpStatus.SERVICE_UNAVAILABLE)
                .body("DRAINING");
        }
        return ResponseEntity.ok("READY");
    }

    @GetMapping("/status")
    public Map<String, Object> status() {
        return Map.of(
            "draining", draining.get(),
            "activeStreams", activeStreams.get()
        );
    }

    // Local demo ONLY; never expose publicly without auth.
    @PostMapping("/demo/drain")
    public Map<String, String> drain() {
        if (draining.compareAndSet(false, true)) {
            drainSignal.tryEmitValue("drain");
        }
        return Map.of("state", "draining");
    }
}
~~~

#### Why Doesn't This Demo Block the Event Loop?

- `Flux.interval(...)` emits periodic events; the handler never calls `Thread.sleep`.
- `Flux.defer(...)` evaluates the draining check when a client actually **subscribes**, not prematurely when constructing the publisher.
- `Sinks.One<String>` broadcasts a one-shot drain signal visible to subscribers even if they subscribe right as the sink emits.
- `takeUntilOther(drainSignal.asMono())` completes the stream cleanly once the drain signal fires.
- `doFinally(...)` decrements the counter on completion, error, or cancellation.
- `AtomicBoolean`/`AtomicInteger` keep fast in-memory state for the demo without blocking network/database I/O.

Two things are **intentionally left unsolved by the demo**: authentication on management/drain endpoints and event replay/persistence. Production designs must add both.

#### Why Not Return 200 and Declare "All Clients Reconnected"?

Once `drain` runs, active streams close and `activeStreams` drops toward 0, yet reconnecting is up to the clients and LB. A single draining JVM cannot verify every client moved to a healthy instance; new requests hitting this draining instance receive 503.

`Sinks.One` completes once, not as a toggleable on/off signal. To test non-draining behavior again, **restart** the app. Do not casually flip `draining=false` once old subscriptions ended, as lifecycle semantics should stay consistent.

### 15.3. application.yml

Create `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

On Boot 3.5, `server.shutdown: graceful` explicitly states the default and does not grant streaming clients automatic replay. `spring.lifecycle.timeout-per-shutdown-phase` caps context shutdown; it **does not invoke** `/demo/drain` by itself.

### 15.4. Starting Up

In the Spring Initializr project root:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

If port 8080 is in use, stop the conflicting process first. Demo URL: `http://localhost:8080`.

## 16. Verifying with curl Across Two Terminals

### 16.1. Initial Readiness

~~~bash
curl -sS -i http://localhost:8080/ready
~~~

Before draining, **HTTP status 200**, response body:

~~~text
READY
~~~

Check status:

~~~bash
curl -sS http://localhost:8080/status
~~~

Before any SSE subscribers, JSON looks like:

~~~json
{"draining":false,"activeStreams":0}
~~~

Key ordering in JSON is not guaranteed by `Map.of`, so tests should parse by key rather than matching raw strings.

### 16.2. Keeping an SSE Stream Open

In **terminal A**, run:

~~~bash
curl -N -i -H 'Accept: text/event-stream' \
  http://localhost:8080/events
~~~

`-N`/`--no-buffer` tells curl to print output immediately without buffering. The server begins emitting events:

~~~text
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-store

event:tick
data:tick-0

event:tick
data:tick-1

event:tick
data:tick-2

~~~

This is **illustrative SSE structure output**; header capitalization/order and spacing after `:` vary by HTTP serializer. However, `data:tick-0`, `tick-1`... every two seconds matches code logic when unaffected by proxies/network buffering.

In terminal B, while SSE is open:

~~~bash
curl -sS http://localhost:8080/status
~~~

Expect `activeStreams` to be **1** with one subscribed SSE client. Opening two SSE connections yields 2.

### 16.3. Triggering Drain from Terminal B

~~~bash
curl -sS -i -X POST http://localhost:8080/demo/drain
~~~

Expected HTTP body:

~~~json
{"state":"draining"}
~~~

Terminal A **ends the stream** after receiving the signal (exact timing depends on cancellation, scheduling, and network). Check readiness:

~~~bash
curl -sS -i http://localhost:8080/ready
~~~

Expected:
- Status **503 Service Unavailable**.
- Body `DRAINING`.

Check status:

~~~bash
curl -sS http://localhost:8080/status
~~~

Once the SSE stream closes:

~~~json
{"draining":true,"activeStreams":0}
~~~

`activeStreams` may not hit 0 instantaneously at the exact microsecond `drain` fires because cleanup is asynchronous. Check again after terminal A closes.

### 16.4. Opening a New SSE Stream After Drain

~~~bash
curl -sS -i http://localhost:8080/events
~~~

Expect status **503** from `ResponseStatusException`. Exact error body details depend on Spring Boot error handling config. `/events` **refuses to open new streams** while draining.

### 16.5. Client Disconnect and Cleanup Observation

Restart the demo to clear draining. Open `curl -N` to `/events`, then press Ctrl+C in the **curl terminal**. Once the server detects socket closure and cancels the subscription, `doFinally` decrements `activeStreams`. Disconnect detection can be delayed or asynchronous; never build cleanup assuming every TCP disconnect fires synchronously on the spot.

**Distinction:** `POST /demo/drain` runs **application draining logic**, not an OS `SIGTERM`. Stopping via an IDE/shell may send SIGINT, SIGTERM, or hard kill depending on the environment. Never treat a Ctrl+C test as proof that platform graceful shutdown coordinates properly with your LB.

## 17. Designing Readiness for Real Environments

The demo `GET /ready` returns plain text for clarity, whereas production normally uses Spring Boot Actuator:
- `/actuator/health/liveness` for liveness.
- `/actuator/health/readiness` for readiness.
- `ApplicationAvailability` and `ReadinessState` for application availability state.

When initiating drain, publish an availability change event, e.g.:

~~~java
// Fragment inside a class holding ApplicationContext context.
AvailabilityChangeEvent.publish(
    context, ReadinessState.REFUSING_TRAFFIC);
~~~

Corresponding imports:
- `org.springframework.boot.availability.AvailabilityChangeEvent`
- `org.springframework.boot.availability.ReadinessState`
- `org.springframework.context.ApplicationContext`

This **does not** replace full shutdown orchestration. Setting readiness false still needs propagation time for LB/ingress to stop routing new traffic and drain active streams. Once the HTTP server stops accepting new connections, probes might stop responding; do not wait until connectors close before expecting a readiness route to return HTTP 503.

When using a dedicated management port, expose `/readyz` and `/livez` on **the main server port** via `management.endpoint.health.probes.add-additional-paths=true` where appropriate. Avoid tying liveness to transient DB/broker blips so you do not trigger cascading pod restarts.

## 18. Client Reconnect: Use Backoff and Jitter to Prevent Reconnect Storms

When pod A drains, thousands of browsers can see SSE/WebSocket close simultaneously. If all reconnect at once, pod B or the LB gets hit by a **thundering herd**:
- TLS/WebSocket handshake spikes.
- Redis/broker subscriptions recreated all at once.
- CPU, connection pools, and memory surge.
- Clients time out and retry again in a vicious cycle.

### Browser SSE EventSource

**Same-origin** frontend example when the app serves the page on the same origin as the API:

~~~javascript
const stream = new EventSource("/events");

stream.addEventListener("tick", event => {
  console.log("event:", event.data);
});

stream.onerror = () => {
  console.warn("SSE disconnected; browser may reconnect");
};

// Close explicitly when the user leaves the view:
window.addEventListener("pagehide", () => stream.close());
~~~

`EventSource` automatically reconnects per browser rules and the SSE `retry:` field. **Never instantiate a new `EventSource` inside every `onerror`** without closing the old instance—that multiplies connections. Across origins, configure CORS properly; `EventSource` cookie/credential behavior depends on `withCredentials` and SameSite/CORS rules.

Apps can emit `retry: 5000` in the SSE stream to hint reconnect delay in milliseconds, though client implementations may enforce their own policies. To avoid synchronized reconnects, use a client reconnection manager adding jitter and retry budgets, especially with custom WebSocket clients.

### WebSocket Reconnect Fragment

~~~javascript
// Illustrative fragment managing frontend retries.
let attempts = 0;

function connectSocket() {
  const socket = new WebSocket("wss://api.example.com/ws");

  socket.onopen = () => {
    attempts = 0;
    // Send subscription/cursor after authentication succeeds.
  };

  socket.onclose = () => {
    const base = Math.min(30000, 1000 * 2 ** attempts);
    const jitter = Math.floor(Math.random() * 500);
    attempts = Math.min(attempts + 1, 5);
    setTimeout(connectSocket, base + jitter);
  };
}

connectSocket();
~~~

This snippet illustrates **backoff with jitter** only—it does not yet handle offline state, logout, `pagehide`, duplicate sockets, auth expiry, or max retry budgets. Production needs cancellation/cleanup and guarantees that only one active connection manager owns each logical session.

**Never reconnect clients directly to an old pod's IP.** Clients connect via the public LB/service hostname so the LB routes to healthy targets. If clients receive per-instance URLs (e.g., sharding), keep service discovery/redirects up to date.

## 19. WebSocket Close Codes: Shutdown vs. Dead Network

Per RFC 6455, a WebSocket server can send a **Close frame**:
- `1000 Normal Closure`: normal protocol/application completion.
- `1001 Going Away`: an endpoint is shutting down or leaving (e.g., server shutdown).
- `1008 Policy Violation`: closed due to policy; do not use as a generic code for normal reconnects.
- `1011 Internal Error`: server encountered an unexpected error.
- `1006 Abnormal Closure`: **must never be sent as a Close frame code**; used locally by receivers when a connection disappears abnormally without a valid close frame.

A server draining gracefully can:
1. Reject **new handshakes**.
2. Send an application-level node-switch notice if needed.
3. Send WebSocket close `1001`.
4. Close sessions after a short wait.
5. Let clients reconnect and restore subscriptions from shared state.

Clients should distinguish `1001` from policy/auth failures: reconnecting makes sense on server going-away, whereas **403/1008 due to missing permissions** should not retry forever. On abrupt network drops, browsers often see code 1006; apply backoff and check network online state.

**Never rely on Close frames always reaching the browser.** On process kills, LB TCP resets, or dropped links, clients often miss graceful close frames. Recovery logic must work even without a "server going away" notice.

## 20. HTTP/2 GOAWAY and Long-Lived Connections

In HTTP/2, **one connection can carry many active streams**. When a server/LB prepares to stop, `GOAWAY` signals that the endpoint will accept no new streams on that connection while allowing started streams time to finish.

Example:

~~~text
HTTP/2 connection
  |
  +-- Stream 1: GET /events (SSE still open)
  +-- Stream 3: GET /catalog (completed)
  +-- Stream 5: POST /orders (in progress)
  |
  +-- GOAWAY (last-stream-id = N)
       |
       +-- No new streams created on this connection
       +-- In-flight streams allowed to complete within limits
       +-- Client opens a new connection when needed
~~~

Per **RFC 9113 §6.8**, `GOAWAY` carries `last-stream-id` identifying the highest peer-initiated stream ID the endpoint may have processed. Clients know stream IDs above that limit **were not processed** and can safely retry them on a new connection. For stream IDs less than or equal to it, **never automatically retry non-idempotent requests** when outcomes are ambiguous.

An SSE stream may still be open when `GOAWAY` arrives; once the grace window expires, the connection/stream is cut. `GOAWAY` **does not automatically resend missed events**. Apps still need event IDs + replay as covered in section 11.

Do not assume every proxy emits exact textbook `GOAWAY` sequences or that client libraries safely retry every business request. Test with real HTTP/2 clients and inspect frames where needed.

## 21. How Spring MVC SseEmitter and Spring WebFlux Differ

Spring MVC/Servlet supports `SseEmitter` and Servlet async request handling. Spring WebFlux supports `Flux<ServerSentEvent<T>>` and streaming publishers.

| Topic | Spring MVC / SseEmitter | Spring WebFlux / Flux SSE |
|---|---|---|
| Primary lifecycle | Servlet async request | Reactive subscription |
| Sending data | `SseEmitter.send(...)` can perform blocking I/O per container | Publisher emission / HTTP writer |
| Timeouts | `SseEmitter` timeout + MVC async/container configs | HTTP server/proxy/operator timeouts per pipeline |
| Client disconnect | `onCompletion`/`onTimeout`/`onError` callbacks | `doFinally`/cancellation/error signals |
| App shutdown | Coordinate emitter completion and Boot shutdown | Coordinate sink/signal completion and Boot shutdown |
| Scaling/replay | Needs external shared state | Also needs external shared state |
| Backpressure | Must govern async executors/sends and slow clients | Reactive demand coordinates pipeline, yet queues still need bounds |

**Fragment** for Spring MVC:

~~~java
@GetMapping(path = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public SseEmitter stream() {
    SseEmitter emitter = new SseEmitter(300_000L);
    emitter.onCompletion(() -> removeFromRegistry(emitter));
    emitter.onTimeout(() -> removeFromRegistry(emitter));
    emitter.onError(error -> removeFromRegistry(emitter));

    registerAndScheduleEvents(emitter);
    return emitter;
}
~~~

This **is not a runnable class**: `removeFromRegistry`, `registerAndScheduleEvents`, and the registry/executor must be implemented in an MVC project. `300_000L` is 300,000 milliseconds (5 minutes) representing an emitter async timeout; **it is not NGINX/LB idle timeout**. Real apps must handle blocking `send()` / `IOException`, cleanup on complete/timeout/error, and executor/capacity configuration.

For new systems aiming at thousands of SSE streams, evaluate WebFlux/Reactor Netty or dedicated event-streaming solutions, yet **never declare WebFlux universally faster than MVC** without benchmarking your actual workload, I/O, and deployment.

## 22. Backpressure, Slow Consumers, and Connection Resources

Every open connection consumes resources:
- Socket/file descriptor and TLS state.
- Memory for buffers, pipelines/sessions, and metadata.
- Timers, scheduled tasks, and heartbeats.
- Broker/topic subscription state or session registry entries.
- Outbound queues if the client reads slowly.

**Never leave an unbounded queue per client.** If a client drops off the network undetected, queued events grow memory until OOM. Reactive streams provide backpressure at key points, yet **cannot prevent** overflows inside WebSocket adapters, brokers, or app sinks on their own.

Strategies:
1. Bound outbound message sizes, buffers, and send durations.
2. Pick overflow policies per business rules: drop non-critical updates, coalesce latest state, disconnect slow clients, or persist and resume.
3. Never silently drop events requiring exact delivery (e.g., financial audits).
4. Cap concurrent connections per user/IP/tenant to guard against handshake abuse.
5. Clean up subscriptions on disconnect, drain, or timeout.
6. Monitor active connections, publish-to-send lag, queue depths, and JVM memory/GC.

**SSE is one-way**, suited for server→client status and notifications; never try forcing bidirectional client commands through SSE. On WebSocket, enforce message size limits, auth, and per-message policies.

## 23. Security of Long-Lived Connections

Long-lived connections often outlive access tokens or session state. Answer clearly:
- Is **handshake** auth sufficient for the whole lifetime?
- When tokens expire, users log out, lose roles, or get locked, can the connection keep reading data?
- Can the server prompt clients to refresh auth and reconnect cleanly?
- Are topic subscriptions authorized **per topic**?
- Does WebSocket handshake validate `Origin` properly?
- Is public edge traffic encrypted via `wss://`/`https://`?

**WebSocket does not follow browser CORS identically to fetch/SSE.** Enforce Origin checks in the handshake, CSWSH/CSRF defenses with cookie auth, and dedicated authentication/authorization. For cross-origin SSE via EventSource, configure CORS appropriately; browser `EventSource` cannot set arbitrary custom request headers like a general HTTP client.

If using sticky cookies for load balancing, they are **not authorization tokens**. When a client reconnects to Pod B, Pod B must re-verify auth and topic permissions rather than trusting stale metadata from the previous pod.

**The demo's drain endpoint has no auth**: never expose it publicly in real systems. Protect control-plane hooks and management endpoints and audit their use.

## 24. Observability: Measure Lifecycle, Not Just Request Rate

Useful metrics:

| Group | Recommended Metrics |
|---|---|
| Connections | Active SSE/WS per instance, opens/closes, connection age, idle duration |
| Lifecycles | Close reasons: normal, going-away, timeout, error, proxy reset, shutdown |
| Client recovery | Reconnect attempts, backoff, time to reconnect, recovered clients/min |
| Data integrity | Last delivered/acked event ID, replay count, duplicate count, gap count |
| Shutdown | Readiness transition time, drained connections, remaining at SIGTERM, forced kills |
| Load balancing | Active connections per backend, new handshake distribution, draining target age |
| Proxy | 499/502/503/504 (per NGINX/vendor), upstream resets, read timeouts |
| Runtime | Reactor event-loop lag, CPU, memory, FD counts, TLS overhead, publish queues |
| SLO | Connected uptime, event delivery latency, % sessions recovered with zero gaps |

**Never place user IDs, raw JWTs, WebSocket session IDs, connection IDs, or full event IDs in high-cardinality Prometheus labels**; use route templates, protocols, close-reason classes, instance/pod names, and bounded dimensions. Tracing and structured logs may record safe correlation IDs under privacy/security controls.

Distinguish **client-initiated disconnects** from **server-initiated drains** and **proxy timeouts**. Seeing only `socket closed` leaves root causes ambiguous until correlated with proxy/LB logs, timestamps, and close codes.

### Locating Which Layer Dropped the Connection

Test systematically:
- Direct call to Boot origin in test network: does the stream stay alive?
- Through NGINX: cut after 60s silence?
- Through ALB/CDN: cut even after raising NGINX timeout?
- Emit app heartbeats and verify bytes actually reach the client?
- Verify NGINX buffering is off and the app flushes responses?
- Compare disconnect timestamps against rollout/pod deletion and SIGTERM logs?

When a drop isolates to a specific hop, fix **that exact layer** instead of turning on "infinite timeouts" everywhere.

## 25. Pre-Rolling-Deploy Testing Matrix

| Scenario | How to Trigger | Pass Criteria |
|---|---|---|
| Long-silent SSE | Suppress business events; send heartbeats only | Not severed by LB/proxy before desired threshold |
| SSE with no heartbeat | Stop all bytes in test | Identify which hop times out rather than mystery drops |
| NGINX buffering | Toggle buffering on vs. off | Event latency/chunks flush promptly |
| WS idle > 60s | Send zero data/pings | Observe idle timeout; then verify ping/pong keeps alive |
| WebSocket disconnect | Restart target / close socket | Client backs off, reconnects, and restores subscriptions |
| SSE reconnect | Brief network drop | `Last-Event-ID`/replay leaves zero gaps with durable store |
| 2 instances | Hold 1,000 connections, scale out | Confirm old sockets do not migrate; new ones distribute evenly |
| Scale-in | Flip readiness false then drain | New handshakes stop hitting draining target post-propagation |
| Graceful shutdown | SIGTERM with open SSE/WS | App drain coordinates cleanly within grace budget |
| Hard kill | SIGKILL / process crash | Client recovery still succeeds without relying on close frames |
| HTTP/2 GOAWAY | Simulate LB/backend draining | Client opens new connection; idempotent/non-idempotent requests handled safely |
| Slow consumer | Throttle network receive | Zero OOM from unbounded queues; overflow policy runs |
| Auth expired | Expire token while WS stays open | Server stops streaming forbidden data |
| Gateway error | Force upstream 502/503 | Proper observability and client backoff/retry behavior |

`1,000 connections` in the table is an illustrative test load, not a universal capacity target. Base scale targets on FD/memory/CPU/broker limits and real SLOs.

## 26. Recommended Rollout Sequence

For a **Browser → CDN/ALB → NGINX → Spring Boot** architecture serving SSE/WebSocket:

1. **Map every hop** with TLS termination, HTTP versions, and proxy routes.
2. Document exact **idle timeouts, absolute lifetimes, read timeouts, async timeouts, and deregistration delays** per hop.
3. Choose a **heartbeat interval** safely below the minimum idle timeout; verify bytes traverse every hop.
4. For SSE, disable **proxy buffering** on streaming routes; for WS, forward Upgrade headers cleanly.
5. Use an external store/broker for **event cursors, subscription state, and recovery**, never just RAM + stickiness.
6. Before rollout, **mark instances unready first** and wait for propagation.
7. Proactively notify/close SSE/WS streams to drain active connections while clients back off.
8. Send SIGTERM and let Boot graceful shutdown finish in-flight work within budget.
9. Ensure Kubernetes termination grace **covers** preStop + Boot grace + overhead.
10. Test ungraceful drops, not just graceful shuts. Critical data must support replay/ack/dedup.
11. Monitor reconnect storms, delivery gaps, and forced terminations.
12. Re-verify all defaults after upgrading Boot, web servers, NGINX, ingress, or cloud LBs.

### Sample Timing Budget Table

| Test Value | Meaning |
|---|---|
| SSE/WS heartbeat: 20s | Keeps traffic flowing safely ahead of idle cutoffs |
| ALB idle timeout: 60s | A hop capable of closing silent connections |
| NGINX `proxy_read_timeout`: 75s | Max silence between consecutive upstream reads |
| Pre-drain propagation window: 10s | Illustrative window for LB/endpoint updates |
| Boot graceful shutdown phase: 30s | Budget waiting for in-flight requests to finish |
| Kubernetes `terminationGracePeriodSeconds`: 60s | Total budget covering all steps above with safety margin |

This is a **planning example**, not a universal production template. Propagation cannot be guaranteed to finish in 10s in every cluster. Furthermore, unless streams are proactively closed, waiting 30s in grace still fails even under a 60s pod budget. Coordinate **all clocks** using real measurements.

## 27. Common Errors and Fixes

| Symptom | Likely Cause | Fix |
|---|---|---|
| SSE drops right around 60s silence | ALB/NGINX idle or `proxy_read_timeout` | Identify hop; add heartbeats + buffering off + aligned timeouts |
| WebSocket 101 succeeds, closes 1 minute later | Upstream silent past proxy read timeout | Send WS ping/pong and inspect proxy logs |
| NGINX delivers SSE in large batches | Response buffering | Set `proxy_buffering off` on streaming route |
| Raised Spring timeout yet still disconnects | Smaller cutoff at CDN/LB/ingress | Trace path and fix true bottleneck |
| Steady HTTP/2 PINGs yet ALB still closes | ALB ignores HTTP/2 PING for idle timer | Emit traffic counted as active by LB and verify |
| Many clients reconnect simultaneously post-deploy | Unstaggered draining, unjittered reconnects | Pre-drain + client backoff/jitter + capacity headroom |
| Scaled out yet old pods hold most sockets | Existing sockets do not auto-rebalance | Expect skew, rolling drain, or enforce max connection age |
| Reconnect to new pod loses session/topics | Local-only state; stickiness fails on pod death | Shared state, broker, and subscription recovery |
| SSE duplicates events after reconnect | Replay lacks stable cursor/dedup | Stable event IDs, client dedup/ack |
| SSE misses events between drop and reconnect | No durable replay | `Last-Event-ID` + event log + atomic catch-up/live handoff |
| WebSocket closes with 1006 instead of 1001 | TCP reset/hard kill/proxy drop without close frame | Recover even without graceful close frames |
| Graceful stop hangs until deadline | Long-lived requests never auto-complete | Application-level drain/close streams before SIGTERM |
| Pod gets SIGKILL despite Boot grace=30s | `terminationGracePeriodSeconds` too tight after preStop | Compute total budget and measure |
| Readiness false triggers immediate pod restart | Liveness confused with readiness | Separate probes and lifecycle states |
| 503 on new streams after drain | Instance intentionally refusing new streams | LB routes clients to healthy targets; retry with backoff |
| Browser CORS error on EventSource | Cross-origin SSE blocked | Configure CORS and cookie policies properly |
| WS handshake returns 403 Origin mismatch | Origin/auth policy rejection | Verify frontend origin instead of wildcarding all |
| FDs/memory climb after many disconnects | Uncleaned subscriptions, unbounded buffers | `onCancel`/`doFinally`/registry cleanup, bound queues |
| JS spawns duplicate connections on `onerror` | Code repeatedly creates fresh EventSource instances | Single connection manager; close old instances |
| HTTP/2 GOAWAY causes duplicate POST retries | Client retries non-idempotent request on ambiguous outcome | Idempotency keys and status reconciliation |

## 28. Review Questions

**1.** Does `proxy_read_timeout 75s` force an SSE connection to close after 75 seconds total?

**Answer:** No. In NGINX, it bounds silence between upstream reads; a response emitting bytes regularly can live far longer.

**2.** Why can an SSE stream sending heartbeats every 20 seconds still drop after a long duration?

**Answer:** Heartbeats may be buffered by a proxy, miss a hop, or hit an **absolute connection lifetime, rollout, or draining** limit rather than an idle timeout.

**3.** A WebSocket is connected to Pod A. Does scaling out Pod C migrate that socket to C?

**Answer:** No. LBs normally pick backends only for new connections/handshakes, never migrating live TCP/WebSocket sockets.

**4.** Do sticky sessions guarantee zero data loss when Pod A restarts?

**Answer:** No. They neither keep Pod A alive nor transfer local RAM to Pod B. Shared state and replay/recovery are required.

**5.** Does Boot 3.5 strictly require adding `server.shutdown: graceful` to turn on graceful shutdown?

**Answer:** Per Boot 3.5 docs, graceful shutdown **is enabled by default**. Declaring it explicitly aids clarity; use `spring.lifecycle.timeout-per-shutdown-phase` to tune the wait budget.

**6.** Does raising the grace period to one hour guarantee WebSockets won't drop during deploys?

**Answer:** No. Streams may never finish on their own, platforms/LBs enforce their own deadlines, and pods can still be terminated. Proactive draining and client recovery are needed.

**7.** Is `terminationGracePeriodSeconds` added on top of `preStop` duration before counting down?

**Answer:** No. It is a shared total termination budget covering hooks, shutdown, and overhead.

**8.** If SSE emits `id`, does Spring automatically replay missed events when the browser reconnects?

**Answer:** No. `EventSource` can send `Last-Event-ID`, yet the server must provide a durable event log/cursor and replay logic.

**9.** Can a server send WebSocket close code 1006 inside a Close frame?

**Answer:** No. 1006 indicates an abnormal drop detected locally by the receiver and must never be sent in a wire frame per RFC 6455.

**10.** Does HTTP/2 `GOAWAY` guarantee all in-flight POSTs were rolled back?

**Answer:** No. `GOAWAY` reports the highest stream ID that might have been processed; ambiguous outcomes on non-idempotent operations still require idempotency/reconciliation.

**11.** If ALB idle=60s and the app emits business events every 5 minutes, is raising only Spring's request timeout enough?

**Answer:** No. Address the idle hop by emitting heartbeats/bytes through the proxy or adjusting ALB policy.

**12.** Why keep liveness true while readiness turns false during draining?

**Answer:** The instance is still finishing existing connections; readiness false halts new traffic, whereas liveness false triggers premature restarts/kills.

### Extended Hands-On Practice

Starting from the section 15 app:
1. Raise `Flux.interval` from 2s to 90s behind a test NGINX instance and compare connections with and without heartbeats.
2. Set `proxy_read_timeout 10s` and observe the stream dropping after 10s of silence. Then add SSE comment heartbeats every few seconds to keep it alive without setting timeouts to "infinite".
3. Run two instances behind a test LB, connect multiple SSE clients, and inspect active connections per instance. Add a third instance and verify existing sockets stay put.
4. Call `/demo/drain` on one instance and verify readiness, SSE completion, and client reconnection to a healthy instance.
5. Design a durable event sequence supporting `Last-Event-ID`; verify zero-gap, zero-duplicate replay across restarts.
6. In a test cluster, send SIGTERM while streams are open, measure actual app shutdown time vs. pod termination budget, and tune budgets accordingly.

## 29. Official References

- [Spring Boot 3.5 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html)
- [Spring Boot 3.5 — Actuator Kubernetes Liveness/Readiness](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
- [Spring Framework — WebFlux Server-Sent Events](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html)
- [Spring Framework — Asynchronous Requests in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html)
- [Spring Framework — Reactive WebSockets](https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html)
- [NGINX — WebSocket Proxying](https://nginx.org/en/docs/http/websocket.html)
- [NGINX — ngx_http_proxy_module: proxy_read_timeout and proxy_buffering](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)
- [AWS ALB — Connection idle timeout and HTTP client keepalive duration](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/edit-load-balancer-attributes.html)
- [AWS ELB — Target Deregistration Delay](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/edit-target-group-attributes.html)
- [Kubernetes — Pod Lifecycle / Termination of Pods](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#termination-of-pods)
- [RFC 9113 — HTTP/2: PING and GOAWAY](https://www.rfc-editor.org/rfc/rfc9113.html)
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455.html)
- [WHATWG HTML Living Standard — Server-Sent Events](https://html.spec.whatwg.org/multipage/server-sent-events.html)

**Final takeaway:** long-lived connections are governed by **the strictest hop**, not Spring Boot alone. Heartbeats rescue idle connections only when bytes traverse proxies; load balancers never migrate live sockets; graceful shutdown waits for in-flight work only within a finite window. Sound production designs combine **aligned timeouts, unbuffered streaming, readiness → draining → SIGTERM, backoff reconnects, and instance-independent state/event recovery**.
