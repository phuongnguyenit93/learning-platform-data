# Verifying JSON Bodies and Converting to Data Types

When testing REST APIs with Spring MVC, checking the HTTP status alone is not enough. An endpoint can return `200 OK` while the JSON body is still missing fields, has wrong values, has the wrong structure, or is incompatible with the DTO expected by the client. Web layer tests need to verify the JSON content and, when appropriate, try converting that body into a Java data type.

Spring Framework 6.2 introduces `MockMvcTester`, an AssertJ-based testing API for `MockMvc`. Instead of combining multiple individual `ResultMatcher` instances, you can write chained assertions: verify the status, read the JSON body, extract values by JSONPath, or convert the entire body into a Java class and inspect that object.

`MockMvcTester` still uses the `MockMvc` and Spring MVC Test infrastructure. It does not start a real HTTP server. The main value of this API is its concise expression of assertions focused on what the client receives.

## 1. Why Verify the JSON Body?

Suppose an endpoint returns user details:

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

A test that only checks the status:

```java
mockMvc.perform(get("/api/users/42"))
        .andExpect(status().isOk());
```

only confirms that the request was processed successfully according to the HTTP status code. The test does not verify whether the body has the right `id`, `name`, and `status`. If serialization omits a field or the controller returns wrong data, the status assertion can still pass.

Checking JSON verifies the response contract at the level the client consumes. There are two common approaches:

- Checking specific values with JSONPath when only a few fields are the focus.
- Converting the entire JSON into a DTO or Java data type when you want to verify the structure and values of the response object.

## 2. What Is `MockMvcTester`?

`MockMvcTester` belongs to the `org.springframework.test.web.servlet.assertj` package. This API provides AssertJ-style request builders and assertions for `MockMvc` results.

Related components:

| Component | Role |
| --- | --- |
| `MockMvc` | Sends simulated requests through `DispatcherServlet` and Spring MVC. |
| `MockMvcTester` | Provides a way to create requests and verify results using AssertJ. |
| `assertThat(...)` | Starts the AssertJ assertion chain. |
| `bodyJson()` | Accesses the body as JSON for verification or conversion. |
| `extractingPath(...)` | Extracts a value from JSON using a JSONPath expression. |
| `convertTo(...)` | Converts the JSON body into the specified Java data type. |

`MockMvcTester` is available starting in Spring Framework 6.2. To use it, the project needs the matching Spring Test version and AssertJ on the test classpath. If using Spring Boot, use a Boot version supporting Spring Framework 6.2 or later with the appropriate test dependencies.

## 3. Initializing `MockMvcTester`

You can create `MockMvc` from a chosen controller and wrap it with `MockMvcTester`:

```java
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.assertj.MockMvcTester;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new UserController())
        .build();

MockMvcTester mvc = MockMvcTester.create(mockMvc);
```

If you want to test the MVC configuration loaded from a `WebApplicationContext`, you can create `MockMvc` with `webAppContextSetup(...)` and pass it into `MockMvcTester.create(...)`:

```java
MockMvc mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .build();

MockMvcTester mvc = MockMvcTester.create(mockMvc);
```

The configuration source of `MockMvc` still determines the integration scope. `MockMvcTester` only changes how requests are created and assertions are written; it does not turn a standalone test into one that loads the entire application context.

In Spring Boot, `@AutoConfigureMockMvc` can auto-configure `MockMvcTester` when the test environment has AssertJ and the Boot version supports this feature. In that case, you can inject the tester directly instead of creating it from `MockMvc`:

```java
@SpringBootTest
@AutoConfigureMockMvc
class UserControllerIntegrationTest {

    @Autowired
    private MockMvcTester mvc;
}
```

If the project's Boot configuration does not provide the tester bean, you can inject `MockMvc` and call `MockMvcTester.create(mockMvc)` in `@BeforeEach`. Choose an initialization approach suited to your Spring Boot version and test setup.

## 4. Sending Requests and Verifying JSON Bodies with JSONPath

Assuming `MockMvcTester` has been created in the `mvc` field, the test can send a GET request and verify the response:

```java
import static org.assertj.core.api.Assertions.assertThat;

@Test
void shouldReturnUserAsJson() {
    assertThat(mvc.get().uri("/api/users/42"))
            .hasStatusOk()
            .bodyJson()
            .extractingPath("$.id")
            .isEqualTo(42);
}
```

The assertion chain is read from left to right:

1. `mvc.get().uri(...)` creates a GET request to the endpoint.
2. `assertThat(...)` starts the assertion on the request result.
3. `hasStatusOk()` confirms the response has status 200.
4. `bodyJson()` shifts the assertion focus to the JSON body.
5. `extractingPath("$.id")` retrieves the value of the `id` property at the JSON root level.
6. `isEqualTo(42)` compares the extracted value with the expected result.

Multiple fields can be checked using separate assertions:

```java
@Test
void shouldExposeExpectedUserFields() {
    var result = mvc.get().uri("/api/users/42");

    assertThat(result).hasStatusOk();
    assertThat(result).bodyJson().extractingPath("$.id").isEqualTo(42);
    assertThat(result).bodyJson().extractingPath("$.name").isEqualTo("Lan");
    assertThat(result).bodyJson().extractingPath("$.status").isEqualTo("ACTIVE");
}
```

JSONPath is useful when you need to inspect part of a response without creating a DTO just to read a few fields. Some common expressions:

| JSONPath | Selected Value |
| --- | --- |
| `$.id` | The `id` property at the root level. |
| `$.profile.email` | The `email` property inside the `profile` object. |
| `$.items[0].name` | The `name` of the first element in the `items` array. |
| `$.items.length()` | The number of elements in the `items` array according to supported JSONPath syntax. |
| `$.items[*].id` | The `id` values across all elements of `items`. |

Use expressions that match the actual response structure. When the JSON structure changes, JSONPath may stop matching; the failing assertion helps signal that the response contract changed.

## 5. Converting the JSON Body to a DTO with `convertTo(...)`

When the response represents a structured object, you can convert the JSON into a Java type and inspect the object. This is useful when multiple fields are related and the test wants to verify the whole object rather than just one path.

Response DTO:

```java
public record UserResponse(long id, String name, String status) {
}
```

Test converting the body to `UserResponse`:

```java
@Test
void shouldConvertJsonBodyToUserResponse() {
    assertThat(mvc.get().uri("/api/users/42"))
            .hasStatusOk()
            .bodyJson()
            .convertTo(UserResponse.class)
            .isEqualTo(new UserResponse(42L, "Lan", "ACTIVE"));
}
```

`convertTo(UserResponse.class)` reads the JSON response and converts it into a `UserResponse` instance. Because records define equality based on their components, `isEqualTo(...)` can compare the entire value of the expected object against the converted result.

If not using a record, you can use a DTO class with constructors or getters/setters compatible with the configured JSON mapper. The key requirement is that the target type can be instantiated and populated by the mapper.

### Inspecting the Object with `satisfies(...)`

When you want to check individual fields or need complex assertions, you can use `satisfies(...)`:

```java
@Test
void shouldConvertAndInspectUserResponse() {
    assertThat(mvc.get().uri("/api/users/42"))
            .hasStatusOk()
            .bodyJson()
            .convertTo(UserResponse.class)
            .satisfies(user -> {
                assertThat(user.id()).isEqualTo(42L);
                assertThat(user.name()).isNotBlank();
                assertThat(user.status()).isEqualTo("ACTIVE");
            });
}
```

`convertTo(...)` returns an assertion for the converted Java object. `satisfies(...)` receives that object to run multiple related assertions. This is helpful when checking invariants across fields or when you do not want to construct a complete expected object.

## 6. Verifying Nested JSON and Collections

A response can contain nested objects:

```java
record AddressResponse(String city, String country) {
}

record CustomerResponse(long id, String name, AddressResponse address) {
}
```

Corresponding JSON:

```json
{
  "id": 7,
  "name": "Minh",
  "address": {
    "city": "Ho Chi Minh City",
    "country": "Vietnam"
  }
}
```

You can verify it directly with JSONPath:

```java
assertThat(mvc.get().uri("/api/customers/7"))
        .hasStatusOk()
        .bodyJson()
        .extractingPath("$.address.city")
        .isEqualTo("Ho Chi Minh City");
```

Or convert it to a DTO:

```java
assertThat(mvc.get().uri("/api/customers/7"))
        .hasStatusOk()
        .bodyJson()
        .convertTo(CustomerResponse.class)
        .isEqualTo(new CustomerResponse(
                7L,
                "Minh",
                new AddressResponse("Ho Chi Minh City", "Vietnam")
        ));
```

For collection responses, you can use JSONPath to check the element count and values at specific positions:

```java
assertThat(mvc.get().uri("/api/users"))
        .hasStatusOk()
        .bodyJson()
        .extractingPath("$[0].name")
        .isEqualTo("Lan");
```

