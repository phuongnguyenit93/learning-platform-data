# Choosing a Data Store and Checking REST Export Support by Version

## Objectives

When setting up Spring Data REST, you must choose the right data store, Spring Data module, and compatible version set. Spring Data REST is responsible for exposing repositories as HTTP resources; it does not supply database drivers, replace data-access modules, or provide the same level of integration-test coverage across all stores.

After this lesson, you will be able to:

- Select a store based on data model, query patterns, transactions, and operational requirements.
- Distinguish stores officially integration-tested with Spring Data REST from stores that are only potentially compatible through the Repository programming model.
- Identify the managed versions of Spring Boot, Spring Data REST, Spring Data Commons, and store modules.
- Initialize a sample repository, inspect HAL endpoints, and test HTTP operations.

## 1. Understanding the Three Layers

When we say an application uses PostgreSQL, MongoDB, or Neo4j, we are referring to the data store. For the application to interact with the store, it needs the corresponding Spring Data module. Spring Data REST sits at the web layer and exposes repositories as HTTP resources.

1. **Data store:** the actual database engine or storage service, such as PostgreSQL, MongoDB, Neo4j, or Cassandra.
2. **Spring Data module:** provides mapping, repositories, queries, and store-specific integration, such as Spring Data JPA or Spring Data MongoDB.
3. **Spring Data REST:** detects eligible repositories and exposes collection/item resources via Spring MVC. Responses default to HAL so clients can discover links.

Processing flow:

~~~text
HTTP client
    |
    v
Spring Data REST (Spring MVC, HAL)
    |
    v
Spring Data Repository
    |
    v
Store-specific Spring Data module
    |
    v
Database / data service
~~~

Example with PostgreSQL:

- PostgreSQL stores the data.
- The PostgreSQL JDBC driver provides connectivity.
- Spring Data JPA maps entities and implements repositories.
- Spring Data REST exposes repositories as HTTP endpoints.

Adding Spring Data REST alone cannot provide persistence capabilities if the application lacks an appropriate store module, driver, and connection configuration.

Spring Data REST is built on Spring MVC. If your application is designed entirely around WebFlux, do not assume the REST exporter will provide an equivalent reactive API. Verify your web architecture and actual repositories; for end-to-end reactive APIs, WebFlux controllers/services may be a clearer choice.

## 2. Choosing a Store by Data and Query Characteristics

Do not pick a database simply because you are familiar with a repository interface. List the data you need to store, key queries, transaction requirements, and growth patterns first.

| Store Category | Common Spring Data Modules | Suitable When | Design Considerations |
|---|---|---|---|
| Relational databases | JPA, JDBC | Data has relationships, constraints, joins, transactions, and SQL reporting | Entities/aggregates, foreign keys, indexes, transaction boundaries, and migrations |
| Reactive relational | R2DBC | Non-blocking SQL access is needed in a reactive application | Reactive repositories, `Mono`/`Flux`, `ConnectionFactory`, and API layer compatibility |
| Document databases | MongoDB, Couchbase | Data is read/written as documents or aggregates with evolving schemas | Embedding vs. referencing, indexes, document size, and query patterns |
| Graph databases | Neo4j | Relationships between entities are central, requiring traversals or path-finding | Nodes, relationships, traversal direction, and query modeling |
| Wide-column | Cassandra | High write throughput, distributed architecture, high availability, predictable queries | Partition keys, clustering keys, and query-driven table design |
| In-memory data grid | GemFire | Distributed in-memory data, caching, or low-latency access is needed | Partitioning, replication, persistence, and data synchronization |
| Key-value, search, directory | Redis, Elasticsearch, LDAP, and related modules | Caching, full-text search, or specialized directory data | Role of the store in architecture, query semantics, and available repository modules |

Consider these criteria together:

- **Data model:** normalized relations, nested documents, or graph relationships lead to very different mapping models.
- **Queries:** list actual queries up front. Cassandra requires query-first modeling; Neo4j excels at traversals; Elasticsearch serves search rather than replacing a transactional system of record.
- **Transactions and consistency:** determine whether you need multi-record transactions, foreign-key constraints, optimistic locking, or single-aggregate updates.
- **Scale and operations:** weigh replication, partitioning, backup/restore, latency, cost, and your team's operational expertise.
- **Application integration:** verify drivers, transaction managers, migration tools, test containers, and Spring Data modules.
- **Exposed API:** evaluate whether repositories make sense as a public REST contract or whether business logic warrants dedicated controllers/services and DTOs.

