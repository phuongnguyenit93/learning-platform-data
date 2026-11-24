# Smoke Testing the UI and Try-It-Out Execution in Appropriate Environments

Swagger UI smoke tests quickly verify that users can open the documentation page, load the right OpenAPI document, see key operations, and send a test request to the API. With springdoc-openapi, this workflow checks the UI, the documentation endpoint, and the runtime API because all three components can behave independently.

A Swagger UI page that loads cleanly does not prove the API is callable. Loading OpenAPI JSON successfully does not prove security, CORS, server URLs, or runtime responses are right. Walk through the full flow from the documentation page to an actual request in an environment with appropriate data and access permissions.

Appropriate environments are typically local, integration, or staging setups configured close to production, with dedicated test accounts and data that can be safely created and deleted. In production, run only approved, safe read-only checks; never use Try it out to arbitrarily create, update, or delete real data.

## 1. What Do Smoke Tests Verify?

Smoke tests are a short suite designed to catch obvious deployment defects before running deeper test suites. For Swagger UI and springdoc-openapi, split them into layers:

| Check Layer | Question to Answer | Example |
|---|---|---|
| Swagger UI page | Does the UI page open? | `/swagger-ui/index.html` returns the page and renders the UI |
| OpenAPI document | Does the UI load the right specification? | `/v3/api-docs` returns valid JSON |
| Operation content | Are target endpoints published? | `GET /api/orders/{id}` is present |
| Security | Does login/Authorize work? | Bearer token is sent in header |
| Try it out | Does the request hit the right API server and return expected results? | `GET` test order returns `200` |
| Contract | Does the runtime response match documented schema and status? | JSON has expected fields and types |

Smoke tests do not replace unit tests, integration tests, contract tests, or performance tests. They simply confirm the basic path from documentation to key API operations works in the target environment.

## 2. Selecting the Environment and Test Data

Before opening Swagger UI, clarify the target environment:

- Swagger UI base URL.
- OpenAPI document or group document URL.
- API server URL in the `servers` field.
- Test account or token.
- Operations permitted to be called.
- Pre-seeded test data or rules for creating and cleaning up data.
- Safeguards for rate limits, emails, payments, messages, or side effects.

Staging environment example:

~~~text
Swagger UI: https://staging.example.com/swagger-ui/index.html
OpenAPI:    https://staging.example.com/v3/api-docs
API server: https://staging-api.example.com
~~~

These addresses are examples only. Use the URLs supplied by your operations team or pipeline; never guess production hostnames from service names.

Maintain a deterministic test dataset, such as a seeded order with ID `smoke-order-001`. When testing write operations, use a run-specific identifier and include a cleanup step. Avoid using personal accounts or real customer data.

### 2.1. Read-Only Checks Only in Production

In production, you may verify the documentation page and OpenAPI document if policy permits. When calling APIs, prefer health endpoints or read-only operations designed for smoke checks.

Never execute `POST`, `PUT`, `PATCH`, or `DELETE` against live data solely to confirm the Try it out button works. If your organization maintains a write-enabled production smoke test procedure, it must use designated test resources, scoped permissions, idempotency keys, and an approved cleanup workflow.

## 3. Verifying Swagger UI and the OpenAPI Document

With default springdoc settings, common URLs are:

| Component | Default Endpoint |
|---|---|
| Swagger UI entry page | `/swagger-ui.html` |
| Swagger UI static entry | `/swagger-ui/index.html` |
| OpenAPI JSON | `/v3/api-docs` |
| OpenAPI YAML | `/v3/api-docs.yaml` |
| Group OpenAPI document | `/v3/api-docs/{group}` |

Projects can override these paths via springdoc configuration or reverse proxies. Always use your application's actual URLs.

Open Swagger UI in a browser and verify:
1. The page does not return `404`, `5xx`, or enter a redirect loop.
2. The Swagger UI interface renders completely.
3. No critical JavaScript errors appear in the Console.
4. The request fetching the OpenAPI document returns a success status.
5. Expected tags and operations appear.
6. No internal URLs, `localhost`, or improper HTTP links appear in API server settings.

If the UI shows `Failed to load API definition`, inspect the `/v3/api-docs` or group document request in the Network tab first. Causes include security blocking the docs endpoint, wrong path, non-OpenAPI-JSON responses, or misconfigured reverse proxy URL rewrites.

## 4. Verifying the OpenAPI Document Independently of the UI

Swagger UI fetches a separate OpenAPI document. Calling that endpoint directly separates UI glitches from specification generation bugs.

Example:

~~~bash
curl -i https://staging.example.com/v3/api-docs
~~~

If the endpoint requires authentication, supply test credentials in the format supported by that environment. Never paste real tokens into docs, shared terminals, or CI logs.

