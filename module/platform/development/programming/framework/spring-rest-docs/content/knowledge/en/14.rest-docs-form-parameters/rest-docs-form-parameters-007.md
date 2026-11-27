# Naming snippets and form descriptions in Spring REST Docs

## 1. Why do snippet names and form descriptions matter?

Spring REST Docs generates documentation from passing HTTP tests. For endpoints accepting **application/x-www-form-urlencoded** forms, **formParameters(...)** generates a table of field names and descriptions for each parameter. The **document(...)** call specifies the **identifier** used to group snippets such as request, response, headers, and form parameters.

These two choices directly affect documentation maintainability:

- Clear identifiers help locate the right example, separate use cases, and prevent snippet overwrites across tests.
- Clear parameter descriptions tell clients what each field is for, whether it is required, and which formats and value ranges are accepted.
- Consistent naming and writing conventions keep Asciidoctor/Markdown pages readable, even as the API grows to many endpoints and request variants.

In the **SPRING_REST_DOCS** module, the goal is to create verifiable REST API documentation using MockMvc, WebTestClient, or REST Assured; generate snippets for requests, responses, payloads, parameters, and headers; and then assemble documentation and integrate it into build/CI. This lesson focuses on naming and describing **form parameters** so readers clearly understand the HTTP contract verified by tests.

## 2. What is the identifier in document(...)?

When you write:

```java
mockMvc.perform(post("/registrations")
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("email", "mai@example.com"))
    .andDo(document("registrations/create-form",
        formParameters(
            parameterWithName("email")
                .description("Registration email; required")
        )
    ));
```

The string **registrations/create-form** is the document identifier. With Spring REST Docs' output directory configuration, it becomes a subdirectory path beneath the snippets root:

```text
build/generated-snippets/
└── registrations/
    └── create-form/
        ├── form-parameters.adoc
        ├── http-request.adoc
        ├── http-response.adoc
        └── ...
```

The snippet filename is determined by the snippet type; the identifier determines the folder group. For example, **formParameters(...)** creates **form-parameters.adoc**, while the default HTTP request snippet creates **http-request.adoc**.

**An identifier is not an endpoint URL, a Java method name, or an AsciiDoc filename.** It is the naming key for an HTTP example's snippet set. Name it intentionally, readably, and stably.

## 3. Identifier naming conventions

### 3.1. Organize by resource and action

A simple convention:

```text
<resource>/<action>-<request-format>[-<scenario>]
```

Examples:

| Identifier | Purpose |
| --- | --- |
| registrations/create-form | Create registration using a URL-encoded form |
| registrations/create-json | Create registration using a JSON body |
| registrations/create-form-minimal | Minimal form request omitting optional fields |
| registrations/create-form-validation-error | Invalid form request and error response |
| subscriptions/update-form | Update subscription using a form |
| uploads/create-multipart | Upload multipart data |

This convention makes the snippet folder layout reflect resources and use cases rather than test class names. If a team already has another standard (such as api/v1/registrations/create), keep that standard consistent across the entire project.

### 3.2. Each scenario with distinct HTTP content should have its own identifier

Do not let two different tests write to **registrations/create-form** if each produces a different request or response. For instance:

```java
// Full request test
document("registrations/create-form",
    formParameters(/* descriptors */));

// Minimal request test
document("registrations/create-form-minimal",
    formParameters(/* same contract, but request omits optional fields */));
```

If identifiers collide, snippets with the same filename at the same path may be overwritten or produce confusing output depending on test execution order and build configuration. One identifier should represent **one meaningful request/response example**.

You do not need an identifier for every unit test. Only tests intended to produce documentation should call document(...); auxiliary validation tests can assert status/body without generating snippets. For example, tests checking multiple invalid email variants do not necessarily need multiple snippet sets.

### 3.3. Use stable names without embedding volatile data

Avoid identifiers that depend on emails, usernames, random IDs, timestamps, or test run counters. Names like **registrations/create-form** are durable and easy to reference. When distinguishing scenarios, use scenario terms such as **minimal**, **validation-error**, or **with-referral** instead of individual data values.

### 3.4. Encode the format in the identifier when an endpoint accepts multiple body types

An endpoint can accept both URL-encoded forms and JSON if the controller declares matching consumes mappings. Separate them:

```text
registrations/create-form
registrations/create-json
```

Both snippet sets are then generated independently:

```text
registrations/
├── create-form/
│   ├── form-parameters.adoc
│   └── http-request.adoc
└── create-json/
    ├── request-fields.adoc
    └── http-request.adoc
```

