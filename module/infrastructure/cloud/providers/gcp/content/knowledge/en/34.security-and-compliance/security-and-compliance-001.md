# Designing Defense in Depth for GCP Resources

A secure Google Cloud environment requires multiple layers of controls working together. IAM restricts who can do what; Organization Policy restricts which configurations are allowed; private networking controls traffic paths; workload and data configurations reduce blast radius when a component is compromised; and logging, alerting, and incident response processes help detect incidents before they spread.

Within the scope of **CLOUD_PROVIDERS_GCP**, this lesson progresses from organizational structure, projects, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases. The goal is to know how to choose the appropriate protection layers, implement them in a consistent architecture, automate checks, and monitor reliability and cost.

After this lesson, learners will be able to:

- Partition security boundaries across organizations, folders, projects, and workloads.
- Combine IAM, Organization Policy, and network controls according to the principle of least privilege.
- Choose appropriate protections for virtual machines, Kubernetes, serverless services, storage, and databases.
- Configure encryption, secrets management, audit logging, and threat detection.
- Integrate security controls into Infrastructure as Code and release pipelines.
- Evaluate a design using access flows, attack scenarios, and operational evidence.

## 1. Defense-in-Depth Mindset

Defense in depth assumes that any single control can be misconfigured, bypassed, or compromised. Therefore, a critical access request must be verified across multiple independent boundaries.

For example, a web service should only read data from Cloud Storage when all of the following conditions are simultaneously satisfied: the workload runs with a service identity granted read access only to the specific bucket; the bucket disallows public access; network access paths and organization policies allow it; the data is encrypted; and access operations are logged and auditable. If one layer is misconfigured, the remaining layers can still limit the scope of damage.

Common layers:

| Layer | Question to Answer | Typical Controls |
|---|---|---|
| Organizational Governance | Which resources are allowed to exist and where? | Resource hierarchy, Organization Policy, project separation |
| Identity | Who or which workload is allowed to perform an action? | IAM, IAM Conditions, service accounts, Workload Identity Federation |
| Network | Which traffic is allowed ingress, egress, and cross-zone traversal? | VPC, subnets, firewall policies, Cloud NAT, Private Service Connect |
| Workload | How are virtual machines, containers, and runtimes securely configured? | Shielded VM, GKE security, Cloud Run ingress, patching |
| Data | How is data classified, accessed, encrypted, and recovered? | Cloud KMS, Secret Manager, bucket controls, database private IP |
| Supply Chain | Which source code and images are allowed to be released? | CI/CD identity, image scanning, Binary Authorization, provenance |
| Detection and Response | How do we know an incident occurred and limit its impact? | Cloud Audit Logs, Security Command Center, Cloud Logging, alerts |

Not every workload requires every security product. Start from assets, data, access flows, and threats; then choose controls proportional to risk, compliance requirements, and operational cost.

### 1.1. Identifying Assets and Trust Boundaries

Before creating firewall rules or assigning IAM roles, compile an inventory of:

1. Assets: projects, VMs, clusters, services, buckets, databases, secrets, encryption keys, and pipelines.
2. Owners: teams responsible for operations and teams responsible for approving access.
3. Data: public, internal, sensitive, or subject to specific residency/retention requirements.
4. Data flows: calling sources, destinations, protocols, identities used, and data in transit.
5. Threats: compromised accounts, public exposure, lateral movement, secret theft, malicious image deployment, or data deletion.

Trust boundaries do not necessarily align with network boundaries. A VM in a private subnet can still be compromised for unauthorized access if its service account has overly broad permissions. Conversely, a service with a public endpoint can still be protected through authentication, ingress controls, WAF, and strict data access permissions.

## 2. Governance Layer: Organizations, Folders, Projects, and Organization Policy

Google Cloud organizes resources in a hierarchy:

~~~text
Organization
├── Folder: production
│   ├── Project: app-prod
│   └── Project: data-prod
├── Folder: non-production
│   ├── Project: app-dev
│   └── Project: app-test
└── Folder: security
    └── Project: central-security
~~~

IAM allow policies and Organization Policies can be inherited from parent nodes down to child nodes. A well-designed hierarchy enables applying common rules at higher levels while allowing controlled exceptions at narrower scopes.

### 2.1. Separating Projects by Environment and Responsibility

