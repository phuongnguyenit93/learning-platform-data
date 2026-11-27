# Distinguishing Omitted Filters, IS NULL Filters, and Value Filters

## Objectives

After this lesson, you will be able to:

- Distinguish three input meanings: applying no filter, fetching only records with null values, and filtering by a specific value.
- Explain why SQL uses IS NULL instead of the = NULL comparison.
- Write clear derived query methods for null and non-null cases.
- Recognize the limitations of @Query queries with :parameter IS NULL OR ... conditions.
- Use Specification/Criteria API to add predicates only when filters are provided.
- Design input data types capable of representing all three states.
- Properly test behavior with omitted, null, empty, and concrete parameter values.

## 1. Three states with different meanings

When building a search screen or data-filtering API, a field can carry three meanings:

1. **No filter provided**: the caller does not want to filter by this field. Any value in the database can be returned.
2. **IS NULL filter**: the caller wants records where the column has no value yet.
3. **Value filter**: the caller wants records whose value equals a specific value.

Example with the email property:

| Input | Meaning | Query condition |
|---|---|---|
| No filter provided | Do not restrict by email | Do not add an email predicate |
| Filter provided as null | Only fetch Customers without an email | email IS NULL |
| Filter provided as an@example.com | Only fetch Customers with that email | email = :email |

These three states cannot be safely represented by a single nullable String email variable if the application cannot tell whether null means "filter not sent" or "filter for null values".

### Sample data

Suppose the customers table contains:

| id | full_name | email |
|---:|---|---|
| 1 | An | an@example.com |
| 2 | Bình | NULL |
| 3 | Chi | chi@example.com |
| 4 | Dũng | NULL |

Expected results:

- No email filter passed: returns all 4 customers.
- Email filter is null: returns Bình and Dũng.
- Email filter is an@example.com: returns only An.

If the system treats "not provided" and "null" as identical, users will have no way to search specifically for records missing an email.

## 2. SQL NULL and three-valued logic

In SQL, NULL represents an unknown or missing value. NULL is not the same as an empty string '', the number 0, or boolean false.

SQL uses three-valued logic:

- TRUE
- FALSE
- UNKNOWN

Standard comparisons with NULL yield UNKNOWN:

~~~sql
SELECT *
FROM customers
WHERE email = NULL;
~~~

This query does not return rows with null email, because email = NULL does not evaluate to TRUE. You must use:

~~~sql
SELECT *
FROM customers
WHERE email IS NULL;
~~~

And to fetch rows that have a value:

~~~sql
SELECT *
FROM customers
WHERE email IS NOT NULL;
~~~

If you want to filter by a parameter, use equality when the parameter is guaranteed to be non-null:

~~~sql
SELECT *
FROM customers
WHERE email = :email;
~~~

When :email is bound to null, email = NULL still does not match. Therefore, you must choose the SQL condition based on the filter state before execution.

### NULL is different from empty string

| email | Meaning |
|---|---|
| NULL | No value yet |
| '' | Zero-length string |
| '   ' | String containing whitespace |
| 'an@example.com' | Non-empty string value |

If business logic treats empty or whitespace-only strings as "not entered", normalize on write or write explicit conditions. Do not assume IS NULL also matches empty strings.

## 3. Mapping nullable properties in an Entity

Example Customer entity:

~~~java
package com.example.customer;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false, length = 120)
    private String fullName;

    @Column(name = "email", nullable = true, length = 254)
    private String email;

    protected Customer() {
    }

    public Customer(String fullName, String email) {
        this.fullName = fullName;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public String getEmail() {
        return email;
    }
}
~~~

nullable = true indicates that the email column permits null when schema is generated from the mapping. In production systems, database migrations must still create the column as nullable as required; the annotation alone does not guarantee an existing schema matches.

Do not use primitives for nullable properties. For example, int cannot represent null; use Integer if that value can be absent. Since email is a String, Java null can represent the unset state.

## 4. Derived query methods for IS NULL and IS NOT NULL

