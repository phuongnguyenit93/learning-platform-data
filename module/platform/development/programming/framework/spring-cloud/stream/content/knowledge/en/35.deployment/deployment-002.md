# Managing Broker Resources by Environment

A Spring Cloud Stream application may run in local, development, test, staging, and production environments, but each environment has different traffic load, criticality, security requirements, and budget. Managing broker resources by environment means provisioning the right resources for each stage, isolating data and access permissions, controlling storage capacity, retention, replication, quotas, and connections, while keeping configuration reproducible during deployment.

The binder only helps the application connect to the broker. It does not replace cluster, topic, queue, namespace, storage, quota, ACL, or backup policy administration. You must clearly separate application configuration from infrastructure resources provisioned by the platform.

## 1. Why Manage Resources by Environment?

A development environment typically needs low cost, easy creation/deletion, and short-lived test data. Production requires fault tolerance, headroom capacity, access control, monitoring, and recovery procedures. If a broker or namespace is shared without clear boundaries, tests can fill up production queues, developers might read sensitive data, or a single deployment could alter another service's configuration.

Key objectives:

- **Isolation:** Clear boundaries for data, credentials, quotas, and permissions per environment.
- **Right-sizing:** Partitions, queues, storage, throughput, and connections matched to load.
- **Durability:** Replication, retention, backup, and disaster recovery aligned with criticality.
- **Security:** TLS, authentication, ACL/RBAC, and secret rotation.
- **Reproducibility:** Resources declared with Infrastructure as Code (IaC), with reviews and change history.
- **Cost control:** Unused environments do not retain large resources or unbounded data.
- **Consistent operations:** Standardized naming, monitoring, alerting, and runbooks.

## 2. Classifying Environments and Service Tiers

Do not provision the same configuration for every environment. The matrix below is a starting point; actual values depend on load, SLA, company policy, and broker capabilities.

| Environment | Goal | Suggested Resources | Data and Retention |
|---|---|---|---|
| Local | Fast development on a personal machine | Single simple broker or container; few partitions; small storage | Dummy data, can be deleted/reset |
| Development | Team integration and functional testing | Shared cluster with dedicated namespace/vhost/topics; low quotas | Synthetic data, short retention |
| Test/CI | Automated runs, test isolation | Ephemeral broker or dedicated namespace; auto-created and cleaned up | Data exists only for the test lifecycle |
| Staging | Closely mirrors production | Topology, TLS, ACLs, partitions, and policies similar to production at smaller scale | Dummy or anonymized data; retention sufficient for testing |
| Production | Serving live business traffic | HA cluster, replication, quotas, capacity headroom, backup/DR | Data governed by storage contracts and compliance requirements |

A shared cluster for multiple environments is only suitable when strong isolation exists: separate tenant/vhost/namespace, credentials, ACLs, quotas, naming, and monitoring. For sensitive data or high-criticality workloads, consider dedicated clusters to prevent noisy neighbors and reduce the blast radius.

## 3. Defining Resource Boundaries and Ownership

Before creating topics or queues, inventory resources per service and environment:

| Attribute | Example | Purpose |
|---|---|---|
| Environment | dev, staging, prod | Select cluster and policies |
| Service | order-stream | Identify owner |
| Binder type | kafka, rabbit, pulsar | Identify messaging system |
| Destination | orders.created | Topic, exchange/queue, or Pulsar topic |
| Consumer group/subscription | order-projection-v1 | Isolate processing progress |
| Retention/TTL | 3 days, 7 days | Bound data lifecycle |
| Partition/replica | 12 partitions, RF 3 | Throughput and durability |
| Quota | 20 MB/s, 100 connections | Resource limits |
| Data classification | internal, confidential | Select access and storage policies |
| Owner/contact | Order Platform team | Accountable team |

Every resource should have an owner, purpose, environment, creation date or reference ticket, and cleanup policy. Avoid unowned destinations or generic names like test-topic used indiscriminately by multiple teams.

A naming convention can include service, environment, and purpose, for example:

    dev.order-stream.orders.created
    staging.order-stream.orders.created
    prod.order-stream.orders.created

Actual naming depends on the broker. Kafka topics typically do not enforce a tenant/namespace hierarchy; RabbitMQ uses virtual hosts, exchanges, and queues; Pulsar uses tenant/namespace/topic. Regardless of structure, names should indicate the owner and environment without embedding sensitive data in the name.

