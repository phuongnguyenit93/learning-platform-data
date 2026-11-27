# Distinguishing Authentication Errors, Permission Denials, and Disabled APIs

When a Java/Spring application on Google Cloud calls Cloud Storage, Secret Manager, BigQuery, or Cloud Run, failures often appear as **401 UNAUTHENTICATED**, **403 PERMISSION_DENIED**, **SERVICE_DISABLED**, or a brief message such as "The caller does not have permission". Although they all stop the application from completing its work, they have completely different root causes and fixes. Blindly granting the Owner role or enabling a batch of APIs as a "quick test" may fail to resolve the incident while introducing security risks.

This lesson explains how to identify the actual identity sending the request, distinguish authentication from authorization, find the API consumer project, inspect IAM policies on the exact resource, and read detailed error information. The examples use Google Cloud CLI, Cloud Audit Logs, and Java client libraries, and apply to Compute Engine, GKE, Cloud Run, and local environments. The focus is on **gathering evidence, fixing only verified root causes, and maintaining least privilege**.

## 1. Three Error Categories to Separate

| Error Category | Core Question | Common Symptoms | First Investigation Path |
| --- | --- | --- | --- |
| Authentication | Can Google verify the caller's identity? | Missing token, expired token, wrong audience, 401 | Credential source, token type, expiration, audience |
| Authorization | Is the authenticated caller allowed to perform the operation on the resource? | 403, permission denied, IAM denial | Actual principal, required permission, IAM policy on the resource |
| API not enabled (service enablement) | Is the API service enabled on the required consumer project? | 403 with SERVICE_DISABLED, API has not been used/enabled | Service name, consumer project, Service Usage status |

A 403 error **is not enough** to conclude a missing IAM role. Some APIs also return 403 when the API is disabled, VPC Service Controls blocks the request, or an organization policy forbids the operation. You must inspect the specific error details, especially the `reason` field in **google.rpc.ErrorInfo** if provided in the response.

Similarly, not every 401 means "not logged into gcloud": runtimes on Cloud Run, GKE, or VMs have their own identities and may not use your laptop's CLI session at all.

## 2. Decision Inspection Flow

~~~mermaid
flowchart TD
  A["A Google API call fails"] --> B{"Do DNS / TCP / TLS to endpoint work?"}
  B -->|"No"| NET["Investigate network, DNS, firewall, NAT, proxy"]
  B -->|"Yes"| C{"Is there a status or ErrorInfo?"}
  C -->|"401 / UNAUTHENTICATED"| AUTH["Check credentials, token, and audience"]
  C -->|"403 / SERVICE_DISABLED"| API["Check API enablement and consumer project"]
  C -->|"403 / PERMISSION_DENIED"| IAM["Check principal, permission, and IAM"]
  C -->|"403 / perimeter"| VPC["Check VPC Service Controls and policies"]
  C -->|"429 / 5xx"| QUOTA["Check quota, retries, and service health"]
  C -->|"Unknown"| DETAIL["Read error details, logs, and request metadata"]
  AUTH --> VERIFY["Apply minimal fix and retry"]
  API --> VERIFY
  IAM --> VERIFY
  VPC --> VERIFY
  QUOTA --> VERIFY
  DETAIL --> VERIFY
~~~

If the application cannot establish TCP/TLS connectivity, investigate the network path first; adding IAM roles will never fix a DNS timeout. Conversely, once you receive a structured error response from a Google API, the request most likely reached the API layer, so look for the identity, service enablement, or policy in the right place.

## 3. Reading Status Codes Together with Error Details

| HTTP / gRPC | Common Meaning | Avoid Assuming |
| --- | --- | --- |
| 401 / UNAUTHENTICATED | No valid credential or token rejected | Not necessarily a missing IAM role |
| 403 / PERMISSION_DENIED | Request denied by permissions or policy | Do not claim it is only a missing role |
| 403 + SERVICE_DISABLED | API is not enabled for the corresponding consumer | Do not fix by adding permissions on a bucket/secret |
| 404 / NOT_FOUND | Resource does not exist, wrong name, or API intentionally limits existence disclosure | Do not assume the resource was actually deleted |
| 429 / RESOURCE_EXHAUSTED | Quota/rate limit or capacity limit | Do not fix by re-authenticating |
| 5xx / UNAVAILABLE | Service or intermediate infrastructure failure | Do not assume IAM is wrong |
| DEADLINE_EXCEEDED | Did not complete within the deadline | Analyze network, server, retries, and timeouts |

