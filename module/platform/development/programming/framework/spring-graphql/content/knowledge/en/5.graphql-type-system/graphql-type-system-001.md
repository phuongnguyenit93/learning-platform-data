# Scalar type

## Objectives

After this lesson, you will be able to:

- Explain how a scalar type serves as a leaf data type in GraphQL and how it appears in a schema.
- Distinguish between the five built-in scalars: `Int`, `Float`, `String`, `Boolean`, and `ID`.
- Understand how GraphQL converts input data and output results.
- Design custom scalars for domain-specific values such as date-times or specialized identifiers.
- Register scalars with Spring for GraphQL through `RuntimeWiringConfigurer` and test parsing and serialization.

## What is a scalar type?

A scalar is a fundamental data type that GraphQL treats as a single value. When a client queries a scalar field, the client receives that value directly and does not write a nested selection set for it.

For example, `Book` has the fields `id`, `title`, and `published`:

```graphql
type Book {
  id: ID!
  title: String!
  published: Boolean!
}
```

The client can select all three fields:

```graphql
query {
  bookById(id: "book-101") {
    id
    title
    published
  }
}
```

The response contains the leaf values:

```json
{
  "data": {
    "bookById": {
      "id": "book-101",
      "title": "Spring in Practice",
      "published": true
    }
  }
}
```

The fields `id`, `title`, and `published` do not have subfields. Conversely, if `Book` has a field `author: Author`, the client must write a selection set for `author` because `Author` is an object type.

Scalars are used in both output and input positions: field return types, field arguments, and fields in input objects. A scalar can appear on both sides—for example, `String` is used to return a book title or accept a search keyword.

## The five built-in scalars

GraphQL defines five standard scalars that every implementation must support:

| Scalar | Meaning | Example |
| --- | --- | --- |
| `Int` | Signed 32-bit integer | `42`, `-7` |
| `Float` | Floating-point number | `19.95`, `-0.5` |
| `String` | Unicode character string | `"GraphQL"` |
| `Boolean` | True or false value | `true`, `false` |
| `ID` | Object identifier, serialized as a string | `"book-101"` |

These scalars have their own coercion rules. Having a similar data type in Java does not mean every Java value is automatically valid for a GraphQL scalar.

### `Int`

`Int` is a signed 32-bit integer, ranging from -2,147,483,648 to 2,147,483,647. It is suitable for quantities, ordering, or bounded counters in the domain.

```graphql
type Inventory {
  availableQuantity: Int!
}
```

Do not use `Int` for large integers that exceed the 32-bit range. If the business domain requires larger numbers, consider a custom scalar such as `Long` or `BigInteger` from an extended scalars library, while agreeing on the representation with the client.

### `Float`

`Float` represents a real number according to GraphQL's floating-point rules. For example:

```graphql
type Product {
  rating: Float
  weight: Float
}
```

Floating-point types can introduce precision errors. You should not use `Float` to store or transmit monetary values if the business requires exact decimal arithmetic. Consider `BigDecimal` in the Java layer and a decimal scalar with clearly defined serialization, parsing, and precision rules.

### `String`

`String` is used for text. String values in GraphQL literals are enclosed in double quotes:

```graphql
query {
  searchBooks(keyword: "Spring") {
    title
  }
}
```

For input data from clients, the server still needs to validate length, format, and content according to business requirements. The `String` type only confirms that the data is a character string; it does not automatically validate emails, URLs, product codes, or application-specific rules.

### `Boolean`

`Boolean` accepts only the two values `true` and `false`:

```graphql
type Book {
  archived: Boolean!
}
```

Do not confuse `false` with `null`. `false` is a defined value; `null` indicates that the field has no value or is allowed to be absent according to the schema and execution result.

### `ID`

`ID` represents an identifier and is commonly used for object keys:

```graphql
type Query {
  bookById(id: ID!): Book
}
```

