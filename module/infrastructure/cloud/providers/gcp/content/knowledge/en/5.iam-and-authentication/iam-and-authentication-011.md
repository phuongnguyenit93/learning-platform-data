# OAuth 2.0, access tokens, and ID tokens when calling GCP services

> **Chapter:** IAM and authentication  
> **Module:** **CLOUD_PROVIDERS_GCP** — Explore Google Cloud from project organization, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners practice selecting services, protecting resources, automating releases, and monitoring reliability and cost.

When a Java application needs to read an object in Cloud Storage, publish a message to Pub/Sub, or call an internal Cloud Run service, it must prove **who is calling**, and the receiving service must verify **what the caller is allowed to do**. Two token types that are easily confused are the **OAuth 2.0 access token** and the **OpenID Connect (OIDC) ID token**. Both can be sent in an **Authorization: Bearer ...** HTTP header, yet **their purposes, retrieval flows, and intended targets differ**.

This lesson explains these concepts and guides token selection for real-world Google Cloud scenarios. The core principle throughout is: **fetch the right token type for the target service, use a least-privileged identity, keep tokens short-lived, and never place secrets in source code or logs**.

## Learning objectives

After this lesson, learners can:

1. Distinguish **authentication**, **authorization**, **OAuth 2.0**, **OIDC**, and **IAM**.
2. Explain key attributes of access tokens and ID tokens, including **scope**, **audience (aud)**, **issuer (iss)**, and **expiration (exp)**.
3. Choose an **access token** when calling Google Cloud APIs and an **ID token** when calling services requiring OIDC ID tokens, especially authenticated Cloud Run services.
4. Understand the roles of **Application Default Credentials (ADC)**, user accounts, service accounts, the metadata server, service account impersonation, and Workload Identity Federation.
5. Practice authenticating from **gcloud CLI**, **cURL**, and **Java**, while avoiding long-lived service account keys when safer options exist.
6. Diagnose HTTP 401/403 errors involving tokens, audiences, scopes, IAM, and target service settings.

## 1. Authentication, authorization, and the service-calling model

These three concepts are related yet distinct:

- **Authentication:** identifies the human or workload sending a request, such as a service account running on Cloud Run.
- **Authorization:** checks whether the authenticated identity has permission to perform a specific action, such as reading an object or invoking a private endpoint.
- **IAM (Identity and Access Management):** the system managing role/permission policies across many Google Cloud resources. Principals, roles, resources, and policy conditions determine whether access is granted or denied.

For example, a Google-authenticated service account is not automatically allowed to read every bucket. The service still evaluates permissions such as **storage.objects.get** on the target resource according to IAM and related conditions.

~~~mermaid
sequenceDiagram
    participant C as Client / Workload
    participant I as Google identity/token service
    participant API as Google Cloud API
    C->>I: Request token with trusted identity
    I-->>C: Short-lived token
    C->>API: Authorization: Bearer TOKEN
    API->>API: Validate token and principal
    API->>API: Check corresponding permissions/scopes/policies
    API-->>C: Result or access error
~~~

**Holding a valid token does not guarantee access.** A token proves identity, while the access decision also depends on IAM, policies, API enablement, resource scope, networking, or the target application.

### 1.1. Common principals and components in Google Cloud

| Principal / component | Example | Role in access |
|---|---|---|
| **User account** | Employee signed into Google Cloud CLI | Represents the human user and permissions granted to them |
| **Service account** | checkout-runtime@PROJECT_ID.iam.gserviceaccount.com | Identity of a workload, pipeline, or integration |
| **Workload identity / federated principal** | Workloads from GKE, GitHub Actions, or environments outside Google Cloud | Uses federated identity to obtain access without long-lived keys |
| **Resource server** | Cloud Storage API, Pub/Sub API, Cloud Run | Receives requests and evaluates tokens alongside access policies |
| **Token issuer / authorization server** | Google service issuing access tokens or ID tokens | Issues tokens when authentication flows satisfy requirements |

Before writing code, specify: **who is calling, which endpoint is called, which token type it accepts, which audience/scope applies, and which IAM permissions must be granted?**

## 2. OAuth 2.0 and OpenID Connect solve two different problems

**OAuth 2.0** is an authorization framework: a client can obtain an **access token** to access resources/APIs within granted permissions, either on behalf of a user or a workload depending on the flow. OAuth 2.0 defines roles such as resource owner, client, authorization server, and resource server, along with multiple grant flows.

**OpenID Connect (OIDC)** adds an identity authentication layer on top of OAuth 2.0; a core artifact is the **ID token**, typically a signed JWT containing claims about the subject and target application/service. The ID token lets the recipient verify identity in a way designed specifically for that scenario.

| Question | OAuth 2.0 | OpenID Connect |
|---|---|---|
| Primary goal | Grant a client access to resources/APIs | Authenticate identity and provide session/subject claims |
| Typical token | Access token | ID token, often alongside an access token in OIDC flows |
| Recipient | Resource server / API accepting that token | Relying party / service named in the **aud** claim |
| Key checks | Scopes and permission checks at the API; plus IAM in Google Cloud | Signature, issuer, audience, expiration, and related claims/checks |
| Common mistake | Thinking having a scope bypasses IAM | Sending an ID token instead of an access token to call Google Cloud REST APIs |

**“OAuth token” is too vague.** When calling an API, always specify whether you need an **access token** or an **ID token**. An OIDC flow can issue both, yet they are not interchangeable.

### 2.1. “Bearer token” is only how the token is carried

Common HTTP header:

~~~http
GET /resource HTTP/1.1
Host: example.googleapis.com
Authorization: Bearer TOKEN_VALUE
~~~

The word **Bearer** means whoever holds the token can present it as a bearer credential. It does not indicate whether the token is an access token, an ID token, or another type. Because a leaked bearer token can be replayed, protect it like a temporary credential:

- Always use HTTPS to external endpoints.
- Never write tokens into logs, tickets, screenshots, or error trackers.
- Never pass tokens in URLs/query strings when headers can be used.
- Avoid storing tokens where other users or processes can read them.
- Let libraries or proper credential sources handle refreshes and expiration.

## 3. Access tokens: standard for calling Google Cloud APIs

**Access tokens** authorize calls to Google APIs, such as:

- **Cloud Resource Manager API:** reading project metadata.
- **Cloud Storage JSON API:** reading metadata or objects, if the caller has permission.
- **Pub/Sub API:** publishing or pulling messages per granted permissions.
- **Secret Manager API:** accessing secret versions per granted permissions.
- **Compute Engine API:** reading/modifying VMs per IAM, scopes, and applicable constraints.

An access token can represent a **user**, a **service account**, or a supported **federated principal**. Google issues multiple access token formats; **do not assume every access token is a dot-delimited JWT you can decode**, or that all share the same length and lifetime. Clients should treat access tokens as opaque strings unless specific token docs say otherwise.

### 3.1. How do scopes and IAM relate?

**OAuth scopes** restrict the kinds of API access a token can request; a common Google Cloud scope is:

~~~text
https://www.googleapis.com/auth/cloud-platform
~~~

The **cloud-platform** scope permits a token to be used across many Google Cloud APIs from a scope perspective, yet **does not grant any IAM role on its own**. A service account with a broad scope lacking **storage.objects.get** on a bucket still cannot read that object. Conversely, a service account with the right role whose token is restricted to a scope not accepted by the target API can still be rejected.

In some Compute Engine/GKE environments, workload **access scopes** can also constrain access tokens. Modern designs enforce permissions with **least-privilege IAM** and pair them with API-appropriate scopes, rather than treating scopes as the primary security boundary.

~~~mermaid
flowchart LR
    T["Valid access token"] --> S{"Scope matches?"}
    S -- "No" --> E1["API denies"]
    S -- "Yes" --> I{"Principal has IAM permission?"}
    I -- "No" --> E2["API denies"]
    I -- "Yes" --> P{"Other conditions, policies, and API checks?"}
    P -- "Not satisfied" --> E3["Denied"]
    P -- "Satisfied" --> OK["Operation permitted"]
~~~

This diagram is a conceptual model: exact ordering and error codes are determined by each API.

### 3.2. Example calling Cloud Resource Manager REST API with an access token

On a dev machine with Google Cloud CLI installed and authenticated as an authorized account:

~~~bash
# Verify CLI account and configured project without exposing tokens.
gcloud auth list
gcloud config list project

# PROJECT_ID is an authorized project you can view.
PROJECT_ID="my-learning-project"

# Access token belongs to the identity signed into gcloud CLI.
# Do not enable shell tracing (-x) and do not print the token.
ACCESS_TOKEN="$(gcloud auth print-access-token)"

curl --fail-with-body --silent --show-error \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  "https://cloudresourcemanager.googleapis.com/v3/projects/$PROJECT_ID"

# Unset temporary shell variable when done.
unset ACCESS_TOKEN
~~~

Requirements: Cloud Resource Manager API is enabled/available, the account holds **resourcemanager.projects.get** on the project, and environmental constraints are met. If permissions are missing, the token may still be valid while the API rejects the request.

**Note:** the access token from the command above targets **Google APIs** and is not a valid ID token for calling a Cloud Run service requiring OIDC authentication.

### 3.3. Expiration and refreshing access tokens

Access tokens are short-lived (many flows are about one hour; exact limits depend on token type and issuer). Long-running apps must:

1. Obtain tokens from an authentication library or trusted credential source.
2. Track expiration or let the library handle refresh timing.
3. Request fresh tokens as needed rather than pinning a static value in an environment variable long-term.
4. Avoid logging out or modifying a workload's credential files mid-execution without understanding the impact.

A **refresh token** is a different credential used in certain user OAuth flows to obtain new access tokens. It carries strict protection requirements; **never equate refresh tokens with access tokens**. Workloads running with an attached service account on Google Cloud normally obtain short-lived tokens from platform infrastructure without managing user refresh tokens.

## 4. ID tokens: proving identity to a specific target service

**ID tokens** in OpenID Connect flows are typically signed **JWTs**. Their payload holds claims. Illustrative example (fields omitted, not a real token):

~~~json
{
  "iss": "https://accounts.google.com",
  "sub": "109876543210987654321",
  "aud": "https://orders-api-abcdef-uc.a.run.app",
  "iat": 1790000000,
  "exp": 1790003600,
  "email": "caller@my-learning-project.iam.gserviceaccount.com"
}
~~~

Notable claims:

| Claim | Meaning | How it is used |
|---|---|---|
| **iss** | Issuer that minted the token | Checked against valid issuers supported by the service |
| **sub** | Stable identifier of the principal within the issuer's namespace | Useful to identify the subject; do not rely solely on email for identity |
| **aud** | Audience — target service/application | Must match the expected service audience, or a supported configured custom audience |
| **iat** | Issued-at timestamp | Supports time-validity checks |
| **exp** | Expiration timestamp | Reject expired tokens; account for allowed clock skew |
| **email / email_verified** | Present depending on token type and issuer | Not included in every ID token; never rely on email alone for authorization |

This is a **conceptual payload sample**, not a complete JWT schema or a guarantee that every ID token carries identical issuers/claims. User login ID tokens use the **OAuth client ID** as audience, whereas Google-signed ID tokens calling Cloud Run can use the **service URL** as audience. Always clarify issuer and recipient.

### 4.1. Purpose of audience

Audience answers: **“Which service was this token issued for?”** For example, the same service account calls two internal APIs:

~~~text
Cloud Run service A: https://orders-api-abcdef-uc.a.run.app
Cloud Run service B: https://billing-api-abcdef-uc.a.run.app
~~~

An ID token minted for audience A **must not be accepted by service B** as a token meant for B. Audience validation prevents tokens issued for one system from being replayed against another.

