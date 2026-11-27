# IAM Roles for EC2, ECS, and EKS by Deployment Environment

## 1. Context: One Application, Different Ways of Supplying Identity

A Spring Boot service needs to read objects from Amazon S3, send messages to Amazon SQS, and fetch secrets from AWS Secrets Manager. When running on a developer workstation, developers can use AWS CLI profiles and IAM Identity Center. When deployed to **Amazon EC2**, **Amazon ECS**, or **Amazon EKS**, the application should receive **temporary AWS credentials via an IAM role dedicated to the workload**.

This is core knowledge in the **AWS Platform** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module: learning how to connect Spring Boot with managed services across AWS, Azure, and Google Cloud—from identity and permissions to storage, messaging, data, secrets, testing, and provider comparison. This lesson examines how to grant AWS permissions properly for each application runtime platform so Spring Cloud AWS labs can use IAM without embedding access keys in source code.

**After this lesson, you will be able to:**

- Explain IAM roles, trust policies, permissions policies, role sessions, and temporary credentials.
- Distinguish an **EC2 instance profile**, an **ECS task role** vs. a **task execution role**, and the two Pod identity mechanisms on **EKS: IRSA and EKS Pod Identity**.
- Decide whether to assign a role at the host, task, or Kubernetes service account level.
- Design least-privilege permissions for S3, SQS, Secrets Manager, and KMS across dev/test/prod environments.
- Verify which principal a Spring Boot/AWSpring application is using; troubleshoot `AccessDenied`, missing credentials, trust configuration, and overridden credentials.
- Structure testing and monitoring without accidentally using another account's credentials.

> **Technical scope:** This lesson focuses on AWS SDK for Java **v2** and how it is used by **AWSpring**'s Spring Cloud AWS. Example ARNs, account IDs, namespaces, queues, and buckets are illustrative only; replace them with provisioned resources and consult compatibility documentation for the service versions in use. This lesson guides models and configuration—it does not provision AWS resources automatically.

## 2. Core Concepts: How Does an IAM Role Grant Permissions?

An **IAM role** is an IAM identity that an eligible principal can **assume** to receive **temporary security credentials**. Unlike an IAM user storing long-lived access keys, a role is typically used through an **STS role session** with time-limited credentials.

An IAM role has two sides to distinguish:

1. **Trust policy:** Who/what *is allowed to assume* the role, through which mechanism, and under what conditions?
2. **Permissions policy:** Once the role is assumed, *which operations* is the session allowed to perform on which resources, and under what conditions?

Beyond those two sides, the actual authorization outcome can also be affected by **resource-based policies**, AWS Organizations **service control policies (SCPs)**, **permissions boundaries**, **session policies**, **KMS key policies**, and other access conditions. A policy stating `Allow` does not guarantee every request succeeds if an explicit deny or another constraint applies.

~~~mermaid
flowchart LR
    W["Spring Boot Workload"] --> CP["Platform credential source"]
    CP --> STS["Role session / temporary credentials"]
    T["Trust policy"] -. "Defines who can receive a role session" .-> STS
    STS --> SDK["AWS SDK for Java v2"]
    SDK --> API["S3 / SQS / Secrets Manager"]
    P["Role permissions policy"] -. "Defines actions and resources" .-> API
    R["Resource/KMS/SCP/condition"] -. "May impose further restrictions" .-> API
~~~

For example, a role trusted by the ECS service that only holds `s3:GetObject` will **not** be able to send SQS messages. Conversely, an IAM role with an `sqs:SendMessage` policy whose trust policy does not allow the right task/service account to assume it will prevent the workload from obtaining credentials for that role.

### 2.1. How Do Role, Profile, Service Account, and Instance Profile Differ?

| Term | Belongs to | Role |
| --- | --- | --- |
| IAM role | AWS IAM | Principal being assumed; permissions and trust are managed in AWS |
| STS role session | AWS STS | Session using temporary AWS credentials for a role |
| Instance profile | EC2/IAM | Mechanism attaching an IAM role to an EC2 instance so workloads obtain credentials via IMDS |
| ECS task role | ECS/IAM | Role supplying credentials to code running inside an ECS task's containers |
| ECS task execution role | ECS/IAM | Role for the ECS agent/platform to launch and run the task |
| Kubernetes service account | Kubernetes/EKS | Kubernetes identity used to link a Pod with AWS permissions via IRSA or Pod Identity |
| AWS CLI profile | Local machine config | Specifies credential source, account/role, and region; does not itself grant IAM permissions |

**A role is not an access key.** The workload receives temporary credentials from the platform/SDK mechanism. The SDK signs requests with those credentials, and AWS checks permissions when the service receives the request.

## 3. Design Principles Before Choosing EC2, ECS, or EKS

A secure deployment flow must answer five questions:

1. **Which workload needs to call AWS?** For example, `receipt-api` only writes receipts to S3 and sends SQS events; `receipt-worker` only receives events and reads objects.
2. **Which environment is it running in?** Dev, staging, and production have different accounts, roles, ARNs, regions, and data.
3. **Where does the platform supply credentials?** EC2 instance profile, ECS task credentials, EKS web identity (IRSA), or EKS Pod Identity.
4. **Which operations are needed?** `s3:PutObject` differs from `s3:ListBucket`; `sqs:SendMessage` differs from `sqs:ReceiveMessage`.
5. **What needs runtime verification?** STS principal, region, endpoint, resource ARNs, IAM/resource/KMS policies, and retry/refresh behavior.

Do not attach permissions to an overly broad role simply because multiple services share a cluster or EC2 host. The more workloads sharing a role, the larger the blast radius if a bug or credential leak occurs. With ECS, permissions are typically scoped **per task definition/service**; with EKS, **per service account**; with EC2, the instance profile represents **the entire instance**, so evaluate isolation carefully when co-locating applications.

### 3.1. Quick Comparison of Credential Provisioning

| Platform | Role to use for application code | Credential path | Scope to watch out for |
| --- | --- | --- | --- |
| EC2 | IAM role attached to **instance profile** | EC2 Instance Metadata Service (IMDS) | Any process able to reach instance credentials can assume the role's permissions |
| ECS on EC2/Fargate | **Task role** | Dedicated credential endpoint provided by ECS for the task/container | Separate permissions per task; protect task-to-host boundaries |
| EKS with IRSA | IAM role bound to a **Kubernetes service account** | Web identity token → AWS STS `AssumeRoleWithWebIdentity` | Trust policy binds cluster OIDC issuer, namespace, and service account |
| EKS with Pod Identity | IAM role associated with a **service account** via EKS association | Pod Identity Agent/credential endpoint → EKS Auth | Agent, association, SDK support, and node/agent permissions must align |

There is no separate "Spring Boot role": Spring Boot/AWSpring uses credentials supplied by the environment and AWS SDK. Defining permissions remains the job of AWS IAM and infrastructure.

## 4. EC2: IAM Roles via Instance Profiles

### 4.1. Credential Flow

When a Spring Boot application runs directly on EC2:

1. An administrator creates an IAM role with a **trust policy for EC2**.
2. The role is placed in an **instance profile** and attached to the EC2 instance.
3. The EC2 metadata service supplies temporary credentials for the instance role through IMDS.
4. AWS SDK for Java v2 can retrieve credentials via `InstanceProfileCredentialsProvider` in the default credentials chain.
5. The SDK signs requests and AWS services evaluate the role's IAM/resource policies.

~~~mermaid
flowchart TD
    EC2["EC2 instance"] --> APP["Spring Boot process"]
    EC2 --> IP["Instance profile / IAM role"]
    IP --> IMDS["IMDS: temporary credentials"]
    APP --> SDK["AWS SDK v2"]
    SDK --> IMDS
    SDK --> S3["S3 / SQS / Secrets Manager"]
~~~

### 4.2. Sample Trust Policy for EC2

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ec2.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

This policy specifies that the EC2 service may assume the role. It **does not grant** `s3:PutObject` or `sqs:SendMessage`; those permissions live in a separate permissions policy.

**An instance profile is a separate component**: during infrastructure provisioning, you must create not just the role, but also the instance profile and its association. If you create the role without attaching the right instance profile, the application on the instance will not see the expected credentials.

### 4.3. IMDS, IMDSv2, and Isolation Risks

IMDS supplies metadata and credentials to workloads on EC2. **IMDSv2** uses session tokens when accessing metadata and should be configured according to your organization's security policy. However, IMDSv2 **does not turn every process on the same instance into separate principals**: if multiple processes can access the metadata/credential endpoint, they can use the same instance role.

Notes:

- Attach an instance profile with least privilege appropriate for all workloads on the instance.
- Never allow applications to log credential contents from IMDS.
- Never expose proxies or metadata endpoints to external networks; enforce SSRF protections, firewalls, and process permissions.
- When running containers on EC2, watch whether containers can reach host IMDS if networking is not properly isolated.
- Do not assume the client will always use the instance role: environment credentials, system properties, or profiles can take precedence over IMDS in the SDK.

**When to consider another model:** if multiple services with different IAM needs share one machine, ECS task roles or EKS Pod identities typically offer cleaner granularity than a shared instance role.

## 5. ECS: Distinguishing Task Role and Task Execution Role

Amazon ECS manages tasks/containers running on EC2 or Fargate. The easiest point of confusion is **two roles serving different purposes**.

| Role type | Primary user | Permission examples |
| --- | --- | --- |
| **Task role** (`taskRoleArn` property) | Application code inside the ECS task | `s3:GetObject`, `s3:PutObject`, `sqs:SendMessage`, `secretsmanager:GetSecretValue` |
| **Task execution role** (`executionRoleArn` property) | ECS agent/platform launching the task | Pulling images from ECR, shipping logs to CloudWatch Logs, fetching secrets referenced at startup depending on config |

A Spring Boot service using `S3Client` must be granted S3 permissions via the **task role**; do not put all S3 permissions on the execution role and expect container code to inherit them automatically.

### 5.1. Trust Policy for an ECS Task Role

Minimal trust policy illustrating the service principal:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

