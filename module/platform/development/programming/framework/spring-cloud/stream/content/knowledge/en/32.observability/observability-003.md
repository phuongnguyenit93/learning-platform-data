# Observing Bindings with the bindings Endpoint

## Objectives

Spring Cloud Stream creates bindings to connect application functions to middleware destinations such as Kafka topics, RabbitMQ exchanges/queues, or Pulsar topics/subscriptions. While the application is running, you need to know which bindings have been created, what state each binding is in, whether it is an input or output, which group it belongs to, and how its lifecycle can be controlled.

Spring Cloud Stream integrates an Actuator endpoint with the ID `bindings`. This endpoint lets you list all bindings of an application instance, view details of a single binding, and submit requests to change a binding's state. It is useful when investigating a consumer not receiving messages, pausing a stream for maintenance, or verifying that bindings started after a deployment.

This lesson explains how to enable the endpoint, read `GET` responses, control bindings with `POST`, understand binder-specific limitations, protect sensitive information, and test the endpoint in an environment with real middleware.

After this lesson, you will be able to:

- Explain bindings and how binding names are derived from function definitions.
- Add Spring Boot Actuator and the required web dependency.
- Expose only the `bindings` endpoint over HTTP.
- List and inspect bindings with `GET /actuator/bindings`.
- Change binding state with `POST /actuator/bindings/{name}`.
- Distinguish `STARTED`, `STOPPED`, `PAUSED`, and `RESUMED`.
- Recognize control capability differences between regular binders and the Kafka Streams binder.
- Use `BindingsLifecycleController` when programmatic control is needed.
- Secure the endpoint, redact sensitive data, and observe per instance.
- Test binding states and troubleshoot common issues.

## 1. What is a binding and why observe it?

A binding is the connection between an input/output of a Spring Cloud Stream application and a destination on the middleware. In the functional model, binding names are derived from the function bean name and the input/output index.

Example:

```java
@Bean
Function<OrderCreated, OrderSummary> summarizeOrder() {
    return order -> new OrderSummary(
            order.eventId(),
            order.orderId(),
            "RECEIVED"
    );
}
```

If the function is named `summarizeOrder`, Spring Cloud Stream creates two default bindings:

| Binding name | Direction | Role |
|---|---|---|
| `summarizeOrder-in-0` | Input | Receives `OrderCreated` |
| `summarizeOrder-out-0` | Output | Emits `OrderSummary` |

Configuration can map them to destinations:

```yaml
spring:
  cloud:
    function:
      definition: summarizeOrder
    stream:
      bindings:
        summarizeOrder-in-0:
          destination: orders.created
          group: order-summary-service
        summarizeOrder-out-0:
          destination: orders.summary
```

The binding name is the identifier that the `bindings` endpoint uses in URLs. It differs from the destination: `summarizeOrder-in-0` is the binding name inside the application, whereas `orders.created` is the destination mapped by the binder to a Kafka topic, RabbitMQ exchange/queue, or Pulsar topic depending on the binder.

Observing bindings helps answer operational questions:

- Was the function bound to the expected inputs/outputs?
- What is the actual binding name?
- Is the binding an input or an output?
- Which consumer group is being used?
- Is the binding currently running?
- Does the binder support pause/resume or only start/stop?
- Has a specific instance received the control request?

The endpoint reflects the bindings of the queried application instance. It is not a cluster dashboard that automatically aggregates all replicas.

## 2. Adding Actuator and web dependencies

Actuator and the web server are optional components. To expose the endpoint over HTTP, the application needs Spring Boot Actuator and a web stack such as Spring MVC or WebFlux.

Maven example:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
```

If the application uses the reactive web stack, replace `spring-boot-starter-web` with:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

Do not add both MVC and WebFlux just to enable the endpoint. Choose the web stack that matches your application. Let the Spring Boot/Spring Cloud BOM dependency management control compatible versions; do not pick an Actuator version different from the running Spring Boot version.

If the application has no web server, HTTP endpoints will not be served. You can observe/control bindings via programmatic APIs in the Spring context, or use another administrative mechanism suited to your deployment.

## 3. Exposing the bindings endpoint

By default, Spring Boot only exposes a small set of safe Actuator endpoints, among which `health` is exposed over HTTP. The `bindings` endpoint must be enabled explicitly:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,bindings
```

