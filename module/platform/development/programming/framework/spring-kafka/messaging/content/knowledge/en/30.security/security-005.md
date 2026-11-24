# Kerberos and GSSAPI

## 1. What Problems Do Kerberos and GSSAPI Solve?

In enterprise environments, Kafka often runs inside an internal network and allows connections only from authenticated applications. Kerberos is a ticket-based authentication protocol, commonly deployed alongside Active Directory or MIT Kerberos. GSSAPI (Generic Security Services Application Program Interface) is the security API Kafka uses to perform the SASL GSSAPI mechanism backed by Kerberos.

With Spring Kafka, `KafkaTemplate`, `@KafkaListener`, `KafkaAdmin`, and Kafka Streams still use the Kafka Java client underneath. Therefore, applications configure Kerberos through Kafka client properties such as `security.protocol`, `sasl.mechanism`, `sasl.kerberos.service.name`, and `sasl.jaas.config`.

Kerberos/GSSAPI provides client and broker identity authentication. It does not replace Kafka ACLs, nor does it automatically encrypt all Kafka data over the network. In production environments, `SASL_SSL` is commonly combined with it: TLS protects the transport channel, while SASL GSSAPI authenticates via Kerberos.

## 2. Components in Kerberos

A Kerberos deployment typically includes these components:

- **Realm:** the administrative domain for Kerberos identities, usually uppercase, e.g., `EXAMPLE.COM`.
- **KDC (Key Distribution Center):** the server that issues tickets; usually consists of an Authentication Server (AS) and a Ticket Granting Server (TGS).
- **Principal:** the identity of a user or service, e.g., `orders-service@EXAMPLE.COM`.
- **Service Principal Name (SPN):** a principal representing a service on a host, e.g., `kafka/broker1.example.com@EXAMPLE.COM`.
- **Ticket Granting Ticket (TGT):** the ticket a client receives after logging into Kerberos, used to request service tickets.
- **Service ticket:** a ticket scoped to a specific service, such as a Kafka broker.
- **Keytab:** a file containing a principal's secret key so a process can log in automatically without interactive password entry.

Clients and brokers do not send Kerberos passwords over the Kafka connection. The client uses a keytab or ticket cache to obtain a ticket from the KDC, then uses GSSAPI to perform the authentication exchange with the broker.

## 3. Kerberos Authentication Flow When Connecting to Kafka

Suppose a Spring Kafka application runs with principal `orders-service@EXAMPLE.COM` and connects to a broker with SPN `kafka/broker1.example.com@EXAMPLE.COM`.

```text
Spring Kafka application
  Principal: orders-service@EXAMPLE.COM
  Keytab: orders-service.keytab
          |
          | 1. Log in with keytab
          v
       Kerberos KDC
          |
          | 2. Issue Ticket Granting Ticket (TGT)
          v
  Kafka Java client / GSSAPI
          |
          | 3. Request service ticket for kafka/broker1.example.com
          v
       Kerberos KDC
          |
          | 4. Return service ticket
          v
  Kafka Java client
          |
          | 5. SASL GSSAPI token exchange over SASL_SSL
          v
  Kafka broker
  SPN: kafka/broker1.example.com@EXAMPLE.COM
          |
          | 6. Authenticate principal, map local principal
          v
      Kafka Authorizer
          |
          | 7. Check ACLs for topic/group/operation
          v
     Producer / Consumer permitted to operate
```

Key steps:

1. The JVM reads the Kerberos and JAAS configuration.
2. `Krb5LoginModule` uses the keytab to log in the application's principal.
3. The Kerberos client obtains a TGT from the KDC.
4. When connecting to a broker, GSSAPI requests a service ticket for the Kafka SPN on the broker hostname.
5. Client and broker exchange SASL tokens for mutual authentication.
6. The broker identifies the client principal and passes it to the authorizer.
7. Kafka ACLs decide whether the principal is allowed to read/write topics or join consumer groups.

Successful authentication only proves which principal the client is. It does not mean that principal has `Read`, `Write`, `Create`, or `Describe` permissions on Kafka resources.

## 4. Client Principals and Broker Principals

Clients and brokers have different principals:

| Component | Example Principal | Role |
|---|---|---|
| Spring Kafka application | `orders-service@EXAMPLE.COM` | Client identity when calling producer, consumer, or admin APIs |
| Kafka broker 1 | `kafka/broker1.example.com@EXAMPLE.COM` | Kafka service identity on broker 1 |
| Kafka broker 2 | `kafka/broker2.example.com@EXAMPLE.COM` | Kafka service identity on broker 2 |
| Kafka broker 3 | `kafka/broker3.example.com@EXAMPLE.COM` | Kafka service identity on broker 3 |

The `kafka` part before `/` is the service name. The hostname must match the hostname the client uses to connect to the broker and the SPN registered in Kerberos.

For example, broker 1 has the principal:

```text
kafka/broker1.example.com@EXAMPLE.COM
```

The client configures:

```properties
sasl.kerberos.service.name=kafka
```

The client does not include the hostname in `sasl.kerberos.service.name`; the Kafka client combines the service name with the broker hostname to build the service principal to authenticate against.

## 5. Preparing the Kerberos Realm and `krb5.conf`

The JVM needs to know the default realm and how to locate the KDC. You can specify the configuration file using the `java.security.krb5.conf` system property.

Example `/etc/krb5.conf` file:

```ini
[libdefaults]
    default_realm = EXAMPLE.COM
    dns_lookup_kdc = true
    ticket_lifetime = 10h
    renew_lifetime = 7d
    forwardable = true

[realms]
    EXAMPLE.COM = {
        kdc = kdc1.example.com
        admin_server = kdc1.example.com
    }

[domain_realm]
    .example.com = EXAMPLE.COM
    example.com = EXAMPLE.COM
```

If DNS does not provide SRV records for the KDC, specify the KDC hostname and port directly in the realm configuration. `default_realm`, domain names, and KDC values in the example must be replaced with your organization's information.

Launch the application with:

```bash
java \
  -Djava.security.krb5.conf=/etc/krb5.conf \
  -jar spring-kafka-messaging.jar
```

In containers, the system property can be passed via `JAVA_TOOL_OPTIONS`:

```bash
JAVA_TOOL_OPTIONS="-Djava.security.krb5.conf=/etc/krb5.conf"
```

On Windows, this property likewise points to the Kerberos configuration file readable by the JVM, for example:

```powershell
java -Djava.security.krb5.conf="C:\kerberos\krb5.ini" -jar spring-kafka-messaging.jar
```

Do not assume every JVM or Kerberos distribution uses the same default path. Verify the actual file mounted/installed in the runtime environment.

## 6. Creating Principals and Keytabs

The Kerberos administrator creates a dedicated principal for the application, for example:

```text
orders-service@EXAMPLE.COM
```

Then generate the corresponding keytab and provision it to the process running Spring Kafka. The exact commands for creating principals/keytabs depend on the KDC, such as MIT Kerberos or Active Directory; this task is typically performed by the infrastructure or IAM team.

A keytab is a sensitive credential. Deployment rules:

- Create a dedicated principal per application or workload; do not use personal accounts.
- Provision keytabs only to the services that need them and restrict file read permissions at the OS/container level.
- Mount keytabs from a secret manager or secret volume; do not commit them to Git, images, or build artifacts.
- Do not copy keytabs into logs, exception messages, or support bundles.
- Maintain a keytab rotation procedure and update service principals/kvno in sync.
- Do not share a single broad-privilege admin keytab across all producers and consumers.

A keytab can contain multiple entries or multiple key versions (kvno). When the KDC rotates a principal's key, an old keytab may no longer authenticate. Coordinate rotation timing with rolling restarts of the application.

## 7. Verifying the Keytab Before Running the Application

With MIT Kerberos tools, you can inspect the keytab and test login:

```bash
# List principals and key versions in the keytab
klist -kte /etc/security/keytabs/orders-service.keytab

# Obtain a TGT using the keytab
kinit -kt /etc/security/keytabs/orders-service.keytab \
  orders-service@EXAMPLE.COM

# Inspect the ticket cache
klist -e

# Request a service ticket for the Kafka broker
kvno kafka/broker1.example.com@EXAMPLE.COM

# Clear the ticket cache after verification
kdestroy
```

If `kinit` fails, resolve the principal, realm, keytab, file read permissions, or system clock before troubleshooting Spring Kafka. If `kinit` succeeds but `kvno` fails, focus on checking the Kafka SPN, hostname, DNS, and KDC.

## 8. Configuring JAAS with `Krb5LoginModule`

The Kafka Java client uses JAAS to perform Kerberos login. The standard JDK login module is:

```text
com.sun.security.auth.module.Krb5LoginModule
```

