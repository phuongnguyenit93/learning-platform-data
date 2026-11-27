# Map arguments in Spring for GraphQL

In GraphQL, each field can accept multiple arguments. GraphQL Java provides those values as a map keyed by argument name. Spring for GraphQL allows controllers to access this data using `@Argument` or `@Arguments` with a `Map<String, Object>` parameter.

The two map approaches have different scopes:

- `@Argument("filter") Map<String, Object> filter` retrieves **the raw value of a single argument named `filter`**. If the argument is an input object, the map contains the fields of that input object.
- `@Arguments Map<String, Object> arguments` retrieves **the entire map of arguments for the field being processed**. Each key is a field-level argument name; each value can be a scalar, a list, or a nested map.

Distinguishing these two cases is critical. Since Spring for GraphQL 1.2, `@Argument Map<String, Object>` always binds a single argument specified explicitly or inferred by parameter name. To retrieve all arguments of the field, use `@Arguments`.

## 1. How are GraphQL arguments represented?

Suppose a book search API has an input object used as a filter:

~~~graphql
enum BookStatus {
    DRAFT
    PUBLISHED
    ARCHIVED
}

input AuthorFilter {
    ids: [ID!]
    namePrefix: String
}

input BookFilter {
    keyword: String
    status: BookStatus
    author: AuthorFilter
}

type Query {
    searchBooks(
        filter: BookFilter
        includeArchived: Boolean! = false
        limit: Int! = 20
    ): [Book!]!
}

type Book {
    id: ID!
    title: String!
    status: BookStatus!
}
~~~

A client can send the query:

~~~graphql
query SearchBooks {
    searchBooks(
        filter: {
            keyword: "Spring"
            status: PUBLISHED
            author: {
                ids: ["author-1", "author-2"]
                namePrefix: "An"
            }
        }
        includeArchived: false
        limit: 10
    ) {
        id
        title
        status
    }
}
~~~

By the time the resolver is invoked, arguments have already been parsed and coerced by GraphQL according to the schema. Spring for GraphQL can bind a portion of that data into Java objects, or supply a map for the controller to handle manually.

The map received is the post-coercion value structure, not the raw JSON string from the HTTP request, and it does not contain the entire GraphQL document. It represents only the arguments of the field currently being executed.

## 2. Using @Argument Map to retrieve a single argument

When you only need to access the `filter` input object, declare `@Argument("filter") Map<String, Object>`:

~~~java
import java.util.Map;
import java.util.List;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> searchBooks(
            @Argument("filter") Map<String, Object> filter
    ) {
        return bookService.search(toCriteria(filter));
    }
}
~~~

`BookService`, `Book`, and the `toCriteria` conversion helper are application components; map conversion is illustrated in Section 5. This example focuses on the handler signature and the scope of data bound by `@Argument`.

Spring looks up the argument named `filter` and passes only that argument's value into the map parameter. With the query from the previous section, the `filter` map has keys such as `keyword`, `status`, and `author`; it does not contain `includeArchived` or `limit` because those are sibling arguments alongside `filter`.

If the Java parameter name matches the argument name and the compiler preserves parameter names, you can write `@Argument Map<String, Object> filter`. In code that must remain stable across build configurations, specify the name explicitly via `@Argument("filter")` or ensure the compiler has `-parameters` enabled.

## 3. Using @Arguments Map to retrieve all arguments

If the controller needs multiple field-level arguments at once, use `@Arguments`:

~~~java
import java.util.Map;

import org.springframework.graphql.data.method.annotation.Arguments;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    @QueryMapping
    public String argumentNames(@Arguments Map<String, Object> arguments) {
        return arguments.keySet().stream().sorted()
                .collect(java.util.stream.Collectors.joining(","));
    }
}
~~~

The corresponding SDL for this illustrative method could be declared as:

~~~graphql
type Query {
    argumentNames(
        filter: BookFilter
        includeArchived: Boolean! = false
        limit: Int! = 20
    ): String!
}
~~~

When the schema declares default values, GraphQL provides values after applying default rules. In the example, `includeArchived` and `limit` can be omitted by the client; the resolver receives the schema default values when those arguments are coerced.

`@Arguments Map<String, Object>` contains the argument map of the current field. For the book search query above, the value structure looks like:

~~~json
{
    "filter": {
        "keyword": "Spring",
        "status": "PUBLISHED",
        "author": {
            "ids": ["author-1", "author-2"],
            "namePrefix": "An"
        }
    },
    "includeArchived": false,
    "limit": 10
}
~~~

This is an illustrative structure to help visualize the shape. Enum values inside the map depend on the schema's enum coercing/runtime wiring; do not assume every enum is always represented as a string if the application configures custom internal values.

## 4. Distinguishing @Argument Map and @Arguments Map

Both declarations accept `Map<String, Object>`, but they bind two different scopes:

| Declaration | Data received | Example top-level keys |
| --- | --- | --- |
| `@Argument("filter") Map<String, Object> filter` | Value of the `filter` argument | `keyword`, `status`, `author` |
| `@Arguments Map<String, Object> arguments` | All arguments of the `searchBooks` field | `filter`, `includeArchived`, `limit` |

Example with the same query:

~~~java
@QueryMapping
public List<Book> searchBooks(
        @Argument("filter") Map<String, Object> filter,
        @Argument("limit") Integer limit,
        @Argument("includeArchived") Boolean includeArchived
) {
    // Each @Argument binds one named argument.
}
~~~

Compared to:

~~~java
@QueryMapping
public List<Book> searchBooks(@Arguments Map<String, Object> arguments) {
    // The map contains filter, limit, and includeArchived.
}
~~~

Do not use `@Argument Map<String, Object>` intending to retrieve all arguments. Prior to Spring for GraphQL 1.2, certain uses of `@Argument` without an explicit name returned the full arguments map; since 1.2, `@Argument Map` always returns the raw value of the argument identified by the annotation name or parameter name. `@Arguments` is the API for the full arguments map.

## 5. Safely accessing nested maps

When an input object contains child objects or lists, the map can hold nested structures:

~~~json
{
    "author": {
        "ids": ["author-1", "author-2"],
        "namePrefix": "An"
    }
}
~~~

Never cast directly without checking the data. A safer way to read it is to validate types at each level:

~~~java
import java.util.List;
import java.util.Map;

private Map<String, Object> asMap(Object value) {
    if (value == null) {
        return Map.of();
    }
    if (!(value instanceof Map<?, ?> source)) {
        throw new IllegalArgumentException("Expected an input object");
    }

    Map<String, Object> result = new java.util.HashMap<>();
    source.forEach((key, item) -> {
        if (!(key instanceof String name)) {
            throw new IllegalArgumentException("Expected string map keys");
        }
        result.put(name, item);
    });
    return result;
}

private List<String> stringList(Object value) {
    if (value == null) {
        return List.of();
    }
    if (!(value instanceof List<?> values)) {
        throw new IllegalArgumentException("Expected a list");
    }

    return values.stream()
            .map(item -> {
                if (!(item instanceof String text)) {
                    throw new IllegalArgumentException("Expected string values");
                }
                return text;
            })
            .toList();
}
~~~

You can then convert the map into an application criteria object:

~~~java
public record AuthorCriteria(List<String> ids, String namePrefix) {}

public enum BookStatus {
    DRAFT,
    PUBLISHED,
    ARCHIVED
}

public record BookSearchCriteria(
        String keyword,
        BookStatus status,
        AuthorCriteria author
) {}
~~~

~~~java
private BookSearchCriteria toCriteria(Map<String, Object> filter) {
    Map<String, Object> authorMap = asMap(filter.get("author"));

    AuthorCriteria author = new AuthorCriteria(
            stringList(authorMap.get("ids")),
            (String) authorMap.get("namePrefix")
    );

    return new BookSearchCriteria(
            (String) filter.get("keyword"),
            toBookStatus(filter.get("status")),
            author
    );
}

private BookStatus toBookStatus(Object value) {
    if (value == null) {
        return null;
    }
    if (value instanceof BookStatus status) {
        return status;
    }
    if (value instanceof String name) {
        return BookStatus.valueOf(name);
    }
    throw new IllegalArgumentException("Unsupported BookStatus value");
}
~~~

The conversion snippet above illustrates two common enum value forms: a Java value that is already `BookStatus`, or a string enum name. If the schema uses custom internal values, write a corresponding converter rather than relying on `toString()`.

## 6. Binding all arguments into a Java object with @Arguments

