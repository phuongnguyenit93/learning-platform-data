# Custom scalar

GraphQL has an explicit type system to describe an API's input and output data. The five built-in scalars—**Int**, **Float**, **String**, **Boolean**, and **ID**—cover many common cases. However, real-world applications often deal with values carrying specialized semantics such as calendar dates, timestamps, UUIDs, monetary amounts, or custom-formatted data. When the built-in types cannot express the full data contract, GraphQL lets you define a **custom scalar**.

A custom scalar is a leaf data type in the schema. Clients treat it as a single value and do not query subfields as they do with object types. The server defines how to read input values, validate them, convert them to an internal type, and serialize the returned result. In Spring for GraphQL, custom scalars are typically implemented using GraphQL Java's **GraphQLScalarType** and registered in **RuntimeWiring**.

## Built-in scalars and the need for custom scalars

GraphQL defines five standard scalars:

| Scalar | Meaning | Example |
| --- | --- | --- |
| **Int** | Signed 32-bit integer | 42 |
| **Float** | Floating-point number | 19.95 |
| **String** | Character string | "Spring" |
| **Boolean** | True or false value | true |
| **ID** | Identifier, usually serialized as a string | "book-101" |

These scalars have serialization and type-checking rules defined by GraphQL. For instance, ID suits identifiers but does not express UUID format; String can hold a date, yet the schema does not indicate which format the string must follow.

Suppose a book management API has a publication date. If the field is declared as String, all of the following are valid strings from GraphQL's perspective:

~~~text
2025-04-18
18/04/2025
April 18, 2025
not-a-date
~~~

Yet they carry different meanings or are invalid according to business rules. A schema with a Date type communicates intent much more clearly:

~~~graphql
scalar Date

type Book {
  id: ID!
  title: String!
  publishedOn: Date!
}
~~~

A custom scalar does not define every business rule of the application by itself. It defines the wire format and how data is converted. For example, a Date scalar can require clients to send an ISO-8601 yyyy-MM-dd string, while whether that date falls within an allowed publication window remains business validation in the service.

## How does a custom scalar work?

A scalar typically participates in two flows:

- **Input:** the client sends a value via variables or writes it directly in the GraphQL document. The server validates and converts that value into an internal Java type.
- **Output:** the resolver returns a Java value. The server validates and serializes it into a value that can be sent in the GraphQL response.

GraphQL Java defines coercion operations via the Coercing interface. Three key methods are:

| Method | Data direction | When it is called |
| --- | --- | --- |
| **serialize** | Java to GraphQL response | When a field returns a scalar value |
| **parseValue** | Input variable value to Java | When an operation uses variables, typically from a JSON request |
| **parseLiteral** | Literal in a GraphQL document to Java | When the client writes a value inline in the operation |

Example of two ways to pass a date:

~~~graphql
query BooksByDate($date: Date!) {
  books(publishedAfter: $date) {
    id
    title
  }
}
~~~

Variables:

~~~json
{
  "date": "2025-04-18"
}
~~~

In this case, GraphQL Java calls parseValue to convert the string in variables into the Java type specified by the scalar.

Clients can also pass a literal directly:

~~~graphql
query {
  books(publishedAfter: "2025-04-18") {
    id
    title
  }
}
~~~

With this syntax, GraphQL Java calls parseLiteral. When the resolver returns a LocalDate, the serialize method converts that date into a yyyy-MM-dd string in the response.

## Choosing the wire format and internal Java type

Before writing a scalar, clearly decide on the data format exchanged between client and server. Some common choices:

| Custom scalar | Common wire format | Possible Java type |
| --- | --- | --- |
| **Date** | yyyy-MM-dd | LocalDate |
| **DateTime** | ISO-8601 with offset or UTC | OffsetDateTime or Instant |
| **UUID** | Standard UUID string | UUID |
| **BigDecimal** | Decimal string to preserve precision | BigDecimal |
| **Long** | Integer beyond 32-bit Int range | Long |

The format must be consistent on both input and output. For calendar dates, LocalDate is usually appropriate because it carries no time zone information. For points on a timeline, choose Instant or OffsetDateTime and clearly specify offset or UTC normalization rules. Avoid using LocalDateTime for a global instant if the API has no accompanying time zone rule.

