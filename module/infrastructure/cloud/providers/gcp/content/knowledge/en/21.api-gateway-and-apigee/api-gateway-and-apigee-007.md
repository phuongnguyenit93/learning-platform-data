# Apigee Policies for Authentication and Traffic Management

An online learning platform exposes a course lookup API for partners. If every request goes straight to the backend, a leaked API key could be exploited to send thousands of calls per second; conversely, a legitimate partner running a batch job could accidentally exhaust resources. **Apigee** lets you attach **policies** to an API proxy to identify clients, enforce API access permissions, smooth sudden traffic spikes, and limit consumption per application.

Within the **API Gateway and Apigee** chapter of the **CLOUD_PROVIDERS_GCP** module, this lesson focuses on configuring and operating policies in Apigee, connecting IAM, VPCs, Cloud Run/GKE backends, logging, SLOs, and cost. Unlike Google Cloud **API Gateway**, Apigee provides an ecosystem of API products, developer apps, and composable policies directly within proxy processing flows. Do not copy Apigee policy XML into API Gateway expecting both products to share the same configuration model.

**After this lesson, you can:**

1. Choose between `VerifyAPIKey`, `OAuthV2`, and `VerifyJWT` based on identity mechanism and token type.
2. Attach policies to `ProxyEndpoint`/`TargetEndpoint` and control execution order and flow conditions.
3. Distinguish `SpikeArrest` (rate/burst smoothing) from `Quota` (periodic usage allowance).
4. Design counters per app/API product instead of unintentionally sharing a single counter.
5. Test valid requests, missing/invalid credentials, limit violations, backend errors, and error handling without leaking secrets.
6. Monitor metrics, adjust limits, and maintain a rollback plan when protecting real APIs.

## 1. Where Do Policies Sit in the Request Path?

An **API proxy** is the layer that receives client requests, applies processing steps, and forwards them to a **target** (such as Cloud Run, GKE, or a self-managed backend). Policies can authenticate, mutate headers, route, throttle load, and return error responses before the backend ever sees the request.

~~~mermaid
flowchart LR
    CLIENT["Partner / application"] --> ENTRY["Apigee API proxy"]
    ENTRY --> AUTH["VerifyAPIKey or<br/>OAuthV2 / VerifyJWT"]
    AUTH --> SPIKE["SpikeArrest<br/>blocks bursts"]
    SPIKE --> QUOTA["Quota<br/>allowance per app"]
    QUOTA --> TARGET["Cloud Run / GKE backend"]
    TARGET --> CLIENT
~~~

This diagram shows **one option**; not every proxy has to apply **all three** mechanisms (API key, OAuth, and JWT). Select one or more based on the actual security contract, then ensure unauthorized requests **cannot accidentally enter a flow that bypasses authentication**.

### 1.1. Execution Path in Apigee

An API proxy has a **ProxyEndpoint** (client-facing) and usually a **TargetEndpoint** (backend-facing). On each endpoint, the main stages include:

| Component | Timing | Example |
| --- | --- | --- |
| ProxyEndpoint `PreFlow/Request` | Start of the request flow at the gateway | Verify credentials, apply SpikeArrest/Quota. |
| Conditional `Flow` | Runs only when the flow's condition matches | Require a specific scope for `POST /orders`. |
| `PostFlow/Request` | After conditional request flows | Header adjustments and common steps needed before target. |
| `TargetEndpoint` request/response | Handles backend communication | Authenticate to backend, transform request/response. |
| `PostFlow/Response` and fault handling | Returns result to client | Headers, logging, standardized errors. |

When multiple conditional flows match, the **first flow** in order whose condition evaluates true runs in that segment. Therefore, policy ordering and placement are part of security design, not merely XML organization.

### 1.2. Policy Order Affects Both Security and Quotas

A common pattern for partner APIs using API keys:

1. **VerifyAPIKey:** proceed only if the key is valid and the app is authorized for the API product/resource.
2. **SpikeArrest:** cap instantaneous request rate; when per-client, derive the ID from the **verified identity**.
3. **Quota:** decrement the allowance per app/product using a well-defined counter.
4. **AssignMessage / equivalent step:** strip client credentials before forwarding to the backend if the backend does not need them.
5. **Route to target:** invoke the backend with its own authentication mechanism if the backend is a private service.

If SpikeArrest/Quota runs **before** authentication, a caller-supplied `client-id` header can distort counter grouping or let anonymous requests consume another customer's quota. If you need to protect the gateway **even before authentication** against a massive flood, place a separate aggregate limit before VerifyAPIKey, treating it strictly as a **shared counter**, not a verified per-app allowance.

### 1.3. API Products and Developer Apps

In Apigee, administrators create an **API product** defining which API proxies/resources/operations a partner may call. Developers register a **developer app**, associate it with one or more API products, and receive an API key. `VerifyAPIKey` checks the key, app status, and API product authorization, populating **flow variables** for downstream quota/routing steps.

