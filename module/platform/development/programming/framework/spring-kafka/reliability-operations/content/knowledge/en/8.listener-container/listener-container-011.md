# missingTopicsFatal

In Spring Kafka, **missingTopicsFatal** is a listener container property that decides whether the container is allowed to start when one or more topics explicitly declared for the listener do not yet exist on the Kafka broker. When this property is enabled, the container refuses to start if checks detect that required topics are missing. When disabled, the container may log a warning and continue starting; the consumer then proceeds according to Kafka's subscription and metadata mechanisms.

This property is useful when an application depends on a set of topics that must already exist before receiving traffic. It helps catch deployment errors early, such as misspelled topic names, forgotten topic creation, or deploying consumers ahead of Kafka infrastructure. However, `missingTopicsFatal` only checks topic existence during container startup. It does not create topics, does not fully validate partition/replication configuration, does not replace ACLs, and is not a continuous monitor if a topic is deleted later.

## 1. Why does a listener container need to check topics?

A listener container needs to know which topics to subscribe to. With explicit topic declarations, applications usually expect those topics to have been pre-provisioned:

~~~java
@KafkaListener(topics = "orders.created", groupId = "billing-service")
public void handle(OrderCreated event) {
    billingService.process(event);
}
~~~

If the `orders.created` topic does not exist yet, the application may face several situations:

- The topic name in configuration is misspelled.
- Infrastructure has not created the topic before deploying the consumer.
- The consumer starts earlier than the provisioning workflow.
- The topic was accidentally deleted or not created in the cluster the application connects to.
- The application is pointing at the wrong environment or cluster.

Without a startup check, the consumer might start and wait for metadata/topics via Kafka mechanisms. That is sometimes desired when topics are created later, but it can also allow configuration mistakes to go unnoticed until the system is already running.

`missingTopicsFatal` lets you choose startup behavior matching your application's requirements:

| Setting | Behavior when declared topic does not exist yet |
|---|---|
| `false` | Container may log a warning and continue starting; consumer waits for topic/metadata via Kafka mechanisms |
| `true` | Container throws an error and fails to start if checks determine required topics are missing |

In many Spring Kafka versions, the default for this property is `false`; the default changed in Spring Kafka 2.3. For projects on older versions or custom setups, check Javadoc and actual configuration rather than relying on another version's default.

## 2. When does missingTopicsFatal take effect?

The property is used during listener container startup, when the container checks configured topics. With an explicit topic list, the container can query brokers for topic metadata/partitions to determine whether topics exist.

General flow:

~~~
Spring starts listener container
             |
             v
Container checks declared topics
             |
       +-----+-----+
       |           |
  Topics exist   Topics missing
       |           |
       v           v
   Subscribe    missingTopicsFatal?
   and run           |
                +---+---+
                |       |
              false    true
                |       |
                v       v
             Warning   Error,
             and       container
             continue  does not start
~~~

This is a startup-time check, not a continuously running monitor. If a topic is deleted after the container has started, `missingTopicsFatal` does not automatically re-run as a health check. The consumer may receive metadata errors, fetch errors, or other states from the Kafka client; applications must monitor logs, metrics, and container status to detect this.

If the container is configured with `autoStartup=false`, the check happens when the container is actually started. Bean creation or Spring context initialization completion does not mean the listener container has already checked topics.

When `autoStartup=true`, listener containers typically start during the Spring lifecycle. If `missingTopicsFatal=true` and a required topic is missing, a container startup failure can cause application startup to fail depending on how the listener registry/containers are started and how the application manages lifecycle. Verify this behavior in a real runtime environment, especially if the application has multiple listener containers with different startup policies.

## 3. Configuring in Spring Kafka

You can set the property directly on the listener container factory's `ContainerProperties`:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
ordersListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);

    factory.getContainerProperties().setMissingTopicsFatal(true);

    return factory;
}
~~~

Listeners using this factory inherit the `missingTopicsFatal` setting of container properties, unless the application creates and configures containers separately.

If you want the container to continue starting while topics may be created later, set `false`:

~~~java
factory.getContainerProperties().setMissingTopicsFatal(false);
~~~

