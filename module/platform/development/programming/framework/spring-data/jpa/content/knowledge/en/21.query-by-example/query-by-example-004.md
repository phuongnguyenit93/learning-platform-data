# matchingAll, matchingAny, and Per-Property Customization

Spring Data JPA provides **Query by Example (QBE)** to build queries from a sample entity (probe). Instead of writing a repository method for every combination of search criteria, the application creates an object containing the values to search for, configures an **ExampleMatcher**, and passes an **Example** to the repository.

Two key condition-combining strategies are:

- **matchingAll()**: all properties included in the probe must match (AND logic).
- **matchingAny()**: only one of the properties included in the probe needs to match (OR logic).

You can also customize matching rules per property: exact, starts with, ends with, contains, case-insensitive, ignoring fields, or transforming values before matching.

QBE is well suited for search screens with simple, optional conditions. When you need nested logical expressions, value ranges, or complex queries, use Specification, Criteria API, or JPQL.

**Example prerequisites:** the code snippets use Java 17 or later, Spring Boot 3.x, and Spring Data JPA. The application needs **spring-boot-starter-data-jpa**, a JDBC driver, a DataSource, and a matching schema. The snippets are parts of a Spring Boot application, not standalone programs runnable with **javac** alone.

## 1. What is Query by Example?

QBE consists of three components:

1. **Probe**: sample entity containing the values to find.
2. **ExampleMatcher**: rules deciding which properties are evaluated and how they are matched.
3. **Example**: combines the probe and matcher to pass to the repository.

Processing flow:

~~~text
Create probe entity
      |
      v
Configure ExampleMatcher
      |
      v
Example.of(probe, matcher)
      |
      v
repository.findAll(example)
      |
      v
Spring Data builds query conditions
      |
      v
Matching entity results
~~~

For example, if the probe has firstName = "An" and lastName = "Nguyen", QBE can generate an equivalent condition:

~~~sql
WHERE first_name = 'An'
  AND last_name = 'Nguyen'
~~~

The actual SQL syntax is determined by the JPA provider and database. In Java, you work with entity properties without manually writing table or column names.

## 2. Sample entity and repository

We use a Person entity with common searchable properties:

~~~java
package com.example.people.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "people")
public class Person {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String firstName;

    private String lastName;

    private String email;

    private Integer age;

    private Boolean active;

    protected Person() {
    }