In real deployments, consider appropriate `aws:SourceAccount` and `aws:SourceArn` conditions per ECS guidance to reduce confused deputy risks. Trust and permissions policies must be evaluated separately; avoid widening principals or resources just to get past errors.

### 5.2. Two ARNs in a Task Definition

Illustrative excerpt of a task definition:

~~~json
{
  "family": "receipt-api",
  "taskRoleArn": "arn:aws:iam::111122223333:role/receipt-api-task-dev",
  "executionRoleArn": "arn:aws:iam::111122223333:role/ecs-task-execution-dev",
  "containerDefinitions": [
    {
      "name": "receipt-api",
      "image": "111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/receipt-api:example",
      "essential": true,
      "memory": 512
    }
  ]
}
~~~

This is an **illustrative snippet**, not a complete task definition for every launch type/network mode. A real ECS deployment also requires CPU/memory, runtime, networking, logging, image tags, and required fields per launch type.

### 5.3. How Does ECS Supply Credentials to the Application?

ECS provides a credential endpoint for the task. SDK v2's `ContainerCredentialsProvider` reads the appropriate endpoint metadata from the container environment—such as `AWS_CONTAINER_CREDENTIALS_RELATIVE_URI` set by ECS—and retrieves **temporary credentials for the task role**. As expiration approaches, the provider is designed to refresh credentials from the platform instead of requiring the application to hold static keys.

Watch out for:

- Never set `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` in the task definition. Environment variables are checked **before** container credentials in `DefaultCredentialsProvider`, which can cause a different principal than the task role to be used.
- Do not confuse secrets injected into the environment from Secrets Manager at task startup with task role credentials: the **task execution role** may read secrets for ECS injection at startup, while the **application task role** needs its own permissions if the application calls the Secrets Manager API directly.
- With ECS on EC2, the node/EC2 instance may have an instance role for the ECS agent; that is separate from the task role. Control container access to node metadata and design proper isolation.
- If a task has no task role assigned, do not implicitly rely on the EC2 host's permissions; especially when migrating workloads to Fargate, that assumption breaks.

### 5.4. Splitting Roles by Workload

If a system has two services:

- `receipt-api`: writes receipts to S3 and publishes SQS events.
- `receipt-worker`: receives SQS messages and reads receipts.

There should be **two separate task roles** to restrict IAM by use case. If one service has a bug or leaks credentials, permissions do not automatically extend to the other service's actions.

## 6. EKS: IAM Roles for Kubernetes Workloads

Amazon EKS runs Kubernetes; workloads are typically organized by namespaces, Deployments, Pods, and **ServiceAccounts**. A Kubernetes service account **is not automatically an AWS IAM role**. A mechanism is needed to link a Kubernetes identity to AWS permissions.

Two common models:

1. **IAM Roles for Service Accounts (IRSA):** a Kubernetes service account is bound to an IAM role; the Pod receives a projected web identity token; the SDK uses STS `AssumeRoleWithWebIdentity`.
2. **EKS Pod Identity:** EKS manages an association between a service account and an IAM role; the Pod Identity Agent exposes a credential endpoint for the SDK to obtain temporary credentials via EKS Auth.

Do not enable multiple mechanisms simultaneously for the same application without clearly establishing precedence and the actual credential path. Also, never grant all application permissions to the node IAM role, because Pods can be rescheduled across nodes and permissions remain unsegregated.

### 6.1. EKS IRSA: OIDC Trust Bound to a Service Account

IRSA model:

~~~mermaid
flowchart TD
    SA["Kubernetes ServiceAccount: payments/receipt-api"] --> POD["Pod using serviceAccountName"]
    OIDC["EKS OIDC issuer + IAM OIDC provider"] --> JWT["Projected web identity token"]
    POD --> JWT
    JWT --> STS["STS AssumeRoleWithWebIdentity"]
    ROLE["IAM role trust policy: sub + aud"] --> STS
    STS --> TEMP["Temporary role credentials"]
    TEMP --> SDK["AWS SDK v2 WebIdentityTokenFileCredentialsProvider"]
    SDK --> SQS["S3 / SQS / Secrets Manager"]
~~~

To implement IRSA properly:

1. Identify the EKS cluster's OIDC issuer; register the corresponding OIDC identity provider in IAM.
2. Create an IAM role with a trust policy restricting the **specific OIDC provider, namespace, and service account**.
3. Attach a least-privilege permissions policy to the role.
4. Annotate the right Kubernetes ServiceAccount with the role ARN.
5. Ensure the Pod specifies the right `serviceAccountName`; verify token projection/SDK runtime and the STS dependency if needed.
6. Verify the principal inside the Pod with STS and test the actual actions/resources.

#### Illustrative IRSA Trust Policy

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::111122223333:oidc-provider/oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLE"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLE:aud": "sts.amazonaws.com",
          "oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLE:sub": "system:serviceaccount:payments:receipt-api"
        }
      }
    }
  ]
}
~~~

`111122223333` and `EXAMPLE` are illustrative placeholders. The `sub` condition strictly binds **namespace `payments` and service account `receipt-api`**. Avoid wildcards allowing every service account in the cluster when only one workload needs permissions.

