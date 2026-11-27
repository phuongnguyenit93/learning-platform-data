# Nested Input Objects

Nested input objects are how GraphQL describes multi-level structured input data. Instead of sending a flat set of separate arguments, the client sends one input object containing child input objects, lists, or related scalars. This design fits mutations that accept a multi-part business request, such as creating an order along with a shipping address and line items, or creating a book along with metadata and a list of chapters.

In Spring for GraphQL, input objects are declared in SDL. GraphQL validates and coerces incoming data against the schema; Spring binds that structure into a Java record or DTO via **@Argument**. The validation and service layers then enforce business rules, access permissions, and consistency across the entire operation.

This lesson focuses on composing input objects into nested structures, passing variables, null/default and list rules, recursive inputs, Java binding, nested validation, and payload limits to enforce.

## 1. When Do You Need Nested Input Objects?

A mutation often receives data belonging to multiple groups. For example, when creating a book, the client might need to send book details, metadata, and chapters:

~~~graphql
type Mutation {
  createBook(
    title: String!
    language: String
    pageCount: Int
    chapterTitles: [String!]
  ): Book!
}
~~~

As the input structure grows, the mutation accumulates many arguments at the same level without clearly expressing data groupings. We can group them into separate input objects:

~~~graphql
input BookMetadataInput {
  language: String
  pageCount: Int
}

input ChapterInput {
  title: String!
  position: Int!
}

input CreateBookInput {
  title: String!
  metadata: BookMetadataInput
  chapters: [ChapterInput!]!
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
~~~

Here, **CreateBookInput** is the primary input; **BookMetadataInput** and **ChapterInput** describe the sub-parts. This structure clearly expresses relationships among values and lets clients send a single complete request.

Nested inputs are useful when:

- A business operation receives multiple groups of data with their own structure.
- A group of fields can be reused across different inputs.
- Data has a parent-child relationship, such as an order and order lines.
- The client needs to send a list of child objects.
- A hierarchical structure needs to be created or updated within the same use case.

Do not nest objects just to make the schema look hierarchical. Use nested structures when they reflect real business boundaries or genuinely required data shapes.

## 2. Data Type Rules for Input Objects

An input object is declared with **input**. Fields inside an input object may only use input types:

- Built-in scalars such as **String**, **Int**, **Float**, **Boolean**, **ID**.
- Custom scalars registered at runtime.
- Enums.
- Other input objects.
- Lists or non-null modifiers wrapping a valid input type.

Example:

~~~graphql
scalar DateTime

enum BookStatus {
  DRAFT
  PUBLISHED
}

input BookMetadataInput {
  language: String
  publishedAt: DateTime
  status: BookStatus = DRAFT
  keywords: [String!]
}
~~~

An input object cannot contain object types, interfaces, or unions. Those are output types. To reference an existing object, the client typically sends an ID:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
}
~~~

The server uses **authorId** to load the author, verify the author exists, and check whether the user has permission to use that author. If the client needs to create a new child object in the same mutation, declare a separate input type for the child object rather than using an output type.

Input fields also cannot declare their own arguments. If parameters need to be passed to an operation, arguments belong on fields of object types, while input objects merely describe the submitted data.

## 3. Building a Nested Structure

Consider an example mutation that creates an order. An order has a shipping address, contact information, and multiple product line items:

~~~graphql
input AddressInput {
  recipient: String!
  street: String!
  ward: String
  city: String!
  postalCode: String
}

input ContactInput {
  email: String!
  phone: String
}

input OrderLineInput {
  productId: ID!
  quantity: Int!
  note: String
}

input CreateOrderInput {
  shippingAddress: AddressInput!
  contact: ContactInput!
  lines: [OrderLineInput!]!
  customerNote: String
}

type Mutation {
  createOrder(input: CreateOrderInput!): Order!
}
~~~

The primary input **CreateOrderInput** describes the order creation request. The child inputs describe groups of data with distinct responsibilities:

| Input Object | Responsibility |
|---|---|
| **AddressInput** | Delivery address |
| **ContactInput** | Contact details for the order |
| **OrderLineInput** | A product and quantity to order |
| **CreateOrderInput** | Aggregates all data parts to create the order |

The client sends a corresponding variables object:

