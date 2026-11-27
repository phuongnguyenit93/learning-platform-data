# Binding nested inputs

## Objectives

After this lesson, you will be able to:

- Declare multi-level input objects in GraphQL SDL.
- Distinguish input objects from object types used for output.
- Send nested inputs using variables or input literals.
- Bind nested input objects into Java records or POJOs using `@Argument`.
- Understand the role of `GraphQlArgumentBinder` in recursively binding objects and collections.
- Choose between constructor binding and property binding appropriately.
- Handle nullability, default values, and omitted/null states.
- Apply Bean Validation to nested objects and list elements.
- Test binding and categorize input errors.

## 1. What are nested inputs?

A GraphQL mutation or query can accept an input object as an argument. That input object can contain another input object or a list of input objects. This structure is called a nested input.

For example, when creating an order, the client needs to send customer details, a shipping address, and order line items:

~~~graphql
input ContactInput {
    email: String!
    phone: String
}

input CustomerInput {
    customerId: ID!
    contact: ContactInput!
}

input AddressInput {
    recipient: String!
    street: String!
    city: String!
    postalCode: String!
}

input OrderLineInput {
    productId: ID!
    quantity: Int!
}

input CreateOrderInput {
    customer: CustomerInput!
    shippingAddress: AddressInput!
    lines: [OrderLineInput!]!
    note: String
}

type Mutation {
    createOrder(input: CreateOrderInput!): Order!
}
~~~

`CreateOrderInput` contains nested structures:

- `customer` is a `CustomerInput`.
- `CustomerInput.contact` is a `ContactInput`.
- `shippingAddress` is an `AddressInput`.
- `lines` is a list of `OrderLineInput`.

This organization groups the data for a single operation into one clearly named argument. Client and server share a structured contract instead of passing many separate arguments.

## 2. How do input objects differ from object types?

GraphQL separates types used to return data from types used to accept data.

`type` declares an object type for output:

~~~graphql
type Order {
    id: ID!
    status: String!
    total: Float!
}
~~~

`input` declares an input object for arguments:

~~~graphql
input CreateOrderInput {
    customer: CustomerInput!
    shippingAddress: AddressInput!
    lines: [OrderLineInput!]!
}
~~~

You cannot directly use an object type as a field type inside an input object. The following example is invalid:

~~~graphql
type Address {
    street: String!
    city: String!
}

input CreateOrderInput {
    shippingAddress: Address
}
~~~

`Address` is an object type meant for output, not an input type. You must define a dedicated input type:

~~~graphql
input AddressInput {
    street: String!
    city: String!
}

input CreateOrderInput {
    shippingAddress: AddressInput!
}
~~~

Output types may contain read-only fields, computed fields, or relationships that clients are not allowed to submit. Input types should contain only the data clients are permitted to supply for that operation. Do not reuse output types as inputs merely to reduce the number of SDL definitions.

## 3. Sending nested inputs with variables

GraphQL variables are passed as JSON. Nested JSON objects correspond to the input objects in the SDL.

Operation:

~~~graphql
mutation CreateOrder($input: CreateOrderInput!) {
    createOrder(input: $input) {
        id
        status
        total
    }
}
~~~

Variables:

~~~json
{
    "input": {
        "customer": {
            "customerId": "customer-42",
            "contact": {
                "email": "an@example.com",
                "phone": "0900000000"
            }
        },
        "shippingAddress": {
            "recipient": "An Nguyen",
            "street": "12 Nguyen Hue",
            "city": "Ho Chi Minh City",
            "postalCode": "700000"
        },
        "lines": [
            {
                "productId": "product-10",
                "quantity": 2
            },
            {
                "productId": "product-25",
                "quantity": 1
            }
        ],
        "note": "Deliver during business hours"
    }
}
~~~

The GraphQL runtime validates the variables structure against the SDL before calling the resolver. Field names, scalar types, input objects, and non-null rules must all match the schema.

If `shippingAddress` is missing or `null` when the SDL declares `AddressInput!`, the input is invalid and the resolver is not invoked.

## 4. Sending nested input literals

Besides variables, GraphQL allows writing input objects directly inline in the operation:

~~~graphql
mutation {
    createOrder(
        input: {
            customer: {
                customerId: "customer-42"
                contact: {
                    email: "an@example.com"
                    phone: "0900000000"
                }
            }
            shippingAddress: {
                recipient: "An Nguyen"
                street: "12 Nguyen Hue"
                city: "Ho Chi Minh City"
                postalCode: "700000"
            }
            lines: [
                { productId: "product-10", quantity: 2 }
                { productId: "product-25", quantity: 1 }
            ]
            note: "Deliver during business hours"
        }
    ) {
        id
        status
    }
}
~~~

