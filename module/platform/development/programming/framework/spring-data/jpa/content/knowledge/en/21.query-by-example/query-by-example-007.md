# Flexible Execution with QueryByExampleExecutor Fluent Queries

Query by Example (QBE) builds search conditions from a sample object (probe) and an ExampleMatcher. When a Repository extends QueryByExampleExecutor, the application can call findBy() to execute an Example using a fluent query. A fluent query allows customizing how results are retrieved right at the call site: sorting, limiting row counts, choosing projections, and fetching data as a List, Page, Slice, Window, or Stream.

This approach is useful when the same search criteria need to be consumed in different forms. For example, a list screen needs a Page, an autocomplete box needs only the top 10 results, a reporting API needs a projection, and a large data processing job wants to scroll by Window. Instead of creating multiple nearly identical Repository methods, you can keep one Example and select the execution mode via a fluent query.

## 1. QueryByExampleExecutor and the findBy() method

QueryByExampleExecutor is a Spring Data interface providing Example-based search operations. JpaRepository inherits Query by Example capabilities, so standard Repositories can use findBy() without manually implementing this interface.

The fluent query method has the general signature:

~~~java
<S extends T, R> R findBy(
        Example<S> example,
        Function<FetchableFluentQuery<S>, R> queryFunction
);
~~~

Type meanings:

- T is the Entity type managed by the Repository.
- S is the probe type used to construct the Example, usually Entity T itself or a compatible subtype.
- R is the result type returned by queryFunction.
- Example holds the probe and ExampleMatcher.
- FetchableFluentQuery provides query configuration operations and terminal operations to fetch results.

The key point is that findBy() accepts a function. Spring Data passes the fluent query into that function; the application configures the query and calls a terminal operation such as all(), page(), slice(), scroll(), or stream(). The final result of the terminal operation becomes the return value of findBy().

## 2. Preparing the Entity and Repository

Example using the Person Entity:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "people")
public class Person {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String firstName;
    private String lastName;
    private Boolean active;

    protected Person() {
    }

