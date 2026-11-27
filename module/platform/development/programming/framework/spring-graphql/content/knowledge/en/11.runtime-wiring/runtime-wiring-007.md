# Custom scalar wiring

## Objectives

After this lesson, you will be able to:

- Explain why declaring a custom scalar in SDL alone is not enough for GraphQL to process values.
- Register a `GraphQLScalarType` using `RuntimeWiringConfigurer` in Spring for GraphQL.
- Leverage extended scalars such as `DateTime`, `Date`, `Long`, and `BigDecimal`.
- Build your own scalar with `Coercing` when the application needs custom formatting rules.
- Distinguish between parsing variables, parsing literals, and serializing results.
- Test scalar wiring with `GraphQlTester` and diagnose common errors.

## A custom scalar requires two parts

GraphQL has five standard scalars: `Int`, `Float`, `String`, `Boolean`, and `ID`. When an API needs to represent values with stricter rules—such as dates and times, order codes, or exact decimal numbers—you can define a custom scalar.

For a custom scalar to work, the application needs two parts:

1. **SDL declaration**: declares the scalar name so the schema can use it in fields, arguments, and input objects.
2. **Runtime wiring**: registers a `GraphQLScalarType` so GraphQL Java knows how to convert incoming data and outgoing results.

Example SDL:

~~~graphql
scalar DateTime

type Event {
  id: ID!
  startsAt: DateTime!
}

type Query {
  event(id: ID!): Event
}
~~~

Declaring `scalar DateTime` only introduces the type name into the schema. It does not describe the internal Java type, the string format accepted from clients, or how resolver values are serialized into JSON. Those rules are handled by the scalar implementation registered in runtime wiring.

If a scalar is declared in SDL without registering an implementation, the schema may fail to build or fail to handle values as expected. The scalar name in the SDL must match the name of the registered `GraphQLScalarType`.

## RuntimeWiringConfigurer in Spring for GraphQL

GraphQL Java provides `RuntimeWiring.Builder` to register custom scalars, directives, type resolvers, and other execution components. Spring for GraphQL provides `RuntimeWiringConfigurer` as the extension point for configuring this builder.

In a Spring Boot application, `RuntimeWiringConfigurer` beans are detected by Boot and applied when building `GraphQlSource`. Therefore, you usually only need to declare a bean in a `@Configuration` class:

~~~java
import graphql.scalars.ExtendedScalars;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration(proxyBeanMethods = false)
public class GraphQlScalarConfiguration {

    @Bean
    RuntimeWiringConfigurer scalarConfigurer() {
        return wiringBuilder ->
                wiringBuilder.scalar(ExtendedScalars.DateTime);
    }
}
~~~

When the GraphQL runtime is initialized, `scalarConfigurer` registers the `DateTime` scalar into `RuntimeWiring.Builder`. Controllers can continue using `@QueryMapping`, `@MutationMapping`, and `@SchemaMapping` as usual; the custom scalar is solely responsible for value conversion.

There is no need to manually create `GraphQlSource` or register manual `DataFetcher`s just to add a scalar. Use `RuntimeWiringConfigurer` for this extension and let Boot manage the GraphQL configuration lifecycle.

## Using the graphql-java-extended-scalars library

Before writing your own `Coercing`, check the `graphql-java-extended-scalars` library. It provides many common extended types, such as:

| Scalar | Typical Java runtime type | Example |
| --- | --- | --- |
| DateTime | OffsetDateTime | 2025-04-10T09:30:00+07:00 |
| Date | LocalDate | 2025-04-10 |
| Time | OffsetTime | 09:30:00+07:00 |
| Long | Long | 9223372036854775807 |
| BigDecimal | BigDecimal | 12345.6789 |
| UUID | UUID | 550e8400-e29b-41d4-a716-446655440000 |

The exact list depends on the library version. Check the documentation for the version used in your project before choosing a scalar.

### Adding the dependency

With Gradle:

~~~groovy
dependencies {
    implementation 'com.graphql-java:graphql-java-extended-scalars:<compatible-version>'
}
~~~

With Maven:

~~~xml
<dependency>
    <groupId>com.graphql-java</groupId>
    <artifactId>graphql-java-extended-scalars</artifactId>
    <version>compatible-version</version>
</dependency>
~~~

Replace `compatible-version` with a version compatible with the GraphQL Java version managed by Spring Boot. Do not pick the latest version blindly if it requires a different GraphQL Java version than your application uses. The Extended Scalars README publishes compatible version lines; check it before upgrading.

