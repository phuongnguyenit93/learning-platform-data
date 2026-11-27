# Image Scanning and Access Control in Amazon ECR

A Java/Spring Boot application packaged as a container image typically includes the base operating system, Java Runtime, Maven/Gradle libraries, application code, and deployment configuration. An image may run fine on a developer's laptop while still containing **publicly disclosed security vulnerabilities (CVEs)** or being deployed to production from an untrusted source. When running containers on **Amazon Elastic Container Service (Amazon ECS)**, two questions must be solved in parallel:

1. **Is the image inspected and remediated for critical vulnerabilities before and after release?**
2. **Who is allowed to push images, who is allowed to pull images, and does ECS use the right identity to pull from the registry?**

**Amazon Elastic Container Registry (Amazon ECR)** is a managed registry service for container images and artifacts. For private repositories, ECR integrates with IAM, repository policies, image scanning, and AWS services such as ECS, Amazon Inspector, EventBridge, and CloudTrail. An image that passes a scan **does not automatically become completely secure**, just as successfully logging into a registry **does not automatically grant push/pull permissions to every repository**.

This lesson belongs to the **Containers with ECS** chapter of the **CLOUD_PROVIDERS_AWS** module. It connects to designing secure applications across Regions/AZs and VPCs, IAM roles, EC2/Fargate, S3-backed image layers, CI/CD, incident monitoring, availability, and cost control.

> **Principle:** Build once, scan the image, store by **digest**, release using a properly scoped IAM role, monitor for new CVEs, and rebuild images periodically. Permissions to **pull images for the ECS runtime** are separate from permissions to **call AWS APIs inside application code**.

## 1. Learning Outcomes

After this lesson, learners will be able to:

1. Explain the relationship among an ECR private registry, repository, image tag, and image digest.
2. Distinguish **Basic scanning** from **Enhanced scanning (Amazon Inspector)**, as well as manual, scan-on-push, and continuous modes.
3. Read and evaluate scan status, severity, CVE, affected package, and patch availability.
4. Understand why `DescribeImageScanFindings` is the right API to inspect scan results, including with newer Basic scanning.
5. Describe permissions required to push and pull images, including `ecr:GetAuthorizationToken`, repository actions, and repository resource policies.
6. Distinguish **ECS task execution role**, **ECS task role**, and **container instance IAM role** by launch type.
7. Design cross-account ECR access and private subnet networking via ECR VPC endpoints/S3 Gateway Endpoint.
8. Build a build–scan–approve–deploy pipeline with security gates, rollbacks, and monitoring for newly disclosed vulnerabilities.
9. Inspect repositories, image digests, scanning configuration, findings, and policies via the AWS CLI without modifying resources.

## 2. Where ECR Fits in the ECS Ecosystem

A system can run the following pipeline:

~~~mermaid
flowchart LR
    D["Developer / Git repository"] --> CI["CI: build and test"]
    CI --> SB["Check dependencies, secrets, SBOM"]
    SB --> ECR["Amazon ECR private repository"]
    ECR --> SC["Basic scan or Amazon Inspector"]
    SC --> G["Security gate / release decision"]
    G --> TD["ECS task definition: image digest"]
    TD --> ECS["ECS service on Fargate/EC2"]
    ECS --> ALB["ALB + Route 53 / CloudFront"]
    ECR --> EB["EventBridge / new findings"]
    EB --> SEC["Security triage / rebuild / patch"]
~~~

**ECR stores images**, **ECS runs tasks/services**, **IAM controls access**, and **Amazon Inspector** provides advanced vulnerability analysis. For a task to pull an image, three independent conditions must hold: the image exists in the repository/Region, the runtime has IAM permissions, and the task has a **valid network path** to ECR and its backing layer store.

### 2.1. Registry, Repository, Tag, and Digest

An ECR private registry is scoped to an **AWS account and Region**; each registry contains multiple repositories. For example:

~~~text
111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/platform/orders-api:1.2.3
|---------- registry endpoint -----------------| |----- repo -------| |tag|
~~~

- `111122223333`: **illustrative** AWS account owning the registry.
- `ap-southeast-1`: Region of the ECR repository.
- `platform/orders-api`: repository name, not a directory on EC2.
- `1.2.3`: **image tag**, a label that can be reassigned if the repository permits mutable tags.
- `sha256:...`: **image digest**, a content identifier of the manifest; suited for pinning the exact scanned/approved image build.

**A tag is not a digest.** If the `stable` tag is moved to a different image, deployments reading the tag at two different times can receive different content. When provenance and reproducibility are required, pin images by **digest**, or strictly enforce tag immutability and record the digest at approval time.

### 2.2. Private vs. Public ECR

This lesson focuses on **Amazon ECR private repositories** used with ECS. Amazon ECR Public has its own endpoints, IAM actions (e.g., `ecr-public:` prefix), and sharing semantics. Do not copy ECR private policies directly to ECR Public without verifying the corresponding action names and registry details.

## 3. Why Must Container Images Be Scanned?

A Java image typically contains:

- **Base image**: e.g., Linux distribution, OpenSSL, libc, curl, shell packages.
- **Java runtime**: JRE/JDK, CA certificates, system libraries.
- **Dependencies**: Spring Boot, Spring Framework, Jackson, Netty, and transitive libraries inside JARs.
- **Application code**: business logic, configuration, endpoints.
- **Artifacts**: config files, scripts, and sometimes secrets accidentally baked into the image.

A new release might patch a CVE in the base image while introducing a new vulnerability via a dependency. Conversely, **a CVE can be published after an image is already deployed**; scanning once at build time is not enough to guarantee future safety.

### 3.1. Protection Layers and Limitations

