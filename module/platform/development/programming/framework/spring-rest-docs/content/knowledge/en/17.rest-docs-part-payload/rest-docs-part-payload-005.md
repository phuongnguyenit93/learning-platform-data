# Documenting Subsections Inside a Request Part with Spring REST Docs

## 1. Multipart payloads can contain nested objects

A profile creation API might receive a JSON `metadata` part. In addition to simple fields like `name` and `description`, the payload contains an `owner` object, a `location` object, and a `contacts` array:

```http
POST /api/profiles HTTP/1.1
Content-Type: multipart/form-data; boundary=----ProfileBoundary

------ProfileBoundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{
  "name": "Engineering team",
  "description": "Platform engineering team",
  "owner": {
    "id": "USR-42",
    "displayName": "Platform Team",
    "contact": {
      "email": "platform@example.test",
      "phone": "+84-28-5550-0100"
    }
  },
  "location": {
    "country": "VN",
    "city": "Ho Chi Minh City"
  },
  "contacts": [
    {"type": "SUPPORT", "value": "support@example.test"},
    {"type": "SALES", "value": "sales@example.test"}
  ]
}
------ProfileBoundary--
```

There are two common ways to explain the `owner` structure:

- List `owner.id`, `owner.displayName`, `owner.contact.email`, and `owner.contact.phone` individually. This suits cases where readers need every field detail.
- Describe the entire `owner` object as a **subsection**. This suits cases where the nested object has its own structure explained in another schema or documentation section.

Spring REST Docs supports both approaches through `FieldDescriptor` instances in `requestPartFields(...)`. This lesson belongs to the **Part payload** chapter of the **SPRING_REST_DOCS** module: using HTTP tests with MockMvc, WebTestClient, or REST Assured to generate verifiable multipart snippets, then integrating them into Asciidoctor/Markdown and build/CI.

After this lesson, you will be able to:

1. Understand a subsection as a nested object or group of fields inside a part's payload.
2. Use `subsectionWithPath(...)` inside `requestPartFields(...)`.
3. Choose between documenting a subsection and listing child fields in detail.
4. Describe multi-level nested subsections, arrays of objects, and optional subsections.
5. Generate snippets from MockMvc tests and include them in API documentation pages.

## 2. Reviewing the scope of requestPartFields(...)

A multipart request can consist of multiple parts. Each part has its own name, headers, and body:

| API | Scope |
| --- | --- |
| `requestParts(...)` | Names and descriptions of the multipart request's parts |
| `requestPartBody("metadata")` | Sample body of the `metadata` part |
| `requestPartFields("metadata", ...)` | Field structure within the payload of the `metadata` part |

Example:

```java
requestPartFields("metadata",
    fieldWithPath("name").description("Profile name"),
    fieldWithPath("owner.id").description("Owner identifier"),
    fieldWithPath("owner.displayName").description("Owner display name")
)
```

The part name passed to `requestPartFields("metadata", ...)` identifies the payload to analyze. Subsequent descriptors use paths relative to that specific part's JSON body. `owner.id` means the `id` field inside the `owner` object, not a field of the main request body.

If the `metadata` part does not contain valid JSON matching the content type handled by Spring REST Docs, the field snippet cannot parse the expected structure. Therefore, tests must send the part with a body and Content-Type matching the contract, typically `application/json`.

## 3. What is a subsection?

A subsection is a structured sub-portion inside a payload. For example:

```json
{
  "name": "Engineering team",
  "owner": {
    "id": "USR-42",
    "displayName": "Platform Team"
  }
}
```

You can document `owner` in two ways.

**Expand child fields:**

```java
requestPartFields("metadata",
    fieldWithPath("name").description("Profile name"),
    fieldWithPath("owner.id").description("Owner identifier"),
    fieldWithPath("owner.displayName").description("Display name")
)
```

**Document the subsection as a single unit:**

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;