**Do not confuse an API key with an end-user account.** Keys primarily identify a registered application/partner; if operations require per-student or per-employee permissions, enforce user-level authentication and authorization (OIDC/OAuth, scopes/claims, and business logic).

## 2. Three Common Authentication Methods

### 2.1. `VerifyAPIKey`: Verify Application and API Product

Example Apigee policy reading a key from a dedicated header:

~~~xml
<VerifyAPIKey name="VAK-Partner">
  <APIKey ref="request.header.x-api-key"/>
</VerifyAPIKey>
~~~

Illustrative client call:

~~~bash
# Use the API key of a registered and approved LAB app
curl --fail-with-body --silent --show-error \
  -H "x-api-key: $LAB_API_KEY" \
  "https://API_PROXY_HOST/partner/v1/courses"
~~~

Do not pass keys in query strings because they can end up in browser history, analytics, and reverse-proxy logs. Even in headers, request logs can capture keys if all headers are logged; enforce **redaction**. An API key must never be treated as proof of a specific **end user's** identity.

When `VAK-Partner` succeeds, Apigee sets variables such as `verifyapikey.VAK-Partner.client_id`. Use it to scope quotas to the **verified key** rather than trusting an arbitrary `client-id` header from the client.

### 2.2. `OAuthV2`: Verify Apigee-Managed Access Tokens

When the proxy uses OAuth access tokens issued/managed by Apigee, the following policy validates the token in `Authorization: Bearer ...`:

~~~xml
<OAuthV2 name="OA-VerifyAccessToken">
  <Operation>VerifyAccessToken</Operation>
</OAuthV2>
~~~

Typically attach this policy to the request PreFlow of the protected API. When configuring `Scope`, understand its exact semantics: multiple scopes inside **one** `<Scope>READ WRITE</Scope>` element in VerifyAccessToken are evaluated with **OR** logic (at least one scope present), not automatically requiring both. If business logic requires **AND**, design an appropriate explicit check.

**Do not use `OAuthV2/VerifyAccessToken` by default to verify external Identity Provider JWT access tokens.** External tokens may require `VerifyJWT` (signed JWTs), a dedicated OAuth/JWT verification policy, or introspection (opaque tokens) against a trusted service. Before choosing, confirm **who issues the token** and **who can verify it**.

### 2.3. `VerifyJWT`: Verify JWT Signature and Claims

For an RS256-signed OIDC/JWT access token from a trusted issuer, an example configuration:

~~~xml
<VerifyJWT name="VJWT-Partner">
  <Algorithm>RS256</Algorithm>
  <PublicKey>
    <JWKS uri="https://ISSUER_HOST/.well-known/jwks.json"/>
  </PublicKey>
  <Issuer>https://ISSUER_HOST/</Issuer>
  <Audience>https://api.example.com/partner</Audience>
</VerifyJWT>
~~~

This is a **template requiring real issuer/JWKS/audience values**, not a ready-to-run policy. When `<Source>` is omitted, `VerifyJWT` reads the `Authorization` header and automatically strips the `Bearer` prefix. If you explicitly specify `<Source>request.header.authorization</Source>`, the policy **does not automatically strip that prefix**, causing tokens to be rejected—an important difference from the default.

Beyond signature and `exp`/`nbf`, check **issuer, audience, algorithm, key rotation**, required scopes/claims, and business permission mapping. Merely decoding the JWT payload or seeing a JWT-shaped string **is not authentication**. Fetching JWKS from a URL uses caching; there can be a delay when an issuer rotates keys, so test rotation windows.

### 2.4. Comparison to Avoid Misuse

| Option | What Does It Verify? | Best Fit | Limitations to Remember |
| --- | --- | --- | --- |
| VerifyAPIKey | Key and app/API product access | Partner APIs, identifying consumer apps | Does not identify end users; keys can be shared or leaked. |
| OAuthV2 VerifyAccessToken | Access token managed by Apigee OAuthV2 | APIs using Apigee-managed OAuth tokens | Tokens from external issuers require a compatible verification strategy. |
| VerifyJWT | JWT signature, expiry, and configured claims | JWTs from a trusted Identity Provider | Does not automatically enforce all business permissions or instant revocation. |
| Backend authorization | Specific user/tenant permissions on resources | Any API handling sensitive data | Gateway auth never replaces record-level access control. |

Security policies may fall under **Standard** or **Extensible** categories and impact licensing/cost depending on your Apigee edition. Before broad rollout, check policy availability/entitlements for your organization.

## 3. `SpikeArrest`: Protecting Backends from Traffic Spikes

`SpikeArrest` sets a request threshold per **second** (`ps`) or **minute** (`pm`) to smooth bursts that could overwhelm the backend. It is a **short-term rate control**, not a business allowance like "100,000 calls/month."

### 3.1. Example: 10 Requests/Second per Verified Client

~~~xml
<SpikeArrest name="SA-Partner">
  <Identifier ref="verifyapikey.VAK-Partner.client_id"/>
  <Rate>10ps</Rate>
  <UseEffectiveCount>true</UseEffectiveCount>
