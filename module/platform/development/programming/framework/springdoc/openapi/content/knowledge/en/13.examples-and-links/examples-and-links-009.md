# External Documentation Links and Conventions for Keeping Examples Free of Secrets

OpenAPI documentation should help integrators understand how to call the API and know where to find deeper guidance. Springdoc lets you attach external documentation links to the specification using `@ExternalDocumentation`; meanwhile, `@ExampleObject`, `@Schema`, and `@Parameter` illustrate requests, responses, and parameter values. Links must be stable, contextual, and point to the right documentation version. Examples must use synthetic data and never contain real tokens, passwords, API keys, or real personal data.

A good documentation link helps readers locate integration guides, error policies, pagination rules, or authentication instructions. A good example helps them send properly formatted data. Both are part of the API contract experience and must be maintained as versioned technical content.

## 1. When are external documentation links needed?

OpenAPI describes the structure and HTTP behavior of an API. However, some content requires longer explanations or evolves independently of schemas:

- Integration quickstarts and client configuration steps.
- Processes for issuing, renewing, and revoking credentials.
- Business rules, order statuses, or resource lifecycles.
- Pagination, filtering, sorting, and rate-limiting conventions.
- Retry, idempotency, and error-handling rules.
- Migration guides between API versions.
- Documentation for webhooks, callbacks, or asynchronous events.

Do not copy entire long guides into an operation's `description`. Keep OpenAPI descriptions concise, focused on the contract, and attach links to detailed explanation pages when readers need additional context.

## 2. `@ExternalDocumentation` at the document level

`@ExternalDocumentation` belongs to package `io.swagger.v3.oas.annotations`. You can declare it inside `@OpenAPIDefinition` to attach a general reference link for the entire API:

```java
package com.example.books.config;

import io.swagger.v3.oas.annotations.ExternalDocumentation;
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Books API",
        version = "1.0.0",
        description = "API for looking up and managing books"
    ),
    externalDocs = @ExternalDocumentation(
        description = "Integration guide and usage rules for the Books API",
        url = "https://docs.example.com/books-api/1.0/guide"
    )
)
public class OpenApiDocumentationConfig {}
```

In the example:

- `description` explains what the target page contains.
- `url` is the full address of the external documentation.
- `@OpenAPIDefinition` places the link at the document level, so it applies to the API as a whole.

The `example.com` domain is purely illustrative. When deploying, replace it with an organization-approved HTTPS URL that has a designated maintainer.

In the OpenAPI specification, this link appears in the root-level `externalDocs` property:

```yaml
openapi: 3.0.3
info:
  title: Books API
  version: 1.0.0
externalDocs:
  description: Integration guide and usage rules for the Books API
  url: https://docs.example.com/books-api/1.0/guide
```

`externalDocs` only generates link metadata. Springdoc does not create that documentation page, does not verify access permissions, and does not guarantee the URL remains live.

## 3. Documentation links at the operation or tag level

Not every guide applies to the entire API. You can attach links at a narrower scope so readers find relevant documentation right on an operation or functional group.

### Linking at an operation using `@Operation`

```java
import io.swagger.v3.oas.annotations.ExternalDocumentation;
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PaymentController {

    @PostMapping("/api/payments")
    @Operation(
        summary = "Create payment request",
        description = "Initialize a payment transaction for an order",
        externalDocs = @ExternalDocumentation(
            description = "Payment flow, idempotency, and status handling",
            url = "https://docs.example.com/payments/1.0/create-payment"
        )
    )
    public PaymentResponse create(@RequestBody PaymentRequest request) {
        // Process payment business logic.
        return new PaymentResponse("pending");
    }
}
```

Operation-level links fit when documentation explains a single action, such as a payment confirmation flow or how to handle a special status.

### Linking at a tag using `@Tag`

```java
import io.swagger.v3.oas.annotations.ExternalDocumentation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
@Tag(
    name = "Orders",
    description = "Query and manage orders",
    externalDocs = @ExternalDocumentation(
        description = "Order lifecycle and statuses",
        url = "https://docs.example.com/orders/1.0/lifecycle"
    )
)
public class OrderController {}
```

Tag-level links fit when multiple operations share a workflow or set of business rules. Tag names should be stable, and the link description should clearly state what the destination page covers.

### Choosing the right scope

| Scope | Declaration location | When to use |
| --- | --- | --- |
| Entire API | `@OpenAPIDefinition(externalDocs = ...)` | There is a shared documentation portal or general guide |
| Group of operations | `@Tag(externalDocs = ...)` | Endpoints in the same domain share a workflow |
| Single operation | `@Operation(externalDocs = ...)` | One action requires dedicated guidance |