    public Person(String firstName, String lastName, Boolean active) {
        this.firstName = firstName;
        this.lastName = lastName;
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

    public Boolean getActive() {
        return active;
    }

    public void setFirstName(String firstName) {
        this.firstName = firstName;
    }

    public void setLastName(String lastName) {
        this.lastName = lastName;
    }

    public void setActive(Boolean active) {
        this.active = active;
    }
}
~~~

Repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

JpaRepository provides Query by Example support out of the box. You can create probes and ExampleMatchers in the service layer and pass them into findBy().

A probe is an object used to describe criteria. Populated properties are used to create predicates according to the matcher; null properties are typically ignored by default.

## 3. Creating an Example from a probe and ExampleMatcher

Example finding people whose last name starts with "Nguyen", case-insensitively:

~~~java
Person probe = new Person(null, "Nguyen", null);

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnorePaths("id")
        .withMatcher(
                "lastName",
                ExampleMatcher.GenericPropertyMatchers
                        .startsWith()
                        .ignoreCase()
        );

Example<Person> example = Example.of(probe, matcher);
~~~

In this example:

- Only lastName is set on the probe.
- id is explicitly ignored.
- matchingAll() requires conditions generated from evaluated properties to all match.
- startsWith() creates a prefix search condition.
- ignoreCase() requests case-insensitive string comparison.

ExampleMatcher is an immutable configuration object; with... methods return a newly configured matcher for continued use.

### matchingAll() and matchingAny()

Two common condition-combining modes:

- matchingAll(): combines evaluated properties with AND.
- matchingAny(): combines evaluated properties with OR.

Example probe with both firstName and lastName:

~~~java
Person probe = new Person("An", "Nguyen", null);

ExampleMatcher allMatcher = ExampleMatcher.matchingAll()
        .withIgnoreCase();

ExampleMatcher anyMatcher = ExampleMatcher.matchingAny()
        .withIgnoreCase();

Example<Person> allExample = Example.of(probe, allMatcher);
Example<Person> anyExample = Example.of(probe, anyMatcher);
~~~

allExample finds people matching both firstName and lastName. anyExample finds people matching either firstName or lastName.

QBE is not a general-purpose boolean expression builder. matchingAny() applies OR across evaluated properties; it does not allow freely grouping expressions like (firstName = ? OR lastName = ?) AND active = true in arbitrary structures. When complex condition groups are needed, consider Specification, Querydsl, or @Query.

## 4. Fluent queries change how results are fetched

After creating an Example, you can use findBy() to configure execution:

~~~java
List<Person> people = repository.findBy(
        example,
        query -> query
                .sortBy(Sort.by("lastName").ascending())
                .all()
);
~~~

Here:
- query is the FetchableFluentQuery provided by Spring Data inside the callback.
- sortBy() adds sort ordering.
- all() executes the query and returns List<Person>.

Property names in Sort are Java property names of the Entity, such as lastName, not SQL column names like last_name.

The strength of fluent queries is separating Example criteria from result retrieval. You can keep the same Example while swapping the terminal operation per use case.

## 5. Limiting result count with limit()

If you only need up to a maximum number of results, use limit():

~~~java
List<Person> suggestions = repository.findBy(
        example,
        query -> query
                .sortBy(Sort.by("lastName").ascending())
                .limit(10)
                .all()
);
~~~

The query returns at most 10 matching Person entities. limit() is useful for autocomplete, suggestion lists, or operations needing only a small result subset.

Limit is not the same as pagination. It only sets an upper bound on fetched results. If you need multi-page navigation, use page() or slice(); if you need position-based continuation, use scroll().

Combine limit() with a stable Sort if results need deterministic ordering. If sorting by a field that can have duplicates, add ID as a secondary criterion.

## 6. Flexible sorting with sortBy()

Fluent queries accept Sort to control result ordering:

~~~java
List<Person> people = repository.findBy(
        example,
        query -> query
                .sortBy(Sort.by(
                        Sort.Order.asc("lastName"),
                        Sort.Order.asc("firstName"),
                        Sort.Order.asc("id")
                ))
                .all()
);
~~~

This sorts by lastName, then firstName, and finally id. ID provides a tie-breaker so results have deterministic ordering when multiple people share the same name.

You can also construct a Sort beforehand and pass it in:

~~~java
Sort sort = Sort.by(
        Sort.Order.desc("active"),
        Sort.Order.asc("lastName")
);

List<Person> people = repository.findBy(
        example,
        query -> query.sortBy(sort).all()
);
~~~

Do not use SQL column names as Sort properties when using fluent queries on an Entity. Spring Data expects persistent property names from the Java model. If sorting by custom SQL expressions or database functions, use a more suitable query mechanism.

## 7. Converting results to projections with as()

Fluent queries can return a projection type instead of the full Entity. Example interface projection:

~~~java
public interface PersonSummary {
    Long getId();
    String getFirstName();
    String getLastName();
}
~~~

Using as():

~~~java
List<PersonSummary> summaries = repository.findBy(
        example,
        query -> query
                .as(PersonSummary.class)
                .sortBy(Sort.by("lastName").ascending())
                .all()
);
~~~

as(PersonSummary.class) tells Spring Data to materialize results as the projection type. This is useful when an API only needs a few fields and does not need full Entity state.

Projections clearly express output data, reduce manual mapping, and can restrict selected properties depending on projection type and provider. Check the actual SQL if your goal is to reduce the number of SELECTed columns.

### Selecting properties with project()

project() lets you specify which properties to include in results:

~~~java
List<Person> partialPeople = repository.findBy(
        example,
        query -> query
                .project("id", "firstName", "lastName")
                .all()
);
~~~

Property names in project() are persistent property names of the Entity. Select only the fields needed for the use case.

When combining projections and keyset scrolling, keep all sort properties and keys needed for Spring Data to determine the next position inside the projection. Do not omit sort fields just because the UI does not display them.

## 8. Paginating with page()

If the UI needs total element count and total page count, use page():

~~~java
Page<Person> page = repository.findBy(
        example,
        query -> query
                .sortBy(Sort.by("lastName").ascending())
                .page(PageRequest.of(0, 20))
);
~~~

The result is Page<Person>, from which you can retrieve:

~~~java
List<Person> content = page.getContent();
long totalElements = page.getTotalElements();
int totalPages = page.getTotalPages();
boolean hasNext = page.hasNext();
~~~

Page includes total count information. Spring Data may need a count query to calculate totalElements, though in some cases the framework can derive the total from page content and avoid a separate count query.

Use Page when the UI genuinely needs an accurate total. On large tables, the count query can be a significant cost.

## 9. Using slice() when total count is not needed

If the UI only needs to know whether more data is available to load, use Slice():

~~~java
Slice<Person> slice = repository.findBy(
        example,
        query -> query
                .sortBy(Sort.by("id").ascending())
                .slice(PageRequest.of(0, 50))
);
~~~

Slice provides the current content and hasNext() status, without totalElements or totalPages like Page. Thus, it avoids needing an exact total count.

Example:

~~~java
if (slice.hasNext()) {
    // Show load more button or go to next page.
}
~~~

Choose Page for UIs needing "page 2 of 10". Choose Slice for infinite scroll lists or "Load more" buttons when you only need to know whether a next element exists.

## 10. Scrolling results with scroll()

Fluent queries can also return Window<T> to scroll by ScrollPosition:

~~~java
Window<Person> window = repository.findBy(
        example,
        query -> query
                .sortBy(Sort.by("id").ascending())
                .scroll(ScrollPosition.offset())
);
~~~

Then, take the last element's position to request the next Window:

~~~java
ScrollPosition nextPosition =
        window.positionAt(window.size() - 1);

Window<Person> nextWindow = repository.findBy(
        example,
        query -> query
                .sortBy(Sort.by("id").ascending())
                .scroll(nextPosition)
);
~~~

Scroll positions have exclusive semantics: the next window starts after the specified element. Therefore, use the position of the last processed element to avoid duplicate elements.

Check window.isEmpty() and window.hasNext() before reading the position. If the window is empty, never call positionAt(-1).

Loop example:

~~~java
ScrollPosition position = ScrollPosition.offset();

while (true) {
    Window<Person> window = repository.findBy(
            example,
            query -> query
                    .sortBy(Sort.by("id").ascending())
                    .scroll(position)
    );

    if (window.isEmpty()) {
        break;
    }

    for (Person person : window) {
        process(person);
    }

    if (!window.hasNext()) {
        break;
    }

    position = window.positionAt(window.size() - 1);
}
~~~

The loop snippet illustrates controlling each Window; in Java, variables captured in a lambda must be final or effectively final. When updating position across iterations, use a final variable per invocation or use WindowIterator to avoid capture issues.

Complete way to write it with a per-iteration captured position variable:

~~~java
ScrollPosition position = ScrollPosition.offset();

while (true) {
    ScrollPosition currentPosition = position;

    Window<Person> window = repository.findBy(
            example,
            query -> query
                    .sortBy(Sort.by("id").ascending())
                    .scroll(currentPosition)
    );

    if (window.isEmpty()) {
        break;
    }

    for (Person person : window) {
        process(person);
    }

    if (!window.hasNext()) {
        break;
    }

    position = window.positionAt(window.size() - 1);
}
~~~

If using keyset scrolling, choose a stable order with ID as a tie-breaker and ensure sort properties are non-null and present in the projection.

## 11. Iterating across Windows with WindowIterator

WindowIterator simplifies iterating over Windows:

~~~java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.support.WindowIterator;

WindowIterator<Person> iterator = WindowIterator.of(position ->
        repository.findBy(
                example,
                query -> query
                        .sortBy(Sort.by("id").ascending())
                        .scroll(position)
        )
).startingAt(ScrollPosition.offset());

while (iterator.hasNext()) {
    Person person = iterator.next();
    process(person);
}
~~~

WindowIterator accepts a function producing a Window for a ScrollPosition, automatically advances to the next position, and supplies elements one by one to the loop.

Use WindowIterator when you want to process elements sequentially. Use a manual loop when you need checkpointing, transaction boundaries, or logging per Window.

Scrolling via QBE combines probe conditions with reading a dataset in chunks. However, it does not create an immutable snapshot of the entire table; if data changes during processing, results can be affected by ordering and query conditions.

## 12. Using stream() and managing resources

Fluent queries can return Stream<T>:

~~~java
@Transactional(readOnly = true)
public void processMatchingPeople(Example<Person> example) {
    try (Stream<Person> people = repository.findBy(
            example,
            query -> query
                    .sortBy(Sort.by("id").ascending())
                    .stream()
    )) {
        people.forEach(this::process);
    }
}
~~~

A Stream can be tied to JDBC or persistence provider resources. Therefore:
- Consume the Stream within an appropriate transaction.
- Close the Stream with try-with-resources.
- Do not return the Stream out of the service after the transaction ends.
- Do not keep the Stream open longer than necessary.
- If you need checkpoints and batch processing, consider Window instead of Stream.

Stream and Window have different lifecycles. A Stream is a sequence of elements that can hold resources open; a Window is a bounded slice of results fetched by a single query.

## 13. Combining limit(), projection, and sortBy()

Fluent operations can be combined to build a specific read query:

~~~java
List<PersonSummary> suggestions = repository.findBy(
        example,
        query -> query
                .as(PersonSummary.class)
                .project("id", "firstName", "lastName")
                .sortBy(Sort.by(
                        Sort.Order.asc("lastName"),
                        Sort.Order.asc("id")
                ))
                .limit(15)
                .all()
);
~~~

This example:
1. Uses Example as the search condition.
2. Converts results to PersonSummary.
3. Requests only the properties needed for the projection.
4. Sorts by lastName then id.
5. Limits to at most 15 results.
6. Executes and returns List<PersonSummary>.

Ensure the projection includes properties needed for sorting and any scroll continuation mechanism if using keyset scrolling. When combining as() and project(), verify with integration tests on your running Spring Data JPA version to confirm projection behavior and mapped columns match expectations.

## 14. findBy() must return the final result inside the callback

An important characteristic of fluent queries is that the FetchableFluentQuery object must only be used inside the findBy() callback scope. The callback must execute a terminal operation and return the final result.

Correct:

~~~java
List<Person> people = repository.findBy(
        example,
        query -> query
                .sortBy(Sort.by("id"))
                .all()
);
~~~

Do not return the query object itself for later use outside the callback:

~~~java
// Do not do this:
var query = repository.findBy(
        example,
        queryFunction -> queryFunction
);
~~~

A fluent query is a query configuration object scoped to the callback. Do not store it in a field, cache it for later execution, or return it out. Always call all(), page(), slice(), scroll(), stream(), or an appropriate terminal operation directly inside the lambda.

## 15. Common terminal operations

Terminal operations determine the final result type:

| Terminal operation | Result | Use when |
|---|---|---|
| all() | List<T> or List<Projection> | Fetching all matching results within query limits |
| page(Pageable) | Page<T> | Total count and page metadata are needed |
| slice(Pageable) | Slice<T> | Only knowing whether a next page exists is needed |
| scroll(ScrollPosition) | Window<T> | Reading in windows and continuing by position |
| stream() | Stream<T> | Stream processing with proper resource management |

Type T in the table can be an Entity or a projection type configured via as(). Choose the terminal operation based on actual requirements; do not use Page just for extra metadata if the UI does not need total counts.

## 16. Limitations of Query by Example

Fluent queries only change how results are executed and formatted. They do not turn QBE into a general-purpose query language.

Important QBE limitations:

- Cannot express arbitrary comparisons like greater-than, less-than, between, or arbitrary expressions for all data types.
- Does not support arbitrary complex boolean grouping structures such as combining multiple nested AND/OR groups.
- Not suitable for describing all collection or Map queries.
- Null properties are normally ignored by default; handling null requires appropriate null handling configuration.
- Primitive default values like false or 0 can be treated as probe values, because primitives cannot represent an "unset" state.
- String comparison and ignore case behavior still depend on the provider/database.

If you need conditions like price > 100, createdAt BETWEEN two timestamps, or (status = A OR status = B) AND tenantId = X, consider Specification, Criteria API, Querydsl, or @Query.

For probes, prefer wrappers such as Boolean or Integer when you need to distinguish "do not filter on this property" from "filter by false/0".

## 17. Separating Example criteria from fluent query execution

These two parts have distinct responsibilities:

| Component | Responsibility |
|---|---|
| Probe | Holds sample values |
| ExampleMatcher | Defines how probe values are compared and combined |
| Example | Wraps probe together with matcher |
| findBy() | Accepts Example and opens a fluent query |
| Fluent query | Configures sort, limit, projection, and result retrieval |
| Terminal operation | Executes and returns List, Page, Slice, Window, or Stream |

For example, changing from all() to page() does not change the search criteria. It only changes how results are fetched and what metadata accompanies them.

Similarly, changing as(PersonSummary.class) does not cause the Example to match more or fewer rows; it changes the shape of the returned data.

## 18. Service example reusing a single Example

You can encapsulate Example creation in a service and execute multiple fluent queries with it:

~~~java
import org.springframework.data.domain.*;
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;
import org.springframework.stereotype.Service;
import java.util.List;

@Service
public class PersonSearchService {

