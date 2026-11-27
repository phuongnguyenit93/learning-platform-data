# Comparing Generated SQL and Relationship Fetching Behavior After an Upgrade

## 1. Objective: verify actual behavior, not just application startup

When upgrading **Spring Data JPA**, **Spring Boot**, **Hibernate/JPA provider**, or drivers/database dialects, repository code and JPQL may stay unchanged while generated SQL, query plans, number of relationship loads, and association initialization timing still change. A test suite that only confirms the application starts or an API returns HTTP 200 will miss these issues.

For example, consider an API returning a list of 100 books with author names:
- Before upgrade: one query fetches books and a few queries fetch authors.
- After upgrade: query count jumps into the dozens or `JOIN` count increases sharply; the JSON output still looks correct, but response latency degrades noticeably.
- Another variation: after upgrading, related data remains an uninitialized proxy; when the web layer serializes outside the transaction, the API throws `LazyInitializationException`.
- In the opposite direction: due to a fetch plan change, the ORM starts loading more tables/collections than expected; RAM consumption and bytes transferred from the database rise even though SQL count drops.

**Verification has two independent parts:**
1. **Correctness:** right entity count, right relationships, no dropped records, no wrongly duplicated records, right ordering, right pages, and right API payload.
2. **Performance/SQL:** actual executed SQL, bind values, round-trip count, rows read, joins/subselects, indexes, and execution plans suitable for real load.

Do not automatically treat changed SQL aliases, column order, or parenthesization as bugs. JPA does not promise identical literal SQL strings across providers/versions; what must be protected are **semantics, data-loading contracts, and evidence-backed performance thresholds**.

## 2. Which components can change during an upgrade?

| Changed layer | Impact to observe |
| --- | --- |
| Spring Boot dependency management | Versions of Spring Data, Hibernate, JDBC driver, transaction infrastructure |
| Spring Data JPA | Repository query derivation, `@Query` parsing, projections, count queries, `Pageable`, `@EntityGraph` |
| Hibernate/JPA provider | Translating JPQL/Criteria to SQL, fetch plans, join result processing, lazy proxies, batch fetching, caching |
| Jakarta Persistence | Mapping `@OneToMany`, `@ManyToOne`, `@OneToOne`, `@ManyToMany`, `FetchType`, entity graphs, and lifecycle |
| JDBC driver and dialect | SQL pagination, parameter type binding, function/sequence syntax, DB capabilities, execution plans |
| Database schema/indexes/data | Foreign keys, cardinality, optimizer statistics, indexes, row counts, and selectivity |
| Application configuration | Open EntityManager in View (OSIV), transaction scope, L2/query cache, `default_batch_fetch_size`, filters |
| Serialization layer | DTO mapping, Jackson getters, whether lazy associations are accessed in transactions or controllers |

Changing multiple layers at once makes attribution difficult. Before comparing, **record exact versions** of Spring Boot, Spring Data JPA, Hibernate, Java, JDBC driver, database engine, and dialect on both baseline and target. Do not write only "Hibernate 6" because minor releases can modify query translation or fetch behavior.

**Notable case: Hibernate 5.x → 6.x.** Hibernate 6 moved to the new SQL AST/SQM model, so SQL shape can change: column aliases, unnecessary joins, path resolution, results of certain HQL queries, fetch logic, and pagination. The Hibernate 6.0 migration guide also notes:
- Hibernate 6 automatically deduplicates identical root entities in collection `join fetch` results; `distinct` in JPQL/HQL is also passed through to SQL, and the old hint `HINT_PASS_DISTINCT_THROUGH` was removed.
- Traversing eager associations in certain graphs/self-referential relationships can generate more joins.
- Certain `@Fetch(FetchMode.JOIN)` configurations combined with lazy settings handle laziness differently than before.
- Moving `javax.persistence.*` → `jakarta.persistence.*` during Jakarta upgrades; mappings and related APIs must be rechecked.

**Do not apply every item above mechanically to all Hibernate releases:** read the migration guide for the *exact* source/target versions and verify using measured SQL.

## 3. Understanding relationship fetch modes before comparing

### 3.1. Mapping fetch mode is a starting point, not the measured SQL result

By JPA defaults:
- `@ManyToOne` and `@OneToOne`: `FetchType.EAGER`.
- `@OneToMany` and `@ManyToMany`: `FetchType.LAZY`.

