# GraphQLScalarType

GraphQL has built-in scalar types such as `String`, `Int`, `Float`, `Boolean`, and `ID`. They represent simple values without subfields. However, real-world APIs often need atomic types with their own rules: UUIDs, dates and times, currencies, emails, or system-specific identifier formats.

GraphQL lets you define **custom scalars** to extend that set of types. In GraphQL Java, `GraphQLScalarType` is the object describing a scalar at runtime; `Coercing` defines how to convert between Java values and GraphQL values. Spring for GraphQL connects custom scalars to the SDL schema through `RuntimeWiringConfigurer`.

This lesson explains the role of `GraphQLScalarType`, the three coercion directions (`serialize`, `parseValue`, `parseLiteral`), how to register scalars in Spring, and how to test both valid and invalid data.

## 1. What Is a Scalar and When Do You Need a Custom Scalar?

A scalar is a leaf-level data type in GraphQL. Clients select a scalar directly without a nested selection set:

```graphql
type Book {
  id: ID!
  title: String!
  publishedYear: Int
  available: Boolean!
}
```

`String`, `ID`, `Int`, and `Boolean` are all built-in scalars. They are suitable for values with simple representations and standard rules.

A custom scalar is appropriate when a single value needs an explicit format or parse/serialize rules. For example:

- `UUID` represents an identifier in UUID format.
- `Date` represents a calendar date without a time of day.
- `DateTime` represents a point in time with a timezone or offset.
- `Decimal` represents an exact decimal number for currency or measurements.
- `EmailAddress` represents an email address following the application's rules.

Do not create a scalar for multi-field structured data. If a value has `street`, `city`, and `postalCode`, consider an object type or input object. If the value domain is a finite named set, an enum is usually a better fit than a scalar. A custom scalar should represent an atomic value with consistent rules.

## 2. GraphQLScalarType in GraphQL Java

In GraphQL Java, `GraphQLScalarType` describes a scalar's name, description, coercing, and related metadata. You can construct one using its builder:

```java
GraphQLScalarType scalar = GraphQLScalarType.newScalar()
        .name("UUID")
        .description("UUID identifier in canonical string format.")
        .coercing(uuidCoercing)
        .build();
```

Key components:

| Component | Role |
| --- | --- |
| `name` | Scalar name referenced in SDL, such as `UUID` |
| `description` | Description of the scalar in the schema and introspection |
| `coercing` | Conversion, input validation, and output serialization rules |
| `specifiedByUrl` (if supported by the version) | Link to the scalar format specification |

In SDL, a custom scalar must be declared using the `scalar` keyword:

```graphql
scalar UUID

type Query {
  book(id: UUID!): Book
}

type Book {
  id: UUID!
  title: String!
}
```

Declaring `scalar UUID` only informs the schema that a scalar named `UUID` exists. It does not automatically define how to read a JSON string into `java.util.UUID`, nor does it validate formatting. The coercing implementation in runtime wiring supplies that behavior.

## 3. Coercing Has Three Conversion Directions

`Coercing` is the contract between GraphQL and the Java type used by the application. Three key methods correspond to three distinct situations:

| Method | Conversion Direction | When Is It Called? |
| --- | --- | --- |
| `parseValue` | External input → Java type | When the client passes variables in JSON `variables` |
| `parseLiteral` | GraphQL AST literal → Java type | When the client writes a value directly in the GraphQL document |
| `serialize` | Java value → GraphQL return value | When the resolver returns a result to the client |

For example, the same UUID can be passed in two ways:

```graphql
# Inline literal: goes through parseLiteral.
query {
  book(id: "550e8400-e29b-41d4-a716-446655440000") {
    id
    title
  }
}
```

Or using variables:

```graphql
query FindBook($id: UUID!) {
  book(id: $id) {
    id
    title
  }
}
```

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000"
}
```

In the second request, GraphQL calls `parseValue` to convert the JSON string into a Java type. In the response, if the resolver returns a `UUID`, GraphQL calls `serialize` to produce a string that the client can read.

### parseValue: Handling Variables

`parseValue` receives external data, typically coming from JSON. The method must check both the data type and its content. If the scalar expects a string, do not silently convert numbers or objects into strings.

### parseLiteral: Handling Literals in the Document

`parseLiteral` receives a GraphQL AST node, such as `StringValue`, `IntValue`, or `ObjectValue`. A UUID scalar accepts only `StringValue`. If a client writes `book(id: 123)`, the parser should not automatically turn that number into a UUID.

### serialize: Returning Data to the Client

`serialize` processes the value returned by a data fetcher/resolver. It must produce a valid, stable GraphQL value that can be represented in the response. Do not return an arbitrary Java object directly if the scalar is published as a string.

## 4. Example: Building a Custom UUID Scalar

Suppose the domain model uses `java.util.UUID`, while GraphQL clients send and receive UUIDs as canonical strings. You create a `GraphQLScalarType` whose internal Java type is `UUID` and whose serialized external type is `String`.

The example below uses GraphQL Java's modern `Coercing` signatures with `GraphQLContext`, `Locale`, and `CoercedVariables`. These signatures change across GraphQL Java generations; use the GraphQL Java version managed by Spring Boot and consult the corresponding API when upgrading.

```java
import graphql.GraphQLContext;
import graphql.execution.CoercedVariables;
import graphql.language.StringValue;
import graphql.language.Value;
import graphql.schema.Coercing;
import graphql.schema.CoercingParseLiteralException;
import graphql.schema.CoercingParseValueException;
import graphql.schema.CoercingSerializeException;
import graphql.schema.GraphQLScalarType;

import java.util.Locale;
import java.util.UUID;

public final class UuidScalar {

    private UuidScalar() {
    }

    public static final GraphQLScalarType UUID_SCALAR =
            GraphQLScalarType.newScalar()
                    .name("UUID")
                    .description("UUID identifier in canonical string format.")
                    .coercing(new Coercing<UUID, String>() {

                        @Override
                        public String serialize(
                                Object dataFetcherResult,
                                GraphQLContext graphQLContext,
                                Locale locale) {

                            if (dataFetcherResult instanceof UUID uuid) {
                                return uuid.toString();
                            }
                            if (dataFetcherResult instanceof String value) {
                                try {
                                    return parseCanonical(value).toString();
                                }
                                catch (IllegalArgumentException ex) {
                                    throw new CoercingSerializeException(
                                            "Expected a valid UUID value.");
                                }
                            }
                            throw new CoercingSerializeException(
                                    "Expected UUID or canonical UUID string.");
                        }

                        @Override
                        public UUID parseValue(
                                Object input,
                                GraphQLContext graphQLContext,
                                Locale locale) {

                            if (!(input instanceof String value)) {
                                throw new CoercingParseValueException(
                                        "UUID input must be a string.");
                            }
                            try {
                                return parseCanonical(value);
                            }
                            catch (IllegalArgumentException ex) {
                                throw new CoercingParseValueException(
                                        "UUID input must use canonical UUID format.");
                            }
                        }

                        @Override
                        public UUID parseLiteral(
                                Value<?> input,
                                CoercedVariables variables,
                                GraphQLContext graphQLContext,
                                Locale locale) {

                            if (!(input instanceof StringValue stringValue)) {
                                throw new CoercingParseLiteralException(
                                        "UUID literal must be a string.");
                            }
                            try {
                                return parseCanonical(stringValue.getValue());
                            }
                            catch (IllegalArgumentException ex) {
                                throw new CoercingParseLiteralException(
                                        "UUID literal must use canonical UUID format.");
                            }
                        }
                    })
                    .build();

    private static UUID parseCanonical(String value) {
        UUID uuid = UUID.fromString(value);
        if (!uuid.toString().equalsIgnoreCase(value)) {
            throw new IllegalArgumentException("UUID is not canonical.");
        }
        return uuid;
    }
}
```

Notable points:

- `parseValue` accepts only `String`, then parses it into `UUID`.
- `parseLiteral` accepts only `StringValue`, rejecting numeric or object literals.
- `serialize` accepts `UUID` from the domain model and returns the canonical string.
- Input and output failures use distinct exception types so GraphQL distinguishes parse errors from serialization errors.
- `parseCanonical` verifies that the string follows the exact canonical form instead of relying solely on whether `UUID.fromString` succeeds.

This is an example UUID scalar; a real application may simplify validation or use a standardized library implementation. Do not copy a short regex for emails or dates and treat it as a complete validator if your domain requires complex rules.

## 5. Registering GraphQLScalarType in Spring for GraphQL

After creating the scalar, you need to wire it into the GraphQL schema runtime. Spring for GraphQL provides `RuntimeWiringConfigurer` to add scalars to the GraphQL Java runtime wiring.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class GraphQlScalarConfiguration {

    @Bean
    RuntimeWiringConfigurer uuidScalarConfigurer() {
        return wiringBuilder ->
                wiringBuilder.scalar(UuidScalar.UUID_SCALAR);
    }
}
```

