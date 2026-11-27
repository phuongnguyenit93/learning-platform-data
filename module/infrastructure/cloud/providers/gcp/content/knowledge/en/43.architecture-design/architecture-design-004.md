# Microservices Architecture and Service-to-Service Authentication

An e-commerce application running on Google Cloud might start as a single Java/Spring Boot service. As the system grows, order management, payments, inventory, notifications, and reporting develop different change cadences and scaling requirements. Splitting them into microservices helps teams deploy independently, yet simultaneously increases inter-component connections and attack surface: which service is allowed to call which service, with what identity, under what conditions, and how should failures in a dependency be handled?

**Service-to-service authentication** is the mechanism for verifying a calling service's identity before accepting requests from another service. On Google Cloud, this model typically uses **workload identities**, service accounts, IAM, Google-signed OpenID Connect ID tokens, and in certain GKE architectures, mutual TLS (mTLS) via a service mesh. To remain secure, it must be combined with **authorization**, network protections, secret management, and observability across services.

This lesson guides you through designing microservices, implementing Cloud Run-to-Cloud Run authentication with ID tokens in Java, explaining GKE Workload Identity Federation and mTLS options, and assembling these pieces into an operable GCP architecture.

## Learning Objectives

After this lesson, you will be able to:

- Evaluate when to split into microservices and when a modular monolith makes more sense.
- Design service boundaries based on domains, data ownership, and API contracts.
- Choose synchronous HTTP/gRPC or asynchronous Pub/Sub/Cloud Tasks based on business needs.
- Distinguish authentication, authorization, network ingress, and encryption in transit.
- Configure Cloud Run IAM and Google-signed ID tokens with the proper audience to call another service.
- Write a Java caller using Application Default Credentials (ADC) and `IdTokenCredentials`.
- Understand GKE Workload Identity Federation, Kubernetes ServiceAccounts, and IAM service accounts.
- Explain mTLS, service meshes, and the limitations of each authentication approach.
- Apply least privilege, token lifecycles, retries, deadlines, tracing, and incident response.
- Build a verification checklist before opening production traffic.

## 1. From Monolith to Microservices

Microservices organize a system into small services with clear business responsibilities communicating over API contracts or events. Each service can be released and scaled relatively independently.

An ordering application might have these components:

| Service | Responsibility | Data Owned by the Service |
|---|---|---|
| Checkout | Receives purchase requests and orchestrates the flow | Checkout sessions and workflow state |
| Orders | Creates and manages the order lifecycle | Order records |
| Inventory | Checks and reserves stock | Stock, reservations |
| Payments | Calls payment providers and records status | Payment attempts and ledger references |
| Notifications | Sends emails, SMS, or push notifications | Notification preferences and delivery status |

### When do microservices deliver value?

- Teams need independent releases at different cadences.
- Certain capabilities require independent scaling.
- Business boundaries and ownership are clear.
- The system has telemetry, CI/CD, and distributed operations capability.
- Security or data requirements demand explicit privilege partitioning.

### When should you hold off on splitting?

If the team is still small, the application domain is unstable, or multiple modules always change together, a **modular monolith** may be simpler. Splitting too early leads to excessive network calls, distributed transactions, schema versioning overhead, and hard-to-diagnose incidents without commensurate benefits.

**Do not equate a microservice with a single container.** One service can run multiple instances; one container can still house multiple business modules. Service boundaries should start from domain and ownership, not merely Docker image count.

## 2. Bounded Contexts and Data Ownership

Apply Domain-Driven Design (DDD) to separate **bounded contexts**:

- Orders decides valid order statuses.
- Inventory decides stock reservation eligibility.
- Payments decides payment status.
- Notifications only needs to know what content to send, not have read access to every business table.

Each service owns the data within its domain. Other services interact via APIs or events rather than modifying each other's tables directly.

### Why avoid arbitrary shared databases?

If Checkout directly `UPDATE`s the Payments table, Payments' boundary loses meaning. A single schema change can break multiple services simultaneously, while making IAM and accountability auditing difficult.

Recommended pattern:

~~~text
             Client
                |
                v
           Checkout API
            /        \
           v          v
      Orders API   Inventory API
          |              |
          v              v
      Orders DB      Inventory DB
          |
          v
       OrderPlaced event
          |
          v
      Notification Worker
~~~

Each service does not strictly need a separate database engine or physical instance. You can share a managed platform while enforcing clear schema, credential, permission, and lifecycle boundaries. Avoid granting multiple services write access to the same business table.

### Inter-service contracts

A contract should specify:

- Endpoint, method, and version or event type.
- Request/response schemas, required fields, and backward compatibility.
- Authentication mechanism and permitted caller identities.
- Authorization at the operation, resource, and tenant levels.
- Deadlines, retries, and idempotency.
- Error semantics and behavior when a dependency is unavailable.
- Ownership, SLI/SLO, documentation, and deprecation policies.

OpenAPI, protobuf, or schema registries help verify compatibility. Contract tests complement unit/integration tests; they do not replace end-to-end business flow testing.

## 3. Choosing a Communication Model: Synchronous vs. Asynchronous

| Communication | Common GCP Technology | Best Fit When | Risks |
|---|---|---|---|
| Synchronous HTTP/REST | Cloud Run, GKE, Load Balancing | Immediate result needed, simple API | Waiting on dependencies and cascading failures |
| Synchronous/streaming gRPC | Cloud Run, GKE | Strict contracts, performance, streaming | Deadlines, connections, proxies, and debugging |
| Asynchronous Pub/Sub | Pub/Sub + Cloud Run/GKE workers | Fan-out, event-driven, decoupled processing | Eventual consistency, duplicates, ordering |
| Task queue | Cloud Tasks + HTTP workers | One-to-one task dispatch, scheduled retries | Queue backlog, deadlines, duplicates |
| Workflow orchestration | Workflows or application orchestrator | Multi-step flows, branching, and state | Complex state transitions |

