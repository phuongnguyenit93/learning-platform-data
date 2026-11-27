# ORDS, REST-Enabled SQL, and Boundaries with Spring Boot Applications

Oracle REST Data Services (ORDS) is a service tier running outside Oracle Database that provides an HTTP/REST interface for applications and tools to access Oracle data. ORDS can publish REST APIs backed by tables, views, PL/SQL handlers, or defined SQL queries. ORDS also provides REST-enabled SQL, allowing clients to submit SQL statements over HTTP within a permitted schema scope.

When a system already includes a Spring Boot application, clearly define which responsibilities belong to ORDS and which belong to Spring Boot. Both can receive HTTP requests and access Oracle, yet their architectural roles differ:

- ORDS is a database-adjacent integration layer, well suited for exposing data or database operations under a controlled REST contract, as well as supporting administrative tools and data integration.
- Spring Boot is an application tier, well suited for executing business logic, coordinating multiple systems, authenticating and authorizing by user/domain, managing workflows, and providing stable APIs for clients.
- REST-enabled SQL is a remote SQL access interface, not a complete business API. It must be tightly secured and enabled only for approved clients, schemas, and purposes.

An architecture can use ORDS standalone, Spring Boot standalone, or both together. The decision should rest on business ownership, security requirements, operability, and the API contract to be delivered.

## 1. What Is ORDS and Where Does It Sit in the Architecture?

ORDS is an Oracle middle tier deployed as a Java service that connects to Oracle Database via connection pools. Clients send HTTP requests to ORDS; ORDS authenticates, checks privileges, routes to a REST handler or REST-enabled SQL endpoint, executes the corresponding database operation, and returns an HTTP response.

General model:

    Web / Mobile / Integration client
                  |
               HTTPS
                  |
                  v
          Oracle REST Data Services
          +--------------------------+
          | Authentication          |
          | Authorization            |
          | REST routing             |
          | SQL / PL/SQL handlers    |
          | Connection pools         |
          +--------------------------+
                  |
          JDBC / database connection
                  |
                  v
             Oracle Database
          +--------------------------+
          | Tables / Views           |
          | PL/SQL packages          |
          | Schemas / Roles          |
          | Transactions             |
          +--------------------------+

ORDS can run independently of the database server and is typically placed behind a reverse proxy or load balancer. The database does not need to expose HTTP endpoints directly to the Internet. Networking should allow traffic to ORDS only over HTTPS, while connections from ORDS to the database are restricted by network policy.

ORDS is not a new database engine and does not replace Oracle Net/JDBC across all applications. It provides an HTTP layer over configured database operations. Transactions, constraints, privileges, and data remain managed by Oracle Database.

### 1.1. Core Components

An ORDS deployment typically comprises:

- **ORDS runtime**: the HTTP service running inside a Java container or standalone mode depending on version and deployment method.
- **Database connection pools**: sets of JDBC connections from ORDS to configured database services/schemas.
- **ORDS metadata**: internal metadata storing REST configuration, modules, handlers, privileges, pools, and ORDS settings.
- **REST modules and handlers**: define endpoints, templates, HTTP methods, source types, and response formatting.
- **Authentication and authorization**: mechanisms to authenticate clients and enforce endpoint access privileges.
- **REST-enabled SQL**: endpoint allowing SQL submission over HTTP per configured policies and privileges.

Configuration command names, admin interfaces, and deployment requirements vary across ORDS releases. For real deployments, consult documentation for your exact running version and check the compatibility matrix with Oracle Database, Java, and related tools.

### 1.2. ORDS and Oracle Database

ORDS requires one or more database pools. A pool holds connection details, parsing schema, user, and related settings. A request borrows a connection from the pool, executes SQL/PL/SQL, and returns the connection to the pool.

Consequently, ORDS connection limits directly relate to Oracle session/process limits. With multiple ORDS instances—each maintaining its own pools—total potential connections equal the sum of pool capacities across every instance and every database pool.

Never size ORDS pools without accounting for other JDBC applications, Spring Boot services, batch jobs, monitoring, and DBA connections. ORDS can also generate heavy load if endpoints allow expensive queries or clients issue excessive concurrent requests.

## 2. REST APIs Published by ORDS

ORDS lets you expose database resources as REST endpoints. Several ways exist to build REST APIs:

1. **AutoREST**: enables REST access for tables or views per supported configuration.
2. **REST modules**: defines modules, URI templates, and handlers per HTTP method.
3. **PL/SQL handlers**: invokes procedures or packages to execute database logic.
4. **Query handlers**: returns data from defined SQL queries.
5. **ORDS metadata APIs**: manages or integrates configurations per appropriate privileges and version.

A well-designed REST API has stable resource paths, clear HTTP method semantics, validated payloads, granular authorization, and structured responses.

