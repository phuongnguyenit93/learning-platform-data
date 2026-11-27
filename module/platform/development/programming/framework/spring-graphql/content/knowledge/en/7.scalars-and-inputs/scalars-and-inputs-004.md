# UUID Scalar in GraphQL

## Objectives

After this lesson, you will be able to:

- Explain why GraphQL has no built-in UUID scalar and when to expose a UUID scalar.
- Distinguish UUID from GraphQL's ID and String scalars.
- Declare a custom UUID scalar in SDL and use it in fields, arguments, and input objects.
- Register the UUID scalar in the GraphQL runtime using Spring for GraphQL.
- Bind UUID values to java.util.UUID in controllers and services.
- Understand the roles of parsing literals, parsing variables, and serializing output.
- Validate invalid UUIDs, nullability, and coercion errors.
- Design, test, and secure APIs that use UUIDs consistently.

## 1. What Is UUID and Why Need a Separate Scalar?

UUID (Universally Unique Identifier) is a 128-bit identifier, typically represented as a hyphenated hexadecimal string:

~~~text
550e8400-e29b-41d4-a716-446655440000
~~~

The standard text form consists of 36 characters: 32 hexadecimal digits and 4 hyphens grouped as 8-4-4-4-12. UUIDs are commonly used as identifiers for users, orders, products, events, or resources that require unique identification.

GraphQL has five built-in scalars: Int, Float, String, Boolean, and ID. GraphQL does not define a built-in UUID scalar. If a schema needs to explicitly declare that a value must conform to the UUID format, the application must define a custom scalar.

Example:

~~~graphql
scalar UUID

type User {
    id: UUID!
    displayName: String!
}
~~~

Declaring `scalar UUID` creates a data type named UUID in the schema. However, declaring it in SDL alone is not enough for the GraphQL runtime to know how to read, validate, and convert UUID values. The application must register the corresponding scalar implementation.

A UUID scalar can handle three responsibilities:

- Accept input values from GraphQL literals or variables.
- Validate and convert the value into the type used by the application, usually java.util.UUID.
- Convert the Java value into a standard string format when returning a response.

## 2. Distinguishing UUID, ID, and String

These three types may all be represented as strings in JSON, yet their contract semantics differ.

| GraphQL Type | Meaning | Validates UUID Format? |
| --- | --- | --- |
| ID | Identifier of an object; internal format can be decided by the server | No |
| String | Plain text | No |
| UUID | Identifier that must conform to the UUID format defined by the scalar | Yes, if the coercing implementation performs validation |

Schema example using ID:

~~~graphql
type Query {
    user(id: ID!): User
}
~~~

ID is suitable when the client only needs to pass an opaque identifier. The value may be a UUID, a number converted to a string, a slug, or another identifier. GraphQL does not automatically verify that the value is formatted as a UUID.

If the API contract requires the identifier to be a UUID, you can use:

~~~graphql
type Query {
    user(id: UUID!): User
}
~~~

In that case, a non-UUID string is rejected during scalar coercion before the resolver is invoked.

Using String simply because a UUID is transmitted over JSON as a string loses type information in the schema. Clients cannot tell from the schema that the value must follow UUID rules.

### 2.1. When to Use Each Type?

Choose ID when the identifier is an opaque API detail and the server wants to retain the freedom to change formats in the future.

Choose UUID when the UUID format is an intentional part of the public contract—for example, when multiple systems exchange the same identifier type or clients want to map it to a language-native UUID type.

Choose String when the value is text rather than an identifier under a UUID contract.

You should not convert every ID field to UUID just because the current database uses UUIDs as primary keys. The GraphQL schema should reflect the contract clients need to know, not necessarily mirror database storage types.

## 3. Defining the UUID Scalar in SDL

GraphQL SDL declares a custom scalar using the scalar keyword:

~~~graphql
"""
128-bit identifier represented as a standard UUID string.
"""
scalar UUID
~~~

You can then use the UUID scalar anywhere an input or output scalar is accepted.

### 3.1. Using UUID as an Output Field

~~~graphql
type User {
    id: UUID!
    displayName: String!
    email: String!
}
~~~

The id field returns a non-null UUID. When the response is serialized, the UUID value typically appears as a string:

~~~json
{
    "data": {
        "user": {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "displayName": "An Nguyen",
            "email": "an@example.com"
        }
    }
}
~~~

### 3.2. Using UUID as an Argument