### Registering DateTime

After adding the dependency, declare the scalar in SDL:

~~~graphql
scalar DateTime
  @specifiedBy(url: "https://scalars.graphql.org/andimarek/date-time.html")

type Event {
  id: ID!
  startsAt: DateTime!
}
~~~

Then register the scalar:

~~~java
@Bean
RuntimeWiringConfigurer scalarConfigurer() {
    return wiringBuilder -> wiringBuilder
            .scalar(ExtendedScalars.DateTime);
}
~~~

Extended Scalars' `DateTime` scalar follows RFC 3339 and produces `OffsetDateTime` in the Java runtime. Accordingly, models or services can use the `OffsetDateTime` type:

~~~java
public record Event(
        String id,
        OffsetDateTime startsAt) {
}
~~~

Example query:

~~~graphql
query {
  event(id: "event-101") {
    id
    startsAt
  }
}
~~~

The response may contain a string value:

~~~json
{
  "data": {
    "event": {
      "id": "event-101",
      "startsAt": "2025-04-10T09:30:00+07:00"
    }
  }
}
~~~

### Registering multiple scalars

A single `RuntimeWiringConfigurer` can register multiple scalars:

~~~java
@Bean
RuntimeWiringConfigurer scalarConfigurer() {
    return wiringBuilder -> wiringBuilder
            .scalar(ExtendedScalars.DateTime)
            .scalar(ExtendedScalars.Date)
            .scalar(ExtendedScalars.BigDecimal)
            .scalar(ExtendedScalars.UUID);
}
~~~

The SDL must declare the scalars used by the schema:

~~~graphql
scalar DateTime
scalar Date
scalar BigDecimal
scalar UUID

type Invoice {
  id: ID!
  issuedOn: Date!
  createdAt: DateTime!
  total: BigDecimal!
  reference: UUID!
}
~~~

Only register scalars that are actually needed. Adding a scalar to runtime wiring does not automatically add fields to the schema; SDL still governs where and how clients can use that type.

## Scalar coercion flow

A custom scalar has three key conversion directions:

| Method | Input data | Result |
| --- | --- | --- |
| parseValue | Value from JSON variables | Internal Java value |
| parseLiteral | Literal in a GraphQL document | Internal Java value |
| serialize | Value returned by a resolver | Scalar value in JSON response |

Example operation containing both a variable and a literal:

~~~graphql
query SearchEvents($after: DateTime!) {
  events(after: $after, before: "2025-12-31T23:59:59+07:00") {
    id
    startsAt
  }
}
~~~

Variables:

~~~json
{
  "after": "2025-01-01T00:00:00+07:00"
}
~~~

In this operation:

- `parseValue` handles the value of `$after` taken from variables.
- `parseLiteral` handles the date-time string written directly in the document for `before`.
- `serialize` converts the `startsAt` values from the resolver into the scalar format sent back to the client.

An implementation that only handles `parseValue` may work with variables yet fail when clients pass inline literals. An implementation that parses input without serializing properly may accept requests successfully yet fail when building the response.

## Defining your own scalar with Coercing

When the extended library does not satisfy your application's custom rules, you can create a `GraphQLScalarType` and implement `Coercing`.

Suppose the system uses order codes formatted as `ORD-` followed by exactly six digits. We want the schema to use an `OrderCode` scalar instead of `String`:

~~~graphql
scalar OrderCode

type Order {
  code: OrderCode!
}

type Query {
  order(code: OrderCode!): Order
}
~~~

### Writing the scalar implementation

The example below uses GraphQL Java's modern `Coercing` signatures with `GraphQLContext`, `Locale`, and `CoercedVariables`:

~~~java
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
import java.util.regex.Pattern;

public final class OrderCodeScalar {

    private static final Pattern FORMAT =
            Pattern.compile("ORD-[0-9]{6}");

