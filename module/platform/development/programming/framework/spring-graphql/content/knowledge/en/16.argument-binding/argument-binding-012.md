# Distinguishing omitted arguments from null in GraphQL

In GraphQL, an argument or input field can be omitted, sent with a `null` value, or sent with a concrete value. These three states carry different meanings. Particularly in partial-update mutations, the server often needs to know whether the client did not mention a field at all or actively requested clearing that field's value.

Spring for GraphQL provides `ArgumentValue<T>` to preserve the distinction between an omitted argument and an argument explicitly sent as null. This wrapper can be used on resolver-level arguments and on fields inside input objects. By understanding GraphQL's semantics properly and preserving this state across the service boundary, an application can implement partial updates without accidentally deleting data.

After this lesson, you will be able to:

- Distinguish omitted, explicit null, and provided states for arguments/input fields.
- Understand how GraphQL applies default values to arguments, variables, and input fields.
- Recognize when non-null schemas reject omitted or null values before reaching the resolver.
- Use `ArgumentValue<T>` on top-level arguments and nested input objects.
- Preserve semantics when translating GraphQL inputs into application commands.
- Design partial-update mutations with clear rules.
- Test all three states using `GraphQlTester`.

## 1. Three states of an input field

Consider the input type:

```graphql
input UpdateBookInput {
    title: String
    subtitle: String
}

type Mutation {
    updateBook(id: ID!, input: UpdateBookInput!): Book!
}
```

For the `subtitle` field, the client can send three forms:

```graphql
# 1. Omit subtitle
mutation {
    updateBook(id: "book-42", input: { title: "New title" }) {
        id
    }
}

# 2. Send subtitle with null value
mutation {
    updateBook(id: "book-42", input: {
        title: "New title"
        subtitle: null
    }) {
        id
    }
}

# 3. Send subtitle with a value
mutation {
    updateBook(id: "book-42", input: {
        title: "New title"
        subtitle: "A practical guide"
    }) {
        id
    }
}
```

These three cases can be interpreted as follows:

| State | Client intent | Common handling in partial updates |
| --- | --- | --- |
| Omitted | Client did not mention the field | Keep the current value unchanged |
| Explicit `null` | Client actively sent null | Clear the value or handle per business rules |
| Provided value | Client sent a new value | Replace the current value |

GraphQL preserves the difference between an absent field and a field with a null value in the coerced input. The problem typically arises at the Java object binding step: if both states are assigned to `null`, the application loses the information the client sent.

## 2. Omitted does not mean null

Omitted means the key does not appear in the input object or the argument was not supplied. Explicit null means the key is present and its value is `null`.

For example, the following two JSON variables payloads are not identical:

```json
{
  "input": {
    "title": "New title"
  }
}
```

```json
{
  "input": {
    "title": "New title",
    "subtitle": null
  }
}
```

In the first object, `subtitle` is omitted. In the second object, the client sends `subtitle` with a null value. If the API uses `null` to clear the subtitle, the two requests must produce two different outcomes.

This also applies to field-level arguments:

```graphql
type Query {
    books(status: BookStatus): [Book!]!
}
```

`books` can be called without passing `status`, or by passing `status: null`. If the application distinguishes these two cases, the resolver must retain information about whether the argument was present.

## 3. Default values change the semantics of omitted

GraphQL allows declaring default values on arguments, variables, and input fields. Defaults are used when the corresponding value is omitted; an explicit null remains null if the type allows null.

Default on an argument:

```graphql
type Query {
    books(limit: Int = 20): [Book!]!
}
```

When the client omits `limit`, the resolver receives the default value `20`. If the client sends `limit: null`, the default is not applied and the resolver receives null because the argument is nullable.

Default on a variable:

```graphql
query Books($limit: Int = 20) {
    books(limit: $limit) {
        id
        title
    }
}
```

If the client does not send the `limit` variable, the variable's default `20` is applied. If the client sends `"limit": null`, the null value is used and the default does not replace it.

Default on an input field:

```graphql
input BookFilter {
    status: BookStatus = PUBLISHED
}
```

When `status` is omitted, input coercion applies `PUBLISHED`. Therefore, if the goal is to detect an unsupplied field to leave data unchanged, avoid declaring a default on that patch field. A default can erase the "leave unchanged" signal before the resolver sees the input.

## 4. Non-null rejects both omitted and null

With a non-null type, the client must provide a non-null value:

```graphql
input CreateBookInput {
    title: String!
}
```

The following requests are invalid:

```graphql
# Missing title
mutation {
    createBook(input: {}) {
        id
    }
}

# title is null
mutation {
    createBook(input: { title: null }) {
        id
    }
}
```

GraphQL rejects the input during validation/coercion before calling the resolver. This is the right choice for creation operations where `title` is mandatory.

For partial updates, a field may be allowed to be omitted while disallowing null. If you declare `String!`, GraphQL will reject both cases. If you need to allow omission and handle explicit null yourself, declare the field nullable and check for null in the service. For example, `title` can be omitted to keep it unchanged, but if the client sends null, the service returns a business error because a book must have a title.

## 5. ArgumentValue<T> in Spring for GraphQL

If a resolver method directly accepts a nullable type like `String`, both omitted and explicit null bind to `null`. `ArgumentValue<T>` additionally retains a flag indicating whether the argument was omitted.

Example with a top-level argument:

```graphql
type Query {
    books(status: BookStatus): [Book!]!
}
```

```java
@QueryMapping
public List<BookView> books(
        @Argument("status") ArgumentValue<BookStatus> status) {

    if (status.isOmitted()) {
        return bookService.findAll();
    }

    if (status.value() == null) {
        return bookService.findWithoutStatus();
    }

    return bookService.findByStatus(status.value());
}
```

In this example:

- `isOmitted()` is `true` when the client did not supply the `status` argument.
- `isOmitted()` is `false` when the client supplied the argument, even if the value sent was null.
- `value()` returns the bound value; for explicit null, this value is null.

If the argument has a default value in the SDL, GraphQL applies the default when the client omits the argument. In that case the resolver receives the default value instead of an omitted state. Hence, only declare a default when that is truly the desired semantics.

## 6. Using ArgumentValue inside input objects

`ArgumentValue<T>` can also be used for fields of a record or DTO receiving an input object. This is an important case for partial-update mutations:

```graphql
input UpdateBookInput {
    title: String
    subtitle: String
}

type Mutation {
    updateBook(id: ID!, input: UpdateBookInput!): Book!
}
```

Java record:

```java
public record UpdateBookInput(
        ArgumentValue<String> title,
        ArgumentValue<String> subtitle) {
}
```

Controller:

```java
@MutationMapping
public BookView updateBook(
        @Argument("id") String id,
        @Argument("input") UpdateBookInput input) {

    return bookService.update(new UpdateBookCommand(
            id,
            toPatch(input.title()),
            toPatch(input.subtitle())));
}

private FieldPatch<String> toPatch(ArgumentValue<String> value) {
    if (value.isOmitted()) {
        return FieldPatch.omitted();
    }
    return FieldPatch.supplied(value.value());
}
```

`ArgumentValue` preserves the state at Spring for GraphQL's binding step. When passing data to the application service, translate it into an application command type so the service does not depend on GraphQL classes.

## 7. Preserving omitted state in application commands

A simple command can represent a field patch using two pieces of information: whether the field was supplied and what value was supplied.

```java
public record FieldPatch<T>(boolean supplied, T value) {

    public static <T> FieldPatch<T> omitted() {
        return new FieldPatch<>(false, null);
    }

    public static <T> FieldPatch<T> supplied(T value) {
        return new FieldPatch<>(true, value);
    }
}

public record UpdateBookCommand(
        String bookId,
        FieldPatch<String> title,
        FieldPatch<String> subtitle) {
}
```

Now the service can cleanly distinguish all three states:

```java
@Transactional
public BookView update(UpdateBookCommand command) {
    BookEntity book = bookRepository.findById(command.bookId())
            .orElseThrow(() -> new BookNotFoundException(command.bookId()));

    if (command.title().supplied()) {
        String title = command.title().value();
        if (title == null || title.isBlank()) {
            throw new InvalidBookTitleException();
        }
        book.rename(title);
    }

    if (command.subtitle().supplied()) {
        book.changeSubtitle(command.subtitle().value());
    }

    return bookMapper.toView(book);
}
```

Result:

- `title` omitted: keep the current title.
- `title` explicit null: reject because title cannot be null.
- `title` with valid string: update title.
- `subtitle` omitted: keep the current subtitle.
- `subtitle` explicit null: clear subtitle.
- `subtitle` with string: replace subtitle.