| Mechanism | What it detects/prevents | What it does not replace |
|---|---|---|
| ECR **Basic scanning** | Certain CVEs in supported OS packages | Full scanning of all Java libraries, runtime config, and security logic |
| ECR **Enhanced scanning** | OS CVEs and many programming-language packages supported by Amazon Inspector | Pentesting, API testing, comprehensive secrets detection |
| CI SBOM/dependency scanner | Packages/dependencies and supply-chain policy | Runtime IAM permissions and network security |
| Image signing/attestation | Origin and integrity under signing/verification policy | Automatically patching vulnerabilities |
| IAM/repository policy | Who can push/pull/manage images | Ensuring the image has no CVEs or secure app config |
| ECS runtime/OS hardening | Restricting process privileges, network, secrets, filesystem | Application code security testing |

A result of **0 Critical findings** does not prove "the image is completely free of vulnerabilities." It could mean the scanner does not support that OS/package, the scan is still pending, the image is archived, the feed lacks coverage, scan scope is incomplete, or findings have not updated yet.

## 4. Basic Scanning and Enhanced Scanning

According to current AWS documentation, ECR provides two scanning types for **private registries**:

| Attribute | **Basic scanning** | **Enhanced scanning** |
|---|---|---|
| Technology | AWS-native scanning | Integrated with **Amazon Inspector** |
| Primary detection scope | CVEs in **OS packages** | CVEs in supported **OS and programming-language packages** |
| Modes | **Manual** or **Scan on push** | **Scan on push** or **Continuous scanning** |
| New CVEs after push | Does not automatically re-evaluate continuously | **Continuous** mode monitors and updates findings when relevant CVEs emerge |
| Manual scan | Yes, when Basic scanning allows | **No** manual enhanced scan via ECR |
| Configuration scope | **Registry scanning configuration**, repository filters within the Region | **Registry scanning configuration**, Inspector activation, and filters within the Region |
| Results | ECR `DescribeImageScanFindings` | ECR findings plus deeper details in Amazon Inspector |
| Cost | Per current Basic pricing/quotas | May incur Amazon Inspector scanning/monitoring charges |

### 4.1. Default Basic Scanning Does Not Mean Every Push Is Scanned

**Basic scanning is enabled by default for private registries**, but repositories **not matching a scan-on-push filter** usually stay in **manual** mode—meaning a scan must be explicitly triggered. To scan automatically on every push, administrators must enable **scan on push** for matching repositories or across the registry via scanning rules.

With Basic scanning, AWS enforces per-image scan frequency limits and registry-wide quotas per documentation; do not design CI to loop manual scans indefinitely if a scan ran recently. Basic scanning may also not support certain OSes or image formats.

### 4.2. Enhanced Scanning and Amazon Inspector

Enhanced scanning requires enabling Amazon Inspector integration for the registry in that Region. Amazon Inspector can:

1. Perform an initial scan of newly pushed images in repositories matching the filter scope.
2. Inspect vulnerability data for OS and supported programming-language packages.
3. Detect/update findings when the CVE database adds new disclosures under **continuous scanning** while the image remains within the monitoring window.
4. Emit scan/finding events to **EventBridge** for triage, ticketing, or notification workflows.

Amazon Inspector uses a **service-linked role** when activated. Under **Enhanced scanning**, repositories **not matching any filter** can remain **Off**; when a repository matches both continuous and scan-on-push filters, **continuous takes precedence**. Never assume enabling Enhanced at the account level automatically scans every repository.

### 4.3. Eligibility Window and Impact of Switching Scan Types

When Enhanced scanning is first enabled, AWS applies eligibility rules for older images; AWS documentation notes Inspector initially recognizes images pushed within the **last 14 days**. Older images may show `SCAN_ELIGIBILITY_EXPIRED` and need to be re-pushed to be scanned within the active scope. Re-scan/monitoring durations can depend on Inspector policy settings.

Switching between **Basic** and **Enhanced** alters the availability of previously completed scans; switching back to the prior type may let you view older scans again. **Do not casually flip scan types in production** just to query CLI output: this is a **registry-level setting per Region**, affecting many repositories.

**Archived images are not scanned** while archived; they must be restored first before scanning under supported conditions.

## 5. Reading Vulnerability Findings Properly

A finding can include the following attributes:

| Attribute | Meaning |
|---|---|
| **CVE** | Vulnerability identifier in databases, e.g., `CVE-20XX-XXXXX` |
| **Severity** | Rating assigned by scanner/provider, such as `CRITICAL`, `HIGH`, `MEDIUM` |
| **Affected package/version** | OS package or library within the affected version range |
| **Fixed version / remediation** | Patched version or advisory if released by the vendor |
| **Image digest** | The exact image build affected |
| **Status/time** | Scan/finding state and update timestamp |
| **Inspector risk context** | Prioritization context based on exploitability/environment data when available |

### 5.1. Severity Alone Is Not the Entire Release Decision

For example, an image might have a `CRITICAL` CVE in an OS package whose code path the app never executes, alongside a `HIGH` CVE in a web library directly parsing user input. Security teams must assess:

- Actual exploitability and exposure surface.
- Whether the package is actively used and whether the vulnerable code is reachable.
- Whether a fix/patch exists.
- Data sensitivity, runtime privileges, and network reachability.
- Remediation deadlines per enterprise policy, and time-bound exceptions with an owner/expiry.

Do not blindly ignore every `MEDIUM` finding, nor block every image forever over an unpatched CVE. Establish a **transparent triage policy with remediation SLAs and approved exceptions**.

### 5.2. New CVEs Disclosed After ECS Is Already Running

If a tag/digest was deployed yesterday and a new CVE is disclosed today, **continuous Enhanced scanning** can update the finding, but it **does not automatically rebuild, patch images, or restart ECS services**. The standard workflow is: update base image/dependency → rebuild → re-scan → deploy new image digest → monitor health → roll back if needed.

## 6. Configuring Scanning in the ECR Console

### 6.1. Confirming Registry and Region

1. Sign in to the AWS Console with the proper account/role, preferring IAM Identity Center and MFA.
2. Open **Amazon ECR → Private registry → Scanning**.
3. Select the **Region** containing the target repository; scanning configuration is managed per registry/Region.
4. Check the current **scan type**: Basic or Enhanced.
5. Inspect **repository filters** and scan frequency before concluding images will be scanned on push.
6. For Enhanced scanning, verify Amazon Inspector is enabled with active coverage/eligibility.

