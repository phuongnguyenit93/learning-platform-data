# API Gateway, API deployments, and backend integrations

## 1. Objectives and context

In the **APIs, Events, and Integration** chapter of the **CLOUD_PROVIDERS_ORACLE** module, OCI API Gateway provides an API entry point for applications to call downstream services under a clear contract. Deployment must align with the tenancy, compartment, IAM, VCN, monitoring, and resource consumption controls.

The running example throughout this lesson is an orders API with three types of routes:

| Client-facing API | Purpose | Backend |
| --- | --- | --- |
| `GET /v1/health` | Verify the path to the gateway and deployment | Stock response |
| `GET /v1/orders/{orderId}` | Read order information | HTTP/HTTPS service |
| `POST /v1/order-summary` | Generate an order summary | OCI Functions |

After this lesson, learners can:

- Distinguish between a gateway, API resource, deployment, specification, route, and backend.
- Create a deployment with a consistent path prefix and routes.
- Integrate HTTP backends and Functions backends with appropriate permissions, networking, and data contracts.
- Distinguish between administrative IAM, client authentication, and gateway-to-backend authentication.
- Validate the configuration with a small lab, read logs, monitor metrics, and determine troubleshooting steps.

## 2. What does API Gateway do in the architecture?

**OCI API Gateway** is a service that manages API entry points, routes requests to backends, and applies supported policies such as authentication, CORS, rate limiting, or data transformation. Backends can be HTTP APIs or OCI Functions. See [Overview of API Gateway](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Concepts/apigatewayoverview.htm).

~~~mermaid
flowchart LR
    CLIENT["API client"] -->|HTTPS request| GW["OCI API Gateway"]
    GW --> DEP["Deployment /v1"]
    DEP --> ROUTE["Select route by path and method"]
    ROUTE --> STOCK["Stock response"]
    ROUTE --> HTTP["HTTP/HTTPS backend"]
    ROUTE --> FN["OCI Functions"]
    HTTP --> DATA["Business data"]
    FN --> DATA
    GW --> OBS["Access logs, execution logs, metrics"]
~~~

The diagram illustrates the logical flow. Deployment and route policies affect how a request is processed; the exact order depends on the policy type and configuration.

A gateway decouples the API address used by clients from the backend location. For example, clients still call `/v1/orders/ORD-1001` when the operations team migrates the orders service to a new compatible backend.

However, changing the backend does not automatically guarantee compatibility. The API owner team must still preserve the status codes, data schemas, authentication methods, and business semantics that clients depend on.

## 3. Resources and concepts

### 3.1. Gateway, deployment, and API resource

| Concept | Role |
| --- | --- |
| API gateway | Network entry point that receives API requests |
| API deployment | API configuration deployed on a gateway |
| Deployment specification | Description of routes, backends, and policies |
| Route | Maps a path, HTTP method, and backend |
| Backend | Target that processes requests or generates responses |
| API resource | Representation of an API at the design stage |
| API description | Description of the API contract, such as in OpenAPI |

An API resource is optional. You can create a deployment directly without creating an API resource first. If you use an API resource and API description, some information can be used to initialize the deployment configuration. See [API Gateway Concepts](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Concepts/apigatewayconcepts.htm).

An OpenAPI file describing the API contract does not replace all deployment decisions: you still need to determine the appropriate gateway, actual backend, networking, and policies.

### 3.2. One gateway can serve multiple deployments

You can create multiple routes within a single deployment, or multiple deployments on the same gateway. Each deployment has its own path prefix, such as `/v1` and `/v2`. See [Deploying an API by Creating an API Deployment](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewaycreatingdeployment.htm).

Design example:

~~~text
Gateway orders-gateway
├── Deployment orders-v1: prefix /v1
│   ├── GET  /health
│   ├── GET  /orders/{orderId}
│   └── POST /order-summary
└── Deployment orders-v2: prefix /v2
    └── GET /orders/{orderId}
~~~

This is an illustrative organization, not a requirement to have two versions. Choose deployment boundaries based on release, configuration, and governance needs.

## 4. Client URL, path prefix, and route

### 4.1. Assembling the correct URL

An API call has the form:

~~~text
https://<gateway-hostname><deployment-path-prefix><route-path>
~~~

With prefix `/v1` and route `/health`:

~~~text
https://<gateway-hostname>/v1/health
~~~

`<gateway-hostname>` must be obtained from the actual gateway in the Console or via the API. It is not the display name such as `orders-gateway`, nor is it the gateway OCID.

Routes are declared relative to the path prefix. Do not write a route as `/v1/health` if the deployment already has prefix `/v1`, unless you intentionally want a duplicated prefix in the URL. Invocation is described in [Calling an API Deployed on an API Gateway](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewayinvokingdeployedapi.htm).

| Configuration | Client-facing result |
| --- | --- |
| Prefix `/v1`, route `/health` | `/v1/health` |
| Prefix `/v1`, route `/orders/{orderId}` | For example `/v1/orders/ORD-1001` |
| Prefix `/v1`, route `/v1/health` | `/v1/v1/health` |

A path prefix does not accept path parameters or wildcards. If you choose prefix `/`, the gateway can only have that single deployment; consider this before choosing root for an API you plan to expand. See [Creating an API Deployment](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewaycreatingdeployment.htm).

### 4.2. Distinguishing the client URL and the backend URL

Suppose the client calls:

~~~text
GET https://<gateway-hostname>/v1/orders/ORD-1001
~~~

The backend may receive:

~~~text
GET https://orders.internal.example/internal/orders/ORD-1001
~~~

The two URLs can have different hosts and different path structures. The specification must describe the required mapping. Do not assume every part of the client path automatically appears in the backend URL.

The domain `orders.internal.example` is only an example; replace it with the real backend and configure DNS resolution accordingly.

## 5. Networking: gateway entry point and path to backend

### 5.1. Public or private is an entry-point decision

| Gateway | Expected access path |
| --- | --- |
| Public | Clients on the Internet when routes and network rules allow |
| Private | Clients within the VCN or a private network connected to the VCN |

A public gateway requires a public regional subnet and appropriate access configuration. The gateway accepts HTTPS on port `443`; corresponding ingress rules are required. A private gateway requires clients to have a route to its private IP address. See [Creating an API Gateway](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewaycreatinggateway.htm).

Being able to resolve DNS does not prove connectivity. A hostname may resolve to a private IP while the machine being tested has no route to that address.

### 5.2. A public gateway can still call a private backend

A public entry point and a private backend address two different requirements. For example, external clients call a public gateway, while the orders service sits behind a private load balancer and only accepts appropriate traffic from the gateway.

Two hops must be verified:

~~~text
Client → Gateway:
    DNS, route, HTTPS 443, certificate, and client policies.

Gateway → Backend:
    Backend DNS, route, egress, backend-side ingress,
    service port, TLS, and backend authentication.
~~~

A curl test on a laptop does not prove that the gateway's subnet can resolve the same hostname or has the same network path. When designing an HTTP integration, verify reachability and access permissions from the gateway's perspective. The document [Adding an HTTP or HTTPS URL as a Back End](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewayusinghttpbackend.htm) also describes backend hostname resolution requirements.

The lab in this lesson selects a **private** gateway and a test client on a network with connectivity to the VCN. This approach lets you observe the API configuration before deciding on a public entry point.

## 6. Three common backend types

The following examples focus on three common backends: `STOCK_RESPONSE_BACKEND`, `HTTP_BACKEND`, and `ORACLE_FUNCTIONS_BACKEND`. The service also provides specialized backends for authentication flows; the full list and guidance are in [Adding API Gateway Back Ends](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewayaddingbackendstoapigateways.htm).

### 6.1. Stock response: gateway-generated response

A stock response returns the declared status, headers, and body without calling an external business service. It is suitable for a configuration-check route or fixed responses. See [Adding Stock Responses as a Back End](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewayaddingstockresponses.htm).

Minimal specification:

~~~json
{
  "routes": [
    {
      "path": "/health",
      "methods": ["GET"],
      "backend": {
        "type": "STOCK_RESPONSE_BACKEND",
        "status": 200,
        "headers": [
          {
            "name": "Content-Type",
            "value": "application/json"
          }
        ],
        "body": "{\"gateway\":\"ok\",\"release\":\"lab-001\"}"
      }
    }
  ]
}
~~~