Do not apply a single value to all listeners if topics have different requirements. A listener reading a mandatory business topic may need fail-fast behavior; a listener reading dynamically created per-tenant topics may need to wait for topics to appear. Separate container factories can express those policies.

### 3.1. Configuring via Spring Boot

With Spring Boot, the listener property can be declared in `application.yml`:

~~~yaml
spring:
  kafka:
    listener:
      missing-topics-fatal: true
~~~

This value applies to listener containers auto-configured by Boot under the corresponding configuration. If the application defines multiple custom factories or overrides `ContainerProperties` in code, inspect the actual factory used by each `@KafkaListener`.

Example listener selecting a specific factory:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "billing-service",
    containerFactory = "ordersListenerFactory"
)
public void handle(OrderCreated event) {
    billingService.process(event);
}
~~~

If the listener uses a factory other than the one configured with `missingTopicsFatal`, the value on the default factory may not apply. Check `containerFactory` on the annotation, registry, and bean configuration.

Spring Boot property names and binding depend on the Boot version. For older projects, check the configuration metadata of the version in use. If the property is not bound, YAML configuration may sit unused without affecting listeners.

## 4. missingTopicsFatal does not create topics

A common misconception is that enabling `missingTopicsFatal` makes Spring Kafka create missing topics. This property only decides how the container reacts to missing topics during the startup check.

It does not replace:

- `KafkaAdmin`.
- `NewTopic` beans.
- Topic creation via Kafka CLI.
- Terraform, Helm, or infrastructure management tools.
- Broker-side `auto.create.topics.enable` policy.

If a topic must exist before consumers run, provision the topic through an explicit infrastructure process and use `missingTopicsFatal=true` to catch drift.

### 4.1. Declaring topics with NewTopic

Spring Kafka supports declaring topics via `NewTopic` beans so `KafkaAdmin` can create topics at application startup:

~~~java
@Bean
NewTopic ordersCreatedTopic() {
    return TopicBuilder.name("orders.created")
            .partitions(6)
            .replicas(3)
            .build();
}
~~~

This example requires a broker cluster with enough brokers to satisfy a replication factor of 3. In a single-broker local environment, set `replicas` to match the test infrastructure.

`KafkaAdmin` uses topic administration permissions to check and create topics. The application's principal must have corresponding privileges if the application is responsible for provisioning. In production, many organizations separate topic-creation privileges from consume/produce privileges; topics are created by an infrastructure pipeline and the application only holds usage permissions.

If relying on `NewTopic` beans, ensure topic creation completes before listeners need to subscribe. Spring Boot and Spring Kafka integrate `KafkaAdmin` with lifecycle, though exact ordering depends on context and container configuration. For strict deployment workflows, provisioning topics in an infrastructure deployment step prior to starting the application is usually easier to control.

### 4.2. Broker-side auto-create topics

Kafka brokers can be configured to auto-create topics when clients access nonexistent topics. This is convenient for test environments but can produce topics with partition counts, replication factors, and retention settings unsuitable for production requirements.

Do not rely on auto-create as the primary provisioning mechanism for critical business topics. If auto-create is enabled, a metadata check may trigger topic creation depending on broker/client behavior and permissions. Then `missingTopicsFatal` might fail to detect that a topic was not properly provisioned because the topic appeared with default settings.

Separating the two responsibilities is clearer:

1. Infrastructure or `KafkaAdmin` creates topics with desired settings.
2. Listener container checks required topics exist before starting.
3. Monitoring confirms topics and partitions remain healthy post-startup.

## 5. Topic existence does not mean the topic is ready

`missingTopicsFatal` checks topic existence within the container's checking capabilities. It is not a comprehensive validator of Kafka topology.

A topic may exist yet fail to meet requirements:

- Fewer partitions than expected.
- Replication factor lower than durability policy.
- Insufficient ISR or some replicas offline.
- Wrong retention or cleanup policy.
- Message size limit incompatible with payloads.
- ACLs disallowing the consumer from reading or the group from committing offsets.
- Topic exists on a different cluster than the one the application needs.

For example, a listener expects `orders.created` to have 12 partitions for parallel processing, yet the topic actually has only 3 partitions. Neither `missingTopicsFatal=false` nor `true` necessarily catches partition-count mismatches once the topic exists.