#### Illustrative ServiceAccount and Deployment

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: receipt-api
  namespace: payments
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::111122223333:role/receipt-api-irsa-dev
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: receipt-api
  namespace: payments
spec:
  replicas: 1
  selector:
    matchLabels:
      app: receipt-api
  template:
    metadata:
      labels:
        app: receipt-api
    spec:
      serviceAccountName: receipt-api
      containers:
        - name: app
          image: 111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/receipt-api:example
~~~

This is a minimal Kubernetes manifest; production deployments also require security contexts, resource limits, readiness probes, logging, and proper image configuration. Account/role values are illustrative only.

With IRSA, the EKS mutating webhook typically injects `AWS_ROLE_ARN` and `AWS_WEB_IDENTITY_TOKEN_FILE` into the container so SDK v2's `WebIdentityTokenFileCredentialsProvider` can obtain role credentials. **SDK v2 and appropriate STS support modules are required**. If the environment contains static credentials, the default chain can select environment variables before web identity and bypass the annotated role.

### 6.2. EKS Pod Identity: Associations and Pod Identity Agent

EKS Pod Identity uses an EKS-managed **association** to link a namespace/service account to an IAM role. In this model, the service account does not need an IRSA annotation pointing to the role. A compatible **Pod Identity Agent** on the cluster/nodes exposes the credential retrieval path for the SDK inside the Pod.

Illustrative trust policy for a Pod Identity role:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "pods.eks.amazonaws.com"
      },
      "Action": [
        "sts:AssumeRole",
        "sts:TagSession"
      ]
    }
  ]
}
~~~

Example creating an association with the AWS CLI once the IAM role, cluster, namespace, and service account exist:

~~~bash
aws eks create-pod-identity-association \
  --cluster-name training-eks \
  --namespace payments \
  --service-account receipt-api \
  --role-arn arn:aws:iam::111122223333:role/receipt-api-pod-dev \
  --region ap-southeast-1
~~~

The command above is an **illustrative mutating AWS command**; do not run it against a real account without authorization. Verify permissions of the operator creating the association, trust policy, Pod Identity Agent health, and restarting Pods when identity configuration changes. Availability and support conditions for Pod Identity depend on node type, cluster/add-on versions, and platform setup.

With EKS Pod Identity, the SDK typically uses the **container credential provider** path via endpoint/token variables supplied by the platform. This **differs** from IRSA's direct web identity/STS path. If a Pod fails to obtain credentials, check:

- Pod Identity association matches the exact cluster, namespace, and service account.
- The agent is installed and running on the relevant nodes.
- Nodes/agent have permissions to call the required EKS Auth API.
- The IAM role trusts principal `pods.eks.amazonaws.com` with the required actions.
- The SDK/runtime supports the container credential endpoint and is not overridden by a higher-priority credential source.

### 6.3. IRSA vs. Pod Identity: Choosing by Situation

| Criterion | IRSA | EKS Pod Identity |
| --- | --- | --- |
| Role binding | Annotation on Kubernetes service account + IAM OIDC trust | EKS Pod Identity association with service account |
| Trusted principal | Cluster's federated OIDC provider | `pods.eks.amazonaws.com` |
| Credential path | Token file → SDK STS web identity | Pod Identity Agent/endpoint → EKS Auth |
| Typical SDK provider | `WebIdentityTokenFileCredentialsProvider` | `ContainerCredentialsProvider` |
| Components to manage | IAM OIDC provider, trust claims `sub`/`aud`, token projection | Pod Identity association, agent, role trust, and EKS Auth permissions |
| Deployment scope | Verify workload, OIDC, and SDK version support | Verify node/agent/cluster and SDK support per environment |

Do not claim one mechanism is universally "safer" or "faster" in every case. Both require least-privilege permissions policies, accurate trust, clear workload identity setup, and verification of resource permissions.

### 6.4. Do Not Use the Node Role for All Pods

An EKS node (such as an EC2 managed node group) has an IAM role serving node/kubelet and infrastructure tasks. If a Pod can reach the node's IMDS and the SDK fails to obtain web identity/Pod Identity credentials, the application risks unintentionally falling back to the **node role**'s credentials. Restrict node metadata access and configure proper Pod roles; never grant broad permissions to the node role for all Pods to share.

**Kubernetes RBAC is not AWS IAM.** A ServiceAccount allowed by Kubernetes to read a ConfigMap is not automatically allowed by AWS to read S3. Design both permission layers according to actual workload behavior.

## 7. Practical Permissions Policies: S3 and SQS

Suppose `receipt-api` needs to:

- Write objects to bucket `example-dev-receipts`, strictly under the `receipts/` prefix.
- Send messages to queue `receipt-events-dev` in `ap-southeast-1`, account `111122223333`.

An illustrative **identity-based permissions policy**:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "WriteReceiptObjects",
      "Effect": "Allow",
      "Action": ["s3:PutObject"],
      "Resource": "arn:aws:s3:::example-dev-receipts/receipts/*"
    },
    {
      "Sid": "PublishReceiptEvents",
      "Effect": "Allow",
      "Action": ["sqs:SendMessage"],
      "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:receipt-events-dev"
    }
  ]
}
~~~

