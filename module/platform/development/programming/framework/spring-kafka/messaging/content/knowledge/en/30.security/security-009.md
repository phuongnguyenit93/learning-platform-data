# Consumer ACL Authorization

Kafka ACLs (Access Control Lists) restrict which principal is allowed to perform which operations on Kafka resources. For a Spring Kafka consumer, the required permissions typically consist of `READ` on the subscribed topic and `READ` on the consumer group the consumer joins. Granting permissions on just these two scopes lets the consumer read data and commit offsets without needing cluster admin privileges.

ACLs only take effect when the broker has enabled an authorizer and the client authenticates as a principal. Spring Kafka configures the connection and listener; permission enforcement is performed by the Kafka broker.

## 1. Distinguishing Authentication and Authorization

These two steps answer different questions:

- **Authentication:** who is the client? For example, SASL/SCRAM verifies username and password, while TLS client authentication can derive the principal from a certificate.
- **Authorization:** what can that principal do? The Kafka authorizer evaluates ACLs on the topic, group, or other resources before allowing the request.

For example, a Spring Boot consumer logs in using SASL/SCRAM with username `orders-consumer`. The broker authenticates the client and maps that identity to principal `User:orders-consumer`. ACLs are created for this principal. `group.id=orders-service` is the consumer group name, not a username or principal.

If a client uses a TLS certificate or a custom principal builder, the principal name seen by the broker may differ from the username in application config. Check the actual principal in broker logs before creating ACLs.

## 2. Components of an ACL

An ACL specifies a principal, permission, operation, resource, and optionally a host:

| Component | Meaning | Consumer Example |
| --- | --- | --- |
| Principal | Identity authenticated by the broker | `User:orders-consumer` |
| Resource type | Type of protected resource | `Topic`, `Group` |
| Resource name | Name of the resource | `orders`, `orders-service` |
| Operation | Permitted action | `READ` |
| Permission | Allow or deny | `ALLOW` |
| Host | Client host permitted to connect | `*` or restricted IP address |

For a standard consumer, grant `READ` on every topic the listener reads and `READ` on the actual group ID. `READ` on a topic also implies `DESCRIBE` according to Kafka ACL permission hierarchy. If an operations tool needs to describe consumer groups, `DESCRIBE` on the group can be granted to a separate operations principal.

## 3. Granting Least-Privilege Permissions for Consumers

Suppose the application uses principal `User:orders-consumer`, subscribes to topic `orders`, and configures `group.id=orders-service`. Use a separate admin principal to create ACLs:

```bash
kafka-acls.sh \
  --bootstrap-server kafka.example.com:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:orders-consumer \
  --operation Read \
  --topic orders

kafka-acls.sh \
  --bootstrap-server kafka.example.com:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:orders-consumer \
  --operation Read \
  --group orders-service
```

The first command permits reading the topic; the second lets the consumer join the group and manage offsets for that group. If the consumer subscribes to multiple topics, grant `READ` for each topic or use a tightly controlled resource pattern.

Do not grant `ALL` on the cluster or `CREATE` on topics to a consumer whose only job is reading. If the application needs topics created, use a separate provisioning/admin principal or a deployment process that creates topics before the consumer runs.

## 4. Resource Patterns for Multiple Topics or Groups

Kafka ACLs support `LITERAL` and `PREFIXED` resource patterns. Use prefixes when resources follow a stable naming convention, such as topics `orders.created`, `orders.updated` and groups `orders-service-blue`, `orders-service-green`.

```bash
# Allow reading all topics starting with orders.
kafka-acls.sh \
  --bootstrap-server kafka.example.com:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:orders-consumer \
  --operation Read \
  --topic orders. \
  --resource-pattern-type prefixed

# Allow joining groups starting with orders-service-.
kafka-acls.sh \
  --bootstrap-server kafka.example.com:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:orders-consumer \
  --operation Read \
  --group orders-service- \
  --resource-pattern-type prefixed
```

A prefix ACL opens access to every resource with that prefix, including resources created in the future. Use it only when all topics/groups under the prefix share the same trust boundary. If different tenants have separate data or access rights, prefer literal ACLs or narrow tenant-specific prefixes.

## 5. Configuring Authentication in Spring Boot

ACLs are not declared inside `@KafkaListener`; the listener only selects topics and groups. The client must connect using credentials matching the principal granted ACLs. The example below uses SASL/SCRAM over TLS:

```properties
spring.kafka.bootstrap-servers=kafka.example.com:9093
spring.kafka.consumer.group-id=orders-service
spring.kafka.consumer.properties[security.protocol]=SASL_SSL
spring.kafka.consumer.properties[sasl.mechanism]=SCRAM-SHA-512
spring.kafka.consumer.properties[sasl.jaas.config]=org.apache.kafka.common.security.scram.ScramLoginModule required username="${KAFKA_USERNAME}" password="${KAFKA_PASSWORD}";
```

