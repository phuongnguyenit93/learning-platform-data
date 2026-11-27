# Designing Trust Boundaries Across Projects and Environments

In Google Cloud, a project is a fundamental unit for organizing resources, assigning permissions, enabling APIs, managing quotas, and tracking costs. How projects are partitioned also determines the blast radius when an account, workload, or configuration is compromised. Therefore, trust boundary design must begin with the question: **which people, applications, and data are permitted to trust one another, and how far can damage spread if one component is taken over?**

This lesson belongs to the **CLOUD_PROVIDERS_GCP** module, covering everything from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage, and databases. The principles in this lesson apply both to application runtime environments and to CI/CD platforms, secrets management, encryption, and monitoring.

After this lesson, you will be able to:

- Choose project boundaries based on environment, data sensitivity, and governance scope.
- Design organization, folder, and project structures for intentional policy inheritance.
- Separate human permissions, workload permissions, and deployment permissions across dev, test, and production.
- Combine projects, Shared VPC, firewall policies, Organization Policies, and VPC Service Controls.
- Build deployment workflows, access validation tests, and monitoring for trust boundaries.

## 1. Trust Boundaries in Google Cloud

A trust boundary is the point at which you define which identities are allowed to access which resources, over which network paths, and under what conditions and control levels. A sound design restricts default permissions, requires explicit authorization when crossing boundaries, and logs critical activity.

A project is a useful administrative boundary because IAM policies, enabled APIs, quotas, billing, and many resource settings are managed per project. However, **a project is not automatically a complete security boundary**:

- IAM policies at the organization or folder level can inherit down into projects and grant permissions across many projects simultaneously.
- Shared VPC lets service projects use a network residing in a host project.
- IAM grants, service account impersonation, API endpoints, or network links can create cross-project access paths.
- Managed services have their own scopes and access models; not every resource is protected by the same mechanism.

Therefore, never look solely at project names to conclude two workloads are isolated. Evaluate four dimensions simultaneously: **identity, resources, network, and data**.

| Control Dimension | Design Question |
|---|---|
| Identity | Who can log in, deploy, impersonate service accounts, or read data? |
| Resources | Which project owns workloads, secrets, encryption keys, data, and logs? Which policies are inherited? |
| Network | Which subnets, IP addresses, APIs, or services can a workload connect to? |
| Data | Who can read, export, copy, decrypt, or modify data across environments? |

## 2. Choosing Project Boundaries by Environment and Trust Level

No single fixed number of projects fits every organization. Create separate projects when two groups of resources need to differ in administrative permissions, sensitivity level, policies, quotas, lifecycle, or incident blast radius.

### Separating Production from Non-Production

Each environment should have dedicated projects. For example, an ordering application can be organized as follows:

~~~mermaid
flowchart TB
    O["Google Cloud Organization"]
    O --> P["Folder: production"]
    O --> N["Folder: non-production"]
    O --> S["Folder: platform-and-security"]
    O --> B["Folder: sandbox"]
    P --> PP["Project: orders-prod"]
    P --> PN["Project: orders-data-prod"]
    P --> PH["Project: net-prod"]
    N --> ND["Project: orders-dev"]
    N --> NT["Project: orders-test"]
    N --> NH["Project: net-nonprod"]
    S --> L["Project: central-logging"]
    S --> K["Project: security-tools"]
    B --> BS["Dedicated sandbox projects"]
~~~

In this model:

- **orders-prod** runs production workloads; **orders-data-prod** holds high-sensitivity data and can be managed independently by the data team.
- **orders-dev** and **orders-test** host non-production workloads. They are not allowed by default to read production secrets, data, or keys.
- **net-prod** and **net-nonprod** are separate Shared VPC host projects, allowing the networking team to manage connectivity centrally while maintaining a boundary between the two environments.
- **central-logging** receives centralized logs; **security-tools** hosts security inventory and monitoring tools.
- Sandboxes are governed by dedicated policies, quotas, and budgets so experiments cannot impact critical environments.

Separating projects lets you apply IAM, Organization Policies, quotas, and billing per environment. Separating folders enables inheriting shared policies across groups of projects. If production and non-production require different controls, place them in separate folders so distinct policies can be enforced.

### When Is a Separate Project Needed for Data?