### 6.2. Example Configuration by Environment

| Repository Group | Suggested Option | Rationale |
|---|---|---|
| `dev/*` with many short-lived images | Basic scan-on-push or Enhanced per risk tier | Early detection while controlling scan volume |
| `staging/*` | Enhanced scan-on-push | Scan OS and language packages prior to promotion |
| `production/*` | Enhanced **continuous** | Monitor newly disclosed CVEs after deployment |
| Archived non-deployable images | Lifecycle/archiving per policy | Optimize storage and tracking scope; archived images cannot be scanned |

This is only a **starting pattern**. Organizations may share one repository across environments and promote by digest; in that case, filters cannot rely simply on `dev/*` or `production/*` naming.

### 6.3. Reading Scan Results in the Console

Go to **ECR → Private repositories → select repository → Images**, and locate the image by **digest or tag**. Open image details to view scan findings, vulnerability severities, and scan status. With Enhanced scanning, links from findings can open **Amazon Inspector** to inspect affected packages and context.

Do not confuse **image pushed** with **image scan completed**. Because scanning is asynchronous, a pipeline must **wait for a valid completed scan state** before making a release decision. If scan status is unsupported/expired/pending/failed, never treat that as "zero CVEs."

## 7. AWS CLI: Safely Inspecting Scanning Configuration and Findings

The commands below are **read-only**, assuming:

- Source ECR account: `111122223333` (**illustrative**).
- Region: `ap-southeast-1`.
- Repository: `platform/orders-api`.
- Image tag: `1.2.3`.
- AWS CLI profile `dev` has appropriate read permissions.

### 7.1. Verify Caller Identity First

~~~bash
aws --version
aws sts get-caller-identity \
  --profile dev \
  --query '{Account:Account,Arn:Arn}' \
  --output json
~~~

If the account ID does not match expectations, **do not proceed to alter ECR settings or deploy**. Another account might have a repository with the same name containing completely different images.

### 7.2. List Repositories and Image Details

~~~bash
aws ecr describe-repositories \
  --profile dev \
  --region ap-southeast-1 \
  --query 'repositories[].{Name:repositoryName,Uri:repositoryUri,TagMutability:imageTagMutability,Encryption:encryptionConfiguration.encryptionType}' \
  --output table

aws ecr describe-images \
  --repository-name platform/orders-api \
  --profile dev \
  --region ap-southeast-1 \
  --query 'imageDetails[].{Digest:imageDigest,Tags:imageTags,PushedAt:imagePushedAt,SizeBytes:imageSizeInBytes}' \
  --output json
~~~

Image sizes in ECR reflect **compressed layers**, differing from local Docker image sizes. `describe-images` is paginated; do not pass `--no-paginate` and assume partial output is complete.

### 7.3. Read Registry Scanning Configuration

~~~bash
aws ecr get-registry-scanning-configuration \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

Output shows `scanType` (`BASIC` or `ENHANCED`) and `rules` with `scanFrequency`/`repositoryFilters` when configured. If no filter matches the repository being deployed, check the corresponding **manual/off** behavior before assuming the pipeline scans automatically.

### 7.4. View Scan Findings for the Exact Image

~~~bash
aws ecr describe-image-scan-findings \
  --repository-name platform/orders-api \
  --image-id imageTag=1.2.3 \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

When tags may be reassigned, query by **image digest** obtained from `describe-images`:

~~~bash
aws ecr describe-image-scan-findings \
  --repository-name platform/orders-api \
  --image-id imageDigest=sha256:REPLACE_WITH_REAL_IMAGE_DIGEST \
  --profile dev \
  --region ap-southeast-1 \
  --query '{Status:imageScanStatus,SeverityCounts:imageScanFindings.findingSeverityCounts,Enhanced:registryId}' \
  --output json
~~~

`REPLACE_WITH_REAL_IMAGE_DIGEST` is a placeholder. In API responses, findings may appear under `imageScanFindings.findings` or `imageScanFindings.enhancedFindings` depending on scan type and API version. For Enhanced scanning, Amazon Inspector provides additional detail.

**Important update:** the newer **AWS-native Basic scanning** no longer returns complete results via `imageScanFindingsSummary` and `imageScanStatus` in `DescribeImages`. When fetching scan results, use **`DescribeImageScanFindings`**. Empty scan status fields in `describe-images` do not prove the image was never scanned.

### 7.5. Triggering a Manual Scan with Basic Scanning

The following command **mutates scan state** and is not part of a read-only lab:

~~~bash
# ILLUSTRATIVE ONLY for Basic scanning and eligible images
aws ecr start-image-scan \
  --repository-name platform/orders-api \
  --image-id imageTag=1.2.3 \
  --profile dev \
  --region ap-southeast-1
~~~

Run this only when the repository uses **Basic scanning** and the operator has permissions/quota. **Enhanced scanning does not support starting manual scans via this mechanism.** Do not call it in a tight loop every few seconds; Basic scanning enforces per-image scan limits and registry-wide quotas.

## 8. Access Policies for ECR: Identity and Repository

There are two primary layers:

1. **IAM identity-based policy:** attached to an IAM user/role, restricting which ECR APIs a user, CI role, or ECS execution role may call.
2. **ECR repository resource-based policy:** attached to **a specific repository**, defining which principals can perform which actions on that repository—especially useful for **cross-account access**.

IAM/SCPs/permissions boundaries and explicit denies can still restrict access. ECR documentation notes that within the same account, an appropriate **allow** in either the IAM policy **or** the repository policy can permit repository actions if not denied. Cross-account access requires evaluating **both the caller's permissions and the resource policy in the repository-owning account**; never rely on a single allow without verifying both sides.

### 8.1. `ecr:GetAuthorizationToken` Differs from Pull/Push Permissions

The ECR Docker registry requires authentication. `ecr:GetAuthorizationToken` obtains the **registry login token** and **must** be allowed by an **IAM identity-based policy**, using:

~~~json
{
  "Effect": "Allow",
  "Action": "ecr:GetAuthorizationToken",
  "Resource": "*"
}
~~~

`Resource: "*"` is required because this action does not support scoping to a repository ARN; it does not grant the caller access to every repository. Standard ECR private registry tokens from `GetAuthorizationToken`/`get-login-password` are valid for **12 hours**, and effective permissions never exceed the IAM principal's policies.

A successful `docker login` only proves a valid registry token was issued. **Push/pull can still fail with AccessDenied or 403** if repository-level actions are missing.

### 8.2. Least-Privilege Permissions to Pull Images

Common actions:

| Action | Purpose |
|---|---|
| `ecr:GetAuthorizationToken` | Obtain private registry login token |
| `ecr:BatchGetImage` | Fetch image manifest by tag/digest |
| `ecr:GetDownloadUrlForLayer` | Obtain download URL for image layers |
| `ecr:BatchCheckLayerAvailability` | Check layer availability in certain client flows |

For a standard ECS execution role, the core permissions are `GetAuthorizationToken`, `BatchGetImage`, and `GetDownloadUrlForLayer`. Scope read/pull permissions to **specific repositories**; never grant `ecr:PutImage` to a runtime that only needs to pull.

### 8.3. Permissions Required to Push Images

A CI pipeline pushing images typically needs:

- `ecr:BatchCheckLayerAvailability`.
- `ecr:InitiateLayerUpload`.
- `ecr:UploadLayerPart`.
- `ecr:CompleteLayerUpload`.
- `ecr:PutImage`.
- `ecr:BatchGetImage` in certain Docker/push workflows.
- `ecr:GetAuthorizationToken` on `Resource: "*"`.

Example IAM permissions for a CI role limited to pushing to a single repository, **without delete-repository or policy-change rights**:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "RegistryLogin",
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    },
    {
      "Sid": "PushOnlyApprovedRepository",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:PutImage",
        "ecr:BatchGetImage"
      ],
      "Resource": "arn:aws:ecr:ap-southeast-1:111122223333:repository/platform/orders-api"
    }
  ]
}
~~~

If CI uses a role from another account, in addition to CI's identity policy, an **ECR repository policy** may be required for cross-account pushes along with relevant guardrails/conditions.

## 9. Distinguishing ECS Task Execution Role, Task Role, and Instance Role

This is the most common IAM mistake with ECS + ECR.

| Identity / Role | Used by whom? | Common tasks |
|---|---|---|
| **Task execution role** (`executionRoleArn`) | ECS/Fargate agent or runtime on behalf of the task | Pull images from ECR, send logs to CloudWatch Logs, fetch secrets for container startup when supported |
| **Task role** (`taskRoleArn`) | **Application code inside the container** | Read S3, DynamoDB, SQS, Secrets Manager, call business AWS APIs |
| **Container instance IAM role** | EC2 host registered to an ECS cluster (EC2 launch type) | ECS agent registers/manages the container instance; may participate in ECR image pulls depending on ECS agent/launch type |
| **CI/CD role** | Build/push/deploy pipeline | Push images, register task definitions, update ECS services per granted permissions |
| **ECR repository policy** | Resource policy on an ECR repository | Allow/deny principals, especially cross-account |

### 9.1. With Fargate: The Execution Role Handles Pulling

Example ECS task definition:

~~~json
{
  "family": "orders-api",
  "requiresCompatibilities": ["FARGATE"],
  "networkMode": "awsvpc",
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "arn:aws:iam::111122223333:role/EcsExecutionPullRole",
  "taskRoleArn": "arn:aws:iam::111122223333:role/OrdersApiTaskRole",
  "containerDefinitions": [
    {
      "name": "orders-api",
      "image": "111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/platform/orders-api:1.2.3",
      "essential": true,
      "portMappings": [
        { "containerPort": 8080, "protocol": "tcp" }
      ]
    }
  ]
}
~~~

This is a **minimal task definition example** to illustrate roles/images. IAM ARNs, accounts, and tags are illustrative, and a real task also needs VPC subnets/security groups, target groups, logging, and deployment settings.

`executionRoleArn` needs permissions to pull from ECR. `taskRoleArn` grants Spring Boot permissions to call business APIs, such as `s3:GetObject` on a specific bucket. **Do not grant `ecr:PutImage` to the task role** simply because the task runs an ECR image.

### 9.2. With ECS Running on EC2

The ECS EC2 launch type has a host **container instance IAM role** used for ECS agent operations and potentially image pulls depending on configuration; the task execution role also plays a role in modern ECS workflows. Verify **the agent, launch type, image pull mechanism, and actual permissions** rather than assuming identical behavior to Fargate. Application containers still use their own **task role** to access AWS APIs.

For high-security workloads, avoid using a broad EC2 instance role in place of scoped per-task permissions.

### 9.3. Sample Execution Role Policy for Fargate Pulling ECR

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "GetRegistryLogin",
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    },
    {
      "Sid": "PullOrdersApiOnly",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchGetImage",
        "ecr:GetDownloadUrlForLayer"
      ],
      "Resource": "arn:aws:ecr:ap-southeast-1:111122223333:repository/platform/orders-api"
    }
  ]
}
~~~

The managed policy **`AmazonECSTaskExecutionRolePolicy`** includes permissions for common ECR pulls and CloudWatch Logs, but because it covers all repositories under its baseline rules, organizations with strict least-privilege requirements often use/customize a tighter policy.

## 10. Cross-Account ECR Pull: A Two-Account Diagram

Suppose:

- **Account A (111122223333)** hosts ECR repository `platform/orders-api` in Singapore.
- **Account B (444455556666)** runs ECS Fargate with role `EcsExecutionPullRole`.
- Requirement: B can **pull only A's repository** to run tasks; B cannot push/overwrite images.

