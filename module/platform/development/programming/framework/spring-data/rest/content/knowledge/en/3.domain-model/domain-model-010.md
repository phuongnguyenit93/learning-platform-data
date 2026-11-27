# Distinguishing Common REST Exporter Behavior from Data Store Specifics

## Objectives

Spring Data REST helps publish Spring Data repositories as HTTP resources following a consistent convention. However, sharing the same URL or HTTP method does not give different databases the same data model, querying capabilities, or consistency guarantees.

This lesson separates three parts that are frequently confused:

1. Behavior provided by the Spring Data REST exporter when exposing a repository.
2. Behavior provided by a specific Spring Data module when implementing the repository.
3. Behavior determined by the database or data store itself.

Distinguishing these three parts helps you design APIs, investigate bugs, and evaluate data store migrations more accurately.

## 1. Architecture and Responsibility Boundaries

A request flows through the layers in this general sequence:

~~~text
HTTP client
    |
    v
Spring Data REST exporter
    |  - discovers repositories permitted for export
    |  - creates collection, item, and search resources
    |  - maps HTTP requests to repository methods
    |  - converts representations and HAL links
    |  - applies exposure settings and REST events
    |
    v
Spring Data repository abstraction
    |
    v
Corresponding Spring Data module
    |  - maps domain objects
    |  - builds and executes queries
    |  - handles IDs and store-specific relationships
    |  - integrates transactions, paging, and sorting
    |
    v
Database / data store
       - schema and data types
       - indexes and query plans
       - transactions and consistency
       - query limitations and storage capabilities
~~~

The **Spring Data REST exporter** focuses on how repositories are presented over HTTP. It provides URLs, HTTP methods, representations, links, and REST customization hooks.

The **Spring Data module** connects the repository abstraction to a specific storage technology. Spring Data JPA, MongoDB, Cassandra, and Neo4j each have their own mapping, query derivation, and capabilities.

The **database** executes queries and enforces final constraints. For instance, a relational database can use foreign keys and joins; a document database stores documents; Cassandra organizes data by partition; Neo4j stores nodes and relationships.

Therefore, Spring Data REST can generate similarly structured APIs across different repositories, but it does not standardize all underlying database behavior.

## 2. Common Behaviors of the REST Exporter

### 2.1. Repository Discovery and Resource Creation

Suppose an application has a repository:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface PersonRepository
        extends CrudRepository<Person, String> {
}
~~~

When the repository is discovered and allowed to be exported, Spring Data REST typically generates two kinds of resources:

- Collection resource representing the set: /people
- Item resource representing a single element: /people/{id}

Resource names are derived by default from the domain type. You can specify the path and collection relation name explicitly:

~~~java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(
        path = "people",
        collectionResourceRel = "people"
)
public interface PersonRepository
        extends CrudRepository<Person, String> {
}
~~~

If the base path is configured as /api, the collection resource has the path /api/people.

Whether a repository is exported depends on repository detection configuration and its exported flag. You can hide an entire repository by setting exported = false on @RepositoryRestResource. You can hide an individual method with @RestResource(exported = false).

This is an API exposure decision. It does not change the schema or how data is stored.

### 2.2. HTTP Method Mapping

For repositories with corresponding CRUD methods, the exporter can provide familiar HTTP operations:

| Resource | HTTP method | Role |
|---|---|---|
| /api/people | GET | Read collection |
| /api/people | POST | Create resource |
| /api/people/{id} | GET | Read single resource |
| /api/people/{id} | PUT | Replace resource state |
| /api/people/{id} | PATCH | Partially update resource |
| /api/people/{id} | DELETE | Delete resource |

This table describes the common REST mapping. Actual supported methods depend on the repository interface, which methods are exported, configuration, and the capabilities of the Spring Data module.

For example, if a repository does not provide delete operations or the delete method is hidden, the exporter cannot provide the corresponding DELETE operation merely by creating a URL. Likewise, a read-only repository should not be assumed to support full CRUD.

The exporter maps requests to repository calls. It does not automatically add business rules such as "only the owner may edit", "cannot delete a person who has orders", or "email must be unique". Those rules must be enforced at the appropriate layer using validation, services, security, or database constraints.

