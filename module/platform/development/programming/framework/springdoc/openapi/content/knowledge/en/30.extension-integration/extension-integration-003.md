# Sharing One Specification While Testing Each UI's Rendering Separately

A Spring Boot application can generate a single OpenAPI document using springdoc-openapi and then serve that document to multiple UIs: Swagger UI, ReDoc, Scalar, or RapiDoc. This approach maintains one unified API contract while each UI provides its own presentation, navigation, schema rendering, authentication handling, and interactive behavior.

However, reading the same OpenAPI file does not mean every UI will render it the same way. One renderer may present `oneOf` well yet make examples hard to find; one UI includes a request-sending button while another is read-only; OAuth redirects might work in Swagger UI yet use the wrong path when placed behind a reverse proxy. Therefore, you should validate the document once at the contract level and test each UI separately at the rendering, interaction, and operational levels.

This guide shows how to establish a shared OpenAPI source from springdoc, connect multiple renderers to that source, compare key differences, and design a test suite to ensure each UI displays what consumers need.

## 1. Separating the Contract Source from the Rendering UI

This architecture has three parts:

1. **The Spring Boot application** registers controllers, DTOs, validation, security, and OpenAPI annotations.
2. **springdoc-openapi** reads the application's mappings and metadata and serves OpenAPI JSON/YAML.
3. **Renderers** fetch the OpenAPI document and present it as a documentation page for users.

Data flow:

~~~mermaid
flowchart TD
    A[Spring Boot controllers, DTO, annotations] --> B[springdoc-openapi]
    B --> C[OpenAPI JSON/YAML]
    C --> D[Swagger UI]
    C --> E[ReDoc]
    C --> F[Scalar]
    C --> G[RapiDoc]
    D --> H[Developer / API consumer]
    E --> H
    F --> H
    G --> H
~~~

A renderer is not a second source of the contract. It reads the document, interprets its contents, and builds a UI. If each UI is configured with a separate manually copied OpenAPI file, those copies can drift over time.

Keeping a single versioned source ensures:

- Every UI displays the same operations, schemas, and security schemes.
- Switching renderers requires no changes to controllers or DTOs.
- A new renderer can be compared against an old one using the exact same document.
- CI can validate OpenAPI content independently of UI checks.
- Portals, static docs, and client generators use the same published contract.

## 2. springdoc Generates the Shared Document

For Spring MVC, the starter that includes Swagger UI is typically **springdoc-openapi-starter-webmvc-ui**. If the application uses WebFlux, choose **springdoc-openapi-starter-webflux-ui**. When only the OpenAPI endpoint is needed to feed another renderer, use the corresponding API starter without packaging Swagger UI.

Basic configuration example:

~~~yaml
springdoc:
  api-docs:
    enabled: true
    path: /v3/api-docs
  swagger-ui:
    enabled: true
    path: /swagger-ui.html
~~~

Default URLs:

| Content | URL |
| --- | --- |
| OpenAPI JSON | /v3/api-docs |
| OpenAPI YAML | /v3/api-docs.yaml |
| Swagger UI | /swagger-ui.html |

If switching to ReDoc or Scalar, keep springdoc to generate the document. You can disable Swagger UI or replace the `-ui` starter with the `-api` starter, depending on which UIs the application serves.

Example enabling only the API document:

~~~yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: false
~~~

Do not disable `springdoc.api-docs.enabled` when a renderer needs to fetch the document from the application. Disabling Swagger UI and disabling the OpenAPI endpoint are two separate things.

## 3. One Document Can Be Read by Multiple Renderers

Suppose the application serves OpenAPI JSON at `/v3/api-docs`. Renderers can reference the same URL:

~~~text
https://api.example.com/v3/api-docs
~~~

| Renderer | Common Way to Receive the Document |
| --- | --- |
| Swagger UI | `url` or `urls` in Swagger UI config |
| ReDoc Community Edition | `spec-url` attribute on the `redoc` element |
| Scalar | `scalar.url` or `scalar.sources` list |
| RapiDoc | `spec-url` attribute on the `rapi-doc` element |

