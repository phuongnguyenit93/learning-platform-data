# Idempotency Tokens, ETags, and Optimistic Concurrency Control

## 1. Two Risks in OCI Automation Applications

In the **OCI SDK and REST API with Java** chapter, calling APIs with valid syntax solves only part of the problem. An Oracle Cloud Infrastructure (OCI) automation application must also handle two common scenarios:

1. **Uncertainty over whether a prior operation succeeded.** The application sends a resource creation request, the service executes it, and the response is lost. Re-issuing it as a brand-new operation can create duplicate resources and unexpected costs.
2. **Stale data used for an update.** Two workers read the same configuration, each modifies part of it, and both submit updates. Without version checks, the later writer can silently overwrite the earlier writer's changes.

In OCI APIs that support them, `opc-retry-token` identifies a retried operation, while an ETag paired with `If-Match` checks version preconditions before updating or deleting. These two mechanisms solve different problems and can appear together in the same automation workflow. [Source: OCI REST APIs](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/usingapi.htm).

After this lesson, you will be able to:

- Distinguish retry tokens, ETags, request IDs, and business operation IDs.
- Persist and reuse a token for the same resource-creation intent.
- Use the Java SDK to read ETags and send conditional updates.
- Separate concurrency conflicts that require recomputation from transient errors safe to retry.
- Recover after timeouts without assuming the operation failed.
- Combine these mechanisms with IAM, observability, and application state management.

The running example is a Java service managing VCNs for learning environments. The service may run on Compute or OKE, store job state in Oracle Database / Autonomous Database, and update VCN freeform tags. The material focuses on API call correctness rather than building a full orchestration engine.

## 2. Distinguishing Four Types of Identifiers

| Value | What Does It Identify? | How It Is Used |
| --- | --- | --- |
| Business operation ID, e.g., `operationId` | Application intent, such as creating an environment for request 1042 | Primary key in an application-designed durable job ledger |
| `opc-retry-token` | One API operation retried within the service's support window | Keep constant when retrying the same operation; never reuse for a different intent |
| ETag | Version/representation of a resource returned by the service | Echo back verbatim in `If-Match` for conditional updates |
| `opc-request-id` | A single request for tracing and support investigation | Log alongside operation ID and outcome details |

For example, job `provision-env-1042` may require three create calls: VCN, subnet, and instance. The application tracks one `operationId` for the overall job, while each API call needs its own retry token if that API supports tokens. Never share a single token across all three operations merely because they serve the same environment.

Nor does a request ID replace a retry token. Two retries of the same operation have different request IDs yet belong to the same business operation. An ETag is not an authentication credential, and a retry token never bypasses IAM permissions.

## 3. Retry Tokens: Resending the Same Operation

### 3.1. The Lost-Response Scenario

Suppose a worker sends a VCN creation request with token `T1`:

```text
Worker                         OCI
  |                             |
  | CreateVcn, token=T1          |
  |---------------------------->|
  |                             | Creates VCN R1
  |        response lost        |
  |<-------------X--------------|
  |                             |
  | CreateVcn, token=T1          | Retry same operation
  |---------------------------->|
```

The token lets the service recognize that the subsequent request belongs to the previously submitted operation rather than executing another independent creation. `CreateVcnRequest` in the Java SDK exposes `opcRetryToken` for this purpose. [Source: CreateVcnRequest.Builder](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/core/requests/CreateVcnRequest.Builder.html).

The critical discipline lies in how the application creates the token:

```text
Correct:
    generate token once per operation
    persist operation and payload durably
    every retry reads the saved token

Wrong:
    generate a new UUID on every timeout and re-create the resource
```

If two workers process the same task and independently generate two tokens, the service has no way to know they represent the same business intent. The application must map that job to a single operation record.

### 3.2. Tokens Must Pair with Stable Intent and Payload

A token should be stored alongside application metadata:

| Application Field | Purpose |
| --- | --- |
| `operationId` | Key of the logical operation |
| `businessKey` | Link back to the originating business request |
| `operationType` | Distinguishes `CREATE_VCN`, `CREATE_SUBNET`, and other actions |
| `targetTenancy`, `region`, `compartmentId` | Captures exact target context for sending requests |
| `retryToken` | Value reused for that same operation |
| Finalized payload or payload fingerprint | Detects accidental payload changes on retry |
| `state`, `firstSentAt`, `lastAttemptAt` | Coordinates retries and unknown-outcome handling |
| Resource OCID, request ID, work request ID if any | Supports continuation and troubleshooting |

This is a recommended application state schema, not a list of required OCI request fields.

For instance, if the initial intent creates a VCN in compartment A with CIDR `10.90.0.0/16`, never reuse that token to create a different VCN in compartment B or change the CIDR. If business requirements change, decide explicitly whether to update an existing resource or start a new creation; never treat an old token as a "retry with different parameters" button.

A payload fingerprint is an internal verification mechanism. If hashing JSON, canonicalize serialization so key reordering does not look like a changed intent. This fingerprint does not replace HTTP request signatures and is not an OCI ETag.

### 3.3. Persist Before Sending to Recover Across Restarts

Recommended workflow with a durable job table:

```text
1. Find or create operation by business key with a uniqueness constraint.
2. In a database transaction:
       save finalized payload, retryToken, status PREPARED
   COMMIT.
3. Send the OCI request with the saved payload and token.
4. On a deterministic response:
       save resource OCID and corresponding state.
5. On timeout or connection loss:
       record UNKNOWN outcome if database is reachable;
       recovery worker reloads the same operation without generating a new token.
```

The uniqueness constraint should reflect business intent, such as the combination of environment and operation type. Leases or job claims help keep two workers from sending simultaneously, but they do not replace tokens: a worker can lose its lease after a request has already reached OCI.

If the process crashes after step 3 and before step 4, the database still holds the operation and its token for investigation or retry. Keeping the token only in RAM means a restart loses that link.

### 3.4. Expiration and Invalidated Tokens

Per OCI's retry token contract, tokens expire after 24 hours and can be invalidated earlier by conflicting actions, such as deleting the created resource from the system. It is not a permanent deduplication mechanism. [Source: Retry Token in REST APIs](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/usingapi.htm).

Once past the guarantee window or when encountering an invalidated token, never blindly swap tokens and resubmit just to clear the error. First determine:

- Does the resource from the prior creation attempt already exist?
- Did the application already record an OCID or success outcome?
- Is current business intent to resume tracking the existing resource or genuinely re-create it?
- Did a deletion or operational intervention invalidate the token?

Only after confirming a new side effect is needed should the application issue a fresh token per its workflow. For multi-day workflows, persist a durable mapping from business key to resource OCID rather than relying solely on token lifetimes.

## 4. Java Example: Creating a VCN with a Saved Token

### 4.1. Code Prerequisites

The example uses OCI Java SDK 3.x with `oci-java-sdk-core` and a chosen HTTP implementation. In a project importing the OCI BOM, the service dependency looks like:

```xml
<dependency>
    <groupId>com.oracle.oci.sdk</groupId>
    <artifactId>oci-java-sdk-core</artifactId>
</dependency>
```

The client requires an authentication provider, region, and appropriate IAM permissions. Illustrative initialization using a local profile:

```java
import com.oracle.bmc.auth.ConfigFileAuthenticationDetailsProvider;
import com.oracle.bmc.core.VirtualNetworkClient;

ConfigFileAuthenticationDetailsProvider auth =
        new ConfigFileAuthenticationDetailsProvider("DEFAULT");

try (VirtualNetworkClient client = VirtualNetworkClient.builder().build(auth)) {
    client.setRegion(auth.getRegion());
    // Call the create or update method shown below.
}
```

This client serves OCI Networking APIs. Persisting the operation in the database belongs to the application layer and happens before calling resource creation.

### 4.2. Submit Method Without Generating Tokens Internally