~~~graphql
type Query {
    user(id: UUID!): User
    usersByIds(ids: [UUID!]!): [User!]!
}
~~~

The user field accepts one UUID. The usersByIds field accepts a list of non-null UUIDs; both the list and each element cannot be null.

A client can call:

~~~graphql
query {
    user(id: "550e8400-e29b-41d4-a716-446655440000") {
        id
        displayName
    }
}
~~~

The UUID literal is enclosed in double quotes because its input representation is a string. The scalar implementation parses that string into a UUID value.

### 3.3. Using UUID in an Input Object

~~~graphql
input CreateUserInput {
    externalId: UUID
    displayName: String!
}

type Mutation {
    createUser(input: CreateUserInput!): User!
}
~~~

The client sends variables:

~~~json
{
    "input": {
        "externalId": "550e8400-e29b-41d4-a716-446655440000",
        "displayName": "An Nguyen"
    }
}
~~~

JSON has no native UUID type, so UUIDs are passed as JSON strings. The GraphQL runtime uses the registered UUID scalar to coerce the value before passing the input data to the resolver.

### 3.4. Nullability Still Applies Like Other Scalars

You can declare:

- UUID: value may be null.
- UUID!: required value, cannot be null.
- [UUID!]!: required list, and every UUID in the list is also required.

Custom scalars do not alter GraphQL nullability rules. If a field is declared UUID! but the resolver returns null, GraphQL handles the error according to non-null propagation rules.

## 4. UUID Format and Validation Rules

UUID has several standardized versions. Common versions include UUID v1, v4, and v7. Each version generates values differently, yet all share the same standard UUID representation.

Examples:

~~~text
550e8400-e29b-41d4-a716-446655440000
f47ac10b-58cc-4372-a567-0e02b2c3d479
018f1f2e-7b3c-7cc1-9f3a-123456789abc
~~~

A general UUID scalar typically checks whether a string is syntactically valid as a UUID. If business logic allows only specific versions, such as UUID v4, you must add separate version validation rules.

Distinguish two levels of validation:

- **Syntactic validation:** whether the value can be parsed into a UUID.
- **Business validation:** whether the UUID belongs to an existing object, matches the right tenant, has the right identifier kind, or satisfies the application's version policy.

Successful parsing does not prove that the object exists or that the user has permission to access it.

### 4.1. Uppercase and Lowercase

Hexadecimal letters in a UUID string can appear in uppercase or lowercase. Java's UUID.toString() typically produces a normalized lowercase representation.

For example, the following two strings represent the same UUID:

~~~text
550E8400-E29B-41D4-A716-446655440000
550e8400-e29b-41d4-a716-446655440000
~~~

Applications should standardize the serialized form in responses, typically the canonical string produced by the scalar implementation. Do not use raw string comparison at the business layer when two values may differ in casing yet represent the same UUID.

### 4.2. Invalid UUIDs

The following values do not follow the standard UUID format:

~~~text
550e8400-e29b-41d4-a716
not-a-uuid
550e8400_e29b_41d4_a716_446655440000
~~~

The scalar must reject unparseable values and produce a clear coercion error. Do not silently turn malformed strings into a default UUID or return null, because that hides input errors and breaks the API contract.

## 5. Setting Up the UUID Scalar in Spring for GraphQL

Two approaches are commonly used:

1. Use an already implemented and tested custom scalar library.
2. Write a custom Coercing implementation when you have UUID rules that existing libraries do not satisfy.

For standard UUIDs, the graphql-java-extended-scalars library provides a built-in UUID scalar. This is a good choice to avoid rewriting common parsing and serialization logic.

### 5.1. Adding the graphql-java-extended-scalars Dependency

With Maven:

~~~xml
<dependency>
    <groupId>com.graphql-java</groupId>
    <artifactId>graphql-java-extended-scalars</artifactId>
    <version>compatible-version</version>
</dependency>
~~~

Declare a library version compatible with the GraphQL Java version managed by Spring Boot.

With Gradle:

~~~groovy
dependencies {
    implementation("com.graphql-java:graphql-java-extended-scalars:compatible-version")
}
~~~

Do not upgrade GraphQL Java independently just to install extended scalars. Check Spring Boot's dependency management and pick an extended scalars release compatible with the GraphQL Java version resolved in your project.

### 5.2. Registering the Scalar with RuntimeWiringConfigurer