`EAGER` requires the provider to load the corresponding association; this **does not mean it must use a single SQL statement**. The provider may emit a `JOIN` or secondary selects. `LAZY` intentionally defers loading, and exact support can depend on the provider, proxies, bytecode enhancement, relationship type, and mapping. In particular, the inverse side of `@OneToOne` and optional relationships have cases where Hibernate must issue an extra query to determine whether the linked entity exists.

A repository method with `@EntityGraph`, JPQL `join fetch`, Hibernate `@Fetch`, or batch fetching can **override/augment the mapping's fetch plan**. When comparing, inspect both the entity annotations **and** the specific repository call.

Minimal example:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "author_id", nullable = false)
private BookAuthor author;
```

The `author` association is not necessarily fully loaded alongside root `Book` when only querying the book list. When calling `book.getAuthor().getName()`, the provider may need to issue additional SQL. If two books share the same author within the same persistence context, each book will not necessarily trigger a separate SQL statement: JPA L1 can reuse the entity by id.

### 3.2. N+1 behavior depends on the access path

A common N+1 example: the first `SELECT` loads N root entities, and reading an association property on each root triggers secondary `SELECT`s. However, actual query count is influenced by:
- the number of **distinct** linked IDs and entities already managed in L1;
- Hibernate L2 cache and query cache (if enabled);
- `@BatchSize` / `hibernate.default_batch_fetch_size` or subselect fetching;
- graphs, join fetches, or fetch depth;
- where getters are accessed: service, DTO mapper, Jackson serializer, logs, or `toString()`.

Therefore, "N+1 = literally N+1 SQL statements" is the name of a problem pattern, **not a formula that holds for every fixture**.

### 3.3. Loading collections and pagination carry extra risks

`JOIN FETCH` on a `@OneToMany` collection causes a root with multiple children to appear as multiple **SQL rows**. Hibernate may return a single root entity in Java results depending on version/handling, yet the number of rows transferred over JDBC can still surge.

Combining pagination directly with collection fetch joins is error-prone or expensive: Hibernate may load many rows and paginate in memory; when `hibernate.query.fail_on_pagination_over_collection_fetch=true` is enabled, it can throw an error instead of doing this silently. Test `Page.getTotalElements()`, distinct element count, ordering, and actual SQL.

A common approach when paginating:
1. Query the **page of root IDs** with stable filters and ordering.
2. Issue a second query fetching relationships for that ID set using `IN`, `@EntityGraph`, or a dedicated query.
3. Re-sort the final results according to the original ID order in the application if the second SQL query does not preserve order.

Do not assume `JOIN FETCH` across multiple collections to "reduce SQL count" is always better: row multiplication/Cartesian products and multiple bag fetch errors can make that approach worse than batch loading.

## 4. Setting up a before-and-after comparison

### 4.1. Lock down variables for a fair comparison

Before changing dependencies, create a **reproducible baseline**:

1. Save the old application commit/tag along with lockfiles/dependency tree (`mvn dependency:tree` or `./gradlew dependencies`).
2. Record versions of Java, Spring Boot, Spring Data JPA, Hibernate, driver, database, dialect, and key settings.
3. Use the same schema migrations (Flyway/Liquibase), indexes, and **realistic correlated data fixtures**: multiple roots, few/many children, null relationships, soft-deleted rows, multiple tenants, large volumes.
4. Keep the same transaction scopes, OSIV, fetch graphs, repository methods, DTO logic, and getter access timing.
5. Separate **cold cache** and **warm cache** runs. Clear L1 between measurements; enable/disable L2/query cache per scenario. Do not let an earlier run accidentally speed up the next.
6. Run against the same database engine/version (ideally a production-equivalent container); changing both the database and Hibernate simultaneously prevents root-cause attribution.
7. Run identical workloads: query parameters, page sizes, sorting, concurrency, data scale, and connection pools.

With Spring Boot, check the actually resolved runtime dependencies rather than looking only at versions in `pom.xml`/`build.gradle`. Another library can pull in a different Hibernate version via dependency overrides.

### 4.2. Business flows that must be baselined

Select a set of key queries, including at least:
- `findById` of a root and accessing to-one/to-many associations;
- repository `findAll`/derived queries and DTO mapping using associations;
- queries with `@Query`, `@EntityGraph`, or `join fetch`;
- pagination + sorting + filtering, especially with to-many associations;
- interface/DTO projections, native queries, and Criteria/Specifications if used by the application;
- lazy access **after transaction** when `spring.jpa.open-in-view=false`;
- writing data and reading it back in a separate transaction so L1 does not mask changes;
- soft-delete/tenant filters/inheritance/self-references if present in the domain.

Not every query needs a literal SQL string snapshot. Pick places where SQL shape is part of the contract to control: avoiding full table scans, not emitting extra queries per record, and preserving filter predicates.

## 5. Enabling logging and metrics at the right layer

### 5.1. Hibernate 6: SQL, bind parameters, and statistics

In dev/test environments (never enable TRACE bind logging containing sensitive data in production):

**`src/test/resources/application.properties`**

```properties
spring.jpa.show-sql=false
spring.jpa.properties.hibernate.format_sql=true
spring.jpa.properties.hibernate.generate_statistics=true
spring.jpa.properties.hibernate.cache.use_second_level_cache=false
spring.jpa.properties.hibernate.cache.use_query_cache=false
spring.jpa.open-in-view=false

logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

`org.hibernate.SQL` logs SQL templates. The `org.hibernate.orm.jdbc.bind` logger (Hibernate 6) shows bound values and data types; Hibernate 5.x used loggers such as `org.hibernate.type.descriptor.sql.BasicBinder`. Exact log configuration **must be verified against the actual version**. When comparing, save bind values too: two identical SQL text statements with different bound conditions can execute completely different plans.

You can retrieve `Statistics` from Hibernate `SessionFactory`:

```java
SessionFactory sessionFactory =
        entityManagerFactory.unwrap(SessionFactory.class);
Statistics stats = sessionFactory.getStatistics();

long sqlStatements = stats.getPrepareStatementCount();
long entityLoads = stats.getEntityLoadCount();
long collectionFetches = stats.getCollectionFetchCount();
```

This is an **illustrative snippet inside a method** having an `entityManagerFactory` variable and imports `org.hibernate.SessionFactory`, `org.hibernate.stat.Statistics`. Counters must be enabled before measuring and cleared/reset before each scenario. `Statistics` metrics are SessionFactory-scoped; if tests run in parallel, they can mix in other activity. `getPrepareStatementCount()` counts JDBC prepared statements, **not latency or physical rows read**.

Between Hibernate 5 and Hibernate 6, version-specific logger/statistics API changes are also part of the upgrade plan; do not copy old configuration and assume logging is active.

### 5.2. Adding SQL capture and database plans

For exact per-test comparison, you can use Hibernate's `StatementInspector` or a JDBC datasource proxy/P6Spy in tests to capture SQL **for a specific flow/transaction**. Log only allowed bind parameters; avoid leaking tokens, personal data, or secrets.

For slow queries, capture `EXPLAIN`/`EXPLAIN ANALYZE` on the target database; measure:
- `JOIN`/`SELECT` shape, filters/ordering, indexes, and scan types;
- estimated vs. actual rows, sorts/hashes, nested loops, temporary data;
- database time and application time;
- p50/p95/p99 latency under sufficient workload.

Shorter-looking SQL is not necessarily faster. One complex `JOIN` can cost more than several small `SELECT`s; the goal is accurate data access at acceptable latency.

## 6. Java 17+ example usable as a regression test

The files below use Spring Boot 3.x, Spring Data JPA, Hibernate 6.x, Java 17+, and H2 for testing. Place them in package `example.sqlcompare`; dependencies needed are `spring-boot-starter-data-jpa`, `spring-boot-starter-test`, and `com.h2database:h2` at test runtime. The test uses Hibernate statistics to measure **the same dataset**, comparing lazy loading, `join fetch`, and `@EntityGraph`.

H2 is only an environment for demonstrating the verification technique. To draw conclusions about production SQL and execution plans, run an additional test suite against the real database/dialect (such as PostgreSQL Testcontainers) with actual schema migrations.

### 6.1. Application bootstrap

**`JpaSqlCompareApplication.java`**

```java
package example.sqlcompare;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JpaSqlCompareApplication {
    public static void main(String[] args) {
        SpringApplication.run(JpaSqlCompareApplication.class, args);
    }
}
```