You can save the JSON to a file for inspection:

~~~bash
curl -fsS \
  https://staging.example.com/v3/api-docs \
  -o openapi.json
~~~

With `jq`, run a quick structural check:

~~~bash
jq -e '.openapi and .info.title and .paths and (.paths | length > 0)' openapi.json
~~~

Verify manually or automatically:
- `openapi` carries the expected project version.
- `info.title` and `info.version` are populated.
- Critical paths are present.
- Operations use the right HTTP methods.
- `servers` points to the API server of the environment under test.
- Security schemes and requirements are present on protected operations.
- Request bodies, responses, and schemas are not missing.

When using `GroupedOpenApi`, verify each published group document. For example, `/v3/api-docs/public` and `/v3/api-docs/internal` contain different operation sets; loading the default document does not prove every group works.

## 5. Checking Server URLs Before Clicking Try It Out

Swagger UI combines the URL in `servers` with each operation's path to build requests. Inspect this field before sending requests:

~~~yaml
servers:
  - url: https://staging-api.example.com
    description: Staging API
paths:
  /api/orders/{id}:
    get:
      responses:
        "200":
          description: Order found
~~~

With this configuration, the operation calls:

~~~text
https://staging-api.example.com/api/orders/{id}
~~~

If `servers` points to `http://localhost:8080`, a container hostname, or production while the UI is open in staging, Try it out can send requests to the wrong environment. Never send a request until confirming that the server URL and path combine into the intended target address.

If the document lists multiple servers, pick the right server from Swagger UI's dropdown. Record the selected server in smoke test results to avoid mixing up local, staging, and production.

## 6. Inspecting Operations Before Calling

Expand the target operation and review the displayed details:

- HTTP method and path.
- Summary, description, and tags.
- Path, query, and header parameters.
- Request body and media types.
- Response status codes.
- Response content types and schemas.
- Security requirements.
- Request/response examples if present.

Example get-order operation:

~~~yaml
paths:
  /api/orders/{id}:
    get:
      operationId: getOrderById
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Order found
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/OrderResponse"
        "404":
          description: Order not found
~~~

If `id` is marked `required` yet the UI shows no input, or a request body lacks a schema, fix the OpenAPI document before testing runtime execution. Smoke tests should also confirm key operations have not vanished after changing profiles, groups, or springdoc settings.

## 7. Authorizing with Test Credentials

When operations require authentication, use Swagger UI's Authorize button.

For Bearer authentication, enter the test access token as prompted. Swagger UI attaches the `Authorization` header per the declared security scheme, typically:

~~~http
Authorization: Bearer <test-access-token>
~~~

For OAuth2 Authorization Code, sign in with a test account and confirm the issued token holds the right scopes. When using a public browser client, configure OAuth2 for browser flows; never embed production client secrets in Swagger UI.

After clicking Authorize:
1. Confirm the UI indicates authorized status.
2. Select an operation carrying a security requirement.
3. Click Try it out and Execute.
4. Inspect the Network tab or request curl output to confirm the expected header/credential was sent.
5. Check the live response and server logs if errors occur.

Without a token, you can run controlled negative smoke checks:
- Protected endpoints return `401` when tokens are missing or invalid.
- Endpoints return `403` when a valid token lacks required permissions.
- Public endpoints remain reachable if the contract defines them as public.

Never use overly privileged tokens. Never share tokens in screenshots or reports.

## 8. Running Try It Out in a Safe Sequence

Start with a `GET` operation against known test data. For example:

1. Expand `GET /api/orders/{id}`.
2. Click Try it out.
3. Enter `smoke-order-001` in the path parameter.
4. Confirm the server dropdown is set to staging.
5. Click Execute.
6. Inspect Request URL, curl command, response code, response headers, and response body.
7. Compare returned data against test fixtures and OpenAPI schemas.

Expected outcome:
- HTTP `200`.
- `Content-Type: application/json`.
- Body contains `id`, `status`, and fields documented in `OrderResponse`.
- The `id` value matches the test order.

If the endpoint returns `404`, check the test fixture, tenant, or access permissions before blaming the documentation. If it returns `401`/`403`, check the token and scopes. If the browser reports CORS errors, inspect both the preflight and actual request in Network; the request may have reached the server while the browser blocked JavaScript from reading the response.

### 8.1. Testing Write Operations with Temporary Data

Perform this step only in local, integration, or staging environments where writes are permitted.

Example `POST` creating an order:

~~~json
{
  "customerReference": "swagger-smoke-2026-001",
  "items": [
    {
      "sku": "TEST-SKU-001",
      "quantity": 1
    }
  ]
}
~~~

