# Distinguishing OCI, Oracle Cloud Applications, and Oracle Database

## Lesson Objectives

After this lesson, you can determine whether a requirement belongs to the OCI infrastructure platform, the Oracle Cloud Applications business suite, or the Oracle Database management system. You can also explain how these three groups work together, distinguish the access permission layers, and identify operational responsibilities before deployment.

This lesson is in the **Oracle Cloud Infrastructure Overview** section of the CLOUD_PROVIDERS_ORACLE module. The focus is on reading the architecture accurately and choosing the right scope of work before studying tenancy, compartments, IAM, VCN, Compute, storage, and database services.

## 1. Three Concepts Answering Three Different Questions

An enterprise may use all three product groups in the same system:

- **OCI — Oracle Cloud Infrastructure:** which infrastructure resources and platform services are used to deploy, connect, and operate the system?
- **Oracle Cloud Applications:** which business applications are used to perform work such as accounting, human resources, or supply chain management?
- **Oracle Database:** which database management system is used to organize, query, and protect application data?

For example, an enterprise has a supplier portal written in Java:

1. The portal runs on OCI Compute and uses VCN networking.
2. The portal's own data is stored in Oracle Database.
3. The portal exchanges business information with Oracle Fusion Cloud ERP via a supported integration interface.

All three choices appear together, yet play different roles. Changing where the Java portal runs does not automatically change the ERP software; changing the portal's database management system also does not automatically transform the enterprise's business applications.

| Criterion | OCI | Oracle Cloud Applications | Oracle Database |
| --- | --- | --- | --- |
| Nature | Cloud infrastructure and platform services | Business applications delivered as a service | Database management system and related deployment options |
| Primary users | Cloud, platform, development, and operations engineers | Business users, functional consultants, and application administrators | Developers, DBAs, data engineers |
| Typical objects operated on | Compartments, networks, VMs, buckets, service resources | Business documents, employees, workflows, business roles | Tables, indexes, transactions, users, and data privileges |
| Typical tasks | Creating an environment to run an API | Configuring a purchase approval workflow | Designing tables and querying orders |
| Knowledge scope | Infrastructure and platform | Business processes and application configuration | Data management and access |

In this lesson, examples of Oracle Cloud Applications mainly use **Oracle Fusion Cloud Applications**, a representative SaaS suite. When encountering a specific product name, always verify the exact product and delivery model; the phrase “Oracle Applications” has a broader scope than a single SaaS suite.

## 2. OCI: The Platform to Build and Operate Systems

### 2.1. Value Provided by OCI