### Example of choosing the right communication path

Checkout needs to know immediately at order confirmation whether stock is available: it can call Inventory synchronously with a tight deadline.

Once the order is created, the system publishes an `OrderPlaced` event to Pub/Sub for Notifications and Analytics to process independently. Do not keep the HTTP checkout request waiting for email delivery if sending email is off the critical path.

If Inventory does not respond, Checkout must enforce a clear policy: return a retryable status, place the order in pending state, or reject; never assume stock is available.

### Eventual consistency and idempotency

An event may be delivered more than once. Consumers must handle duplicates via event IDs, transaction keys, or idempotent upserts. If publishing an event after a database transaction, consider a transactional outbox to avoid committing an order while failing to publish the event.

Microservices do not automatically guarantee exactly-once execution across an entire workflow. You must design retries, deduplication, and business compensation when operations have side effects.

## 4. Authentication, Authorization, Encryption, and Ingress Are Four Distinct Layers

| Mechanism | Question | Example |
|---|---|---|
| Authentication (AuthN) | Who is calling? | Caller is service account `checkout-caller` |
| Authorization (AuthZ) | What is the caller allowed to do? | Only allowed to invoke Inventory; only allowed to read stock |
| Encryption in transit | Is data protected on the wire? | HTTPS/TLS, or mTLS within a mesh |
| Network ingress | Where is traffic allowed to reach the endpoint from? | Internal Cloud Run ingress or internal load balancer |

An HTTPS request does not mean the caller is authorized. Similarly, holding the Invoker role while blocked by network ingress still prevents access. Each layer must be configured and tested independently.

**Zero Trust** dictates never implicitly trusting a caller simply because it resides in the same VPC, namespace, or cluster. Workload identity, permissions, and access scope must be verified at the appropriate boundary.

## 5. Threat Model for Service-to-Service

Before picking mechanisms, identify assets to protect and potential attack paths.

| Threat | Scenario | Control |
|---|---|---|
| Spoofed caller | A workload sends requests using an unauthorized identity | Signed tokens, issuer/audience validation, IAM |
| Misused token for wrong target | An Inventory token is replayed against Payments | Tokens scoped with target-specific audiences |
| Shared service account | Compromising one service allows calling all services | Per-workload identity and least privilege |
| Token/secret leakage | Logs record bearer tokens or private keys | Never log secrets; use short-lived credentials |
| Lateral movement | Compromised workload calls other internal services | Per-hop AuthN/AuthZ, ingress, and network policies |
| API gateway bypass | Internal client calls privileged service directly | Enforce authorization at the receiver/service boundary |
| Confused deputy | Service uses high privileges to act on unverified user requests | Bind user, tenant, and operation permissions |
| Replay/duplicate requests | Payment retries create multiple charges | Idempotency keys and validation |
| Denial of service | Authorized caller sends excessive requests | Quotas, rate limits, concurrency, backpressure |
| Cross-environment access | Staging accidentally calls production Payments | Project/identity isolation, endpoint allowlists, and IAM |

**Caller identity does not equal end-user identity.** Checkout may authenticate as a valid service account, yet the receiver still needs to verify whether Checkout is authorized to act on behalf of that specific user or tenant.

## 6. Service Accounts and Workload Identities on Google Cloud

A service account is an identity for workloads. A Cloud Run service or VM can run under an IAM service account and use Application Default Credentials (ADC) to obtain short-lived credentials.

Permission example:

~~~text
checkout Cloud Run
  runtime identity: checkout-caller@PROJECT.iam.gserviceaccount.com
                   |
                   | Cloud Run Invoker on Inventory
                   v
inventory Cloud Run (private)
  runtime identity: inventory-runtime@PROJECT.iam.gserviceaccount.com
                   |
                   | read-only access to inventory data
                   v
Cloud SQL / Cloud Storage / other resources
~~~

### One service account per role

Do not share a single Owner service account across all services. Instead:

- Checkout has permission to invoke Inventory and publish order events if needed.
- Inventory has permission to access inventory data, with no payment permissions.
- Payments has permission to call payment providers and access required secrets.
- Notifications only has permission to read its subscription and send notifications.

Permission to invoke Inventory is granted **on the Inventory resource**, not as a project-wide Editor role for Checkout.

### Why avoid JSON service account keys?

Long-lived private keys can be copied or leaked via Git, container images, or build systems. On Cloud Run, GKE, or Compute Engine, prefer runtime identities and short-lived credentials via the metadata server or federation. Do not set `GOOGLE_APPLICATION_CREDENTIALS` pointing to a key file in production without a specially security-reviewed justification.

## 7. Cloud Run-to-Cloud Run Authentication: Overview

Suppose two services run on Cloud Run:

- **checkout**: receives HTTP requests from the frontend and needs to call Inventory.
- **inventory**: internal API requiring Cloud Run IAM authentication.

Standard flow:

~~~text
Checkout container
  |
  | ADC bound to checkout-caller service account
  v
Metadata server / Google auth library
  |
  | Google-signed OIDC ID token
  | aud = Inventory service URL
  v
HTTP Authorization: Bearer ID_TOKEN
  |
  v
Inventory Cloud Run ingress check
  |
  v
