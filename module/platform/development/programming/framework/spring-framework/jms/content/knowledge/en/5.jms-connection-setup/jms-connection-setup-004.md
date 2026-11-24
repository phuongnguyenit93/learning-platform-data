# Broker Address, Credentials, and Connection Options in Spring JMS

## 1. Objectives and Connection Model

A Spring JMS application can only send or receive messages when it knows **which broker to connect to**, **which identity to authenticate with**, and **which policies to apply to the connection**. This is the infrastructure configuration for producers and consumers, independent of the message body and business processing logic.

~~~text
application.yml / environment variables / secret manager
       |  URL + username/password + TLS + retry + resource options
       v
Jakarta JMS ConnectionFactory (provider-specific)
       |
       +--> Spring JmsTemplate ---> Producer ---> broker
       |
       +--> Spring @JmsListener container ---> Consumer ---> broker
       |
       v
Network transport / authentication / authorization
       |
       v
Broker (e.g., Apache ActiveMQ Artemis)
       +--> Queues and Topics
       +--> routing, persistence, security, HA
~~~

Separate these terms clearly:

- **Broker URL**: the endpoint address the JVM must reach over the network, typically consisting of scheme, hostname/IP, port, and possibly provider-specific parameters.
- **Credential**: username/password or another authentication mechanism used to verify the application's identity to the broker.
- **Authorization**: permissions to send, receive, create, or browse destinations after authentication succeeds.
- **ConnectionFactory**: the `jakarta.jms.ConnectionFactory` object that supplies JMS connections, hiding provider and transport details.
- **Destination**: a Queue or Topic named something like `orders.commands`. This is not the broker's host/port address.
- **Connection options**: TLS, timeouts, retry/reconnect, caching/pooling, client ID, listener concurrency, transacted sessions, and provider-specific policies.

This lesson uses **Spring Boot 3.x, Spring Framework 6, Jakarta Messaging, and Apache ActiveMQ Artemis** to provide runnable examples. Configuration differs across Artemis, ActiveMQ Classic, IBM MQ, and other JMS providers; do not switch providers while keeping all properties unchanged.

## 2. Understanding the Broker URL Accurately

### 2.1. Address Structure

With the **Artemis JMS client** and TCP transport:

~~~text
tcp://localhost:61616
 |     |         |
 |     |         +-- broker acceptor port
 |     +------------ hostname/IP seen from the JVM
 +------------------ Artemis transport scheme
~~~

Environment examples:

| Where the Java app runs | Where the broker runs | Illustrative broker URL |
| --- | --- | --- |
| Java running on a developer machine | Artemis Docker publishing the JMS port | `tcp://localhost:61616` |
| Java in a container on the same Docker Compose network | Service named `artemis` | `tcp://artemis:61616` |
| Java running on a host in an internal network | Broker with internal DNS | `tcp://broker.internal.example:61616` |
| Java in Kubernetes | Broker with Service DNS | `tcp://artemis.messaging.svc.cluster.local:61616` |

**Very common mistake:** `localhost` inside a Java container points to **the Java container itself**, not the broker container or the host machine. The address must match where the program actually runs. If the broker is in another container on the same network, use the service name provided by Docker/Kubernetes or the corresponding endpoint.

Port `61616` is commonly used for Artemis messaging; port `8161` is typically the web management console. Successfully opening `http://localhost:8161` does not prove the JMS TCP listener on `61616` can accept JMS connections.

### 2.2. The Provider/Protocol Determines the Scheme and URI

JMS is a **standard Java API**, not a single wire protocol:

- The Artemis JMS client typically uses `tcp://host:port` with the corresponding Artemis Core client protocol/transport.
- An AMQP 1.0 client may require `amqp://` or `amqps://`; changing the URL prefix **does not** turn the Artemis JMS client into an AMQP provider.
- ActiveMQ Classic or IBM MQ have different URL/factory configurations and TLS/HA characteristics. When switching brokers, consult that provider's client library and documentation.
- Spring Boot 3 uses the `jakarta.jms.*` API. Legacy JMS client libraries that only implement `javax.jms.*` cannot directly stand in for Jakarta interfaces.

