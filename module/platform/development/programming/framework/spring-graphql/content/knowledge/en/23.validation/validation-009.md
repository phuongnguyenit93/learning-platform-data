# Binding Errors by Field Path

When a GraphQL mutation accepts an input object, Spring for GraphQL must convert the GraphQL data into Java parameters for the handler. This process can fail due to incompatible data types, inability to bind constructors or properties, or data violating validation constraints. So that the client knows exactly which field needs fixing, the server should return errors accompanied by the **field path**.

Spring for GraphQL uses **GraphQlArgumentBinder** to bind arguments into records, DTOs, collections, or nested objects. Binding and validation errors are represented via **BindingResult**, typically wrapped in **BindException** when not handled directly in the controller. **FieldError.getField()** provides the path to the invalid property, such as **author.name** or **chapters[0].title**.

This lesson covers how field paths are produced from input objects, how to handle BindException and Errors, how to convert errors into structured GraphQL responses, how to distinguish input field paths from GraphQL response paths, how to handle nested/list inputs, how to normalize error codes, and how to test with GraphQlTester.

## 1. What is a binding error?

Suppose the schema accepts an input to create a book:

~~~graphql
input CreateBookInput {
  title: String!
  pageCount: Int
  author: AuthorInput!
}

input AuthorInput {
  name: String!
  email: String
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
~~~

The Java handler receives a record:

~~~java
public record CreateBookInput(
        String title,
        Integer pageCount,
        AuthorInput author) {
}

public record AuthorInput(
        String name,
        String email) {
}
~~~

The client sends a nested input structure. Spring needs to instantiate CreateBookInput, then instantiate AuthorInput, and assign the corresponding values.

Binding errors can occur when:

- Spring cannot convert a value to the target Java type.
- An object cannot be instantiated via constructor or property binding.
- The data structure is incompatible with the DTO.
- Bean Validation detects an unsatisfied constraint after binding.

For example, pageCount must be greater than 0, yet the client sends a negative value. Or a Java field has an enum/custom type whose value cannot be converted under the current configuration.

A binding error differs from a GraphQL syntax error or a business error. It relates to the step of converting input into Java objects and checking constraints on those objects.

## 2. Where binding sits in GraphQL execution

A request goes through the main steps:

~~~mermaid
flowchart TD
    A[GraphQL document and variables] --> B[Parse document]
    B --> C[Validate against schema]
    C --> D[Coerce GraphQL input]
    D --> E[GraphQlArgumentBinder]
    E --> F[Java record / DTO]
    F --> G[Bean Validation]
    G --> H[Controller handler]
    H --> I[Service and domain logic]
~~~

Each step has its own kind of error:

| Stage | Error example | Handling mechanism |
|---|---|---|
| Parse | Document missing bracket | GraphQL parser |
| Schema validation | Input field does not exist | GraphQL validation |
| Variable coercion | Value does not match GraphQL scalar | GraphQL input coercion |
| Argument binding | Unable to instantiate or convert Java target | GraphQlArgumentBinder / BindException |
| Bean Validation | @NotBlank, @Min, @Email not satisfied | BindingResult / BindException |
| Business validation | Author does not exist, book is duplicated | Service/domain exception or business payload |

Not every invalid input produces a BindException. For example, a client passing a string into an Int! variable is typically rejected by GraphQL during coercion, before the annotated controller is called. @GraphQlExceptionHandler is intended for exceptions raised during field processing; it does not replace the parser or schema validator.

## 3. GraphQlArgumentBinder and BindingResult

With annotated controllers, @Argument tells Spring to extract the current field's argument and bind it to the target Java type.

~~~java
@MutationMapping
public Book createBook(
        @Argument("input") CreateBookInput input) {
    return bookService.create(input);
}
~~~

Spring for GraphQL uses **GraphQlArgumentBinder** to convert input structures into objects. The binder supports constructor binding, property binding, nested objects, and collections.

During binding, Spring collects errors into **BindingResult**. If errors are not handled via an Errors or BindingResult parameter in the handler, the process can throw **BindException** containing those errors.

Important error types:

- **FieldError**: an error attached to a specific property.
- **ObjectError**: an error at the whole-object level, not attached to an individual field.
- **BindingResult**: a collection of field errors and global/object errors.
- **BindException**: an exception carrying BindingResult when binding or validation fails.

To return errors by field path, read **FieldError.getField()** instead of returning only a generic message.

## 4. What is a field path?

A field path is the path to the invalid property inside the Java object being bound.

DTO example:

~~~java
public record CreateBookInput(
        String title,
        AuthorInput author) {
}

public record AuthorInput(
        String name,
        String email) {
}
~~~

If author.name violates @NotBlank, Spring can produce a FieldError with the field path:

~~~text
author.name
~~~

With a nested collection:

~~~java
public record CreateBookInput(
        String title,
        List<ChapterInput> chapters) {
}

public record ChapterInput(
        String title,
        Integer pageNumber) {
}
~~~

If the title of the first element is invalid, the field path looks like:

~~~text
chapters[0].title
~~~

Some examples:

| Input structure | Illustrative field path |
|---|---|
| title | title |
| author.name | author.name |
| chapters[0].title | chapters[0].title |
| addresses[1].postalCode | addresses[1].postalCode |
| settings.timeZone | settings.timeZone |

This is the property path provided by Spring's binding/validation mechanism. With nested DTOs, the path is usually relative to the target object being bound. The outer GraphQL argument name like input does not necessarily become a prefix of FieldError.getField() automatically.

If the application uses @BindParam to map a GraphQL name different from the Java name, inspect the actual path and normalize it to the public field name known to clients. Do not guess or prepend an argument-name prefix without verifying.

## 5. Distinguishing input field path and GraphQL error path

These two kinds of paths serve different purposes and should not be used interchangeably.

**Input field path** identifies the property inside the input object that has an error:

~~~text
author.email
chapters[0].title
~~~

**GraphQL error path** identifies the field in the response tree where the error was recorded. For example, if the createBook mutation raises an error, the GraphQL error's path can be:

~~~json
{
  "path": ["createBook"]
}
~~~

If the client uses an alias:

~~~graphql
mutation {
  result: createBook(input: $input) {
    id
  }
}
~~~

The GraphQL response path uses the alias result, while the input field path still points to the property inside the input such as author.email.

Therefore, place the input path inside a dedicated extension, such as fieldErrors[].fieldPath. Do not write the input path into the GraphQL path attribute, because that attribute has the standard meaning of the field's position in the response.

## 6. Declaring validation for input objects

To check constraints, applications commonly use Jakarta Bean Validation together with the Spring Boot validation starter.

Dependency:

~~~gradle
implementation("org.springframework.boot:spring-boot-starter-validation")
~~~

DTO:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record CreateBookInput(
        @NotBlank String title,
        @NotNull @Min(1) Integer pageCount,
        @Valid AuthorInput author) {
}

public record AuthorInput(
        @NotBlank String name,
        @Email String email) {
}
~~~

Meaning of the annotations:

- @NotBlank: string must contain at least one non-whitespace character.
- @NotNull: value must not be null.
- @Min(1): number must be greater than or equal to 1.
- @Email: value must have a valid email format according to the validator.
- @Valid: triggers recursive validation for nested objects.

In the controller, mark the input with @Valid:

~~~java
@MutationMapping
public Book createBook(
        @Argument("input") @Valid CreateBookInput input) {
    return bookService.create(input);
}
~~~

Spring for GraphQL enables Bean Validation for the annotated argument. If constraints are not met, errors are placed into BindingResult and can be handled in the controller or via exception handling.

### Validation for collections and elements

For list inputs, trigger validation for each element:

~~~java
public record CreateBookInput(
        @NotBlank String title,
        List<@Valid ChapterInput> chapters) {
}

public record ChapterInput(
        @NotBlank String title,
        @Min(1) Integer pageNumber) {
}
~~~

@Valid on the type argument instructs the validator to descend into each ChapterInput. When an element is invalid, the field path can include an index such as chapters[0].pageNumber.

If a non-empty list is needed, add a constraint on the list itself:

~~~java
public record CreateBookInput(
        @NotEmpty List<@Valid ChapterInput> chapters) {
}
~~~

Collection-level constraints and element-level constraints produce different errors. An @NotEmpty error attaches to path chapters; an element's @NotBlank error attaches to a path like chapters[0].title.

## 7. Handling errors locally with Errors or BindingResult

If you want the controller to decide how to return validation errors inside the mutation payload, you can declare an **Errors** parameter immediately after the argument marked for validation.

~~~java
@MutationMapping
public CreateBookPayload createBook(
        @Argument("input") @Valid CreateBookInput input,
        Errors errors) {

    if (errors.hasErrors()) {
        return CreateBookPayload.invalid(
                validationErrorMapper.toUserErrors(errors));
    }

    Book book = bookService.create(input);
    return CreateBookPayload.success(book);
}
~~~

Errors or BindingResult must be placed immediately after the corresponding argument parameter so Spring associates the right error set with that input.

This approach fits when the API intentionally models validation as an expected business result, for example:

~~~graphql
type UserError {
  fieldPath: String!
  code: String!
  message: String!
}

type CreateBookPayload {
  book: Book
  userErrors: [UserError!]!
}
~~~

The controller can convert each FieldError into a UserError. In this case, the resolver still returns a normal payload without needing to emit a top-level GraphQL error just because the user entered bad data.

If the input fails to bind into an object, check how the binder populates Errors in the version you are using. For binding errors thrown as BindException, you can use a centralized exception handler as shown in the next section.

## 8. Handling BindException with @GraphQlExceptionHandler

If the controller does not accept Errors/BindingResult, or you want to standardize binding errors across multiple controllers, you can use **@GraphQlExceptionHandler** inside a controller or **@ControllerAdvice**.

Example global handler:

~~~java
@ControllerAdvice
public class GraphQlBindingExceptionAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleBindException(
            BindException exception,
            DataFetchingEnvironment environment) {

        List<Map<String, Object>> fieldErrors =
                exception.getFieldErrors().stream()
                        .map(this::toFieldError)
                        .toList();

        List<String> objectErrors =
                exception.getGlobalErrors().stream()
                        .map(this::safeMessage)
                        .toList();

        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.BAD_REQUEST)
                .message("Invalid input data")
                .extensions(Map.of(
                        "code", "INPUT_BINDING_FAILED",
                        "fieldErrors", fieldErrors,
                        "objectErrors", objectErrors))
                .build();
    }

    private Map<String, Object> toFieldError(FieldError error) {
        return Map.of(
                "fieldPath", error.getField(),
                "code", toPublicCode(error),
                "message", safeMessage(error));
    }

    private String safeMessage(ObjectError error) {
        String message = error.getDefaultMessage();
        return StringUtils.hasText(message)
                ? message
                : "Invalid value";
    }

    private String toPublicCode(FieldError error) {
        if (error.isBindingFailure()) {
            return "INVALID_TYPE";
        }
        return switch (error.getCode() == null ? "" : error.getCode()) {
            case "NotBlank", "NotNull", "NotEmpty" -> "REQUIRED";
            case "Min", "Max", "Positive", "PositiveOrZero" -> "OUT_OF_RANGE";
            case "Email" -> "INVALID_FORMAT";
            case "Size" -> "INVALID_LENGTH";
            default -> "INVALID_VALUE";
        };
    }
}
~~~

