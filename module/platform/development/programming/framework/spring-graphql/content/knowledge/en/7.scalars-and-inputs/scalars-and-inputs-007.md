# Input Object Binding

## Objectives

After this lesson, you will be able to:

- Design input objects in GraphQL SDL for queries and mutations.
- Explain how Spring for GraphQL binds GraphQL data into Java classes, records, and collections.
- Use @Argument to receive input objects in annotated controllers.
- Bind nested inputs, lists, enums, and domain data types.
- Combine Bean Validation to validate data and handle binding errors.
- Distinguish omitted data from null when designing partial-update mutations.

## What Is Input Object Binding?

A GraphQL input object is a data structure that a client sends to a field, typically used when a query has multiple criteria or a mutation requires multiple related pieces of data. An input object is declared using the input keyword in SDL.

Spring for GraphQL provides an argument binding mechanism to convert GraphQL-processed data into Java parameters. With an annotated controller, you can receive an input object using @Argument and a corresponding DTO, class, or record. This relieves the controller from manually reading each key from a Map and converting values by hand.

For example, a book creation API might accept a title, author ID, and page count:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
  pageCount: Int
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
~~~

The client sends a mutation:

~~~graphql
mutation CreateBook($input: CreateBookInput!) {
  createBook(input: $input) {
    id
    title
  }
}
~~~

Variables:

~~~json
{
  "input": {
    "title": "Spring GraphQL Guide",
    "authorId": "author-12",
    "pageCount": 320
  }
}
~~~

GraphQL validates the input structure against the schema before executing the resolver. Spring for GraphQL then binds the input object into the Java type declared by the controller method.

## Input Objects and Object Types Serve Different Purposes

GraphQL separates types used to accept data from types used to return data:

| Kind | Declaration | Purpose |
| --- | --- | --- |
| Object type | type Book { ... } | Describes data that can be queried in a response |
| Input object | input CreateBookInput { ... } | Describes data a client can send to a field |

An input object cannot use an object type as a subfield. It can only contain valid input types such as scalars, enums, other input objects, and their list/non-null modifiers. The following example is invalid:

~~~graphql
type Author {
  id: ID!
  name: String!
}

input CreateBookInput {
  title: String!
  author: Author
}
~~~

Author is an object type, so it cannot be used as an input object field. Declare a separate input type instead:

~~~graphql
input AuthorReferenceInput {
  authorId: ID!
}

input CreateBookInput {
  title: String!
  author: AuthorReferenceInput!
}
~~~

Separating input and output helps the API strictly control what data clients are allowed to send. A Book object may contain createdAt, internalStatus, or read-only fields; CreateBookInput should contain only the attributes that the book creation use case actually needs.

## Binding Input Objects to a Java Record

Java records fit input DTOs well because they represent immutable data with an explicit constructor and component-named accessors.

~~~java
public record CreateBookInput(
        String title,
        String authorId,
        Integer pageCount) {
}
~~~

The controller receives the entire input argument:

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

Component names in the record must match the field names in the input object. With a schema containing title, authorId, and pageCount, the binder maps those values into CreateBookInput. Java types must be compatible with GraphQL types: String typically binds to String, Int to Integer or int when guaranteed non-null, and lists to appropriate collections.

Prefer reference types such as Integer for nullable fields. With int, Java cannot represent null. For fields that can be omitted or sent as null, reference types allow the DTO to accurately reflect the incoming data.

## Binding to a Regular Java Class

You can also use a regular class DTO instead of a record. Spring for GraphQL supports binding via constructors or property binding mechanisms matching the class structure.

~~~java
public class CreateBookInput {

    private String title;
    private String authorId;
    private Integer pageCount;

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

    public Integer getPageCount() {
        return pageCount;
    }

    public void setPageCount(Integer pageCount) {
        this.pageCount = pageCount;
    }
}
~~~

A class with a suitable constructor and setters is often convenient when the DTO needs to comply with JavaBean conventions or framework validation. For immutable classes, declare an explicit constructor and ensure the binder can match parameter names with input fields.

Avoid adding unnecessary multiple constructors that make constructor binding selection ambiguous. Input DTOs should be simple, closely mirror the input object structure, and carry no persistence logic.

