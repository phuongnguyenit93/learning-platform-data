# Choosing a Repository Interface by Version and Application Needs in Spring Data JPA

Choosing a repository interface affects the set of methods the service layer can call, return types, and Spring Data upgradeability. A repository that needs to write/delete data has different requirements from a search-only repository; an application needing pagination also has different requirements from a task that just loads a small list.

In Spring Data JPA, `JpaRepository<T, ID>` is often a convenient choice for common JPA CRUD. However, not every repository needs that entire API. When designing, identify the Spring Data version in use, the operations callers actually need, and the repository's responsibility boundaries.

This lesson focuses on how to make that decision, compatibility differences between Spring Data 2.x and 3.x, how to narrow an API, and how to verify that choice in a real project.

## 1. Start from caller needs

Do not choose an interface simply because it is familiar. First, list the capabilities required by the components calling the repository:

- Only look up by ID or by a few attributes?
- Need to create, update, and delete data?
- Need sorting or pagination?
- Have optional filters combined dynamically?
- Need JPA-specific APIs such as flush, entity references, or batch delete operations?
- Need to return `List`, `Page`, or `Slice`?
- Is the repository used across multiple modules or layers with different operation permissions?

These answers determine the right interface. For example, a service that only looks up products by SKU does not need a repository exposing `deleteAll()`; a paginated admin view typically needs `Pageable`; a data import pipeline may need batch write APIs and explicit transactions.

Treat a repository as a contract between the business layer and the storage layer. The wider the contract, the more likely callers will depend on operations they do not actually need.

## 2. Check the Spring Data version before choosing

Interface hierarchies can differ between Spring Data generations. In a Spring Boot project, the Spring Data version is typically managed through the Spring Boot BOM. Therefore, inspect the resolved dependencies rather than guessing from dependency names or an online tutorial.

With Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.data:spring-data-commons,org.springframework.data:spring-data-jpa
~~~

With Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-data-commons --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-data-jpa --configuration runtimeClasspath
~~~

If the Gradle command is run on Windows PowerShell, `gradlew.bat` can be used instead of `./gradlew`.

### 2.1. Key difference between Spring Data 2.x and 3.x

In Spring Data 2.x, `PagingAndSortingRepository<T, ID>` extends `CrudRepository<T, ID>`. Thus, simply extending `PagingAndSortingRepository` gives the repository both CRUD and paging/sorting.

~~~java
// Spring Data 2.x: PagingAndSortingRepository includes CRUD.
public interface ProductRepository
        extends PagingAndSortingRepository<Product, Long> {
}
~~~

Starting in Spring Data 3.0, this inheritance relationship changed: `PagingAndSortingRepository` focuses on paging/sorting and no longer extends `CrudRepository`. If you only extend it, methods like `save` or `deleteById` do not automatically appear.

~~~java
// Spring Data 3.x+: paging/sorting only.
public interface ProductPagingRepository
        extends PagingAndSortingRepository<Product, Long> {
}
~~~

If a 3.x project needs both CRUD and paging/sorting without using `JpaRepository`, combine the two interfaces:

~~~java
// Spring Data 3.x+: explicitly combine both capability groups.
public interface ProductRepository
        extends CrudRepository<Product, Long>,
                PagingAndSortingRepository<Product, Long> {
}
~~~

Spring Data 3.0 also introduced `ListCrudRepository` and `ListPagingAndSortingRepository`. They provide methods returning `List` in the corresponding cases, sparing callers from handling `Iterable` when they want a concrete list.

| Version | CRUD | Paging/sorting | List-returning APIs |
|---|---|---|---|
| Spring Data 2.x | `CrudRepository` | `PagingAndSortingRepository` also includes CRUD | `JpaRepository` has common List APIs |
| Spring Data 3.x+ | `CrudRepository` or `ListCrudRepository` | `PagingAndSortingRepository` is a separate group | `ListCrudRepository`, `ListPagingAndSortingRepository`, and `JpaRepository` |

In JPA applications, `JpaRepository` often hides most of this difference because it provides the needed JPA feature set. The inheritance difference still matters when a project uses `PagingAndSortingRepository` directly or defines custom base interfaces.

### 2.2. Spring Boot 2.x and 3.x

Spring Boot 2.x projects typically pair with Spring Data 2.x and the `javax.persistence` persistence namespace. Spring Boot 3.x moves to Spring Data 3.x, requires Java 17 or higher, and uses the `jakarta.persistence` namespace.

Example imports in a Boot 3.x project:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.GeneratedValue;
~~~