Illustrative examples:

    GET /ords/app/orders/1001
    POST /ords/app/orders
    PATCH /ords/app/orders/1001
    DELETE /ords/app/orders/1001

These paths merely illustrate resource design. Actual endpoints depend on the base path, schema alias, module, and templates configured in ORDS.

### 2.1. AutoREST

AutoREST can enable REST access for tables or views supported by ORDS. Once configured, ORDS exposes endpoints to read or manipulate data according to capabilities and granted privileges.

AutoREST can fit:

- Internal tools needing access to a set of approved tables.
- Prototypes or simple data integrations.
- Reference tables with stable structures.
- Cases needing a quick REST interface without writing custom handlers.

However, AutoREST does not automatically implement full business rules. If an operation must verify inventory, credit limits, order state transitions, audit logging, or coordinate multiple tables, exposing raw CRUD on a table bypasses business workflows.

Avoid bulk-enabling AutoREST across an application schema merely for convenience. Every exposed table becomes a new data access surface. Control tables, columns, privileges, sensitive data, DML operations, and client authentication.

### 2.2. REST Modules, Templates, and Handlers

REST modules let you define APIs around explicit contracts rather than coupling directly to table structures.

Common concepts:

- **Module**: group of endpoints sharing a base path and module name.
- **Template**: URI pattern, e.g., `orders/:orderId`.
- **Handler**: request handling logic per HTTP method.
- **Source type**: content type the handler executes, such as query or PL/SQL.
- **Parameter**: path, query, or header values passed into the handler.
- **Privilege/role**: access control requirements for the endpoint.
- **Pagination and response format**: pagination mechanics, data formatting, and response metadata.

Contract example:

    GET /ords/app/v1/orders/:orderId

The handler extracts `orderId` from the path, validates parameters, queries data, and returns a JSON response. For data-modifying operations, invoke PL/SQL packages that enforce transactions and business rules instead of concatenating arbitrary SQL strings from inputs.

REST handlers can decouple API contracts from physical table names. When internal schemas evolve, handlers can preserve stable response contracts if managed carefully.

### 2.3. Using PL/SQL Packages as a Database Business Layer

In some systems, business logic is encapsulated in PL/SQL packages. ORDS can invoke packages through handlers. This fits when logic must run close to the data, requires consistent transactions, and is maintained by DBAs/database teams.

Illustrative example:

    CREATE OR REPLACE PACKAGE order_api AS
      PROCEDURE create_order(
        p_customer_id IN NUMBER,
        p_order_id OUT NUMBER
      );
    END order_api;
    /

The ORDS handler receives the request, validates input, invokes the package, and returns the appropriate status code and payload. Agree clearly on who owns commit/rollback, exception handling, and HTTP error mapping. Never let a single request commit inside a package while also depending on another transaction in the handler without fully understanding the semantics.

If packages hold critical business logic, manage versioning, tests, `EXECUTE` privileges, dependencies, and migrations just like application code.

## 3. What Is REST-Enabled SQL?

REST-enabled SQL is an ORDS feature allowing clients to submit SQL statements via an HTTP endpoint configured for a schema. Instead of defining a separate REST resource per operation, the client sends a request containing a SQL statement and bind parameters; ORDS executes it within the granted context and returns results.

The endpoint typically takes the form:

    POST /ords/{schema-alias}/_/sql

This is a common illustrative URL pattern. Base paths, schema aliases, endpoint availability, and request/response contracts depend on ORDS version and deployment configuration. Obtain the exact endpoint from documentation or metadata of your running environment rather than hardcoding from examples.

REST-enabled SQL can be useful for:

- Authorized analytics or administrative tools.
- SQL clients integrating over HTTP.
- Internal tasks requiring parameterized queries without building a dedicated REST module per statement.
- Certain development or data-testing workflows.

The defining characteristic is that the client supplies the SQL. Consequently, the database user's privilege scope, authentication mechanism, and statement restrictions dictate the risk level. Never treat REST-enabled SQL as a public endpoint for mobile apps or browsers to send arbitrary queries.

### 3.1. Request and Response Flow

Conceptual flow:

    Client
      |
      | HTTPS POST + SQL statement + binds
      v
    ORDS REST-enabled SQL endpoint
      |
      | authenticate / authorize
      | validate request
      | borrow database connection
      v
    Oracle Database
      |
      | execute statement
      | produce rows / status
      v
    ORDS serializes response
      |
      v
    Client receives JSON response

Illustrative payload for a query with binds:

    {
      "statementText": "select order_id, status from orders where customer_id = :customer_id",
      "binds": [
        {
          "name": "customer_id",
          "type": "NUMBER",
          "value": 1001
        }
      ],
      "offset": 0,
      "limit": 50
    }

Field structures, supported bind types, row limits, multi-statement handling, and response formats must be verified against your ORDS release. The example above illustrates parameterized SQL only, not a guarantee across all endpoint versions.

