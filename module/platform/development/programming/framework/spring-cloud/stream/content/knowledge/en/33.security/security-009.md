# Restricting Dynamic Destinations and Controllable Expressions

Spring Cloud Stream allows applications to decide where to send messages at runtime. `StreamBridge` can create dynamic output bindings; the `spring.cloud.stream.sendto.destination` header can instruct the framework to send results to a destination; Spring Cloud Function can select functions via the `spring.cloud.function.definition` header or a SpEL expression in `spring.cloud.function.routing-expression`. These capabilities are useful for routers, tenant-aware event gateways, and multi-broker integration applications.

That very flexibility creates a security boundary. If destination names, function names, or expression strings are taken directly from HTTP requests, message headers, or external systems, senders can influence where messages are published or which processing logic is invoked. An arbitrary destination can cause the application to create unintended topics/queues, cross tenant boundaries, emit data to unauthorized systems, or exhaust broker resources. An untrusted SpEL expression can access objects and capabilities that the application author never intended to expose externally.

This lesson covers restricting dynamic destinations, controlling function routing, protecting SpEL, authenticating and authorizing routes, configuring binders/brokers according to least privilege, auditing, and testing controllable-input scenarios. The overarching principle is that external callers may request a business category, while the application maps that request to an approved destination or function.

## Learning Objectives

After this lesson, you will be able to:

- Explain how StreamBridge creates and caches dynamic output bindings.
- Use `spring.cloud.stream.dynamic-destinations` as a destination allowlist.
- Distinguish destination restrictions from caller authentication and authorization.
- Identify headers that can control output destinations or function routing.
- Distinguish `spring.cloud.function.definition` from `spring.cloud.function.routing-expression`.
- Understand the difference between SpEL from message headers and SpEL from application properties.
- Use fixed mappings or `MessageRoutingCallback` for safe routing.
- Prevent tenants from choosing destinations outside their authorized scope.
- Restrict topic/queue creation and publish permissions on the broker.
- Test injection, route bypass, resource exhaustion, and auditing.

## 1. What Is a Dynamic Destination?

In Spring Cloud Stream, bindings are normally declared ahead of time in configuration. For example, `orders-out-0` binds to destination `orders.events`. With dynamic destinations, an application can ask the framework to create an output binding at runtime without pre-declaring that binding.

`StreamBridge` supports this model:

~~~java
@RestController
class EventIngressController {

    private final StreamBridge streamBridge;