It can also be configured via properties:

```properties
management.endpoints.web.exposure.include=health,bindings
```

Expose only the endpoints you actually need. Setting `include: "*"` can make many other management endpoints accessible as well. Do not open up all of Actuator just to observe bindings.

After starting the application, check the endpoint mapping logs or send a request:

```bash
curl http://localhost:8080/actuator/bindings
```

The default path is `/actuator/bindings`. If the application customizes the management base path or management port, the URL changes according to Spring Boot configuration.

### Using a separate management port

You can separate the management port from the business HTTP port:

```yaml
server:
  port: 8080

management:
  server:
    port: 8081
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,bindings
```

With this example, the endpoint is at:

```text
http://localhost:8081/manage/bindings
```

Separating the port makes it easier to apply dedicated network policies to management traffic. It does not automatically provide authentication or authorization; you still must configure security for the management interface.

## 4. Listing all bindings with GET

Send the request:

```http
GET /actuator/bindings
```

Example:

```bash
curl -s http://localhost:8080/actuator/bindings
```

The endpoint returns the list of bindings managed by the current application instance. Fields may vary by binder and version; a response might look like:

```json
[
  {
    "bindingName": "summarizeOrder-in-0",
    "name": "summarizeOrder-in-0",
    "group": "order-summary-service",
    "pausable": false,
    "state": "running",
    "paused": false,
    "input": true,
    "extendedInfo": {}
  },
  {
    "bindingName": "summarizeOrder-out-0",
    "name": "summarizeOrder-out-0",
    "group": "order-summary-service",
    "pausable": false,
    "state": "running",
    "paused": false,
    "input": false,
    "extendedInfo": {}
  }
]
```

This is an illustrative response; do not treat every field as a fixed schema across all binders. Inspect the actual response from the release you are using.

Commonly seen fields:

| Field | Meaning |
|---|---|
| `bindingName` / `name` | Binding name within the application |
| `group` | Consumer group for an input binding that has a group |
| `input` | Indicates whether the binding is an input or output |
| `state` | Lifecycle state, such as running or stopped |
| `paused` | Indicates whether the binding is paused, if provided by the binder |
| `pausable` | Indicates whether the binding supports pause/resume |
| `extendedInfo` | Additional binder-specific information |

Output bindings normally do not have a consumer group like inputs. For anonymous consumers, `group` may not carry a named-group value. Do not infer broker lag, queue depth, or unacked message counts solely from the `running` state; the bindings endpoint primarily describes binding lifecycle/configuration.

### Binding name vs. destination

If the response lists `summarizeOrder-in-0`, that is the name to use in the detail endpoint or when posting a state change. Do not use the destination `orders.created` in place of the binding name if they differ.

With function composition or multiple inputs/outputs, binding names may have other indices such as `process-in-1`, `process-out-0`. Read the actual names from the endpoint rather than guessing them.

## 5. Viewing details of a single binding

Use the binding name in the path:

```http
GET /actuator/bindings/{bindingName}
```

Example:

```bash
curl -s http://localhost:8080/actuator/bindings/summarizeOrder-in-0
```

This request helps focus on a single binding when the application has multiple functions or multiple binders. The response typically shows the name, group, input/output direction, state, and extended information provided by the binder.

If the binding does not exist on the queried instance, the endpoint may return a not-found error. Before concluding that the binding was not created, check:

- Whether the function is included in `spring.cloud.function.definition`.
- Whether the binding name has the right `-in-0`/`-out-0` suffix.
- Whether the binding is created automatically or explicitly.
- Whether the queried instance is the one that initialized that function.
- Whether the application started successfully and binder provisioning completed.

The endpoint does not replace startup logs or binder health. If a binding was not created due to a configuration error, inspect startup errors and binder logs.

## 6. Controlling lifecycle with POST

The endpoint accepts posting a new state to the same binding URL:

```http
POST /actuator/bindings/{bindingName}
Content-Type: application/json

{"state":"STOPPED"}
```

Common lifecycle states:

| State | Meaning |
|---|---|
| `STARTED` | Start the binding |
| `STOPPED` | Stop the binding |
| `PAUSED` | Pause the consumer if supported by the binder |
| `RESUMED` | Resume a paused consumer if supported by the binder |