For currency or decimals requiring exact precision, BigDecimal is preferable to double. If the wire format uses a JSON number, some JavaScript clients can lose precision on large numbers or long fractional digits; using a string with an explicit format can be safer, though clients must adhere to that contract.

Do not create a custom scalar merely to rename a type without additional rules. If String or ID already expresses the contract accurately and needs no custom coercion, using a built-in scalar is simpler.

## Implementing a Date scalar with GraphQL Java

The following example defines a Date scalar backed by java.time.LocalDate. The scalar accepts ISO-8601 strings in yyyy-MM-dd format for both variables and literals; output accepts only LocalDate.

~~~java
import graphql.language.StringValue;
import graphql.schema.Coercing;
import graphql.schema.CoercingParseLiteralException;
import graphql.schema.CoercingParseValueException;
import graphql.schema.CoercingSerializeException;
import graphql.schema.GraphQLScalarType;

import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;

public final class DateScalar {

    private static final DateTimeFormatter FORMATTER =
            DateTimeFormatter.ISO_LOCAL_DATE;

    private DateScalar() {
    }

    public static GraphQLScalarType create() {
        return GraphQLScalarType.newScalar()
                .name("Date")
                .description("Calendar date in ISO-8601 yyyy-MM-dd format")
                .coercing(new Coercing<LocalDate, String>() {

                    @Override
                    public String serialize(Object dataFetcherResult) {
                        if (dataFetcherResult instanceof LocalDate date) {
                            return FORMATTER.format(date);
                        }
                        throw new CoercingSerializeException(
                                "Date can only be serialized from LocalDate");
                    }

                    @Override
                    public LocalDate parseValue(Object input) {
                        if (!(input instanceof String value)) {
                            throw new CoercingParseValueException(
                                    "Date input must be a yyyy-MM-dd string");
                        }
                        try {
                            return LocalDate.parse(value, FORMATTER);
                        } catch (DateTimeParseException ex) {
                            throw new CoercingParseValueException(
                                    "Invalid Date; use yyyy-MM-dd format");
                        }
                    }

                    @Override
                    public LocalDate parseLiteral(Object input) {
                        if (!(input instanceof StringValue stringValue)) {
                            throw new CoercingParseLiteralException(
                                    "Date literal must be a string");
                        }
                        try {
                            return LocalDate.parse(stringValue.getValue(), FORMATTER);
                        } catch (DateTimeParseException ex) {
                            throw new CoercingParseLiteralException(
                                    "Invalid Date; use yyyy-MM-dd format");
                        }
                    }
                })
                .build();
    }
}
~~~

The exception types indicate which direction failed:

- **CoercingParseValueException** is for input coming from variables.
- **CoercingParseLiteralException** is for literals with the wrong type or format.
- **CoercingSerializeException** is for values returned by a resolver that cannot be converted into the wire format.

Error messages should state the expected format clearly without containing sensitive data or internal details. The snippet uses the basic Coercing methods for readability; depending on the GraphQL Java version managed by Spring Boot, the API may also provide overloads taking GraphQLContext, Locale, and CoercedVariables. When implementing, check the API signatures of the GraphQL Java version in your project and prefer the version-appropriate overloads if context or locale is needed.

## Registering custom scalars in Spring for GraphQL

Declaring scalar Date in SDL only tells the schema that a scalar named Date exists. The GraphQL runtime still needs to know how to coerce that scalar. In Spring for GraphQL, you can register a GraphQLScalarType using a RuntimeWiringConfigurer bean:

~~~java
import graphql.schema.GraphQLScalarType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class GraphQlScalarConfiguration {

    @Bean
    GraphQLScalarType dateScalar() {
        return DateScalar.create();
    }

    @Bean
    RuntimeWiringConfigurer runtimeWiringConfigurer(
            GraphQLScalarType dateScalar) {
        return wiringBuilder -> wiringBuilder.scalar(dateScalar);
    }
}
~~~

Spring Boot automatically detects RuntimeWiringConfigurer beans and applies this configuration when building the GraphQL runtime. If the application has multiple custom scalars, you can register each scalar in the same configurer or split them into smaller configurers by area of responsibility. The scalar name in the SDL must match the name of the GraphQLScalarType.

The schema can use the Date scalar in both output fields and arguments:

~~~graphql
scalar Date

