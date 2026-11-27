# QuerydslPredicateExecutor and Binding Customization When Supported by Version and Store

## 1. Querydsl in Spring Data

Querydsl is a Java library for building type-safe queries from expressions. Instead of concatenating query strings or creating a separate finder method for every filter combination, an application can compose conditions into a Predicate.

Generated Q-type classes derived from the domain model describe properties and their corresponding data types. For example, QPerson.firstName is a StringPath, while QPerson.age is a NumberPath. The compiler and IDE can check property names as well as the operations invoked on each path type.

Spring Data provides **QuerydslPredicateExecutor<T>** so repositories can execute Predicates. When supported by the Spring Data version and store module, an application can filter, count, or check existence of data using predicates without declaring a separate method for every combination of conditions.

Three parts need to be distinguished:

- **Querydsl:** builds type-safe query expressions.
- **QuerydslPredicateExecutor:** repository contract for executing Predicates.
- **Querydsl web binding:** converts HTTP query parameters into a Predicate; conversion rules can be customized.

Simply adding Querydsl to the classpath is not enough. The store module must provide a matching implementation, Q-types must be generated properly, and web binding must be configured or integrated by Spring Data REST in the version in use.

## 2. What does QuerydslPredicateExecutor provide?

Common operations of the interface include:

~~~~java
public interface QuerydslPredicateExecutor<T> {

    Optional<T> findOne(Predicate predicate);

    Iterable<T> findAll(Predicate predicate);

    Iterable<T> findAll(Predicate predicate, Sort sort);

    Page<T> findAll(Predicate predicate, Pageable pageable);

    long count(Predicate predicate);

    boolean exists(Predicate predicate);
}
~~~~

| Method | Purpose |
|---|---|
| findOne(predicate) | Finds one matching result; may fail if multiple results exist when the implementation requires uniqueness |
| findAll(predicate) | Retrieves matching results |
| findAll(predicate, sort) | Retrieves matching results sorted |
| findAll(predicate, pageable) | Retrieves a page of matching results |
| count(predicate) | Counts matching records |
| exists(predicate) | Checks whether any matching record exists |

A Predicate is a query condition, not input data to be persisted. For example:

~~~~java
QPerson person = QPerson.person;

Predicate predicate = person.active.isTrue()
        .and(person.firstName.containsIgnoreCase("an"));

Page<Person> result = repository.findAll(
        predicate,
        PageRequest.of(0, 20)
);
~~~~

This condition selects active people whose firstName contains the substring "an", case-insensitively. Q-types keep expressions strictly typed.

## 3. Version and store support requirements

The ability to use Querydsl depends on the release train and storage module. Before designing an API, verify:

1. The Spring Data version in use still provides compatible Querydsl integration.
2. The store module has an implementation for QuerydslPredicateExecutor.
3. The Querydsl version is compatible with Spring Data, Spring Boot, and the persistence namespace.
4. The annotation processor has generated Q-types for entities or documents.
5. The repository is instantiated as a bean and can execute predicates against the actual store.

Spring Data JPA has Querydsl integration. Other storage modules may vary in support or lack support in the version being used. Do not assume every Spring Data repository can simply add QuerydslPredicateExecutor.

### Dependencies and Q-type generation

With Spring Data JPA, projects typically need the Querydsl JPA module and annotation processor to generate Q-type classes. A Maven dependency setup may look like:

~~~~xml
<dependency>
    <groupId>com.querydsl</groupId>
    <artifactId>querydsl-jpa</artifactId>
</dependency>

<dependency>
    <groupId>com.querydsl</groupId>
    <artifactId>querydsl-apt</artifactId>
    <scope>provided</scope>
</dependency>
~~~~

This is an illustrative skeleton, not a copy-paste configuration for every project. For Querydsl using Jakarta Persistence, the artifact/classifier and annotation processor must correspond to jakarta.persistence; legacy projects using javax.persistence must configure the older namespace. Use Spring Boot's dependency management or an appropriate BOM to select compatible versions.

Once the annotation processor is configured, the build generates classes such as:

~~~~text
target/generated-sources/annotations/
    com/example/domain/QPerson.java
~~~~

Q-types are auto-generated code and should not be edited directly. Whenever domain properties are added or changed, rerun the build to refresh Q-types. If the IDE cannot find QPerson, check the annotation processor, generated-sources directory, package, and persistence namespace.

