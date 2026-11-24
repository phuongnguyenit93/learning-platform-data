# Runbook for Authentication Failures in Spring Kafka Operations

## 1. Objective and Scope

This runbook guides operations teams in handling incidents where a Spring Boot application using Spring Kafka cannot authenticate with Kafka brokers. The objective is to identify the exact failing layer, restore connectivity in a controlled manner, preserve evidence for investigation, and avoid exposing credentials during response.

In Kafka, distinguish three layers:

1. **Transport and TLS:** whether the client can establish a connection and verify the broker's certificate.
2. **Authentication:** whether the broker can verify the client's identity via SASL or mTLS.
3. **Authorization:** whether the authenticated principal is permitted to perform operations on the topic, consumer group, or Kafka resource.

Several errors appear close together in logs yet require different remediation. For instance, **SaslAuthenticationException** typically indicates a SASL authentication failure; **SSLHandshakeException** occurs at the TLS layer; **TopicAuthorizationException** or **GroupAuthorizationException** usually indicate the principal was authenticated but lacks permissions. Do not rotate passwords or grant extra ACLs before identifying the exact failing layer.

This runbook covers common configurations:

- **SASL_SSL:** TLS encrypts the connection and SASL authenticates the principal.
- **SASL_PLAINTEXT:** SASL without TLS encryption; used only when architecture and policy allow, not a typical production choice.
- **SSL:** TLS verifies the broker, and optionally uses mTLS to verify the client.
- OAuth/OAUTHBEARER, SCRAM, or PLAIN depending on the mechanisms supported by the Kafka cluster.

## 2. Incident Detection and Classification

### 2.1. Common Symptoms

| Log symptom or sign | Suspected layer | Meaning and first investigation direction |
|---|---|---|
| SaslAuthenticationException | SASL authentication | Check SASL mechanism, principal, credentials, or token |
| Authentication failed / Invalid username or password | SASL authentication | Verify secret version, principal status, and credentials on broker |
| SSLHandshakeException | TLS | Check truststore, certificate, hostname, expiration, and mTLS requirements |
| PKIX path building failed | TLS trust | Client cannot build a trusted CA chain |
| No subject alternative DNS name matching | TLS hostname | Target connection hostname does not match certificate SAN |
| Unexpected Kafka request of type ... during SASL handshake | Protocol/listener | Client and listener may be using incompatible security protocols |
| Unsupported SASL mechanism | SASL mechanism | Mechanism requested by client is not enabled or mismatched on listener/broker |
| TopicAuthorizationException | Authorization | Principal lacks permissions on the topic or corresponding operation |
| GroupAuthorizationException | Authorization | Principal lacks permissions for the consumer group |
| Consumer repeatedly rejoins or producer retries after credential change | Connection/client lifecycle | Some instances may still hold old credentials or old clients |

Spring Kafka logs often wrap the root error inside multiple exceptions such as KafkaException, ListenerExecutionFailedException, or consumer startup errors. Trace the `Caused by` chain down to the deepest exception and record the broker, client ID, timestamp, and failing operation. Do not conclude based solely on the first log line.

### 2.2. Distinguishing Authentication from Authorization

Authentication answers "who is the client?". Authorization answers "what is this principal allowed to do?". A client can authenticate successfully yet still be denied reading a topic, writing to a topic, or joining a consumer group.

| Outcome | Action needed |
|---|---|
| TLS handshake fails | Investigate certificates, trust, and hostname first |
| TLS succeeds, SASL fails | Investigate SASL mechanism, JAAS, credentials, or tokens |
| SASL succeeds, request rejected due to ACLs | Check principal and minimum required ACLs |
| CLI works while application fails | Compare configuration, secret version, runtime, and client properties of the app |
| Only some pods fail | Compare images, secret versions, rollout timing, and individual pod states |

### 2.3. Determine Impact Scope

Before changing configuration, determine:

- Whether the incident affects one application, a group of pods, one broker listener, or the entire cluster.
- Whether only producers, only consumers, Kafka Admin, or all clients are failing.
- Whether one principal or multiple principals are affected.
- Whether errors began after a deployment, secret rotation, certificate change, ACL change, broker upgrade, or network change.
- Whether the incident causes data loss, rising lag, increased retries, filling internal queues, or SLA impact.

Record the start time, detection time, environment, namespace, deployment, pod, client ID, principal (if logs permit), bootstrap endpoint, connected broker, and correlation/request ID if available. Never paste passwords, tokens, private keys, or full JAAS strings into tickets.

## 3. Initial Response Procedure