If a renderer is hosted on a different domain from the API, the browser fetches the document via a cross-origin request. Whenever possible, serve the UI and document under the same origin or configure CORS precisely for the documentation source. Do not open wildcard CORS for the entire API just to make the docs page work.

## 4. Differences Between UIs

Renderers have different goals and feature sets. The table below is a starting point for selection and testing, not a guarantee that every version behaves identically.

| Capability | Swagger UI | ReDoc Community Edition | Scalar | RapiDoc |
| --- | --- | --- | --- | --- |
| Presentation style | Operations by tag, direct interaction | Three-column layout, navigation and schemas | Interactive API reference, sidebar and API client | Web component with customizable layout |
| Primary focus | Exploring endpoints and trying requests | Reading descriptions, schemas, and examples | Reading docs and sending requests from API client | Embedding reference into a custom page |
| Sending requests from UI | Built-in Try it out | Community Edition has no built-in Try-it console | Built-in Test Request button | Request testing can be enabled via configuration |
| Authentication | Supports Authorize and OAuth configuration | Displays security schemes; auth testing depends on edition/deployment | API client can use the document's security schemes | Configurable authorize component |
| Deep linking | Supported when `deepLinking` is enabled | Navigates by anchor/section | Deep links to operations and schemas | Link/anchor support depends on version |
| Multiple documents | Supports `urls` and top bar | Can create multiple pages or entries depending on hosting | Built-in `sources` and document switcher | Can switch `spec-url` or configure multiple sources |
| Schema coverage | Depends on Swagger UI version | Displays schemas and composition | Displays schemas alongside examples | Displays schemas per supported OpenAPI features |

A few points to keep in mind:

- Swagger UI fits well when users need to explore operations and test endpoints directly on the page.
- ReDoc Community Edition fits reading documentation, navigation, and inspecting schemas; the Try-it feature in Redocly's hosted product is not implied to exist in Community Edition.
- Scalar provides a built-in API client and multi-source document configuration; ensure source URLs are reachable by the browser.
- RapiDoc is a web component, useful when embedding the reference into a custom-designed page.

Do not pick a renderer based solely on homepage screenshots. Test it with your application's real document, including security, schema composition, examples, and multiple groups.

## 5. Testing the Same Document on Swagger UI

Springdoc integrates Swagger UI via `springdoc-openapi-starter-webmvc-ui` or `springdoc-openapi-starter-webflux-ui`. UI properties use the `springdoc.swagger-ui` prefix.

Example:

~~~yaml
springdoc:
  swagger-ui:
    path: /docs
    deep-linking: true
    display-operation-id: true
    display-request-duration: true
    operations-sorter: alpha
    tags-sorter: alpha
    doc-expansion: none
~~~

The properties above affect how Swagger UI presents the spec:

- `path`: path of the UI page.
- `deep-linking`: enables URL fragments pointing to a tag or operation.
- `display-operation-id`: displays `operationId` to cross-reference contracts and client code.
- `display-request-duration`: displays request duration when using Try it out.
- `operations-sorter` and `tags-sorter`: sort operations/tags.
- `doc-expansion`: initial expansion state of operation groups.

If there are multiple `GroupedOpenApi` beans, you can configure a URL list:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Public API
        url: /v3/api-docs/public
      - name: Admin API
        url: /v3/api-docs/admin
    urls-primary-name: Public API
~~~

Only add this list when you need explicit control over which documents users can select. If springdoc's automatic group configuration already meets your needs, there is no need to redeclare the URLs.

Checks on Swagger UI:

1. The docs page loads configuration and the OpenAPI document.
2. Tags and operations are ordered for easy discovery.
3. `operationId` is not blank if the team requires displaying it.
4. Request body, parameter, and response examples render accurately.
5. Authorize recognizes the right schemes.
6. Try it out sends requests to the right server.
7. Deep links still open the right operation after reloading or sharing the URL.

## 6. Testing the Same Document on ReDoc

ReDoc Community Edition can be embedded with an HTML element and the OpenAPI document URL:

~~~html
<!doctype html>
<html lang="vi">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Order API</title>
  </head>
  <body>
    <redoc spec-url="/v3/api-docs"></redoc>
    <script type="module" src="/assets/redoc.standalone.js"></script>
  </body>
