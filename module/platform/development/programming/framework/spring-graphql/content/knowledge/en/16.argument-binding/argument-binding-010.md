# Setter binding

## Objectives

After this lesson, you will be able to:

- Explain setter binding in Spring for GraphQL's argument binding mechanism.
- Create a JavaBean DTO with a no-argument constructor and setters to receive GraphQL data.
- Bind input objects, nested objects, and collections using `@Argument`.
- Understand the role of property names, ConversionService, and GraphQlArgumentBinder.
- Distinguish GraphQL input coercion errors from Java object binding errors.
- Combine setter binding with Bean Validation and ArgumentValue<T>.
- Choose when to use setter binding, constructor binding, or direct field access.

## What is setter binding?

When a client sends arguments to a GraphQL field, Spring for GraphQL needs to convert that data into the Java parameters of a controller method. With @Argument, the framework uses GraphQlArgumentBinder to instantiate and populate the target object.

There are two common ways to instantiate an object:

1. **Constructor binding**: takes argument data and passes it into a primary/data constructor.
2. **Setter binding**: invokes the default constructor to create the object, then maps argument values to properties via setters.

Setter binding suits JavaBean DTOs that have a no-argument constructor and setters following JavaBeans conventions. This approach is useful when the DTO needs mutable properties, compatibility with JavaBean libraries, or is structured in the traditional class style.

For example, the schema declares an input:

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

The client sends a mutation with variables:

~~~graphql
mutation CreateBook($input: CreateBookInput!) {
  createBook(input: $input) {
    id
    title
  }
}
~~~

~~~json
{
  "input": {
    "title": "Spring for GraphQL",
    "authorId": "author-12",
    "pageCount": 320
  }
}
~~~

Spring for GraphQL can bind this input into a `CreateBookInput` JavaBean by creating the object first and then calling the corresponding setters.

## JavaBean conventions for setter binding

A DTO using setter binding typically has:

- A no-argument constructor so the binder can create an instance.
- Setters for each property to be received from GraphQL.
- Java property names matching the field names in the input object.
- Java types capable of representing the data after GraphQL coercion.

Example DTO:

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

In this example:

- CreateBookInput() allows the binder to instantiate the object.
- setTitle receives the value of the title field.
- setAuthorId receives the value of the authorId field.
- setPageCount receives the value of the pageCount field.
- Getters allow the service or other code to read the data after binding.

Setters should perform simple value assignment. Do not call repositories, write to the database, or execute business logic inside setters because the binder may invoke setters in binding order rather than an application-defined business workflow.

## Receiving the DTO with @Argument

The controller receives the entire input object through @Argument:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

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

@Argument("input") specifies that the method receives the argument named `input` on the GraphQL field. The argument name is determined by the schema; the DTO class name does not dictate the argument name.

If the name is omitted from the annotation, Spring can infer it from the method parameter name when parameter name metadata is retained in bytecode—for example, when the project is compiled with the `-parameters` option. Writing `@Argument("input")` explicitly makes the mapping easier to read and avoids relying on compiler configuration.

@Argument has no `required` or `defaultValue` attributes. Requiredness and default values are declared in the SDL, and GraphQL Java validates them before the controller method is invoked.

## Setter binding flow

The binding process can be visualized as follows:

~~~mermaid
flowchart TD
    A[Client sends GraphQL variables] --> B[GraphQL parse and input coercion]
    B --> C[GraphQL builds argument map]
    C --> D[@Argument receives input argument]
    D --> E[GraphQlArgumentBinder]
    E --> F[Invoke no-argument constructor]
    F --> G[Map input field to property]
    G --> H[Invoke matching setter]
    H --> I[Bind nested objects and collections]
    I --> J[Controller method receives DTO]
    J --> K[Application service]
~~~

GraphQL validates the structure against the SDL first. The binder then receives the coerced argument, instantiates the DTO, and populates properties. Only when binding succeeds does the controller method receive the constructed object.

Setter binding applies recursively. If a DTO has a property whose type is another input DTO or a list of input DTOs, the binder continues instantiating child objects and binding inner values using the same principles.

## Binding nested input objects

Suppose an order creation mutation has a shipping address and order line items:

~~~graphql
input ShippingAddressInput {
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
  shippingAddress: ShippingAddressInput!
  items: [OrderItemInput!]!
}

type Mutation {
  createOrder(input: CreateOrderInput!): Order!
}
~~~

The Java DTOs can be designed as separate JavaBeans:

~~~java
public class ShippingAddressInput {

    private String recipient;
    private String street;
    private String city;
    private String postalCode;

    public ShippingAddressInput() {
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

~~~java
public class OrderItemInput {

    private String productId;
    private Integer quantity;

    public OrderItemInput() {
    }

    public String getProductId() {
        return productId;
    }

    public void setProductId(String productId) {
        this.productId = productId;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
~~~

~~~java
import java.util.List;

public class CreateOrderInput {

    private String customerId;
    private ShippingAddressInput shippingAddress;
    private List<OrderItemInput> items;

    public CreateOrderInput() {
    }

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public ShippingAddressInput getShippingAddress() {
        return shippingAddress;
    }

    public void setShippingAddress(ShippingAddressInput shippingAddress) {
        this.shippingAddress = shippingAddress;
    }

    public List<OrderItemInput> getItems() {
        return items;
    }

    public void setItems(List<OrderItemInput> items) {
        this.items = items;
    }
}
~~~

When receiving `CreateOrderInput`, the binder performs these steps:

1. Instantiates `CreateOrderInput` using its no-argument constructor.
2. Instantiates `ShippingAddressInput`, binds the address properties, and assigns it via `setShippingAddress`.
3. Instantiates each `OrderItemInput` in the `items` list.
4. Assigns the bound list via `setItems`.
5. Assigns `customerId` via `setCustomerId`.

The controller only needs to receive the top-level DTO:

~~~java
@MutationMapping
public Order createOrder(
        @Argument("input") CreateOrderInput input) {
    return orderService.create(input);
}
~~~

The binder supports nested object and collection structures, but does not enforce business rules for you. For example, `quantity` may be bound as a type-valid integer while still needing validation to ensure it is greater than 0.

## Data types and ConversionService

GraphQL input values are converted according to scalars and enums in the schema. When further conversion to the target Java type is needed, GraphQlArgumentBinder uses ConversionService.

Common types:

| GraphQL input | Common Java type |
| --- | --- |
| String | String |
| ID | String or a suitable identifier type |
| Int | Integer |
| Float | Double |
| Boolean | Boolean |
| BigDecimal custom scalar | BigDecimal if the scalar returns this type |
| DateTime custom scalar | Type defined by the scalar implementation, e.g., OffsetDateTime |
| Enum | Java enum with matching values |
| List | List<T> or a compatible collection |

Prefer declaring Java types that match the result of GraphQL scalar coercion. ConversionService can support registered conversions, but you should not rely on an implicit conversion that has not been configured or tested.

If the application needs a custom format, register an appropriate converter or formatter with the ConversionService used for argument binding. For custom scalars, define the Java runtime type explicitly in `Coercing`; avoid parsing into one type while declaring the DTO with an incompatible type hoping the binder will sort it out.

## GraphQL field names and Java property names

By default, the binder maps input field names to matching property names. For example:

| GraphQL input field | Java property | Setter |
| --- | --- | --- |
| firstName | firstName | setFirstName(...) |
| authorId | authorId | setAuthorId(...) |
| pageCount | pageCount | setPageCount(...) |

If the schema and Java follow different naming conventions, an explicit mapping strategy is required. For instance, the schema might use `first_name` while the Java property uses `firstName`. `GraphQlArgumentBinder` supports configuring a `nameResolver` to translate GraphQL names to Java property names.

In Spring for GraphQL versions that provide `GraphQlArgumentBinder.Options`, binding options can be configured via `AnnotatedControllerConfigurer`. Specific configuration depends on the framework version; consult the API docs for your project's version before declaring custom beans. For a new schema, agree on a consistent naming convention from the start to avoid custom mapping workarounds.

## Setter binding with validation

Setter binding only guarantees that data is transferred into the DTO. It does not automatically verify constraints such as non-blank strings, positive quantities, or maximum lengths.

You can use Jakarta Bean Validation with constraints on fields or getters of the JavaBean:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

public class OrderItemInput {

    @NotBlank
    private String productId;

    @NotNull
    @Positive
    private Integer quantity;

    public OrderItemInput() {
    }

    public String getProductId() {
        return productId;
    }

    public void setProductId(String productId) {
        this.productId = productId;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
~~~

For nested objects, use `@Valid` to trigger cascading validation:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.util.List;

public class CreateOrderInput {

    @NotNull
    @Valid
    private ShippingAddressInput shippingAddress;

    @NotEmpty
    private List<@NotNull @Valid OrderItemInput> items;

    public CreateOrderInput() {
    }

    public ShippingAddressInput getShippingAddress() {
        return shippingAddress;
    }

    public void setShippingAddress(ShippingAddressInput shippingAddress) {
        this.shippingAddress = shippingAddress;
    }

    public List<OrderItemInput> getItems() {
        return items;
    }

    public void setItems(List<OrderItemInput> items) {
        this.items = items;
    }
}
~~~

The controller triggers validation before calling the service:

~~~java
@MutationMapping
public Order createOrder(
        @Argument("input") @Valid CreateOrderInput input) {
    return orderService.create(input);
}
~~~

Ensure the application includes the `spring-boot-starter-validation` dependency and a configured validator bean. When validation fails, the controller method does not proceed with the use case; the exception can be mapped to a GraphQL error according to the API's error policy.

Distinguish three layers of validation:

- GraphQL schema: data types, required fields, enums, and nullability.
- Bean Validation: lengths, non-blank strings, positive numbers, non-empty lists.
- Application service: whether the object exists, whether its state permits the operation, and whether the user is authorized to perform it.

Do not put database queries or authorization checks inside setters. Setters should only update DTO state; the service is responsible for rules that depend on data and application context.

## Omitted and explicit null in JavaBeans

With regular Java properties, an unsent value and an explicitly sent `null` both result in the property having a `null` value. If a partial-update mutation needs to distinguish these two states, you can use `ArgumentValue<T>` as the property type:

~~~java
import org.springframework.graphql.data.ArgumentValue;

public class UpdateBookInput {

    private ArgumentValue<String> subtitle;

    public UpdateBookInput() {
    }

    public ArgumentValue<String> getSubtitle() {
        return subtitle;
    }

    public void setSubtitle(ArgumentValue<String> subtitle) {
        this.subtitle = subtitle;
    }
}
~~~

In the service:

~~~java
public Book updateSubtitle(Book book, UpdateBookInput input) {
    ArgumentValue<String> subtitle = input.getSubtitle();

    if (subtitle != null && !subtitle.isOmitted()) {
        book.setSubtitle(subtitle.value());
    }

    return bookRepository.save(book);
}
~~~

With `ArgumentValue`, `isOmitted()` indicates whether the field was omitted or provided. If the field is provided with a `null` value, `value()` is `null`; the service can interpret that as a request to clear the subtitle. If the field is omitted, the service preserves the old value.

Spring for GraphQL supports `ArgumentValue` inside object structures bound via `@Argument`, including properties initialized via setters. Test both states in your target version. Only use the wrapper on fields that truly need the distinction; other properties can keep using standard Java types.

## Setter binding vs. constructor binding

The two binding approaches serve different DTO styles:

| Criterion | Setter binding | Constructor binding |
| --- | --- | --- |
| Object instantiation | Default/no-argument constructor | Primary/data constructor |
| Populating data | Invokes setters by property | Passes values into constructor parameters |
| Suitable DTOs | Mutable JavaBeans | Records or immutable classes |
| State changes after creation | Possible via setters | Typically no setters |
| Key requirement | No-argument constructor and matching setters | Matching constructor and parameter names |

Setter binding examples commonly use a class with a no-argument constructor and public setters. Constructor binding is usually more natural with Java records:

~~~java
public record CreateBookInput(
        String title,
        String authorId,
        Integer pageCount) {
}
~~~

If a class has both a matching data constructor and a default constructor, check the binder's constructor selection rules in the Spring for GraphQL version you use. When you intentionally want setter binding, design a simple JavaBean DTO with a default constructor and no competing data constructors.

There is no need to force every DTO in the application into the same style. Choose the binding style based on immutability requirements, code structure, and integrated libraries.

## When a DTO lacks setters: direct field access

Setter binding requires accessor methods to assign properties. If the target object lacks setters, Spring for GraphQL provides an option to fall back to direct field access. This option is useful for certain DTOs with package-private or private fields that do not expose conventional accessors.

`GraphQlArgumentBinder` supports the `fallBackOnDirectFieldAccess` option; in supported versions, this option can be configured via `AnnotatedControllerConfigurer` or `GraphQlArgumentBinder.Options`.

Direct field access reduces the need for setters, but makes binding dependent on the class's internal field structure. With traditional JavaBeans, explicit setters are generally easier to read and control. Do not enable the fallback just to mask a DTO missing property mappings; choose a consistent DTO model and test it.

## Common errors with setter binding

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| DTO receives all null values | Missing setter or setter/property name does not match input field | Check JavaBean properties and field names in SDL |
| Unable to instantiate DTO | Missing suitable default constructor | Add a no-argument constructor or use constructor binding |
| Nested field fails to bind | Child DTO lacks constructor/setters or has wrong structure | Check each child DTO and collection generic types |
| Type mismatch during binding | Java type is incompatible with scalar or enum | Align SDL, scalar coercion, and DTO |
| Some properties are skipped | Misnamed setter, inaccessible setter, or differing naming convention | Fix setters or configure an appropriate name resolver |
| Binding fails before controller runs | GraphQL coercion or `GraphQlArgumentBinder` throws an error | Distinguish schema input errors from Java binding errors; inspect field path in error |
| Omitted and null treated the same | Property uses a regular nullable type | Use `ArgumentValue<T>` for properties needing distinction |
| Validation does not run | Missing validation starter, `@Valid`, or cascading validation | Check validator and annotations on DTO |

When binding fails, `GraphQlArgumentBinder` accumulates issues into a `BindException` with corresponding field paths instead of reporting only the first error. For example, an error at `items[0].quantity` pinpoints the exact element and property that failed.

## Testing setter binding with GraphQlTester

Test through GraphQL operations to verify the schema, `@Argument`, DTO setters, and controller together. Example:

~~~java
@Test
void bindsJavaBeanInput() {
    graphQlTester.document("""
        mutation CreateBook($input: CreateBookInput!) {
            createBook(input: $input) {
                id
                title
            }
        }
        """)
    .variable("input", Map.of(
            "title", "Spring for GraphQL",
            "authorId", "author-12",
            "pageCount", 320))
    .execute()
    .path("createBook.title")
    .entity(String.class)
    .isEqualTo("Spring for GraphQL");
}
~~~

In a `@GraphQlTest` slice test, mock `BookService` and capture `CreateBookInput` to verify setters received the expected data. Integration tests with a full application context verify schema resources, controller discovery, and runtime wiring together.

You should test:

1. Complete input bound accurately into the JavaBean.
2. Nullable fields omitted or receiving null according to the contract.
3. Nested input objects and lists bound properly.
4. Enums and custom scalars converted to their corresponding Java types.
5. Missing non-null fields or wrong types rejected by GraphQL.
6. A DTO lacking setters or a no-argument constructor producing an identifiable binding error.
7. Bean Validation catching invalid values before calling the service.
8. `ArgumentValue` distinguishing omitted from explicit null.
9. Service not being invoked when coercion or binding fails.

Beyond the response, verify the DTO argument received by the service. That catches property or setter naming bugs even when the resolver still returns a seemingly valid response.

## Hands-on practice

Create a book registration mutation using setter binding:

1. Declare `CreateBookInput` in the SDL with `title`, `authorId`, and `pageCount`.
2. Create a `CreateBookInput` JavaBean class with a no-argument constructor, getters, and setters.
3. Create a `@MutationMapping` receiving `@Argument("input") CreateBookInput`.
4. Add a nested `PublisherInput` inside `CreateBookInput` and bind it via setters.
5. Add a `List<String>` or DTO list for `tags`.
6. Use `@Valid` with Bean Validation to validate `title` and `pageCount`.
7. Write `GraphQlTester` tests for valid input, missing required fields, wrong types, and nested inputs.
8. Try converting the DTO to a Java record to compare constructor binding with setter binding.
9. Add a patch field using `ArgumentValue<String>` and test omitted vs. explicit null.

After completing the practice, explain how the binder instantiates objects, how setters are called to assign properties, and how binding errors differ from GraphQL input validation errors.

## Key takeaways

Setter binding is how `GraphQlArgumentBinder` instantiates a DTO via its default constructor and populates GraphQL values through setters. DTOs typically require a no-argument constructor, JavaBean-compliant setter names, and Java types compatible with schema scalars/enums. Binding applies recursively to nested input objects and collections; `ConversionService` handles type conversion when needed. Use `@Argument` to receive DTOs, `@Valid` to validate constraints, and `ArgumentValue<T>` when you need to distinguish omitted from explicit null. Prefer explicit setters for mutable JavaBeans; use constructor binding for immutable DTOs where appropriate.

## References

- [Spring for GraphQL – Annotated Controllers, @Argument and Argument Binding](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [GraphQlArgumentBinder API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/GraphQlArgumentBinder.html)
- [AnnotatedControllerConfigurer API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/method/annotation/support/AnnotatedControllerConfigurer.html)
