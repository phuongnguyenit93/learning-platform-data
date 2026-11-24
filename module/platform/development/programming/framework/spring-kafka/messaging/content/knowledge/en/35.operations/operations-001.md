# Checking Brokers and Bootstrap Servers

When operating a Spring Kafka application, connection errors often appear even before a listener receives any record. The application might fail to resolve hostnames, fail to open a TCP connection, fail SASL/TLS authentication, or successfully connect to a bootstrap broker yet fail to reach the brokers that the cluster advertises in metadata.

Checking brokers and `bootstrap.servers` needs to follow the entire connection flow: from the initial bootstrap address, through the metadata returned by Kafka, to the leader/controller broker endpoints that the client needs to reach. A bootstrap address accepting a TCP port connection is not enough to conclude that the application can read or write data.

## 1. What are bootstrap servers used for?

`bootstrap.servers` is the initial list of addresses for a Kafka client to find a broker and fetch cluster metadata. The client does not need to connect directly to every broker at initialization; it can start with one or a few addresses from the list, then use metadata to learn which broker manages which partition and leader.

Example of configuring multiple endpoints:

```properties
spring.kafka.bootstrap-servers=broker-1.example.net:9092,broker-2.example.net:9092,broker-3.example.net:9092
```

Declare multiple reachable brokers so the client has fallback endpoints when one bootstrap address is temporarily unavailable. All addresses must belong to the same cluster and match the listener/protocol used by the application.

Bootstrap servers are not the only list the client will connect to over its lifetime. After receiving metadata, the client connects to the broker endpoints advertised by the cluster. Therefore, you must verify both bootstrap addresses and advertised broker addresses.

## 2. Understanding advertised.listeners and post-bootstrap connection errors

Brokers publish their client-facing endpoints through the `advertised.listeners` configuration. This is the hostname/IP and port that a broker sends in metadata. The `listeners` configuration determines where the broker binds and listens; `advertised.listeners` determines which address clients see to connect.

A common mistake when running Kafka in Docker is that the application connects to `localhost:9092` or a host-published port, but metadata returns a hostname that only resolves inside the Docker network. An application running outside the container cannot connect to that endpoint.

```text
Spring Boot app
      |
      | bootstrap: localhost:9092  (connectable)
      v
Kafka broker
      |
      | metadata returns: kafka-1:29092
      v
App host cannot resolve kafka-1
```

Configure separate listeners for the network zones that need access—for example, an internal listener for containers and an external listener for applications running on the host. Each client must use the endpoint advertised for its network. Do not set `advertised.listeners` to `localhost` if clients run on another machine or container.

## 3. Checking DNS and TCP from the actual runtime environment

Run checks from the exact machine, container, or Kubernetes pod running Spring Boot. Testing from a developer's laptop does not prove that a production pod shares the same DNS routes, firewall rules, or network policies.

On Windows PowerShell:

```powershell
Resolve-DnsName broker-1.example.net
Test-NetConnection broker-1.example.net -Port 9092
```

On Linux or inside a container:

```bash
getent hosts broker-1.example.net
nc -vz broker-1.example.net 9092
```

`Resolve-DnsName` or `getent hosts` verifies name resolution. `Test-NetConnection` or `nc` tests whether TCP can open to the port. A successful TCP check only proves that the network path and port are reachable; it does not verify the Kafka protocol, TLS handshake, SASL authentication, ACLs, or topic permissions.

Repeat the check against the broker endpoints that the client receives in metadata. If the bootstrap broker is reachable but an advertised endpoint is not, producers/consumers can still time out when interacting with partitions managed by that broker.

## 4. Checking TLS and SASL

If the cluster requires TLS or SASL, the client's protocol and credentials must match the broker listener. In Spring Boot, an example configuration for SASL/SCRAM over TLS is:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
    properties:
      "[security.protocol]": SASL_SSL
      "[sasl.mechanism]": SCRAM-SHA-512
      "[sasl.jaas.config]": ${KAFKA_SASL_JAAS_CONFIG}
