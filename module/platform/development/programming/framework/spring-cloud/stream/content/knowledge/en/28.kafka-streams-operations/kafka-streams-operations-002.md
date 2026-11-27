# Thread Count, Tasks, Standby Replicas, and Scaling Scope

Kafka Streams processes data in parallel by dividing a topology into **tasks** tied to input topic partitions, and then executing those tasks on **stream threads** within each Kafka Streams instance. In the Spring Cloud Stream Kafka Streams Binder, the number of threads per instance can be configured with `num.stream.threads`. For topologies with state stores, Kafka Streams also supports **standby task replicas** to maintain state copies on other instances; the number of backup replicas is configured with `num.standby.replicas`.

Three numbers must be distinguished: the number of topic partitions, the number of stream threads per instance, and the number of application instances. Partitions determine the maximum parallelism of the topology; threads provide execution capacity within a process; instances add machine resources and task distribution capability. Standby replicas improve state recovery when an instance fails, but do not increase the number of active tasks processing input.

This lesson belongs to the **Kafka Streams Operations** chapter of the `SPRING_CLOUD_STREAM` module. It focuses on functional topologies, the Kafka Streams task/thread model, state stores, changelogs, `num.stream.threads`, `num.standby.replicas`, horizontal/vertical scaling, partition limits, recovery, and production monitoring.

## 1. Distinguishing Partitions, Tasks, Threads, and Instances

These concepts are directly related but are not interchangeable:

| Component | Role | Scope |
|---|---|---|
| Topic partition | Ordered segment of data in a Kafka topic | Broker/topic |
| Kafka Streams task | Unit of topology processing bound to input partitions of a subtopology | Topology/application |
| Stream thread | Execution thread running tasks assigned to it by Kafka Streams | One Kafka Streams instance |
| Kafka Streams instance | A Kafka Streams process/client participating in the same application ID | One application replica |
| Standby task | A state copy of a task, updated from the changelog so it can take over | A different instance from the active task |

```text
Kafka topic: orders.events (6 partitions)
       |
       v
Topology: aggregateOrders
       |
       +--> Task 0 ----+
       +--> Task 1     |
       +--> Task 2     +--> Stream threads across instances
       +--> Task 3     |
       +--> Task 4     |
       +--> Task 5 ----+
```

One task can be executed on one stream thread at a time. One stream thread can process multiple tasks as scheduled by Kafka Streams. Therefore, six tasks do not strictly require six threads; three threads can handle six tasks, with each thread handling multiple tasks. Conversely, creating more threads than active tasks can leave some threads without any tasks to run.

A task is also not a Java thread manually created inside function code. Kafka Streams manages task creation, task assignment to instances/threads, pausing, and task migration during rebalances.

## 2. Tasks Are Created from Input Topic Partitions

Kafka Streams divides a topology into subtopologies. For a simple source subtopology, each partition of the input topic produces a corresponding task. The task reads that partition and runs the processors within the subtopology.

Example of a topic with six partitions:

```text
orders.events
  P0  P1  P2  P3  P4  P5
   |   |   |   |   |   |
   v   v   v   v   v   v
  T0  T1  T2  T3  T4  T5
```

In this example, there are six tasks for the subtopology. The actual number of tasks for a complex topology also depends on the subtopology structure, the partition counts of the input topics, and repartition topics created by key-changing, join, or grouping operations.

When a topology combines multiple input topics, topics participating in joins or co-partitioned operations must have compatible partition counts and partitioning strategies. A single task can read corresponding partitions from multiple topics. Do not simply add up the partition counts of all input topics to infer the total number of tasks in the topology.

For a topology with multiple subtopologies, each subtopology has its own set of tasks. Repartition topics can create new boundaries and change the number of tasks in downstream parts of the topology. Review the topology description and actual task information when capacity planning.

## 3. Partitions Set the Ceiling on Parallelism

For a subtopology, the partition count of the input/repartition topics is the factor that determines how many tasks can run in parallel. Increasing the number of replicas or stream threads cannot create new partition tasks if the topology has no additional partitions.

Example:

| Input Partitions | Instances | Stream Threads/Instance | Total Threads | Notes |
|---:|---:|---:|---:|---|
| 4 | 1 | 4 | 4 | At most 4 active tasks; can utilize all 4 threads |
| 4 | 2 | 2 | 4 | Can distribute 4 active tasks across 2 instances |
| 4 | 4 | 2 | 8 | Only 4 active tasks; some threads/instances may receive no tasks |
| 12 | 3 | 2 | 6 | Can run up to 6 tasks concurrently on the 6 available threads; remaining tasks await execution scheduling |
| 12 | 6 | 2 | 12 | Has all 12 threads available to run 12 active tasks if resources and assignment allow |

