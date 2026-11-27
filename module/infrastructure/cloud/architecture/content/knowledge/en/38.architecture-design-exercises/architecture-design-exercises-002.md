# Building Context, Deployment, and Data Flow Diagrams

> **Scope:** A design exercise in **CLOUD_ARCHITECTURE**. Learners translate business and non-functional requirements into three verifiable architectural views: a **context diagram**, a **deployment diagram**, and a **data flow diagram**. The focus is on justifying networking, compute, data, and deployment model choices, as well as trade-offs across reliability, security, scalability, cost, and operations using Well-Architected thinking.

## 1. Why Does the Same System Need Multiple Diagrams?

A single diagram usually cannot simultaneously explain to a product owner who the system talks to, show infrastructure engineers which network zones machines run in, and show security teams how sensitive data crosses trust boundaries. When you try to cram every detail into one picture, readers easily miss assumptions or mistakenly assume one connecting line explains every kind of interaction.

Three diagrams answer three different questions:

| View | Question to answer | Main elements | Primary audience |
|---|---|---|---|
| **System context** | Who does the system serve, which systems does it interact with, and where do responsibility boundaries lie? | Users, target system, external systems, relationships | Product owner, architects, security, partners |
| **Deployment** | Where do components run, on what resource types, and how are network/fault zones connected? | DNS, ingress, subnets, AZs, workloads, DB, queues, network paths, fault domains | Cloud architect, platform engineer, SRE |
| **Data flow** | What data is created, read, written, and moved where; who is authorized to receive it? | Actors, processing steps, data stores, data flows, trust boundaries | Backend, data engineer, security, compliance |

The context diagram shows **the system as a black box**. The deployment diagram opens the black box by showing where runtime components live and how they connect. The data flow diagram opens the black box by tracing **how data travels and transforms**. All three views must use the same system name, the same partners, and have no behavioral contradictions.

### 1.1. Learning Outcomes

After this lesson, learners can:

- Choose the right scope, target audience, and level of detail for each diagram.
- Gather requirements and determine system boundaries before selecting cloud services.
- Draw three linked diagrams of a multi-component application using a readable notation such as Mermaid.
- Trace a business journey across all three diagrams, from actors through workloads, databases, queues, and partners.
- Mark network boundaries, identities, sensitive data, single points of failure, recovery paths, and assumptions requiring validation.
- Defend design decisions against Well-Architected principles, articulating trade-offs among scalability, security, reliability, cost, and operational complexity.

## 2. Conventions: What to Draw, and at What Level?

In this lesson, a **system** is a software product with defined business responsibilities, such as an ordering system. A **component** can be an API, worker, data store, or gateway. A **deployment node** hosts one or more components at runtime, such as a container service in an availability zone (AZ). A **data flow** represents information being transmitted or stored, not merely a network connection.

### 2.1. Boundaries and Notation

No single notation standard fits every organization. Place a **legend** or brief note beside the diagram specifying:

- Person/box labeled **Actor**: direct user or actor.
- Box **System**: the system owning the business capability; **External System** box: partners/systems outside the design scope.
- Container **Cloud/Region/VPC/Subnet/AZ**: deployment location or boundary, not automatically an authorization boundary.
- Cylinder **Data Store**: persistent storage; queues are drawn separately because they carry messaging semantics.
- Arrows labeled with **protocol names** in deployment diagrams or **data names** in data flow diagrams.
- Box or dashed boundary **Trust Boundary**: where trust levels, administrative ownership, or authentication mechanisms change.

The context diagram can follow C4 System Context style; the deployment diagram corresponds to the C4 Deployment view; the data flow diagram can follow Level 0/1 DFD. These are **complementary views**—there is no need to force every notation into a single rigid standard. Focus on consistent naming and clear edge meanings.

### 2.2. Things a Diagram Does Not Prove on Its Own

- Drawing two instances across two AZs does not prove the application fails over automatically or that the database replicates accurately.
- Drawing a database in a private network does not prove the application cannot leak data via a public API.
- Drawing a TLS line does not prove secrets are protected everywhere at rest or that principals follow least privilege.
- Drawing a one-way arrow does not prove the actual protocol has no response; many protocols require a return path within the same session.
- Drawing a backup icon does not prove RTO/RPO can be met without recovery drills.
- Drawing a queue does not automatically guarantee exactly-once delivery or atomic writes between orders and events.

A diagram is a **model for discussion and verification**. Real capability must be confirmed through configuration, testing, metrics, and operational procedures.

## 3. Running Case Study: An Online Ordering System

A hypothetical enterprise is building the **MâyShop Order** system for customers to place orders via a website. The system must manage shopping carts, create orders, receive payment results, update order status, and send confirmation emails. Inventory is managed by the enterprise's ERP system; payments and email delivery are handled by two external providers.

> **All numbers in this lesson are pedagogical assumptions** used to practice architectural decisions; they are not performance commitments or default recommendations for a production environment.

### 3.1. Business Requirements

| ID | Need | Observable outcome |
|---|---|---|
| BR-01 | Customers browse products and create orders | System generates a unique order ID, displays total amount and status |
| BR-02 | Customers pay via a payment provider | Payment impact is recorded at most once per valid transaction |
| BR-03 | Receive asynchronous payment notifications | Duplicate or delayed callbacks/webhooks do not create duplicate orders or charges |
| BR-04 | Check and reserve inventory via ERP | Never confirm orders beyond agreed inventory rules |
| BR-05 | Send email after payment confirmation | Delivery attempts, failures, retries, and DLQ can be tracked |
| BR-06 | Support staff look up order status | Staff only view/modify data within their authorized scope |

