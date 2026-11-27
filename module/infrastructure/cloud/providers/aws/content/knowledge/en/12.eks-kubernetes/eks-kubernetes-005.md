# IAM Roles for Service Accounts and EKS Pod Identity

A Java/Spring Boot application running in **Amazon Elastic Kubernetes Service (Amazon EKS)** may need to read objects from Amazon S3, retrieve secrets from AWS Secrets Manager, update DynamoDB, or query CloudWatch. Those requests must be signed with valid **AWS credentials** and evaluated against **IAM permissions**. Embedding long-lived access keys inside a Docker image, Kubernetes Secret, or source code exposes credentials to leakage and complicates rotation; letting every Pod use the broad IAM role of the EC2 worker node allows a compromised Pod to abuse the entire node's permissions.

The two EKS mechanisms that solve workload identity are **IAM Roles for Service Accounts (IRSA)** and **EKS Pod Identity**. Both link a **Kubernetes ServiceAccount** to an **AWS IAM role** so applications receive **temporary security credentials** without distributing static keys. They differ in credential retrieval flows, IAM trust policies, deployment prerequisites, and multi-cluster governance.

This topic belongs to the **Kubernetes with EKS** chapter of the **CLOUD_PROVIDERS_AWS** module. It connects IAM, AWS STS, VPC, EC2/Fargate, EKS networking, S3, RDS, DynamoDB, serverless, CloudTrail, availability, resilience, and cost control when designing applications on AWS.

> **Core principle:** A Kubernetes ServiceAccount is an identity **inside the cluster**; an IAM role is an identity **on AWS**. IRSA and Pod Identity bridge these two identity layers, but **do not replace Kubernetes RBAC, IAM least privilege, Pod Security, or network path controls**.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Distinguish Kubernetes ServiceAccounts, Kubernetes RBAC, IAM roles, role trust policies, and role permissions policies.
2. Accurately describe the **IRSA → projected OIDC token → STS AssumeRoleWithWebIdentity** flow.
3. Describe **EKS Pod Identity association → agent → EKS Auth AssumeRoleForPodIdentity → temporary credentials**.
4. Configure or read example IAM policies, ServiceAccounts, Deployments, and associations for both mechanisms.
5. Compare usage across EKS Linux EC2 nodes, EKS Auto Mode, and Fargate; recognize Windows/Outposts limitations.
6. Know how to use AWS SDK for Java v2 and the default credential chain, and verify the **actual role in use**.
7. Explain cross-account Pod Identity via **target roles** and role chaining.
8. Design IAM least privilege, Kubernetes RBAC, IMDS protection, VPC endpoints, monitoring, and troubleshooting.
9. Plan a migration from IRSA to Pod Identity with safe rollout/rollback.
10. Diagnose `AccessDenied`, mismatched OIDC issuers, unsupported SDKs, agents lacking network connectivity, or wrong namespaces/ServiceAccounts.

## 2. How Does a Kubernetes ServiceAccount Differ from an IAM Role?

Suppose a workload has a Kubernetes identity:

~~~text
Cluster:        shop-cluster
Namespace:      shop
ServiceAccount: orders-api
Subject:        system:serviceaccount:shop:orders-api
~~~

A Pod specifies `spec.serviceAccountName: orders-api` to use the ServiceAccount in namespace `shop`. The Kubernetes API server recognizes the ServiceAccount via a Kubernetes token and applies **Kubernetes RBAC**. However, the AWS S3 API does not accept a “service account name” as an IAM principal. To call S3, the AWS SDK needs credentials for an **IAM role session**.

| Component | Scope | Permission Examples |
|---|---|---|
| **ServiceAccount** | Kubernetes cluster + namespace | Pod identity when calling the Kubernetes API |
| **Kubernetes RBAC** | Kubernetes API resources | `get pods`, `list configmaps` |
| **IAM role trust policy** | Who may assume the role | OIDC issuer and `sub/aud`, or service principal `pods.eks.amazonaws.com` |
| **IAM permissions policy** | Permissions to call AWS APIs | `s3:GetObject` on a prefix; `dynamodb:GetItem` on a table |
| **Resource-based policies / guardrails** | Additional conditions on AWS resources | S3 bucket policy, KMS key policy, SCP, permissions boundary |
| **VPC/network policies** | Actual connectivity path | STS/EKS Auth/S3 endpoints, DNS, Security Groups, routing |

A Pod with a **valid IAM role but no path to the S3 endpoint** will time out. A Pod with a **valid network path but missing `s3:GetObject`** will be denied. Diagnostics must therefore separate **authentication**, **authorization**, and **networking**.

### 2.1. Why not use the worker node's IAM role?

An EC2 worker node has an IAM instance profile for kubelet, EKS networking, and node management tasks. If a container can reach the **EC2 Instance Metadata Service (IMDS)**, it can retrieve node credentials, which are typically far broader than an application needs. Both IRSA and Pod Identity reduce reliance on node IAM roles for workloads, yet **do not automatically lock down IMDS** or turn containers into an absolute security boundary.

Enforce IMDSv2 and appropriate hop limits/network controls; constrain node role permissions, Pod Security, privileged/hostNetwork/hostPath settings, and Kubernetes RBAC. Never grant `AdministratorAccess` to a node role just because one Pod needs to read an S3 file.

## 3. Two Credential Issuance Flows

~~~mermaid
flowchart TD
    P["Pod + Kubernetes ServiceAccount"] --> X{"Identity mechanism"}
    X -->|"IRSA"| O["Projected OIDC web identity token"]
    O --> W["AWS SDK WebIdentity provider"]
    W --> STS["STS AssumeRoleWithWebIdentity"]
    X -->|"EKS Pod Identity"| A["EKS association + projected Pod Identity token"]
    A --> C["AWS SDK Container credentials provider"]
    C --> G["EKS Pod Identity Agent on node"]
    G --> AUTH["EKS Auth AssumeRoleForPodIdentity"]
    AUTH --> STS2["AWS-managed STS role session"]
    STS --> T["Temporary AWS credentials"]
    STS2 --> T
    T --> S["S3 / DynamoDB / Secrets Manager"]
~~~

