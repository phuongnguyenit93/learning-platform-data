# Choosing LAZY or EAGER for Singular Relationships

In JPA, a singular relationship (to-one association) is a relationship in which one entity references at most one other entity. The two commonly used annotations are **@ManyToOne** and **@OneToOne**. When loading an entity, JPA must decide when the referenced entity's data will be loaded. That decision is controlled by the fetch type **LAZY** or **EAGER**.

- **LAZY**: defers loading the association until the application needs to access it, if the provider supports that deferred loading mechanism.
- **EAGER**: requires the provider to load the association together with the entity before returning the entity to the application.

For singular relationships, JPA's default is **EAGER** for both **@ManyToOne** and **@OneToOne**. Therefore, if no fetch type is specified, the association may be loaded eagerly even when the current screen or business operation does not need it. Choosing an appropriate fetch type and designing per-query fetch plans helps control SQL query counts, avoid N+1 problems, and prevent loading unnecessary data.

**Prerequisites for the examples:** the code snippets use Spring Boot 3.x, Java 17 or higher, Jakarta Persistence, and Spring Data JPA. The application requires **spring-boot-starter-data-jpa**, a JDBC driver, a DataSource, and the corresponding schema. These are source files inside a Spring Boot application, not standalone programs runnable solely with **javac**.

## 1. What Is a Singular Relationship in JPA?

A singular relationship is an association where one entity holds a reference to at most one other entity:

- **@ManyToOne**: many owning-side entities can reference the same target entity. For example, many books belong to one author.
- **@OneToOne**: one entity links to at most one entity on the other side. For example, an account has one personal profile.

Book and author relationship example:

~~~text
Author
  id
  name
    ^
    | multiple Books can reference
    |
Book
  id
  title
  author_id
~~~

In the database, a **ManyToOne** relationship is typically represented by a foreign key **author_id** in the **books** table. In Java, the **author** property has type **Author**.

## 2. How Do LAZY and EAGER Differ?

| Characteristic | LAZY | EAGER |
|---|---|---|
| Intent | Defer loading the association | Load the association before returning the entity to the application |
| When accessing the association | Provider may execute an additional query | Data is already loaded per the provider's fetch plan |
| SQL | May be triggered on access | May use a JOIN or separate SELECTs |
| Unnecessary data loading | Reduced if the association is unused | May load excess data |
| Common risk | Accessing after the persistence context closes | Loading too much data and triggering N+1 |

Important point: **EAGER is not synonymous with JOIN**. The provider may use a JOIN in the initial SQL query or issue one or more additional SELECT queries to satisfy the EAGER requirement. The execution strategy depends on the provider, mapping, query, and dialect.

Conversely, **LAZY does not guarantee zero extra SQL**. When code accesses the association, the provider may load the data with another query. The goal of LAZY is to defer loading until needed, not to automatically optimize all queries.

### JPA Defaults for Singular Relationships

| Annotation | Default Fetch |
|---|---|
| **@ManyToOne** | **FetchType.EAGER** |
| **@OneToOne** | **FetchType.EAGER** |

For collection relationships, the default for **@OneToMany** and **@ManyToMany** is **LAZY**. This lesson focuses on singular relationships, but keep the difference in mind so you do not assume all associations share the same default.

JPA defines **EAGER** as a requirement that the provider fetch the association per the fetch plan before returning the result to the application. **LAZY** is a hint to the provider. The provider may not support deferring in certain cases and still load eagerly. Therefore, inspect the provider's actual runtime behavior rather than looking only at annotations.

## 3. @ManyToOne Example with LAZY

Suppose each book has one author, and many books can belong to the same author.

`Author` entity:

~~~java
package com.example.catalog.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "authors")
public class Author {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Author() {
    }

    public Author(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

`Book` entity:

~~~java
package com.example.catalog.domain;

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
@Table(name = "books")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String title;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "author_id", nullable = false)
    private Author author;

    protected Book() {
    }