`FieldPatch` is just one option for representing the command. A project can use a sealed interface or a dedicated `PatchField<T>` type to make the states even clearer. What matters is not losing presence information when crossing the service boundary.

## 8. Why Optional<T> is usually not enough

`Optional<T>` represents the presence or absence of a value. However, for partial updates, the application needs at least three states: omitted, explicit null, and a concrete value.

If both omitted and explicit null are converted into `Optional.empty()`, the service cannot tell whether the client intended to keep the field unchanged or clear it. `Optional` remains useful when only representing presence/absence of a value, but it does not replace `ArgumentValue<T>` when you need to preserve GraphQL input presence semantics.

Similarly, a plain DTO:

```java
public record UpdateBookInput(String title, String subtitle) {
}
```

can receive `null` for both an omitted field and an explicit null field. This DTO suffices if the application intentionally treats both cases identically. If business logic needs to distinguish them, use `ArgumentValue<T>` on fields requiring presence tracking or bind into a structure that preserves key presence.

## 9. Reading presence at the DataFetchingEnvironment level

In a resolver that needs lower-level access to the GraphQL Java API, you can inspect the argument map and check whether a key exists:

```java
@QueryMapping
public List<BookView> books(DataFetchingEnvironment environment) {
    Map<String, Object> arguments = environment.getArguments();

    if (!arguments.containsKey("status")) {
        return bookService.findAll();
    }

    BookStatus status = (BookStatus) arguments.get("status");
    if (status == null) {
        return bookService.findWithoutStatus();
    }

    return bookService.findByStatus(status);
}
```

`containsKey` distinguishes an absent key from a key with a null value. This approach is useful when reading multiple dynamic arguments or manipulating map structures. With annotated controllers and strongly typed parameters, `ArgumentValue<T>` is usually more concise and easier to test.

For nested input objects, you must check keys on the corresponding nested map. Avoid rewriting an entire resolver to manipulate maps manually if a strongly typed DTO meets the requirement.

## 10. Variables and omitted/null

GraphQL variables are sent as JSON. Consider the operation:

```graphql
mutation UpdateBook($id: ID!, $input: UpdateBookInput!) {
    updateBook(id: $id, input: $input) {
        id
        title
        subtitle
    }
}
```

Variables without the `subtitle` key:

```json
{
  "id": "book-42",
  "input": {
    "title": "New title"
  }
}
```

Variables with the `subtitle` key set to null:

```json
{
  "id": "book-42",
  "input": {
    "title": "New title",
    "subtitle": null
  }
}
```

If an operation references a nullable variable that the client does not send and the variable has no default, the variable is undefined. When that variable is used as the value of an input object field, that field can be omitted from the input after coercion; an explicit JSON null remains a provided value. Therefore, inspect both how the operation declares variables and the JSON object the client sends.

Do not confuse a JSON object having a key with a null value with a JSON object lacking the key. Client code sometimes automatically serializes undefined properties as null; this can cause the server to interpret it as a request to clear the field. Inspect the actual payload sent over HTTP.

## 11. Do not put defaults on patch fields if omission means leave unchanged

Consider the schema:

```graphql
input UpdateBookInput {
    subtitle: String = "Untitled"
}
```

If the client omits `subtitle`, GraphQL applies the default `"Untitled"`. The service will receive a provided value instead of an omitted state and could overwrite the existing subtitle.

For inputs intended for partial updates, usually declare fields nullable without defaults:

```graphql
input UpdateBookInput {
    subtitle: String
}
```

Then use `ArgumentValue<String>` to treat omitted as leave unchanged and null as clear. If you want defaults for creation operations, declare defaults on a dedicated create input type or apply defaults in the service when the field is actually omitted.

Separating `CreateBookInput` and `UpdateBookInput` generally makes semantics clearer because creation and partial updates have different required/optional rules.

## 12. Validation when fields can be omitted or null

Bean Validation must align with the chosen semantics. If a nullable field is used to request clearing a value, placing `@NotNull` directly on that field will make clearing impossible. If an omitted field is allowed to preserve existing data while explicit null is invalid, validation must run conditionally based on presence.

Example:

```java
if (!input.title().isOmitted()) {
    String title = input.title().value();
    if (title == null || title.isBlank()) {
        throw new InvalidBookTitleException();
    }
}
```

Rules involving multiple fields or the resource's current state should be checked in the service/domain. For example, a client may omit `status`, but if they send `status: null`, the domain disallows clearing the status. The service must validate and return a business error.