requestPartFields("metadata",
    fieldWithPath("name").description("Profile name"),
    subsectionWithPath("owner")
        .description("Profile owner information")
)
```

`subsectionWithPath("owner")` describes the entire nested group as a single entry in the field table. It does not generate a recursive table containing every child field. If readers need to know the details of `id`, `displayName`, or `contact`, list those fields with individual descriptors or provide a detailed schema elsewhere in the documentation.

## 4. Syntax of subsectionWithPath(...)

`subsectionWithPath(...)` belongs to `org.springframework.restdocs.payload.PayloadDocumentation` and returns a `SubsectionDescriptor`, which is a type of field descriptor:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;

subsectionWithPath("owner")
    .description("Owner information")
```

This API can be used with `requestPartFields(...)`:

```java
requestPartFields("metadata",
    fieldWithPath("name").description("Profile name"),
    subsectionWithPath("owner").description("Owner information"),
    subsectionWithPath("location").description("Profile address")
)
```

Subsection paths follow the same JSON path conventions as `fieldWithPath(...)`:

| Payload path | Meaning |
| --- | --- |
| `owner` | Top-level `owner` object |
| `owner.contact` | `contact` object nested inside `owner` |
| `location` | Top-level `location` object |
| `contacts[]` | Elements in the `contacts` array |
| `items[].product` | `product` object inside each element of the `items` array |

The path must exist in the tested part body unless the descriptor is marked optional. Use the exact path matching the actual JSON, including field names and nesting positions.

### 4.1. Subsection vs. field descriptor

| API | When to use |
| --- | --- |
| `fieldWithPath("owner.id")` | Need to define a specific field |
| `subsectionWithPath("owner")` | Want to group a nested object into one entry |
| `fieldWithPath("contacts[].type")` | Need to define a field within each array element |
| `subsectionWithPath("contacts[]")` | Want to describe the array element structure as a group |

Do not declare a subsection to stand in for all child fields while simultaneously expecting the same snippet to list those fields in detail. Choose the level of detail appropriate for your readers and avoid creating overlapping descriptors for the same payload section.

## 5. Choosing the right level of detail

A subsection is not always the better choice. Depending on the structure and API consumers, you can choose:

| Scenario | Recommended documentation approach | Reason |
| --- | --- | --- |
| Small nested object where all fields matter | List each field with `fieldWithPath(...)` | Users know exact names and meanings |
| Large nested object or one with its own schema | `subsectionWithPath(...)` | Keeps the main table concise and avoids duplicating schemas |
| Sub-portion contains internal fields | Publish only the public portion | Avoids exposing implementation details |
| Stable structure shared across many endpoints | Subsection accompanied by shared schema docs | Reduces content duplication |
| Sub-portion varies by request type | Describe fields and variants | Clarifies presence conditions |

A field table containing only an `owner` row with the description “Owner information” may be too general if clients need to know whether `owner.id` is required or `owner.contact.email` can be omitted. In that case, expand the subsection or point to a separately published schema.

## 6. Multi-level nested subsections

Consider the payload:

```json
{
  "name": "Engineering team",
  "owner": {
    "id": "USR-42",
    "profile": {
      "displayName": "Platform Team",
      "department": {
        "code": "ENG",
        "name": "Engineering"
      }
    }
  }
}
```

You can document at each level:

```java
requestPartFields("metadata",
    fieldWithPath("name").description("Profile name"),
    fieldWithPath("owner.id").description("Owner identifier"),
    subsectionWithPath("owner.profile")
        .description("Display profile of the owner")
)
```

In this approach, `owner.id` is explained in detail while `owner.profile` is collapsed into a subsection. To expand deeper:

```java
requestPartFields("metadata",
    fieldWithPath("name").description("Profile name"),
    fieldWithPath("owner.id").description("Owner identifier"),
    fieldWithPath("owner.profile.displayName").description("Display name"),
    fieldWithPath("owner.profile.department.code").description("Department code"),
    fieldWithPath("owner.profile.department.name").description("Department name")
)
```

The two representations serve two different goals. Once `owner.profile` is documented as a subsection, do not add its child descriptors to the same list expecting the subsection to automatically expand into a detailed table. When both an overview and a full schema are needed, use a supplementary description/schema or a separate documentation structure rather than declaring overlapping paths.

## 7. Subsections containing arrays of objects

A JSON part may contain an array of objects:

```json
{
  "name": "Engineering team",
  "contacts": [
    {
      "type": "SUPPORT",
      "value": "support@example.test",
      "primary": true
    },
    {
      "type": "SALES",
      "value": "sales@example.test",
      "primary": false
    }
  ]
}
```

If you need to document each element's fields in detail:

```java
requestPartFields("metadata",
    fieldWithPath("name").description("Profile name"),
    fieldWithPath("contacts[].type").description("Contact address type"),
    fieldWithPath("contacts[].value").description("Contact value"),
    fieldWithPath("contacts[].primary").description("Whether this is the primary contact")
)
```

If you only need to state that `contacts` is a list of contact details and the schema is published separately:

```java
requestPartFields("metadata",
    fieldWithPath("name").description("Profile name"),
    subsectionWithPath("contacts")
        .description("List of contacts; element schema is described in Contact")
)
```

`contacts` groups the entire array; `contacts[]` can be used to refer to the repeating element of the array when describing an element subsection. Check the exact JSON path supported by payload snippets in your Spring REST Docs version and choose a consistent description style.

## 8. Optional subsections and null values

A subsection may be absent if the contract allows it. Example payload:

```json
{
  "name": "Engineering team"
}
```

Descriptor:

```java
requestPartFields("metadata",
    fieldWithPath("name").description("Profile name"),
    subsectionWithPath("owner")
        .description("Owner information")
        .optional()
)
```

`optional()` allows the `owner` subsection to be missing from the test payload. If `owner` is present with a `null` value, that is a different state from the field being absent; decide and test separately per contract. Do not assume `optional()` means every case of `null`, empty object, or missing child fields is valid.

If `owner` may be absent, yet inside `owner` the `id` field is required whenever the object is present, document this rule clearly and write tests for both branches:

- Without `owner`: valid.
- With `owner` but missing `id`: invalid.
- With `owner.id`: valid if other constraints are satisfied.

## 9. Complete example with MockMvc and Spring REST Docs

### 9.1. DTO and controller

We use a `metadata` part containing nested objects:

```java
import java.util.List;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;

record Owner(String id, String displayName) {}
record Contact(String type, String value) {}
record ProfileMetadata(String name, Owner owner, List<Contact> contacts) {}
record ProfileReceipt(String profileId, String name, String ownerId) {}

@RestController
class ProfileController {

    @PostMapping(
            path = "/api/profiles",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    ProfileReceipt create(@RequestPart("metadata") ProfileMetadata metadata) {
        String ownerId = metadata.owner() == null ? null : metadata.owner().id();
        return new ProfileReceipt("PRO-100", metadata.name(), ownerId);
    }
}
```

The controller above only illustrates binding a JSON part into a DTO. A real system should place validation, authorization, and profile persistence logic in appropriate components.

### 9.2. Creating the multipart part

```java
import java.nio.charset.StandardCharsets;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;

MockMultipartFile metadata = new MockMultipartFile(
        "metadata",
        "",
        MediaType.APPLICATION_JSON_VALUE,
        """
        {
          "name": "Engineering team",
          "owner": {
            "id": "USR-42",
            "displayName": "Platform Team"
          },
          "contacts": [
            {"type": "SUPPORT", "value": "support@example.test"},
            {"type": "SALES", "value": "sales@example.test"}
          ]
        }
        """.getBytes(StandardCharsets.UTF_8));
```

The part is named `metadata` with Content-Type `application/json`; the JSON body contains the `owner` object and `contacts` array.

