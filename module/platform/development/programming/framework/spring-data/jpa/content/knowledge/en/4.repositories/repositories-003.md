# Choosing an Interface by Version and Application Needs in Spring Data JPA

Spring Data JPA provides multiple repository interfaces with overlapping functionality. Choosing the right interface ensures a repository exposes only the capabilities the application needs while avoiding compatibility issues when upgrading Spring Data. For typical JPA applications, `JpaRepository` is a convenient choice; when you need to restrict the API, optimize queries, or support dynamic queries, you can combine `Repository`, `CrudRepository`, `PagingAndSortingRepository`, `JpaSpecificationExecutor`, and related interfaces.

This lesson focuses on synchronous Spring Data JPA repositories. JPA is a blocking data access technology; reactive interfaces such as `ReactiveCrudRepository` are intended for other reactive modules, such as Spring Data MongoDB Reactive or R2DBC.

## 1. Understanding the Structure of Repository Interfaces

The interfaces are organized into functional layers. Not every interface is a direct drop-in replacement for another.

| Interface | Role | When to Use |
|---|---|---|
| `Repository<T, ID>` | Root interface marking the domain type and ID type; provides no built-in CRUD | When you want to declare the exact repository methods to expose |
| `CrudRepository<T, ID>` | Basic CRUD operations | When you need to save, read, count, and delete data |
| `ListCrudRepository<T, ID>` | Extends CRUD with `List`-returning methods | Using Spring Data 3.x+ and wanting to work with typed lists |
| `PagingAndSortingRepository<T, ID>` | Reading data by page or sort order | When `Pageable` or `Sort` is needed |
| `ListPagingAndSortingRepository<T, ID>` | Variant returning `List` for sorted queries | When `List` results are needed for sorting without `Page` metadata |
| `JpaRepository<T, ID>` | Combines CRUD, paging/sorting, Query by Example, and JPA-specific operations | Standard JPA repositories needing the full feature set |
| `JpaSpecificationExecutor<T>` | Executes queries based on `Specification` | Dynamic filters with many optional conditions |
| `QueryByExampleExecutor<T>` | Queries based on a sample entity | Simple searches using populated properties |

`T` is the entity type, and `ID` is the primary key type of the entity. For example, `JpaRepository<Product, Long>` means the repository manages the `Product` entity with a primary key of type `Long`.

### 1.1. `Repository` — The Root Interface

`Repository<T, ID>` is a marker interface. It tells Spring Data which entity the repository works with and what type the ID has. It does not provide methods like `save`, `findAll`, or `deleteById` by itself.

You can extend `Repository` directly and declare only the methods the application wants to expose:

~~~java
package com.example.store;

import java.util.Optional;
import org.springframework.data.repository.Repository;

public interface ProductLookupRepository
        extends Repository<Product, Long> {

    Optional<Product> findBySku(String sku);
}
~~~

Spring Data can generate the implementation for the derived query method `findBySku`. This approach is useful when a component only needs to look up products and should not have access to write/delete operations through that repository.

If you need to define a repository using an annotation instead of extending `Repository`, you can use `@RepositoryDefinition(domainClass = ..., idClass = ...)`. In most projects, interface inheritance remains easier to read and organize.

### 1.2. `CrudRepository` — Basic CRUD

`CrudRepository<T, ID>` provides commonly used operations:

~~~java
public interface ProductCrudRepository
        extends CrudRepository<Product, Long> {
}
~~~

Typical methods include:

- `save(entity)` and `saveAll(entities)` to save entities.
- `findById(id)`, `findAll()`, and `findAllById(ids)` to read data.
- `existsById(id)` and `count()` to check existence and count records.
- `deleteById(id)`, `delete(entity)`, `deleteAllById(ids)`, and `deleteAll()` to delete data.

Single-ID read methods usually return `Optional<T>` to represent the case where no record is found. In `CrudRepository`, methods returning multiple entities usually use `Iterable<T>`; this lets implementations avoid committing to a specific list structure.

### 1.3. `ListCrudRepository` — CRUD with `List`

`ListCrudRepository` was added in Spring Data 3.0. This interface extends `CrudRepository` and overrides several methods to return `List`, for example:

~~~java
public interface ProductListRepository
        extends ListCrudRepository<Product, Long> {
}
~~~

Key differences:

