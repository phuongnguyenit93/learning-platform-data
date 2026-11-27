# JPQL Queries Entities and Attributes Instead of Tables and Columns

## 1. Objectives

JPQL (Jakarta Persistence Query Language) is a query language that operates on the JPA object model. JPQL queries Entities and their Java attributes, whereas SQL queries physical tables and columns in the database.

For example, if the `Product` Entity is mapped to the `catalog_products` table and the `name` attribute is mapped to the `product_name` column, JPQL still writes `select p from Product p where p.name = :name`. Table names and column names do not appear in JPQL.

After this lesson, you will be able to:
- Distinguish JPQL from SQL and identify entity names and attribute names.
- Write JPQL queries in Spring Data JPA's `@Query`.
- Use named parameters, positional parameters, joins, path expressions, and conditional operators.
- Return Entities, scalars, DTOs, or Pages from JPQL.
- Use fetch joins to control relationship loading and avoid N+1 in suitable use cases.
- Perform bulk updates/deletes and understand their impact on the persistence context and lifecycle callbacks.

## 2. JPQL Works with the Entity Model

JPQL uses:
- **Entity name**: the Entity name in the JPA model. By default, it is the class name without the package; it can be changed using `@Entity(name = "...")`.
- **Persistent attribute**: the Java attribute name mapped in the Entity, which is either a field or a property depending on the Entity's access strategy.
- **Association path**: a path navigating through a relationship, for example `p.category.name`.

JPQL does not use table names from `@Table`, column names from `@Column`, Java getter names, or local application variable names. It uses entity names and persistent attribute names.

```java
@Entity
@Table(name = "catalog_products")
public class Product {
    @Id
    private Long id;

    @Column(name = "product_name")
    private String name;
}
```

JPQL:

```jpql
select p from Product p where p.name = :name
```

The equivalent SQL might be:

```sql
select p.id, p.product_name
from catalog_products p
where p.product_name = ?
```

The JPA provider is responsible for translating JPQL into SQL appropriate for the database and mapping. Therefore, the same JPQL can run across different databases as long as the mappings and expressions used are compatible.

### Renaming an Entity

If declared as:

```java
@Entity(name = "CatalogProduct")
@Table(name = "catalog_products")
public class Product {
    // Persistent attributes.
}
```

JPQL must use the entity name `CatalogProduct`:

```jpql
select p from CatalogProduct p where p.name = :name
```

`@Entity(name = ...)` renames the entity in the JPQL model. `@Table(name = ...)` specifies the physical table name. These two names serve different roles.

## 3. Sample Data Model

The example uses Java 17+, Maven, Spring Boot 3.5.0, Spring Data JPA, and H2. The model consists of `Category` and `Product`; each product can belong to a category.

### Category Entity

`src/main/java/com/example/catalog/product/Category.java`:

```java
package com.example.catalog.product;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "categories")
public class Category {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 80)
    private String name;

    @Column(nullable = false)
    private boolean active;

    protected Category() {
        // JPA requires a no-arg constructor.
    }

    public Category(String name, boolean active) {
        if (name == null || name.isBlank() || name.length() > 80) {
            throw new IllegalArgumentException("Category name is required");
        }
        this.name = name.trim();
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public boolean isActive() {
        return active;
    }
}
```

### Product Entity

`src/main/java/com/example/catalog/product/Product.java`:

```java
package com.example.catalog.product;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.math.BigDecimal;

@Entity
@Table(name = "catalog_products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "product_name", nullable = false, length = 160)
    private String name;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "category_id")
    private Category category;

    protected Product() {
        // JPA requires a no-arg constructor.
    }

    public Product(String name, BigDecimal price, Category category) {
        if (name == null || name.isBlank() || name.length() > 160) {
            throw new IllegalArgumentException("Product name is required");
        }
        if (price == null || price.signum() < 0) {
            throw new IllegalArgumentException("Price cannot be negative");
        }
        this.name = name.trim();
        this.price = price;
        this.category = category;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public Category getCategory() {
        return category;
    }
}
```

In this mapping, `Product.category` is a Java attribute. The corresponding physical column is `category_id`. JPQL accesses the relationship using `p.category`, not `p.category_id`.

## 4. Declaring JPQL with @Query

Spring Data JPA allows placing JPQL in `@Query` on a Repository method. The method name can then describe the business intent; the JPQL string defines the actual query.

