# Limitations on Grouped Conditions, Relationships, and Complex Queries

## 1. What kinds of queries is Query by Example suited for?

Spring Data JPA Query by Example (QBE) builds query conditions from a sample object, called a **probe**. Populated properties in the probe are used to find Entities with matching corresponding properties. QBE is well suited for simple search forms where users enter a few optional fields such as name, email, status, or city.

QBE reduces the need to create many repository methods for simple filter combinations. However, a probe is not a full query expression language. QBE has clear limitations regarding how conditions are combined, comparison operators, collections, and complex relationships. When requirements exceed those limits, switch to Specification, Querydsl, JPQL, or a custom repository.

## 2. Three components of QBE

QBE has three components:

- **Probe:** an object holding sample values to search for. Usually a newly instantiated Entity with only the fields to filter on populated.
- **ExampleMatcher:** specifies how to match, such as AND or OR, string handling, ignore case, ignored properties, or null handling.
- **Example:** combines the probe and matcher to pass to the repository.

Repository example:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
}
```

`JpaRepository` provides Query by Example operations via `QueryByExampleExecutor`, such as `findOne`, `findAll`, `count`, and `exists` accepting an `Example`.

## 3. Creating a probe and ExampleMatcher

Suppose the `Customer` Entity has `id`, `firstName`, `lastName`, `email`, `status`, and `createdAt`. You can create a probe to search by name and status:

```java
Customer probe = new Customer();
probe.setFirstName("Lan");
probe.setStatus(CustomerStatus.ACTIVE);

ExampleMatcher matcher = ExampleMatcher.matching()
    .withIgnorePaths("id", "createdAt")
    .withMatcher(
        "firstName",
        ExampleMatcher.GenericPropertyMatchers.startsWith().ignoreCase()
    );

Example<Customer> example = Example.of(probe, matcher);
List<Customer> customers = customerRepository.findAll(example);
```

This illustrative snippet requires the corresponding Entity and enum. `matching()` combines properties included in the probe with AND by default. `firstName` is matched by prefix case-insensitively; `status` is matched by its exact value.

`withIgnorePaths` excludes properties from conditions, which is useful when the probe comes from an object with an ID or technical values that should not participate in searching. Names in the matcher are Java property names, not physical column names.

## 4. Null is ignored by default

QBE ignores null properties in the probe by default. Example:

```java
Customer probe = new Customer();
probe.setFirstName("Lan");
probe.setEmail(null);
```

With the default matcher, the search condition uses only `firstName`; `email = null` is not automatically added to the query. This is convenient behavior for search forms with many optional fields.

If you need to match null properties, you can use `withIncludeNullValues()`. Null properties are then included in conditions per store semantics, typically corresponding to IS NULL checks. Weigh this carefully because a probe with many null fields can create unintended null conditions. Combine with `withIgnorePaths` to exclude properties that should not participate.

## 5. Be careful with primitive types in probes

Primitive properties such as `int`, `long`, or `boolean` always have default values in Java: `0`, `0L`, or `false`. QBE cannot distinguish those default values from values the user genuinely wants to search for.

For example, if `Customer` has `int age`, a new probe may carry `age = 0` and QBE may include an age condition in the query. If the form did not enter an age, this can produce wrong results.

For optional search fields, prefer wrapper types such as `Integer`, `Long`, and `Boolean` to represent null when no value is provided. If the Entity must use primitives, you can add the property to `withIgnorePaths("age")` when that filter is not supplied.

## 6. matchingAll and matchingAny

QBE supports two overall condition-combining modes:

| Matcher | Combining logic |
| --- | --- |
| `ExampleMatcher.matching()` or `matchingAll()` | All properties included in the probe must match (AND) |
| `ExampleMatcher.matchingAny()` | Only one property included in the probe needs to match (OR) |

Example finding customers whose first name or email contains a keyword:

```java
Customer probe = new Customer();
probe.setFirstName("an");
probe.setEmail("an");

ExampleMatcher matcher = ExampleMatcher.matchingAny()
    .withMatcher(
        "firstName",
        ExampleMatcher.GenericPropertyMatchers.contains().ignoreCase()
    )
    .withMatcher(
        "email",
        ExampleMatcher.GenericPropertyMatchers.contains().ignoreCase()
    );