Spring for GraphQL provides RuntimeWiringConfigurer to add scalars to the runtime wiring.

~~~java
import graphql.scalars.ExtendedScalars;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
class GraphQlScalarConfiguration {

    @Bean
    RuntimeWiringConfigurer uuidScalarConfigurer() {
        return wiringBuilder ->
                wiringBuilder.scalar(ExtendedScalars.UUID);
    }
}
~~~

In this example:

- ExtendedScalars.UUID is the scalar implementation provided by the library.
- RuntimeWiringConfigurer adds the scalar to the GraphQL runtime.
- The registered scalar name must match the name UUID in the SDL.

Once the runtime is built, the GraphQL engine can use this scalar to parse inputs and serialize outputs.

You do not need to write a resolver for the UUID scalar itself. Scalar coercing is responsible for value conversion; field resolvers remain responsible for business logic such as finding a user or creating an order.

### 5.3. If Implementing Coercing Manually

GraphQL Java represents a custom scalar through GraphQLScalarType and Coercing. A coercing implementation needs to handle three conversion directions:

| Method | Input Data | Role |
| --- | --- | --- |
| parseValue | Value from variables, typically a JSON string | Validate and convert into a UUID |
| parseLiteral | Literal value in a GraphQL document | Validate the AST node and convert into a UUID |
| serialize | Java value returned by a resolver | Convert the UUID into a response string |

Conversion flow:

~~~mermaid
flowchart TD
    A["GraphQL variable or literal"] --> B["parseValue / parseLiteral"]
    B --> C{"Valid UUID?"}
    C -->|No| D["Coercion error"]
    C -->|Yes| E["java.util.UUID"]
    E --> F["Resolver / service"]
    F --> G["Returned UUID value"]
    G --> H["serialize"]
    H --> I["UUID string in response"]
~~~

When writing coercing manually:

- Accept only the input type published by the API, usually a string.
- Parse using Java's standard UUID library.
- Translate parse failures into GraphQL Java's appropriate coercion exceptions.
- Do not let parseLiteral and parseValue enforce two different sets of rules.
- serialize should handle the UUID type that resolvers actually return.
- Do not expose stack traces or internal details in public error messages.

Coercing method signatures can vary across GraphQL Java versions. Some newer versions pass GraphQLContext, Locale, and CoercedVariables. When implementing manually, use the exact signatures of the GraphQL Java version managed by your project. If you only need standard UUIDs, ExtendedScalars.UUID typically lets you avoid this API compatibility work.

## 6. Using UUID in Controllers and the Java Domain

When the scalar parses into java.util.UUID, controllers can receive this Java type directly via @Argument.

Schema:

~~~graphql
scalar UUID

type User {
    id: UUID!
    displayName: String!
}

type Query {
    user(id: UUID!): User
}
~~~

Controller:

~~~java
import java.util.UUID;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
class UserController {

    private final UserService userService;

    UserController(UserService userService) {
        this.userService = userService;
    }

    @QueryMapping
    User user(@Argument("id") UUID id) {
        return userService.findById(id);
    }
}
~~~

Client operation:

~~~graphql
query FindUser($id: UUID!) {
    user(id: $id) {
        id
        displayName
    }
}
~~~

Variables:

~~~json
{
    "id": "550e8400-e29b-41d4-a716-446655440000"
}
~~~

Scalar coercing converts the JSON string into a UUID before the resolver uses the argument. The service can work directly with UUID instead of repeating string-parsing logic.

### 6.1. Using UUID in an Input Object

Schema:

~~~graphql
input CreateUserInput {
    externalId: UUID
    displayName: String!
}

type Mutation {
    createUser(input: CreateUserInput!): User!
}
~~~

Java record:

~~~java
import java.util.UUID;

public record CreateUserInput(
        UUID externalId,
        String displayName) {
}
~~~

Controller:

~~~java
@MutationMapping
User createUser(@Argument("input") CreateUserInput input) {
    return userService.create(input);
}
~~~

Successful binding depends on scalar coercing returning a compatible Java type and the DTO structure matching the input object. With extended scalars, verify the Java type returned by the UUID scalar in the library version you are using.

### 6.2. UUID in Entities and Repositories

If the domain model uses UUID:

~~~java
public record User(
        UUID id,
        String displayName) {
}
~~~

Repositories/services can accept the same type:

~~~java
interface UserRepository {
    Optional<User> findById(UUID id);
}
~~~

~~~java
@Service
class UserService {

    private final UserRepository userRepository;

    UserService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    User findById(UUID id) {
        return userRepository.findById(id)
                .orElseThrow(() -> new UserNotFoundException(id));
    }
}
~~~

Using the same UUID type from the GraphQL boundary into the domain reduces back-and-forth string conversions. If the persistence system uses a different type, place the conversion in the corresponding repository or adapter.

## 7. Do Input and Output UUIDs Follow the Same Rules?

A scalar can apply coercion for both input and output, though the two directions must be examined separately.

### 7.1. Input Coercion

Input arrives from two sources:

- Variables, usually a JSON string.
- Literals in the GraphQL document, also string literals.

Variables example:

~~~json
{
    "id": "550e8400-e29b-41d4-a716-446655440000"
}
~~~

Literal example:

~~~graphql
query {
    user(id: "550e8400-e29b-41d4-a716-446655440000") {
        displayName
    }
}
~~~

Both must be validated according to the same UUID rules.

### 7.2. Output Serialization

A resolver can return java.util.UUID. The scalar converts that value into a string for the response:

~~~json
{
    "data": {
        "user": {
            "id": "550e8400-e29b-41d4-a716-446655440000"
        }
    }
}
~~~

If a resolver returns a type not supported by the scalar, serialization may fail when GraphQL executes the field. Keep return types consistent across the domain and scalar implementation.

### 7.3. Do Not Turn the Scalar into a Database Query

A scalar only validates and converts a value's representation. It should not query the database to verify whether the UUID exists.

For example:

- The scalar verifies that the string can be parsed into a UUID.
- The resolver or service looks up the user by UUID.
- The service enforces business rules and access permissions.

Maintaining this boundary allows the scalar to be reused across many fields without depending on a specific database or service.

## 8. Testing the UUID Scalar

Both valid and invalid cases should be tested at the GraphQL execution level.

### 8.1. Testing a Valid UUID

Example using GraphQlTester configured for the application:

~~~java
graphQlTester.document("""
        query FindUser($id: UUID!) {
            user(id: $id) {
                id
                displayName
            }
        }
        """)
        .variable("id", "550e8400-e29b-41d4-a716-446655440000")
        .execute()
        .path("user.id")
        .entity(String.class)
        .isEqualTo("550e8400-e29b-41d4-a716-446655440000");
~~~

The test verifies that the UUID variable is coerced and the response is serialized as the expected string.

### 8.2. Testing a Malformed UUID

~~~java
graphQlTester.document("""
        query FindUser($id: UUID!) {
            user(id: $id) {
                id
            }
        }
        """)
        .variable("id", "not-a-uuid")
        .execute()
        .errors()
        .verify();
~~~

The test verifies that a non-UUID value is rejected during coercion. If you need finer-grained checks, you can assert on the error message or error classification according to your application's error contract.

### 8.3. Testing Literals

Beyond variables, you should verify that the scalar parses literals:

~~~graphql
query {
    user(id: "550e8400-e29b-41d4-a716-446655440000") {
        id
    }
}
~~~

A scalar that parses variables properly but fails to parse literals creates inconsistent behavior between operation styles. When using extended scalars, the library provides coercion logic for these paths; integration tests help verify that scalar registration is in effect.

### 8.4. Cases to Include in Tests

| Case | Expected Result |
| --- | --- |
| Valid UUID via variable | Resolver receives UUID and response returns UUID string |
| Valid UUID via literal | Operation executes |
| Malformed string | Coercion error |
| Number passed to UUID scalar | Rejected if the scalar requires a string |
| Missing UUID! argument | Validation/coercion error |
| Null passed to UUID! argument | Coercion error |
| Output field returns UUID | Serialized as a string |
| Output field returns unsupported type | Serialization error |
| Valid UUID with no matching user | Resolver/service handles not-found case |

Do not conflate UUID format errors with object not-found errors. These two cases happen at different layers and need to be observed and handled separately.

## 9. Error Handling and Coercion Messages

When a UUID is invalid, the scalar should raise a coercion error so the GraphQL runtime reports that the input does not match the declared type.

Example message that could be returned:

~~~text
Invalid UUID value
~~~

Public error messages should give the client enough information to know the input data is invalid. Do not include stack traces, internal package names, or system details in the message.

