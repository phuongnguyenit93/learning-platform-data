# JAAS configuration

Kafka uses **JAAS (Java Authentication and Authorization Service)** to configure login information for certain SASL authentication mechanisms. In Spring Kafka, JAAS typically appears when a consumer or producer connects to a cluster requiring **SASL/PLAIN**, **SASL/SCRAM**, **SASL/GSSAPI (Kerberos)**, or **SASL/OAUTHBEARER**.

A proper JAAS configuration must answer: which LoginModule the application logs in with, which credential or identity it uses, which SASL mechanism the broker supports, where the configuration is loaded from, and how secrets are protected. Misconfiguration can prevent the application from starting, cause the SASL handshake to fail, cause the broker to reject authentication, or create a system that works in test environments but is unsafe in production.

This lesson belongs to the **Operational Security** chapter of the **Spring Kafka Reliability Operations** module. It focuses on JAAS structure, client configuration via sasl.jaas.config, static JAAS files, how Spring Boot passes security properties to Kafka clients, differences between PLAIN/SCRAM/Kerberos/OAuth, secrets management, rotation, diagnostics, and operational runbooks.

## 1. Which Part of Kafka Security Does JAAS Solve?

When a Kafka client connects to a broker, there are several distinct security layers:

1. **Transport security:** TLS encrypts the transport channel and can authenticate broker or client certificates.
2. **Authentication:** the broker verifies who the client is. With SASL, the authentication mechanism can use a JAAS LoginModule.
3. **Authorization:** the broker decides whether the authenticated principal is allowed to read topics, write topics, use consumer groups, or perform administrative operations.
4. **Application identity:** services and workloads are issued separate credentials with their own lifecycles and permissions.

JAAS primarily configures **the login identity and credentials for authentication**. It does not replace TLS, does not define ACLs on its own, and does not decide which topics a consumer is allowed to read.

Diagram:

~~~text
Spring Boot application
        |
        v
KafkaProducer / KafkaConsumer
        |
        +-- SSL/TLS: transport encryption and authentication
        |
        +-- SASL mechanism
                |
                v
             JAAS LoginModule
                |
                v
          SASL authentication exchange
                |
                v
          Kafka broker authenticates principal
                |
                v
          Kafka authorizer checks ACL
                |
                v
          Topic / group / cluster operation
~~~

If authentication succeeds but ACLs are missing, the client can still receive authorization errors. If the TLS handshake fails, the JAAS LoginModule has not even been used yet. Identifying the right error layer helps avoid replacing credentials when the actual issue is the truststore or ACLs.

## 2. JAAS LoginContext and LoginModule

JAAS defines a **LoginContext** that references a login configuration. That configuration contains one or more **LoginModules** along with control flags and options.

An entry has the general form:

~~~text
KafkaClient {
    com.example.security.ExampleLoginModule required
        optionOne="value"
        optionTwo="another-value";
};
~~~

Components:

- **KafkaClient:** the requested application/login context name.
- **LoginModule class:** the class implementing the login mechanism.
- **required/requisite/sufficient/optional:** control flag determining how the module's outcome affects the overall login.
- **Options:** parameters the module needs to obtain identity, credentials, or set up the subject.
- **Semicolon:** terminates the LoginModule declaration.
- **Closing brace and semicolon:** terminates the JAAS entry.

In Kafka, common LoginModules belong to the Kafka client or JDK, for example:

| Mechanism | Commonly Used LoginModule |
|---|---|
| SASL/PLAIN | org.apache.kafka.common.security.plain.PlainLoginModule |
| SASL/SCRAM | org.apache.kafka.common.security.scram.ScramLoginModule |
| SASL/GSSAPI | com.sun.security.auth.module.Krb5LoginModule |
| SASL/OAUTHBEARER | org.apache.kafka.common.security.oauthbearer.OAuthBearerLoginModule |

The module class must be on the process's classpath/runtime. For a custom LoginModule, both client and runtime must have the corresponding dependency, and the class must properly implement the JAAS API.

## 3. LoginModule Control Flags

JAAS supports four main control flags:

| Flag | General Meaning |
|---|---|
| required | The module must succeed; login continues running remaining modules before aggregating results |
| requisite | The module must succeed; if it fails, login stops immediately |
| sufficient | Success can be enough for login to succeed if prior required modules did not fail |
| optional | Outcome is not strictly required to determine login success if other modules provide the needed result |

For typical Kafka SASL configurations, the usual example is a single LoginModule with the **required** flag:

~~~text
org.apache.kafka.common.security.scram.ScramLoginModule required
    username="orders-reader"
    password="...";
~~~

Do not arbitrarily add multiple LoginModules or change control flags just to "try to make it work." The Kafka client SASL JAAS property is typically designed for one login module entry in client configuration; follow the documentation for the Kafka client version you are using. A static JAAS file can contain multiple entries and modules per JAAS syntax, but how Kafka selects a context still depends on context names and client behavior.

## 4. Two Ways to Supply JAAS to a Kafka Client

A Kafka client can receive JAAS configuration in two common ways:

**Approach A — Inline property sasl.jaas.config**

- Configured directly in Kafka client properties.
- Can be set separately for producer, consumer, or admin client.
- Easy to pass via Spring Boot configuration and secret managers.
- No need to create a separate JAAS file for the application.
- Can override static JAAS contexts per Kafka client behavior.

**Approach B — Static JAAS file**

- Create a file containing named login contexts, e.g., KafkaClient.
- JVM loads the file via the system property java.security.auth.login.config.
- Multiple Java components can share a context.
- Requires managing file lifecycle, mounts, permissions, and process startup.
- One misconfiguration can affect multiple clients in the same JVM.

For Spring Boot microservices, **sasl.jaas.config** is usually the convenient choice because security configuration can be attached per Kafka client factory. A static JAAS file is suitable when the environment already has JVM-wide JAAS management processes or needs to share a login context across multiple libraries.

## 5. Structure of sasl.jaas.config

