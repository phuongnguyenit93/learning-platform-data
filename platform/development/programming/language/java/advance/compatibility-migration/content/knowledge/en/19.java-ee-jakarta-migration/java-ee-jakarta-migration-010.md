# Planning Migration by Interdependent Component Groups

Migrating a Java EE system to Jakarta EE is rarely just a matter of renaming `javax.*` to `jakarta.*`. Real applications typically consist of a web container, REST APIs, CDI, JPA, Bean Validation, transactions, messaging, security, JSON/XML libraries, client SDKs, plugins, and business modules. These components link to one another through types in method signatures, annotations, service providers, configuration, databases, HTTP, or queues. Upgrading individual JARs in an arbitrary order can leave the application partially compiling yet failing upon deployment.

A more effective approach is **dividing the migration into groups of tightly interdependent components**, then migrating each group in an order governed by the dependency graph. A group's scope must be wide enough to resolve incompatible API bindings, yet small enough to test and roll back safely.

This lesson presents a method for building an inventory, analyzing graphs, defining *migration units*, partitioning *waves*, choosing compatibility boundaries across groups, constructing a test matrix, and organizing rollout. Examples describe a hypothetical system; module names and versions in examples are not mandatory configurations for every project.

## 1. Why Can Libraries Not Be Migrated One by One?

A legacy Java EE web module may depend directly on:

- `javax.servlet.*` for receiving HTTP requests.
- `javax.ws.rs.*` for exposing REST endpoints.
- `javax.enterprise.*` and `javax.inject.*` for dependency injection.
- `javax.persistence.*` for mapping entities.
- `javax.validation.*` for validation.
- `javax.transaction.*` for Java EE/Jakarta transaction APIs.
- An implementation or framework using reflection to inspect those annotations.

Legacy class example:

```java
import javax.inject.Inject;
import javax.ws.rs.GET;
import javax.ws.rs.Path;
import javax.persistence.EntityManager;

@Path("/orders")
public class OrderResource {
    @Inject
    EntityManager entityManager;

    @GET
    public String list() {
        return "orders";
    }
}
```

If you only upgrade the Jakarta REST implementation while keeping the `javax.ws.rs.Path` resource annotation, the newer runtime may not recognize the class as a REST resource. If you only rename annotations while the container still supplies Jakarta EE 8 APIs in the `javax` namespace, the class may fail to find required types or CDI/JPA may fail to function properly.

**Namespace is part of type identity in Java.** Two similarly named interfaces:

```text
javax.servlet.Filter
jakarta.servlet.Filter
```

are two different types. A class implementing the first does not automatically implement the second. Mixing legacy and newer dependencies in the same runtime can cause `ClassCastException`, `NoClassDefFoundError`, `NoSuchMethodError`, or silent bootstrap failures that do not appear at compile time.

Therefore, a migration group should encompass **the components that must change Java or runtime contracts together** to function as a verifiable unit.

## 2. Identifying the Exact Java EE → Jakarta EE Scope

Distinguish the following milestones:

| Phase | API Namespace Characteristics | Planning Significance |
|---|---|---|
| Traditional Java EE | Standard Java EE APIs reside in `javax.*`. | Baseline for many legacy applications. |
| Jakarta EE 8 | Mostly retains the `javax.*` namespaces of corresponding Java EE APIs. | Rebranding/standards transfer does not yet mean imports changed. |
| Jakarta EE 9 onward | Relevant Jakarta EE APIs migrate to `jakarta.*`. | Significant source/binary incompatibility boundary. |
| Subsequent Jakarta EE releases | Ongoing evolution of APIs, runtimes, and platform baselines. | Read exact compatibility matrices, release notes, and step-by-step migration guides. |

**Do not rename every `javax.*`.** Many `javax` packages belong to Java SE and are unaffected by Jakarta EE migration, such as `javax.sql`, `javax.naming`, `javax.crypto`, `javax.management`, `javax.net.ssl`, `javax.xml.parsers`, and `javax.annotation.processing`.

Additionally, module-level exceptions exist, such as Jakarta transaction APIs versus the Java SE XA API. Import changes must be decided by **API owner, artifact, and the specific specification documentation**, never blanket prefix search-and-replace.

## 3. Sample System Model

Suppose an order management system comprises the following components:

```text
                              External Clients
                                    |
                                    v
                           +------------------+
                           | API Gateway      |
                           +------------------+
                                    |
                           HTTP/JSON (contract)
                                    |
                                    v
                         +----------------------+
                         | order-web.war        |
                         | Servlet + REST       |
                         +----------------------+
                            |                 |
                         CDI/DI          DTO + validation
                            |                 |
                            v                 v
                         +----------------------+
                         | order-service        |
                         | business logic, txn  |
                         +----------------------+
                            |               |
                           JPA              JMS
                            |               |
                   +-------------+    +---------------+
                   | order-data  |    | order-events  |
                   | entities    |    | publisher     |
                   +-------------+    +---------------+
                         |                  |
                       Database           Queue
                         |
              +----------------------+
              | reporting-batch      |
              | data reading/ORM     |
              +----------------------+
```

In reality, these modules also connect to frameworks, an application server, logging, and shared libraries. A plan to “migrate `order-web` first and handle services and JPA later” may be unworkable if modules exchange `javax.persistence.EntityManager` or Jakarta annotations directly.

Conversely, if `reporting-batch` only calls a stable HTTP API, it can upgrade independently of `order-web`. **Data/protocol boundaries** are a critical tool for decoupling migration groups.

## 4. Choosing *Migration Units* Based on Dependencies

A *migration unit* is a set of components upgraded and verified together because no stable compatibility boundary exists within the set.

Example:

| Group | Hypothetical Components | Why Group Together? |
|---|---|---|
| Web/API | Servlets, Jakarta REST runtime, filters, interceptors, authentication integration. | Share Jakarta web APIs and container coupling. |
| CDI/Injection | CDI runtime, bean discovery, qualifiers, interceptors, extensions. | Annotations and lifecycle bind to one dependency injection container. |
| Persistence | JPA API/provider, entities, converters, transaction integration, caches. | ORM/provider and entity annotations must match. |
| Validation | Jakarta Validation API/provider, DTO annotations, REST/JPA integration. | Validation bootstrap and annotation namespaces must align. |
| Messaging | Jakarta Messaging API/provider adapters, producers, consumers, MDBs if any. | Messaging runtime, transactions, and listener integration couple tightly. |
| Build/Runtime | JDK, frameworks/BOM, server, Maven/Gradle plugins, test containers. | Governs Java baseline and supported artifact combination. |
| Boundary contracts | JSON schemas, XML schemas, HTTP routes, message schemas, DB schemas. | Boundaries that must stay stable while two cohorts coexist. |