- `findAll()` returns `List<T>`.
- `findAllById(ids)` returns `List<T>`.
- `saveAll(entities)` returns `List<S>`.

Choose this interface when you want the basic CRUD API but need `List` return types for indexed access, Collection operations, or passing into components that accept `List`.

You do not need to choose `ListCrudRepository` if the application does not care about the specific return type. In Spring Data JPA 3.x+, `JpaRepository` already provides the `List`-returning methods.

### 1.4. `PagingAndSortingRepository` — Pagination and Sorting

`PagingAndSortingRepository<T, ID>` provides paginated or sorted read methods, typically:

~~~java
Page<Product> findAll(Pageable pageable);
Iterable<Product> findAll(Sort sort);
~~~

This interface is suitable when you need to limit the number of records read per query or sort by entity properties. However, how this interface combines with CRUD depends on the Spring Data version; the key change is covered in section 2.

### 1.5. `JpaRepository` — Default Choice for JPA Repositories

In a typical Spring Data JPA application, you can start with:

~~~java
package com.example.store;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

`JpaRepository` combines the essential capabilities of a JPA repository:

- CRUD with `List` return types on the appropriate APIs.
- Pagination and sorting.
- Query by Example.
- JPA operations such as `flush()`, `saveAndFlush()`, `saveAllAndFlush()`, and batch delete methods.
- `getReferenceById(id)` to obtain an entity reference by ID; loading data can be deferred until needed.

Because it already includes extensive functionality, `JpaRepository` is usually the most concise choice for a repository that needs reading, writing, deleting, and pagination. If only a subset of the API is needed, a narrower interface can be created to avoid exposing operations unsuitable for the caller's responsibility.

Several JPA-specific methods should be understood accurately:

- `flush()` synchronizes pending changes in the persistence context to the database. Flushing is not synonymous with committing a transaction.
- `saveAndFlush(entity)` saves the entity and requests an immediate flush.
- `saveAllAndFlush(entities)` saves a group of entities and then flushes.
- `getReferenceById(id)` may return a proxy/reference without reading the record immediately. If the ID does not exist, an error may only surface when the proxy is accessed or when the provider checks the data.
- `deleteAllInBatch()` and batch delete methods perform bulk deletions. They can bypass entity lifecycle callbacks and leave an open persistence context out of sync with the database. Use them only when you understand the consequences.

`saveAll` also does not guarantee that Hibernate will issue a single SQL INSERT statement for the entire list. Batching effectiveness depends on JPA provider settings, ID type, database, and transaction configuration.

## 2. Differences Between Spring Data 2.x and 3.x

When upgrading Spring Data, pay attention to changes in the inheritance relationships among interfaces. This is a common reason old repository code fails to compile or loses CRUD methods after updating dependencies.

### 2.1. Spring Data 2.x

In the Spring Data 2.x line, `PagingAndSortingRepository` extended `CrudRepository`. Therefore, a repository extending only `PagingAndSortingRepository` had both CRUD and pagination/sorting methods:

~~~java
// Pattern suitable for Spring Data 2.x
public interface ProductRepository
        extends PagingAndSortingRepository<Product, Long> {
}
~~~

The repository above could call `save`, `findById`, and `deleteById` as well as `findAll(Pageable)`.

### 2.2. Spring Data 3.x and Later

Starting from Spring Data 3.0, `PagingAndSortingRepository` no longer extends `CrudRepository`. This interface focuses on pagination and sorting. If you extend only it, the repository does not automatically have CRUD methods like `save` or `deleteById`.

Example:

~~~java
// Only has pagination/sorting capabilities in Spring Data 3.x+
public interface ProductPagingRepository
        extends PagingAndSortingRepository<Product, Long> {
}
~~~

If you want to combine CRUD and pagination/sorting, extend both:

~~~java
public interface ProductRepository
        extends CrudRepository<Product, Long>,
                PagingAndSortingRepository<Product, Long> {
}
~~~

Spring Data 3.0 also introduced `ListCrudRepository` and `ListPagingAndSortingRepository` to support `List`-returning APIs. For JPA, a simpler choice is usually `JpaRepository`, since it already combines the corresponding capabilities.

### 2.3. Quick Comparison Table