Example JAAS configuration for a long-running application using a keytab:

```text
com.sun.security.auth.module.Krb5LoginModule required
    useKeyTab=true
    storeKey=true
    keyTab="/etc/security/keytabs/orders-service.keytab"
    principal="orders-service@EXAMPLE.COM"
    doNotPrompt=true;
```

Option meanings:

| Option | Meaning |
|---|---|
| `useKeyTab=true` | Log in using a keytab |
| `storeKey=true` | Store the principal's key in the Subject for GSSAPI to use |
| `keyTab=...` | Path to the keytab |
| `principal=...` | Principal the application logs in as |
| `doNotPrompt=true` | Do not prompt interactively for a password |

For background services, a keytab is usually better suited than a ticket cache created by manual user login. A ticket cache is useful for local development or CLI tools:

```text
com.sun.security.auth.module.Krb5LoginModule required
    useTicketCache=true;
```

Do not configure multiple credential mechanisms simultaneously without understanding `Krb5LoginModule`'s selection order. When running with a ticket cache, the process must have a valid cache and a clear ticket-refresh workflow.

### Using a Static JAAS File

The Kafka client also supports configuring JAAS in a dedicated file with a section named `KafkaClient`:

```text
KafkaClient {
    com.sun.security.auth.module.Krb5LoginModule required
        useKeyTab=true
        storeKey=true
        keyTab="/etc/security/keytabs/orders-service.keytab"
        principal="orders-service@EXAMPLE.COM"
        doNotPrompt=true;
};
```

Start the JVM with:

```bash
java \
  -Djava.security.auth.login.config=/etc/security/kafka-client-jaas.conf \
  -Djava.security.krb5.conf=/etc/krb5.conf \
  -jar spring-kafka-messaging.jar
```

A static JAAS file typically shares a single identity across Kafka clients in the JVM. If producers, consumers, and admin need different principals, per-client `sasl.jaas.config` is more flexible. When both the system property `java.security.auth.login.config` and the client property `sasl.jaas.config` are set, the client property takes precedence.

## 9. Configuring Kerberos in Spring Boot

Spring Kafka does not need a dedicated annotation for Kerberos. Configuration is passed down to Kafka producer, consumer, and admin clients via `spring.kafka`.

Example `application.yml` using the same principal across Kafka clients:

```yaml
spring:
  kafka:
    bootstrap-servers:
      - broker1.example.com:9093
      - broker2.example.com:9093
      - broker3.example.com:9093
    security:
      protocol: SASL_SSL
    properties:
      sasl.mechanism: GSSAPI
      sasl.kerberos.service.name: kafka
      sasl.jaas.config: >-
        com.sun.security.auth.module.Krb5LoginModule required
        useKeyTab=true
        storeKey=true
        keyTab="${KAFKA_KEYTAB_PATH:/etc/security/keytabs/orders-service.keytab}"
        principal="${KAFKA_KERBEROS_PRINCIPAL:orders-service@EXAMPLE.COM}"
        doNotPrompt=true;
    ssl:
      trust-store-location: file:/etc/security/kafka/client.truststore.p12
      trust-store-type: PKCS12
      trust-store-password: ${KAFKA_TRUSTSTORE_PASSWORD}
```

In this example:

- `security.protocol: SASL_SSL` enables SASL with TLS.
- `sasl.mechanism: GSSAPI` selects Kerberos via GSSAPI.
- `sasl.kerberos.service.name: kafka` specifies the service name in the broker SPN.
- `sasl.jaas.config` logs in the application principal using a keytab.
- `ssl.trust-store-*` lets the JVM verify broker certificates; replace with your actual CA/trust configuration.

`spring.kafka.properties.*` are shared Kafka client properties for producer and consumer. `KafkaAdmin` has its own `spring.kafka.admin.properties.*` group; if the application uses `KafkaAdmin`, configure JAAS under the admin group accordingly. Example when all three clients use the same principal:

```yaml
spring:
  kafka:
    admin:
      security:
        protocol: SASL_SSL
      properties:
        sasl.jaas.config: >-
          com.sun.security.auth.module.Krb5LoginModule required
          useKeyTab=true storeKey=true
          keyTab="${KAFKA_KEYTAB_PATH:/etc/security/keytabs/orders-service.keytab}"
          principal="${KAFKA_KERBEROS_PRINCIPAL:orders-service@EXAMPLE.COM}"
          doNotPrompt=true;
```

