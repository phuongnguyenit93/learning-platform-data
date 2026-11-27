# Optional Return Type

## 1. Why does a resolver need to represent results that may not exist?

When a client queries an object by ID, the system may find a record or may not find it. For example, `book(id: "book-42")` may return a book, whereas `book(id: "unknown")` has no corresponding object.

In Java, `Optional<T>` represents a result that may or may not have a value without needing to use `null` as a direct return value. Many Spring Data repositories already use this type for methods finding a single record, such as `findById` returning `Optional<Book>`.

In GraphQL, the absence of data is represented by `null` if the field is declared nullable. GraphQL does not have an `Optional` type in SDL. When a resolver returns `Optional<T>`, GraphQL Java can unwrap this wrapper to obtain the inner value; `Optional.empty()` becomes `null`, while `Optional.of(value)` becomes `value` itself.

Thus, `Optional<T>` is the Java-side representation, while the `!` mark in the schema still determines whether GraphQL accepts a `null` result.

## 2. Declaring nullable fields in SDL

Suppose an API looks up a book by ID:

```graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    isbn: String!
}
```

The return type of `book` is `Book`, without `!`, so the field can return `null` when the book is not found. The `id: ID!` argument is still required and cannot accept `null`.

Query:

```graphql
query FindBook($id: ID!) {
    book(id: $id) {
        id
        title
        isbn
    }
}
```

When the book exists, the response contains the `Book` object. When it does not exist, the response may be:

```json
{
  "data": {
    "book": null
  }
}
```

This is a valid result according to the schema. Not finding a record is not necessarily a GraphQL execution error; it can be the normal outcome of a lookup query.

## 3. Returning `Optional<T>` from `@QueryMapping`

A Spring Data repository typically already returns `Optional<T>` when finding a single record. You can keep that type through the service and resolver:

```java
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository extends JpaRepository<Book, String> {
}
```

Service:

```java
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class BookQueryService {

    private final BookRepository bookRepository;

    public BookQueryService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    public Optional<Book> findById(String id) {
        return bookRepository.findById(id);
    }
}
```

Resolver:

```java
import java.util.Optional;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    private final BookQueryService bookQueryService;

    public BookQueryController(BookQueryService bookQueryService) {
        this.bookQueryService = bookQueryService;
    }

    @QueryMapping
    public Optional<Book> book(@Argument String id) {
        return bookQueryService.findById(id);
    }
}
```

When the resolver returns `Optional<Book>`, GraphQL Java uses the default value unboxing mechanism to extract the inner value. The execution result is equivalent to the resolver returning `Book` when data exists or `null` when `Optional` is empty. Spring for GraphQL registers the controller method as a data fetcher; unboxing `Optional` is part of GraphQL Java's execution mechanism.

This allows the resolver to keep a clean contract with the service. There is no need to call `.get()` and no need to manually convert every case into `null` directly in the controller.

## 4. How are `Optional.empty()` and `Optional.of(value)` handled?

GraphQL Java provides `ValueUnboxer` and its default implementation `DefaultValueUnboxer` to handle wrappers like `java.util.Optional`.

| Java value from resolver | Value after unboxing | GraphQL result with nullable field |
| --- | --- | --- |
| `Optional.of(book)` | `book` | `Book` object |
| `Optional.empty()` | `null` | `null` |
| `null` | `null` | `null` |

Example:

```java
@QueryMapping
public Optional<Book> book(@Argument String id) {
    if ("book-42".equals(id)) {
        return Optional.of(new Book(
            "book-42",
            "Spring for GraphQL",
            "9780000000042"
        ));
    }

    return Optional.empty();
}
```

For ID `book-42`, the client receives the book object. For another ID, the client receives `book: null` if SDL declares the field nullable. `Optional.empty()` does not automatically produce a GraphQL error and does not automatically set the HTTP status to 404.

Do not use `Optional.of(value)` if `value` can be null. If the data source can return null, use `Optional.ofNullable(value)` or better yet keep the `Optional` result from the repository.

## 5. Nullability in SDL remains the deciding rule

`Optional.empty()` is unboxed to `null`. Therefore, if the field is declared non-null, this result violates the schema contract.

Example:

```graphql
type Query {
    book(id: ID!): Book!
}
```

Resolver:

```java
@QueryMapping
public Optional<Book> book(@Argument String id) {
    return bookRepository.findById(id);
}
```

If the repository returns `Optional.empty()`, GraphQL receives a null value for the `Book!` field. GraphQL produces a non-null field execution error and propagates null up to the nearest nullable parent field. Because `book` sits directly under the root `Query`, `data` may become `null`.

Therefore, choose nullability based on business semantics:

- Use `Book` when not found is a normal outcome and the client should receive `null`.
- Use `Book!` when the contract guarantees a book is always present or when not found must be represented as an error.
- If not found is a business error, you can throw a domain exception and map it to a GraphQL error instead of returning `Optional.empty()`.

Do not use `Optional<T>` to avoid designing nullability. The Java wrapper and the GraphQL schema must describe the same data policy.

