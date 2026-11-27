# Distinguishing custom snippets from hand-written documentation

## 1. Two ways to create content in API documentation

When building REST API documentation, not all information is suited to automatic generation from tests. Some content can be verified directly from HTTP requests/responses, while other parts require an author to explain context, workflows, or business decisions.

In **SPRING_REST_DOCS**, Spring REST Docs receives data from HTTP tests using MockMvc, WebTestClient, or REST Assured. Default snippets describe requests, responses, headers, fields, parameters, and parts. When a new snippet type is needed, the team can create a **custom snippet** that reads the operation context and renders with a template. By contrast, hand-written documentation is the Markdown or AsciiDoc prose maintained directly by authors.

The two approaches serve different goals:

- **Custom snippets** generate structured content from an operation recorded by a test. They fit information that must match HTTP data, such as method, URI, status, selected headers, or multipart part lists.
- **Hand-written documentation** presents human-authored content, such as design rationale, integration guides, business workflows, high-level examples, operational notes, or decisions that cannot be expressed by a single HTTP call.

This lesson belongs to the **Snippet customization** chapter of **SPRING_REST_DOCS** — a module for generating verifiable REST API documentation from HTTP tests, creating snippets for requests, responses, payloads, parameters, and headers, then compiling Asciidoctor/Markdown and integrating into build/CI.

After this lesson, you will be able to:

- Distinguish the data sources and verification mechanisms of custom snippets versus hand-written documentation.
- Choose which content should be auto-generated and which should be hand-authored.
- Understand the limits of test-based verification and the risks of hand-written content.
- Combine snippets with Markdown/AsciiDoc explanations in a cohesive document.
- Design reviews and CI checks to catch stale content or missing snippets.
- Avoid treating custom snippets as a replacement for all instructional documentation.

## 2. What is a custom snippet?

A custom snippet is a documentation component registered in `document(...)` and executed against Spring REST Docs' operation context. The operation contains the request and response recorded by the test, along with related attributes.

For example, to produce `operation-summary.adoc` with HTTP method, URI, and status:

```java
public class OperationSummarySnippet extends TemplatedSnippet {

    public OperationSummarySnippet() {
        super("operation-summary", "operation-summary", Map.of());
    }

    @Override
    protected Map<String, Object> createModel(Operation operation) {
        Map<String, Object> model = new LinkedHashMap<>();
        model.put("operationName", operation.getName());
        model.put("method", operation.getRequest().getMethod().name());
        model.put("uri", operation.getRequest().getUri().toString());
        model.put("status", operation.getResponse().getStatus().value());
        return model;
    }
}
```

Mustache template:

```adoc
.Operation summary
|===
|Property|Value

|Operation
|{{operationName}}

|HTTP method
|{{method}}

|URI
|{{uri}}

|Status
|{{status}}
|===
```

Register the snippet alongside default snippets:

```java
mockMvc.perform(get("/api/products/{id}", 42)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("products-get",
        new OperationSummarySnippet(),
        responseFields(
            fieldWithPath("id").description("Product ID"),
            fieldWithPath("name").description("Product name")
        )
    ));
```

When the test runs, Spring REST Docs invokes the custom snippet with `Operation`, the custom snippet builds the model, and the template renders the content. The output can be:

```text
build/generated-snippets/
└── products-get/
    ├── operation-summary.adoc
    └── response-fields.adoc
```

This is still documentation generated automatically from tests. Developers write the Java class and template, while the values of `method`, `uri`, and `status` come from the actual operation.

A custom snippet does not have to use `TemplatedSnippet`; you can implement `Snippet` directly if you need complete control over output generation. `TemplatedSnippet` is convenient when content is rendered via Mustache.

## 3. What is hand-written documentation?

Hand-written documentation is content written directly by authors in `.adoc` or `.md` files. It can be rendered by Asciidoctor or a Markdown builder, but Spring REST Docs does not automatically check every sentence against HTTP operations.

Example guide written in AsciiDoc:

```adoc
== Retrieving product information

This API is used to display the product detail page.
Clients need catalog read permission before calling the endpoint.

=== Usage workflow

. Retrieve the product ID from the catalog list.
. Call the detail API with the product ID.
. Display name, price, and stock status from the response.

=== Notes

If a product has been discontinued, clients may still receive
a successful response, but the `active` field will be `false`.
```

Or Markdown:

```markdown
## Retrieving product information

This API serves the product detail screen. Clients need
catalog read permission before calling the endpoint.

### Workflow

1. Retrieve the product ID from the catalog list.
2. Call the detail API with the product ID.
3. Display the returned data.

### Notes

Discontinued products can still be queried.
```

