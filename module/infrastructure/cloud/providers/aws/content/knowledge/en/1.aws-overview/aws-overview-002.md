# The AWS Shared Responsibility Model

> **Chapter:** AWS Overview  
> **Scope:** CLOUD_PROVIDERS_AWS — explore the Amazon Web Services (AWS) ecosystem, from Regions/AZs, IAM, and VPC to compute, storage, databases, and serverless; learn to design secure, observable, resilient, and cost-controlled applications.

## Learning Objectives

After this lesson, you will be able to:

1. Explain the **Shared Responsibility Model** and distinguish *security **of** the cloud* from *security **in** the cloud*.
2. Identify AWS's and the customer's responsibilities across common services such as EC2, S3, RDS, Lambda, and Fargate.
3. Apply the model when configuring IAM, networking, encryption, logging, backups, recovery, and compliance.
4. Analyze incidents to determine which party operates the relevant infrastructure layer and what protective actions the customer must take.

## 1. Why Is the Shared Responsibility Model Needed?

When hosting applications in a self-operated data center, an organization typically manages everything from server room doors, power, hardware, and networking to the operating system, data, and applications. When moving to AWS, AWS takes over a large share of that infrastructure; however, **using AWS does not automatically make customer applications and data secure**.

AWS refers to this delineation as the **AWS Shared Responsibility Model**:

- **AWS is responsible for security *of* the cloud:** protecting and operating the infrastructure that delivers AWS services.
- **The customer is responsible for security *in* the cloud:** protecting the data, identities, configurations, and software components controlled by the customer.

This defines an **operational boundary**, not a 50/50 split of responsibility. The proportion of work the customer must manage varies depending on the service used.

**Opening example:** AWS keeps the Amazon S3 storage hardware running and protected. But if an administrator grants object read permission to everyone on the Internet, AWS cannot know whether that content is supposed to be public under the company's policy. The access decision and the consequences of that configuration fall within the customer's scope.

## 2. Two Primary Layers of Responsibility

### 2.1. AWS: Security *of* the Cloud

AWS is responsible for the platform on which cloud services run, for example:

| Component | Typical AWS role |
| --- | --- |
| Data centers | Physical access controls, power, cooling, and facility operations. |
| Hardware | Managing servers, storage devices, networking equipment, and replacing failed hardware. |
| AWS network infrastructure | Operating the physical network layer, connectivity systems, and AWS infrastructure. |
| Virtualization, service platform | Securing and maintaining the underlying layer beneath customer resources, including the hypervisor and related infrastructure where applicable. |
| Managed services | Operating the infrastructure and foundational software layers that AWS commits to managing specifically for each service. |

AWS builds Regions and Availability Zones (AZs) to provide location choices and fault-tolerance capabilities. **AWS operates the AZ infrastructure; the customer decides whether to deploy applications across multiple AZs, back up data, and test restores.**

### 2.2. Customer: Security *in* the Cloud

What the customer is typically responsible for:

| Component | Questions the customer must address |
| --- | --- |
| Data | Where is sensitive data stored? Who can read it? How long is it retained? When must it be deleted? |
| Identity and access | Which person or workload is allowed to perform which actions? Are MFA, least privilege, and credential controls in place? |
| Resource configuration | Are S3 buckets, Security Groups, public endpoints, databases, and roles configured properly? |
| Applications | Are source code, libraries, APIs, database queries, and user authentication secure? |
| Customer-managed operating systems | Are EC2 instances patched, hardened, and appropriately protected against malware? |
| Encryption and key management | Is data protected in transit and at rest? Who is granted permission to use KMS keys? |
| Logging, monitoring, and response | Are there sufficient logs to detect, investigate, alert, and respond to incidents? |
| Backup and recovery | Are there backup strategies, RPO/RTO targets, and restore drills that meet business requirements? |
| Compliance | Do controls satisfy regulations and policies applicable to the data, product, and industry? |

The customer does not directly perform *every* task in the table for *every* service. For instance, AWS patches the underlying host OS for RDS, whereas the customer patches the guest OS on standard EC2 instances.

### 2.3. Boundary Diagram