### 3.2. Non-Functional Requirements and Assumptions

| ID | Sample requirement | Initial design implication |
|---|---|---|
| NFR-01 | Peak 300 API requests/second, with potential spikes during promotions | Separate scalable components; check DB and partner connections |
| NFR-02 | Order-creation API p95 ≤ 400 ms under defined load | Observe end-to-end latency; limit synchronous dependencies on the hot path |
| NFR-03 | SLO 99.9% valid requests succeed over a 30-day window | Track metrics per business journey, not just health checks |
| NFR-04 | Loss of one AZ does not stop the entire system | Distribute API/workers across multiple AZs; verify DB/ingress failover |
| NFR-05 | RTO ≤ 60 minutes, RPO ≤ 5 minutes for defined disaster scenario | Define scenario, backups/replication, and recovery drills |
| NFR-06 | Protect customer and order data; never write payment tokens to logs | Data classification, least privilege, encryption, and log controls |
| NFR-07 | Budgeted, cost-allocated by environment, with measurable cost per order | Monitoring/FinOps, selecting services fitted to workload size |

**Clarify scope before drawing:** MâyShop Order owns order data and payment orchestration, but does not own the payment provider's ledger. The ERP owns authoritative inventory counts. The email service is a message transport; receiving an "accepted" response from the provider does not mean the email reached the customer's inbox.

### 3.3. Catalog of Actors and Dependencies

| Consistent name | Within MâyShop Order scope? | Responsibility |
|---|---|---|
| **Customer** | No, end user | Browses, places orders, checks status |
| **Support staff** | No, end user | Looks up and handles support requests per role |
| **MâyShop Order** | Yes | Provides application, manages orders, orchestrates flows |
| **Payment gateway** | No, partner | Creates payment sessions and emits transaction statuses |
| **Inventory ERP** | No, separate enterprise system | Checks/reserves stock and tracks item availability |
| **Email provider** | No, partner | Accepts send requests and emits delivery status if supported |

Once the team agrees on this catalog, **do not arbitrarily rename items** to "Payment Service", "PSP", or "Gateway A" across different diagrams without a note. Consistent naming makes cross-diagram completeness checks straightforward.

## 4. Step 1: Building the System Context Diagram

A context diagram focuses on **relationships**. It should show one central node for MâyShop Order, user actors, and the external systems the product interacts with. Do not place containers, VPCs, databases, network ports, queues, or machine types in this diagram.

### 4.1. How to Build It

1. Write a one-sentence description: "MâyShop Order lets customers place orders online and track them, coordinating with payment, inventory, and email services."
2. Place MâyShop Order at the center; clearly draw the boundary of the system your team is responsible for building.
3. List users and partners that **directly interact** with the system; omit dependencies outside the current release scope.
4. On each connection, label a **business verb** and the data/value exchanged; avoid writing just "API."
5. Verify that every requirement BR-01 through BR-06 maps to a corresponding actor or dependency.
6. Add detail only when needed to clarify ownership or compliance boundaries.

### 4.2. Sample Context Diagram

~~~mermaid
flowchart LR
    C["Customer\nActor"]
    S["Support staff\nActor"]
    subgraph Bound["System boundary under design"]
        O["MâyShop Order\nOrdering system"]
    end
    P["Payment gateway\nExternal system"]
    E["Inventory ERP\nExternal system"]
    M["Email provider\nExternal system"]
    C -->|"Browse, place orders, view status"| O
    S -->|"Look up and support per permissions"| O
    O <-->|"Create session, receive payment result"| P
    O <-->|"Check / reserve inventory"| E
    O -->|"Request confirmation email delivery"| M
~~~

**How to read it:** MâyShop Order is the only system inside the team's design responsibility boundary. The payment gateway and ERP are not "inside the application" just because the application's API calls them. Bidirectional arrows depict business-level exchange, not an assertion that both directions share the same protocol or reliability.

### 4.3. Critique Questions for the Context Diagram

- The ERP belongs to the same enterprise but is operated by another team: who owns the SLA and interface changes? The diagram must treat the ERP as external to MâyShop Order.
- The payment gateway sends webhooks to the application: this is still an external-to-system-boundary interaction and should be shown even if it hits the same API.
- Customers are redirected to the partner's payment page: should we show a direct relationship between customer and partner? If the real journey involves a partner-owned redirect or iframe, you can add a "Customer ↔ Payment gateway" link and note responsibility when the user leaves your system.
- Email payloads contain order IDs and email addresses: where is the data processing agreement with the provider? This marks a data boundary to clarify in the DFD.
- Is an identity/SSO provider an external actor? Add it only if the application actually integrates with one—do not speculate.

A context diagram **passes review** when someone who knows nothing about infrastructure details still understands what value the system creates, who it communicates with, and which components lie outside direct control.

## 5. Step 2: Building the Deployment Diagram

A deployment diagram answers "**where does it run and how does it connect?**". Inputs are business journeys and NFRs for performance, HA, recovery, networking, and security. Never choose a service just because its icon looks nice or it is trendy; every block should trace back to a requirement.

### 5.1. Choosing the Layers to Represent

For MâyShop Order, the conceptual architecture includes:

- **Internet edge:** DNS, abuse protection/WAF or CDN where needed, public HTTPS ingress/load balancer.
- **Workloads:** API and workers running in a private application network, distributed across at least two AZs to avoid single-AZ dependence.
- **Business storage:** managed relational database with multi-AZ availability configured and verified—do not assume every DB deployment mode fails over automatically.
- **Asynchronous processing:** managed queue, workers processing events with idempotency, retries, and a DLQ.
- **External connectivity:** payment gateway, ERP, and email need appropriate outbound paths alongside identity controls and least-privilege access; payment webhooks enter via ingress.
- **Operations:** metrics, logs, distributed traces, audit logs, secret manager, backup/restore, and alerting.

Containers are not mandatory; VMs, serverless, or PaaS can all fit. In this example we choose a **container service** because we need to run the API and worker independently, scale with load, and manage rollouts. Actual compute choice must be evaluated against team skills, startup latency, cost, portability, and operational requirements.

### 5.2. Sample Deployment Diagram

~~~mermaid
flowchart TB
    Customer["Customer / Support staff"]
    DNS["DNS + HTTPS edge layer\nWAF/CDN if needed"]
    PSP["Payment gateway\nexternal system"]
    ERP["Inventory ERP\nexternal system"]
    Mail["Email provider\nexternal system"]
    Customer -->|"HTTPS 443"| DNS
    PSP -->|"Authenticated HTTPS webhook"| DNS
    subgraph Region["Cloud region - Production environment"]
        subgraph VPC["Application network / VPC"]
            LB["Public ingress / Load balancer"]
            subgraph AZ1["Availability Zone A"]
                API1["API container A\nprivate subnet"]
                W1["Worker A\nprivate subnet"]
            end
            subgraph AZ2["Availability Zone B"]
                API2["API container B\nprivate subnet"]
                W2["Worker B\nprivate subnet"]
            end
            EG["Controlled egress path\nNAT / private connectivity per target"]
        end
        Q["Managed queue + DLQ"]
        DB[("Managed relational DB\nMulti-AZ HA as configured")]
        Sec["Workload identity + Secret manager"]
        Obs["Logs / metrics / traces / audit"]
        Backup["Backups / DR plan"]
        LB -->|"Private API"| API1
        LB -->|"Private API"| API2
        API1 <-->|"Restricted DB connection"| DB
        API2 <-->|"Restricted DB connection"| DB
        API1 -->|"TLS + IAM / events"| Q
        API2 -->|"TLS + IAM / events"| Q
        Q -->|"Messages / pull"| W1
        Q -->|"Messages / pull"| W2
        W1 <-->|"State access"| DB
        W2 <-->|"State access"| DB
        DB --> Backup
        API1 -.-> Sec
        API2 -.-> Sec
        W1 -.-> Sec
        W2 -.-> Sec
        API1 -.-> Obs
        API2 -.-> Obs
        W1 -.-> Obs
        W2 -.-> Obs
        API1 --> EG
        API2 --> EG
        W1 --> EG
        W2 --> EG
    end
    DNS -->|"HTTPS / approved ingress"| LB
    EG -->|"HTTPS, identity, and timeouts"| PSP
    EG -->|"Approved integration link"| ERP
    EG -->|"HTTPS to email API"| Mail
~~~

**Legend and caveats:** This is a **conceptual deployment diagram**, not a diagram of exact route tables, subnet CIDRs, or vendor-specific endpoints. The database and queue are drawn at the regional-service level to avoid implying an icon sits in only one AZ. Actual deployment must verify each service's HA model, replication, access controls, and endpoint placement. The arrow from queue to worker shows logical message delivery; on many message brokers, the worker actively polls/pulls from the queue over TLS.

### 5.3. Companion Connectivity Matrix

The diagram shows only major links; a **network matrix** confirms where ports open and who can call whom:

| Source | Destination | Mechanism | Allowed conditions |
|---|---|---|---|
| Internet customers | DNS/ingress | HTTPS 443 | Public because customer-facing; enforces TLS and abuse controls |
| Payment gateway | Webhook endpoint at ingress | HTTPS 443 | Signature/request verification, replay protection, idempotency |
| Load balancer | API A/B | Private app port, e.g., 8080 | Accepts traffic only from approved ingress; uses health checks |
| API A/B and Worker A/B | DB | DB port, e.g., 5432 | Network policy + proper DB identity; never expose DB publicly |
| API | Managed queue | HTTPS/TLS or broker protocol | IAM/workload identity scoped to publish actions |
| Worker | Managed queue | HTTPS/TLS or broker protocol | IAM/workload identity scoped to consume/ack/DLQ |
| API/worker | ERP, payment, email | Agreed protocol, usually HTTPS | Controlled egress, timeouts, retries, and credentials |
| Workloads | Secret manager / observability | Protected endpoints | Least privilege, encryption, no secrets in logs |

**Network return traffic** normally follows stateful connection tracking—not every protocol requires opening a separate inbound rule. Actual configuration must verify security groups, firewalls, routes, DNS, private endpoints/NAT, and IPv4/IPv6.

### 5.4. Locating Trust Boundaries

On the deployment diagram, mark at minimum:

1. **Internet → ingress layer**: all requests are untrusted by default; require TLS, input validation, appropriate authentication/authorization, and abuse limits.
2. **Ingress → workloads**: expose only business routes; debug and admin ports must never appear on public ingress.
3. **Workloads → DB/queue/secrets**: never grant "all actions on all resources"; each workload has its own identity and narrow permissions.
4. **Workloads → partners**: data leaves the application's control domain; require contracts, error handling, data minimization, and auditability.
5. **Production ↔ staging/dev environments**: separate identities, data, secrets, and network boundaries; never share production keys with test environments.

