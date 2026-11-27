# Validation groups

## Objectives

After this lesson, you will be able to:

- Explain why a DTO may need multiple validation rule sets.
- Declare validation groups using interfaces and attach constraints to each group.
- Select groups for each mutation using Spring @Validated.
- Combine groups with @Valid, nested validation, and group conversion.
- Use group sequences to control validation order.
- Distinguish validation groups from GraphQL SDL validation and business checks.
- Test validation groups in Spring for GraphQL.

## What problem do validation groups solve?

Bean Validation allows declaring constraints on DTOs with annotations such as @NotNull, @NotBlank, @Size, and @Positive. Within an API, the same data structure can be used across multiple use cases that require different rules.

For example, when creating a product, the client does not yet have an ID, so the server generates a new ID. When updating a product, the ID must be provided. Product price is required upon creation, yet may be kept unchanged during a partial update.

If every constraint belongs to the same default group, it is difficult to express differences between operations. Validation groups allow grouping constraints into named groups, then instructing the validator to run one or more groups depending on the use case.

A group is a Java interface. The interface contains no logic; it simply identifies a set of constraints to execute.

## Declaring groups

Create separate interfaces for use cases:

~~~java
import jakarta.validation.groups.Default;

public interface OnCreate extends Default {
}

public interface OnUpdate extends Default {
}
~~~

In this example, both groups extend Default. When the validator runs OnCreate or OnUpdate, constraints belonging to Default are also applied. This is useful when a DTO has common rules shared across all operations.

If you do not want to include default constraints, you can declare standalone groups without extending Default. In that case, constraints that do not specify groups still belong to Default and will not run automatically when requesting only OnCreate or OnUpdate.

This is a key point to remember: when specifying a custom group, Bean Validation does not automatically run all Default constraints. Deliberately choose one of two approaches:

- Have the custom group extend Default if you want to include common constraints.
- Explicitly assign the constraints that need to run to the right group.

## Attaching constraints to groups

Example of an input used for both product creation and update operations:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Null;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;

public record ProductInput(
        @Null(groups = OnCreate.class)
        @NotNull(groups = OnUpdate.class)
        String id,

        @NotBlank
        @Size(max = 120)
        String name,

        @NotNull(groups = OnCreate.class)
        @Positive
        BigDecimal price) {
}
~~~

Meaning:

- id must be null when creating because the server is responsible for assigning the ID.
- id must have a value when updating.
- name must not be blank and must be at most 120 characters in both operations because OnCreate and OnUpdate extend Default.
- price is required when creating.
- If price is provided when updating, the value must still be greater than 0. Because OnUpdate extends Default, @Positive also applies.

Data types in the DTO should be reference types such as String, Long, and BigDecimal when you need to distinguish a missing value from a valid value. Avoid using int or boolean for inputs that may be omitted by the client, because primitive types cannot represent null.

The example above describes an update rule where name is still required while price can be omitted. If a use case allows updating any field optionally, clearly design the semantics of omitted fields and explicit null; validation groups alone do not distinguish between those two states.

## Selecting groups in Spring for GraphQL with @Validated

Spring for GraphQL supports Bean Validation on annotated controller methods. When a Validator bean exists in the application context, AnnotatedControllerConfigurer can check parameters marked with @Valid or Spring's @Validated before calling the method.

Spring @Validated lets you specify which group to run:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;
import org.springframework.validation.annotation.Validated;

@Controller
public class ProductMutationController {

    private final ProductService productService;

    public ProductMutationController(ProductService productService) {
        this.productService = productService;
    }

    @MutationMapping
    public Product createProduct(
            @Argument("input")
            @Validated(OnCreate.class)
            ProductInput input) {

        return productService.create(input);
    }

    @MutationMapping
    public Product updateProduct(
            @Argument("input")
            @Validated(OnUpdate.class)
            ProductInput input) {

        return productService.update(input);
    }
}
~~~

Both mutations use the same ProductInput but select different groups. When createProduct is called, OnCreate and Default constraints run. When updateProduct is called, OnUpdate and Default constraints run.

If the input is invalid, validation fails before the controller method is called. Therefore, the service should not receive a DTO that already violates constraints enforced at this boundary.

When custom groups are not needed, @Valid is a concise way to run validation under the Default group:

~~~java
@MutationMapping
public Product createProduct(
        @Argument("input") @Valid ProductInput input) {
    return productService.create(input);
}
~~~

Use @Validated when selecting specific groups is needed. You do not need to place both @Valid and @Validated on the same parameter; @Validated already marks validation while specifying the group.

## Configuring Bean Validation