Not every row in this table is an independent deployment unit. For a WAR on an application server, Web, CDI, JPA, Validation, and server integration often form **one migration unit that must move together**. With microservices communicating via HTTP/queues, you can group per service and rely on protocol contracts to migrate sequentially.

## 5. Establishing Source and Target States

Before partitioning groups, create an **inventory with real versions**. Record for each component:

- Module/service name, source location, output artifact, and owner.
- Source JDK, target JDK, and committed Java runtime baseline.
- Runtime: application server, servlet container, embedded framework, or batch launcher.
- Java EE/Jakarta EE spec API versions used in code.
- Corresponding implementations/providers: JPA, CDI, JAX-RS, validation, messaging.
- Actually resolved direct and transitive dependencies.
- Communication contracts with other modules/services.
- Data storage locations and current schema/format versions.
- Special classloader/module-path/classpath rules and runtime plugins.
- Business criticality and rollback capability.

Abbreviated profile example:

```yaml
component: order-web
artifact: order-web.war
owner: order-team
sourceRuntime: legacy-app-server
targetRuntime: jakarta-compatible-server
sourceApiFamily: javaee-javax
targetApiFamily: jakarta
jdkBaseline: 17
integrationBoundaries:
  - http: /api/orders
  - module: order-service
  - event: OrderCreated
dependencies:
  - order-service
  - common-web-filters
  - json-codec
tests:
  - order-api-contract
  - authentication-integration
  - persistence-smoke
rollbackNeeds:
  - old-and-new-message-readers
status: planned
```

Illustrative records do not guarantee a particular server supports all those versions together. In an actual migration, choose a **JDK, framework, and server stack with a verified compatibility matrix**, rather than picking solely by Java feature-release number.

## 6. Gathering the Dependency Graph from Multiple Sources

No single tool uncovers every kind of dependency. Combine:

1. **Build dependency graph:** Maven, Gradle, BOMs, transitive dependencies.
2. **Source dependency graph:** imports, method signatures, annotations, and module references.
3. **Binary dependency graph:** `jdeps`, class-file references, package/API usage.
4. **Runtime integration graph:** CDI, JPA, SPI, reflection, `ServiceLoader`, and container-managed resources.
5. **Data-flow graph:** HTTP, events, JDBC tables, batch files, JSON/XML, database migrations.
6. **Operational graph:** startup ordering, deployment pipelines, secrets, ports, shared servers.

### 6.1. Maven

```bash
mvn dependency:tree
```

In multi-module projects, run per relevant module and specify scopes (`compile`, `runtime`, `test`). Parent POMs or BOMs can override versions not explicitly listed in a module's `pom.xml`.

To inspect inherited settings:

```bash
mvn help:effective-pom
```

This complements configuration visibility yet does not replace the dependency tree for locating transitive dependencies and actual runtime artifacts.

### 6.2. Gradle

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
    --dependency jakarta.persistence \
    --configuration runtimeClasspath
```

Select the proper configuration and subproject, because test, build plugin, compile, and runtime dependencies can differ.

### 6.3. `jdeps`

```bash
jdeps --recursive --multi-release 17 \
    --class-path "libs/*" \
    build/libs/order-service.jar
```

This illustrates analyzing an artifact's static dependencies on a JDK supporting those flags. `--multi-release 17` applies when inspecting multi-release JARs; it is **not** a way to make `jdeps` rewrite sources to Java 17. On Windows, path/wildcard separators depend on the shell and tool.

`jdeps` surfaces class references to `javax`/`jakarta` packages, yet cannot automatically spot references stored only in XML, reflection strings, deployment descriptors, or message payloads.

### 6.4. Searching Sources and Configurations

Keywords to audit in context:

```text
javax.servlet
javax.ws.rs
javax.persistence
javax.enterprise
javax.inject
javax.validation
javax.jms
javax.transaction
web.xml
persistence.xml
beans.xml
META-INF/services
Class.forName
ServiceLoader
```

Some `javax.*` strings are valid Java SE APIs; do not automatically flag all matches for conversion.

## 7. Representing a Directed Dependency Graph

Define an edge `A -> B` if **A depends on B**. Example:

```text
order-web -----------> order-service -------> order-data
    |                       |                     |
    v                       v                     v
common-web             transaction-api        JPA provider
    |                       |
    v                       v
Servlet/JAX-RS          CDI integration
```

In an acyclic graph, typically upgrade **foundational dependencies** before **consumers**, or prepare a compatible release of the foundational dependency before migrating consumers.

For large graphs, drawing at fine technical granularity becomes unreadable. Use two tiers:

- **Component graph:** JAR/WAR/service modules, frameworks, servers, and artifacts.
- **Contract graph:** Java interfaces, REST endpoints, queue schemas, and database schemas exchanged between components.

The component graph shows what must build/deploy together. The contract graph shows which groups can coexist across versions.

## 8. Hard Dependencies vs Soft Dependencies

An edge is not merely binary “yes” or “no”; label how separable it is:

| Relationship Type | Example | Independence for Migration |
|---|---|---|
| Java type signature | Module accepts `javax.persistence.EntityManager`. | Very low if signature mandates old namespace. |
| Container-managed integration | CDI bean injected into JAX-RS resource. | Low when sharing one Jakarta runtime. |
| Shared framework internals | Module calls internal framework APIs. | Low and high-risk. |
| JPA entity annotations | Provider scans entities using a specific annotation namespace. | Usually requires syncing provider and metadata. |
| HTTP/JSON contract | Service A calls Service B via stable JSON DTOs. | Higher if backward/forward compatibility holds. |
| Queue event schema | Producer/consumer share versioned Avro/JSON/XML schemas. | Separable if readers accept both formats. |
| Database schema | Two services mutate the same table. | High risk; needs backward-compatible migrations and coordination. |
| CLI/file exchange | Batch reads versioned files. | Can be independent if format contract is preserved. |

Annotate **hard/soft coupling** on every edge with rationale. Do not partition groups purely by directory layout or package names.

## 9. Dependency Cycles and Strongly Connected Components

Long-lived monoliths often contain cycles:

```text
order-web -> order-service -> common-domain
    ^                             |
    |                             |
    +-----------------------------+
