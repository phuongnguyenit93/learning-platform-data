# Cannot Connect to Broker

When a Spring Kafka application cannot connect to a Kafka broker, you need to determine at which step the failure occurs: address resolution, opening a TCP connection, receiving cluster metadata, TLS/SASL handshaking, or performing a Kafka operation. A syntactically valid `bootstrap.servers` address is not enough to guarantee that the application can reach the entire cluster. After connecting to the bootstrap broker, the Kafka client receives metadata containing advertised broker addresses and may open connections to other brokers to send to or read from partition leaders.

Therefore, diagnosis should proceed in order: **confirm the endpoint from the exact application runtime environment → check DNS/TCP → check `advertised.listeners` → check protocol and security → verify producer, consumer, and AdminClient → check topic/group permissions**. A layered approach helps avoid changing security or timeout configurations when the actual root cause is simply a wrong hostname or port.

## 1. Understanding the Kafka Connection Path

Spring Kafka uses the Kafka Java client. The producer, consumer, and AdminClient all need to connect to brokers, though the purpose and timing of connection creation may differ.

```text
Spring Boot application
    |
    +---- KafkaTemplate / ProducerFactory
    |
    +---- @KafkaListener / ConsumerFactory
    |
    +---- KafkaAdmin / AdminClient
              |
              v
       bootstrap.servers
              |
              v
        Bootstrap broker
              |
              | Metadata: broker IDs, endpoints,
              | topic partitions, leaders
              v
        Kafka cluster
          /    |    \
         v     v     v
      Broker Broker Broker
         \     |     /
          Partition leaders
```

`bootstrap.servers` is the initial list of addresses for the client to discover the cluster. It is not the only list of addresses the client will connect to throughout its lifecycle. After receiving metadata, the client uses the advertised broker endpoints to connect to the appropriate coordinator or partition leader.

A common failure mode is that the bootstrap broker is reachable, yet the hostname in `advertised.listeners` cannot be resolved or reached from the application environment. In that case, the client partially initializes, but produce/fetch still fails.

## 2. Distinguishing Failure Layers

| Layer | Question | Error examples |
| --- | --- | --- |
| Endpoint configuration | Is there a valid broker address? | `No resolvable bootstrap urls given` |
| DNS | Does the hostname resolve from the runtime? | `UnknownHostException` |
| TCP/network | Can a socket be opened to the host and port? | `Connection refused`, timeout, `DisconnectException` |
| Kafka metadata | Does the client receive valid metadata and endpoints? | Node not found, metadata request timeout |
| Listener protocol | Is that port the right Kafka listener? | Connecting plaintext to an SSL port or vice versa |
| TLS | Are the certificate chain and hostname valid? | `SSLHandshakeException`, `PKIX path building failed` |
| SASL authentication | Are the credentials and mechanism correct? | `SaslAuthenticationException` |
| Authorization | Does the principal have topic/group permissions? | `TopicAuthorizationException`, `GroupAuthorizationException` |
| Application behavior | Are the producer/consumer actually performing operations? | Send future fails, listener receives no records |

Not every error appearing in Kafka logs is a network error. For example, `TopicAuthorizationException` indicates the client got far enough for the broker to reject access; increasing timeouts or changing ports will not solve an ACL error.

## 3. First Step: Confirm bootstrap.servers

Check the actual configuration loaded when the application runs, not just the `application.yml` file in source control. Profiles, environment variables, command-line arguments, or secrets/ConfigMaps can override default values.

Spring Boot configures bootstrap servers with:

```yaml
spring:
  kafka:
    bootstrap-servers: broker-1.example.net:9092,broker-2.example.net:9092
```

Points to verify:

- The hostname matches the environment where the application is running.
- The port is the right Kafka listener, not confused with JMX, controller, HTTP proxy, or another service's port.
- The list is properly comma-separated and does not include URL schemes such as `http://`.
- Do not use `localhost` unless the broker runs in the same network namespace as the application.
- Do not mix plaintext, SSL, and SASL_SSL endpoints in the same list if the client is only configured for one protocol.
- The active profile actually loads the expected values.

If using an environment variable:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
```

Verify that this variable exists inside the process/container/pod. A variable present on a developer's machine does not automatically appear inside a Docker container or Kubernetes pod.

## 4. Check DNS from the Exact Application Runtime Environment

A hostname might resolve on the host machine but fail to resolve inside a container or pod. Run the check from the same network environment as the application.

On Windows PowerShell:

```powershell
Resolve-DnsName broker-1.example.net
```

On Linux or inside a container:

```bash
getent hosts broker-1.example.net
```

If DNS fails:

- Check whether the hostname spelling and domain suffix are correct.
- Check which DNS server the container/pod is using.
- Check service discovery, namespace, and DNS search paths.
- With Kubernetes, verify the service name and namespace, for example `kafka-bootstrap.messaging.svc.cluster.local`.
- Do not arbitrarily replace the hostname with an IP address if TLS certificates or broker metadata require a specific hostname.

If DNS returns multiple addresses, check each endpoint and ensure every advertised broker is reachable.

## 5. Check TCP and Port

Successful DNS only proves the hostname resolves. Next, verify the TCP connection.

On Windows PowerShell:

```powershell
Test-NetConnection broker-1.example.net -Port 9092
```

Read the `TcpTestSucceeded` field. If it is `False`, inspect routing, firewalls, security groups, network policies, port mappings, and the broker-side listener.

On Linux:

```bash
nc -vz broker-1.example.net 9092
```

Common outcomes:

| Result | Possible meaning | How to handle |
| --- | --- | --- |
| Connection refused | Host is reachable, but no service is listening on the port or it is rejected | Check broker listener, port mapping, and service target |
| Connection timed out | Packets are dropped, route/firewall is wrong, or endpoint is unresponsive | Check network route, firewall, security group, and NetworkPolicy |
| No route to host | No network path or an intermediate device rejects traffic | Check subnet, gateway, route, and policy |
| TCP succeeded | Socket can be opened | Proceed to check Kafka protocol, TLS/SASL, and metadata |

A successful TCP test does not prove the Kafka protocol is right. For example, the port might be open, yet it is an SSL listener while the client is using PLAINTEXT; the Kafka handshake will fail.

## 6. Check advertised.listeners

`listeners` specifies the address/port the broker binds to receive connections. `advertised.listeners` specifies the endpoints the broker publishes in metadata for clients to use. These two settings serve different roles.

Example broker configuration in Docker:

```properties
listeners=INTERNAL://0.0.0.0:29092,EXTERNAL://0.0.0.0:9092
advertised.listeners=INTERNAL://kafka:29092,EXTERNAL://localhost:9092
listener.security.protocol.map=INTERNAL:PLAINTEXT,EXTERNAL:PLAINTEXT
inter.broker.listener.name=INTERNAL
```

In this example:

- Other containers on the same Docker network connect to `kafka:29092`.
- Applications running on the host machine connect to `localhost:9092`.
- The broker advertises the endpoint corresponding to the listener the client used.

Do not configure a broker to advertise `localhost:9092` to an application running in another container. `localhost` inside a container refers to the application container itself, not the broker container.

A classic symptom: `Test-NetConnection` to the bootstrap port succeeds, logs show the client received metadata, and then an error appears trying to connect to another hostname. Read the hostname/port in the `Connection to node ... could not be established` log and compare it with `advertised.listeners`.

## 7. Bootstrap Broker vs. Broker Endpoints After Metadata

Suppose the configuration is:

```yaml
spring:
  kafka:
    bootstrap-servers: kafka-bootstrap:9092