`body` is a string in the specification. Because that string contains JSON, the inner quotes are escaped.

A `200` result from this route only confirms that the entry path, deployment, and stock response configuration are working. It does not prove that the orders service or database is healthy.

### 6.2. HTTP backend: calling an HTTP/HTTPS service

An HTTP backend is suitable when the business logic already exposes an API, such as a service on Compute, OKE, behind a load balancer, or a REST endpoint of an integrated system.

Example of a **route** to add to the `routes` array:

~~~json
{
  "path": "/orders/{orderId}",
  "methods": ["GET"],
  "backend": {
    "type": "HTTP_BACKEND",
    "url": "https://orders.internal.example/internal/orders/${request.path[orderId]}",
    "connectTimeoutInSeconds": 3,
    "readTimeoutInSeconds": 10,
    "sendTimeoutInSeconds": 10,
    "isSSLVerifyDisabled": false
  }
}
~~~

`url` is the backend address; the three timeouts control the connection, response-reading, and request-sending phases. `isSSLVerifyDisabled: false` keeps backend certificate verification enabled. For a private CA, configure appropriate trust instead of disabling verification to mask errors. See [Adding an HTTP or HTTPS URL as a Back End](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewayusinghttpbackend.htm).

For the example above:

~~~text
Client:   /v1/orders/ORD-1001
Route:    /orders/{orderId}
Context:  request.path[orderId] = ORD-1001
Backend:  /internal/orders/ORD-1001
~~~

The `${request.path[orderId]}` syntax is a context variable evaluated by the gateway, not a value for the shell to substitute.

If writing the specification using a Bash heredoc, use a quoted delimiter to preserve this variable as-is:

~~~bash
cat > deployment.json <<'JSON'
{
  "routes": [
    {
      "path": "/orders/{orderId}",
      "methods": ["GET"],
      "backend": {
        "type": "HTTP_BACKEND",
        "url": "https://orders.internal.example/internal/orders/${request.path[orderId]}"
      }
    }
  ]
}
JSON
~~~

This is an example of replacing the configuration file in the learner's lab directory. When keeping multiple routes in the same specification, edit the `routes` array instead of overwriting the file with a single-route snippet.

Context variables can also be used in supported policies. For dynamic values in query strings, Oracle instructs using a query parameter transformation policy rather than concatenating dynamic query expressions directly into `url`. See [Adding Context Variables](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewaycontextvariables.htm).

### 6.3. Functions backend: calling a deployed function

Example of a route sending requests to OCI Functions:

~~~json
{
  "path": "/order-summary",
  "methods": ["POST"],
  "backend": {
    "type": "ORACLE_FUNCTIONS_BACKEND",
    "functionId": "REPLACE_WITH_REAL_FUNCTION_OCID"
  }
}
~~~

Replace the placeholder with a real function OCID. The function must be deployed, the gateway must have network connectivity to Functions, and it must have appropriate invoke permissions. The permissions of the user creating the deployment must also be prepared. See [Adding a Function as an API Gateway Back End](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewayusingfunctionsbackend.htm).

Example request contract chosen by the application team:

~~~http
POST /v1/order-summary HTTP/1.1
Content-Type: application/json

{"orderId":"ORD-1001"}
~~~

The function must read and validate data according to this contract, and return status, headers, and body compatible with the integration mechanism and FDK used. Do not assume that every existing function understands the exact same request structure.

For example, the function needs to know what to return when `orderId` is missing, when the order does not exist, and when the data service encounters an error. Those behaviors belong to the API contract and backend logic.

### 6.4. Integrating with other services at the right layer

| Backend system | Approach |
| --- | --- |
| HTTP microservice | HTTP backend |
| Short-lived logic deployed on OCI Functions | Functions backend |
| Oracle Integration with a suitable endpoint | HTTP integration with matching authentication |
| Oracle Database data | Appropriate service or REST layer accessing the DB |
| OCI API requiring signed requests | API-calling component with a valid signing mechanism |

