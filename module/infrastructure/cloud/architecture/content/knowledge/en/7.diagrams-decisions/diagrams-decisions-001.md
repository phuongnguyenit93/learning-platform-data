# The C4 Model: Context, Containers, and Components

When designing a system in the cloud, architects must communicate with multiple groups: product owners want to understand which business capabilities the system supports; backend engineers need to know how components depend on one another; platform teams need to know what resources must be deployed; and security teams need to identify critical trust boundaries and data flows. A single diagram packed with cloud service icons rarely satisfies all of those needs at once.

The **C4 model** is a way of describing software architecture at different levels of zoom: **Context**, **Container** (a runnable or data-storage unit), and **Component** (parts inside a container), along with the **Code** level when needed. The first three levels are usually sufficient to clarify a cloud design during the architecture phase. Instead of drawing every server, database, API, and processing layer in a single picture, the designer moves deliberately from the big picture down to intentional detail.

In the **CLOUD_ARCHITECTURE** module, C4 helps move from **business requirements** to **application structure**, before selecting networking, compute, data, and deployment models. C4 helps stakeholders discuss trade-offs across **reliability, security, scalability, cost, and operations**; those properties themselves still have to be verified through deployment design, measurements, and Well-Architected reviews.

## 1. What Questions Does C4 Answer?

The name **C4** comes from four C words: *Context, Container, Component, Code*. Each level depicts the same system at a different scope of observation.

| Level | Core question | Primary elements in the diagram | Typical audience |
|---|---|---|---|
| **1. System Context** | Who does the system serve and which external systems does it interact with? | Users, the system being designed, other systems, and the relationships between them | Product owner, business analyst, architect, security |
| **2. Container** | What applications or data stores exist inside the system, and how do they communicate? | Web app, API, worker, database, queue, application or storage units | Architect, developer, platform, operations |
| **3. Component** | What functional building blocks is a specific container split into, and how do they depend on each other? | Controller, application service, domain service, adapter, repository, and similar functional blocks | Developer, tech lead, design reviewer |
| **4. Code (optional)** | Which classes, interfaces, packages, or code modules implement the critical components? | Selected code structures | Developer, code maintainer |

These levels are **not four mandatory stages that must all be drawn**. The purpose of zooming is to include only the detail readers need to make decisions. A small system may only need Context and Container; a complex API may need Component as well; a Code diagram is usually only useful for a specific part that is hard to understand.

### Example of Levels of Detail

Suppose we are building a **Booking System** that allows customers to search for spots, make bookings, and receive confirmations:

- **Context:** Customers use the Booking System; the system communicates with a payment gateway and an email provider.
- **Container:** The Booking System has a Web App, Booking API, transactional database, queue, and notification worker.
- **Component:** Inside the Booking API are an HTTP Controller, Booking Service, booking rule checks, Repository, Payment Adapter, and Outbox Writer.
- **Code:** Only when needed do we draw the Booking Service interface, transactional data types, and how the Repository performs atomic operations.

Each level must be **semantically consistent**: an external system mentioned at the Context level remains an external system at the Container level; you must not accidentally turn a partner's payment gateway into an internal component just because you are drawing at a finer level of detail.

## 2. C4 Concepts and Notation Rules

C4 focuses on a simple set of elements:

| Element | Meaning | Examples |
|---|---|---|
| **Person** | A human user or role that directly interacts with the system | Customer, operations staff |
| **Software System** | A software system delivering meaningful functionality to users or other systems | Booking System, Payment Gateway |
| **Container** | An application or data store that runs/stores data as a distinct unit with its own role within a software system | Web App, Booking API, database, message broker |
| **Component** | A cohesive set of functionality grouped behind a clear interface or responsibility inside a container | Booking Service, Reservation Repository |
| **Relationship** | A usage or data-exchange relationship between elements | "Calls HTTPS API", "Reads/writes bookings", "Consumes messages" |
| **Boundary** | The system boundary or grouping scope of the elements being described | Booking System containing its containers |

**A Container in C4 is not synonymous with a Docker container.** A C4 container can be a JVM application running on a virtual machine, a web app in a browser, a managed database, or a serverless worker. It expresses an **application or data-store boundary**, without prescribing Docker, Kubernetes, or instance counts.