```

The bootstrap broker returns metadata containing three brokers:

```text
broker 1 -> kafka-1.internal:9092
broker 2 -> kafka-2.internal:9092
broker 3 -> kafka-3.internal:9092
```

The application must still resolve and connect to those required endpoints. If only `kafka-bootstrap` is reachable while `kafka-1.internal` is unreachable from the application subnet, the client will not be able to produce/fetch reliably.

Therefore, verify all advertised broker addresses, not just one bootstrap endpoint. In cloud or Kubernetes environments, make sure DNS/service routing and firewalls allow the client to reach the required broker endpoints.

## 8. Docker Compose: localhost and Network Alias Pitfalls

In Docker Compose, the service name is typically used as the hostname between containers on the same network:

```yaml
services:
  kafka:
    image: apache/kafka:latest
    ports:
      - "9092:9092"
    # The broker must advertise appropriate listeners for both
    # containers in the network and clients on the host.

  order-service:
    build: .
    environment:
      KAFKA_BOOTSTRAP_SERVERS: kafka:29092
    depends_on:
      - kafka
```

The Compose snippet above only illustrates service discovery; actual listener configuration depends on the Kafka image and how the broker is initialized. `depends_on` does not guarantee Kafka is ready to accept requests; it mainly coordinates container startup order unless an appropriate healthcheck/condition is configured.

Common mistakes:

- An application inside a container uses `localhost:9092` instead of the service name `kafka:29092`.
- The broker only advertises the host endpoint `localhost`, making it unreachable from containers.
- The port published to the host is right, but the internal container port differs.
- The application starts before the broker finishes startup.
- The broker and application are on two different Docker networks.

Use internal endpoints for container-to-container traffic and external endpoints for clients running outside Docker. Do not assume a single address works for every network.

## 9. Kubernetes: Service DNS, Pod Endpoints, and NetworkPolicy

In Kubernetes, applications often bootstrap through Service DNS. However, Kafka brokers can return metadata containing per-broker endpoints. These endpoints must also be reachable from the application pod.

Check from inside the pod:

```bash
kubectl exec -n app deploy/order-service -- \
  getent hosts kafka-bootstrap.messaging.svc.cluster.local
```

Check TCP from the pod using a tool available in the image or an ephemeral debug container:

```bash
kubectl exec -n app deploy/order-service -- \
  nc -vz kafka-0.kafka-brokers.messaging.svc.cluster.local 9092
```

Verify:

- The Service selector points to the right broker pods.
- The Headless Service and per-broker DNS work if the cluster requires them.
- Kafka `advertised.listeners` returns hostnames/ports that application pods can resolve.
- `NetworkPolicy` allows egress from the application namespace to the broker ports.
- Node firewalls/security groups or managed Kafka rules allow the traffic.
- TLS certificate SANs match the DNS names advertised by Kafka metadata.
- Service `port` and `targetPort` are not mixed up.

Do not use static pod IPs as bootstrap endpoints when the platform provides stable service discovery. Pod IPs can change whenever a broker restarts or is rescheduled.

## 10. Verify the Broker Is Running and Listeners Bind Properly

On the broker side, check:

- The broker process/container/pod is healthy.
- Kafka startup logs have no port bind, listener configuration, or storage errors.
- `listeners` binds to an interface that can accept connections from the required networks; binding `127.0.0.1` only accepts loopback connections.
- The actual port matches the endpoint the client uses.
- `listener.security.protocol.map` maps the listener name to the right protocol.
- `advertised.listeners` does not use an internal hostname that clients cannot reach.
- In a multi-broker cluster, all brokers have valid endpoints and certificates.

Verification commands depend on how Kafka is deployed. With Docker:

```bash
docker ps
docker logs kafka
```

With Kubernetes:

```bash
kubectl get pods -n messaging
kubectl get svc -n messaging
kubectl logs -n messaging kafka-0
```

A container in the `Running` state does not mean Kafka is ready. Read the startup logs and use a health/readiness check appropriate for the Kafka listener.

## 11. Check Listener Protocol: PLAINTEXT, SSL, or SASL_SSL

The port must match the protocol configured on the client. For example:

| Broker listener | Client `security.protocol` |
| --- | --- |
| PLAINTEXT | `PLAINTEXT` |
| SSL | `SSL` |
| SASL_PLAINTEXT | `SASL_PLAINTEXT` |
| SASL_SSL | `SASL_SSL` |

Spring Boot configures the protocol via Kafka properties:

```yaml
spring:
  kafka:
    properties:
      "[security.protocol]": SSL