```

The `KAFKA_BOOTSTRAP_SERVERS` variable holds a comma-separated list of host:port pairs. `KAFKA_SASL_JAAS_CONFIG` holds the JAAS configuration injected from a secret manager or deployment environment. Never write real usernames/passwords into source code, committed configuration files, or logs.

If using a private CA, configure the truststore or appropriate trust material so the JVM can verify the broker certificate. Verify that the hostname in the certificate matches the hostname the client connects to. Do not disable hostname verification to bypass certificate errors in production.

Distinguish common errors:

- `SSLHandshakeException`: check the trust chain, certificate expiry, hostname, and TLS protocol/ciphers.
- `SaslAuthenticationException`: check username, password, mechanism, and JAAS config.
- `TopicAuthorizationException` or `GroupAuthorizationException`: the client progressed past the connection step, but the principal lacks ACLs on the topic or consumer group.

## 5. Checking brokers with Kafka CLI

Use the scripts included with the Kafka distribution from the same network and with the same security configuration that the application uses. When the cluster requires SASL/TLS, create a dedicated client properties file, such as `client.properties`, and pass it via `--command-config`.

Check that the broker supports Kafka APIs and responds:

```bash
kafka-broker-api-versions.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --command-config client.properties
```

List topics:

```bash
kafka-topics.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --command-config client.properties \
  --list
```

Inspect partitions, leaders, replicas, and ISR of a topic:

```bash
kafka-topics.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --command-config client.properties \
  --describe \
  --topic orders
```

Check consumer groups and committed offsets:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --command-config client.properties \
  --describe \
  --group order-service
```

On Windows, use the corresponding `.bat` files in the `bin\windows` directory of the Kafka distribution. Script names and some options may vary by Kafka version; use scripts from a version compatible with the cluster.

The `--list` and `--describe` commands require the corresponding ACL permissions. If a command fails with authorization denied, that does not necessarily mean the broker is down; distinguish connection/authentication errors from resource permission errors.

## 6. Checking the cluster with AdminClient

A Java application can use Kafka `AdminClient` to inspect the cluster ID, broker nodes, and controller. This operates at the Kafka protocol layer, which is more informative than a plain TCP probe:

```java
Map<String, Object> config = new HashMap<>();
config.put(AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
    "broker-1.example.net:9092,broker-2.example.net:9092");

// Add security.protocol, sasl.mechanism, and sasl.jaas.config
// if the cluster requires SASL/TLS.
try (AdminClient admin = AdminClient.create(config)) {
    DescribeClusterResult result = admin.describeCluster();

    String clusterId = result.clusterId().get(5, TimeUnit.SECONDS);
    Collection<Node> nodes = result.nodes().get(5, TimeUnit.SECONDS);
    Node controller = result.controller().get(5, TimeUnit.SECONDS);

    log.info("Kafka cluster={}, brokers={}, controller={}",
        clusterId, nodes.size(), controller);
}
```

Set a finite timeout on admin operations so health checks do not hang indefinitely. Close `AdminClient` after use. If using AdminClient in a periodic health indicator, consider reusing a lifecycle-managed client instead of creating a new client on every probe.

You can extend the check with `describeTopics(...)` to verify that topics exist and inspect partition metadata. However, `DESCRIBE` permission and data read permission are separate; succeeding on topic description does not prove that the consumer has `READ` ACL or the producer has `WRITE` ACL.

## 7. Configuring bootstrap servers in Spring Boot

In a Spring Boot application, define the bootstrap list in one consistent place and supply values per deployment environment:

```properties
spring.kafka.bootstrap-servers=${KAFKA_BOOTSTRAP_SERVERS}
spring.kafka.consumer.group-id=order-service
spring.kafka.consumer.properties[request.timeout.ms]=30000
spring.kafka.admin.properties[request.timeout.ms]=10000
```

Do not hard-code dev addresses into production artifacts. Use DNS/service endpoints appropriate for the environment and ensure every broker endpoint in metadata is reachable from the workload.

If the application has custom configurations for `ProducerFactory`, `ConsumerFactory`, `KafkaAdmin`, or `AdminClient`, verify that each client receives the right bootstrap list and security properties. Custom beans can override Spring Boot auto-configuration.

## 8. Readiness checks and startup verification

