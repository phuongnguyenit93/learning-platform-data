# Repository Hierarchy and Method Contract Changes Across Version Lines

## 1. Why check repositories when upgrading?

Spring Data Repositories are composed from multiple smaller interfaces. Each interface contributes a group of contracts:

- \`Repository<T, ID>\`: marker interface that defines the domain type and key type.
- \`CrudRepository<T, ID>\`: create, read, update, and delete operations.
- \`PagingAndSortingRepository<T, ID>\`: queries with pagination or sorting.
- \`ListCrudRepository<T, ID>\`: CRUD with multi-result methods returning \`List\`.
- \`ListPagingAndSortingRepository<T, ID>\`: sorting and pagination, returning \`List\` for non-paged sorted queries.
- \`JpaRepository<T, ID>\`: combines the contracts above and adds JPA-specific operations.

A change in inheritance relationships can cause an older repository to lose a group of methods even though the interface name still exists. When upgrading, check both the interfaces a repository extends and the return types that callers are using.

The most important change between Spring Data 2.x and 3.x is that \`PagingAndSortingRepository\` no longer extends \`CrudRepository\`. Spring Data 3.0 also added interfaces returning \`List\`. Spring Data 4.x retains this separated model.

## 2. Repository hierarchy in Spring Data 2.x

### 2.1. PagingAndSortingRepository extends CrudRepository

In Spring Data 2.x, the common hierarchy is:

```text
Repository<T, ID>
        |
        v
CrudRepository<T, ID>
        |
        v
PagingAndSortingRepository<T, ID>
```

Because \`PagingAndSortingRepository\` extended \`CrudRepository\`, a repository only needed to declare:

```java
public interface CustomerRepository
        extends PagingAndSortingRepository<Customer, Long> {
}
```

This repository had both groups of methods:

- CRUD: \`save\`, \`saveAll\`, \`findById\`, \`findAll\`, \`deleteById\`, \`delete\`, \`count\`...
- Paging/sorting: \`findAll(Pageable)\`, \`findAll(Sort)\`.

Caller example:

```java
customerRepository.save(customer);

Optional<Customer> customer =
    customerRepository.findById(10L);

Page<Customer> page =
    customerRepository.findAll(PageRequest.of(0, 20));

Iterable<Customer> sorted =
    customerRepository.findAll(Sort.by("name"));
```

Code relying on this inheritance relationship compiles with Spring Data 2.x.

### 2.2. Return contracts of CrudRepository

Multi-result methods in \`CrudRepository\` use \`Iterable\`:

```java
public interface CrudRepository<T, ID> {

    <S extends T> S save(S entity);

    <S extends T> Iterable<S> saveAll(Iterable<S> entities);

    Optional<T> findById(ID id);

    Iterable<T> findAll();

    Iterable<T> findAllById(Iterable<ID> ids);

    long count();

    void deleteById(ID id);
}
```

Single-item methods such as \`findById\`, \`save\`, \`count\`, and \`deleteById\` do not change their meaning just because the repository also has paging/sorting.

### 2.3. Contract of PagingAndSortingRepository

In the 2.x line, this interface adds:

```java
Page<T> findAll(Pageable pageable);

Iterable<T> findAll(Sort sort);
```

- \`Page<T>\` contains page content along with metadata such as total elements and total pages.
- \`Iterable<T>\` contains the sorted entities.
- \`findAll(Sort)\` is not paginated; if the dataset is large, this method may load all results.

## 3. Major change starting in Spring Data 3.0

### 3.1. PagingAndSortingRepository no longer extends CrudRepository

Starting in Spring Data 3.0, \`PagingAndSortingRepository\` is a standalone repository fragment that directly extends \`Repository\`:

```text
                 Repository<T, ID>
                   /          \
                  v            v
       CrudRepository       PagingAndSortingRepository
                  |
                  v
          ListCrudRepository

       PagingAndSortingRepository
                  |
                  v
       ListPagingAndSortingRepository
```

Because the CRUD and paging/sorting branches are separated, the old declaration:

```java
public interface CustomerRepository
        extends PagingAndSortingRepository<Customer, Long> {
}
```

no longer provides \`save()\`, \`findById()\`, \`deleteById()\`, or other CRUD methods in Spring Data 3.x and 4.x. This interface provides only the paging/sorting contract.

This change can break compilation of old code even though the name \`PagingAndSortingRepository\` still exists. Lines such as:

```java
customerRepository.save(customer);
customerRepository.findById(10L);
```

will fail if the variable or bean is declared solely with the type \`PagingAndSortingRepository<Customer, Long>\`.

### 3.2. Combining the two branches after upgrading

If you need the traditional CRUD return type \`Iterable\`, extend both interfaces:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, Long>,
                PagingAndSortingRepository<Customer, Long> {
}
```

