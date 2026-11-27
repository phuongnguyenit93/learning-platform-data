# Custom Descriptions for Constraints

## 1. Lesson Objectives

Bean Validation specifies that a property must not be empty, must fall within a numeric range, or must match a pattern. Spring REST Docs can resolve constraint metadata and convert it into descriptive sentences for API documentation. However, default descriptions may not match your language, terminology, or product conventions. In such cases, you need to **customize how constraints are described**.

This lesson belongs to the **Constraints** chapter of the **SPRING_REST_DOCS** module. The module teaches how to produce verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured; generate snippets for requests, responses, payloads, parameters, and headers; and compile Asciidoctor/Markdown in build and CI pipelines.

After this lesson, you will be able to distinguish runtime validation messages from documentation descriptions; override descriptions via a `ResourceBundle`; use constraint attributes; pass a custom resolver to `ConstraintDescriptions`; attach descriptions to field descriptors; and test snippet contents to prevent drift.

> Spring REST Docs' central API is `ConstraintDescriptions`. The default mechanism uses a Bean Validation `Validator` to find property constraints and `ResourceBundleConstraintDescriptionResolver` to describe them. Prefer a resource bundle when you only need to change phrasing; write a custom resolver when special processing is required.

## 2. Runtime Messages Differ from Documentation Descriptions

An annotation can declare a message:

~~~java
@NotBlank(message = "Name must not be blank")
private String name;
~~~

This message serves **runtime validation**: the application returns it when a request violates the rule. Spring REST Docs has its own description mechanism for explaining constraints in documentation.

| Item | Purpose | Example |
| --- | --- | --- |
| Bean Validation message | Report error when a request is invalid | Name must not be blank. |
| Constraint description | Explain the rule in documentation | Must provide a name with at least one non-whitespace character. |
| Field descriptor description | Explain the meaning of the field | User's display name. |
| HTTP error response | Tell the client how the request was rejected | 400 and error payload per contract. |

Changing the annotation message does not necessarily change the documentation description. Changing REST Docs' resource bundle does not automatically change the error message returned by the controller either.

## 3. ConstraintDescriptions and the Default Resolvers

Example DTO:

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class RegisterMemberRequest {
    @NotBlank
    @Size(min = 2, max = 80)
    private String fullName;

    @NotBlank
    @Email
    @Size(max = 254)
    private String email;

    @Min(18)
    private Integer age;
}
~~~

Retrieving descriptions:

~~~java
import org.springframework.restdocs.constraints.ConstraintDescriptions;

ConstraintDescriptions descriptions =
    new ConstraintDescriptions(RegisterMemberRequest.class);

List<String> nameRules =
    descriptions.descriptionsForProperty("fullName");

List<String> emailRules =
    descriptions.descriptionsForProperty("email");
~~~

The default constructor uses:

- `ValidatorConstraintResolver` to find property constraints via a Bean Validation `Validator`.
- `ResourceBundleConstraintDescriptionResolver` to obtain descriptive sentences from a resource bundle.

The default discovery mechanism currently supports property constraints. Do not expect the resolver to automatically extract every class-level rule, method parameter constraint, or service-layer business rule. The result of `descriptionsForProperty` is a list of `String`; the author must attach them to descriptors or templates.

## 4. Overriding Descriptions via a Resource Bundle

The simplest approach is creating a resource bundle with base name:

~~~text
org.springframework.restdocs.constraints.ConstraintDescriptions
~~~

Each key is the fully qualified class name of the constraint annotation plus the `.description` suffix. With Jakarta Bean Validation:

~~~properties
jakarta.validation.constraints.NotBlank.description=Must not be null, empty, or whitespace-only
jakarta.validation.constraints.NotNull.description=Value must not be null
jakarta.validation.constraints.Size.description=Length must be within the declared limits
jakarta.validation.constraints.Email.description=Must be a valid email address format
jakarta.validation.constraints.Min.description=Value must be greater than or equal to the minimum limit
jakarta.validation.constraints.Max.description=Value must not exceed the maximum limit
~~~

