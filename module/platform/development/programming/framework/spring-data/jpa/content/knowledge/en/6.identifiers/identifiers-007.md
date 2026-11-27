# Composite Keys with @EmbeddedId and @IdClass

## 1. Objectives

In JPA, an Entity usually has a single property as its primary key. However, some tables only uniquely identify a record when multiple columns are combined. A primary key consisting of two or more properties is called a composite primary key.

Examples:
- A physical copy of a book is identified by its ISBN and copy number.
- A course enrollment is identified by student ID and course code.
- An order line item is identified by order ID and line number.

JPA supports two common ways to map composite keys:
- `@EmbeddedId`: groups key components into an `@Embeddable` class, then embeds that class into the Entity.
- `@IdClass`: declares each key component directly on the Entity using multiple `@Id` fields, while specifying a separate key class with `@IdClass`.

After this lesson, you will be able to design both composite key styles, understand key class requirements, use them with Spring Data `JpaRepository`, write queries targeting individual key components, and avoid common pitfalls.

## 2. When Do You Need a Composite Key?

Suppose the `book_copies` table stores copies of books. The ISBN identifies a book title, but one title can have multiple copies. Therefore, ISBN alone is not unique. Copy number also only has meaning within the scope of a single ISBN.

The appropriate primary key is the pair `(isbn, copy_number)`.

```sql
CREATE TABLE book_copies (
    isbn VARCHAR(17) NOT NULL,
    copy_number INTEGER NOT NULL,
    title VARCHAR(200) NOT NULL,
    available BOOLEAN NOT NULL,
    PRIMARY KEY (isbn, copy_number)
);
```

Some illustrative rows:

| isbn | copy_number | title | available |
| --- | ---: | --- | --- |
| 9780134685991 | 1 | Effective Java | true |
| 9780134685991 | 2 | Effective Java | false |
| 9781492078005 | 1 | Learning SQL | true |

The first two copies share the same ISBN but differ in `copy_number`, so they remain two distinct records. When querying or updating a copy, the application must provide both key components.

Only use a composite key when those components truly define the record's identity in the data model. If the table has a simple surrogate key and the business columns are protected by a unique constraint, a single key may be easier to work with. Base your decision on the domain model, foreign keys, and how data is identified across the system.

## 3. General Requirements for Composite Key Classes

Whether using `@EmbeddedId` or `@IdClass`, the key class must meet these basic requirements:

1. Be a serializable class (`Serializable`).
2. Have a no-arg constructor with `public` or `protected` visibility.
3. Implement `equals()` and `hashCode()` based on the key components.
4. Key values must match the database primary key and must not change after the Entity is persisted.
5. Key components must be fully assigned before persisting. Composite keys are typically supplied by the application; do not assume JPA will auto-generate individual key parts like `@GeneratedValue` on a single key.

`equals()` and `hashCode()` are critical because the key class serves as the identity value in the persistence context, caches, and Java data structures. Two key objects containing the same components must be considered equal.

For example, two `BookCopyId("9780134685991", 1)` instances must be equal and share the same hash code. If equality only compares object references, looking up an Entity with a newly instantiated key object will not behave as expected in Java contexts.

For keys containing strings, standardize data normalization rules. For instance, ISBNs should be stored in a canonical format. If the database uses a case-insensitive collation while Java's `equals()` is case-sensitive, comparison rules on the two sides may mismatch.

## 4. Approach 1: Using @EmbeddedId

`@EmbeddedId` groups all key components into a value object. The key class is annotated with `@Embeddable`; the Entity holds a single property annotated with `@EmbeddedId`.

### 4.1. Creating the BookCopyId Class

`src/main/java/com/example/library/book/BookCopyId.java`:

```java
package com.example.library.book;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.io.Serial;
import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class BookCopyId implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    @Column(name = "isbn", nullable = false, length = 17)
    private String isbn;

    @Column(name = "copy_number", nullable = false)
    private Integer copyNumber;

    protected BookCopyId() {
        // JPA requires a no-arg constructor.
    }

    public BookCopyId(String isbn, Integer copyNumber) {
        if (isbn == null || isbn.isBlank()) {
            throw new IllegalArgumentException("ISBN is required");
        }
        if (copyNumber == null || copyNumber <= 0) {
            throw new IllegalArgumentException("Copy number must be positive");
        }
        this.isbn = isbn.trim();
        this.copyNumber = copyNumber;
    }

    public String getIsbn() {
        return isbn;
    }

    public Integer getCopyNumber() {
        return copyNumber;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof BookCopyId that)) {
            return false;
        }
        return Objects.equals(isbn, that.isbn)
                && Objects.equals(copyNumber, that.copyNumber);
    }

    @Override
    public int hashCode() {
        return Objects.hash(isbn, copyNumber);
    }
}
```

Explanation:
- `@Embeddable` allows the class to be embedded into an Entity so its properties become columns in that Entity's table.
- `@Column` defines the column names and constraints for each key component.
- The no-arg constructor is `protected` so JPA can instantiate it.
- The public constructor helps the application create valid keys and validates input data.
- `equals()` compares both ISBN and copy number; `hashCode()` uses the exact same two components.
- `@Serial` and `serialVersionUID` declare Java serialization versioning; they do not replace the `Serializable` requirement on the key class.

### 4.2. Using the Key in the Entity

`src/main/java/com/example/library/book/BookCopy.java`:

```java
package com.example.library.book;

import jakarta.persistence.Column;
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "book_copies")
public class BookCopy {
    @EmbeddedId
    private BookCopyId id;

    @Column(nullable = false, length = 200)
    private String title;

    @Column(nullable = false)
    private boolean available;

    protected BookCopy() {
        // JPA requires a no-arg constructor.
    }

    public BookCopy(BookCopyId id, String title, boolean available) {
        if (id == null) {
            throw new IllegalArgumentException("Book copy ID is required");
        }
        if (title == null || title.isBlank() || title.length() > 200) {
            throw new IllegalArgumentException("Title must contain 1 to 200 characters");
        }
        this.id = id;
        this.title = title.trim();
        this.available = available;
    }

    public BookCopyId getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public boolean isAvailable() {
        return available;
    }
}
```

Because `@EmbeddedId` is placed on the field, this Entity uses field access. JPA maps the fields inside `BookCopyId` to the `isbn` and `copy_number` columns, alongside the Entity's `title` and `available` columns.

Structurally, key parts are accessed via `bookCopy.getId().getIsbn()` and `bookCopy.getId().getCopyNumber()`. This contrasts clearly with `@IdClass`, where key properties reside directly on the Entity.

### 4.3. Declaring the Repository

`src/main/java/com/example/library/book/BookCopyRepository.java`:

```java
package com.example.library.book;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookCopyRepository extends JpaRepository<BookCopy, BookCopyId> {
    List<BookCopy> findById_IsbnOrderById_CopyNumberAsc(String isbn);
}
```

The ID type parameter of `JpaRepository` is `BookCopyId`, not `Long`, because the Entity's primary key is a two-component object.

The method `findById_IsbnOrderById_CopyNumberAsc` is a derived query traversing the property path `id.isbn` and ordering by `id.copyNumber`. The underscore (`_`) explicitly marks property path boundaries so Spring Data parses the method name unambiguously.

### 4.4. Using the Repository

```java
BookCopyId id = new BookCopyId("9780134685991", 2);

BookCopy copy = new BookCopy(id, "Effective Java", true);
bookCopyRepository.save(copy);

BookCopy found = bookCopyRepository.findById(id)
        .orElseThrow(() -> new IllegalArgumentException("Book copy not found"));

List<BookCopy> allCopies = bookCopyRepository
        .findById_IsbnOrderById_CopyNumberAsc("9780134685991");
```

This snippet assumes `bookCopyRepository` has been injected into a Spring bean. On save, Hibernate creates a row with a primary key containing both `isbn` and `copy_number`. When finding by ID, pass a `BookCopyId` containing both components.

## 5. Approach 2: Using @IdClass

With `@IdClass`, key properties are declared directly on the Entity and each property is marked with `@Id`. A separate key class merely mirrors the exact same names and data types of those properties.

For example, a student can only have one enrollment record per course. The composite key is `(student_id, course_code)`.

### 5.1. Creating the StudentCourseId Class

`src/main/java/com/example/library/course/StudentCourseId.java`:

```java
package com.example.library.course;

import java.io.Serial;
import java.io.Serializable;
import java.util.Objects;

public class StudentCourseId implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private Long studentId;
    private String courseCode;

    public StudentCourseId() {
        // JPA requires a no-arg constructor.
    }

    public StudentCourseId(Long studentId, String courseCode) {
        this.studentId = Objects.requireNonNull(studentId, "studentId is required");
        this.courseCode = Objects.requireNonNull(courseCode, "courseCode is required");
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof StudentCourseId that)) {
            return false;
        }
        return Objects.equals(studentId, that.studentId)
                && Objects.equals(courseCode, that.courseCode);
    }

    @Override
    public int hashCode() {
        return Objects.hash(studentId, courseCode);
    }
}
```

### 5.2. Declaring the Entity with Multiple @Id Fields

`src/main/java/com/example/library/course/StudentCourse.java`:

```java
package com.example.library.course;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;

@Entity
@Table(name = "student_courses")
@IdClass(StudentCourseId.class)
public class StudentCourse {
    @Id
    @Column(name = "student_id", nullable = false)
    private Long studentId;

    @Id
    @Column(name = "course_code", nullable = false, length = 30)
    private String courseCode;

    @Column(nullable = false, length = 20)
    private String status;

    protected StudentCourse() {
        // JPA requires a no-arg constructor.
    }

    public StudentCourse(Long studentId, String courseCode, String status) {
        if (studentId == null || studentId <= 0) {
            throw new IllegalArgumentException("Student ID must be positive");
        }
        if (courseCode == null || courseCode.isBlank() || courseCode.length() > 30) {
            throw new IllegalArgumentException("Course code is required");
        }
        if (status == null || status.isBlank() || status.length() > 20) {
            throw new IllegalArgumentException("Status is required");
        }
        this.studentId = studentId;
        this.courseCode = courseCode.trim();
        this.status = status.trim();
    }

    public Long getStudentId() {
        return studentId;
    }

    public String getCourseCode() {
        return courseCode;
    }

    public String getStatus() {
        return status;
    }
}
```

Crucial rule for `@IdClass`: the name and type of every property in `StudentCourseId` must match the corresponding ID property on the Entity. For instance, if the Entity has `studentId` of type `Long` and `courseCode` of type `String`, the ID class must declare those exact same two property names and types.

`@IdClass(StudentCourseId.class)` links the Entity to its key class. Do not place `@EmbeddedId` on the same Entity at the same time. The two strategies are mutually exclusive mapping alternatives.

### 5.3. Repository and Usage

`src/main/java/com/example/library/course/StudentCourseRepository.java`:

```java
package com.example.library.course;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface StudentCourseRepository
        extends JpaRepository<StudentCourse, StudentCourseId> {
    List<StudentCourse> findByStudentId(Long studentId);
}
```

With `@IdClass`, key components are direct properties on the Entity, so derived queries can reference `studentId` or `courseCode` directly.

```java
StudentCourse registration = new StudentCourse(101L, "JAVA-101", "ACTIVE");
studentCourseRepository.save(registration);

StudentCourseId id = new StudentCourseId(101L, "JAVA-101");
StudentCourse found = studentCourseRepository.findById(id)
        .orElseThrow(() -> new IllegalArgumentException("Registration not found"));

List<StudentCourse> registrations = studentCourseRepository.findByStudentId(101L);
```

The generic ID parameter on `JpaRepository` is still `StudentCourseId`, even though the Entity has two fields annotated with `@Id`.

## 6. Comparing @EmbeddedId and @IdClass

| Criterion | `@EmbeddedId` | `@IdClass` |
| --- | --- | --- |
| Location of key properties | Grouped inside an object embedded into the Entity. | Placed directly on the Entity, each field marked `@Id`. |
| Key class | Annotated with `@Embeddable`. | Separate POJO class linked via `@IdClass`. |
| Key access | `entity.getId().getPart()` or `entity.id.part`. | `entity.getPart()` or `entity.part`. |
| Component derived queries | Traverse path, e.g., `findById_Isbn`. | Use property name directly, e.g., `findByStudentId`. |
| Grouping | Key components are grouped into a clear value object. | Key components are exposed directly on the Entity. |
| Repository ID type | `@Embeddable` class. | `@IdClass` class. |