</html>
~~~

The example uses a bundled asset at `/assets/redoc.standalone.js`. Install a specific ReDoc version, copy the bundle into the application's static directory or host the asset on the same domain; if using a CDN, pin the version instead of using a floating URL. Verify Content Security Policy, caching, and asset loading from users' browsers.

ReDoc Community Edition presents the document in a three-column layout: navigation, content, and schema/example panel. When testing:

- Are long operation descriptions readable and do they preserve headings/lists?
- Are nested schemas navigable?
- Do `oneOf`, `anyOf`, `allOf`, and `discriminator` help readers understand variants?
- Are request/response examples displayed alongside schemas properly?
- Can tags, operations, and models be found via search?
- Does long content work on narrow viewports?

Do not expect a Swagger UI-style Try it out button in ReDoc Community Edition. If a business requirement is sending requests from the docs, choose a renderer with a built-in API client or use a product edition that includes that feature.

You can generate a static HTML page from an OpenAPI file using Redocly CLI:

~~~bash
npx @redocly/cli build-docs openapi.yaml
~~~

The command produces a static documentation page for hosting on a web server or artifact storage. When a document has `$ref` pointers to external files, bundle the referenced files before distributing a standalone file.

## 7. Testing the Same Document on Scalar

Scalar has its own Spring Boot integration. For Spring MVC, you can use `scalar-webmvc`; for WebFlux, use `scalar-webflux`. springdoc remains the component generating the OpenAPI document.

Configuration example:

~~~yaml
scalar:
  enabled: true
  url: /v3/api-docs
  path: /scalar
  page-title: Spring Shop API Reference
~~~

When the application runs, the Scalar UI is typically served at `/scalar`. Check the integration documentation for the exact Scalar and Spring Boot versions in use; Java integration releases may change modules, properties, and runtime requirements. Current Scalar Java integration documentation describes support for Spring Boot 3.x, so do not assume a given starter works with Spring Boot 4.x without verifying that release's compatibility matrix.

If there are multiple groups, declare separate sources:

~~~yaml
scalar:
  enabled: true
  sources:
    - url: /v3/api-docs/public
      title: Public API
      slug: public
      is-default: true
    - url: /v3/api-docs/admin
      title: Admin API
      slug: admin
~~~

Scalar can display an API client and a Test Request button for operations. Check:

- Can the document source be fetched from the browser?
- Does the document switcher select the right default group?
- Is the right server selected, especially when the app runs behind a gateway?
- Are request bodies and parameters populated properly into the API client?
- Are Bearer/API key/OAuth schemes recognized?
- Are tokens absent from public HTML or JavaScript?
- Do test responses display status, headers, and body?

Never put tokens, client secrets, or passwords in properties sent to the browser. Those values can be viewed by users via DevTools, source maps, or network requests. To protect the Scalar page, use Spring Security to control the UI route and documentation endpoints.

## 8. RapiDoc as Another Web Component

RapiDoc can be embedded in an HTML page using the `rapi-doc` element:

~~~html
<rapi-doc
  spec-url="/v3/api-docs"
  render-style="read"
  show-header="true">
</rapi-doc>
<script type="module" src="/assets/rapidoc-min.js"></script>
~~~

The snippet above illustrates passing the document to the web component. Verify supported attribute names and values against the RapiDoc version pinned in the project. Do not use unpinned CDN URLs in production if UI reproducibility is required.

RapiDoc supports different OpenAPI versions per release. When using OpenAPI 3.1 or newer features such as webhooks, verify the compatibility matrix of the exact packaged RapiDoc version.

## 9. An OpenAPI Contract Must Contain Enough Information for Renderers to Display

A renderer cannot display information not described in the document. For example, if a controller only declares a response DTO without describing response codes, examples, or security, the UI cannot infer the missing business semantics on its own.

Abbreviated OpenAPI example:

~~~yaml
openapi: 3.0.3
info:
  title: Payment API
  version: 1.0.0
