# Assured Workloads and Compliance Controls

When deploying systems on Google Cloud, organizations may need to meet requirements covering where data is stored, support personnel locations, permitted service types, encryption key management, and the ability to prove those rules are continuously enforced. **Assured Workloads** helps organizations establish a controlled boundary for sensitive workloads by applying predefined control packages to a Google Cloud folder. Accompanying policies and monitoring mechanisms help restrict non-compliant configurations, track violations, and surface information for remediation.

In the `CLOUD_PROVIDERS_GCP` module, this topic connects project organization and IAM with VPC design, choosing Compute Engine, GKE, Cloud Run, storage services, and databases. When a workload must comply with specific regional or regulatory requirements, the architecture requires more than simply picking the right service. Teams must also determine whether that service is supported under the control package, where data resides, who can access it, how keys are managed, and how configuration drift is detected.

Assured Workloads provides technical safeguards to support compliance requirements. Using the product does not automatically certify an entire application or organization as compliant with a law or standard. Customers remain responsible for data classification, application design, identity management, operational processes, governing external systems, and collecting evidence within their audit scope.

## Learning Objectives

After this lesson, learners will be able to:

- Explain the role of Assured Workloads and how control packages establish a control boundary for a workload.
- Distinguish regional data boundaries, regulatory data boundaries, and Sovereign Controls by Partners.
- Understand the relationship between folders, projects, organization policies, data residency, personnel controls, and key management.
- Identify IAM, billing, location, and supported product prerequisites before creating an Assured Workloads folder.
- Create and inspect a sample workload via the Google Cloud Console or `gcloud`.
- Monitor violations, handle exceptions, apply control package updates, and align responsibilities between Google Cloud and the customer.

## 1. Assured Workloads in Google Cloud Architecture

### What Problem Does Assured Workloads Solve?

A Google Cloud organization can contain many folders and projects serving different application teams. If all projects share one policy set, operations teams may struggle to enforce strict controls for one sensitive workload without disrupting general systems. Conversely, if each team builds its own policies independently, configurations easily diverge and become hard to evidence.

Assured Workloads provides a folder configured according to a **control package**. A control package bundles controls such as resource location restrictions, product/service restrictions, support personnel access requirements, and key management options. These policies apply to the folder and its descendant projects and resources within each mechanism's supported scope.

For example, an organization can place workloads processing medical records in a folder dedicated to Healthcare and Life Sciences, while general internal analytics applications remain in another folder. New projects created inside the compliance folder inherit restrictions matching the control package. When moving an existing project into the folder, teams must inspect existing resources, locations, services, and configurations beforehand.

### Position of Assured Workloads in the Resource Hierarchy

```text
Organization
├── Folder: internal applications
│   └── Project: reporting
│       └── BigQuery, Cloud Storage, Cloud Run
│
└── Folder: Assured Workloads
    ├── Control package: e.g., Data Boundary for FedRAMP High
    ├── Organization policies and associated controls
    ├── Project: sensitive records
    │   ├── Compute Engine / GKE
    │   ├── Cloud Storage / BigQuery (if supported)
    │   └── Cloud KMS / CMEK per package requirements
    └── Project: data processing services
```

A folder serves as an organizational and policy enforcement boundary. Projects remain the boundary for managing APIs, billing, IAM, and resources. An Assured Workloads folder does not automatically create every project or key required; deployment teams still must create projects, enable permitted services, grant IAM, and configure applications.

### Key Control Layers

| Control Layer | Question to Answer | Common Mechanisms |
|---|---|---|
| Data location | In which regions are resources and data stored? | Resource Locations organization policy, regional data boundary. |
| Permitted services | Which products/APIs may the workload use? | Resource Usage Restriction and the control package's supported products list. |
| Provider personnel | Who at Google can access data during support? | Personnel access controls, Assured Support, Access Transparency, Access Approval depending on package and service. |
| Encryption and keys | Who controls keys and where are keys stored? | Google-managed keys, CMEK, Cloud EKM, key import, or mechanisms per control package. |
| Monitoring | How are non-compliant configurations detected? | Assured Workloads violation monitoring, Cloud Audit Logs, and remediation workflows. |

These layers complement IAM, VPC, firewalls, workload hardening, vulnerability management, and incident response processes. Assured Workloads does not replace those foundational security controls.