Older Boot 2.x projects typically have:

~~~java
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.GeneratedValue;
~~~

Do not mix the two namespaces in the same entity model. When upgrading, check entities, converters, annotations, integration libraries, and test configurations. Let the Spring Boot BOM manage compatible Spring Data modules; do not manually upgrade `spring-data-commons` and `spring-data-jpa` individually to mismatched lines.

## 3. Choosing by the API surface to expose

### 3.1. Repository — declare only the needed contract

`Repository<T, ID>` is the root marker interface for Spring Data to recognize a repository. It does not provide CRUD on its own. You can declare just the methods you need:

~~~java
package com.example.catalog;

import java.util.Optional;
import org.springframework.data.repository.Repository;

public interface ProductReader extends Repository<Product, Long> {

    Optional<Product> findBySku(String sku);

    Optional<Product> findById(Long id);
}
~~~

Spring Data can generate implementations for the query methods above. Callers see only the two declared lookup operations. This suits read-only components or modules wanting a narrow contract.

A narrow interface does not by itself create a database security mechanism. If end users are not permitted to view or modify data, authorization checks are still required in the service/API layer, along with database permissions when the architecture requires them.

### 3.2. CrudRepository — basic CRUD

When callers need create, read, update, and delete operations without JPA-specific APIs, `CrudRepository<T, ID>` is a compact choice:

~~~java
public interface ProductCrudRepository
        extends CrudRepository<Product, Long> {

    Optional<Product> findBySku(String sku);
}
~~~

Basic CRUD methods can work across multiple Spring Data modules. This is helpful when you want services to depend on a general repository contract even though the concrete implementation may be JPA.

In Spring Data 2.x, multi-entity methods on `CrudRepository` typically return `Iterable`. If callers need `List`, you can convert in the service or pick an interface with List-returning APIs suitable for your version.

### 3.3. ListCrudRepository — when callers need List

Starting in Spring Data 3.0:

~~~java
public interface ProductListRepository
        extends ListCrudRepository<Product, Long> {
}
~~~

Choose this interface if the application only needs CRUD but wants `findAll`, `findAllById`, and `saveAll` to return `List` in the contract. It fits callers needing the full Collection API, ordered processing, or passing results to components that accept `List`.

There is no need to switch to `ListCrudRepository` just to make code shorter if the project already uses `JpaRepository`; `JpaRepository` already provides List return types for those operations.

### 3.4. PagingAndSortingRepository — when pagination or sorting is needed

This interface provides read methods accepting `Pageable` or `Sort`. On Spring Data 3.x, it does not include CRUD.

~~~java
public interface ProductPagingRepository
        extends PagingAndSortingRepository<Product, Long> {
}
~~~

If the repository also needs CRUD on 3.x, combine it with `CrudRepository` or use `JpaRepository` for JPA. If only paged queries are needed, keeping a dedicated paging interface clearly communicates read-only responsibility.

### 3.5. JpaRepository — when the full JPA feature set is needed

This is the common choice for repositories in JPA applications:

~~~java
package com.example.catalog;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    Optional<Product> findBySku(String sku);
}
~~~

`JpaRepository` combines CRUD, paging/sorting, and Query by Example capabilities, while also providing JPA operations like flush and entity references. In Spring Data 3.x, it also provides List APIs aligned with the new interface structure.

Choose it when callers genuinely need most of a JPA repository's functionality. If a service only needs lookups, you can pass a narrower read interface instead of coupling the service to all of `JpaRepository`.

## 4. Choosing return types by how callers consume data

Choosing the repository interface only addresses the method set. Query return types also affect performance and API contracts.

### 4.1. List — simple list

Use `List<T>` when the result set is small or the query is already explicitly bounded:

~~~java
List<Product> findByCategory(String category);
~~~

The method above can load every product in a category. If a category has hundreds of thousands of records, returning the full list can consume significant memory and time.

### 4.2. Page — total result count needed

~~~java
Page<Product> findByCategory(
        String category,
        Pageable pageable
);
~~~

`Page<T>` provides page content, total element count, total page count, and current page metadata. To compute the total, Spring Data typically needs an extra count query. Therefore, `Page` fits UIs that display something like "page 2 of 18" or total result counts.

### 4.3. Slice — only need to know if more data exists

~~~java
Slice<Product> findByCategory(
        String category,
        Pageable pageable
);
~~~