</SpikeArrest>
~~~

Meaning:

- `<Rate>10ps</Rate>`: threshold of 10 requests/second; this does not mean the backend is guaranteed to receive exact 10-request bursts in **every** 1-second window due to the enforcement algorithm and load distribution.
- `<Identifier .../>`: isolates the limit by **API key verified by VerifyAPIKey**. Omitting Identifier creates a shared proxy-wide limit.
- `<UseEffectiveCount>true</UseEffectiveCount>`: uses the recommended effective/synchronized counting mechanism for Apigee; in Apigee production, **do not leave it `false`** merely because an older example used the smoothing algorithm.

**Required ordering in this example:** `VAK-Partner` must run before `SA-Partner`, otherwise `verifyapikey.VAK-Partner.client_id` is not populated yet. If protecting multiple auth flows (JWT, API key, guest traffic), select the right identifier for each branch rather than reusing an empty variable.

### 3.2. Distinguishing Per-Client Limits from Global Limits

| Goal | Conceptual Configuration | Effect |
| --- | --- | --- |
| Protect entire backend | SpikeArrest without `Identifier` | All consumers share one threshold; one consumer can impact others. |
| Protect per partner | `Identifier` = verified client ID | Each partner has an isolated threshold, reducing noisy-neighbor contention. |
| Protect critical routes | Separate policy or conditional flow by path/method | Avoid applying one rigid threshold to both cheap GETs and heavy POSTs. |
| Differentiate service tiers | `Rate ref` reading from **trusted** config, e.g. managed API product/KVM | Never let callers pass `rate=100000ps` directly. |

**SpikeArrest does not replace** Cloud Armor/WAF, infrastructure protection, load balancing, autoscaling, or circuit breakers. Even a small number of CPU-intensive requests can cause overload; evaluate cost-per-request, timeouts, and backend backpressure.

### 3.3. Relationship to Latency

If a backend sustains at most 50 RPS stably with p99 under SLO, setting SpikeArrest to 100ps for a single app is unlikely to be safe. Base limits on **load tests** measuring p95/p99 latency, concurrent requests, payload sizes, and active consumer count.

For example, with three partners each allowed 10ps: theoretical aggregate traffic can reach **30ps** before counting other sources. If the total backend cap must stay at 20ps, add a separate global protection layer alongside per-client limits; setting three per-client limits does not automatically enforce a global cap.

## 4. `Quota`: Limiting Usage Over a Time Window

`Quota` governs total request consumption over a **time window**. It fits API product contracts like "1,000 calls/hour per app" or "100,000 calls/day," maintaining counters for reporting and rejecting requests once the quota is exhausted.

### 4.1. Example: 1,000 Requests/Hour per Client

~~~xml
<Quota name="Q-PartnerHour">
  <Identifier ref="verifyapikey.VAK-Partner.client_id"/>
  <Allow count="1000"/>
  <Interval>1</Interval>
  <TimeUnit>hour</TimeUnit>
</Quota>
~~~

In this example, each `client_id` verified by VerifyAPIKey gets its own quota. If you **omit** `Identifier`, the policy may share a single proxy-wide counter instead of per-partner counters. Never use an unverified `request.queryparam.partner` as the identifier, because clients can change it to bypass the quota.

**Reset timing** depends on the Apigee quota type and counting rules; never assume "every counter resets at 00:00 UTC" without explicitly configuring the calendar type and `StartTime`. For billing or strict contractual allowances, align on **window boundaries, counted units, billable operations, and retry policy** before deployment.

### 4.2. Quota Driven by API Product

Apigee lets you declare quotas on the **API product** or **operation**; to make the policy consume that configuration, `Quota` can reference the preceding authentication policy:

~~~xml
<Quota name="Q-FromProduct">
  <UseQuotaConfigInAPIProduct stepName="VAK-Partner">
    <DefaultConfig>
      <Allow>1000</Allow>
      <Interval>1</Interval>
      <TimeUnit>day</TimeUnit>
    </DefaultConfig>
  </UseQuotaConfigInAPIProduct>
</Quota>
~~~

`DefaultConfig` is only a **fallback when the API product does not define a corresponding quota**. For per-operation configs, precedence rules and **counter scope** (`PRODUCT`/`PROXY`) must be defined in the API product; **independent per-operation counters** may be created rather than a single shared bucket as operators sometimes assume.

Avoid accidentally running **both `Q-PartnerHour` and `Q-FromProduct`** on the same request when only one quota is intended: the two policies will enforce two separate limits. Choose one model aligned with the API contract and verify exactly which operations increment the counter.

### 4.3. How Quota Differs from SpikeArrest