Actual responses may differ between REST and gRPC. A Java client may throw an exception with the corresponding code rather than printing raw HTTP JSON. Never log just "call failed"; record the **service/method, status code, reason, project, and resource** so you can trace the root cause.

## 4. ErrorInfo Example: Disabled API Error

A REST response may contain a structure similar to this:

~~~json
{
  "error": {
    "code": 403,
    "message": "API has not been used in the consumer project or is disabled.",
    "status": "PERMISSION_DENIED",
    "details": [
      {
        "@type": "type.googleapis.com/google.rpc.ErrorInfo",
        "reason": "SERVICE_DISABLED",
        "domain": "googleapis.com",
        "metadata": {
          "service": "secretmanager.googleapis.com",
          "consumer": "projects/123456789"
        }
      }
    ]
  }
}
~~~

This is an **illustrative example**, not an actual incident record. When you see the reason `SERVICE_DISABLED`, identify the **service** being denied and the **consumer** indicated in the response. The `consumer` value may be a project number rather than a human-readable project ID.

Do not ignore these fields and look only at the 403 code. An IAM permission denied error can also return 403 without `SERVICE_DISABLED`; the remediation is different.

## 5. Identifying Which Identity the Caller Is Using

Google Cloud has multiple credential sources. Each source can point to a different principal and a different project:

| Execution Environment | Typical Identity | Pitfall |
| --- | --- | --- |
| Laptop, using gcloud CLI | Active account in gcloud config or service account impersonation | CLI succeeds while Java program uses a different ADC |
| Laptop, using Application Default Credentials | Credentials discovered by ADC in the environment | Stale local credentials, different quota project |
| Compute Engine | Service account attached to the VM via metadata server | VM uses default service account or restricted OAuth scopes |
| Cloud Run | Runtime service account of the revision/service | Confused with deployer identity or Cloud Build identity |
| GKE | Workload Identity Federation for GKE or workload credential mechanism | Confusing Kubernetes service account with Google IAM principal |
| CI/CD outside GCP | Workload Identity Federation or valid issued credential | Wrong audience/provider or impersonation chain |

**Development identity** is not **runtime identity**. For example, the deployer may have Secret Manager admin rights while the Cloud Run runtime service account only has bucket read access; when the app reads a secret, it still gets 403.

Before granting any role, answer: **which principal signed the failing request?**

## 6. gcloud auth and ADC Are Two Separate Credential Systems

The Google Cloud CLI uses its login configuration to call APIs from `gcloud` commands. Google Cloud client libraries typically use **Application Default Credentials (ADC)** according to the library's credential discovery mechanism.

Inspect the CLI:

~~~bash
gcloud auth list
gcloud config list
~~~

These two commands read `gcloud` authentication state and configuration. They **do not prove** that a Java program running on the same machine is using those credentials.

ADC typically looks for credentials in an order determined by the library and environment, usually including:

1. The **GOOGLE_APPLICATION_CREDENTIALS** environment variable, if set to a suitable credential configuration.
2. An ADC file generated in the development environment.
3. Credentials provided by the runtime via the metadata service when running on supported Google Cloud environments.

Do not assume every `GOOGLE_APPLICATION_CREDENTIALS` value points to a service account JSON key; it can also point to a Workload Identity Federation configuration. Avoid long-lived service account keys when federated identities or short-lived impersonation can be used.

A valuable test is running the exact credential-resolution code inside the same container/VM or failing environment, while **never printing access tokens or credential contents to logs**.

## 7. OAuth Access Token, ID Token, and API Key

Three credential types are frequently confused:

| Type | Used For | Common Mistake |
| --- | --- | --- |
| OAuth 2.0 access token | Calling Google APIs requiring OAuth, scoped to principal permissions | Sending an expired token or missing required scopes |
| OpenID Connect ID token | Proving identity to a recipient that verifies audience, such as an authenticated Cloud Run service | Using an ID token to call a Google API that requires an access token |
| API key | APIs that support project/app identification and quota or key-allowed access | Treating an API key as IAM permission to read private data |

An ID token can have a valid signature yet be rejected because its **audience** does not match the receiving service. An access token can be valid while the caller lacks permission on the resource. An API key does not replace IAM for private operations requiring user or service account authentication.

Never include tokens, API keys, or private keys in screenshots, tickets, or public logs. When inspecting tokens, prefer safe status and principal metadata rather than printing raw credentials.

## 8. 401 Authentication Errors: Investigation Procedure

When receiving 401 or UNAUTHENTICATED:

1. Identify the API endpoint and call method: REST, gRPC, client library, or proxy.
2. Determine whether the library uses ADC, explicitly configured credentials, or an API key.
3. Verify whether the runtime can reach a valid credential source—for example, the metadata service on a VM or Cloud Run.
4. Verify the right token type: an access token for Google APIs or an ID token with the exact audience for a receiving service.
5. Check token expiration, clock skew, and refresh mechanism; avoid manually caching tokens past their expiry.
6. With Workload Identity Federation, check the audience, provider, subject mapping, and any impersonation chain.
7. Retry the same small, non-destructive operation; if 403 appears afterward, inspect resource permissions.

If the application cannot obtain a token, the root cause may occur **before any request reaches the Google API**. For instance, an ADC failure to locate credentials raises a Java exception; the API may never have received a request. Do not report it as "Google API returned 401" if no HTTP response actually occurred.

## 9. 403 Permission Errors: Knowing the Exact Permission

IAM operates on principals, permissions, resources, and policies. A role is a collection of permissions; missing one specific permission does not justify granting a broad role.

Examples:

| Task | Typical Permission | Scope to Inspect |
| --- | --- | --- |
| Read a Cloud Storage object | `storage.objects.get` | Bucket or appropriate resource scope |
| List objects | `storage.objects.list` | Bucket or appropriate scope |
| Access a secret version | `secretmanager.versions.access` | Secret, project, or appropriate scope |
| Create a BigQuery query job | `bigquery.jobs.create` | Project running the job |
| Read BigQuery data | Appropriate table/dataset read permission | Dataset/table or service IAM model |
| Deploy Cloud Run | Appropriate Cloud Run admin permissions | Service/project plus permission to use the runtime identity |

These are illustrative permissions; an SDK operation may need additional permissions to fetch metadata, list, or create other resources. Look up the exact permissions for the method and read the error message before changing IAM.

**Resource boundaries matter.** Having a role on project A does not grant read access to a bucket in project B. A resource with its own policy may not be fully visible if you only inspect IAM policy at the project level.

## 10. Relationship Between IAM Allow, Deny, Conditions, and Boundaries

A permission can still be denied even if you see a relevant role assigned:

- The role is granted to a **different principal**, or group membership has not taken effect as expected.
- The role is granted on a **different project**, bucket, or service account.
- The binding has an **IAM Condition** that is not satisfied (time, resource, attributes).
- An **IAM Deny policy** applies at a relevant scope and denies the permission.
- A **Principal Access Boundary** or related access boundary restricts the resource.
- An organization policy or service-specific rule blocks the operation despite an IAM allow.
- The resource changed, was misspelled, or the API returns an opaque error to avoid leaking existence.

Evaluate **effective access** rather than simply scanning for a role name in a table. Google Cloud provides **Policy Troubleshooter for IAM** to analyze a principal, permission, and resource within supported scopes. Its output should be cross-checked against conditions at incident time, group memberships, policies, and error details.

Do not remove Deny policies/Conditions or add Owner just because a role "looks right." Identify the active policy and why it is denying access.

## 11. Disabled APIs: Distinguishing Usage Permissions from Enablement Permissions

To call many Google APIs, the corresponding service must be **enabled** on the API consumer project per service rules. Having permissions on a bucket or secret does not replace enabling the API.

Check enabled APIs in the consumer project:

~~~bash
gcloud services list --enabled \
  --project=CONSUMER_PROJECT_ID
~~~

Common service name examples:

~~~text
storage.googleapis.com
secretmanager.googleapis.com
run.googleapis.com
bigquery.googleapis.com
artifactregistry.googleapis.com
compute.googleapis.com
~~~

These are reference service names, **not** a list to enable everywhere for every application. Which APIs to enable depends on what the application actually uses and organizational policy.

Permission to **call an API** is distinct from permission to **enable an API**. Enabling an API typically requires a permission such as `serviceusage.services.enable` or an appropriate role such as Service Usage Admin within organizational controls. Do not grant Service Usage admin rights to a runtime identity just so an app can enable APIs at runtime.

Once you confirm the right API is disabled, submit a change request and have an authorized owner enable it in the correct consumer project. Then verify the updated state and retry. Do not rely on an arbitrary CLI project just because it happens to be the default on your laptop.

## 12. Three Frequently Confused Project Concepts

Multiple projects can be involved in a single API call:

| Project | Role | Example |
| --- | --- | --- |
| Resource project | Holds the accessed resource | Bucket/secret/dataset in a data project |
| Credential project | Associated with the principal or credential source | Project where the service account was created |
| Consumer/quota project | Used to identify the consumer for quota/billing/service enablement per API | Project reported in `ErrorInfo` |