Literals and variables follow the exact same SDL structure. In real-world applications, variables are usually more convenient because clients can build JSON dynamically, reuse operations, and avoid string concatenation.

Either way, the server receives data that has already passed GraphQL input coercion. Resolvers do not need to manually parse GraphQL strings or read the JSON request body.

## 5. Binding nested inputs into Java records

Spring for GraphQL uses argument binding to convert GraphQL data into the Java types declared by controller methods. `GraphQlArgumentBinder` supports recursive binding of input objects, including nested objects and collections.

Java records are a good fit when input DTOs primarily hold data and do not need to be mutated after creation:

~~~java
public record ContactInput(
        String email,
        String phone) {
}

public record CustomerInput(
        String customerId,
        ContactInput contact) {
}

public record AddressInput(
        String recipient,
        String street,
        String city,
        String postalCode) {
}

public record OrderLineInput(
        String productId,
        Integer quantity) {
}

public record CreateOrderInput(
        CustomerInput customer,
        AddressInput shippingAddress,
        List<OrderLineInput> lines,
        String note) {
}
~~~

Record components match the fields in the SDL:

| GraphQL input field | Java record component |
| --- | --- |
| `CreateOrderInput.customer` | `CustomerInput customer` |
| `CustomerInput.contact` | `ContactInput contact` |
| `CreateOrderInput.shippingAddress` | `AddressInput shippingAddress` |
| `CreateOrderInput.lines` | `List<OrderLineInput> lines` |
| `OrderLineInput.quantity` | `Integer quantity` |

When binding `CreateOrderInput`, the framework recursively constructs `CustomerInput`, `ContactInput`, `AddressInput`, and each `OrderLineInput` element. Field names in the SDL must match component names or the binding rules used by the DTO.

## 6. Receiving nested inputs with @Argument

The controller method only needs to declare the argument at the GraphQL field level. Spring binds the entire nested object structure into the DTO:

~~~java
@Controller
class OrderMutationController {

    private final OrderService orderService;

    OrderMutationController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MutationMapping
    public Order createOrder(
            @Argument("input") CreateOrderInput input) {

        return orderService.create(input);
    }
}
~~~

`@Argument("input")` targets the `input` argument of the `Mutation.createOrder` field. There is no need to repeat the annotation for child fields like `customer`, `contact`, or `shippingAddress`. Child fields are bound according to the structure of `CreateOrderInput`.

Distinguish between these two schemas:

~~~graphql
type Mutation {
    createOrder(input: CreateOrderInput!): Order!
}
~~~

and:

~~~graphql
type Mutation {
    createOrder(
        customer: CustomerInput!
        shippingAddress: AddressInput!
        lines: [OrderLineInput!]!
    ): Order!
}
~~~

The first structure receives a single nested input object. The second receives multiple independent arguments. The Java signature must match the actual SDL. Do not use `@Argument("customer")` to retrieve a child field if the schema only declares a single `input` argument.

## 7. Constructor binding and property binding

The Spring argument binder can instantiate objects using either constructor binding or property binding.

**Constructor binding** creates an object via a constructor whose parameters correspond to the input fields. Java records work naturally with this approach because records have a canonical constructor containing all record components.

~~~java
public record AddressInput(
        String recipient,
        String street,
        String city,
        String postalCode) {
}
~~~

**Property binding** instantiates the object and then assigns values to properties with matching setters or fields.

~~~java
public class AddressInput {

    private String recipient;
    private String street;
    private String city;
    private String postalCode;

    public AddressInput() {
    }

    public String getRecipient() {
        return recipient;
    }

    public void setRecipient(String recipient) {
        this.recipient = recipient;
    }

    public String getStreet() {
        return street;
    }

