# `ArgumentValue` in Spring for GraphQL

When receiving arguments from a GraphQL request, there are cases where an application needs to distinguish three states: the client did not send the argument, the client sent the argument with a `null` value, or the client sent a specific value. With a regular Java parameter bound using `@Argument`, the first two states both become `null`. Spring for GraphQL's `ArgumentValue<T>` preserves whether the argument was omitted, allowing the resolver to handle partial-update mutations accurately.

This is especially useful for PATCH operations. If the client does not send the `description` field, the server can keep the current description. If the client sends `description: null`, the server can clear the description. If the client sends a string, the server updates it to the new value.

## 1. The problem: omitted vs. explicit null

In GraphQL, a nullable argument can be omitted or explicitly sent with a `null` value. The following two requests do not carry the same meaning:

```graphql
mutation {
    updateProject(id: "project-01") {
        id
        description
    }
}
```

```graphql
mutation {
    updateProject(id: "project-01", description: null) {
        id
        description
    }
}
```

The first request does not send the `description` argument. The second request sends the argument and explicitly specifies `null`.

In a partial-update feature, we typically want the following convention:

| Input state | Possible business meaning |
|---|---|
| Omit argument | Leave the current field unchanged. |
| Send `null` | Clear the current value if the field allows empty/null. |
| Send a value | Assign the new value. |

If you use a Java parameter of type `String` or `Optional<String>` with `@Argument`, the resolver cannot cleanly distinguish the first two states in this way. `ArgumentValue<String>` retains both the value and the flag indicating whether the argument was omitted.

## 2. What is `ArgumentValue<T>`?

`ArgumentValue<T>` is a container in Spring for GraphQL, in the package:

```java
import org.springframework.graphql.data.ArgumentValue;
```

The container holds the bound value and whether the argument was omitted. Important methods:

| Method | Meaning |
|---|---|
| `isOmitted()` | `true` if the argument was not sent; `false` if sent, even when the value is `null`. |
| `isPresent()` | `true` if there is a non-`null` value. |
| `value()` | Returns the value; may be `null`. |
| `asOptional()` | Converts the value to an `Optional`; no longer distinguishes omitted from explicit null. |
| `ArgumentValue.ofNullable(value)` | Creates a container for a provided argument, even when `value` is `null`. |
| `ArgumentValue.omitted()` | Creates a container representing an omitted argument. |

Example:

```java
ArgumentValue<String> omitted = ArgumentValue.omitted();
ArgumentValue<String> explicitNull = ArgumentValue.ofNullable(null);
ArgumentValue<String> provided = ArgumentValue.ofNullable("Spring GraphQL");
```

Result:

| Container | `isOmitted()` | `isPresent()` | `value()` |
|---|---:|---:|---|
| `omitted` | `true` | `false` | `null` |
| `explicitNull` | `false` | `false` | `null` |
| `provided` | `false` | `true` | `"Spring GraphQL"` |

The key point to remember is that checking `value() == null` is not enough to conclude the argument was omitted. Check `isOmitted()` first, then handle the value.

## 3. Using `ArgumentValue` as a controller parameter

`ArgumentValue` can be declared directly on a handler parameter. You can use it in place of `@Argument` if the Java parameter name matches the GraphQL argument name, or combine it with `@Argument` to specify the argument name explicitly.

SDL:

```graphql
type Project {
    id: ID!
    name: String
}

type Mutation {
    updateProject(id: ID!, name: String): Project
}
```

Controller:

```java
@Controller
class ProjectController {

    private final ProjectService projectService;

    ProjectController(ProjectService projectService) {
        this.projectService = projectService;
    }

    @MutationMapping
    Project updateProject(
            @Argument("id") String id,
            @Argument("name") ArgumentValue<String> name) {

        if (name.isOmitted()) {
            return projectService.updateWithoutChangingName(id);
        }

        if (name.value() == null) {
            return projectService.clearName(id);
        }

        return projectService.rename(id, name.value());
    }
}
```

The resolver distinguishes three cases:

1. `name` not sent: call the service to keep the existing name.
2. `name: null` sent: call the service to clear the name if business rules allow it.
3. `name: "New name"` sent: call the service to update the name.

In the example, `name` is declared nullable in the SDL so the client can omit it or send `null`. `id` is Non-null because the mutation requires identifying the project. If `name` were declared `String!`, GraphQL would reject requests omitting it or sending `null` before calling the resolver; in that case `ArgumentValue` cannot be used to allow those two cases.