`src/main/java/com/example/catalog/product/ProductRepository.java`:

```java
package com.example.catalog.product;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.transaction.annotation.Transactional;

public interface ProductRepository extends JpaRepository<Product, Long> {
    @Query("""
           select p
           from Product p
           where p.category.name = :categoryName
           order by p.name asc
           """)
    List<Product> findByCategoryName(@Param("categoryName") String categoryName);

    @Query("""
           select p
           from Product p
           join p.category c
           where c.active = true
             and p.price <= :maxPrice
           order by p.price asc, p.name asc
           """)
    List<Product> findAffordableProductsInActiveCategories(
            @Param("maxPrice") BigDecimal maxPrice);

    @Query("""
           select p
           from Product p
           left join fetch p.category
           where p.id = :id
           """)
    Optional<Product> findWithCategoryById(@Param("id") Long id);

    @Query(
            value = "select p from Product p join p.category c where c.name = :categoryName",
            countQuery = "select count(p) from Product p join p.category c where c.name = :categoryName")
    Page<Product> findPageByCategoryName(
            @Param("categoryName") String categoryName, Pageable pageable);

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Transactional
    @Query("""
           update Product p
           set p.price = :newPrice
           where p.category.name = :categoryName
           """)
    int updatePriceByCategoryName(
            @Param("categoryName") String categoryName,
            @Param("newPrice") BigDecimal newPrice);
}
```

The `findByCategoryName` method uses the path expression `p.category.name`. JPQL can automatically generate the required join to traverse the association. The second method writes an explicit join to place conditions on the alias `c`.

`@Query` expects JPQL by default in Spring Data JPA. Only when `nativeQuery = true` is enabled does it switch to native SQL.

## 5. Named Parameters and Positional Parameters

JPQL supports named parameters and positional parameters.

Named parameter:

```java
@Query("select p from Product p where p.name = :name and p.price <= :maxPrice")
List<Product> search(
        @Param("name") String name,
        @Param("maxPrice") BigDecimal maxPrice);
```

Positional parameter:

```java
@Query("select p from Product p where p.name = ?1 and p.price <= ?2")
List<Product> search(String name, BigDecimal maxPrice);
```

Named parameters are generally easier to read and less error-prone when a method has multiple parameters. The name in `@Param` must match the name after `:` in JPQL exactly.

Never concatenate user-supplied strings directly into JPQL. Use parameter binding to prevent syntax errors and injection risks.

### LIKE and IN Conditions

```java
@Query("""
       select p from Product p
       where lower(p.name) like lower(concat('%', :keyword, '%'))
       """)
List<Product> searchByName(@Param("keyword") String keyword);

@Query("select p from Product p where p.id in :ids")
List<Product> findAllByIds(@Param("ids") List<Long> ids);
```

`IN` with a collection parameter is suitable when the list is non-empty. For an empty list, handle it in the Service layer before calling the repository to avoid depending on how the provider/database handles an empty `IN` expression.

## 6. Path Expressions and JOIN

JPQL can navigate nested attributes using dot notation:

```jpql
select p from Product p where p.category.name = :categoryName
```

When you need to filter, sort, or select data from an association, you can declare a join and an alias:

```jpql
select p from Product p join p.category c where c.active = true
```

### INNER JOIN

`join` or `inner join` only returns records that have a matching association. For example:

```jpql
select p from Product p join p.category c where c.name = :categoryName
```

### LEFT JOIN

`left join` retains the left side even when there is no association on the right side:

```jpql
select p from Product p left join p.category c
```

Because `Product.category` is optional in the example, products without a category can still appear in the results.

### ON and WHERE Conditions

JPQL allows placing additional conditions on a join using `on`:

```jpql
select p
from Product p
left join p.category c on c.active = true
```

The `on` condition restricts which rows match on the joined side while still retaining the `Product` on the left side. If you move `c.active = true` down to `where`, rows without a category will be filtered out because the condition on `c` is not true. This distinction is especially important with `left join`.

### JOIN over a Collection

If an Entity has a collection association, you can join that collection:

```jpql
select distinct d
from Department d
join d.employees e
where e.active = true
```

`distinct` helps eliminate duplicate Entity results when one `Department` matches multiple `Employee` instances. With a collection join, multiple SQL result rows can correspond to the same root Entity.