If you need to convert a JSON array into `List<UserResponse>`, the target type has a generic type parameter. In that case, use a conversion API that supports generic type references and the corresponding JSON mapper, rather than passing just `List.class`, because type erasure loses the element type. If the test only needs to verify a few elements, JSONPath is usually simpler.

## 7. Verifying POST Requests and JSON Responses

`MockMvcTester` supports HTTP methods similar to `MockMvc`. You can build a POST request with a JSON content type and JSON body:

```java
@Test
void shouldCreateUserAndReturnJson() {
    String requestBody = """
            {
              "name": "Lan"
            }
            """;

    assertThat(mvc.post().uri("/api/users")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(requestBody))
            .hasStatus(201)
            .bodyJson()
            .extractingPath("$.name")
            .isEqualTo("Lan");
}
```

Here, `contentType(...)` declares the request body format; `content(...)` provides the JSON payload; `hasStatus(201)` verifies the Created status. You can use `hasStatusCreated()` if you want to express status 201 explicitly according to the assertion API of your version.

When the API returns a DTO, you can combine typed conversion:

```java
assertThat(mvc.post().uri("/api/users")
                .contentType(MediaType.APPLICATION_JSON)
                .content(requestBody))
        .hasStatus(201)
        .bodyJson()
        .convertTo(UserResponse.class)
        .satisfies(user -> {
            assertThat(user.name()).isEqualTo("Lan");
            assertThat(user.status()).isEqualTo("ACTIVE");
        });
```

Such a test verifies request mapping, JSON request binding, controller logic, and JSON response serialization within the scope of the configured `MockMvc`.

## 8. Verifying JSON Errors and Error Responses

A JSON body can be an error object. For example, an API returns errors with this structure:

```java
record ApiError(String code, String message) {
}
```

The test can verify the status and individual error fields:

```java
assertThat(mvc.get().uri("/api/users/999"))
        .hasStatus(404)
        .bodyJson()
        .extractingPath("$.code")
        .isEqualTo("USER_NOT_FOUND");
```

Or convert the body to an error DTO:

```java
assertThat(mvc.get().uri("/api/users/999"))
        .hasStatus(404)
        .bodyJson()
        .convertTo(ApiError.class)
        .isEqualTo(new ApiError(
                "USER_NOT_FOUND",
                "User 999 was not found"
        ));
```

If the response is not JSON, do not call `bodyJson()` just to check text. Use text body or header assertions suited to the response type. If an endpoint returns `204 No Content`, no body exists, so there is no JSON to convert.

## 9. JSONPath vs. Typed Conversion: Which Should You Choose?

The two verification approaches serve different purposes:

| Criterion | JSONPath with `extractingPath(...)` | `convertTo(...)` |
| --- | --- | --- |
| Scope | One or a few specific fields. | Entire body into a Java type. |
| Expected DTO | Not required. | Requires a compatible target type. |
| Nested objects | Extracted directly by path. | Mapper creates nested objects per configuration. |
| Collections | Easy to check elements or properties by path. | Needs generic type handling for specific element types. |
| When appropriate | Only a few values are the contract to verify. | Need to verify the response is compatible with the DTO used by the client. |

You do not need to convert every response into a DTO in every test. JSONPath fits small assertions, whereas typed conversion makes sense when the response schema is a major part of the API contract.

## 10. The Role of JSON Mappers and Message Converters

Spring MVC uses `HttpMessageConverter` to convert between HTTP bodies and Java objects. For JSON, applications commonly use Jackson via `MappingJackson2HttpMessageConverter` when the corresponding dependency is present.

The process in a JSON response can be illustrated as follows:

```text
Controller returns Java object
          |
          v
HttpMessageConverter (e.g., Jackson)
          |
          v
JSON HTTP response body
          |
          +--> JSONPath assertion reads value in JSON
          |
          +--> bodyJson().convertTo(Dto.class)
                    |
                    v
              JSON mapper creates Java object
                    |
                    v
              AssertJ asserts on object
```

Two conversion directions should be distinguished:

- When a controller returns an object, Spring MVC's message converter serializes the object into a JSON response.
- When the test calls `convertTo(...)`, the JSON response is deserialized into the target type for the assertion to check.

Both directions can use corresponding mapper configurations, but tests should not assume every Java type converts automatically. DTOs must be mapper-compatible, required modules must be on the classpath, and custom serializers/deserializers must be configured if the response relies on them.

