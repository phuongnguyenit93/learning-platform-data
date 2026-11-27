# Defining Columns and Primary Keys with @Column and @Id in Spring Data JDBC

## 1. Purpose of Mapping Columns and Primary Keys

In a relational database, a table has **columns** that store a record's attributes and usually a **primary key** that uniquely identifies each row. In Java, we work with classes, objects, and fields such as `id`, `title`, and `unitPrice`. **Spring Data JDBC** bridges these two models through *relational object mapping*.

The two foundational annotations are:

- **`@Column`:** specifies the SQL column name corresponding to a Java property, especially when the two sides use different names.
- **`@Id`:** specifies which property serves as the entity's *identifier*, allowing Spring Data JDBC to tell new objects from existing ones and perform appropriate save/load operations.

Example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("books")
public class Book {

    @Id
    private Long id;

    private String title;

    @Column("unit_price")
    private BigDecimal price;
}
~~~

Here:

| Java Element | Role | Database Element |
|---|---|---|
| `@Table("books")` | Specifies the mapped table | `books` table |
| `@Id private Long id` | Marks the entity identifier | Primary key column `id` |
| `private String title` | Mapped via naming convention | `title` column |
| `@Column("unit_price") private BigDecimal price` | Explicit column-name mapping | `unit_price` column |

**Important distinction:** these annotations provide **mapping metadata for Spring Data JDBC**. They do not execute `CREATE TABLE` statements or turn Java properties into actual SQL constraints. Primary keys in the database must still be defined via DDL or migrations.

## 2. Which Packages Do These Two Annotations Belong To?

Spring Data JDBC uses annotations from the **Spring Data** ecosystem, not Jakarta Persistence/JPA annotations:

~~~java
// Spring Data Commons:
import org.springframework.data.annotation.Id;

// Spring Data Relational:
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;
~~~

Do not confuse them with:

~~~java
// JPA annotations, not used in place of Spring Data JDBC mapping:
import jakarta.persistence.Id;
import jakarta.persistence.Column;
import jakarta.persistence.Table;
~~~

Even though the names are identical, they serve different mapping layers. Spring Data Relational's `@Column` is usually written as `@Column("column_name")`, whereas JPA typically uses `@Column(name = "column_name")`. Importing the wrong package by mistake can cause repositories to map incorrectly or miss metadata.

Several related annotations commonly used alongside them:

| Annotation | Function |
|---|---|
| `@Table("books")` | Sets the entity's table name |
| `@Column("unit_price")` | Sets the property's column name |
| `@Id` | Marks the identifier |
| `@Transient` | Excludes a property from persistence mapping |
| `@Version` | Manages a version field for optimistic locking |
| `@MappedCollection` | Controls foreign-key/key columns for collections inside an aggregate |
| `@Embedded` | Maps a value object's properties into columns of the enclosing table |

This lesson focuses on **`@Column` and `@Id`**, referencing the remaining annotations to clarify responsibility boundaries when needed.

## 3. @Column: Mapping a Java Property to a SQL Column Name

The purpose of `@Column` is to make explicit **which column a Java property reads from and writes to**. For instance, in Java we may prefer the concise name `price`, while the existing schema uses `unit_price`:

~~~java
@Column("unit_price")
private BigDecimal price;
~~~

When Spring Data JDBC reads the `unit_price` column, it maps the value into the `price` property. When saving the entity, this same metadata determines which column receives the `price` value.

### 3.1. When Do You Need `@Column`?

**Case 1 — Java name and column name differ in terminology**

~~~java
@Column("isbn_code")
private String isbn;

@Column("unit_price")
private BigDecimal price;
~~~

Although the fields are named `isbn` and `price`, Spring Data JDBC uses the columns `isbn_code` and `unit_price`.

**Case 2 — Compatibility with an existing schema**

For example, a legacy system has a column named `legacy_customer_code`. Java can still use a clear property name:

~~~java
@Column("legacy_customer_code")
private String customerCode;
~~~

**Case 3 — Explicit mapping to reduce reliance on conventions**

