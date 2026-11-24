# API Key in Header, Query, or Cookie

## 1. What is an API key in an OpenAPI contract?

An API key is a value issued by a system to an application or client to identify and control API access. The client sends the key with requests; the backend checks the key, status, usage scope, and related policies before permitting processing.

In OpenAPI, an API key is described using a **Security Scheme Object** of type **apiKey**. This definition states where the key is transmitted and which field name is used:

- **header**: the key is in an HTTP request header.
- **query**: the key is in the URL query string.
- **cookie**: the key is in a request cookie.

OpenAPI places Security Schemes in **components.securitySchemes**. Then, a **Security Requirement Object** specifies which operations require that scheme. Springdoc reads security annotations or the OpenAPI model to generate this section in the documentation.

Two responsibilities must be distinguished:

- OpenAPI describes how clients send credentials.
- Spring Security or the application's security layer actually verifies the API key and decides whether to allow or reject the request.

Declaring **@SecurityScheme** does not automatically generate keys, store keys, or enable key verification in the backend.

## 2. Structure of an API key Security Scheme

An API key scheme has core properties:

| OpenAPI Property | Meaning |
|---|---|
| **type** | Must be **apiKey** |
| **in** | Key transmission location: **header**, **query**, or **cookie** |
| **name** | Name of the header, query parameter, or cookie carrying the key |
| **description** | Instructions on how to obtain and send the key |

OpenAPI YAML example for a key in a header:

~~~yaml
components:
  securitySchemes:
    ApiKeyHeaderAuth:
      type: apiKey
      in: header
      name: X-API-Key
      description: API key issued to the client by the system
security:
  - ApiKeyHeaderAuth: []
~~~

In the example:

- **ApiKeyHeaderAuth** is the scheme name used for referencing.
- **type: apiKey** indicates this is an API key mechanism.
- **in: header** specifies the key is located in a request header.
- **name: X-API-Key** is the header name the client must send.
- **security** at the document level requires operations using this document to apply that scheme, unless an operation has its own overriding security.

The scheme name is an internal identifier in the OpenAPI document. It can differ from the actual header name. For example, the scheme is named ApiKeyHeaderAuth, while the transmitted header is X-API-Key.

## 3. Declaring an API key in a header with annotations

Springdoc supports reading Swagger/OpenAPI annotations. You can declare an API key scheme using **@SecurityScheme**:

~~~java
@Configuration
@SecurityScheme(
    name = "ApiKeyHeaderAuth",
    type = SecuritySchemeType.APIKEY,
    in = SecuritySchemeIn.HEADER,
    paramName = "X-API-Key",
    description = "API key issued by administrator"
)
public class OpenApiSecurityConfiguration {
}
~~~

The annotations and enums in the example belong to the following packages:

~~~java
io.swagger.v3.oas.annotations.security.SecurityScheme
io.swagger.v3.oas.annotations.enums.SecuritySchemeType
io.swagger.v3.oas.annotations.enums.SecuritySchemeIn
~~~

**paramName** in the annotation maps to the name property of the Security Scheme Object. The annotation's name value is the scheme name, while paramName is the header name sent by the client.

After declaring the scheme, the OpenAPI document will contain an equivalent section:

~~~yaml
components:
  securitySchemes:
    ApiKeyHeaderAuth:
      type: apiKey
      in: header
      name: X-API-Key
      description: API key issued by administrator
~~~

This annotation only defines the scheme. To require operations to use the scheme, add a Security Requirement at the document, controller, or operation level.

## 4. Applying a global Security Requirement

You can apply an API key to the entire API using **@OpenAPIDefinition**:

~~~java
@Configuration
@OpenAPIDefinition(
    security = {
        @SecurityRequirement(name = "ApiKeyHeaderAuth")
    }
)
@SecurityScheme(
    name = "ApiKeyHeaderAuth",
    type = SecuritySchemeType.APIKEY,
    in = SecuritySchemeIn.HEADER,
    paramName = "X-API-Key"
)
public class OpenApiSecurityConfiguration {
}
~~~

