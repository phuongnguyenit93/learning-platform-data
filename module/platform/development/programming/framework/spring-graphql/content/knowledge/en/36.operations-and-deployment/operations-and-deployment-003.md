# Health checks for transports

## 1. Why do transports need health checks?

A Spring for GraphQL application can serve requests over multiple transports: HTTP, WebSocket, Server-Sent Events (SSE), or RSocket. Each transport establishes connections, exchanges messages, and terminates requests differently.

An application can start up successfully while the GraphQL HTTP route is misconfigured. The WebSocket endpoint might not be enabled, the handshake might fail, or the server might fail to send `connection_ack`. An RSocket server might open a TCP port while the GraphQL route is not yet registered. Therefore, merely checking whether the Java process is still running is not enough to confirm that clients can use the API.

Health checks need to answer different questions:

- Is the process still alive and able to keep running?
- Is the instance ready to receive traffic?
- Can the specific transport establish a connection?
- Can the GraphQL engine receive, validate, and execute an operation?
- Are essential dependencies for operations functioning?

Do not combine all of these questions into a single probe. Liveness, readiness, and synthetic transport checks serve different purposes.

## 2. Distinguishing liveness, readiness, and transport health

| Check type | Question | Action on failure |
| --- | --- | --- |
| Liveness | Is the instance stuck or in a state that cannot recover in place? | The orchestrator can restart the instance |
| Readiness | Can the instance accept new requests? | The load balancer or orchestrator stops routing traffic to the instance |
| Transport health | Can HTTP, WebSocket, SSE, or RSocket receive requests over its protocol? | Report transport error, alert, or remove endpoint from traffic per policy |
| GraphQL smoke test | Can a GraphQL document be parsed, validated, and executed? | Alert on schema, wiring, or runtime errors |
| Dependency health | Are databases or essential services responding? | May mark the instance unready if the dependency is truly mandatory |

Liveness should reflect the internal health of the process. Do not include databases, message brokers, or external APIs in liveness because an outage in a shared dependency could cause Kubernetes to restart all instances and trigger a cascading failure.

Readiness can check a dependency if that dependency is truly required for the instance to serve traffic. This decision must be grounded in architecture: whether the dependency has a fallback, circuit breaker, or is not used by every request.

## 3. Transports supported by Spring for GraphQL

Spring for GraphQL supports GraphQL requests over HTTP, WebSocket, and RSocket. Spring GraphQL 2.1 also provides an SSE handler to stream Subscription responses over HTTP.

| Transport | Connection model | Suitable operations |
| --- | --- | --- |
| HTTP | Request/response, typically POST JSON | Queries and Mutations; GET can be used if explicitly enabled |
| WebSocket | Long-lived bidirectional connection | Subscriptions, as well as single-response Queries/Mutations |
| SSE | Server-to-client HTTP connection stream | Subscriptions |
| RSocket | Session over TCP or WebSocket, supporting multiple interaction models | Queries/Mutations via request-response; Subscriptions via request-stream |

Transports share the same GraphQL schema and execution engine, but health checks must go through the exact transport being verified. An Actuator HTTP endpoint does not prove that WebSocket or RSocket routes are working.

## 4. Spring Boot Actuator provides health endpoints

Add Actuator to get health endpoints and application availability probes:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("org.springframework.boot:spring-boot-starter-graphql")
}
```

The default health endpoint is exposed over HTTP at `/actuator/health`. Spring Boot provides health indicators for application availability, including `livenessState` and `readinessState`.

For applications running on Kubernetes, Boot auto-configures liveness and readiness health groups. They can be enabled explicitly in any environment with the following configuration:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
```

Default probe endpoints:

- `/actuator/health/liveness`
- `/actuator/health/readiness`

With `add-additional-paths: true`, Boot also exposes `/livez` and `/readyz` on the main application server port. This is useful when Actuator runs on a separate management port: probes go through the same HTTP server used by the GraphQL endpoint, avoiding situations where the management port is still working while the main server has failed.

## 5. Configuring Kubernetes probes

Example Deployment using the additional endpoints on the main server port:

```yaml
spec:
  containers:
    - name: spring-graphql
      ports:
        - name: http
          containerPort: 8080
      startupProbe:
        httpGet:
          path: /livez
          port: http
        periodSeconds: 10
        failureThreshold: 30
      livenessProbe:
        httpGet:
          path: /livez
          port: http
        periodSeconds: 10
        timeoutSeconds: 2
        failureThreshold: 3
      readinessProbe:
        httpGet:
          path: /readyz
          port: http
        periodSeconds: 5
        timeoutSeconds: 2
        failureThreshold: 3
```