## 4. Configuring Spring Cloud Stream per Environment

Applications should load endpoints and credentials from profiles, environment variables, or a secret manager. Never commit production addresses, passwords, tokens, truststore passwords, or private keys to the repository.

Shared binding configuration example:

    spring:
      cloud:
        function:
          definition: processOrder
        stream:
          bindings:
            processOrder-in-0:
              destination: ${ORDERS_INPUT_DESTINATION}
              group: ${ORDERS_CONSUMER_GROUP}
              consumer:
                concurrency: ${ORDERS_CONCURRENCY:1}
            processOrder-out-0:
              destination: ${ORDERS_OUTPUT_DESTINATION}

Environment variables are supplied per deployment environment. Destination and consumer group names must remain stable by contract; never let test and production accidentally share the same group.

### 4.1. Kafka Binder

Kafka connection configuration example:

    spring:
      cloud:
        stream:
          kafka:
            binder:
              brokers: ${KAFKA_BOOTSTRAP_SERVERS}
              auto-create-topics: false
              auto-add-partitions: false

In production, infrastructure workflows should generally create topics and partitions before the application starts. Disabling auto-create/auto-add prevents applications from accidentally creating topics with inappropriate default partition counts or retention settings. For local/dev, auto-create can be enabled if controlled and the broker is dedicated to that environment.

The Kafka Binder provides broker connection properties and producer/consumer settings. Attributes such as topic retention, replication factor, min.insync.replicas, cleanup.policy, broker quotas, and ACLs belong to the Kafka administration layer; do not assume that merely setting them in a binding will cause the broker to apply them. Some binder properties support creating topics or partitions, yet resource policies still need to be managed through cluster governance mechanisms.

### 4.2. RabbitMQ Binder

Applications can receive broker addresses via Spring Boot Rabbit connection properties:

    spring:
      rabbitmq:
        addresses: ${RABBITMQ_ADDRESSES}
        username: ${RABBITMQ_USERNAME}
        password: ${RABBITMQ_PASSWORD}
      cloud:
        stream:
          bindings:
            processOrder-in-0:
              destination: orders
              group: order-projection

RabbitMQ commonly uses virtual hosts to isolate resources and permissions. Exchanges, queues, bindings, DLXs, TTL policies, max-length, quorum queues, and user permissions should be created or managed via IaC/automation. Applications should not use a broker administrator account to run consumers.

### 4.3. Pulsar Binder

Spring for Apache Pulsar provides client configuration, while the Pulsar Binder maps bindings to topics/subscriptions:

    spring:
      pulsar:
        client:
          service-url: ${PULSAR_SERVICE_URL}
      cloud:
        stream:
          bindings:
            processOrder-in-0:
              destination: persistent://${PULSAR_TENANT}/${PULSAR_NAMESPACE}/orders.created
              group: order-projection

Pulsar uses tenants and namespaces to organize topics along with policies. Administration endpoints and authentication may need separate configuration depending on the Spring Boot/Spring Pulsar version. Tenants, namespaces, retention, backlog quotas, replication clusters, and permissions should be provisioned by the platform/IaC. Do not use broad admin credentials as runtime credentials for applications.

Specific property names and provisioning capabilities vary by Spring Cloud Stream, binder, and Spring Boot versions. Manage versions through a BOM, verify the configuration metadata of the release in use, and confirm effective configuration in staging before releasing.

## 5. Separating Connection Configuration from Broker Resource Configuration

Application configuration and broker configuration serve different purposes:

| Application/Binder Configuration | Broker/Platform Configuration |
|---|---|
| Broker endpoint, credentials, TLS trust | Cluster size, broker nodes, storage pools |
| Destination and consumer group | Topic/queue/namespace creation |
| Consumer concurrency, retries, ack mode | Partition count, replication, queue type |
| Producer batching, compression, timeouts | Retention, quotas, storage policies |
| Binding content type and Serde | ACLs, roles, vhost permissions |
| Client ID and connection settings | Broker network, listeners, disk alerts |

For example, setting destination to orders.created does not automatically guarantee the topic has 12 partitions, a replication factor of 3, or 7-day retention. Verify the actual topic via the broker admin API/CLI or IaC state.

