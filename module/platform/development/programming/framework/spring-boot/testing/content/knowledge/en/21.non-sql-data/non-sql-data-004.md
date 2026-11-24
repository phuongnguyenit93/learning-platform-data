# @DataNeo4jTest for graph relationships and queries

Within the **Non-SQL Data** group of the **Spring Boot - testing** module, `@DataNeo4jTest` is a **test slice** focused on Spring Data Neo4j: testing repositories, `@Node` and `@Relationship` mappings, and **Cypher** queries against a real Neo4j graph database. Tests do not need to start an HTTP server or load all application services and controllers, yet **they must have a Neo4j instance to connect to**.

The biggest difference compared to `@DataJdbcTest` or `@DataJpaTest` is that graph data consists of **nodes, directed relationships, labels, properties, and patterns/paths**. A test that merely checks `repository.save(person)` returns a non-null object is far too weak: it does not prove relationship direction, exact edge counts, pattern matching, safe parameter binding, or potential transaction/schema errors.

**After this lesson, you should be able to:**

- Choose `@DataNeo4jTest` accurately instead of `@DataJpaTest`, `@JdbcTest`, or `@SpringBootTest`.
- Set up a Spring Boot 3.5 + Neo4j 5 environment via Testcontainers and `@ServiceConnection`.
- Model `Author`/`Book` with the directed edge `(:Author)-[:WROTE]->(:Book)`.
- Test repository CRUD, relationship loading, derived queries, Cypher `@Query`, and direct queries via `Neo4jClient`.
- Verify **exact direction** and **exact edge counts** rather than inferring them from an in-memory Java object.
- Understand transaction rollback in imperative tests; avoid leaving data behind in reactive tests, when rollback is disabled, or with shared containers.
- Recognize what the slice **does not prove**: full service wiring, HTTP, security, production database configuration, lock/concurrency, and query performance.
- Add advanced cases: relationship properties, unique constraints, path queries, optional matches, and test idempotency.

Examples use **Java 17+**, Spring Boot **3.5.x**, Spring Data Neo4j 7.5, and JUnit Jupiter. APIs/imports in Spring Boot 4.x may move to different modules/packages; do not copy Boot 3.5 import paths into Boot 4 without checking version compatibility.

## 1. What environment does @DataNeo4jTest actually create?

A minimal test:

```java
@DataNeo4jTest
class AuthorRepositoryTest {
    @Autowired AuthorRepository repository;
    @Autowired Neo4jClient neo4jClient;
}
```

This is only a **skeleton**, not a standalone runnable class: you must declare the repository, have a running Neo4j instance, and supply driver configuration. `@DataNeo4jTest` instructs Spring Boot to:

1. Initialize a **narrow ApplicationContext** with auto-configurations for Spring Data Neo4j.
2. Scan `@Node` domain objects, initialize Neo4j repositories, and configure components such as `Neo4jClient`, `Neo4jTemplate`, and transaction infrastructure depending on dependencies.
3. Exclude ordinary `@Service`, `@Component`, controller, or arbitrary `@ConfigurationProperties` beans by default. If a bean is truly needed for repository mapping, bring it into the slice intentionally.
4. For imperative tests, enable **test-managed transactions + rollback after each test method** by default.
5. **Not bundle an embedded database** or connection URI automatically; you must supply Neo4j via Testcontainers, the Neo4j test harness, or a safe test instance.

**Version note:** In Boot 3.5, the annotation is imported from:

```java
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
```

Do not confuse this with imports in some Spring Boot 4.x releases, where testing support is reorganized under module `spring-boot-data-neo4j-test` and a different package.

### Do not assume tests spin up an in-memory Neo4j automatically

With H2/SQLite tests, you may be used to a single annotation providing an in-memory database. With modern Neo4j, `@DataNeo4jTest` only wires up the **Spring side** of connections and repositories. **Without a container, server, or harness**, repositories fail on connection when executed.

Practical options:

| Option | Pros | Limitations |
| --- | --- | --- |
| **Testcontainers Neo4j** | Real Neo4j engine over Bolt, close to production; fits Docker-enabled CI | Requires Docker runtime, image pulls, slower startup |
| **Neo4j test harness** | Runs server inside JVM, helpful when testing procedures/extensions | Version/JVM compatibility, runtime behavior differs from remote deployment |
| Dedicated Neo4j test server | Reusable, resembles a test environment | Must enforce isolation, auth, schema/cleanup, never point at production |

The runnable lesson uses **Testcontainers** so it never assumes Neo4j is already running locally.

## 2. Nodes, relationships, direction, and Cypher concepts

Neo4j stores a **property graph**. A small graph:

```text
(:Author {name:"An"})
   |
   +--[:WROTE]--> (:Book {title:"Graph Basics", year:2025})
   |
   +--[:WROTE]--> (:Book {title:"Cypher Patterns", year:2024})

(:Author {name:"Mai"})
   |
   +--[:WROTE]--> (:Book {title:"Data Modeling", year:2023})
```

Structural meaning:

- `Author` and `Book` are **node labels**.
- `name`, `title`, and `year` are **node properties**.
- `WROTE` is a **relationship type** directed **Author → Book**.
- A node can have multiple labels; a pair of nodes can have multiple relationships depending on the model/constraints.
- The graph does not automatically enforce rules like "each Author has at most two Books" or uniqueness of `name`. You must define and test constraints/contracts explicitly.

Cypher to find an author and their books:

```cypher
MATCH (a:Author {name: $name})-[:WROTE]->(b:Book)
RETURN b.title AS title
ORDER BY title
```

In Java, `$name` is a **query parameter** bound by the driver/Spring Data. Never concatenate input directly into Cypher like `"... WHERE a.name = '" + input + "'"`; that is hard to escape and creates a query injection risk.

### Relationship direction is not decorative

These two patterns are **different**:

```cypher
MATCH (a:Author)-[:WROTE]->(b:Book)
RETURN count(b) AS total
```

```cypher
MATCH (b:Book)-[:WROTE]->(a:Author)
RETURN count(a) AS total
```

In the sample data, the first pattern finds real WROTE edges; the second matches nothing because there is no WROTE edge pointing from Book to Author. If undirected traversal is needed, Cypher supports **undirected patterns** like `-[:WROTE]-`, but never use that when the contract mandates direction.