The example illustrates mapping errors into an aggregated GraphQLError. Add the corresponding imports for BindException, BindingResult, FieldError, ObjectError, GraphQLError, GraphqlErrorBuilder, ErrorType, DataFetchingEnvironment, and StringUtils.

Key points:

- exception.getFieldErrors() retrieves property-bound errors.
- error.getField() returns the field path.
- error.getCode() is an internal code generated by Spring/validator; map it to a stable API code.
- error.isBindingFailure() helps distinguish conversion/binding errors from constraint validation.
- getDefaultMessage() provides the message resolved by the message resolver if available.
- exception.getGlobalErrors() retrieves object-level errors.

Do not include error.getRejectedValue() in responses by default. Rejected values can contain passwords, tokens, personal data, or user content that should not be logged or returned.

## 9. Designing GraphQL error extensions for field paths

An error contract can be designed as follows:

~~~json
{
  "data": {
    "createBook": null
  },
  "errors": [
    {
      "message": "Invalid input data",
      "path": ["createBook"],
      "extensions": {
        "classification": "BAD_REQUEST",
        "code": "INPUT_BINDING_FAILED",
        "fieldErrors": [
          {
            "fieldPath": "title",
            "code": "REQUIRED",
            "message": "Title must not be blank"
          },
          {
            "fieldPath": "author.email",
            "code": "INVALID_FORMAT",
            "message": "Email format is invalid"
          },
          {
            "fieldPath": "chapters[0].pageNumber",
            "code": "OUT_OF_RANGE",
            "message": "Page count must be greater than 0"
          }
        ]
      }
    }
  ]
}
~~~

