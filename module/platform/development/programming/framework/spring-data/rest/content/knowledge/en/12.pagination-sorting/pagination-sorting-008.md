# Sorting Ascending, Descending, and by Multiple Properties with sort

## Objectives

Spring Data REST allows clients to sort collection results using the `sort` query parameter. Clients can choose the property, ascending or descending direction, and combine multiple sort criteria within a single request.

Example:

    GET /customers?sort=lastName,asc

This request reads the customers collection and sorts by lastName ascending. If you need to sort by multiple properties, send multiple sort parameters:

    GET /customers?sort=status,asc&sort=lastName,asc&sort=firstName,desc

Criteria are applied in the order they appear: status first, then lastName, and finally firstName. Later criteria only decide the order among records that have equal values in earlier criteria.

## 1. Structure of the sort Parameter

A sort parameter has the form:

    sort=<property>,<direction>

Where:

- property is a property name of the domain type or a property path supported by the store.
- direction is the sort direction: asc or desc.
- A comma separates the property name and direction.

Examples:

    GET /customers?sort=lastName,asc
    GET /customers?sort=createdAt,desc

If direction is omitted, Spring Data defaults to ASC:

    GET /customers?sort=lastName

You can specify the direction explicitly so requests are easier to read and avoid relying on defaults:

    GET /customers?sort=lastName,asc

The property name must match the property path in the domain model, not necessarily the column name in the database. With JPA, if an entity has a property lastName mapped to column customer_last_name, the sort parameter still uses lastName.

## 2. Ascending and Descending Sorting

### 2.1. ASC — ascending

Use asc to sort from smallest to largest or in ascending lexicographical order depending on the data type:

    GET /customers?sort=lastName,asc

Some examples:

- Numbers: 10, 20, 30.
- Dates/times: oldest timestamp to newest timestamp.
- Strings: comparison order depends on collation and the database.

### 2.2. DESC — descending

Use desc to reverse the sort direction:

    GET /customers?sort=createdAt,desc

Some examples:

- Numbers: 30, 20, 10.
- Dates/times: newest timestamp to oldest timestamp.
- Strings: descending comparison order according to the store's collation.

Sort direction applies individually to each property. When there are multiple criteria, each criterion can use a different direction.

### 2.3. Comparing the Two Directions

| Request | Result |
|---|---|
| sort=price,asc | Lower price first, higher later |
| sort=price,desc | Higher price first, lower later |
| sort=createdAt,asc | Older records first |
| sort=createdAt,desc | Newer records first |
| sort=name,asc | Names in ascending order |
| sort=name,desc | Names in descending order |

String ordering and null-value handling depend on the database, collation, and store configuration. If the API needs specific rules for case sensitivity or nulls, define and test the behavior on the database in use.

## 3. Sorting by Multiple Properties

To sort by multiple properties, repeat the sort query parameter. Each parameter describes an independent criterion.

Example:

    GET /customers?sort=status,asc&sort=lastName,asc&sort=firstName,asc

The database applies the order:

1. status ascending.
2. If two customers have the same status, compare lastName ascending.
3. If both status and lastName are equal, compare firstName ascending.

You can mix ASC and DESC:

    GET /orders?sort=status,asc&sort=createdAt,desc&sort=total,desc

This request sorts status ascending; within each status group, newer orders come first; if creation timestamps are equal, total amount is sorted descending.

### 3.1. Parameter Order Matters

The following two requests can produce different results:

    GET /customers?sort=status,asc&sort=createdAt,desc

    GET /customers?sort=createdAt,desc&sort=status,asc

The first request prioritizes status. The second request prioritizes createdAt. The first criterion carries the highest ordering priority; subsequent criteria only break ties when preceding criteria are equal.

Do not pack multiple properties into an arbitrary single string like:

    sort=status,asc,lastName,desc

Send each criterion as a separate sort parameter so Spring Data parses the structure properly.

### 3.2. Adding ID as the Final Criterion for Stable Ordering

If records can tie across all sort properties, the order between them may be unstable. This causes problems when clients read multiple pages while data changes.

You can add a unique key as the final criterion:

    GET /customers?sort=status,asc&sort=lastName,asc&sort=id,asc&page=0&size=20