If you want multi-result methods to return \`List\`, use the two List interfaces:

```java
public interface CustomerRepository
        extends ListCrudRepository<Customer, Long>,
                ListPagingAndSortingRepository<Customer, Long> {
}
```

There is no need to add both \`CrudRepository\` and \`ListCrudRepository\` in the same declaration. \`ListCrudRepository\` already extends \`CrudRepository\` and overrides the multi-result methods with a \`List\` return type.

### 3.3. Added List interfaces

Spring Data 3.0 introduced the corresponding List interfaces:

| Interface | Multi-result methods |
|---|---|
| \`CrudRepository\` | \`Iterable\` |
| \`ListCrudRepository\` | \`List\` |
| \`PagingAndSortingRepository\` | \`Iterable\` for \`findAll(Sort)\`, \`Page\` for \`findAll(Pageable)\` |
| \`ListPagingAndSortingRepository\` | \`List\` for \`findAll(Sort)\`, \`Page\` for \`findAll(Pageable)\` |

Example \`ListCrudRepository\`:

```java
public interface ListCrudRepository<T, ID>
        extends CrudRepository<T, ID> {

    List<T> findAll();

    List<T> findAllById(Iterable<ID> ids);

    <S extends T> List<S> saveAll(Iterable<S> entities);
}
```

Single-item methods such as \`findById()\`, \`save()\`, \`count()\`, and \`deleteById()\` continue to be inherited from \`CrudRepository\`.

Example \`ListPagingAndSortingRepository\`:

```java
public interface ListPagingAndSortingRepository<T, ID>
        extends PagingAndSortingRepository<T, ID> {

    List<T> findAll(Sort sort);
}
```

Paginated methods still return \`Page<T>\`; the List interface does not turn \`Page<T>\` into \`List<T>\`.

## 4. JpaRepository hierarchy across version lines

### 4.1. JpaRepository in Spring Data JPA 2.x

In Spring Data JPA 2.x, \`JpaRepository\` extended \`PagingAndSortingRepository\` and \`QueryByExampleExecutor\`. Because \`PagingAndSortingRepository\` extended \`CrudRepository\` at that time, \`JpaRepository\` had full CRUD and paging/sorting.

In addition, \`JpaRepository\` redeclared several methods with a \`List\` return type, such as:

- \`List<T> findAll()\`
- \`List<T> findAll(Sort sort)\`
- \`List<T> findAllById(Iterable<ID> ids)\`
- \`List<S> saveAll(Iterable<S> entities)\`

Therefore, callers directly using \`JpaRepository\` in 2.x already received \`List\` for these methods, even though the general \`CrudRepository\` returned \`Iterable\`.

### 4.2. JpaRepository starting in Spring Data JPA 3.x

Starting in 3.0, \`JpaRepository\` directly combines the List interfaces:

```java
@NoRepositoryBean
public interface JpaRepository<T, ID>
        extends ListCrudRepository<T, ID>,
                ListPagingAndSortingRepository<T, ID>,
                QueryByExampleExecutor<T> {
    // JPA-specific methods
}
```

The method groups provided by a JPA repository include:

- Basic CRUD through \`ListCrudRepository\` and \`CrudRepository\`.
- Paging/sorting through \`ListPagingAndSortingRepository\` and \`PagingAndSortingRepository\`.
- Query by Example through \`QueryByExampleExecutor\`.
- JPA-specific operations such as \`flush()\`, \`saveAndFlush()\`, \`saveAllAndFlush()\`, batch delete, and \`getReferenceById()\`.

Because \`JpaRepository\` already combines both branches, a typical declaration remains simple:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
```

This is the right choice for JPA repositories needing CRUD, paging/sorting, and JPA-specific operations.

### 4.3. JpaRepository in Spring Data JPA 4.x