~~~mermaid
flowchart TB
    subgraph AWS["AWS — Security OF the cloud"]
        A["Facilities and hardware"]
        B["AWS networking and virtualization platform"]
        C["AWS-managed service foundation layer"]
    end
    subgraph CUSTOMER["Customer — Security IN the cloud"]
        D["Data and IAM identities"]
        E["Access permissions, network configuration, and encryption"]
        F["Applications, monitoring, backups, and recovery"]
        G["Self-managed OS/applications when using EC2"]
    end
    AWS --> CUSTOMER
~~~

This diagram is a conceptual model: **the exact dividing line depends on each service**. For example, the customer manages the guest OS when using EC2, but does not directly manage the OS of the servers running Lambda.

## 3. How Does the Boundary Shift by Service?

The amount of management handled by AWS generally increases as you move from self-managed virtual machines to managed services and serverless. The customer still retains responsibility for data, identities, configurations, and application logic.

| Service | AWS typically manages | Customer typically manages |
| --- | --- | --- |
| **Amazon EC2** | Data centers, physical servers, underlying network, hypervisor. | Guest OS and patches, applications, instance configuration, Security Groups, IAM permissions, data, backups. |
| **Amazon S3** | Storage service infrastructure, hardware, and S3 platform operations. | Data/objects, bucket policies, IAM, public access permissions, encryption and key usage permissions, versioning/lifecycle as needed. |
| **Amazon RDS** | Server infrastructure, underlying OS, and many database operational tasks handled by the service. | DB accounts and privileges, schemas/queries, allowed configurations, version/upgrade selection per service, network security, data, backup/HA setup. |
| **AWS Lambda** | Compute infrastructure, servers, and managed execution environment; runtimes provided by AWS per applicable update policies. | Function code, libraries/dependencies and their patches, execution role, secrets, event configuration, network connectivity, logs, and data. |
| **Amazon ECS on AWS Fargate** | Underlying servers, container runtime infrastructure, and host OS. | Container images, packages inside images, applications, IAM task roles, networking, task definitions, data, and observability. |
| **Amazon EKS** | AWS-managed Kubernetes control plane. | Workloads, RBAC, cluster configuration, network policies, access permissions, and—when using self-managed EC2 worker nodes—node OS and node patching. |

**Note:** Each service has specific mechanisms for version updates, patching, and configuration; do not assume that the word "managed" eliminates customer responsibility for software or configuration.

### 3.1. EC2: Flexibility Comes with Greater Responsibility

With EC2, AWS provides the infrastructure for virtual machines. The customer chooses the Amazon Machine Image (AMI), operating system, software packages, running services, and open network ports.

For example, suppose a development team runs a website on EC2:

- AWS fixes the physical host beneath an instance when an infrastructure failure occurs.
- The development team must patch the OS and application libraries, restrict SSH ports, manage users, and protect secrets.
- If the server is compromised due to an unpatched vulnerability in the application service, running on EC2 does not shift application-patching responsibility to AWS.
- If downtime must be avoided when an AZ fails, the development team must **design and deploy** multiple instances/AZs, load balancing, and appropriate recovery mechanisms.

When using third-party AMIs, the customer must also evaluate the image source and responsibility for updating components inside it.

### 3.2. RDS: AWS Operates the Underlying Database Layer, the Customer Protects the Data

Amazon RDS helps create and operate relational databases. AWS handles many tasks such as infrastructure provisioning and operational/maintenance tasks provided by RDS. Even so, the customer must still:

1. Place the database in an appropriate network, verify the **PubliclyAccessible** attribute, and allow connections only from required applications.
2. Grant DB accounts following least privilege; store secrets in an appropriate secrets management service.
3. Choose encryption settings, backup retention period, Multi-AZ, and maintenance/upgrade windows according to application requirements.
4. Control schemas, queries, application security, and test data restoration.

**Understanding backups properly:** RDS supports automated backups, but retention periods and options depend on configuration and engine/service type. Having the ability to create backups does not automatically mean the application meets its RPO/RTO or has a verified recovery plan.

### 3.3. S3: A Durable Service Does Not Mean Configurations Are Always Correct