| Criterion | SpikeArrest | Quota |
| --- | --- | --- |
| Goal | Smooth bursts / high rates over short intervals | Cap total usage over a time period |
| Thresholds | `10ps`, `100pm` | `1000/hour`, `100000/day` |
| Counted by | Proxy-wide or `Identifier` | Counters per proxy/app/product/operation per config |
| On exceedance | Faults immediately, typically mapped to **429** | Rejects once exhausted, typically mapped to **429** |
| Best fit | Protecting backend latency and capacity | Developer SLAs/contracts, fair-use caps |
| Interchangeable? | **No** | **No** |

A partner sending 1,000 requests in **one minute** might stay within a 10,000/day quota yet still overwhelm the backend; SpikeArrest handles the instantaneous burst. Conversely, an app calling steadily at 1 request/second will not trip a 10ps SpikeArrest yet will exhaust a 1,000/hour quota over time.

### 4.4. Flow Variables for Limit Feedback Headers

Quota populates variables such as:

~~~text
ratelimit.Q-PartnerHour.allowed.count
ratelimit.Q-PartnerHour.used.count
ratelimit.Q-PartnerHour.expiry.time
~~~

You can use `AssignMessage` to set response headers communicating remaining allowance/reset time. However, clarify their exact semantics, freshness, and header formatting rules; **never** place flow variables containing API keys or access tokens into responses. Counters and analytics reports may differ due to calculation timing, distribution, and policies; do not treat ad-hoc logs as a billing ledger without verifying reconciliation.

## 5. Attaching Policies to Flows in Safe Order

This example chooses **an API-key authentication model**, SpikeArrest, and per-app quota. Each policy resides in its own XML file, for example:

~~~text
apiproxy/
  policies/
    VAK-Partner.xml
    SA-Partner.xml
    Q-PartnerHour.xml
    AM-StripKey.xml
  proxies/
    default.xml
~~~

**Snippet** inside `ProxyEndpoint` (not a complete API proxy bundle):

~~~xml
<PreFlow name="PreFlow">
  <Request>
    <Step><Name>VAK-Partner</Name></Step>
    <Step><Name>SA-Partner</Name></Step>
    <Step><Name>Q-PartnerHour</Name></Step>
    <Step><Name>AM-StripKey</Name></Step>
  </Request>
  <Response/>
</PreFlow>
~~~

Policy to strip credentials before forwarding the request to the backend when the backend does not need the client key header:

~~~xml
<AssignMessage name="AM-StripKey">
  <Remove>
    <Headers>
      <Header name="x-api-key"/>
    </Headers>
  </Remove>
  <AssignTo createNew="false" type="request"/>
</AssignMessage>
~~~

**Processing order** in the request PreFlow runs top to bottom: verify → spike → quota → strip. Each policy's `name` matches `Step/Name`. An XML policy file added to the bundle but **not attached to a flow** does not execute merely by existing.

### 5.1. Avoid Running or Bypassing a Policy on the Wrong Endpoints

If `GET /health` is an internal check endpoint that does not require an API key, you can use a conditional step or separate route, but you must:

1. Allow only the **exact approved path and method**—never use overly broad patterns like "any path containing health."
2. Ensure all data/privileged endpoints remain protected in **every applicable flow**.
3. Account for encoded paths, query strings, trailing slashes, and target routing so `/admin` can never slip into the health branch.
4. Protect the health endpoint with ingress/network controls if it is not meant to be public.

Policy placement is part of **security review**. Use `continueOnError="false"` on core authentication/throttling policies so you never accidentally **fail open** if a policy errors.

### 5.2. Backend Protection Is Still Required

A valid API key at the proxy does not mean a private Cloud Run/GKE target will automatically accept the request. The target may require an **ID token/service identity, mTLS, private networking, or IAM** depending on backend type. That is a separate layer to design on the **TargetEndpoint/service callout** or supported network path. Never make a Cloud Run backend public just to "quickly fix" a proxy-to-backend auth failure.

## 6. Returning Consistent Errors Without Leaking Sensitive Information

When a policy fails, Apigee enters fault handling according to configuration. Use `FaultRules` and `DefaultFaultRule` or supported error standardization mechanisms to return consistent messages. Never set `continueOnError="true"` on VerifyAPIKey/OAuth/VerifyJWT just to let endpoints keep serving without credentials.

| Scenario | Typical HTTP Status | What the Response Should Say | Avoid |
| --- | --- | --- | --- |
| Missing/invalid/expired credentials | **401** | Authentication credentials are invalid | Printing keys/tokens, secrets, stack traces, or configs. |
| Valid principal not authorized for resource | **403** per authorization design | Insufficient permissions for the operation | Exposing internal backend policy details. |
| SpikeArrest or Quota exceeded | **429** | Rate/quota limit exceeded; retry per guidance | Promising inaccurate reset times or encouraging tight retry loops. |
| Backend temporarily overloaded | **503/502/504** by fault source | Service unavailable | Returning 401, which causes clients to keep rotating keys. |
| Policy config, key store, or management link failure | Typically **5xx** | Internal error code for correlation | Failing open or falsely reporting "quota exhausted." |

Actual HTTP statuses depend on the policy, fault variables, and your error mappings; **never assume every policy violation automatically returns your exact desired JSON/status**. Verify real responses in a test environment.