### Step 1 — Open Incident and Preserve Evidence

Create or update the incident per on-call procedures. Record the responder, timestamps, scope, affected services, and recent changes. Collect logs covering the error window from the application and brokers if access is permitted.

When collecting logs:

- Bound the time range and workloads inspected.
- Check whether logs accidentally contain usernames, passwords, tokens, JAAS configs, or sensitive data before sharing.
- Do not enable cluster-wide debug logging for Kafka or TLS unless necessary.
- If elevating log levels is required, enable it only at narrow scope and for a short duration; record start and stop times.
- Protect incident logs according to organizational access and retention policies.

### Step 2 — Check Application Health

Determine whether the application is running steadily or crashing/restarting. Check readiness/liveness, restart counts, deployment revisions, image versions, and pod creation times.

For Kubernetes, the following commands inspect metadata and logs without reading Secret values:

~~~bash
kubectl get pods -n <namespace> -l app=<application> -o wide
kubectl describe pod -n <namespace> <pod-name>
kubectl logs -n <namespace> <pod-name> --since=15m
kubectl logs -n <namespace> <pod-name> --previous
~~~

`kubectl describe pod` may display events and Secret references; review output before sharing externally. Application logs must also be checked to ensure they contain no credentials.

Compare failing pods against healthy pods if only a subset of replicas is affected. Verify whether the rollout completed, whether pods use the expected image and config, whether secret volumes are mounted, and whether the service account has permission to read the secret source.

### Step 3 — Check Network and TLS

Verify DNS, routes, firewalls, and listener ports from the actual environment running the application. With SASL_SSL, the TLS handshake occurs before SASL authentication. If TLS is not succeeding, investigating SASL at this step will not help.

Check these points:

1. Bootstrap hostname resolves to the expected address and the listener port is reachable.
2. Broker certificate is unexpired, its chain is trusted, and its SAN includes the hostname used by the client.
3. Client uses the right truststore and the truststore contains the current CA.
4. If mTLS is enabled, the client has an appropriate certificate and private key; the broker trusts the CA that issued the client certificate.
5. After bootstrap, hostnames in each broker's advertised listeners must also be valid against the certificate.

You can use OpenSSL to test the handshake from a host with the tool installed:

~~~bash
openssl s_client -connect broker.example.com:9093 -servername broker.example.com -showcerts -verify_return_error
~~~

OpenSSL output tests only the TLS path from the machine running the command. It does not verify the application's custom truststore, JAAS, SASL, or JVM configuration. Never disable hostname verification or use trust-all just to make a test pass.

### Step 4 — Verify Protocol and SASL Mechanism

Compare client configuration against the listener the bootstrap endpoint points to. Check at minimum:

- `security.protocol`: `SASL_SSL`, `SASL_PLAINTEXT`, `SSL`, or `PLAINTEXT`.
- `sasl.mechanism`: for example `SCRAM-SHA-512`, `SCRAM-SHA-256`, `PLAIN`, or `OAUTHBEARER`.
- JAAS login module matching the mechanism.
- Broker listener has the corresponding mechanism enabled.
- If multiple listeners exist, `listener.security.protocol.map` and advertised listeners map correctly.

A client using `SASL_SSL` cannot connect properly to a listener that only accepts `SSL` or `SASL_PLAINTEXT`. Similarly, `SCRAM-SHA-512` on the client must be supported by the cluster and the principal must have matching SCRAM credentials. Do not test random mechanisms in production; verify the approved listener and deployment configurations.

### Step 5 — Check Credential Provisioning

Inspect metadata and provisioning status:

- Does the Secret exist in the right namespace or secret manager?
- Does the workload reference the correct secret name and key?
- Does the service account or workload identity have permission to read the secret?
- Does the rolled-out secret version or revision match the approved version?
- Is the value missing, empty, containing an unintended trailing newline, or altered by templating/escaping?
- Are any pods still running with an old secret because they were not restarted or have not reloaded configuration?

Never use `kubectl get secret -o yaml`, `printenv`, `env`, `set`, debug dumps, or similar commands to print sensitive data into terminals or logs. If you need to verify variables are populated without reading their values, check variable presence inside the container:

~~~bash
kubectl exec -n <namespace> <pod-name> -- sh -c 'test -n "$KAFKA_USERNAME" && test -n "$KAFKA_PASSWORD" && echo "Kafka credential variables are present"'
~~~

The command above only checks whether the two variables are non-empty. It does not prove the credentials are valid or the principal is active. For file-mounted secrets, verify file existence, permissions, and metadata such as modification timestamp; never print private key contents or keystore passwords.