### 6.2. Two entities with a many-books → one-author relationship

**`BookAuthor.java`**

```java
package example.sqlcompare;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "book_authors")
public class BookAuthor {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected BookAuthor() {
    }

    public BookAuthor(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

**`LibraryBook.java`**

```java
package example.sqlcompare;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "library_books")
public class LibraryBook {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String title;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "author_id", nullable = false)
    private BookAuthor author;

    protected LibraryBook() {
    }

    public LibraryBook(String title, BookAuthor author) {
        this.title = title;
        this.author = author;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public BookAuthor getAuthor() {
        return author;
    }
}
```

### 6.3. Repository with three fetch plans

**`LibraryBookRepository.java`**

```java
package example.sqlcompare;

import java.util.List;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface LibraryBookRepository
        extends JpaRepository<LibraryBook, Long> {

    @Query("""
        select b from LibraryBook b
        join fetch b.author
        order by b.id
        """)
    List<LibraryBook> findAllWithAuthor();

    @EntityGraph(attributePaths = "author")
    @Query("select b from LibraryBook b order by b.id")
    List<LibraryBook> findAllWithAuthorGraph();
}
```

- `findAll(Sort.by("id"))` inherited from `JpaRepository`: loads root books while the author association remains lazy.
- `findAllWithAuthor()` specifies `join fetch`: in this to-one scenario, Hibernate typically brings books and authors in **a single SQL JOIN**.
- `findAllWithAuthorGraph()` specifies a fetch graph for `author`. `@EntityGraph` declares which attributes to load; it **does not promise identical SQL JOIN strings as JPQL** across every provider and version.

### 6.4. Test measuring SQL count and comparing contents

**`src/test/java/example/sqlcompare/FetchPlanRegressionTest.java`**

```java
package example.sqlcompare;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.PersistenceContext;
import java.util.List;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Sort;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest(properties = {
        "spring.jpa.properties.hibernate.generate_statistics=true",
        "spring.jpa.properties.hibernate.cache.use_second_level_cache=false",
        "spring.jpa.properties.hibernate.cache.use_query_cache=false"
})
class FetchPlanRegressionTest {
    @PersistenceContext
    EntityManager entityManager;

    @Autowired
    EntityManagerFactory entityManagerFactory;

    @Autowired
    LibraryBookRepository repository;