**A Component in C4 is not synonymous with a microservice.** A component is a functional structure **inside a container**; it may be a Java module, a package group, or a set of classes. A microservice usually has its own deployment and operational boundary, so it may appear as a **container at the C4 level**, depending on how the software system is scoped.

**A C4 boundary is not automatically a security trust boundary.** Putting two components inside the same system box does not guarantee they share the same permissions, network, or data classification. During security reviews, trust boundaries, sensitive data, and actual access flows must be annotated explicitly.

### Rules to Help Readers Understand Diagrams

1. **Name elements by business role or responsibility:** "Booking API" is clearer than "Service A"; "Reservation Database" is clearer than "DB-01".
2. **Write short descriptions:** Each element answers "what does it do?"; for containers you can add technology or storage type such as "Java/Spring Boot" and "PostgreSQL".
3. **Label relationships:** Describe the action and key protocol, such as "Sends booking request over HTTPS/JSON", rather than using blank arrows.
4. **Distinguish internal from external:** Keep boundaries clear; do not place a payment provider inside the box of software you manage.
5. **Maintain a single scope of observation:** Do not mix Java classes, servers, Regions, and external SaaS offerings as peer elements without explanation.
6. **Provide a legend when using colors or line styles:** Viewers should not have to guess whether green means "managed" or "secure".
7. **Favor readability over completeness:** Pick meaningful relationships; if too many lines cross, split the diagram or use supplementary views.

## 3. Level 1 — System Context: The System's Context

A **System Context diagram** places the *one software system under study* at the center, then identifies the **user roles** and **other systems** directly involved. This is the bridge between business requirements and technical architecture.

The Booking System example has three main interactions:

- **Customer:** Searches for and books spots, tracks status.
- **Operations staff:** Monitors bookings and handles support cases.
- **Payment Gateway:** Processes payment transactions requested by the system.
- **Email Provider:** Receives requests to send confirmations or notifications.

~~~mermaid
flowchart LR
    CUSTOMER["Person: Customer"]
    OPS["Person: Operations Staff"]
    BOOK["Software System: Booking System<br/>Search, book spots, manage status"]
    PAYMENT["External Software System:<br/>Payment Gateway"]
    EMAIL["External Software System:<br/>Email Provider"]

    CUSTOMER -->|"Search, book, and view status"| BOOK
    OPS -->|"Monitor and handle bookings"| BOOK
    BOOK -->|"Request payment via API"| PAYMENT
    BOOK -->|"Send confirmation email request"| EMAIL
~~~

*Illustrative diagram in Mermaid following the semantics of a C4 System Context; this is not the official C4 notation or a cloud deployment diagram.*

### What Should and Should Not Appear at Level 1

At Level 1, the **Booking System is a single box**. There is no need to know whether it runs Spring Boot, Node.js, Kubernetes, or which database it uses. Context also does not tell you how many API instances exist, which Region hosts them, or how subnets are arranged.

From this diagram, stakeholders can review requirements:

- Are customers allowed to book when the payment gateway is temporarily down? If so, what is the business state?
- What personal or payment information crosses into external systems? Is that data permitted to be transferred to third parties?
- Is delayed email delivery acceptable, and where do customers check confirmation results?
- Is there an operations group that needs different permissions from regular users?

Omitting a payment system or identity provider at Level 1 leaves security, data-protection, integration, and incident-handling decisions at later levels without a solid foundation. Conversely, Level 1 should not turn into a catalog of all infrastructure services.

### How to Define the "System" Boundary

The software system boundary should reflect the functional scope and ownership managed by a team or organization. For example, a platform might split "Booking System" and "Payment System" into two internal systems with separate lifecycles; in that case, the Payment System appears as a **related system** in Booking's Context. There is no rule that an organization must put its entire product into a single software system.

State clearly **which system is being zoomed into**, because the term "container" at Level 2 only has meaning within the scope of the chosen system.

## 4. Level 2 — Container: Application and Data Structure

Once stakeholders agree on the context, the **Container diagram** zooms into the Booking System to show the **application, storage, and processing units that have distinct responsibilities**.

In this example:

| Container | Responsibility | Illustrative technology | Architectural requirements |
|---|---|---|---|
| **Web App** | Displays search/booking UI and calls the API | Web SPA | User experience, session and data protection |
| **Booking API** | Authenticates, validates rules, and executes booking business logic | Java / Spring Boot | Stateless compute, transactions, concurrency control |
| **Reservation Database** | Persists booking state and durable outbox records | Relational database | Consistency, backups, recovery |
| **Outbox Publisher** | Publishes successfully written events to the queue | Worker/background process | Retries, preventing lost events |
| **Message Queue** | Holds pending notification messages for processing | Managed queue | Durability, retention limits, redelivery |
| **Notification Worker** | Consumes events and calls the Email Provider | Worker | Idempotency, retries, failure monitoring |

~~~mermaid
flowchart LR
    CUSTOMER["Person:<br/>Customer"]
    PAYMENT["External System:<br/>Payment Gateway"]
    EMAIL["External System:<br/>Email Provider"]

    subgraph BOOK["Software System: Booking System"]
        WEB["Container: Web App<br/>SPA"]
        API["Container: Booking API<br/>Java / Spring Boot"]
        DB[("Container: Reservation Database<br/>Relational DB")]
        PUBLISHER["Container: Outbox Publisher<br/>Background worker"]
        QUEUE[("Container: Message Queue<br/>Managed service")]
        NOTIFY["Container: Notification Worker<br/>Background worker"]

        WEB -->|"HTTPS / JSON"| API
        API -->|"Transaction: read/write booking and outbox"| DB
        PUBLISHER -->|"Read outbox, mark result"| DB
        PUBLISHER -->|"Publish event"| QUEUE
        QUEUE -->|"Deliver message"| NOTIFY
    end

    CUSTOMER -->|"Uses via browser"| WEB
    API -->|"Request payment over HTTPS"| PAYMENT
    NOTIFY -->|"Call email-sending API"| EMAIL
~~~

The diagram clarifies the **business processing path**: the Web App calls the Booking API; the API writes data inside a transaction. The notification event is written in the same transaction to the **outbox**, then the Outbox Publisher reads and publishes it to the queue; the Notification Worker processes it asynchronously. This is one design approach to avoid the situation where a database commit succeeds but event publishing fails, causing lost notifications.

The solution still requires **idempotency** rules because the publisher may re-send the same event and the queue may redeliver messages; the worker must not send the same email multiple times uncontrollably. Details of "how deduplication works" can be explained at the Component level or in processing-flow docs, rather than cramming them onto the Container diagram.

### Why Are Databases and Queues Treated as Containers?

In C4, databases and message queues are **data stores or infrastructure components with an independent role in the software system**, so they are usually represented as containers. This makes **state ownership** and access flows visible. However, C4 does not require a one-to-one mapping between a container and a single cloud service or physical instance:

- A Booking API container can run **multiple replicas** on VMs, Kubernetes, or a managed application platform.
- A database container can be deployed using a managed database service with replication and failover.
- A Message Queue container can be realized by a managed service with specific quotas and delivery semantics.

The container model describes **structure and responsibilities**; a deployment diagram adds **placement, counts, network connectivity, and redundancy**.

### Container Does Not Mean Microservice

Booking API can be a **modular monolith** containing several clearly separated business modules. Splitting every function into a separate microservice increases the number of APIs, network call paths, distributed transactions, monitoring resources, and operational overhead. You should split out another container only when there is a clear need around deployment lifecycle, data ownership, scalability, fault isolation, or team ownership.

## 5. Level 3 — Component: Responsibilities Inside a Container

At Level 3, we pick **a single container to zoom into**, such as Booking API. Other containers like the database or web app appear only as **dependencies outside the scope of the container under study**, even though they still belong to the same Booking System.

For example, splitting Booking API into the following components:

| Component inside Booking API | Responsibility | Key relationships |
|---|---|---|
| **Booking Controller** | Receives requests, validates format, and returns responses | Calls Booking Application Service |
| **Authentication & Authorization** | Verifies caller identity and checks permission to perform the action | Used as appropriate by controller/application service |
| **Booking Application Service** | Orchestrates the booking use case and transaction | Calls Availability Policy, Repository, Outbox Writer |
| **Availability Policy** | Evaluates business rules on spot availability | Does not decide final consistency solely from cache |
| **Reservation Repository** | Queries and updates bookings | Uses database and data constraints |
| **Outbox Writer** | Writes business events in the same transaction as the booking | Writes to database; publisher emits after commit |
| **Payment Gateway Adapter** | Standardizes calls to the external payment system | Hides provider protocol and SDK details |

