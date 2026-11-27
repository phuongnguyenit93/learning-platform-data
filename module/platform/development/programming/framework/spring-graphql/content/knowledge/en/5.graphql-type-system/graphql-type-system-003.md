# Enum types in GraphQL

An enum type (enumeration type) represents a finite set of values allowed by a GraphQL API. Instead of accepting an arbitrary string like `"published"`, the schema can explicitly declare valid statuses such as `DRAFT`, `IN_REVIEW`, and `PUBLISHED`. GraphQL uses this set of values to validate input, describe output, and help clients understand the exact options supported by the server.

In Spring for GraphQL, enums are declared in SDL and can be mapped to a Java `enum` so resolvers receive, process, and return type-safe data. When an enum name in the API differs from the Java constant name or database storage value, GraphQL Java lets you configure the mapping through `RuntimeWiringConfigurer`.

After this lesson, you will be able to:

- Declare enums and enum values in GraphQL SDL.
- Use enums in output fields, arguments, and input objects.
- Pass enums in GraphQL documents and JSON variables using the correct syntax.
- Map GraphQL enums to Java enums in Spring for GraphQL.
- Decouple public enum names from internal storage codes.
- Design nullability, deprecation, tests, and safe enum changes.

## 1. An enum is a scalar-like type with a finite set of values

A GraphQL enum is a leaf type, similar to a scalar in that clients receive a single value and cannot select subfields inside it. The difference is that scalars usually represent a broad domain of values, whereas an enum only accepts the names defined in the schema.

For example, a book can be in one of four states:

```graphql
enum BookStatus {
    DRAFT
    IN_REVIEW
    PUBLISHED
    ARCHIVED
}

type Book {
    id: ID!
    title: String!
    status: BookStatus!
}
```

`BookStatus` is the enum type name. `DRAFT`, `IN_REVIEW`, `PUBLISHED`, and `ARCHIVED` are the enum values. The `Book.status` field can hold only one of these values and cannot return an arbitrary string like `"WAITING"` if that value is not declared.

Enum values are GraphQL names and are case-sensitive. Names must follow GraphQL naming rules; do not use the reserved literals `true`, `false`, or `null` as enum values. An enum must have at least one value, and all values within the same enum must have unique names.

## 2. Declaring enums in SDL

Basic syntax:

```graphql
enum EnumTypeName {
    VALUE_ONE
    VALUE_TWO
    VALUE_THREE
}
```

Example enum for orders:

```graphql
enum OrderStatus {
    PENDING
    CONFIRMED
    SHIPPING
    DELIVERED
    CANCELLED
}
```

Each enum value can have a description to explain its business meaning:

```graphql
"""Processing status of an order."""
enum OrderStatus {
    """The order has been created and is awaiting confirmation."""
    PENDING

    """The order has been confirmed."""
    CONFIRMED

    """The order is currently being shipped."""
    SHIPPING

    """The order has been delivered successfully."""
    DELIVERED

    """The order has been cancelled."""
    CANCELLED
}
```

Descriptions make the schema self-documenting and can be read via introspection. If the business rules are complex, explain them further in API documentation rather than creating overly long enum names or expecting the value name alone to convey the full meaning.

## 3. Using enums in output fields

Enums are commonly used as return types for object fields:

```graphql
type Product {
    id: ID!
    name: String!
    availability: Availability!
}

enum Availability {
    IN_STOCK
    OUT_OF_STOCK
    PREORDER
}
```

Clients can select an enum just like a regular field:

```graphql
query {
    product(id: "p-100") {
        id
        name
        availability
    }
}
```

The response looks like:

```json
{
  "data": {
    "product": {
      "id": "p-100",
      "name": "Mechanical Keyboard",
      "availability": "IN_STOCK"
    }
  }
}
```

In the JSON response, the enum is represented as a string of the value name. However, in a GraphQL operation document, an enum literal is an unquoted token. Clients cannot request subfields on an enum such as `availability { code }`, because an enum is a leaf type.

The resolver must return a value that the GraphQL enum type can serialize into one of the declared values. If the server returns an unmappable value, GraphQL produces an execution error for that field. For a non-null field, the error can propagate up to the parent field according to null propagation rules.

## 4. Using enums as arguments for filtering data

Enums are very useful for filters with a fixed set of choices:

```graphql
enum BookStatus {
    DRAFT
    IN_REVIEW
    PUBLISHED
    ARCHIVED
}

type Query {
    books(status: BookStatus): [Book!]!
}
```

Clients can pass an enum literal directly:

```graphql
query {
    books(status: PUBLISHED) {
        id
        title
    }
}
```

