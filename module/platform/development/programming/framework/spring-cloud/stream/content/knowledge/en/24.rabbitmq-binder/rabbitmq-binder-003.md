# Exchange Names, Queue Names, and Resource Prefixes

In the Spring Cloud Stream RabbitMQ Binder, `destination` and `group` directly affect the names of resources created on the broker. Typically, `destination` determines the exchange; when a consumer declares `group`, the binder creates a queue attached to that exchange. The `queueNameGroupOnly` property changes how queue names are formed, while `spring.cloud.stream.rabbit.binder.prefix` adds a common prefix to the exchange and queue names managed by the binder.

Understanding naming rules helps avoid creating the wrong resources, prevent collisions across environments, and ensure producers and consumers connect to the right topology. Exchange name, queue name, and routing key are three distinct concepts: an exchange receives messages, a queue stores messages for consumers, and a routing key helps the exchange decide which queues receive a message.

This lesson belongs to the **RabbitMQ Binder** chapter of the `SPRING_CLOUD_STREAM` module, focusing on exchange names, queue names, and resource prefixes in the `Supplier`/`Function`/`Consumer` model. It also explains the relationships among destination, consumer group, routing key, virtual host, provisioning, and safe renaming workflows.

## 1. RabbitMQ Resources to Distinguish

RabbitMQ uses several AMQP resource types to route and store messages:

| Resource | Role | Example |
|---|---|---|
| Exchange | Receives messages from producers and routes them based on exchange type/routing key | `orders.events` |
| Queue | Stores messages waiting for consumers to receive | `orders.events.inventory-projection` |
| Binding | Links an exchange to a queue, optionally with a binding key | Exchange `orders.events` binds to the inventory queue with `orders.*` |
| Routing key | Value sent by a producer with a message for exchange routing | `orders.created` |
| Virtual host (vhost) | Independent resource namespace and permission boundary inside the broker | `/production` |

```text
Producer
   |
   | publish(exchange, routingKey, message)
   v
Exchange: orders.events
   |
   | binding key: orders.created
   v
Queue: orders.events.inventory-projection
   |
   v
Consumer group: inventory-projection
```

An exchange is not where consumers pull messages directly. A queue is what holds messages for consumers. One exchange can be bound to multiple queues; one queue can also be bound to multiple exchanges. Exchange and queue names may be related by binder conventions, but they remain two separate resources.

## 2. `destination` Typically Determines the Exchange Name

In the RabbitMQ Binder, a binding's `destination` is typically used as the exchange name that the binder connects to or declares. Example:

```yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.events
          content-type: application/json
```

With this configuration, the output binding `publishOrder-out-0` sends messages to the `orders.events` exchange within the active vhost and binder configuration. A producer does not necessarily create a queue; queues are typically declared by consumer bindings or by a separate topology management process.

If both producer and consumer use `destination: orders.events`, they reference the same logical exchange. The consumer also needs a queue to receive messages. The queue name depends on the group and Rabbit binder configuration.

Do not confuse the function name or binding name with the exchange name. `publishOrder-out-0` is the binding name in the application; `orders.events` is the destination and typically the exchange on RabbitMQ.

## 3. `group` Participates in Constructing the Queue Name

For a consumer binding with a group, the RabbitMQ Binder defaults to naming the queue from the destination and group. Common convention:

```text
<destination>.<group>
```

Example:

```yaml
spring:
  cloud:
    function:
      definition: projectInventory
    stream:
      bindings:
        projectInventory-in-0:
          destination: orders.events
          group: inventory-projection
```

The corresponding default queue name is:

```text
orders.events.inventory-projection
```

Replicas of the same logical consumer must share the same group. They then consume from the shared queue together, and RabbitMQ distributes messages among consumers using competing consumers. If another application uses a separate group, the binder creates a separate queue bound to the exchange; each group can receive a copy of messages according to the binding/routing topology.

Example with two independent consumers:

| Consumer | Destination | Group | Default queue |
|---|---|---|---|
| Inventory projection | `orders.events` | `inventory-projection` | `orders.events.inventory-projection` |
| Analytics projection | `orders.events` | `analytics-projection` | `orders.events.analytics-projection` |

The two queues serve two different processing purposes. Do not create a separate group for each pod of the same application if the goal is load sharing; doing so gives each pod its own queue and an independent copy instead of competing on a single queue.

