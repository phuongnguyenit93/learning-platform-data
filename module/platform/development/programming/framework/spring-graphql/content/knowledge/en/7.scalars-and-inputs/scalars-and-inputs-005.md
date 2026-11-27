# Custom Scalar Wiring in Spring for GraphQL

GraphQL has five built-in scalars: `Int`, `Float`, `String`, `Boolean`, and `ID`. When an API needs to represent other data types such as dates and times, exact decimals, UUIDs, or business-specific values, you can declare a **custom scalar** in the SDL and register the data conversion logic in the runtime wiring.

Spring for GraphQL provides `RuntimeWiringConfigurer` to add scalars to `RuntimeWiring.Builder`. With the Spring Boot starter, simply declaring this bean allows auto-configuration to apply it when creating `GraphQlSource`. Custom scalars thus become part of the schema contract and are used consistently whenever GraphQL accepts input or returns output.

## 1. What Problems Do Custom Scalars Solve?

A scalar is a single-valued data type at the GraphQL level. Clients receive a scalar value rather than an object with subfields. The built-in scalars cover many common needs, but they do not directly describe certain application types:

- `DateTime`: a point in time with an offset or timezone.
- `UUID`: an identifier in UUID format.
- `BigDecimal`: a decimal number that must preserve exact precision.
- `Money`: a monetary amount with specific formatting rules and decimal places.
- `URL`: a resource address formatted as a URL.

You should not use `String` for every data type just because JSON can transmit strings. If every date-time field is `String`, the schema cannot express the formatting convention clearly and the runtime has no single place to validate data. Custom scalars let you name types according to domain semantics and centralize parse/serialize rules in one implementation.

A custom scalar is still a single-valued scalar. If data requires multiple independently meaningful attributes—such as an amount and a currency—consider using an object type or input object instead of packing multiple pieces of information into a single string.

## 2. Declaring a Custom Scalar in SDL

SDL uses the `scalar` keyword to declare a new scalar type. Example schema using `DateTime`:

~~~graphql
scalar DateTime

type Query {
    serverTime: DateTime!
}

type Event {
    id: ID!
    name: String!
    startsAt: DateTime!
}
~~~

Declaring `scalar DateTime` only creates the type name in the schema. It does not yet define which Java value will be used or how data is converted between GraphQL and Java. If a scalar is used in a field or argument without a corresponding implementation, the GraphQL runtime will not be able to process that value properly.

The scalar name in the SDL must match the registered `GraphQLScalarType` name. For example, `scalar DateTime` requires the runtime wiring to register a scalar named `DateTime`, not `OffsetDateTime` or `Date`.

## 3. Conversion Lifecycle of a Scalar

A GraphQL scalar has three main conversion paths:

~~~mermaid
flowchart TD
    A[Client JSON variable] --> B[parseValue]
    C[Inline GraphQL literal] --> D[parseLiteral]
    B --> E[Java value]
    D --> E
    E --> F[Resolver / Service]
    F --> G[Java result]
    G --> H[serialize]
    H --> I[JSON response value]
~~~

| Method | When Is It Called? | Example |
| --- | --- | --- |
| `parseValue` | Converts input from GraphQL variables, usually coming from a JSON request | String `"2026-11-20T10:15:30Z"` to `OffsetDateTime` |
| `parseLiteral` | Converts a literal written directly in a GraphQL document | Literal `"2026-11-20T10:15:30Z"` to `OffsetDateTime` |
| `serialize` | Converts a Java value returned by a resolver into a GraphQL response value | `OffsetDateTime` to an ISO-8601 string |

A proper implementation must handle all three methods. Implementing only `parseValue` can make requests with variables work while inline literals fail. Implementing parsing properly while getting serialization wrong can allow a mutation to accept input while failing to convert the response.

## 4. Registering Pre-Built Scalars with Extended Scalars

You do not always need to write `Coercing` yourself. The GraphQL Java Extended Scalars library provides many widely used implementations, such as `DateTime`, `Date`, `Time`, `URL`, `UUID`, and `BigDecimal`.