    EventIngressController(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    @PostMapping("/events")
    ResponseEntity<Void> publish(@RequestBody OrderEvent event) {
        streamBridge.send("orders.events", event);
        return ResponseEntity.accepted().build();
    }
}
~~~

If the name passed to `send` is not an existing binding, StreamBridge can dynamically create an output binding and provision the destination if supported by the binder. The binding is cached for reuse on subsequent sends. This mechanism is convenient when destinations are genuinely known only at runtime, but it also means an input value can influence the messaging resources used by the application.

### 1.1. Controllable Entry Points

| Entry Point | How It Affects Routing |
|---|---|
| First argument to `StreamBridge.send` | Selects the output binding/destination |
| `spring.cloud.stream.sendto.destination` header | Instructs the framework to resolve the output destination |
| `spring.cloud.function.definition` header | Selects the function or composition to invoke |
| `spring.cloud.function.routing-expression` header | Supplies a SpEL expression to select a function |
| `spring.cloud.function.definition` property | Selects the function at the application level |
| `spring.cloud.function.routing-expression` property | Sets the routing expression at the application level |
| Binder type in StreamBridge overload | Selects the binder used to create a dynamic binding when multiple binders exist |

Not all of these values inherently originate from end users. However, if an HTTP adapter forwards headers into a Message, external producers can send arbitrary headers, or an intermediary system can modify messages, treat those values as untrusted input until validated.

## 2. Risks When Destinations Are Chosen from Input

Suppose an API accepts a `destination` field and passes it directly to `streamBridge.send(destination, event)`. If the application allows any destination name, callers can send messages to an internal topic or queue that the API was never designed to access.

Common risks:

- **Unauthorized publishing:** callers send data to internal destinations, audit streams, or another service's queues.
- **Cross-tenant access:** tenant A picks tenant B's destination name and reads/writes data outside its scope.
- **Uncontrolled resource creation:** varying names can cause the binder to provision new topics/queues if the broker and binder have permissions.
- **Resource exhaustion:** creating numerous bindings, cache entries, topics, queues, or metadata strains both the application and broker.
- **Data leakage:** events are routed to destinations with different consumers or retention policies than intended.
- **Wrong binder:** in multi-binder applications, uncontrolled dynamic binder selection can route messages to the wrong cluster.
- **Hard-to-trace auditing:** arbitrary destination names obscure ownership, SLAs, retention, and error-handling workflows.

A destination name is not a harmless identifier string. In some configurations, resolving a name can trigger binding creation and broker resource provisioning. Treat destinations as resource access permissions.

## 3. Dynamic Destination Allowlist

Spring Cloud Stream provides the `spring.cloud.stream.dynamic-destinations` property to restrict which destination names can be dynamically bound. If configured, only destinations in the list can be dynamically bound. If unconfigured, the default permits binding any destination.

Example:

~~~yaml
spring:
  cloud:
    stream:
      dynamic-destinations:
        - orders.events
        - billing.events
        - audit.events
~~~

Names outside the list will not be turned into dynamic bindings. Always configure an explicit allowlist for applications using dynamic destinations.

### 3.1. An Allowlist Is One Protection Layer, Not User Authorization

An allowlist answers the question: is the application allowed to dynamically bind to this destination? It does not answer the question: is the current user allowed to publish to that destination?

If the list contains `orders.events` and `billing.events`, any request passing through the same service credential can still request either destination unless the application checks the principal's permissions. Therefore, combine:

1. Application-level allowlist.
2. Server-managed route mapping.
3. Authorization by user, tenant, or service identity.
4. Broker ACL/vhost/namespace policies.

Do not use an allowlist in place of authorization.

### 3.2. Never Build Allowlists from Request Data

Never read a list of destination names from a request and feed it directly into properties or resolvers. Allowlists must be managed through trusted configuration or reviewed source code.

If the system needs tenant-based routing, do not construct destination names from an arbitrary tenantId string. Authenticate the tenant from a verified identity, verify the tenant's permissions, and then look up the registered destination from trusted configuration or a controlled registry.

## 4. Limiting the Dynamic Destination Cache

StreamBridge caches dynamic output bindings for reuse. Current Spring Cloud Stream documentation describes the cache as evicting old entries with a default size of 10. You can configure the size with `spring.cloud.stream.dynamic-destination-cache-size`.

Example:

~~~yaml
spring:
  cloud:
    stream:
      dynamic-destination-cache-size: 8
~~~

Cache size helps bound how many bindings stay in memory and limits memory growth from many dynamic bindings. Once exceeded, older bindings may be evicted from the cache and recreated on future sends.

**Cache size is not an allowlist and not a destination creation quota.** Evicting a binding from in-memory cache does not delete the topic/queue from the broker. Callers could still request many different names over time, increasing broker resources or binding creations. Therefore:

- Use `dynamic-destinations` to restrict permitted names.
- Size the cache to match a finite set of destinations.
- Set quotas or policies on the broker if the platform supports them.
- Rate-limit APIs and cap registered tenants/destinations.
- Monitor dynamic binding counts and provisioned topic/queue counts.

Do not increase cache size to handle an unbounded stream of destination names. First determine why the application needs to create new destinations at all.

## 5. Prefer Pre-Declared Output Bindings

If the list of output destinations is known at deployment time, declare static bindings. This lets you review binders, destinations, serialization, and producer properties before the application runs.

~~~yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      output-bindings: orders-out-0;billing-out-0
      bindings:
        orders-out-0:
          destination: orders.events
          binder: kafka
        billing-out-0:
          destination: billing.events
          binder: rabbit
~~~

The application can invoke StreamBridge using the declared binding names:

~~~java
streamBridge.send("orders-out-0", orderEvent);
streamBridge.send("billing-out-0", billingEvent);
~~~

Caller-supplied input should only be a route key such as `orders` or `billing`. The application looks up the route key to a known binding name; never pass raw request strings directly as binding names.

Static bindings do not authenticate users by themselves. You must still check authorization before sending. However, they eliminate unintended destination creation and keep broker configuration easier to govern.

## 6. Mapping Routes via Fixed Lists

A safe pattern is defining the allowed route set in code or trusted configuration:

~~~java
@Component
class EventPublisher {