- Separate production from development/test so that experimentation permissions do not automatically grant access to real data.
- Separate shared networking, logging/security, and workload projects when the organization requires distinct administrative boundaries.
- Use Shared VPC when multiple workload projects need to share a single network managed by the networking team. The host project owns the network; service projects contain the workloads.
- Use clear naming, labels, and owners to trace costs, assets, and accountability.
- Restrict project creation and organization structure modification permissions to a small administrative group.

Project separation alone does not create security. You must also review IAM permissions, network peering/links, service accounts, log sinks, and cross-project data access paths.

### 2.2. Using Organization Policy to Block Risky Configurations

Organization Policy places configuration restrictions on resources. Some commonly considered constraints include:

- **constraints/iam.disableServiceAccountKeyCreation**: prevents creating file-based service account keys.
- **constraints/iam.disableServiceAccountKeyUpload**: prevents uploading external service account keys.
- **constraints/storage.publicAccessPrevention**: prevents granting public access to Cloud Storage.
- **constraints/compute.vmExternalIpAccess**: restricts which VMs are allowed to have external IP addresses.
- **constraints/compute.requireShieldedVm**: requires using Shielded VMs where supported.
- **constraints/gcp.resourceLocations**: restricts resource creation locations according to organizational policy.

The applicability and behavior of each constraint depend on the resource type, service version, and supported scope. Review the constraint documentation before enforcing it at the organization level.

Safe rollout process:

1. Select a pilot folder or project.
2. Identify whether existing resources violate the constraint.
3. Test in audit mode or run impact analysis if supported by the constraint.
4. Handle workloads requiring exceptions through an approval workflow.
5. Enforce at the appropriate scope, monitor deployment errors, and periodically review exceptions.

Organization Policy and IAM address two different questions. IAM determines which actions a principal is permitted to call; Organization Policy restricts which configurations are allowed to exist. Blocking public IP creation does not replace reviewing IAM permissions, and granting an IAM permission does not make a configuration prohibited by Organization Policy valid.

## 3. Identity Layer: IAM and Service Accounts

In the cloud, identity is the primary security boundary. A request can come from a user, group, service account, workload in GKE, or external CI/CD system.

### 3.1. Applying Least Privilege

- Grant permissions to Google Groups instead of assigning them directly to many individual user accounts.
- Prefer predefined roles suited to the task. Create custom roles when predefined roles grant excessive permissions and the organization can maintain custom roles.
- Avoid using primitive roles (Owner, Editor, and Viewer) for day-to-day work because of their broad scope.
- Assign roles at the smallest node that meets the requirement: resource or project rather than organization if organization-wide permissions are not needed.
- Use IAM Conditions to restrict permissions by time, resource attributes, or supported context.
- Separate deployment permissions, operational permissions, and log-reading permissions; do not use a single administrative account for every job.

For example, a development team that needs to deploy Cloud Run can be granted permissions to deploy services in the application project and permission to act as the specific runtime service account. This team does not need organization admin permissions, permission to modify company-wide firewalls, or permission to read all production secrets.

### 3.2. Designing Service Accounts for Workloads

Each workload should have a dedicated identity scoped by function and environment. Do not share a single overly broad service account across multiple applications, because if one application is compromised, an attacker can inherit all permissions of the shared identity.

- Grant only the roles needed for the workload to read/write the specific resources.
- Do not embed JSON keys in source code, container images, long-lived environment variables, or CI variables.
- Prefer runtime-attached identities and impersonation mechanisms instead of long-lived keys.
- Use Workload Identity Federation so CI/CD or workloads outside Google Cloud obtain short-lived credentials without storing service account keys.
- For GKE, use Workload Identity Federation for GKE to map a Kubernetes ServiceAccount to Google Cloud permissions.
- Review permissions of service-managed service agents; do not delete or modify service agent roles based on guesswork.

Service account keys should only be exceptions with a documented justification, owner, expiration, and revocation process. If keys must be used in legacy systems, store them in a controlled secret vault, restrict where they are used, monitor usage, and plan their deprecation.

### 3.3. Periodic Permission Reviews

IAM Recommender and Policy Intelligence can help detect underutilized permissions or analyze policy impact. These are signals for owners to review; you should not automatically revoke permissions based solely on a period of inactivity without understanding business processes.

When investigating a denied request, inspect the principal, resource, permission, inherited policies, IAM Conditions, deny policies, and Organization Policies. A 403 error does not necessarily mean a simple missing role.

## 4. Network Layer: Segmentation, Ingress, and Egress Controls

VPC creates a logical network scope for resources. Subnets partition IP address ranges by region; firewall rules and firewall policies control traffic; private connectivity services reduce the need to expose resources to the Internet.

