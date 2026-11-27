# Building Mutations with Input Validation

A well-designed mutation must protect data right at the API boundary, check business rules before writing data, and return clear enough errors for the client to fix the request. With Spring for GraphQL, we combine type constraints in the GraphQL SDL, Jakarta Bean Validation on Java inputs, and business checks in the service.

This hands-on practice builds a `createMember` mutation that takes a name, email, and age. The mutation only calls the service when the data is valid. The examples use Java records and the `jakarta.validation` namespace, suitable for Spring Boot 3+ applications with Spring for GraphQL.

## 1. Identifying the Validation Layers

The processing flow has four layers, each solving a different class of problems:

1. **GraphQL SDL** validates the structure of the operation: whether the field exists, whether data types match, and whether required fields are missing or receive `null`.
2. **Bean Validation** validates the content of individual values: strings are not blank, emails match the format, and age falls within bounds.
3. **Service/domain** checks rules that depend on business logic or current state: whether the email is already taken, or whether the caller has permission to create a member in this group.
4. **Database** enforces final constraints such as unique constraints and foreign keys. Pre-checking in the service provides friendly messages; database constraints remain necessary to handle concurrent requests.

Do not cram all four layers into the resolver. The resolver receives the bound and structurally valid input, then delegates to the service.

## 2. Adding Required Dependencies

With Gradle and Spring Boot dependency management, add the following starters; let Spring Boot's BOM manage compatible versions:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-validation")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.graphql:spring-graphql-test")
}
```

`spring-boot-starter-validation` brings a Jakarta Bean Validation provider into the application. Without a provider, annotations like `@NotBlank` still compile when the API is present, but there is no runtime engine to enforce them.

## 3. Declaring Input and Mutation in SDL

Create or update the schema at `src/main/resources/graphql/schema.graphqls`:

```graphql
type Query {
    member(id: ID!): Member
}

type Member {
    id: ID!
    fullName: String!
    email: String!
    age: Int!
}

input CreateMemberInput {
    fullName: String!
    email: String!
    age: Int!
}

type Mutation {
    createMember(input: CreateMemberInput!): Member
}
```

`input` is the type reserved for client-submitted data; do not use the output type `Member` as an input. `CreateMemberInput!` requires the client to pass the input object, and the `!` on each field requires that field's value not to be missing or `null`.

SDL cannot express all content rules. For example, `email: String!` still accepts an empty string, and `age: Int!` still accepts a negative number. Those conditions will be checked using Bean Validation.

In this example, the mutation field returns a nullable `Member`. When the resolver raises a validation error, GraphQL can return `createMember: null` alongside an entry in `errors`. If you change the return type to `Member!`, an error on this field can propagate null up to the parent level according to GraphQL's non-null rules.

## 4. Creating the Input Model with Jakarta Bean Validation

Create the `CreateMemberInput` record:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateMemberInput(
        @NotBlank(message = "Full name must not be blank")
        @Size(max = 100, message = "Full name must not exceed 100 characters")
        String fullName,

        @NotBlank(message = "Email must not be blank")
        @Email(message = "Email format is invalid")
        @Size(max = 254, message = "Email must not exceed 254 characters")
        String email,

        @NotNull(message = "Age is required")
        @Min(value = 18, message = "Member must be at least 18 years old")
        @Max(value = 120, message = "Age must not be greater than 120")
        Integer age
) {}
```

A few points to distinguish:

- `@NotNull` only rejects `null`; it does not reject an empty string.
- `@NotBlank` rejects `null`, empty strings, and whitespace-only strings. This annotation is intended for `CharSequence`.
- `@Email` checks basic format. It does not verify that the mailbox exists, that the user owns the mailbox, or that the email has not already been registered.
- `@Size` limits length; it does not replace `@NotBlank`.
- Use `Integer` instead of `int` so the Java model can still represent `null`, making `@NotNull` meaningful when the input is invoked from another code path or if the SDL changes.

The `18..120` range is purely an illustrative rule. In a real application, choose bounds based on your domain requirements and data policy.

## 5. Attaching Validation to the `@Argument` Parameter

The resolver uses `@MutationMapping` to map to the `createMember` field in SDL:

```java
import jakarta.validation.Valid;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

@Controller
public class MemberGraphQlController {

    private final MemberService memberService;

    public MemberGraphQlController(MemberService memberService) {
        this.memberService = memberService;
    }

    @MutationMapping
    public Member createMember(
            @Argument("input") @Valid CreateMemberInput input) {
        return memberService.create(input);
    }
}
```

`@Argument("input")` extracts the object from the `input` argument of the mutation. `@Valid` tells Spring for GraphQL to run Bean Validation on the bound object. If any constraint is violated, resolver invocation stops and Spring GraphQL raises a `BindException`; `memberService.create` is not called.

Placing constraints on the input model keeps formatting rules attached to the input data and allows them to be tested independently. There is no need to manually invoke `Validator.validate` in each resolver when using this `@Valid` mechanism.