A gateway works with APIs; a direct TCP connection to a database listener does not become a REST API merely by being placed behind a gateway.

In particular, forwarding the raw `Authorization` header of an OCI-signed request does not guarantee the signature remains valid when the host or path changes. Oracle recommends signing the final request sent to the target service, potentially via a Functions backend using an appropriate OCI authentication mechanism. See [OCI service API calls fail after being proxied through API Gateway](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewaytroubleshooting_topic-service_api_calls_fail_after_proxied.htm).

## 7. Administrative IAM and gateway permissions to invoke Functions

### 7.1. Separating principals

| Principal | Scope to consider |
| --- | --- |
| Developer or CI | Create/update gateways, deployments, and related configurations |
| API client | Allowed to call routes per API authentication/authorization policies |
| Gateway | Allowed to access backends requiring IAM or credentials |
| Backend function or service | Allowed to access business data |

Developer deployment permissions do not automatically allow clients to call business APIs, nor do they automatically grant a function permission to read a bucket or database.

Example granting permission to manage gateway resources in compartment `ApiDev`:

~~~text
Allow group 'Default'/'ApiDevelopers' to manage api-gateway-family in compartment ApiDev
~~~

The deployment team also needs permissions for networking and related resources according to the design. Do not treat this single policy statement as the entire configuration required for every backend.

### 7.2. Example of a gateway invoking Functions

Compartment-scoped policy template:

~~~text
Allow any-user to use functions-family in compartment AppFunctions where all { request.principal.type = 'ApiGateway', request.resource.compartment.id = '<GATEWAY_COMPARTMENT_OCID>' }
~~~

Replace the compartment and OCID with real values. The condition restricts the principal to API Gateways in the specified compartment. Here, `any-user` does not grant anonymous API clients permission to invoke the function directly.

This template grants scope to gateways belonging to that compartment; choose an organization and conditions that match your governance boundaries. IAM policy templates are described by Oracle in [Create Policies to Control Access](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewaycreatingpolicies.htm).

If the function further reads Object Storage or secrets, design the function's runtime permissions separately. That is a distinct access hop in the chain.

## 8. Authentication and authorization for API callers

### 8.1. Verifying identity and action permissions

**Authentication** determines who is calling. **Authorization** determines what that identity is allowed to do.

OCI API Gateway supports options such as token validation or invoking an authorizer function. See [Adding Authentication and Authorization](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewayaddingauthzauthn.htm).

For tokens, the configuration must match the API's issuer and audience. The design needs to specify where the token is obtained, what mechanism validates it, and what scopes or permissions each route requires. Refer to [Validating Tokens](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewayusingjwttokens.htm).

Example protection contract for the orders API:

| Route | Recommended permission |
| --- | --- |
| `GET /orders/{orderId}` | Permission to read orders and access that specific order |
| `POST /order-summary` | Permission to generate summaries |
| Administrative routes | Restricted to the corresponding admin role |

Object-level permissions, such as "a user can only view their own orders," must be checked at the layer that has sufficient business data. A valid token does not automatically prove ownership of every order ID.

### 8.2. Authorizer and business backend have different roles

An authorizer function decides whether a request is allowed to proceed; a backend function handles the route's business logic. Using the same Functions platform does not turn these two roles into a single step.

An authorizer can also affect latency, load, and availability. Define its inputs, outputs, and error-handling behavior according to the supported authorizer protocol. See [Passing Tokens to Authorizer Functions](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewayusingauthorizerfunction.htm).

## 9. Policies: applying the right scope

### 9.1. API policies are not IAM policies

IAM policies control permissions on OCI resources. Request/response policies in a deployment control how the API processes requests and responses.

Examples:

| Configuration | Effect |
| --- | --- |
| IAM `manage api-gateway-family` | Allows resource management operations |
| Authentication policy | Verifies client identity when calling the API |
| Rate limiting policy | Limits request rate according to configuration |
| CORS policy | Controls cross-origin resource sharing in browsers |
| Transformation policy | Modifies supported request/response data |

Not every policy type supports the same scope. Check whether a policy applies at the deployment level or route level instead of assuming every configuration can be placed arbitrarily at both levels.

### 9.2. Rate limiting at the deployment level

