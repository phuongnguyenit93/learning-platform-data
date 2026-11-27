# Bytecode Enhancement, Lazy Attribute Loading, and Dirty Tracking in Hibernate

## 1. Problem and Objectives

In Spring Data JPA, Hibernate typically acts as the *JPA provider* responsible for translating Java objects to relational data. An entity may contain several small columns used on most screens alongside a few large columns needed only on detail views. At the same time, inside a transaction holding many managed entities, Hibernate must determine which entities changed so it can issue appropriate `UPDATE` statements.

**Hibernate bytecode enhancement** is a mechanism that transforms entity class bytecode to add interception when the application **reads** or **writes** a property. Two major uses of it are:

1. **Lazy attribute loading**: loading expensive attributes only when they are actually accessed, rather than always loading them with the base entity fields.
2. **Inline/enhanced dirty tracking**: recording property assignments directly inside the entity, reducing the need to compare every entity's entire state against a snapshot on flush.

This is a **Hibernate ORM** extension, not a Spring Data JPA annotation or AOP proxy. Exact behavior depends on the Hibernate version and enhancement configuration. Standard JPA APIs such as `EntityManager`, `@Basic`, and `FetchType` continue to be used as normal.

After this lesson, you should be able to distinguish enhancement from traditional proxies/dirty checking, enable and verify enhancement, use `@Basic(fetch = LAZY)` and `@LazyGroup`, understand limitations with mutable data, test generated SQL and attribute loading, and avoid confusing dirty tracking with SQL `UPDATE` statements.

## 2. What Is Bytecode Enhancement?

Bytecode is the intermediate code inside `.class` files executed by the JVM. Hibernate can process compiled entity classes to weave *interception points* on property reads/writes and certain internal ORM contracts. Developers still write normal Java classes, while the class loaded at runtime carries extra capabilities supplied by Hibernate.

Conceptual example:

```java
@Entity
class Article {
    @Id
    Long id;

    String title;

    @Basic(fetch = FetchType.LAZY)
    String fullText;
}
```

The snippet above is **conceptual code, not a standalone file with imports or constructors**. When enhancement supports `fullText`, Hibernate can return an entity with `id` and `title` populated while deferring `fullText`. When the application reads `fullText`, the interceptor can issue an additional query to load the data. Without proper enhancement, `LAZY` on a basic property is merely a hint and Hibernate may fetch the column eagerly upfront.

**Note:** enhancement differs from creating runtime proxy subclasses. Hibernate can already use proxies to defer loading *entire related entities* via `@ManyToOne(fetch = LAZY)`. Bytecode enhancement lets Hibernate intercept *attributes inside the entity itself*, including basic types such as `String` or `byte[]` depending on mapping. For polymorphic associations, proxies may still be necessary; enhancement does not replace all proxies.

### 2.1. Comparing Easily Confused Mechanisms

| Mechanism | Primary Effect | Requires Enhancement? |
| --- | --- | --- |
| JPA persistence context (L1) | Manages entity identity, state, and changes within an `EntityManager` | Not required |
| Snapshot-based dirty checking | Compares current state against a snapshot on flush | Not required |
| Hibernate enhanced dirty tracking | Entity tracks which properties were assigned/modified | Yes |
| Entity proxy | Defers loading the entity at the target side of an association | Not necessarily |
| Lazy basic attribute | Defers loading basic/LOB columns of the entity itself | With Hibernate, requires appropriate enhancement |
| `@EntityGraph` / `JOIN FETCH` | Selects related data to load for a specific query | Not enhancement |
| Spring `@Transactional` | Creates transaction boundaries via Spring advice/proxies | Not enhancement |
| Spring `@Cacheable` | Caches method results | Not enhancement |

Enhancement adds **capabilities** only. It does not turn an `EAGER` property into `LAZY`, does not open transactions, and does not override every fetch decision made by mappings or queries.

### 2.2. Build-time or runtime?

- **Build-time enhancement:** a Hibernate plugin transforms bytecode after compilation, before packaging or running tests. This is the easiest approach to verify and reproduce in CI pipelines.
- **Runtime enhancement:** classes are transformed when loaded by a supporting runtime environment or agent. Availability and setup depend on the runtime, classloader, and Hibernate version; never assume adding a property to `application.yml` replaces a build plugin across all projects.
- **No enhancement:** Hibernate still handles most JPA work via proxies and snapshot-based dirty checking. An application is not wrong simply for lacking enhancement; benefits must be measured against actual workloads.

