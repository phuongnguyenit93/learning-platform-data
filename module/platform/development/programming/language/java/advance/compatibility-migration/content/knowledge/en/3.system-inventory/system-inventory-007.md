# Inventorying Protocols, Stored Data, and External Systems

Before upgrading Java, changing libraries, or replacing a service, you need to know which components the application communicates with and how data is exchanged. A module may expose only a few externally visible controllers while depending on multiple databases, message brokers, authentication services, payment systems, file stores, and batch jobs. Missing a single connection can cause a change that appears to affect only one module to break a business flow elsewhere.

**System inventorying** is the process of collecting and verifying connections, data contracts, storage locations, and external dependencies before planning a migration. The results must answer: which component communicates with which component, over what protocol, with what data structure, who owns both ends of the connection, which versions are in use, and what could be impacted when one side changes.

## 1. Defining the Survey Scope

Start from the boundary of the application or module being migrated. List inbound flows, outbound flows, and internal flows that may cross that boundary.

- **Inbound connections:** external systems calling REST APIs, sending messages, pushing files, invoking callbacks, or accessing a published interface.
- **Outbound connections:** the application calling other services, querying databases, sending messages, writing files, or calling vendor APIs.
- **Internal connections:** modules within the same system calling each other via Java interfaces, internal HTTP, message brokers, or sharing a database/schema.
- **Stored data flows:** data written today may be read by the new version, a batch job, reports, or another system in the future.
- **Operational flows:** health checks, service discovery, remote configuration, secrets, log forwarding, metrics, tracing, and deployment mechanisms can also be dependencies that need surveying.

Do not limit the scope to calls appearing directly inside a single class. A flow may pass through a gateway, adapter, queue, scheduled job, or integration platform before reaching its destination. Also record intermediary components that can transform data or make routing decisions.

Distinguish the following three concepts to avoid confusion:

- **Protocol:** rules for exchanging information, for example HTTPS, AMQP, JDBC, or SFTP.
- **Contract:** structure and meaning of requests, responses, messages, files, or stored data.
- **System/endpoint:** the specific component the application connects to, for example `customer-service`, a PostgreSQL cluster, or a payment provider.

Two systems may both use HTTPS yet have completely different contracts, authentication methods, and versioning policies. Recording each piece of information under the right category helps evaluate migration more accurately.

## 2. Listing Protocols and Data Exchange Mechanisms

A protocol describes how two sides transmit information. When inventorying, record both the transport-layer protocol and the payload format if they can change independently.

### 2.1. Synchronous Communication Over HTTP

Common integration styles include REST/JSON, SOAP/XML, GraphQL, and internal HTTP APIs. For each connection, record:

- Logical address or service name, environment, and endpoint path; do not include tokens or secrets in the documentation.
- HTTP method, path, query parameters, headers, and content type.
- Request/response structure, data types, required/optional fields, enums, units, and default values.
- Authentication method: OAuth2, JWT, API key, mutual TLS, session, or custom mechanism.
- Timeouts, retries, circuit breakers, rate limits, pagination, and size limits.
- Meaning of HTTP statuses, business error codes, and error-handling rules.
- API version, deprecation policy, and consumers calling the endpoint.

For example, two APIs may both return JSON yet differ in time representation (`UTC` vs local time), money (`decimal` vs integer in minor units), missing fields (`null` vs omitted), and how errors are expressed. Those differences can break consumers even when the endpoint still returns HTTP 200.

For SOAP, in addition to the URL and HTTP transport, record the WSDL, XSD, namespaces, SOAP version, operations, fault rules, and security policies. If the client is generated from WSDL, record the contract version used to generate the code and how to regenerate stubs when the contract changes.

For GraphQL, record the schema, queries/mutations used, custom scalar types, nullability rules, pagination, and handling of deprecated/removed fields. For versioned APIs, record clearly whether the version lives in the URL, header, or media type.

### 2.2. Asynchronous Communication via Messages

Java applications frequently exchange messages asynchronously via Kafka, RabbitMQ, JMS, or cloud queue services. A message broker reduces temporal coupling between producer and consumer, yet does not eliminate data contract coupling.

For each message flow, record:

- Broker, cluster, virtual host or namespace, and corresponding environments.
- Topic, queue, exchange, routing key, subscription, or consumer group.
- Producer, consumer, and teams responsible for operating each end.
- Payload format: JSON, Avro, Protobuf, XML, byte array, or custom format.
- Schema/version, schema registry, and compatibility rules if any.
- Delivery semantics: at-most-once, at-least-once, or mechanisms approximating exactly-once within a specific scope.
- Message ordering, partition key, deduplication, idempotency, and ability to handle duplicate messages.
- Retries, backoff, dead-letter queue (DLQ), message retention duration, and replay mechanism.
- Acknowledgement policy, offsets/consumer positions, and behavior when a consumer stops mid-processing.

Do not merely record “the application uses Kafka”. You need to know which topic carries which events, who publishes them, and who reads them. For example, renaming a field in an `OrderCreated` event can impact multiple independent consumers not directly managed by the producer's development team.

Pay special attention to the fact that messages can outlive a single deployment. A new consumer may re-read old messages still stored in the broker; an old consumer may receive new messages after the producer is upgraded. Therefore, event contracts must be evaluated in both version directions.

### 2.3. File Exchange and Batch

Many integrations do not use direct APIs, exchanging files instead via SFTP, FTPS, shared directories, object storage, or scheduled import/export mechanisms. Record:

- Transfer channel and logical location of files; distinguish test and production environments.
- Who produces the file, who receives it, who acknowledges processing, and who is responsible when a file is missing.
- Format: CSV, TSV, fixed-width, Excel, XML, JSON, ZIP, or binary formats.
- Encoding, delimiter, quote/escape, line ending, timezone, date format, and decimal conventions.
- Filename, naming convention, inbound/outbound directories, frequency, run schedule, and file arrival deadline.
- Header rules, column order, required fields, value encoding, and representation of error records.
- File-completion detection mechanism, checksums, signatures, encryption, duplicate-processing prevention, and post-processing archival.

For example, a batch job may still complete without errors yet produce wrong data if a vendor switches `dd/MM/yyyy` to `MM/dd/yyyy`, changes encoding to UTF-8 with BOM, or inserts a column at the beginning of the file while the program reads positionally. Therefore, test file contracts with representative sample data, including empty files, Vietnamese characters, boundary values, and error records.

### 2.4. Database Connections and Data Access Protocols

For databases, record the DBMS type and version, JDBC driver, hostname/service name in secret-free configuration form, database/schema, connection type, TLS, connection pool, and failover mechanism. State clearly whether the application uses JDBC directly, Spring JDBC, JPA/Hibernate, MyBatis, or another adapter.

Beyond the JDBC protocol, the data contract also includes SQL dialect, data types, collation, timezone, constraints, transaction isolation, stored procedures, triggers, and access permissions. A new driver version or database engine change can affect data types, SQL statements, transaction behavior, and performance.

If the application connects through a proxy, database gateway, or read replica, document those layers. They may enforce different connection limits, read/write routing, or timeout policies than the primary database.

### 2.5. Other Communications

Depending on architecture, systems may also use TCP sockets, WebSockets, RMI, LDAP, SMTP, DNS, gRPC, multicast, device protocols, or vendor-specific SDKs. Do not overlook a connection merely because it is not a REST API.

For each specialized protocol, identify the version, framing/encoding mechanism, timeouts, authentication, error codes, payload limits, reconnection handling, and client/server compatibility. If communication is wrapped in an SDK, record both the SDK version and the remote service versions supported by that SDK.

## 3. Listing Stored Data

Stored data is part of the system contract. A new application version may have to read data written years earlier; a rollback may force the old version to read data just updated by the new version. Therefore, the survey must cover structure, semantics, lifecycle, and all parties reading/writing the data.

### 3.1. Relational Databases

For each database/schema, record:

- Data owner and business purpose.
- Related tables, views, materialized views, sequences, functions, procedures, and triggers.
- Primary keys, foreign keys, unique constraints, check constraints, and important indexes.
- Column types, lengths, precision/scale, nullability, defaults, collation, and timezone.
- Creation/update/deletion rules, soft deletes, audit fields, and versioning/optimistic locking.
- Table relationships, reference data, and enum values stored as text or numbers.
- Migration history, migration tool, and schema application order.
- Other applications, jobs, reports, or users reading/writing the same schema.

Do not assume a database belongs exclusively to one service just because that service initially created the tables. A report, stored procedure, or legacy application might be accessing it directly. Changing column names, data types, or constraints without knowing those consumers can cause migration failures outside the source code being modified.

### 3.2. NoSQL and Semi-Structured Data