OCI API Gateway supports rate limiting across all routes of a deployment, either by total requests or by client IP. This policy is not configured individually per route within a deployment. See [Limiting the Number of Requests to Back Ends](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewaylimitingbackendaccess.htm).

Example top-level configuration section in a specification:

~~~json
{
  "requestPolicies": {
    "rateLimiting": {
      "rateKey": "TOTAL",
      "rateInRequestsPerSecond": 20
    }
  },
  "routes": [
    {
      "path": "/health",
      "methods": ["GET"],
      "backend": {
        "type": "STOCK_RESPONSE_BACKEND",
        "status": 200,
        "body": "ok"
      }
    }
  ]
}
~~~

`20` is an illustrative value for the lab. In a production system, choose the limit based on backend processing capacity and usage needs.

Per-IP is not the same as per-account: multiple users may share a NAT address. If usage needs to be managed by customer or service tier, evaluate usage plans and appropriate client identification mechanisms.

Rate limiting helps control incoming request volume. It does not replace timeouts, connection limits, or fault-tolerant design at the backend.

### 9.3. CORS for browser-based clients

CORS lets browsers decide whether to share a response with code running from another origin. You can configure the policy at the deployment or route level. See [Adding CORS support to API Deployments](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewayaddingcorssupport.htm).

Example configuration for a specific frontend:

~~~json
{
  "cors": {
    "allowedOrigins": ["https://app.example.com"],
    "allowedMethods": ["GET", "POST"],
    "allowedHeaders": ["Authorization", "Content-Type"],
    "exposedHeaders": ["opc-request-id"],
    "isAllowCredentialsEnabled": false,
    "maxAgeInSeconds": 300
  }
}
~~~

This content goes inside `requestPolicies` at the chosen scope. Replace the example origin with the real origin.

If a browser fails while curl succeeds, inspect the preflight request, method, headers, and CORS response. Curl does not enforce the same-origin policy like a browser does. At the same time, CORS does not grant business permissions to clients; the API still needs its own authentication/authorization mechanism.

## 10. Lab: creating an independently testable deployment

### 10.1. Preparation

The commands below are Bash instructions for learners to run in their own environment. The lab does not yet require deploying the orders service or a function; start with a stock response to test the entry path.

Prerequisites:

- A region and compartment dedicated to the API lab.
- OCI CLI configured with the correct profile, tenancy, and region.
- A VCN and private regional subnet already prepared.
- A test client with network connectivity to the VCN.
- Permissions to create gateways/deployments and use related network resources.
- HTTPS `443` ingress to the gateway from an appropriate test source.

In the Console, open **API Gateway**, create a gateway named `orders-gateway-lab`, type **Private**, and select the lab VCN and subnet. Wait until the resource is active, then record the gateway OCID and hostname from the Console.

You do not need to expose a real backend to the Internet to complete this test.

### 10.2. Save the lab specification

Create a `deployment.json` file in the lab directory with the full content from Section 6.1, containing the `/health` stock response route.

This specification does not declare client authentication and only returns fixed lab data. When adding business routes, you must configure protection according to the defined contract.

Set the actual values:

~~~bash
export OCI_REGION='us-ashburn-1'
export API_COMPARTMENT_OCID='REPLACE_WITH_API_COMPARTMENT_OCID'
export GATEWAY_OCID='REPLACE_WITH_GATEWAY_OCID'
export GATEWAY_HOSTNAME='REPLACE_WITH_GATEWAY_HOSTNAME'
~~~

`GATEWAY_HOSTNAME` must contain only the hostname, without `https://` or `/v1`. If you choose another region, update `OCI_REGION` to match the created resources.

### 10.3. Create the deployment

Run from the directory containing `deployment.json`:

~~~bash
oci api-gateway deployment create \
  --region "$OCI_REGION" \
  --compartment-id "$API_COMPARTMENT_OCID" \
  --gateway-id "$GATEWAY_OCID" \
  --display-name orders-v1-lab \
  --path-prefix /v1 \
  --specification file://deployment.json
~~~