Spring Boot passes these properties to the corresponding autoconfigured Kafka clients. If producer, consumer, and admin share one principal, keep the same JAAS string in the relevant groups; if using separate principals, configure per-client overrides as shown in the next section.

`KAFKA_TRUSTSTORE_PASSWORD`, `KAFKA_KEYTAB_PATH`, and principal must be supplied by the deployment environment. Do not write real truststore passwords or credentials into the repository.

## 10. Using Different Principals for Producer, Consumer, and Admin

A single JVM can create multiple Kafka clients with different identities. The Kafka client property `sasl.jaas.config` lets each producer or consumer use its own principal. In Spring Boot, shared settings can be overridden by per-client properties.

Example:

```yaml
spring:
  kafka:
    bootstrap-servers: broker1.example.com:9093
    security:
      protocol: SASL_SSL
    properties:
      sasl.mechanism: GSSAPI
      sasl.kerberos.service.name: kafka
    consumer:
      properties:
        sasl.jaas.config: >-
          com.sun.security.auth.module.Krb5LoginModule required
          useKeyTab=true storeKey=true
          keyTab="/etc/security/keytabs/order-reader.keytab"
          principal="order-reader@EXAMPLE.COM"
          doNotPrompt=true;
    producer:
      properties:
        sasl.jaas.config: >-
          com.sun.security.auth.module.Krb5LoginModule required
          useKeyTab=true storeKey=true
          keyTab="/etc/security/keytabs/order-writer.keytab"
          principal="order-writer@EXAMPLE.COM"
          doNotPrompt=true;
    admin:
      properties:
        sasl.jaas.config: >-
          com.sun.security.auth.module.Krb5LoginModule required
          useKeyTab=true storeKey=true
          keyTab="/etc/security/keytabs/order-admin.keytab"
          principal="order-admin@EXAMPLE.COM"
          doNotPrompt=true;
```

The producer factory uses principal `order-writer`, the consumer factory uses `order-reader`, and `KafkaAdmin` uses `order-admin`. This supports least privilege: a service that only reads data does not need credentials permitted to create topics or write to other topics.

Only declare a shared `sasl.jaas.config` when every client genuinely uses the same identity. If separate JAAS configs are declared on producer/consumer/admin, verify the final resolved configuration of each client to avoid accidentally inheriting or overriding the wrong principal.

## 11. Configuring the Kafka Java Client Directly

If creating `ProducerFactory` or `ConsumerFactory` manually, add the Kafka client properties to the configuration map:

```java
Map<String, Object> securityProperties(String jaasConfig) {
    Map<String, Object> properties = new HashMap<>();

    properties.put(CommonClientConfigs.SECURITY_PROTOCOL_CONFIG, "SASL_SSL");
    properties.put(SaslConfigs.SASL_MECHANISM, "GSSAPI");
    properties.put(SaslConfigs.SASL_KERBEROS_SERVICE_NAME, "kafka");
    properties.put(SaslConfigs.SASL_JAAS_CONFIG, jaasConfig);

    return properties;
}
```

Example creating a consumer factory:

```java
@Bean
ConsumerFactory<String, OrderEvent> orderConsumerFactory(
        @Value("${spring.kafka.bootstrap-servers}") String bootstrapServers,
        @Value("${app.kafka.jaas-config}") String jaasConfig) {

    Map<String, Object> properties = new HashMap<>();
    properties.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
    properties.put(ConsumerConfig.GROUP_ID_CONFIG, "order-service");
    properties.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
    properties.putAll(securityProperties(jaasConfig));

    return new DefaultKafkaConsumerFactory<>(
            properties,
            new StringDeserializer(),
            new JsonDeserializer<>(OrderEvent.class));
}
```

The producer factory uses the same security properties alongside producer serializers:

```java
@Bean
ProducerFactory<String, OrderEvent> orderProducerFactory(
        @Value("${spring.kafka.bootstrap-servers}") String bootstrapServers,
        @Value("${app.kafka.jaas-config}") String jaasConfig) {

    Map<String, Object> properties = new HashMap<>();
    properties.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
    properties.putAll(securityProperties(jaasConfig));

    return new DefaultKafkaProducerFactory<>(
            properties,
            new StringSerializer(),
            new JsonSerializer<>());
}
```

In the Java example, `app.kafka.jaas-config` is a custom application property loaded from a secret/config provider. It can be declared in deployment configuration:

```yaml
app:
  kafka:
    jaas-config: >-
      com.sun.security.auth.module.Krb5LoginModule required
      useKeyTab=true storeKey=true
      keyTab="${KAFKA_KEYTAB_PATH}"
      principal="${KAFKA_KERBEROS_PRINCIPAL}"
      doNotPrompt=true;
```

The example focuses on SASL properties; if using `SASL_SSL`, you still must configure the appropriate truststore/certificates. When creating factories manually, do not forget to apply security configuration to `KafkaAdmin`, `KafkaStreams`, or any other clients used by the application.

## 12. Configuring the Broker to Accept GSSAPI

The broker must enable a SASL listener and the GSSAPI mechanism. Example for a broker using `SASL_SSL`:

```properties
listeners=SASL_SSL://0.0.0.0:9093
advertised.listeners=SASL_SSL://broker1.example.com:9093

sasl.enabled.mechanisms=GSSAPI
sasl.kerberos.service.name=kafka

listener.name.sasl_ssl.gssapi.sasl.jaas.config=com.sun.security.auth.module.Krb5LoginModule required useKeyTab=true storeKey=true doNotPrompt=true keyTab="/etc/kafka/keytabs/kafka-broker.keytab" principal="kafka/broker1.example.com@EXAMPLE.COM";

security.inter.broker.protocol=SASL_SSL
sasl.mechanism.inter.broker.protocol=GSSAPI
```

This is an illustrative broker configuration. In a multi-broker cluster, each broker must use a keytab containing the service principal matching its own hostname. If the cluster uses `inter.broker.listener.name`, configure the internal listener using that model and do not simultaneously set a conflicting inter-broker protocol option.

The broker must also have a valid TLS keystore/certificate for the `SASL_SSL` listener. The certificate must match the hostname in `advertised.listeners` so clients can complete TLS verification.

## 13. Hostname, DNS, and SPN Must Match

Kerberos is sensitive to service names and hostnames. The Kafka client may perform reverse DNS lookups during the SASL handshake. Hostname misconfiguration often causes `Server not found in Kerberos database` or `GSS initiate failed`.

Verify the following points:

- `bootstrap.servers` uses resolvable FQDNs.
- `advertised.listeners` returns each broker's real FQDN, not an internal hostname unreachable from clients.
- SPNs are registered with the exact broker hostnames, e.g., `kafka/broker1.example.com@EXAMPLE.COM`.
- `sasl.kerberos.service.name` matches the `kafka` service prefix in the SPN.
- Forward DNS and reverse DNS do not resolve to a hostname different from the SPN.
- The TLS certificate SAN includes the broker hostname used by clients.
- Do not use IP addresses instead of hostnames when SPNs are registered by FQDN.

In environments with load balancers or DNS aliases, determine which hostname the Kafka client actually uses to request the service ticket. Do not register arbitrary alias SPNs if the broker cannot authenticate that principal.

## 14. Authentication and Kafka ACL Authorization

After GSSAPI authenticates the client, the broker has a principal for the authorizer to evaluate permissions. Kafka ACLs are a separate authorization layer.

Example permission matrix:

| Principal | Resource | Required Permissions |
|---|---|---|
| `User:order-writer` | Topic `orders` | `Write`; plus `Describe` if required by operations |
| `User:order-reader` | Topic `orders` | `Read` and appropriate describe permission |
| `User:order-reader` | Group `order-service` | `Read` to join/commit offsets for the consumer group |
| `User:order-admin` | Topic/cluster | Only needed administrative permissions such as `Create`, `Alter`, or `Describe` |

The principal seen in ACLs depends on the broker's principal mapping rules. With Kerberos, `sasl.kerberos.principal.to.local.rules` can transform full principals into short names to form principals like `User:order-reader`. If your organization uses a custom `KafkaPrincipalBuilder`, mapping behavior may differ.

Do not grant `super.users` or cluster-wide permissions to an application just to work around authorization errors. Grant least-privilege ACLs matching actual topics, groups, and operations.

## 15. Ticket Lifetime and Automatic Credential Renewal

Long-running applications cannot rely on a ticket cache that expires without renewal. When using a keytab with the Kafka Java client, the login module and Kafka login manager can re-acquire credentials according to the ticket lifetime and Kerberos configuration.

Points to control:

- TGTs and service tickets have lifetimes governed by realm policy.
- The KDC must be reachable from pods/VMs during login and renewal.
- The keytab must remain valid and carry a key version accepted by the KDC.
- The JVM process needs read permission on the keytab throughout its lifecycle.
- When rotating keytabs, roll out the application and verify new tickets before revoking old keys.
- Monitor login/reauthentication errors rather than checking connectivity only at startup.

The Kafka client provides Kerberos settings related to login refresh, but you should not change default intervals without understanding your realm's ticket lifecycle. Before tuning, check `ticket_lifetime`, `renew_lifetime`, keytabs, and login module logs.

## 16. Protecting Connections with `SASL_SSL`

Two common protocols:

| Protocol | Authentication | Transport Encryption |
|---|---|---|
| `SASL_PLAINTEXT` | SASL GSSAPI/Kerberos | No TLS; unsuitable for untrusted networks |
| `SASL_SSL` | SASL GSSAPI/Kerberos | Uses TLS to protect data in transit |

Kerberos authenticates clients and brokers, but when data confidentiality in transit is required, use `SASL_SSL`. Configure a truststore or SSL bundle so the JVM verifies broker certificates. If mutual TLS is required, also configure client certificates per organizational policy; mTLS and Kerberos can be combined, though they serve different purposes.

Do not disable hostname verification or trust all certificates as a quick fix for TLS errors. Fix certificate SANs, trust chains, and broker hostnames properly.

## 17. Debugging and Observing Kerberos/GSSAPI

When authentication fails, check from the lowest layer upward:

1. DNS and network connectivity to the KDC.
2. The JVM is reading the right `krb5.conf`.
3. The keytab contains the right principal and the process can read the file.
4. `kinit` can obtain a TGT.
5. `kvno` can obtain a service ticket for the Kafka SPN.
6. The Kafka client uses the right service name, mechanism, and JAAS config.
7. The broker uses the right SPN/keytab and GSSAPI listener.
8. The TLS handshake succeeds if using `SASL_SSL`.
9. Kafka ACLs allow the principal's operations.

You can enable temporary Kerberos debugging via a JVM option:

```bash
java \
  -Djava.security.krb5.conf=/etc/krb5.conf \
  -Dsun.security.krb5.debug=true \
  -jar spring-kafka-messaging.jar
```

Debug output may expose principals, hostnames, and sensitive environment details. Enable it only briefly, restrict log read access, and disable it after investigation. Never leave Kerberos debugging enabled continuously in production.

Metrics/logs to watch include authentication failure counts, TLS handshake failures, connection times, reconnects, consumer authentication exceptions, and Kafka authorization exceptions. Never log keytabs, ticket caches, or JAAS credentials.

## 18. Common Errors and How to Handle Them

| Error | Common Cause | What to Check |
|---|---|---|
| `No valid credentials provided` | JAAS failed to log in, missing TGT, or unreadable keytab | Check `principal`, `keyTab`, file permissions, and `kinit` |
| `Failed to find any Kerberos tgt` | Ticket cache missing/expired or keytab login failed | Use a keytab for services; check `klist` and JAAS options |
| `Server not found in Kerberos database` | Wrong SPN hostname/service name or not registered in KDC | Check `advertised.listeners`, DNS, SPN, and `sasl.kerberos.service.name` |
| `Clock skew too great` | Client, broker, or KDC clocks drifted beyond realm limit | Synchronize NTP/time service across hosts |
| `Preauthentication failed` | Wrong keytab, old key version, or principal mismatch | Check keytab/kvno and rotate credentials properly |
| `GSS initiate failed` | Composite failure during GSSAPI handshake | Enable Kerberos debug briefly; check KDC, SPN, DNS, JAAS, and broker logs |
| `KRB_AP_ERR_MODIFIED` | Broker uses a key not matching the SPN or keytab rotated out of sync | Verify SPN owner, keytab, and kvno on the broker |
| `SaslAuthenticationException` | Broker rejected authentication or client used wrong mechanism/protocol | Compare `GSSAPI`, `SASL_SSL`, service name, and broker listener |
| `SSLHandshakeException` | Truststore missing CA, expired cert, or SAN hostname mismatch | Check trust chain, certificate, and hostname verification |
| `TopicAuthorizationException` | Kerberos authentication succeeded, but principal lacks ACL | Check the principal logged by the broker and grant least-privilege ACLs |
| `GroupAuthorizationException` | Principal lacks `Read` permission on consumer group | Grant ACL for the exact group ID |
| Slow connection during SASL handshake | Slow DNS/reverse DNS lookup or non-standard hostname | Use stable FQDNs and check DNS resolution |

