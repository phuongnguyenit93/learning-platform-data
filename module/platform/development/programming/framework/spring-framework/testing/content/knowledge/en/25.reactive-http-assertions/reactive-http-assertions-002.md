# Body as a DTO, List, or Generic Type

When testing an HTTP endpoint, we often need to verify that the response body can be read by the client into the data type published by the API contract. With JSON, a body may represent a DTO, a nested object, a list, or a generic structure such as `Page<UserResponse>` or `Map<String, List<OrderResponse>>`. Checking only the status or a few JSON strings may fail to catch errors in data types, nested structures, or deserialization capability.

`MockMvcTester` in Spring Framework 6.2+ supports reading a JSON body and converting it into a Java type with `bodyJson().convertTo(...)`. You can convert to a concrete class, a DTO containing a list, or a generic type described using `ParameterizedTypeReference`. Then AssertJ checks the converted object using equality, property assertions, or `satisfies(...)`.

## 1. From a JSON response to a Java data type

Suppose an endpoint returns user information:

```java
@RestController
@RequestMapping("/api/users")
class UserController {

    @GetMapping("/{id}")
    UserResponse findById(@PathVariable long id) {
        return new UserResponse(id, "Lan", "ACTIVE");
    }
}

record UserResponse(long id, String name, String status) {
}
```

The JSON response looks like this:

```json
{
  "id": 42,
  "name": "Lan",
  "status": "ACTIVE"
}
```

On the server side, Spring MVC uses `HttpMessageConverter` (usually a Jackson JSON converter) to serialize `UserResponse` into JSON. On the test side, `convertTo(UserResponse.class)` deserializes the JSON response into a Java instance. We can compare that instance with the expected object.

```java
assertThat(mvc.get().uri("/api/users/42"))
        .hasStatusOk()
        .bodyJson()
        .convertTo(UserResponse.class)
        .isEqualTo(new UserResponse(42L, "Lan", "ACTIVE"));
```

This is a response contract check at the data type level. The test verifies that the JSON can be mapped to `UserResponse` and that the fields have the expected values. If the JSON is missing a field required by application logic, has the wrong type, or has a structure incompatible with the DTO, the conversion or assertion may fail.

## 2. Preparing `MockMvcTester`

`MockMvcTester` belongs to the `org.springframework.test.web.servlet.assertj` package and was introduced in Spring Framework 6.2. It provides an AssertJ-style request and assertion API for `MockMvc` results.

A tester can be created from an already configured `MockMvc`:

```java
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.assertj.MockMvcTester;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new UserController())
        .build();

MockMvcTester mvc = MockMvcTester.create(mockMvc);
```

If you want to test the MVC configuration loaded from `WebApplicationContext`, create `MockMvc` with `webAppContextSetup(...)` and wrap it with `MockMvcTester.create(...)`. The source of the `MockMvc` configuration determines the test scope; `MockMvcTester` only changes how requests and assertions are written.

With a Spring Boot version that supports MockMvcTester, an auto-configured tester can be injected when AssertJ is on the test classpath:

```java
@SpringBootTest
@AutoConfigureMockMvc
class UserControllerIntegrationTest {

    @Autowired
    private MockMvcTester mvc;
}
```

If the application is not yet using Spring Framework 6.2 or a Boot version that supports this auto-configuration, upgrade according to the dependency management in use or create the tester manually from `MockMvc`. Do not mix different `spring-test` versions in the same application.

## 3. Converting the body to a concrete DTO

For a root-level JSON object, pass the target class to `convertTo(...)`:

```java
public record UserResponse(long id, String name, String status) {
}

@Test
void shouldReturnUserAsTypedResponse() {
    assertThat(mvc.get().uri("/api/users/42"))
            .hasStatusOk()
            .bodyJson()
            .convertTo(UserResponse.class)
            .isEqualTo(new UserResponse(42L, "Lan", "ACTIVE"));
}
```

