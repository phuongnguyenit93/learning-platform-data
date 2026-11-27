# Security, IAM Authentication, and Connecting Kafka Clients to MSK

## Learning Objectives

Amazon Managed Streaming for Apache Kafka (Amazon MSK) manages Apache Kafka broker infrastructure, yet applications must still connect to the right endpoint, authenticate their identity, and hold permissions to perform actions on the cluster. A client can resolve DNS and open a TCP connection and still fail to produce or consume due to missing Kafka permissions. Conversely, an IAM policy can be valid while connections still time out due to security groups, routing, or mismatched bootstrap brokers.

In the CLOUD_PROVIDERS_AWS module, learners need to understand how to place MSK in a VPC, select an appropriate authentication mechanism, and design least-privilege permissions. This lesson focuses on IAM access control, Kafka client connectivity, as well as SASL/SCRAM and mutual TLS (mTLS) options so you know when each fits.

After this lesson, learners will be able to:

- Distinguish between authentication, authorization, network access, and encryption.
- Explain MSK IAM access control and the difference between control-plane APIs and the Kafka data plane.
- Choose IAM, SASL/SCRAM, or mTLS based on identity, runtime environment, and governance needs.
- Configure Java Kafka clients with the AWS_MSK_IAM mechanism and the aws-msk-iam-auth library.
- Configure non-Java clients using SASL_OAUTHBEARER and the corresponding token-signing library.
- Author IAM policies scoping permissions by cluster, topic, consumer group, and transactional ID.
- Retrieve the right bootstrap broker string and choose the right port for each authentication method.
- Connect to MSK Provisioned and MSK Serverless inside a VPC.
- Design cross-account connectivity using MSK cluster policies and multi-VPC private connectivity.
- Troubleshoot DNS, TCP, TLS, SASL, and authorization failures layer by layer.

## 1. Four Protection Layers When Connecting to Kafka

When an application connects to an MSK broker, four independent questions apply:

1. **Network access:** does the client have a route and security group/network ACL permission to reach the broker?
2. **Encryption:** is data in transit protected with TLS?
3. **Authentication:** how does the broker verify who the client is?
4. **Authorization:** which cluster, topics, or consumer groups is that identity allowed to connect to, read from, write to, or join?

A request succeeds only when every required layer passes. IAM does not open network ports; security groups do not grant topic read permissions; TLS alone does not prove a client may produce; bootstrap servers do not grant Kafka permissions.

~~~mermaid
sequenceDiagram
    participant C as Kafka client
    participant N as VPC / Security Group
    participant B as MSK broker
    participant I as IAM / Kafka authorizer
    C->>N: DNS lookup and TCP connect
    N->>B: Allow connection to listener
    C->>B: TLS handshake (with client certificate if using mTLS)
    C->>B: SASL authentication if using IAM or SCRAM
    B->>I: Verify identity and permissions
    I-->>B: Allow or Deny
    B-->>C: Kafka response
~~~

For example, **Connection timed out** errors typically require investigating networking first. **SaslAuthenticationException** usually points to authentication mechanisms or credentials. **TopicAuthorizationException** shows the client progressed further but lacks topic permissions. Reading the right error layer keeps you from editing IAM policies when the actual root cause is DNS or a port.

## 2. Authentication and Authorization in MSK

Authentication identifies the connecting principal. A principal can be an IAM role, a SCRAM user, or an identity derived from a client certificate. Authorization determines what that principal may do on the cluster.

Amazon MSK supports the following primary mechanisms for MSK Provisioned:

| Mechanism | Authentication | Typical authorization | Characteristics |
|---|---|---|---|
| IAM access control | AWS IAM identity and SigV4 signature | IAM policies with `kafka-cluster:` prefix | Unifies authentication and authorization; ideal for workloads using IAM roles |
| SASL/SCRAM | Username/password stored in Secrets Manager | Apache Kafka ACLs | Separates credentials from topic permissions; suits user/password models |
| Mutual TLS | Client certificate issued by AWS Private CA | Apache Kafka ACLs | Certificate-based authentication; suits PKI and certificate-managed workloads |
| Unauthenticated | None | No client-layer identity control | Consider only for isolated testing environments |

Do not enable multiple mechanisms simply because you can. Each extra mechanism adds credentials, listeners, rotation workflows, and incident handling paths. Select the mechanism aligned with existing identities and organizational operational capabilities.

## 3. What Does IAM Access Control Solve?

IAM access control for MSK handles both authentication and authorization for IAM identities. Clients use AWS credentials to prove identity; MSK evaluates IAM policies to determine permitted Kafka operations.

Example:

- An ECS task runs with task role `orders-producer-role`.
- The Kafka client retrieves temporary credentials from task metadata.
- The MSK IAM library signs authentication messages with SigV4.
- The broker verifies the IAM principal and evaluates cluster/topic policies.
- The producer can write only to the topics permitted by policy.

This avoids storing usernames/passwords or long-lived access keys in config files. When tasks rotate or credentials refresh, the AWS credential provider chain automatically fetches new temporary credentials.

IAM access control works with Java and non-Java clients such as Python, Go, JavaScript, and .NET. For non-Java clients, AWS states the cluster must run Kafka 2.7.1 or newer for IAM access control.

An important point: Apache Kafka ACL APIs can be invoked on a cluster using IAM access control, yet ACLs do not govern permissions for IAM identities. For IAM principals, you must use IAM authorization policies.

IAM access control also does not protect Apache ZooKeeper nodes on clusters still using ZooKeeper. If ZooKeeper access is needed, design separate security groups and ZooKeeper controls; never assume Kafka broker IAM permissions cover ZooKeeper.

## 4. Distinguishing Control Plane and Kafka Data Plane

MSK has two action groups with similar names that belong to separate planes.

| Prefix | Plane | Examples | Purpose |
|---|---|---|---|
| `kafka:` | MSK control plane | `kafka:DescribeCluster`, `kafka:GetBootstrapBrokers` | Manage or query MSK resources via AWS APIs |
| `kafka-cluster:` | Kafka data plane | `kafka-cluster:Connect`, `kafka-cluster:WriteData` | Allow Kafka clients to perform operations on clusters/topics/groups |

For example, an administrative pipeline calling AWS CLI to fetch bootstrap brokers may need `kafka:GetBootstrapBrokers`. However, that permission does not allow a producer to write messages to a topic.

Conversely, a role with only `kafka-cluster:Connect` and `kafka-cluster:WriteData` can perform matching Kafka operations, yet may lack permission to call AWS APIs to list clusters or retrieve endpoints.

Separating these two permission sets prevents application roles from accidentally having rights to create, delete, or modify clusters.

## 5. IAM Principals and Client Credential Sources