~~~mermaid
flowchart LR
    WEB["External Container:<br/>Web App"]
    DB[("External Container:<br/>Reservation Database")]
    PAYMENT["External Software System:<br/>Payment Gateway"]

    subgraph API["Container: Booking API (Java / Spring Boot)"]
        CTRL["Component:<br/>Booking Controller"]
        AUTH["Component:<br/>Authentication & Authorization"]
        SERVICE["Component:<br/>Booking Application Service"]
        RULES["Component:<br/>Availability Policy"]
        REPO["Component:<br/>Reservation Repository"]
        OUTBOX["Component:<br/>Outbox Writer"]
        PAY["Component:<br/>Payment Gateway Adapter"]

        CTRL -->|"Check permissions"| AUTH
        CTRL -->|"Execute use case"| SERVICE
        SERVICE -->|"Evaluate rules"| RULES
        SERVICE -->|"Read/write booking"| REPO
        SERVICE -->|"Write event in same transaction"| OUTBOX
        SERVICE -->|"Request payment when needed"| PAY
    end

    WEB -->|"HTTPS / JSON"| CTRL
    REPO -->|"SQL / transaction"| DB
    OUTBOX -->|"SQL / transaction"| DB
    PAY -->|"HTTPS API"| PAYMENT
~~~

*Components are logical boundaries. They can be implemented as packages, modules, interfaces, or Java classes depending on how the code is actually structured. The diagram does not require each component to be a separate process or pod.*

### Expressing Transaction Boundaries Clearly

In this example, **Booking Application Service** orchestrates a single database-scoped transaction, including writing the booking and writing the outbox record. **Reservation Repository** must use appropriate concurrency control operations: unique constraints, conditional updates, locks, or an appropriate isolation level. Merely checking "availability" with a separate SELECT followed by an INSERT without database protection can cause double booking under concurrent requests.

Calls to the Payment Gateway go to an external system, so they **do not belong to the same local ACID transaction**. If a payment step is involved, the use case needs an explicit state model such as *pending payment*, *confirmed*, *expired*, *failed*, along with retry handling, webhooks, and the case where payment succeeds but the response is lost. Orchestration or compensation workflows may be needed instead of assuming a single transaction spans both systems.

The Component diagram lets engineers spot areas that need sharper specification:

- Who is responsible for limiting hold duration and resolving double bookings?
- Which component enforces authorization before reading someone else's data?
- Is the outbox event written before or after commit?
- Which business state does a payment failure translate into?
- Are controllers holding all the business rules, making logic hard to test and maintain?

## 6. Code, Dynamic, and Deployment Levels: Supplementing as Needed

C4 commonly presents the **Code level** as the fourth layer of detail, yet real-world systems also benefit from very useful **supplementary views**:

| View | When to use | Questions answered |
|---|---|---|
| **Code (Level 4, optional)** | A component has complex code structure that implementers need to align on | How do interfaces, classes, and modules collaborate? |
| **Dynamic diagram** | Booking, payment, retry, or recovery flows where interaction order matters | When does who call whom, in what order, and what are the failure branches? |
| **Deployment diagram** | Need to evaluate Regions, AZs, subnets, runtimes, replicas, cloud services, and failover | Where are logical containers deployed and how are they replicated? |
| **System landscape** | An organization has many interrelated software systems | How do organization-wide systems connect with one another? |

### Dynamic Diagram: Illustrating a Booking Flow

~~~mermaid
sequenceDiagram
    actor U as Customer
    participant W as Web App
    participant A as Booking API
    participant D as Reservation Database
    participant P as Outbox Publisher
    participant Q as Message Queue
    participant N as Notification Worker
    participant E as Email Provider

    U->>W: Confirm booking
    W->>A: POST /bookings (Idempotency-Key)
    A->>D: Transaction: check double-booking, write booking + outbox
    D-->>A: Commit succeeded
    A-->>W: Booking ID and status
    W-->>U: Display confirmation
    P->>D: Read unpublished outbox records
    D-->>P: Booking event
    P->>Q: Publish event (retryable)
    Q->>N: Deliver message
    N->>E: Request email send (deduplicated)
    N-->>Q: Ack after completion