*Extended bytecode enhancement* features that automatically managed certain interactions with associated objects have been deprecated in recent Hibernate branches. That does not mean all bytecode enhancement is deprecated. Prefer updating both sides of bidirectional associations with explicit Java helper methods and enable only the enhancement features you actually need.

## 3. Lazy Attribute Loading

Suppose a `Document` entity has:

- `id` and `title`: commonly displayed in list views.
- `body`: long content needed only on the detail view.
- `internalNotes`: very long internal notes read only by a dedicated review feature.

If all three groups are always fetched in the same query, list APIs transfer and materialize unused data. With enhancement and `@Basic(fetch = FetchType.LAZY)`, Hibernate can defer loading heavy fields.

### 3.1. Java 17+ mapping: complete class example

The Java files in these examples live in package `demo.enhancement` of **a Spring Boot application configured with Spring Data JPA and Hibernate**. Because they rely on external dependencies, they are not designed to be compiled solely via `javac Document.java`.

**`Document.java`**

```java
package demo.enhancement;

import jakarta.persistence.Basic;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import org.hibernate.annotations.LazyGroup;

@Entity
@Table(name = "documents")
public class Document {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String title;

    @Lob
    @Basic(fetch = FetchType.LAZY)
    @LazyGroup("body")
    private String body;

    @Lob
    @Basic(fetch = FetchType.LAZY)
    @LazyGroup("notes")
    private String internalNotes;

    @Version
    private long version;

    protected Document() {
        // JPA requires a no-arg constructor.
    }

    public Document(String title, String body, String internalNotes) {
        this.title = title;
        this.body = body;
        this.internalNotes = internalNotes;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getBody() {
        return body;
    }

    public String getInternalNotes() {
        return internalNotes;
    }

    public void rename(String newTitle) {
        if (newTitle == null || newTitle.isBlank()) {
            throw new IllegalArgumentException("Title must not be blank");
        }
        this.title = newTitle;
    }

    public void replaceBody(String newBody) {
        this.body = newBody;
    }
}
```

**Explanation of each annotation group:**

- `@Basic(fetch = FetchType.LAZY)` is a JPA request/hint regarding how a **basic attribute** is fetched. With Hibernate, proper enhancement is required to expect deferred loading of basic columns.
- `@Lob` marks large data; it may map to CLOB/text depending on dialect. `@Lob` **does not enable lazy loading on its own**.
- `@LazyGroup("body")` and `@LazyGroup("notes")` are Hibernate-specific annotations: the two fields belong to distinct lazy-loading groups. If both remained in the same default group, accessing one could trigger loading the entire group.
- `@Version` is optimistic locking to detect concurrent updates per JPA. It is **not** a dirty-tracking setting, though it helps protect records during modifications.
- Getters contain no SQL, yet on an enhanced class, **accessing** a lazy field can cause Hibernate to execute SQL to load the corresponding group.
- Avoid unintended field access in getters, `toString()`, `equals()`, serializers, or loggers: invoking those methods can inadvertently access `body`/`internalNotes` and trigger loading.

### 3.2. Illustrative SQL: when does loading happen?

Suppose `id = 7`. Service code inside a transaction:

```java
Document document = entityManager.find(Document.class, 7L);
String title = document.getTitle();
String body = document.getBody();
```

With enhancement active and the mapping above, the SQL flow **may conceptually look like**:

```sql
-- Load columns needed for the eager group:
SELECT id, title, version
FROM documents
WHERE id = 7;

-- On first access to the body group:
SELECT body
FROM documents
WHERE id = 7;
```

This SQL is illustrative, **not a guaranteed output**: provider, dialect, secondary mappings, fetch plans, caching, and version can alter actual columns and queries. The key point is that `find` may omit `body`, while calling `getBody()` may trigger loading the `body` group. Reading `getInternalNotes()` afterward may trigger a separate load for the `notes` group.

**Do not misunderstand:** queries using `JOIN FETCH`, entity graphs, or projections selecting needed columns directly can alter the fetch plan; `@LazyGroup` is also not a cure for N+1 queries. Reading a lazy attribute across 100 entities can issue up to 100 extra fetches without appropriate batching or caching.

### 3.3. Lazy groups and round-trip costs

Hibernate defines *lazy groups*: multiple lazy attributes in the same group can be loaded together when any attribute in that group is accessed.

| Mapping | Reading `body` | Reading `internalNotes` |
| --- | --- | --- |
| Both lazy in the same default group | May load both together | Usually already loaded after the first access |
| Two distinct `@LazyGroup`s | Loads the `body` group | Loads the `notes` group when accessed |
| Both eager or enhancement ineffective | Likely loaded in the initial query | No extra fetch needed, but cost already paid upfront |

