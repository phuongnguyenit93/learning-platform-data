# Mutation Input Objects

## Objectives

After this lesson, you will be able to:

- Design input objects in GraphQL SDL for mutations.
- Explain why input types are separate from object types used in responses.
- Bind input objects to Java records or classes using `@Argument` in Spring for GraphQL.
- Handle nested inputs, lists, enums, and custom scalars.
- Combine Bean Validation with business checks in the service layer.
- Design inputs for create and update operations, including the difference between omitted fields and null values.
- Test mutations with variables and `GraphQlTester`.

## Why Should Mutations Accept Input Objects?

Mutations typically execute a use case with multiple input values. For example, creating an order requires a customer ID, product list, shipping address, and a note. Declaring all of these as individual arguments makes the schema parameter-heavy and hard to extend:

~~~graphql
type Mutation {
  createOrder(
    customerId: ID!
    productIds: [ID!]!
    quantities: [Int!]!
    recipient: String!
    street: String!
    city: String!
    note: String
  ): Order!
}
~~~

This design also risks mismatching the `productIds` and `quantities` lists by position. Instead, group related data into an input object:

~~~graphql
type Mutation {
  createOrder(input: CreateOrderInput!): Order!
}

input CreateOrderInput {
  customerId: ID!
  items: [CreateOrderItemInput!]!
  shippingAddress: ShippingAddressInput!
  note: String
}

input CreateOrderItemInput {
  productId: ID!
  quantity: Int!
}

input ShippingAddressInput {
  recipient: String!
  street: String!
  city: String!
  postalCode: String
}
~~~

Input objects create a named, reusable, and evolvable structure. Each element in `items` pairs `productId` with `quantity`, so line-item data always stays together. The shipping address is also grouped into its own object.

This is a useful design convention for mutations with multiple input fields. GraphQL does not require every mutation to have only a single `input` argument, though an input object usually keeps the schema clear and extensible.

## Input Objects Differ from Response Object Types

GraphQL distinguishes between types used to return data and input types used to receive data:

| Kind | SDL keyword | Role |
| --- | --- | --- |
| Object type | type | Describes fields clients can query in responses |
| Input object | input | Describes fields clients are allowed to pass in arguments |

For example, the `Order` object type may contain read-only or server-computed data:

~~~graphql
type Order {
  id: ID!
  status: OrderStatus!
  total: BigDecimal!
  createdAt: DateTime!
  items: [OrderItem!]!
}
~~~

The input for creating an order should only contain data the client is allowed to provide:

~~~graphql
input CreateOrderInput {
  customerId: ID!
  items: [CreateOrderItemInput!]!
  shippingAddress: ShippingAddressInput!
  note: String
}
~~~

Do not use the `Order` object type as an input type. GraphQL only allows input objects to contain scalars, enums, other input objects, and valid list/non-null modifiers. Interfaces, unions, and object types are output types and cannot be placed directly inside an input object.

Separating input and output types helps the server control incoming data. Clients cannot supply `status`, `total`, or `createdAt` when those fields are determined by business logic.

## Declaring Mutations and Input Objects in SDL

A simple schema for creating a product can be declared as follows:

~~~graphql
enum ProductCategory {
  BOOK
  ELECTRONICS
  HOME
}

input CreateProductInput {
  name: String!
  description: String
  category: ProductCategory!
  price: BigDecimal!
  tagIds: [ID!]!
}

type Product {
  id: ID!
  name: String!
  description: String
  category: ProductCategory!
  price: BigDecimal!
  tags: [Tag!]!
}

type Mutation {
  createProduct(input: CreateProductInput!): Product!
}
~~~

The `!` modifiers define required values:

- `createProduct` requires the `input` argument.
- `CreateProductInput` requires `name`, `category`, `price`, and `tagIds`.
- `description` can be omitted or given `null`.
- `tagIds` must be a non-null list and none of its elements can be null. An empty list is still valid by type; if business rules require at least one tag, add validation.

