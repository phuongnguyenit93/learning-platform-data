# Probe, Example, and ExampleMatcher Model in Spring Data JPA

Query by Example (QBE) allows finding entities by creating a sample object (probe), populating the properties to search for, and describing how to match them using ExampleMatcher. Spring Data JPA converts the Example into query conditions, enabling applications to build dynamic search filters without writing a separate derived query or JPQL statement for every field combination.

QBE is well suited for search forms with many optional fields and relatively simple conditions. It is especially useful when users only enter a few properties, such as a name starting with a string, an exact email match, and an age equal to a specific value. QBE has limitations: it cannot represent arbitrary nested OR/AND condition groups, cannot match collections/maps, and does not replace Specification or Querydsl for complex queries.

This lesson explains the three components Probe, Example, and ExampleMatcher, how null values are ignored, how primitives are handled, global/per-property matcher configuration, using the fluent API for sorting, pagination, scrolling, and streaming, as well as testing and choosing QBE in real-world applications.

## 1. What components make up Query by Example?

QBE has three components:

1. **Probe:** the domain object populated with the values you want to find.
2. **ExampleMatcher:** specifies how to match, such as AND or OR, exact or substring string matching, which properties to ignore, and whether matching is case-sensitive.
3. **Example:** wraps the probe together with the matcher to pass to the repository.

General flow:

~~~mermaid
flowchart TD
    A[Create probe from entity] --> B[Populate properties to search]
    B --> C[Create ExampleMatcher]
    C --> D[Wrap into Example]
    D --> E[Repository receives Example]
    E --> F[Spring Data JPA creates predicates]
    F --> G[Database returns matching entities]
~~~

Conceptual example: to find people whose firstname starts with "An" and lastname equals "Nguyen", we create a Person probe, set those two properties, and use a matcher configured with STARTING for firstname and EXACT for lastname.

QBE does not require declaring a separate repository method for each combination of conditions. The same repository method can accept many different Examples.

## 2. Creating an entity as a Probe

A probe is usually an instance of the entity managed by the repository. Properties assigned a value become search conditions according to the matcher; null properties are usually ignored by default.

Example Person entity:

~~~java
package com.example.people;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "people")
public class Person {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(length = 100)
    private String firstname;

    @Column(length = 100)
    private String lastname;

    @Column(length = 200)
    private String email;

    private Integer age;

    private Boolean active;

    protected Person() {
    }

