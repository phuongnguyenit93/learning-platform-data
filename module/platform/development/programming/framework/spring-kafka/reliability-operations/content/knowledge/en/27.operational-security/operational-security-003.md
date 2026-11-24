# AuthenticationException

## 1. What Is AuthenticationException?

**AuthenticationException** is a Kafka client exception indicating that the client failed to authenticate with the Kafka broker. It typically occurs when a consumer or producer attempts an operation requiring an authenticated connection, but the broker rejects the identity or authentication mechanism presented by the client.

The class is in the package:

~~~java
org.apache.kafka.common.errors.AuthenticationException
~~~

A common subclass in SASL connections is:

~~~java
org.apache.kafka.common.errors.SaslAuthenticationException
~~~

For example, the Order Fulfillment service connects to Kafka using SASL/SCRAM. After the password is rotated on the broker, an old pod still uses the previous credential. When the Kafka client performs the authentication handshake, the broker rejects the credential and the client may throw AuthenticationException or a corresponding subclass.

~~~text
Spring Kafka application
          |
          v
      Kafka client
          |
          | SASL/TLS authentication
          v
      Kafka broker
          |
     +----+---------------------+
     |                          |
 Valid credential        Invalid credential
     |                          |
     v                          v
Authenticated client      AuthenticationException
     |                          |
     v                          v
Kafka operations          Retry or fail per policy
~~~

This is an error at the **Kafka connection security layer**. It differs from an exception thrown by a business method processing a record. In many scenarios, the listener has not received any record yet, so there is no specific message to retry or route to a DLT.

## 2. Which Question Does Authentication Answer?

Kafka security has two conceptual steps:

1. **Authentication:** who is the client?
2. **Authorization:** what is the authenticated principal allowed to do?

Authentication establishes the connection's identity. Authorization checks permissions on resources such as topics, consumer groups, transactional IDs, or the cluster.

| Aspect | Authentication | Authorization |
|---|---|---|
| Question | Who is the client? | What is the client allowed to do? |
| Error example | Wrong SCRAM password | Principal lacks READ on topic |
| Typical exception | AuthenticationException | AuthorizationException |
| Fix | Credential, SASL, TLS, principal mapping | ACL, resource, operation |
| Fixable by adding an ACL? | No | Possibly |
| Fixable by rotating the password? | Possibly | No, if permissions are still missing |

A valid password does not automatically grant READ on a topic. A valid READ ACL also does not make a client with a wrong password authenticated.

**Do not classify every security error as AuthenticationException.** Read the exception class and root cause before choosing remediation.

## 3. Where the Exception Occurs in the Kafka Client

A Kafka client may have to authenticate when establishing a connection or when sending a request to the broker. This can happen when a consumer fetches metadata, joins a group, fetches records, or when a producer sends a record.

A typical consumer flow:

~~~text
KafkaListenerContainer starts
          |
          v
ConsumerFactory creates KafkaConsumer
          |
          v
Consumer subscribes to topic
          |
          v
KafkaConsumer.poll()
          |
          v
Kafka client communicates with broker
          |
          v
Authentication handshake
          |
     +----+--------------------+
     |                         |
    OK                       Rejected
     |                         |
     v                         v
Metadata/group/fetch     AuthenticationException
     |                         |
     v                         v
Listener receives       Container retry/stop policy
ConsumerRecord
~~~

Not every authentication failure occurs at the exact moment KafkaConsumer is constructed. Some errors only appear when the client starts sending requests to the broker. Therefore, a successful startup log is not enough to prove the consumer has authenticated and can read data.

Conversely, errors occurring before the listener container is created, such as invalid bean or property configuration, may not go through the poll loop's AuthenticationException handling path.

## 4. Common Causes