Clients need a valid AWS credential source. In AWS environments, prefer temporary credentials from IAM roles:

| Client environment | Recommended identity source |
|---|---|
| Amazon EC2 | Instance profile role |
| Amazon ECS | Task role |
| Amazon EKS | EKS Pod Identity or IAM Roles for Service Accounts (IRSA) |
| AWS Lambda | Execution role |
| Developer workstation | AWS IAM Identity Center or named profile |
| Workload in another account | AssumeRole or cross-account IAM setup per architecture |

The `aws-msk-iam-auth` library uses the AWS credential provider chain. Never put access keys and secret keys into source code, container images, `client.properties`, manifests, or logs.

With named profiles on a developer machine, you can set `awsProfileName` in JAAS options. In production, let workload identity supply credentials automatically. If a role must assume a role in another account, verify both the target role's trust policy and `sts:AssumeRole` permission on the source principal.

Check your active identity with the AWS CLI:

~~~bash
aws sts get-caller-identity
~~~

The output must match the role or principal expected by operations. If the CLI and Kafka client run in different environments, do not assume they use the same credential source.

## 6. Enabling IAM Access Control on MSK Provisioned

When creating an MSK Provisioned cluster, enable IAM role-based authentication under Security settings. When creating via API or AWS CLI, the client authentication block looks like:

~~~json
{
  "ClientAuthentication": {
    "Sasl": {
      "Iam": {
        "Enabled": true
      }
    }
  }
}
~~~

IAM authentication requires client-to-broker TLS encryption. Do not configure an IAM listener on plaintext connections. When enabling IAM on an existing cluster, verify cluster state, encryption-in-transit settings, and client impact before making changes.

A cluster can enable additional authentication methods where supported by the service and configuration. However, each listener must be paired with its exact matching bootstrap string, port, and client properties.

## 7. Configuring Java Clients with AWS_MSK_IAM

Java can use the custom SASL mechanism `AWS_MSK_IAM`. This mechanism is implemented by the `aws-msk-iam-auth` library.

Add the Maven dependency. Version 2.3.9 was the stable release published on Maven Central at the time of writing; check the latest release and Kafka client compatibility before upgrading.

~~~xml
<dependency>
    <groupId>software.amazon.msk</groupId>
    <artifactId>aws-msk-iam-auth</artifactId>
    <version>2.3.9</version>
</dependency>
~~~

Client properties:

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=AWS_MSK_IAM
sasl.jaas.config=software.amazon.msk.auth.iam.IAMLoginModule required;
sasl.client.callback.handler.class=software.amazon.msk.auth.iam.IAMClientCallbackHandler
~~~

If using a named profile on a developer machine, add the option to the JAAS config:

~~~properties
sasl.jaas.config=software.amazon.msk.auth.iam.IAMLoginModule required awsProfileName="dev-msk";
~~~

There is no need to generate SASL passwords or copy access keys into config files. The library discovers AWS credentials from the provider chain, signs authentication payloads, and handles credential refreshes per its built-in lifecycle.

### 7.1. Minimal Java Producer

The example below reads the bootstrap string from an environment variable and uses the process's IAM role:

~~~java
import java.util.Properties;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;

public class MskIamProducer {
    public static void main(String[] args) {
        String bootstrapServers =
            System.getenv("MSK_BOOTSTRAP_SERVERS");

        if (bootstrapServers == null || bootstrapServers.isBlank()) {
            throw new IllegalStateException(
                "MSK_BOOTSTRAP_SERVERS is required"
            );
        }

        Properties props = new Properties();
        props.put("bootstrap.servers", bootstrapServers);
        props.put("key.serializer",
            "org.apache.kafka.common.serialization.StringSerializer");
        props.put("value.serializer",
            "org.apache.kafka.common.serialization.StringSerializer");

        props.put("security.protocol", "SASL_SSL");
        props.put("sasl.mechanism", "AWS_MSK_IAM");
        props.put("sasl.jaas.config",
            "software.amazon.msk.auth.iam.IAMLoginModule required;");
        props.put("sasl.client.callback.handler.class",
            "software.amazon.msk.auth.iam.IAMClientCallbackHandler");

        try (KafkaProducer<String, String> producer =
                 new KafkaProducer<>(props)) {
            ProducerRecord<String, String> record =
                new ProducerRecord<>(
                    "orders",
                    "order-1001",
                    "{\"orderId\":\"order-1001\",\"status\":\"CREATED\"}"
                );

            producer.send(record).get();
            producer.flush();
        } catch (Exception e) {
            throw new RuntimeException("Cannot publish to MSK", e);
        }
    }
}
~~~

Producers must hold `Connect`, `DescribeTopic`, and `WriteData` permissions on the corresponding resources. If the topic does not exist yet, create it via an administrative workflow or grant `CreateTopic` under an approved policy.

### 7.2. Minimal Java Consumer

Consumers additionally need permissions on the consumer group. Example:

~~~java
import java.time.Duration;
import java.util.Collections;
import java.util.Properties;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;

public class MskIamConsumer {
    public static void main(String[] args) {
        String bootstrapServers =
            System.getenv("MSK_BOOTSTRAP_SERVERS");

        Properties props = new Properties();
        props.put("bootstrap.servers", bootstrapServers);
        props.put("group.id", "orders-reader");
        props.put("auto.offset.reset", "earliest");
        props.put("enable.auto.commit", "false");
        props.put("key.deserializer",
            "org.apache.kafka.common.serialization.StringDeserializer");
        props.put("value.deserializer",
            "org.apache.kafka.common.serialization.StringDeserializer");

        props.put("security.protocol", "SASL_SSL");
        props.put("sasl.mechanism", "AWS_MSK_IAM");
        props.put("sasl.jaas.config",
            "software.amazon.msk.auth.iam.IAMLoginModule required;");
        props.put("sasl.client.callback.handler.class",
            "software.amazon.msk.auth.iam.IAMClientCallbackHandler");

        try (KafkaConsumer<String, String> consumer =
                 new KafkaConsumer<>(props)) {
            consumer.subscribe(Collections.singletonList("orders"));

            while (true) {
                ConsumerRecords<String, String> records =
                    consumer.poll(Duration.ofSeconds(1));

                for (ConsumerRecord<String, String> record : records) {
                    System.out.printf(
                        "topic=%s partition=%d offset=%d key=%s value=%s%n",
                        record.topic(),
                        record.partition(),
                        record.offset(),
                        record.key(),
                        record.value()
                    );
                }

                if (!records.isEmpty()) {
                    consumer.commitSync();
                }
            }
        }
    }
}
~~~

This is a learning example for connecting and reading messages. Production applications must add shutdown handling, bounded retries, error-type-aware handling, business-aligned offset commits, and consumer rebalance management.