Spring Data JPA supports explicit keywords:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    List<Customer> findByEmailIsNull();

    List<Customer> findByEmailIsNotNull();

    List<Customer> findByEmail(String email);
}
~~~

Meaning:

- findByEmailIsNull(): fetches Customers with a null email.
- findByEmailIsNotNull(): fetches Customers with a non-null email.
- findByEmail(value): finds Customers whose email equals the passed value.

With derived equality queries, Spring Data JPA treats a null parameter as an IS NULL condition. Thus, calling findByEmail(null) can be used to find records with null email. However, an explicit method name like findByEmailIsNull() makes intent clearer and prevents readers from mistaking it for skipping the filter.

If you want to support all three states in a single search API, do not simply call findByEmail(email) when email is nullable. When email is null because the request omitted it, that method will search for null emails instead of skipping the condition.

### Combining with other conditions

~~~java
List<Customer> findByStatusAndEmailIsNull(CustomerStatus status);

List<Customer> findByStatusAndEmailIsNotNull(CustomerStatus status);

List<Customer> findByStatusAndEmail(
    CustomerStatus status,
    String email
);
~~~

These methods work well when the set of queries is fixed and easy to express. If filters have many optional states, declaring every method combination quickly becomes unmanageable.

## 5. Why does :email IS NULL OR c.email = :email fail to express all three states?

A common pattern in @Query:

~~~java
@Query("""
    select c
    from Customer c
    where (:email is null or c.email = :email)
    """)
List<Customer> searchByEmailOrAll(@Param("email") String email);
~~~

The query logic is:

- If :email is null, the first branch :email IS NULL is true, so no email filter is applied.
- If :email has a value, the first branch is false and the query compares c.email = :email.

This expresses two states:

1. Null means skip the filter.
2. A concrete value means filter by that value.

It **cannot** express the third state, "filter email IS NULL". When null is passed, the query returns all records instead of only those with a null email.

This is not a syntax error; it is a limitation of how the condition is designed. A single nullable parameter does not carry enough information to distinguish "not supplied" from "supplied with null".

### When is this pattern appropriate?

Use it when the API contract clearly states that null always means ignoring the condition. For example, a simple search screen where users can only type an email or leave it blank not to filter.

If business logic needs to find records with null emails, use a separate method or a filter representation with explicit state.

## 6. Using Specification to represent all three states

For dynamic filters, Spring Data JPA Specification is a clean choice. Specification allows adding predicates conditionally.

### A stateful filter type

Create a data type that represents whether a filter was supplied and its value:

~~~java
package com.example.customer;

public record NullableFilter<T>(boolean supplied, T value) {

    public NullableFilter {
        if (!supplied && value != null) {
            throw new IllegalArgumentException(
                "An omitted filter cannot carry a value"
            );
        }
    }

    public static <T> NullableFilter<T> omitted() {
        return new NullableFilter<>(false, null);
    }

    public static <T> NullableFilter<T> isNull() {
        return new NullableFilter<>(true, null);
    }

    public static <T> NullableFilter<T> equalTo(T value) {
        if (value == null) {
            throw new IllegalArgumentException(
                "Use isNull() to filter for null"
            );
        }
        return new NullableFilter<>(true, value);
    }
}
~~~

Three ways to construct it:

~~~java
NullableFilter<String> anyEmail = NullableFilter.omitted();
NullableFilter<String> missingEmail = NullableFilter.isNull();
NullableFilter<String> exactEmail =
        NullableFilter.equalTo("an@example.com");
~~~

Here:

- supplied = false: do not add a predicate.
- supplied = true and value = null: add IS NULL.
- supplied = true and value is non-null: add equality.

### Specification for Customer

~~~java
package com.example.customer;

import java.util.Objects;

import org.springframework.data.jpa.domain.Specification;

public final class CustomerSpecifications {

    private CustomerSpecifications() {
    }

    public static Specification<Customer> emailMatches(
            NullableFilter<String> filter) {

        Objects.requireNonNull(filter, "filter must not be null");

        return (root, query, criteriaBuilder) -> {
            if (!filter.supplied()) {
                return criteriaBuilder.conjunction();
            }

            if (filter.value() == null) {
                return criteriaBuilder.isNull(root.get("email"));
            }

            return criteriaBuilder.equal(
                root.get("email"),
                filter.value()
            );
        };
    }
}
~~~