When calling an authenticated Cloud Run service, **aud** is normally the receiving service's root URL (`run.app` URL) or a **custom audience** configured on Cloud Run. Do not include paths, query parameters, or traffic-tag URLs in the default audience. When calling via a custom domain, **do not assume the custom domain itself works as the audience**; configure a custom audience when appropriate.

### 4.2. Verifying ID token signatures

Splitting a JWT into three parts and Base64URL-decoding the payload **does not verify its signature**. Any service validating ID tokens itself must use a trusted OIDC/JWT library to check:

- Signature against the trusted issuer's public keys.
- Issuer, audience, expiration, and required claims.
- Signing algorithm within an allowed set, never trusting an algorithm proposed arbitrarily by the token header.
- Other business constraints: tenant/domain, application permissions, or allowlisted identities.

On Cloud Run with IAM authentication enabled, **the Cloud Run platform validates the ID token and caller IAM on the service** before requests reach the container. If the API inside the container also enforces business authorization (e.g., users can view only their own invoices), the app must still validate and apply those checks. **IAM Invoker does not automatically perform in-app business authorization.**

## 5. Quick selection table: which endpoint requires which token?

| Call | Typical token used | Requirements to accept request |
|---|---|---|
| Read project via Cloud Resource Manager REST API | **Access token** | Matching scope/API, principal has project read permission |
| Read objects via Cloud Storage API | **Access token** | Required IAM/object permissions and bucket constraints |
| Publish messages to Pub/Sub REST API | **Access token** | Publish permission on topic and relevant API settings |
| Access Secret Manager API | **Access token** | Secret version access permission and matching policies |
| Call a private Cloud Run service | **Google-signed OIDC ID token** | Valid **aud**, caller has Cloud Run Invoker, plus service conditions |
| Call HTTP endpoint triggered by Cloud Tasks/Scheduler | **ID token** when target is private Cloud Run with OIDC configured | Task's service account and audience/role must match |
| Website sign-in with Google Sign-In/OIDC | **ID token** for relying party (login app) | Audience is app's client ID; validate issuer/signature/claims |
| Call Google APIs on behalf of a user after OAuth consent | **User access token** | User granted matching scopes and principal holds relevant permissions |
| Call public endpoint requiring no auth | May require no token | May still have app-layer or API gateway protections |

**You cannot swap an ID token for an access token merely because both travel in the Authorization header.** The rule is set by **the target service's documentation**, not the header syntax.

## 6. Calling private Cloud Run with an ID token: complete example

Context:

- **order-api** runs on Cloud Run and requires authentication.
- **payment-worker** calls that service, running under service account **worker-caller@PROJECT_ID.iam.gserviceaccount.com**.
- The target needs **roles/run.invoker** granted to the calling service account on that exact Cloud Run service.
- When making requests, the worker must send a **Google-signed ID token** whose **aud** is the receiving service's root URL or a valid custom audience.

~~~mermaid
sequenceDiagram
    participant W as payment-worker (service account)
    participant M as Metadata server / Identity service
    participant R as Cloud Run order-api
    W->>M: Request ID token with aud=order-api URL
    M-->>W: Google-signed ID token
    W->>R: HTTPS Authorization: Bearer ID_TOKEN
    R->>R: Validate token: iss/aud/exp
    R->>R: Check IAM Cloud Run Invoker
    alt Valid and authorized
      R-->>W: 2xx or app response
    else Invalid/missing token or unauthorized
      R-->>W: 401/403 depending on failure
    end
~~~

### 6.1. Grant Invoker (administrator action)

~~~bash
# Run only by someone permitted to edit service IAM.
PROJECT_ID="my-learning-project"
REGION="us-central1"
RECEIVER_SERVICE="order-api"
CALLER_SA="worker-caller@my-learning-project.iam.gserviceaccount.com"

gcloud run services add-iam-policy-binding "$RECEIVER_SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --member="serviceAccount:$CALLER_SA" \
  --role="roles/run.invoker"
~~~

**This role is attached for the caller on the receiving service**, not on the calling Cloud Run service. IAM permissions of the person **deploying** a workload also differ from those of the **runtime** service account.

A service account holding Invoker on service A **does not automatically have access** to service B.

### 6.2. Testing from a dev machine via impersonation

Assuming the user is logged into gcloud, authorized to **impersonate** the caller service account, and that caller holds Invoker:

~~~bash
# In Bash, replace with real Cloud Run URL.
TARGET_URL="https://order-api-abcdef-uc.a.run.app"
CALLER_SA="worker-caller@my-learning-project.iam.gserviceaccount.com"

# Mint ID token for the receiving service's exact audience.
ID_TOKEN="$(gcloud auth print-identity-token \
  --impersonate-service-account="$CALLER_SA" \
  --audiences="$TARGET_URL")"

# Send over HTTPS only; never echo or log token.
curl --fail-with-body --silent --show-error \
  -H "Authorization: Bearer $ID_TOKEN" \
  "$TARGET_URL/health"

unset ID_TOKEN
~~~

This is a **live call**; if `/health` does not exist, the app may return 404 even after authentication and IAM succeed. Replace URL/path with an authorized endpoint for testing.

**Note:** `gcloud auth print-identity-token` used directly with user credentials can produce a **generic ID token** meant for testing Cloud Run and Cloud Run functions. Do not treat it as a production ID token for arbitrary applications. The example above uses **service account impersonation** to specify an explicit audience, which still requires appropriate token-minting permission on the service account.

### 6.3. Calling from Cloud Run via the metadata server

Inside Cloud Run, when code runs with a configured runtime service account, the platform provides a metadata server for short-lived tokens. Without an auth library, you can request an ID token for an audience:

~~~bash
# Runs inside a Google Cloud workload supporting the metadata server.
# Not a command to run from a regular laptop.
TARGET_AUDIENCE="https://order-api-abcdef-uc.a.run.app"

ID_TOKEN="$(curl --fail-with-body --silent --show-error \
  -H "Metadata-Flavor: Google" \
  --get \
  --data-urlencode "audience=$TARGET_AUDIENCE" \
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity")"