If a UUID is syntactically valid but does not exist in the system, that is a business error in the resolver or service. The application can map the exception to a GraphQL error using DataFetcherExceptionResolver or @GraphQlExceptionHandler.

Example distinction:

| Scenario | Detection Layer |
| --- | --- |
| "not-a-uuid" | Scalar coercion |
| Properly formatted UUID with no matching user | Resolver/service |
| UUID matches a user, but caller lacks permission | Authorization |
| Database unreachable | Infrastructure/service error |

Proper classification helps the API return appropriate errors and ensures logs contain enough detail for investigation without leaking internal data.

## 10. Security When Using UUID as an Identifier

UUIDs are generally harder to guess than sequential identifiers, but they are not an authorization mechanism.

Never assume a user can access a resource simply because they know the resource's UUID. The resolver or service must still check permissions.

Example:

~~~java
@QueryMapping
User user(@Argument("id") UUID id) {
    User user = userService.findById(id);
    authorizationService.checkCanViewUser(user);
    return user;
}
~~~

In addition:

- Do not treat UUIDs as secrets or access tokens.
- Do not log sensitive UUIDs unnecessarily.
- Do not allow clients to pick a tenant or owner UUID without checking permissions.
- Limit UUID list sizes to prevent oversized requests.
- Use parameter binding in persistence queries.
- Specify the UUID version and generation strategy if there are specific security or distributed requirements.

UUID v4 is typically randomly generated; UUID v7 has a structure that supports time-based sorting. Choosing a version depends on system requirements, but a syntax-validating scalar does not prove the UUID's generation source is secure.

## 11. Common Pitfalls

| Symptom | Cause | Solution |
| --- | --- | --- |
| Unknown type UUID | SDL uses UUID without declaring scalar UUID | Add scalar declaration to the schema |
| UUID input causes coercion error | Scalar not registered or string is malformed | Check RuntimeWiringConfigurer and input value |
| ID accepts non-UUID strings | ID does not validate UUID format | Use custom scalar UUID if the contract requires it |
| Controller receives unexpected type | Scalar implementation returns a different Java type than DTO expects | Check parseValue return type and argument binding |
| UUID output serialization fails | Resolver returns a type unsupported by the scalar | Return java.util.UUID or a type supported by the scalar |
| Literals work while variables fail (or vice versa) | parseLiteral and parseValue are inconsistent | Test both coercion paths |
| User not found despite valid UUID | UUID does not correspond to an existing record | Handle in service/resolver |
| User reads another user's resource | Checking only UUID without checking permissions | Enforce authorization by user and resource |

## 12. Process for Introducing a UUID Scalar into an Application

When adding a UUID scalar to Spring for GraphQL, follow this sequence:

1. **Define the contract.** Decide whether the API truly needs UUID or just an opaque ID identifier.
2. **Declare in SDL.** Add scalar UUID and use it on the appropriate fields, arguments, or input objects.
3. **Choose an implementation.** Prefer a tested scalar such as ExtendedScalars.UUID if there are no custom rules.
4. **Register runtime wiring.** Use RuntimeWiringConfigurer and ensure the scalar name matches the SDL.
5. **Choose the Java type.** Use java.util.UUID consistently across the boundary, service, and domain where appropriate.
6. **Verify coercion.** Test literals, variables, valid UUIDs, malformed strings, and null values.
7. **Verify serialization.** Ensure output UUIDs are serialized into canonical strings.
8. **Verify business logic.** Separate format errors, not-found errors, and unauthorized access.
9. **Write integration tests.** Verify the scalar is registered in the application's GraphQL runtime.
10. **Track compatibility.** When upgrading GraphQL Java or extended scalars, re-check dependency compatibility and run coercion tests.

## 13. Summary

GraphQL has no built-in UUID scalar. When UUID is part of the API contract, declare scalar UUID in the SDL and register a coercing implementation to handle inputs and outputs. ID suits opaque identifiers; String is for text; a UUID scalar explicitly expresses and validates the UUID format.

In Spring for GraphQL, you can use graphql-java-extended-scalars with RuntimeWiringConfigurer to register ExtendedScalars.UUID, then bind to java.util.UUID via @Argument or input DTOs. The scalar is responsible only for parsing, format validation, and serialization; looking up objects, checking permissions, and handling business logic still belong in resolvers/services. Testing variables, literals, nullability, and outputs ensures UUID behaves consistently across the entire GraphQL API.
