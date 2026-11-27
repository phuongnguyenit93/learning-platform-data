# Authentication, service identity, and event trigger permissions

> **Chapter:** Cloud Run functions and Eventarc  
> **Lesson:** Authentication, service identity, and event trigger permissions  
> **Module:** CLOUD_PROVIDERS_GCP

In the **CLOUD_PROVIDERS_GCP** module, learners explore Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage, and databases. Through deployment scenarios, learners learn how to choose services, secure resources, automate releases, and monitor reliability alongside cost. For **Cloud Run functions** and **Eventarc**, a core security requirement is determining **who can create a trigger, which identity the trigger uses to invoke the function, and what permissions the function uses once running**.

For example, when a new object is uploaded to Cloud Storage, it emits `google.cloud.storage.object.v1.finalized`. Eventarc routes the event to the Java function `invoice-event-handler`. For this flow to work securely, you must combine **event receiver permissions**, **Cloud Run invocation permissions**, **the function's runtime identity**, **Google service agent permissions**, and **deployer permissions**. Missing a single link can leave the trigger showing an active status while the function never receives events.

This lesson uses **Eventarc Standard** and Cloud Run functions deployed under the current Cloud Run model (equivalent in platform foundation to Cloud Functions 2nd gen). Project names, buckets, and accounts in the examples are placeholders only; IAM operations, function deployments, and trigger creation may incur costs and modify real permissions. Run only in an approved sandbox project. The content prioritizes **a clear IAM model, complete examples, and a reusable diagnostic approach**.

## 1. Learning outcomes

After this lesson, you will be able to:

1. Distinguish the **deployer**, **Eventarc trigger service account**, **Cloud Run function runtime service account**, and **Google-managed service agents**.
2. Explain **authentication** (identity verification) and **authorization** (permission checks) in the Eventarc → Cloud Run flow.
3. Grant `roles/eventarc.eventReceiver` and `roles/run.invoker` properly for triggers, and understand the exception for **direct Pub/Sub events**.
4. Explain why the Google Cloud Storage service agent may need `roles/pubsub.publisher` when emitting direct events to Eventarc.
5. Deploy a Java CloudEvents function, configure its runtime identity, and create a dedicated Eventarc trigger.
6. Use `gcloud` to inspect triggers, service IAM, project IAM, logs, and 401/403 errors.
7. Recognize misconceptions around **service account keys**, **ID tokens**, **access tokens**, **runtime ADC**, and **event payloads**.
8. Design least privilege, separation of duties, event deduplication, monitoring, and cost control.

## 2. Event flow and four identity layers

~~~mermaid
flowchart LR
    Dev["Deployer / CI"] -->|"Deploy and create trigger"| Ctrl["Cloud Run + Eventarc control plane"]
    Bucket["Cloud Storage bucket"] -->|"Object finalized"| StorageAgent["Cloud Storage service agent"]
    StorageAgent -->|"Source publisher permission"| Transport["Eventarc / Pub/Sub transport"]
    Transport -->|"Trigger identity + ID token"| Run["Cloud Run function<br/>private target"]
    TriggerSA["Trigger service account"] -. "Event Receiver + Run Invoker" .-> Transport
    TriggerSA -. "Authenticates invocation" .-> Run
    Run -->|"Runtime identity / ADC"| API["Cloud Storage, Pub/Sub, Secret Manager"]
    RuntimeSA["Function runtime service account"] -. "Least-privilege API roles" .-> API
~~~

**Four layers to keep separate:**

| Identity | Who does it represent? | Typical permissions |
|---|---|---|
| **Deployer / CI principal** | Person or pipeline creating the function and trigger | Deploy, create triggers, and `iam.serviceAccounts.actAs` on attached accounts |
| **Trigger service account** (user-managed) | Identity Eventarc uses when delivering events to the destination | `roles/eventarc.eventReceiver` when required; `roles/run.invoker` on the exact Cloud Run target |
| **Function runtime service account** | Identity Java code uses when calling Google Cloud APIs | `roles/storage.objectViewer` on the bucket or specific API roles if needed by the logic |
| **Google service agents** | Google-managed identities operating Eventarc/Cloud Storage/Pub/Sub/Cloud Run | Service-agent roles and `pubsub.publisher`/`serviceAccountTokenCreator` depending on source type |

**Do not use a single service account for the deployer, trigger, and runtime** just for convenience. The trigger only needs to **invoke the function**; it does not need to read every object or access Secret Manager. The function runtime only needs to **execute business logic**, not create Eventarc triggers.

## 3. Authentication, authorization, and identity in Cloud Run

### 3.1. Authentication vs. authorization

- **Authentication:** requires presenting valid credentials, identifying the principal calling the service.
- **Authorization:** determines whether that principal is allowed to perform a specific action on the resource.
- **Cloud Run Invoker:** `roles/run.invoker` includes `run.routes.invoke` permission to call a protected Cloud Run service/function.
- **Ingress policy:** restricts which network paths can deliver requests; separate from IAM Invoker.
- **Application authorization:** after a request reaches the Java handler, the application may still need additional authentication and authorization for business contents.