Example SASL/SCRAM-SHA-512:

~~~properties
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-reader" password="secret";
~~~

An inline JAAS entry consists of:

- LoginModule class name.
- Control flag.
- Module options, typically username/password or identity-specific settings.
- Ending with a semicolon.

The **sasl.mechanism** and **sasl.jaas.config** properties must match the listener/broker configuration. Simply setting username/password does not cause the client to automatically choose the right SASL mechanism.

Example PLAIN:

~~~properties
sasl.mechanism=PLAIN
sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username="orders-reader" password="secret";
~~~

Example SCRAM:

~~~properties
sasl.mechanism=SCRAM-SHA-256
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-reader" password="secret";
~~~

Credentials in examples are placeholders only. Do not commit real passwords into source code, application.yml, Docker images, build artifacts, or logs.

## 6. Spring Boot Configuration for SASL/JAAS

Spring Boot can pass Kafka client properties through Spring Kafka properties. A general approach is using **spring.kafka.properties** for shared Kafka properties:

~~~yaml
spring:
  kafka:
    bootstrap-servers: broker1.example.net:9093,broker2.example.net:9093
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: KAFKA_SASL_JAAS_CONFIG_SECRET_REFERENCE
~~~

The secret reference value in the example represents an environment variable or secret provider injected at deployment time. Spring placeholders can be used in application configuration, but real secrets must come from a secret manager or deployment platform, not be committed to the repository.

Producer and consumer can be configured separately if they use different principals or credentials:

~~~yaml
spring:
  kafka:
    bootstrap-servers: broker1.example.net:9093
    consumer:
      properties:
        security.protocol: SASL_SSL
        sasl.mechanism: SCRAM-SHA-512
        sasl.jaas.config: KAFKA_CONSUMER_JAAS_SECRET_REFERENCE
    producer:
      properties:
        security.protocol: SASL_SSL
        sasl.mechanism: SCRAM-SHA-512
        sasl.jaas.config: KAFKA_PRODUCER_JAAS_SECRET_REFERENCE
~~~

Exact binding syntax and precedence among common properties, consumer.properties, producer.properties, and admin.properties must be verified for your Spring Boot version. Do not assume common properties always win over specific properties or vice versa; inspect the effective configuration of each client factory.

### 6.1. Producer and consumer can use separate principals

A service can:

- Have the consumer read orders.events using principal orders-reader.
- Have the producer write orders.audit using principal orders-writer.
- Have the admin client use only a principal with describe/config permissions at the level required.

Separating principals aids least privilege and makes audit investigations clearer. If all clients use one admin credential, a credential leakage incident can affect the entire cluster.

## 7. Building Kafka Properties in Java

When creating Kafka client factories manually, security properties can be configured in a Map:

~~~java
Map<String, Object> props = new HashMap<>();

props.put(
    ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
    "broker1.example.net:9093"
);
props.put(
    CommonClientConfigs.SECURITY_PROTOCOL_CONFIG,
    "SASL_SSL"
);
props.put(
    SaslConfigs.SASL_MECHANISM,
    "SCRAM-SHA-512"
);
props.put(
    SaslConfigs.SASL_JAAS_CONFIG,
    jaasConfigFromSecret
);
~~~

This Map can be used to construct a DefaultKafkaConsumerFactory or the corresponding producer factory.

Do not log the entire Map because sasl.jaas.config contains credentials. When debugging effective properties, mask passwords/tokens and display only:

- security.protocol;
- sasl.mechanism;
- sanitized broker endpoint;
- secret reference/version, if available;
- whether credentials have been configured.

## 8. SASL/PLAIN

SASL/PLAIN transmits username/password in the SASL exchange. This mechanism must be used over a **TLS** connection in production environments to protect credentials in transit.

Client JAAS:

~~~text
org.apache.kafka.common.security.plain.PlainLoginModule required
    username="orders-reader"
    password="replace-with-secret";
~~~

Client properties:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=PLAIN
~~~

On the broker side, PLAIN server configuration needs a way to verify user credentials. For simple setups, the server JAAS module can declare user entries using the option format supported by Kafka's PLAIN module, for example:

~~~text
org.apache.kafka.common.security.plain.PlainLoginModule required
    username="broker-interbroker"
    password="broker-secret"
    user_orders-reader="reader-secret"
    user_orders-writer="writer-secret";
~~~

The user_* options on the broker side are an example mechanism of PlainLoginModule to verify users. Do not use example credentials directly in production. For real systems, evaluate how credentials are stored and rotated; avoid keeping a broker JAAS file with many readable user passwords when an appropriate secret integration solution exists.

PLAIN does not encrypt passwords at the SASL mechanism level. **SASL_SSL** is typically required to protect the network exchange. Only use SASL_PLAINTEXT in isolated lab environments that contain no real credentials.

## 9. SASL/SCRAM

SCRAM is a password-based challenge-response mechanism that avoids sending the password directly like PLAIN. Kafka supports SCRAM-SHA-256 and SCRAM-SHA-512.

Client JAAS:

~~~text
org.apache.kafka.common.security.scram.ScramLoginModule required
    username="orders-reader"
    password="replace-with-secret";
~~~

Client properties:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
~~~

The broker must have a listener configured to support SASL/SCRAM and hold the user's SCRAM credentials in the appropriate metadata/configuration. Credential creation is typically done using Kafka administrative tools or the platform's control plane, not simply by adding every client's username/password to the broker JAAS file.

Illustrative administrative command:

~~~bash
bin/kafka-configs.sh \
  --bootstrap-server broker1.example.net:9093 \
  --alter \
  --add-config 'SCRAM-SHA-512=[iterations=8192,password=replace-me]' \
  --entity-type users \
  --entity-name orders-reader
~~~

Exact syntax and admin client authentication must match your Kafka version/distribution. Passwords on the command line can appear in shell history or process inspection; in production, use credential injection/secret-safe tooling supported by the platform.

