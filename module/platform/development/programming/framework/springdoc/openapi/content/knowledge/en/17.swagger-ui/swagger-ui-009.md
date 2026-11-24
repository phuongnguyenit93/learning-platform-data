# Displaying Requests, cURL, Responses, and Response Time

After a user selects **Try it out** and clicks **Execute**, Swagger UI sends an HTTP request to the server selected in the OpenAPI document. The displayed output helps inspect how the request was constructed, which status the server returned, what the response contains, and how long the request took from the browser's perspective.

These sections are especially helpful during API integration: you can cross-check the request URL and cURL command against the contract, inspect actual headers and bodies, examine server errors, and reproduce requests using a command-line tool. The response time shown in the UI is client-side observed duration; it does not isolate internal server processing time on its own.

## 1. What appears after Execute

When an operation is executed in Swagger UI, the interface typically shows the following information:

| Displayed section | Content | Question answered |
|---|---|---|
| Request URL | Full URL called, including server, path, and query string | Which host and endpoint did the request go to? |
| cURL | Equivalent command to reproduce the request | Can the request be re-run from a terminal? |
| Server response | HTTP status code and response details | Did the server accept or reject the request? |
| Response body | Returned payload according to media type | Does the actual data match the schema? |
| Response headers | Headers sent back by the server | What are Content-Type, cache, request ID, or other metadata? |
| Response time | Request completion time measured by the UI | How long did the client wait? |

Section names and layout may vary slightly across Swagger UI versions. The core content remains the sent request and the response received by the browser.

## 2. Request URL shows the exact call target

The Request URL is built from the server URL in OpenAPI, the operation path, and parameters entered by the user. Operation example:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping("/orders/{orderId}")
OrderResponse getOrder(
        @PathVariable("orderId") String orderId,
        @RequestParam(name = "includeItems", defaultValue = "false")
        boolean includeItems) {
    // ...
}
~~~

If the selected server is <code>http://localhost:8080/api</code>, the user enters <code>orderId = ORD-100</code>, and enables <code>includeItems</code>, the request URL can be:

~~~text
http://localhost:8080/api/orders/ORD-100?includeItems=true
~~~

When inspecting the URL, cross-check:

- Whether the scheme is <code>http</code> or <code>https</code>.
- Whether host and port match the target environment being tested.
- Whether context path or gateway prefix is missing or duplicated.
- Whether path variables were substituted with the entered values.
- Whether query parameters have the right names and values.
- Whether values with special characters are properly URL-encoded.

If the URL is wrong, inspect the server list in OpenAPI, <code>servers</code> configuration, context path, reverse proxy, and the server URL selected in Swagger UI. Do not jump to concluding a controller has a bug before confirming the request reached the right application.

## 3. cURL is a reproduction of the request

Swagger UI typically provides a cURL command based on the selected operation, server, parameters, request body, and authentication details. Example:

~~~bash
curl -X 'GET' \
  'http://localhost:8080/api/orders/ORD-100?includeItems=true' \
  -H 'accept: application/json' \
  -H 'Authorization: Bearer <access-token>'
~~~

This command sends a GET request to the endpoint, requests a JSON response, and attaches a Bearer token. For requests with a body, cURL may additionally include content type and data:

~~~bash
curl -X 'POST' \
  'http://localhost:8080/api/orders' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "productCode": "SKU-100",
    "quantity": 2
  }'
~~~

You can copy the command from Swagger UI and run it in a terminal to reproduce the request without opening the UI. When using tokens, replace placeholders with valid test tokens and avoid saving real tokens in scripts, shared terminal history, or documentation.

### 3.1. cURL is not necessarily a byte-for-byte browser log

The cURL command is generated from OpenAPI metadata and Swagger UI's interactive state. It is useful for reproducing the method, URL, declared headers, and request body, though it does not necessarily include every header added automatically by the browser, proxy, or cookies. For example, the real request may carry <code>Origin</code>, <code>User-Agent</code>, cookies, or CORS-related headers not fully shown in the displayed cURL snippet.

Therefore, when investigating a failing request precisely, also inspect the browser's Network tab or server-side logs. Use cURL to reproduce and narrow down the issue, then compare with the actual browser request if discrepancies occur.

### 3.2. Running cURL on Windows

On Windows PowerShell, the name <code>curl</code> may be mapped as an alias to <code>Invoke-WebRequest</code> depending on version and setup. To run the cURL syntax generated by Swagger UI, use the <code>curl.exe</code> executable when installed. You may need to adjust quotes or line continuations for your shell.

## 4. Reading HTTP status in Server response

The status code indicates the outcome at the HTTP level. Common groups:

| Group | Meaning | Examples |
|---|---|---|
| 2xx | Request processed successfully | <code>200 OK</code>, <code>201 Created</code>, <code>204 No Content</code> |
| 3xx | Redirection required or redirect status | <code>301</code>, <code>302</code>, <code>304</code> |
| 4xx | Request has an issue or is not permitted | <code>400</code>, <code>401</code>, <code>403</code>, <code>404</code>, <code>409</code> |
| 5xx | Server or intermediary encountered an error | <code>500</code>, <code>502</code>, <code>503</code>, <code>504</code> |

