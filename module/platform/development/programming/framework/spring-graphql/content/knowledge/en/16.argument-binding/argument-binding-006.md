# Binding input objects

## Objectives

After this lesson, you will be able to:

- Explain the role of GraphQL input objects and distinguish them from object types used for returned data.
- Declare input types containing scalars, enums, nested objects, and lists.
- Use `@Argument` to bind input objects into Java records or DTOs.
- Understand how `GraphQlArgumentBinder` instantiates objects and converts nested data.
- Handle default values, nullability, omitted arguments, and explicit nulls.
- Combine Bean Validation with input DTOs.
- Distinguish GraphQL validation errors, binding errors, and business errors.
- Test the binding process using `GraphQlTester`.

## 1. What are input objects used for?

A GraphQL input object is a data type designed for operation inputs. It groups multiple related values into a named structure, allowing mutations or queries to receive complex data without declaring an excessive number of separate arguments.

For example, creating an order requires a customer ID, shipping address, list of order items, and shipping method. You could declare each argument individually on the mutation, but the schema would become long and hard to extend. An input object groups that data into a single unit:

~~~graphql
input CreateOrderInput {
  customerId: ID!
  shippingAddress: AddressInput!
  items: [OrderLineInput!]!
  shippingMethod: ShippingMethod!
}

input AddressInput {
  street: String!
  city: String!
  postalCode: String
}

input OrderLineInput {
  productId: ID!
  quantity: Int!
}

enum ShippingMethod {
  STANDARD
  EXPRESS
}

type Mutation {
  createOrder(input: CreateOrderInput!): Order!
}
~~~

The client passes data in a single variable:

~~~graphql
mutation CreateOrder($input: CreateOrderInput!) {
  createOrder(input: $input) {
    id
    status
  }
}
~~~

Variables:

~~~json
{
  "input": {
    "customerId": "customer-42",
    "shippingAddress": {
      "street": "12 Nguyen Hue",
      "city": "Ho Chi Minh City",
      "postalCode": "700000"
    },
    "items": [
      {
        "productId": "book-01",
        "quantity": 2
      },
      {
        "productId": "book-02",
        "quantity": 1
      }
    ],
    "shippingMethod": "EXPRESS"
  }
}
~~~

Input objects make the input contract clear, strongly typed, and reusable across multiple mutations when the semantics are the same.

## 2. Distinguishing input types and object types

GraphQL strictly separates types used to accept data from types used to return data.

- **Object types** describe the data the server returns to the client. Fields on object types can accept arguments and can reference interfaces or unions.
- **Input object types** describe the data structure clients are allowed to send in. Fields on input objects cannot take arguments and can only use valid input types.

Example:

~~~graphql
type Order {
  id: ID!
  status: OrderStatus!
  total: Money!
}

input CreateOrderInput {
  customerId: ID!
  shippingAddress: AddressInput!
}
~~~

You cannot use `Order` as an input argument type just because it has the needed fields. Likewise, you cannot use `CreateOrderInput` as the return type of a mutation.

Types allowed inside an input object include:

- Built-in scalars such as `String`, `Int`, `Float`, `Boolean`, `ID`.
- Declared custom scalars.
- Enums.
- Other input objects.
- Lists of valid input types.

An input object cannot contain object types, interfaces, or unions. This rule prevents clients from sending structures with complex output fields or relationships unsuitable for inputs.

## 3. Binding input objects into Java with @Argument

In Spring for GraphQL, `@Argument` marks a method parameter that receives the value from a GraphQL field argument.

SDL:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
  publishedYear: Int
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
~~~

Java DTO:

~~~java
public record CreateBookInput(
        String title,
        String authorId,
        Integer publishedYear) {
}
~~~

Controller:

~~~java
@Controller
public class BookMutationController {

    private final BookService bookService;

    public BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public Book createBook(
            @Argument("input") CreateBookInput input) {
        return bookService.create(input);
    }
}
~~~

Spring for GraphQL retrieves the `input` argument value and binds the data structure into `CreateBookInput`. The method receives the constructed Java object and can pass it directly to the service.