Before troubleshooting connection errors, verify all four: **broker implementation + client JAR + protocol/transport + network endpoint**.

### 2.3. Do Not Confuse the Broker URL with Queue/Topic Names

~~~properties
spring.artemis.broker-url=tcp://localhost:61616
~~~

~~~java
jmsTemplate.convertAndSend("orders.commands", "Create order O-42");
~~~

Here `localhost:61616` is the path to the broker. `orders.commands` is the JMS destination name, defaulting to a Queue when `JmsTemplate` is in queue mode. One broker can host many Queues and Topics. Permission to connect to the broker does not automatically grant send/receive rights on every destination.

If the broker disables Queue auto-creation, create the destination administratively before clients send to it. If an Artemis broker has custom routing configured, check the address/routing type rather than looking only at the Queue name.

## 3. Authentication, Authorization, and Secret Management

### 3.1. What Do Username/Password Protect?

When a client creates a JMS connection, the broker typically verifies the username/password. Then the broker checks that identity's **permissions** on the destination according to roles/ACLs.

| Case | How to interpret |
| --- | --- |
| Cannot establish TCP | Has not reached authentication yet |
| TCP succeeds, login rejected | Wrong credentials, authentication realm, or locked account |
| Login succeeds, send fails with `Not authorized` | Missing send/create permission or broker routing policy |
| Send succeeds, listener does not receive | Possible missing consume permission, wrong destination, selector, or Queue/Topic mode |
| TLS handshake error | Invalid certificate, CA/truststore, hostname, or TLS protocol; may not have reached login yet |

Each service should use a dedicated account with least privilege, such as only `send` on `orders.commands` and `consume` from `orders.results`. Do not use a broker admin account for business applications.

### 3.2. Spring Boot Reading Credentials from Externalized Configuration

In `application.properties`, you can write:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
spring.artemis.user=${JMS_BROKER_USER:demo}
spring.artemis.password=${JMS_BROKER_PASSWORD:demo}
~~~

The `${KEY:default}` form uses Spring placeholder syntax `${KEY:default}` in the actual configuration file. In **local exercises**, `demo/demo` is a test account; in production deployments, remove credential fallbacks and supply user/password via a secret manager or platform-managed environment variables. Never commit real passwords to the repository.

Example in **PowerShell**:

~~~powershell
$env:JMS_BROKER_URL = "tcp://localhost:61616"
$env:JMS_BROKER_USER = "demo"
$env:JMS_BROKER_PASSWORD = "demo"
gradle bootRun
~~~

Example in **Bash**:

~~~bash
export JMS_BROKER_URL='tcp://localhost:61616'
export JMS_BROKER_USER='demo'
export JMS_BROKER_PASSWORD='demo'
gradle bootRun
~~~

Lines using the `demo` password apply only to a learning broker. Never place credentials in Git, issues, public docs, CLI audit trails, or logs. Secrets in environment variables still carry exposure risk via process inspection privileges and operational tooling; proper access control and secret lifecycle management remain necessary.

### 3.3. Changing Passwords While the Application Is Running

Updating a secret in a secret store does not mean an already-established JMS connection automatically switches login identities. Depending on the provider and factory configuration, an existing connection may keep running with the old credentials until a reconnect, or the next reconnect might reuse cached values if the factory has not been reconfigured.

Therefore, follow a secret rotation procedure: provision new credentials, update the application environment, recycle connections / restart instances on schedule, verify send/receive, and then revoke old credentials. Never log both old and new passwords for "debugging."

## 4. Key Spring Boot/Artemis Properties

With the `spring-boot-starter-artemis` dependency, Spring Boot can auto-configure an Artemis `ConnectionFactory`, `JmsTemplate`, and listener factory. When not using JNDI or a custom `ConnectionFactory` bean, the properties below are usually enough to start.