These are illustrative application permissions. Infrastructure provisioning must create the real bucket/queue and inspect default policies and encryption. If S3 uses **SSE-KMS**, the application may need corresponding KMS permissions on the exact KMS key—for example `kms:GenerateDataKey` and, depending on operations, `kms:Decrypt`. If SQS/Secrets Manager uses a customer-managed key, review KMS permissions and key policies separately. Never grant `kms:*` on all keys just to silence a temporary error.

**Notes on ARNs:**

- `s3:PutObject` generally applies to an **object ARN**, e.g. `arn:aws:s3:::bucket/prefix/*`.
- `s3:ListBucket` applies to a **bucket ARN**, e.g. `arn:aws:s3:::bucket`, and restricting prefixes requires appropriate conditions.
- SQS actions apply to a **queue ARN**, containing region and account ID.
- Secrets Manager actions should be scoped to exact secret ARNs/agreed naming groups.

### 7.1. Producer Role vs. Consumer Role

A consumer reading queue `receipt-events-dev` and retrieving S3 receipts needs different permissions:

| Workload | Operations to evaluate | Risk when granted too broadly |
| --- | --- | --- |
| `receipt-api` | `s3:PutObject`, `sqs:SendMessage` | Could write/delete outside business scope if `s3:*` or `sqs:*` is granted |
| `receipt-worker` | `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:GetQueueAttributes`, possibly `sqs:ChangeMessageVisibility`; `s3:GetObject` | Could read any object or manipulate other queues if roles are shared |
| Spring Boot reading secrets at runtime | `secretsmanager:GetSecretValue` for needed secrets; appropriate KMS permissions | Could expose other applications' secrets if broad wildcards are used |

Exact permissions depend on the actual APIs/SDK and listener container. For example, if an SQS listener fetches a queue URL or changes visibility, verify those actions too rather than assuming only `ReceiveMessage`. Grant only the permissions actually used, then test end-to-end.

## 8. Separating Roles Across Dev, Staging, and Production

The same Spring Boot image can be deployed across multiple environments, but **identities and resources must be isolated per environment**.

| Environment | Typical identity mechanism | Target resources | Guardrails |
| --- | --- | --- | --- |
| Laptop | AWS CLI profile + IAM Identity Center for sandbox account | Dev buckets/queues/secrets | Temporary credentials, MFA, account allowlist |
| CI integration test | OIDC/STS role in test account or emulator | Test resources or LocalStack | Block production calls; scope account/role |
| EC2 dev | Dev instance profile role | Dev ARNs | Restrict resources and IMDS |
| ECS staging | Dedicated task role for staging service | Staging ARNs | Never use execution role in place of application role |
| EKS staging | Dedicated IRSA/Pod Identity role per service account | Staging ARNs | Tightly scope namespace/service account trust, verify Pod principal |
| Production | Least-privilege production workload role | Production ARNs | Deployment controls, auditing, permissions boundaries/SCPs |

If a company uses multiple AWS accounts, identify the expected account ID for each environment. **The right role in the wrong account can still cause unintended impact** if policies or cross-account trust permit the operation.

### 8.1. Cross-Account Access

A service in account A may need to read S3 objects in account B. In that scenario, explicitly design:

- Roles and trust policies across accounts, or resource-based policies permitting the exact principal in account A per service rules.
- Permission to call `sts:AssumeRole` on the caller side and trust on the target role if using assume-role.
- Resource/KMS policies in account B.
- Resource region/endpoint; token session duration and effective permissions after assuming the role.

Never switch the SDK to another IAM role simply because an HTTP 403 occurred; cross-account access must be intentionally configured. Merging permissions for every account into a default role expands blast radius.

### 8.2. Separating Deployment Permissions from Runtime Permissions

Permissions to create/update IAM roles, attach instance profiles, update ECS task definitions, create EKS associations, or edit Kubernetes ServiceAccounts are **deployment/infrastructure** permissions. They should not automatically reside in the **application runtime role**.

For example:

- A CD pipeline may need permissions to update an ECS service and pass a role to a task within controlled scope (`iam:PassRole` if required).
- At runtime, `receipt-api` only needs permission to write to S3 and send to SQS.
- The ECS execution role needs permissions to assist task startup, separate from the task role.
- Kubernetes deployment controllers hold permissions to schedule Pods, while application Pods should only have IAM roles with business permissions.

## 9. How Do Spring Cloud AWS and the AWS SDK Pick Up Roles?

In AWS SDK for Java v2, `DefaultCredentialsProvider` checks credential sources in the standard order:

1. Java system properties containing access key/secret key.
2. Environment variables containing access key/secret key.
3. Web identity token/role ARN (useful for IRSA).
4. Shared AWS profile.
5. Container credentials (ECS task role, EKS Pod Identity when properly configured).
6. EC2 instance profile via IMDS.

