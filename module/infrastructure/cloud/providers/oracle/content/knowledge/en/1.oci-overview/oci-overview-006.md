# Shared Responsibility Model for Security on OCI

## 1. Objectives and Context

Moving applications to Oracle Cloud Infrastructure (OCI) changes how security tasks are divided. Oracle operates the infrastructure delivering the services; the organization using the services still must protect identities, data, application code, and configurations under its control.

For example, Oracle may operate Object Storage as designed, yet a bucket configured as public by the customer can still expose data. Similarly, a virtual machine running on protected infrastructure does not guarantee the Java application inside has been patched or checks authorization properly.

This lesson belongs to the **Oracle Cloud Infrastructure Overview** chapter of the **CLOUD_PROVIDERS_ORACLE** module. The content helps learners connect tenancy, compartments, IAM, VCN, Compute, storage, and Oracle database services to responsibilities for deployment, monitoring, automation, cost control, and maintaining availability.

After this lesson, you can:

- Distinguish security of cloud infrastructure from security of workloads using the cloud.
- Identify Oracle's share and the customer's share across each service type.
- Spot gaps when configuring IAM, networking, data, software patching, and logging.
- Turn a security requirement into an assigned task with verification evidence.
- Apply the model to a Java system using Compute, Object Storage, and Autonomous Database.

## 2. Principles of the Shared Responsibility Model