## 4. Consumers Without a Group

If `group` is not declared, the consumer is typically treated as an anonymous subscription. The RabbitMQ Binder can create a temporary/anonymous queue with a binder- or broker-generated name, usually with auto-delete or non-durable characteristics depending on configuration.

This subscription style is useful for experiments or consumers that only need to receive messages while the application is running. It is unsuitable when you need a stable queue to retain messages while the application is offline.

For production consumers requiring durability, declare a stably named group. A stably named queue ensures:

- Messages continue to be retained while the consumer is temporarily stopped, provided the queue is durable and messages are published persistently as configured.
- Multiple replicas participate in the same queue.
- Administrators can monitor backlog, consumers, and permissions.
- Topology can be provisioned and verified prior to deployment.

Declaring a group alone is not enough to satisfy all durability conditions. Verify durable queue settings, durable exchange settings, delivery mode, TTL, and RabbitMQ policies.

## 5. `queueNameGroupOnly` Changes Queue Naming

The RabbitMQ Binder provides the `queueNameGroupOnly` property. When kept at its default `false`, the queue usually includes both the destination and the group. When set to `true`, the queue name is based solely on the group.

Example:

```yaml
spring:
  cloud:
    function:
      definition: projectInventory
    stream:
      bindings:
        projectInventory-in-0:
          destination: orders.events
          group: inventory-projection
      rabbit:
        bindings:
          projectInventory-in-0:
            consumer:
              queue-name-group-only: true
```

The queue name in group-only mode is:

```text
inventory-projection
```

Comparison:

| `queue-name-group-only` | Conventional queue name |
|---|---|
| `false` | `orders.events.inventory-projection` |
| `true` | `inventory-projection` |

This property only changes how the queue name is constructed. It does not change the exchange name derived from `destination`, does not change routing keys, and does not turn a group into an exchange.

### When to Use Group-Only?

Group-only mode is useful when the system already follows a queue naming convention independent of destinations or needs compatibility with an externally managed RabbitMQ topology. However, the group name must be unique within the vhost and binder scope. If two different destinations both use the group `worker`, they may target the same `worker` queue, causing collisions or merging streams unexpectedly.

Only enable `queueNameGroupOnly` after auditing all consumers sharing the vhost and confirming group names do not collide. Without external topology compatibility requirements, the default name combining destination and group is usually easier to trace.

## 6. Adding Prefixes with the Rabbit Binder `prefix`

The Rabbit binder provides a binder-level `prefix` property to prepend a string to the exchange and queue names declared by the binder. It is typically configured at:

```text
spring.cloud.stream.rabbit.binder.prefix
```

Example:

```yaml
spring:
  cloud:
    stream:
      rabbit:
        binder:
          prefix: "prod."
```

With destination `orders.events` and group `inventory-projection`, resource names are prefixed according to convention:

| Resource | Without prefix | With `prod.` prefix |
|---|---|---|
| Exchange | `orders.events` | `prod.orders.events` |
| Default queue | `orders.events.inventory-projection` | `prod.orders.events.inventory-projection` |
| Group-only queue | `inventory-projection` | `prod.inventory-projection` |

The prefix becomes part of the physical resource name. The application can still use the logical destination `orders.events` in binding configuration; the binder adds the prefix when declaring/resolving RabbitMQ resources according to configuration.

A prefix helps distinguish resources across environments or application groups on the same vhost, such as `dev.`, `staging.`, and `prod.`. However, a prefix is not a security boundary and does not replace virtual hosts or ACLs.

## 7. Prefix Applies to Resource Names, Not Routing Keys

The Rabbit binder prefix is intended to prepend a prefix to exchange and queue names managed by the binder. Routing keys and binding keys are message routing values; they follow their own configuration rules.

Example:

```text
prefix = prod.
destination = orders.events
group = inventory-projection
binding key = orders.created

Exchange:    prod.orders.events
Queue:       prod.orders.events.inventory-projection
Binding key: orders.created
```

Do not automatically prepend `prod.` to routing keys just because a binder prefix is configured. If routing keys need to distinguish environments or tenants, design them as part of a separate routing contract and configure producers and consumers consistently.

## 8. Complete Producer and Consumer Configuration

Example of a producer emitting order events and an inventory consumer receiving them:

```yaml
spring:
  cloud:
    function:
      definition: publishOrder;projectInventory
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.events
          content-type: application/json
        projectInventory-in-0:
          destination: orders.events
          group: inventory-projection
          content-type: application/json
      rabbit:
        binder:
          prefix: "prod."
        bindings:
          publishOrder-out-0:
            producer:
              exchange-type: topic
          projectInventory-in-0:
            consumer:
              queue-name-group-only: false
              binding-routing-key: "orders.*"
```

Expected logical topology:

```text
Producer binding: publishOrder-out-0
Destination: orders.events
          |
          v
Exchange: prod.orders.events (topic)
          |
          | binding key: orders.*
          v
Queue: prod.orders.events.inventory-projection
          |
          v
Consumer binding: projectInventory-in-0
```

Producer and consumer share the logical destination `orders.events`; the binder prefix turns the physical exchange name into `prod.orders.events`. The consumer group creates a logical queue from the destination and group, with the prefix prepended to the queue name. The binding key `orders.*` determines which messages are routed to the queue on the topic exchange.

If the exchange already exists with type `direct` and a new binding attempts to declare the same name with type `topic`, RabbitMQ may reject the redeclaration because the exchange attributes are incompatible. All producers and consumers sharing an exchange must agree on the exchange type and topology attributes.

## 9. Exchange Type Is Not the Exchange Name

`exchange-type` determines how the exchange routes messages, not how the destination name is formed. Common types:

| Exchange type | Routing behavior | Example |
|---|---|---|
| `direct` | Routing key must match the binding key exactly | `orders.created` |
| `topic` | Routing key matches patterns containing `*` and `#` | `orders.*`, `orders.#` |
| `fanout` | Sends to every bound queue regardless of routing key | Broadcasting notifications to multiple consumers |
| `headers` | Routes based on message headers and binding arguments | Messages with header `region=apac` |

For example, `destination: orders.events` remains the logical exchange name whether `exchange-type` is `direct` or `topic`. When multiple bindings declare the same exchange, they must agree on the exchange type and declaration properties.

## 10. Virtual Host vs. Prefix

A RabbitMQ virtual host creates a separate resource namespace. Two vhosts can have exchanges and queues with identical names, yet they remain independent resources. A prefix only changes the name string within the same resource namespace.

| Criterion | Prefix | Virtual host |
|---|---|---|
| Purpose | Distinguish resource names | Isolate resources and access permissions |
| Scope | Within a single vhost | Separates resources within the broker |
| ACLs | Does not create a permission boundary by itself | Has per-vhost configure/write/read permissions |
| Duplicate names | Can still collide if prefixes match | Same names can be used in different vhosts |
| Example | `prod.orders.events` | Vhost `/production` containing `orders.events` |

If production and staging environments require data and access isolation, use separate vhosts or separate clusters as required by security policy. A prefix helps identify resources and avoid name collisions when multiple applications share a vhost, but it should not be treated as a data protection mechanism.

## 11. Setting Prefixes by Environment

You can pass the prefix via environment configuration to reuse the same artifact across environments:

```yaml
spring:
  cloud:
    stream:
      rabbit:
        binder:
          prefix: "${RABBIT_RESOURCE_PREFIX:dev.}"
```

Example values:

```text
Local:       RABBIT_RESOURCE_PREFIX=local.
Development: RABBIT_RESOURCE_PREFIX=dev.
Staging:     RABBIT_RESOURCE_PREFIX=staging.
Production:  RABBIT_RESOURCE_PREFIX=prod.
```

Place the prefix in environment configuration or the platform's secret/config management. Avoid hardcoding environment names into every destination, as that duplicates binding configuration and makes changes harder.

Prefixes should stay stable throughout the deployment lifecycle. Changing from `prod.` to `production.` can cause the binder to start declaring new exchanges/queues while the old resources remain. Messages waiting in the old queue do not automatically move to the new queue.

## 12. Resource Naming Guidelines

Resource names should be readable, stable, and manageable. A common convention:

```text
<environment>.<domain>.<event>
<environment>.<domain>.<event>.<consumer-group>
```

Example:

```text
Exchange: prod.orders.events
Queue:    prod.orders.events.inventory-projection
Queue:    prod.orders.events.analytics-projection
```

Recommendations:

- Use lowercase letters and dots or hyphens consistently.
- Names should reflect the domain/event or consumer role, without containing personal data.
- Keep names stable across deployments and restarts.
- Avoid using arbitrary request data to construct exchange/queue names.
- Keep lengths bounded; RabbitMQ enforces protocol/broker limits on queue/exchange names, so prefer short, structured names.
- Make groups specific enough to avoid collisions when using `queueNameGroupOnly`.
- Do not embed build numbers or pod IDs in durable queue names.

Do not share a single prefix across two applications if they need different topologies or permissions without a further namespacing convention. Resource names should reflect ownership and operational lifecycle.

## 13. Prefixes and Provisioning Permissions

The RabbitMQ Binder can declare exchanges, queues, and bindings based on binding configuration. For the binder to auto-create resources, the connection account needs appropriate configure permissions in the vhost; producers need write permissions on exchanges, and consumers need read permissions on queues.

When infrastructure is pre-provisioned with Terraform, Ansible, or broker administration workflows, align physical names with the binder. If the binder still attempts to declare an existing resource with a different type, durability, or arguments, RabbitMQ may reject the declaration. If your organization requires the binder not to auto-declare certain resources, configure the corresponding declaration/binding options for your Rabbit binder version and test against the provisioned topology.

Example permissions to review:

| Component | Required role-based permissions |
|---|---|
| Producer | Write to the exchanges the producer publishes to |
| Consumer binder | Read queues; configure/bind if the binder auto-declares topology |
| Infrastructure admin | Configure exchanges/queues/bindings and policies |
| Monitoring tools | Read/inspect metadata according to granted permissions |

Do not grant full-vhost administrative permissions to an application just so it can publish. Grant least-privilege permissions scoped to each service's resources and responsibilities.

## 14. Changing Destination, Group, or Prefix Is a Topology Change

Renaming an exchange or queue is not simply editing a string in a YAML file. RabbitMQ does not automatically migrate messages from old resources to new ones.

Example of changing a prefix:

```text
Before: prod.orders.events
After:  production.orders.events
```

After deploying the new configuration, the binder may declare the new exchange. A new queue may also be created and bound to the new exchange. The old queue may still hold unprocessed messages, and old consumers may still be active.

A migration workflow should:

1. Inventory existing exchanges, queues, bindings, and backlogs.
2. Create the new resources with agreed names and attributes.
3. Configure producers to publish to the new exchange, or perform controlled dual-publishing if needed.
4. Start new consumers and verify queues/bindings are correct.
5. Drain or replay remaining messages in the old queue according to policy.
6. Cut over all producers/consumers to the new topology.
7. Confirm the old queue has no remaining messages or consumers before deleting it.
8. Record the mapping between old and new names for auditability.

Do not delete an old queue immediately after changing a group or prefix without checking the backlog. Deleting it can drop unprocessed messages.

## 15. Avoiding Collisions with Multiple Binders or Services

A Spring Cloud Stream application can use multiple binders, each with its own configuration namespace and broker connection. The Rabbit resource prefix belongs to the Rabbit binder; it does not apply to Kafka topics or Pulsar topics.

If multiple services share a RabbitMQ vhost, establish:

- Which service owns each exchange and queue.
- Which services are allowed to bind queues to exchanges.
- Whether prefixes distinguish environments or domains.
- Whether group names are unique if using group-only queue naming.
- Whether exchanges sharing a name share the same type and declaration arguments.
- Who is responsible for cleaning up resources when a service is decommissioned.

Do not create a separate queue per replica of the same consumer group when competing consumers are desired. Likewise, do not share the same queue across two independent services if both must receive complete copies of messages; two services need two separate queues and two separate bindings.

## 16. Verifying Resource Names at Runtime

Do not rely solely on logical names in YAML. After the application starts, inspect the physical names in the RabbitMQ Management UI or RabbitMQ CLI:

- Does the exchange have the expected prefix and destination?
- Does the queue follow destination/group or group-only naming as intended?
- Are queue durability and auto-delete settings as required?
- Does the binding key match the intended pattern?
- Does the exchange type match between producer and consumer?
- Are consumers connected to the queue?
- Are messages entering the expected queue?

You can use RabbitMQ CLI commands to list resources in the corresponding vhost:

```bash
rabbitmqctl list_exchanges -p /production name type durable
rabbitmqctl list_queues -p /production name durable auto_delete messages consumers
rabbitmqctl list_bindings -p /production source_name destination_name routing_key
```