```

If all three modules call each other through interfaces containing `javax.*` types, upgrading just one module is infeasible.

In graph theory, a **strongly connected component (SCC)** is a set of nodes mutually reachable along directed edges. You can treat each SCC as a candidate migration unit, then contract them into a directed acyclic graph (DAG).

However, an **SCC does not automatically require deploying together** in every scenario. If one edge in the cycle is replaced by a compatible REST/queue interface or stable adapter, the SCC breaks apart. Therefore, plans should evaluate:

1. Migrating the entire SCC in one wave if scope and verification remain manageable.
2. Or proactively breaking the cycle via decoupled interfaces, adapters, or clear boundaries.
3. Then re-analyzing the resulting DAG and migration order.

Breaking groups by **changing dependency boundaries** is architectural design, not mere import rewriting.

## 10. Java-Level Boundaries Differ from Protocol Boundaries

This is the single most important design decision when running two namespaces concurrently.

A Java interface like:

```java
public interface OrderHandler {
    void handle(javax.servlet.http.HttpServletRequest request);
}
```

cannot simply serve as an interface accepting `jakarta.servlet.http.HttpServletRequest`. The two types are not assignable to each other.

A more decoupled boundary:

```java
public interface OrderHandler {
    OrderResult handle(OrderCommand command);
}
```

using DTOs free of Servlet/JPA/CDI types reduces namespace coupling. Both legacy and Jakarta web adapters can translate their respective environment requests into the same `OrderCommand`.

Structure:

```text
Legacy Servlet adapter (javax) ----+
                                    |
                                    v
                            Domain contract
                                    ^
                                    |
Jakarta Servlet adapter -----------+
```

**Precondition:** the shared contract must truly be container-independent, neither returning nor accepting incompatible Java EE/Jakarta types. Across two separate processes, crossing HTTP/queues also avoids classloader and type-identity conflicts. Within a single JVM, classpaths and runtimes must still remain conflict-free.

## 11. Choosing a Transition Strategy: Big-Bang, Waves, or Strangler

### 11.1. One-Shot / Coordinated Migration

Upgrade an entire deployable application and its runtime in one coordinated change.

Suitable when:

- A single WAR/EAR has tightly coupled API namespaces.
- Runtime/container disallows mixing two API generations in one deployment.
- Automated tests are strong and full-deployment rollback is viable.
- External data/schemas stay unchanged or are already bidirectional.

Drawbacks include larger blast radius, longer integration phases, and harder root-cause triage if frameworks, JDK, and DB schemas change simultaneously.

### 11.2. Wave-Based Migration

Split components into independently testable/deployable groups, upgrading foundational groups or boundary-stable groups first.

Example:

```text
Wave 0  -> Baseline + dependency inventory + contract tests
Wave 1  -> Decouple domain API from javax/Jakarta, standardize DTOs
Wave 2  -> Upgrade runtime/framework/BOM for a pilot deployable
Wave 3  -> Web + CDI + Validation + JPA in the same deployment
Wave 4  -> Messaging + batch + integrations and dependent consumers
Wave 5  -> Remove adapters, old configurations, regression hardening
```

This ordering is illustrative. In another system, messaging might need to migrate earlier or share a wave with JPA due to shared transaction boundaries.

### 11.3. Strangler-Style Migration

Keep the legacy application running while moving features piece by piece into a new Jakarta application/runtime communicating via APIs or events.

Suitable when a system is too large for one upgrade, requires continuous delivery, and supports clean data boundaries. Account for routing, authorization, duplicate processing, distributed transactions, and data ownership.

**Never treat running two systems in parallel as free:** operational complexity, data synchronization, and dual business rules increase during transition.

## 12. Grouping by *Runtime Compatibility Cohort*

In Java EE/Jakarta, runtimes commonly dictate conversion boundaries:

| Component | Compatibility Questions to Verify |
|---|---|
| Jakarta Servlet / web container | Does the container support the target API namespace and spec version? |
| Jakarta REST runtime | Does the JAX-RS implementation/version align with container, CDI, and JSON providers? |
| Jakarta CDI | Are CDI API, bean discovery, interceptors, and extension providers from the same generation? |
| Jakarta Persistence | Are JPA API, ORM provider, enhancement, mapping, caches, and transactions compatible? |
| Jakarta Validation | Are Validation API, implementation, EL provider, and REST integration synchronized? |
| Jakarta Messaging | Do JMS API/provider/client, connection factories, and transaction integration align? |
| Jakarta Security | Do authentication/authorization integrations, filters, and security constraints still work? |
| JSON/XML Binding | Are JSON-B/Jackson/JAXB providers, namespaces, and wire formats stable? |
| Application server | Do server BOM/spec profiles, classloading rules, and deploy descriptors match? |

There is no rule that “every artifact carrying a `jakarta` prefix is compatible.” For example, an API may be supplied by the container while the app packages a competing implementation inside the WAR, triggering duplicate classes or provider conflicts. Consult the official **combined support matrix**, not individual libraries in isolation.

## 13. Select Runtime and Framework Before Locking the Dependency BOM

Swapping only Jakarta API JARs does not turn an old application server into a Jakarta runtime. The application server or embedded framework creates servlets, manages CDI/JPA, coordinates transactions, handles messaging, and drives lifecycle services.

Target selection process:

1. Determine JDK target and support lifecycle.
2. Choose an application server or framework supporting the required Jakarta spec version.
3. Verify whether the runtime ships the needed spec implementations/profiles or needs external providers.
4. Select the matching framework or runtime BOM/dependency management.
5. Identify which dependencies are **provided** by the container vs packaged by the app.
6. Verify build/test/deploy plugins and container base images.
7. Lock one verified combination before migrating multiple modules.

Maven example when the runtime supplies the Servlet API:

```xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <version>VERSION_COMPATIBLE_WITH_CONTAINER</version>
    <scope>provided</scope>
</dependency>
```

The version above is a placeholder; replace it with the version supported by your runtime. Avoid blindly selecting the newest release and bundling a mismatched API JAR into a WAR. With embedded servers, dependency layouts differ: implementation/container artifacts typically sit on the application's runtime classpath.

## 14. Example: Migrating a Servlet Filter Group

A legacy filter:

```java
import javax.servlet.Filter;
import javax.servlet.FilterChain;
import javax.servlet.ServletException;
import javax.servlet.ServletRequest;
import javax.servlet.ServletResponse;
import java.io.IOException;

public final class LegacyRequestFilter implements Filter {
    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {
        chain.doFilter(request, response);
    }
}
```

Jakarta version:

```java
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import java.io.IOException;

