# IAM, encryption, and message storage policies in Google Cloud Pub/Sub

## Learning objectives

After this lesson, you will be able to:

1. Distinguish the permissions of **publishers**, **subscribers**, Pub/Sub administrators, and the **Pub/Sub service agent**; grant IAM on the right topic, subscription, or Cloud KMS key.
2. Explain default encryption, **TLS**, **customer-managed encryption keys (CMEK)**, and how Pub/Sub uses **envelope encryption**.
3. Configure a **message storage policy** with an allowed regions list, and distinguish it from **enforceInTransit** and **regional endpoints**.
4. Understand policy/KMS impacts during region changes, key rotation, Cloud Run/GKE deployments, cross-project permissions, and resolving **PERMISSION_DENIED** or **FAILED_PRECONDITION** errors.
5. Practice **gcloud**, a **Java Publisher** example using Application Default Credentials (ADC), regional data monitoring, rollback design, and exercises.

## 1. Problem: an order system must control who, which key, and where data lives

A Java/Spring Boot system running on **Cloud Run** publishes **order.created** events to Pub/Sub; a **GKE worker** processes orders and persists data to Cloud SQL and Cloud Storage. Security imposes three requirements:

- Only the **orders-api** service account may **publish** to the topic; only the dedicated worker may **consume** the subscription.
- Messages are encrypted; for sensitive data, the business needs key lifecycle control via **Cloud KMS**.
- Message contents must be stored in **asia-southeast1**; in strictly regulated environments, publish/pull requests themselves must also be processed inside allowed regions.

~~~mermaid
flowchart LR
  API["Cloud Run orders-api<br/>Publisher identity"] -->|"Publish"| TOPIC["Pub/Sub topic<br/>orders-events"]
  TOPIC -->|"Fan-out"| SUB["Subscription<br/>orders-worker-sub"]
  SUB -->|"Pull + Ack"| WORK["GKE Java worker<br/>Subscriber identity"]
  KMS["Cloud KMS<br/>CMEK key"] -. "Service agent encrypt/decrypt" .-> TOPIC
  POLICY["Topic message storage policy<br/>allowedPersistenceRegions"] -. "Residency" .-> TOPIC
  IAM["IAM at topic/subscription"] -. "Who can publish/consume" .-> TOPIC
  IAM -. "Who can consume" .-> SUB
~~~

In the **CLOUD_PROVIDERS_GCP** module, this lesson connects project/IAM/VPC with Cloud Run, GKE, Cloud Storage, databases, release security, and reliability/cost monitoring. The three mechanisms—**IAM**, **encryption**, and **message storage policy**—complement rather than replace one another.

| Mechanism | Question solved | Does NOT solve |
|---|---|---|
| **IAM** | Which principal can publish, consume, or configure topics/subscriptions? | Where messages are stored, or content security after app reads |
| **Encryption / CMEK** | Which key protects messages at rest? Who controls the KMS key? | Publish/subscribe access, restricting processing location |
| **Message storage policy** | In which Google Cloud regions are message contents stored/processed? | Publisher IAM, resource labels/names, retention duration |
| **enforceInTransit** | Reject Publish/Pull when handled in a disallowed region? | User auth, replay protection, application-level payload encryption |

## 2. Reviewing the Pub/Sub model and permission attachment points

A **Topic** is where producers publish messages. A **Subscription** consumes messages from a topic; multiple subscriptions on the same topic receive separate logical copies with separate backlogs and acknowledgments. **Ack** confirms successful processing so Pub/Sub stops delivering that message under the applicable delivery semantics.

~~~text
projects/shop-dev-001/topics/orders-events
    |
    +-- projects/shop-dev-001/subscriptions/orders-worker-sub
    +-- projects/shop-dev-001/subscriptions/orders-audit-sub
~~~

Names are illustrative and not pre-created. **Message storage policies and CMEK** are configured on the **topic**. **Publisher IAM** is typically granted on the **topic**; **Subscriber IAM** is typically granted on the **subscription**. **Subscription retention** and **topic message retention** are distinct from **message storage regions**.

### 2.1. Identities to keep separate

| Principal | Proper role | Recommended scope |
|---|---|---|
| **orders-publisher@...** | Send events from Cloud Run | **roles/pubsub.publisher** on topic `orders-events` |
| **orders-subscriber@...** | Pull/Ack from GKE or Cloud Run worker | **roles/pubsub.subscriber** on subscription `orders-worker-sub` |
| **Platform operator** | Create/modify topics, subscriptions, and policies | Pub/Sub Editor/Admin at approved scope |
| **Pub/Sub service agent** | Allows Pub/Sub to use Cloud KMS for encrypt/decrypt | **roles/cloudkms.cryptoKeyEncrypterDecrypter** on the CryptoKey |
| **KMS administrator** | Create, rotate, disable, manage key IAM | Appropriate Cloud KMS role; separated from runtime |
| **Push subscription service agent / delivery identity** | Mint tokens for authenticated push | Token creator and endpoint invoker permissions as required |

A GKE **KSA**, **Cloud Run runtime service account**, **Pub/Sub service agent**, and **node service account** are distinct identities. Never grant all of these roles to a single principal just to silence a 403 error.

## 3. Pub/Sub IAM: right role, right resource

### 3.1. Roles to remember

| Predefined role | Primary task | Notable permissions |
|---|---|---|
| **roles/pubsub.publisher** | Publish to a topic | **pubsub.topics.publish** |
| **roles/pubsub.subscriber** | Consume/Ack subscriptions; also grants attach subscription per role definition | **pubsub.subscriptions.consume**, **pubsub.topics.attachSubscription** |
| **roles/pubsub.viewer** | Inspect topic, subscription, and schema configurations | Get/List within scope |
| **roles/pubsub.editor** | Manage multiple Pub/Sub resources | Broader than Viewer/Publisher/Subscriber |
| **roles/pubsub.admin** | Full Pub/Sub administrative control within IAM scope | Can alter/delete resources; do not grant to app runtimes |

