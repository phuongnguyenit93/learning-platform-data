# Hands-On: Protecting and Publishing a Java API on GCP

A Java API allowing partners to query order status is running on Cloud Run. Handing the backend URL directly to partners makes it difficult for the development team to manage keys, limit traffic, monitor usage, and swap backends without breaking clients. **Google Cloud API Gateway** can serve as the front door for exposing OpenAPI-declared endpoints; when partner scale, API products, and advanced policies grow, **Apigee** is the full-featured API management choice.

This lesson belongs to the **API Gateway and Apigee** chapter of the **CLOUD_PROVIDERS_GCP** module. The goal is to practice a secure flow—**client → API Gateway → Java Cloud Run backend → Google Cloud services**—combining projects, IAM, VPCs, CI/CD, logging, reliability, and cost. The example is kept compact so it can be deployed in a lab project and then expanded with production controls on a sound foundation.

After this lesson, you can:

- Distinguish **caller authentication** (API key/JWT), **gateway-to-backend authentication** (IAM service account), and **business authorization** in Java.
- Write a minimal Java HTTP API, containerize it, and deploy it as a **private Cloud Run service**.
- Author an OpenAPI 2.0 spec with `x-google-backend`, routing, and an API key requirement.
- Create an API config and gateway with `gcloud`, enable the managed service, and test valid/invalid requests.
- Add JWT validation, quotas, logging, CORS restrictions, and secret handling.
- Know when to use **Apigee API proxies, API products, VerifyAPIKey, Quota, and SpikeArrest** instead of API Gateway.
- Practice a `401/403/404/429/5xx` troubleshooting runbook, rollbacks, and proper resource cleanup.

> **Lab scope:** all project IDs, service accounts, URLs, and API keys are placeholders. Commands creating Cloud Run/API Gateway/Artifact Registry resources incur charges; run only in an authorized project and never expose real customer data. This lesson **does not execute commands against a Google Cloud account**.

## 1. Architecture and Responsibility Boundaries

~~~mermaid
flowchart LR
    C["Partner client"] -->|"HTTPS + API key / JWT"| G["API Gateway"]
    G -->|"OIDC ID token from gateway SA"| R["Private Cloud Run Java API"]
    R -->|"ADC + runtime SA"| D["Cloud SQL / Cloud Storage / Pub/Sub"]
    I["IAM: Invoker + data roles"] --> G
    I --> R
    M["Logging / Monitoring / Billing"] --> G
    M --> R
~~~

| Layer | Identity / Control | Who Is Responsible? |
|---|---|---|
| **Client → Gateway** | API key identifies client project; JWT authenticates caller when configured | API provider manages OpenAPI, issuer, and key restrictions |
| **Gateway → Cloud Run** | API config uses a **backend-auth service account** to mint ID tokens; Cloud Run verifies IAM Invoker | Platform/IAM team |
| **Java → data** | **Cloud Run runtime service account** uses ADC to call APIs or DBs | Developer/data owner |
| **Java authorization** | Right user/tenant, scopes, order ownership, input validation | Java application |
| **API governance** | OpenAPI, quotas, analytics, developer onboarding | API platform team |

**Important:** an API key is **not** proof of who the end user is; a leaked key can be copied. A JWT validated by the Gateway only settles token validity against issuer/audience; Java must still decide **which orders that caller may view**. Backend IAM controls **who can invoke Cloud Run**, not business authorization.

### Choosing API Gateway or Apigee?

| Criterion | **API Gateway** | **Apigee** |
|---|---|---|
| Purpose | Lightweight API publishing with OpenAPI/gRPC, routing, API keys/JWTs, quotas | Lifecycle of **API products**, consumer apps, policies, analytics, and partner governance |
| Definition unit | API → API config → Gateway | API proxy → environment → API product → developer app |
| Routing | `x-google-backend` in OpenAPI | ProxyEndpoint/TargetEndpoint and flows |
| Traffic control | Quotas in API config/Service Control and backend limits | SpikeArrest, Quota, per-app/product policies |
| Policy extensibility | Supported OpenAPI extensions | Auth, transformation, traffic, threat protection, caching policies per license |
| Complexity | Less operational overhead for common APIs | More configuration, permissions, and cost |

A simple Java API for a few internal/partner apps usually starts with **API Gateway**. If the organization sells APIs under Bronze/Silver/Gold tiers, needs a developer portal, consumption terms, and complex policy chains, consider **Apigee**. Never assume "Apigee is automatically more secure in every case": effectiveness depends on policies, IAM, networking, and operational discipline.

## 2. Lab: A Simple Java HTTP API

The lab uses **JDK 21** to avoid framework dependencies. The API returns non-sensitive JSON at `GET /v1/hello` and exposes a health check at `GET /healthz`. With a real Spring Boot application, you keep the exact same gateway pattern and swap the backend container.