Split groups when two fields have independent access frequencies. If both are always used together, too many groups increase round-trips. **Optimize by actual bytes transferred, query count, and response latency**, not by assuming more lazy groups is always faster.

### 3.4. Checking whether an attribute has been loaded

Jakarta Persistence provides a standard API:

```java
jakarta.persistence.PersistenceUnitUtil loadUtil =
        entityManager.getEntityManagerFactory()
                .getPersistenceUnitUtil();

boolean bodyLoaded = loadUtil.isLoaded(document, "body");
```

This snippet runs inside a JPA environment with `entityManager` and `document`, not as a standalone program. With proper mapping and enhancement, right after `find` without reading `body`, `bodyLoaded` is expected to be `false`; after `getBody()`, it becomes `true`.

With Hibernate you can also use `Hibernate.isPropertyInitialized(document, "body")` for diagnostics, though standard `PersistenceUnitUtil` is preferable when only checking loaded state. **The isLoaded result describes the state of that specific object**, not a guarantee that all repository queries or every execution path produce the same SQL count.

### 3.5. Laziness and transaction/session boundaries

Suppose a transaction has closed and the entity becomes detached:

```java
Document doc = documentService.loadDocument(id);  // Transaction ends.
String body = doc.getBody();                        // May fail.
```

If `body` remains uninitialized and Hibernate needs a session to load it, accessing it may throw `LazyInitializationException`. Enhancement **does not** bundle a database connection or transaction inside the object.

A cleaner service design loads required data **while the session is active** and returns an explicit DTO:

```java
package demo.enhancement;

public record DocumentDetail(Long id, String title, String body) {
}
```

```java
package demo.enhancement;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentQueryService {
    private final DocumentRepository repository;

    public DocumentQueryService(DocumentRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public DocumentDetail getDetail(Long id) {
        Document d = repository.findById(id).orElseThrow();
        return new DocumentDetail(d.getId(), d.getTitle(), d.getBody());
    }
}
```

In `getDetail`, `getBody()` is read while the session is open, so `DocumentDetail` holds no lazy fields. This example loads the body because a detail endpoint actually needs it; list endpoints should use projections or queries selecting only display columns instead of calling unnecessary getters.

### 3.6. Lazy basic attributes vs. lazy associations

- `@OneToMany` and `@ManyToMany` are `LAZY` by JPA default; Hibernate typically uses collection wrappers to defer queries.
- `@ManyToOne` and `@OneToOne` are `EAGER` by JPA default unless `fetch = LAZY` is specified. Hibernate may use proxies, enhancement, or other strategies depending on the relationship and target identification.
- `@Basic(fetch = LAZY)` targets **basic properties of the entity itself**, such as `String body`. For Hibernate to honor this reliably, verify that the entity is enhanced.
- Enhancement can enable *no-proxy lazy to-one* associations where applicable; **it does not guarantee every polymorphic or one-to-one relationship avoids proxies**. Do not rewrite all mappings solely because the plugin is enabled.
- If L2 cache or query cache is enabled, it can change observed SQL without changing fetch semantics. When benchmarking, distinguish cache hits from enhancement behavior.

## 4. Enabling Enhancement at Build Time

Exact configuration depends on your build tool and the **Hibernate ORM version actually used by the application**. In Spring Boot, dependency management usually selects the Hibernate version. Never pull an arbitrary plugin version off the internet and force an incompatible Hibernate runtime branch.

### 4.1. Gradle (Groovy DSL) — example for a project using Hibernate ORM 7.2

Example `build.gradle` for a compatible Hibernate 7.2.x project:

```groovy
plugins {
    id 'java'
    id 'org.hibernate.orm' version '7.2.25.Final'
}

hibernate {
    enhancement {}
}
```

The configuration block above is used in Hibernate 7.2 documentation to enable enhancement. **The `{}` after `enhancement` is important**: older examples writing `hibernate { enhancement }` may simply invoke a Groovy getter without actually enabling enhancement. When a project uses Hibernate 6.x or 7.4.x, use the plugin matching that supported runtime line; the snippet above only illustrates Hibernate 7.2 syntax, not an instruction to change Hibernate versions in every Spring Boot application.

Verification command for an already-configured Gradle project:

```bash
./gradlew clean test
```

On Windows, use:

```powershell
.\gradlew.bat clean test
```

The project requires the Java plugin, source sets, and appropriate Hibernate/Spring Data JPA dependencies. If using Maven, Hibernate provides `hibernate-enhance-maven-plugin` for build-time enhancement; match plugin configuration and goals to your exact Hibernate line. Never cite a generic Spring Boot property as proof that bytecode was actually enhanced.