### Which Should You Choose?

Prefer `@EmbeddedId` when you want to model the key as a standalone, reusable value object and encapsulate key-related behavior in one class. This often keeps the Entity cleaner when keys have multiple components.

Choose `@IdClass` when your existing model needs key properties directly on the Entity, or when you want to query by ID fields without traversing a nested `id` property.

Both approaches are valid. There is no rule that one is inherently faster than the other; query performance depends on SQL, indexes, the database engine, and how the application accesses data.

## 7. JPQL Queries with Composite Keys

JPQL operates on Entities and Java properties, not directly on SQL table/column names. With `@EmbeddedId`, you must traverse the ID property to access a component.

Example:

```java
@Query("select b from BookCopy b where b.id.isbn = :isbn")
List<BookCopy> findAllCopies(@Param("isbn") String isbn);
```

With `@IdClass`, key components live directly on the Entity:

```java
@Query("select sc from StudentCourse sc where sc.studentId = :studentId")
List<StudentCourse> findRegistrations(@Param("studentId") Long studentId);
```

When using derived queries, Spring Data parses the corresponding property paths as well. With embedded keys, an underscore in the method name clarifies the boundary between `id` and the sub-property.

## 8. Using Composite Keys with Entity Relationships

A common scenario is a composite key containing a parent Entity's foreign key. With `@EmbeddedId`, JPA provides `@MapsId` to map a relationship into part of an embedded key.

For example, an order line has key `(order_id, line_number)`. The `OrderLine` Entity can hold `@EmbeddedId OrderLineId` along with a `@ManyToOne` relationship to `PurchaseOrder`, annotated with `@MapsId("orderId")`. The `orderId` field inside the embedded key is populated from `PurchaseOrder`'s primary key.

```java
@Entity
public class OrderLine {
    @EmbeddedId
    private OrderLineId id;

    @MapsId("orderId")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id")
    private PurchaseOrder order;

    // Other order line properties.
}
```

This illustrative snippet assumes `OrderLineId` has an `orderId` property matching the name and type of `PurchaseOrder`'s primary key. In a real project, both Entities, the ID class, and all columns must be fully declared. `@MapsId` avoids having to maintain two separate values independently for the same key part.

For complex relationships, design carefully to avoid serialization loops, lazy loading outside transactions, and key mutations after persisting an Entity. Primary keys should remain immutable throughout the Entity's lifecycle.

## 9. Testing Repositories with H2

The example below verifies both mapping styles in a JPA test slice. `BookCopy`, `BookCopyId`, `StudentCourse`, `StudentCourseId`, and both repositories must reside in packages scanned by Spring Boot.

`src/test/java/com/example/library/CompositeIdRepositoryTest.java`:

```java
package com.example.library;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import com.example.library.book.BookCopy;
import com.example.library.book.BookCopyId;
import com.example.library.book.BookCopyRepository;
import com.example.library.course.StudentCourse;
import com.example.library.course.StudentCourseId;
import com.example.library.course.StudentCourseRepository;

@DataJpaTest
class CompositeIdRepositoryTest {
    @Autowired
    private BookCopyRepository bookCopyRepository;

    @Autowired
    private StudentCourseRepository studentCourseRepository;

    @Test
    void savesAndFindsEntityUsingEmbeddedId() {
        BookCopyId id = new BookCopyId("9780134685991", 1);
        bookCopyRepository.save(new BookCopy(id, "Effective Java", true));
        bookCopyRepository.flush();

        BookCopy found = bookCopyRepository.findById(
                new BookCopyId("9780134685991", 1)).orElseThrow();

        assertThat(found.getTitle()).isEqualTo("Effective Java");
        assertThat(found.getId()).isEqualTo(id);
    }

    @Test
    void queriesEmbeddedIdParts() {
        bookCopyRepository.saveAll(List.of(
                new BookCopy(new BookCopyId("9780134685991", 2), "Effective Java", false),
                new BookCopy(new BookCopyId("9780134685991", 1), "Effective Java", true),
                new BookCopy(new BookCopyId("9781492078005", 1), "Learning SQL", true)));
        bookCopyRepository.flush();

        List<BookCopy> copies = bookCopyRepository
                .findById_IsbnOrderById_CopyNumberAsc("9780134685991");

        assertThat(copies)
                .extracting(copy -> copy.getId().getCopyNumber())
                .containsExactly(1, 2);
    }

    @Test
    void savesAndFindsEntityUsingIdClass() {
        studentCourseRepository.save(
                new StudentCourse(101L, "JAVA-101", "ACTIVE"));
        studentCourseRepository.flush();

        StudentCourse found = studentCourseRepository.findById(
                new StudentCourseId(101L, "JAVA-101")).orElseThrow();

        assertThat(found.getStatus()).isEqualTo("ACTIVE");
        assertThat(studentCourseRepository.findByStudentId(101L)).hasSize(1);
    }
}
```