### 4.1. Segmenting Networks by Business Flow

Network design should originate from required communication flows:

- Web/API tiers only receive traffic from load balancers or designated sources.
- Application tiers only call databases on required ports.
- Databases do not accept direct connections from the Internet.
- Management traffic traverses IAP or a dedicated administrative path.
- Dev/test environments are not allowed to connect to production by default.
- Egress is opened only as needed; services needing to call Google APIs can use Private Google Access or Private Service Connect depending on the architecture.

Do not treat subnets as complete isolation. Within the same VPC, firewall policies still need to specify source, destination, protocol, and port. When using Shared VPC, align network management, firewall management, and workload deployment permissions between the host project and service projects.

### 4.2. Managing Firewalls

Prioritize explicit rules with clear owners and purposes:

1. Identify legitimate flows before creating rules.
2. Avoid opening SSH/RDP or management ports to the entire Internet.
3. Do not use overly broad source IP ranges when you can restrict by subnet, service account, tag, or appropriate identity.
4. Use hierarchical firewall policies when mandatory rules are needed at the organization/folder level; use VPC firewall rules for the corresponding network scope.
5. Review unused rules, duplicate rules, and rules whose priority overrides intended rules.
6. Inspect both ingress and egress, including traffic from workloads to external APIs.

An overly permissive rule can defeat network segmentation. Every firewall change should be evaluated against actual application flows and have a rollback plan.

### 4.3. Private Access and Outbound Connectivity

- **IAP TCP forwarding** enables VM administration via identity and IAM without opening public SSH/RDP.
- **Cloud NAT** provides NAT for outbound connections from workloads without external IPs; static NAT addresses can be configured when a stable source address is needed. Cloud NAT does not create an inbound connection path to VMs.
- **Private Google Access** allows VMs with only internal IP addresses to reach supported Google APIs and services.
- **Private Service Connect** provides private connectivity to Google services or services published by providers.
- **Cloud VPN** and **Cloud Interconnect** connect on-premises networks to VPCs through appropriate models for encryption, latency, and bandwidth.
- **Cloud Armor** protects applications behind load balancers using WAF policies and DDoS mitigation capabilities appropriate to the load balancer type.

### 4.4. Distinguishing Firewalls from VPC Service Controls

VPC Service Controls create a service perimeter around supported Google services to reduce the risk of unauthorized API access or data exfiltration outside the perimeter. It is useful for sensitive data in services such as Cloud Storage and BigQuery.

VPC Service Controls is not a general-purpose network firewall, does not replace IAM, and does not protect every API or every transmission path. Perimeter design must account for ingress/egress rules, projects, services, identities, devices, and integrated services. Test legitimate flows before enforcing to avoid breaking running pipelines or applications.

## 5. Workload Layer: Protecting Compute Engine, GKE, and Cloud Run

### 5.1. Compute Engine

- Use Shielded VMs where appropriate to strengthen boot-chain integrity with Secure Boot, vTPM, and integrity monitoring.
- Prefer VMs without external IPs; use IAP or a controlled bastion for administrative access.
- Enable OS Login and bind SSH permissions via IAM rather than managing SSH keys manually on each machine.
- Patch operating systems and packages on schedule; monitor update status and vulnerabilities.
- Restrict the VM's service account; the metadata server should not become a path to obtain overly broad credentials.
- Separate workloads by environment and sensitivity level; do not run unrelated applications under the same identity.

### 5.2. Google Kubernetes Engine

A Kubernetes cluster introduces a Kubernetes RBAC permission layer alongside Google Cloud IAM. Both must be controlled:

- Use private nodes and restrict control plane access paths according to the organization's network model.
- Use Workload Identity Federation for GKE so pods access Google APIs using dedicated identities.
- Apply Kubernetes RBAC by namespace and responsibility; avoid granting cluster-admin to application accounts.
- Use NetworkPolicy to restrict pod-to-pod communication where supported by the architecture and dataplane.
- Manage images through Artifact Registry; scan for vulnerabilities and deploy images only from trusted sources.
- Consider Binary Authorization to enforce policies on which images are permitted to run.
- Protect secrets, admission configurations, and access to the Kubernetes API; update the control plane and nodes on supported schedules.

A private cluster does not mean the cluster is secure. Overly broad RBAC permissions, malicious images, or high-privilege workload identities can still lead to compromise.

### 5.3. Cloud Run and Serverless Services