Do not put enum literals in double quotes. `PUBLISHED` is an enum value; `"PUBLISHED"` is a string literal and is invalid where an enum type is required.

To filter by multiple statuses, use a list of enums:

```graphql
type Query {
    booksByStatuses(statuses: [BookStatus!]!): [Book!]!
}
```

Operation:

```graphql
query {
    booksByStatuses(statuses: [DRAFT, IN_REVIEW]) {
        id
        title
    }
}
```

`[BookStatus!]!` requires the argument to be a non-null list where each element is also non-null. The list can be empty unless the resolver or business validation requires at least one element; SDL has no standard syntax to require a list to contain a minimum of one item.

## 5. Enums in input objects and mutations

An enum can be a field of an input object, allowing mutations to receive structured data:

```graphql
enum BookStatus {
    DRAFT
    IN_REVIEW
    PUBLISHED
    ARCHIVED
}

input UpdateBookInput {
    title: String
    status: BookStatus
}

type Mutation {
    updateBook(id: ID!, input: UpdateBookInput!): Book!
}
```

Clients can update the status:

```graphql
mutation {
    updateBook(
        id: "book-42"
        input: { status: PUBLISHED }
    ) {
        id
        status
    }
}
```

The schema verifies that `status` is a valid enum value before the resolver executes. If a client sends a nonexistent name, the request is rejected during input coercion/validation; the resolver does not need to re-implement the list of valid values.

For partial update mutations, a nullable enum field can have three states that need to be distinguished: the client omits the field, the client sends `null`, or the client sends an enum value. If the business logic needs to distinguish "leave status unchanged" from "clear status value", use Spring for GraphQL's `ArgumentValue<T>` or an appropriate input model to detect omitted fields versus explicitly passed `null`.

## 6. Enum literals and JSON variables

GraphQL documents and JSON variables represent enums with different syntax.

In a GraphQL document, an enum is an unquoted literal:

```graphql
query FindBooks($status: BookStatus!) {
    books(status: $status) {
        id
        title
    }
}
```

When passing variables via JSON, the enum value is sent as a JSON string containing the exact enum name:

```json
{
  "status": "PUBLISHED"
}
```

This does not mean enum and String are the same type. JSON does not have a dedicated enum type, so the variable value is encoded as a string; GraphQL still uses the `$status: BookStatus!` declaration to verify that the name belongs to the enum.

Some invalid examples:

```graphql
# Wrong: string literal is not an enum literal
books(status: "PUBLISHED")

# Wrong: value is not declared in BookStatus
books(status: WAITING_FOR_REVIEW)
```

Enum names must match the SDL exactly. `published`, `Published`, and `PUBLISHED` are three distinct names.

## 7. Mapping enums to Java enums in Spring for GraphQL

In Java, enums are typically represented with `enum`:

```java
public enum BookStatus {
    DRAFT,
    IN_REVIEW,
    PUBLISHED,
    ARCHIVED
}
```

For a Java enum whose constants match the GraphQL names, you can use `NaturalEnumValuesProvider` to map each GraphQL enum value to the corresponding Java enum constant:

```java
@Configuration
public class GraphQlEnumConfiguration {

    @Bean
    RuntimeWiringConfigurer bookStatusEnumWiring() {
        return wiringBuilder -> wiringBuilder.type(
                "BookStatus",
                typeWiring -> typeWiring.enumValues(
                        new NaturalEnumValuesProvider<>(BookStatus.class)));
    }
}
```

Spring Boot automatically detects `RuntimeWiringConfigurer` beans and includes this configuration when building the GraphQL schema. `NaturalEnumValuesProvider` maps enum names in the SDL to Java enum constants with the same name. This allows resolvers to accept and return `BookStatus` directly instead of handling strings in multiple places.

Resolvers can use the enum directly:

```java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books(@Argument("status") BookStatus status) {
        return status == null
                ? bookService.findAll()
                : bookService.findByStatus(status);
    }

    @MutationMapping
    public Book publishBook(@Argument("id") String id) {
        return bookService.changeStatus(id, BookStatus.PUBLISHED);
    }
}
```

`@Argument("status")` binds the GraphQL argument to the Java parameter. Input binding is performed by Spring for GraphQL via `GraphQlArgumentBinder`; simple types can be converted using the conversion service, while input objects are bound to the constructor or properties of the target object.

Without a configured enum provider, GraphQL Java typically represents enum values at runtime by their GraphQL name. When you want resolvers and models to use a Java enum directly on both input and output paths, configuring an explicit provider keeps the mapping contract clear and avoids serialization errors caused by both sides using different internal value types.

## 8. Mapping when GraphQL names differ from Java names