Spring Boot collects `RuntimeWiringConfigurer` beans when building `GraphQlSource`. The scalar is registered in the runtime wiring and can be used by fields declaring `UUID` in the SDL.

Schema:

```graphql
scalar UUID

type Query {
  book(id: UUID!): Book
}

type Book {
  id: UUID!
  title: String!
}
```

Resolvers can receive the Java `UUID` type once `parseValue` or `parseLiteral` finishes:

```java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument UUID id) {
        return bookService.findById(id);
    }
}
```

If `Book.id` is a `UUID`, the custom scalar's `serialize` method turns it into a string in the response. This lets the domain layer use the strongly typed `UUID`, while the GraphQL contract uses a string representation easy to exchange over JSON.

## 6. Using Pre-Built Scalars from the Extended Library

You do not always need to write `Coercing` manually. GraphQL Java Extended Scalars provides several common scalars such as `Date`, `DateTime`, `Time`, `Url`, `Email`, `BigDecimal`, and others depending on the library version.

Example using `ExtendedScalars.Date`:

```gradle
dependencies {
    implementation("com.graphql-java:graphql-java-extended-scalars")
}
```

Choose a library version compatible with the GraphQL Java version managed by Spring Boot; do not upgrade GraphQL Java independently just to match a specific Extended Scalars release.

Register the scalar:

```java
@Configuration
public class GraphQlScalarConfiguration {

    @Bean
    RuntimeWiringConfigurer scalarConfigurer() {
        return wiring -> wiring.scalar(ExtendedScalars.Date);
    }
}
```

SDL:

```graphql
scalar Date

type Book {
  publishedOn: Date
}
```

Extended Scalars reduces coercing boilerplate and leverages existing formatting rules. However, check the documentation of the library version you use: input formats, parsed Java types, timezone rules, and serialization behavior may differ from what your system expects.

Do not register multiple scalars with the same name simultaneously or replace built-in scalars like `String` with custom scalars. The scalar name in SDL must match the registered scalar name.

## 7. Testing Scalars with Variables, Literals, and Output

Custom scalars should be tested across all three coercion directions. Testing only `parseValue` is not enough because inline literals go through `parseLiteral`, and values returned by resolvers go through `serialize`.

### Testing Valid Variables

With schema `book(id: UUID!): Book`, send variables:

```java
graphQlTester.document("""
        query FindBook($id: UUID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
    .variable("id", "550e8400-e29b-41d4-a716-446655440000")
    .execute()
    .path("book.id")
    .entity(String.class)
    .isEqualTo("550e8400-e29b-41d4-a716-446655440000");
```

This test passes through `parseValue`, invokes the resolver with Java type `UUID`, and then passes through `serialize` to produce the response string.

### Testing Valid Literals

```java
graphQlTester.document("""
        query {
            book(id: "550e8400-e29b-41d4-a716-446655440000") {
                id
            }
        }
        """)
    .execute()
    .path("book.id")
    .entity(String.class)
    .isEqualTo("550e8400-e29b-41d4-a716-446655440000");
```

This test exercises `parseLiteral`.

### Testing Invalid Input

You can send a malformed UUID or the wrong JSON type:

```java
graphQlTester.document("""
        query FindBook($id: UUID!) {
            book(id: $id) {
                id
            }
        }
        """)
    .variable("id", "not-a-uuid")
    .execute()
    .errors()
    .expect(error -> error.getMessage()
            .contains("UUID input must use canonical UUID format"))
    .verify();
```

For a UUID scalar, verify that invalid values are rejected before the resolver runs. In a full test, you can verify that the service mock was not called.

### Testing Serialization

Have the resolver return a `UUID` and check that the response is the canonical string. Also try returning an object of the wrong type to confirm that the scalar produces a serialization error. Do not test only the input path, because serialization errors can occur when database data or domain objects violate the contract.

## 8. How GraphQL Represents Coercion Errors

Scalar errors occur at different stages:

| Error | Method | Typical Consequence |
| --- | --- | --- |
| Variable fails to parse | `parseValue` | Request is rejected during variable coercion; the corresponding resolver is not invoked |
| Literal has wrong type or format | `parseLiteral` | Document fails validation/coercion; the field is not executed |
| Resolver returns unserializable value | `serialize` | Error occurs during field execution and is added to `errors`; null propagation follows schema nullability |