Steps in the assertion chain:

1. `mvc.get().uri(...)` sends a GET request via `MockMvc`.
2. `hasStatusOk()` verifies the response has status 200.
3. `bodyJson()` requests reading the body as JSON.
4. `convertTo(UserResponse.class)` deserializes the body into the `UserResponse` type.
5. `isEqualTo(...)` compares the resulting object with the expected object.

Records suit response DTOs well because the constructor and components are explicitly declared, and records automatically provide `equals()` and `hashCode()`. For regular classes, you can use constructors or getters/setters supported by the JSON mapper.

Mutable class example:

```java
public class UserResponse {

    private long id;
    private String name;
    private String status;

    public UserResponse() {
    }

    public long getId() {
        return id;
    }

    public void setId(long id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
```

With this class, the test can use `satisfies(...)` to check individual properties:

```java
assertThat(mvc.get().uri("/api/users/42"))
        .hasStatusOk()
        .bodyJson()
        .convertTo(UserResponse.class)
        .satisfies(user -> {
            assertThat(user.getId()).isEqualTo(42L);
            assertThat(user.getName()).isEqualTo("Lan");
            assertThat(user.getStatus()).isEqualTo("ACTIVE");
        });
```

`isEqualTo(...)` is suitable when the DTO implements value-based equality. `satisfies(...)` is more flexible when the class does not override `equals()`, when you only want to check a subset of properties, or when you need to assert relationships across multiple fields.

## 4. Converting nested object structures

API responses often contain nested objects. For example, a user with an address:

```java
public record AddressResponse(String city, String country) {
}

public record UserDetailResponse(
        long id,
        String name,
        AddressResponse address
) {
}
```

JSON response:

```json
{
  "id": 42,
  "name": "Lan",
  "address": {
    "city": "Ho Chi Minh City",
    "country": "Vietnam"
  }
}
```

Convert the entire body into `UserDetailResponse`:

```java
assertThat(mvc.get().uri("/api/users/42/detail"))
        .hasStatusOk()
        .bodyJson()
        .convertTo(UserDetailResponse.class)
        .isEqualTo(new UserDetailResponse(
                42L,
                "Lan",
                new AddressResponse("Ho Chi Minh City", "Vietnam")
        ));
```

The JSON mapper reads the `address` object as `AddressResponse` because that component's type is declared in the DTO. This approach checks both the nested structure and the field values. If you only care about a deeply nested field, JSONPath remains a concise option:

```java
assertThat(mvc.get().uri("/api/users/42/detail"))
        .hasStatusOk()
        .bodyJson()
        .extractingPath("$.address.city")
        .isEqualTo("Ho Chi Minh City");
```

## 5. Converting a JSON array into a typed list

An endpoint may return a JSON array:

```json
[
  {"id": 1, "name": "Lan", "status": "ACTIVE"},
  {"id": 2, "name": "Minh", "status": "INACTIVE"}
]
```

If you only pass `List.class`, Java loses the `UserResponse` element type due to type erasure. The conversion result may be a `List` containing maps instead of a typed DTO list.

To retain generic type information, use `ParameterizedTypeReference`:

```java
import java.util.List;

import org.springframework.core.ParameterizedTypeReference;

ParameterizedTypeReference<List<UserResponse>> userListType =
        new ParameterizedTypeReference<>() {
        };

@Test
void shouldConvertJsonArrayToTypedList() {
    assertThat(mvc.get().uri("/api/users"))
            .hasStatusOk()
            .bodyJson()
            .convertTo(userListType)
            .satisfies(users -> {
                assertThat(users).hasSize(2);
                assertThat(users.get(0))
                        .isEqualTo(new UserResponse(1L, "Lan", "ACTIVE"));
                assertThat(users.get(1))
                        .isEqualTo(new UserResponse(2L, "Minh", "INACTIVE"));
            });
}
```

