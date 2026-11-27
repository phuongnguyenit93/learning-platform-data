# Property Paths and Implicit Joins

## Objectives

JPQL queries entities and Java attributes. When an attribute represents a relationship to another entity, navigating further through the property path can cause the JPA provider to generate a `JOIN` in SQL. This is an **implicit join**. Understanding this rule helps predict which records get filtered out, why a query unexpectedly behaves like an inner join, and when to write an explicit `JOIN` or `LEFT JOIN`.

For example, `b.publisher.name` navigates from entity `Book` through the `publisher` relationship and reads the `name` attribute. Because `publisher` is an association to another entity, JPQL must join the corresponding table. Path navigation across a single-valued association has inner join semantics. If `publisher` can be null, books without a publisher will not appear in the results.

This lesson explains path expression syntax, implicit joins, explicit joins, collection joins, `ON` and `WHERE`, fetch joins, query costs, and a runnable Spring Data JPA example.

## 1. JPQL Works with Entities and Java Attributes

JPQL is the query language of Jakarta Persistence. Statements use entity names, associations, and persistent attributes declared in Java:

```java
@Entity
@Table(name = "books")
public class Book {
    @Id
    private Long id;

    private String title;

    @ManyToOne
    @JoinColumn(name = "publisher_id")
    private Publisher publisher;
}
```

JPQL references `Book`, `title`, and `publisher`, not directly the table name `books`, column `title`, or column `publisher_id`.

```jpql
select b
from Book b
where b.publisher.name = :publisherName
```

Here `Book` is the entity name, `b` is the identification variable, `b.title` is a state-field path, `b.publisher` is an association path, and `b.publisher.name` continues navigation through the association.

Entity and attribute names must match the Java mapping and are case-sensitive according to JPQL rules. If the database column is named `publisher_name` while the Java property is `name`, JPQL still writes `p.name`.

## 2. What is a Path Expression?

A path expression is a path starting from an identification variable or a valid path value, navigating through attributes of an entity or embeddable.

| JPQL path | Meaning |
| --- | --- |
| `b.title` | Basic attribute `title` of Book. |
| `b.publisher` | Association from Book to Publisher. |
| `b.publisher.name` | Attribute `name` of the Publisher linked to Book. |
| `b.publisher.country` | Attribute `country` of Publisher. |
| `b.publisher.address.city` | Navigates through Publisher and then to attribute `city` in embeddable Address. |

Navigating across a **single-valued association** such as `@ManyToOne` or `@OneToOne` can trigger an implicit join. Navigating into attributes of an embeddable stays within the same mapped object; the embeddable itself is not a separate entity/table and does not create an extra join.

For instance, if `Publisher.address` is `@Embedded Address`, the path `b.publisher.address.city` needs to join from Book to Publisher, while `address.city` maps to a column on the Publisher table.

### Collection-Valued Paths

You cannot navigate directly through a collection as if it were a single entity:

```jpql
select b
from Book b
where b.reviews.comment = :comment
```

`reviews` is a collection-valued association. To access individual reviews, declare a range variable using `JOIN`:

```jpql
select distinct b
from Book b
join b.reviews r
where r.comment = :comment
```

`r` represents each `Review` in the `b.reviews` collection, allowing access to `r.comment`.

## 3. Implicit Joins Generated When Traversing Associations

Suppose entity `Book` has a `ManyToOne` relationship to `Publisher`. The query:

```jpql
select b
from Book b
where b.publisher.country = :country
```

navigates from `b` through association `publisher` and reads `country`. The provider must join Book with Publisher. The conceptual SQL could look like:

```sql
select b.id, b.title, b.publisher_id
from books b
inner join publishers p on p.id = b.publisher_id
where p.country = ?
```

JPQL does not contain the `JOIN` keyword, yet the association path generates the necessary join. For path navigation across single-valued associations, an implicit join has inner join semantics.

### Consequences When the Association Can Be Null

If `Book.publisher` is nullable, the query `b.publisher.country = :country` will not return books that have no publisher. There is no publisher to satisfy the path predicate, so those rows are excluded just as with an inner join.

| Book | Publisher | `b.publisher.country = 'VN'` |
| --- | --- | --- |
| Spring JPA | Northwind Press, VN | Can match |
| Hibernate Deep Dive | Old House, US | Does not match |
| Independent JPQL | No publisher | Excluded by implicit inner join |