Clients should use bind variables instead of concatenating input into SQL strings. Binds separate data from SQL syntax, prevent many forms of SQL injection, and help the database reuse execution plans where appropriate.

### 3.2. SQL Statements and Database Privileges

REST-enabled SQL does not bypass Oracle privilege rules. SQL executes within the database context of the user/schema configured for the endpoint. That user must hold only least privileges for the integration's purpose.

If the user can read multiple schemas or holds broad DML privileges, clients using REST-enabled SQL can affect that entire data scope. Endpoint protection must therefore start with the database account:

- Use a dedicated account per integration group.
- Grant only `SELECT`/`EXECUTE` or DML on required objects.
- Never use `SYS`, `SYSTEM`, or DBA accounts for applications.
- Separate read-only integrations from write integrations.
- Restrict schemas, networking, authentication, and resource quotas appropriately.
- Review object privileges via roles vs. direct grants per runtime execution requirements.

Never grant general SQL access just because a client needs to read a few reports. Create views or packages limiting data, then publish APIs with explicit contracts.

### 3.3. REST-Enabled SQL Is Not a Business REST API

A generic SQL endpoint couples clients directly to database structure: table names, column names, data types, joins, filter rules, and SQL privileges. If the schema changes, client queries break. Clients can also craft unintended queries if privileges are overly broad.

A business API typically exposes only the operations permitted by the system, such as:

    POST /orders
    GET /orders/{id}
    POST /orders/{id}/approve

Business contracts express concepts like creating, viewing, and approving orders. Clients need no knowledge of `ORDER_HEADER`, `ORDER_LINE`, or internal packages.

Treat REST-enabled SQL as a controlled data-access tool for trusted clients. When you need stable public APIs, versioning, validation, business authorization, orchestration, and backward compatibility, build dedicated resource APIs.

## 4. Boundaries Between ORDS and Spring Boot Applications

Spring Boot and ORDS can coexist in one system, but responsibilities must be clearly separated so two layers do not jointly own the same API or business rule.

### 4.1. When to Use ORDS?

ORDS fits when:

- You need to expose a set of Oracle data as REST resources with minimal intermediate tiers.
- APIs primarily read/write data within one schema under a simple contract.
- PL/SQL packages own the database logic and you want to expose them over HTTP.
- DBAs or the database team operate database-adjacent APIs.
- Controlled tools or integration clients need REST-enabled SQL.
- You want Oracle-integrated ORDS capabilities such as SQL Developer Web, REST APIs, or related administration features.

Example: a schema holds a read-only product catalog table. ORDS can publish a `GET` endpoint for internal applications with scoped privileges and defined responses.

### 4.2. When to Use Spring Boot?

Spring Boot fits when:

- APIs must coordinate multiple databases, message brokers, or external services.
- Business workflows involve multi-step processes, state machines, approval rules, or sagas.
- You need end-user authentication and authorization by tenant, organization, or domain permissions.
- You need application-level contract control, versioning, validation, rate limiting, and observability.
- API release lifecycles must be decoupled from database schema lifecycles.
- Logic must be unit-tested independently and managed as an application service.
- You need multi-database support or flexibility to swap the persistence layer.

Example: order creation must authenticate the buyer, check inventory, calculate pricing, apply coupons, save the order, and emit events to shipping. This is an application workflow well suited for Spring Boot orchestration; ORDS can serve as a secondary integration endpoint if needed.

### 4.3. Comparison Table

| Criterion | ORDS | Spring Boot |
|---|---|---|
| Primary role | HTTP interface for Oracle Database | Application/API layer |
| Execution context | SQL, PL/SQL, and handlers inside database context | Java application services, repositories, and integration clients |
| API contract | Modules/templates/handlers or AutoREST | Controllers, DTOs, services, and API specifications |
| Multi-system integration | Can call out via PL/SQL or other integrations, but not its core role | Well suited for orchestration and integration |
| Complex business logic | Possible in PL/SQL, though tightly coupled to the database | Well suited for multi-step workflows and domain logic |
| General SQL access | REST-enabled SQL can permit SQL over HTTP per privileges | Should not expose general SQL to clients |
| Database coupling | Higher, close to schemas and PL/SQL | Can encapsulate the database behind repositories/services |
| Authentication | ORDS/OAuth2/identity integration per environment | Spring Security and identity provider integration |
| Connection management | ORDS database pools | JDBC pools in each application instance |
| Deployment | ORDS runtime and database metadata configuration | Java service, container, or application runtime |
| Primary operators | DBAs/database team and platform team | Backend/application platform team |

There is no universal rule that ORDS is always faster than Spring Boot or Spring Boot is always more secure than ORDS. Performance and security depend on implementation, queries, pools, privileges, networking, payloads, caching, and operations.

## 5. Combining ORDS and Spring Boot in an Architecture