### Step 6 — Verify Principal and Authentication Mechanism

Once TLS and protocol are confirmed correct, verify the principal against the mechanism in use:

- **SCRAM:** username must point to an existing principal; SCRAM credentials must be provisioned on the target cluster. Check whether a rotation created a new principal/credential while the workload still uses the old credential.
- **PLAIN:** username/password must match the broker's authentication store. Use only over TLS in environments requiring credential protection in transit.
- **OAuth/OAUTHBEARER:** check token expiration, issuer, audience, required scopes/claims, clock skew, reachability of the token endpoint, and JWKS/introspection endpoints per design.
- **mTLS:** check the client certificate presented, chain, and CA trusted by the broker; verify principal mapping if brokers derive the principal from the certificate.

If multiple clients sharing the same principal fail simultaneously, prioritize checking changes on the broker, credential store, or listener. If only one deployment fails after a rollout, prioritize checking secret references, config binding, and that deployment's image version.

### Step 7 — Distinguish ACL Errors

If authentication succeeds but operations are rejected, check ACLs for the exact principal, topic, and consumer group. Producers may need write permission on the topic; consumers may need read permission on the topic and appropriate permissions on the group; Admin clients may need additional permissions depending on admin commands.

Never grant `*` or cluster-wide admin permissions just to clear errors. Permission requests must specify the principal, resource, operation, and business justification. If principal mapping changed, old ACLs may no longer match even though certificates or SASL credentials remain valid.

## 4. Troubleshooting Branches by Authentication Mechanism

### 4.1. SCRAM

Typical symptoms are `SaslAuthenticationException` or brokers logging failed SCRAM authentication. Check:

1. Client and listener both use the exact same SCRAM mechanism.
2. JAAS login module is `org.apache.kafka.common.security.scram.ScramLoginModule`.
3. Username resolves from the correct secret source.
4. Principal exists on the cluster and credentials were created for the matching SCRAM mechanism.
5. After rotation, all instances received the new secret version and recreated their Kafka clients.
6. Old credentials were not revoked before workloads finished transitioning to the new credentials.

Example Spring Boot configuration (placeholders only):

~~~yaml
spring:
  kafka:
    properties:
      "[security.protocol]": SASL_SSL
      "[sasl.mechanism]": SCRAM-SHA-512
      "[sasl.jaas.config]": >-
        org.apache.kafka.common.security.scram.ScramLoginModule required
        username="${KAFKA_USERNAME}"
        password="${KAFKA_PASSWORD}";
~~~

Do not log `sasl.jaas.config`. If credentials must be replaced, prefer creating a new principal with least privilege, deploying and verifying all instances, and only then revoking the old principal when your platform supports that workflow.

### 4.2. PLAIN

PLAIN transmits credentials inside the SASL payload; this mechanism does not encrypt passwords on its own. If the application uses PLAIN, verify the listener uses `SASL_SSL` and the TLS handshake succeeds before inspecting credentials. Check username/password, the broker authentication store, and credential update timestamps.

If PLAIN is discovered running over an unencrypted connection in production, record it as a security configuration issue to resolve through change management. Do not unilaterally alter listeners during an incident without assessing impact on other clients.

### 4.3. OAuth/OAUTHBEARER

When tokens are rejected, check these cause categories:

- Token is expired or not yet valid.
- Clocks on the application, broker, or identity provider have drifted significantly.
- Issuer or audience does not match broker configuration.
- Claims, scopes, or roles do not satisfy policy.
- Token endpoint, JWKS endpoint, or introspection endpoint is unreachable.
- Client secret used to obtain tokens is wrong, expired, or revoked.
- Refresh mechanism is not running, or the token callback returns a stale token or fails to update credentials.

Do not log tokens for comparison. Use non-sensitive metadata such as `exp`, `iss`, `aud`, key ID, and request ID if allowed by policy, while ensuring extracted claims do not expose personal data or unnecessary internal details. If the token endpoint fails, distinguish network errors, client authentication errors, and identity provider policy errors.

When tokens are short-lived, check refresh intervals and each Kafka client's ability to fetch new tokens. If a custom callback or provider fails, inspect provider exceptions and metrics without dumping tokens.

### 4.4. TLS Client Authentication (mTLS)

If the broker requires mTLS, the client must present a valid certificate. Check the mounted certificate, matching private key, keystore password/alias, certificate chain, expiration, Key Usage/Extended Key Usage, and CA trusted by the broker.