```java
import java.util.Objects;

import com.oracle.bmc.core.VirtualNetworkClient;
import com.oracle.bmc.core.model.CreateVcnDetails;
import com.oracle.bmc.core.requests.CreateVcnRequest;
import com.oracle.bmc.core.responses.CreateVcnResponse;
import com.oracle.bmc.retrier.RetryConfiguration;

public final class IdempotentVcnCreate {
    private IdempotentVcnCreate() {}

    public static CreateVcnResponse submit(
            VirtualNetworkClient client,
            CreateVcnDetails savedIntent,
            String savedRetryToken) {

        Objects.requireNonNull(client, "client");
        Objects.requireNonNull(savedIntent, "savedIntent");
        if (savedRetryToken == null || savedRetryToken.isBlank()) {
            throw new IllegalArgumentException("Saved retry token is required");
        }

        CreateVcnRequest request = CreateVcnRequest.builder()
                .createVcnDetails(savedIntent)
                .opcRetryToken(savedRetryToken)
                .retryConfiguration(
                        RetryConfiguration.SDK_DEFAULT_RETRY_CONFIGURATION)
                .build();

        return client.createVcn(request);
    }
}
```

`savedIntent` must be constructed from the operation's finalized payload. Example payload to create a learning VCN:

```java
CreateVcnDetails intent = CreateVcnDetails.builder()
        .compartmentId(compartmentId)
        .displayName("learning-env-1042")
        .cidrBlocks(java.util.List.of("10.90.0.0/16"))
        .freeformTags(java.util.Map.of("environment", "learning"))
        .build();
```

`cidrBlocks` is the CIDR list field on the current builder; choose a CIDR matching your lab network plan. [Source: CreateVcnDetails.Builder](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/core/model/CreateVcnDetails.Builder.html).

A UUID can be used to generate the token initially, but that generation belongs in the durable operation-creation step. When retrying the same operation, reload the old token and payload rather than regenerating a UUID inside `submit`.

The SDK supports request-level retry configuration. The example selects the SDK's default retry config for the VCN creation request; do not assume all Java SDK APIs retry identically when unconfigured. SDK retries also do not persist operations across process crashes. [Source: Java SDK Concepts — Retries](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/javasdkconcepts.htm).

Upon receiving `CreateVcnResponse`, save the OCID from `getVcn().getId()` along with the response's request ID. If saving to the database fails after OCI created the resource, recovery must still reconcile the existing operation. Never conclude the OCI call failed merely because the application's local commit failed.

## 5. ETags and the Lost-Update Problem

### 5.1. Two Workers Reading the Same Version

Suppose a VCN currently has two tags:

```json
{
  "environment": "learning",
  "owner": "team-a"
}
```

Worker A wants to add `costCenter=training`; Worker B wants to change `owner=team-b`. Both read the same initial snapshot and build a new tag map from it.

| Time | Worker A | Worker B | Resource State |
| --- | --- | --- | --- |
| t1 | Reads tags and ETag E1 | | Initial version |
| t2 | | Reads tags and ETag E1 | Initial version |
| t3 | Writes map with `costCenter` | | New version E2 |
| t4 | | Writes old map with updated `owner` | Risk of losing `costCenter` without version check |

Re-reading right before writing still leaves a race window: the resource can change between the two requests. The condition must be enforced by the service when accepting the update.

### 5.2. Reading the ETag and Sending `If-Match`

`GetVcnResponse` exposes both the resource and its ETag via `getVcn()` and `getEtag()`. `UpdateVcnRequest.Builder.ifMatch(...)` passes the precondition so the update succeeds only if the ETag still matches. [Source: GetVcnResponse](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/core/responses/GetVcnResponse.html), [UpdateVcnRequest.Builder](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/core/requests/UpdateVcnRequest.Builder.html).

Application flow:

```text
GET resource -> snapshot S1, ETag E1
compute update U1 from S1
UPDATE U1 with If-Match: E1

if succeeded:
    receive new snapshot/ETag if returned by the API
if ETag mismatch:
    do not blindly resend U1 with the new ETag
    re-read and decide whether intent can be recomputed or conflict must be reported
```