Authors are responsible for the content, accuracy, and updating these explanations when business rules change. The build can verify syntax or includes, but successful rendering alone does not prove every descriptive sentence matches the application.

Hand-written documentation does not mean low-quality documentation. It is essential for things that cannot be inferred from a single HTTP exchange, such as intended use cases, business flows, design decisions, retry guidance, or multi-operation integration examples.

## 4. Comparing by data source and verifiability

| Criterion | Custom snippet | Hand-written documentation |
| --- | --- | --- |
| Data source | Operation context, descriptors, and attributes | Content supplied by authors |
| Generation time | When documentation tests run | When authoring or compiling documentation |
| HTTP verification | Can be checked against recorded requests/responses | Not automatically verified against HTTP exchanges |
| How created | Java `Snippet`/`TemplatedSnippet` and template | Markdown/AsciiDoc |
| Structure | Backed by schema/model and template | Flexible according to authoring goals |
| API changes | Can fail tests/snippets when data mismatches | Can go stale while the build still succeeds |
| Business context | Only present if tests pass it or operations carry it | Can explain context more thoroughly |
| Maintenance | Must keep code, model, and template compatible | Needs content reviews and owners to update |
| Reusability | Good across many operations sharing structure | Good for guides, workflows, and overview chapters |

Key point: custom snippets **can be verified**, but that does not mean every piece of data inside them is automatically accurate. If a snippet puts `constraints`, `label`, or `businessRule` from a hard-coded value in Java, the test only confirms the snippet rendered; it does not prove that rule matches the application's actual validation.

Example:

```java
model.put("maxUploadSize", "5 MiB");
```

The value above is simply author-provided metadata. To make it reflect the real configuration, retrieve it from an authoritative config source or write tests/assertions comparing it against enforced limits.

## 5. Choosing custom snippets for content tied to HTTP exchanges

Use a custom snippet when content can be extracted from an operation and must stay synchronized with tests.

Suitable cases:

- Method, URI, response status, and Content-Type.
- Selected request/response headers.
- Multipart part name, filename, Content-Type, and size.
- A concise summary block for an operation.
- Correlation headers or pagination metadata recorded by tests.
- Structured technical content that needs to be generated uniformly across many operations.

Example multipart summary snippet:

```java
for (OperationRequestPart part : operation.getRequest().getParts()) {
    Map<String, Object> item = new LinkedHashMap<>();
    item.put("name", part.getName());
    item.put("filename", part.getSubmittedFileName());
    item.put("contentType", part.getHeaders().getContentType());
    item.put("size", part.getContent().length);
    parts.add(item);
}
```

The output is generated from the actual multipart request in the test. If the `image` part changes its Content-Type or filename, subsequent snippet generation reflects the new data.

Use an allowlist when extracting headers; never dump `Authorization`, `Cookie`, tokens, or sensitive data. For filenames or query strings that may hold private data, sanitize them before putting them into the model.

### 5.1. Do not generate content an operation cannot prove

The operation context does not inherently know:

- At which step of a business process users should call the API.
- Why a field is required by product policy.
- Recommended retry or backoff conditions.
- Overall authorization rules if a test only runs as one account.
- Limits enforced at an API gateway if the test only calls the controller.
- SLAs, quotas, or operational commitments.

You can pass this information as attributes or configuration for templates to display, but unless it is sourced and verified from a trustworthy source, treat it as authored content. Do not label a column "Verified" for a value entered purely by hand.

## 6. Choosing hand-written documentation for explanatory content

Use Markdown/AsciiDoc directly for:

- Product introductions and API scope.
- Authentication, authorization concepts, and how to obtain tokens.
- Business workflows spanning multiple operations.
- Retry, idempotency, timeout, and rate-limit policies.
- Client-side error handling flows.
- SDK guides and examples combining multiple endpoints.
- Design decisions, migration guides, and changelogs.
- Explaining limits that cannot yet be verified by a single HTTP test.

For example, a retry guide section:

```markdown
### Handling transient errors

When receiving a 503 error, the client may retry according to the
application's retry policy. Use exponential backoff and limit the total number
of retries. Do not automatically retry write operations unless the
request's idempotency has been confirmed.
```

This paragraph needs review by someone who understands operational and business contracts. It is not verified merely because the Markdown page builds cleanly.

For critical topics like retries, timeouts, quotas, or security, cite the authoritative source and owner. For instance, if values come from runtime configuration, avoid duplicating hard-coded numbers across multiple pages.

## 7. Combining custom snippets with hand-written documentation