```

If a client uses `PLAINTEXT` to connect to an SSL port, or uses `SSL` to connect to a plaintext port, the handshake will fail. Confirm the listener/port provided by the Kafka operations team instead of trying protocols at random.

With multiple listeners on a broker, `listener.security.protocol.map` must map each listener name to the corresponding protocol. For inter-broker communication, `inter.broker.listener.name` also needs to point to the appropriate listener.

## 12. Diagnosing TLS Certificates

If TCP opens but the TLS handshake fails, check the trust chain, certificate validity period, and hostname verification.

Common client TLS settings:

```yaml
spring:
  kafka:
    properties:
      "[security.protocol]": SSL
      "[ssl.truststore.location]": ${KAFKA_TRUSTSTORE_LOCATION}
      "[ssl.truststore.password]": ${KAFKA_TRUSTSTORE_PASSWORD}
      "[ssl.truststore.type]": PKCS12
      "[ssl.endpoint.identification.algorithm]": https
```

Common errors:

- `PKIX path building failed`: the truststore is missing the CA or intermediate certificate.
- `No subject alternative DNS name matching`: the connected hostname is missing from the certificate's SANs.
- `Keystore was tampered with, or password was incorrect`: wrong password or wrong keystore type.
- `UnrecoverableKeyException`: invalid private key password or key entry.
- Certificate expired/not yet valid: expired certificate or skewed system clock.

Do not disable hostname verification to bypass SAN errors. Fix the certificate or the advertised endpoint so they match. If using mTLS, also verify the client keystore, private key, and whether the broker truststore trusts the client's CA.

You can test TLS independently with:

```bash
openssl s_client -connect broker-1.example.net:9093 \
  -servername broker-1.example.net -showcerts
```

This command lets you observe the certificate chain and handshake; it does not fully verify the Kafka protocol or SASL authentication.

## 13. Diagnosing SASL Authentication

If the cluster uses SASL, verify the mechanism, username/password or token, and JAAS/callback configuration.

Example SASL SCRAM over TLS:

```yaml
spring:
  kafka:
    properties:
      "[security.protocol]": SASL_SSL
      "[sasl.mechanism]": SCRAM-SHA-512
      "[sasl.jaas.config]": org.apache.kafka.common.security.scram.ScramLoginModule required username="${KAFKA_USERNAME}" password="${KAFKA_PASSWORD}";
      "[ssl.truststore.location]": ${KAFKA_TRUSTSTORE_LOCATION}
      "[ssl.truststore.password]": ${KAFKA_TRUSTSTORE_PASSWORD}
