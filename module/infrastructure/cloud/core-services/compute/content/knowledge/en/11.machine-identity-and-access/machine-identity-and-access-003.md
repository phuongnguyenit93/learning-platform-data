# Granting Least Privilege for Applications to Call Cloud Services

An application running on a VM, container, or serverless platform often needs to call other cloud services: reading files from object storage, writing logs, fetching configuration, accessing secrets, sending messages to queues, or querying databases. To perform these operations, the target service must know **which application is calling** and **what the application is allowed to do**.

Workload identity (or machine identity) solves this identification part. The system assigns a dedicated identity to the VM, container, function, or process; the target service verifies the identity and then enforces permission policies. **Least privilege** requires granting only the exact actions, resources, and conditions that the workload needs to complete its task.

In the **CLOUD_CORE_SERVICES_COMPUTE** module, this lesson focuses on how to grant least-privilege permissions for applications calling cloud services. Topics include machine identity, IAM roles, managed identities, service accounts, short-lived credentials, resource-scoped permissions, federation, metadata endpoint protection, secret management, auditing, and permission testing workflows.

## 1. Why Do Applications Need Dedicated Identities?

Imagine a VM running an image-processing worker. The worker needs to read image files from one bucket, write thumbnails to another bucket, and send completion notifications to a queue. If it uses an access key with administrative permissions across the entire cloud account, a bug in the application or a security vulnerability could expose all resources.

Instead, grant the worker a dedicated identity with permissions to:

- Read objects in the input image bucket.
- Write objects to a specific prefix in the output bucket.
- Send messages to the specific image-processing queue.
- Have no permissions to delete buckets, create IAM users, read billing data, or modify networking.

If the worker is compromised, the blast radius is limited to the granted permissions. Other workloads such as the catalog API, reporting batch jobs, and backups should each have their own identities because they have different tasks and data scopes.

Dedicated identities help:

1. Clearly identify which workload called an API.
2. Grant permissions aligned with the task and required resources.
3. Revoke or modify permissions for one workload without affecting others.
4. Avoid sharing a single credential across multiple applications.
5. Track activity through audit logs.
6. Use short-lived, automatically refreshed credentials instead of static keys.

A machine identity should not be treated as a shared account for every process on a host. If multiple applications with different trust levels share one broad role, each application inherits all permissions of that role. Separate identities by workload, environment, and trust boundary.

## 2. Distinguishing User Identities from Workload Identities

Cloud systems typically have at least two groups of principals (entities performing actions):

| Identity group | Represents | Examples |
|---|---|---|
| Human identity | Humans logging in to administer or use the system | Cloud engineers, administrators, operations staff |
| Workload identity | Applications or automated processes calling services | VM running an API, Kubernetes Pod, serverless function, CI pipeline |

User identities are usually tied to interactive login, MFA, groups, and personnel provisioning workflows. Workload identities usually need to run automatically without a human entering a password, so they require an authentication mechanism that can issue and refresh credentials safely.

Do not use an engineer's personal account as an application's identity. When staff leave, change roles, or change MFA, workloads may break; auditing also becomes unable to tell whether an action came from a human or from an application.

Key terms:

- **Principal:** an identity recognized by the security system, such as a user, role, service account, or federated identity.
- **Authentication:** verifying who the principal actually is.
- **Authorization:** deciding which actions the principal is permitted to perform on which resources.
- **Credential:** data used to prove identity, such as a token, certificate, or access key.
- **Policy:** a set of rules describing allowed or denied permissions.
- **Resource:** a protected asset, such as a bucket, queue, secret, or database.

Successful authentication does not mean the application is allowed to do everything. After verifying identity, the service still checks authorization for every action.

## 3. How Does Workload Identity Work?

A common model is that the compute platform attaches an identity to the workload. When the application needs to call a cloud service, it requests temporary credentials from the platform's identity mechanism. The credentials are sent to the target service; the service verifies the token or signature and evaluates policies attached to the principal.