Place the bundle on the classpath according to Java `ResourceBundle` rules. You can use a default bundle and a localized bundle following project conventions. Use package `jakarta.validation.constraints` for Jakarta Bean Validation; legacy projects using `javax.validation` must declare keys matching the actual annotation package.

### 4.1. Overriding a Single Constraint

A resource bundle can override just one key. Example:

~~~properties
jakarta.validation.constraints.NotBlank.description=Must not be blank or contain only spaces
~~~

The description for `NotBlank` comes from the custom bundle; other constraints on the same property are still handled normally by the resolver. You do not need to write a brand-new resolver just to change one sentence.

If multiple locales exist, ensure the locale selected in the build matches the documentation language. Do not rely on a developer machine's personal locale because CI may run with different settings.

### 4.2. Using Constraint Attributes

Some constraints carry attributes:

| Constraint | Attribute | Meaning |
| --- | --- | --- |
| `@Min(18)` | `value` | Minimum threshold. |
| `@Max(120)` | `value` | Maximum threshold. |
| `@Size(min=2,max=80)` | `min`, `max` | Size bounds. |
| `@DecimalMin` | `value`, `inclusive` | Threshold and boundary inclusivity. |
| `@Digits` | `integer`, `fraction` | Integral and fractional digit counts. |
| `@Pattern` | `regexp`, `flags` | Pattern and flags. |

Resource bundles support placeholders pointing to constraint attributes. The default `Min` description can use a placeholder for `value`. Example localized bundle:

~~~properties
jakarta.validation.constraints.Min.description=Value must be at least the declared minimum threshold
jakarta.validation.constraints.Max.description=Value must not exceed the declared maximum threshold
jakarta.validation.constraints.Size.description=Length must be within the declared min and max range
~~~

When specific numbers need to be shown, use placeholders matching the exact attribute names provided by the constraint, then verify the actual description returned by the resolver. If the bundle has the wrong key, wrong package, or the locale is not loaded, output will not match expectations.

For `Pattern`, avoid printing long raw regexes to API consumers. You can override the description in business terms, e.g., "Order code consists of 3–20 uppercase letters, digits, or hyphens", provided the wording accurately matches the real validator.

### 4.3. Avoiding Wrong Boundary and Unit Descriptions

`DecimalMin`/`DecimalMax` can distinguish inclusive from exclusive bounds. If `inclusive=false`, phrasing like "0.01 or higher" can misstate semantics. `Size` also has different units: characters for strings, elements for collections/arrays, entries for maps. Phrase descriptions according to the actual data type.

## 5. ResourceBundleConstraintDescriptionResolver

`ResourceBundleConstraintDescriptionResolver` is the built-in implementation of `ConstraintDescriptionResolver`. The no-arg constructor uses the default bundle at base name `org.springframework.restdocs.constraints.ConstraintDescriptions` and the default locale. Another constructor accepts a specific `ResourceBundle`.

Example:

~~~java
import java.util.Locale;
import java.util.ResourceBundle;

import org.springframework.restdocs.constraints.ConstraintDescriptions;
import org.springframework.restdocs.constraints.ResourceBundleConstraintDescriptionResolver;

ResourceBundle bundle = ResourceBundle.getBundle(
    "org.springframework.restdocs.constraints.ConstraintDescriptions",
    Locale.forLanguageTag("vi")
);

ResourceBundleConstraintDescriptionResolver resolver =
    new ResourceBundleConstraintDescriptionResolver(bundle);

ConstraintDescriptions descriptions =
    new ConstraintDescriptions(RegisterMemberRequest.class, resolver);
~~~

This is helpful when you need a fixed locale instead of relying on the JVM's default locale. The base name must point to a resource on the classpath. If the bundle is not found, check the classpath, bundle name, locale, and fully qualified keys.

### 5.1. ConstraintDescriptions Constructors