SDL checks structure and GraphQL types. It does not automatically guarantee that price is greater than 0, that tags exist, or that the user has permission to create products in the selected category.

## Sending Mutations with Variables

Clients should use variables to separate input data from the operation structure:

~~~graphql
mutation CreateProduct($input: CreateProductInput!) {
  createProduct(input: $input) {
    id
    name
    category
    price
  }
}
~~~

Variables:

~~~json
{
  "input": {
    "name": "Mechanical Keyboard",
    "description": "75% layout keyboard",
    "category": "ELECTRONICS",
    "price": 1850000.00,
    "tagIds": ["tag-01", "tag-07"]
  }
}
~~~

GraphQL validates variables against `CreateProductInput` before calling the resolver. Extra fields not declared in the input type are rejected; missing required fields or invalid types also cause the request to fail input coercion.

Variables are convenient for clients because operation documents can be reused, cached, and used to pass complex data without string-concatenating GraphQL at runtime.

## Binding Input Objects to Java Records

Spring for GraphQL provides argument binding to convert input data into Java types. With annotated controllers, use `@Argument` to receive the entire input object.

Records are a good fit for immutable DTOs:

~~~java
import java.math.BigDecimal;
import java.util.List;

public record CreateProductInput(
        String name,
        String description,
        ProductCategory category,
        BigDecimal price,
        List<String> tagIds) {
}
~~~

Corresponding Java enum:

~~~java
public enum ProductCategory {
    BOOK,
    ELECTRONICS,
    HOME
}
~~~

Controller:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

@Controller
public class ProductMutationController {

    private final ProductService productService;

    public ProductMutationController(ProductService productService) {
        this.productService = productService;
    }

    @MutationMapping
    public Product createProduct(
            @Argument("input") CreateProductInput input) {
        return productService.create(input);
    }
}
~~~

Record component names must correspond to field names in the SDL. Java types must also be compatible with the scalar or enum converted by the GraphQL runtime. For example, `BigDecimal` matches a registered `BigDecimal` scalar; if using another custom scalar, check which Java type that scalar produces.

Do not use primitive types for nullable input properties. Use `Integer`, `Boolean`, or `BigDecimal` instead of `int` or `boolean` for fields that can receive null. Reference types allow the DTO to represent missing values.

## Binding Nested Input Objects and Lists

Input objects can contain other input objects. For example, an order has a shipping address and multiple line items:

~~~java
public record ShippingAddressInput(
        String recipient,
        String street,
        String city,
        String postalCode) {
}

public record CreateOrderItemInput(
        String productId,
        Integer quantity) {
}

public record CreateOrderInput(
        String customerId,
        List<CreateOrderItemInput> items,
        ShippingAddressInput shippingAddress,
        String note) {
}
~~~

The controller receives the top-level DTO:

~~~java
@MutationMapping
public Order createOrder(
        @Argument("input") CreateOrderInput input) {
    return orderService.create(input);
}
~~~

The argument binder maps nested fields according to their matching structure. `items` becomes `List<CreateOrderItemInput>`, and `shippingAddress` becomes `ShippingAddressInput`. The service receives a strongly typed object instead of manually reading nested `Map` structures.

When designing lists, explicitly define nullability at both the list and element levels:

| SDL | Meaning |
| --- | --- |
| [ID] | List can be null; elements can be null |
| [ID!] | List can be null; elements cannot be null |
| [ID]! | List cannot be null; elements can be null |
| [ID!]! | List cannot be null; elements cannot be null |

Nullability does not replace business validation. For example, `[CreateOrderItemInput!]!` still allows an empty list. Use `@NotEmpty` if an order must contain at least one line item.

## Binding Enums and Custom Scalars

Input objects can contain enums and custom scalars. For enums, the GraphQL value must match one of the declared enum values:

~~~graphql
enum PaymentMethod {
  CASH
  CARD
  BANK_TRANSFER
}