curl --fail-with-body --silent --show-error \
  -H "Authorization: Bearer $ID_TOKEN" \
  "$TARGET_AUDIENCE/health"

unset ID_TOKEN
~~~

The metadata server is accessed over HTTP **inside supported internal environments** and requires the **Metadata-Flavor: Google** header. Never expose metadata endpoints to the Internet, never forward responses to external clients, and guard apps against vulnerabilities like SSRF that could reach metadata.

In production code, use **Google authentication libraries** to fetch and refresh tokens instead of assembling raw curl calls or custom caches.

### 6.4. Alternative header when the app already uses Authorization

Cloud Run supports another header for ID tokens:

~~~http
X-Serverless-Authorization: Bearer ID_TOKEN
~~~

This header helps when the container needs to reserve **Authorization** for the application's own business authentication. When both headers are present, Cloud Run prioritizes **X-Serverless-Authorization** when checking incoming requests. Do not treat this header as a universal rule across all Google APIs; it is Cloud Run-specific behavior.

## 7. Application Default Credentials (ADC): how apps locate credentials

**Application Default Credentials** is the strategy Google Cloud libraries use to automatically find environment-appropriate credentials, allowing the same code to run on dev machines, Compute Engine, Cloud Run, GKE, or federated environments.

ADC searches in priority order:

1. The path specified in **GOOGLE_APPLICATION_CREDENTIALS**.
2. The ADC credential file created by **gcloud auth application-default login** on a dev workstation.
3. The service account attached to the workload, provided via the **metadata server** on supported environments.

~~~mermaid
flowchart TD
    C["Google Cloud client/auth library"] --> E{"GOOGLE_APPLICATION_CREDENTIALS set?"}
    E -- "Yes" --> F["Read credential config at that path"]
    E -- "No" --> L{"Local ADC file exists?"}
    L -- "Yes" --> U["Use local ADC"]
    L -- "No" --> M["Use attached identity / metadata server if supported"]
    F --> T["Create/refresh matching token"]
    U --> T
    M --> T
    T --> API["Call Google Cloud API / fetch ID token with exact audience"]
~~~

**Search order is not a security ranking.** Using a long-lived key file in step 1 is usually riskier than using an attached service account in step 3, even though ADC checks the environment variable first.

### 7.1. gcloud credentials differ from local ADC

Two easily confused commands:

~~~bash
# Authenticate for gcloud CLI commands.
gcloud auth login

# Set up Application Default Credentials for Google Cloud
# libraries used in code on a dev machine.
gcloud auth application-default login
~~~

Both mechanisms can use different accounts and store separate credentials. Therefore:

- `gcloud projects list` succeeding does not prove Java code using ADC holds the same permissions.
- Switching the active account in gcloud CLI does not automatically switch the ADC account.
- Tokens printed by `gcloud auth print-access-token` may differ from tokens produced by code using ADC.
- When testing with the same service account, consider **service account impersonation** for both CLI and ADC per Google Cloud docs, with explicit permissions.

To pinpoint a permission failure, inspect **the actual identity of the credentials in use**, rather than checking only the project name in config.

### 7.2. Recommended runtime identities

| Environment | Credential source to consider | Rationale |
|---|---|---|
| Developer laptop | User local ADC or ADC impersonating a service account | Separates personal environment from runtime identity |
| Cloud Run | Dedicated service account attached to the Cloud Run service | Platform automatically supplies short-lived tokens |
| Compute Engine | Attached service account and matching IAM roles | Avoids storing private keys on VMs |
| GKE | **Workload Identity Federation for GKE** | Binds permissions per workload/Kubernetes ServiceAccount, limiting node-wide permissions |
| External CI/CD (GitHub Actions, etc.) | **Workload Identity Federation** | Uses external system identity, exchanged for short-lived credentials |
| Enterprise using external IdP for staff | **Workforce Identity Federation** per org architecture | Federates human user identities from supported IdPs |

**Workload Identity Federation** and **Workforce Identity Federation** serve different principal groups (workloads vs. workforce). When designing IAM, specify federation type, trust configuration, principal mapping, service account impersonation if any, and audience scope.

### 7.3. Avoid service account keys whenever unnecessary

A service account JSON private key file is a long-lived credential that can be copied. If leaked, an attacker can use it without touching the original environment until the key is disabled or blocked by other controls.

Preference by scenario:

1. **Attached service account** for Cloud Run/Compute Engine.
2. **Workload Identity Federation for GKE** for pods.
3. **Workload Identity Federation** for runners outside Google Cloud.
4. **Service account impersonation** for authorized tasks needing a service account identity.
5. Use a **service account key** only when no viable alternative exists, backed by approval, protection, monitoring, rotation, and revocation.

An **external account credential configuration** file used for Workload Identity Federation is not a service account private key. Never assume every JSON file referenced by **GOOGLE_APPLICATION_CREDENTIALS** is a “key”.

## 8. Service account impersonation and token-minting permissions

**Impersonation** lets an authenticated principal request short-lived credentials to act with another service account's identity. There are **two identities**: the caller performing impersonation and the impersonated service account.

Example: a dev account is only permitted to mint short-lived tokens for **staging-caller@...**, while `staging-caller` holds read access on a test bucket. The dev does not need direct bucket read access on their personal user account; operations are delegated through the service account.

~~~mermaid
flowchart LR
    U["Developer / CI principal"] -->|"Granted token-creation rights"| SA["Service account"]
    SA -->|"Granted IAM on target"| R["Bucket / API / Cloud Run service"]
    U -. "Request short-lived token" .-> T["IAM Credentials API"]
    T -. "Token for service account" .-> U
    U -->|"Call with token"| R
~~~

**Token-minting permissions and token-usage permissions are two distinct steps:**