In practice, complete API documentation usually combines both approaches:

1. Authors describe purpose, usage workflows, and business notes in Markdown/AsciiDoc.
2. HTTP tests verify requests/responses and generate snippets.
3. Documentation pages include the snippets in the right locations.
4. The build verifies snippets exist and documentation renders cleanly.
5. Reviewers check both auto-generated data and authored content.

Example AsciiDoc page combining both:

```adoc
= Product API
:toc: left

== Retrieving product information

This API serves the product detail page. Clients need
catalog read permission before calling the endpoint.

=== HTTP request and response

include::{snippets}/products-get/http-request.adoc[]

include::{snippets}/products-get/http-response.adoc[]

=== Operation summary

include::{snippets}/products-get/operation-summary.adoc[]

=== Response fields

include::{snippets}/products-get/response-fields.adoc[]

=== Usage guide

. Call the endpoint with the product ID received from the catalog.
. Read the `active` field to determine whether the product is still active.
. Display `price` in the currency specified in the response.
```

In this example:
- The introduction and usage guide are maintained by authors.
- `http-request`, `http-response`, `operation-summary`, and `response-fields` are generated from tests.
- The page blends both sources into one seamless document.

Avoid manually repeating values already present in snippets. If the URI changes, the snippet will regenerate; a hand-written sentence repeating the URI may keep the old value and cause a contradiction.

## 8. Example comparison: one endpoint, two responsibilities

Suppose the `GET /api/products/{id}` endpoint returns:

```json
{
  "id": 42,
  "name": "Java in Practice",
  "active": true,
  "price": 250000
}
```

### Part generated from tests

Tests can verify:
- Status `200`.
- Response Content-Type is `application/json`.
- JSON has `id`, `name`, `active`, `price`.
- Field types and descriptions declared in `responseFields(...)`.
- URI contains the exact product ID sent.

Example:

```java
mockMvc.perform(get("/api/products/{id}", 42)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(42))
    .andDo(document("products-get",
        responseFields(
            fieldWithPath("id").description("Product ID"),
            fieldWithPath("name").description("Product name"),
            fieldWithPath("active").description("Whether the product is still active"),
            fieldWithPath("price").description("Product price, in VND")
        )
    ));
```

Generated snippets verify that documented fields exist in the sample response. If the response gains a new field before strict descriptors are updated, the test can fail; if a required documented field is absent from the sample response, the test can also fail.

### Part written by hand

Authors need to explain:
- Which screen or use case the endpoint serves.
- From which prior operation the client obtains `id`.
- How discontinued products should be displayed.
- Whether responses should be cached.
- Special business error cases.

These points are not proven by a single sample response alone. Business documentation or appropriate tests are needed as the source of confirmation.

## 9. Managing change and preventing drift

Both custom snippets and hand-written docs can go stale, though they are detected differently.

| Change | Custom snippet | Hand-written documentation |
| --- | --- | --- |
| URI changes in test | Automatically reflected on next generation | Hand-written sentences mentioning the URI can go stale |
| Response adds new field | Strict `responseFields` can catch undocumented fields | Hand-written field explanations need review |
| Error status changes | Test assertions/snippets can catch it | Hand-written status tables need updating |
| Retry policy changes | Single operations usually do not know | Owner must update the guide |
| Template changes | Snippet output can change | Hand-written prose is minimally affected |
| Business field name changes | Descriptors/tests must be updated | Related explanatory prose also needs review |

Management recommendations:

- Use tests and strict descriptors for observable parts of the contract.
- Separate business and operational rules into owned content.
- Link to a canonical policy source instead of copying numbers repeatedly.
- Review prose mentioning URIs, statuses, fields, or headers to avoid duplicating auto-generated data.
- When the contract changes, inspect both snippets and hand-written sections that depend on it.
- Save generated snippets in CI artifacts or pull request diffs for review.

## 10. Verification and review in CI

A documentation pipeline may include these steps:

```text
HTTP documentation tests
          |
          v
Spring REST Docs generates snippets
          |
          +----------------------+
          |                      |
          v                      v
Custom snippet output       Static AsciiDoc/Markdown
          |                      |
          +----------+-----------+
                     |
                     v
           Asciidoctor / Markdown build
                     |
                     v
             Link/include checks
                     |
                     v
              Review and publish
```

CI can automatically verify:
- Documentation tests pass.
- Expected snippets were generated.
- Custom snippets contain the required method/status/part values.
- Asciidoctor includes do not point to missing files.
- Markdown/AsciiDoc builds have no supported syntax errors.