### Graph queries differ from SQL JOINs

In SQL, you typically write `JOIN ... ON foreign_key`. In Neo4j, relationships are stored data structures. Query patterns and traversals depend on:

- Relationship direction and type.
- Edge multiplicity (0, 1, or many edges).
- Paths and traversal lengths.
- Optional match/null semantics.
- Row counts returned by a query; joins or traversals can multiply rows.
- Constraints/indexes on node properties and actual cardinality.

Therefore, graph tests should inspect **edges** and **edge counts** directly with Cypher alongside loading domain objects through the repository.

## 3. Comparing test slices in Spring Boot

| Annotation / approach | Layer tested | Real DB? | Used for |
| --- | --- | --- | --- |
| Plain JUnit + mock repository | Java/service logic against fake contract | No | Validation, policy, pure mapping |
| `@DataNeo4jTest` | Neo4j repositories, mapping, Cypher | **Yes**, Neo4j test instance | Graph relationships and queries |
| `@DataMongoTest` | MongoDB documents and repositories | MongoDB per test setup | Document queries |
| `@DataJdbcTest` | Spring Data JDBC + SQL | SQL datasource | Relational JDBC |
| `@DataJpaTest` | JPA/Hibernate | SQL datasource | JPA entities/JPQL |
| `@DataR2dbcTest` | R2DBC | R2DBC datasource | Reactive SQL access |
| `@SpringBootTest` | Broad application context | Depends on config | Multi-layer services/transactions/proxies/integration |
| `@WebMvcTest` or `@WebFluxTest` | Web controllers, JSON, HTTP contracts | Usually mocked services | Status, routing, validation, relevant security boundary |

**Do not use `@DataJpaTest` for Neo4j `@Node` entities**: JPA does not understand Spring Data Neo4j's `@Relationship`. Conversely, `@DataNeo4jTest` does not test JPA entities, SQL datasources, REST APIs, or Kafka consumers.

It is a test slice **with an ApplicationContext**, not a plain Java unit test, yet narrower than the full application. A Neo4j repository test can run with `@DataNeo4jTest` without production service beans. That is a speed and diagnostics advantage, not a flaw.

## 4. Runnable example: the Author → Book model

We use a two-node model:

- **Author:** has a Neo4j ID, a name, and a list of books the author wrote.
- **Book:** has an ID, title, and publication year.
- **WROTE:** directed edge from Author to Book, with no properties in the basic example.
- The repository provides `save`, `findById`, `findByName`, and a Cypher query returning book titles.

**File set:**

```text
src/
├── main/java/example/testing/neo4j/
│   ├── GraphApplication.java
│   ├── Author.java
│   ├── Book.java
│   ├── AuthorRepository.java
│   ├── GraphRule.java
│   └── GraphRuleDemo.java
└── test/java/example/testing/neo4j/
    ├── AuthorRepositoryTest.java
    └── GraphRuleTest.java
```

Choose a unified root package so `@SpringBootApplication` can find repositories and nodes. Below are all the required source files.

### 4.1. Gradle dependencies for Spring Boot 3.5

In a Gradle project generated by Spring Initializr (already configured with plugins, repositories, dependency management, and Java 17+), the relevant dependencies in `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-neo4j'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:neo4j'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is an **additive snippet**, not a standalone `build.gradle`. The Boot 3.5 BOM manages compatible Spring Data Neo4j/Testcontainers versions; projects using Boot 4's BOM must verify Testcontainers 2.x packages and changed test modules.

**Operational requirements:** Docker/container runtime ready, permission to pull image `neo4j:5.26`, and enough network/CPU/RAM for the container to start. Never use a production Neo4j database or real credentials for destructive tests.

### 4.2. GraphApplication.java

Create `src/main/java/example/testing/neo4j/GraphApplication.java`:

```java
package example.testing.neo4j;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GraphApplication {
    public static void main(String[] args) {
        SpringApplication.run(GraphApplication.class, args);
    }
}
```

This class lets Spring Boot locate the application configuration in the same package. The slice tests in Section 5 **do not need `main()` to run** or open an HTTP server. When running the real app via `main`, provide `spring.neo4j.uri` and authentication to that environment's Neo4j instance. The example does not try to launch a Neo4j server inside `main()`.

### 4.3. Book.java — target node

Create `src/main/java/example/testing/neo4j/Book.java`:

```java
package example.testing.neo4j;

import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Book")
public class Book {

    @Id
    @GeneratedValue
    private Long id;

    private String title;
    private int year;

    public Book() {
    }

    public Book(String title, int year) {
        this.title = title;
        this.year = year;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public int getYear() {
        return year;
    }

    public void setYear(int year) {
        this.year = year;
    }
}
```

**Explanation:** `@Node("Book")` maps the Java object to the `Book` label. The `@Id @GeneratedValue Long` pair uses a **Neo4j-generated internal identifier** in SDN 7.5; it is `null` before the object is saved. This example chooses internal IDs to keep the code concise and focused on relationships.

**Production design warning:** Neo4j internal IDs are not stable business keys to expose to clients; they can be reused after deletion and have no meaning across databases. For production models, consider UUID/string business IDs via `@GeneratedValue(UUIDStringGenerator.class)` or assigned stable IDs with matching constraints.

The class includes a no-arg constructor, a data constructor, and necessary getters/setters so Spring Data Neo4j can map fields and assign IDs. Do not use `jakarta.persistence.Entity` or JPA's `@GeneratedValue` in this file.

### 4.4. Author.java — root node and directed edge

Create `src/main/java/example/testing/neo4j/Author.java`:

```java
package example.testing.neo4j;

import java.util.ArrayList;
import java.util.List;

import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Author")
public class Author {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @Relationship(
            type = "WROTE",
            direction = Relationship.Direction.OUTGOING)
    private List<Book> books = new ArrayList<>();

    public Author() {
    }

    public Author(String name) {
        this.name = name;
    }

