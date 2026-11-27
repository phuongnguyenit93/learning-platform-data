# String, Int, Float, and Boolean in GraphQL

GraphQL provides four basic scalars that appear in almost every API: `String`, `Int`, `Float`, and `Boolean`. A scalar is a single data type with no subfields for clients to select further. They are used directly in output objects, field arguments, and input objects.

In Spring for GraphQL, these standard scalars are already supported out of the box by GraphQL. You declare them in the SDL and then map values to appropriate Java types in resolvers or input objects. What matters is understanding the data types, limits, and conversion rules in both directions: data sent in by the client and results returned by the server.

## 1. Overview of the Four Basic Scalars

| GraphQL Scalar | Meaning | Common Java Type | Corresponding JSON Type |
| --- | --- | --- | --- |
| `String` | Unicode text | `String` | String |
| `Int` | Signed 32-bit integer | `Integer` / `int` | Integer number |
| `Float` | Double-precision floating-point number | `Double` / `double` | Number |
| `Boolean` | True or false value | `Boolean` / `boolean` | Boolean |

These scalars are nullable by default. Add `!` to require a non-null value, such as `String!`, `Int!`, `Float!`, or `Boolean!`. Nullability is a GraphQL-specific rule; it is not automatically inferred from whether a Java property uses a primitive or wrapper type.

## 2. String: Text Data

`String` represents a sequence of characters. GraphQL SDL uses double quotes for string literals:

```graphql
type Query {
    greeting(name: String!): String!
    description: String
}
```

A client can execute the query:

```graphql
query {
    greeting(name: "An")
    description
}
```

Sample response:

```json
{
  "data": {
    "greeting": "Hello, An!",
    "description": null
  }
}
```

Some rules to keep in mind:

- String literals use double quotes, such as `"GraphQL"`; single-quote syntax like `'GraphQL'` is not a valid string literal in GraphQL.
- Strings can contain Unicode, so accented Vietnamese characters are supported normally.
- When you need to represent double quotes, backslashes, or newlines inside a literal, you must escape them according to GraphQL string syntax.
- `String!` does not mean the string must be non-empty. The string `""` is still a non-null String; non-empty rules need to be checked at the business logic layer.

Example of an input object receiving search criteria:

```graphql
input ProductSearchInput {
    keyword: String
    category: String
}

type Query {
    searchProducts(filter: ProductSearchInput!): [Product!]!
}
```

Both `keyword` and `category` are nullable, so the client can omit them or send null according to the input contract. If the application needs to distinguish between omitting a field and passing null, use the appropriate binding mechanism in Spring for GraphQL and clearly define the update/search behavior.

A Java resolver should return `String` for a String field:

```java
@QueryMapping
public String greeting(@Argument("name") String name) {
    return "Hello, " + name + "!";
}
```

You should not return an arbitrary domain object for a `String` field and expect GraphQL to automatically choose a property to serialize. Return the exact type published by the schema or explicitly map the object to a string at the application layer.

## 3. Int: Signed 32-bit Integer

GraphQL `Int` is a signed 32-bit integer. Valid values fall within the range:

\[
-2^{31} \leq n \leq 2^{31}-1
\]

This corresponds to `-2147483648` through `2147483647`. `Int` is suitable for quantities, positions, page numbers, or counts within this range.

Schema example:

```graphql
type Product {
    stock: Int!
    reviewCount: Int!
}

type Query {
    totalProducts: Int!
    productsInStock(minimum: Int = 1): [Product!]!
}
```

A query:

```graphql
query {
    totalProducts
    productsInStock(minimum: 5) {
        stock
        reviewCount
    }
}
```

`Int` accepts integers and does not accept decimal values. For example, `5` is valid, whereas `5.5` is not a valid Int value. Values exceeding the 32-bit range are also rejected on input or cannot be serialized as Int on output.

In Java, use `Integer` or `int` to map GraphQL `Int`. If a field is nullable or an input can be omitted, prefer `Integer` because the wrapper type can represent null. The primitive `int` type always holds a numeric value and cannot represent null; an unassigned primitive variable can also carry the default value `0`, making it hard for the application to distinguish whether the client sent 0 or sent no value at all.

Resolver example:

```java
@QueryMapping
public Integer totalProducts() {
    return productService.countProducts();
}
```

If the system needs integers larger than the 32-bit limit, do not force the data into `Int`. Consider designing a custom scalar or representing the value as `String` with clear formatting rules. The built-in GraphQL `Int` is not a 64-bit `long` type.

## 4. Float: Double-Precision Floating-Point Number

GraphQL `Float` represents a double-precision floating-point number. In Java, the commonly used type is `Double` or `double`.

```graphql
type Product {
    rating: Float
    averagePrice: Float!
}

type Query {
    averageRating: Float
}
```

Float literals can include a fractional part or an exponent:

```graphql
query {
    averageRating
}
```

Example response value:

```json
{
  "data": {
    "averageRating": 4.75
  }
}
```