Cloud Run IAM authentication/Invoker check
  |
  v
Inventory application authorization
  |
  v
Business operation
~~~

### Three prerequisites before calling

1. **Runtime identity**: Checkout runs with its own dedicated service account.
2. **Invoker permission**: Checkout's service account is granted `roles/run.invoker` on Inventory.
3. **Valid token**: The request carries a Google-signed ID token with the correct audience, sent over HTTPS.

Additionally, if Inventory uses `internal` or `internal-and-cloud-load-balancing` ingress, the network path from Checkout must be permitted. Being in the same project does not mean every Cloud Run-to-Cloud Run call is automatically classified as internal when ingress is restricted; you may need Direct VPC egress, a connector, Private Google Access, Private Service Connect, or an internal load balancer depending on topology.

### ID tokens vs. access tokens

| Credential Type | Typical Purpose | Key Considerations |
|---|---|---|
| OAuth 2.0 access token | Calling Google Cloud APIs based on scopes/IAM | Do not arbitrarily substitute for an ID token |
| OIDC ID token | Proving caller identity to a target service | Contains an audience binding it to the target |
| API key | Identifying a project/app for certain APIs | Not privileged workload authentication |
| Service account key | Long-lived private credential | Avoid when ADC/workload identity is available |
| mTLS certificate | Mutual transport-layer authentication | May require service mesh/CA/certificate lifecycle management |

Cloud Run IAM may accept certain Google-signed OAuth tokens in documented scenarios, but **the recommended service-to-service flow is a Google-signed ID token** whose audience matches the service.

## 8. Hands-On IAM for Two Cloud Run Services

The commands below are examples to design and review before applying. Replace placeholders with actual project, region, image, and service account values. Running deployment commands can alter production.

### Step 1 – Create runtime identities

~~~bash
gcloud iam service-accounts create checkout-caller \
  --project=PROJECT_ID \
  --display-name="Checkout caller"

gcloud iam service-accounts create inventory-runtime \
  --project=PROJECT_ID \
  --display-name="Inventory runtime"
~~~

### Step 2 – Deploy Inventory requiring authentication

~~~bash
gcloud run deploy inventory \
  --project=PROJECT_ID \
  --region=REGION \
  --image=REGION-docker.pkg.dev/PROJECT_ID/services/inventory:VERSION \
  --service-account=inventory-runtime@PROJECT_ID.iam.gserviceaccount.com \
  --no-allow-unauthenticated
~~~

Disabling **unauthenticated invocation** is mandatory in this example. If using Terraform/IaC, keep this policy in code and monitor for policy drift.

### Step 3 – Grant Invoker role only on the Inventory service

~~~bash
gcloud run services add-iam-policy-binding inventory \
  --project=PROJECT_ID \
  --region=REGION \
  --member="serviceAccount:checkout-caller@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
~~~

Never grant `roles/run.invoker` to `allUsers` or `allAuthenticatedUsers` on a protected service. Nor should you grant it broadly at the project level when access is only needed on Inventory.

### Step 4 – Deploy Checkout with a dedicated identity

~~~bash
gcloud run deploy checkout \
  --project=PROJECT_ID \
  --region=REGION \
  --image=REGION-docker.pkg.dev/PROJECT_ID/services/checkout:VERSION \
  --service-account=checkout-caller@PROJECT_ID.iam.gserviceaccount.com
~~~

Checkout may have public ingress or sit behind a load balancer/API Gateway depending on architecture. Making Checkout public does not make Inventory public. Keep each service's ingress policy and IAM policy separate.

### Step 5 – Retrieve Inventory's URL

~~~bash
gcloud run services describe inventory \
  --project=PROJECT_ID \
  --region=REGION \
  --format="value(status.url)"
~~~

Suppose the returned URL is:

~~~text
https://inventory-abc123-uc.a.run.app
~~~

This value is illustrative only. With Cloud Run IAM, the default audience is **the root URL of the receiving service** or a validly configured custom audience—not a detailed path like `/v1/stock`.

## 9. ID Tokens: Audience, Headers, and Lifetime

Cloud Run accepts Google-signed ID tokens in:

~~~http
Authorization: Bearer ID_TOKEN
~~~

Or when the application needs to reserve `Authorization` for another business token:

~~~http
X-Serverless-Authorization: Bearer ID_TOKEN
~~~

If both are sent, Cloud Run prioritizes `X-Serverless-Authorization` for IAM authentication. Explicitly design how `Authorization` is handled at the application layer so workload tokens and end-user tokens do not collide.

### Choosing the audience

When calling:

~~~text
https://inventory-abc123-uc.a.run.app/v1/stock/SKU-001
~~~

the ID token should have audience:

~~~text
https://inventory-abc123-uc.a.run.app
~~~

Do not set the audience to a URL with a path or query string unless a matching custom audience is configured. Even when calling a traffic tag URL, the default audience remains the root URL of the receiving service. A custom domain is not automatically a valid audience; if a different value is needed, configure a custom audience on the receiving Cloud Run service.

Audience restricts where a token can be used; never mint unbound tokens for system-wide reuse.

### Token expiry and refresh

ID tokens typically have a short lifetime (about one hour in many metadata flows) and should not be hardcoded or cached long-term. Google authentication libraries handle token refreshes automatically as needed. If calling the metadata server directly, inspect the `exp` claim or request fresh tokens per security policy.

Never log bearer tokens, place tokens in URL query strings, or send tokens to untrusted endpoints.

## 10. Java Practice: Calling Inventory with IdTokenCredentials