Spring Data JPA 4.x continues to maintain the separated model from 3.0. Current APIs still declare \`JpaRepository\` over \`ListCrudRepository\`, \`ListPagingAndSortingRepository\`, and \`QueryByExampleExecutor\`.

Therefore, the 3.x migration rules still apply in 4.x:

- \`PagingAndSortingRepository\` is independent from CRUD.
- \`ListCrudRepository\` extends \`CrudRepository\`.
- \`ListPagingAndSortingRepository\` extends \`PagingAndSortingRepository\`.
- \`JpaRepository\` combines the contracts needed for JPA.

Do not assume Spring Data 4.x restored the old 2.x inheritance relationship.

### 4.4. Quick comparison table

| Contract | Spring Data 2.x | Spring Data 3.x | Spring Data 4.x |
|---|---|---|---|
| \`PagingAndSortingRepository\` extends CRUD | Yes | No | No |
| \`ListCrudRepository\` | Not available | Yes | Yes |
| \`ListPagingAndSortingRepository\` | Not available | Yes | Yes |
| \`JpaRepository\` has CRUD and paging | Yes | Yes | Yes |
| \`JpaRepository.findAll()\` | \`List<T>\` | \`List<T>\` | \`List<T>\` |
| \`JpaRepository.findAll(Sort)\` | \`List<T>\` | \`List<T>\` | \`List<T>\` |
| \`JpaRepository.findAll(Pageable)\` | \`Page<T>\` | \`Page<T>\` | \`Page<T>\` |
| \`JpaRepository.saveAll(...)\` | \`List<S>\` | \`List<S>\` | \`List<S>\` |

This table describes the synchronous interfaces in Spring Data Commons/JPA. Reactive and coroutine modules have their own corresponding interfaces.

## 5. Return type contracts to understand clearly

### 5.1. Iterable and List

\`Iterable<T>\` is a general contract allowing iteration over results without requiring a list structure. \`List<T>\` additionally provides indexed access and Collection/List operations.

```java
CrudRepository<Customer, Long> crudRepository = ...;

Iterable<Customer> all = crudRepository.findAll();

ListCrudRepository<Customer, Long> listRepository = ...;

List<Customer> list = listRepository.findAll();
```

If the caller only needs to iterate, \`Iterable\` is usually sufficient. If the caller needs indexing or passes results directly into an API accepting \`List\`, use the appropriate List contract.

Do not cast arbitrarily:

```java
List<Customer> customers =
    (List<Customer>) crudRepository.findAll();
```

\`CrudRepository.findAll()\` only promises to return \`Iterable\`; an implementation is not required to return a \`List\` instance. Use \`ListCrudRepository\` or declare the receiving type as \`Iterable\`.

### 5.2. Page and Slice

\`Page<T>\` contains page content along with metadata such as total elements and total pages. Creating a \`Page\` typically requires an additional count query to determine the total result count, depending on Spring Data's optimizations and page content.

\`Slice<T>\` focuses on the content and whether there is a next page; it does not require the total element count across the entire result set.

```java
Page<Customer> page =
    repository.findByStatus(
        CustomerStatus.ACTIVE,
        PageRequest.of(0, 20)
    );

List<Customer> content = page.getContent();
boolean hasNext = page.hasNext();
long total = page.getTotalElements();
```

If an API needs to display the total number of pages, use \`Page<T>\`. If it only needs a "Load more" button, consider \`Slice<T>\` to avoid unnecessary count costs.

### 5.3. Optional and single results

Methods such as \`findById(ID)\` continue to return \`Optional<T>\` across version lines. Optional explicitly represents the case where the entity is not found:

```java
Optional<Customer> customer = repository.findById(id);

customer.ifPresent(this::sendWelcomeMessage);
```

For query methods returning a single entity, Spring Data expects at most one result. If the query returns more than one result, the framework throws an incorrect result size exception.

### 5.4. save and saveAll

The \`save\` contract remains:

```java
<S extends T> S save(S entity);
```

Use the object returned by \`save\` for subsequent operations:

```java
Customer saved = repository.save(customer);

Long id = saved.getId();
```

With JPA, when an entity already exists, the operation may use \`EntityManager.merge()\`. The merged result is the managed instance; it may differ from the passed-in object. Therefore, do not assume \`save(entity)\` always returns the exact same reference.

\`saveAll\` in \`CrudRepository\` returns \`Iterable<S>\`; \`ListCrudRepository\` and \`JpaRepository\` provide the \`List<S>\` contract.

### 5.5. findAllById does not guarantee input order

\`findAllById(ids)\` returns the found entities. If some IDs do not exist, the result may have fewer elements than the input IDs. Result order is not guaranteed to match the order of the passed-in IDs.

If the API requires the exact input order, build a map by ID after querying or use a query with an explicit \`ORDER BY\`.

## 6. JpaRepository methods to watch when upgrading

### 6.1. getOne and getById move to getReferenceById

The methods \`getOne(ID)\` and \`getById(ID)\` are deprecated; the current API recommends \`getReferenceById(ID)\`.

```java
Customer reference = repository.getReferenceById(customerId);
```

This method returns an entity reference. The provider can typically return a proxy without immediately reading the database row; if the ID does not exist, an error may only occur when accessing the proxy's data. Exact behavior depends on the provider.

If you need to verify the entity exists and read data immediately, use:

```java
Customer customer = repository.findById(customerId)
    .orElseThrow(() -> new CustomerNotFoundException(customerId));
