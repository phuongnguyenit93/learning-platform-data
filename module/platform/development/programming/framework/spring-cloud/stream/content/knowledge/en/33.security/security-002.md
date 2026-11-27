# RabbitMQ Authentication, Virtual Hosts, and TLS

A Spring Cloud Stream application using RabbitMQ must pass three layers of protection before safely exchanging messages: connection identity authentication, authorization within a virtual host, and transport protection using TLS. These three layers answer different questions:

- Authentication: who is the client? RabbitMQ verifies username/password or another authentication mechanism.
- Virtual host and authorization: which namespace is the client allowed to access, and which queues/exchanges can it declare or use?
- TLS: is data traversing the network encrypted, and does the client verify the correct server? With mutual TLS, the broker can also verify the client certificate.

A successful TCP connection does not mean authentication succeeded. Successful authentication does not mean the user is allowed into the virtual host. Entering the virtual host still does not guarantee permission to publish or consume. Finally, an AMQP connection may work yet remain unencrypted if TLS is not enabled.

## 1. Three Protection Layers in an AMQP Connection

~~~mermaid
flowchart TD
    A["Spring Cloud Stream Rabbit Binder"] --> B["TLS handshake"]
    B --> C["Verify server certificate<br/>and optional client certificate"]
    C --> D["AMQP authentication<br/>username / password or SASL"]
    D --> E["Select virtual host"]
    E --> F["Check permissions<br/>configure / write / read"]
    F --> G["Declare / publish / consume"]
~~~

The sequence above is a conceptual model. The TLS handshake happens before AMQP messages are exchanged. Once the channel is established, the client authenticates with the broker, selects a virtual host when opening the AMQP connection, and RabbitMQ checks permissions on each resource.

| Layer | Mechanism | Error Examples |
|---|---|---|
| TLS | X.509 certificates, trust store, hostname verification | PKIX path building failed, certificate expired |
| Authentication | Username/password or broker-supported SASL mechanism | ACCESS_REFUSED - Login was refused |
| Virtual host | Namespace selected when opening connection | Vhost does not exist or user is not permitted to access |
| Authorization | Permissions by resource and operation | Access to exchange/queue refused |

## 2. Authentication: How RabbitMQ Verifies Clients

RabbitMQ authenticates AMQP connections using an authentication mechanism allowed by the broker. The most common setup is username/password via the internal authentication backend. RabbitMQ can also use LDAP, HTTP, or other plugins/backends; environments requiring client certificates can use the X.509/SASL EXTERNAL mechanism when the broker is configured accordingly.

Example creating an application account:

~~~bash
rabbitmqctl add_user orders-service 'REPLACE_WITH_SECRET'
rabbitmqctl change_password orders-service 'REPLACE_WITH_SECRET'
~~~

In real environments, passwords should be provisioned from a secret manager or identity management workflow. Do not put real passwords in shell history, committed YAML files, or deployment logs.

An application user should be a dedicated account for the workload. Do not use an administrative account to run consumers/producers. Separating accounts per service or trust boundary allows independent credential revocation, auditing, and permission scoping.

### 2.1. The guest Account

RabbitMQ creates a preconfigured guest user in some default installations. This user is usually restricted to connecting only from the loopback interface. An application running on another machine will not be able to use guest to connect remotely by default.

Do not expand remote access for guest to fix connection errors. Create a dedicated user, set a strong password, and grant least-privilege permissions on the right virtual host.

### 2.2. Authentication Does Not Grant Business Permissions

A valid username/password only verifies identity. After authentication, RabbitMQ still checks:

- Is the user allowed to access the requested virtual host?
- Is the user allowed to declare the necessary exchanges/queues?
- Is the user allowed to publish to the exchange?
- Is the user allowed to consume from the queue?

Therefore, an ACCESS_REFUSED error can appear even after a successful login. Distinguish authentication errors from vhost and permission errors using broker logs and specific AMQP messages.

## 3. Virtual Host as RabbitMQ's Namespace

A virtual host (vhost) is a logical namespace containing exchanges, queues, bindings, policies, and related resources. Queue or exchange names in two different vhosts can be identical without conflicting.

Example:

~~~text
RabbitMQ cluster
  |
  +-- vhost: /orders
  |     +-- exchange: orders.events
  |     +-- queue: order-service
  |
  +-- vhost: /billing
        +-- exchange: orders.events
        +-- queue: order-service
~~~