`Slice<T>` provides the current slice's data and whether a next page exists. It fits "Load more" buttons or infinite scroll when the UI does not need the total record count. Depending on the query and database, Spring Data may fetch one extra record to determine whether further results remain.

### 4.4. List with Pageable — fetch only bounded data

~~~java
List<Product> findByActiveTrue(Pageable pageable);
~~~

This limits results by page without returning total-element metadata like `Page`. Use it when callers only need a bounded slice of a list.

Do not use `Page` for every endpoint. If the total result count is unused, `Slice` or bounded `List` can reduce query overhead.

## 5. Adding executors by search style

A repository can compose multiple interfaces to add search capabilities. Executors do not replace CRUD; they supplement how queries are built.

### 5.1. JpaSpecificationExecutor — dynamic criteria

When users can toggle multiple filters on and off, `JpaSpecificationExecutor<T>` helps compose predicates:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long>,
                JpaSpecificationExecutor<Product> {
}
~~~

Example Specification:

~~~java
public final class ProductSpecs {

    private ProductSpecs() {
    }

    public static Specification<Product> active() {
        return (root, query, cb) ->
                cb.isTrue(root.get("active"));
    }

    public static Specification<Product> categoryIs(String category) {
        return (root, query, cb) ->
                cb.equal(root.get("category"), category);
    }

    public static Specification<Product> priceAtLeast(BigDecimal price) {
        return (root, query, cb) ->
                cb.greaterThanOrEqualTo(root.get("price"), price);
    }
}
~~~

Combining them:

~~~java
Specification<Product> spec =
        Specification.where(ProductSpecs.active())
                .and(ProductSpecs.categoryIs("BOOK"))
                .and(ProductSpecs.priceAtLeast(new BigDecimal("50.00")));

Page<Product> result = products.findAll(
        spec,
        PageRequest.of(0, 20, Sort.by("name").ascending())
);
~~~

In production applications, only add a predicate when the corresponding filter is supplied. Validate inputs and inspect query plans if filters can touch large tables.

### 5.2. QueryByExampleExecutor — search by example entity

Query by Example fits simple searches based on values of a probe object:

~~~java
Product probe = new Product();
probe.setName("mouse");

ExampleMatcher matcher = ExampleMatcher.matching()
        .withIgnoreCase()
        .withStringMatcher(ExampleMatcher.StringMatcher.CONTAINING);

List<Product> matches =
        products.findAll(Example.of(probe, matcher));
~~~

QBE is convenient when conditions are straightforward property matching. It does not express complex ORs, advanced comparisons, or relationship criteria well; in those cases Specification or JPQL is usually clearer.

## 6. Organizing interfaces along module boundaries

A large application may have multiple services sharing one entity with different needs. Not every service needs to depend on the same broad repository.

Example:

~~~java
public interface ProductReader extends Repository<Product, Long> {
    Optional<Product> findById(Long id);
    Optional<Product> findBySku(String sku);
}

public interface ProductWriter extends Repository<Product, Long> {
    <S extends Product> S save(S product);
}
~~~

An adapter or service can inject only the contract it requires. This organization makes dependencies express the caller's intent and reduces the chance of calling unintended operations.

If creating a shared generic interface, annotate it with `@NoRepositoryBean` so Spring Data does not try to instantiate a bean for an interface lacking a concrete domain type:

~~~java
@NoRepositoryBean
public interface ReadRepository<T, ID>
        extends Repository<T, ID> {

    Optional<T> findById(ID id);

    List<T> findAll();
}