| Need | Spring Data 2.x | Spring Data 3.x+ |
|---|---|---|
| Basic CRUD | `CrudRepository` | `CrudRepository` or `ListCrudRepository` |
| CRUD + paging/sorting via one interface | `PagingAndSortingRepository` | `JpaRepository` for JPA, or combine `CrudRepository` with `PagingAndSortingRepository` |
| Paging/sorting only | `PagingAndSortingRepository` | `PagingAndSortingRepository` |
| CRUD with List results | `JpaRepository` returns List on corresponding JPA methods | `ListCrudRepository` or `JpaRepository` |
| Paging/sorting with List result for Sort | Depends on APIs in the version used | `ListPagingAndSortingRepository` or `JpaRepository` |

Do not copy a repository example from Spring Data 2.x documentation into a 3.x project without checking the inheritance hierarchy. Check the Javadoc for the exact dependency version managed by Spring Boot.

### 2.4. Spring Boot, Java, and JPA Namespace

The Spring Boot version determines the compatible Spring Framework and Spring Data versions managed via dependency management.

- Spring Boot 2.x projects typically use Spring Data 2.x and the `javax.persistence` namespace.
- Spring Boot 3.x moves to Spring Data 3.x, requires Java 17 or later, and uses the `jakarta.persistence` namespace.
- When using a newer Spring Boot line, let the Spring Boot BOM manage the corresponding Spring Data versions rather than upgrading individual modules manually.

Example entity imports in a Spring Boot 3.x project:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.GeneratedValue;
~~~

Legacy Spring Boot 2.x projects typically use:

~~~java
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.GeneratedValue;
~~~

Do not mix `javax.persistence` and `jakarta.persistence` within the same entity model. During an upgrade, check source imports, dependencies, plugins, integration libraries, and test configurations.

You can inspect resolved dependencies using Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.data,org.springframework.boot
~~~

Use the Spring Data version managed by the Spring Boot BOM unless the project has a clear compatibility reason to override it. Pinning separate versions for `spring-data-jpa` and `spring-data-commons` can produce incompatible APIs.

## 3. Choosing an Interface Based on Real Needs

No single interface is optimal for every application. Start from the operations the caller actually needs.

| Scenario | Interface to Consider | Reason |
|---|---|---|
| Standard JPA repository needing CRUD and paging | `JpaRepository<T, ID>` | Full functionality with minimal configuration |
| Only basic CRUD needed | `CrudRepository<T, ID>` | Small API without JPA-specific method dependencies |
| Using Spring Data 3.x+, needing CRUD returning List | `ListCrudRepository<T, ID>` | Convenient return types for Collections |
| Only queries needed, without exposing write/delete | `Repository<T, ID>` with custom query methods | Restricts API surface |
| Only paging/sorting needed and CRUD lives elsewhere | `PagingAndSortingRepository<T, ID>` | Separates paged query responsibility |
| Search filters vary by user parameters | `JpaSpecificationExecutor<T>` combined with `JpaRepository` | Builds dynamic query conditions |
| Searching by a simple sample object | `QueryByExampleExecutor<T>` or `JpaRepository` | Avoids writing many query methods |
| Complex fixed queries | `@Query` on the repository | Controls JPQL or native SQL |
| Custom data access logic | Repository fragment | Separates custom implementation from standard CRUD |

### 3.1. Using `JpaRepository` for Most JPA CRUD

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmailIgnoreCase(String email);

    Page<Customer> findByActiveTrue(Pageable pageable);
}
~~~

This example includes CRUD, paging, sorting, querying by email, and paginated querying of active customers. Derived query methods are generated from Java property names in the entity.

Choose this approach when the repository is the primary data access gateway for an aggregate or entity and the application needs most standard operations.

### 3.2. Restricting the API with `Repository`

A component that should only perform lookups can use a narrow repository:

~~~java
public interface CustomerReader
        extends Repository<Customer, Long> {

    Optional<Customer> findById(Long id);

    Optional<Customer> findByEmailIgnoreCase(String email);

    List<Customer> findByActiveTrue();
}
~~~

This repository does not expose `save` or `deleteById`. It is useful in modules that separate read/write permissions at the internal API level, or when you want to reduce a service's dependency on unused operations.

This is not a database security mechanism. True access control must still be enforced at the application, transaction, and database layers when required.

If you create a generic base interface shared across multiple repositories, mark it with `@NoRepositoryBean` so Spring Data does not try to create a bean directly for an interface without a concrete domain type:

~~~java
@NoRepositoryBean
public interface ReadOnlyRepository<T, ID>
        extends Repository<T, ID> {

    Optional<T> findById(ID id);

    List<T> findAll();
}

public interface ProductReader
        extends ReadOnlyRepository<Product, Long> {

    Optional<Product> findBySku(String sku);
}
~~~

Required imports:

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.repository.Repository;
~~~

### 3.3. Combining `JpaSpecificationExecutor` for Dynamic Filters

When a search screen has multiple optional filters—such as name, status, category, and price range—creating a repository method for every combination of conditions quickly becomes unmaintainable.

You can extend the repository:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long>,
                JpaSpecificationExecutor<Product> {
}
~~~

A simple `Specification`:

~~~java
public final class ProductSpecifications {

    private ProductSpecifications() {
    }

    public static Specification<Product> hasCategory(String category) {
        return (root, query, builder) ->
                builder.equal(root.get("category"), category);
    }

    public static Specification<Product> priceAtLeast(BigDecimal minPrice) {
        return (root, query, builder) ->
                builder.greaterThanOrEqualTo(root.get("price"), minPrice);
    }
}
~~~

Combining conditions in the service:

~~~java
Specification<Product> filter =
        Specification.where(ProductSpecifications.hasCategory("BOOK"))
                .and(ProductSpecifications.priceAtLeast(
                        new BigDecimal("100.00")));

Page<Product> result = products.findAll(
        filter,
        PageRequest.of(0, 20, Sort.by("name").ascending())
);
~~~

The example requires these imports:

~~~java
import java.math.BigDecimal;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;
~~~

In real applications, only add a condition when the corresponding parameter has a value. Avoid calling `equal` with a null value if business logic expects the filter to be skipped. Also verify property types, entity property names, and the SQL generated by Hibernate.

### 3.4. Choosing Query by Example for Simple Searches

Query by Example (QBE) lets you create a sample entity and use its properties as search criteria:

~~~java
Product probe = new Product();
probe.setName("keyboard");

ExampleMatcher matcher = ExampleMatcher.matching()
        .withIgnoreCase()
        .withStringMatcher(ExampleMatcher.StringMatcher.CONTAINING);

Example<Product> example = Example.of(probe, matcher);

List<Product> matches = products.findAll(example);
~~~

QBE works well when search criteria are primarily based on property values of a sample entity and matching options. QBE does not fully replace `Specification`: complex OR conditions, expressions across relationships, advanced comparisons, or multi-branch business logic are usually better served by `Specification` or JPQL.

### 3.5. Choosing `Page`, `Slice`, or `List`

When querying large lists, the return type is also a design decision:

- `Page<T>` contains page content plus total element/page counts. Spring Data typically needs an additional count query to compute the total.
- `Slice<T>` indicates whether a next page exists without necessarily counting all results.
- `List<T>` returns only the data; when passing `Pageable`, the list can still be limited to a page, but without page metadata.

Example:

~~~java
Page<Product> findByActiveTrue(Pageable pageable);

Slice<Product> findByCategory(String category, Pageable pageable);

List<Product> findByCategoryAndActiveTrue(
        String category,
        Pageable pageable
);
~~~

Use `Page` when the UI needs the total result count and total pages. Use `Slice` for "load more" or infinite scroll patterns where you only need to know whether more data exists. Use `List` when the caller only needs the records of a bounded slice of data.

## 4. When to Use Query Methods, `@Query`, or Repository Fragments?

Repository interfaces can combine multiple query strategies. Choose the simplest option that clearly satisfies the requirement.

### 4.1. Derived Query — Generating Queries from Method Names

~~~java
Optional<Product> findBySku(String sku);

List<Product> findByNameContainingIgnoreCase(String keyword);

List<Product> findByPriceBetween(
        BigDecimal minPrice,
        BigDecimal maxPrice
);
~~~

Suitable for queries whose conditions are easy to read from the method name. When the method name becomes too long or expresses complex logic, consider `Specification` or `@Query`.

### 4.2. `@Query` — JPQL or Native SQL

~~~java
@Query("""
       select p
       from Product p
       where p.active = true
         and p.price >= :minPrice
       """)
List<Product> findAvailableProducts(
        @Param("minPrice") BigDecimal minPrice
);
~~~

