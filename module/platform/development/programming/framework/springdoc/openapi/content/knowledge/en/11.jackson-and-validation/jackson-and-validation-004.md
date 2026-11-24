# `@JsonView` and Per-Operation Data Projections

A model can contain more information than a single endpoint needs to return. For instance, a user list screen may need only the ID and display name; a detail screen needs the email as well; an admin endpoint might also need internal notes. If every endpoint serializes the same DTO in the exact same way, responses can easily include unnecessary fields or make the API contract unclear.

Jackson provides `@JsonView` to select a subset of properties when serializing or deserializing JSON. Spring MVC lets you activate a view on a controller method for responses and on a `@RequestBody` parameter for requests. Springdoc-openapi supports the `@JsonView` annotation in Spring MVC APIs, enabling it to generate schemas reflecting the projection used in each operation.

Crucially, a view only controls which properties Jackson reads or writes. It does not decide whether a caller has permission to access an endpoint, does not replace validation, and does not optimize database queries.

## 1. What Is a JSON View?

A JSON View is a marker class or interface. It typically contains no methods or state; the class name simply represents a group of properties. DTO properties are annotated with `@JsonView` to indicate which views they belong to.

For example, an account has these fields:

| Property | Public list | Detail | Admin |
| --- | --- | --- | --- |
| `id` | Yes | Yes | Yes |
| `displayName` | Yes | Yes | Yes |
| `email` | No | Yes | Yes |
| `internalNote` | No | No | Yes |

Views can be defined using nested interfaces:

```java
public final class UserViews {

    public interface Public {}

    public interface Detail extends Public {}

    public interface Admin extends Detail {}

    public interface Create {}

    public interface Update {}

    private UserViews() {}
}
```

`Detail extends Public` means the detail view inherits the properties of the public view. `Admin extends Detail` further includes the properties of both preceding views. `Create` and `Update` are two separate views for input data.

## 2. Annotating DTO Properties with Views

Place `@JsonView` on a field or getter to define which views include the property:

```java
public class UserDto {

    @JsonView(UserViews.Public.class)
    private UUID id;

    @JsonView({
        UserViews.Public.class,
        UserViews.Create.class,
        UserViews.Update.class
    })
    private String displayName;

    @JsonView(UserViews.Detail.class)
    private String email;

    @JsonView(UserViews.Admin.class)
    private String internalNote;

    // Constructors, getters and setters omitted.
}
```

With the view hierarchy above:

- `Public` includes `id` and `displayName`.
- `Detail` includes the fields of `Public` plus `email`.
- `Admin` includes the fields of `Detail` plus `internalNote`.
- `Create` and `Update` accept only `displayName` in this example.

A property can belong to multiple views by passing a class array to `@JsonView`. This is useful when the same field is used in both public responses and create/update requests.

You do not need a separate view for every endpoint. Group by stable data purposes, such as `Public`, `Detail`, `Admin`, `Create`, and `Update`, to keep the number of views from growing too quickly.

## 3. Selecting a View for Each Operation's Response

For controllers returning data via `@ResponseBody` or `ResponseEntity`, place `@JsonView` on the method to choose the response serialization view:

```java
@RestController
@RequestMapping("/api/users")
class UserController {

    private final UserService userService;

    UserController(UserService userService) {
        this.userService = userService;
    }

    @GetMapping("/{id}")
    @JsonView(UserViews.Public.class)
    UserDto getSummary(@PathVariable UUID id) {
        return userService.getById(id);
    }

    @GetMapping("/{id}/detail")
    @JsonView(UserViews.Detail.class)
    UserDto getDetail(@PathVariable UUID id) {
        return userService.getById(id);
    }

    @GetMapping("/{id}/admin")
    @JsonView(UserViews.Admin.class)
    UserDto getAdminView(@PathVariable UUID id) {
        return userService.getById(id);
    }
}
```

All three operations return the same Java type `UserDto`, yet Jackson serializes them according to three different views. For example, the public response contains only:

```json
{
  "id": "9c1c21b1-2cc0-45c7-86a4-10cde57c6c1b",
  "displayName": "Nguyen An"
}
```

The detail response adds `email`; the admin response adds `internalNote`. The view is fixed by the method annotation, so clients cannot pass a view name to request additional fields from the server.

Spring MVC supports only a single active view class on a controller method. Although `@JsonView` accepts multiple classes in its value array, the response advice supports a single class argument; if you need to combine multiple groups, create a composite interface through inheritance such as `Admin extends Detail`.

## 4. Selecting a View When Deserializing a Request Body

`@JsonView` can also be placed directly on a `@RequestBody` parameter. Spring MVC uses that view when Jackson deserializes JSON into the DTO:

```java
@PostMapping
@JsonView(UserViews.Public.class)
UserDto create(
    @JsonView(UserViews.Create.class)
    @Valid @RequestBody UserDto request
) {
    return userService.create(request);
}

@PutMapping("/{id}")
@JsonView(UserViews.Public.class)
UserDto update(
    @PathVariable UUID id,
    @JsonView(UserViews.Update.class)
    @Valid @RequestBody UserDto request
) {
    return userService.update(id, request);
}
```

In this example:

- `@JsonView(UserViews.Create.class)` on the parameter selects the fields read from input JSON on creation.
- `@JsonView(UserViews.Update.class)` limits the fields bound during updates.
- `@JsonView(UserViews.Public.class)` on the method selects the fields serialized in the response.
- `@Valid` runs Bean Validation on the object after deserialization succeeds.

The two annotation positions serve separate purposes: the annotation on the parameter controls request deserialization; the annotation on the method controls response serialization. You can use two different views within the same operation.

Properties outside the input view will not be bound under the active view. However, do not treat this as a mechanism that rejects every unknown field or enforces absolute write permissions. Behavior with unselected fields also depends on Jackson configuration and application error handling; test payloads containing fields outside the view. For sensitive data or complex write rules, dedicated request DTOs are usually easier to control.

## 5. View Inheritance and Unannotated Properties

Inheritance between view interfaces enables reusing field groups:

```java
public interface SummaryView {}

public interface DetailView extends SummaryView {}

public interface AdminView extends DetailView {}
```

A field annotated with `@JsonView(SummaryView.class)` appears in `SummaryView`, `DetailView`, and `AdminView` because the latter two extend the former. A field annotated with `@JsonView(AdminView.class)` appears only in the admin view.

Pay attention to properties without `@JsonView`. Jackson has `MapperFeature.DEFAULT_VIEW_INCLUSION` to decide whether unannotated properties appear in every view:

- When enabled, unannotated properties are included in all views.
- When disabled, unannotated properties are excluded from active views.

Jackson 2.x enables this feature by default at the library level, whereas Spring Boot's default `ObjectMapper` configuration typically disables it. Jackson 3 also changes the library default to disabled. If an application constructs or replaces its `ObjectMapper`, behavior may differ. Therefore, check the actual configuration instead of relying on a single universal default.

In a DTO using multiple views, the most predictable approach is to annotate every property that should appear explicitly with a view. In particular, never leave a sensitive field unannotated and assume it will always stay hidden.

## 6. Springdoc Schema Generation with `@JsonView`

Springdoc-openapi confirms support for the `@JsonView` annotation in Spring MVC APIs. When an operation uses a view, springdoc can use the view information to build a schema matching the data read or written by Jackson.

For example, two operations both returning `UserDto`:

```java
@GetMapping("/{id}")
@JsonView(UserViews.Public.class)
UserDto getSummary(@PathVariable UUID id) { ... }

@GetMapping("/{id}/detail")
@JsonView(UserViews.Detail.class)
UserDto getDetail(@PathVariable UUID id) { ... }
```

In `/v3/api-docs`, the schemas referenced by the two operations should reflect their respective projections. Springdoc may create separate component schemas per view or name components according to the internal rules of the version in use. Do not rely on specific component names without inspecting the output; what matters is confirming that each operation's `properties` list matches the actual response.

For request bodies, also check that the schema attached to the operation reflects the view on the `@RequestBody` parameter. Springdoc supports views on MVC APIs, but if a controller uses `MappingJacksonValue`, a custom `ResponseBodyAdvice`, a separate `ObjectMapper`, or dynamic runtime view selection, automatic schema generation may not infer every data branch. In those cases, declare schemas explicitly using `@Schema(implementation = ...)` or customize OpenAPI appropriately.

## 7. Dynamic View Control with `MappingJacksonValue`

When a view is chosen in code rather than via a fixed annotation, Spring MVC allows returning `MappingJacksonValue`:

```java
@GetMapping("/{id}/profile")
MappingJacksonValue getProfile(
    @PathVariable UUID id,
    Authentication authentication
) {
    UserDto user = userService.getById(id);

    Class<?> view = userAccessService.canSeeDetails(authentication, user)
        ? UserViews.Detail.class
        : UserViews.Public.class;

    MappingJacksonValue result = new MappingJacksonValue(user);
    result.setSerializationView(view);
    return result;
}
```

Here, the application chooses the view after checking the user's permissions. This example illustrates how Spring MVC passes a view to Jackson; in real applications, authorization must still be explicitly enforced and tested separately.

An operation might return multiple JSON shapes depending on caller identity. OpenAPI usually needs to document all valid shapes; if automatic schema generation reflects only one type, publish an appropriate shared schema or use `oneOf`/separate operations so the contract stays clear. Do not assume springdoc can infer every branch executed inside a service.

## 8. `@JsonView` Does Not Replace DTOs, Validation, or Security