| Constructor | Effect |
| --- | --- |
| `ConstraintDescriptions(Class<?>)` | Default resolvers for discovery and description. |
| `ConstraintDescriptions(Class<?>, ConstraintResolver)` | Replaces constraint discovery, keeps default description resolver. |
| `ConstraintDescriptions(Class<?>, ConstraintDescriptionResolver)` | Keeps default discovery, replaces description resolver. |
| `ConstraintDescriptions(Class<?>, ConstraintResolver, ConstraintDescriptionResolver)` | Customizes both discovery and description. |

If you only want to change wording, the constructor taking `ConstraintDescriptionResolver` is sufficient. Do not replace the Validator resolver if property constraint lookup already works properly.

## 6. Writing a Custom ConstraintDescriptionResolver

The `ConstraintDescriptionResolver` interface has one method:

~~~java
String resolveDescription(Constraint constraint);
~~~

The method receives a `Constraint` built by Spring REST Docs from validation metadata and returns a descriptive sentence. When custom logic is needed, implement this interface. A safe pattern is delegating to `ResourceBundleConstraintDescriptionResolver` first, then applying controlled normalization rules.

~~~java
import org.springframework.restdocs.constraints.Constraint;
import org.springframework.restdocs.constraints.ConstraintDescriptionResolver;

public class ProjectConstraintDescriptionResolver
        implements ConstraintDescriptionResolver {

    private final ConstraintDescriptionResolver delegate;

    public ProjectConstraintDescriptionResolver(
            ConstraintDescriptionResolver delegate) {
        this.delegate = delegate;
    }

    @Override
    public String resolveDescription(Constraint constraint) {
        String description = this.delegate.resolveDescription(constraint);
        // Apply custom tested rules if needed.
        return description;
    }
}
~~~

This example is a wrapper illustrating the extension point; the constructor must be supplied with an appropriate delegate. Without additional logic, the result remains the delegate's description. Do not assume a class translates automatically just because its name starts with `Project`.

Usage:

~~~java
ResourceBundleConstraintDescriptionResolver resourceResolver =
    new ResourceBundleConstraintDescriptionResolver(bundle);

ConstraintDescriptionResolver customResolver =
    new ProjectConstraintDescriptionResolver(resourceResolver);

ConstraintDescriptions descriptions =
    new ConstraintDescriptions(RegisterMemberRequest.class, customResolver);
~~~

When a resolver actually transforms phrasing, test the output for each custom rule, locale fallback, and unmapped cases. Avoid blanket string replacements if a phrase depends on attributes or context.

## 7. Describing Custom Constraint Annotations

Applications can define custom annotations:

~~~java
@Target({ ElementType.FIELD, ElementType.PARAMETER })
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = StrongPasswordValidator.class)
public @interface StrongPassword {
    String message() default "Password does not meet policy";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

If the `Validator` recognizes it as a property constraint, REST Docs can extract the corresponding metadata. To supply a description, add a resource bundle key by the fully qualified annotation name:

~~~properties
com.example.validation.StrongPassword.description=Password must have at least 12 characters and satisfy the system password policy
~~~

Descriptions must reflect the actual validator. If the validator only checks length, do not add uppercase/digit requirements. If policy varies by tenant or configuration, documentation must explain the scope rather than stating one fixed limit for all users.

## 8. Attaching Descriptions to Field Descriptors

Once you have the list of descriptions, you can concatenate them directly into the description:

~~~java
ConstraintDescriptions descriptions =
    new ConstraintDescriptions(RegisterMemberRequest.class, resolver);

requestFields(
    fieldWithPath("fullName").description(
        "Full name. " + String.join("; ",
            descriptions.descriptionsForProperty("fullName"))
    ),
    fieldWithPath("email").description(
        "Contact email. " + String.join("; ",
            descriptions.descriptionsForProperty("email"))
    )
)
~~~

This works with the default template because constraints live inside the description. It is easy to implement, though it can make the description column long for large DTOs.

### 8.1. Descriptor Attributes and Custom Snippets

You can store constraints in a dedicated attribute:

~~~java
import static org.springframework.restdocs.snippet.Attributes.key;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

FieldDescriptor email = fieldWithPath("email")
    .description("Contact email")
    .attributes(key("constraints").value(
        String.join("; ", descriptions.descriptionsForProperty("email"))
    ));
~~~

The `constraints` key is project-named. The default template will not render the attribute automatically unless it reads this key. A custom fields snippet can add a Constraints column:

| Field | Description | Constraints |
| --- | --- | --- |
| fullName | Full name | Must not be blank; length 2–80 characters. |
| email | Contact email | Valid email format; maximum 254 characters. |

To show a dedicated column, copy the fields template matching your Spring REST Docs version, add logic to read the descriptor attribute, and run tests to verify the snippet. Do not use template syntax from a different version without checking.

## 9. HTTP Tests Proving Descriptions Reflect Validation

Example DTO:

~~~java
public class CreateMemberRequest {
    @NotBlank
    @Size(min = 2, max = 80)
    private String name;