    public void addBook(Book book) {
        books.add(book);
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

    public List<Book> getBooks() {
        return books;
    }

    public void setBooks(List<Book> books) {
        this.books = new ArrayList<>(books);
    }
}
```

**Mapping meaning:**

- `@Relationship(type="WROTE", direction=OUTGOING)` creates **Author → Book** edges for elements in `books`.
- `Book` instances referenced from the aggregate root can be persisted together with `Author` under Spring Data Neo4j semantics; when reading `Author`, repository mapping restores queried relationships according to entity loading rules.
- `List<Book>` here does not guarantee **stored edge order** like a Java list. In tests, sort titles when business logic **does not require ordering**, rather than assuming reloads always match `addBook` order.
- Avoid creating bidirectional mappings that could cause recursive cycles or unintended duplicate graph edges without fully understanding ownership/direction.
- Do not confuse this `@Relationship` with JPA `@OneToMany`; Neo4j stores an **edge**, not a foreign key in a table.

If you need to store **properties directly on the edge** (such as `role`, `since`, `weight`), see `@RelationshipProperties`/`@TargetNode` in the advanced section. Do not place relationship fields on `Book` and silently treat them as per-edge data, because the same Book can link to multiple Authors with different roles.

### 4.5. AuthorRepository.java — derived and custom queries

Create `src/main/java/example/testing/neo4j/AuthorRepository.java`:

```java
package example.testing.neo4j;

import java.util.List;
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface AuthorRepository
        extends Neo4jRepository<Author, Long> {

    Optional<Author> findByName(String name);

    @Query("""
            MATCH (a:Author {name: $name})-[:WROTE]->(b:Book)
            RETURN b.title AS title
            ORDER BY title
            """)
    List<String> findBookTitles(
            @Param("name") String name);
}
```

**Two query styles:**

- `findByName` is a derived repository query on the `name` property of the `Author` node.
- `findBookTitles` uses `@Query` with explicit Cypher: filtering Author by `$name`, traversing `WROTE` in the right direction, and returning sorted titles. This is a **scalar projection** (`List<String>`) rather than asking SDN to hydrate a full `Author` aggregate from a custom Cypher query.
- `@Param("name")` safely binds the Java argument to `$name`; never concatenate strings from input.
- `ORDER BY title` makes assertions deterministic.

Standard `Neo4jRepository` methods such as `save`, `findById`, `findAll`, `deleteById`, `count`, and `existsById` are provided by Spring Data. Tests use the **real repository bean**, never mocking it, to prove Cypher and mapping actually work.

**Why not write `@Query("MATCH (a)-[r]->(b) RETURN a,r,b")` and assume it always maps cleanly?** Spring Data Neo4j has specific rules for assembling aggregates from records, nodes, and relationships. When a query returns multiple records per root or omits required relationship parts, entity mapping may not hydrate completely. When a query only needs scalars, return scalars; when hydrating complex graphs, structure Cypher to return complete root/nodes/relationships per SDN documentation.

## 5. Complete Testcontainers Neo4j + @DataNeo4jTest suite

Create `src/test/java/example/testing/neo4j/AuthorRepositoryTest.java`:

```java
package example.testing.neo4j;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.testcontainers.containers.Neo4jContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@DataNeo4jTest
class AuthorRepositoryTest {

    @Container
    @ServiceConnection
    static Neo4jContainer<?> neo4j =
            new Neo4jContainer<>("neo4j:5.26");

    @Autowired
    private AuthorRepository authors;

    @Autowired
    private Neo4jClient neo4jClient;

    private static Author authorWithTwoBooks() {
        Author author = new Author("An");
        author.addBook(new Book("Graph Basics", 2025));
        author.addBook(new Book("Cypher Patterns", 2024));
        return author;
    }

    private long countWroteEdges(String authorName) {
        return neo4jClient.query("""
                MATCH (a:Author {name: $name})
                      -[r:WROTE]->(b:Book)
                RETURN count(r) AS total
                """)
                .bind(authorName).to("name")
                .fetchAs(Long.class)
                .mappedBy((typeSystem, record) ->
                        record.get("total").asLong())
                .one()
                .orElseThrow();
    }

    @Test
    void savesRootAndRelatedNodes() {
        Author saved = authors.save(authorWithTwoBooks());

        assertNotNull(saved.getId());

        Author loaded = authors.findById(
                saved.getId()).orElseThrow();

        assertEquals("An", loaded.getName());
        assertEquals(2, loaded.getBooks().size());
        assertTrue(loaded.getBooks().stream()
                .allMatch(book -> book.getId() != null));
        assertEquals(2L, countWroteEdges("An"));
    }

    @Test
    void derivedQueryLoadsMappedRelationships() {
        authors.save(authorWithTwoBooks());

        Author loaded = authors.findByName("An").orElseThrow();

        List<String> titles = loaded.getBooks().stream()
                .map(Book::getTitle)
                .sorted()
                .toList();

        assertEquals(
                List.of("Cypher Patterns", "Graph Basics"),
                titles);
        assertTrue(authors.findByName("Missing").isEmpty());
    }

    @Test
    void customCypherUsesDirectionAndStableOrdering() {
        authors.save(authorWithTwoBooks());

        assertEquals(
                List.of("Cypher Patterns", "Graph Basics"),
                authors.findBookTitles("An"));
        assertEquals(List.of(), authors.findBookTitles("Mai"));
    }

    @Test
    void cypherParameterIsNotStringConcatenation() {
        authors.save(authorWithTwoBooks());

        List<String> result =
                authors.findBookTitles("An' OR true");

        assertTrue(result.isEmpty());
        assertEquals(2L, countWroteEdges("An"));
    }

    @Test
    void missingRootAndEmptyRelationshipsAreDistinct() {
        authors.save(new Author("Mai"));

        assertTrue(authors.findByName("Missing").isEmpty());
        assertTrue(
                authors.findByName("Mai")
                        .orElseThrow()
                        .getBooks()
                        .isEmpty());
        assertEquals(0L, countWroteEdges("Mai"));
    }

    @Test
    void updatesNodePropertyOnSave() {
        Author saved = authors.save(new Author("An"));

        saved.setName("An Updated");
        Author updated = authors.save(saved);

        assertEquals(
                "An Updated",
                authors.findById(updated.getId())
                        .orElseThrow()
                        .getName());
        assertTrue(authors.findByName("An").isEmpty());
    }