    public Person(
            String firstName,
            String lastName,
            String email,
            Integer age,
            Boolean active) {
        this.firstName = firstName;
        this.lastName = lastName;
        this.email = email;
        this.age = age;
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getFirstName() {
        return firstName;
    }

    public String getLastName() {
        return lastName;
    }

    public String getEmail() {
        return email;
    }

    public Integer getAge() {
        return age;
    }

    public Boolean getActive() {
        return active;
    }

    public void setFirstName(String firstName) {
        this.firstName = firstName;
    }

    public void setLastName(String lastName) {
        this.lastName = lastName;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public void setAge(Integer age) {
        this.age = age;
    }

    public void setActive(Boolean active) {
        this.active = active;
    }
}
~~~

Repository:

~~~java
package com.example.people.repository;

import com.example.people.domain.Person;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

**JpaRepository** provides Query by Example operations via **QueryByExampleExecutor**. You do not need to write a separate method for every combination of firstName, lastName, email, or age.

The examples below assume fields are mapped directly as shown in the entity. In real applications, property names in the matcher must match Java property names, even if database column names differ.

## 3. matchingAll(): all conditions must match

**ExampleMatcher.matchingAll()** requires every property included in the probe and not ignored to match. This is the AND strategy.

Example finding people whose firstName starts with "An" and lastName is exactly "Nguyen":

~~~java
Person probe = new Person(null, null, null, null, null);
probe.setFirstName("An");
probe.setLastName("Nguyen");

ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withMatcher(
        "firstName",
        property -> property.startsWith().ignoreCase()
    )
    .withMatcher(
        "lastName",
        property -> property.exact().ignoreCase()
    );

Example<Person> example = Example.of(probe, matcher);

Iterable<Person> people = personRepository.findAll(example);
~~~

Equivalent logical condition:

~~~sql
WHERE LOWER(first_name) LIKE 'an%'
  AND LOWER(last_name) = 'nguyen'
~~~

This is a logical illustration for readability; exact SQL functions, escape characters, and syntax depend on the provider/database.

If no matcher is specified, **matchingAll()** is the default strategy of ExampleMatcher. **ExampleMatcher.matching()** also creates a matcher with the matching-all strategy.

Use matchingAll when search conditions are simultaneous constraints, for example:

- First name starts with a string.
- Last name matches exactly.
- Email contains a keyword.
- Active status equals true.

## 4. matchingAny(): only one condition needs to match

**ExampleMatcher.matchingAny()** combines evaluated properties using OR logic. An entity can be included in results as long as one condition matches.

Example finding people whose firstName contains "an" or whose email is exactly "support@example.test":

~~~java
Person probe = new Person(null, null, null, null, null);
probe.setFirstName("an");
probe.setEmail("support@example.test");

ExampleMatcher matcher = ExampleMatcher.matchingAny()
    .withMatcher(
        "firstName",
        property -> property.contains().ignoreCase()
    )
    .withMatcher(
        "email",
        property -> property.exact().ignoreCase()
    );

Example<Person> example = Example.of(probe, matcher);

Iterable<Person> people = personRepository.findAll(example);
~~~

Equivalent logical condition:

~~~sql
WHERE LOWER(first_name) LIKE '%an%'
   OR LOWER(email) = 'support@example.test'
~~~

With matchingAny, a person with a matching firstName can still be returned even if their email differs from the probe value. Conversely, a person with a matching email is also returned even if their firstName does not contain "an".

### Comparing the two strategies

Suppose a probe has two conditions A and B:

| A matches | B matches | matchingAll (A AND B) | matchingAny (A OR B) |
|---|---|---|---|
| Yes | Yes | Yes | Yes |
| Yes | No | No | Yes |
| No | Yes | No | Yes |
| No | No | No | No |

Key point to remember: matchingAll/matchingAny only combine properties actually included in the criteria. Null properties are ignored by default; thus a null field does not automatically become an IS NULL condition under either strategy.

## 5. Customizing matching for each property

**withMatcher(propertyPath, ...)** allows specifying a custom rule for a property. Common string matching modes:

| Matcher | Meaning | Probe value "spring" |
|---|---|---|
| **exact()** | Exact string match | **spring** |
| **startsWith()** | Starts with | **spring data** |
| **endsWith()** | Ends with | **data spring** |
| **contains()** | Contains substring | **learn spring data** |
| **regex()** | Matches regular expression | Depends on regex |

Example:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withMatcher("firstName", m -> m.startsWith())
    .withMatcher("lastName", m -> m.endsWith())
    .withMatcher("email", m -> m.exact());
~~~

When the probe has firstName = "An", lastName = "Nguyen", and email = "an@example.test", conditions are generated according to each corresponding matcher.

The property name passed to **withMatcher** is the Java property name. If the entity declares:

~~~java
@Column(name = "first_name")
private String firstName;
~~~

then the matcher must use **firstName**, not **first_name**.

Nested property paths can be used if supported by the mapping and provider, such as **address.city**. The path must match the entity property structure.

## 6. Customizing the default matcher and overriding per property

You can set a global string matching mode for all String properties, then override a specific property:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withStringMatcher(
        ExampleMatcher.StringMatcher.CONTAINING
    )
    .withIgnoreCase()
    .withMatcher(
        "email",
        property -> property.exact()
    );
~~~

In the example:

- By default, string properties are matched using substring containment.
- String properties are matched case-insensitively.
- Email specifically uses exact matching instead of substring containment.

Per-property matchers can override the default rule. This lets you define a global rule while still controlling fields that need exact matching.

Common **StringMatcher** values:

- **DEFAULT**: uses the store/provider default behavior.
- **EXACT**: exact match.
- **STARTING**: starts with.
- **ENDING**: ends with.
- **CONTAINING**: contains substring.
- **REGEX**: uses regular expressions if supported by the store.

Do not use regex indiscriminately on large queries. How regex is translated and whether indexes can be used depend on the database/provider.

## 7. Enabling or disabling ignoreCase

By default, string matching is case-sensitive according to the store's default configuration. You can enable case-insensitivity for all String properties:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnoreCase();
~~~

Or enable it only for certain properties:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnoreCase("firstName", "lastName");
~~~

You can also configure it directly inside a property matcher:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withMatcher(
        "email",
        property -> property.exact().ignoreCase()
    );
~~~

Using ignoreCase can cause the provider to generate expressions like LOWER(column). Depending on the database and indexes, this can affect performance. If case-insensitive queries are a frequent requirement, consider an appropriate collation or database functional index and inspect the execution plan.

## 8. Ignoring properties with withIgnorePaths

Because the probe is a full entity, besides search fields it may also contain an ID, creation timestamp, update timestamp, or internal status. If you do not want those fields to participate in the query, use **withIgnorePaths**.

~~~java
Person probe = new Person(null, null, null, null, null);
probe.setFirstName("An");
probe.setActive(true);

ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnorePaths("id", "createdAt", "updatedAt");

Example<Person> example = Example.of(probe, matcher);
~~~

Properties in ignorePaths are excluded from matching conditions even if they have non-null values.

Practical examples:

- An auto-generated ID should not accidentally become a search condition.
- createdAt and updatedAt are usually not search form criteria.
- Audit or technical fields may need to be ignored.

Path names must be Java properties. If an entity does not have createdAt or updatedAt, do not include them in your real application's configuration.

## 9. How are null values handled by default?

By default, QBE ignores null properties in the probe. This fits optional search forms: if the user only enters firstName, the remaining fields do not participate in the query.

~~~java
Person probe = new Person(null, null, null, null, null);
probe.setFirstName("An");

// lastName, email, age, and active are null so they are ignored by default.
Example<Person> example = Example.of(probe);
~~~

If you need to find entities where a property equals SQL NULL, you can enable **withIncludeNullValues()**:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIncludeNullValues()
    .withIgnorePaths("id", "createdAt", "updatedAt");

Example<Person> example = Example.of(probe, matcher);
~~~

When include null values is enabled, null properties are evaluated as null conditions according to QBE/JPA semantics. This can turn many unpopulated fields in the probe into IS NULL conditions. Therefore, it must be combined with ignorePaths or careful probe design.

If the goal is "skip if not entered, search for null if a special option is selected", represent that choice explicitly in the request/criteria and build an appropriate matcher. Do not use an empty probe with include-null as a general search mechanism.

## 10. Notes on primitive types

QBE distinguishes null from actual values. Wrapper types like **Integer** and **Boolean** can be null, making them suitable for optional search criteria.

By contrast, primitives such as **int** and **boolean** always have default values:

- A newly initialized int has value **0**.
- A newly initialized boolean has value **false**.

These values are not null, so they can be treated as unintended search conditions.

For example, if an entity uses:

~~~java
private int age;
private boolean active;
~~~

When a new probe is created, age = 0 and active = false may participate in the query. Ways to handle this:

1. Use **Integer** and **Boolean** if the field may be omitted from search criteria.
2. Or add the primitive fields to **withIgnorePaths** when you do not want them evaluated.
3. Only set primitive values when the user explicitly selects the corresponding criterion.

This is why entities using wrappers are usually easier to use as search probes for optional fields.

## 11. Transforming values before matching

**withTransformer(propertyPath, transformer)** lets you normalize a probe value before generating the query condition.

Example stripping extra whitespace from email:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withMatcher(
        "email",
        property -> property.exact().ignoreCase()
    )
    .withTransformer(
        "email",
        source -> source.map(value -> value.toString().trim())
    );
~~~

If probe.email is **"  AN@example.test  "**, the transformer returns the trimmed value before the matcher builds the condition. The transformer does not mutate the original probe entity; it normalizes the value used for matching.

Transformers can be used for string normalization, formatting, or simple input cleanup. Do not put database queries or complex business logic inside a transformer.

## 12. Using Example with Sort and Pageable

QBE can be combined with sorting and pagination. This is useful when a search form has many optional conditions and results need to be displayed page by page.

Sorting example:

~~~java
Example<Person> example = Example.of(probe, matcher);

Iterable<Person> people = personRepository.findAll(
    example,
    Sort.by(
        Sort.Order.asc("lastName"),
        Sort.Order.asc("firstName"),
        Sort.Order.asc("id")
    )
);
~~~

Pagination example:

~~~java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.asc("lastName"),
        Sort.Order.asc("id")
    )
);