**`App.java`**

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class App {
    public static void main(String[] args) throws Exception {
        int port = Integer.parseInt(
            System.getenv().getOrDefault("PORT", "8080"));
        HttpServer server = HttpServer.create(
            new InetSocketAddress("0.0.0.0", port), 0);
        ExecutorService executor = Executors.newFixedThreadPool(8);
        server.setExecutor(executor);

        server.createContext("/v1/hello", ex -> {
            if (!"GET".equals(ex.getRequestMethod())) {
                send(ex, 405, "{\"error\":\"method_not_allowed\"}");
                return;
            }
            send(ex, 200, "{\"message\":\"hello from Java API\"}");
        });
        server.createContext("/healthz", ex ->
            send(ex, 200, "{\"status\":\"ok\"}"));

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            server.stop(1);
            executor.shutdown();
        }));
        server.start();
        System.out.println("Listening on port " + port);
    }

    private static void send(HttpExchange ex, int status, String json)
            throws IOException {
        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set(
            "Content-Type", "application/json; charset=utf-8");
        ex.sendResponseHeaders(status, bytes.length);
        try (var output = ex.getResponseBody()) {
            output.write(bytes);
        }
    }
}
~~~

This is a minimal lab handler without persistence, per-tenant auth, request validation, or tracing. Java's `HttpServer` uses prefix matching: sensitive routes in real applications must be routed and guarded explicitly. **Never treat OpenAPI as the sole authorization layer**, especially when the backend exposes other paths.

**`Dockerfile`**

~~~dockerfile
FROM eclipse-temurin:21-jdk AS build
WORKDIR /src
COPY App.java .
RUN javac --add-modules jdk.httpserver -d /app App.java

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /app /app
USER 65532:65532
EXPOSE 8080
ENTRYPOINT ["java", "--add-modules", "jdk.httpserver", "-cp", "/app", "App"]
~~~

Test locally before deploying:

~~~bash
docker build --platform linux/amd64 -t java-api-gateway:lab .
docker run --rm -e PORT=9090 -p 9090:9090 java-api-gateway:lab

# Another terminal:
curl -i http://localhost:9090/v1/hello
curl -i http://localhost:9090/healthz
~~~

Expect `200` and valid JSON. Because this lab uses only `GET`, no database is needed yet. When upgrading to an orders API, the Java service can use ADC to access Cloud SQL/Firestore/Storage via its own runtime service account; **never bake a JSON private key into a Docker image**.

## 3. Deploying a Cloud Run Backend Requiring IAM

Prepare a Google Cloud project with billing enabled and deployment permissions; choose a region supported by both API Gateway and Cloud Run. Example in Bash/Cloud Shell:

~~~bash
PROJECT_ID="my-api-lab-project"
REGION="asia-southeast1"
REPO="api-images"
SERVICE="java-orders-api"
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/java-api:v1"
RUN_SA="java-api-runtime@$PROJECT_ID.iam.gserviceaccount.com"
GW_SA="api-gateway-backend@$PROJECT_ID.iam.gserviceaccount.com"

gcloud config set project "$PROJECT_ID"
gcloud services enable \
  run.googleapis.com artifactregistry.googleapis.com \
  apigateway.googleapis.com servicemanagement.googleapis.com \
  servicecontrol.googleapis.com

# Create the repository and service accounts only if they do not exist yet.
gcloud artifacts repositories create "$REPO" \
  --repository-format=docker --location="$REGION"
gcloud iam service-accounts create java-api-runtime \
  --display-name="Cloud Run Java API runtime"
gcloud iam service-accounts create api-gateway-backend \
  --display-name="API Gateway backend invocation"

gcloud auth configure-docker "$REGION-docker.pkg.dev"
docker build --platform linux/amd64 -t "$IMAGE" .
docker push "$IMAGE"

gcloud run deploy "$SERVICE" \
  --image="$IMAGE" \
  --region="$REGION" \
  --service-account="$RUN_SA" \
  --ingress=all \
  --no-allow-unauthenticated \
  --port=8080 \
  --timeout=30s \
  --max-instances=5

RUN_URL="$(gcloud run services describe "$SERVICE" \
  --region="$REGION" --format='value(status.url)')"
echo "$RUN_URL"
~~~

**Why `--ingress=all` yet still called private?** The Cloud Run URL is network-reachable over the Internet, yet **IAM requires a valid ID token and Invoker permission**. `--ingress=internal` is generally unsuitable for direct invocation by public API Gateway. This is **authentication/IAM** protection, not a claim that the backend only has a private IP. Systems requiring strict network-path isolation need a dedicated design (load balancer/IAP/Apigee/network perimeter) per supported product features.

### Grant Backend Invocation Permission to the Exact Service Account

~~~bash
gcloud run services add-iam-policy-binding "$SERVICE" \
  --region="$REGION" \
  --member="serviceAccount:$GW_SA" \
  --role="roles/run.invoker"

# Verify Cloud Run has not granted Invoker to allUsers.
gcloud run services get-iam-policy "$SERVICE" --region="$REGION"
~~~

**Never grant `roles/run.admin` or `roles/editor` to the Gateway.** It only needs `run.routes.invoke` on the service. The deployer creating the API config needs `iam.serviceAccounts.actAs` on `GW_SA` (typically via `roles/iam.serviceAccountUser` on that SA) plus appropriate API Gateway management permissions; **do not grant service account impersonation rights to every developer**.

Test before creating the Gateway:

~~~bash
# Without an ID token/Invoker, access must be rejected.
curl -i "$RUN_URL/v1/hello"

# If the test account holds run.invoker:
curl -i -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "$RUN_URL/v1/hello"
~~~

If the tester lacks Invoker, the second command also returns `403`; that is **correct IAM behavior**, not a Java bug. Avoid "fixing" it with `--allow-unauthenticated`.

## 4. OpenAPI Definition and API Key Policy