### 4.2. CI and IDE workflow considerations

1. Compile entity classes for Java 17+ and run the enhancement task in the build pipeline.
2. Package and run the **enhanced** artifacts in tests, runtime execution, Docker images, or JARs. Do not let an IDE runner execute unenhanced `.class` files while CI runs enhanced ones.
3. Run tests verifying `@Basic(LAZY)` takes effect. Tests should fail if the plugin is removed, ensuring optimizations are not silently lost during build changes.
4. In multi-module projects, verify that the module **containing the entity classes** is enhanced; enabling the plugin only on a top-level application module does not guarantee classes already packaged in a library module are transformed.
5. In frameworks with their own build-time augmentation, follow framework integration docs and avoid uncontrolled double enhancement.

### 4.3. What signs verify enhancement?

- **JPA behavior:** after `find`, `PersistenceUnitUtil.isLoaded(entity, "body")` is `false`, and calling the getter turns it into `true`. This is the most important check when the goal is lazy attributes.
- **Hibernate internal contracts:** enhanced entities may implement `org.hibernate.engine.spi.PersistentAttributeInterceptable`; entities with inline tracking may implement `org.hibernate.engine.spi.SelfDirtinessTracker`. Use these only for diagnostics or version-pinned integration tests; never couple domain code to these internal interfaces.
- **SQL logs / statement inspector:** the initial query omits lazy columns, and accessing the getter triggers a separate SELECT when needed.
- **Actual artifacts:** inspect bytecode inside packaged classes rather than relying only on source files or IDE settings.
- **Regression testing:** temporarily disabling enhancement in a test branch should cause lazy-attribute tests to catch the regression, given matching data and dialect.

Do not treat successful application startup as proof. Hibernate runs fine without enhancement, so the optimization can silently vanish without throwing any exception.

## 5. Traditional Dirty Checking vs. Enhanced Dirty Tracking

### 5.1. Snapshot-based dirty checking

When a `Document` entity is loaded into the persistence context, Hibernate may retain a snapshot of its initial state. If `title` changes, during `flush` Hibernate compares current values against the snapshot to decide whether an `UPDATE` is needed.

```text
SELECT document -> managed entity + snapshot
                          |
                    rename("New title")
                          |
                   transaction flush
                          |
           compare attributes against snapshot
                          |
             if changed: SQL UPDATE
```

This approach is robust because it can detect many value changes even when the application does not reassign a property's reference, depending on the type's mutability plan. However, with thousands of managed entities or many attributes, snapshot comparison incurs CPU and memory overhead.

### 5.2. Enhanced dirty tracking (inline)

When enhancement enables dirty tracking, bytecode can mark an attribute dirty whenever it is written. On flush, Hibernate can ask the entity "which attributes changed?" instead of comparing every property of every entity.

```text
SELECT document -> enhanced managed entity
                          |
                    rename("New title")
                          |
                 record field "title"
                          |
                   transaction flush
                          |
                  query dirty state
                          |
             if changed: SQL UPDATE
```

**This optimizes change *detection*, not whether SQL `UPDATE` statements run or which columns they include.** Dirty tracking alone does not determine how many columns Hibernate puts into SQL. By default, Hibernate may generate an UPDATE containing many mapped columns; `@DynamicUpdate` is a separate mechanism to generate SQL based only on modified columns (weigh prepared statement caching and consistency). Enhancement also does not replace `@Version` or transactions.

### 5.3. Example updating a managed entity via Spring Data JPA

**`DocumentRepository.java`**

```java
package demo.enhancement;

import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentRepository
        extends JpaRepository<Document, Long> {
}
```

**`DocumentCommandService.java`**

```java
package demo.enhancement;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentCommandService {
    private final DocumentRepository repository;

    public DocumentCommandService(DocumentRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void rename(Long id, String newTitle) {
        Document document = repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Document not found"));
        document.rename(newTitle);
        // Managed entity: Hibernate detects the change automatically at flush/commit.
    }
}
```

For a managed entity inside a transaction, calling `repository.save(document)` after `rename` is not required for dirty checking to run. The foundational conditions remain: **the entity is managed, the transaction permits writes, and the operation actually alters persistent state**. If the entity is detached, modifying the object outside a transaction will not automatically persist to the database.

### 5.4. Why dirty tracking does not imply `@DynamicUpdate`

Suppose a row has columns `title`, `body`, `internal_notes`, `version`. When the application updates only `title`:

- **Dirty detection:** decides whether `title` counts as changed and whether the entity needs updating.
- **SQL update shape:** decides which columns appear in `SET`; by default, the provider may update all mapped updatable columns.
- **Optimistic locking:** `@Version` adds a version check to prevent overwriting concurrent updates according to convention.
- **Flush/transaction:** decides when SQL is sent and when commit takes effect.

When considering updating only changed columns, Hibernate offers `@DynamicUpdate`:

```java
// Hibernate-specific annotation that can be placed on class Document:
// @org.hibernate.annotations.DynamicUpdate
```

The snippet above is **illustrative only**—do not add it blindly without benchmarking. `@DynamicUpdate` can increase the number of distinct SQL statement variants to prepare and interacts with optimistic locking and update mappings. Without `@Version`, selective column updates must also be evaluated carefully for lost updates and record invariants.

### 5.5. Limitations with mutable data

Enhanced tracking relies heavily on intercepting **property reassignments**. An object can mutate **internally** while the field's reference stays unchanged. Example:

```java
byte[] bytes = document.getAttachmentBytes();
bytes[0] = 9;        // Mutates array element without reassigning the field.
```

This snippet illustrates a hypothetical entity with a `getAttachmentBytes()` getter, **not a method on the `Document` class in section 3**. An interceptor observing only field writes may miss the change to `bytes[0]`. Depending on the type, Hibernate may use mutability plans or supplementary snapshots, but never assume all *in-place* mutations are reliably detected by inline tracking.

A safer design:

```java
public void replaceAttachment(byte[] newBytes) {
    this.attachmentBytes = newBytes.clone();
}
```

This is an **illustrative method for an entity with an `attachmentBytes` field**. It replaces the field reference/value with fresh data and avoids retaining an array callers might later mutate. For other mutable types such as `Date`, `Calendar`, `byte[]`, JSON documents, stateful embeddables, or custom user types, inspect mutability plans and test real behavior. Never apply `@Immutable` to data the application mutates internally.

**Design tip:** prefer immutable value objects, replace the whole value via setters/domain methods when updating, and write integration tests verifying database persistence. When mutating nested structures inside embeddables or collections, verify the tracking behavior of those mappings separately.

### 5.6. When dirty checking may not run or write even though an entity changed

- The entity is **detached** outside the persistence context: changes are not automatically synchronized.
- The query, entity, or transaction/session is configured read-only per Hibernate policy: standard property updates should not be expected on flush.
- Calling `@Modifying` with JPQL bulk update/delete: the query hits the database directly and **bypasses per-entity dirty checking and lifecycle callbacks**; managed entities still in the persistence context can become stale.
- Data is modified via JDBC or external systems: Hibernate does not observe entity writes.
- Flush/commit has not occurred yet: changing an in-memory field does not mean SQL has already executed.
- Assigning an equal value or mapping logic treats the field as clean: no UPDATE is needed.
- Transaction rollback: even if SQL ran during flush, changes are not committed.

Do not enable enhancement expecting it to detect external SQL or replace clearing/refreshing the persistence context.

## 6. Integration Test Example Verifying Exact Behavior

The files from sections 3 and 5 can be used in a Spring Boot project with `spring-boot-starter-data-jpa`. To run the test below, add test dependencies (`spring-boot-starter-test`, H2 test runtime), enable build-time enhancement on the entity module, and ensure Spring Boot scans package `demo.enhancement`. **Use a Hibernate plugin version compatible with the Hibernate version managed by Spring Boot**, rather than blindly copying the illustrative 7.2 version from section 4.

**`DocumentEnhancementJpaTest.java`** in `src/test/java/demo/enhancement/`:

```java
package demo.enhancement;

import jakarta.persistence.PersistenceUnitUtil;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class DocumentEnhancementJpaTest {
    @Autowired
    TestEntityManager testEntityManager;

    @Test
    void lazyGroupsLoadIndependently() {
        Document original = new Document(
                "Guide", "Long body content", "Private internal notes");
        testEntityManager.persistAndFlush(original);
        Long id = original.getId();

        testEntityManager.clear(); // Ensure loading from a fresh persistence context.
        Document loaded = testEntityManager.find(Document.class, id);

        PersistenceUnitUtil util = testEntityManager
                .getEntityManager()
                .getEntityManagerFactory()
                .getPersistenceUnitUtil();

        assertThat(util.isLoaded(loaded, "body")).isFalse();
        assertThat(util.isLoaded(loaded, "internalNotes")).isFalse();

        assertThat(loaded.getBody()).isEqualTo("Long body content");
        assertThat(util.isLoaded(loaded, "body")).isTrue();
        assertThat(util.isLoaded(loaded, "internalNotes")).isFalse();

        assertThat(loaded.getInternalNotes()).isEqualTo("Private internal notes");
        assertThat(util.isLoaded(loaded, "internalNotes")).isTrue();
    }

    @Test
    void managedChangeSurvivesFlushAndReload() {
        Document original = new Document(
                "Old title", "Content", "Notes");
        testEntityManager.persistAndFlush(original);
        Long id = original.getId();

        testEntityManager.clear();
        Document loaded = testEntityManager.find(Document.class, id);
        loaded.rename("New title");

        testEntityManager.flush();
        testEntityManager.clear();

        Document reloaded = testEntityManager.find(Document.class, id);
        assertThat(reloaded.getTitle()).isEqualTo("New title");
    }
}
```