These commands require appropriate administrative permissions and must run on a node/cluster with the RabbitMQ CLI tools. In production environments, reading topology metadata should follow authorized operational permissions.

## 17. Testing Naming Rules

An integration test suite should verify actual exchange and queue names after the binder declares the topology:

| Scenario | Configuration | Expected verification |
|---|---|---|
| Default names | destination and group, no prefix | Exchange equals destination; queue follows destination/group |
| Prefix | Prefix `dev.` | Exchange/queue names carry the expected prefix |
| Group-only | `queue-name-group-only: true` | Queue name is based solely on group, with prefix if configured |
| Two groups | Same destination, different groups | Two independent queues both bound to the exchange |
| Same group, multiple replicas | Replicas sharing destination/group | Both consume from the same queue |
| Anonymous consumer | No group declared | Verify anonymous queue and actual lifecycle |
| Routing key | Topic/direct exchange and specific binding key | Messages arrive in the expected queue |
| Environment prefixes | `dev.` and `prod.` | Resource names do not collide by design |
| Exchange declaration conflict | Same name with different exchange type | Broker rejects declaration; caught before deploy |
| Prefix migration | Switching from old prefix to new prefix | Old queue is drained/replayed before cleanup |

The Test Binder can test message flows at the Spring layer, but it does not fully verify real RabbitMQ exchange/queue names and bindings. Integration tests with a compatible broker or topology verification via the RabbitMQ management API/CLI are needed.

## 18. Observability and Operations

Monitor these metrics:

- Number of exchanges and queues created per prefix.
- Queue backlog, oldest message age, and message growth rate.
- Consumer count per queue.
- Rate of unroutable publishes or returned messages if publisher returns are enabled.
- Declaration errors caused by resources with the same name but differing attributes.
- Permission errors on configure, write, read, or bind operations.
- Number of queues with zero consumers or leftover resources after migration.

Logs should include binding name, logical destination, group, and vhost; where possible, log the resolved physical exchange/queue names as well. Do not log sensitive payloads or credentials. Bound metric label cardinality if many dynamic destinations exist.

Set alerts when queues have zero consumers, backlogs grow continuously, exchange/queue declarations fail, or resource counts spike unexpectedly after a deployment.

## 19. Workflow for Designing Exchange, Queue, and Prefix Names

When configuring the RabbitMQ Binder:

1. Choose a stable destination for the exchange by domain/event.
2. Choose a stable group for each logical consumer.
3. Decide between default destination/group queue naming or group-only naming.
4. If using group-only, guarantee group names are unique within the vhost/binder namespace.
5. Choose prefixes by environment or application namespace if multiple topologies share a vhost.
6. Distinguish prefixes from vhosts; use vhosts/ACLs when security isolation is required.
7. Align exchange type, durability, and binding arguments across services.
8. Provision resources and grant appropriate configure/write/read permissions.
9. Inspect physical names via the RabbitMQ Management UI or CLI.
10. Plan migrations when changing destination, group, or prefix; drain old queues before cleanup.

## 20. Self-Check

- [ ] Can distinguish exchange, queue, binding, and routing key.
- [ ] Can explain why destination typically determines the exchange name.
- [ ] Can explain how group participates in constructing the default queue name.
- [ ] Can distinguish named consumer groups from anonymous subscriptions.
- [ ] Know how `queueNameGroupOnly` changes queue names.
- [ ] Can configure `spring.cloud.stream.rabbit.binder.prefix`.
- [ ] Understand that prefix applies to resource names and does not automatically alter routing keys.
- [ ] Can distinguish prefix from RabbitMQ virtual host.
- [ ] Know that exchange type and declaration arguments must be consistent across bindings.
- [ ] Can design a safe migration when changing destination, group, or prefix.
- [ ] Can verify the live topology using RabbitMQ Management UI/CLI.

## Conclusion

In the RabbitMQ Binder, `destination` typically determines the exchange; `group` participates in creating the queue following the destination-plus-group convention. `queueNameGroupOnly` can shorten the queue name to just the group, while `spring.cloud.stream.rabbit.binder.prefix` prepends a prefix to binder-managed exchange and queue names. Prefixes help distinguish resources across environments, but they do not replace virtual hosts or ACLs. Keep names stable, prevent group collisions, align exchange declarations, and inspect the live topology. When changing names or prefixes, execute a migration and drain old queues to avoid dropping messages.