`ParameterizedTypeReference<List<UserResponse>>` preserves both the `List` container type and the `UserResponse` element type through generic type information captured when creating an anonymous subclass. The `convertTo(ParameterizedTypeReference<T>)` overload uses this information to deserialize the array into `List<UserResponse>`.

If the Spring Test version in use does not have a conversion overload accepting `ParameterizedTypeReference`, check the API for that exact version or use a wrapper DTO with a concretely declared generic field. Do not substitute `List.class` if assertions need to work with typed `UserResponse` instances.

### When you only need to check part of a list

If the test does not need to manipulate Java objects, JSONPath can be simpler:

```java
assertThat(mvc.get().uri("/api/users"))
        .hasStatusOk()
        .bodyJson()
        .extractingPath("$[0].name")
        .isEqualTo("Lan");
```

You can combine JSONPath to verify element counts, positions, or specific properties. Use typed list conversion when you need to check multiple fields of each element or when the element data type is an important part of the API contract.

## 6. Converting nested generic types

APIs often return an outer wrapper object around a data list, for example:

```json
{
  "page": 0,
  "size": 2,
  "items": [
    {"id": 1, "name": "Lan", "status": "ACTIVE"},
    {"id": 2, "name": "Minh", "status": "INACTIVE"}
  ]
}
```

You can model the response with a generic DTO:

```java
public record PageResponse<T>(
        int page,
        int size,
        List<T> items
) {
}
```

When converting the body, provide the full generic type:

```java
ParameterizedTypeReference<PageResponse<UserResponse>> pageType =
        new ParameterizedTypeReference<>() {
        };

assertThat(mvc.get().uri("/api/users?page=0&size=2"))
        .hasStatusOk()
        .bodyJson()
        .convertTo(pageType)
        .satisfies(page -> {
            assertThat(page.page()).isZero();
            assertThat(page.size()).isEqualTo(2);
            assertThat(page.items()).hasSize(2);
            assertThat(page.items().get(0).name()).isEqualTo("Lan");
        });
```

The key point is that the target type must be `PageResponse<UserResponse>`, not just `PageResponse.class`. If only the raw class is passed, the mapper does not know the element type of `items` and typically decodes them as generic maps.

The same principle applies to other generic types:

```java
ParameterizedTypeReference<Map<String, List<UserResponse>>> responseType =
        new ParameterizedTypeReference<>() {
        };
```

Full type information lets assertions work with `Map<String, List<UserResponse>>` instead of `Map<String, Object>` containing unconverted nested elements.

## 7. Wrapper DTO for collections

`ParameterizedTypeReference` is not always needed. If the API returns a JSON object with a list field, you can declare a concrete wrapper DTO:

```java
public record UserListResponse(List<UserResponse> users, int total) {
}
```

Then convert using the regular class:

```java
assertThat(mvc.get().uri("/api/users/summary"))
        .hasStatusOk()
        .bodyJson()
        .convertTo(UserListResponse.class)
        .satisfies(response -> {
            assertThat(response.total()).isEqualTo(2);
            assertThat(response.users()).hasSize(2);
            assertThat(response.users().get(0).name()).isEqualTo("Lan");
        });
```

The JSON mapper reads the generic information of the `List<UserResponse>` component in the record and converts each element to `UserResponse`. A wrapper gives the response a clear structure that is convenient for clients, while avoiding the need to create a separate generic type reference in tests for a fixed response shape.

## 8. Converting maps, enums, and special data types

A JSON object can be converted into a `Map` if the structure is dynamic or has no stable DTO. However, if the schema is known, a DTO usually makes contract verification clearer.

Example with a typed map value:

```java
ParameterizedTypeReference<Map<String, UserResponse>> mapType =
        new ParameterizedTypeReference<>() {
        };

assertThat(mvc.get().uri("/api/users/by-key"))
        .hasStatusOk()
        .bodyJson()
        .convertTo(mapType)
        .satisfies(users -> {
            assertThat(users).containsKey("primary");
            assertThat(users.get("primary").name()).isEqualTo("Lan");
        });
```