Add the `com.graphql-java:graphql-java-extended-scalars` dependency to your project. Choose a version compatible with the GraphQL Java version managed by Spring Boot dependency management; avoid upgrading GraphQL Java independently to a version incompatible with Spring for GraphQL.

### 4.1. SDL Declaration

~~~graphql
scalar DateTime
scalar UUID
scalar BigDecimal

type Query {
    serverTime: DateTime!
}

type Product {
    id: UUID!
    price: BigDecimal!
}
~~~

### 4.2. Creating a RuntimeWiringConfigurer Bean

In Spring Boot, you can register scalars using a `RuntimeWiringConfigurer` bean:

~~~java
import graphql.scalars.ExtendedScalars;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration(proxyBeanMethods = false)
public class GraphQlScalarConfiguration {

    @Bean
    RuntimeWiringConfigurer scalarConfigurer() {
        return wiring -> wiring
                .scalar(ExtendedScalars.DateTime)
                .scalar(ExtendedScalars.UUID)
                .scalar(ExtendedScalars.GraphQLBigDecimal);
    }
}
~~~

Spring Boot detects the `RuntimeWiringConfigurer` bean and applies the callback when creating the GraphQL runtime. You do not need to create `GraphQlSource` manually just to register scalars. If the application does not use auto-configuration, you can call `configureRuntimeWiring(...)` on the `GraphQlSource` builder to apply the same configuration.

### 4.3. Corresponding Java Types

Resolvers can use the Java types matching the scalar implementations:

~~~java
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.UUID;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

public record Product(UUID id, BigDecimal price) {}

public interface ProductService {
    Product findById(UUID id);
}

@Controller
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @QueryMapping
    public OffsetDateTime serverTime() {
        return OffsetDateTime.now();
    }

    @QueryMapping
    public Product product(@Argument UUID id) {
        return productService.findById(id);
    }
}
~~~

In this example, the `DateTime` scalar is used with `OffsetDateTime`, `UUID` with `java.util.UUID`, and `BigDecimal` with `java.math.BigDecimal`. Check the scalar implementation's documentation to know the exact input and output Java types it supports; the scalar name alone does not dictate the Java type.

## 5. Defining a Custom Money Scalar

When data rules belong to your own domain, the application can create a `GraphQLScalarType` with its own `Coercing` implementation. For example, `Money` is represented internally as `BigDecimal`, while on the GraphQL wire format it is a decimal string with at most two digits after the decimal point.

Conventions for this example:

- Clients send values as strings, such as `"125.50"`.
- Thousands separators or currency symbols are not accepted.
- At most two decimal places are allowed.
- Java uses `BigDecimal`, not `double`, to preserve precision.
- Responses are serialized as strings with exactly two decimal places.

### 5.1. Declaring the Scalar in the Schema

~~~graphql
scalar Money

type Product {
    id: ID!
    price: Money!
}

type Query {
    product(id: ID!): Product
    echoMoney(value: Money!): Money!
}
~~~

### 5.2. Writing Coercing

`Coercing` defines how to parse input variables, parse literals, and serialize results. The example below uses GraphQL Java's modern `Coercing` API with `GraphQLContext`, `CoercedVariables`, and `Locale`:

~~~java
import graphql.GraphQLContext;
import graphql.execution.CoercedVariables;
import graphql.language.StringValue;
import graphql.language.Value;
import graphql.schema.Coercing;
import graphql.schema.CoercingParseLiteralException;
import graphql.schema.CoercingParseValueException;
import graphql.schema.CoercingSerializeException;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Locale;
import java.util.regex.Pattern;

public final class MoneyCoercing implements Coercing<BigDecimal, String> {

    private static final Pattern FORMAT =
            Pattern.compile("-?(?:0|[1-9]\\d*)(?:\\.\\d{1,2})?");