Private IP addresses **do not automatically mean** the application has proper authorization, and TLS **does not mean** the caller is authorized. Both networking and IAM/authorization must be designed.

### 5.5. Fault Domains, Scaling, and DR Placement

A multi-AZ architecture must answer concretely:

- Are API and worker instances truly spread across two AZs, or could the scheduler pack them all into one?
- When one AZ fails, does the remaining AZ have sufficient minimum capacity? How long does scaling take, and can connection pools and DB limits handle it?
- Do the load balancer and health checks detect failed instances, stop routing traffic, and recover sessions cleanly?
- Does the database fail over across AZs according to its deployment mode? How do in-flight connections handle timeouts and retries?
- Do the queue and secret manager have SLAs and fault tolerance aligned with application targets?
- If an **entire region** fails, where are backups/replicas stored, who triggers DR, and have RTO/RPO been measured?

**Multi-AZ does not automatically equal multi-region DR.** If NFR-05 applies to a full-region disaster, the detailed diagram must add the DR region, protected backup locations, traffic failover paths, and data recovery mechanisms; the sample diagram only places a placeholder **"Backups / DR plan"** because a concrete option has not yet been selected.

### 5.6. Capacity Checks and Trade-Offs

Suppose the ordering API needs 300 requests/second at p95 ≤ 400 ms. You cannot derive container counts directly from that figure. Measure single-instance throughput at representative load, CPU, memory, DB connections, and wait times on the ERP and payment gateway; then add headroom for losing an AZ.

For example, if one container steadily handles **75 requests/second** under test conditions and the target per-instance utilization is **60%** of measured capacity, expected capacity is roughly **45 requests/second/container**. Serving 300 requests/second requires roughly **7 containers** under normal conditions, before accounting for traffic skew, AZ distribution, redundancy margins, and database limits. This is only a **capacity estimate**; validate with real load tests under a single-AZ failure.

Adding instances increases DB connections. If each instance opens up to 100 connections, eight instances could demand 800 concurrent connections, exceeding DB limits. Design pooling, scale caps, query patterns, and backpressure end-to-end.

## 6. Step 3: Building the Data Flow Diagram (DFD)

A data flow diagram answers "**what data passes through whom, how is it transformed, and where is it stored?**". In a DFD, edges carry **data labels** (such as "order ID + payment status"), not just "REST." Network ports, AZs, or machine types are usually not the main elements of a DFD.

### 6.1. Distinguishing Level 0 and Level 1 DFDs

- **Level 0 DFD (context-level DFD):** the system is a single overarching process surrounded by external entities and inbound/outbound data flows. It looks similar to a context diagram, but edge labels emphasize data exchanged.
- **Level 1 DFD:** decomposes the system into key business processes (P1, P2, P3...), data stores (D1, D2...), and flows between them. Decompose further to Level 2 if a complex process warrants deeper inspection.

For this exercise, the context diagram in section 4 serves as the system-level view; the **Level 1 DFD** below provides data depth.

### 6.2. Data Inventory and Classification

| Data | Primary source/destination | Sample classification | Handling rules |
|---|---|---|---|
| Order ID, line items, total amount | Customer → MâyShop Order → Order DB | Business; may link to customer identity | Validate, enforce owner-scoped access, retain per policy |
| Customer shipping details | Customer → MâyShop Order | Personal data (PII) | Encrypt in transit/at rest, restrict logging and read access |
| Transaction reference, payment status | Payment gateway ↔ MâyShop Order | Business-sensitive | Verify webhook origin, check amount/order, enforce idempotency |
| Reserved quantities and SKUs | MâyShop Order ↔ ERP | Operational data | Enforce reservation TTLs and release on cancellation |
| "Order paid" event | DB/outbox → queue → worker | Business | Handle duplicate delivery, include idempotency key |
| Email address and confirmation body | MâyShop Order → email provider | Contains personal data | Send minimal data needed; never include internal tokens |
| Logs/traces | Workloads → observability | Metadata; can leak sensitive info if logged carelessly | Mask PII/secrets, restrict access and retention |

**Do not collect raw payment card data** when the flow can be delegated to the partner using appropriate hosted fields/tokenization. Minimizing sensitive data passing through your system is a security and compliance architecture decision; verify the payment mechanism, responsibility boundaries, and applicable enterprise requirements.

### 6.3. Level 1 DFD for Order Creation and Email Delivery

~~~mermaid
flowchart LR
    C["Customer\nExternal entity"]
    P["Payment gateway\nExternal entity"]
    ERP["Inventory ERP\nExternal entity"]
    Mail["Email provider\nExternal entity"]
    subgraph Sys["MâyShop Order - application data zone"]
        A["P1 - Accept order\nand create payment session"]
        B["P2 - Verify webhook\nand update status"]
        D[("D1 - Order DB\norders + outbox")]
        X["P3 - Forward outbox\nevents to queue"]
        Q[("D2 - Queue / DLQ\nevents")]
        W["P4 - Send email\nand record result"]
    end
    C -->|"Cart, shipping address, order request"| A
    A -->|"Order ID, awaiting payment status"| C
    A <-->|"SKU, stock check/reserve request"| ERP
    A -->|"Order ID, amount, session request"| P
    P -->|"Payment session reference"| A
    P -->|"Webhook: transaction ID, status"| B
    A -->|"Write PENDING order and reference"| D
    B <-->|"Match order, update PAID once"| D
    D -->|"Unpublished outbox records"| X
    X -->|"Order paid event"| Q
    Q -->|"Message to process / retry"| W
    W -->|"Order ID, address, email content"| Mail
    W -->|"Delivery status / idempotency"| D