criteriaBuilder.conjunction() creates a TRUE condition, equivalent to not restricting results by email. When the filter carries null, isNull() creates an IS NULL predicate. When it carries a value, equal() creates an equality predicate.

### Repository and service

The repository needs to extend JpaSpecificationExecutor:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                JpaSpecificationExecutor<Customer> {
}
~~~

Service:

~~~java
@Service
public class CustomerSearchService {

    private final CustomerRepository repository;

    public CustomerSearchService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<Customer> searchByEmail(NullableFilter<String> emailFilter) {
        return repository.findAll(
            CustomerSpecifications.emailMatches(emailFilter)
        );
    }
}
~~~

Call examples:

~~~java
service.searchByEmail(NullableFilter.omitted()); // Do not filter email
service.searchByEmail(NullableFilter.isNull());  // Email IS NULL
service.searchByEmail(
    NullableFilter.equalTo("an@example.com")
); // Email = value
~~~

This approach scales easily to multiple filters because each filter can build an independent predicate and combine them with AND/OR as required by business rules.

## 7. Combining multiple filters

Suppose a Customer search screen has:

- Email: unfiltered, IS NULL, or equals a value.
- Status: unfiltered or equals an enum.
- Enabled: unfiltered or equals true/false.

You can build a Specification:

~~~java
public static Specification<Customer> search(
        NullableFilter<String> emailFilter,
        NullableFilter<CustomerStatus> statusFilter,
        NullableFilter<Boolean> enabledFilter) {

    return (root, query, cb) -> {
        List<Predicate> predicates = new ArrayList<>();

        if (emailFilter.supplied()) {
            if (emailFilter.value() == null) {
                predicates.add(cb.isNull(root.get("email")));
            } else {
                predicates.add(
                    cb.equal(root.get("email"), emailFilter.value())
                );
            }
        }

        if (statusFilter.supplied()) {
            if (statusFilter.value() == null) {
                predicates.add(cb.isNull(root.get("status")));
            } else {
                predicates.add(
                    cb.equal(root.get("status"), statusFilter.value())
                );
            }
        }

        if (enabledFilter.supplied()) {
            if (enabledFilter.value() == null) {
                predicates.add(cb.isNull(root.get("enabled")));
            } else {
                predicates.add(
                    cb.equal(root.get("enabled"), enabledFilter.value())
                );
            }
        }

        return cb.and(predicates.toArray(Predicate[]::new));
    };
}
~~~

This example assumes the status and enabled fields allow null. If they are declared NOT NULL in the entity/schema, the IS NULL branch will yield no results, though the filter structure still expresses the right semantics. You can extract predicate creation into a helper to avoid duplication as the number of filters grows.

For queries involving multiple associations, sorting, or joins, control duplicate rows and use query.distinct(true) when necessary. When paginating, verify both the count query and actual results.

## 8. Using @Query with explicit state flags

If you want to keep a single static JPQL query, you can pass two extra flags:

- filterEmail: whether to apply the email filter.
- emailIsNull: if the filter is applied, whether to search for null.
- email: concrete value when non-null.

Example:

~~~java
@Query("""
    select c
    from Customer c
    where
        :filterEmail = false
        or (
            :filterEmail = true
            and :emailIsNull = true
            and c.email is null
        )
        or (
            :filterEmail = true
            and :emailIsNull = false
            and c.email = :email
        )
    """)
List<Customer> search(
    @Param("filterEmail") boolean filterEmail,
    @Param("emailIsNull") boolean emailIsNull,
    @Param("email") String email
);
~~~

How to call it:

| Case | filterEmail | emailIsNull | email |
|---|---:|---:|---|
| No filter | false | false | null |
| Email IS NULL | true | true | null |
| Email equals value | true | false | an@example.com |

You must ensure the parameter combination is consistent. For example, when filterEmail = true and emailIsNull = false, email must be non-null. Validate this in the service layer before calling the repository.