## 7. JOIN FETCH and Avoiding N+1

`join fetch` instructs the provider to load the association together with the root Entity in the same query. For example:

```jpql
select p
from Product p
left join fetch p.category
where p.id = :id
```

This query loads both the `Product` and its associated `Category` so that when `product.getCategory()` is read within the transaction, the provider does not need a separate query for that association.

Distinction:
- `join p.category c`: joins to filter, sort, or use data from the association; it does not necessarily require the association to be fetched into the Entity graph.
- `join fetch p.category`: joins and simultaneously instructs the provider to load the association.

Fetch join is a useful tool to address N+1 when you know in advance that a use case needs the related data. You can use `@EntityGraph` as an alternative if you want to separate the fetch plan from the JPQL string.

Avoid paginating directly on a query that fetch-joins a collection such as `@OneToMany` or `@ManyToMany`. Collection joins can multiply rows, causing pagination to become semantically incorrect or forcing Hibernate to load large amounts of data into memory and paginate there. In such cases, consider querying IDs by page first and then loading details, using batch fetching, DTO projection, or a suitable `@EntityGraph`. To-one fetch joins are generally easier to control.

## 8. Projections and DTOs with JPQL

The Service does not always need the full Entity. JPQL supports constructor expressions to return DTOs.

`src/main/java/com/example/catalog/product/ProductSummary.java`:

```java
package com.example.catalog.product;

import java.math.BigDecimal;

public class ProductSummary {
    private final Long id;
    private final String name;
    private final BigDecimal price;

    public ProductSummary(Long id, String name, BigDecimal price) {
        this.id = id;
        this.name = name;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }
}
```

Add a method to `ProductRepository`:

```java
@Query("""
       select new com.example.catalog.product.ProductSummary(p.id, p.name, p.price)
       from Product p
       where p.category.name = :categoryName
       order by p.name
       """)
List<ProductSummary> findSummariesByCategoryName(
        @Param("categoryName") String categoryName);
```

Constructor expressions use the fully qualified class name, and the arguments must match a suitable constructor. The result is a DTO, not a managed Entity. This approach reduces the amount of data fetched from the database and avoids exposing unnecessary Entity graphs outside the persistence layer.

## 9. Aggregates, GROUP BY, and HAVING

JPQL supports aggregate functions such as `count`, `sum`, `avg`, `min`, and `max`, along with `group by` and `having`.

```java
@Query("""
       select c.name, count(p)
       from Product p
       join p.category c
       group by c.name
       having count(p) >= :minimumProducts
       order by c.name
       """)
List<Object[]> countProductsByCategory(
        @Param("minimumProducts") long minimumProducts);
```

Each `Object[]` element contains two values in select order: the category name and the number of Products. For long-term usage, consider a DTO constructor expression or a projection with named fields to reduce manual casting.

## 10. Pagination with Page and countQuery

Spring Data JPA can paginate JPQL results by accepting a `Pageable` and returning `Page<T>`. When you need control over the counting query, declare a separate `countQuery`:

```java
@Query(
        value = "select p from Product p join p.category c where c.name = :categoryName",
        countQuery = "select count(p) from Product p join p.category c where c.name = :categoryName")
Page<Product> findPageByCategoryName(
        @Param("categoryName") String categoryName, Pageable pageable);
```

`Page<T>` contains the page content and total count metadata. Spring Data may need to run an additional count query to determine the total number of elements and total pages. For complex queries, an explicit `countQuery` prevents it from deriving an unsuitable count query.

If you only need to know whether a next page exists without needing the total result count, consider returning `Slice<T>` to avoid the cost of a count query.

Example repository call:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by("name").ascending().and(Sort.by("id").ascending()));

Page<Product> page = productRepository.findPageByCategoryName("Electronics", pageable);
System.out.println(page.getTotalElements());
System.out.println(page.getTotalPages());
```

Page index starts at 0. Include a stable sort order, such as adding the ID as a secondary criterion, to avoid non-deterministic ordering when multiple records share the same name.

## 11. UPDATE and DELETE with JPQL

JPQL supports bulk updates and bulk deletes. In Spring Data JPA, the repository method requires `@Modifying`; the operation must run inside a transaction.

Example:

```java
@Modifying(clearAutomatically = true, flushAutomatically = true)
@Transactional
@Query("update Product p set p.price = :newPrice where p.category.name = :categoryName")
int updatePriceByCategoryName(
        @Param("categoryName") String categoryName,
        @Param("newPrice") BigDecimal newPrice);