These rows are illustrative capacity models; actual task distribution depends on the topology, Kafka Streams assignment, live instance count, and per-machine resources.

If higher throughput is needed but the partition count is too small, revisit topic/partition design, key distribution, and co-partitioning capabilities. Do not simply add replicas and expect throughput to scale linearly.

## 4. What Does a Stream Thread Do?

A stream thread is a processing thread managed by Kafka Streams. It polls records from assigned partitions, routes records through the processor topology, updates state stores, handles punctuation, and participates in commits/transactions according to configuration.

A Kafka Streams instance can run multiple stream threads. The `num.stream.threads` property sets the number of processing threads per instance. Kafka Streams' default value is one stream thread unless configured otherwise.

Example of one instance running two stream threads:

```text
Kafka Streams instance A
  applicationId = order-aggregator-v1
  num.stream.threads = 2

  StreamThread-1: Task 0, Task 2, Task 4
  StreamThread-2: Task 1, Task 3, Task 5
```

The task list in the diagram is illustrative; Kafka Streams determines the actual assignment. A single thread can process multiple tasks and alternate among them.

Increasing `num.stream.threads` can utilize more CPU within the same process if there are enough tasks and resources. However, adding threads also increases CPU contention, context switching, memory usage, connections, and state store activity. Do not set a high thread count simply because a machine has many cores; measure CPU, latency, throughput, and task assignment.

## 5. Configuring `num.stream.threads` in the Kafka Streams Binder

The Kafka Streams Binder passes Kafka Streams client properties through the binder's `configuration` branch. Example:

```yaml
spring:
  cloud:
    function:
      definition: aggregateOrders
    stream:
      bindings:
        aggregateOrders-in-0:
          destination: orders.events
      kafka:
        streams:
          binder:
            applicationId: order-aggregator-v1
            configuration:
              num.stream.threads: 2
```

`num.stream.threads: 2` means each Kafka Streams instance creates two stream threads. If the application runs three replicas, the total configured stream thread count is six.

This is a Kafka Streams property, not `spring.cloud.stream.bindings.<binding>.consumer.concurrency` from the regular Kafka Binder. Do not confuse the listener container concurrency of the regular Kafka Binder with the stream thread count of Kafka Streams.

Place the configuration under the Kafka Streams Binder namespace. If an application uses both the regular Kafka Binder and the Kafka Streams Binder, identify which binder serves each binding; similarly named properties can have different scopes and semantics.

## 6. Vertical Scaling with Stream Threads

Vertical scaling means increasing an instance's resources, such as CPU and RAM, and then increasing `num.stream.threads` when the topology has enough tasks to take advantage of them.

Advantages:

- No need to increase the number of pods/VMs.
- Can utilize multiple cores on a single machine.
- Fewer instances to manage and potentially lower connection/coordination overhead.
- Useful when partition counts are moderate and the workload is CPU-heavy within a single process.

Limitations:

- A single instance remains a single fault domain; when the machine or process stops, all active tasks on that instance must be reassigned.
- The number of active tasks is still bounded by partitions/subtopologies.
- Adding threads does not increase partition counts or resolve hot partitions.
- A larger process may require more RAM, file descriptors, and local disk.

Vertical scaling is appropriate when measurements show CPU is the bottleneck, the task count is high enough, and the machine has available capacity. If the bottleneck is network, broker, database, or a hot key, adding stream threads may not help.

## 7. Horizontal Scaling with Application Replicas

Horizontal scaling means running multiple application instances participating in the same Kafka Streams application. Instances must share the same `applicationId` so Kafka Streams can coordinate task assignment.

Example deploying three replicas:

```text
Deployment: order-aggregator
applicationId: order-aggregator-v1

Replica A: 2 stream threads
Replica B: 2 stream threads
Replica C: 2 stream threads
```

With six partitions/tasks, six stream threads across three replicas can provide six active processing slots. When scaling out additional replicas, Kafka Streams rebalances tasks across instances. If the task count does not increase, extra instances may end up with no active tasks.

