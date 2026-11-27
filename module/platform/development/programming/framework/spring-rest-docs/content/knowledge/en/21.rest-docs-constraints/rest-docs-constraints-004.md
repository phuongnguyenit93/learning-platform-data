# ConstraintDescriptionResolver and Describing Constraints

## 1. The Role of Constraints in API Documentation

In the **SPRING_REST_DOCS** module, Spring REST Docs generates REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. Integrators need to know not only the name and type of each field, but also the data limits: strings must not be empty, emails must be valid, numbers must fall within a range, or dates must satisfy specific timing rules.

Example DTO:

```java
class CreateUserRequest {
    @NotBlank
    @Size(min = 2, max = 60)
    String name;

    @NotBlank
    @Email
    String email;

    @NotNull
    @Min(18)
    @Max(120)
    Integer age;
}
```

Bean Validation annotations store constraints directly in the source code. Spring REST Docs can read this metadata and convert it into descriptive sentences for snippets. This lets documentation reuse limits declared in DTOs instead of duplicating them manually in multiple places.

Key classes in package `org.springframework.restdocs.constraints`:

| Component | Role |
| --- | --- |
| `ConstraintDescriptions` | API for retrieving constraint descriptions by class and property |
| `ConstraintResolver` | Resolves constraints applied to a property |
| `ValidatorConstraintResolver` | Resolves constraints using a Bean Validation `Validator` |
| `ConstraintDescriptionResolver` | Converts a resolved constraint into a descriptive sentence |
| `ResourceBundleConstraintDescriptionResolver` | Default resolver that looks up descriptions from a `ResourceBundle` |
| `Constraint` | Represents a constraint with a name and configuration attributes map |

Two steps must be separated: **resolving constraints** and **describing constraints**. `ConstraintDescriptionResolver` handles only the second step. To change how metadata is discovered, look at `ConstraintResolver` or `ValidatorConstraintResolver`.

## 2. Retrieving Descriptions with ConstraintDescriptions

Basic usage:

```java
import java.util.List;
import org.springframework.restdocs.constraints.ConstraintDescriptions;

ConstraintDescriptions descriptions =
        new ConstraintDescriptions(CreateUserRequest.class);

List<String> nameDescriptions =
        descriptions.descriptionsForProperty("name");

List<String> emailDescriptions =
        descriptions.descriptionsForProperty("email");
```

`descriptionsForProperty("name")` returns a list of descriptions for constraints on the **Java property name** `name`, such as `@NotBlank` and `@Size(min = 2, max = 60)`. Exact output depends on the resolver and resource bundle.

The property name passed in is not necessarily the JSON path. If the Java property is `displayName` while the JSON uses `display_name` via `@JsonProperty`, query constraints using `displayName`, whereas the REST Docs descriptor uses the JSON path `display_name`.

By default, constraints are resolved using a Bean Validation `Validator`. Current Spring REST Docs documentation states that the default mechanism supports **property constraints**. Do not assume class-level, cross-field, or method constraints will automatically appear via `descriptionsForProperty`. Cross-field rules such as start date preceding end date must be documented and tested separately, or handled with a resolver that finds the appropriate constraints.

## 3. What Is ConstraintDescriptionResolver?

`ConstraintDescriptionResolver` is an interface that turns a `Constraint` object into a descriptive sentence:

```java
public interface ConstraintDescriptionResolver {
    String resolveDescription(Constraint constraint);
}
```

`Constraint` provides two main pieces of information:

- `getName()`: the fully qualified name of the constraint, e.g., `jakarta.validation.constraints.Size`.
- `getConfiguration()`: a map of attributes such as `min`, `max`, `value`, or `regexp`.

The resolver can look up templates by constraint name, populate them using configuration attributes, and return the result. It does not validate data; it interprets metadata that has already been resolved.

### 3.1. ResourceBundleConstraintDescriptionResolver

The default resolver `ResourceBundleConstraintDescriptionResolver` looks up a resource bundle with base name:

```text
org.springframework.restdocs.constraints.ConstraintDescriptions
```

Each key is the fully qualified constraint name plus the `.description` suffix. For example:

```properties
jakarta.validation.constraints.NotNull.description=This field must not be null
jakarta.validation.constraints.NotBlank.description=This field must not be blank
jakarta.validation.constraints.Size.description=Length must be between ${min} and ${max} characters
jakarta.validation.constraints.Email.description=Must be a valid email address
jakarta.validation.constraints.Min.description=Value must be greater than or equal to ${value}
jakarta.validation.constraints.Max.description=Value must be less than or equal to ${value}
```