This works, but the query becomes verbose with many control parameters. Specification is usually easier to read as the number of filters grows or logic has multiple states.

## 9. Do not confuse absent, null, and empty string at the API layer

A common source of bugs lies in converting HTTP requests/JSON into Java objects.

### Query parameters

Example:

- GET /customers: email is not sent.
- GET /customers?email=an%40example.com: email has a value.
- GET /customers?email=: email is an empty string after decoding, not automatically null.

HTTP query strings have no universal standard syntax for representing JSON null. If you want to search for null emails, the API can provide a dedicated parameter such as emailNull=true, or an explicit endpoint/filter syntax.

Do not automatically convert empty strings to null unless the API contract explicitly specifies it. Doing so can prevent users from searching for valid empty-string values.

### JSON request body

With JSON:

~~~json
{}
~~~

The email field does not appear.

~~~json
{"email": null}
~~~

The email field appears with a null value.

~~~json
{"email": "an@example.com"}
~~~

The email field appears with a concrete value.

A plain Java DTO with only String email cannot distinguish a missing field from a null field after deserialization. If the API needs tri-state semantics, use a type capable of representing field presence, for example:

- A separate boolean such as emailProvided.
- A tri-state wrapper like NullableFilter<String>.
- Jackson JsonNode checking both has("email") and isNull().
- A wrapper library supporting JSON field presence such as JsonNullable<T>, if the project already uses it.

Example with JsonNode:

~~~java
JsonNode body = objectMapper.readTree(requestBody);

if (!body.has("email")) {
    // Filter not supplied
} else if (body.get("email").isNull()) {
    // Filter email IS NULL
} else {
    String email = body.get("email").asText();
    // Filter email by value
}
~~~

If the API is a PATCH updating an entity, the three states have different semantics:

- Field absent: keep the current value.
- Field null: clear the current value.
- Field with value: update to the new value.

These are partial-update semantics and should not automatically share the same semantics as search screens.

## 10. Can Optional<T> solve the three-state problem?

No. Optional<T> only represents having a value or having no value. Optional.empty() does not tell whether the caller wants to skip the filter or search for a null column.

Example:

~~~java
Optional<String> email = Optional.empty();
~~~

You cannot tell from this variable whether the intent is:

- Do not filter email.
- Filter email IS NULL.

Optional.ofNullable(value) also collapses null and missing into the same state. If you need three states, use a filter type with a presence flag or an explicit sealed type/enum.

Another clear model:

~~~java
public sealed interface EmailFilter
        permits AnyEmail, EmailIsNull, EmailEquals {
}

public record AnyEmail() implements EmailFilter {
}

public record EmailIsNull() implements EmailFilter {
}

public record EmailEquals(String value) implements EmailFilter {
    public EmailEquals {
        if (value == null) {
            throw new IllegalArgumentException("value must not be null");
        }
    }
}
~~~

This model expresses intent directly in the type system. Use it when you want to prevent invalid boolean combinations.

## 11. Testing the three states

The repository/service must test all three cases:

~~~java
@DataJpaTest
class CustomerSearchTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void omittedFilterReturnsAllCustomers() {
        CustomerSearchService service =
                new CustomerSearchService(repository);

        List<Customer> result = service.searchByEmail(
            NullableFilter.omitted()
        );

        assertEquals(4, result.size());
    }

    @Test
    void explicitNullReturnsOnlyCustomersWithoutEmail() {
        CustomerSearchService service =
                new CustomerSearchService(repository);

        List<Customer> result = service.searchByEmail(
            NullableFilter.isNull()
        );

        assertEquals(2, result.size());
        assertTrue(result.stream().allMatch(c -> c.getEmail() == null));
    }

    @Test
    void concreteValueReturnsExactMatch() {
        CustomerSearchService service =
                new CustomerSearchService(repository);

        List<Customer> result = service.searchByEmail(
            NullableFilter.equalTo("an@example.com")
        );

        assertEquals(1, result.size());
        assertEquals("An", result.get(0).getFullName());
    }
}
~~~