OCI provides components such as compute, networking, storage, and platform services. You combine them to run custom-developed applications, enterprise software, or data workloads. An overview portfolio is presented at [Oracle Cloud Infrastructure](https://www.oracle.com/cloud/).

For the Java supplier portal, decisions at the OCI layer include:

| Decision | Related Components |
| --- | --- |
| Which governance scope should resources be placed in? | Tenancy, compartment |
| Who can create, modify, or delete resources? | IAM |
| Through which path does the application receive connections? | VCN, subnets, routing, and network rules |
| Where does the Java code run? | Compute, containers, or an appropriate execution model |
| Where are attachments stored? | Object Storage or an appropriate storage service |
| How is infrastructure monitored and recreated? | Monitoring services, APIs, and automation tools |

Creating a new VM only creates a compute environment. To deliver the supplier portal, the project team still has to deploy code, configure authentication, connect data, and build business workflows.

### 2.2. OCI Includes Multiple Service Levels

Do not treat every OCI resource as a self-managed virtual machine. The platform also has managed services, such as database services. The level of automation and control depends on each service.

For example:

~~~text
Option A
OCI Compute
└── your team installs and operates the database software

Option B
Database service on OCI
└── uses the management capabilities of the chosen service
~~~

Both options use OCI, yet responsibilities for patching, backups, and software management can differ. When planning, record the specific service name instead of merely writing “database on cloud”.

## 3. Oracle Cloud Applications: Applications Serving Business Processes

### 3.1. Focusing on Organizational Workflows

Oracle Fusion Cloud Applications provides functionality for areas such as ERP, HCM, supply chain, and customer experience. Users work with business objects and workflows already provided by the product. See [Oracle Fusion Cloud Applications](https://www.oracle.com/applications/).

For example:

| Business Need | Application Group Commonly Considered |
| --- | --- |
| Managing financial operations and related processes | ERP |
| Managing human resources and employee lifecycle | HCM |
| Managing supply chain operations | SCM |
| Supporting sales, service, and customer interactions | CX |

This is a way to identify domains, not a claim that every capability is available in every package. Actual scope depends on the product modules and configuration.

In the SaaS model, the provider operates the service software; the customer still needs to implement business processes, configure permissions, prepare data, and test integrations. Oracle presents this model at [SaaS Comparison — Oracle Cloud Applications](https://www.oracle.com/applications/what-is-saas/comparison-saas/).

### 3.2. What Customers Typically Configure

A SaaS project may need to define organizational structure, user groups, approval workflows, and how data is migrated from legacy systems. Implementation work focuses on how the enterprise uses the product.

Hypothetical example: the purchasing department wants purchase orders exceeding an internal threshold to go through an additional approval level. First and foremost, this is a workflow and business authorization requirement inside the application. Adding CPU to a VM will not create that workflow.

Conversely, if the enterprise builds an additional custom portal for suppliers, the portal may need infrastructure to run code, store data, and monitor operations. This extension creates work at the OCI layer, even though the SaaS application remains operated by the provider.

### 3.3. A SaaS App Running on Infrastructure Does Not Mean the Customer Administers That Infrastructure

Oracle describes Fusion Cloud Applications as built on Oracle's cloud infrastructure. However, permissions to use a SaaS application and permissions to administer infrastructure resources are different scopes.

A business administrator does not automatically get SSH access to the SaaS service's servers. Similarly, an organization having an OCI tenancy does not mean every resource inside the SaaS service becomes a VM or database directly managed by the organization.

If an OCI interface supports managing Fusion environments, you must distinguish environment management operations permitted by the product from access to the underlying operating system or data. Each operation still remains subject to the corresponding service scope and authorization.

## 4. Oracle Database: Data Management System With Multiple Deployment Options

### 4.1. Role of the Database Management System

Oracle Database manages data, providing querying, transactions, and access control. Applications can use SQL and appropriate interfaces to work with data. Foundational concepts are explained in [Introduction to Oracle Database](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/introduction-to-oracle-database.html).

In the custom-developed supplier portal, the project team might design a table to store registration requests:

~~~sql
SELECT request_id, supplier_code, approval_status
FROM supplier_requests
WHERE approval_status = 'PENDING';
~~~

This SQL snippet only illustrates a hypothetical schema managed by the project team. It is not a query against an internal Fusion table and is not a command executed in this lesson.

The database management system provides mechanisms to store and query data; the application team still needs to define valid statuses, state-transition rules, and who is allowed to approve. A table with an approval_status column does not by itself form a complete purchasing system.

### 4.2. Oracle Database Can Appear Outside OCI

Oracle Database has deployment options in an enterprise's on-premises data center and on supported cloud environments. Therefore, knowing “the application uses Oracle Database” does not tell you where the application or database is running. See deployment models at [Oracle Database](https://www.oracle.com/database/).

Two axes must be separated:

| Decision Axis | Example Answers |
| --- | --- |
| Data technology | Oracle Database |
| Deployment location and management model | On-premises server; self-managed on Compute; managed database service |

A change on the location axis can keep the database technology unchanged. A change on the technology axis may require modifying SQL, drivers, data types, and operational procedures even when the deployment location stays the same.

### 4.3. Oracle Database and Oracle Database Services on OCI

**Oracle Database** is the database management system technology. **Oracle Database services on OCI** are ways of delivering and operating that technology with platform capabilities.

Options such as Base Database, Autonomous, and Exadata Database Service have different management scopes. Starting documentation is at [OCI Database](https://docs.oracle.com/en-us/iaas/Content/Database/home.htm).

Even when a service automates many administrative tasks, the application still needs an appropriate schema, properly privileged accounts, and efficient queries. A database service does not automatically provide ERP or HCM workflows like a business application suite.

## 5. Relationships Among the Three Groups: Combining by Need

The diagram below depicts an integration example, not a mandatory structure for every Oracle system.

~~~mermaid
flowchart LR
    U["Supplier portal user"] --> J

    subgraph C["Customer-deployed system part on OCI"]
        J["Custom-developed Java application"]
        D["Portal's Oracle Database"]
        S["Portal's Object Storage"]
        J -->|"SQL via JDBC"| D
        J -->|"Storage API"| S
    end

    J -->|"HTTPS via supported API"| F["Oracle Fusion Cloud Applications SaaS"]
    B["Business user"] --> F
~~~

Meaning of the diagram:

- OCI provides the platform for the customer-deployed portion of the system.
- Oracle Database holds data belonging to the portal in this example.
- Fusion provides SaaS business functionality and integration interfaces.
- A user may work across multiple applications, but permissions in each application must be defined.

The diagram intentionally places Fusion outside the resource scope directly managed by the portal team. It does not claim Fusion runs outside Oracle infrastructure or that all integration connections share the same network path.

In a real architecture, you also need to determine the system of record. For instance, if supplier profiles are managed by ERP, records in the portal might only be pending submissions or a UI cache copy. Both sides should not update independently without reconciliation rules.

## 6. Three Access Permission Layers to Distinguish

Successfully signing into one system does not automatically grant permissions in the other systems. Even with SSO, you must distinguish **identity authentication** from **action authorization**.

| Permission Layer | Protected Target | Example Operations Requiring Permission |
| --- | --- | --- |
| OCI IAM | Cloud resources and administrative operations | Create VMs, change network config, manage database resources |
| Roles inside SaaS applications | Business functionality and business data | View documents, approve transactions, call business APIs |
| Privileges inside Oracle Database | Connection sessions and data objects | Connect to database, read tables, execute procedures |

OCI IAM controls who can act on OCI resources within the granted scope. This model is built on identities, groups, and policies; see [Overview of IAM](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/overview.htm).

Oracle Database controls access to data objects through users, roles, and privileges. See [Protecting Database Objects by Using Schemas](https://docs.oracle.com/en/database/oracle/oracle-database/26/dbseg/protecting-database-objects-using-schemas.html).

For Fusion, permission to call REST APIs also depends on application roles and privileges. The [Quick Start for Oracle Fusion Cloud Financials REST API](https://docs.oracle.com/en/cloud/saas/financials/26d/farfa/Quick_Start.html) guide requires checking permissions for the corresponding resource and operation.

### 6.1. Permission Assignment Example for a Project Team

Assume a project has three people:

- **An — platform engineer:** creates networks and VMs for the portal.
- **Bình — business specialist:** configures and tests purchasing workflows.
- **Chi — DBA:** manages the portal's dedicated data schema.

The permission design could be:

| Person | Assigned Job | Permissions That Should Not Be Assumed by Default |
| --- | --- | --- |
| An | Manage infrastructure in the portal's compartment | Permission to approve purchases in Fusion |
| Bình | Perform assigned business tasks | Permission to alter routes or delete VMs |
| Chi | Manage portal data per role | Tenancy-wide admin rights or access to all data in SaaS |

Broad infrastructure administrative privileges can indirectly affect data confidentiality and integrity, such as via configuration changes or resource lifecycle operations. Therefore, separating the three permission layers must also go hand in hand with privileged account controls and separation of duties.

### 6.2. Conditions for an Application to Read Data

For the portal's own Oracle Database, a connection typically needs to satisfy all of the following at once:

1. The application has a network path to the database endpoint.
2. Connection settings and transport security are configured appropriately.
3. The connecting identity is authenticated.
4. That identity has privileges to access the required data objects.

OCI permission to view a database resource does not replace those conditions. Conversely, an account that reads a table does not automatically gain permission to change cloud resource network settings.

Services may support identity integration to simplify authentication. Even with integration, permission scope and access conditions still need to be configured according to the documentation of the exact service.

## 7. Distinguishing Three Types of Programming Interfaces

For a Java developer, “calling Oracle” can mean three different tasks.

| Task | Commonly Used Interface | Resulting Objects |
| --- | --- | --- |
| Managing cloud resources | OCI API, OCI SDK, or CLI | Resource info, provisioning state, service configuration |
| Exchanging business data with Fusion | APIs and integration mechanisms supported by the application | Business data such as documents or records |
| Reading and writing self-managed application data | JDBC and appropriate SQL | Data rows, query results, transaction outcomes |

Example describing the configuration of a Java service:

~~~text
OCI_SCOPE
  tenancy
  compartment
  region
  appropriate OCI authentication method

PORTAL_DATABASE
  endpoint of dedicated database
  service name and connection configuration
  database identity or supported authentication mechanism

FUSION_INTEGRATION
  SaaS environment URL
  documented API path
  corresponding authentication method and business permissions
~~~

This is a conceptual description, not a runnable configuration file as-is. In a real application, each group needs its own configuration, secret management, and error handling.

### 7.1. Do Not Infer SQL Access From SaaS Usage Rights

When integrating with Fusion, start from the APIs, import/export tools, or extension mechanisms supported by the product. Do not design around the assumption that the project team can open a JDBC connection into the SaaS internal database.

Some products provide their own reporting or data extraction tools. Having permission to use those tools does not equate to database administrator rights or permission to modify internal tables directly.

As a concrete example of a SaaS boundary: [Understanding Access Limits for Cloud EPM](https://docs.oracle.com/en/cloud/saas/enterprise-performance-management-common/tsepm/7_tips_and_tricks_understand_access_limits.html) states that this service does not provide direct SQL access to the underlying database. When working with another product, read the documentation for that exact product rather than generalizing this detail into a universal rule for every SaaS.

### 7.2. Do Not Treat Technical Status as Final Business Outcome

Suppose the portal submits a record to ERP:

~~~text
Portal receives record
→ saves pending-send state
→ calls integration API
→ records service-side response
→ tracks business status and reconciles
~~~

Successfully provisioning a VM only indicates that an infrastructure resource was created. Writing a row to a database only reflects the outcome of that data operation. On the ERP side, there are still validations and business workflows to monitor.

If an API uses asynchronous processing, the application must distinguish between the request being accepted and the business operation being completed. How to determine this must rely on the documentation of the specific endpoint.

When retrying after a network error, avoid creating duplicate records. You can design a business reference ID, submission status, and reconciliation mechanism suited to the capabilities of the API being used.

## 8. Migrating an App to OCI and Moving to SaaS Are Two Different Project Types

### 8.1. Moving Existing E-Business Suite to OCI

An enterprise operating Oracle E-Business Suite can move the system to OCI infrastructure in a supported configuration. The application remains E-Business Suite; the project changes the deployment location and may change how some components are managed.

Oracle confirms this distinction in the [Oracle E-Business Suite on Oracle Cloud FAQ](https://docs.oracle.com/cd/E72030_01/infoportal/ebscfaq.html).

Tasks to consider may include:

- Verifying certified application, OS, and database configurations.
- Designing networking and connectivity with existing systems.
- Migrating data and application components.
- Testing integrations, performance, and recovery.
- Defining the team or partner responsible for operations after cutover.

The level of self-management may differ if the enterprise adds managed services. Hiring an operations provider still needs to be distinguished from switching to a different SaaS product.

### 8.2. Moving Business Processes to Fusion Cloud Applications

Moving from an existing application to Fusion SaaS typically requires evaluating processes, configuration, data, and integrations against the target product.

For example, a customization in a legacy system may need to be replaced with built-in configuration capabilities or supported extensions. Data may need to be cleansed and mapped to the target structure. Users also need permission checks and training on the new workflows.

| Area | Migrating an Existing App to OCI | Moving to Fusion SaaS |
| --- | --- | --- |
| Focus | Deployment location and operational architecture | Business application and how workflows are implemented |
| Application software | Can keep the existing application in a supported configuration | Uses the functionality of the target SaaS product |
| Data | Migrated and validated according to the chosen architecture | Cleansed, mapped, and loaded per product capabilities |
| Integration | Re-verify connectivity and compatibility | May require redesigning interfaces and business flows |
| Operations | Define responsibilities across infrastructure, application, and data layers | Business administration, permissions, integrations, and SaaS customer responsibilities |

Do not estimate a SaaS migration project solely by the time needed to copy VMs or databases. The two project types have different transformation targets and completion criteria.

## 9. Operational Responsibility Changes With Service Choice

OCI's shared responsibility model requires customers to understand their share of work regarding workloads, permissions, and configurations. See [Security Overview](https://docs.oracle.com/en-us/iaas/Content/Security/Concepts/security_overview.htm).

The table below is for analyzing responsibilities, not a replacement for each service's operational documentation:

| Choice | Part the Project Team Must Clearly Define |
| --- | --- |
| Java and self-installed database on Compute | Manage guest OS, software, patching, backups, and recovery |
| Java connecting to a managed database service | Remaining responsibilities for schema, queries, privileges, connections, and data protection configuration |
| Using Fusion SaaS | Business configuration, users, authorization, data, and integration testing |
| Java portal integrating with Fusion | Portal operations, data synchronization, integration error handling, and identity separation |

A combined system may require multiple teams to troubleshoot a single incident together. For example, “unable to create supplier” could stem from a dropped connection, invalid outbound payload, missing API permissions, or an ERP business rule.

Investigation should follow the flow:

1. Identify the business operation and affected users.
2. Check whether the request reached the portal.
3. Check whether the portal saved the data and sent the integration call.
4. Check the result returned by the target service.
5. Reconcile status on both sides before retrying or fixing data.

Correlation IDs and business reference IDs help connect information across layers. Logs should avoid recording passwords, tokens, or unnecessary sensitive data.

## 10. Cost and Availability Must Be Examined Layer by Layer

### 10.1. Separating Cost Sources

You cannot deduce total cost from a single label like “Oracle Cloud”.

| Scope | Components to Include in Budget Estimates |
| --- | --- |
| OCI for custom-deployed apps | Compute, networking, storage, and services used |
| Oracle Database | Deployment option, capacity and storage, data protection, applicable software usage model |
| Oracle Cloud Applications | Modules, subscription scope, and usage metrics for the selected service |
| Integration system | Runtime environment for extensions, data storage, data transfer, and operational effort |

This table only points out scopes to check; it does not state terms or prices. When building a real budget, cross-check the exact service and usage agreement.

A SaaS subscription and OCI resources for an extension portal can coexist. Therefore, monitor both portions rather than assuming extension costs are included in every application subscription.

### 10.2. Component Availability Does Not Reflect Full Process Availability

Suppose the Java portal is running and its dedicated database is reachable, yet the target API is temporarily unavailable. Users can submit new records, but registration inside ERP is not yet complete.

The design can allow:

- Accepting the record and clearly displaying a pending status.
- Persisting a request trail for controlled retries.
- Preventing duplicate submissions when the target received the request but the response was lost.
- Reconciling status once connectivity recovers.

This is a decision of integration and business architecture. Increasing the number of VMs only supports the application portion running on them; completing the workflow also depends on the database, SaaS service, and related connections.

## 11. How to Interpret an Ambiguous Requirement

When receiving a request to “deploy Oracle”, clarify the deliverable before choosing services.

| Initial Statement | Information to Clarify | Classification Direction |
| --- | --- | --- |
| “Need an Oracle machine to run Java” | Need a machine to run code, an OS, or a specific application product? | Usually starts at OCI infrastructure if the goal is running a custom app |
| “Need an Oracle HR system” | Which HR capabilities and which product choice are needed? | Business application, potentially Fusion HCM |
| “Move Oracle to the cloud” | Moving a database, an existing app, or moving business processes to SaaS? | Not enough information to conclude |
| “Java needs to connect to Oracle” | Connecting to a database via JDBC or calling an application API? | Must identify endpoint and identity type |
| “Give the team Oracle permissions” | Resource management rights, business rights, or SQL rights? | Separate the permission layers |
| “Pull data from ERP” | Which data, for what purpose, and which interface is supported? | Application integration and data governance |

A clearer description might be:

~~~text
Build a supplier portal in Java.

Deployment part:
- run on OCI in the project's compartment;
- store dedicated data in a chosen Oracle Database service;
- store attachments in an appropriate storage service;
- integrate with Fusion via a supported API.

Operations part:
- restrict permissions by job function;
- track integration status and handle retries;
- define the system of record, costs, and recovery approach.
~~~

This description separates where code runs, data technology, business application, and operational work. The project team can continue selecting detailed services with less scope confusion.

## 12. Quick Identification Scenarios

### Scenario A: Learning Java and Oracle SQL on a Personal Computer

The learner runs a Java application and Oracle Database in an appropriate development environment. The scenario includes Oracle Database technology; there is no indication that OCI or a SaaS application suite is being used.

### Scenario B: Moving a Java API to OCI

The application is deployed onto Compute and uses OCI storage services. This is work on the OCI platform. You cannot conclude the application uses Oracle Database or Fusion if the architecture has not stated those choices.

### Scenario C: An Employee Creates a Document in Fusion

The employee uses authorized business functions inside the SaaS application. The main work is a business workflow. The user does not need to create a VM for each document and does not become a DBA by performing that action.

### Scenario D: Keeping the Database On-Premises, Moving the Java Layer to OCI

The system combines an application on OCI with Oracle Database in another location. Connectivity, latency, security, and outage handling must be designed. The database technology name alone does not determine its deployment location.

### Scenario E: A Java Portal on OCI Integrating With Fusion

All three groups can appear together if the portal uses its own Oracle Database. The team must manage the boundaries: OCI resources, portal data, and business functionality provided by Fusion.

## 13. Pre-Deployment Identification Checklist

Before choosing services or requesting permissions, complete the following details:

| Item | Result to Specify Clearly |
| --- | --- |
| Product | OCI, business application name, database engine or data service name |
| Deliverable | Code execution environment, business capability, data, or integration flow |
| Deployment location | Which parts are in OCI, SaaS, or on-premises environment |
| Permissions | Cloud administrative identity, application identity, and data identity |
| Responsibilities | Who configures, patches, backs up, monitors, and handles incidents for each part |
| System of record | Which system has authority to decide business values |
| Cost | Which services and subscriptions must be included in monitoring scope |
| Recovery | Which workflows must continue operating and how data is handled during an outage |

In this module, the lessons on tenancy, IAM, VCN, Compute, and storage build deployment capability on OCI. The database lessons explain choosing and operating the related data services. When connecting with Oracle Cloud Applications, you must add corresponding product and business knowledge to design interfaces, permissions, and responsibilities accurately.