## 2. Control Packages and Compliance Requirement Categories

Control packages form the foundation of Assured Workloads. Each package combines controls designed to support a specific category of legal, regulatory, regional, or data sovereignty requirement. Google Cloud organizes packages into three primary groups.

### Regional Data Boundaries

Regional data boundaries focus on requirements that data be stored within a specific region or group of countries. Organizations select the appropriate data boundary and configure permitted resource locations. Some regional packages also provide controls over support personnel or provider access.

Examples of regional requirements include EU Data Boundary, US Data Boundary, Canada Data Boundary, Japan Data Boundary, Australia Data Boundary, or packages for other regions supported by Google Cloud. Package names, regions, and service lists can evolve over time; consult the current list before designing.

A regional data boundary fits when the core requirement is restricting data location or operating within a geographic boundary. If the organization's regulations also require demonstrating sector-specific controls such as CJIS, FedRAMP, or ITAR, choose the exact regulatory data boundary instead of relying solely on a regional package.

### Regulatory Data Boundaries

Regulatory data boundaries group controls serving a specific regulation or compliance program. Examples include:

- **FedRAMP Moderate and FedRAMP High**: requirements for systems processing U.S. federal agency information at the corresponding impact level.
- **CJIS**: requirements protecting criminal justice information.
- **IL2, IL4, and IL5**: Impact Levels used in environments processing U.S. Department of Defense information.
- **ITAR**: requirements governing data and technology subject to International Traffic in Arms Regulations.
- **IRS Publication 1075**: requirements protecting federal tax information.
- **Healthcare and Life Sciences**: controls supporting healthcare sector requirements, including needs related to HIPAA and HITRUST within package scope.
- **Canada Controlled Goods Program (CGP)** and other region-specific data protection packages.

Do not assume all packages share the same location restrictions, personnel requirements, or key mechanisms. Two regulatory packages may enforce different control sets and product lists. Read the specific package description and cross-check it against the obligations your organization must satisfy.

### Sovereign Controls by Partners

Sovereign Controls by Partners allows using a supported local partner to operate or manage certain sovereignty control components. Depending on the package and partner, scope may include encryption key management, access justification, auditing, and regional data controls.

This category is useful when an organization requires a trusted local partner to participate in governing critical cloud environment components. Evaluate contracts, partner roles, resource permissions, support workflows, billing, and incident handling responsibilities. Not every partner or every package provides the exact same set of services.

### Choosing the Right Control Package

| Requirement | Package Category to Consider | Verification Questions |
|---|---|---|
| Data must stay within the EU or a specific country/region | Regional data boundary | Which data is covered? Which regions are permitted? Are regional support personnel requirements needed? |
| Must satisfy a program such as FedRAMP, CJIS, IL4, ITAR, or IRS 1075 | Regulatory data boundary | Does the package match the exact level/program? Which services and features are supported? |
| Need a local partner managing keys or sovereignty controls | Sovereign Controls by Partners | Which partners are supported? Who holds the keys? How do approval and audit workflows operate? |

A control package is a set of technical measures supporting a baseline. It does not replace legal review, independent audits, internal procedures, or evidence of how the organization actually uses the services.

## 3. Data Residency and Data Boundaries

### What Does Data Residency Mean?

Data residency describes where data is stored *at rest*. Google Cloud offers location options for services that support data location configuration. Assured Workloads uses location restrictions to help organizations govern where in-scope resources can be created or used.

During folder creation, the organization selects a control package and configures allowed resource locations per package requirements. The Resource Locations organization policy can restrict creating new resources outside the permitted locations. Some services or resource types fall outside the scope controllable by this constraint; always verify the supported resources list rather than assuming every resource is restricted automatically.

### Distinguishing Three Types of Location

In Assured Workloads design, distinguish among:

1. **Position in the resource hierarchy**: under which organization or parent folder the folder sits. This is a governance structure choice.
2. **Assured Workloads environment location**: the workload's location field in the Assured Workloads service, specified when creating the workload via Console or CLI. Select a location supported for the control package.
3. **Resource location**: the region or multi-region where actual Google Cloud resources are permitted to be created and used. The Resource Locations organization policy enforces this limit for supported resources.