`--specification` takes the specification content, not an outer wrapper document that also includes the gateway OCID and compartment. Those values are already passed via CLI parameters. The specification structure is described in [Creating an API Deployment Specification](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewaycreatingspecification.htm).

Record the deployment OCID from the output. Monitor the work request and deployment status in the Console; only run tests once creation succeeds and the deployment is `ACTIVE`.

You can inspect the resource again with the CLI:

~~~bash
export DEPLOYMENT_OCID='REPLACE_WITH_DEPLOYMENT_OCID'

oci api-gateway deployment get \
  --region "$OCI_REGION" \
  --deployment-id "$DEPLOYMENT_OCID"
~~~

A successful resource creation command does not prove that an HTTP backend will be reachable. With a stock response, there is not yet an outbound call to a business backend to verify.

### 10.4. Call the API from a client with connectivity to the private gateway

~~~bash
curl --include \
  "https://$GATEWAY_HOSTNAME/v1/health"
~~~

Expected output:

~~~http
HTTP/1.1 200
Content-Type: application/json

{"gateway":"ok","release":"lab-001"}
~~~

The HTTP version or some headers may vary depending on the connection; verify status `200` and the configured body.

Additional tests:

| Test | What to observe |
| --- | --- |
| Call `/v1/health` with GET | Receive the stock response |
| Call `/health` without the prefix | Does not match the configured API path |
| Call an undeclared path | Does not route to another backend |
| Call an undeclared method | Does not execute the behavior of an allowed method |
| Check logs | Locate the request entering the deployment |

Do not use `curl -k` by default. If TLS fails, inspect the hostname and certificate instead of skipping verification and concluding the configuration is complete.

## 11. Extending the lab to real backends

### 11.1. Adding an HTTP backend

Prepare an orders service and a test endpoint with a clear contract. Before updating the deployment, confirm:

1. The backend hostname resolves via the DNS used by the gateway.
2. Routes and network rules allow the gateway to connect to the backend port.
3. The backend has a valid certificate and trust chain if using HTTPS.
4. The backend accepts the intended method, path, headers, and authentication method.
5. Test order data exists to distinguish routing errors from business errors.

Add the route object from Section 6.2 to the `routes` array of `deployment.json`, keeping the `/health` route. Replace the example hostname with the real target.

Update:

~~~bash
oci api-gateway deployment update \
  --region "$OCI_REGION" \
  --deployment-id "$DEPLOYMENT_OCID" \
  --specification file://deployment.json
~~~

Updating the specification must retain all routes and policies you want to keep using; do not treat a single-route snippet as a patch that automatically merges into the current configuration. In CI, you can add `--if-match` with the ETag from a prior get call to control concurrent updates. See [deployment update](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/api-gateway/deployment/update.html).

After the update succeeds:

~~~bash
curl --include \
  "https://$GATEWAY_HOSTNAME/v1/orders/ORD-1001"
~~~

Compare the response with the test data and backend logs. The stock response still succeeding while the orders route fails indicates you should focus on the new integration hop.

### 11.2. Adding a Functions backend

Prepare a deployed function that handles the lab's JSON request. Confirm the gateway's permission to invoke the function, the deployer's permissions, and network connectivity to Functions.

Add the route from Section 6.3 to the specification, replace `functionId` with the real OCID, and update the deployment.

Invoke:

~~~bash
curl --include \
  --request POST \
  --header 'Content-Type: application/json' \
  --data '{"orderId":"ORD-1001"}' \
  "https://$GATEWAY_HOSTNAME/v1/order-summary"
~~~

If the deployment is protected by a bearer token, include a valid token according to the API configuration. Backend or function runtime credentials should not be sent by clients in place of the API token.

Verify the result in both places: the gateway routed the request and the function executed the business logic properly. If the function further accesses a database, verify that data hop as well.

### 11.3. Distinguishing verification levels accurately

| Passing test | What is proven | What still needs verification |
| --- | --- | --- |
| Stock response | Entry point and basic routing | Business backend |
| HTTP GET test order | One path to the HTTP backend | Per-user permissions and concurrent load |
| Functions response | Gateway can invoke the function | Data dependencies and error scenarios |
| Valid token | One authentication config works | Invalid tokens, missing scopes, expiration |
| Small load test | Behavior at measured load | Bursts, resource limits, and recovery |