Two queues both named order-service in two vhosts are two independent resources. A client connected to /orders cannot automatically see the queue in /billing.

Vhosts are useful for:

- Separating environments or business domains.
- Restricting access per service.
- Applying policies, quotas, and topology configuration per namespace.
- Avoiding resource name collisions between workloads.

A vhost is not an independent broker or cluster. Vhosts in the same cluster still share broker infrastructure, nodes, disks, and processing capacity; do not use vhosts instead of infrastructure boundaries when strong resource isolation is required.

### 3.1. Creating a Vhost and Granting Permissions

Example creating a namespace for the orders service:

~~~bash
rabbitmqctl add_vhost /orders
rabbitmqctl set_permissions -p /orders orders-service '.*' '.*' '.*'
~~~

The example assumes the orders-service user was created in the previous step. The set_permissions command grants broad permissions across all resources in the vhost to demonstrate syntax. Do not use .* for all three permissions in production if the application only needs specific queues/exchanges. The next section narrows permissions using regular expressions.

The default vhost name is usually /. In an AMQP URI, / is a path delimiter, so the / vhost is percent-encoded as %2F when configured via URI. When using the Spring Boot property spring.rabbitmq.virtual-host, declare the value / directly.

### 3.2. Vhost Access Permissions

A user must be granted permissions on a vhost before using the resources within it. You can inspect permissions with:

~~~bash
rabbitmqctl list_permissions -p /orders
rabbitmqctl list_user_permissions orders-service
~~~

If a user does not have permissions on a vhost, the broker refuses to open an AMQP connection to that vhost, even if the username/password is valid.

## 4. Three Permission Types: configure, write, and read

RabbitMQ manages permissions via three regular expressions bound to each user and vhost:

| Permission | Allows | Example Operations |
|---|---|---|
| configure | Declare, modify, or delete resources | Declare/delete an exchange or queue |
| write | Write to a resource | Publish to an exchange; some binding operations require permissions on related resources |
| read | Read from a resource | Consume from a queue or fetch messages via permitted operations |

RabbitMQ checks permissions on the affected resources. When binding a queue to an exchange, required permissions involve both the source exchange and the destination queue; do not assume read permission on a queue alone suffices for all topology operations.

Example of a service consuming a platform-precreated queue:

~~~bash
rabbitmqctl set_permissions -p /orders orders-consumer \
  '^$' '^$' '^orders\.submitted$'
~~~

In the command above:

- configure is ^$: matches no resource name.
- write is ^$: disallows publishing to exchanges.
- read is ^orders\.submitted$: only allows reading the queue named exactly orders.submitted.

Example of a service that only publishes to an exchange:

~~~bash
rabbitmqctl set_permissions -p /orders orders-publisher \
  '^$' '^orders\.events$' '^$'
~~~

Expressions must match the exact resource names actually used by the binder. If the binder auto-creates a queue whose name combines destination and group, the regex must permit that exact name.

### 4.1. What Permissions Does Binder Auto-Declared Topology Need?

The Rabbit binder can auto-declare exchanges, queues, and bindings. Depending on the topology, the binder needs the corresponding permissions to declare resources, publish, and consume. If a user only has read permission while the binder attempts to create a queue, the application may connect successfully and then fail during binding initialization.

There are two deployment approaches:

1. Binder-managed topology: grant least-privilege configure/write/read permissions matching the exact resources the binder must create and use.
2. Platform-managed topology: administrators pre-create exchanges, queues, and bindings; the binder is configured not to declare or bind externally managed components; the application user receives only the necessary runtime permissions.

Do not disable topology declaration arbitrarily. If the binder does not create the queue or binding, they must already exist and point to the right exchange/routing key before the consumer starts.

## 5. Configuring the Spring Cloud Stream Rabbit Binder

The Rabbit binder uses Spring AMQP and Spring Boot Rabbit connection properties. For an application with a single Rabbit binder, connection properties are normally placed under spring.rabbitmq.*.

Example:

~~~yaml
spring:
  rabbitmq:
    host: rabbitmq.internal
    port: 5672
    username: orders-service
    password: RABBITMQ_PASSWORD_FROM_SECRET
    virtual-host: /orders

  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-service
~~~

In the example, the binder connects to rabbitmq.internal:5672, authenticates as orders-service, and opens vhost /orders. The binding processOrder-in-0 uses destination orders.events and group order-service; the binder maps them to exchanges/queues according to Rabbit binder rules.