## 4. Declaring the repository

A JPA repository can combine JpaRepository, QuerydslPredicateExecutor, and QuerydslBinderCustomizer:

~~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository
        extends JpaRepository<Person, Long>,
                QuerydslPredicateExecutor<Person>,
                QuerydslBinderCustomizer<QPerson> {

    @Override
    default void customize(
            QuerydslBindings bindings,
            QPerson root) {
        // Declare binding rules.
    }
}
~~~~

The three interfaces have distinct responsibilities:

- **JpaRepository<Person, Long>** provides JPA-based repository operations.
- **QuerydslPredicateExecutor<Person>** enables executing Predicates on Person.
- **QuerydslBinderCustomizer<QPerson>** allows defining how query parameters are bound into predicates.

If an API is read-only, choose the minimal repository contract suited to the store. Extending JpaRepository also brings in write operations; restrict REST exposure and authorization if those should not be exposed.

## 5. Query parameters to Predicate

When Querydsl web support is integrated, clients can send properties to filter on as query parameters:

~~~~http
GET /people?firstName=An&active=true
Accept: application/hal+json
~~~~

High-level processing flow:

1. Identify the domain type, e.g., Person.
2. Read the query parameters permitted for binding.
3. Convert HTTP strings into corresponding Java types such as Boolean, Long, enum, or date.
4. Build a Querydsl condition for each property.
5. Combine the conditions into a single Predicate.
6. Pass the Predicate to the repository for execution.

The equivalent Predicate could be written as:

~~~~java
QPerson person = QPerson.person;

Predicate predicate = person.firstName.eq("An")
        .and(person.active.isTrue());
~~~~

In Spring Data REST, when the repository and version integrate QuerydslPredicateExecutor, query parameters on the collection resource can be used for filtering. With Spring Data Web in a custom MVC controller, **@QuerydslPredicate** can be used to receive a Predicate from the request.

Do not assume every query parameter becomes a search condition. Binding can be constrained by customizers, property types, conversion, and version configuration.

## 6. Customizing bindings with QuerydslBinderCustomizer

QuerydslBindings defines how each property is turned into a condition. Default rules can depend on property types and versions. If the API needs explicit semantics, declare bindings explicitly.

Example: match strings with case-insensitive contains and exclude password from searchability:

~~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository
        extends JpaRepository<Person, Long>,
                QuerydslPredicateExecutor<Person>,
                QuerydslBinderCustomizer<QPerson> {

    @Override
    default void customize(
            QuerydslBindings bindings,
            QPerson root) {

        bindings.bind(root.firstName)
                .first((path, value) ->
                        path.containsIgnoreCase(value));

        bindings.bind(String.class)
                .first((StringPath path, String value) ->
                        path.containsIgnoreCase(value));

        bindings.excluding(root.password);
    }
}
~~~~

The specific binding for firstName defines that field's semantics. The binding on String.class applies a rule to remaining string properties. excluding(root.password) prevents password from being used as a query parameter.

Per-field binding fits when a property needs custom rules. Per-type binding fits when applying the same rule across many fields. Verify the actual behavior of the version in use if a property matches both a specific binding and a type-level binding.

### Some commonly used expressions

~~~~java
@Override
default void customize(QuerydslBindings bindings, QPerson root) {

    // Exact match.
    bindings.bind(root.email)
            .first((path, value) -> path.eq(value));

    // Contains string, case-insensitive.
    bindings.bind(root.firstName)
            .first((path, value) ->
                    path.containsIgnoreCase(value));

    // Number greater than or equal to the supplied value.
    bindings.bind(root.age)
            .first((path, value) -> path.goe(value));

    // Allow only specific fields.
    bindings.including(
            root.firstName,
            root.lastName,
            root.active,
            root.age
    );
}
~~~~

Expressions such as eq, contains, containsIgnoreCase, startsWithIgnoreCase, goe, loe, and in are used depending on the Q-path type. Do not invoke StringPath operations on a NumberPath or a path that lacks the corresponding operation.

## 7. first and all: single vs. multiple values

A query parameter can appear multiple times:

~~~~http
GET /people?status=ACTIVE&status=PENDING
~~~~

The binding API offers two handling styles:

- **first(...)** uses the first value according to the binding contract.
- **all(...)** receives the collection of values and allows building a condition from the entire set.

Example matching status against any of the supplied values:

~~~~java
bindings.bind(root.status)
        .all((path, values) ->
                Optional.of(path.in(values)));
~~~~

The predicate corresponds to status IN ('ACTIVE', 'PENDING'). If first is used for a multi-valued parameter, remaining values are not combined into an IN condition. Use all when the endpoint needs to process all supplied values.

## 8. Excluding and including: blocklist or allowlist

Binding can be open to many properties of the domain type. That is convenient during development, but can inadvertently expose filtering on fields that should not appear in the API.

**Excluding** creates a list of forbidden fields:

~~~~java
bindings.excluding(
        root.password,
        root.resetToken,
        root.internalNotes
);
~~~~

This approach works when most fields are safe to search and only a few fields need to be removed.

**Including** creates an allowlist of fields permitted for binding:

~~~~java
bindings.including(
        root.firstName,
        root.lastName,
        root.email,
        root.active
);
~~~~

This approach fits public APIs where only a small subset of fields is meaningful for searching. Properties outside the allowlist are not exposed as query parameters.

Hiding a field in the response is not enough to secure searching. A field that is not serialized can still be sensitive if the server allows clients to filter on that field. Control binding independently from serialization and authorization.

## 9. Using @QuerydslPredicate in a custom controller

In addition to Spring Data REST's automatic repository resources, Spring Data Web supports binding a Predicate to a controller parameter with @QuerydslPredicate.

~~~~java
@RestController
@RequestMapping("/people")
class PersonSearchController {

    private final PersonRepository repository;