public final class JakartaRequestFilter implements Filter {
    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {
        chain.doFilter(request, response);
    }
}
```

The source diff looks tiny, yet the group scope also includes:

- Server/container instantiating the filter.
- `web.xml` or `@WebFilter` annotations.
- Framework/security filters running before/after.
- `FilterRegistration` if registered programmatically.
- Libraries accepting `ServletRequest`/`FilterChain` in public signatures.
- Servlet API version targeted by the framework.
- Session/cookie/authentication integration and test infrastructure.

If a security filter library lacks Jakarta Servlet support, renaming imports in application filters does not make that library compatible. Upgrade or replace the library within **the same web/security group**.

## 15. Example: Migrating CDI + JPA + Validation Together

A legacy service combining all three:

```java
import javax.enterprise.context.ApplicationScoped;
import javax.inject.Inject;
import javax.persistence.EntityManager;
import javax.transaction.Transactional;
import javax.validation.Valid;

@ApplicationScoped
public class OrderService {
    @Inject
    EntityManager entityManager;

    @Transactional
    public void create(@Valid OrderInput input) {
        entityManager.persist(
                new OrderEntity(input.reference()));
    }
}
```

Jakarta equivalent:

```java
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import jakarta.persistence.EntityManager;
import jakarta.transaction.Transactional;
import jakarta.validation.Valid;

@ApplicationScoped
public class OrderService {
    @Inject
    EntityManager entityManager;

    @Transactional
    public void create(@Valid OrderInput input) {
        entityManager.persist(
                new OrderEntity(input.reference()));
    }
}
```

`OrderInput` and `OrderEntity` here are application-defined DTO/entity types. To run properly, also verify:

- A JPA provider supporting `jakarta.persistence.*`.
- Entity annotations, entity scanning, custom converters, and named queries.
- CDI runtime and extension libraries.
- Transaction manager and propagation semantics.
- Bean Validation provider and annotation metadata.
- `persistence.xml`, `beans.xml`, datasources, and transaction settings.
- Test runners and containers booting the right CDI/JPA/transaction generation.

This exemplifies a **container-lifecycle tightly coupled group**. Compiling `OrderService` alone does not verify container bootstrap or transaction behavior.

## 16. Planning Around Interleaved Java EE and Java SE APIs

A project may contain hundreds of `javax` imports, part of which lie outside Jakarta's scope.

Example:

```java
import javax.sql.DataSource;     // Java SE: keep unchanged
import javax.naming.InitialContext; // Java SE: keep unchanged
import javax.crypto.Cipher;     // Java SE: keep unchanged

import javax.persistence.Entity; // Java EE/Jakarta: review required
import javax.ws.rs.Path;        // Java EE/Jakarta: review required
```

These annotations classify **API ownership**, without implying every class is always present in every JDK distribution. When upgrading JDKs, certain Java EE modules once distributed inside the JDK were removed; for instance, JEP 320 removed the Java EE/CORBA modules starting in JDK 11.

For precise planning, build a mapping table:

| Old Symbol/Artifact | API Owner | New Symbol/Artifact | Action |
|---|---|---|---|
| `javax.servlet.Filter` | Servlet / Jakarta Servlet | `jakarta.servlet.Filter` | Migrate with web container/framework. |
| `javax.persistence.Entity` | JPA / Jakarta Persistence | `jakarta.persistence.Entity` | Migrate with ORM/provider. |
| `javax.validation.Valid` | Bean Validation / Jakarta Validation | `jakarta.validation.Valid` | Migrate with validator integration. |
| `javax.jms.Message` | JMS / Jakarta Messaging | `jakarta.jms.Message` | Migrate with provider/client. |
| `javax.xml.bind.JAXBContext` | JAXB / Jakarta XML Binding | `jakarta.xml.bind.JAXBContext` per target. | Verify separate API/runtime and XML contracts. |
| `javax.sql.DataSource` | Java SE JDBC API | Keep `javax.sql.DataSource`. | Do not bulk-replace. |
| `javax.naming.InitialContext` | Java SE JNDI API | Keep `javax.naming.InitialContext`. | Verify JNDI resources when switching servers. |
| `javax.annotation.processing.Processor` | Java SE compiler API | Keep `javax.annotation.processing.Processor`. | Do not rename for Jakarta namespaces. |

A documented mapping listing API owners and official sources beats any blind `javax.` search-and-replace script.

## 17. Hidden Dependencies to Include in Groups

An application can depend on a library at runtime without importing it directly in source.

### 17.1. Reflection and Annotation Scanning

Frameworks often resolve classes by string name or annotation:

```java
Class<?> type = Class.forName(configuredClassName);
```

If `configuredClassName` still points to an old provider package, compilation succeeds while runtime fails. Check properties files, XML descriptors, bean scanning rules, and generated metadata.

### 17.2. Service Provider Interface

`META-INF/services` may contain provider names or service interfaces using old namespaces. If a library migrates to `jakarta.*`, service config files, module descriptors, and providers must update together to follow the new contract.

### 17.3. Generated Code

OpenAPI clients, JAXB/XJC, JPA metamodels, QueryDSL, annotation processors, or other generators can emit `javax.*` imports even after handwritten sources migrate.

Inventory generators and their versions, enforcing the right order: **upgrade generators and templates before regenerating code**. Never patch generated outputs by hand only for the next build to overwrite them.

### 17.4. Container Descriptors

Files such as `web.xml`, `persistence.xml`, `beans.xml`, and transaction or security descriptors carry XML namespaces and schema versions. Do not update only Java imports; align descriptor schemas with the target runtime.

### 17.5. Plugins and Third-Party Extensions

CDI extensions, Hibernate listeners, servlet filters, JAX-RS filters, and test runners can bind to legacy namespaces. Every plugin needs a compatible release or replacement plan.

## 18. Selecting Wave Order from the Dependency Graph

After contracting inseparable groups, a DAG emerges:

```text
Core DTO/contract
       |
       +----> Persistence integration
       |             |
       |             v
       +----> Domain service ------> Web + API
       |                                 |
       +----> Event contract             +----> external clients
                     |
                     v
                Messaging adapters
                     |
                     v
                 Batch consumers