Oracle describes security on OCI as a shared responsibility: Oracle protects the infrastructure and service operations, while customers must configure resources securely and protect their workloads. [Oracle: Shared Security Model](https://docs.oracle.com/en-us/iaas/Content/cloud-adoption-framework/security.htm)

The model can be viewed across two scopes:

| Scope | Primary Question | Example |
| --- | --- | --- |
| Security **of** the cloud | How are cloud services built and operated securely? | Protecting data centers, hardware, and network infrastructure operated by Oracle |
| Security **in** the cloud | How does the organization use the services securely? | Restricting IAM policies, protecting secrets, configuring networking, and securing app code |

This is not an even 50/50 split. The more managed a service is, the less the customer directly operates the underlying layers, yet the customer still must decide who has access, which data is uploaded, and which configuration meets workload requirements.

~~~mermaid
flowchart TB
    O["Oracle: infrastructure and service portions operated by Oracle"]
    C["Customer: identities, data, applications, and assigned configurations"]
    O --> B["Touchpoints: APIs, configuration, permissions, logs, and notifications"]
    C --> B
    B --> W["Workload to be protected and verified"]
~~~

A single control often involves multiple tasks. For access management, Oracle provides IAM mechanisms; the customer designs groups, policies, provisioning workflows, and revocation. For encryption, the service performs encryption according to its mechanism; the customer still must choose key management, decryption permissions, and appropriate data sharing scope.

Therefore, when noting “both parties share responsibility”, break it down into concrete tasks. If no one owns reviewing permissions or handling alerts, that is an operational gap even when security tools exist.

### 2.1. Three Questions to Identify Boundaries

For each component, answer:

1. **Who operates this layer?** For example, Oracle operates physical servers; the customer operates the OS inside a standard Compute virtual machine.
2. **Who decides the configuration?** For example, the customer decides which networks are allowed to reach service ports.
3. **Who must verify the outcome?** For example, the operations team must confirm alerts reach the right people and backups can be restored.

Do not generalize responsibilities from the vendor name. A self-installed Oracle database on Compute and an Autonomous Database both use Oracle technology, yet have different operational boundaries.

## 3. Responsibility Table by Layer

The following table provides guidance for common workloads on OCI public cloud. When deploying, cross-check the exact service and operational model in use; do not apply the table verbatim to every Cloud@Customer variant or specialized service.

| Layer or Control | What Oracle Operates/Provides | What the Customer Must Organize and Execute |
| --- | --- | --- |
| OCI data centers and hardware | Protects and operates service infrastructure | Choose architecture and deployment locations fitting workload requirements |
| Cloud network infrastructure | Underlying network and service isolation mechanisms | Design VCN, subnets, routes, and access rules |
| IAM | Identity, authentication, and authorization platform | Protect credentials, grant least privilege, review and revoke permissions |
| Standard Compute VM | Infrastructure running virtual machines | Protect guest OS, host accounts, runtime, and application |
| Object Storage | Operates the storage service | Set bucket/object permissions, control sharing, and manage data lifecycle |
| Self-installed software | Underlying infrastructure or service per product | Choose versions, configure, patch, and monitor self-managed software |
| Data and business logic | Service data protection capabilities | Classify data, restrict access, and define permitted usage |
| Logging and detection | Recording, monitoring, or detection mechanisms provided by the service | Select log sources, configure scope, handle alerts, and retain evidence |
| System recovery | Backup and recovery capabilities per service | Choose recovery targets, configure, and test workload recovery |
| OCI access devices | Service interfaces and APIs | Protect laptops, browsers, CI/CD runners, and admin tools |

Oracle distinguishes responsibility for protecting infrastructure from responsibility for protecting operating systems, applications, and customer-configured resources; the customer-managed scope increases further when using bare metal and operating the entire software stack yourself. [Oracle: Security Overview](https://docs.oracle.com/en-us/iaas/Content/Security/Concepts/security_overview.htm)

The key when using this table is finding **unassigned tasks**, not just checking the “Oracle” or “customer” column. A private bucket today can be altered tomorrow; a policy accurate at deployment may no longer fit after an employee changes roles.

## 4. Boundaries Shift by Service

### 4.1. Compute VMs and Bare Metal

With standard Compute virtual machines, the operations team must manage the OS inside the VM, login accounts, SSH configuration, application software, and update processes. Oracle provides the infrastructure; keeping customer-run software patched is work the customer must perform. [Oracle: Securing Compute](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/compute_security.htm)

Example with Java on a VM:

- The platform team updates the operating system and restricts server admin privileges.
- The application team updates the JDK, libraries, and business code per internal assignment.
- Both teams coordinate to test releases and rollback paths to a safe version.

Creating a new patched image does not automatically replace VMs already running from the old image. You need a plan for in-place updates or instance replacement and verification of the outcome.

With bare metal, there is by default no Oracle-managed hypervisor operating on the customer's behalf. Software installed by the customer, including a virtualization layer if self-deployed, must have clear ownership.

### 4.2. Self-Installed Database on Compute

If you install Oracle Database yourself on Compute, you cannot treat it as an Autonomous Database merely because it runs on OCI. The team using it must manage the self-installed software layer, patches, configuration, accounts, backups, and recovery according to the chosen architecture.

This option offers high control while increasing operational tasks. Include staffing, maintenance windows, and incident-response capability when evaluating total cost.

### 4.3. Base Database Service

Base Database Service provides management capabilities and service tooling, yet does not mean Oracle automatically performs every tenant database administration task. The service's security responsibility documentation distinguishes Oracle maintaining infrastructure and releasing patches from customer administrators applying and testing patches on tenant instances. [Oracle: Security Guide for Base Database Service](https://docs.oracle.com/en/cloud/paas/base-database/guide/security-guide.html)

Before operating, clearly define who:

- Monitors and approves OS and database software patches within the customer-managed scope.
- Schedules, executes, or coordinates update tooling.
- Tests application connectivity and functionality after updates.
- Manages users, data privileges, and recovery procedures.

“Having automation tools” and “Oracle being responsible for completing that task for your workload” are two different things.

### 4.4. Autonomous Database

With Autonomous Database, Oracle takes on many administrative tasks, including patching and upgrading Autonomous Database resources. The customer remains responsible for application security, resource and data access permissions, network connectivity, as well as monitoring application health and performance. Some tasks require the customer to request or configure execution. [Oracle: Autonomous Database Responsibility Model](https://docs.oracle.com/en/cloud/paas/autonomous-database/shared-responsibility-model.html)

Thus, choosing this service can reduce self-management of the database platform, yet does not fix SQL injection bugs, queries returning data to the wrong user, or leaked application passwords.

### 4.5. Other Managed Services

Apply the same analysis to services such as Load Balancing, API Gateway, or Functions: separate the service portion Oracle operates from the code, routes, backends, permissions, and settings controlled by the customer.

Do not use labels like IaaS or PaaS as a complete task checklist. The exact service name, deployment variant, and actual configuration determine who must do each task.

## 5. IAM: Oracle Provides the Mechanism, the Customer Decides Permissions

Within a tenancy, an overly broad policy can allow modifying networks, reading data, or creating billable resources. Therefore, protecting IAM is cross-cutting work across every service.

Tasks the customer must assign clearly:

1. Use personal accounts and appropriate workload identities instead of shared accounts.
2. Protect logins with appropriate authentication methods and MFA.
3. Scope permissions by job role, environment, and resource boundary.
4. Review memberships, administrative roles, and automation permissions.
5. Revoke permissions, sessions, and credentials via a defined process when no longer needed.
6. Protect CI/CD machines, admin laptops, and places where access configs are stored.

Compartments help organize resources and serve as an authorization scope. Placing resources in a separate compartment only provides protection when related policies are designed properly; a compartment name does not create a permission barrier by itself.

### 5.1. Separating Three Control Paths

| Access Path | Example | Verification Question |
| --- | --- | --- |
| OCI resource administration | Modify VCN, change bucket config, manage instances | Who does IAM allow to perform which operations? |
| Using services and data | Read objects or connect to a database | Do service and endpoint permission mechanisms restrict access properly? |
| Application business logic | User views orders or downloads invoices | Did the application verify the user has rights to that specific record? |

Someone with restricted OCI admin permissions may still access data through a path shared by the application. Conversely, an application account with limited business roles does not guarantee the underlying infrastructure credentials are also least-privileged.

Therefore, inspect the entire request path rather than looking at a single policy screen.

## 6. Networking: Secure Infrastructure Still Requires Proper Configuration

Oracle provides networking components and control mechanisms; the customer chooses how to connect them. VCNs, subnets, routes, gateways, Network Security Groups (NSGs), and security lists must accurately reflect business flows. [Oracle: Securing Networking: VCN, Load Balancers, and DNS](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/networking_security.htm)

For a typical web service, you might design:

- Clearly defined entry points for external traffic.
- Application backends without public IPs if the architecture does not require them.
- Databases accepting only approved application and administrative connections.
- Administrative paths separated from end-user paths.
- Outbound traffic reviewed for purpose and scope.

This is an architectural suggestion, not a default configuration Oracle deploys automatically for every application.

### 6.1. Network Rules and Data Privileges Solve Different Problems

An NSG allowing connections to a database port only defines which network path traffic can traverse. It does not ensure the database account only reads the exact tables needed.

Similarly, a private subnet does not fix authorization bugs in the application. If the application connects to the database with an overly privileged account, an application bug can still impact data even though the database is not exposed on the public Internet.

When implementing network rules, inspect every relevant layer: routes, gateways, NSGs, security lists, host firewalls, and service listening configurations. Do not conclude access is blocked just because you edited one rule in one layer.

### 6.2. Private Paths and Encryption

Connecting over a private network and protecting data with TLS serve different goals. A private network helps control routing paths; TLS protects connections through protocol-level authentication and encryption.

For Java applications, you still must configure trust stores, validate certificates, and manage certificate expiration properly. Do not disable certificate verification as a “quick fix” for connection errors and treat that connection as safe simply because it sits inside a VCN.

## 7. Data, Encryption, and Secrets

### 7.1. Encryption Does Not Replace Authorization

Object Storage encrypts objects server-side; encryption keys can be Oracle-managed or use Vault keys depending on configuration. This encryption protects stored data under the service's mechanism, not replace deciding who may read data via the API. [Oracle: Object Storage Data Encryption](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/encryption.htm)

If a read request is validly authorized by the system, the service can decrypt and return the data. Thus, an encrypted bucket can still leak data when shared improperly.

The customer must define:

- Data types and sensitivity levels.
- Who can read, write, delete, or share.
- Where data is stored and how long it must be retained.
- How backups, exports, and test-environment data are protected.
- Plans for detecting and responding to anomalous access.

### 7.2. Private Buckets and Shared Links

Even a bucket configured as non-public still needs inspection for other sharing paths, such as pre-authenticated requests (PARs). A PAR allows access via a generated URL with a corresponding scope and expiration; therefore, manage that URL as an authorization credential, avoiding putting it in public logs or uncontrolled documents. [Oracle: Securing Object Storage](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/objectstorage_security.htm)

When reviewing a bucket, inspect policies, public access settings, PARs, application accounts, and other integration mechanisms in use. Looking only at a “private” badge is not enough to conclude all data is restricted as intended.

### 7.3. Encryption Keys and Application Secrets

Encryption keys and secrets serve different purposes. A database password or access token does not become safe merely because data on disk is encrypted.

Operational procedures should specify:

- Who can create, use, rotate, and revoke keys or secrets.
- How and with which identity the application retrieves secrets.
- When rotating a secret, how dependent components are updated and verified.
- If a key becomes unavailable, which workloads are affected.
- How to prevent secrets from appearing in source code, images, logs, or pipeline output.

For customer-managed keys, assess impact before disabling or deleting them. An action intended to increase security can cut off data access if dependent services are not considered.

## 8. Software Updates and Supply Chain

The shared responsibility model must reach down to every running software package. A cloud service updating its platform does not automatically update every library brought in by the application team.

For example, for a Java application on a VM, the inventory needing owners might include:

| Component | Suggested Internal Owner | Required Evidence |
| --- | --- | --- |
| Guest OS | Platform team | Running version and update results |
| JDK/runtime | Platform team or app team per agreement | Actual version in the deployed environment |
| Java libraries | Development team | Dependency inventory, review results, and patched releases |
| Self-installed web server or reverse proxy | Team assigned to operate that component | Configuration and update schedule |
| Image or deployment package | CI/CD team | Build source, version, and release provenance |
| Business code | Application team | Authentication, authorization, and input validation checks |

This table is an example of organizational assignment. Oracle does not know which internal team owns the JDK; the customer must resolve that.

Vulnerability remediation processes must connect all steps: identifying affected components, assessing exploitability, choosing a fix, testing, deploying, and verifying the running version. Closing an alert after editing a config file while the instance has not yet been replaced can leave the risk active.

Automation should make this workflow repeatable. It still requires people managing pipeline permissions, artifact sources, exceptions, and failed deployment scenarios.

## 9. Logging, Detection, and Response

### 9.1. Having Logs Differs From Having Detection Capability

OCI Audit automatically records calls to supported public APIs. That does not mean Audit contains every OS action, every SQL query, or every time an application returns data. Additional service, database, OS, and application logs must be selected based on what needs observation. [Oracle: Overview of Audit](https://docs.oracle.com/en-us/iaas/Content/Audit/Concepts/auditoverview.htm)

For instance, investigating an unauthorized invoice download might require correlating:

- Resource configuration and permission changes.
- Data access logs of the relevant service.
- Application authentication and authorization logs.
- Timestamps, user identifiers, and request IDs to link events.

Do not write passwords, tokens, or unnecessary sensitive data content into logs. Log stores also need access controls, protection against unauthorized modification/deletion, and retention management.

### 9.2. Detection Tools Still Need Scope and Responders

Cloud Guard uses targets and detectors to define scope and issues to detect. Responders provide remediation actions according to configured mechanisms and permissions. The customer must define which resources are inspected, who handles findings, and when automated remediation is allowed. [Oracle: Getting Started with Cloud Guard](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/part-start.htm), [Oracle: About OCI Responder Recipes](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/respond-recipes-about.htm)

Do not treat “Cloud Guard is enabled” as proof that every misconfiguration will fix itself. An automated action can also affect applications, so its permissions, scope, and rollback path must be verified.

### 9.3. Evidence for a Control

A control such as “the invoice bucket must not be public” should have:

1. Desired rule and applicable resource scope.
2. Team responsible for keeping configuration compliant.
3. Output from reading current configuration and testing relevant access paths.
4. Mechanism to detect unexpected changes.
5. Alert recipients and handling SLAs by risk level.
6. Remediation procedure along with re-verification evidence.

This turns a security slogan into auditable operational work.

## 10. Resiliency, Cost, and Compliance

### 10.1. Resilient Infrastructure Does Not Replace Recovery Design

Oracle provides infrastructure and capabilities supporting availability. Customers still must define business continuity targets, design workloads, and test appropriate HA/DR plans. Do not assume OCI automatically replicates and fails over an entire application to another region. [Oracle: Shared Responsibility Model for Resiliency](https://docs.oracle.com/en-us/iaas/Content/cloud-adoption-framework/oci-shared-responsibility.htm)

Two targets to clarify:

- **RPO:** acceptable data loss, typically expressed as a time interval.
- **RTO:** target time to restore service after an outage.

For example, an application needing to return within 30 minutes and tolerating at most 5 minutes of data loss needs a plan meeting both targets. Having a backup does not by itself prove that requirement is met.

Backups, replication, and high availability address different scenarios. A bad data change can be replicated to a replica; therefore, test both point-in-time recovery and the ability to bring the application back into operation.

### 10.2. Security Relates to Cost Control

Exposed credentials or overly broad resource-creation permissions can lead to unplanned usage. Organizations must combine IAM, appropriate quotas, anomaly detection, and resource management.

OCI Budgets provides soft spending thresholds and alerts; do not treat a budget as an automatic kill switch stopping all charges when a threshold is hit. [Oracle: Budgets](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/budgetsoverview.htm)

The responsible team must know who receives notifications, who inspects anomalous resources, and who has authority to isolate or stop cost-generating activity. Decisions to stop workloads must weigh business impact rather than relying on a single isolated alert.

### 10.3. Provider Evidence and Workload Evidence

Service documentation or certifications help evaluate the infrastructure and processes provided by Oracle. The organization still must demonstrate that its own workload configuration and operation meet defined requirements.

For example, data center control evidence does not replace invoice access-review history. Customer responsibilities include data classification, control selection, evidence retention, and reviewing actual usage per organizational requirements.

## 11. Example: Java Application on OCI

Suppose a development team builds an order-management application comprising:

- Load Balancer receiving HTTPS.
- Java application running on a Compute VM in an application subnet.
- Autonomous Database storing orders.
- Object Storage storing invoice files.
- Log sources and alarms for operations.

~~~mermaid
flowchart LR
    U["Users"] --> L["HTTPS Load Balancer"]
    L --> J["Java on Compute VM"]
    J --> D["Autonomous Database"]
    J --> O["Object Storage"]
    J --> M["Application and OS logs"]
    L --> M
    D --> M
    O --> M
    M --> T["Operations team receives and handles"]
~~~

This diagram is a conceptual architecture. Arrows to logs represent observability needs, not a claim that all log types are automatically enabled and routed to one place.

### 11.1. Concrete Responsibility Assignment

| Requirement | What Oracle Provides/Operates | What the Organization Must Complete |
| --- | --- | --- |
| VM runs on protected infrastructure | Compute infrastructure per service | Patch guest OS, manage accounts, and restrict admin paths |
| Database operated under Autonomous model | Platform administration portion of the service | Manage data privileges, connectivity, and application config |
| Only the customer owning the order can download the invoice | Storage and access mechanisms of the service | Verify business permissions before returning files or issuing download links |
| Connection secrets are not leaked | Key/secret management mechanisms when selected | Scope usage permissions, integrate into app, and avoid logging secrets |
| Anomalous access is detected | Log sources and corresponding detection tools | Enable required sources, build alerts, and assign on-call responders |
| System can recover | Backup and recovery features per product | Select targets, coordinate components, and run recovery drills |

In this example, a bug in invoice-download authorization lies in the application even though the file is stored in an encrypted service. Choosing Autonomous Database also does not remove responsibility for patching the JDK on the application VM.

### 11.2. One Request Path Requires Multiple Controls

When a user downloads an invoice, questions that must be resolved include:

1. Has the user been authenticated by the application?
2. Does the invoice belong to an order that user is allowed to view?
3. Is the workload identity restricted to reading only the necessary storage scope?
4. If generating a download link, are scope and expiration appropriate?
5. Is the download activity logged without exposing sensitive data or tokens?

A secure design must connect these layers. Restricting an NSG alone or enabling encryption alone is insufficient to answer all of these questions.

## 12. Incident Handling: Invoice Bucket Shared Improperly

Suppose the operations team discovers that the bucket holding invoices was switched to public access. There is no evidence that Object Storage infrastructure was compromised.

### 12.1. Customer's Share of Work

Following the approved runbook, the responsible team must:

1. Confirm the exact bucket, data type, and time of discovery.
2. Preserve necessary evidence such as configurations and change history.
3. Block the improper sharing path and inspect related PARs, policies, or credentials.
4. Identify which account or pipeline made the change.
5. Investigate access scope using appropriate log sources; clearly note any gaps insufficient for conclusions.
6. Handle credentials if there are signs of exposure or unauthorized use.
7. Fix source configuration, pipelines, or processes to prevent recurrence.
8. Re-verify access permissions and update the incident record.

Do not definitively conclude “no data was downloaded” simply because no events appear in a log source that does not cover that operation.

### 12.2. When Is Coordination With Oracle Needed?

If there are signs of a bug in the service's authorization mechanism, API results mismatching configuration, or suspicion involving Oracle-operated infrastructure, provide technical details through the appropriate support channel: resource, region, timeframe, request ID, and a reproducible description.

Oracle handles the portion belonging to the service it operates; the customer still must isolate risk and coordinate investigation of its workload. Opening a support request does not replace response actions within the organization's authority.

Do not send passwords, private keys, or secret tokens in support tickets. Provide sufficient technical traces for investigation through accepted exchange mechanisms.

## 13. Practice Exercise: Building a Responsibility Record and Verification

This exercise focuses on analysis and configuration inspection. You do not need to create billable resources or intentionally make data public to simulate an incident.

### 13.1. Preparation

Choose a test architecture or diagram consisting of Compute, VCN, a bucket, and a database service. If inspecting real resources, use only accounts with appropriate permissions and authorized test data.

Confirm in advance the tenancy name, compartment, and region to inspect. Do not mistake a development environment for production or vice versa.

### 13.2. Execution Steps

**Step 1 — List the layers.**

Record separately: infrastructure, guest OS, JDK, libraries, networking, IAM, data, secrets, logging, and recovery. For the database, specify self-installed on Compute, Base Database, or Autonomous Database.

**Step 2 — Split tasks by service.**

For each layer, identify Oracle's operational share and the organization's share under its control. If unknown, mark it for verification in service documentation; do not shift responsibility to Oracle by default.

**Step 3 — Assign internal owners.**

Choose the platform team, application team, database administration, or security team realistically. Every task must have an accountable point of contact for completion, even when multiple teams participate.

**Step 4 — Pick three controls to verify.**

For example:

- The invoice bucket must not be shared outside approved scope.
- Application servers accept traffic only from the designed path.
- Running Java software and OS have documented version info and an update owner.

**Step 5 — Collect current evidence.**

Read bucket configuration and related sharing mechanisms; inspect network rule layers; collect version evidence from the running environment or trusted management system. Do not alter permissions or open network paths just to make verification easier.

**Step 6 — Define drift detection mechanisms.**

Record which log types, configuration checks, or detection tools will report when a control changes. If using Cloud Guard, verify appropriate targets and detectors; if relying on pipelines, define how out-of-band changes are detected.

**Step 7 — Tabletop drill on paper.**

Suppose a control is violated: who receives the alert, who has authority to remediate, what evidence must be preserved, and who verifies restoration? There is no need to create an actual violation on live resources.

### 13.3. Sample Record for One Control

The following sample is illustrative exercise data, not an OCI configuration schema:

~~~json
{
  "control": "Invoice bucket sharing is restricted",
  "scope": "Test compartment, mock invoice bucket",
  "provider_part": "Operates the service's storage and access mechanisms",
  "customer_owner": "Platform team",
  "customer_action": "Check policies, public access, and PARs",
  "evidence": "Configuration read output and access path verification",
  "detection_owner": "Operations team",
  "verification_status": "NOT_VERIFIED"
}
~~~

Only change the record's verification result once evidence has been collected. Do not use a pre-filled template as proof that live resources are secure.

### 13.4. Completion Criteria

The exercise succeeds when:

- Each critical layer has responsibility boundaries accurately described for the chosen services.
- Each customer-side task has a specific owning team.
- The three chosen controls have verification results or are clearly marked not yet verifiable.
- Intake, remediation, and re-verification flows exist when violations are detected.
- Gaps are recorded as follow-up tasks with assigned owners.

## 14. Misconceptions That Easily Create Gaps

| Misconception | Understanding to Apply |
| --- | --- |
| “Running on OCI means Oracle patches all software.” | Identify who operates each layer; self-managed software still requires patching processes. |
| “With a managed database, the application needs no security.” | Data privileges, application code, and connection paths still must be controlled. |
| “Data is encrypted so broad sharing is still safe.” | Encryption and authorization protect different aspects. |
| “A private subnet prevents all risks.” | Permissions, connection flows, software, and business authorization still matter. |
| “Enabling detection tools finishes operations.” | Inspection scope, alert recipients, and responders are still needed. |
| “Having backups satisfies recovery.” | Data and application recovery must be tested against RPO/RTO. |
| “Budgets automatically block all excess spending.” | Budgets are soft thresholds; processes and resource controls are still required. |
| “Infrastructure certifications make the workload compliant automatically.” | The organization still must evaluate its configuration and actual usage. |

When designing an OCI workload, translate each security requirement into four elements: **control scope, owner, implementation method, and verification evidence**. Doing so turns the shared responsibility model into daily tenancy operations rather than just an introductory service diagram.