The Google authentication library provides `IdTokenCredentials` and `IdTokenProvider`. The following example uses Cloud Run runtime ADC, generates a token with Inventory's URL as the audience, and attaches it to HTTP requests.

~~~java
import com.google.api.client.http.GenericUrl;
import com.google.api.client.http.HttpRequest;
import com.google.api.client.http.HttpRequestFactory;
import com.google.api.client.http.HttpResponse;
import com.google.api.client.http.javanet.NetHttpTransport;
import com.google.auth.http.HttpCredentialsAdapter;
import com.google.auth.oauth2.GoogleCredentials;
import com.google.auth.oauth2.IdTokenCredentials;
import com.google.auth.oauth2.IdTokenProvider;

import java.io.IOException;

public final class InventoryHttpCaller {
    private final HttpRequestFactory requestFactory;
    private final String inventoryServiceUrl;

    public InventoryHttpCaller(String inventoryServiceUrl) throws IOException {
        GoogleCredentials adc = GoogleCredentials.getApplicationDefault();
        if (!(adc instanceof IdTokenProvider)) {
            throw new IllegalStateException(
                "Runtime credentials cannot provide Google-signed ID tokens");
        }

        IdTokenCredentials idCredentials =
            IdTokenCredentials.newBuilder()
                .setIdTokenProvider((IdTokenProvider) adc)
                .setTargetAudience(inventoryServiceUrl)
                .build();

        this.inventoryServiceUrl = inventoryServiceUrl;
        this.requestFactory = new NetHttpTransport()
            .createRequestFactory(new HttpCredentialsAdapter(idCredentials));
    }

    public int readStockStatus(String sku) throws IOException {
        // Encode SKU into a path segment using an appropriate URL library.
        String url = inventoryServiceUrl + "/v1/stock/" + sku;
        HttpRequest request = requestFactory.buildGetRequest(new GenericUrl(url));
        request.setConnectTimeout(2000);
        request.setReadTimeout(5000);

        HttpResponse response = request.execute();
        try {
            return response.getStatusCode();
        } finally {
            response.disconnect();
        }
    }
}
~~~

This snippet illustrates **fetching an ID token for Cloud Run IAM**. In production, add URL encoding for `sku`, response body parsing, error mapping, overall deadlines, retry policies, and user/tenant authorization checks on Inventory.

### Shared Spring bean

Creating new credentials, token clients, and HTTP transports on every HTTP request wastes resources and adds latency. Create a shared caller managed by the Spring lifecycle:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class InventoryClientConfig {
    @Bean
    InventoryHttpCaller inventoryHttpCaller(
        @Value("${inventory.service-url}") String inventoryServiceUrl
    ) throws java.io.IOException {
        return new InventoryHttpCaller(inventoryServiceUrl);
    }
}
~~~

This uses the **`inventory.service-url`** property from Spring Boot configuration. In larger systems, prefer validated `@ConfigurationProperties` for passing URLs instead of scattering `@Value` annotations. Accept only HTTPS service URLs from trusted configuration. When an application calls multiple targets, each target gets its own audience.

**Local ADC often differs from runtime ADC.** Developer user credentials from `gcloud auth application-default login` may not support `IdTokenProvider`. When testing locally, use service account impersonation or a supported ID token mechanism; never create JSON keys just to make code run.

### When an end-user Authorization header is needed

If Checkout must forward a business token in `Authorization`, you can obtain the Google-signed ID token via the auth library and attach it to `X-Serverless-Authorization` for Cloud Run IAM verification, leaving `Authorization` for application authentication. Do not assume both headers are populated automatically when using `HttpCredentialsAdapter` alone; using both requires an intentionally configured HTTP client or interceptor.

## 11. Manual Testing via the Metadata Server

On Cloud Run runtime, you can fetch an ID token from the metadata server via the identity endpoint (this does not work identically on a local machine):

~~~bash
curl -fsS \
  -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=TARGET_SERVICE_URL"
~~~

`TARGET_SERVICE_URL` must be properly URL-encoded in the query string when needed. The command outputs a sensitive token: **never paste the output into tickets, logs, or chat**. For automated tests, use Google auth libraries and restrict logging instead of printing tokens to a terminal.

Test requirements should verify at least:

1. Checkout with the right identity and audience calls Inventory successfully.
2. A caller without `roles/run.invoker` is rejected.
3. A token with another service's audience is rejected.
4. A request without a token is rejected when IAM auth is enabled.
5. Disallowed network ingress is blocked even if the caller holds the IAM role.
6. Inventory denies access to another tenant's stock even when the caller is an authorized service.

## 12. Ingress Restriction and IAM Are Two Independent Layers

Cloud Run offers ingress options such as:

- **All**: endpoint can be called from the Internet; IAM authentication can still protect it.
- **Internal**: restricts callers to sources recognized as internal by Cloud Run rules.
- **Internal and Cloud Load Balancing**: allows paths through configured load balancers.

**Do not confuse internal ingress with `roles/run.invoker`.** Ingress controls whether traffic can reach the endpoint; IAM controls whether an identity is permitted to invoke the service.

### Cloud Run-to-Cloud Run with internal ingress

If Inventory has internal ingress and Checkout is another Cloud Run service, calling the URL directly is not always classified as internal. Depending on network configuration, you may need:

- Direct VPC egress or a Serverless VPC Access connector from the caller.
- Routing traffic through a VPC recognized by Cloud Run as internal.
- Private Google Access and appropriate DNS/endpoints.
- Or Private Service Connect / an internal Application Load Balancer if required by the architecture.