SCRAM should still run over TLS to protect metadata, broker identity, and all traffic. Do not treat SCRAM as a replacement for transport encryption.

## 10. SASL/GSSAPI and Kerberos

GSSAPI typically integrates Kafka with Kerberos. The common JAAS LoginModule is the JDK **Krb5LoginModule**.

Example client JAAS:

~~~text
com.sun.security.auth.module.Krb5LoginModule required
    useKeyTab=true
    storeKey=true
    keyTab="/var/run/secrets/kafka/orders-reader.keytab"
    principal="orders-reader@EXAMPLE.COM"
    serviceName="kafka";
~~~

Client property:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=GSSAPI
~~~

Some environments use SASL_PLAINTEXT on separately protected networks, but TLS remains an option to evaluate for transport confidentiality/integrity and broker identity.

Kerberos also depends on:

- Realm and KDC configuration.
- DNS/service principal naming.
- Keytab permissions.
- Ticket validity/renewal.
- Clock synchronization.
- Kafka broker service principal.
- JVM krb5 configuration.

### 10.1. krb5.conf

The JVM may need Kerberos configuration:

~~~text
[libdefaults]
  default_realm = EXAMPLE.COM
  dns_lookup_kdc = true
  rdns = false
~~~

The file can be supplied via a system property:

~~~text
-Djava.security.krb5.conf=/etc/krb5.conf
~~~

Paths, realm, and KDC must match the actual environment. Do not copy keytabs from a developer's laptop into images or repositories.

### 10.2. Keytab and principal

A keytab contains material allowing authentication as a Kerberos principal. Protect it like a high-value secret:

- File permissions readable only by the process user.
- Mount read-only.
- Do not include in container image layers.
- Do not log file contents or base64 encoding.
- Rotate according to KDC procedures.
- Avoid sharing the same principal across unrelated applications.

If using a ticket cache instead of a keytab, understand the process lifecycle, cache location, and renewal. A client that starts up successfully may only reveal errors hours later on reconnect when the ticket expires.

## 11. SASL/OAUTHBEARER

SASL/OAUTHBEARER uses OAuth bearer tokens for authentication. The JAAS LoginModule is:

~~~text
org.apache.kafka.common.security.oauthbearer.OAuthBearerLoginModule required;
~~~

However, a bare JAAS entry **does not automatically generate a valid token**. The Kafka client needs a callback handler or mechanism supporting token acquisition appropriate for the identity provider environment.

Client properties may include:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=OAUTHBEARER
sasl.login.callback.handler.class=com.example.kafka.security.TokenCallbackHandler
~~~

The callback handler must properly implement the Kafka client API and:

- Obtain tokens from the identity provider or workload identity.
- Verify required audience/scope.
- Manage token expiry and refresh.
- Never log tokens.
- Handle timeouts, rate limits, and identity provider outages.

The Kafka broker also needs an appropriate OAuth bearer validator/callback handler configured to verify tokens and map principals. Client login succeeding in fetching a token does not guarantee the broker accepts the token or ACLs permit the operation.

Do not embed long-lived access tokens in source code or JAAS files. Tokens are typically short-lived; use callbacks/credential providers and controlled refresh mechanisms.

## 12. SASL Mechanism Must Match the Broker Listener

A Kafka listener can support one or more SASL mechanisms depending on broker configuration.

Conceptual example:

~~~properties
listeners=SASL_SSL://0.0.0.0:9093
advertised.listeners=SASL_SSL://broker1.example.net:9093
listener.security.protocol.map=SASL_SSL:SASL_SSL
sasl.enabled.mechanisms=SCRAM-SHA-512,PLAIN
~~~

The client selects one mechanism:

~~~properties
sasl.mechanism=SCRAM-SHA-512
~~~

If the client selects PLAIN while the listener only supports SCRAM-SHA-512, authentication will fail even with a valid username/password.

Similarly, **security.protocol** must match the listener endpoint:

| Client protocol | Broker listener | Meaning |
|---|---|---|
| PLAINTEXT | PLAINTEXT | No SASL, no TLS |
| SSL | SSL | TLS, no SASL |
| SASL_PLAINTEXT | SASL listener without TLS | SASL but unencrypted transport |
| SASL_SSL | SASL_SSL listener | SASL over TLS |

You cannot use JAAS to turn a PLAINTEXT listener into a SASL listener. The broker listener must be configured and exposed on the proper endpoint.

## 13. Static JAAS File for Kafka Clients

A JAAS file can define a named context:

~~~text
KafkaClient {
    org.apache.kafka.common.security.scram.ScramLoginModule required
        username="orders-reader"
        password="replace-with-secret";
};
~~~

The JVM loads the file via:

~~~text
-Djava.security.auth.login.config=/etc/kafka/jaas.conf
~~~

The Kafka client can look up the **KafkaClient** context in the JAAS configuration when inline sasl.jaas.config is not used, per Kafka client behavior.

Operational points:

- The file must exist and be readable by the process user.
- The path must be valid inside the container, not a host path.
- The file should be mounted read-only.
- Secrets must be provisioned via a secret manager/Kubernetes Secret or equivalent mechanism.
- Do not place the file in the source tree or image layer.
- The JVM system property must be passed properly at process startup.
- When changing the file, know whether the LoginContext/client reloads or requires recreating the client.

Do not assume editing the file on disk automatically updates a running LoginContext. Credential refresh behavior depends on the LoginModule and Kafka client lifecycle.

## 14. Static JAAS Context vs. Inline Client Override

A Kafka client can receive an inline property:

~~~properties
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-reader" password="secret";
~~~

When this property is configured, the client uses that entry for SASL login instead of relying on the static JAAS context, per Kafka client rules.

Benefits:

- Producer/consumer can use different principals.
- Multiple Kafka clusters in the same JVM can have separate credentials.
- No need to modify a JVM-wide JAAS file for each client.
- Spring Boot can bind security settings per factory.

Static JAAS fits environments with JVM-level login context management. If multiple libraries rely on KafkaClient, align ownership to avoid one global file holding credentials for too many components.

