# What Is OCI and Core Service Groups

## Lesson Objectives

After this lesson, you can explain what Oracle Cloud Infrastructure (OCI) provides, distinguish the major service groups, and describe how they work together in a system. You can also identify initial decisions around access control, deployment location, data, monitoring, cost, and resilience.

This lesson belongs to the **Oracle Cloud Infrastructure Overview** section of the CLOUD_PROVIDERS_ORACLE module. The running example throughout is a Java order-management application: it has an API serving users, a database storing transactions, and a place to store PDF invoices. This is a design example for understanding services; you do not need to create paid resources to follow the lesson.

## 1. What Does OCI Provide?

**Oracle Cloud Infrastructure** is Oracle's cloud platform, providing infrastructure resources and platform services to build, deploy, and operate applications. You can provision servers, private networks, storage capacity, and databases through a web interface or automation tools.

A Java application running on a personal computer typically needs a JVM, database connection settings, and a data directory. When serving real users, the system also needs a stable access address, authorization, secret management, error tracking, backups, and scalability. OCI provides the components to meet those needs; the system architecture determines how they are combined.

Two usage levels can be envisioned:

| Usage Level | Example on OCI | Work the Development Team Needs to Handle |
| --- | --- | --- |
| Infrastructure as a Service, IaaS | Compute virtual machines, VCN networking, Block Volume | Choose configurations, install, and operate software on the provisioned resources |
| Managed platform, often under PaaS | Managed databases, Kubernetes Engine, Functions | Develop the application and configure the service within the scope of responsibility of each product |

The level of management differs across services. For example, renting a VM to install Oracle Database yourself creates a different operational workload than using a database service with automation. Therefore, when evaluating a service, identify **which part Oracle operates and which part your team still operates**.

OCI supports many types of applications, including Java applications, container services, data processing, and systems using Oracle Database. Oracle's SaaS business applications such as ERP or HCM belong to the broader Oracle Cloud ecosystem; choosing OCI to deploy your own applications is a decision at the infrastructure and platform layer.

## 2. Map of Core Service Groups

The following table groups services by design need. This is a learning map, not a complete catalog of every product or a fixed layout in the Console.

| Need | Service Group | Representative Components | Example for the Order Application |
| --- | --- | --- | --- |
| Organize resources, control permissions | Governance and Identity | Tenancy, Compartment, IAM | Separate learning and production environments; grant permissions by group |
| Connect components | Networking | VCN, subnet, gateway, Load Balancer | Receive HTTPS from users and forward to the API |
| Execute applications | Compute | Compute, Kubernetes Engine, Functions | Run the Java service or invoice-processing tasks |
| Store block, file, and object data | Storage | Block Volume, File Storage, Object Storage | Store disk data, shared directories, PDF invoices |
| Store structured data | Database | Base Database, Autonomous, Exadata Database Service | Store orders and payment status |
| Track activity | Monitoring and Observability | Monitoring, Logging, Audit | Detect slow APIs and trace configuration changes |
| Protect configuration and data | Security | IAM, key and secret management, Cloud Guard | Restrict permissions, protect connection credentials |
| Recreate and modify infrastructure | Automation | API, CLI, SDK, Terraform, Resource Manager | Recreate the environment from configuration |
| Track usage and spending | Cost Management | Cost Analysis, Budgets, tags, quotas | Attribute costs to the lab environment and set alerts |

A single service can serve multiple goals. IAM supports both governance and serves as a security foundation; tags help both with organization and with cost analysis. When reading documentation, relate each service to specific system requirements rather than just memorizing names.

## 3. Resource Organization Concepts

### 3.1. Tenancy, Compartment, and Resources