These three concepts are related but not synonymous. For instance, placing a folder under an organizational governance folder does not mean data may reside in every region. Nor does the Assured Workloads environment location automatically define the list of allowed locations for every descendant resource.

### Data Scope and Metadata

Not every piece of information appearing in a project qualifies as Customer Data covered by data residency commitments. According to Google Cloud documentation, data location commitments apply to Customer Data at rest for services supporting location configuration; operational metadata or Service Data is governed by separate terms and documentation.

Common fields requiring particular caution include:

- Names and IDs of resources, projects, or folders.
- Resource descriptions, labels, tags, and configuration attributes.
- URIs, file paths, bucket names, or dataset names.
- User IDs, timestamps, log-based metrics, and configuration rule content.
- Firewall rule names, security scan configurations, or IAM policies.

Do not place sensitive data, personally identifiable information, or regulated content into these metadata fields unless there is confirmation that the field falls within the corresponding protection boundary. Classify data before designing resource names, labels, logs, and descriptions.

### Example of Location Restrictions

Suppose an organization chooses the EU Data Boundary package. The deployment team should:

1. Select an environment location and resource locations matching the EU list supported by the control package.
2. Create projects inside the Assured Workloads folder.
3. Create resources only in locations on the permitted list.
4. Verify whether specific services support the location and appear on the supported products list.
5. Check resources not covered by the Resource Locations constraint and address them via appropriate administrative or technical controls.

Location policies do not migrate existing data from one region to another. When onboarding a legacy project, teams must assess and migrate or recreate required resources following each service's procedures.

## 4. Supported Products and Control Package Limits

### Not Every GCP Service Is Supported in Every Package

Supported products lists are published per control package. A service supported in FedRAMP High might not be supported in CJIS or a regional data boundary. If a product does not appear on a package's list, do not assume it satisfies all regional, regulatory, or sovereignty controls of that package.

Some folders can enable the Resource Usage Restriction organization policy to limit permitted APIs/services. However, some API endpoints are shared between supported and unsupported products; having an endpoint enabled does not prove every product using that endpoint is within supported scope.

Before choosing a service for a workload, verify:

- Whether the product name and API service are listed for that exact control package.
- Whether the specific feature or SKU falls within supported scope.
- Whether the service's regions, multi-regions, and location options are compatible.
- Whether any features require separate activation or configuration after folder creation.
- Whether data is transmitted to a service, API, or project outside the folder.

### Applying to Compute, Containers, Storage, and Databases

| Service Group | What to Verify Before Deployment |
|---|---|
| Compute Engine | Region of VMs, disks, snapshots, and images; supported service types; data flows to external management systems. |
| Google Kubernetes Engine (GKE) | Region/zone of clusters and nodes; integrated services; image registries; whether logging, monitoring, and add-ons fall within supported scope. |
| Cloud Run | Service region, input/output data, secrets, logs, and dependent services. |
| Cloud Storage | Bucket location, storage class, replication, and CMEK if required by the control package. |
| BigQuery | Dataset location, API services, permitted features, and where query results are stored. |
| Databases | Instance/cluster location, backups, replicas, exports, cross-region connectivity, and supported encryption options. |

The table above is an architectural checklist, not confirmation that all services are supported in every package. The official supported products list per control package is the authoritative basis for decisions.

### When a Required Service Is Not Yet Supported

If a needed service is not supported:

1. Check whether a supported alternative meets business requirements.
2. Determine whether data can be processed in a separate workload outside the compliance boundary.
3. Evaluate integration across the two boundaries: which data crosses, which identities have access, and how transmission channels are secured.
4. If regulations permit exceptions, obtain formal approval from compliance/legal teams and relevant authorities when required.
5. Document justification, scope, owner, and compensating controls; never treat an exception as proof the service is certified.

## 5. Personnel Access and Google Governance Controls

Assured Workloads can enforce requirements on Google personnel allowed to access data when providing support. Depending on the control package, requirements may cover work location, citizenship or adjudication status, personnel verification, background checks, and support roles. For example, some FedRAMP High packages require frontline and tier-2 support personnel and subprocessors to meet U.S. location requirements and enhanced background checks.

### Access Transparency

Access Transparency provides logs of certain actions taken by Google personnel when accessing Customer Data to fulfill support obligations or resolve incidents. For example, logs may record Cloud Customer Care actions while handling a support case or investigating an outage.