ID breaks ties between records sharing the same status and lastName. This makes result ordering more predictable during pagination.

Stable sorting does not create a data snapshot. If records are inserted, deleted, or updated while the client navigates pages, page contents can still change. For strict consistency under continuous write load, consider snapshot or cursor-based pagination at the appropriate API layer.

## 4. Combining Sort with Pagination

Spring Data REST accepts sort together with pagination parameters:

- page: page index, starting from 0.
- size: maximum number of elements in a page.
- sort: one or more sorting criteria.

Example:

    GET /customers?page=0&size=10&sort=lastName,asc&sort=firstName,asc

This request retrieves the first page of up to 10 customers, sorted by lastName then firstName.

Example fetching the next page:

    GET /customers?page=1&size=10&sort=lastName,asc&sort=firstName,asc

When using HAL, the response may contain self, next, and prev links. Follow the links returned by the server to navigate, as those links reflect the actual URL and pagination parameters.

A collection request with sort whose repository does not support a read method accepting Sort or Pageable may fail to apply the expected ordering. Check repository overloads and how Spring Data REST selects the collection method.

## 5. Declaring Repositories That Support Sort

Spring Data provides PagingAndSortingRepository with methods accepting Sort and Pageable.

Starting with Spring Data 3.x, PagingAndSortingRepository no longer extends CrudRepository. If you need both CRUD and paging/sorting, declare both interfaces:

    public interface CustomerRepository
            extends CrudRepository<Customer, Long>,
                    PagingAndSortingRepository<Customer, Long> {
    }

If your project uses JpaRepository, this interface already provides the necessary CRUD, paging, and sorting capabilities:

    public interface CustomerRepository
            extends JpaRepository<Customer, Long> {
    }

Spring Data REST can use the corresponding repository methods to read the collection and apply the ordering created from the sort query parameters.

### 5.1. Domain Type Example

    @Entity
    public class Customer {

        @Id
        @GeneratedValue
        private Long id;

        private String firstName;
        private String lastName;
        private String status;
        private Instant createdAt;
    }

Repository:

    @RepositoryRestResource(path = "customers")
    public interface CustomerRepository
            extends JpaRepository<Customer, Long> {
    }

Valid requests based on the example's properties:

    GET /customers?sort=lastName,asc
    GET /customers?sort=createdAt,desc
    GET /customers?sort=status,asc&sort=createdAt,desc&sort=id,asc

Use Java property names from the domain model. Do not use SQL table or column names unless they happen to match the mapped property path.

## 6. Using Sort in Java Code

If you need to construct a sort in a service or repository call, you can use Spring Data's factory methods:

    Sort sort = Sort.by("lastName").ascending();

Or declare multiple criteria:

    Sort sort = Sort.by(
        Sort.Order.asc("status"),
        Sort.Order.asc("lastName"),
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id")
    );

Using it with a repository:

    List<Customer> customers = customerRepository.findAll(sort);

If you need pagination alongside sorting:

    Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
            Sort.Order.asc("status"),
            Sort.Order.desc("createdAt"),
            Sort.Order.asc("id")
        )
    );

    Page<Customer> page = customerRepository.findAll(pageable);

For REST collections, Spring Data REST automatically constructs Sort or Pageable from query parameters. These Java examples help show how the same structure is represented when calling a repository directly in application code.

## 7. Property Paths and Sorting Nested Properties

Spring Data supports property paths in Sort if the store and mapping can handle that path.

Example where Customer has a relationship to Address:

    @Entity
    public class Customer {

        @ManyToOne
        private Address address;
    }

    @Entity
    public class Address {
        private String city;
    }

You can try sorting by the property path:

    GET /customers?sort=address.city,asc

Requirements:

- address must be a valid property on Customer.
- city must be a valid property on Address.
- The persistence store must support generating a query for that property path.
- The mapping and association must permit the corresponding query.

Not every association or property path is sortable in every store. If the request returns an error, check the mapping and the persistence provider's query logs.

## 8. Sort Limitations and Controls

### 8.1. Non-existent Property

If the client sends a property name that does not exist in the domain model, for example:

    GET /customers?sort=unknownField,asc