| Step | Requirement |
|---|---|
| Call **generateAccessToken** | Principal needs **iam.serviceAccounts.getAccessToken** on the service account; common role is **roles/iam.serviceAccountTokenCreator** |
| Call **generateIdToken** | Principal needs **iam.serviceAccounts.getOpenIdToken**; dedicated role **roles/iam.serviceAccountOpenIdTokenCreator** exists |
| Use access token to call Google API | Impersonated service account must hold required IAM/API permissions |
| Use ID token to call Cloud Run | Impersonated service account needs **roles/run.invoker** on the receiving service, and audience must be valid |

Even a **Project Owner** might lack token-minting permission on a service account if IAM on that service account blocks or omits it. Conversely, granting **Token Creator** too broadly opens privilege escalation paths. Scope impersonation tightly and audit its usage.

CLI example using impersonation to obtain a short-lived access token:

~~~bash
# Never display token publicly; use within controlled sessions.
TARGET_SA="staging-caller@my-learning-project.iam.gserviceaccount.com"

ACCESS_TOKEN="$(gcloud auth print-access-token \
  --impersonate-service-account="$TARGET_SA")"

# Use ACCESS_TOKEN with authorized Google Cloud API endpoints.
# Unset variable afterward.
unset ACCESS_TOKEN
~~~

## 9. Workload Identity Federation: authenticating outside Google Cloud

A pipeline running on GitHub Actions, AWS, Azure, or a self-managed platform can hold its **source system's OIDC token**. Do not blindly pass that OIDC token directly to Google Cloud REST APIs.

General flow:

1. Workload proves its identity to an **external IdP** trusted by Google Cloud.
2. Workload receives an assertion/token from the IdP.
3. Google Cloud **Security Token Service (STS)** validates federation config and exchanges the assertion for a short-lived federated credential.
4. Workload uses the federated credential directly on supported services or impersonates a service account per config.
5. The resulting Google Cloud credential calls Google APIs or fetches a Google-signed ID token for targets like Cloud Run.

~~~mermaid
sequenceDiagram
    participant CI as External CI workload
    participant IdP as External OIDC/SAML IdP
    participant STS as Google STS
    participant IAM as IAM Credentials (if impersonating)
    participant GCP as Google Cloud API / Cloud Run
    CI->>IdP: Fetch workload assertion
    IdP-->>CI: Assertion
    CI->>STS: Exchange assertion per federation config
    STS-->>CI: Federated credential
    opt If service account impersonation needed
      CI->>IAM: Request service account token
      IAM-->>CI: Access token or Google-signed ID token
    end
    CI->>GCP: Call with appropriate token type
    GCP-->>CI: Result per IAM and policies
~~~

**Not every federated token is accepted identically by every service.** Verify the target service, supported principal formats, and whether an impersonation step is required.

Specifically for **Workload Identity Federation for GKE**, components like the GKE metadata server exchange Kubernetes ServiceAccount tokens on the workload's behalf for Google Cloud credentials. Applications should use ADC/client libraries rather than packing JSON keys into pods.

## 10. User OAuth 2.0 and OIDC application sign-in

Not all GCP interactions are machine-to-machine. An application may need:

- Users signing in with Google and identifying themselves.
- Users authorizing the app to read a Google resource they own.
- Backends using their own service accounts for internal processing.

These are distinct flows.

### 10.1. Authorization code flow with PKCE

In web/mobile apps, modern OAuth flows use **authorization code** and **PKCE** where appropriate, keeping client secrets protected and reducing authorization code interception risk.

~~~mermaid
sequenceDiagram
    participant U as User
    participant App as Application
    participant Google as Google Authorization Server
    U->>App: Sign in / grant access
    App->>Google: Redirect with state, code_challenge, scope
    Google->>U: Authenticate and consent if needed
    U-->>Google: Approve/deny
    Google-->>App: Authorization code to redirect URI
    App->>Google: Exchange code + code_verifier
    Google-->>App: Access token (+ ID token if OIDC; refresh token when eligible)
    App->>App: Verify ID token; manage session
~~~

Important properties:

- **state** defends against forged requests/cross-session binding; validate upon redirect.
- **PKCE** protects authorization code exchange.
- **redirect URI** must be valid and match app registration.
- **scope** should be minimal for the feature; never request broad permissions needlessly.
- **ID token** authenticates the user under OIDC; **access token** calls APIs accepting that token.
- **refresh token** (if issued) must be safeguarded carefully, especially on backends.

A Google ID token from a website login typically has **aud = website's OAuth client ID**. Never reuse it to call private Cloud Run simply because both are JWTs. Cloud Run IAM authentication enforces its own issuer/audience/permission rules.

### 10.2. Service accounts do not replace user authorization

A service account is the **application/workload** identity. If a rule says “user A can view only user A's orders”, a backend querying Cloud SQL using a service account permitted to read the database **does not automatically enforce user A's business permissions**. The backend still needs session/user identity and application-layer authorization checks.

Similarly, if an app must act on a user's behalf against an API requiring user OAuth consent, you cannot simply swap in a service account and skip user delegation rules. Specialized features like domain-wide delegation carry strict governance controls and are not default choices.

## 11. Practice in Java: separating the two token types

Because this module includes many Java apps running on GCP, this section illustrates two code patterns. Use **Google Auth Library for Java** (package **com.google.auth.oauth2**) and HTTP libraries suited to your project. Pin a stable version managed by your project and verify APIs for that exact version.

### 11.1. Access token via ADC for Google APIs

~~~java
import com.google.auth.oauth2.GoogleCredentials;
import java.io.IOException;
import java.util.List;

public final class AccessTokenExample {
    public static String getTokenForGoogleApis() throws IOException {
        GoogleCredentials credentials = GoogleCredentials.getApplicationDefault();

        if (credentials.createScopedRequired()) {
            credentials = credentials.createScoped(
                List.of("https://www.googleapis.com/auth/cloud-platform")
            );
        }

        credentials.refreshIfExpired();
        return credentials.getAccessToken().getTokenValue();
    }
}
~~~

This shows how an access token can be retrieved from environment-configured ADC. In real applications, **prefer per-service Google Cloud client libraries**, because they attach and refresh access tokens automatically without extracting raw token strings in business code. If manual REST calls are unavoidable, send the token string only in HTTPS requests and never log it.

