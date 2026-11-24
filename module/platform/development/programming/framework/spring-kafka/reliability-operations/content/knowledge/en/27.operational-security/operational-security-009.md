# Zero-Downtime Credential Rotation

In **Spring Kafka Reliability Operations**, **zero-downtime credential rotation** is the process of replacing passwords, SASL secrets, OAuth client credentials, TLS certificates, or Kerberos keys while producers and consumers continue serving workloads throughout the change.

**Core principle:** the broker/identity provider must accept the new credential before clients switch; Spring Kafka clients must actually load the new credential; and the old credential must be revoked only after verifying that all workloads have migrated.

A common approach is **blue/green principal rotation**: create a new principal, grant exact ACLs, verify with a canary client, roll out instance by instance, observe traffic by principal, and then revoke the old principal. This provides a clear overlap window and rollback path.

## 1. Defining "Zero Downtime"

Zero downtime does not necessarily mean every TCP connection and consumer session stays unbroken. When credentials change, some clients may reconnect; consumer groups may rebalance; producers may need to establish new connections. What must be guaranteed is zero record loss and keeping the service within SLO.

| Workload | Objective |
|---|---|
| Consumer | Sufficient capacity, no skipped offsets, lag within SLO |
| Producer | Successful publishing, bounded retries |
| Transactional processor | No transactional.id collisions, clean commits |
| Kafka Streams | Internal topics and state stores remain accessible |
| Batch worker | Appropriate checkpointing/pause-resume |

If zero rebalances or connection resets are strictly required, verify the capabilities of the auth mechanism and client. Rolling restarts keep the workload serving, though brief rebalances still occur.

## 2. Why Changing a Password Directly Causes an Outage

Suppose all consumers share one username/password. If the broker changes the password before the application switches, existing connections may keep running briefly, while reconnects/restarts fail. If the application switches before the broker accepts the new credential, new clients fail as well.

Therefore, do not change one side before the other side is ready. You need credential overlap or a new principal.

## 3. Blue/Green Principals

~~~text
BLUE:  orders-reader-v1
GREEN: orders-reader-v2

Both are accepted concurrently by the broker during the overlap window.
V2 has equivalent least-privilege ACLs as V1.
~~~

~~~mermaid
flowchart TD
    A["Provision principal v2"] --> B["Copy least-privilege ACL"]
    B --> C["Test auth and workload operations"]
    C --> D["Roll out clients using v2"]
    D --> E["Observe all instances and jobs"]
    E --> F{"No client still uses v1?"}
    F -->|No| D
    F -->|Yes| G["Revoke v1"]
    G --> H["Verify v2-only operation"]
~~~

The benefit is being able to roll back to v1 prior to revocation, track which clients have migrated, and revoke independently. Do not grant broad permissions to v2 just to save time.

## 4. Inventory Before Rotation

List every place the credential is used:

- Kafka consumers, groups, topics, and replicas.
- Kafka producers, output topics, and transactional IDs.
- Custom KafkaTemplate/ProducerFactory/ConsumerFactory beans.
- KafkaAdmin/AdminClient.
- Kafka Streams, internal topics, and state stores.
- Scheduled jobs, CronJobs, and batch workers.
- Kafka Connect workers/connectors.
- CI/CD, migration, and smoke-test tools.
- Monitoring clients and health checks.
- Disaster recovery/standby clusters.

Record principals, secret references, and versions; do not record passwords/tokens in tickets or spreadsheets. Do not overlook nightly jobs or tools running outside Kubernetes.

## 5. Choosing a Strategy by Mechanism

| Mechanism | Credential | Common Overlap Approach |
|---|---|---|
| SASL/SCRAM | Username/password | New principal and parallel ACLs |
| SASL/PLAIN | Username/password | New user; always protect with TLS |
| OAuth/OAUTHBEARER | Client secret/key/token source | IdP accepts old/new credentials simultaneously |
| mTLS | Client certificate/private key | Trust both old and new CAs/certificates |
| Kerberos/GSSAPI | Keytab/key version/ticket | Coordinate KVNO, ticket renewal, and rollout |
| Cloud IAM | Workload identity/role | Provision new identity and trust/policy overlap |