**roles/pubsub.subscriber** includes more than pulling a single subscription because the role includes **attachSubscription** on topics per its permission set. In practice, bind this role directly on the **subscription**; if tighter restriction is needed, consider a custom role with the minimum Google-supported permissions.

### 3.2. Resource-level IAM vs. project-level IAM

For Pub/Sub, IAM bindings at the **topic** or **subscription** level are usually safer than **project-level** roles because they constrain an application's blast radius.

~~~bash
# This is an IAM change; run only in an authorized lab project.
gcloud pubsub topics add-iam-policy-binding orders-events \
  --project=shop-dev-001 \
  --member="serviceAccount:orders-publisher@shop-dev-001.iam.gserviceaccount.com" \
  --role="roles/pubsub.publisher"

gcloud pubsub subscriptions add-iam-policy-binding orders-worker-sub \
  --project=shop-dev-001 \
  --member="serviceAccount:orders-subscriber@shop-dev-001.iam.gserviceaccount.com" \
  --role="roles/pubsub.subscriber"
~~~

Inspecting IAM policies does not expose message payloads:

~~~bash
gcloud pubsub topics get-iam-policy orders-events \
  --project=shop-dev-001

gcloud pubsub subscriptions get-iam-policy orders-worker-sub \
  --project=shop-dev-001
~~~

**Evaluate effective permissions**, not just the binding on one resource: a principal may inherit access via groups, project, folder, organization, or custom roles. If a subscriber can still read after removing a subscription binding, check inherited permissions at higher levels.

### 3.3. Creating subscriptions and attachSubscription errors

To **create a subscription attached to a topic**, the creator may need:

- **pubsub.subscriptions.create** in the project owning the subscription.
- **pubsub.topics.attachSubscription** on the source topic.

If the topic and subscription live in **two different projects**, check IAM in **both places**. Having the subscriber role to pull a subscription is **not necessarily** sufficient to create a new subscription.

### 3.4. Runtime identity: ADC instead of JSON keys

- **Cloud Run:** configure a runtime service account with Publisher role on the topic. The Google Cloud Pub/Sub Java client locates credentials via **Application Default Credentials**.
- **GKE:** use **Workload Identity Federation for GKE** binding IAM to a Kubernetes ServiceAccount, or impersonation if needed; avoid service account JSON keys in Secrets/ConfigMaps.
- **CI/CD outside GCP:** prefer **Workload Identity Federation**; never commit long-lived keys into repositories.
- **Compute Engine:** requires a service account and appropriate scopes/IAM; verify the actual principal used when calling Pub/Sub.

**Do not confuse an ID token for an HTTP push endpoint with the OAuth access token/ADC used by publishers or pull subscribers to call the Pub/Sub API.**

### 3.5. Authenticated push: two IAM layers

If a subscription **pushes** to a private Cloud Run endpoint:

1. Pub/Sub configures a **push authentication service account**.
2. The user creating/updating the subscription needs **iam.serviceAccounts.actAs** on that service account.
3. The **Pub/Sub service agent** needs permission to mint OIDC tokens (**roles/iam.serviceAccountTokenCreator**) for the push identity per documentation.
4. The push identity needs **roles/run.invoker** on the target Cloud Run service.
5. Cloud Run verifies the configured token **audience/issuer**; never treat an unauthenticated HTTP 200 endpoint as secure design.

The **Pub/Sub publish/consume** permissions are separate from **invoking a Cloud Run HTTP endpoint**. In the pull lab below, push authentication is not needed yet.

## 4. Encryption: Google default encryption, TLS, and CMEK

### 4.1. Encrypted at rest by default

Pub/Sub encrypts customer content **at rest** by default using Google-managed keys. API traffic runs over **TLS**-protected channels. Businesses do not need to enable CMEK merely to get baseline encryption.

**CMEK** lets organizations control the **key encryption key (KEK)** in Cloud KMS—configuring IAM, rotation, key location, auditing, or HSM/Autokey as needed.

| Approach | Who manages the KEK? | Value | Trade-offs |
|---|---|---|---|
| **Google default encryption** | Google Cloud | Low operational overhead, no key management | Less control over key lifecycle |
| **Pub/Sub + Cloud KMS CMEK** | Key owner in Cloud KMS | IAM/key rotation, auditability, and revocation | Extra KMS permissions, quota/cost, outage risk if key becomes inaccessible |
| **Application-level encryption before publish** | Application/enterprise | Protects payload along custom trust boundary | Harder to search/transform, requires key management and decryption in subscribers; **distinct from CMEK** |

### 4.2. Envelope encryption does not mean KMS encrypts every payload

~~~mermaid
flowchart LR
  MSG["Message data"] --> DEK["Pub/Sub uses DEK<br/>to encrypt data"]
  KMS["Cloud KMS CMEK (KEK)"] --> WRAP["Wrap/unwrap DEK"]
  DEK --> STORE["Store encrypted message"]
  WRAP --> STORE
  STORE --> READ["Pub/Sub decrypts before delivery"]
  READ --> SUB["IAM-authorized subscriber"]
~~~

Pub/Sub uses **data encryption keys (DEKs)** for messages, while **Cloud KMS CMEK** wraps and unwraps those DEKs. Per documentation, Pub/Sub generates a new DEK for a topic roughly **every 6 hours**. Therefore, KMS operation counts **do not equal message counts**; individual messages do not trigger separate Cloud KMS encrypt calls.

**Important limitation:** message **attributes** are not encrypted at Pub/Sub's **application layer** like the payload, even though they remain encrypted at underlying infrastructure/hardware layers. Never place API keys, card numbers, JWTs, or sensitive PII inside message attributes, topic IDs, subscription IDs, labels, or logs.