Placeholders `${min}`, `${max}`, and `${value}` in the resource bundle are replaced with the constraint's configuration attributes. As a result, the same `Size` key can produce different descriptions for `name` and `password`.

Class names in keys must match the annotation namespace. Applications using Jakarta Validation have keys starting with `jakarta.validation.constraints`. Legacy projects using `javax.validation.constraints` need keys under that namespace.

### 3.2. Overriding Default Descriptions

A resource bundle is ideal when you need to translate descriptions into another language (such as Vietnamese), standardize domain terminology, add descriptions for custom annotations, or change default phrasing while keeping dynamic values from annotations.

Example:

```properties
jakarta.validation.constraints.Size.description=Length must be between ${min} and ${max} characters
```

If `name` has `min = 2, max = 60`, the returned description could be "Length must be between 2 and 60 characters". Do not hardcode numbers in individual descriptors when annotations already carry that metadata.

## 4. Customizing ConstraintDescriptionResolver

When a resource bundle is not flexible enough, you can implement the interface. The following example maps several common constraints to localized sentences and substitutes placeholders from configuration:

```java
import java.util.Map;

import org.springframework.restdocs.constraints.Constraint;
import org.springframework.restdocs.constraints.ConstraintDescriptionResolver;

class VietnameseConstraintDescriptionResolver
        implements ConstraintDescriptionResolver {

    private static final Map<String, String> TEMPLATES = Map.of(
        "jakarta.validation.constraints.NotBlank",
        "Must not be blank",
        "jakarta.validation.constraints.Email",
        "Must be a valid email address",
        "jakarta.validation.constraints.Size",
        "Length must be between ${min} and ${max} characters",
        "jakarta.validation.constraints.Min",
        "Value must be greater than or equal to ${value}"
    );

    @Override
    public String resolveDescription(Constraint constraint) {
        String template = TEMPLATES.get(constraint.getName());
        if (template == null) {
            return "Must satisfy constraint " + constraint.getName();
        }

        String result = template;
        for (Map.Entry<String, Object> entry
                : constraint.getConfiguration().entrySet()) {
            result = result.replace(
                    "${" + entry.getKey() + "}",
                    String.valueOf(entry.getValue()));
        }
        return result;
    }
}
```

Wiring the custom resolver:

```java
ConstraintDescriptions descriptions =
        new ConstraintDescriptions(
                CreateUserRequest.class,
                new VietnameseConstraintDescriptionResolver());

List<String> nameRules =
        descriptions.descriptionsForProperty("name");
```

This constructor replaces the description resolver; constraint discovery still uses the default `ValidatorConstraintResolver`.

This is a minimal example. Production implementations need policies for unreplaced placeholders, data types, locales, and constraints without templates. If you want to preserve standard placeholder-substitution behavior, customizing the resource bundle is usually preferable to reimplementing the logic.

## 5. Selecting a ResourceBundle by Locale

`ResourceBundleConstraintDescriptionResolver` provides a default constructor and a constructor taking a specific `ResourceBundle`. Example:

```java
import java.util.Locale;
import java.util.ResourceBundle;

import org.springframework.restdocs.constraints.ConstraintDescriptions;
import org.springframework.restdocs.constraints.ResourceBundleConstraintDescriptionResolver;

ResourceBundle bundle = ResourceBundle.getBundle(
        "org.springframework.restdocs.constraints.ConstraintDescriptions",
        Locale.forLanguageTag("vi"));

ResourceBundleConstraintDescriptionResolver resolver =
        new ResourceBundleConstraintDescriptionResolver(bundle);

ConstraintDescriptions descriptions =
        new ConstraintDescriptions(CreateUserRequest.class, resolver);
```

A bundle layout following the standard base name might look like:

```text
src/test/resources/
└── org/
    └── springframework/
        └── restdocs/
            └── constraints/
                ├── ConstraintDescriptions.properties
                └── ConstraintDescriptions_vi.properties
```

The default constructor uses the default locale and thread context class loader. If you need consistent results across developer machines and CI, specify the locale explicitly or standardize the build environment configuration.

You do not need to write a custom resolver solely to translate descriptions. A resource bundle is simpler for that case.

## 6. Merging Constraint Descriptions into FieldDescriptor

After retrieving descriptions, you can append them to the field's description:

```java
ConstraintDescriptions constraints =
        new ConstraintDescriptions(CreateUserRequest.class);

String nameDescription = "User display name. "
        + String.join("; ",
            constraints.descriptionsForProperty("name"));

requestFields(
    fieldWithPath("name").description(nameDescription)
)
```