## 6. Managing Kafka Resources by Environment

Kafka resources must be managed at both cluster and topic levels. Key decisions:

- **Partition count:** Based on throughput, consumer parallelism, and key distribution.
- **Replication factor:** Number of partition replicas; production typically requires multiple replicas across different brokers.
- **min.insync.replicas:** Minimum synchronized replicas required for producers requesting appropriate acks.
- **Retention:** Duration or size for storing records before the broker deletes them.
- **Cleanup policy:** delete, compact, or a combination depending on the topic's purpose.
- **Quota:** Produce/consume throughput or request limits per principal/client.
- **ACL:** Read/write/describe/create permissions per topic and group.
- **Storage:** Disk capacity, replication overhead, and data growth rate.

Example matrix:

| Attribute | Dev | Staging | Production |
|---|---|---|---|
| Broker | Single node or small cluster | Small-scale HA cluster | HA cluster sized to capacity |
| Replication factor | 1 if data loss is acceptable | 2 or per topology | Usually 3 when enough brokers exist |
| Partition | Few, per tests | Close to production structure | Based on throughput and max consumers |
| Retention | Short | Sufficient for testing/replay | Per business needs and compliance |
| ACL | Dedicated dev credentials | Dedicated staging credentials | Least-privilege principal |
| Quota | Low | Close to test load | Per capacity plan |

Do not set a replication factor of 3 if the cluster only has two brokers; likewise, do not treat RF 1 as a safe production configuration. min.insync.replicas must be compatible with the replication factor and producer acks; otherwise, producers may have writes rejected when a broker loses a replica.

### 6.1. Calculating Kafka Storage Capacity

Estimate raw data:

    raw_bytes = average_message_bytes × messages_per_second × retention_seconds

Cluster capacity must also account for replication and overhead:

    cluster_storage ≈ raw_bytes × replication_factor × overhead_factor

Example: 2 KB average message, 500 messages/second, 3-day retention:

    raw_bytes = 2,048 × 500 × 259,200
              ≈ 265.4 GB

With a replication factor of 3, raw replicated storage is around 796 GB before accounting for indexes, compression, headroom, and overhead. This is an initial estimate; actual message sizes after compression, tombstones, compaction, segments, and retention policies can change the result significantly.

Do not target 100% disk utilization. Reserve headroom for replica rebalancing, broker restarts, traffic bursts, and operational incident response time.

### 6.2. Retention and Topic Types

Event log topics need sufficient retention for consumers to recover or replay within business bounds. Compacted topics are used for state/changelogs or latest value per key; do not arbitrarily apply short retention if consumers rely on rebuilding state.

Separate topics with distinct purposes:
- Event history: Retained by time/size and replay requirements.
- State/changelog: Cleanup policy aligned with state store semantics.
- Retry/DLQ: Retention long enough for investigation and controlled reprocessing.
- Metrics/telemetry: Avoid putting large payloads or sensitive data into shared topics.

## 7. Managing RabbitMQ by Environment

RabbitMQ commonly organizes permissions and resources by virtual host. Each environment can use a separate vhost, such as /orders-dev, /orders-staging, and /orders-prod, or dedicated clusters when strong isolation is needed.

Resources to manage:
- Virtual hosts and configure/write/read permissions.
- Exchange types, queues, bindings, and durability.
- Queue type: classic or quorum depending on requirements.
- Dead-letter exchanges/queues and routing keys.
- TTL, max-length, max-length-bytes, and overflow policies.
- Prefetch and consumer concurrency.
- Users, passwords, TLS certificates, and policies.
- Memory/disk watermarks and connection/channel limits.

Example separating vhosts via profiles:

    spring:
      rabbitmq:
        virtual-host: ${RABBITMQ_VHOST}
        addresses: ${RABBITMQ_ADDRESSES}

Do not create a single user with configure/write/read permissions across all vhosts for every service. A consumer typically only needs read access on relevant queues/exchanges; a producer only needs write access to target exchanges. Configure permissions should belong to a provisioning identity.

### 7.1. Queue Durability and Replication