JPQL references entities and Java properties, not physical table or column names directly. If using native SQL, the query becomes tightly coupled to the syntax and capabilities of a specific database.

For update/delete statements using `@Modifying`, design transactions clearly and consider the persistence context state after bulk operations. Bulk updates/deletes do not automatically synchronize every entity currently managed in memory.

### 4.3. Repository Fragment — Custom Implementations

When query logic does not fit derived queries or `@Query`, it can be extracted into a fragment interface and separate implementation. The main repository extends the fragment so Spring Data composes the implementation into the repository.

This keeps custom logic clearly organized while preserving standard CRUD operations in `JpaRepository`. Avoid creating one huge repository implementation containing all data access logic when it can be split into fragments by responsibility.

## 5. Common Misconceptions to Avoid

1. **Extending only `PagingAndSortingRepository` on Spring Data 3.x and calling `save`:** this interface no longer provides CRUD. Add `CrudRepository` or use `JpaRepository`.
2. **Assuming `JpaRepository` is mandatory:** a repository can extend `Repository` or `CrudRepository` if only a small set of methods is needed.
3. **Assuming `ListCrudRepository` exists in every version:** this interface was added in Spring Data 3.0. Do not use it in projects still depending on Spring Data 2.x.
4. **Confusing `Page` with `List`:** `Page` provides metadata and usually triggers a count query; `List` has no total page information.
5. **Confusing `flush` with `commit`:** flush sends pending changes to the database, whereas commit ends the transaction.
6. **Using `deleteAllInBatch` like `deleteAll`:** batch operations can bypass entity lifecycle callbacks and leave the persistence context out of sync.
7. **Upgrading individual Spring Data modules separately:** keep Spring Data modules compatible with one another; prefer versions managed by the Spring Boot BOM.
8. **Using reactive repositories with JPA:** JPA is synchronous/blocking; choose reactive repositories only when using compatible reactive storage technologies and drivers.
9. **Assuming `saveAll` is always a single SQL batch:** batching requires provider configuration and also depends on key type, database, and transactions.
10. **Putting all operations into the repository:** transactions and business rules should generally be organized in services; repositories focus on data access.

## 6. Interface Selection Workflow

You can follow this workflow when creating a new repository or reviewing an existing one:

1. Identify the storage module: if using JPA, use Spring Data JPA interfaces; do not pick reactive interfaces from another module.
2. Check the Spring Boot/Spring Data version managed in the project.
3. List the operations callers need: read, write, delete, pagination, sorting, dynamic queries, or JPA-specific operations.
4. Choose the smallest interface that meets the needs. For standard JPA CRUD, start with `JpaRepository`.
5. If dynamic queries are needed, add `JpaSpecificationExecutor` or use QBE depending on complexity.
6. If only a few methods are needed, consider extending `Repository` and declaring a narrow API.
7. Write repository tests and inspect generated SQL for important queries.
8. When upgrading versions, read the release notes/Javadoc for that exact version and check namespace, method signature, and inheritance changes.

## 7. Self-Check Checklist

- [ ] I know the repository's entity type and ID type.
- [ ] I have verified the actual Spring Data version from the dependency tree or BOM.
- [ ] I do not rely on Spring Data 2.x's `PagingAndSortingRepository` inheritance in a 3.x project.
- [ ] I choose `JpaRepository` when the full JPA feature set is needed.
- [ ] I choose `Repository`/`CrudRepository` when a narrower API is desired.
- [ ] I understand when to use `Page`, `Slice`, or `List`.
- [ ] I add `JpaSpecificationExecutor` only when dynamic queries are required.
- [ ] I understand `flush`, transactions, and the limitations of batch operations.
- [ ] I do not mix `javax.persistence` with `jakarta.persistence`.
- [ ] The repository has tests covering important query methods.

## Conclusion

For Spring Data JPA applications, `JpaRepository<T, ID>` is a reasonable starting point when CRUD, pagination, sorting, and common JPA operations are needed. Use `Repository` or `CrudRepository` to keep the API small, add `JpaSpecificationExecutor` for dynamic filters, and choose `Page`/`Slice`/`List` based on the data callers need. When upgrading from Spring Data 2.x to 3.x, check the inheritance change on `PagingAndSortingRepository` and the new `List` interfaces so repositories continue to compile and provide the expected functionality.