~~~

**How to read it:**

- P1 creates the order in a pending state, exchanges inventory checks, and requests a payment session. Reservation order, expiration TTLs, and error handling across ERP/DB/payment gateway must be explicitly specified in the execution flow.
- P2 processes asynchronous results from the payment gateway; it verifies signatures, expiration, transaction ID, amount, and valid state transitions before updating. **Never trust** a browser redirect alone as proof of payment.
- D1 stores orders and **outbox records** so that when the DB state transition commits, the outbound event is not lost if queue publishing fails midway. The transactional outbox pattern relies on a proper DB transaction and a replay/mark-sent mechanism.
- P3 pushes outbox records onto the queue. If publishing and marking sent are not atomic, events may be emitted more than once; consumers must be idempotent.
- P4 consumes messages and sends emails; retries are bounded, and a DLQ holds failed tasks for handling. The email itself might have been accepted by the provider before the worker lost the response; choose idempotency/deduplication based on provider capabilities and business requirements.

This is a **logical data model**, not a complete payment workflow definition. A real system may need provider reconciliation jobs, refund handling, reservation releases, cart updates, and email updates after delivery callbacks.

### 6.4. Security-Relevant Data Flows

For every arrow in the DFD, document:

| Arrow | Sensitive data? | Trust boundary | Controls to prove |
|---|---|---|---|
| Customer → P1 | May contain PII | Internet → application | TLS, auth where needed, validation, order-level authorization |
| P1 ↔ ERP | SKUs, reserved counts, order ID | Application → external enterprise system | Service identity, timeouts, bounded retries, duplicate-hold prevention |
| P1 → Payment gateway | Amount, order ID, minimal metadata | Application → provider | Credential protection, data checks, and contract compliance |
| Payment gateway → P2 | Transaction result | Provider → public ingress | Protocol-compliant signature/source verification, anti-replay, idempotency |
| P2 → D1 | Order and transaction state | Workload → persistent store | Write permissions, transactions, unique constraints, audit trail |
| D1 → P3 → D2 | Paid event | DB/outbox → broker | Scoped publish permissions, deduplication, PII protection |
| D2 → P4 → email | Address, confirmation content | Workload → email provider | Consumer permissions, redaction, retention policy, and delivery state |

**Special note:** a partner webhook URL usually must be public so the partner can call it. This intentional public exposure must appear in the deployment diagram and be marked as crossing a trust boundary in the DFD. An **intentional** public route differs from leaving a DB or admin endpoint publicly exposed.

### 6.5. Failure Scenarios That Make the DFD More Valuable

Consider three scenarios:

**Webhook delivered twice:** If P2 updates state using a conditional transaction (e.g., permitting PENDING → PAID only once) and writes the outbox record in the same transaction, the second delivery can safely return success without duplicate side effects. The system must still verify the partner transaction record and handle webhooks carrying differing statuses.

**DB commits successfully, but broker rejects the event:** If the API publishes directly after DB commit, a crash between the two operations can cause the confirmation email never to be sent. The outbox lets P3 scan and replay unacknowledged records. In return, you must operate a publisher, retry logic, outbox cleanup, and backlog monitoring.

**Email provider times out:** The worker does not know whether the partner received the request. Blind retries could send duplicate emails. Use a partner-supported idempotency key or appropriate deduplication/status lookup; if neither is possible, the design doc must explicitly record "at-least-once" semantics and possible duplicate delivery.

DFDs reveal where data originates and where state lives. A **sequence diagram** can be added to illustrate call ordering, timeouts, and retries, but it does not replace a DFD when reviewing overall data storage and trust boundaries.

## 7. Step 4: Cross-Checking the Three Diagrams

After drawing, run a **cross-view consistency** check. If the context diagram includes an email partner but the deployment diagram lacks egress to email, the architecture is missing a network path. If the DFD has an Order DB store but the deployment diagram lacks its storage location and backup policy, the design is not ready to implement.

### 7.1. Traceability Matrix from Requirements to Components and Evidence

| Requirement | Context diagram | Deployment diagram | DFD | Test / Evidence |
|---|---|---|---|---|
| BR-01 create order | Customer ↔ MâyShop Order | Ingress → API → DB | Customer → P1 → D1 | E2E order creation, unique order ID, accurate totals |
| BR-02, BR-03 payment | Payment gateway ↔ MâyShop Order | API outbound to payment gateway; webhook via ingress | P1 ↔ PSP, PSP → P2 → D1 | Signature verification, duplicate webhooks, invalid states, retries |
| BR-04 inventory | ERP ↔ MâyShop Order | API ↔ ERP link | P1 ↔ ERP | Reservations, TTL expiry, partner failures, count consistency |
| BR-05 email | MâyShop Order → email provider | Queue → worker → egress → email | D1 → P3 → D2 → P4 → email | Successful send, retries, DLQ, duplicate handling |
| NFR-02 performance | Customer journey | Load balancer, API scale, DB, external dependencies | Hot path P1 and background path P4 | Load test p95 and saturation monitoring |
| NFR-04 AZ fault tolerance | System service quality | Multi-AZ API/workers, DB HA, LB | Flow check when components fail | Single-AZ outage drill, data integrity and recovery time check |
| NFR-06 sensitive data | Partners and responsibility boundaries | IAM, TLS, private DB, secrets, audit | PII/credentials across processes and stores | Authorization tests, secret scans, log reviews |
| NFR-07 cost | Service scope and dependencies | Compute, DB, queue, egress, logs, backups | Event frequency/volume, retention | Tagging, cost reports, and cost per order |