| Cause Category | Example | Investigation Direction |
|---|---|---|
| Wrong credential | SCRAM username/password mismatch | Secret version and broker principal |
| Expired/disabled credential | Password rotated or account disabled | Rotation process, account status |
| Wrong SASL mechanism | Client uses SCRAM-SHA-256 while broker listener only allows SCRAM-SHA-512 | Broker listener and client config |
| Wrong JAAS | Incorrect login module or option | sasl.jaas.config |
| TLS client identity | Client certificate expired or untrusted | Certificate chain, validity, principal mapping |
| OAuth token | Token expired, wrong audience/issuer, or rejected | Token provider, issuer, audience, clock |
| Kerberos | Ticket expired, wrong service principal, or faulty keytab | KDC, principal, keytab, clock skew |
| Principal mapping | Broker derives a different principal than the ACL expects | Broker security configuration |
| Broker security change | Listener or authentication provider changed | Broker deployment and audit logs |
| Secret injection error | Pod receives empty value or stale secret | Mounted secret, environment, and rollout |

Some TLS, DNS, network, or client configuration errors may be represented by other exceptions such as SSLException, ConfigException, or KafkaException. Do not assume every connection error mentioning security is an AuthenticationException.

## 5. Distinguishing AuthenticationException from AuthorizationException

Common authorization exceptions:

~~~java
org.apache.kafka.common.errors.AuthorizationException
org.apache.kafka.common.errors.TopicAuthorizationException
org.apache.kafka.common.errors.GroupAuthorizationException
~~~

The exact subclass name depends on the Kafka client version and the denied operation.

Example:

~~~text
SASL authentication succeeds
          |
          v
Broker identifies principal:
User:orders-reader
          |
          v
Consumer requests READ on orders.created
          |
          v
ACL check
          |
     +----+----------------------+
     |                           |
   ALLOW                       DENY
     |                           |
     v                           v
Fetch records              AuthorizationException
~~~

When you see AuthenticationException, check identity and credentials first. When you see AuthorizationException, check the principal, resource, and denied operation.

Do not fix AuthenticationException by granting superuser permissions. Do not fix AuthorizationException by repeatedly changing passwords.

## 6. What Is SASL in the Context of This Exception?

SASL is an authentication framework that Kafka can use to verify client identity. Common mechanisms:

| Mechanism | Brief Description |
|---|---|
| PLAIN | Sends username/password over SASL; should be used with TLS to protect in transit |
| SCRAM-SHA-256 | Challenge-response using salted password with SHA-256 |
| SCRAM-SHA-512 | Challenge-response using salted password with SHA-512 |
| GSSAPI | Typically integrates with Kerberos |
| OAUTHBEARER | Uses OAuth bearer tokens |
| Custom mechanism | Depends on plugins and broker configuration |

Client and broker must agree on the mechanism for the target listener. A client configured with the wrong mechanism cannot complete the authentication handshake.

### 6.1. SASL_SSL and SASL_PLAINTEXT

- **SASL_SSL** combines SASL authentication with TLS encryption.
- **SASL_PLAINTEXT** uses SASL without TLS transport encryption.

In production environments, use TLS according to your organization's security policy. PLAIN without TLS risks exposing credentials on the network.

### 6.2. TLS and mutual TLS

With mutual TLS, the client presents a certificate so the broker authenticates its identity. Truststore and keystore serve different roles:

- Truststore holds CAs/certificates the client trusts when verifying the broker.
- Keystore holds the client's private key and certificate when client authentication is required.

Expired certificates, invalid chains, or wrong principal mapping can cause handshakes to fail. However, TLS errors are not always surfaced as Kafka AuthenticationException; check the actual root cause.

## 7. Configuring SASL/SCRAM in Spring Boot

Example consumer configuration:

~~~yaml
spring:
  kafka:
    bootstrap-servers:
      - kafka-a.example.net:9093
      - kafka-b.example.net:9093

    consumer:
      group-id: order-fulfillment
      enable-auto-commit: false
      properties:
        "[security.protocol]": SASL_SSL
        "[sasl.mechanism]": SCRAM-SHA-512
        "[sasl.jaas.config]": 'org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-reader" password="<secret-injected-at-runtime>";'
~~~