For non-null fields in the SDL, GraphQL already rejects omitted and null before reaching the resolver. For nullable fields, application validation determines whether null is acceptable according to business rules.

## 13. Testing all three states with GraphQlTester

`GraphQlTester` lets you pass variables as maps to precisely test whether a key is present.

Omitted case:

```java
Map<String, Object> input = new HashMap<>();
input.put("title", "New title");

graphQlTester.document("""
        mutation UpdateBook($id: ID!, $input: UpdateBookInput!) {
            updateBook(id: $id, input: $input) {
                id
                title
                subtitle
            }
        }
        """)
    .variable("id", "book-42")
    .variable("input", input)
    .execute();
```

Explicit null case:

```java
Map<String, Object> input = new HashMap<>();
input.put("title", "New title");
input.put("subtitle", null);

graphQlTester.document("""
        mutation UpdateBook($id: ID!, $input: UpdateBookInput!) {
            updateBook(id: $id, input: $input) {
                id
                title
                subtitle
            }
        }
        """)
    .variable("id", "book-42")
    .variable("input", input)
    .execute();
```

Use `HashMap` in explicit null tests because `Map.of(...)` does not allow null values. For all three cases, verify that the service receives the expected command and that the final persisted data follows the intended semantics.

Tests to include:

1. An omitted field is marked omitted and leaves existing data unchanged.
2. An explicit null is preserved and handled according to clearing or validation rules.
3. A concrete value is bound and updated properly.
4. A default value is applied when omitted if the schema declares a default.
5. Non-null arguments/input fields are rejected before the resolver runs when omitted or null.
6. An unsent variable behaves differently from a variable sent as explicit null.
7. Nested input objects preserve presence for fields being patched.
8. Validation errors or business errors are returned according to the GraphQL contract.

## 14. Common pitfalls

- **Treating omitted the same as null:** can erase data when the client only meant to update another field.
- **Binding into a regular nullable DTO and trying to recover presence:** key presence information is already lost; use `ArgumentValue<T>` at the binding step.
- **Using `Optional<T>` for partial updates:** collapses explicit null and omitted into the same state.
- **Declaring defaults on patch fields:** omission gets replaced by the default and can overwrite existing data.
- **Marking a field with `!` while expecting omission to be allowed:** non-null forces the client to supply a non-null value.
- **Using Java primitives for nullable inputs:** primitives like `int` cannot represent null; use wrappers like `Integer` when needed.
- **Placing `@NotNull` on a clearable field:** validation will reject explicit null even when it is a valid operation.
- **Serializing undefined properties as null on the client:** the server misinterprets them as requests to clear values.
- **Passing `ArgumentValue` deep into domain/service layers:** couples the application layer to Spring for GraphQL; convert to a dedicated command type.
- **Only testing the final value:** verify all three states and confirm the service is invoked with the right command.

## 15. Design workflow for omitted and null arguments

When designing queries or mutations with optional inputs, follow these steps:

1. Determine which fields may be omitted, which allow explicit null, and which are required.
2. Choose nullability in the SDL per contract; use non-null when both omitted and null must be rejected.
3. Only declare a default if omission should genuinely be replaced with a default value.
4. For partial updates, avoid defaults on fields where omitted means keep unchanged.
5. Use `ArgumentValue<T>` on top-level arguments or nested input fields that need presence tracking.
6. Translate states into a strongly typed application command before calling the service.
7. Perform conditional validation and update rules in the service/domain.
8. Check client JSON serialization so omitted fields do not unintentionally become null.
9. Test omitted, explicit null, concrete values, defaults, and non-null validation using `GraphQlTester`.

Omitted and explicit null are two distinct signals in a GraphQL contract. For creation operations, non-null and default values help control required data; for partial updates, `ArgumentValue<T>` lets Spring for GraphQL preserve whether the client supplied a field. Passing presence semantics through application commands and testing all three states allows services to preserve, clear, or update data accurately according to client intent.

## References

- [GraphQL Specification — Input Objects](https://spec.graphql.org/October2021/#sec-Input-Objects)
- [GraphQL Specification — Input Coercion](https://spec.graphql.org/October2021/#sec-Input-Coercion)
- [Spring for GraphQL — Argument Binding](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.arguments)
- [Spring for GraphQL — ArgumentValue API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/ArgumentValue.html)
- [Spring for GraphQL — GraphQlTester](https://docs.spring.io/spring-graphql/reference/testing.html)