```

When edges represent “consumer depends on provider,” prepare a **compatible provider** before upgrading consumers. However, deployment order follows contracts at the boundaries.

Examples:
- If REST consumer V1 rejects unknown fields, upgrade consumers before producers emit new fields.
- If a new DB schema breaks the legacy app, expand the schema in a backward-compatible way first.
- If two modules pass Jakarta Java types directly inside one WAR, upgrade them together.
- If message formats are versioned and consumers tolerant, producers and consumers can migrate in separate waves per contract.

In short, **build order from Java dependencies** and **rollout order from data/protocol boundaries** can differ. Express both in the plan rather than relying on one flat module list.

## 19. Wave Plan Table with Entry/Exit Criteria

Example for an ordering system:

| Wave | Goal | Components | Entry Criteria | Exit Criteria |
|---|---|---|---|---|
| 0 — Baseline | Establish current state. | Build, CI, dependency inventory, contract fixtures. | Working production system. | Legacy build and tests are reproducible. |
| 1 — Decouple boundaries | Stop public domain APIs from exposing `javax.*`. | DTOs, domain APIs, adapters. | Dependency graph understood. | Contracts container-independent and tested. |
| 2 — Runtime pilot | Validate target Jakarta stack. | Server/framework/BOM + one small feature. | Target support matrix validated. | Bootstrap, auth, JPA, logging, and deploy succeed. |
| 3 — Core app | Migrate primary deployable app. | Servlet/REST/CDI/JPA/Validation. | Compatible plugins/providers ready. | Integration/contract tests green. |
| 4 — Integrations | Migrate messaging, batch, related client SDKs. | JMS, REST clients, batch. | Wire contracts support parallel execution. | Zero unsupported legacy namespace call paths left. |
| 5 — Cleanup | Remove legacy bridges. | Old configs, transformers, legacy imports. | No traffic/data needs legacy behavior. | Rollback plan and evidence recorded. |

A wave is never finished merely because source compiles. Require measurable **exit criteria**: passing tests, successful deployments, compatible contracts, healthy resource metrics, and validated rollback steps.

## 20. Using *Expand → Migrate → Contract* for Data Boundaries

When two groups upgrade at different times, data contracts must support coexistence.

### 20.1. Expand

Deploy consumers able to read both old and new formats. If renaming a JSON field, readers accept legacy aliases during transition. If changing DB schemas, add new columns without dropping columns still needed by legacy apps.

### 20.2. Migrate

Gradually switch producers to the new format or run controlled dual-write/dual-read. Monitor counts of legacy-format messages/records and un-upgraded clients.

### 20.3. Contract

Remove legacy read paths only once stored data is migrated or expired and zero legacy consumers remain. Deletion requires evidence, an owner, and rollback verification.

JSON example:

```json
{
  "eventVersion": 2,
  "orderId": "ORD-10",
  "status": "CREATED",
  "occurredAt": "2026-11-12T00:00:00Z"
}
```

This illustrates an event schema, **unrelated directly** to `javax` vs `jakarta` packages. Java namespaces are a source/binary concern; JSON wire schemas are an independent contract. Separating the two lowers migration risk.

## 21. Shared Databases and Transaction Boundaries

A successfully migrated JPA group may still conflict with a database schema shared across multiple applications.

Verify:

- Old and new entity mappings targeting the same tables/columns.
- ID/key generation, optimistic locking, and transaction isolation.
- Whether schema migrations are backward-compatible.
- Whether DB-serialized payloads (JSON/XML/blobs) changed format.
- Which drivers/ORMs batch and reporting services use.
- Whether second-level and query caches remain compatible.
- Whether legacy apps still run cleanly after schema upgrades.

A classic dangerous mistake is dropping a column alongside deploying the new Jakarta app while a legacy Java EE batch job still queries that column.

A safer sequence:
1. Add new columns or views without breaking legacy read paths.
2. Run data backfills with completeness checks.
3. Roll out new code reading/writing according to plan.
4. Migrate remaining consumers.
5. Drop old schema objects once zero dependencies remain proven.

For multi-service transactions, never assume splitting services into independent runtimes keeps distributed transactions atomic as before. You may need outbox, idempotency, or compensation flows; those are architectural changes requiring separate design and testing.

## 22. Differences Between Monolith and Microservice Migrations

### 22.1. Multi-Module Monolith / EAR

In a traditional EAR or WAR, modules often share:

- One application server.
- CDI/JPA transaction contexts.
- Classloader hierarchies.
- Entity objects and local Java interfaces.
- Security realms and JNDI resources.

Thus, even when sources split across multiple Maven/Gradle modules, the **deployable/runtime boundary** may force them to move together. Modules can shift namespaces separately only behind adapter boundaries and classloading isolation genuinely supported by the runtime.

### 22.2. Microservices Over HTTP/Queues

Each service can adopt a Jakarta runtime independently if wire protocols remain compatible:

```text
Legacy service (Java EE / javax)
              |
              | HTTP/JSON
              v
New service (Jakarta / jakarta)
```

These services do not send `javax.servlet.HttpServletRequest` or `jakarta.servlet.HttpServletRequest` across the network; they exchange JSON, HTTP statuses, headers, or event schemas.

Preconditions require explicit contracts: authentication, correlation IDs, retry/idempotency, versioned payloads, timezones, error semantics, and rollout ordering. Do not assume “separate processes means independent migration” if shared databases or transactions still couple them tightly.

## 23. Using Adapters to Shrink Must-Move-Together Groups

An adapter keeps domain contracts stable while the outer layer adapts to the runtime.

Domain API example:

```java
package com.example.order.domain;

public record CreateOrderCommand(
        String customerId,
        String productCode,
        int quantity) {
}

public interface CreateOrderUseCase {
    String create(CreateOrderCommand command);
}
```

Jakarta-side Servlet adapter:

```java
package com.example.order.web;

import com.example.order.domain.CreateOrderCommand;
import com.example.order.domain.CreateOrderUseCase;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

public final class OrderServlet extends HttpServlet {
    private final CreateOrderUseCase useCase;

    public OrderServlet(CreateOrderUseCase useCase) {
        this.useCase = useCase;
    }