A **private** function is not callable merely because the caller is in the same VPC. Conversely, holding `roles/run.invoker` does not guarantee events arrive if the event source, transport path, network policy, or trigger filters are wrong.

### 3.2. Eventarc uses the trigger identity to invoke an authenticated function

An Eventarc trigger attaches **one service account**. When delivering an event to a Cloud Run function requiring authentication, Eventarc uses this identity via service mechanisms to issue a request carrying a valid **Google-signed ID token**. Cloud Run checks authentication and IAM **before the Java handler processes the CloudEvent**.

~~~text
Cloud Storage emits event
  → Eventarc filters event per trigger
  → Eventarc sends HTTP CloudEvent to Cloud Run
  → Cloud Run authenticates trigger identity
  → IAM checks roles/run.invoker on destination
  → Java CloudEventsFunction.accept(event)
~~~

**Common mistake:** an `ACTIVE` trigger does not prove the destination receives requests. If you forget `roles/run.invoker`, the trigger may be created successfully while deliveries fail with authentication/authorization errors.

### 3.3. Runtime service identity is the second layer

Once the function runs, Java code may need to fetch object contents, publish to Pub/Sub, call Firestore, or read Secret Manager. When using **Google Cloud Client Libraries**, the function typically obtains credentials via **Application Default Credentials (ADC)** from the **runtime service account attached to the Cloud Run revision**.

- **ID token**: suitable for invoking an authenticated Cloud Run target, with the matching `aud`.
- **OAuth 2.0 access token**: typically used to call Google APIs with the IAM permissions of a service identity.
- **Service account JSON key**: long-lived private credential, should never be embedded in containers/source, and is usually unnecessary in Cloud Run.
- **CloudEvent payload**: business data such as bucket/object names, **not a credential** and not proof that the caller is authorized.

Do not set `GOOGLE_APPLICATION_CREDENTIALS` pointing to a JSON key on Cloud Run just "to make the SDK recognize an account"; configure the runtime service identity with `--service-account` and grant least-privilege IAM.

## 4. IAM roles and where to grant them

| Principal receiving role | Role / permission | Reasonable scope | When needed? |
|---|---|---|---|
| Trigger creator | `roles/eventarc.admin` or appropriate custom role | Project managing Eventarc | Creating/updating/deleting triggers |
| Principal attaching service account | `roles/iam.serviceAccountUser` (`iam.serviceAccounts.actAs` permission) | **On the specific service account** | When assigning trigger/runtime/build identities |
| Deployer via Cloud Run source | `roles/run.sourceDeveloper` and `roles/serviceusage.serviceUsageConsumer`, plus required build roles | Deployment project | Creating/updating functions from source |
| Deployer via Cloud Functions v2 API | `roles/cloudfunctions.developer` or equivalent role | Deployment project | Only when using `gcloud functions` / Functions v2 API |
| **Trigger SA** | `roles/eventarc.eventReceiver` | Source/trigger project per model | Events from supported providers; **not required for Pub/Sub direct events** |
| **Trigger SA** | `roles/run.invoker` | **Target Cloud Run service** | Invoking a function requiring authentication |
| **Runtime SA** | e.g., `roles/storage.objectViewer` | Source bucket to read | **Only when Java actually downloads object data** |
| **Cloud Storage service agent** | `roles/pubsub.publisher` | Event source project per guide | Direct Cloud Storage events via Eventarc |
| **Eventarc service agent** | `roles/eventarc.serviceAgent` | Project | Google-managed transport/validation; usually auto-granted |
| **Pub/Sub service agent** (some older projects) | `roles/iam.serviceAccountTokenCreator` | Project/service account per guide | When the project enabled the Pub/Sub service agent **before 2021-04-08** |
| **Cloud Functions service agent** | `roles/cloudfunctions.serviceAgent` | Project | When deploying via the Cloud Functions v2 API |

**Important:** `roles/eventarc.serviceAgent` is for the **Google-managed Eventarc service agent**, not for the trigger SA or developers. Similarly, granting `roles/run.invoker` to the function's runtime SA **will not fix** a trigger failing to invoke the destination, because **the calling principal is the trigger SA**.

### 4.1. Direct Pub/Sub exception

When Eventarc receives **direct events from Cloud Pub/Sub**, documentation does not require granting `roles/eventarc.eventReceiver` to the trigger SA; the trigger still needs permission to **invoke the destination** if the target is private. Permissions for publishers to send messages to the Pub/Sub topic are a **separate concern** and do not arise automatically just because the trigger has Invoker.

### 4.2. Default Compute Engine service account is not a production choice

If no identity is specified when creating a trigger, Eventarc may use the **Compute Engine default service account** `PROJECT_NUMBER-compute@developer.gserviceaccount.com`. Older projects may have automatically granted Editor to this default account, whereas newer organizations often block this auto-grant via Organization Policy.