### 6.1. Sample Error Response Structure

An API contract can standardize on a JSON structure:

~~~json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Request exceeded the allowed limit",
    "requestId": "safe-request-id-for-lookup"
  }
}
~~~

You can use `AssignMessage` to construct the body/status and `RaiseFault` in custom validation branches; when handling faults from built-in policies, use FaultRules matched on exact `fault.name`/`errorcode`. In production, keep messages free of policy XML, sensitive JWT claims, or backend connection parameters.

If setting `Retry-After`, include it only when you know a **valid retry window** for the fault/quota type; retries with backoff and jitter are far better than clients hammering simultaneously at quota reset.

### 6.2. Do Not Let Policies Accidentally Leak API Keys

- Prefer receiving keys in **headers** and strictly over **HTTPS**.
- Strip key/token headers before sending to the target when the backend does not need them (if the backend needs the verified identity, pass a **gateway-generated identity context** with anti-spoofing protection rather than trusting client-supplied headers).
- Configure debug/log redaction; do not print full request headers, query strings, bodies, or flow variables holding secrets.
- Restrict who can use **Apigee Debug** and view data that may appear in traces.
- If a key leaks, revoke/regenerate it per procedure, notify the app owner, and audit abnormal behavior.

## 7. Controlled Lab: Authenticated and Throttled Partner API

**Goal:** within an **already provisioned Apigee lab organization and environment**, protect an API proxy pointing to a sample target; verify the sequence VerifyAPIKey → SpikeArrest → Quota. Do not create Apigee organizations or network infrastructure yourself in this lesson, as those resources carry separate **entitlement, connectivity, and billing** requirements.

### 7.1. Preparation

You need:

- A **test** Apigee organization, environment, and environment group with an HTTPS hostname routing to that environment.
- A lab API proxy and an HTTP backend capable of receiving test requests, such as an internal endpoint returning `200 OK`; never use a sensitive production backend.
- Sufficient Apigee permissions to create/edit policies and deploy proxies **in the lab environment**, and create API products and developer apps.
- Two **approved** developer apps/keys to verify per-consumer counter isolation.
- Apigee Proxy Editor UI or CI/CD pipeline managing the API proxy bundle, plus authorized access to Debug/analytics.
- Keep test traffic low; never run large load tests beyond authorized limits.

Before editing, confirm the **exact organization, environment, proxy revision, and base path**. If an existing proxy already has security policies, **do not overwrite them**; create a dedicated lab proxy or a reviewed configuration branch.

### 7.2. Create the API Product and Developer Apps

Perform in the UI or via your organization's management workflow:

1. Create a lab API product allowing only the defined **proxy and resource path `/partner/v1/courses`**.
2. Create developer/app A and developer/app B; associate each app with the API product and ensure status is **approved**.
3. Store each app's consumer key in an **appropriate secret store**—never commit to repos or paste in chat.
4. If configuring quota on the API product, note the **counter scope**, limit, and counted operations; in the initial lab, use a **fixed Quota** for straightforward observation.

**Important negative test:** using the key of an app **not authorized for this API product/resource** must be rejected even if that key is valid for another product.

### 7.3. Configure Policies for the Lab

Add three policies in the request PreFlow:

**`VAK-Lab.xml`**

~~~xml
<VerifyAPIKey name="VAK-Lab">
  <APIKey ref="request.header.x-api-key"/>
</VerifyAPIKey>
~~~

**`SA-Lab.xml`**

~~~xml
<SpikeArrest name="SA-Lab">
  <Identifier ref="verifyapikey.VAK-Lab.client_id"/>
  <Rate>2ps</Rate>
  <UseEffectiveCount>true</UseEffectiveCount>
</SpikeArrest>
~~~

**`Q-Lab.xml`**

~~~xml
<Quota name="Q-Lab">
  <Identifier ref="verifyapikey.VAK-Lab.client_id"/>
  <Allow count="5"/>
  <Interval>1</Interval>
  <TimeUnit>minute</TimeUnit>
</Quota>
~~~

Attach to the request PreFlow in order:

~~~xml
<PreFlow name="PreFlow">
  <Request>
    <Step><Name>VAK-Lab</Name></Step>
    <Step><Name>SA-Lab</Name></Step>
    <Step><Name>Q-Lab</Name></Step>
  </Request>
  <Response/>
</PreFlow>
~~~

These are **policy/flow configuration snippets**, not a standalone deployable API proxy bundle. Configure ProxyEndpoint/TargetEndpoint, routes, hostname, and revision properly, and run Apigee's XML/policy validation before deploying.

**Why 2ps rate and 5/min quota?** Those are intentionally low limits for quick verification, not production recommendations. SpikeArrest can reject a burst before the 5/min quota is exhausted—so **quota** tests must send requests slowly enough not to trip SpikeArrest.

### 7.4. Verify Valid Requests and Credential Errors