**Similarities:** Both ultimately give the Pod temporary credentials consisting of an access key ID, secret access key, session token, and expiration. They must remain confidential, refresh automatically, and adhere to IAM least privilege.

**Differences:**

- **IRSA:** the SDK running inside the Pod reads a projected web identity token and directly calls **AWS STS `AssumeRoleWithWebIdentity`**.
- **Pod Identity:** the SDK running inside the Pod calls the **agent's local credentials endpoint on the node**; the agent calls **EKS Auth `AssumeRoleForPodIdentity`** and receives credentials on the Pod's behalf.

## 4. Comparison Table: Choosing Between IRSA and Pod Identity

| Criterion | IRSA | EKS Pod Identity |
|---|---|---|
| Pod identity | Kubernetes ServiceAccount | Kubernetes ServiceAccount |
| Role mapping | `eks.amazonaws.com/role-arn` annotation | **EKS Pod Identity association** |
| IAM trust principal | **Federated OIDC provider** per cluster | **`pods.eks.amazonaws.com`** |
| STS operation | `AssumeRoleWithWebIdentity` | EKS Auth fetches role credentials via `AssumeRoleForPodIdentity` |
| OIDC provider in IAM | Must be created for cluster issuer | **Not required** for Pod Identity |
| Agent | Does not use Pod Identity Agent | Required on Linux EC2 nodes; built into Auto Mode |
| SDK provider | Web identity token credentials | Container credentials |
| Reusing roles across clusters | Trust must manage per-cluster issuers | Trust uses shared service principal; associations are per cluster |
| Fargate Pods | **IRSA supported** | **Not supported** |
| EKS Linux EC2 worker nodes | Yes | Yes, when prerequisites are met |
| EKS Auto Mode | Check corresponding configuration | Yes, agent mechanism is built-in |
| Cross-account | OIDC federation and/or role chaining | Association can use **`--target-role-arn`** for role chaining |
| Java SDK | Requires web identity support | AWS SDK for Java v2 **≥ 2.21.30** per EKS docs |
| Multi-SA governance | Manage annotations and OIDC trusts | Manage associations via EKS API |
| Best suited for | Environments already using IRSA, Fargate workloads | New workloads on supported node types |

For new workloads on supported nodes, **EKS Pod Identity** is often more convenient since you do not manage an IAM OIDC provider per cluster. **IRSA remains fully supported by AWS**, especially for Fargate or systems standardized on OIDC. Before choosing, check your AWS Region, EKS cluster platform version, SDK, and compute types.

## 5. IRSA: OIDC Issuer, Projected Token, and Trust

### 5.1. Cluster OIDC issuer

Each EKS cluster has an OIDC issuer URL of the form:

~~~text
https://oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLEOIDCID
~~~

This is an **illustrative issuer**. In practice, use the URL returned by `aws eks describe-cluster`. IAM requires an **OIDC identity provider** matching this URL. Because the issuer embeds a cluster identifier, deleting and recreating a cluster with the same name can break old IAM providers/trusts.

The projected ServiceAccount JWT includes key claims:

~~~json
{
  "iss": "https://oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLEOIDCID",
  "aud": ["sts.amazonaws.com"],
  "sub": "system:serviceaccount:shop:orders-api"
}
~~~

This is a **simplified illustrative payload**, not a real or complete JWT. `iss` is the issuer; `aud` scopes the token to AWS STS; `sub` identifies the exact namespace and ServiceAccount. The OIDC provider/JWKS handles signature verification and token lifetime. Never paste tokens into tickets, logs, or Git.

### 5.2. IAM trust policy for IRSA

Example for a cluster in account `111122223333`, ServiceAccount `shop/orders-api`:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TrustOrdersServiceAccount",
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::111122223333:oidc-provider/oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLEOIDCID"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLEOIDCID:aud": "sts.amazonaws.com",
          "oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLEOIDCID:sub": "system:serviceaccount:shop:orders-api"
        }
      }
    }
  ]
}
~~~

**Mandatory:** replace the account and OIDC issuer with real values. In the trust policy, `Principal.Federated` is the IAM OIDC provider ARN; condition keys **do not include `https://`** and must match the exact issuer path. Never widen `sub` to a wildcard across all namespaces/SAs just to silence `AccessDenied`. A misused high-privilege ServiceAccount is a severe IAM vulnerability.

### 5.3. IAM role permissions policy

The `orders-api` app only needs to read configuration files in S3:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadOrdersConfiguration",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::orders-config-demo/app/*"
    }
  ]
}
~~~

`s3:GetObject` uses an **object ARN**. To list the bucket, also grant `s3:ListBucket` on the **bucket ARN** with prefix conditions where needed. SSE-KMS encrypted objects may require `kms:Decrypt` and a matching key policy. The IAM role trust policy and permissions policy serve two distinct roles: **who can assume the role** and **what the role is allowed to do**.

## 6. IRSA: ServiceAccount and Deployment YAML

### 6.1. The `role-arn` annotation

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: shop
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::111122223333:role/OrdersReadOnlyIrsaRole
~~~

Namespace `shop` must already exist, and the IAM role ARN must be a real role whose OIDC trust matches `sub`. The annotation enables the EKS Pod Identity Webhook for IRSA to inject the needed configuration into new Pods.

### 6.2. Deployment selecting the ServiceAccount

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: shop
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      serviceAccountName: orders-api
      containers:
        - name: app
          image: 111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/shop/orders-api:1.0.0
          ports:
            - containerPort: 8080
~~~

**Note:** this manifest is a condensed example; production deployments still need image digests, resource requests/limits, readiness/liveness probes, SecurityContext, Pod security, and rollout policies. Without `serviceAccountName`, Pods use the `default` ServiceAccount instead of `orders-api`.

### 6.3. Credentials provider inside an IRSA Pod

When a new Pod is created, EKS typically injects:

~~~text
AWS_ROLE_ARN=arn:aws:iam::111122223333:role/OrdersReadOnlyIrsaRole
AWS_WEB_IDENTITY_TOKEN_FILE=/var/run/secrets/eks.amazonaws.com/serviceaccount/token
~~~