Avoid repeating the exact same URL on every operation when a document-level or tag-level link is sufficient. Place links where readers can predict and find them.

## 4. Distinguishing `externalDocs` from other link types

OpenAPI has several structures containing URLs, each serving a different purpose:

| Component | Meaning |
| --- | --- |
| `externalDocs` | Link to additional explanatory documentation about the API, tag, or operation |
| `servers` | Base URLs where clients send HTTP requests |
| `info.termsOfService` | URL to the service terms of use |
| `info.contact` | Support contact information |
| `@Link` / Link Object | Describes navigation from one response to another operation or its input values |
| `@ExampleObject.externalValue` | URL to example content stored externally |

For example, the URL `https://api.example.com` is the server for calling the API; the URL `https://docs.example.com/books/guide` is supplemental documentation. Never use `externalDocs` in place of `servers`, and never use `servers` to point to a guide page.

`@Link` is also different from `@ExternalDocumentation`. A Link Object describes a response-driven navigation relationship between operations, such as from an order-creation result to the view-order operation. It is not merely a URL to a guide page.

## 5. Using `@ExampleObject` for inline examples

Inline examples work well for short, stable payloads that are immediately helpful in Swagger UI. You can declare examples inside `@Content` of a request or response:

```java
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.parameters.RequestBody;

@Operation(
    summary = "Create book",
    requestBody = @RequestBody(
        required = true,
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = CreateBookRequest.class),
            examples = {
                @ExampleObject(
                    name = "BasicBook",
                    summary = "Basic book",
                    description = "Minimal payload to create a book",
                    value = "{\"title\":\"Spring Boot Essentials\",\"publicationYear\":2025}"
                ),
                @ExampleObject(
                    name = "BookWithoutYear",
                    summary = "Book without publication year",
                    value = "{\"title\":\"Practical REST APIs\"}"
                )
            }
        )
    )
)
```

`name` is the example identifier; `summary` and `description` explain the scenario; `value` contains the sample payload. Examples must be valid against the schema and reflect data the API actually accepts.

For parameters, you can use `@Parameter(example = ...)` or `@Parameter(examples = ...)` as needed. For a single DTO field value, use `@Schema(example = ...)`. Pick the right location so examples render alongside the data element the reader is inspecting.

## 6. Using `externalValue` when examples are stored in separate files

If an example is large, spans many lines, or is shared across multiple places, you can host the content at a stable public URL and reference it via `@ExampleObject(externalValue = ...)`:

```java
@Content(
    mediaType = "application/json",
    schema = @Schema(implementation = BulkImportRequest.class),
    examples = @ExampleObject(
        name = "BulkImport",
        summary = "Bulk record import example",
        externalValue = "https://docs.example.com/examples/books/bulk-import-v1.json"
    )
)
```

In OpenAPI, an Example Object can use either `value` or `externalValue`. These two attributes are alternative ways to supply example content; do not declare both for the same example. `externalValue` points to external example content, whereas `value` embeds the payload directly inside the document.

When using `externalValue`, keep in mind:

- The URL must be accessible by tools or readers that need to fetch the example.
- The file must have valid formatting and content matching the declared media type.
- Prefer HTTPS and versioned URLs or immutable paths.
- Some OpenAPI rendering tools may not fetch or display external examples identically; test with Swagger UI and target client tools.
- If an example is small, critical, or needs reliable offline display, inline `value` is usually easier to control.

Never point `externalValue` to a URL requiring an access token, a temporary signed URL, or an address containing secret information in the query string. A public link should never become a vector for leaking credentials.

## 7. Conventions for creating safe example data

Any example in OpenAPI may be copied into tickets, docs, logs, client source code, or test environments. Assume example contents could be shared broadly.

Never put the following types of data into examples:

- Passwords, PINs, security answers, or login credentials.
- Access tokens, refresh tokens, real JWTs, API keys, client secrets, or private keys.
- Session cookies, session IDs, password reset codes, or active verification codes.
- Real personal data such as full names paired with real emails/phone numbers, addresses, dates of birth, or national IDs.
- Real payment data, card numbers, CVVs, bank accounts, or transaction info traceable to users.
- Internal domains, private IPs, environment hostnames, system paths, bucket names, or sensitive resource IDs.
- Log entries or payloads copied from production without sanitization.