Access Transparency delivers visibility and audit correlation. Security teams can ingest logs into a SIEM, correlate them with support cases, and review access justification, timestamps, actors, and affected resources. Logs only cover supported services and access types; consult the current supported list.

### Access Approval

Access Approval allows customers to review and approve requests by Google personnel to access Customer Data in supported scenarios. When access is needed, Google personnel submit a request with a business justification. Authorized administrators can approve or deny requests in the Console or via API. Approved requests are logged and can be correlated with Access Transparency logs.

Access Approval is an additional control layer on top of Google's privileged access mechanisms. Customer approval does not grant IAM permissions to Google employees; employees must still hold appropriate internal Google authorization before accessing anything. Assured Workloads personnel requirements are evaluated before Access Approval requests are considered. Verify that target services support Access Approval and understand access cases outside notification scope.

### Assured Support

Assured Support is an add-on support option for workloads with support personnel requirements. You can create and use an Assured Workloads folder without a support subscription. However, to receive support from personnel meeting the control package's requirements, the organization needs an active **Enhanced Support** or **Premium Support** subscription. The appropriate support tier routes cases to personnel meeting relevant criteria such as work location, personnel screening, and data access controls.

### Distinguishing the Three Mechanisms

| Mechanism | Role | Question Answered |
|---|---|---|
| Assured Workloads personnel controls | Restricts the pool of personnel eligible to support the workload per control package. | Who is eligible to be considered for access? |
| Access Transparency | Records selected Customer Data access actions by Google personnel. | When and in what context did Google personnel access data? |
| Access Approval | Requires prior approval for supported access types. | Does the organization consent to this access request? |

These three mechanisms complement one another; they are not three names for the same feature. Operational on-call procedures must also be aligned to respond promptly to approval requests, especially during active incidents.

## 6. Key Management and Encryption

Key requirements depend on the control package. Some packages support Google-owned and Google-managed encryption keys; others allow or require Customer-Managed Encryption Keys (CMEK), Cloud External Key Manager (Cloud EKM), or external key import. Do not assume every workload inside Assured Workloads mandates CMEK.

### CMEK and Separation of Duties

CMEK allows customers to control CryptoKeys in Cloud Key Management Service (Cloud KMS). Key usage permissions are granted specifically to the service agent of the service encrypting data. Key administration teams can be separated from application operations teams to reduce the risk of one identity both administering data and unilaterally altering or destroying keys.

In certain control packages, Google recommends or requires placing key management in a separate project from the workload project. For instance, Data Boundary for ITAR requires using CMEK and a dedicated key management project with key rings in compliant locations. This structure supports separation of duties and helps limit developer permissions.

### Creating a Folder Does Not Create Keys

During Assured Workloads folder creation, the UI may offer to create a CMEK management project and key ring. This step only provisions the project and key ring per the selected configuration. **Assured Workloads does not automatically create cryptographic keys**. Teams must create keys, choose appropriate algorithms and protection levels, grant IAM to service agents, and test integration before onboarding data.

### Cloud EKM and Key Access Justifications

If the control package and partner support Cloud EKM, primary key material can remain in an EKM system external to Google Cloud. Cloud KMS references the key and forwards cryptographic requests over the configured connection. This can satisfy external key control requirements while increasing dependency on partner endpoints, network connectivity, and partner availability.

Key Access Justifications (KAJ) adds context explaining the reason for an external key usage request. With a KAJ-compatible EKM, the partner can evaluate the justification to allow or deny operations by policy. KAJ does not replace IAM, Access Approval, or audit logs; distinguish Google personnel data access requests from external key usage requests.

## 7. IAM, Billing, and Deployment Prerequisites

### Permission Prerequisites

To create an Assured Workloads folder, the operator needs appropriate minimum permissions on the organization and billing account. Roles listed in Google Cloud documentation include:

- **Assured Workloads Administrator** (`roles/assuredworkloads.admin`): creates and manages Assured Workloads folders.
- **Resource Manager Organization Viewer** (`roles/resourcemanager.organizationViewer`): views resources within the organization.
- **Appropriate Cloud Billing permissions**: links or uses a billing account for the workload per the creation workflow.