| Setting | Purpose | Notes |
| --- | --- | --- |
| `spring.artemis.mode=native` | Connect to an external broker | Does not start an embedded broker |
| `spring.artemis.broker-url` | Artemis connection URI | Must match the network namespace and port |
| `spring.artemis.user` | Broker username | Provide via secret injection |
| `spring.artemis.password` | Broker password | Never hardcode in production |
| `spring.jms.pub-sub-domain` | Queue when `false`; Topic when `true` | Producer and listener must use the matching domain |
| `spring.jms.cache.enabled` | Boot's JMS session/resource caching | Typically enabled by default |
| `spring.jms.cache.session-cache-size` | Session cache size | Not the count of network connections |
| `spring.jms.listener.auto-startup` | Auto-start listeners | Typically enabled by default |
| `spring.jms.listener.min-concurrency` | Minimum concurrent listeners | Consumes additional sessions/consumers |
| `spring.jms.listener.max-concurrency` | Maximum concurrent listeners | Must suit Queue vs. durable Topic semantics |
| `spring.jms.client-id` | Client ID on the JMS connection | Set only when needed; watch for duplicates when scaling |
| `spring.jms.jndi-name` | Look up factory from JNDI | When set, favors JNDI over Artemis auto-configuration |
| `spring.artemis.pool.enabled` | Enable pooled JMS connection factory when dependency is present | Test lifecycle and limits |
| `spring.artemis.pool.max-connections` | Maximum pooled connections | Does not mean one connection per request |

**Layering:** `spring.artemis.*` configures the provider; `spring.jms.*` configures Spring JMS integration. Check property name changes between Spring Boot versions against the official docs for your exact version.

## 5. Runnable Example: Artemis + Spring Boot 3.x + Java 17

Goal: from Spring code, send a message to a Queue and have a listener receive it. A send–receive test is far more meaningful than checking a TCP port or seeing the application start up.

### 5.1. Starting Local Artemis

The machine needs Docker. Example using the official Apache Artemis image and publishing ports only to the loopback interface:

~~~bash
docker run --detach --rm --name artemis-connect-lab -p 127.0.0.1:61616:61616 -p 127.0.0.1:8161:8161 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:2.57.0
~~~

Wait for the broker to finish starting, then inspect logs:

~~~bash
docker logs artemis-connect-lab
~~~

This container is only for learning; when removed, data is not guaranteed to persist without a mounted persistent volume. Artemis usually allows Queue auto-creation in sample setups. If the broker enforces stricter policies, pre-create Queue `connectivity.demo` and grant send/consume permissions.

### 5.2. Gradle Project

`settings.gradle`:

~~~groovy
rootProject.name = 'spring-jms-connection-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

These versions are pinned so the example stays consistent; in real systems, use a Spring Boot maintenance/security release supported by your organization. Spring Boot 3.x requires a compatible Jakarta JMS client.