## How Spring for GraphQL Performs Binding

The processing flow can be visualized in the following steps:

~~~mermaid
flowchart TD
    A[Client sends variables or literals] --> B[GraphQL parses and coerces input]
    B --> C[Validates types and structure against SDL]
    C --> D[GraphQL produces argument data]
    D --> E[Spring GraphQlArgumentBinder]
    E --> F[Converts and binds into Java DTO]
    F --> G[Annotated controller]
    G --> H[Application service]
    H --> I[GraphQL response]
~~~

GraphQL is responsible for validating the schema contract, such as required fields, scalar types, enums, and input structure. Spring for GraphQL then binds the argument data into the Java type declared on the method. Binding may involve type conversion, constructor invocation, or property assignment depending on the DTO.

These two layers can produce two distinct categories of errors:

- GraphQL input coercion/validation: non-existent field on an input type, missing non-null field, wrong scalar, or invalid enum.
- Java argument binding: inability to convert data to the target Java type, incompatible constructor, or property assignment error.

When diagnosing issues, inspect both GraphQL errors and server logs. A binding error can occur before the controller method is ever invoked.

## Binding Nested Input Objects

An input object can contain other input objects. This is useful when a mutation accepts domain-structured data.

For example, creating an order containing shipping details and a list of items:

~~~graphql
input AddressInput {
  recipient: String!
  street: String!
  city: String!
  postalCode: String
}

input OrderItemInput {
  productId: ID!
  quantity: Int!
}

input CreateOrderInput {
  customerId: ID!
  shippingAddress: AddressInput!
  items: [OrderItemInput!]!
}

type Mutation {
  createOrder(input: CreateOrderInput!): Order!
}
~~~

Corresponding Java records:

~~~java
public record AddressInput(
        String recipient,
        String street,
        String city,
        String postalCode) {
}

public record OrderItemInput(
        String productId,
        Integer quantity) {
}

public record CreateOrderInput(
        String customerId,
        AddressInput shippingAddress,
        List<OrderItemInput> items) {
}
~~~

The controller can accept the top-level DTO:

~~~java
@MutationMapping
public Order createOrder(
        @Argument("input") CreateOrderInput input) {
    return orderService.create(input);
}
~~~

Spring for GraphQL binds nested objects according to the matching structure. The OrderItemInput list binds into List<OrderItemInput>; shippingAddress binds into AddressInput. The service receives a cleanly structured DTO and can run business checks such as verifying the product exists, checking inventory availability, and ensuring the address is supported.

The schema only checks types and presence. For example, quantity: Int! does not guarantee that the quantity is greater than 0. That condition belongs to validation or application business logic.

## Binding Lists, Enums, and Specialized Scalars

### Lists

An input object can contain a list of scalars or a list of input objects:

~~~graphql
input BulkArchiveInput {
  bookIds: [ID!]!
}
~~~

The Java DTO can use List<String>:

~~~java
public record BulkArchiveInput(List<String> bookIds) {
}
~~~

With [ID!]!, the list cannot be null and each element cannot be null. An empty list is still valid under GraphQL typing; if business rules require at least one element, add validation such as @NotEmpty.

### Enums

A GraphQL enum is a useful input/output type for a finite set of values:

~~~graphql
enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

input BookFilterInput {
  status: BookStatus
}
~~~

Java can declare the corresponding enum:

~~~java
public enum BookStatus {
    DRAFT,
    PUBLISHED,
    ARCHIVED
}

public record BookFilterInput(BookStatus status) {
}
~~~

Enum constant names must match the GraphQL enum values. If different name-conversion rules are needed, configure explicit mapping and test it.

### Custom Scalars

If the schema uses a custom scalar, the Java DTO needs a target type compatible with the scalar implementation. For example, a DateTime scalar may parse into Instant or OffsetDateTime depending on the scalar library selected. Do not assume every custom scalar automatically binds to every seemingly similar Java type; verify the Coercing implementation and the application's conversion service.

## Renaming Fields During Binding with @BindParam

