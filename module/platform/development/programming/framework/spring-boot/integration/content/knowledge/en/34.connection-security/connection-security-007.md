# Distinguishing Authentication to Brokers, Databases, and HTTP Services

## Goals and Context

In the **SPRING_BOOT_INTEGRATION** module, Spring Boot coordinates system integrations across HTTP clients, databases, caches, message brokers, and Spring Integration adapters. The focus is configuration, data contracts, transactions, errors, duplicate handling, testing, and observability across real integration flows. When one flow traverses multiple systems, each hop has a distinct **trust boundary**, authentication mechanism, and permission scope.

Suppose Order Service receives an HTTP request, writes to PostgreSQL, emits an event to Kafka, and Inventory Service consumes the event, writes to another database, and calls a Pricing HTTP API. In such a flow, there are at least four independent identities:

- External client calling the **Order HTTP API**.
- **Order Service** logging into PostgreSQL and Kafka.
- **Inventory Service** logging into Kafka and its own database.
- **Inventory Service** acquiring an appropriate token to call the **Pricing HTTP API**.

You cannot reuse one `Authorization: Bearer ...` across every target. Kafka has SASL/TLS/ACLs, PostgreSQL has users/roles and server-configured auth methods, RabbitMQ has virtual hosts and permissions, Redis has ACLs, while HTTP APIs commonly use OAuth2 access tokens, API keys, mTLS, or request signatures. A successful TLS connection also **does not prove** the caller is permitted to perform every business operation.

This lesson belongs to the **Connection Security** chapter, topic **Distinguishing authentication to brokers, databases, and HTTP services**.

### Learning Outcomes

After this lesson, you can:

1. Distinguish **identity**, **authentication**, **authorization**, **TLS server authentication**, **mTLS client authentication**, and **business authorization**.
2. Identify which identity is used at each point in an integration flow.
3. Configure Kafka connections with `SASL_SSL`, SCRAM, and topic/consumer-group permissions.
4. Distinguish RabbitMQ credentials, virtual hosts, configure/write/read permissions, and TLS.
5. Configure PostgreSQL JDBC with user/password, SCRAM, and `sslmode=verify-full`.
6. Understand Redis ACLs, MongoDB `authSource`/X.509, and how they differ from HTTP security.
7. Design HTTP service-to-service authentication using OAuth2 client credentials or mTLS.
8. Avoid confusing an inbound OAuth2 resource server with an outbound OAuth2 client.
9. Apply least privilege, secret/CA rotation, and per-environment credential isolation.
10. Classify authentication, authorization, and network errors to avoid improper retries.
11. Write integration tests for invalid credentials, missing permissions, wrong certificates, and expired tokens.
12. Build a production checklist for a connection flow spanning multiple security boundaries.

> **Principle:** Authentication answers **"who are you?"**; authorization answers **"what may you do on which resource?"**. TLS protects and can authenticate **peers at the transport layer**; it does not replace Kafka, database, or HTTP service business permissions.

---

## 1. Mapping the Security Boundaries of an Integration Flow

~~~mermaid
flowchart LR
    U["External user / client"] -->|"HTTPS bearer token"| A["Order API"]
    A -->|"JDBC user + SCRAM / TLS"| D1[("Orders PostgreSQL")]
    A -->|"Kafka SASL_SSL / topic ACL"| K["Kafka cluster"]
    K -->|"SASL_SSL / group ACL"| I["Inventory Service"]
    I -->|"DB role + TLS"| D2[("Inventory PostgreSQL")]
    I -->|"OAuth2 access token / mTLS"| H["Pricing HTTP API"]
    I -. "Redis ACL + TLS" .-> C["Redis cache"]
~~~

**Each arrow has its own policy.** Even if two services run in the same VPC or Kubernetes namespace, network location **is not enough** to prove identity or authorization. Every peer must be verified according to its policy.

One way to inventory connections:

| Caller | Target | Required Identity | Authorization Check |
| --- | --- | --- | --- |
| Browser/mobile client | Order API | End-user JWT/session | Only view/modify own orders |
| Order Service | Orders PostgreSQL | `order_app` database role | SELECT/INSERT/UPDATE on granted schemas/tables |
| Order Service | Kafka broker | Kafka principal via SASL/cert | WRITE to `orders.events`, not all topics |
| Inventory Service | Kafka broker | Kafka consumer principal | READ topic, READ matching consumer group |
| Inventory Service | Inventory PostgreSQL | `inventory_app` DB role | CRUD within inventory scope |
| Inventory Service | Pricing API | OAuth2 client/service identity | `pricing.read` scope **and** resource policy |
| Inventory Service | Redis | ACL user `inventory_cache` | Only needed commands/key patterns |
| Admin/migration job | DB/schema | Separate migration identity | Required DDL, not granted to app runtime |

**Never share one administrative account across all arrows.** If a Kafka credential leaks, the blast radius must remain confined to that service's Kafka resources—it must never simultaneously unlock the database or HTTP admin APIs.

### 1.1. The Question: "Who Authenticates Whom?"

In a standard TLS connection:

1. The client connects to the host.
2. The server presents its certificate and chain.
3. The client verifies CA, validity, hostname/SAN, and TLS constraints.
4. If **mTLS** is configured, the client also presents a certificate/private key for the server to verify.
5. The application/broker/database layer performs authentication/authorization per its policy.

Do not assume a client having a truststore with a CA already has a **client identity**: a truststore helps **verify the server**, whereas a keystore containing a private key/client cert is what authenticates the client in mTLS.

### 1.2. Three Distinct Protection Layers

| Layer | Examples | Common Failures |
| --- | --- | --- |
| Transport encryption/peer validation | TLS, CA, hostname verification | `SSLHandshakeException`, certificate unknown |
| Authentication | SASL SCRAM, DB user/password, HTTP bearer | Invalid credentials, token expired |
| Authorization | Kafka ACL, DB GRANT, HTTP scope/tenant | Authenticated yet operation denied |

**Critical checkpoint:** A successful TLS handshake **does not** prove username/password are right. A right password **does not** prove a role can SELECT. A valid HTTP JWT signature **does not** prove the token has the right audience/scope/tenant.

---

## 2. Layer-by-Layer Comparison: Brokers, Databases, and HTTP Services

| Aspect | Kafka | RabbitMQ | PostgreSQL | Redis | HTTP Service |
| --- | --- | --- | --- | --- | --- |
| Client identity | SASL principal or TLS certificate principal | Username/vhost or TLS client cert via appropriate mechanism | DB role/user, per `pg_hba.conf` | ACL username/password | OAuth2 client/user, mTLS identity, API key |
| Common authentication | SASL SCRAM, GSSAPI, OAUTHBEARER; mTLS | AMQP SASL PLAIN over TLS, EXTERNAL when configured | SCRAM-SHA-256 password, certificate, GSS, provider-specific IAM | ACL AUTH + TLS | Bearer JWT/opaque token, API key, HMAC, mTLS |
| Authorization | Topic/group/cluster ACL or RBAC | Vhost and configure/write/read regex permissions | CONNECT/schema USAGE/table/row privileges | Commands, key patterns, and categories | Scopes/roles/audience + domain ACL |
| TLS trust | Kafka SSL truststore/PEM config | AMQPS TLS/CA/hostname | JDBC driver TLS CA/hostname | TLS trust and Redis endpoint | HTTPS server certificate/hostname |
| Client private key | Needed only if using mTLS | Needed only if broker requires client cert | Needed only if DB uses cert auth | Provider-specific mTLS support | Needed only if HTTP mTLS |
| "Login OK" proves | Principal accepted | Login/vhost allowed per policy | DB session authenticated | ACL session authenticated | Token/key accepted by endpoint |
| Does NOT prove | WRITE/READ on all topics/groups | Permissions on all queues/exchanges | DDL or SELECT on all tables | All keys/commands | All resources/tenants |
| Credential reuse | Never across systems | Never across systems | Never across systems | Never across systems | Token must match audience/scope |

Other backends like MongoDB, MySQL, Elasticsearch, and Pulsar also have their own security models. **Never copy JDBC properties into Kafka, or put a bearer token into a DB password field**, unless a specific driver/provider officially supports a configured IAM/OAuth token model.

## 3. Distinguishing Authentication Methods from TLS

### 3.1. Server-Auth TLS

A connection to `postgresql://db.internal:5432`, `broker.internal:9093`, or `https://api.internal` can use TLS to:

- Encrypt traffic.
- Detect tampering in transit.
- Authenticate the server endpoint if the certificate is properly checked.

If a client skips hostname validation or trusts all certificates, the connection may still be encrypted yet **does not guarantee it reached the intended server**.

### 3.2. mTLS (Mutual TLS)

~~~mermaid
sequenceDiagram
    participant C as Service client
    participant S as Server / broker / DB
    C->>S: TLS ClientHello
    S-->>C: Server certificate
    C->>C: Verify trusted CA + SAN/hostname
    S-->>C: CertificateRequest if mTLS required
    C->>S: Client certificate + proof of private key
    S->>S: Validate client cert/identity policy
    Note over C,S: May continue with SASL/password/OAuth or map certificate identity
    C->>S: Application request
~~~

mTLS can be used **alongside** SASL/passwords/tokens, or mapped into an application principal if supported by the server/plugin. Rules must be clearly defined on both sides.

Examples:

- Kafka `security.protocol=SSL` with a client certificate and broker principal mapping/ACLs can use TLS principals instead of SASL.
- Kafka `SASL_SSL` uses TLS for transport and a SASL mechanism for Kafka authentication; it does not automatically require client certificates.
- RabbitMQ can use TLS client certificates with the appropriate auth mechanism/plugin; merely enabling TLS does not log in via certificate.
- PostgreSQL `hostssl` can require a client certificate via `pg_hba.conf`; a client certificate does not automatically grant all DB privileges.
- An HTTP gateway can authenticate an mTLS service identity, yet the backend still needs role/resource authorization.

### 3.3. Truststores and Keystores Do Not Swap Roles

| Component | Contains | Used For |
| --- | --- | --- |
| Truststore | CA certificates / trusted roots | Client verifies destination's certificate |
| Keystore/key material | Client private key + certificate chain | Client proves identity in mTLS |
| DB password | Secret tied to DB role | Database authentication |
| SASL password | Secret tied to broker principal | Kafka/Rabbit auth mechanism |
| OAuth client secret | Secret of OAuth client | Acquire access token from authorization server |
| OAuth access token | Token issued by AS, with expiry/audience | Call resource server per policy |
| API key | Secret/key issued by API provider | HTTP operations per provider contract |

Never store private keys in source repos or log `javax.net.debug=all`/HTTP headers into observability systems without redaction. Secrets must be managed and rotated.

---

## 4. Kafka: Broker Authentication vs. Topic/Group Authorization

Kafka producers and consumers connect to brokers, not HTTP REST endpoints. Common layers:

1. TLS to broker: `SSL` or `SASL_SSL`.
2. Broker principal: SASL SCRAM/GSSAPI/OAUTHBEARER or mTLS mapping.
3. Authorization: ACL/RBAC for operations on topics, groups, and cluster resources.
4. Message payload/headers: data contract, correlation, idempotency; **not user authentication**.

### 4.1. Kafka `security.protocol`

| Protocol | Transport Encryption | Kafka Client Authentication |
| --- | --- | --- |
| `PLAINTEXT` | No | None at Kafka protocol layer; network trust is insufficient |
| `SSL` | TLS | Can use certificate authentication if configured on broker |
| `SASL_PLAINTEXT` | No | SASL without encryption — avoid in production |
| `SASL_SSL` | TLS | SASL authentication over TLS |

`SASL_SSL` **does not** mean "mandatory TLS client certificate". The SASL mechanism is configured by `sasl.mechanism` and broker listeners; TLS can be server-auth only. For Kafka TLS client auth, check broker-side `ssl.client.auth` and principal mapping.

### 4.2. Spring Boot Kafka Producer with SCRAM

An `application.yml` example for Spring Boot 3.x:

~~~yaml
spring:
  kafka:
    bootstrap-servers:
      - kafka-1.internal.example:9093
      - kafka-2.internal.example:9093
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: >-
        org.apache.kafka.common.security.scram.ScramLoginModule
        required username="${KAFKA_USERNAME}"
        password="${KAFKA_PASSWORD}";
      ssl.truststore.location: /etc/certs/kafka-truststore.p12
      ssl.truststore.password: ${KAFKA_TRUSTSTORE_PASSWORD}
      ssl.truststore.type: PKCS12
    producer:
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
~~~

**Accompanying requirements:**

- `KAFKA_USERNAME`, `KAFKA_PASSWORD`, and truststore password must come from secret injection, **never hardcoded**.
- Bootstrap brokers and advertised listeners must point to hostnames covered by certificate SANs.
- Verify server hostname/CA; never disable hostname verification by setting `ssl.endpoint.identification.algorithm` to empty.
- `acks: all` governs acknowledgement/durability; **it does not determine authentication**.
- Producer serializers govern the data contract; they do not determine authorization.
- `SCRAM-SHA-512` only works when the Kafka cluster/listeners support it and the user is provisioned.
- JAAS syntax requires the trailing `;`. Verify Spring config interpolation and quoting in your actual environment/container.
- When using PEM and SSL bundles/cloud vendor IAM, property names may differ depending on Kafka client/provider version.

### 4.3. Kafka Consumer: Needs Both Topic and Group Permissions

~~~yaml
spring:
  kafka:
    consumer:
      group-id: inventory-projection
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
~~~

This consumer **inherits** shared `spring.kafka.properties` if configured that way. The consumer needs a Kafka principal authorized for:

- READ on topic `orders.events` (plus needed metadata permissions).
- READ on consumer group `inventory-projection`.
- Additional topic/group permissions if using transactional consumers, DLT publishing, or topic auto-creation per policy.

**A topic authorization failure does not mean wrong password.** A user can authenticate cleanly yet be rejected by the broker from reading a topic or group. Distinguish `SaslAuthenticationException` from `TopicAuthorizationException`, `GroupAuthorizationException`, and networking/TLS failures.

### 4.4. Should Producer and Consumer Share a Principal?

If one service both publishes and consumes, they may need different permissions. One shared principal simplifies config yet widens the blast radius:

~~~text
order-producer principal  -> WRITE orders.events
inventory-consumer        -> READ orders.events + READ group inventory-projection
dlq-relay                 -> READ retry-topic + WRITE dlq-topic
schema-registry-client    -> Separate permissions per Schema Registry provider
~~~

Separate principals per deployment/workload with least privilege whenever feasible. Kafka authorization has no built-in concept of "logged-in HTTP user" unless the application explicitly models end-user identity, auditing, and separate ACLs.

### 4.5. Kafka `OAUTHBEARER` and Managed IAM

Kafka has SASL `OAUTHBEARER`, yet it **is not identical** to HTTP Bearer headers. It requires a Kafka login callback handler/token retriever, broker listeners supporting token validation, and Kafka principal permissions. Cloud providers may supply proprietary IAM/managed auth mechanisms or callbacks; use the exact vendor configuration.

Never copy an OAuth2 access token from an inbound HTTP request into `sasl.jaas.config` expecting a Kafka broker to accept it: token audience, trust, validators, lifecycles, and Java client callbacks differ.

### 4.6. Kafka mTLS Principal

When the broker configures SSL client-auth, certificate identity can map to a principal via a broker principal builder/mapper. In that case:

- The client has a private key/cert.
- The broker trusts the right CA.
- Client-side hostname verification is still required.
- Topic/group ACLs bind to the **mapped principal**, not necessarily the raw certificate DN.
- Certificate rotation can change DN/SAN or principal mapping, breaking permissions even though the TLS handshake succeeds.

Kafka `SSL` mode has no SASL username/password by default. Under `SASL_SSL`, some clusters still enforce TLS client certificates; that is a cluster-specific policy, not the default meaning of the mode name.

### 4.7. Authentication and Producer ACK Are Separate Concerns

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant K as Kafka broker
    participant C as Consumer
    P->>K: TLS/SASL handshake
    K-->>P: Authentication accepted
    P->>K: Produce event E-100
    K->>K: Check topic WRITE ACL + append
    K-->>P: Producer ACK per acks configuration
    K->>C: Deliver record to consumer
    C->>C: Process with inbox/idempotency
~~~

Broker authentication establishes the **principal**, ACLs decide **where you can publish/read**, and producer ACK reports broker acknowledgment status per config. None of these steps proves the consumer committed its SQL transaction.

---

## 5. RabbitMQ: Username/Password, Virtual Host, and Three Permission Types

RabbitMQ does not use Kafka SASL property names. AMQP 0-9-1 typically uses username/password with broker-supported authentication mechanisms, virtual hosts, and permissions on exchanges/queues.

### 5.1. Spring Boot RabbitMQ Configuration

~~~yaml
spring:
  rabbitmq:
    host: rabbitmq.internal.example
    port: 5671
    virtual-host: /orders
    username: ${RABBITMQ_USERNAME}
    password: ${RABBITMQ_PASSWORD}
    ssl:
      enabled: true
      validate-server-certificate: true
      verify-hostname: true
~~~

This assumes the RabbitMQ broker has a TLS listener on port 5671, a certificate matching the hostname, and the user exists and has permissions on `/orders`.

**Version note:** `spring.rabbitmq.ssl.*` properties exist in supported Spring Boot releases, though trust/key store settings and SSL bundle integration can vary by Boot version. Check actual configuration metadata and test handshakes instead of copying Kafka properties into RabbitMQ.

### 5.2. Virtual Hosts Are Resource Namespaces

RabbitMQ's `virtual-host: /orders` is neither an HTTP path nor a Kubernetes namespace. A RabbitMQ user may authenticate successfully yet **lack permissions on the target vhost**.

RabbitMQ permissions for a user on each vhost typically consist of three regexes:

| Permission | Basic Meaning | Example Resource |
| --- | --- | --- |
| `configure` | Declare/delete/alter matching exchanges/queues | Queue `orders.retry` |
| `write` | Publish/send to matching exchanges/paths | Exchange `orders.exchange` |
| `read` | Consume/get/bind per broker operation policy | Queue `orders.events.inventory` |

Actual AMQP operation permissions can involve both source and destination during bindings or specific rules. Never rely purely on a queue name regex and assume publish/consume will succeed.

### 5.3. Separating Publisher and Consumer Privileges

Example policy:

~~~text
order-publisher:
  vhost=/orders
  configure=none (if topology is pre-provisioned)
  write=^orders\.exchange$
  read=none

inventory-consumer:
  vhost=/orders
  configure=none
  write=none (except error/DLQ publishing if needed)
  read=^orders\.events\.inventory$
~~~