**Do not rely on default permissions.** Create a **user-managed trigger SA** and grant only the required roles; the function runtime should also use a separate user-managed SA.

## 5. Preparing the Eventarc → Java Cloud Run function lab

**Setup:** bucket `gs://BUCKET_NAME` in `asia-southeast1` emits object finalized events; Eventarc trigger `invoice-finalized` invokes Java function `invoice-event-handler` in the same region. The sample code only logs event metadata and **does not download object contents**, so the runtime does not need Storage Object Viewer.

| Component | Example value |
|---|---|
| Project | `PROJECT_ID` |
| Project number | `PROJECT_NUMBER` |
| Region | `asia-southeast1` |
| Source bucket | `BUCKET_NAME` already created in a compatible project/location |
| Function | `invoice-event-handler` |
| Trigger | `invoice-finalized` |
| Trigger SA | `evt-invoice@PROJECT_ID.iam.gserviceaccount.com` |
| Runtime SA | `fn-invoice@PROJECT_ID.iam.gserviceaccount.com` |
| Event type | `google.cloud.storage.object.v1.finalized` |

Prerequisites:

- Cloud Run, Eventarc, Eventarc Publishing, Cloud Build, Artifact Registry, Cloud Storage, and related APIs are enabled/permitted per procedure.
- The bucket for direct Cloud Storage events is in a **compatible project and region/multi-region** with the trigger, per Eventarc Standard requirements.
- The deployer has permissions to create functions/triggers and `iam.serviceAccounts.actAs` on the respective accounts.
- The build service account and Cloud Run service agent have the required deployment and Artifact Registry access permissions.
- IAM changes may take time to propagate; re-check after granting roles.
- Never use a production bucket containing user data for event experiments.

### 5.1. Pre-change inspection commands

~~~bash
gcloud auth list
gcloud config get-value project
gcloud projects describe PROJECT_ID --format="value(projectNumber)"

gcloud services list --enabled \
  --project=PROJECT_ID \
  --filter="NAME:eventarc.googleapis.com OR NAME:run.googleapis.com"

gcloud storage buckets describe gs://BUCKET_NAME

gcloud eventarc triggers list \
  --project=PROJECT_ID \
  --location=asia-southeast1
~~~

Read the bucket's actual location instead of guessing from its name. In this lesson, all resource-writing commands include `--project=PROJECT_ID` where supported by the CLI.

## 6. Step 1 — Create two service accounts with distinct responsibilities

**Commands in sections 6–9 modify real IAM, functions, and triggers**; run only when authorized in a sandbox project.

~~~bash
# Identity Eventarc uses to invoke the function.
gcloud iam service-accounts create evt-invoice \
  --project=PROJECT_ID \
  --display-name="Eventarc invoice trigger identity"

# Identity the Java function uses at runtime.
gcloud iam service-accounts create fn-invoice \
  --project=PROJECT_ID \
  --display-name="Invoice function runtime identity"
~~~

Then verify:

~~~bash
gcloud iam service-accounts describe \
  evt-invoice@PROJECT_ID.iam.gserviceaccount.com \
  --project=PROJECT_ID

gcloud iam service-accounts describe \
  fn-invoice@PROJECT_ID.iam.gserviceaccount.com \
  --project=PROJECT_ID
~~~

**Do not grant `roles/editor` or `roles/owner` to either account.** The trigger SA does not need Storage Object Viewer for this function. The runtime SA does not yet need Storage permissions because the code only reads metadata already inside the CloudEvent.

## 7. Step 2 — Grant proper trigger and Cloud Storage source permissions

### 7.1. Eventarc Event Receiver for the trigger SA

For **Cloud Storage direct events**, grant:

~~~bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:evt-invoice@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/eventarc.eventReceiver"
~~~

This role is granted **at the project level** per Eventarc documentation. It does **not** allow the Java runtime to read objects or create new triggers.

### 7.2. Cloud Storage service agent needs Pub/Sub Publisher

Eventarc Standard uses **Pub/Sub as the transport** for many sources. For direct Cloud Storage events, the **Cloud Storage service agent of the bucket's project** needs publish permission for event transport.

Retrieve the service agent email (the command may **initialize the agent** if it does not yet exist):

~~~bash
gcloud storage service-agent --project=PROJECT_ID
~~~

Replace `STORAGE_AGENT_EMAIL` with the returned email, then grant:

~~~bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:STORAGE_AGENT_EMAIL" \
  --role="roles/pubsub.publisher"
~~~

This is the **Cloud Storage** service agent, not `evt-invoice@...` and not `fn-invoice@...`. Do not grant Pub/Sub Publisher to every service account just to test one trigger.

### 7.3. Remaining service agents

