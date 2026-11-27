# Separating Administrative Accounts from Runtime Application Accounts

## 1. Why Separate These Two Account Types?

In a Spring Cloud Stream system, the application connects to Kafka, RabbitMQ, or Pulsar to publish and consume messages. The broker also needs people or automated systems to create topics, queues, namespaces, virtual hosts, ACLs, policies, quotas, and security settings. These two bodies of work have vastly different permission scopes.

- **Administrative identity:** used by administrators or provisioning pipelines to create, modify, and inspect broker resources. Permissions can include managing topics/namespaces, granting ACLs, configuring policies, creating users/roles, and altering cluster settings.
- **Runtime identity:** used by the service when the application starts and processes messages. Permissions typically only require reading certain topics/queues, writing to certain destinations, and joining the exact consumer group/subscription.

If the application uses administrative credentials, a misconfiguration, dependency vulnerability, or secret leak can allow an attacker to delete topics, create users, alter ACLs, or read data outside business boundaries. Separating identities limits blast radius: runtime can only execute operations required by the service's functionality.

~~~mermaid
flowchart TD
    H[Platform administrator] -->|MFA / short-lived admin identity| P[Provisioning pipeline]
    P -->|Create topics, queues, ACLs, policies| B[(Messaging broker)]
    S[Spring Cloud Stream application] -->|Runtime credential from secret manager| R[Least-privilege runtime principal]
    R -->|Read / write only approved destinations| B
    R -. No user, ACL or cluster administration .-> B
~~~

The core principle is that an application receives only the permissions needed to execute its message flows. Broker resource administration happens in a separate workflow, with clear accountability and auditability.

## 2. Distinguishing Identity, Role, and Credential

These concepts are often lumped together as "user", yet they have distinct meanings:

| Concept | Meaning | Examples |
|---|---|---|
| Identity / principal | Identity authenticated by the broker | svc-orders-prod, platform-provisioner |
| Role | Set of permissions bound to an identity | orders-consumer, topic-provisioner |
| Credential | Proof used to verify identity | Password, client certificate, SASL secret, OAuth token |
| ACL / permission | Permission on a specific resource | Read topic orders.events, Write topic orders.accepted |
| Destination | Where the application sends or receives messages | Kafka topic, Rabbit exchange/queue, Pulsar topic |

A runtime principal can be granted permissions to read input topics and write output topics. An administrative account can be granted a provisioning role scoped to a cluster or namespace. A credential is authentication material; it does not replace permission design.

Identity names should reflect service, environment, and purpose, such as svc-order-processor-prod. Avoid using a single shared application account across all services because auditing will struggle to determine which service performed an action.

## 3. Two-Stream Permission Model

A secure deployment workflow has two independent streams:

1. **Provisioning:** a pipeline or administrator creates destinations, groups/subscriptions, policies, and permissions for the runtime principal.
2. **Runtime:** the application fetches runtime credentials from a secret manager, connects to the broker, and reads/writes only the granted destinations.

Example when deploying order-processor:

| Task | Executing Identity | Required Permissions |
|---|---|---|
| Create topic orders.events | Provisioner | Create/Describe topic |
| Create topic orders.accepted | Provisioner | Create/Describe topic |
| Grant ACLs to service | Provisioner | Alter ACL within assigned scope |
| Consume orders.events | Runtime principal | Read topic, Describe topic, Read group |
| Produce orders.accepted | Runtime principal | Write topic, Describe topic |
| Delete production topic | Administrator per approval process | Controlled administrative privileges |

The application does not need permission to create users or grant ACLs to carry out daily message reading/writing. If the binder must inspect metadata or declare resources at startup, determine the exact minimum permissions required by your binder version and consider pre-provisioning resources.

## 4. Minimum Permissions for a Spring Cloud Stream Application

Before granting permissions, list all messaging operations of the service:

- Which input bindings consume?
- Which output bindings produce?
- Does the service need its own consumer group or subscription?
- Are there retry topics, dead-letter queues (DLQs), or retry destinations?
- Does the binder need to read metadata, declare exchanges/queues, or check schemas?
- Does the application genuinely need to create destinations automatically?

From this list, build a permission matrix. Example:

| Resource | Runtime svc-order-processor-prod | Provisioner |
|---|---|---|
| orders.events | Read, Describe | Create, Describe, Alter |
| orders.accepted | Write, Describe | Create, Describe, Alter |
| orders.retry | Write/Read per retry flow | Create, Describe, Alter |
| orders.DLT | Write or Read per error flow | Create, Describe, Alter |
| Consumer group order-processor | Read | Managed per cluster policy |
| ACLs and users | None | Grant permissions within assigned scope |
| Cluster configuration | None | Appropriate admin roles only |

Do not grant permissions just because "it might be needed later". When a new feature requires an additional destination, update permissions through the provisioning pipeline and review the change as part of the release.

## 5. Kafka: Separating Admin Principals and Application Principals

Kafka authenticates clients into principals, such as User:svc-order-processor-prod. Authorization can use ACLs or the Kafka platform's corresponding authorizer. Admin accounts hold permissions to manage topics and ACLs; runtime principals only receive permissions on the topics and consumer groups used by the service.

Example permissions needed for a service reading an input topic and writing an output topic:

~~~text
Principal: User:svc-order-processor-prod

Topic orders.events:
  Read
  Describe

Topic orders.accepted:
  Write
  Describe

Group order-processor:
  Read
~~~

Exact permissions depend on the Kafka version, authorizer, and operations performed by the binder. Illustrative ACL CLI commands using the Kafka ACL authorizer:

~~~bash
kafka-acls.sh --bootstrap-server kafka.prod.example:9093 \
  --command-config admin-client.properties \
  --add --allow-principal 'User:svc-order-processor-prod' \
  --operation Read --operation Describe \
  --topic orders.events

kafka-acls.sh --bootstrap-server kafka.prod.example:9093 \
  --command-config admin-client.properties \
  --add --allow-principal 'User:svc-order-processor-prod' \
  --operation Write --operation Describe \
  --topic orders.accepted

kafka-acls.sh --bootstrap-server kafka.prod.example:9093 \
  --command-config admin-client.properties \
  --add --allow-principal 'User:svc-order-processor-prod' \
  --operation Read --group order-processor
~~~

These commands run with dedicated administrative credentials in admin-client.properties. Never package that admin file in the application image or classpath. The provisioning pipeline should store the file/secret in a separate execution environment with controlled access.

## 6. Kafka: Avoiding Auto-Created Topics with Runtime Privileges

The Kafka binder can support auto-creating topics or increasing partitions depending on configuration. If the runtime principal is granted Create/Alter permissions so the binder can self-provision, the application identity receives a broader scope than normal produce/consume rights.

For production, consider pre-creating topics and ACLs via an administrative pipeline, then disabling auto-create/auto-add-partitions if compatible with your architecture and binder version.

Illustrative configuration example:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          autoCreateTopics: false
          autoAddPartitions: false
~~~

Property names and default behaviors must be verified against the exact Kafka binder version in use. Some clusters may also auto-create topics via broker-level settings; disabling auto-create on the binder does not replace proper broker and ACL configuration.

If an application truly needs to create destinations dynamically, do not grant cluster-wide permissions to every instance. Use a dedicated provisioning service or an automated identity with resource limits, input validation, and auditing.

## 7. Kafka: Configuring Runtime Credentials for Spring Cloud Stream

The application should receive only runtime credentials. Example using SASL/SCRAM via environment variables:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          brokers: ${KAFKA_BOOTSTRAP_SERVERS}
          configuration:
            security.protocol: SASL_SSL
            sasl.mechanism: SCRAM-SHA-512
            sasl.jaas.config: ${KAFKA_RUNTIME_JAAS}
~~~

KAFKA_RUNTIME_JAAS must be injected into the process by a secret manager or deployment platform. Real values must never reside in repositories, Dockerfiles, image layers, logs, or committed config files.