Do not look only at the color or status number. Cross-check the actual status with the responses declared in OpenAPI:

- <code>200</code>: read the response body and verify the data.
- <code>201</code>: verify the newly created resource and returned identifier.
- <code>204</code>: no response body; verify status and headers.
- <code>400</code>: read validation details or request syntax errors.
- <code>401</code>: check the token or authentication credentials.
- <code>403</code>: request is authenticated but lacks permissions, depending on server policy.
- <code>404</code>: check path, ID, and resource existence.
- <code>409</code>: check business conflict or data state.
- <code>5xx</code>: check server logs, gateway logs, and correlation/request IDs if available.

Swagger UI displays the status returned by the endpoint or an intermediary. The interface does not diagnose the business cause of an error on its own; inspect the response body and correlate with logs.

## 5. Reading Response body and Content-Type

The response body is the actual data returned by the server. Success example:

~~~json
{
  "orderId": "ORD-100",
  "status": "CONFIRMED",
  "total": 259900.00,
  "items": []
}
~~~

Cross-check the body against the OpenAPI schema:

- Are required fields present?
- Do data types (number, string, boolean, array, or object) match the schema?
- Do field names, enums, formats, and nested structures match?
- Do null values or omitted fields follow the contract convention?

The <code>Content-Type</code> header indicates the body format, such as <code>application/json</code>. If an operation returns a file, plain text, or another format, the displayed content may differ from JSON formatting.

For a <code>204 No Content</code> response, an empty body is correct behavior. Do not treat an empty Response body area as an error if the status and contract state that the operation returns no content.

If the server returns HTML of a proxy error page while OpenAPI describes JSON, the request may have been blocked or failed at the gateway before reaching the controller. Check Content-Type, status, and intermediary logs.

## 6. Reading Response headers

Response headers provide metadata to the client. Useful headers include:

| Header | Role |
|---|---|
| <code>Content-Type</code> | Response body format |
| <code>Content-Length</code> | Body size if provided |
| <code>Cache-Control</code> | Caching rules |
| <code>ETag</code> | Identifier for the resource representation version |
| <code>Location</code> | URL of a new resource or redirect target, common in creation responses |
| <code>Retry-After</code> | Suggested wait time before retrying |
| <code>X-Request-Id</code> | ID for looking up logs if issued by the system |

Not every header appears in every response. Some headers are added by a gateway or web server; others are explicitly returned by the application.

When Swagger UI runs on a different origin from the API, browser JavaScript can only read response headers exposed by CORS. If a custom header such as <code>X-Request-Id</code> is present in the response yet invisible in the UI, check the server's <code>Access-Control-Expose-Headers</code> setting. That does not necessarily mean the header was absent on the wire; inspect the Network tab to confirm.

## 7. Displaying response duration

Swagger UI has the <code>displayRequestDuration</code> option to show request duration. With springdoc-openapi, it can be enabled in <code>application.yml</code>:

~~~yaml
springdoc:
  swagger-ui:
    displayRequestDuration: true
~~~

After restarting or reloading application config, execute an operation using Try it out. The UI displays the request duration alongside response info according to the Swagger UI version's layout.

To configure via properties:

~~~properties
springdoc.swagger-ui.displayRequestDuration=true
~~~

This time is a UI/client-side measurement covering sending the request and receiving the response. It may include:

- Time for the browser to prepare and dispatch the request.
- Network latency between browser, proxy/gateway, and server.
- Processing time in intermediary components.
- Server processing and response generation time.
- Time to receive response data back at the browser.

Therefore, do not equate this number with CPU time or internal controller processing time. When server performance analysis is needed, combine backend metrics, tracing, and logs.

### 7.1. Distinguishing types of duration

| Measurement | Where measured | Usually reflects |
|---|---|---|
| Request duration in Swagger UI | Browser | Client-observed time from sending until receiving the response |
| Server request duration | Backend or web server | Server request handling time per system instrumentation point |
| Database query time | Data layer | Database query execution time |
| Distributed trace span | Each service/component | Timing and relationships across steps in a request |

For example, Swagger UI reports 850 ms while a controller metric reports 120 ms. The difference may lie in the network, gateway, authentication, serialization, or steps before/after the controller. Use tracing to pinpoint the gap instead of guessing from a single number.

### 7.2. Comparing durations meaningfully

When comparing two calls, keep conditions as similar as possible:

- Same endpoint, method, and server.
- Same payload and data size.
- Same authentication state and permissions.
- Same environment and network conditions.
- Record multiple samples instead of drawing conclusions from a single request.

The first request can be affected by application initialization, cold caches, or unpooled connections. Do not use a single measurement to conclude that performance improved or degraded.

## 8. Configuration example and reading a complete call

Suppose an API returns order details:

~~~java
import java.math.BigDecimal;
import java.util.List;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{orderId}")
    ResponseEntity<OrderResponse> getOrder(
            @PathVariable("orderId") String orderId,
            @RequestParam(name = "includeItems", defaultValue = "false")
            boolean includeItems) {

        OrderResponse response = new OrderResponse(
            orderId,
            "CONFIRMED",
            new BigDecimal("259900.00"),
            includeItems ? List.of("SKU-100") : List.of()
        );
        return ResponseEntity.ok(response);
    }
}

record OrderResponse(
    String orderId,
    String status,
    BigDecimal total,
    List<String> items
) {}
~~~

After opening <code>GET /api/orders/{orderId}</code>:

1. Click Try it out.
2. Enter <code>orderId = ORD-100</code>.
3. Set <code>includeItems = false</code>.
4. Click Execute.

An illustrative result may contain:

~~~text
Request URL
http://localhost:8080/api/orders/ORD-100?includeItems=false

Server response
Code: 200

Response body
{
  "orderId": "ORD-100",
  "status": "CONFIRMED",
  "total": 259900.00,
  "items": []
}

Response headers
content-type: application/json
~~~

Swagger UI also provides the corresponding cURL command and response duration if <code>displayRequestDuration</code> is enabled. This is an illustrative result; actual URL, body, headers, and duration depend on the running application.

## 9. Reproducing errors with cURL

Suppose Swagger UI receives <code>404</code> for an order ID. Copy the cURL command, re-run it in a terminal preserving the same method, URL, query, headers, and body. Then:

1. Compare status and response body between Swagger UI and the terminal.
2. If both fail identically, check the endpoint, data, and server logs.
3. If only Swagger UI fails, check CORS, cookies, tokens, server URL, and browser Network.
4. If cURL returns a different response, compare sent headers and authentication credentials.
5. If the response includes a request ID, use it to look up related logs.

When sharing error findings, record the method, URL with sensitive info masked, status, response body stripped of personal data, and request ID. Do not post access tokens, session cookies, or customer data in screenshots or public logs.

## 10. Notable edge cases

**Requests with query parameters.** Check that queries appear in Request URL and cURL; distinguish an absent parameter from an empty-valued parameter.

**Requests with a JSON body.** Check that cURL includes Content-Type and a body matching the schema. If the server returns <code>400</code>, inspect field error details and JSON types.

**Requests with file uploads.** Check the <code>multipart/form-data</code> media type, file field name, and other form fields. The browser generates the multipart boundary automatically; do not manually hardcode a Content-Type lacking a boundary when reproducing with cURL.

**File download responses.** Check status, <code>Content-Type</code>, <code>Content-Disposition</code>, and download behavior. The UI may not render binary payloads the way it renders JSON.

**Responses with no body.** For <code>204</code>, an empty body area is normal.

**Custom response headers not visible.** When calling cross-origin, check CORS expose headers and verify in Network.

**Response duration not shown.** Check <code>springdoc.swagger-ui.displayRequestDuration</code>, the loaded runtime config, and the bundled Swagger UI version.

## 11. Common errors

**Request URL points to the wrong server.** Select the right server in Swagger UI and check <code>servers</code> configuration, context path, and reverse proxy.

**cURL gives a different result from Swagger UI.** Compare tokens, cookies, headers, body, and URL. Generated cURL does not necessarily include every browser-added header.

**Response body does not match schema.** Inspect the DTO, Jackson serializer/deserializer, content negotiation, and exception handler; then update documentation or implementation.

**Status present but no body.** Check whether the status is <code>204</code> or the response legitimately has no content. If the status is an error, inspect response headers and server logs.

**Cannot read custom headers in the UI.** Check <code>Access-Control-Expose-Headers</code> for cross-origin requests.

**Response duration is higher than server logs.** Both measurements have different start/end boundaries. Use metrics and distributed tracing to find where the difference goes.

**Using a single request duration to judge performance.** Run multiple iterations under stable conditions and use proper benchmarking tools for load testing.

## 12. Checklist after every Execute

- [ ] Request URL points to the right server, path, and query parameters.
- [ ] Method, headers, and request body match the contract.
- [ ] cURL can reproduce the request after supplying any necessary details.
- [ ] HTTP status matches the expected scenario.
- [ ] Response body and Content-Type match the schema.
- [ ] Important response headers have been inspected.
- [ ] Response duration is understood as a client-side measurement.
- [ ] On error, compared cURL, Network, request ID, and server logs.
- [ ] Credentials and sensitive data are masked before sharing.

## References

- [Swagger UI – Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/): UI options, including displaying request duration.
- [springdoc-openapi – Properties](https://springdoc.org/properties.html): configuring <code>springdoc.swagger-ui</code>.
- [Swagger UI – Usage](https://swagger.io/docs/open-source-tools/swagger-ui/usage/overview/): reading operations and using Try it out.
- [curl – Manual](https://curl.se/docs/manpage.html): method, header, body syntax, and request options.
- [MDN – HTTP Messages](https://developer.mozilla.org/en-US/docs/Web/HTTP/Messages): HTTP request and response structure.
- [MDN – CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS): browser access to response headers on cross-origin calls.