The password string is a placeholder only. In production, fetch secrets from a secret manager, Kubernetes Secret, or a platform-managed injection mechanism. Do not commit passwords to source control.

The corresponding producer configuration must use an identity permitted to publish to the topic. Do not assume consumer and producer should share the same principal; separating principals enables least privilege.

### 7.1. Verifying the client actually receives the secret

An application might start even if a secret was injected incorrectly into runtime configuration, depending on when the client opens its connection. Verify:

- Secret key exists.
- Value is non-empty.
- Pod uses the right secret version.
- Environment/property binding points to the right key.
- JAAS config is built properly.
- ConsumerFactory uses the right security properties.
- Broker logs receive the expected principal.

Do not log passwords or full JAAS strings for debugging.

## 8. Broker-Side SCRAM Configuration

The broker must support the mechanism used by the client and have credentials for that principal. The process for managing SCRAM users depends on the Kafka deployment, broker version, and administrative tooling.

Operationally, verify:

1. The broker listener enables SASL.
2. The SCRAM-SHA-512 mechanism is allowed on that listener.
3. User orders-reader has been provisioned.
4. The password on the broker matches the secret used by the application.
5. Brokers across the cluster have consistent security configuration.
6. Rotation was applied to the right cluster/environment.

Do not assume updating one broker updates the whole cluster. With multi-broker deployments or external identity providers, verify state across the entire connection path.

## 9. TLS and Certificate Configuration

Example client using SASL_SSL with a truststore:

~~~yaml
spring:
  kafka:
    properties:
      "[security.protocol]": SASL_SSL
      "[sasl.mechanism]": SCRAM-SHA-512
      "[ssl.truststore.location]": /var/run/kafka-secrets/truststore.p12
      "[ssl.truststore.type]": PKCS12
      "[ssl.truststore.password]": "<truststore-password-from-secret>"
~~~

If using mutual TLS, also configure the keystore according to broker requirements and client certificate policy. Truststore/keystore passwords are secrets; do not put them into logs or repositories.

Inspect certificates:

- Not Before and Not After.
- Matching Subject/SAN.
- Certificate chain up to a trusted CA.
- Key usage and extended key usage.
- Truststore contains the right CA.
- Clocks on pod/node and broker are not significantly skewed.
- Whether the broker listener requires a client certificate.

An expired certificate can cause a handshake error, though the exact exception depends on where the error occurs in the TLS stack and the Kafka client version.

## 10. Consumer-Side AuthenticationException

When a consumer encounters AuthenticationException during Kafka operations, the listener may not have received any record from the broker.

That means:

- There is no specific ConsumerRecord to pass through DefaultErrorHandler.
- There is no record to route to a DLT simply because credentials are wrong.
- Retrying a record cannot fix a username/password.
- Security connectivity and consumer container lifecycle must be handled.

Illustrative flow:

~~~text
KafkaConsumer.poll()
       |
       v
AuthenticationException
       |
       v
No record delivered to listener
       |
       v
Container authentication retry policy
       |
       +--> Wait and retry
       |
       +--> Stop container when retry is disabled
~~~

This is a connection/security-layer error. Look for the root cause in Kafka client logs and broker authentication logs.

## 11. Producer-Side AuthenticationException

AuthenticationException can also occur on the producer side. When KafkaTemplate sends a message, the error can be reported via a callback or CompletableFuture depending on the API used.

Example:

~~~java
kafkaTemplate.send("orders.created", orderId, event)
    .whenComplete((result, error) -> {
        if (error != null) {
            log.error("Kafka send failed", error);
            return;
        }

        log.debug(
            "Kafka send succeeded: topic={}, partition={}",
            result.getRecordMetadata().topic(),
            result.getRecordMetadata().partition()
        );
    });
~~~

In production, inspect the exception chain to distinguish AuthenticationException, AuthorizationException, timeouts, or serialization errors.

**authExceptionRetryInterval on a listener container only governs the consumer container path.** It does not configure retries for a KafkaTemplate producer. Producers need retry/error handling aligned with the producer API, delivery timeout, idempotence, and business outbox policy.