Forms use **formParameters(parameterWithName(...))**; JSON uses **requestFields(fieldWithPath(...))**. Do not share an identifier simply because field names match.

## 4. Writing descriptions for each form parameter

### 4.1. Descriptions must help clients send valid requests

A simple descriptor:

```java
parameterWithName("email")
    .description("Email address used to create the registration; required.")
```

Description content should answer practical questions:

| Information | Integrator's question | Example |
| --- | --- | --- |
| Purpose | What is the field used for? | Email to receive registration notifications |
| Presence | Is it required? | Required; must not be blank |
| Type/format | What format should be sent? | Valid email; UTF-8 string |
| Allowed values | What options exist? | basic or pro |
| Value range | What are the limits? | Integer from 1 to 5 |
| Default value | What does the server do when omitted? | Defaults to basic |
| Multiple values | Can the name be repeated? | Send topics once per topic |
| Conditions | Are there special rules? | Send only when email delivery is selected |

You do not need to cram every detail into every field. Include what matters to the client; avoid vague descriptions such as "email" or "plan", or merely repeating the parameter name without explaining usage.

### 4.2. Describing requiredness and optionality

Spring REST Docs checks form parameter name presence based on descriptors. A descriptor without **optional()** is treated as required in the snippet by default. Example:

```java
formParameters(
    parameterWithName("email")
        .description("Email address; required, must not be blank."),
    parameterWithName("plan")
        .optional()
        .description("Subscription plan; may be omitted, defaults to basic."),
    parameterWithName("referral")
        .optional()
        .description("Referral code; send only when a valid code is available.")
)
```

**optional()** means the parameter may be **absent in the request used to generate the snippet**. It does not make the controller automatically accept a missing field, nor does it apply a default value. Ensure that:

1. Server binding/validation permits the field to be absent.
2. Tests verify behavior when the field is omitted.
3. The description explains any default value or related conditions.

Conversely, required fields should not call optional(). If the documented request omits such a field, Spring REST Docs reports an error during snippet generation, catching sample requests that fail to reflect the contract.

### 4.3. Describing allowed values and formats

Examples:

```java
parameterWithName("plan")
    .description("Service plan; accepts only basic or pro.")

parameterWithName("seats")
    .description("Number of registered seats; integer from 1 to 5.")

parameterWithName("startDate")
    .description("Start date in ISO-8601, yyyy-MM-dd format.")
```

A description is guidance text for clients. It **does not automatically validate** allowed values, numeric types, or date formats. The server needs corresponding validation, and tests must verify valid and invalid cases.

Use examples faithful to the real format. If the server accepts 2026-11-17, do not document the date as 17/11/2026; if the server supports only basic/pro, do not write "arbitrary plans".

### 4.4. Describing multiple values under one name

For the body:

```text
topics=java&topics=spring&topics=rest-docs
```

Only one descriptor is needed for the topics name:

```java
parameterWithName("topics")
    .description("List of topics; repeat the topics name for each item. " +
                 "Accepts java, spring, or rest-docs; maximum 3 items.")
```

Do not create three descriptors with the same name to represent individual values. formParameters(...) describes parameter names; it does not check item count, ordering, or list values. Those rules require separate validation and tests.

### 4.5. Describing intentionally ignored fields

If a request carries an internal parameter that public documentation should omit, you can use:

```java
parameterWithName("internalTrace")
    .ignored()
```

ignored() tells Spring REST Docs to accept the declared parameter without including it in the snippet table. Use it only when there is a clear, deliberate decision; never use it to hide public API fields or make a test pass when you forgot to document a parameter.

## 5. Complete example: naming snippets and describing forms

### 5.1. API contract

Suppose the POST /registrations endpoint accepts:

| Parameter | Rule |
| --- | --- |
| email | Required; valid email address |
| plan | Required; basic or pro |
| seats | Required; integer from 1 to 5 |
| referral | Optional; referral code string |

### 5.2. Illustrative controller

```java
package example.docs;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/registrations")
public class RegistrationController {

    @PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<Void> create(
            @RequestParam String email,
            @RequestParam String plan,
            @RequestParam Integer seats,
            @RequestParam(required = false) String referral) {

        if (email.isBlank() || !email.contains("@")) {
            return ResponseEntity.badRequest().build();
        }
        if (!plan.equals("basic") && !plan.equals("pro")) {
            return ResponseEntity.badRequest().build();
        }
        if (seats < 1 || seats > 5) {
            return ResponseEntity.badRequest().build();
        }
        // Learning example: persistence logic is omitted.
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
```