They may be the same project, but not necessarily. For example, a Cloud Run app in an application project may read a Secret Manager secret in a security project using a runtime service account from the application project. Depending on the service, the API determines the consumer project from the credential, request, or quota project.

When `ErrorInfo` includes consumer metadata, **prioritize checking that exact project** instead of guessing from the resource project. Never swap the quota project to "bypass" API enablement or policies; changing the consumer affects quotas, billing, and IAM requirements.

## 13. Quota Project in Application Default Credentials

Local user ADC credentials may specify a separate **quota project**. An API call failure may relate to the project used for quota/billing or permission to use that project, rather than read permissions on the target resource.

Signs to watch for:

- `gcloud` commands succeed while the local Java client fails, or vice versa.
- Error messages reference an unexpected consumer project or quota project.
- Certain APIs explicitly require a quota project when using user ADC.
- The principal lacks permission to use the project for quota billing, such as `serviceusage.services.use` where applicable.

Before making adjustments, record the current configuration and identify which project is authorized as the consumer. You can configure the ADC quota project per Google Cloud documentation, but this alters your development environment and should be done deliberately.

Do not download a service account key to work around quota project errors. Safer alternatives include managed identities, impersonation, or Workload Identity Federation aligned with policy.

## 14. Compute Engine: Service Accounts and OAuth Scopes

A VM can have both an attached service account and OAuth access scopes. On certain API call paths from a VM, **effective permissions** are bounded by both IAM permissions and configured scopes.

Read-only VM inspection command:

~~~bash
gcloud compute instances describe VM_NAME \
  --project=PROJECT_ID \
  --zone=ZONE \
  --format="yaml(name,serviceAccounts,networkInterfaces)"
~~~

For example, a VM may have an IAM role allowing Cloud Storage reads, yet have overly restrictive scopes; the caller can still fail. Conversely, a broad `cloud-platform` scope **does not grant Owner**: IAM still governs permissions on every resource.

Verify the actual identity running the application, because a process may use `GOOGLE_APPLICATION_CREDENTIALS` instead of the VM's service account. Do not modify scopes or grant broader roles before confirming which credential path the code is using.

## 15. Cloud Run: Separating Deploy, Build, and Runtime Identities

Cloud Run typically involves at least three principal groups:

1. The user or pipeline **deploying** the revision/service.
2. The identity **building** the image (such as the Cloud Build service account when using Cloud Build).
3. The **runtime service account** attached to the Cloud Run service/revision when the container runs.

When a Java API on Cloud Run cannot read a secret, check the runtime service account first. Just because the deployer or Cloud Build service account can read the secret does not mean the runtime has that permission.

Inspect the service configuration:

~~~bash
gcloud run services describe SERVICE_NAME \
  --project=PROJECT_ID \
  --region=REGION \
  --format=yaml
~~~

Check which revision currently receives traffic and which identity is configured on that revision. If the application uses default ADC, it normally obtains credentials from the Cloud Run runtime metadata service; if code explicitly configures credentials, inspect that path.

**A deployment error involving `iam.serviceAccounts.actAs`** is separate from a runtime secret-access error. Service Account User/`actAs` permission lets the deployer attach a service account under supported conditions; it does not grant Secret Manager access to the runtime identity. Token-minting impersonation also uses distinct permissions and should not be conflated.

## 16. GKE: Kubernetes Service Account and Google IAM Principal

On GKE, Pods can use **Workload Identity Federation for GKE** to access Google Cloud APIs without distributing service account keys. Depending on the model, a workload can be identified directly by the principal bound to a Kubernetes service account (KSA) or impersonate a properly configured IAM service account (GSA).

When a Pod gets 401/403:

1. Identify the namespace, Pod name, and Kubernetes service account attached to the Pod.
2. Check that Workload Identity Federation is properly enabled/configured for the cluster and node pool where applicable.
3. Determine whether the actual caller principal is the KSA identity or an impersonated GSA.
4. Check the binding/impersonation conditions and the roles on the target resource.
5. Check API enablement on the consumer project and VPC Service Controls if applicable.
6. Compare old vs. new Pods after configuration changes and verify how the SDK retrieves credentials.

Read-only commands:

~~~bash
kubectl get pod POD_NAME -n NAMESPACE \
  -o jsonpath="{.spec.serviceAccountName}"