All replicas of the same topology must use the same application ID and compatible topology/configuration. Do not append a pod ID or replica ordinal to the application ID; doing so creates independent applications instead of sharing load within the same consumer group.

## 8. Combining Instance Count and Thread Count

The total configured stream threads can be calculated simply as:

\[
T_{configured} = N_{instances} \times T_{per-instance}
\]

Where:

- (N_{instances}) is the number of running Kafka Streams instances.
- (T_{per-instance}) is `num.stream.threads` per instance.

For example, four replicas with three stream threads each yield twelve stream threads in total. This does not mean the topology always runs twelve tasks in parallel. Available active tasks still depend on subtopology partitions and assignment.

When there are fewer tasks than threads, some threads have no tasks. When there are more tasks than threads, a single thread can manage multiple tasks. Evaluate task count, thread count, CPU, and thread state together to determine an effective configuration.

## 9. What Is a Standby Task Replica?

A stateful topology can maintain local state stores. When an instance owning an active task fails, another instance must restore state from the changelog topic before continuing processing. Restoration can take considerable time if state is large or changelog backlog is high.

Kafka Streams supports standby tasks: another instance maintains a state copy of the task by reading the changelog topic. A standby task does not process input records like an active task; it updates state so it is ready to be promoted when the active task fails or assignment changes.

```text
Input partitions
      |
      v
Active task on Replica A
      |
      +---- updates state store
      |
      +---- writes changelog topic
                    |
                    v
           Standby task on Replica B
           updates state copy

When Replica A fails:
  Replica B can take over the active task and continue after rebalance/promotion.
```

Standby tasks reduce the amount of state that must be restored from scratch during failover. They do not completely eliminate rebalances, catch-up, or other recovery steps. The time saved depends on how fresh the standby state is, changelog throughput, assignment, and the receiving instance's capacity.

## 10. Configuring `num.standby.replicas`

`num.standby.replicas` specifies the desired number of standby copies per stateful task. Example:

```yaml
spring:
  cloud:
    function:
      definition: aggregateOrders
    stream:
      bindings:
        aggregateOrders-in-0:
          destination: orders.events
      kafka:
        streams:
          binder:
            applicationId: order-aggregator-v1
            configuration:
              num.stream.threads: 2
              num.standby.replicas: 1
```

With `num.standby.replicas: 1`, Kafka Streams attempts to maintain one standby copy for each stateful task. This value does not mean a task has two active consumers or double throughput.

Standby replicas are allocated on Kafka Streams instances other than the instance running the active task. To have one independent standby, at least one other instance must be available to receive the standby task. To have two standby copies on different instances, enough distinct instances and appropriate resources are required. One process with multiple stream threads does not substitute for multiple independent instances for process/host fault tolerance.

Standby allocation also depends on the number of live instances, task assignment, and topology structure. If there are not enough instances, Kafka Streams cannot achieve the desired standby count.

## 11. Standby Replicas Are Only Useful for Stateful Processing

Standby tasks are meaningful when a topology has state to maintain, such as:

- `KTable` and materialized views.
- Aggregations such as count, sum, or reduce.
- Windowed aggregations.
- Joins requiring state stores.
- Processor API using state stores.

A stateless topology that only filters/maps records and has no state stores to recover generally gains no significant benefit from standby replicas. Setting a large `num.standby.replicas` for a stateless workload does not increase throughput.

State stores must have appropriate changelogging enabled so Kafka Streams can rebuild state. If logging is disabled for a store, re-evaluate restore and standby capabilities; do not assume standby state is maintained like a changelog-backed store.

## 12. Active Tasks and Standby Tasks Do Not Share Input Load

Active tasks read input partitions and run the topology. Standby tasks maintain state from the changelog but do not receive input partitions to perform the same business processing as an active copy.

| Criterion | Active task | Standby task |
|---|---|---|
| Reads input partitions | Yes | No, in standby role |
| Executes processor topology | Yes | Does not process business input like an active task |
| Updates state | Yes | Updates replica from changelog |
| Writes business output | Can | No |
| Purpose | Process data | Shorten recovery when an active task is lost |
| Throughput impact | Generates processing throughput | Improves availability, does not increase active throughput |

Therefore, if the application is slow due to insufficient processing capacity, inspect partitions, active tasks, stream threads, CPU, and downstream latency. Adding standby replicas is not a way to increase throughput.

## 13. Conditions for Standby to Work Effectively

For standby to assist state recovery:

- The topology must have state stores requiring recovery.
- State stores must have appropriate changelogs and changelog topics must be retained.
- Instances must have Kafka connectivity and permissions to read changelog/internal topics.
- Standby tasks must be assigned to a different instance from the active task.
- Standby instances need sufficient RAM, CPU, local disk, and network to maintain state.
- Changelogs must be updated fast enough so standby does not lag far behind.
- Application ID and topology configuration must remain consistent across replicas.

Standby state may still lag behind active state. When promoted, the instance receiving the task may need to catch up further from the changelog before resuming normal processing. Monitor lag/restore metrics rather than assuming standby is always instantaneously in sync.

## 14. Changelog Topics and Local State Stores

Kafka Streams state stores are typically persisted locally on the instance for fast access. Changelog topics record state changes for recovery or recreating state on another instance.

```text
Active processor
      |
      +--> Local state store (RocksDB/in-memory)
      |
      +--> Changelog topic on Kafka
                    |
                    +--> Standby state store on Replica B
                    |
                    +--> Restore state when a new instance takes over the task
```

The local state store serves fast processing; the changelog topic is the durable source for recovery under Kafka Streams semantics. Do not manually delete changelog topics or arbitrarily change the application ID while existing state is still needed.

The application's Kafka permissions must cover the appropriate internal topics: reading input, writing output, consumer group access, and reading/writing/creating changelog or repartition topics per cluster policy. Missing ACLs for changelogs can prevent standby updates or cause state restoration to fail.

## 15. Configuring the Local State Directory

Kafka Streams uses `state.dir` to store local state. Example:

```yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            configuration:
              state.dir: /var/lib/order-stream/state
              num.stream.threads: 2
              num.standby.replicas: 1
```

In container environments, the directory must exist or be creatable, have write permissions, and have sufficient disk space. Each instance needs its own state directory; do not let multiple replicas write to a shared directory on a network volume.

You can use local disk or dedicated volumes depending on your operational strategy. Local data speeds up restarts on the same instance if still valid, while cross-instance recovery still relies on Kafka changelogs and Kafka Streams mechanisms. Do not treat a local volume as a replacement for changelog topics.

## 16. Six-Partition Sizing Example

Suppose an order-aggregation topology reads the `orders.events` topic with six partitions and requires one standby replica per task.

```yaml
spring:
  cloud:
    function:
      definition: aggregateOrders
    stream:
      bindings:
        aggregateOrders-in-0:
          destination: orders.events
      kafka:
        streams:
          binder:
            applicationId: order-aggregator-v1
            configuration:
              num.stream.threads: 2
              num.standby.replicas: 1
              state.dir: /var/lib/order-stream/state
```

The deployment runs three replicas with the same configuration and same `applicationId`:

| Replica | Stream threads | Illustrative role |
|---|---:|---|
| A | 2 | Several active tasks and standby tasks of other tasks |
| B | 2 | Several active tasks and standby tasks of other tasks |
| C | 2 | Several active tasks and standby tasks of other tasks |

Six partitions create at most six active tasks for this simple subtopology. Six stream threads can process six active tasks if assignment and resources are appropriate. One standby replica per task requires state copies to be allocated on other instances; exact placement is decided by Kafka Streams.

If only one replica runs with two stream threads, the application can still process active tasks, but has no other instance to maintain an independent standby. Increasing `num.standby.replicas` while running only one instance does not provide cross-process failover.

## 17. Horizontal Scaling and Standby Example

Suppose an application initially runs two replicas with two stream threads each. After measuring load, the operations team scales to four replicas while keeping the same application ID:

```text
Before:
  Replica A: 2 threads
  Replica B: 2 threads

After:
  Replica A: 2 threads
  Replica B: 2 threads
  Replica C: 2 threads
  Replica D: 2 threads

All share applicationId = order-aggregator-v1
```

Kafka Streams rebalances active and standby tasks across instances. With more instances, tasks can be distributed better and standbys can be placed across different failure domains. However, if the topic has only two partitions, the topology does not have four active tasks to utilize eight stream threads.

When increasing replicas, ensure instances run the same topology version and compatible configuration. Rolling deployments can temporarily increase rebalances; set appropriate readiness/liveness probes and shutdown grace periods to minimize disruption.

## 18. How to Choose the Number of Stream Threads

There is no single right value for every workload. You can start with one or two threads per instance, then measure:

- Number of active tasks assigned per instance.
- Throughput in records/second and processing latency.
- CPU utilization and garbage collection.
- Record processing time and extent of blocking in user code.
- RocksDB/state store I/O and disk latency.
- Network throughput and changelog write/read rates.
- Stream thread states and frequency of thread error transitions.

If each thread has few tasks or the topic has few partitions, adding threads may yield no extra throughput. If handlers perform blocking I/O, review the processing design and Kafka Streams constraints; do not default to adding threads instead of removing blocking calls from the topology.

Benchmark with payload sizes, key distributions, state stores, and brokers representative of production. Use representative data to uncover hot keys, partition skew, and state restore costs.

## 19. How to Choose the Number of Standby Replicas

The `num.standby.replicas` value is a trade-off between recoverability and resource cost:

| Value | Meaning | Trade-off |
|---:|---|---|
| 0 | Do not maintain standby tasks | Fewer resources; failover requires restoring state from changelog |
| 1 | One standby copy per stateful task | Enables faster takeover when one instance fails; increases disk/network/CPU |
| 2 | Two standby copies per stateful task | Tolerates more instance failures under suitable assignment; higher cost |

Do not set standby replicas higher than fault-tolerance needs. Each copy must maintain state, read the changelog, and consume local disk. If state stores are large, standby overhead can be substantial.

To maintain one standby on another instance, at least two Kafka Streams instances must participate in the same application. To have two standby copies on two different instances, at least three suitable instances are required. This is a necessary condition for instance count; successful allocation still depends on assignment and topology constraints.

## 20. Standby Does Not Replace Kafka Broker Replication

Standby tasks and Kafka broker replication protect two different layers:

| Mechanism | What Does It Protect? | Scope |
|---|---|---|
| Kafka topic replication | Log/record copies across brokers | Kafka infrastructure |
| Kafka Streams standby task | State store copies on other application instances | Stream processing layer |
| Local state store | Local working state of a single instance | One machine/volume |

Standby tasks read the changelog topic; if the broker/changelog loses data, standby cannot reconstruct lost data on its own. Conversely, broker replication does not maintain a materialized state store ready to process on another application instance.

Production needs both proper replication/ISR for Kafka topics and an appropriate standby strategy for stateful applications. Protect input topics, output topics, and internal changelog/repartition topics according to data criticality.

## 21. Rebalancing During Scaling or Instance Failure

When instances join or leave the application, Kafka Streams re-coordinates task assignment. This process can pause tasks, switch active/standby roles, and restore state if the instance receiving a task lacks the latest state.

Common scenarios:

- Scale up: new instances join and tasks are redistributed; standby assignments may change.
- Scale down: tasks on stopped instances move to remaining instances; state may need to catch up.
- Process crash: tasks are reassigned after membership/session timeout and rebalance.
- Rolling deploy: multiple instances restart sequentially; shutdown configuration and grace periods affect disruption.
- Network partition: instances may be considered disconnected; monitor rebalances and task promotions.

Standby state can reduce restore time, but does not eliminate failure detection, rebalancing, and promotion time. Measure actual Recovery Time Objective (RTO) by testing process/instance termination.

## 22. Failure Domains and Standby Placement

If active and standby reside on the same host or failure domain, a single host failure can lose both copies. When infrastructure supports it, spread replicas across different nodes, zones, or racks to improve fault tolerance.

Do not look only at replica count. Check:

- Are pods scheduled on the same node?
- Are nodes in the same availability zone?
- Do persistent volumes share the same failure domain?
- Are Kafka broker/changelog replicas distributed accordingly?
- Are network paths between standby and Kafka independent?

Kafka Streams assignment and rack-awareness mechanisms depend on Kafka/client versions and deployment configuration. Do not assume standbys are placed in different zones just because `num.standby.replicas` is greater than 0; verify actual application placement.

## 23. Partition Skew and Hot Keys

Adding tasks, threads, or instances does not solve the case where a single partition receives most of the traffic. If partition keys are skewed, one task can run hot while others sit idle.

Example:

| Partition | Illustrative Traffic Share | Consequence |
|---|---:|---|
| P0 | 55% | Task P0 can become the bottleneck |
| P1 | 10% | Low load |
| P2 | 9% | Low load |
| P3 | 9% | Low load |
| P4 | 9% | Low load |
| P5 | 8% | Low load |

Inspect partition-level bytes/records, key distribution, and processing latency. You may need to choose a better key, split hot keys using business strategies, or change the topology. Changing partition keys requires considering ordering and state migration.