- **Eventarc service agent:** typically holds `roles/eventarc.serviceAgent` automatically when Eventarc creates its first resource. If revoked, restore the role on `service-PROJECT_NUMBER@gcp-sa-eventarc.iam.gserviceaccount.com` via your IAM administrator.
- **Pub/Sub service agent:** if enabled **before April 8, 2021**, it sometimes needs `roles/iam.serviceAccountTokenCreator` for authenticated push flows. Do not grant this role broadly out of habit in newer projects.
- **Cloud Functions service agent:** when deploying with `gcloud functions` or the Functions v2 API, holds `roles/cloudfunctions.serviceAgent`. With modern `gcloud run deploy`, verify the corresponding Cloud Run source deploy and build permissions.

**Distinction:** Google service agents are created and managed by Google, whereas `evt-invoice` is a user-managed SA you created. Some agents only appear after an API is enabled and used for the first time.

## 8. Step 3 — Write a minimal Java CloudEvents function

Assumed project layout:

~~~text
invoice-event-handler/
├── pom.xml
└── src/main/java/functions/InvoiceEventHandler.java
~~~

### 8.1. Java code that accepts no sensitive data from callers

~~~java
package functions;

import com.google.cloud.functions.CloudEventsFunction;
import io.cloudevents.CloudEvent;
import java.util.logging.Logger;

public final class InvoiceEventHandler implements CloudEventsFunction {
    private static final Logger log =
            Logger.getLogger(InvoiceEventHandler.class.getName());

    @Override
    public void accept(CloudEvent event) {
        if (event == null || event.getId() == null
                || event.getType() == null || event.getSource() == null) {
            throw new IllegalArgumentException("Missing CloudEvent metadata");
        }

        String eventId = event.getId();
        String eventType = event.getType();
        String source = event.getSource().toString();

        // Demo: log metadata; do not log full payloads or secrets.
        log.info(() -> "eventId=" + eventId
                + " type=" + eventType + " source=" + source);
    }
}
~~~

This sample uses **Functions Framework for Java** and CloudEvents. The handler reads only **CloudEvent metadata**, without treating event payloads as inherently "trusted instructions." When a real app reads objects using bucket/name from an event, it must validate a bucket allowlist, event type, object generation, and idempotency; never let arbitrary events trick the app into reading out-of-scope resources.

### 8.2. Maven POM for Java 21

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.example</groupId>
  <artifactId>invoice-event-handler</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>com.google.cloud.functions</groupId>
      <artifactId>functions-framework-api</artifactId>
      <version>1.0.4</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

`1.0.4` is the Functions Framework API version in the documentation example; verify current versions and dependency compatibility for production use. The code only activates when `--function` points to `functions.InvoiceEventHandler`. Test the build first:

~~~bash
mvn -version
mvn clean package
~~~

No JSON service account key is needed in the POM. If your enterprise uses an Artifact Registry Maven repository for dependencies, Maven also needs **Reader IAM** and an appropriate credential helper in the build environment.

## 9. Step 4 — Deploy the private function and grant Invoker

### 9.1. Setting the runtime service identity at deploy time

Inside the Java project directory, run (this command **modifies resources**):

~~~bash
gcloud run deploy invoice-event-handler \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --source=. \
  --function=functions.InvoiceEventHandler \
  --base-image=java21 \
  --service-account=fn-invoice@PROJECT_ID.iam.gserviceaccount.com
~~~

This is the **Cloud Run functions** syntax for deploying directly from source under current guidance. Omit `--allow-unauthenticated` to keep the function **private**. If deploying via `gcloud functions deploy` / Functions v2 API, a different set of flags and permissions applies; do not mix examples.

The **deployer** needs `iam.serviceAccounts.actAs` on the runtime SA plus appropriate build/deploy permissions. Service account `fn-invoice` only needs the business permissions it actually uses. Deploy permission **does not automatically imply** runtime invocation permission.

### 9.2. Grant `roles/run.invoker` on the exact Cloud Run service

~~~bash
gcloud run services add-iam-policy-binding invoice-event-handler \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --member="serviceAccount:evt-invoice@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
~~~

**This is a mandatory step in the private destination pattern.** Grant the permission on the **underlying Cloud Run service**, not `roles/cloudfunctions.invoker` from the Cloud Functions 1st gen model. Use project-wide Invoker only when requirements and risks are explicitly approved; service-level scoping prevents one trigger from invoking other functions.

Verify:

~~~bash
gcloud run services get-iam-policy invoice-event-handler \
  --project=PROJECT_ID \
  --region=asia-southeast1

gcloud run services describe invoice-event-handler \
  --project=PROJECT_ID \
  --region=asia-southeast1
~~~

Inspect the runtime service account, ingress, Cloud Run target URI, and the IAM binding for `evt-invoice`. Do not assume the trigger has invoke access merely because the function shows `Ready`.

### 9.3. An easy-to-make mistake

If you grant `roles/run.invoker` to `fn-invoice@...` (runtime SA) instead of `evt-invoice@...` (trigger SA), events will still be blocked at Cloud Run authentication. **The runtime SA is not the caller of Eventarc deliveries**.