If startup must validate partition counts, replication, or topic configuration, add a preflight step using `AdminClient` or verify during the provisioning pipeline. Separate container existence checks from infrastructure readiness checks.

## 6. Explicit topics and topicPattern

Spring Kafka supports registering listeners via an explicit topic list or via a regex pattern.

Explicit topics:

~~~java
@KafkaListener(topics = {"orders.created", "orders.updated"})
public void handle(OrderEvent event) {
    service.process(event);
}
~~~

Topic pattern:

~~~java
@KafkaListener(topicPattern = "orders\\..*")
public void handle(OrderEvent event) {
    service.process(event);
}
~~~

With an explicit topic list, the container knows the exact topic names to verify. With `topicPattern`, matching topics can change over time and the broker/client can discover new matching topics during metadata refreshes.

Do not assume `missingTopicsFatal` validates every topic a regex might match like a static list. Checking behavior and what happens when a pattern matches no topics yet can depend on subscription type and Spring Kafka version. If the application must ensure at least one topic exists at startup, perform a dedicated preflight check with `AdminClient` and verify your version's behavior.

Pattern subscriptions fit dynamic topics, but constrain regex scope so consumers do not accidentally subscribe to unrelated topics. When using patterns, monitor the actual list of subscribed topics and principal permissions.

## 7. Distinguishing missing topics from unavailable brokers or metadata

Not every failure when the container checks topics means the topic does not exist.

Different scenarios:

| Scenario | Possible symptoms | Investigation direction |
|---|---|---|
| Topic genuinely not created yet | Metadata does not find topic or container reports missing topic | Check topic name and provisioning |
| Broker unreachable | Timeout, disconnect, bootstrap/metadata request failure | Check DNS, network, broker listeners, and TLS |
| Authentication failure | SASL/SSL authentication exception | Check credentials, mechanism, truststore |
| Authorization failure | Topic/group authorization exception | Check ACLs and principal |
| Topic exists without leader | Leader unavailable or metadata unstable | Check partition state and brokers |
| Topic exists with wrong topology | Listener starts but partition/replication counts fail requirements | Inspect with `AdminClient` or admin tools |

If brokers are starting up or metadata is not yet ready, topic checks can fail due to connection errors rather than accurately proving a topic does not exist. Read the root exception and Kafka client logs before changing `missingTopicsFatal`.

Disabling `missingTopicsFatal` will not fix unreachable brokers, bad credentials, or missing ACLs. It only changes the reaction to missing topics during the startup check.

## 8. Impact on startup and deployment

Choosing `missingTopicsFatal` is a decision between failing fast and allowing the listener to wait for topics to appear.

### 8.1. When to enable true

Enabling `true` fits when:

- The topic is a mandatory dependency for core application functionality.
- The topic must be created beforehand by an infrastructure pipeline.
- Starting the consumer before the topic exists constitutes a deployment error.
- Startup/readiness should reflect missing critical dependencies.
- You do not want the application appearing healthy while unable to consume data.

In this model, deployment pipelines should create topics before deploying consumers. If a topic is missing, startup failure creates a clear signal to halt the pipeline and fix provisioning.

### 8.2. When to leave false

`false` fits when:

- Topics are created dynamically after the application starts.
- The environment permits consumers to wait for topics to appear.
- The listener does not need to run immediately during bootstrap.
- Topic patterns or subscriptions have a changing set of topics.
- The system has dedicated retry/monitoring workflows watching for topic creation.

In return, the application may run while the listener is not yet receiving data from missing topics. Metrics/alerts are needed for consumers lacking partition assignments or making no progress, rather than relying solely on the Spring application reporting UP.

### 8.3. Policy selection table

| System characteristic | Recommendation |
|---|---|
| Fixed business topic, provisioned before deploy | `true` |
| Topic created by IaC pipeline before app start | `true` |
| Topic created per tenant at runtime | `false` or per-tenant preflight |
| Pattern subscription picking up new topics over time | Evaluate pattern behavior; usually needs dedicated monitoring |
| Local development with auto-created topics | `false` may be convenient, but does not reflect production policy |
| Mandatory topic for core function where missing topic must block deploy | `true` |

Do not choose `false` just to hide deployment bugs. Also do not enable `true` mechanically if the architecture intentionally allows topics to be created after startup.