    private static final Map<String, String> BINDINGS = Map.of(
            "orders", "orders-out-0",
            "billing", "billing-out-0");

    private final StreamBridge streamBridge;
    private final DestinationAuthorizer authorizer;

    EventPublisher(
            StreamBridge streamBridge,
            DestinationAuthorizer authorizer) {
        this.streamBridge = streamBridge;
        this.authorizer = authorizer;
    }

    boolean publish(
            String routeKey,
            Principal principal,
            Object event) {

        String binding = BINDINGS.get(routeKey);
        if (binding == null) {
            throw new IllegalArgumentException("Unsupported route");
        }

        authorizer.requirePublishPermission(principal, routeKey);

        return streamBridge.send(binding, event);
    }
}
~~~

In the example:

- `routeKey` can only be one of the predefined keys.
- The binding name comes from an application-managed map.
- Authorization is verified before sending.
- The caller cannot pass an arbitrary topic name directly.

In real applications, you can use an enum instead of a String to represent routes. If a route key comes from a URL or JSON, check nullability, length, and valid values; reject unknown routes rather than synthesizing destination names.

### 6.1. Authorization Must Be Bound to the Principal

The `DestinationAuthorizer` example must verify the caller has permission to publish to that route. For multi-tenant systems:

- Obtain the tenant from an authenticated token/session.
- Never treat a self-asserted tenantId in payload or headers as a verified identity.
- Verify the tenant owns or is authorized to use that route.
- Map tenant and route to a server-managed destination.
- Deny when unauthorized, even if the destination is in the application-wide allowlist.

If each tenant needs its own destination, store the tenant-to-destination mapping in a controlled registry and verify registry access permissions. Never concatenate input strings into topic names without authentication and authorization.

## 7. StreamBridge in Multi-Binder Applications

Spring Cloud Stream supports multiple binders in the same application, such as Kafka and RabbitMQ. When using StreamBridge with multiple binders, an overload allows specifying the binder type:

~~~yaml
spring:
  cloud:
    stream:
      dynamic-destinations:
        - orders.events
        - billing.events
~~~

~~~java
streamBridge.send("orders.events", "kafka", orderEvent);
streamBridge.send("billing.events", "rabbit", billingEvent);
~~~

The names `kafka` and `rabbit` illustrate binder types registered in the application. The binder type should come from a reviewed internal mapping, never from requests or message headers. Destination names in the example must also be in `dynamic-destinations`.

The binder-type overload is used when StreamBridge creates a dynamic binding. If the output binding was already pre-created via `spring.cloud.stream.output-bindings` or already bound under another binder, the binder type argument does not change the binder attached to that binding. For static output bindings, use `send(bindingName, data)` and configure the binder directly on the binding.

If a caller can select both destination and binder, the attack surface widens: the same route key could be sent to a different cluster with different retention, ACLs, consumers, or sensitive data. Map each business route to a fixed destination/binder pair.

Mapping example:

| Route key | Dynamic destination | Binder type |
|---|---|---|
| orders | orders.events | kafka |
| billing | billing.events | rabbit |
| audit | audit.events | kafka |

Never allow clients to supply `binderType` or cluster names. Those values belong to the application's operational configuration.

## 8. The spring.cloud.stream.sendto.destination Header

Spring Cloud Stream can route outputs using the `spring.cloud.stream.sendto.destination` header. The framework reads the name in the header and attempts to resolve or create a destination with that name.

Simple example:

~~~java
@Bean
Function<OrderEvent, Message<OrderEvent>> routeOrder() {
    return event -> MessageBuilder.withPayload(event)
            .setHeader(
                    "spring.cloud.stream.sendto.destination",
                    "orders.events")
            .build();
}
~~~

The example above uses a fixed destination. Risk arises if the header value is taken directly from an external payload or header:

~~~java
// Unsafe: input data controls the destination
@Bean
Function<OrderEvent, Message<OrderEvent>> unsafeRoute() {
    return event -> MessageBuilder.withPayload(event)
            .setHeader(
                    "spring.cloud.stream.sendto.destination",
                    event.requestedDestination())
            .build();
}
~~~

Do not build routing headers from client-asserted fields. Replace them with server-verified values looked up from an allowlist:

~~~java
@Bean
Function<OrderEvent, Message<OrderEvent>> safeRoute() {
    return event -> {
        String destination = switch (event.eventType()) {
            case "ORDER_CREATED" -> "orders.events";
            case "BILLING_REQUESTED" -> "billing.events";
            default -> throw new IllegalArgumentException("Unsupported event type");
        };

        return MessageBuilder.withPayload(event)
                .setHeader(
                        "spring.cloud.stream.sendto.destination",
                        destination)
                .build();
    };
}
~~~

In real applications, principal authorization checks must happen before the function produces an output. If the function receives messages from a broker, apply identity/service authorization suited to the message source; never assume a valid event type implies the sender is authorized to route.

## 9. Function Routing and Two Distinct Headers

Spring Cloud Function has two important routing headers:

- `spring.cloud.function.definition`: the name of a function or a composition chain, such as `validateOrder|acceptOrder`.
- `spring.cloud.function.routing-expression`: a SpEL expression returning the function definition to invoke.

These two headers control which function is invoked, not the output destination. They can appear in message headers when an adapter forwards HTTP headers or broker messages into Spring Cloud Function.

To use `RoutingFunction` in Spring Cloud Stream, enable routing via `spring.cloud.stream.function.routing.enabled=true` or configure `spring.cloud.function.routing-expression` at the application level. When enabling header-based routing, validate headers before messages enter the router.

~~~yaml
spring:
  cloud:
    stream:
      function:
        routing:
          enabled: true
~~~

### 9.1. Function Definition Header

If a message carries the `spring.cloud.function.definition` header, the routing function can use that value to select a function. Since the value can specify a function name or composition, do not allow clients to pick arbitrary function beans from the catalog.

Design risk example:

~~~text
HTTP header:
  spring.cloud.function.definition = function-name-from-client

RoutingFunction:
  looks up function in FunctionCatalog
~~~

If the catalog contains administrative functions, data-writing functions, or internal-only functions, letting users choose function names can expose ungranted capabilities.

### 9.2. Routing Expression Header

The `spring.cloud.function.routing-expression` header allows passing a SpEL expression to select a function. Valid documented example:

~~~properties
spring.cloud.function.routing-expression=headers.function_name
~~~

This expression reads the `function_name` header from the message and returns a function definition. However, if a sender can supply the entire expression string, they may try to influence expression evaluation or select functions outside the permitted scope.

Spring Cloud Function currently evaluates expressions arriving from message headers using `SimpleEvaluationContext`, which is more restricted than `StandardEvaluationContext`. Expressions configured via application properties or system/environment properties are evaluated with `StandardEvaluationContext`, which has fuller capabilities. This is an important distinction, yet `SimpleEvaluationContext` should not be treated as a guarantee of safety for arbitrary untrusted expressions.

Spring Framework warns that evaluating SpEL from untrusted sources is inherently risky; `SimpleEvaluationContext` restricts only part of the capabilities and is not an absolute security sandbox. The best design is not allowing users to send expression strings at all. Send a route key from a finite value set and let the application decide the function.

### 9.3. Routing Precedence Order

According to Spring Cloud Function, for imperative functions, the precedence order is:

1. `MessageRoutingCallback`.
2. Message headers if no callback is present.
3. Application properties.

This means a header supplied by an external message can override a routing expression set in application properties if no callback exists. When server-controlled routing is required, register a callback to enforce a fixed policy, or strip/overwrite untrusted routing headers before reaching the routing function.

For reactive functions, per-message header routing does not apply like it does for imperative functions; routing instructions are supplied at the application property level because the unit of work is the entire stream. Do not rely on this difference as an excuse to skip protecting configuration.

## 10. Using MessageRoutingCallback to Restrict Functions

`MessageRoutingCallback` lets the application decide the function from the message in code. A safe callback uses a fixed route map instead of interpreting sender-supplied strings:

~~~java
@Bean
MessageRoutingCallback secureRoutingCallback() {
    Map<String, String> allowedFunctions = Map.of(
            "ORDER_CREATED", "orderHandler",
            "PAYMENT_SETTLED", "paymentHandler");

    return message -> {
        String eventType = message.getHeaders()
                .get("event-type", String.class);

        String functionName = allowedFunctions.get(eventType);
        if (functionName == null) {
            throw new IllegalArgumentException("Unsupported event type");
        }

        return functionName;
    };
}
~~~

The callback returns only mapped function names. It does not parse SpEL strings from messages. Because the callback takes precedence over headers and application properties for imperative routing, it centralizes routing decisions in server code.

However, the callback must still authenticate the message source and business permissions if event types can be sent by multiple producers. A valid route key does not prove a producer is authorized to emit that event. Enforce broker ACLs and identity/tenant checks per your system architecture.

### 10.1. Handling Invalid Routes

Do not silently drop messages when a route is unauthorized. Spring Cloud Function has a mechanism for unroutable messages; the default handler may log and let the flow continue, resulting in dropped messages. For critical business flows:

- Record invalid routes via metrics and audit logs.
- Send the message to quarantine/DLQ per policy.
- Never infinitely retry a non-existent route key.
- Never dynamically create new functions or destinations to "try" processing it.
- Return an appropriate error at the ingress API if the route was selected directly by a request.

## 11. Never Parse SpEL from External Data

SpEL supports property access, method invocation, object instantiation, and bean references in capable contexts. If an application invokes the parser directly on a client-supplied string, the sender can control how the expression evaluates.

Unsafe pattern:

~~~java
String expressionText = request.expression();
Expression expression = parser.parseExpression(expressionText);
Object result = expression.getValue(evaluationContext);
~~~

The risk goes beyond syntax. Expressions can access objects exposed via the root object, property accessors, method resolvers, variables, or functions. Even a getter that looks like simple property access can have side effects.

Do not try to solve this by filtering out a few dangerous characters. Expression languages have rich syntax; denylists routinely miss alternate representations. Do not treat switching to `SimpleEvaluationContext` as permission to accept arbitrary user expressions either.

### 11.1. Use Typed Data Instead of Expressions

Instead of accepting:

~~~json
{
  "routingExpression": "expression supplied by caller"
}
~~~

accept a route key:

~~~json
{
  "route": "orders"
}
~~~

Then map the route key to a fixed binding/function. If the business genuinely needs administrator-defined rules, design a constrained DSL with an explicit grammar, data types, operators, and permissions; do not allow administrators to enter arbitrary SpEL without strict review workflows and access controls.

### 11.2. Expressions in Application Properties

Expressions placed in application properties are usually managed by developers or operators and do not come directly from end users. However, configuration sources can become compromised if:

- Config Server or the configuration store suffers unauthorized access.
- Deployment pipelines allow unauthorized users to modify environment variables.
- Management endpoints or configuration refresh endpoints are improperly exposed.
- Secret/configuration management lacks per-environment access control.

Protect configuration sources and management endpoints with authentication, authorization, network restrictions, and auditing. Never allow end users to alter routing properties or function definitions.

## 12. Never Trust Routing Headers from External Brokers

A producer can send headers with framework-like names. If a consumer reads from a topic where multiple producers have write access, routing headers must be treated as untrusted data.

Headers to watch:

| Header | Potential Impact |
|---|---|
| `spring.cloud.stream.sendto.destination` | Selects output destination |
| `spring.cloud.function.definition` | Selects function or composition |
| `spring.cloud.function.routing-expression` | Selects function via SpEL |
| Application-defined route/tenant headers | Can affect internal mapping if code trusts them directly |

Countermeasures:

1. Never pass external routing headers intact across trust boundaries.
2. Remove or overwrite sensitive headers at the ingress adapter if not permitted.
3. Use dedicated business headers with clear schemas, then map through an allowlist.
4. Verify producer identity and publish permissions at the broker.
5. Never let payload fields directly dictate destination or function names.

Example stripping routing headers before forwarding a message into internal logic:

~~~java
Message<OrderEvent> trustedMessage =
        MessageBuilder.fromMessage(incoming)
                .removeHeader("spring.cloud.stream.sendto.destination")
                .removeHeader("spring.cloud.function.definition")
                .removeHeader("spring.cloud.function.routing-expression")
                .build();
~~~

API names and header mutability depend on the Message type and Spring Messaging version. In a real pipeline, construct a new message from the payload and an allowlisted set of headers rather than copying all external headers.

## 13. Broker-Level Authorization

Application allowlists and mappings protect routing logic. The broker must still enforce permissions at the resource layer.

Examples:

| Broker | What to Restrict |
|---|---|
| Kafka | Cluster/topic ACLs and appropriate create/describe/write permissions |
| RabbitMQ | Users scoped per vhost, configure/write/read permissions on exchanges/queues |
| Pulsar | Tenant/namespace/topic authorization and produce/consume permissions |

An application that only needs to publish to two fixed topics should not use a credential allowed to create and write every topic/queue in the cluster. If the binder must provision destinations at startup, grant tightly scoped provisioning permissions and separate them from runtime permissions when architecture permits.

For multi-tenancy, consider:

- Separate credentials or service identities per tenant/namespace when strong isolation is needed.
- Dedicated RabbitMQ vhosts or Pulsar namespaces.
- Kafka ACLs scoped by topic and principal.
- Never using a broker admin credential inside web-facing applications.
- Rotating credentials and storing them in a secret manager.

Broker ACLs are the last line of defense when an application has a bug or a code path bypasses mapping. Do not grant broad ACLs and hope every controller validates properly.

## 14. Controlling Resource Exhaustion

Dynamic destinations can increase the number of bindings, topics, queues, and metadata entries. A sender submitting many distinct names can spawn huge numbers of destinations if the binder and broker allow it.

Mitigations:

- Configure an exact allowlist.
- Validate route key length and format before lookup.
- Disallow wildcards or patterns without a reviewed requirement.
- Rate-limit per principal and tenant.
- Cap registered destinations per tenant.
- Limit concurrency and message size.
- Enforce broker quotas, topic/queue policies, and create permissions.
- Monitor binding counts, destination counts, and creation rates.
- Maintain an owner-verified cleanup process for application-managed resources.

Do not delete topics or queues merely because a binding cache entry was evicted. Application binding lifecycle and broker resource lifecycle are two distinct concepts.

## 15. Auditing and Observability for Routing

When an application routes messages, record routing decisions via structured logs or audit events:

- Authenticated principal/service identity.
- Verified tenant.
- Route key received from request/message.
- Mapped destination or binding.
- Binder type selected by the application.
- Invoked function name.
- Event ID/correlation ID.
- Authorization and publish attempt outcome.

Never log passwords, tokens, sensitive payloads, or entire SpEL expressions. If you need to investigate a configured expression, log the reviewed config version/source or config identifier rather than logging secret data.

Metrics should have bounded cardinality:

- Rejected route count by valid route key/error group.
- Publish count by registered binding.
- Active dynamic binding count.
- Destinations rejected by allowlist.
- Invalid function route count.
- Broker authorization/provisioning errors.

Do not attach free-form user IDs, tenant IDs, or arbitrary destinations as metric tags if cardinality can grow unboundedly. Use logs/traces for specific identifiers.

## 16. Secure Ingress Design Example

The example below accepts a business route key, checks permissions, and sends via pre-declared output bindings:

~~~java
@RestController
@RequestMapping("/events")
class SecureEventController {