### 11.2. ID token for a private Cloud Run service from ADC

~~~java
import com.google.auth.oauth2.GoogleCredentials;
import com.google.auth.oauth2.IdTokenCredentials;
import com.google.auth.oauth2.IdTokenProvider;
import java.io.IOException;

public final class IdTokenExample {
    public static String getIdTokenForCloudRun(String audience)
            throws IOException {
        GoogleCredentials base = GoogleCredentials.getApplicationDefault();

        if (!(base instanceof IdTokenProvider)) {
            throw new IllegalStateException(
                "Current ADC does not support minting ID tokens directly; " +
                "use an attached service account or a supported " +
                "impersonation/ID token provider mechanism."
            );
        }

        IdTokenCredentials idCredentials =
            IdTokenCredentials.newBuilder()
                .setIdTokenProvider((IdTokenProvider) base)
                .setTargetAudience(audience)
                .build();

        idCredentials.refreshIfExpired();
        return idCredentials.getIdToken().getTokenValue();
    }
}
~~~

Invoke as follows in an environment **whose credential source supports ID tokens**:

~~~java
String cloudRunUrl = "https://order-api-abcdef-uc.a.run.app";
String token = IdTokenExample.getIdTokenForCloudRun(cloudRunUrl);

// HTTP client sends GET/POST to a valid endpoint, e.g., /health:
// Header: Authorization: Bearer <token>
// Do not log tokens. Prefer an auth-aware HTTP client to handle refreshes/tokens.
~~~

**Important limitation:** local ADC created from a standard human user account does not necessarily implement **IdTokenProvider**. The code above intentionally throws a clear error there instead of assuming every ADC can issue Cloud Run ID tokens. Runtime service accounts or supported impersonated identities are standard options; verify support per credential type and library version.

### 11.3. Never store tokens in long-lived fields

A Java service running for hours must never grab a token at startup into a **static final String TOKEN** for indefinite reuse. Tokens expire. Instead:

- Hold the library-managed credential/client object.
- Let the library automatically refresh or request new tokens as needed.
- Use an HTTP client capable of attaching authenticated credentials per request.
- Configure bounded timeouts/retries and never retry infinitely on 401/403.
- Never leak tokens in exception messages, stack traces, or diagnostics.

## 12. Managing IAM across multiple GCP services

An e-commerce backend commonly calls several target types:

~~~mermaid
flowchart TD
    P["Cloud Run: checkout-api\nService account: checkout-runtime"] -->|"ID token, aud=URL"| R["Cloud Run: private fraud-service"]
    P -->|"Access token / ADC"| S["Secret Manager API"]
    P -->|"Access token / ADC"| PUB["Pub/Sub API"]
    P -->|"Matching connector/database auth"| DB["Cloud SQL"]
    IAM["Per-resource IAM policies"] -. "run.invoker" .-> R
    IAM -. "secretmanager.versions.access" .-> S
    IAM -. "pubsub.topics.publish" .-> PUB
~~~

### 12.1. Illustrative permission matrix

| Caller | Target | Token | Permissions to verify |
|---|---|---|---|
| checkout-runtime | Private Cloud Run fraud-service | Google-signed ID token | **roles/run.invoker** on fraud-service |
| checkout-runtime | Secret Manager secret | Access token (via ADC) | Least role with **secretmanager.versions.access** on the secret |
| checkout-runtime | Pub/Sub topic | Access token (via ADC) | Least role with **pubsub.topics.publish** on the topic |
| CI release | Cloud Run deployment API | Access token for Google APIs | Cloud Run/Artifact Registry deploy rights plus appropriate runtime SA usage rights |
| reporting-job | Reporting Cloud Storage bucket | Access token (via ADC) | Object read/write rights matching exact requirements |
| Website end user | checkout backend | App-designed session/JWT mechanism | Backend authentication and business authorization |

For Cloud SQL, connection methods can involve private IP, connectors/Cloud SQL Auth Proxy, IAM database authentication, or database credentials depending on architecture. Never assume a Google API access token serves directly as a password for every SQL engine.

### 12.2. Choosing separate runtime service accounts

Create separate service accounts for workloads with distinct permission footprints, for example:

- **checkout-runtime**: publishes to one topic and reads one secret.
- **fraud-runtime**: reads only the required dataset.
- **reporting-job**: writes only to the reporting bucket.
- **ci-deployer**: deploys into the designated environment.

If all workloads share one service account holding broad project-wide permissions, a vulnerability in one container compromises multiple services. Minimizing permissions and separating identities reduces blast radius and improves audit clarity.

## 13. Troubleshooting 401, 403, and authentication errors

HTTP 401 usually points to a **missing or invalid token**, while 403 usually points to **missing permissions or a deny policy**. Still, exact HTTP codes and messages depend on gateways, products, and app code; read target logs and detailed error codes.

| Symptom | Possible cause | Safe verification steps |
|---|---|---|
| Cloud Run 401 calling private service | Missing ID token, wrong audience, expired token, invalid issuer/signature | Check token type, service root URL, and expected audience |
| Cloud Run 403 | Caller lacks Invoker, or blocked by IAM/ingress policy | Inspect principal, bindings, and policies on target service |
| Google REST API reports missing scope | Access token restricted to an incompatible scope | Check credential source and token scope via safe security tooling |
| Google REST API 403 despite valid access token | Principal lacks IAM permission or hits policy/API/quota limits | Check target resource, exact permission, API enablement, quotas |
| Java code gets 403 while gcloud CLI succeeds | **gcloud auth login** and **ADC** use two different identities | Inspect ADC source, quota project, and runtime principal IAM |
| Error fetching ID token from laptop ADC | User ADC does not supply a suitable IdTokenProvider | Use service account impersonation or a supported runtime environment |
| Metadata server unreachable | Running outside Google Cloud or different config | Verify runtime environment, Metadata-Flavor header, and supported endpoint |
| Token failures after roughly one hour | Cached token expired without refresh | Let auth library manage refreshes or request a fresh token |
| Calling Cloud Run via custom domain returns 401 | **aud** mismatches default URL or valid custom audience | Inspect service audience config; never guess from request URL |
| Access token leaked in pipeline | `echo`, `set -x`, header logging, or saved artifacts | Revoke/contain credentials, fix logging, and switch to short-lived tokens |
| Permission error impersonating service account | Missing **getAccessToken/getOpenIdToken** on target SA | Inspect service account policy and token creator roles |
| Private VPC connection fails | DNS, routes, firewalls, ingress, or private endpoint | Separate network debugging from token/IAM debugging |