## 8. IAM Access Control for Non-Java Clients

Non-Java clients use the `OAUTHBEARER` SASL mechanism. AWS provides MSK auth token-signing libraries for languages such as Python, JavaScript, Go, and .NET.

Execution flow:

1. The client obtains AWS credentials from the environment or workload role.
2. The signer library generates an IAM token for the cluster's Region.
3. The Kafka client supplies the token via SASL/OAUTHBEARER.
4. The broker verifies the token and evaluates IAM policies.

Python example following the `kafka-python` and AWS signer pattern:

~~~python
import socket
from kafka import KafkaProducer
from aws_msk_iam_sasl_signer import MSKAuthTokenProvider

AWS_REGION = "ap-southeast-1"
BOOTSTRAP_SERVERS = "replace-with-iam-bootstrap-brokers"

class MskTokenProvider:
    def token(self):
        token, expiry_ms = MSKAuthTokenProvider.generate_auth_token(
            AWS_REGION
        )
        return token

producer = KafkaProducer(
    bootstrap_servers=BOOTSTRAP_SERVERS,
    security_protocol="SASL_SSL",
    sasl_mechanism="OAUTHBEARER",
    sasl_oauth_token_provider=MskTokenProvider(),
    client_id=socket.gethostname()
)

try:
    producer.send(
        "orders",
        key=b"order-1001",
        value=b'{"orderId":"order-1001","status":"CREATED"}'
    ).get()
    producer.flush()
finally:
    producer.close()
~~~

The token provider API and Kafka client parameters depend on library versions. Follow the signer's Getting Started example for your exact language and client library version. Do not persist tokens long-term: tokens expire and must be regenerated when the client re-authenticates.

## 9. IAM Authorization Policies and Kafka Resource ARNs

IAM data-plane policies use four resource types:

| Resource | ARN format |
|---|---|
| Cluster | `arn:aws:kafka:region:account-id:cluster/cluster-name/cluster-uuid` |
| Topic | `arn:aws:kafka:region:account-id:topic/cluster-name/cluster-uuid/topic-name` |
| Consumer group | `arn:aws:kafka:region:account-id:group/cluster-name/cluster-uuid/group-name` |
| Transactional ID | `arn:aws:kafka:region:account-id:transactional-id/cluster-name/cluster-uuid/transactional-id` |

Example cluster ARN:

~~~text
arn:aws:kafka:ap-southeast-1:123456789012:cluster/orders-prod/abcd1234-0123-abcd-5678-1234abcd-1
~~~

The topic ARN must include the exact same cluster name and UUID:

~~~text
arn:aws:kafka:ap-southeast-1:123456789012:topic/orders-prod/abcd1234-0123-abcd-5678-1234abcd-1/orders
~~~

Do not confuse a cluster ARN with a topic ARN. Use the `*` wildcard to broaden scope only with clear justification. Policies for topic `orders` should scope to that specific topic rather than granting `topic/*` across the entire cluster.

## 10. Least-Privilege Policy for Producers

A producer writes messages to topic `orders`. It needs permission to connect to the cluster and describe/write data to that topic.

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ConnectToOrdersCluster",
      "Effect": "Allow",
      "Action": [
        "kafka-cluster:Connect"
      ],
      "Resource": [
        "arn:aws:kafka:ap-southeast-1:123456789012:cluster/orders-prod/abcd1234-0123-abcd-5678-1234abcd-1"
      ]
    },
    {
      "Sid": "WriteOrdersTopic",
      "Effect": "Allow",
      "Action": [
        "kafka-cluster:DescribeTopic",
        "kafka-cluster:WriteData"
      ],
      "Resource": [
        "arn:aws:kafka:ap-southeast-1:123456789012:topic/orders-prod/abcd1234-0123-abcd-5678-1234abcd-1/orders"
      ]
    }
  ]
}
~~~

This policy does not grant topic creation or deletion permissions. A producer that only publishes messages should not receive `kafka-cluster:*` or cluster administrative permissions by default.

## 11. Least-Privilege Policy for Consumers

A consumer reads topic `orders` using consumer group `orders-reader`. Beyond reading the topic, it needs permission to join the group and update offsets.

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ConnectToOrdersCluster",
      "Effect": "Allow",
      "Action": [
        "kafka-cluster:Connect"
      ],
      "Resource": [
        "arn:aws:kafka:ap-southeast-1:123456789012:cluster/orders-prod/abcd1234-0123-abcd-5678-1234abcd-1"
      ]
    },
    {
      "Sid": "ReadOrdersTopic",
      "Effect": "Allow",
      "Action": [
        "kafka-cluster:DescribeTopic",
        "kafka-cluster:ReadData"
      ],
      "Resource": [
        "arn:aws:kafka:ap-southeast-1:123456789012:topic/orders-prod/abcd1234-0123-abcd-5678-1234abcd-1/orders"
      ]
    },
    {
      "Sid": "UseOrdersConsumerGroup",
      "Effect": "Allow",
      "Action": [
        "kafka-cluster:DescribeGroup",
        "kafka-cluster:AlterGroup"
      ],
      "Resource": [
        "arn:aws:kafka:ap-southeast-1:123456789012:group/orders-prod/abcd1234-0123-abcd-5678-1234abcd-1/orders-reader"
      ]
    }
  ]
}
~~~

`ReadData` requires dependent actions defined by MSK, including `Connect`, `DescribeTopic`, and `AlterGroup`. `AlterGroup` lets the client join the group and update associated state/offsets. If the consumer uses a different group ID, the group ARN in the policy must match.

## 12. Common Kafka Data-Plane Permissions

| Need | Actions to evaluate | Resource |
|---|---|---|
| Connect to cluster | `kafka-cluster:Connect` | Cluster |
| Describe topic | `kafka-cluster:DescribeTopic` | Topic |
| Write messages | `kafka-cluster:WriteData` | Topic |
| Read messages | `kafka-cluster:ReadData` | Topic |
| Create topic | `kafka-cluster:CreateTopic` | Topic |
| Alter topic | `kafka-cluster:AlterTopic` | Topic |
| Delete topic | `kafka-cluster:DeleteTopic` | Topic |
| Describe consumer group | `kafka-cluster:DescribeGroup` | Group |
| Join/update group | `kafka-cluster:AlterGroup` | Group |
| Delete group | `kafka-cluster:DeleteGroup` | Group |
| Use transactional ID | `kafka-cluster:DescribeTransactionalId`, `kafka-cluster:AlterTransactionalId` | Transactional ID |
| Alter cluster | `kafka-cluster:AlterCluster` | Cluster |

Some actions require companion actions. For example, `AlterTopic` requires `Connect` and `DescribeTopic`; `AlterGroup` requires `Connect` and `DescribeGroup`. Always cross-check AWS's Required actions table when writing policies.