kubectl get serviceaccount KSA_NAME -n NAMESPACE -o yaml
~~~

A KSA annotation (in models that use annotations) does not guarantee that impersonation and IAM bindings are valid. Verify the actual token flow and permissions.

Do not copy a service account JSON key into a Kubernetes Secret to work around Workload Identity failures without a risk assessment and mandatory justification. Short-lived credentials and identity federation are generally safer.

## 17. Java Client: Categorizing Exceptions Instead of Swallowing Errors

Java client libraries typically resolve ADC automatically. Below is an example reading Cloud Storage object metadata and classifying the response:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageException;
import com.google.cloud.storage.StorageOptions;

public class InspectStorageAccess {
  public static void inspect(String bucket, String objectName) {
    Storage storage = StorageOptions.getDefaultInstance().getService();
    try {
      Blob blob = storage.get(BlobId.of(bucket, objectName));
      if (blob == null) {
        System.out.println("Object not found or empty response");
        return;
      }
      System.out.println("Object size: " + blob.getSize());
    } catch (StorageException e) {
      int code = e.getCode();
      if (code == 401) {
        System.err.println("AUTHENTICATION: check ADC/token");
      } else if (code == 403) {
        System.err.println("FORBIDDEN: analyze ErrorInfo, IAM, API enablement, and VPC SC");
      } else if (code == 429) {
        System.err.println("QUOTA/RATE LIMIT: check limits and retry");
      } else {
        System.err.println("Cloud Storage error code: " + code);
      }
    }
  }
}
~~~

This example demonstrates error classification, **not a complete application**. `StorageException` may not expose every `ErrorInfo` field in a human-readable format; when distinguishing `SERVICE_DISABLED` from an IAM denial, inspect exception details, library-supported responses, or server-side logs.

If ADC fails before constructing a request, an exception from credential creation/retrieval may occur without hitting `catch (StorageException)` in the snippet above. Production code must log root causes safely without logging tokens or JSON key contents, and design retries by error type rather than continuously retrying 401/403.

## 18. Cloud Audit Logs Help Verify Principals and Permissions

Audit logs can record:

- **authenticationInfo:** the caller identity observed by the service.
- **authorizationInfo:** checked permissions/resources and allow/deny outcomes where available.
- **serviceName, methodName:** the API and method invoked.
- **status:** outcome or error code.
- **resourceName:** the accessed resource within supported scope.

Reference filter in Logs Explorer:

~~~text
protoPayload.serviceName="secretmanager.googleapis.com"
protoPayload.status.code=7
~~~

Here, gRPC status code 7 corresponds to `PERMISSION_DENIED` in log records that use this `status` field. Field names and codes can vary depending on API, resource type, log type, and version; inspect a real log entry rather than assuming this filter captures every failure.

**Data Access audit logs may need to be enabled** for the relevant service and operation types, and the investigator must have log-viewing permissions. Not seeing a log entry does not prove a request was never sent: it may have failed before reaching the API, logging may be disabled, viewing permissions may be missing, or you may be looking in the wrong project.

## 19. Inspecting IAM Policies via CLI Without Modifying Permissions

Example of inspecting project IAM:

~~~bash
gcloud projects get-iam-policy RESOURCE_PROJECT_ID \
  --format=yaml
~~~

The output can be lengthy. Search for relevant roles, principals, and conditions, and avoid sharing full policies outside authorized channels. **Project IAM does not show all bucket/secret/dataset-level bindings or inherited deny/condition policies at parent levels.**

Inspect a service account:

~~~bash
gcloud iam service-accounts describe \
  RUNTIME_SA@PROJECT_ID.iam.gserviceaccount.com \
  --project=PROJECT_ID
~~~

This only confirms the service account exists along with basic metadata; it **does not prove** the service account has permissions on the target resource.

For a specific principal/permission/resource tuple, use Policy Troubleshooter or service-specific access-checking tools to inspect inherited policies, conditions, and deny rules. Never simply grep for a role name and assume access is sufficient.

## 20. Distinguishing Missing IAM Permissions from VPC Service Controls

**VPC Service Controls (VPC SC)** add an access perimeter around supported services to reduce the risk of unauthorized data exfiltration. A caller with full IAM permissions can still be denied by VPC SC if the request does not satisfy perimeter ingress/egress rules or other perimeter conditions.

Signs to check:

- The response mentions a service perimeter, VPC Service Controls, or provides a violation identifier.
- Requests from outside the perimeter fail while requests from workloads inside the perimeter succeed.
- Caller and resource IAM are both valid, yet cross-project/cross-perimeter requests are denied.
- Audit logs or violation logs contain matching details depending on logging configuration and viewing permissions.