    @NotBlank
    @Email
    private String email;
}
~~~

Valid test:

~~~java
@Test
void createMemberWithValidInput() throws Exception {
    ConstraintDescriptions descriptions =
        new ConstraintDescriptions(CreateMemberRequest.class, resolver);

    mockMvc.perform(post("/api/members")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .content("""
                {"name":"Lan Nguyen","email":"lan@example.com"}
                """))
        .andExpect(status().isCreated())
        .andDo(document("members-create",
            requestFields(
                fieldWithPath("name").description(
                    "Member name. " + String.join("; ",
                        descriptions.descriptionsForProperty("name"))
                ),
                fieldWithPath("email").description(
                    "Email. " + String.join("; ",
                        descriptions.descriptionsForProperty("email"))
                )
            )
        ));
}
~~~

This example assumes the endpoint and fixture return `201 Created`, and `resolver` was configured prior to the test. The test class requires MockMvc/REST Docs setup and corresponding imports.

Invalid test:

~~~java
@Test
void rejectInvalidMemberEmail() throws Exception {
    mockMvc.perform(post("/api/members")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {"name":"Lan Nguyen","email":"not-an-email"}
                """))
        .andExpect(status().isBadRequest())
        .andDo(document("members-create-invalid"));
}
~~~

`400 Bad Request` is an assumed error contract. An application may map validation failures to another status or schema. Assert the real response and describe the real error fields; do not treat the error format above as a REST Docs default.

### 9.1. Testing Boundary Values

| Rule | Valid Value | Values to Test |
| --- | --- | --- |
| `@NotBlank` | `"Lan"` | Empty string, whitespace, null. |
| `@Size(min=2,max=80)` | Length 2 and 80 | Length 1 and 81. |
| `@Email` | `lan@example.com` | Malformed string. |
| `@Min(18)` | 18 | 17. |
| `@Max(120)` | 120 | 121. |

If the resource bundle changes, HTTP validation may still pass while snippet descriptions change. Review snippet diffs or add appropriate description output checks in CI.

## 10. Locale and Stability in CI

The default constructor of `ResourceBundleConstraintDescriptionResolver` uses the default locale and thread context class loader. If a developer machine and CI have different locales, snippets can be generated in two different languages.

For stability:

- Specify an explicit locale when creating the `ResourceBundle`.
- Ensure the bundle is on the classpath of the snippet-generating task.
- Do not depend on a machine's personal locale.
- Verify UTF-8 and localized characters after the build.
- Keep descriptions stable so diffs reflect only intentional changes.

When fixed output is required, load a `ResourceBundle` for the desired locale and pass it to the bundle-accepting constructor as shown above.

## 11. Limitations to Understand

Customizing descriptions improves documentation language but does not alter validation behavior:

1. Descriptions do not enforce validation; HTTP tests must still send inputs and assert outcomes.
2. Default `ConstraintDescriptions` resolves property constraints; class-level, method parameter, and domain constraints require separate descriptions.
3. Resource bundles only replace phrasing for annotations with keys; they do not discover all business rules.
4. Custom templates only render metadata if descriptors attach attributes under the expected key.
5. Placeholders must accurately reflect attributes, units, and inclusive/exclusive bounds.
6. Documentation descriptions are not synonymous with runtime error messages.
7. If a constraint depends on tenant, feature flag, or dynamic configuration, documentation must clarify the scope.

## 12. CI and Change Review

~~~mermaid
flowchart TD
    A["Annotation or policy changes"] --> B["Update ResourceBundle / resolver"]
    B --> C["HTTP tests: valid, invalid, and boundary"]
    C --> D{"Validation assertions pass?"}
    D -->|No| E["Fail build"]
    D -->|Yes| F["Generate REST Docs snippets"]
    F --> G["Review descriptions and field tables"]
    G --> H["Render Asciidoctor/Markdown"]
    H --> I{"Snippets and docs pass?"}
    I -->|No| E
    I -->|Yes| J["Package / Publish"]
~~~

When descriptions change, review both raw request/response snippets and `request-fields`/`response-fields`. The render task must run after the snippet-generating tests and must not include stale artifacts. If a custom template changes, verify the constraints column does not hide existing field descriptions.

## 13. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Descriptions stay in English | Localized bundle not loaded or wrong locale | Check base name, locale, classpath, and resolver. |
| Custom key has no effect | Wrong fully qualified annotation name or missing `.description` suffix | Verify exact package and key. |
| Placeholder not replaced | Wrong attribute name or constraint lacks that attribute | Inspect metadata and output. |
| Runtime message changed but docs did not | Bean Validation message differs from REST Docs description | Update the documentation bundle as well. |
| Docs changed but runtime error stayed the same | Only edited the REST Docs bundle | Update validation messages if needed. |
| Custom description does not appear | Not attached to descriptor or template does not read attribute | Check descriptors and template. |
| CI locale differs from dev machine | Using default JVM locale | Fix the locale when constructing the resolver. |
| Custom constraint has no description | Bundle is missing key | Add key or custom resolver. |
| Description states wrong boundary | Did not check inclusive/exclusive | Cross-check attributes and boundary tests. |
| Business rule does not appear | Not a property constraint | Document and test at the domain/API layer. |

## 14. Practice Exercise

Create DTO `CreateProductRequest`:

~~~java
public class CreateProductRequest {
    @NotBlank
    @Size(min = 2, max = 100)
    private String name;

    @NotNull
    @DecimalMin(value = "0.01", inclusive = true)
    @DecimalMax(value = "1000000.00", inclusive = true)
    private BigDecimal price;

    @NotBlank
    @Pattern(regexp = "[A-Z0-9-]{3,20}")
    private String sku;
}
~~~

Steps:

1. Use `ConstraintDescriptions` to retrieve descriptions for `name`, `price`, and `sku`.
2. Create a resource bundle matching Spring REST Docs' base name; override `NotBlank`, `Size`, `DecimalMin`, and `DecimalMax`.
3. Use placeholders for attributes and verify returned descriptions show the correct min/max.
4. Create a resolver with a localized `ResourceBundle`; confirm CI produces identical output.
5. Attach descriptions to field descriptors; try both merging into `description` and a `constraints` column via a custom template.
6. Write HTTP tests for a valid request, price equal to 0, SKU failing the pattern, and name exceeding length.
7. Compare runtime error messages with documentation descriptions.
8. Change a limit and review the snippet diff, final docs, and pipeline.

**Completion criteria:** customize constraint descriptions to match project language/terminology; render them cleanly in field snippets; understand the difference between runtime messages and documentation descriptions; maintain HTTP tests and CI to keep docs synchronized with validation logic.

## References

- [Spring REST Docs — Bean Validation Constraints](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/constraints.html)
- [Spring REST Docs — ConstraintDescriptions API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/constraints/ConstraintDescriptions.html)
- [Spring REST Docs — ResourceBundleConstraintDescriptionResolver API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/constraints/ResourceBundleConstraintDescriptionResolver.html)
- [Spring REST Docs — ConstraintDescriptionResolver API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/constraints/ConstraintDescriptionResolver.html)
- [Jakarta Bean Validation — Specification](https://jakarta.ee/specifications/bean-validation/)