A hybrid architecture can use Spring Boot for public APIs and ORDS as an internal interface for specific database tasks or data tools.

Example:

    Browser / Mobile / Partner
              |
            HTTPS
              |
              v
        API Gateway / WAF
              |
              v
       Spring Boot services
       +----------------------+
       | Authentication       |
       | Business rules       |
       | Validation           |
       | Orchestration        |
       | Audit / Observability|
       +----------------------+
           |             |
           | JDBC        | HTTPS (selected integration)
           v             v
       Oracle DB         ORDS
                           |
                           v
                       Oracle DB

In this model, Spring Boot connects directly to Oracle via JDBC for core business transactions. ORDS provides a separate REST API for integration teams, reporting, or administrative tools. Not every Spring Boot operation needs to go through ORDS; adding an extra HTTP hop between tiers increases latency and adds failure points unless it provides clear architectural value.

Key principles:

- Assign a single contract owner for each use case.
- Never duplicate the same endpoint in both Spring Boot and ORDS without strong justification.
- If Spring Boot calls ORDS, configure timeouts, retries, circuit breakers, authentication, and trace propagation.
- Avoid circular calls: Spring Boot → ORDS → Spring Boot.
- Never expose REST-enabled SQL directly to public clients when a use case needs a business API.
- Keep transaction boundaries explicit. A JDBC transaction in Spring Boot does not automatically wrap a separate HTTP request to ORDS.
- Synchronize schema migrations, API versions, and release plans across owning teams.

### 5.1. Spring Boot Calling ORDS as an External HTTP Service

If a use case genuinely requires calling ORDS, Spring Boot can use `WebClient` or an HTTP client to invoke the endpoint. Encapsulate the client in a dedicated adapter/service instead of having controllers construct URLs and HTTP requests directly.

Illustrative example with `WebClient`:

    @Configuration
    class OrdsClientConfiguration {

        @Bean
        WebClient ordsWebClient(
                WebClient.Builder builder,
                OrdsProperties properties) {
            return builder
                    .baseUrl(properties.baseUrl())
                    .build();
        }
    }

    @ConfigurationProperties(prefix = "integration.ords")
    public record OrdsProperties(String baseUrl) {}

    @Service
    class CatalogClient {

        private final WebClient webClient;

        CatalogClient(WebClient ordsWebClient) {
            this.webClient = ordsWebClient;
        }

        Mono<CatalogItem> findItem(String itemId) {
            return webClient.get()
                    .uri("/ords/catalog/v1/items/{id}", itemId)
                    .retrieve()
                    .bodyToMono(CatalogItem.class);
        }
    }

This snippet illustrates adapter structure only. In real applications, configure OAuth2/client credentials or ORDS-supported authentication, timeouts, error mapping, HTTP connection pools, correlation IDs, and retry policies. Never automatically retry `POST`/`PUT` unless operations are idempotent.

If an ORDS API merely runs simple data queries that Spring Boot could read directly via a repository, evaluate whether the HTTP hop is truly warranted. Use ORDS when an independent REST contract or database-team-managed integration gateway is required.

### 5.2. Transaction Boundaries Across HTTP Calls

A database transaction is typically bound to a specific connection/session. If Spring Boot opens a JDBC transaction and makes an HTTP call to ORDS, ORDS borrows a different connection from its own pool. Those two connections do not automatically share a single local transaction.

Example:

    Spring Boot transaction A
        |
        +-- UPDATE order_header
        |
        +-- HTTP request to ORDS
                |
                +-- ORDS transaction B
                        |
                        +-- UPDATE inventory

If transaction B commits while transaction A rolls back, inventory and orders become inconsistent. If A commits while B fails, state is likewise inconsistent. Never assume Spring Boot's `@Transactional` governs the transaction inside an ORDS HTTP request.

For operations requiring atomicity on the same database, perform them within the same JDBC transaction boundary or invoke a stored procedure/package over a single connection. When coordinating multiple services over HTTP, design sagas, outbox/inbox patterns, idempotency, and compensating actions instead of relying on a local transaction that cannot span services.

### 5.3. Schema and API Ownership

Clearly establish:

- Which team owns the database schema.
- Which team owns PL/SQL packages.
- Which team owns ORDS modules and privileges.
- Which team owns Spring Boot API contracts.
- Who manages authentication, certificates, secrets, and rotation.
- Who owns versioning and backward compatibility.
- Who monitors performance, quotas, connection pools, and production errors.

If both Spring Boot and ORDS touch the same schema, maintain migration workflows compatible with both. Never deploy DDL that breaks ORDS endpoints while Spring Boot still relies on the old schema, or vice versa.

## 6. Securing ORDS and REST-Enabled SQL

ORDS is an HTTP surface into the database. Misconfiguration can leak data or allow operations beyond the integration's intent. Security must be layered.

### 6.1. HTTPS and Network Boundaries