For enums, the DTO can declare the enum type directly:

```java
public enum UserStatus {
    ACTIVE,
    INACTIVE
}

public record UserResponse(long id, String name, UserStatus status) {
}
```

If the JSON contains the string `"ACTIVE"` and the mapper uses default enum configuration, the `status` field can be converted to `UserStatus.ACTIVE`. If the application uses a custom enum deserializer or represents enums with another code, the test must use the matching mapper configuration to verify that behavior.

For date/time, money, or custom types, declare the DTO with the appropriate domain type and ensure the JSON mapper has the necessary modules/serializers registered. For example, `LocalDate` typically requires Jackson's Java Time module. Typed conversion tests catch missing modules or incompatible date formats.

## 9. Verifying the body after a POST request

Typed conversion is also useful for responses from POST, PUT, or PATCH. Suppose a user creation endpoint accepts JSON and returns `UserResponse`:

```java
@PostMapping
@ResponseStatus(HttpStatus.CREATED)
UserResponse create(@RequestBody CreateUserRequest request) {
    return new UserResponse(42L, request.name(), "ACTIVE");
}

record CreateUserRequest(String name) {
}
```

The test sends a JSON body and converts the response:

```java
String requestBody = """
        {"name":"Lan"}
        """;

assertThat(mvc.post().uri("/api/users")
                .contentType(MediaType.APPLICATION_JSON)
                .content(requestBody))
        .hasStatus(201)
        .bodyJson()
        .convertTo(UserResponse.class)
        .isEqualTo(new UserResponse(42L, "Lan", "ACTIVE"));
```

This test verifies that the request body is bound, the controller handles it, and the response is serialized and deserialized back into the expected DTO. When you want to verify an exact HTTP status, use `hasStatus(201)` or a supported specific status matcher rather than just checking that the request did not fail.

## 10. Role of the JSON mapper and message converter

There are two separate conversion steps in the test:

```text
                SERVER SIDE
Controller returns Java DTO
          |
          v
HttpMessageConverter (Jackson)
          |
          v
HTTP response body (JSON)
          |
          v
MockMvcTester.bodyJson()
          |
          v
JSON mapper used for convertTo(...)
          |
          v
DTO / List<DTO> / Java generic type
          |
          v
AssertJ verifies values
```

`HttpMessageConverter` belongs to Spring MVC and is responsible for producing the HTTP response body. `convertTo(...)` belongs to the assertion phase and is responsible for deserializing the JSON body into the target type. The two processes both involve a JSON mapper, but you should not assume every custom application configuration automatically applies to the assertion conversion step.

For results to accurately reflect the application contract:

- Ensure the converter producing the response uses the expected JSON configuration.
- Ensure the target type has constructors, properties, or record components compatible with the mapper.
- Register required modules for `JavaTime`, monetary types, or custom domain types.
- Use the same naming strategy and mapping annotations that clients expect to receive.
- When verifying custom serializers/deserializers, configure them explicitly in the test and verify both output and conversion.

If the test uses `webAppContextSetup`, the converters from the loaded MVC configuration can be tested directly. If using `standaloneSetup`, register the required converters through the builder. Boot configuration typically provides Jackson converters according to the application's dependencies and properties.

## 11. Comparing typed conversion and JSONPath

The two ways of checking a JSON body can complement each other:

| Need | Suitable approach |
| --- | --- |
| Check one specific field | `bodyJson().extractingPath("$.name")` |
| Check an object with multiple fields | `bodyJson().convertTo(UserResponse.class)` |
| Check a list of DTOs | `convertTo(ParameterizedTypeReference<List<UserResponse>>)` |
| Check a wrapper with a list field | `convertTo(UserListResponse.class)` |
| Check a nested generic type | `convertTo(ParameterizedTypeReference<PageResponse<UserResponse>>)` |
| Check a dynamic structure without a stable DTO | JSONPath or `Map` with an appropriate generic type |