A durable queue does not automatically mean messages are protected against every failure. Consider queue type and cluster topology. Quorum queues use Raft-based replication to increase durability, at the cost of extra resources and specific node-count requirements. Classic mirrored queues are an older mechanism that has changed across RabbitMQ versions; do not copy configurations from outdated documentation without verifying support.

Select queue types based on delivery requirements, throughput, latency, and cluster capabilities. Staging should use queue types close to production to validate ack behavior, failover, and throughput.

### 7.2. TTL, DLX, and Queue Limits

Queues should not hold messages indefinitely unless required by business logic. You can configure message TTL, queue TTL, max-length, or dead-letter exchanges to handle expired/overflowing messages. Policies must be reviewed because overflow can drop or dead-letter messages depending on configuration. Do not set TTL too short on retry/DLQ queues, causing messages to disappear before investigation.

## 8. Managing Pulsar Resources by Environment

Pulsar uses tenants and namespaces to organize topics, permissions, and policies. Example:

    persistent://orders-dev/streaming/orders.created
    persistent://orders-staging/streaming/orders.created
    persistent://orders-prod/streaming/orders.created

Resources/policies to manage:
- Tenants and namespaces.
- Partitioned topics and partition counts.
- Namespace bundles and load distribution across brokers.
- Retention and backlog quotas.
- Message TTL and compaction.
- Replication across clusters/regions.
- Authentication roles and namespace permissions.
- Storage quotas, backlog sizes, and BookKeeper capacity.
- Subscriptions and consumer counts.

### 8.1. Retention and Backlog Quotas

Retention defines how long messages are kept for rereading after subscriptions have acknowledged them, within policy limits. Backlog quota limits the amount of unacknowledged data a subscription may accumulate. These two policies serve different purposes: retention supports archiving/replay; backlog quota protects storage when consumers slow down or stop.

Choose policies by environment:
- Dev: Small retention and backlog quotas, easy to clean up.
- Staging: Long enough to test restarts, replays, and load.
- Production: Aligned with RPO/RTO, audit requirements, and storage capacity.

If a backlog quota is exceeded, the broker may enforce policies such as producer exceptions, consumer eviction, or holding backlog depending on configuration. Understand the exact behavior before enabling; a storage-protection policy can affect producers or subscriptions.

### 8.2. Replication and Storage

Cross-cluster Pulsar replication differs from ledger replication in BookKeeper. One mechanism protects data across bookies within a cluster; the other replicates topic data across clusters/regions as configured. Do not treat enabling geo-replication as a substitute for backups or failover testing.

Monitor bookie disk usage, ledger availability, write/read latency, under-replicated ledgers, and broker ownership. Staging should test permissions, endpoints, and policies similar to production using test data.

## 9. Quotas and Noisy Neighbor Protection

A shared cluster can be overwhelmed if one service consumes excessive CPU, disk, connections, or throughput. Quotas limit the impact between tenants/clients.

Commonly needed limits:
- Produce/consume byte rate or request rate.
- Number of connections, channels, or consumers.
- Number of topics/queues/partitions.
- Storage quotas and retention.
- Backlog size and message age.
- Max message size and batch size.
- Concurrent admin/provisioning requests.

Quotas should be grounded in a capacity plan and trigger alerts before hitting thresholds. If set too low, producers may be throttled and consumers may fall behind. If set too high, a misbehaving workload can degrade other services.

In a shared cluster, attach quotas to appropriate service principals/client IDs or tenants/namespaces/vhosts. Do not rely solely on application hostnames, since multiple services may run on the same node or behind NAT.

## 10. Security and Networking by Environment

Each environment requires dedicated endpoints and credentials. Production should enforce TLS for broker and admin endpoints, authenticate service identities, and apply least-privilege authorization.

Principles:
- Separate dev/staging/prod secrets; never reuse passwords or tokens.
- Use an encrypted, access-controlled secret manager or Kubernetes Secret.
- Do not store secrets in application.yml, Docker images, logs, or shared config files.
- Restrict network paths from workloads to brokers; open only required ports.
- Enforce ACLs/RBAC per topic, queue, namespace, and consumer group.
- Rotate credentials/certificates and maintain a revocation process.
- Separate runtime publish/consume permissions from resource provisioning permissions.
- Validate TLS hostnames, CA trust, and certificate expiration.
- Do not expose admin APIs or management UIs publicly unless necessary.