    @Override
    protected void doPost(
            HttpServletRequest request,
            HttpServletResponse response)
            throws IOException {
        String id = useCase.create(new CreateOrderCommand(
                request.getParameter("customerId"),
                request.getParameter("productCode"),
                Integer.parseInt(request.getParameter("quantity"))));
        response.setContentType("text/plain");
        response.getWriter().write(id);
    }
}
```

This illustrates **type boundaries**. Instantiating/registering a servlet with constructor-injected dependencies must follow your container or framework; containers do not automatically invoke parameterized constructors during standard servlet scanning. Real apps may use CDI, a DI framework, or programmatic servlet registration.

Do not use this sample verbatim in production: add input validation, authentication, HTTP error handling, and proper transaction semantics.

An adapter prevents domain layers from exposing `HttpServletRequest` or `EntityManager` in public APIs. Changing web runtimes then avoids coupling all business logic to Jakarta APIs.

## 24. Tools for Source and Bytecode Rewriting

Automated migration tools help cut manual errors:

- **OpenRewrite:** applies framework- or dependency-specific recipes across sources and build files.
- **Eclipse Transformer:** transforms certain Java EE/Jakarta namespaces across archives/classes/resources per rule sets.
- **IDE refactorings and build tools:** update imports, annotations, configs, and generators.
- **Static API diff tools:** inspect version differences and incompatible APIs.
- **`jdeps`:** investigates bytecode-level package references.

### 24.1. When to Use Tools?

When hundreds of imports/annotations change, automation saves substantial time. Yet tools do not decide for you:
- Whether the target runtime/container supports the version combination.
- Which components must upgrade together.
- Which Java SE `javax.*` packages must stay untouched.
- Whether semantics, security, or data contracts shifted.
- Whether test coverage and rollback readiness are sufficient.

### 24.2. Controlling Transformed Outputs

When applying bytecode transformers to third-party artifacts during transition, record version, checksum, origin, and license of transformed outputs; never assume a transformed artifact carries the vendor's official support/security guarantees.

Automated source rewrites also do not fix incompatible DB schemas, JMS providers, or runtime extensions lacking Jakarta support. After rewriting, still verify compile, bootstrap, integration, contract tests, and packaging.

## 25. Building a Group Compatibility Matrix

Example matrix requiring verification:

| Group | Java Baseline | Runtime/Framework | API Namespace | Status |
|---|---|---|---|---|
| Web + CDI | Target Java | Jakarta-capable target | `jakarta.*` | Needs plugin/security filter verification. |
| JPA + transaction | Target Java | Compatible ORM + transaction manager | `jakarta.persistence.*` | Needs entity scan and transaction tests. |
| Validation | Target Java | Compatible Validation provider | `jakarta.validation.*` | Needs DTO and integration tests. |
| Messaging | Target Java | Compatible broker client + provider | `jakarta.jms.*` | Needs connection and redelivery tests. |
| Legacy reporting | Source/target Java per plan | Batch runner | Can keep `javax.*` temporarily | Separable only if boundaries stay compatible. |
| Domain contracts | Shared Java baseline | Container-independent | Exposes no container APIs | Needs contract tests. |

Fill every final cell with **real versions** linked to official compatibility matrices. Templates do not certify any specific Java or provider version.

## 26. Dependency Contracts for Wave Rollout

A group must hold a “neighbor compatibility” contract before upgrading independently:

```yaml
migrationGroup: web-jakarta
target:
  runtime: "selected-jakarta-runtime"
  java: "supported-jdk"
  namespace: "jakarta"
dependsOn:
  - domain-contract-v2
  - persistence-jakarta
  - validation-jakarta
boundaries:
  http:
    read: [v1, v2]
    write: v1
  database:
    schema: expanded
entryCriteria:
  - target-dependencies-resolved
  - integration-env-ready
  - contract-tests-baselined
exitCriteria:
  - deploy-successful
  - auth-and-session-tests-pass
  - persistence-and-transaction-tests-pass
  - http-contracts-pass
rollback:
  old-runtime-readable-data: true
  rollback-procedure-tested: true
```

Values in this YAML are illustrative. Real teams may track these in issue trackers, ADRs, or planning tables; what matters is **measurable entry/exit criteria**, not which management tool stores them.

## 27. Testing Around Dependency Boundaries

Running only per-module unit tests easily misses bugs sitting at integration seams.

| Boundary | Priority Tests |
|---|---|
| Servlet / REST / security | Endpoint routing, filter chains, auth, session/cookie, error mapping. |
| CDI / injection | Bean discovery, qualifiers, lifecycle, interceptors, producer methods. |
| JPA / transaction | Entity scanning, schema mapping, rollback, lazy loading, locking. |
| Validation | Constraints, custom validators, message interpolation, REST/JPA hooks. |
| JMS / queue | Serialization, message listeners, ack, redelivery, transactions, idempotency. |
| JSON / XML | Golden fixtures, backward/forward compatibility, namespaces/schemas. |
| JDBC / database | Drivers, connection pools, migrations, transaction isolation. |
| Shared domain API | Binary/source compatibility, DTO round-trips, adapter tests. |
| Deployment / container | Startup, CDI/JPA bootstrap, JNDI, packaging, modules/classloaders. |

### 27.1. Separate Three Test Tiers

- **Component tests:** verify logic within a module using appropriate test doubles.
- **Integration tests:** boot real providers/containers to verify CDI, JPA, JMS, and REST runtimes.
- **Contract/end-to-end tests:** verify behavior across HTTP, events, DBs, or external clients, especially during two-generation coexistence.

Compiling tests against Jakarta APIs does not prove the runtime provides matching implementation providers. Execute against representative target runtimes or test containers.

### 27.2. Compare Semantic Outcomes, Not Just Build Status

Newer serializers or JSON providers may change field ordering, null inclusion, or date formatting. When contracts demand equivalent payloads, use semantic assertions; when payloads are cryptographically signed raw bytes, check byte-level canonicalization. Never make tests pass by updating golden outputs blindly if the new output breaks old contracts.

## 28. Testing Migration in CI

A sensible pipeline can split as follows:

```text
                 PR source/build
                       |
                       v
               Dependency resolution
                       |
                       v
             Compile + static analysis
                       |
              +--------+--------+
              |                 |
              v                 v
       Component tests    Contract fixtures
              |                 |
              +--------+--------+
                       |
                       v
       Deploy to representative Jakarta runtime
                       |
                       v
              Integration tests
                       |
                       v
          Mixed-version compatibility tests
                       |
                       v
          Security/performance checks
                       |
                       v
                Release candidate