This is an **illustrative permission model**, not a literal `rabbitmqctl set_permissions` command. In some setups, consumers need extra permissions for binding/declaring/queue maintenance. Provision topology using a dedicated operator/identity so runtime apps only hold minimal permissions.

### 5.4. RabbitMQ `guest` User and Environments

RabbitMQ's default `guest` account is restricted to loopback logins by default broker configuration. Never use `guest/guest` as a production credential, and never open remote access for `guest` just to bypass a login failure.

### 5.5. AMQPS TLS and Client Certificates

Enabling `ssl.enabled` makes the client verify server TLS. It **does not** automatically turn username/password auth into mTLS. For client certificate authentication:

1. The broker requests/verifies client certs.
2. The client configures a keystore/client private key.
3. The broker enables a mechanism/plugin mapping the certificate to a user (e.g., `EXTERNAL` depending on setup).
4. That user is granted vhost permissions.
5. Test cert rotation, revoked/expired certs, and permission denials.

**TLS success, RabbitMQ login success, queue READ permission, and publisher confirms** are four separate checkpoints.

### 5.6. `@RabbitListener` Does Not Grant Permissions

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventsListener {

    @RabbitListener(queues = "orders.events.inventory")
    public void handle(OrderEvent event) {
        // Business processing.
    }
}
~~~

`OrderEvent` is an application DTO. The listener container uses the service's `ConnectionFactory` and credentials; the annotation **grants no broker permissions**. Without READ permission on the queue/vhost, the listener fails at startup or during consumption. Likewise, receiving a message does not prove the consumer has permission to write to PostgreSQL.

### 5.7. DLQ/Publisher Confirms Are Separate from Authorization

Publisher confirms and consumer ACKs are **delivery/progress semantics**, not authentication mechanisms. A user with WRITE on an exchange but no `configure` permission on queues can still publish if topology is pre-provisioned; a successful publisher confirm does not prove the consumer committed to the DB.

---

## 6. PostgreSQL: Database User, `pg_hba.conf`, TLS, and GRANT

Database authentication spans multiple layers:

1. TLS server identity — the driver verifies the exact PostgreSQL endpoint.
2. Authentication method — PostgreSQL `pg_hba.conf` selects a rule matching connection/client/role/database.
3. Database role — the authenticated principal.
4. Authorization — `CONNECT`, `USAGE`, `SELECT`, `INSERT`, `UPDATE`, `EXECUTE`, and row-level policies.
5. Transaction — having permissions does not guarantee the SQL transaction committed.

### 6.1. Spring Boot JDBC with Hostname-Verifying TLS

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://orders-db.internal.example:5432/orders?sslmode=verify-full
    username: ${ORDERS_DB_USERNAME}
    password: ${ORDERS_DB_PASSWORD}
    hikari:
      maximum-pool-size: 12
      connection-timeout: 3000
      max-lifetime: 1800000
~~~

PostgreSQL JDBC's `sslmode=verify-full` enforces certificate chain and hostname verification. The client must trust the issuing CA, e.g. via Java truststore or driver-specific `sslrootcert` property depending on deployment. Never assume an internal CA is already in the JRE truststore.

**Never use** `sslmode=require` as equivalent to full server identity verification. `sslmode` values have distinct semantics (`disable`, `allow`, `prefer`, `require`, `verify-ca`, `verify-full`). To prevent MITM attacks, use `verify-full` with verified trust anchors.

### 6.2. `pg_hba.conf` Governs Authentication Method

Conceptual server-side example:

~~~text
# type   database  user         address           auth-method
hostssl  orders    order_app    10.20.0.0/16      scram-sha-256
~~~

This is illustrative server configuration and must pair with firewall/network policy and PostgreSQL TLS settings. Never edit production `pg_hba.conf` without change control. `hostssl` requires TLS; `scram-sha-256` specifies the password authentication protocol.

PostgreSQL also supports client certificates, GSS/SSPI, LDAP/PAM, and environment-specific plugins/IAM proxies. **Client `sslmode` does not select the DB authentication method**, and a SCRAM password does not verify server hostname certificates.

### 6.3. Database Roles and Schema/Table Privileges

An `order_app` role might authenticate yet still fail to read a table:

~~~sql
-- Administrative example, never run using the runtime application identity.
CREATE ROLE order_app LOGIN;

GRANT CONNECT ON DATABASE orders TO order_app;
GRANT USAGE ON SCHEMA app TO order_app;

GRANT SELECT, INSERT, UPDATE
ON TABLE app.orders, app.order_outbox
TO order_app;
~~~

`CREATE ROLE`/`GRANT` are DDL/DCL **executed by a database admin/migration provisioning role**; never let the app grant itself permissions at startup.

A role allowed to SELECT `orders` does not automatically have SELECT on all `public.*`, permission to run schema migrations, create extensions, or read PII in other schemas. PostgreSQL also enforces object ownership, sequences (for serial/identity columns), row-level security, and default privileges on future objects.

### 6.4. Migration Account vs. Runtime Account

~~~text
migration_db_identity:
  Needed DDL; controlled object creation/alteration.

order_app_runtime:
  SELECT/INSERT/UPDATE on required tables.
  No DROP TABLE/CREATE EXTENSION/ALTER ROLE.
~~~

Flyway/Liquibase can use dedicated credentials in a pipeline job or separate datasource/migration settings. Never grant DDL `SUPERUSER` to the application just to make startup migrations "easier".

### 6.5. Database Password vs. IAM Token

Some cloud DB providers issue short-lived IAM database authentication tokens. Tokens may be passed in the JDBC password slot or via a specific credential provider, yet they require a **provider-specific connector/refresh mechanism**; never treat an HTTP Pricing API OAuth2 token as a default DB password.

Hikari connection pools maintain long-lived connections; an expired token usually affects **opening new connections**, not necessarily invalidating every existing connection immediately. Verify provider policy, token refresh, and pool recycling on rotation.

### 6.6. When Are PostgreSQL Client Certificates Used?

A DB server can require a TLS client cert and/or map cert DN to a DB role. This requires matching `pg_hba.conf`, `pg_ident.conf` when mapping, client key/cert config, and database privileges. `sslmode=verify-full` only verifies the server—it **does not present a client certificate**.

### 6.7. SQLSTATE Helps Classify Failures

| SQLSTATE (PostgreSQL) | Category | Implication |
| --- | --- | --- |
| `28P01` | `invalid_password` | Wrong or rejected credentials |
| `28000` | `invalid_authorization_specification` | Auth/role/access context error |
| `42501` | `insufficient_privilege` | Login succeeded yet SQL privilege missing |
| `08001`/`08006` | Connection problems | Network/connection failure, not automatically wrong password |
| `40001` | Serialization failure | Transaction concurrency; safe to retry the **entire transaction** per contract |
| `40P01` | Deadlock detected | Concurrency/locking, not authentication |

Never retry bad-password logins thousands of times, which can lock/throttle accounts or mask rotation errors. On a SQL transaction commit timeout, the outcome may be **UNKNOWN** and require business key reconciliation rather than assuming rollback.

 
## 7. Redis: ACL Users and Key/Command Permissions

Redis does not use Kafka SASL SCRAM or PostgreSQL `pg_hba.conf`. With Redis 6+ ACLs, a connection typically sends **username/password** via `AUTH`/client handshake, and Redis checks the ACL user's command categories, command names, and key patterns.

### 7.1. Spring Boot Redis with ACL and TLS

A Spring Boot 3.x example using default Lettuce:

~~~yaml
spring:
  data:
    redis:
      host: redis.internal.example
      port: 6380
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
      timeout: 2s
      connect-timeout: 1s
~~~

This assumes Redis exposes a TLS listener on the chosen port and the Java client trusts the right certificate. Some Spring Boot 4.x releases alter property namespaces/starters; check exact metadata.

**Do not confuse:**

- `username/password` authenticate the Redis ACL principal.
- TLS encrypts and verifies the server; it does not grant key access rights.
- `host/port` and connection timeouts are network settings.
- TTL/cache names are application data settings, not auth permissions.
- `spring.data.redis.password` is not a JWT token by default.

### 7.2. Redis ACL Example

A least-privilege policy:

~~~text
ACL user: inventory_cache
Allowed key pattern: cache:inventory:*
Allowed commands: GET, SET, DEL, PING and
  protocol/client handshake commands needed by the driver.
No access: CONFIG, FLUSHALL, arbitrary KEYS, admin commands.
~~~

An admin command in a test environment might look like:

~~~text
ACL SETUSER inventory_cache on >REDACTED-PASSWORD ~cache:inventory:* +get +set +del +ping
~~~

**This is strictly illustrative**—never run literal passwords/ACLs in production. Redis clients may need extra commands for handshakes, Lua, `MGET`, `EXPIRE`, `UNLINK`, transactions, pub/sub, or Spring Cache internals; policies must reflect **the commands the application actually runs**. `REDIS_USERNAME`/password still require secret injection and rotation.

### 7.3. Redis `NOAUTH`, `WRONGPASS`, `NOPERM`

| Condition | Meaning |
| --- | --- |
| `NOAUTH Authentication required` | Redis session not yet authenticated per policy |
| `WRONGPASS invalid username-password pair or user is disabled` | Credentials/user rejected |
| `NOPERM ...` | Authenticated yet forbidden from running command/key |
| TLS handshake error | Transport/peer verification failed |
| Connection timeout | Network/availability issue, not proof of bad credentials |