    @Test
    void deletingRootRemovesItsOutgoingEdges() {
        Author saved = authors.save(authorWithTwoBooks());

        assertEquals(2L, countWroteEdges("An"));
        authors.deleteById(saved.getId());

        assertFalse(authors.existsById(saved.getId()));
        assertEquals(0L, countWroteEdges("An"));
    }

    @Test
    void testsDoNotAssumeGeneratedIdValues() {
        Author saved = authors.save(new Author("Mai"));

        assertNotNull(saved.getId());
        assertTrue(authors.existsById(saved.getId()));
    }
}
```

**The class has exactly 8 `@Test` methods**. This is a Spring Data Neo4j slice test against a real Neo4j container. It checks **nodes + edges + scalar Cypher queries**, not a fake Java object.

### Why does @ServiceConnection work?

- `@Testcontainers` and `@Container` manage the Neo4j container lifecycle via the JUnit Testcontainers extension.
- Spring Boot's `@ServiceConnection` builds **`Neo4jConnectionDetails`** from the container and supplies it to Neo4j auto-configuration. This avoids hardcoding URIs, credentials, and random ports.
- `@DataNeo4jTest` remains a **slice**, not becoming `@SpringBootTest`; only relevant beans are loaded.
- Testcontainers Neo4j uses the Bolt driver to reach Neo4j inside the container; it is not a fake in-memory graph.
- Imperative tests in this class run in Spring-managed transactions and roll back by default. Each test builds its own fixtures without depending on execution order.

**Note:** Testcontainers 1.x (managed by the Boot 3.5 BOM) uses `org.testcontainers.containers.Neo4jContainer`. In Testcontainers 2.x, the package/module for Neo4j may differ; the code above intentionally targets **Boot 3.5** to avoid mixing different dependency generations.

### Breakdown of the eight cases

**Case 1 — save root + related nodes:** `authors.save(...)` persists one Author and two Books, plus two `WROTE` edges. The test reloads via `findById` and checks size 2 and non-null IDs. More importantly, `Neo4jClient` counts **real edges** via Cypher, not merely an in-memory List size.

**Case 2 — derived query:** `findByName("An")` finds the root and hydrates relationships; we **sort titles** before asserting because relationship collection order is not automatically a business contract. `findByName("Missing")` returns `Optional.empty()`, distinct from an Author with an empty Book list.

**Case 3 — custom Cypher:** tests `findBookTitles` on the real graph, filtering by `$name` and traversing `-[:WROTE]->` in the exact direction; `ORDER BY title` gives deterministic output. No fake query returning a constant string.

**Case 4 — parameters:** input `"An' OR true"` is passed as a **string parameter**, never concatenated into the Cypher statement. Zero matches are returned, while Author "An"'s graph still retains two edges. This test acts as a binding regression guard, **not a substitute for a security review of every query builder**.

**Case 5 — missing vs. empty relationships:** an unfound Author is `Optional.empty()`; finding "Mai" with zero books is a valid Author with `books=[]`. The test ensures these two states are never conflated.

**Case 6 — update node:** after saving, rename and save again. The test reads back the property via the repository and confirms the old name no longer matches. It does not mutate `saved.getName()` in Java memory and pretend SQL/Cypher ran.

**Case 7 — delete root:** verifies the root is gone and no `WROTE` edges originate from the old Author. **Do not conclude all Book nodes were deleted** because deletion of related nodes depends on ownership and aggregate persistence semantics; in graphs, multiple roots can reference the same node.

**Case 8 — generated ID:** checks only that the ID is non-null and the repository can look it up by ID. **Do not assert IDs must be 0, 1, or sequential**, since internal IDs are neither business keys nor API contracts.

### Why use Neo4jClient alongside the repository?

`Neo4jClient` lets you execute direct Cypher queries **inside the Spring-managed context/transaction**. The `countWroteEdges` helper:

```cypher
MATCH (a:Author {name: $name})-[r:WROTE]->(b:Book)
RETURN count(r) AS total
```

verifies the **relationship** count in storage rather than trusting the mapper blindly. `fetchAs(Long.class).mappedBy(...)` extracts the `total` field from the Neo4j result record, returning `Optional<Long>`; the test calls `orElseThrow()` in case no row is returned. With `count(...)`, Cypher returns one row with value 0 even when nothing matches.

**Do not switch to opening an independent Neo4j Java Driver session to inspect uncommitted writes of a test transaction** unless you fully understand transaction boundaries. A separate driver session will not see uncommitted changes inside the Spring-managed test transaction. An injected `Neo4jClient` participates in the proper transaction and provides real data verification.

## 6. Running and reading results

On macOS/Linux:

```bash
./gradlew test --tests example.testing.neo4j.AuthorRepositoryTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.testing.neo4j.AuthorRepositoryTest"
```

**Expected outcome when environment is ready:** 8 JUnit methods pass. A Neo4j container is created and started during the test class lifecycle; Spring Boot configures `Neo4jConnectionDetails` for repositories and the client to connect.

Console output varies by Gradle/JUnit version, so do not promise fixed stdout. If Docker is unavailable, tests may fail **before assertions run**; that is an environment/CI error and must not be misreported as a repository mapping failure.

**Checks to perform before changing test code:**

- `Could not connect to localhost:7687`: the test is falling back to the default URI instead of connection details; check `@ServiceConnection`, container startup, and dependencies.
- `No qualifying bean of type AuthorRepository`: check the Spring Data Neo4j starter, `GraphApplication`/repository packages, and `@DataNeo4jTest`.
- Mismatched package imports: do not mix Boot 3.5 with Boot 4 or Testcontainers 1.x with 2.x.
- Query misses relationships: check direction/type, `addBook(...)` setup, entity mapping, and transaction visibility.
- Cypher `ClientException`: inspect syntax error, label/property names, and parameter binding; do not blindly add `MATCH (n) DETACH DELETE n` at test startup to hide issues.
- Docker image pull failure: verify registry/network, Docker memory/cgroup, and compatible image tags.

## 7. Transaction rollback and test data isolation

### 7.1. Default behavior in imperative @DataNeo4jTest

In Spring Boot 3.5, imperative `@DataNeo4jTest` uses a test-managed transaction that rolls back at the end of each test method. The typical flow is:

```text
TestContext opens test transaction
          |
          v
@Test: authors.save(author)
          |
          v
@Test: authors.findById(...) + Neo4jClient query(...)
          |
          v
Assert values and relationships
          |
          v
TestContext rolls back transaction
```

This lets each test method in the example create independent fixtures. When a test both `save`s and calls `findById` within the same transaction, data is visible immediately, yet **that does not prove it committed** to the graph after the method finishes.

**Never have Test A create a node and Test B depend on it.** JUnit has no guaranteed execution order matching source code order. Do not assume data should be shared across methods just because the test class has a static container.

### 7.2. Disabling rollback when commit behavior truly must be tested

If the goal is to test behavior outside a test transaction, disable the transaction wrapper:

```java
@DataNeo4jTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class ExplicitCommitBehaviorTest {
    // Tests here must create their own fixtures and cleanup.
}
```

This is a **class skeleton**, omitting imports/fields/test methods; it is not a standalone runnable file. In this mode, repository methods/real transaction boundaries commit and **data is not automatically rolled back** at the end of the test method.

Use this setup only against a **dedicated test** Neo4j instance, with unique data namespaces/IDs and reliable cleanup. When a JUnit-managed container is owned by a single test class, container shutdown discards all ephemeral data; however, never rely on container shutdown for isolation when a container is shared across multiple classes.

### 7.3. Reactive Spring Data Neo4j is a special case

Spring Data Neo4j supports both imperative and reactive infrastructure depending on dependencies. However, **imperative test-managed `@Transactional` cannot directly manage Reactive Streams transactions** for repository methods returning `Mono`/`Flux`.

When testing reactive repositories:

- Configure the test with `@Transactional(propagation = NOT_SUPPORTED)` to avoid attaching an imperative test transaction to reactive access.
- Use `StepVerifier` to verify the publisher actually **subscribes/completes/errors**, rather than comparing `Mono` objects.
- For atomic rollback across reactive steps, use `TransactionalOperator` or a reactive service with explicitly designed and verified transaction semantics.
- Use a dedicated Neo4j instance/test database with cleanup; do not assume reactive tests auto-rollback just because the class has `@DataNeo4jTest`.
- Do not mix imperative and reactive repositories in one test expecting them to share a transaction across threads/contexts.

**The runnable example suite in this lesson uses exclusively imperative repositories.** This reactive section provides scoping guidance, not a claim that a complete reactive test is included.

## 8. Testing relationships with properties: @RelationshipProperties

In real graphs, relationships often carry data. For example, a person belongs to a project with a role and start year:

```text
(:Person {name:"An"})
   -[:MEMBER_OF {role:"LEAD", since:2023}]->
(:Project {key:"P-7"})
```

In Spring Data Neo4j, use `@RelationshipProperties` with `@TargetNode`. Below is a **conceptual** declaration pattern, not a standalone runnable file set because constructors/getters, graph classes, and repositories are omitted:

```java
@Node("Person")
class Person {
    @Id @GeneratedValue
    private Long id;