You can create a shared helper:

```java
static String withConstraints(
        String businessDescription,
        List<String> constraintDescriptions) {

    if (constraintDescriptions.isEmpty()) {
        return businessDescription;
    }

    return businessDescription + " Constraints: "
            + String.join("; ", constraintDescriptions);
}
```

Using the helper:

```java
ConstraintDescriptions userConstraints =
        new ConstraintDescriptions(CreateUserRequest.class);

requestFields(
    fieldWithPath("name").description(
        withConstraints(
            "User display name",
            userConstraints.descriptionsForProperty("name"))),
    fieldWithPath("email").description(
        withConstraints(
            "Contact address",
            userConstraints.descriptionsForProperty("email")))
)
```

`requestFields` is usually the right fit because Bean Validation is typically applied to request DTOs. You can also add constraints to response fields if the response contract truly guarantees those rules, but do not assume input validation proves every response obeys the same constraints.

## 7. Passing Constraints as Metadata for Custom Snippets

If you want to keep business descriptions separate from constraint descriptions, you can attach metadata to the descriptor:

```java
import static org.springframework.restdocs.snippet.Attributes.key;

List<String> nameConstraints =
        userConstraints.descriptionsForProperty("name");

requestFields(
    fieldWithPath("name")
        .description("User display name")
        .attributes(key("constraints").value(nameConstraints))
)
```

An attribute does not automatically create a new column in the default snippet. A custom snippet template must read `constraints` and render it. Example target table:

| Path | Type | Description | Constraints |
| --- | --- | --- | --- |
| name | String | User display name | Must not be blank; 2 to 60 characters long |
| email | String | Contact address | Valid email format |

This is appropriate when a team wants to standardize constraints into a dedicated column. Configure the template properly and inspect the rendered snippet; do not assume descriptor attributes appear automatically in default output.

## 8. MockMvc: Generating Request Fields with Constraints