API Gateway requires an **API definition** declaring allowed paths, the backend URL, and client protection rules. This example uses **OpenAPI 2.0** for concise syntax, broad API Gateway support, and straightforward `x-google-backend` usage. API Gateway also supports OpenAPI 3.x, though extensions and `securitySchemes` use different syntax.

Create a lab file named **`openapi.yaml`** and replace `CLOUD_RUN_URL` with the real `RUN_URL` obtained after deployment:

~~~yaml
swagger: "2.0"
info:
  title: java-orders-lab-api
  version: "1.0.0"
  description: Java Cloud Run API protected by API Gateway
schemes:
  - https
produces:
  - application/json

# Do not forward routes undeclared in OpenAPI.
x-google-allow: configured
x-google-backend:
  address: https://YOUR-CLOUD-RUN-SERVICE-URL.run.app
  path_translation: APPEND_PATH_TO_ADDRESS
  deadline: 20.0

securityDefinitions:
  api_key:
    type: apiKey
    name: x-api-key
    in: header

# Every operation in this sample requires an API key.
security:
  - api_key: []

paths:
  /v1/hello:
    get:
      summary: Say hello from Java
      operationId: getHello
      responses:
        "200":
          description: Successful response
          schema:
            type: object
            properties:
              message:
                type: string
        "405":
          description: Method not allowed
~~~

**Explaining the decisive fields:**

- `x-google-backend.address` is the **root HTTPS URL** of the Cloud Run service (not the gateway URL). A wrong URL causes backend errors at the gateway.
- `path_translation: APPEND_PATH_TO_ADDRESS` forwards `/v1/hello` to Cloud Run **preserving the path**, matching the Java handler. When placed at the **operation level**, the default can be `CONSTANT_ADDRESS`, turning path segments into query parameters; declare it explicitly.
- `deadline: 20.0` sets a 20-second gateway wait limit for the backend in this example, kept below Cloud Run's `--timeout=30s`. The default API Gateway deadline is 15 seconds if omitted. Limits vary by gateway/streaming mode; check current docs before raising it.
- `x-google-allow: configured` allows only declared methods/paths; avoid `all`, which lets undeclared routes pass **without the same auth rules**.
- `securityDefinitions.api_key` requires a key in the `x-api-key` header. **An API key identifies the project/consumer for usage control**, not end-user identity.
- Global `security` applies to all operations; adding `security` on a specific operation **overrides** global security. Review carefully to avoid accidentally exposing sensitive endpoints.

When adapting `openapi.yaml` per environment, **do not manually append a path** to `address` when the backend already serves `/v1/hello`, since `APPEND_PATH_TO_ADDRESS` appends the request path again. Verify with the two `curl` tests at the end of the lab.

## 5. Creating the API Config, Enabling the Managed Service, and Creating the Gateway

From the lab directory containing `openapi.yaml` with the real backend URL substituted:

~~~bash
API_ID="java-orders-lab"
CONFIG_ID="java-orders-v1"
GATEWAY_ID="java-orders-gateway"

gcloud api-gateway apis create "$API_ID" --project="$PROJECT_ID"

gcloud api-gateway api-configs create "$CONFIG_ID" \
  --api="$API_ID" \
  --openapi-spec="openapi.yaml" \
  --backend-auth-service-account="$GW_SA" \
  --project="$PROJECT_ID"

gcloud api-gateway api-configs describe "$CONFIG_ID" \
  --api="$API_ID" --project="$PROJECT_ID"
~~~

During API config creation, Google Cloud takes time to validate and deploy the configuration; do not re-run `create` with the same ID while an operation is still in progress. An API config is **immutable for routing/auth**: when editing OpenAPI, create a **new config ID** and update the gateway rather than overwriting the old config.

### Enable the Managed Service for API Keys

API Gateway uses Service Management/Service Control to validate API keys and quotas. After creating the API, retrieve its **managed service name** from the API description and enable it:

~~~bash
MANAGED_SERVICE="$(gcloud api-gateway apis describe "$API_ID" \
  --project="$PROJECT_ID" \
  --format="value(managedService)")"
echo "$MANAGED_SERVICE"

# This is the API's own managed service, not apigateway.googleapis.com.
gcloud services enable "$MANAGED_SERVICE" \
  --project="$PROJECT_ID"
~~~

Do not guess the managed service name from the API ID; use the exact `managedService` value returned by Google Cloud. If it does not appear immediately under APIs & Services, wait for propagation and check again.

### Create a Regional Gateway

~~~bash
gcloud api-gateway gateways create "$GATEWAY_ID" \
  --api="$API_ID" \
  --api-config="$CONFIG_ID" \
  --location="$REGION" \
  --project="$PROJECT_ID"

gcloud api-gateway gateways describe "$GATEWAY_ID" \
  --location="$REGION" \
  --project="$PROJECT_ID"

GW_HOST="$(gcloud api-gateway gateways describe "$GATEWAY_ID" \
  --location="$REGION" \
  --project="$PROJECT_ID" \
  --format='value(defaultHostname)')"
echo "https://$GW_HOST"
~~~

Wait for the Gateway to reach **ACTIVE** state before testing. `defaultHostname` is Google-assigned; if you need a **custom domain**, follow the proper DNS/TLS and load balancer setup rather than pointing an arbitrary CNAME and expecting HTTPS to work automatically.