    @Relationship(type = "MEMBER_OF",
                  direction = Relationship.Direction.OUTGOING)
    private List<Membership> memberships = new ArrayList<>();
}

@RelationshipProperties
class Membership {
    @RelationshipId
    private Long relationshipId;

    private String role;
    private int since;

    @TargetNode
    private Project project;
}

@Node("Project")
class Project {
    @Id @GeneratedValue
    private Long id;

    private String key;
}
```

**What to test for relationship properties:**

1. A `MEMBER_OF` edge exists in the right direction.
2. `role`/`since` are actually stored on the **relationship**, not on Person or Project.
3. Reloading via the repository restores `Membership.role`/`since` and `@TargetNode Project` accurately.
4. Updating edge properties does not accidentally create duplicate edges or delete another subject's edge.
5. If multiple edges between the same source and target are allowed, assert **multiplicity** and real identity/semantics rather than just `count >= 1`.
6. If uniqueness is needed on the Person–Project pair or on role, define an explicit constraint/business policy; Neo4j does not forbid multiple relationships of the same type between two nodes by default.

**Why `@RelationshipId`?** Spring Data Neo4j needs to identify a specific relationship instance to safely manage lifecycle and update mapping. Never drop this annotation when building `@RelationshipProperties` in SDN 7.5 and rely purely on object references.

With bidirectional or self-referencing relationships, clearly define ownership/direction and prevent infinite mapping loops during HTTP JSON serialization. Richly connected graph entities should not be returned directly as REST response DTOs.

## 9. Graph query edge cases that must be tested explicitly

### 9.1. Directed edges and reversed patterns

Suppose `Author(An)-[:WROTE]->Book(Graph Basics)`. Test:

```cypher
MATCH (:Author {name: $name})-[:WROTE]->(:Book)
RETURN count(*) AS outgoing
```

and the counter-check:

```cypher
MATCH (:Book)-[:WROTE]->(:Author {name: $name})
RETURN count(*) AS reverse
```

In the graph created by the example, `outgoing=2` and `reverse=0`. If a developer accidentally flips `@Relationship(Direction.INCOMING)`, a test checking only "two books in the Java List" could miss it; a directional Cypher check catches it red-handed.

### 9.2. Multi-hop path traversal

People network example:

```cypher
MATCH p = (start:Person {name: $startName})
          -[:KNOWS*1..3]->
          (end:Person {name: $endName})
RETURN length(p) AS hops
```

This is a **query sample**, not executed in the Author/Book suite from Section 5 because it uses unseeded `Person` labels and `KNOWS` relationships. When writing path tests:

- Seed a small graph with known hop counts (e.g., A→B→C).
- Verify direction and `*1..3` bounds, avoiding unbounded queries that trigger huge traversals.
- A graph with multiple valid paths can return **multiple records**; never assume a single result.
- If shortest path is the goal, use syntax/queries matching your Cypher version and test ties with multiple equal-length paths.
- Do not claim a path result maps to a complete aggregate if the query omits nodes/relationships.

### 9.3. OPTIONAL MATCH and null

`OPTIONAL MATCH` has outer-match semantics where an Author without `WROTE` still appears with a null Book:

```cypher
MATCH (a:Author {name: $name})
OPTIONAL MATCH (a)-[:WROTE]->(b:Book)
RETURN a.name AS authorName, b.title AS bookTitle
```

For "Mai" with no books, the query returns a row where `bookTitle=null`. This **differs** from `MATCH (a)-[:WROTE]->(b)`, which returns zero rows when no edge exists. Tests should distinguish **missing root**, **root with empty collection**, and **optional null projection**.

### 9.4. Duplicates and multiple paths

Neo4j does not deduplicate records unless requested by the query or aggregation. `MATCH` over multiple edges/paths can emit multiple rows for the same node. When the business contract requires unique authors, use `DISTINCT` deliberately and assert exact counts. **Do not sprinkle `DISTINCT` casually** when relationship multiplicity is meaningful data to preserve.

### 9.5. Sorting and pagination

Without `ORDER BY`, the database does not guarantee record order. When an API requires ordering:

```cypher
MATCH (a:Author)-[:WROTE]->(b:Book)
RETURN b.title AS title
ORDER BY title ASC, elementId(b) ASC
SKIP $skip LIMIT $limit
```

This is a query snippet requiring `$skip` and `$limit` parameters; use `elementId(b)` only as a **tie-breaker within a single database/query**, never as a stable business identifier. For production pagination, prefer a stable/unique domain key to avoid shifting pages across requests.

If a repository method combines `Pageable` with a custom `@Query`, verify that the query template applies `SKIP/LIMIT`, sorting, and an appropriate count query. Do not assume SQL/JPA paging semantics are automatically injected into every hand-written Cypher query.

## 10. Unique constraints, indexes, and schema migrations

Unlike relational tests with a `schema.sql` creating tables, Neo4j does not require pre-creating "tables" for `Author` or `Book` before writing nodes. Still, production systems normally need **constraints/indexes**.

Cypher example:

```cypher
CREATE CONSTRAINT author_name_unique IF NOT EXISTS
FOR (a:Author) REQUIRE a.name IS UNIQUE
```

This constraint (Neo4j 5) forbids two `Author` nodes with duplicate `name` in that database. **It is not generated automatically from `@Node("Author")` or the `name` field alone.**

If a test wants to verify uniqueness:

1. Initialize the constraint through a valid schema migration/setup **before** the test transaction runs.
2. Create Authors with the same name in two separate write operations.
3. Expect the appropriate database/driver/Spring Data exception, not just a Java validator.
4. Note that constraint creation may be a **schema operation requiring its own transaction**; do not run DDL inside a DML test transaction expecting rollback to drop the constraint.
5. If a container is shared across classes, creating/dropping schema affects other tests; isolate database/schema/test lifecycle.

**Do not mechanically put constraint creation into every `@BeforeEach`.** DDL and indexing carry cost, and test transaction rollback is generally not meant to "undo schema" between methods. Use migrations or test fixture setup at the appropriate lifecycle scope, or a dedicated container for schema-focused tests.

An index speeds up queries, yet a 3-node unit graph test **does not prove query plans on production data**. When performance matters, use `EXPLAIN/PROFILE`, representative datasets, and the matching Neo4j engine/edition in tests separated from unit/repository correctness tests.

## 11. How do Neo4jClient, Neo4jTemplate, and repository tests differ?

| API | How it works | Suitable test |
| --- | --- | --- |
| `Neo4jRepository<Author, Long>` | Repository proxy, derived methods, custom `@Query` | Public repository contract |
| `Neo4jTemplate` | SDN mapping operations driven by domain metadata | Mapping/persistence outside repositories |
| `Neo4jClient` | Direct Cypher with parameter binding and result mapping | Query results, node/edge counts, custom projections |
| Neo4j Java `Driver` | Low-level Neo4j Bolt sessions/transactions | Connectivity/protocol, transaction handling, low-level graph |
| Mock repository | Never hits real Neo4j | Service logic needing a fake collaborator |

**Avoid circular self-verification:** if a production repository query is wrong and the test uses that exact same repository method to inspect expected data, both setup and assertion can share the bug. For graph tests, combining repository setup with an explicit `Neo4jClient` query (`MATCH ...-[r:TYPE]->...`) or inspecting the raw graph structure lowers that risk.

**However:** running `Neo4jClient` inside the same Spring test transaction sees uncommitted data — great for slice verification, yet it does not verify commit/isolation on a separate connection. When testing transaction boundaries, design explicit integration tests and avoid confusing test transactions with production transactions.

### Careful with full-aggregate query mapping

Suppose a custom query returns multiple records for the same `Author`:

```cypher
MATCH (a:Author)-[r:WROTE]->(b:Book)
RETURN a, r, b
```

When asking SDN to assemble an aggregate with all related nodes, follow Spring Data Neo4j documentation on collecting relationships and nodes **one record per root** or path mapping. Returning multiple rows with duplicate roots in an unexpected shape can leave collection properties incompletely hydrated.

In the runnable example, the custom query returns `List<String>` to avoid mixing a scalar projection test with aggregate hydration complexities. The derived `findByName` query handles testing the Author→Books relationship hydration.

## 12. H2 cannot replace Neo4j; Testcontainers has limits too

**There is no `@AutoConfigureTestDatabase(replace = NONE)` equivalent in the JDBC sense for Neo4j.** That annotation controls SQL datasource replacement, not Neo4j graph databases. To connect to Neo4j, configure `spring.neo4j.*`/`Neo4jConnectionDetails` or a custom driver configuration.

In Boot 3.5, `@ServiceConnection` supplies connection details for `Neo4jContainer`; this keeps code concise and avoids mispointing URLs. If you cannot use it, `@DynamicPropertySource` with `registry.add("spring.neo4j.uri", container::getBoltUrl)` plus username/password works; **never mix both arbitrarily** and create competing configuration sources.

Testcontainers provides:

- A real Neo4j engine over Bolt in an isolated container.
- The ability to test real data mapping, Cypher, transactions, and database errors.
- A consistent environment across developer machines and Docker-enabled CI.

Yet it does not automatically prove:

- Production clustering, replica routing, high availability, and transaction bookmarks.
- Cloud authentication, TLS certificates, network latency, and reverse proxies.
- Production data volumes/index cardinality, plan caches, and performance.
- Production user privileges, role-based authorization/enterprise features.
- Production-equivalent plugin/extension configs or migrations.

Therefore, add targeted integration/E2E tests when risks sit outside the repository boundary.

## 13. Clean test data and avoiding @DirtiesContext misuse

Each method in `AuthorRepositoryTest` creates its own Author/Book fixtures, and imperative transaction rollback guarantees test-managed DML leaves no committed nodes behind. That is usually enough to keep methods independent.

However, **exceptions exist**:

- Tests disabling `@Transactional` or using `Propagation.NOT_SUPPORTED`.
- Work executing in a separate/`REQUIRES_NEW` transaction that commits outside the test transaction.
- Reactive pipelines that do not join imperative test transactions.
- Low-level driver code opening independent sessions, external workers, or asynchronous side effects committing independently.
- Tests creating schema constraints/indexes, external events, or caches that do not roll back with the test transaction.

In those cases, use a dedicated test DB/container, stable fixture IDs, and explicit cleanup. **Never run `MATCH (n) DETACH DELETE n` on a database not verified as test-only.**

`@DirtiesContext` forces Spring TestContext to rebuild the context when needed, yet **it is not a Neo4j server reset command**. Rebuilding contexts is expensive and does not wipe committed data from a running container. Only use `@DirtiesContext` when Spring context state itself was mutated and cannot be safely reset.

### Container lifecycle and cached ApplicationContext

A `static @Container` belongs to the JUnit class lifecycle; a Spring context can be cached/reused across classes. If a cached context holds a Neo4j Driver pointing to a container stopped at the end of a previous class, a subsequent test class reusing that context can fail unexpectedly.

Ways to avoid this:

- For single-class examples, a JUnit-managed static container suffices.
- When sharing across multiple test classes, consider a **context-scoped container bean** or a lifecycle-aligned shared container so the container outlives every context using it.
- Do not enable parallel tests sharing one graph database with conflicting seeds/cleanups without proper isolation.
- Do not hold mutable global containers/static repositories across unrelated suites without lifecycle control.

**A test passing alone yet failing in the full suite** is usually a sign of wrongly shared state, transactions, or container lifecycle.

## 14. Plain Java 17 example: distinguishing edge direction without Neo4j

To see what can be tested with plain JUnit and what **requires a database**, we create a small rule counting directed relationships over a Java dataset:

Create `src/main/java/example/testing/neo4j/GraphRule.java`:

```java
package example.testing.neo4j;

import java.util.List;
import java.util.Objects;

public final class GraphRule {
    private GraphRule() {
    }