## 10. Step 5 — Create an Eventarc trigger with a dedicated identity

~~~bash
gcloud eventarc triggers create invoice-finalized \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --destination-run-service=invoice-event-handler \
  --destination-run-region=asia-southeast1 \
  --event-filters="type=google.cloud.storage.object.v1.finalized" \
  --event-filters="bucket=BUCKET_NAME" \
  --service-account=evt-invoice@PROJECT_ID.iam.gserviceaccount.com
~~~

**Prerequisites for this example:**

- `BUCKET_NAME` is only the bucket name **without `gs://`** in the event filter.
- The source bucket is in a location compatible with the Eventarc trigger; Cloud Storage direct events have project/location constraints.
- `evt-invoice` holds Event Receiver for the GCS provider and Invoker on the function.
- The Cloud Storage service agent holds Publisher, and the Eventarc agent still has its operational permissions.
- No trigger with the same name already exists in the same project/location.

Inspect:

~~~bash
gcloud eventarc triggers describe invoice-finalized \
  --project=PROJECT_ID \
  --location=asia-southeast1

gcloud eventarc triggers list \
  --project=PROJECT_ID \
  --location=asia-southeast1
~~~

Check `serviceAccount`, `eventFilters`, destination, transport, and status/conditions. A newly created trigger may need **propagation time** to start working; inspect logs/metrics if no events appear yet rather than repeatedly changing IAM.

## 11. Step 6 — Trigger an event and verify the result

**The action below uploads a test object to Cloud Storage and may incur charges:**

~~~bash
printf "invoice event lab\n" > invoice-test.txt

gcloud storage cp invoice-test.txt \
  gs://BUCKET_NAME/lab/invoice-test.txt
~~~

Check function logs:

~~~bash
gcloud run services logs read invoice-event-handler \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --limit=100
~~~

Expect to see metadata similar to:

~~~text
eventId=... type=google.cloud.storage.object.v1.finalized
source=//storage.googleapis.com/projects/_/buckets/...
~~~

If the function receives multiple events, do not automatically treat it as an IAM failure. Eventarc/Pub/Sub typically exhibit **at-least-once** semantics with retries depending on mechanism/configuration; the handler must implement **idempotency**. For Cloud Storage events, use `event.source + event.id` or a combination of bucket/object/generation to determine if the work was already processed. Do not use object name alone if the same name can have multiple generations.

### 11.1. HTTP function invocation is not Pub/Sub publishing

- When **Eventarc** invokes a private Cloud Run function, **`roles/run.invoker` is needed by the trigger SA**.
- When a **user wants to call HTTP directly**, that caller also needs appropriate auth/Invoker and an **ID token with the right audience**. You can test using `gcloud run services proxy` or a separately guided flow.
- When the **Java function code** itself calls a Google Cloud API, it uses **runtime SA + ADC**.

Do not grant `allUsers` Invoker just to test when the trigger is still getting 403; identify the wrong principal or missing IAM binding instead.

## 12. Event source, trigger, and runtime: choosing permissions by scenario

| Scenario | Trigger SA | Source service agent | Runtime SA |
|---|---|---|---|
| **Cloud Storage finalized → private function** | Event Receiver + Run Invoker | Storage SA needs Pub/Sub Publisher | Needs Storage Object Viewer only if code downloads objects |
| **Pub/Sub direct event → private function** | Run Invoker; Event Receiver **not required** for this source | Publisher needs permission to publish to the Pub/Sub topic | Business permissions only; no Pub/Sub Subscriber needed when event is delivered via handler |
| **Cloud Audit Logs event → private function** | Event Receiver + Run Invoker | Eventarc agents/transport path per provider | Business permissions only |
| **Function A calls HTTP function B** | No Eventarc needed for direct call | Not applicable | A's runtime SA must hold Run Invoker on B and send a valid ID token |
| **Public HTTP webhook** | No Eventarc trigger | Not applicable | Runtime SA remains minimal; auth/signature and app-level authorization required |

**Grant only the necessary roles.** If the Java consumer only logs CloudEvent metadata like in the lab, do not grant `roles/storage.admin` or `roles/pubsub.admin`. If the handler must read object contents, grant `roles/storage.objectViewer` on **that specific bucket**, not across the entire organization.

## 13. Common misconfigurations and how to diagnose them