## 6. Converting Validation Errors into Clear GraphQL Errors

You can centralize error handling in `@ControllerAdvice` so resolvers share a consistent response format:

```java
import graphql.GraphqlErrorBuilder;
import graphql.GraphQLError;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.validation.BindException;
import org.springframework.web.bind.annotation.ControllerAdvice;

import java.util.stream.Collectors;

@ControllerAdvice
public class GraphQlValidationAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleBindException(BindException exception) {
        String details = exception.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> error.getField() + ": " + error.getDefaultMessage())
                .distinct()
                .collect(Collectors.joining("; "));

        return GraphqlErrorBuilder.newError()
                .errorType(ErrorType.BAD_REQUEST)
                .message("Invalid input data: " + details)
                .build();
    }
}
```

`@GraphQlExceptionHandler` enables Spring GraphQL to convert exceptions thrown during data fetching into a `GraphQLError`. `ErrorType.BAD_REQUEST` classifies input errors; the message only includes field names and the defined constraint messages. Do not include stack traces, SQL statements, configuration details, or sensitive data in messages sent to the client.

GraphQL typically represents execution errors in the `errors` array of the response. Do not assume every resolver error will be represented by a distinct HTTP status; clients must read both `data` and `errors` per the GraphQL specification.

Errors caused by GraphQL failing to parse the document, wrong field names, or wrong scalar types are usually caught before the resolver runs. Those errors are not `BindException` from Bean Validation and do not go through this handler.

## 7. Placing Business Rules in the Service

Bean Validation is suitable for standalone rules on the input. Rules requiring repository access, system state, or user permissions belong in the service/domain layer:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Locale;

@Service
public class MemberService {

    private final MemberRepository memberRepository;

    public MemberService(MemberRepository memberRepository) {
        this.memberRepository = memberRepository;
    }

    @Transactional
    public Member create(CreateMemberInput input) {
        if (memberRepository.existsByEmailIgnoreCase(input.email())) {
            throw new DuplicateEmailException("Email is already in use");
        }

        Member member = new Member(
                null,
                input.fullName().trim(),
                input.email().trim().toLowerCase(Locale.ROOT),
                input.age()
        );

        return memberRepository.save(member);
    }
}
```

This illustrates layering; `Member`, `MemberRepository`, and `DuplicateEmailException` are application domain/repository types that must be defined accordingly. The unique email rule must also have a unique constraint in the database. Two concurrent requests can both pass `existsByEmailIgnoreCase`, so a pre-check query cannot replace storage constraints and constraint-violation handling.

If you want to return business errors such as a duplicate email, map `DuplicateEmailException` to a GraphQL error with a stable code or return a mutation payload containing `userErrors`. Do not disguise this error as a Bean Validation error.

## 8. Sending the Mutation from a GraphQL Client

Use GraphQL variables to separate the operation from the data:

```graphql
mutation CreateMember($input: CreateMemberInput!) {
    createMember(input: $input) {
        id
        fullName
        email
        age
    }
}
```

Valid variables:

```json
{
  "input": {
    "fullName": "Nguyen Minh An",
    "email": "an@example.com",
    "age": 24
  }
}
```

When the request is valid, GraphQL invokes the resolver, Spring binds the input, Bean Validation checks the constraints, and then the service creates the member and the resolver returns the `Member` object.

## 9. Observing the Response When Input Is Invalid

Try sending a malformed email and an age below the limit:

```json
{
  "input": {
    "fullName": "An",
    "email": "not-an-email",
    "age": 16
  }
}
```

With the handler in section 6, the response has the following illustrative shape:

```json
{
  "data": {
    "createMember": null
  },
  "errors": [
    {
      "message": "Invalid input data: email: Email format is invalid; age: Member must be at least 18 years old",
      "extensions": {
        "classification": "BAD_REQUEST"
      },
      "path": ["createMember"]
    }
  ]
}
```

This is an illustrative shape; the order of field errors and extensions depends on library versions and configuration. What to verify is that the response contains an appropriately classified error, the mutation field does not return success data, and the service does not write data.

## 10. Testing with GraphQlTester

Unit tests for constraints are useful, but integration tests via `GraphQlTester` also verify that SDL, argument binding, `@Valid`, and the exception handler work together properly.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.context.annotation.Import;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verifyNoInteractions;

@GraphQlTest(MemberGraphQlController.class)
@Import(GraphQlValidationAdvice.class)
class MemberGraphQlControllerTest {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    MemberService memberService;

    @Test
    void rejectsInvalidEmailAndAgeBeforeCallingService() {
        graphQlTester.document("""
                mutation {
                    createMember(input: {
                        fullName: "An"
                        email: "not-an-email"
                        age: 16
                    }) {
                        id
                    }
                }
                """)
                .execute()
                .errors()
                .satisfy(errors -> assertThat(errors)
                        .anyMatch(error -> error.getMessage().contains("email")
                                && error.getMessage().contains("age")));

        verifyNoInteractions(memberService);
    }
}
```