Verify the topology in current Cloud Run private networking documentation. In some cases, requiring IAM authentication alone may satisfy the threat model and be simpler to deploy; choose internal ingress when a strict network boundary is required and the flow has been tested.

### Using the right URL alone does not prove private networking

Calling a `run.app` URL over HTTPS does not by itself prove traffic traverses a private VPC. Network controls, VPC Service Controls, ingress settings, load balancers, and logging must be verified for the specific architecture.

## 13. GKE Workload Identity Federation: Identity for Pods

GKE uses Kubernetes ServiceAccounts (KSAs) to represent workloads inside a cluster. **Workload Identity Federation for GKE** lets a workload's principal call Google Cloud APIs without managing static JSON keys.

High-level flow:

~~~text
Pod with Kubernetes ServiceAccount
          |
          v
Kubernetes projected service account token
          |
          v
GKE metadata server
          |
          v
Security Token Service / federation
          |
          v
IAM principal or IAM service account impersonation
          |
          v
Google Cloud API / service
~~~

Enabling Workload Identity Federation does not automatically grant IAM permissions. Specific roles must be granted on target resources.

### Two permission models

**Direct resource access**: the GCP resource's IAM policy grants permissions directly to the KSA/namespace principal within the workload identity pool. Suitable when the Google Cloud API supports it directly and you want to skip the impersonation step.

**IAM service account impersonation**: the KSA is allowed to impersonate an IAM service account, and that IAM service account holds the required permissions. Use when an API or flow requires a service account identity in a form not yet fully supported by direct federation, after reviewing current limitations.

### Example: KSA and IAM service account binding

Create a KSA:

~~~bash
kubectl create namespace checkout
kubectl create serviceaccount checkout-ksa --namespace checkout
~~~

Allow the KSA to impersonate the IAM service account on a GKE project with Workload Identity enabled:

~~~bash
gcloud iam service-accounts add-iam-policy-binding \
  checkout-caller@PROJECT_ID.iam.gserviceaccount.com \
  --project=PROJECT_ID \
  --role=roles/iam.workloadIdentityUser \
  --member="serviceAccount:PROJECT_ID.svc.id.goog[checkout/checkout-ksa]"
~~~

Add the annotation:

~~~bash
kubectl annotate serviceaccount checkout-ksa \
  --namespace checkout \
  iam.gke.io/gcp-service-account=checkout-caller@PROJECT_ID.iam.gserviceaccount.com
~~~

In the Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout
  namespace: checkout
spec:
  replicas: 2
  selector:
    matchLabels:
      app: checkout
  template:
    metadata:
      labels:
        app: checkout
    spec:
      serviceAccountName: checkout-ksa
      containers:
        - name: checkout
          image: REGION-docker.pkg.dev/PROJECT_ID/apps/checkout@sha256:IMAGE_DIGEST
          ports:
            - containerPort: 8080
~~~

This example requires the cluster/node pool to support the GKE metadata server and proper Workload Identity setup. Avoid mixing the namespace's default KSA with dedicated KSAs if you want clear privilege boundaries.

### Calling Cloud Run from GKE

To invoke an IAM-protected Cloud Run service:

1. Identify the workload identity or service account acting as caller.
2. Grant `roles/run.invoker` to that identity on the receiving Cloud Run service.
3. Obtain a Google-signed ID token with the matching audience via a mechanism supported by that credential flow.
4. Send the request over HTTPS and verify network ingress.

**Do not assume an access token from Workload Identity Federation is automatically an ID token for calling Cloud Run.** When the Java library needs `IdTokenProvider`, confirm the actual credentials support ID token generation; if needed, use IAM service account impersonation or an authorized ID token creation API with proper permissions. Test the flow on the cluster rather than assuming from KSA configuration docs alone.

## 14. Mutual TLS (mTLS) and Cloud Service Mesh

Standard TLS lets the client verify the server and protects data in transit. **mTLS** requires both client and server to present certificates, enabling mutual workload identity authentication at the transport layer.

Cloud Service Mesh can provide identity, mTLS, authorization, and telemetry mechanisms for service-to-service traffic in supported models.

| Aspect | Cloud Run IAM + ID token | Service mesh mTLS |
|---|---|---|
| Identity | Caller's Google-signed ID token | Identity bound to the workload certificate |
| Where verified | Cloud Run platform before entering the container | Proxy/mesh data plane |
| Audience | Yes, for the target service | Does not use the same OIDC `aud` mechanism |
| Policy | Cloud Run Invoker + application AuthZ | Mesh AuthorizationPolicy + application AuthZ |
| Certificate lifecycle | App does not manage certs for IAM | Mesh/CA manages issuance and rotation |
| Best fit | Cloud Run service-to-service | GKE and supported mesh architectures |

These models are not mutually exclusive. A multi-platform system can use Cloud Run IAM at serverless boundaries and mesh mTLS among services inside GKE.

### Example mTLS policy in an Istio-compatible mesh

If the `inventory` namespace is onboarded to the mesh, an illustrative policy:

~~~yaml
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: inventory-strict-mtls
  namespace: inventory
spec:
  mtls:
    mode: STRICT
~~~

An illustrative authorization policy:

~~~yaml
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: allow-checkout-to-inventory
  namespace: inventory
spec:
  selector:
    matchLabels:
      app: inventory
  action: ALLOW
  rules:
    - from:
        - source:
            principals:
              - "cluster.local/ns/checkout/sa/checkout-ksa"
      to:
        - operation:
            methods: ["GET"]
            paths: ["/v1/stock/*"]