paths:
  /payments:
    post:
      operationId: createPayment
      tags:
        - Payments
      summary: Create payment
      description: |
        Creates a payment request for an order.

        Send only once with the same idempotency key.
      security:
        - bearerAuth: []
      parameters:
        - name: Idempotency-Key
          in: header
          required: true
          schema:
            type: string
          example: pay-req-10001
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/PaymentRequest'
            examples:
              card:
                summary: Card payment
                value:
                  orderId: ORD-10001
                  method: card
                  cardToken: tok_example
      responses:
        '201':
          description: Payment request created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/PaymentResponse'
              example:
                paymentId: PAY-10001
                status: PENDING
        '409':
          description: Idempotency key was already used with a different payload
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
  schemas:
    PaymentRequest:
      oneOf:
        - $ref: '#/components/schemas/CardPaymentRequest'
        - $ref: '#/components/schemas/BankPaymentRequest'
      discriminator:
        propertyName: method
        mapping:
          card: '#/components/schemas/CardPaymentRequest'
          bank: '#/components/schemas/BankPaymentRequest'
    CardPaymentRequest:
      type: object
      required: [orderId, method, cardToken]
      properties:
        orderId:
          type: string
        method:
          type: string
          enum: [card]
        cardToken:
          type: string
    BankPaymentRequest:
      type: object
      required: [orderId, method, bankCode]
      properties:
        orderId:
          type: string
        method:
          type: string
          enum: [bank]
        bankCode:
          type: string
    PaymentResponse:
      type: object
      required: [paymentId, status]
      properties:
        paymentId:
          type: string
        status:
          type: string
          enum: [PENDING, PAID, FAILED]
~~~

This is an illustrative contract example, not a complete controller. In an application, springdoc can generate most of the document from `@Operation`, `@Parameter`, `@RequestBody`, `@ApiResponse`, `@Schema`, and DTOs; complex examples or discriminators may require annotations or customizers.

When testing the same document across multiple UIs, compare these points:

- Is `operationId` visible and deep-linkable?
- Does Markdown in `description` preserve paragraphs, lists, and code?
- Is the `Idempotency-Key` header presented as required?
- Are the two `oneOf` branches distinguished by the discriminator?
- Can request examples be viewed and copied?
- Is the security scheme displayed accurately as HTTP bearer?
- Can responses `201` and `409` be inspected individually?

## 10. Checking oneOf, anyOf, allOf, and discriminator

Schema composition is where renderers most easily produce very different experiences:

- `oneOf`: data must match exactly one schema in the list.
- `anyOf`: data may match one or more schemas.
- `allOf`: data combines the constituent schemas.
- `discriminator`: indicates the field used to select a concrete schema among variants.

Do not just check whether a renderer prints the schema names. Verify that readers can understand:

1. Which fields differ across variants.
2. Which values the discriminator field takes.
3. Which fields are required in each variant.
4. Which example corresponds to which schema.
5. Whether `$ref` links open the target schema.

If a UI only lists schemas without making the discriminator mapping clear, add intentional descriptions and examples. Do not simplify the contract into a flatter schema just to please one renderer if doing so loses data semantics.

## 11. Checking Examples and Descriptions

OpenAPI allows placing examples at multiple levels: schema, parameter, media type, or request/response content. Renderers may prioritize and display those levels differently.

Include:

- Valid examples for common requests.
- Examples for each `oneOf` branch or polymorphic type.
- Success response examples.
- Error response body examples if the API returns an error schema.
- Descriptions explaining units, timezones, formats, and business conditions.
- Synthetic data in examples, never real tokens, emails, card numbers, or customer data.

If Swagger UI shows a different example than ReDoc, inspect where `example`/`examples` sit in the document before tweaking the UI. A renderer cannot unify an example if the contract holds multiple examples and each UI chooses a different presentation rule.

## 12. Checking Security and OAuth Separately per UI

OpenAPI describes security schemes and operation requirements. Renderers read that information to show how to authenticate, but a renderer does not replace Spring Security or an authorization server.

Common schemes:

| Scheme | Information in OpenAPI |
| --- | --- |
| Bearer JWT | `type: http`, `scheme: bearer`, `bearerFormat: JWT` |
| API key | `type: apiKey`, `name`, `in: header/query/cookie` |
| Basic | `type: http`, `scheme: basic` |
| OAuth2 | `type: oauth2`, flows and scopes |
| OpenID Connect | `type: openIdConnect`, discovery URL |

Check on each UI:

- The scheme is recognized as the right type.
- Scopes and OAuth flows display accurately.
- Authorization URL, token URL, and redirect URI use the right public host.
- Bearer tokens are stored only within the browser session per renderer behavior.
- The Authorize button does not mislead users into thinking documentation itself secures the API.
- Test endpoints are still authenticated and authorized by the server like normal requests.

Do not add a global security requirement when public endpoints exist. A renderer may prominently display an Authorize button, but that does not mean every operation requires a token.

Never embed client secrets in JavaScript or public configuration. For OAuth Authorization Code, use PKCE when the client is a public browser app and configure the exact redirect URI on the authorization server.

## 13. Checking Server URLs and Reverse Proxies

The Try it out or Test Request button sends requests to URLs in `servers`. If springdoc infers an internal host from a proxied request, some renderers may call the wrong address.

For example, the document contains:

~~~yaml
servers:
  - url: https://api.example.com
    description: Public API
~~~

Verify:

- Is the server URL the public base URL?
- Is the context path duplicated?
- Does HTTP/HTTPS match the environment?
- Does an internal port accidentally appear in the document?
- Does the proxy pass forwarded headers properly?
- Can the browser reach that host from the user's network?

If using the same document across staging and production, consider generating an appropriate server list or publishing separate documents per environment. Never let a production document point to a staging hostname.

## 14. CORS and Document Access Permissions

If the docs page and the OpenAPI endpoint are on different origins, the browser must be permitted to read the documentation endpoint's response. CORS only allows the browser to read the response; it neither authenticates users nor protects OpenAPI content from authorized callers.

Verify:

- `GET /v3/api-docs` or the group URL returns 200 from the renderer's origin.
- Preflight is handled if requests include required headers.
- Security filters do not return an HTML login page instead of JSON.
- CORS allows only trusted docs origins.
- External `$ref` targets are also permitted or bundled.
- CSP permits the script/style/connect sources required by the renderer.

If the API contract contains internal endpoints or sensitive details, control access on the server and wherever documentation is hosted. Disabling Swagger UI does not automatically disable the OpenAPI JSON endpoint.

## 15. Keeping the Same Contract Version Across All UIs

In development, renderers can read `/v3/api-docs` directly. In release environments, consider storing the OpenAPI document as a versioned artifact:

~~~text
artifacts/
  openapi/
    1.4.0/
      openapi.json
      openapi.yaml
~~~

Workflow:

1. Build the application and generate the OpenAPI document.
2. Validate the document.
3. Store the artifact tagged with the version or commit.
4. Publish the artifact to an accessible location.
5. Configure each renderer to point to the same artifact.
6. On a new release, update all renderers together.

Do not let Swagger UI read the document from a new commit while ReDoc still reads an old file on a CDN. If caching is present, use versioned URLs or an appropriate ETag/cache policy to detect stale documents.

## 16. Verifying Renderers Do Not Misrepresent OpenAPI Semantics

A UI may ignore or render certain elements differently:

| OpenAPI Element | What to Observe |
| --- | --- |
| `operationId` | Is it shown, used as a deep link, or used in code samples? |
| `deprecated` | Is there a warning indicator for deprecated operations? |
| `tags` | Are operations grouped properly and in the expected order? |
| `externalDocs` | Does the link appear and open the right target? |
| `callbacks` | Are callback contracts displayed if the renderer supports them? |
| `webhooks` | Is the webhook structure displayed accurately? |
| `links` | Can relationships between responses and follow-up operations be inspected? |
| `x-*` extensions | Are important extensions supported by the renderer? |
| `multipart/form-data` | Are file fields and regular fields easy to understand? |
| Binary response | Are media types and downloadable payloads described accurately? |
| `readOnly`/`writeOnly` | Is the distinction between request and response fields clear? |

Do not assume every renderer supports every part of OpenAPI equally. Document the contract features your application actually uses, then cross-check the release notes or feature matrix of your pinned renderer.

