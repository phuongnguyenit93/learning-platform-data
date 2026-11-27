# Role of PagingAndSortingRepository and Inheritance Changes Across Versions

In Spring Data, **PagingAndSortingRepository** is the repository contract for reading data with pagination and sorting. It belongs to Spring Data Commons and can therefore be used with multiple storage modules such as JPA, MongoDB, JDBC, or Redis, depending on what each module supports.

With Spring Data REST, the repository type an application declares affects which operations the REST layer can detect and expose. Consequently, the inheritance change of PagingAndSortingRepository starting in Spring Data 3.0 is a key point to check when upgrading an application.

## 1. What Does PagingAndSortingRepository Provide?

This interface adds two ways to query collections:

- \`findAll(Pageable pageable)\`: retrieves a page of data. The result is \`Page<T>\`, containing the page content along with metadata such as current page number, page size, total elements, and total pages.
- \`findAll(Sort sort)\`: retrieves elements sorted by one or more properties. The result is \`Iterable<T>\`; this method does not provide total page metadata.

\`Pageable\` describes the page to fetch, typically including page index, page size, and optionally sort order. \`Sort\` describes sort order without requiring paginated results.

For example, a repository call can request the first page of 20 records sorted ascending by full name. Each module's repository implementation translates that request into a query suited to the underlying datastore.

This interface defines only pagination and sorting capabilities at the repository layer. It does not define business-specific queries on its own; applications can still add query methods, derived queries, or custom queries supported by the module in use.

## 2. Inheritance Before and Since Spring Data 3.0

This is the most important change to remember when reading or upgrading repositories.

### Spring Data 2.x and Earlier

In versions prior to Spring Data 3.0, PagingAndSortingRepository extended CrudRepository:

~~~java
PagingAndSortingRepository<T, ID>
        extends CrudRepository<T, ID>
        extends Repository<T, ID>
~~~

Therefore, simply declaring:

~~~java
public interface PersonRepository
        extends PagingAndSortingRepository<Person, Long> {
}
~~~

gave the repository both capability groups:

- CRUD from CrudRepository, such as \`save\`, \`findById\`, \`findAll()\`, \`deleteById\`.
- Paging and sorting from PagingAndSortingRepository, such as \`findAll(Pageable)\` and \`findAll(Sort)\`.

Some older codebases therefore declare only PagingAndSortingRepository yet still invoke CRUD methods.

### Spring Data 3.0 Onward

Starting with Spring Data 3.0, PagingAndSortingRepository **no longer extends CrudRepository**. Both interfaces independently extend Repository and represent two distinct capability sets:

~~~java
CrudRepository<T, ID>
        extends Repository<T, ID>

PagingAndSortingRepository<T, ID>
        extends Repository<T, ID>
~~~

If an application needs both CRUD and paging/sorting, explicitly declare both:

~~~java
public interface PersonRepository
        extends CrudRepository<Person, Long>,
                PagingAndSortingRepository<Person, Long> {
}
~~~

If only paging and sorting are needed, you can continue extending only PagingAndSortingRepository. In that case, the repository does not automatically inherit the CRUD methods defined by CrudRepository.

In Spring Data JPA, when you need common JPA repository operations alongside CRUD, paging, and sorting, JpaRepository is often a convenient choice because it combines the necessary contracts for that scenario.

## 3. Impact on Spring Data REST

Spring Data REST relies on repository metadata and methods to generate REST resources. Exposed repository operations are mapped to corresponding HTTP operations depending on export configuration and applied annotations.

### Paging and Sorting on Collection Resources

When a repository provides paging/sorting capabilities, clients can request data via familiar query parameters:

~~~http
GET /people?page=0&size=20&sort=lastName,asc
~~~

Meaning:

- \`page=0\`: requests the first page under default zero-based page numbering.
- \`size=20\`: requests up to 20 elements in the page.
- \`sort=lastName,asc\`: sorts ascending by the \`lastName\` property. Multiple sort criteria can be passed using the syntax supported by Pageable/Spring Data REST.

With a Page result, the REST response can contain page metadata and navigation links such as previous, next, or last page. The exact JSON/HAL shape depends on the configuration and Spring Data REST version.

### CRUD Changes When Upgrading to Spring Data 3.0

Suppose an older repository only declares:

~~~java
public interface PersonRepository
        extends PagingAndSortingRepository<Person, Long> {
}
~~~

In Spring Data 2.x, this repository also extended CrudRepository so CRUD operations were available.

After upgrading to Spring Data 3.0+, the repository only retains the paging/sorting contract. Places in Java code calling \`save\`, \`deleteById\`, \`findById\`, or \`findAll()\` from CrudRepository will no longer be satisfied by this interface. The set of CRUD operations Spring Data REST can detect from the repository may also change accordingly.

If the API must continue supporting paginated reads, sorting, and CRUD, add CrudRepository to the repository declaration. Adding interfaces should accurately reflect business requirements and storage module capabilities.

Note: extending an interface does not mean every method is always publicly exposed. Spring Data REST is also governed by export configuration, \`@RepositoryRestResource\`, \`@RestResource(exported = false)\`, and other repository customizations.

## 4. Examples of Choosing Interfaces

### Paging and Sorting Only

~~~java
public interface ReadOnlyPersonRepository
        extends PagingAndSortingRepository<Person, Long> {
}
~~~

This declaration fits when the repository contract only needs paged or sorted collection queries. It does not provide CRUD via CrudRepository.

### Both CRUD and Paging/Sorting Needed

~~~java
public interface PersonRepository
        extends CrudRepository<Person, Long>,
                PagingAndSortingRepository<Person, Long> {
}
~~~

This is the explicit declaration suited to Spring Data 3.0+ when the application wants to retain both capability groups.

### Spring Data JPA Applications

~~~java
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

JpaRepository fits when the application uses JPA and needs a richer repository API including CRUD, paging, and sorting. For other modules, choose the corresponding interface provided by that module.

## 5. Configuring Page Sizes in Spring Data REST

Spring Boot applications can set a default page size and maximum page size limit for Spring Data REST. For example:

~~~yaml
spring:
  data:
    rest:
      default-page-size: 20
      max-page-size: 100
~~~

These numbers are illustrative configuration values. Choose limits suitable for response payload size, query cost, and client needs. Setting a maximum limit helps prevent requests asking for overly large pages.

## 6. Checklist When Upgrading from Spring Data 2.x to 3.x

1. Find repositories that declare only \`PagingAndSortingRepository\`.
2. Check usages of CRUD methods such as \`save\`, \`delete\`, \`findById\`, and \`findAll()\`.
3. If the repository still needs CRUD, add \`CrudRepository\` or use a module-specific interface like \`JpaRepository\` where appropriate.
4. If the repository only needs paging/sorting, keep the PagingAndSortingRepository contract and do not rely on previously inherited CRUD methods.
5. Re-verify the Spring Data REST API: confirm collection GET supports paging/sorting as needed, and create, update, and delete operations remain exposed as designed.
6. Verify page size, max page size, and annotations controlling repository/method export.

## 7. Key Points to Remember

- PagingAndSortingRepository provides \`findAll(Pageable)\` and \`findAll(Sort)\`.
- Before Spring Data 3.0, PagingAndSortingRepository extended CrudRepository and therefore included CRUD.
- Starting in Spring Data 3.0, the two interfaces are separate and both extend Repository.
- To keep CRUD alongside paging/sorting in Spring Data 3.0+, extend both CrudRepository and PagingAndSortingRepository, or use an appropriate higher-level module interface.
- In Spring Data REST, changing a repository contract can alter exposed operations. Verify both Java methods and HTTP APIs after upgrading.