`src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
spring.artemis.user=${JMS_BROKER_USER:demo}
spring.artemis.password=${JMS_BROKER_PASSWORD:demo}
spring.jms.pub-sub-domain=false
spring.jms.cache.enabled=true
spring.jms.cache.session-cache-size=5
spring.jms.listener.auto-startup=true
spring.jms.listener.min-concurrency=1
spring.jms.listener.max-concurrency=1
~~~

In the rendered Markdown, placeholders begin with `$` and follow Spring's `${NAME:default}` syntax. `pub-sub-domain=false` means the example uses a Queue.

### 5.3. Main Class and Enabling Listeners

`src/main/java/demo/jms/ConnectivityApplication.java`:

~~~java
package demo.jms;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class ConnectivityApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConnectivityApplication.class, args);
    }
}
~~~

Spring automatically provides `ConnectionFactory` and `JmsTemplate` from the starter and external properties. For this example, do not manually construct `ActiveMQConnectionFactory`; adding one can inadvertently disable auto-configuration.

### 5.4. Producer Using ConnectionFactory Indirectly

`src/main/java/demo/jms/PingPublisher.java`:

~~~java
package demo.jms;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
public class PingPublisher implements ApplicationRunner {

    private final JmsTemplate jmsTemplate;

    public PingPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @Override
    public void run(ApplicationArguments args) {
        jmsTemplate.convertAndSend("connectivity.demo", "ping-001");
        System.out.println("SENT: ping-001");
    }
}
~~~

`convertAndSend` converts the `String` into a `TextMessage` via Spring's converter and sends it to the Queue. When connection creation, login, or sending fails, Spring typically throws a `JmsException` wrapping the underlying provider cause. `SENT` only prints after the send method returns normally.

### 5.5. Listener Verifying Receive Permissions

`src/main/java/demo/jms/PingReceiver.java`:

~~~java
package demo.jms;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class PingReceiver {

    @JmsListener(destination = "connectivity.demo")
    public void onPing(String body) {
        System.out.println("RECEIVED: " + body);
    }
}
~~~

With a Queue, a message sent before the listener is ready usually waits in the queue per broker policy. Thus, this exercise does not depend on a non-durable Topic subscription being online at the exact moment of publishing.

### 5.6. Running and Checking Results

~~~bash
gradle bootRun
~~~

If using the project's Gradle wrapper, run `./gradlew bootRun` in Bash or `.\gradlew.bat bootRun` on Windows. JDK 17+ and a Gradle version compatible with the selected plugins are required.

When the broker is reachable, credentials are valid, the Queue is allowed, and producer/consumer permissions are set, the log will include:

~~~text
SENT: ping-001
RECEIVED: ping-001
~~~

**The order of the two lines may be swapped** because the listener runs on another thread. Spring/Artemis also print framework logs. This is the expected output under normal conditions; network errors, auth failures, or an unstarted broker will not guarantee both lines appear.

Running the app again sends another new JMS message with the same `ping-001` **body**. If multiple consumers/services listen on the same Queue, only one consumer handles that delivery; stop other apps when you want deterministic observation.

Stop the broker after practicing:

~~~bash
docker stop artemis-connect-lab
~~~

## 6. CachingConnectionFactory and Pooling

Most applications need to **reuse JMS resources**:

~~~text
ConnectionFactory -> Connection -> Session -> Producer/Consumer
~~~

Creating and closing a new Connection/Session/Producer for every send can be expensive. Spring Boot commonly wraps the provider factory in `CachingConnectionFactory` to cache JMS resources appropriately.

### 6.1. Default Caching

~~~properties
spring.jms.cache.enabled=true
spring.jms.cache.session-cache-size=5
~~~

Key points:

- `session-cache-size=5` limits cached **Sessions** per session/acknowledgement mode, **not** the number of forced broker connections.
- Producer/session caching can speed up consecutive `JmsTemplate` sends.
- Listener containers manage their own resource lifecycles. Do not assume each listener thread uses exactly one session from this cache.
- Carelessly setting `client ID`, consumer caching, or session reuse alongside durable subscriptions can cause identifier conflicts or unexpected resource retention.

### 6.2. When `pooled-jms` Is Needed

When high load requires managing multiple concurrent connections/sessions, Spring Boot with Artemis supports pooling if you add the library:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
    implementation 'org.messaginghub:pooled-jms'
}
~~~

~~~properties
spring.artemis.pool.enabled=true
spring.artemis.pool.max-connections=8
~~~

This configuration **enables a bounded pool option**; it does not mean 8 connections are always open. When the pool is full, callers may block or fail per timeout policy; measure connection counts, session counts, throughput, latency, and broker quotas.

Do not wrap one connection factory in multiple layers of caching/pooling without clear lifecycle control. Increasing connection counts will not improve throughput if the bottleneck is the DB, listener logic, or broker storage.

## 7. Timeouts, Dead-Connection Detection, and Retries

Connection errors can happen at several points:

1. Unable to connect at application startup.
2. Connected, but the broker/network drops mid-processing.
3. Broker restarts and old sessions are gone.
4. Failover to a backup broker with different session/transaction state.
5. Connection remains open, but heartbeat detects an unresponsive peer.

Distinguish **connect timeout**, **heartbeat/liveness timeout**, **initial connection retry**, **post-failure reconnect**, and **message receive timeout**. They are not one single parameter.

### 7.1. Artemis-Specific Reconnect Parameters

Example provider-specific Artemis broker URL:

~~~properties
spring.artemis.broker-url=tcp://localhost:61616?retryInterval=1000&reconnectAttempts=10
~~~

- `retryInterval`: base interval between reconnect attempts, in milliseconds.
- `reconnectAttempts`: number of reconnect attempts after losing a connection per Artemis's contract; `-1` typically means unlimited.
- `initialConnectAttempts` controls certain failure scenarios during the initial connection phase; do not confuse it with reconnect attempts after an established connection.
- `retryIntervalMultiplier` and `maxRetryInterval` support backoff and delay caps.

Test provider settings together with Spring's listener container recovery. Avoid aggressive infinite retries: if the broker is truly down or credentials are rejected, a retry storm adds load and clutters logs.

### 7.2. Heartbeat and Connection TTL

Artemis supports settings like:

~~~text
tcp://broker.internal:61616?connectionTTL=60000&clientFailureCheckPeriod=30000
~~~

`connectionTTL` (ms) is how long a connection can go without receiving data before being considered dead; `clientFailureCheckPeriod` governs ping/failure detection. These are **connection liveness options**, not **message time-to-live**. Message TTL must be set on the send/producer operation.

Network jitter, GC pauses, or slow VMs can cause overly short timeouts to trigger false disconnects. The broker may also enforce overrides; inspect server-side settings as well.

### 7.3. HA/Failover and Duplicates

A client can reconnect to the same or backup broker in an Artemis HA topology, but a client option like `ha=true` does not build an HA broker cluster by itself. If the connection drops during a producer send or consumer ACK, the application may not know for sure how far the broker committed. Reconnecting can lead to retries or redeliveries.

For important business messages, design **idempotency keys**, proper transactions/ACKs, backlog monitoring, and a DLQ. Connection recovery only restores the communication channel; it does not automatically guarantee end-to-end exactly-once semantics.

## 8. TLS and Securing the Connection

Username/password handle **authentication**, not encrypting data on the wire. Artemis supports TLS through transport configuration, for example:

~~~text
tcp://broker.internal.example:61617?sslEnabled=true;verifyHost=true;trustStorePath=/etc/jms/truststore.p12;trustStoreType=PKCS12
~~~

This pattern requires a matching TLS acceptor on the broker, a hostname matching the certificate, and a truststore containing the trusted CA/certificate.

- `sslEnabled=true`: enables TLS for the Artemis transport.
- `verifyHost=true`: verifies the connected hostname matches a valid SAN/CN on the certificate.
- `trustStorePath` / `trustStoreType`: location and format of trusted certificates.
- If the broker requires **mutual TLS**, the client must supply an issued keystore/certificate/private key and the server must be configured to verify client certificates.
- Truststore/keystore passwords and secret keys must be injected securely at runtime, never embedded as literal passwords in source or logged URLs.

**Never disable `verifyHost` or enable `trustAll` in production** to bypass handshake errors. Fix DNS/certificates, CA/truststore, expiration dates, and TLS protocols/ciphers to match.

Even inside trusted internal networks, TLS adds value: authenticating the broker prevents connecting to the wrong endpoint and encrypts messages that may contain sensitive business data.

## 9. Client ID, Listener Concurrency, and Destination Mode

Three settings commonly cause "connected fine, but listener behaves wrong":

**Client ID (`spring.jms.client-id`):**

- Client ID can identify a durable Topic subscription.
- For unshared durable subscriptions, two active consumers cannot simultaneously share the same identifier; horizontal scaling must design subscription identity properly.
- For ordinary Queues like in this lab, do not assign the same fixed client ID to every instance.

**Queue vs. Topic (`spring.jms.pub-sub-domain`):**

- `false`: destinations default to Queues.
- `true`: destinations default to Topics.
- Producer, listener factory, and broker routing must agree. A message sent to a Queue will not magically reach a Topic of the same name just because another consumer subscribed there.

**Listener concurrency:**

- `min-concurrency`/`max-concurrency` affect consumer/session counts and resource pressure.
- Queues can use competing consumers to share work; Topics have subscription semantics, especially unshared durable subscriptions.
- Tweaking concurrency cannot fix a wrong URL, wrong credentials, or a denied ACL.

## 10. Troubleshooting from the Outside In

### 10.1. Step 1: Verify the Network Endpoint

Windows PowerShell:

~~~powershell
Test-NetConnection localhost -Port 61616
~~~

Linux with netcat:

~~~bash
nc -vz localhost 61616
~~~

This only confirms the **TCP port is reachable**. This step **does not** verify the Artemis JMS handshake, auth, TLS certificate, ACLs, or ability to receive messages.

For a Docker broker:

~~~bash
docker ps
docker logs artemis-connect-lab
~~~

If Java runs inside a container/pod, test DNS, service ports, and network policies **from inside that container/pod**; testing from the host can give different results.

### 10.2. Step 2: Classify the Error

| Symptom | Common cause | How to check |
| --- | --- | --- |
| `Connection refused` | Wrong host/port, broker not listening, missing Docker port publish | Check broker logs, listeners, and actual URL |
| `Connect timed out` | Firewall, routing, network policy, unresponsive broker | Test TCP from the JVM's runtime environment |
| `UnknownHostException` | Wrong DNS/service name or different Docker network | Check DNS and application namespace |
| `Authentication failed` | Wrong secret, nonexistent user, wrong realm | Check secret version and broker auth |
| `Not authorized` on send | Logged in, but missing permission | Check destination send/create ACLs |
| Listener does not receive | Wrong Queue/Topic mode, destination, selector, or consume ACL | Match names/routing and receive permissions |
| `SSLHandshakeException` | Truststore/CA, SAN/hostname, cipher, TLS version | Check broker TLS acceptor and certificates |
| Works locally, fails in container | Used `localhost` inside the container | Use the broker's service name/endpoint |
| Duplicate clientId | Multiple instances sharing one fixed ID inappropriately | Design durable identity properly |
| Unusually many connections | Recreating factory repeatedly, pool/concurrency too high | Inspect bean lifecycle and broker metrics |
| Duplicate messages after reconnect | Ambiguous ACK/send at failure moment | Idempotency, transactions, redelivery metrics |
| Still fails after secret rotation | Client still using old credentials | Check instance restart/factory recreation and secret injection |

### 10.3. Step 3: Verify End-to-End

These milestones **cannot substitute for one another**:

1. TCP port is reachable.
2. JMS connection authenticates.
3. Producer successfully sends a message to a destination.
4. Consumer actually receives the message.
5. Business logic and ACK/transaction complete.

Seeing only "Started Application" without `SENT` and `RECEIVED` does not yet prove end-to-end JMS connectivity. Read the exception chain, broker logs, and available metrics; never print passwords to debug.

## 11. Common Operational Scenarios

### 11.1. Moving from Host to Docker Compose

On the host:

~~~properties
spring.artemis.broker-url=tcp://localhost:61616
~~~

Inside a container on the same network as an Artemis service named `artemis`:

~~~properties
spring.artemis.broker-url=tcp://artemis:61616
~~~

Same broker and same port, yet **the hostname must change** because the execution environment changed. In Kubernetes, use the corresponding Service DNS rather than ephemeral pod/container addresses that change on restart.

### 11.2. Different Credentials for Staging and Production

Even with the exact same JAR, use different usernames/secrets and endpoints per environment. During secret rotation, watch both **new connections** and **existing connections**, ensuring old users are not revoked before all instances have switched over.

### 11.3. HA Broker Still Produces Duplicate Sends

A retry when unsure whether the previous send succeeded can create a second message. Thus the issue is not necessarily "failed to reconnect"; it is transactional ambiguity. Design a stable `eventId` in payload/properties and idempotent processing to reduce the impact of duplicates.

### 11.4. Connected Successfully, Yet Backlog Keeps Growing

Check concurrency, listener processing time, ACK/transaction failures, consumer permissions, poison messages/DLQ, and broker quotas. Adding more connections will not help if consumers are slow due to a database or external dependency.

## 12. Configuration Verification Exercises

1. **Wrong login:** change only `JMS_BROKER_PASSWORD` to an invalid value, re-run, and confirm an authentication error occurs. Restore valid credentials to observe normal send–receive.
2. **Wrong port:** change the URL from `61616` to an unused port and observe the difference between a connection error and an authentication error.
3. **Wrong host in container:** change `tcp://artemis:61616` to `tcp://localhost:61616` in a standalone app container, observe the error, and explain network namespaces.
4. **Missing permission:** if the broker supports a consume-only account, try publishing with it and distinguish a send ACL error from a broker login failure.
5. **Broker restart:** observe recovery with `reconnectAttempts`, recording disconnect/reconnect timestamps; check duplicate handling rather than assuming exactly-once.
6. **Cache/pool:** inspect broker session/connection counts before and after changing `session-cache-size` or enabling pooling. Explain why those numbers differ.