### 9.3. Documenting subsections in the part

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestPartFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;
import static org.springframework.restdocs.request.RequestDocumentation.partWithName;
import static org.springframework.restdocs.request.RequestDocumentation.requestParts;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class ProfilePartSubsectionDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new ProfileController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsOwnerAndContactsAsSubsections() throws Exception {
        MockMultipartFile metadata = new MockMultipartFile(
                "metadata",
                "",
                MediaType.APPLICATION_JSON_VALUE,
                """
                {
                  "name": "Engineering team",
                  "owner": {
                    "id": "USR-42",
                    "displayName": "Platform Team"
                  },
                  "contacts": [
                    {"type": "SUPPORT", "value": "support@example.test"},
                    {"type": "SALES", "value": "sales@example.test"}
                  ]
                }
                """.getBytes(StandardCharsets.UTF_8));

        mockMvc.perform(multipart("/api/profiles").file(metadata))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.profileId").value("PRO-100"))
                .andExpect(jsonPath("$.name").value("Engineering team"))
                .andExpect(jsonPath("$.ownerId").value("USR-42"))
                .andDo(document("profile-create",
                        requestParts(
                                partWithName("metadata")
                                        .description("Profile metadata as JSON")
                        ),
                        requestPartFields("metadata",
                                fieldWithPath("name").description("Profile name"),
                                subsectionWithPath("owner")
                                        .description("Owner information; Owner schema"),
                                subsectionWithPath("contacts")
                                        .description("List of contacts; Contact schema")
                        )));
    }
}
```

In the example, `requestParts(...)` documents the `metadata` part; `requestPartFields("metadata", ...)` documents `name` and the two subsections `owner` and `contacts`. Assertions verify that the `owner` object was deserialized into the DTO and that the controller read `owner.id` accurately.

If API consumers need to know the child fields of `owner` and `contacts`, replace the respective subsections with specific descriptors:

```java
requestPartFields("metadata",
    fieldWithPath("name").description("Profile name"),
    fieldWithPath("owner.id").description("Owner identifier"),
    fieldWithPath("owner.displayName").description("Display name"),
    fieldWithPath("contacts[].type").description("Contact type"),
    fieldWithPath("contacts[].value").description("Contact address or value")
)
```

## 10. Common errors

| Symptom | Cause | How to handle |
| --- | --- | --- |
| Subsection `owner` not found | JSON part lacks `owner` or path is misspelled | Check the body of the right part and field names |
| Snippet only shows row `owner`, not `owner.id` | Used `subsectionWithPath("owner")` | Replace with specific field descriptors if detailed schema is needed |
| Overlapping subsection and child field descriptors | Declared `owner` as subsection while also describing `owner.id` in the same list | Pick one description level or separate schema into another section |
| Optional child field fails documentation | Field descriptor lacks `.optional()` | Mark optional if contract allows the field to be absent |
| Absent object and null object treated identically | Nullability semantics not defined | Write separate descriptions and tests for absent, null, and empty object |
| Array not documented as expected | Wrong JSON path, missing `[]` for element fields | Inspect JSON structure and use matching path |
| JSON part fails to parse | Wrong part Content-Type or invalid body | Send `application/json` with valid JSON |
| Snippet generated but readers cannot understand child schema | Subsection description is too brief | State referenced schema clearly or expand into field descriptors |

## 11. WebTestClient, REST Assured, and documentation

Subsection descriptors do not depend on the test client. What matters is that the test client sends the right multipart part and the documentation mechanism attaches the part payload snippet.

### 11.1. WebTestClient

You can use `MultipartBodyBuilder` to build the JSON part:

```java
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.web.reactive.function.BodyInserters;

MultipartBodyBuilder body = new MultipartBodyBuilder();
body.part("metadata", """
        {
          "name": "Engineering team",
          "owner": {"id":"USR-42","displayName":"Platform Team"}
        }
        """)
        .contentType(MediaType.APPLICATION_JSON);

webTestClient.post()
        .uri("/api/profiles")
        .body(BodyInserters.fromMultipartData(body.build()))
        .exchange()
        .expectStatus().isOk();
```

When adding documentation, use `requestPartFields("metadata", subsectionWithPath("owner")...)` inside the `document(...)` call of the WebTestClient integration. The code above illustrates creating the request; the client must be configured with Spring REST Docs beforehand.

### 11.2. REST Assured

REST Assured can send a JSON part as a multipart part:

```java
given()
        .filter(documentationFilter)
        .multiPart("metadata",
                "{\"name\":\"Engineering team\","
                        + "\"owner\":{\"id\":\"USR-42\","
                        + "\"displayName\":\"Platform Team\"}}",
                "application/json")
        .when()
        .post("/api/profiles")
        .then()
        .statusCode(200);