### Create an API Key and Test Requests

In the Google Cloud Console, go to **APIs & Services → Credentials → Create credentials → API key** in the test client project. Apply **API restrictions** to the exact `java-orders-lab-api` managed API and **application restrictions** (HTTP referrers, server IPs, or appropriate client type) where possible. Store the key in Secret Manager or a temporary client environment variable; **never commit keys to Git or logs**.

~~~bash
# Set temporarily on the lab machine. NEVER write real values into Markdown.
API_KEY="REPLACE_WITH_RESTRICTED_LAB_API_KEY"

# Missing key: expected to be rejected by the gateway.
curl -i "https://$GW_HOST/v1/hello"

# Invalid key: must also be rejected by the gateway.
curl -i -H "x-api-key: INVALID" \
  "https://$GW_HOST/v1/hello"

# Valid authorized key: expected HTTP 200 and JSON.
curl -i -H "x-api-key: $API_KEY" \
  "https://$GW_HOST/v1/hello"

# Undeclared route: must not be forwarded to the backend.
curl -i -H "x-api-key: $API_KEY" \
  "https://$GW_HOST/healthz"
~~~

Error codes for missing/invalid keys may be `401` or `403` with bodies reflecting Service Control reasons; **never hardcode an expectation of a single status code**. `/healthz` is omitted from OpenAPI and thus is not routed; in production, also test unsupported methods like `POST /v1/hello`.

**Verifying both independent paths:** if `curl` to the Cloud Run URL without an ID token fails, while `curl` through the gateway with a valid API key returns 200, you have verified both **backend IAM** and **gateway client-key** enforcement in the lab scope. This **does not yet prove** JWT/end-user authorization since the lab currently uses only an API key.

## 6. Protecting Real Applications: JWTs and Business Authorization

In production, an API key can tie traffic to a consumer project for quotas and attribution, yet it is **insufficient** for personal, financial, or order data. Authenticate callers with **JWT** (or an equivalent mechanism), then enforce business authorization in the backend.

Add an OpenAPI 2.0 security definition with an organization-trusted OIDC issuer/JWKS. The example illustrates Google ID tokens with issuer `https://accounts.google.com`; `CLIENT_ID` must be an approved OAuth client audience:

~~~yaml
# Merge into existing securityDefinitions; do not replace with a separate block.
securityDefinitions:
  api_key:
    type: apiKey
    name: x-api-key
    in: header
  google_id_token:
    type: oauth2
    flow: implicit
    authorizationUrl: ""
    x-google-issuer: https://accounts.google.com
    x-google-jwks_uri: https://www.googleapis.com/oauth2/v3/certs
    x-google-audiences: YOUR_OAUTH_CLIENT_ID

# Same list item: requires BOTH API key AND JWT.
security:
  - api_key: []
    google_id_token: []
~~~

**Important OpenAPI security semantics:** schemes inside one list object combine with **AND**; writing two separate items `- api_key: []` and `- google_id_token: []` expresses **OR**—either one could pass. Never leave auth unintentionally open by misreading YAML indentation.

The client sends:

~~~bash
# ID_TOKEN must be issued for the exact issuer/audience and not expired.
ID_TOKEN="REPLACE_WITH_VALID_USER_ID_TOKEN"
curl -i "https://$GW_HOST/v1/hello" \
  -H "x-api-key: $API_KEY" \
  -H "Authorization: Bearer $ID_TOKEN"
~~~

API Gateway verifies the token signature via JWKS, `iss`, `aud`, `exp`, and required claims. When JWT authentication is configured, the gateway forwards verified claims in the **`X-Apigateway-Api-Userinfo`** header (base64url-encoded payload). The gateway may **replace** the `Authorization` header with the ID token used for **backend invocation**; do not assume `Authorization` arriving at Java is the user's original token.

**Preventing header spoofing:** clients could forge headers if the backend had another access path or a misconfigured proxy. Therefore:

1. Ensure Cloud Run grants `run.invoker` **only to authorized principals**, never `allUsers`.
2. Configure API Gateway JWT validation with the right issuer/audience and eliminate bypass routes.
3. Trust `X-Apigateway-Api-Userinfo` only when requests genuinely arrive through the authenticated gateway and direct backend access is locked down; for sensitive systems, validate tokens/claims inside the app or adopt deeper security controls as required.
4. In Java, enforce authorization by `sub`/tenant/roles and **resource ownership**, not merely checking that a JWT has a valid signature.

**Deploying the change:** create a new API config (e.g., `java-orders-v2`) from the JWT-enabled OpenAPI spec, wait for ACTIVE, test with and without tokens, then run:

~~~bash
gcloud api-gateway gateways update "$GATEWAY_ID" \
  --api="$API_ID" \
  --api-config="java-orders-v2" \
  --location="$REGION" \
  --project="$PROJECT_ID"
~~~

Run this only after **`java-orders-v2` has been successfully created via `api-configs create`** and routes/auth are verified; do not treat `update` as creating the config itself. Keep the older config for rollback if needed, then clean up unused configs per procedure.

## 7. Quotas, Rate Limiting, CORS, and Request Validation

API Gateway can use an **API key tied to a consumer project** for quota tracking. Distinguish:

- **Quota:** caps API usage over a time window (API Gateway supports **per-minute/per-project** quotas via OpenAPI 2.0 extensions).
- **Burst rate limiting:** protects the backend from multi-second traffic spikes; per-minute quotas do not fully replace burst controls.
- **Authorization:** permission to call a route or read an order; quotas are not authorization.
- **CORS:** a browser policy governing cross-origin requests, **not** a mechanism that stops `curl` callers.

### Example Quota Declaration for API Gateway

Add these sections to OpenAPI **2.0**; `x-google-management` sits **top-level**, while `x-google-quota` sits **inside the `GET /v1/hello` operation**:

~~~yaml
# Top-level (same level as info, securityDefinitions, paths)
x-google-management:
  metrics:
    - name: read-requests
      displayName: Read requests
      valueType: INT64
      metricKind: DELTA
  quota:
    limits:
      - name: read-requests-per-minute
        metric: read-requests
        unit: "1/min/{project}"
        values:
          STANDARD: 100

# Under paths./v1/hello.get:
x-google-quota:
  metricCosts:
    read-requests: 1
~~~

This quota means **100 quota units per minute per consumer project** for an operation assigned cost 1. It is not "100 requests per user" or an IP limit. Operations **without `x-google-quota`** are not automatically subject to this quota. The consumer project must be validly identified via an API key.

**Changing quotas across multiple gateways:** `metrics` and `quota` are managed at the **API level**, not isolated per API config. If v1 and v2 configs serve simultaneously and you **rename or remove a quota metric**, gateways still running the old config can return **HTTP 500** during quota checks. Keep metric names/structures compatible during rollouts; adjust limits only after assessing impact scope.

### CORS in Web APIs

If a frontend at `https://portal.example.com` calls the gateway cross-origin, browsers send a **preflight `OPTIONS`** request when headers/methods require it. The gateway does not automatically enable CORS on every endpoint:

1. Declare the corresponding `OPTIONS` route/method in OpenAPI, checking preflight auth requirements (browsers do not always send API keys/JWTs on preflight).
2. Have the backend or proxy layer return `Access-Control-Allow-Origin` with approved origins and minimal `Access-Control-Allow-Methods` / `Access-Control-Allow-Headers`.
3. Never use `Access-Control-Allow-Origin: *` alongside credentialed requests.
4. Never embed secret API keys in client-side code that cannot keep secrets; public websites can have keys extracted, so use JWTs and design usage protection accordingly.

**CORS does not replace IAM, API keys, or JWTs.** A caller using `curl` bypasses browser CORS policies completely.

### Controls That Must Remain in Java

API Gateway does not enforce all schema or business constraints. The Java API must still validate:

- Body length, `Content-Type`, required fields, and file upload limits.
- Tenant and data-owner authentication/authorization.
- SQL parameterization, injection prevention, and output escaping.
- Idempotency keys for side-effecting `POST` requests, plus transaction/correlation IDs.
- Timeouts and connection pools to Cloud SQL; never return sensitive payloads or stack traces.
- Additional rate limits/circuit breakers when backends have fragile downstream dependencies.

## 8. Moving to Apigee: Governing APIs for Many Partners

**Apigee** organizes APIs as products and manages API consumers explicitly:

~~~mermaid
flowchart LR
    C["Partner developer app"] --> P["Apigee API proxy"]
    P --> V["VerifyAPIKey / JWT / OAuth2"]
    V --> Q["Quota / SpikeArrest / threat policies"]
    Q --> T["TargetEndpoint: Java API"]
    PROD["API product"] --> V
    DEV["Developer + App registration"] --> PROD
    M["Apigee Analytics"] --> P
~~~

| Concept | Meaning |
|---|---|
| **API proxy** | Public URL, ProxyEndpoint, TargetEndpoint, and flow/policy chain before calling backend |
| **API product** | Bundle of resource paths, HTTP methods, and consumption quotas/entitlements for app groups |
| **Developer app** | Client registered to an API product with credentials and approved/revoked status |
| **VerifyAPIKey** | Verifies the key belongs to a valid app and eligible product |
| **OAuthV2 / VerifyJWT** | Validates bearer tokens and related policies per identity model |
| **Quota** | Consumption allowance per app/product and time window |
| **SpikeArrest** | Smooths sudden traffic spikes to protect the target |
| **API analytics** | Tracks usage, latency, and errors by app/product/proxy |

**Core distinction:** API Gateway keys typically identify a **consumer Google Cloud project**, whereas Apigee developer apps/API products model **partner access contracts** with fine-grained lifecycle and analytics management. Do not assume creating an API product enforces policies automatically: attach **`VerifyAPIKey`/OAuth/Quota policies** to the appropriate proxy flows.

### Example VerifyAPIKey Policy

A policy file inside an Apigee API proxy:

~~~xml
<VerifyAPIKey name="Verify-Partner-Key">
  <APIKey ref="request.header.x-api-key"/>
</VerifyAPIKey>
~~~

Attach this policy to the **ProxyEndpoint request PreFlow** (or appropriate flow) to block requests lacking a valid key **before reaching the target**. In Apigee, keys are issued when a developer app subscribes to an API product—do not expect a **Google Cloud API key** from APIs & Services Credentials to work as an Apigee developer-app key.

### Example Burst Protection with SpikeArrest

~~~xml
<SpikeArrest name="Limit-Sudden-Traffic">
  <Rate>10ps</Rate>
</SpikeArrest>
~~~

