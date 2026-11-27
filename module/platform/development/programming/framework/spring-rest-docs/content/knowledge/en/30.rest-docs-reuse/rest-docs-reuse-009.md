# Avoiding semantic errors when reusing descriptors

## 1. How can descriptor reuse break the API contract?

Spring REST Docs produces verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. Tests send requests, verify responses, and use descriptors to document payload fields, parameters, headers, cookies, and links. Descriptors produce snippets; snippets are compiled into Asciidoctor/Markdown and integrated into the build and CI.

Reusing descriptors reduces duplication, yet a descriptor is not merely a line of description to print in a table. It also expresses the operation's contract: whether a field is required, whether a parameter may be absent, which headers must appear, which links are advertised, and which part of the payload is being documented.

If you use one shared descriptor across endpoints with different contracts, the documentation can be wrong even though tests still pass:

- A field required on endpoint A gets marked optional because endpoint B allows omitting it.
- A response-only header gets mistakenly used in a request.
- ignored() hides an important field that another endpoint is supposed to advertise.
- A generic description no longer matches the context of each resource.
- A descriptor for a nested path is used at the root, producing the wrong path or meaning.

The rule is to reuse structure and terminology that are genuinely identical, while declaring operation-specific state and semantics separately.

## 2. Descriptors describe contracts, not just table formatting

A descriptor typically carries several aspects:

| Aspect | Example | Impact |
| --- | --- | --- |
| Identifier | fieldWithPath("email") | Selects the field in the payload |
| Meaning | description("Email address") | Content shown to readers |
| State | optional(), ignored() | Specifies whether the field may be missing or ignored |
| Metadata | attributes(key("format").value("email")) | Additional information for templates |
| Extraction context | beneathPath(...) | Selects a subsection of a payload or links |

When two endpoints both have an id field, they do not necessarily share the same meaning. id in a user response may be a user ID; id in an order creation request may be an idempotency key. Do not share descriptions merely because path names match.

Before sharing a descriptor, compare:

1. Are the paths or header/parameter names identical?
2. Is the meaning to the client identical?
3. Do the fields/parameters share the same required/optional behavior?
4. Do they share the same type, format, constraints, and lifecycle?
5. Is the descriptor extracted from the same payload level or the same HTTP message direction?

Only when these align should you use a shared factory.

## 3. Distinguishing shared structure from endpoint-specific contracts

| Category | Shareable? | Example |
| --- | --- | --- |
| Structural conventions | Usually yes | Describing correlation headers, timestamp formats |
| Endpoint semantics | Needs per-operation review | Required fields, status transitions, mandatory filters |

For example, two endpoints both use X-Correlation-ID with the same meaning:

~~~java
static HeaderDescriptor correlationIdHeader() {
    return headerWithName("X-Correlation-ID")
            .description("Correlation ID for tracing the request");
}
~~~

This factory can be shared if both endpoints genuinely accept the same header with the same requirements. Conversely, do not create one common request fields set for every endpoint just because many payloads contain a name field.

## 4. Do not share optional/ignored state unconditionally

optional() and ignored() change how a descriptor participates in validation and snippets:

- optional() indicates the field/parameter/header may be absent in a valid operation.
- ignored() excludes the descriptor from the documentation section and corresponding checks.
- Relaxed mode permits undocumented data to appear within the configured snippet scope.

These states are not presentation preferences. They reflect the contract. For example:

~~~java
// Profile creation API requires email
fieldWithPath("email")
        .description("Email address")

// Profile update API allows omitting email
fieldWithPath("email")
        .optional()
        .description("New email address if changing")
~~~

Both fields share the same path but have different contracts. Do not use a single descriptor configured as optional for both operations.

Similarly, ignored() is not a shortcut for every field you do not feel like documenting yet. If a field is part of the contract clients need to know about, document it. Only ignore a field when intentionally excluding it from documentation and after understanding the validation impact.

## 5. Use factories to create fresh descriptors per context

A safe approach is creating fresh descriptors on each factory call. Share the factory helper and standard description text, rather than sharing a single state-mutated descriptor across multiple operations:

~~~java
import org.springframework.restdocs.payload.FieldDescriptor;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.snippet.Attributes.key;

final class CommonFieldDescriptors {

    private CommonFieldDescriptors() {
    }

    static FieldDescriptor requiredEmail() {
        return fieldWithPath("email")
                .description("Email address")
                .attributes(key("format").value("email"));
    }