With Spring Boot, add the validation starter if the application does not have it yet:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

When a Bean Validation provider is present and a Validator bean is registered, Spring for GraphQL can detect the validator and enable validation for annotated controllers. Spring Boot typically auto-configures the validator when the starter and compatible provider are on the classpath.

If the application configures GraphQlSource or AnnotatedControllerConfigurer manually, verify that a Validator is supplied to the configurer. Simply adding annotations to DTOs does not mean validation runs automatically if the application has not configured a validator.

Inspect the dependency tree when multiple Jakarta Validation versions or different providers exist. Spring Boot manages compatible versions; avoid independently adding an incompatible Hibernate Validator version.

## GraphQL SDL and validation groups are two different layers

The GraphQL engine checks the operation, data types, arguments, and nullability before calling the resolver. Bean Validation runs after GraphQL has bound arguments into Java objects.

SDL example:

~~~graphql
scalar BigDecimal

input ProductInput {
  id: ID
  name: String
  price: BigDecimal
}

type Mutation {
  createProduct(input: ProductInput!): Product!
  updateProduct(input: ProductInput!): Product!
}
~~~

The fields id, name, and price are all nullable in SDL. This allows the same input shape to be sent to both mutations. Validation groups decide which fields are required in each use case.

If you declare name: String! in SDL, GraphQL requires name for every mutation using ProductInput. Validation groups cannot make that field optional in another mutation.

Conversely, if SDL declares name: String, GraphQL allows it to be omitted or null. Bean Validation can require name using @NotBlank in the appropriate groups.

| Validation layer | Timing | Example |
| --- | --- | --- |
| GraphQL parsing and validation | Before resolver | Non-existent field, wrong argument type |
| GraphQL input coercion | Before resolver | ID or BigDecimal cannot be converted |
| Bean Validation group | After binding input, before calling method | id must be null on create, must be present on update |
| Business validation | Inside service/domain | SKU already in use, user does not own product |

Do not use validation groups to replace business checks or authorization. Constraints on DTOs typically check local data; database state and access permissions must be verified in the service or security layer.

## Nested validation and @Valid

When a DTO contains another input object, mark @Valid to enable cascade validation:

~~~java
public record AddressInput(
        @NotBlank(groups = OnCreate.class)
        String street,

        @NotBlank(groups = OnCreate.class)
        String city) {
}

public record CreateOrderInput(
        @NotBlank(groups = OnCreate.class)
        String customerId,

        @NotNull(groups = OnCreate.class)
        @Valid
        AddressInput shippingAddress) {
}
~~~

If the controller selects OnCreate:

~~~java
@MutationMapping
public Order createOrder(
        @Argument("input")
        @Validated(OnCreate.class)
        CreateOrderInput input) {

    return orderService.create(input);
}
~~~

The group is propagated down to nested objects during cascade validation. As a result, constraints belonging to OnCreate on AddressInput are also checked.

For collections, you can cascade validation to each element:

~~~java
public record CreateOrderInput(
        @NotEmpty(groups = OnCreate.class)
        List<@Valid OrderLineInput> items) {
}
~~~

Each OrderLineInput is validated under the active group. If the list could contain nulls, add appropriate constraints such as @NotNull on elements or use generic type annotations to reject null elements.

## Converting groups for nested objects with @ConvertGroup

Sometimes a child object has its own rule set and does not share the same group names as the parent object. In that case, @ConvertGroup allows changing the group at the cascade validation boundary.

Example:

~~~java
public interface AddressCreate {
}

public record AddressInput(
        @NotBlank(groups = AddressCreate.class)
        String street,

        @NotBlank(groups = AddressCreate.class)
        String city) {
}

public record CreateOrderInput(
        @NotNull(groups = OnCreate.class)
        @Valid
        @ConvertGroup(
                from = OnCreate.class,
                to = AddressCreate.class)
        AddressInput shippingAddress) {
}
~~~

When validation runs OnCreate on CreateOrderInput, cascading to shippingAddress converts the OnCreate group into AddressCreate. Constraints on AddressInput belonging to AddressCreate are executed.

@ConvertGroup only takes effect alongside cascade validation, meaning @Valid is required on the association. You can use @ConvertGroup.List when mapping multiple different groups.

Do not create group conversions if parent and child share the same rule set. Use group conversion when two input domains truly have distinct validation vocabularies.

## Group inheritance and group sequence

Group inheritance and group sequences address two different needs:

- Group inheritance lets a group include constraints from a parent group.
- Group sequence controls the execution order of groups and stops at the first group with errors.

### Group inheritance