`10ps` is a directional threshold of **10 requests/second** under the policy's smoothing algorithm—not a promise of exactly 10 requests every second or a guarantee against overload. To isolate limits per **partner/app**, configure `Identifier` from `VerifyAPIKey` flow variables as needed; use **Quota** for daily/monthly allowances or API product tiers.

**Apigee does not bypass backend permissions.** If the Java target is a private Cloud Run service, the proxy needs proper backend authentication (supported via Apigee target/token policies, service accounts, and IAM Invoker). Never make the backend public just to test Apigee. Before scaling to production proxies, verify token minting, target SSL, VPC connectivity, and actual Apigee runtime region.

### Scenario for Choosing Apigee Over API Gateway

An enterprise has 120 partners: **Bronze** tier gets 1,000 requests/day, **Gold** gets 100,000 requests/day, needing a self-service developer portal, per-app analytics, revocation, threat policies, and contract versioning. Building tier/partner governance from scratch over API Gateway would require heavy custom code; Apigee provides **API products**, **developer apps**, policies, and analytics out of the box. Still, budget for licensing, API traffic, environments/runtimes, and operational costs per current Apigee pricing.

## 9. Hardening, Operations, and Cost Control

### Least-Privilege IAM Permissions

| Identity | Typical Permissions | Avoid Granting |
|---|---|---|
| CI/CD deployer | Cloud Run deploy, Artifact Registry, API Gateway config/gateway permissions, and `iam.serviceAccounts.actAs` on exact SA | Organization-wide Owner |
| API Gateway backend SA | `roles/run.invoker` **on the exact Cloud Run service** | Cloud Run Admin / Storage Admin |
| Cloud Run runtime SA | Cloud Storage/Cloud SQL/Pub/Sub roles needed by Java | IAM Admin or default Editor |
| Client Google Cloud project | API enabled and restricted API key | Backend Invoker or runtime SA credentials |
| Apigee proxy runtime | Required policies and backend access | Broad IAM roles unrelated to the proxy |

### Input Protection and Observability

- Enforce **HTTPS**, validate JWT issuer/JWKS/audience and scopes, support key rotation, and never log API keys/JWTs.
- Cloud Run service **must not grant `roles/run.invoker` to `allUsers`**; only the API Gateway SA holds invoke permission; audit per-backend policies and CI/CD IAM changes.
- Use OpenAPI `x-google-allow: configured`, verify method/path case sensitivity, and prevent undeclared routes from bypassing auth.
- Use Secret Manager for Java secrets; never put DB credentials in OpenAPI specs, images, or `curl` history.
- Enforce quotas and load protection at the API/Cloud Run layers, bounding database connections relative to instance counts.
- Propagate trace/correlation IDs from gateway to Java, logging outcomes and latency without dumping sensitive bodies.
- Distinguish **gateway auth/quota 4xx** from **Java backend 4xx/5xx** in alerts and reports.
- Restrict IAM for API config creators and audit changes to gateways, configs, and service accounts.

### Metrics for Dashboards

| Metric | How to Use It |
|---|---|
| Gateway request count by HTTP status | Spot bad API keys, expired JWTs, and 401/403/429 spikes |
| Gateway/backend latency P50/P95/P99 | Separate delays at proxy, Cloud Run, and Cloud SQL |
| Cloud Run request count, 5xx, instances, CPU/memory | Scaling behavior and downstream bottlenecks |
| Quota exceeded / consumer usage | Track tier consumption and abused keys |
| API config/gateway state and rollout history | Catch issues when changing backend URLs, timeouts, or quota metrics |
| IAM audit and Cloud Logging | Trace Invoker changes and unexpected direct traffic |
| Billing across API Gateway/Apigee, Cloud Run, LB, network, Logs | Forecast total API cost |

**Never treat HTTP `200` alone as proof of security:** a valid JWT from another tenant might be accessing unauthorized records if Java skips authorization. Likewise, if the gateway returns `200` while Java fails a database write afterward, the system lacks proper transactional error handling.

### Cost and Reliability

An API fronted by Gateway can incur:

~~~text
API Gateway traffic / gateway-related charges
  + Cloud Run CPU/memory/request cost
  + Artifact Registry / Cloud Build
  + Cloud SQL / Cloud Storage / Pub/Sub
  + network egress, load balancer if used
  + Cloud Logging / Monitoring
~~~

With Apigee, factor in **plan/licensing**, API proxy traffic/transactions, environments/runtimes, policy types, and supporting services per contract. Never declare API Gateway or Apigee "cheaper" solely on per-million-request pricing when product management and operational needs differ.

**API Gateway can be deployed in multiple regions** by design; a single gateway in one region does not provide multi-region disaster recovery on its own. For critical systems, design multi-region gateways with supported load balancing/custom domains, multi-region Cloud Run backends, data protection, and tested failover.

## 10. Troubleshooting Runbook and Safe Rollouts