~~~json
{
  "input": {
    "shippingAddress": {
      "recipient": "Nguyen An",
      "street": "12 Nguyen Hue",
      "ward": "Ben Nghe",
      "city": "Ho Chi Minh City",
      "postalCode": "700000"
    },
    "contact": {
      "email": "an@example.com",
      "phone": "0900000000"
    },
    "lines": [
      {
        "productId": "product-01",
        "quantity": 2
      },
      {
        "productId": "product-02",
        "quantity": 1,
        "note": "Ship together"
      }
    ],
    "customerNote": "Call before delivery"
  }
}
~~~

Field names and structure in JSON must match the input objects in the schema. GraphQL validates every level; a child field with the wrong type or a missing required field renders the input invalid before the mutation resolver executes.

## 4. Passing Nested Inputs with Variables

Prefer using variables for mutations with nested structures. The GraphQL document stays stable:

~~~graphql
mutation CreateOrder($input: CreateOrderInput!) {
  createOrder(input: $input) {
    id
    status
    total
  }
}
~~~

The client passes data in JSON variables. Separating the document from variables lets you reuse operations, avoid manual query string concatenation, and easily test different datasets.

In a GraphQL document, enums are written as enum literals:

~~~graphql
input: {
  status: PUBLISHED
}
~~~

In JSON variables, enums are represented as strings:

~~~json
{
  "status": "PUBLISHED"
}
~~~

Scalar values inside nested objects are coerced according to their respective scalars. For instance, **DateTime** needs a scalar implementation to parse/serialize dates and times; declaring **scalar DateTime** in SDL alone is not enough.

### Unknown Fields

Input objects accept only declared fields. If a client sends:

~~~json
{
  "input": {
    "shippingAddress": {
      "recipient": "Nguyen An",
      "street": "12 Nguyen Hue",
      "city": "Ho Chi Minh City",
      "countryCode": "VN"
    },
    "lines": []
  }
}
~~~

If **countryCode** is not defined on **AddressInput**, GraphQL reports an input coercion/validation error. This prevents clients from inadvertently sending properties that the server has not exposed.

### List Inputs and Singleton Coercion

List fields are normally sent as JSON arrays. GraphQL input coercion also allows a single value to be coerced into a single-element list in certain cases under list input rules:

~~~graphql
input CreateBookInput {
  tags: [String!]
}
~~~

For the **tags** field, clients should send an array such as **["graphql"]** so the payload clearly expresses intent. Do not rely on singleton coercion in the client contract when the business data is inherently a list.

## 5. Multi-Level Lists and Nullability

Nested inputs can have multiple layers of nullable and non-null modifiers. Each **!** applies at the exact position it wraps.

For the field:

~~~graphql
input CreateOrderInput {
  lines: [OrderLineInput!]!
}
~~~

Meaning:

- **lines** cannot be null.
- The **lines** list may be empty, unless business validation requires at least one element.
- Each **OrderLineInput** element cannot be null.
- Fields inside each **OrderLineInput** continue to follow their own nullability rules.

Comparison of the four list forms:

| Declaration | List Nullable? | Element Nullable? |
|---|---:|---:|
| **[OrderLineInput]** | Yes | Yes |
| **[OrderLineInput]!** | No | Yes |
| **[OrderLineInput!]** | Yes | No |
| **[OrderLineInput!]!** | No | No |

Example:

~~~graphql
input OrderLineInput {
  productId: ID!
  quantity: Int!
  discountCode: String
}
~~~

Having a non-null list and non-null lines does not mean every field inside a line is required. **discountCode** can still be omitted or null.

GraphQL has no direct syntax to specify that a list must contain at least one element. If an order must contain at least one line, check this in Bean Validation or the service layer.

## 6. Default Values in Nested Inputs

Input fields can declare default values. Defaults apply when the field is omitted, according to GraphQL rules:

~~~graphql
enum DeliveryMethod {
  STANDARD
  EXPRESS
}

input DeliveryOptionsInput {
  method: DeliveryMethod = STANDARD
  leaveAtDoor: Boolean = false
}

input CreateOrderInput {
  shippingAddress: AddressInput!
  lines: [OrderLineInput!]!
  delivery: DeliveryOptionsInput = {
    method: STANDARD
    leaveAtDoor: false
  }
}
~~~

If the client omits **delivery**, the default input object is used. If the client sends **delivery** as an object while omitting **leaveAtDoor**, the child field's default can be applied. If the client explicitly sends **delivery: null**, the nullable field receives null instead of the default object.

Distinguish these cases:

| Payload | Result According to Schema |
|---|---|
| Omit **delivery** | Uses the default for the **delivery** field |
| Send **delivery: null** | Value of **delivery** is null if the field is nullable |
| Send **delivery: {}** | Input object is present; child fields use their defaults if defined |
| Send **delivery: { method: EXPRESS }** | **method** is EXPRESS; other child fields use their defaults if defined |