The value RABBITMQ_PASSWORD_FROM_SECRET is an illustrative placeholder; in deployment, map the secret from the environment or secret manager into the password property. Do not commit real passwords into application.yml.

### 5.1. Using Multiple Rabbit Binders or Multiple Brokers

If an application has multiple binders, each binder can have its own environment. Example:

~~~yaml
spring:
  cloud:
    stream:
      binders:
        rabbit-orders:
          type: rabbit
          defaultCandidate: false
          environment:
            spring:
              rabbitmq:
                host: orders-rabbit.internal
                port: 5672
                username: orders-service
                password: ORDERS_RABBIT_PASSWORD_FROM_SECRET
                virtual-host: /orders
        rabbit-audit:
          type: rabbit
          defaultCandidate: false
          environment:
            spring:
              rabbitmq:
                host: audit-rabbit.internal
                port: 5672
                username: audit-service
                password: AUDIT_RABBIT_PASSWORD_FROM_SECRET
                virtual-host: /audit
      bindings:
        processOrder-in-0:
          binder: rabbit-orders
          destination: orders.events
          group: order-service
        publishAudit-out-0:
          binder: rabbit-audit
          destination: audit.events
~~~

rabbit-orders and rabbit-audit are two binder configuration names both with type rabbit, yet each binder has its own host, credentials, and vhost. Set defaultCandidate: false so only bindings explicitly referencing them select them.

If using inheritEnvironment: false, declare all required properties in the binder environment and verify how your deployment supplies placeholders/secrets to the separate context.

## 6. Configuring TLS for AMQPS Connections

TLS encrypts data in transit and enables clients to verify the server's identity via certificates. RabbitMQ typically provides the TLS listener on port 5671, though the actual port depends on broker configuration.

With one-way TLS:

1. RabbitMQ presents the server certificate.
2. The client verifies the certificate chain against the trust store.
3. The client verifies that the hostname in the certificate matches the connected hostname.
4. After the handshake, the client performs AMQP authentication using username/password.

Spring Boot Rabbit connection example:

~~~yaml
spring:
  rabbitmq:
    host: rabbitmq.internal
    port: 5671
    username: orders-service
    password: RABBITMQ_PASSWORD_FROM_SECRET
    virtual-host: /orders
    ssl:
      enabled: true
      trust-store: file:/run/secrets/rabbitmq-truststore.p12
      trust-store-password: RABBITMQ_TRUSTSTORE_PASSWORD_FROM_SECRET
      trust-store-type: PKCS12
      validate-server-certificate: true
      verify-hostname: true
~~~

trust-store contains the CAs or certificate chains the client trusts to verify the broker. validate-server-certificate and verify-hostname should be enabled in production. Do not disable hostname verification just to make a test connection pass.

Specific TLS property names depend on the Spring Boot/Spring AMQP version. Check the configuration metadata and documentation for the exact version in your project's BOM before deploying.

### 6.1. Using an AMQPS URI

Spring AMQP also supports configuring connections via URI. The URI uses the amqps scheme to require TLS:

~~~text
amqps://orders-service:ENCODED_PASSWORD@rabbitmq.internal:5671/%2Forders
~~~

This is a syntax illustration. Special characters in username/password and vhost must be percent-encoded according to URI rules. The vhost /orders becomes %2Forders in the path.

Do not put URIs containing real passwords in source code or logs. If configuring both a URI and individual host/port/user/password properties simultaneously, check the precedence of the Spring Boot version in use; avoid conflicting configuration sources.

## 7. Mutual TLS and Client Certificates

One-way TLS verifies the broker to the client. Mutual TLS (mTLS) adds a step where the broker verifies the client certificate. The broker must be configured to require and trust client certificates; setting a key store on the application side alone is not enough to enable mTLS.

Example client key store configuration:

~~~yaml
spring:
  rabbitmq:
    host: rabbitmq.internal
    port: 5671
    username: orders-service
    password: RABBITMQ_PASSWORD_FROM_SECRET
    virtual-host: /orders
    ssl:
      enabled: true
      key-store: file:/run/secrets/orders-client.p12
      key-store-password: RABBITMQ_KEYSTORE_PASSWORD_FROM_SECRET
      key-store-type: PKCS12
      trust-store: file:/run/secrets/rabbitmq-truststore.p12
      trust-store-password: RABBITMQ_TRUSTSTORE_PASSWORD_FROM_SECRET
      trust-store-type: PKCS12
      validate-server-certificate: true
      verify-hostname: true
