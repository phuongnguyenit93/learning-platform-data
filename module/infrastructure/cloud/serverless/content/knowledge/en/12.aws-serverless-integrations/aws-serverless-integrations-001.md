# Building HTTP Endpoints with API Gateway and Lambda Function URLs

AWS Lambda can handle HTTP requests via API Gateway or via a Lambda Function URL. Both approaches allow invoking a Java function over HTTPS and receiving a response, but they provide different API management layers.

API Gateway is suitable when an endpoint requires routing, centralized authentication, throttling, version/stage management, a custom domain, or multiple API operations. A Lambda Function URL is suitable for a simple endpoint attached directly to a single function, such as a webhook or a small HTTP handler, where API management requirements are basic.

To choose properly, you need to understand how a request enters Lambda, how the event payload is represented, who has permission to invoke the function, and the limits of each layer in the HTTP path.

## 1. Architecture Overview

An HTTP request to a Java Lambda can take one of two main paths.

~~~mermaid
flowchart TD
    C["HTTP client / browser / partner"] --> D{"Choose endpoint"}
    D -->|API Gateway| G["API Gateway route and authorizer"]
    G --> L["AWS Lambda Java function"]
    D -->|Function URL| U["Lambda Function URL"]
    U --> L
    L --> S["Database / queue / AWS services"]
    L --> R["HTTP response"]
    R --> C
~~~

With API Gateway, the gateway receives the request, applies policies at the API layer, and forwards the request to Lambda. Lambda processes it and returns the result according to the integration protocol. The gateway converts that result into an HTTP response for the client.

With a Function URL, AWS provides an HTTPS endpoint attached directly to a Lambda function or alias. Requests are forwarded to the function using HTTP payload format v2.0. The function handles routing and business logic itself, while policies such as application authentication, data validation, or per-tenant limits may need to be implemented in Lambda or in a preceding layer.

Both models are synchronous request/response. If an operation takes a long time or does not fit within HTTP wait times, the endpoint should record a job, send a message to a queue, or start a workflow, and then return an acknowledgment code for the client to query later.

## 2. How Do API Gateway and Lambda Function URL Differ?

| Criterion | API Gateway | Lambda Function URL |
|---|---|---|
| Entry point | Centrally managed API endpoint | HTTPS URL generated for Lambda |
| Routing | Has routes, methods, and stages | The function usually inspects path and method itself |
| Authentication | Can use IAM, JWT authorizer, Lambda authorizer, and mechanisms depending on API type | Choose AWS_IAM or NONE; additional business authentication in the application or preceding layer |
| Throttling | Has API-layer throttling policies | Mainly relies on Lambda concurrency and additional protection layers |
| API management | Has stages, deployments, custom domains, access logs, and API integrations | Minimalist, attached directly to the function |
| CORS | Can be configured in API Gateway | Has CORS configuration for Function URL |
| API keys and usage plans | Available on REST API; check features per API type | No built-in equivalent usage plan/API key management |
| Best suited for | APIs with multiple routes, multiple clients, or governance requirements | Webhooks or small endpoints with minimal centralized management requirements |

Not every API Gateway feature is available on every API type. API Gateway offers REST APIs and HTTP APIs with different feature sets. HTTP APIs are typically suited for simple HTTP APIs requiring routing and JWT/Lambda authorizers. REST APIs provide additional management features such as usage plans/API keys, caching, request validation, and advanced integrations. Cross-check the required features against the API type and current AWS documentation before choosing.

### 2.1. When to Choose API Gateway?

Choose API Gateway when you need an API management layer decoupled from the function:

- Multiple routes such as GET /orders, POST /orders, and GET /orders/{id}.
- Multiple Lambda functions or backend services behind the same API.
- Shared JWT or Lambda authorizer authentication.
- Per-route or per-API-stage throttling.
- Custom domains, dev/test/prod stages, and access logging.
- API key/usage plan management or features only available in REST API.
- Decoupling the public API lifecycle from the Lambda deployment lifecycle.