Defaults should be used for stable, self-explanatory values. Do not set defaults for data that depends on the current user, current timestamp, tenant, or database state, because schema defaults are static values defined in the schema.

## 7. Distinguishing Omitted and Null in Nested Inputs

For partial-update mutations, the two states "field not sent" and "field sent with null" can carry different meanings:

- Omitted: keep the current value.
- Null: clear or set the value to null, if business rules allow.

Example:

~~~graphql
input UpdateAddressInput {
  street: String
  ward: String
  city: String
}

input UpdateCustomerInput {
  id: ID!
  address: UpdateAddressInput
}
~~~

Payload sending only **city**:

~~~json
{
  "input": {
    "id": "customer-01",
    "address": {
      "city": "Ho Chi Minh City"
    }
  }
}
~~~

Here **street** and **ward** are omitted. If the client sends **ward: null**, the server may interpret that as a request to clear ward. Likewise, omitting **address** completely versus sending **address: null** can also carry different meanings.

A regular Java DTO may not preserve whether a field was present: an omitted field and a field passed as null can both become Java null. If exact patch semantics are required, you can bind to a Map structure to check key presence, use an appropriate presence-aware type at the argument boundary, or design a dedicated mutation for clearing data. Verify how your Spring GraphQL version binds inputs, especially with deeply nested input objects.

Do not assume that every null in an input means "keep unchanged". Document the API contract clearly and test both omitted and explicit null cases.

## 8. Recursive Input Objects

An input object can reference another input object and can form recursive structures. For example, representing a category tree:

~~~graphql
input CategoryInput {
  name: String!
  children: [CategoryInput!]
}

input CreateCategoryTreeInput {
  root: CategoryInput!
}

type Mutation {
  createCategoryTree(input: CreateCategoryTreeInput!): Category!
}
~~~

Clients can send a multi-level tree:

~~~json
{
  "input": {
    "root": {
      "name": "Books",
      "children": [
        {
          "name": "Programming",
          "children": [
            {
              "name": "GraphQL"
            },
            {
              "name": "Spring"
            }
          ]
        },
        {
          "name": "Databases"
        }
      ]
    }
  }
}
~~~

GraphQL permits an input type to reference itself recursively provided the structure has a termination point. A cycle consisting solely of required singular non-null fields with no base case is invalid, because no finite value could ever satisfy that structure. You can break the cycle with a nullable field or a list.

The following example creates a singular non-null cycle that cannot terminate:

~~~graphql
input NodeInput {
  next: NodeInput!
}
~~~

A valid structure with a termination point:

~~~graphql
input NodeInput {
  value: String!
  next: NodeInput
}
~~~

When accepting recursive data, the server must enforce limits on depth, node count, and total payload size. A valid schema does not mean every valid payload has an acceptable processing cost.

## 9. Binding Nested Inputs to Java in Spring for GraphQL

Spring for GraphQL binds input objects into controller Java parameters via **@Argument**. You can represent input levels with nested records.

SDL:

~~~graphql
input AddressInput {
  recipient: String!
  street: String!
  city: String!
  postalCode: String
}

input OrderLineInput {
  productId: ID!
  quantity: Int!
  note: String
}

input CreateOrderInput {
  shippingAddress: AddressInput!
  lines: [OrderLineInput!]!
  customerNote: String
}

type Mutation {
  createOrder(input: CreateOrderInput!): Order!
}
~~~

Java records:

~~~java
public record AddressInput(
        String recipient,
        String street,
        String city,
        String postalCode) {
}

public record OrderLineInput(
        String productId,
        Integer quantity,
        String note) {
}

public record CreateOrderInput(
        AddressInput shippingAddress,
        List<OrderLineInput> lines,
        String customerNote) {
}
~~~

Controller:

~~~java
@Controller
public class OrderMutationController {

    private final OrderService orderService;

    public OrderMutationController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MutationMapping
    public Order createOrder(@Argument("input") CreateOrderInput input) {
        CreateOrderCommand command = new CreateOrderCommand(
                input.shippingAddress(),
                input.lines(),
                input.customerNote());

        return orderService.create(command);
    }
}
~~~

**@Argument("input")** extracts the **input** argument of the mutation field and binds the nested structure into records. Java field names must match the input fields in the SDL. Java types must also be compatible: **ID** typically uses **String**, **Int** uses **Integer** or a suitable numeric type, lists use collections, and child inputs use matching records/DTOs.