Do not treat a future as a completed business transaction if database state updates or other event publications still remain.

## 12. How Does Spring Kafka Handle AuthenticationException?

For listener containers, Spring Kafka provides the property:

**authExceptionRetryInterval**

This property specifies the wait duration before retrying when KafkaConsumer throws AuthenticationException or AuthorizationException in supported code paths.

If the interval is not configured, the container's default behavior is to stop when the corresponding auth/authz exception occurs. When an interval is configured, the container can keep retrying instead of stopping immediately.

Example:

~~~java
factory.getContainerProperties()
    .setAuthExceptionRetryInterval(Duration.ofSeconds(30));
~~~

The retry interval must be shorter than the consumer's **max.poll.interval.ms**. Confirm the exact property and behavior for your deployed Spring Kafka version.

### 12.1. The retry interval does not fix credentials by itself

Suppose the password changed on the broker while the pod still uses the old password. A consumer retrying after 30 seconds will still use the same old credential and keep failing.

The retry interval only creates a window for external conditions to be repaired: new secrets loaded, the broker identity provider recovering, or security configuration fixed.

If the client does not support reloading credentials at runtime, recreate the KafkaConsumer or restart the process according to deployment policy.

### 12.2. Do not set the interval close to max.poll.interval.ms

Example:

~~~text
max.poll.interval.ms          = 300000 ms
authExceptionRetryInterval    = 30000 ms
~~~

30 seconds is shorter than 5 minutes, but total time between polls also depends on record processing time, GC, network, and other callbacks. Do not place the retry interval near the limit just because a naive comparison looks valid.

## 13. ConsumerRetryAuthEvent and Recovery

When an auth exception is retried per configuration, supported versions of Spring Kafka can publish:

~~~java
org.springframework.kafka.event.ConsumerRetryAuthEvent
~~~

The event has a reason to distinguish:

~~~java
ConsumerRetryAuthEvent.Reason.AUTHENTICATION
ConsumerRetryAuthEvent.Reason.AUTHORIZATION
~~~

After a retry succeeds, the framework can publish:

~~~java
org.springframework.kafka.event.ConsumerRetryAuthSuccessfulEvent
~~~

An observer can log it:

~~~java
@Component
public class KafkaAuthenticationObserver {

    @EventListener
    public void onRetry(ConsumerRetryAuthEvent event) {
        log.warn(
            "Kafka authentication retry: reason={}, listener={}",
            event.getReason(),
            event.getContainer()
        );
    }

    @EventListener
    public void onRecovered(ConsumerRetryAuthSuccessfulEvent event) {
        log.info(
            "Kafka authentication retry succeeded: source={}",
            event.getSource()
        );
    }
}
~~~

The retry event indicates the container is retrying; the successful event indicates the auth retry succeeded after a prior error. Do not treat the successful event as proof that the listener has processed records or that consumer lag has dropped to 0.

If the retry interval is not configured, the container may follow the stop branch and publish ConsumerStoppedEvent with an AUTH-related reason in supported versions.

## 14. Distinguishing Authentication Errors from Record Processing Errors

A listener can throw an exception while processing data:

~~~java
@KafkaListener(topics = "orders.created")
public void consume(OrderCreated event) {
    fulfillmentService.process(event);
}
~~~

If process throws IllegalStateException due to a database timeout, that is a **record processing failure**. DefaultErrorHandler can be used to retry the record or recover.

If KafkaConsumer.poll throws AuthenticationException before delivering a record, DefaultErrorHandler has no business record to handle.

| Error | Appropriate Mechanism |
|---|---|
| AuthenticationException | Fix credential/TLS/SASL; auth retry or container lifecycle |
| AuthorizationException | Fix ACL/principal/resource |
| Database timeout in listener | DefaultErrorHandler/backoff or business retry |
| JSON deserialization error | ErrorHandlingDeserializer and recovery policy |
| Poison record | Non-retryable classification or DLT |
| Producer send authentication failure | Producer future/callback, security fix, and delivery policy |