public interface ProductReadRepository
        extends ReadRepository<Product, Long> {

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

Do not create multiple interfaces just to rename identical methods. Splitting is only valuable when it represents a real responsibility boundary, is clearly used by callers, and is testable.

### 6.1. Applications with multiple Spring Data modules

If the same application uses both JPA and MongoDB, configure repository scanning explicitly. When a domain type carries annotations from multiple stores or the repository base interface is not enough to identify the store, Spring Data may fail to distinguish which module owns a repository.

Packages can be separated:

~~~java
@Configuration
@EnableJpaRepositories(basePackages = "com.example.persistence.jpa")
class JpaRepositoryConfig {
}

@Configuration
@EnableMongoRepositories(basePackages = "com.example.persistence.mongo")
class MongoRepositoryConfig {
}
~~~

This is a configuration example for when an application genuinely uses both corresponding modules; do not add this configuration to a JPA-only project. Ensure packages do not overlap unexpectedly during scanning.

## 7. Verifying choices at compile time and via tests

A repository interface might compile in one version and fail to compile in another due to inheritance changes. Therefore, verifying choices with a small compile check is helpful during upgrades.

Example repository for Spring Data 3.x:

~~~java
public interface ProductRepository
        extends CrudRepository<Product, Long>,
                PagingAndSortingRepository<Product, Long> {

    Optional<Product> findBySku(String sku);
}
~~~

An integration test can verify that the bean is created and query methods work:

~~~java
@DataJpaTest
class ProductRepositoryTest {

    @Autowired
    private ProductRepository products;

    @Test
    void findsProductBySku() {
        Product product = products.save(
                new Product("Keyboard", "KB-01")
        );

        Optional<Product> found = products.findBySku("KB-01");

        assertThat(found).isPresent();
        assertThat(found.orElseThrow().getId()).isEqualTo(product.getId());
    }
}
~~~

This is an illustrative snippet; `Product`'s constructors and properties must match the actual entity in the project. Repository testing should use an appropriate test database, such as H2 for basic checks or Testcontainers when verifying behavior specific to the target database.

Upgrade verification steps:

1. Confirm the resolved Spring Boot and Spring Data versions.
2. Check imports for `javax.persistence` vs. `jakarta.persistence`.
3. Find interfaces extending `PagingAndSortingRepository`.
4. Check call sites invoking `save`, `deleteById`, or other CRUD methods on those repositories.
5. If a 3.x project needs both CRUD and paging, combine `CrudRepository` with `PagingAndSortingRepository` or switch to `JpaRepository`.
6. Compile the entire project and run repository tests.
7. Inspect generated SQL for performance-sensitive queries.

## 8. Sample decisions

| Need | Recommended choice | Reason |
|---|---|---|
| A JPA repository needing CRUD, paging, and JPA operations | `JpaRepository` | Complete feature set, minimal composition needed |
| Read-only lookup by ID and SKU | `Repository` with query methods | Narrow contract, exposes no write/delete operations |
| General CRUD, no JPA-specific APIs needed | `CrudRepository` | Basic method set |
| CRUD returning List on Spring Data 3.x | `ListCrudRepository` | Return types fit callers |
| Standalone paging/sorting on Spring Data 3.x | `PagingAndSortingRepository` | Provides only the paged/sorted read group |
| Multiple optional filter criteria | `JpaSpecificationExecutor` | Dynamic predicate composition |
| Simple search by example entity | `QueryByExampleExecutor` | Minimal query code |
| Fixed JPQL/native SQL query | Query method with `@Query` | Explicit query definition |

## 9. Common mistakes when choosing an interface

- **Extending only PagingAndSortingRepository in Spring Data 3.x while calling save:** add `CrudRepository` or use `JpaRepository`.
- **Using ListCrudRepository in a Spring Data 2.x project:** that interface does not exist in this line; check dependency versions before applying.
- **Choosing JpaRepository for every module even when callers are read-only:** an overly broad contract couples callers to unnecessary operations.
- **Using Page for screens that do not need total result counts:** can trigger unnecessary count queries; consider Slice or bounded List.
- **Using Specification for a very simple query:** a derived query or `@Query` may be easier to read.
- **Upgrading a single Spring Data module manually:** can cause version skew between Commons and JPA; prefer the Spring Boot BOM.
- **Treating a narrow repository as a security boundary:** access permissions must be enforced in services/APIs and the database as required.
- **Using reactive JPA repositories:** JPA is blocking; choose a reactive persistence technology if an end-to-end reactive flow is required.

## 10. Checklist before creating or changing a repository

- [ ] Actual Spring Data version is known.
- [ ] Identified whether callers need read, write, delete, pagination, or dynamic queries.
- [ ] Selected an interface with a just-enough API surface.
- [ ] If using Spring Data 3.x, verified the inheritance hierarchy of PagingAndSortingRepository.
- [ ] Considered ListCrudRepository if List APIs are needed on Spring Data 3.x.
- [ ] Chosen Page, Slice, or List according to display needs.
- [ ] Added JpaSpecificationExecutor only when dynamic criteria are genuinely needed.
- [ ] Checked package scanning if the application uses multiple Spring Data modules.
- [ ] Compiled and ran repository tests after changes.

A good choice is not necessarily the shortest or broadest interface. Let caller needs determine the contract, let dependency versions determine available APIs, and let services manage transactions alongside business rules. For most standard JPA repositories, starting with `JpaRepository<T, ID>` is sensible; narrow down to `Repository`/`CrudRepository` when you want tighter API control, or add executors when specific search needs arise.