    private static final Map<String, String> OUTPUT_BINDINGS = Map.of(
            "orders", "orders-out-0",
            "billing", "billing-out-0");

    private final StreamBridge streamBridge;
    private final RouteAuthorizer routeAuthorizer;

    SecureEventController(
            StreamBridge streamBridge,
            RouteAuthorizer routeAuthorizer) {
        this.streamBridge = streamBridge;
        this.routeAuthorizer = routeAuthorizer;
    }

    @PostMapping("/{route}")
    ResponseEntity<Void> publish(
            @PathVariable String route,
            Principal principal,
            @RequestBody EventEnvelope event) {

        String binding = OUTPUT_BINDINGS.get(route);
        if (binding == null) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Unsupported route");
        }

        routeAuthorizer.requirePermission(principal, route, event);

        boolean accepted = streamBridge.send(binding, event);
        if (!accepted) {
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE, "Publish was not accepted");
        }

        return ResponseEntity.accepted().build();
    }
}
~~~

This is a structural example. `RouteAuthorizer` must verify the principal and tenant permissions from authenticated data. If the application has multiple binders, the pre-declared binding determines the binder; never let clients select the binder type.

The boolean return value of `StreamBridge.send` indicates the send operation was accepted at the channel/binding per the API; do not interpret it as proof that the target consumer processed the message or business side effects completed. If the API needs durable delivery confirmation, design acknowledgments suited to the binder and broker.