Example stopping an input binding:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"state":"STOPPED"}' \
  http://localhost:8080/actuator/bindings/summarizeOrder-in-0
```

Restarting the binding:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"state":"STARTED"}' \
  http://localhost:8080/actuator/bindings/summarizeOrder-in-0
```

Pausing and resuming when supported by the binder:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"state":"PAUSED"}' \
  http://localhost:8080/actuator/bindings/summarizeOrder-in-0

curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"state":"RESUMED"}' \
  http://localhost:8080/actuator/bindings/summarizeOrder-in-0
```

After a POST, read the binding back with GET to verify its actual state. Do not rely solely on the HTTP response of the control call; the binder may need time to complete the lifecycle transition or may log a warning if the state is unsupported.

### STOPPED vs. PAUSED

`STOPPED` stops the binding lifecycle. For an input consumer, new messages are not received through that binding while it is stopped. How in-flight messages, offsets/acks, queue backlogs, and redeliveries behave follows the binder/middleware semantics; do not assume POST stop means all in-flight messages have completed or rolled back.

`PAUSED` pauses message reception while keeping the binding according to the binder's capabilities. It is not a universal feature across all middleware. When draining messages before maintenance, verify that the binder supports pause and check in-flight processing before acting.

## 7. Lifecycle capabilities depend on binder and version

Not every binder supports every state. Current Spring Cloud Stream documentation states:

- For regular binders, `STARTED` and `STOPPED` are the basic lifecycle operations.
- `PAUSED` and `RESUMED` only take effect if both the binder and middleware support them. Current documentation notes Kafka and Solace support these states.
- The Kafka Streams binder has separate control documentation: it only supports `STARTED` and `STOPPED`; `PAUSED` and `RESUMED` are not available in the Kafka Streams binder.

Therefore, do not assume the Kafka Streams binder supports pause/resume just because the regular Kafka binder can. For RabbitMQ or Pulsar binders, do not assume POST `PAUSED`/`RESUMED` works; check the release guide and the response/logs of the binder in use.

| Binder/model | STARTED / STOPPED | PAUSED / RESUMED |
|---|---|---|
| Regular Kafka binder | Yes | Yes per current documentation |
| Kafka Streams binder | Yes | No |
| Solace binder | Yes | Yes per current documentation |
| RabbitMQ binder | Yes per binding lifecycle | Do not assume; check version |
| Pulsar binder | Yes per binding lifecycle | Do not assume; check version |

This table is a guide for choosing operations, not a substitute for checking the compatibility matrix of your specific version. If a binder does not support a state, logs may emit a warning or the binding may not transition to the requested state.

## 8. Binding names in functions, Consumers, and StreamBridge

Default binding names are derived from function definitions:

| Function type | Common binding name |
|---|---|
| `Supplier<T>` | `functionName-out-0` |
| `Consumer<T>` | `functionName-in-0` |
| `Function<I,O>` | `functionName-in-0`, `functionName-out-0` |
| Function with multiple inputs | `functionName-in-0`, `functionName-in-1`, ... |
| Function with multiple outputs | `functionName-out-0`, `functionName-out-1`, ... |

If `StreamBridge` is used, an output binding may be created when sending a message if the binding does not yet exist and dynamic destination behavior is enabled in configuration. Afterwards, the binding can appear in the endpoint. For explicit bindings not created from function definitions, names may omit the `-in-0`/`-out-0` suffix.

Example:

```java
@Service
class OrderPublisher {

    private final StreamBridge streamBridge;

    OrderPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    boolean publish(OrderCreated event) {
        return streamBridge.send("orders-out-0", event);
    }
}
```

Once the output binding is created, the endpoint can show `orders-out-0`. If the binding does not appear, check whether a message has been sent yet, whether the binding is created explicitly or automatically, and whether the output name matches code and configuration.

## 9. Observing bindings is not the same as observing the broker

The bindings endpoint reports binding state inside the application. It does not provide full middleware operational metrics.

| Question | Where to observe |
|---|---|
| Has the binding been created? | `/actuator/bindings` |
| Is the binding running or stopped? | `/actuator/bindings/{name}` |
| What is the Kafka consumer lag? | Kafka consumer group metrics/tooling |
| How many ready/unacked messages are in the RabbitMQ queue? | RabbitMQ Management/API/metrics |
| What are the Pulsar subscription backlog and redeliveries? | Pulsar Admin/metrics |
| Does the application have errors or lack readiness? | `/actuator/health`, application logs |
| What are message throughput and latency? | Micrometer metrics/tracing and broker metrics |
| Are there serialization/deserialization errors? | Application logs, error metrics, and binder-specific diagnostics |

A binding in the `running` state does not prove it is receiving messages. There may be no producer, mismatched routing keys, undrained subscription backlogs, rejected ACLs, or failing consumer handlers. Combine the bindings endpoint with health, logs, metrics, and broker administration tools.

## 10. The endpoint only controls the targeted instance

In multi-replica deployments, each application instance has its own Spring context and binding lifecycle. Sending a POST to one pod applies the action to that pod's binding. It does not automatically broadcast to all replicas in Kubernetes or a VM fleet.

Example deployment with three pods:

```text
orders-service-0 -> /actuator/bindings/summarizeOrder-in-0
orders-service-1 -> /actuator/bindings/summarizeOrder-in-0
orders-service-2 -> /actuator/bindings/summarizeOrder-in-0
```

If you only call the endpoint on `orders-service-0`, the other two pods may keep consuming. With consumer groups, pods can share the same logical subscription/group; stopping one pod does not mean the whole group stops.

To manage an entire fleet, use an orchestrator/control plane with an instance inventory and call the management endpoint of each instance, or use a centralized operational mechanism. Handle timeouts, changing instance IPs, rolling restarts, and partial successes. Do not send requests to a load-balanced service URL without knowing which instance handles it; a response from one pod does not prove all pods changed state.

## 11. Securing the bindings endpoint

The endpoint can change the lifecycle of message flows. If an unauthorized party can POST `STOPPED`, they can halt message consumption. Therefore:

- Do not expose management endpoints directly to the Internet.
- Only expose `bindings` when actually needed.
- Use a separate management port/network when appropriate.
- Protect it with Spring Security or an API gateway enforcing authentication/authorization.
- Grant POST permissions only to required operators/roles.
- Restrict network access with firewalls or Kubernetes NetworkPolicies.
- Write audit logs for state-change operations.
- Monitor failed requests and unexpected stop/start actions.

Simple conceptual security configuration with Spring Security 6:

```java
@Bean
SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
    http.securityMatcher(EndpointRequest.to("bindings"));
    http.authorizeHttpRequests(authorize ->
            authorize.anyRequest().hasRole("STREAM_OPERATOR")
    );
    http.httpBasic(Customizer.withDefaults());
    return http.build();
}
```

This is a conceptual example; production configuration must integrate your authentication provider, TLS, and application security policy. If the application defines a custom `SecurityFilterChain`, Spring Boot may not apply default Actuator security configuration; ensure matchers and authorization rules cover both the endpoint root and subpaths.

### Do not expose all endpoints for debugging convenience

Avoid:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
```

If you need other endpoints, add only the exact IDs required. When enabling multiple endpoints, evaluate the configuration data, environment variables, beans, logs, and operational information they could expose.

## 12. Redacting sensitive data in responses

The bindings endpoint can display extended information or binder-related configuration. Some values may contain credentials, SASL configuration, SSL key material, or connection details. Do not assume all values are masked uniformly across every version.

Spring Boot provides `SanitizingFunction` to customize how sensitive data is masked. Example:

```java
@Bean
SanitizingFunction sanitizingFunction() {
    return data -> {
        if ("sasl.jaas.config".equals(data.getKey())) {
            return data.withValue("[REDACTED]");
        }
        return data;
    };
}
```

The example above illustrates masking a specific property. The application should identify the list of sensitive keys for its binder and environment, such as passwords, tokens, private keys, JAAS configs, or credentials embedded in URLs. Never log secrets while handling endpoint responses.

Test sanitization against actual responses on the running version. Just because the endpoint does not display a property in a test environment does not mean production will not display a corresponding property.

## 13. Controlling bindings with BindingsLifecycleController