API Gateway also helps the function focus on business logic instead of building the entire HTTP layer itself. However, you must manage timeouts and payload limits for both the gateway and Lambda.

### 2.2. When to Choose Function URL?

A Function URL is suitable when:

- You only need a single endpoint attached directly to a single function.
- You want to reduce the number of components to configure and operate.
- The endpoint serves a webhook or simple integration.
- The caller can use AWS IAM/SigV4, or the application has its own authentication mechanism.
- You do not need the advanced API management features of API Gateway.

A Function URL does not automatically provide a user authentication system, per-tenant quotas, API key management, or multi-service routing. If those capabilities are needed, place an appropriate layer in front or use API Gateway.

A Function URL can sit behind CloudFront or another edge layer if you need a domain, caching, or additional protection policies. In that case, you must configure origin access, forwarded headers, and invoke permissions so clients cannot bypass the edge layer to call the origin URL directly against your intent.

## 3. Choosing HTTP API or REST API in API Gateway

API Gateway provides multiple API types. For HTTP endpoints invoking Lambda, the two commonly considered choices are HTTP API and REST API.

| Requirement | HTTP API | REST API |
|---|---|---|
| HTTP routing and Lambda proxy integration | Yes | Yes |
| Built-in JWT authorizer | Yes | Can use other authorizer mechanisms, including Cognito/Lambda/IAM depending on configuration |
| Lambda authorizer | Yes | Yes |
| CORS | Yes | Yes |
| Stages and custom domains | Yes | Yes |
| API keys and usage plans | No equivalent feature to REST API | Yes |
| API caching | No | Yes |
| Built-in request validation | More limited; usually validated in Lambda | Has configurable request validation |
| Advanced API management features | Focused on simple HTTP APIs | More options |

HTTP API is usually a good starting point for a new HTTP API if its features meet the requirements. REST API is suitable when you need specific management capabilities available only in that type. Do not choose solely based on the names “REST” or “HTTP”; list your mandatory features and verify the right API type.

## 4. Request Flow and Lambda Proxy Integration

With Lambda proxy integration, API Gateway transforms request information into a JSON event for Lambda. The event typically contains:

- HTTP method and path.
- Query string and path parameters.
- Headers and cookies.
- Request body.
- Request context information such as request ID, source IP, identity, or authorizer context.
- A flag indicating whether the body is Base64-encoded.

Lambda returns a status code, headers, and body. API Gateway uses this response to construct the HTTP response sent to the client.

With HTTP API payload format 2.0, some fields are structured as rawPath, rawQueryString, cookies, and requestContext.http. Lambda Function URLs also use payload format 2.0. Therefore, a Java handler using the HTTP API v2 event type can be shared across both endpoint types in many cases, provided the application does not depend on context fields specific to one integration type.

Do not assume that the API Gateway REST API v1 event and the HTTP API/Function URL v2 event share the same structure. REST API proxy integration typically uses payload format 1.0 with different field names and representations. Choose the right event class and response class according to the configured payload format.

## 5. Java Handler for HTTP API Payload v2.0

AWS Lambda Java Events provides event types for API Gateway HTTP API v2.0 and Function URLs. The example below illustrates a handler that receives a v2 event and returns a JSON response.

The example uses Java 17 and the AWS Lambda Java Core and AWS Lambda Java Events libraries. Choose dependency versions compatible with your project's JDK and build tool.

~~~java
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import com.amazonaws.services.lambda.runtime.events.APIGatewayV2HTTPEvent;
import com.amazonaws.services.lambda.runtime.events.APIGatewayV2HTTPResponse;

import java.util.Map;