**A helpful rule of thumb:** every component in the deployment diagram must serve at least one explicit requirement or control; every sensitive data flow in the DFD must have a corresponding deployment path and protection mechanism; every partner in the context diagram must appear on a designed integration path.

### 7.2. Walking Through a Concrete Journey

Use the **"successful order placement"** journey to read continuously across all three diagrams:

1. **Context:** Customer places an order via MâyShop Order; the system uses the ERP and payment gateway, then sends an email.
2. **Deployment:** HTTPS request hits ingress, routes to an API instance in one of two AZs; API calls DB/ERP/PSP; webhook from PSP enters ingress; worker consumes the queue and calls the email provider.
3. **Data:** P1 creates a PENDING order; P2 verifies payment and updates to PAID; outbox emits the event; P4 sends the email and records status.
4. **Verification:** Test duplicate requests, delayed webhooks, DB failover, queue backlog, single-AZ loss, and partner outages. Inspect metrics, traces, and logs linked by correlation ID across steps.

If a step in the journey **cannot be located on at least one diagram where it belongs**, something needs clarification. For example, if the diagram omits the inbound webhook path, networking teams can easily miss an authenticated route or open the wrong port.

## 8. Evaluating the Architecture with Well-Architected Right on the Diagrams

Well-Architected is a way of questioning the consequences of architectural decisions, not a set of decorative icons. Most cloud evaluation frameworks include pillars for operations, security, reliability, performance, cost, and sustainability; names and specifics may vary by platform.

| Perspective | Critique questions for the three diagrams | Example action |
|---|---|---|
| **Operational Excellence** | Are incident detection, tracking, and recovery flows drawn? Who owns each dependency? | Add observability, runbooks, owners, and alert testing |
| **Security** | Which boundaries does data cross? Which workloads can read the DB, queue, and secrets? | Isolate IAM per workload, dedicated webhook ingress, redact PII in logs |
| **Reliability** | Losing an AZ, DB, or PSP stops which journeys? Are queues, retries, idempotency, and DR in place? | Measure failover, backlog, RTO/RPO, and transaction compensation |
| **Performance Efficiency** | Does the API wait synchronously on ERP/PSP on the hot path? Are bottlenecks at the DB or connection pool? | Add tracing, bounded caching, timeouts, and per-tier scaling |
| **Cost Optimization** | What do multi-AZ, DB HA, NAT, logs, cross-AZ traffic, and storage retention cost? | Allocate costs, size redundancy to SLOs, track cost per successful order |
| **Sustainability** | Are there idle resources, redundant storage, overly long log retention, or duplicate processing? | Right-size capacity, set retention policies, eliminate wasted work |

### 8.1. Trade-Offs Without Absolute Answers

**Synchronous or asynchronous payment processing?** A synchronous path lets the app return quickly on session creation, but ties responsiveness to partner latency; asynchronous webhook processing confirms state from a more reliable signal, at the cost of needing idempotency and eventual consistency. Often both are combined: create sessions synchronously, confirm status via webhooks/reconciliation.

**Use a queue or call email directly from the API?** A queue decouples the API from email provider latency, enables retries, and smooths bursts; in exchange, it adds a broker, workers, message states, backlogs, DLQs, and operational overhead.

**Single region or multi-region?** Multi-AZ is standard to mitigate localized faults; cross-region DR handles a broader class of outages but introduces cost, replication, traffic-routing management, and data divergence risks. Decide based on RTO/RPO requirements and drill results, not a desire for "as many regions as possible."

**Shared DB or per-service DB?** A shared DB reduces initial setup work but couples teams and makes independent permissions and scaling harder. Splitting databases isolates data boundaries at the cost of synchronization and cross-service consistency work. A brand-new system does not always need to start as many microservices.

**Put every service in private subnets?** Internet-facing access still requires public ingress for customers and webhooks. Private placement fits DBs, workers, and admin UIs; true protection also demands IAM, authentication, authorization, and egress controls.

### 8.2. Writing Concise Architecture Decision Records (ADRs)

After a review, document at least two major decisions instead of letting "the diagram speak for itself":

~~~text
ADR-01: Decouple email delivery from the order-creation path
Context: The order-creation API needs p95 <= 400 ms under target load.
Decision: Record events via an outbox and forward to a managed queue;
          a dedicated worker sends emails with retries and a DLQ.
Trade-off: Higher operational cost/complexity; emails are not instantaneous.
Required evidence: Load tests, backlog metrics, publish-failure tests,
                   idempotency and delivery-status verification.
Owner / review date: ...

ADR-02: Run API and workers across at least two AZs
Context: Requirement to keep operating when one AZ fails.
Decision: Spread workloads and select an appropriate HA DB configuration.
Trade-off: Higher redundancy cost; must verify placement and failover.
Required evidence: AZ-loss drill, remaining throughput, transaction errors,
                   measured RTO/RPO for the defined scenario.
Owner / review date: ...
~~~

## 9. A Repeatable Practice Workflow

### Phase A: Gather and Lock Assumptions

Create a one-page brief capturing scope, key journeys, data types, stakeholders, three to five critical SLOs/NFRs, and unknowns. Label unverified assumptions—for example, "ERP allows 100 requests/second" or "payment gateway signs webhooks"—and never treat assumptions as facts while drawing.

### Phase B: Draw Context and Confirm Ownership