If the test uses `standaloneSetup`, message converters can be supplied or customized in `MockMvcBuilders`. If the test uses `webAppContextSetup`, converters come from the loaded MVC configuration. When using Spring Boot with `@AutoConfigureMockMvc`, converters typically follow the application configuration.

## 11. Prerequisites and Common Mistakes

**Spring Framework version is too old.**

`MockMvcTester` was introduced in Spring Framework 6.2. If the project uses an older version, the corresponding class or API does not exist. Upgrade Spring consistently with the project's dependency management instead of adding a mismatched Spring Test JAR.

**AssertJ is missing from the test classpath.**

`MockMvcTester` is designed around AssertJ. Ensure the AssertJ dependency is present in the test runtime. With Spring Boot, `spring-boot-starter-test` usually provides common testing libraries including AssertJ.

**Invalid JSON response.**

`bodyJson()` requires a body that can be parsed as JSON. If the controller returns text, HTML, or an empty body, the JSON assertion will fail. Check the content type and response body before choosing a JSON assertion.

**JSONPath does not match the structure.**

If the path is wrong or the field is inside a nested object, the expression may fail to find a value. Cross-check the JSONPath against the actual JSON structure, especially with arrays and nested objects.

**Numeric values have a different type than expected.**

JSON numbers may be represented by different numeric types depending on the parser and extraction method. Choose a compatible expected value or convert to a DTO with explicit types to keep assertions clear.

**DTO is incompatible with the JSON mapper.**

If constructors, properties, or field types do not match, `convertTo(...)` can fail. Check the DTO structure, Jackson annotations, and required modules.

**Using `List.class` and expecting `List<UserResponse>`.**

Java generic types undergo type erasure. Passing only `List.class` does not retain element type information. Use the conversion API's generic type support if you need to deserialize a collection with a specific element type, or check individual elements with JSONPath.

**Confusing JSON assertions with exact character-by-character serialized JSON checks.**

JSONPath verifies data structurally. If property order or whitespace is not part of the contract, do not assert on raw JSON strings rigidly. If exact string formatting is a requirement, test the body text separately and recognize the test will be sensitive to formatting.

## 12. When Should You Still Use `MockMvc` and `ResultMatcher`?

`MockMvcTester` is a convenient alternative API for writing assertions, but `MockMvc` and `MockMvcResultMatchers` remain useful. Some projects already have tests using:

```java
mockMvc.perform(get("/api/users/42"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.name").value("Lan"));
```

This style remains valid. You can choose `MockMvcTester` for new tests or when you want AssertJ fluent assertions, while keeping traditional `MockMvc` in tests that are already clear and stable. There is no need to convert all tests simply because a new API exists.

What matters is that assertions accurately express the response contract: status, headers, JSON body, data types, and the values clients depend on.

## 13. Workflow for Testing JSON Bodies

When writing tests for an endpoint returning JSON, you can follow this sequence:

1. Create `MockMvc` for the scope to be tested: standalone controller, web application context, or Spring Boot test.
2. Create `MockMvcTester` via `MockMvcTester.create(mockMvc)` or inject the Spring Boot-configured tester if supported by your version.
3. Send the request using `get()`, `post()`, or the appropriate method, and specify the URI, headers, content type, and body as needed.
4. Assert the HTTP status before inspecting the content.
5. Call `bodyJson()` to assert that the response is JSON.
6. Use `extractingPath(...)` for specific fields or `convertTo(Dto.class)` to verify the complete object.
7. Add assertions for error responses, collections, nested objects, and empty-body cases when those are part of the endpoint's behavior.
8. Ensure the mappers and converters in the test are compatible with the configuration the endpoint needs.

A concise example for a response DTO:

```java
assertThat(mvc.get().uri("/api/users/42"))
        .hasStatusOk()
        .bodyJson()
        .convertTo(UserResponse.class)
        .isEqualTo(new UserResponse(42L, "Lan", "ACTIVE"));
```

This test confirms a successful HTTP response, that the body can be read as JSON, and that the JSON data converts into the exact response type expected by the client.

## Conclusion

`MockMvcTester` in Spring Framework 6.2+ provides an AssertJ way to verify MockMvc responses. `bodyJson()` opens the JSON body for assertions; `extractingPath(...)` checks specific values by JSONPath; `convertTo(...)` deserializes JSON into a DTO or Java type to inspect the entire object.

Choose JSONPath when only part of the contract needs verification and typed conversion when the DTO structure is what needs checking. Combining status, JSON body, and data types helps tests catch response bugs that status-only assertions cannot see.