Consider mapping the GraphQL input DTO into an application-layer command. That keeps the service decoupled from the API structure and allows other adapters to reuse the same business logic.

### When to Use Map Instead of a DTO?

DTOs/records fit when the input structure is known and stable. A Map can be useful when:

- You need to check whether a field was explicitly sent.
- There is an open data section with a separately governed structure.
- You need to handle explicit null differently from omitted.

Do not use Map for all inputs just for flexibility. Map forfeits static typing benefits, refactoring safety, and schema-aligned code clarity. Even when binding to a Map, the GraphQL schema should still strictly define which input fields are accepted.

## 10. Validation for Nested Inputs

GraphQL validates data types at every input level. For instance, if **quantity** is **Int!**, a client cannot pass a string instead of an integer or omit the required field. However, GraphQL does not automatically check that quantity is greater than 0 or that the product ID exists.

### Bean Validation with Nested Objects

You can use Jakarta Bean Validation to validate every level of input:

~~~java
public record AddressInput(
        @NotBlank String recipient,
        @NotBlank String street,
        @NotBlank String city,
        @Pattern(regexp = "\\d{6}") String postalCode) {
}

public record OrderLineInput(
        @NotBlank String productId,
        @NotNull @Min(1) Integer quantity,
        @Size(max = 200) String note) {
}

public record CreateOrderInput(
        @NotNull @Valid AddressInput shippingAddress,
        @NotEmpty List<@NotNull @Valid OrderLineInput> lines,
        @Size(max = 500) String customerNote) {
}
~~~

Key points to note:

- **@Valid** on **shippingAddress** triggers cascade validation for the child object.
- **@Valid** on the list element type validates each **OrderLineInput**.
- **@NotEmpty** requires the list to have at least one element.
- **@NotNull** on the list element type prevents null elements at the Bean Validation layer.
- **@Min(1)** ensures the quantity is greater than or equal to 1.

The controller can mark the input for validation:

~~~java
@MutationMapping
public Order createOrder(
        @Argument("input") @Valid CreateOrderInput input) {
    return orderService.create(input);
}
~~~

The application requires a Jakarta Bean Validation provider, typically via **spring-boot-starter-validation**. With Spring Boot 3, use annotations from **jakarta.validation**. Verify your application's method/argument validation configuration so constraints are enforced at the proper level.

### Business Validation Across the Entire Input Tree

Some rules require checking data or multiple elements together:

- Do all product IDs exist and are they currently on sale?
- Does the user have permission to purchase those products?
- Does the total quantity exceed order limits?
- Should duplicate product IDs be merged into one line?
- Is the address within a supported delivery area?
- Can the order lines and address be processed within a single transaction?

These rules belong in the service/application layer. Controller validation catches bad inputs early; the service must still protect business invariants because the same service can be invoked through multiple entry points.

## 11. Security When Accepting Multi-Level Data

Nested inputs expand the surface area of client-supplied data. If designed carelessly, clients could alter attributes that the server is supposed to control.

For example, do not accept internal fields like the following if the server determines them:

~~~graphql
input CreateOrderInput {
  customerId: ID
  status: String
  approved: Boolean
  total: Float
  shippingAddress: AddressInput
  lines: [OrderLineInput!]!
}
~~~

The server should obtain **customerId** from the authenticated principal, compute **total** from product prices and quantities, set **status** according to the workflow, and perform approvals through a separate flow. Never trust client-sent values merely because they have valid GraphQL types.

With nested inputs, you should:

- Verify permissions for every referenced ID at every level.
- Never allow clients to choose tenant, owner, or role when the server must determine them.
- Limit nesting depth and the number of child objects.
- Limit string lengths, list sizes, and overall payload size.
- Avoid logging entire inputs if they contain personal information or sensitive data.
- Manage transactions when one mutation creates multiple related objects.
- Clearly define the policy when one list element is invalid: reject the whole mutation or allow partial results.

GraphQL input coercion protects structure and types; authorization and business validation protect data and business permissions.

## 12. Transactions and Consistency When Creating Nested Objects

A mutation receiving nested input may create multiple records: an order, an address, order lines, and product associations. If only some of them are saved successfully, the system can be left in an inconsistent state.