Never retry `WRONGPASS` infinitely, and never disable ACLs or TLS to "fix" timeouts. When a Spring Cache operation fails with `NOPERM`, check the exact command and key pattern; new code might call `MGET`/`EXPIRE` that wasn't granted yet, rather than credentials being wrong.

### 7.4. Cache ACLs Do Not Replace Business Data Authorization

A Redis user permitted to read `cache:inventory:*` may still see multiple tenants if keys/values mix them. Cache keys must include appropriate tenant/namespace isolation, yet relying solely on a client-supplied tenant ID still lacks authorization. Business services must verify caller identity and SKU/tenant access **before reading/writing the cache**.

---

## 8. MongoDB and Other Databases: Principals and Authentication Databases

Each database has its own mechanism—do not treat everything as "a JDBC password".

### 8.1. MongoDB `authSource`

MongoDB often uses SCRAM-based authentication with credentials managed in an **authentication database**. Example URI injected via secret:

~~~yaml
spring:
  data:
    mongodb:
      uri: ${INVENTORY_MONGODB_URI}
~~~

Conceptual URI value:

~~~text
mongodb://inventory_app:<redacted>@mongo-1.internal:27017/inventory
  ?authSource=admin
  &tls=true
~~~

An actual URI must be **on one line**, percent-encode special characters in user/password, and include proper CA/hostname verification. Never log full URIs containing passwords. `authSource=admin` only means credentials authenticate against the `admin` database; it **does not** grant admin privileges on the `inventory` database.

MongoDB also supports X.509 authentication and cloud mechanisms per deployment; configure the exact driver/mechanism, roles, and TLS client certificate when required.

### 8.2. MongoDB Roles vs. PostgreSQL

MongoDB roles/privileges scope over databases/collections/actions; PostgreSQL uses roles, schemas, tables, sequences, and row-level security. Never mechanically translate SQL `GRANT SELECT` into MongoDB roles. When Spring Data MongoDB connects cleanly yet `find` or `update` fails as unauthorized, that is a resource privilege error, not necessarily invalid credentials.

### 8.3. MySQL/MariaDB and SQL Server

Other relational DBs have driver-specific TLS verification and auth mechanisms:

- MySQL has TLS `sslMode` such as `VERIFY_IDENTITY` in compatible Connector/J versions, along with authentication plugin policies.
- SQL Server JDBC has `encrypt`, `trustServerCertificate`, and hostname/certificate settings, plus SQL/AD authentication models.
- PostgreSQL has `sslmode=verify-full`.
- R2DBC does not necessarily share exact URL/property names with its JDBC counterpart.

**Never write a "universal" `ssl=true` for every driver.** Test each driver's server identity verification and endpoint rotation behavior.

---

## 9. HTTP Service Authentication: Bearer Tokens, mTLS, API Keys, and HMAC

HTTP services support multiple schemes; most modern Spring Boot apps use OAuth2/OIDC when token delegation or service-to-service client credentials are required.

### 9.1. Common Mechanisms

| Method | Client Sends | Server Validates | When Appropriate | Risks |
| --- | --- | --- | --- | --- |
| OAuth2 bearer access token | `Authorization: Bearer ...` | Signature/JWKS or introspection and policy | Service-to-service/user delegation | Token leak, wrong audience/scope |
| API key | Provider-contracted header | Lookup/hash/key policy | Simple API provider integrations | Long-lived key, lacks fine-grained claims |
| HTTP Basic | Base64 `username:password` in Authorization | Credential store | Legacy/intranet (still needs TLS) | Long-lived credentials/replay |
| HTTP mTLS | Client certificate/private key in TLS | Cert CA/identity mapping | Strong workload peer identity | Cert renewal/trust management |
| HMAC request signature | Signature, timestamp, nonce, signed bytes | Shared secret/key + canonical request | Webhooks/partner APIs | Clock skew, replay/canonicalization |
| Cookie/session | Session cookie | Session store/CSRF policy | Browser-oriented apps | Should not be reused as M2M credential |
| OAuth2 token exchange/on-behalf-of | Downstream-specific token | Authorization server + resource server | Cross-service user delegation | Confused-deputy/cross-audience |

### 9.2. `Authorization: Bearer` Is an Application Header

~~~http
GET /v1/prices/SKU-A HTTP/1.1
Host: pricing.internal.example
Authorization: Bearer <redacted>
Accept: application/json
~~~

An access token does not replace TLS; the HTTP client must still verify HTTPS hostname/certificate. Tokens leaked through logs/proxies can be replayed until expired/revoked. Never log raw Authorization headers.

**A Bearer header is not a Kafka `SASL_SSL` login** and not a PostgreSQL password. Those systems might support tokens in specialized setups, yet each requires its own protocol and audience configuration.

### 9.3. Client Credentials Are a **Service Identity**, Not End-User Identity

~~~mermaid
sequenceDiagram
    participant I as Inventory Service
    participant AS as OAuth Authorization Server
    participant P as Pricing Resource Server
    I->>AS: POST token endpoint: client_credentials + client auth
    AS->>AS: Validate client, policy, requested scopes
    AS-->>I: Access token (expiry, audience/scope semantics)
    I->>P: HTTPS GET + Bearer access token
    P->>P: Verify token + audience + scope + domain access
    P-->>I: Price result / 401 / 403
~~~

Never confuse `client_id` with the identity of the user logged into Order API. Client credentials represent the service/workload and permissions granted by the authorization server/provider.

### 9.4. Spring Boot OAuth2 Client Configuration

Spring Boot 3.x/Spring Security 6.x example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    // If the same service also accepts incoming bearer tokens:
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          pricing:
            provider: pricing-idp
            client-id: ${PRICING_CLIENT_ID}
            client-secret: ${PRICING_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope:
              - pricing.read
        provider:
          pricing-idp:
            token-uri: https://identity.internal.example/oauth2/token
~~~

The authorization server must provision the `pricing` client, allow the `client_credentials` grant, permit the requested scopes, and confirm the resource audience. The client requesting `pricing.read` does not prove the server **granted it** or that the resource server accepts it.

### 9.5. `RestClient` Outbound OAuth2 Token Interceptor

With **Spring Security versions providing `OAuth2ClientHttpRequestInterceptor` (e.g., Spring Security 6.4+)**, you can wire the OAuth2 authorized-client manager into `RestClient`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class PricingOAuthClientConfiguration {

    @Bean
    OAuth2AuthorizedClientManager serviceAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClientService) {

        OAuth2AuthorizedClientProvider provider =
                OAuth2AuthorizedClientProviderBuilder.builder()
                        .clientCredentials()
                        .build();

        var manager =
                new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                        registrations, authorizedClientService);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }

    @Bean
    RestClient pricingRestClient(
            RestClient.Builder builder,
            OAuth2AuthorizedClientManager serviceAuthorizedClientManager) {

        var oauthInterceptor =
                new OAuth2ClientHttpRequestInterceptor(
                        serviceAuthorizedClientManager);

        return builder
                .baseUrl("https://pricing.internal.example")
                .requestInterceptor(oauthInterceptor)
                .build();
    }
}
~~~

The classes used here have version constraints. On Boot 3.2/Spring Security 6.2 or Spring Boot 4/Spring Security 7, check the matching integration APIs and never assume helper interceptors exist identically in every version. `AuthorizedClientServiceOAuth2AuthorizedClientManager` fits **service/background jobs outside HTTP servlet requests**; if the workflow uses user delegation, the manager/principal model differs.

Example request attaching client registration/principal:

~~~java
import org.springframework.web.client.RestClient;

import static org.springframework.security.oauth2.client.web.client.RequestAttributeClientRegistrationIdResolver.clientRegistrationId;
import static org.springframework.security.oauth2.client.web.client.RequestAttributePrincipalResolver.principal;

public class PricingGateway {

    private final RestClient restClient;

    public PricingGateway(RestClient restClient) {
        this.restClient = restClient;
    }

    public PriceQuote quote(String sku) {
        return restClient.get()
                .uri("/v1/prices/{sku}", sku)
                .attributes(clientRegistrationId("pricing"))
                .attributes(principal("inventory-service"))
                .retrieve()
                .body(PriceQuote.class);
    }
}
~~~

`PriceQuote` is an application DTO. In real deployments, verify `principal(...)` and `clientRegistrationId(...)` helpers for your exact Spring Security version; the authenticated principal key must be chosen deliberately—never implicitly use an end-user ID for client credentials. The HTTP transport needs connect/read timeouts, TLS trust, and concurrent request limits.

### 9.6. Do Not Confuse Resource Server with OAuth2 Client

A service can both accept incoming HTTP bearer tokens and call other services:

| Component | Role | Spring Dependency/Config |
| --- | --- | --- |
| Inbound endpoint | **OAuth2 Resource Server** validates caller's access token | Resource server JWT/opaque validation |
| Outbound HTTP caller | **OAuth2 Client** acquires and attaches appropriate access tokens | Client registration/authorized-client manager |
| Authorization Server | Issues tokens, manages clients/scopes/claims | Independent IAM/IdP system |
| Downstream Resource Server | Validates tokens separately per audience/scope/domain | Pricing API policy |

Inbound resource server JWT example:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.internal.example/
~~~

This is only part of inbound resource server config; you still need an HTTP security chain, authorization policies, and version-appropriate audience validation. **Configuring `issuer-uri` does not create client credentials for calling the outbound Pricing API.**

### 9.7. Audience and Scope Are Two Different Checks

A token may contain:

~~~json
{
  "iss": "https://identity.internal.example/",
  "sub": "inventory-service",
  "aud": ["pricing-api"],
  "scope": "pricing.read",
  "exp": 1795260000
}
~~~

These are illustrative claims (not a signed token). Pricing API should validate issuer, signature/key, expiration, audience, scopes/roles, and domain policies like tenant/warehouse. A token issued for **Kafka gateway** or **Order API** must not be accepted by Pricing API merely because it shares the same issuer.

### 9.8. Never Forward Inbound Tokens Directly

~~~text
External user --JWT(aud=order-api)--> Order Service
Order Service --?--> Pricing API
~~~

Passing a user's bearer token directly downstream creates **wrong audience**, over-privilege, and confused deputy risks. If the downstream must act on the user's behalf, use a delegated access/token-exchange/on-behalf-of flow **supported by your IdP**, and enforce tenant/resource permissions. If the downstream only needs service-level pricing reference data, use a dedicated client-credentials token.

### 9.9. `WebClient` and Reactive Context

With Spring WebFlux, OAuth2 client integration uses dedicated filters/managers; `RestClient`'s servlet `OAuth2ClientHttpRequestInterceptor` does not replace the reactive `WebClient` security filter. Inside a Reactor chain, ensure principal/authorized client and Reactor context propagate cleanly rather than pulling `ThreadLocal` state from a servlet request inside a background consumer.

### 9.10. API Keys and HMAC

API keys typically use a provider-defined header:

~~~http
GET /v1/tax-rates HTTP/1.1
Host: tax.partner.example
X-API-Key: <redacted>
~~~

The header name `X-API-Key` **is not a universal standard**. Never embed keys in URLs/query strings where they land in logs, proxy analytics, and browser history. Rotations should use overlap windows if supported by the provider.

HMAC signing requires canonical method/path/query/body, timestamp, nonce, key identifier, and clock-skew tolerance per provider contract. Signing a body before Jackson serializes it—if actual bytes differ—breaks signature verification. Signatures do not replace TLS, authorization, or anti-replay storage.

---

## 10. Identity Model for Spring Integration Adapters

A Spring Integration flow can start from inbound HTTP, build a message, and route to AMQP, JDBC, or HTTP outbound adapters.

~~~mermaid
flowchart LR
    A["HTTP Gateway\nuser/token"] --> C["IntegrationFlow"]
    C --> P["JDBC Adapter\nDB role"]
    C --> K["Kafka Adapter\nKafka principal"]
    C --> R["RabbitMQ Adapter\nAMQP user/vhost"]
    C --> H["HTTP Outbound Gateway\nOAuth client token"]
    C --> D["Redis Cache Adapter\nACL user"]
~~~

**Adapter configurations primarily use the credentials of their underlying connection factories/clients**; they do not automatically "carry" user identities from message headers.

### 10.1. Headers Do Not Replace Authentication

An Integration `Message` may hold:

~~~text
headers:
  correlationId=...
  tenantId=...
  traceparent=...
payload:
  OrderConfirmed(...)
~~~

`tenantId` in a message header is **data** for routing/business policy, not a credential authenticated by Kafka/DB/HTTP. If messages come from a broker where untrusted parties can publish, an attacker can spoof headers. Verify publisher identity via broker ACLs, validate payload/signatures if needed, and enforce tenant authorization in the consumer.

### 10.2. Translating Identity Across Trust Boundaries

A service authenticates to Kafka as principal `inventory-consumer` and then calls the HTTP Pricing API as OAuth client `inventory-service`:

- Kafka only knows the principal has READ on the topic/group.
- Pricing only knows the OAuth client token (or delegated user if actually present).
- Database only knows the `inventory_app` DB role.
- The application must audit `eventId`, `operationId`, `tenantId`, and causal links across stages.

Never claim "Kafka authenticated the message so inbound data needs no validation": the broker authenticates the **connection principal**, not the validity of every business field in the event.

### 10.3. Never Serialize Secrets into Outbox/Inbox

An outbox should store **durable business intent**:

~~~json
{
  "eventId": "8e6d6e12-d0e2-4b15-8865-1b53a6bc7b39",
  "aggregateId": "ORD-100",
  "eventType": "OrderConfirmed",
  "schemaVersion": 2,
  "payload": {"orderId": "ORD-100", "amountMinor": 150000}
}
~~~

Never put Kafka passwords, OAuth access tokens, DB passwords, or API keys inside persisted event payloads. The relay acquires **fresh credentials from runtime secret sources** when dispatching. If an outbox job retries days later, an old access token is virtually guaranteed to be expired.

### 10.4. Service Account vs. Business Actor

A command may originate from end-user `user-123` yet execute under the inventory service principal. Audit them separately:

~~~text
transportPrincipal: inventory-service
businessActor: user-123 (verified upstream, with trust chain)
operationId: K-100
tenant: tenant-A
~~~

Never treat an actor passed in a message as an "authenticated end-user" without provenance verification and a policy accepting that trust chain. Minimize user context fields and protect privacy.

---

## 11. Secrets: Injection, Scope, Rotation, and Lifecycle

### 11.1. Never Hardcode

Wrong:

~~~yaml
spring:
  datasource:
    password: my-secret-password

  kafka:
    properties:
      sasl.jaas.config: org.apache.kafka.common.security.scram.ScramLoginModule required username="admin" password="admin123";
~~~

YAML committed to a repository gets replicated into build logs, container images, and backups. Secrets must also stay out of Spring Actuator config/env endpoints and exception messages.

### 11.2. Externalized Configuration

~~~yaml
spring:
  datasource:
    username: ${ORDERS_DB_USERNAME}
    password: ${ORDERS_DB_PASSWORD}

  rabbitmq:
    username: ${RABBITMQ_USERNAME}
    password: ${RABBITMQ_PASSWORD}

  data:
    redis:
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
~~~

Variables are injected by the orchestrator/secret manager; never commit `.env` files containing secrets to Git. In Kubernetes, secrets can be mounted files or injected env vars; protect RBAC, encryption at rest, auditing, and pod permissions. Env vars remain exposed to process inspection/crash dumps/diagnostics, so do not treat them as unconditionally invulnerable.

### 11.3. Rotation Is More Than Editing the Secret Store

Updating a password/certificate in a secret manager **does not mean** running clients immediately use the new value.

| Client | Rotation Behavior to Verify |
| --- | --- |
| Kafka Java producer/consumer | SASL credential config may be captured at client creation; requires client/container restart/recreation |
| RabbitMQ `CachingConnectionFactory` | Open connections hold old credentials; requires recovery/recreation |
| HikariCP JDBC pool | Existing connections may persist; new connections need the new credentials |
| Redis Lettuce pool/connection | Reconnects may require new credentials |
| `RestClient` OAuth2 | Access tokens are cached until expiry; client credentials re-acquire via manager |
| mTLS client | TLS sessions/private key loading may require reload/connection recycling |

Rotation workflows need **old/new overlap** where backends support it, verification of new connections, healthy rollouts, and rollback. Never revoke the old credential while workers still depend on it unless an active incident demands immediate revocation.

### 11.4. Secret Scope and Environment Isolation

Create distinct identities for:

- Dev/staging/prod.
- Region/cluster when blast radius needs isolation.
- Producer vs. consumer when permissions differ.
- Runtime app vs. schema migration jobs.
- Human administrators vs. automation.
- HTTP client registrations per downstream audience/scope.

Never keep one "master integration password" accessing Kafka, the database, RabbitMQ, and Pricing API.

### 11.5. Certificate Rotation

TLS certificates involve trust chains, SANs, expiries, and private keys; you must:

1. Issue new certs with matching SANs/CAs.
2. Ensure clients trust the new CA before servers switch if the CA changes.
3. Deploy the new server cert and monitor handshakes.
4. Deploy/rotate client certs for mTLS per policy.
5. Recycle connections/sessions as required.
6. Remove old CAs/credentials after the overlap window.
7. Test negative cases for revoked/expired/unknown-signer certs.

Never work around cert expiry by disabling hostname verification or enabling trust-all.

---

## 12. Do Not Confuse Authentication Failures with Connectivity or Authorization Failures

Applications often lump all errors into `ConnectionFailedException`. That is a mistake because retry policies differ per failure class.

| Connection Point | Authentication Failure | Authorization Failure | Transport/Capacity Failure |
| --- | --- | --- | --- |
| Kafka | `SaslAuthenticationException` | Topic/group authorization exception | Broker unavailable, TLS handshake, timeout |
| RabbitMQ | Login rejected/AMQP `ACCESS_REFUSED` (depending on handshake) | Vhost/queue/exchange access denied | Connection reset, heartbeat timeout |
| PostgreSQL | SQLSTATE `28P01` | SQLSTATE `42501` | SQLSTATE `08xxx`, pool timeout |
| Redis | `NOAUTH`, `WRONGPASS` | `NOPERM` | Connection refused, TLS timeout |
| MongoDB | `AuthenticationException`/code 18 per driver | Unauthorized/code 13 per driver | Server selection timeout |
| HTTP API | HTTP 401 or provider auth error | HTTP 403/`insufficient_scope` | 502/503/504, DNS, TLS, read timeout |
| TLS/mTLS | Cert invalid/untrusted (TLS layer) | TLS principal authenticated yet app ACL denies | TCP refused, DNS failure |

**Watch out for error codes:** a proxy/API may return non-standard 401/403 codes; RabbitMQ can return `ACCESS_REFUSED` during both login handshakes and permission checks. Inspect **phase, broker logs, and root cause**, not just exception class names.