    public Person(
            String firstname,
            String lastname,
            String email,
            Integer age,
            Boolean active) {
        this.firstname = firstname;
        this.lastname = lastname;
        this.email = email;
        this.age = age;
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getFirstname() {
        return firstname;
    }

    public void setFirstname(String firstname) {
        this.firstname = firstname;
    }

    public String getLastname() {
        return lastname;
    }

    public void setLastname(String lastname) {
        this.lastname = lastname;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }

    public Boolean getActive() {
        return active;
    }

    public void setActive(Boolean active) {
        this.active = active;
    }
}
~~~

This is the complete entity used for the following examples. A probe does not need to be persisted; it is just a Java object carrying search values. The no-argument constructor is protected so JPA can instantiate the entity, and setters make probe creation in the examples easy to read.

With QBE, populate only the properties the user actually wants to use as criteria. Do not initialize a probe using a constructor that assigns default values to all fields if those values are not search criteria.

## 3. Declaring a repository that supports QBE

Spring Data JPA provides QueryByExampleExecutor. JpaRepository already inherits QBE capabilities, so a regular repository can directly use methods that accept an Example.

~~~java
package com.example.people;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

Commonly used QBE methods include:

| Method | Result |
|---|---|
| findOne(example) | Optional containing at most one entity |
| findAll(example) | Iterable of matching entities |
| findAll(example, sort) | Sorted Iterable |
| findAll(example, pageable) | Page of entities |
| count(example) | Number of matching entities |
| exists(example) | Whether at least one matching entity exists |
| findBy(example, queryFunction) | Query via the fluent API |

If findOne(example) matches multiple entities, Spring Data does not arbitrarily pick one row; it throws an incorrect result size error. Only use findOne when the conditions can identify at most one entity.

## 4. Creating a simple Example

The shortest way is to create a probe and call Example.of():

~~~java
Person probe = new Person();
probe.setFirstname("An");

Example<Person> example = Example.of(probe);

List<Person> people = repository.findAll(example);
~~~

With the default matcher:

- Properties with null values are ignored.
- Properties with values are matched using equality.
- Strings are matched exactly and case-sensitively by default.
- Non-ignored properties are combined using AND.

Therefore, a probe with firstname = "An" and all other properties null means finding a Person whose firstname equals "An".

When you need to change how matching works, pass a matcher to Example.of():

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreCase()
        .withStringMatcher(ExampleMatcher.StringMatcher.CONTAINING);

Example<Person> example = Example.of(probe, matcher);
~~~

This example applies substring matching and case-insensitivity to evaluated string properties, unless a specific property matcher overrides the global configuration.

## 5. matchingAll() and matchingAny()

ExampleMatcher has two ways to combine conditions:

- matchingAll(): every populated criterion must match, equivalent to AND logic.
- matchingAny(): only one populated criterion needs to match, equivalent to OR logic.

Example probe with firstname = "An" and lastname = "Nguyen".

~~~java
Person probe = new Person();
probe.setFirstname("An");
probe.setLastname("Nguyen");

ExampleMatcher allMatcher = ExampleMatcher.matchingAll();
ExampleMatcher anyMatcher = ExampleMatcher.matchingAny();

List<Person> allMatches =
        repository.findAll(Example.of(probe, allMatcher));

List<Person> anyMatches =
        repository.findAll(Example.of(probe, anyMatcher));
~~~

Meaning:

| Matcher | Condition |
|---|---|
| matchingAll() | firstname = 'An' AND lastname = 'Nguyen' |
| matchingAny() | firstname = 'An' OR lastname = 'Nguyen' |

matchingAny() only creates an OR across the properties that have criteria. It cannot create arbitrary logical groups such as:

~~~sql
firstname = 'An'
OR (firstname = 'Binh' AND lastname = 'Nguyen')
~~~

If nested condition groups are needed, use Specification, Criteria API, or Querydsl.

## 6. Ignoring null properties and includeNullValues()

By default, ExampleMatcher ignores null properties in the probe. This is why QBE is well suited for search forms with optional fields.

Example:

~~~java
Person probe = new Person();
probe.setLastname("Tran");
// firstname, email, age, and active remain null.

Example<Person> example = Example.of(probe);
List<Person> people = repository.findAll(example);
~~~

The condition filters only by lastname. Null fields do not generate IS NULL conditions.

If you want to find entities where a property is null, you can use the includeNullValues() matcher:

~~~java
Person probe = new Person();
probe.setEmail(null);

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIncludeNullValues()
        .withIgnorePaths("id", "firstname", "lastname", "age", "active");

Example<Person> example = Example.of(probe, matcher);
List<Person> people = repository.findAll(example);
~~~

This matcher includes non-ignored null properties in the search criteria; in the example, email must be null. The other properties are explicitly ignored so they do not accidentally add extra IS NULL conditions.

Be careful with includeNullValues(): if a probe has many null properties, the matcher may require all of those properties to be null. For entities with many fields, use ignorePaths or create a dedicated probe to express the exact condition needed.

## 7. Primitives and default values can create unintended conditions

Java primitives such as boolean, int, and long cannot hold null. When creating a new probe, they default to false or 0. QBE sees these as real values, so it can use them as search criteria.

For example, if an entity declares:

~~~java
private boolean active;
private int age;
~~~

A new probe will have active = false and age = 0. These two values can become unintended conditions.

There are two ways to handle this:

1. Use wrapper types Boolean and Integer to represent an unset state as null.
2. Use withIgnorePaths("active", "age") when you do not want those fields to participate in the search.

In the Person entity of this lesson, active is Boolean and age is Integer, so a new probe can leave both fields null when filtering by them is not needed. This is why wrapper types are usually more convenient for search models.

Do not confuse null in a probe with false or 0. Null means no criterion is provided by default; false and 0 are specific values.

## 8. withIgnorePaths(): ignoring properties that have values

withIgnorePaths() ignores properties even when the probe has a value set.

~~~java
Person probe = new Person();
probe.setFirstname("An");
probe.setLastname("Nguyen");
probe.setAge(0);

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnorePaths("id", "age");

Example<Person> example = Example.of(probe, matcher);
~~~

In the example, age = 0 does not participate in the search condition. This is useful when a probe is created from a form with default values or when certain entity properties are outside the search scope.

For ID, version, and technical fields, clearly decide whether they are business criteria. To avoid accidentally filtering by unwanted fields, you can explicitly pass them to ignorePaths.

Property path names use Java property names, not database column names. For example, ignore "firstname", not the SQL column name if the column is mapped with @Column(name = ...).

## 9. StringMatcher: string matching modes

ExampleMatcher.StringMatcher specifies the default matching mode for string properties.

| Value | Meaning | Illustrative condition |
|---|---|---|
| EXACT | Exact match | firstname = 'An' |
| STARTING | Starts with string | firstname LIKE 'An%' |
| ENDING | Ends with string | firstname LIKE '%An' |
| CONTAINING | Contains string | firstname LIKE '%An%' |
| DEFAULT | Uses matcher/store default | Depends on matcher configuration |

Example finding firstname starting with "An":

~~~java
Person probe = new Person();
probe.setFirstname("An");

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withStringMatcher(ExampleMatcher.StringMatcher.STARTING);

List<Person> people =
        repository.findAll(Example.of(probe, matcher));
~~~

Example finding a substring:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withStringMatcher(ExampleMatcher.StringMatcher.CONTAINING);
~~~

StringMatcher applies to evaluated string properties. If you want each field to have a different matching mode, use withMatcher() by property path.

REGEX may appear in the matcher API or documentation of some stores, but you should not assume regex is supported the same way across all Spring Data modules and databases. With Spring Data JPA, check the version/provider and use a separate query if true regular expressions are required.

## 10. IgnoreCase: case-insensitive search

You can enable ignore case for all string properties:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreCase();
~~~

Or enable it only for specific properties:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreCase("firstname", "email");
~~~

Example:

~~~java
Person probe = new Person();
probe.setFirstname("an");

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreCase("firstname")
        .withStringMatcher(ExampleMatcher.StringMatcher.STARTING);

List<Person> people =
        repository.findAll(Example.of(probe, matcher));
~~~

Results can match "An", "AN", or "anna" according to the case-insensitive comparison rules executed by the provider/database.

IgnoreCase typically causes the provider to generate expressions similar to LOWER(column) and LOWER(parameter), though the exact SQL depends on Hibernate and the database. Collation, locale, and Vietnamese diacritics can affect results; do not assume ignore case also strips accents. If accent-insensitive search is needed, separate normalization must be designed.

## 11. Per-property matchers

withMatcher() allows configuring a specific property path. This is commonly used when firstname needs prefix matching, lastname needs exact matching, and email needs case-insensitive matching.

~~~java
Person probe = new Person();
probe.setFirstname("An");
probe.setLastname("Nguyen");
probe.setEmail("EXAMPLE.COM");

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withMatcher("firstname",
                property -> property.startsWith().ignoreCase())
        .withMatcher("lastname",
                property -> property.exact().ignoreCase())
        .withMatcher("email",
                property -> property.contains().ignoreCase());

Example<Person> example = Example.of(probe, matcher);
List<Person> people = repository.findAll(example);
~~~

In the example:

- firstname starts with "An", case-insensitive.
- lastname matches "Nguyen" exactly, case-insensitive.
- email contains "EXAMPLE.COM", case-insensitive.

A property matcher overrides the global string matcher configuration for that property. Properties without a specific configuration continue to use the default matcher or global configuration.

The path name must point to a valid property on the probe. If the entity has embedded properties, nested paths can be used according to the mapping, such as address.city. Test the actual paths against your application's mapping and provider.

## 12. PropertyValueTransformer: normalizing probe values

withTransformer() allows transforming a property's value before creating the predicate. For example, trimming leading/trailing whitespace or normalizing letter casing.

~~~java
Person probe = new Person();
probe.setFirstname("  An  ");

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withMatcher("firstname",
                property -> property.startsWith().ignoreCase())
        .withTransformer("firstname",
                value -> value
                        .map(String.class::cast)
                        .map(String::trim)
                        .map(trimmed -> (Object) trimmed));

Example<Person> example = Example.of(probe, matcher);
~~~

The transformer receives an Optional<Object>:

- The Optional has a value when the probe property has a value.
- It can return Optional.empty() to drop the value after transformation.
- It can return an Optional containing the normalized value.
- The transformer only affects how the query is built; it does not modify entities stored in the database.

Do not use transformers to execute complex business logic or call external services. Keep transformations simple, deterministic, and easy to test.

## 13. ExampleMatcher is immutable

ExampleMatcher is designed to be immutable. The with... methods return a new matcher, so you must assign the result back to a variable if you want to keep the configuration.

Correct:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll();
matcher = matcher.withIgnoreCase();
matcher = matcher.withIgnorePaths("id");
~~~

You can also chain calls:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreCase()
        .withIgnorePaths("id", "active")
        .withStringMatcher(ExampleMatcher.StringMatcher.CONTAINING);
~~~

Do not call withIgnoreCase() and ignore the return value:

~~~java
ExampleMatcher matcher = ExampleMatcher.matchingAll();
matcher.withIgnoreCase(); // Does not modify the original matcher.
~~~

Because the matcher is immutable, you can reuse a base configuration to derive new matchers. However, the probe is a mutable Java object; do not modify the probe after creating an Example if you want query conditions to remain stable and easy to reason about.

## 14. Nested properties and QBE limitations

QBE can handle some nested properties, such as properties of embedded objects or singular associations. However, QBE is not a tool for expressing every kind of join and predicate group.

Important limitations:

- Does not support matching collection-valued or map-valued properties as a general QBE criterion.
- Cannot express arbitrary condition groups with nested AND/OR.
- Not suitable for queries requiring complex conditions across multiple collections.
- Has no syntax to express arbitrary greater-than/less-than comparisons on numeric or date/time types using a plain probe.
- String matching is mainly for exact, starts, ends, and contains; do not assume support for all LIKE operators or regex.
- QBE only creates predicates from probe values and the matcher; it is not a full query language like JPQL.

Example suitable for QBE:

~~~text
firstname starts with "An"
AND lastname equals "Nguyen"
AND email contains "example.com"
~~~

Example beyond QBE's natural expressiveness:

~~~text
(age >= 18 AND active = true)
OR (age < 18 AND email IS NOT NULL)
~~~

For the second query, use Specification/Criteria API or Querydsl to build predicates according to business rules.

## 15. findOne, findAll, count, and exists

The repository supports several operations with Example:

~~~java
Person probe = new Person();
probe.setEmail("an@example.com");

Example<Person> example = Example.of(probe);

Optional<Person> one = repository.findOne(example);

List<Person> all = repository.findAll(example);

long count = repository.count(example);

boolean exists = repository.exists(example);
~~~

Meaning:

- findOne() returns an Optional if there is at most one result; if there are multiple results, it throws an incorrect result size error.
- findAll() returns all matching entities.
- count() counts matching entities.
- exists() checks whether at least one matching entity exists.

Do not use findOne() for a non-unique property if business rules allow multiple results. Use findAll() or add genuinely unique conditions.

If you only need to know whether data exists, exists() is clearer than loading the entire list and checking isEmpty().

## 16. Combining QBE with Sort and Pageable

You can pass Sort or Pageable directly:

~~~java
Person probe = new Person();
probe.setLastname("Nguyen");

Example<Person> example = Example.of(probe);

List<Person> sorted = repository.findAll(
        example,
        Sort.by(Sort.Direction.ASC, "firstname")
);

Page<Person> page = repository.findAll(
        example,
        PageRequest.of(
                0,
                20,
                Sort.by(Sort.Direction.ASC, "firstname")
        )
);
~~~

Sort uses Java property names, not physical column names. If deterministic ordering is needed for pagination, add a unique property as a tie-breaker, such as id.

Page provides content, totalElements, and totalPages. Depending on the query, Spring Data may run an additional count query. If the UI only needs to know whether more data follows, consider Slice or a fluent query slice to avoid calculating the total count.

## 17. Fluent Query API with Example

findBy(example, queryFunction) lets you fine-tune how results are fetched without creating extra repository methods. A fluent query can configure sorting, limits, projections, pages, slices, and other ways of reading data.

Example fetching a sorted page:

~~~java
Page<Person> page = repository.findBy(
        example,
        query -> query
                .sortBy(Sort.by("lastname").ascending())
                .page(PageRequest.of(0, 20))
);
~~~

Example fetching the first ordered result:

~~~java
Optional<Person> first = repository.findBy(
        example,
        query -> query
                .sortBy(Sort.by("id").ascending())
                .first()
);
~~~

The fluent query callback must return the result immediately within the findBy() call. Do not store FetchableFluentQuery to use after the callback finishes.

### Projections via fluent query

If you only need certain fields, you can use a projection instead of loading the full entity. Example interface projection:

~~~java
public interface PersonNameView {
    String getFirstname();
    String getLastname();
}
~~~

~~~java
List<PersonNameView> names = repository.findBy(
        example,
        query -> query.as(PersonNameView.class).all()
);
~~~

The projection must be compatible with the properties and projection capabilities of the Spring Data JPA version in use. For complex reports, DTO queries with JPQL may be easier to control.

## 18. Scrolling data with the Scroll API

With Spring Data versions that support the Scroll API and the store module's fluent query, you can use Example together with scroll to read data in Windows instead of loading all results at once.

Example offset-based scrolling:

~~~java
Window<Person> window = repository.findBy(
        example,
        query -> query
                .sortBy(Sort.by("id").ascending())
                .limit(100)
                .scroll(ScrollPosition.offset())
);
~~~

The Window contains up to 100 elements as configured above. If more data remains, you can use the position of the last element in the window as the starting point for the next call:

~~~java
if (!window.isEmpty() && window.hasNext()) {
    ScrollPosition nextPosition =
            window.positionAt(window.size() - 1);

    Window<Person> nextWindow = repository.findBy(
            example,
            query -> query
                    .sortBy(Sort.by("id").ascending())
                    .limit(100)
                    .scroll(nextPosition)
    );
}
~~~

Key points to remember:

- Use a stable sort order; add a unique ID as a tie-breaker.
- Offset scrolling can be expensive when the offset is very large because the database still has to scan past preceding rows.
- Keyset scrolling can be more efficient for large datasets if the sort and conditions are suitable.
- Supported data types and scroll capabilities depend on the Spring Data version, store module, and query shape.
- Check your project version's actual API before using it; if QBE fluent query does not support the required scroll mode, use a repository query or another pagination approach.

The Scroll API is suitable for batch processing, exports, or processing more data than should be loaded into memory at once. It is not a replacement for UI pagination in all cases.

## 19. Streaming QBE results

Fluent queries can also return a Stream:

~~~java
@Transactional(readOnly = true)
public void exportPeople(Example<Person> example) {
    try (Stream<Person> people = repository.findBy(
            example,
            query -> query.stream()
    )) {
        people.forEach(person ->
                System.out.println(person.getFirstname()));
    }
}
~~~

Related imports:

~~~java
import java.util.stream.Stream;
import org.springframework.transaction.annotation.Transactional;
~~~

A Stream can hold database resources/cursors open while iterating, therefore:

- Close the stream using try-with-resources.
- Keep the transaction open throughout the entire read.
- Do not return the Stream out of the service after the transaction has ended.
- Do not assume the stream always loads row-by-row in true streaming fashion; the driver, provider, and fetch size affect behavior.
- If memory bounds are needed, check fetch size configuration and the actual SQL.

Do not use repository.findAll(example).stream() for very large datasets because findAll(example) already loads the entire result set before creating an in-memory Stream.

## 20. Building search filters from requests

QBE is often used for search forms with many optional fields. You can accept a DTO and map it to a probe:

~~~java
public record PersonSearchRequest(
        String firstname,
        String lastname,
        String email
) {
}
~~~

Service:

~~~java
@Service
public class PersonSearchService {