```

Do not replace \`findById\` with \`getReferenceById\` if business logic needs to handle non-existence immediately at the call site.

### 6.2. deleteInBatch moves to deleteAllInBatch

\`deleteInBatch(Iterable<T>)\` is deprecated; use \`deleteAllInBatch(Iterable<T>)\`:

```java
repository.deleteAllInBatch(customers);
```

This is a bulk operation. It does not have the same semantics as deleting entities one by one:
- Does not execute cascade semantics like individual JPA entity deletion.
- Does not emit corresponding lifecycle events for each entity.
- The first-level persistence context may become out of sync with the database after the bulk statement.
- Pending changes should be flushed before the operation, and affected entities cleared/refreshed afterward when needed.

If you need cascades, callbacks, or lifecycle events, use the appropriate \`deleteAll(entities)\` instead of batch delete.

### 6.3. saveAndFlush and saveAllAndFlush

These methods have existed since Spring Data JPA 2.5:

```java
Customer saved = repository.saveAndFlush(customer);

List<Customer> savedCustomers =
    repository.saveAllAndFlush(customers);
```

\`flush()\` pushes pending changes in the persistence context to the database. It does not mean committing the transaction. The transaction can still roll back after a flush.

Do not call \`saveAndFlush\` after every \`save\` just to be sure data is persisted. Frequent flushing can reduce batching effectiveness and increase round-trips.

## 7. Impact of hierarchy changes on custom repositories

### 7.1. Repository needing only CRUD

```java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
```

Or using the List contract:

```java
public interface CustomerRepository
        extends ListCrudRepository<Customer, Long> {
}
```

### 7.2. Repository needing only paging/sorting

If a repository only provides paged/sorted reads, it can extend:

```java
public interface CustomerBrowseRepository
        extends PagingAndSortingRepository<Customer, Long> {
}
```

In 3.x/4.x, this interface has no \`save\` or \`delete\`. This can be a good choice when you want to restrict the API of a read-only component.

### 7.3. Repository needing both CRUD and paging/sorting

```java
public interface CustomerRepository
        extends CrudRepository<Customer, Long>,
                PagingAndSortingRepository<Customer, Long> {
}
```

Or the List variant:

```java
public interface CustomerRepository
        extends ListCrudRepository<Customer, Long>,
                ListPagingAndSortingRepository<Customer, Long> {
}
```

### 7.4. Standard JPA repository

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
```