### Navigating Across Multiple Associations

For example, `b.publisher.organization.country` traverses two associations if both `publisher` and `organization` are entity relationships. The provider must join the corresponding tables to evaluate the path. At each association step, consider nullability and join semantics.

Do not assume path navigation is cheap simply because the JPQL query is short. A long path can produce multiple joins and affect the execution plan.

## 4. When Should You Write an Explicit JOIN?

Write an explicit join when you need an alias for the related entity, need to join a collection, want to choose `INNER JOIN` vs. `LEFT JOIN` explicitly, want to add an `ON` condition, or want to load an association using `JOIN FETCH`.

```jpql
select b
from Book b
join b.publisher p
where p.country = :country
```

This query explicitly expresses an inner join from Book to Publisher. It has equivalent basic filtering semantics to path navigation `b.publisher.country`, while the alias `p` makes the query easier to extend.

### INNER JOIN

`JOIN` defaults to an inner join. Only Books with a matching Publisher are kept.

```jpql
select b
from Book b
join b.publisher p
where p.name like :pattern
```

### LEFT JOIN

`LEFT JOIN` preserves the left-side entity even when no related entity exists. Attributes on the right-side alias will be null when no matching record exists.

```jpql
select b
from Book b
left join b.publisher p
order by b.title
```

This query can return books without a publisher. If you add `where p.name = :name`, rows without a publisher will be excluded by the WHERE condition, making the effective result behave like an inner join for that condition.

## 5. ON and WHERE in LEFT JOIN

`ON` adds a condition directly to the join step. `WHERE` filters results after the join has been executed. This distinction is especially critical with `LEFT JOIN`.

### Condition in ON

```jpql
select b
from Book b
left join b.publisher p on p.active = true
```

Books are still retained even if the publisher is inactive or nonexistent; when there is no matching active publisher, the `p` side is null.

### Condition in WHERE

```jpql
select b
from Book b
left join b.publisher p
where p.active = true
```

The WHERE condition filters out rows where `p` is null. Consequently, Books without a publisher or with an inactive publisher are excluded.

| Book | Publisher active? | LEFT JOIN ... ON active=true | LEFT JOIN ... WHERE active=true |
| --- | --- | --- | --- |
| Spring JPA | Yes | Keeps Book and Publisher | Keeps Book |
| Hibernate Deep Dive | No | Keeps Book, Publisher side null | Excluded |
| Independent JPQL | No Publisher | Keeps Book, Publisher side null | Excluded |

JPQL has supported `ON` conditions for explicit association joins since Jakarta Persistence 2.1. When moving predicates between ON and WHERE, re-verify the intended semantics because the number of returned rows can change.

## 6. Collection JOIN and DISTINCT

When joining a collection, a single root entity can appear multiple times in the relational result set because each collection element produces a joined row.

```jpql
select b
from Book b
join b.reviews r
where r.rating >= :minimumRating
```

If a book has three qualifying reviews, the join produces three rows for that same book. If the goal is a unique list of Books, use `DISTINCT`:

```jpql
select distinct b
from Book b
join b.reviews r
where r.rating >= :minimumRating
order by b.title
```

`DISTINCT` requests unique entity results per the query's semantics. The provider/database may perform deduplication in SQL or at the ORM layer depending on the mapping and query. Verify generated SQL and actual row counts when a query joins multiple collections.

If you only want to check whether an entity has at least one collection element satisfying a condition, you can use an `EXISTS` subquery to avoid multiplying root rows:

```jpql
select b
from Book b
where exists (
    select r.id
    from Review r
    where r.book = b
      and r.rating >= :minimumRating
)
```

## 7. JOIN FETCH and Implicit Joins Are Not the Same

An implicit join handles path navigation and filtering/selecting data. It does not guarantee that the association will be initialized on the returned entity.

`JOIN FETCH` instructs the provider to load the association in the same query:

```jpql
select b
from Book b
left join fetch b.publisher
order by b.title
```

For a lazy `ManyToOne` association, fetch join helps avoid issuing an additional SELECT per book when code reads `book.getPublisher().getName()`.

### When to Use Fetch Join?

- When you know the screen or business logic needs the association and want to load it in a single query.
- When avoiding N+1 queries for accessed relationships.
- When ensuring the association is loaded before the transaction ends.