Runtime applications should have a dedicated principal per service and environment. If a credential is compromised, its blast radius should be confined to the resources that service needs.

## 11. Infrastructure as Code and Provisioning

Topics, queues, namespaces, quotas, ACLs, and policies should be declared in version-controlled IaC or provisioning automation. Tools can include Terraform providers, Helm charts, Kubernetes operators, Ansible, or reviewed admin scripts. Choose tools suited to the broker and your organization's operational standards.

A sound management workflow:
1. Declare resource name, owner, environment, and policies.
2. Review changes in a pull request.
3. Inspect the plan/diff before applying.
4. Provision broker resources before deploying the application.
5. Verify topics/queues/namespaces, partitions, retention, and ACLs.
6. Deploy the application with environment-specific endpoints and secrets.
7. Run publish/consume smoke tests.
8. Monitor lag, errors, quotas, and resource usage.
9. Clean up test/dev resources according to TTL and owner.

Do not let every application auto-create production resources using admin credentials at startup. Doing so grants overly broad application permissions and makes resource policies hard to review. Auto-provisioning can be helpful in local/dev, but production should have clear ownership and governance.

## 12. Managing Configuration Through CI/CD

A deployment pipeline should separate the application artifact from environment configuration. The same artifact can be promoted across dev, staging, and production; endpoints, credentials, and resource names are injected per environment.

Environment variable examples:

    KAFKA_BOOTSTRAP_SERVERS=kafka-prod.example.internal:9093
    ORDERS_INPUT_DESTINATION=prod.order-stream.orders.created
    ORDERS_CONSUMER_GROUP=order-projection-v2

Do not use the same consumer group across different environments if they must process independently. With Kafka, sharing a group can split partitions and offsets, causing staging to steal data from production if clusters/topics/groups are accidentally shared. RabbitMQ and Pulsar similarly risk sharing queues/subscriptions or altering processing progress.

Release steps:
- Validate schemas/configs.
- Provision or verify resources.
- Verify ACLs/TLS.
- Deploy consumers using a safe rollout strategy.
- Run publish/consume smoke tests.
- Confirm consumer groups/subscriptions and backlog.
- Monitor alerts post-deployment.
- Roll back application version or config per runbook.

Do not bring real production data into staging without proper approval, anonymization, and data protection policies.

## 13. Promotion and Configuration Differences

Staging should match production in broker type, version, authentication, TLS, topic/queue policies, and binder behavior. Scale can be smaller, but critical semantics must be preserved. For example:
- Kafka staging should test partition keys, groups, retention, and consumer rebalancing.
- Rabbit staging should test queue types, acks, DLXs, TTL, and prefetch.
- Pulsar staging should test tenants/namespaces, subscription types, backlog quotas, and auth.

Do not reuse a single shared profile that only swaps hostnames if environments differ in policies. Explicitly declare properties that need to differ while keeping common configuration shared to minimize drift.

## 14. Backup, Retention, and Disaster Recovery

Each stream should define:
- RPO: Acceptable amount of data loss during an incident.
- RTO: Time required to restore the service.
- Retention: Record storage duration and replay capability.
- Replication: Copies within a cluster or across regions.
- Backup/restore: What data is backed up, frequency, and verification method.
- Recovery owner: Who executes failover, replay, and reconciliation.

Replication is not backup. It can replicate deletions or corrupted data as well. Backups need independent retention, access controls, and restore tests.

Kafka can use MirrorMaker 2 or cluster replication solutions to replicate topics/consumer offsets depending on architecture. RabbitMQ offers federation/shovel or cluster/backup mechanisms depending on the use case; do not confuse cluster replication with message backups. Pulsar supports geo-replication between clusters; metadata/data backup procedures and failover tests are still required.

Testing failover in staging:
1. Produce a batch of test events with unique IDs.
2. Confirm producers/consumers operate normally on the primary cluster.
3. Simulate connection loss or switch endpoints per runbook.
4. Verify data arrives on the standby cluster within RPO bounds.
5. Switch consumers over and check for duplicates/gaps.
6. Measure recovery time and reconcile event IDs.
7. Restore normal state according to documented procedures.

## 15. Capacity Planning by Environment

Capacity must be calculated from data rates, message sizes, retention, replication, and overhead—not just partition or queue counts.