Having a Spring Data module for a store does not mean that store is integration-tested with Spring Data REST. That is a separate verification step after selecting the database.

## 3. Store Support Scope of Spring Data REST

Spring Data REST's Getting Started documentation currently lists five store integrations that the project explicitly verifies with integration tests:

- **Spring Data JPA**
- **Spring Data MongoDB**
- **Spring Data Neo4j**
- **Spring Data GemFire**
- **Spring Data Cassandra**

Read the meaning of this list carefully. Spring Data REST does not add storage functionality to a database by itself. In principle, the exporter can work with other Spring Data projects as long as they support the Repository programming model. The five stores above are the integrations confirmed by the project's integration tests.

Classify candidate stores by level of evidence:

| Level | Meaning | Action Needed |
|---|---|---|
| On the integration-tested list | Spring Data REST documentation explicitly states the store is integration-tested | Start with the corresponding module, then still test your exact version and required features |
| Has Repository abstraction but outside the list | May be compatible at the repository model level, but lacks the same level of verification in docs | Build a proof of concept and integration tests with the exact store module, exporter, and version |
| Lacks a suitable repository | The exporter cannot automatically turn arbitrary APIs into repository resources | Use dedicated controllers/services or custom adapters, or choose another module |

Do not conclude that Redis, Elasticsearch, Couchbase, LDAP, Spring Data JDBC, or R2DBC cannot be integrated merely because they are absent from the five-store list. The accurate conclusion is that current documentation does not list them among officially integration-tested combinations; you must check the repository contract and verify via testing.

### Special Case: R2DBC

Spring Data R2DBC supports reactive repositories, typically extending `ReactiveCrudRepository` and returning Reactor types such as `Mono` or `Flux`. This repository model differs behaviorally from synchronous JPA examples.

R2DBC is not on the list of five stores announced as integration-tested by Spring Data REST. Therefore:

- Do not assume every `ReactiveCrudRepository` will be exported as a proper REST endpoint just because it extends `Repository`.
- Check the documentation and integration tests for the specific Spring Data REST / store module pair you use.
- If the application requires end-to-end reactive processing, evaluate WebFlux controllers/services and data conversion rather than assuming an MVC exporter covers all requirements.

## 4. Checking Spring Data Versions Against Spring Boot

### 4.1. Letting Spring Boot Manage Dependencies

Spring Data comprises many modules with independent release cycles. Spring Data REST, Commons, JPA, MongoDB, Neo4j, and Cassandra do not necessarily share the same major/minor version numbers.

When using Spring Boot, let Boot's dependency management handle module versions. The following table is taken from the Managed Dependency Coordinates of stable Spring Boot releases published as of 2026-11-11:

| Spring Boot | `spring-data-rest-webmvc` | `spring-data-commons` | Release train |
|---|---:|---:|---|
| 4.1.2 | 5.1.2 | 4.1.2 | 2026.0 |
| 4.0.9 | 5.0.8 | 4.0.8 | 2025.1 |
| 3.5.16 | 4.5.13 | 3.5.13 | 2025.0 |

These are examples of Boot-managed version sets, not a recommendation to upgrade an older project without evaluating Java, Spring Framework, and other libraries.

Key rules:

- Do not manually assign the same version to all Spring Data modules.
- Do not override `spring-data-rest-webmvc` or `spring-data-commons` individually without checking the compatibility matrix.
- Use Spring Boot starters and omit the version field when the Boot BOM manages the artifact.
- If not using Spring Boot, use the Spring Data Release Train BOM to synchronize Spring Data modules.
- When upgrading, read the release notes and migration guides for the corresponding release train; do not just bump version numbers in your build file.

### 4.2. Distinguishing Artifacts

| Artifact | Role |
|---|---|
| `spring-boot-starter-data-rest` | Boot starter to enable Spring Data REST |
| `spring-data-rest-webmvc` | REST exporter built on Spring MVC |
| `spring-data-rest-core` | Core components of Spring Data REST |
| `spring-data-rest-hal-explorer` | HAL browser for exploring APIs, if needed by the application |
| `spring-data-jpa` | Repositories and mapping for JPA |
| `spring-data-mongodb` | Repositories and mapping for MongoDB |
| `spring-data-neo4j` | Repositories and mapping for Neo4j |
| `spring-data-cassandra` | Repositories and mapping for Cassandra |
| Database driver | Actual connectivity to PostgreSQL, MongoDB, Cassandra, and other stores |

Adding the REST starter without a store module or driver will not yield working repositories. Adding a store starter without enabling the REST exporter also does not mean repositories will be exposed as endpoints.