Do not send a message to a DLT just because the consumer cannot log into Kafka. The listener has not received any message to recover.

## 15. ConsumerStoppedEvent When Auth Fails

If the container stops due to AuthenticationException or AuthorizationException and no auth retry interval is configured, Spring Kafka can publish **ConsumerStoppedEvent** with reason **AUTH** in supported versions.

This differs from ConsumerRetryAuthEvent:

| Event | Meaning |
|---|---|
| ConsumerRetryAuthEvent | Container is retrying after an auth/authz error |
| ConsumerRetryAuthSuccessfulEvent | Auth retry succeeded |
| ConsumerStoppedEvent | Consumer has stopped |
| ConsumerStartedEvent | Consumer started its lifecycle |
| ConsumerPartitionAssignedEvent | Consumer was assigned partitions |

If an observer receives ConsumerStoppedEvent, distinguish between operator stop, application shutdown, and auth failure. Do not auto-restart indefinitely while the root cause persists.

## 16. Secret Rotation and Consumer Lifecycle

A practical issue is that passwords are loaded into the environment at JVM startup. Once a secret manager updates to a new value, the running process may still hold the old value.

~~~text
Secret manager
     |
     v
Pod starts with password v1
     |
     v
KafkaConsumer uses v1
     |
     v
Broker rotates to password v2
     |
     v
Existing consumer authentication fails
     |
     v
Retry may still use v1
~~~

Questions to verify:

1. Is the secret volume updated?
2. Does the application read the secret each time KafkaConsumer is created or only at startup?
3. Does ConsumerFactory retain previously bound security properties?
4. Does recreating KafkaConsumer load the new value?
5. Is a pod/JVM restart needed to refresh the environment?
6. Is there a rolling restart to preserve sufficient consumer capacity?

**Restarting a listener container does not change environment variables by itself.** If configuration is only loaded at process start, you need a process restart or a deliberately designed and tested reload mechanism.

### 16.1. Rolling rotation

With multiple consumer replicas:

~~~text
1. Provision new credential
2. Configure broker to accept new credential
3. Roll out application using new credential
4. Confirm all consumers authenticate
5. Revoke old credential after migration
~~~

Exact sequencing depends on the SCRAM mechanism, identity provider, and ability to support old/new credentials concurrently. Do not revoke the old credential before replicas have migrated to the new credential if the deployment requires zero-downtime transition.

## 17. OAuth Bearer Tokens

With SASL/OAUTHBEARER, the client needs a valid token per issuer, audience, signature, expiration, and broker validation policy.

AuthenticationException can occur if the token is rejected. Investigate:

- Has the token expired?
- Are client and issuer clocks skewed?
- Are audience and issuer correct?
- Is JWKS/key rotation up to date?
- Is the token callback/refresh handler working?
- Is the broker validating the token with the right trust configuration?

Do not log tokens to debug. Only log token acquisition outcomes, issuer aliases, or approved error categories.

If the token provider cannot refresh, increasing the auth retry interval will not create a valid token. You must restore the token provider or OAuth configuration.

## 18. Kerberos/GSSAPI

With GSSAPI, authentication depends on Kerberos tickets, service principals, keytabs, and the KDC.

Common causes:

- Expired ticket.
- Keytab does not match the principal.
- Wrong service principal name.
- Incorrect DNS canonicalization.
- Clock skew between client and KDC.
- KDC unreachable.
- Misconfigured JAAS login module.

Inspect Kerberos using platform tooling and broker/client logs per security policy. Do not copy keytabs or ticket caches into issue trackers.

If credential renewal can occur in-process, confirm the Kafka client/SASL callback uses that renewal mechanism. Otherwise, restart/recreate consumers according to lifecycle.

## 19. TLS Trust and Client Certificates

TLS errors can happen at multiple steps:

- Client does not trust the CA that signed the broker certificate.
- Broker does not trust the CA of the client certificate.
- Certificate expired.
- Subject/SAN mismatch.
- Wrong keystore/truststore password.
- Private key does not match certificate.
- Incompatible protocol/cipher policy.