- Enforce HTTPS only for client traffic to ORDS.
- Place ORDS behind a controlled load balancer/reverse proxy or API gateway.
- Restrict network paths from ORDS to the database; open only necessary ports and services.
- Never expose database listeners directly to the Internet.
- Separate internal and public endpoints via network policies, hostnames, or gateway rules.
- Manage certificates, expiration, and rotation.
- Never trust client-supplied identity headers unless authenticated and forwarded by a trusted gateway mechanism.

### 6.2. Authentication and Authorization

Authentication answers who the client is; authorization answers what the client is permitted to do. Control these separately.

ORDS supports various authentication mechanisms depending on version and environment, such as OAuth 2.0, database authentication, or identity provider integration. Choose flows matching client types:

- Machine-to-machine integrations: client credentials or supported service identities.
- User-facing applications: delegated user identity or appropriate gateway/identity provider integration.
- Administrative access: dedicated accounts, MFA, and network restrictions per organizational policy.

After authentication, privileges/roles must restrict which endpoints and objects a client can access. Never grant one broad schema-wide role to every integration client.

### 6.3. Least Privilege in the Database

Create dedicated database users per application or integration group. For instance, a reporting read-only user should hold `SELECT` on approved views, never `UPDATE`/`DELETE` on transactional tables.

Create views limiting columns and rows:

    CREATE VIEW reporting_order_summary AS
    SELECT order_id, order_date, status, total_amount
    FROM orders
    WHERE status <> 'INTERNAL';

    GRANT SELECT ON reporting_order_summary TO report_api_user;

The `WHERE` clause is illustrative only. If data requires tenant- or user-level isolation, enforce mechanisms preventing clients from tampering with predicates to read another tenant's data—such as views, VPD/row-level security, application contexts, or controlled handlers depending on architecture.

Never use the schema owner account with broad privileges for REST-enabled SQL clients.

### 6.4. SQL Injection and Bind Variables

REST-enabled SQL accepts SQL from clients, demanding strict control over privileges and statement construction. In API handlers, strictly avoid concatenating request input directly into SQL:

    -- Unsafe: input concatenated directly into SQL
    sql_text := 'SELECT * FROM orders WHERE customer_id = ' || p_customer_id;

Always prefer bind variables:

    SELECT order_id, status
    FROM orders
    WHERE customer_id = :customer_id;

Bind variables separate values from SQL syntax. However, binds cannot substitute for table names, column names, or SQL keywords. When dynamic SQL needs identifiers, enforce allowlists and validate identifiers via `DBMS_ASSERT` or equivalent controls—never accept arbitrary identifiers from clients.

With REST-enabled SQL, clients submit statements directly, so bind variables protect values without making the endpoint inherently safe. A client allowed to submit arbitrary SQL can still read or modify any object accessible to that database user. Least privilege and endpoint restrictions remain foundational.

### 6.5. Protecting Sensitive Data

- Never return passwords, tokens, secrets, or authentication data in responses.
- Never publish tables containing personal data without clear purpose and authorization.
- Limit returned columns, especially identity and financial fields.
- Enable auditing for sensitive access per compliance requirements.
- Keep secret payloads and SQL literals containing sensitive data out of logs.
- Define log retention periods and log access permissions.
- Apply masking/anonymization when using production data in non-production environments.

### 6.6. Rate Limits, Payloads, and Query Cost

Database-backed REST endpoints can be abused via high-frequency requests or queries returning massive datasets. Enforce:

- Rate limits and concurrency limits at the gateway/ORDS aligned with database capacity.
- Pagination and maximum page size caps.
- Statement timeouts and HTTP request timeouts.
- Request/response payload size limits.
- SQL plan and index reviews for critical queries.
- Monitoring of connection pools, active sessions, CPU, I/O, and wait events.
- Request cancellation and client-disconnect handling policies.

Never expose endpoints permitting unrestricted full table scans or unbounded queries on large tables.

## 7. Connection Pools, Concurrency, and Performance

ORDS maintains database connection pools. Each ORDS instance and each pool can open up to a configured maximum number of connections. Behind a load balancer, total potential sessions scale rapidly across instances.

Example:

    3 ORDS instances
    2 database pools per instance
    20 maximum connections per pool

    Maximum potential connections
      = 3 x 2 x 20
      = 120

This excludes connections from Spring Boot, batch jobs, monitoring, and DBAs. With Oracle dedicated server mode, each application session usually maps to a server process; check against `PROCESSES`, `SESSIONS`, and database host capacity.

### 7.1. Do Not Grow Pools Indefinitely

Larger pools raise concurrency, yet also increase sessions, processes, memory usage, and resource contention. If the database is already CPU- or I/O-saturated, enlarging pools can worsen latency.

Measure:

- Active and pending requests in ORDS.
- Connection pool active/available counts and borrow timeouts.
- Sessions by service/module/schema.
- SQL execution time, wait events, CPU, and I/O.
- Throughput and p95/p99 latency.
- HTTP error rates and database error rates.