The name in `@Argument("input")` must match the argument on the `Mutation.createBook` field. If no explicit name is passed, Spring can infer it from the Java parameter name when parameter name metadata is preserved in bytecode. For important APIs, explicitly declaring the name avoids depending on compiler configuration.

Do not receive the entire JSON request as a raw string and parse it manually when the GraphQL schema already describes that structure. Using input types and `@Argument` takes advantage of GraphQL's type validation and Spring's binding mechanism.

## 4. How does GraphQlArgumentBinder work?

Spring for GraphQL uses `GraphQlArgumentBinder` to convert argument data already parsed by the GraphQL engine into Java objects.

The binding process can be understood through the following steps:

1. GraphQL validates the operation against the schema and coerces input values.
2. Spring retrieves the argument value corresponding to `@Argument`.
3. The binder reads the Map structure, lists, and converted scalar values.
4. The binder creates the target object using constructor binding if a suitable constructor is present.
5. For suitable mutable types, the binder can use a default constructor and bind properties via setters or fields.
6. If nested data fails to bind, binding errors are recorded and passed into error handling.

With Java records, the canonical constructor is the natural choice because records are immutable and explicitly declare their data components:

~~~java
public record AddressInput(
        String street,
        String city,
        String postalCode) {
}

public record CreateBookInput(
        String title,
        String authorId,
        Integer publishedYear) {
}
~~~

With mutable classes, you can use a default constructor and setters:

~~~java
public class CreateBookInput {

    private String title;
    private String authorId;
    private Integer publishedYear;