The controller is simplified to illustrate the contract. A production system should use Bean Validation or thorough service-layer validation; email.contains("@") is not a complete email check.

### 5.3. MockMvc test and stable identifiers

```java
package example.docs;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(RegistrationController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class RegistrationDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void createRegistrationDocumentsFormContract() throws Exception {
        mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "mai@example.com")
                .param("plan", "pro")
                .param("seats", "2")
                .param("referral", "campaign-2026"))
            .andExpect(status().isCreated())
            .andDo(document("registrations/create-form",
                formParameters(
                    parameterWithName("email")
                        .description("Valid email address; required."),
                    parameterWithName("plan")
                        .description("Subscription plan; accepts only basic or pro."),
                    parameterWithName("seats")
                        .description("Number of seats; integer from 1 to 5."),
                    parameterWithName("referral")
                        .optional()
                        .description("Referral code; may be omitted.")
                )
            ));
    }

    @Test
    void createRegistrationWithMinimalForm() throws Exception {
        mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "mai@example.com")
                .param("plan", "basic")
                .param("seats", "1"))
            .andExpect(status().isCreated())
            .andDo(document("registrations/create-form-minimal",
                formParameters(
                    parameterWithName("email")
                        .description("Valid email address; required."),
                    parameterWithName("plan")
                        .description("Subscription plan; accepts only basic or pro."),
                    parameterWithName("seats")
                        .description("Number of seats; integer from 1 to 5."),
                    parameterWithName("referral")
                        .optional()
                        .description("Referral code; may be omitted.")
                )
            ));
    }
}
```

Both tests use separate identifiers:

- **registrations/create-form:** request including a referral code.
- **registrations/create-form-minimal:** request omitting the optional referral parameter.

The descriptors declare referral as optional in both cases. This lets the second test accurately verify that clients are allowed to omit the field. The remaining three fields are not optional, so a request missing any of them will cause document generation to fail or the server to reject the request.

The tests assume the controller has no extra service dependencies. If the endpoint has CSRF, authentication, or business dependencies, add appropriate configuration/mocks so tests reflect the application's real HTTP flow.

## 6. Reusing descriptors while keeping snippet names clear

When multiple scenarios describe the same parameter contract, repeating descriptors can cause documentation drift. You can extract descriptor configuration into a shared helper method in the test class or test support:

```java
private static ParameterDescriptor[] registrationFormParameters() {
    return new ParameterDescriptor[] {
        parameterWithName("email")
            .description("Valid email address; required."),
        parameterWithName("plan")
            .description("Subscription plan; accepts only basic or pro."),
        parameterWithName("seats")
            .description("Number of seats; integer from 1 to 5."),
        parameterWithName("referral")
            .optional()
            .description("Referral code; may be omitted.")
    };
}
```

Import org.springframework.restdocs.request.ParameterDescriptor. Usage:

```java
document("registrations/create-form",
    formParameters(registrationFormParameters()));

document("registrations/create-form-minimal",
    formParameters(registrationFormParameters()));
```

formParameters(...) accepts a list of descriptors for form parameter names. Reuse descriptors only when two requests share **the exact same contract**. If one variant has different fields, different allowed values, or different optionality conditions, create separate descriptors or explicitly note differences instead of forcing a shared configuration.

Do not turn descriptions into overly long strings containing every endpoint rule. Divide the information cleanly:

- Parameter description: meaning, format, presence, and primary value range.
- AsciiDoc page introduction: cross-field rules, business conditions, and examples.
- Dedicated tests: verify boundary cases that snippets do not check automatically.

## 7. Describing forms on an Asciidoctor page

Identifiers form stable paths for including snippets. Example src/docs/asciidoc/registrations.adoc file:

```adoc
= Registration API

== Create registration with URL-encoded form

Send the request with Content-Type: application/x-www-form-urlencoded.
Fields email, plan, and seats are required.
The referral field may be omitted.

=== Request with referral

==== HTTP request
include::{snippets}/registrations/create-form/http-request.adoc[]

==== Form parameters
include::{snippets}/registrations/create-form/form-parameters.adoc[]

==== HTTP response
include::{snippets}/registrations/create-form/http-response.adoc[]

=== Minimal request

This request omits referral.

==== HTTP request
include::{snippets}/registrations/create-form-minimal/http-request.adoc[]

==== Form parameters
include::{snippets}/registrations/create-form-minimal/form-parameters.adoc[]

==== HTTP response
include::{snippets}/registrations/create-form-minimal/http-response.adoc[]
```