These steps are a hands-on workflow for the learner; having a specification in the documentation does not mean cloud resources have been created or tests have been executed.

## 12. Latency, timeouts, and retries

### 12.1. Timeouts must align across the entire chain

A request may traverse the client, gateway, function or service, and then the database. Each tier can have its own timeout.

Design example:

~~~text
Client waits up to its contract limit
    → gateway has connection and backend I/O limits
    → backend sets a processing deadline
    → DB query has a timeout shorter than the remaining budget
~~~

The HTTP backend's connect/read/send timeout parameters control individual phases; do not treat them as a single total clock that can be simply summed in every scenario.

If the caller stops waiting, the side effect at the backend may already have occurred. For example, an order is written successfully but the response is lost; unguarded retries can write it a second time.

Therefore, APIs that create resources or trigger business actions must define an idempotency key, how duplicate requests are detected, and what response is returned on retries.

### 12.2. Choosing the right synchronous or asynchronous contract

A short-lived API can return results directly. If the work takes longer than the agreed HTTP budget, design it to accept the request, create a job, and provide a status-polling endpoint.

Example application-designed contract:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{"jobId":"JOB-1001","status":"accepted"}
~~~

The gateway routes this API; the backend must actually persist or hand off the work before acknowledging acceptance. Choosing to return `202` does not automatically create a queue, worker, or completion guarantee.

### 12.3. Multiple backends for the same route

API Gateway supports dynamically selecting a backend based on configured request elements, such as path context, headers, or authenticated identity. See [Dynamically Selecting API Gateway Back Ends](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewaydynamicroutingbasedonrequest_topic.htm).

This can be used to direct groups of requests to different compatible backends. However:

- Routing rules do not replace permission checks.
- Client-supplied headers do not prove the client belongs to a trusted group.
- A default rule and a consistent contract across backends are required.
- Selecting a backend per request does not automatically provide failover when one target fails.

For foundational practice, a single deterministic backend per route is usually easier to observe.

## 13. Logs and metrics for operations

### 13.1. Access logs and execution logs

API deployments have two main log types:

| Log | Purpose |
| --- | --- |
| Access log | Summary of requests and responses passing through the deployment |
| Execution log | Processing steps inside the gateway and error details |

Configure an appropriate execution log level and enable the log categories in OCI Logging for the deployment, with a log group and retention period. Setting the log level in the specification does not replace setting up the log collection destination. See [Adding Logging to API Deployments](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewayaddinglogpolicies.htm).

When investigating a request, record the timestamp, method, path, deployment, correlation ID, and backend release. If the application supports a correlation ID, standardize how it is propagated and logged across the gateway, services, and functions.

Log enough to investigate issues, but avoid logging tokens, passwords, or full sensitive order data.

### 13.2. Gateway and backend metrics

The metrics namespace is `oci_apigateway`. Notable metrics include `HttpRequests`, `HttpResponses`, `BackendHttpResponses`, `Latency`, `IntegrationLatency`, and `InternalLatency`. See [API Gateway Metrics](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Reference/apigatewaymetrics.htm).

| Observation | Analysis direction |
| --- | --- |
| Gateway returns many 4xx | Check routes, methods, tokens, and policies |
| Backend returns many 5xx | Cross-check backend logs and health |
| `IntegrationLatency` increases | Check integrations outside the gateway, including DNS or authentication |
| Total latency increases | Separate internal processing from integration calls |
| Sudden request spike | Distinguish real users, retries, and anomalous traffic |

Do not treat IntegrationLatency as solely the duration of business code. This metric also reflects external integrations outside the gateway that the request traverses.

### 13.3. Testing endpoints from the right vantage point

A stock response verifies reachability to a specific path; measuring dependencies requires adding a test aligned with the business workflow.

For a private gateway, the probe must have a route to the private network. For a public entry point, an appropriate external monitoring check can be used. Do not assume "no errors in metrics" means the endpoint is reachable. Oracle distinguishes reachability from metrics in [Monitoring endpoint reachability](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewaytroubleshooting_topic-monitor_endpoint_reachability.htm).