~~~mermaid
flowchart TD
    R["Account A: ECR repository platform/orders-api"]
    P["Repository policy: allow execution role B to pull"]
    B["Account B: ECS Fargate task"]
    X["Task execution role in Account B"]
    I["IAM: GetAuthorizationToken + pull repository A"]
    A["Task role: business AWS APIs"]
    R --> P
    X --> I
    B --> X
    P -->|"Repository allow + identity allow"| B
    B --> A
~~~

### 10.1. Repository Policy in Account A

Example **resource policy attached to the repository**:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowAccountBExecutionRolePull",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::444455556666:role/EcsExecutionPullRole"
      },
      "Action": [
        "ecr:BatchGetImage",
        "ecr:GetDownloadUrlForLayer"
      ],
      "Resource": "*"
    }
  ]
}
~~~

Inside a **repository policy** attached to a single ECR repository, `Resource: "*"` scopes to the repository holding the policy; it does not grant access to other repositories. This matches official AWS example syntax. `ecr:GetAuthorizationToken` is **not** granted via a repository policy; it belongs in role B's **identity policy**.

### 10.2. IAM Identity Policy in Account B

Attached to the ECS execution role in Account B:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EcrLogin",
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    },
    {
      "Sid": "PullCrossAccountOrdersApi",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchGetImage",
        "ecr:GetDownloadUrlForLayer"
      ],
      "Resource": "arn:aws:ecr:ap-southeast-1:111122223333:repository/platform/orders-api"
    }
  ]
}
~~~

When SGs/VPC routing are valid and ECR holds the image in the right Region, Fargate task B can pull via the execution role under this policy design. In real environments, also evaluate SCPs, permissions boundaries, deny statements, endpoint policies, and ECR repository policies. Account B must also have the Region enabled if required by Region/feature rules.

### 10.3. Common Mistakes

- **B has `GetAuthorizationToken`, A omits repo permission:** login succeeds, but pull fails with 403.
- **A allows role B to pull, role B lacks `GetAuthorizationToken`:** runtime cannot authenticate to the registry.
- **A grants access to Account B root instead of the specific role:** scope may be broader than intended; review policy.
- **Task role has permissions while execution role lacks them:** container fails to start even with broad app role permissions.
- **Same-named repository in another account/Region:** manifest not found, task hits wrong endpoint, or `CannotPullContainerError`.

## 11. Docker Login, Push, and Pull in Practice

The commands below are **operational syntax with real side effects**. Running them requires the AWS CLI, Docker, an authorized IAM profile, and an approved repository.

### 11.1. Logging Into Private ECR by Region

~~~bash
aws ecr get-login-password \
  --profile ci \
  --region ap-southeast-1 \
  | docker login --username AWS --password-stdin \
      111122223333.dkr.ecr.ap-southeast-1.amazonaws.com
~~~

`get-login-password` uses current AWS credentials to retrieve a **12-hour token**. It passes the password over standard input to avoid exposing it on the command line. Docker may store registry credentials locally or in a credential store; use an appropriate credential helper and never copy `~/.docker/config.json` containing credentials into artifacts or CI logs.

ECR private tokens are retrieved per Region via `get-login-password`, so match the **Region to the registry endpoint**. Holding a valid token never bypasses IAM permissions.

### 11.2. Build, Tag, and Push an Image

~~~bash
# Example for CI authorized to push; may incur ECR storage fees.
docker build -t orders-api:1.2.3 .

docker tag orders-api:1.2.3 \
  111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/platform/orders-api:1.2.3

docker push \
  111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/platform/orders-api:1.2.3
~~~

After pushing, read the image digest and scan status. Never assume `docker push` succeeding means the image passed the **security gate**. For production releases, use the digest and a review workflow to ensure ECS runs the exact inspected build.

### 11.3. Pulling an Authorized Image

~~~bash
docker pull \
  111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/platform/orders-api:1.2.3
~~~

If pulling succeeds on a laptop but fails on an ECS task, compare the **different IAM principals**: the laptop uses a developer role, whereas Fargate uses the **task execution role**. Always verify permissions and networking from the ECS environment, not just a personal workstation.

## 12. ECR in a VPC Private Subnet: IAM Permissions and Network Path

An ECS Fargate task can run in private subnets **with no public IP**. If the subnet has no NAT/Internet egress, image pulls can still work over **AWS PrivateLink / VPC endpoints** when fully configured.

With Linux Fargate platform version **1.4.0 or later**, using ECR private VPC endpoints typically requires:

| Endpoint | Type | Role |
|---|---|---|
| `com.amazonaws.ap-southeast-1.ecr.api` | Interface | ECR API, token/metadata actions |
| `com.amazonaws.ap-southeast-1.ecr.dkr` | Interface | Docker registry API for image pulls |
| `com.amazonaws.ap-southeast-1.s3` | **Gateway endpoint** | Access S3-backed image layers during pull |

Fargate platform version 1.3.0 or older has different endpoint requirements; consult the corresponding AWS documentation. If tasks also use CloudWatch Logs, Secrets Manager, or SSM Parameter Store over a private network, **corresponding endpoints** or valid NAT egress may be required.

### 12.1. Connectivity Checklist

1. **VPC/Subnet/route table:** the S3 Gateway Endpoint is associated with the required route tables.
2. **Private DNS:** enabled on ECR interface endpoints so the runtime resolves the private endpoint properly.
3. **Endpoint Security Group:** allows TCP 443 from task ENIs per subnet/SG design.
4. **Execution IAM role and repository policy:** permit the exact required ECR actions.
5. **Endpoint policy:** does not block the repository or account in use.
6. **DNS resolution:** VPC attributes/Route 53 Resolver do not break endpoint hostnames.
7. **Cross-account/cross-Region:** endpoints and network paths serve the registry's actual Region.
8. **S3 layer delivery:** S3 access for layers must exist; having only the ECR API endpoint is not enough.

**Note:** the first image pull via ECR pull-through cache or certain foreign-layer mechanisms may require Internet egress per service documentation; do not assume three endpoints suffice for every upstream image source. Test the topology with your actual launch type and image source.

### 12.2. Distinguishing Three Pull Failure Categories