## 24. Operational Impact of Changing Partition Counts

Increasing partitions can create more tasks and parallelism for topologies reading that topic. However, changing the partition count can also alter key-to-partition mapping for standard partitioners. Messages with the same key before and after the change may land on different partitions depending on partition calculation.

For stateful topologies, changing partition counts requires reviewing:

- Co-partitioning across topics participating in joins.
- New task counts and task distribution.
- Internal repartition topics.
- State store and changelog partitioning.
- Per-key processing ordering during the transition period.
- State backfill/rebuild capabilities.

Do not arbitrarily increase partitions just to get more tasks. Test the topology and migration plan with representative data.

## 25. Key Configuration Properties

| Property | Scope | Effect |
|---|---|---|
| `applicationId` | Kafka Streams Binder | Shared identity of the topology and replicas |
| `num.stream.threads` | Kafka Streams client | Number of stream threads per instance |
| `num.standby.replicas` | Kafka Streams client | Desired number of standby task replicas per stateful task |
| `state.dir` | Kafka Streams client | Directory for local state storage |
| `commit.interval.ms` | Kafka Streams client | Commit/flush interval per Kafka Streams semantics and processing mode |
| `cache.max.bytes.buffering` or version-equivalent cache setting | Kafka Streams client | Record/state cache size to optimize processing |

Supported properties and property names may vary by Kafka Streams version. Use the Spring Cloud Stream release train and Kafka client matching your project. For the examples in this lesson, the primary properties are `num.stream.threads`, `num.standby.replicas`, and `state.dir`.

## 26. Environment-Specific Configuration Example

Threads, standbys, and state directory can be managed via environment variables:

```yaml
spring:
  cloud:
    function:
      definition: aggregateOrders
    stream:
      bindings:
        aggregateOrders-in-0:
          destination: ${ORDERS_TOPIC:orders.events}
      kafka:
        streams:
          binder:
            applicationId: ${STREAMS_APPLICATION_ID:order-aggregator-dev}
            configuration:
              num.stream.threads: ${STREAMS_THREADS:2}
              num.standby.replicas: ${STREAMS_STANDBY_REPLICAS:1}
              state.dir: ${STREAMS_STATE_DIR:/var/lib/order-stream/state}
```

Example deployment values:

| Environment | Replicas | Threads/instance | Standby/task | Goal |
|---|---:|---:|---:|---|
| Local | 1 | 1 | 0 | Simple for development |
| Integration test | 2 | 1 | 1 | Verify failover and standby |
| Staging | 3 | 2 | 1 | Measure throughput and recovery |
| Production | Per benchmark | Per benchmark | Per RTO/RPO | Balance capacity and availability |

These are illustrative values; production sizing must be based on partition count, state size, traffic, CPU, disk, network, and recovery targets.

## 27. Monitoring Thread and Task State

In production, observe both processing capacity and recoverability:

- Number of active tasks and standby tasks per instance.
- Number of stream threads and thread states.
- Records/second, bytes/second, and processing latency.
- Consumer lag per partition.
- Rebalance duration and task migration.
- State restore duration, restore rate, and changelog lag.
- Local state store size, RocksDB disk usage, and I/O latency.
- CPU, heap, garbage collection, and network throughput.
- Task, serialization, and commit/transaction errors.

If active tasks are insufficient, check partition count and topology. If tasks are sufficient but CPU is low, check thread assignment and downstream bottlenecks. If restoration is slow, check standby lag, changelog throughput, local disk, and state size.

Do not monitor only aggregate application-wide throughput. A hot partition or a slow-restoring task can be masked by aggregated metrics.

## 28. Testing Scaling and Recovery

An operational test suite should cover:

| Scenario | Action | Expected Result |
|---|---|---|
| Single instance, multiple threads | Set `num.stream.threads` greater than 1 | Multiple threads run tasks when partitions are sufficient |
| Multiple instances, same ID | Run multiple replicas with the same application ID | Tasks are distributed across instances |
| Replica with different ID | Intentionally change one replica's ID | Observe that it becomes an independent application |
| Fewer partitions than threads | Create a topic with few partitions | Extra threads do not create extra active tasks |
| Standby equal to 0 | `num.standby.replicas: 0` | Failover must restore state from changelog per Kafka Streams mechanics |
| Standby equal to 1 | Run at least two instances | Verify standby tasks are maintained on another instance |
| Stop active instance | Kill the process owning active tasks | Standby can be promoted; measure recovery time |
| Stop node hosting standby | Lose the failure domain holding standby copies | Verify tasks are restored/reassigned |
| Changelog lag | Generate high load or throttle network | Measure standby update delay and catch-up |
| Scale up/down | Change replica count | Measure rebalances, task movement, and throughput |
| Large state | Increase state store size | Measure restore duration, disk, and network |
| Partition skew | Create a hot key | Identify task/partition bottleneck |

