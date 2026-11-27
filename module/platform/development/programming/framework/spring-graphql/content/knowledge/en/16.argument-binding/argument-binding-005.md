# Binding scalar arguments in Spring for GraphQL

In GraphQL, fields can declare arguments with scalar types such as `ID`, `String`, `Int`, `Float`, or `Boolean`. On the Spring for GraphQL side, the `@Argument` annotation retrieves that value from the operation and binds it to a controller method parameter.

For example, the `product(id: ID!): Product` field requires the client to pass an ID. A `@QueryMapping` method can receive the ID via a Java `String` parameter:

```graphql
type Query {
  product(id: ID!): Product
}
```

```java
@QueryMapping
public Product product(@Argument("id") String productId) {
    return productService.findById(productId).orElse(null);
}
```

GraphQL validates argument types and performs coercion according to the schema before calling the resolver. Spring for GraphQL then supplies the value to the parameter annotated with `@Argument`. Therefore, three things must align: the argument name in the SDL, the name specified in the annotation, and the Java type the method accepts.

## Scalar arguments in GraphQL SDL

GraphQL has five built-in scalar types:

| Scalar | Meaning | Common Java type |
| --- | --- | --- |
| `Int` | Signed 32-bit integer. | `Integer` |
| `Float` | Double-precision floating-point number. | `Double` |
| `String` | Character string. | `String` |
| `Boolean` | True or false value. | `Boolean` |
| `ID` | Unique identifier, serialized as a string. | `String` |

Example schema declaring multiple scalar arguments:

```graphql
type Query {
  product(id: ID!): Product
  searchProducts(keyword: String!, minPrice: Float, limit: Int = 20): [Product!]!
  products(activeOnly: Boolean = true): [Product!]!
}
```

The `!` markers and default values determine whether an argument can be omitted or accept `null`. `keyword: String!` requires a non-null value; `minPrice: Float` may be omitted or passed as `null`; `limit` defaults to `20` when omitted.

`ID` is suited for identifiers, not numbers used in arithmetic. Even if the current database primary key is an integer, you should generally receive IDs in Java as `String` to avoid coupling the API contract to storage types.

## Using `@Argument` in annotated controllers

Spring for GraphQL uses `@Argument` to mark a parameter that receives an argument of the field being resolved. You can declare the argument name directly:

```java
@Controller
public class ProductQueryController {

    private final ProductService productService;

    public ProductQueryController(ProductService productService) {
        this.productService = productService;
    }

    @QueryMapping
    public Product product(@Argument("id") String productId) {
        return productService.findById(productId).orElse(null);
    }
}
```

In this example, the Java parameter name is `productId`, while the SDL argument name is `id`. `@Argument("id")` explicitly tells Spring to bind the value from the `id` argument to the `productId` parameter.

If the Java parameter name matches the argument name, you can use the shorthand form:

```java
@QueryMapping
public Product product(@Argument String id) {
    return productService.findById(id).orElse(null);
}
```

When relying on the Java parameter name, ensure the build preserves parameter name metadata, such as enabling the `-parameters` compiler option if your project setup requires it. Using an explicit name in `@Argument("...")` keeps the mapping resilient to variable renames or build configuration changes.

`@Argument` works on Query fields, Mutation fields, and nested fields handled by `@SchemaMapping`. The argument value always belongs to the current field, not a parent field's arguments.

## Binding multiple scalar arguments

A field can accept multiple scalar arguments. Spring binds each argument to its corresponding parameter:

```graphql
type Query {
  searchProducts(
    keyword: String!
    minPrice: Float
    maxPrice: Float
    limit: Int = 20
    activeOnly: Boolean = true
  ): [Product!]!
}
```

```java
@QueryMapping
public List<Product> searchProducts(
        @Argument("keyword") String keyword,
        @Argument("minPrice") Double minPrice,
        @Argument("maxPrice") Double maxPrice,
        @Argument("limit") Integer limit,
        @Argument("activeOnly") Boolean activeOnly) {
    return productService.search(
            keyword, minPrice, maxPrice, limit, activeOnly);
}
```

Wrapper types `Integer`, `Double`, and `Boolean` can represent `null`. If an argument is declared nullable, using wrapper types is safer than primitive types like `int`, `double`, or `boolean`, because Java primitives cannot hold null.

In this example, the SDL provides defaults for `limit` and `activeOnly`. When the client omits those two arguments, GraphQL applies the default values before invoking the resolver. Thus, the controller receives values that already have schema defaults applied.

## Passing arguments via variables

Clients can pass scalars inline within an operation, but in real-world applications you should prefer variables. Variables separate input data from query text, allowing operations to be reused and avoiding manual string concatenation.

```graphql
query SearchProducts(
  $keyword: String!
  $minPrice: Float
  $limit: Int = 20
) {
  searchProducts(
    keyword: $keyword
    minPrice: $minPrice
    limit: $limit
  ) {
    id
    name
    price
  }
}
```

Variables JSON:

```json
{
  "keyword": "keyboard",
  "minPrice": 500000,
  "limit": 10
}
```

The declared type of a variable must be compatible with the argument position in the schema. For instance, `$keyword: String!` can be passed into `keyword: String!`; a nullable `String` variable cannot be used in a required `String!` position without a suitable default according to GraphQL rules.

Never interpolate client values directly into a query using string concatenation. Using variables lets GraphQL validate input types and prevents syntax errors from quotes or special characters in the data.

## GraphQL coercion runs before invoking the resolver

When receiving an operation, GraphQL validates and converts input values according to their declared types. For scalar arguments, two key cases are:

- **Inline literal:** the value is directly inside the query, e.g., `product(id: "p-100")`. GraphQL checks the literal against the scalar type.
- **Variable:** the value is in the JSON variables payload, e.g., `{ "id": "p-100" }`. GraphQL checks and coerces the runtime value according to the variable type.

If the client passes the wrong type, GraphQL reports a validation or input coercion error before invoking the DataFetcher. For instance, `limit: "ten"` is invalid when the schema requires `Int`; the resolver should never have to parse that string manually.

Scalar-specific notes:

- `Int` only represents integers within the signed 32-bit range. Values exceeding that range require a different scalar type.
- `Float` represents double-precision floating-point numbers; do not use it for currency requiring exact decimal arithmetic.
- `Boolean` only accepts boolean values and does not automatically coerce the string `"true"` to `true` under GraphQL rules.
- `String` accepts strings and does not automatically convert arbitrary JSON types to text.
- `ID` is serialized as a string, and input coercion supports strings or integers. On the client, send IDs as strings to preserve formatting such as leading zeros.

GraphQL coercion checks data types; it does not replace business validation. For example, `minPrice: -10` is still a valid Float in GraphQL; the service must check that prices are non-negative if business rules require it.

## Nullable, Non-Null, and default values

When binding arguments, distinguish three cases: the argument is omitted, the argument is passed as `null`, and the argument is passed with a value.

| SDL | Omit argument | Pass `null` |
| --- | --- | --- |
| `name: String` | Valid; value may be absent. | Valid. |
| `name: String!` | Invalid without a default. | Invalid. |
| `limit: Int = 20` | Valid; uses `20`. | Valid for nullable type; explicit null is not replaced by `20`. |
| `limit: Int! = 20` | Valid; uses `20`. | Invalid. |

Defaults are applied when an argument is omitted. If a client explicitly passes `null` to a nullable argument, the value remains null; defaults do not replace an explicit null.

With a regular nullable Java parameter, an omitted value and an explicit null are both represented as `null`. If business logic needs to distinguish these two states, use `ArgumentValue<T>`:

```java
import org.springframework.graphql.data.ArgumentValue;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;

@QueryMapping
public List<Product> products(
        @Argument("category") ArgumentValue<String> category) {
    if (category.isOmitted()) {
        return productService.findAllCategories();
    }

    if (category.value() == null) {
        return productService.findWithoutCategory();
    }

    return productService.findByCategory(category.value());
}
```

The snippet assumes `category` is declared nullable in the SDL. `ArgumentValue` indicates whether the argument was omitted; `value()` holds the passed value, which can be null. If the schema declared `category: String!`, GraphQL would already reject omitted or null cases before the controller runs.

## Binding to appropriate Java types

Choose Java types based on the scalar and its nullability:

```graphql
type Query {
  product(id: ID!): Product
  products(limit: Int, minPrice: Float, active: Boolean): [Product!]!
}
```

```java
@QueryMapping
public Product product(@Argument("id") String id) {
    return productService.findById(id).orElse(null);
}

@QueryMapping
public List<Product> products(
        @Argument("limit") Integer limit,
        @Argument("minPrice") Double minPrice,
        @Argument("active") Boolean active) {
    return productService.search(limit, minPrice, active);
}
```

Do not bind GraphQL `Int` to Java `Long` assuming GraphQL natively supports 64-bit integers. GraphQL `Int` is still signed 32-bit; if business logic needs large integers, define a custom scalar with explicit coercion rules.

For currency, `Float` can introduce floating-point precision errors. You can use a custom scalar such as `Decimal` or represent amounts in minor units (such as cents) depending on the API contract. A custom scalar requires defining coercion in GraphQL Java and the corresponding Java type.

## Custom scalar arguments

When a value does not fit the five built-in scalars, the schema can declare a custom scalar. For example, `DateTime` representing an instant in time:

```graphql
scalar DateTime

type Query {
  eventsSince(from: DateTime!): [Event!]!
}
```

To bind to `Instant`, the application must register a `GraphQLScalarType` with a `Coercing` implementation defining how to read input literals, parse variables, and serialize outputs. `Coercing` must validate format, timezone, and valid values; the resolver can then accept the corresponding Java type:

```java
@QueryMapping
public List<Event> eventsSince(@Argument("from") Instant from) {
    return eventService.findSince(from);
}
```