    private final PersonRepository repository;

    public PersonSearchService(PersonRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<Person> search(PersonSearchRequest request) {
        Person probe = new Person();
        probe.setFirstname(request.firstname());
        probe.setLastname(request.lastname());
        probe.setEmail(request.email());

        ExampleMatcher matcher = ExampleMatcher.matchingAll()
                .withIgnorePaths("id", "age", "active")
                .withIgnoreCase("firstname", "lastname", "email")
                .withMatcher("firstname",
                        property -> property.startsWith())
                .withMatcher("lastname",
                        property -> property.contains())
                .withMatcher("email",
                        property -> property.exact());

        return repository.findAll(Example.of(probe, matcher));
    }
}
~~~

The DTO restricts which fields clients are allowed to search on. Do not bind requests directly to an entity probe if the entity has internal fields such as role, status, tenantId, or audit metadata that clients must not control.

If blank strings need to be normalized to null, perform this explicitly in the service layer or DTO validation. Do not automatically treat empty strings, whitespace-only strings, and null as identical unless the API contract specifies so.

## 21. When to choose QBE, Specification, or Querydsl?

| Criterion | Query by Example | Specification/Criteria | Querydsl |
|---|---|---|---|
| Condition construction | Probe + matcher | Predicates in code | Predicates with fluent/type-safe API |
| Optional fields | Very convenient | Flexible | Flexible |
| Simple AND/OR | Yes via matchingAll/Any | Yes | Yes |
| Nested AND/OR groups | Limited | Yes | Yes |
| >, <, between comparisons | Not suitable with basic probe | Yes | Yes |
| Complex collection/exists | Limited | Yes | Yes |
| Readability for simple search forms | High | Medium | Medium |
| Suitability for complex queries | Low | High | High |

Choose QBE when filters are mainly equality and string matching, fields are optional, and complex predicate groups are not needed.

Choose Specification when you need to dynamically compose predicates, numeric/date comparisons, between, joins, or nested conditions while sticking to the Spring Data JPA API.

Choose Querydsl when the project already uses Querydsl and needs type-safe queries with rich structure.

## 22. Testing QBE with @DataJpaTest

Example test using the entity and repository declared above:

~~~java
package com.example.people;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

@DataJpaTest
class PersonRepositoryQbeTest {