public class HttpHandler
        implements RequestHandler<APIGatewayV2HTTPEvent, APIGatewayV2HTTPResponse> {

    @Override
    public APIGatewayV2HTTPResponse handleRequest(
            APIGatewayV2HTTPEvent event,
            Context context) {

        String method = event.getRequestContext().getHttp().getMethod();
        String path = event.getRawPath();

        if ("GET".equals(method) && "/health".equals(path)) {
            return response(200, "{\"status\":\"ok\"}");
        }

        if (!"GET".equals(method)) {
            return response(405, "{\"error\":\"method_not_allowed\"}");
        }

        return response(404, "{\"error\":\"not_found\"}");
    }

    private static APIGatewayV2HTTPResponse response(
            int statusCode,
            String body) {

        return APIGatewayV2HTTPResponse.builder()
                .withStatusCode(statusCode)
                .withHeaders(Map.of(
                        "content-type", "application/json; charset=utf-8",
                        "cache-control", "no-store"
                ))
                .withBody(body)
                .build();
    }
}
~~~

In the example, the handler only supports GET /health. A real-world API needs an appropriate router or framework, input validation, centralized error handling, and must not return stack traces to clients.

If using API Gateway REST API payload v1.0, use the corresponding event/response types, such as APIGatewayProxyRequestEvent and APIGatewayProxyResponseEvent. Do not force a v1 event into a v2 class or vice versa.

### 5.1. Handler Configuration and Packaging

Lambda needs to know the handler class and the selected Java runtime. With a custom runtime or native executable, how events are received and responses are returned differs from the standard Java managed runtime. Use the AWS Lambda Java runtime interface and adapters supported for your deployment model.

A Java project typically needs the following libraries:

- AWS Lambda Java Core to implement RequestHandler.
- AWS Lambda Java Events to use built-in event/response types.
- A JSON library if payload parsing/serialization is needed.
- AWS SDK v2 if the function calls AWS services.

Package the artifact in the format required by the runtime, configure the fully qualified handler class name with its package, and verify that the JAR or deployment package contains the required dependencies. If using Maven Shade or Gradle Shadow, check service metadata and resources after packaging.

## 6. Reading the Request Body and Handling Data Safely

An HTTP event can carry a string body. For binary bodies or certain integration types, the body may be Base64-encoded. The application must check the encoding flag before decoding.

Key principles:

- Check the Content-Type and body size.
- Parse JSON using a library with appropriate limits.
- Validate required fields, data types, lengths, and value ranges.
- Do not trust client-supplied headers such as tenant ID, role, or user ID.
- Do not log the entire body if it contains sensitive information.
- Return 400 for malformed data, 413 when exceeding payload limits, and 415 when the media type is unsupported.
- Set limits at both the gateway and the application; check the actual payload limits of both the gateway and Lambda.

For requests with large files, upload the file to S3 using a time-limited pre-signed URL and send the object key in the request. Avoid passing entire large files through API Gateway and Lambda unless necessary.

## 7. Routing, Path Parameters, and Query Strings

API Gateway can define explicit routes such as:

~~~text
GET    /health
POST   /orders
GET    /orders/{orderId}
DELETE /orders/{orderId}
~~~

Each route can be connected to a corresponding Lambda integration. You can use one function for multiple routes or split functions by bounded context, permission level, and load. A single large function with many routes reduces the number of deployments, but can tightly couple IAM permissions, concurrency, and scaling across routes.

With a Function URL, the URL is attached directly to the function; the handler or framework inside the function must distinguish methods and paths itself. If multiple routes or multiple backends are needed, you can use an in-application router, CloudFront/API Gateway in front, or split endpoints per function.

Query strings must be parsed according to standard URL encoding. Do not concatenate strings to build SQL, shell commands, or target URLs. Path parameters must be validated and encoded when used in queries or logs.

## 8. CORS and Preflight Requests

CORS is a browser mechanism that controls which web pages are allowed to read responses from another origin. It is not a user authentication mechanism and does not block non-browser clients such as curl or server-to-server callers.