Service example:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final AddressRepository addressRepository;
    private final ProductService productService;

    public OrderService(
            OrderRepository orderRepository,
            AddressRepository addressRepository,
            ProductService productService) {
        this.orderRepository = orderRepository;
        this.addressRepository = addressRepository;
        this.productService = productService;
    }

    @Transactional
    public Order create(CreateOrderCommand command) {
        Address address = addressRepository.save(
                Address.from(command.shippingAddress()));

        List<OrderLine> lines = command.lines().stream()
                .map(line -> {
                    Product product =
                            productService.requirePurchasable(line.productId());
                    return OrderLine.create(product, line.quantity(), line.note());
                })
                .toList();

        Order order = Order.create(address, lines, command.customerNote());
        return orderRepository.save(order);
    }
}
~~~

This example illustrates transaction boundaries. In a real application, calling an external service may not participate in the same database transaction; in such cases, consider an outbox, saga, or appropriate compensation mechanism. Do not let a GraphQL resolver directly coordinate multiple repositories and transactions if that belongs to service business logic.

## 13. Testing Nested Inputs with GraphQlTester

GraphQlTester allows sending nested variables using Map and List:

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
            "shippingAddress", Map.of(
                    "recipient", "Nguyen An",
                    "street", "12 Nguyen Hue",
                    "city", "Ho Chi Minh City"),
            "lines", List.of(
                    Map.of("productId", "product-01", "quantity", 2),
                    Map.of("productId", "product-02", "quantity", 1))))
    .execute()
    .path("createOrder.status")
    .entity(String.class)
    .isEqualTo("CREATED");
~~~

Tests should cover:

1. Full nested input creates the parent object and child objects.
2. Missing non-null nested object is rejected by GraphQL.
3. Child field with wrong type or unknown name is rejected by coercion/validation.
4. Empty lists and non-empty lists are handled according to business rules.
5. One invalid list element produces the outcome matching the mutation's atomicity policy.
6. Bean Validation is applied across nested levels.
7. Omitted and explicit null behave differently if required by the contract.
8. Deeply recursive inputs or oversized payloads are bounded.
9. IDs in nested inputs are checked for permissions and existence.
10. Failures mid-way through saving multiple objects leave no partial state behind.

You can assert errors with **errors()** on GraphQlTester and inspect **data** when the API supports partial results. For atomic mutations, tests should confirm no partial data is persisted when the operation fails.

## 14. Common Nested Input Design Mistakes

| Mistake | Consequence | Solution |
|---|---|---|
| Using an output object type inside an input | Invalid schema | Create a dedicated input object |
| Nesting too many levels without business meaning | Hard for clients to build payloads and hard for server to validate | Separate data groups only when they have clear responsibilities |
| Creating one generic input type for every mutation | Unclear update permissions and required fields | Design inputs per use case |
| Failing to check nullability at each level | May accept incomplete structures or unintended null elements | Choose non-null markers according to the contract |
| Allowing empty lists when business logic requires elements | Mutation creates incomplete objects | Use Bean Validation or business validation |
| Assuming omitted and null mean the same thing | Patch updates may accidentally erase data | Preserve presence information when needed |
| Checking only GraphQL types | Missing non-existent IDs or access control checks | Validate inside the service |
| Allowing unbounded recursive payloads | Can exhaust CPU, memory, and database resources | Limit depth, node count, and payload size |
| Saving child objects piecemeal without a transaction | Data can become inconsistent | Define transactions or compensation workflows |
| Using Map for every input | Loses static typing and makes refactoring harder | Use records/DTOs for known structures |

## 15. Process for Designing Nested Input Objects

When designing a mutation that accepts a nested structure, follow these steps:

1. Identify the use case and the groups of data the client needs to send.
2. Create a separate input object for each group with business meaning.
3. Use only scalars, enums, input objects, and lists in input fields.
4. Choose nullability and defaults at each level, including each list element.
5. Decide which fields reference existing resources by ID and which create new child objects.
6. Define the semantics of omitted, null, and defaults for update mutations.
7. Bind the input into nested Java records/DTOs using **@Argument**.
8. Apply cascaded Bean Validation and business validation.
9. Verify authorization, payload size, depth limits, and transactions.
10. Write GraphQlTester tests for success cases, structural errors, nulls, lists, and deep inputs.

Nested input objects represent a multi-part business request through a clean GraphQL contract. SDL defines structure and types; GraphQL validates data at every level; Spring for GraphQL binds it into Java objects; and the validation and service layers guarantee valid, authorized, and consistently persisted data. When nested structures mirror the domain accurately and have proper resource limits, mutations become easier to understand, test, and scale safely.