    @Autowired
    private PersonRepository repository;

    @Test
    void matchesFirstnamePrefixIgnoringCase() {
        repository.save(new Person(
                "An", "Nguyen", "an@example.com", 25, true));
        repository.save(new Person(
                "Anna", "Tran", "anna@example.com", 30, true));
        repository.save(new Person(
                "Binh", "Nguyen", "binh@example.com", 28, true));

        Person probe = new Person();
        probe.setFirstname("an");

        ExampleMatcher matcher = ExampleMatcher.matchingAll()
                .withMatcher("firstname",
                        property -> property.startsWith().ignoreCase());

        List<Person> result =
                repository.findAll(Example.of(probe, matcher));

        assertThat(result)
                .extracting(Person::getFirstname)
                .containsExactlyInAnyOrder("An", "Anna");
    }

    @Test
    void ignoresNullProbePropertiesByDefault() {
        repository.save(new Person(
                "An", "Nguyen", "an@example.com", 25, true));
        repository.save(new Person(
                "Binh", "Nguyen", "binh@example.com", 28, true));
        repository.save(new Person(
                "Lan", "Tran", "lan@example.com", 24, false));

        Person probe = new Person();
        probe.setLastname("Nguyen");

        List<Person> result =
                repository.findAll(Example.of(probe));

        assertThat(result).hasSize(2);
        assertThat(result)
                .allMatch(person -> "Nguyen".equals(person.getLastname()));
    }

