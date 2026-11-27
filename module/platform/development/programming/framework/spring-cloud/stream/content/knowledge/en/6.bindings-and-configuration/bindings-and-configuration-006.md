# Default Configuration and Per-Binding Overrides

## Objectives

A Spring Cloud Stream application typically has multiple bindings: one receiving orders, one receiving payments, and one or more emitting events. If every binding redeclares content type, retries, concurrency, and common properties, the configuration grows verbose, hard to review, and prone to drift. Spring Cloud Stream lets you set **shared default values** and override them **per binding** when a specific stream has special requirements.

This lesson explains how to organize configuration by scope, how bindings are named in the functional model, how to distinguish common properties from binder-specific properties, and how to determine the effective value when multiple configuration sources participate.

After this lesson, you will be able to:

- Use `spring.cloud.stream.default` to declare shared configuration.
- Override defaults via `spring.cloud.stream.bindings.<bindingName>`.
- Distinguish common consumer/producer properties from extension properties of the Kafka, RabbitMQ, or Pulsar binder.
- Select a default binder or a specific binder for a binding.
- Organize profiles and environment variables to configure across deployment environments.
- Verify effective configuration rather than just reading a single YAML file.

## 1. Bindings as the unit of configuration

In the functional model, binding names are derived from the function bean name and input/output port positions:

| Function | Binding | Role |
|---|---|---|
| `Consumer<OrderCreated> orderCreated()` | `orderCreated-in-0` | Receives order events |
| `Function<Payment, Receipt> processPayment()` | `processPayment-in-0`, `processPayment-out-0` | Receives payments and emits receipts |
| `Supplier<AuditEvent> auditEvents()` | `auditEvents-out-0` | Emits audit events |
| `Consumer<AuditEvent> auditLog()` | `auditLog-in-0` | Receives events for logging |

Example:

```java
@Bean
Consumer<OrderCreated> orderCreated(OrderService service) {
    return service::handle;
}

@Bean
Function<Payment, Receipt> processPayment(PaymentService service) {
    return service::process;
}

@Bean
Supplier<AuditEvent> auditEvents(AuditService service) {
    return service::nextEvent;
}

@Bean
Consumer<AuditEvent> auditLog(AuditService service) {
    return service::handle;
}
```

Each binding can be configured individually for destination, group, content type, consumer, or producer settings. Configuration must use the exact binding name. If you mistype `processPayment-out-0` as `process-payment-out-0`, the properties may not apply to the actual binding.

You can declare the function names to activate:

```yaml
spring:
  cloud:
    function:
      definition: orderCreated;processPayment;auditEvents;auditLog
```

This declaration explicitly identifies which function beans are wired into streams. If omitted, function discovery and activation depend on auto-configuration and the beans present in the application context; in applications with multiple functions, explicit declaration is more predictable.

## 2. Setting shared configuration as defaults

Common properties can be placed under `spring.cloud.stream.default`. Bindings that do not declare their own values use the corresponding defaults.

Example setting default content type and consumer retry settings:

```yaml
spring:
  cloud:
    stream:
      default:
        content-type: application/json
        consumer:
          max-attempts: 3
          back-off-initial-interval: 1000
          back-off-multiplier: 2.0
          back-off-max-interval: 10000
```

Meaning:

- `content-type` is the default payload format when a binding does not specify one.
- `consumer.max-attempts` sets the maximum number of processing attempts under Spring Cloud Stream's retry mechanism.
- `back-off-initial-interval` is the initial wait interval between attempts.
- `back-off-multiplier` adjusts how the wait interval grows.
- `back-off-max-interval` caps the maximum wait interval.

This example sets three total attempts under typical consumer retry configuration; redelivery counts at the broker layer may be a separate mechanism. Do not mechanically add or multiply attempt counts without checking how the binder handles errors.

You can also set defaults for producers if output bindings share a policy. For example, when producers all share a common content type:

```yaml
spring:
  cloud:
    stream:
      default:
        content-type: application/json
```

Not every broker property can be placed in `default`. Only use common properties here that Spring Cloud Stream supports at the binding, consumer, or producer level.

## 3. Overriding per binding

When a stream has requirements different from the default, place properties under `spring.cloud.stream.bindings.<bindingName>`. Per-binding configuration takes precedence over the corresponding default values.

Example: most consumers retry three times, while the payment stream is allowed five attempts and the audit stream does not need retries:

```yaml
spring:
  cloud:
    stream:
      default:
        content-type: application/json
        consumer:
          max-attempts: 3
          back-off-initial-interval: 1000
          back-off-multiplier: 2.0
          back-off-max-interval: 10000

      bindings:
        orderCreated-in-0:
          destination: orders.created
          group: inventory-service

        processPayment-in-0:
          destination: payments.authorized
          group: billing-service
          consumer:
            max-attempts: 5

        auditLog-in-0:
          destination: audit.events
          group: audit-service
          consumer:
            max-attempts: 1

        auditEvents-out-0:
          destination: audit.generated
```