Create a dedicated data project when the data team requires independent administrative permissions, when data carries a higher classification than workloads, when storage or encryption key policies differ, or when multiple applications share a centrally governed data domain. Separating projects adds an IAM and governance boundary, though it also increases connectivity, logging, and operational setup work.

If data and application share the same owners, classification level, and lifecycle, one project per application and environment may be sufficient. Choose boundaries based on real differences in permissions and risk, avoiding fragmentation just for the sake of having more projects.

### Foundational Design Rules

1. Production never shares projects with dev, test, or sandbox.
2. Separate projects when owners, trust levels, or compliance requirements differ.
3. Do not grant permissions at the organization or folder level broader than the team's needs.
4. Use separate networking projects per trust domain when applying Shared VPC.
5. Keep logs and security tools in central projects with restricted administrative permissions.
6. Every cross-project access path must have an owner, justification, and monitoring.

## 3. Designing Identity Boundaries with IAM

IAM controls which principal can perform which actions on resources. In multi-project environments, inherited permissions and directly granted permissions must be evaluated together.

### Human Permissions

Manage permissions through Google Groups or enterprise identity groups instead of assigning permissions directly to individuals. Groups can be separated by role and environment:

| Group | Typical Permissions | Scope |
|---|---|---|
| **gcp-platform-admins** | Platform and shared structure administration | Platform folder or foundational projects |
| **orders-devs** | Develop, view logs, and deploy to dev | Project orders-dev |
| **orders-testers** | Test, read logs, and run test suites | Project orders-test |
| **prod-operators** | Operate production according to duties | Required production projects |
| **security-auditors** | Read configurations and audit logs | Assigned audit scope |

Do not grant broad **Owner** or **Editor** roles to development teams merely so they can deploy applications. Use narrower predefined roles or custom roles matching required operations. Log reading permissions should not imply permission to alter workloads; deployment permissions should not automatically include editing IAM or reading every secret.

Permissions at the organization and folder levels carry broad impact. Only a platform admin team with clear accountability should receive high-level administrative permissions. When a team only operates **orders-prod**, grant permissions at that project rather than the production folder if they do not need to manage other projects.

### Workload and Pipeline Permissions

Each application should have a dedicated service account per environment, for example:

- **orders-api-dev** accesses only dev resources.
- **orders-api-test** accesses only test resources.
- **orders-api-prod** accesses only required production resources.

Attach the appropriate service account to workloads on Compute Engine, GKE, or Cloud Run. Grant permissions to read secrets, write buckets, or access databases directly on target resources with minimal scope. Never reuse a single service account with permissions across all three environments for configuration convenience.

Deployment pipelines should use separate identities per environment. CI can build artifacts, run tests, and hold dev/test deploy permissions; production releases require a dedicated production identity alongside appropriate approval gates. If CI runs outside Google Cloud, prefer Workload Identity Federation to exchange short-lived credentials rather than storing long-lived service account keys.

Avoid downloading and distributing service account key files. Long-lived keys are easily copied from build machines, logs, or source repositories. When a pipeline must impersonate a service account, grant impersonation permissions only on the exact target service account and restrict which principals may impersonate it.

### Cross-Project Permissions Must Be Explicit

For example, an application in **orders-prod** needs to read a bucket in **orders-data-prod**. Grant read permissions to the production service account on that exact bucket or required resource. Do not add that service account as an administrator of the data project if the application only needs to read one dataset.

When auditing access permissions, inspect all of the following:

- Direct IAM policies on the resource.
- Inherited IAM policies at project, folder, and organization levels.
- Service account impersonation permissions.
- Access granted via groups or principal sets.
- IAM Conditions and context-aware access rules if used by the organization.

## 4. Designing Network Boundaries

A VPC network belongs to one project and has global scope; subnets have regional scope. Firewall rules, routes, Cloud NAT, and network connections are configured at varying scopes. Thus, two separate projects can still communicate if the organization actively connects them.

### Use Separate Networks per Trust Domain

For systems with production and non-production, consider two separate Shared VPC host projects:

- **net-prod** contains the production VPC, application subnets, and production data subnets.
- **net-nonprod** contains the dev/test VPC, test subnets, and controlled Internet egress paths.