Page<Person> page = personRepository.findAll(example, pageable);
~~~

Pageable uses a 0-based page index. Page returns metadata such as totalElements and totalPages; computing totals may require a count query.

Adding ID as the final sort criterion ensures deterministic ordering when multiple people share the same lastName. The basic QBE executor provides findAll overloads accepting Pageable that return a Page.

## 13. QBE methods available on the repository

Through **QueryByExampleExecutor**, the repository supports common operations:

| Method | Result | Purpose |
|---|---|---|
| **findOne(example)** | Optional | Find at most one result; errors if multiple results exist |
| **findAll(example)** | Iterable | Fetch all matching results |
| **findAll(example, sort)** | Iterable | Fetch sorted results |
| **findAll(example, pageable)** | Page | Fetch paginated results |
| **count(example)** | long | Count matching results |
| **exists(example)** | boolean | Check if any matching result exists |

Example:

~~~java
Example<Person> example = Example.of(probe, matcher);

Optional<Person> one = personRepository.findOne(example);

long total = personRepository.count(example);

boolean found = personRepository.exists(example);
~~~

Only use **findOne** when search criteria guarantee at most one result, such as a unique email. If multiple entities match, the method can throw **IncorrectResultSizeDataAccessException** through Spring Data's translation layer.

## 14. ExampleMatcher is immutable