Example capacity plan table:

| Component | Dev | Staging | Production |
|---|---:|---:|---:|
| Peak event rate | 20/s | 200/s | 2,000/s |
| Average payload | 1 KB | 1 KB | 2 KB |
| Retention | 1 day | 3 days | 7 days |
| Replication | 1 | 2 | 3 |
| Consumer instances | 1 | 2 | Based on load tests |
| Storage headroom | 30% | 30% | Per failover/burst plan |

Numbers are illustrative only. Production capacity must account for peaks/bursts, replays, backlog draining, replication, compaction, indexes, log segments, message metadata, and free space for brokers to rebuild replicas. For RabbitMQ, include message store, queue indexes, and quorum logs. For Pulsar, include ledger storage, backlog retention, and bookie replication.

Do not take a dev capacity plan and multiply by an arbitrary factor to size production. Rely on load testing and real observability data.

## 16. Resource Monitoring and Alerting

Monitor both broker and application resources:

| Category | Kafka | RabbitMQ | Pulsar |
|---|---|---|---|
| Storage | Disk per broker, log size, retention | Message store, queue index, disk alarm | Bookie disk, ledger size, backlog |
| Throughput | Bytes/sec, records/sec, request latency | Publish/deliver/ack rates | Publish/dispatch rates |
| Parallelism | Partitions, consumer group lag | Queue consumers, unacked, prefetch | Partitions, subscriptions, consumer count |
| Availability | Brokers, controller, ISR | Nodes, quorum queues, connections | Brokers, bookies, ledgers |
| Quota | Client/user quotas, request throttling | Connection/channel/resource limits | Namespace/tenant resource quotas |

Alerts should be tied to impact:
- Disk or storage projected to run out before remediation time.
- Consumer lag/backlog age exceeding SLO.
- Ready/unacked queues growing continuously.
- Under-replicated partitions or abnormal ledger health.
- Sustained quota throttling.
- Certificates nearing expiration.
- Connection/consumer count dropping to 0 during active hours.
- Retention or backlog quotas approaching limits.

Do not alert merely because CPU spikes for one minute if throughput and latency remain within SLO. Use thresholds, sustained windows, trends, and runbooks to reduce alert noise.

## 17. Cleaning Up Unused Resources

Old topics/queues/namespaces increase costs and make it harder for operators to distinguish live resources. Maintain a controlled cleanup process:
- Dev/test resources have owners and expiry/TTL.
- Confirm no active producers/consumers remain.
- Check retention, DLQ, and audit requirements before deleting.
- Export required metadata if needed.
- Require review approval for staging/prod resources.
- Delete via IaC or admin workflows with audit logging.
- Verify no bindings still reference the destination.

Do not automatically delete production topics simply because there has been no traffic for a few days; a topic may serve as a replay or audit source. Cleanup must be governed by owner, contract, and retention policies.

## 18. Resource Incident Runbooks

### 18.1. Broker Out of Disk Space

1. Identify the affected broker/node or bookie.
2. Check data growth rate, retention, and replication overhead.
3. Find the topics/queues/namespaces consuming the most storage.
4. Confirm whether retention can be reduced or cleanup triggered per policy.
5. Expand storage/brokers if necessary through infrastructure procedures.
6. Monitor replica recovery, queue health, and producer throttling.
7. Reconcile data after the system stabilizes.

Never manually delete segments, ledgers, or queue files to free up space.

### 18.2. Quota Exceeded

1. Identify the throttled principal/client/tenant.
2. Compare actual throughput against quotas and SLOs.
3. Check for bursts, retry storms, or producer loops.
4. Determine whether the quota was misconfigured or workload grew legitimately.
5. Adjust quotas with review, or throttle/reduce producer load.
6. Monitor lag/backlog and downstream systems after changes.

Never disable cluster-wide quotas just to accommodate one misbehaving service.

### 18.3. Test Environment Impacting Another Environment

1. Identify the endpoint, topic/queue/subscription, and credentials in use.
2. Stop the misconfigured test producers/consumers.
3. Check whether groups/subscriptions shared processing progress.
4. Separate resources and credentials per environment.
5. Reconcile events read/written by mistake and assess replay needs.
6. Add config validation checks in CI to prevent recurrence.

## 19. Common Mistakes