`startupProbe` gives the application enough time to start up. While the startup probe has not yet succeeded, Kubernetes does not yet use liveness and readiness in the usual way to decide on restarts or traffic routing.

A readiness failure removes the instance from endpoint routing; a liveness failure can lead to a restart. Do not use the same external dependency condition for both probes.

## 6. Readiness in the application lifecycle

Spring Boot manages `ApplicationAvailability` and updates states during startup/shutdown:

| Phase | Liveness | Readiness | HTTP server |
| --- | --- | --- | --- |
| Starting | `BROKEN` | `REFUSING_TRAFFIC` | Not started yet |
| Started | `CORRECT` | `REFUSING_TRAFFIC` | Not accepting traffic yet |
| Ready | `CORRECT` | `ACCEPTING_TRAFFIC` | Accepting requests |
| Graceful shutdown | `CORRECT` | `REFUSING_TRAFFIC` | Rejecting new requests and processing in-flight requests if enabled |
| Shutdown complete | No longer active | No longer active | Closed |

This helps the orchestrator stop sending new requests before the process terminates. With WebSocket and RSocket, you need an additional session draining strategy, controlled connection closing, and client reconnect with backoff; HTTP readiness does not automatically check or terminate existing sessions.

## 7. Readiness and dependency health indicators

Boot does not automatically add every external health indicator to the readiness group. If the application has a mandatory dependency, you can include that indicator in the group:

```yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,db
```

This example is only appropriate when the database is a mandatory dependency for the instance to serve requests. If the API can continue serving part of its traffic when the database temporarily fails, putting `db` into readiness can knock out all instances even though some operations still work.

Do not put shared dependencies or dependencies with fallbacks into liveness. Think carefully before adding a shared dependency to readiness, because if all instances transition to `REFUSING_TRAFFIC` simultaneously, the service may stop accepting any connections.

## 8. Actuator health is not a GraphQL transport check

`/actuator/health` reports the status of registered health contributors. It does not by default send GraphQL documents to `/graphql`, perform a WebSocket handshake, or invoke an RSocket GraphQL route.

Therefore, distinguish two layers:

1. **Platform probe:** checks the process and availability state via `/livez`, `/readyz`, or the corresponding health group.
2. **Synthetic transport probe:** an external client sends real requests over HTTP, WebSocket, SSE, or RSocket and verifies protocol-compliant responses.

Do not create a dummy HTTP health endpoint and use its result to conclude that every transport is working. Each transport can have its own dependencies, endpoint mappings, security rules, and network paths.

## 9. Designing a GraphQL smoke query

To test the GraphQL engine and resolvers, you can provide a lightweight field dedicated to probes:

```graphql
type Query {
    serviceHealth: String!
}
```

```java
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class ServiceHealthController {

    @QueryMapping
    public String serviceHealth() {
        return "UP";
    }
}
```

Check operation:

```graphql
query TransportHealth {
    serviceHealth
}
```

This field only verifies that the request passed through the transport, GraphQL parser, schema validation, DataFetcher mapping, and resolver. It does not prove that the database or business services are healthy.

If you need to check a dependency, create a dedicated probe with a timeout that performs only a very lightweight operation. Do not run heavy business queries, and do not return connection strings or internal details in the response. Protect the probe field with network policies, authentication, or expose it only on an administrative network where appropriate.

Another option is querying `{ __typename }` to test the GraphQL engine without adding a field to the public schema. However, that query does not invoke business resolvers and thus will not detect mapping errors in custom DataFetchers.

## 10. Health check for the HTTP transport

Spring for GraphQL handles GraphQL HTTP via `GraphQlHttpHandler`. Spring Boot exposes HTTP POST at `/graphql` by default; the path can be configured differently depending on the Boot version.

An HTTP transport probe should:

1. Open a connection to the exact host, port, and path that real clients use.
2. Send an HTTP POST with `Content-Type: application/json`.
3. Send a lightweight GraphQL operation such as `TransportHealth`.
4. Verify the HTTP status, JSON response, `errors`, and values in `data`.
5. Apply a short timeout, bounded retries, and avoid polling too frequently.

Example using `curl` and `jq`:

```bash
curl --fail --silent --show-error \
  -H 'Content-Type: application/json' \
  -d '{"query":"query TransportHealth { serviceHealth }"}' \
  http://localhost:8080/graphql \
  | jq -e '.errors == null and .data.serviceHealth == "UP"'
```