| Symptom | Likely causes | Verification step |
|---|---|---|
| Trigger `ACTIVE` yet function receives no events; HTTP 403 | Missing `roles/run.invoker` for **trigger SA** | `gcloud run services get-iam-policy` |
| Trigger creation fails with permission denied | Deployer lacks Eventarc/`iam.serviceAccounts.actAs` permissions | IAM of trigger-creating principal and service account |
| Trigger creation fails on Eventarc service agent | New agent not ready or lost `roles/eventarc.serviceAgent` | Check project number, Eventarc agent, and policy |
| GCS direct event never appears | Cloud Storage service agent lacks `roles/pubsub.publisher`; wrong bucket/filters | Storage service agent, project IAM, trigger filters |
| Pub/Sub direct event only, still fails invoke | Missing Invoker, not Event Receiver | Trigger SA IAM on target |
| Function gets 403 reading object | Runtime SA lacks Storage Viewer or object IAM/policy | Application logs, bucket IAM, runtime identity |
| Console HTTP test returns 403 | Caller lacks ID token/Run Invoker | Distinguish user test from Eventarc caller |
| Event received but Java throws 500 | Code bug, dependency, Secret, API quota, or input | Cloud Run request/application logs |
| Duplicate events arrive | At-least-once delivery or retries | Deduplication by event ID/source/generation |
| Source deployment fails | Build SA lacks Artifact Registry, Cloud Build, or `actAs` permission | Build logs + deployer/build SA IAM |
| `404` or wrong destination | Trigger targets wrong service/region/path | `eventarc triggers describe` and `run services describe` |
| Trigger created but events arrive slowly | IAM propagation, trigger initialization, or source delay | Eventarc/Cloud Run metrics, check timestamps |
| Cross-project service account rejected | Missing cross-project identity config / org policy | Cross-project SA docs, IAM, and audit logs |

### 13.1. Layered 403 troubleshooting flow

~~~mermaid
flowchart TD
    Start["Not receiving CloudEvent"] --> Source{"Source event matches filter?"}
    Source -->|"No"| S["Check bucket/topic, event type, region"]
    Source -->|"Yes"| Agent{"Service agents and Event Receiver valid?"}
    Agent -->|"No"| A["GCS Publisher + Eventarc SA + trigger Receiver"]
    Agent -->|"Yes"| Invoke{"Cloud Run logs show 401/403?"}
    Invoke -->|"Yes"| I["Check exact trigger SA + roles/run.invoker"]
    Invoke -->|"No"| Code{"Handler logs show 5xx/timeout?"}
    Code -->|"Yes"| R["Check runtime SA, code, secrets, dependencies"]
    Code -->|"No"| O["Check delivery logs, latency, idempotency"]
~~~

**Do not solve every error by granting Owner/Editor or making the function public.** Doing so hides design flaws, creates security vulnerabilities, and makes the next incident harder to diagnose.

### 13.2. Useful read-only status commands

~~~bash
gcloud eventarc triggers describe invoice-finalized \
  --project=PROJECT_ID --location=asia-southeast1

gcloud run services describe invoice-event-handler \
  --project=PROJECT_ID --region=asia-southeast1

gcloud run services get-iam-policy invoice-event-handler \
  --project=PROJECT_ID --region=asia-southeast1

gcloud projects get-iam-policy PROJECT_ID \
  --format=yaml

gcloud run services logs read invoice-event-handler \
  --project=PROJECT_ID --region=asia-southeast1 --limit=100
~~~

When querying Cloud Audit Logs or Pub/Sub metrics, ensure you hold appropriate viewer permissions; **never write bearer tokens, service account JSON, PII payloads, or signed URLs to logs**.

## 14. Securing event-driven applications beyond IAM

### 14.1. CloudEvent content is still untrusted data

Cloud Run verifies **sender identity** when private, yet event data still requires validation:

- Validate `event.type`, `source`, bucket allowlists, and object generation.
- Limit input size and never log raw payloads containing sensitive data.
- Never use object names for arbitrary filesystem access.
- Never perform side-effecting actions without determining an **idempotency key**.
- For public webhooks or external event sources, verify signatures and provider-specific authentication policies.
- When writing to a database, prefer transactions/idempotent upserts rather than trusting "delivered once."

### 14.2. Retries and dead-letter handling

Event delivery can repeat or fail due to function timeouts, 429, 5xx, network issues, or IAM. Inspect the trigger/transport **retry policy** and configure a **dead-letter topic** when appropriate; do not assume every trigger always retries forever or only once.

A well-designed handler:

1. Receives the event, validates schema and source.
2. Computes the deduplication key.
3. Records "in progress/processed" in durable transactional storage.
4. Executes idempotent business logic.
5. Returns success only when work has been accepted/processed per policy.
6. For transient errors, uses retries/backoff and a DLQ mechanism to avoid losing events or looping indefinitely.

### 14.3. Cross-project and org policies

If the source bucket, Eventarc trigger, service account, and function live in different projects, check:

- **Eventarc supported cross-project routing** and per-event-type project configuration.
- Organization Policies governing **cross-project service account usage**.
- Deployer's `iam.serviceAccounts.actAs` permission on SAs in another project.
- Invoker IAM on the **target project/service**.
- Event source/agent permissions in the **source project**.
- VPC Service Controls and data residency when enforced by the environment.

Do not take a "one project, one region" example and assume you can swap every `PROJECT_ID` to different values without adding cross-project IAM.

## 15. Operations, observability, and cost