The test assumes the test database is seeded with the four Customers from the table in Section 1. In a real application, inject the service via the Spring context instead of instantiating it manually if the service has transactions or other dependencies.

Add boundary tests:

- Is an empty string considered a valid value or does it need normalization?
- How are whitespace-only strings handled?
- Are invalidly formatted filter values rejected at the validation layer?
- Are null columns permitted by the schema?
- Do multiple filters combined with AND/OR produce the expected result set?
- Does pagination preserve total counts and sorting?

## 12. Performance and index usage

A query such as:

~~~jpql
where (:email is null or c.email = :email)
~~~

can be convenient because it only needs one method, but the OR expression can make it harder for the database to choose an optimal index plan in some workloads. Effectiveness depends on the database, statistics, parameters, and query planner.

Dynamic Specification adds only the necessary predicates and can generate cleaner SQL:

- No filter: no email condition.
- Null filter: email IS NULL.
- Value filter: email = ?

The database can leverage indexes tailored to each query. For IS NULL filters, index usability depends on the database and index type. Inspect execution plans and measure on production-like data; do not assume one style is always faster.

If email is used frequently for exact lookups, consider an appropriate index. For case-insensitive comparisons, expression indexes/collations and normalization must stay consistent between queries and schema.

## 13. Common errors

| Symptom | Cause | Solution |
|---|---|---|
| Omitted email but only received null-email records | Called findByEmail(null) when null actually meant an absent filter | Track presence; do not add a predicate when the filter is absent |
| Passed null but received all records | Used (:email IS NULL OR ...) where null meant skip filter | Use a dedicated IS NULL or tri-state filter |
| email = NULL returns no results | SQL uses three-valued logic | Use IS NULL |
| Empty strings not found with IS NULL | Empty string differs from database NULL | Define normalization or filter email = '' |
| Optional.empty cannot distinguish intent | Optional only has two states | Use a tri-state wrapper or enum |
| JSON DTO cannot tell missing field from null | Deserializer sets both to Java null | Track field presence or use JsonNode/wrapper |
| Query with many ORs is hard to optimize | Using one query for multiple states | Use Specification and inspect execution plans |
| Filter has null value but service skips it | Service checks value == null and omits predicate | Check the supplied/presence flag as well |
| PATCH unintentionally clears data | Absent field and null field were merged | Use field-presence semantics for partial updates |

## Process for choosing an implementation

1. Define the contract: does null mean skip or match null columns?
2. If only one fixed condition is needed, use a derived method like findByEmailIsNull() or findByEmailIsNotNull().
3. If a nullable parameter only means "do not filter when null", @Query with :email IS NULL OR ... may suffice.
4. If absent, null, and value are all needed, use Specification/Criteria API or a tri-state filter object.
5. At the API layer, preserve field-presence information before converting into a filter.
6. Test all three states, empty strings, multiple filters, and pagination.
7. Check execution plans if queries run against large tables.

## Pre-merge checklist

- [ ] Defined clearly what absent, null, and empty string mean.
- [ ] SQL uses IS NULL/IS NOT NULL instead of = NULL comparisons.
- [ ] Derived query methods have explicit names for null.
- [ ] Do not use a single nullable parameter to represent three states.
- [ ] Optional filter queries are used only when null means skip.
- [ ] Specification adds predicates only when the filter is actually supplied.
- [ ] API preserves the distinction between missing fields and null fields where needed.
- [ ] Optional.empty is not used as a tri-state filter.
- [ ] Integration tests verify all three states.
- [ ] Indexes and execution plans are evaluated under realistic workloads.

## Conclusion

Omitting a filter, filtering for IS NULL, and filtering by a value are three distinct intents. SQL requires IS NULL to check for null; = NULL never evaluates to TRUE. Derived queries can explicitly express null via findByEmailIsNull(), whereas a @Query like (:email IS NULL OR c.email = :email) uses null to mean skipping the filter. When all three states are needed, preserve field-presence information with a filter object and build dynamic predicates via Specification/Criteria API. Separately test absent, null, concrete values, and empty strings to avoid filtering data incorrectly.