## 15. Broker-Side JAAS and Listener-Specific Configuration

Brokers can also use JAAS to authenticate clients or log into other clusters under certain mechanisms.

A static JAAS file for a broker typically has the **KafkaServer** context. Example simple PLAIN configuration:

~~~text
KafkaServer {
    org.apache.kafka.common.security.plain.PlainLoginModule required
        username="broker-interbroker"
        password="interbroker-secret"
        user_orders-reader="reader-secret"
        user_orders-writer="writer-secret";
};
~~~

Broker starts with:

~~~text
-Djava.security.auth.login.config=/etc/kafka/kafka_server_jaas.conf
~~~

In Kafka brokers, listener/mechanism-specific JAAS properties can be configured in the form:

~~~properties
listener.name.sasl_ssl.plain.sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username="broker-interbroker" password="secret" user_orders-reader="reader-secret";
~~~

Listener and mechanism names in the property must follow the corresponding lowercase rules. Exact syntax depends on the Kafka broker version and security setup.

Do not confuse:

- **Client JAAS:** credentials a client uses to log into a broker.
- **Broker JAAS:** modules/credentials a broker uses for server-side mechanisms or inter-broker SASL.
- **Inter-broker authentication:** brokers authenticating with other brokers if the cluster uses SASL for internal traffic.

A client can log in successfully to an external listener while broker-to-broker communication still fails due to inter-broker mechanisms or separate credentials.

## 16. SCRAM Broker Credentials Differ from PLAIN User Options

With PLAIN, a simple JAAS configuration can contain user_* options for the server to check passwords. With SCRAM, user credentials are typically managed via Kafka metadata/configuration per the SCRAM mechanism.

Do not copy PLAIN user_* templates into a SCRAM LoginModule and expect the broker to recognize the credentials. Create SCRAM credentials for the principal via Kafka's administration mechanism and configure the listener to support the corresponding mechanism.

Broker-side JAAS may also need a username/password for **inter-broker client authentication**. That is the identity the broker uses to connect to other brokers, not a list of all consumer users.

## 17. Spring Boot Profiles and Multiple Environments

Do not use the same hard-coded JAAS string across local, staging, and production.

A profile configuration:

~~~yaml
spring:
  kafka:
    bootstrap-servers: KAFKA_BOOTSTRAP_SERVERS_SECRET_REFERENCE
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: KAFKA_SASL_JAAS_CONFIG_SECRET_REFERENCE
~~~

Non-secret values like mechanism/endpoint can be configured per environment. Secrets should be injected by the platform, not committed to profiles.

Local development can use a dedicated Kafka dev cluster and restricted principals. Do not disable TLS or switch to real PLAIN passwords just to make local config look simpler like production.

## 18. Kubernetes Secrets and Inline JAAS Strings

A Kubernetes Secret can supply an environment variable:

~~~yaml
env:
  - name: KAFKA_SASL_JAAS_CONFIG
    valueFrom:
      secretKeyRef:
        name: orders-kafka-auth
        key: sasl-jaas-config
~~~

The application uses secret injection per the Spring Boot configuration in the previous section.

Kubernetes Secrets must be protected:

- Enable encryption at rest for the backing store per cluster policy.
- Restrict who can read the Secret via RBAC.
- Do not print the entire Pod environment in diagnostic endpoints/logs.
- Avoid exposing unprotected Actuator env/configprops endpoints.
- Use dedicated namespaces/service accounts per workload.
- Restrict exec access into production containers.

A Secret exposed as an environment variable is typically read at process startup. Updating the Secret does not necessarily update the environment variable inside a running process; a controlled rollout/restart may be required for new credentials to take effect.

## 19. Mounting a JAAS File as a Secret Volume

If using a static JAAS file:

~~~yaml
volumes:
  - name: kafka-jaas
    secret:
      secretName: orders-kafka-jaas
      defaultMode: 0400
containers:
  - name: orders-service
    volumeMounts:
      - name: kafka-jaas
        mountPath: /etc/kafka
        readOnly: true
~~~

JVM:

~~~text
-Djava.security.auth.login.config=/etc/kafka/jaas.conf
~~~

The YAML example must be integrated into a complete Pod spec for the application. Verify file path, owner/group, and read permissions inside the image. If the process runs as non-root, mode 0400 might prevent that user from reading if ownership does not match; design securityContext/volume permissions intentionally.

Do not mount a Secret read-write for an application that only needs to read it. Do not copy JAAS files into the image via Dockerfile COPY.

## 20. Do Not Put JAAS Secrets on the Command Line or in Logs

A common mistake is running:

~~~text
java -Dsasl.jaas.config="...password=secret..." -jar app.jar
~~~

Credentials can appear in process arguments, shell history, diagnostic tools, or deployment manifests. Kafka client properties should not be passed in ways that expose passwords on the command line.

Prefer:

- Secret managers or workload identities.
- Controlled environment variable injection.
- Mounted Secret files with appropriate permissions.
- Callback handlers that fetch tokens/credentials dynamically.
- Redaction in logs, tracing, and exception reporting.

Do not log sasl.jaas.config. Do not include passwords in exception messages or startup configuration dumps.

## 21. Secret Rotation for SCRAM/PLAIN

Rotation must be coordinated between broker credentials and client credentials. A general procedure:

1. Create new credentials or use a platform-supported parallel mechanism.
2. Grant appropriate permissions to the new principal.
3. Update Secret Manager/Kubernetes Secret.
4. Recreate/restart clients via a controlled rollout to load new credentials.
5. Verify authentication and authorization across all replicas.
6. Monitor authentication failures, reconnects, and consumer lag.
7. Revoke old credentials after all clients have transitioned.

Do not change the password on the broker side before knowing which clients use that credential. An abrupt simultaneous rotation can cause hundreds of consumers to fail reconnection and trigger a rebalance storm.