| Signal | What to monitor |
|---|---|
| Trigger health/conditions | Whether trigger creates cleanly, routes to the right destination, uses right service account |
| Event delivery success/failure | Events received, retries, 4xx/5xx, delay |
| Function logs and latency | Processing duration, Java errors, memory/CPU, timeouts |
| IAM changes | Additions/removals of Invoker, Event Receiver, service agent roles |
| Quotas and Pub/Sub transport | Ensuring event path is not throttled by quotas or permissions |
| Idempotency/DLQ | Duplicate events, backlog, dead-letter messages, and replay procedures |
| Billing | Eventarc, Pub/Sub transport, Cloud Run invocations/CPU/memory, builds, logs, Cloud Storage operations |

Costs extend beyond Cloud Run runtime; Pub/Sub transport, logging, and storage requests can incur usage/retention charges. Use **Billing Reports** and the **Google Cloud Pricing Calculator** rather than assuming all events cost the same or stay within free tiers.

**Rollback:** keep previous function releases, check trigger destination/paths and event filters; roll back code via revisions/CI when needed. Before deleting a trigger or SA, check if other consumers depend on it. Deleting an SA or revoking Invoker prematurely can break another event pipeline.

## 16. Case study: invoices processed by a Java function

**Context:** a retail system has a Java Orders API writing PDF invoices to Cloud Storage. When an object finalizes, Eventarc invokes a function to process metadata; later, the function may save state to Firestore or publish a downstream Pub/Sub event.

**Least-privilege permission design:**

| Component | Principal | Permissions |
|---|---|---|
| Function/trigger publisher | CI deployer SA | Deploy/Eventarc create + `actAs` on the exact service accounts |
| Eventarc trigger | `evt-invoice@...` | Event Receiver and Run Invoker on `invoice-event-handler` |
| Cloud Storage event source | Cloud Storage service agent | Pub/Sub Publisher on the project per guidance |
| Java function | `fn-invoice@...` | No Storage Viewer needed if reading metadata only; add bucket permission if downloading |
| Cloud Run target | Private function | Only the trigger SA and authorized callers hold Invoker |
| Service agents | Eventarc/Cloud Run/Cloud Functions/PubSub where applicable | Google-managed roles on the right principals and APIs |

Release workflow:

1. Create user-managed SAs with clear scopes.
2. Deploy the private function with the runtime SA.
3. Grant Invoker properly to the trigger SA.
4. Create the trigger with exact filters.
5. Upload a non-sensitive test file; observe event ID/type and logs.
6. Negative test: remove Invoker in **sandbox** and verify the authentication failure; restore it and verify recovery.
7. Add deduplication, retries/DLQ, and alerts before production.
8. Document role bindings, key decisions, and costs in the runbook.

**Do not equate HTTP success with transaction success.** If the function only logs metadata while the real requirement is persisting invoices to a database, test side effects, idempotency, and DB permissions.

## 17. Practice exercises and self-assessment questions

### Exercise 1 — Distinguishing four identities

An engineer grants `roles/storage.objectViewer` to the trigger SA and `roles/run.invoker` to the runtime SA. The trigger shows active status yet Cloud Run reports unauthorized.

**Question:** What are the two permission mistakes? Which role needs to move to which principal?

**Hint:** The trigger SA needs Run Invoker on the function; the runtime SA only needs Storage Viewer when code must download objects.

### Exercise 2 — Cloud Storage direct event

Eventarc receives `google.cloud.storage.object.v1.finalized`, yet no Cloud Run logs appear even though target Invoker is set properly.

**Question:** Which service agent and role should you inspect? Should you also check event filters/project/location?

**Hint:** The Cloud Storage service agent needs Pub/Sub Publisher; check type/bucket filters and the Eventarc agent.

### Exercise 3 — Pub/Sub direct event

A Pub/Sub direct trigger already has `roles/run.invoker` on a private function, yet lacks Event Receiver.

**Question:** Is this always an error? Why or why not?

**Hint:** For direct Pub/Sub events, Event Receiver is not required; inspect actual delivery and other permissions.

### Exercise 4 — Runtime API 403

Cloud Run receives the CloudEvent successfully, yet Java code calling `Storage.get(bucket, object)` returns 403.

**Question:** Which principal and IAM scope must you inspect? Why won't adding Event Receiver fix it?

**Hint:** The runtime SA needs Storage Object Viewer on the bucket/required permissions; the error occurs **after invocation**.

### Exercise 5 — Manual HTTP caller

A developer opens the function URL in a browser and sees 403, while Eventarc works normally.

**Question:** Does the browser automatically send a valid ID token? Should you enable unauthenticated access?

**Hint:** Caller identity, Run Invoker, and an ID token with the matching audience are required; do not make the function public just to test.

### Exercise 6 — CI cannot deploy

A Cloud Build deployer uses dedicated runtime and trigger SAs, yet fails with an `iam.serviceAccounts.actAs` error.

**Question:** To whom should `roles/iam.serviceAccountUser` be granted, and on which resources?

**Hint:** Grant it to the deployer/CI principal on the **exact SAs** being attached; do not grant project-wide Owner.

