# Actual Number of Consumers Created

In Spring Kafka, a listener does not necessarily correspond to a single Kafka consumer. When concurrency is enabled, the listener container creates multiple consumer workers to read in parallel. When the application runs multiple replicas, the consumer count scales further with each replica. Therefore, to know how many consumers the system actually creates, you must calculate from the number of listener containers, concurrency, and application instance count.

A common point of confusion is that **created consumer**, **member that has joined the consumer group**, and **consumer assigned partitions** are three different states. Spring may have created a consumer that has not yet joined the group; a joined member may still have no partitions assigned if the number of members exceeds the number of eligible partitions. Counting these three layers accurately helps avoid over-scaling and correctly diagnose why some consumers receive no records.

This lesson belongs to the **Concurrency and Scaling** chapter of the **SPRING_KAFKA_MESSAGING** module, focusing on how Spring Kafka creates consumers from listener concurrency, how to calculate counts across multiple replicas and listeners, and how to observe actual assignments in a Kafka consumer group.

## Learning Outcomes

After this lesson, you can:

- Explain the relationship between @KafkaListener, listener containers, concurrency, and KafkaConsumer.
- Calculate the number of consumers created within a single JVM and across an entire deployment.
- Calculate separately the number of consumers belonging to each group.id.
- Distinguish between instantiated consumer instances, registered group members, and members with partition assignments.
- Configure concurrency using Spring Boot, container factories, and @KafkaListener.
- Understand the impact of multiple listeners and multiple replicas.
- Inspect child containers in Spring and group members in Kafka.
- Explain why increasing concurrency does not automatically increase partition count or throughput.
- Identify which configurations create idle consumers or increase operational overhead.

## 1. How Does a @KafkaListener Create Consumers?

Spring Kafka does not invoke a @KafkaListener method directly using a single shared KafkaConsumer for the whole application. When the application starts, Spring creates a listener endpoint and a listener container to manage the consumer lifecycle.

With concurrency greater than one, Spring Kafka uses ConcurrentMessageListenerContainer. This container creates child KafkaMessageListenerContainer instances; each child container manages its own Kafka consumer and poll loop.

~~~mermaid
flowchart TD
    A["@KafkaListener"] --> B["Listener endpoint"]
    B --> C["ConcurrentMessageListenerContainer"]
    C --> D1["KafkaMessageListenerContainer 1"]
    C --> D2["KafkaMessageListenerContainer 2"]
    C --> D3["KafkaMessageListenerContainer 3"]
    D1 --> K1["KafkaConsumer 1"]
    D2 --> K2["KafkaConsumer 2"]
    D3 --> K3["KafkaConsumer 3"]
    K1 --> G["Consumer group"]
    K2 --> G
    K3 --> G
~~~

Example of a listener with concurrency of three:

~~~java
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-fulfillment",
        concurrency = "3"
)
public void consume(OrderCreatedEvent event) {
    orderService.handle(event);
}
~~~

Once the container starts successfully, this listener has three consumer workers in the same JVM. Each worker has its own KafkaConsumer and can be registered by the Kafka group coordinator as a member of the orders-fulfillment group.

Concurrency is the number of consumer workers the container is configured to create. It is not the number of listener method invocations, the number of records in one poll, or the number of topic partitions.

## 2. Three Numbers to Distinguish

When asking “how many consumers are there”, you must clarify which layer is being counted:

| Concept | Meaning | Where to Observe |
|---|---|---|
| Created consumer (instantiated) | KafkaConsumer instantiated by the listener container inside the application | Spring listener containers and startup logs |
| Group member | Consumer that has joined the consumer group and is recognized by the coordinator | Kafka AdminClient or group administration tools |
| Consumer assigned partitions | Group member currently owning at least one partition under the current assignment | Group assignment |

The three numbers can differ over a period of time:

- A container that has not started or is stopping may not have active consumers yet.
- A newly started consumer may not have completed joining the group yet.
- A member that has joined the group may receive no partitions because the number of members exceeds assignable partitions.
- During a rebalance, assignments may be temporarily unstable.

A member without partitions can still be a valid group member and maintain its membership. It is not currently processing records from the subscription's partitions under the current assignment, but that does not mean the consumer object has not been created.

## 3. Formula for Consumers by Replica and Concurrency

For an identical listener container running across multiple replicas:

~~~text
N_{created} = R \times C
~~~

Where:

- (R): number of replicas running the listener.
- (C): concurrency of the listener container per replica.
- (N_{created}): expected number of consumer workers created once all containers have started stably.

Examples:

| Replicas | Concurrency per replica | Expected consumer workers |
|---:|---:|---:|
| 1 | 1 | 1 |
| 1 | 3 | 3 |
| 2 | 3 | 6 |
| 4 | 3 | 12 |
| 5 | 4 | 20 |

If a deployment has three pods and listener concurrency is four, the total number of consumer workers for that listener is 12, not four.

The formula above calculates a single listener container. If the application has multiple listener containers, you must sum the consumers of each container:

~~~text
N_{created,total} = sum_{j=1}^{L} (R_j \times C_j)
~~~

Where (L) is the number of listener/container types being counted, (R_j) is the number of replicas running container j, and (C_j) is that container's concurrency.

If listeners use different group IDs, they belong to separate consumer groups. If they share the same group ID, members of those listeners join the same group and partition distribution depends on subscriptions and the assignor. When counting per group, only sum containers that share the same group ID and connect to the same cluster.

Consumers created manually with KafkaConsumer outside listener containers must also be counted separately.

## 4. Example of an Application with Multiple Listeners

Suppose an application has two listeners:

- fulfillment listener concurrency 3, group orders-fulfillment.
- audit listener concurrency 2, group orders-audit.

The application runs four replicas. Each replica creates:

| Listener | Group ID | Concurrency | Consumers per replica |
|---|---|---:|---:|
| Fulfillment | orders-fulfillment | 3 | 3 |
| Audit | orders-audit | 2 | 2 |
| Total | Two separate groups | 5 | 5 |

Across four replicas:

- Group orders-fulfillment has up to 12 consumer members from these listeners.
- Group orders-audit has up to 8 consumer members.
- The entire application creates an expected 20 consumer workers.

Do not add 12 and 8 into a single group of 20 members. These are two independent groups with separate offsets and partition assignments.

Code example:

~~~java
@Component
public class OrderListeners {

    @KafkaListener(
            topics = "orders.created",
            groupId = "orders-fulfillment",
            concurrency = "3"
    )
    public void fulfill(OrderCreatedEvent event) {
        fulfillmentService.handle(event);
    }

    @KafkaListener(
            topics = "orders.created",
            groupId = "orders-audit",
            concurrency = "2"
    )
    public void audit(OrderCreatedEvent event) {
        auditService.record(event);
    }
}
~~~

Each @KafkaListener method creates a separate listener endpoint/container. Concurrency of one listener is not automatically shared with or summed onto the other, even when they reside in the same Java class.

## 5. Configuring Concurrency with Spring Boot

With the listener container factory auto-configured by Spring Boot, you can set a default concurrency:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: orders-fulfillment
      enable-auto-commit: false
    listener:
      concurrency: 3
~~~

This value is applied as the default concurrency for listener containers created from the auto-configured factory, unless overridden by the listener or a specific factory configuration.

This setting does not mean the entire application creates only three consumers. If the application has multiple listener endpoints using that factory, each endpoint can create consumers according to its concurrency.

Check which listeners use the default factory and which specify a separate containerFactory.

## 6. Configuring Concurrency in ConcurrentKafkaListenerContainerFactory

When you need control per group of listeners, you can create a separate factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
fulfillmentKafkaListenerFactory(
        ConsumerFactory<String, OrderCreatedEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    return factory;
}
~~~

Using the factory:

~~~java
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-fulfillment",
        containerFactory = "fulfillmentKafkaListenerFactory"
)
public void fulfill(OrderCreatedEvent event) {
    fulfillmentService.handle(event);
}
~~~

Here the factory sets concurrency to three. Listeners using this factory receive that setting if they do not specify their own endpoint concurrency attribute.

If you have both Spring Boot defaults, a custom factory, and a concurrency attribute on @KafkaListener, clearly identify which factory each listener uses and the final effective value. Avoid adding configuration values together: they are sources that set a container's concurrency, not additive consumer counts.

## 7. Overriding Concurrency on @KafkaListener

Spring Kafka allows declaring concurrency directly on @KafkaListener:

~~~java
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-fulfillment",
        containerFactory = "fulfillmentKafkaListenerFactory",
        concurrency = "5"
)
public void fulfill(OrderCreatedEvent event) {
    fulfillmentService.handle(event);
}
~~~

If the endpoint sets concurrency to five, this endpoint's container uses five instead of the factory's default concurrency. The annotation attribute can use configuration placeholders to vary by environment:

~~~java
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-fulfillment",
        concurrency = "${app.kafka.fulfillment.concurrency:3}"
)
public void fulfill(OrderCreatedEvent event) {
    fulfillmentService.handle(event);
}
~~~

In this example, the default value is three if app.kafka.fulfillment.concurrency is not declared. When running across multiple replicas, each replica creates workers according to the effective concurrency value.

Centralize concurrency in environment-based or factory-based configuration for easier operations. Scattering values across many annotations makes calculating total consumers and adjusting load harder.

## 8. Partition Count Limits Assigned Consumers, Not Created Consumers

Suppose topic orders.created has four partitions, the application runs three replicas, and each replica has concurrency set to three.

Expected number of created consumer workers:

~~~text
3 \times 3 = 9
~~~

However, with a four-partition topic and all members subscribing to that topic, at most four members can be assigned partitions at a time. The remaining members can remain in the group without partition assignments.

~~~mermaid
flowchart TB
    subgraph Apps["3 application replicas"]
        A1["Replica 1: 3 consumers"]
        A2["Replica 2: 3 consumers"]
        A3["Replica 3: 3 consumers"]
    end
    subgraph Topic["orders.created: 4 partitions"]
        P0["Partition 0"]
        P1["Partition 1"]
        P2["Partition 2"]
        P3["Partition 3"]
    end
    A1 --> P0
    A2 --> P1
    A3 --> P2
    A1 --> P3
    A2 -.-> I["5 members may have no assignment"]
    A3 -.-> I
~~~

The diagram only illustrates the limit on assigned members; specific partitions are distributed according to the assignor and actual group membership.

Key points:

- Partition count does not prevent Spring from creating more consumer workers.
- Excess consumers still incur thread, connection, heartbeat, and group management overhead.
- Increasing concurrency beyond the partition count generally does not increase read parallelism for that topic.
- If a group subscribes to multiple topics, consider the total partitions matching the subscription and assignment strategy, not just the partition count of one topic.

With complex subscriptions or multiple topics, not every member is guaranteed a partition simply because total partition count exceeds member count. The outcome also depends on the assignor and how members subscribe.

## 9. Explicit Partition Assignment Cases

When @KafkaListener uses @TopicPartition to assign specific partitions, Spring Kafka distributes the declared TopicPartitions across the child containers.

Example:

~~~java
@KafkaListener(
        groupId = "orders-fixed-assignment",
        topicPartitions = {
                @TopicPartition(topic = "orders.created", partitions = {"0", "1", "2"})
        },
        concurrency = "5"
)
public void consume(OrderCreatedEvent event) {
    orderService.handle(event);
}
~~~

There are three specified partitions while concurrency is declared as five. With explicit partition assignment, Spring Kafka adjusts the number of child containers down to match the number of specified partitions when concurrency exceeds the distributable partitions. Therefore, this case does not necessarily create all five consumers.