If the credential mechanism supports multiple credentials/overlap during transition, use an overlap window to reduce downtime. Exact implementation depends on Kafka version and credential provider.

## 22. Secret Rotation for Kerberos

Kerberos rotation involves principals/keytabs and ticket renewal:

- Issue new keytab per KDC procedures.
- Verify principal and service principal name.
- Securely update the Secret volume.
- Determine whether the Kafka LoginModule reloads the keytab or requires re-login/recreating the client.
- Monitor ticket expiry and renewal failures.
- Roll out clients gradually to avoid all members reconnecting simultaneously.
- Revoke the old keytab after verifying all workloads.

An updated keytab file on a volume does not guarantee a running LoginModule automatically loads the new key. Verify actual lifecycle behavior and schedule client reauthentication/recreation if needed.

## 23. OAuth Token Refresh

OAuth bearer typically uses short-lived tokens. Requirements:

- Token callback handler capable of fetching new tokens.
- Refresh before expiry with a safety margin.
- Handle identity provider timeouts/rate limits.
- Never log bearer tokens.
- Verify audience, issuer, and scopes.
- Distinguish token acquisition errors from broker token rejection.
- Monitor time-to-expiry and refresh failures.

Do not solve token expiry by extending token lifetimes indefinitely or placing static access tokens in JAAS files. Use workload identity or client credentials flows compliant with security policy.

## 24. Principal Mapping and Authorization

Authentication identifies the principal. The broker authorizer then checks ACLs or policies.

~~~text
JAAS/SASL login succeeds
        |
        v
Principal = User:orders-reader
        |
        v
ACL check:
  READ orders.events
  READ group inventory-worker
        |
        +-- Allowed -> consume
        |
        +-- Denied -> authorization exception
~~~

The broker can use a principal builder or principal mapping rules to normalize principal names. With Kerberos, a principal like orders-reader@EXAMPLE.COM can be mapped to a short name depending on broker configuration.

Do not change JAAS passwords when the actual error is an ACL issue. Authentication failures typically show signs in SASL handshake/login; authorization failures typically occur after the broker has identified the principal and checked the operation.

## 25. TLS Truststore Is Still Required When Using SASL_SSL

JAAS does not configure the TLS trust chain. With SASL_SSL, the client must also trust the broker's certificate:

~~~yaml
spring:
  kafka:
    properties:
      security.protocol: SASL_SSL
      ssl.truststore.location: /var/run/secrets/kafka/client.truststore.p12
      ssl.truststore.password: KAFKA_TRUSTSTORE_PASSWORD_SECRET_REFERENCE
      ssl.truststore.type: PKCS12
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: KAFKA_SASL_JAAS_CONFIG_SECRET_REFERENCE
~~~

This is an example client truststore. Not every cluster requires a truststore password or separate file; the JVM truststore or PEM-based configuration can be used depending on the Kafka client version.

If the broker certificate is not trusted, failure occurs during the TLS handshake before SASL. Changing the JAAS password will not fix a truststore/certificate issue.

If using mTLS, client certificate/key configuration belongs to SSL properties; that is a separate transport authentication layer. mTLS can be combined with SASL, but verify that the broker listener and policy support both.

## 26. Separating Authentication and Authorization When Reading Errors

| Symptom | Likely Failing Layer | Check |
|---|---|---|
| TLS handshake failed | SSL/TLS | Certificate chain, hostname, truststore |
| No matching SASL mechanism | SASL negotiation | Broker enabled mechanisms and client sasl.mechanism |
| JAAS configuration error | JAAS parsing/login | LoginModule, control flag, options, semicolon |
| Authentication failed | SASL credential/identity | Username/password, SCRAM credential, token, Kerberos |
| Group authorization failed | Broker ACL | Group resource permissions |
| Topic authorization failed | Broker ACL | READ/WRITE/Describe permissions |
| Token expired/invalid | OAuth | Issuer, audience, expiry, callback refresh |
| GSS initiate failed | Kerberos | Keytab, principal, KDC, DNS, clock |

Errors may be wrapped by the Kafka client or Spring Kafka. Read the **root cause chain** and broker logs when you have access, not just the top-level exception in the application log.

## 27. Common JAAS Syntax Mistakes

### Missing Semicolon

Wrong:

~~~text
org.apache.kafka.common.security.scram.ScramLoginModule required
    username="reader"
    password="secret"
~~~

Right:

~~~text
org.apache.kafka.common.security.scram.ScramLoginModule required
    username="reader"
    password="secret";
~~~

### Wrong LoginModule Name

A typo in the package/class prevents the LoginModule from loading. Verify the exact name and Kafka client/JDK dependencies.

### Wrong Quotes or Escaping

Passwords with special characters must be represented accurately across the JAAS string, YAML, shell, and environment variables. Multiple parser layers can alter backslashes/quotes.

### Wrong Context Name

The static JAAS file defines KafkaClient, but the client/library requires a different context, or the JVM is loading a different file.

### SASL Mechanism Mismatch

ScramLoginModule with sasl.mechanism=PLAIN, or vice versa.

### Mixing YAML Quoting with JAAS Syntax

YAML strings must be properly quoted/escaped. A safe approach is passing the JAAS string via a secret reference instead of writing complex passwords directly in YAML.

## 28. YAML Configuration and Escaping Example

A JAAS string contains double quotes, spaces, and a semicolon. If inline in YAML:

~~~yaml
spring:
  kafka:
    properties:
      sasl.jaas.config: 'org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-reader" password="replace-me";'
~~~

Outer single quotes preserve the double quotes inside the JAAS string. If the password contains a single quote, backslash, or special YAML characters, proper escaping is required per YAML and JAAS parsers; do not build strings by concatenating raw user input.

In production, supply the entire JAAS string from secret injection:

~~~yaml
sasl.jaas.config: KAFKA_SASL_JAAS_CONFIG_SECRET_REFERENCE
~~~

The secret value must contain one complete JAAS entry. When injecting via CI/CD, check for extra newlines/trailing whitespace and quoting without printing the secret to pipeline logs.