Set variables in a shell authorized to send requests to the lab Apigee hostname:

~~~bash
export API_BASE="https://YOUR_APIGEE_LAB_HOST/partner/v1"
export API_KEY_A="YOUR_LAB_APP_A_KEY"
export API_KEY_B="YOUR_LAB_APP_B_KEY"

# 1. Valid Key A within limits
curl --silent --show-error --include \
  -H "x-api-key: $API_KEY_A" \
  "$API_BASE/courses"

# 2. Missing key: must be rejected
curl --silent --show-error --include "$API_BASE/courses"

# 3. Invalid key: must be rejected
curl --silent --show-error --include \
  -H "x-api-key: invalid-lab-key" \
  "$API_BASE/courses"
~~~

**Never run with production keys** or paste shell commands containing keys into tickets or logs. Environment variables are illustrated for the lab; on shared machines, protect shell history/process logs and clear credentials afterward.

Expected: valid requests receive the backend response; missing/invalid key requests are blocked at the gateway before the target runs. Verify via **secret-redacted trace/Debug** and backend access logs, not just HTTP status codes.

### 7.5. Verify Quota and Per-App Counter Isolation

With `Q-Lab` allowing at most 5 requests/minute, after waiting past a window reset with no other traffic using key A:

~~~bash
# Send slowly so the quota test is not prematurely blocked by SpikeArrest
for i in 1 2 3 4 5 6; do
  curl --silent --show-error --output /dev/null \
    --write-out "A request $i: %{http_code}\n" \
    -H "x-api-key: $API_KEY_A" \
    "$API_BASE/courses"
  sleep 1
done

# Immediately test app B with a different key
curl --silent --show-error --include \
  -H "x-api-key: $API_KEY_B" \
  "$API_BASE/courses"
~~~

Expected: the **sixth request** from A within the same quota window is rejected, while B has its own quota and can still succeed. If not, check:

- Did any other requests use key A/B during the test?
- When does the quota window reset and which counter type does the policy use?
- Is `Identifier` actually `verifyapikey.VAK-Lab.client_id`, after VerifyAPIKey?
- Is another SpikeArrest or Quota policy running on the same flow?
- Do the API product and operation mapping match the resource?

**Do not insist that the sixth request must return one fixed body/status** if your organization uses custom FaultRules; record the actual response and fault code to compare against your design.

### 7.6. Verify SpikeArrest Independently of Quota

Wait for a fresh quota window or use another unconsumed lab app/key; send a **small, bounded** burst exceeding 2ps:

~~~bash
for i in 1 2 3 4; do
  curl --silent --show-error --output /dev/null \
    --write-out "burst $i: %{http_code}\n" \
    -H "x-api-key: $API_KEY_B" \
    "$API_BASE/courses" &
done
wait
~~~

Some requests may be rejected by SpikeArrest depending on counting, concurrency, algorithm, and proxy state. Use only four requests in the lab to demonstrate the principle; do not escalate to thousands of requests or load-test production just because the first attempt did not trigger 429.

### 7.7. Clean Up and Restore

When finished, **strictly for authorized lab-created resources**:

1. Save evidence free of keys/tokens: revision, policy names, flow order, request statuses, fault codes, quota metrics.
2. Undeploy **only the lab proxy revision** or restore the previous revision per change management.
3. Revoke test developer app credentials if no longer needed; remove the lab API product only if no other apps depend on it.
4. Confirm the lab backend is no longer receiving test proxy or automation calls.
5. Inspect Apigee analytics, consumed quota/cost, and logs that might contain sensitive data; handle per policy.

Never delete shared API products, apps, environments, or proxies just to "clean up" an exercise. This lesson **does not** ask you to create or delete real organizations; those carry much broader governance and cost scope than an API proxy.

## 8. Monitoring, Tuning, and Troubleshooting

### 8.1. Distinguishing Four Error Groups

| Symptom | Root-Cause Layer | Check First |
| --- | --- | --- |
| `401`, fault `InvalidApiKey`, or missing key | VerifyAPIKey | Is the app approved? Is the key right? Does the API product cover this proxy/resource/path? |
| `401`/`403` with Bearer token | OAuthV2/VerifyJWT or authorization | Issuer, audience, algorithm, expiry, scope, and policy-verified identity. |
| `429` before periodic quota is exhausted | SpikeArrest or another fault rule | `Rate`, `Identifier`, `UseEffectiveCount`, burstiness, and concurrent arrivals. |
| `429` after a steady number of requests | Quota | Window, count, counter scope, product/operation, app key, and retries. |
| `502/503/504`, high latency while policies pass | Target/egress or backend | Target URL, DNS/TLS, Cloud Run IAM, VPC path, timeouts, concurrency, and load tests. |
| `500` after adding a policy | XML, flow variable/step, policy entitlement, or config | Validation/deploy logs, Debug, policy names, and target environment. |
| App B shares quota with App A | Missing/unresolved Identifier or shared counter config | Verify VerifyAPIKey runs first, policy name/flow variable, and counter sharing. |
| Valid API key rejected on specific path | API product operation/resource mismatch | Product association, path suffix/method, app status, and proxy deployment. |