    public static final GraphQLScalarType ORDER_CODE =
            GraphQLScalarType.newScalar()
                    .name("OrderCode")
                    .description("Order code in the format ORD- followed by six digits")
                    .coercing(new Coercing<String, String>() {

                        @Override
                        public String serialize(
                                Object dataFetcherResult,
                                GraphQLContext graphQLContext,
                                Locale locale) {

                            if (dataFetcherResult instanceof String value
                                    && FORMAT.matcher(value).matches()) {
                                return value;
                            }
                            throw new CoercingSerializeException(
                                    "OrderCode result has an invalid format");
                        }

                        @Override
                        public String parseValue(
                                Object input,
                                GraphQLContext graphQLContext,
                                Locale locale) {

                            if (input instanceof String value
                                    && FORMAT.matcher(value).matches()) {
                                return value;
                            }
                            throw new CoercingParseValueException(
                                    "OrderCode variable has an invalid format");
                        }

                        @Override
                        public String parseLiteral(
                                Value<?> input,
                                CoercedVariables variables,
                                GraphQLContext graphQLContext,
                                Locale locale) {

                            if (input instanceof StringValue stringValue) {
                                String value = stringValue.getValue();
                                if (FORMAT.matcher(value).matches()) {
                                    return value;
                                }
                            }
                            throw new CoercingParseLiteralException(
                                    "OrderCode literal has an invalid format");
                        }

                        @Override
                        public Value<?> valueToLiteral(
                                Object input,
                                GraphQLContext graphQLContext,
                                Locale locale) {

                            String value = serialize(
                                    input, graphQLContext, locale);
                            return StringValue.newStringValue(value).build();
                        }
                    })
                    .build();

    private OrderCodeScalar() {
    }
}
~~~

The implementation has four responsibilities:

- `serialize` validates the data returned by the resolver and converts it into a string value in the response.
- `parseValue` validates JSON variables and converts them into a Java value.
- `parseLiteral` accepts only `StringValue` in the GraphQL AST, then checks the format.
- `valueToLiteral` converts a valid input value into an AST literal when GraphQL Java needs to represent that value as a literal.

Across all three primary paths, the formatting rules are identical. If an input is valid via variables but invalid via a literal, clients will experience inconsistent behavior.

### Registering the custom scalar

Add the newly created scalar to runtime wiring:

~~~java
@Configuration(proxyBeanMethods = false)
public class GraphQlScalarConfiguration {

    @Bean
    RuntimeWiringConfigurer scalarConfigurer() {
        return wiringBuilder -> wiringBuilder
                .scalar(OrderCodeScalar.ORDER_CODE);
    }
}
~~~

From the moment the schema is built, the GraphQL runtime can use `OrderCode` for arguments, input fields, and output fields declared in the SDL.

## Coercion errors and handling

GraphQL Java specifies that each coercion method must throw the appropriate exception type when conversion fails:

| Method | Exception to use | Scenario |
| --- | --- | --- |
| serialize | CoercingSerializeException | Resolver returned an unserializable type or format |
| parseValue | CoercingParseValueException | JSON variable has the wrong type or format |
| parseLiteral | CoercingParseLiteralException | Literal has an invalid AST node or format |

Do not return `null` to signal malformed data. `null` is a GraphQL value with its own semantics and may be valid if a field is nullable. When a scalar cannot convert data, throw the corresponding exception so GraphQL produces a coercion error.

Do not let arbitrary `RuntimeException`s escape from coercion methods. Catch necessary conversion errors and translate them into the right `Coercing...Exception` type. Error messages should describe the issue at a level appropriate for clients; avoid exposing stack traces, database queries, or sensitive data in errors.

Scalars should focus on format validation and data representation. Rules such as whether an order code exists or whether the user has permission to view that order do not belong in a scalar; check those in the resolver or service.

## Aliased scalars and when to use them

Sometimes data can be represented by a standard scalar, yet you want a name that conveys business meaning. For example, an article link could be a string, but `ArticleUrl` makes the schema easier to read:

~~~graphql
scalar ArticleUrl

type Article {
  id: ID!
  url: ArticleUrl!
}
~~~

Extended Scalars supports creating an aliased scalar from an existing scalar. Example:

~~~java
import graphql.Scalars;
import graphql.scalars.ExtendedScalars;
import graphql.schema.GraphQLScalarType;

GraphQLScalarType articleUrl =
        ExtendedScalars.newAliasedScalar("ArticleUrl")
                .aliasedScalar(Scalars.GraphQLString)
                .build();
~~~

Then register the alias with `RuntimeWiringConfigurer`:

~~~java
return wiringBuilder -> wiringBuilder.scalar(articleUrl);
~~~

Aliases add semantic clarity to the schema, but they do not automatically add URL validation. If you need to check the scheme, host, or URL format, use an existing specialized scalar or implement `Coercing` with well-defined rules.