The networking team manages host projects and subnets; application teams deploy resources into linked service projects. Shared VPC reduces network operational duplication while creating a trust relationship between the host project and service projects. Do not mix workloads with different trust levels into the same shared network if isolation policies mandate independent boundaries.

Example enabling Shared VPC and associating a service project:

~~~bash
# Enable Shared VPC on the production host project
gcloud compute shared-vpc enable net-prod

# Associate the production application project with the host project
gcloud compute shared-vpc associated-projects add orders-prod --host-project=net-prod
~~~

Replace project IDs with actual IDs. The operator needs appropriate Shared VPC admin permissions on the host project and project association permissions. After linking, share only required subnets and grant subnet usage permissions to the right operational groups.

### Controlling Network Flows

- Use custom VPCs and subnets organized by region, tier, or trust domain.
- Define permitted sources and destinations; open firewall rules only for required protocols, ports, and source ranges.
- Use hierarchical firewall policies when mandatory rules are required at the organization or folder level.
- Limit public IPs for internal workloads; consider Private Google Access, Cloud NAT, and Private Service Connect depending on service access patterns.
- Document cross-VPC, VPN, Interconnect, or peering connections; review routes and access permissions after every change.

Firewalls only control network traffic within their scope. Firewalls do not replace IAM: an application may reach an API over an allowed network path and must still be denied if the principal lacks permissions on the resource.

## 5. Protecting Data and Secrets by Environment

Project boundaries must be reflected in how data is stored and encrypted. If production workloads run in a separate project yet share buckets, secrets, or keys with dev, the trust boundary can still be breached at the data layer.

### Storage and Databases

- Use separate buckets, datasets, and databases per environment or data domain.
- Grant permissions only to service accounts of the corresponding environment; avoid granting production read access to the entire developer group.
- Enable public access prevention for Cloud Storage where appropriate and use uniform bucket-level access to manage permissions centrally via IAM.
- Apply storage, retention, backup, and data location policies aligned with classification and compliance requirements.
- Never copy production data verbatim into dev/test if it contains sensitive information. Apply masking, tokenization, or generate synthetic data before sharing.

### Secret Manager and Cloud KMS

Create separate secrets per environment. For instance, **orders-db-password-prod** exists and grants permissions strictly within production scope; dev secrets hold separate values and access controls. Do not put production secrets into environment variables or configuration files committed to repositories.

For CMEK, consider separate CryptoKeys for production and non-production, separate key admin permissions from key usage permissions, and control who can decrypt data. Separating keys by environment allows revoking or altering policy in one environment without directly impacting the other.

## 6. Using Organization Policy to Set Guardrails

Organization Policy allows organizations to place configuration restrictions across the resource hierarchy. Policies can be set at the organization, folder, or project level; child nodes inherit policies from parent nodes unless inheritance overrides or exceptions permit otherwise.

Commonly considered guardrails include:

| Objective | Example Constraint | Rationale |
|---|---|---|
| Restrict long-lived service account keys | **constraints/iam.disableServiceAccountKeyCreation** | Reduce risk of static key exposure |
| Skip creating the default network | **constraints/compute.skipDefaultNetworkCreation** | Avoid default networks with unsuitable configurations |
| Restrict resource locations | **constraints/gcp.resourceLocations** | Support data residency requirements |
| Control IAM members outside allowed domains | **constraints/iam.allowedPolicyMemberDomains** | Reduce accidental grants to external identities |

These examples must be evaluated against the organization's services and identity model before enforcement. Some constraints vary in supported scope or management behavior; inspect current constraint documentation and pilot on a representative folder/project.

Manage project provisioning through a controlled project creation process or project factory. This process can automatically attach folders, billing accounts, admin groups, log sinks, budgets, required APIs, and Organization Policies. Project creators should not be able to arbitrarily pick a less-restricted folder to bypass production policies.

Do not set overly broad exceptions at the organization level just to make one special workload function. If a system genuinely needs an exception, place it in a folder with a clear owner, justification, review deadline, and compensating controls.

## 7. Using VPC Service Controls for Supported Data Services

VPC Service Controls (VPC SC) creates a service perimeter around projects and supported Google Cloud services to reduce the risk of data leaving the trusted domain via APIs. Perimeters can be paired with access levels and ingress/egress policies to specify permitted access sources.