Replace them with synthetic data clearly recognizable as an example:

| Case | Value to use in documentation |
| --- | --- |
| Email | `lan.nguyen@example.com` |
| Illustrative domain | `api.example.com` or `docs.example.com` |
| Phone number | Use an obvious placeholder string such as `+84-000-000-000` if the schema only needs to illustrate format |
| Token | `tok_test_example_only` or `<your-access-token>` in prose guides |
| API key | `YOUR_API_KEY` or `REPLACE_WITH_TEST_KEY` |
| User ID | `user_demo_001` |
| Address | Fictional address clearly noted as sample data |
| Payment card | Synthetic sandbox token published by the provider; never use real card numbers outside official test suites |

If you need an example shaped like a token or identifier, use an invalid dummy value and state clearly that it is a placeholder. Never craft a string that looks like a real credential and could mislead readers into thinking it can authenticate.

## 8. Safe examples for authentication headers

Never put real tokens into `@ExampleObject`, `@Parameter(example = ...)`, or `@Schema(example = ...)`. For Bearer authentication, document the authentication method using a security scheme:

```java
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;

@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
```

On operations requiring authentication, use `@SecurityRequirement(name = "bearerAuth")`. Users enter the token for their active environment through Swagger UI's **Authorize** button. The documentation does not need to contain a reusable sample token.

If you want to illustrate HTTP syntax in prose instructions, use a placeholder:

```http
Authorization: Bearer <your-access-token>
```

This is instructional text, not a usable credential. In schemas or JSON examples, you can use the string `YOUR_TEST_TOKEN` if a field simply needs to show format, while noting clearly that clients must substitute a system-issued token.

Never place tokens in query parameters or URLs for illustration. URLs routinely appear in browser histories, proxy logs, analytics, and server logs; credentials in URLs are easily stored or leaked unintentionally.

## 9. Safe examples for personal and payment data

A profile-creation request example can use fictional data:

```json
{
  "displayName": "Lan Nguyen",
  "email": "lan.nguyen@example.com",
  "phone": "+84-000-000-000"
}
```

The email address uses the `example.com` domain reserved for documentation. The phone number is a placeholder and does not represent a real subscriber. If the documentation needs country-accurate formats, pick number ranges officially designated for testing per local regulations or system guidelines.

Payment examples should use synthetic sandbox tokens:

```json
{
  "paymentMethod": {
    "kind": "card",
    "token": "tok_test_example_only",
    "last4": "4242"
  }
}
```

Use only test card numbers provided by the payment gateway in its official sandbox documentation. Never copy card details from a real transaction into examples, even if several digits are masked.

## 10. Managing documentation URLs by version

An API can have multiple versions coexisting. Documentation links should help users know which contract version they are reading:

```text
https://docs.example.com/books-api/1.0/guide
https://docs.example.com/books-api/2.0/guide
```

Useful rules:

1. **Include the version in the path when content depends on the API version.** This lets older clients continue reading the right documentation.
2. **Keep old URLs working during the support window.** If moving pages, use stable redirects and update links in OpenAPI.
3. **Avoid linking to a "latest" page for rules that may change.** A `latest` page works for general overviews, but contract docs should be pinned to a specific version.
4. **Use HTTPS URLs and official domains.** Never point public documentation to internal hostnames or personal environments.
5. **Assign an owner to each link.** Engineering or docs teams should know who updates the page when the API changes.
6. **Verify destination pages on release.** A syntactically valid URL returning 404, requiring internal login, or showing outdated content is still a broken link.

If an API has docs per functional group, you can use dedicated paths like `/orders/1.0/lifecycle` or `/payments/1.0/retries`. Paths should reflect topic and version, without usernames, tokens, session IDs, or secret parameters.

## 11. Including examples and links in OpenAPI YAML

When Springdoc generates the specification, links and examples appear in their corresponding locations. Condensed example:

```yaml
externalDocs:
  description: Books API Integration Guide
  url: https://docs.example.com/books-api/1.0/guide
paths:
  /api/books:
    post:
      summary: Create book
      externalDocs:
        description: Rules for creating and validating book data
        url: https://docs.example.com/books-api/1.0/create
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateBookRequest'
            examples:
              BasicBook:
                summary: Basic book
                value:
                  title: Spring Boot Essentials
                  publicationYear: 2025
```

With an external example, OpenAPI can represent it as:

```yaml
examples:
  BulkImport:
    summary: Bulk record import example
    externalValue: https://docs.example.com/examples/books/bulk-import-v1.json
```