The organization must have a valid, active billing account. To assign these roles, administrators need appropriate IAM permissions at the organization level. In day-to-day operations, use narrower roles such as Assured Workloads Reader or Editor for users who only need to view or update workloads; do not grant broad Admin roles to the entire development team.

Other tasks may require specific permissions:

| Task | Roles/Permissions to Consider |
|---|---|
| View workloads and status | `roles/assuredworkloads.reader` or equivalent role. |
| Create/delete workload folders | `roles/assuredworkloads.admin` and required organization/billing permissions. |
| Modify control package or update workload | `assuredworkloads.workload.update`, typically included in Assured Workloads Editor/Admin. |
| View violations | `assuredworkloads.violations.get` and `assuredworkloads.violations.list`. |
| Edit organization policies | Organization Policy Administrator role (`roles/orgpolicy.policyAdmin`) or equivalent permissions. |
| Manage folder IAM | Appropriate Resource Manager permissions on the resource hierarchy. |

Verify IAM roles documentation for exact actions; a data-reading role does not inherently grant permission to edit organization policies or record exceptions.

### Billing and Costs

Assured Workloads requires a valid billing account. Certain control packages, support options, or partner-provided services may carry separate terms and costs. Before deploying, determine:

- Which billing account bears the workload's charges.
- Whether Enhanced Support or Premium Support is needed to meet support personnel requirements.
- Whether any partner services require a separate partner services billing account.
- Pricing, quotas, and regional limitations for the selected Google Cloud services.

Do not estimate costs solely from folder creation. Budget for compute, storage, networking, logging, KMS, support, and partner services based on real traffic.

## 8. Creating and Using an Assured Workloads Folder

### Preparation Workflow

Before creating the folder, architecture and compliance teams should align on:

1. Data types processed and applicable regulations.
2. Control package matching regional, regulatory, and personnel requirements.
3. Assured Workloads environment location and permitted resource locations list.
4. Whether products, APIs, and features needed by the workload appear in supported products.
5. Which projects need to be created fresh, and which existing projects can be onboarded after assessment.
6. How keys, logging, Access Transparency, Access Approval, and support will be managed.
7. Operational owner team, exception approvers, and incident response workflows.

The folder can be created under the organization or an appropriate parent folder. Placement in the resource hierarchy should not be arbitrary because folder structure shapes inherited IAM permissions and policies. The organization chosen during folder creation cannot be changed afterward; confirm the right organization and parent folder before proceeding.

### Creating a Folder via the Google Cloud Console

General flow in the Google Cloud Console:

1. Open the **Assured Workloads** page in the Google Cloud Console and select the target organization.
2. Click **Create** to start creating a folder.
3. Enter a folder name containing no sensitive data or PII; an `aw-` prefix can help identification.
4. Select the organization and folder position in the resource hierarchy.
5. Choose the control package category, then pick the specific package such as Data Boundary for FedRAMP High, EU Data Boundary, or another suitable package.
6. Select permitted resource locations aligned with workload and control package requirements.
7. Review descriptions of controls, supported products, and additional requirements.
8. If needed, configure the CMEK management project and key ring; remember this step does not create cryptographic keys.
9. Review configuration and billing, and confirm folder creation.

After the folder is created, create projects underneath or move assessed existing projects into it. Do not move production workloads into the folder solely because folder creation succeeded; verify policies, services, IAM, and resource locations first.

### Example Creating a Workload with gcloud CLI (API v1)

The example below creates an Assured Workloads environment using the v1 control package model. Replace placeholders with your actual organization ID and billing account. `us-central1` is only an illustrative location for a U.S. workload; choose a valid location per the control package and organizational data requirements.

```bash
# Select the administrative project used to call the Assured Workloads API.
gcloud config set project ADMIN_PROJECT_ID

# Enable the API in the selected administrative project only if not already enabled.
gcloud services enable assuredworkloads.googleapis.com

gcloud assured workloads create aw-fedramp-high-prod \
  --organization=ORGANIZATION_ID \
  --location=us-central1 \
  --display-name="FedRAMP High - production" \
  --compliance-regime=data-boundary-for-fedramp-high \
  --billing-account=billingAccounts/BILLING_ACCOUNT_ID \
  --version=v1
```

In this example:

- `ORGANIZATION_ID` is the parent organization ID.
- `--location` is the Assured Workloads environment location and must be on the supported locations list.
- `--compliance-regime` selects the control package; the value must be a valid regime supported by the current CLI.
- `BILLING_ACCOUNT_ID` is an active billing account ID.
- `--version=v1` specifies the v1 API model using control packages for Assured Workloads folders.

The workload creation command does not replace selecting appropriate resource locations, checking supported products, or configuring application IAM. For packages requiring dedicated options, follow the folder creation guide for that specific package.

You can list v1 workloads in the chosen organization and location:

```bash
gcloud assured workloads list \
  --organization=ORGANIZATION_ID \
  --location=us-central1 \
  --version=v1
```

### Onboarding Existing Projects

An active project can be moved into an Assured Workloads folder after assessment. The process should include:

1. Inventorying resources, services, APIs, locations, backups, snapshots, replicas, and outbound connections.
2. Comparing every service against the control package's supported products.
3. Verifying all resources reside in compatible locations; planning data migrations if needed.
4. Reviewing IAM, service accounts, service agents, KMS permissions, logs, and metadata.
5. Evaluating the impact of Resource Usage Restriction and organization policies on current deployments.
6. Testing in a staging environment or representative project before migrating production.
7. Moving the project per Resource Manager guidance and monitoring any resulting violations.

Moving a project into a folder does not automatically relocate data across regions, replace unsupported services, or create CMEK keys. A project may require architectural changes before meeting a control package.

## 9. Monitoring and Handling Violations

Assured Workloads monitors workload configurations by comparing control package requirements against organization policies and live resources.

### Two Primary Violation Categories

**Organization policy violations** appear when an organization policy configuration is changed in a way that conflicts with the folder's requirements. For example, an administrator modifies a location policy or service restriction policy, weakening enforced controls.

**Resource violations** appear when a resource breaches enforced limits. For instance, a resource is created in an unpermitted location or uses a resource type failing service restrictions. Monitoring scope depends on supported constraints and resource types. Verify whether resource violation monitoring is enabled for the folder; monitoring policy violations and resource violations have distinct configurations and prerequisites.

### Violation States

| State | Meaning | Action |
|---|---|---|
| `UNRESOLVED` | Violation has not been resolved or a configuration change introduced a new violation after a prior exception. | Investigate cause, identify owner, and plan remediation. |
| `RESOLVED` | Violation was resolved by restoring a compliant configuration. | Preserve evidence and verify no recurrence. |
| `EXCEPTION` | Violation has a documented exception with business justification under authorized permissions. | Track scope, approver, and review deadline/criteria per internal workflow. |

An exception does not mean the resource has become compliant. It is a risk governance decision requiring justification, approval, and compensating controls where needed. If configuration continues to change after an exception, the violation may reappear and require re-evaluation.

### Viewing Violations with gcloud

Example listing violations for a workload:

```bash
gcloud assured workloads violations list \
  --location=us-central1 \
  --organization=ORGANIZATION_ID \
  --workload=WORKLOAD_ID
```

Output can include violation ID, violation type, description, first detection timestamp, affected policy constraint, current state, and links to audit logs. Use this information to locate who changed the configuration, affected resources, and remediation guidance.

In the Console, operations teams can view the overview on the Assured Workloads page and open Monitoring to filter by folder, state, violation type, constraint, or resource type. Email notifications can be enabled for organization policy violations or when exceptions are added so responsible teams react promptly.

### Remediation Workflow

1. Open violation details and identify the affected folder, project, resource, or organization policy.
2. Check audit logs to locate the change that caused the violation and the acting identity.
3. Determine root cause: misconfiguration, out-of-band change, new service, unmigrated legacy resource, or misunderstood limit.
4. Select appropriate remediation, such as restoring policy, migrating or recreating resources in a valid location, replacing a service with a supported product, or fixing IAM.
5. If an exception is needed, obtain authorization from an approved authority and document scope, justification, and compensating controls.
6. Verify the state transitions to `RESOLVED` or `EXCEPTION` as expected; preserve evidence and update runbooks.

Do not simply silence alerts to clean up dashboards. The goal is addressing root causes and maintaining an auditable control posture.

## 10. Updating Control Packages and Maintaining Configurations