Not every TLS error is wrapped as AuthenticationException. For instance, an unreadable truststore may fail immediately at client initialization, while a handshake failure may surface as SSLException or KafkaException depending on cause and version.

Read nested causes, not just the outermost exception name.

## 20. Diagnostics from Logs and Brokers

A useful AuthenticationException log should include:

- Timestamp.
- Service/pod/instance.
- Client ID and group ID if available.
- Broker endpoint.
- Security protocol and mechanism, without secrets.
- Exception class and nested causes.
- Listener ID or producer identity.
- Approved secret/config version alias.

Broker authentication logs can show the principal, listener, and rejection reason. Use them to confirm which identity the broker actually received.

Do not log raw SASL JAAS configs, passwords, tokens, private keys, or serialized security material.

### 20.1. Checking effective configuration

A deployment may have multiple configuration sources:

- application.yml.
- Environment variables.
- Kubernetes ConfigMap/Secret.
- Secret manager provider.
- Custom ConsumerFactory.
- Kafka client properties map.

Determine the **effective** values of security.protocol, sasl.mechanism, JAAS config, and truststore/keystore paths. Do not assume the YAML file is the final source if environment variables override it.

## 21. Distinguishing Startup vs. Runtime Exceptions

There can be two failure groups:

**Startup/configuration failure:** the application or bean cannot construct KafkaConsumer because a property is invalid, a keystore is unreadable, or configuration is broken. The container may fail to start; ConsumerFailedToStartEvent or an application startup failure may appear depending on lifecycle.

**Runtime authentication failure:** the consumer is running and the Kafka client hits AuthenticationException while communicating with the broker. When auth retry is configured, the container may publish ConsumerRetryAuthEvent.

The authExceptionRetryInterval property is not a universal mechanism to fix bean initialization errors or configuration parse errors. Examine the timing of the exception and its stack trace.

## 22. Separate Principals for Producer and Consumer

A least-privilege architecture can use:

| Principal | Expected Permissions |
|---|---|
| User:orders-api | WRITE on orders.created |
| User:orders-reader | READ on orders.created and READ on group order-fulfillment |
| User:orders-dlt-reader | READ on orders.created.DLT and dedicated DLT group |
| User:kafka-admin | Administrative permissions per policy, not used at runtime |

If the same principal is shared across all services, a single exposed credential creates a much larger blast radius.

AuthenticationException indicates the client failed to authenticate its identity. Once authentication succeeds, the broker still enforces per-principal/resource ACLs.

## 23. Backoff and Retry Policy

If using authExceptionRetryInterval, choose the interval based on:

- Time typically needed to fix credentials/ACLs.
- max.poll.interval.ms.
- Consumer group SLO.
- Consumer lag growth rate.
- Number of replicas failing concurrently.
- Broker authentication capacity.
- Alerting/escalation workflow.

Do not set an interval so short that all consumers retry simultaneously, causing a connection/authentication storm. Consider adding jitter in an external automation layer if policy allows; do not assume the framework interval includes jitter.

If credentials are permanently wrong, infinite retries only generate log noise and keep the system in a degraded state. Alert based on outage duration and restart budget.

## 24. Why Restarting Does Not Automatically Fix AuthenticationException

Restarting a container can create a new KafkaConsumer, but if ConsumerFactory still uses the same wrong password, the new consumer will fail too.

~~~text
Container A
  credential v1
  authentication fails
       |
       v
stop/start
       |
       v
Container B
  credential v1
  authentication fails again
~~~

A restart only helps if it actually loads updated configuration or reinitializes the client after the root cause has been fixed.

Before restarting:

1. Identify the principal and root cause.
2. Fix credentials, certificates, or broker configuration.
3. Confirm the consumer factory will pick up the new value.
4. Choose a container restart or pod restart depending on how config is loaded.
5. Stop completely before starting again.
6. Confirm the consumer joins the group and receives partitions.