The AWS SDK reads the projected token and calls `STS AssumeRoleWithWebIdentity`. A **network path to the STS endpoint** is required, such as via a private STS VPC endpoint or an appropriate NAT gateway. For private workloads, prefer the **regional STS endpoint** so the SDK does not accidentally call the global endpoint without private connectivity.

### 6.4. IRSA deployment workflow

1. Inspect the EKS cluster issuer.
2. Create the IAM OIDC provider matching the issuer if the cluster does not have one yet.
3. Create the IAM role with `sub/aud` trust policy and least-privilege permissions policy.
4. Add the `eks.amazonaws.com/role-arn` annotation to the ServiceAccount.
5. Configure the Deployment to reference that ServiceAccount.
6. Create new Pods/roll out per procedure to receive the token/env vars.
7. Verify `STS GetCallerIdentity` and the required AWS API calls from inside the Pod.

Example **cluster-mutating** commands, run only in an authorized lab with approved YAML files:

~~~bash
kubectl apply -f irsa-service-account.yaml
kubectl rollout restart deployment/orders-api -n shop
~~~

Creating an OIDC provider/role and running `kubectl apply` modify real infrastructure and are not part of the read-only lab in this lesson.

## 7. EKS Pod Identity: Associations, Agent, and EKS Auth

EKS Pod Identity is configured via an **EKS association** rather than IRSA annotations. An association links:

~~~text
Cluster:        shop-cluster
Namespace:      shop
ServiceAccount: orders-api
IAM role:       arn:aws:iam::111122223333:role/OrdersReadOnlyPodRole
~~~

AWS creates an EKS-managed mapping. When a new Pod uses a ServiceAccount with an association, EKS injects environment/container credential settings into the Pod; the AWS SDK talks to the node's Pod Identity Agent.

### 7.1. Credential flow

~~~mermaid
sequenceDiagram
    participant P as Pod / AWS SDK
    participant A as Pod Identity Agent
    participant E as EKS Auth API
    participant T as AWS STS
    participant S as AWS service
    P->>A: Local credential endpoint + Pod Identity token
    A->>E: AssumeRoleForPodIdentity
    E->>T: EKS-managed assume role
    T-->>E: Temporary credentials
    E-->>A: Temporary credentials
    A-->>P: Credentials for SDK caching/refresh
    P->>S: Request signed with IAM role session
    S-->>P: Response per permissions policy
~~~

**Note:** Pod Identity does not require the SDK to call `AssumeRoleWithWebIdentity` directly; this is the fundamental difference from IRSA.

### 7.2. Injected environment variables

Pod Identity injects values like:

~~~text
AWS_CONTAINER_CREDENTIALS_FULL_URI=http://169.254.170.23/v1/credentials
AWS_CONTAINER_AUTHORIZATION_TOKEN_FILE=/var/run/secrets/pods.eks.amazonaws.com/serviceaccount/eks-pod-identity-token
~~~

The Pod Identity token has audience `pods.eks.amazonaws.com`; the agent uses it to authenticate the Pod. Do not confuse this token with the **IRSA OIDC token with audience `sts.amazonaws.com`**.

The agent uses link-local IPv4 `169.254.170.23`, and local IPv6 `fd00:ec2::23` when configured. If IPv6 is disabled on nodes, the agent may need its IPv6 listener disabled per AWS documentation. When using an HTTP proxy, add the local address to `NO_PROXY`/`no_proxy` so tokens/credentials are never sent through a corporate proxy.

### 7.3. Support prerequisites

- EKS cluster/platform version supports Pod Identity.
- Pods run on supported **Linux EC2 worker nodes**, or **EKS Auto Mode** with the integrated agent mechanism.
- On EC2 worker nodes, the **EKS Pod Identity Agent** must be healthy (typically the `eks-pod-identity-agent` EKS add-on / DaemonSet).
- The **Node IAM role** for the agent has `eks-auth:AssumeRoleForPodIdentity`. AWS-managed `AmazonEKSWorkerNodePolicy` already includes this permission; custom node policies must add it appropriately.
- Nodes have a network path to the **EKS Auth API** via Internet/NAT or a private interface endpoint.
- The SDK inside the container supports Pod Identity and is not overridden by another credential source.

**EKS Fargate Pods are not supported by EKS Pod Identity.** Do not attempt to install the DaemonSet agent on Fargate to “fix” it—use IRSA. Pod Identity also does not support Windows EC2 nodes, EKS Anywhere, or local clusters on Outposts per AWS limits.

### 7.4. EKS Auto Mode

In **EKS Auto Mode**, the EKS Pod Identity Agent capability is built in; **you do not need to manually install the agent add-on**. Still verify cluster/node mode, SDK, and associations. Not seeing an `eks-pod-identity-agent` DaemonSet when Auto Mode is active does not mean Pod Identity is missing.

## 8. Pod Identity IAM Trust Policy Differs from IRSA

With EKS Pod Identity, the IAM role trusts the EKS **service principal**:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowOrdersPodIdentity",
      "Effect": "Allow",
      "Principal": {
        "Service": "pods.eks.amazonaws.com"
      },
      "Action": [
        "sts:AssumeRole",
        "sts:TagSession"
      ],
      "Condition": {
        "StringEquals": {
          "aws:RequestTag/kubernetes-namespace": "shop",
          "aws:RequestTag/kubernetes-service-account": "orders-api"
        }
      }
    }
  ]
}
~~~

- `sts:AssumeRole` allows EKS Pod Identity to use the IAM role.
- `sts:TagSession` allows EKS to attach session tags identifying the workload source.
- Conditions validate the session's **namespace and ServiceAccount**. You can further tighten by cluster ARN/name or conditions like `aws:SourceOrgId` where aligned with AWS Organizations and IAM documentation.
- The role still needs its **permissions policy** for S3/DynamoDB/APIs as in section 5.3.

**Difference from IRSA:** there is no `Principal.Federated` and no OIDC `sub/aud` conditions. A role can be reused across multiple EKS clusters without adding a new issuer per cluster to the trust policy; even so, govern trust conditions, session tags, and blast radius when reusing roles.

### 8.1. Session tags and ABAC

Pod Identity provides default AWS-injected session tags, such as:

| Session Tag | Content |
|---|---|
| `eks-cluster-arn` | Cluster ARN |
| `eks-cluster-name` | Cluster name |
| `kubernetes-namespace` | Pod namespace |
| `kubernetes-service-account` | ServiceAccount |
| `kubernetes-pod-name` | Pod name |
| `kubernetes-pod-uid` | Pod UID |

IAM can use these tags in **ABAC (Attribute-Based Access Control)** to scope resources. Never allow other principals to arbitrarily set tags mimicking `kubernetes-*`/`eks-*`, as they could bypass intended boundaries. Session tags plus inline policies have a packed size limit; `PackedPolicyTooLarge` requires trimming policies or adjusting tag settings per documentation.

### 8.2. Session policy on an association

The EKS Pod Identity association API can accept a **session policy** to further constrain permissions applied to Pods beyond the role's policies. A session policy **cannot elevate permissions** above the IAM role and works alongside resource-based policies/guardrails. This is an advanced option and unnecessary for a dedicated role like `OrdersReadOnlyPodRole`.

## 9. Creating a Pod Identity Association via Console/CLI

### 9.1. Install the agent for EC2 node clusters

In the EKS Console, select the cluster → Add-ons → **EKS Pod Identity Agent**. Or use the CLI (**modifies real cluster**):

~~~bash
aws eks create-addon \
  --cluster-name shop-cluster \
  --addon-name eks-pod-identity-agent \
  --profile dev \
  --region ap-southeast-1
~~~

Before running, check whether the add-on already exists, node roles, Region, cluster platform version, and EKS Auth networking. Do not install the add-on on EKS Auto Mode.

### 9.2. ServiceAccount for Pod Identity

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: shop
~~~

This ServiceAccount **does not need** the `eks.amazonaws.com/role-arn` annotation used by IRSA. The Deployment still specifies `serviceAccountName: orders-api`.

### 9.3. Create the association via the EKS API

~~~bash
# MUTATING: run only when role/cluster are approved
aws eks create-pod-identity-association \
  --cluster-name shop-cluster \
  --namespace shop \
  --service-account orders-api \
  --role-arn arn:aws:iam::111122223333:role/OrdersReadOnlyPodRole \
  --profile dev \
  --region ap-southeast-1
~~~

The primary `--role-arn` must belong to the **EKS cluster's AWS account**, due to IAM PassRole requirements. The principal managing the association needs `eks:CreatePodIdentityAssociation` and **`iam:PassRole` on that exact role** per policy. Never grant PassRole across all privileged roles.

Associations exhibit **eventual consistency**: for a few seconds after the API succeeds, the configuration may not yet apply across all components. Never create/update associations in the hot request path of an application. Create new Pods / roll out after the association is ready so they receive the right env vars and projected tokens.

### 9.4. Inspect association and agent status

~~~bash
aws eks list-pod-identity-associations \
  --cluster-name shop-cluster \
  --profile dev \
  --region ap-southeast-1 \
  --output json

aws eks list-addons \
  --cluster-name shop-cluster \
  --profile dev \
  --region ap-southeast-1 \
  --output json

kubectl get serviceaccount orders-api -n shop -o yaml

kubectl get daemonset eks-pod-identity-agent -n kube-system -o wide
~~~

The last command applies to clusters **running the agent DaemonSet**. On Auto Mode, the agent is integrated and may not appear as that DaemonSet. With a real association ID, use `aws eks describe-pod-identity-association --cluster-name ... --association-id ...` to inspect details.

## 10. Cross-Account IAM: IRSA and Pod Identity

Suppose the EKS cluster resides in account **A `111122223333`**, while DynamoDB/S3 data lives in account **B `444455556666`**.

### 10.1. Cross-account IRSA

Two common patterns:

1. An IAM role in account B trusts the OIDC issuer of EKS cluster A—once B configures the matching IAM OIDC provider—and token `sub/aud` match the trust. Pods receive role B credentials via `AssumeRoleWithWebIdentity`; or
2. Pods receive an IRSA IAM role in A, then call **`AssumeRole`** into target role B via credential providers and cross-account trust/policies.

Verify IAM permissions on the caller, target role trust, SCPs/permissions boundaries, and bucket/KMS policies. Never assume two accounts in the same Organization can automatically assume each other's roles.

### 10.2. Cross-account Pod Identity and `target-role-arn`

Per the current EKS API, a Pod Identity association can specify a **target IAM role** via `--target-role-arn`. EKS manages **role chaining** automatically:

~~~mermaid
flowchart LR
    P["Pod shop/orders-api in account A"] --> E["EKS Pod Identity association"]
    E --> S["Source role in A"]
    S -->|"sts:AssumeRole"| T["Target role in B"]
    T --> D["S3 / DynamoDB in account B"]
~~~

**Mutating** command (illustrative only):

~~~bash
aws eks create-pod-identity-association \
  --cluster-name shop-cluster \
  --namespace shop \
  --service-account orders-api \
  --role-arn arn:aws:iam::111122223333:role/OrdersPodIdentitySourceRole \
  --target-role-arn arn:aws:iam::444455556666:role/SharedDataReadRole \
  --profile dev \
  --region ap-southeast-1
~~~

Design requirements:

- Source role `OrdersPodIdentitySourceRole` belongs to the **cluster's account**, trusts `pods.eks.amazonaws.com`, and holds `sts:AssumeRole` targeting the target role.
- Target role `SharedDataReadRole` belongs to B and **trusts source role A**; its permissions allow only required actions/resources.
- If using session tags across role chaining, handle `sts:TagSession`, conditions, and guardrails properly.
- Role chaining is subject to a **maximum one-hour session duration** on the chained assume step plus refresh/quota constraints.
- Add resource policies/KMS permissions on resources in B as needed.

Before using this in production, verify AWS CLI/EKS API versions supporting `--target-role-arn`. **Do not conclude Pod Identity lacks cross-account support** solely from older docs that required manual assume-role code.

## 11. Platform Limitations, Quotas, and Selection

### 11.1. Support by Pod execution environment