| Symptom | First Suspicions |
|---|---|
| `ResourceInitializationError` fetching auth | `GetAuthorizationToken`, execution role, or ECR API endpoint |
| Connection timeout to registry | ECR DKR/API endpoint, DNS, routes, SG/NACL, NAT |
| Auth succeeds, but manifest/layer gets 403 | `BatchGetImage`, `GetDownloadUrlForLayer`, repository policy, endpoint policy |
| Unable to download layers | S3 endpoint/NAT/route or required ECR permissions |
| Image/tag does not exist | Wrong account/Region/repository/tag/digest |
| Task runs, but app fails calling S3 | **Application task role**, not the ECR execution role |

## 13. Designing a Release Gate from Scan Findings

A well-controlled pipeline can use these stages:

~~~mermaid
flowchart TD
    C["Commit"] --> B["Build + unit/integration tests"]
    B --> S["Dependency scan / SBOM / secrets checks"]
    S --> P["Push image with unique tag to ECR"]
    P --> Q["Wait for ECR/Inspector scan to complete"]
    Q --> D{"Does result meet release policy?"}
    D -->|"Pass or valid exception"| R["Record approved image digest"]
    D -->|"Fail"| F["Block promotion, create remediation ticket"]
    R --> E["ECS task definition uses image digest"]
    E --> H["Canary/rolling deploy + health checks"]
    H --> M["Monitor CloudWatch and new CVEs"]
    M --> U["Rebuild/patch/rollout on new findings"]
~~~

### 13.1. An Illustrative Policy Gate

This is **one team's example**, not a mandatory AWS standard:

- **Block** if the scan is incomplete/eligibility expired/unsupported for required image layers.
- **Block or require an exception** for Critical vulnerabilities that are exploitable within the app's exposure surface.
- **Enforce remediation SLAs** by risk level for High/Medium findings.
- **Store evidence:** image digest, commit SHA, scan type, scan timestamp, finding counts, exception owner, and expiration date.
- **Re-evaluate** when new CVEs affect already-deployed images.

**Never deploy via the mutable `latest` tag** after scanning `latest` earlier. The pipeline must bind the **image digest** of the exact scanned image to the deployed task definition.

### 13.2. Things a Gate Must Never Assume

- `scan completed` does not mean `0 findings`.
- `0 findings` does not mean every OS/framework/dependency was supported and checked.
- A scan finishing before deploy does not mean the image was signed or source code was reviewed.
- ECR image scanning does not clean up secrets, malware, runtime CVEs, or IAM misconfigurations.
- New post-release CVEs require continuous detection and remediation; running old tasks never patches code automatically.

## 14. EventBridge, Amazon Inspector, and CloudTrail

### 14.1. Events When Scanning Completes

With **Basic scanning**, Amazon ECR can emit events to EventBridge such as:

~~~json
{
  "source": "aws.ecr",
  "detail-type": "ECR Image Scan",
  "detail": {
    "scan-status": "COMPLETE",
    "repository-name": "platform/orders-api",
    "image-digest": "sha256:EXAMPLE_IMAGE_DIGEST"
  }
}
~~~

This is an **abbreviated event sample**, not a complete production payload.

With **Enhanced scanning**, **Amazon Inspector** emits events when initial scans finish or findings are created/updated/closed. Common EventBridge patterns include:

~~~json
{
  "source": ["aws.inspector2"],
  "detail-type": ["Inspector2 Scan", "Inspector2 Finding"]
}
~~~

You can route EventBridge → Lambda/Step Functions/SNS/Security Hub to update tickets, notify owners, or flag rebuilds. When handling events, enforce idempotency, IAM scoping, rate limiting, and distinguish lifecycle events from **current scan state** queried from ECR/Inspector APIs.

### 14.2. CloudTrail and Audit Responsibility

CloudTrail can record ECR management APIs such as `PutImage`, `SetRepositoryPolicy`, `PutRegistryScanningConfiguration`, and `BatchDeleteImage` depending on event logging configuration. When investigating an overwritten image, correlate actor/principal, timestamp, Region, repository, and image digest. Never treat a tag as the unique ID of a release event.

### 14.3. Practical Monitoring

- Percentage of production images with recent/successful scans.
- Count and age of open Critical/High findings.
- Unscanned, unsupported, or eligibility-expired images.
- Counts of `CannotPullContainerError`/`ResourceInitializationError` tasks.
- Time from CVE fix availability to image rebuild and deployment.
- Uncleaned old images/layers, ECR storage usage, and Inspector/CloudWatch costs.

## 15. Repository Governance: Immutable Tags, Lifecycle, and Encryption

### 15.1. Tag Immutability

When a repository sets an **IMMUTABLE** tag policy, clients cannot overwrite an existing tag; ECR returns an error on re-push under active rules. Some newer configurations support intentional exclusions, so check the exact repository setting.

- Prefer tags carrying commit/release identifiers, such as `1.2.3-9af15d`.
- Record the image **digest** in release manifests, task definitions, and audit records.
- Do not use mutable `latest` as a release anchor.
- Manage tag policies via IaC/approvals rather than ad-hoc manual edits outside the pipeline.

**Tag immutability does not replace digest pinning**, nor does it prove an image was scanned.

### 15.2. Lifecycle/Archiving

ECR lifecycle policies can clean up unneeded old images by count/age/tag or supported criteria. However:

- Deleting an **image digest** still needed by new tasks can break scale-out or recovery.
- Keeping too many images/layers increases storage cost.
- Unrestored archived images have pull/scan restrictions; verify the restore procedure before relying on them for production.
- Retain **active releases, rollback candidates, and policy-mandated retention**.

### 15.3. Encryption and KMS Permissions

ECR supports encryption at rest for stored images using options such as AWS-managed encryption or **AWS KMS** when selected. With a KMS customer managed key, administrators must check the key policy, grants, and KMS permissions. Encryption **at rest** protects stored registry contents by design, but does not fix CVEs in the image or guarantee safe container execution.