## 17. Security Testing

Do not test only valid routes. Test inputs attempting to bypass limits as well.

### 17.1. Testing Dynamic Destinations

- Destinations in the allowlist bind successfully.
- Destinations outside the allowlist are rejected.
- Empty, null, oversized, or malformed names are rejected.
- Strings with delimiters, wildcards, or control characters cannot form new routes.
- Sending many distinct names does not increase binding counts unexpectedly.
- Cache eviction does not delete or recreate broker resources outside policy.

### 17.2. Testing Function Routing

- The `spring.cloud.function.definition` header cannot select functions outside the map.
- The `spring.cloud.function.routing-expression` header cannot execute client-sent expressions.
- Function composition cannot invoke unauthorized internal functions.
- Unknown event types are rejected or quarantined.
- MessageRoutingCallback enforces fixed mappings.
- Reactive functions are not assumed to support per-message routing headers.

### 17.3. Testing Tenant Isolation

- Tenant A cannot publish to tenant B's binding.
- Tenant IDs in payloads do not override the authenticated tenant.
- Valid routes still fail when the principal lacks permissions.
- Broker ACLs deny publishing outside credential scope.
- Logs/audits reflect the principal and resolved route.

### 17.4. Testing Configuration and Operations

- `dynamic-destinations` is explicitly configured in production profiles.
- Cache size matches the approved destination count.
- Actuator/config endpoints deny unauthorized users from changing routing properties.
- Binder credentials have no unnecessary broker admin privileges.
- Alerts detect abnormal spikes in destination/binding counts.
- Messages carrying malicious routing headers do not alter routes.