To resolve, identify the perimeter, service, source, target, identity, ingress/egress policies, and business requirement. Analyze the violation and craft the minimal change with security review. **Never disable VPC SC or switch to another endpoint to bypass a perimeter** when it is a mandatory control.

Both VPC SC and IAM must be satisfied; being allowed by one does not automatically satisfy the other.

## 21. Disabled API vs. Permission Denied: A Practical Scenario

**Context:** A Cloud Run application in project `app-prod` uses its runtime service account to read a secret version in project `sec-prod`.

Scenario A — API disabled:

- Error details contain `SERVICE_DISABLED` with a specific consumer project.
- Service Usage in the consumer project shows Secret Manager API is not enabled.
- Even if the runtime has the Secret Manager Secret Accessor role on the secret, the call is blocked before the operation executes.
- Resolution: confirm the consumer project and ask an authorized owner to enable the API, then retry.

Scenario B — Missing permission:

- The API is enabled on the consumer project, but the request is denied because the principal lacks `secretmanager.versions.access` on the target secret.
- Audit logs/error details confirm the runtime identity and target resource.
- Resolution: grant the minimal appropriate permission/role at the narrowest scope allowed by organizational policy, then retry.

Scenario C — Authentication failure:

- The app has an altered credential config or sends an ID token of the wrong type when calling the Secret Manager API.
- The client lacks a valid access token or cannot refresh credentials.
- Resolution: fix the ADC/token flow rather than adding IAM roles.

Scenario D — VPC SC:

- Credentials are valid, the role is correct, and the API is enabled, but the request originates from a source that violates perimeter rules.
- Resolution: investigate the violation and design compliant ingress/egress rules.

These are **four independent scenarios**, even though the end user may only see a generic "Failed to load configuration" message.

## 22. Case Study: CLI Succeeds, Java Program Fails

An engineer runs a `gcloud` command successfully on their laptop, but a Java application accessing the same bucket receives 403.

Hypotheses to test:

1. `gcloud` CLI uses account A, while Java ADC uses account B or a different credential file.
2. Java ADC has an incorrect quota project, or the API is enabled on CLI's consumer project but not Java's.
3. The program runs inside an IDE/Docker container where `GOOGLE_APPLICATION_CREDENTIALS` differs from the terminal.
4. The SDK invokes a different operation than the CLI, requiring additional permissions.
5. The Java program accesses a different bucket, a different project, or a wrong resource path.
6. Environment-specific VPC SC, IAM conditions, or proxies differ.

**Procedure:** Record the active CLI identity, Java execution environment, ADC credential path, consumer/quota project, and the exact API method and resource. Compare these factors before changing IAM. Never conclude the Java client library is broken simply because two invocation methods yield different outcomes.

## 23. Case Study: Cloud Run Deploys Successfully, Runtime Fails

A pipeline deploys a Cloud Run service cleanly; when the first request arrives, the app returns 500 because it cannot fetch a secret.

Investigation:

- Build and deploy logs show the pipeline finished, which does not prove runtime permissions.
- Check the runtime service account on the revision receiving traffic.
- From the Java error, determine whether it is 401, 403, `SERVICE_DISABLED`, or a network issue.
- If 403, inspect roles on the **target secret**, not only IAM on the project hosting Cloud Run.
- If `SERVICE_DISABLED`, inspect the consumer project reported in `ErrorInfo`.
- If behavior differs across revisions, compare runtime identities, environment variables, secret references, and ADC configuration.

Fix the correct runtime principal or environment configuration, then validate with a canary revision before shifting full traffic. Do not grant Secret Manager permissions to the Cloud Build service account to fix a runtime error if it is not the principal calling the API.

## 24. Case Study: Only One GKE Namespace Gets 403

Two namespaces in the same cluster call a Google API; namespace A succeeds, while namespace B gets 403.

Investigation checklist:

- Do Pods in both namespaces actually use the same Kubernetes service account?
- Are the principals bound to the KSA/GSA identical?
- Are IAM bindings scoped by namespace, principal, or resource?
- Does namespace B have different NetworkPolicies or egress rules (if requests actually time out, check this path)?
- Does `ErrorInfo` report an IAM denial, disabled API, or perimeter policy?
- Is Workload Identity Federation configured consistently across node pools and workloads?

If B returns an API 403, a difference in NetworkPolicy alone is usually not the direct cause of an access denial; prioritize checking principal, IAM, and policies. If B times out before HTTP, go back to DNS/egress. Never change network policies and IAM roles simultaneously.