| Execution Environment | IRSA | Pod Identity |
|---|---|---|
| Linux EC2 managed/self-managed nodes | Supported | Supported if agent and versions match |
| EKS Auto Mode | Check specific config/workload | Supported, built-in agent |
| EKS Fargate | **Supported** | **Not supported** |
| Windows EC2 worker nodes | Requires separate compatibility review | **Not supported** |
| EKS Anywhere | Does not directly use EKS-managed OIDC like IRSA | Not supported |
| EKS local clusters on Outposts | IRSA not supported per AWS limits | Pod Identity not supported |

The **Fargate pod execution role** is used by the Fargate runtime to prepare Pods (such as pulling images). It **does not become the application's IAM role**. For an app reading S3 on EKS Fargate, use **IRSA** as supported.

### 11.2. Quotas and versions

- EKS currently supports up to **5,000 Pod Identity associations per cluster** per published service limits. Verify live limits/quotas before very large deployments.
- A namespace/ServiceAccount pair in one cluster has **one primary role association**.
- For **AWS SDK for Java 2.x**, AWS specifies a minimum version of **2.21.30** for EKS Pod Identity; prefer newer versions with up-to-date security fixes.
- EKS cluster/platform and add-on versions must support Pod Identity; do not assume legacy Kubernetes versions or Outposts work.
- Association changes are eventually consistent; already running Pods are not updated simultaneously.

## 12. AWS SDK for Java v2: Never Hardcode Access Keys

### 12.1. Verify identity with STS

Code relies solely on the default credentials provider chain:

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sts.StsClient;
import software.amazon.awssdk.services.sts.model.GetCallerIdentityResponse;