### 12.1. HTTP 401 and 403

- **401 Unauthorized:** request lacks valid authentication credentials per HTTP auth semantics; responses typically include a challenge.
- **403 Forbidden:** server understood the request yet refuses it due to authorization policy; authenticated clients can still receive 403.
- OAuth bearer errors may carry `invalid_token`, `insufficient_scope`, and challenge details per spec.

A 401 caused by an expired token can be resolved by **refreshing the token and bounded retrying**. A 403 caused by missing scope/tenant needs provisioning/authorization fixes, not aggressive retries. Never refresh tokens in a loop to bypass security policies.

### 12.2. TLS Errors

`SSLHandshakeException` can be caused by:

- Client does not trust CA/server chain.
- Hostname missing from SAN.
- Certificate expired/not yet valid.
- Unsupported TLS version/cipher.
- Server requires client certificate yet client sent none.
- Client certificate chain untrusted by server.
- Revocation/identity mapping policy.

A valid SASL password cannot fix a TLS handshake failure occurring **before** the authentication protocol completes.

### 12.3. Pool Connection Failures

Hikari connection-acquisition timeouts or Kafka network disconnects can occur after credentials are accepted. Do not rotate passwords blindly when the real problem is an exhausted pool or unavailable broker quorum.

### 12.4. Unknown Business Outcomes

Even when authenticated and authorized, a request may execute and then lose its response:

~~~mermaid
sequenceDiagram
    participant C as Integration Service
    participant A as HTTP Partner
    participant D as Partner DB
    C->>A: HTTPS POST /reserve + Bearer token + Idempotency-Key K-100
    A->>A: Validate token, scope, tenant
    A->>D: INSERT reservation
    D-->>A: COMMIT
    A--xC: Response lost
    C->>C: Network timeout → UNKNOWN
    C->>A: Lookup status / replay same K-100
    A-->>C: Stored receipt
~~~

An authentication failure before application execution can be classified per contract, whereas **a timeout after sending a command** does not prove transaction rollback. Keep a stable `operationId`, target idempotency, and status lookup; never generate a new command ID after a read timeout.

---

## 13. Cause-Based Retry Policy

| Error Group | Auto-Retry? | Condition |
| --- | --- | --- |
| Invalid password/API key | No hot retries | Refresh secret/config, verify provisioning |
| Expired OAuth access token | Possibly once | Manager acquires fresh token; never bypass forbidden |
| Missing Kafka topic/group ACL | No hot retries | Operator grants exact permissions |
| Missing RabbitMQ vhost/read/write | No hot retries | Fix broker permissions |
| DB SQLSTATE `42501` | No hot retries | Fix GRANT/role |
| Redis `NOPERM` | No hot retries | Fix ACL command/key policy |
| TLS cert expired/SAN mismatch | No hot retries | Fix trust/PKI; never disable verification |
| Network connection refused/503 | Bounded retries | Exponential backoff/jitter/deadline |
| HTTP 429 | Possibly | Honor `Retry-After` and rate limits |
| SQL deadlock/serialization retry | Possibly | Retry **entire transaction**, keep stable business identity |
| Timeout after sending POST/COMMIT | Outcome `UNKNOWN` | Query status or idempotent replay |
| Malformed payload/schema mismatch | No | Fix contract |
| Kafka consumer rebalance | Framework handling | Preserve offset/inbox semantics; do not turn into auth retry |

Retries must have a **cross-layer budget**. Never let the HTTP adapter retry 3 times, the business workflow retry 5 times, and the broker listener retry 10 times without tracking total maximum attempts. Auth failures usually require **human/operator intervention or secret rotation**, not a thundering herd.

---

## 14. Testing Security at the Right Boundaries, Not Just Service Methods

### 14.1. Required Test Matrix

| ID | Environment | Fault Injection | Expectation |
| --- | --- | --- | --- |
| SEC-01 | Kafka producer | Wrong SASL password | Authentication fails, no publish |
| SEC-02 | Kafka producer | Valid principal, no WRITE ACL | Authorization denied, no message |
| SEC-03 | Kafka consumer | Valid principal, no group READ | Cannot join/read group |
| SEC-04 | Kafka TLS | Untrusted CA/SAN mismatch | Handshake fails, verification stays enabled |
| SEC-05 | RabbitMQ | Wrong username/password | Login fails |
| SEC-06 | RabbitMQ | Valid user, wrong vhost | Vhost access denied |
| SEC-07 | RabbitMQ | Valid user, no queue READ | Consume rejected |
| SEC-08 | PostgreSQL | Wrong password | SQLSTATE auth failure |
| SEC-09 | PostgreSQL | Valid login, no table SELECT | SQLSTATE insufficient privilege |
| SEC-10 | PostgreSQL TLS | Server cert wrong hostname | `verify-full` rejects |
| SEC-11 | Redis | Wrong ACL password | `WRONGPASS` |
| SEC-12 | Redis | Valid ACL yet forbidden key/command | `NOPERM` |
| SEC-13 | HTTP client | Missing bearer token | 401/challenge |
| SEC-14 | HTTP client | Valid token, wrong audience/scope | Rejected per API policy |
| SEC-15 | HTTP client | Expired token | Refreshed/re-acquired cleanly, no infinite retry |
| SEC-16 | HTTP mTLS | Missing/untrusted client certificate | TLS/client identity rejected |
| SEC-17 | Multi-hop | Kafka message forged `tenantId` | Consumer domain authorization rejects |
| SEC-18 | Credential rotation | New secret active, old revoked | New connections succeed; no leaks |
| SEC-19 | Integration | After COMMIT, response lost | `UNKNOWN` + idempotent reconciliation |
| SEC-20 | Logging | Auth fails with secret-bearing config | No credentials/tokens in logs |

### 14.2. Kafka Tests Against a Real Broker

Use Kafka Testcontainers or a managed test environment configured with TLS/SASL/ACLs. Embedded/mock Kafka producers do not prove broker authorization.

Acceptance case:

~~~text
Given Kafka principal order-producer has WRITE orders.events
When client publishes event E-100
Then broker acknowledges according to acks configuration

Given same principal lacks WRITE billing.events
When client publishes to billing.events
Then broker rejects by ACL
And no unauthorized message appears
And service does not retry indefinitely
~~~

If the test environment does not enable a Kafka authorizer/ACLs, a "no WRITE ACL" test proves nothing. Provision real broker security for negative tests.

### 14.3. RabbitMQ Tests

Use RabbitMQ Testcontainers with users/vhosts/permissions created by bootstrap/test admin. Independently test publisher WRITE-only, consumer READ-only, missing vhost, and TLS cases.

Never assert that a `@RabbitListener` Java method processes a payload and conclude authentication is secure. Listener authentication happens during AMQP connection/channel setup.

### 14.4. PostgreSQL Tests

With PostgreSQL Testcontainers, provision at least:

- `order_app` runtime user with CRUD only on needed tables.
- `order_migrator` separate DDL identity.
- `unauthorized_app` lacking SELECT on target tables.
- Wrong password and SQLSTATE failure cases.
- TLS verification test in an appropriately TLS-enabled environment.

A practical test:

~~~sql
-- Executed by provisioning/migration identity:
GRANT CONNECT ON DATABASE orders TO order_app;
GRANT USAGE ON SCHEMA app TO order_app;
GRANT SELECT ON TABLE app.orders TO order_app;
REVOKE ALL ON TABLE app.secrets FROM order_app;
~~~

Then execute JDBC as the runtime user, asserting `app.orders` is readable while `app.secrets` is denied. Apply `GRANT`/`REVOKE` in a dedicated test fixture, never inside app business methods.

### 14.5. HTTP OAuth2 Contract Tests

Use a mock authorization server/token endpoint + MockWebServer/WireMock for downstream:

1. Client credentials token request uses right client registration, grant type, and auth.
2. Gateway **does not send the business request** if token acquisition fails.
3. Resource server receives the right token audience/scope and expiry.
4. Token lacking scope receives 403; client does not hot-retry.
5. Expired access token is re-acquired by manager per policy.
6. End-user token with wrong audience is never forwarded.
7. HTTP redirect to an unrelated origin never receives Authorization headers/secrets per policy.
8. Timeout after side effect preserves stable `Idempotency-Key`.

With Spring Security, avoid testing solely by mocking `SecurityContextHolder` and assuming the outbound manager/HTTP interceptor works; include a test with real `RestClient`/`WebClient` wiring and a token endpoint stub.

### 14.6. Testing mTLS

Generate **test-only** CAs and certificates with SANs matching test hosts, keeping private keys inside the ephemeral test environment:

- Trusted CA + matching hostname: handshake OK.
- Unknown CA: fail.
- Wrong hostname/SAN: fail.
- Expired/not-yet-valid: fail.
- Missing client cert when server `needClientAuth`: fail.
- Valid client cert lacking application authorization: handshake OK, business denied.
- Rotation: CA/trust overlap, new connection succeeds.

Never place shared test private keys/certificates into production secret stores; never disable validation to make tests "succeed".

### 14.7. When Testcontainers Is Not Enough

Kafka TLS/SASL + ACLs or RabbitMQ certificate auth require real server configuration. If CI cannot run them due to privilege/PKI constraints, explicitly document the test coverage gap and add isolated staging security regressions; **never mark a negative auth test PASS when broker security was actually disabled**.

---

## 15. Monitoring and Classifying Security Signals