## 9. Other related configurations

`missingTopicsFatal` is only one piece of listener container configuration. Understand neighboring properties so functions are not misattributed.

| Property/mechanism | Role |
|---|---|
| `autoStartup` | Decides whether the listener container auto-starts with lifecycle |
| `missingTopicsFatal` | Decides whether the container fails if declared topics are missing during startup check |
| `topics` / `topicPattern` | Selects explicit topics or regex-matched topics |
| `KafkaAdmin` / `NewTopic` | Provisions topics from the application when configured |
| `auto.create.topics.enable` | Allows brokers to auto-create topics per broker policy |
| `ConsumerFactory` | Creates Kafka consumers with bootstrap, security, and consumer properties |
| `group.id` | Identifies the consumer group |
| startup timeout / API timeout | Affects how long metadata/admin operations can wait |
| readiness/liveness probes | Reflect application/container health per deployment policy |

`autoStartup=false` does not mean topics are skipped forever; when the container is started manually, the startup check can run at that time. `KafkaAdmin` creating topics is not an effect of `missingTopicsFatal`. Readiness probes also need dedicated design to distinguish a running app process from a listener actually assigned partitions and processing records.

## 10. Example design with two listener groups

An application might have a mandatory `orders.created` topic and dynamically created per-tenant `tenant-events` topics. The two listeners may need different policies.

Factory for mandatory topic:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
requiredTopicFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setMissingTopicsFatal(true);
    return factory;
}
~~~

Factory for topics that may appear later:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, TenantEvent>
dynamicTopicFactory(
        ConsumerFactory<String, TenantEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, TenantEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setMissingTopicsFatal(false);
    return factory;
}
~~~

Listeners using their corresponding factories:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "requiredTopicFactory"
)
public void handleOrder(OrderCreated event) {
    orderService.handle(event);
}

@KafkaListener(
    topicPattern = "tenant-events\\..*",
    containerFactory = "dynamicTopicFactory"
)
public void handleTenantEvent(TenantEvent event) {
    tenantService.handle(event);
}
~~~

This example illustrates separating policies at the factory level. With `topicPattern`, verify subscription and startup check behavior in your specific Spring Kafka version. If the application needs to confirm a tenant topic exists before handling a tenant, add a per-tenant check rather than relying on a global flag.

## 11. Checking topics before the listener starts

For systems with strict readiness requirements, `AdminClient` can be used to verify topics and topology before allowing listeners to start.

Example checking topic existence:

~~~java
public boolean topicExists(Admin admin, String topic) throws Exception {
    return admin.listTopics()
            .names()
            .get(10, TimeUnit.SECONDS)
            .contains(topic);
}
~~~

The snippet above is a simple illustration. In production, handle timeouts, authorization, unavailable clusters, and large topic lists. If only checking a specific topic, use the `describeTopics` API appropriate for your Kafka client version and distinguish `TopicDoesNotExistException` from connection/permission errors.

To check partition count:

~~~java
TopicDescription description = admin.describeTopics(
        List.of("orders.created")
    ).allTopicNames()
     .get(10, TimeUnit.SECONDS)
     .get("orders.created");

int partitionCount = description.partitions().size();
~~~

Checking replication factor can inspect each partition's replica list in `TopicDescription`. If policy requires the same replication factor on every partition, check all partitions rather than just the first partition.

Do not treat an `AdminClient` preflight as a one-time check that guarantees state will never change. Topics can be deleted or altered after the check. Preflight is a pre-startup gate; monitoring must still detect runtime changes.

## 12. Investigation procedure when a listener fails to start

When a container fails to start and logs mention missing topics, investigate in order:

### Step 1: Identify listener and factory

- Which listener failed to start?
- Does the annotation use `topics` or `topicPattern`?
- Which `containerFactory` is the listener using?
- Is `missingTopicsFatal` set directly on the factory?
- Is a Boot property overridden by Java configuration?

### Step 2: Confirm topic name and cluster

- Are the topic spelling, dots, and naming convention exact?
- Do bootstrap servers point to the right environment?
- Does the topic exist on the cluster the consumer connects to?
- Was the topic just created while metadata has not refreshed yet?