Avoid using a custom scalar for data with multiple fields that clients need to query individually. For example, currency is usually better modeled as a `Money` object type with `amount` and `currency`, rather than packing both into an unstructured string.

## Testing custom scalars with GraphQlTester

Test scalars through GraphQL operations to verify SDL, runtime wiring, coercion, and resolvers together.

Example schema echoing an `OrderCode`:

~~~graphql
type Query {
  echoOrderCode(value: OrderCode!): OrderCode!
}
~~~

Controller:

~~~java
@Controller
public class OrderCodeController {

    @QueryMapping
    public String echoOrderCode(@Argument("value") String value) {
        return value;
    }
}
~~~

Test with variables to verify `parseValue` and `serialize`:

~~~java
graphQlTester.document("""
        query Echo($value: OrderCode!) {
            echoOrderCode(value: $value)
        }
        """)
    .variable("value", "ORD-000123")
    .execute()
    .path("echoOrderCode")
    .entity(String.class)
    .isEqualTo("ORD-000123");
~~~

Test with a literal to verify `parseLiteral`:

~~~java
graphQlTester.document("""
        query {
            echoOrderCode(value: "ORD-000123")
        }
        """)
    .execute()
    .path("echoOrderCode")
    .entity(String.class)
    .isEqualTo("ORD-000123");
~~~

Additional cases to test:

| Input/output | Expected result |
| --- | --- |
| ORD-000123 via variable | Parses and serializes successfully |
| ORD-000123 via literal | Parses literal and serializes successfully |
| ORD-123 | Rejected because it does not have six digits |
| ord-000123 | Rejected if the contract is case-sensitive |
| Number 123 instead of string | Rejected |
| Resolver returns malformed string | Serialization fails |
| Null value for non-null field | GraphQL rejects due to nullability before scalar processes value |

For `DateTime`, also test timezone offsets, values without offsets, invalid formats, and fractional second precision according to the chosen contract. If the scalar is used inside an input object, add tests for binding into DTOs or method arguments.

## Common issues

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Schema fails to start | Scalar is in SDL but not registered in runtime wiring | Add a `RuntimeWiringConfigurer` bean |
| Scalar not recognized | Name in SDL differs from `GraphQLScalarType` name | Synchronize scalar names |
| Variables succeed but literals fail | Only `parseValue` was implemented or tested | Implement and test `parseLiteral` |
| Valid input but response fails | `serialize` rejects the type returned by the resolver | Check Java runtime type and `serialize` rules |
| Scalar works after library upgrade but fails in another runtime | Extended Scalars version incompatible with GraphQL Java | Cross-check dependency version and dependency tree |
| Invalid value returns null | `Coercing` uses null to signal errors | Throw the appropriate coercion exception |
| Scalar also checks data access permissions | Mixing format validation with business authorization | Move existence and permission checks to service/resolver |

## Comprehensive practice

In an invoice management API, implement the following scalars:

1. Use `Date` for invoice issue date.
2. Use `DateTime` for record creation timestamp.
3. Use `BigDecimal` for total amount if the scalar library and contract satisfy precision requirements.
4. Create `InvoiceCode` following the format `INV-` plus eight digits.

Follow these steps:

- Declare scalars in the SDL and document formats with `@specifiedBy` when a stable specification exists.
- Add the Extended Scalars dependency with a compatible version.
- Register built-in extended scalars via `RuntimeWiringConfigurer`.
- Write `GraphQLScalarType` and `Coercing` for `InvoiceCode`.
- Test variables, literals, and output serialization using `GraphQlTester`.
- Verify that coercion errors do not leak internal data and that services remain responsible for business validation.

## Key takeaways

Custom scalars must be declared in the SDL and registered in runtime wiring. Spring Boot discovers `RuntimeWiringConfigurer` beans and applies them when building `GraphQlSource`. Prefer Extended Scalars for common formats; only write a custom `GraphQLScalarType` when you need a custom contract. A scalar should handle `parseValue`, `parseLiteral`, and `serialize` consistently while throwing the right exception when coercion fails. Test variables, literals, and output with `GraphQlTester`, and keep business validation and authorization in services or resolvers.

## References

- [Spring Boot – GraphQL RuntimeWiring](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Spring for GraphQL – Request Execution and RuntimeWiringConfigurer](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [GraphQL Java – Scalars](https://graphql-java.com/documentation/scalars/)
- [graphql-java-extended-scalars](https://github.com/graphql-java/graphql-java-extended-scalars)
