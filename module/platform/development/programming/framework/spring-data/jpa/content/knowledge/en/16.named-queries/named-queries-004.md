# Organizing Queries in META-INF/orm.xml

In JPA, named queries can be declared using annotations on entities or in an XML mapping file. As the number of queries grows, placing every query in entity annotations or scattering them across repositories can make source code harder to read and manage.

The **META-INF/orm.xml** file allows centralizing JPA metadata, including named JPQL queries, named native queries, and result-set mappings. This keeps entity classes focused on the data model while reusable queries are organized in XML.

This lesson covers the structure of `orm.xml`, how to declare and call named queries, how Spring Data JPA resolves named queries by convention, native SQL result mapping, registering additional XML files in Spring Boot, and common pitfalls.

**Prerequisites for the examples:** the code snippets use Spring Boot 3.x, Java 17 or higher, Jakarta Persistence, and Spring Data JPA. The application requires **spring-boot-starter-data-jpa**, a JDBC driver, a DataSource, and a matching schema. These are components of a Spring Boot application, not standalone programs runnable solely with **javac**.

## 1. What is a named query and when should it be used?

A named query is a query predeclared with a unique name in the persistence unit. The application calls the query by that name instead of repeating JPQL or SQL at each call site.

JPA has two common types:

- **Named JPQL query**: queries entities and Java properties.
- **Named native query**: queries database tables and columns directly with SQL.

JPQL example:

~~~sql
select b
from Book b
where b.isbn = :isbn
~~~

Native SQL example:

~~~sql
SELECT b.id, b.title, b.isbn, b.price
FROM books b
WHERE b.isbn = ?
~~~