### 13.1. Sequential investigation workflow

1. **Identify endpoint:** Google Cloud API, private Cloud Run, IAP, or app-managed auth?
2. **Identify required token:** access token or Google-signed ID token, and is a specific audience required?
3. **Identify actual principal:** user ADC, attached service account, federated principal, or impersonated service account?
4. **Check freshness:** is the token expired? Is there clock skew or missing refresh logic?
5. **Check scope/audience:** scopes apply to Google APIs; `aud` applies to ID tokens at target services.
6. **Check IAM and policies:** does the principal hold permissions on the **exact resource**? Are conditions or deny policies blocking?
7. **Check environment:** API enabled, quotas, region, DNS, VPC, ingress, service health?
8. **Cross-check logs safely:** inspect Cloud Audit Logs and app logs at metadata/error-code level; never ask someone to paste live token values.

**Never paste tokens into untrusted online decoders** or public tickets. You may inspect JWT headers/payloads inside controlled local tools for debugging, keeping in mind decoding **does not verify signatures** and the token itself remains a secret.

### 13.2. Two particularly common mistakes

**Wrong token type:** a developer grabs an access token from `gcloud` and sends it to an IAM-authenticated Cloud Run service. Cloud Run expects a Google-signed ID token with the matching audience. Fix it by minting an ID token properly, not by blindly escalating IAM.

**Wrong identity:** the CLI succeeds under an Editor user account while Cloud Run runs under a low-privilege service account. Fix it by granting **just enough permissions to the runtime service account** on target resources, never by copying developer credentials into the container.

## 14. Designing token security and operability

### 14.1. Brief threat model

Suppose an HTTP container has an **SSRF** vulnerability. If the app lets arbitrary client inputs hit the metadata server, an attacker could steal tokens for the runtime service account and call any APIs that service account is permitted to invoke.

To reduce risk:

- Validate and restrict target URLs when the app fetches external resources.
- Block untrusted input from steering requests toward internal/metadata addresses.
- Separate workload identities and bind IAM only to exact required resources.
- Use short-lived platform-provided tokens without baking long-lived keys into containers.
- Monitor anomalies and rely on audit logs for investigation.
- Keep libraries updated and run security checks in pipelines.

Short-lived tokens **do not eliminate risk** if a service account holds overly broad permissions or the app can continually mint fresh tokens. Least privilege and network boundaries remain essential.

### 14.2. Safe release automation

In CI/CD, pipelines deploying Cloud Run or GKE should separate:

- **Build identity:** read source code, pull dependencies, push artifacts.
- **Deploy identity:** modify deployment resources, using runtime service accounts where permitted.
- **Runtime identity:** call APIs and peer services while the application serves traffic.

Never reuse a single Owner service account across all three stages. Pipelines outside GCP should consider **Workload Identity Federation** with trust policies locked to repo, branch, or workflow, paired with appropriately scoped deployment permissions.

### 14.3. Observability and cost

401/403 failures drive up failed requests, retry processing time, and sometimes service call charges. In operations, track:

- Error rate by endpoint and HTTP status code.
- Counts of authentication / permission-denied errors from available logs.
- Credential retrieval latency if unnecessary refreshes occur frequently.
- Unusual impersonation calls on sensitive service accounts.
- User SLO impact, especially across Cloud Run → Cloud Run → database chains.

Never log tokens for debugging convenience. Good logs need only timestamp, service, error type, request ID, principal when safely logged by the system, and target resource. Log retention also requires balancing access controls and Cloud Logging costs.

## 15. Case study: Cloud Run order processor calling fraud check

**Requirement:** an e-commerce system has **checkout-api** receiving orders, calling internal **fraud-checker** for risk scoring, publishing events to Pub/Sub, and reading Secret Manager APIs when needed. Both services run in the production project with separate service accounts.

### 15.1. Token selection

| Action | Identity | Token | Required IAM |
|---|---|---|---|
| checkout-api calls fraud-checker | checkout-runtime | **ID token**, aud=fraud-checker URL | Invoker on fraud-checker |
| checkout-api publishes to Pub/Sub | checkout-runtime | **Access token/ADC** | Pub/Sub Publisher on target topic |
| checkout-api reads Secret Manager | checkout-runtime | **Access token/ADC** | Secret Manager Secret Accessor on target secret |
| fraud-checker reads own data | fraud-runtime | Access token/ADC or matching service auth | Least-privilege data permissions |
| CI releases checkout-api revision | ci-deployer | Access token for Google APIs | Deploy rights and scoped runtime SA usage |

### 15.2. Deployment flow

1. Create **checkout-runtime** for the caller service and **fraud-runtime** for the receiving service.
2. Run **checkout-api** with `checkout-runtime`.
3. Configure **fraud-checker** to require authentication and grant **roles/run.invoker** to `checkout-runtime` on `fraud-checker`.
4. Inside `checkout-api`, obtain an ID token with **aud** equal to `fraud-checker`'s root URL via appropriate client library/metadata service.
5. Send HTTPS requests to `fraud-checker`, checking response codes and timeouts.
6. Use **ADC** to publish to Pub/Sub or call Secret Manager; grant dedicated IAM roles scoped to the exact topic/secret.
7. Monitor latency, 401/403 errors, retries, and audit logs without logging tokens.
8. When rotating identities or promoting across environments, update bindings and target service audience configs accordingly.