In this example:

- `orderCreated-in-0` uses JSON and the default three retry attempts.
- `processPayment-in-0` uses JSON, but overrides the attempt count to five; the remaining backoff properties still come from defaults.
- `auditLog-in-0` uses JSON and attempts only once, suitable if errors are routed to another designed handling workflow.
- `auditEvents-out-0` is a `Supplier` output binding and does not receive consumer properties.

Per-binding configuration only needs to specify the properties that differ. There is no need to copy the entire default configuration into every binding.

### Example overriding content type and destination

One binding can use a different format from the rest:

```yaml
spring:
  cloud:
    stream:
      default:
        content-type: application/json
      bindings:
        auditEvents-out-0:
          destination: audit.events
          content-type: application/cloudevents+json
```

The content type in this example is an event-contract choice; producer and consumer must agree on schema and conversion capability. Changing content type only on the producer without updating the consumer can cause deserialization failures before the business function is even invoked.

## 4. Distinguishing common properties from binder-specific properties

Spring Cloud Stream has two configuration groups to keep distinct:

**Common properties** apply across the framework abstraction, for example:

- Destination, group, and content type.
- Consumer retry, backoff, and concurrency.
- Producer partitioning at the supported common-property level.
- The binder chosen for the binding.

**Binder extension properties** control broker-specific capabilities, for example:

- Kafka: consumer isolation level, offset reset, Kafka producer settings, transactions, and client properties.
- RabbitMQ: exchanges, queues, routing, prefetch, dead-lettering, and listener/container options.
- Pulsar: subscription type, acknowledgment timeout, subscription name, schema, and client options.

Extension properties typically reside in the binder's own namespace, in the form:

```text
spring.cloud.stream.<binder>.bindings.<bindingName>.consumer...
spring.cloud.stream.<binder>.bindings.<bindingName>.producer...
```

Illustrative example with the Kafka binder:

```yaml
spring:
  cloud:
    stream:
      bindings:
        orderCreated-in-0:
          destination: orders.created
          group: inventory-service
      kafka:
        bindings:
          orderCreated-in-0:
            consumer:
              configuration:
                isolation.level: read_committed
```

`isolation.level` is a Kafka consumer property; do not place it under common consumer configuration and expect RabbitMQ or Pulsar to interpret it the same way. Extension structure and property names must be verified against the documentation for the exact binder version in use.

For RabbitMQ or Pulsar, use the corresponding binder namespace and verify property names by version. Do not copy a Kafka configuration to another binder merely by swapping the broker name.

## 5. Selecting a default binder and per-binding binder

When an application uses only one binder, the framework can usually pick the matching binder automatically from dependencies and existing configuration. When an application has multiple binders or wants an explicit selection, you can declare a default binder:

```yaml
spring:
  cloud:
    stream:
      default-binder: kafka
```

A single binding can override that choice using the `binder` property:

```yaml
spring:
  cloud:
    stream:
      default-binder: kafka
      bindings:
        orderCreated-in-0:
          destination: orders.created
          group: inventory-service
          binder: kafka
        alertEvents-out-0:
          destination: inventory.alerts
          binder: rabbit
```

The names `kafka` and `rabbit` here must correspond to binders registered in the application. When configuring multiple instances of the same binder type, declare each binder under `spring.cloud.stream.binders` with its own name, type, and environment; then reference that name from the binding's `binder` property.

Choosing a binder per binding is an integration decision. Application services should not inspect binder names to drive business rules. If a flow needs to send to two systems, model two output ports or two output adapters and configure each binding accordingly.

## 6. Configuration precedence order

When investigating effective values, distinguish two levels of precedence:

1. **Within Spring Cloud Stream configuration:** default values apply when a binding does not declare its own value; per-binding properties override the corresponding defaults. Binder extension properties control binder-specific behavior.
2. **Across Spring Boot configuration sources:** config files, profile-specific files, environment variables, system properties, and command-line arguments have their own precedence order. Higher-priority sources can override values in `application.yml`.

Example base file:

```yaml
spring:
  cloud:
    stream:
      default:
        consumer:
          max-attempts: 3
      bindings:
        orderCreated-in-0:
          destination: orders.created
          group: inventory-service
```

A production profile file can override a specific value:

```yaml
# application-prod.yml
spring:
  cloud:
    stream:
      bindings:
        orderCreated-in-0:
          consumer:
            max-attempts: 5
```

When running with the `prod` profile, the `orderCreated-in-0` binding uses five attempts. Other bindings still use the default value of three unless overridden by a higher-priority configuration source.

Environment-varying values can also be passed via environment variables:

```text
SPRING_CLOUD_STREAM_BINDINGS_ORDERCREATED_IN_0_CONSUMER_MAX_ATTEMPTS=5
```

This variable name illustrates Spring Boot's rule for converting property names to uppercase and underscores. For binding names containing hyphens or special characters, verify Spring Boot's environment-variable binding rules and check the effective runtime value at startup. For complex configurations, profile YAML files are usually easier to read and less error-prone.

Do not assume a value in a YAML file is the final value. When local, test, staging, and production differ, check active profiles, environment variables, and launch arguments.

## 7. Configuring per environment without duplicating entire files

A maintainable pattern is placing shared settings in `application.yml` and recording only differences in profiles:

```yaml
# application.yml
spring:
  cloud:
    function:
      definition: orderCreated;processPayment
    stream:
      default:
        content-type: application/json
        consumer:
          max-attempts: 3
      bindings:
        orderCreated-in-0:
          destination: orders.created
          group: inventory-service
        processPayment-in-0:
          destination: payments.authorized
          group: billing-service
```

```yaml
# application-dev.yml
spring:
  cloud:
    stream:
      bindings:
        orderCreated-in-0:
          destination: dev.orders.created
```

```yaml
# application-prod.yml
spring:
  cloud:
    stream:
      bindings:
        orderCreated-in-0:
          destination: orders.created
        processPayment-in-0:
          consumer:
            max-attempts: 5
```

Profile files only declare what differs. Remaining values are inherited from the shared configuration, provided no higher-priority configuration source changes them.

Never put passwords, tokens, or credentials into committed files. Use a secret manager or managed environment variables in the deployment environment. Destinations, groups, and retry counts should also be treated as deliberate operational configuration; avoid letting every developer machine pick uncontrolled values.

## 8. Common configuration mistakes

| Symptom | Possible cause | How to check |
|---|---|---|
| Binding does not use default retry | Placed at wrong level or wrong binding name | Cross-check function name and `-in-0`/`-out-0` suffix |
| One binding fails to receive JSON | Binding content type overrides default or producer sends different format | Check content type on both sides and schema |
| RabbitMQ ignores Kafka property | Extension property placed under wrong namespace | Move property into the right binder's namespace |
| Local and production have different retry counts | Profile or environment variable override | Check active profiles and externalized configuration |
| Binding uses the wrong broker | Wrong `default-binder` or `binder` | Check registered binder names and binding selection |
| Config changed but behavior did not | Misspelled property, unsupported option, or overridden elsewhere | Check startup logs, bound config, and exact version docs |
| Retries exceed expectations | Framework retries combined with broker redelivery | Check attempt counts at each layer and ack/offset state |

An invalid property may be ignored, cause a startup failure, or have no effect depending on how the binder and version handle it. Never conclude everything is fine solely because the application booted successfully.

## 9. Procedure to verify effective configuration

When a binding behaves unexpectedly, check in sequence:

1. Identify the activated function bean via `spring.cloud.function.definition`.
2. Compute the exact binding name from the function name and input/output position.
3. Look up default settings in `spring.cloud.stream.default`.
4. Look up binding-specific settings in `spring.cloud.stream.bindings.<bindingName>`.
5. Inspect extension properties in the binder's namespace.
6. Identify the selected binder via `default-binder` or the binding's `binder` property.
7. Check active profiles, environment variables, system properties, and command-line arguments.
8. Verify behavior with integration tests or inspect startup logs / Actuator environment if the application is allowed to expose that endpoint safely.

Do not expose configuration management endpoints publicly just for debugging. When using Spring Boot Actuator, restrict access and avoid exposing credentials or sensitive data.

### Example verification via tests

You can test configuration at the application context level with Spring Boot tests, then use the Test Binder to send messages and observe behavior. A pure unit test that only reads configuration objects does not prove the binder actually applies retries, partitioning, or DLQs. Extension properties must be tested against the corresponding binder.

Example test cases to include:

- A binding without dedicated settings receives default values.
- A binding with its own `max-attempts` uses the overridden value.
- A binding with its own content type converts payloads properly.
- The production profile overrides the base configuration.
- Bindings select the right binder when the application has multiple binders.
- Kafka/Rabbit/Pulsar properties only affect bindings using the matching binder.

## Conclusion

Putting shared settings in `spring.cloud.stream.default` lets bindings share consistent policies. When one stream needs different behavior, declare values in `spring.cloud.stream.bindings.<bindingName>`; specific configuration overrides the corresponding defaults. Broker-specific properties belong in the appropriate binder's namespace.

When deploying Spring Cloud Stream with Kafka, RabbitMQ, or Pulsar, organize shared settings, per-binding settings, and binder extensions in their proper scopes. Check binding names, selected binders, profiles, and external configuration sources to verify the final behavior. Configuration should only be considered correct once verified against the real binder and deployment environment.