~~~

This is a simplified **happy path**, not yet showing all error states. During review, you must add scenarios where the database rejects a duplicate booking, HTTP times out after commit, the publisher/queue is interrupted, or the Email Provider returns an error. Those branches can be shown in separate sequence diagrams or use-case specs; they do not all belong on the Context diagram.

### Deployment Diagram: Connecting C4 to the Cloud

An illustrative deployment on a cloud platform:

~~~mermaid
flowchart TB
    USER["Users / Internet"] --> EDGE["CDN, DNS, edge protection"]
    EDGE --> LB["Public load balancer"]
    subgraph VNET["Application private cloud network"]
        subgraph AZ1["Availability Zone A"]
            APIA["Booking API replica A"]
            WA["Notification Worker A"]
        end
        subgraph AZ2["Availability Zone B"]
            APIB["Booking API replica B"]
            WB["Notification Worker B"]
        end
        DB[("Managed relational database<br/>HA configuration as chosen")]
        QUEUE[("Managed message queue")]
        PUBLISH["Outbox Publisher<br/>With replacement/continuation mechanism"]
        LB --> APIA
        LB --> APIB
        APIA --> DB
        APIB --> DB
        PUBLISH --> DB
        PUBLISH --> QUEUE
        QUEUE --> WA
        QUEUE --> WB
    end
~~~

*This deployment diagram only illustrates two AZs for compute. Actual placement, redundancy, and failure scope of the database, queue, publisher, and external services must be verified against the specific cloud product and configuration. You cannot infer HA simply from a "managed" label.*

Here, you may choose to run Booking API on VMs, container orchestration, serverless functions, or a managed application service; that is a **deployment decision**, and does not necessarily change the name "Booking API" on C4 Level 2. If the architecture changes from one Booking API to multiple independent services, then the Container diagram must also be updated.

## 7. Connecting C4 Levels to Cloud Decisions

A clear design practice is to tie **each architectural question to the right view**, then record the decision in documentation or an ADR.

| Architectural question | Useful view | Decision or evidence |
|---|---|---|
| Who uses the system, who processes payments, what data leaves to partners? | Context | List of actors, external systems, data flows, and integration responsibilities |
| Should notification processing be decoupled from the booking request? | Container and Dynamic | API, queue, worker, outbox; retries and business state |
| Who guarantees no double bookings? | Component and data design | Transactions, constraints, concurrency control |
| Run the API on VMs, a container platform, or serverless? | Deployment, non-functional requirements, and ADR | Latency, load, operational skills, cost, scaling capability |
| Can the system recover if one AZ fails? | Deployment and fault analysis | Dependencies, failover, AZ-loss testing, RTO/RPO |
| Which database is the API allowed to access? | Container, Deployment, and security view | Network policies, IAM, secrets, and audit logs |
| Will booking events be lost if the queue fails? | Dynamic, Component, and ADR | Outbox, replay mechanism, backlog monitoring |
| Where do costs come from? | Deployment, cost view, and cloud reports | Compute, database, queue, logs, networking, backups, cost allocation |

**The C4 levels do not replace non-functional design.** A line "Booking API → Database" tells you there is a dependency, but does not tell you whether the connection is encrypted, whether the database has a replica, what the p95 query latency is, whether the connection pool will saturate, or what cross-Region data transfer costs.

### Scalability and the Logical–Physical Distinction

On C4 Container, Booking API can appear as **a single box** even when it actually runs many stateless replicas. If the API keeps session state in the RAM of a single replica and requires users to always hit that exact replica, scale-out/failover capability is restricted. That detail belongs in a "stateless compute and externalized state" decision, not by renaming the container after the replica count.

Similarly, when scaling up API replicas, limits in the database, payment gateway, and queue can still become bottlenecks. You need concurrent load testing, connection pool management, quotas, rate limits, backpressure, and p95/p99 latency observation. The C4 diagram gives you the baseline list of dependencies to measure.

### Security and Trust Boundaries

Once you have Context and Container diagrams, mark every point where data crosses a boundary:

1. From the Internet/browser into the Web App and Booking API: authentication, abuse protection, session/token protection.
2. From Booking API to the database: workload identity, least privilege, network controls, and encrypted connections.
3. From Booking API to the Payment Gateway: partner verification, webhook/callback authentication, avoiding logging secrets and sensitive payment data.
4. From Notification Worker to the Email Provider: limiting shared data, secrets, retries, and deduplication.
5. From components to observability systems: protecting logs from containing tokens, secrets, or unnecessary personal information.

If a cloud provider offers IAM, private endpoints, network segmentation, and encryption services, those capabilities implement **controls**; they do not make the whole flow automatically secure if permissions or usage are misconfigured.

## 8. From Diagrams to Decisions: Architecture Decision Record (ADR)

Diagrams help people see structure, but rarely answer on their own **why Option A was chosen over Option B**. For decisions with significant trade-offs, write a concise **Architecture Decision Record (ADR)**.

Example for the booking system:

### ADR-001 — Asynchronous Confirmation Email Processing

**Context:** The Email Provider can respond slowly or fail. Users need to know the booking result immediately; state already committed successfully in the database must not be rolled back just because email is slow.

**Options:**

- **A. Send email synchronously inside Booking API:** Fewer components; however, requests depend on the latency and availability of the email provider.
- **B. Write booking, push event to queue, then process via worker:** Decouples the email path; however, there is a risk of database write succeeding while queue publish fails if operations are not coordinated.
- **C. Write booking and outbox in the same transaction, publisher forwards event to queue, worker processes:** Adds outbox, replay, monitoring, and idempotency mechanisms, in exchange for reducing the risk of losing events after commit.

**Decision:** Choose **C** because the business requirement is fast confirmation of the booking transaction, while email is allowed to arrive later. Use the database as the source of truth; the worker must reprocess messages safely.

**Consequences:** Must monitor outbox publishing lag, queue depth, retry counts, and failure alerts. Users view booking status directly in the system rather than treating email receipt as the sole source of truth.

**Verification:** Simulate Email Provider failure, stop the publisher right after database commit, and redeliver duplicate messages; verify no booking is lost, events can be replayed, and unwanted duplicate sends are controlled.

**Related diagrams:** Context shows the Email Provider dependency; Container shows queue/worker/outbox publisher; Component shows Outbox Writer; Dynamic explains the write and publish sequence.

This ADR can lead to follow-up decisions: choosing which managed queue service to use, message retention duration, data protection strategy in emails, and alert thresholds. When a decision changes, update both the ADR and related diagrams so they do not contradict each other.

## 9. C4 and Well-Architected Reviews

Well-Architected frameworks help ask systematic questions. C4 helps list the right components and dependencies to review, though it does not by itself prove that the system meets quality targets.

| Pillar | What C4 makes visible | Questions that must be verified further |
|---|---|---|
| **Operational Excellence** | Containers, owners, dependencies, and processing paths | Are there logs, metrics, traces, runbooks, deploy/rollback procedures, and incident management? |
| **Security** | Actors, external systems, data flows, and processing scope | Are IAM/least privilege, network segmentation, encryption, authentication, and sensitive-data handling enforced? |
| **Reliability** | Dependency points that can cause cascading outages | Are there single points of failure? Do backups, failover, and drills meet RTO/RPO? |
| **Performance Efficiency** | Synchronous/asynchronous call paths and database access points | What are real load results for throughput, p95/p99, connection pools, and quotas? |
| **Cost Optimization** | Which application services and data stores must be deployed | Are compute, storage, network, log, and standby environment costs estimated and allocated? |
| **Sustainability** | Always-on workloads, background jobs, and data stores | Are right-sizing, autoscaling, data lifecycle policies, and idle-resource avoidance in place? |

For example, reference targets for a workload might be set at **99.9% availability**, **booking p95 under 500 ms** at expected load, **maximum RTO of 60 minutes**, and **maximum RPO of 15 minutes**. These are **illustrative assumptions**, not default targets. Metrics must be negotiated with the business, then measured against the real system via load testing and recovery drills.

A C4 diagram can point out where a system is prone to failure, but the answer to availability depends on **deployment configuration and verification results**. A database drawn as "managed" does not inherently achieve an RPO of 0; two API replicas do not guarantee survival when an AZ fails if they share a single point of failure.