In this response:

- path: ["createBook"] is the GraphQL response path.
- fieldErrors[].fieldPath is the path inside the input object.
- extensions.code is the overall error code.
- fieldErrors[].code is the error code for each field.

Clients can use fieldPath to attach errors to the right input control. Do not require clients to parse messages to find the invalid field.

### One aggregated error or multiple separate errors?

There are two common approaches:

| Approach | Advantages | Notes |
|---|---|---|
| One GraphQLError containing fieldErrors | Groups errors of one input into a single easy-to-handle contract | Client needs to read the extension array |
| Multiple GraphQLErrors, one error per field | Each error has its own message and metadata | Must keep response path aligned with the resolver field and unify error codes |

For validation errors of a single input object, one aggregated error is usually easier to consume. If an application chooses multiple GraphQLErrors, do not put the input property path into GraphQL path; keep it inside an extension such as fieldPath.

## 10. Binding errors in nested objects

Suppose the input has a shipping address:

~~~graphql
input AddressInput {
  street: String!
  city: String!
  postalCode: String
}

input CreateOrderInput {
  customerName: String!
  shippingAddress: AddressInput!
}
~~~

Java DTO:

~~~java
public record CreateOrderInput(
        @NotBlank String customerName,
        @Valid AddressInput shippingAddress) {
}