A **tenancy** is the account and governance boundary of an organization on OCI. Inside a tenancy, a **compartment** groups related resources to organize them and apply access permissions. A compartment is a logical grouping, not a server or a private network. See the definitions at [Account and Access Concepts](https://docs.oracle.com/en-us/iaas/Content/GSG/Concepts/concepts-account.htm).

Example of environment organization:

~~~text
Organization Tenancy
├── learning
│   ├── experimental Java application
│   └── mock data
├── staging
│   └── integration testing system
└── production
    └── system serving real users
~~~

This design helps learners identify where resources are allowed to be created and where stricter protection is needed. However, creating a compartment does not automatically complete access control; appropriate IAM policies are required. Nor does a compartment automatically block network traffic between two applications.

A compartment spans across regions within a tenancy. The same compartment can contain resources located in different regions; each resource still has its own deployment scope. Refer to [Working with Compartments](https://docs.oracle.com/en-us/iaas/Content/Identity/compartments/Working_with_Compartments.htm).

### 3.2. IAM Answers Who Can Do What

**Identity and Access Management (IAM)** manages identities and access permissions. It is necessary to distinguish:

- **Authentication:** which identity is sending the request?
- **Authorization:** which actions is that identity allowed to perform?
- **Permission scope:** which resources do those actions apply to?

For example, the learner group can observe and operate on resources in learning, while the operations group can manage production. Identity domains support managing users and identity configurations; policies express permissions for OCI resources. The foundational documentation is [Overview of IAM](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/overview.htm).

In practice, permissions should closely match the job. Someone who only reads monitoring metrics does not need permission to delete a database. An application that needs to write invoices to a storage location also does not need administrative permissions across the entire tenancy.

### 3.3. OCID Helps Identify Resources

Many OCI resources have an **Oracle Cloud Identifier (OCID)**. Display names help humans recognize resources; OCIDs help APIs and automation tools reference resources accurately.

In a deployment record, you should specify which resource belongs to which compartment and which region it is used in. If you only write the name “order-api”, operators may confuse the staging and production environments.

## 4. Deployment Locations: Region, Availability Domain, and Fault Domain

These three concepts describe levels of location and infrastructure isolation:

| Concept | Meaning | Questions to Ask |
| --- | --- | --- |
| Region | Geographic area where OCI services are deployed | Are user latency and data residency requirements met? |
| Availability Domain, AD | One or more data centers with infrastructure isolation within a region | How does the system tolerate a failure at the AD scope? |
| Fault Domain, FD | A grouping of hardware and infrastructure inside an AD | Are application replicas concentrated on the same infrastructure group? |

Each region has a specific number of ADs and service catalog that must be checked. Resource scopes also differ: for example, a VCN belongs to a region, whereas a Compute instance is attached to an AD. Do not assume every region has the same layout or every service deploys identically. See [Regions and Availability Domains](https://docs.oracle.com/en-us/iaas/Content/General/Concepts/regions.htm).

For the order application, choosing a region is a shared decision for components that interact frequently: the API, the database, and the invoice storage location. Placing them far apart without a clear reason can make connection times, data transfer, and error handling more complex.

For resilience, consider the failure scope. Two processes on the same VM can both stop when the VM fails. Even two VMs do not necessarily protect the system if critical data exists in only a single component. The design must consider the entire dependency chain.

## 5. Networking: Creating a Path for Requests

### 5.1. VCN and Subnets

A **Virtual Cloud Network (VCN)** is a virtual private network within a region. Subnets divide a VCN into address ranges and network configuration boundaries.

Example IPv4 design for this lesson:

~~~text
VCN: 10.20.0.0/16
├── ingress subnet: 10.20.1.0/24
│   └── public Load Balancer
├── application subnet: 10.20.2.0/24
│   └── Java VMs, no public IP assigned
└── data subnet: 10.20.3.0/24
    └── private endpoint of the chosen database
~~~

This is an illustrative addressing diagram. In a real deployment, you must check endpoint placement and the subnet requirements of the specific database service.

A working network flow simultaneously requires valid addressing, routing paths, rules allowing traffic, and a listening target service. Having IAM permission to create a VM is not enough to send HTTP to an application on that VM.

### 5.2. Commonly Used Components

| Component | Primary Role |
| --- | --- |
| Route table | Determines the forwarding destination for traffic by route |
| Internet Gateway | Provides an internet connection path for properly configured resources |
| NAT Gateway | Allows resources without a public IP to initiate outbound internet connections |
| Service Gateway | Provides a private path to supported services in Oracle Services Network |
| Network Security Group, NSG | Applies traffic rules to resources placed in the group |
| Security list | Applies traffic rules at the scope of subnets using the list |
| Load Balancer | Receives connections and distributes them to application backends |

Basic networking definitions are presented in [Networking Overview](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/overview.htm?elqak=8AF5B9E30B6DFC7B703A4F11B64785A066DAC37240E40E50CDD8B7F404B9023FB4EF).

For example, a private VM that needs to download updates can use a NAT Gateway. Connections initiated by the VM can receive responses; a NAT Gateway does not turn the VM into a server accepting arbitrary inbound connections from the internet. See [NAT Gateway](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/NATgateway.htm?source=%3Aso%3Afb%3Aor%3Aawr%3Aodv%3A%3A).

In the order example, only the ingress layer needs to be public. The API and database communicate over private paths restricted as needed. For instance, the application layer receives requests from the Load Balancer, while the database receives connections from the application layer.

## 6. Compute, Containers, and Serverless: Choosing Where to Run Code

### 6.1. Compute Instance

Compute provides virtual machines and bare metal servers. The **image** determines the operating system platform, while the **shape** determines the resource configuration. For a VM running Java, the operations team typically manages the guest OS, JVM, deployment artifact, and application configuration. See [Overview of the Compute Service](https://docs.oracle.com/en-us/iaas/Content/Compute/Concepts/computeoverview.htm).

A VM is an easy-to-picture choice when learning how an application uses infrastructure:

~~~text
Compute VM
├── operating system
├── JVM
├── order-api.jar
├── data connection configuration
└── process shipping logs and metrics
~~~

Choosing a configuration should be based on actual load. High CPU, out-of-memory conditions, and waiting on the database are different problems; increasing VM size may only solve part of them. For Java, you must allocate resources for the heap, off-heap memory, threads, and the operating system.

### 6.2. Kubernetes Engine, OKE

**Oracle Kubernetes Engine (OKE)** provides managed Kubernetes to deploy and orchestrate containerized applications. The scope of responsibility also depends on the node type and cluster configuration. Users still need to design workloads, access permissions, and application operations. See [Overview of Kubernetes Engine](https://docs.oracle.com/en-us/iaas/Content/ContEng/Concepts/contengoverview.htm).

OKE is suitable when a system needs container orchestration and the team has Kubernetes capability. A small Java service does not necessarily need a cluster; the decision should be based on deployment requirements, the number of services, and operational capability.

### 6.3. Functions

**OCI Functions** executes logic under the Functions as a Service model. Users focus on the function and execution configuration rather than provisioning VMs for each task. Examples include handling an event when a new invoice appears or transforming a file. See [Overview of Functions](https://docs.oracle.com/en-us/iaas/Content/Functions/Concepts/functionsoverview.htm).

Tasks must be designed around the platform's execution limits, triggers, and error handling. If an event is reprocessed, the application must avoid creating two invoices or recording the same business action twice.

| Option | When to Consider |
| --- | --- |
| Compute VM | Need control over the OS and runtime environment; want to start from a familiar server model |
| OKE | Need to orchestrate many container workloads with the Kubernetes operational model |
| Functions | Have event-driven or invocation-based tasks that fit the service's execution limits |

## 7. Storage: Which Access Pattern Does the Data Need?

Do not choose storage based only on capacity. You need to determine whether the application reads and writes data as blocks, files, or objects.

| Service | How It Is Used | Example |
| --- | --- | --- |
| Block Volume | Attached to an instance and used like a disk device | Data disk for software running on a VM |
| File Storage | Accessed as a shared file system over the network | Shared directory for machines that need file operations |
| Object Storage | Reads and writes objects in a bucket via API or suitable tools | PDF invoices, images, report exports |

**Block Volume** provides block storage that can be attached to an instance. Data can be preserved independently of the instance lifecycle when volumes are managed properly. Storage durability does not replace a backup plan against operator mistakes or application bugs. See [Overview of Block Volume](https://docs.oracle.com/en-us/iaas/Content/Block/Concepts/overview.htm).

**File Storage** provides a file system over the network, supporting NFS. The service is suitable when software needs path-based operations and data sharing between machines. Both network access rules and file permissions must be considered. See [Overview of File Storage](https://docs.oracle.com/en-us/iaas/Content/File/Concepts/filestorageoverview.htm).

**Object Storage** stores objects in buckets. In the order application, the database can hold the order ID and the invoice reference key; the PDF content resides in a private bucket. See [Overview of Object Storage](https://docs.oracle.com/en-us/iaas/Content/Object/Concepts/objectstorageoverview.htm).

Do not assume Object Storage behaves like an application's disk directory. When migrating code from reading local files to reading objects, you need to consider APIs, authentication, network errors, and concurrent access.

A useful design question is: **if the machine running the application is replaced, what data must still exist?** In the order example, orders and invoices must exist independently; temporary files used to generate PDFs can be regenerated.

## 8. Database: Choosing Management Level and Data Requirements

OCI offers several database options. In this module, the focus includes Oracle Database services; the choice should be based on workload type, compatibility, administrative privileges, and operational responsibility.

| Option Group | Key Characteristics to Understand | Questions When Choosing |
| --- | --- | --- |
| Base Database Service | Deploys Oracle Database with the service's management and automation capabilities | Which configurations, versions, and administrative privileges does the application need? |
| Autonomous AI Database, commonly known as Autonomous Database | Automates many database administration tasks | Does the application fit the capabilities and limits of the managed model? |
| Exadata Database Service | Oracle Database service on the Exadata platform | Does the workload require the characteristics and scale of Exadata? |
| Self-installed database on Compute | Your team manages the software on rented infrastructure | Is there sufficient capacity for patching, backups, recovery, and operations? |

Service families and related documentation are listed at [OCI Database](https://docs.oracle.com/en-us/iaas/Content/Database/home.htm). Product names and deployment options may evolve over time; when practicing, use the documentation for the exact service.

For the order system, start from data requirements:

- Which changes must be inside the same transaction?
- How many concurrent connections and what latency are acceptable?
- Is compatibility with an existing enterprise Oracle Database required?
- How much data loss at most and how long an outage are acceptable?
- Who is responsible for testing backups and recovery?

Using a managed service does not automatically solve schema design, SQL, indexing, connection pool limits, or application account permissions. An application can overload a database if each API replica opens too many connections.

## 9. Security and Shared Responsibility

OCI uses a shared responsibility model. Oracle protects the underlying cloud infrastructure; the customer protects workloads, identities, data, and resource configurations within their scope. The exact split depends on the service. See [Security Overview](https://docs.oracle.com/en-us/iaas/Content/Security/Concepts/security_overview.htm).

Applied to the order example:

| Area | Deployment Team Decision |
| --- | --- |
| Identity | Who can sign in, who requires MFA, which permissions must be revoked on role change |
| Administrative access | Who can modify networking, change configurations, delete resources |
| Application connections | How the application receives secrets and service access permissions |
| Data | Who can view orders, download invoices, access backups |
| Software | How the application and team-managed components are updated |

Do not place passwords or private keys in source code, images, or logs. Use secret management and workload identity mechanisms appropriate to the execution platform. Application permissions should also be scoped separately from deployer permissions.

An invoice bucket can be configured as private yet the application still exposes content if business permission checks are incorrect. Therefore, OCI IAM and application-level user authorization are two layers that must work together.

## 10. Monitoring: Knowing How the System Is Performing

A system needs both status data and data that explains incidents.

| Component | Question Supported |
| --- | --- |
| Monitoring and alarms | Are CPU, errors, or latency exceeding configured thresholds? |
| Logging | Which requests failed and what did the application record? |
| Audit | Which administrative actions or recorded API calls changed which resources? |
| Application monitoring and tracing | Which component in the processing chain did a request spend time in? |

Monitoring uses metrics and alarms; notification destinations must be configured so operators receive alerts. See [Overview of Monitoring](https://docs.oracle.com/en-us/iaas/Content/Monitoring/Concepts/monitoringoverview.htm).

For example, the API might return errors because it cannot acquire a database connection while VM CPU remains low. Observing only CPU does not reflect the full health of the application. The team needs to add business metrics and logs with correlation IDs for requests.

According to [Monitoring and Observability](https://docs.oracle.com/en-us/iaas/Content/cloud-adoption-framework/monitoring-and-observability.htm), data such as metrics, logs, and events support observing and troubleshooting system issues. In practice, you can start with request count, error rate, response time, and data connection status.

Logs need enough context for investigation while avoiding tokens, passwords, payment details, or full sensitive customer data.

## 11. Automation: From Actions to Reproducible Configuration

There are several ways to work with OCI:

| Approach | Typical Role |
| --- | --- |
| Console | Explore services and inspect resources via web interface |
| CLI | Perform repetitive actions or query resources from the command line |
| REST API, SDK | Integrate OCI into tools and applications; SDK has a Java option |
| Terraform | Describe desired infrastructure state in configuration |
| Resource Manager | Run and manage infrastructure jobs from supported configurations on OCI |

Resource Manager supports managing Terraform configurations and state, with jobs such as planning and applying changes. See [Overview of Resource Manager](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Concepts/resourcemanager.htm).

For the order environment, reproducible configuration should express the network, where the application runs, required links, and environment-specific configuration values. Secrets must be handled through an appropriate mechanism, not written in plain text in public configuration.

Automation reduces manual steps, but intended changes must be reviewed before applying. A misconfiguration can create many wrong resources very quickly. Permissions for automation tools should therefore also be scoped to their task.

## 12. Cost and Availability Must Go With Design

### 12.1. Cost Control

System cost includes multiple components: compute capacity, storage, databases, data transfer, and related operational services. A mental formula is:

~~~text
Estimated cost
  = compute resources over time
  + storage and backups
  + database services
  + billable traffic
  + other supporting services
~~~

This is a way to list cost sources, not Oracle's pricing formula. Billing units and pricing policies must be checked on the exact service before creating resources.

**Budgets set soft spending thresholds and alerts.** A budget does not guarantee that resources stop when a threshold is reached; data and alerts also have an evaluation cycle. See [Budgets](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/budgetsoverview.htm?source=%3Apm%3Amz%3A%3A%3Arc_wwmk170417p00028%3Aprofitsummersmbenterprise).

In a learning environment, define the compartment, duration of use, responsible person, and cleanup plan upfront. When finished, check volumes, backups, and accompanying services as well; stopping a VM is not enough to conclude the entire system has stopped incurring charges.

Service limits, quotas, and budgets serve different purposes. Limiting the number of resources is not equivalent to capping total spend. Having quota available also does not guarantee the provider has provisioning capacity in your chosen location.

### 12.2. Availability and Recovery

**High availability, HA** aims to maintain service when a component fails. **Disaster recovery, DR** aims to restore operations after a larger incident. Both goals must be designed and tested separately.

Two concepts are commonly used to express recovery requirements:

- **RTO:** target time to restore operations.
- **RPO:** target amount of data that may be lost, measured in time.

As a hypothetical example, a team sets an RTO of one hour and an RPO of fifteen minutes. The architecture must have processes and data mechanisms that meet those targets; merely writing two numbers in a document does not prove the system can recover.

A Load Balancer with two APIs does not protect transactions if the database remains an unhandled single point of failure. Likewise, having backups does not mean recovery time is known. Testing recovery is part of operations.

## 13. Combining Service Groups Into an Order System

The diagram below is an **illustrative architecture**, not a complete deployment configuration. Buckets belong to Object Storage, not inside a subnet; private paths to services require corresponding network configuration and permissions.

~~~mermaid
flowchart TB
    U["User"] -->|"HTTPS"| LB

    subgraph R["Chosen Region"]
        subgraph V["VCN"]
            LB["Public Load Balancer"]
            A["Java API - Replica A"]
            B["Java API - Replica B"]
            DB["Private endpoint of database service"]
            SG["Service Gateway"]
            LB --> A
            LB --> B
            A --> DB
            B --> DB
            A --> SG
            B --> SG
        end
        SG --> O["Object Storage - private invoice bucket"]
    end

    A -.-> T["Metrics and logs"]
    B -.-> T
    T --> M["Monitoring, Logging, and alarms"]
~~~

An order creation request might pass through these steps:

1. The user sends HTTPS to the Load Balancer.
2. One API replica authenticates the user and checks business permissions.
3. The API writes the order to the database.
4. The invoice-generation task writes the PDF to Object Storage.
5. The application stores the invoice reference key while emitting necessary logs and metrics.
6. When the user requests to download the invoice, the application checks permissions and serves the data using the designed mechanism.

You must handle the case where the database write succeeds but invoice generation fails. One design can record a pending state and allow safe retries, rather than treating all steps as an atomic transaction across services.

The two API replicas should avoid keeping critical state on local disk. If a login session or invoice exists only on replica A, a user routed to replica B may hit errors even while both VMs are still running.

The diagram does not yet show database HA configuration, backups, secret management, network rules, or AD/FD placement. In a real deployment, the team must add those decisions according to the chosen goals and services.

## 14. Practice Identifying Services Without Provisioning Resources

Prepare a short design for the Java application in the following order:

1. **Define the scope:** one learning environment, mock data, one intended region.
2. **Organize resources:** choose compartments and required roles.
3. **Choose where to run code:** start with a VM if the goal is learning infrastructure; note reasons if choosing OKE or Functions.
4. **Classify data:** transactions in the database, PDFs in Object Storage, temporary files that can be regenerated.
5. **Map access paths:** specify public components and required private connections.
6. **Set operational signals:** identify metrics, logs, alert recipients, and how to check whether the application is still serving.
7. **Set practice limits:** expected cost sources, duration of use, and cleanup checklist.
8. **Define recovery:** note data that must be protected and how to test recovery.

The expected outcome is a diagram and a decision table with rationale. For example: “Invoices reside in Object Storage because the application needs to store and retrieve individual documents by key; the VM only holds temporary files while processing”.

If you already have Console read access, you can identify the corresponding region, compartment, and resource information. An empty list must be checked against the right scope and permissions before concluding that resources do not yet exist.

## 15. Misconceptions to Correct From the Start

| Misconception | Correct Understanding for Design |
| --- | --- |
| OCI is only for Oracle Database | OCI also provides networking, compute, storage, and many platform services |
| A compartment is a subnet | A compartment organizes and authorizes; a subnet belongs to network structure |
| Having IAM means all access is controlled | Network rules, data permissions, and application-level authorization are still required |
| A managed service means no operational work | Remaining responsibility depends on the service and configuration used |
| Having two APIs means the system is HA | You must consider the Load Balancer, data, dependencies, and failure scopes |
| Durable storage means any error can be recovered | Backups, retention periods, and recovery testing are still required |
| A budget is an automatic spending cap | Budgets provide soft thresholds and alerts |
| Stopping a VM finishes the cost part | You must also check storage, backups, and accompanying resources |

When moving to deeper lessons, always link each service name to four questions: **what need does the service solve, what does it connect to, who is allowed to use it, and what part must your team operate**. That way, learning tenancy, IAM, VCN, Compute, storage, and databases becomes related decisions within the same system.