Always inspect the **fault code and error source** rather than concluding from HTTP status alone. For example, 429 can originate from SpikeArrest, Quota, or another gateway/load-balancer layer. If an issue begins right after deploying a new revision, diff flow order, names, and conditions against the previous revision.

### 8.2. Minimum Metrics

- **Gateway:** request counts by proxy/operation/app, p50/p95/p99 latency, policy faults, 4xx/5xx rates.
- **Security:** invalid/revoked keys, JWT issuer/audience failures, new clients, unusual paths, IAM and API product changes.
- **Traffic:** SpikeArrest violations and Quota violations by identifier, per-app usage vs. quota/contract.
- **Backend:** error rate, concurrency, CPU, connection pools, request processing time, and autoscaling behavior.
- **Cost:** request/API call volume, policy entitlements, Apigee capacity, traffic to backends, Cloud Logging/analytics, and supporting services.

Apigee provides API Analytics/Debug scoped by organization and access permissions. In production, restrict Debug permissions, configure **masking/redaction**, and enforce retention: a trace can inadvertently capture `Authorization` headers, `x-api-key`, client secrets, cookies, or sensitive payloads.

### 8.3. Limit Tuning Workflow

~~~mermaid
flowchart TD
    S["Measure per-app RPS/latency,<br/>backend capacity, and SLO"] --> D["Choose Rate / Quota / Identifier"]
    D --> TEST["Test in staging: valid/invalid,<br/>burst, reset, 429, key rotation"]
    TEST --> CAN["Deploy reviewed revision<br/>with heightened monitoring"]
    CAN --> G{"SLOs, security, and<br/>cost targets met?"}
    G -->|Yes| KEEP["Keep config, save baseline"]
    G -->|No| ROLLBACK["Roll back revision / policy<br/>per change plan"]
    KEEP --> S
    ROLLBACK --> S
~~~

**Do not simply raise `Rate` because a partner complains about 429s:** determine whether the partner was blocked by a 2ps burst, daily quota, non-idempotent client retry loops, or genuine backend capacity saturation. If you raise aggregate limits while a Cloud Run/GKE backend has low max instances or database connection caps, the gateway will admit more requests only for the target service to return more 503s.

### 8.4. Retries and Idempotency

API clients should handle 429/5xx with **exponential backoff, jitter, deadlines, and a retry budget**. For payment/registration POST operations, add an **idempotency key** and transactional handling: on timeout, the first request may have succeeded on the backend, so blind retries can create duplicate transactions.

If quota counts requests at proxy ingress, a request rejected by the backend or retried multiple times may still count toward usage depending on the chosen policy. Define **what constitutes a billable/counted unit** in the API contract and verify with tests; never assume "only 2xx responses consume quota."

## 9. Design Scenarios and Exercises

### Scenario A — Partner Consuming Backend Bandwidth

A course lookup API has three partners: Bronze, Silver, and Gold. The backend benchmarks at roughly **120 RPS** while keeping p99 under SLO; read requests have roughly comparable cost. Bronze sends irregular traffic with 300-request bursts at the top of each minute; Gold sends a steady 40 RPS. Propose:

1. A **global protection** threshold preventing backend saturation.
2. Per-app SpikeArrest thresholds tied to **verified app identity** or API product.
3. Per-tier quotas (e.g., daily) matching contracts.
4. How to verify Gold is not degraded when Bronze bursts.

**Guidance:** use **VerifyAPIKey** to verify app and product; **per-client SpikeArrest** to contain Bronze bursts; **Quota** to enforce tier totals; optionally add a global protection layer within proven backend capacity. Never simply divide 120 RPS evenly across three partners: leave headroom, account for read/write mix, concurrency, latency, and other traffic sources.

### Scenario B — Valid Token for the Wrong Audience

A partner sends an unexpired RS256-signed JWT using a valid key from JWKS. However, the token carries `aud=api-A` while calling `api-B`.

**Question:** should the request be accepted? Which policy settings protect against this?

**Suggested Answer:** **no** if B requires its own audience; `VerifyJWT` must enforce the expected `Issuer` and `Audience` for B, along with algorithm/keys and required claims. Checking the signature alone is insufficient to prevent tokens minted for service A from being replayed against service B.

### Scenario C — Quota Exhausted Despite Low Traffic

A developer app calls the API at 1 RPS and starts getting 429s after a while; SpikeArrest is `10ps` and quota is `1000/hour`.

**Question:** explain why 1 RPS still gets rejected and outline the investigation steps.

**Suggested Answer:** 1 RPS equals **3,600 requests/hour**, exceeding the **1,000/hour** quota without ever hitting 10ps. Distinguish rate/burst limits from total quota. Inspect the window, retries, counter scope, and app ID before raising the quota.

### Scenario D — Spoofed Identifier

