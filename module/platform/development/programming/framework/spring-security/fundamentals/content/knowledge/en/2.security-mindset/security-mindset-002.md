# Threat Modeling and Attack Surface Identification

An application can use Spring Security, HTTPS, and properly hashed passwords and still leak data if the development team misses an access path or an abuse scenario. **Threat modeling** helps answer the questions: what are we protecting; who can cause harm; what path do they take; what could go wrong; and how do we verify the protections?

This lesson uses **a hypothetical Spring Boot application** to practice this mindset. The goal is to build an attack surface map and an evidence-backed risk list yourself. The threats in the examples are **scenarios to verify**, not a conclusion that a real system currently has vulnerabilities.

## 1. Getting the Terminology Right

| Term | Meaning | Example |
| --- | --- | --- |
| **Asset** | Data, functionality, identity, or system capability that needs protection. | Order information, refund permission, webhook signing key. |
| **Threat actor** | A subject with the capability or motive to perform a harmful action. | External user, compromised customer account, compromised integration partner. |
| **Attack surface** | Total exposure points, functions, and channels an actor can interact with to affect the system. | REST APIs, login page, webhook endpoint, file upload, admin port, dependency/build pipeline. |
| **Entry point** | A specific path through which data or commands enter the system from a source. | POST /api/orders, message consumer, events from a partner service. |
| **Trust boundary** | A location where data/identity crosses between domains with different trust levels or privileges. | Browser → backend; API → database; external service → webhook. |
| **Threat** | A scenario in which an actor can harm an asset. | Customer A views Customer B's order. |
| **Vulnerability** | A specific weakness that makes a threat possible. | An endpoint fetching an order by ID without checking the owner. |
| **Risk** | The combination of likelihood and impact in a specific context. | Customer data leakage on a publicly accessible API. |
| **Control** | A way to prevent, detect, limit, or remediate impact. | Ownership check, rate limit, signature verification, audit log. |

**Threat modeling is different from running vulnerability scanners.** A scanner can detect outdated library versions or unusual HTTP configurations; it struggles to understand business rules like "a user may only read their own orders." Threat modeling requires understanding architecture, permissions, data, and misuse cases together.

**Attack surface does not mean only public APIs.** A message queue, scheduled job, imported file, internal-only admin API, or CI/CD pipeline can still become a path to critical assets. You can reduce exposure points without eliminating all risk; the goal is to understand and control exploitable paths.

## 2. Starting with Assets and Protection Goals

Before counting endpoints, you must know **what will be affected** if an entry point is abused.

Suppose the order management system has the following assets:

| Asset | Key Protection Requirement | If Control Is Lost |
| --- | --- | --- |
| Customer profiles and shipping addresses | **Confidentiality** and owner-scoped access | Personal information leaked. |
| Orders, amounts, payment status | **Integrity** | Altering amounts or forging "paid" status. |
| Refund and role-update functions | **Authorization** and traceability | Unauthorized refunds or privilege escalation. |
| JWTs, session cookies, API keys, webhook signing keys | **Confidentiality**, proper lifecycle and revocation | Identity or partner request spoofing. |
| APIs and order processing queues | **Availability** and resource limits | Resource exhaustion, delayed order processing. |
| Logs/audit trail | **Integrity** and sufficient evidence | Unable to determine which sensitive operations occurred. |

Three foundational properties commonly used are **CIA**: Confidentiality, Integrity, and Availability. For business applications, you must also consider access control, action authenticity, traceability, privacy, and operational safety.

Ask concrete questions: "If Customer A knows Customer B's order ID, what must stop A from reading that data?"; "Who is allowed to mark an order as paid, and what proof is accepted?"; "What are the consequences of losing access control to an admin endpoint?". Questions about assets guide the search for attack paths instead of starting from a generic vulnerability checklist.

## 3. Defining Scope, Users, and Assumptions

A useful model must explicitly state its **scope**: the versions, environments, and components considered. For example:

- A Java 17+ and Spring Boot application with REST APIs for shoppers and admin staff.
- Browsers/mobile clients calling APIs through a reverse proxy or gateway.
- The backend using an order database, object storage for documents, and a message queue for asynchronous processing.
- A payment provider calling a webhook endpoint to report events.
- The backend potentially calling an external service to check shipping status.
- Monitoring/management endpoints and CI/CD existing with separate access scopes.