Sometimes a schema uses camelCase or snake_case by API convention while Java property names follow a different convention. Spring for GraphQL provides @BindParam to specify the input field name used when binding constructor parameters or properties.

Schema example:

~~~graphql
input CreateCustomerInput {
  first_name: String!
  last_name: String!
}
~~~

The Java record can keep camelCase component names:

~~~java
import org.springframework.graphql.data.BindParam;

public record CreateCustomerInput(
        @BindParam("first_name") String firstName,
        @BindParam("last_name") String lastName) {
}
~~~

When using @BindParam, place the annotation where the binder supports it in the DTO and verify with tests. Do not rename schema fields just to match a Java class if doing so makes the API inconsistent with existing clients.

## Using Map When Input Structure Is Truly Dynamic

In some cases, an application needs to receive an input object with a dynamic structure. You can accept the argument as a Map:

~~~java
@MutationMapping
public Result configure(
        @Argument("settings") Map<String, Object> settings) {
    return configurationService.apply(settings);
}
~~~

A Map is flexible, yet sacrifices the benefits of a statically typed DTO: the compiler does not check keys, value types, or nested structures. If the schema already defines the input structure, prefer a DTO or record. Use a Map only when data genuinely expands dynamically and the service enforces strict allowlists, type checks, and size limits.

## Validation for Input Objects

The schema validates types and nullability, but does not replace business validation. For example:

- title must not be empty or whitespace-only.
- pageCount must be greater than 0.
- items must contain at least one element.
- quantity must be greater than 0.
- the address must have a valid city according to system rules.

You can use Jakarta Bean Validation on DTOs. Add the validation dependency compatible with Spring Boot:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Define constraints on the records:

~~~java
public record CreateOrderInput(
        @NotBlank String customerId,
        @NotNull @Valid AddressInput shippingAddress,
        @NotEmpty List<@Valid OrderItemInput> items) {
}

public record AddressInput(
        @NotBlank String recipient,
        @NotBlank String street,
        @NotBlank String city,
        String postalCode) {
}

public record OrderItemInput(
        @NotBlank String productId,
        @NotNull @Positive Integer quantity) {
}
~~~

Place @Valid on nested fields so validation cascades into child objects and list elements. The controller triggers validation:

~~~java
@MutationMapping
public Order createOrder(
        @Argument("input") @Valid CreateOrderInput input) {
    return orderService.create(input);
}
~~~

When validation fails, the method should not proceed with business execution. Spring for GraphQL can translate binding/validation errors into GraphQL errors; applications can use an exception resolver to standardize error messages and error codes for clients. Do not return stack traces, SQL queries, or internal data in error messages.

Distinguish three validation layers:

| Layer | Example | Where Handled |
| --- | --- | --- |
| GraphQL schema | Required fields, Int type, valid enum | GraphQL engine |
| DTO validation | Non-blank string, positive quantity, non-empty list | Bean Validation |
| Business validation | Customer exists, product in stock, user authorized to place order | Application service/domain |

Do not cram every rule into the SDL or DTO. Rules that depend on the database, current state, or user permissions should be checked in the business layer.

## Nullability, Defaults, and Input Objects

Modifiers in SDL determine which data may be missing or null:

~~~graphql
input SearchBooksInput {
  keyword: String
  authorId: ID
  page: Int = 0
  size: Int! = 20
}
~~~

keyword and authorId can be omitted or set to null. page has a default of 0; if omitted, GraphQL applies the default value. size is non-null with a default of 20, so the client may omit it but must not pass null.

In Java, use reference types for nullable fields:

~~~java
public record SearchBooksInput(
        String keyword,
        String authorId,
        Integer page,
        Integer size) {
}
~~~

If you need to distinguish an omitted field from an explicit null, Spring for GraphQL supports ArgumentValue<T> for arguments and compatible binding targets. For instance, an update DTO can declare ArgumentValue<String> subtitle to know whether the client wants to keep or clear the subtitle. Test nested input binding on the Spring for GraphQL version you use; do not wrap every field if business logic does not need the distinction.

## Designing Safe DTOs

Input objects are the boundary for data entering the system from clients. Design DTOs per use case instead of binding directly to JPA entities or persistence documents.