`@Arguments` does not only support `Map`. You can use it to bind all field-level arguments into a record or DTO with an appropriate constructor:

~~~java
public record SearchBooksArguments(
        BookFilter filter,
        Boolean includeArchived,
        Integer limit
) {}
~~~

The input records matching the SDL can be declared as follows:

~~~java
public record AuthorFilter(List<String> ids, String namePrefix) {}

public record BookFilter(
        String keyword,
        BookStatus status,
        AuthorFilter author
) {}
~~~

~~~java
@QueryMapping
public List<Book> searchBooks(@Arguments SearchBooksArguments arguments) {
    return bookService.search(
            arguments.filter(),
            Boolean.TRUE.equals(arguments.includeArchived()),
            arguments.limit()
    );
}
~~~

Difference compared to `@Argument BookFilter filter`:

- `@Argument("filter") BookFilter filter` binds the `filter` argument alone into `BookFilter`.
- `@Arguments SearchBooksArguments arguments` binds the field-level argument map into the properties of `SearchBooksArguments`.

This is a good option when a method accepts multiple related arguments and you want strong Java typing. If you only need a single input object, `@Argument` usually expresses intent more directly.

## 7. When should you use a Map vs. a DTO?

Maps are flexible, but they sacrifice compile-time type checking. For stable APIs with well-defined input structures, a DTO/record is usually the better choice.

| Criterion | `Map<String, Object>` | DTO/record |
| --- | --- | --- |
| Data types | Checked manually when reading | Types declared in Java |
| Nested structure | Must check and cast at every level | Binder recursively binds into nested objects |
| Refactoring | Keys are strings; error-prone on rename | Compiler helps find errors and refactor |
| Flexible input | Convenient for dynamic filters or varying field sets | Suits stable input contracts |
| Validation | Usually requires manual checks or DTO conversion | Can use Bean Validation with `@Valid`/`@Validated` |
| Code readability | Must inspect schema and accessed keys | Method signature communicates data structure |

Maps are suitable when:

- A resolver needs to handle dynamic filters or many optional criteria.
- You need to forward a flexible input structure to a specialized processing layer.
- You need to read raw arguments to perform custom conversion rules.
- You are building generic tooling that operates across many input object types.

DTOs/records are suitable when:

- The input structure is stable and clearly defined in the SDL.
- You want to use Bean Validation.
- You want compiler support for type checking, renaming, and refactoring.
- Multiple services share the same data contract.

Do not use a map just to avoid creating a small record. An explicit input type generally makes controllers and services easier to maintain.

## 8. @Argument Map does not bypass GraphQL schema validation

Receiving an argument as a Map does not turn GraphQL input into arbitrary schemaless data. GraphQL still validates the query and coerces inputs against the SDL before invoking the resolver.

SDL example:

~~~graphql
input BookFilter {
    keyword: String
    status: BookStatus
}

type Query {
    searchBooks(filter: BookFilter): [Book!]!
}
~~~

If a client sends an `unknownField` not declared in `BookFilter`, GraphQL rejects the input object during the validation/coercion step. The resolver does not receive an arbitrary map containing undeclared fields.

Using a Map only changes how Java receives data after GraphQL has enforced the schema contract. Therefore, continue designing input types intentionally, bounding list sizes, and controlling allowed enums or scalars.

## 9. Distinguishing arguments from variables, context, and source objects

Within a handler method, the following concepts have distinct scopes:

| Data | How to access | Meaning |
| --- | --- | --- |
| A single GraphQL argument | `@Argument("filter") Map<String, Object>` | Value of one specific argument |
| All arguments of the field | `@Arguments Map<String, Object>` | Map of the current field's arguments |
| GraphQL variables | Through arguments after coercion | Values passed by the client to substitute variables in the operation; not a separate map bound directly in the controller |
| Source/parent object | Source parameter, e.g., `Book book` | Parent object currently being resolved for the field |
| Request context | `GraphQLContext` or `@ContextValue` | Shared metadata such as principal, tenant, or correlation ID |

Example query:

~~~graphql
query Search($criteria: BookFilter, $limit: Int!) {
    searchBooks(filter: $criteria, limit: $limit) {
        id
        title
    }
}
~~~