Then, the OpenAPI document has a Security Requirement at the root level:

~~~yaml
security:
  - ApiKeyHeaderAuth: []
~~~

Operations inherit the global security requirement unless they declare their own security. Swagger UI can display the **Authorize** button for this scheme. Users enter the API key there; Swagger UI uses the supplied value when sending requests to protected operations.

Only apply global security when every operation in the document genuinely requires the key. If there are health checks, login endpoints, or public APIs that do not require a key, exclude them from the security requirement at the operation level.

A Security Requirement only describes the contract requirement. The backend must still verify the key for every request.

## 5. Protecting only one controller or operation

Not every endpoint shares the same access policy. You can place **@SecurityRequirement** at the controller level:

~~~java
@RestController
@RequestMapping("/api/products")
@SecurityRequirement(name = "ApiKeyHeaderAuth")
public class ProductController {

    @GetMapping
    public List<ProductResponse> findAll() {
        return productService.findAll();
    }

    @GetMapping("/{id}")
    public ProductResponse findById(@PathVariable Long id) {
        return productService.getByIdOrThrow(id);
    }
}
~~~

Operations in the controller are documented as requiring the ApiKeyHeaderAuth scheme. Other controllers without this annotation will not automatically inherit the requirement from the controller above.

You can declare security directly on an operation:

~~~java
@GetMapping("/api/reports/summary")
@Operation(
    summary = "View summary report",
    security = {
        @SecurityRequirement(name = "ApiKeyHeaderAuth")
    }
)
public ReportSummary getSummary() {
    return reportService.getSummary();
}
~~~

Declaring at the operation level is useful when only a few endpoints need an API key. Choose a level that matches your security boundaries and inspect the generated document to confirm the Security Requirement sits in the right place.

## 6. Excluding a public endpoint from global security

If a document has a global Security Requirement, a public operation needs to override that requirement with an empty security list.

In OpenAPI YAML:

~~~yaml
paths:
  /api/health:
    get:
      summary: Check service status
      security: []
      responses:
        "200":
          description: Service is operational
~~~

**security: []** on an operation means the operation requires no security scheme, even security inherited from the document root.

This differs from omitting the security property from the operation. If an operation does not declare its own security, it inherits document-level security. To make an operation public, an explicit override must be expressed.

When using annotations, how empty security is represented can depend on how your version of Springdoc and swagger-annotations handles default annotation values. Inspect the final OpenAPI JSON. If you need to ensure security: [], you can use an OperationCustomizer or OpenApiCustomizer to set an empty security list on selected operations.

Do not confuse hiding a scheme from Swagger UI with removing backend protection. If an endpoint is truly public, the security filter chain must also allow that request.

## 7. API key in a query parameter

Some legacy APIs or third-party services require keys in the query string. This can be described using a scheme with **in: query**:

~~~yaml
components:
  securitySchemes:
    ApiKeyQueryAuth:
      type: apiKey
      in: query
      name: api_key
security:
  - ApiKeyQueryAuth: []
~~~

Corresponding annotation:

~~~java
@SecurityScheme(
    name = "ApiKeyQueryAuth",
    type = SecuritySchemeType.APIKEY,
    in = SecuritySchemeIn.QUERY,
    paramName = "api_key",
    description = "API key passed in query parameter"
)
~~~

The client sends a request like:

~~~http
GET /api/products?api_key=CLIENT_KEY
~~~

Do not use real keys in documentation examples. CLIENT_KEY is only a placeholder to illustrate parameter placement.

API keys in queries carry the risk of being recorded in many places:

- Browser history and bookmarks.
- Access logs of web servers, reverse proxies, or API gateways.
- Analytics and monitoring systems.
- Copied or shared URLs.
- Referrer headers in certain navigation flows.
- Caches or logs of intermediary systems.

HTTPS protects data in transit but does not prevent URLs from being saved in logs or browser history. Therefore, when designing new APIs, prefer API keys in headers over query strings.

## 8. API key in a cookie