If a frontend on a different origin calls the API, configure:

- Allowed origins: only origins that are actually permitted.
- Allowed methods: the methods the frontend needs.
- Allowed headers: Authorization, Content-Type, or required business headers.
- Exposed headers: headers the frontend needs to read, such as request ID or rate-limit metadata.
- Credentials: enable only when browser cookies or credentials are truly needed.

Browsers may send an OPTIONS preflight before the actual request. API Gateway or Function URL can be configured to handle CORS. If the gateway already manages CORS, avoid having Lambda return conflicting headers. For dynamic origins, only reflect origins that are on the allowlist; do not echo back any arbitrary Origin sent by the client.

Do not combine a wildcard origin with credentialed requests. If cookies are needed, configure specific origins, credentials, and appropriate cookie attributes such as Secure, HttpOnly, and SameSite.

## 9. Authentication and Invoke Permissions

### 9.1. API Gateway

API Gateway can verify callers before invoking Lambda:

- IAM authorization for callers using AWS Signature Version 4.
- JWT authorizer for access tokens from compatible identity providers.
- Lambda authorizer to apply custom authentication or authorization logic.
- Other built-in mechanisms depending on API type and configuration.

After authentication, you still need to check permissions on resources and tenants inside the application. A valid token does not mean the caller is allowed to read every order or perform every operation.

API Gateway needs permission to invoke the Lambda integration. Typically, a resource-based policy on the function is used to allow the API Gateway service principal to invoke that specific function, scoped by the appropriate API, account, stage, or source ARN. Do not grant broader permissions than needed.

### 9.2. Lambda Function URL

Function URL has two built-in authentication modes:

- **AWS_IAM:** callers must sign requests with SigV4 and have the necessary IAM permissions to invoke the URL.
- **NONE:** no IAM authentication is required at the Function URL layer; the endpoint can be called by any client that can reach the URL if the resource policy allows it.

NONE does not mean the application is protected. When using this mode for webhooks or public APIs, the handler must verify webhook signatures, JWT/session tokens, or appropriate business credentials. Do not treat a hard-to-guess URL as an authentication mechanism.

With AWS_IAM, check both the caller's identity policy and Lambda's resource-based policy. With NONE, check the resource-based policy and the scope of principals allowed to invoke. Exact permissions can depend on Function URL configuration and Lambda policy updates; verify current IAM documentation during deployment.

### 9.3. Do Not Confuse CORS, API Keys, and Authentication

- CORS controls whether a browser is allowed to read the response.
- API keys are typically used to identify clients, measure usage, or apply usage plans; they are not strong enough proof of identity for sensitive data.
- Authentication determines who the caller is.
- Authorization determines what the caller is allowed to do.
- Rate limiting and quotas control usage levels.

A secure endpoint usually needs a combination of these mechanisms according to the business risk level.

## 10. IAM Least Privilege and Protecting Lambda

The Lambda execution role defines what the function is allowed to do when it runs. This is the permission of the code inside the function, distinct from the permissions of clients allowed to call the endpoint.

For example, an order-creation function might only need permission to write to a specific DynamoDB table and send messages to a specific queue. Do not attach AdministratorAccess or read access to all of S3 just to deploy faster.

Distinguish three types of permissions:

1. **Caller permission:** which client or service is allowed to call the endpoint.
2. **Lambda resource policy:** which principal is allowed to invoke the function or Function URL.
3. **Lambda execution role:** which AWS services the function is allowed to access while running.

A misconfiguration in any of the three layers can cause 403/AccessDenied errors or grant overly broad permissions. When using API Gateway, scope invoke permissions to the exact API Gateway source ARN if possible. When using Function URL, restrict principals and auth type according to your design.

Do not put AWS access keys in the request body, query string, or environment variables when an IAM role can be used. Use the execution role and Secrets Manager/Parameter Store for application secrets; restrict secret read permissions to only the functions that need them.