Run the tests from the directory containing `pom.xml`:

```bash
mvn test
```

The expected result is Maven finishing with `BUILD SUCCESS` and all three tests passing. The first test confirms lookup using a new ID instance with the same values; the second verifies derived queries on `@EmbeddedId` components; the third confirms `@IdClass` works with `findById` and ID-property queries.

To test mappings in a complete application, you need the `spring-boot-starter-data-jpa` dependency, a database driver (H2 in this example), and a `@SpringBootApplication` class in the root package.

## 10. Common Errors

| Symptom | Cause | Solution |
| --- | --- | --- |
| Mapping error at startup | Key class lacks a no-arg constructor or `Serializable`. | Check constructors and add `implements Serializable`. |
| Entity not found by ID | Key class implements `equals()`/`hashCode()` improperly or a key component mismatches. | Compare all components and match exact data types with the Entity. |
| `@IdClass` mapping mismatch | Field names or types in the ID class differ from the Entity's `@Id` properties. | Ensure every component's name and type match identically. |
| Repository uses wrong ID type | Declared `JpaRepository<Entity, Long>` even though Entity has a composite key. | Use the composite ID class as the second generic argument. |
| Derived query cannot resolve property | Wrong path for embedded key or misspelled property name. | Use `findById_Isbn` for `@EmbeddedId`; use `findByStudentId` directly for `@IdClass`. |
| Duplicate primary key error | Two Entities share all key components. | Validate data and key creation rules before persisting. |
| Key component is null | Application constructed an incomplete ID. | Validate all components before calling `save`. |
| Updating primary key after saving fails | Entity's identifying key was mutated during persistence lifecycle. | Treat keys as immutable; if business identity changes, reconsider the data model. |
| Using `@GeneratedValue` for part of a composite key | Partial key generation is not uniformly supported across providers and strategies. | Assign the full composite key in the application or redesign with a surrogate key. |

## 11. Design Principles

1. Only use a composite key when multiple attributes genuinely define a record together.
2. Keep the key class small, immutable once used, and equipped with `equals()`/`hashCode()` covering all components.
3. Choose `@EmbeddedId` to group the key into a value object; choose `@IdClass` to expose key components directly on the Entity.
4. Declare the Repository's generic ID type with the exact composite key class.
5. Use Java property names in derived queries, JPQL, and `Sort`; do not confuse them with SQL column names.
6. With `@EmbeddedId` and a parent Entity relationship, consider `@MapsId` to map part of the key from the relationship.
7. Do not mutate keys after an Entity is persisted; if identity must change, re-evaluate the data model.
8. Weigh composite key scalability when designing foreign keys in other tables: every referencing table must store all key components.

## 12. Completion Checklist

- [ ] Can explain why a table needs a composite key.
- [ ] Can create an `@Embeddable` class with `Serializable`, a no-arg constructor, `equals()`, and `hashCode()`.
- [ ] Can map an Entity with `@EmbeddedId` and use the ID class as the Repository generic.
- [ ] Can create an ID class whose field names/types match the Entity's `@Id` properties.
- [ ] Can map an Entity with `@IdClass` and query by individual key components.
- [ ] Can distinguish key property access and derived queries between the two strategies.
- [ ] Know when to use `@MapsId` and why primary keys should be immutable.
- [ ] Can run repository tests for both mapping approaches.

Once completed, you can represent composite keys properly per JPA standards, use them across Entities and Repositories, and choose between `@EmbeddedId` and `@IdClass` to fit your domain model.