Test 1 checks **lazy attributes/`@LazyGroup`** and catches missing enhancement if the provider loads fields eagerly. Test 2 verifies **managed entity changes persist through flush and reload**. However, Test 2 alone *does not prove* enhanced inline tracking: snapshot-based dirty checking produces the same result. To verify the interceptor was actually woven, you can add a separate diagnostic check:

```java
assertThat(loaded)
        .isInstanceOf(org.hibernate.engine.spi.SelfDirtinessTracker.class);
```

This is an optional assertion for configurations enabling **enhanced dirty tracking** (placed after `loaded` is fetched), relying on an internal Hibernate API; if a configuration enables enhancement only for lazy loading without inline tracking, do not apply this assertion. Pin compatibility tests by version and avoid internal types in business code.

Command to run if the project has a Gradle Wrapper:

```bash
./gradlew test --tests "demo.enhancement.DocumentEnhancementJpaTest"
```

On Windows: `.\gradlew.bat test --tests "demo.enhancement.DocumentEnhancementJpaTest"`. Do not assume these files can run standalone without application/database configuration. If the project uses Spring Boot 4, some test auto-configuration packages have changed; adjust test annotations/imports according to your version's documentation.

### 6.1. Interpreting test outcomes

| Observation | Interpretation |
| --- | --- |
| `isLoaded(loaded, "body") == false` before getter | Field is not yet marked loaded on the current entity |
| After calling `getBody()`, state becomes `true` | The body group initialized per mapping |
| `internalNotes` stays false after reading `body` | The two lazy groups load independently as intended |
| After renaming `title`, flush/clear, reload shows new title | Managed entity changes synchronized to the database |
| `body` column appears in the initial SELECT | Enhancement is inactive, mapping/fetch plan requested eager load, or another cause needs investigation |
| Many extra SELECTs appear when calling getters across entities | Attribute-level N+1 risk; consider projections or tuned fetch plans |
| Only update test passes, no loaded-state check | Insufficient proof that enhancement is active |

**For SQL timing**, enable controlled logging in tests or use Hibernate `StatementInspector`/statistics to observe actual queries. The illustrative SQL statements in this lesson are not literal stdout or guaranteed output across all dialects.

## 7. Enabling Enhancement Does Not Eliminate Other Hibernate Issues

### 7.1. N+1 queries can still happen

When an endpoint loads 100 `Document` instances with `body` unloaded and then loops calling `getBody()` on each entity, Hibernate may issue many extra SELECTs. Enhancement avoids fetching when **content is unneeded**, yet if `body` is truly needed for all 100, a projection/DTO query or proper fetch plan is far better.

Choose strategies per use case:

- **Lists:** return `id`, `title`, `updatedAt` via projections or DTOs. Avoid calling body getters in mappers or loggers.
- **Details:** load `body` explicitly inside the transaction and return a populated DTO. Never pass lazy entities outside the transaction for serializers to touch.
- **Bulk reports:** write queries reading required columns in a single pass instead of lazy-loading entity by entity.
- **Writes:** load only state needed to enforce invariants and locking; retain optimistic locking and transactions.

### 7.2. Do not confuse with Open Session in View (OSIV)

When OSIV is enabled, serializers accidentally touching lazy attributes after the controller/service transaction completes can still trigger SQL because the session stays open across the request. This hides unexpected queries and makes query counts hard to control.

Do not rely on OSIV to justify calling lazy getters in the view layer. Define data-access boundaries inside services/queries, assemble DTOs, and measure query counts on real endpoints.

### 7.3. Dirty tracking does not solve concurrency

Two transactions can read the same entity and update it concurrently. Enhanced tracking detects changes **only on the local entity**. It does not prevent lost updates, phantom reads, or cross-system conflicts. Use `@Version`, appropriate transaction isolation, pessimistic locking when genuinely needed, and concurrency tests.