GraphQL `Float` accepts either integer or floating-point values in a Float input position. Therefore, `4`, `4.0`, and `4.75` can all be coerced into Float. A string like `"4.75"` is not a valid numeric Float value. Non-finite values such as `NaN` or infinity are not valid JSON numbers to transmit in a GraphQL response.

Resolver example:

```java
@QueryMapping
public Double averageRating() {
    return productService.calculateAverageRating();
}
```

You should not use GraphQL `Float` to store or transmit monetary amounts that require exact decimal precision. Binary floating-point numbers can represent some decimal values only approximately, leading to rounding errors in calculations. For money, it is usually better to use an integer in the smallest currency unit (such as cents) or a custom scalar based on `BigDecimal` with clearly defined serialize/parse rules.

## 5. Boolean: True or False Value

GraphQL `Boolean` represents only two values: `true` and `false`. Boolean literals are lowercase:

```graphql
type Product {
    active: Boolean!
    featured: Boolean
}

type Query {
    isStoreOpen: Boolean!
}
```

Query example:

```graphql
query {
    isStoreOpen
    products {
        active
        featured
    }
}
```

Response example:

```json
{
  "data": {
    "isStoreOpen": true,
    "products": [
      { "active": true, "featured": false },
      { "active": true, "featured": null }
    ]
  }
}
```

`Boolean` does not automatically convert strings like `"true"`, `"yes"`, or the number `1` into Boolean on input. The client must send a proper JSON boolean type. `Boolean!` requires a true or false value; it does not accept null.

In Java, use `Boolean` for nullable fields and `boolean` when the contract always guarantees a value. For optional inputs, the `Boolean` wrapper helps distinguish `null` from `false`. If you use the primitive `boolean`, the default value is `false`, so a state where the client did not send the field can become ambiguous with the client explicitly sending false.

## 6. Combining Scalars in a Schema

A real-world schema can use all four scalars within the same object and input:

```graphql
type Product {
    id: ID!
    name: String!
    stock: Int!
    rating: Float
    active: Boolean!
}

input ProductFilter {
    keyword: String
    minimumStock: Int
    minimumRating: Float
    activeOnly: Boolean = true
}

type Query {
    products(filter: ProductFilter!): [Product!]!
}
```

In this example:

- `name` is required text.
- `stock` is a 32-bit integer and cannot be null.
- `rating` is a nullable floating-point number because a product may not have been rated yet.
- `active` always has a true or false state.
- `keyword`, `minimumStock`, and `minimumRating` are optional filter criteria.
- `activeOnly` defaults to true if the client does not provide this field.

A client can send the query and variables:

```graphql
query FindProducts($filter: ProductFilter!) {
    products(filter: $filter) {
        id
        name
        stock
        rating
        active
    }
}
```

```json
{
  "filter": {
    "keyword": "keyboard",
    "minimumStock": 3,
    "minimumRating": 4.25,
    "activeOnly": true
  }
}
```

JSON variables must preserve the exact scalar types: strings enclosed in double quotes, integers without a fractional part for `Int`, numbers for `Float`, and `true`/`false` for `Boolean`. Do not send all values as strings and expect GraphQL to convert them automatically.

## 7. Mapping Input Objects to Java

With Spring for GraphQL, an input object can be bound to a Java record or class. For example:

```java
public record ProductFilter(
        String keyword,
        Integer minimumStock,
        Double minimumRating,
        Boolean activeOnly) {
}
```

The resolver receives the input object using `@Argument`:

```java
import java.util.List;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @QueryMapping
    public List<Product> products(@Argument("filter") ProductFilter filter) {
        return productService.search(filter);
    }
}
```

`String`, `Integer`, `Double`, and `Boolean` correspond respectively to the four scalars in the SDL. Wrapper types are used in the record because these input fields can be omitted or receive null. If the SDL provides a default such as `activeOnly: Boolean = true`, GraphQL applies the default when the field is omitted; verify how the input object binding behaves and use the received value according to the declared contract.

If you need to distinguish between an omitted field and a field passed as null, you can use `ArgumentValue<T>` on an appropriate argument or a binding type that preserves input presence state. Do not use primitives for optional fields because primitives lose null/omitted information.

## 8. Validation: Valid Scalar Type Does Not Mean Valid Business Logic

GraphQL scalars check basic types and coercibility. They do not replace business validation. For example:

- `name: String!` can still accept an empty string.
- `age: Int!` can still accept negative numbers if the schema has no additional rules.
- `rating: Float` can still accept `-100.0` even if business rules only allow 0 to 5.
- `active: Boolean!` only validates true/false; it does not decide who has permission to change the state.

You can check these conditions in the service or validation layer of the application. For example:

```java
public ProductFilter validate(ProductFilter filter) {
    if (filter.minimumStock() != null && filter.minimumStock() < 0) {
        throw new IllegalArgumentException("minimumStock must not be negative");
    }

    if (filter.minimumRating() != null
            && (filter.minimumRating() < 0 || filter.minimumRating() > 5)) {
        throw new IllegalArgumentException("minimumRating must be between 0 and 5");
    }

    if (filter.keyword() != null && filter.keyword().isBlank()) {
        throw new IllegalArgumentException("keyword must not contain only whitespace");
    }

    return filter;
}
```