In earlier examples, OnCreate and OnUpdate extended Default. Therefore, constraints without declared groups run when either of these two groups is selected.

You can build inheriting groups when a use case extends common rules:

~~~java
public interface BasicChecks {
}

public interface CreateChecks extends BasicChecks {
}
~~~

When running CreateChecks, constraints belonging to BasicChecks also run. This is helpful when multiple use cases share a common baseline rule set.

### Group sequence

There are cases where you want basic checks to run first, and only run expensive business checks after the data has passed the basic step:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import java.math.BigDecimal;

public interface BasicChecks {
}

public interface BusinessChecks {
}

public record ProductCreateInput(
        @NotBlank(groups = BasicChecks.class)
        String name,

        @NotNull(groups = BasicChecks.class)
        @Positive(groups = BasicChecks.class)
        BigDecimal price,

        @NotBlank(groups = BusinessChecks.class)
        @Pattern(regexp = "[A-Z]{3}-[0-9]{6}", groups = BusinessChecks.class)
        String sku) {
}

@GroupSequence({
        BasicChecks.class,
        BusinessChecks.class
})
public interface ProductCreateChecks {
}
~~~

When the controller uses:

~~~java
@MutationMapping
public Product createProduct(
        @Argument("input")
        @Validated(ProductCreateChecks.class)
        ProductCreateInput input) {

    return productService.create(input);
}
~~~

Bean Validation runs BasicChecks first. If this group has violations, BusinessChecks does not run. If there are no errors, the validator proceeds to the next group.

A group sequence must declare groups in the desired order. Do not include the sequence interface itself in its own group list. If Default needs to be included, explicitly include Default.class in the sequence.

Example:

~~~java
@GroupSequence({
        Default.class,
        BasicChecks.class,
        BusinessChecks.class
})
public interface CompleteProductChecks {
}
~~~

Sequences fit when validation steps have a clear order. Avoid using sequences merely to combine multiple groups if ordering or short-circuiting is not needed.

## Validation groups do not automatically distinguish omitted and explicit null

With GraphQL inputs, nullable fields can be omitted or explicitly sent with a null value. A regular nullable Java property may receive null in both cases.

Validation groups decide which constraints run; they do not inherently indicate whether the client omitted the field or sent null. For partial update mutations, if the two states carry different meanings, use ArgumentValue<T>:

~~~java
import org.springframework.graphql.data.ArgumentValue;

public record PatchProductInput(
        ArgumentValue<String> name) {
}
~~~

When handling:

~~~java
if (!input.name().isOmitted()) {
    String name = input.name().value();
    if (name != null && name.isBlank()) {
        throw new InvalidProductNameException();
    }
    product.rename(name);
}
~~~

This example illustrates two mechanisms with separate responsibilities: groups select constraints for the update operation; ArgumentValue preserves the omitted state so the service decides whether to change the field. If you want to use Bean Validation for the value inside the wrapper, verify container value extraction support in your provider and version; otherwise, check conditionally after determining the field was sent.

If create and update have very different structures, two separate DTOs are usually easier to understand than one large DTO with too many groups. Validation groups fit best when the data structure is mostly the same while a few rules vary by use case.

## Handling validation errors in GraphQL

When validation fails, the annotated controller method is not called and Spring for GraphQL raises a validation exception, typically ConstraintViolationException. The exception is processed through the exception resolution chain to become a GraphQL error.

You can use @GraphQlExceptionHandler in a controller or a shared DataFetcherExceptionResolver to standardize errors. Example:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.stereotype.Controller;
import jakarta.validation.ConstraintViolationException;

import java.util.Map;

@Controller
public class ProductMutationController {

    @GraphQlExceptionHandler
    public GraphQLError handleValidation(
            ConstraintViolationException exception,
            GraphqlErrorBuilder<?> errorBuilder) {

        return errorBuilder
                .message("Invalid input data")
                .errorType(ErrorType.BAD_REQUEST)
                .extensions(Map.of("code", "VALIDATION_FAILED"))
                .build();
    }
}
~~~

This is an illustrative handler example; if per-field errors need to be returned, convert the constraint violations into a filtered and controlled fieldErrors list. Do not send rejected values or default messages if they may contain sensitive data.

@GraphQlExceptionHandler in a controller applies to exceptions raised from handler methods belonging to that controller. If you want the same error contract across multiple controllers, consider a shared handler or DataFetcherExceptionResolver.

## Testing validation groups

Test at two levels:

1. Unit tests for DTOs and groups to verify which constraints run.
2. GraphQL tests to verify mutations select the right group, errors are converted into responses, and the service is not called when input is invalid.

Unit test example:

~~~java
Validator validator = Validation.buildDefaultValidatorFactory()
        .getValidator();

ProductInput input = new ProductInput(
        null,
        "Mechanical Keyboard",
        null);

Set<ConstraintViolation<ProductInput>> createViolations =
        validator.validate(input, OnCreate.class);

Set<ConstraintViolation<ProductInput>> updateViolations =
        validator.validate(input, OnUpdate.class);
~~~

With the input above:

- OnCreate must report an error because price is required.
- OnUpdate must report an error because id is required.
- Default constraints such as @NotBlank and @Size still run because both groups extend Default.

GraphQlTester example for a mutation:

~~~java
graphQlTester.document("""
        mutation CreateProduct($input: ProductInput!) {
            createProduct(input: $input) {
                id
            }
        }
        """)
    .variable("input", Map.of(
            "name", "Mechanical Keyboard"))
    .execute()
    .errors()
    .satisfy(errors -> {
        assertThat(errors).isNotEmpty();
    });
~~~

In actual tests, also assert the error code VALIDATION_FAILED and verify ProductService.create is not called. A similar test for update should verify that missing id is rejected, while OnCreate-specific rules are not mistakenly applied.

Cases to include:

- Valid create succeeds and calls the right service.
- Create missing price is rejected before calling the service.
- Create sending a client-supplied id is rejected.
- Update missing id is rejected.
- Update with id and valid data is accepted.
- Default constraints run in both groups if groups extend Default.
- Constraints belonging only to OnCreate do not run in OnUpdate and vice versa.
- Nested objects cascade under the appropriate group.
- Group conversion switches to the right group for child objects.
- Group sequence stops when the first group has violations.

## Common errors

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| Default constraints do not run | Custom group does not extend Default | Have the group extend Default or assign constraints explicitly to the group |
| Create constraints also run on update | Constraints assigned to the wrong group or controller selected wrong group | Check groups on annotations and @Validated |
| Child object constraints do not run | Missing @Valid on nested field | Enable cascade validation |
| Parent object's group does not match child object | Two domains use different groups | Use @ConvertGroup at the association |
| Group sequence continues running next step after previous step fails | Sequence declared incorrectly or validating groups separately | Invoke the sequence group and check order |
| SDL rejects before Bean Validation runs | Field is declared non-null or wrong type | Adjust SDL if requiredness depends on the use case |
| Update treats omitted and null the same | Only regular nullable properties are used | Use ArgumentValue when distinguishing is needed |
| Validation does not run | Missing Validator bean or parameter lacks @Valid/@Validated | Check validation starter and annotated controller configuration |
| Service still runs despite invalid input | Validation not enabled or test mocks wrong boundary | Check validator, groups, and verify service invocation |
| One DTO has too many groups | Use cases have significantly different structures | Split DTOs by use case to reduce complexity |

## Comprehensive practice

Build two mutations createProduct and updateProduct:

1. Declare ProductInput with id, name, and price.
2. Create OnCreate and OnUpdate; have them extend Default to share common constraints.
3. Use @Null(groups = OnCreate.class) and @NotNull(groups = OnUpdate.class) for id.
4. Use @NotBlank and @Size for name.
5. Use @NotNull(groups = OnCreate.class) and @Positive for price.
6. Place @Validated(OnCreate.class) on the createProduct parameter.
7. Place @Validated(OnUpdate.class) on the updateProduct parameter.
8. Write a nested DTO with @Valid and try converting groups using @ConvertGroup.
9. Create a group sequence consisting of BasicChecks and BusinessChecks.
10. Test each mutation with Validator and GraphQlTester, and verify the service is not called when validation fails.

After completing it, explain why GraphQL SDL still needs to allow nullable fields if requiredness changes per mutation, why groups do not replace business validation, and when to split DTOs.

## Key takeaways

Validation groups allow applying different constraint sets for each use case. Declare groups via interfaces, attach constraints via the groups attribute, and select groups in annotated controllers using Spring @Validated. Remember that constraints without a specified group belong to Default; custom groups only run Default if they inherit from or are sequenced with Default. Use @Valid to cascade, @ConvertGroup to switch groups for child objects, and @GroupSequence when validation ordering is needed. GraphQL SDL still checks types and nullability before Bean Validation; services remain responsible for business rules and authorization. Use ArgumentValue when needing to distinguish omitted fields from explicit null, and split DTOs if use cases differ too much.

## References

- [Spring for GraphQL – Annotated Controllers, Validation](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Jakarta Bean Validation – Specification](https://jakarta.ee/specifications/bean-validation/)
- [Spring Framework – Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