    public CreateBookInput() {
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getAuthorId() {
        return authorId;
    }

    public void setAuthorId(String authorId) {
        this.authorId = authorId;
    }

    public Integer getPublishedYear() {
        return publishedYear;
    }

    public void setPublishedYear(Integer publishedYear) {
        this.publishedYear = publishedYear;
    }
}
~~~

For classes with multi-parameter constructors, parameter names must be discoverable by Spring so input fields are matched accurately. You can use records, compiler configurations that retain parameter names, or appropriate constructor metadata. Never assume JSON field order will be used for positional assignment.

## 5. Binding nested input objects

An input object can contain other input objects. The Java structure should accurately mirror the shape of the SDL.

SDL:

~~~graphql
input AddressInput {
  street: String!
  city: String!
  postalCode: String
}

input CreateCustomerInput {
  fullName: String!
  email: String!
  address: AddressInput!
}

type Mutation {
  createCustomer(input: CreateCustomerInput!): Customer!
}
~~~

Java records:

~~~java
public record AddressInput(
        String street,
        String city,
        String postalCode) {
}

public record CreateCustomerInput(
        String fullName,
        String email,
        AddressInput address) {
}
~~~

Controller:

~~~java
@MutationMapping
public Customer createCustomer(
        @Argument("input") CreateCustomerInput input) {
    return customerService.create(input);
}
~~~

When the client sends an input containing an `address` object, the binder constructs an `AddressInput` and attaches it to `CreateCustomerInput`.

Nested structures can go multiple levels deep, but they should remain aligned with the domain. Overly deep inputs or inputs with many optional branches can make requests difficult for clients to construct and validation rules hard to reason about.

If a nested object is used across multiple mutations with the exact same meaning, you can reuse the input type. Only reuse types when the contract and semantics are truly identical; do not merge inputs with different purposes just to reduce the number of types.

## 6. Binding lists and enums

Input objects commonly contain lists of elements and enums. Java DTOs should specify concrete generic types so the binder knows what element type to instantiate.

SDL:

~~~graphql
enum ShippingMethod {
  STANDARD
  EXPRESS
}

input OrderLineInput {
  productId: ID!
  quantity: Int!
}

input CreateOrderInput {
  shippingMethod: ShippingMethod!
  items: [OrderLineInput!]!
}
~~~

Java:

~~~java
public enum ShippingMethod {
    STANDARD,
    EXPRESS
}

public record OrderLineInput(
        String productId,
        Integer quantity) {
}

public record CreateOrderInput(
        ShippingMethod shippingMethod,
        List<OrderLineInput> items) {
}
~~~

For enums, value names in the SDL must match Java enum constant names or have an appropriate mapping configured. For lists, `List<OrderLineInput>` lets the binder instantiate each element as a DTO instead of leaving untyped Maps.

Do not declare raw types such as `List items` when elements need to be bound into objects. Using concrete generic types makes code easier to read, easier to verify, and avoids manual casting.

## 7. Scalar coercion occurs before Java binding

The GraphQL engine is responsible for parsing and coercing values according to the scalar types in the schema. Only afterward does the Spring binder map those coerced values into Java parameters.

Example:

~~~graphql
input CreateBookInput {
  title: String!
  publishedYear: Int
  authorId: ID!
}
~~~

DTO:

~~~java
public record CreateBookInput(
        String title,
        Integer publishedYear,
        String authorId) {
}
~~~

In this example:

- `String` is bound to Java `String`.
- `Int` is bound to `Integer`.
- `ID` is typically received as Java `String`.

If using custom scalars like `Date` or `DateTime`, scalar coercing must be registered in runtime wiring. Once the GraphQL engine converts the value to `LocalDate` or `OffsetDateTime`, the binder can assign that value to a DTO with the matching type.

Do not expect the binder to guess arbitrary custom string formats. Let the scalar define how data is parsed and serialized according to the schema contract.

## 8. Required, nullable, and default values

The `!` marker in the SDL determines whether a value is allowed to be null. The Java DTO should pick corresponding types.

| SDL | Meaning | Common Java type |
|---|---|---|
| `String!` | Required, non-null | `String` with appropriate validation/business checks |
| `String` | Nullable | `String` |
| `Int!` | Required, non-null | `Integer` or `int` |
| `Int` | Nullable | `Integer` |
| `[Item!]!` | Required list, non-null elements | `List<ItemInput>` |
| `[Item]` | Both list and elements nullable | Java structure must handle nulls at both levels |

For nullable fields, use wrapper/reference types to represent null. Avoid primitives for values that may be omitted because primitives cannot accept null.

### Default values in SDL

You can declare a default value for an argument or input field:

~~~graphql
input SearchOptions {
  includeArchived: Boolean = false
  pageSize: Int = 20
}

type Query {
  searchBooks(options: SearchOptions): [Book!]!
}
~~~

When a client omits a field that has a default value, GraphQL applies the default according to input coercion rules. When Java receives the argument, understand that the default value has already been applied at the GraphQL layer; avoid duplicating a different default inside the DTO unintentionally.

A default value only applies when omission is allowed. A non-null field without a default must be provided by the client or supplied via variables/arguments per GraphQL rules.

## 9. Distinguishing omitted and explicit null with ArgumentValue

In inputs, there are two distinct states:

- **Omitted:** the client did not send the field.
- **Explicit null:** the client sent the field with a null value.

For partial-update mutations, these two states can have different meanings. For example, omitting `subtitle` means keeping it unchanged; sending `subtitle: null` means clearing the current value.

SDL:

~~~graphql
type Mutation {
  updateBookSubtitle(
    id: ID!
    subtitle: String
  ): Book!
}
~~~

The controller can use `ArgumentValue<T>`:

~~~java
@MutationMapping
public Book updateBookSubtitle(
        @Argument String id,
        @Argument ArgumentValue<String> subtitle) {

    if (subtitle.isOmitted()) {
        return bookService.findById(id);
    }

    return bookService.updateSubtitle(id, subtitle.value());
}
~~~

`ArgumentValue` allows checking whether the argument was passed. When the argument is explicitly passed as null, `isOmitted()` is false and `value()` is null. When the argument is absent, `isOmitted()` is true.

Two requests with different meanings:

~~~graphql
mutation {
  updateBookSubtitle(id: "b-01") {
    id
  }
}
~~~

~~~graphql
mutation {
  updateBookSubtitle(id: "b-01", subtitle: null) {
    id
  }
}
~~~

This approach is useful for PATCH-style mutations. With complex input objects, design an appropriate strategy to represent omitted/null states and test each field; do not automatically treat every missing nullable field as a request to delete data.

## 10. Validation for input DTOs

GraphQL validation checks types and structure against the SDL, but it does not replace business validation. For instance, `quantity: Int!` ensures a non-null integer is present, but does not automatically guarantee quantity is greater than 0.

You can use Jakarta Bean Validation on DTOs:

~~~java
public record OrderLineInput(
        @NotBlank String productId,
        @NotNull @Positive Integer quantity) {
}

public record AddressInput(
        @NotBlank String street,
        @NotBlank String city,
        String postalCode) {
}

public record CreateOrderInput(
        @NotBlank String customerId,
        @NotNull @Valid AddressInput shippingAddress,
        @NotEmpty List<@NotNull @Valid OrderLineInput> items,
        @NotNull ShippingMethod shippingMethod) {
}
~~~

The controller marks the input for validation:

~~~java
@MutationMapping
public Order createOrder(
        @Argument("input") @Valid CreateOrderInput input) {
    return orderService.create(input);
}
~~~

When the application has an appropriate Bean Validation implementation, Spring for GraphQL can apply validation to annotated method arguments. Nested constraints require `@Valid` to trigger cascading validation.

Commonly used annotations:

| Annotation | Meaning |
|---|---|
| `@NotNull` | Null is not allowed |
| `@NotBlank` | Non-null string with at least one non-whitespace character |
| `@Positive` | Number must be greater than 0 |
| `@Size` | Restricts length or collection size |
| `@Email` | Basic email format validation |
| `@Valid` | Enables cascading validation for nested objects |

The SDL should describe structural constraints such as requiredness and scalar types. Bean Validation adds data constraints. The service still needs to check domain rules involving current state, user permissions, or database records.

## 11. Distinguishing GraphQL validation, binding errors, and business errors

A request can fail at different stages.

| Stage | Example | Where handled |
|---|---|---|
| GraphQL parse/validation | Syntax error, non-existent field, missing non-null argument | GraphQL engine before invoking resolver |
| Scalar coercion | Passing a string that cannot parse into Int or Date | GraphQL Java scalar coercing |
| Argument binding | Unable to construct DTO or bind nested property | `GraphQlArgumentBinder` and error handling mechanism |
| Bean Validation | Quantity is 0, invalid email | Jakarta Bean Validation |
| Business validation | Product discontinued, user lacks permission to place order | Service/domain layer |

For example, the client sends `quantity: "many"` when the SDL declares `Int!`. GraphQL can reject it at the coercion step before the controller runs.

If the client sends a valid integer `0`, GraphQL accepts the data type. Bean Validation with `@Positive` catches that quantity is invalid according to business rules.

If quantity is 2 but the product is out of stock, only the service/domain layer has the information needed to reject the operation.

Do not collapse every error into a single generic message. Distinguish structural errors, data errors, and business errors so clients can fix requests or display appropriate feedback. Public error messages should never contain SQL, stack traces, or sensitive details.

## 12. Using Map when dynamic input is needed

In some scenarios, input structure may vary by configuration or require dynamic handling. In those cases, you can accept the argument as a Map:

~~~java
@MutationMapping
public Result executeDynamic(
        @Argument("payload") Map<String, Object> payload) {
    return dynamicService.execute(payload);
}
~~~

The SDL still needs to declare a valid input object:

~~~graphql
input DynamicPayload {
  action: String!
  attributes: [AttributeInput!]
}

input AttributeInput {
  name: String!
  value: String
}

type Mutation {
  executeDynamic(payload: DynamicPayload!): Result!
}
~~~

A Map gives dynamic key access at the cost of reduced type safety. Code must manually verify keys, value types, nested structures, and business rules. Do not use a Map for every input just to reduce the number of DTOs.

If the schema is stable, a concrete record or DTO is usually easier to maintain, with better IDE support and validation.

## 13. Do not bind inputs directly into JPA entities

Do not use persistence entities as public input DTOs simply because the fields look similar.

For instance, an Order entity might contain:

- Server-generated `id`.
- `status` managed by business workflows.
- `createdAt` and `updatedAt`.
- `customer` or internal relationships.
- Audit or ownership fields.

If client inputs are bound directly onto the entity, there is a risk clients could pass fields they are not authorized to modify. This is a mass assignment vulnerability.

Create an input DTO containing only the fields clients are allowed to submit:

~~~java
public record CreateOrderInput(
        String customerId,
        AddressInput shippingAddress,
        List<OrderLineInput> items,
        ShippingMethod shippingMethod) {
}
~~~

The service checks permissions, loads related data, and constructs the entity according to business rules:

~~~java
public Order create(CreateOrderInput input, UserPrincipal principal) {
    // Check permission to place an order on behalf of customer.
    // Load products and check inventory.
    // Calculate total amount on the server.
    // Create Order with server-managed status and audit fields.
}
~~~

Clients should never decide final prices, order statuses, or audit information when those values are server-controlled.

## 14. Testing input binding with GraphQlTester

Integration tests should send GraphQL operations with variables to test coercion, binding, and the resolver together.

Example:

~~~java
@Test
void shouldBindNestedCreateBookInput() {
    graphQlTester.document("""
            mutation CreateBook($input: CreateBookInput!) {
                createBook(input: $input) {
                    id
                    title
                    author {
                        id
                    }
                }
            }
            """)
            .variable("input", Map.of(
                    "title", "GraphQL in Practice",
                    "authorId", "author-01",
                    "publishedYear", 2026))
            .execute()
            .path("createBook.title")
            .entity(String.class)
            .isEqualTo("GraphQL in Practice");
}
~~~

For nested inputs, you can pass nested Maps in the test to accurately represent the JSON structure sent by the client.

You should write tests for these cases:

1. Valid input object bound into a record/DTO.
2. Nested input objects bound properly.
3. Lists and enums converted properly.
4. Missing required field rejected by GraphQL.
5. Wrong scalar type rejected by coercion.
6. Nullable field accepting explicit null.
7. Omitted argument distinguished via `ArgumentValue`.
8. Bean Validation rejecting invalid data.
9. Binding errors returned in the expected GraphQL errors format.
10. Service rejecting business violations such as out-of-stock or insufficient permissions.

Example testing an invalid request:

~~~java
@Test
void shouldRejectInvalidQuantity() {
    graphQlTester.document("""
            mutation {
                createOrder(input: {
                    customerId: "customer-42"
                    shippingAddress: {
                        street: "12 Nguyen Hue"
                        city: "Ho Chi Minh City"
                    }
                    items: [{
                        productId: "book-01"
                        quantity: 0
                    }]
                    shippingMethod: EXPRESS
                }) {
                    id
                }
            }
            """)
            .execute()
            .errors()
            .satisfy(errors -> assertThat(errors).isNotEmpty());
}
~~~

The test above assumes the DTO has `@Positive` and validation is enabled. In real tests, also check the error codes or error classification published by your application rather than only asserting that the errors list is non-empty.

## 15. Input object design principles

When designing GraphQL inputs and Java DTOs, keep the following in mind:

- Create dedicated input types for data submitted by clients.
- Never use object types, interfaces, or unions in input positions.
- Use records or DTOs with clear structures for binding.
- Use `@Argument("input")` with explicit argument names.
- Keep Java types aligned with SDL scalars, enums, lists, and nullability.
- Use concrete generic types for nested collections.
- Use `ArgumentValue<T>` when you need to distinguish omitted from explicit null.
- Use Bean Validation for data constraints and the service for domain rules.
- Never bind directly into JPA entities that contain sensitive or server-managed fields.
- Test valid inputs, missing fields, wrong types, nulls, binding errors, and business errors.

A good input object accurately reflects the data clients are allowed to provide. It should not be a copy of an entire entity or an overly broad structure that makes modification permissions hard to enforce.

## Conclusion

Input object binding is the process of converting input data already type-checked by GraphQL into Java objects that controllers and services can use. In Spring for GraphQL, `@Argument` combined with `GraphQlArgumentBinder` supports binding scalars, enums, lists, DTOs, and nested input structures.

Using Java records or DTOs keeps structures clear and type-safe. Combining SDL nullability, `ArgumentValue`, Bean Validation, and domain checks properly handles missing data, explicit nulls, malformed values, and business rule violations. When testing with `GraphQlTester`, cover the entire path from variables to Java objects and mutation results.

## References

- [Spring for GraphQL — Annotated Controllers and Argument Binding](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — GraphQlArgumentBinder API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/data/GraphQlArgumentBinder.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [GraphQL Specification — Input Objects](https://spec.graphql.org/October2021/#sec-Input-Objects)
- [Jakarta Bean Validation](https://jakarta.ee/specifications/bean-validation/)