### 2.3. HAL and Hypermedia

Spring Data REST uses HAL JSON by default to represent resources. A response may contain:

- _links: links to the current resource, collection, searches, or related resources.
- _embedded: elements embedded within collection representations.
- page: pagination metadata when the repository supports paging.

Clients can start at the root URL, read collection links, and follow self or relationship links. This approach reduces the need for clients to manually assemble every URL.

HAL is a format for representing resources and links. HAL does not dictate whether an entity is stored in a table, document, or graph. The same kind of HTTP link can point to data persisted using completely different models.

### 2.4. Search Resources and Query Methods

Spring Data REST can expose repository query methods under a search resource. For example:

~~~java
import java.util.Optional;

import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(path = "people")
public interface PersonRepository
        extends CrudRepository<Person, String> {

    @RestResource(path = "by-email", rel = "by-email")
    Optional<Person> findByEmail(
            @Param("email") String email
    );
}
~~~

The endpoint can be called as follows:

~~~http
GET /api/people/search/by-email?email=linh@example.com
~~~

The exporter is responsible for creating the search resource, setting the path, and passing query parameters to the repository call. Whether the Spring Data module can derive and execute that query depends on the mapping and the store's querying capabilities.

Method naming conventions do not guarantee that every store supports the same operators. For instance, string matching, case-insensitive searches, collection queries, or multi-condition combinations may have different limitations across JPA, MongoDB, and Cassandra.

### 2.5. Projections, Events, Validation, and Security

The REST exporter also provides extension points for representations and request lifecycles:

- **Projections and excerpts:** customize which attributes appear in representations.
- **REST events:** allow the application to react before or after create, save, update, or delete operations.
- **Validation:** integrate application validators when data is written.
- **Repository exposure:** control which repositories or methods are published.
- **Security integration:** combine with Spring Security to enforce user authentication and access permissions.

These utilities affect public API exposure and request handling. They do not replace indexes, transactions, consistency levels, partition keys, or data store relationship mechanisms.

## 3. Specific Characteristics of Each Spring Data Module

### 3.1. Spring Data JPA: Entities and Relationships in Relational Databases

JPA maps domain objects to entities and tables. For example:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "people")
public class Person {

    @Id
    private String id;

    @Column(nullable = false)
    private String email;

    protected Person() {
    }

    public Person(String id, String email) {
        this.id = id;
        this.email = email;
    }

    public String getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Characteristics belonging to JPA and relational databases:

- @Entity and @Table map Java classes to tables.
- @Id identifies the primary key; @Column describes column attributes.
- Relationships can be declared with @ManyToOne, @OneToMany, @OneToOne, or @ManyToMany.
- Hibernate manages the persistence context, dirty checking, cascade, and fetch strategies.
- Spring Data JPA supports derived queries, JPQL, and native queries.
- Transactions and locking depend on the JPA provider, transaction configuration, and database.
- The database can enforce joins, constraints, indexes, and foreign keys according to the schema.

The REST exporter can represent an association using a HAL link. However, an HTTP link does not determine whether the relationship cascades, is lazy-loaded, or how the database enforces foreign key constraints.

### 3.2. Spring Data MongoDB: Documents and Collections

MongoDB stores documents inside collections. Domain types typically use @Document and @Id:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("people")
public class Person {

    @Id
    private String id;

    private String email;

    public Person() {
    }

    public Person(String id, String email) {
        this.id = id;
        this.email = email;
    }

    public String getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Characteristics belonging to MongoDB and Spring Data MongoDB:

- @Document maps a domain type to a collection.
- Objects are converted into documents with corresponding fields.
- Related data can be embedded within a document or stored as references; there are no relational joins and foreign keys by default.
- Query methods are translated into MongoDB queries according to module capabilities.
- Indexes, aggregations, sharding, and transactions depend on the MongoDB deployment and configuration.
- @Version can support optimistic locking according to module capabilities.

The exporter can still create collection resources, item resources, search links, and HAL representations. It does not turn MongoDB references into foreign-key associations or SQL joins.

### 3.3. Spring Data Cassandra: Partitions and Query Models

Cassandra organizes data by tables, partition keys, and clustering columns. Domain types typically use @Table and @PrimaryKey:

~~~java
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("people")
public class Person {