Do not use the same runbook for SCRAM, OAuth, mTLS, and Kerberos. Verify broker, IdP, and Kafka client versions.

## 6. SASL/SCRAM

Kafka SCRAM stores a credential verifier per user/mechanism. Do not assume one principal can always hold two passwords concurrently. Blue/green principals are usually clearer:

~~~text
orders-reader-v1 -> READ orders.events; READ group orders-service
orders-reader-v2 -> READ orders.events; READ group orders-service
~~~

Create v2, grant least-privilege ACLs, authenticate, and run a consume test. Then shift clients via a rolling rollout. Delete v1 only once all consumers, producers, jobs, and tools have migrated.

Producer principals need WRITE on output topics. Transactional producers need permissions on transactional IDs. Consumers need group permissions in addition to topic permissions.

## 7. Spring Boot SCRAM Configuration

Example properties with secret-free placeholders:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka.internal:9093
    consumer:
      properties:
        security.protocol: SASL_SSL
        sasl.mechanism: SCRAM-SHA-512
        sasl.jaas.config: INJECTED_ORDERS_READER_V2_JAAS
    producer:
      properties:
        security.protocol: SASL_SSL
        sasl.mechanism: SCRAM-SHA-512
        sasl.jaas.config: INJECTED_ORDERS_WRITER_V2_JAAS
~~~

`INJECTED_*` values are illustrative placeholders only. Secrets must be supplied from a secret manager or approved deployment mechanism. If using custom factories, verify each factory receives the exact client-specific properties; do not edit application.yml and assume every client has switched.

## 8. OAuth/OAUTHBEARER

Distinguish the client secret used to fetch tokens, the access token presented to the broker, the refresh mechanism, and issuer/audience/scope. Rotation typically involves:

1. Create a new client secret/key at the IdP.
2. Allow old and new credentials to coexist if supported by the IdP.
3. Update the secret reference.
4. Verify the callback/login handler fetches new tokens.
5. Reconnect/recreate clients per Kafka client capabilities.
6. Confirm the broker accepts new tokens with the right scopes.
7. Monitor expiry and re-authentication.
8. Revoke the old secret after the entire fleet has migrated.

Do not log access tokens, refresh tokens, client secrets, or JWT claims. Log only secret version and failure category. Do not assume updating the secret store makes a running callback handler automatically switch configuration.

## 9. mTLS Certificate Rotation

A trust overlap procedure:

~~~text
Broker/client trust:
  CA_OLD trusted
  CA_NEW trusted

Client fleet:
  some use CERT_OLD
  rolling rollout to CERT_NEW

After verification:
  remove CA_OLD
~~~

Add the new CA to the truststore before clients use new certificates. Issue new certificates, verify principal mapping (DN/SAN) and ACLs, update keystores, roll out instance by instance, force reconnects to verify the new SSLContext, and only then remove the old CA.

Replacing files on disk does not guarantee existing Kafka client SSLContexts reload automatically. Many clients load SSL configuration at initialization; identify the refresh/recreate path. Never disable hostname verification or use trust-all to work around rotation errors.

## 10. Kerberos/GSSAPI

Verify client principal, keytab, broker SPN, realm, DNS, clock skew, ticket lifetime, KVNO, and renewal. Some systems support multiple key versions in a keytab for overlap, though details depend on the KDC and management tools.

Test:
- Broker service principal is properly updated.
- New clients log in using the new keytab.
- Ticket renewal works over long durations.
- Whether Kafka clients require re-login or recreation.
- Old keys are revoked only when no clients still need them.

Do not print keytabs, ticket caches, or JAAS secrets.

## 11. ACL Parity