Where a schema has inconsistent historical naming, `@Column` lets readers see the actual column name directly in code.

### 3.2. When Is `@Column` Optional?

Spring Data JDBC has a **naming convention** (*naming strategy*). In standard setups, camelCase property names are converted to underscore-separated column names, for example:

| Java Property | Expected Column Name Under Common Conventions |
|---|---|
| `title` | `title` |
| `publishedOn` | `published_on` |
| `createdAt` | `created_at` |
| `bookCode` | `book_code` |

So you can write:

~~~java
private LocalDate publishedOn;
~~~

and let the framework map it to `published_on` under the appropriate naming strategy.

**Do not treat the convention table as an absolute guarantee:** naming also depends on version, `NamingStrategy`, dialect, and how the database handles case sensitivity and quoted identifiers. If a schema uses special names, declare `@Column` explicitly and verify the generated SQL against the real database.

### 3.3. Does `@Column` Create Data Types, NOT NULL, or Indexes?

**No.** This is a key difference to grasp when moving from ORM technologies that support schema generation to Spring Data JDBC.

Example:

~~~java
@Column("email_address")
private String email;
~~~

This line does not automatically create:

- The `email_address` column in the database.
- `NOT NULL`, `UNIQUE`, or `CHECK` constraints.
- `VARCHAR(320)` or any specific column length.
- Indexes to speed up queries by email.
- Default values or automatic timestamp updates.

Those decisions belong to **DDL/migrations**:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email_address VARCHAR(320) NOT NULL UNIQUE
);
~~~

Java-layer validation, such as `@NotNull`, helps catch invalid input early when triggered at the right layer, but **never replaces database constraints**.

## 4. @Id: Identifying Entities in Spring Data JDBC

`@Id` marks the property carrying the **entity's identity**:

~~~java
@Id
private Long id;
~~~

For a Spring Data JDBC repository, the identifier is essential in both directions:

1. **Reading entities:** locates and maps the primary key value from the database onto the object.
2. **Saving entities:** helps determine whether an entity is new or existing to choose between insert and update.

For example, `CrudRepository<Book, Long>` declares:

~~~java
public interface BookRepository extends CrudRepository<Book, Long> {
}
~~~

The type parameter `Book` is the managed entity; `Long` is the identifier type matching the `@Id`-annotated property.

When calling:

~~~java
Optional<Book> book = repository.findById(42L);
~~~

the repository uses the identifier to locate the corresponding record. When deleting:

~~~java
repository.deleteById(42L);
~~~

the identifier pinpoints the affected record. Spring Data JDBC can generate dialect-specific SQL from mapping metadata; illustrative SQL snippets should not be assumed to be identical across all versions.

### 4.1. @Id Is Not a Database PRIMARY KEY Definition

Java:

~~~java
@Id
private Long id;
~~~

SQL schema:

~~~sql
id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY
~~~

The two parts do different things:

- `@Id` tells **Spring Data JDBC** that the `id` property is the identifier.
- `PRIMARY KEY` tells the **database** that primary key values must be unique and non-null.
- `GENERATED BY DEFAULT AS IDENTITY` tells the **database** to generate an ID value when an insert does not supply one (exact syntax/behavior depends on the DBMS).

If Java has `@Id` while the table lacks a primary key or contains duplicate values, the database may still allow inconsistent data depending on the schema. Java mapping does not supply missing constraints.

## 5. Complete Example: Book Mapping Columns and Primary Key

Suppose we are building a book catalog application. The database has the schema:

~~~sql
CREATE TABLE books (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    isbn_code VARCHAR(20) NOT NULL UNIQUE,
    unit_price DECIMAL(12, 2) NOT NULL,
    published_on DATE
);
~~~

The names `isbn_code` and `unit_price` differ from the Java property names, so we use `@Column`.

### 5.1. Entity Class

~~~java
package com.example.catalog;

import java.math.BigDecimal;
import java.time.LocalDate;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("books")
public class Book {

    @Id
    private Long id;

    private String title;