### 4.3. CMEK does not encrypt data after subscribers read it

When a subscriber pulls or receives a push, Pub/Sub decrypts the content for delivery to the authorized client. Afterward, the application must still protect:

- Java logs/exception traces, dead-letter processing, and message retries.
- Connections to Cloud SQL/other APIs and objects written to Cloud Storage.
- Data in heap, disk, snapshots, export files, or backups.
- Which principals have IAM permission to consume the content.

**CMEK does not replace IAM, TLS, schema/payload controls, data masking, or application security.**

## 5. Hands-on A — Granting scoped Pub/Sub IAM

### 5.1. Prerequisites and environment

All illustrative names belong to project **shop-dev-001**, not pre-existing resources. Assume the **Pub/Sub API** is enabled, billing/quotas exist, and admin rights follow lab policy. Never test IAM changes or revocations in production.

~~~bash
gcloud auth list
gcloud config get-value project
gcloud services list --enabled --project=shop-dev-001

# If the lab project has not enabled the API yet, requires admin rights:
gcloud services enable pubsub.googleapis.com \
  --project=shop-dev-001

# Create a topic and pull subscription strictly for this lab.
gcloud pubsub topics create orders-events \
  --project=shop-dev-001

gcloud pubsub subscriptions create orders-worker-sub \
  --project=shop-dev-001 \
  --topic=orders-events
~~~

### 5.2. Create two identities without sharing roles

~~~bash
gcloud iam service-accounts create orders-publisher \
  --project=shop-dev-001 \
  --display-name="Publisher for orders-events"

gcloud iam service-accounts create orders-subscriber \
  --project=shop-dev-001 \
  --display-name="Subscriber for orders-worker-sub"
~~~

Next, grant **Publisher** on the topic and **Subscriber** on the subscription using the commands from Section 3.2. Review IAM policies; operators need IAM read rights, while runtime identities need their respective roles.

### 5.3. Test via CLI with appropriate principals

~~~bash
# Caller must have pubsub.topics.publish on the topic.
gcloud pubsub topics publish orders-events \
  --project=shop-dev-001 \
  --message='{"eventId":"lab-001","type":"order.created"}' \
  --attribute=event_type=order.created

# Caller must have pubsub.subscriptions.consume on the subscription.
gcloud pubsub subscriptions pull orders-worker-sub \
  --project=shop-dev-001 \
  --limit=5 \
  --auto-ack
~~~

These commands use the **active gcloud principal**. They **do not automatically use** the two newly created service accounts. To test permissions as an individual identity, use **--impersonate-service-account** if allowed, or run directly from the Cloud Run/GKE runtime identity.

**Use `--auto-ack` only for testing**: in real apps, ack **only after processing and persisting results durably**; nack/retry transient failures. Never run pull commands on a production subscription if acking could discard unprocessed messages.

### 5.4. Negative tests

In the test environment, verify:

1. Publisher **cannot** pull the subscription without the Subscriber role.
2. Subscriber **cannot** publish to the topic without the Publisher role.
3. A third unprivileged service account **cannot** do either.
4. Add the required role on the specific resource and retest; **never grant Editor/Owner** to bypass errors.

If a negative test still succeeds, inspect inherited permissions or which gcloud/ADC identity is actually active.

## 6. Hands-on B — Creating a Cloud KMS CMEK for a topic

### 6.1. Match key location to architecture

Because Pub/Sub is a global service, Google Cloud **recommends CMEK in the `global` location** to avoid unnecessary cross-region dependencies. Consider a **regional key** only when:

- Message storage policy allows **one region** and **enforceInTransit** is enabled.
- **All publishers and subscribers** use the same **regional endpoint** in that region.

Do not assume a single-region topic always benefits from a regional KMS key; evaluate permissions, availability, latency, and residency mandates first. The example below chooses a **global KMS key** for the lab environment.

### 6.2. Create a key ring and symmetric CryptoKey

~~~bash
gcloud services enable cloudkms.googleapis.com \
  --project=shop-dev-001

gcloud kms keyrings create pubsub-ring \
  --project=shop-dev-001 \
  --location=global

gcloud kms keys create orders-messages-key \
  --project=shop-dev-001 \
  --location=global \
  --keyring=pubsub-ring \
  --purpose=encryption \
  --rotation-period=90d \
  --next-rotation-time=2027-03-01T00:00:00Z
~~~

**The rotation date above is illustrative and must fit when you run the lab**; if past or against org policy, substitute a valid schedule. Do not create a key with an already-existing name. **Key rings and CryptoKeys cannot be deleted directly** the way topics can; plan names, locations, and IAM before creating KMS resources.

### 6.3. Grant permission to the Pub/Sub service agent, not the publisher

The project's Pub/Sub service agent follows this format:

~~~text
service-PROJECT_NUMBER@gcp-sa-pubsub.iam.gserviceaccount.com
~~~

Fetch the **actual project number**:

~~~bash
gcloud projects describe shop-dev-001 \
  --format="value(projectNumber)"
~~~

Assuming the project number is **123456789012**:

~~~bash
gcloud kms keys add-iam-policy-binding orders-messages-key \
  --project=shop-dev-001 \
  --location=global \
  --keyring=pubsub-ring \
  --member="serviceAccount:service-123456789012@gcp-sa-pubsub.iam.gserviceaccount.com" \
  --role="roles/cloudkms.cryptoKeyEncrypterDecrypter"
~~~

Substitute the real number before running. **Do not grant KMS Encrypter/Decrypter to publishers and subscribers** merely because they use a CMEK topic. Publishers/Subscribers need only Pub/Sub IAM; **the Pub/Sub service** performs encryption/decryption with the key.