    private final PersonRepository repository;

    public PersonSearchService(PersonRepository repository) {
        this.repository = repository;
    }

    private Example<Person> createExample(String lastName) {
        Person probe = new Person(null, lastName, true);

        ExampleMatcher matcher = ExampleMatcher.matchingAll()
                .withIgnorePaths("id")
                .withMatcher(
                        "lastName",
                        ExampleMatcher.GenericPropertyMatchers
                                .startsWith()
                                .ignoreCase()
                );

        return Example.of(probe, matcher);
    }

    public List<PersonSummary> suggestions(String lastName) {
        Example<Person> example = createExample(lastName);

        return repository.findBy(example, query -> query
                .as(PersonSummary.class)
                .sortBy(Sort.by("lastName").ascending())
                .limit(10)
                .all());
    }

    public Page<Person> searchPage(
            String lastName,
            Pageable pageable) {

        Example<Person> example = createExample(lastName);

        return repository.findBy(example, query -> query
                .sortBy(Sort.by("lastName").ascending())
                .page(pageable));
    }
}
~~~

The service reuses the same search rules while choosing different result shapes:
- suggestions() returns up to 10 projections for an autocomplete box.
- searchPage() returns Page<Person> for a paginated screen.

This is an illustrative structural example. The project must define PersonRepository, PersonSummary, and corresponding Entity accessors. To change filter conditions, modify createExample() or create dedicated matchers per use case.

## 19. Testing fluent queries

Test both the QBE criteria and how the fluent query returns results.

Repository test example:

~~~java
@DataJpaTest
class PersonRepositoryTest {