```

The `int` return value is the number of affected records. `flushAutomatically = true` requests flushing pending changes before executing the bulk query; `clearAutomatically = true` requests clearing the persistence context afterward to avoid continuing to use managed Entities with stale state.

Bulk DML has important characteristics:
- It operates directly on the database in a single statement without loading each Entity into the persistence context.
- Lifecycle callbacks such as `@PreUpdate`, `@PostUpdate`, `@PreRemove`, and `@PostRemove` do not execute for each affected Entity.
- Cascades from normal Entity operations are not applied the way they are when calling `remove()` on individual Entities.
- Already-managed Entities may hold stale values after a bulk query; appropriate clearing or refreshing is needed.

Do not use bulk updates when business logic requires per-Entity execution. Load the Entities and modify them inside a transaction, or move the necessary rules into the bulk statement/database itself when appropriate.

JPQL bulk update/delete has a narrower scope and syntax than SQL. In particular, you cannot freely use joins in update/delete statements as you do in select queries; check the JPA specification and use subqueries or redesign the query when needed.

## 12. JPQL and Native SQL

| Criterion | JPQL | Native SQL |
| --- | --- | --- |
| Query target | Entities and persistent attributes. | Physical tables, views, and columns. |
| Names in query | Entity names, property names. | Table and column names. |
| Database portability | Higher; provider translates to SQL. | More dependent on dialect/database. |
| Database-specific features | Limited to supported JPQL expressions and functions. | Can use database-specific syntax, CTEs, window functions, or features. |
| Result mapping | Entities, scalars, DTO constructor expressions. | Entity mappings, scalars, or projections with appropriate configuration. |

JPQL:

```java
@Query("select p from Product p where p.name = :name")
List<Product> findByNameJpql(@Param("name") String name);
```

Native SQL:

```java
@Query(value = "select * from catalog_products p where p.product_name = :name", nativeQuery = true)
List<Product> findByNameNative(@Param("name") String name);
```

Only enable `nativeQuery = true` when you genuinely want to write SQL against the physical schema or need database features that JPQL cannot express adequately.

## 13. Project Configuration and Testing

The example uses Java 17+ and Spring Boot 3.5.0. Required dependencies:

```xml
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
```

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:jpqldb;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=true
```

`src/test/java/com/example/catalog/product/ProductRepositoryJpqlTest.java`:

```java
package com.example.catalog.product;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

@DataJpaTest
class ProductRepositoryJpqlTest {
    @Autowired
    private ProductRepository productRepository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void queriesByEntityPropertyAndJoinsCategory() {
        Category electronics = entityManager.persist(new Category("Electronics", true));
        Category inactive = entityManager.persist(new Category("Archived", false));
        entityManager.persist(new Product("Keyboard", new BigDecimal("79.90"), electronics));
        entityManager.persist(new Product("Mouse", new BigDecimal("25.00"), electronics));
        entityManager.persist(new Product("Old device", new BigDecimal("10.00"), inactive));
        entityManager.flush();

        List<Product> products = productRepository.findByCategoryName("Electronics");

        assertThat(products)
                .extracting(Product::getName)
                .containsExactly("Keyboard", "Mouse");
    }

    @Test
    void returnsDtoProjection() {
        Category electronics = entityManager.persist(new Category("Electronics", true));
        entityManager.persist(new Product("Keyboard", new BigDecimal("79.90"), electronics));
        entityManager.flush();

        List<ProductSummary> summaries = productRepository
                .findSummariesByCategoryName("Electronics");

        assertThat(summaries).hasSize(1);
        assertThat(summaries.get(0).getName()).isEqualTo("Keyboard");
        assertThat(summaries.get(0).getPrice()).isEqualByComparingTo("79.90");
    }

    @Test
    void fetchesCategoryWithProduct() {
        Category electronics = entityManager.persist(new Category("Electronics", true));
        Product product = entityManager.persist(
                new Product("Keyboard", new BigDecimal("79.90"), electronics));
        entityManager.flush();
        Long productId = product.getId();
        entityManager.clear();

        Product loaded = productRepository.findWithCategoryById(productId).orElseThrow();

        assertThat(loaded.getCategory().getName()).isEqualTo("Electronics");
    }

    @Test
    void paginatesAndCountsResults() {
        Category electronics = entityManager.persist(new Category("Electronics", true));
        entityManager.persist(new Product("Keyboard", new BigDecimal("79.90"), electronics));
        entityManager.persist(new Product("Mouse", new BigDecimal("25.00"), electronics));
        entityManager.persist(new Product("Monitor", new BigDecimal("199.00"), electronics));
        entityManager.flush();

        Page<Product> page = productRepository.findPageByCategoryName(
                "Electronics",
                PageRequest.of(0, 2, Sort.by("name").ascending().and(Sort.by("id").ascending())));

        assertThat(page.getContent()).hasSize(2);
        assertThat(page.getTotalElements()).isEqualTo(3);
        assertThat(page.getTotalPages()).isEqualTo(2);
    }
}
```