~~~

These examples apply only when the mesh/CRD version and deployment mode support these fields. Trust domains and principal formats may vary; verify against actual configuration. Applying a `STRICT` policy to workloads lacking a mesh identity can drop traffic. Test in staging and roll out per namespace.

**mTLS authenticates workloads, not end-user privileges.** Inventory must still check authorization at the SKU, order, or tenant level as required by business logic.

## 15. Pub/Sub Push and Cloud Tasks: Asynchronous HTTP Authentication

Not every service-to-service call is an active HTTP request initiated by a container. With a Pub/Sub push subscription or a Cloud Tasks HTTP task, an intermediary service sends the request to a worker.

### Pub/Sub push with OIDC authentication

A pattern:

~~~text
Orders -> Publish OrderPlaced -> Pub/Sub subscription
                                     |
                                     | authenticated push
                                     | OIDC ID token of push SA
                                     v
                              Notifications Cloud Run
~~~

To protect Notifications:

- Create or select a service account for push authentication.
- Grant `roles/run.invoker` to that service account on the receiving Cloud Run service.
- Configure the push subscription to use that service account and the appropriate audience.
- Verify permissions so the Pub/Sub service agent can mint tokens on behalf of the push service account per documentation.
- Do not open public unauthenticated invocation just to make push work.

Pub/Sub can redeliver messages. Handlers must be idempotent and return success status only after durable processing per the subscription contract.

### Cloud Tasks HTTP targets with OIDC

Cloud Tasks supports attaching OIDC tokens to HTTP tasks targeting Cloud Run. The service account used to issue tokens must be authorized to invoke the receiving service; the principal creating the task needs permission to use that service account per Cloud Tasks rules.

Do not substitute an access token for an OIDC token when targeting an IAM-protected Cloud Run HTTP service, unless a specific documented flow supports and has been tested for it.

### Async does not eliminate authorization

A valid message arriving via Pub/Sub does not guarantee every action inside its payload is permitted. Consumers must still validate schemas, sources, tenants, idempotency, and business rules. Never allow message producers to self-assign elevated privileges by putting `role=admin` in a payload.

## 16. Organizing Service-to-Service Authorization by Business Capabilities

The IAM Invoker role generally determines **who may call a service endpoint**. It does not inherently know whether the caller should only view stock or also adjust stock.

For example, Inventory has:

~~~text
GET  /v1/stock/{sku}
POST /v1/reservations
POST /v1/stock-adjustments
~~~

If Checkout needs the first two endpoints, it should not by default receive business permission to adjust stock.

### Two-layer policy

1. **Platform authorization**: Cloud Run IAM ensures the caller is a valid identity with invoke permission.
2. **Application authorization**: Inventory checks the operation, tenant, resource, and behavior against business policies.

You can split sensitive APIs into a separate service so IAM boundaries stay narrow, or add policy enforcement in the application, service mesh, or a designed gateway. Relying solely on a self-declared `X-Caller-Name` header is insecure.

### Propagating end-user identity properly

If a user logs into the frontend and Checkout calls Orders:

- Checkout authenticates and authorizes the user for the checkout action.
- Orders may need user context to verify tenant/ownership.
- User context should be passed via a token with a valid issuer, signature, audience, expiry, and claims, or via an explicitly designed delegation mechanism.
- Do not simply pass `X-User-Id` and blindly trust the caller in all scenarios.
- Do not forward a user's access token to a service that is not its intended audience.

When using two token layers, distinguish the workload token securing the hop from the end-user token/business context used for authorization. Ensure privileged tokens are never written to logs.

## 17. Resilience: Deadlines, Retries, and Failure Isolation

Microservices increase remote calls. One HTTP request might traverse Checkout, Inventory, and Payments; if every hop sets a 10-second timeout, total latency can blow past user SLOs.

### Deadline budgets

Example checkout latency SLO under 2 seconds:

| Component | Reference Budget |
|---|---|
| API gateway and Checkout validation | 200 ms |
| Inventory reservation | 400 ms |
| Payment authorization | 700 ms |
| DB commit and response | 300 ms |
| Network/retry headroom | 400 ms |

This table is illustrative and must be measured on real traffic. Steps can run in parallel or sequentially; compute budgets along the critical path rather than mechanically summing them.

### Bounded retries

- Retry only allowed transient errors.
- Use exponential backoff and jitter.
- Cap retry counts and overall deadlines.
- Use idempotency keys for order creation, stock reservation, and payments.
- Avoid simultaneous retries across every layer, which causes **retry amplification**.
- Apply circuit breakers, bulkheads, and concurrency limits when downstream services degrade.

### Graceful degradation

If Notifications fails, Checkout can still complete the order and emit an event for later retry. If Payments fails, do not record the order as paid. Every dependency needs an explicit decision on whether it sits on the critical path.

## 18. Observability Across Microservices

A 503 error at Checkout does not immediately reveal whether Inventory timed out, an IAM token was invalid, or the payment provider errored. Signals must correlate across multiple hops.

| Telemetry | Information to Capture |
|---|---|
| Metrics | Request rate, p95/p99 latency, error rate, saturation per service/dependency |
| Traces | Trace/span IDs across Checkout -> Inventory -> Payments |
| Logs | Structured logs with trace ID, service name, revision, and error category |
| Audit logs | IAM changes, deploys, policy updates, and key admin actions |
| SLOs | User-journey availability/latency, not just VM/Pod health |
| Security events | 401/403 responses, principals, audience mismatches, policy denials |