OpenAPI also allows describing an API key located in a cookie:

~~~yaml
components:
  securitySchemes:
    ApiKeyCookieAuth:
      type: apiKey
      in: cookie
      name: API_SESSION
security:
  - ApiKeyCookieAuth: []
~~~

Corresponding annotation:

~~~java
@SecurityScheme(
    name = "ApiKeyCookieAuth",
    type = SecuritySchemeType.APIKEY,
    in = SecuritySchemeIn.COOKIE,
    paramName = "API_SESSION",
    description = "Session cookie issued by the server"
)
~~~

Browsers can automatically send cookies matching the request's domain, path, expiration, and cookie policy. For authentication cookies, typically consider these attributes:

- **Secure**: send the cookie only over HTTPS.
- **HttpOnly**: prevent JavaScript from reading the cookie.
- **SameSite**: control sending the cookie in cross-site requests.
- **Path** and **Domain**: restrict cookie scope.
- **Max-Age** or **Expires**: control lifetime.

There is an important limitation when testing APIs via Swagger UI: browsers do not allow JavaScript to manually set the Cookie header like a normal header. It is a forbidden request header. Therefore, declaring an in: cookie scheme does not guarantee the Authorize button can automatically inject the cookie into every request.

If the cookie is issued by the server for the matching domain/path and the browser allows sending it in that context, the browser may attach the cookie automatically. If Swagger UI and the API are on different origins, check credential mode, CORS allowCredentials, specific origins, and the browser's SameSite policy. Behavior should be verified using the Network tab in the target browser.

## 9. Comparing header, query, and cookie

| Location | How it is sent | Advantages | Points to note |
|---|---|---|---|
| Header | X-API-Key: ... | Not in URL; suitable for API clients and server-to-server | Must allow header in CORS when cross-origin |
| Query | ?api_key=... | Compatible with some legacy APIs and services requiring URL parameters | Easily appears in URLs, logs, history, and analytics |
| Cookie | Cookie: API_SESSION=... sent by browser | Fits browser session models and server-managed cookies | Requires handling CSRF, SameSite, CORS credentials, and browser limits |

For new APIs, headers are usually the easier option to control. Cookies fit when an application uses browser sessions and has a clear cookie/CSRF protection policy. Queries should only be used when there is a specific compatibility requirement and key exposure risks have been evaluated.

No location replaces secure key management on the backend. Issue separate keys per client, restrict permissions, set expirations when appropriate, and support key revocation and rotation.

## 10. Distinguishing Security Scheme from Parameter Object

An API key may look like a query parameter or header parameter, but if it is used for authentication, it should be described with a Security Scheme.

Example declared as a Parameter Object:

~~~java
@Parameter(
    name = "X-API-Key",
    in = ParameterIn.HEADER,
    required = true,
    description = "API key"
)
~~~

This declaration only states that the operation accepts a header parameter. It does not fully convey security scheme semantics and may not appear in Swagger UI's Authorize area.

For a key used for authentication, declare:

~~~java
@SecurityScheme(
    name = "ApiKeyHeaderAuth",
    type = SecuritySchemeType.APIKEY,
    in = SecuritySchemeIn.HEADER,
    paramName = "X-API-Key"
)
~~~

Then apply **@SecurityRequirement(name = "ApiKeyHeaderAuth")** to the appropriate operations.

Only use a Parameter Object when the value is business input data rather than a credential. For instance, X-Tenant-Id could be a header selecting a tenant under the application contract; if it is not a secret or authentication mechanism, it can be described as a regular parameter.

Do not declare the same API key as both a Security Scheme and a required Parameter Object on the same operation without a special reason. This can cause Swagger UI to generate two input fields or duplicate the header in the documentation.

## 11. Combining multiple Security Schemes: OR and AND

OpenAPI represents multiple security options using a list of Security Requirement Objects. Both combination modes must be clearly understood:

**OR – accept any one of the schemes:**

~~~yaml
security:
  - ApiKeyHeaderAuth: []
  - ApiKeyQueryAuth: []