For example, the schema declares `id: UUID!` but the resolver returns the string `"invalid"`. `serialize` cannot produce a valid value. GraphQL reports an error for that field; because the field is non-null, null may propagate up to the nearest nullable parent object. Therefore, custom scalars must validate both input and output.

Do not throw a generic `RuntimeException` from every coercion branch. Using `CoercingParseValueException`, `CoercingParseLiteralException`, and `CoercingSerializeException` accurately describes the failure type and helps GraphQL generate an appropriate error response.

## 9. Designing Safe Custom Scalars

A custom scalar is the boundary between client-supplied data and the data types trusted by the domain layer. Follow these principles:

- **Strict type checking:** if a scalar is published as a string, do not automatically convert numbers or objects into strings.
- **Canonical format:** if multiple equivalent representations exist, decide whether to accept all of them or only one canonical form.
- **Symmetric parsing and serialization:** data serialized by the server should be parseable back according to the contract within the allowed format.
- **Request-state independence:** coercing should be a deterministic conversion without reading databases or making network calls.
- **Size limits:** string-based scalars should limit length to prevent oversized inputs.
- **Sufficient error messages:** clearly state the expected format without revealing internal information or sensitive data.
- **Not a substitute for authorization:** a valid UUID does not prove a user has permission to access the resource with that UUID.
- **Do not confuse syntax validation with business validation:** a syntactically valid email does not necessarily exist; a valid currency code is not necessarily allowed in a specific transaction.

For `DateTime`, clearly decide whether offsets are required, whether values normalize to UTC, and whether precision is milliseconds or nanoseconds. For `Decimal`, define precision, scale, rounding rules, and whether scientific notation is permitted. These decisions should live in the scalar description or specification so clients use it consistently.

## 10. GraphQLScalarType vs. Other Options

Not every data type should be turned into a custom scalar:

| Need | Suitable Choice |
| --- | --- |
| Strings, integers, floats, booleans | Built-in scalar |
| A finite set of named values | Enum |
| An atomic value with custom formatting | Custom scalar / `GraphQLScalarType` |
| Object with multiple returned fields | Object type |
| Grouped data sent by the client | Input object |
| Distinguishing multiple object kinds | Interface or union |

Custom scalars keep contracts concise and give you strong Java types, but they also hide internal structure from GraphQL selection sets. If clients need to query parts of the data, use an object type instead of packing everything into a custom JSON scalar.

## 11. Common Pitfalls When Integrating Custom Scalars

| Symptom | Cause | Solution |
| --- | --- | --- |
| `Unknown type UUID` | SDL references scalar without declaring `scalar UUID` or schema file is not loaded | Check SDL and schema locations |
| Scalar is declared, but input fails to parse | `GraphQLScalarType` is not registered in runtime wiring | Add a `RuntimeWiringConfigurer` |
| Variables work, but literals fail | `parseValue` is right, but `parseLiteral` does not handle the AST node | Check `StringValue`, `IntValue`, or required AST nodes |
| Resolver receives `String` instead of domain type | Coercing parses to wrong Java type or scalar is not properly registered | Check generic type and `parseValue`/`parseLiteral` |
| Response has serialization error | Resolver returns an object incompatible with the scalar | Check `serialize` and the type returned by the service |
| Duplicate scalar name | Multiple configs register different scalars under the same name | Register only one definition per scalar name |
| Code fails to compile after upgrading Boot | `Coercing` signatures changed with GraphQL Java version | Use the Boot-managed dependency and update overridden methods |

## 12. Practice Exercise

Build a custom scalar `ISBN` for a book management API:

1. Declare `scalar ISBN` in the SDL.
2. Create a `GraphQLScalarType` named `ISBN` with a description explaining the supported format.
3. Write `Coercing` so `parseValue` and `parseLiteral` accept only strings matching the ISBN format permitted by the application.
4. Write `serialize` so the response always has a consistent representation.
5. Register the scalar using `RuntimeWiringConfigurer`.
6. Use `@Argument ISBN` or the corresponding Java type to receive the parsed value.
7. Write tests for valid variables, valid literals, malformed strings, wrong JSON types, and serialization.

Example schema:

```graphql
scalar ISBN

type Query {
  bookByIsbn(isbn: ISBN!): Book
}

type Book {
  id: ID!
  isbn: ISBN!
  title: String!
}
```

Once finished, verify that the same formatting rules apply to variables, inline literals, and returned data. This is an essential criterion for making a custom scalar a reliable data contract for clients and resolvers in Spring for GraphQL.