Spring Data may report an error when building or executing the query. Verify the Java property name, casing, and property path instead of using a database column name.

### 8.2. Unsuitable Property Types

A property with a complex type or an association unsupported by the store may not be usable as a sort criterion. Only expose properties that the persistence provider can translate into a valid ORDER BY expression.

### 8.3. Business Rules for Sorting

An API may need to restrict which fields clients are allowed to sort by. For example, a Customer list screen might only allow sorting by:

- lastName
- createdAt
- status

If you need an allowlist or role-based sort rules, enforce them at the appropriate API/service layer or custom controller. Do not treat client-supplied property names as a trustworthy business rule.

### 8.4. Nulls and Collation

How nulls are placed first or last and how strings are compared can vary across databases. Some databases support NULLS FIRST or NULLS LAST syntax; direct usability depends on the Spring Data version and store.

If results must be consistent across multiple database environments, define explicit null/collation rules and test on the actual database.

## 9. Reading Responses and Verifying Order

When a collection GET returns HAL JSON, inspect:

- _embedded: the entities on the current page.
- _links.self: the URL of the current request.
- _links.next and _links.prev: pagination links when available.
- page: page metadata.

Abbreviated response example:

    {
      "_links": {
        "self": {
          "href": "http://localhost:8080/customers?sort=lastName,asc&sort=id,asc"
        }
      },
      "_embedded": {
        "customers": [
          { "id": 101, "lastName": "An" },
          { "id": 108, "lastName": "Binh" },
          { "id": 115, "lastName": "Binh" }
        ]
      }
    }

This is an illustrative response only. The relation name and entity properties depend on the domain type and configuration.

To verify sorting works:

1. Create test data with distinct property values as well as duplicate cases.
2. Send a GET with a single sort criterion.
3. Compare the order of property values in the response against the requested direction.
4. Send a request with multiple criteria to verify tie-breaking.
5. Combine page/size and check navigation links.
6. Check SQL or query logs if you need to confirm ORDER BY is pushed down to the database.

## 10. Practice Examples

Suppose Customer has properties status, lastName, firstName, and createdAt.

| Requirement | Request |
|---|---|
| Last name ascending | GET /customers?sort=lastName,asc |
| Newest creation date first | GET /customers?sort=createdAt,desc |
| Status ascending, last name ascending | GET /customers?sort=status,asc&sort=lastName,asc |
| Status ascending, newest creation date first | GET /customers?sort=status,asc&sort=createdAt,desc |
| Last name, first name, then ID ascending | GET /customers?sort=lastName,asc&sort=firstName,asc&sort=id,asc |
| Page 2, 20 items, multi-criteria sort | GET /customers?page=1&size=20&sort=status,asc&sort=createdAt,desc&sort=id,asc |

The requests assume the collection path is /customers and the properties exist in the domain model.

## 11. Common Issues

| Symptom | Cause to Check |
|---|---|
| Results are not in the expected order | Wrong property name or direction |
| Only one criterion is applied | Whether the client sent multiple sort parameters properly |
| Unstable order among duplicate records | Missing a unique tie-breaker criterion such as ID |
| Sort works but pages shift unpredictably | Data changing between requests or unstable sort |
| Request returns property path error | Check property names and association mappings |
| Strings ordered differently than expected | Check database collation and case sensitivity |
| Nulls appear in different positions across environments | Check database null ordering rules |
| sort parameter is ignored | Check whether the repository supports Sort/Pageable and the collection method is exported |

## 12. Checklist

1. Determine the collection URL from the HAL root resource.
2. Verify the repository supports Sort or Pageable.
3. Use Java property names matching the domain model.
4. Choose asc or desc for each criterion.
5. Send each criterion as a separate sort query parameter.
6. Place the highest-priority criterion first.
7. Add ID or a unique property as a tie-breaker when paginating.
8. Combine page and size if pagination is needed.
9. Follow HAL links to navigate between pages.
10. Verify property paths, null ordering, and collation on the actual store.

## References

- [Spring Data REST — Paging and sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html)
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data Commons — Sorting query results](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html)
- [Spring Data Commons — Sort API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Sort.html)
- [Spring Data Commons — Pageable API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Pageable.html)
- [Spring Data JPA — Query methods](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html)