The {snippets} variable must point to the root snippets directory, such as build/generated-snippets. The include::...[] directives are Asciidoctor syntax and are not automatically interpreted by standard Markdown renderers. If your primary documentation is Markdown, link to the HTML generated by Asciidoctor or add a build-managed conversion step.

### 7.1. Heading and description hierarchy

Each section should have a heading representing one operation or one request variant:

```text
Registration API
└── Create registration with form
    ├── Request with referral
    │   ├── HTTP request
    │   ├── Form parameters
    │   └── HTTP response
    └── Minimal request
        ├── HTTP request
        ├── Form parameters
        └── HTTP response
```

Avoid generic section names like "Snippet 1" or "Example 2". Good headings tell readers which request they are viewing even before reading the code blocks.

### 7.2. Structuring non-redundant descriptions

Place general rules at the top of the endpoint section, then let the form-parameters.adoc table explain each field in detail. Repeating every rule in the introduction, every parameter row, and the notes makes the page verbose and hard to maintain.

For example, introduce "referral is optional and applies only when the client has a valid referral code"; in the descriptor table, write "Valid referral code; may be omitted." Both complement each other without duplicating the entire explanation.

## 8. Build and CI integration

With Gradle Groovy DSL and the Asciidoctor plugin installed:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir.absolutePath
}
```

CI runs:

```bash
./gradlew test asciidoctor
```

This relationship ensures documentation depends on test snippets. When an identifier changes, update the include::{snippets}/...[] paths as well; otherwise, Asciidoctor will fail to find the old files. A clean build prevents stale leftover snippets from masking tests that no longer generate documentation.

Check the following items in pull requests:

1. Does the identifier accurately describe the resource, action, and request format?
2. Does each scenario have a distinct identifier if its request/response differs?
3. Do required/optional form parameters match the controller and tests?
4. Do descriptions state formats, value ranges, and defaults accurately?
5. Do include paths point to the right identifiers?
6. Do both tests and the Asciidoctor step run in the CI pipeline?

## 9. Common errors

| Symptom | Cause | Fix |
| --- | --- | --- |
| Test snippets get overwritten | Two tests share the same identifier and snippet filenames | Name identifiers per request scenario |
| Asciidoctor reports form-parameters.adoc not found | Wrong identifier in include or test did not generate snippet | Match document(...), output directory, and include path |
| Description only says "email" | Omits meaning, format, and whether required or optional | Write descriptions guiding clients to send valid requests |
| Marked optional() but controller returns 400 when missing | Documentation descriptor does not alter the server contract | Align binding/validation, tests, and descriptors |
| New parameter appears unexpectedly in request | Descriptor not updated | Keep formParameters(...) strict and document the new field |
| Used ignored() to make tests pass | Hides an undocumented public field | Ignore only internal fields with an explicit decision |
| One descriptor shared across APIs with inaccurate descriptions | Endpoint contracts have diverged | Split descriptor helpers by contract group |
| Identifier contains email/ID/timestamp | Output path becomes unstable and hard to reference | Use static names based on resource/action/scenario |
| AsciiDoc repeats descriptions | General rules repeated across multiple heading levels | Keep endpoint rules at the top, field details in the table |

## 10. Practice exercise

Create a POST /subscriptions endpoint accepting a form:

| Parameter | Rule |
| --- | --- |
| email | Required, valid email |
| topics | Required, name repeated 1–3 times, each value in java, spring, testing |
| frequency | Optional, weekly or monthly, defaults to weekly |
| referral | Optional, referral code string |

Steps:

1. Write the controller and a full-request test.
2. Set the identifier to subscriptions/create-form.
3. Write descriptors with descriptions conveying meaning, requiredness, valid values, defaults, and repeatable topics.
4. Create a minimal-request test using the identifier subscriptions/create-form-minimal.
5. Create a test subscriptions/create-form-invalid for an invalid frequency value and document the error response with responseFields(...).
6. Reuse a shared descriptor helper for fields sharing the same contract; do not reuse it where actual conditions differ.
7. Embed all three snippet sets in Asciidoctor and run ./gradlew test asciidoctor in CI.

**Pass criteria:** identifiers are clear with no snippet overwrites; the form parameters table explains enough for clients to send valid requests; descriptions reflect server behavior; documentation is compiled from test-verified snippets.

## References

- [Spring REST Docs — Form Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/form-parameters.html)
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [Spring REST Docs — RequestDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/request/RequestDocumentation.html)