    PersonSearchController(PersonRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/filter")
    Page<Person> filter(
            @QuerydslPredicate(root = Person.class)
            Predicate predicate,
            Pageable pageable) {

        return repository.findAll(predicate, pageable);
    }
}
~~~~

Request:

~~~~http
GET /people/filter?firstName=An&active=true&page=0&size=20
~~~~

Spring Data Web builds the Predicate from query parameters; the controller passes the predicate and Pageable to QuerydslPredicateExecutor.

A custom controller fits when you need a dedicated search route, combining the predicate with business logic or tenant scoping, returning DTOs/projections, capping results, custom validation, or extra authorization.

@QuerydslPredicate requires Spring Data web support and compatible configuration. If you want to apply custom bindings to the controller, you can use QuerydslBinderCustomizer on the repository or a binder specified via the API of the version in use.

## 10. Nested paths and aliases

Querydsl allows building conditions on nested properties through Q-types:

~~~~java
bindings.bind(root.address.city)
        .first((path, value) ->
                path.equalsIgnoreCase(value));
~~~~

QPerson can provide a path to address.city if the domain model and Q-type represent that relationship. However, exposing nested paths in an HTTP API requires consideration:

- Associations can trigger expensive joins.
- Collection relationships can multiply result rows or cause heavy queries.
- Nested fields can contain sensitive data.
- Java property names may not be the desired API names.

If your version of QuerydslBindings supports aliases for bindings, you can expose friendlier query parameter names than internal property names. Verify the as(...) method and its behavior in the Javadoc for your exact version before using it.

## 11. Pagination, sorting, and performance

Combining Predicate with Pageable lets the API filter and paginate in the same request:

~~~~http
GET /people?active=true&page=0&size=20&sort=lastName,asc
~~~~

In a custom controller, you can call:

~~~~java
Page<Person> page = repository.findAll(predicate, pageable);
~~~~

Do not let clients request an unlimited page size. Consider:

- Database indexes for frequently filtered or sorted fields.
- Allowing sorting only on permitted and properly indexed fields.
- Predicates on associations or unindexed fields can be very expensive.
- Total result counts may require a separate count query.
- Combining many filters can produce complex queries.
- Limiting the number of conditions and value list sizes.

Predicate-based search is flexible, but does not guarantee good performance for every combination of conditions.

## 12. Data types and conversion

Web binding typically starts from string values in the URL. Spring Data must convert those values into appropriate Java types to construct predicates.

~~~~http
GET /people?age=30&active=true&status=ACTIVE&createdAt=2026-01-15
~~~~

Values can be converted into Integer/Long, Boolean, enum, and date if ConversionService has a matching converter.

When binding does not work as expected, check:

1. Does the query parameter name match the property path or alias?
2. Does the Q-type contain that property?
3. Can the string value be converted to the domain type?
4. Is a custom converter or formatter changing the conversion?
5. Is the binding restricted by including/excluding?
6. Does the store module support the corresponding expression and operation?

Do not parse everything with toString() and build untyped predicates. Using proper conversion and typed Querydsl paths catches errors earlier.

## 13. Securing the search surface

Querydsl web binding can open up a mini query language via the URL. Therefore, treat bindings as part of the public API.

- Allow searching only on fields with business meaning.
- Exclude passwords, tokens, secrets, internal flags, and unnecessary personal data.
- Prefer an allowlist with including(...) for public APIs.
- Do not let clients pick arbitrary paths or open every association.
- Attach tenant/ownership predicates on the server; never trust a client-supplied query parameter to restrict tenant scope.
- Constrain page size, sort fields, and number of values per filter.
- Use proper indexes and monitor slow queries.
- Return projections/DTOs if clients do not need the entire entity.
- Enforce authorization before executing queries.

For example, if a user may only see records belonging to the current tenant, the tenant predicate must be combined from the server-side security context. Do not rely solely on a client-sent tenantId request parameter, since a client could change the ID to probe another tenant's data.

## 14. Testing Querydsl bindings

Test both the binding itself and execution against the real store or an appropriate test slice.

Example with MockMvc:

~~~~java
mockMvc.perform(get("/people/filter")
        .param("firstName", "an")
        .param("active", "true")
        .param("page", "0")
        .param("size", "10"))
    .andExpect(status().isOk());
~~~~

Tests should verify that results match containsIgnoreCase semantics, Boolean conversion, and pagination.

For excluded fields:

~~~~java
mockMvc.perform(get("/people/filter")
        .param("password", "secret"))
    .andExpect(status().isOk());
~~~~

Do not check only the status code; verify that the excluded parameter does not alter the query results or is rejected according to the application's contract.

Cases to test:

1. Fields not in including(...) do not generate a query condition.
2. Multiple status values generate an IN condition when using all(...).
3. first(...) handles values according to contract.
4. Aliases, nested paths, and type conversion work properly.
5. Pageable does not exceed maximum page size.
6. Tenant scope is always applied even when the client omits any tenant parameter.
7. Predicates are translated and executed properly on the real database/store.

A test that only inspects the Predicate object is not enough to prove the store module translates and executes the query correctly.

## 15. Common errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| QPerson not found | Annotation processor has not run or generated sources are not recognized by the IDE | Check the build processor and generated-sources |
| Repository fails to initialize | Store/version does not support QuerydslPredicateExecutor or incompatible dependencies | Check store documentation and dependency tree |
| Query parameter does not filter data | Binding is not enabled or property name mismatches | Check Spring Data web/REST integration and binder |
| String search returns results too broad/narrow | Default binding semantics differ from expectation | Declare first(...) explicitly |
| Multiple values only take one value | Using first(...) instead of all(...) | Use all(...) and an IN predicate when appropriate |
| Sensitive field is still searchable | Missing excluding or not using an allowlist | Use excluding(...) or including(...) |
| Slow query | Predicate opens too many fields, associations, or lacks indexes | Restrict bindings, add indexes, and analyze the query |
| Date/enum value fails to parse | ConversionService lacks converter or wrong format | Add converter/formatter and test the request |
| Controller does not receive Predicate | Missing Spring Data web support or wrong root type | Check @QuerydslPredicate and web configuration |

## 16. Conclusion

QuerydslPredicateExecutor lets Spring Data repositories execute type-safe Predicates; web binding can turn query parameters into Predicates to build flexible search APIs. This capability depends on the Spring Data version and store module, and requires properly generated Q-types.

QuerydslBinderCustomizer is the key extension point to define per-field semantics, apply type-based bindings, handle single or multiple values, and restrict fields using allowlists or blocklists. For public APIs, prefer allowlists, limit pagination, and always append security predicates on the server. Test against the exact version and real database to ensure predicates bind and execute accurately.

## References

- [Spring Data Commons — QuerydslPredicateExecutor API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/querydsl/QuerydslPredicateExecutor.html)
- [Spring Data Commons — Querydsl web support](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html)
- [Spring Data REST — Reference documentation](https://docs.spring.io/spring-data/rest/reference/)
- [Spring Data JPA — Querydsl support](https://docs.spring.io/spring-data/jpa/reference/repositories/core-extensions.html)
- [Querydsl Reference Guide](https://querydsl.com/static/querydsl/latest/reference/html_single/)