Before clicking Execute, verify:
- The selected server is a test environment.
- The payload uses test fixtures and test SKUs.
- The operation does not trigger real payments, shipments, or external notifications.
- You have a way to locate and delete the created data.
- An idempotency key is supplied if supported and tests may re-run.

After clicking Execute, verify the contract status such as `201 Created`, valid response body, and `Location` header if advertised. Use `GET` to confirm the created resource, then clean it up per environment procedures.

Never assume Try it out simulates requests locally. Clicking Execute sends a real HTTP request to the selected server.

## 9. Checking Responses Against the Contract

Swagger UI displays responses yet should not be treated as a full JSON Schema validator for every response. Testers must verify live responses against the OpenAPI document or use dedicated contract validation tools.

Core verification points:

| Component | What to Confirm |
|---|---|
| HTTP status | Matches published response code |
| `Content-Type` | Matches response media type |
| Body shape | Object/array and nested structure match |
| Properties | Field names and data types match schema |
| `required` | Required fields are present |
| Nullable | `null` values align with schema |
| Enums/constraints | Values satisfy declared sets/bounds |
| Headers | `Location`, correlation ID, or other published headers appear |
| Error responses | Status and error schema match the error scenario |

Expected response example:

~~~json
{
  "id": "smoke-order-001",
  "status": "CONFIRMED",
  "itemCount": 1
}
~~~

If OpenAPI declares `itemCount` as an integer while runtime returns `"1"` as a string, the UI still renders JSON cleanly. That is a contract violation that must be logged and fixed.

## 10. Testing Intentional Error Cases

A useful smoke test covers at least a few safe error cases, not only happy paths.

| Scenario | Expected Outcome |
|---|---|
| `GET` with existing ID | `200` and matching response schema |
| `GET` with non-existent ID | `404` per contract |
| Protected endpoint without token | `401` |
| Token missing required scope | `403` |
| Payload missing required field | `400` or `422` per API design |
| Invalid enum value | Validation error per contract |
| Unsupported `Content-Type` | `415` if API advertises this behavior |

Run negative tests only against controlled data and environments. Never send oversized loads, huge files, or attack strings into live systems without a dedicated security test plan.

Do not force every API onto a single status code. Check against each service's actual contract—for instance, whether an application uses `400` or `422` for validation errors.

## 11. Checking CORS and Browser Requests

Because Swagger UI runs in a browser, it is subject to Same-Origin Policy and CORS. When the UI and API sit on different origins, the browser must receive appropriate CORS headers.

In the Network tab:
1. Locate any `OPTIONS` preflight request sent by the browser.
2. Check `Access-Control-Allow-Origin`.
3. Check `Access-Control-Allow-Methods`.
4. Check `Access-Control-Allow-Headers`, especially when requests send `Authorization` or `Content-Type`.
5. Check that the actual request response also includes proper CORS headers.
6. When using cookie credentials, verify a specific origin and `Access-Control-Allow-Credentials` match policy.

CORS does not replace authentication or authorization. `curl` and Postman do not enforce browser CORS, so a successful terminal request does not prove Try it out will work. Conversely, browsers may block JavaScript from reading responses even when the server processed the request.

When the UI and API share the same origin, CORS is usually unnecessary for that flow. Never open wildcard origins just to make smoke tests pass.

## 12. Automating Swagger UI Smoke Tests with Playwright

You can automate UI rendering and OpenAPI loading checks with Playwright. The example below assumes the default `/v3/api-docs` endpoint:

~~~typescript
import { test, expect } from "@playwright/test";

test("Swagger UI loads the expected OpenAPI document", async ({ page }) => {
  const docsResponsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url());

    return (
      url.pathname.endsWith("/v3/api-docs") &&
      response.request().method() === "GET"
    );
  });

  await page.goto(process.env.SWAGGER_UI_URL!);

  await expect(page.locator(".swagger-ui")).toBeVisible();

  const docsResponse = await docsResponsePromise;
  expect(docsResponse.ok()).toBeTruthy();

  const spec = await docsResponse.json();

  expect(spec.openapi).toMatch(/^3\./);
  expect(spec.info.title).toBeTruthy();
  expect(Object.keys(spec.paths ?? {}).length).toBeGreaterThan(0);
  expect(spec.paths).toHaveProperty("/api/health");
});
~~~

Set `SWAGGER_UI_URL` in CI to the test environment's URL. Replace `/api/health` with a real path your team wants to verify.

If using a context path, group document URL, or `springdoc.swagger-ui.url` pointing elsewhere, adjust the response matcher accordingly. `.swagger-ui` is Swagger UI's container selector; if upgrading versions or customizing UI themes, verify the selector still matches.