public record AddressInput(
        @NotBlank String street,
        @NotBlank String city,
        @Pattern(regexp = "^[0-9]{5,10}$") String postalCode) {
}
~~~

If postalCode has an invalid format, the FieldError path can be:

~~~text
shippingAddress.postalCode
~~~

When converting to the response, preserve the nested path so the client identifies the right input control.

If the DTO uses a Java name different from the GraphQL input field, a step is needed to translate from the Java property path to the public field path. You can create a dedicated mapper for defined aliases or binding names; avoid trimming prefixes arbitrarily on strings because that can break nested paths.

## 11. Binding errors in lists and collections

With an input containing a list of elements:

~~~graphql
input LineItemInput {
  productId: ID!
  quantity: Int!
}

input CreateOrderInput {
  items: [LineItemInput!]!
}
~~~

Java:

~~~java
public record CreateOrderInput(
        @NotEmpty List<@Valid LineItemInput> items) {
}

public record LineItemInput(
        @NotBlank String productId,
        @Min(1) Integer quantity) {
}
~~~

If the second element has quantity equal to 0, the field path can be:

~~~text
items[1].quantity
~~~

The index helps the client know which element in the array has an error. If the list is re-sorted or filtered between submission and display, the client should use the index together with a stable item ID when matching items.

Do not strip indices when normalizing paths, because items[0].quantity and items[2].quantity are two distinct errors.