    @Test
    void matchingAnyUsesOrBetweenPopulatedProperties() {
        repository.save(new Person(
                "An", "Tran", "an@example.com", 25, true));
        repository.save(new Person(
                "Binh", "Nguyen", "binh@example.com", 28, true));
        repository.save(new Person(
                "Lan", "Le", "lan@example.com", 24, false));

        Person probe = new Person();
        probe.setFirstname("An");
        probe.setLastname("Nguyen");

        ExampleMatcher matcher = ExampleMatcher.matchingAny();
        List<Person> result =
                repository.findAll(Example.of(probe, matcher));

        assertThat(result).hasSize(2);
    }
}
~~~

The tests verify case-insensitive prefix matching, null being ignored by default, and matchingAny combining with OR. @DataJpaTest typically runs a transaction per test and rolls back after the test finishes.

Add tests for includeNullValues, ignorePaths, primitive defaults, property transformers, and any nested properties your application actually uses. If results depend on collation, functions, or database-specific behavior, run integration tests against the same database engine used in production.

## 23. Common mistakes

| Symptom | Cause | Fix |
|---|---|---|
| New probe does not return expected results | Primitive false/0 accidentally became a criterion | Use wrappers or ignorePaths |
| Null field is not filtered with IS NULL | Null is ignored by default | Use withIncludeNullValues and explicit ignorePaths |
| Results are too narrow | matchingAll combines multiple criteria with AND | Use matchingAny if business logic requires simple OR |
| Results are too broad | matchingAny only needs one criterion to match | Use matchingAll or restrict the probe |
| Searching "An" does not match "Anna" | Default StringMatcher is exact | Use STARTING or CONTAINING |
| IgnoreCase does not strip accents | IgnoreCase only handles letter case | Design separate accent normalization if needed |
| withIgnoreCase has no effect | Ignored the newly returned matcher | Reassign or chain the matcher |
| Transformer is not applied | Wrong property path or incompatible Optional return | Check the path and Optional<Object> type |
| QBE does not filter collections | Collections/maps are not supported as general probe criteria | Use Specification/Querydsl |
| Cannot express condition groups | QBE only supports simple matchingAll/Any | Use Specification or Querydsl |
| findOne throws multiple results error | Probe does not uniquely identify one entity | Use findAll or add unique conditions |
| Stream holds connections open too long | Stream not closed or transaction ended too early | Use try-with-resources inside a transaction |
| Scroll duplicates or skips data | Unstable sort or position not updated properly | Use a sort with a unique key and take the last Window position |

## 24. Practical design principles

- Create probes containing only properties users are allowed to search on.
- Use wrappers for properties that may be left unset.
- Use matchingAll for standard search forms; use matchingAny only when OR across fields matches business requirements.
- Keep null ignored by default; only use includeNullValues when genuinely searching for null columns.
- Configure StringMatcher per property when fields have different requirements.
- Use ignorePaths for IDs, technical statuses, or default values that are not search criteria.
- Keep ExampleMatcher immutable and do not modify the probe after creating the Example.
- Use Page/Slice for UI and Scroll/Stream for large data processing when supported by your version/provider.
- Close Streams and keep the transaction open throughout reading.
- Use Specification or Querydsl when you need predicate groups, ranges, collection joins, or complex conditions.
- Test null behavior, primitives, casing, string matching, and the real target database.

## 25. Self-assessment checklist

- [ ] Can explain Probe, Example, and ExampleMatcher.
- [ ] Can create an Example from an entity probe using Example.of().
- [ ] Can use a repository extending JpaRepository to invoke QBE.
- [ ] Can distinguish matchingAll() and matchingAny().
- [ ] Understand that null is ignored by default.
- [ ] Can use withIncludeNullValues() to find null properties.
- [ ] Can identify the primitive false/0 issue in probes.
- [ ] Can use withIgnorePaths() to ignore properties.
- [ ] Can configure EXACT, STARTING, ENDING, and CONTAINING.
- [ ] Can enable IgnoreCase globally or per property.
- [ ] Can use withMatcher() for individual properties.
- [ ] Can use withTransformer() to normalize probe values.
- [ ] Understand that ExampleMatcher is immutable.
- [ ] Know the limitations with collections, maps, and complex predicate groups.
- [ ] Can use findOne, findAll, count, and exists with the right cardinality.
- [ ] Can combine Example with Sort, Pageable, and fluent queries.
- [ ] Know how to close Streams and use transactions when reading large datasets.
- [ ] Can choose QBE, Specification, or Querydsl based on complexity.
- [ ] Write tests for null, OR/AND, string matchers, and edge cases.

## 26. Conclusion

The probe is the sample entity, Example wraps the probe with a matcher, and ExampleMatcher defines how properties are combined and matched. Spring Data JPA uses these three components to build dynamic queries from supplied values without writing a separate method for every filter combination.

QBE is well suited for simple equality and string searches, especially when many fields can be left blank. Pay attention to nulls, primitive defaults, AND/OR, ignorePaths, and per-property matcher settings. When you need ranges, collection joins, or nested condition groups, switch to Specification or Querydsl. For large result sets, use fluent queries, scroll, or stream depending on version capabilities, always keeping a stable order and managing transactions and resources properly.