## 6. Using Optional for nested fields

Optional is also useful for fields of an object type when a relationship may not exist. For example, a book may not yet have an assigned publisher:

```graphql
type Book {
    id: ID!
    title: String!
    publisher: Publisher
}

type Publisher {
    id: ID!
    name: String!
}
```

Resolver:

```java
@Controller
public class BookFieldController {

    private final PublisherRepository publisherRepository;

    public BookFieldController(PublisherRepository publisherRepository) {
        this.publisherRepository = publisherRepository;
    }

    @SchemaMapping(typeName = "Book", field = "publisher")
    public Optional<Publisher> publisher(Book book) {
        return publisherRepository.findById(book.publisherId());
    }
}
```

If there is no corresponding publisher, the `publisher` field returns `null`; other fields of `Book` can still be returned normally. If SDL declares `publisher: Publisher!`, a missing publisher creates a non-null error as in the previous section.

For relationship fields loaded for multiple parent objects, consider `@BatchMapping` or DataLoader to avoid N+1. Returning `Optional` from the resolver only addresses how to represent a potentially absent result; it does not automatically optimize the number of repository calls.

## 7. Optional is different from an empty list

Do not confuse `Optional.empty()` with a collection that has no elements. The two results have different meanings:

```graphql
type Query {
    book(id: ID!): Book
    booksByAuthor(authorId: ID!): [Book!]!
}
```

- `book` looks up one object: not found can return `null` via `Optional.empty()`.
- `booksByAuthor` looks up multiple objects: no matching books should return an empty list `[]`.

Java example:

```java
@QueryMapping
public Optional<Book> book(@Argument String id) {
    return bookRepository.findById(id);
}

@QueryMapping
public List<Book> booksByAuthor(@Argument String authorId) {
    return bookRepository.findAllByAuthorId(authorId);
}
```

With `[Book!]!`, an empty list is a valid value. Do not return `Optional.empty()` to represent a list with no elements, because it becomes `null` and violates the non-null list contract. Use `List.of()` or an appropriate empty collection.

`Optional<List<Book>>` should only be considered when the domain genuinely distinguishes "no collection" from "collection exists but is empty". In most GraphQL list queries, an empty list is a simpler and clearer representation.

## 8. Optional and reactive `Mono<T>` type

Spring for GraphQL supports reactive types such as `Mono<T>` and `Flux<T>` in annotated controllers. For a single result that may not exist, `Mono<T>` can emit one value or complete without emitting a value.

Example:

```java
@QueryMapping
public Mono<Book> book(@Argument String id) {
    return bookReactiveRepository.findById(id);
}
```

If `Mono` emits a `Book`, the field receives that object. If `Mono` completes empty, Spring for GraphQL converts the reactive result into a null completion value for GraphQL to handle according to the field's nullability. This is similar in meaning to `Optional.empty()` for nullable fields.

There is no need to wrap a `Mono<Book>` in `Optional` or use `Mono<Optional<Book>>` unless there is a special domain need. Choose a representation matching the data layer:

| Processing model | Appropriate return type |
| --- | --- |
| Synchronous repository returning a potentially missing single result | `Optional<Book>` |
| Synchronous resolver returning a potentially missing result | `Optional<Book>` or nullable `Book` |
| Reactive repository/service returning an asynchronous single result | `Mono<Book>` |
| Resolver returning multiple reactive results | `Flux<Book>` or `Mono<List<Book>>` depending on contract |

Both `Mono.empty()` and `Optional.empty()` can lead to null in GraphQL, but they belong to two different processing models. Do not switch a reactive flow to blocking just to create an `Optional`.

## 9. Choosing between Optional, null, and exceptions

Three common representations have different meanings:

| Return approach | Meaning | When appropriate |
| --- | --- | --- |
| `Optional.empty()` | No result | Not found is a normal outcome of a nullable field |
| `null` | No value | Simple resolver or legacy API already using nullable returns |
| Throwing an exception | Execution encountered an error | Not found is a business error or a system error needs to be reported to the client |

Example of a lookup that may have no result:

```java
@QueryMapping
public Optional<Book> book(@Argument String id) {
    return bookQueryService.findById(id);
}
```

Example where business rules require the book to exist:

```java
@QueryMapping
public Book requiredBook(@Argument String id) {
    return bookQueryService.findById(id)
        .orElseThrow(() -> new BookNotFoundException(id));
}
```

`BookNotFoundException` can be handled with `@GraphQlExceptionHandler` or `DataFetcherExceptionResolver` to return an error with an appropriate code and message. Keep SDL and exception handling consistent; do not declare a nullable field to represent "normal not found" while also throwing exceptions for every missing data case if the client does not want that behavior.

Do not call `Optional.get()` without checking. That call can throw `NoSuchElementException`, turning a normal absent result into an unintended execution error.

## 10. Optional in input is not the same as Optional in output

In output, `Optional.empty()` is unboxed to null and GraphQL applies field nullability. In input, GraphQL also distinguishes an omitted argument from an argument explicitly passed as `null`.