There is no need to additionally declare \`CrudRepository\`, \`PagingAndSortingRepository\`, or the List variants because \`JpaRepository\` already combines them.

### 7.5. Generic base repository

You can create a base interface to share contracts across multiple repositories:

```java
@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends ListCrudRepository<T, ID>,
                ListPagingAndSortingRepository<T, ID> {
}
```

Concrete repository:

```java
public interface CustomerRepository
        extends BaseRepository<Customer, Long> {
}
```

\`@NoRepositoryBean\` prevents Spring Data from attempting to create a bean for the intermediate generic interface when there is no concrete domain type yet.

If the base repository is only for JPA and needs methods like \`flush()\`, it can extend \`JpaRepository<T, ID>\` instead of the two List interfaces above.

## 8. Impact of Java and Jakarta when moving from 2.x to 3.x

The Repository hierarchy change is not the only change in Spring Data 3.0. This is a major platform upgrade. Spring Data 3.x requires Spring Framework 6.x and Java 17+.

| Item | Spring Data JPA 2.7.x | Spring Data JPA 3.x |
|---|---|---|
| Spring Framework | 5.3.x | 6.x |
| Java baseline | Java 8+ depending on version | Java 17+ |
| JPA namespace | \`javax.persistence\` | \`jakarta.persistence\` |
| Jakarta EE | Java EE/Jakarta EE 8 era | Jakarta EE 9+ |
| Hibernate typically paired with Spring Boot | Hibernate 5.x | Hibernate 6.x |

Example entity imports that must change:

```java
// Spring Data JPA 2.x / JPA 2.x
import javax.persistence.Entity;
import javax.persistence.Id;
```

```java
// Spring Data JPA 3.x / Jakarta Persistence
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
```

You cannot keep both namespaces simultaneously for the same entity mapping and expect the provider to convert automatically. Upgrade imports, dependencies, converters, annotations, and JPA integration libraries together.

### 8.1. Spring Data 4.x and Spring Framework 7

Spring Data 4.0 belongs to the Spring Framework 7 generation, on a Jakarta EE 11 and Jakarta Persistence 3.2 foundation. Java 17 remains the baseline of the Framework 7 generation; Java 25 is the newly supported LTS.

With 4.x, check:
- Spring Boot 4.x/Spring Framework 7 compatibility.
- Jakarta Persistence 3.2 and integration libraries.
- JSpecify null-safety annotations in new APIs.
- AOT repository processing if the application uses AOT/native image.
- Deprecated APIs still present in the specific version.

For the repository hierarchy, 4.x retains the separated model from 3.0. There is no need to revert from List interfaces back to 2.x inheritance.

## 9. How to upgrade repositories safely

### 9.1. Inventory interfaces extending PagingAndSortingRepository

Find all declarations of the form:

```java
interface XRepository
        extends PagingAndSortingRepository<X, Long> {
}
```

Classify them:
- Read-only with paging/sorting: can stay as is.
- Needs CRUD: add \`CrudRepository\` or \`ListCrudRepository\`.
- JPA repository needing the full JPA API: consider \`JpaRepository\`.

### 9.2. Check callers relying on inherited CRUD

Find call sites:
- \`save()\`, \`saveAll()\`
- \`findById()\`, \`findAll()\`, \`findAllById()\`
- \`existsById()\`, \`count()\`
- \`delete()\`, \`deleteById()\`, \`deleteAll()\`

If a variable is declared as \`PagingAndSortingRepository\`, CRUD methods will no longer be available from 3.x onwards. Update the declared type or repository interface to match the required contract.

### 9.3. Choose Iterable or List intentionally

If the caller only needs to iterate, \`Iterable\` remains an appropriate contract. If the caller needs indexing, use a List variant or \`JpaRepository\`.

Do not change every interface to List just to avoid loops. An unpaginated query returning hundreds of thousands of rows can still consume significant memory even if the return type is \`List\`.

### 9.4. Replace deprecated methods

Find and handle:
- \`getOne(id)\` → \`getReferenceById(id)\`.
- \`getById(id)\` → \`getReferenceById(id)\`.
- \`deleteInBatch(entities)\` → \`deleteAllInBatch(entities)\`.

After replacing, re-verify semantics:
- A reference may not yet be initialized.
- Batch delete does not run cascades/lifecycle like normal entity deletion.
- Bulk operations can make the persistence context stale.

### 9.5. Align dependencies

Do not upgrade \`spring-data-jpa\` separately while leaving \`spring-data-commons\` on another version line. The two modules are tightly coupled.

For Spring Boot applications:
- Prefer Spring Boot dependency management/BOM.
- Choose a Boot line supporting the desired Spring Data train.
- Only override versions after checking the compatibility matrix.
- Do not mix Spring Framework 5 with Spring Data 3, or Framework 6 with incompatible Jakarta dependencies.

For applications managing dependencies themselves, use the corresponding Spring Data release train BOM so Spring Data modules stay synchronized.

### 9.6. Compatibility baseline and the Spring Boot BOM

When upgrading Spring Data, do not pick individual versions for each library. Spring Boot publishes a set of dependencies tested together via the `spring-boot-dependencies` BOM. For Spring Boot applications, use the BOM of the exact Boot line being run as the version management source for Spring Framework, Spring Data modules, Hibernate ORM, and the Jakarta Persistence API.

The BOM manages dependency versions, but it is not a tool that installs the JDK on the machine. The JDK baseline must follow the Spring Boot/Spring Framework line's requirements and be reflected in Maven compiler configuration or the Gradle Java toolchain. Therefore, treat **Spring Boot release line + BOM + compiler/toolchain configuration** as the application's compatibility baseline.

| Spring Boot line | Spring Framework | Spring Data | Hibernate ORM | Persistence API | JDK baseline |
|---|---|---|---|---|---|
| Boot 2.x | 5.x | 2.x | 5.x | `javax.persistence` | Per minor release; 2.x releases support Java 8+ depending on version |
| Boot 3.x | 6.x | 3.x | 6.x | `jakarta.persistence` 3.1 generation | Java 17+ |
| Boot 4.x | 7.x | 4.x | 7.x generation | `jakarta.persistence` 3.2 generation | Per Boot 4.x system requirements; check supported JDK for exact minor release |

The table above represents the corresponding major generations, not pinned patch versions. Exact module versions must be taken from the BOM of the selected Spring Boot release. Spring Data modules have their own major/minor numbers; for example, `spring-data-jpa` is not required to have the same version number as Spring Boot. The BOM selects modules belonging to the compatible release train.

#### Using the Spring Boot BOM with Maven

If the project can inherit from the Spring Boot parent, use `spring-boot-starter-parent`. This parent imports the dependency management corresponding to the Boot version:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
</dependencies>
```