## 29. Multiple Kafka Clusters in the Same Spring Boot Application

An application may connect to multiple clusters:

~~~text
Spring Boot service
   |
   +-- Primary Kafka
   |     +-- orders-reader principal
   |
   +-- Audit Kafka
         +-- audit-writer principal
~~~

If common spring.kafka.properties is used for both, it is easy to accidentally apply the same credentials or security protocol to all clients. For multiple clusters, create separate **named KafkaProperties/ConsumerFactory/ProducerFactory** beans, each with:

- its own bootstrap servers;
- its own security.protocol;
- its own sasl.mechanism;
- its own sasl.jaas.config;
- its own SSL trust material if needed;
- appropriate principals/ACLs.

Do not put two distinct clusters into the same bootstrap list if they are not part of the same Kafka cluster or do not share security/metadata semantics.

## 30. Configuring AdminClient and Kafka Streams

AdminClient, Kafka Streams, and Kafka Connect have their own security configurations per client/runtime.

- AdminClient needs SASL/JAAS properties when invoking describe/config/ACL operations.
- Kafka Streams needs configuration for internal consumers/producers and may have dedicated properties.
- Kafka Connect workers and connectors may use worker-level or connector-level overrides depending on deployment.

Do not assume the consumer factory configuration in Spring Kafka automatically applies to every independently constructed AdminClient or Kafka Streams instance.

If the application uses Spring Kafka Admin, verify that AdminClient properties are built from the proper Boot configuration. If constructing AdminClient manually, pass appropriate security properties and do not log JAAS.

## 31. Credential Scope and Least Privilege

A principal should have least-privilege permissions for its role:

| Principal | Suggested Permissions |
|---|---|
| orders-reader | READ/Describe on topic orders.events and READ on group orders-worker |
| orders-writer | WRITE/Describe on topic orders.audit |
| orders-admin | Only approved administrative permissions, not used for runtime listeners |
| broker-interbroker | Permissions and identity dedicated to broker-to-broker communication |

Exact permission/ACL names depend on the authorizer and Kafka distribution. The principle is that a producer does not need permission to read every topic; a consumer does not need permission to create topics or alter cluster configs.

Splitting credentials by workload helps:

- Revoke one service without impacting the whole system.
- Audit principals more clearly.
- Limit blast radius when a secret is exposed.
- Rotate per service.

## 32. JAAS and Secret Management

A secure secret pipeline:

~~~text
Secret manager / workload identity
             |
             v
Deployment platform injects secret
             |
             v
Spring Boot binds property
             |
             v
Kafka client LoginModule
             |
             v
SASL authentication
~~~

Principles:

- Do not hard-code passwords/tokens in Git.
- Do not put secrets into Docker build args or image layers.
- Do not store secrets in committed Helm values.
- Do not print ApplicationContext Environment/config props containing secrets.
- Mask secrets in startup diagnostics.
- Restrict secret read access by workload identity.
- Audit access and perform rotation.
- Purge secrets from shell history and CI logs if accidentally exposed.

If a credential is exposed, treat it as an incident: revoke/rotate, inspect access logs, review principal permissions, and assess data access. Merely editing a config file without revoking the old credential does not resolve the exposure.

## 33. Observing JAAS Login and SASL Handshake

Certain Kafka client logs can help diagnose issues:

- LoginModule initialization.
- SASL mechanism negotiation.
- Authentication exchange.
- Callback handler errors.
- Reauthentication/credential refresh.
- Broker disconnect/reconnect.

Logger names and detail levels depend on the Kafka client version. Enabling DEBUG/TRACE can produce huge log volumes and expose sensitive metadata. Do not assume logs always mask passwords/tokens as expected.

Procedure:

1. Start with the application exception and root cause.
2. Determine whether it is TLS, SASL negotiation, JAAS login, or ACL.
3. Enable narrow loggers briefly if needed.
4. Redact credentials/tokens before pasting logs into tickets/chat systems.
5. Turn off verbose logging after gathering evidence.

Do not leave debug logs containing raw JAAS config enabled in production.

## 34. Inspecting Effective Security Configuration

When configuring multiple layers, verify what the client actually receives:

- bootstrap.servers;
- security.protocol;
- sasl.mechanism;
- whether JAAS config was supplied;
- SSL truststore type/location;
- callback handler class;
- client.id/group.id.

Do not print raw sasl.jaas.config or tokens. You can log:

~~~text
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config.present=true
sasl.username=orders-reader
credential.source=kubernetes-secret/orders-kafka-auth
~~~

Usernames can also be sensitive data depending on policy; mask or log a normalized principal if needed.

If both Spring Boot common properties and consumer-specific properties declare security settings, verify the **effective config of each client factory** instead of guessing precedence.

## 35. JAAS Configuration and Kafka Client Lifecycle

A JAAS LoginContext is typically created during Kafka client authentication. When credentials change:

- Some callback handlers can fetch new tokens on re-login.
- Static JAAS files are not necessarily re-read for an existing LoginContext.
- Environment variables do not automatically change in a running process.
- Already-created Kafka producers/consumers may need to be closed/recreated to use new config.
- Spring Kafka listener containers need a controlled lifecycle restart if new factories/configs require new clients.

Do not update a Secret and assume running clients already use the new password. Verify via authentication events, client reconnects, and rollout behavior.

## 36. Connection Pools and Multiple Consumer Clients

A ConcurrentMessageListenerContainer can spawn multiple child consumers. If each child consumer uses SASL, credential/login behavior may be initialized per client instance.

During a simultaneous rollout or reconnect:

- Many clients log in at the same time.
- The identity provider/KDC may experience load spikes.
- Broker authentication rates rise.
- Rebalances and reconnects can happen concurrently.

Rotations should be rolled out gradually, with appropriate readiness/liveness probes and retry/backoff, avoiding restarting all pods at once if the group must maintain capacity.

## 37. Kerberos Clock Skew and DNS