Readiness should reflect whether the application can actually serve workload. For a service that depends on Kafka to receive or send events, you can check `describeCluster()` or a bounded-timeout metadata operation before marking the dependency ready.

Avoid running a heavy probe on every health request. A health indicator should use a short timeout, avoid creating new AdminClients repeatedly, and avoid letting a Kafka outage hang the health endpoint. You can cache the check result for a short interval and report `UP` or `DOWN` with a concise, sanitized cause.

Distinguish readiness from liveness:

- **Readiness:** whether the application can accept traffic or process events yet; a Kafka dependency issue may make an instance unready.
- **Liveness:** whether the process is alive and capable of self-recovery. Do not restart repeatedly just because Kafka temporarily loses connectivity if the application is designed to retry and recover.

If using Spring Boot Actuator, inspect the health endpoint and the actual contributors configured in the application. A passing Kafka health indicator does not replace a smoke test sending and receiving through the real runtime topic, group, and principal.

## 9. Producer and consumer smoke test

Once brokers and metadata are reachable, run a smoke test against a test topic:

1. Use the real runtime credentials to publish a record with a unique correlation ID.
2. Wait for the `KafkaTemplate.send()` future to complete within a timeout.
3. Use a test consumer group to read the record and verify its key, payload, and partition.
4. Confirm that the consumer group can commit offsets if the application needs to commit.
5. Record the cluster, topic, partition, timestamp, and outcome; avoid logging sensitive payloads.

This smoke test verifies the broker protocol, serialization, ACLs, producer, and consumer together. Use a dedicated topic/group so production data and offsets remain unaffected.

## 10. Common errors and investigation steps

| Symptom | First things to check |
| --- | --- |
| `UnknownHostException` | DNS, hostnames in the bootstrap list, and advertised.listeners. |
| `Connection refused` | Broker listener, port, service endpoint, and firewall rules. |
| `TimeoutException` after fetching metadata | Advertised broker endpoints, network routes from pod/host to every broker, and broker load. |
| Repeated `DisconnectException` | TCP/TLS, proxy/load balancer, idle timeouts, and broker logs. |
| `SSLHandshakeException` | CA, truststore, certificate hostname, and certificate validity period. |
| `SaslAuthenticationException` | Credentials, JAAS config, SASL mechanism, and broker listener. |
| `TopicAuthorizationException` | Principal ACLs on the topic. |
| `GroupAuthorizationException` | `READ` ACL on the consumer group. |
| Topic missing or partition lacks a leader | Topic provisioning, metadata, controller, and broker status. |

When investigating, record the bootstrap address used, the broker endpoints received from metadata, the root exception, the timestamp, and the client ID. Never write passwords, JAAS strings, tokens, or private keys into logs.

## 11. Operations checklist

- Provide at least two bootstrap endpoints matching the cluster's topology and HA policy.
- Test DNS and TCP from the exact host/container/pod running the application.
- Verify that `advertised.listeners` returns hostnames and ports reachable from the workload.
- Verify TLS certificates, truststore, SASL mechanism, and credentials.
- Use Kafka CLI with the same security properties to verify brokers, topics, and groups.
- Check the cluster ID, broker nodes, and controller with AdminClient when deeper diagnostics are needed.
- Verify topics, partition leaders, replicas/ISR, and consumer group offsets.
- Put bootstrap servers and secrets into environment configuration or a secret manager.
- Configure readiness timeouts and smoke tests; do not confuse a TCP check with Kafka health.
- Log diagnostic details carefully without exposing credentials.

Checking brokers and bootstrap servers requires verifying both initial endpoints and the brokers advertised by the cluster in metadata. Combining DNS/TCP, TLS/SASL, Kafka CLI, AdminClient, and a smoke test with the actual runtime principal isolates failures from network up to ACLs and avoids falsely assuming Kafka is ready just because one port is open.

## References

- [Kafka Producer Configs - bootstrap.servers](https://kafka.apache.org/documentation/#producerconfigs_bootstrap.servers)
- [Kafka Broker Configs - listeners and advertised.listeners](https://kafka.apache.org/documentation/#brokerconfigs_advertised.listeners)
- [Kafka AdminClient API](https://kafka.apache.org/documentation/#adminapi)
- [Spring Boot Kafka support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