| Symptom | Primary Suspect | How to Check |
|---|---|---|
| Gateway fails to create API config | Invalid OpenAPI structure, bad backend URL, deployer lacks `actAs` on backend SA | `api-configs create` operation, `--backend-auth-service-account`, IAM |
| Gateway not active yet | API config/gateway still provisioning or unsupported region | `gateways describe`, ACTIVE state, Cloud Operations |
| Missing API key returns 401/403 | `x-api-key` omitted or key not enabled for managed service | OpenAPI `securityDefinitions`, API key restrictions, managed API enabled |
| Valid key returns 403 | API not enabled in consumer project, wrong key restrictions, or backend IAM denial | Separate gateway 403 from Cloud Run 403 via logs |
| Invalid JWT | Wrong `iss`/`aud`/`exp`, rotated JWKS, or missing Bearer header | API Gateway auth logs, OIDC issuer, `x-google-audiences` |
| `/v1/hello` returns 404 | Wrong `x-google-backend` path translation or undeclared route | OpenAPI paths/methods, backend logs, case sensitivity |
| Cloud Run returns 403 after gateway | Gateway backend SA lacks `roles/run.invoker`; wrong backend ID token audience | Cloud Run IAM, `x-google-backend.address`, API config service account |
| Backend timeout / 503 / 504 | Slow Java startup, gateway `deadline`, Cloud Run timeout, exhausted DB pool | Gateway vs. Cloud Run latency, startup time, DB connection limits |
| Quota returns 429 | Consumer project exceeded quota or burst protection | Quota metric/limit, consumer key, client backoff |
| Old gateway errors 500 after new config | Renamed/deleted API-level quota metric breaks older config's reference | Compare `x-google-management` and `x-google-quota` across configs |
| Browser reports CORS error | Preflight `OPTIONS` lacks route/auth or wrong response headers | Browser network tab, API config, and backend headers |
| Valid Apigee key rejected | API product omits route/method, developer app revoked, or misconfigured policy | Developer app/product, VerifyAPIKey flow variables, trace |

### Read-Only Investigation Commands

~~~bash
gcloud api-gateway apis describe "$API_ID" --project="$PROJECT_ID"
gcloud api-gateway api-configs describe "$CONFIG_ID" \
  --api="$API_ID" --project="$PROJECT_ID"
gcloud api-gateway gateways describe "$GATEWAY_ID" \
  --location="$REGION" --project="$PROJECT_ID"
gcloud run services get-iam-policy "$SERVICE" --region="$REGION"
gcloud run services logs read "$SERVICE" \
  --region="$REGION" --limit=50
~~~

If the Gateway blocks a request before calling the backend, Java **will have no log entry for that request**. Correlate by timestamp, gateway hostname, route, HTTP status, and trace; never start editing Java code before confirming which layer failed.

### Releasing a New API Config and Rollback

1. Review `openapi.yaml` in Git: paths, security, backend address, JWT claims, quotas, and deadline.
2. Create a **new API config ID** rather than trying to edit routing/auth on the old ID.
3. Wait for config ACTIVE; verify API key/JWT, 404 routes, and gateway-to-backend IAM using a canary gateway or compatible test workflow.
4. Switch the Gateway to the new config via `gcloud api-gateway gateways update` and monitor 4xx/5xx/P95.
5. On error, **update the gateway back to the previous valid config**; backend/IAM changes may also require separate rollback.
6. Delete old configs only when no Gateway references them; never delete a config currently active on a gateway.

## 11. Applied Scenario: Orders API for Three Partners

An enterprise has a Java API serving:

~~~text
GET  /v1/catalog/{itemId}     → public data with usage control
GET  /v1/orders/{orderId}     → sensitive data belonging to one partner
POST /v1/orders               → side-effecting order creation
~~~

Recommended design:

| Endpoint | Client Protection | Java / Backend Protection |
|---|---|---|
| `GET /v1/catalog/{itemId}` | Restricted API key + quota | Input validation, caching, read-only DB role |
| `GET /v1/orders/{orderId}` | API key **and** partner JWT | Check order tenant/ownership; return only authorized data |
| `POST /v1/orders` | API key + JWT, load limits | Validate body, idempotency key, transactions, and auditing |

The Cloud Run backend stays private via Gateway's IAM Invoker; the Java API uses a runtime service account scoped to exact Cloud SQL/Storage/Pub/Sub resources. When partners grow from 3 to 100 and require **API product tiers**, developer app approvals, self-service onboarding, and advanced policies, the team evaluates Apigee.

**Failure scenario:** partner A sends a valid JWT yet guesses partner B's `orderId`. The Gateway verifies the signature and forwards the request to Java; **Java must return `403`** because the caller lacks permission to view that order. Relying on a valid API key/JWT without checking ownership leaves a critical authorization flaw.

## 12. Pre-Publication API Checklist

- [ ] Java backend runs locally; Linux/AMD64 image and Cloud Run use the right `PORT`.
- [ ] Cloud Run does not grant `allUsers` invoke; gateway backend SA holds **only** `roles/run.invoker` on the service.
- [ ] API config creator has `iam.serviceAccounts.actAs` on the exact backend SA; deployer and runtime identities are separated.
- [ ] OpenAPI defines exact paths/methods, `x-google-allow: configured`, and `APPEND_PATH_TO_ADDRESS`.
- [ ] Managed API service is enabled; API keys are restricted to the right API and clients.
- [ ] For sensitive data, enforce JWT issuer/JWKS/audience and verify business permissions in Java.
- [ ] Do not configure **OR** security when **AND** between API key and JWT is truly required.
- [ ] Never put keys, tokens, or PII in source code, logs, or URL queries; secrets have rotation/revocation processes.
- [ ] Quotas, burst protection, Cloud Run instance/DB pool limits, and backoff client retries are in place.
- [ ] Browsers have proper CORS/preflight routes if the API is called directly from web apps.
- [ ] Monitor gateway 4xx/5xx, backend 5xx, latency, quotas, IAM changes, and cost.
- [ ] Maintain procedures for releasing new API configs, canarying, rollback, and cleaning up unused gateways/configs.
- [ ] If using Apigee, **API products, apps, and policies** are attached to flows; tested key revocation and quota enforcement.