The example illustrates Spring Boot 3.5 and Java 17. When upgrading, change the Boot version according to the chosen release line and check the minimum JDK of that minor release. Do not add separate versions for `spring-data-jpa`, `spring-data-commons`, `hibernate-core`, or `jakarta.persistence-api` when the BOM already manages them.

If the organization has its own parent POM, you can import the BOM without inheriting the Boot parent:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

In this case, `boot.version` is a project property that must point to a specific Spring Boot release. Keep dependency declarations without versions so the BOM manages them.

#### Using the Spring Boot BOM with Gradle

When using the Spring Boot Gradle plugin alongside the dependency management plugin, the BOM corresponding to the Boot plugin version is imported automatically. Dependencies can be declared without versions:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
}
```

If using Gradle native BOM support, you can declare a platform:

```groovy
dependencies {
    implementation platform("org.springframework.boot:spring-boot-dependencies:${bootVersion}")
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
}
```

Declaring `platform` applies the BOM's constraints to the corresponding configuration. Only use `enforcedPlatform` when you truly want to force versions by the platform and understand its impact on the dependency graph.

#### Why not mix major lines or override arbitrarily?

Do not arbitrarily combine the following components:
- Spring Framework 5 with Spring Data 3 or 4.
- Spring Data 2.x with Spring Framework 6/7 just because it partially compiles.
- Hibernate 5 with the Jakarta Persistence namespace of Boot 3/4.
- Hibernate 6/7 with the old `javax.persistence` JPA dependency.
- Spring Data JPA and Spring Data Commons from two incompatible release trains.

Major lines can change namespaces, method signatures, SPIs, and binary contracts. A dependency graph may compile yet fail when initializing ApplicationContext, creating EntityManagerFactory, scanning repositories, or running queries.

Do not override individual versions just to make Maven/Gradle resolution errors go away. The sequence should be:
1. Choose a Spring Boot release line compatible with your JDK and deployment requirements.
2. Let the Boot BOM manage Spring Framework, Spring Data, Hibernate ORM, and Persistence API.
3. Declare starters/modules without versions if the BOM already manages them.
4. If a newer Spring Data train is needed, use the `spring-data-bom.version` property when the Spring Boot version in use supports that mechanism, then verify compatibility and the effective dependency graph.
5. If a security patch or bugfix is needed, prefer upgrading the Spring Boot patch release. Only override an individual dependency when backed by compatibility evidence from release notes/vendors and covered by thorough tests.

The JDK is not selected as an artifact by the BOM. Set the compiler/toolchain to match the Boot line's baseline and verify both the build JDK and the runtime JDK. A build machine running a newer JDK does not mean the application's bytecode/runtime target is automatically compatible with the production JDK.

#### Inspecting the dependency graph with Maven

Check the running Maven/JDK versions:

```bash
./mvnw -version
java -version
```

Inspect the effective POM after parent, profiles, and BOM are applied:

```bash
./mvnw help:effective-pom
```

Inspect the full dependency tree and conflicted/omitted versions:

```bash
./mvnw dependency:tree -Dverbose
```

Filter dependencies critical to Spring Data JPA:

```bash
./mvnw dependency:tree -Dverbose -Dincludes=org.springframework:*,org.springframework.data:*,org.hibernate.orm:hibernate-core,org.hibernate:hibernate-core,jakarta.persistence:jakarta.persistence-api,javax.persistence:javax.persistence-api
```

Hibernate artifacts on older lines may use the group `org.hibernate`; newer lines typically use `org.hibernate.orm`. Checking both groups helps detect leftover old dependencies during an upgrade.

If the project sets the Java version in a Maven property, you can inspect its value:

```bash
./mvnw help:evaluate -Dexpression=java.version -q -DforceStdout
```

Also check `maven.compiler.release`, `maven.compiler.source`, or the compiler plugin configuration in the effective POM if the project does not use `java.version`.

#### Inspecting the dependency graph with Gradle

Check the Gradle and JDK versions used for the build:

```bash
./gradlew -version
java -version
```

Inspect the full runtime dependency graph:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Use `dependencyInsight` to find why a specific version was selected:

```bash
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-data-jpa --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-data-commons --configuration runtimeClasspath
./gradlew dependencyInsight --dependency hibernate-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jakarta.persistence-api --configuration runtimeClasspath
./gradlew dependencyInsight --dependency javax.persistence-api --configuration runtimeClasspath
```

Check configured Java toolchains:

```bash
./gradlew javaToolchains
```

Read the output to determine whether a version was selected by a BOM, constraint, conflict resolution, or a directly declared dependency. If multiple major generations appear together, trace the dependency path and remove the responsible override or old dependency.

#### Verification after alignment

After fixing dependencies:
- Run compilation to catch incompatible APIs.
- Run unit and integration tests to confirm repositories, EntityManagerFactory, and transactions work.
- Run migrations on a database matching the target vendor/version.
- Inspect the runtime dependency tree, not just the compile classpath.
- Verify the JDK in CI and the runtime image matches the chosen baseline.
- Document the rationale for any approved override so the next upgrade does not accidentally remove it.

Official documentation:
- [Spring Boot — Build Systems and Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html): curated dependency set and BOM.
- [Spring Boot — Maven Plugin Usage](https://docs.spring.io/spring-boot/maven-plugin/using.html): Boot parent, BOM, and managed dependency versions.
- [Spring Boot — Gradle Dependency Management](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html): dependency management plugin, platform, and version overrides.
- [Spring Data — Dependencies and Release Train](https://docs.spring.io/spring-data/commons/reference/dependencies.html): version relationships between Spring Data modules and the Release Train BOM.


## 10. Testing Repository contracts after upgrading

### 10.1. Compilation checks for return types

```java
List<Customer> all = customerRepository.findAll();