If the KMS key resides in project **security-kms-001** while the topic lives in **shop-dev-001**, grant KMS access on the key in **security-kms-001** to the **Pub/Sub service agent of the topic's project**, not to an unrelated service agent in the KMS project.

### 6.4. Create a CMEK topic

Create a separate lab topic to avoid affecting topics with existing data:

~~~bash
gcloud pubsub topics create orders-secure \
  --project=shop-dev-001 \
  --topic-encryption-key=projects/shop-dev-001/locations/global/keyRings/pubsub-ring/cryptoKeys/orders-messages-key

gcloud pubsub topics describe orders-secure \
  --project=shop-dev-001
~~~

Verify **kmsKeyName** points to the right CryptoKey. If the Pub/Sub service agent has not been provisioned yet, trigger/create the service identity per official docs and bind IAM before testing the topic. Never remove or alter key IAM while a production subscription has a backlog.

### 6.5. Changing keys does not re-encrypt past messages

Pub/Sub allows updating the key associated with a topic, however:

- **Changing the KMS key on a topic** affects only messages published after the new setting takes effect. Pub/Sub caches keys and can take around **30 minutes** to pick up a new key config.
- **Rotating a CryptoKey version in Cloud KMS** does not make the topic switch immediately; per Pub/Sub docs it can take **up to 12 hours** for the new version to protect subsequent DEKs.
- **Older messages still depend on the old key/key version** throughout retention, which can be up to **31 days**. Never disable or destroy old key versions right away simply because the topic switched to a new key.

**Rotation runbook:** check usage/retention → create/rotate new key → monitor publish/delivery and Cloud KMS logs → ensure old backlogs have drained or retention expired → only then consider disabling under change control; assess impact on subscription replay/snapshots.

### 6.6. KMS failures are availability risks

If a key is disabled, key IAM is revoked, or KMS is unreachable, **publish/pull can return FAILED_PRECONDITION** and push delivery can halt. Never "fix" this by disabling CMEK without investigation: older data may still be encrypted under the old key.

In practice, **do not test disabling keys** on shared systems. Instead, model it in diagrams/runbooks and check KMS IAM policies, key versions, Cloud Audit Logs, and backlog metrics.

## 7. Message storage policy: where are message contents stored?

A Pub/Sub topic has a **messageStoragePolicy**, containing:

~~~json
{
  "messageStoragePolicy": {
    "allowedPersistenceRegions": ["asia-southeast1"],
    "enforceInTransit": false
  }
}
~~~

**allowedPersistenceRegions** is a **list of region IDs** (such as **asia-southeast1**, **asia-east1**), not zones or multi-region names like **asia**. At least one region must be listed, complying with any active **Resource Location Restriction organization policy**.

When a publisher sits elsewhere and **enforceInTransit=false**, Pub/Sub may accept the request and route data into an allowed region for persistence. Thus **publishers outside the list are not automatically rejected**, though latency or transit through other network regions can occur prior to storage.

### 7.1. Scope limits of the storage policy

The policy governs **message contents** stored/processed; **it does not enforce residency on topic names, labels, or IAM settings**. It does not create a dedicated storage bucket, turn topics into strictly single-region services, or automatically govern backend residency once subscribers write to Cloud SQL or Cloud Storage.

### 7.2. When no policy is declared

- A new topic inherits a message storage policy from the organization's **Resource Location Restriction** if one exists.
- Without a location-restricting org policy, **all regions** are allowed.
- Default **enforceInTransit** can also be governed by a corresponding **organization policy**; do not assume it defaults to false in every organization.
- Changing an organization policy **does not automatically update all existing topics**; proactively sync or inspect each topic.

### 7.3. Updating the policy does not migrate old messages

Suppose a topic previously stored messages in **asia-east1**, and now allows only **asia-southeast1**. Updating **allowedPersistenceRegions**:

1. Applies to **new messages** published after the update.
2. Does **not** move or re-encrypt messages already published under the old policy.
3. Does not guarantee older data disappears from the old region immediately; inventory backlog, retention, and snapshots.

For strict compliance residency mandates, **design topics and policies right from the start**, and evaluate historical data before declaring regional migration complete.

## 8. enforceInTransit: adding request-processing boundaries

Set **enforceInTransit=true** to require Pub/Sub not only to store contents in allowed regions, but also to process **Publish, Pull, StreamingPull, and push delivery** strictly inside those regions.

| Scenario | false / disabled | true |
|---|---|---|
| Publisher in an allowed region | Succeeds if IAM/quotas permit | Succeeds |
| Publish request handled outside the allowed list | Accepted and routed to an allowed region for storage | **FAILED_PRECONDITION** |
| Subscriber Pull/StreamingPull from a disallowed region | Accessible if IAM and system permit | **FAILED_PRECONDITION** |
| Push subscription | Routed normally | Processes delivery only in allowed regions; overly tight restrictions can **halt delivery** |
| Client outside Google Cloud using global endpoint | Enters near client, then stores in allowed region | Easily lands in a disallowed region and fails; use a **regional endpoint** |

**FAILED_PRECONDITION differs from PERMISSION_DENIED:** the former typically points to policy/region/KMS state, whereas the latter points to IAM or another access control. Diagnose via response codes and logs.

### 8.1. Three types of Pub/Sub endpoints

| Endpoint | Example | Guarantee |
|---|---|---|
| **Global** | `pubsub.googleapis.com` | Routes near where the client enters Google Cloud; **does not pin processing region** |
| **Regional** | `pubsub.asia-southeast1.rep.googleapis.com` | Requests are processed strictly in the specified region; **does not auto-reroute to another region** |
| **Locational** | Per specific location format in Pub/Sub docs | Generally enters the specified location, yet **lacks the strict guarantee of a regional endpoint** |