When the resolver receives `@Argument("filter") Map<String, Object> filter`, it receives the value bound to the `filter` argument, even though that value came from the `$criteria` variable. The variable name does not become a key in the argument map; the key remains the schema argument name `filter`.

## 10. Maps and omitted vs. null

For nullable inputs, GraphQL distinguishes between a client not sending a field and sending the field with `null`. This is often important for partial-update mutations:

~~~graphql
input UpdateBookInput {
    title: String
    subtitle: String
}

type Mutation {
    updateBook(id: ID!, input: UpdateBookInput!): Book!
}
~~~

Example:

- `{ title: "New title" }`: update title, do not touch subtitle.
- `{ title: "New title", subtitle: null }`: client requests clearing subtitle if business rules allow.

If you need to know for certain whether an argument was omitted or passed as `null`, use `ArgumentValue<T>` for that argument. `@Argument` with a plain nullable value cannot fully express this distinction in all cases; `ArgumentValue` provides `isOmitted()` alongside the actual value.

With input objects, `ArgumentValue` can be used as a Java record property to preserve whether a field was omitted or passed as `null`:

~~~java
import org.springframework.graphql.data.ArgumentValue;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

public record UpdateBookInput(
        String title,
        ArgumentValue<String> subtitle
) {}

@Controller
public class BookMutationController {

    @MutationMapping
    public Book updateBook(
            @Argument("id") String id,
            @Argument("input") UpdateBookInput input
    ) {
        if (input.subtitle().isOmitted()) {
            return bookService.keepSubtitle(id);
        }
        return bookService.setSubtitle(id, input.subtitle().value());
    }
}
~~~

The SDL above declares `UpdateBookInput.subtitle` as nullable. If the client omits `subtitle`, `isOmitted()` is `true` and the service keeps the old value. If the client sends `subtitle: null`, `isOmitted()` is `false` and `value()` returns `null`, allowing the service to clear the value if business rules permit. Do not rely on `Map.get(key) == null` to distinguish these two cases because that check cannot differentiate an absent key from a key mapped to null; `containsKey` is only helpful when the underlying map structure actually preserves that distinction.

## 11. Validation when receiving a Map

The GraphQL schema checks types and nullability, but does not replace business rules. When accepting a map, the controller or service must validate necessary conditions before using the data.

For example, limiting the list of authors:

~~~java
private AuthorCriteria toAuthorCriteria(Map<String, Object> authorMap) {
    List<String> ids = stringList(authorMap.get("ids"));

    if (ids.size() > 50) {
        throw new IllegalArgumentException("At most 50 author IDs are allowed");
    }

    String prefix = (String) authorMap.get("namePrefix");
    if (prefix != null && prefix.length() > 80) {
        throw new IllegalArgumentException("namePrefix is too long");
    }

    return new AuthorCriteria(ids, prefix);
}
~~~

For inputs with a stable structure, you can bind to a record with constraints and use `@Valid`:

~~~java
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Size;

public record AuthorFilterInput(
        @Size(max = 50) List<String> ids,
        @Size(max = 80) String namePrefix
) {}

public record BookFilterInput(
        @Size(max = 120) String keyword,
        BookStatus status,
        @Valid AuthorFilterInput author
) {}
~~~

~~~java
@QueryMapping
public List<Book> searchBooks(@Argument("filter") @Valid BookFilterInput filter) {
    return bookService.search(filter);
}
~~~

Bean Validation requires a configured validator in the application context. Using a DTO keeps constraints close to the data structure and avoids rewriting manual type checks on maps.

## 12. Security when handling map arguments

Never pass a map from the client directly into an entity or database query. Doing so can cause mass assignment, allowing clients to try submitting internal properties or unauthorized criteria.

Some principles:

1. Only read keys permitted by the schema and business rules.
2. Use allowlists for sort fields, filter operations, and statuses.
3. Never concatenate map keys/values directly into SQL or JPQL; use parameter binding and safe query builders.
4. Check access permissions in the service/resolver; a map argument is not proof of authorization.
5. Bound list element counts, string lengths, and input depth.
6. Do not log the entire map if it may contain personal information or sensitive data.

If a filter affects tenant scope, obtain the tenant from the authenticated security principal or context and combine it with the client-submitted filter. Never let the client choose a tenant solely via a map key without authorization checks.