Platform roles **do not automatically win over every source**. If a Docker image or JVM arguments supply static access keys, the SDK may use them instead of the role attached to the task/Pod/instance. Therefore, on AWS, strip unnecessary static credentials from runtime and let the default chain pick up temporary environment credentials.

### 9.1. Simple Spring Boot Configuration

With AWSpring and the needed starters, the application can supply region and resource names via configuration:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ${AWS_REGION}

app:
  aws:
    receipt-bucket: ${APP_RECEIPT_BUCKET}
    event-queue: ${APP_EVENT_QUEUE}
~~~

This snippet **contains no access keys**. When running on EC2/ECS/EKS, the AWS SDK uses the credential provider chain or corresponding Spring Cloud AWS bean configuration. `AWS_REGION` and bucket/queue names must be supplied in the runtime environment; they do not automatically exist in every environment.

### 9.2. Using a Spring-Managed SDK Client

~~~java
import org.springframework.stereotype.Service;
import software.amazon.awssdk.services.s3.S3Client;

@Service
public class ReceiptMetadataService {
    private final S3Client s3Client;

    public ReceiptMetadataService(S3Client s3Client) {
        this.s3Client = s3Client;
    }

    public long sizeOf(String bucket, String key) {
        return s3Client.headObject(request -> request
                .bucket(bucket)
                .key(key))
            .contentLength();
    }
}
~~~

When the right starter or bean configuration is in place, `S3Client` can be injected by Spring. With Spring Cloud AWS, verify the exact version, starters, and auto-configuration conditions. **AWSpring does not grant IAM permissions**; it only helps construct beans/clients and integrate Spring mechanisms with the SDK.

### 9.3. When Creating AWS SDK Clients Yourself

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration
class AwsClients {
    @Bean
    S3Client s3Client() {
        return S3Client.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build();
    }
}
~~~

In this example, omitting `credentialsProvider(...)` still allows the SDK to use the default credential chain, while the region is configured explicitly. When deploying across multiple regions, load the region from environment configuration or manage per-region clients rather than hard-coding it in shared code.

If declaring custom `AwsCredentialsProvider`/client beans under AWSpring conventions, check whether they override the default chain. Constructing a `StaticCredentialsProvider` with keys in production source code defeats temporary role credential issuance and refresh.

### 9.4. Credential Refresh

Credentials from EC2 instance profiles, ECS task roles, IRSA, and Pod Identity are **time-limited**. The SDK's default providers are designed to refresh credentials appropriately per source when needed. Never call `resolveCredentials()` once and wrap the result in a `StaticCredentialsProvider` for a long-lived application; the application will hit `ExpiredToken`.

If the application assumes roles via STS itself, use a credential provider with proper refresh support and close resources appropriately.

## 10. Verifying the Active Role and Troubleshooting Errors

### 10.1. Using STS GetCallerIdentity

One way to verify the principal of a **running client** is calling STS:

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sts.StsClient;