## 16. Cost and Multi-Region Operations

| Cost Source | What to Watch |
|---|---|
| **ECR storage** | Stored image/layer volume, storage class/tiering if applicable |
| **Amazon Inspector** | Enhanced scanning, monitoring/re-scans at current pricing |
| **Data transfer** | Cross-Region/cross-account/Internet traffic and layer fetch paths |
| **VPC Interface Endpoints** | Endpoint-hours and data processed |
| **NAT Gateway** | Data processing charges if image pulls traverse NAT |
| **CloudWatch/CloudTrail/EventBridge** | Logs, metrics, event processing, and audit storage |
| **ECS Fargate/EC2** | Task/service compute, independent of the ECR registry |

For multi-Region ECS deployments, you can use **ECR replication rules** or pipeline pushes/promotions per Region, but verify permissions, digest consistency, replication timing, and **target Region scanning configuration**. Creating a repository in Singapore does not automatically make images appear in Tokyo without replication/copying.

Avoid forcing cross-Region image pulls across every task when replication and release policies can avoid it; evaluate deployment latency, networking, cost, and availability.

## 17. Troubleshooting by Error Category

| Symptom | Common Causes | Verification |
|---|---|---|
| `no basic scan findings` despite push | Repository still on manual scan; Basic not triggered; scan pending/unsupported | `get-registry-scanning-configuration` then `describe-image-scan-findings` |
| `DescribeImages` lacks `imageScanFindingsSummary` | Newer Basic scanning omits this field | Use `DescribeImageScanFindings` |
| `SCAN_ELIGIBILITY_EXPIRED` | Image outside Inspector monitoring/eligibility window | Check Inspector coverage/duration; consider pushing a fresh image |
| `UNSUPPORTED_IMAGE` | OS/package/media type outside scanner scope | Check AWS supported images/OSes; scan additionally in CI |
| `StartImageScan` unavailable | Enhanced scanning does not support manual scans | Check scan type and filters |
| ECR Docker login gets `AccessDenied` | Identity policy lacks `ecr:GetAuthorizationToken` | Verify caller, IAM/SCPs, and correct Region |
| Docker login succeeds, pull returns 403 | Missing `BatchGetImage`/`GetDownloadUrlForLayer`, repo/endpoint policy deny | Check repo ARN, principal, and policies on both sides |
| `CannotPullContainerError` on Fargate start | Role, image URI, auth, VPC endpoints, or S3 layer path | Inspect ECS stopped reason, logs, execution role, SG/endpoints |
| ECS task runs, app fails calling S3 | Missing `s3:GetObject` on the **task role** | Compare `taskRoleArn` and resource policy |
| `ImageTagAlreadyExistsException` | Repository has immutable tags | Use a new tag and record the digest |
| Cross-Region registry returns manifest not found | Pulling wrong registry endpoint/Region | Verify account ID/Region/image digest |
| Enhanced enabled, repo not scanned | Repo matches no filters → Off, or Inspector inactive | Inspect scanning rules and Inspector coverage |
| Task lacks CPU/memory to run | Image pull succeeded, but task startup failed | Check task sizing, container logs, and health checks |
| Image still has CVEs after code fix | Base image or transitive Java dependencies not updated | Rebuild with updated base image/dependencies; scan new digest |
| Image was deleted/archived | Lifecycle policy removed rollback build | Inspect ECR lifecycle/restore; protect required release digests |
| ECR/Inspector bill spikes | Stale images, overly broad scan/monitoring scope, data transfer | Analyze Cost Explorer/billing/retention and filters |

### 17.1. Diagnostic Sequence When ECS Fails to Start

1. Read the ECS **stopped reason** and service events; distinguish an image pull error from an application error.
2. Verify **AWS account, Region, and image URI/tag/digest**.
3. Inspect the task definition's **`executionRoleArn`**; does it have `GetAuthorizationToken` and repo pull actions?
4. If cross-account, check the repository policy in the image-owning account.
5. Check the **network path** from task subnet/ENI to ECR API/DKR and S3 layers.
6. If the image pull succeeded, move on to **`taskRoleArn`**, application logs, secrets/DB/ALB health.
7. Never grant administrator access or open the entire Internet just to "test" in production.

## 18. Read-Only Lab: Evaluating an ECR Repository

### 18.1. Prerequisites

An authorized practice AWS account with AWS CLI v2 and profile `dev`, with read permissions for ECR repositories, scanning configuration, and scan findings. There is no need to create repositories, push images, enable Inspector, or modify IAM. If no repository is available, use **simulated outputs** based on the lesson's tables/policies for analysis.

### 18.2. Step A – Confirm Account and Region

~~~bash
aws sts get-caller-identity \
  --profile dev \
  --query '{Account:Account,Arn:Arn}' \
  --output json

aws ecr describe-repositories \
  --profile dev \
  --region ap-southeast-1 \
  --query 'repositories[].{Name:repositoryName,Uri:repositoryUri}' \
  --output table
~~~

Question: which repository is used for production, and could it collide in name with a repository in another account or Region?

### 18.3. Step B – Inspect Registry Scanning Rules

~~~bash
aws ecr get-registry-scanning-configuration \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

Analyze `scanType`, `scanFrequency`, and `repositoryFilters`. Under Basic scanning, if a repository matches no scan-on-push filter, which mode does it use? Under Enhanced scanning, what happens if a repository matches no filter?

### 18.4. Step C – Inspect Images and Scan Findings

~~~bash
aws ecr describe-images \
  --repository-name platform/orders-api \
  --profile dev \
  --region ap-southeast-1 \
  --query 'imageDetails[].{Digest:imageDigest,Tags:imageTags,PushedAt:imagePushedAt}' \
  --output json

aws ecr describe-image-scan-findings \
  --repository-name platform/orders-api \
  --image-id imageTag=1.2.3 \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

If no authorized image exists, do not push one yourself; explain the `COMPLETE`, `IN_PROGRESS`, `FAILED`, or `SCAN_ELIGIBILITY_EXPIRED` statuses that the API/scanner can report per scan type. If a scan completes with Critical findings, propose a remediation workflow aligned with a release policy.