This is an illustrative structure. The real specification may contain additional schemas, responses, tags, security, and other metadata. After changing annotations, inspect `/v3/api-docs` or `/v3/api-docs.yaml` to verify URLs and examples appear in the right positions.

## 12. Checking links and examples before publishing

A syntactically valid URL can still be unusable. Before publishing documentation, check:

- URLs use HTTPS and point to the right official domain.
- Destination pages return appropriate content, not a login or error page.
- Target API consumers have permission to access those pages.
- Destination pages cover the right API, operation, and version.
- Redirects do not lead to URLs containing sensitive data or irrelevant content.
- External examples have valid formatting, match the media type, and require no secret credentials to fetch.
- Inline examples validate against the schema and can be copied to test in a sandbox environment.

For a large documentation set, you can add automated link checks in the documentation pipeline. Checks must handle redirects, transient errors, and authenticated pages appropriately; do not treat every `403` from internal docs as a valid public link.

## 13. Workflow for auditing secrets in examples

Before merging or releasing documentation changes, follow these steps:

1. Search for common sensitive field names such as `password`, `secret`, `token`, `apiKey`, `authorization`, `cookie`, `privateKey`, and `clientSecret`.
2. Inspect the actual values inside each example rather than relying solely on field names. A `reference` or `id` field could also contain a sensitive internal code.
3. Replace production data with synthetic data or inert placeholders.
4. Inspect URLs, headers, cookies, and query strings to make sure they contain no credentials.
5. Inspect `externalValue` files and linked pages; secrets can reside in externally hosted examples.
6. Run a secret scanner if the repository or pipeline has a suitable tool.
7. Ask the API owner to confirm examples accurately reflect the contract and disclose no internal details.

Secret scanners help catch strings shaped like keys or tokens, yet cannot replace reading the content. A synthetic value can resemble a secret; conversely, a real internal code might not match scanner patterns. Combine tooling with manual review.

If a real credential is found to have been committed or published, deleting the string from documentation is not enough. Notify the credential owner to revoke or rotate it following security procedures, and assess where the content was distributed. Never keep copying a credential into another example to "maintain consistency".

## 14. Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Link missing in Swagger UI | `externalDocs` does not appear in OpenAPI or UI renders it in a different spot than expected | Inspect JSON/YAML; open the URL in `externalDocs` directly |
| Documentation URL returns 404 | Page moved or wrong version path | Update URL and keep redirects if needed |
| API consumers cannot access documentation | Page is internal-network only or requires ungranted permissions | Provide an audience-appropriate page or document access requirements clearly |
| External example does not render | Tool does not support fetching `externalValue`, URL blocked, or invalid content | Test with target tools; use inline `value` if stable rendering is required |
| Example does not match schema | Outdated payload or copied from another version | Update example and validate against current schema |
| Token appears in Swagger UI | Credential placed in `value`, `example`, header, or URL | Replace with placeholder; if it is a real credential, revoke/rotate it |
| Example contains personal data | Production payload copied without sanitization | Replace with synthetic data unlinkable to real individuals |
| Documentation points to internal hostname | Development or staging URL used in public metadata | Replace with the official consumer-facing domain |
| `latest` page mismatches older API | Link is not version-pinned | Use versioned documentation URLs and maintain them during support |

## 15. Checklist for safe links and examples

- [ ] `@ExternalDocumentation` is placed at the right scope: document, tag, or operation.
- [ ] Each link has a short description clearly stating what readers will find.
- [ ] URLs use HTTPS, official domains, and stable paths.
- [ ] Documentation is pinned to the right API version and has an owner.
- [ ] `@ExampleObject.value` or `externalValue` reflects a valid payload.
- [ ] `value` and `externalValue` are not declared simultaneously for the same example.
- [ ] Examples contain no real passwords, tokens, API keys, session cookies, or private keys.
- [ ] Personal, payment, and identifier data are all synthetic.
- [ ] Headers, cookies, query strings, and URLs contain no credentials.
- [ ] External example files have also been audited for secrets.
- [ ] URLs and examples have been verified in OpenAPI JSON/YAML and Swagger UI.
- [ ] Content has been reviewed before publishing or releasing.

`@ExternalDocumentation` connects the OpenAPI contract with detailed guides; `@ExampleObject` and `@Schema` illustrate how to use the API. Keep links stable by version and use only synthetic data in examples. That way, documentation remains genuinely helpful to integrators without becoming a place that stores or leaks credentials and sensitive data.