- Choose appropriate ingress settings: internal only, internal and load balancer, or broader access depending on product requirements.
- Enable IAM authentication for endpoints not intended for public access; if a service must be public, restrict ingress and protect behind a load balancer.
- Assign a dedicated runtime service account with least privilege.
- Use Secret Manager to provide secrets; do not bake secrets into images.
- Use Direct VPC egress or Serverless VPC Access when the service needs to reach private network resources, depending on the service type and architectural requirements.
- Set concurrency, timeout, CPU/memory, and autoscaling limits based on actual load to control reliability and cost.

Serverless reduces server management overhead but does not eliminate responsibility for protecting identities, applications, data, ingress configurations, and dependencies.

## 6. Data Layer: Access Control, Encryption, and Recovery

### 6.1. Cloud Storage

For buckets containing internal or sensitive data:

- Enable Uniform bucket-level access to manage permissions consistently with IAM rather than mixing IAM and ACLs.
- Enable Public Access Prevention to prevent accidental public exposure.
- Grant permissions only to service accounts or groups that require access.
- Use versioning, retention policies, or backup mechanisms aligned with recovery objectives.
- Control data location and object lifecycle to meet residency, retention, and cost requirements.
- Enable Data Access audit logs when evidence of who read or modified data is needed.

Terraform example for a private bucket:

~~~hcl
resource "google_storage_bucket" "private_data" {
  name                        = "example-project-private-data"
  location                    = "ASIA"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }
}
~~~

This is an illustrative configuration. Bucket names must be globally unique; location must be chosen according to data requirements; provider and deployment permissions must match the environment. Versioning helps recover objects but does not replace independent backups or restore testing procedures.

### 6.2. Cloud SQL and Databases

- Prefer private IP and VPC connectivity when applications run in a compatible network environment.
- Avoid overly broad authorized networks or allowing all source addresses.
- Use identities and authentication mechanisms supported by the service; do not share a single database account across all applications.
- Store credentials in Secret Manager and maintain a rotation/revocation schedule.
- Enable backups, point-in-time recovery, and test restores periodically.
- Restrict database privileges to required schemas, tables, or operations.
- Monitor connections, authentication failures, configuration changes, and sensitive queries as supported by the service.

Private IP reduces network exposure surface but does not enforce permissions at the database layer. Applications still require authentication and data-level authorization.

### 6.3. Cloud KMS and Secret Manager

Encryption at rest and in transit is a foundational layer. Google-managed encryption meets default needs for many scenarios; CMEK (customer-managed encryption keys) is appropriate when an organization requires control over key lifecycle, usage permissions, or specific audit requirements.

When using CMEK:

- Separate key administrators from data administrators where separation of duties is required.
- Grant key usage permissions only to the specific service agent for the right service and key.
- Design rotation, monitoring, and recovery plans for services and key access; with an external key manager, clarify backup capabilities with the provider.
- Understand the impact if a key is disabled or access is lost: workloads may be unable to read or write data.

Secret Manager is intended for secrets such as API tokens, passwords, and credentials. Scope permissions per secret, avoiding granting read access to all secrets for a workload; use versions, rotation, and audit logs appropriately. Do not write secrets into logs, exception messages, or pipeline outputs.

## 7. Software Supply Chain and Deployment Layer

A well-configured workload can still be compromised if the deployment pipeline releases untrusted images. The supply chain must be protected from source to runtime.

1. Protect repositories, branches, code reviews, and build system credentials.
2. Use Workload Identity Federation so external pipelines obtain short-lived credentials; separate build identity from deploy identity.
3. Grant the pipeline permission to push images only to the designated Artifact Registry repository and deploy only to the designated project/service.
4. Scan images for vulnerabilities, control dependencies, and generate artifact provenance where supported by the workflow.
5. Use Binary Authorization or equivalent admission controls to restrict which images may run.
6. Manage infrastructure with Terraform or IaC tools; review IAM, firewall, bucket, key, and policy changes just like code reviews.
7. Run policy checks in CI before applying; detect public buckets, overly broad permissions, unapproved external IPs, and missing encryption configurations.
8. Record who approved changes, which commit produced an artifact, and which artifact was deployed.

Do not grant a pipeline Owner permissions simply to deploy. Create narrow deployment roles scoped by service, resource, and environment; require separate approvals for production.

## 8. Detection Layer: Logging, Security Command Center, and Alerting