### 18.5. Step D – Inspect Repository Policy

~~~bash
aws ecr get-repository-policy \
  --repository-name platform/orders-api \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

If no custom resource policy is attached, the API may report policy not found; that **does not allow public access by default**. Check identity IAM policies and cross-account rules. Identify which `Principal` can pull/push and whether admin/delete rights exist.

### 18.6. Step E – ECS Fargate Permissions

Review the earlier task definition JSON and policies and answer:

1. Which role requires `ecr:GetAuthorizationToken`?
2. Which role requires `s3:GetObject` when the Java app processes orders from S3?
3. Can Account B pull Account A's image if only Account B's IAM policy allows it while Account A's repository policy does not?
4. If a task runs in a private subnet without NAT, which endpoints are needed to pull from ECR?
5. If a task definition uses a mutable tag, how do the risks differ from using a digest?
6. If a new scan discovers a Critical vulnerability after an image is running, does ECS patch it automatically?

### 18.7. Step F – Propose a Release Policy

Write a short one-page brief describing **which image digests are permitted to deploy**, when to block, when exceptions apply, who approves, and how new CVEs are tracked. Include a rollback runbook pointing to a verified digest. No real ECS service needs to be created for this exercise.

## 19. Self-Assessment Questions

1. How do an ECR registry, repository, image tag, and digest differ?
2. Why does Basic scanning not cover all Java dependencies?
3. Distinguish Basic manual, Basic scan-on-push, Enhanced scan-on-push, and Enhanced continuous.
4. Does an ECR registry defaulting to Basic automatically scan every repository on push?
5. Under Enhanced scanning, how is a repository scanned if it matches no scanning filter?
6. Why is `DescribeImageScanFindings` more reliable than reading only `DescribeImages` for current Basic scan results?
7. When an image reports `0 findings` but the scanner marks it unsupported, can you release it without further checks?
8. Can `GetAuthorizationToken` be restricted via `Resource` to a single repository ARN?
9. Which role allows ECS Fargate to **pull** an ECR image: task role or task execution role?
10. A running task gets AccessDenied calling DynamoDB; which role should you check?
11. In a cross-account pull, what roles do the repository policy and caller IAM policy each play?
12. How long is an ECR login token valid, and does the token elevate IAM permissions?
13. When an ECS task runs in a private subnet, why can ECR endpoints alone still fail without an S3 gateway endpoint?
14. Why should an immutable image tag still be cross-referenced by digest in release records?
15. What happens when Enhanced scanning detects a new CVE in an already-deployed image?
16. Why should a CI role be restricted to pushing to a specific repository and denied editing repository policies?
17. How do you prevent a lifecycle policy from deleting images needed for rollback?
18. What charges can arise when enabling Enhanced scanning and pulling images over private endpoints?

### Answer Guidance

Competency requires distinguishing **image content/digest**, **scanner coverage/finding status**, **ECR repository access**, **ECS runtime execution permissions**, and **application AWS API permissions**. You should be able to interpret scan output, make an evidence-backed release decision, and isolate root causes when ECS fails to pull an image.

## 20. Official AWS Documentation

1. [Amazon ECR image scanning](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning.html) – Overview of Basic and Enhanced scanning.
2. [Configuring basic scanning](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning-basic-enabling.html) – Registry-level configuration, scan-on-push filters.
3. [Enhanced scanning](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning-enhanced.html) – Inspector integration, coverage, and monitoring windows.
4. [Configuring enhanced scanning](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning-enhanced-enabling.html) – Filters, frequency, CLI.
5. [Retrieving basic scan findings](https://docs.aws.amazon.com/AmazonECR/latest/userguide/describe-scan-findings.html) – `DescribeImageScanFindings` API.
6. [Retrieving enhanced scan findings](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning-enhanced-describe-scan-findings.html) – Viewing findings and Amazon Inspector.
7. [ECR scanning filters](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning-filters.html) – Repository matching criteria.
8. [Private repository policies](https://docs.aws.amazon.com/AmazonECR/latest/userguide/repository-policies.html) – Resource policies and IAM permissions.
9. [ECR repository policy examples](https://docs.aws.amazon.com/AmazonECR/latest/userguide/repository-policy-examples.html) – Cross-account examples.
10. [IAM permissions for pushing images](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-push-iam.html) – Required actions for pushing.
11. [Amazon ECR images with ECS](https://docs.aws.amazon.com/AmazonECR/latest/userguide/ECR_on_ECS.html) – Image URIs and pull permissions.
12. [ECS task execution IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html) – ECR/Logs permissions for ECS execution.
13. [ECR VPC endpoints](https://docs.aws.amazon.com/AmazonECR/latest/userguide/vpc-endpoints.html) – API/DKR interface and S3 gateway endpoints.
14. [AWS CLI get-login-password](https://docs.aws.amazon.com/cli/latest/reference/ecr/get-login-password.html) – Registry login and 12-hour token.
15. [AWS ECR events and EventBridge](https://docs.aws.amazon.com/AmazonECR/latest/userguide/ecr-eventbridge.html) – Basic scan events.
16. [Enhanced scanning EventBridge events](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning-enhanced-events.html) – Inspector2 Scan/Finding events.
17. [ECR image scanning troubleshooting](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning-troubleshooting.html) – Scan errors and eligibility.
18. [Amazon ECR pricing](https://aws.amazon.com/ecr/pricing/) – Storage and data transfer.
19. [Amazon Inspector pricing](https://aws.amazon.com/inspector/pricing/) – Enhanced vulnerability scanning.

> **Key takeaway:** ECR governs **which images are stored and who can access them**, ECS uses the **execution role** to pull images, and Amazon Inspector helps **monitor CVEs**. A reliable workflow combines **digest pinning, appropriate scanning, scoped IAM/repository policies, proper VPC connectivity, release gates, auditing, and rebuilding images when new vulnerabilities emerge**.