Control packages may be updated when Google Cloud adds supported products, modifies policies, or enhances controls. Assured Workloads provides workload updates to compare current folder configuration against the latest available version.

The update workflow should include:

1. Open Assured Workloads folder details and check whether updates are available.
2. Read the changelog: organization policies, allowed services, locations, key management, or personnel requirements.
3. Assess impact on existing projects, deployment pipelines, APIs, resources, and integrations.
4. Test the update in a representative environment if organizational processes permit.
5. Approve the change through change management workflows.
6. Apply the update, re-verify the workload, and monitor for post-update violations.
7. Record control package version, update date, approver, and verification results.

Do not postpone updates indefinitely, as the folder may miss new controls or current service lists. At the same time, never apply updates in production without assessing impact on running workloads.

### Assured Workloads Frameworks

Google Cloud also offers **Assured Workloads frameworks** to define and evaluate cloud controls at the folder or project level. Current documentation marks frameworks as Preview and requires access eligibility/allowlisting. Frameworks use concepts such as cloud controls, rules, and enforcement modes like Preventive, Detective, and Audit, and can support dashboards and assessment reports.

Frameworks represent a separate extension path from v1 Assured Workloads folder control packages. In real deployments, check release status, access prerequisites, and current version documentation; do not assume a Preview feature is production-ready or carries the same assurances as GA packages.

## 11. Shared Responsibility and Limits to Understand Clearly

### Google Cloud Responsibilities

Google Cloud provides the underlying infrastructure, services, and defined control packages; operates components within service scope; maintains location, personnel, and access restriction mechanisms per package; and provides supporting visibility such as Access Transparency, violation monitoring, and supported products documentation.

### Customer Responsibilities

Customers remain responsible for:

- Choosing the right control package and locations for legal/business requirements.
- Using only supported services, features, and locations within the compliance scope.
- Designing secure IAM, service accounts, VPCs, firewalls, workload identities, and governance processes.
- Classifying data and avoiding placing sensitive data into metadata or out-of-scope services.
- Configuring CMEK/Cloud EKM if required, managing key lifecycles, and preserving data recoverability.
- Enabling, retaining, and analyzing audit logs; monitoring violations and governing exceptions.
- Managing subprocessors, external endpoints, release pipelines, users, and client devices.
- Gathering evidence and conducting compliance assessments as required by regulators or auditors.

### Commonly Misunderstood Limits

1. **Having an Assured Workloads folder does not mean an application is automatically compliant.** Architecture and operations must be verified both inside and outside the folder.
2. **Data residency does not cover all metadata.** Resource names, IDs, labels, descriptions, and Service Data fall under separate scope terms.
3. **Not every resource is governed by the Resource Locations constraint.** Always check the supported resources list.
4. **Not every GCP service is supported in every package.** Rely on the exact supported products list for the package.
5. **Access Transparency is not Access Approval.** One logs access; the other requires prior approval for supported access events.
6. **Folder setup does not pre-create cryptographic keys.** A CMEK project/key ring may be provisioned, while keys themselves must be created and configured separately.
7. **Support subscriptions have separate requirements.** Receiving support from personnel meeting control package criteria requires an active Enhanced Support or Premium Support subscription.
8. **Exceptions do not eliminate risk.** They require justification, authority, compensating controls, and periodic review.

## 12. Deployment Scenarios

### Scenario A: Healthcare System Protecting Data Within the United States

A healthcare provider deploys a patient records application on Cloud Run, stores files in Cloud Storage, and analyzes data in BigQuery. Compliance requires a U.S. data boundary along with controls appropriate for Healthcare and Life Sciences.

The architecture team must select the Healthcare and Life Sciences control package, confirm the specific services and features are supported, choose valid resource locations, configure CMEK if required by internal policy, and grant KMS permissions to service agents. The team also evaluates Assured Support if support personnel must meet package criteria, enables Access Transparency, and establishes an Access Approval workflow for supported services.

During deployment, the project team verifies locations for the Cloud Run service, buckets, datasets, backups, and logs, while avoiding putting patient details into resource names or labels. After go-live, the team monitors violations and periodically reviews supported products.

### Scenario B: Agency Workload Requiring Data Boundary for FedRAMP High

A team deploys a workload processing data within FedRAMP High scope. The team selects Data Boundary for FedRAMP High and U.S. resource locations from the supported list. Projects running Compute Engine and storage services are created only when products, APIs, locations, and features appear on the permitted list.