### 7.2. ORDS and Spring Boot Maintain Separate Pools

When both Spring Boot and ORDS connect to the same database, they hold two independent sets of connection pools. Example:

    Spring Boot replicas: 4
    Hikari maximumPoolSize: 20
    Potential Spring Boot sessions: 80

    ORDS instances: 2
    ORDS pool maximum: 30
    Potential ORDS sessions: 60

    Combined potential: 140 sessions

This reflects only maximum configured pool capacity. Add batch jobs, monitoring, scheduled jobs, background sessions/processes, and headroom. On RAC, inspect each instance individually, as connection distribution may be uneven.

### 7.3. Connection Timeouts and Query Timeouts

Distinguish between:

- Time spent waiting to borrow a connection from the pool.
- SQL execution time inside the database.
- Request processing time in ORDS.
- Timeouts at the reverse proxy/API gateway.
- Client-side timeouts.

If a proxy timeout is shorter than query execution time, the client receives an error while the database keeps working. Order timeouts sensibly, support statement cancellation, and release connections promptly when requests abort.

## 8. HTTP Semantics and API Design

ORDS REST modules should adhere to HTTP semantics so clients understand request effects accurately.

| Method | Standard Meaning | Example |
|---|---|---|
| `GET` | Read resource without altering business state | Fetch order details |
| `POST` | Create resource or execute command | Create order |
| `PUT` | Replace resource representation per contract | Update full configuration |
| `PATCH` | Partially update a resource | Perform allowed status transition |
| `DELETE` | Delete or mark resource deleted per contract | Delete draft |

Never use `GET` to execute DML. Proxies, caches, or browsers may retry `GET` assuming method safety. A `GET` handler with side effects makes systems unpredictable and hard to secure.

### 8.1. Status Codes and Error Responses

Keep responses consistent:

- `200 OK` for successful reads or updates returning a body.
- `201 Created` when creating a resource succeeds, optionally with `Location`.
- `204 No Content` when an operation succeeds without a response body.
- `400 Bad Request` for malformed input.
- `401 Unauthorized` when unauthenticated or credentials are invalid.
- `403 Forbidden` when authenticated without sufficient permissions.
- `404 Not Found` when the resource does not exist or is hidden by policy.
- `409 Conflict` for state or constraint conflicts.
- `422 Unprocessable Content` if syntax is valid yet validation rules fail per contract.
- `429 Too Many Requests` when rate limits are exceeded.
- `500 Internal Server Error` for unexpected failures; never expose stack traces or internal SQL.

Specific error codes must match your system's API contract. Never return raw Oracle error stacks to public clients, as they can leak table names, schemas, SQL, file paths, or internal details.

### 8.2. Pagination and Sorting

List endpoints must enforce page size limits and stable pagination. On large datasets, offset pagination slows down at deep offsets; keyset pagination over sort keys often performs better.

Sort fields must be allowlisted. Never concatenate client-supplied sort values or column names straight into SQL. In query handlers, map sort options to SQL columns on the server side.

### 8.3. Idempotency and Retries

Clients may retry on timeouts or dropped connections. For order creation or payments, retries can create duplicate records if APIs lack an idempotency strategy.

Command APIs should consider idempotency keys, unique constraints, request ledgers, or deduplication mechanics. Only retry automatically when operations are safe to retry or carry idempotency guarantees.

## 9. Versioning and API Lifecycle Management

Both ORDS modules and Spring Boot APIs require versioning once clients depend on their contracts.

Example:

    /ords/app/v1/orders
    /ords/app/v2/orders

Or version via headers per organizational standards. Never alter data types, field meanings, status codes, or access rules without assessing client impact.

When database schemas change:

1. Identify every API/handler referencing affected objects.
2. Deploy backward-compatible schema changes when needed.
3. Update PL/SQL packages and ORDS modules per release plan.
4. Update Spring Boot adapters or DTOs if contracts change.
5. Test both old and new clients.
6. Retire older API versions only after client migration completes.

Use expand-and-contract migrations: add new columns or packages first, migrate clients, and remove legacy structures in a subsequent release. This reduces the risk of ORDS and Spring Boot hitting schema mismatches during rollouts.

## 10. Observability, Logging, and Auditing

Because ORDS is a distinct tier, it needs independent observability linked to the database.

Fields to record:

- Request ID/correlation ID.
- HTTP method, route, and status code.
- Safe client identity or application identity.
- Total processing time, pool wait time, and database time.
- Invoked module/handler or endpoint.
- Database service, schema/pool, and session/module if configured.
- Rows returned or affected, without logging sensitive payloads.
- Safely mapped Oracle error codes.
- Authentication/authorization outcomes at an appropriate level.