### Exercise 7 — Event arrives twice

Two events with the same `source` and `id` cause the function to write two invoice records in Firestore.

**Question:** How do you design the idempotency/deduplication mechanism? When do you return success?

**Hint:** Persist a durable processing key and use conditional writes/transactions; ACK when the business state satisfies the contract.

### Exercise 8 — Cross-project trigger

The bucket is in project A, the function in project B, and the trigger SA in project C. An engineer grants permissions only in B and still reports 403.

**Question:** Which layers must be verified before allowing production use?

**Hint:** Product cross-project support, Eventarc trigger/source projects, service account policy/`actAs`, target Invoker, and service agents.

### Exercise 9 — Ordered diagnosis

A pipeline produces no events after upload. Order the verification chain:

- Source bucket and type filter;
- Eventarc trigger identity/conditions;
- Cloud Storage Publisher and Eventarc agent;
- Target Cloud Run Invoker;
- Runtime Java logs and object read permissions;
- Retries/DLQ and idempotency.

**Requirement:** state the signal that distinguishes a **pre-invocation** failure from an **in-function** failure.

## 18. Pre-production checklist

- [ ] Identified the exact event type, source project/location, and destination service.
- [ ] Separated **deployer**, **trigger SA**, **runtime SA**, and **Google service agents**.
- [ ] Trigger uses a user-managed SA rather than relying on default compute SA Editor permissions.
- [ ] `roles/eventarc.eventReceiver` granted where required by the provider; remembered the **Pub/Sub direct events** exception.
- [ ] `roles/run.invoker` placed on the exact **target Cloud Run service** for the exact trigger SA.
- [ ] Function is private; ingress, IAM Invoker, and app-level authorization are reviewed separately.
- [ ] Cloud Storage direct events have Publisher permission on the right **Cloud Storage service agent**.
- [ ] Eventarc service agent retains its managed role; legacy Pub/Sub token creator granted only if needed.
- [ ] Runtime SA has least-privilege Google API permissions; no JSON private keys stored in source/images.
- [ ] Deployer has deploy/trigger-create roles and `iam.serviceAccounts.actAs` on relevant SAs.
- [ ] CloudEvent inputs validate source/type/ID, never treating payloads as credentials.
- [ ] Handler is idempotent; retries, timeouts, dead-letter handling, and replay are governed.
- [ ] Logs/metrics/alerts cover 401/403/5xx, event delay, and IAM drift.
- [ ] Cross-project setup, VPC Service Controls, org policies, and data residency verified if applicable.
- [ ] Safely tested a 403 negative case in sandbox and verified fixing it via IAM on the right principal.
- [ ] Estimated costs for Cloud Run, Pub/Sub transport, Eventarc, logs, builds, and source operations.
- [ ] Runbook, owner, rollback, and service account/trigger revocation controls are in place.

## 19. Official documentation

Roles, service agents, deployment methods, and event providers may change over time. Verify against current docs before operating on real projects:

- [Eventarc Standard — Roles and permissions for Cloud Run functions targets](https://docs.cloud.google.com/eventarc/standard/docs/functions/roles-permissions)
- [Eventarc Standard — Roles and permissions for Cloud Run targets](https://docs.cloud.google.com/eventarc/docs/roles-permissions)
- [Cloud Run — Deploy a function from source](https://docs.cloud.google.com/run/docs/deploy-functions)
- [Cloud Run — Write functions](https://docs.cloud.google.com/run/docs/write-functions)
- [Cloud Run — Java runtime](https://docs.cloud.google.com/run/docs/runtimes/java)
- [Cloud Run — Introduction to service identity](https://docs.cloud.google.com/run/docs/securing/service-identity)
- [Cloud Run — Configure service identity](https://docs.cloud.google.com/run/docs/configuring/services/service-identity)
- [Eventarc — Receive Cloud Storage direct events using gcloud](https://docs.cloud.google.com/eventarc/standard/docs/run/create-trigger-storage-gcloud)
- [Cloud Run — Trigger functions from Cloud Storage using Eventarc](https://docs.cloud.google.com/run/docs/tutorials/trigger-functions-storage)
- [Cloud Run — Troubleshooting](https://docs.cloud.google.com/run/docs/troubleshooting)
- [Cloud Functions v2 — Function identity](https://docs.cloud.google.com/functions/docs/securing/function-identity)
- [Eventarc — IAM roles reference](https://docs.cloud.google.com/iam/docs/roles-permissions/eventarc)

**Key takeaway:** For **Eventarc → private Cloud Run function**, the **trigger service account** must have the **appropriate event-receiving role** and **`roles/run.invoker` on the exact function**; the **runtime service account** receives only the permissions Java code needs at execution time. **Cloud Storage/Pub/Sub/Eventarc service agents** have separate duties and must not be confused with those two accounts. Proper security configuration must be verified through **real events, logging, 403 negative testing, idempotency, and cost checks**, not merely an "Active" trigger status.