`kafka-cluster:*Topic*` does not include every action containing the word `Topic`. Per AWS definitions, this wildcard covers basic topic actions such as `CreateTopic`, `DescribeTopic`, `AlterTopic`, and `DeleteTopic`, but excludes dynamic configuration actions. Do not use wildcards as a substitute for reading the required actions list.

## 13. Idempotence and Transactions with IAM

Idempotent producers reduce duplicate writes during retries. Transactional producers can write atomically across multiple partitions and combine offsets in certain processing flows.

When using IAM:

- Idempotent writes require `kafka-cluster:WriteDataIdempotently` at the cluster scope alongside required connect/write permissions.
- Transactions require describe and alter permissions on the corresponding transactional ID resource.
- Starting in Kafka 2.8 and newer, `enable.idempotence` is enabled by default; IAM has certain differences from Kafka ACLs when scoping `WriteData` to a specific topic.
- AWS specifies that IAM access control supports the `WriteTxnMarkers` API to complete transactions on Kafka 3.8 and newer clusters. On versions prior to 3.8, this internal action is not supported by IAM; evaluate SCRAM or mTLS with ACLs if workloads rely on transactions.

Example policy requiring a dedicated transactional ID:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ConnectAndEnableIdempotentWrites",
      "Effect": "Allow",
      "Action": [
        "kafka-cluster:Connect",
        "kafka-cluster:WriteDataIdempotently"
      ],
      "Resource": [
        "arn:aws:kafka:ap-southeast-1:123456789012:cluster/orders-prod/abcd1234-0123-abcd-5678-1234abcd-1"
      ]
    },
    {
      "Sid": "WriteOrders",
      "Effect": "Allow",
      "Action": [
        "kafka-cluster:DescribeTopic",
        "kafka-cluster:WriteData"
      ],
      "Resource": [
        "arn:aws:kafka:ap-southeast-1:123456789012:topic/orders-prod/abcd1234-0123-abcd-5678-1234abcd-1/orders"
      ]
    },
    {
      "Sid": "UseOrderTransactions",
      "Effect": "Allow",
      "Action": [
        "kafka-cluster:DescribeTransactionalId",
        "kafka-cluster:AlterTransactionalId"
      ],
      "Resource": [
        "arn:aws:kafka:ap-southeast-1:123456789012:transactional-id/orders-prod/abcd1234-0123-abcd-5678-1234abcd-1/orders-writer-*"
      ]
    }
  ]
}
~~~

This is an illustrative template. Verify dependent action requirements and your running Kafka version. Do not grant cluster-wide transactional ID permissions if a producer only needs a single ID namespace.

## 14. IAM Control-Plane Policy for Operators

An administrative role or CI/CD pipeline may need to inspect cluster metadata and fetch bootstrap brokers. This is a separate policy from produce/consume permissions.

Example permitting only cluster description and bootstrap broker retrieval:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadOrdersClusterMetadata",
      "Effect": "Allow",
      "Action": [
        "kafka:DescribeCluster",
        "kafka:DescribeClusterV2",
        "kafka:GetBootstrapBrokers"
      ],
      "Resource": [
        "arn:aws:kafka:ap-southeast-1:123456789012:cluster/orders-prod/abcd1234-0123-abcd-5678-1234abcd-1"
      ]
    }
  ]
}
~~~

If a pipeline creates a cluster with a custom configuration, AWS evaluates `kafka:CreateCluster` or `kafka:CreateClusterV2` against both the cluster resource and the configuration resource. A policy permitting only the cluster ARN can raise `AccessDeniedException` on the configuration ARN. Separate cluster creation statements and supply matching resources per the control-plane policy documentation.

## 15. SASL/SCRAM with AWS Secrets Manager

SASL/SCRAM authenticates clients via username/password. MSK stores credentials in AWS Secrets Manager and periodically syncs associated credentials to the cluster. SCRAM uses a challenge-response mechanism and never sends plaintext passwords over the wire; MSK enforces TLS for client-broker traffic when SCRAM is configured.

Requirements when creating the secret:

- Choose secret type `Other type of secrets`.
- The secret name must start with the prefix `AmazonMSK_`.
- Use a customer managed AWS KMS key; secrets encrypted with Secrets Manager's default AWS managed key cannot be associated with MSK.
- The credential JSON contains two fields: `username` and `password`.
- Record the secret ARN to associate with the cluster.

Example secret value:

~~~json
{
  "username": "orders-writer",
  "password": "replace-with-a-generated-long-random-secret"
}
~~~

Create the secret via console or AWS CLI, then associate it with the cluster via console or `BatchAssociateScramSecret`. Upon association, MSK attaches a resource policy to the secret allowing the cluster to read the credential. Do not manually alter that policy; if the policy or KMS key changes, re-associate the secret per AWS guidance.

MSK supports `SCRAM-SHA-512`. Do not use `SASL/PLAIN` with MSK. When applications retrieve credentials, read from Secrets Manager via an IAM role and inject them into the Kafka client at runtime; avoid writing usernames/passwords into source control or container images.

### 15.1. Java Client Properties for SCRAM

~~~properties
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="INJECT_USERNAME" password="INJECT_PASSWORD";
~~~

`INJECT_USERNAME` and `INJECT_PASSWORD` are placeholder values. Applications must read the secret using a role granted `secretsmanager:GetSecretValue` on the exact secret ARN, then assemble the client configuration securely. Never commit files containing real credentials.

With SCRAM, topic/group authorization relies on Apache Kafka ACLs. Create ACLs first and configure `allow.everyone.if.no.acl.found=false` so resources without ACLs are not open to every principal by default. Plan this change carefully because it affects all clients using the cluster.

## 16. Mutual TLS (mTLS) with AWS Private CA

mTLS requires clients to present a certificate during the TLS handshake. MSK verifies the certificate chain against the AWS Private CA configured on the cluster. The CA can reside in the same account or another account.

General workflow:

1. Create or select an AWS Private CA dedicated to the MSK cluster.
2. The client generates a private key and CSR.
3. AWS Private CA signs the certificate.
4. The client stores the private key and certificate chain in a keystore.
5. The client trusts broker certificates via a truststore.
6. The Kafka client connects using `security.protocol=SSL`.
7. Apache Kafka ACLs determine which topics the certificate principal may read or write.

AWS recommends using an independent Private CA per MSK cluster so certificates from one cluster are not inadvertently accepted by another cluster.

### 16.1. Client Properties for mTLS

~~~properties
security.protocol=SSL
ssl.truststore.location=/secure/path/kafka.client.truststore.jks
ssl.keystore.location=/secure/path/kafka.client.keystore.p12
ssl.keystore.type=PKCS12
ssl.keystore.password=INJECT_STORE_PASSWORD
ssl.key.password=INJECT_KEY_PASSWORD
~~~