Use appropriate OpenTelemetry instrumentation for Java/Spring Boot and your chosen observability backend. Avoid labels containing user IDs or tokens due to cardinality, privacy, and cost.

### Distinguishing authentication errors

| Symptom | Possible Cause | How to Investigate |
|---|---|---|
| 401 / unauthenticated | Missing token, expired token, or invalid signature/audience | Check token minting, audience, and request headers |
| 403 / permission denied | Identity has a token but lacks invoke permission, or another policy denies it | Check IAM policy on receiving service, service account, and ingress |
| Connection timeout | Routing/VPC, DNS, firewall, or unresponsive upstream | Check network path, ingress, and latency |
| 404 or service unavailable | Wrong URL, route, revision, or HTTP method | Check endpoints, deployments, and logs |
| 429 / resource exhausted | Quotas, concurrency, or rate limits | Check metrics and retry budgets |

Error codes may vary by API or proxy. Never rely solely on HTTP status to infer root cause; cross-check platform logs, application logs, audit logs, and networking.

### Never log tokens

When debugging authentication, log only safe metadata such as service name, request ID, expected audience, exception type, token expiry **without the token value**, and platform-verified identity if available. Never dump `Authorization` or `X-Serverless-Authorization`.

## 19. CI/CD, IAM as Code, and Safe Deployment

Manage service accounts, Cloud Run IAM bindings, ingress settings, and deployment configs via Terraform or reviewed IaC. Do not run tests as Owner while running production with a restricted service account without equivalent testing.

A reliable deployment pipeline:

~~~text
Commit
  |
  v
Build + unit tests + contract tests
  |
  v
Security scan + provenance + image digest
  |
  v
Provision/verify IAM + target configuration
  |
  v
Deploy staging with service identities
  |
  v
Negative auth tests + functional integration tests
  |
  v
Canary production + SLO checks
  |
  v
Promotion or rollback
~~~

### Separating build identity and runtime identity

The build service account needs only permissions to build/push artifacts and deploy within its granted scope. The runtime service account needs only permissions to call dependent services or access required data. Never run production containers under a CI/CD administrator service account.

### Release policies

- Every IAM change must be reviewed.
- Avoid granting project-wide wildcards when only a single service needs access.
- Enable auditing and alerts on policy changes.
- Regression-test service-to-service auth after changing URLs or custom audiences.
- When rotating/revoking a service account, assess impact on callers.
- Use canaries and rollbacks to limit blast radius when token/auth configurations change.

## 20. Real-World Scenario: Checkout Calling Inventory and Payments

A company deploys:

- Frontend behind an external Application Load Balancer or API Gateway.
- Checkout running on Cloud Run, receiving user requests.
- Inventory running on Cloud Run, IAM-protected.
- Payments running on Cloud Run or GKE, with IAM/mTLS protection per runtime.
- Order events sent via Pub/Sub to Notifications.
- Each service has its own identity and data store.

### Step 1 – Define security boundaries

| Component | Calls | Required Permissions |
|---|---|---|
| Frontend | Checkout | End-user auth and checkout business flow |
| Checkout SA | Inventory | Cloud Run Invoker on Inventory |
| Checkout SA | Payments | Invoke only approved payment endpoints |
| Orders SA | Pub/Sub topic | Publisher on the specific topic |
| Pub/Sub push SA | Notifications | Invoker on Notifications |
| Inventory runtime SA | Inventory DB | Access only to inventory data |
| Payments runtime SA | Payment secrets | Secret Manager Accessor for specific secrets |

Never create a single Owner role for all services.

### Step 2 – Design the request flow

~~~text
User
  |
  v
Checkout (user auth + business validation)
  |
  +-- [OIDC ID token aud=Inventory URL] --> Inventory
  |
  +-- [OIDC ID token aud=Payments URL] --> Payments
  |
  v
Commit order / outbox event
  |
  v
Pub/Sub -> Notifications (authenticated push)
~~~

Each downstream target has a distinct audience. An Inventory ID token is never reused for Payments.

### Step 3 – Negative tests

- Call Inventory with Notifications' service account: must be blocked if not granted Invoker.
- Call Inventory with a token carrying Payments' audience: must be rejected.
- Call Payments for an order belonging to another tenant: must be blocked by business authorization.
- Attempt a Pub/Sub push without the authorized identity: must be rejected.
- Send timed-out requests or duplicate events: must be handled per deadline/idempotency policy.
- Verify logs contain no bearer tokens.

### Step 4 – Reliability checks

- Inventory timeout: Checkout returns a safe status without recording a bogus stock reservation.
- Payments timeout: transaction carries an idempotency key and a pending-verification status if needed.
- Pub/Sub redelivery: Notifications does not send duplicates outside acceptable rules.
- Scale-out: service accounts, connection pools, and downstream quotas support the max Cloud Run instances.
- Revision rollout: IAM, audience, and ingress continue working on new revisions.

### Step 5 – Operations and incident response

Maintain a runbook for sudden spikes in authentication failures:

1. Identify the receiving service and actual caller identity.
2. Check recent IAM/ingress, service account, and deployment changes.
3. Inspect token audience, expiry, issuer, and header names.
4. Check network connectivity if ingress is internal.
5. Roll back configuration or revisions when evidence links the failure to a recent change.
6. Verify SLOs, security logs, and negative tests after recovery.

Never fix a 403 error in production by granting `allUsers` Invoker or temporarily disabling IAM checks.