    public record Edge(String from, String to) {
    }

    public static long outgoingCount(
            List<Edge> edges, String from) {
        Objects.requireNonNull(edges, "edges");
        return edges.stream()
                .filter(edge -> Objects.equals(
                        edge.from(), from))
                .count();
    }

    public static boolean hasDirectedEdge(
            List<Edge> edges, String from, String to) {
        return edges.stream()
                .anyMatch(edge -> Objects.equals(
                        edge.from(), from)
                        && Objects.equals(edge.to(), to));
    }
}
```

Create `src/main/java/example/testing/neo4j/GraphRuleDemo.java`:

```java
package example.testing.neo4j;

import java.util.List;

public class GraphRuleDemo {
    public static void main(String[] args) {
        List<GraphRule.Edge> edges = List.of(
                new GraphRule.Edge("An", "Graph Basics"),
                new GraphRule.Edge("An", "Cypher Patterns"),
                new GraphRule.Edge("Mai", "Data Modeling"));

        System.out.println(
                GraphRule.outgoingCount(edges, "An"));
        System.out.println(
                GraphRule.hasDirectedEdge(
                        edges, "An", "Graph Basics"));
        System.out.println(
                GraphRule.hasDirectedEdge(
                        edges, "Graph Basics", "An"));
    }
}
```

Compile/run with JDK 17+ from the project root:

```bash
javac -d out src/main/java/example/testing/neo4j/GraphRule.java src/main/java/example/testing/neo4j/GraphRuleDemo.java
java -cp out example.testing.neo4j.GraphRuleDemo
```

**Exact** stdout:

```text
2
true
false
```

Create `src/test/java/example/testing/neo4j/GraphRuleTest.java`:

```java
package example.testing.neo4j;

import java.util.List;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class GraphRuleTest {

    @Test
    void countsOutgoingEdgesOnly() {
        List<GraphRule.Edge> edges = List.of(
                new GraphRule.Edge("An", "Book A"),
                new GraphRule.Edge("Book A", "An"),
                new GraphRule.Edge("An", "Book B"));

        assertEquals(2L, GraphRule.outgoingCount(edges, "An"));
    }

    @Test
    void directionIsNotSymmetricByDefault() {
        List<GraphRule.Edge> edges = List.of(
                new GraphRule.Edge("An", "Book A"));

        assertTrue(
                GraphRule.hasDirectedEdge(
                        edges, "An", "Book A"));
        assertFalse(
                GraphRule.hasDirectedEdge(
                        edges, "Book A", "An"));
    }
}
```

These are **2 JUnit unit tests**, running without a Spring context or Neo4j:

```bash
./gradlew test --tests example.testing.neo4j.GraphRuleTest
```

**Draw a clear boundary:** the plain Java cases only prove `GraphRule` logic over a mock `List<Edge>`. They **do not prove** Spring Data Neo4j created `WROTE` edges in the database. The `@DataNeo4jTest` with `Neo4jClient` provides the required evidence for real mapping and Cypher.

## 15. Debugging and common pitfalls

**1. Assuming `@DataNeo4jTest` auto-starts embedded Neo4j.** Spring Data Neo4j 7.x does not bundle a database automatically; you need Testcontainers, the test harness, or a test server.

**2. Using `@DataJpaTest` for `@Node`.** JPA/Hibernate does not process Spring Data Neo4j mappings. Pick the slice matching the persistence technology.

**3. Importing the wrong `@DataNeo4jTest` package between Boot 3.5 and Boot 4.** Check the BOM/module/version and actual imports; never mix snippets from two generations.

**4. Mocking `AuthorRepository` and claiming Cypher works.** Mocks never speak Bolt or check labels/edges/queries. Keep the real repository and client in slice tests.

**5. Asserting only Java List size before saving.** That does not prove the database holds the edge. Query Cypher to count relationships after saving.

**6. Confusing `INCOMING` and `OUTGOING`.** Two nodes connected in opposite directions represent different relationships; test direction against the contract.

**7. Testing `findById` without checking related nodes.** Root fields can be right while relationship mapping is broken; test hydration and query edge counts.

**8. Trusting relationship List order.** Without explicit ordering, the database does not promise insertion order. Assert sets or sorted values when order is not a contract.

**9. Building Cypher by concatenating input.** Use `$parameter` and `@Param`/`Neo4jClient.bind` instead of string interpolation.

**10. Returning duplicate root records from custom queries and expecting complete mapping.** SDN has strict expectations for record/node/relationship shapes; use scalar projections or controlled custom mapping.

**11. Confusing a missing root with a root having an empty collection.** `Optional.empty` differs from `Author.books=[]`. Write tests for both cases.

**12. Assuming internal Neo4j IDs are business keys.** Never assert sequential IDs or expose them as stable public identifiers; prefer UUIDs/keys with constraints when needed.

**13. Forgetting UNIQUE constraints or schema migrations.** Neo4j does not create uniqueness constraints from `@Node` alone; constraint tests need proper lifecycle DB setup.

**14. Running constraint DDL inside a test transaction expecting rollback.** Schema lifecycle differs from DML; run via appropriate test DB setup/migrations.

**15. Adding `@Transactional` thinking reactive writes will roll back.** Imperative test-managed transactions do not cover reactive pipelines; use `ReactiveTransactionManager`/`TransactionalOperator` and cleanup.

**16. Letting tests commit data and relying on order.** Test classes sharing a Neo4j container can leak nodes; keep transaction rollback or explicit cleanup.

**17. Opening another Neo4j Driver session to read uncommitted data.** An independent connection/transaction cannot see uncommitted rows/nodes from the test; understand transaction boundaries.

**18. Neglecting Docker/container lifecycle.** Context caches can outlive containers; when multiple classes share a context, align their lifecycles.

**19. Using tiny test graphs to prove production index/performance.** That requires representative datasets, `EXPLAIN/PROFILE`, and production-like environments.

**20. Using `@SpringBootTest` for every repository test.** Full contexts are slower and harder to diagnose; use the slice when only Cypher/mapping is needed.

## 16. QA checklist for @DataNeo4jTest

**Before running:**

- Are Spring Boot, Spring Data Neo4j, and Testcontainers versions aligned?
- Are `@Node`, `@Id`, `@GeneratedValue`, and `@Relationship` imported from **Spring Data Neo4j**, not JPA?
- Is there a real Neo4j test instance with valid `@ServiceConnection` or `@DynamicPropertySource`?
- Does the test connect to a **test database**, never production?
- Is container lifecycle compatible with context caching and parallel execution?

**For mapping:**

- Did we check node labels, properties, generated IDs, and reload from the database?
- Do edges have the exact **type, direction, and count**?
- Are there child objects/nested relationships needing hydration?
- Do collection tests compare contents without relying on unguaranteed ordering?
- If relationship properties exist, are they saved/read accurately with `@TargetNode`/`@RelationshipId`?

**For Cypher:**

- Do queries use `$params` instead of string concatenation?
- Are match, no-match, missing root, and empty relationships all tested?
- Do `MATCH`/`OPTIONAL MATCH` and null semantics match the contract?
- Does the query return scalars or a full aggregate? Does the record shape support mapping?
- Is `ORDER BY` present whenever tests/apps depend on deterministic ordering?
- Are contractual constraints/indexes/migrations set up and tested separately?

**For isolation and quality:**

- Do imperative tests roll back? Are we careful not to assume data was committed?
- Do reactive tests have their own transaction/cleanup without relying on imperative rollback?
- When transactions are disabled, are test data cleanup and dedicated namespaces in place?
- Are repository and `Neo4jClient` combined to verify the real graph?
- Are service/controller/security tests kept at their own appropriate levels?
- Are Testcontainers startup failures distinguished from code bugs when Docker fails?
- Are test conclusions kept strictly within **Neo4j graph/persistence** boundaries?

**Conclusion:** `@DataNeo4jTest` is the right choice to verify **node/relationship mapping and Cypher repository queries** in a narrow Spring context **with a real Neo4j instance**. For meaningful tests, prove `WROTE` edges by **type + direction + count**, verify loaded nodes, and confirm query results bind and sort cleanly. Testcontainers + `@ServiceConnection` yield a repeatable environment; transaction rollback isolates imperative tests. For reactive access, schema constraints, multi-service orchestration, or production performance, add tests at their respective boundaries rather than extrapolating from a green slice.

## 17. References

- [Spring Boot 3.5 — Auto-configured Data Neo4j Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@DataNeo4jTest` scope, rollback, and reactive caveats.
- [Spring Data Neo4j 7.5 — Testing with Spring Boot](https://docs.spring.io/spring-data/neo4j/reference/7.5/testing/testing-with-spring-boot.html): Neo4jClient/repository slice and Testcontainers/harness.
- [Spring Boot 3.4/3.5 — Testcontainers Service Connections](https://docs.spring.io/spring-boot/3.4/reference/testing/testcontainers.html): `Neo4jContainer`, `@ServiceConnection`/`Neo4jConnectionDetails`.
- [Spring Data Neo4j — Metadata-based Mapping](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html): `@Node`, `@Relationship`, `@RelationshipProperties`, and `@TargetNode`.
- [Spring Data Neo4j 7.5 — Handling IDs](https://docs.spring.io/spring-data/neo4j/reference/7.5/object-mapping/mapping-ids.html): internal IDs, UUID generators, and business keys.
- [Spring Data Neo4j — Custom Queries](https://docs.spring.io/spring-data/neo4j/reference/appendix/custom-queries.html): `@Query`, parameter binding, and aggregate mapping pitfalls.
