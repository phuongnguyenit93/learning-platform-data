# subsectionWithPath for Child Objects in Spring REST Docs

## 1. Context and Objectives

**Spring REST Docs** helps create verifiable REST API documentation from HTTP tests using **MockMvc**, **WebTestClient**, or **REST Assured**. Snippets for requests, responses, payloads, parameters, and headers are generated when tests pass, and are then assembled into Asciidoctor/Markdown documentation in the build and CI pipeline.

This lesson belongs to the **Subsection** group and focuses on the `subsectionWithPath(...)` API when a JSON payload contains **child objects**. This is a useful option when you want the payload description table to state the meaning of an entire object instead of listing every field at every level.

For example, an endpoint returns user information consisting of `id`, `enabled`, `roles`, and a `profile` object containing multiple data groups. On the API overview page, we only need to explain what `profile` is; the details may be documented separately or omitted, depending on the API contract.

After completing this lesson, you will be able to:

- Use `subsectionWithPath("profile")` in `responseFields(...)` and `requestFields(...)` to document a child object.
- Understand the exact scope of fields considered documented when using this descriptor.
- Distinguish `subsectionWithPath(...)` from `fieldWithPath(...)` and `beneathPath(...)`.
- Write a MockMvc test that generates both an overview snippet and a detailed snippet, as well as identify when schema changes cause the test to fail.
- Include snippets into Asciidoctor documentation and bind the documentation generation step to testing in build/CI.

## 2. Child Objects in a JSON Payload

Suppose `GET /users/usr-42` returns the response:

```json
{
  "id": "usr-42",
  "enabled": true,
  "profile": {
    "displayName": "Lan Nguyen",
    "contact": {
      "email": "lan@example.test",
      "phone": "+84900000000"
    },
    "address": {
      "city": "Ho Chi Minh City",
      "country": "VN"
    }
  },
  "roles": ["READER"]
}
```

At the root level, the payload has four fields: `id`, `enabled`, `profile`, and `roles`. However, `profile` is a **child object** with nested fields:

```text
response body
├── id
├── enabled
├── profile
│   ├── displayName
│   ├── contact
│   │   ├── email
│   │   └── phone
│   └── address
│       ├── city
│       └── country
└── roles
```

If you want the overview table to display only four rows, you can declare:

```java
responseFields(
    fieldWithPath("id")
        .description("User ID"),
    fieldWithPath("enabled")
        .description("Account activation status"),
    subsectionWithPath("profile")
        .description("User profile information"),
    fieldWithPath("roles")
        .description("List of roles")
)
```

With `subsectionWithPath("profile")`, Spring REST Docs considers **the entire `profile` branch and the fields beneath it** to be documented in **this snippet**. Therefore, the overview table has a single row describing the `profile` object instead of requiring you to add every `profile.displayName`, `profile.contact.email`, `profile.address.city`, and so on.

Basic syntax:

```java
subsectionWithPath("pathToObject")
    .description("Meaning of the entire object")
```

For deeper objects, the path can be `subsectionWithPath("profile.address")` if the table is documenting the payload directly from the root. Paths use REST Docs JSON path syntax: dots separate object levels; for special keys, the corresponding bracket syntax must be applied.

## 3. Complete Example with MockMvc