List<Customer> byIds =
    customerRepository.findAllById(List.of(1L, 2L));

List<Customer> saved =
    customerRepository.saveAll(customers);

Page<Customer> page =
    customerRepository.findAll(PageRequest.of(0, 20));
```

This example fits when \`customerRepository\` is declared with \`JpaRepository\`, \`ListCrudRepository\` combined with \`ListPagingAndSortingRepository\`, or an interface providing the corresponding return types.

If the repository is declared only with \`CrudRepository\`, the first List variables cannot directly accept methods returning \`Iterable\` without conversion.

### 10.2. Testing repositories with @DataJpaTest

```java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void exposesCrudAndPagingContracts() {
        repository.save(new Customer("anna@example.test"));
        repository.save(new Customer("minh@example.test"));

        List<Customer> all = repository.findAll();

        Page<Customer> firstPage =
            repository.findAll(PageRequest.of(0, 1));

        assertThat(all).hasSize(2);
        assertThat(firstPage.getContent()).hasSize(1);
        assertThat(firstPage.getTotalElements()).isEqualTo(2);
    }
}
```

The test assumes the \`Customer\` entity has a constructor accepting email and the repository extends \`JpaRepository<Customer, Long>\`. Configure an appropriate test database for the project; if queries or migrations depend on vendor-specific SQL, also run integration tests against real PostgreSQL/MySQL.

### 10.3. Verifying batch methods and reference semantics

If code uses \`getReferenceById\`, test both existing and missing ID cases. Do not only assert that the proxy is non-null; accessing a field may be what triggers checking the row.

If code uses \`deleteAllInBatch\`, verify:
- The database deleted the expected rows.
- The persistence context is cleared/refreshed when needed.
- Business rules do not rely on skipped cascades or lifecycle callbacks.

### 10.4. Checking the API a service actually exposes

Sometimes the repository has all methods, but the service receives the bean through an overly narrow interface:

```java
private final PagingAndSortingRepository<Customer, Long> repository;
```

In Spring Data 3.x/4.x, the field above does not provide CRUD. If the service needs \`save()\`, inject an interface reflecting the full contract, such as \`JpaRepository<Customer, Long>\` or a custom interface extending both CRUD and paging.

## 11. Common errors when upgrading

| Symptom | Cause | Resolution |
|---|---|---|
| \`save()\` not found after upgrading to 3.x | Extends only \`PagingAndSortingRepository\` | Add a CRUD interface or switch to \`JpaRepository\` |
| \`findById()\` missing on repository variable | Declared type is only paging/sorting | Declare a type that includes CRUD |
| Cannot assign result to List | Method only guarantees \`Iterable\` | Use a List interface or convert intentionally |
| Caller expects \`findAll(Sort)\` to return List but gets Iterable | Uses general \`PagingAndSortingRepository\` | Use \`ListPagingAndSortingRepository\` or \`JpaRepository\` |
| Code still calls \`getOne()\` or \`getById()\` | Deprecated APIs | Use \`getReferenceById()\` and verify semantics |
| Batch delete leaves in-memory entities out of sync with DB | Bulk delete does not synchronize persistence context | Flush before, clear/refresh afterward |
| Entity not recognized after upgrading to Boot 3 | Imports still use \`javax.persistence\` | Migrate to \`jakarta.persistence\` |
| Missing method/class errors across modules | Spring Data JPA and Commons version skew | Align the release train/BOM |
| Generic repository gets instantiated directly as a bean | Missing \`@NoRepositoryBean\` | Annotate intermediate interfaces |
| Test compiles but paging metadata is wrong | Only checking the content list | Assert Page total, sort, and page boundaries |

## 12. Pre-completion upgrade checklist

- [ ] Identified the exact Spring Data version in use: 2.x, 3.x, or 4.x.
- [ ] Checked the inheritance relationship of \`PagingAndSortingRepository\`.
- [ ] Repositories needing CRUD explicitly declare a CRUD interface on 3.x/4.x.
- [ ] Chose \`Iterable\` or \`List\` according to caller contracts.
- [ ] Confirmed \`JpaRepository\` still provides CRUD and paging/sorting.
- [ ] Checked return types of \`findAll\`, \`findAllById\`, \`saveAll\`, \`findAll(Sort)\`, and \`findAll(Pageable)\`.
- [ ] Replaced \`getOne\`/\`getById\` with \`getReferenceById\` where appropriate.
- [ ] Replaced \`deleteInBatch\` with \`deleteAllInBatch\` and reviewed semantics.
- [ ] Migrated \`javax.persistence\` namespace to \`jakarta.persistence\` when moving to Spring Data 3.x+.
- [ ] Java/Spring Framework/Jakarta Persistence versions are compatible.
- [ ] Spring Data JPA and Spring Data Commons are managed by the same release train.
- [ ] Intermediate generic repositories have \`@NoRepositoryBean\`.
- [ ] Compilation and integration tests pass against the target database.
- [ ] Verified paging metadata, List contracts, transactions, and persistence context after bulk operations.

## 13. Official references

- [Spring Data Commons — Defining Repository Interfaces](https://docs.spring.io/spring-data/commons/reference/repositories/definition.html): how to combine CRUD, paging/sorting, and List repository variants.
- [Spring Data Commons — 2.7 PagingAndSortingRepository API](https://docs.spring.io/spring-data/commons/docs/2.7.x/api/org/springframework/data/repository/PagingAndSortingRepository.html): CRUD inheritance relationship in the 2.x line.
- [Spring Data Commons — ListCrudRepository API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/repository/ListCrudRepository.html): List contract introduced in 3.0.
- [Spring Data Commons — ListPagingAndSortingRepository API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/ListPagingAndSortingRepository.html): List contract for sorted methods.
- [Spring Data JPA — JpaRepository 2.7 API](https://docs.spring.io/spring-data/jpa/docs/2.7.6/api/org/springframework/data/jpa/repository/JpaRepository.html): List methods declared in the 2.x line and JPA-specific methods.
- [Spring Data JPA — JpaRepository 3.0 API](https://www.springframework.org/spring-data/jpa/docs/3.0.12/api/org/springframework/data/jpa/repository/JpaRepository.html): composition from ListCrudRepository and ListPagingAndSortingRepository.
- [Spring Data JPA — JpaRepository 4.1 API](https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/JpaRepository.html): current hierarchy and deprecated methods.
- [Announcing ListCrudRepository and Friends for Spring Data 3.0](https://spring.io/blog/2022/02/22/announcing-listcrudrepository-friends-for-spring-data-3-0/): explains the rationale for separating sorting from CRUD.
- [Spring Data 2025.1 Goes GA](https://spring.io/blog/2025/11/14/spring-data-2025-1-goes-ga/): Spring Framework 7 and Jakarta EE 11 foundation of the 4.0 line.

## 14. Conclusion

In Spring Data 2.x, \`PagingAndSortingRepository\` extended \`CrudRepository\`, so extending paging/sorting alone gave a repository CRUD as well. Starting in Spring Data 3.0, these two groups were separated so they can be flexibly combined with the new List interfaces. Repositories needing both must declare both CRUD and paging/sorting; \`ListCrudRepository\` and \`ListPagingAndSortingRepository\` are the choices when List return types are desired.

\`JpaRepository\` remains the complete option for JPA. In 2.x, it extended \`PagingAndSortingRepository\` and redeclared several methods returning List. From 3.x onward and in 4.x, it directly combines \`ListCrudRepository\` and \`ListPagingAndSortingRepository\`. Therefore, standard JPA repositories extending \`JpaRepository\` do not need redundant CRUD/paging interfaces added.

When upgrading, check the repository types services accept, the methods callers use, and actual return types. Replace deprecated APIs such as \`getOne\`, \`getById\`, and \`deleteInBatch\` after verifying semantics. When moving from 2.x to 3.x, update the Java baseline and migrate the \`javax.persistence\` namespace to \`jakarta.persistence\`; when moving to 4.x, align Spring Framework 7/Jakarta EE 11 and check additional AOT/null-safety changes. Finally, let the Spring Boot BOM or Spring Data release train manage modules consistently and verify with compilation tests and integration tests against the target database.