```

Check:

- Whether `sasl.mechanism` matches the mechanism enabled on the broker.
- Whether credentials belong to the right cluster/environment and have not expired.
- Whether the JAAS config has proper syntax, quotes, and trailing semicolon.
- For OAuth, whether the callback handler and token provider can reach the token endpoint.
- For `SASL_SSL`, the truststore and hostname verification must still be valid.

`SaslAuthenticationException` is typically an authentication error, not a TCP error. Do not put passwords/tokens into logs for debugging; logging the mechanism name and exception class is enough for initial isolation.

## 14. Distinguishing Authentication from Authorization

Once TLS/SASL succeeds, the broker can still reject operations due to ACLs.

| Exception | Common meaning | What to check |
| --- | --- | --- |
| `SaslAuthenticationException` | SASL authentication failed | Credentials, mechanism, JAAS/token |
| `TopicAuthorizationException` | Principal lacks topic permission | `READ`/`WRITE`/`DESCRIBE` ACLs on the topic |
| `GroupAuthorizationException` | Principal lacks consumer group permission | Corresponding group ACLs |
| `TransactionalIdAuthorizationException` | Lacks transactional ID permission | Transactional ID ACL for transactional producer |

Do not grant `superuser` or broad permissions across all topics just to make errors disappear. Grant least-privilege permissions to the service according to its role as producer, consumer, or transactional producer.

## 15. Verifying with Kafka Command-Line Tools

If Kafka CLI tools are available in an environment that can reach the cluster, use `kafka-broker-api-versions` to verify bootstrap and metadata:

```bash
kafka-broker-api-versions.sh \
  --bootstrap-server broker-1.example.net:9092
```

For SSL/SASL clusters, pass a client configuration file:

```bash
kafka-broker-api-versions.sh \
  --bootstrap-server broker-1.example.net:9093 \
  --command-config client.properties
```

Inspect topic metadata:

```bash
kafka-topics.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --describe --topic orders.created
```

If the CLI works from the same environment while the Spring app does not, compare exact bootstrap servers, protocol, truststore, SASL mechanism, principal, and overrides in Spring profiles. If the CLI also fails, focus on endpoints, network, or the broker.

## 16. Checking Each Kafka Client in Spring Boot

An application may use different configurations for the producer, consumer, and admin client. Example shared configuration:

```yaml
spring:
  kafka:
    bootstrap-servers: broker-1.example.net:9092,broker-2.example.net:9092
    properties:
      "[security.protocol]": PLAINTEXT
    producer:
      properties:
        "[client.id]": order-service-producer
    consumer:
      group-id: order-service-consumer
      properties:
        "[client.id]": order-service-consumer
    admin:
      fail-fast: true