## 21. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Sharing one service account across all services | Compromise of one service grants broad access | Per-workload identity and least privilege |
| Using API keys for internal authentication | Fails to bind workload/permissions properly | Google-signed ID tokens or appropriate mTLS |
| Using OAuth access tokens like OIDC ID tokens | Wrong audience/validation flow | Use Google auth library ID tokens for Cloud Run |
| Using a URL with a path as the default audience | Token rejected | Use the receiving service's root URL |
| Calling a traffic tag and passing tag URL as audience | Audience mismatch | Still use the root service URL or custom audience |
| Assuming Cloud Run in the same project is internal by default | Internal ingress rejects requests | Check VPC routing per documentation |
| Enabling HTTPS only and skipping IAM | Any caller can hit the endpoint | Require authentication and grant specific Invokers |
| Enabling IAM only and skipping business authorization | Authorized service invokes disallowed actions | Check operation, resource, and tenant |
| Bundling JSON keys inside images | Risk of leaking long-lived credentials | Runtime identity/ADC/federation |
| Forwarding end-user tokens to every downstream service | Token leakage or audience mismatch | Delegation and token separation |
| Mesh mTLS without authorization policies | Any workload in the mesh can call too broadly | Enforce workload-level authorization |
| Retrying all 401/403 errors | Amplifies load and masks config bugs | Classify errors; do not retry deterministic auth errors |
| Skipping negative auth tests | Misconfigured policies slip into production | Test missing tokens/wrong roles/wrong audiences |
| Logging `Authorization` headers | Exposes bearer credentials | Redaction and structured logging |

## 22. Production Deployment Checklist

### Architecture Design

- [ ] Service boundaries are grounded in clear bounded contexts.
- [ ] Each service has an owner, API/event contract, and SLO.
- [ ] Data and write permissions are partitioned per service.
- [ ] Synchronous/asynchronous paths and retry semantics are defined.
- [ ] Eventual consistency, idempotency, and failure modes are evaluated.

### Identity and Security

- [ ] Each workload has its own identity; no long-lived JSON keys when ADC is available.
- [ ] Callers hold the exact Invoker role on the receiving Cloud Run service.
- [ ] ID tokens are Google-signed with the audience matching the receiving service.
- [ ] Application does not log tokens and handles token refreshes.
- [ ] Network ingress is configured and tested independently of IAM.
- [ ] GKE workloads use Workload Identity Federation with scoped permissions.
- [ ] If using a mesh, mTLS and `AuthorizationPolicy` roll out safely.
- [ ] Receivers enforce business authorization per operation/resource/tenant.
- [ ] Secrets use Secret Manager with least-privilege IAM permissions.
- [ ] Negative tests cover missing/invalid tokens, audiences, and identities.

### Operations and Release

- [ ] Timeouts, retries, backpressure, and circuit breakers fit each dependency.
- [ ] Distributed tracing/correlation IDs and per-hop metrics are active.
- [ ] Audit logs capture critical IAM/policy changes.
- [ ] Service accounts and IAM policies live in reviewed IaC.
- [ ] Build identity and runtime identity are separated.
- [ ] Canaries verify both functionality and authentication/authorization.
- [ ] Runbooks exist for 401/403 errors, token issuance, routing, and mesh policies.
- [ ] Rollback plans exist for ingress, identity, or audience changes.
- [ ] Never widen permissions temporarily to patch production outages without review and approval.

## Conclusion

Microservices architecture on Google Cloud is not merely splitting a monolith into multiple containers. Its value lies in business boundaries, data ownership, communication contracts, and independent operability. When services call one another, design **workload identities, authentication, access permissions, and network controls** for every hop. On Cloud Run, the standard pattern pairs dedicated service accounts, the Invoker role, and Google-signed OIDC ID tokens with the right audience; on GKE, Workload Identity Federation and mTLS/service mesh are appropriate options depending on goals. Combining these with application-level authorization, observability, deadlines, idempotency, and controlled CI/CD yields a system that both scales cleanly and reduces unauthorized access risk.

## References

- [Cloud Run: Authenticating service-to-service](https://docs.cloud.google.com/run/docs/authenticating/service-to-service)
- [Cloud Run: Java service-to-service authentication sample](https://docs.cloud.google.com/run/docs/samples/cloudrun-service-to-service-auth)
- [Cloud Run: Configure custom audiences](https://docs.cloud.google.com/run/docs/configuring/custom-audiences)
- [Cloud Run: Security overview](https://docs.cloud.google.com/run/docs/securing/security)
- [Cloud Run: Ingress restrictions](https://docs.cloud.google.com/run/docs/securing/ingress)
- [Cloud Run: Private networking](https://docs.cloud.google.com/run/docs/securing/private-networking)
- [Google Cloud: Workload identities](https://docs.cloud.google.com/iam/docs/workload-identities)
- [GKE: Workload Identity Federation overview](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/workload-identity)
- [GKE: Configure Workload Identity Federation](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-identity)
- [Java: IdTokenCredentials reference](https://docs.cloud.google.com/java/docs/reference/google-auth-library/latest/com.google.auth.oauth2.IdTokenCredentials)
- [Google Cloud: Get an ID token](https://docs.cloud.google.com/docs/authentication/get-id-token)
- [Cloud Service Mesh documentation](https://docs.cloud.google.com/service-mesh/docs)
- [Cloud Tasks: Authenticate HTTP target tasks](https://docs.cloud.google.com/tasks/docs/creating-http-target-tasks)
- [Pub/Sub: Authenticate push subscriptions](https://docs.cloud.google.com/pubsub/docs/authenticate-push-subscriptions)
- [Google Cloud Architecture Framework: Security](https://docs.cloud.google.com/architecture/framework/security)