### Be Careful with Collection Fetch Joins

Fetch-joining a collection can duplicate root rows in SQL. `select distinct b` is often needed to ensure unique entity results.

Avoid combining database pagination casually with collection fetch joins. Because a root entity can span multiple joined rows, the provider may paginate in memory or emit warnings and incur heavy overhead. For pagination, consider querying a page of IDs first and fetching associations in a second query, using a suitable `@EntityGraph`, or using projections.

Fetch-joining multiple collections simultaneously can also produce a Cartesian product, causing row counts to grow rapidly. Fetch only the associations actually needed.

## 8. Path Expressions, NULL, and Collection Operators

Path navigation across an association can drop root entities when the association is null. If you need to keep root entities, use `LEFT JOIN` and check the alias:

```jpql
select b
from Book b
left join b.publisher p
where p is null or p.country = :country
```

JPQL provides expressions for collections:

```jpql
select b from Book b where b.reviews is empty
```

`IS EMPTY` checks whether a collection has no elements. You can use `SIZE(b.reviews)` when you need the element count, or `:review member of b.reviews` when checking whether an entity is in the collection.

```jpql
select b from Book b where size(b.reviews) >= :minimumReviews
```

`SIZE` typically requires the database to count elements via a subquery or equivalent expression. If you only need to check whether a collection has an element matching a predicate, `EXISTS` can express the intent more clearly.

## 9. JPQL Paths and Spring Data Derived Property Paths

Both mechanisms often use the same attribute names, but they are parsed in different places:

| Mechanism | Example | How It Works |
| --- | --- | --- |
| JPQL in `@Query` | `where b.publisher.country = :country` | JPA provider interprets the path and generates necessary SQL joins. |
| Derived query method | `findByPublisherCountry(String country)` | Spring Data parses the method name into a query following property paths. |
| Runtime Sort | `Sort.by("publisher.name")` | Spring Data validates the property path and applies ordering; the path may trigger a join. |

In derived queries, `_` can be used to disambiguate property boundaries when attribute names are ambiguous, such as `findByPublisher_Name`. That is a Spring Data method-name parsing rule, not JPQL syntax.

When using `@Query`, write valid JPQL syntax and use explicit aliases/paths. Do not put SQL column names in JPQL unless the query is declared as native SQL.

## 10. Performance and How to Inspect SQL

Path navigation may look concise, but it does not eliminate JOIN costs. To evaluate a query:

1. Enable `logging.level.org.hibernate.SQL=DEBUG` in development to observe generated SQL.
2. Use `EXPLAIN` or the database's execution plan to inspect join order, indexes, estimated rows, and scans.
3. Verify indexes on foreign keys and filtered/sorted columns of related tables.
4. Test with data distributions close to production, especially when associations are nullable or collections have many elements.
5. Count queries executed when accessing lazy associations to catch N+1 issues.
6. Compare implicit paths, explicit joins, fetch joins, and `EXISTS` for the exact business result required.

For instance, `b.publisher.country = :country` typically benefits from an index on `books.publisher_id` and potentially an index on `publishers.country`, depending on the execution plan. Proper indexes do not guarantee fast queries if predicates have low selectivity or datasets are large.

## 11. Runnable Example with Java 17+, Spring Boot, and H2

The example creates three books: one with a Vietnamese publisher, one with an inactive US publisher, and one with no publisher. The queries demonstrate implicit joins, left joins, collection joins, ON conditions, and fetch joins.

### Project Structure

```text
jpql-paths/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/jpql/
        │   ├── JpqlPathsApplication.java
        │   ├── Publisher.java
        │   ├── Book.java
        │   ├── Review.java
        │   ├── BookPublisherInfo.java
        │   ├── PublisherRepository.java
        │   ├── BookRepository.java
        │   └── DemoService.java
        └── resources/
            └── application.properties
```

### `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>jpql-paths</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:jpqlpaths;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

### `Publisher.java`

```java
package com.example.jpql;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "publishers")
public class Publisher {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false, length = 2)
    private String country;

    @Column(nullable = false)
    private boolean active;

    protected Publisher() {
    }

    public Publisher(String name, String country, boolean active) {
        this.name = name;
        this.country = country;
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getCountry() {
        return country;
    }

    public boolean isActive() {
        return active;
    }
}
```