~~~

In this model:

- The key store contains the client's private key and certificate.
- The trust store contains the CA/certificate used to verify the RabbitMQ server.
- The RabbitMQ server must trust the CA that signed the client certificate and configure its TLS listener to require a peer certificate.
- If you want the certificate to replace username/password, the broker must enable the X.509/SASL EXTERNAL authentication mechanism and map certificate identities to RabbitMQ users.

If the broker only requires a TLS client certificate for channel verification while still using username/password for AMQP authentication, both layers apply. mTLS does not automatically grant vhost or resource permissions.

## 8. Creating Trust Stores and Key Stores

Java clients commonly use JKS or PKCS12. PKCS12 is a widely used interchange format for certificates and private keys.

Example importing a CA certificate into a trust store:

~~~bash
keytool -importcert \
  -alias rabbitmq-ca \
  -file rabbitmq-ca.pem \
  -keystore rabbitmq-truststore.p12 \
  -storetype PKCS12
~~~

Example inspecting the contents of a trust store:

~~~bash
keytool -list \
  -keystore rabbitmq-truststore.p12 \
  -storetype PKCS12
~~~

If using mTLS, the key store must contain the client's private key and certificate chain, not just the CA certificate. The client certificate must have the appropriate key usage and be signed by a CA trusted by the broker.

Do not place key store/trust store passwords in committed scripts. In containers, mount files from a secret volume with restricted read permissions and pass passwords via secret environment variables or the platform's secret management mechanism.

## 9. TLS on the RabbitMQ Broker Side

Clients only establish TLS connections when RabbitMQ has a TLS listener and an appropriate certificate chain. A broker configuration must specify:

- Server certificate and private key.
- Trusted CA certificates if verifying client certificates.
- TLS listener port, typically 5671.
- Allowed TLS versions and cipher suites.
- Peer verification policy and client certificate requirement.
- Authentication mechanisms allowed after the TLS handshake.

Conceptual configuration example in rabbitmq.conf:

~~~ini
listeners.tcp = none
listeners.ssl.default = 5671

ssl_options.cacertfile = /etc/rabbitmq/tls/ca.pem
ssl_options.certfile   = /etc/rabbitmq/tls/server.pem
ssl_options.keyfile    = /etc/rabbitmq/tls/server-key.pem

ssl_options.verify = verify_peer
ssl_options.fail_if_no_peer_cert = true
~~~

The verify and fail_if_no_peer_cert properties above require the broker to verify the peer certificate and reject clients that do not provide a certificate. This is an mTLS example; if only one-way TLS is needed, the broker configuration does not have to require a client certificate.

Do not copy TLS configuration from examples into production without verifying certificates, CAs, hostnames, the RabbitMQ version, and your organization's security policy. Misconfiguring TLS on the broker can prevent all clients from connecting.

## 10. Certificate-Based Authentication

RabbitMQ supports X.509 authentication via SASL EXTERNAL when the plugin/backend and listener are configured accordingly. The client certificate is mapped to a username according to broker policy, typically based on the common name or a configured mapping mechanism.

To use this mechanism, you must:

1. Enable the TLS listener and require client certificates.
2. Configure RabbitMQ to trust the CA signing client certificates.
3. Enable the EXTERNAL authentication mechanism on both broker and client.
4. Define rules mapping the certificate identity to a RabbitMQ user.
5. Create the corresponding user/identity and grant vhost permissions.
6. Configure the client to use the appropriate certificate and omit password mechanisms if not required.

This is a broker- and client-level setup; it does not happen automatically just because spring.rabbitmq.ssl.enabled=true. Verify which SASL mechanisms the Spring AMQP client and RabbitMQ deployment support in your running versions.

## 11. Distinguishing Authentication, Vhost, Permission, and TLS Errors

| Symptom | Possible Failing Layer | Investigation Direction |
|---|---|---|
| Connection refused | TCP/listener/network | Host, port, firewall, listener 5672/5671 |
| SSLHandshakeException | TLS handshake | Certificate chain, protocol, cipher, client certificate |
| PKIX path building failed | Trust store | CA/intermediate certificate and trust store path |
| No subject alternative DNS name matching | Hostname verification | Connected host must match SAN in server certificate |
| ACCESS_REFUSED - Login was refused | Authentication | Username, password, backend, mechanism |
| vhost not found | Virtual host | Whether the vhost was created with the exact name |
| access to vhost refused | Vhost authorization | Whether the user has been granted permissions on the vhost |
| access to exchange/queue refused | Resource authorization | Whether configure/write/read regexes match the resource |
| Channel shutdown during declare | Topology permissions or incompatible declare attributes | Configure permissions and existing topology |