Since Spring Cloud Stream 3.1, applications can use the `BindingsLifecycleController` bean to query and control bindings from Java instead of HTTP:

```java
BindingsLifecycleController controller =
        applicationContext.getBean(BindingsLifecycleController.class);

Binding<?> binding = controller.queryState("summarizeOrder-in-0");

if (binding.isRunning()) {
    controller.stop("summarizeOrder-in-0");
}
```

You can also change state explicitly:

```java
controller.changeState("summarizeOrder-in-0", State.STOPPED);
controller.changeState("summarizeOrder-in-0", State.STARTED);
```

The controller also provides convenience methods such as start/stop and pause/resume. Actual capabilities still depend on the binder; calling pause does not magically give a binder pause support if the middleware adapter does not support it.

Use the programmatic API when integrating lifecycle control with an internal management service or testing directly. For external operational actions outside the process, the Actuator endpoint is usually easier to integrate with ops tooling.

Since Spring Cloud Stream 4.2, the controller also supports creating new bindings and retrieving extension properties for explicitly created bindings. This is an advanced dynamic binding management capability; do not confuse it with `GET /actuator/bindings`, which observes existing bindings.

## 14. Testing the bindings endpoint

Testing can be performed at multiple layers.

### Application context test

Verify:

- The Actuator dependency is on the classpath.
- The web stack is initialized.
- The bindings endpoint is registered.
- Function bindings have the expected names.
- Exposure configuration includes `bindings`.
- Security permits operator roles and rejects unauthorized roles.

### HTTP test

For Spring MVC, you can use MockMvc; for WebFlux, you can use WebTestClient. Core cases:

| Request | Expectation |
|---|---|
| `GET /actuator/bindings` | Returns list of bindings |
| `GET /actuator/bindings/{name}` | Returns details of an existing binding |
| `GET` non-existent binding | Returns an appropriate error without leaking internals |
| `POST` state `STOPPED` | Binding transitions to stopped if supported by binder |
| `POST` state `STARTED` | Binding transitions to running |
| `POST` state `PAUSED` | Succeeds only when supported by binder |
| `POST` invalid state | Returns appropriate validation error |
| Unauthenticated request | Rejected |
| User without operator role | Rejected |

Example testing GET with MockMvc:

```java
@SpringBootTest
@AutoConfigureMockMvc
class BindingEndpointTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void listsBindings() throws Exception {
        mockMvc.perform(get("/actuator/bindings"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON
                ))
                .andExpect(jsonPath("$[?(@.name=='summarizeOrder-in-0')]")
                        .exists());
    }
}
```

Tests must configure the appropriate function definition and test binder or real binder so bindings are created in the context. Response schemas can differ across binders/versions; adjust JSON paths to match the actual response rather than relying on fields not guaranteed by contract.

### Broker integration test

HTTP tests do not prove the broker stopped or resumed delivering messages properly. Add integration tests with Kafka, RabbitMQ, or Pulsar as appropriate:

1. Publish a message and verify the consumer receives it.
2. POST `STOPPED` to the input binding.
3. Publish more messages and verify the binding does not receive them while stopped per binder semantics.
4. POST `STARTED`.
5. Verify the consumer resumes processing and backlog is handled per broker policy.
6. If testing pause/resume, verify the binder actually supports those states.
7. Inspect in-flight messages during stop and check ack/offset outcomes.
8. Inspect logs/metrics after the operation.

Do not assert that messages "disappear" when a binding stops. The broker may retain messages in the topic/queue/subscription for the consumer to receive once the binding starts again; exact semantics depend on the middleware.

## 15. Troubleshooting workflow when a binding stops working

When a consumer is not receiving messages, follow this sequence:

1. Call `GET /actuator/bindings` on the exact instance.
2. Confirm the exact binding name.
3. Call `GET /actuator/bindings/{name}` to inspect its state.
4. Verify the binding is an input and its destination/group match configuration.
5. Check application logs and binder health.
6. Check the broker topic/queue/subscription, ACLs, routing, and backlog with broker tools.
7. Check message conversion, retries, acks, and handler exceptions.
8. If the binding is unexpectedly stopped, check audit/logs for lifecycle actions.
9. POST `STARTED` only after identifying why it stopped and with operator authorization.
10. Call GET again and verify the consumer is actually receiving messages.