    @Override
    public String serialize(
            Object dataFetcherResult,
            GraphQLContext graphQLContext,
            Locale locale
    ) {
        if (!(dataFetcherResult instanceof BigDecimal amount)) {
            throw new CoercingSerializeException(
                    "Money result must be represented as BigDecimal"
            );
        }

        try {
            return amount.setScale(2, RoundingMode.UNNECESSARY).toPlainString();
        }
        catch (ArithmeticException ex) {
            throw new CoercingSerializeException(
                    "Money supports at most two fractional digits"
            );
        }
    }

    @Override
    public BigDecimal parseValue(
            Object input,
            GraphQLContext graphQLContext,
            Locale locale
    ) {
        if (!(input instanceof String text)) {
            throw new CoercingParseValueException(
                    "Money variable must be a decimal string"
            );
        }

        try {
            return parseMoney(text);
        }
        catch (IllegalArgumentException ex) {
            throw new CoercingParseValueException("Invalid Money variable");
        }
    }

    @Override
    public BigDecimal parseLiteral(
            Value<?> input,
            CoercedVariables variables,
            GraphQLContext graphQLContext,
            Locale locale
    ) {
        if (!(input instanceof StringValue stringValue)) {
            throw new CoercingParseLiteralException(
                    "Money literal must be a string"
            );
        }

        try {
            return parseMoney(stringValue.getValue());
        }
        catch (IllegalArgumentException ex) {
            throw new CoercingParseLiteralException("Invalid Money literal");
        }
    }

    private static BigDecimal parseMoney(String text) {
        if (!FORMAT.matcher(text).matches()) {
            throw new IllegalArgumentException("Unsupported Money format");
        }
        return new BigDecimal(text).setScale(2, RoundingMode.UNNECESSARY);
    }
}
~~~

Key points in this implementation:

- `serialize` accepts only `BigDecimal`. If a resolver accidentally returns a `Double`, `String`, or another object, the scalar raises a serialization error instead of silently converting it.
- `parseValue` accepts only JSON strings. This prevents clients from sending a JSON floating-point number that may already have lost precision before reaching Java.
- `parseLiteral` accepts only GraphQL `StringValue`, because the scalar's wire format contract is a string.
- `setScale(2, RoundingMode.UNNECESSARY)` does not silently round. Values with more than two decimal places are rejected.
- `toPlainString()` preserves standard decimal notation and avoids scientific notation.

The methods taking `GraphQLContext` and `Locale` reflect the signatures of newer GraphQL Java versions. Spring Boot manages the GraphQL Java version via dependency management; if your project uses an older version, check the `Coercing` signatures in the matching Javadoc before copying the implementation.

### 5.3. Registering GraphQLScalarType in Runtime Wiring

Create a `GraphQLScalarType` whose name matches the SDL and register it in `RuntimeWiring`:

~~~java
import graphql.schema.GraphQLScalarType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration(proxyBeanMethods = false)
public class MoneyScalarConfiguration {

    @Bean
    GraphQLScalarType moneyScalar() {
        return GraphQLScalarType.newScalar()
                .name("Money")
                .description("Decimal amount with at most two fractional digits")
                .coercing(new MoneyCoercing())
                .build();
    }

    @Bean
    RuntimeWiringConfigurer moneyScalarConfigurer(
            GraphQLScalarType moneyScalar
    ) {
        return wiring -> wiring.scalar(moneyScalar);
    }
}
~~~

Once registered, resolvers can accept or return `BigDecimal`:

~~~java
import java.math.BigDecimal;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class MoneyController {

    @QueryMapping
    public BigDecimal echoMoney(@Argument("value") BigDecimal value) {
        return value;
    }
}
~~~

Inline literal request:

~~~graphql
query {
    echoMoney(value: "125.5")
}
~~~

The response contains the value `"125.50"`. When using variables, the value must also be a JSON string:

~~~json
{
    "query": "query Echo($value: Money!) { echoMoney(value: $value) }",
    "variables": {
        "value": "125.50"
    }
}
~~~