`@JsonView` is useful when multiple operations share a model but need different field sets. However, it should not be used as the sole solution for everything:

- **Not authorization:** views specify which fields Jackson reads/writes. Spring Security or authorization logic must decide whether a caller can access the operation and data.
- **Not validation:** views do not check required fields, lengths, formats, or business rules. Use Bean Validation such as `@NotBlank`, `@Email`, `@Size`, and business checks.
- **Not query projection:** Jackson filters JSON after the object has already been constructed. To reduce data fetched from the database, use projections in the repository/service layer.
- **Not a replacement for dedicated DTOs:** create, update, and response payloads may have substantially different rules. Separate DTOs limit what data can be submitted and make the contract clearer.
- **Does not automatically hide fields in every serialization path:** if an object is serialized outside a view-enabled controller, behavior can differ. Understand your `ObjectMapper` configuration and data flows.

A safe rule is never to put secrets like password hashes, tokens, or credentials into a shared response DTO and rely solely on a view to mask them. Do not return such data from the service if an operation does not need it.

## 9. Testing Responses, Requests, and OpenAPI Schemas

Because views affect serialization, deserialization, and documentation, test all three layers separately:

1. **Test serialization:** call the public endpoint and verify JSON omits `email` and `internalNote`; call the detail endpoint and verify `email` is present while `internalNote` is absent.
2. **Test deserialization:** send JSON with fields allowed in `Create` or `Update` and verify they bind; send extra fields outside the view and verify the actual behavior of your Jackson configuration.
3. **Test validation:** submit missing data or constraint violations within the active view and confirm Bean Validation returns the expected error.
4. **Test OpenAPI:** open `/v3/api-docs`, locate each operation, and verify request/response schemas list the right properties.
5. **Test access control:** confirm the admin endpoint remains protected by Spring Security even when a response view already strips sensitive fields.

Example response test with MockMvc:

```java
@SpringBootTest
@AutoConfigureMockMvc
class UserControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publicViewDoesNotExposeEmailOrInternalNote() throws Exception {
        mockMvc.perform(get("/api/users/{id}", "9c1c21b1-2cc0-45c7-86a4-10cde57c6c1b"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.displayName").exists())
            .andExpect(jsonPath("$.email").doesNotExist())
            .andExpect(jsonPath("$.internalNote").doesNotExist());
    }
}
```

The test above verifies the endpoint's actual response. Another test should call `/v3/api-docs` or use `MockMvc` to verify the published schema matches the response.

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Unannotated fields still appear | `DEFAULT_VIEW_INCLUSION` is enabled | Check `ObjectMapper` and annotate fields explicitly with views. |
| Annotated fields do not appear | Active view does not match or inherit the field's view | Check interface inheritance and `@JsonView` on fields/getters. |
| Request accepts fields outside the view | Deserialization and out-of-view field handling differ from expectations | Check `JsonViewRequestBodyAdvice`, Jackson config, and test out-of-view payloads. |
| Schema in Swagger UI has extra or missing fields | Schema not generated using the expected view or custom converter interferes | Check `/v3/api-docs`, method/parameter views, and schema overrides. |
| Dynamic view returns multiple shapes while OpenAPI has one schema | Springdoc cannot infer runtime branches in code | Declare a shared schema, `oneOf`, or split operations per contract. |
| Sensitive field leaks on another endpoint | DTO serialized without a view or via another serialization path | Use separate response DTOs and test all endpoints returning data. |

## 10. Usage Guidelines

- Create small view interfaces organized by data purpose, using inheritance to extend field groups.
- Place `@JsonView` explicitly on properties that need control.
- Place the view on the controller method for responses and on the `@RequestBody` parameter for requests.
- Different request and response views can be used in the same operation.
- Verify `MapperFeature.DEFAULT_VIEW_INCLUSION` on the actual `ObjectMapper`.
- Use springdoc to generate view-aware schemas, then inspect `/v3/api-docs` for each operation.
- Use separate DTOs when request/response rules diverge significantly or sensitive data must be isolated from shared models.
- Always test serialization, deserialization, validation, and access control independently.

`@JsonView` enables multiple operations to share a Java type while exposing different JSON projections. When views are explicitly selected on controllers, Jackson is configured consistently, and springdoc generates schemas according to the views, the OpenAPI documentation will closely reflect the data clients actually receive or send. Views are a tool for shaping JSON; validation, data querying, and authorization still need to be designed in their proper application layers.

## References

- [Spring Framework – Jackson JSON Views in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/jackson.html)
- [Spring Framework – `JsonViewRequestBodyAdvice`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/JsonViewRequestBodyAdvice.html)
- [springdoc-openapi FAQ – `@JsonView` support in Spring MVC](https://springdoc.org/faq.html)
- [Jackson Databind – `MapperFeature.DEFAULT_VIEW_INCLUSION`](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/MapperFeature.html)