The new principal needs exact permissions:

| Role | Resource | Permissions Typically Needed |
|---|---|---|
| Consumer | Topic | READ, DESCRIBE |
| Consumer | Group | READ |
| Producer | Topic | WRITE, sometimes DESCRIBE |
| Transactional producer | Transactional ID | WRITE/DESCRIBE per operation |
| Admin | Cluster/topic | Only required admin permissions |

Exact permissions depend on the broker authorizer, version, operations, and prefix ACLs. Check effective ACLs and deny policies. Do not grant superuser just to make health checks turn UP.

## 12. Spring Kafka Client Lifecycle

Spring Kafka creates KafkaConsumer/KafkaProducer via factories and listener containers. Credentials are typically read when clients are constructed. Updating a Kubernetes Secret does not guarantee existing clients swap credentials.

Components to inspect:
- DefaultKafkaConsumerFactory and consumer instances.
- DefaultKafkaProducerFactory and producer instances.
- KafkaTemplate and ProducerFactory.
- KafkaListenerEndpointRegistry/listener containers.
- KafkaAdmin/AdminClient.
- Custom interceptors, callback handlers, and SSLContexts.
- Transaction managers and producer caches.

Do not close raw KafkaConsumer/Producers from arbitrary threads. Use Spring lifecycle APIs or roll out new instances to swap clients safely.

## 13. Rolling Deployment for Consumer Groups

~~~text
A, B, C use credential v1

Roll A to v2 -> wait for Ready and assignment
Roll B to v2 -> wait for Ready and assignment
Roll C to v2 -> wait for Ready and assignment

Verify no v1 clients remain
Revoke v1
~~~

Rolling restarts can trigger rebalances. Mitigate impact with spare capacity, graceful shutdown, draining in-flight work, suitable maxUnavailable, and tracking rebalance duration/lag. Cooperative sticky assignment can reduce partition movement if the whole group supports it, though it does not eliminate all rebalances.

With a single consumer replica, a restart creates a window with no active consumer. Add capacity or use blue/green deployment if continuous workload processing is required.

## 14. Producer Rollout and Idempotence

Roll producers instance by instance, watching send success, reconnects, latency, retries, and producer errors. If idempotence is enabled, let the Kafka client manage producer identity/sequences per lifecycle; do not assume a new producer inherits old state.

For transactional producers, pay close attention to **transactional.id**. Two concurrent producers using the same ID can fence each other. Grant transactional ID permissions to the new principal before rollout, prevent two owners from using incompatible IDs simultaneously, and monitor ProducerFencedException/transaction aborts.

Do not change the transactional ID prefix at the same time as credential rotation unless necessary. If forced to change it, treat it as a separate transaction ownership change and test thoroughly.

## 15. Kafka Streams and Internal Resources

The new principal needs permissions for input/output topics, consumer group/application ID, repartition topics, changelog topics, transactional IDs, and Admin operations if the topology creates internal topics.

An application might read input successfully yet fail when writing changelogs or creating repartition topics. Test state restoration, processing, and transaction commits with the new principal. Avoid combining rotation with topology/application.id migrations to keep rollback simple.

## 16. Kubernetes Secret Rollout

Environment variables are typically read only at process startup. Mounted Secret volumes may update, yet the application/Kafka client will not reload automatically without a supporting mechanism. SSLContext may also retain previously loaded certificates.

A clean approach is updating the secret version/reference in the Pod template to create a new ReplicaSet and rolling update:

~~~yaml
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  template:
    spec:
      containers:
        - name: orders-service
          env:
            - name: KAFKA_CREDENTIAL_VERSION
              value: "v2"
~~~

This is an illustrative fragment only; secret values must still be injected via Secrets/secret managers. maxUnavailable=0 requires sufficient capacity and resource quotas for maxSurge.

## 17. Readiness Gates

A new pod should not become Ready just because the JVM started. Readiness must reflect real capability:

**Consumer:** new credentials loaded, authentication succeeded, joined group with accepted assignment state, and fetch/processing path works when data arrives.

**Producer:** authentication succeeded and can publish to required topics; if transactional, transaction lifecycle works.

A successful AdminClient describeCluster does not prove the producer has WRITE ACLs or the consumer has READ/group ACLs. For idle topics, do not necessarily wait for real business records; use appropriate assignment and capability checks. Do not publish synthetic messages to production topics without explicit design/cleanup.

Readiness failure usually marks a Pod NotReady; liveness failure can restart the process. When credential rotation fails, keep readiness DOWN if the dependency is mandatory, but do not fail liveness solely due to wrong broker/secret settings. Restart loops with the same config cannot fix credentials.

## 18. Capability-Based Health State

Maintain separate states for producer, consumer, and admin, including operation, last-success timestamp, and failure category. Do not use a single shared Kafka boolean if the application holds multiple roles.

State holder example:

~~~java
import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;

public class KafkaCapabilityState {

    public record Snapshot(
            boolean available,
            String capability,
            String failureKind,
            Instant lastSuccess) {
    }

    private final AtomicReference<Snapshot> current =
        new AtomicReference<>(
            new Snapshot(false, "not_verified", "unknown", null)
        );

    public void success(String capability) {
        current.set(new Snapshot(
            true, capability, "none", Instant.now()
        ));
    }

    public void failure(String capability, String kind) {
        Snapshot previous = current.get();
        current.set(new Snapshot(
            false, capability, kind, previous.lastSuccess()
        ));
    }

    public Snapshot snapshot() {
        return current.get();
    }
}
~~~

This is a state-based example and does not perform authentication itself. Integration code must update state after real operations and apply freshness thresholds so readiness does not flap. Never put credentials or raw exception messages into health details.

## 19. Cutover by Client Role

| Wave | Client | Verification |
|---|---|---|
| 0 | Admin/test client | New principal authenticates and ACLs are right |
| 1 | Producer canary | Send operation to test topic |
| 2 | Consumer canary | Join test group, fetch/process |
| 3 | Subset of production producers | Send success, latency |
| 4 | Subset of production consumers | Assignment, lag, processing |
| 5 | Remainder | Zero old clients left |
| 6 | Revoke old identity | v2-only operation succeeds |

Do not use the same production consumer group for an isolated canary if you do not want the canary receiving production partitions. Use a test topic/group or an explicit canary design.

## 20. Monitoring the Overlap Window

| Metric | Question |
|---|---|
| Auth success/failure by principal | Are new clients authenticating? |
| Connection/reconnect count | Is there a reconnect storm? |
| Group membership/assignment | Is consumer capacity sufficient? |
| Rebalance count/duration | How much churn did rollout cause? |
| Consumer lag | Is the workload disrupted? |
| Producer send success | Can the new principal write? |
| Transaction abort/fencing | Any identity/ownership issues? |
| Retry/DLT backlog | Are errors routing to recovery paths? |
| Readiness | Are pods Ready only after capability checks? |
| Old principal last seen | Are any workloads still using v1? |

Do not look only at Deployment rollout completion. Nightly scheduled jobs, connectors, or DR environments might only reconnect after the old credential is revoked.

## 21. Rollback Criteria

Define rollback thresholds upfront:

- Authentication failures rising on the new principal.
- Producer send errors exceeding SLO.
- Consumer group losing assignments longer than allowed.
- Lag exceeding business thresholds.
- Unusual spikes in transaction fencing/aborts.
- Readiness failing to recover.
- An uninventoried client still depending on v1.

If v1 remains safe and valid, roll instances back to v1 prior to revocation. Never revoke v1 during the rollback window. If v1 was compromised, do not keep it for rollback; use a third identity or emergency rotation.

## 22. Criteria to Revoke the Old Credential

