# Troubleshooting Early WebSocket Disconnects, Buffered SSE, and Response-Already-Committed Errors

Spring Cloud Gateway typically forwards short-lived HTTP requests. WebSocket and Server-Sent Events (SSE) have a different lifecycle: connections can stay open for minutes or hours, data arrives incrementally, and the response may have already started before the backend encounters an error. Consequently, timeout, filter, or proxy settings suitable for standard REST APIs can still drop streaming connections or deliver events in delayed bursts.

This lesson focuses on three common symptoms:

- WebSocket handshake succeeds, yet the connection closes immediately afterward or at fixed intervals.
- SSE returns `200 OK`, yet the client only receives batches of events after waiting.
- Gateway or a custom filter reports that the response is already committed and refuses to change status or write an error body.

These issues can occur simultaneously. Trace the entire request path: client → CDN/WAF or ingress → load balancer → Spring Cloud Gateway → target service. Each layer may enforce its own timeout, buffering, or connection-closing policy.

## 1. Distinguish Symptoms Before Fixing

| Symptom | Signs to Confirm | Common Root-Cause Group |
|---|---|---|
| WebSocket never receives `101 Switching Protocols` | Handshake returns 4xx/5xx or redirects | Route mismatch, wrong URI scheme, auth, `Origin`, TLS, or handshake headers |
| WebSocket gets `101` then closes | Connection opens then drops after a fairly consistent interval | Idle timeout, missing ping/pong, backend closes session, proxy lacks upgrade support, or reconnect bug |
| SSE returns `200` yet events arrive in batches | Backend emits steadily, yet client sees nothing right away | Proxy buffering, compression, body-aggregating filter, caching, or client buffering |
| SSE disconnects after a period | Disconnection interval may repeat regularly | Response timeout, ingress/load-balancer idle timeout, connection lifetime limit, or upstream error |
| `response already committed` | Error occurs when a filter or error handler tries to set status/headers or write body | Response already sent headers or partial data; multiple components writing response; mid-stream failure |

Do not conclude that Gateway closed the connection merely because the client connects through Gateway. First test calling the target service directly from the same network environment and compare against going through Gateway. If direct calls fail too, inspect the service and downstream infrastructure. If only calls through Gateway fail, focus on Gateway's routes, filters, and HTTP client config, then check the ingress or load balancer ahead of it.

## 2. Gather Evidence from the Client

### Checking SSE

Use `curl -N` to disable output buffering in curl. If the endpoint requires a token, include the appropriate auth header:

```bash
curl -iN --http1.1 \
  -H 'Accept: text/event-stream' \
  -H 'Authorization: Bearer <token>' \
  https://gateway.example.com/events
```

Observe:

- Status code and time until response headers arrive.
- Whether `Content-Type` is `text/event-stream`.
- Whether events arrive at the backend's emission cadence or only appear after delays.
- When the connection closes and whether it repeats at fixed intervals.

SSE uses line-based framing. Each event normally ends with a blank line, for example:

```text
id: 42
event: update
data: new-status

```

If the backend writes data without terminating events with a blank line or without flushing, the client may keep waiting even while the TCP connection remains open. Therefore, verify how the backend produces events, not just Gateway config.

### Checking WebSocket

`curl` is not a full WebSocket testing tool. Use `wscat`, `websocat`, or an application WebSocket client:

```bash
wscat -c wss://gateway.example.com/ws
```

Record whether the handshake returns `101 Switching Protocols`, duration from connect to close, close code, and close reason if provided. Test the same endpoint directly on the target service to isolate the layer.

A successful handshake only proves the HTTP upgrade completed. It does not prove the connection will stay alive, the backend is healthy, or proxies will keep the connection open indefinitely.

## 3. Fixing Early WebSocket Disconnects

### Declare Routes with a WebSocket Scheme