Run tests from the directory containing `pom.xml`:

```bash
mvn test
```

The expected result is Maven finishing with `BUILD SUCCESS` and all four tests passing. The tests verify path expressions, joins, DTO constructor projection, fetch joins, and pagination/count queries. This is the expected output from the example, not an actual build log.

## 14. Common Errors

| Symptom | Cause | Solution |
| --- | --- | --- |
| `UnknownEntityException` or entity not found | Using table name instead of entity name, or entity is not scanned. | Use the default Entity name or `@Entity(name=...)` and check component scanning. |
| Attribute not found | Using SQL column name instead of persistent attribute, or typo in path. | Cross-check Java property names and association mappings. |
| `@Query` written as SQL fails with JPQL syntax error | Forgetting that `@Query` defaults to JPQL. | Use entity/property names or set `nativeQuery = true` if SQL is needed. |
| Parameter not bound | `@Param` name does not match `:parameter` or positional order is wrong. | Use named parameters and verify exact names. |
| Query returns duplicate Entities after collection join | One root Entity matches multiple collection elements. | Use `select distinct` when semantics require unique Entities. |
| N+1 queries when reading associations | Query does not fetch the association while code accesses the lazy relation repeatedly. | Use fetch join, `@EntityGraph`, batch fetching, or DTOs. |
| Pagination with collection fetch join is incorrect or slow | Collection join multiplies rows and hinders database-level pagination. | Separate paginated ID query and related data query, or use DTO/batch fetching. |
| Entities in persistence context have stale data after bulk DML | Bulk query bypasses managed state of individual Entities. | Flush before if needed and clear/refresh after the bulk query. |
| DTO constructor expression fails | Wrong fully qualified class name, parameter order, or constructor types. | Ensure constructor is public and parameters match the select expressions. |

## 15. Principles for Writing Maintainable JPQL

1. Always use entity names and persistent attribute names; only use table/column names in native SQL.
2. Prefer named parameters to keep queries readable and avoid parameter ordering mistakes.
3. Use aliases for joins so conditional expressions remain clear.
4. Use `distinct` when a collection join can produce multiple rows for the same root Entity and results need deduplication.
5. Only use fetch joins for associations needed by the use case; avoid fetching collections together with pagination.
6. Use DTO projections when only a subset of data is required.
7. Declare an explicit `countQuery` for `Page` if the query is complex.
8. Use `@Modifying` and transactions for bulk DML; proactively manage the persistence context afterward.
9. Switch to native SQL when database-specific features are needed or a query cannot be expressed well in JPQL.

## 16. Completion Checklist

- [ ] Can explain that JPQL queries Entities and Java attributes rather than physical tables/columns.
- [ ] Can distinguish entity names from table names and persistent attributes from column names.
- [ ] Can write `@Query` with named parameters.
- [ ] Can use path expressions, inner joins, left joins, and `on` conditions.
- [ ] Can distinguish regular joins from join fetches.
- [ ] Can return Entities, DTOs, and Pages from JPQL.
- [ ] Understand the impact of count queries and collection fetch joins on pagination.
- [ ] Can use `@Modifying` for bulk update/delete and manage the persistence context.
- [ ] Know when to switch to native SQL.
- [ ] Can run integration tests with H2.

Once completed, you can write JPQL aligned with the Entity model, query relationships accurately, and choose between Entity results, DTOs, pagination, or native SQL based on practical requirements.