With S3, two scopes are easily confused:

- AWS designs and operates the service's storage infrastructure.
- The customer decides **who can access objects**, how data is shared, retention periods, and how to recover from accidental deletion or overwrite.

S3 now enables server-side encryption by default for new objects using SSE-S3; this does **not** replace reviewing bucket policies, IAM, sensitive data classification, or requirements for customer-managed keys. Similarly, S3 Block Public Access must be checked at both the account and bucket levels in active environments, especially for pre-existing resources or complex configurations.

Versioning, replication, Object Lock, and lifecycle policies each solve different requirements. They must be designed deliberately rather than assuming AWS replication or storage durability equals a complete backup strategy.

### 3.4. Lambda and Serverless: Less Server Management, Application Security Still Applies

AWS Lambda does not require customers to directly administer host servers. Yet a Lambda function can still be exploited if:

- Input-handling code lacks validation, leading to injection or data exposure.
- The execution role allows reading all buckets or deleting many resources when the function only needs to write one object.
- Tokens, passwords, or API keys are hardcoded in source code or printed to logs.
- Libraries in the deployment package/container image contain unpatched vulnerabilities.
- The endpoint/API triggering the function lacks authentication, rate limiting, or proper monitoring.

Therefore, **serverless reduces infrastructure operations** but does not eliminate responsibility for code, dependencies, identities, and data.

## 4. Applying Shared Responsibility Across Security Pillars

### 4.1. IAM: AWS Provides the Tools, the Customer Decides the Permissions

AWS IAM provides users, roles, policies, and credential-issuance mechanisms. The customer is responsible for defining which identity gets which permissions. Foundational practices:

- Protect the root account, enable MFA, and restrict root usage for daily work.
- Prefer roles/temporary credentials for EC2, Lambda, and applications; avoid distributing long-lived access keys unnecessarily.
- Apply **least privilege**: grant only the actions and resources genuinely needed, and review permissions periodically.
- Control cross-account access and enforce strong authentication for human users.
- Monitor anomalous activity and revoke access when personnel or workloads no longer require it.