public class CallerIdentity {
    public static void main(String[] args) {
        try (StsClient sts = StsClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {

            GetCallerIdentityResponse result = sts.getCallerIdentity();
            System.out.println("Account: " + result.account());
            System.out.println("Principal: " + result.arn());
        }
    }
}
~~~

Requires the `software.amazon.awssdk:sts` dependency, managed via the AWS SDK BOM. Output prints **account/ARN** without secret keys or session tokens. Inside EKS, when properly configured, the ARN looks like `arn:aws:sts::111122223333:assumed-role/OrdersReadOnlyPodRole/...` or the corresponding IRSA role.

### 12.2. Reading an S3 object

~~~java
import java.nio.file.Path;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;

public class DownloadOrdersConfig {
    public static void main(String[] args) {
        try (S3Client s3 = S3Client.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {

            s3.getObject(
                GetObjectRequest.builder()
                    .bucket("orders-config-demo")
                    .key("app/config.json")
                    .build(),
                Path.of("config.json")
            );
        }
    }
}
~~~

This snippet performs an actual object read when run with valid resources/credentials. The app needs IAM `s3:GetObject`, network connectivity to the S3 endpoint, and KMS permissions if the object is encrypted with a customer-managed KMS key.

### 12.3. Credentials provider precedence can pick the wrong role

The SDK checks **multiple credential sources in priority order**. If the container still holds `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, or a custom `StaticCredentialsProvider`, those may be selected **before** IRSA/Pod Identity. In the Java SDK v2, the web identity provider is evaluated before the container credentials provider.

If both an **IRSA annotation** and a **Pod Identity association** exist, the `AWS_ROLE_ARN`/`AWS_WEB_IDENTITY_TOKEN_FILE` variables from IRSA can cause the SDK to **keep using IRSA**, even though Pod Identity is also valid. Before concluding “Pod Identity isn't working,” verify the **actual caller ARN**, inspect relevant environment variable **names without printing secret values**, remove leftover configuration, and launch new Pods.

Both mechanisms rely on **expiring temporary credentials**. Let SDK providers refresh automatically; never copy a credential set into static config for long-running applications.

## 13. Migrating from IRSA to EKS Pod Identity

To minimize downtime and govern privileges during migration:

1. **Audit:** cluster/platform version, Linux EC2 vs. Fargate nodes, SDK versions, OIDC issuer, current annotations, IAM roles, and permissions.
2. **Prepare:** enable the EKS Pod Identity Agent on supported clusters (except Auto Mode), ensure the node role has `eks-auth:AssumeRoleForPodIdentity`, and verify EKS Auth endpoint connectivity.
3. **Create the Pod Identity role:** trust `pods.eks.amazonaws.com` with appropriate namespace/SA/cluster conditions, and least-privilege permissions equal to or narrower than IRSA.
4. **Create the EKS association:** matching role and ServiceAccount in the right namespace; allow eventual consistency.
5. **Keep IRSA during preparation**, avoiding revoking permissions before the agent/association are ready.
6. **Remove IRSA annotations and web identity env overrides** from the ServiceAccount/Pod template when shifting traffic.
7. **Roll out gradually:** use rolling/canary deployments so new Pods receive injected Pod Identity credentials; never replace all production Pods at once.
8. **Verify:** `GetCallerIdentity` and a granted read-only API call; monitor app health, error logs, CloudTrail, and request latency.
9. **Rollback:** if new Pods fail to obtain credentials, restore the IRSA ServiceAccount/role trust and roll out per runbook.
10. **Controlled cleanup:** remove unused OIDC trusts/providers only after confirming no other ServiceAccounts depend on them.

~~~mermaid
flowchart TD
    A["Stable IRSA"] --> B["Check compute + SDK + Agent"]
    B --> C["Create Pod Identity role and association"]
    C --> D["Remove IRSA annotation for new Pods"]
    D --> E{"Actual role and AWS APIs correct?"}
    E -->|Yes| F["Monitor and finalize"]
    E -->|No| G["Rollback to IRSA, investigate root cause"]
~~~

**Note:** updating a ServiceAccount does not re-inject env vars into **existing Pods**. Creating new Pods is required to observe the updated identity configuration; association updates also have propagation latency.

## 14. Security: Least Privilege, RBAC, IMDS, and Auditing

### 14.1. RBAC protects workload identities

Anyone able to **create Pods/Deployments using a privileged ServiceAccount** can leverage the AWS permissions of the IAM role bound to that SA. Therefore:

- Restrict `create/update deployments`, `create pods`, `update serviceaccounts`, and namespace operations via Kubernetes RBAC.
- Never bind elevated IAM roles to the `default` ServiceAccount.
- Separate `shop-dev/orders-api` from `shop-prod/orders-api`; validate `sub` or session tags.
- Use admission policies where appropriate to restrict privileged containers, hostPath, unsigned images, and unapproved ServiceAccounts.
- Restrict `eks:CreatePodIdentityAssociation`, `eks:UpdatePodIdentityAssociation`, and **`iam:PassRole`** by role/cluster so developers cannot arbitrarily attach admin roles.

Kubernetes RBAC **is not** an IAM role trust policy; both are required.

### 14.2. Protecting node IAM roles and IMDS

On EKS EC2 nodes, Pods can reach IMDS if not properly restricted. With `hostNetwork: true`, AWS emphasizes that Pods retain a path to IMDS, even if the AWS SDK prefers IRSA/Pod Identity when configured.

- Enforce **IMDSv2** and configure appropriate network/hop limits.
- Grant the node IAM role only permissions needed by the node/agent, never broad business data permissions.
- Run Pods as non-root and restrict privilege escalation, hostNetwork/hostPID/hostPath.
- Do not treat containers as the sole security boundary; maintain processes to patch node OS/Kubernetes and container images.

### 14.3. Keep credentials out of logs

- Never print IRSA projected JWTs or Pod Identity tokens.
- Never `curl` the local credential endpoint and paste responses into tickets; responses contain secrets/tokens.
- Never place long-lived access keys into `ConfigMap`, `Kubernetes Secret`, Docker images, or manifests.
- Verify **STS caller ARN/account** instead of printing secret values.
- Never write pod service account tokens into persistent volumes, snapshots, or CI artifacts.

### 14.4. CloudTrail and Kubernetes auditing

CloudTrail logs AWS STS/role session API activity along with principal/session metadata. With Pod Identity, **session tags** for cluster, namespace, and SA/pod aid investigation by configuration. With IRSA, the role/session identity and STS `AssumeRoleWithWebIdentity` provide the audit trail.

Kubernetes control-plane audit logs are a **separate source** showing who created/modified ServiceAccounts/Deployments. Correlate CloudTrail, Kubernetes audit, CloudWatch, and EKS logs by timestamp/request IDs; never assume one tool captures events across every layer.

## 15. Networking: STS, EKS Auth, and Service Endpoints

### 15.1. IRSA requires STS

Pods using IRSA call `AssumeRoleWithWebIdentity` via STS. In private subnets without Internet egress, consider a regional STS interface VPC endpoint:

~~~text
com.amazonaws.ap-southeast-1.sts
~~~

Use the **regional STS endpoint**, ensuring Private DNS, TCP 443 security groups, routes/NACLs, and IAM policies. If the SDK is configured to call the global STS endpoint, it may bypass the regional private STS endpoint. When setting up the IAM OIDC provider, private-only networks must separately account for reaching the OIDC issuer/discovery endpoint from admin tooling.

### 15.2. Pod Identity requires EKS Auth

The Pod Identity Agent must call the EKS Auth API. On nodes without NAT/Internet egress, create the interface endpoint:

~~~text
com.amazonaws.ap-southeast-1.eks-auth
~~~

This **is not** the EKS Kubernetes API endpoint and is distinct from `com.amazonaws.ap-southeast-1.eks` for EKS management APIs. Ensure endpoint SGs, Private DNS, node IAM permission `eks-auth:AssumeRoleForPodIdentity`, and a healthy add-on.

### 15.3. Local agent and proxies

The SDK inside the Pod connects to `169.254.170.23`. If the Pod uses an HTTP proxy, add the local IP to `NO_PROXY`, e.g.:

~~~text
NO_PROXY=169.254.170.23,localhost,127.0.0.1
~~~

The agent configures an IPv6 listener on `fd00:ec2::23`; in environments with IPv6 disabled, update add-on settings accordingly. Never expose the agent endpoint to the Internet; it is a link-local credential service.

### 15.4. Valid credentials do not guarantee S3 access

Suppose a Pod has the right role, yet S3 calls time out. Inspect the **S3 Gateway/Interface VPC Endpoint**, NAT/routes, endpoint policy, and DNS. If S3 returns `AccessDenied`, check IAM permissions, bucket policies, KMS key policies, and exact action/resource keys. **STS/Pod Identity only solve credential delivery**, not network connectivity to S3/DynamoDB/Secrets Manager.

## 16. Cost, Availability, and Multi-Cluster Scale

| Component | Cost / Operational Consideration |
|---|---|
| EKS control plane | Cluster/support tier fees by version |
| EC2 worker nodes, Fargate, EKS Auto Mode | Compute and storage independent of identity |
| STS, EKS Auth | Rate limits, retry/backoff, and API usage policies |
| AWS PrivateLink interface endpoints | Endpoint-hours, data processing, and related fees |
| NAT Gateway | Egress/data processing if used instead of PrivateLink |
| CloudWatch, CloudTrail, EKS logs | Log/metrics ingestion, retention, queries |
| S3, DynamoDB, KMS | Business resource storage/API/KMS charges |

**Availability:** IRSA depends on projected tokens/STS; Pod Identity additionally depends on the **agent** and **EKS Auth**. Never re-instantiate AWS SDK clients/providers on **every request**, to avoid throttling and cold-start overhead. The SDK should cache temporary credentials, auto-refresh, and retry transient errors with backoff. If the agent fails on one node, workloads on that node may fail to fetch fresh credentials; multi-AZ/node spreading and agent monitoring matter.

**Scale:** Pod Identity simplifies trust policies across multiple clusters using a shared service principal, yet you still manage per-cluster/SA associations and scope IAM roles per workload. Multi-cluster setups should not reuse one overly broad role just to minimize IAM role count.

## 17. Common Errors

| Symptom | Possible Causes | How to Investigate |
|---|---|---|
| IRSA `InvalidIdentityToken` | Wrong OIDC issuer/provider, cluster recreated, mismatched token `aud` | EKS `identity.oidc.issuer`, IAM OIDC provider, and trust |
| IRSA `AccessDenied` at STS | `sub/aud` trust mismatch on namespace/SA or wrong role | Compare role ARN, trust conditions, ServiceAccount annotation |
| Pod still uses node role | Missing identity injection, IMDS accessible, SDK provider chain fallback | `serviceAccountName`, caller ARN, IMDS exposure |
| Pod Identity missing credentials | Missing association, agent not running, unsupported node compute | `list-pod-identity-associations`, DaemonSet/Auto Mode, node type |
| Agent cannot reach EKS Auth | Node role lacks `eks-auth:AssumeRoleForPodIdentity` or bad private endpoint/SG | IAM policy, `eks-auth` VPC endpoint, and DNS |
| Agent fails to start with IPv6 disabled | Agent configures IPv6 listener by default | Disable IPv6 in add-on config per AWS docs |
| HTTP proxy breaks local credentials | Missing `NO_PROXY` for `169.254.170.23` | Proxy settings; verify secure local connectivity |
| Valid Pod Identity association still uses IRSA | Old web identity env vars/annotations take precedence | Check provider precedence, roll Pods after removing annotation |
| Java SDK does not use Pod Identity | SDK version too old or custom provider | Upgrade AWS SDK Java v2 ≥ 2.21.30 and use default chain |
| Cross-account target role `AccessDenied` | Source role lacks AssumeRole, bad target trust/TagSession conditions | Check IAM in both accounts and `target-role-arn` |
| Pod calling S3 gets `AccessDenied` | Role lacks action, bucket/KMS policy denies | Actual role ARN, `s3:GetObject`, KMS/resource policies |
| Pod calling S3 times out | Missing S3 endpoint/network route | VPC, subnet routes, DNS, SG/NACL, NAT |
| `PackedPolicyTooLarge` | Session tags + policy payload exceed limit | Trim policies/tags |
| Fargate fails to run Pod Identity | **Not supported** | Use IRSA for EKS Fargate |
| New association not taking effect | Eventual consistency and old Pods lack injection | Allow propagation, create new Pods per runbook |
| Pod has right SA name, wrong namespace | Namespace/SA pair differs from association/trust | `kubectl get pod ... -o yaml` and EKS associations |

### 17.1. Investigation sequence

1. Identify **AWS account, Region, cluster, namespace, Pod, and ServiceAccount**.
2. Determine whether the Pod runs on Linux EC2/Auto Mode or Fargate/Windows.
3. Check OIDC annotation/provider (IRSA) or association/agent (Pod Identity).
4. Verify **actual caller ARN** and SDK credential provider precedence.
5. Cross-check IAM role trust + permissions, bucket/KMS policies, and conditions.
6. Verify network paths to STS/EKS Auth and specific service endpoints.
7. Inspect CloudTrail/EKS/CloudWatch logs; retry transient errors properly without opening wildcard permissions to test.

## 18. Read-Only Lab: Inspecting IAM Identity of an EKS Workload

**Prerequisites:** AWS CLI v2 profile `dev` with read permissions for AWS EKS/IAM; `kubectl` configured to read cluster `shop-cluster` in `ap-southeast-1`. Without a cluster, analyze the JSON/YAML examples in the lesson without creating infrastructure.

### Step A — Identify caller and cluster

~~~bash
aws sts get-caller-identity \
  --profile dev \
  --output json

aws eks describe-cluster \
  --name shop-cluster \
  --profile dev \
  --region ap-southeast-1 \
  --query 'cluster.{Name:name,Status:status,Version:version,Issuer:identity.oidc.issuer}' \
  --output json
~~~

### Step B — Read ServiceAccount and Deployment

~~~bash
kubectl get sa orders-api -n shop -o yaml

kubectl get deployment orders-api \
  -n shop \
  -o jsonpath='{.spec.template.spec.serviceAccountName}'

kubectl get pods -n shop -o wide
~~~

Check whether an IRSA annotation is present, which ServiceAccount the deployment uses, and which nodes the Pods run on. Do not infer “missing annotation” = “no AWS role” when Pod Identity is used.

### Step C — Inspect Pod Identity associations and agent

~~~bash
aws eks list-pod-identity-associations \
  --cluster-name shop-cluster \
  --profile dev \
  --region ap-southeast-1 \
  --output json

aws eks list-addons \
  --cluster-name shop-cluster \
  --profile dev \
  --region ap-southeast-1 \
  --output json

kubectl get daemonset eks-pod-identity-agent \
  -n kube-system -o wide
~~~

**With EKS Auto Mode**, you will not necessarily see the DaemonSet because the agent is built in. Without an association for the namespace/SA pair, the SDK has no basis to select Pod Identity for that Pod.

### Step D — Inspect the IAM role

~~~bash
aws iam get-role \
  --role-name OrdersReadOnlyPodRole \
  --profile dev \
  --query 'Role.{Arn:Arn,Trust:AssumeRolePolicyDocument}' \
  --output json

aws iam list-attached-role-policies \
  --role-name OrdersReadOnlyPodRole \
  --profile dev \
  --output json
~~~

To see all IAM permissions, you may also need to check **inline policies** via `list-role-policies/get-role-policy`. These commands are read-only, yet still require matching IAM permissions.

### Step E — Verify identity inside the Pod

If the container already includes AWS CLI and `kubectl exec` is authorized:

~~~bash
# Replace POD_NAME with the actual Pod name; never copy token contents.
kubectl exec -n shop POD_NAME -- aws sts get-caller-identity
~~~

If production containers lack CLI tools, use Java `GetCallerIdentity` code or an admin-approved diagnostic tool, recording only **ARN/account** and never temporary credentials.

### Step F — Verification table

| What to Verify | Data Source | Question |
|---|---|---|
| AWS account/cluster | `get-caller-identity` + `describe-cluster` | Is this the right environment? |
| Kubernetes workload identity | Pod + Deployment + ServiceAccount | Are Namespace/SA correct? |
| IRSA mapping | SA annotation + OIDC trust | Do `sub/aud` match? |
| Pod Identity mapping | EKS association + IAM trust | Are association/agent valid? |
| Effective IAM role | `sts get-caller-identity` inside Pod | Which role is the SDK using? |
| Authorization | IAM/bucket/KMS policies | Does the role have the right action/resource? |
| Networking | VPC endpoints, DNS, SGs | Can the Pod reach the service API? |

## 19. Scenarios and Self-Assessment Questions

### 19.1. Mechanism selection scenarios

**Scenario A:** Spring Boot running on EKS Linux managed node groups, needing to read S3, using a recent Java SDK v2. Pod Identity is generally well suited once the agent, IAM role, and EKS Auth endpoint are properly set up.

**Scenario B:** A batch job on EKS Fargate needs to read DynamoDB. Choose **IRSA**, because Pod Identity is not supported on Fargate.

**Scenario C:** A cluster in account A needs S3 in account B. With Pod Identity, use a source role in A and `--target-role-arn` in B, requiring source AssumeRole permission and target trust. With IRSA, use cross-account OIDC federation or role chaining per design.

**Scenario D:** A ServiceAccount already has a Pod Identity association, yet the caller remains the old IRSA role. Inspect `AWS_ROLE_ARN`/`AWS_WEB_IDENTITY_TOKEN_FILE`, remove the IRSA annotation, roll out new Pods, and verify the actual caller.

### 19.2. Questions

1. Why is a Kubernetes ServiceAccount not directly equivalent to an IAM role?
2. Which IAM trust principal and STS API does IRSA require?
3. How does `sub=system:serviceaccount:shop:orders-api` constrain permissions?
4. What is the Pod Identity trust principal? Why is `sts:TagSession` required?
5. Who calls `eks-auth:AssumeRoleForPodIdentity` and which IAM role needs that permission?
6. Which two environment variables help the SDK locate the Pod Identity Agent?
7. Why does Pod Identity not require an IAM OIDC provider for the cluster?
8. Is IRSA or Pod Identity suitable for Fargate Pods?
9. What is the minimum AWS SDK for Java v2 version required for Pod Identity?
10. Why might an SA with both an IRSA annotation and a new association continue using IRSA?
11. What does `--target-role-arn` do when accessing data in another account?
12. A Pod calling S3 times out; is broadening IAM permissions the first step?
13. What is the role of Kubernetes RBAC when a user can modify ServiceAccounts/Deployments?
14. Why must IMDS still be protected even after enabling IRSA/Pod Identity?
15. During migration, why shouldn't you delete the entire IAM OIDC provider immediately?
16. How do you verify the effective role without exposing tokens?

### Suggested answers

- **IRSA:** OIDC projected token → AWS STS `AssumeRoleWithWebIdentity` → temporary credentials.
- **Pod Identity:** EKS association → local agent → EKS Auth `AssumeRoleForPodIdentity` → temporary credentials.
- **Security:** IAM trust + permissions + Kubernetes RBAC + IMDS isolation + network path.
- **Operations:** default credentials provider chain, right SDK, actual role ARN, lifecycle refresh, CloudTrail, controlled rollout/rollback.

## 20. Official AWS Documentation

1. [IAM roles for service accounts](https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html) — IRSA architecture and OIDC.
2. [Assign IAM roles to Kubernetes service accounts](https://docs.aws.amazon.com/eks/latest/userguide/associate-service-account-role.html) — IRSA trust, annotations, and manifests.
3. [Create an IAM OIDC provider for your EKS cluster](https://docs.aws.amazon.com/eks/latest/userguide/enable-iam-roles-for-service-accounts.html) — Linking cluster issuer to IAM.
4. [Learn how EKS Pod Identity grants pods access to AWS services](https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html) — Fargate limits, node support, and associations.
5. [Understand how EKS Pod Identity works](https://docs.aws.amazon.com/eks/latest/userguide/pod-id-how-it-works.html) — Agent, EKS Auth, and environment variables.
6. [Set up the EKS Pod Identity Agent](https://docs.aws.amazon.com/eks/latest/userguide/pod-id-agent-setup.html) — Agent add-on, node IAM, VPC endpoint.
7. [Create IAM role for EKS Pod Identity](https://docs.aws.amazon.com/eks/latest/userguide/pod-id-role.html) — Service trust principal and session tags.
8. [Create/assign EKS Pod Identity association](https://docs.aws.amazon.com/eks/latest/userguide/pod-id-association.html) — Association API and Console.
9. [Use EKS Pod Identity with an AWS SDK](https://docs.aws.amazon.com/eks/latest/userguide/pod-id-minimum-sdk.html) — Java SDK v2 ≥ 2.21.30.
10. [Pod Identity target IAM roles and cross-account](https://docs.aws.amazon.com/eks/latest/userguide/pod-id-assign-target-role.html) — Role chaining in EKS.
11. [AWS CLI create-pod-identity-association](https://docs.aws.amazon.com/cli/latest/reference/eks/create-pod-identity-association.html) — Flags, target role, and session policy.
12. [Pod Identity session tags and ABAC](https://docs.aws.amazon.com/eks/latest/userguide/pod-id-abac.html) — Session tags and IAM conditions.
13. [EKS node IAM role](https://docs.aws.amazon.com/eks/latest/userguide/create-node-role.html) — `eks-auth:AssumeRoleForPodIdentity` permission.
14. [Identity and Access Management best practices for EKS](https://docs.aws.amazon.com/eks/latest/best-practices/identity-and-access-management.html) — Least privilege and IMDS.
15. [AWS SDK for Java v2 credentials provider chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html) — Provider precedence and refresh.
16. [AWS STS AssumeRoleWithWebIdentity](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRoleWithWebIdentity.html) — STS federation.
17. [Amazon EKS PrivateLink endpoints](https://docs.aws.amazon.com/eks/latest/userguide/vpc-interface-endpoints.html) — Connecting to EKS Auth API in a private VPC.
18. [Kubernetes ServiceAccounts](https://kubernetes.io/docs/concepts/security/service-accounts/) — Kubernetes identity and RBAC.
19. [AWS STS Regional endpoints](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp_enable-regions.html) — STS in Region.

> **Remember:** **IRSA** uses OIDC tokens and `AssumeRoleWithWebIdentity`; **EKS Pod Identity** uses EKS associations, the Pod Identity Agent, and EKS Auth. Both only reach full effectiveness when paired with **least-privilege IAM, RBAC, IMDS isolation, automatic SDK credential refresh, VPC endpoints, auditing, and controlled rollouts**.