### Requirement-to-Architecture Verification Matrix

| Requirement | Diagram level to show | Decision | Verification check |
|---|---|---|---|
| Never confirm two bookings for the same resource/time slot | Component: Booking Service + Repository; Container: DB | Transactions and constraints in the data model | Under two concurrent requests, only one valid transaction is confirmed |
| Email provider outage does not lose bookings | Context, Container, and Dynamic | Outbox + durable queue + worker | Disconnect Email Provider, replay, and verify the booking still exists |
| API scales out without losing sessions | Container and Deployment | Stateless API; session/token handled appropriately | Route requests across replicas, scale in/out |
| Only authorized users can view booking data | Context, Component, and security view | Object-level authorization, IAM, token protection | Cross-user access attempt is denied and audited properly |
| Easy to allocate application costs | Deployment and cost view | Resource tagging, environment/product boundaries | Reconcile billing reports by owner/workload |

## 10. Process for Creating and Maintaining Useful C4 Diagrams for a Team

An effective practical workflow:

1. **Define purpose and audience:** Is the diagram for explaining business flows, security review, or deployment decisions? Each purpose requires a different level of detail.
2. **Scope the software system:** Define the boundary and responsibilities of the system being described; list users and external systems.
3. **Draw Context first:** Focus on primary interactions, critical data crossing boundaries, and integration assumptions.
4. **Zoom into Containers:** Show runtime/storage units, responsibilities, key technologies, data-exchange directions, sync/async modes, and where state is owned.
5. **Choose which containers need Component diagrams:** Prioritize parts with critical business logic, high complexity, or security/consistency risk; you do not need to draw every container.
6. **Add Dynamic/Deployment views:** Use when failure flows, execution order, or mapping to cloud infrastructure affects decisions.
7. **Record ADRs and assumptions:** Capture rationale, alternatives, trade-offs, review triggers, and verification checks; link them to diagrams.
8. **Review across roles:** Product confirms business flows; backend confirms code responsibilities; platform confirms deployment; security confirms data flows and permissions.
9. **Update alongside system changes:** When adding or removing a container, changing dependencies, integrating a new partner, or adjusting boundaries, update the diagrams in the same architecture-change review cadence.

### Storing Diagrams as Code

Text-based diagrams (Mermaid or dedicated DSLs like Structurizr DSL) are convenient to store alongside architecture docs, inspect diffs, and review via pull requests. The benefit is real only if **element names and semantics stay consistent**, someone owns keeping the diagrams updated, and the review process catches actual drift.

For example, links between diagrams and ADRs can be kept in a table inside project docs:

| Element | Level | Related decision | Approver on change |
|---|---|---|---|
| Payment Gateway | Context | How payment states and webhooks are handled | Product + Backend + Security |
| Booking API | Container | Stateless compute, scaling limits, transactions | Backend + Platform |
| Notification Worker | Container | Retries, idempotency, notification SLA | Backend + Operations |
| Booking Application Service | Component | Booking responsibility and consistency rules | Backend |
| Reservation Database | Container + Deployment | HA, backups, schema, and RTO/RPO | Backend + Platform |

Not every organization needs this exact table. The value lies in **every diagram having a clear purpose and owner**, avoiding diagrams that look great at the start but quickly drift out of sync with the system.

## 11. Common Mistakes When Using C4

**Mistake 1 — Drawing everything in one diagram.** A diagram containing users, Java classes, Kubernetes nodes, databases, Regions, and firewalls is very hard to read. **Fix:** Separate Context, Container, Component, and Deployment according to the question at hand.

**Mistake 2 — Confusing a C4 container with Docker.** Viewers assume migrating from VMs to Kubernetes requires changing the entire logical structure. **Fix:** Define containers by application/data-store unit; record the execution mechanism in Deployment.

**Mistake 3 — Mixing components and microservices.** Representing every Java class as an independently deployed service, or conversely treating an external system as an internal package. **Fix:** Keep container boundaries intact and only zoom into components of the selected container.

**Mistake 4 — Omitting relationship direction or meaning.** A blank arrow "API ↔ Database" does not show who initiates access, reads or writes, or over what protocol. **Fix:** Label relationships and include only details that matter for the diagram's goal.