This matters for partial update Mutations. For example, a client may want to:

- Not send `description`: keep the current description.
- Send `description: null`: clear the current description.
- Send `description: "New text"`: update the description.

A regular `@Argument` parameter does not always preserve the distinction between an omitted value and a null value. Spring for GraphQL provides `ArgumentValue<T>` to represent the value along with a flag indicating whether the argument was omitted.

Example:

```java
@MutationMapping
public Book updateBook(
        @Argument String id,
        @Argument ArgumentValue<String> description) {

    return bookService.updateDescription(
        id,
        description.isOmitted(),
        description.value()
    );
}
```

`ArgumentValue` is suitable when business logic needs to distinguish omitted from explicit null. Do not use `Optional<T>` as a substitute for this mechanism if all three states must be preserved.

## 11. Testing Optional return types with `GraphQlTester`

Test both `Optional.of(value)` and `Optional.empty()` cases to ensure the resolver matches the schema's nullability.

Schema:

```graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
```

Testing the found case:

```java
@SpringBootTest
@AutoConfigureHttpGraphQlTester
class OptionalBookQueryTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void returnsBookWhenPresent() {
        graphQlTester.document("""
            query {
                book(id: "book-42") {
                    id
                    title
                }
            }
            """)
            .execute()
            .path("book.id")
            .entity(String.class)
            .isEqualTo("book-42");
    }

    @Test
    void returnsNullWhenOptionalIsEmpty() {
        graphQlTester.document("""
            query {
                book(id: "missing") {
                    id
                }
            }
            """)
            .execute()
            .path("book")
            .valueIsNull();
    }
}
```

The example assumes the repository or fixture returns `Optional.of(book)` for `book-42` and `Optional.empty()` for `missing`. When testing the not-found case, `GraphQlTester` confirms the field is actually null and the response has no unexpected errors.

Add a separate test for a non-null schema (`Book!`) to confirm `Optional.empty()` produces a GraphQL error and null propagation according to contract. Testing both `Optional.of` and `Optional.empty` values helps detect resolver or schema mismatches.

## 12. Common errors when using Optional

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Client receives null even though repository has data | Service produces `Optional.empty()` incorrectly or queries with wrong key | Check repository and data mapping before returning |
| Query throws non-null error when not found | SDL declares `Book!` field while resolver returns `Optional.empty()` | Make field nullable if absence is normal, or throw an exception per business rules |
| Resolver throws `NoSuchElementException` | Calling `Optional.get()` when no value is present | Return Optional directly, or intentionally use `orElse`, `orElseGet`, or `orElseThrow` |
| List field returns null when no elements exist | Using `Optional.empty()` to represent an empty list | Return an empty collection for non-null list fields |
| API returns inconsistent nulls and errors | Mixing `Optional.empty()` with exceptions for the same case | Clarify whether absence is a normal outcome or a business error |
| Resolver uses confusing multiple wrapper layers | Unnecessarily combining `Optional`, `Mono`, `CompletableFuture` | Choose one type matching the synchronous or reactive model |
| Mutation does not distinguish omitted from null | Using `Optional<T>` for partial update input | Use `ArgumentValue<T>` when both states need to be distinguished |
| Thinking Optional makes a GraphQL field nullable | Ignoring the type in SDL | Determine nullability via `T` or `T!` in the schema |

## 13. Checklist for designing Optional return types

- [ ] Use `Optional<T>` for a single result that may not exist.
- [ ] Declare the field nullable in SDL if `Optional.empty()` is a valid result.
- [ ] Understand that GraphQL Java unboxes `Optional.of(value)` to value and `Optional.empty()` to null.
- [ ] Do not call `Optional.get()` without checking.
- [ ] Do not use an empty Optional instead of an empty list.
- [ ] Clearly choose between normal absence and a business error.
- [ ] Use `Mono<T>` when the data layer is reactive instead of switching to blocking.
- [ ] Do not overuse nested wrappers like `Mono<Optional<T>>`.
- [ ] Use `ArgumentValue<T>` for inputs that need to distinguish omitted from explicit null.
- [ ] Test value-present, empty Optional, and non-null propagation cases.

## Conclusion

`Optional<T>` is a useful return type when a resolver needs to represent an object that may not exist. With Spring for GraphQL, controller methods can return value types handled by GraphQL Java; `DefaultValueUnboxer` unwraps `Optional.of(value)` to value and `Optional.empty()` to null. SDL remains the source of truth deciding whether a field accepts null.

Use nullable fields when not found is a normal outcome, use exceptions when it is a business error, and use empty lists for list queries with no elements. For reactive resolvers, `Mono<T>` already represents a potentially absent value. For partial update inputs, use `ArgumentValue<T>` when you need to distinguish an omitted argument from an argument explicitly passed as null.

## References

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [GraphQL Java — ValueUnboxer API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/execution/ValueUnboxer.html)
- [GraphQL Specification — Type System and Non-Null](https://spec.graphql.org/October2021/#sec-Non-Null)