## 13. Testing Map arguments with GraphQlTester

You can use `@GraphQlTest` to verify a resolver receives the expected map from a GraphQL request. Example testing `@Argument("filter") Map`:

Test SDL placed in `src/test/resources/graphql/schema.graphqls`:

~~~graphql
input BookFilter {
    keyword: String
}

type Query {
    filterKeyword(filter: BookFilter): String
    argumentSummary(filter: BookFilter, limit: Int): String
}
~~~

Controller receiving a single argument or all arguments:

~~~java
import java.util.Map;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.Arguments;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
class MapArgumentController {

    @QueryMapping
    public String filterKeyword(@Argument("filter") Map<String, Object> filter) {
        return (String) filter.get("keyword");
    }

    @QueryMapping
    public String argumentSummary(@Arguments Map<String, Object> arguments) {
        return arguments.keySet().stream().sorted()
                .collect(java.util.stream.Collectors.joining(","));
    }
}
~~~

Test verifying `@Argument` receives only the `filter` input object while `@Arguments` sees all field-level arguments:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;

@GraphQlTest(MapArgumentController.class)
class MapArgumentTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void distinguishesOneArgumentFromAllArguments() {
        GraphQlTester.Response response = graphQlTester.document("""
                query {
                    filterKeyword(filter: { keyword: "Spring" })
                    argumentSummary(filter: { keyword: "Spring" }, limit: 10)
                }
                """)
            .execute();

        response.errors().verify();
        response.path("filterKeyword")
                .entity(String.class)
                .isEqualTo("Spring");
        response.path("argumentSummary")
                .entity(String.class)
                .isEqualTo("filter,limit");
    }
}
~~~

The test uses a single response to verify both fields. Add test cases for nested maps, lists, null values, omitted arguments, enum coercion, and invalid inputs.

## 14. Common errors

| Symptom | Cause | Fix |
| --- | --- | --- |
| `@Argument Map` contains only one child object | Annotation binds a single named argument, not all arguments | Use `@Arguments Map` if you need the full map |
| Map lacks expected key | Parameter name does not match argument or `-parameters` is missing | Declare `@Argument("name")` explicitly |
| `ClassCastException` when reading nested value | Incorrect assumption about nested type | Check `instanceof` and validate before casting |
| Enum value is not the expected string | Enum has a custom internal value or coercing | Check runtime wiring or bind to the appropriate enum/domain type |
| Cannot distinguish omitted and null | Only checking `Map.get(...)` or using a plain nullable argument | Use `ArgumentValue<T>` for values requiring distinction |
| `@Argument Map` behaves differently from older code | Pre-1.2 behavior changed | From 1.2 onward, use `@Arguments` for the full arguments map |
| Input map with unknown field rejected before resolver | GraphQL schema does not declare that field | Add the field to SDL if valid; Map does not bypass schema validation |
| Map bound straight to entity causes unintended updates | Trusting client data and enabling mass assignment | Convert map through allowlists/criteria DTOs before calling the service |

## 15. Workflow for choosing how to bind arguments

When writing an annotated controller, choose in order:

1. If you only need one argument, use `@Argument("name")` with an appropriate scalar or DTO type.
2. If you need the raw value of one input object, use `@Argument("input") Map<String, Object>`.
3. If you need the raw map of all field-level arguments, use `@Arguments Map<String, Object>`.
4. If you need to bind all arguments into a strongly typed object, use `@Arguments SearchArguments`.
5. If the input has a stable structure and needs validation/safe refactoring, prefer a record/DTO over a map.
6. If you need to distinguish omitted arguments from `null`, use `ArgumentValue<T>`.
7. Convert raw maps into criteria/domain objects after checking types, allowed keys, and business rules.
8. Test the exact map scope, nested values, default values, and invalid inputs using `GraphQlTester`.

Map arguments are useful when flexible input handling is needed, provided you clarify whether the map represents a single argument or all arguments of the field. Using `@Argument` and `@Arguments` properly, combined with type checks and conversion into structured models, keeps controllers flexible while preserving the GraphQL schema as the primary data contract.

## References

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Argument API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/method/annotation/Argument.html)
- [Spring for GraphQL — Arguments API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/method/annotation/Arguments.html)
- [Spring for GraphQL — ArgumentValue API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/ArgumentValue.html)