~~~

The client can use either the header API key or the query API key. Each item in the list is an alternative option.

**AND – require multiple schemes simultaneously:**

~~~yaml
security:
  - ApiKeyHeaderAuth: []
    TenantKeyHeaderAuth: []
~~~

Within a single Security Requirement Object, all listed schemes must be satisfied together. For example, the client must send both the application API key and the tenant identification key.

Do not confuse these two structures. Placing two schemes as two separate list items means OR; placing them as two properties inside the same object means AND.

When combining multiple API keys, consider whether the backend actually validates all credentials under the same rules. OpenAPI only describes the relationship; it does not automatically create combination logic in Spring Security.

## 12. Global and per-operation Security Requirements

OpenAPI allows declaring security at two levels:

| Location | Scope |
|---|---|
| Root security | Applies by default to operations in the document |
| Operation security | Overrides inherited document-level security requirements |

Example of a document with a default API key while the health endpoint is public:

~~~yaml
security:
  - ApiKeyHeaderAuth: []

paths:
  /api/products:
    get:
      summary: Product list
      responses:
        "200":
          description: Success

  /api/health:
    get:
      summary: Health check
      security: []
      responses:
        "200":
          description: Service is operational
~~~

Operation GET /api/products inherits the API key. Operation GET /api/health has security: [] and therefore requires no scheme.

If you simply omit security on the health operation without writing an empty list, it still inherits the global requirement. Open /v3/api-docs to inspect the security field at the root and on the operation.

## 13. Swagger UI Authorize and API keys

When an OpenAPI document has a Security Scheme and Security Requirement, Swagger UI can render an **Authorize** button. For header or query API keys, users enter the key value in the UI; Swagger UI adds the credential to requests when calling protected operations.

A verification workflow:

1. Open Swagger UI.
2. Click Authorize.
3. Enter a test API key issued for the development environment.
4. Confirm the UI displays the authorized state.
5. Call an operation needing the key using Try it out.
6. Open Developer Tools → Network to verify the sent header or query.
7. Call a public operation to confirm the key is not sent outside the expected scope.
8. Click Logout/Authorize again or reload the page as appropriate to clear test credentials.

Do not put real API keys in JavaScript code, OpenAPI files, public examples, or source control. Swagger UI is a client-side interface; anyone with access to the browser can inspect the credentials they entered or the requests sent.

With cookie schemes, test the browser's actual ability to send cookies rather than assuming Authorize can set the Cookie header. Cookies typically need to be set by the server or an appropriate login flow.

## 14. CORS, cookies, and CSRF

When Swagger UI and the API run on different origins, browsers enforce CORS. If a request includes a custom API key header such as X-API-Key, the browser may send an OPTIONS preflight before the actual request.

The backend needs to allow:

- The origin of the Swagger UI page.
- The HTTP methods used.
- The X-API-Key header or corresponding authentication header.
- Credentials if the application genuinely uses cross-origin cookies.
- Exposed response headers if JavaScript needs to read them.

With cookie authentication, CORS must allow credentials and declare specific origins; wildcard origins cannot normally be used with credentials. Cross-site cookies are also affected by SameSite and browser third-party cookie blocking policies.

Cookies sent automatically by browsers can introduce **Cross-Site Request Forgery (CSRF)** risks. If the API uses cookies to authenticate state-changing requests, appropriate CSRF mitigations such as anti-CSRF tokens, Origin/Referer checks, or SameSite policies must be applied according to the application model. Merely declaring in: cookie in OpenAPI does not protect endpoints against CSRF.

## 15. API keys and backend protection principles

An API key is typically a credential carrying access permissions per client or integration. The backend needs verification mechanisms independent of documentation:

- Generate keys with sufficient randomness and entropy.
- Issue separate keys for each application or partner.
- Store securely; consider storing only hashes if the verification process permits.
- Restrict scope, tenant, quota, or allowed API lists.
- Support key revocation and rotation.
- Monitor unusual usage and enforce rate limiting.
- Never log full keys.
- Use HTTPS to protect credentials in transit.
- Do not embed long-lived secrets in public frontend applications.