### Nested lists

With multi-level nested structures:

~~~text
shipments[0].packages[2].weight
~~~

The path indicates the first shipment, third package has an invalid weight field. Keep all segments and indices intact so the UI can pinpoint the error accurately.

## 12. When GraphQL field names and Java property names differ

Normally, GraphQL input field names match Java component/property names:

~~~graphql
input CreateBookInput {
  title: String!
}
~~~

~~~java
public record CreateBookInput(String title) {
}
~~~

If the names differ, Spring for GraphQL provides **@BindParam** to specify the input field name used for constructor binding.

Example:

~~~graphql
input CreateBookInput {
  book_title: String!
}
~~~

~~~java
public record CreateBookInput(
        @BindParam("book_title") @NotBlank String title) {
}
~~~

@BindParam helps the binder find the right input key to build constructor arguments. However, the error path may reflect the property name or binding path used by the binder/validator. If the API needs to return the exact name book_title, write a mapping step from the internal path to the public GraphQL name and test that mapping.

Do not assume renaming a constructor parameter automatically changes the field path in every situation.

## 13. Normalizing error codes

Spring and Bean Validation can generate codes like NotBlank, NotNull, typeMismatch, Size, or Email. These are codes meant for internal binding/message resolution.

Client APIs should receive stable codes, for example:

| Internal error | Suggested API code |
|---|---|
| NotBlank | REQUIRED |
| NotNull | REQUIRED |
| NotEmpty | REQUIRED |
| typeMismatch or binding failure | INVALID_TYPE |
| Min, Max, Positive | OUT_OF_RANGE |
| Email, Pattern | INVALID_FORMAT |
| Size | INVALID_LENGTH |
| Unmapped constraint | INVALID_VALUE |

This is only an example API convention. The application needs a consistent mapping across all input types.

Do not send the raw FieldError.getCodes() list to clients because it may contain internal Java object, property, or class names. Convert to stable public codes before serializing.

## 14. Binding errors and business validation

Not every error with a field path is a binding error.

Example:

- author.email is malformed: Bean Validation.
- items[0].quantity is less than 1: Bean Validation.
- input.pageCount cannot be converted to a Java type: binding/conversion.
- authorId has a valid format but does not exist in the database: business validation.
- User is not allowed to use that authorId: authorization.

Business validation often requires domain lookups or checking current state. It should be handled in the service/domain layer and returned as an exception or payload per the API contract.

You can use the same fieldPath structure for business validation when an error relates to an input field, but do not fake a BindException for domain errors. Create an explicit business error type and use a shared mapper if you want the same response format.

## 15. Security when returning binding errors

Errors by field path make it easier for clients to fix data, but that does not mean every piece of information from BindingResult should be exposed.

Avoid putting the following values into GraphQL responses:

- Rejected values that may contain sensitive data.
- Internal class, constructor, or property names not part of the API contract.
- Exception messages from conversion services if they leak implementation details.
- Stack traces or causes.
- Table names, SQL statements, or database details.

Instead:

- Return only fieldPath, public error codes, and controlled messages.
- Use friendly messages containing no secret values.
- Log details on the server with an appropriate correlation ID.
- Do not log raw variables or rejected values unless necessary.
- Check permissions before revealing whether a field/resource exists.

## 16. Testing field paths with GraphQlTester

GraphQlTester helps verify GraphQL responses when binding or validation fails.

Mutation query example:

~~~graphql
mutation {
  createBook(input: {
    title: " "
    pageCount: 0
    author: {
      name: " "
      email: "invalid"
    }
  }) {
    id
  }
}
~~~

Basic test:

~~~java
@SpringBootTest
class BookBindingErrorTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void shouldReturnBindingError() {
        GraphQlTester.Response response = graphQlTester.document("""
                mutation {
                    createBook(input: {
                        title: " "
                        pageCount: 0
                        author: {
                            name: " "
                            email: "invalid"
                        }
                    }) {
                        id
                    }
                }
                """)
            .execute();

        response.errors()
                .expect()
                .message("Invalid input data")
                .verify();
    }
}
~~~

To assert the contents of fieldErrors, you can use response.errors().satisfy(...) and inspect the extensions of each response error according to the GraphQlTester API of your version. The test goal is to verify that paths like title, pageCount, author.name, and author.email appear accurately, not merely that an error exists.

Consider adding tests for:

1. Scalar coercion errors rejected by GraphQL before the resolver.
2. FieldErrors on top-level properties.
3. FieldErrors in nested objects.
4. FieldErrors in list elements with indices.
5. Global/object errors without a field path.
6. Binding failures and Bean Validation failures having distinct API codes.
7. @BindParam mapping to the exact public field name.
8. Errors/BindingResult received immediately after the corresponding argument.
9. @GraphQlExceptionHandler returning GraphQLError with the right response path.
10. Input field path placed in extensions without overwriting GraphQL response path.
11. Rejected values and stack traces absent from the response.
12. Business validation distinguished from binding validation.

If you want to test the mapper from BindingResult to field error DTOs separately, you can write unit tests for the mapper without running GraphQL execution.

## 17. Common mistakes when mapping binding errors by path

| Symptom | Possible cause | How to fix |
|---|---|---|
| Client receives only one generic message | Not reading BindingResult.getFieldErrors() | Return list of field errors in extensions or payload |
| Path missing nested levels | Taking only the last field name | Use the full FieldError.getField() |
| List error does not point out element | Stripping index from path | Preserve the items[0].field format |
| Client misinterprets GraphQL path | Writing input path into GraphQLError.path | Put input path in extensions.fieldErrors[].fieldPath |
| BindException never seen | Error occurred at GraphQL coercion before the binder | Identify the right error stage |
| Error code changes after refactoring | Sending raw Spring validation codes | Map to stable API codes |
| User data leaked | Returning rejectedValue | Do not serialize rejected values |
| Nested validation does not run | Missing @Valid on object or collection element | Enable cascade validation |
| Path name differs from SDL | DTO uses different property name or @BindParam | Map path to public GraphQL name |
| Domain error treated as binding | Reusing vague exceptions | Classify binding, validation, and business errors |

## 18. Workflow for implementing binding errors by field path

When designing input validation for GraphQL:

1. Declare input objects in SDL with clear scalars, lists, and nested inputs.
2. Create Java records/DTOs whose property names match the input fields.
3. Use @BindParam if constructor/property names differ from GraphQL names.
4. Add Jakarta Validation constraints for fields and objects to validate.
5. Use @Valid for nested objects and each collection element.
6. Mark the argument with @Argument and @Valid.
7. Choose Errors/BindingResult if the mutation needs to return validation in the payload.
8. If letting exceptions propagate, handle BindException with @GraphQlExceptionHandler or an exception resolver.
9. Use FieldError.getField() to preserve full nested paths and list indices.
10. Map internal codes to stable API error codes.
11. Put the input field path in a dedicated extension, not confused with GraphQL response path.
12. Do not return rejected values, stack traces, or internal details.
13. Test coercion, binding, nested/list validation, and business errors separately.

Binding errors by field path help clients know exactly which property in the input needs fixing. Spring for GraphQL provides GraphQlArgumentBinder and BindingResult to collect errors; FieldError.getField() preserves nested property paths and collection indices. When converting errors into GraphQL responses, distinguish input field paths from response paths, normalize error codes, and return only safe messages. For mutations that need to return validation errors as business results, use Errors/BindingResult; for centralized error handling, use @GraphQlExceptionHandler. Test nested objects, lists, and custom-bound field names so the error contract stays consistent.