For example, production projects containing sensitive data can belong to a dedicated perimeter. A principal from a dev project cannot by default call APIs to read data inside that perimeter, even if a misconfigured IAM policy accidentally granted broad permissions; the request must still satisfy perimeter rules.

VPC SC requires careful design:

- Protects only services and operations supported by VPC SC; not every Google Cloud API sits inside the perimeter.
- Does not replace IAM, firewalls, or identity controls.
- Cross-project connections, CI/CD tools, support accounts, and data export/import flows may require explicit ingress or egress rules.
- Run dry-run mode to observe requests that would be blocked, analyze logs, and tune before enabling enforcement.
- Test administrative and operational flows too; an overly tight perimeter can break backups, deployments, or legitimate support access.

VPC SC fits data domains needing reduced exfiltration risk across supported services. It is an additional control layer in a defense-in-depth architecture, not a way to build private networking for every workload.

## 8. Separating Pipelines and Release Workflows

Production boundaries must be preserved across both build and deploy stages. A sound model builds artifacts once, stores them in a managed registry, and promotes the exact same artifact through test and production. Use immutable digests to ensure production runs the exact artifact that was tested.

Example release flow:

~~~mermaid
flowchart LR
    C["Source repository"] --> B["Build project"]
    B --> A["Artifact Registry"]
    A --> D["Deploy dev identity"]
    D --> T["Test project"]
    T --> G["Approval gate"]
    G --> P["Deploy production identity"]
    P --> R["Production project"]
    D -. "No access permissions" .-> R
~~~

Control points:

1. Separate build permissions from deploy permissions; the build pipeline does not need production admin permissions.
2. Use dedicated deploy service accounts per environment.
3. Require approvals or release conditions for production.
4. Allow the production pipeline to access only required production secrets and resources.
5. Log build history, approvers, artifact digests, deploy identities, and rollout results.
6. Revoke pipeline permissions or credentials when a repository, runner, or workload identity is no longer trusted.

## 9. Monitoring and Testing Trust Boundaries

A boundary is only valuable when the organization can detect boundary crossings or unexpected changes.

- Enable and centralize Cloud Audit Logs per requirements; pay special attention to IAM changes, Organization Policy changes, network configurations, KMS, and data access.
- Use aggregated log sinks to send logs to a security or logging project managed by an independent team.
- Restrict permissions to delete logs, change retention, or alter sinks for audit logs.
- Use Security Command Center and inventory tools to detect public resources, misconfigurations, or overly broad permissions.
- Set alerts for high-level IAM changes, adding projects to perimeters, firewall policy edits, and service account impersonation grants.
- Periodically review inherited permissions, unused service accounts, cross-project links, and Organization Policy exceptions.

### Testing with Negative Scenarios

Do not test only that legitimate users can access resources. Verify that disallowed actions are denied:

| Test Scenario | Expected Outcome |
|---|---|
| Dev developer reads production secret | Denied |
| Dev service account impersonates production service account | Denied |
| Non-production workload connects to production data subnet | Blocked unless an approved flow exists |
| Project outside perimeter calls sensitive data API inside perimeter | Denied by VPC SC if request fails ingress/access policy |
| Application deployer grants themselves Owner role | Denied |
| Production IAM or firewall change | Recorded in audit logs and triggers alert per policy |

Run tests using test accounts and representative workloads. Record the principal, project, resource, timestamp, applicable policy, and result. When access is denied, verify it was blocked by the intended policy rather than an unrelated misconfiguration causing an outage.

## 10. Example Commands to Inspect IAM and Shared VPC

Retrieve a project's IAM policy to inspect direct bindings:

~~~bash
gcloud projects get-iam-policy orders-prod
~~~

Grant log viewing permission to the operations group on the exact production project:

~~~bash
gcloud projects add-iam-policy-binding orders-prod --member="group:prod-operators@example.com" --role="roles/logging.viewer"
~~~

This example only grants log viewing; it does not grant deployment or workload modification permissions. Substitute your actual project ID, group email, and role. Before adding a binding, check inherited permissions from folders and the organization to avoid unintentionally expanding scope.

To inspect Shared VPC configuration:

~~~bash
# View the host project currently providing Shared VPC
gcloud compute shared-vpc get-host-project orders-prod

# List service projects associated with the host project
gcloud compute shared-vpc list-associated-resources net-prod
~~~