Example: if a function only needs to read reports from one prefix in a bucket, the policy below restricts read access to that prefix.

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": "arn:aws:s3:::example-private-reports/approved/*"
    }
  ]
}
~~~

This is an **illustrative IAM permission snippet**, not a complete configuration for every application. Effective permissions also depend on related policies such as bucket policies, resource policies, SCPs, permissions boundaries, explicit denies, and environmental conditions. This policy snippet does not allow listing the entire bucket.

### 4.2. VPC, Security Groups, and NACLs

AWS operates the underlying network. Within Amazon VPC, the customer decides subnets, route tables, Internet connectivity, Security Groups, network ACLs (NACLs), and traffic paths from applications to resources.

- **Security Group:** a stateful network filter attached to supported resources; the customer defines inbound/outbound rules.
- **Network ACL:** a stateless filter at the subnet level; both inbound and outbound traffic must be accounted for.
- **Public/private subnet:** depends on routing and connectivity design; placing a machine inside a VPC does not automatically isolate it from the Internet.
- **Network segmentation:** open only genuinely required paths from the load balancer to the application and from the application to the database.

A better pattern for a website is allowing HTTPS from the Internet to an Application Load Balancer, allowing traffic only from the load balancer to the app, and allowing only the app to connect to RDS on the database port. Do not open administrative or database ports to all addresses merely for testing convenience.

### 4.3. Encryption and Keys

Encryption should be examined in two states:

| Case | Common measures | Responsibilities to clarify |
| --- | --- | --- |
| **Data in transit** | HTTPS/TLS, encrypted connections to databases and APIs. | The customer configures endpoints, appropriate TLS versions/policies, and verifies that connections use TLS. |
| **Data at rest** | Storage encryption for S3, EBS, RDS, or the corresponding service. | The customer verifies appropriate encryption modes, data read permissions, and key usage requirements. |
| **Key management** | AWS KMS and AWS-managed or customer-managed key options. | AWS operates the KMS platform; the customer manages key usage permissions, key policies, and key lifecycle according to the chosen key type. |

**Encryption does not replace authorization.** An application or IAM role permitted to decrypt and read data can still expose that data if permissions are overly broad or an account is compromised.

### 4.4. Monitoring, Logging, and Incident Response

AWS operates services such as Amazon CloudWatch, AWS CloudTrail, Amazon GuardDuty, and AWS Config. However, the customer must determine proper enablement/configuration, collection scope, retention period, alerting, and response procedures.

A baseline approach includes:

1. Capturing API events and necessary configuration changes; protecting logs against unauthorized modification or deletion.
2. Monitoring application errors, resource utilization, unusual logins, and sensitive IAM changes.
3. Routing alerts to on-call responders; maintaining triage and incident response playbooks.
4. Periodically testing investigation capability from logs instead of enabling services and forgetting them.

Do not equate **having a logging service** with **having logging that meets requirements**. For example, CloudTrail provides Event History for a subset of management events over a limited window, whereas longer retention, data events, or multi-account log centralization require additional configuration.

### 4.5. Availability, Recovery, and Cost

AWS manages Region/AZ infrastructure and provides services for scalable systems. The customer decides the application architecture and the target level of fault tolerance:

- **High availability:** consider multiple AZs for critical components, health checks, load balancing, and failover mechanisms.
- **Disaster recovery:** define RPO (maximum acceptable data loss) and RTO (maximum recovery time), then choose backups/cross-Region replication if needed.
- **Testing:** run restore and failover drills to validate realistic targets.
- **Cost:** choosing Multi-AZ, backup retention, logging, replication, and encryption can increase costs. Balance business requirements, risk, and budget.

A system placing the entire application and database in a single AZ can still suffer an outage when that AZ experiences an issue, even while AWS fulfills its infrastructure operational responsibilities.

## 5. Four Scenarios Where Responsibility Is Easily Confused

| Scenario | Responsibility analysis | Required action |
| --- | --- | --- |
| S3 holds customer documents with a policy accidentally allowing public access. | AWS operates S3, but object sharing permissions are a customer configuration. | Block the misconfigured access, check account/bucket Block Public Access, and analyze logs and affected data scope. |
| EC2 runs a web library with a known patched vulnerability that has not been updated. | AWS manages the host/hypervisor; the customer manages the app and OS inside EC2. | Patch the library/OS, inspect the instance, revoke exposed credentials, and redeploy from a trusted image. |
| An AZ goes down, making a single-AZ application unreachable. | AWS is responsible for AZ infrastructure; the customer is responsible for choosing a fault-tolerant architecture that meets requirements. | Deploy critical components across multiple AZs and test failover. |
| Lambda uses an overly broad IAM role and is exploited to read data beyond what is needed. | AWS operates the Lambda environment; the customer defines function permissions and secures the code. | Narrow the IAM policy, investigate CloudTrail/logs, fix code or configuration, and rotate secrets if needed. |

When investigating a real incident, **responsibility often involves both sides at different layers**. For example, AWS is responsible for maintaining the security of the KMS service, while the customer must define appropriate key usage permissions. The model helps clarify actions and control boundaries; it does not replace service agreements, support terms, legal obligations, or incident response procedures.

## 6. Illustrative Design: An E-Commerce Web Application on AWS

Suppose a team builds an order-intake application with the following components:

- Application Load Balancer (ALB) receiving HTTPS.
- EC2 running the API and business logic in private subnets; if resilience to AZ failure is required, use multiple instances and appropriate Auto Scaling.
- Amazon RDS storing order data, with access restricted to the application.
- S3 storing invoices/attachments.
- An IAM role for EC2, CloudTrail/CloudWatch for monitoring, KMS, and backup/restore mechanisms as required.

~~~mermaid
flowchart TB
    USER["Users"] -->|HTTPS| ALB["Application Load Balancer"]
    subgraph VPC["Customer VPC"]
        ALB --> APP_A["EC2 App — AZ A"]
        ALB --> APP_B["EC2 App — AZ B"]
        APP_A --> DB[("RDS — database")]
        APP_B --> DB
    end
    APP_A --> S3[("Amazon S3 — documents")]
    APP_B --> S3
    LOG["CloudTrail / CloudWatch"] -.-> APP_A
    LOG -.-> APP_B
~~~

This diagram illustrates only the **logical flow**; connectivity paths must be implemented with proper routes, Security Groups, endpoints/NAT, and network configuration. If RDS Multi-AZ is chosen, the standby/failover topology is a separate configuration, not implied automatically by the drawing.

### Responsibility Assignment Matrix for the Architecture Above

| Item | AWS is responsible for | Application team is responsible for |
| --- | --- | --- |
| EC2 | Physical infrastructure and virtualization. | Image, OS, patches, application, IAM role, security rules. |
| ALB | Load balancing service infrastructure. | Listeners, TLS/certificates, target groups, routing, access controls. |
| RDS | Infrastructure and operational tasks provided by RDS. | Database setup, privileges, subnets/Security Groups, backup retention, Multi-AZ, restore tests. |
| S3 | Storage platform. | Bucket/object policies, Block Public Access, data classification, encryption, lifecycle/versioning. |
| IAM | AWS authentication and authorization platform. | Roles, policies, permissions boundaries, identity lifecycle governance. |
| Monitoring | Operating AWS observability tools. | Selecting logs/metrics, configuring alarms, on-call assignment, investigation, and response. |

### Practice: Checking Configurations by Responsibility

The following AWS CLI snippet is **read-only** to support self-assessment; it requires AWS CLI configured with appropriate permissions, and you should replace illustrative identifiers with resources from your own environment.

~~~bash
# Confirm the AWS identity used for the current session.
aws sts get-caller-identity

# Check the Block Public Access configuration of an S3 bucket.
aws s3api get-public-access-block --bucket example-private-reports

# Check the server-side encryption configuration of the bucket.
aws s3api get-bucket-encryption --bucket example-private-reports

# View inbound rules of a Security Group.
aws ec2 describe-security-groups \
  --group-ids sg-0123456789abcdef0 \
  --query "SecurityGroups[0].IpPermissions"

# Check RDS attributes related to networking, encryption, HA, and backups.
aws rds describe-db-instances \
  --db-instance-identifier example-orders-db \
  --query "DBInstances[0].[PubliclyAccessible,StorageEncrypted,MultiAZ,BackupRetentionPeriod]"
~~~

**How to interpret the output:**

- Bucket policies, IAM policies, and account-level permissions still need to be reviewed holistically; a single Block Public Access check does not prove data is definitely secure.
- If a command cannot find the bucket, receives access denied, or finds no configuration, inspect the context; do not treat that as proof that the system is protected.
- For Security Groups, review source addresses, protocols, and ports; for example, inbound SSH from 0.0.0.0/0 typically needs to be narrowed.
- For RDS, the returned attributes support an initial assessment. They do not replace checking subnets, routes, parameter groups, database accounts, and running restore drills.

## 7. Workflow for Real-World Projects

To avoid "responsibility gaps," a delivery team can follow this workflow.

**Step 1 — Map assets and data.** List AWS accounts, Regions, VPCs, EC2, S3, RDS, Lambda, sensitive data flows, and third-party services. Classify sensitivity levels and retention/recovery requirements.

**Step 2 — Review the responsibility boundary for each service.** Identify which infrastructure layers AWS manages, which code/configs the application team manages, and which options require the customer to proactively enable or configure them.

**Step 3 — Assign clear ownership.** Designate who manages IAM, OS/application patching, networking, databases, backups, logging, encryption keys, and incident response. If a managed service provider (MSP) is involved, define responsibilities in the contract while cross-checking against the AWS account owner's obligations.

**Step 4 — Implement verifiable controls.** Use Infrastructure as Code where appropriate; enforce MFA, least privilege, private networking, encryption, logging, configuration checks, and build/deploy standards.

**Step 5 — Verify and improve.** Conduct IAM permission reviews, Security Group/S3 audits, image/dependency vulnerability scans, retention reviews, restore tests, alert checks, and credential-compromise tabletop drills.

| Verification question | Expected evidence |
| --- | --- |
| Who is responsible for updating the EC2 operating system? | Specific owner, patch schedule, and recorded patch status. |
| Can any S3 object be accessed unexpectedly? | Effective access checks, Block Public Access, and relevant policies. |
| Does the workload have more permissions than its actual function requires? | IAM review and approved list of required permissions. |
| When one AZ fails, how does the application stay available? | Multi-AZ/failover architecture and test results. |
| If data is accidentally deleted, how long does recovery take? | Backup policy, restore drills, and RPO/RTO results. |
| During an incident, what data does the team use to detect and investigate? | Log sources, alarms, retention periods, and response runbooks. |

## 8. Common Misconceptions

**"AWS has compliance certifications, so my system is automatically compliant."** Incorrect. AWS certifications and compliance reports cover the scope of evaluated services and control layers; the customer must still meet requirements for data, identities, applications, how services are used, and applicable regulations. AWS Artifact can help access certain AWS compliance documents for assessment purposes.

**"Using a managed service means no patching is needed."** Incorrect. AWS may operate the host and underlying software, but the customer still manages applications, dependencies, configurations, and customer-selectable upgrade/version schedules.

**"Enabling encryption is enough."** Incorrect. Anyone with permission to decrypt/read can still access the data; proper authorization, secret protection, monitoring, and access control are required.

**"Data is in AWS, so AWS automatically backs up and recovers all my mistakes."** Incorrect. Backup, versioning, and replication mechanisms vary by service and configuration. The customer must define recovery objectives, configure them, and verify results.

**"AWS provides Regions/AZs, so the application is high-availability by default."** Incorrect. Eliminating single points of failure, choosing Multi-AZ/Multi-Region, scaling capability, and failover processes remain part of the customer's application design.

## 9. Self-Check Questions

**Question 1.** Who is responsible for patching vulnerabilities in the guest OS of a standard EC2 instance?  
**Answer:** The customer; AWS manages the underlying physical infrastructure and virtualization layer.

**Question 2.** Using RDS instead of self-installing PostgreSQL on EC2 shifts which responsibilities to AWS?  
**Answer:** Many infrastructure, underlying OS, and database operational tasks provided by the RDS service. The customer remains responsible for data, configurable settings/versions, privileges, connectivity, and backup/recovery objectives.

**Question 3.** Is AWS responsible if an S3 bucket becomes public due to a customer-configured bucket policy?  
**Answer:** Setting policies and controlling shared objects are the customer's responsibility; AWS secures the S3 service infrastructure. Effective configuration across all layers must be carefully evaluated.

**Question 4.** A Lambda application exposes data because its execution role has permission to read every bucket. Does serverless shift this responsibility to AWS?  
**Answer:** No. The customer defines the function's IAM permissions, application code, dependencies, and data.

**Question 5.** A website running in only one AZ experiences an outage when that AZ has an incident. What is the key architectural lesson?  
**Answer:** AWS's responsibility for infrastructure does not replace the customer building fault tolerance. You must design HA according to requirements, distribute resources appropriately, and verify failover.

## 10. Takeaways

The Shared Responsibility Model helps engineering teams answer a practical question: **which layer does AWS protect, and which layer must we configure and operate ourselves?** AWS provides and secures the cloud infrastructure. The customer secures data, identities, access permissions, applications, configurations, and recovery levels aligned with business requirements. Choosing higher-level managed services shifts some infrastructure tasks to AWS, but responsibility for data and how services are used always remains.

In every AWS design, define responsibilities **per service and per component**; then pair those responsibilities with clear owners, verifiable configurations, monitoring logs, backup plans, and recovery drills. This is the foundation for selecting the right services, operating securely, and managing risk and cost.

### Further Reading from AWS

- [AWS Shared Responsibility Model](https://aws.amazon.com/compliance/shared-responsibility-model/) — AWS's official Shared Responsibility Model.
- [AWS Well-Architected — Security Pillar](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/welcome.html) — principles for designing and operating security on AWS.
- [Amazon S3 — Security best practices](https://docs.aws.amazon.com/AmazonS3/latest/userguide/security-best-practices.html) — guidance on protecting data and configuring S3 access permissions.