Example using JUnit Jupiter, MockMvc, Spring REST Docs MockMvc, the Bean Validation API, and a provider such as Hibernate Validator. With Spring Boot, the validation dependency is typically supplied via the corresponding validation starter.

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.constraints.ConstraintDescriptions;
import org.springframework.restdocs.junit.jupiter.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class CreateUserConstraintDocumentationTest {

    private MockMvc mockMvc;

    private final ConstraintDescriptions constraints =
            new ConstraintDescriptions(CreateUserRequest.class);

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new UserController())
                .apply(documentationConfiguration(documentation))
                .build();
    }

    @Test
    void documentCreateUserRequestConstraints() throws Exception {
        String nameDescription = "User name. "
                + String.join("; ",
                    constraints.descriptionsForProperty("name"));
        String emailDescription = "Email address. "
                + String.join("; ",
                    constraints.descriptionsForProperty("email"));

        mockMvc.perform(post("/api/users")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "name": "Lan Nguyen",
                              "email": "lan@example.test"
                            }
                            """))
                .andExpect(status().isCreated())
                .andDo(document("users-create-constraints",
                        requestFields(
                                fieldWithPath("name")
                                        .description(nameDescription),
                                fieldWithPath("email")
                                        .description(emailDescription)
                        )
                ));
    }

    record CreateUserRequest(
            @NotBlank @Size(min = 2, max = 60) String name,
            @NotBlank @Email String email) {}

    @RestController
    static class UserController {
        @PostMapping("/api/users")
        ResponseEntity<Void> create(
                @Valid @RequestBody CreateUserRequest request) {
            return ResponseEntity.status(201).build();
        }
    }
}
```

In this example, `ConstraintDescriptions` reads annotations on the DTO; `descriptionsForProperty` returns descriptions by property name; `String.join` merges constraints into `FieldDescriptor`; `@Valid` triggers Bean Validation when Spring binds the request; `requestFields` verifies the payload and generates the snippet.

The test sends valid data to receive `201 Created`. Real applications also need tests with invalid requests to prove validation is active and returns the expected contract status/errors. Having descriptive sentences in a snippet does not prove validation is enforced at runtime.

## 9. Custom Constraints

Applications may define custom constraints such as `@VietnamesePhoneNumber` or `@ValidSku`. To describe them via a bundle, the key uses the annotation's fully qualified name plus `.description`.

Example annotation:

```java
@Constraint(validatedBy = VietnamesePhoneNumberValidator.class)
@Target({ FIELD, PARAMETER, ANNOTATION_TYPE })
@Retention(RUNTIME)
public @interface VietnamesePhoneNumber {
    String message() default "Invalid phone number";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
```

Key in the bundle:

```properties
com.example.validation.VietnamesePhoneNumber.description=Must be a Vietnamese phone number in a format accepted by the API
```

If the bundle lacks a matching key, the default resolver cannot provide the desired domain description. Add the message and write a test to verify it.

With a custom resolver, define a policy for unknown constraints: return a fallback containing the constraint name or fail early in documentation tests to force adding a description. Do not return an empty string or silently skip new constraints if the contract requires full disclosure.

## 10. ConstraintResolver and ValidatorConstraintResolver

Spring REST Docs separates the **constraint discovery** mechanism from the **constraint description** mechanism:

| Component | Responsibility | When to Customize? |
| --- | --- | --- |
| `ValidatorConstraintResolver` | Uses Bean Validation `Validator` to find constraints on a property | When you need to swap the Validator/provider or metadata access |
| `ConstraintResolver` | Abstracts constraint lookup by property and class | When you need a different source or lookup mechanism |
| `ConstraintDescriptionResolver` | Converts resolved constraints into descriptive sentences | When translating, changing terminology, or supporting custom constraints |
| `ResourceBundleConstraintDescriptionResolver` | Looks up descriptions from a resource bundle | When messages need to follow a locale/bundle |

By default:

```java
new ConstraintDescriptions(CreateUserRequest.class)
```

uses a Validator-based resolver to find constraints and a resource-bundle resolver to describe them. If you only need to change the wording or language, passing a new `ConstraintDescriptionResolver` or bundle is enough. If you want to change how metadata is discovered, supply a custom `ConstraintResolver` through the corresponding constructor.

Current Spring REST Docs documentation notes that support is limited to property constraints. Cross-field rules such as `startDate < endDate` require separate business documentation and tests; do not assume `descriptionsForProperty` automatically reads class-level rules.

## 11. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Empty description list | Property has no constraints, wrong name, or Validator cannot find it | Check the DTO and Java property name |
| No description for custom annotation | Bundle is missing key by fully qualified name | Add `.description` key or custom resolver |
| Placeholders are not replaced | Attribute key mismatch or custom resolver does not handle them | Use the proper resolver and placeholders |
| javax/jakarta namespace mismatch | Annotations and bundle use different namespaces | Match the namespace to your dependencies |
| Business meaning duplicated in description | Constraints appended to text that already repeats them | Separate business meaning from validation rules |
| Constraints do not match HTTP behavior | Annotations present but validation does not run | Check `@Valid`, provider, and write invalid request tests |
| Template does not display attribute | Using default snippet | Configure template to read the attribute |
| Class-level constraint does not appear | Default mechanism focuses on property constraints | Document/test cross-field rules or use a custom resolver |
| Results differ between local machine and CI | Different default locales | Specify locale/resource bundle explicitly |

## 12. Practice Exercise

Use `CreateUserRequest` from section 8:

1. Retrieve descriptions for `@NotBlank` and `@Size(min = 2, max = 60)` via `descriptionsForProperty("name")`.
2. Add `@Pattern` to a `phone` field and add a localized description in the bundle.
3. Create `@VietnamesePhoneNumber`, add a bundle key by its fully qualified name, and verify the description.
4. Replace the default resolver with `VietnameseConstraintDescriptionResolver`; test both a known constraint and one without a template.
5. Pass a Vietnamese locale bundle into `ResourceBundleConstraintDescriptionResolver` and compare it with the default locale.
6. Merge constraint descriptions into `requestFields` and verify the snippet includes min/max limits.
7. Create a custom snippet template with a Constraints column, attach the `constraints` attribute, and verify the template renders properly.
8. Send an invalid request to verify Bean Validation actually blocks the request.
9. Add a rule requiring start date before end date; write business tests and separate documentation.

**Completion criteria:** you can extract constraints from Bean Validation using `ConstraintDescriptions`, understand the boundary between `ConstraintResolver` and `ConstraintDescriptionResolver`, override descriptions with a resource bundle, write a custom resolver, attach descriptions to descriptors/snippets, and verify documentation reflects actively enforced validation.

## References

- [Spring REST Docs — Bean Validation Constraints](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/constraints.html): constraint resolution, resource bundles, and inserting descriptions into snippets.
- [Spring REST Docs — ConstraintDescriptions API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/constraints/ConstraintDescriptions.html): constructors and `descriptionsForProperty`.
- [Spring REST Docs — ConstraintDescriptionResolver API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/constraints/ConstraintDescriptionResolver.html): `resolveDescription(Constraint)`.
- [Spring REST Docs — Constraint API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/constraints/Constraint.html): `getName()` and `getConfiguration()`.