Do not react to every `SaslAuthenticationException` by immediately replacing the keytab. First separate Kerberos login errors, SPN errors, TLS errors, and ACL errors because they occur at different layers.

## 19. Integration Testing Kerberos with Spring Kafka

Testing should validate authentication, authorization, and Kafka business logic:

1. **Standalone login:** run `kinit -kt` with the service principal's keytab.
2. **Service ticket:** use `kvno kafka/broker1.example.com@EXAMPLE.COM` to verify the SPN.
3. **Producer:** send a record to a permitted topic and verify the send future succeeds.
4. **Consumer:** read records using an ACL-permitted group ID.
5. **ACL deny:** use an unauthorized principal and verify the broker rejects the operation properly.
6. **Principal mapping:** verify the full principal maps to the expected short name used in ACLs.
7. **TLS:** verify the broker certificate chain and hostname are trusted by the JVM.
8. **Keytab rotation:** replace the keytab per procedure and verify the application can reconnect/reauthenticate.
9. **KDC unavailable:** verify reconnect/renew behavior and operational alerting.
10. **Broker restart:** verify producer/consumer reconnect and GSSAPI handshake succeeds.

An integration test environment can run a Kafka broker and a test Kerberos KDC realm in containers or dedicated VMs. Never use production principals/keytabs in tests. Unit tests for YAML configuration do not prove ticket exchange and broker ACLs work; at least one end-to-end test against a GSSAPI-enabled KDC and broker is needed.

## 20. Production Deployment Workflow

1. Create dedicated principals for the application and dedicated SPNs for each broker hostname.
2. Configure the realm/KDC and synchronize clocks across clients, brokers, and KDC.
3. Generate keytabs and verify them with `klist`, `kinit`, and `kvno`.
4. Configure the broker `SASL_SSL` listener, enable `GSSAPI`, and use each broker's matching keytab.
5. Configure Spring Boot with `security.protocol=SASL_SSL`, `sasl.mechanism=GSSAPI`, service name, and `sasl.jaas.config`.
6. Mount keytabs/truststores via secret management and restrict read permissions.
7. Grant least-privilege Kafka ACLs for producer, consumer, and admin principals.
8. Verify `bootstrap.servers`, `advertised.listeners`, DNS, SPNs, and certificate SANs.
9. Test producer, consumer, authorization denials, restarts, and keytab rotation.
10. Monitor login failures, TLS failures, ACL denials, ticket expiry, and reconnects after deployment.

## 21. Summary

- Kerberos authenticates using tickets; GSSAPI is the SASL API/mechanism Kafka uses to perform Kerberos authentication.
- Clients use an application principal and keytab; each broker has a hostname-based service principal.
- `sasl.kerberos.service.name` must match the service prefix in the broker SPN, typically `kafka`.
- The JVM needs to read the right `krb5.conf`; JAAS `Krb5LoginModule` typically uses `useKeyTab=true`, `storeKey=true`, `principal`, `keyTab`, and `doNotPrompt=true` for background services.
- Spring Boot passes Kafka client security properties via `spring.kafka.security.protocol` and `spring.kafka.properties.*`; JAAS can be overridden separately for producer, consumer, and admin.
- `SASL_SSL` combines Kerberos authentication with TLS encryption; `SASL_PLAINTEXT` does not encrypt Kafka traffic in transit.
- Kerberos authentication and Kafka ACL authorization are two separate steps.
- FQDNs, DNS, `advertised.listeners`, SPNs, clock synchronization, and keytab kvnos must all align.
- Keytabs are secrets; manage file permissions and rotation, and never commit them to source control.
- End-to-end testing must include a KDC, GSSAPI broker, TLS, and ACLs; checking YAML alone is insufficient.

When Kerberos/GSSAPI is configured properly, a Spring Kafka application can authenticate with a centrally managed service identity while Kafka ACLs precisely control which topics and consumer groups the application may access.

## References

- [Apache Kafka — Authentication using SASL (GSSAPI/Kerberos)](https://kafka.apache.org/44/security/authentication-using-sasl/)
- [Apache Kafka — Broker Configurations](https://kafka.apache.org/44/configuration/broker-configs/)
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html)
- [Java SE — Krb5LoginModule](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.security.auth/com/sun/security/auth/module/Krb5LoginModule.html)