### 15.1. Suggested Metrics

| Metric/Event | Meaning |
| --- | --- |
| `integration.authn.failure` by target | Credential/token/certificate failure |
| `integration.authz.denied` by resource class | Principal lacks permission |
| `integration.tls.handshake.failure` | Server trust/client cert failure |
| `integration.oauth.token.acquire.failure` | OAuth2 client registration/token endpoint |
| `integration.oauth.token.refresh` | Token lifecycle |
| `integration.kafka.topic.authorization.denied` | Kafka topic ACL |
| `integration.kafka.group.authorization.denied` | Consumer group permission |
| `integration.rabbitmq.vhost.denied` | RabbitMQ vhost access |
| `integration.db.insufficient_privilege` | SQL GRANT/RLS |
| `integration.redis.acl.denied` | Redis command/key ACL |
| `integration.connection.retries` | Connection retry activity |
| `integration.business.outcome_unknown` | Remote result unconfirmed |
| `integration.secret.rotation.failed` | New credential activation issue |

These metric names are **suggested application instrumentation**, not claims that Spring Actuator/Micrometer provides all of them out of the box. Frameworks/client libraries have their own logs/metrics; map them into a consistent taxonomy without leaking secrets.

### 15.2. Cardinality and Privacy

Prometheus tags should use `target_type=kafka|rabbitmq|jdbc|redis|http`, `downstream=pricing`, `error_category=authentication|authorization|tls|network`, `environment=prod`. **Never attach access tokens, passwords, full certificate subjects, raw SQL, emails, `operationId`, or high-cardinality usernames to metric labels.**

Structured logs may contain:

~~~json
{
  "service": "inventory-service",
  "downstream": "pricing",
  "boundary": "http-oauth2",
  "errorCategory": "authorization",
  "operationId": "K-100",
  "action": "price.read",
  "result": "denied"
}
~~~

Logging an `operationId` still requires proper access control and retention; keep it out of metric labels. Never log Authorization headers, OAuth client secrets, password-bearing SASL JAAS configs, secret-bearing full JDBC URLs, or Redis `AUTH` values.

### 15.3. Alerts by Root Cause

- Spike in Kafka auth failures **right after rollout** → secret/config/provider mismatch.
- RabbitMQ vhost denied → wrong vhost or missing permission provisioning.
- SQLSTATE `42501` → missing DB grants, not Hikari pool tuning.
- HTTP 403 on a single tenant → domain permission/scope policy.
- TLS handshake failures rising on CA rotation day → trust overlap/hostname/SAN issue.
- Token acquisition failures → IdP availability/client secret rotation.
- Rising connection timeouts alongside Hikari pending threads → capacity issue, not automatically auth.

An alert saying only "connection failed" forces operators to guess across systems; retain `phase`/`target` and a sanitized error category.

---

## 16. Runbook for Connection Authentication Incidents

| Symptom | First Check | What NOT to Do |
| --- | --- | --- |
| Kafka SASL login rejected | SASL mechanism, listener, principal, secret, JAAS formatting | Disable SASL / switch to PLAINTEXT |
| Kafka `TopicAuthorizationException` | Topic ACL principal, resource name, and operation | Grant cluster admin to app |
| Kafka `GroupAuthorizationException` | Group ID, consumer group ACL | Grant cluster-wide group admin |
| Kafka SSL handshake failure | CA, SAN, hostname, TLS version, client cert policy | Disable endpoint identification |
| RabbitMQ login rejected | Username/password, vhost, mechanism, guest restrictions | Enable remote `guest` login |
| RabbitMQ `ACCESS_REFUSED` on declare/bind | configure/write/read resource permissions | Grant `.*` across whole vhost unreviewed |
| PostgreSQL `28P01` | DB role/password, provider token/rotation | Hot-retry logins |
| PostgreSQL `42501` | Schema USAGE/table GRANT/RLS/sequence privileges | Run runtime as `SUPERUSER` |
| PostgreSQL certificate verify failed | `sslmode=verify-full`, root CA, hostname | Downgrade to `sslmode=disable` |
| Redis `WRONGPASS` | ACL username/password, disabled user | Disable ACLs |
| Redis `NOPERM` | Commands/keys actually used by application | Grant `+@all ~*` indiscriminately |
| MongoDB unauthorized | `authSource`, roles, db/collection | Grant `root` role |
| HTTP 401 `invalid_token` | Expiry, issuer, JWKS, audience, token acquisition | Forward token from another audience |
| HTTP 403 `insufficient_scope` | Scope/role/tenant policy | Retry infinitely |
| OAuth token endpoint 401 | Client registration secret, grant/client auth mode | Log client secret to debug |
| mTLS client cert rejected | Client key/cert/CA, EKU, SAN/mapping | Trust all certificates |
| Cache/DB timeout | Network/pool/time budget | Rotate secrets without evidence |
| Response lost after remote COMMIT | Operation ID, remote receipt/status | Mint a new command with a fresh UUID |

### 16.1. Systematic Diagnostic Workflow

1. **Pinpoint the exact boundary:** Kafka producer, Kafka consumer, RabbitMQ, PostgreSQL, Redis, or Pricing HTTP API?
2. **Pinpoint the phase:** DNS/TCP → TLS handshake → authentication → authorization → business command → acknowledgment.
3. **Check the real identity:** service principal/DB role/OAuth client registration, not pod name.
4. **Check secrets/CAs** without printing values: source, version, mounts, permissions, expiry/rotation.
5. **Check backend policies:** topic/group ACLs, vhost permissions, SQL GRANTs, Redis ACLs, HTTP audience/scope/tenant.
6. **Verify networking** and DNS/SAN/hostname if failing prior to authentication.
7. **Check pools/capacity** if intermittent and backend auth logs show no rejections.
8. **Classify retries:** authz/authn permanent, bounded token refresh, transient network, unknown business outcome.
9. **Reproduce with a minimal test identity** in a safe environment without production secrets.
10. **Audit and fix the policy** at the right scope without granting blanket admin or weakening TLS.
11. **Verify after rotation/rollout** on new connections, not just existing pooled sessions.
12. **Protect business outcomes:** if the request may have committed, reconcile using a stable `operationId`.

---

## 17. Case Study: Order Service → Kafka → Inventory → PostgreSQL → Pricing API

### 17.1. Requirement

An `OrderConfirmed` event originates from Order Service:

~~~json
{
  "eventId": "e1001f0a-27e7-4bf8-aee6-8e49ab7523a7",
  "orderId": "ORD-100",
  "tenantId": "TENANT-A",
  "amountMinor": 150000,
  "schemaVersion": 2
}
~~~

Flow:

~~~mermaid
sequenceDiagram
    participant O as Order Service
    participant K as Kafka
    participant I as Inventory Service
    participant D as Inventory DB
    participant AS as OAuth IdP
    participant P as Pricing API
    O->>K: SASL_SSL producer: event E-100
    K->>K: Check topic WRITE ACL
    K-->>O: ACK
    K->>I: Consumer group: deliver E-100
    I->>I: Validate schema + authenticated service trust
    I->>D: JDBC role inventory_app: inbox + reserve
    D-->>I: COMMIT
    I->>AS: client_credentials pricing.read
    AS-->>I: Token aud=pricing-api
    I->>P: HTTPS Bearer token, tenant policy
    P-->>I: Pricing result
    I->>K: Commit offset/ACK according to Kafka listener policy
~~~

In real design, **calling the Pricing API and committing the offset** must follow the business/transaction contract. If the remote Pricing call has side effects, use outbox/saga/idempotency rather than holding a PostgreSQL transaction open across multi-second HTTP calls. The diagram shows boundaries, **not a cross-system ACID transaction**.

### 17.2. Credential Inventory

| Identity | Used For | Permitted Actions Only |
| --- | --- | --- |
| `order-producer` | Kafka | WRITE `orders.confirmed` |
| `inventory-consumer` | Kafka | READ `orders.confirmed` + READ group `inventory-v2` |
| `inventory_app` | PostgreSQL | CRUD on inventory/inbox/outbox tables |
| `inventory_cache` | Redis | Key namespace `cache:inventory:*` and needed commands |
| `inventory-pricing-client` | OAuth2 | Acquire token with `pricing.read` and Pricing API audience |
| `inventory-migrator` | PostgreSQL migration | Controlled DDL via deployment job |

Never use `order-producer` as a DB user or `inventory_app` as an HTTP bearer token. Permissions on the Kafka hop never bleed into HTTP.

### 17.3. Targeted Failure Tests

**Scenario A — Kafka READ permission revoked:**

~~~text
Given consumer authenticates with valid SCRAM secret
When Kafka denies READ on topic orders.confirmed
Then listener cannot process records
And metrics show authorization denied
And service does not endlessly reconnect with same permission error
~~~

**Scenario B — PostgreSQL role lacks INSERT:**

~~~text
Given Kafka consumer authenticated and authorized
When INSERT inventory_reservations is denied
Then local SQL transaction rolls back
And Kafka offset is not advanced as business-applied
And message can be retried/parked according to listener policy
~~~

**Scenario C — Pricing scope missing:**

~~~text
Given Inventory authenticates to Pricing OAuth token endpoint
When token lacks pricing.read scope
Then Pricing denies the read
And application records authz failure without leaking token
And retry does not turn the event into a duplicate reservation
~~~

**Scenario D — Response lost after commit:**