`ID` is serialized as a string in the response. When passing input, GraphQL allows either string or integer values according to this scalar's rules, whether the value is written directly in the document or passed via variables; however, strings should be used to clearly represent identifiers in queries and variables.

`ID` does not mean the server automatically checks existence, uniqueness, or access permissions for the object. Nor does it have to be a UUID or a database primary key. That convention must be defined by the application.

## Scalars in input and output

Scalars appear in return type declarations:

```graphql
type Book {
  id: ID!
  title: String!
  pageCount: Int
}
```

Scalars also appear in arguments and input objects:

```graphql
input CreateBookInput {
  title: String!
  pageCount: Int
  published: Boolean = false
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
```

In this example, `String`, `Int`, and `Boolean` are the types of data sent by the client. The server must validate the values before using them in business logic. `published` has a default value of `false` when the client does not provide this field, following GraphQL's default value rules.

Scalars are valid types for both input and output. Object types are only for output; input object types are only for input. If you need to pass a nested data structure into a mutation, declare an `input` type instead of using an object type.

## Nullability and lists are not new scalars

The `!` mark and square brackets are GraphQL type modifiers. They can wrap scalars or other valid types:

| Declaration | Meaning |
| --- | --- |
| `String` | A string or `null` |
| `String!` | A required string, cannot be `null` |
| `[String]` | A list that can be `null`, each element can be `null` |
| `[String!]` | A list that can be `null`, each element cannot be `null` |
| `[String]!` | A list that cannot be `null`, elements can be `null` |
| `[String!]!` | Both the list and all elements cannot be `null` |

Example:

```graphql
type Author {
  nicknames: [String!]!
}
```

The `nicknames` field always returns a list; the list can be empty but cannot be `null`, and every element must be a non-null string. Nullability directly affects how GraphQL propagates errors when a resolver returns `null` for a non-null field.

## GraphQL coercion: parsing input and serializing output

GraphQL does more than convert JSON into Java objects. The GraphQL engine performs coercion to ensure data conforms to the declared scalar.

There are three important operations when working with scalars:

| Operation | Data direction | Meaning |
| --- | --- | --- |
| Parse value | Client variables → internal value | Converts and validates input taken from JSON variables |
| Parse literal | GraphQL document → internal value | Converts and validates values written directly in the query |
| Serialize | Resolver value → JSON response | Converts internal values into the format the client receives |

Example query using variables:

```graphql
query BookById($id: ID!) {
  bookById(id: $id) {
    id
    title
  }
}
```

```json
{
  "id": "book-101"
}
```

In this case, GraphQL parses the variable according to the `ID!` type. If the client writes `bookById(id: "book-101")` inline, GraphQL parses the literal in the document. When the resolver returns a `Book` object, scalar fields such as `id` and `title` are serialized before building the JSON response.

A value may be valid at the Java layer yet fail to serialize according to the declared scalar. For example, if a resolver returns an object incompatible with the `String` scalar, GraphQL can produce an execution error. Therefore, when creating a custom scalar, you must clearly define all three conversion directions, not just input validation.

## When do you need a custom scalar?

The five standard scalars cover basic data types, but real-world APIs often have values with specific semantics:

- Date and time with a time zone, such as order creation timestamps.
- Exact decimal numbers, such as monetary amounts or rates.
- UUIDs, URLs, emails, or identifiers with a custom format.
- Large integers exceeding the range of `Int`.

You could represent these values using `String` or `Float`, but then the schema does not clearly describe the data rules. Custom scalars help give types meaningful names, centralize validation, and enforce the wire format across the API.

Example schema declaring a `DateTime` scalar:

```graphql
scalar DateTime

type Event {
  id: ID!
  startsAt: DateTime!
}

type Query {
  event(id: ID!): Event
}
```

The name `DateTime` tells the client that the field is a date-time value. However, the SDL by itself does not specify whether the string must follow ISO-8601, whether a time zone is required, or whether Java should use `Instant`, `OffsetDateTime`, or another type. Those rules must be determined by the scalar implementation and API documentation.