Protect private keys, keystores, and passwords as secrets. Never bake keystores into public images or repositories. Establish procedures for issuance, rotation, expiration, and compromised-certificate response.

### 16.2. Certificate Revocation Limitations

Amazon MSK does not support Certificate Revocation Lists (CRLs) for mTLS. To block a compromised client certificate, prepare an operational revocation plan: update trust boundaries/CAs per procedure, adjust Kafka ACLs and security groups, rotate certificates, and audit active connections. Never assume deleting a certificate in ACM automatically causes brokers to reject already-issued certificates.

With mTLS, the principal can be mapped from the Distinguished Name, such as `User:CN=orders-writer`. Kafka ACLs must match the exact principal recognized by the broker.

## 17. Comparing IAM, SCRAM, and mTLS

| Criterion | IAM | SASL/SCRAM | mTLS |
|---|---|---|---|
| Identity | IAM user/role | Username/password | Client certificate |
| Credential store | AWS credential provider chain | Secrets Manager | Keystore/PKI |
| Authorization | IAM data-plane policies | Kafka ACLs | Kafka ACLs |
| Rotation | Temporary credentials auto-refresh | Rotate secret and sync user | Renew/reissue certificate |
| Fit for AWS workloads | Strong fit | Fits when user/password is required | Fits when PKI already exists |
| Fit for non-AWS clients | Possible via federation/roles | Possible | Possible |
| MSK Serverless | Required | Not supported | Not supported |
| Topic permission governance | IAM resource policies | Kafka ACLs | Kafka ACLs |

IAM is usually the simplest option for workloads running on AWS because it leverages roles and temporary credentials. SCRAM fits when an organization already operates user/password workflows. mTLS fits when device or application identities are governed via PKI.

## 18. Encryption in Transit and Encryption at Rest

Amazon MSK always encrypts data at rest using AWS KMS. At cluster creation, you can select a customer managed key; otherwise, MSK uses an AWS managed key.

For data in transit:

- TLS 1.2 is the default configuration published by MSK.
- MSK Provisioned can use a TLS security policy to enable TLS 1.3 where supported.
- IAM and SASL/SCRAM require TLS for client-broker traffic.
- mTLS also uses TLS along with client certificates.
- Never open a plaintext listener for production workloads just to work around a client error.

Broker-to-broker encryption is a separate setting. Do not confuse encryption at rest with client-to-broker TLS. Data encrypted on disk can still traverse a plaintext connection if the cluster permits it and a client connects to the wrong listener.

## 19. Retrieving Bootstrap Brokers Properly

Bootstrap brokers are the initial entry points a Kafka client uses to discover cluster metadata and other brokers. This list does not necessarily include every broker in the cluster. Never construct endpoints manually by concatenating hostnames or guessing ports.

Retrieve them via the AWS CLI:

~~~bash
aws kafka get-bootstrap-brokers --cluster-arn "$MSK_CLUSTER_ARN"
~~~

For a cluster using IAM, read the `BootstrapBrokerStringSaslIam` field:

~~~bash
aws kafka get-bootstrap-brokers \
  --cluster-arn "$MSK_CLUSTER_ARN" \
  --query BootstrapBrokerStringSaslIam \
  --output text
~~~

Common fields:

| Field | Use when |
|---|---|
| `BootstrapBrokerStringTls` | Client uses the TLS listener |
| `BootstrapBrokerStringSaslScram` | Client uses SASL/SCRAM |
| `BootstrapBrokerStringSaslIam` | Client uses SASL/IAM |
| `BootstrapBrokerStringPublicTls` | Client connects publicly over TLS |
| `BootstrapBrokerStringPublicSaslScram` | Client connects publicly over SCRAM |
| `BootstrapBrokerStringPublicSaslIam` | Client connects publicly over IAM |
| `BootstrapBrokerStringVpcConnectivityTls` | Client uses multi-VPC private connectivity with TLS |
| `BootstrapBrokerStringVpcConnectivitySaslScram` | Client uses multi-VPC private connectivity with SCRAM |
| `BootstrapBrokerStringVpcConnectivitySaslIam` | Client uses multi-VPC private connectivity with IAM |

If public access is enabled on the cluster, use the matching Public field for clients outside the VPC. Never use a public bootstrap string for internal workloads when a private endpoint is available.

## 20. Ports and Network Rules by Listener

Common ports for MSK Provisioned:

| Method | Access inside AWS | Public access |
|---|---:|---:|
| Plaintext | 9092 | Not recommended |
| TLS | 9094 | 9194 |
| SASL/SCRAM | 9096 | 9196 |
| SASL/IAM | 9098 | 9198 |

MSK has separate ports for IPv6. When using dual-stack, retrieve the matching IPv6 bootstrap string and check ports in the port information documentation.

Broker security groups must allow inbound traffic from client security groups on the active listener port. For IAM, for example, allow TCP 9098 from the client security group. Never open all ports or `0.0.0.0/0` just to fix timeouts.

Clients must be able to resolve broker DNS names and connect to every broker returned by the cluster after bootstrapping. A successful TCP test to one bootstrap broker does not prove every broker is reachable. Check route tables, DNS, security groups, network ACLs, intermediate firewalls, and client outbound rules.

## 21. Connecting to MSK Provisioned Within the Same VPC

By default, an MSK Provisioned cluster is accessed privately from clients in the same VPC. Minimum setup:

1. Place EC2/ECS/EKS clients in a VPC with routing to MSK brokers.
2. Attach a security group to the client.
3. In the broker security group, allow inbound TCP from the client security group on the auth listener's port.
4. Ensure DNS resolution and network ACLs do not block traffic.
5. Retrieve the bootstrap broker string matching the authentication method.
6. Configure client properties.
7. Verify `get-caller-identity` and test a Kafka operation on a permitted topic.

IAM listener example: the broker security group allows TCP 9098 from the client security group. For SCRAM, the in-AWS listener is typically 9096; for mTLS/TLS, it is 9094.

Do not use one broad rule for all workloads. Separate security groups per service, such as `sg-orders-producer` and `sg-orders-consumer`, and grant specific inbound rules.

## 22. Multi-VPC Private Connectivity and Cross-Account Access

Amazon MSK supports multi-VPC private connectivity via AWS PrivateLink so clients in other VPCs/accounts can connect privately to a cluster. This is helpful when VPCs have overlapping CIDRs or when organizations want to avoid complex peering and routing management.

Key details to remember:

- Supports Kafka 2.7.1 and newer.
- Supports IAM, TLS/mTLS, and SASL/SCRAM; does not support unauthenticated access.
- Multi-VPC connectivity operates within the same AWS Region, not cross-Region.
- Does not support multi-VPC connections to ZooKeeper.
- Does not support `t3.small` in multi-VPC configurations.
- The client VPC needs matching subnets and Availability Zone IDs aligned with the cluster per service guidelines.

General workflow:

1. The cluster owner enables multi-VPC connectivity for the chosen authentication scheme.
2. The cluster owner attaches a cluster policy for external accounts/principals.
3. The client account creates a managed VPC connection and endpoint per guidelines.
4. The client role holds permissions to create VPC connections and required EC2 endpoint resources.
5. Retrieve the VPC connectivity bootstrap broker string.
6. Configure the client with an authentication scheme permitted by the cluster.

## 23. MSK Cluster Policy for Cross-Account Access

A cluster policy is a resource-based policy attached to an MSK cluster. It lets another account establish private connectivity; when using IAM client authentication, the cluster policy can also grant Kafka data-plane permissions to connecting principals.

Condensed example allowing Account B to connect to a cluster in Account A:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "123456789012"
      },
      "Action": [
        "kafka:CreateVpcConnection",
        "kafka:GetBootstrapBrokers",
        "kafka:DescribeCluster",
        "kafka:DescribeClusterV2"
      ],
      "Resource": "arn:aws:kafka:ap-southeast-1:111122223333:cluster/orders-prod/abcd1234-0123-abcd-5678-1234abcd-1"
    },
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "123456789012"
      },
      "Action": [
        "kafka-cluster:Connect"
      ],
      "Resource": "arn:aws:kafka:ap-southeast-1:111122223333:cluster/orders-prod/abcd1234-0123-abcd-5678-1234abcd-1"
    },
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "123456789012"
      },
      "Action": [
        "kafka-cluster:DescribeTopic",
        "kafka-cluster:ReadData"
      ],
      "Resource": "arn:aws:kafka:ap-southeast-1:111122223333:topic/orders-prod/abcd1234-0123-abcd-5678-1234abcd-1/orders"
    }
  ]
}
~~~

This is an illustrative example; production policies must restrict specific accounts, roles, topics, and groups. The client account also needs identity policy permissions for `kafka:CreateVpcConnection`, `ec2:CreateTags`, `ec2:CreateVPCEndpoint`, and `ec2:DescribeVpcAttribute` per connectivity instructions. Cluster policies have a size limit; keep policies concise and track versions on updates.

## 24. MSK Serverless and IAM

MSK Serverless requires IAM access control on every cluster. Serverless does not support Apache Kafka ACLs; authorization is handled via IAM policies.

Consequences:

- Java clients can use `AWS_MSK_IAM` or documented IAM mechanisms.
- Non-Java clients use `SASL_OAUTHBEARER`.
- Roles need permissions scoped by cluster, topic, and group ARNs.
- Certain actions do not apply to Serverless, such as `kafka-cluster:AlterCluster` and dynamic cluster configuration actions.
- Provisioned SCRAM or mTLS guides cannot be applied to Serverless.

Retrieve endpoints via the cluster's `View client information` section or the appropriate API. Use the bootstrap string returned by MSK and policy actions marked as Serverless-supported in the IAM action reference.

## 25. Protecting Credentials, Secrets, and Certificates

Kafka credentials are the gateway to streaming data. Manage their lifecycle with clear owners and applications.

With IAM:

- Give each producer/consumer its own service-scoped role.
- Prefer temporary credentials and workload identity.
- Avoid long-lived IAM user access keys whenever roles can be used.
- Revoke access via policies/roles and monitor changes.
- Scope permissions to specific topics, groups, and transactional IDs.

With SCRAM:

- Generate strong random passwords.
- Store them in Secrets Manager with a customer managed KMS key.
- Separate users per workload; avoid sharing one credential across all applications.
- Rotate secrets per schedule and account for MSK credential sync times.
- Never log secrets or pass passwords on command lines in shared environments.

With mTLS:

- Protect private keys.
- Issue distinct certificates per workload or trust boundary.
- Monitor expiration and automate renewal/reissuance.
- Maintain a runbook for compromised certificates since MSK does not support CRLs.
- Use Kafka ACLs and security groups to constrain permissions and network access.

## 26. Auditing and Security Operations

A production system must be able to answer: which principal connected, from which workload, to which cluster, and what actions it could perform.

Recommended controls:

- CloudTrail to log MSK API calls and certain Kafka administrative actions. CloudTrail integration for Amazon MSK requires a cluster using IAM access control; events cover MSK APIs and certain Kafka actions such as creating, altering, or deleting topics.
- For Standard and Express brokers, enable broker logs to analyze client-cluster communication; enable authorizer logs to record authorization decisions and aid permission troubleshooting. Logs can be sent to CloudWatch Logs, S3, or Amazon Data Firehose.
- IAM Access Analyzer and policy reviews to spot unintended cross-account/external access.
- AWS Config/Security Hub controls to flag clusters with unauthenticated access or non-compliant security settings.
- Inventory of cluster ARNs, listeners, ports, auth schemes, owners, and data classifications.
- Change approval workflows for IAM policies, cluster policies, ACLs, certificates, and Secrets Manager resource policies.

Do not enable overly verbose logging without retention and cost modeling. Ensure logs never record passwords, tokens, or sensitive message payloads.

## 27. End-to-End Connectivity and Testing Workflow

Use a non-production environment and a test topic to verify each layer.

~~~mermaid
flowchart TD
    A[Obtain cluster ARN and auth scheme] --> B[Fetch bootstrap brokers]
    B --> C[Check DNS, routing, and TCP port]
    C --> D[Verify IAM identity or SCRAM/mTLS credentials]
    D --> E[Check policies / ACLs]
    E --> F[Run Kafka CLI producer]
    F --> G[Run Kafka CLI consumer]
    G --> H[Verify offsets, group, and logs]
~~~

### 27.1. Retrieving IAM Bootstrap Brokers

~~~bash
aws kafka get-bootstrap-brokers \
  --cluster-arn "$MSK_CLUSTER_ARN" \
  --query BootstrapBrokerStringSaslIam \
  --output text
~~~

Store the output in the client's `MSK_BOOTSTRAP_SERVERS` variable. Use the IAM broker string matching your chosen private or public environment.

### 27.2. Checking Network Reachability

From the client, verify DNS resolution for every broker in the bootstrap string. Check TCP connectivity to port 9098 for the in-AWS IAM listener. Tools like `nc` or `Test-NetConnection` verify only TCP reachability, not IAM policies or Kafka authorization.

### 27.3. Using the Kafka CLI

With the Kafka CLI having the IAM plugin library on its classpath and `client.properties` configured:

~~~bash
kafka-topics.sh --bootstrap-server "$MSK_BOOTSTRAP_SERVERS" --list --command-config client.properties
~~~

Create a topic only when the role holds permission and procedures allow:

~~~bash
kafka-topics.sh --bootstrap-server "$MSK_BOOTSTRAP_SERVERS" --create --topic msk-auth-lab --partitions 3 --replication-factor 3 --command-config client.properties
~~~

Produce:

~~~bash
kafka-console-producer.sh --bootstrap-server "$MSK_BOOTSTRAP_SERVERS" --topic msk-auth-lab --producer.config client.properties
~~~

Consume:

~~~bash
kafka-console-consumer.sh --bootstrap-server "$MSK_BOOTSTRAP_SERVERS" --topic msk-auth-lab --from-beginning --consumer.config client.properties
~~~

If the policy does not grant `CreateTopic`, use a topic pre-created by an administrator. Never grant administrative permissions just to run a lab.

## 28. Symptom-Based Troubleshooting

| Symptom | Layer to inspect | Remediation |
|---|---|---|
| DNS lookup fails | DNS/VPC | Check private DNS, resolvers, routes, and that bootstrap string matches cluster/Region |
| Connection timeout | Network | Check SG inbound/outbound, NACLs, routes, firewalls, and listener port |
| Connection refused | Endpoint/port | Match port against auth scheme and bootstrap broker field |
| TLS handshake failure | TLS | Check listener, truststore, keystore, certificate chain, protocol, and system clock |
| `SaslAuthenticationException` | Authentication | Check IAM credentials, token-signing Region, SASL mechanism, plugin/classpath, or SCRAM credentials |
| `TopicAuthorizationException` | Topic authorization | Check topic ARN, `DescribeTopic`, `WriteData`, or `ReadData` |
| `GroupAuthorizationException` | Consumer group | Check `DescribeGroup`, `AlterGroup`, and group ARN |
| `ClusterAuthorizationException` | Cluster authorization | Check `Connect` and cluster ARN |
| Cannot retrieve bootstrap brokers | Control plane | Check `kafka:GetBootstrapBrokers`, `kafka:DescribeCluster`, and cluster ARN |
| Consumer cannot read after Connect succeeds | Data plane/group | Check topic read, group permissions, offsets, and subscriptions |
| Producer transaction cannot finish | Kafka version/transactions | Check Kafka version, transactional ID actions, and `WriteTxnMarkers` limits |

### 28.1. Distinguishing Authentication and Authorization Errors

- `SaslAuthenticationException` usually occurs when the broker cannot validate credentials or the SASL mechanism.
- `TopicAuthorizationException` usually indicates the client authenticated successfully but was denied permissions on the topic.
- `GroupAuthorizationException` usually relates to the group ARN or group permissions.
- `TimeoutException` warrants checking network reachability and broker availability before editing policies.

If you just updated an IAM policy, wait for propagation and retry. AWS notes that IAM policy changes typically take effect in under a minute, though network conditions can delay propagation.

### 28.2. Errors from Mismatched Listeners

Common mistakes:

- Using port 9094 while configuring `SASL_SSL` and the IAM mechanism.
- Passing `BootstrapBrokerStringTls` to a SCRAM client.
- Using a public broker string from a VPC client intending private connectivity.
- Using an IAM bootstrap string without `aws-msk-iam-auth` on the classpath.
- Configuring `AWS_MSK_IAM` on a Python client instead of `OAUTHBEARER`.

Verify bootstrap field, port, `security.protocol`, and `sasl.mechanism` together as one consistent set.

## 29. Case Study: Separating Producers and Consumers for an Order System

An e-commerce platform has two applications:

- `checkout-service` writes `OrderCreated` events to topic `orders`.
- `fulfillment-service` reads topic `orders` using consumer group `fulfillment-workers`.

Security design:

1. Both applications run on ECS with separate task roles.
2. The MSK Provisioned cluster enables IAM authentication and TLS.
3. The broker security group accepts traffic only from the ECS services' security groups on port 9098.
4. The producer role holds only `Connect`, `DescribeTopic`, and `WriteData` on topic `orders`.
5. The consumer role holds only `Connect`, `DescribeTopic`, `ReadData` on topic `orders`, and `DescribeGroup`/`AlterGroup` on group `fulfillment-workers`.
6. Cluster ARN, topic ARN, and group ARN are injected into policies via IaC.
7. CloudTrail tracks control-plane operations; broker logs and application metrics support troubleshooting.
8. The consumer processes messages idempotently by order ID to avoid duplicate side effects on retries.

When the fulfillment team later needs to read a `returns` topic, they submit a scoped policy change. Never grant `kafka-cluster:*` merely to silence an authorization error quickly.

## 30. Production Readiness Checklist

### Cluster and Network

- [ ] Cluster has appropriate authentication enabled; no unauthenticated listeners outside test environments.
- [ ] Client-broker encryption is enabled.
- [ ] Bootstrap broker string is fetched from MSK API/console and matches the auth scheme.
- [ ] Security groups permit only identified client sources.
- [ ] DNS, routes, NACLs, and firewalls allow clients to reach all required brokers.
- [ ] Public access is disabled if workloads only need private connectivity.

### IAM and Authorization

- [ ] Workloads use IAM roles or appropriate credential providers.
- [ ] Producers and consumers use separate roles.
- [ ] Policies use `kafka-cluster:` for the data plane and `kafka:` for the control plane.
- [ ] Cluster/topic/group/transactional ID ARNs are verified accurately.
- [ ] No broad wildcards granted without clear justification.
- [ ] Transactional/idempotent producers verified against Kafka version and dependent permissions.
- [ ] Cross-account policies and trust policies reviewed.

### SCRAM/mTLS (If Used)

- [ ] SCRAM secrets have the `AmazonMSK_` prefix and a customer managed KMS key.
- [ ] MSK-attached secret resource policies are preserved intact.
- [ ] SCRAM users have rotation schedules and owners.
- [ ] mTLS certificates have expiration monitoring and reissuance workflows.
- [ ] Private keys are securely protected.
- [ ] Kafka ACLs match exact principals.
- [ ] For mTLS, a runbook exists for compromised certificates because MSK does not support CRLs.

### Operations

- [ ] Producer/consumer tests executed in non-production.
- [ ] Alerts configured for authentication/authorization failures and connection errors.
- [ ] Appropriate log retention and access controls in place.
- [ ] Review process established for IAM policies and cluster policies.
- [ ] Credential/certificate rotation and incident response plans documented.
- [ ] Clients configure multiple bootstrap brokers to support failover.
- [ ] Consumer groups, offsets, retries, and dead-letter strategies tested.

## 31. Self-Check Exercises