The control package enforces location and support personnel restrictions within package scope. Security separates the folder admin group, key admin group, and application operations group. If personnel-compliant support is required, the organization subscribes to Enhanced Support or Premium Support. Organization policy and resource changes are monitored to detect configuration drift.

### Scenario C: Organization Requiring Local Partner Participation for Sovereignty Controls

An organization in a country mandates local partner key management and auditing. The team evaluates Sovereign Controls by Partners options supported in that region, selects a partner, and reviews contracts, roles, billing, data scope, key management rights, access justifications, and incident procedures.

The team deploys workloads in a folder under the partner's control package, creates supported projects and resources, and configures connections to required key management and audit services. Before production, the team rehearses scenarios where the partner is unavailable, denies an access request, or needs to restore key access permissions.

## 13. Pre-Production Workload Checklist

- [ ] Identified data, regulatory obligations, and the matching control package.
- [ ] Verified Assured Workloads environment location and permitted resource locations.
- [ ] Verified supported products, APIs, features, and resource types for the exact package.
- [ ] Selected appropriate parent folder and organization/project structure.
- [ ] Verified IAM for Assured Workloads Admin, Organization Viewer, billing, and operational teams.
- [ ] Assessed existing projects before onboarding; no unresolved resources/locations remain.
- [ ] Configured service accounts, IAM, VPC, firewalls, and dependent services.
- [ ] Determined requirements for Google-managed keys, CMEK, Cloud EKM, or key import.
- [ ] Created and tested keys if needed; did not confuse a key ring with a cryptographic key.
- [ ] Evaluated Access Transparency, Access Approval, and Assured Support per package.
- [ ] Enabled and tested policy/resource violation monitoring.
- [ ] Defined remediation, exception, escalation, and evidence retention workflows.
- [ ] Scheduled periodic reviews of supported products and workload updates.
- [ ] Checked billing, support subscriptions, partner services, and operational budgets.

## 14. Conclusion

Assured Workloads helps organizations establish a controlled boundary for sensitive workloads using control packages defined by region, regulation, or data sovereignty. Folders and associated policies form the foundation for restricting locations, services, support personnel, and certain key management requirements. Monitoring violations and applying control package updates help operations teams know when configurations drift or control baselines evolve.

For successful adoption, combine Assured Workloads with thoughtful organization/folder/project design, IAM, VPC, supported services, key management, logging, and change management workflows. Verify every service and data type against control package scope, rehearse violation remediation, and retain operational evidence. That is how compliance requirements become verifiable technical controls maintained throughout the workload lifecycle.

## References

- [Overview of Assured Workloads](https://docs.cloud.google.com/assured-workloads/docs/overview)
- [Control packages](https://docs.cloud.google.com/assured-workloads/docs/control-packages)
- [Create an Assured Workloads folder](https://docs.cloud.google.com/assured-workloads/docs/create-folder)
- [Supported products by control package](https://docs.cloud.google.com/assured-workloads/docs/supported-products)
- [Assured Workloads locations](https://docs.cloud.google.com/assured-workloads/docs/locations)
- [Data residency](https://docs.cloud.google.com/assured-workloads/docs/data-residency)
- [Shared responsibility in Assured Workloads](https://docs.cloud.google.com/assured-workloads/docs/shared-responsibility)
- [IAM roles](https://docs.cloud.google.com/assured-workloads/docs/iam-roles)
- [Monitor an Assured Workloads folder for violations](https://docs.cloud.google.com/assured-workloads/docs/monitor-folder)
- [Apply workload updates](https://docs.cloud.google.com/assured-workloads/docs/apply-updates)
- [Getting support](https://docs.cloud.google.com/assured-workloads/docs/getting-support)
- [Access Transparency overview](https://docs.cloud.google.com/assured-workloads/access-transparency/docs/overview)
- [Access Approval overview](https://docs.cloud.google.com/assured-workloads/access-approval/docs/overview)
- [gcloud assured workloads create](https://docs.cloud.google.com/sdk/gcloud/reference/assured/workloads/create)
- [Assured Workloads frameworks overview (Preview)](https://docs.cloud.google.com/assured-workloads/docs/frameworks-overview)