This snippet only illustrates input validation; a real application should map validation errors into GraphQL errors with appropriate information for the client. Avoid returning stack traces or internal details in the message.

## 9. Literals and Variables: Sending the Right Data Types

GraphQL supports passing values directly in the document or using variables. With the document:

```graphql
query {
    productByCode(code: "P-100") {
        name
    }
    productsWithStock(minimum: 10) {
        name
    }
}
```

With variables, the document declares variable types and the request body provides JSON values:

```graphql
query ProductByCode($code: String!, $minimum: Int!) {
    productByCode(code: $code) {
        name
    }
    productsWithStock(minimum: $minimum) {
        name
    }
}
```

```json
{
  "code": "P-100",
  "minimum": 10
}
```

Variables are useful because clients can reuse a GraphQL document and change input data without concatenating query strings. They also help avoid string escaping errors and make the type of each value explicit.

Example of calling the HTTP endpoint with `curl`:

```bash
curl http://localhost:8080/graphql \
  -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{
    "query": "query ProductByCode($code: String!, $minimum: Int!) { productByCode(code: $code) { name } productsWithStock(minimum: $minimum) { name } }",
    "variables": { "code": "P-100", "minimum": 10 },
    "operationName": "ProductByCode"
  }'
```

## 10. Testing Scalars with GraphQlTester

Tests should verify that scalars are bound into Java and serialized into the response with the right types. Example with `GraphQlTester` configured in the test context:

```java
@Test
void scalarArgumentsAreMappedToExpectedValues() {
    graphQlTester.document("""
            query Greeting($name: String!, $count: Int!, $ratio: Float!, $enabled: Boolean!) {
                greeting(name: $name)
                repeatedCount(count: $count)
                scaledValue(ratio: $ratio)
                enabled(value: $enabled)
            }
            """)
        .variable("name", "An")
        .variable("count", 3)
        .variable("ratio", 2.5)
        .variable("enabled", true)
        .execute()
        .path("greeting")
        .entity(String.class)
        .isEqualTo("Hello, An!");
}
```

The `repeatedCount`, `scaledValue`, and `enabled` fields in the example must be declared in the schema and have corresponding resolvers. You can write separate assertions for each field using `.path(...).entity(Integer.class)`, `.entity(Double.class)`, or `.entity(Boolean.class)` to verify the returned type and value.

You should add edge cases:

1. Strings with accented Vietnamese characters, special characters, and empty strings.
2. Int at 32-bit boundary values and out-of-range values.
3. Int receiving a decimal literal or a non-integer JSON variable.
4. Float receiving integer and decimal numbers, and rejecting numeric strings.
5. Boolean receiving true/false and rejecting strings or numbers.
6. Nullable scalars accepting null; Non-Null scalars rejecting null.
7. Input objects applying defaults when fields are omitted.

## 11. Common Errors

| Symptom | Cause | Solution |
| --- | --- | --- |
| String argument is rejected | Client sends a number or boolean instead of a string | Send a JSON string or GraphQL string literal. |
| Int is rejected even though the value looks numeric | Value has a fractional part or exceeds the 32-bit range | Send an integer within the valid range; use another scalar if the domain needs large numbers. |
| Float does not accept a value | Client sends a string instead of a JSON number, or a non-finite value | Send a finite JSON number. |
| Boolean does not accept `"true"` | That is a string, not a Boolean | Send `true` or `false` without quotes. |
| Resolver violates Non-Null | Resolver returns null while SDL declares `!` | Ensure a value is always present or adjust nullability to match business rules. |
| Monetary amounts have precision errors | Using Float for decimal calculations requiring exact precision | Use the smallest currency unit as Int or a custom scalar based on BigDecimal. |
| Optional input turns into 0/false | Using Java primitives for data that can be omitted | Use wrappers `Integer`, `Double`, `Boolean` or a binding that preserves omitted state. |

## 12. Checklist When Using Basic Scalars

1. Choose `String` for text, `Int` for 32-bit integers, `Float` for double-precision floating-point numbers, and `Boolean` for true/false states.
2. Add `!` only when the application can guarantee a non-null value.
3. Use the exact JSON types when sending variables; do not encode every value as a string.
4. Map to `String`, `Integer`, `Double`, and `Boolean` in Java.
5. Prefer wrapper types for nullable fields or optional inputs to preserve null.
6. Account for the 32-bit limit of Int and floating-point precision errors of Float.
7. Use business validation for value ranges, empty strings, negative numbers, or rating limits.
8. Do not use Float for currency requiring exact decimal precision.
9. Test inputs, outputs, nullability, and boundary values.

The four scalars `String`, `Int`, `Float`, and `Boolean` form the data type foundation for most GraphQL schemas. When you declare contracts accurately in the SDL, send variables with the proper types, and map them to appropriate Java types, the API becomes easier to use and avoids many runtime coercion errors.