## 14. Hop-by-hop troubleshooting

| Symptom | Check first | Useful evidence |
| --- | --- | --- |
| Cannot connect to gateway | DNS, routes, port 443 ingress, and client location | Hostname, resolved IP, connection error |
| TLS handshake fails | Hostname, certificate, and trust chain | TLS error details, presented certificate |
| Does not match expected API | Prefix, route, method, and active deployment | Full URL and effective specification |
| Authentication/authorization error | Token, policy, and business permissions | Execution logs and auth configuration |
| Stock response works but HTTP route fails | Path to HTTP backend | DNS, routes, TLS, and backend access logs |
| Functions integration fails | Function OCID, gateway permissions, and connectivity | Gateway logs, function logs, and request ID |
| Slow response or timeout | Timeouts and downstream dependencies | Latency, integration latency, and backend logs |
| Browser fails but curl succeeds | CORS and preflight | OPTIONS request and response headers |
| OCI service rejects signature | Signature of the final request to the service | Host, path, and signing mechanism at the service-calling layer |

A status code is a symptom, not enough on its own to pinpoint the fault source. The same `5xx` error can originate from the backend, networking, or a processing step inside the gateway.

Investigation example:

~~~text
GET /v1/orders/ORD-1001 fails
    → /v1/health still returns 200
    → check whether the orders route points to the right backend
    → check gateway logs for DNS/TLS/connection errors
    → if the request reached the backend: check backend logs and data
~~~

Going hop by hop prevents changing authentication policies when the real root cause is that the backend hostname cannot resolve DNS.

## 15. Releases, rollbacks, and cost control

### 15.1. Managing specifications alongside releases

Keep specifications in version control, tied to the corresponding environment and backend configurations. When updating, review changes to routes, policies, backend URLs, and function OCIDs.

Note the boundaries:

- Changing the prefix or removing a route can break existing clients.
- Changing the backend can keep the URL intact while altering schemas or behavior.
- Changing policies can block legitimate clients or open unintended access.
- Rolling back a deployment does not automatically roll back data already written by the backend.

Running `/v2` alongside `/v1` only makes sense when there is a contract, a client migration plan, and a deprecation date for the old version. There is no need to create a new version for every compatible internal change.

### 15.2. End-to-end availability

Consider the gateway, networking, authentication service, backend, and data tier. A healthy gateway still results in API failures if the backend or database is down.

If cross-region redundancy is required, prepare the gateway, deployment, certificates, permissions, backend artifacts, and data in the target region. Having two deployments on the same gateway is not a cross-region redundancy plan.

For backends across multiple instances, use an appropriate distribution layer and health checks instead of assuming a single backend URL is inherently highly available.

### 15.3. Budgeting tied to actual traffic

Estimate costs from API request volume, invoked backends, networking, logs, and related services. Check pricing tables and tenancy terms at deployment time; this lesson does not assume fixed unit prices.

Items to measure:

| Factor | Control mechanism |
| --- | --- |
| Request volume and retries | Rate limiting, client monitoring, and retry policies |
| Functions backend | Measure invocation count, execution duration, and resources |
| External database/API backend | Concurrency limits and avoiding unnecessary calls |
| Logs | Choose log levels, data scope, and retention periods |
| Lab releases | Clean up test resources when no longer needed |

After the lab, delete only the deployment and gateway created specifically for the exercise if nothing else depends on them. Do not delete shared VCNs, policies, or functions just because the lab has ended.

## 16. Decisions to finalize for an API

A configuration ready for implementation must answer:

1. Which hostname, prefix, path, and method do clients call?
2. Which backend does each route target, and what request/response contract does it use?
3. Over which network do clients reach the gateway, and over which network does the gateway reach the backend?
4. Who may manage resources, who may call the API, and what permissions does the gateway use to invoke backends?
5. Where are timeouts, rate limits, CORS, and business permissions enforced?
6. Are there sufficient logs, metrics, and an approved configuration to investigate issues or roll back?

For the orders API, the stock response verifies the entry point; HTTP integration verifies the existing service; Functions integration connects the API to serverless logic. API correctness and availability come from keeping those hops aligned in configuration, permissions, and data contracts.