```

This is a generic example for a plaintext environment. Production typically requires SSL/SASL and corresponding secrets. `KafkaAdmin` may connect at application startup to inspect/create topics depending on configuration; if `fail-fast` is enabled, admin errors can fail startup early.

If the producer sends successfully but the listener receives nothing, check separately:

- Consumer bootstrap servers and security properties.
- Consumer group ID and group ACLs.
- Topic subscription and whether the topic exists.
- Whether the deserializer initializes properly.
- Partition assignment and consumer lag.

If the consumer runs while the producer fails, inspect the producer factory, serializer, topic write ACL, and `KafkaTemplate` callback/future.

## 17. Application Starts Up While Kafka Is Not Ready

Not every Kafka client opens connections immediately when the Spring context is created. A producer can be created lazily and only connect when sending; a listener container can retry connections at runtime; `KafkaAdmin` may perform operations at startup depending on configuration.

Therefore, the application reporting `Started` does not mean the broker connected successfully. Conversely, a single connection error logged while the broker is starting up is not necessarily a persistent failure if the client reconnects afterward.

Distinguish between:

- **Startup failure:** context fails to start due to `KafkaAdmin` or listener fail-fast.
- **Transient connection failure:** broker is not ready yet or network is flaky; the client will reconnect.
- **Persistent connection failure:** endpoint, DNS, protocol, or security is misconfigured.
- **Operation failure:** client connects, but send/fetch/metadata/authorization fails.

Application readiness should reflect business requirements. If the service cannot serve traffic when Kafka is unavailable, health/readiness should reflect that. If the application can start and retry while the broker recovers, do not turn a transient failure into a crash loop just because the first connection attempt failed.

## 18. Timeouts and Reconnects: Tune Only After Finding the Root Cause

The Kafka client has reconnect and retry mechanisms. Related properties include:

| Property | Role |
| --- | --- |
| `reconnect.backoff.ms` | Base wait interval between reconnect attempts |
| `reconnect.backoff.max.ms` | Upper bound on reconnect backoff |
| `socket.connection.setup.timeout.ms` | Time limit to establish a socket connection |
| `socket.connection.setup.timeout.max.ms` | Upper bound for connection setup timeout with backoff |
| `request.timeout.ms` | Time to wait for a response to a single request |
| `default.api.timeout.ms` | Default timeout for APIs that take a timeout |

Do not raise all timeouts to several minutes to mask bad DNS or `advertised.listeners`. Large timeouts can make the application slower to detect outages. Fix endpoints and networking first; only then tune reconnect/backoff according to fault-tolerance requirements.

For the producer, distinguish timeouts while `send()` is waiting for metadata/buffer (`max.block.ms`) from future failures after the record has been accepted into the send pipeline (`delivery.timeout.ms`). For the consumer, inspect the poll loop and rebalances separately rather than inferring from producer timeouts.

## 19. Ordered Diagnostic Workflow

Follow these steps in order to narrow the scope:

1. **Confirm runtime configuration:** capture the actual `bootstrap.servers`, active profiles, environment variables, and security protocol; redact passwords/secrets when logging.
2. **Check DNS:** resolve each bootstrap hostname from the container/pod/process running the application.
3. **Check TCP:** test each hostname/port; note whether it is refused, timed out, or succeeded.
4. **Check broker listeners:** confirm the broker binds the port and the listener uses the right protocol.
5. **Check metadata:** use Kafka CLI or client logs to view the advertised broker endpoints.
6. **Check advertised listeners:** test DNS/TCP to every broker endpoint that must be reached.
7. **Check TLS/SASL:** verify CA, SANs, keystores, mechanism, and credentials.
8. **Check authorization:** verify topic/group/transactional ID ACLs.
9. **Check each client:** producer, consumer, and AdminClient have matching configurations.
10. **Check end-to-end operations:** publish a test record, consume with a test group, and observe send results/lag.

Record the timestamp, hostname, port, broker node ID, exception class, and client ID. Those details are enough for the operations team to locate the right broker and logs without sharing credentials.

## 20. Common Error and Resolution Table

| Log/symptom | Possible cause | How to handle |
| --- | --- | --- |
| `No resolvable bootstrap urls given` | Bootstrap list is empty or malformed | Check runtime property, delimiters, and hostnames |
| `UnknownHostException` | DNS fails to resolve | Check DNS from the exact container/pod and service name |
| `Connection refused` | Broker is not listening on the port or wrong port mapping | Check broker process, listener, and port |
| `Connection timed out` | Firewall, route, security group, or network policy drops packets | Check bidirectional network path and policies |
| `Connection to node -1 could not be established` | Bootstrap endpoint is unreachable | Check bootstrap hostname/port, broker startup, and protocol |
| Bootstrap succeeds but another node fails | `advertised.listeners` returns an endpoint the client cannot reach | Check metadata and each broker's advertised host/port |
| `SSLHandshakeException` | TLS protocol, trust chain, SAN, or certificate error | Check truststore, certificate chain, and hostname verification |
| `PKIX path building failed` | Client does not trust the CA that signed the broker certificate | Add the right CA/intermediate to the truststore |
| `SaslAuthenticationException` | Wrong credentials or SASL mechanism | Check username/password/token and mechanism |
| `UnsupportedSaslMechanismException` | Client uses a mechanism not enabled on the broker | Align `sasl.mechanism` with the broker |
| `TopicAuthorizationException` | Principal lacks topic permission | Check `READ`/`WRITE`/`DESCRIBE` ACLs |
| `GroupAuthorizationException` | Principal lacks consumer group permission | Check group ACLs |
| Producer sends, listener does not receive | Consumer config, group, subscription, or deserialization error | Check consumer logs, assignment, lag, and deserializer |
| App reports started but cannot send yet | Producer has not actually connected yet or async send fails | Observe future/callback and run a smoke test |

## 21. Connection Smoke Test After Fixing

Once endpoints and security are right, verify the real flow with a test topic:

1. Use Kafka CLI to inspect broker metadata from the application environment.
2. Create or verify a test topic with appropriate partitions.
3. Send a record with a unique key/event ID using a test producer.
4. Wait for the `KafkaTemplate.send()` future to complete and check `RecordMetadata`.
5. Consume the record with a test consumer group using the matching deserializer.
6. Verify key, payload, headers, and partition.
7. Check consumer lag/offset to confirm the record was read.
8. Repeat for the application's own producer, consumer, and AdminClient if they use separate factories/configs.

Do not rely solely on `nc` or `Test-NetConnection` as proof that the application connects to Kafka. Those commands only test TCP; a Kafka smoke test verifies metadata, protocol, authentication, and produce/consume operations.

## 22. Logging and Observability

During investigation, gather useful context without exposing secrets:

- Kafka bootstrap hostname/port and active profile.
- Kafka client ID, group ID, and broker node ID.
- Exception class, root cause, and timestamp.
- Producer send rate/error rate and request latency.
- Consumer connection status, assignment, lag, and rebalance count.
- TLS certificate subject/SAN/expiry if the issue is certificate-related; never log private keys.
- Recent broker listener or network policy changes around the time of the error.

You can temporarily enable Kafka client `DEBUG` logging in test environments or during a controlled investigation window. `DEBUG` can generate high log volume and contain sensitive metadata; do not leave it enabled long-term in production without evaluation.

## 23. Prevention Checklist

- [ ] `bootstrap.servers` comes from runtime configuration for the right environment.
- [ ] Hostname and port are reachable from where the application runs.
- [ ] Every broker endpoint in metadata resolves and connects.
- [ ] `listeners` binds to the appropriate interface.
- [ ] `advertised.listeners` publishes endpoints valid for the client's network.
- [ ] Docker/Kubernetes services, port mappings, and `NetworkPolicy` rules are verified.
- [ ] `security.protocol` matches the listener.
- [ ] TLS truststore, SANs, hostname verification, and mTLS are properly configured if required.
- [ ] SASL mechanism and credentials are valid if using SASL.
- [ ] Topic, group, and transactional ID ACLs follow least privilege.
- [ ] Producer, consumer, and AdminClient all use the right configuration.
- [ ] Produce/consume smoke tests and connection/lag monitoring are in place.
- [ ] Readiness/reconnect policy is appropriate when the broker is temporarily unavailable.

## 24. Conclusion

Broker connection failures must be diagnosed layer by layer: endpoint, DNS, TCP, metadata, advertised listener, protocol, TLS/SASL, and authorization. The most important principle is to test from the exact application runtime environment and verify every broker endpoint returned in metadata. One reachable bootstrap hostname does not guarantee that advertised brokers are also reachable.

In Spring Kafka, verify `spring.kafka.bootstrap-servers` and runtime properties, inspect producer/consumer/AdminClient separately, and use a Kafka smoke test to prove publish and consume actually work. Keep hostname verification enabled, never disable security to bypass errors, avoid overly broad ACLs, and only adjust timeouts after fixing network or listener root causes. With a clear DNS/TCP/metadata/security checklist, most connectivity incidents can be isolated quickly and resolved with confidence.

## References

- [Apache Kafka — Broker Configurations: Listeners](https://kafka.apache.org/documentation/#brokerconfigs_listeners)
- [Apache Kafka — Security](https://kafka.apache.org/documentation/#security)
- [Apache Kafka — Admin Client](https://kafka.apache.org/documentation/#adminapi)
- [Spring for Apache Kafka — Connecting to Kafka](https://docs.spring.io/spring-kafka/reference/kafka/connecting.html)
- [Spring Boot — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html)