    @Test
    void comparesLazyAccessWithFetchJoinAndEntityGraph() {
        BookAuthor an = new BookAuthor("An");
        BookAuthor binh = new BookAuthor("Binh");
        entityManager.persist(an);
        entityManager.persist(binh);

        entityManager.persist(new LibraryBook("Book-1", an));
        entityManager.persist(new LibraryBook("Book-2", binh));
        entityManager.persist(new LibraryBook("Book-3", an));

        entityManager.flush();
        entityManager.clear();

        Statistics stats = entityManagerFactory
                .unwrap(SessionFactory.class).getStatistics();

        // Case 1: query roots then access LAZY association.
        stats.clear();
        List<LibraryBook> plain = repository.findAll(Sort.by("id"));
        List<String> plainNames = plain.stream()
                .map(book -> book.getAuthor().getName())
                .toList();
        long plainSql = stats.getPrepareStatementCount();

        // Case 2: JPQL fetch join.
        entityManager.clear();
        stats.clear();
        List<LibraryBook> joined = repository.findAllWithAuthor();
        List<String> joinedNames = joined.stream()
                .map(book -> book.getAuthor().getName())
                .toList();
        long joinedSql = stats.getPrepareStatementCount();

        // Case 3: EntityGraph.
        entityManager.clear();
        stats.clear();
        List<LibraryBook> graphed = repository.findAllWithAuthorGraph();
        List<String> graphNames = graphed.stream()
                .map(book -> book.getAuthor().getName())
                .toList();
        long graphSql = stats.getPrepareStatementCount();

        assertThat(plainNames).containsExactly("An", "Binh", "An");
        assertThat(joinedNames).isEqualTo(plainNames);
        assertThat(graphNames).isEqualTo(plainNames);

        assertThat(joinedSql).isEqualTo(1L);
        assertThat(plainSql).isGreaterThan(joinedSql);
        assertThat(graphSql).isEqualTo(1L);
    }
}
```

Run in a Maven project with the Maven Wrapper:

```bash
./mvnw test -Dtest=FetchPlanRegressionTest
```

On Windows, you can run `mvnw.cmd test -Dtest=FetchPlanRegressionTest`. With Gradle, run the `test` task with an equivalent filter. The test **does not assert on application stdout**; the success condition is the test PASSING with all three assertion groups.

The fixture has 3 books and 2 distinct authors. Without L2 cache enabled, reading the root list then accessing LAZY authors typically yields **1 book query + 2 author queries**, whereas join fetching a to-one relationship typically requires **1 query**. The assertions only require `plainSql > joinedSql` to avoid coupling the test to implementation-optimized lazy query counts; `joinedSql == 1` and `graphSql == 1` are **expected verification baselines for this Hibernate 6 + H2 example**. If an upgrade changes that, inspect the SQL and root cause before updating expectations.

`Statistics` accumulates across the `SessionFactory`: run this test in isolation, not in parallel with other tests sharing the same factory when strict counts are needed. Calling `clear()` after each scenario prevents L1-managed entities from letting the next scenario skip queries. Seeding and flushing happen **before** `stats.clear()` so `INSERT` statements do not skew the measurement.

### 6.5. Adapting to production

When the application has multiple relationships, also test:
- `@OneToMany` collections with 0, 1, and many elements; verify total rows and unique root ID sets.
- Nullable associations and tables with filtered/soft-deleted data; compare `LEFT JOIN` vs. `INNER JOIN`.
- First page, middle page, and last page; ensure deterministic order and accurate `totalElements`.
- Projection queries selecting a subset of columns; guard against loading the entire graph unintentionally.
- Paths read from controllers/mappers; test with OSIV disabled to expose lazy access outside transactions.

If a business case allows the backend to issue multiple SQL statements and still stay fast, do not refactor code solely to reach one SQL statement. Instead of applying the example's expectations universally, establish dedicated query/latency budgets based on data and SLAs.

## 7. Reading SQL diffs after an upgrade

### 7.1. What should be compared?

| Attribute | What to inspect during comparison |
| --- | --- |
| Total statement count | Did N+1 appear or extra queries fire during DTO/JSON serialization? |
| SQL type | `SELECT`, `UPDATE`, `DELETE`, count query, subselect |
| `JOIN` count and direction | `INNER` vs `LEFT`; are roots without children dropped, or are extra fetches occurring? |
| `WHERE` | Are tenant/soft-delete/authorization predicates still accurate? |
| `ORDER BY` / pagination | Is order deterministic, and is offset/limit pushed down to the DB? |
| Bind parameters | Do different values/types alter the query plan? |
| Rows/cardinality | Is to-many causing row multiplication, or are wrong joins dropping rows? |
| Select list | Are too many columns/LOBs loaded, or did alias changes break native mapping? |
| DB execution plan | Index scan/seq scan, sort/hash, estimated vs actual rows |
| Entity initialization | Which relationships initialize before/after access, are there secondary selects? |
| Result/data | Are JSON/DTO, root IDs, child IDs, counts, and pages accurate? |
| Cache | L1/L2/query cache hits/misses; is caching hiding SQL queries? |

The SQL snippets below are **shape illustrations**, not guaranteed literal Hibernate output:

Without fetching author:

```sql
SELECT b.id, b.title, b.author_id
FROM library_books b
ORDER BY b.id;