`TopologyTestDriver` is suitable for testing topology logic. It does not replace integration/load tests when validating thread assignment, standby replicas, rebalancing, and state restoration. Those tests require a real Kafka broker and multiple Kafka Streams instances or an equivalent test environment.

## 29. Common Sizing Mistakes

| Wrong Choice | Consequence | Fix |
|---|---|---|
| Increasing threads when partitions are too few | Idle threads without throughput gain | Evaluate partitions and topology first |
| Increasing replicas with different application IDs | Independent apps consume independently, risking duplicate output | Share the same application ID for the same topology |
| Setting standbys while running only one instance | No other instance to hold an independent standby | Deploy additional replicas |
| Setting standby count too high | Wastes disk, network, CPU, and state update overhead | Choose standby count based on recovery targets |
| Confusing standby with active replicas | Expecting throughput gains that do not occur | Distinguish state copy from input processing |
| Missing internal topic ACLs | Standby/restore cannot read or write changelogs | Grant proper ACLs for internal topics |
| Sharing `state.dir` across replicas | Local state conflicts | Use a dedicated directory per instance |
| Placing all replicas on the same node | One node outage loses multiple state copies | Spread across failure domains |
| Ignoring hot partitions | One task overloads despite spare total CPU | Analyze keys and partition-level metrics |
| Unplanned partition increases | Changes key mapping/co-partitioning/state | Plan migration and test the topology |

## 30. Sizing and Deployment Workflow

1. Measure records/second, payload size, state size, and target latency.
2. Determine the partition count of each input topic and subtopology/repartition topics.
3. Estimate the number of active tasks that can be created.
4. Choose instance count and `num.stream.threads` based on CPU, tasks, and throughput benchmarks.
5. Keep one stable shared `applicationId` for all replicas of the topology.
6. Determine whether the topology has state stores requiring standbys.
7. Choose `num.standby.replicas` based on RTO, instance count, and state replication cost.
8. Ensure standbys reside on different instances/failure domains if fault tolerance is required.
9. Grant appropriate ACLs and retention for input/output/internal changelog topics.
10. Provision a dedicated local state directory with sufficient capacity and write permissions per instance.
11. Test scaling, rebalancing, failover, standby promotion, and state restoration.
12. Monitor task/thread states, lag, restore time, CPU, disk, and network in production.

## 31. Self-Check

- [ ] Distinguish topic partitions, Kafka Streams tasks, stream threads, and application instances.
- [ ] Explain how tasks are created from partitions and subtopologies.
- [ ] Know that partition count limits topology parallelism.
- [ ] Configure `num.stream.threads` in the Kafka Streams Binder.
- [ ] Distinguish vertical scaling with threads from horizontal scaling with replicas.
- [ ] Know that replicas of the same topology must share `applicationId`.
- [ ] Explain standby tasks and the role of changelog topics.
- [ ] Configure `num.standby.replicas`.
- [ ] Understand that standbys do not process input like active tasks and do not increase active throughput.
- [ ] Know that multiple independent instances are required for true standby failover.
- [ ] Distinguish standby tasks from Kafka broker replication.
- [ ] Evaluate the impact of partition skew, state size, and failure domains.
- [ ] Design tests for scaling, rebalancing, failover, and state restoration.

## Conclusion

Kafka Streams creates tasks from input/subtopology partitions and executes them on each instance's stream threads. `num.stream.threads` tunes the number of threads per instance; replica count scales capacity horizontally and spreads failure domains, though both are bounded by the active tasks produced by partitions. For stateful topologies, `num.standby.replicas` maintains state copies from changelogs on other instances to reduce recovery time when an active instance fails. Standbys do not process input in place of active tasks and do not increase throughput. Production sizing must balance partitions, tasks, threads, instances, state size, changelogs, CPU, disk, network, and recovery targets; then validate through integration/load tests and real metrics.