~~~mermaid
sequenceDiagram
    participant W as VM / Container / Function
    participant I as Identity Service
    participant T as Token / Credential Service
    participant S as Cloud Service
    W->>I: Request workload identity
    I->>T: Verify workload and identity attachment
    T-->>W: Short-lived credentials
    W->>S: API request with credentials
    S->>S: Verify credentials and evaluate policy
    S-->>W: Allow or deny
~~~

The exact steps depend on the provider:

1. An administrator creates a role, managed identity, or service account.
2. The identity is attached to a VM, node, Pod, or function; or issued via federation.
3. The workload retrieves a token/credential using a platform-supported SDK or endpoint.
4. The SDK signs the request or sends a bearer token to the target service.
5. The service verifies the credential, principal, audience, expiration, and policy.
6. When the credential nears expiration, the SDK or agent obtains a new credential.

The key point is that the application does not need to store long-lived access keys in source code or configuration files. The identity is bound to the runtime environment and credentials are issued automatically for short durations.

## 4. Common Identity Models in the Cloud

Names and implementations vary across providers, but the shared concept is attaching a principal to a workload and issuing time-limited credentials.

| Platform | Common mechanism | Example |
|---|---|---|
| AWS | IAM role, instance profile, task role, Lambda execution role | EC2 instance uses a role to read an S3 bucket |
| Microsoft Azure | Managed identity: system-assigned or user-assigned | VM uses a managed identity to read a secret from Key Vault |
| Google Cloud | Service account attached to VM or workload identity federation | Compute Engine VM uses a service account to write logs or read objects |
| Kubernetes | ServiceAccount combined with projected tokens and cloud workload identity/federation | Pod exchanges a Kubernetes token for cloud role credentials |
| CI/CD platforms | OIDC federation or short-lived credentials | Deployment pipeline is allowed to update only one environment |

### 4.1. AWS IAM role and instance profile

An IAM role is an identity that can be assumed by a trusted principal. The role has a trust policy defining who is allowed to use the role and a permission policy defining what the role is allowed to do.

For EC2, an instance profile is the mechanism for attaching an IAM role to an instance. Applications on the VM can retrieve temporary credentials from the EC2 instance metadata service via the SDK. When credentials expire, a compatible SDK automatically refreshes them.

Other workloads have corresponding mechanisms:

- EC2 instances use an instance profile.
- ECS tasks use a task role to grant permissions to application code in the task.
- Lambda functions use an execution role.
- EKS Pods can use IAM Roles for Service Accounts (IRSA) or EKS Pod Identity depending on architecture.

Do not attach a broad administrative role to an entire EC2 fleet just so one application can read a single bucket.

### 4.2. Azure managed identity

Managed identity provides a Microsoft Entra-managed identity for Azure resources. There are two common forms:

- **System-assigned:** the identity's lifecycle is tied to an Azure resource; when the resource is deleted, that identity is deleted as well.
- **User-assigned:** the identity is an independent resource, can be attached to multiple permitted resources, and has its own lifecycle.

A VM or service supporting managed identity can request a token for a specific audience/resource and use that token to call Azure services. Permissions are typically granted via Azure role-based access control (Azure RBAC) at an appropriate scope, such as a storage account, container, or Key Vault.

Managed identity eliminates the need to store client secrets in the application, but scope and roles must still be restricted. A user-assigned identity attached to too many VMs can expand the blast radius if one VM is compromised.

### 4.3. Google Cloud service account

A service account represents a workload on Google Cloud. A service account can be attached to a Compute Engine VM or corresponding workload. Applications use Application Default Credentials (ADC) or client libraries to obtain platform-issued credentials.

IAM policies bind roles to the service account at the organization, project, folder, or resource level. Grant permissions at the smallest scope that meets the need. For example, if a workload only needs to read objects in one bucket, prefer read permissions on that bucket rather than broad permissions across the entire project.

Do not create and download JSON service account keys onto VMs when the workload can use an attached service account directly or federation.

## 5. Designing Permissions with the Principle of Least Privilege

A policy should answer three questions:

1. **Who:** which principal is performing the action?
2. **What:** which actions are permitted?
3. **Where/when:** on which resources and under what conditions?

A permission can be described as a tuple:

\[
Permission = (Principal,\ Action,\ Resource,\ Condition)
\]

For example, a thumbnail worker may be allowed to call object read actions on the `product-uploads` bucket and write objects to the `thumbnails/` prefix of the `product-assets` bucket, while not being allowed to delete objects or modify bucket policies.

### 5.1. Restricting by action

Grant only the API actions the application truly needs. For example:

- Reading objects: `GetObject`.
- Writing objects: `PutObject`.
- Sending messages: `SendMessage`.
- Reading a specific secret: the secret manager API's read-secret action.
- Writing logs: only the required log-writing actions.

Avoid granting action wildcards such as `*` without a clear justification. List, Read, Write, Delete, and Admin permissions have different scopes; an application that only reads data should not have delete or configuration-change permissions.

### 5.2. Restricting by resource

An action permitted across all resources can still be very broad. Restrict resources using ARNs, resource IDs, buckets, queues, databases, secrets, or corresponding scopes.

For example, `s3:GetObject` on `arn:aws:s3:::company-data/*` allows reading every object in that bucket; if a worker only processes uploaded images, restrict it to the `uploads/*` prefix. When listing a bucket is needed, the policy needs a separate bucket-level permission and can use conditions to restrict `s3:prefix`.

### 5.3. Additional conditions

Policies can be further restricted with conditions:

- Environment or resource tags.
- VPC endpoint or source network.
- Mandatory TLS.
- Principal tags or session tags.
- Audience, subject, or issuer of a federated token.
- Time or contextual attributes supported by the service.

Conditions help narrow permission scope, but must be tested because a misconfigured condition can block valid workloads. Do not rely on source IP address as the sole identity; networks can change and an IP does not prove the principal.

### 5.4. Deny and effective permissions

Some platforms support explicit denies or multi-layered policies. Explicit deny usually takes precedence over allow in corresponding IAM models. Effective permissions may result from combining identity policies, resource policies, organization policies, permission boundaries, session policies, and other conditions.

Do not look at a single policy in isolation and conclude an application has permission. Review the entire authorization path and test the actual operation in a test environment.

## 6. Example: EC2 Reading Only One Prefix on S3

Suppose a VM running a reporting application needs to read CSV files from the `daily-input/` prefix in the `analytics-data` bucket. The application does not need to write or delete objects.

### 6.1. Trust policy for EC2

The role must allow the EC2 service to assume it:

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

The trust policy answers who is allowed to assume the role. It does not grant S3 read permissions; S3 access permissions live in a separate permission policy.

### 6.2. Permission policy reading only objects in a prefix

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadDailyInputObjects",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::analytics-data/daily-input/*"
    }
  ]
}
~~~

This policy allows reading objects under the specified prefix. If the application needs to list objects, `s3:ListBucket` on the bucket ARN with a condition restricting `s3:prefix` may be required. Add that permission only after confirming the application actually needs it.

### 6.3. Attaching the role to EC2

Abbreviated Terraform example:

~~~hcl
resource "aws_iam_role" "report_reader" {
  name = "report-reader"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "read_daily_input" {
  name = "read-daily-input"
  role = aws_iam_role.report_reader.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject"]
      Resource = "arn:aws:s3:::analytics-data/daily-input/*"
    }]
  })
}

resource "aws_iam_instance_profile" "report_reader" {
  name = "report-reader"
  role = aws_iam_role.report_reader.name
}

resource "aws_instance" "report_worker" {
  ami                  = var.approved_ami_id
  instance_type        = "t3.small"
  subnet_id            = var.private_subnet_id
  iam_instance_profile = aws_iam_instance_profile.report_reader.name
}
~~~

This is a structural example; use images, subnets, and provider versions appropriate to the real account. In production, role names, resource ARNs, tags, and policies should be managed according to organizational standards. VM creation modules should not automatically grant broad permissions beyond the workload's purpose.

### 6.4. Application retrieving credentials

With a compatible AWS SDK, the application typically uses the default credential provider chain. When running on EC2 with an instance profile, the SDK can obtain temporary credentials from the metadata service without access keys in configuration files.