    @Autowired
    private PersonRepository repository;

    @Test
    void fluentQueryAppliesExampleSortAndLimit() {
        repository.save(new Person("An", "Nguyen", true));
        repository.save(new Person("Binh", "Nguyen", true));
        repository.save(new Person("Chi", "Tran", true));

        Person probe = new Person(null, "Nguyen", true);

        ExampleMatcher matcher = ExampleMatcher.matchingAll()
                .withIgnorePaths("id")
                .withMatcher(
                        "lastName",
                        ExampleMatcher.GenericPropertyMatchers
                                .exact()
                                .ignoreCase()
                );

        Example<Person> example = Example.of(probe, matcher);

        List<Person> result = repository.findBy(
                example,
                query -> query
                        .sortBy(Sort.by("firstName").ascending())
                        .limit(1)
                        .all()
        );

        assertEquals(1, result.size());
        assertEquals("An", result.get(0).getFirstName());
    }
}
~~~

With the fixture data above, the expected output is:

~~~text
size = 1
firstName = An
~~~

Also add tests for:
1. matchingAll() and matchingAny().
2. IgnoreCase, exact, startsWith, and containing.
3. Null probe fields and ignorePaths.
4. Primitive default values versus wrapper types.
5. sortBy() with multiple criteria.
6. limit() and projections.
7. Page with accurate totalElements.
8. Slice with accurate hasNext().
9. Window advancing to the exact right position without duplicates or skipped elements.
10. Stream consumed and closed inside an appropriate transaction.

Run integration tests against the target database when collation behavior, data types, or query plans matter to the application. Do not rely solely on in-memory database tests to conclude all production behaviors are identical.

## 20. Common mistakes

**Creating only an Example without calling a terminal operation**

Example only describes conditions. findBy() requires a callback that executes a terminal operation to retrieve results.

**Returning the fluent query out of the callback**

The query object is scoped to the callback. Returning it or storing it for later use violates the API lifecycle.

**Confusing sort property names with SQL column names**

sortBy() on an Entity uses Java property names like lastName, not column names like last_name.

**Using Page when total count is not needed**

Page may trigger a count query. If you only need to know whether more results exist, use Slice or Window.

**Projection missing sort properties when scrolling**

Keyset scrolling needs sort property and key values to determine the position. Include these fields in the projection.

**Using primitives in probes and accidentally filtering by default values**

false or 0 can become search conditions. Use wrappers when an unset state is needed.

**Expecting QBE to express arbitrary complex conditions**

QBE has operator and boolean grouping limits. Switch to Specification, Querydsl, or @Query when conditions exceed matcher capabilities.

**Using Stream without closing it**

Streams can hold JDBC resources. Use try-with-resources inside an appropriate transaction.

**Using limit() instead of pagination**

limit only caps the maximum number of results. Use page(), slice(), or scroll() when you need to continue through a dataset.

## 21. Workflow for choosing a fluent query for a use case

When building flexible searches:

1. Create a probe with the properties the user actually provided.
2. Choose ExampleMatcher: matchingAll or matchingAny, string matching mode, ignore case, and ignore paths.
3. Use Example.of(probe, matcher) to wrap the conditions.
4. Call repository.findBy(example, query -> ...) to configure the fluent query.
5. Use sortBy() and limit() when sorting or limiting is needed.
6. Use as() or project() if only a subset of data is needed.
7. Choose all(), page(), slice(), scroll(), or stream() based on how results are consumed.
8. Do not return the fluent query object out of the callback.
9. Inspect SQL, count queries, indexes, and projections on a real database.
10. If filtering conditions exceed QBE's capabilities, switch to Specification, Querydsl, or @Query rather than building an overly complex, hard-to-understand probe.

## 22. Conclusion

QueryByExampleExecutor.findBy() combines Example with FetchableFluentQuery to separate search criteria from result retrieval. The probe and ExampleMatcher determine which records match; the fluent query determines sort, limit, projection, and terminal operation. Use all() for List, page() when total count is needed, slice() when only checking for a next page, scroll() for Window, and stream() with proper resource management. Fluent queries must execute inside the callback and must not be stored or returned outside. QBE still has limits on operators and condition grouping; for complex queries, use Specification, Querydsl, or @Query.