### Question 1

Which two things does MSK IAM authentication handle?

**Answer:** Authenticating the IAM principal and authorizing Kafka data-plane operations via IAM policies.

### Question 2

What is the difference between `kafka:` and `kafka-cluster:`?

**Answer:** `kafka:` governs MSK management APIs such as `DescribeCluster`/`GetBootstrapBrokers`; `kafka-cluster:` governs Kafka operations such as `Connect`, `ReadData`, and `WriteData`.

### Question 3

A producer only needs to write to topic `orders`. Should you grant `kafka-cluster:*` or `Connect`, `DescribeTopic`, and `WriteData` on the specific topic ARN?

**Answer:** Grant only the required actions on the specific cluster/topic ARNs following least privilege.

### Question 4

Why does a consumer need permissions on the group ARN?

**Answer:** A consumer must join the group and update offsets/group state; these operations are controlled by `DescribeGroup` and `AlterGroup`.

### Question 5

Which IAM mechanism do Java clients use?

**Answer:** They can use custom `AWS_MSK_IAM` or `SASL_OAUTHBEARER`; the custom mechanism requires the `aws-msk-iam-auth` library.

### Question 6

Which mechanism do Python clients use for IAM access control?

**Answer:** `SASL/OAUTHBEARER` with a signer library generating MSK auth tokens for the target AWS Region.

### Question 7

What is port 9098 typically used for?

**Answer:** The `SASL/IAM` listener for clients accessing MSK inside AWS. The public IAM listener uses port 9198 when public access is enabled.

### Question 8

How do ports 9096 and 9094 differ?

**Answer:** 9096 is the `SASL/SCRAM` listener; 9094 is the `TLS` listener.

### Question 9

What prefix and KMS key type are required for an MSK SASL/SCRAM secret?

**Answer:** The secret name must start with `AmazonMSK_` and be encrypted with a customer managed KMS key; Secrets Manager's default AWS managed key cannot be associated.

### Question 10

Does MSK Serverless support Kafka ACLs?

**Answer:** No. MSK Serverless requires IAM access control and does not support Apache Kafka ACLs.

### Question 11

Does MSK support CRLs for mTLS?

**Answer:** No. Use Kafka ACLs, security groups, and certificate replacement/reissuance workflows to handle compromised certificates.

### Question 12

If `get-bootstrap-brokers` succeeds but the producer times out, what should you check?

**Answer:** Check DNS, routes, security groups, NACLs, firewalls, and reachability to every broker on the right listener port. Retrieving the bootstrap string only proves the control-plane API returned the endpoints.

### Question 13

If a producer receives `TopicAuthorizationException`, which actions should you inspect?

**Answer:** Check `Connect`, `DescribeTopic`, `WriteData`, and the topic ARN; also check for explicit `Deny` statements or permission boundaries/SCPs.

### Question 14

Why should internal workloads avoid public bootstrap strings?

**Answer:** Internal workloads should use private endpoints over controlled network paths; public listeners expand the exposure surface and depend on public access settings.

### Question 15

Can MSK multi-VPC private connectivity connect across Regions?

**Answer:** No. Multi-VPC private connectivity for MSK applies between VPCs/accounts within the same Region.

### Question 16

On Kafka versions prior to 3.8, does IAM support `WriteTxnMarkers` to complete transactions?

**Answer:** No. AWS documentation states support for this API starts in Kafka 3.8 and newer; older versions must evaluate SCRAM or mTLS with ACLs if workloads require transaction termination.

## 32. Official References

- [IAM access control for Amazon MSK](https://docs.aws.amazon.com/msk/latest/developerguide/iam-access-control.html)
- [How IAM access control for Amazon MSK works](https://docs.aws.amazon.com/msk/latest/developerguide/how-to-use-iam-access-control.html)
- [Configure clients for IAM access control](https://docs.aws.amazon.com/msk/latest/developerguide/configure-clients-for-iam-access-control.html)
- [Create authorization policies for the IAM role](https://docs.aws.amazon.com/msk/latest/developerguide/create-iam-access-control-policies.html)
- [Common use cases for client authorization policy](https://docs.aws.amazon.com/msk/latest/developerguide/iam-access-control-use-cases.html)
- [Semantics of IAM authorization policy actions and resources](https://docs.aws.amazon.com/msk/latest/developerguide/kafka-actions.html)
- [Get the bootstrap brokers for an Amazon MSK cluster](https://docs.aws.amazon.com/msk/latest/developerguide/msk-get-bootstrap-brokers.html)
- [Get the bootstrap brokers using the AWS CLI](https://docs.aws.amazon.com/msk/latest/developerguide/get-bootstrap-cli.html)
- [Port information for Amazon MSK](https://docs.aws.amazon.com/msk/latest/developerguide/port-info.html)
- [Sign-in credentials authentication with AWS Secrets Manager](https://docs.aws.amazon.com/msk/latest/developerguide/msk-password.html)
- [Set up SASL/SCRAM authentication for an Amazon MSK cluster](https://docs.aws.amazon.com/msk/latest/developerguide/msk-password-tutorial.html)
- [Mutual TLS client authentication for Amazon MSK](https://docs.aws.amazon.com/msk/latest/developerguide/msk-authentication.html)
- [Set up a client to use authentication](https://docs.aws.amazon.com/msk/latest/developerguide/msk-authentication-client.html)
- [Apache Kafka ACLs in Amazon MSK](https://docs.aws.amazon.com/msk/latest/developerguide/msk-acls.html)
- [Amazon MSK encryption](https://docs.aws.amazon.com/msk/latest/developerguide/msk-encryption.html)
- [Amazon MSK logging and authorizer logs](https://docs.aws.amazon.com/msk/latest/developerguide/msk-logging.html)
- [Log Amazon MSK API calls and Kafka actions with CloudTrail](https://docs.aws.amazon.com/msk/latest/developerguide/logging-API-using-cloudtrail.html)
- [Connect to an Amazon MSK Provisioned cluster](https://docs.aws.amazon.com/msk/latest/developerguide/client-access.html)
- [Amazon MSK multi-VPC private connectivity](https://docs.aws.amazon.com/msk/latest/developerguide/aws-access-mult-vpc.html)
- [MSK Serverless](https://docs.aws.amazon.com/msk/latest/developerguide/serverless.html)
- [AWS MSK IAM authentication library releases](https://github.com/aws/aws-msk-iam-auth/releases)
- [AWS MSK IAM authentication library on Maven Central](https://central.sonatype.com/artifact/software.amazon.msk/aws-msk-iam-auth)

Features, ports, Kafka versions, and client libraries may change. Before deploying, verify current documentation, bootstrap broker strings, and the IAM action reference for your exact cluster type, Region, and Kafka version.