Do not log returned credentials or save them to long-lived files. Let the credential provider handle refreshes and transmit credentials only over secure channels to the target service.

## 7. Short-Lived Credentials and Token Lifecycle

Long-lived credentials such as access keys or service account keys can remain valid for months. If leaked, an attacker has extended time to use them until the key is revoked. Short-lived credentials shrink the risk window because they expire and are reissued through an identity workflow.

Workload credentials may be:

- Temporary access key / secret key with a session token.
- OAuth 2.0 access token.
- JWT signed by an identity provider.
- Time-limited X.509 certificate.
- Projected token for a Kubernetes ServiceAccount.

When receiving a credential, verify:

- Expiration: when it expires.
- Audience: which service or API the token was issued to access.
- Issuer: which system issued the token.
- Subject: which workload identity is represented.
- Scope or claims: permission scope and context.

The SDK should manage refreshes using official mechanisms. Do not store tokens manually in source code, long-lived environment variables, or shared files when a credential provider can be used.

### 7.1. A token is not a harmless temporary string

Short-lived tokens are still credentials. If stolen while valid, an attacker can use the token within its permitted scope and lifetime. Therefore:

- Do not write tokens to logs or telemetry.
- Transmit tokens over TLS.
- Keep tokens in memory whenever possible.
- Do not share tokens across unrelated workloads.
- Use appropriate audiences and subjects.
- Revoke or reduce permissions when an incident is detected.

### 7.2. Credential rotation

For platform-issued temporary credentials, rotation is typically automated. For static credentials that cannot yet be eliminated:

1. Store them in a secret manager.
2. Grant secret access permissions only to the intended workload.
3. Set a rotation schedule and appropriate overlap window.
4. Update the application to read the new version.
5. Verify the new credential works.
6. Revoke the old credential and inspect usage logs.

Do not create a new key and forget to revoke the old one. Multiple active keys increase the attack surface.

## 8. Protecting the Metadata Service and Credential Endpoints

Cloud VMs typically provide a metadata service to supply instance information, bootstrap configuration, and temporary credentials for the role attached to the machine. If an application or proxy has an SSRF (Server-Side Request Forgery) vulnerability, an attacker may attempt to access the metadata endpoint to obtain sensitive data.

The metadata service is not a public Internet API. It is designed for workloads on the machine to reach over a special network path. However, an insecure application can unintentionally send requests to this endpoint on behalf of a user.

### 8.1. Mitigating SSRF risks

- Enable metadata protection mechanisms recommended by the cloud provider.
- Prefer mandatory metadata tokens/sessions if supported by the platform.
- Block metadata access from processes or containers that do not need it.
- Do not allow arbitrary user-supplied URLs to be fetched without destination validation.
- Block access to the link-local metadata IP in proxies or network policies where appropriate.
- Restrict the role attached to the host to least privilege.
- Do not run multiple untrusted workloads on the same host with a broad role.

### 8.2. AWS IMDSv2

AWS EC2 Instance Metadata Service version 2 (IMDSv2) uses a session token flow before querying metadata. Instances can be configured to require tokens and restrict the hop limit to match the network topology. This mitigates certain simple SSRF patterns, but does not replace fixing SSRF vulnerabilities or restricting role permissions.

In Terraform, configuration typically looks like:

~~~hcl
metadata_options {
  http_endpoint               = "enabled"
  http_tokens                 = "required"
  http_put_response_hop_limit = 1
}
~~~

A hop limit of 1 may not fit certain container architectures or network namespaces that require an extra hop. Test on the actual runtime and choose the smallest value that still supports the application. Do not disable the metadata endpoint if workloads rely on it for instance-profile credentials; configure protections according to design.

## 9. Workload Identity Federation

Federation allows a workload to use an identity from a trusted identity provider to obtain cloud credentials without creating long-lived keys. For example, a CI/CD pipeline running outside the cloud can obtain an OIDC token from the CI platform, then exchange that token for temporary credentials to deploy to a specific project or account.

General flow:

1. The workload authenticates or is issued a token by a trusted issuer.
2. The token contains issuer, subject, audience, and related claims.
3. Cloud STS or the identity service verifies the signature and claims.
4. The trust policy checks whether the workload matches the permitted repository, branch, environment, or service account.
5. The cloud issues short-lived credentials bound to a role.
6. The workload uses those credentials to call APIs within the granted scope.

~~~mermaid
sequenceDiagram
    participant C as CI / Kubernetes Workload
    participant O as OIDC Identity Provider
    participant F as Cloud STS / Federation
    participant R as Cloud Resource
    C->>O: Request identity token
    O-->>C: JWT with issuer, subject, audience
    C->>F: Exchange token for credentials
    F->>F: Verify signature and trust conditions
    F-->>C: Short-lived cloud credentials
    C->>R: Call API with credentials
    R-->>C: Result per IAM policy
~~~

The trust policy should restrict:

- Specific issuer, rather than trusting every identity provider.
- Audience matching the token exchange service.
- Exact subject, such as repository and branch or Kubernetes namespace/service account.
- Environment or additional claims if supported by the platform.
- Target role having least-privilege permissions.

If a trust policy checks only the issuer without restricting subject/audience, many other workloads under the same identity provider may attempt to obtain the role. Federation eliminates static keys, but does not eliminate the need to harden trust policies.

## 10. Identities for Containers and Kubernetes

Containers often run on nodes that have an underlying host identity. If every Pod uses the node's credentials, one compromised Pod can inherit the permissions of every other workload on the node.

Grant identities at the workload level whenever the platform supports it:

- Each application or Pod group has its own Kubernetes ServiceAccount.
- Bind cloud permissions to the right service account via federation or cloud-native integration.
- Mount projected tokens only into containers that need them.
- Restrict namespaces and permissions to create/use service accounts.
- Do not share the default service account across all applications.

### 10.1. Kubernetes ServiceAccount

A ServiceAccount is an identity in Kubernetes for Pods to authenticate to the Kubernetes API or map to a cloud identity through integration mechanisms. Modern tokens are typically issued as projected tokens with an audience and expiration; avoid creating long-lived static token Secrets unless necessary.

ServiceAccount example:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: image-worker
  namespace: media
automountServiceAccountToken: false
~~~

If a Pod only needs a cloud identity via a specific token projection mechanism, configure token mounting according to platform guidance. Disabling auto-mount in the example prevents giving Kubernetes API tokens to every container unnecessarily; it does not configure cloud federation by itself.

### 10.2. Separating Kubernetes RBAC and cloud IAM

Kubernetes RBAC controls permissions to call the Kubernetes API, such as reading a ConfigMap or listing Pods. Cloud IAM controls permissions to call cloud services, such as reading object storage or retrieving secrets. These two permission layers are independent and must be evaluated separately.

A Pod may lack permission to read Kubernetes Secrets while still having permission to read secrets from a cloud secret manager via an IAM role. Conversely, a service account permitted to list Pods in a namespace does not automatically have permission to read cloud buckets.

### 10.3. Avoiding inheriting node permissions

On some platforms, Pods can reach node credentials if network or metadata access is not restricted. Use workload identity integration, block metadata access from Pods that do not need it, and test boundaries between namespaces. Do not treat the node role as an appropriate default role for all Pods.

## 11. Managed Identity and Accessing Secrets

Workload identity and secrets are related but distinct concepts:

- **Identity** tells who the workload is and determines what it is allowed to do.
- **Secret** is sensitive data the workload needs to use, such as a database password or an external system API key.

If the target service supports IAM or workload identity, prefer authenticating with identity instead of creating static passwords. If the application still requires a secret, use the workload identity to authenticate to the secret manager and read only the exact secret needed.

Example:

1. The VM has the `orders-api` role.
2. The role is allowed to read only the secret `prod/orders/database-password`.
3. The application uses temporary credentials to call the secret manager.
4. The secret manager verifies the role and returns the secret.
5. The application uses the secret to connect to the database without logging the secret.

Do not grant permission to read all secrets in an account just because the application needs one password.

## 12. Permission Scope and Workload Separation Models

Roles should be separated by function, environment, and sensitivity level:

| Workload | Required permissions | Permissions to avoid |
|---|---|---|
| Catalog API | Read catalog data, write logs | Delete buckets, edit IAM |
| Order API | Write orders, call payment service via controlled endpoint | Read HR data, administer accounts |
| Image worker | Read upload prefix, write thumbnail prefix, send queue result | Read payment data, delete buckets |
| Backup agent | Read backup sources and write to backup repository per policy | Modify application code, create IAM users |
| Monitoring agent | Read metrics and send logs | Read business payloads or unnecessary secrets |
| CI/CD deployment | Deploy to a specific application/environment | Organization-wide admin permissions |

Development, staging, and production should have separate identities or trust boundaries. Do not allow a single production role to be assumed by pipelines running on every branch. For CI/CD, allow only protected branches or approved environments to assume production deployment roles.

### 12.1. Separating read and write permissions

If a workload has a read-only component and a data-writing component, consider splitting them into two identities. For example, a lookup API only needs read permissions; an update worker only needs write access to a specific prefix. Separation limits the impact if one component is exploited.

### 12.2. Separating permissions by environment

Do not allow development workloads to read production data just because they share an account or project. Use separate accounts/projects/subscriptions or resource scopes where appropriate. If sharing is unavoidable, policies must explicitly restrict by tags, resource paths, conditions, and identities.

## 13. Auditing and Monitoring Identity Activity

Audit logs help answer:

- Which workload called the API?
- Which identity was assumed or had its token exchanged?
- Which action was performed?
- Which resource was accessed or modified?
- From what time, address, and environment did the request arrive?
- Which policy denied the action?

Cloud providers typically offer audit services recording administrative and API activity, such as AWS CloudTrail, Azure Activity Log, or Google Cloud Audit Logs. Enable and retain logs per organizational requirements, restrict log deletion permissions, and alert on sensitive actions.

Events to monitor:

- Creating, modifying, or deleting roles, policies, and trust relationships.
- Attaching a new role to a VM, function, or workload.
- Creating service account keys or long-lived access keys.
- Unusual role assumptions or token exchanges.
- Secret accesses outside normal scope.
- Sudden spikes in denied actions.
- Policy changes that broaden permissions.

Do not write access tokens, secret values, or private keys into logs. Audit logs should retain principal ID, request ID, action, resource, result, and context needed for investigation.

## 14. Testing Permissions Before Going to Production

A policy may be syntactically valid while still granting too many permissions or breaking the application. Test both directions: the workload has enough required permissions and has no excess permissions.

Suggested workflow:

1. List the API actions the application actually calls.
2. Identify specific resource ARNs/IDs or scopes for each action.
3. Create a dedicated role for the workload and configure its trust policy.
4. Attach the role to the intended VM, task, Pod, or function.
5. Run integration tests for valid operations.
6. Attempt disallowed operations and verify they are denied.
7. Check audit logs to confirm the actual principal used.
8. Review unused permissions and tighten the policy.
9. Set up alerts for role/policy changes and anomalous access.

### 14.1. Positive and negative testing

Example for a worker that needs to read input objects and write thumbnails:

| Test operation | Expected result |
|---|---|
| Read object in permitted upload prefix | Allow |
| Write object in permitted thumbnail prefix | Allow |
| Delete source object | Deny unless required by business logic |
| Read payment data bucket | Deny |
| Modify IAM policy | Deny |
| Read another application's secret | Deny |

Negative testing is critical. Testing only valid actions does not prove that permissions are properly bounded.

### 14.2. Using permission analysis tools

Depending on the platform, you can use an IAM policy simulator, access analyzer, role assignment review, policy insights, or equivalent permission inspection tools. These tools help identify unused permissions, overly broad trust relationships, or risky resource policies.

Analysis results must be cross-checked against business workflows. Do not automatically remove permissions just because they were unused over one observation window; a workload might run on a schedule or only during emergencies.

## 15. Handling Exposed Credentials or Abused Roles

When credential exposure is suspected:

1. Identify the principal, credential ID, expiration, and affected workload.
2. Revoke or disable the credential if supported by the platform.
3. Detach the role from the workload or temporarily reduce permissions when needed.
4. Inspect audit logs to find accessed actions and resources.
5. Check whether data was read, modified, or deleted.
6. Rotate related secrets and fix the original vulnerability.
7. Restore data if unauthorized modifications occurred.
8. Issue new credentials through a secure workflow.
9. Document the incident and add controls to prevent recurrence.

Short-lived credentials reduce the post-compromise window but do not eliminate risk. An attacker can still use a token while it remains valid. If the role is overly broad, even a short window can cause major damage.

## 16. Real-World Example: E-Commerce System

An e-commerce system has a catalog API, an orders API, an image-processing worker, and a reporting job. Each component calls different cloud services.

| Workload | Identity | Core permissions | Boundary |
|---|---|---|---|
| Catalog API | catalog-api-prod | Read catalog storage, send logs | Production catalog resources only |
| Orders API | orders-api-prod | Write orders database, read connection secret | Orders database and secret only |
| Image worker | image-worker-prod | Read uploads, write thumbnails, send queue results | Media bucket prefixes and queue |
| Report job | report-reader-prod | Read aggregated data, write report output | Reporting dataset and bucket |

If the image-processing worker is compromised, the worker's role does not allow reading order data or modifying IAM. If the catalog API deployment pipeline runs from a development branch, the trust policy prevents it from assuming the production role. When a VM is replaced, the new VM receives the same workload identity through instance configuration without copying access keys from the old machine.

This design creates clear boundaries between workloads. Operations teams can inspect audit logs to see which API or worker accessed resources and tighten permissions individually for each component.

## 17. Workload Identity Implementation Workflow

The following workflow can be applied to a new workload:

1. **Describe the task:** list the cloud services the application needs to call and the actions required.
2. **Identify the principal:** choose an appropriate IAM role, managed identity, service account, or federated identity.
3. **Design trust:** restrict which workloads can receive the identity, issuer, subject, audience, and environment.
4. **Design permissions:** specify minimal actions, resources, and conditions.
5. **Attach the identity:** configure it on the VM, task, Pod, or function using the platform's mechanism.
6. **Integrate the SDK:** use the default credential provider or official library to retrieve and automatically refresh tokens.
7. **Protect the credential endpoint:** restrict metadata access, mitigate SSRF, and never log tokens.
8. **Test:** run positive and negative tests in a separate environment.
9. **Enable auditing:** monitor role assumptions, token exchanges, API access, and policy changes.
10. **Review periodically:** remove excess permissions, unused identities, and legacy static credentials.

## 18. Common Mistakes

- **Using long-lived access keys in source code:** easily leaked through Git, images, logs, or backups.
- **Sharing a role across all workloads:** one compromised application can inherit the permissions of others.
- **Attaching an administrative role to a VM:** turns an application vulnerability into full-account compromise risk.
- **Restricting actions while forgetting resources:** read permissions may still cover every bucket or project.
- **Overly broad trust policy:** unintended workloads can assume the role.
- **Treating authentication as authorization:** successful authentication does not grant resource access.
- **Treating Kubernetes RBAC as cloud IAM:** the two permission layers protect different APIs.
- **Letting all Pods use the node role:** erases permission boundaries between workloads.
- **Treating short-lived tokens as harmless:** leaked tokens still work until they expire.
- **Placing secrets in user-data or images:** sensitive data can be read from metadata, logs, or image clones.
- **Testing only allowed permissions:** skipping negative tests leaves excess permissions undetected.
- **Not monitoring policy drift:** permissions can gradually widen over repeated changes.

## 19. Takeaways

Workload identity helps applications prove their identity when calling cloud services. IAM roles, managed identities, service accounts, and federation are common ways to grant identities to VMs, containers, functions, or pipelines. Prefer platform-issued short-lived credentials over long-lived keys stored in applications.

Least privilege requires scoping principals, actions, resources, and conditions strictly to the task. Separate identities across workloads and environments, protect the metadata endpoint, manage secrets separately, test both allowed and denied operations, and monitor audit logs. When identities and permissions are designed cleanly, applications can call cloud services securely without holding broad administrative privileges.