**Failure variation:** after changing a Cloud Run URL for traffic splitting, the client sets **aud** to the traffic-tag URL. The service can reject the token. Keep audience set to the Cloud Run-accepted service URL or configured custom audience. Request path/traffic tag and audience do not have to match.

### 15.3. Architectural takeaway

Using both token types in **the same application** is normal: ID tokens for private Cloud Run services, access tokens for Google APIs. Each call has its own resource server, permissions, and audience/scope. What matters is selecting **identity and token per access boundary**, never storing one shared token across the whole system.

## 16. Controlled practice exercises

The exercises below need only an authorized project/dev environment. They do not require opening public access, downloading service account keys, or editing production IAM.

### 16.1. Part A — Permission mapping for three calls

Prompt: a Java app running on Cloud Run needs to:

1. Read project metadata via the Cloud Resource Manager API.
2. Call an authenticated Cloud Run service **inventory-api**.
3. Write objects to a reporting Cloud Storage bucket.

Fill in:

| Target | Token to use | Minimum IAM check | Audience / scope |
|---|---|---|---|
| Resource Manager | … | … | … |
| inventory-api | … | … | … |
| Cloud Storage | … | … | … |

**Hint:** Resource Manager and Cloud Storage require access tokens; `inventory-api` requires a Google-signed ID token with **aud** matching the receiving service. Corresponding IAM permissions must exist on the project, Cloud Run service, and bucket.

### 16.2. Part B — Checking local environment

~~~bash
# Displays configuration info only; does not print tokens.
gcloud auth list
gcloud config list
gcloud config get-value project

# If local ADC is not yet set up for the learning environment and login is permitted:
# gcloud auth application-default login

# You can test permissions on a dev project with a read operation:
gcloud projects describe YOUR_PROJECT_ID
~~~

Explain why `gcloud projects describe` succeeding does not guarantee a Java program using ADC holds equivalent permissions.

### 16.3. Part C — Interpreting error codes

Three fictitious incidents:

- **Incident 1:** Cloud Run returns 401; logs show the client sent an access token instead of an ID token.
- **Incident 2:** Caller sends a Google-signed ID token with the right audience, yet Cloud Run returns 403.
- **Incident 3:** Java client fails calling Secret Manager, while the same user runs gcloud CLI to read the project successfully.

For each incident, identify **token type, identity, permissions, and credential source** to inspect. Never default to granting Owner or enabling public access.

**Guided answers:**

- (1) Mint an ID token with the exact audience; Cloud Run IAM authentication requires the right token type.
- (2) Check the principal and Invoker role/access conditions on the service.
- (3) Check that Java's ADC differs from the CLI, and verify whether the runtime principal holds access on the required secret version; project read permission does not equal secret read permission.

## 17. Misconceptions to avoid

| Misconception | Accurate understanding |
|---|---|
| “OAuth 2.0 is a type of token.” | OAuth 2.0 is an authorization framework encompassing multiple flows and credential/token types. |
| “Access tokens and ID tokens are both Bearer, so they are interchangeable.” | The header syntax may match, yet the target service expects a specific token type. |
| “If an ID token JWT decodes cleanly, it is valid.” | You must verify the signature and required claims; decoding only reads payload data. |
| “An access token with cloud-platform scope grants all permissions.” | IAM and other policies still govern access. |
| “Having roles/run.invoker lets you call the service without an ID token.” | Private Cloud Run requires a validly authenticated request, including token and related conditions. |
| “Logging into gcloud CLI sets Java ADC to the same account.” | CLI credentials and ADC are managed separately. |
| “Using a service account requires downloading a JSON key.” | Attached identities, federation, and impersonation usually reduce risk. |
| “A user ID token from Google Sign-In works for calling any Cloud Run service.” | Website sign-in tokens use different audiences/issuers and verification rules. |
| “Changing the request URL means aud must include the full path.” | Cloud Run's default audience is the service's root URL or a valid custom audience. |
| “When a token expires, just keep retrying HTTP calls.” | Refresh tokens via the proper mechanism and bound retries. |
| “Permission to mint a token means permission to call any API.” | The impersonated service account still needs actual permissions on target APIs. |
| “Authentication completes business authorization.” | Applications must still enforce user-level authorization over business data. |

## 18. Official reference documentation

Check Google Cloud docs to track API updates, identity mechanics, and security guidance:

- [Google Cloud Authentication — Token types](https://docs.cloud.google.com/docs/authentication/token-types)
- [Get an ID token](https://docs.cloud.google.com/docs/authentication/get-id-token)
- [Cloud Run — Authenticate service-to-service](https://docs.cloud.google.com/run/docs/authenticating/service-to-service)
- [Application Default Credentials — How it works](https://docs.cloud.google.com/docs/authentication/application-default-credentials)
- [Authenticate using REST](https://docs.cloud.google.com/docs/authentication/rest)
- [Service account impersonation](https://docs.cloud.google.com/iam/docs/service-account-impersonation)
- [Workload Identity Federation for GKE](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/workload-identity)
- [gcloud auth print-identity-token reference](https://docs.cloud.google.com/sdk/gcloud/reference/auth/print-identity-token)

Permissions, token types, flows, and library capabilities can change by service/version. When implementing in production, check docs matching your exact SDK version and target endpoint characteristics.

---

**Takeaway:** For **Google Cloud REST APIs** like Storage, Pub/Sub, Secret Manager, or Resource Manager, you typically need an **OAuth 2.0 access token** paired with matching IAM permissions. For **private Cloud Run services**, you typically need a **Google-signed OIDC ID token** with **audience matching the receiving service**, plus **Cloud Run Invoker** for the caller. **ADC, attached service accounts, and Workload Identity Federation** enable apps to obtain/exchange short-lived tokens without managing long-lived private keys. This forms the foundation for building secure, automated, observable, and cost-controlled Compute Engine, GKE, Cloud Run, and data systems.