Kerberos depends on timestamps and service principal resolution. Failure modes:

- Client clock skewed relative to KDC.
- DNS reverse lookup returns a hostname different from the service principal.
- Broker principal uses a different service name/realm than the client expects.
- Keytab contains the wrong principal.
- Ticket expired or renewal is not working.

When GSSAPI login fails, check:

1. NTP/clock synchronization on nodes and KDC.
2. Principal in the keytab.
3. Kafka broker service principal.
4. Forward/reverse DNS.
5. krb5.conf realm/KDC.
6. Keytab file permissions.
7. Ticket validity and renewal.

Do not change SCRAM usernames/passwords when the cluster actually uses GSSAPI.

## 38. OAuth Callback Handlers and Token Errors

With OAUTHBEARER, separate:

- Token acquisition failure: unable to obtain a token from the IdP.
- Token refresh failure: token is nearing expiry and refresh fails.
- Broker validation failure: broker does not trust issuer/audience/signature.
- Authorization failure: principal is authenticated but ACLs disallow it.

Logs should record:

~~~text
event=oauth_token_refresh_failed
provider=corp-idp
reason=timeout
token_present=true
token_value=REDACTED
~~~

Do not log tokens or full JWT payloads if they contain sensitive claims. When debugging JWTs, extract only necessary non-sensitive claims and adhere to security policy.

## 39. JAAS and AuthenticationException Handling

When a client receives AuthenticationException, do not catch it and retry infinitely with the same credentials. If the password is wrong or the user has not been created yet, retrying will not make the problem disappear.

An appropriate policy:

- Classify credential/configuration errors as non-retryable or retry slowly with limits.
- Alert early.
- Keep readiness reflecting connectivity per service requirements.
- Avoid rapid crash loops that flood the broker/IdP with login storms.
- After credentials are fixed, recreate clients/containers per lifecycle.

For transient network/IdP outages, retry with backoff and jitter can be appropriate. For ACL denials, fix the authorization policy.

## 40. Runbook: SASL Authentication Failed

### Step 1 — Confirm endpoint

Are the bootstrap server, port, listener, and environment correct? Is the client accidentally connecting to the wrong cluster or a PLAINTEXT port?

### Step 2 — Check security protocol

Does client security.protocol match the listener? SASL_SSL requires proper TLS certificate trust before SASL runs.

### Step 3 — Check mechanism

Is client sasl.mechanism in the broker's sasl.enabled.mechanisms? Do PLAIN/SCRAM/GSSAPI/OAUTHBEARER match the JAAS LoginModule?

### Step 4 — Check JAAS parsing

Is the LoginModule class right? Are options correct? Is the control flag valid? Does the inline string have the semicolon and proper escaping? Does the file context have the right name?

### Step 5 — Verify credential source

Does the secret reference exist? Did the pod mount/inject the right version? Are username/principal correct? Was trailing whitespace/newline added to the password? Does secret rotation have a rollout process?

### Step 6 — Check broker-side identity

Do the PLAIN server user config, SCRAM credentials, Kerberos service principal, or OAuth validator correspond?

### Step 7 — Check TLS/Kerberos/OAuth specifics

TLS truststore/hostname, Kerberos realm/keytab/clock, or OAuth issuer/audience/expiry/callback.

### Step 8 — Check broker logs

If authorized, cross-check broker authentication logs to see whether the handshake was rejected due to mechanism, credentials, or principal.

Do not include passwords, keytab contents, or bearer tokens in bug tickets.

## 41. Runbook: Authentication Succeeds but Topic Access Is Denied

Symptom: consumer connects but receives TopicAuthorizationException or GroupAuthorizationException.

1. Identify the principal after authentication/principal mapping.
2. Confirm exact consumer group name and topic name.
3. Check READ/Describe ACLs for the topic.
4. Check READ ACL for the consumer group.
5. For producers, check WRITE/Describe and transactional ID ACLs if using transactions.
6. Check cluster authorizer and principal builder/mapping.
7. Grant least-privilege permissions through the approved change process.
8. Verify with actual consumer/producer operations.

Do not change JAAS credentials if the principal already authenticates properly and only lacks ACLs.

## 42. Runbook: Application Works Initially but Fails Hours Later

Possibilities:

- OAuth token expired and refresh callback failed.
- Kerberos ticket/keytab renewal is not working.
- Credentials were rotated, but some pods have not reloaded.
- Broker reauthentication/connection renewal triggered an error.
- Secret volume/env versions are inconsistent across replicas.

Check:

1. Timestamp of last authentication success and first failure.
2. Token/ticket expiry timeline.
3. Redacted callback refresh logs.
4. Which pod/instance is using which secret version.
5. Client reconnect/re-authentication behavior.
6. Broker authentication failures and group rebalances.
7. Mechanism to recreate Kafka clients after secrets change.

Recover according to the credential provider lifecycle rather than restarting one random pod and ignoring remaining replicas.

## 43. Runbook: JAAS File Is Not Loaded

1. Check JVM system property java.security.auth.login.config.
2. Verify the absolute path inside the container.
3. Check volume mount and file existence.
4. Check process user read permissions.
5. Verify file encoding and syntax.
6. Confirm context name KafkaClient/KafkaServer for client/broker.
7. Check whether inline sasl.jaas.config overrides the static context.
8. Check that the file is loaded at process startup and whether clients were created before/after.
9. Do not print the file to the console for debugging.

If using Spring Boot, check whether the property is bound directly via sasl.jaas.config or the app genuinely relies on a static file.

## 44. Testing JAAS Configuration

A security test suite should cover:

### 44.1. Happy path with SASL/SCRAM

- Create a test principal with least-privilege permissions.
- Configure SASL_SSL and SCRAM mechanism.
- Consumer reads authorized topic.
- Producer writes only to authorized topic.

### 44.2. Wrong credential

- Use a wrong password.
- Verify authentication failure is clearly classified.
- No retry storm or infinite crash loop.
- Logs contain no secrets.