This test checks page loading and spec fetching without clicking Execute on operations. Keep Try it out verification as a controlled manual check or write dedicated API integration/contract tests. Automating UI button clicks couples tightly to DOM structure and breaks easily on Swagger UI upgrades.

## 13. Checking Endpoints via HTTP in CI

Alongside browser smoke tests, CI can quickly verify UI page and OpenAPI document statuses:

~~~bash
curl -fsS -L \
  https://staging.example.com/swagger-ui.html \
  -o swagger-ui.html

curl -fsS \
  https://staging.example.com/v3/api-docs \
  -o openapi.json

jq -e '.openapi and .info.title and (.paths | length > 0)' openapi.json
~~~

When endpoints are protected, supply test credentials from CI's secret store using the appropriate authentication mechanism. Never print access tokens to logs.

Additional checks to layer in:
- Verify critical paths using `jq`.
- Confirm server URLs do not point to production or `localhost`.
- Validate the OpenAPI document with a version-compatible validator.
- Diff against a baseline to catch breaking changes.
- Upload JSON/YAML as build artifacts for reviewer inspection.

HTTP checks alone do not confirm JavaScript UI rendering works. Keep at least one browser smoke test whenever the UI is an important part of the product.

## 14. Recording Smoke Test Results

A concise report should record enough detail for reproduction:

| Field | Example |
|---|---|
| Environment | staging |
| Timestamp / build | build number or commit |
| Swagger UI URL | Tested UI URL |
| OpenAPI version | 3.1.0 |
| Document group | public |
| Operation | `GET /api/orders/{id}` |
| Selected server | staging API |
| Authentication | test user, scope `orders:read` |
| Request fixture | `smoke-order-001` |
| Result | `200`, valid JSON |
| Cleanup | No data created / fixture deleted |
| Issues found | None or short description |

Never include tokens, cookies, passwords, or personal data in reports. If attaching Swagger UI screenshots, redact credentials and sensitive data.

## 15. Common Pitfalls and Fixes

**Swagger UI opens but fails to load the API definition.** Check the document URL in Network, HTTP status, response content type, security rules, and paths behind reverse proxies.

**UI loads the spec but shows no operations.** Check the selected document group, path filters, package scanning, and springdoc settings.

**Try it out calls the wrong environment.** Inspect the server dropdown and OpenAPI `servers` field before clicking Execute.

**Request returns `401`.** Check token expiration, `Bearer` scheme, `Authorization` header, and authentication filters.

**Request returns `403`.** Token may be valid yet lack required roles/scopes, or be blocked by policy.

**Browser reports CORS while `curl` succeeds.** Inspect preflight and actual request CORS headers. `curl` does not enforce browser CORS.

**Response displays yet violates the schema.** Swagger UI is not a full response validator. Use contract tests to enforce types, `required`, enums, and constraints.

**`POST` creates duplicate data on re-runs.** Use dedicated fixtures, idempotency keys where supported, and post-test cleanup.

**Swagger UI lacks Try it out or disables a method.** Check `springdoc.swagger-ui.supportedSubmitMethods`, custom UI settings, and whether the method is declared on the operation.

**Spec loads from an unexpected group.** Check `springdoc.swagger-ui.url`, `springdoc.swagger-ui.urls`, and `/v3/api-docs/{group}`.

**Production tests cause side effects.** Move write checks to staging or sandbox, keeping only approved read-only checks in production.

## 16. Completion Checklist

- [ ] Environment and base URLs confirmed.
- [ ] Dedicated test accounts and test data prepared.
- [ ] Swagger UI opens and renders completely.
- [ ] OpenAPI document loads cleanly.
- [ ] OpenAPI version, title, and version are accurate.
- [ ] Document group contains target operations.
- [ ] `servers` point to the right environment.
- [ ] Parameters, request bodies, responses, and security metadata display accurately.
- [ ] Authorization with test credentials succeeds.
- [ ] A `GET` operation against a fixture returns expected results.
- [ ] Any write test runs only in test environments and cleans up afterward.
- [ ] Status, `Content-Type`, response body, and headers match the contract.
- [ ] CORS is verified in a browser when UI and API have different origins.
- [ ] No tokens or sensitive data appear in reports.
- [ ] Appropriate HTTP/browser smoke tests run in CI.
- [ ] Tested environment, build, and operations are recorded.

## References

- [springdoc-openapi – Getting Started](https://springdoc.org/): OpenAPI endpoints, Swagger UI, and Spring Boot integration settings.
- [Swagger UI – Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/): configuring document URLs, servers, Authorize, and Try it out.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html): describing servers, operations, parameters, request bodies, responses, and security.
- [Playwright – Writing Tests](https://playwright.dev/docs/writing-tests): automating browser UI verification.
- [MDN – Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS): browser CORS and preflight behavior.