**Mistake 5 — A Context diagram that only lists internal microservices.** The picture loses users, business purpose, and external systems. **Fix:** Move internals down to Container; Context focuses on system scope and interactions.

**Mistake 6 — A Container diagram that omits where state lives.** The team overlooks transactions, session stores, queues, and single points of failure. **Fix:** Show data stores and key read/write flows along with the technologies or properties needing review.

**Mistake 7 — Treating a diagram as proof of security and HA.** Seeing a "Private Network" or "Multi-AZ" box and concluding the system is secure. **Fix:** Supplement with policies, infrastructure details, and real testing; distinguish assumptions from verified facts.

**Mistake 8 — Diagrams and actual code drifting apart.** A service has been split out while the diagram still shows it combined, or a new payment integration never appears. **Fix:** Tie diagram updates to architecture change reviews and ADRs.

**Mistake 9 — Overusing colors or vendor names.** Diagrams become hard to read and locked into specific products even while the logic is still portable. **Fix:** Prefer role-based names; include vendor/technology names only when they affect decisions.

## 12. Exercise: Draw C4 for a Ticketing System

A company wants to deploy a ticketing system on the cloud. Users search for events, hold seats briefly, pay, and receive an email. The system uses an external payment provider and an external email provider. The team currently has a web application, a Java API, and a relational database; email sending runs synchronously. During ticket-sale openings, API traffic spikes; if payment or email slows down, many requests time out.

**Practice requirements:**

1. **Context:** Draw ticket buyers, support staff, Ticketing System, Payment Gateway, and Email Provider. Mark which relationships carry sensitive data or third-party dependencies.
2. **Container:** Propose Web App, Ticketing API, Transactional Database, and—if justified—Queue + Notification Worker + Outbox Publisher. Explain why each task is synchronous or asynchronous.
3. **Component:** Zoom into Ticketing API as Ticket Controller, Ticket Purchase Service, Seat Allocation Policy, Reservation Repository, Payment Adapter, and Outbox Writer. Define consistency boundaries and seat-contention handling.
4. **Deployment:** Choose how to run the API in the cloud; clarify replica count, load balancing, networking, database HA, and observability. If using managed services, state the remaining responsibilities of the application team.
5. **ADR:** Write a decision on asynchronous email or seat holds; list at least two options, trade-offs, and verification methods.
6. **Well-Architected:** Identify one key risk for each pillar: reliability, security, performance, cost, and operations.

### Solution Evaluation Guide

| Criterion | Signs of a sound solution | Signs needing revision |
|---|---|---|
| Proper C4 scope | Context has people and external systems; Container has apps/data stores; Component has one container's logic | All element types mixed into a single level |
| Data consistency | Database guarantees no double-sold seats; hold duration and payment states are clearly specified | Relying solely on checks in cache or RAM |
| Error handling | Email failure does not lose transactions; retries and deduplication exist where needed | Synchronous notification sending makes critical requests depend on email |
| Scaling and HA | API instances are replaceable; database dependencies are measured; failover and backups are tested | Merely adding replicas while ignoring bottlenecks and single points of failure |
| Security | External data flows have authentication, authorization, and data protection | Diagram fails to identify who accesses sensitive data |
| Evidence-based decisions | ADR states rationale, alternatives, consequences, and measurements | Picking cloud services by product name without tying back to requirements |

### Self-Check Questions

- Why can Booking API running on 12 Kubernetes pods still be just **one C4 container**?
- If an external identity management system is added, which diagrams must be updated and why?
- Why does the database appear at Level 2, whereas Reservation Repository appears at Level 3?
- Why is a Context diagram insufficient to prove RTO/RPO targets?
- If you migrate from a self-managed database to a managed database while business logic and application boundaries stay the same, which diagram level needs the most updates?
- When the Container diagram and an ADR describe two different event-publishing approaches, how should the team resolve that inconsistency?

**Key takeaway:** C4 is an **architecture communication method organized by levels of zoom**. Context clarifies purpose and boundaries, Container clarifies application and data units, and Component clarifies responsibilities inside a single unit. Decisions around networking, compute, HA, security, cost, and operations must be anchored to those diagrams and verified through deployment design, ADRs, and real measurements.