```

During transition, two test tracks may be needed:
- **Legacy mode:** run current code against expanded boundary contracts.
- **Target mode:** run the Jakarta cohort on the new runtime.

Testing only target mode risks missing regressions breaking old clients/producers. Testing only legacy mode fails to prove target deployment readiness.

## 29. Managing Configuration and Deployment Descriptors

Java EE/Jakarta consists of more than source code. Inspect:

- Namespaces and versions in `web.xml`, `beans.xml`, `persistence.xml`, and related descriptors.
- Resource/JNDI names and datasource configurations.
- Servlet context paths, HTTP headers, session persistence, and cookie policies.
- Authentication providers, roles, and security constraints.
- Transaction timeouts, pool sizing, and persistence unit names.
- Logging, metrics, tracing, and health probes.
- Build plugins packaging WAR/EARs and container library resolution order.
- Embedded vs externally managed container mode.

Changing servers can introduce different defaults even after fixing API sources. Never relax security defaults solely to mimic legacy behavior without an explicit security review.

## 30. Planning Rollback Alongside Migration

After upgrading a group, production incidents may require rolling back. Your rollback plan must answer:

1. Can the older artifact still deploy on the current runtime?
2. Must the older application server also be restored, or only the WAR?
3. Are updated DB schemas still compatible with the old application version?
4. Can legacy consumers read events/messages emitted by the new version?
5. Are there in-flight transactions or messages requiring draining?
6. Are caches/session states incompatible across both versions?
7. If running two systems in parallel, how do routing and data ownership revert?

Examples:
- If moving from `javax.servlet.*` to `jakarta.servlet.*` alongside swapping containers, rollback may require reverting the entire image/container.
- If a DB schema dropped a column required by the old app, rolling back code alone fails.
- If new messages contain an enum value unknown to legacy consumers, legacy consumers may fail after rollback.

When planning waves, minimize irreversible changes in early waves. Whenever data migrations are mandatory, have tested backup/restore or dual-read strategies.

## 31. Handling Third-Party Dependencies Without Jakarta Releases

Not every plugin or library provides a compatible release when your project needs to upgrade. Options:

| Option | When Appropriate | Trade-off |
|---|---|---|
| Wait/move to official Jakarta release | Library is maintained with a clear roadmap. | May delay migration schedule. |
| Replace with an equivalent library | Alternatives exist with fitting APIs/support. | Requires code changes and behavioral tests. |
| Build an adapter or split process | Library supports only `javax` yet isolates cleanly behind a contract. | Adds operational/serialization latency. |
| Apply controlled bytecode transformer | Library is nearly compatible and transform rules are thoroughly tested. | Risks around vendor support, security, reflection, dynamic resources. |
| Defer the entire migration unit | Tight coupling cannot yet be broken. | Continues carrying legacy JDK/runtime risk. |

Never try running a third-party `javax.servlet.Filter` inside a container accepting only `jakarta.servlet.Filter` without a valid adapter/bridge mechanism. They are distinct Java types.

For critical libraries lacking solutions, record an **owner-assigned blocker** and decision plan rather than silently marking the wave complete.

## 32. Choosing Between Shared Code and Parallel Adapters

Sometimes an internal API library must serve both legacy and Jakarta applications:

### 32.1. Extract Container-Independent Core

Prefer this wherever possible. Domain contracts like `OrderCommand` and `OrderResult` import neither Servlet/JPA nor CDI, enabling one shared artifact.

### 32.2. Dual Namespace Adapters

You can publish:
- `order-web-javax` for legacy runtimes.
- `order-web-jakarta` for newer runtimes.

Both delegate to the shared core API. Prevent both adapters from landing together in an incompatible classloader/runtime. Manage dependency graphs, artifact coordinates, CI matrices, and release versions explicitly.

### 32.3. Two Long-Lived Branches

Use only when no cleaner option exists. Parallel branches invite drift, out-of-sync security patches, and double maintenance. When unavoidable, define sunset dates, backport rules, and legacy traffic metrics.

## 33. Risk Matrix and How to Prioritize Groups

Never prioritize purely by “which module has the fewest files.” A small group owning authentication or payments carries far higher risk than a large group rendering read-only reports.

Score across dimensions:

| Risk Dimension | Question |
|---|---|
| Tight coupling | How many direct dependencies use `javax/jakarta` types? |
| Runtime coupling | Does it share a container, transaction manager, or classloader? |
| Data impact | Does it write DBs/queues or alter long-lived storage formats? |
| Test coverage | Do representative contract/integration tests exist? |
| Business criticality | Does it affect revenue, authentication, or compliance? |
| Rollbackability | Can it revert without complex data repair? |
| Third-party blockers | Are there plugins lacking Jakarta support? |
| Operational impact | Must servers, images, certificates, or networking change? |

A simple 1–5 scale per dimension provides an **indicative** score rather than an absolute mechanical formula. Use scores to ask better questions and agree on pilot order, not to replace engineering judgment.

Wave 1 should ideally combine **high learning value with tightly bounded production impact**, such as a well-tested read-only feature with low data sensitivity.

## 34. Team Coordination and Ownership Plan

Group-based migration requires clear accountability:

- **Platform/build team:** JDK, framework/BOM, containers, CI, artifact provenance.
- **Web/API team:** Servlet/REST, routing, security filters, API contracts.
- **Domain team:** decouple container types from business APIs, preserve behavior.
- **Persistence team:** JPA, transactions, datasources, schema migrations.
- **Integration team:** JMS, HTTP clients, event contracts, external dependencies.
- **QA/reliability:** contract fixtures, integration environments, nonfunctional testing.
- **Security:** auth, parser settings, dependencies, CVEs, and TLS policies.
- **Operations:** deploy/rollback, traffic routing, monitoring, and incident runbooks.

This breakdown is illustrative; smaller organizations combine roles. What matters is assigning a defined owner to every dependency group and boundary contract.

Each tracking record can list:
- Migration unit owner.
- External dependency owner.
- Chosen compatibility matrix document.
- Before/after artifact versions.
- Exit criteria and test evidence.
- Blocker decisions.
- Rollout and rollback approvers.

## 35. End-to-End Plan Example

Suppose a large `order-web` system must migrate. Inventory reveals:

- `common-domain` contains both DTOs and `javax.persistence` annotations.
- `order-web` uses legacy Servlet and JAX-RS.
- `order-service` uses legacy CDI and transactions.
- `order-data` uses legacy JPA and Validation.
- `order-events` publishes JSON messages; consumers do not depend directly on Java types.
- `reporting-batch` reads the DB independently.

### 35.1. Analysis and Decisions

1. Split `common-domain-api` into container-free DTOs/contracts.
2. Move JPA entities/mappings into `order-data` so namespaces never leak across APIs.
3. Group `order-web` + `order-service` + `order-data` + CDI/Validation into one deployable migration unit sharing server/lifecycle.
4. Keep `order-events` behind a stable event contract so older consumers keep reading.
5. Schedule `reporting-batch` in a separate wave as long as DB schemas remain compatible.
6. Upgrade target server/framework/BOM to a supported set together with the Jakarta deployable.
7. Once stable in production, migrate `reporting-batch` and retire legacy adapters.

### 35.2. Graph After Separating Boundaries

```text
          common-domain-api
             /    |     \
            v     v      v
       web-app   events  reporting
          |
          v
   [CDI + JPA + Validation]
          |
          v
    Shared database
```

Simplified diagram: `web-app` and CDI/JPA/Validation still upgrade in one wave; `events` and `reporting` decouple once data and DB contracts are guaranteed.

### 35.3. Execution Sequence

```text
Baseline & fixtures
       |
       v