Revoke v1 only with evidence that:
1. All production pods use v2.
2. Scheduled/batch jobs have migrated.
3. Connect, Streams, admin tools, and DR have been checked.
4. No auth activity from v1 appears over a window long enough to cover periodic workloads.
5. v2 producer/consumer/transaction operations are stable.
6. New ACLs are verified.
7. The rollback window has ended or an alternative identity path exists.
8. Security owner approves if required by process.

Do not rely solely on the current Deployment. A process outside Kubernetes may still use the old credential.

## 23. Emergency Rotation on Credential Compromise

Routine rotation prioritizes overlap. When a credential is compromised, prioritize shrinking the attacker's window to abuse the secret; brief disruption may be accepted per incident policy.

1. Identify the principal/secret and client scope.
2. Create a new identity or secure credential.
3. Grant least-privilege ACLs.
4. Deploy new clients ordered by blast radius.
5. Revoke the compromised credential per incident commander decision.
6. Monitor auth attempts from the old identity.
7. Inspect broker audit logs.
8. Verify workloads use the new identity.
9. Rotate related credentials that might also be exposed.
10. Document the incident and preventive actions.

Do not extend overlap just to preserve availability while an attacker is actively using the old secret.

## 24. Safe Logging and Metrics

Illustrative structured log:

~~~text
event=kafka_credential_rotation
service=orders-service
client_type=consumer
principal=orders-reader-v2
credential_version=secret-v2
phase=canary
authentication=success
group_assignment=ready
~~~

Never log passwords, tokens, refresh tokens, full JAAS configs, private keys, keytabs, or keystore passwords.

Suggested metrics: rotation phase, auth success/failure, reconnect count, assignment count, consumer lag, producer send failures, transaction aborts, readiness state, and old credential last-seen. These are custom metrics; principal labels must have low cardinality and comply with policy.

## 25. Integration Tests for Credential Rotation

Use a broker with real authentication/ACLs or an equivalent test environment:

1. Create v1/v2 principals and least-privilege ACLs for both.
2. Start producers/consumers using v1 and verify operations.
3. Start a canary client using v2.
4. Verify authentication, authorization, and real produce/consume.
5. Roll each consumer instance to v2.
6. Check group assignment, lag, and rebalances.
7. Roll producers to v2 and check acknowledgements.
8. Check transaction commit/fencing if applicable.
9. Confirm zero clients still use v1.
10. Revoke v1 and force/retry reconnect of v2 clients.
11. Verify v2-only operations continue.
12. Test rollback prior to revoking v1.
13. Test emergency revocation separately if required by threat model.

Do not test only the handshake; test topic/group/transaction permissions. Test broker images might not fully support SCRAM/OAuth/Kerberos/ACLs, so document limitations explicitly.

## 26. Integration Tests for TLS and OAuth

**mTLS:**
- Trust both old and new CAs during overlap.
- Start clients with the old certificate.
- Switch canary to the new certificate.
- Force reconnects to verify the new SSLContext.
- Roll out fleet.
- Remove the old CA.
- Reconnect all clients and verify only the new cert is accepted.
- Test expired/unknown CAs and ensure private keys are never logged.

**OAuth:**
- Issue tokens using the old client credential.
- Provision new credential and overlap at the IdP.
- Verify callback fetches new tokens.
- Verify broker accepts tokens and claims.
- Test refresh before/after expiry.
- Revoke old credential.
- Verify clients no longer depend on the old secret.
- Test wrong issuer/audience/scope and ensure tokens are never leaked.

A mock callback returning a token does not prove the broker SASL/OAUTHBEARER handshake works; integrate against an appropriate IdP/broker.

## 27. Routine Rotation Runbook

**Preparation**
1. Inventory all clients/principals/secret references.
2. Identify mechanism and client lifecycle.
3. Lock down SLOs, overlap duration, and rollback window.
4. Provision new identity.
5. Grant equivalent least-privilege ACLs.
6. Test the new principal.
7. Prepare secret versions, deployments, and dashboards.