## 11. Throttling, Concurrency, and Timeouts

API Gateway can apply throttling to protect the API. Lambda has its own concurrency limits, including reserved concurrency and account/region limits. These two layers complement each other:

- API Gateway throttling limits the rate of requests entering the API.
- Lambda concurrency limits the number of running invocations.
- Database connection pools and limits protect downstream dependencies.
- Per-tenant quotas require shared state or a dedicated quota service.

An API might not exceed its request rate yet still drive Lambda to high concurrency if each invocation takes a long time to process. Conversely, low concurrency can cause requests to be throttled even when the average rate is small. Account for both processing time and concurrent requests.

Timeouts for the client, API Gateway, and Lambda must be set with a clear relationship. If Lambda runs longer than the gateway or client wait time, the caller may receive a timeout while the function is still executing side effects. This causes the caller to retry and create duplicate operations. For long-running tasks, use a job ID, queue, or workflow to return results asynchronously.

Do not use infinite retries on the client. For 429 or 503 errors, clients should respect Retry-After if present, use exponential backoff with jitter, and use an idempotency key for non-idempotent operations.

## 12. HTTP Responses, Status Codes, and Errors

A Lambda proxy response typically contains a status code, headers, and a body. Use status codes with the right semantics:

| Status | When to use |
|---|---|
| 200 OK | Request succeeded and has a result |
| 201 Created | Resource created |
| 202 Accepted | Asynchronous job accepted |
| 204 No Content | Succeeded, no body |
| 400 Bad Request | Malformed request or missing data |
| 401 Unauthorized | Missing or invalid authentication credentials |
| 403 Forbidden | Caller lacks permission |
| 404 Not Found | Route or resource not found |
| 405 Method Not Allowed | Route does not support the method |
| 409 Conflict | State or idempotency conflict |
| 413 Payload Too Large | Body exceeds limit |
| 415 Unsupported Media Type | Unsupported Content-Type |
| 429 Too Many Requests | Rate limit or quota exceeded |
| 500 Internal Server Error | Unexpected error inside the function |
| 502/503 | Integration error or service temporarily unavailable, depending on the layer generating the response |

Do not return stack traces, SQL, internal ARNs, or secrets in responses. Log error details in controlled logs and return stable error codes to the client. With API Gateway, errors can be generated by the gateway, the authorizer, or Lambda; logs and statuses should help distinguish the error source.

## 13. Webhooks via API Gateway or Function URL

Webhooks are a common use case for serverless HTTP endpoints. External providers send events to the endpoint when events occur, such as payments, status changes, or task completions.

A webhook handler should:

1. Read the raw body exactly as sent by the provider.
2. Verify the HMAC signature or the provider's authentication mechanism.
3. Check the timestamp/nonce if the protocol supports replay protection.
4. Check the event ID to prevent duplicate processing.
5. Persist the event durably or write it to an inbox/queue.
6. Return 2xx after durable acceptance.
7. Process business logic via a worker if the task is long.

Do not parse JSON and re-serialize it before verifying the signature if the signature is computed over the raw bytes. Changing whitespace or encoding can cause signature verification to fail.

API Gateway is useful when you need multiple webhook routes, centralized authentication, or edge throttling. A Function URL is suitable for simple webhooks if the application verifies signatures and manages idempotency itself. For webhooks, public endpoints should not rely on a secret in the URL; use signature headers and securely managed secrets.

## 14. Observability and Request Tracing

A request can pass through API Gateway, an authorizer, Lambda, and multiple AWS services. Establish the ability to correlate logs:

- API Gateway request ID.
- Lambda awsRequestId.
- Correlation ID generated by the application or received from a trusted source.
- Route, method, and status code.
- Gateway duration, Lambda initialization time, and Lambda duration.
- Authorizer result and authentication errors, without logging tokens.
- Dependency latency and downstream errors.
- Throttling, concurrency, and retry information.