Domain decoupling
       |
       v
Target runtime pilot
       |
       v
Coordinated Jakarta deployment
       |
       v
Integration + mixed-version verification
       |
       v
Reporting/batch migration
       |
       v
Cleanup & legacy removal
```

Every step must capture pass/fail logs, artifact versions, and rollback conditions; ticking a checklist alone is not sufficient.

## 36. Typical Failure Scenarios

### 36.1. `ClassCastException` Between Two API Generations

**Symptom:** legacy code attempts casting `jakarta.servlet.ServletRequest` to `javax.servlet.ServletRequest` or vice versa.

**Cause:** two distinct Java types; matching method names do not make them compatible.

**Resolution:** align adapter and runtime to the same generation, or place container-independent contracts between groups.

### 36.2. `NoClassDefFoundError: javax/...`

**Symptom:** a library inside the new Jakarta container still requires `javax.servlet.*` or `javax.persistence.*` classes.

**Possible causes:** un-upgraded artifact, stale transitive dependency, plugin, or generated code.

**Resolution:** identify the referencing JAR/class, inspect the dependency graph and support matrix; never blindly drop an old API JAR onto the classpath and call it fixed.

### 36.3. CDI Fails to Discover Beans

**Symptom:** deployment succeeds yet `@Inject` fields remain uninjected.

**Possible causes:** old annotations, wrong descriptors, bean discovery modes, mismatched CDI extensions or providers.

**Resolution:** inspect CDI runtime logs, imports/metadata, and run integration tests booting the real container.

### 36.4. JPA Fails to Recognize Entities

**Symptom:** entities are unmanaged or persistence unit bootstrap fails.

**Possible causes:** entity annotations use old namespaces, wrong `persistence.xml`, different JPA provider/version, scanning filters, or module accessibility.

**Resolution:** migrate entities, ORM provider, and configs in the same group; verify mappings and transactions.

### 36.5. REST Endpoints Return 404 Post-Migration

**Symptom:** classes have `@Path` yet endpoints fail to register.

**Possible causes:** leftover `javax.ws.rs.Path`, wrong JAX-RS bootstrap config/provider, or container skipping application scanning.

**Resolution:** inspect runtime annotations, resource registration, and deployment logs.

### 36.6. Unit Tests Pass, Production Fails

**Symptom:** tests mocking `EntityManager` or instantiating resources via `new` succeed, while the server fails.

**Cause:** unit tests never exercised CDI/JPA/Servlet lifecycles.

**Resolution:** add deployment/integration tests running against representative runtimes.

### 36.7. Rollback Cannot Read New Data

**Symptom:** rolled-back legacy app fails to parse messages or breaks on DB schemas.

**Cause:** data contracts changed in the same wave without preserving backward compatibility.

**Resolution:** follow expand/migrate/contract and design data rollback plans.

## 37. Pre-Sign-Off Migration Planning Checklist

- [ ] Defined source and target Java EE/Jakarta EE versions, including JDK/runtime.
- [ ] Inventoried artifacts and **resolved dependency versions**, not just direct declarations.
- [ ] Separated Jakarta-spec `javax.*` packages from Java SE `javax.*` packages.
- [ ] Identified target server/framework/BOM and verified compatibility matrices.
- [ ] Built both component graph and contract graph.
- [ ] Distinguished Java type coupling from HTTP/queue/DB boundaries.
- [ ] Identified dependency cycles and tightly coupled cohorts that must move together.
- [ ] Checked runtime extensions, plugins, generated code, and descriptors.
- [ ] Defined migration units with owners, blockers, and entry/exit criteria.
- [ ] Established wave build order and wave rollout order separately.
- [ ] Built contract tests for boundaries requiring dual-version coexistence.
- [ ] Built CDI/JPA/Validation/Servlet/JMS tests on real providers/containers.
- [ ] Prepared golden JSON/XML/message fixtures and checked schema compatibility.
- [ ] Verified DB schemas, transactions, and rollback preconditions.
- [ ] Confirmed classpath/module path, BOMs, and `provided` dependencies.
- [ ] Defined mitigation strategies for plugins lacking Jakarta releases.
- [ ] Established security, deployment, observability, and rollback plans.
- [ ] Scheduled retirement criteria for legacy adapters, transformers, and branches.
- [ ] Documented architectural decisions and compatibility evidence per group.

## 38. References

- [Jakarta EE Specifications](https://jakarta.ee/specifications/): Jakarta EE specifications and API versions.
- [Jakarta EE Platform](https://jakarta.ee/specifications/platform/): platform releases and related profiles.
- [Jakarta EE 9 Release](https://jakarta.ee/release/9/): context behind the Java EE to Jakarta namespace transition.
- [Jakarta EE Migration Guides](https://jakarta.ee/learn/): learning materials and migration guidance from the Jakarta ecosystem.
- [JEP 320 — Remove the Java EE and CORBA Modules](https://openjdk.org/jeps/320): modules formerly bundled in the JDK and removed in Java 11.
- [Eclipse Transformer](https://github.com/eclipse-transformer/transformer): namespace/resource transformation tool suited to selected migration cases.
- [OpenRewrite](https://docs.openrewrite.org/): recipe-driven source/build rewriting tool.
- [Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): inspecting resolved dependency trees.
- [Gradle — Viewing Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): inspecting dependency graphs and `dependencyInsight`.
- [Oracle jdeps](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html): analyzing static dependencies in classes/JARs.
- [Semantic Versioning](https://semver.org/): interpreting version conventions where applicable; does not replace compatibility matrices.
- [Jakarta Servlet Specification](https://jakarta.ee/specifications/servlet/): Jakarta Servlet API contracts.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/): Jakarta Persistence API contracts.
- [Jakarta Contexts and Dependency Injection](https://jakarta.ee/specifications/cdi/): CDI spec and integration points.

## Conclusion

Planning Java EE to Jakarta EE migration by **interdependent component groups** manages source, binary, runtime, and data risks far better than rewriting imports module by module. Start with an inventory and dependency graphs, separate Java SE APIs from Jakarta APIs, locate container- and namespace-coupled components, and define fitting migration units. Sequence waves according to compatibility requirements across **both Java dependencies and HTTP, queue, and database boundaries**, backed by measurable entry/exit criteria, integration tests, and clear rollback plans. Modules decoupled by stable contracts can migrate independently across waves; modules exchanging `javax/jakarta` types directly or sharing one container lifecycle generally must upgrade together. The ultimate objective is not merely deploying a Jakarta build, yet sustaining business functionality and data integrity across multi-version coexistence.