    public Book(String title, Author author) {
        this.title = title;
        this.author = author;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public Author getAuthor() {
        return author;
    }
}
~~~

Key points to understand:

- **@ManyToOne** indicates many books can reference one author.
- **fetch = FetchType.LAZY** requests deferring loading the author until accessed, if supported by the provider.
- **optional = false** expresses a mandatory relationship at the mapping level.
- **@JoinColumn(name = "author_id")** identifies the foreign key column.
- **nullable = false** indicates the foreign key column is non-null during schema generation.

With Hibernate, a **ManyToOne LAZY** relationship is typically implemented via proxies or suitable bytecode enhancement. When loading a `Book`, Hibernate can load only the book's data and hold a deferred reference to `Author`. When code calls **book.getAuthor().getName()**, the association is initialized if it has not been loaded yet.

Example reading a book without needing author details:

~~~java
Book book = bookRepository.findById(id).orElseThrow();
String title = book.getTitle();
// book.getAuthor() is not accessed, so the association may remain unloaded.
~~~

If business logic needs the author's name, choose an appropriate fetch plan for that query rather than assuming every query reading `Book` needs `Author`.

## 4. @OneToOne Example with LAZY

Suppose an account has a personal profile. The foreign key can be placed in the user accounts table:

~~~java
@Entity
@Table(name = "user_accounts")
public class UserAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "profile_id", nullable = false, unique = true)
    private Profile profile;

    protected UserAccount() {
    }

    public Profile getProfile() {
        return profile;
    }
}
~~~

`Profile` entity:

~~~java
@Entity
@Table(name = "profiles")
public class Profile {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String displayName;

    protected Profile() {
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Here **UserAccount** is the owning side because it contains **@JoinColumn**. The **profile_id** column is a foreign key, and **unique = true** prevents a profile from being referenced by multiple accounts if the schema actually has the corresponding unique constraint.

If the model uses a bidirectional relationship, the other side can declare:

~~~java
@OneToOne(mappedBy = "profile", fetch = FetchType.LAZY)
private UserAccount account;
~~~

The side with **mappedBy** is the inverse side and does not own the foreign key. With an inverse one-to-one, the provider needs to determine whether the association exists. In some implementations, this forces the provider to query eagerly or prevents complete deferral without extra information. Hibernate may require bytecode enhancement to support effective lazy loading on certain inverse one-to-one mappings.

Therefore, **fetch = LAZY** on **@OneToOne** should be verified against your specific provider and relationship direction. Inspect the actual SQL to confirm whether the association is genuinely deferred. Do not conclude every one-to-one is lazy merely because the annotation specifies LAZY.

## 5. Should You Choose LAZY or EAGER for Singular Relationships?

A generally useful design guideline is to declare singular relationships as **LAZY** and choose which data to load per query. For example:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "author_id")
private Author author;
~~~

Reasons:

1. A query may only need data from the primary entity.
2. Many screens or use cases only need a subset of associations.
3. Per-query fetch plans let you select the exact associations to load.
4. It avoids an EAGER association pulling unnecessary data everywhere the entity is used.

However, LAZY is not an absolute rule. If an association is always required in nearly all use cases and eager loading is measured to be appropriate, EAGER can be a reasonable choice. Decisions should be based on access patterns and actual SQL.

Do not set all relationships to EAGER just to avoid lazy loading errors. That approach can cause a simple query to load a huge entity graph, increasing SQL statements, memory consumption, and processing time.

## 6. How Can N+1 Queries Happen?

N+1 is a situation where the application runs one query to retrieve a list of primary entities, and then runs an additional query for each entity when accessing an association.

Example:

~~~java
List<Book> books = bookRepository.findAll();

for (Book book : books) {
    System.out.println(book.getAuthor().getName());
}
~~~

If there are N books and their authors have not been loaded yet, the SQL may look like:

~~~sql
SELECT id, title, author_id
FROM books;

SELECT id, name FROM authors WHERE id = ?;
SELECT id, name FROM authors WHERE id = ?;
SELECT id, name FROM authors WHERE id = ?;
-- ... subsequent author loads
~~~

The total query count can be one query for the list of books plus up to N queries loading associations. If many books reference the same author and the persistence context/cache already holds that author, the extra SELECT count may be lower than N. With many distinct authors, however, N+1 is a clear risk.

N+1 does not occur only with LAZY. EAGER can also generate separate SELECTs per association depending on the provider and fetch plan. Therefore, switching LAZY to EAGER is not a reliable fix for N+1.

Identify which queries actually need the association, then design a fetch plan for that specific use case.

## 7. Using JOIN FETCH to Load Associations in One Query

JPQL supports **JOIN FETCH** to retrieve the main entity and required associations in the same query.

Repository:

~~~java
package com.example.catalog.repository;

import com.example.catalog.domain.Book;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Optional;

public interface BookRepository extends JpaRepository<Book, Long> {