-- May be issued later upon accessing getAuthor().getName():
SELECT a.id, a.name
FROM book_authors a
WHERE a.id = ?;
```

To-one fetch join:

```sql
SELECT b.id, b.title, b.author_id, a.id, a.name
FROM library_books b
JOIN book_authors a ON a.id = b.author_id
ORDER BY b.id;
```

Aliases, column ordering, join syntax, and SQL wrapping can vary by ORM/dialect. Compare by **SQL shape + parameters + results + SQL count**; raw string comparison produces too many false positives.

### 7.2. Recording evidence-backed comparison results

A report template for each critical query:

| Field | Content |
| --- | --- |
| Query ID | `books.listWithAuthor` |
| Source | `LibraryBookRepository.findAllWithAuthor()` |
| Baseline | Commit, Boot/Data JPA/Hibernate/driver/dialect/database versions |
| Target | Corresponding commit and versions |
| Fixture | 3 books/2 authors for unit regression; production-like scale for benchmark |
| Result correctness | IDs, ordering, association values, page/count |
| SQL before/after | Sanitized log files, query location |
| Statement count | `plainSql`, `joinedSql`, `graphSql`, warm/cold |
| Plan/latency | `EXPLAIN ANALYZE`, p95 under described workload |
| Verdict | PASS, needs optimization, or evidenced regression |

Keep baseline and target artifacts separate. If an upgrade changes SQL aliases while query count, results, and performance remain sound, record a **valid change** rather than classifying it as a regression.

## 8. Common post-upgrade discrepancies and how to handle them

### 8.1. EAGER pulls in more SQL or joins

For example, an entity with multiple default-EAGER `@ManyToOne` associations, especially multi-level self-referential relationships. The provider may expand join graphs or emit secondary selects differently from older versions.

**How to handle:** review mappings, set `LAZY` on to-one associations where business logic permits and the provider supports it, then specify the fetch plan per use case via `@EntityGraph`/`join fetch`. Do not switch every association to LAZY while leaving service callers accessing them outside transactions.

### 8.2. N+1 appears in mappers/serializers

Repository tests calling only `findAll()` observe one SQL statement, yet building DTOs/JSON calls `book.getAuthor().getName()`, triggering secondary SELECTs.

**How to handle:** measure the entire read path, not just up to the repository return. When a use case needs the author, fetch it in the query or use a projection selecting only required fields. Test with OSIV disabled to expose untracked access outside transactions.

### 8.3. `@EntityGraph` does not guarantee identical SQL to `join fetch`

`@EntityGraph` specifies an attribute load graph; the provider may choose different SQL strategies than explicit JPQL join fetch. `FETCH graph` and `LOAD graph` also have different semantics for attributes omitted from the graph. Per JPA, a fetch graph marks listed attributes as eager while others may be treated as lazy under graph semantics (the provider is still allowed to fetch more); a load graph preserves mapping fetch policies for unlisted attributes.

**How to handle:** measure each repository method, verify eager/lazy initialization, and inspect actual SQL. Do not draw conclusions from the annotation name alone.

### 8.4. Collection fetch join results have different root counts

In Hibernate 6, duplicate root entities from collection join fetches are handled differently from some earlier versions, and legacy `DISTINCT`/hint usage changed as well. However, this does not eliminate multiplied **SQL rows** and does not replace checking pages/counts.

**How to handle:** assert the set of root IDs, child count per root, ordering, pagination, and total counts. Avoid inferring from `List.size()` when joining multiple to-many associations. If a query has a custom `select` projection or scalar result, verify `DISTINCT` semantics separately.

### 8.5. Pagination with collection fetch joins runs in RAM

When a `Pageable` query fetches a collection, the provider may not push SQL limits down as desired. The query still returns the expected single page in Java, yet JDBC loads too many rows or Hibernate throws an error if configured to fail fast.

**How to handle:** enable `hibernate.query.fail_on_pagination_over_collection_fetch=true` in tests; switch to a two-step strategy of paging root IDs first then fetching children by ID. Verify the count query is properly generated or explicitly declared.

### 8.6. SQL changes are due to dialect/driver or query planner

After upgrading, `limit/offset` may become `offset ... fetch first ... rows only`, aliases may change, or the DB may pick a different plan due to statistics/indexes, not necessarily due to fetch annotations.

**How to handle:** check the dialect/driver and DB version; inspect actual SQL, bind values, and execution plans. H2 tests do not substitute for PostgreSQL, MySQL, SQL Server, or Oracle testing when the application targets those engines.

### 8.7. L1/L2 or query cache masks comparison issues

A second run inside the same transaction emits no SQL because L1 already holds the entities. Or L2 cache returns cached state, skewing cold-start comparisons.

**How to handle:** isolate transactions and call `EntityManager.clear()` or open a fresh context for each scenario; if using L2/query cache, measure cache-on and cache-off separately and evict caches with provider APIs when truly needed. `EntityManager.clear()` **does not clear L2 or Spring Cache**.

### 8.8. LAZY relationships throw `LazyInitializationException`

If a serializer accesses an association when no persistence context remains, the application fails; with OSIV enabled, the problem may be hidden behind extra queries outside the service transaction. Changing OSIV/transaction boundaries during the same upgrade alters symptoms.

**How to handle:** determine required output data and load/map DTOs inside an explicit service transaction. Do not turn EAGER on everywhere or extend sessions indefinitely just to make serialization succeed.

## 9. Regression diagnosis workflow

Follow this order to avoid fixing the wrong cause:

1. **Confirm reproducibility:** run the same fixture/call path on baseline and target; check source versions, settings, and DB.
2. **Verify semantics:** are root counts/IDs, associations, filters, pages, ordering, and null handling still accurate? Fix correctness before optimizing.
3. **Count SQL across the full use case:** repository → service → DTO/serializer; separate cold/warm caches.
4. **Classify the diff:** extra secondary selects (N+1), added/changed joins, excessive JDBC rows, in-memory pagination, L2/cache, or dialect/plan.
5. **Locate the fetch plan source:** mappings, JPQL, derived queries, `@EntityGraph`, Hibernate fetch annotations, configuration, and transaction boundaries.
6. **Make the smallest fix at the right layer:** adjust the use case's fetch plan, projection, batch loading, two-step pagination, indexes, or dialect/config as appropriate.
7. **Re-run two-sided verification:** business results are correct and SQL/latency budgets are respected. With production-like data, verify plans/throughput.
8. **Archive an annotated diff:** if the SQL change is valid, document why; if it was a regression, add a test to catch it in future upgrades.

Decision examples:

| Post-upgrade observation | High likelihood | Investigation path |
| --- | --- | --- |
| Query count grows with root count | N+1 association access | DTO mapper, serialization, fetch graph, batch fetching |
| Query count drops yet p95 increases | Join/row multiplication, poor plan | `EXPLAIN ANALYZE`, row count, select list |
| Missing roots without children | `INNER JOIN` instead of `LEFT JOIN` or filter | SQL join predicate, `optional`, filters |
| Small page yet SQL reads many rows | Collection fetch + pagination | Warning `HHH000104`/version-dependent, fail-fast property |
| Entity graph returns right data with different SQL | Provider chose a different fetch strategy | Graph semantics and actual Hibernate SQL |
| Only fails after controller returns | LAZY load outside context | OSIV/transactions and DTO mapping |
| Only fast on the second benchmark run | Warm L1/L2/query cache | Reset/isolate caches, separate warm/cold |

## 10. Pre-acceptance upgrade checklist

- [ ] Recorded resolved versions, mappings/dialect/database/schema, and configuration parameters.
- [ ] Have representative fixtures: nulls, multi-valued associations, filters, pagination, large datasets.
- [ ] Tested actual read paths end-to-end to DTO/API, not only repository queries.
- [ ] Compared SQL counts, bind values, join shapes, select lists, and row cardinalities.
- [ ] Checked `@OneToMany`, `@ManyToOne`, `@OneToOne`, `@ManyToMany`, and graph loading.
- [ ] Ensured no failing lazy access after transactions close.
- [ ] Checked `DISTINCT`, duplicate roots, count queries, and pagination with collection fetching.
- [ ] Separated cold/warm caches and scoped statistics properly.
- [ ] Used a real database engine/dialect to evaluate SQL plans and latency.
- [ ] Documented valid SQL changes and evidenced regressions, and added tests to CI.

**Remember:** when upgrading JPA/Hibernate, "unchanged code" does not mean "unchanged SQL and fetch plans." Use **the same fixture + the same transaction/use case + SQL/logs/statistics + result and performance assertions** to evaluate, rather than relying solely on HTTP 200 or visual SQL appearance.

### Official version-specific references

- [Hibernate ORM 6.0 Migration Guide](https://docs.hibernate.org/orm/6.0/migration-guide/migration-guide/) — changes in generated SQL, fetching, DISTINCT, queries, and Jakarta API.
- [Hibernate ORM User Guide — Fetching](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#fetching) — fetch plans, `join fetch`, batch/subselect, and SQL behavior. Use the docs matching your deployed Hibernate version.
- [Spring Data JPA — JPA Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html) — `@Query`, `@EntityGraph`, pagination, and projections.
- [Spring Data JPA — EntityGraph API](https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/EntityGraph.html) — ad hoc graphs and `FETCH`/`LOAD`.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — mappings, entity graphs, and fetch semantics.