### `Book.java`

```java
package com.example.jpql;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "books")
public class Book {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "publisher_id")
    private Publisher publisher;

    @OneToMany(mappedBy = "book", cascade = CascadeType.ALL, orphanRemoval = true)
    private List<Review> reviews = new ArrayList<>();

    protected Book() {
    }

    public Book(String title, Publisher publisher) {
        this.title = title;
        this.publisher = publisher;
    }

    public void addReview(Review review) {
        reviews.add(review);
        review.setBook(this);
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public Publisher getPublisher() {
        return publisher;
    }
}
```

### `Review.java`

```java
package com.example.jpql;

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
@Table(name = "book_reviews")
public class Review {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "review_text", nullable = false)
    private String comment;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "book_id", nullable = false)
    private Book book;

    protected Review() {
    }

    public Review(String comment) {
        this.comment = comment;
    }

    void setBook(Book book) {
        this.book = book;
    }
}
```

### `BookPublisherInfo.java`

```java
package com.example.jpql;

public class BookPublisherInfo {
    private final String title;
    private final String publisherName;

    public BookPublisherInfo(String title, String publisherName) {
        this.title = title;
        this.publisherName = publisherName;
    }

    public String getTitle() {
        return title;
    }

    public String getPublisherName() {
        return publisherName;
    }
}
```

### `PublisherRepository.java`

```java
package com.example.jpql;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PublisherRepository extends JpaRepository<Publisher, Long> {
}
```

### `BookRepository.java`

```java
package com.example.jpql;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface BookRepository extends JpaRepository<Book, Long> {
    @Query("select b from Book b "
         + "where b.publisher.country = :country order by b.title")
    List<Book> findByPublisherCountry(@Param("country") String country);

    @Query("select b from Book b "
         + "left join b.publisher p "
         + "where p.name = :name or p is null order by b.title")
    List<Book> findByPublisherNameOrNoPublisher(@Param("name") String name);

    @Query("select distinct b from Book b "
         + "join b.reviews r "
         + "where lower(r.comment) like lower(concat('%', :keyword, '%')) "
         + "order by b.title")
    List<Book> findBooksWithReviewContaining(@Param("keyword") String keyword);

    @Query("select new com.example.jpql.BookPublisherInfo(b.title, p.name) "
         + "from Book b left join b.publisher p on p.active = true "
         + "order by b.title")
    List<BookPublisherInfo> findPublisherInfoWithActivePublisher();

    @Query("select b from Book b left join fetch b.publisher order by b.title")
    List<Book> findAllWithPublisher();
}
```

In `findByPublisherCountry`, `b.publisher.country` is an implicit join. In `findByPublisherNameOrNoPublisher`, the join is written explicitly to preserve books without a publisher. The collection join query uses `distinct` to avoid returning duplicate Books. The DTO query places `p.active = true` in `ON`, so it still returns every book, with the publisher name set to null if the publisher is inactive or missing.

### `DemoService.java`

```java
package com.example.jpql;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DemoService {
    private final PublisherRepository publisherRepository;
    private final BookRepository bookRepository;

    @PersistenceContext
    private EntityManager entityManager;

    public DemoService(PublisherRepository publisherRepository,
                       BookRepository bookRepository) {
        this.publisherRepository = publisherRepository;
        this.bookRepository = bookRepository;
    }

    @Transactional
    public void runDemo() {
        Publisher northwind = publisherRepository.save(
                new Publisher("Northwind Press", "VN", true));
        Publisher oldHouse = publisherRepository.save(
                new Publisher("Old House", "US", false));

        Book spring = new Book("Spring JPA", northwind);
        spring.addReview(new Review("JPQL implicit joins explained"));

        Book hibernate = new Book("Hibernate Deep Dive", oldHouse);
        hibernate.addReview(new Review("Query tuning and indexes"));

        Book independent = new Book("Independent JPQL", null);

        bookRepository.saveAll(List.of(spring, hibernate, independent));
        entityManager.flush();
        entityManager.clear();

        System.out.println("Implicit join, country VN: "
                + titles(bookRepository.findByPublisherCountry("VN")));
        System.out.println("Left join, publisher or none: "
                + titles(bookRepository.findByPublisherNameOrNoPublisher("Northwind Press")));
        System.out.println("Collection join, review contains join: "
                + titles(bookRepository.findBooksWithReviewContaining("join")));

        System.out.println("LEFT JOIN ON active publisher:");
        for (BookPublisherInfo row : bookRepository.findPublisherInfoWithActivePublisher()) {
            String publisher = row.getPublisherName() == null
                    ? "(none)" : row.getPublisherName();
            System.out.println("  " + row.getTitle() + " -> " + publisher);
        }

        System.out.println("Fetch join:");
        for (Book book : bookRepository.findAllWithPublisher()) {
            String publisher = book.getPublisher() == null
                    ? "(none)" : book.getPublisher().getName();
            System.out.println("  " + book.getTitle() + " -> " + publisher);
        }
    }

    private static String titles(List<Book> books) {
        return books.stream()
                .map(Book::getTitle)
                .reduce((left, right) -> left + ", " + right)
                .orElse("");
    }
}
```