## 17. Testing UIs Across Desktop, Tablet, and Mobile

A document can be valid yet still produce a hard-to-use UI:

- Long schema names overflow the sidebar.
- Parameter tables are too wide on mobile.
- Code blocks cannot scroll horizontally.
- Multi-level headings in descriptions clutter navigation.
- Model expansion opens too much content.
- Authorize or Try it out buttons are clipped on small screens.
- Contrast on tags, badges, or deprecated states is insufficient.

Test at least three viewport sizes: desktop, tablet, and mobile. Use the keyboard to navigate through navigation items, operations, parameters, and interactive buttons. Check focus states, heading hierarchy, and accessible names of controls.

## 18. Designing a Two-Layer Test Suite

Do not rely on a single screenshot as proof. Split tests into two layers:

**Layer A — contract/document**

- OpenAPI JSON/YAML parses cleanly.
- OpenAPI version is right.
- Required paths and HTTP methods exist.
- Schemas, `$ref`, examples, and security requirements are complete.
- No unintended internal endpoints exist.
- Contract diff has no unapproved breaking changes.

**Layer B — renderer/UI**

- The renderer page loads successfully.
- The browser fetches the right document version.
- No critical JavaScript or network errors occur.
- Tags, operations, models, and examples can be located.
- Auth and server selectors work.
- Deep links open the right operation.
- Layout, accessibility, and responsive behavior meet requirements.

A green contract test does not prove the renderer displays properly. Likewise, a renderer page loading does not prove the contract is valid or real requests succeed.

## 19. Smoke-Testing the Document Endpoints

Verify the document from the application:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  --output openapi.json

curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs.yaml \
  --output openapi.yaml
~~~

Check that the JSON has a version and paths:

~~~bash
jq -e '.openapi and (.paths | length > 0)' openapi.json
~~~

If using multiple groups:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs/public \
  --output openapi-public.json
~~~

Verify every URL used by any renderer, not only the default document URL. If the UI loads the page yet the document returns 401, 403, 404, or an HTML login page, the rendered content may be blank or show a parse error.

## 20. Smoke-Testing in the Browser

For each renderer, check a representative set of operations:

1. An operation with path parameters and query parameters.
2. An operation with a request body and multiple content types.
3. An operation with success and error responses.
4. An operation with schema composition such as `oneOf`.
5. An operation with a security requirement.
6. An operation with long examples or multi-paragraph descriptions.
7. An operation belonging to a separate group.

You can use Playwright or your project's browser automation tool to:

- Open the UI page.
- Wait for the document to finish loading.
- Verify the API title or key operations appear.
- Open a deep link.
- Verify no document requests failed.
- Capture screenshots at fixed viewports to compare when upgrading the renderer.

Do not tie tests to volatile internal CSS classes of a renderer. Prefer visible text, accessible roles/names, URLs, network responses, and actual user behaviors.

## 21. Test Matrix for Multiple UIs

Example release test matrix:

| Item | Swagger UI | ReDoc | Scalar | RapiDoc |
| --- | --- | --- | --- | --- |
| Loads the right OpenAPI artifact | Required | Required | Required | Required |
| Displays key operations | Required | Required | Required | Required |
| Schema composition | Required if used by contract | Required if used by contract | Required if used by contract | Required if used by contract |
| Request/response examples | Required | Required | Required | Required |
| Authorize/OAuth | Test as needed | Check rendering and features of edition used | Test API client if used | Test if interaction enabled |
| Sending requests | Test Try it out | Not applicable for Community Edition | Test Test Request | Test if enabled |
| Deep linking | Test when enabled | Test anchor/navigation | Test operation/schema links | Test links per version |
| Responsive/accessibility | Required | Required | Required | Required |
| Security/CORS | Required | Required | Required | Required |

Do not mark a feature "not applicable" and skip a product requirement. If users must be able to test requests from the documentation, choose a renderer that supports that requirement or add a dedicated API client.

