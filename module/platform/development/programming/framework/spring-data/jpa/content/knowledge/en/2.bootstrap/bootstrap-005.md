# Trying Out Create, Read, Update, and Delete Operations with Spring Data JPA

Spring Data JPA helps Java applications interact with relational databases through repositories. Instead of manually writing basic SQL statements for every operation, you declare an entity representing the table and a repository interface. Spring Data generates the repository implementation at application startup; Hibernate typically acts as the JPA provider to translate operations on entities into SQL.

This hands-on exercise builds a small Spring Boot application using Java 17+, Spring Data JPA, and H2. The program will add a product, read the product back, change its price, and delete the record. The H2 database runs in memory, making it convenient for experimentation without installing a database server.

## 1. How Does CRUD Work?

CRUD represents the four basic data operations:

| Operation | Meaning | Commonly Used Methods |
|---|---|---|
| Create | Add a new record | \`save(entity)\`, \`saveAll(entities)\` |
| Read | Read one or more records | \`findById(id)\`, \`findAll()\`, \`count()\` |
| Update | Modify an existing record | Load entity, update properties then \`save(entity)\`; or use dirty checking inside a transaction |
| Delete | Delete a record | \`deleteById(id)\`, \`delete(entity)\`, \`deleteAll()\` |

Basic processing flow:

1. The application invokes a repository method.
2. Spring Data JPA delegates the call to JPA operations on \`EntityManager\`.
3. Hibernate manages the entity and generates the corresponding SQL statement.
4. The database executes the SQL and returns results.
5. Results are mapped back into entities or Java values.

Repositories reduce boilerplate code, though they do not eliminate the need to understand SQL, primary keys, transactions, or table design. As data grows, pay attention to query design, pagination, indexes, and the number of SQL statements executed.

## 2. Creating the Maven Project

Create a project with the following structure. Packages and paths in the example consistently use \`com.example.jpacrud\`.

~~~text
spring-data-jpa-crud/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/jpacrud/
    │   │   ├── JpaCrudApplication.java
    │   │   ├── Product.java
    │   │   ├── ProductRepository.java
    │   │   └── ProductService.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/jpacrud/
            └── ProductRepositoryTest.java
~~~

Contents of \`pom.xml\`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>spring-data-jpa-crud</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>spring-data-jpa-crud</name>

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

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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
~~~

Spring Boot manages compatible versions of Spring Data JPA, Hibernate, and H2 via dependency management. In real projects, you can choose the latest Spring Boot 3.5.x patch suitable for your deployment environment; there is no need to specify separate versions for dependencies already managed by the parent.

## 3. Configuring the Database

Create \`src/main/resources/application.properties\`:

~~~properties
spring.datasource.url=jdbc:h2:mem:shopdb;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
spring.jpa.open-in-view=false

spring.h2.console.enabled=true
~~~

Explanation:

- \`jdbc:h2:mem:shopdb\` creates an in-memory H2 database named \`shopdb\`. Data is lost when the JVM terminates.
- \`DB_CLOSE_DELAY=-1\` keeps the database alive throughout the JVM's lifetime, even when there are temporarily no open connections.
- \`ddl-auto=create-drop\` instructs Hibernate to create the schema at application startup and drop it when the application shuts down. This is convenient for hands-on exercises.
- \`show-sql\` and \`format_sql\` help observe SQL generated by Hibernate.
- \`open-in-view=false\` avoids keeping the persistence context open throughout the HTTP request lifecycle. For web applications, load required data inside the service transaction.

Do not use \`create-drop\` for real data. In deployment environments, Flyway or Liquibase is typically used to manage migrations, with \`validate\` or another appropriate schema configuration selected. The H2 console should also only be enabled in controlled development environments.

## 4. Declaring the Product Entity

An entity is a Java class mapped by JPA to a database table. Create \`Product.java\`:

~~~java
package com.example.jpacrud;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    // JPA requires a no-argument constructor with protected or public access.
    protected Product() {
    }

    public Product(String name, BigDecimal price) {
        this.name = name;
        this.price = price;
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

    public BigDecimal getPrice() {
        return price;
    }

    public void setPrice(BigDecimal price) {
        this.price = price;
    }

    @Override
    public String toString() {
        return "Product{id=" + id
                + ", name='" + name + '\''
                + ", price=" + price.toPlainString()
                + "}";
    }
}
~~~

Important annotations:

- \`@Entity\` marks the class as JPA-managed.
- \`@Table(name = "products")\` specifies the table name.
- \`@Id\` identifies the primary key.
- \`@GeneratedValue(strategy = GenerationType.IDENTITY)\` delegates ID generation to the database using the identity mechanism.
- \`@Column\` declares constraints and column types. \`precision = 12, scale = 2\` fits the example storing prices with two decimal places.
- The no-argument constructor allows JPA to instantiate the entity when reading data.

Use \`BigDecimal\` for prices rather than \`double\` or \`float\`, because binary floating-point types can introduce rounding inaccuracies when representing decimal numbers. In real systems, add input validation and matching database constraints.

## 5. Creating the Repository

Create \`ProductRepository.java\`:

~~~java
package com.example.jpacrud;

import java.math.BigDecimal;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository extends JpaRepository<Product, Long> {

    List<Product> findByNameContainingIgnoreCase(String keyword);

    List<Product> findByPriceGreaterThanEqual(BigDecimal minPrice);
}
~~~

The two type parameters of \`JpaRepository<Product, Long>\` are the entity type and the primary key type, respectively. Spring Data automatically creates an implementation for this interface when the application starts.

In addition to standard CRUD methods, Spring Data can derive queries from method names:

- \`findByNameContainingIgnoreCase\` searches for names containing the keyword, ignoring case.
- \`findByPriceGreaterThanEqual\` finds products whose price is greater than or equal to the passed price.

There is no need to write SQL for these simple queries. For complex queries, \`@Query\` with JPQL or native SQL can be used; choose the approach fitting the complexity and performance requirements.

## 6. Testing All Four Operations

Create \`JpaCrudApplication.java\`:

~~~java
package com.example.jpacrud;

import java.math.BigDecimal;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class JpaCrudApplication {

    public static void main(String[] args) {
        SpringApplication.run(JpaCrudApplication.class, args);
    }

    @Bean
    CommandLineRunner crudDemo(ProductRepository products) {
        return args -> {
            // CREATE: add a new product.
            Product created = products.save(
                    new Product("Mechanical Keyboard", new BigDecimal("89.90"))
            );
            System.out.println("CREATE: " + created);

            // READ: read the product back by primary key.
            Product read = products.findById(created.getId())
                    .orElseThrow(() -> new IllegalStateException("Product not found"));
            System.out.println("READ:   " + read);

            // UPDATE: change the price and save the entity.
            read.setPrice(new BigDecimal("79.90"));
            Product updated = products.save(read);
            System.out.println("UPDATE: " + updated);

            // DELETE: delete the product and verify existence again.
            products.deleteById(created.getId());
            System.out.println("DELETE: exists="
                    + products.existsById(created.getId()));
        };
    }
}
~~~

Run the application with Maven:

~~~bash
mvn spring-boot:run
~~~

When the database is newly created and the program runs for the first time, the four lines printed by the program will look like:

~~~text
CREATE: Product{id=1, name='Mechanical Keyboard', price=89.90}
READ:   Product{id=1, name='Mechanical Keyboard', price=89.90}
UPDATE: Product{id=1, name='Mechanical Keyboard', price=79.90}
DELETE: exists=false
~~~

Startup logs and Hibernate SQL statements may appear interleaved. The output above shows the four lines from the \`System.out.println\` statements in the runner. IDs start at 1 because this is a fresh H2 database with no prior records.

### 6.1. CREATE — Adding Data

~~~java
Product created = products.save(
        new Product("Mechanical Keyboard", new BigDecimal("89.90"))
);
~~~

We create a new entity and pass it to \`save\`. Because the entity does not yet have a generated ID, Spring Data JPA recognizes it as a new entity and instructs JPA to persist it. Hibernate generates an \`INSERT\` statement; after saving succeeds, the ID is assigned to the entity.

You can insert multiple entities with \`saveAll(entities)\`. Avoid calling \`save\` in a loop for very large datasets without considering batching and transactions, as simple calls can generate excessive database round-trips.

### 6.2. READ — Reading Data

~~~java
Product product = products.findById(id)
        .orElseThrow(() -> new IllegalArgumentException("Product not found"));
~~~

\`findById\` returns \`Optional<Product>\` because the requested ID might not exist. Handle the empty case with \`orElseThrow\`, \`orElse\`, or checking \`isPresent()\`; do not call \`get()\` indiscriminately.

Common read options:

- \`findAll()\`: reads all records; only suitable when the table is small or data is bounded.
- \`findAllById(ids)\`: reads records by a list of IDs.
- \`existsById(id)\`: checks whether an ID exists.
- \`count()\`: counts records.
- Derived query methods such as \`findByNameContainingIgnoreCase(keyword)\`: searches by specific criteria.

For large tables, avoid using \`findAll()\` to load all data into memory. Use pagination or bounded queries.

### 6.3. UPDATE — Modifying Data

In the runner, we load the entity, change the price, and call \`save\`:

~~~java
Product product = products.findById(id).orElseThrow();
product.setPrice(new BigDecimal("79.90"));
Product updated = products.save(product);
~~~

For an existing entity, \`save\` typically uses merge to synchronize entity state with the persistence context. Use the object returned by \`save\`, because for a detached entity, the merged object may be a different instance.

Inside a transaction, if the entity is managed, Hibernate can detect property changes via dirty checking and emit an \`UPDATE\` upon flush or commit. In that case, calling \`save\` again is not required. The service example below illustrates this approach.

Do not treat \`save\` as a SQL upsert statement with identical rules across every database. Determining whether an entity is new or existing relies on Spring Data JPA's new-entity detection mechanism and entity configuration.

### 6.4. DELETE — Deleting Data

~~~java
products.deleteById(id);
boolean stillExists = products.existsById(id);
~~~

\`deleteById\` deletes the entity with the corresponding primary key. You can use \`delete(entity)\` when you already have the entity, or \`deleteAll()\` when you genuinely need to delete all data. Bulk delete operations must be considered carefully because they can affect cascades, the persistence context, and foreign key constraints.

In real applications, clearly define behavior when the ID does not exist, user permissions, business constraints, and auditing before deletion.

## 7. Placing Transactions in the Service

The repository already provides transactions for individual CRUD methods. However, a business operation often consists of multiple read and write steps; transaction boundaries should be placed in the service so the steps succeed or roll back together.

Create \`ProductService.java\`:

~~~java
package com.example.jpacrud;

import java.math.BigDecimal;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductService {

    private final ProductRepository products;

    public ProductService(ProductRepository products) {
        this.products = products;
    }

    @Transactional(readOnly = true)
    public Product getProduct(Long id) {
        return products.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Product not found"));
    }

    @Transactional
    public Product updatePrice(Long id, BigDecimal newPrice) {
        Product product = products.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Product not found"));

        product.setPrice(newPrice);

        // The entity remains managed; dirty checking will persist changes upon commit.
        return product;
    }

    @Transactional
    public void deleteProduct(Long id) {
        Product product = products.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Product not found"));
        products.delete(product);
    }
}
~~~

Key takeaways:

- \`@Transactional\` establishes a transaction boundary for the service method.
- \`readOnly = true\` indicates the method is read-only and lets the framework/provider apply appropriate optimizations; do not treat this as an absolute write-protection security mechanism.
- When \`updatePrice\` modifies a managed entity, dirty checking detects the change and Hibernate writes it to the database on transaction commit.
- If an error causes the transaction to roll back, changes within that transaction are undone according to database mechanics.
- In a web application, controllers should call services; services handle business logic and transactions, while repositories focus on data access.

The runner in the previous section called the repository directly to demonstrate each operation. In applications with real business logic, move that flow into a service instead of letting controllers or multiple components manage transactions individually.

## 8. Testing CRUD with JUnit

Repositories can be tested with \`@DataJpaTest\`. Create \`ProductRepositoryTest.java\`:

~~~java
package com.example.jpacrud;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class ProductRepositoryTest {

    @Autowired
    private ProductRepository products;

    @Test
    void shouldCreateReadUpdateAndDeleteProduct() {
        Product saved = products.save(
                new Product("Wireless Mouse", new BigDecimal("25.00"))
        );

        assertThat(saved.getId()).isNotNull();

        Product found = products.findById(saved.getId()).orElseThrow();
        assertThat(found.getName()).isEqualTo("Wireless Mouse");

        found.setPrice(new BigDecimal("20.00"));
        Product updated = products.save(found);
        assertThat(updated.getPrice()).isEqualByComparingTo("20.00");

        products.deleteById(saved.getId());
        assertThat(products.existsById(saved.getId())).isFalse();
    }
}
~~~

Run tests:

~~~bash
mvn test
~~~

\`@DataJpaTest\` creates a test slice focused on JPA components and normally runs each test inside a transaction that rolls back after the test completes. This prevents tests from leaving test data in the database. The test above verifies that an ID is generated, data is read accurately, the price is updated, and the record no longer exists after deletion.

## 9. Querying and Pagination as Data Grows

The repository can declare additional query methods following naming conventions:

~~~java
List<Product> findByNameContainingIgnoreCase(String keyword);
List<Product> findByPriceGreaterThanEqual(BigDecimal minPrice);
~~~

Call examples:

~~~java
List<Product> matches =
        products.findByNameContainingIgnoreCase("keyboard");

List<Product> affordable =
        products.findByPriceGreaterThanEqual(new BigDecimal("50.00"));
~~~

If sorting and pagination are needed, use \`Pageable\`:

~~~java
Page<Product> page = products.findAll(
        PageRequest.of(0, 10, Sort.by("name").ascending())
);

List<Product> firstTenProducts = page.getContent();
long totalProducts = page.getTotalElements();
int totalPages = page.getTotalPages();
~~~

Required imports for the pagination example:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
~~~

Page numbers start at 0; the example above retrieves the first page, up to 10 products, sorted ascending by the \`name\` entity property. Property names in \`Sort\` are the Java property names of the entity, not necessarily matching physical database column names.

\`Page\` typically requires an extra count query to compute total elements. If the UI only needs to know whether a next page exists, \`Slice\` may be more appropriate because it does not necessarily fetch the total record count.

## 10. Common Errors and Troubleshooting

| Symptom | Common Cause | How to Check |
|---|---|---|
| Unable to create repository bean | Package scan does not cover repository or Spring configuration is wrong | Place main class in a parent package of entities, repositories, and services |
| Entity not mapped | Missing \`@Entity\`, \`@Id\`, or no-argument constructor | Check entity annotations and constructors |
| Unable to connect to H2 | Missing H2 dependency or wrong URL/driver | Check dependency, JDBC URL, and startup logs |
| Record not found | ID does not exist or data has not been committed | Check ID, transactions, and actual data |
| Precision errors in prices | Using \`double\` or \`float\` | Use \`BigDecimal\` and declare precision/scale |
| Slow queries or high memory usage | Using \`findAll()\` on large tables or loading unnecessary relationships | Use filters, pagination, and inspect generated SQL |
| Foreign key constraint error | Deleting a parent record while child records still exist | Define relationships and cascade rules explicitly |

Some notes when moving to real applications:

1. **Validation:** validate input data at the application layer; while retaining key constraints in the database such as \`NOT NULL\`, \`UNIQUE\`, and foreign keys.
2. **Transactions:** group multiple operations belonging to the same business action into a single service transaction.
3. **N+1 queries:** when reading entity relationships, check SQL counts. Use fetch joins, entity graphs, or projections when appropriate; do not blindly enable eager loading on every relationship.
4. **Optimistic locking:** if multiple users can modify the same record, consider adding a \`@Version\` field to detect conflicting updates instead of silently overwriting each other's data.
5. **Migrations:** use Flyway or Liquibase for controlled schema changes. Avoid letting Hibernate automatically create or drop real data tables.
6. **Security:** do not expose the H2 console publicly and do not return entities directly from APIs if doing so exposes internal fields or triggers unintended relationship loading.

## 11. Self-Check After the Exercise

After running \`mvn spring-boot:run\` and \`mvn test\`, verify:

- [ ] The application starts and connects to H2.
- [ ] The CREATE operation creates a product and receives an ID.
- [ ] The READ operation retrieves the exact name and price.
- [ ] The UPDATE operation saves the new price.
- [ ] The DELETE operation causes \`existsById\` to return \`false\`.
- [ ] The repository test completes successfully.
- [ ] You can explain the roles of entity, repository, transaction, and dirty checking.

Once you understand the CRUD flow with H2, you can replace the datasource with PostgreSQL, MySQL, or another relational database system. Entities and repositories generally remain unchanged at a basic level; you must update the driver, JDBC URL, connection details, appropriate data types, and schema management approach for the new database.