    public void setStreet(String street) {
        this.street = street;
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public String getPostalCode() {
        return postalCode;
    }

    public void setPostalCode(String postalCode) {
        this.postalCode = postalCode;
    }
}
~~~

Both records and POJOs can serve as nested input DTOs as long as their structure and data types are compatible. For regular Java classes using multi-parameter constructors, ensure constructor parameter names can be read properly by Spring, such as preserving parameter names at compilation or using suitable constructor metadata. Never assume JSON field order will be used for positional binding.

Records suit immutable inputs; mutable POJOs suit cases requiring setters or specialized binding workflows. Choose a consistent style within the same DTO.

## 8. Binding lists of nested inputs

An input object can contain lists of input objects. In the order example, `lines` is a list of `OrderLineInput`.

SDL:

~~~graphql
input OrderLineInput {
    productId: ID!
    quantity: Int!
}

input CreateOrderInput {
    lines: [OrderLineInput!]!
}
~~~

Java:

~~~java
public record OrderLineInput(
        String productId,
        Integer quantity) {
}
~~~

In `CreateOrderInput` from the previous example, the `lines` component has type `List<OrderLineInput>`. Spring binds each element in the list into an `OrderLineInput`. The resolver receives `List<OrderLineInput>` instead of a list of Maps requiring manual conversion.

If the SDL declares `[OrderLineInput!]!`, neither the list nor any element may be null. However, non-null does not mean the list must have at least one element. Requiring at least one element needs separate validation, such as `@NotEmpty`.

## 9. Scalar types and conversion in nested inputs

Scalar fields in nested inputs are coerced by GraphQL first, and then bound by Spring to the corresponding Java types.

~~~graphql
input ProductFilterInput {
    keyword: String
    minPrice: Float
    maxPrice: Float
    active: Boolean
    categoryIds: [ID!]!
}
~~~

~~~java
public record ProductFilterInput(
        String keyword,
        Double minPrice,
        Double maxPrice,
        Boolean active,
        List<String> categoryIds) {
}
~~~

Some key points:

- `String` typically binds to `String`.
- `Int` fits `Integer` or a compatible integer type.
- `Float` can bind to an appropriate floating-point type such as `Double`.
- `Boolean` binds to `Boolean`.
- `ID` is typically represented in Java as `String`.
- Custom scalars require a coercing implementation and conversion compatible with the target Java type.

If using custom scalars such as `UUID`, register the scalar in runtime wiring and verify the Java type returned by the scalar. Do not assume that every scalar with a string JSON representation automatically binds to any Java type.

For nullable fields, use wrappers such as `Integer`, `Double`, and `Boolean` instead of primitives if you need to represent null. Java primitives cannot hold null and can obscure the meaning of an optional field.

## 10. Nullability, omitted, and default values

GraphQL distinguishes required fields from optional fields using `!`.

~~~graphql
input AddressInput {
    street: String!
    city: String!
    apartment: String
}

input CreateOrderInput {
    shippingAddress: AddressInput!
    note: String
}
~~~

- `shippingAddress: AddressInput!` requires a non-null input object.
- `street: String!` and `city: String!` are required fields inside the object.
- `apartment: String` may be null or omitted.
- `note: String` may be null or omitted.

GraphQL validates non-null constraints before the resolver runs. If a required field is missing or null is passed to a non-null field, the input is invalid.

For nullable fields, two states can carry different meanings: the client did not send the field, or the client sent the field with `null`. When bound to a regular nullable Java property, both become `null`. If business logic needs to distinguish them—such as in a partial update—use a representation for omitted/null supported by Spring GraphQL, such as `ArgumentValue<T>`, at the appropriate binding position.

Example with an optional field-level argument:

~~~graphql
type Mutation {
    renameBook(id: ID!, title: String): Book!
}
~~~

~~~java
@MutationMapping
public Book renameBook(
        @Argument("id") String id,
        @Argument("title") ArgumentValue<String> title) {

    if (title.isOmitted()) {
        return bookService.keepTitle(id);
    }

    if (title.value() == null) {
        return bookService.clearTitle(id);
    }

    return bookService.rename(id, title.value());
}
~~~

For nested patch inputs, design DTOs and wrappers to preserve omitted/null states according to the binding capabilities of the Spring GraphQL version you use. Do not use a plain nullable Java property if business logic needs to distinguish "leave unchanged" from "clear value".

GraphQL also supports default values on input fields:

~~~graphql
input SearchOptionsInput {
    page: Int = 0
    size: Int = 20
    includeArchived: Boolean = false
}

input SearchBooksInput {
    keyword: String!
    options: SearchOptionsInput!
}
~~~

If the client omits `page`, `size`, or `includeArchived`, GraphQL applies the default values during schema input coercion. The DTO receives the coerced values per the schema. Avoid setting different defaults in the SDL, DTO, and service, as that makes results depend on the call path.

## 11. Validation for nested inputs

GraphQL validates structure and data types against the SDL, but does not replace business validation. For example, `quantity: Int!` ensures quantity is a non-null integer, but does not guarantee quantity is greater than 0.

Spring for GraphQL can integrate Bean Validation when the application has a validation provider and the method argument is annotated with `@Valid` or `@Validated`.

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

public record ContactInput(
        @NotBlank @Email String email,
        String phone) {
}

public record CustomerInput(
        @NotBlank String customerId,
        @NotNull @Valid ContactInput contact) {
}

public record AddressInput(
        @NotBlank String recipient,
        @NotBlank String street,
        @NotBlank String city,
        @NotBlank String postalCode) {
}

public record OrderLineInput(
        @NotBlank String productId,
        @Min(1) int quantity) {
}

public record CreateOrderInput(
        @NotNull @Valid CustomerInput customer,
        @NotNull @Valid AddressInput shippingAddress,
        @NotEmpty List<@NotNull @Valid OrderLineInput> lines,
        String note) {
}
~~~

Controller:

~~~java
import jakarta.validation.Valid;

@MutationMapping
public Order createOrder(
        @Argument("input") @Valid CreateOrderInput input) {

    return orderService.create(input);
}
~~~

`@Valid` on the method argument triggers validation for the input object. `@Valid` annotations on nested properties tell validation to descend into child objects. For lists, `@Valid` on the type argument enables validating each element.

A Bean Validation provider is required, typically added via `spring-boot-starter-validation` in Spring Boot applications. With Spring Boot 3, annotations reside in the `jakarta.validation` package.

### 11.1. Schema validation and Bean Validation

| Check | GraphQL SDL | Bean Validation |
| --- | --- | --- |
| Required field | `String!` | `@NotNull` |
| Non-empty string | No standard equivalent rule | `@NotBlank` |
| Integer | `Int` | Java `Integer` type |
| Minimum quantity | Does not validate business values | `@Min(1)` |
| Valid email format | Not checked automatically | `@Email` |
| Nested object | Input object and field types | `@Valid` to cascade |
| List with at least one element | Not enforced by `[T!]!` alone | `@NotEmpty` |

GraphQL validation protects the data type contract. Bean Validation adds content constraints. Rules that depend on the database or system state—such as product availability or whether a customer is permitted to order—must still be checked in the service/domain layer.

## 12. Handling binding and validation errors

Errors can occur at multiple stages:

1. **GraphQL input coercion:** wrong scalar type, missing non-null field, or invalid input object.
2. **Spring argument binding:** GraphQL data cannot be converted into the target Java structure.
3. **Bean Validation:** object binds successfully but violates constraints.
4. **Business validation:** structurally valid data fails to satisfy business rules.

| Input data | Detection layer |
| --- | --- |
| `quantity` passed as string `"many"` instead of integer | GraphQL coercion |
| DTO requires unbindable constructor/property | Argument binding |
| Malformed `email` | Bean Validation |
| `quantity` is `0` when minimum `1` is required | Bean Validation or business validation |
| Product does not exist | Service/repository |
| Product is out of stock | Business validation |

Spring GraphQL translates binding or validation errors into GraphQL errors via the framework's error handling mechanism. Applications can customize error representation using `DataFetcherExceptionResolver` or `@GraphQlExceptionHandler`.

Do not return stack traces, database table names, or internal details in error messages. Return client-friendly validation messages and log technical details in controlled server logs. Never turn invalid inputs into empty objects or silently ignore malformed fields.

## 13. Do not bind inputs directly into persistence entities

An approach that might look quick is accepting a database entity directly as input:

~~~java
@MutationMapping
public Order createOrder(@Argument("input") OrderEntity input) {
    return repository.save(input);
}
~~~

This can allow clients to submit properties they should not control, such as:

- Server-generated `id`.
- `status` modifiable only by the backend.
- `createdAt`, `updatedAt`.
- `tenantId` or `ownerId`.
- Internal relationships or administrative flags.

Use a dedicated input DTO:

~~~java
public record CreateOrderInput(
        CustomerInput customer,
        AddressInput shippingAddress,
        List<OrderLineInput> lines,
        String note) {
}
~~~

Then have the service map the input into a domain/entity object according to server policy:

~~~java
@Service
class OrderService {