Commands are only configuration checks. Also cross-check shared subnets, subnet usage IAM permissions, firewall policies, and actual connection flows.

## 11. Common Design Mistakes

- **Separating folders while sharing a single project**: IAM, quotas, and many settings still live at the project level. Separate projects when true governance boundaries are needed.
- **Putting dev and production into the same Shared VPC**: both environments share network infrastructure and can affect each other through changes. Use separate host projects when isolation is needed.
- **Granting organization-level permissions to fix a local issue**: permissions cascade down across many projects. Grant permissions at the narrowest suitable scope.
- **Sharing service accounts across environments**: a single exposed credential can open a path into production. Create dedicated identities and grant separate permissions.
- **Assuming VPC SC replaces IAM**: perimeters do not replace resource authorization and do not cover every service.
- **Assuming separate projects equal isolated data**: shared buckets, secrets, keys, or databases still create cross-project dependencies.
- **Letting dev read production data for easier debugging**: use masked data or synthetic data instead.
- **Enabling policies or perimeters directly in enforcement mode without testing**: can break backups, deployments, and legitimate operational flows. Use test environments and dry-run mode when supported.
- **Failing to centralize audit logs**: privileged users in one project could tamper with local logs. Ship logs to a central project with independent permissions.

## 12. Design Checklist

Before promoting a system to production, confirm:

- [ ] Separate projects exist for production, dev, test, and sandbox matching isolation needs.
- [ ] Folders reflect governance and policy domains; inherited permissions have been reviewed.
- [ ] Data, secrets, encryption keys, and log projects have clear owners.
- [ ] User groups and service accounts are separated by role and environment.
- [ ] Long-lived service account keys are avoided wherever short-lived identities or federation can be used.
- [ ] Cross-project permissions are explicitly granted, scoped to exact resources, and logged.
- [ ] Shared VPC, firewalls, and network connectivity accurately reflect trust domains.
- [ ] Organization Policies have been piloted and have an exception management workflow.
- [ ] VPC SC is applied to appropriate services, with dry-run and ingress/egress flows validated.
- [ ] Build and deploy pipelines separate identities; production has release approval gates.
- [ ] Audit logs are centralized, protected from tampering, and monitored with alerts for sensitive changes.
- [ ] Negative access scenarios that must be denied have been tested.

## 13. Self-Check

1. Why are separate projects for production and dev insufficient to guarantee isolation if both projects share the same Shared VPC?
2. When should IAM permissions be placed at the folder level versus directly on a project?
3. Why should service accounts used for production workloads be separated from dev service accounts?
4. What protective layer does VPC Service Controls add, and why is IAM still required?
5. A build pipeline needs to release the same artifact through test and production. How can you avoid granting the pipeline production administrative permissions?

**Suggested Answers**

1. Shared VPC creates network connectivity and an administrative relationship between the host project and service projects; firewalls, subnets, and subnet usage permissions can allow the two environments to impact each other.
2. Place at the folder level when permissions apply uniformly across child projects; place at the project level when only one project requires those permissions.
3. Separating service accounts limits blast radius when a credential is exposed and prevents dev workloads from inheriting production permissions by default.
4. VPC SC reduces the risk of data leaving the perimeter through supported Google Cloud services; IAM still decides whether a principal is permitted to perform operations on a resource.
5. Build the artifact once, store it as an immutable artifact, then use separate deploy identities for test and production; the production pipeline receives permissions only on the target deployment project and resources, gated by appropriate approvals.

## References

- [Google Cloud: Resource hierarchy](https://cloud.google.com/resource-manager/docs/cloud-platform-resource-hierarchy)
- [Google Cloud: IAM overview](https://cloud.google.com/iam/docs/overview)
- [Google Cloud: Shared VPC](https://cloud.google.com/vpc/docs/shared-vpc)
- [Google Cloud: Hierarchical firewall policies](https://cloud.google.com/firewall/docs/firewall-policies)
- [Google Cloud: Organization Policy overview](https://cloud.google.com/resource-manager/docs/organization-policy/overview)
- [Google Cloud: VPC Service Controls overview](https://cloud.google.com/vpc-service-controls/docs/overview)
- [Google Cloud: Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation)
- [Google Cloud: Cloud Audit Logs](https://cloud.google.com/logging/docs/audit)