Both queries can be declared with **@NamedQuery**/**@NamedNativeQuery** annotations, or placed in XML mappings. This lesson focuses on organizing them with `orm.xml`.

Named queries are useful when:

- A query is used in multiple places.
- You want to centralize queries and persistence metadata.
- You want to separate long SQL statements from Java code.
- You need to declare native SQL or result-set mappings.
- You want to manage query definitions alongside the persistence unit's XML mappings.

You do not need to move every query method into `orm.xml`. Simple one-off queries may be better suited to derived queries or **@Query** directly on the repository. Choose the declaration style based on reusability and how your project groups code.

## 2. Location and role of META-INF/orm.xml

By JPA convention, the default mapping file is named:

~~~text
src/main/resources/
└── META-INF/
    └── orm.xml
~~~

After building, the file is typically located at **META-INF/orm.xml** on the application classpath. The persistence provider reads this file as part of the persistence unit metadata.

In standard JPA configuration, **META-INF/orm.xml** is the default mapping file name. If you use other XML files or multiple mapping files, they must be registered with the persistence unit. In Spring Boot, the **spring.jpa.mapping-resources** property allows specifying additional or explicit mapping resources.

Example multi-file structure:

~~~text
src/main/resources/
└── META-INF/
    ├── orm.xml
    └── queries.xml
~~~

Both files use the JPA XML mapping structure with the **entity-mappings** root element. Splitting files can separate entity mappings and query definitions by module, though avoid splitting too finely if it makes searching and verification harder.

### What can orm.xml do?

A mapping file can declare:

- Entity mappings and table names.
- Field/property, column, and relationship mappings.
- Named JPQL queries.
- Named native queries.
- SQL result-set mappings.
- Other persistence metadata defined in the ORM XML schema.

**orm.xml does not replace entity scanning, DataSource setup, or repository scanning.** Entity classes must still belong to the appropriate persistence unit; the database must still be configured; and repository interfaces must still be discovered by Spring Data JPA.

## 3. Basic XML structure of orm.xml

With Jakarta Persistence 3.1, the root element typically looks like:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<entity-mappings
    xmlns="https://jakarta.ee/xml/ns/persistence/orm"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/persistence/orm
        https://jakarta.ee/xml/ns/persistence/orm/orm_3_1.xsd"
    version="3.1">

    <!-- Mappings and named queries go here -->

</entity-mappings>
~~~

Meaning:

- **entity-mappings** is the root element of the ORM mapping file.
- **xmlns** specifies the Jakarta Persistence ORM namespace.
- **xsi:schemaLocation** binds the namespace to the corresponding XML schema.
- **version** indicates the ORM schema version in use.

With Spring Boot 3.x, use the **jakarta** namespace and a schema compatible with the Jakarta Persistence version of your stack. Do not copy legacy Java EE/JPA 2.x namespaces if the application has moved to Jakarta Persistence.

## 4. Declaring named JPQL queries with named-query

Suppose we have a `Book` entity:

~~~java
package com.example.catalog.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "books")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 150)
    private String title;

    @Column(nullable = false, length = 20)
    private String isbn;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    protected Book() {
    }

    public Book(String title, String isbn, BigDecimal price) {
        this.title = title;
        this.isbn = isbn;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getIsbn() {
        return isbn;
    }

    public BigDecimal getPrice() {
        return price;
    }
}
~~~

Declare the query in **META-INF/orm.xml**:

~~~xml
<entity-mappings
    xmlns="https://jakarta.ee/xml/ns/persistence/orm"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/persistence/orm
        https://jakarta.ee/xml/ns/persistence/orm/orm_3_1.xsd"
    version="3.1">

    <named-query name="Book.findByIsbn">
        <query>
            <![CDATA[
                select b
                from Book b
                where b.isbn = :isbn
            ]]>
        </query>
    </named-query>

</entity-mappings>
~~~

Key points to note:

- **name** is the unique name of the named query in the persistence unit.
- JPQL uses the entity name **Book**, not the table name **books**.
- JPQL uses the Java property **isbn**, not the physical column name if they differ.
- **:isbn** is a named parameter.
- CDATA allows special query characters inside XML without manual escaping.

Multiple **named-query** elements can be declared in the same file:

~~~xml
<named-query name="Book.findAllOrderByTitle">
    <query>
        select b from Book b order by b.title
    </query>
</named-query>

<named-query name="Book.findExpensive">
    <query>
        select b from Book b where b.price >= :minimumPrice
    </query>
</named-query>
~~~

Do not declare two named queries with the same name in the same persistence unit. The query name is a runtime identifier; choose a discoverable convention such as **EntityName.methodName**.

## 5. Calling a named JPQL query with EntityManager

You can invoke a query by name using EntityManager:

~~~java
List<Book> books = entityManager
    .createNamedQuery("Book.findByIsbn", Book.class)
    .setParameter("isbn", isbn)
    .getResultList();
~~~

Example in a service:

~~~java
@Service
public class BookQueryService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional(readOnly = true)
    public List<Book> findByIsbn(String isbn) {
        return entityManager
            .createNamedQuery("Book.findByIsbn", Book.class)
            .setParameter("isbn", isbn)
            .getResultList();
    }
}
~~~

**createNamedQuery(name, resultClass)** creates a typed query, enabling compile-time result type checking. If the query does not return `Book` as declared, an error may occur during execution or result conversion.

If at most one row is expected, you can use **getSingleResult()** or an equivalent API. Handle **NoResultException** and **NonUniqueResultException** appropriately. For queries that may return no rows, calling **getResultList()** and checking for an empty list is often easier to control.

## 6. Spring Data JPA named query lookup by naming convention

Spring Data JPA can automatically locate named queries using the convention:

~~~text
<EntitySimpleName>.<repositoryMethodName>
~~~

Example repository:

~~~java
package com.example.catalog.repository;

import com.example.catalog.domain.Book;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface BookRepository extends JpaRepository<Book, Long> {

    List<Book> findByIsbn(String isbn);
}
~~~

Spring Data JPA looks for the named query named:

~~~text
Book.findByIsbn
~~~

If this query is declared in **orm.xml**, the repository method can use it without placing **@Query** on the method.

If no matching named query is found, Spring Data can fall back to deriving the query from the method name, provided the method name is a valid derived query.

### @Query vs. named query: which takes precedence?

When a repository method has **@Query**, the query declared directly in the annotation takes precedence over the convention-based named query. Therefore, if you want the definition in `orm.xml` to be used, do not place another `@Query` on the same method.

You can align method names with domain classes and query names so lookup remains clear. For query methods with complex names or potential convention overlaps, inspect startup logs and integration tests to confirm Spring Data picked the intended query.

## 7. Declaring named native queries in orm.xml

Native queries use SQL directly. In XML, declare them with **named-native-query**:

~~~xml
<named-native-query
    name="Book.findByIsbnNative"
    result-class="com.example.catalog.domain.Book">

    <query>
        <![CDATA[
            SELECT
                b.id,
                b.title,
                b.isbn,
                b.price
            FROM books b
            WHERE b.isbn = ?
        ]]>
    </query>

</named-native-query>
~~~

Here:

- **name** is the name of the named native query.
- **result-class** specifies the entity type used to map each row.
- SQL uses physical table and column names.
- The **?** placeholder is a positional parameter for the native query.

With native SQL, using only positional parameters is portable under Jakarta Persistence. Some providers support named parameters in native queries, but you should not rely on that if you want queries to be portable across providers.

Calling via EntityManager:

~~~java
Book book = entityManager
    .createNamedQuery("Book.findByIsbnNative", Book.class)
    .setParameter(1, isbn)
    .getSingleResult();
~~~

Note: a native query mapping to an entity must supply enough column data to satisfy the entity mapping. If you only fetch a subset of fields, use a DTO or scalar result mapping instead of declaring `result-class` as `Book`.

## 8. Using sql-result-set-mapping when column names differ from entity mapping

When SQL uses custom aliases or joins multiple tables, you can declare **sql-result-set-mapping** and **entity-result**:

~~~xml
<sql-result-set-mapping name="BookEntityMapping">
    <entity-result entity-class="com.example.catalog.domain.Book">
        <field-result name="id" column="book_id"/>
        <field-result name="title" column="book_title"/>
        <field-result name="isbn" column="book_isbn"/>
        <field-result name="price" column="book_price"/>
    </entity-result>
</sql-result-set-mapping>
~~~

Named native query referencing the mapping:

~~~xml
<named-native-query
    name="Book.findByIsbnMapped"
    result-set-mapping="BookEntityMapping">

    <query>
        <![CDATA[
            SELECT
                b.id AS book_id,
                b.title AS book_title,
                b.isbn AS book_isbn,
                b.price AS book_price
            FROM books b
            WHERE b.isbn = ?
        ]]>
    </query>

</named-native-query>
~~~

In **field-result**:

- **name** is the persistent property of the entity.
- **column** is the column name or alias returned by the SQL statement.

If the entity has additional persistent fields such as a version, discriminator, embedded ID, secondary table, or complex associations, the result set mapping must satisfy all requirements of that mapping. The simplified example above assumes the entity only has the listed fields.

## 9. Registering additional XML mappings in Spring Boot

With standard JPA configuration, **META-INF/orm.xml** is the default mapping file. If the application has additional mapping files, such as **META-INF/queries.xml**, they can be declared in Spring Boot:

~~~yaml
spring:
  jpa:
    mapping-resources:
      - META-INF/queries.xml
~~~

The **spring.jpa.mapping-resources** property corresponds to the mapping-file resources of the persistence unit. Each listed file must be on the classpath and have valid ORM XML structure.

If declaring multiple files:

~~~yaml
spring:
  jpa:
    mapping-resources:
      - META-INF/catalog-mappings.xml
      - META-INF/report-queries.xml
~~~

Do not create two files that declare the same named query name. Manage query names uniquely across the entire persistence unit.

In a typical Spring Boot application, you do not need to create **persistence.xml** solely to declare named queries if auto-configuration already manages EntityManagerFactory. If the project manually configures the persistence unit or has multiple EntityManagerFactories, register mapping resources on the specific factory/persistence unit used by the repositories.

## 10. Organizing files in multi-module projects

You can organize files by domain:

~~~text
src/main/resources/
└── META-INF/
    ├── orm.xml
    ├── catalog-queries.xml
    └── reporting-queries.xml
~~~

One way to divide them:

- **orm.xml**: default mappings or shared named queries.
- **catalog-queries.xml**: queries serving the catalog domain.
- **reporting-queries.xml**: aggregation and reporting queries.

When adding separate files, register them in **spring.jpa.mapping-resources**. Name queries using a logical namespace, for example:

~~~text
Book.findByIsbn
Book.findExpensive
Customer.findActive
PurchaseOrder.revenueByMonth
~~~

The query name is not a required package name. This convention simply avoids collisions and helps readers identify the related entity/use case.

Avoid creating one massive XML file containing every query in the entire application if multiple teams develop independently. Conversely, there is no need for a separate file per small query. Choose boundaries by domain and maintenance ownership.

## 11. How XML mappings and annotations coexist

JPA allows annotations and XML mappings to be used together. XML can supplement or override certain annotation metadata according to JPA mapping rules. However, avoid declaring the same metadata in multiple places without a clear reason.

Some guidelines:

- Entities can still be marked with **@Entity** in Java while named queries are placed in `orm.xml`.
- You can keep **@Table** and **@Column** in annotations and centralize named queries in XML.
- If XML declares field/relationship mappings overlapping with annotations, understand precedence and `metadata-complete` before deploying.
- Do not assume all XML declarations are purely additive; some XML configurations can override annotations.
- Use a single source of truth for each metadata category to minimize conflicts.

A maintainable option is: basic entity mappings in annotations, and named queries plus native result mappings in XML. This is optional, but it prevents entity classes from becoming overly long when there are many queries.

## 12. Validating named queries at startup and runtime

The JPA provider typically registers and validates named JPQL queries during persistence unit initialization. As a result, JPQL syntax errors or invalid entity/property names can cause the application to fail at startup.

With named native queries, database-specific SQL may only be fully validated when the query executes, depending on the provider and database. Do not rely on successful application startup to conclude that native SQL is valid.

An integration test can verify a named query in `orm.xml`:

~~~java
@DataJpaTest
class BookNamedQueryTest {

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void findsBookByNamedJpqlQuery() {
        Book book = new Book(
            "Spring Data JPA",
            "9780000000001",
            new BigDecimal("250.00")
        );
        entityManager.persist(book);
        entityManager.flush();

        List<Book> result = entityManager
            .getEntityManager()
            .createNamedQuery("Book.findByIsbn", Book.class)
            .setParameter("isbn", "9780000000001")
            .getResultList();

        assertThat(result).hasSize(1);
        assertThat(result.get(0).getTitle()).isEqualTo("Spring Data JPA");
    }
}
~~~

The test assumes the `Book` entity has a constructor matching the example. If the test slice fails to load mapping resources due to custom project configuration, inspect the EntityManagerFactory configuration and register mapping resources for tests.

You should have separate tests for:

- Named JPQL queries.
- Named native queries on the target database.
- Entity result mappings covering all required columns.
- Count queries or pagination if applicable.
- Parameter binding and result types.

## 13. Common pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Named query not found | XML file not loaded by persistence unit or wrong name | Check META-INF location, mapping-resources, and query name |
| XML schema/namespace error | Used legacy JPA namespace or incompatible version | Use Jakarta namespace and matching schema version |
| JPQL reports entity not found | Used table name instead of entity name or entity not managed | Use entity name and verify entity scanning |
| JPQL reports property not found | Used SQL column name instead of Java property | Use the property name on the entity |
| Native query fails to map entity | Missing persistent column or incorrect alias | SELECT all required columns or use result-set mapping |
| Native named query binds parameter incorrectly | Used non-portable named parameter | Use positional placeholder and positional setParameter |
| Two queries have duplicate names | Repeated definition across annotations/XML or multiple mapping files | Use unique names within the persistence unit |
| Repository uses a different query than expected | @Query on method takes precedence over convention-based named query | Check annotations and named-query lookup |
| Application fails to start after adding orm.xml | Invalid JPQL, nonexistent entity/property, or invalid XML | Inspect bootstrap errors and verify mappings |
| Native SQL only fails at runtime | Database-dependent SQL or incorrect alias | Integration test against the real database |

## 14. Checklist for organizing queries in orm.xml

- [ ] Place the default file in the exact location **src/main/resources/META-INF/orm.xml**.
- [ ] Use the Jakarta ORM namespace and version-compatible schema.
- [ ] Give every named query a unique name within the persistence unit.
- [ ] Use **named-query** for JPQL and **named-native-query** for direct SQL.
- [ ] Use entity names/property names in JPQL.
- [ ] Use table/column names in native SQL.
- [ ] Use positional parameters for native queries when portability is needed.
- [ ] Use **result-class** or **sql-result-set-mapping** appropriately.
- [ ] Return all required columns when mapping native results to entities.
- [ ] Register additional XML mappings via **spring.jpa.mapping-resources**.
- [ ] Check precedence when both annotations and XML declare metadata.
- [ ] Avoid duplicate query names across files.
- [ ] Write integration tests for both named JPQL and named native queries.

## 15. Conclusion

**META-INF/orm.xml** allows organizing JPA metadata and named queries outside entity source code. Use **named-query** for JPQL, **named-native-query** for direct SQL, and **sql-result-set-mapping** when mapping columns/aliases back to entities.

Spring Data JPA can locate named queries using the **EntityName.methodName** convention, while EntityManager can invoke them directly via **createNamedQuery**. With Spring Boot, ensure mapping resources are loaded by the persistence unit, especially when using additional XML files. Test queries against the real database to verify syntax, parameter binding, and result mappings.