When reporting results, record the broker version, JMS client version, URL **with secrets stripped**, retry settings, and exact exception types. Never attach a full environment dump containing passwords.

## 13. Pre-Deployment Connection Setup Checklist

- [ ] Identified the right JMS provider, Jakarta client, and compatible transport/protocol.
- [ ] Broker URL matches the JVM's network namespace, host, and messaging port.
- [ ] Service account credentials are securely managed with least-privilege send/consume permissions.
- [ ] TLS, truststore, hostname, and certificates are verified in protected environments.
- [ ] ConnectionFactory/JmsTemplate/listener factory consistently use the chosen provider.
- [ ] Queue/Topic mode, destinations, and broker routing align.
- [ ] Caching/pooling and listener concurrency have bounds based on real needs.
- [ ] Retry/reconnect, timeouts, and broker HA have clear policies and error monitoring.
- [ ] Client ID/durable subscriptions do not conflict across multiple instances.
- [ ] Executed send–receive tests and verified ACK/redelivery behavior per business rules.
- [ ] Have a credential rotation plan and post-rollout connectivity checks.

## 14. Self-Assessment Questions

**1.** Why does `tcp://localhost:61616` work on the host yet fail when Java runs in a Docker container separate from the broker?

Because `localhost` now resolves to the Java container itself, so you must use an endpoint reachable from that container (usually the service name on the shared network).