| Mistake | Consequence | Prevention |
|---|---|---|
| Sharing topics/queues/groups between dev and prod | Tests consume or alter production data | Separate namespaces/vhosts/topics/groups and credentials |
| Auto-creating resources in production | Topics/queues created with wrong policies | Pre-provision via IaC and disable auto-create where appropriate |
| Using admin credentials for applications | Large blast radius if secrets leak | Least-privilege runtime principals |
| Unlimited retention | Storage grows unboundedly | Set retention and quotas by contract |
| Replication factor exceeding broker count | Topics fail to provision or lack ISR | Verify topology and min ISR |
| Scaling consumers without scaling broker capacity | Brokers or downstream systems overload | Capacity plan the entire pipeline |
| Staging differs too much from production | Bugs only surface during real deployment | Keep broker versions and key semantics close to production |
| Not managing secrets by environment | Credential leaks or connecting to wrong cluster | Use secret managers and CI environment protections |
| Treating replication as backup | Cannot recover from deleted or bad data | Independent backups and restore tests |
| Not cleaning up test resources | Rising costs and operational clutter | Track owners, expiry, and controlled IaC destroy |

## 20. Environment-Based Broker Management Workflow

1. Classify data, criticality, and stream SLOs.
2. Choose isolation level: dedicated cluster vs. dedicated tenant/vhost/namespace.
3. Calculate partitions, queues, throughput, connections, and storage.
4. Choose replication, retention, backlog quotas, and recovery policies.
5. Create dedicated principals, ACLs, TLS certificates, and secrets.
6. Declare resources in IaC and review diffs.
7. Provision broker resources prior to deploying applications.
8. Inject endpoints/credentials via config store or secret manager.
9. Deploy binders and bindings with environment-specific destinations/groups.
10. Smoke test publish/consume and verify resource policies.
11. Monitor lag, storage, quotas, connections, DLQs, and alerts.
12. Periodically review capacity/retention and clean up end-of-life resources.

## 21. Pre-Deployment Checklist

- [ ] Each environment has dedicated endpoints, destinations, and consumer groups/subscriptions.
- [ ] Clusters or tenants/vhosts/namespaces have clear boundaries and owners.
- [ ] Topics, queues, partitions, and storage are provisioned via IaC.
- [ ] Replication factor/quorum matches topology and durability requirements.
- [ ] Retention, TTL, DLQ, and backlog quotas have explicit values.
- [ ] Throughput, connection, and storage quotas are configured per capacity plan.
- [ ] Runtime principals have only necessary publish/consume permissions.
- [ ] Admin/provisioning identities are separated from application credentials.
- [ ] TLS, secret rotation, network policies, and certificate expiry are managed.
- [ ] Spring Cloud Stream profiles pull endpoints from environment/secret stores.
- [ ] Production does not auto-create resources outside approved workflows.
- [ ] Staging mirrors production broker versions and key semantics.
- [ ] Dashboards/alerts exist for lag, backlog, storage, quotas, and broker health.
- [ ] Backup/DR plan includes RPO/RTO and restore tests.
- [ ] Dev/test resources have owners, expiry, and cleanup procedures.
- [ ] Runbooks exist for disk exhaustion, quota limits, and environment misconfiguration.

Managing broker resources by environment is full-lifecycle resource management: isolating environments, provisioning topics/queues/namespaces, assigning quotas, retention, replication, access controls, monitoring, backups, and cleanup. Spring Cloud Stream is just the application layer connecting to those resources; broker policies must be governed independently and verified before deployment. When a single artifact is promoted across environments with properly injected endpoints, credentials, and destinations, the system reduces the risk of tests impacting production, controls costs, and establishes clear recoverability.

## References

- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/)
- [Apache Kafka — Operations and Configuration](https://kafka.apache.org/documentation/#operations)
- [RabbitMQ — Virtual Hosts and Access Control](https://www.rabbitmq.com/docs/vhosts)
- [RabbitMQ — Quorum Queues](https://www.rabbitmq.com/docs/quorum-queues)
- [Apache Pulsar — Tenants and Namespaces](https://pulsar.apache.org/docs/next/concepts-multi-tenancy/)
- [Apache Pulsar — Namespace Policies](https://pulsar.apache.org/docs/next/admin-api-namespaces/)