    @PrimaryKey
    private String id;

    private String email;
}
~~~

Characteristics belonging to Cassandra and Spring Data Cassandra:

- The partition key determines how data is partitioned across nodes.
- Clustering columns determine how data is ordered within a partition.
- CQL has strict rules on query predicates; you cannot run arbitrary ad-hoc queries like SQL on a relational database.
- Cassandra does not provide joins or foreign keys in the relational sense.
- Query methods must align with the primary key, partition design, and CQL capabilities.
- Paging, consistency levels, and replication have distinct semantics.

A method can be exposed as a search URL, yet that does not prove Cassandra can execute arbitrary queries behind it. Repository design must follow Cassandra's query model. In particular, queries incompatible with the partition key may be rejected or require enabling filtering at high cost.

### 3.4. Spring Data Neo4j: Nodes and Relationships

Neo4j stores data as a graph of nodes and relationships. Domain types typically use @Node; relationships are mapped with corresponding relationship annotations.

Characteristics belonging to Neo4j and Spring Data Neo4j:

- Domain models describe nodes and relationships.
- Queries may require pattern matching or graph traversal.
- Traversal depth, node counts, and graph topology affect query cost.
- Query language and mapping are determined by Spring Data Neo4j and Neo4j.
- Transactions and graph access rules belong to the module and database.

The exporter can publish repositories as HTTP resources, but REST representations do not turn a graph into a table-and-foreign-key model.

## 4. Responsibility Matrix

| Aspect | REST exporter | JPA | MongoDB | Cassandra | Neo4j |
|---|---|---|---|---|---|
| Collection/item URLs | Created from repository and configuration | Does not decide | Does not decide | Does not decide | Does not decide |
| HAL and links | Resource/link representation | Entity/association metadata | Document/reference metadata | Repository/entity metadata | Node/relationship metadata |
| HTTP CRUD | Maps requests to exported methods | Executed via JPA | Executed via MongoDB module | Executed via Cassandra module | Executed via Neo4j module |
| Mapping | Does not define store schema | Entity, table, column | Document, collection, field | Table, partition/clustering key | Node, relationship |
| Querying | Publishes query methods | JPQL/SQL, derived queries | Mongo queries, derived queries | CQL and partition limits | Graph queries |
| Relationships | Can be represented via links | Associations, joins, foreign keys | Embedded documents or references | Designed per query model | Graph relationships |
| Paging/sorting | Forwards REST parameters when supported | Per query and database | Per query and database | Per Cassandra paging/query model | Per query and module |
| Transactions/consistency | Does not define store semantics | Per JPA/database | Per MongoDB deployment | Per consistency level/replication | Per Neo4j |

This table classifies responsibilities. Exact capabilities also depend on the Spring Data version, repository interface, driver, and database configuration.

## 5. Same REST Contract Does Not Mean Same Semantics

A repository can keep nearly the same shape across stores:

~~~java
import java.util.Optional;

import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(
        path = "people",
        collectionResourceRel = "people"
)
public interface PersonRepository
        extends CrudRepository<Person, String> {

    @RestResource(path = "by-email", rel = "by-email")
    Optional<Person> findByEmail(
            @Param("email") String email
    );
}
~~~

With a base path of /api, clients can see paths such as:

~~~text
GET    /api/people
POST   /api/people
GET    /api/people/{id}
PUT    /api/people/{id}
PATCH  /api/people/{id}
DELETE /api/people/{id}
GET    /api/people/search/by-email?email=...
~~~

This illustrates the API shape. It is not a standalone project that runs identically against every store. With JPA, Person needs JPA mapping; with MongoDB, Person needs document mapping; with Cassandra, the mapping must match the primary key; with Neo4j, the domain model must fit a graph.

Even when URLs stay unchanged, the following aspects can still differ:

- ID types and ID generation mechanisms.
- Which query methods are supported and how strings, nulls, or collections are handled.
- Whether relationships are stored as associations, embedded documents, references, or graph relationships.
- Paging, sorting, result ordering, and query cost.
- Transaction boundaries, locking, concurrency, and consistency.
- Indexes and query limits imposed by the store.

Therefore, keeping the same URLs does not mean you can swap databases merely by swapping a dependency. Migrating stores can require changing domain mappings, repository methods, queries, indexes, transactions, and data organization.

## 6. How to Determine Whether an Issue Is in the Exporter or the Data Store

Suppose a client calls:

~~~http
GET /api/people/search/by-email?email=linh@example.com
~~~

You can investigate from the outside in:

1. **REST exporter:** Is the repository exported? Does the HAL root contain the search link? Are the path, relation name, and query parameter correct? Is the method hidden with exported = false?
2. **Repository abstraction:** Is the method on a detected repository? Are parameter types and return types appropriate?
3. **Spring Data module:** Do property names match the mapping? Does the module support the derived query and matching operator used? Is an explicit query needed?
4. **Data store:** Does the field or column exist? Is there an appropriate index? Does the query violate a partition key, schema, or database constraint?

Common scenarios:

- **Collection returns slowly:** the exporter likely called the collection read properly; check paging, data volume, indexes, and the store's query plan.
- **Search URL returns 404:** check whether the search method is exported, whether the path is accurate, and whether the repository was detected.
- **Search URL exists, but the query fails:** check the derived query, mapping, and module capabilities; a successfully generated URL does not guarantee the database supports the query.
- **Item URL cannot find data:** check the passed ID, how the module maps IDs, and the actual record in the store.
- **Relationship is not saved as expected:** check cascade, ownership, references, or the module's relationship mapping.
- **PATCH does not update a property:** check JSON binding, projections, representations, validation, and mappings. The HTTP method does not bypass persistence rules.

The key is separating HTTP resource publishing issues from repository execution issues and database issues. Each layer has different observability and different fixes.

## 7. Design Guidelines When Working Across Multiple Data Stores

- Keep resource paths, relation names, and exposure configuration at the REST layer so the API follows clean conventions.
- Map domain types according to the target store's model; do not force relational entities, documents, and graphs to share one set of annotations.
- Only expose query methods supported by the Spring Data module. Verify actual queries against the target database.
- Design indexes, partition keys, associations, or graph relationships at the data store layer.
- Do not assume all stores share the same transaction boundaries, isolation, locking, or consistency guarantees.
- Use integration tests against each real store. Embedded or in-memory databases may not reproduce production partition, index, transaction, and consistency constraints.
- If the API needs separate DTOs, multi-step business logic, business-level authorization, or a response contract independent of the domain model, consider explicit services/controllers instead of exporting repositories directly.
- When migrating stores, re-evaluate data, queries, IDs, relationships, paging, transactions, and query costs. Preserving URLs solves only part of API compatibility.

## 8. Data Store Migration Checklist

1. Which mapping annotations does the domain type currently use? Are they compatible with the new module?
2. Are the ID type and ID generation mechanism compatible with item resources?
3. Is every query method supported by the new module?
4. Do queries need to change to align with indexes, partition keys, or graph patterns?
5. Do associations need to become embedded documents, references, or graph relationships?
6. What ordering, paging, sorting, or total-count behaviors does the API rely on? Does the new store have identical semantics?
7. What guarantees do current transactions and concurrency rely on? Does the new store provide equivalents?
8. Do integration tests run against databases and configurations close to production?
9. Do HAL links, representations, status codes, and error responses still match client expectations?

If any answer changes, assess the business and API impact before migrating.

## References

- [Spring Data REST – Getting started](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html)
- [Spring Data REST – Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST – Customizing repository exposure](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [Spring Data JPA – Reference documentation](https://docs.spring.io/spring-data/jpa/reference/)
- [Spring Data MongoDB – Reference documentation](https://docs.spring.io/spring-data/mongodb/reference/)
- [Spring Data Cassandra – Reference documentation](https://docs.spring.io/spring-data/cassandra/reference/)
- [Spring Data Neo4j – Reference documentation](https://docs.spring.io/spring-data/neo4j/reference/)