Do not send `125.50` as a JSON number under this scalar contract. Also do not send `"$125.50"` or `"125,50"`, because the chosen format does not accept currency symbols or decimal commas.

## 6. Registering Scalars via RuntimeWiringConfigurer or GraphQlSourceBuilderCustomizer?

Spring for GraphQL offers multiple extension points for configuring the GraphQL runtime. When you only need to register scalars, `RuntimeWiringConfigurer` is the focused and straightforward choice.

~~~java
@Bean
RuntimeWiringConfigurer scalarConfigurer() {
    return wiring -> wiring.scalar(ExtendedScalars.DateTime);
}
~~~

If you need deeper customization of the builder that creates `GraphQlSource`, you can use `GraphQlSourceBuilderCustomizer`:

~~~java
import graphql.scalars.ExtendedScalars;
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
GraphQlSourceBuilderCustomizer graphQlSourceCustomizer() {
    return builder -> builder.configureRuntimeWiring(wiring ->
            wiring.scalar(ExtendedScalars.DateTime)
    );
}
~~~

The import in the example uses Spring Boot 3.x. In Spring Boot 4.x, the interface's package changes to `org.springframework.boot.graphql.autoconfigure.GraphQlSourceBuilderCustomizer`; use the package matching your project version.

Both approaches add scalars to the runtime wiring, but their scopes differ:

| Extension Point | When to Use |
| --- | --- |
| `RuntimeWiringConfigurer` | Registering scalars, directives, data fetchers, or type resolvers |
| `GraphQlSourceBuilderCustomizer` | Needing broader builder configuration such as schema factory, schema inspection, instrumentation, or GraphQL builder |

Do not register the same scalar repeatedly across multiple configurers/customizers. If multiple beans configure the same scalar, overriding or conflicts can cause errors during schema creation. Pick a single place to own the implementation and registration.

## 7. Design Rules for Custom Scalars

A scalar is part of the public API. Before writing the implementation, clearly define the data contract.

### 7.1. Choose a Stable Wire Format

For example, with dates and times, you can choose ISO-8601 with an offset such as `2026-11-20T10:15:30+07:00`. For monetary amounts, you can choose a decimal string such as `125.50`. Avoid letting the format depend on the server or client locale.

### 7.2. Keep the Internal Java Type Clear

Choose one consistent Java type per scalar. For example:

| Scalar | Suggested Java Type |
| --- | --- |
| `DateTime` | `OffsetDateTime` or a standardized temporal type |
| `UUID` | `java.util.UUID` |
| `BigDecimal` | `java.math.BigDecimal` |
| `Money` in the example | `java.math.BigDecimal` |

Do not use `double` or `float` to store money or data requiring decimal precision. Binary floating-point numbers cannot accurately represent many common decimal values.

### 7.3. Validate Both Input and Output

`parseValue` and `parseLiteral` protect data entering resolvers. `serialize` protects the response contract when resolvers return data. Do not validate only the input and assume every returned Java value is valid.

### 7.4. Do Not Round Silently

If the domain requires at most two fractional digits, decide explicitly whether a value like `12.345` should be rejected or rounded according to a specific rule. For instance, `RoundingMode.UNNECESSARY` rejects values that require rounding; if business rules allow rounding, choose a rounding mode and place that rule consistently in the domain/service layer.

### 7.5. Error Messages Must Not Leak Sensitive Data

Scalar error messages should describe the expected format and error location well enough for the client to fix the request. Do not include sensitive data, stack traces, or internal details in errors returned to clients.

## 8. Testing Custom Scalars

You should test all three conversion paths: parsing literals, parsing variables, and serializing responses. You can use `GraphQlTester` to execute operations through the GraphQL runtime.

Example of testing the `Money` scalar:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.context.annotation.Import;
import org.springframework.graphql.test.tester.GraphQlTester;

import static org.assertj.core.api.Assertions.assertThat;