When using Spring Security, API keys are typically verified in a custom filter or authentication provider depending on architecture. When the key is valid, the application creates an appropriate Authentication; when the key is missing or invalid, it returns a status and error response per API policy.

An OpenAPI Security Scheme only helps clients know how to present credentials. It does not verify keys, grant permissions, or replace the filter chain.

## 16. Common errors when describing API keys

| Symptom | Cause to check |
|---|---|
| Swagger UI has no Authorize button | Security Scheme exists but operations lack a Security Requirement |
| Key entered but request does not send header | Scheme uses wrong in, wrong paramName, or operation does not apply the scheme |
| Backend reports missing key | Header/query/cookie name in docs differs from name read by backend |
| API key appears as a business query parameter | Parameter Object was used instead of Security Scheme |
| Public endpoint still locked in Swagger UI | Operation has not overridden global security with security: [] |
| Every endpoint unexpectedly requires a key | Security Requirement was placed at root while the document has public endpoints |
| Cookie is not sent by browser | Domain, path, Secure, SameSite, credentials, or browser policy mismatch |
| Swagger UI cannot set Cookie header directly | Browsers forbid JavaScript from setting the forbidden Cookie request header |
| API key header request blocked by CORS | Preflight does not permit origin, method, or header |
| Key leaked in logs | API uses query string or logging system does not mask credentials |
| Two schemes produce wrong auth logic | Confused OR across multiple Security Requirement Objects with AND in one object |
| Document has scheme but backend does not validate | Only OpenAPI was declared; runtime verification has not been implemented |

When troubleshooting, check in order: Security Scheme, Security Requirement, request in the Network tab, credential name read by the backend, and runtime authentication outcome.

## 17. Checking the OpenAPI document and real requests

After configuring Springdoc, fetch the document:

~~~http
GET /v3/api-docs
~~~

If the application has document groups, check the corresponding group's endpoint.

For API keys, verify:

1. components.securitySchemes has the required scheme.
2. type is apiKey.
3. in accurately specifies header, query, or cookie.
4. name matches the exact header, query parameter, or cookie name read by the backend.
5. Root security applies to the intended scope.
6. Public operations have security: [] if they need to drop global requirements.
7. Security Requirement OR/AND matches the authentication policy.
8. Swagger UI shows the scheme in Authorize and sends credentials as expected.
9. Requests with a missing key, invalid key, and valid key produce the expected status responses.
10. Logs do not record full credentials.

You can test with MockMvc or integration tests for missing key, invalid key, revoked key, and valid key cases. OpenAPI tests verify the contract; HTTP tests verify the backend enforces security.

Do not use real API keys in test fixtures or logs. Use dummy keys for test environments and clear credentials from Swagger UI after completing checks.

## 18. Principles for choosing an API key location

When designing API keys for Springdoc OpenAPI:

1. Prefer headers for new APIs, such as X-API-Key.
2. Use query only when compatibility with an API or platform requires it.
3. Use cookies when the authentication architecture is cookie-based and has an appropriate CSRF policy.
4. Declare the scheme using @SecurityScheme or the OpenAPI model.
5. Apply using @SecurityRequirement at the proper document, controller, or operation level.
6. Use security: [] for public operations that need to override global security.
7. Distinguish Security Scheme from Parameter Object.
8. Understand OR/AND relationships across multiple security requirements.
9. Do not place real keys in documentation, frontend code, or logs.
10. Inspect OpenAPI JSON, the Swagger UI Network tab, and backend authentication.

API keys in headers, queries, and cookies can all be described with OpenAPI Security Schemes, though each location has distinct characteristics. Headers are usually suitable for API integrations; queries risk exposing credentials in URLs; cookies depend on browser policies and require CSRF handling. When the Security Scheme, Security Requirement, and backend verification mechanism align, Swagger UI can guide clients to send keys properly while the documentation accurately reflects the API's protection scope.