Do not reset offsets just to handle an authentication failure. Offsets are data positions, not credentials.

## 25. AuthenticationException and Transactions

With transactional producers or consume-transform-produce, an authentication failure can prevent the producer from initializing transactions or the consumer from fetching data.

If the transaction has not started/committed, an authentication failure does not yield a successful transaction outcome. Once connectivity is restored, verify that the transaction manager and producer factory resume working.

For transactional producers, also check:

- Transactional ID prefix.
- Whether the principal has required permissions on the transactional ID.
- Broker transaction coordinator.
- Whether producer fencing occurred independently of authentication.

**ProducerFencedException is not AuthenticationException.** Both errors require separate root-cause analysis.

If a consumer already performed an external side effect outside Kafka before the connection error or process stop, that side effect will not automatically roll back with a Kafka transaction. Use idempotency or outbox/inbox patterns appropriately.

## 26. Integration Testing AuthenticationException

A useful test should use a real test Kafka broker with SASL authentication enabled, such as a Testcontainers image/configuration supported by the project.

General scenario:

1. Start the broker with the chosen SASL mechanism.
2. Provision the test consumer principal and credentials.
3. Start the Spring Kafka listener with valid security properties.
4. Confirm the listener receives a sample record.
5. Change credentials or create a client with wrong credentials in the test environment.
6. Confirm the client hits AuthenticationException or the actual subclass.
7. If testing Spring auth retry, configure authExceptionRetryInterval shorter than max.poll.interval.ms.
8. Capture ConsumerRetryAuthEvent when supported by the version.
9. Restore authentication conditions.
10. Wait for ConsumerRetryAuthSuccessfulEvent if the retry path is supported and the client can recover.
11. Confirm the consumer resumes polling and processing records.
12. Clean up test credentials and resources.

Do not use a mock broker that simply throws an arbitrary exception and conclude SASL/TLS authentication works end-to-end. Unit tests for exception classification are useful but do not replace integration tests against real broker security.

### 26.1. Fail-fast test

Another test without configuring authExceptionRetryInterval:

- Trigger an authentication failure.
- Observe the container stopping per Spring Kafka version behavior.
- Check ConsumerStoppedEvent with reason AUTH if supported by API/version.
- Fix the credentials.
- Perform a controlled container restart.
- Confirm the listener processes subsequent records.

## 27. Monitoring and Alerting

| Signal | Meaning |
|---|---|
| AuthenticationException count | Frequency of authentication errors |
| SaslAuthenticationException count | SASL-related errors |
| ConsumerRetryAuthEvent reason AUTHENTICATION | Container is retrying authentication |
| ConsumerRetryAuthSuccessfulEvent | Auth retry has recovered |
| ConsumerStoppedEvent reason AUTH | Consumer stopped due to auth/authz depending on version |
| ConsumerFailedToStartEvent | Consumer failed to start |
| Broker auth failure logs | Rejected principal/listener |
| Secret rotation version | Which credential is currently in use |
| Consumer lag | Impact on data processing progress |
| Connection/reconnect metrics | Ability to communicate with broker |

Alerts should aggregate multiple retry events into one ongoing incident rather than paging on every single event.

Example alert conditions:

- Authentication failure persists beyond SLO threshold.
- Multiple replicas fail together right after secret rotation.
- Consumer lag grows during retries.
- ConsumerStoppedEvent reason AUTH appears on a critical listener.
- No successful retry occurs after a secret has been rolled out.

## 28. Production Runbook

When encountering AuthenticationException:

1. Record timestamp, service, pod, client ID, and listener/group if available.
2. Read the exception class and full nested cause chain.
3. Identify whether the failing operation is on the consumer or producer.
4. Check the effective security.protocol and sasl.mechanism.
5. For SCRAM/PLAIN, verify username, password, and broker credentials.
6. For OAuth, check token issuer, audience, expiration, and refresh.
7. For Kerberos, check ticket, principal, keytab, KDC, and clock.
8. For TLS, check truststore, certificate chain, expiry, and client identity.
9. Cross-check broker authentication logs.
10. Distinguish AuthenticationException from AuthorizationException.
11. Check the actual secret/config version used by the process.
12. If the consumer container is retrying, monitor ConsumerRetryAuthEvent and lag.
13. If the container has stopped, fix the root cause before restarting.
14. If secrets are only loaded at JVM start, perform an appropriate rolling pod restart.
15. Confirm the consumer joins the group and receives partitions.
16. Confirm the listener processes records and offsets advance.
17. Check for duplicate side effects if uncommitted records are redelivered.
18. Document the root cause and update the credential rotation procedure.

Do not reset offsets, grant superuser permissions, or restart indefinitely just to make the exception disappear.

## 29. Common Misconceptions

**AuthenticationException means the principal lacks READ on the topic.** Incorrect; that is authorization.

**Adding an ACL fixes a wrong password.** Incorrect; you must fix credentials or authentication configuration.

**DefaultErrorHandler retries AuthenticationException from poll.** Incorrect; the error handler handles record listener failures, whereas auth exceptions can happen before a record is delivered.

**DLT is where messages go when a consumer cannot log in.** Incorrect; the consumer has not received any record to recover.

**authExceptionRetryInterval automatically refreshes passwords.** Incorrect; it only controls retry timing.

**Restarting a listener container always loads new secrets.** Incorrect if secrets are bound into the environment at JVM startup.

**Every TLS error is an AuthenticationException.** Incorrect; inspect the actual exception and nested cause.

**Producer is also controlled by authExceptionRetryInterval.** Incorrect; that property belongs to listener containers.

**Authentication success means permission to read topics.** Incorrect; the broker still checks ACLs.

**Consumer retry success means lag is zero.** Incorrect; you must verify assignment, processing, and commits.

**Log the full JAAS string to find the wrong password.** Unsafe; JAAS may contain secrets.

**Increasing retries infinitely solves expired credentials.** Incorrect; credentials must be restored.

## 30. Implementation Checklist

- [ ] Correctly identify Kafka AuthenticationException and nested causes.
- [ ] Distinguish authentication from authorization.
- [ ] Identify whether the error is at consumer, producer, or startup.
- [ ] Verify security.protocol and SASL mechanism.
- [ ] Manage username/password via a secret provider.
- [ ] Verify OAuth/Kerberos/TLS if used.
- [ ] Never log JAAS, passwords, tokens, or private keys.
- [ ] Configure authExceptionRetryInterval intentionally for listener containers.
- [ ] Keep retry interval smaller than max.poll.interval.ms.
- [ ] Observe ConsumerRetryAuthEvent and successful events when supported by version.
- [ ] Have a policy for container stop with reason AUTH.
- [ ] Do not use DefaultErrorHandler/DLT for auth connection errors before receiving records.
- [ ] Maintain a secret rotation process and verify reload behavior.
- [ ] Use separate principals and least-privilege ACLs.
- [ ] Test authentication failures against a real secured broker.
- [ ] Verify group assignment, processing, and offsets after recovery.

## 31. Key Takeaways

**AuthenticationException** is a Kafka client exception indicating the client failed to authenticate with the broker. Causes typically lie in credentials, SASL mechanism, JAAS, OAuth tokens, Kerberos, or TLS client identity. It differs from **AuthorizationException**, which occurs when an authenticated principal lacks permissions on a resource.

On Spring Kafka consumers, **authExceptionRetryInterval** can let the container wait and retry when KafkaConsumer throws AuthenticationException or AuthorizationException in supported paths. If unconfigured, the container can stop. The retry interval does not fix credentials and does not replace secret management. Producer-side AuthenticationException needs handling via producer futures/callbacks and a separate delivery policy.

When troubleshooting, read nested causes and broker logs, verify effective security configuration, fix credentials/certificates or the identity provider, and choose a container or pod restart based on how the application loads secrets. After authentication recovers, confirm the consumer joins the group, receives partitions, processes records, and commits offsets; protect side effects against redelivery using idempotency.