**ExampleMatcher** is an immutable configuration object. The with... methods return a new matcher instead of mutating the existing instance.

Prefer chaining:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnorePaths("id")
    .withIgnoreCase()
    .withMatcher("firstName", property -> property.startsWith());
~~~

If configuring step by step, reassign the result:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll();

matcher = matcher.withIgnorePaths("id");
matcher = matcher.withIgnoreCase();
~~~

If you call **matcher.withIgnoreCase()** and ignore the return value, the original matcher does not receive the change. This is a common bug when building matchers across multiple statements.

Probes and matchers should also be created fresh per search request. Do not share mutable probes across concurrent requests.

## 15. Limitations of Query by Example

QBE is convenient, but it does not replace every kind of query. Important limitations:

- Does not support arbitrary nested boolean expressions such as (A AND B) OR (C AND D) using matchingAll/matchingAny alone.
- matchingAny only ORs evaluated properties; it cannot create nested OR/AND groups.
- Does not directly support range comparison operators like greater-than, less-than, or between with the flexibility of Specification.
- Not suitable for collection or map criteria.
- Not a tool for writing arbitrary joins or fetch plans.
- Does not express calculations, subqueries, aggregates, or multi-table conditions well.

For example, if you need to find:

~~~text
(age >= 18 AND active = true)
OR
(lastName starts with "Tran" AND email contains "example")
~~~

QBE cannot express this condition group with a single ExampleMatcher alone. Use Specification/Criteria API or JPQL.

### When should you use Specification?

Specification fits when conditions can be dynamically combined with AND/OR and include comparison operators:

~~~java
public static Specification<Person> ageAtLeast(int minimumAge) {
    return (root, query, cb) ->
        cb.greaterThanOrEqualTo(root.get("age"), minimumAge);
}
~~~

Multiple Specifications can be combined with **and()** and **or()**. For queries with complex logic, this is clearer than forcing QBE beyond its scope.

## 16. Testing matchingAll, matchingAny, and property matchers

You can test the repository with **@DataJpaTest**. The example below assumes a test database and schema for Person are configured:

~~~java
@DataJpaTest
class PersonExampleTest {

    @Autowired
    private PersonRepository personRepository;