Start with one central system and direct actors. Verify with the product owner that connections reflect the business. If system boundaries shift, update the owner list and impacted NFRs.

### Phase C: Draft Deployment

Select compute, data storage, and ingress layers based on requirements. Add network paths, AZs, external services, security, observability, and DR. Every link must explain how it satisfies network rules, identity, and data protection. Distinguish conceptual design patterns from provider/region-specific SKUs once a vendor is chosen.

### Phase D: Draw the DFD from Business Journeys

Pick critical paths such as order creation and payment confirmation, breaking them into processes, input/output data, and data stores. Mark sensitive data and trust boundaries. Highlight async handoffs, non-atomic steps, or complex access checks with notes.

### Phase E: Cross-Check and Present Decisions

Use the requirements traceability matrix; ask infrastructure engineers where each DFD process runs, ask backend engineers to walk journeys across deployed services, and ask security where data enters/exits and what permissions apply. Record ADRs, open issues, owners, and test plans.

### 9.1. Suggested Submission Folder Structure

If managing documentation as code, you can organize diagrams in the project's architecture repository like this:

~~~text
architecture/
  README.md                   # scope, version, legend
  01-context.md               # context diagram + notes
  02-deployment.md            # deployment diagram + network matrix
  03-data-flow.md             # DFD + data inventory
  requirements-traceability.md
  decisions/
    ADR-001-async-notification.md
    ADR-002-multi-az.md
~~~

This is only a **suggested submission layout**, not an instruction to create extra files for this lesson. For the exercise, a single Markdown document containing all three diagrams and decision tables works fine.

## 10. Exercise 1: Completing a Context Diagram Yourself

**Scenario:** MâyShop Order adds a self-service customer return-request feature. The business uses an external shipping system to generate return labels and a customer care team to approve requests inside the system.

**Tasks:**

1. Identify two new actors/systems involved and each party's ownership scope.
2. Extend the context diagram with business data flows for "return request", "approval decision", "return tracking number", and "shipment status".
3. List at least three questions for the product owner before locking the context—such as who may request returns, who approves them, and which system processes refunds.
4. Explain why you do not draw the shipping partner's database directly inside MâyShop Order's boundary when that DB is partner-managed.

**Self-assessment criteria:** Out-of-scope systems are clearly marked; user roles are not confused with services; every link carries a business label; unresolved choices are logged as questions or assumptions.

## 11. Exercise 2: Adapting Deployment to Changed Requirements

**Scenario:** During a sale event, traffic jumps fourfold compared to the baseline case. Operations observes rising API p95 latency, the DB hitting its connection limit, and messages aging in the queue. Meanwhile, budget does not allow running every component across multiple regions.

**Tasks:**

1. Identify at least three likely bottlenecks on the deployment diagram. For each, specify a metric to confirm or refute the hypothesis.
2. Propose one way to scale the API, one way to protect the DB, and one way to clear worker backlog, stating the risk of each change.
3. Redraw or annotate the diagram to distinguish multi-AZ HA from regional DR; explain how NFR-04 is met and how NFR-05 will be tested.
4. Highlight resources requiring cost allocation: ingress, compute, database, queue, NAT/egress, logs, backups.
5. Describe a case where **adding more containers** makes the system worse and prove it using expected measurements.

**Hint:** A component's capacity cannot be evaluated in isolation. If you double API instances and multiply DB connection pools accordingly without scaling DB capacity, overall p95 can worsen. Consider concurrency limits, pooling, query optimization, backpressure, and removing unnecessary synchronous calls.

## 12. Exercise 3: Redrawing the DFD for Compliance Requirements

**Scenario:** The business must delete or anonymize customer contact details per applicable retention rules, while still retaining invoices and transaction records under separate business/legal retention periods. The email provider may retain sent content for its own retention window.

**Tasks:**

1. Classify data using the inventory in section 6.2 and map where each type resides: order DB, queue/DLQ, logs, backups, email provider.
2. Add a "request contact deletion/anonymization" flow to the DFD, showing processes for requester verification, data processing, and audit evidence storage.
3. Note cases where data cannot be deleted immediately due to valid retention obligations; distinguish deletion, anonymization, pseudonymization, and access restriction.
4. Specify how data in the DLQ, backups, and email provider should be handled or governed by matching retention policies.
5. Propose three tests covering permissions, data safety, and observability; avoid using real customer data in test reports.

**Note:** This exercise asks for a technical model supporting business-defined compliance requirements; actual retention and deletion policies must be confirmed by compliance owners for the specific jurisdiction and contracts.

## 13. Capstone Exercise: Defending the Design in Review

Imagine you are the architect presenting the MâyShop Order deployment plan to the product owner, SRE, security engineer, and finance. Prepare **a complete set of three diagrams** and short decision records. Minimum deliverables:

1. **Context diagram:** One primary system, two user types, three external systems; interaction labels and responsibility boundaries.
2. **Deployment diagram:** Ingress, API, workers, DB, queue, AZs, primary network paths, identities, secrets, observability, and DR; legend for public/private paths.
3. **Level 1 DFD:** Processes for order creation, payment verification, event publishing, email delivery; data stores, named flows, and trust boundaries.
4. **Traceability matrix:** At least six BR/NFR requirements mapped through blocks/flows and tests.
5. **Two ADRs:** One reliability decision and one data-handling or security decision; each includes trade-offs, metrics, and revisit triggers.
6. **Three failure scenarios:** Single-AZ loss, duplicate payment webhooks, and unresponsive email provider; specify affected flows, metrics observed, and recovery steps.