The runtime principal needs Read/Describe on input topics, Write/Describe on output topics, and Read on the consumer group if the application consumes. If the binder requires additional operations like DescribeConfigs or IdempotentWrite, verify against actual producer/consumer configurations and grant only what is necessary.

## 8. Kafka: Where Should Admin Accounts Be Used?

A Kafka admin account can be used by:

- Pipelines creating topics, partitions, retention, and cleanup policies.
- Pipelines granting or revoking ACLs for service principals.
- Workflows creating/managing SCRAM users or certificate mappings.
- Operations tools inspecting the cluster and applying approved configuration changes.

This account should not be used by:

- A Spring Boot application at startup.
- Kafka binder producers/consumers.
- Daily scheduled message-processing jobs.
- Scripts embedded inside a runtime image.
- A developer laptop running production services.

If you need to test runtime permissions, log in using the actual runtime principal in a dedicated test job scoped to test read/write access. Do not attempt to "fix ACL errors" by swapping runtime credentials for admin credentials.

## 9. RabbitMQ: Separating Administrators, Management Tags, and Virtual Host Permissions

RabbitMQ has separate users, virtual hosts, and permissions. Administrators can create vhosts, users, policies, and grant permissions. An application's runtime user should only hold permissions on the required virtual host and resources.

RabbitMQ distinguishes user tags from resource permissions:

- User tags such as administrator, management, or monitoring control access to the management UI/API.
- Permissions on a virtual host control configure, write, and read rights on exchanges/queues.

Having a management tag does not mean a user holds all permissions on all vhosts; conversely, an application may need permission to read/write queues without needing Management UI access.

Example creating a vhost and user with an admin account:

~~~bash
rabbitmqctl add_vhost /orders
rabbitmqctl add_user svc_order_processor_prod "$RABBIT_RUNTIME_PASSWORD"
rabbitmqctl set_permissions -p /orders svc_order_processor_prod \
  '^orders\.(events|accepted|retry|DLT)$' \
  '^orders\.(accepted|retry|DLT)$' \
  '^orders\.(events|retry)$'
~~~

The regexes in the example only illustrate resource scope; adjust them to actual exchange/queue names and binder provisioning behavior. Do not grant administrator or management tags to runtime users.

## 10. RabbitMQ: Understanding the Three Permission Types

RabbitMQ manages three permission types per virtual host:

- configure: create, delete, or alter resources such as exchanges and queues matching the regex scope.
- write: publish to exchanges or perform corresponding write operations.
- read: consume from queues or perform corresponding read operations.

The Spring Cloud Stream Rabbit binder can declare exchanges, queues, and bindings on startup. If you let the binder auto-provision, the runtime user usually needs configure permission on the matching resource names in addition to read/write permissions. That is why the provisioning strategy must be explicitly decided.

Two deployment models:

1. **Pre-provision:** administrators/pipelines create exchanges, queues, and bindings beforehand. The runtime user receives only the permissions needed for publish/consume if the binder is configured not to self-declare resources.
2. **Scoped runtime declaration:** the runtime user receives configure on a narrow set of resource names, with no rights to manage users/vhosts/policies.

Do not use `.*` regexes for all permissions when the application only needs a few destinations. When destination names change, update regexes and resources through code review.

## 11. RabbitMQ: Configuring Runtime Credentials

Example runtime connection configuration:

~~~yaml
spring:
  rabbitmq:
    host: ${RABBITMQ_HOST}
    port: ${RABBITMQ_PORT:5671}
    username: ${RABBITMQ_RUNTIME_USERNAME}
    password: ${RABBITMQ_RUNTIME_PASSWORD}
    virtual-host: /orders
    ssl:
      enabled: true
~~~

SSL property names and truststore/client certificate settings may vary by Spring Boot/Rabbit client version. Configuration must enable server certificate validation and use appropriate trust material; do not disable hostname verification to bypass TLS errors.