type Query {
  books(publishedAfter: Date): [Book!]!
}

type Book {
  id: ID!
  title: String!
  publishedOn: Date!
}
~~~

The resolver receives the Java LocalDate type because the scalar has already converted the input before the method is invoked:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books(@Argument LocalDate publishedAfter) {
        return bookService.findPublishedAfter(publishedAfter);
    }
}
~~~

When the service returns Book objects whose publishedOn field is LocalDate, the Date scalar serializes them into ISO-8601 strings in the response. As a result, controllers and services work with meaningful Java types instead of passing raw date strings throughout the application.

## Input and output processing flow

The diagram below summarizes where a custom scalar sits during execution:

~~~mermaid
flowchart TD
    A["Client GraphQL request"] --> B{"How is the input passed?"}
    B -->|"JSON variables"| C["parseValue"]
    B -->|"Literal in document"| D["parseLiteral"]
    C --> E["Internal Java type"]
    D --> E
    E --> F["Resolver / Service"]
    F --> G["Returned Java value"]
    G --> H["serialize"]
    H --> I["GraphQL response"]
~~~

A scalar handles type conversion at the GraphQL boundary. It should not access a database, make HTTP calls, or execute business logic. Keeping coercing pure ensures formatting rules are easy to test, predictable, and reusable across many fields.

## Testing custom scalars

You should test the three coercion methods individually as well as through integrated GraphQL operations:

| Case | Expected result |
| --- | --- |
| Serialize a valid LocalDate | ISO-8601 string yyyy-MM-dd |
| Serialize a non-LocalDate object | Serialization error |
| Parse variable with a valid date | Corresponding LocalDate obtained |
| Parse variable with invalid format | Input coercion error |
| Parse literal with a valid string | Corresponding LocalDate obtained |
| Parse literal that is not a string or has an invalid date | Literal coercion error |

Example testing via GraphQlTester:

~~~java
graphQlTester.document("""
        query Books($after: Date) {
            books(publishedAfter: $after) {
                id
                publishedOn
            }
        }
        """)
    .variable("after", "2025-04-18")
    .execute()
    .path("books[0].publishedOn")
    .entity(String.class)
    .isEqualTo("2025-04-20");
~~~

This test exercises parseValue when receiving the variable and serialize when returning the publishedOn field. To test parseLiteral, write an operation with the Date value inline in the document instead of passing it via variables. Also add tests for invalid dates such as 2025-02-30, malformed formats such as 18/04/2025, null values if the field is nullable, and null values on non-null fields.

When testing errors with GraphQlTester, verify that the operation produces a coercion error and that the resolver is not invoked with invalid input. This guarantees malformed data is rejected right at the GraphQL boundary before reaching the business layer.

## Designing safe and stable custom scalars

A custom scalar is part of the public contract. Once clients depend on it, changing the wire format can break compatibility. For instance, changing Date from yyyy-MM-dd to dd/MM/yyyy makes existing clients send data that is no longer valid. Establish the format early, document the scalar description in the schema, and keep the format stable.

Several principles to follow:

1. **Validate input strictly.** Accept only the published type and format; do not silently coerce arbitrary numbers, objects, or strings into valid values.
2. **Serialize a well-defined Java type.** Avoid accepting multiple unrelated internal types, as doing so can produce inconsistent responses.
3. **Use standard formats.** ISO-8601 works well for dates and timestamps; UUIDs should use standard string form; decimals require clear precision and scale rules.
4. **Separate coercion from business validation.** Scalars validate shape and convert types; services enforce rules such as ensuring a publication date is not in the future or an amount is within limits.
5. **Do not confuse scalars with objects.** If clients need to query sub-properties such as amount and currency, consider a Money object type instead of an opaque scalar.
6. **Choose clear names and descriptions.** Names like DateTime, UUID, or Money need a concrete format contract so clients know how to use them.
7. **Test both input and output.** Testing only parsing without serialization can allow data to be read in while responses violate the format.

Custom scalars are valuable when a value has a distinct format and coercion rules that must be shared consistently across multiple fields. In Spring for GraphQL, SDL declares the scalar name, GraphQL Java defines how to parse and serialize it, and RuntimeWiringConfigurer wires that scalar into the runtime. Keeping this boundary clear allows the schema to express specialized data types while resolvers and services continue working with appropriate Java types.