A `Quota` policy uses `request.header.customer-id` as `Identifier`. Any client can change that header; after hitting 429, they simply supply another value and keep calling.

**Question:** identify the vulnerability and the fix.

**Suggested Answer:** untrusted identifier; replace it with `verifyapikey.<policy-name>.client_id` or a claim **verified** by a JWT/OAuth policy and normalized. Test quota isolation between two apps, key rotation, and empty flow variables; never rely on arbitrary client-supplied headers from the Internet.

### Scenario E — Proxy Upgrade Causes Spike in 401s

After adding JWT verification to PreFlow, every partner using an API key starts receiving 401s even though their keys are still valid.

**Question:** identify the most likely cause and two appropriate fixes.

**Guidance:** placing both `VerifyAPIKey` and `VerifyJWT` unconditionally in one PreFlow requires **both credentials simultaneously**. If the API contract allows **two independent auth methods**, design clear conditional flows/branches with anti-bypass guards; if the contract is migrating to JWT, run a migration plan, issue tokens, and coordinate with partners before cutover. Never set `continueOnError=true` so unauthenticated requests pass through.

## 10. Self-Check Questions

**1. Does an XML policy in the bundle run automatically?**  
No; it must be attached with a `Step` in the appropriate flow or execution hook.

**2. Does `VerifyAPIKey` authenticate end users?**  
Not by default. It verifies the app/key and API product/resource entitlement.

**3. Does `OAuthV2 VerifyAccessToken` verify any JWT from an external Identity Provider?**  
Not automatically; choose a token-verification policy matching the actual issuer and token format.

**4. Does `VerifyJWT` automatically strip the `Bearer` prefix when reading the default `Authorization` header?**  
Yes. However, when explicitly adding `<Source>` pointing to a header containing the prefix, the policy does not strip that prefix automatically.

**5. Distinguish a 20ps SpikeArrest from a 10,000/day quota?**  
20ps is a short-term rate/burst limit; quota is total requests over a period. A client can violate one without violating the other.

**6. What can happen if `Identifier` is omitted in Quota?**  
Requests may share a single proxy-wide counter rather than isolating per app.

**7. Why verify the order VerifyAPIKey → SpikeArrest/Quota?**  
So traffic policies key off **verified** identity variables rather than unpopulated variables or spoofed headers.

**8. Why avoid `continueOnError=true` on authentication policies?**  
It can allow unverified requests to continue (fail open) unless a separate branch explicitly blocks them.

**9. Is returning 429 enough for DDoS defense or backend load protection?**  
No. You need multi-layered protection, load testing, timeouts, IAM/network controls, and appropriate autoscaling.

**10. What is required for a proxy to enforce limits accurately per app's API product?**  
The app must be verified and linked to the right API product/operations; Quota must use the proper configuration/counter scope.

## 11. Official Documentation

- [Apigee — What are policies?](https://cloud.google.com/apigee/docs/api-platform/fundamentals/what-are-policies): policy XML, attachment, and responsibilities.
- [Apigee — Controlling proxies with flows](https://cloud.google.com/apigee/docs/api-platform/fundamentals/what-are-flows): PreFlow, conditional flows, PostFlow, and ordering.
- [VerifyAPIKey policy](https://cloud.google.com/apigee/docs/api-platform/reference/policies/verify-api-key-policy): API products, developer apps, and flow variables.
- [OAuthV2 policy](https://cloud.google.com/apigee/docs/api-platform/reference/policies/oauthv2-policy): VerifyAccessToken and scopes.
- [VerifyJWT policy](https://cloud.google.com/apigee/docs/api-platform/reference/policies/verify-jwt-policy): issuer, audience, keys/JWKS, Source, and claims.
- [SpikeArrest policy](https://cloud.google.com/apigee/docs/api-platform/reference/policies/spike-arrest-policy): Rate, Identifier, UseEffectiveCount, and bursts.
- [Quota policy](https://cloud.google.com/apigee/docs/api-platform/reference/policies/quota-policy): counters, time windows, and API product quotas.
- [AssignMessage policy](https://cloud.google.com/apigee/docs/api-platform/reference/policies/assign-message-policy): remove/add headers and build responses.
- [RaiseFault policy](https://cloud.google.com/apigee/docs/api-platform/reference/policies/raise-fault-policy): controlled faults.
- [Apigee policies reference](https://cloud.google.com/apigee/docs/api-platform/reference/policies/reference-overview-policy): policy categories and usage conditions.
- [Apigee security](https://cloud.google.com/apigee/docs/api-platform/security/overview): API proxy security, tokens, and access requirements.

Features, policy entitlements, quotas, traffic limits, and costs can vary across **Apigee, Apigee hybrid, organization/edition, and deployment time**. Before production use, verify official documentation, API product mappings, flow ordering, and error responses in an **approved environment**. A sound design proves that **unauthorized requests are blocked**, **legitimate partners cannot starve each other**, **backends stay protected during bursts**, and **access remains enforced at the business layer**.