**Canary/rollout**
8. Switch producer/consumer canaries.
9. Verify authentication, ACLs, and real operations.
10. Roll out instance by instance per readiness/capacity.
11. Monitor assignment, lag, send errors, and transactions.
12. Verify jobs/connectors/admin/DR.
13. Halt rollout if rollback thresholds are breached.

**Completion**
14. Verify no clients still use v1.
15. Hold overlap long enough to cover periodic jobs.
16. Revoke old credentials/ACLs.
17. Verify v2-only after reconnects.
18. Monitor business SLOs and auth failures.
19. Record credential version and outcome.

## 28. Runbook When Rotation Causes Errors

1. Halt further rollout.
2. Classify as AuthN, AuthZ, TLS, OAuth, Kerberos, or network.
3. Check secret version/mount and whether clients use the updated config.
4. Check security.protocol, mechanism, and broker listener.
5. Check principal mapping and topic/group/transactional ID ACLs.
6. Check SSLContext/callback refresh/recreation.
7. If v1 is still safe, roll canaries/instances back to v1.
8. Do not revoke v1 during the rollback window.
9. If v1 is compromised, switch to a third identity per incident plan.
10. Re-run canary operations before resuming.
11. Document root cause and preventive actions.

Never grant superuser or disable hostname verification as a temporary workaround.

## 29. Anti-Patterns

- Changing the password on the broker before clients migrate.
- Updating Secrets while assuming Kafka clients reload automatically.
- Revoking v1 before rollout finishes.
- Missing CronJobs, connectors, DR, and admin tools.
- Omitting group/transactional ID ACLs for the new principal.
- Restarting the entire fleet simultaneously.
- Running two transactional producers with the same transactional.id.
- Testing only the SASL handshake without testing operations.
- Using describeCluster as consumer readiness.
- Skipping checks on OAuth refresh or Kerberos renewal.
- Not waiting for stop/recreate lifecycle completion.
- Having no rollback window.
- Keeping a compromised credential alive too long just to prioritize zero downtime.

## 30. Checklist Before Revoking the Old Credential

- [ ] New principal authenticates against the right broker listener.
- [ ] ACLs are right for topics, groups, and transactional IDs.
- [ ] Producer clients migrated with stable send success.
- [ ] Consumer clients migrated with stable assignments.
- [ ] Kafka Streams/internal topics verified.
- [ ] KafkaAdmin, connectors, jobs, tools, and DR migrated.
- [ ] OAuth refresh/Kerberos renewal working.
- [ ] New TLS certs used after reconnects.
- [ ] Zero old principal activity across the overlap window.
- [ ] Consumer lag and business SLOs normal.
- [ ] Transaction fencing/aborts not rising.
- [ ] Rollback window closed or alternative identity ready.
- [ ] Security owner approved revocation if required.
- [ ] Audit record captured for revocation timestamp.

## 31. Conclusion

**Zero-downtime credential rotation** requires the broker or identity provider to accept the new credential before clients migrate, while the old credential remains valid long enough for rollout and rollback. With SASL/SCRAM, blue/green principals usually give clean overlap; with mTLS, prepare new CA trust before rolling certificates; with OAuth/Kerberos, govern token/ticket renewal and client lifecycle.

In Spring Kafka, updating a Secret does not automatically swap credentials on running KafkaConsumer, KafkaProducer, KafkaAdmin, or SSLContext instances. Identify the exact client lifecycle, roll out in waves per readiness/capacity, verify **both authentication and authorization with real operations**, and only then revoke the old identity.

Throughout the process, monitor consumer group rebalances, lag, in-flight records, transaction aborts/fencing, and idempotency. When a credential is compromised, prioritize revocation per incident policy instead of extending overlap to preserve availability. Rotation is complete only when **all workloads use the new credential, zero old credential dependencies remain, and business processing still meets SLO**.