For document databases, key-value stores, wide-column stores, or graph databases, record collection/bucket/key patterns, document shapes, partition keys, indexes, TTLs, consistency models, and query patterns. Identify which fields are required, which fields may be absent, data types that can evolve over time, and how the application handles old documents.

If data has a flexible schema, collect document versions existing from multiple time periods. The schema in current source code does not necessarily reflect all data stored in production.

### 3.3. Caches, Search Indexes, and Derived Data

Redis caches, local caches, search indexes, read models, materialized views, and summary tables can usually be regenerated, yet still carry their own contracts. Record key patterns, value structures, TTLs, namespaces, invalidation strategies, serialization versions, and data sources for rebuilding.

If a new version changes the object structure in cache, the old version may fail to deserialize it while both versions coexist. You may need new namespace/key versions, a mechanism to read both formats during transition, or controlled cache clearing. Do not flush production caches arbitrarily without assessing rebuild load and business impact.

For search indexes, record mappings/analyzers, aliases, reindexing workflows, and data synchronization methods. Changing a mapping may require creating a new index and switching aliases rather than modifying the active index directly.

### 3.4. Files, Object Storage, and Long-Term Stored Data

Record buckets/containers, prefixes, naming conventions, metadata, content types, encodings, encryption, retention, lifecycle, versioning, and access permissions. Identify which application generates the files, who reads them, and whether they are linked in the database or sent externally.

Stored formats such as PDF, images, CSV, JSON, ZIP, or binary files may be consumed by another application years later. If changing structure or encryption algorithms, you must know how to read old data and how to handle already-issued files.

### 3.5. Event Logs, Audits, Sessions, and Operational Data

Survey event stores, audit logs, change history, sessions, persisted tokens, idempotency records, outbox/inbox tables, and retry state. This data is often forgotten because it does not sit in primary business tables, yet it can determine recoverability and correctness after migration.

Clearly record retention duration, deletion rules, payload formats, sensitive data, access controls, and replay capabilities. If events or audit records are retained long-term, the new format must have a strategy for reading old data.

## 4. Listing External Systems

An external system is a component outside the deployment scope and direct control of the module being surveyed. It may be operated by another internal team, supplied by a partner company, or managed by a cloud platform.

Common categories:

- **Identity and access:** Identity Providers, OAuth/OIDC, LDAP, SSO, token issuance services, and key/certificate management.
- **Payments and finance:** payment gateways, banks, reconciliation, e-invoicing, and tax systems.
- **Notifications and communications:** SMTP/email, SMS, push notifications, chat, or notification services.
- **Data and business systems:** CRM, ERP, warehouse systems, shipping, customer management, partners, and reference data sources.
- **Technical platforms:** cloud storage, secrets managers, service discovery, configuration servers, monitoring, logging, tracing, and feature flags.
- **Data integration:** data warehouses, ETL/ELT, BI, reporting systems, and data sharing platforms.
- **Vendor-managed services:** SaaS APIs, commercial SDKs, license servers, verification services, or identity services.

For each system, record its name and purpose, technical/business owner, support contact, environments, connection method, API/SDK versions, data contracts, authentication mechanisms, quotas, SLAs, maintenance schedules, and incident handling procedures. Also note network zones, firewalls, DNS, proxies, certificates, and allowlists if they affect connectivity.

Secrets such as passwords, private keys, access tokens, and connection strings containing credentials must not be copied into survey documents. Record only the secret/config key name, where it is managed, the responsible person or team, and how it is rotated. When sharing documents, readers must know where to find configuration securely without receiving secret values.

For third-party systems, identify what happens when the service is slow, down, changes APIs, or exhausts quota. Document timeouts, retries, fallbacks, circuit breakers, rate limits, and reconciliation mechanisms. A dependency might not cause a build error yet still pose major upgrade risk because vendor contracts or policies change independently.

## 5. Tracing From Source Code to Real Connections in Java

Source code helps locate connection points, yet runtime configuration and operational evidence reveal where the system actually connects. Combine multiple sources to avoid drawing conclusions from a single trace.

### 5.1. Checking Dependencies and Configuration

Read `build.gradle`, `settings.gradle`, or `pom.xml` to find drivers, clients, and integration libraries. For example:

| Trace in Java project | What to investigate |
|---|---|
| Spring Web, `RestClient`, `WebClient`, `RestTemplate`, OpenFeign | HTTP APIs and service discovery |
| `WebServiceTemplate`, SOAP client, WSDL-generated classes | SOAP services and XML schemas |
| gRPC stubs, Protobuf | gRPC services and message schemas |
| `KafkaTemplate`, `@KafkaListener` | Kafka topics, producers, and consumers |
| `JmsTemplate`, `@JmsListener`, AMQP client | Queues, exchanges, and subscriptions |
| JDBC driver, `DataSource`, `JdbcTemplate` | Databases, schemas, and connection pools |
| JPA/Hibernate, MyBatis | Entity mappings, SQL, and database schemas |
| Flyway or Liquibase | History of data structure changes |
| S3/cloud storage SDK, SFTP client | Object storage or file exchange |
| SMTP/mail client, LDAP/OIDC/OAuth client | Email, identity, and access |
| Redis client, search client | Caches or search indexes |

Dependencies only indicate integration capabilities. A library can sit on the classpath without being active; conversely, connections may be created dynamically via reflection, plugins, or external configuration. Therefore, trace where clients are created, where beans are injected, where endpoints are read, and where data is sent/received.

### 5.2. Finding Entry/Exit Points in Source Code

Look for controllers, listeners, scheduled jobs, command-line runners, adapters, repositories, client wrappers, and data transformation classes. Follow the flow from the entry point to where network calls or storage reads/writes occur.

In Spring Boot, traces may include `@RestController`, `@KafkaListener`, `@JmsListener`, `@Scheduled`, `DataSource`, `EntityManager`, `WebClient.Builder`, `RestClient.Builder`, and custom client beans. Do not search only for annotations: an adapter may invoke another service through an interface while the concrete implementation is selected by configuration.

Also inspect configuration in `application.yml`, `application-<profile>.yml`, environment variables, ConfigMaps, secret references, deployment manifests, and platform configuration. When documenting, record only key names and provider sources; do not copy secret values or sensitive production data.

### 5.3. Cross-Checking Against the Running Environment

Source code may differ from production configuration. Cross-check using accessible authoritative sources such as service registries, API gateways, message broker consoles, database catalogs, cloud resource inventories, deployment manifests, logs, metrics, and distributed traces.

Runtime observation helps confirm:

- Which endpoints or topics are actually called.
- Frequency, volume, payload sizes, and peak times.
- Which consumers/producers are active.
- Whether timeouts, retries, DLQs, and connection failures occur frequently.
- Whether unexpected clients or applications are accessing databases/APIs.
- Whether actual versions, schemas, or configurations match documentation.

Do not infer that a connection does not exist merely because it does not appear in a short log window. Monthly jobs, reconciliation tasks, or flows triggered only by rare events might not show up during observation. Ask owners and inspect operational schedules, contract documents, and deployment history.

## 6. Integration Inventory Table Template

Each connection should have its own row or record. If a system has multiple APIs, topics, or schemas with different owners and lifecycles, split them for independent assessment.

| Field | Information to record |
|---|---|
| ID | Stable identifier for the connection or data flow |
| Flow name | Clear business name, for example `order-created-to-fulfillment` |
| Direction | Inbound, outbound, or internal |
| Provider / Consumer | Component producing and component receiving data |
| Target/source system | Service, database, broker, bucket, or vendor name |
| Protocol | HTTPS, JDBC, Kafka, AMQP, SFTP, gRPC... |
| Contract | Endpoint/topic/table/file format, schema, and version |
| Authentication | OAuth2, mTLS, API key, service account...; do not record secrets |
| Data | Key fields, format, encoding, timezone, data classification |
| Frequency/volume | Real-time, event-driven, hourly, daily, sourced volume estimate |
| Errors and recovery | Timeouts, retries, DLQ, idempotency, fallback, replay |
| Owner | Team owning each end and support contact |
| Environment | Dev, test, staging, production, and config differences |
| Evidence | Code/config paths, contracts, dashboards, or verified docs |
| Status | Verified, needs confirmation, deprecated/unused, or unknown |
| Migration risk | Components and versions that may be impacted |

Illustrative example of one inventory row:

| Field | Example value |
|---|---|
| ID | `INT-ORDER-01` |
| Flow name | Publish order-created event |
| Direction | Outbound from Order Service; inbound to Fulfillment Service |
| Provider / Consumer | Order Service / Fulfillment Service |
| Target system | Kafka cluster, topic `order.created` |
| Protocol | Kafka, JSON payload |
| Contract | Event `OrderCreated`, schema version 2 |
| Authentication | Service account and TLS; secrets managed in secret store |
| Data | Order ID, customer ID, currency, total, occurredAt |
| Errors and recovery | At-least-once, idempotent consumer, retries, and DLQ |
| Owner | Order team / Fulfillment team / Platform team |
| Evidence | Producer class, listener class, topic config, and schema registry |
| Status | Verified in staging; need to confirm old consumers in production |
| Migration risk | Old consumer versions may fail to read new fields or new enums |

The values above only illustrate how to fill in the fields. When surveying an actual system, every value must come from the corresponding code, config, owner, or runtime evidence.

## 7. Stored Data Inventory Template

In addition to the integration table, build a separate catalog for each data store. One store may hold multiple tables or collections, yet the relationship between data and the applications using it must be preserved.

| Field | Question to answer |
|---|---|
| Data store | Which database, schema, collection, bucket, cache, or index? |
| Owner | Which team is accountable for data semantics and quality? |
| Producer | Which component creates or updates the data? |
| Consumer | Which component, batch, report, or partner reads the data? |
| Schema/version | How are the current structure and old versions identified? |
| Constraints | Keys, nullability, uniqueness, precision, timezone, encoding? |
| Lifecycle | Retention, archival, deletion, TTL, and backups? |
| Migration | Tool, history, ordering, and rollback capability? |
| Historical data | Can the new version read old data? |
| Transition | Is there backfilling, dual-write, reindexing, or transformation? |
| Protection | Data classification, encryption, access control, and auditing? |
| Evidence | Verified DDL, migration scripts, entity mappings, catalogs, or queries? |

Specifically document shared tables and out-of-application access. A database catalog can tell you an object exists, yet does not necessarily reveal every application using it. Cross-check query logs, access permissions, source code, and owners of related systems.

## 8. Assessing Compatibility Impact From the Inventory

Once the catalog is complete, link each planned change to its related providers, consumers, contracts, and data. Do not assess risk purely by endpoint count; a monthly reconciliation file can matter more than a rarely used API that lacks a fallback.

For each connection, ask:

1. Which side can be upgraded first? Is there a period where a new provider runs alongside an old consumer or vice versa?
2. Does the contract change names, types, required fields, enums, encodings, units, timezones, or meaning?
3. Is there old data, message backlogs, unprocessed files, or caches created by the previous version?
4. Are there consumers outside the team currently doing the work? Who confirms they are ready?
5. If one side rolls back, can data written by the new version still be read?
6. Can contract tests or integration tests be run against real versions on both sides?
7. Are there ways to observe and detect errors after deployment: metrics, logs, traces, DLQs, reconciliation, or alerts?

Results can be grouped for planning:

- **Verified and compatible:** test evidence or contracts confirm supported version combinations.
- **Requires coordinated change:** provider and consumer must deploy in order or require a transition phase.
- **Insufficient evidence:** owner, consumer, schema, or runtime behavior is unclear; investigate before locking the plan.
- **No longer in use:** evidence shows the connection is inactive and the owner confirms it can be removed.

Do not mark a connection as unused merely because it is not found in the source code currently being read. Confirm with owners and inspect scheduled flows, rare flows, or external consumers.

## 9. Step-by-Step Survey Process

A practical workflow can follow these steps:

**Step 1 — Map boundaries and business flows.** Identify modules, environments, inbound/outbound flows, and main data groups. Start from use cases so connections appearing only in one business branch are not missed.

**Step 2 — Locate traces in source code and dependencies.** List clients, listeners, repositories, scheduled jobs, adapters, schemas, migration scripts, and configs. Record specific files/classes or locations as evidence.

**Step 3 — Check deployment configuration.** Cross-check profiles, environment variables, secret references, service discovery, gateways, brokers, databases, and cloud resources. Do not put secret values in the report.

**Step 4 — Confirm with owners on both sides.** Ask about active consumers/producers, contract versions, run schedules, SLAs, quotas, planned changes, and support contacts. Every connection needs an owner confirmation or an explicitly unknown status.

**Step 5 — Cross-check with runtime evidence.** Use logs, metrics, traces, broker dashboards, database catalogs, and batch schedules to confirm actual paths. Record observation timestamps to avoid confusing stale data with current state.