Effective investigation order:

1. Check DNS, TCP, and listener.
2. If using TLS, verify the handshake, trust chain, and hostname.
3. Check the authentication mechanism and credentials.
4. Check that the vhost exists and the user has access permissions.
5. Check configure/write/read permissions for exchanges and queues.
6. Check that the binder is using the intended host, vhost, user, and TLS environment.

Do not immediately change permissions to .* when encountering ACCESS_REFUSED. First identify which resource and operation were denied.

## 12. Checking with RabbitMQ Tools and OpenSSL

On the broker, administrators can inspect:

~~~bash
rabbitmqctl list_vhosts
rabbitmqctl list_users
rabbitmqctl list_permissions -p /orders
rabbitmqctl list_queues -p /orders name consumers messages_ready messages_unacknowledged
rabbitmqctl list_connections user vhost peer_host peer_port state
~~~

These commands require appropriate administrative privileges on the RabbitMQ node. Do not grant administrative privileges to an application user just to run diagnostic commands.

Testing the TLS listener from a client machine:

~~~bash
openssl s_client \
  -connect rabbitmq.internal:5671 \
  -servername rabbitmq.internal \
  -showcerts \
  -verify_return_error
~~~

If you need to test a client certificate:

~~~bash
openssl s_client \
  -connect rabbitmq.internal:5671 \
  -servername rabbitmq.internal \
  -cert client-cert.pem \
  -key client-key.pem \
  -CAfile rabbitmq-ca.pem \
  -verify_return_error
~~~

OpenSSL commands check the TLS handshake and certificate validation; they do not verify AMQP username/password, vhosts, or resource permissions. Further verification with an AMQP client or Spring Cloud Stream application is required.

## 13. Testing Connections and Permissions by Role

You should have test accounts representing producers, consumers, and topology management workloads:

| Role | Expected Permissions | Behavior to Verify |
|---|---|---|
| Producer | Access to target vhost, write on target exchange | Publish succeeds; publishing to another exchange is denied |
| Consumer | Access to target vhost, read on target queue | Consume succeeds; reading another queue is denied |
| Topology provisioner | Configure on resources to create; plus write/read if needed | Declare exchanges, queues, and bindings as planned |
| Service runtime | Minimum permissions to operate | Cannot create/delete out-of-scope resources |

Test scenarios:

1. Valid credentials and valid vhost: connection succeeds.
2. Wrong password: authentication fails.
3. Valid password but user lacks vhost permissions: connection opening is refused.
4. User enters the right vhost but lacks write: publish is refused.
5. User lacks read: consume is refused.
6. User lacks configure when binder needs to create a queue: binding initialization fails.
7. TLS trust store missing CA: handshake fails.
8. Hostname does not match certificate SAN: hostname verification fails.
9. One-way TLS works but broker requires mTLS: client without certificate is rejected.
10. Expired or revoked certificate per PKI policy: connection is rejected.

Do not test by logging wrong passwords or printing full URIs. Tests should verify the error type and connection status without printing secrets.

## 14. Container and Kubernetes Deployment

For containerized applications, mount certificates and trust stores from secret volumes:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: order-consumer
spec:
  containers:
    - name: app
      image: example/order-consumer:latest
      env:
        - name: RABBITMQ_PASSWORD
          valueFrom:
            secretKeyRef:
              name: rabbitmq-orders
              key: password
        - name: RABBITMQ_TRUSTSTORE_PASSWORD
          valueFrom:
            secretKeyRef:
              name: rabbitmq-orders-tls
              key: truststore-password
      volumeMounts:
        - name: rabbitmq-tls
          mountPath: /run/secrets
          readOnly: true
  volumes:
    - name: rabbitmq-tls
      secret:
        secretName: rabbitmq-orders-tls
~~~

This is an illustrative manifest. Secrets must be created and managed through a secure workflow; never commit Secret contents with real credentials to Git. Grant secret read permissions to the right service account and mount only the required files.

When rotating certificates:

- Issue new certificates before old ones expire.
- Update the trust store so clients trust the new CA during the transition period.
- Update broker certificates following an appropriate rolling procedure.
- Recreate or refresh the connection factory if the client does not automatically reload certificates.
- Verify new connections are using the new certificate.
- Revoke old certificates after all clients have transitioned.

Do not assume the JVM automatically reloads mounted trust store/key store files when files change. Reloading capability depends on how Spring AMQP/SSLContext is created and the library version.

## 15. Securing Vhosts and Permissions in Multi-Service Environments

One design can separate namespaces by business domain:

~~~text
/orders
  orders.events
  orders.retry
  orders.dlq

/billing
  billing.commands
  billing.events
  billing.dlq

/notifications
  notifications.outbound
  notifications.dlq
~~~

Each service has its own user:

- orders-consumer only reads order queues.
- billing-publisher only writes to billing exchanges.
- notification-worker only reads notification queues.
- A provisioner account is used in the deployment pipeline to declare topology.

Separating users and vhosts does not replace resource-level permission restrictions. A user with .* permissions on /orders can still manipulate every queue/exchange in that vhost. Choose narrow regexes based on resource names and functions.

Do not grant administrator, management, or monitoring tags to runtime users if they do not need Management UI/API access. Administrative tags and AMQP permissions are separate mechanisms; tags do not replace configure/write/read on a vhost.

## 16. TLS and Authentication Do Not Replace Each Other

Common combinations:

| TLS | AMQP authentication | Outcome |
|---|---|---|
| Disabled | Username/password | Connection can authenticate, but data is unencrypted in transit |
| Enabled, verify server | Username/password | Channel is encrypted and the broker is verified by the client |
| Enabled mTLS | Username/password | Channel is encrypted, broker verifies client certificate, then AMQP authenticates with password |
| Enabled mTLS + SASL EXTERNAL | Certificate identity | Broker can use the certificate to authenticate the user if mapping/mechanism is fully configured |

TLS does not automatically grant vhost access. Username/password does not encrypt data. Vhosts do not verify certificates. Permissions do not protect data from being read in transit. Configure every layer completely according to your system's threat model.

## 17. Pre-Production Checklist

- [ ] Create a dedicated user per workload; do not use guest or administrative accounts.
- [ ] Create the proper virtual host and specify its name explicitly in binder configuration.
- [ ] Grant least-privilege configure/write/read permissions per resource.
- [ ] Decide whether the binder auto-declares exchanges, queues, and bindings or topology is provisioned externally.
- [ ] Configure host, port, username, password, and virtual host in the right binder environment.
- [ ] Use a secret manager or secret volume to supply credentials.
- [ ] Enable the TLS listener on the broker and spring.rabbitmq.ssl.enabled on the client.
- [ ] Install a trust store with the appropriate CA; keep server certificate validation and hostname verification enabled.
- [ ] Enable mTLS only when the broker requires client certificates and the trust chain is configured.
- [ ] If using SASL EXTERNAL, verify the authentication mechanism and certificate identity mapping.
- [ ] Verify TLS protocol, ciphers, and certificate expiration against PKI policy.
- [ ] Check vhosts, permissions, queue consumer counts, and actual publish/consume flows.
- [ ] Test wrong password, missing permissions, wrong vhost, hostname mismatch, and expired certificate.
- [ ] Have a plan for credential/certificate rotation and connection recovery.
- [ ] Do not log secrets, private keys, or full URIs.

## Official References

- [RabbitMQ Access Control](https://www.rabbitmq.com/docs/access-control): users, authentication backends, virtual hosts, and resource permissions.
- [RabbitMQ Virtual Hosts](https://www.rabbitmq.com/docs/vhosts): namespaces, creating vhosts, and access permissions.
- [RabbitMQ TLS Support](https://www.rabbitmq.com/docs/ssl): TLS listeners, certificates, peer verification, and client certificates.
- [RabbitMQ Networking](https://www.rabbitmq.com/docs/networking): ports, listeners, and AMQP/TLS connections.
- [Spring Cloud Stream Rabbit Binder Reference](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html): Rabbit binder and connection configuration.
- [Spring Boot RabbitMQ Support](https://docs.spring.io/spring-boot/reference/messaging/amqp.html): spring.rabbitmq.* properties and SSL configuration.
- [Spring AMQP Connection and Resource Management](https://docs.spring.io/spring-amqp/reference/amqp/connections.html): ConnectionFactory and AMQP connection setup.