### 4.3. Inspecting Resolved Dependencies

With Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.data
~~~

With Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-data-rest-webmvc --configuration runtimeClasspath
~~~

Read the output in order:

1. Identify the version of `spring-data-rest-webmvc`.
2. Identify the version of `spring-data-commons`.
3. Identify the actual store module, such as `spring-data-jpa` or `spring-data-mongodb`.
4. Check whether any dependency was overridden or pulled in at a different version via a transitive dependency.
5. Cross-check all versions against the Managed Dependency Coordinates of your Spring Boot line or Spring Data Release Train BOM.
6. Read the Spring Data REST documentation and release notes for the exact major/minor version before using a specific feature.

A dependency tree only proves the build resolved dependencies. It does not prove that a store's repositories are exported properly or that database operations work. You must test endpoints against the real store or an equivalent integration-test environment.

## 5. Setup Example with JPA and PostgreSQL

JPA is one of the five stores with official Spring Data REST integration tests. The example below uses Spring Boot 4.1.2; starter and Spring Data module versions are managed by Boot.

### 5.1. Maven Dependencies

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.2</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-rest</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

This is the dependency portion of the POM. To run the application, you need to configure the PostgreSQL datasource and create an appropriate database. Do not declare separate versions for the REST starter, JPA starter, or driver when using Boot dependency management.

### 5.2. Entity and Repository

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Product() {
    }

    public Product(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "products")
public interface ProductRepository extends JpaRepository<Product, Long> {
}
~~~

Place the entity and repository in packages scanned by the Spring Boot application. `JpaRepository` provides CRUD, paging, and sorting. The repository annotation sets the collection name explicitly for stable endpoints.

### 5.3. Connection Configuration

Minimal configuration example for PostgreSQL:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/catalog
spring.datasource.username=app
spring.datasource.password=change-me
spring.jpa.hibernate.ddl-auto=update
~~~

The password above is only a local configuration example. Real environments should load secrets from environment variables or a secret manager. For production systems, managing schemas with Flyway or Liquibase is usually much easier to control than automatic schema updates.

### 5.4. Exported Endpoints

With a public repository and default settings, Spring Data REST discovers the repository and exports a collection resource:

| HTTP | URL | Purpose |
|---|---|---|
| GET | `/products` | Retrieve the collection |
| GET | `/products/{id}` | Retrieve a single item |
| POST | `/products` | Create an item when `save` is exported |
| PUT/PATCH | `/products/{id}` | Update an item according to export settings |
| DELETE | `/products/{id}` | Delete an item when `delete` is exported |

Discover the API from the root URL and request the HAL media type:

~~~bash
curl -i http://localhost:8080/
curl -i -H "Accept: application/hal+json" http://localhost:8080/products
~~~

The root resource returns links to exported resources. A collection response may contain an empty embedded list if no data exists yet; that does not mean the endpoint is missing.

Try creating a product:

~~~bash
curl -i -X POST http://localhost:8080/products \
  -H "Content-Type: application/json" \
  -H "Accept: application/hal+json" \
  -d '{"name":"Keyboard"}'
~~~

When the repository and database work properly, creation returns HTTP `201 Created` and a `Location` header pointing to the new item. The exact ID is generated by the database and cannot be assumed beforehand.

When switching from JPA to MongoDB, Neo4j, or Cassandra, you must change the store starter, driver, mapping, configuration, and repository for that module. Do not merely swap the dependency name in the POM.

## 6. Controlling Which Repositories Are Exported

Spring Data REST can automatically detect repositories. Public repositories are typically considered for export according to the configured detection strategy. Check each repository, annotation, and exposed method.

Common strategies:

| Strategy | Behavior |
|---|---|
| `DEFAULT` | Uses default rules, considering public repositories and the `exported` flag |
| `ALL` | Considers all repositories, regardless of visibility or annotations |
| `VISIBILITY` | Based on repository visibility |
| `ANNOTATED` | Only considers repositories annotated with `@RepositoryRestResource` |

Example changing the collection path:

~~~java
@RepositoryRestResource(path = "products")
public interface ProductRepository extends JpaRepository<Product, Long> {
}
~~~

Hiding an internal repository:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends JpaRepository<AuditRecord, Long> {
}
~~~

Hiding a finder method:

~~~java
import java.util.List;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(path = "products")
public interface ProductRepository extends JpaRepository<Product, Long> {

    @RestResource(exported = false)
    List<Product> findByInternalCode(String internalCode);
}
~~~

A repository can exist and be used by services without appearing in the REST API due to visibility, detection strategy, or `exported = false`.