    @Test
    void matchingAllRequiresEveryIncludedProperty() {
        personRepository.save(
            new Person("An", "Nguyen", "an@example.test", 25, true)
        );
        personRepository.save(
            new Person("An", "Tran", "other@example.test", 30, true)
        );

        Person probe = new Person(null, null, null, null, null);
        probe.setFirstName("An");
        probe.setLastName("Nguyen");

        ExampleMatcher matcher = ExampleMatcher.matchingAll()
            .withIgnoreCase("firstName", "lastName");

        Iterable<Person> result =
            personRepository.findAll(Example.of(probe, matcher));

        assertThat(result).hasSize(1);
        assertThat(result.iterator().next().getLastName())
            .isEqualTo("Nguyen");
    }

    @Test
    void matchingAnyAcceptsEitherIncludedProperty() {
        personRepository.save(
            new Person("An", "Nguyen", "an@example.test", 25, true)
        );
        personRepository.save(
            new Person("Binh", "Tran", "support@example.test", 30, true)
        );

        Person probe = new Person(null, null, null, null, null);
        probe.setFirstName("An");
        probe.setEmail("support@example.test");

        ExampleMatcher matcher = ExampleMatcher.matchingAny()
            .withMatcher("firstName", property -> property.exact())
            .withMatcher("email", property -> property.exact());

        Iterable<Person> result =
            personRepository.findAll(Example.of(probe, matcher));

        assertThat(result).hasSize(2);
    }
}
~~~

In the second test, the first entity matches firstName and the second matches email. Because the matcher is matchingAny, both are returned.

When testing, include data matching one condition, all conditions, and no conditions. Also test case-insensitivity, ignorePaths, null handling, and primitive defaults if the entity has primitive fields.

## 17. Common mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Too few results with matchingAll | All fields populated in the probe must match | Check non-null fields and switch to matchingAny if business rules require it |
| Too many results with matchingAny | Only one field needs to match | Populate only truly needed criteria and choose matchingAll when AND is required |
| Unentered field still participates in query | Primitive with default value used | Use wrappers or ignorePaths |
| Cannot find strings with different casing | ignoreCase not enabled | Use withIgnoreCase or a per-property matcher |
| Substring search only matches exact strings | StringMatcher not configured properly | Use contains/CONTAINING |
| ID accidentally becomes a condition | Probe has non-null ID | Use withIgnorePaths("id") |
| Searching for null values does not work | Null is ignored by default | Use withIncludeNullValues and control other fields |
| Configured matcher has no effect | Ignored the new object returned by with... | Reassign the matcher or chain configuration calls |
| QBE cannot express the condition | Range, nested booleans, or complex joins needed | Use Specification, Criteria, or JPQL |
| Unstable result pages | Sort lacks a unique tie-breaker | Add ID to the end of Sort |

## 18. QBE usage checklist

- [ ] Create a fresh probe for each search request.
- [ ] Populate only the fields the user actually entered.
- [ ] Use matchingAll when every condition must match.
- [ ] Use matchingAny when only one condition needs to match.
- [ ] Use withMatcher to configure exact, startsWith, endsWith, or contains per property.
- [ ] Use withIgnoreCase for fields requiring case-insensitive search.
- [ ] Use withIgnorePaths for ID, audit fields, or non-criteria properties.
- [ ] Understand that null is ignored by default and withIncludeNullValues changes that behavior.
- [ ] Use wrappers instead of primitives for optional search fields.
- [ ] Reassign the return value of with... methods because ExampleMatcher is immutable.
- [ ] Combine Sort/Pageable when sorting or pagination is needed.
- [ ] Use Specification/JPQL when ranges, joins, or nested boolean logic are needed.
- [ ] Test SQL and results across realistic probe combinations.

## 19. Conclusion

**matchingAll()** combines evaluated properties with AND; **matchingAny()** combines them with OR. **withMatcher()** lets you define matching rules per property, while **withIgnoreCase()**, **withIgnorePaths()**, **withIncludeNullValues()**, and **withTransformer()** provide finer control over search behavior.

QBE fits search forms with simple, optional criteria. Build probes explicitly, prevent default primitive values from accidentally entering queries, and control null handling. When you need range conditions, joins, or nested AND/OR groups, switch to Specification or JPQL to keep queries clear and accurate.