Example<Customer> example = Example.of(probe, matcher);
List<Customer> matches = customerRepository.findAll(example);
```

The logic here is `firstName CONTAINS 'an' OR email CONTAINS 'an'`. `matchingAny()` applies OR across all selected properties; it does not let you define arbitrary nested AND/OR groups.

## 7. QBE cannot express arbitrary grouped conditions

The most important limitation is that QBE does not support grouped/nested predicates. For example, business rules require:

```text
status = ACTIVE
AND
(firstName = 'Lan' OR lastName = 'Tran')
```

This is the expression `A AND (B OR C)`. QBE only provides the global choice of matchingAll or matchingAny; there is no probe/matcher API to form parenthesized groups like the one above.

Similarly, the following expression cannot be described directly with a single ExampleMatcher:

```text
firstName = 'Lan'
OR
(firstName = 'Linh' AND lastName = 'Tran')
```

Do not try to simulate grouped expressions by creating multiple probes and merging results in Java when datasets are large or paginated. That approach easily causes extra load, duplicate IDs, wrong counts, and wrong ordering. Let the database execute grouping logic using Specification, Querydsl, or JPQL.

## 8. Limitations on comparison operators

QBE mainly supports value-equality matching and several string matching modes. For String, `ExampleMatcher.StringMatcher` provides modes such as:

| String matcher | Meaning |
| --- | --- |
| `EXACT` | String must match exactly |
| `STARTING` | Starts with probe string |
| `ENDING` | Ends with probe string |
| `CONTAINING` | Contains probe string |
| `REGEX` | Matches regular expression, depending on store support |

QBE does not provide a general DSL to express numeric/date conditions such as:

- `age > 18` or `price >= 100`.
- `createdAt BETWEEN from AND to`.
- `score < threshold`.
- `status IN (A, B, C)` as an arbitrary collection operator.
- Comparing two properties against each other or writing arbitrary functions on columns.

Do not use probe values to implicitly mean `greater than` or `between`. For range, list, comparison, or function conditions, use an appropriate query tool.

## 9. QBE with singular relationships and nested properties

QBE can traverse nested property paths, including properties of embedded objects or singular relationships when mapping allows. For example, `Customer` has an embedded `Address`:

```java
@Embeddable
public class Address {
    private String city;
    private String postalCode;
}
```

```java
@Entity
public class Customer {
    @Id
    private Long id;

    private String firstName;

    @Embedded
    private Address address;
}
```

Creating a probe with only city set:

```java
Customer probe = new Customer();
Address address = new Address();
address.setCity("Da Nang");
probe.setAddress(address);

ExampleMatcher matcher = ExampleMatcher.matching()
    .withIgnorePaths("id", "firstName");

Example<Customer> example = Example.of(probe, matcher);
List<Customer> result = customerRepository.findAll(example);
```

The matcher uses only `address.city` which has a value; null `address.postalCode` is ignored by default. You can explicitly ignore individual nested properties using dot paths like `address.postalCode` if needed.

For singular relationships like ManyToOne, you can construct a nested probe for properties of the related Entity, such as `customer.accountManager.email`, if that path is a valid persistent property. The query provider will generate the necessary path/join. Inspect the SQL and test null-association cases, because relationship path semantics and join types can affect result sets.

QBE is not suitable for filtering across collection associations such as `orders.items` or ManyToMany. Collections and maps are not supported for property matching in QBE. For conditions based on collection elements, use EXISTS/JOIN in Specification, Querydsl, or JPQL.

## 10. Complex relationships and conditions on child collections

Suppose you need to find Customers who have at least one order in PAID status. This is an existence condition on the `orders` collection. A probe cannot express conditions on a collection element using a normal nested object.

With Specification, you can create explicit joins and predicates:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                JpaSpecificationExecutor<Customer> {
}
```

```java
Specification<Customer> hasPaidOrder = (root, query, cb) -> {
    Join<Customer, PurchaseOrder> order = root.join("orders");
    query.distinct(true);
    return cb.equal(order.get("status"), OrderStatus.PAID);
};

List<Customer> customers = customerRepository.findAll(hasPaidOrder);
```

This is an illustrative snippet; import `Join`, `Specification`, and the corresponding domain types. `distinct(true)` eliminates duplicate Customers when one customer has multiple PAID orders. If using `Page`, check the count query so unique Customers are counted. When you only need to check if a matching order exists, an EXISTS subquery can avoid multiplying root rows.

## 11. Using Specification for grouped conditions

Specification built on JPA Criteria API lets you construct arbitrary AND/OR predicates:

```java
Specification<Customer> spec = (root, query, cb) -> cb.and(
    cb.equal(root.get("status"), CustomerStatus.ACTIVE),
    cb.or(
        cb.equal(root.get("firstName"), "Lan"),
        cb.equal(root.get("lastName"), "Tran")
    )
);

List<Customer> result = customerRepository.findAll(spec);
```

This expression accurately represents `status = ACTIVE AND (firstName = Lan OR lastName = Tran)`. Small Specifications can be composed for reuse:

```java
Specification<Customer> active =
    (root, query, cb) -> cb.equal(root.get("status"), CustomerStatus.ACTIVE);

Specification<Customer> nameMatches =
    (root, query, cb) -> cb.or(
        cb.equal(root.get("firstName"), "Lan"),
        cb.equal(root.get("lastName"), "Tran")
    );

Specification<Customer> combined = active.and(nameMatches);
```