Never log access tokens, passwords, sensitive bind values, or full SQL containing personal data. Where SQL auditing is required, govern retention, access controls, and masking per data policies.

Spring Boot should forward correlation IDs to ORDS over HTTP so logs correlate across gateway, service, ORDS, and database. For direct JDBC connections, Spring Boot should set `module`/`action` or client identifiers so DBAs can identify sessions in `V$SESSION`.

## 11. Deploying and Operating ORDS

Production deployments must manage both the ORDS runtime and database metadata.

Items to prepare:

- Compatible ORDS, Java runtime, and Oracle Database versions.
- ORDS configuration directory and secret management approach.
- Database pools, service names, schema mappings, and connection limits.
- HTTPS certificates, reverse proxies, load balancers, and network firewalls.
- Authentication providers, OAuth clients, roles, and privileges.
- Appropriate backups of metadata and configuration.
- Logs, metrics, health checks, and alerting.
- Patch management and upgrade plans.
- HA/DR for both the ORDS runtime and database backend.

Never store database passwords in source code or committed configuration files. Use a secret manager or platform-supported configuration encryption; restrict secret read access and schedule rotations.

### 11.1. Health Checks and Readiness

Health checks must distinguish whether the ORDS process is alive from whether database pools can actually serve requests. A process can return HTTP responses even when pools are exhausted or the database is down.

Monitor at minimum:

- Runtime process and HTTP listener.
- Connectivity through database pools.
- Authentication/authorization dependencies.
- Request error rates and latency.
- Connection pool saturation.
- Database service health.

Health endpoints must not leak sensitive details about the database or internal configuration.

### 11.2. HA and Scaling

Multiple ORDS instances can run behind a load balancer. Each instance needs consistent configuration pointing to the proper database services. Scaling out ORDS increases HTTP capacity, yet also raises total potential connections to the database.

Before scaling out, sum pool capacities across all instances and check Oracle `SESSIONS`/`PROCESSES`. If the database is the bottleneck, adding ORDS instances increases load without improving throughput.

### 11.3. Upgrades and Compatibility

When upgrading ORDS:

- Read release notes and Java/database version requirements.
- Back up configuration files and the database storing ORDS metadata.
- Test custom modules, handlers, privileges, and authentication.
- Test legacy endpoints and required SQL-enabled endpoints.
- Deploy rolling or blue/green if supported by your architecture.
- Prepare runtime rollback and metadata migration fallback plans.

Never upgrade production runtimes without testing in a comparable environment, especially when APIs are dependencies for other systems.

## 12. Choosing ORDS vs. Spring Boot by Use Case

One way to decide is to start with the question: does the client need raw database data access or to execute a business behavior?

| Use Case | Typical Fit | Reason |
|---|---|---|
| Internal tool running approved queries | Controlled REST-enabled SQL | Technical client needs to run SQL under scoped privileges |
| Publishing read-only reference tables | ORDS REST API or view handler | Simple contract, data lives close to the database |
| Simple CRUD for one schema with a clear owner | ORDS REST module | Exposes resources cleanly close to the database |
| Multi-step order creation | Spring Boot | Needs orchestration, validation, and domain logic |
| Calling payment, inventory, and message brokers | Spring Boot | Coordinates multiple systems and handles distributed errors |
| Public APIs for mobile/partners | Spring Boot typically fits best | Needs versioning, business authorization, and stable contracts |
| DBA tools or trusted data integration | ORDS/REST-enabled SQL by scope | Close to the database and suited for controlled access |
| Logic already encapsulated in PL/SQL packages | ORDS handler can fit | Exposes packages without rewriting logic elsewhere |

These are guidelines, not rigid walls. A system can use ORDS for database-centric endpoints and Spring Boot for business APIs, provided ownership and security boundaries stay crisp.

## 13. Illustrative Scenario: Order Management System

Suppose a system includes:

- Spring Boot Order Service owning the order placement workflow.
- Oracle Database storing orders, customers, and inventory.
- ORDS publishing a product catalog read API for an internal integration client.
- A DBA tool using REST-enabled SQL on an administrative network to run permitted queries.

Order creation flow:

    Mobile client
        |
        | POST /api/orders
        v
    Spring Boot Order Service
        |
        +--> Validate user and request
        +--> Check business rules
        +--> Update order and inventory in DB transaction
        +--> Write outbox event
        |
        v
    HTTP response

Catalog read flow:

    Internal integration client
        |
        | GET /ords/catalog/v1/products
        v
    ORDS REST handler
        |
        | query approved view
        v
    Oracle Database

Admin query flow:

    Admin SQL tool
        |
        | HTTPS + authenticated SQL request
        v
    ORDS REST-enabled SQL
        |
        | restricted database account
        v
    Oracle Database

In this design, Spring Boot owns the order placement workflow. ORDS does not expose a second endpoint to update orders that would bypass Order Service validation and transaction logic. ORDS serves only approved catalog data. REST-enabled SQL is locked down to admin tooling, dedicated users, and an isolated network.