Spring Cloud Gateway recognizes WebSocket routes via the `ws` or `wss` scheme. Example routing directly to a service:

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: chat-websocket
          uri: ws://chat-service:8080
          predicates:
            - Path=/ws/**
          filters:
            - StripPrefix=1
```

When discovering the service via Spring Cloud LoadBalancer, use the `lb:ws` scheme:

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: chat-websocket
          uri: lb:ws://chat-service
          predicates:
            - Path=/ws/**
          filters:
            - StripPrefix=1
```

Choose the configuration matching your actual deployment. If the backend listens on `/ws/**`, omit `StripPrefix=1`; if the backend listens only on `/`, keep it. When using `RewritePath`, test the expression against a real request to confirm the rewritten path matches the backend endpoint.

Items to verify:

1. Do predicates match the exact handshake path and method? Another REST route may intercept the request ahead of the WebSocket route if its conditions are too broad.
2. Does the target URI use `ws://`, `wss://`, or `lb:ws://` appropriately? Using `http://` for a route requiring WebSocket upgrade is misconfigured.
3. Does any filter inadvertently strip or alter handshake headers like `Upgrade`, `Connection`, `Sec-WebSocket-Key`, and `Sec-WebSocket-Protocol`? Let Gateway handle the handshake natively; avoid forcing fixed handshake headers via filters without clear evidence.
4. Does the backend accept the client's `Origin`, subprotocol, and authentication credentials?
5. When using `wss`, certificates and trust chains must be valid at every TLS hop. Distinguish client-to-ingress TLS from Gateway-to-backend TLS.

### Distinguish Connect Timeout from Idle Timeout

`connect-timeout` bounds how long it takes to establish the upstream connection. It is not a keepalive mechanism for an open WebSocket. A connection can complete the handshake and later be closed by an idle timeout at ingress, load balancer, firewall, NAT, or backend.

Compare timeout configs across all layers. If connections consistently close after ~60 seconds, for example, look for a ~60-second limit across each proxy and service instead of arbitrarily bumping Gateway timeouts. Choose bounds matching expected idle intervals and system resources.

For long-lived connections, implement ping/pong heartbeats or application-level keepalive messages. Heartbeats must fire more frequently than the shortest idle timeout along the path. Verify clients, backends, and proxies handle heartbeats properly; never assume every layer emits pings automatically.

When clients reconnect, provide a session recovery strategy: session identifiers, resume tokens, or state sync across replicas. Sticky sessions help only when the app truly stores local state; they do not replace heartbeats and cannot defeat timeouts.

### Security Considerations After Upgrade

Gateway HTTP filters process the handshake request. Once upgraded, WebSocket frames flow through the WebSocket handling path; never treat Gateway's `RequestRateLimiter` as a per-frame or per-message rate limiter. If you need per-message rate limits, frame size limits, per-action authorization, or anti-spam controls, enforce them inside the WebSocket service or a dedicated message-processing layer.

Authenticate the handshake before upgrading, validate `Origin` per app policy, and cap message sizes in the backend. Never log tokens, sensitive cookies, or private frame contents.

## 4. Fixing Buffered SSE

### Keep Responses in Streaming Mode

A WebFlux backend can return `Flux<ServerSentEvent<T>>` or a publisher compatible with `text/event-stream`. Example:

```java
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofSeconds(10))
        .map(sequence -> ServerSentEvent.builder("update-" + sequence)
            .id(Long.toString(sequence))
            .event("update")
            .build());
}
```

Each event must serialize in proper SSE format and flush immediately so clients receive it right away. For streams that may stay quiet for long intervals, backends can emit heartbeat comments:

```text
: keep-alive

```

Comments do not trigger application data events, yet keep the connection visibly active and reduce the chance a proxy deems it idle. Base the heartbeat interval on the shortest idle timeout in the infrastructure.

Responses should carry `Content-Type: text/event-stream` and an appropriate cache policy, typically `Cache-Control: no-cache` or `no-store` depending on data sensitivity. If Nginx sits upfront, `X-Accel-Buffering: no` may be needed per Nginx configuration. This header is Nginx-specific, not a universal directive for every proxy.

Do not treat `Transfer-Encoding: chunked` as a mandatory requirement. HTTP/1.1 typically uses chunked transfer encoding when content length is absent, whereas HTTP/2 streams data via DATA frames. What matters is verifying events reach the client continuously rather than being held and batched into one large response.

### Find the Buffering Layer

Inspect each of these in order:

- **Backend:** are events emitted and flushed on cadence; does any code collect the publisher into a `List`, `collectList()`, or full body before returning?
- **Gateway filters:** are `ModifyResponseBody`, response caches, body-draining filters, or logic collapsing `Flux<DataBuffer>` into one large buffer active? Those break streaming.
- **Compression:** try disabling compression for the SSE endpoint at the compressing layer if observation shows the compressor holding data. Some compressors or proxies flush only once a buffer threshold fills.
- **Ingress/CDN:** check response buffering, caching, compression, and proxy rules for `text/event-stream`. Disable buffering at the exact layer performing buffering.
- **Client:** use `curl -N` or a streaming-capable SSE client to rule out buffering by the test tool.

Never apply response rewrites, caching, or retries mechanically to long-lived streams. Once some events have reached the client, retries cannot transparently replay as if nothing arrived. To recover after disconnects, design resumption via event IDs and the `Last-Event-ID` header on the backend.

### Configure Timeouts per Route

A short timeout fits regular read APIs, not long-lived streaming responses. The example below sets default HTTP client timeouts while disabling the global response timeout on the SSE route via route metadata:

```yaml
spring:
  cloud:
    gateway:
      httpclient:
        connect-timeout: 5000
        response-timeout: 30s
      routes:
        - id: event-stream
          uri: lb://event-service
          predicates:
            - Path=/events/**
          filters:
            - StripPrefix=1
          metadata:
            response-timeout: -1
```

`connect-timeout` in the example is in milliseconds. Global `response-timeout` is a duration; per-route metadata `response-timeout` takes milliseconds, where `-1` disables the global response timeout for that route per Spring Cloud Gateway's mechanism. Verify this behavior against your running Spring Cloud Gateway version and re-test after upgrades.

Disabling Gateway's response timeout does not disable idle timeouts on ingress, load balancers, CDNs, firewalls, or backends. Those layers still need compatible settings and heartbeats if streams have long quiet periods. Never set infinite timeouts globally across all routes when only one endpoint streams.

## 5. Understanding Response-Already-Committed Errors

In WebFlux, a response is committed once status/headers have been sent or body bytes begin writing to the connection. Prior to that moment, filters or error handlers can choose status and headers. Once committed, the application cannot switch `200 OK` to `500 Internal Server Error`, nor replace already-sent bytes with a fresh JSON error body.

This happens easily with SSE and streaming responses: Gateway already sent `200` headers, the client already received several events, and then the backend errors or the upstream times out. An error handler runs and tries to write a separate JSON error response. The result is typically a `response already committed` error, a write failure, or an abrupt mid-stream disconnect.

Other common causes:

- A custom `GlobalFilter` writes a body and still calls `chain.filter(exchange)`, leaving two components writing the response.
- A filter sets status/headers after `chain.filter(exchange)` completed or after the body flushed.
- `onErrorResume` unconditionally writes an error body without checking whether the response is committed.
- Multiple code paths call `writeWith` or `writeAndFlushWith`.
- A body-transforming filter consumes a publisher while another filter attempts to read the consumed publisher again.

### Register Headers Before the Response Commits

If you need to add a header, register the callback before invoking the filter chain:

```java
@Override
public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
    ServerHttpResponse response = exchange.getResponse();
    response.beforeCommit(() -> {
        response.getHeaders().set("X-Gateway-Processed", "true");
        return Mono.empty();
    });
    return chain.filter(exchange);
}
```

Never mutate headers inside callbacks running after the response has already been sent. If you need to observe a stream, decorate the response in a WebFlux-idiomatic way that preserves streaming; avoid buffering the entire body into a byte array just to measure or log.

### Handle Errors While Checking Committed State

For normal responses that have not sent data yet, filters can craft an error response. Once committed, only log the error and terminate the publisher/connection cleanly per lifecycle; never attempt to send a second status or body:

```java
return chain.filter(exchange).onErrorResume(error -> {
    ServerHttpResponse response = exchange.getResponse();

    if (response.isCommitted()) {
        log.warn("Error occurred after response was already committed", error);
        return Mono.error(error);
    }

    response.setStatusCode(HttpStatus.BAD_GATEWAY);
    response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
    byte[] body = "{\"error\":\"upstream_failure\"}"
        .getBytes(StandardCharsets.UTF_8);
    DataBuffer buffer = response.bufferFactory().wrap(body);
    return response.writeWith(Mono.just(buffer));
});
```

This snippet illustrates handling in a custom filter; add imports, logger, and align the error contract with your application. It cannot turn a partially sent stream into a complete response. For streams, clients should treat mid-stream closure as signal loss and use the protocol's reconnect/resume mechanism.

## 6. Ordered Isolation Workflow

Perform these steps using the same request ID or test session:

1. **Identify connection type.** For WebSocket, verify `101` handshake and close codes. For SSE, verify `200`, `Content-Type`, and event cadence. For committed errors, determine how much data was already sent before the error hit.
2. **Call upstream directly.** Use identical path, auth headers, and payload. If the failure reproduces directly, fix the service before touching Gateway.
3. **Inspect the route.** Confirm predicates, URI scheme, load balancing, and post-`StripPrefix`/`RewritePath` path.
4. **Audit filters.** Look for filters that drain bodies, mutate response bodies, cache, retry, fall back, or write responses. Temporarily disable suspected filters in a test environment to pinpoint the actor.
5. **Compare timeouts.** Match disconnect times against response timeouts, idle timeouts, connection lifetimes, and duration caps across every proxy. A repeating interval points straight to the matching config.
6. **Check buffering.** Compare when the backend emits an event, when Gateway receives it, and when the client receives it. Disable compression/buffering one layer at a time in tests to find where data stalls.
7. **Correlate logs and metrics.** Propagate a correlation ID across hops; capture route ID, upstream, duration, close/error cause, and committed state. Never log tokens or sensitive payloads.
8. **Run long-lived connection tests.** Run past the expected idle timeout, test quiet periods with zero events, test reconnects, and test restarting a backend replica.

If Gateway Actuator metrics are enabled, monitor Gateway request metrics—commonly named `spring.cloud.gateway.requests`—alongside Reactor Netty connection and error metrics. Exact names and tags depend on version, config, and registry. Expose only needed Actuator endpoints and protect access.

## 7. Quick Decision Table

| Check Result | Next Step |
|---|---|
| WebSocket lacks `101` | Check `ws`/`wss` route, predicates, auth, `Origin`, subprotocols, and TLS handshake |
| WebSocket gets `101`, closes after fixed interval | Compare idle timeouts across ingress/LB/firewall/backend; add proper heartbeats |
| WebSocket fails only through Gateway | Audit route, handshake headers, and filters matching that path |
| Direct SSE is smooth, batched through Gateway | Audit response filters, compression, and proxy buffering along Gateway's path |
| SSE batches both directly and through Gateway | Inspect how the backend flushes events and which test client is used |
| SSE closes at fixed intervals | Compare response timeouts and idle timeouts at every hop; verify heartbeats |
| `response already committed` occurs only on stream errors | Do not write a second error body; log, end stream, and support reconnect/resume |
| `response already committed` occurs even on REST | Check for filters writing responses in multiple places or editing headers/status post-commit |

## 8. Pre-Production Checklist

- [ ] WebSocket routes use proper `ws`/`wss` or `lb:ws`, and post-rewrite paths match backend endpoints.
- [ ] Handshake, authentication, `Origin`, subprotocols, and TLS tested along the real production network path.
- [ ] WebSocket heartbeat interval is shorter than the lowest idle timeout; clients handle reconnects and close codes.
- [ ] SSE emits properly framed events, flushes consistently, and sends heartbeats when needed.
- [ ] SSE responses carry proper content types and cache policies; proxy buffering/compression verified.
- [ ] Streaming routes bypass filters that aggregate entire response bodies or cache responses inappropriately.
- [ ] Timeouts across Gateway, ingress, load balancer, CDN, and backend align with expected connection durations.
- [ ] Error handlers check `response.isCommitted()` and never try to write a second response.
- [ ] Correlation IDs, connection metrics, and close/error logs suffice to isolate the failing hop.
- [ ] Tested long-lived load, idle connections, upstream restarts, reconnects, and SSE resumption via event IDs.

WebSocket and SSE must be operated as long-lived connections. Once routes are properly configured, data flows smoothly through each proxy, and response commit timing is respected, most premature disconnects, buffering bursts, and duplicate response write errors become straightforward to isolate.