**2.** Does opening the TCP port successfully prove the username/password are correct?

No. Socket reachability is only the network layer; JMS handshake, authentication, and authorization are not yet proven.

**3.** Does `spring.jms.cache.session-cache-size=5` mean five broker connections?

No. That configures Session caching, not the number of network connections or mandatory consumers.

**4.** Why can a listener receive duplicate messages after failover?

The ACK/commit outcome can be ambiguous when the network drops; the provider may redeliver. Idempotency and proper transactions are required.

**5.** Does setting `ha=true` on the client create an HA broker?

No. The broker itself must have a live/backup topology and real failover capability.

**6.** Should credentials be put inside the broker URL for easier debugging?

No. Keep secrets out of URLs and logs; configure them securely via secret injection.

**7.** Does configuring SSL/TLS automatically grant an account permission to consume a Queue?

No. TLS secures transport and certificate identity; broker ACLs still govern consume/send permissions.

## 15. Official References

- Spring Boot — JMS / ActiveMQ Artemis: https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
- Spring Boot — Common Application Properties: https://docs.spring.io/spring-boot/3.4/appendix/application-properties/index.html
- Spring Framework — Using Spring JMS (Connections/Caching/Listener): https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Artemis — Using JMS / Jakarta Messaging: https://artemis.apache.org/components/artemis/documentation/latest/using-jms.html
- Artemis — Configuring the Transport (TCP/TLS): https://artemis.apache.org/components/artemis/documentation/latest/configuring-transports.html
- Artemis — Detecting Dead Connections: https://artemis.apache.org/components/artemis/documentation/latest/connection-ttl.html
- Artemis — Core Client Failover: https://artemis.apache.org/components/artemis/documentation/latest/client-failover.html

**Learning takeaway:** Reliable JMS connectivity is a combination of **accurate broker addressing, matching protocol/client, valid credentials/ACLs, transport security, connection lifecycle, and recovery policies**. Always verify with a real send–receive message and inspect errors at the right layer.