For example, `@Version` on `Document` makes Hibernate check versions during updates according to mapping. If an external system executes direct SQL bypassing the `version` increment convention, that safeguard can fail. Enhancement does not replace that shared write contract.

### 7.4. Do not confuse dirty tracking with auditing/history

Enhanced tracking can tell Hibernate which properties changed within a persistence context, but it does not automatically store **record version history** or logs of who edited what. For auditing, use Envers, domain events/outbox, or a dedicated audit log. Spring Data auditing annotations such as `@LastModifiedDate` are a separate feature from enhancement and still require proper auditing configuration.

### 7.5. Entity serialization and utility methods

A very common mistake:

```java
@Override
public String toString() {
    return "Document{title='" + title
            + "', body='" + body + "'}";
}
```

On an enhanced entity, `toString()` reading `body` can trigger heavy column loads, causing SQL during logging or exceptions when detached. Likewise, `equals()/hashCode()` referencing lazy fields, Lombok `@Data` generating default getters/toString/equals, JSON serializers, or automatic mappers can trigger unintended loads. Exclude heavy lazy fields from such methods and return DTOs that explicitly specify exported data.

## 8. When Should You Use It?

| Situation | Assessment |
| --- | --- |
| Entities contain large LOB/text/blob columns needed by only a few endpoints | Lazy attributes + enhancement can reduce I/O significantly |
| Persistence context holds very many managed entities with frequent flushes | Enhanced dirty tracking can cut snapshot/diff overhead |
| Small entities where nearly all fields are always read | Per-field laziness may increase round-trips without benefit |
| App reads via projections and updates via bulk JPQL | Entity enhancement may have little impact on main query paths |
| Mutable arrays/JSON/custom types are frequently mutated in place | Needs careful testing or immutable/replacement patterns; never trust tracking blindly |
| System requires portability across multiple JPA providers | `@LazyGroup` and plugin mechanisms are Hibernate-specific; prefer JPA queries/projections where suitable |
| Endpoints traverse many cross-entity associations | Evaluate entity graphs, batch fetching, and N+1; enhancement alone is insufficient |

Practical metrics include: p50/p95 response time, bytes/columns returned, SELECT count per request, flush latency, persistence-context heap usage, and post-commit correctness. Always benchmark **enhancement on vs. off under the same workload**; isolated entity microtests easily miss network and query costs.

## 9. Common Failures

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `@Basic(fetch=LAZY)` yet field is already loaded right after find | No enhancement; plugin didn't run; entity module unenhanced; query fetch plan selects the column | Inspect actual artifacts, test `isLoaded` and SQL; configure build for exact Hibernate line |
| Enabled Hibernate property only, yet lazy basic still fails to defer | Runtime property cannot replace class enhancement in the current setup | Use supported build-time enhancement and test it |
| Accessing lazy field outside transaction throws `LazyInitializationException` | Detached entity, closed session | Load needed data into DTOs inside the transaction |
| Reading a list triggers dozens/hundreds of extra SQL queries | Lazy getters accessed inside a loop | Use DTOs/projections/fetch plans for batch reads |
| `@LazyGroup` fails to separate two fields | Same group, enhancement missing, or query eagerly loaded them | Check group names, loaded state, SQL, and mappings |
| Modified element of `byte[]` yet DB does not update | In-place mutation bypassed field-write interception | Assign a new array/value and test flush/clear |
| Modified entity yet no `UPDATE` occurs | Detached, read-only, unflushed, rolled back, or no dirty change | Verify managed state, transaction, flush, and query path |
| Enhanced dirty tracking enabled yet SQL still updates many columns | Dirty detection is separate from SQL update shape | Evaluate `@DynamicUpdate` independently; test concurrency |
| `@Modifying` bulk query skips entity listeners | Bulk updates bypass entity-level lifecycle | Handle clear/refresh, auditing, and cache invalidation explicitly |
| IDE run differs from CI in SELECT counts | IDE uses unenhanced classes while CI runs enhancement task | Align build/run classpaths and packaged artifacts |
| Enabling enhancement causes mappers/loggers to trigger unexpected SQL | Getters/toString/serializers read lazy fields | Avoid serializing entities directly; use DTOs |

## 10. Workflow for Adopting in a Spring Data JPA Module