In the two-worker example, if A updates successfully first, B sending `If-Match: E1` is rejected because the version no longer matches. `412 NoEtagMatch` is the ETag conflict response documented by OCI. [Source: OCI API Errors](https://docs.oracle.com/en-us/iaas/Content/API/References/apierrors.htm).

Treat ETags as opaque values: never increment them, compare them for ordering, or infer timestamps or edit counts from them. Pass the exact value returned by the SDK/API into the next conditional request.

### 5.3. Having an ETag Is Not Enough if Writes Omit the Condition

An ETag does not lock the resource while the application computes changes. Another actor can still update the resource; the precondition detects the stale snapshot on the next conditional write.

If a writer deliberately omits `If-Match`, other writers cannot prevent overwrites caused by that unconditional write. In a multi-tool environment, standardize conditional updates or clearly assign ownership of configuration fields per tool.

Java `synchronized` only coordinates threads sharing that lock inside a single JVM process. It does not coordinate other pods, the Console, the CLI, or an independent infrastructure controller updating the same VCN.

## 6. Representation on the REST API

The HTTP snippets below only illustrate header and payload placement; they omit full headers and signatures required for live requests. When calling REST directly, you must still sign requests per the OCI signing contract. [Source: Request Signatures](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/signingrequests.htm).

Creating a VCN with a token:

```http
POST /20160918/vcns HTTP/1.1
Host: iaas.ap-singapore-1.oraclecloud.com
Content-Type: application/json
opc-retry-token: 92bb936d-cdaf-4509-8090-f349ff8f9adc
Authorization: <valid-signature>

{
  "compartmentId": "<compartment_ocid>",
  "displayName": "learning-env-1042",
  "cidrBlocks": ["10.90.0.0/16"]
}
```

Conditional update after reading the ETag:

```http
PUT /20160918/vcns/<vcn_ocid> HTTP/1.1
Host: iaas.ap-singapore-1.oraclecloud.com
Content-Type: application/json
If-Match: "example-etag-e1"
Authorization: <valid-signature>

{
  "displayName": "learning-env-1042-ready"
}
```

`example-etag-e1` is an illustrative placeholder, not a format to construct manually. In the Java SDK, pass the service-returned value via `.ifMatch(getResponse.getEtag())`.

In HTTP semantics, `If-Match: *` tests whether any representation exists rather than matching a specific ETag. Therefore, it does not enforce "the resource is still at the version I read." Use only the conditional request forms supported by the target API. [Source: RFC 9110 — If-Match](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.1).

Never attach `opc-retry-token` to arbitrary APIs assuming the service guarantees deduplication. Between the two builders used in this lesson, `CreateVcnRequest` has `opcRetryToken` while the `UpdateVcnRequest` example uses `ifMatch`; check each operation's contract before applying.

## 7. Java Example: Conditional Tag Updates by Business Intent

### 7.1. Define Intent Before Writing a Retry Loop

Instead of a vague request "write this tag map," the application specifies clearly:

> Change tag `owner` from expected value `team-a` to `team-b`, while preserving all other tags from the latest snapshot.

With this intent:

- If another tag changed, re-reading and rebuilding the map preserves that change.
- If `owner` is already `team-b`, the desired state is already met and no extra write is needed.
- If `owner` became `team-c`, report a business conflict instead of overwriting it.

This is an application policy in the example, not an automatic OCI behavior. A controller with exclusive ownership over the `owner` tag might choose a different rule, but must decide explicitly before retrying.

### 7.2. Illustrative Code

The example uses Java 17 and a `VirtualNetworkClient` already configured with an authentication provider and region. The method returns the `Vcn` observed or returned after updating. `expectedValue=null` expresses expecting the tag does not exist yet; `desiredValue` must be non-null.

```java
import java.util.ConcurrentModificationException;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ThreadLocalRandom;

import com.oracle.bmc.core.VirtualNetworkClient;
import com.oracle.bmc.core.model.UpdateVcnDetails;
import com.oracle.bmc.core.model.Vcn;
import com.oracle.bmc.core.requests.GetVcnRequest;
import com.oracle.bmc.core.requests.UpdateVcnRequest;
import com.oracle.bmc.core.responses.GetVcnResponse;
import com.oracle.bmc.model.BmcException;
import com.oracle.bmc.retrier.RetryConfiguration;
import com.oracle.bmc.waiter.MaxAttemptsTerminationStrategy;

public final class ConditionalVcnTags {
    private ConditionalVcnTags() {}

    public static Vcn compareAndSetTag(
            VirtualNetworkClient client,
            String vcnId,
            String key,
            String expectedValue,
            String desiredValue) throws InterruptedException {

        Objects.requireNonNull(client, "client");
        Objects.requireNonNull(vcnId, "vcnId");
        Objects.requireNonNull(desiredValue, "desiredValue");
        if (key == null || key.isBlank()) {
            throw new IllegalArgumentException("Tag key must not be blank");
        }

        RetryConfiguration oneUpdateAttempt = RetryConfiguration.builder()
                .terminationStrategy(new MaxAttemptsTerminationStrategy(1))
                .build();

        int maxConflictAttempts = 3;
        for (int attempt = 1; attempt <= maxConflictAttempts; attempt++) {
            GetVcnResponse snapshot = client.getVcn(
                    GetVcnRequest.builder().vcnId(vcnId).build());

            Map<String, String> current = snapshot.getVcn().getFreeformTags();
            Map<String, String> next = current == null
                    ? new HashMap<>() : new HashMap<>(current);
            String actualValue = next.get(key);

            if (Objects.equals(actualValue, desiredValue)) {
                return snapshot.getVcn();
            }

            if (!Objects.equals(actualValue, expectedValue)) {
                throw new ConcurrentModificationException(
                        "Target tag changed; re-evaluate intent");
            }

            String etag = snapshot.getEtag();
            if (etag == null || etag.isBlank()) {
                throw new IllegalStateException(
                        "Missing ETag; refusing unconditional update");
            }

            next.put(key, desiredValue);
            UpdateVcnRequest request = UpdateVcnRequest.builder()
                    .vcnId(vcnId)
                    .ifMatch(etag)
                    .updateVcnDetails(UpdateVcnDetails.builder()
                            .freeformTags(next)
                            .build())
                    .retryConfiguration(oneUpdateAttempt)
                    .build();

            try {
                return client.updateVcn(request).getVcn();
            } catch (BmcException error) {
                boolean etagConflict = error.getStatusCode() == 412
                        && "NoEtagMatch".equals(error.getServiceCode());

                if (!etagConflict || attempt == maxConflictAttempts) {
                    throw error;
                }

                // Next iteration must re-GET and recompute the payload.
                Thread.sleep(ThreadLocalRandom.current().nextLong(100, 401));
            }
        }

        throw new IllegalStateException("Exceeded conflict resolution limit");
    }
}
```

Example call inside a block managing the client lifecycle:

```java
Vcn result = ConditionalVcnTags.compareAndSetTag(
        client,
        vcnId,
        "owner",
        "team-a",
        "team-b");
```

Every conflict iteration re-GETs and rebuilds the map from the fresh snapshot. The code never keeps the old map and swaps only the ETag, as doing so would still erase changes made by another worker.

`UpdateVcnDetails` uses a builder that distinguishes unset fields from fields explicitly set to null. Thus, the example sets only `freeformTags`; never convert the entire fetched object into an update payload containing every field. [Source: UpdateVcnDetails](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/core/model/UpdateVcnDetails.html).

### 7.3. Limitations and Meaning of the Outcome

Conditions to keep in mind when using this method:

- This operation converges toward a desired state. If the tag already holds the target value, the method succeeds regarding observed state; it does not prove the caller itself wrote that value.
- Only `412 NoEtagMatch` enters the read-recompute loop here. Permission errors, timeouts, and other failures propagate to the outer orchestrator.
- Update retries are capped to 1 attempt in the retrier so conflict handling remains visible. `GetVcn` retains the client/SDK policy.
- Three attempts is an illustrative cap. Production code also needs an overall deadline, cancellation support, and contention metrics.
- The method does not persist operations to a database. The application layer owns persisting intent and outcome if crash recovery is needed.

`RetryConfiguration` lets you control termination and retry strategies in the SDK; capping attempts on a request is not a complete business recovery policy. [Source: RetryConfiguration Java API](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/retrier/RetryConfiguration.html).

## 8. Resolving Conflicts: When Is Recomputation Safe?

### 8.1. Changes to Independent Fields

If A adds `costCenter` while B changes `owner`, B can re-read the snapshot after A's update, preserve `costCenter`, and apply the `owner` update if business preconditions still hold. Safe recomputation depends on merge semantics, not just ETags.

Inspect maps and collections carefully. When an API accepts an entire collection on update, never assume it merely appends the entries sent. In the tags example, building the map from the latest snapshot avoids accidentally dropping unrelated keys.

If the intent is to delete a key, record the key to remove. After re-reading, remove that key from the current map instead of sending an old map missing unrelated entries.

### 8.2. Concurrent Edits to the Same Business Field

If A changes `owner` to `team-c` while B wanted to change `team-a` to `team-b`, B must re-evaluate because its business precondition no longer holds. Fetching the new ETag and writing `team-b` turns a detected conflict into an unreviewed overwrite.

Depending on the configuration type, an application can choose:

| Intent Type | Appropriate Policy |
| --- | --- |
| Drive a controller-owned tag to desired value | Re-read and converge within bounded retries |
| Change a field only if it still holds an approved value | Check prior value; report conflict if changed |
| Edit routes or security rules affecting multiple components | Recompute from current config and revalidate invariants |
| Submit edits from a long-open admin form | Show the newer version so the user decides how to merge |

An ETag signals that the version changed. Deciding whether that change allows reapplying the intent belongs to business logic or the controller.

### 8.3. Persistent Contention

If two controllers continuously fight to set a field to two different values, adding retries increases API traffic without resolving the disagreement. Clarify configuration ownership, unify the desired-state source, or serialize jobs for the same resource through a coordinator.

Per-resource-ID queues or leases can reduce contention among application-managed workers. Keep `If-Match` anyway to catch edits from the Console, CLI, or external tools outside that coordinator.

## 9. Timeouts During Conditional Updates

An important edge case occurs when the initial update using ETag E1 was accepted by the service—producing E2—but the response was lost. The application retries with E1 and receives `412`.

```text
GET -> state S1, ETag E1
UPDATE with E1 -> applied as S2, response lost
resend UPDATE with E1 -> may receive 412
```

The `412` on the retry indicates the ETag precondition failed on that attempt. It does not prove the first attempt failed, nor does it identify who created the newer state.

The orchestration layer must:

1. Preserve the original intent and record the outcome as unknown.
2. Re-GET the exact resource, region, and context under verification.
3. Compare current state against the target state and business preconditions.
4. If the target state is already satisfied, record success under a **state-convergence policy** if policy allows.
5. If the target state is not yet met and preconditions still hold, build a new request from the fresh snapshot/ETag.
6. If preconditions changed or cannot be verified safely, escalate to reconciliation or report a conflict.

When you need to know specifically "did *this* operation cause the effect," comparing final state alone may be insufficient. For example, if two actors both set a tag to the same value, final state cannot tell which actor wrote it. You also need operation history, persisted results, and tracing IDs.

Never drop `If-Match` after a timeout just to make the final request "guaranteed to go through." Doing so removes the safeguard against overwriting with a stale snapshot.

## 10. Retrying Transient Errors and Bounding Total Work

### 10.1. Do Not Retry All Errors the Same Way

| Outcome | Application Behavior to Consider |
| --- | --- |
| Timeout / connection drop after request may have been sent | Unknown outcome; preserve operation identity, use token or state reconciliation per API |
| `429 TooManyRequests` or retryable server error | Backoff with jitter; keep same token and intent |
| `412 NoEtagMatch` | Re-read and re-evaluate precondition; do not blindly resend stale payload |
| `409 IncorrectState` | Check resource state; retry only per operation contract |
| `409 InvalidatedRetryToken` | Investigate prior attempt and current intent before issuing a new token |
| Parameter, auth, or permission error | Fix root cause; avoid infinite retry loops |

OCI distinguishes error codes sharing an HTTP status; for example, `409 IncorrectState` has different retry semantics from `409 Conflict` or `409 InvalidatedRetryToken`. Read the service error code alongside HTTP status rather than checking only `status >= 400`. [Source: OCI API Errors](https://docs.oracle.com/en-us/iaas/Content/API/References/apierrors.htm).

### 10.2. Controlling Multi-Layer Retries

One Java call can be retried multiple times by the SDK retrier. If job runners and queues also retry outside it, request volume can exceed expectations.

Hypothetical calculation if each layer allows up to three attempts:

```text
3 job attempts
    × 3 application attempts per job
    × 3 SDK attempts per call
    = up to 27 HTTP attempts for that retried call
```

This is an illustrative calculation, not the SDK's default attempt count. It shows why an overall budget must be managed rather than configuring each layer in isolation.

For each operation type, define:

- Total deadline and max attempts per layer.
- Which errors belong to transport retries vs. business recomputation.
- Which tokens/payloads must remain immutable across layers and restarts.
- Stop conditions on deadline expiry, cancellation, or terminal resource state.
- Polling bounds and metrics during reconciliation.

Jittered backoff reduces synchronized retries across workers. It will not fix invalid payloads, missing IAM permissions, or two controllers fighting over conflicting desired configs.

## 11. Scope of Guarantees: One Request Is Not an Infrastructure Transaction

### 11.1. Multiple Resources Need Per-Step Workflow State

A workflow creating a VCN, subnet, instance, and database configuration can finish partially. The VCN creation token does not make the remaining three steps an atomic transaction. Nor does the VCN's ETag version-check the subnet or database resources.

The application must persist per-step state, created OCIDs, and recovery plans. If instance launch fails, you can fix and resume that step or compensate according to policy; never automatically delete all resources simply because one response dropped.

Examples across the OCI module:

- When creating Compute or database resources, check whether the operation supports retry tokens and record accepted resources.
- When updating storage resources, check the specific ETag/conditional headers supported by that API; do not assume ETags carry identical internal semantics across all services.
- When updating network configurations spanning multiple resources, verify preconditions per resource and coordinate workflow steps rather than treating one ETag as a VCN-wide lock.

### 11.2. Asynchronous Tasks Need Completion Tracking

Some OCI APIs return before a long-running operation completes. When an operation uses a work request, the response can supply `opc-work-request-id` to track progress via the service's work-request API. This ID is distinct from `opc-request-id` and retry tokens. [Source: Asynchronous Work Requests](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/workrequests.htm).

Do not infer that the task finished merely because a retried submission with a token returned a valid response. Distinguish:

```text
intent persisted
    -> API accepted operation
    -> resource/task in progress
    -> confirmed completion or failure
```

Not every operation returns a work request ID; for instance, the VCN creation code in this lesson does not read a work-request header unannounced by that response contract. Pick lifecycle polling or work-request tracking to match the API you call.

### 11.3. Conditional Deletion

Some delete APIs also support `If-Match`; `DeleteVcnRequest` exposes this field. It prevents deleting a resource based on a stale version, though it does not independently verify whether the user still intends to delete that resource. [Source: DeleteVcnRequest.Builder](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/core/requests/DeleteVcnRequest.Builder.html).

After a delete timeout, a `GET` failing to find the resource must be interpreted alongside error codes, permissions, and business intent. Never treat every `404` as proof deletion succeeded, since OCI may return an error code that does not distinguish nonexistent resources from unauthorized access.

## 12. Lab: Observing Tokens and ETags

### 12.1. Preparing the Environment

Choose a learning compartment, a test VCN, and an identity with VCN read/update permissions. Creation tests require matching create permissions. Never run illustrative updates against a VCN serving live applications.

Prepare a Java project with `oci-java-sdk-core`, authentication provider, region, and HTTP implementation. Lab logs should include operation ID, VCN OCID, attempt, read ETag, result code, and request ID; never log private keys or `Authorization` headers.

### 12.2. Observing a Deterministic ETag Conflict

To trigger deterministic contention, read two snapshots before executing the first update. The snippet below contains statements inside a method that already has `client` and `vcnId`, using the same request/model/response imports from the Java examples above.

```java
GetVcnResponse a = client.getVcn(
        GetVcnRequest.builder().vcnId(vcnId).build());
GetVcnResponse b = client.getVcn(
        GetVcnRequest.builder().vcnId(vcnId).build());

client.updateVcn(UpdateVcnRequest.builder()
        .vcnId(vcnId)
        .ifMatch(a.getEtag())
        .updateVcnDetails(UpdateVcnDetails.builder()
                .displayName("learning-writer-a")
                .build())
        .build());

client.updateVcn(UpdateVcnRequest.builder()
        .vcnId(vcnId)
        .ifMatch(b.getEtag())
        .updateVcnDetails(UpdateVcnDetails.builder()
                .displayName("learning-writer-b")
                .build())
        .build());
```

When both reads observe the same ETag and update A changes the ETag before update B runs, B must be rejected because its precondition no longer matches. Re-read the resource to inspect the current display name and ETag. VCNs allow updating display name and tags via API. [Source: Updating a VCN](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/update-vcn.htm).

Next, experiment with tags: have one worker change an unrelated key while the other calls `compareAndSetTag`. Observe the re-read preserving the first worker's new tag and applying the target update when the expected value still matches. Also test changing the target key to a third value to observe the business conflict.

### 12.3. Observing the Same Token Across Two Submissions

Create a test operation, saving the payload and token before sending. Submit `CreateVcn`, record the OCID, and call again with the exact same payload and token while the token remains valid. Cross-check the result against the API contract and verify no second independent VCN was created by the retry.

To simulate a dropped response, let your test harness discard the first call's return value after it completes and replay from the persisted operation. This simulates an application failure window, not all possible network failure modes. Reuse the exact old token to observe recovery behavior.

Do not generate a new token on the second submission in this exercise. To demonstrate the risk of using a different token, test with a model or mock first to avoid provisioning unintended resources outside the lab's scope.

### 12.4. Observation Criteria

| Scenario | Expected Design Outcome |
| --- | --- |
| Same create operation, same payload and token | Retry handled per the API's idempotency contract |
| Worker restarts after request was sent | Reloads token from the operation record |
| Update using an older ETag | Conflict detected instead of unconditional overwrite |
| Unrelated tag modified | Re-reads and recomputes map per policy |
| Target tag changed unexpectedly | Halts and reports business conflict |
| Timeout after an update that may have succeeded | Reconciles state instead of declaring failure from timeout alone |
| Retry budget exhausted | Preserves explicit state for investigation or coordinated resume |

## 13. IAM, Observability, and Availability

Idempotency and optimistic concurrency do not replace authorization. The Java identity needs permissions for the specific operations in the target compartment. Updating freeform tags requires resource-update permission; for VCNs, check `VCN_UPDATE` in the policy reference rather than assuming every `use` permission includes updating tags. [Source: Understanding Free-form Tags](https://docs.oracle.com/en-us/iaas/Content/Tagging/Concepts/understandingfreeformtags.htm).

Signals an application should track:

| Signal | Operational Meaning |
| --- | --- |
| `412` rate by resource type | Detects competing writers or snapshots held too long |
| Count of operations in `UNKNOWN` state | Tasks needing reconciliation before proceeding |
| Age of unresolved operations | Detects tasks approaching or exceeding the retry token window |
| Token changes per business key | Detects design bugs creating unintended new operations |
| Attempts and total processing time | Exposes multi-layer retries or excessive deadlines |
| Gap between operation count and created resources | Aids investigation of orphaned resources and cost risk |

Do not scale up worker counts just to drain a slow queue if all workers contend on the same resource. When conflict rates rise, reduce contention on that resource or fix configuration ownership first.

A durable operation ledger, stable retry tokens, and conditional ETags enable applications to resume cleanly after process failures. Combining them with bounded retries and observability prevents a minor transport glitch from turning into duplicate resources or prolonged configuration overwrite loops.

## 14. Principles to Apply

For create operations supporting retry tokens, **one API intent keeps one stable token across retries**, persisted alongside its payload and target context. For updates supporting ETags, **read a snapshot, compute the change, and write with that snapshot's `If-Match`**; on conflict, re-decide from fresh data and business preconditions.

In a Java service managing OCI, both mechanisms belong inside the same orchestration design: distinguish unknown outcomes from confirmed failures, persist OCIDs and task states, bound retries, and monitor actual resources. That gives automation for VCN, Compute, storage, or database services a sound foundation for crash recovery and concurrency control.