The runtime account is restricted to vhost /orders. If the application needs to publish to /operations, create a separate binder/connection and dedicated user for that vhost, or grant intentional permissions per architecture. Never use one administrator password to connect across all vhosts.

## 12. RabbitMQ: Do Not Grant Admin Permissions Just to Inspect Queues

Applications normally do not need the Management HTTP API. Health indicators or metrics can use separate endpoints/credentials depending on configuration. If broker monitoring is needed, provision a read-only monitoring user for metrics and keep it separate from the runtime messaging principal.

Do not put management credentials into the Spring Cloud Stream binder just to inspect queues. The binder connects via AMQP to publish/consume; the management API is a separate administrative surface.

When investigating backlogs, an administrator or monitoring identity can view queue state. Runtime services only need to process messages within their granted permission scope.

## 13. Pulsar: Separating Superusers, Admin Roles, and Runtime Roles

Pulsar authenticates clients into roles and supports authorization by tenant, namespace, and topic. Admin roles can manage tenants/namespaces, policies, permissions, and resources. An application's runtime role usually only needs produce and/or consume permissions on designated namespaces/topics.

Example separation:

| Role | Responsibility | Scope |
|---|---|---|
| platform-admin | Cluster administration and security configuration | Cluster per organizational policy |
| namespace-provisioner | Create namespaces, topics, policies, and grant permissions | Assigned tenant/namespace |
| svc-orders-prod | Consume and produce order events | Namespace commerce/orders |
| svc-audit-prod | Consume events for auditing | Granted audit namespace/topic |

Do not use superuser tokens for applications. A superuser can bypass many permission boundaries; if compromised, the impact is severe.

## 14. Pulsar: Granting Producer and Consumer Permissions by Namespace

Illustrative admin operation via the Pulsar admin CLI:

~~~bash
pulsar-admin namespaces grant-permission commerce/orders \
  --role svc-orders-prod \
  --actions produce,consume
~~~

The produce and consume permissions in the example are granted on the commerce/orders namespace. If a service only needs to consume, omit produce; if it only emits events, omit consume. Topic-level permissions can be granted when your authorization model and Pulsar version support them, enabling tighter scoping.

Creating tenants/namespaces, setting retention, backlog quotas, subscription policies, or granting roles are provisioning duties. Runtime roles must not be allowed to self-grant permissions or modify namespace policies.

## 15. Pulsar: Runtime Authentication via Token or TLS

Pulsar supports multiple authentication methods, such as tokens or TLS certificates. Runtime credentials should represent the application role and be constrained by authorization policies.

Illustrative client token configuration using Spring Boot Pulsar client properties:

~~~yaml
spring:
  pulsar:
    client:
      service-url: ${PULSAR_SERVICE_URL}
      authentication:
        plugin-class-name: org.apache.pulsar.client.impl.auth.AuthenticationToken
        params:
          token: ${PULSAR_RUNTIME_TOKEN}
~~~

Property paths and how authentication parameters are passed depend on the Spring Boot Pulsar client and Spring Cloud Stream Pulsar binder versions. Verify the supported configuration in your project's dependency version; do not copy verbatim across versions if property structures change.

The token issued to svc-orders-prod has only the granted produce/consume permissions. Never give a platform-admin token to an application pod. Tokens should have a TTL or an appropriate revocation/rotation process.

## 16. Comparison Table of Permission Separation by Broker

| Broker | Administrative Identity | Runtime Identity | Typical Runtime Permissions Needed |
|---|---|---|---|
| Kafka | Principal managing topics, ACLs, users, and cluster policies | Service's SASL/OAuth/mTLS principal | Read/Describe topic, Write topic, Read group |
| RabbitMQ | User managing vhosts, users, policies, and permissions | Dedicated user within a virtual host | Read/Write; scoped Configure if binder auto-provisions |
| Pulsar | Superuser/admin/provisioner role | Role authenticated via token or TLS | Produce/Consume on namespace/topic |