1. **Confirm the bottleneck to improve:** oversized columns are fetched unnecessarily, or persistence-context dirty checking overhead has been measured as significant.
2. **Check versions:** identify the Hibernate runtime from the dependency graph/BOM and the compatible enhancement plugin; do not upgrade Hibernate independently and break the Spring Boot contract.
3. **Design mappings:** mark candidates `@Basic(fetch=LAZY)`; group independent fields with `@LazyGroup` if needed. Avoid making every small column lazy by habit.
4. **Enable enhancement in the build pipeline**, ensuring every entity module is actually processed before tests and packaging.
5. **Test before and after reading fields:** flush, clear, reload entities; use `PersistenceUnitUtil.isLoaded` and inspect SQL. Test both inside transactions and detached behavior.
6. **Verify dirty tracking:** modify a managed property, flush/clear/reload; if verifying the inline tracker, use a diagnostic assertion compatible with your Hibernate version.
7. **Audit mutable data:** never rely on in-place mutation of `byte[]`/JSON/custom objects untested; prefer replacing with new value objects and proper custom mutability plans when needed.
8. **Review endpoints and transactions:** DTOs/projections, N+1 mitigation, OSIV, serialization, and query limits.
9. **Benchmark realistic workloads** and watch for regressions after build, framework, plugin, or mapping changes.
10. **Keep CI tests** covering lazy semantics and DB updates; never trade data correctness for speculative CPU gains.

### Self-Check Exercises

**Exercise 1.** An entity has `@Lob @Basic(fetch=LAZY) String body`, yet right after `find`, `isLoaded(entity, "body")` returns `true`. Is JPA violating its contract? **Answer:** Not necessarily. `FetchType.LAZY` on basic attributes is a hint; Hibernate requires enhancement and behavior also depends on the fetch plan. Check the plugin, compiled class artifacts, and actual queries.

**Exercise 2.** Two lazy fields exist: `body` and `internalNotes`. How do you avoid loading notes when reading `body`? **Answer:** Assign two different `@LazyGroup` names and verify with `isLoaded`/SQL while enhancement is active.

**Exercise 3.** Enhanced dirty tracking is enabled, and the app mutates `image[0]` on `byte[] image` without reassigning the field. Is the change guaranteed to reach the DB? **Answer:** No. In-place mutation can bypass field-write interception; test it or replace the field with a new value.

**Exercise 4.** Calling `document.rename("A")` inside a `@Transactional` method—must you call `repository.save(document)` for Hibernate to detect the change? **Answer:** No, if the entity is managed. Hibernate performs dirty checking at flush/commit with or without enhancement.

**Exercise 5.** Does enhanced tracking make SQL `UPDATE` statements include only the single changed column? **Answer:** Not by default; it optimizes detecting which properties are dirty. SQL update shape is a separate decision, potentially involving `@DynamicUpdate`.

**Exercise 6.** Does enabling enhancement eliminate `LazyInitializationException` outside transactions? **Answer:** No. When a field is unloaded and the object is detached, Hibernate still needs a session to fetch it. Materialize needed fields before returning DTOs.

## 11. Key Takeaways and Official References

- Bytecode enhancement weaves interception logic into **entity bytecode**, distinct from Spring AOP proxies.
- `@Basic(fetch = LAZY)` on basic fields generally requires enhancement for Hibernate to defer loading. `@LazyGroup` groups attributes fetched together.
- Enhanced dirty tracking records modified fields and can reduce flush overhead, but **does not guarantee** detecting all in-place mutations on mutable values, does not replace transactions/versioning, and does not automatically produce partial SQL updates.
- To prove behavior works, **reload entities after flush/clear**, check `PersistenceUnitUtil.isLoaded`, inspect SQL, and verify running artifacts are actually enhanced.
- Enable optimizations only after understanding read/write goals; when data is needed for a list or query, explicit projections and fetch plans are often simpler to control.

Official documentation to consult for your exact Hibernate version:

- Hibernate ORM 7.2 — User Guide, Bytecode Enhancement section: https://docs.hibernate.org/orm/7.2/userguide/html_single/#BytecodeEnhancement
- Hibernate ORM 7.2 — Introduction, Using the bytecode enhancer (Gradle syntax): https://docs.hibernate.org/orm/7.2/introduction/html_single/#bytecode-enhancement
- Hibernate ORM 7.4 — User Guide (newer stable branch; check for changes): https://docs.hibernate.org/stable/orm/userguide/html_single/
- Hibernate Tooling — Gradle/Maven plugins: https://hibernate.org/orm/tooling/
- Jakarta Persistence — `@Basic`, `FetchType`, `PersistenceUnitUtil`: https://jakarta.ee/specifications/persistence/
- Spring Data JPA — Reference Documentation: https://docs.spring.io/spring-data/jpa/reference/