## 18. Common Mistakes

1. **Leaving dynamic-destinations empty in production**: defaults to allowing any name to bind dynamically. Configure an explicit allowlist.
2. **Passing request destinations directly to StreamBridge**: callers can select unintended resources. Map route keys to fixed bindings.
3. **Treating cache size as a security limit**: cache eviction does not prevent creating new broker resources. Use allowlists, quotas, and ACLs.
4. **Using regexes instead of allowlists**: a pattern-matching name can still be an unauthorized destination. Use an exact name set or controlled registry.
5. **Assuming a valid destination means caller authorization**: allowlists are app-level policies, not principal authorization. Check permissions separately.
6. **Trusting tenantId in payloads**: clients can claim another tenant. Derive tenants from verified identities.
7. **Letting clients pick binder types**: routes could cross to a different cluster. Map bindings and binders server-side.
8. **Forwarding external headers verbatim**: routing headers can alter destinations or functions. Strip or overwrite sensitive headers.
9. **Allowing clients to send function definitions**: can invoke internal functions or compositions outside public flows. Use callbacks and finite maps.
10. **Evaluating SpEL from requests**: expressions can access context capabilities. Use typed route keys and fixed maps.
11. **Trusting SimpleEvaluationContext as a total sandbox**: it is merely a restricted context, not a universal security guarantee. Avoid untrusted expressions.
12. **Leaving application properties modifiable by unauthorized parties**: property expressions use a more powerful evaluation context. Protect configs and management endpoints.
13. **Silently dropping invalid routes**: messages can vanish without audit trails. Reject, quarantine, or handle errors explicitly.
14. **Granting overly broad broker credentials**: routing bugs can write to unintended topics/queues. Enforce least privilege.
15. **Failing to test resource exhaustion**: varied destination names can spawn numerous bindings and broker resources. Apply rate limits, quotas, and alerts.