### Step 3: Check permissions and connectivity

- Does the principal have describe/consume permissions on the topic and required group permissions?
- Are TLS/SASL configured properly?
- Are brokers reachable and do partitions have leaders?
- Do logs show timeouts or authentication failures rather than nonexistent topics?

### Step 4: Check provisioning

- Did the topic-creation pipeline succeed?
- Is `KafkaAdmin` configured and authorized to create topics?
- Was the `NewTopic` bean loaded into the application context?
- Does the topic have the right partition count, replication, and config?

### Step 5: Choose the appropriate response

- If the topic is mandatory and missing is a deploy bug, keep `missingTopicsFatal=true` and fix provisioning.
- If the topic is intentionally created post-startup by design, consider `false` and add monitoring.
- If the error is broker/auth/ACL, fix the corresponding dependency; do not flip flags to hide errors.
- If the topic exists with wrong topology, add dedicated readiness checks.

### Step 6: Verify listener operation

After the container starts, confirm the consumer group has members, partitions are assigned, the listener receives test records, and committed offsets advance. Container started state alone is not enough to prove the consumer is reading data.

## 13. Post-startup monitoring

Because `missingTopicsFatal` does not monitor continuously, production needs to track runtime signals:

- Listener container running/stopped state.
- Consumer group member count and partition assignments.
- Consumer lag and age of oldest unprocessed record.
- Metadata, topic authorization, fetch, and commit errors.
- Container restart counts or start failures.
- Topic/partition state and under-replicated partitions.
- Time from deployment until the consumer receives its first record.

If a topic is deleted post-startup, the consumer may stop receiving data or encounter errors when metadata refreshes. Alert when listeners unexpectedly lack assignments, group lag rises, or consumers make no progress beyond SLO windows.

Readiness probes can check listener container state and assignments if the application has actuator/custom health indicators. Do not use a simple check that the Spring context is running to conclude consumers are ready to process.

## 14. Common configuration mistakes

| Practice | Consequence | Fix |
|---|---|---|
| Thinking `missingTopicsFatal` creates topics | Topics remain missing or get created with unsuitable defaults | Provision via `KafkaAdmin`/`NewTopic` or IaC |
| Setting `false` to mask misspelled topic names | App starts but listener never receives expected data | Verify topic names and add alerts for consumer assignment |
| Setting `true` for dynamic topics | Startup may fail before topics are created as designed | Use appropriate policy or dedicated preflight |
| Checking only topic existence | Misses partition count, replication, retention, or ACLs | Add topology and permission checks |
| Confusing broker unavailable with missing topic | Changing flag leaves connection error unresolved | Read root exception and check network/metadata |
| Assuming the flag monitors at runtime | Fails to detect topics deleted post-startup | Monitor containers, groups, metadata, and lag |
| Configuring Boot while listener uses another factory | Value does not apply to the listener being controlled | Inspect effective `containerFactory` and `ContainerProperties` |
| Relying on auto-create in production | Topics may get wrong partition/replication/config | Disable or control auto-create and provision explicitly |

## 15. Design checklist

Before choosing `missingTopicsFatal`, answer:

1. Is the listener's topic a mandatory dependency or can it appear after startup?
2. Does the listener declare explicit `topics` or a `topicPattern`?
3. Which factory does the actual container use and what is its `missingTopicsFatal` value?
4. What are the defaults and property bindings in your Spring Kafka/Spring Boot version?
5. Are topics created by IaC, `KafkaAdmin`/`NewTopic`, or broker auto-create?
6. Does provisioning finish before the listener starts?
7. Does the application need to verify partition counts, replication factor, retention, or ACLs?
8. If brokers are temporarily unavailable, do logs distinguish connection errors from missing topics?
9. When set to `false`, does monitoring detect consumers with no assignment or no progress?
10. If a topic is deleted post-startup, who detects it and what is the recovery runbook?

`missingTopicsFatal` is a startup policy switch for listener containers. Enabling `true` fits when topics must exist before the application takes traffic and missing topics should block deployment. Leaving `false` fits when topics can appear later or subscriptions are dynamic, provided the application has strong runtime observability. Regardless of the value chosen, topics still must be properly provisioned and monitored for partitions, replication, access permissions, and operational health.