Permission names and authorization details differ across broker versions and plugins. The design goal stays the same: the runtime principal holds permissions only on the resources the service uses.

## 17. Never Place Admin Credentials in Application Configuration

Do not store admin usernames/passwords, superuser tokens, or administrative client certificates in:

- Committed application.yml or application-prod.yml files.
- Dockerfiles, build arguments, or image layers.
- Public GitHub Actions/GitLab CI logs or artifacts.
- Kubernetes ConfigMaps.
- Test fixture files packaged into JARs.
- Shared environment variables across all services.

Runtime credentials are also secrets, yet they must be managed separately and never substituted with admin credentials. Runtime secrets are issued only to specific workloads, namespaces, and environments.

Example configuration referencing only environment variables:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          brokers: ${KAFKA_BOOTSTRAP_SERVERS}
          configuration:
            security.protocol: SASL_SSL
            sasl.mechanism: SCRAM-SHA-512
            sasl.jaas.config: ${KAFKA_RUNTIME_JAAS}
~~~

The configuration file contains variable names; the secret manager/secret mount supplies the values. Never print secret values while debugging.

## 18. Secret Managers and Workload-Scoped Provisioning

A deployment platform can retrieve runtime secrets from:

- Kubernetes Secrets synced from an external secret manager.
- HashiCorp Vault or a cloud secret manager.
- Workload identities and short-lived tokens issued by the platform.
- A certificate manager issuing client certificates for mTLS.

Reference flow:

~~~mermaid
sequenceDiagram
    participant W as Workload identity
    participant SM as Secret manager
    participant A as Spring Cloud Stream app
    participant B as Broker
    W->>SM: Authenticate workload
    SM->>W: Runtime secret for this service
    W->>A: Mount / inject runtime credential
    A->>B: Authenticate as svc-orders-prod
    B-->>A: Authorize only assigned topics / queues
~~~

Credentials should be issued per service and environment. Do not reuse a single secret across development, staging, and production. When a service is decommissioned or changes ownership, revoke its credentials.

If the platform supports workload identity or short-lived tokens, prefer those mechanisms to minimize credential lifetime. If using static passwords, maintain rotation and secure distribution workflows.

## 19. Credential Rotation Without Disrupting Applications

Rotation should be planned before secrets expire. Common workflow:

1. Create a new credential for the same runtime principal or a versioned new principal.
2. Grant matching ACLs/permissions to the new credential.
3. Place the new secret in the secret manager.
4. Restart or reload the workload as supported by the client/binder.
5. Confirm new connections authenticate and message flows operate.
6. Revoke the old credential once all instances have switched over.
7. Record an audit event and rotation timestamp.

With some mechanisms, two credentials can remain active briefly in parallel. With mechanisms that do not support multiple simultaneous credentials, perform a controlled rollout or use a new versioned principal and shift traffic.

Never revoke the old credential before the new credential is verified. Likewise, never leave old credentials active indefinitely after rotation.

## 20. Separation by Environment and by Service

Each environment needs its own identity and resource scope:

| Environment | Runtime Principal | Broker Scope |
|---|---|---|
| Development | svc-orders-dev | Development cluster/topics |
| Staging | svc-orders-stg | Staging cluster/topics |
| Production | svc-orders-prod | Production cluster/topics |

Do not use svc-orders-dev to access production just for configuration convenience. Do not share a principal among order-processor, billing-service, and audit-service; each service has different data flows and responsibilities.

If multiple instances of the same service must share a consumer group, they can share the service's runtime principal or a platform-issued workload identity. If your organization requires per-instance auditing, you can assign separate principals per workload instance/replica, though you must manage the resulting ACL count and rotation appropriately.

## 21. Administrative Privileges Must Be Time-Bound and Audited

Admin privileges carry high impact, so they should be granted by role and bounded in time:

- Human administrators authenticate using personal identities and MFA.
- Provisioning pipelines use dedicated service identities, never shared human passwords.
- Admin privileges are scoped to specific clusters, tenants, or namespaces according to responsibility.
- Production changes are reviewed and logged with requester, approver, and change details.
- Administrative credentials have rotation and revocation procedures.
- Break-glass accounts are locked away, monitored, and used only during documented incidents.

Do not share one admin account across an entire team. Individual identities make it traceable who or which pipeline altered ACLs, deleted topics, or changed policies.

## 22. Provisioning Pipelines Should Be Idempotent and Controlled

Pipelines creating resources and permissions must be safely re-runnable. Re-running should not create duplicate users, grant broader ACLs, or delete out-of-scope resources.

~~~mermaid
flowchart TD
    A[Review change request] --> B[Validate destination and permission matrix]
    B --> C[Provisioner authenticates with admin identity]
    C --> D[Create / verify broker resources]
    D --> E[Grant least-privilege runtime permissions]
    E --> F[Verify runtime principal access]
    F --> G[Publish audit result]
~~~

Pipelines should verify:

- Do destinations follow naming conventions and have valid owners?
- Does the runtime principal exist?
- Do ACLs already exist; if so, are they properly scoped?
- Are new permissions broader than what was reviewed?
- Do topic/queue policies align with retention, DLQ, and quotas?
- After granting permissions, can the runtime principal read/write the exact intended resources?
- Are out-of-scope resources still denied?

Testing both allowed and denied permissions catches overly broad ACL configurations.

## 23. Testing Runtime Permissions by Allow and Deny Principles

A good security test does not only confirm a service can read valid topics. It also verifies the service cannot perform administrative actions or access out-of-scope resources.

Example test matrix:

| Operation | Expected Result |
|---|---|
| Consume orders.events | Allow |
| Produce orders.accepted | Allow |
| Consume payroll.events | Deny |
| Create a new topic | Deny |
| Delete a production topic | Deny |
| Create broker users or grant ACLs | Deny |
| Read necessary metadata of granted topics | Allow if binder requires it |

Test with real runtime credentials in a test environment. Never run tests with admin credentials and assume runtime permissions are correct.

## 24. Verifying the Binder Does Not Accidentally Use Admin Credentials

When multiple binders or brokers exist, inspect every connection:

1. Do binder names and endpoints match the right cluster/vhost/namespace?
2. Is the injected username/principal/token a runtime identity?
3. Does the credential belong to the right environment?
4. Do ACLs cover only the binding's destinations?
5. Is the binder auto-creating resources and therefore requiring Configure/Create permissions?
6. Is any global configuration or environment variable accidentally overriding credentials?
7. Do logs print sensitive principals/usernames or endpoints? If so, filter sensitive data.

With multiple binders, each binder may need its own runtime principal. For example, kafka-orders-prod only reads order topics, while kafka-analytics-prod only writes analytics topics. Do not use a shared admin credential to solve connectivity issues across binders.

## 25. Limiting Permissions When the Binder Must Self-Declare Resources

Some binders support auto-provisioning exchanges/queues/topics or DLQs. Distinguish application message-processing rights from resource-declaration rights:

- Produce/consume are runtime data operations.
- Create/declare/configure are operations altering broker topology.
- Grant/revoke ACLs or policies are security administration operations.

If the binder is required to declare resources at startup, you can grant narrow Configure permission for approved exchange/queue names. Never grant user creation, vhost modification, or cluster management rights because of this.

Another option is to pre-provision resources and configure the binder not to self-create. This approach generally keeps runtime principal privileges smaller and ensures topology changes are controlled through pipelines.

## 26. Handling Compromised Runtime Credentials

If a runtime secret is suspected to be compromised:

1. Identify affected services, environments, principals, and destinations.
2. Create replacement credentials or a new principal with the same least-privilege permissions.
3. Distribute the new credentials through the secret manager.
4. Roll out/reconnect workloads and verify message flow.
5. Revoke the compromised old credential.
6. Inspect broker audit logs for anomalous activity.
7. Check whether ACLs or permissions were modified without authorization.
8. If needed, temporarily narrow or revoke permissions and process backlogs per runbook.
9. Document the root cause of the secret leak and update procedures.