## 19. Safe Routing Design Workflow

When building routing in Spring Cloud Stream:

1. List the destinations and functions the application genuinely needs.
2. Prefer pre-declared output bindings when the destination set is finite.
3. If dynamic destinations are needed, set `spring.cloud.stream.dynamic-destinations` as an allowlist.
4. Size the cache to the approved binding count and monitor eviction.
5. Accept business route keys instead of destination names or expressions.
6. Map route keys to bindings, destinations, and binders using trusted configuration/code.
7. Authenticate principals and tenants before sending.
8. Guard `sendto.destination`, `function.definition`, and `function.routing-expression` headers.
9. Use MessageRoutingCallback when per-message function routing is needed.
10. Never parse SpEL supplied by users or external systems.
11. Protect application properties, Config Server, and management endpoints.
12. Restrict broker ACLs, provisioning rights, and quotas.
13. Audit routes, principals, binders, and outcomes.
14. Test route bypass, tenant isolation, expression injection, and resource exhaustion.

## Conclusion

Dynamic destinations and routing expressions are powerful capabilities in Spring Cloud Stream, yet they expand the blast radius of input data. `StreamBridge.send` and the `spring.cloud.stream.sendto.destination` header can cause the framework to dynamically resolve or create output bindings. The `spring.cloud.function.definition` and `spring.cloud.function.routing-expression` headers can influence which function runs; SpEL expressions from message headers and application properties evaluate in different contexts.

Use destination allowlists, static bindings whenever possible, typed route keys, and server-managed mappings. Enforce authorization by principal/tenant; never trust external headers, payloads, or expressions. `dynamic-destination-cache-size` only bounds the binding cache and does not replace allowlists or broker quotas. Combine least-privilege broker ACLs, auditing, rate limits, and security testing so a routing request can never escalate access or spawn unintended resources.

## References

- [Spring Cloud Stream — StreamBridge and Dynamic Destinations](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Binding Service Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-service-properties.html)
- [Spring Cloud Stream — Event Routing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/event-routing.html)
- [Spring Cloud Function — Programming Model and Routing](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Framework — SpEL Security Considerations](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