Public names in the schema do not have to match Java constant names. For example, the API may want to use `UNDER_REVIEW`, while the domain model uses `REVIEW`:

```graphql
enum BookStatus {
    DRAFT
    UNDER_REVIEW
    PUBLISHED
}
```

```java
public enum BookStatus {
    DRAFT,
    REVIEW,
    PUBLISHED
}
```

In that case, provide a custom mapping using `enumValues`:

```java
@Configuration
public class GraphQlEnumConfiguration {

    @Bean
    RuntimeWiringConfigurer bookStatusEnumWiring() {
        return wiringBuilder -> wiringBuilder.type(
                "BookStatus",
                typeWiring -> typeWiring.enumValues(graphQlValue -> switch (graphQlValue) {
                    case "DRAFT" -> BookStatus.DRAFT;
                    case "UNDER_REVIEW" -> BookStatus.REVIEW;
                    case "PUBLISHED" -> BookStatus.PUBLISHED;
                    default -> throw new IllegalArgumentException(
                            "Unsupported BookStatus: " + graphQlValue);
                }));
    }
}
```

This mapping is used when the schema is built so that each GraphQL enum value has a corresponding runtime value. When serializing output, GraphQL Java relies on the registered mapping to convert the runtime value back to the public name in the SDL. Declare every enum value completely; do not leave a value unmapped or accidentally map multiple values to the same runtime value if they must remain distinct.

When names match, `NaturalEnumValuesProvider` is more concise. When names differ or you need to map to another internal object, use a custom `EnumValuesProvider` via `enumValues`.

## 9. Decoupling public enums from storage codes

Do not let database storage details directly dictate public enum names. For example, a legacy system stores statuses using the codes `D`, `R`, and `P`:

```java
public enum BookStatus {
    DRAFT("D"),
    REVIEW("R"),
    PUBLISHED("P");

    private final String databaseCode;

    BookStatus(String databaseCode) {
        this.databaseCode = databaseCode;
    }

    public String databaseCode() {
        return databaseCode;
    }
}
```

GraphQL can still publish clear, readable names:

```graphql
enum BookStatus {
    DRAFT
    UNDER_REVIEW
    PUBLISHED
}
```

Resolvers work with `BookStatus`; the service or repository translates the enum to the storage code. With JPA, you can use an `AttributeConverter`:

```java
@Converter
public class BookStatusConverter
        implements AttributeConverter<BookStatus, String> {

    @Override
    public String convertToDatabaseColumn(BookStatus status) {
        return status == null ? null : status.databaseCode();
    }

    @Override
    public BookStatus convertToEntityAttribute(String code) {
        if (code == null) {
            return null;
        }

        return Arrays.stream(BookStatus.values())
                .filter(status -> status.databaseCode().equals(code))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException(
                        "Unknown BookStatus database code: " + code));
    }
}
```

```java
@Entity
public class BookEntity {

    @Convert(converter = BookStatusConverter.class)
    private BookStatus status;
}
```

This way, renaming a public enum value does not force you to change database codes. Conversely, storage code changes can also be handled in the converter without exposing those details to GraphQL clients.

If using `@Enumerated(EnumType.STRING)`, JPA stores the Java constant name; renaming a constant may require a data migration. Avoid `EnumType.ORDINAL` for long-lived data because the database stores the numeric position of the constant; adding or reordering constants can silently change the meaning of existing data.

## 10. Nullability and default values for enums

Enums follow the same nullability rules as other GraphQL types:

```graphql
type Book {
    status: BookStatus
    requiredStatus: BookStatus!
}

type Query {
    books(status: BookStatus = PUBLISHED): [Book!]!
}
```

- `status: BookStatus` can return `null`.
- `requiredStatus: BookStatus!` must return a valid enum value.
- `status: BookStatus = PUBLISHED` uses `PUBLISHED` when the argument is omitted.

Default enum values in SDL are written as enum literals, without double quotes. If a client explicitly sends `null` for a nullable argument, the default value is not applied; the resolver receives `null` per the field's contract.

Do not use a placeholder enum value such as `UNKNOWN` merely to replace all null cases if the business needs to distinguish "undetermined", "not applicable", and "missing data". Clarify whether those states are truly distinct domain values or simply absent data.

## 11. Deprecating enum values

When an enum value is no longer recommended, you can mark it with `@deprecated`:

```graphql
enum PaymentMethod {
    CARD
    BANK_TRANSFER
    CASH @deprecated(reason: "Use a supported electronic payment method.")
}
```

A deprecated value still exists in the schema and can still be sent or received by older clients. This directive lets introspection tools and documentation signal that the value should be replaced; it does not automatically reject requests using that value.