## 22. Common Errors When Using Multiple Renderers

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| One UI is missing an operation | UI is reading the wrong group or a stale document | Check URL, artifact version, and cache |
| Swagger UI works but ReDoc lacks Try it | ReDoc Community Edition has no built-in Try-it console | Choose a renderer with an API client or a product edition with that feature |
| `oneOf` schema is hard to follow | Missing discriminator, description, or examples | Add contract metadata and check each renderer |
| OAuth works in one UI but not another | Redirect URL, PKCE, or OAuth config differs | Check redirect allowlist and per-renderer config |
| Request button calls the wrong host | Wrong `servers` or forwarded headers | Fix public server URL and proxy configuration |
| UI is blank even though page returns 200 | Document blocked, wrong content type, or HTML login returned | Inspect browser network responses |
| Group missing from top bar | UI has no configured URL/source list | Configure group URLs for the renderer |
| Examples differ across UIs | Renderers pick different `example`/`examples` levels | Standardize example placement and content |
| Some schemas fail to render | Renderer version lacks feature support or `$ref` fails to resolve | Pin/upgrade renderer, bundle refs, and check support matrix |
| Works locally but fails in production | CORS, CSP, context path, proxy, or CDN cache | Inspect network/security policies on the real domain |
| UI leaks internal API info | Document exposed too broadly or docs route unprotected | Restrict packages/paths and protect docs endpoints |

## 23. Release Workflow with Multiple UIs

1. Generate the OpenAPI document from the exact source code and profile being released.
2. Validate the document and run contract diff.
3. Verify required paths, schemas, security, and examples.
4. Store the artifact with a clear version or commit.
5. Configure Swagger UI, ReDoc, Scalar, or RapiDoc to use the same artifact.
6. Run separate smoke tests for each supported renderer.
7. Check OAuth, server URLs, CORS, and access control on staging.
8. Check desktop/mobile layouts and accessibility.
9. Publish the document and UIs as part of the same release.
10. Record renderer versions, artifact version, and test results so future upgrades can be compared.

When upgrading a renderer, keep the OpenAPI artifact fixed during the first test run. When updating the contract, keep the renderer version fixed during the first test run. Separating these two changes helps identify whether a failure comes from the document or the UI.

## 24. Review Checklist

- [ ] `springdoc` is the single source generating the OpenAPI document.
- [ ] Each renderer points to the right JSON/YAML URL or artifact version.
- [ ] The default document and all groups are tested.
- [ ] Swagger UI, ReDoc, Scalar, or RapiDoc versions are pinned.
- [ ] `operationId`, tags, and deep links are meaningful and stable.
- [ ] Schema composition, discriminators, and `$ref` render accurately.
- [ ] Request/response examples are easy to find and contain no real data.
- [ ] Security schemes and OAuth flows display accurately.
- [ ] Server URLs and proxy prefixes point to public endpoints.
- [ ] CORS, CSP, and Spring Security permit the document loading flow properly.
- [ ] API client/Try it out is tested only on renderers that support it.
- [ ] Responsive layout, keyboard navigation, and contrast are verified.
- [ ] CI runs separate contract validation and browser smoke tests.
- [ ] All UIs use the same contract version on release.

A shared OpenAPI document frees teams from maintaining multiple copies of a contract. Yet user experience quality depends on each specific renderer and how it handles every part of the document. Validate the contract once at the data level, then test each UI separately at the rendering, interaction, security, and responsive-behavior levels.

## References

- [springdoc-openapi – Documentation](https://springdoc.org/)
- [springdoc-openapi – Configuration Properties](https://springdoc.org/properties.html)
- [Swagger UI – Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/)
- [Swagger UI – Deep Linking](https://swagger.io/docs/open-source-tools/swagger-ui/usage/deep-linking/)
- [ReDoc – OpenAPI-generated API Reference](https://github.com/Redocly/redoc)
- [Redocly CLI – build-docs](https://redocly.com/docs/cli/commands/build-docs)
- [Scalar – Spring Boot Integration](https://scalar.com/docs-for/spring-boot)
- [Scalar – Java Integration](https://scalar.com/products/api-references/integrations/java)
- [RapiDoc – OpenAPI Support](https://rapidocui.com/docs/get-started/openapi-support/)