CI cannot fully verify automatically:
- Whether introductory prose is business-accurate.
- Whether hand-written examples still fit the API version.
- Whether retry recommendations are safe.
- Whether hard-coded quota tables match operational config.
- Whether multi-step workflows describe the right sequence.

Therefore, pull requests changing documentation need two review scopes: test/snippet review and prose/policy review. Use code owners or appropriate reviewers for each part.

## 11. Common mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Putting an entire guide inside a custom snippet | Chose the wrong mechanism for explanatory content | Write prose in AsciiDoc/Markdown and include related snippets |
| Manually copying URI/status in many places | Duplicating data that can be generated from operations | Include `http-request`, `http-response`, or custom snippets |
| Assuming custom snippets are always right | Model may contain hard-coded values | Identify data sources and add assertions for each value |
| Prose is wrong yet CI still passes | Build only checks rendering, not business meaning | Review content and specify owners/sources |
| Snippet is not generated | Forgot to register custom snippet in `document(...)` or test did not run | Check tests and operation output directory |
| Include is missing | Operation/snippet name in docs does not match | Verify generated paths and includes |
| Hand-written content goes stale after API change | No links or responsible owner | Search references and review dependent sections |
| Token leaked in custom snippet | Put all operation headers into the model | Use an allowlist, masking, and synthetic test data |
| Using snippets to publish unverified quotas | Hand-entered values presented as runtime data | Pull from config sources or state clearly that it is authored policy |

## 12. Decision workflow for choosing representation

Before adding a piece of content, ask:

1. Does the value appear directly in the tested HTTP exchange?
2. Can the value be retrieved reliably from `Operation` or descriptors?
3. Should tests fail when the value changes or becomes invalid?
4. Does the content need to explain context, rationale, or multi-step guidance?
5. Who is responsible for updating it when policies or business rules change?

Practical rule of thumb:

| If the content... | Preferred representation |
| --- | --- |
| Is a tested method, URI, status, header, payload, or part | Default snippet or custom snippet |
| Is a fields, parameters, or links table | Default snippet with descriptors |
| Is a new table whose data comes from the operation | Custom snippet |
| Is API purpose, use cases, and business workflows | Hand-written documentation |
| Is operational or retry policy | Hand-written documentation with owner/source |
| Is an HTTP example that must match tests | Include generated snippet |
| Is a guide combining multiple operations | Hand-written documentation combining multiple snippets |

No rule forces a page to use only one approach. A strong page usually combines explanatory prose with verified snippets.

## 13. Hands-on exercises

For the `GET /api/products/{id}` endpoint:

1. Write a MockMvc test verifying status and response fields.
2. Include `http-request.adoc`, `http-response.adoc`, and `response-fields.adoc` in your documentation.
3. Create `OperationSummarySnippet` to generate method, URI, and status in a table.
4. Hand-write an introduction covering use cases, access permissions, and client usage steps.
5. Add a retry or caching section, stating the policy source and owner.
6. Change the endpoint URI in the mapping and run the test; verify that the snippet reflects the new URI.
7. Review prose mentioning the URI or fields to spot stale content.
8. Add test assertions for critical custom snippet values.
9. Run Asciidoctor and verify the full page contains both auto-generated and authored content.
10. Open a pull request requesting review for both contract/snippets and business prose.

### Self-check questions

- From what source does a custom snippet read its data?
- Why can a custom snippet contain hard-coded data without automatically proving it is accurate?
- How does hand-written documentation differ from generated snippets in verification?
- When a URI changes, why is including a snippet safer than copying the URI into multiple prose paragraphs?
- Which content fits `TemplatedSnippet`?
- When should guides be written in AsciiDoc or Markdown?
- What can CI verify, and what can it not conclude on its own?
- How do you combine both approaches without duplicating data?
- Who should review hand-written retry, quota, or authorization policies?

**Key takeaway:** Custom snippets generate structured content from tested operations and suit HTTP data that must stay in sync. Hand-written documentation explains context, business rules, and usage that a single HTTP exchange cannot convey on its own. Combine both: tests and snippets for the observable contract, and owned, sourced prose for authored guidance.

## References

- [Spring REST Docs — Customizing the Output](https://docs.spring.io/spring-restdocs/how-to/customizing-the-output.html): creating custom snippets, templates, and attributes.
- [Spring REST Docs — `TemplatedSnippet` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/snippet/TemplatedSnippet.html): rendering snippets from the operation model.
- [Spring REST Docs — Working with Asciidoctor](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/working-with-asciidoctor.html): including snippets and compiling documentation pages.
- [Spring REST Docs — `Operation` API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/operation/Operation.html): operation data provided to custom snippets.