## 4. Using `ArgumentValue` in input objects

For mutations with many fields to update, group them into an input object. `ArgumentValue` is supported not only on controller parameters, but also on fields inside objects bound via `@Argument`, including nested fields.

SDL:

```graphql
input ProjectPatchInput {
    name: String
    description: String
    website: String
}

type Mutation {
    patchProject(id: ID!, input: ProjectPatchInput!): Project!
}
```

Java record:

```java
public record ProjectPatchInput(
    ArgumentValue<String> name,
    ArgumentValue<String> description,
    ArgumentValue<String> website
) {}
```

Controller:

```java
@MutationMapping
Project patchProject(
        @Argument("id") String id,
        @Argument("input") ProjectPatchInput input) {

    return projectService.patch(id, input);
}
```

In the service, handle each field independently:

```java
Project patch(String id, ProjectPatchInput input) {
    Project project = findRequired(id);

    if (!input.name().isOmitted()) {
        if (input.name().value() == null) {
            project.clearName();
        }
        else {
            project.rename(input.name().value());
        }
    }

    if (!input.description().isOmitted()) {
        project.changeDescription(input.description().value());
    }

    if (!input.website().isOmitted()) {
        project.changeWebsite(input.website().value());
    }

    return projectRepository.save(project);
}
```

The snippet above illustrates an update policy; domain methods such as `clearName`, `changeDescription`, and `changeWebsite` should be defined according to the application's business rules. If `description` or `website` does not allow `null`, validate and return a validation error instead of assigning `null`.

Because `ArgumentValue` can appear inside nested object structures, you can also use it for a field of a nested input object:

```java
public record ProjectSettingsPatch(
    ArgumentValue<Boolean> notificationsEnabled
) {}

public record ProjectPatchInput(
    ArgumentValue<String> name,
    ProjectSettingsPatch settings
) {}
```

If `settings.notificationsEnabled` is omitted, keep the current setting; if `false` is sent, disable notifications; if `null` is sent, the application can reject it or apply a dedicated rule. This distinction is especially important for Booleans because `false` is a valid value distinct from `null`.

## 5. `ArgumentValue` for an entire input argument

Besides wrapping individual fields in an input object, you can wrap the entire controller method argument:

```graphql
type Mutation {
    importProjects(input: ProjectImportInput): ImportResult!
}
```

```java
@MutationMapping
ImportResult importProjects(
        @Argument("input") ArgumentValue<ProjectImportInput> input) {

    if (input.isOmitted()) {
        return importService.importUsingDefaultInput();
    }

    if (input.value() == null) {
        return importService.rejectNullInput();
    }

    return importService.importProjects(input.value());
}
```

Here `input` can be omitted, explicitly sent as `null`, or contain a `ProjectImportInput`. If the schema declares `input: ProjectImportInput!`, the first two cases are rejected by GraphQL before the resolver runs. Only declare it nullable when the API contract truly permits those states.

## 6. Comparing `ArgumentValue`, `Optional`, and regular parameters

These three types do not carry the same amount of information:

| Parameter type | Argument omitted | Argument sent as `null` | Argument has value |
|---|---|---|---|
| `String` with `@Argument` | Usually receives `null` | Receives `null` | Receives value |
| `Optional<String>` with `@Argument` | `Optional.empty()` | `Optional.empty()` | `Optional.of(value)` |
| `ArgumentValue<String>` | `isOmitted() == true` | `isOmitted() == false`, `value() == null` | `isOmitted() == false`, `value() != null` |

`Optional` represents the presence or absence of a non-`null` value; it does not retain whether the argument was sent. `ArgumentValue` preserves the omitted state as well, making it suitable when logic needs to distinguish "leave unchanged" from "clear value".

Do not call `asOptional()` too early if you need to preserve this distinction, because both an omitted argument and an argument sent as `null` become `Optional.empty()`.

## 7. Impact of Non-null and default values in SDL

`ArgumentValue` does not replace GraphQL's input coercion rules. The schema still determines which arguments or input fields are required and whether they have default values.

| SDL | When client omits | When client sends `null` |
|---|---|---|
| `name: String` | Can be omitted; `ArgumentValue` recognizes omitted. | Allowed; `ArgumentValue` recognizes explicit null. |
| `name: String!` | Invalid request if there is no default value. | Invalid request. |
| `name: String = "Guest"` | GraphQL applies the default value. | Explicit `null` is still a sent value if the type permits it. |
| `name: String! = "Guest"` | GraphQL applies the default value. | Explicit `null` is invalid. |