`@MockitoBean` is available in Spring Framework 6.2 and later. For older Spring Boot/Spring Framework versions, use the corresponding mock bean mechanism of your project version, such as `@MockBean` if still supported. If the test slice does not automatically locate the schema, verify that the schema is under `src/main/resources/graphql/` or check the application's schema location configuration.

You should add tests for: blank name, name exceeding 100 characters, blank email, age 17, age 18, age over 120, and valid input. For the valid case, mock the service to return a `Member` and assert that the response contains the expected data.

## 11. Distinguishing SDL Errors from Bean Validation Errors

The two groups of errors occur at different stages:

| Scenario | Where Detected | Does the Resolver Run? |
|---|---|---|
| Missing `input` in mutation | GraphQL operation validation | No |
| `age` receives a string instead of `Int` | GraphQL scalar validation/coercion | No |
| `email` receives `null` when SDL declares `String!` | GraphQL input validation | No |
| `email` is an empty string | `@NotBlank` | Binding starts; service is not called |
| `email` has invalid format | `@Email` | Binding starts; service is not called |
| `age` is less than 18 | `@Min(18)` | Binding starts; service is not called |
| Email is already used by another account | Service/domain and database | Yes |

If GraphQL rejects the request before the resolver, the `BindException` handler in section 6 does not handle that error. Check the GraphQL response and test the exact layer responsible for each scenario.

## 12. Validating Nested Inputs

When an input contains a child object, place `@Valid` on the nested component so validation cascades into that object:

```java
public record AddressInput(
        @NotBlank(message = "City must not be blank")
        String city,

        @NotBlank(message = "Country code must not be blank")
        @Size(min = 2, max = 2, message = "Country code must be 2 characters")
        String countryCode
) {}

public record CreateMemberInput(
        @NotBlank @Size(max = 100) String fullName,
        @NotBlank @Email @Size(max = 254) String email,
        @NotNull @Min(18) @Max(120) Integer age,
        @NotNull @Valid AddressInput address
) {}
```

The corresponding SDL needs `AddressInput` and the field `address: AddressInput!`. `@Valid` triggers constraint checking on `AddressInput`; without this annotation, constraints on `city` and `countryCode` may not be evaluated when validating the parent object. For collection inputs, use `List<...>` and cascade validation for each element according to the model structure.

## 13. Keeping Authorization Separate from Validation

Valid input does not mean the caller is permitted to execute the mutation. For example, a well-formed `groupId` may still belong to a group that the current user is not allowed to manage. Obtain identity from the security context, enforce permissions at the appropriate layer, and verify access to individual resources in the service/domain layer.

Do not accept `ownerId`, `createdBy`, or privileged roles from the client and trust those values directly. If an API requires an ID sent by the client, the service must verify that the caller is authorized to act on that resource. Validation addresses data quality; authorization addresses permission to perform an action.

## 14. Common Implementation Mistakes

- **Declaring `String!` and assuming the string always has content.** `!` only excludes `null`; add `@NotBlank` to reject empty or whitespace-only strings.
- **Forgetting `@Valid` on `@Argument`.** Constraints may be fully declared yet never triggered on the resolver execution path.
- **Using `@NotBlank` on numbers.** Choose constraints suited to the data type, such as `@NotNull`, `@Min`, and `@Max` for `Integer`.
- **Putting database queries inside custom validators for everything.** This easily couples validation to infrastructure and does not solve race conditions. State-dependent rules usually belong in the service/domain layer.
- **Validating only on the client.** Clients can be bypassed or spoofed; the server must validate on its own.
- **Returning raw exceptions to the client.** Convert exceptions into GraphQL errors with safe messages and stable classification codes.
- **Assuming every error goes through `BindException`.** Parse errors, schema validation, scalar coercion, authorization, and business errors originate from different places; handle each according to its type.
- **Using validation instead of database constraints.** Pre-save checks do not protect data against concurrent requests or other write paths.

## 15. Completion Exercises

Starting from the `createMember` mutation, complete the following requirements:

1. Add a `phoneNumber` field with a non-blank rule and reasonable length limits. Choose constraints appropriate for the phone number format your system supports.
2. Add `AddressInput` and cascade validation for `city` and `countryCode`.
3. Write an integration test proving that both an invalid email format and an out-of-range age are rejected before calling the service.
4. Create a duplicate email scenario in the service; map the business error to a GraphQL error with a stable code, while also placing a unique constraint in the database.
5. Try sending a request missing `email` or passing `age` with the wrong type to observe errors handled by GraphQL before the resolver.

Once completed, you should be able to answer these self-check questions:

- Why can't `String!` replace `@NotBlank`?
- What role does `@Valid` play on an `@Argument` parameter?
- Why does checking for duplicate email in the service still require a unique constraint in the database?
- Which errors are handled by `@GraphQlExceptionHandler` for `BindException`, and which errors are caught by GraphQL before the resolver?
- Why does passing validation not prove that the user is authorized to run the mutation?