`flush()` synchronizes the persisted records to the database; `clear()` detaches current entities so subsequent queries read fresh from the database. Consequently, the fetch join section demonstrates loading the publisher alongside the Book rather than reusing objects already cached in the persistence context.

### `JpqlPathsApplication.java`

```java
package com.example.jpql;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class JpqlPathsApplication {
    public static void main(String[] args) {
        SpringApplication.run(JpqlPathsApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(DemoService service) {
        return args -> service.runDemo();
    }
}
```

### Running the Application

```bash
mvn spring-boot:run
```

Output printed by the application:

```text
Implicit join, country VN: Spring JPA
Left join, publisher or none: Independent JPQL, Spring JPA
Collection join, review contains join: Spring JPA
LEFT JOIN ON active publisher:
  Hibernate Deep Dive -> (none)
  Independent JPQL -> (none)
  Spring JPA -> Northwind Press
Fetch join:
  Hibernate Deep Dive -> Old House
  Independent JPQL -> (none)
  Spring JPA -> Northwind Press
```

The output above reflects the newly inserted data in H2. Specific aliases and SQL may vary by Hibernate version and dialect. The key observation is that the implicit path `b.publisher.country` does not return `Independent JPQL` because its publisher is null; the explicit LEFT JOIN retains that row.

## 12. Common Errors

1. **Assuming path navigation only reads a Java field:** `b.publisher.name` traverses an association and can generate an implicit inner join.
2. **Not understanding why entities with null associations disappear:** implicit joins have inner join semantics; use `LEFT JOIN` if the root entity must be preserved.
3. **Navigating directly through a collection:** use `JOIN b.reviews r` and then access `r.comment`.
4. **Putting a right-side predicate in WHERE after a LEFT JOIN:** null rows are eliminated. Put the predicate in `ON` to preserve the left-side entity.
5. **Forgetting DISTINCT when joining a collection:** a single root can appear multiple times due to multiple related elements.
6. **Confusing implicit joins with fetch joins:** a filtering join does not guarantee the association is initialized on the returned entity.
7. **Collection fetch join with pagination:** can cause duplicates, incorrect pagination, or in-memory paging; use a dedicated pagination strategy.
8. **Using SQL column names in JPQL:** JPQL uses entity names and Java properties; native SQL uses physical schema table/column names.
9. **Overlooking N+1:** querying a list of Books and then accessing a lazy Publisher can trigger extra queries unless fetched as needed.

## 13. Best Practices

- Use path navigation for short queries and single-valued relationships when inner join semantics are intended.
- Write explicit JOINs when you need an alias, collection join, LEFT JOIN, or ON condition.
- Use LEFT JOIN to preserve root entities when an association can be null.
- Place conditions appropriately: ON to restrict paired rows; WHERE to filter final results.
- Use DISTINCT or EXISTS when a collection join can multiply root rows.
- Use JOIN FETCH or `@EntityGraph` when loading associations to prevent N+1.
- Avoid paginating directly over collection fetch joins; inspect SQL and execution plans.
- Use accurate entity/Java property names and test against the target database.

Key takeaway: **Navigating across a single-valued association in JPQL can produce an implicit inner join; collections require an explicit join to bind an alias per element. Use LEFT JOIN when preserving entities without relationships, place predicates in ON or WHERE according to desired semantics, and use fetch join separately when the goal is loading associations.**