Set `KAFKA_USERNAME=orders-consumer` and supply the password via a secret manager or runtime environment variable. Never commit passwords, JAAS secrets, or private keys to Git. For a private CA, configure truststore/SSL according to the cluster's infrastructure.

`SASL_SSL` both encrypts the transport channel and authenticates the client with SASL. `SASL_PLAINTEXT` does not encrypt network data; never use it over untrusted networks. The SASL mechanism must match the broker, such as `SCRAM-SHA-512`, `PLAIN`, or `OAUTHBEARER`.

When using multiple Kafka clients in the same application, remember to configure producer, consumer, and `KafkaAdmin` according to their own principals and needs. Properties under `spring.kafka.consumer.properties` apply only to consumers. Do not assume consumer credentials can create topics or send messages.

## 6. Permissions for Related Tasks

A consumer that only reads topics and joins a group does not normally need cluster admin privileges. Other tasks require dedicated ACLs:

| Task | Commonly Needed Resource / Operation |
| --- | --- |
| Consume topic | `READ` on `Topic` and `READ` on `Group` |
| View consumer group info via ops tools | `DESCRIBE` on `Group` for an operations principal |
| Publish records | `WRITE` on `Topic` |
| Create topics | `CREATE` on `Topic` or cluster permission matching the provisioning method |
| Delete topics | `DELETE` on `Topic` |
| Manage ACLs | ACL admin permissions per authorizer and Kafka version |

If the application uses `KafkaAdmin` with `NewTopic` beans to create topics at startup, the admin client needs topic-creation permission. Separating provisioning from the consumer's runtime principal reduces privileges and prevents a data-reading application from altering cluster structure.

## 7. Verifying Granted ACLs

Use an admin principal to list the consumer's ACLs:

```bash
kafka-acls.sh \
  --bootstrap-server kafka.example.com:9093 \
  --command-config admin.properties \
  --list \
  --principal User:orders-consumer
```

Verify that `ALLOW READ` exists for topic `orders` and group `orders-service`, and confirm the resource pattern and host match expectations. Do not stop at checking that ACLs exist; run the consumer with its real runtime credentials to confirm the broker recognizes the expected principal.

You can test with a small listener reading a record from the topic. If the listener subscribes to the topic, joins the group, and reads the record successfully, basic runtime permissions are working. Use a test topic/group to test denied cases without impacting production flows.

## 8. Recognizing Authorization Errors

When an ACL is missing or the principal mismatches, the broker rejects the request. Common errors:

- `TopicAuthorizationException`: the principal lacks required permissions on the accessed topic.
- `GroupAuthorizationException`: the principal lacks permissions on the consumer group, usually related to joining the group or committing offsets.
- `ClusterAuthorizationException`: the client invoked a cluster-level operation without corresponding permissions.
- `SaslAuthenticationException`: authentication failed; this is an authentication error, so check username, password, SASL mechanism, and TLS configuration before looking at ACLs.

When diagnosing, check in order: the principal received by the broker, the exact topic name, the runtime `group.id`, the denied operation, and the ACLs applied to the resource. The group name can be overridden by container configuration or `@KafkaListener(groupId=...)`, so do not look only at `spring.kafka.consumer.group-id`.

Do not catch and ignore authorization errors as if they were business-invalid records. Infinite retries will not fix a missing ACL; fix the permissions or principal configuration, then restart/resume the consumer per operational policy.

## 9. Revoking Permissions When No Longer Used

When an application or tenant is decommissioned, revoke the exact ACLs that were granted. Example:

```bash
kafka-acls.sh \
  --bootstrap-server kafka.example.com:9093 \
  --command-config admin.properties \
  --remove \
  --allow-principal User:orders-consumer \
  --operation Read \
  --topic orders

kafka-acls.sh \
  --bootstrap-server kafka.example.com:9093 \
  --command-config admin.properties \
  --remove \
  --allow-principal User:orders-consumer \
  --operation Read \
  --group orders-service
```

Revoking an ACL does not delete topics, records, or committed offsets. If a principal is shared across multiple applications, revoking permissions can disrupt all of those clients. Therefore, assign separate principals per service or workload, with a credential rotation process and revocation upon decommissioning.

## 10. Consumer Security Checklist

- Confirm the broker enables an authorizer and has no unexpectedly permissive settings.
- Identify the actual principal from SASL or TLS certificates.
- Grant `READ` on the exact topics and `READ` on the exact group ID used by listeners.
- Use literal ACLs or narrow prefixes aligned with data boundaries.
- Use `SASL_SSL` or appropriate TLS and store credentials in a secret manager.
- Separate the runtime consumer principal from admin/provisioning principals.
- Test both allowed and denied cases using real credentials.
- Monitor authorization failures and audit ACLs periodically.

Consumer ACL authorization means restricting read access by topic and consumer group tied to an authenticated principal. Combining least-privilege ACLs with SASL/TLS, per-service credentials, and testing with the exact runtime configuration protects Kafka data while keeping Spring Kafka flows running reliably.