Do not react by replacing runtime credentials with admin credentials for a "quick recovery". When runtime credentials are tightly scoped, revoking them limits the incident's blast radius.

## 27. Common Design Mistakes

| Practice | Risk | Fix |
|---|---|---|
| Using an admin user in application.yml | Exposes credentials with broad privileges | Create a dedicated runtime principal |
| Sharing one user across all services | No incident isolation and hard to audit | One identity per service/environment |
| Runtime allowed to create/delete any topic | Application bugs can destroy data | Pre-provision or restrict resources |
| Rabbit runtime user has administrator tag | Unnecessary management privileges | Remove admin tag, grant vhost permissions only |
| Pulsar application uses superuser token | Bypasses authorization boundaries | Issue token for a dedicated produce/consume role |
| Kafka runtime has Alter ACL permission | Can self-escalate privileges | Grant ACL management rights only to provisioner |
| Secrets placed in ConfigMap or Git | Credentials easily exposed | Secret manager/Secret mount |
| No credential rotation | Secrets live too long | Rotation schedule and transition procedure |
| Not testing denied operations | ACLs may be overly broad | Negative authorization tests |
| Granting .* permissions for convenience | Runtime accesses out-of-scope resources | Destination-specific regexes/ACLs |

## 28. Production Readiness Checklist

- [ ] Dedicated runtime principal per service and environment.
- [ ] No admin passwords/tokens in application configuration or images.
- [ ] Kafka ACLs allow only required topics/groups.
- [ ] RabbitMQ users have no administrator/management tags unless needed; permissions scoped by vhost/resource.
- [ ] Pulsar roles have only produce/consume on assigned namespaces/topics.
- [ ] Topics, queues, DLQs, and policies provisioned through controlled workflows.
- [ ] Auto-create/declare configured to match the permission model.
- [ ] Secrets fetched from a secret manager or workload identity.
- [ ] TLS and broker authentication enabled with proper certificate verification.
- [ ] Credential rotation and revocation processes in place.
- [ ] Audit logging enabled for administrative permission changes.
- [ ] Tests verify allowed operations are permitted and out-of-scope operations are denied.
- [ ] Logs do not print passwords, tokens, JAAS configs, or private keys.
- [ ] Runbook ready for compromised runtime credentials.

## 29. Deployment Workflow with Separation of Duties

1. Design bindings and list the topics/queues/groups/subscriptions the service needs.
2. Create a permission matrix for the runtime principal.
3. Review resources, permissions, and environments before making production changes.
4. Provisioner authenticates with an administrative identity to create resources and ACLs.
5. Secret manager supplies runtime credentials to the specific workload.
6. Spring Cloud Stream binder connects using the runtime identity.
7. Verify allow/deny behavior using runtime credentials.
8. Monitor broker audit logs and metrics after rollout.
9. Rotate credentials on schedule and revoke old credentials.
10. When a service is retired, revoke the runtime principal and clean up permissions per procedure.

Separating administrative accounts from runtime application accounts is a vital security boundary in messaging systems. Administrators or provisioning pipelines manage topology, users, and ACLs; Spring Cloud Stream runtime uses only an identity authorized to read/write the intended business destinations. Apply the same principle across Kafka principals/ACLs, RabbitMQ users/vhost permissions, and Pulsar roles/namespace permissions; combine secret managers, rotation, auditing, and testing of both allowed and denied operations to reduce blast radius when applications or credentials encounter incidents.

## References

- [Apache Kafka — Authorization and ACLs](https://kafka.apache.org/documentation/#security_authz)
- [RabbitMQ — Access Control](https://www.rabbitmq.com/docs/access-control)
- [Apache Pulsar — Authorization](https://pulsar.apache.org/docs/security-authorization/)
- [Spring Cloud Stream — Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/overview.html)
- [Spring Cloud Stream — Rabbit Binder](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html)