If the endpoint returns `running` while broker backlog grows, the problem may lie in throughput, partitions/concurrency, consumer errors, or middleware. Do not repeatedly stop/start as a cure-all; doing so can increase rebalances, redeliveries, or processing disruption.

## 16. Common issues

| Symptom | Possible cause | How to resolve |
|---|---|---|
| `/actuator/bindings` returns 404 | Missing Actuator/web dependency or endpoint not exposed | Add dependencies and configure exposure |
| Only `health` is available | `bindings` not added to exposure include | Configure `health,bindings` |
| GET returns 401/403 | Security requires auth or lacks required role | Grant operator role per policy |
| Binding does not appear | Function not activated or binder provisioning failed | Check function definition and startup logs |
| Used destination in URL and got not found | URL requires binding name | Retrieve name from GET list |
| POST PAUSED has no effect | Binder/model does not support pause | Check capability and version |
| Cannot pause Kafka Streams binder | Kafka Streams binder only supports STARTED/STOPPED | Use stop/start or another appropriate mechanism |
| POST succeeds but consumer still runs on another pod | Only one instance was called | Execute across the fleet via control plane |
| Binding running but no messages | No producer, wrong routing/ACL, handler errors, or backlog | Combine broker metrics and logs |
| Response exposes sensitive configuration info | Extended info contains credentials/properties | Secure endpoint and use SanitizingFunction |
| Redeliveries occur after stop/start | In-flight messages were not acked/committed | Check ack/offset semantics and idempotency |
| Wrong URL | Custom management port/base path configured | Check management server config |

## 17. Safe operations runbook

Before controlling a production binding:

- Confirm the cluster, application instance, and binding name.
- Identify input/output direction and the binder in use.
- Check current state via GET.
- Assess impact on backlog, in-flight messages, offsets/acks, and downstream.
- Have a clear operational reason and an authorized operator.
- Perform one lifecycle change at a time.
- Re-read state after POST.
- Check broker metrics and application logs.
- If managing multiple replicas, verify the outcome on each instance.
- Record an audit entry including operator, timestamp, binding, old/new state, and reason.

When maintaining consumers, consider draining or waiting for in-flight messages to finish before stopping. The lifecycle endpoint does not replace the application's graceful shutdown strategy and does not automatically guarantee all side effects have committed.

## 18. Version-specific reference documentation

Endpoint and binder capabilities change across releases. When implementing, consult the reference guide for the exact Spring Cloud Stream/Spring Boot version in your dependency management:

- [Spring Cloud Stream — Binding visualization and control](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding_visualization_control.html): dependencies, GET/POST endpoints, lifecycle states, programmatic controller, and sanitization.
- [Spring Cloud Stream — Kafka Streams binder binding visualization and control](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/binding-visualization-and-control-in-binder.html): sample response and the Kafka Streams binder's STARTED/STOPPED-only limitation.
- [Spring Boot — Actuator endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): exposure, access control, and endpoint security.
- [Spring Cloud Stream — Binding properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html): binding names, destinations, groups, and binding configuration.

Do not use snapshot documentation to assert capabilities of an older release. Record Spring Boot, Spring Cloud Stream, and binder versions when creating runbooks and test reports.

## Conclusion

The `/actuator/bindings` endpoint lets you observe the bindings Spring Cloud Stream has created on an application instance. Use `GET /actuator/bindings` to list them, `GET /actuator/bindings/{name}` to view details, and `POST /actuator/bindings/{name}` with a JSON state payload to control lifecycle. The name used in the URL is the binding name, not necessarily the destination on the broker.

To enable the endpoint, add Actuator and a web dependency, then expose the `bindings` ID in management configuration. Protect the endpoint with authentication/authorization and network policies because POST can halt message flows; redact sensitive configuration values before returning responses. Pause/resume support depends on the binder: the Kafka Streams binder only supports STARTED/STOPPED, while other binders must be verified by version.

The endpoint only controls the instance receiving the request and only describes binding lifecycle. Combine it with health, logs, metrics, and Kafka/RabbitMQ/Pulsar administration tools. After every action, re-read the state and check the broker to confirm message flow is actually behaving as expected.