This controller snippet only works when the `DateTime` custom scalar is registered and its coercion returns a compatible `Instant`. If the scalar only parses to `String`, an `Instant` parameter needs an appropriate conversion or the resolver must accept `String` and convert explicitly.

In Spring for GraphQL, you can register custom scalars via `RuntimeWiringConfigurer` or the corresponding bean/runtime wiring mechanism for your Spring Boot version. Test both input variables and output serialization with integration tests.

## Binding scalar arguments on nested fields

Arguments do not only appear on root Query fields. A field on an object type can also accept scalar arguments:

```graphql
type Book {
  id: ID!
  title: String!
  summary(maxLength: Int = 200): String
}
```

```java
@SchemaMapping(typeName = "Book", field = "summary")
public String summary(Book book, @Argument("maxLength") Integer maxLength) {
    return summaryService.createSummary(book.getId(), maxLength);
}
```

Here `Book book` is the source object provided by the parent field; `maxLength` is the argument of the `Book.summary` field. Spring binds these two separate data sources into the method parameters.

The same applies to `@MutationMapping` and `@SubscriptionMapping`: `@Argument` always retrieves an argument of the field the method is handling.

## Validation after binding

The GraphQL schema checks structure and scalar types, but it does not know all business rules. After binding, the service or validation layer needs to check conditions such as:

- `limit` must fall within allowed bounds, e.g., 1 to 100.
- `minPrice` must not be negative.
- `keyword` must not consist solely of whitespace.
- IDs must refer to existing resources that the user is authorized to access.
- `from` must not be after `to` in a date range query.

You can use Bean Validation or service-layer validation depending on the application structure. Either way, validation errors should be translated into GraphQL errors with stable messages and error codes. Do not rely on GraphQL scalar coercion to replace business validation.

## Testing scalar argument binding

`GraphQlTester` can send operations with variables to verify values are bound into the controller and the expected response is produced:

```java
@Test
void bindsScalarVariables() {
    graphQlTester.document("""
        query Search($keyword: String!, $limit: Int) {
          searchProducts(keyword: $keyword, limit: $limit) {
            id
            name
          }
        }
        """)
        .variable("keyword", "keyboard")
        .variable("limit", 5)
        .execute()
        .path("searchProducts[0].name")
        .entity(String.class)
        .isEqualTo("Mechanical Keyboard");
}
```

Beyond the happy path, you should test:

- Arguments whose names differ from Java parameter names and are specified with `@Argument("...")`.
- Missing variables for Non-Null arguments rejected before the resolver runs.
- Wrong scalar types, such as a string passed to `Int`, producing coercion errors.
- `Int` values outside the 32-bit range being rejected.
- Nullable arguments receiving `null` per the contract.
- Omitted arguments receiving the SDL default.
- Explicit null not being replaced by the default.
- `ArgumentValue` distinguishing omitted from explicit null if business logic requires it.
- Custom scalars parsing variables, parsing literals, and serializing outputs properly.
- Business validation rejecting values that have the right type but are invalid.

When verifying that a resolver is not called on coercion failure, you can mock the service and assert zero interactions. This confirms errors are caught at the GraphQL layer before business logic runs.

## Common errors

| Symptom | Cause | Fix |
| --- | --- | --- |
| `@Argument` receives null despite client sending value | SDL argument name does not match annotation or variable was not passed properly. | Check names in SDL, `@Argument("...")`, and variables. |
| Spring fails to bind parameter | Java type is incompatible with coerced scalar value. | Use a compatible Java type or register explicit conversion/custom scalar. |
| Required argument is omitted | SDL declares Non-Null without a default. | Pass the variable or declare a default if business rules allow. |
| Default value is not applied | Client passes explicit `null`; defaults only apply when omitted. | Distinguish omitted from null and adjust schema/logic. |
| `Int` rejects large numbers | GraphQL `Int` is only signed 32-bit. | Use a custom scalar for large integers. |
| Monetary amounts lose precision | Using `Float` for exact decimal math. | Use a decimal custom scalar or minor currency units. |
| Java primitive throws error on null argument | `int`, `double`, `boolean` cannot hold null. | Use wrappers `Integer`, `Double`, `Boolean` for nullable arguments. |
| Custom scalar fails to bind to `Instant` | `Coercing` returns a different type or is not registered. | Align `parseValue` return type with parameter type and test runtime wiring. |

## Key takeaways

`@Argument` extracts the value from an argument of the current field and binds it to a controller method parameter. Names in the SDL must match annotation names; specify `@Argument("name")` when you want resilient mapping. Use Java types matching each scalar, prefer wrappers for nullable arguments, and remember that GraphQL `Int` is a signed 32-bit integer.

GraphQL validates scalar inputs and applies defaults before calling the resolver. An omitted argument differs from an argument passed as `null`; when you need to distinguish them, use `ArgumentValue<T>`. For specialized data types such as timestamps or decimals, register explicit custom scalars and coercion logic. After binding, the service must still perform business validation and authorization.