With **enforceInTransit=true** and data restricted to **asia-southeast1**, **regional endpoints** in that region are **recommended** for both publishers and pull subscribers. If a Java service runs in the US or outside GCP while still hitting the global endpoint, requests may enter a disallowed region and fail.

**Remember:** regional endpoints also trade off availability: during a regional outage, requests **do not automatically fail over to another region**. Multi-region apps need an explicit allowed-regions list and an approved endpoint-switching strategy, not just a single checkbox.

## 9. Hands-on C — Creating a topic with storage policy and in-transit enforcement

### 9.1. Single region, no in-transit enforcement

~~~bash
gcloud pubsub topics create orders-resident \
  --project=shop-dev-001 \
  --message-storage-policy-allowed-regions=asia-southeast1

gcloud pubsub topics describe orders-resident \
  --project=shop-dev-001 \
  --format="yaml(name,messageStoragePolicy)"
~~~

**Do not conclude all requests are processed in asia-southeast1** from this policy alone: it only **restricts where message contents may be stored**. To enforce Pub/Sub processing location, add `enforceInTransit` and use matching endpoints.

### 9.2. Enable enforcement in the lab

~~~bash
gcloud pubsub topics update orders-resident \
  --project=shop-dev-001 \
  --message-storage-policy-allowed-regions=asia-southeast1 \
  --message-storage-policy-enforce-in-transit

gcloud pubsub topics describe orders-resident \
  --project=shop-dev-001 \
  --format="yaml(name,messageStoragePolicy)"
~~~

**Warning:** **MessageStoragePolicy** flags on `update` must be passed together. Omitting **--message-storage-policy-enforce-in-transit** when updating the regions list can revert the omitted property to default and **unintentionally disable enforcement**. Never assume `update` patches only one field unless CLI docs explicitly state so.

### 9.3. Multiple allowed regions and availability

Example allowing **asia-southeast1** and **asia-east1**:

~~~bash
gcloud pubsub topics update orders-resident \
  --project=shop-dev-001 \
  --message-storage-policy-allowed-regions=asia-southeast1,asia-east1 \
  --message-storage-policy-enforce-in-transit
~~~

When a publish request hits an allowed region, Pub/Sub can store the message in the allowed region nearest the publisher. **Adding a region to the policy does not move existing messages**, nor does it create synchronous multi-region replication. If clients only run in one region, adding a second region does not make the pipeline HA unless the application can switch endpoints and workloads too.

### 9.4. Sync with Resource Location Restriction

~~~bash
# Use when the org policy has passed security/platform review.
gcloud pubsub topics update orders-resident \
  --project=shop-dev-001 \
  --recompute-message-storage-policy
~~~

**--recompute-message-storage-policy** applies the active organization policy to the topic and **cannot** be combined with explicit region flags in the same command. Always **read back** both `allowedPersistenceRegions` and `enforceInTransit`, since org policies may differ from the topic's prior configuration. Never alter shared environment organization policies just to run a lab.

### 9.5. REST representation for IaC review

~~~json
{
  "name": "projects/shop-dev-001/topics/orders-resident",
  "messageStoragePolicy": {
    "allowedPersistenceRegions": [
      "asia-southeast1",
      "asia-east1"
    ],
    "enforceInTransit": true
  }
}
~~~

This is **part of the Topic resource body**; when calling **topics.patch**, pass the exact **updateMask** per API reference to update only `messageStoragePolicy` without overwriting or clearing other fields. With Terraform/IaC, plan changes carefully and avoid drift between gcloud console edits and the IaC repository.

## 10. Hands-on D — Java Publisher with ADC and regional endpoint

Example of a Java 21 app on Cloud Run publishing events **without storing JSON keys**. Maven uses **com.google.cloud:google-cloud-pubsub**, managed via an organization-vetted **Google Cloud libraries BOM**. Standalone class below:

~~~java
import com.google.api.core.ApiFuture;
import com.google.cloud.pubsub.v1.Publisher;
import com.google.protobuf.ByteString;
import com.google.pubsub.v1.PubsubMessage;
import com.google.pubsub.v1.TopicName;
import java.util.concurrent.TimeUnit;

public final class OrderEventPublisher {
    private OrderEventPublisher() {}