## Using pre-built extended scalars

Before writing your own `Coercing`, check extended scalar libraries. The GraphQL Java project provides the `graphql-java-extended-scalars` library, which offers common scalars such as `DateTime`, `Date`, `Long`, `BigDecimal`, `UUID`, and several others.

Add the dependency version compatible with the GraphQL Java version managed by Spring Boot. Gradle example:

```groovy
dependencies {
    implementation 'com.graphql-java:graphql-java-extended-scalars:<compatible-version>'
}
```

The `<compatible-version>` placeholder must be replaced with the version matching GraphQL Java in the application's dependency management. Avoid upgrading GraphQL Java independently just to get a scalar if doing so mismatches the version supported by Spring for GraphQL.

After adding the dependency, register the scalar with `RuntimeWiringConfigurer`:

```java
import graphql.scalars.ExtendedScalars;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class GraphQlScalarConfiguration {

    @Bean
    RuntimeWiringConfigurer runtimeWiringConfigurer() {
        return wiringBuilder ->
                wiringBuilder.scalar(ExtendedScalars.DateTime);
    }
}
```

The SDL can then use that scalar:

```graphql
scalar DateTime

type Event {
  id: ID!
  startsAt: DateTime!
}
```

Spring Boot GraphQL collects `RuntimeWiringConfigurer` beans and applies them when building runtime wiring. The scalar must be registered under the exact name used in the schema. Read the documentation for the library version you are using to confirm which Java types the scalar supports and which data formats it accepts.

## Defining your own custom scalar

When a data type has system-specific rules, you can define a `GraphQLScalarType` using GraphQL Java. The key component is `Coercing`, where input parsing and output serialization are implemented.

For example, a library system uses order codes formatted as `ORD-` followed by six digits. The SDL declares:

```graphql
scalar OrderCode

type Order {
  code: OrderCode!
}

type Query {
  order(code: OrderCode!): Order
}
```

The scalar implementation can represent the internal value as a Java `String`. The example below illustrates the extension points; the exact `Coercing` method signatures may vary across GraphQL Java versions, so adjust them according to your project's dependency:

```java
private static final Pattern ORDER_CODE_PATTERN =
        Pattern.compile("ORD-[0-9]{6}");

private static boolean isValidOrderCode(String value) {
    return ORDER_CODE_PATTERN.matcher(value).matches();
}

private static final GraphQLScalarType ORDER_CODE =
        GraphQLScalarType.newScalar()
            .name("OrderCode")
            .description("Order code in the format ORD- followed by six digits")
            .coercing(new Coercing<String, String>() {
                // serialize: validate the value returned by the resolver and convert it to String.
                // parseValue: validate input taken from variables.
                // parseLiteral: validate a literal in the GraphQL document.
            })
            .build();
```

The snippet above focuses on the scalar structure; the bodies of the three methods must be implemented according to the `Coercing` API of the GraphQL Java version in use. Each method should reject malformed data with the corresponding exception (`CoercingSerializeException`, `CoercingParseValueException`, or `CoercingParseLiteralException`). You should not return `null` to hide invalid input.

Register the scalar the same way you register an extended scalar:

```java
@Bean
RuntimeWiringConfigurer runtimeWiringConfigurer() {
    return wiringBuilder -> wiringBuilder.scalar(ORDER_CODE);
}
```

For `parseLiteral`, verify the exact AST node type accepted by the scalar, such as a string literal. For `parseValue`, verify the Java type of the variable data. For `serialize`, ensure the value returned by the resolver can be converted into a stable wire format. All three paths must enforce the same business rules so queries using variables and queries using literals do not behave differently.

## Documenting a custom scalar's contract

The scalar name makes the schema clearer, but clients cannot infer the full format from the name alone. Write an SDL description and publish a specification if the scalar uses an external standard:

```graphql
"""Order code in the format ORD- followed by six digits."""
scalar OrderCode
```

GraphQL also supports the `@specifiedBy` directive on scalars to link to a specification document describing the scalar:

```graphql
scalar DateTime @specifiedBy(url: "https://example.com/api/date-time-format")
```

The URL above is only an illustrative example; in a real API, use a stable document owned by your organization or an appropriate public specification. The documentation should describe literal format, variable format, response format, time zone, precision, and data constraints.

## Testing scalars in Spring for GraphQL

Scalars should be tested both in isolation and through GraphQL operations. With `GraphQlTester`, you can send variables to verify `parseValue` and inspect the response to verify `serialize`.

Example test for a query accepting `OrderCode`:

```java
graphQlTester.document("""
        query FindOrder($code: OrderCode!) {
            order(code: $code) {
                code
            }
        }
        """)
    .variable("code", "ORD-000123")
    .execute()
    .path("order.code")
    .entity(String.class)
    .isEqualTo("ORD-000123");
```

You should test both valid and invalid cases:

| Case | Expected result |
| --- | --- |
| `ORD-000123` | Parsed successfully |
| `ORD-12` | Rejected due to invalid format |
| `ord-000123` | Rejected if the convention is case-sensitive |
| Non-string value | Rejected when the scalar requires a string |
| Resolver returns invalid code | Serialization fails and produces an execution error |
| Query passes literal instead of variable | `parseLiteral` applies the same validation rules |

When testing errors, verify that the response contains an appropriate error and does not leak internal details such as stack traces or sensitive data. For custom date-time scalars, add tests for time zones, offsets, sub-second precision, and boundary values.

## Common scalar design mistakes

**Using `Float` for currency.** Floating-point numbers can introduce rounding and arithmetic inaccuracies. Choose an exact decimal representation and standardize scale, rounding, and currency.

**Treating `ID` as a security mechanism.** `ID` only describes an identifier. The server must still verify that the object exists and that the user is authorized to access it.

**Validating only variables.** Queries can pass literals directly. Custom scalars need to handle both `parseValue` and `parseLiteral`.

**Parsing input while forgetting serialization.** A resolver can return data that does not conform to the scalar format. Both output values and input values must be checked.

**Defining overly generic scalars.** A scalar named `Date` that does not specify time zone, format, or precision forces clients to guess. Document the contract and test the format.

**Using a custom scalar to replace an object type.** Scalars are suited for single values. If data has multiple attributes that clients need to select individually, use an object type. For example, `Money { amount, currency }` is usually more flexible than an unstructured currency string.

**Ignoring data limits.** String scalars can receive very large payloads if the server imposes no limits. Enforce size limits, validate format, and avoid expensive processing on untrusted input.

## Putting it all together

In an order management API, design a schema with the following fields:

1. `Order.id` using `ID!`.
2. `Order.totalAmount` using a decimal type suited to monetary precision requirements.
3. `Order.createdAt` using a custom `DateTime` scalar.
4. `Query.order(code: OrderCode!)` accepting an order code formatted according to system rules.

Implement it using these steps:

- Choose built-in scalars when the data type fits.
- Add an extended scalars library if a scalar matches the required contract.
- Write custom `Coercing` only when system-specific rules are needed.
- Register the scalar with `RuntimeWiringConfigurer`.
- Write tests for literals, variables, output serialization, and malformed input.
- Document format, nullability, precision, and constraints for each scalar.

## Key takeaways

Scalars are GraphQL's leaf data types. The five standard scalars are `Int`, `Float`, `String`, `Boolean`, and `ID`; they have their own coercion rules and limits. `!` and lists are type modifiers, not new scalars. When you need date-times, decimals, or specialized identifiers, you can use an extended scalars library or define a `GraphQLScalarType` with `Coercing`. In Spring for GraphQL, register scalars via `RuntimeWiringConfigurer`; test variable parsing, literal parsing, and output serialization to ensure a consistent contract.