public class CurrentAwsIdentity {
    public static void main(String[] args) {
        try (StsClient sts = StsClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {
            var identity = sts.getCallerIdentity();
            System.out.println("Account: " + identity.account());
            System.out.println("Principal: " + identity.arn());
        }
    }
}
~~~

This example requires the `software.amazon.awssdk:sts` SDK module. The STS client here uses default credentials unless overridden elsewhere. If S3/SQS services use a custom provider, an STS client checking the **default chain** will not necessarily reflect the same principal: configure STS with the **exact same provider** or inspect request/CloudTrail details through a secure workflow.

`GetCallerIdentity` reveals the principal's account/ARN, **does not verify specific permissions** on S3 or SQS, and does not indicate which child provider in the default chain was chosen. ARNs/account IDs may be internal information; avoid printing them to public logs.

### 10.2. Layered Diagnostic Table

| Symptom | What to check | How to verify |
| --- | --- | --- |
| Unable to find credentials | Role/instance profile not attached; missing ECS task role; broken IRSA token or Pod Identity agent/association | Inspect platform and provider chain; safely verify endpoint/token |
| ECS startup fails pulling image | Execution role lacks ECR/log/secret permissions at launch | Inspect task execution role and ECS service events |
| ECS app gets 403 calling S3 | Insufficient task role permissions or overridden credentials | STS principal from app, IAM/resource/KMS policies |
| EKS IRSA `AccessDenied` assuming role | Wrong OIDC provider, `sub`/`aud` trust condition, or service account | Compare issuer/namespace/SA, trust policy, and token projection |
| EKS Pod Identity fails to get credentials | Association/agent/role trust/EKS Auth access or incompatible SDK | Check association, agent, runtime environment |
| EC2 fails to receive instance credentials | Instance profile/IMDS disabled or metadata unreachable | Check association, IMDSv2, host/network |
| App runs under wrong role | Java system property/environment key/profile taking precedence over workload provider | Check process configuration; verify actual STS principal |
| `ExpiredToken` | Temporary credentials hard-cached or provider not refreshing | Inspect SDK provider/session/token lifecycle |
| `NoSuchKey` or `QueueDoesNotExist` | Wrong resource/region/queue URL/key | Compare ARN, region, endpoint, and application configuration |

**Distinguishing credential retrieval errors from IAM errors:**

- **Unable to obtain credentials:** SDK lacks material to sign requests; typically a provider/STS/metadata failure.
- **Credentials obtained, request denied:** Request reached AWS, but IAM/resource/SCP/KMS or a condition denied it.
- **Wrong region/endpoint:** Request may be validly signed by the right role yet still miss the intended resource.
- **Wrong role:** Working credentials exist, but belong to an unintended principal/account—usually due to precedence or infrastructure misconfiguration.

Never resolve `AccessDenied` by adding `AdministratorAccess` to a role before identifying the missing action/resource/condition.

### 10.3. CloudTrail and Audit Trails

CloudTrail can help correlate requests with principals and role sessions. When investigating incidents, inspect event source, action, timestamp, region, principal/session identity, resource, and error code within the configured logging scope. CloudTrail does not automatically capture details for all data events by default: for S3 object-level data events, enable the corresponding event logging if observability is needed.

When EKS Pod Identity uses session tagging, session tags can help distinguish workload metadata within the capabilities of the mechanism and configuration. Do not treat tags as sole proof without checking trust and IAM policies.

## 11. Testing Permissions Across Environments

Writing unit tests for business logic **does not require** real AWS permissions. For local integration tests, you can use LocalStack or an emulator with static **fake test credentials**, endpoint overrides, and a test region. However, only a smoke test in a real AWS environment validates actual IAM roles, trust, metadata/agents, KMS, and resource policies.

| Test level | Primary verification | What cannot be concluded |
| --- | --- | --- |
| Unit tests with fake/mock adapters | Service invokes business logic and maps errors properly | AWS identity, IAM, networking, and endpoints |
| Local integration tests with LocalStack | Spring/AWS SDK wiring, serialization, basic S3/SQS | Most trust policies, IMDS/IRSA/Pod Identity, and full AWS semantics |
| AWS dev/staging smoke tests | Real roles, region, ARNs, IAM/resource/KMS, live requests | High-load failures and every operational edge case |
| Failure and observability tests | Retries, duplicate messages, token refresh, AccessDenied alerts | Entire production correctness from a single scenario |

### 11.1. Simulating Credential Provisioning Failures

Scenarios worth testing:

- ECS service runs with the right task role, but a test setup introduces a higher-priority credential override; verify the system detects the wrong account/role.
- EKS Pod uses a service account without an IRSA annotation or association; verify the application **does not silently fall back to the node role** unintentionally.
- EC2 instance profile is detached or metadata is unreachable; verify startup or health checks report a clear error.
- Temporary credentials rotate over time; run a long-lived task and confirm valid provider refresh.
- S3 permissions are present while KMS permissions are missing; verify logs distinguish the root cause without blindly expanding IAM.

These failure tests must be conducted in an isolated test environment—never detach roles serving production.

### 11.2. Smoke Testing Roles and Target Resources

On dev/staging, run from **inside the actual workload**:

1. Verify actual account/role ARN via STS (using the same credential source).
2. Confirm the region and resource ARNs match the environment.
3. Perform small controlled operations, e.g., `PutObject` into a test prefix, `SendMessage` to a test queue.
4. Inspect IAM/KMS/network errors and business outcomes.
5. Clean up test resources within granted permissions/scope and verify zero side effects in production.

Avoid running smoke tests using developer laptop credentials and concluding ECS/EKS roles are correct; doing so tests **two completely different principals**.

## 12. Common Design Mistakes

### 12.1. Putting Every Permission on the EC2 Instance Role

This approach seems simple initially, yet allows multiple processes to share permissions. When service isolation is required, consider splitting instances/roles or migrating to ECS task roles or EKS workload identities, while locking down IMDS access.

### 12.2. Putting Application Permissions on the ECS Execution Role

The execution role lets the ECS agent pull images, but the application does not automatically use that role to call S3/SQS. Put application permissions on `taskRoleArn` and check the STS principal from inside the container.

### 12.3. Putting Business Permissions on the EKS Node Role

The EKS node role serves the node. If all Pods rely on it, services can cross privilege boundaries. Use IRSA or Pod Identity with precise service accounts and trust, and restrict node IMDS access.

### 12.4. Making Trust Policies Too Broad

IRSA with a `sub` condition accepting any namespace or a Pod Identity role lacking appropriate association restrictions expands spoofing/misuse exposure. Narrow trust to the exact workload and combine with IAM/resource policies. For ECS/EC2, allow only the service principal and appropriate conditions; never allow any principal to assume the role.

### 12.5. Storing Access Keys in application.yml

Creating static IAM user keys to "fix" ECS/EKS credentials makes the application bypass workload identity, complicates rotation, and risks leaks. The proper fix is diagnosing the role/trust/metadata/agent issue so the SDK provider chain works as intended.

### 12.6. Conflating Region, Account, and Role

A role may belong to the right account while the S3 bucket lives in another region; a queue URL or secret ARN may point to another account/region. IAM permissions, endpoints, and resource configurations must be verified **separately**.

## 13. Comprehensive Hands-On Scenario

**Problem statement:** A Spring Boot system has two applications:

- `receipt-api` receives files from users, stores them in `s3://example-dev-receipts/receipts/`, and sends events to queue `receipt-events-dev`.
- `receipt-worker` receives messages, downloads files for processing, and records results in a dedicated data store.

The team currently runs locally with an AWS CLI profile and plans to deploy to EC2 dev, ECS staging, and EKS production. Each environment has its own account and resources; the Java applications use Spring Cloud AWS and AWS SDK v2.

### Task A — Select Roles by Platform

1. For **EC2 dev**, diagram the relationship `IAM role → instance profile → EC2 → IMDS → SDK client`. Explain the risk when API and worker share one instance.
2. For **ECS staging**, define separate `taskRoleArn` roles for API and worker, plus an appropriate `executionRoleArn` for the ECS agent. Specify which role holds application permissions.
3. For **EKS production**, choose IRSA or Pod Identity based on cluster/agent support. Define separate namespaces and service accounts for each application, corresponding trust, and permission scope.
4. For **local**, use an IAM Identity Center sandbox profile. Do not embed access keys in Spring configuration.

### Task B — Design Least-Privilege Permissions

Complete the permissions table:

| Workload | S3 | SQS | Secrets Manager/KMS |
| --- | --- | --- | --- |
| `receipt-api` | Write strictly to prefix `receipts/*` | `SendMessage` to target queue | Read only secrets/KMS keys genuinely used |
| `receipt-worker` | Read only prefix/objects needed for processing | Receive/Delete/GetQueueAttributes/ChangeMessageVisibility if used | Read only secrets/KMS keys genuinely used |

Cross-check actual policies against the permissions of each SDK operation. Never use wildcard `Action:"*"` or `Resource:"*"` out of habit.

### Task C — Debug Incidents

1. ECS API returns 403 on `PutObject`, yet role `ecs-task-execution-dev` already has S3 permissions. Why does it still fail?
2. An EKS IRSA Pod is annotated, yet STS reports assume-role failure. Which `sub`, `aud`, OIDC provider, and service account conditions must be compared?
3. The Pod Identity role is right, yet the Pod reports missing credentials. How do you check association, agent, node/EKS Auth, and provider precedence?
4. An EC2 role has full SQS permissions, yet the application runs with another access key from the environment. Analyze provider chain order and consequences.
5. Production uses a role in the right account, yet the SQS URL points to staging. Why must region, queue ARN, and policies all be checked?

### Task D — Testing Plan

Design a suite including:

- Unit tests for S3/SQS adapters.
- LocalStack integration tests with fake credentials and test endpoints.
- Smoke tests on each platform using the actual role, alongside `GetCallerIdentity`, account/region checks, and minimal operations.
- Tests for token refresh, IAM failures, and SQS retry/duplicate events.
- Monitoring with safe logs, metrics, and CloudTrail where properly configured.

**Evaluation criteria:** Diagrams must show the exact **application principal** for each platform, cleanly separated role/trust/permissions policies, environment-scoped resource ARNs, and verification of **the actual role used by the workload** rather than relying solely on profile/role names in documentation.

## 14. Conceptual Comparison with Azure and Google Cloud

The multi-cloud goal of this module requires understanding the shared principle: workloads should use **managed/workload identities** to acquire short-lived credentials, then enforce least-privilege access on resources. Yet each provider implements identity issuance and authorization differently.

| Need | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| Workload on VM | EC2 instance profile IAM role | Managed Identity for VM | Service account attached to Compute Engine VM |
| Container/orchestrator | ECS task role; EKS IRSA/Pod Identity | Managed Identity / workload identity for container/AKS environments | Workload Identity Federation for GKE |
| Default SDK credentials | `DefaultCredentialsProvider` | Credential chains such as `DefaultAzureCredential` | Application Default Credentials (ADC) |
| Resource authorization | IAM identity/resource policies, KMS/SCP where applicable | Azure RBAC and service policies | IAM roles/bindings, conditions, and service policies |

This table compares concepts only; it **does not** equate permission syntax or credential chains across clouds. For instance, a Kubernetes ServiceAccount on EKS cannot automatically reuse GKE IAM configuration. When implementing multi-cloud Spring Boot applications, keep business logic separate from each provider's specific adapters and identity settings.

## 15. Key Takeaways

With **EC2**, the application role goes through an **instance profile** and IMDS, typically offering instance-level isolation. With **ECS**, application code uses the **task role**, while the **task execution role** serves startup infrastructure. With **EKS**, applications should obtain identity per **Kubernetes service account** via **IRSA** (OIDC/web identity/STS) or **Pod Identity** (association/agent/EKS Auth) depending on the platform.

All three models rely on **temporary credentials** and real IAM permissions. Spring Cloud AWS and AWS SDK for Java v2 facilitate retrieving and using credentials, but they do not replace designing trust policies, least privilege, resource/KMS policies, regions, resources, and testing. Choosing the right role for each workload and environment is the foundation before integrating S3, SQS, secrets, databases, or comparing analogous patterns on Azure and Google Cloud.