Preventive controls cannot guarantee zero incidents. Systems must produce sufficient evidence to detect, investigate, and recover.

### 8.1. Cloud Audit Logs

Cloud Audit Logs record activity on Google Cloud resources. Key log categories include:

- **Admin Activity**: administrative operations and configuration changes.
- **System Event**: actions performed by Google Cloud systems.
- **Policy Denied**: requests denied by policies where supported by the service.
- **Data Access**: data access or read/write operations requiring auditing; must be explicitly evaluated and enabled for sensitive services and data.

Route critical logs to a centralized logging/security project using aggregated sinks at the organization or folder level. Restrict permissions to read, modify, and delete logs; configure retention and exports to match investigation requirements. Centralized logging still requires managing ingestion, storage, and query costs.

### 8.2. Security Command Center

Security Command Center (SCC) provides visibility into security posture, vulnerabilities, misconfigurations, and threats across Google Cloud resources. Specific capabilities depend on the edition, enabled services, and deployment scope.

Operational workflows should include:

- Triaging findings by severity and actual exposure.
- Assigning owners and remediation deadlines.
- Prioritizing findings with clear exploit paths, sensitive data, or elevated privileges.
- Tracking remediation status and recurring findings.
- Routing critical findings into the organization's ticketing/incident system.

Cloud Asset Inventory supports asset inventory and configuration queries; Policy Intelligence supports permission analysis. Combine these sources to answer what assets exist, who has access, and what changes recently occurred.

### 8.3. Alerting and Response

Create alerts for operationally meaningful events, for example:

- IAM changes at the organization level or in production projects.
- New service account keys created or signs of anomalous credential usage.
- Firewall rules opening management ports to broad source ranges.
- Buckets or data services becoming public.
- Workloads generating anomalous egress traffic.
- Critical findings appearing or backup/restore failures.

Each alert must have a recipient, priority level, log source, verification steps, and remediation actions. Test response procedures using tabletop or simulated scenarios; enabling alerts without responders creates noise rather than reducing risk.

## 9. Architecture Example: API Application Using Cloud Run and Cloud SQL

Suppose an application receives Internet requests, processes them with Cloud Run, stores data in Cloud SQL, and stores files in Cloud Storage.

~~~mermaid
flowchart TD
    U[Internet Users] --> B[External HTTPS Load Balancer]
    A[Cloud Armor security policy] -. Attached to backend service .-> B
    B --> C[Cloud Run API]
    C -->|Dedicated runtime identity| D[Cloud SQL private IP]
    C -->|Restricted read/write permissions| E[Cloud Storage private bucket]
    C --> F[Secret Manager]
    D --> G[Backup and recovery]
    C --> H[Cloud Logging and Audit Logs]
    E --> H
    D --> H
    H --> I[Centralized security project]
    I --> J[Security Command Center and alerts]
~~~

Security decisions:

1. The load balancer is the entry point for Internet traffic; Cloud Armor enforces HTTP(S) protection policies.
2. Cloud Run restricts ingress to internal-and-cloud-load-balancing when the architecture uses an external Application Load Balancer; configure authentication to match how the application serves users.
3. Cloud Run runs with a dedicated service account having only the required database and bucket permissions.
4. Cloud Run uses Direct VPC egress or Serverless VPC Access to connect to Cloud SQL over private IP.
5. The bucket enables Uniform bucket-level access and Public Access Prevention; access is granted only to the application's service account.
6. Secret Manager stores required credentials; the application does not bake credentials into the image.
7. Database backups are configured according to RPO/RTO; the operations team tests restores.
8. Audit logs and application logs are routed to a central location; SCC and alerts help detect misconfigurations or anomalous activity.

What must be verified during implementation is the actual path from the load balancer to Cloud Run, invoke permissions, VPC connectivity, DNS, firewalls, Cloud SQL permissions, and secret read permissions. A conceptually sound diagram can still fail if a specific permission or network route is missing.

## 10. Phased Implementation Roadmap

Do not enable every policy across production all at once without understanding the impact. Deploy in sequence:

| Phase | Activities | Completion Evidence |
|---|---|---|
| 1. Inventory | List projects, assets, owners, data, and access flows | Inventory with owners and sensitivity levels |
| 2. Governance | Standardize folders/projects, enable appropriate Organization Policies | Policies tested, exceptions have owners |
| 3. Identity | Review broad roles, service accounts, keys, and CI/CD permissions | Least-privilege list, no unnecessary keys remaining |
| 4. Network | Segment VPCs, review firewalls, remove unnecessary public IPs | Permitted flows documented and tested |
| 5. Workload/Data | Harden VMs/GKE/Cloud Run, private buckets/databases, secrets, and backups | Configuration checks and restore tests pass |
| 6. Detection | Centralize audit logs, enable SCC, create alerts | Logs queryable, alerts have assigned responders |
| 7. Automation | Integrate policies and configuration checks into IaC/CI | Pipeline blocks sample policy violations |
| 8. Operations | Run incident drills, periodically review exceptions and permissions | Drill reports and action items with owners |

Each phase requires a rollback plan, an accountable owner, and a way to measure application impact. For changes that could block requests, test in a representative environment before expanding.

## 11. Design Review Checklist

### Organization and IAM

- [ ] Production is separated from development environments along appropriate boundaries.
- [ ] Owner/Editor permissions are restricted and an emergency access process exists.
- [ ] Workloads use dedicated service accounts with least privilege.
- [ ] No long-lived service account keys remain without justification and an owner.
- [ ] Organization Policies have clear scopes, exceptions, and testing procedures.

### Network and Workloads

- [ ] External IPs have been removed from VMs that do not require public IPs.
- [ ] SSH/RDP is not open to the entire Internet; administrative access is identity-based.
- [ ] Firewall rules have owners, purposes, and restricted sources/destinations.
- [ ] GKE has RBAC, Workload Identity Federation, and image controls.
- [ ] Cloud Run has appropriate ingress, authentication, and runtime identity settings.
- [ ] Databases do not accept public connections beyond approved requirements.

### Data and Operations

- [ ] Sensitive buckets enable Uniform bucket-level access and Public Access Prevention.
- [ ] Secrets are not stored in source code, images, or logs.
- [ ] Encryption, key access, and data locations meet requirements.
- [ ] Backups have defined RPO/RTO and restore testing has been performed.
- [ ] Required audit logs are enabled and routed to centralized storage.
- [ ] Critical findings have owners, deadlines, and remediation evidence.
- [ ] Costs for logs, network egress, backups, and security services are monitored.

## 12. Common Mistakes

**Relying solely on firewalls.** Firewalls do not replace IAM, application authentication, or database permissions. A compromised workload can still use an overly broad service account to read data.

**Using a single service account across multiple applications.** This expands the blast radius when one application is compromised. Separate identities by workload and environment.

**Assuming private IP means secure.** Private IP reduces direct exposure from the Internet, but does not stop internal principals with excessive permissions or compromised workloads.

**Enabling organization-level policies without impact assessment.** Constraints can break deployments for existing pipelines or services. Pilot first, document exceptions, and roll out in phases.

**Using VPC Service Controls as a general-purpose firewall.** Service perimeters focus on API access and data exfiltration risks for supported services; they do not replace firewalls, IAM, or general egress controls.

**Enabling logs without responders.** Logs are only valuable when retained long enough, queryable, and tied to alerting and response workflows.

**Assuming backups guarantee data recovery.** Only a tested restore proves that the backups, permissions, keys, and recovery procedures work together.

**Ignoring operational costs.** Data Access logs, long-term retention, Cloud NAT, egress, SCC, and backups can generate significant costs. Configure retention and sampling appropriately, and monitor budgets without sacrificing necessary evidence.

## 13. Official References

- [Organization Policy overview](https://cloud.google.com/resource-manager/docs/organization-policy/overview)
- [IAM overview](https://cloud.google.com/iam/docs/overview)
- [VPC firewall rules](https://cloud.google.com/vpc/docs/firewalls)
- [VPC Service Controls overview](https://cloud.google.com/vpc-service-controls/docs/overview)
- [Cloud Armor overview](https://cloud.google.com/armor/docs/overview)
- [Shielded VM overview](https://cloud.google.com/compute/shielded-vm/docs/shielded-vm)
- [Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation)
- [Cloud Audit Logs overview](https://cloud.google.com/logging/docs/audit)
- [Security Command Center overview](https://cloud.google.com/security-command-center/docs/concepts-security-command-center-overview)
- [Secret Manager overview](https://cloud.google.com/secret-manager/docs/overview)
- [Binary Authorization overview](https://cloud.google.com/binary-authorization/docs/overview)

When designing for a production system, re-verify current limits, editions, supported regions, and behavior in the respective product documentation. A defense-in-depth architecture is only effective when control layers are configured properly, tested against business flows, and maintained throughout the operational lifecycle.