### 13.1. Questions Reviewers Might Ask

**Product owner:** When a customer sees a "payment successful" page before the webhook arrives, what status does the system display? Who explains discrepancies to the customer?

**SRE:** If one AZ fails during peak hour, does spillover traffic into the surviving AZ exceed DB or API capacity? Do we have test evidence?

**Security:** Why must the webhook be public? What authentication stops external actors from forging payment outcomes, and where are audit logs stored?

**Data engineer:** If the outbox publishes twice or the queue redelivers an event, will order status or emails be written or sent twice?

**Finance:** Why pay for DB HA and standby workers? How does this option's cost compare against the business's acceptable downtime loss?

**Architect:** From any node in the deployment diagram, can you trace back to a requirement—and from any piece of sensitive data, can you see every place it travels?

### 13.2. Suggested Grading Rubric

| Criterion | Max points | Signs of quality |
|---|---:|---|
| Accurate scope and system boundaries | 15 | External systems and internal modules are clearly separated |
| Context diagram with accurate actors/relationships | 15 | Complete business interactions, consistent naming |
| Sound deployment across network, compute, data | 20 | Covers AZs, ingress, private workloads, dependencies, HA/DR, and connectivity matrix |
| DFD covers critical flows, stores, and failures | 20 | Addresses callbacks, queues, sensitive data, idempotency |
| Cross-view traceability and test design | 15 | Clear chain: requirements → components → data → evidence |
| Well-Architected trade-off explanation | 10 | Addresses reliability, security, cost, performance, operations |
| Presentation and assumptions | 5 | Readable, clear legends, assumptions never stated as proven facts |
| **Total** | **100** | |

A polished diagram that lacks duplicate-payment handling, omits data boundaries, or makes false failover claims is not deployment-ready. Conversely, a diagram using simple shapes can still excel when boundaries, responsibilities, flows, and decisions are crystal clear.

## 14. Common Mistakes When Building the Three Diagrams

| Mistake | Consequence | Fix |
|---|---|---|
| Putting VMs, DBs, and subnets in the context diagram | Business stakeholders lose sight of responsibility boundaries | Keep one primary system box; move details to deployment |
| Deployment diagram lists service names without connections | Ingress, egress, sources/destinations, and protections remain unknown | Add arrows, protocols, boundaries, and a connectivity matrix |
| Labeling every DFD arrow "API" | Impossible to see what data leaves the system | Name the payload or information: order ID, status, email |
| Equating private subnets with complete security | Misses authorization flaws and internal app risks | Add IAM, authorization, secrets, and permission tests |
| Showing only the happy path | Misses retry storms, timeouts, and outage behavior | Annotate duplicate callbacks, failed queues, DB failover, DR |
| Drawing multiple AZs while forgetting DB/queues or capacity | False confidence in HA despite hidden single points of failure | Check every component and run an AZ-loss drill |
| Placing a backup icon and claiming RTO/RPO met | Lacks real restore evidence | Design recovery scenarios, measure, and run drills |
| Omitting measurement units or load assumptions | Cannot evaluate compute or cost choices | Record load profile, p95, SLO, window, region, and data sources |
| Changing a partner's name across diagrams | Hard to review and easy to drop flows | Use a shared naming catalog and traceability matrix |
| Failing to update diagrams after deployment | Operations runbooks or security reviews become inaccurate | Store diagrams as code with versions, owners, and review workflows |

## 15. Pre-Submission Diagram Checklist

### Before drawing

- [ ] Business goals, system scope, and owners are agreed upon.
- [ ] Non-functional requirements, assumptions, and unconfirmed items are documented.
- [ ] Sensitive data, partners, and responsibility boundaries are identified.

### Context diagram

- [ ] Shows the exact central system and necessary external actors/systems.
- [ ] Names and link labels express business activities understandable to readers.
- [ ] Avoids stuffing unnecessary deployment technologies.

### Deployment diagram

- [ ] Shows placement of compute, storage, ingress, queues, and critical dependencies.
- [ ] Shows network segmentation/fault domains and clearly marks public vs. private paths.
- [ ] Includes IAM/secrets, telemetry, and backup/DR aligned with NFRs.
- [ ] Includes a connectivity matrix and plans for testing performance, HA, and cost.

### Data flow diagram

- [ ] Process names begin with actions; data stores and external entities are clearly distinguished.
- [ ] Arrows carry data names and sender/receiver; trust boundaries are not hidden.
- [ ] Callbacks, retries, idempotency, failures, and sensitive data are analyzed.
- [ ] Temporary stores, logs, DLQs, backups, and third parties are accounted for.

### Cross-checking and operations

- [ ] At least one key business journey traces cleanly across all three diagrams.
- [ ] No critical component or link is unowned or appears in only one diagram.
- [ ] Major decisions state rationale, trade-offs, owners, and verification plans.
- [ ] Diagrams carry update dates, versions, and a process to revise as architecture evolves.

## 16. Key Takeaways

Cloud architecture design starts with **business needs and constraints**, followed by networking, compute, databases, and deployment choices. The context diagram answers **"who and which systems are involved?"**; the deployment diagram answers **"where do components run and how do they connect?"**; and the DFD answers **"how is data processed, stored, and exchanged?"**.

A useful set of diagrams must be consistent, readable enough for collaborative review, and precise enough to drive real tests. Quality is measured by whether readers can **trace from requirements to design decisions**, spot risks, and understand Well-Architected trade-offs—not by how many cloud service icons appear on the page.