If the goal is to distinguish "not sent" from "sent as null", consider not declaring a default value for that position. When the SDL provides a default, GraphQL applies the default value for omitted inputs; the resolver works with the coerced value rather than treating omission as an independent PATCH instruction.

For input objects, the same rules apply to each field. A Non-null field cannot be omitted or sent as `null` without a suitable default value. Design the SDL as nullable for fields that genuinely need to support clearing or skipping updates.

## 8. Testing all three states with `GraphQlTester`

When testing `ArgumentValue`, do not only send a request with a value. Separately test omitted, explicit null, and an actual value.

Example of three GraphQL documents:

```graphql
mutation {
    updateProject(id: "project-01") {
        id
        name
    }
}
```

```graphql
mutation {
    updateProject(id: "project-01", name: null) {
        id
        name
    }
}
```

```graphql
mutation {
    updateProject(id: "project-01", name: "Platform Team") {
        id
        name
    }
}
```

In tests, verify the service is invoked according to the meaning of each request:

| Request | Expectation |
|---|---|
| Without `name` | Keep the current name unchanged. |
| `name: null` | Clear the name if business rules allow. |
| `name: "Platform Team"` | Update the name to `Platform Team`. |

You can test the omitted flag directly in the controller or use Mockito `verify` to check that the service receives the expected command. For input objects, repeat the three cases above for each important field, and verify that unsent fields retain their existing data.

If using variables, watch how maps are created in Java: `Map.of(...)` does not allow `null` values. When testing explicit null, use a map that permits nulls, such as `HashMap`, or write literal `null` in the GraphQL document as in the examples above.

## 9. Notes when applying to partial-update APIs

`ArgumentValue` preserves input intent but does not decide business rules on its own. Define the behavior clearly for each field:

1. Does omitted mean keep unchanged, use a default, or take another action?
2. Is `null` valid to clear the data?
3. Does a provided value need normalization or validation?
4. If one field is invalid, does the entire mutation fail or do valid fields still get updated?
5. Do the changes need to occur within the same transaction?

For example, a project name might not be clearable while its description can be cleared. In that case `name: null` should produce a validation error, whereas `description: null` can clear the description. Do not apply a single null policy to every field just because they live in the same input object.

If a mutation modifies multiple fields, validate the entire patch before persisting data to avoid unintended partial updates. Place that logic in the service/domain layer; the controller only receives and forwards the state information from `ArgumentValue`.

## 10. Common pitfalls

**Only checking `value() == null`.** Both omitted and explicit null can return `null`. Check `isOmitted()` first.

**Using `Optional` and expecting to know whether the client sent the argument.** `Optional.empty()` does not distinguish omitted from explicit null. Use `ArgumentValue` when both states matter.

**Declaring a field Non-null while wanting to allow omitting or sending null.** GraphQL rejects the request before the controller runs. Change the SDL to nullable if the contract needs to allow these states.

**Setting a default value while still expecting to detect omitted.** GraphQL applies the default when the input is omitted. Avoid defaults where you need to distinguish omission from a provided value.

**Converting to `Optional` too early.** `asOptional()` loses the difference between omitted and explicit null. Only convert after handling the omitted state if logic requires the distinction.

**Not using `ArgumentValue` in nested inputs.** Spring supports this container inside object structures bound via `@Argument`; use it for PATCH fields that need to preserve all three states.

**Letting the controller decide all update rules.** Translate input states into explicit domain actions and keep rules, validation, and transactions in the appropriate service.

## Conclusion

`ArgumentValue<T>` enables Spring for GraphQL to distinguish an omitted argument from an argument explicitly sent as `null` or with a value. Use `isOmitted()` to detect the unsent state, `value()` to read the value, and `isPresent()` when confirming a non-`null` value. This container can be used directly on controller parameters or inside nested input objects, making it very useful for PATCH mutations. Combine it with properly designed nullability and default values in the SDL, and test all three states so your update API behaves consistently.

## References

- [Spring for GraphQL — Annotated Controllers: ArgumentValue](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL API — `ArgumentValue<T>`](https://docs.spring.io/spring-graphql/docs/1.4.2/api/org/springframework/graphql/data/ArgumentValue.html)