If that integration client later needs to submit order requests, it should call the Spring Boot business API rather than receiving general DML privileges via REST-enabled SQL.

## 14. Common Architectural Mistakes

### 14.1. Public REST-Enabled SQL

Letting Internet clients send arbitrary SQL drastically expands attack surface and coupling. One privilege mistake can expose or corrupt unintended data.

Fix: enable only for controlled clients using least-privilege accounts, network restrictions, and strong authentication. For public use cases, build dedicated REST resources or Spring Boot APIs.

### 14.2. Direct AutoREST on Business Tables

Enabling raw CRUD directly on order, payment, or account tables bypasses business rules, auditing, and workflows. Fix: publish read-only views or PL/SQL handlers invoking controlled packages; keep business commands in application services when Spring Boot owns the domain.

### 14.3. Spring Boot Calling ORDS for Every Query

Routing every JDBC operation over HTTP to ORDS adds latency, extra connection pools, failure points, and split transaction boundaries. Do so only when an independent REST contract or integration boundary is needed. When Spring Boot owns the use case and needs transactions with Oracle, direct JDBC is simpler.

### 14.4. Split Ownership of Business Rules

If both Spring Boot and PL/SQL implement the same pricing or approval rule, logic diverges over time. Pick a single owner per rule and make the other side an adapter. If business logic lives in PL/SQL, Spring Boot should call the package via a repository/adapter instead of reimplementing the rule differently.

### 14.5. Ignoring Total Connection Counts

ORDS, Spring Boot, batch jobs, and admin tools maintain separate pools. Checking only one application's pool risks hitting Oracle `SESSIONS` or `PROCESSES` when everything scales under load. Sum max pool sizes across all replicas and preserve headroom.

### 14.6. Leaking Database Errors Over HTTP

Returning raw SQL, stack traces, or Oracle error messages exposes schemas, objects, and internal structure. Map errors to stable API error codes, keep technical details in controlled logs, and return correlation IDs to clients.

## 15. Design and Operations Checklist

### Before Publishing Endpoints

- Determine whether the endpoint serves end users, services, or admin tools.
- Choose ORDS REST modules, AutoREST, PL/SQL handlers, or REST-enabled SQL.
- Define contract and business logic ownership.
- Scope database users, schemas, objects, and privileges.
- Design authentication, authorization, and HTTPS.
- Define pagination, timeouts, payload limits, rate limits, and error mappings.
- Review SQL/PL/SQL, indexes, execution plans, and load capacity.
- Check sensitive data exposure and auditing requirements.
- Test both authorized and unauthorized clients.

### When Combining with Spring Boot

- Call ORDS only through centrally configured adapters/clients.
- Configure timeouts, retries, circuit breakers, and idempotency.
- Never assume `@Transactional` spans an ORDS HTTP request.
- Never split ownership of a single business rule across ORDS and Spring Boot.
- Monitor connection pools in both tiers.
- Propagate correlation IDs and set `module`/`action` for traceability.
- Manage schema migrations compatibly across ORDS and Spring Boot.
- Maintain versioning and deprecation plans for endpoints.

### After Deployment

- Monitor HTTP status codes, latency, and error rates.
- Monitor ORDS pools, database sessions/processes, and SQL waits.
- Periodically review privileges and OAuth clients.
- Verify certificate and secret rotations.
- Test upgrades and rollbacks.
- Verify logs contain no unauthorized tokens/passwords/PII.
- Rehearse outages when the database or ORDS runtime is unavailable.

## 16. Key Principles to Remember

- ORDS is a middle tier providing an HTTP/REST interface to Oracle Database.
- ORDS REST APIs can be built via AutoREST, modules/templates/handlers, or PL/SQL packages.
- REST-enabled SQL accepts SQL over HTTP and must be secured as a privileged database access interface.
- Spring Boot excels at business APIs, orchestration, multi-system integration, and domain authorization.
- Never expose general SQL to public clients when only specific business operations are needed.
- ORDS and Spring Boot maintain separate connection pools; sum total sessions across all instances and services.
- An HTTP call from Spring Boot to ORDS creates a separate transaction boundary; `@Transactional` does not span both connections.
- Assign clear single ownership for every API contract and business rule.
- Security must combine HTTPS, authentication, authorization, least privilege, bind variables, rate limiting, and auditing.
- Performance monitoring must cover HTTP requests, ORDS pools, and Oracle Database together.

ORDS and Spring Boot complement each other well when each tier holds its proper responsibilities. ORDS provides a database-adjacent REST interface and controlled SQL access tooling; Spring Boot provides the application tier to safeguard contracts, orchestrate business logic, and integrate systems. Clear boundaries keep APIs maintainable, transactions predictable, access tightly scoped, and the database free from unnecessary exposure.