input PaymentInput {
  method: PaymentMethod!
  amount: BigDecimal!
}
~~~

Java DTO:

~~~java
public enum PaymentMethod {
    CASH,
    CARD,
    BANK_TRANSFER
}

public record PaymentInput(
        PaymentMethod method,
        BigDecimal amount) {
}
~~~

For custom scalars such as `DateTime`, `UUID`, or extended `BigDecimal`, register the implementation using `RuntimeWiringConfigurer` and use a compatible Java type in the DTO. If a scalar parses into `OffsetDateTime`, do not declare the Java field as `LocalDateTime` assuming the binder will drop the offset automatically. Keep types consistent across SDL, scalar implementations, and DTOs.

## Using Class DTOs Instead of Records

If your project uses JavaBeans or needs setters, you can declare the input DTO as a class:

~~~java
public class CreateProductInput {

    private String name;
    private String description;
    private ProductCategory category;
    private BigDecimal price;
    private List<String> tagIds;

    public CreateProductInput() {
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }

    public ProductCategory getCategory() {
        return category;
    }

    public void setCategory(ProductCategory category) {
        this.category = category;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void setPrice(BigDecimal price) {
        this.price = price;
    }

    public List<String> getTagIds() {
        return tagIds;
    }

    public void setTagIds(List<String> tagIds) {
        this.tagIds = tagIds;
    }
}
~~~

Class DTOs can use constructor binding or property binding depending on their structure and binder configuration. Keep constructors, property names, and data types simple for predictable binding. Do not create multiple competing constructors without a clear reason.

## Validating Mutation Inputs

The GraphQL schema checks types, required fields, and enums. Bean Validation adds data constraints such as non-blank strings, positive numbers, or non-empty lists.

Add the validation dependency if the project does not already include it:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Define the DTO with constraints:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import java.util.List;

public record CreateOrderInput(
        @NotBlank String customerId,
        @NotEmpty List<@NotNull @Valid CreateOrderItemInput> items,
        @NotNull @Valid ShippingAddressInput shippingAddress,
        String note) {
}

public record CreateOrderItemInput(
        @NotBlank String productId,
        @NotNull @Positive Integer quantity) {
}

public record ShippingAddressInput(
        @NotBlank String recipient,
        @NotBlank String street,
        @NotBlank String city,
        String postalCode) {
}
~~~

The `@Valid` annotation cascades validation into nested objects and list elements. The controller enables validation on the input:

~~~java
@MutationMapping
public Order createOrder(
        @Argument("input") @Valid CreateOrderInput input) {
    return orderService.create(input);
}
~~~

Validation should be placed at the appropriate layer:

| Layer | Example | Responsibility |
| --- | --- | --- |
| GraphQL schema | `customerId` is `ID!`, `quantity` is `Int!` | Checks structure, types, and nullability |
| Bean Validation | `quantity` must be positive, `recipient` non-blank | Checks local data constraints |
| Application service/domain | Customer must exist, product is available, tag belongs to current tenant | Checks state and business rules |

Bean Validation cannot replace authorization checks. For example, a validly formatted `customerId` does not mean the current user is allowed to create an order for that customer.

When validation fails, Spring for GraphQL translates binding/validation errors into GraphQL errors using the framework's error handling mechanism. If the API needs a consistent error format, you can add a `DataFetcherExceptionResolver` to map business errors to information the client is allowed to receive. Do not include stack traces, SQL statements, or internal data in error messages.

## Input Objects for Create and Update

Create operation inputs typically have required fields because the server needs data to create the resource:

~~~graphql
input CreateProductInput {
  name: String!
  category: ProductCategory!
  price: BigDecimal!
}
~~~

Partial update inputs typically have nullable fields so clients only send values they want to change:

~~~graphql
input UpdateProductInput {
  name: String
  description: String
  price: BigDecimal
}

type Mutation {
  updateProduct(id: ID!, input: UpdateProductInput!): Product!
}
~~~

Example where the client updates only the name:

~~~graphql
mutation UpdateProduct($id: ID!, $input: UpdateProductInput!) {
  updateProduct(id: $id, input: $input) {
    id
    name
    description
  }
}
~~~

Variables:

~~~json
{
  "id": "product-101",
  "input": {
    "name": "Wireless Mechanical Keyboard"
  }
}
~~~

The `description` field is omitted. A patch API usually defines an omitted field as keeping the current value, whereas an explicit `null` clears the value if clearing is allowed for that field.

### Distinguishing omitted and explicit null

If a DTO only has regular nullable properties like `String description`, omitted values and explicit null values may both bind to `null`. When business logic needs to distinguish between the two states, Spring for GraphQL provides `ArgumentValue<T>` to retain whether a field was omitted.

Update DTO example:

~~~java
import org.springframework.graphql.data.ArgumentValue;
import java.math.BigDecimal;

public record UpdateProductInput(
        ArgumentValue<String> name,
        ArgumentValue<String> description,
        ArgumentValue<BigDecimal> price) {
}
~~~

The service can handle each field:

~~~java
public Product update(String id, UpdateProductInput input) {
    Product current = productRepository.findById(id)
            .orElseThrow(() -> new ProductNotFoundException(id));

    if (!input.name().isOmitted()) {
        current.setName(input.name().value());
    }
    if (!input.description().isOmitted()) {
        current.setDescription(input.description().value());
    }
    if (!input.price().isOmitted()) {
        current.setPrice(input.price().value());
    }

    return productRepository.save(current);
}
~~~

In this example, when `description` is omitted, it remains unchanged; when `description` is explicitly null, its value is cleared. For `name` and `price`, the service should reject null according to business rules before saving. You can combine validation or explicit checks to ensure valid data.

If the use case does not need to distinguish omitted from null, a regular nullable DTO is simpler. When using `ArgumentValue` inside nested input objects, test binding against your project's Spring for GraphQL version to confirm actual semantics.

### Default values in input objects

GraphQL allows declaring defaults for input fields:

~~~graphql
input SearchProductsInput {
  page: Int = 0
  size: Int! = 20
  keyword: String
}
~~~

If `page` or `size` is omitted, GraphQL applies the default. If the nullable `keyword` field is omitted, it has no supplied value. If the client sends `keyword: null`, its value remains null; defaults apply only when a field is omitted, not when an explicit null is passed.

Define defaults in SDL when the value represents a general API rule. If a default depends on tenant, permissions, or runtime configuration, compute it in the service instead of hardcoding it in the schema.

## Designing Mutation Responses

A mutation can return the newly created object directly or return a payload type containing the object and metadata. For small APIs, returning `Product` directly is straightforward:

~~~graphql
type Mutation {
  createProduct(input: CreateProductInput!): Product!
}
~~~

For APIs needing extra details like a request ID, processing status, or structured business errors, use a payload:

~~~graphql
type CreateProductPayload {
  product: Product
  requestId: ID!
}

type Mutation {
  createProduct(input: CreateProductInput!): CreateProductPayload!
}
~~~

A payload is an output object type, not an input object. Clients can select the fields they want to receive:

~~~graphql
mutation CreateProduct($input: CreateProductInput!) {
  createProduct(input: $input) {
    requestId
    product {
      id
      name
    }
  }
}
~~~

Choose the response shape based on client needs and the API's error conventions. There is no need to wrap every mutation in a payload if it adds no extra value.

## Transaction Boundaries and Mutation Execution

Root mutation fields in an operation are executed serially by GraphQL. However, this does not automatically guarantee that multiple mutation fields in the same operation run in a single database transaction or roll back together.

If a use case requires atomicity, group its business steps into an application service and place the transaction at that layer. For example, creating an order may require checking inventory, creating the order, and writing order items in the same transaction. Do not rely on clients sending multiple mutation fields in one request as a substitute for a business transaction.

Similarly, controllers should focus on receiving input, calling services, and returning results. Pricing rules, inventory checks, authorization, and data writes belong in the application/domain layer.

## Testing Mutation Inputs with GraphQlTester

`GraphQlTester` lets you send documents and variables, then assert on the response. Example:

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

graphQlTester.document("""
        mutation CreateProduct($input: CreateProductInput!) {
            createProduct(input: $input) {
                id
                name
                category
            }
        }
        """)
    .variable("input", Map.of(
            "name", "Mechanical Keyboard",
            "category", "ELECTRONICS",
            "price", new BigDecimal("1850000.00"),
            "tagIds", List.of("tag-01", "tag-07")))
    .execute()
    .path("createProduct.name")
    .entity(String.class)
    .isEqualTo("Mechanical Keyboard");
~~~

In real tests, you can use `@GraphQlTest` to test the controller and related schema, mocking the service to verify the DTO binds properly. Integration tests with a full application context verify runtime wiring, validation, and persistence together.

You should test cases such as:

1. Valid input binds to the DTO with exact values.
2. Nested inputs and lists bind with the expected structure.
3. Missing non-null fields or invalid types are rejected by GraphQL.
4. Invalid enums or custom scalars are rejected.
5. Bean Validation catches blank strings, empty lists, or negative quantities.
6. Business validation rejects invalid customers, products, or tags.
7. Update inputs distinguish omitted from explicit null per contract.
8. Failed mutations leave no partial side effects when the use case requires a transaction.
9. Unauthorized users cannot modify data outside their scope.

Beyond the response, check data state after the mutation to confirm the operation created or updated records accurately.

## Common Pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Unable to bind input to DTO | Field names or Java types incompatible with SDL | Compare field names, constructors, and data types |
| Using an object type as input | Confusing output types with input objects | Declare a dedicated input type |
| Nullable field causes Java error | DTO uses primitive types | Use reference types like `Integer` or `Boolean` |
| Nested field does not bind | Child DTO lacks a matching constructor/property | Check nested DTO structure |
| Enum fails conversion | Client value does not match enum value | Synchronize SDL and Java enums |
| Validation does not run | Missing validation dependency, `@Valid`, or cascade validation | Check starter and annotations |
| Update accidentally clears data | Treating omitted and null as the same state | Use `ArgumentValue` when distinction is needed |
| Client sends internal fields | Input object is too broad or binds directly to entity | Create use-case-specific DTOs and enforce authorization |
| Mutation leaves partial data | Transaction placed on wrong layer or fragmented steps | Group atomic logic into a transactional service |

## Comprehensive Practice

Build an order creation mutation:

1. Declare `CreateOrderInput` with `customerId`, `items`, `shippingAddress`, and `note`.
2. Declare `CreateOrderItemInput` along with `ShippingAddressInput`.
3. Create matching Java records and a controller accepting `@Argument("input")`.
4. Use `@Valid` to validate local data such as non-blank recipient and positive quantity.
5. In `OrderService`, validate customer, products, inventory, and access permissions.
6. Place a transaction on the service if creating the order and order items must be atomic.
7. Write `GraphQlTester` tests for valid input, missing required fields, empty lists, negative quantity, and non-existent products.
8. Add `UpdateOrderInput` with nullable fields and use `ArgumentValue` for fields that must distinguish omitted from null.

After completing this, explain which parts are checked by the GraphQL schema, which are handled by Bean Validation, and which must be decided by the service.

## Key Takeaways

Mutation input objects group related data into a typed structure, making the schema readable and extensible. Spring for GraphQL uses `@Argument` and the argument binder to convert inputs into Java records or classes, including nested objects, lists, and enums. The GraphQL schema checks types and nullability; Bean Validation checks data constraints; services enforce business rules, authorization, and transactions. For partial updates, clearly define the semantics of omitted and explicit null fields; use `ArgumentValue<T>` when distinguishing those states. Test mutations with variables and `GraphQlTester`, and verify the operation's side effects.