    static FieldDescriptor optionalEmail() {
        return fieldWithPath("email")
                .optional()
                .description("New email address if changing")
                .attributes(key("format").value("email"));
    }
}
~~~

Use in the appropriate context:

~~~java
requestFields(CommonFieldDescriptors.requiredEmail());
requestFields(CommonFieldDescriptors.optionalEmail());
~~~

Separate factories make the state explicit at the call site. When business descriptions differ, name factories after their meaning, such as requiredBillingEmail() or optionalContactEmail(), instead of creating a generic helper with hard-to-read boolean flags.

## 6. Avoid keeping shared descriptors in mutable arrays

Do not declare a global descriptor array and modify its elements per test. Doing so makes meaning depend on call order and can cause failures when tests run in parallel.

Unsafe:

~~~java
static final FieldDescriptor EMAIL =
        fieldWithPath("email").description("Email address");

// Multiple tests modify or reconfigure this same descriptor.
~~~

Prefer creating fresh ones via a factory:

~~~java
static FieldDescriptor emailField(boolean optional) {
    FieldDescriptor descriptor = fieldWithPath("email")
            .description("Email address");
    return optional ? descriptor.optional() : descriptor;
}
~~~

However, do not overuse booleans if the parameter name fails to convey the full contract. Two factories, requiredEmail() and optionalEmail(), are usually easier to read and review.

Arrays passed to requestFields(...), responseFields(...), or requestHeaders(...) should also be created separately per operation. Avoid mutating an array after passing it to a snippet.

## 7. Do not mix request and response descriptors

Some header names appear in both requests and responses with different meanings. For example, Content-Type:

~~~java
static HeaderDescriptor requestContentType() {
    return headerWithName("Content-Type")
            .description("Media type of the request body");
}

static HeaderDescriptor responseContentType() {
    return headerWithName("Content-Type")
            .description("Media type of the response body");
}
~~~

Both helpers use the same header name, yet have direction-specific descriptions. Similarly, do not share request and response cookies just because cookie names match. Use requestCookies(...) for cookies sent by the client and responseCookies(...) for cookies returned by the server.

~~~java
document("login",
        requestHeaders(requestContentType()),
        responseHeaders(responseContentType()));
~~~

Separating helpers by request/response prevents describing the wrong direction of transfer and helps reviewers see what the endpoint advertises.

## 8. Do not reuse descriptors across different path contexts

A payload subsection extractor can change the context in which a descriptor is interpreted. For example, the same id field can appear both at the root and inside an embedded resource:

~~~json
{
  "id": "collection-1",
  "_embedded": {
    "orders": [
      {"id": "order-42", "status": "PAID"}
    ]
  }
}
~~~

The root field and the field inside orders[] do not necessarily have the same meaning. Document them separately:

~~~java
responseFields(
        fieldWithPath("id").description("Collection ID"),
        subsectionWithPath("_embedded.orders")
                .description("Embedded orders"));

responseFields(
        beneathPath("_embedded.orders[]"),
        fieldWithPath("id").description("Order ID"),
        fieldWithPath("status").description("Order status"));
~~~

The two snippets have different contexts. Do not take the root id descriptor and reuse it directly inside the subsection if the business descriptions differ.

## 9. Reuse subsets of descriptors instead of the whole set

When two operations share only a few fields, combine the shared subset with specific fields:

~~~java
static FieldDescriptor[] auditFields() {
    return new FieldDescriptor[] {
            fieldWithPath("createdAt")
                    .description("Creation timestamp")
                    .attributes(key("format").value("ISO-8601")),
            fieldWithPath("updatedAt")
                    .description("Last update timestamp")
                    .attributes(key("format").value("ISO-8601"))
    };
}

static FieldDescriptor[] orderFields() {
    return Stream.concat(
            Arrays.stream(auditFields()),
            Stream.of(
                    fieldWithPath("orderNumber").description("Order number"),
                    fieldWithPath("status").description("Order status")))
            .toArray(FieldDescriptor[]::new);
}
~~~

This example shares the audit fields group while keeping order fields separate. When combining descriptors, verify there are no duplicate paths and no conflicting descriptions. If endpoints share a field but differ in format or visibility permissions, create context-specific factories instead of mutating a shared descriptor.

## 10. When should relaxed mode be used?

Relaxed mode is useful when an operation intentionally documents only a portion of a payload or parameter set. However, relaxed mode does not replace defining the contract:

- If an undocumented field is internal, consider intentional ignored() or appropriate preprocessing.
- If a field is part of the public API, document it instead of relying on relaxed mode so tests always pass.
- If only one endpoint has extra fields, apply a specific descriptor/relaxed policy to that endpoint alone.
- Do not configure relaxed mode globally just to avoid updating descriptors when the API changes.

For example, an endpoint returns an extended object, but the documentation page only wants to document basic fields:

~~~java
relaxedResponseFields(
        fieldWithPath("id").description("Resource ID"),
        fieldWithPath("name").description("Resource name"))
~~~

Authors should clearly note the documentation scope that intentionally omits other fields. If the goal is complete documentation and detecting contract changes, use strict descriptors so tests catch new fields.

## 11. Example of two operations with different contracts

Suppose a profile creation API requires email, while an update API accepts partial data:

~~~java
@Test
void createProfileDocumentsRequiredEmail() throws Exception {
    mockMvc.perform(post("/api/profiles")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"email":"an@example.test","displayName":"An"}
                            """))
            .andExpect(status().isCreated())
            .andDo(document("profiles-create",
                    requestFields(
                            CommonFieldDescriptors.requiredEmail(),
                            fieldWithPath("displayName")
                                    .description("Display name"))));
}

@Test
void updateProfileDocumentsOptionalEmail() throws Exception {
    mockMvc.perform(patch("/api/profiles/{id}", "profile-7")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"displayName":"An Nguyen"}
                            """))
            .andExpect(status().isOk())
            .andDo(document("profiles-update",
                    requestFields(
                            CommonFieldDescriptors.optionalEmail(),
                            fieldWithPath("displayName")
                                    .optional()
                                    .description("New display name if changing"))));
}
~~~

Examples must be adapted to your actual controllers and DTOs. Both use the email concept, yet required/optional differs by operation. Separate descriptors preserve exact semantics and help tests detect when contracts change.

## 12. Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Required field documented as optional | Reused an optional descriptor from another endpoint | Create separate required/optional factories |
| Field disappears from snippet | Used ignored() on a shared descriptor | Only ignore in the operation that genuinely needs it |
| Description does not fit context | Shared descriptors purely based on path name | Compare business meaning and payload type |
| Request header has a response description | Shared helper without distinguishing transfer direction | Create request/response descriptor factories |
| Nested field wrongly described | Used descriptor in the wrong subsection context | Create descriptors for the specific path/subsection |
| Tests behave unstably | Shared mutable descriptors/arrays across tests | Create fresh descriptors from factories per operation |
| New field does not fail tests | Used relaxed mode too broadly | Return to strict mode for public contract parts |
| Duplicate descriptions or paths | Combined shared and specific descriptors without checking | Review paths after composition |

## 13. Practice exercise

1. Create two endpoints sharing an email field where one requires it and the other treats it as optional.
2. Write two factories returning separate descriptors and use the right factory in each test.
3. Create helpers for request Content-Type and response Content-Type with distinct descriptions.
4. Reuse an audit fields group for order and customer while keeping resource-specific fields separate.
5. Create a response containing root id and embedded orders[].id; document their two distinct meanings.
6. Experiment with ignored() and relaxed response fields, noting which cases are appropriate in a public contract.
7. Run documentation tests to confirm strict descriptors catch undocumented fields/parameters.

**Completion criteria:** determine when descriptors are genuinely shareable; avoid semantically wrong sharing of optional/ignored state; distinguish request/response and path contexts; use factories to create fresh descriptors; preserve strictness matching the API contract.

## 14. Pre-commit checklist

- [ ] Shared descriptors have the same business meaning across every operation.
- [ ] Required/optional/ignored accurately reflect each endpoint's contract.
- [ ] Factories create fresh descriptors per operation or context.
- [ ] Request and response descriptors are separated when meanings differ.
- [ ] Same-named fields at root and in subsections are documented in their respective contexts.
- [ ] Shared and specific descriptors introduce no duplicate paths or conflicting descriptions.
- [ ] Relaxed mode is only used when intentionally documenting part of a contract.
- [ ] Strict descriptors still protect critical parts of the public API.
- [ ] Documentation tests have been rerun and snippets reflect the contract accurately.

**Remember:** Only reuse descriptors when path, meaning, and contract state are genuinely identical. Share factories and description conventions, while creating separate descriptors for operations with different required/optional rules, request/response directions, or subsection contexts so Spring REST Docs documentation never misrepresents API semantics.