Checking only the HTTP status is insufficient. With GraphQL over HTTP, once a request has been validated successfully, errors raised during execution typically appear in the `errors` field of the GraphQL response while the HTTP status may still be `200 OK`. The probe must verify the GraphQL payload as well.

When using the `application/graphql-response+json` media type, certain parse/validation errors can be represented by HTTP 4xx per the GraphQL over HTTP specification. Therefore, inspecting the payload remains necessary to distinguish transport failures from GraphQL execution errors.

## 11. HTTP path differences between Spring Boot 3 and Spring Boot 4

The property name for the HTTP GraphQL path changed across major versions:

| Version | Property | Default value |
| --- | --- | --- |
| Spring Boot 3.x | `spring.graphql.path` | `/graphql` |
| Spring Boot 4.x | `spring.graphql.http.path` | `/graphql` |

WebSocket still uses `spring.graphql.websocket.path`; the RSocket route uses `spring.graphql.rsocket.mapping`. When configuring probes, use the exact effective path after profiles, reverse proxies, and ingress rewrites are applied.

Example HTTP path configuration:

```yaml
spring:
  graphql:
    http:
      path: /api/graphql
```

This `http.path` snippet applies to Spring Boot 4.x. For Boot 3.x, use `spring.graphql.path: /api/graphql`.

## 12. Health check for the WebSocket transport

A WebSocket health check must verify more than the HTTP Upgrade handshake. Spring for GraphQL uses the `graphql-transport-ws` GraphQL over WebSocket protocol.

The probe sequence should include:

1. Connect via WebSocket to the target endpoint and request the `graphql-transport-ws` subprotocol.
2. Wait for the handshake to succeed.
3. Send `connection_init` with an authentication payload if required by the server.
4. Wait for the server to send `connection_ack`.
5. Optionally send `ping` and wait for `pong` to verify bidirectional messaging.
6. Send a single-result GraphQL operation to verify execution over WebSocket.
7. Receive `next` with the expected data and `complete`, then close the connection cleanly.

Example protocol flow:

```text
Client -> Server: WebSocket handshake
                  Sec-WebSocket-Protocol: graphql-transport-ws

Client -> Server: {"type":"connection_init"}
Server -> Client: {"type":"connection_ack"}
Client -> Server: {"type":"ping"}
Server -> Client: {"type":"pong"}
Client -> Server: {
                    "id":"health-1",
                    "type":"subscribe",
                    "payload":{
                      "query":"query { serviceHealth }"
                    }
                  }
Server -> Client: {
                    "id":"health-1",
                    "type":"next",
                    "payload":{"data":{"serviceHealth":"UP"}}
                  }
Server -> Client: {"id":"health-1","type":"complete"}
```

`connection_ack` confirms that the server accepted connection initialization; it does not yet prove that a resolver can execute successfully. `ping/pong` checks message exchange on the connection, while the single-result operation also verifies GraphQL execution.

## 13. Enabling and managing the WebSocket endpoint

The GraphQL WebSocket endpoint is not exposed by default in Spring Boot. To enable it:

- Servlet applications require the `spring-boot-starter-websocket` dependency.
- WebFlux applications do not require an extra dependency for the WebSocket handler.
- Both require configuring `spring.graphql.websocket.path`.

Example:

```yaml
spring:
  graphql:
    websocket:
      path: /graphql-ws
      connection-init-timeout: 10s
      keep-alive: 20s
```

`connection-init-timeout` bounds how long the client has to send `connection_init`. `keep-alive` configures the interval at which the server sends pings when the connection is idle. Keep-alive helps detect dropped connections, but does not replace a probe that executes a GraphQL operation.

WebSocket connections are long-lived and can hold multiple concurrent subscriptions. Limit the number of connections, message size, and subscriptions per session with appropriate server/handler configuration. Do not spawn an indefinite subscription probe on every Kubernetes check.

## 14. Health check for the SSE transport

Spring for GraphQL provides `GraphQlSseHandler` to stream Subscription results over Server-Sent Events. Clients send an HTTP POST with `Content-Type: application/json` and `Accept: text/event-stream`; the response contains one or more SSE events.

SSE is only suitable for Subscriptions. Queries and Mutations should use standard HTTP JSON.

An SSE probe can:

1. Open a Subscription request to the appropriate SSE endpoint.
2. Confirm the HTTP response has media type `text/event-stream`.
3. Wait for the first event within a configured timeout.
4. Confirm the GraphQL payload is valid and contains the expected data.
5. Cancel the stream after receiving sufficient probe data.