### 44.3. Mechanism mismatch

- Client chooses a mechanism not enabled on the broker.
- Verify error is classified as SASL negotiation/configuration.

### 44.4. Missing ACL

- Authentication succeeds with a valid principal.
- Revoke READ topic or group ACL.
- Verify authorization errors are distinguished from authentication failures.

### 44.5. TLS trust error

- Use a truststore that does not trust the test broker certificate.
- Verify error occurs at the TLS handshake and is not mistaken for a JAAS password error.

### 44.6. Secret rotation

- Transition from old credential to new credential following the procedure.
- Roll out clients gradually.
- Verify all instances reconnect.
- Revoke old credential after completion.

### 44.7. OAuth expiry/refresh

- Use a short-lived token in tests.
- Simulate IdP timeout and refresh failure.
- Verify callbacks do not log tokens and clients have an appropriate reconnect policy.

### 44.8. Kerberos

- Use a test realm/KDC.
- Verify principal/keytab.
- Verify clock skew and ticket renewal.

Do not use real production credentials in integration tests or CI logs.

## 45. Verifying Spring Boot Property Binding

When configuring multiple factories, tests should confirm:

- Consumer factory receives the right sasl.mechanism and JAAS credential source.
- Producer factory uses a separate principal if required.
- AdminClient does not accidentally use broader admin credentials than needed.
- No factory falls back to PLAINTEXT unexpectedly.
- Unresolved secrets fail fast rather than silently falling back to default credentials.
- Startup diagnostics do not print raw JAAS strings.

Test configuration/bean inspection and a SASL-enabled test broker can be used. Do not merely assert that the YAML string exists; verify that an actual Kafka client can authenticate and be authorized.

## 46. Common Configuration Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Setting only username/password | Broker does not know the right mechanism | Configure corresponding sasl.mechanism and JAAS LoginModule |
| Using PLAIN over unencrypted transport | Credentials can be exposed | Use SASL_SSL |
| Confusing JAAS with ACL | Authentication succeeds but operation is denied | Check principal and ACLs |
| Confusing SASL failure with TLS failure | Fixing the wrong layer | Read handshake/root cause |
| Wrong static context name | LoginContext cannot find entry | Check KafkaClient/KafkaServer and file |
| Missing semicolon | JAAS parse failure | Use complete entry syntax |
| SCRAM credential only put in client JAAS | Broker has no credential to verify | Create SCRAM user in broker metadata/control plane |
| Copying PLAIN user_* options to SCRAM | Wrong server configuration | Use SCRAM credential management |
| Hard-coding secrets in YAML/Git | Secret exposure | Secret manager/injection |
| Passing passwords in JVM command line | Can be exposed via process inspection/history | Secret-safe injection |
| Updating Secret without recreating clients | Clients still use old credentials | Understand reload/re-login lifecycle and rollout |
| One admin principal for all clients | Large blast radius | Separate least-privilege principals |
| Static OAuth token in JAAS | Token expires, auth outage | Callback handler/refresh |
| Kerberos keytab with wrong principal | GSSAPI login fails | Check keytab, realm, and service principal |
| Unsynchronized clocks | Kerberos tickets rejected | NTP and clock monitoring |
| Logging all properties | Can expose passwords/tokens | Redaction and allowlist |
| Assuming KafkaClient static file applies to all clients | Some clients have inline overrides or separate contexts | Check effective config per factory |

## 47. Production Checklist

Before deploying JAAS configuration:

1. Have you identified the exact authentication mechanism supported by the broker listener?
2. Does security.protocol match the endpoint and TLS requirements?
3. Is the LoginModule class available in the runtime?
4. Are JAAS syntax, control flag, options, and semicolon valid?
5. Does the client use inline sasl.jaas.config or a static JAAS file, and is ownership clear?
6. Is the static context name KafkaClient/KafkaServer correct?
7. Do Spring Boot consumer, producer, and admin clients each have appropriate effective security config?
8. Has broker-side PLAIN/SCRAM/Kerberos/OAuth configuration been provisioned?
9. Does the principal have least-privilege ACLs?
10. Are TLS truststores/certificates configured independently of JAAS?
11. Are secrets sourced from a secret manager/workload identity instead of Git/images?
12. Do logs, Actuator, and diagnostics mask JAAS/passwords/tokens?
13. Are Kubernetes Secret RBAC, encryption at rest, and volume permissions appropriate?
14. Does rotation have an overlap/rollout/reconnect plan?
15. Have OAuth token refresh or Kerberos ticket renewal been tested?
16. Could multiple replicas reconnect simultaneously and cause an authentication storm?
17. Are AuthenticationException and authorization failures distinguished?
18. Are SASL handshake, TLS, and broker authentication logs observable during incidents?
19. Are there integration tests for wrong credentials, mechanism mismatch, TLS, ACLs, and rotation?
20. Is there a runbook to roll back/rotate/revoke credentials on exposure or auth outage?

## 48. Conclusion

**JAAS configuration** is part of the authentication layer when Kafka clients use SASL. In Spring Kafka, the most convenient configuration approach is usually passing the LoginModule entry via **sasl.jaas.config**, combined with the proper **security.protocol** and **sasl.mechanism**. Static JAAS files with KafkaClient/KafkaServer contexts remain useful in environments managing logins at the JVM or broker level.

Secure operations require distinguishing PLAIN, SCRAM, GSSAPI, and OAUTHBEARER; understanding whether credentials live on the client, broker, or identity provider; separating authentication from TLS and ACLs; managing secrets via the platform; and planning for rotation/re-authentication. When errors occur, identify whether they happen at TLS handshake, JAAS parsing/login, SASL negotiation, broker authentication, or authorization before changing credentials.

A good JAAS configuration does more than just let a client log in. It must restrict the principal to the right permissions, keep credentials out of logs/artifacts, support controlled rotation, and provide enough evidence to investigate authentication failures without disrupting the entire consumer group.