Check principal mapping on the broker if identity is derived from the certificate subject or SAN. A TLS-valid certificate can still map to a different principal than the one granted ACLs. In that case, operation failures may be authorization rather than handshake errors.

Do not rotate client certificates en masse before confirming the broker trusts the new CA. When changing CAs, roll out trust for the new CA during a transition phase before switching client certificates.

## 5. Verification Using Kafka CLI

Kafka CLI can isolate application bugs from broker or credential issues. Run only from an authorized environment using a client config file provisioned via a secret store or restricted-access mount.

Example placeholder client config file (never put real credentials in documentation or tickets):

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="${KAFKA_USERNAME}" password="${KAFKA_PASSWORD}";
ssl.truststore.location=/etc/kafka/tls/truststore.p12
ssl.truststore.type=PKCS12
ssl.truststore.password=<injected-at-runtime>
ssl.endpoint.identification.algorithm=https
~~~

In a real environment, the file must be generated or mounted via secret management; placeholders here are not valid runtime values. Restrict file read permissions and remove temporary files per policy after use. Avoid passing passwords as command-line arguments because they can leak via process lists, shell history, or logs.

You can test broker APIs and connectivity:

~~~bash
kafka-broker-api-versions.sh --bootstrap-server broker.example.com:9093 --command-config /run/secrets/kafka/client.properties
~~~

If you need to test producer/consumer paths, use the same protected config file:

~~~bash
kafka-console-producer.sh --bootstrap-server broker.example.com:9093 --producer.config /run/secrets/kafka/client.properties --topic <test-topic>
kafka-console-consumer.sh --bootstrap-server broker.example.com:9093 --consumer.config /run/secrets/kafka/client.properties --topic <test-topic> --group <test-group> --from-beginning
~~~

Use only approved test topics and groups. Producer commands write real data; consumer commands can create groups or affect offsets depending on flags. Never run against production topics or active application groups without assessing impact.

If the CLI succeeds while Spring Kafka fails, compare:

- The CLI config file vs. actual Kafka client properties in the application.
- Secret version, service account, mount path, and file read permissions.
- Java runtime, default truststore, hostname, and DNS inside the container.
- `security.protocol`, SASL mechanism, JAAS login module, and endpoints.
- Client ID, principal mapping, and ACLs.
- When the client was created relative to when the secret was rotated.

If both the CLI and application fail, focus investigation on broker listeners, credential stores, identity providers, CAs, or shared infrastructure changes.

## 6. Controlled Service Recovery

### 6.1. Choose Action by Confirmed Cause

| Confirmed cause | Recovery action |
|---|---|
| Wrong or missing secret reference | Fix reference to the approved secret version, roll out workload, and verify |
| Credential expired or revoked | Provision new credential, update secret store, roll out clients, and retire old credential per plan |
| Wrong SASL mechanism or protocol | Restore approved listener/client configuration through change process |
| Invalid certificate or CA | Issue/update certificate or truststore per PKI process, then reload/restart required clients |
| OAuth token endpoint or issuer failure | Restore token issuance flow or identity provider config; verify new tokens |
| Missing ACL | Grant exact permissions for principal and resource after validating request |
| Some pods still hold old clients | Perform controlled rollout to recreate clients and verify each replica |

### 6.2. Deploying New Credentials or Configurations

Before rollout:

1. Confirm the new secret version or configuration has been created and approved.
2. Check access permissions to the secret source and mounted files.
3. Verify how your Spring Boot and Kafka client versions reload configuration.
4. Prepare rollout order, success criteria, and how to revert to the prior version if still valid.
5. Ensure brokers or the identity provider accept the new credentials throughout the transition period.

After rollout:

1. Verify new pods are Ready and running the right image/config revision.
2. Confirm logs show no further TLS/SASL authentication errors.
3. Confirm the producer can send a test message to an approved resource.
4. Confirm the consumer can read the test message and the group operates normally.
5. Monitor retries, consumer lag, rebalances, throughput, and error rates.
6. Verify all replicas have switched to the new secret version before revoking old credentials.

Do not assume updating a Secret file makes a running Kafka client automatically reload credentials. Depending on configuration, Spring Boot may read properties only during bean initialization; the Kafka client may retain previously instantiated JAAS login modules or SSL contexts. Unless a tested reload mechanism exists, use a rolling restart or recreate beans/clients per deployment procedures.

### 6.3. Rollback

Rollback is safe only if old credentials or certificates are still valid and have not been revoked. Before rolling back:

- Check whether the old credential is still accepted by the broker or identity provider.
- Check whether the old CA is still in the truststore and unrevoked.
- Check whether ACLs for the old principal remain accurate and not overly permissive.
- Confirm rollback does not reintroduce a compromised secret into the system.
- Record config version, secret reference, and rollback timestamp.

If an old credential was revoked due to suspected exposure, never restore it just to shorten outage duration. Finish provisioning new credentials or use an approved contingency plan.

## 7. Incident Resolution Verification Criteria

Close the incident only after conditions matching the incident scope are met:

- TLS handshakes succeed from affected workloads with hostname verification still enabled.
- SASL or mTLS authentication succeeds with the expected principal.
- Producers/consumers can execute their authorized operations.
- No abnormal spike in authentication/authorization errors occurs during the observation window.
- All replicas use the proper secret/certificate/config revision.
- Consumer lag and retries return to acceptable operational thresholds; no continuously growing backlog remains.
- Old credentials are retired as planned if rotation was part of remediation.
- Logs and metrics do not leak secrets; temporary debug logging has been turned off.

For consumers, check both the consumer group and offsets/lag. A consumer may authenticate successfully yet fail to read data due to missing ACLs, or rebalance continuously for another reason. For producers, verify acknowledgments and write outcomes per configured delivery semantics; do not rely solely on an open socket.

## 8. When to Escalate Incident Severity

Escalate or engage the appropriate owning teams when:

- Multiple applications or multiple principals fail to authenticate simultaneously.
- Broker listeners, CAs, secret managers, or identity providers show widespread failures.
- Credentials are exposed, misused, or show anomalous access.
- Rotation disrupts multiple workloads or it is unclear which credentials remain active.
- There is risk of data loss, SLA breach, consumer lag exceeding thresholds, or prolonged producer write outage.
- Broad changes are needed to listeners, broker configurations, CA trust, or policies.

Coordination points typically include the Kafka/platform team, identity or PKI management team, application team, and security team per organizational workflow. When handing off, provide timestamps, scope, broker/listener, client ID, shareable principal, root exception, recent changes, and steps taken. Never send credentials, tokens, or private keys over incident channels.

## 9. Incident Record Template

Use the following template to document the response:

~~~text
Incident ID:
Environment / Namespace:
Application / Deployment:
Affected pods:
First observed at (UTC):
Last known good time:
Kafka bootstrap endpoint / listener:
Client ID:
Authentication mechanism:
Principal (if permitted):
Observed exception / root cause:
Affected operations: produce / consume / admin
Scope: one pod / one application / multiple applications / cluster-wide
Recent changes: deploy / secret rotation / certificate / ACL / broker / network
Evidence references: application logs / broker logs / metrics / audit events
Confirmed cause:
Recovery action:
Validation results:
Credential or certificate retired:
Follow-up owner:
Incident closed at:
~~~

Record only necessary metadata. Never put passwords, tokens, JAAS strings, private keys, or Secret contents into the template.

## 10. Preventing Recurrence

After the incident, determine why detection was delayed or why recovery was difficult. Effective measures typically include:

- Separate metrics and alerts for TLS handshake failures, SASL authentication failures, and authorization failures.
- Track connection failure rates by client ID, principal, listener, and broker; avoid putting secrets in metric labels.
- Alert ahead of credential/certificate expiration with enough lead time for renewal and rollout.
- Automate checks for secret references, read permissions, and certificate metadata in pipelines without printing secret values.
- Standardize Kafka client configurations so producers, consumers, and admins share consistent security policies.
- Test rotations in staging using the exact same secret delivery and Kafka client lifecycle mechanisms as production.
- Maintain backup credentials or approved re-issuance procedures; do not share principals across multiple applications.
- Practice runbooks periodically, including OAuth provider outages, CA rotations, and emergency credential revocations.
- Audit ACLs by owner and actual need, removing redundant permissions after application changes.

A useful runbook needs an owner, version, review date, links to dashboards, and internal escalation paths. Update documentation after every incident or Kafka architecture change so steps reflect the active listeners, SASL mechanisms, secret sources, and tools in production.

## 11. Core Response Principle

When authentication fails, pinpoint the exact failing stage: TLS, SASL/mTLS, or authorization. Gather evidence safely, compare configurations and secret versions, and recover through small, verifiable changes. Never print credentials to logs, disable certificate verification, grant broad ACLs to mask errors, or revoke old credentials before clients have migrated to new ones unless responding to a secret compromise. The service is considered recovered only when workloads resume required Kafka operations and operational metrics stabilize.