```

`documentationFilter` must be configured with `requestParts(...)` and `requestPartFields("metadata", ...)` containing the subsection descriptor. The specific multipart overload depends on the REST Assured version; inspect the Content-Type and body of the part actually sent by the request.

### 11.3. Inserting snippets into Asciidoctor

Documentation example:

```asciidoc
= Profile API

== Create profile

=== Request parts

include::{snippets}/profile-create/request-parts.adoc[]

=== Metadata fields

include::{snippets}/profile-create/request-part-metadata-fields.adoc[]

=== Multipart request

include::{snippets}/profile-create/http-request.adoc[]
```

Actual snippet paths depend on the template format and Spring REST Docs version. Check the `generated-snippets/profile-create` directory after running tests and use the exact filenames rather than guessing snippet names. If using Markdown, configure `TemplateFormats.markdown()` and use a suitable snippet assembly workflow; standard Markdown lacks a built-in include syntax like Asciidoctor.

## 12. Build and CI integration

Implementation workflow:

1. Declare the Spring REST Docs dependency matching MockMvc, WebTestClient, or REST Assured.
2. Write multipart tests with a representative JSON part and assertions for fields the application actually binds.
3. Use `requestParts(...)` for parts and `requestPartFields(...)` with `subsectionWithPath(...)` or `fieldWithPath(...)` for the body.
4. Configure a snippet directory such as `build/generated-snippets` (Gradle) or `target/generated-snippets` (Maven).
5. Make the Asciidoctor task depend on the test task and include the exact generated snippets.
6. Run tests and render documentation in CI. When the JSON part changes, strict payload snippets help detect outdated descriptors.

Example Gradle command once tasks are declared:

```bash
./gradlew test asciidoctor
```

Do not document an entire subsection with a single description line and treat it as a substitute for validation. Required rules, optionality, enums, nullability, and cross-field relationships must be enforced in the application and verified with dedicated tests.

## 13. Hands-on exercise

The `POST /api/projects` API receives a `metadata` part with the payload:

```json
{
  "name": "REST Docs rollout",
  "owner": {
    "userId": "USR-10",
    "team": {
      "code": "PLATFORM",
      "displayName": "Platform Engineering"
    }
  },
  "settings": {
    "visibility": "TEAM",
    "notifications": {
      "email": true,
      "webhook": false
    }
  },
  "labels": [
    {"name": "backend"},
    {"name": "documentation"}
  ]
}
```

Perform the following:

1. Create a controller binding `@RequestPart("metadata")` to a corresponding DTO.
2. Write a MockMvc test sending the JSON part with `application/json`.
3. Document `name` in detail; document `owner`, `settings`, and `labels` using `subsectionWithPath(...)`.
4. Create a second variant expanding `owner.team.code`, `owner.team.displayName`, `settings.notifications.email`, and `labels[].name` with `fieldWithPath(...)`.
5. Try omitting `settings` from the payload; determine and document optionality properly if the API permits it.
6. Add tests for `owner = null` and an `owner` object missing `userId`, verifying results against the validation contract.
7. Generate snippets and integrate them into Asciidoctor/CI.

**Completion criteria:** Choose the right level of detail for each subsection; JSON paths match the payload; no overlapping descriptors are declared; documentation clearly distinguishes which portions are grouped and which are explained in detail.

## 14. Key takeaways

`subsectionWithPath(...)` allows documenting an object or group of nested fields as a single entry in the field table of `requestPartFields(partName, ...)`. Use it when a sub-structure has its own schema or is too large to list in the main table; use `fieldWithPath(...)` when API consumers need to know the name, type, and meaning of each specific field. Combine `requestParts(...)`, `requestPartFields(...)`, multipart tests, and Asciidoctor/Markdown snippets so part body documentation stays both clear and verifiable in build/CI.

### References

- [Spring REST Docs — Request Part Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-part-payloads.html)
- [Spring REST Docs — PayloadDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/payload/PayloadDocumentation.html)
- [Spring REST Docs — Request Parts](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-parts.html)
- [Spring Framework — Multipart Forms and RequestPart](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html)