Specification fits when dynamic conditions combine multiple logic groups, optional filters, and joins. For queries with heavy aggregation, projections, or database-specific SQL, consider Querydsl, JPQL, or a custom repository.

## 12. Using @Query when logic is static and clear

If grouping conditions are fixed, JPQL can express them directly:

```java
@Query("""
    select c
    from Customer c
    where c.status = :status
      and (c.firstName = :firstName or c.lastName = :lastName)
    """)
List<Customer> searchByStatusAndEitherName(
    @Param("status") CustomerStatus status,
    @Param("firstName") String firstName,
    @Param("lastName") String lastName
);
```

JPQL uses entity names and Java properties. If collection filtering is needed, use JOIN or EXISTS; if using a to-many JOIN and returning the root entity, consider `distinct` to avoid duplicate Entities. With Page, declare an appropriate count query when the query uses joins, distinct, or grouping.

## 13. When to choose QBE, Specification, Querydsl, or @Query?

| Requirement | Suitable tool |
| --- | --- |
| Search form with many optional fields, mainly exact/string matching | Query by Example |
| Nested AND/OR, arbitrary condition groups | Specification or Querydsl |
| `>`, `<`, BETWEEN, IN comparisons, or varied dynamic conditions | Specification or Querydsl |
| Filtering across collections/to-many relationships | EXISTS/JOIN via Specification, Querydsl, or JPQL |
| Static query with clear, rarely changing logic | `@Query` JPQL |
| CTEs, window functions, or database-specific features | Native SQL/custom repository |

There is no need to replace QBE if a form only has simple optional fields and global AND/OR suffices. Switch tools when QBE's limitations force workarounds or make results hard to reason about.

## 14. Performance and pagination with QBE

QBE still generates database queries; it does not filter all data in Java. Performance depends on generated conditions, indexes, data volume, joins, and execution plans.

- Populate only the properties genuinely needed for filtering in the probe.
- Use `withIgnorePaths` to exclude IDs, timestamps, or default primitive values that are not search criteria.
- Be cautious with `matchingAny()` because OR across multiple columns can be harder to index than AND depending on the database and data.
- For nested properties, inspect the SQL for unexpected joins.
- With `Page<T>`, Spring Data may run an extra count query; check total counts and the count query.
- Do not fetch all results and filter in Java streams when the database can apply predicates.

QBE can be combined with `Sort` or `Pageable`:

```java
Page<Customer> page = customerRepository.findAll(
    example,
    PageRequest.of(0, 20, Sort.by("lastName").ascending())
);
```

Sort uses valid Java domain properties, not physical column names. If the query involves associations or complex conditions, inspect the SQL and count query on the target database.

## 15. Common mistakes and diagnosis

**Too few results because a field defaults to 0 or false.** Check primitives in the probe; use nullable wrappers or add the property to `withIgnorePaths`.

**Want to find null properties but get no results.** Null is ignored by default. Use `withIncludeNullValues()` when null matching is needed and ignore unrelated properties.

**matchingAny returns too many results.** `matchingAny()` ORs every property included in the probe. If grouped logic is needed, switch to Specification/Querydsl.

**Cannot express `A AND (B OR C)`.** QBE only has global matchingAll/matchingAny, without nested predicate groups.

**Need to filter greater-than age or date ranges.** QBE has no general comparison operators; use Specification, Querydsl, or JPQL.

**Cannot filter collections or child records.** QBE does not support collection/map matching. Use EXISTS/JOIN in an appropriate query.

**Nested associations make queries slow or miss results.** Check property paths, null associations, SQL joins, and indexes; consider writing an explicit query.

**Count or Page has duplicate results.** To-many joins can multiply root rows; use distinct/EXISTS and a count query that counts distinct roots.

## 16. Checklist before choosing Query by Example

- Can the probe express conditions primarily via exact values or string matching?
- Does the overall logic only need global AND or OR, or does it need arbitrary parenthesized groups?
- Are `>`, `<`, BETWEEN, IN, functions, or subqueries required?
- Do you need to filter across collections/maps or multiple to-many relationships?
- Do any primitives in the probe have default values causing unintended filters?
- Should nulls be ignored or match IS NULL?
- Are nested properties valid and are generated joins appropriate?
- If paginating, are the count query and root distinctness accurate?
- If exceeding QBE limits, can Specification, Querydsl, or @Query express it more clearly?

Query by Example is a concise choice for probe-based search with simple conditions. It does not replace a general-purpose query language: there are no nested AND/OR groups, arbitrary comparison operators, or collection/map filtering. Recognizing these limits early helps you pick the right tool and keep queries readable, accurate, and easy to optimize.