JSONPath is usually more concise when only part of the body is the focus. Typed conversion is appropriate when the response structure is a strongly typed contract and multiple fields must be verified together.

There is no need to create a DTO just to check a single simple value. Conversely, if actual clients deserialize the response into a DTO or generic type, testing conversion helps catch compatibility issues earlier.

## 12. Common mistakes when converting bodies to data types

**Using `List.class` for a list of DTOs.**

Java type erasure discards the element type when only raw `List.class` is passed. Use `ParameterizedTypeReference<List<UserResponse>>` or a wrapper DTO with a `List<UserResponse>` field.

**Using a raw class for a generic DTO.**

`PageResponse.class` does not preserve `T`. If you need `PageResponse<UserResponse>`, supply the full generic type using `ParameterizedTypeReference`.

**DTO does not match the JSON.**

Property names, field types, constructors, and setters must be compatible with the mapper. Check JSON naming strategies, annotations, and nested structures when conversion fails.

**Missing module for special types.**

Types like `LocalDate`, `LocalDateTime`, or custom domain types may require separate modules or serializers/deserializers. Ensure the mapper in the test has the necessary configuration.

**Body is not JSON or is empty.**

`bodyJson()` and `convertTo(...)` require a valid JSON body. For text, file, XML, or `204 No Content` responses, use assertions suitable for that body type.

**Checking DTOs only by identity.**

If a DTO is a regular class that does not override `equals()`, two instances with the same data may still not be equal according to `isEqualTo(...)`. Use a record, implement value-based equality, or use `satisfies(...)` to inspect properties.

**Forgetting to verify the status before the body.**

If a request returns an HTML error or an error body with a different schema, converting to the DTO may fail in ways that obscure the real issue. Verify the status and content type first, then convert the body according to the corresponding response schema.

**Assuming conversion proves the server serializes correctly in every environment.**

Conversion only proves that the specific body in the test can be used by the mapper to build the target type. If the test mapper differs from client or server configuration, results may not accurately reflect production. Use matching mapper configuration when schemas depend on custom serializers or modules.

## 13. Workflow for testing bodies as DTOs or generic types

When verifying that a response can be read by clients as a Java type, follow this sequence:

1. Identify the response schema: single object, nested object, JSON array, or generic object.
2. Declare a DTO reflecting the schema, preferring records or classes with clear mapping.
3. For collections or generic types, preserve type parameter information with `ParameterizedTypeReference` or use a concrete wrapper DTO.
4. Create `MockMvcTester` from a `MockMvc` configured for the test scope.
5. Send the request and verify the HTTP status.
6. Call `bodyJson().convertTo(...)` to convert the body into the target type.
7. Use equality or `satisfies(...)` to inspect the data; use JSONPath for individual fields when appropriate.
8. Ensure the JSON mapper and message converters are compatible with the configuration required by the API contract.

Example for a generic list:

```java
ParameterizedTypeReference<List<UserResponse>> userListType =
        new ParameterizedTypeReference<>() {
        };

assertThat(mvc.get().uri("/api/users"))
        .hasStatusOk()
        .bodyJson()
        .convertTo(userListType)
        .satisfies(users -> {
            assertThat(users).hasSize(2);
            assertThat(users).extracting(UserResponse::status)
                    .containsOnly("ACTIVE", "INACTIVE");
        });
```

## Conclusion

`MockMvcTester.bodyJson().convertTo(...)` helps verify HTTP bodies using the Java data types expected by clients. For a single DTO, pass `Class`; for lists or generic types, use `ParameterizedTypeReference` to preserve element and type parameter information. A wrapper DTO is a good choice when the API returns an object with a fixed collection field.

Combining status checks, typed conversion, and object assertions verifies the response contract at the data level. Use JSONPath when only a few fields are needed, and typed conversion when mapping the entire response into a DTO or generic type is what needs verification.