    public Order create(CreateOrderInput input) {
        OrderEntity entity = new OrderEntity();

        entity.setCustomerId(input.customer().customerId());
        entity.setShippingAddress(mapAddress(input.shippingAddress()));
        entity.setLines(mapLines(input.lines()));
        entity.setNote(input.note());

        // ID, tenant, owner, status, and timestamps
        // are determined by server-side rules.
        return repository.save(entity);
    }
}
~~~

Input DTOs create a clear boundary between data clients are allowed to send and internal system state. Do not trust client-submitted data for owner or tenant values when those must be derived from the security context.

## 14. Testing nested input binding

Test through GraphQL operations to verify that the SDL, argument binder, and controller work together.

Example with `GraphQlTester`:

~~~java
graphQlTester.document("""
        mutation CreateOrder($input: CreateOrderInput!) {
            createOrder(input: $input) {
                id
                status
            }
        }
        """)
        .variable("input", Map.of(
                "customer", Map.of(
                        "customerId", "customer-42",
                        "contact", Map.of(
                                "email", "an@example.com",
                                "phone", "0900000000"
                        )
                ),
                "shippingAddress", Map.of(
                        "recipient", "An Nguyen",
                        "street", "12 Nguyen Hue",
                        "city", "Ho Chi Minh City",
                        "postalCode", "700000"
                ),
                "lines", List.of(
                        Map.of("productId", "product-10", "quantity", 2),
                        Map.of("productId", "product-25", "quantity", 1)
                ),
                "note", "Deliver during business hours"
        ))
        .execute()
        .path("createOrder.status")
        .entity(String.class)
        .isEqualTo("CREATED");
~~~

This test verifies that nested variables bind into the DTO and the mutation returns the expected result.

Cases to include:

- Nested object with all valid fields.
- Nested object missing a non-null field.
- Omitted nullable field.
- Nullable field passed as `null`.
- List of nested objects with multiple elements.
- A list element with the wrong type or missing a required field.
- Bean Validation failure at a child object level.
- Bean Validation failure on a list element.
- Custom scalar inside a nested input coerced properly.
- Invalid input prevented from causing the service to write data.

DTO unit tests cannot verify SDL field names, GraphQL coercion, or Spring's nested object binding. An integration test via `GraphQlTester` should be the primary verification layer for the path from GraphQL variables to Java arguments.

## 15. Common pitfalls

| Symptom | Cause | Fix |
| --- | --- | --- |
| `@Argument` receives null | Argument name does not match SDL or client did not send input | Check argument names and variables |
| Nested child object receives null | SDL field name does not match property/constructor component | Compare field names at each level |
| Unable to bind Java record | Constructor components or Java types are incompatible | Check component names and data types |
| POJO has null property despite client sending value | Missing suitable setter/constructor or property binding failed | Use a record or add setters/constructors |
| List binds wrong element types | Generic element type incompatible with input object | Use `List<SpecificInput>` and check SDL |
| Using output `type` in input | GraphQL forbids object types as input fields | Declare a separate `input` type |
| Required field omitted | Violates non-null in SDL | Check `!` markers and payload |
| Cannot distinguish omitted from null | DTO uses regular nullable properties | Use `ArgumentValue` when distinction is needed |
| Nested object validation does not run | Missing `@Valid` on argument or child property | Add cascading validation |
| Empty list still passes schema | `[T!]!` does not require elements | Use `@NotEmpty` or business validation |
| Client can supply unwanted owner/tenant | Input DTO exposes internal fields | Separate input DTO and determine trusted values on the server |

## 16. Nested input design workflow

When designing a mutation that receives multi-level data, follow this sequence:

1. **Identify data clients are allowed to submit.** Separate public fields from internal state.
2. **Design input objects.** Split into small input types grouped by meaningful data domains.
3. **Declare nullability.** Use `!` for required fields and define default values where applicable.
4. **Choose Java structures.** Use records for immutable DTOs or POJOs when property binding is needed.
5. **Keep names consistent.** Match SDL field names with Java components, constructors, or properties.
6. **Bind at the argument level.** Use `@Argument` for the field-level input object; the binder handles nested levels.
7. **Add validation.** Use `@Valid` and constraints for structural rules, then enforce business rules in the service.
8. **Handle omitted and null.** Choose appropriate DTOs/wrappers if update operations need to distinguish both states.
9. **Map inputs to the domain.** Never let clients directly control internal entity fields.
10. **Test via GraphQL operations.** Cover nested objects, lists, binding errors, and validation.

## 17. Summary

Nested inputs allow a single GraphQL argument to contain multi-level input objects and lists of input objects. The SDL uses `input` to define the data structure clients may send; object types using `type` are for output and cannot substitute for input types.

In Spring for GraphQL, `@Argument` receives the field-level input object, while `GraphQlArgumentBinder` recursively binds nested objects and collections into Java records or POJOs. Field names and data types must align at every level. GraphQL coercion checks structure and nullability; Bean Validation checks constraints like email, quantity, and nested objects; the service continues enforcing business rules. Using dedicated input DTOs, handling omitted/null explicitly, and testing with `GraphQlTester` keeps binding safe, understandable, and maintainable.