**Step 6 — Build the catalog and version matrix.** Attach providers/consumers, schemas, protocols, owners, and coexisting version pairs. Mark shared flows or flows with existing backlogs.

**Step 7 — Connect the catalog to the migration plan.** For each change, specify required tests, deployment order, rollback plan, monitoring approach, and completion criteria. Information gaps must remain marked for verification rather than guessed.

## 10. Frequently Missed Dependencies

Some connections appear infrequently in main processing paths yet can cause incidents after migration:

- Scheduled jobs, cron tasks, end-of-day/month batches, and jobs running only on special data.
- Callbacks/webhooks from partners calling into the system after a delay.
- Old messages sitting in queues or event stores that are replayed after deployment.
- Files already exported to partners, files awaiting import, or archived files needing re-reading.
- Reports, BI, ETL, and operational scripts accessing the database directly.
- Mobile apps or desktop clients with slower update cycles than the backend.
- Caches, sessions, tokens, cookies, or serialized data shared across application versions.
- Certificates, DNS, firewall rules, proxies, allowlists, TLS versions, and cipher suites.
- Health checks, readiness/liveness probes, service discovery, and autoscaling configs.
- Monitoring agents, log shippers, tracing exporters, and alert rules depending on metric names or log structures.
- License servers, verification services, payment gateways, or vendor APIs with separate quotas and maintenance windows.
- Secret rotation, encryption keys, and data encrypted with old keys.

This list is a prompt for asking questions, not proof that the system uses all of the above. Only add verified dependencies to the catalog, or mark them clearly as hypotheses to test.

## 11. Required Outputs Before Starting Migration

A useful survey should produce outputs that can be reviewed and updated:

- **Context/dependency diagram:** showing the surveyed module, external systems, brokers, databases, and data exchange directions.
- **Integration inventory:** every endpoint, topic, queue, file flow, database connection, and external system, along with provider/consumer, owner, and contract.
- **Data inventory:** data stores, schemas, tables/collections, producers/consumers, retention, and migration history.
- **Sample contract pack:** confirmed OpenAPI/WSDL/Protobuf/Avro schemas, sample JSONs, DDLs, sample files, or sample events.
- **Version matrix:** provider/consumer and old/new data combinations that can coexist.
- **Gap and risk register:** unverified information, unknown consumers, coordinated changes needed, and testing approaches.
- **Owner and evidence list:** who confirmed what, where to verify, and when it was last verified.

The diagram can start simple:

~~~text
                  +----------------------+
                  |  External Partner    |
                  |  HTTPS / JSON        |
                  +----------+-----------+
                             ^
                             | outbound API
                             |
+----------------------------+-----------------------------+
|                    Java Application                       |
|                                                           |
|  REST Controller ---> Business Service ---> Repository    |
|          |                  |                 |            |
|          |                  +----> Kafka      |            |
|          |                         producer   |            |
|          |                                    v            |
|          |                              +-----------+      |
|          |                              | Database  |      |
|          |                              +-----------+      |
|          |                                                 |
|          +---- inbound API                                 |
+-----------------------------------------------------------+
                             |
                             v
                    +------------------+
                    | Kafka Broker     |
                    | topic: ...       |
                    +--------+---------+
                             |
                             v
                    +------------------+
                    | Other Consumer   |
                    +------------------+
~~~

Actual diagrams need component names, protocols, data directions, and owners. If there are multiple consumers, split out each consumer to clearly show the impact of schema changes.

## 12. Survey Completion Criteria

The survey can be considered sufficient to build a migration plan when:

- Key inbound, outbound, internal, and stored data flows have been listed.
- Each connection has a provider, consumer, protocol, contract, or an explicit missing-information status.
- Data stores have identified owners, schemas, producers/consumers, and migration/rollback strategies.
- External systems have documented contacts, environments, authentication, limits, and incident handling mechanisms.
- The source code inventory has been cross-checked against configurations and runtime evidence within accessible scope.
- Out-of-team consumers, rare tasks, backlogged data, and shared connections have been reviewed.
- Compatibility risks are tied to specific versions and have a test method or accountable owner for verification.
- No credentials or secret values exist in the survey documentation.

System inventorying is not a mere list of libraries or endpoints. Its value lies in clarifying the entire path of data, contracts between components, and the people responsible for each connection endpoint. Only once this information is verified can the development team choose an upgrade order, design a transition phase, test version pairs, and prepare rollbacks with controllable risk.