API Gateway access logs help distinguish gateway errors from errors inside Lambda. Lambda logs record application processing details. CloudWatch metrics/alarms can track request count, latency, 4xx/5xx, Lambda errors, throttles, duration, and concurrency. X-Ray or compatible tracing can help connect call segments across services.

Do not log Authorization headers, cookies, API keys, webhook signatures, or sensitive payloads. If investigation is needed, log a fingerprint or reference ID that cannot be reused as a credential.

## 15. Deploying and Testing the Endpoint

Before exposing the endpoint to the Internet, test both happy paths and error paths:

1. Call a valid route with the correct method.
2. Call a non-existent route and an unsupported method.
3. Send query strings, path parameters, and bodies with special encoding.
4. Send invalid JSON bodies, oversized bodies, and unsupported Content-Types.
5. Call without a token, with an expired token, and with a token lacking proper permissions.
6. Test CORS OPTIONS preflight from allowed origins and rejected origins.
7. Send requests exceeding throttling and verify 429 responses.
8. Simulate Lambda timeouts and slow dependencies.
9. Send webhooks with invalid signatures, duplicate event IDs, and stale timestamps.
10. Test a caller without permission to invoke the Function URL or API Gateway integration.
11. Verify the Lambda execution role only has necessary permissions.
12. Check access logs, Lambda logs, correlation IDs, and alarms.

You can use SAM, CDK, CloudFormation, or Terraform to manage API Gateway, Lambda, IAM policies, environment variables, and log configurations as code. Whichever tool you use, manage changes by environment and avoid manual edits in production without a reproducible configuration source.

Separate dev/test/prod endpoints using stages, aliases, or separate stacks as appropriate for your architecture. Do not allow dev endpoints to access production data. With Lambda aliases, configure the API integration or Function URL to point to the right alias/version according to your release strategy. Verify rollback and invoke permissions after each deployment.

## 16. Process for Choosing and Building an Endpoint

1. **Identify API requirements.** Number of routes, clients, authentication, quotas, domain, and operational needs.
2. **Choose API Gateway or Function URL.** If centralized API management is needed, prefer API Gateway; if the endpoint is simple with minimal governance features, consider Function URL.
3. **Choose the API Gateway type.** Compare HTTP API and REST API based on mandatory features.
4. **Choose the payload format.** Use event/response types matching v1.0 or v2.0.
5. **Write the Java handler.** Validate method/path/body, authenticate callers, and return proper status/headers/body.
6. **Configure permissions.** Separate caller permissions, Lambda resource policy, and execution role.
7. **Set limits.** Configure payload size, timeout, throttling, concurrency, and quotas.
8. **Configure CORS and domain.** Open only the required origins, methods, and headers.
9. **Add logging and tracing.** Use request IDs and correlation IDs, and exclude secrets from logs.
10. **Test and deploy.** Verify permissions, errors, retries, webhook duplicates, and rollback.

## 17. Self-Check Questions

- In what API management layers do API Gateway and Lambda Function URL differ?
- When is HTTP API more suitable than REST API?
- What built-in authentication modes does Function URL have?
- Why must a Function URL with AuthType NONE be protected at the application layer or a preceding layer?
- How do payload formats 1.0 and 2.0 affect Java event classes?
- Why does CORS not replace authentication or authorization?
- How do caller permission, Lambda resource policy, and execution role differ?
- Why must the gateway timeout be considered together with the Lambda timeout?
- How should a webhook verify signatures on the raw body and prevent duplicates?
- Which metrics and logs help isolate errors between API Gateway and Lambda?

API Gateway and Lambda Function URL can both expose a Java Lambda over HTTP, but they serve different levels of requirements. Choose based on routing, authentication, throttling, API management, and operational needs; then verify payload contracts, IAM, timeouts, CORS, and idempotency so the endpoint operates safely under real traffic.