This is an important distinction between topic subscription and explicit partition assignment. Check startup logs and actual child container count when using @TopicPartition.

When there are multiple TopicPartitionOffsets, Spring Kafka distributes them across the child containers. Each partition is still managed by only one consumer in the corresponding container assignment at a time.

## 10. Counting Consumers Across Multiple Group IDs

An application can have multiple listeners with different group IDs. Each group maintains separate membership and offsets, even if the listeners read the same topic.

For example, one replica has:

- Listener A: group orders-fulfillment, concurrency 3.
- Listener B: group orders-analytics, concurrency 2.
- Listener C: group orders-audit, concurrency 1.

The total consumer workers in the JVM is six, split across three groups:

| Group ID | Consumers per replica | 3 replicas |
|---|---:|---:|
| orders-fulfillment | 3 | 9 |
| orders-analytics | 2 | 6 |
| orders-audit | 1 | 3 |
| Application total | 6 | 18 |

Do not use the total of 18 to infer that 18 consumers are competing for partitions in one group. Each group receives the full stream according to its own offsets and has independent assignments.

Conversely, if multiple listeners share the same group ID and subscribe to the same topic, members from all those listeners can share partitions. Check the effective groupId on each endpoint rather than only looking at the default group-id in application.yml.

## 11. Observing Child Container Count in Spring

You can use KafkaListenerEndpointRegistry to inspect managed listener containers. For ConcurrentMessageListenerContainer, you can read concurrency and child container count.

Illustrative example:

~~~java
@Component
public class ListenerContainerInspector {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerContainerInspector(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void logContainerCounts() {
        for (MessageListenerContainer container :
                registry.getListenerContainers()) {

            if (container instanceof
                    ConcurrentMessageListenerContainer<?, ?> concurrent) {

                log.info(
                        "Listener container concurrency={}, childContainers={}",
                        concurrent.getConcurrency(),
                        concurrent.getContainers().size()
                );
            }
        }
    }
}
~~~

getConcurrency() reports the container's concurrency; getContainers().size() reports how many child KafkaMessageListenerContainers currently exist. Comparing these two values helps detect containers that have not created as many workers as configured.

This is a Spring-side metric. It does not prove every consumer has joined the group or received a partition assignment. To verify Kafka-side state, inspect group membership and assignments.

If the application has multiple container factories or manually created listeners, iterate over all managed containers and tally by their respective listener ID/group ID. Avoid logging only one factory and treating it as the application's total consumers.

## 12. Observing Group Members and Partition Assignments with AdminClient

Kafka AdminClient can describe consumer groups. The result shows the members recognized by the coordinator and the partitions assigned to each member.

Example:

~~~java
Map<String, ConsumerGroupDescription> groups =
        adminClient.describeConsumerGroups(
                List.of("orders-fulfillment")
        ).all().get(10, TimeUnit.SECONDS);

ConsumerGroupDescription group =
        groups.get("orders-fulfillment");

log.info(
        "Group={}, state={}, members={}",
        group.groupId(),
        group.state(),
        group.members().size()
);

for (MemberDescription member : group.members()) {
    log.info(
            "memberId={}, clientId={}, host={}, assignedPartitions={}",
            member.consumerId(),
            member.clientId(),
            member.host(),
            member.assignment().topicPartitions()
    );
}
~~~

This example helps distinguish:

- Total members that have joined the group.
- Client ID and host of each member.
- Partitions assigned to each member.
- Members with an empty assignment.

AdminClient APIs may vary slightly by Kafka client version; use the dependency version present in your project. When a group is rebalancing, observed results can change rapidly; sample after the group stabilizes and use reasonable timeouts.

When reconciling with Spring's created consumer count, account for startup timing, connection errors, authentication, group join, and stopping containers.

## 13. Calculating Consumers for Kubernetes Deployments

In Kubernetes, replica count often changes via Deployment configuration or HorizontalPodAutoscaler. If each pod has a fixed listener container concurrency, the consumer count changes with the number of running pods.

Example:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-fulfillment
spec:
  replicas: 4
  template:
    spec:
      containers:
        - name: app
          image: example/orders-fulfillment:1.0
          env:
            - name: SPRING_KAFKA_LISTENER_CONCURRENCY
              value: "3"
~~~

With four pods and concurrency of three, the deployment is expected to create 12 consumer workers for listeners using this configuration.

If HPA scales replicas from four to six, expected workers increase from 12 to 18. Kafka will rebalance the group to distribute partitions across the new membership.

Remember:

- Pods in Pending state or whose application has not started have not created listener consumers yet.
- Terminating pods may still have consumers shutting down.
- Rolling deployments can temporarily push pods and consumers above the desired replica count under a maxSurge strategy.
- Aggressive HPA scaling can cause frequent rebalances.
- Adding consumers does not help if partitions or downstream are already at their limit.

When calculating capacity, use the number of pods actually running the listener and effective concurrency, not just the declared replicas in the manifest.

## 14. Calculating Concurrency with Multiple Listeners and Replicas

A clear configuration table helps predict consumer counts before deployment.

Suppose a deployment has three replicas and these listeners:

| Listener | Group ID | Concurrency/pod | Consumers across deployment |
|---|---|---:|---:|
| Fulfillment | orders-fulfillment | 4 | 12 |
| Notification | orders-notification | 2 | 6 |
| Audit | orders-audit | 1 | 3 |
| Total | 3 groups | 7 | 21 |

If fulfillment concurrency increases from four to six, total consumers across the deployment increase by six, from 21 to 27. Only group orders-fulfillment gains members; the other two groups remain unchanged.

Useful formula:

[
N_{group} = sum_{j \in group} R_j \times C_j
]

Only sum listener containers sharing the same group ID on the same Kafka cluster. If a container is deployed on different replicas with different concurrency values, use the actual replica count and concurrency of each deployment group.

Do not add partition count into the created-consumer formula. Partition count is used to evaluate assignment capacity and read parallelism, not to determine how many consumer objects Spring instantiates.

## 15. Reasons Actual Consumer Count Differs from Expected

| Cause | Symptom | How to Check |
|---|---|---|
| Container not started | Spring has not created enough consumers yet | Check lifecycle and listener container status. |
| Listener uses a different factory | Concurrency differs from Boot configuration | Check containerFactory on @KafkaListener. |
| Annotation override | Concurrency value differs from factory | Check concurrency on the endpoint. |
| Explicit partition assignment | Spring may lower concurrency to match declared partitions | Check @TopicPartition and child container count. |
| Replicas not ready | Total workers lower than declared replicas | Check pod readiness and application logs. |
| Consumer connection/auth errors | Workers fail to join group | Check exceptions, broker address, TLS/SASL, and ACLs. |
| Rebalance in progress | Members/assignments change temporarily | Observe group state and rebalance logs. |
| Multiple group IDs | Consumers split across separate groups | Check effective group ID per listener. |
| Shutdown/rolling update | Consumers leaving group or being recreated | Check lifecycle and rollout events. |

If consumer member count is lower than expected workers, verify containers have started and consumers can join the broker before increasing concurrency further.

If member count is right but assigned member count is low, check partition count, subscriptions, assignor, and explicit assignments. These are two different classes of problems.

## 16. Impact of Excess Consumers on Resources and Throughput

Excess consumers are not just a number on a dashboard. Each consumer worker can add:

- A KafkaConsumer and internal buffer structures.
- A poll/listener processing thread.
- Network connections to brokers and the group coordinator.
- Heartbeats and fetch/commit requests.
- Heap, CPU, and metrics resources.
- Group coordination and rebalance overhead when membership changes.

If there are 24 consumer members but the topic only has six partitions in the group, at most six members can receive partitions of that topic when all members share the subscription. The remaining members still incur overhead without increasing parallel read capacity.

Too many consumers can increase rebalance frequency during autoscaling or rolling deployments, increase broker connections, and put pressure on group management.

On the other hand, concurrency that is too low can leave partitions underutilized when each consumer processes slowly. The goal is to choose a consumer count aligned with partitions, resources, and target throughput, not to maximize worker count.

## 17. Workflow for Choosing the Right Consumer Count

You can determine concurrency using these steps:

1. List all listener endpoints and group IDs.
2. Determine the actual replica count of each deployment.
3. Determine the effective concurrency of each listener container.
4. Calculate total consumer workers per group.
5. Compare against partition count and subscription of each group.
6. Measure lag, throughput, processing latency, and downstream capacity.
7. Increase concurrency or replicas when unexploited partitions remain and resources allow.
8. If members already exceed partitions, prioritize optimizing processing or evaluating partition expansion instead of adding more consumers.
9. Check the impact on databases, connection pools, downstream APIs, and brokers.
10. Monitor group membership and rebalances after every change.
11. Document effective configurations so future scaling can be calculated consistently.

Do not mechanically set concurrency equal to CPU core count. Consumers may be bottlenecked by partition count, I/O, databases, or downstream services before CPU is saturated.

## 18. Comprehensive Exercise: Calculating Consumers for an Order System

A Spring Kafka system has three deployments:

- Fulfillment: three replicas, concurrency four, group orders-fulfillment.
- Notification: two replicas, concurrency two, group orders-notification.
- Audit: four replicas, concurrency one, group orders-audit.

Requirements:

1. Calculate consumer workers for each deployment.
2. Calculate total consumers across the system.
3. Calculate expected members for each group.
4. State how many members of the fulfillment group can at most have partitions if orders.created has six partitions and all subscribe to the topic.
5. Increase fulfillment to concurrency six and recalculate member count.
6. Run two listeners with the same group ID and verify they share assignments within the group.
7. Switch one listener to a separate group ID and observe independent offsets.
8. Use KafkaListenerEndpointRegistry to inspect concurrency and child container count.
9. Use AdminClient to inspect members, client IDs, and partition assignments.
10. Scale a deployment from three to five replicas and observe the rebalance.
11. Check consumer counts during a rolling update.
12. Propose a final configuration based on partitions, lag, and downstream capacity.

Results should include a table with deployment, listener, group ID, replicas, concurrency, expected consumers, observed members, and members with partition assignments. Record the measurement timestamp since group membership can change during rollouts or rebalances.

## 19. Learning Sequence and Completion Criteria

| Stage | Core Content | Self-Check Criterion |
|---|---|---|
| 1. Container model | @KafkaListener and listener containers | Explain how child containers manage KafkaConsumer. |
| 2. Concurrency | One container creates multiple consumer workers | Calculate consumers within a single JVM. |
| 3. Replicas | Multiple pods/instances | Calculate total consumers across a deployment. |
| 4. Multiple listeners | Multiple endpoints and group IDs | Sum consumers accurately per group. |
| 5. Configuration | Boot, factory, and annotation | Determine effective concurrency accurately. |
| 6. Assignment | Members and partitions | Distinguish created consumers from assigned consumers. |
| 7. Runtime inspection | Registry and AdminClient | Reconcile worker count with actual group members. |
| 8. Scaling | Partitions, lag, and downstream | Choose concurrency based on metrics and limits. |
| 9. Operations | Kubernetes rollout and rebalance | Predict consumer fluctuations when scaling. |

The lesson is complete when you can calculate the number of consumers created by Spring Kafka from replica count and each listener's concurrency, separate consumer counts accurately by group ID, and verify group members alongside partition assignments at runtime.

The actual number of consumers is not just the concurrency value in one annotation. It is the product of listener containers, effective concurrency, and running instances. After calculating worker count, check group membership and partition assignments separately to know how many consumers can genuinely receive data and add throughput.