~~~text
Given Inventory DB COMMIT for operationId K-100
When Pricing API response is lost or Kafka offset commit fails
Then outcome/progress is reconciled using stable identities
And duplicate event processing is blocked by inbox/unique constraint
~~~

**This is the vital link between security and reliability:** Having permission to receive an event does not guarantee every downstream action succeeds; auth/permission failures can strike **mid-workflow** and must be handled along transaction/idempotency boundaries.

---

## 18. Common Anti-Patterns

| Anti-Pattern | Why Is It Wrong? | Right Approach |
| --- | --- | --- |
| Sharing one password across Kafka, DB, RabbitMQ, HTTP | Huge blast radius, wrong protocol model | Service identity/secret per boundary |
| Enabling TLS and assuming auth/ACLs are done | TLS transport ≠ application authorization | Verify principal and resource permissions |
| Checking CA only, disabling hostname verification | MITM/wrong peer risk | CA + SAN/hostname validation |
| Using a truststore as client mTLS identity | Truststores do not hold client private keys | Supply client key/cert when server requires it |
| Configuring Kafka `SASL_SSL` and assuming mTLS is required | SASL and TLS client auth are distinct | Match mechanism to broker listener |
| Assuming Kafka producer `acks=all` means consumer applied | Broker ACK ≠ DB COMMIT | Inbox/consumer processing receipt |
| Granting Kafka consumer topic READ without group READ | Separate resource ACL | Provision both topic and group ACLs |
| Giving RabbitMQ user login without vhost access | Credentials ≠ vhost permission | Per-vhost grants |
| Giving RabbitMQ app `configure/write/read=.*` unconditionally | Over-privileged | Provision topology separately; least privilege |
| Using PostgreSQL `postgres` superuser for the app | Broad DDL/admin power | Dedicated runtime role |
| Treating `sslmode=require` like `verify-full` | Does not verify hostname like `verify-full` | Full cert/hostname verification |
| Assuming Redis `AUTH` grants access to all keys | ACLs scope commands/patterns | Prefix and command restrictions |
| Reading `tenantId` from Kafka header as auth identity | Headers can be spoofed | Domain authz and provenance policy |
| Forwarding inbound JWTs across all downstreams | Wrong audience/confused deputy | Service tokens/token exchange |
| Using OAuth2 resource server config to make outbound HTTP calls | Inbound verifier does not acquire tokens | OAuth2 client registration/manager |
| Hardcoding access tokens in `application.yml` | Expires/leaks secrets | Token acquisition/refresh |
| Storing access tokens in the outbox | Stale tokens/PII leakage | Store business intent, fetch credential at relay time |
| Logging full JDBC URLs, SASL JAAS, Authorization headers | Leaks secrets | Sanitized diagnostics |
| Retrying 401/403/28P01/NOPERM continuously | Cannot fix permissions; causes outages | Fail fast + operator action |
| Disabling TLS/mTLS on handshake errors | Weakens security, exposes credentials | Fix cert/CA/SAN |
| Testing only mocked services without enabling broker ACLs | Tests miss real authz | Secure integration tests |
| Rotating secrets without recycling connections | Clients keep using old credentials | Rotation rollout/new-connection validation |
| Treating a timeout after POST as un-committed | Remote outcome is `UNKNOWN` | Stable key/status lookup |
| Using the runtime account to run migrations | Long-lived elevated privileges | Separate migration identity |

---

## 19. Production Checklist

### A. Identify Boundaries

- [ ] Inventory all outbound/inbound connections by caller, target, and environment.
- [ ] Separate transport TLS, client authentication, and resource authorization.
- [ ] Assign dedicated service principals for Kafka/Rabbit/DB/Redis/HTTP as needed.
- [ ] Never reuse credentials or forward tokens to the wrong audience.
- [ ] Enforce end-user authorization and workload authentication independently.
- [ ] Never trust tenant/correlation headers as authenticated credentials.

### B. Kafka and RabbitMQ

- [ ] Kafka `security.protocol`, `sasl.mechanism`, JAAS/provider, and TLS trust are accurate.
- [ ] Kafka producer topic WRITE and consumer topic/group READ are least-privilege.
- [ ] Never use `SASL_PLAINTEXT` when credentials cross untrusted networks.
- [ ] Kafka mTLS identity mapping (if used) is tested across certificate rotation.
- [ ] RabbitMQ uses the right vhost and `configure`/`write`/`read` permissions.
- [ ] RabbitMQ TLS verifies server cert/hostname; remote `guest` is disabled.
- [ ] Publisher confirms/consumer ACKs are treated as delivery semantics, not business auth.

### C. Databases and Caches

- [ ] PostgreSQL `sslmode=verify-full` with matching CA/SAN in TLS-required environments.
- [ ] Runtime DB role has no unnecessary DDL/admin privileges.
- [ ] Migration identity is independent of the runtime role.
- [ ] Database permissions cover exact schemas/tables/sequences/RLS.
- [ ] R2DBC/JDBC/MongoDB/Redis use driver-specific auth/TLS configurations.
- [ ] Redis ACL user has only required key patterns/commands.
- [ ] Caches never replace authoritative business authorization.

### D. HTTP Services

- [ ] OAuth2 client credentials registration/manager fits the security framework version.
- [ ] Client tokens match issuer, audience, scopes, expiry, and target service.
- [ ] Resource server independently validates tokens and domain permissions.
- [ ] Token acquisition/cache/refresh/revocation have runbooks.
- [ ] Never forward inbound JWTs downstream to unintended audiences.
- [ ] API keys/HMAC/mTLS have proper canonicalization, verification, and rotation.
- [ ] HTTPS hostname/server certificates are verified; never trust-all.

### E. Secrets, Reliability, and Operations

- [ ] Secret injection comes from secret manager/orchestrator, never hardcoded.
- [ ] Client keys, passwords, and tokens never appear in logs, metrics, outbox, or Git.
- [ ] Credential/certificate rotation overlap and new-connection tests exist.
- [ ] Never hot-retry permanent authentication/authorization failures.
- [ ] Transient network retries have budget/backoff/jitter/deadlines.
- [ ] Commands use stable `operationId`/idempotency and `UNKNOWN` reconciliation.
- [ ] Secure integration tests cover invalid auth, denied ACLs, wrong SANs, and wrong audiences.
- [ ] Logs/metrics classify authn, authz, TLS, network, and business commits.
- [ ] Alerts exist for expiring credentials/certificates and permission drift.
- [ ] Incident runbooks never require disabling security to recover.

**Remember:** Kafka and RabbitMQ authenticate a **broker client principal** and enforce permissions on topics/groups or vhosts/exchanges/queues; PostgreSQL authenticates a **database role** and checks `GRANT`/RLS; Redis uses an **ACL user** with command/key permissions; HTTP services use **bearer tokens, API keys, HMAC, or mTLS** and check audience/scope/resource policies. TLS protects transport and authenticates servers, and mTLS can authenticate clients; no single mechanism by itself proves a **remote business transaction** completed. In Spring Boot Integration, configure **each boundary using its native protocol**, apply least privilege, manage secret rotation, and test authentication, authorization, and transport failure cases.

## References

- [Spring Boot — Kafka](https://docs.spring.io/spring-boot/reference/messaging/kafka.html): configuring `spring.kafka.*`, producers, and consumers.
- [Apache Kafka — Security](https://kafka.apache.org/documentation/#security): SASL, TLS, ACLs, and security protocols.
- [Apache Kafka — Authorization and ACLs](https://kafka.apache.org/documentation/#security_authz): resource operations/permissions.
- [Spring Boot — AMQP](https://docs.spring.io/spring-boot/reference/messaging/amqp.html): RabbitMQ `ConnectionFactory` and SSL config.
- [RabbitMQ — Authentication](https://www.rabbitmq.com/docs/access-control): users, authentication mechanisms, and authorization.
- [RabbitMQ — TLS](https://www.rabbitmq.com/docs/ssl): server/client TLS certificates and validation.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): delivery acknowledgement semantics.
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): `DataSource`/Hikari/JDBC configuration.
- [PostgreSQL — Client Authentication](https://www.postgresql.org/docs/current/client-authentication.html): `pg_hba.conf` and supported auth mechanisms.
- [PostgreSQL — Database Roles and Privileges](https://www.postgresql.org/docs/current/user-manag.html): roles, privileges, and grants.
- [PostgreSQL JDBC — SSL](https://jdbc.postgresql.org/documentation/ssl/): JDBC TLS trust and `sslmode`.
- [Redis — ACL](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/): Redis user/command/key permissions.
- [Spring Data Redis — Reference](https://docs.spring.io/spring-data/redis/reference/): Lettuce, Redis connections, and ACLs.
- [MongoDB — Authentication](https://www.mongodb.com/docs/manual/core/authentication/): SCRAM, `authSource`, X.509.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): authorized clients and client credentials.
- [Spring Security — RestClient OAuth2](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html): `OAuth2ClientHttpRequestInterceptor` and managers.
- [Spring Security — OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): inbound bearer validation.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer tokens and errors.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): client credentials grant.
- [RFC 8705 — OAuth 2.0 mTLS](https://www.rfc-editor.org/rfc/rfc8705): certificate-bound tokens/client authentication.
- [Spring Integration — Reference](https://docs.spring.io/spring-integration/reference/): adapters, flows, and messaging boundaries.
- [Enterprise Integration Patterns — Idempotent Receiver](https://www.enterpriseintegrationpatterns.com/patterns/messaging/IdempotentReceiver.html): duplicate-safe processing.
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html): durable integration intents and retries.