These are **assumptions for practice**; each project must replace them with actual diagrams, URLs, configurations, and deployment permissions. Record unverified items such as "are we sure the webhook is only callable from the provider?", "is the management endpoint behind the gateway?", "does the app use cookie-sessions or bearer tokens?". An unverified assumption must never be treated as a security control.

At the same time, identify **actors and capabilities**:

- Unauthenticated guest: can send requests to public paths, controls path, query, body, and many headers.
- Authenticated customer: has valid access to **their own** account but may try accessing others' IDs.
- Internal staff: holds certain privileges; must consider insider abuse or account takeover risks.
- Partner service: sends data to webhooks, may replay events or be spoofed if verification is weak.
- Automated processes and dependencies: hold access to data or infrastructure per configuration, adding supply/execution risk chains if compromised.

Never assume "inside the internal network" means always trustworthy: an internal account, workload, or host can also be compromised.

## 4. Drawing Data Flows and Marking Trust Boundaries

A data-flow diagram (DFD) helps visualize where data enters and crosses boundaries. A simple example:

~~~mermaid
flowchart LR
    U["Customer / browser"] -->|"HTTP request"| G["Gateway"]
    E["Payment partner"] -->|"Webhook"| G
    G -->|"HTTP"| A["Spring Boot API"]
    A -->|"Read/write orders"| D[("Orders DB")]
    A -->|"Upload/download"| F[("Object Storage")]
    A -->|"Order events"| Q["Message Queue"]
    Q --> W["Order Worker"]
    A -->|"HTTPS"| S["Shipping service"]
    OP["Operations staff"] -->|"Management access"| M["Management Endpoint"]
~~~

Each arrow represents **a flow to evaluate**, without implicitly assuming all components share the same trust level. Annotate zones such as Internet, gateway/DMZ, backend runtime, data stores, operations network, partner systems, and deployment channels. Some key boundaries:

1. **Internet → gateway/API:** user-supplied data; requires authentication, input constraints, authorization, and rate limiting.
2. **Partner → webhook:** receives messages from external systems; requires source/proof verification, integrity, expiration, and replay protection depending on protocol.
3. **Application → database:** the application can reach more records than a single user's permissions allow; permission controls must hold at the business layer, queries, and DB accounts.
4. **API → queue/worker:** messages may arrive late, duplicated, or out of order; the worker must not assume all payload fields are valid just because they came from the queue.
5. **Backend → external service:** must control destination URL/host, credentials, outbound data, timeouts, and returned results.
6. **Operations → management/CI/CD:** high-privilege path requiring identity, network, secrets, and change-log management.

**A trust boundary can exist inside the same process or system.** For example: an authenticated principal lacking refund permission; or a Service querying the DB with system privileges that must verify customer permissions per record.

For each arrow, record: source → target, data in transit, protocol, identity used, trust level, where authentication happens, where authorization happens, whether data is stored/logged, and what happens if data is modified, spoofed, replayed, or lost.

## 5. Building an Attack Surface Inventory

After the high-level diagram, create an **inventory** of entry points, exit points, privileged interfaces, and software supply paths. Example table:

| Exposure Point | Who Controls Input? | Related Data/Permissions | Verification Questions |
| --- | --- | --- | --- |
| GET /api/catalog | Internet users | Public product data | Could internal fields or customer data leak? |
| POST /api/orders | Logged-in customers | Price, quantity, buyer identity | Is client-sent price trusted? Is duplicate submission prevented? |
| GET /api/orders/{id} | Logged-in customers | Individual customer orders | Are owner/tenant checked per ID? |
| POST /api/payments/webhook | External service; could also be spoofed | Payment status | How are signature, timestamp, event ID, and idempotency verified? |
| POST /api/documents | Logged-in customers | Files and object storage | What are the limits on size, file type, and read-back permissions? |
| /api/admin/** | Staff and anyone able to send requests | Refunds, permission updates | Fine-grained authorization, audit logging, and confirmation for sensitive actions? |
| Consumer of orders.created | Producers and message broker | Order processing commands | How far are schema/producer trusted? How are duplicate events handled? |
| HTTP client calling external services | Backend, indirect user input | Egress network, partner tokens | Can destination URLs be manipulated into SSRF by users? |
| /actuator/** or management port | Ops network if configured properly | Health, metrics, operational info | Which ports and endpoints are actually exposed; is auth or network restriction applied? |
| CI/CD and artifact registry | Users with repo/build access | Deploy credentials, release rights | How are secrets, branch protection, dependencies, and supply chain managed? |

These are **candidates for investigation**; the table does not claim those endpoints exist or are vulnerable in any specific project.

Also examine paths **not going through Controllers**: scheduled jobs, WebSockets, GraphQL, batch CSV/Excel imports, file parsers, message listeners, RPC/gRPC, login callbacks, email links, static files, debug endpoints, health/metrics, caches/backups, container/admin consoles, cloud IAM, public object-storage ACLs, and internal microservice endpoints.

To build a real inventory, cross-check multiple sources: deployment diagrams, gateway/Ingress configs, route/controller lists, Spring SecurityFilterChain, OpenAPI/Swagger, actuator mappings if permitted, job/consumer definitions, dependencies, and external integrations. **Looking only at source code or only at public Internet URLs is not enough**, because reality can differ: routes mounted via a gateway, management running on a separate port, proxy path rewrites, or extra endpoints enabled by profiles.

## 6. Analyzing Threats with STRIDE

STRIDE is a set of prompting questions so common threat categories are not missed. Apply it **to each component and data flow** you drew, rather than merely ticking a checklist.

| STRIDE Category | Guiding Question | Example in the Order System |
| --- | --- | --- |
| **S — Spoofing** | Can someone impersonate a user, service, or partner? | Sending a webhook impersonating the payment provider. |
| **T — Tampering** | Can data/commands be modified without authorization in transit or at rest? | Client altering the amount when creating an order; modifying a queue message. |
| **R — Repudiation** | Can we determine who performed a sensitive operation? | Unable to tell which employee issued a refund. |
| **I — Information Disclosure** | Which data could leak to the wrong subject? | Customer A reading Customer B's order; tokens leaking into logs. |
| **D — Denial of Service** | Can any point be exhausted of resources? | Sending huge files, spawning excessive jobs, calling DB-heavy APIs. |
| **E — Elevation of Privilege** | Can a subject act beyond granted privileges? | Regular user invoking admin features; worker token holding overly broad privileges. |

STRIDE is a **threat-elicitation method**, not proof of a vulnerability. It can be combined with common API failure modes such as **BOLA/IDOR** (accessing the wrong object), **broken function-level authorization** (invoking a function outside one's role), mass assignment, SSRF, injection, misconfiguration, business-flow abuse, and missing resource limits. One risk may span multiple STRIDE categories.

Useful questions for each entry point:

- If changing **identity**: can the client spoof a user ID/role via headers or parameters?
- If changing **object**: can a record ID be swapped for another user's ID?
- If changing **state**: can an invalid state transition be requested or an event replayed?
- If changing **volume**: can huge, repeated, concurrent, or slow requests exhaust resources?
- If changing **data source**: are files, messages, or partner responses trusted excessively?
- If the user bypasses the official browser: does the API still enforce checks when called via scripts or other clients?

## 7. Deep Dive into Illustrative Attack Paths

### 7.1. Reading Another User's Order (BOLA/IDOR)

**Asset:** order details, addresses, transaction history. **Entry point:** GET /api/orders/{id}. **Actor:** logged-in user who only has rights to their own orders.

Scenario to examine: client changes {id} from A's order to B's order. If the server only verifies "logged in" and fetches the order by ID, authentication succeeds while **object-level authorization** fails.

Appropriate controls: retrieve user/tenant from the authenticated principal; Service queries by pair (orderId, ownerId/tenantId) or enforces permissions at the data layer; never trust client-supplied ownerId; restrict returned fields. Add a test where A logs in, requests B's order, and verifies **none of B's content is returned**, even when the ID exists. Return 403 or 404 depending on existence-hiding design, but stay consistent.

### 7.2. Spoofing or Replaying a Payment Webhook

**Asset:** payment status and amount. **Entry point:** POST /api/payments/webhook. **Boundary:** external provider → backend.

Scenario: the system relies on status=PAID in the body without verifying the message, or accepts the same event multiple times causing duplicate actions such as recording a transaction or refund twice.

Verify the signature/HMAC or provider-mandated mechanism, use the raw body when the signing spec requires it, check timestamp/expiration and event ID, store idempotent processing state, verify amount/currency/order reference against server-held data, and validate allowed state transitions. **IP allowlisting alone, HTTPS alone, or obscure paths alone are usually insufficient** to prove message authenticity.

Testing: invalid signature, stale event, duplicate event, transaction referencing nonexistent order, mismatched amount, out-of-order events.

### 7.3. Calling User-Supplied URLs (SSRF)

**Asset:** internal metadata, tokens, non-public network resources. **Entry point:** backend feature fetching images/documents from a submitted URL.

Scenario: the backend can reach internal systems; if a user controls the URL, the app can be turned into a proxy sending requests to addresses the user cannot reach directly.

Controls: ideally call only necessary business domains/destinations; validate scheme and host, check resolved IP addresses after DNS and on redirects, restrict egress at the network layer, enforce timeouts/response size limits; never send sensitive credentials to untrusted URLs. Blocking a few substrings in the URL is insufficient against DNS/redirect variants.

Safe-environment testing: valid URL; non-allowlisted domain; redirect leading to forbidden target; internal/metadata network addresses rejected.

### 7.4. Cookie-Sessions and State-Changing Actions

If the application uses cookies automatically sent with requests, an attacker may trick a user's browser into performing unintended actions. **CSRF** is a threat to evaluate against the specific authentication mechanism and client. Spring Security provides CSRF support, but the team must understand why it is enabled/disabled, how tokens are issued and sent, and how SameSite/Secure/HttpOnly apply to cookies.

Ask further: does the API use Bearer tokens explicitly placed in Authorization by JavaScript, or cookie-sessions? Are any POST/PUT/DELETE endpoints missing anti-forgery protection? Is browser CORS properly understood? **CORS does not replace CSRF or server-side authorization**.

### 7.5. File Uploads and Asynchronous Processing

An upload can exceed size limits, contain the wrong content type, exploit a parser, be stored in a public area, or be processed by a worker with higher privileges than the uploader. Queues introduce further issues: retries, duplicates, poison messages, resource congestion, and out-of-order events.

Enforce size/count limits, verify file type by content when appropriate, store in isolation, use least-privilege storage permissions, scan/process in a restricted environment, cap retry counts, and route failing messages to a dead-letter queue per policy. Workers must validate data and business rules for **the exact action the worker executes**.

### 7.6. Exposed Admin Paths or Operational Configurations

Admin and management endpoints must be identified per environment: which paths, which ports, who can connect, and which middleware protects them. Spring SecurityFilterChain protecting a set of application URLs **does not automatically prove** that a separate management port, another proxy, or an infrastructure console is similarly protected.

Limit exposed features to what is needed, enforce authn/authz and network policies, manage secrets/roles with least privilege, monitor configuration changes, and apply patches. Also protect deployment pipelines because CI/CD credentials may grant enough rights to alter the application even when the API itself is well protected.

## 8. From Threats to a Verifiable Control Plan

A list of "possible attacks" is only useful when linked to consequences, controls, and a concrete verification method. A **risk register** can be used:

| ID | Scenario / Boundary | Assumed Likelihood & Impact | Required Control | Verification Evidence |
| --- | --- | --- | --- | --- |
| TM-01 | A reads B's order via API | High likelihood if owner check is missing; high impact | Owner/tenant authorization in Service | Cross-user/cross-tenant tests, verify response leaks no data |
| TM-02 | Spoofed webhook confirms payment | High impact; likelihood depends on current verification | Signature, timestamp, idempotency, reconciliation | Invalid signature, replay, and amount mismatch tests |
| TM-03 | URL import calls internal network | Depends on user URL input and egress config | Target allowlist, block internal IPs, network egress policy | Redirect/DNS/forbidden-address tests |
| TM-04 | Upload flood exhausts resources | Depends on rate limits, quotas, and workload | Size limit, quota, timeout, backpressure | Authorized load test, resource metrics |
| TM-05 | Admin/management exposed | High impact; likelihood depends on network and privileges | Network restriction, authentication, authorization, audit | Probe from external network zone, test low-privilege account |

**The ratings in the table are hypothetical for learning purposes.** To prioritize in practice, you must know what is reachable, exploitation conditions, exploitability, affected data, existing controls, and business needs. Do not turn placeholder assumptions into "standard risk scores."

A pragmatic prioritization scheme:

- **Very high priority:** reachable path, severe impact, missing critical control or evidence of exploitation.
- **High priority:** major impact, though certain conditions/controls reduce likelihood.
- **Medium/low priority:** harder-to-reach path, less sensitive asset, or limited impact, yet still requires an owner and review schedule.

Impact should consider **confidentiality, integrity, availability, financial, legal, and customer harm**. When data is insufficient to rank, mark **"needs verification"** rather than guessing. Each item should have an owner, treatment direction (mitigate, approve-and-accept, transfer, or remove feature), status, and re-verification date.

## 9. Which Part Does Spring Security Support in This Model?

For Spring MVC/Servlet applications, Spring Security organizes authentication and authorization around **SecurityFilterChain**. It can help authenticate HTTP requests, restrict routes by role/authority, protect against CSRF as configured, manage SecurityContext, and apply method security. These mechanisms act as **controls** for some of the identified threats.

Illustrative configuration setting URL policy. This is **a configuration snippet for a Spring Boot application that already has the Spring Security dependency**, not a standalone Java program:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/catalog/**").permitAll()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .requestMatchers("/api/orders/**").authenticated()
        .anyRequest().denyAll()
    );
    return http.build();
}
~~~

The classes in this snippet come from Spring Security: HttpSecurity, SecurityFilterChain, and HttpMethod from Spring Framework. **The code only expresses path access policy**; it does not provide login mechanisms, tokens, user stores, object permissions, webhook verification, network controls, or protection for ports outside the configured filter chain. Authentication mechanisms must be configured to match the client type; keeping default CSRF or adjusting it must align with the actual threat model.

In the example above, `authenticated()` on `/api/orders/**` **does not guarantee** User A cannot read Order B. A data-level rule is needed:

~~~text
Authenticated identity: customerId = A
Request: GET /api/orders/42
Service lookup: orderId = 42 AND ownerId = A
If not found or not permitted → do not return order 42 data
~~~

Similarly, `hasRole("ADMIN")` alone cannot prove that employee is allowed to refund a specific order in every state. Object-level, state, and context rules usually belong in the Service/domain layer; method security can assist when appropriate. Note that self-invocation can bypass Spring proxies when enforcing method-level controls, so test through the actual application call path.

A good threat model helps **choose the right control**; it does not require mechanically adding filters or annotations to every method.

## 10. Java 17 Example: Recording Flows Crossing Boundaries

To avoid staying purely theoretical, you can write a small program representing a **static inventory** of the hypothetical system. The following program does not scan networks, detect vulnerabilities, or automatically decide which flows are dangerous; it simply prints the points to review.

Save as **SurfaceInventory.java**:

~~~java
import java.util.List;

public class SurfaceInventory {

    record Flow(
        String interfaceName,
        String sourceZone,
        String targetZone,
        String data
    ) {}

    public static void main(String[] args) {
        List<Flow> flows = List.of(
            new Flow("GET /api/orders/{id}", "Browser", "API", "Order details"),
            new Flow("POST /api/payments/webhook", "PaymentPartner", "API", "Payment event"),
            new Flow("EVENT orders.created", "Queue", "Worker", "Order event"),
            new Flow("SQL orders lookup", "API", "Database", "Order records"),
            new Flow("GET /actuator/health", "OpsNetwork", "Management", "Health data")
        );

        for (Flow flow : flows) {
            System.out.println(
                flow.interfaceName() + " | "
                + flow.sourceZone() + " -> " + flow.targetZone()
                + " | " + flow.data()
            );
        }
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac SurfaceInventory.java
java SurfaceInventory
~~~

**Exact stdout output:**

~~~text
GET /api/orders/{id} | Browser -> API | Order details
POST /api/payments/webhook | PaymentPartner -> API | Payment event
EVENT orders.created | Queue -> Worker | Order event
SQL orders lookup | API -> Database | Order records
GET /actuator/health | OpsNetwork -> Management | Health data
~~~

From the output, add **human analysis**: is each sourceZone trustworthy, who controls the input, what is protected at targetZone, possibilities of spoofing/tampering/replay/DoS, authorization logic, and negative tests. In real work, the inventory should include verified data from source code and deployment configs; never treat a hardcoded list like this as evidence of the actual system.

## 11. Concise Threat Modeling Workflow for a New Feature

Apply the following loop to the "customer creates and views orders" feature:

1. **Lock scope:** release version, related endpoints/tasks, environment, and what is out of scope.
2. **Identify assets:** order data, accounts, money, secrets, processing capacity, and logs needing protection.
3. **Draw flows:** client → gateway → API → DB/queue/third-party; annotate where permissions and trust levels change.
4. **Inventory the surface:** every method/path, body, file, header, callback, consumer, admin port; verify against real deployment.
5. **Find failure scenarios:** apply STRIDE and abuse cases like swapping IDs, altering prices, spoofing webhooks, replays, flooding, calling out-of-role functions.
6. **Prioritize and assign ownership:** describe impact, preconditions, existing controls, owner, priority, and items lacking evidence.
7. **Implement and verify:** deploy appropriate controls, add negative tests, monitor logs/metrics, and revisit on architectural changes.

**Template for recording a complete threat:**

~~~yaml
id: TM-ORDERS-001
asset: Customer order details
entry_point: GET /api/orders/{id}
actor: Authenticated user without ownership
trust_boundary: Browser -> API -> Order data
threat: Read another customer's order by changing the order ID
preconditions: Endpoint accessible to logged-in users
impact: Unauthorized exposure of order and address information
controls:
  - Authorize by current principal and order owner/tenant
  - Limit fields returned in the response
verification:
  - User A requesting User B's order receives no B data
  - Cross-tenant access is also denied
owner: Order API team
status: Proposed; confirm against the deployed implementation
~~~

The values above describe a **hypothetical exercise**, not confirmed findings in any specific system. When documenting a real project, replace them with actual evidence, tasks, and owners.

## 12. Boundary-Based Negative Testing Matrix

A simple way to turn a threat model into action is building a **who → does what → on which resource → expected outcome** matrix:

| Subject / Scenario | Test Action | Secure Expectation |
| --- | --- | --- |
| Unauthenticated | View another user's private order | Do not return order content. |
| User A | View/edit an order belonging to User B | Deny access or modification. |
| User A | Submit arbitrary high/low `totalAmount` field | Server calculates/validates price from trusted source per business rules. |
| Regular user | Call admin-only refund endpoint | Denied with no side effects. |
| Webhook without valid signature | Report order as paid | Do not update payment status. |
| Valid webhook with duplicate event ID | Replay event | Do not perform duplicate business side effects. |
| Oversized or wrong-type file upload | Submit file | Bounded/controlled, does not exhaust resources. |
| URL import pointing outside allowed target | Ask backend to fetch content | Do not call forbidden target. |
| Outside ops network | Access dedicated management endpoint | Do not leak info or operational privileges. |

Tests should target the **real call path**: HTTP + filter chain + Service + data/permissions, or message listener/worker when the entry point is not HTTP. Testing "returns 403" is insufficient if the system already performed mutations before returning the error; verify DB state, messages, transactions, and related logs.

Use authorized test environments, accounts, and test data; never put real accounts, real tokens, or sensitive information into tests or captured result logs.

## 13. Signs a Threat Model Is Incomplete

- Inventorying only **GET/POST Controllers** while forgetting queues, files, admin ports, CI/CD, and third-party systems.
- Marking only "logged in" while ignoring **per-object, per-tenant, and per-action permissions**.
- Writing "Spring Security is enabled" as the answer to every threat without specifying matchers, policies, trust boundaries, and tests.
- Assuming JSON from an internal Service or messages from a queue are automatically trustworthy.
- Mixing unverified assumptions with confirmed evidence; failing to record sources, owners, or versions.
- Marking all threats as "high" or using arbitrary scores without considering assets and reachability.
- Listing only technical vulnerabilities while ignoring **business-flow abuse** (swapping owners, duplicate refunds, invalid states).
- Testing only the happy path; lacking tests for low privileges, different-owner objects, spoofed/duplicate messages, or extreme inputs.
- Doing it once and abandoning it: new features, new routes, new integrations, changes to cookie/JWT usage, or network segmentation all require **reviewing the model again**.

## 14. Practice Exercise

Pick a feature with at least **two roles** and **one sensitive asset** (e.g., customer viewing orders and admin issuing refunds). In 30–45 minutes, produce the following artifacts:

1. A diagram showing client, API, data store, and at least one trust boundary.
2. A table listing each entry point, who controls identity/inputs, and affected assets.
3. At least three STRIDE scenarios or abuse cases **with explicit preconditions, consequences, and assumptions**.
4. For each scenario, one concrete control and one executable negative test.
5. A list of unknowns to ask DevOps, QA, or business owners before prioritizing.

Self-evaluate with three questions: **(1)** Are there any paths entering the system without going through a Controller? **(2)** Where is a user "validly logged in" yet still not permitted to access the resource? **(3)** Which controls have **test evidence**, and which are still assumptions?

## Conclusion

Threat modeling starts from **assets and data flows**, uncovers **exposure points and trust boundaries**, and then hypothesizes how identities, data, or privileges could be abused. Spring Security helps enforce many authentication and authorization controls, yet business policies, object-level permissions, integrations, infrastructure, testing, and operations still require deliberate review. The ultimate value of threat modeling is an **actionable, verifiable risk map** kept up to date as the application evolves.