For example, a User entity may have attributes id, email, role, enabled, and createdAt. A profile update mutation should accept only the fields the user is allowed to change:

~~~graphql
input UpdateProfileInput {
  displayName: String
  phoneNumber: String
}
~~~

Corresponding DTO:

~~~java
public record UpdateProfileInput(
        String displayName,
        String phoneNumber) {
}
~~~

If you bind directly to the entity, internal attributes might accidentally become part of the contract or get updated through another binding path. Dedicated DTOs limit input data, clarify field ownership, and prevent mass assignment.

In addition:

- Do not trust userId or tenantId values sent by the client when identity can be obtained from the security context.
- Enforce authorization on each object and action in the service.
- Limit list sizes and string lengths to prevent oversized requests.
- Do not write raw inputs verbatim to logs if they contain sensitive information.
- Keep input DTOs independent of persistence entities so the schema can evolve according to API needs.

## Testing Input Object Binding

Spring for GraphQL provides GraphQlTester to test operations, variables, and results. Example:

~~~java
graphQlTester.document("""
        mutation CreateBook($input: CreateBookInput!) {
            createBook(input: $input) {
                id
                title
            }
        }
        """)
    .variable("input", Map.of(
            "title", "Spring GraphQL Guide",
            "authorId", "author-12",
            "pageCount", 320))
    .execute()
    .path("createBook.title")
    .entity(String.class)
    .isEqualTo("Spring GraphQL Guide");
~~~

You should test these cases:

1. Valid input binds to the DTO with exact values.
2. Nested inputs and lists bind in the right order and with the right types.
3. Omitted optional fields and explicit null fields are handled according to the contract.
4. Missing non-null fields or wrong types are rejected by GraphQL.
5. Invalid enums or custom scalars are rejected.
6. Bean Validation catches data violating constraints.
7. Business validation rejects invalid state, such as a non-existent product.
8. Unauthorized users cannot submit input to modify data outside their scope.

When testing errors, check both GraphQL errors and post-mutation data state to verify that a failed operation leaves no unintended side effects.

## Common Errors

| Symptom | Possible Cause | Solution |
| --- | --- | --- |
| Argument fails to bind to DTO | Field name does not match component/property or constructor is incompatible | Compare SDL with DTO; use @BindParam when needed |
| Input object field reports wrong type | Using an object type instead of an input type | Declare a dedicated input object |
| Nullable value causes Java error | Using primitive types for nullable fields | Use reference types like Integer or Boolean |
| Nested field is not bound | Child DTO lacks matching constructor/properties | Check DTO structure and collection types |
| Enum fails to convert | Java constant name differs from GraphQL enum value | Align names or configure explicit mapping |
| Validation does not run | Missing validation dependency, missing @Valid, or missing cascade validation | Check starter, annotations, and @Valid on nested fields |
| Input can update internal fields | Binding directly to entity or overly broad DTO | Create use-case-specific input DTOs and check permissions |

## Comprehensive Practice

Build an order creation mutation following the CreateOrderInput schema from the nested inputs section:

1. Create the AddressInput, OrderItemInput, and CreateOrderInput records.
2. Write a controller accepting @Argument("input") and calling OrderService.
3. Add Bean Validation for recipient, street, city, productId, and quantity.
4. Check business rules: the customer must exist, products must be available for sale, and quantity must be greater than 0.
5. Write GraphQlTester tests for valid input, missing required fields, empty lists, negative quantity, and non-existent productId.
6. Verify that error responses do not leak internal data and no order is created when validation fails.

After completing it, try renaming an SDL field and updating the DTO using @BindParam. Observe the tests to clearly understand the relationship between the GraphQL contract and Java binding.

## Takeaways

Input objects describe the data structures clients send into GraphQL fields. Spring for GraphQL uses its argument binder to convert GraphQL-validated data into Java records, classes, lists, or target types. @Argument connects inputs to controller methods; @BindParam supports custom field-name mapping; @Valid and Bean Validation enforce data constraints. Use dedicated DTOs per use case, support nested inputs purposefully, distinguish null from omitted when needed, and leave business validation and authorization to the service layer.