    @Column("isbn_code")
    private String isbn;

    @Column("unit_price")
    private BigDecimal price;

    private LocalDate publishedOn;

    public Book() {
    }

    public Book(
            String title,
            String isbn,
            BigDecimal price,
            LocalDate publishedOn
    ) {
        this.title = title;
        this.isbn = isbn;
        this.price = price;
        this.publishedOn = publishedOn;
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getIsbn() {
        return isbn;
    }

    public void setIsbn(String isbn) {
        this.isbn = isbn;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void setPrice(BigDecimal price) {
        this.price = price;
    }

    public LocalDate getPublishedOn() {
        return publishedOn;
    }

    public void setPublishedOn(LocalDate publishedOn) {
        this.publishedOn = publishedOn;
    }
}
~~~

This is a simple mutable entity so you can observe the ID being populated after saving. Spring Data JDBC also supports immutable/constructor-based mapping styles, yet the core principle of `@Id` and `@Column` remains identifying the key and column names.

### 5.2. Repository

~~~java
package com.example.catalog;

import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface BookRepository extends CrudRepository<Book, Long> {

    List<Book> findByIsbn(String isbn);
}
~~~

`findByIsbn` is declared using the **Java property name** `isbn`, not the column name `isbn_code`. When the framework derives a query from the method name within Spring Data JDBC's supported scope, `@Column("isbn_code")` metadata resolves the column in SQL.

### 5.3. Saving a New Object

~~~java
Book newBook = new Book(
        "Spring Data JDBC",
        "978-0000000001",
        new BigDecimal("199000.00"),
        LocalDate.of(2025, 1, 15)
);

Book saved = bookRepository.save(newBook);
Long generatedId = saved.getId();
~~~

In this example `id` starts as `null`, so the entity is considered new and Spring Data JDBC performs an INSERT. The database creates the identity key value; the framework retrieves the generated value when the driver/database supports generated key retrieval.

Conceptually, the SQL is similar to:

~~~sql
INSERT INTO books (title, isbn_code, unit_price, published_on)
VALUES (?, ?, ?, ?);
~~~

Values for `?` are bound via JDBC. The exact SQL and key-retrieval mechanism are determined by Spring Data JDBC, the dialect, and the driver.

After calling `save`, **always use the returned entity**, especially with immutable models or callbacks that may return a new object. In this mutable example, the ID may also be updated on the original instance.

### 5.4. Reading and Updating an Existing Row

~~~java
Book book = bookRepository.findById(generatedId)
        .orElseThrow(() -> new IllegalArgumentException(
                "Book not found: " + generatedId
        ));

book.setPrice(new BigDecimal("179000.00"));

Book updated = bookRepository.save(book);
~~~

`book` already has an identifier, so the repository recognizes it as an existing object under standard new-entity detection and follows the update path. Illustrative SQL:

~~~sql
UPDATE books
SET title = ?, isbn_code = ?, unit_price = ?, published_on = ?
WHERE id = ?;
~~~

Exact SQL generation depends on mapping, lifecycle, and version. `save` does not work like JPA's automatic dirty-field tracking: **mutating properties on an object does not emit an UPDATE until a save operation is performed**.

## 6. How Spring Data JDBC Knows Whether an Entity Is New or Existing

This is a frequent point of confusion when working with `@Id`.

In standard configurations, Spring Data determines whether an entity is new based on metadata and object state:

| Entity State | Common Interpretation |
|---|---|
| `@Id Long id = null`, no other detection strategy | New entity, performs INSERT |
| `@Id Long id = 42L`, no other detection strategy | Entity has an ID, typically follows UPDATE path |
| `@Id long id = 0` with primitive and default strategy | Zero is typically treated as having no ID yet |
| Has a `@Version` property | Version may be checked **before ID** to detect a new entity |
| Entity implements `Persistable` | `isNew()` controls newness |

The table above describes the **common default strategy**, not the only possible rule. Spring Data allows customizing detection and lifecycle; exact behavior depends on the model, version, and callbacks.

### 6.1. Why Prefer `Long` Over `long` for Auto-Generated IDs?

~~~java
@Id
private Long id;
~~~

Using the wrapper `Long` lets you distinguish:

- `null`: no ID generated by the database yet.
- A numeric value: an ID has been assigned.

With primitive `long`, the default value is `0`; although Spring Data has rules treating numeric zero IDs as new in common cases, `Long` is usually clearer for auto-generated keys and avoids confusion with valid domain values.

### 6.2. Pre-Assigning an ID Does Not Mean the Framework Always INSERTs

Suppose the application uses a business-generated string code:

~~~java
@Id
private String code;
~~~

If you create a new entity with `code = "BK-001"` right before calling `save`, the default mechanism may see it as an existing entity because the identifier is no longer `null`. As a result, the UPDATE path is chosen even though the row does not yet exist in the database.

This is not an `@Id` bug; it is a matter of **distinguishing an assigned ID from new-entity state**.

Common solutions:

1. If the database generates the ID, leave it `null` initially and receive the ID after saving.
2. If the application generates the ID, consider assigning it in a `BeforeConvertCallback` at the appropriate lifecycle stage after newness has been determined.
3. For models that need explicit control, consider implementing `Persistable` with `isNew()` matching the lifecycle.
4. If using `@Version`, understand that new-entity detection can rely on version before checking ID.

Do not assume “if `save` sees an ID, the framework tries UPDATE and automatically falls back to INSERT if no row exists”: that behavior is not guaranteed by Spring Data JDBC's model.

## 7. Where Are Primary Keys Created?

There are two common design categories.

### 7.1. Database-Generated Primary Keys

Example DDL:

~~~sql
CREATE TABLE books (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(200) NOT NULL
);
~~~

Java:

~~~java
@Table("books")
public class Book {
    @Id
    private Long id;

    private String title;

    // constructors, getters, setters...
}
~~~

Create a new object with `id == null`, then call `repository.save(book)`. The framework relies on JDBC generated-key support, the dialect, and database capabilities to retrieve the ID upon saving.

Depending on the database, identity syntax may be `GENERATED ... AS IDENTITY`, `AUTO_INCREMENT`, or another mechanism. **`@Id` does not determine the key-generation strategy at the database layer.**

### 7.2. Application-Generated Primary Keys

You can use a business code or an application-generated UUID, provided the new-entity detection strategy aligns properly.

Example illustrating a callback that generates a UUID for `BookDocument` before converting the entity to SQL form:

~~~java
import java.util.UUID;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("book_documents")
public class BookDocument {

    @Id
    private UUID id;

    private String fileName;

    public UUID getId() {
        return id;
    }

    public void setId(UUID id) {
        this.id = id;
    }

    public String getFileName() {
        return fileName;
    }

    public void setFileName(String fileName) {
        this.fileName = fileName;
    }
}
~~~

Registering the callback:

~~~java
import java.util.UUID;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.relational.core.mapping.event.BeforeConvertCallback;

@Configuration
public class DocumentIdConfiguration {

    @Bean
    BeforeConvertCallback<BookDocument> assignDocumentId() {
        return document -> {
            if (document.getId() == null) {
                document.setId(UUID.randomUUID());
            }
            return document;
        };
    }
}
~~~

With this callback, the entity enters `save` with a `null` ID; the ID is assigned during the lifecycle before writing to the database. **The table must have a compatible ID column**, and UUID generation is just one design choice. For immutable entities, the callback may need to return a new instance instead of mutating the existing one.

Never assume “the database auto-generates UUIDs” just because Java declares `@Id UUID id`. Where IDs are generated must be explicit: application code, database defaults, triggers, or another mechanism.

## 8. Adding @Version for Concurrent Update Control

Although `@Version` is not the main topic, it is closely tied to `@Id`'s lifecycle.

Example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("books")
public class VersionedBook {

    @Id
    private Long id;

    @Version
    private Long version;

    private String title;

    // constructors, getters, setters...
}
~~~

The DDL must include a version column:

~~~sql
CREATE TABLE books (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT,
    title VARCHAR(200) NOT NULL
);
~~~

Spring Data JDBC can use the version to detect new entities and enforce **optimistic locking**. During an update, the framework checks the expected version; if another transaction modified the row in between, the update can fail with an optimistic locking exception instead of silently overwriting.

Notes:

- Wrapper type `Long` allows an unsaved version to be `null`.
- The schema needs a version column of a compatible type.
- If manual SQL updates the table without maintaining the version column, repository optimistic-locking assumptions can break.
- New-entity detection when `@Version` is present follows different precedence than checking `@Id` alone.

## 9. Can @Column Be Used to Map a Primary Key?

You can place both `@Id` and `@Column` on the same property when the primary key column name differs from the Java property name:

~~~java
@Table("books")
public class Book {

    @Id
    @Column("book_id")
    private Long id;

    // ...
}
~~~

DDL:

~~~sql
CREATE TABLE books (
    book_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(200) NOT NULL
);
~~~

The two annotations complement each other:

- `@Id`: this property is the **identifier**.
- `@Column("book_id")`: the identifier is stored in **column `book_id`**.

If you put only `@Column("book_id")` without `@Id`, the framework lacks the identifier metadata required by repositories. If you put only `@Id` while the schema actually names the column `book_id`, default conventions may look for `id` and fail.

### Can You Put Multiple @Id Annotations to Create a Composite Key?

Do not assume that placing `@Id` on multiple properties automatically creates a **composite key**. Support and representation for composite identifiers can depend on the Spring Data JDBC version. Verify the mechanism supported by your version and design mappings consistently with composite keys in the schema. For foundational lessons, a single-property identifier is the clearest model.

## 10. How to Tell Which Annotations Affect SQL

Imagine an entity:

~~~java
@Table("customers")
public class Customer {

    @Id
    @Column("customer_id")
    private Long id;

    @Column("display_name")
    private String name;

    private String phoneNumber;

    // constructors / accessors...
}
~~~

Expected DDL:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    display_name VARCHAR(150) NOT NULL,
    phone_number VARCHAR(30)
);
~~~

When a repository saves or queries a `Customer`, metadata about table name, column names, and identifier is used to construct the SQL operations. For example, a lookup by ID is conceptually:

~~~sql
SELECT customer_id, display_name, phone_number
FROM customers
WHERE customer_id = ?;
~~~

However, Spring Data JDBC may vary column order, aliases, identifier quoting, or dialect-specific syntax from the illustration. The goal of `@Column` is to **specify the right column identifier**, not to force the framework to emit the exact string template above.

## 11. Interacting with JdbcTemplate and NamedParameterJdbcTemplate

`@Id` and `@Column` are used by Spring Data JDBC in **repository/aggregate mapping**. When writing SQL directly with `JdbcTemplate`, you remain responsible for reading columns and building objects in a `RowMapper`.

Example:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class BookReportDao {

    private final JdbcTemplate jdbc;

    public BookReportDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<String> findAllIsbns() {
        String sql = "SELECT isbn_code FROM books ORDER BY id";
        return jdbc.query(
                sql,
                (rs, rowNum) -> rs.getString("isbn_code")
        );
    }
}
~~~

Here `JdbcTemplate` runs application-written SQL. A custom `RowMapper` does not automatically inspect `@Column("isbn_code")` on an entity to rewrite column names in the SQL string.

Similarly, when using `NamedParameterJdbcTemplate`:

~~~java
var params = new MapSqlParameterSource("id", bookId);
String sql = """
        SELECT id, title, isbn_code, unit_price, published_on
        FROM books
        WHERE id = :id
        """;
~~~

`:id` is a **SQL parameter name**, not the `@Id` annotation. Parameter names are chosen by the SQL author and bound through the template; `@Id` is entity-identity metadata in Spring Data.

Thus, you can use repositories for aggregate CRUD and JDBC templates for specialized reporting queries, while keeping column names, schemas, and transaction rules consistent.

## 12. Column Naming Conventions, Quoted Identifiers, and Different Databases

Some databases are case-insensitive for unquoted identifiers; others strictly distinguish **quoted** and **unquoted** identifiers. For instance, PostgreSQL folds unquoted identifiers to lowercase, while quoted names preserve exact spelling.

Suppose a PostgreSQL schema declares:

~~~sql
CREATE TABLE "BookInventory" (
    "BookId" BIGINT PRIMARY KEY,
    "DisplayName" VARCHAR(200)
);
~~~

Such a schema differs considerably from unquoted snake_case tables and columns. Simply changing Java property names is sometimes not enough to get the right quoting behavior.

When working with identifiers containing uppercase letters, spaces, or SQL keywords, you should:

1. Verify the exact identifier names in the database, including quoting.
2. Declare matching `@Table` and `@Column` mappings and, if necessary, configure conventions/quoting appropriate for your version and dialect.
3. Verify the actual SQL against the target database.

For new projects, **simple table/column names that do not rely on quoting and follow a consistent convention** are usually easiest to maintain—for example `books`, `isbn_code`, `unit_price`.

## 13. NULL, Default Values, and Data Types

`@Column` specifies the column name, while reading/writing data must still be compatible with the column's data type.

| Java Type | Common SQL Type | Notes |
|---|---|---|
| `Long` | `BIGINT` | Suitable for identity IDs; allows `null` in Java before insert |
| `String` | `VARCHAR` / `TEXT` | Length, charset, and constraints are defined by the schema |
| `BigDecimal` | `DECIMAL` / `NUMERIC` | Recommended for money or data needing exact decimal precision |
| `LocalDate` | `DATE` | Contains neither time nor timezone |
| `LocalDateTime` | `TIMESTAMP` | Does not carry timezone information |
| `Boolean` | `BOOLEAN` or equivalent | Depends on database and converter |

For instance, if `published_on` allows `NULL`, then `LocalDate publishedOn` can be `null`. If the schema specifies `NOT NULL` and the application tries to save `null`, the database rejects it; `@Column` does not supply a default value.

When the database has `DEFAULT CURRENT_TIMESTAMP` or another default, do not assume Spring Data JDBC will **automatically omit the column from INSERT** whenever the Java property is null. Depending on how the framework constructs the INSERT, null may be bound explicitly, preventing the database default from applying. Design lifecycle, mapping, or SQL accordingly when you want the database to populate values.

## 14. @Column and Other Aggregate Mapping Structures

### 14.1. Embedded Value Objects

A value object such as `Address` can be stored in columns of the parent table instead of a separate table. Spring Data JDBC provides `@Embedded` for this pattern, optionally with a prefix to avoid column name collisions. `@Column` still defines a property's column name, though flattening/prefixing of embedded objects follows its own rules.

### 14.2. Collections and Foreign Keys

For example, an `Order` aggregate containing `OrderLine` items. In Spring Data JDBC's one-to-many model, join columns in the child table are managed by aggregate mapping; `@MappedCollection(idColumn = "...", keyColumn = "...")` can be used to customize the foreign-key and collection-key columns.

Do not arbitrarily put `@Column("order_id")` on a collection and expect it to act like `@MappedCollection`. They represent two distinct mapping responsibilities.

### 14.3. Non-Persisted Properties

If a property is only temporary application state, you can use Spring Data's `@Transient` to exclude it from persistence mapping. Omitting `@Column` does not mean a property is ignored automatically: **normal persistent properties are still mapped via the naming strategy**.

## 15. Common Mistakes When Defining @Column and @Id

| Symptom | Typical Cause | Resolution |
|---|---|---|
| Query reports column `price` does not exist | Java property is `price`, actual column is `unit_price` | Add `@Column("unit_price")` |
| Insert/update reports table/column does not exist | DDL not executed, wrong schema, or identifier mismatch | Check migrations, `@Table`, `@Column`, and naming strategy |
| Repository fails to recognize primary key properly | Imported `jakarta.persistence.Id` or missing `@Id` | Use `org.springframework.data.annotation.Id` |
| New object with pre-assigned ID causes `save` to run update | Default detection treats non-null identifier as existing | Design `isNew`, `BeforeConvertCallback`, or version appropriately |
| `save` does not return expected ID | Schema lacks ID generation or driver/dialect cannot fetch generated keys | Check identity/sequence, generated keys, and ID strategy |
| `@Column` is declared but database still lacks constraints | `@Column` does not generate DDL | Define `PRIMARY KEY`, `NOT NULL`, `UNIQUE` in migrations |
| `null` property causes constraint error | SQL column is `NOT NULL` or value was not assigned | Handle inputs, defaults, and constraints explicitly |
| Used `isbn_code` in a derived query method name | Derived queries normally reference **Java property** `isbn` | Write `findByIsbn(...)` |
| Updates overwritten by two concurrent requests | No optimistic locking mechanism configured | Consider `@Version` and transaction/isolation settings |
| Hand-written query ignores mapping annotations | `JdbcTemplate` with a custom `RowMapper` does not apply repository mapping automatically | Read the actual SQL column names in SQL/`ResultSet` |

### Debugging Principle

When errors occur, check step by step: **actual table DDL → column names and SQL types → annotation imports → Java property names → ID state before `save` → executed SQL**. If the problem is new vs. existing object handling, focus on `@Id`, `@Version`, `Persistable.isNew()`, and callbacks; if it is a column-name error, focus on `@Column`, `@Table`, and the naming strategy.

## 16. Practice Exercises

### Exercise 1 — Renaming Properties Without Changing the Schema

Given the table:

~~~sql
CREATE TABLE students (
    student_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL,
    enrollment_date DATE
);
~~~

Create a `Student` class with properties `id`, `name`, and `enrolledOn`. Use `@Table`, `@Id`, and `@Column` to map all three columns accurately. Write a `CrudRepository<Student, Long>` and insert a student.

**Hint:** column `student_id` differs from `id`; `full_name` differs from `name`; `enrollment_date` differs from `enrolledOn`.

### Exercise 2 — Observing Auto-Generated IDs

Use a `BIGINT` identity column. Create an object with `id == null`, call `save`, and print the returned ID. Then fetch the same object by ID, modify one property, and call `save` again. Inspect the database to confirm the first call performed INSERT and the second performed UPDATE.

### Exercise 3 — Spotting Wrong Annotation Imports

Try using `jakarta.persistence.Column` in a Spring Data JDBC entity instead of `org.springframework.data.relational.core.mapping.Column`. Observe the behavior and explain why **the annotation import** matters more than two annotations sharing the same simple name.

### Exercise 4 — Application-Generated IDs

Design an entity with `@Id UUID id`. Try assigning a UUID before calling `save` and observe how Spring Data JDBC distinguishes new objects. Then use a UUID-generating callback or `Persistable` strategy to handle the lifecycle properly.

### Exercise 5 — Verifying Constraint Responsibilities

Add `@Column("email_address")` and try saving two records with the same email. Add `UNIQUE(email_address)` to the schema, run again, and observe the difference. Explain the division of responsibility between mapping metadata and database constraints.

## 17. Key Takeaways

- **`@Column` answers “which SQL column does this Java property map to?”**. It primarily controls column naming; it does not declare SQL types, lengths, indexes, or constraints.
- **`@Id` answers “which property identifies this entity?”**. It plays the central role in ID lookups and in determining whether an entity is new or existing.
- You can place **`@Id` and `@Column` on the same property** when the primary key column name differs from the Java property name.
- Import **Spring Data annotations from the right packages**; do not confuse them with JPA's `jakarta.persistence` annotations.
- **The database enforces `PRIMARY KEY` and ID generation strategies**. For auto-generated keys, `Long id = null` clearly represents an unsaved entity before insert.
- `save` does not automatically guarantee an INSERT when an entity already has an ID; design `isNew`, callbacks, or version strategies when assigning identifiers manually.
- In Spring Data JDBC, entity mappings and database schemas must stay consistent; Java annotations never replace DDL or migrations.