    public static void main(String[] args) throws Exception {
        TopicName topic = TopicName.of("shop-dev-001", "orders-resident");

        // Endpoint pinned to an allowed Pub/Sub processing region.
        Publisher publisher = Publisher.newBuilder(topic)
            .setEndpoint("pubsub.asia-southeast1.rep.googleapis.com:443")
            .build();  // Uses ADC from Cloud Run/GKE/workstation.

        try {
            PubsubMessage event = PubsubMessage.newBuilder()
                .setData(ByteString.copyFromUtf8(
                    "{\"eventId\":\"lab-002\",\"type\":\"order.created\"}"))
                .putAttributes("event_type", "order.created")
                .build();

            ApiFuture<String> result = publisher.publish(event);
            String messageId = result.get(30, TimeUnit.SECONDS);
            System.out.println("Published message ID: " + messageId);
        } finally {
            publisher.shutdown();
            publisher.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

**Security significance:** the Pub/Sub Java client obtains credentials via **ADC**. The Cloud Run runtime identity needs **roles/pubsub.publisher** on the topic and requires no Cloud KMS permissions. **setEndpoint** routes RPCs to the Pub/Sub **regional endpoint**; for the subscriber to share the same guarantee, configure the matching endpoint on the **Subscriber/Pull client** as well, not just the publisher.

### 10.1. Mandatory changes before production

- Never instantiate a `Publisher` per **HTTP request**: reuse one client for efficient batching, retries, and connection pooling.
- Attach an **eventId/idempotency key**, handle **publish retries creating duplicates**, and make consumers idempotent.
- Never log plaintext messages containing sensitive data; never put customer IDs, emails, or API keys in attributes.
- Ack in the consumer **only after processing commits**. On consumer failures, follow retry/dead-letter policies; IAM and encryption do not guarantee end-to-end exactly-once.
- Design circuit breakers/backoff, metrics, and halt publishing if **FAILED_PRECONDITION** indicates a persistent misconfiguration rather than retrying infinitely.
- Use vetted code paths and Maven dependency versions. If network policy blocks regional endpoints, verify DNS, TLS, firewall rules, and Private Google Access before deploying.

### 10.2. What does the subscriber do?

A pull subscriber can use the Java **Subscriber** client with a **MessageReceiver** callback; inside the callback:

~~~java
// Code inside the callback registered with Subscriber:
// Ack only after durable processing succeeds.
try {
    processAndCommit(message);  // Application-defined business function.
    consumer.ack();
} catch (Exception ex) {
    consumer.nack();
}
~~~

This is a **pseudocode fragment**, not a standalone compilable Java class because **processAndCommit, message, and consumer** must be declared in the actual callback. With **enforceInTransit=true**, verify the Subscriber client also uses an allowed **regional endpoint**.

## 11. Mechanisms easily confused with message storage policy

| Mechanism | Effect | NOT equivalent to |
|---|---|---|
| **Message storage policy** | Where message contents are stored/processed | **message retention** or backups |
| **Subscription message retention** | How long a subscription retains messages, including backlog | Residency, encryption, IAM |
| **Topic message retention** | Retains copies of messages on the topic for a configured window | Allowing other regions |
| **Snapshot / Seek / Replay** | Restores consumption state within supported bounds | Data recovery if an entire region or key is lost |
| **Ordering key** | Preserves per-key order under config/region rules | Authorization and encryption |
| **Exactly-once delivery** | Strengthens delivery guarantees for **pull subscriptions** within scope | Business transactional exactly-once |
| **CMEK** | Controls the encryption layer via KMS | Guaranteeing single-region data or encrypting individual payload fields |
| **VPC Service Controls** | Mitigates data exfiltration outside a security perimeter | Replacing message storage policy or Pub/Sub IAM |

**Example:** setting subscription retention to **7 days** does not restrict message contents to Vietnam or Asia. To control region, use a message storage policy; to block processing outside allowed regions, enable **enforceInTransit** and matching endpoints.

If a topic uses **ordering keys** and a policy excludes the nearest processing region, Pub/Sub may return errors due to ordering and location constraints. Test actual policies before running multi-region production ordering or exactly-once workloads.

## 12. Monitoring IAM, CMEK, and message location

### 12.1. Metrics to watch in Cloud Monitoring

| Goal | Pub/Sub metric | Response |
|---|---|---|
| Failing publishes | **topic/send_request_count**, grouped by `response_code` | Distinguish 403 from `FAILED_PRECONDITION` |
| Failing pulls | **subscription/pull_request_count** | Inspect IAM, KMS, region/endpoint |
| Abnormal StreamingPull | **subscription/streaming_pull_response_count** | Look for `response_code` **FAILED_PRECONDITION**; do not treat every stream close as an outage |
| Backlog by region | **subscription/num_unacked_messages_by_region** | Track queued counts per region |
| Backlog bytes by region | **subscription/unacked_bytes_by_region** | Verify data distribution across regions |
| Aging messages | **subscription/oldest_unacked_message_age_by_region** | Alert before retention expires |
| Delivery health | **subscription/delivery_latency_health_score** | Locate delays from publish to delivery |

Per Cloud Monitoring guidance, **prefer metrics with the `_by_region` suffix** for backlog when monitoring region-sensitive systems: global metrics can suffer gaps if one region stops reporting while others remain healthy.

### 12.2. Inspect actual location—never guess from topic ID

In **Cloud Monitoring → Metrics Explorer**:

1. Select Pub/Sub metric **subscription/unacked_bytes_by_region**.
2. Filter by subscription **orders-worker-sub** and project.
3. Group by **region** to inspect unacknowledged bytes over time.
4. Cross-check displayed regions against **messageStoragePolicy.allowedPersistenceRegions**.
5. Also inspect **topic/subscription retained acked bytes by region** when retention/replay is enabled.

**Note:** backlog metrics measure only remaining unacked messages; they **do not prove** all past acked messages stayed in the right location. Metrics have sampling lag, and charts may look empty when backlog is zero—combine metrics with policy configs, audits, and change history.

### 12.3. Auditing and cost

- **Cloud Audit Logs** can record IAM/topic policy changes; check **Data Access logs** enablement, service scope, and pricing.
- **Cloud KMS audit logs** help diagnose disabled keys or permission errors; never log KMS secret material.
- **Cloud Billing** tracks Pub/Sub throughput/storage, cross-region/outbound traffic induced by storage policies, Cloud KMS cryptographic operations, and logging/Monitoring.
- Apply labels/owners to topics and subscriptions per policy, review permissions periodically, and test IAM after rotating service accounts.
- Budget alerts warn on spend yet **do not stop services automatically**; when restricting to one region, evaluate availability and network costs too.

## 13. Symptom-based troubleshooting

| Symptom | Hypothesis | How to verify |
|---|---|---|
| **PERMISSION_DENIED** on publish | Publisher SA lacks Pub/Sub Publisher on topic, wrong identity/project | **gcloud pubsub topics get-iam-policy**, ADC/runtime SA |
| **PERMISSION_DENIED** on pull | Subscriber lacks consume permission on subscription | **get-iam-policy**, effective roles, resource name |
| Cannot create subscription | Missing subscription create in project or `attachSubscription` on topic | Permissions in **both project and topic**, cross-project grants |
| Authenticated push returns 401/403 | Wrong OIDC audience/Invoker, push SA, or token creator IAM | Push config, Cloud Run IAM, Pub/Sub service agent |
| **FAILED_PRECONDITION** right after enabling `enforceInTransit` | Publisher/subscriber handled outside allowed regions | Topic policy, **regional endpoint**, client region |
| Push delivery stops after tightening policy | Allowed regions do not cover push/external export processing location | Push metrics, policy, endpoint/export location |
| **FAILED_PRECONDITION** despite right regional endpoint | KMS key disabled, key permissions revoked, or billing | KMS IAM/versions/audit, billing, Pub/Sub error details |
| Updated allowed regions yet old data remains in old region | Policy **does not migrate already-published messages** | Retention/backlog/snapshots, policy update timestamp |
| Enabled enforce yesterday, mysteriously off today | `gcloud update` passed only allowed regions, omitting enforce flag | Describe topic, review update command/IaC |
| CMEK rotated yet new key version not used yet | Pub/Sub key rotation has propagation lag, not retroactive | Cloud KMS logs, topic key config, up to 12 hours |
| Subscription backlog grows | Subscriber cannot ack due to IAM/KMS/region or code errors | **_by_region** backlog, pull errors, GKE/Cloud Run logs |
| No data in `_by_region` metric | Zero backlog, metric sampling lag, or wrong filter | Time window, resource/region, compare other metrics |
| Publish runs yet consumer misses messages | Subscription/filters/ack/retry issue, not always IAM | Subscription settings, `eventId`, subscriber logs, DLQ |

### Layered troubleshooting workflow

~~~mermaid
flowchart TD
    E["Publish/Pull error"] --> ERR{"HTTP/gRPC code?"}
    ERR -->|"PERMISSION_DENIED"| IAM["Verify principal and resource IAM"]
    ERR -->|"FAILED_PRECONDITION"| PRE{"In-transit region or CMEK?"}
    PRE --> REGION["Topic policy + endpoint + client region"]
    PRE --> KEY["KMS IAM + key version + Cloud Audit"]
    ERR -->|"INVALID_ARGUMENT"| CFG["Schema / topic / request config"]
    ERR -->|"UNAVAILABLE/DEADLINE_EXCEEDED"| RETRY["Transient outage / quota / retry policy"]
    IAM --> OBS["Readback + metrics + negative test"]
    REGION --> OBS
    KEY --> OBS
    CFG --> OBS
    RETRY --> OBS
~~~

**Never fix every error by broadening IAM or disabling `enforceInTransit`.** Isolate the real root cause; a KMS error can present with the same **FAILED_PRECONDITION** code as a region error.

## 14. Case study: multi-region Java orders and data residency

The **An Binh** operations team runs two Cloud Run/GKE clusters:

- **asia-southeast1**: primary API and workers holding transaction data.
- **asia-east1**: standby region activated when the primary site fails.

Message security policy:

| Goal | Design |
|---|---|
| Prevent other services from publishing orders | Publisher IAM scoped strictly to topic **orders-resident** |
| Prevent workers from reading out-of-scope events | Subscriber IAM scoped strictly to the target subscription |
| Staff manage KMS without reading messages | Separate KMS admin, Pub/Sub service agent, and subscriber |
| Store only in two allowed regions | `allowedPersistenceRegions = asia-southeast1, asia-east1` |
| Process all requests inside allowed regions | `enforceInTransit=true`; publishers and subscribers use **regional endpoints** |
| Support key rotation | CMEK rotation plus runbook keeping old key versions until old retention expires |
| Support recovery | Re-point client endpoints, workloads, subscription replay, and data stores; do not assume policy fails over automatically |

### 14.1. Region failover is more than flipping a flag

When running publishers/consumers in **asia-east1**:

1. Confirm the region is in the allowed list and permitted by organization policy.
2. Switch Java clients to **pubsub.asia-east1.rep.googleapis.com:443** via configuration; never hardcode an immutable endpoint in an image release.
3. Confirm runtime service accounts/Workload Identity have required IAM and backend databases/storage also have a regional failover plan.
4. Monitor **publish success, pull, and backlog by region**; if ordering or exactly-once is enabled, verify regional compatibility constraints.
5. If using a **regional Cloud KMS key**, evaluate key availability when failing over to another region; using global CMEK where policy allows can be simpler.

**No implicit promise:** merely listing two regions in a topic policy does not provide active-active replication of all messages or automatic endpoint failover. Regional readiness requires end-to-end design across publishers, subscribers, APIs, KMS, and data stores.

### 14.2. Acceptance test matrix

| Test | Expected |
|---|---|
| `orders-publisher` publishes to topic | Succeeds |
| `orders-publisher` pulls subscription | **PERMISSION_DENIED** if no other role exists |
| `orders-subscriber` pulls subscription | Succeeds |
| External principal publishes | Blocked unless granted IAM |
| Publish from disallowed region with `enforce=true` | **FAILED_PRECONDITION** |
| Java publisher uses allowed regional endpoint | Succeeds if IAM/quota/KMS valid |
| CMEK service agent lacks CryptoKey Encrypter/Decrypter | Topic creation/operation fails with KMS error; caught in lab |
| Update region policy | New messages follow policy; **old messages do not auto-migrate** |
| Rotate KMS key | New key applies with delay; old messages are not re-encrypted |
| Primary region fails | Client/app failover runbook executes per plan, accepting switchover delay |
| Backlog grows | `_by_region` metrics and alerts trigger |

## 15. Exercises and suggested answers

### Exercise A — Choose the right role

A Java producer only publishes to **orders-events**; a worker only pulls from **orders-worker-sub**. Which roles should be granted and where?

**Answer:** **roles/pubsub.publisher** on the topic for the producer; **roles/pubsub.subscriber** on the subscription for the worker. Never grant Pub/Sub Admin to applications.

### Exercise B — Right principal for CMEK

A topic uses a KMS key; the publisher has the Publisher role, yet Pub/Sub reports missing KMS permissions. Should you grant **roles/cloudkms.cryptoKeyEncrypterDecrypter** to the publisher?

**Answer:** No. Grant it to the **Pub/Sub service agent of the topic's project** on the target key; the publisher does not directly encrypt/decrypt DEKs.

### Exercise C — Storage policy vs. transit policy

A topic allows storage only in **asia-southeast1** with **enforceInTransit=false**. A publisher from the US still succeeds. Does that violate the policy?

**Answer:** Not necessarily. Pub/Sub may accept the request in another region and route the content to `asia-southeast1` for persistence. To reject requests processed outside allowed regions, enable **enforceInTransit** and use a matching regional endpoint.

### Exercise D — Accidentally dropping enforcement

An update command passes only **--message-storage-policy-allowed-regions=asia-east1** when **enforceInTransit=true** was previously enabled.

**Question:** Risk? **Answer:** CLI update can reset omitted in-transit attributes back to default. Pass **--message-storage-policy-enforce-in-transit** again to keep it enabled, and read back the topic config.

### Exercise E — Region change and old data

A topic storing in **us-central1** is updated to **asia-southeast1**. Do all previously published messages immediately move to Asia?

**Answer:** No. The new policy applies to **new messages** and does not migrate historical data. Inspect backlog, retention/snapshots, and legacy data handling policies.

### Exercise F — CMEK rotation

KMS rotates the key version at 09:00; at 09:10 the system still uses the old version. Is this an immediate bug?

**Answer:** Not necessarily. Pub/Sub can take up to **12 hours** to adopt a new key version; older messages continue using the pre-rotation key. Do not disable the old key while older data still needs to be read.

### Exercise G — Interpreting error codes

After enabling in-transit enforcement, a Java Pub/Sub client using the global endpoint returns **FAILED_PRECONDITION**. What should you do first?

**Answer:** Check **allowedPersistenceRegions**, inspect which region actually handled the request, and switch to an **allowed regional endpoint**. Also check key/billing status since the same error code can stem from KMS.

### Exercise H — Locating data via metrics

You need to prove a subscription's backlog is no longer sitting in a prohibited region. Which metric helps, and what is its limitation?

**Answer:** **subscription/unacked_bytes_by_region** or **num_unacked_messages_by_region**, filtered to the subscription and grouped by region. It measures **current backlog** only—it does not prove all previously acked messages were deleted or moved out of the region.

### Exercise I — Production design

Design a Java `orders-api` on Cloud Run and a consumer on GKE meeting these requirements: only those two services have access, dedicated CMEK, allowed regions **asia-southeast1/asia-east1**, all Publish/Pull processed inside allowed regions, with failover and monitoring.

**Guided answer:** separate KSA/Cloud Run IAM with minimal topic/subscription grants; service agent KMS permissions; topic message storage policy + `enforceInTransit`; configurable regional endpoints for region switching; idempotent consumer, regional backlog alerts, retention/rollback, and CMEK rotation/failover runbooks.

## 16. Summary and references

**Six takeaways to remember:**

1. **IAM controls who:** Publisher on the topic, Subscriber on the subscription; distinguish runtime identities from the Pub/Sub service agent.
2. **Pub/Sub encrypts at rest by default**; CMEK increases Cloud KMS control at the cost of extra overhead and availability risk.
3. With **CMEK**, Cloud KMS wraps/unwraps DEKs rather than encrypting every payload individually. **Attributes are not encrypted by Pub/Sub at the application layer** like message data.
4. **Message storage policy** restricts where **message contents** are stored/processed, not topic names/labels/IAM; updating the policy **does not move old messages**.
5. **enforceInTransit=true** rejects requests processed outside allowed regions; publishers and pull subscribers should use allowed **regional endpoints**.
6. **KMS rotation, IAM, backlogs, regional endpoints, and app failover** must be tested together—never mistake a storage policy for HA, backups, or retention.

**Official Google Cloud documentation:**

1. [Pub/Sub IAM access control](https://docs.cloud.google.com/pubsub/docs/access-control) — topic, subscription, and permission grants.
2. [Pub/Sub predefined roles](https://docs.cloud.google.com/iam/docs/roles-permissions/pubsub) — Publisher, Subscriber, Admin, Viewer.
3. [Configure message encryption](https://docs.cloud.google.com/pubsub/docs/encryption) — default encryption, CMEK, service agent, and key rotation.
4. [Configure message storage policies](https://docs.cloud.google.com/pubsub/docs/resource-location-restriction) — `allowedPersistenceRegions`, `enforceInTransit`, organization policy.
5. [Pub/Sub API endpoints](https://docs.cloud.google.com/pubsub/docs/reference/service_apis_overview) — global, regional, locational, and selection guidance.
6. [Pub/Sub API error codes](https://docs.cloud.google.com/pubsub/docs/reference/error-codes) — `PERMISSION_DENIED`, `FAILED_PRECONDITION`, and troubleshooting.
7. [Authenticate push subscriptions](https://docs.cloud.google.com/pubsub/docs/authenticate-push-subscriptions) — OIDC push, service agent IAM, and audience.
8. [Monitor Pub/Sub](https://docs.cloud.google.com/pubsub/docs/monitoring) — regional backlog/latency metrics.
9. [Create topics with gcloud](https://docs.cloud.google.com/sdk/gcloud/reference/pubsub/topics/create) — message storage policy and CMEK flags.
10. [Update topics with gcloud](https://docs.cloud.google.com/sdk/gcloud/reference/pubsub/topics/update) — recompute and update flags.
11. [Java Pub/Sub Publisher.Builder](https://docs.cloud.google.com/java/docs/reference/google-cloud-pubsub/latest/com.google.cloud.pubsub.v1.Publisher.Builder) — endpoint, batching, ADC options.