Do not let the probe keep the stream open indefinitely. Spring for GraphQL implements SSE using distinct connections; each stream occupies its own connection, so scalability and HTTP/2 should be considered when using it.

## 15. Health check for the RSocket transport

Spring for GraphQL supports RSocket over TCP or WebSocket. `GraphQlRSocketHandler` handles Queries/Mutations as RSocket `request-response`, and Subscriptions as `request-stream`.

An RSocket probe should verify:

1. Establishing an RSocket session to the target TCP/WebSocket server.
2. Sending a GraphQL request to the route configured by `spring.graphql.rsocket.mapping`.
3. Receiving a response from the appropriate interaction model.
4. Checking GraphQL `data` and `errors`, not merely checking that the session opened.
5. Closing or reusing the session according to the probe client's policy.

Example Boot configuration:

```yaml
spring:
  graphql:
    rsocket:
      mapping: graphql
```

The client needs to send the request to the `graphql` route. RSocket keep-alive or a successful connection setup only confirms the transport-layer session; it does not yet prove that the GraphQL route is registered and operations run.

For subscriptions, a dedicated probe can send a request-stream, wait for the first event, and then cancel the subscription. Do not use request-response to verify stream semantics.

## 16. Probe selection matrix by transport

| Transport | Connection check | GraphQL execution check | Probe teardown |
| --- | --- | --- | --- |
| HTTP | TCP/TLS and HTTP POST to the GraphQL path | Verify `data.serviceHealth` and no `errors` | Close response |
| WebSocket | Upgrade + `graphql-transport-ws` + `connection_ack` | Send single-result query via `subscribe`, verify `next` | Receive `complete`, close socket |
| SSE | HTTP response `text/event-stream` | Send Subscription and verify first event | Cancel stream |
| RSocket | Open session and route | Request-response query or request-stream subscription | Close/cancel interaction |

You do not need to probe every transport if the application does not expose it. Only create probes for endpoints that clients actually use.

## 17. Integrating synthetic checks into monitoring

Platform probes typically run from kubelet or the container runtime. Synthetic transport checks should run from an independent component with a network path similar to real clients, such as a monitoring agent or black-box exporter.

A synthetic check should record:

- The transport and endpoint tested.
- Connection/handshake establishment duration.
- GraphQL operation completion duration.
- Result status `UP`, `DOWN`, or `DEGRADED`.
- HTTP status or protocol close/error code on failure.
- Sanitized GraphQL error codes, without raw sensitive query variables.
- Timestamp, timeout, and retry count.

Separate metrics by transport and outcome. Do not put tokens, user IDs, query documents, or variables into metric labels because this causes high cardinality and can leak data.

## 18. Timeouts, retries, and probe frequency

Health checks must be lighter than business operations. Set timeouts shorter than the load balancer or client timeouts, and avoid aggressive retries.

A reference starting configuration:

| Component | Initial suggestion |
| --- | --- |
| HTTP connect timeout | 1–2 seconds |
| HTTP GraphQL response timeout | 2–3 seconds |
| WebSocket handshake + ack timeout | 2–3 seconds |
| WebSocket smoke operation timeout | 2–3 seconds |
| RSocket connect + request timeout | 2–3 seconds |
| Retry | At most 1 attempt with jitter for synthetic monitors; Kubernetes probes use their own thresholds |
| Probe interval | Choose based on SLO and load; avoid sending too frequently across all replicas |

These are starting values for experimentation, not fixed standards. Tune them according to your latency baseline, network environment, and startup behavior. If probes run at high frequency across many replicas, use a very lightweight query and avoid hitting the database every time.

## 19. Securing health endpoints

Health endpoints can disclose database status, brokers, schemas, or internal details. Expose only the minimum data needed by the orchestrator.

- Use firewalls, network policies, or security rules to restrict access sources.
- Do not return stack traces, internal hostnames, JDBC URLs, credentials, or table names.
- Keep Actuator details at an appropriate level; do not enable `show-details=always` on public endpoints.
- If a GraphQL smoke field is exposed through the public API, return only an overall status and consider authorization.
- If probes require a token, store the token in a secret and rotate it periodically.
- Do not log tokens or WebSocket `connection_init` authentication payloads.
- Separate administrative health endpoints from business endpoints when needed, while still checking the main server port using additional probe paths.

## 20. Testing health checks in a Spring environment

Each layer should be tested independently:

1. Test `/actuator/health/liveness` and `/actuator/health/readiness` as application availability transitions states.
2. Test `/livez` and `/readyz` over the main server port if additional paths are enabled.
3. Send an HTTP GraphQL smoke query and confirm `data` is accurate and `errors` is empty.
4. For WebSocket, test handshake, `connection_init`, `connection_ack`, ping/pong, and a single-result operation.
5. For SSE, test response media type, first event, and cancel.
6. For RSocket, test session, route, request-response, and request-stream if Subscriptions exist.
7. Simulate timeouts, connection refused, unauthorized, invalid GraphQL documents, and resolver errors.
8. Test shutdown: readiness transitions to `REFUSING_TRAFFIC`, new requests are rejected, and long-lived sessions are drained per policy.

`GraphQlTester` is well suited for testing schemas and GraphQL execution independently of transport. To test real transports, use the respective HTTP/WebSocket/RSocket client or integration tests against a running server.

## 21. Common issues

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `/actuator/health` is UP, yet `/graphql` fails | Actuator does not execute GraphQL requests | Add a synthetic HTTP GraphQL probe |
| HTTP status 200, yet the probe reports a failure | A GraphQL execution error is in response `errors` | Inspect the payload and result fields |
| WebSocket handshake succeeds, yet no ack arrives | Wrong subprotocol, auth payload, or connection init timeout | Check `graphql-transport-ws`, `connection_init`, and server logs |
| WebSocket ack succeeds, yet queries fail | GraphQL engine/schema/resolver has an error | Send a single-result smoke operation after ack |
| WebSocket endpoint returns 404 | Endpoint is not enabled or path is incorrect | Add required dependency and configure `spring.graphql.websocket.path` |
| SSE returns JSON instead of an event stream | Missing `Accept: text/event-stream` or endpoint does not enable SSE | Check request headers and handler mappings |
| RSocket session opens, yet GraphQL requests fail | Wrong route or GraphQL handler not mapped | Check `spring.graphql.rsocket.mapping` and client route |
| Probe stays DOWN when management port is separate | Probe only checks the management server while the main server fails | Enable `probes.add-additional-paths` and probe the main port |
| All replicas restart when DB fails | Liveness depends on the DB or a shared dependency | Move dependency checks to readiness or separate monitors |
| Readiness is DOWN even though some APIs still run | Readiness group contains a non-essential dependency | Review indicators and fallbacks/circuit breakers |
| Probes increase database load | Probe query performs heavy business logic or runs too often | Use a lightweight resolver, reduce frequency, and bound timeouts |

## 22. Deployment checklist

- [ ] Add Spring Boot Actuator and expose required health endpoints.
- [ ] Enable liveness/readiness probes in the deployment environment.
- [ ] Use liveness for internal process state, without external system dependencies.
- [ ] Add only essential dependencies to readiness.
- [ ] Use additional paths so probes go through the main server port when needed.
- [ ] Confirm the GraphQL HTTP path for your Spring Boot version.
- [ ] Create a lightweight GraphQL smoke operation and check both `data` and `errors`.
- [ ] For WebSocket, verify handshake, `connection_ack`, and a real operation.
- [ ] For SSE, verify the first event and stream cancellation.
- [ ] For RSocket, verify session, route, and the appropriate interaction model.
- [ ] Set timeouts, retries, and intervals according to SLOs.
- [ ] Restrict access permissions and data returned by health endpoints.
- [ ] Test failure modes, startup, and graceful shutdown.
- [ ] Monitor latency and failure rates separately per transport.

## Conclusion

Health checks for Spring for GraphQL must distinguish process health, traffic readiness, and the status of each transport. Spring Boot Actuator provides liveness/readiness health groups; Spring for GraphQL provides handlers for HTTP, WebSocket, SSE, and RSocket. Actuator health endpoints do not automatically execute GraphQL operations, nor do they confirm that long-lived transports are working.

A sound operational design uses liveness to detect processes that cannot recover in place, readiness to decide whether an instance accepts new requests, and synthetic transport probes to verify the exact connection paths clients use. HTTP probes must inspect the GraphQL payload; WebSocket probes must verify protocol initialization and an operation; SSE probes must receive an event; RSocket probes must verify session, route, and interaction model. Keep probes lightweight, bounded by timeouts, access-restricted, and free of external system dependencies in liveness to avoid causing cascading failures.

## References

- [Spring for GraphQL — Server Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring Boot — Actuator Endpoints and Health](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — GraphQL Web Endpoints](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Spring Boot — Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [GraphQL over WebSocket Protocol — `graphql-transport-ws`](https://github.com/enisdenjo/graphql-ws/blob/master/PROTOCOL.md)
- [Kubernetes — Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