If you want to stop accepting an enum value, enforce that policy in the resolver/service and plan its removal according to your compatibility versioning policy. Simply deleting a value from SDL will invalidate older operations that send that value.

## 12. When should you use an enum?

An enum is a good fit when the set of values:

- Is finite and controlled by the server.
- Has stable business semantics that can be clearly named.
- Needs to be validated before the resolver processes it.
- Can be used by clients to build dropdowns, filters, or branching logic.

Good examples: order status, account type, priority level, shipping method, or sort direction.

An enum is not a good fit when values are user-generated, change frequently, or depend on runtime data. For example, a list of countries updated by an admin system may need a `Country` object type with `code` and `name` instead of an enum if the API needs additional metadata or allows catalog updates without changing the schema.

| Need | Type to consider | Reason |
| --- | --- | --- |
| Fixed set of statuses | Enum | GraphQL validates allowed values |
| User-entered text | `String` | Domain of values is unbounded |
| Catalog with ID and metadata | Object type | Multiple fields can be queried |
| Unique identifier | `ID` | Represents identity, not a set of choices |
| Values changing via configuration | Object type or suitable scalar | No need to modify schema whenever the list changes |

Do not use enums as an authorization mechanism. Enums describe valid values in the API; user permissions must be checked on the server based on identity and request context.

## 13. Testing enums in GraphQL

You should test both enum input and output through real operations. With `GraphQlTester`, you can send a query using an enum literal:

```java
graphQlTester.document("""
        query {
            books(status: PUBLISHED) {
                id
                status
            }
        }
        """)
    .execute()
    .path("books[0].status")
    .entity(String.class)
    .isEqualTo("PUBLISHED");
```

Cases to include in tests:

1. Valid enum literals bind to the expected Java/domain value.
2. Nonexistent enum values are rejected by GraphQL before invoking the resolver.
3. Enums returned by resolvers are serialized to the expected public name.
4. Enums inside input objects and enum lists bind properly.
5. Custom mappings between SDL names and Java enums work for both input and output.
6. Nulls and default values adhere to schema declarations.
7. Deprecated enum values preserve intended compatible behavior during the transition period.

For enums using custom database codes, test the converter for every valid code and unsupported code. This helps catch legacy data issues before they surface as serialization errors in GraphQL responses.

## 14. Common mistakes

- **Putting enum literals in double quotes:** `status: "PUBLISHED"` is a string, not an enum literal in a GraphQL document.
- **Using an undeclared value:** GraphQL rejects the input before the resolver runs.
- **Case mismatch:** enum names must match the SDL exactly.
- **Java enum mismatching the mapping:** resolvers may receive or return unserializable values if an appropriate provider is not configured.
- **Using ordinals as storage codes:** adding or reordering constants can alter the meaning of existing data.
- **Removing enum values still used by clients:** older operations become invalid.
- **Using enums for frequently changing catalogs:** every new option requires changing and releasing the schema.
- **Confusing `@deprecated` with disabling:** the directive only marks a value as no longer recommended; it does not block requests by itself.

## 15. Design and implementation workflow for enums

When adding an enum to Spring for GraphQL, follow these steps:

1. Determine whether the set of choices is truly finite and stable.
2. Name the enum type and enum values consistently; write descriptions for values that could be ambiguous.
3. Use the enum in output fields, arguments, or input objects according to business needs.
4. Decide on nullability and default values; do not use `UNKNOWN` to mask every missing-data case.
5. Create the corresponding Java enum; if SDL and Java names match, consider `NaturalEnumValuesProvider`.
6. If names differ or the database uses custom codes, declare an explicit mapping and a persistence-layer converter.
7. Test input, output, lists, nulls, defaults, and invalid enum values.
8. When changing the value set, assess active clients and use `@deprecated` for a transition period.

Enums make the GraphQL contract clearer by restricting data to a named set of choices. When SDL is combined with Java enums and appropriate mappings in Spring for GraphQL, the application can validate input early, keep data types consistent, and decouple public names from storage details. Use enums for genuinely finite business concepts and manage value evolution as an API contract change.

## References

- [GraphQL Specification — Enums](https://spec.graphql.org/October2021/#sec-Enums)
- [GraphQL Java — Data mapping](https://graphql-java.com/documentation/master/data-mapping/)
- [GraphQL Java — NaturalEnumValuesProvider](https://javadoc.io/static/com.graphql-java/graphql-java/19.11/graphql/schema/idl/NaturalEnumValuesProvider.html)
- [Spring for GraphQL — Annotated Controllers and argument binding](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring Boot — GraphQL RuntimeWiring](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