## 13. Practice Exercises

**Exercise 1 — Security Boundary Analysis.** A client calls `GET /v1/orders/42` with a valid API key but no JWT. If the API config only requires a key, what happens? When the Java backend returns data without checking ownership, where does the vulnerability lie? Diagram the three layers: client auth, backend IAM, and business auth.

**Exercise 2 — Lab Deployment.** Write `App.java` and `Dockerfile` per section 2, test `PORT=9090`, deploy Cloud Run disallowing anonymous calls, grant the Gateway SA `roles/run.invoker`, then create the OpenAPI spec and Gateway. List the expected results of the four `curl` tests in section 5.

**Exercise 3 — JWT Protection.** Consider two configurations:

~~~yaml
# A: OR, insufficient if both are required
security:
  - api_key: []
  - google_id_token: []

# B: AND
security:
  - api_key: []
    google_id_token: []
~~~

Why does configuration B fit sensitive order routes? List the JWT claims verified by the gateway and the authorization checks Java must still perform.

**Exercise 4 — Per-Project Quota.** An API has a quota of 1,000 units/minute/project, with `GET` costing 1 and `POST` costing 5. In one minute, a partner sends 200 GETs and 100 POSTs. How many total units are consumed? How many remain? If 3 users in the same project share one key, does each user get 1,000 units?

**Exercise 5 — Debugging Errors.** Gateway calls to Cloud Run return 403 even though direct `curl` with an admin's ID token returns 200. Check the API config backend SA, Invoker role, `x-google-backend.address`, backend JWT audience, and IAM propagation before changing Java source code.

**Exercise 6 — Config Release.** Gateway A runs `config-v1` with quota metric `read-requests`. The team creates `config-v2` renaming the metric to `read-v2` and updates Gateway B. Why might Gateway A start returning 500s? Design a rollout and rollback that do not break the API's shared quota metric.

**Exercise 7 — Choosing Apigee.** An organization has 50 partners with Bronze/Gold consumption tiers, needs per-developer-app key revocation, partner-level usage analytics, and burst protection. Propose the API product, VerifyAPIKey, Quota, SpikeArrest, flow attachment, and Cloud Run target IAM design.

**Exercise 8 — Production Design.** A partner calls `POST /v1/orders` twice because the client timed out after the database already committed. Propose idempotency keys, unique constraints/transactions, timeouts, and tracing in Java; explain why API Gateway cannot prevent duplicate business writes using an API key alone.

## Official Reference Documentation

- [Getting started with API Gateway and Cloud Run](https://cloud.google.com/api-gateway/docs/get-started-cloud-run) — order of creating backend, API config, and gateway.
- [Create an API config](https://cloud.google.com/api-gateway/docs/creating-api-config) — `gcloud api-configs create`, immutability, managed service, and rollover.
- [Deploy an API to a gateway](https://cloud.google.com/api-gateway/docs/deploying-api) — `gcloud gateways create/update`, locations, and hostnames.
- [Securing backend services](https://cloud.google.com/api-gateway/docs/securing-backend-services) — IAM Invoker for Cloud Run backends.
- [Configure API Gateway development environment](https://cloud.google.com/api-gateway/docs/configure-dev-env) — `actAs` permissions and backend auth service account.
- [OpenAPI 2.0 extensions](https://cloud.google.com/api-gateway/docs/oasv2-extensions) — `x-google-backend`, path translation, `x-google-quota`, and limits.
- [Use API keys](https://cloud.google.com/api-gateway/docs/authenticate-api-keys) — creating/restricting keys and managed services.
- [Using JWT to authenticate users](https://cloud.google.com/api-gateway/docs/authenticating-users-jwt) — issuer, JWKS, audience, and `X-Apigateway-Api-Userinfo`.
- [API Gateway troubleshooting](https://cloud.google.com/api-gateway/docs/troubleshoot) — IAM, key, config, and quota metric errors.
- [API Gateway quotas and limits](https://cloud.google.com/api-gateway/docs/quotas) — API/config/gateway counts and request limits.
- [Apigee API products](https://cloud.google.com/apigee/docs/api-platform/publish/what-api-product) — developer apps, API products, and consumption policies.
- [Apigee VerifyAPIKey policy](https://cloud.google.com/apigee/docs/api-platform/reference/policies/verify-api-key-policy) — verifying developer app keys.
- [Apigee SpikeArrest policy](https://cloud.google.com/apigee/docs/api-platform/reference/policies/spike-arrest-policy) — smoothing traffic spikes.
- [Apigee JSONThreatProtection policy](https://cloud.google.com/apigee/docs/api-platform/reference/policies/json-threat-protection-policy) — bounding dangerous JSON payloads.
- [API Gateway pricing](https://cloud.google.com/api-gateway/pricing), [Apigee pricing](https://cloud.google.com/apigee/pricing), [Cloud Run pricing](https://cloud.google.com/run/pricing) — estimating end-to-end pipeline costs.