The following code uses JUnit 5, Spring MVC Test, and Spring REST Docs. The test controller returns fixed JSON so the documentation does not depend on a database or runtime clock. In a real project, replace the sample controller with your application's controller and fixtures.

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class UserProfileDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders
                .standaloneSetup(new SampleUserController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentProfileAsSubsection() throws Exception {
        mockMvc.perform(get("/users/{id}", "usr-42")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.profile").isMap())
                .andExpect(jsonPath("$.profile.contact.email")
                        .value("lan@example.test"))
                .andDo(document("users-get-profile-overview",
                        responseFields(
                                fieldWithPath("id")
                                        .description("User ID"),
                                fieldWithPath("enabled")
                                        .description("Whether the account is enabled"),
                                subsectionWithPath("profile")
                                        .description("Profile information"),
                                fieldWithPath("roles")
                                        .description("List of roles")
                        )
                ));
    }

    @RestController
    static class SampleUserController {

        @GetMapping(
                value = "/users/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        ResponseEntity<String> getUser(@PathVariable String id) {
            if (!"usr-42".equals(id)) {
                return ResponseEntity.notFound().build();
            }

            String json = """
                    {
                      "id": "usr-42",
                      "enabled": true,
                      "profile": {
                        "displayName": "Lan Nguyen",
                        "contact": {
                          "email": "lan@example.test",
                          "phone": "+84900000000"
                        },
                        "address": {
                          "city": "Ho Chi Minh City",
                          "country": "VN"
                        }
                      },
                      "roles": ["READER"]
                    }
                    """;

            return ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(json);
        }
    }
}
```

This snippet uses Java 17+ (text blocks) and requires the appropriate testing libraries on the test classpath. `RestDocumentationExtension` manages the REST Docs context, `documentationConfiguration(restDocumentation)` attaches REST Docs to MockMvc, and `document("users-get-profile-overview", ...)` generates snippets when the HTTP exchange satisfies the assertions.

### Why Are Assertions Still Needed When Using REST Docs?

`responseFields(...)` checks documentation descriptors; it does not replace all behavioral/business assertions. In the example:

- `status().isOk()` ensures the endpoint returns HTTP 200.
- `jsonPath("$.profile").isMap()` verifies that `profile` is actually a JSON object.
- `jsonPath("$.profile.contact.email")` ensures the key value matches the fixture.
- `responseFields(...)` ensures the declared root-level fields are present and no out-of-scope root-level fields appear in strict mode.

In particular, writing `subsectionWithPath("profile")` **does not mean** REST Docs is validating each child field against a complete schema. If the contract requires guaranteeing email, address, and formatting rules, add business assertions and/or a separate detailed snippet.

## 4. How Is the Overview Snippet Generated?

After the test passes, with the identifier `users-get-profile-overview`, the default snippet output directory for Gradle is typically:

```text
build/generated-snippets/
└── users-get-profile-overview/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── curl-request.adoc
    ├── httpie-request.adoc
    ├── request-body.adoc
    ├── response-body.adoc
    └── response-fields.adoc
```

The default files depend on your snippet configuration and the information present in the HTTP exchange. The most important file for this lesson is `response-fields.adoc`, produced by the `responseFields(...)` call. Conceptually, this table describes:

| Field | JSON Type | Description |
| --- | --- | --- |
| `id` | String | User ID |
| `enabled` | Boolean | Whether the account is enabled |
| `profile` | Object | Profile information |
| `roles` | Array | List of roles |

This table only illustrates the content; the actual styling, column headers, and rendering depend on the REST Docs template in use.

**Key takeaway:** `subsectionWithPath("profile")` does not automatically generate `response-fields-profile.adoc` or `response-body-profile.adoc`. It creates **one row** in the `response-fields.adoc` table of the current payload and covers child fields when REST Docs checks the completeness of that table.

## 5. Strict Documentation: How Are New Fields Handled?

`responseFields(...)` is strict by default: a field appearing in the payload without being documented causes the test to fail, unless that field belongs to a covered subsection or has an appropriate declaration.

Based on the `users-get-profile-overview` example:

| Response Change | Strict Overview Table Result | Reason |
| --- | --- | --- |
| Adding `profile.nickname` | Usually still passes | `profile` and its descendants are already covered by `subsectionWithPath("profile")`. |
| Adding `profile.contact.telegram` | Usually still passes | This is still a field inside the `profile` branch. |
| Adding `createdAt` at root | Fails when undocumented | `createdAt` is a new root-level field and does not belong to the documented subsection. |
| Removing `profile` completely | Fails if the descriptor remains required | `profile` is documented but missing. |
| Removing `profile.address.country` | Overview table may still pass | The overview table does not declare `country` individually. |
| Changing `profile` from object to string | Should not rely solely on descriptors | Combine with `jsonPath("$.profile").isMap()` assertion to catch JSON type errors. |

Strictness here has a **validation boundary**. The overview table protects the declared root-level paths, while deliberately not policing the entire internal structure of `profile`. That is a documentation design choice: better readability in exchange for a narrower scope for catching child field changes.

### A Common Mistake

Suppose the API adds a `createdAt` field outside `profile`. If you use:

```java
responseFields(
    fieldWithPath("id").description("User ID"),
    subsectionWithPath("profile").description("Profile information")
)
```

the table is still missing `enabled`, `roles`, and `createdAt` at the root; in strict mode, the test fails. `subsectionWithPath("profile")` **only** covers `profile`, and does not ignore fields elsewhere in the JSON.

## 6. When You Want to Verify Child Object Details: Add beneathPath

Here is the core difference between the two APIs:

| API | Role | Typical Usage |
| --- | --- | --- |
| `subsectionWithPath("profile")` | Descriptor covering an object and its descendants in the current field table | `responseFields(subsectionWithPath("profile").description(...))` |
| `beneathPath("profile")` | Extractor selecting a subtree to generate a separate snippet | `responseFields(beneathPath("profile"), ...)` or `responseBody(beneathPath("profile"))` |

Suppose you want to keep the overview table short while still verifying each field of `profile`. Add a **second snippet** to the same `document(...)` call:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.beneathPath;

// Inside document("users-get-profile-overview", ...):
responseFields(
    beneathPath("profile").withSubsectionId("profile-details"),
    fieldWithPath("displayName")
        .description("Display name"),
    fieldWithPath("contact.email")
        .description("Contact email"),
    fieldWithPath("contact.phone")
        .optional()
        .description("Contact phone number if available"),
    fieldWithPath("address.city")
        .description("City"),
    fieldWithPath("address.country")
        .description("Country code")
)
```

This example is an **additional handler snippet**: place it after the overview `responseFields(...)`, separated by a comma in the arguments to `document(...)`.

REST Docs then additionally generates `response-fields-profile-details.adoc`. Paths in the detailed snippet are **relative** to `profile`: use `contact.email`, not `profile.contact.email`. If `profile.nickname` appears without being documented, the strict detailed table will fail; the overview table with `subsectionWithPath("profile")` can still remain valid.

You can generate a separate portion of the response body using another handler:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.responseBody;

// Inside document("users-get-profile-overview", ...):
responseBody(
    beneathPath("profile").withSubsectionId("profile-details")
)
```

The body snippet is named `response-body-profile-details.adoc`, reflecting the extracted JSON portion. Calling `responseBody(...)` alone does not mean the subsection's fields are fully documented and validated; to protect the detailed schema, also use `responseFields(beneathPath(...), ...)`.

## 7. Using subsectionWithPath with Deeper Objects

If you want to describe `address` as a block while still listing name and contact details individually, you can document directly from the root:

```java
responseFields(
    fieldWithPath("id")
        .description("User ID"),
    fieldWithPath("enabled")
        .description("Activation status"),
    fieldWithPath("profile.displayName")
        .description("Display name"),
    fieldWithPath("profile.contact.email")
        .description("Contact email"),
    fieldWithPath("profile.contact.phone")
        .description("Contact phone"),
    subsectionWithPath("profile.address")
        .description("Profile address"),
    fieldWithPath("roles")
        .description("List of roles")
)
```

In this table, `profile.address.city` and `profile.address.country` sit under `profile.address` and therefore do not need separate descriptions in the current snippet. Conversely, `profile.contact.email` and `profile.contact.phone` must have descriptors because we are **not** covering all of `profile.contact` with a subsection descriptor.

A practical guideline: choose the **documentation boundary** at a branch with clear business meaning. Avoid using `subsectionWithPath("profile")` just to make tests pass when you don't yet know the structure of `profile`. If client teams need every property to integrate, provide a detailed table and corresponding test.

## 8. With Request Payloads, the Principle Remains the Same

`subsectionWithPath(...)` is not exclusive to responses. For example, `POST /users` receives a JSON request:

```json
{
  "username": "lan.nguyen",
  "profile": {
    "displayName": "Lan Nguyen",
    "preferences": {
      "language": "vi",
      "timezone": "Asia/Ho_Chi_Minh"
    }
  }
}
```

In the documentation handler of the request test, you can use:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;

requestFields(
    fieldWithPath("username")
        .description("Username"),
    subsectionWithPath("profile")
        .description("Initial user profile")
)
```

The handler generates `request-fields.adoc` with two rows: `username` and `profile`. This is still a strict table for the root-level request, while the child fields `profile.displayName` and `profile.preferences.language` are covered by `subsectionWithPath("profile")`. When you need to explain the child fields to client implementers, add `requestFields(beneathPath("profile"), ...)` in a test that includes `profile`.

MockMvc, WebTestClient, and REST Assured can all use descriptors from `PayloadDocumentation`; the difference lies in how `document(...)` is attached to the HTTP exchange:

- **MockMvc:** `.andDo(document("id", requestFields(...)))` or `.andDo(document("id", responseFields(...)))`.
- **WebTestClient:** `.expectBody().consumeWith(document("id", responseFields(...)))`.
- **REST Assured:** `.filter(document("id", responseFields(...)))` when setting up the HTTP request.

Before running these examples, each framework must be configured with the Spring REST Docs extension/configurer or filter according to the official guide.

## 9. optional, ignored, relaxed, and Data Types

### Objects That May Be Absent

If the API contract allows the response to omit `profile`, you can mark it:

```java
subsectionWithPath("profile")
    .optional()
    .description("User profile, if already completed")
```

`optional()` allows the documented field to be absent. You should have **a test for the variant without the object** to confirm the behavioral contract. If you also use `beneathPath("profile")` in the same test, the extractor requires the branch to be present to extract the data. Therefore, for a response without `profile`, do not attach this extractor; generate the subsection snippet in a test that includes the data.

### Fields Intentionally Excluded from the Table

`ignored()` can be used on a descriptor for a known field that you do not want shown in the documentation. For example, if an internal field is present in the test payload and genuinely does not belong in public documentation, you can intentionally mark its descriptor as ignored. Do not use `ignored()` to hide schema changes that the development team does not yet understand.

### Relaxed Mode

`relaxedResponseFields(...)` (or `relaxedRequestFields(...)`) skips undocumented fields. This mode is useful for selective documentation, but if the goal is to catch unexpected payload changes, prefer a strict table combined with `subsectionWithPath(...)` at the exact branch to summarize.

### Object Type in the Table

In case you want to explicitly display the object type, you can declare:

```java
import org.springframework.restdocs.payload.JsonFieldType;

subsectionWithPath("profile")
    .type(JsonFieldType.OBJECT)
    .description("Profile information")
```

`type(...)` supplies the type displayed in the documentation. If you need to be certain at runtime that a **JSON object** is returned per the contract, verify it additionally with a JSON assertion such as `jsonPath("$.profile").isMap()` in MockMvc. Do not treat the type description in the table as a substitute for an actual data assertion test.

## 10. Assembling Snippets into Documentation and the Build Pipeline

With the identifier from Section 3, the Asciidoctor document can include the overview table:

```asciidoc
= Users API
:toc: left

== GET /users/{id}

Returns account status and user profile.

=== HTTP Response

include::{snippets}/users-get-profile-overview/http-response.adoc[]

=== Overview Response Fields

include::{snippets}/users-get-profile-overview/response-fields.adoc[]
```

If the test added the `responseFields(beneathPath("profile").withSubsectionId("profile-details"), ...)` handler, you can also add:

```asciidoc
=== Profile Fields

include::{snippets}/users-get-profile-overview/response-fields-profile-details.adoc[]
```

To ensure snippets are generated before Asciidoctor compiles the docs, you can wire the tasks in Gradle (Groovy DSL; assuming the project already has the Asciidoctor plugin, Spring REST Docs dependencies, and test configuration installed):

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    inputs.dir snippetsDir
    dependsOn tasks.named('test')
    attributes 'snippets': snippetsDir
}
```

Then run:

```bash
./gradlew clean test asciidoctor
```

When integrating into CI, let failing tests block the documentation generation and publishing step to avoid publishing snippets that no longer match the API. The output path must be consistent between REST Docs and the Asciidoctor configuration; with Maven, the standard directory is `target/generated-snippets`.

If the project builds Markdown documentation, use the templates/snippets and inclusion mechanism appropriate for your chosen Markdown pipeline instead of Asciidoctor's `include::[]` directive.

## 11. Common Errors

| Symptom | Cause | How to Fix |
| --- | --- | --- |
| Test reports an undocumented field | A new field appeared outside the `profile` branch, or a root-level descriptor is missing | Inspect paths in the actual payload and add the appropriate descriptor. |
| Test still passes when a field is added inside `profile` | `subsectionWithPath("profile")` covers descendants | Add a strict `responseFields(beneathPath("profile"), ...)` table when child structure verification is needed. |
| Test reports path not found | Wrong letter casing or path declared at the wrong level | Compare against actual JSON and descriptor paths. |
| Detailed table reports `profile.contact.email` missing | Path has the `profile` prefix even though the `profile` branch was extracted | Use `contact.email` when descriptors are inside `beneathPath("profile")`. |
| `response-fields-profile-details.adoc` is not generated | Only `subsectionWithPath` was declared without adding a `beneathPath` handler | Add the detailed snippet and run the test. |
| Test returns a string instead of a `profile` object | Unexpected data type change; documenting the type alone does not enforce the contract | Add a JSON assertion to verify the object and key data. |
| Asciidoctor reports a missing snippet | Test did not generate the snippet, wrong identifier, or wrong path | Check build order, snippets directory, and include filename. |

## 12. Practice Exercise

Starting from `UserProfileDocumentationTest` in Section 3, complete the following:

1. **Test the strict boundary:** add `profile.nickname` to the JSON while keeping the descriptors unchanged. Verify that the overview table with `subsectionWithPath("profile")` is still generated. Then add `createdAt` at the root; observe the strict test result.
2. **Document a deeper object:** replace `subsectionWithPath("profile")` with three descriptors for `profile.displayName`, `profile.contact`, and `profile.address` (the last two using `subsectionWithPath`). Re-run and observe the more detailed overview table.
3. **Create a detailed table:** keep the initial overview table, and also add `responseFields(beneathPath("profile").withSubsectionId("profile-details"), ...)`. Add `profile.nickname` and verify that the strict detailed table catches the new field.
4. **Optional:** make the response omit `profile.contact.phone` and mark the corresponding descriptor in the detailed table with `optional()`. Verify the test still passes; try removing `optional()` to see the difference.
5. **Documentation build:** include `response-fields.adoc` and `response-fields-profile-details.adoc` in Asciidoctor, then run `./gradlew clean test asciidoctor` in a configured environment.

**Completion criteria:** you can point out the exact paths covered by `subsectionWithPath("profile")`, explain why a new field inside `profile` and a new field at the root can produce different test outcomes, and combine an overview table with a detailed table when clients need the complete schema.

## References

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): how to document fields, subsections, paths, and verify payload completeness.
- [Spring REST Docs — Reference Documentation](https://docs.spring.io/spring-restdocs/reference/): setting up MockMvc, WebTestClient, REST Assured, generating snippets, and integrating Asciidoctor/build.