## 25. Applying Least Privilege When Fixing Errors

A permission fix decision should be phrased as:

> Principal P needs permission X to execute method M on resource R under condition C.

Instead of:

> The app got 403; grant Owner to make the error go away.

Remediation workflow:

1. Extract the actual principal from errors/logs and confirm the credential source.
2. Identify the denied API method, resource, and permission.
3. Inspect existing grants alongside parent-level policies, resource-level policies, conditions, and deny rules.
4. Choose the smallest predefined role that meets the need; use a custom role when an approved process exists.
5. Grant at the exact resource scope, record the ticket/approval, and set an expiration if temporary.
6. Re-test the real operation, inspect logs, and confirm policy enforcement.
7. Never leave broad temporary roles in place after closing the incident.

If the error is a disabled API, the person making the fix should be the Service Usage configuration owner, not the runtime service account. Likewise, if a token has the wrong audience, changing IAM roles will not produce a valid access token.

## 26. Do Not Infinitely Retry 401/403 Errors

Authentication and authorization errors are usually not transient errors that aggressive retries can fix. Infinite retries can cause:

- Inflated log volume and observability costs, obscuring the original failing request.
- Increased downstream load and user-facing latency.
- Repeated side effects in write workflows.
- Difficulty distinguishing a resolved issue from stale credential caches.

Classify handling as follows:

| Error | Handling Strategy |
| --- | --- |
| Expired token that library can refresh | Let the SDK refresh via supported mechanisms; bound retries |
| Misconfigured credential | Fix the credential source; do not retry infinitely |
| IAM permission denied | Stop/handle the failure; retry only after valid policy updates |
| API disabled | Wait for authorized enablement, confirm status, then retry |
| Transient 429 or 5xx | Bounded retries with backoff/jitter if the API operation is safe |

Tag the error category clearly in metrics so a wave of permission denials is not mistaken for a network outage. For operations with side effects, apply idempotency or deduplication mechanisms where supported by the service.

## 27. Post-Remediation Verification Scenario

After adjusting IAM or enabling an API, do not run a single trivial command and declare the application recovered. Verify across these layers:

1. **Credential:** the application obtains valid credentials and is not accidentally using local credentials in runtime.
2. **API enabled:** the appropriate service is enabled in the confirmed consumer project.
3. **Authorization:** the principal holds the exact permission on the right resource under applicable conditions.
4. **API response:** the actual business operation succeeds, not just TCP/TLS connectivity.
5. **Business logic:** returned values are accurate, and no private data is unexpectedly exposed.
6. **Monitoring:** 401/403 rates stop climbing, and no new errors appear due to policy changes.
7. **Regression:** related workflows continue working and audit logs remain sufficient for traceability.

With multiple revisions, Pods, or VMs, verify identities across every active serving group. An older instance may still be using different credentials or configuration from a newly started instance.

## 28. Investigation Runbook Table for 401/403/SERVICE_DISABLED

| Step | Question | Expected Evidence | If Missing / Failing |
| --- | --- | --- | --- |
| 1. Identify request | Which API, method, and resource? | Endpoint, timestamp, request/correlation ID | Collect application logs first |
| 2. Classify error | Is it 401, 403, 429, 5xx, or network? | HTTP/gRPC status, `ErrorInfo` | Do not modify policies before classifying |
| 3. Identify credential | ADC, runtime SA, WIF, or user token? | Principal and credential type | Fix auth flow if misconfigured |
| 4. Check consumer | Which project consumes API/quota? | `ErrorInfo`, client config | Reconcile projects |
| 5. Check API enablement | Is the right service enabled? | Service Usage status | Request enablement on the right project if missing |
| 6. Check IAM | Is the permission effective on the target resource? | IAM allow/deny, conditions, Policy Troubleshooter | Grant least-privilege role or fix policy with justification |
| 7. Additional policies | Are VPC SC, org policies, or scopes blocking? | Violation/error details | Remediate via security workflow |
| 8. Verify | Have operations and functionality recovered? | Response, logs, and business test | Continue root cause analysis |
| 9. Close incident | Were any broad permissions or secrets left behind? | Change record, IaC, audit | Revoke temporary permissions and update runbook |

## 29. Hands-On Exercise: Three Errors on Secret Manager

**Scenario:** A Spring Boot application needs to read a secret in a sandbox project. Distinguish the three failure modes in an approved environment without modifying production projects.

Tasks:

1. Record the service name, project, dummy secret, and application runtime service account.
2. Execute a passing baseline and record the response code, timestamp, and principal (never store tokens).
3. Introduce an invalid credential case **in an isolated test environment**, confirming an authentication error or pre-request failure.
4. Restore the credential, use a valid identity that lacks secret read permissions, and record the permission denied response.
5. Check service enablement on the sandbox consumer project; if the environment permits simulating a disabled API, follow approved change procedures rather than disabling a shared team API.
6. For each case, fill in the HTTP/gRPC code, `ErrorInfo` reason (if present), principal, consumer, and minimal remediation.
7. Re-test with the Java application to confirm ADC, networking, and IAM are all valid.
8. Inspect logs/audits and verify no temporary bindings or test credentials remain afterward.

Never proactively disable an API used by other applications. When `SERVICE_DISABLED` cannot be safely simulated, use a mocked response example to practice error classification and explicitly note that it is a mock.

**Deliverables:** a three-error comparison matrix, a principal/consumer/resource identification table, sanitized read-only `gcloud` inspection outputs, an IAM or API enablement decision, and a rollback runbook.

## 30. Common Mistakes

| Mistake | Consequence | Remedy |
| --- | --- | --- |
| Seeing 403 and adding Owner | Excessive privilege; may still fail on disabled API or VPC SC | Read `ErrorInfo` and locate the exact policy |
| Lumping 401 and 403 together as "missing permissions" | Fixing the wrong layer; credentials remain invalid | Check authentication first, authorization second |
| Checking only `gcloud` active account | Java ADC/runtime uses a different identity | Check credentials inside the actual process |
| Enabling APIs in the resource project by guesswork | Actual consumer project remains disabled | Use the consumer reported in error/config |
| Ignoring the quota project | `serviceusage.services.use` errors or wrong consumer | Identify quota project and corresponding permissions |
| Assuming `cloud-platform` scope grants all permissions | APIs still reject via IAM | Separate OAuth scopes from resource permissions |
| Granting secret access to the deployer instead of runtime SA | Cloud Run still fails at runtime | Separate deploy, build, and runtime identities |
| Treating KSA as GSA in every GKE cluster | Granting permissions to the wrong principal | Verify WIF identity and actual mapping |
| Ignoring IAM deny/conditions | Role looks valid yet requests stay blocked | Evaluate effective access and use policy troubleshooting |
| Disabling VPC SC to fix 403 | Breaks data security perimeter | Analyze the violation and make minimal policy changes |
| Logging tokens to debug | Credential leakage | Log only safe metadata |
| Infinite retries on 401/403 | Higher cost without fixing misconfiguration | Classify, stop, and fix the root cause |

## 31. Pre-Closure Incident Checklist

- Recorded exact API/method, project, resource, timestamp, and error code.
- Read `ErrorInfo` reason/metadata or equivalent details if provided by the API.
- Separated network errors from Google API responses.
- Verified the actual runtime principal rather than guessing from `gcloud auth list`.
- Checked token type, expiration, audience, and credential source for 401 errors.
- Distinguished CLI credentials, ADC, metadata service, and Workload Identity Federation.
- Identified resource project, credential project, and consumer/quota project.
- Verified API enablement on the actual consumer project without enabling unused APIs in bulk.
- Verified minimal permissions, binding scope, and IAM conditions for 403 errors.
- Checked deny policies, Principal Access Boundaries, organization policies, and VPC SC where applicable.
- Separated deployer, Cloud Build, and Cloud Run runtime service accounts.
- Verified KSA/GSA/Workload Identity mapping on GKE according to the active model.
- Checked OAuth scopes on VMs where applicable without treating them as IAM replacements.
- Used audit logs and Policy Troubleshooter within scope while understanding log limitations.
- Avoided granting Owner/Editor or disabling perimeters for a "quick test."
- Confirmed real operations and business journeys work reliably after remediation.
- Confirmed no unauthorized temporary tokens, keys, or IAM bindings remain.
- Documented root cause, IaC changes, regression tests, and accountable owner.

To troubleshoot Google API failures effectively, follow the sequence: **valid credentials → API enabled on the right consumer project → IAM permissions and policies allow access → correct business outcome**. Although `SERVICE_DISABLED`, missing IAM permissions, and VPC Service Controls denials all surface as 403, they require different owners and different fixes. Collecting the exact principal, project, permission, and `ErrorInfo` before acting lets operations teams restore service quickly without sacrificing security, auditability, or Google Cloud infrastructure stability.