Auto-exporting repositories is also an API contract and security decision. Only publish operations appropriate for a public API; use Spring Security to protect endpoints. For multi-step business logic, custom DTOs, complex authorization, or workflows, controllers/services usually give clearer contract control.

## 7. Testing Support Level for Your Exact Version

Do not stop at seeing the application start successfully. Write integration tests or smoke tests for the exact Spring Data REST and store module pair you are deploying.

Minimum checklist:

1. **Context:** the application starts, repository beans are created, and the database connects.
2. **Discovery:** GET on root returns HTTP 200 and includes a link to the expected collection.
3. **Collection:** GET on the collection returns HTTP 200, HAL JSON media type, and appropriate paging metadata.
4. **Create:** POST returns HTTP 201 and a valid `Location` header.
5. **Read:** GET on the `Location` URI returns the newly created data.
6. **Update:** PUT/PATCH works according to repository methods and exposure configuration.
7. **Delete:** DELETE succeeds only when the delete operation is exported.
8. **Finder/search:** verify search resources and query methods if your application uses them.
9. **Store mapping:** verify IDs, associations, data types, transactions, and optimistic locking per module.
10. **Paging/sorting:** verify the features your application needs; do not assume all stores share identical semantics.
11. **Security:** unauthorized users cannot invoke sensitive operations.
12. **Version:** re-run tests against the exact version being deployed, not only the newest version in documentation.

For stores outside the integration-tested list, verify at least CRUD, ID mapping, query methods, paging/sorting, and associations if your application relies on them. For R2DBC, explicitly verify whether reactive repositories are supported by your exporter version; do not infer this from the Repository abstraction.

### Common Errors

- **404 Not Found:** wrong path/base path, repository not discovered, or resource not exported.
- **405 Method Not Allowed:** the resource exists, but the corresponding method is absent or disabled via `exported`/exposure configuration.
- **`NoSuchMethodError`/`ClassNotFoundException`:** may stem from version mismatches, BOM overrides, or duplicate module versions.
- **Root has the link, but store operations fail:** the exporter discovered the repository, while the store driver, mapping, transaction, or query needs attention.
- **Build succeeds, but REST endpoints are not exported:** having the dependency present does not mean the repository is scanned and exported.
- **API exposes internal operations:** check detection strategy, `exported` flags, Spring Security, and public contract design.

## 8. Selection and Verification Workflow

1. List your data model, query patterns, transactions, and operational requirements.
2. Choose the database and corresponding Spring Data module.
3. Check whether the store is on Spring Data REST's integration-tested list or only offers the Repository abstraction.
4. If using R2DBC, separately verify reactive repositories and WebMVC/WebFlux architecture.
5. Choose a Spring Boot line or Spring Data release train compatible with Java and Spring Framework.
6. Let the BOM manage versions; inspect the dependency tree after building.
7. Add the REST exporter, store module, driver, and connection settings.
8. Create a sample repository and verify the HAL root, collection, and item endpoints.
9. Run integration tests covering CRUD, mapping, queries, paging, security, and required features.
10. Publish the API only after confirming both compatibility and exposure policies.

## Official References

- [Spring Data REST — Getting Started](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html): setup, supported stores, and integration test scope.
- [Spring Data REST — Repository Resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): collection/item resources, HAL, and HTTP methods.
- [Spring Data REST — Customizing](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html): repository detection, `exported` flag, and endpoint customization.
- [Spring Data REST — Dependencies](https://docs.spring.io/spring-data/rest/reference/data-commons/dependencies.html): dependency management and the Spring Data release train.
- [Spring Data R2DBC — Repositories](https://docs.spring.io/spring-data/relational/reference/r2dbc/repositories.html): `ReactiveCrudRepository` and reactive repository behavior.
- [Spring Boot 4.1 Managed Dependency Coordinates](https://docs.spring.io/spring-boot/4.1/appendix/dependency-versions/coordinates.html): versions managed by Boot 4.1.
- [Spring Boot 4.0 Managed Dependency Coordinates](https://docs.spring.io/spring-boot/4.0/appendix/dependency-versions/coordinates.html): versions managed by Boot 4.0.
- [Spring Boot 3.5 Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html): versions managed by Boot 3.5.
- [Spring Data 2026.0 Release Notes](https://github.com/spring-projects/spring-data-commons/wiki/Spring-Data-2026.0-Release-Notes): changes and upgrade notes for the release train.

Spring versions evolve across patches and release trains. When starting a project or upgrading, cross-check the official documentation and your project's dependency tree at the time of implementation.