    @Query("""
        select b
        from Book b
        join fetch b.author
        where b.id = :id
        """)
    Optional<Book> findByIdWithAuthor(@Param("id") Long id);
}
~~~

Service:

~~~java
@Service
public class BookQueryService {

    private final BookRepository bookRepository;

    public BookQueryService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @Transactional(readOnly = true)
    public BookDetails getDetails(Long id) {
        Book book = bookRepository.findByIdWithAuthor(id)
            .orElseThrow();

        return new BookDetails(
            book.getId(),
            book.getTitle(),
            book.getAuthor().getName()
        );
    }
}
~~~

DTO:

~~~java
public record BookDetails(
    Long id,
    String title,
    String authorName
) {
}
~~~

In this example, **JOIN FETCH** instructs JPA to load `Author` together with `Book`. When the service maps the entity to a DTO, calling **getAuthor().getName()** does not need a separate lazy query for this association.

If the association can be null, use **LEFT JOIN FETCH** to preserve the main entity even when no related entity exists:

~~~java
@Query("""
    select b
    from Book b
    left join fetch b.author
    where b.id = :id
    """)
Optional<Book> findByIdWithOptionalAuthor(@Param("id") Long id);
~~~

Use JOIN FETCH according to query requirements; do not turn every repository query into one that fetches every association.

## 8. Using @EntityGraph to Describe a Fetch Plan

JPA EntityGraph lets you declare associations to load for a query without manually writing JPQL JOIN FETCH.

Example:

~~~java
package com.example.catalog.repository;

import com.example.catalog.domain.Book;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface BookRepository extends JpaRepository<Book, Long> {

    @EntityGraph(attributePaths = "author")
    Optional<Book> findByIsbn(String isbn);
}
~~~

**attributePaths = "author"** instructs this query to load the `Author` association. Spring Data JPA translates the EntityGraph into a fetch plan suitable for the provider.

Multiple paths can be specified:

~~~java
@EntityGraph(attributePaths = {
    "author",
    "publisher"
})
Optional<Book> findDetailedById(Long id);
~~~

This example assumes the `Book` entity has **author** and **publisher** association properties.

Some differences:

- **JOIN FETCH** writes the join explicitly in JPQL, suitable when the query has custom join logic.
- **@EntityGraph** separates the fetch plan from query conditions, keeping derived query method reuse clean.
- Both require inspecting actual SQL; providers may execute fetch plans differently.
- EntityGraph does not mean every relationship on the entity is loaded.

JPA supports two common graph types:

- **FETCH graph**: specified attributes are treated as eager in the query's fetch plan; unspecified attributes follow graph rules.
- **LOAD graph**: specified attributes are treated as eager; other attributes retain their default mapping fetch semantics.

In Spring Data JPA, **@EntityGraph** defaults to `FETCH` if no type is declared. Choose the graph type according to your query goal and verify results on your provider.

## 9. Using DTO Projections When Only Partial Data Is Needed

If a screen only needs book ID, title, and author name, loading the entire entity graph is unnecessary. DTO projections select only the required columns:

~~~java
package com.example.catalog.dto;

public record BookListItem(
    Long id,
    String title,
    String authorName
) {
}
~~~

Repository:

~~~java
@Query("""
    select new com.example.catalog.dto.BookListItem(
        b.id,
        b.title,
        a.name
    )
    from Book b
    join b.author a
    where b.title like concat('%', :keyword, '%')
    """)
List<BookListItem> searchBookItems(@Param("keyword") String keyword);
~~~

The query retrieves only the values needed for the DTO. The result is not a managed `Book` entity, so the persistence context does not track the DTO as an entity.

DTO projections are useful for lists, reports, and API read models. If you need to modify an entity, load the appropriate entity inside a transaction and perform business changes there.

## 10. LazyInitializationException and Transaction Boundaries

With LAZY, an association may still be unloaded when a service returns an entity to a controller. If the persistence context has closed, accessing the association can raise **LazyInitializationException** in Hibernate.

Dangerous example:

~~~java
public Book getBook(Long id) {
    return bookRepository.findById(id).orElseThrow();
}
~~~

After the method returns, the transaction or persistence context may have ended. The controller then calls:

~~~java
book.getAuthor().getName();
~~~

If the association has not been initialized yet, Hibernate no longer has a persistence context to load the data.

The recommended handling is to determine the data to return and load/map it inside the transaction:

~~~java
@Transactional(readOnly = true)
public BookDetails getBookDetails(Long id) {
    Book book = bookRepository.findByIdWithAuthor(id).orElseThrow();

    return new BookDetails(
        book.getId(),
        book.getTitle(),
        book.getAuthor().getName()
    );
}
~~~

Do not switch all associations to EAGER merely to avoid `LazyInitializationException`. Also avoid relying on Open Session in View as a general fetch plan workaround; accessing associations while rendering a response can issue unexpected queries and make performance unpredictable.

A helpful rule: entities are loaded and mapped into DTOs at the service transaction boundary; the controller receives data ready to return.

## 11. Ways to Optimize LAZY Loading for Lists

Besides JOIN FETCH, EntityGraph, and DTO projections, Hibernate provides mechanisms to reduce query counts.

### Batch Fetching

When multiple entities need to initialize the same type of association, Hibernate can group multiple IDs into an IN query rather than running individual SELECTs.

It can be configured at the entity level:

~~~java
@Entity
@BatchSize(size = 32)
public class Author {
    // ...
}
~~~

Or globally:

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        default_batch_fetch_size: 32
~~~

Batch fetching can reduce N+1 to a small number of batched queries. This is a Hibernate feature, not a guarantee across all JPA providers. Batch size should be benchmarked against your database and data volume.

### DTO Projections

If only a few fields are needed, DTO projections are usually cheaper than loading entities and associations only to discard most of the data.

### EntityGraph or JOIN FETCH

If a use case needs the entity along with specific associations, use an explicit fetch plan to load the exact required data.

No single strategy is optimal for every query. Base choices on row counts, number of associations, cardinality, pagination, and actual SQL.

## 12. Cascade, optional, and fetch Are Different Concepts

Three attributes that are often confused:

| Concept | Question |
|---|---|
| Fetch type | When loading an entity, when is the association loaded? |
| Cascade | Do persist/merge/remove operations propagate to the related entity? |
| Optional/nullability | Is the association mandatory or allowed to be null? |

Example:

~~~java
@ManyToOne(
    fetch = FetchType.LAZY,
    optional = false
)
@JoinColumn(name = "author_id", nullable = false)
private Author author;
~~~

Here:

- **LAZY** controls when `Author` is loaded.
- **optional = false** expresses a mandatory relationship at the JPA level.
- **nullable = false** describes a non-nullable foreign key column in the mapping.

If you add **cascade = CascadeType.PERSIST**, persisting `Book` can propagate to `Author` per the cascade rule. That does not make the association EAGER.

Do not indiscriminately add **CascadeType.REMOVE** to a `ManyToOne` relationship. Deleting one `Book` usually does not mean deleting the `Author`, because the `Author` may be referenced by many other `Book` records.

## 13. Inspecting SQL and Measuring Performance

Do not look only at annotations to conclude a query is optimal. Observe the SQL emitted by the provider.

In development, you can enable:

~~~yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
~~~

If you need to view bind parameter values, Hibernate has a dedicated logger for JDBC binds. Only enable it in appropriate test environments because query parameters may contain sensitive data.

When checking a use case, record:

1. Number of SELECT statements before accessing the association.
2. Number of SELECT statements after accessing the association.
3. Which associations are loaded despite the use case not using them.
4. Row counts and returned payload size.
5. Results when running with entity counts close to production data volumes.

Query behavior test example:

~~~java
@DataJpaTest
class BookFetchTest {