@GraphQlTest(MoneyController.class)
@Import(MoneyScalarConfiguration.class)
class MoneyScalarTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void parsesLiteralAndSerializesResult() {
        graphQlTester.document("""
                query {
                    echoMoney(value: "125.50")
                }
                """)
            .execute()
            .path("echoMoney")
            .entity(String.class)
            .isEqualTo("125.50");
    }

    @Test
    void parsesVariable() {
        graphQlTester.document("""
                query Echo($value: Money!) {
                    echoMoney(value: $value)
                }
                """)
            .variable("value", "125.50")
            .execute()
            .path("echoMoney")
            .entity(String.class)
            .isEqualTo("125.50");
    }

    @Test
    void rejectsMoreThanTwoFractionalDigits() {
        graphQlTester.document("""
                query Echo($value: Money!) {
                    echoMoney(value: $value)
                }
                """)
            .variable("value", "12.345")
            .execute()
            .errors()
            .satisfy(errors -> assertThat(errors).isNotEmpty());
    }
}
~~~

The test imports `MoneyScalarConfiguration` to bring the custom scalar into the test slice. `MoneyController` returns the parsed value as-is, so the literal test verifies `parseLiteral` and the variables test verifies `parseValue`; both valid tests pass through `serialize` to produce the response. The `12.345` test verifies that malformed input is rejected by GraphQL.

In addition, test cases where a resolver returns the wrong Java type or returns a `BigDecimal` with an invalid scale to confirm `serialize` rejects invalid output. Unit-testing `MoneyCoercing` directly is also helpful for regex and precision edge cases.

## 9. Common Errors When Wiring Scalars

| Symptom | Cause | Solution |
| --- | --- | --- |
| Scalar is declared, but runtime reports no coercing | Only wrote `scalar DateTime` in SDL without registering an implementation | Register via `RuntimeWiringConfigurer` or a customizer |
| Scalar name mismatch | SDL uses `DateTime` while the registered scalar has a different name | Ensure the `GraphQLScalarType` name matches the SDL |
| Variables work, but literals fail | `parseLiteral` is not implemented properly | Handle AST nodes in `parseLiteral` |
| Input is valid, but response fails | `serialize` does not support the Java type returned by the resolver | Standardize the Java type or fix the serialization contract |
| JSON number is rejected | Scalar specifies string input | Send the variable as a JSON string per the wire format |
| Method signature compile error | `Coercing` API differs across GraphQL Java versions | Check the version managed by Spring Boot and follow its Javadoc |
| Scalar registered twice | Multiple configurers/customizers register the same scalar | Keep a single owner for registration |

## 10. Workflow for Adding a New Custom Scalar

When adding a scalar to an API, follow these steps:

1. Define the domain semantics, internal Java type, and wire format that clients will send and receive.
2. Declare `scalar Name` in the SDL and use the scalar on the necessary fields or arguments.
3. Pick an existing implementation from Extended Scalars if it fits the contract; otherwise, create a dedicated `GraphQLScalarType` and `Coercing`.
4. Implement `parseValue`, `parseLiteral`, and `serialize` completely.
5. Register the scalar via a `RuntimeWiringConfigurer` bean; use `GraphQlSourceBuilderCustomizer` only when broader builder configuration is needed.
6. Test input variables, inline literals, output serialization, and malformed values.
7. Document the format clearly in the API documentation so clients do not have to guess how data is represented.

Custom scalars help the schema express data types in domain language and centralize conversion rules in runtime wiring. When wire formats, Java types, and validation are clearly defined, clients and servers can exchange data much more consistently.

## References

- [Spring for GraphQL — Runtime Wiring](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution.graphqlsource)
- [Spring for GraphQL — GraphQlSource API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/GraphQlSource.html)
- [GraphQL Java — Custom Scalars](https://www.graphql-java.com/documentation/scalars/)
- [GraphQL Java Extended Scalars](https://github.com/graphql-java/graphql-java-extended-scalars)
- [GraphQL Specification — Scalars](https://spec.graphql.org/October2021/#sec-Scalars)