    @Autowired
    private BookRepository bookRepository;

    @Test
    void fetchesAuthorForDetailsQuery() {
        Book book = bookRepository.findByIdWithAuthor(1L).orElseThrow();

        assertThat(book.getAuthor().getName()).isNotBlank();
    }
}
~~~

The test above verifies that the query returns the association data. If you need to assert the exact SQL count, use Hibernate Statistics or a datasource proxy in tests. Asserting only the final result does not prove the absence of N+1 queries.

## 14. Common Errors

| Symptom | Cause | Solution |
|---|---|---|
| **LazyInitializationException** | Accessing association after persistence context closes | Load using an appropriate fetch plan and map to DTO inside transaction |
| N+1 queries | Iterating over a list and accessing each LAZY association | Use JOIN FETCH, EntityGraph, projections, or batch fetching |
| Loading too much data | Using EAGER on associations not needed by every use case | Choose LAZY and per-query fetch plans |
| EAGER still emits multiple SELECTs | EAGER is not required to use JOIN | Inspect SQL and design an explicit fetch plan |
| One-to-one LAZY still loads eagerly | Provider needs to determine association existence or lacks inverse lazy support | Check ownership direction, bytecode enhancement, and SQL |
| API emits SQL while serializing entities | Returning entities directly and serializer accesses associations | Return DTOs built within the transaction |
| Replacing LAZY with EAGER slows down the app | Large entity graph and uncontrolled queries | Optimize per use case instead of altering all mappings |
| Fetch plan does not behave as expected | Queries, EntityGraph, and providers have specific semantics | Inspect actual SQL and write integration tests |

## 15. Fetch Type Selection Checklist

- [ ] Determine whether the association is **@ManyToOne** or **@OneToOne**.
- [ ] Remember that the default for both singular relationships is **EAGER**.
- [ ] Consider declaring **LAZY** to defer unneeded data, keeping in mind it is a JPA hint.
- [ ] Verify provider LAZY support, especially for inverse **@OneToOne**.
- [ ] Identify which use cases need the association and choose JOIN FETCH, EntityGraph, or DTO projection.
- [ ] Do not switch all associations to EAGER to handle lazy loading errors.
- [ ] Avoid accessing associations outside the persistence context.
- [ ] Count SQL queries and check for N+1 with sufficiently large datasets.
- [ ] Keep fetch type, cascade, and optionality as separate decisions.
- [ ] Return DTOs from services when building API read responses.

## 16. Conclusion

For singular relationships, JPA defaults to EAGER for **@ManyToOne** and **@OneToOne**, whereas LAZY is a hint asking the provider to defer loading the association. EAGER does not guarantee a JOIN; LAZY also does not guarantee no extra queries. Both must be evaluated against actual SQL.

A design that is usually easier to control is declaring associations LAZY where appropriate, then using JOIN FETCH, **@EntityGraph**, DTO projections, or batch fetching for individual use cases. Loading data at the right time, mapping DTOs within transactions, and checking query counts prevent both `LazyInitializationException` and N+1 queries.