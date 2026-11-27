# Firebase Projects and Their Relationship to Google Cloud Projects

## Learning Objectives

After this lesson, you will be able to:

1. Explain why a **Firebase project and a Google Cloud project are the same underlying project**, not two separate systems requiring manual synchronization.
2. Distinguish **project display name, project ID, project number**, **Firebase App ID**, Android package name, Apple bundle ID, and Web app registrations.
3. Create a new Firebase project or **add Firebase to an existing Google Cloud project** in a controlled way without accidentally creating a second project.
4. Manage **IAM, Firebase Security Rules, service accounts, Spark/Blaze billing**, organization policies, and Google Analytics appropriately.
5. Separate **development, staging, and production**; configure Firebase CLI, client apps, and Java/Cloud Run backends without mixing up projects.
6. Troubleshoot wrong projects, permission denied errors, rising costs, and accidental deletion using an actionable runbook.

## 1. Context: One System, Two Management Toolsets

In the **CLOUD_PROVIDERS_GCP** module, you have learned **projects, IAM, VPC, Cloud Run, GKE, Cloud Storage, and databases**. Firebase adds web/mobile app tooling such as **Firebase Authentication, Cloud Firestore, Cloud Storage for Firebase, Cloud Messaging, Hosting, Remote Config**, and client SDKs.

Suppose a company builds an ordering application:

- **Web and Android apps** sign in through Firebase Authentication.
- **Cloud Firestore** holds shopping carts and UI state requiring near-realtime sync.
- **Java/Spring Boot orders-api** on Cloud Run processes transactional order logic.
- **Cloud SQL** stores financial transactions; **Pub/Sub** distributes events.
- Operations uses **Google Cloud IAM, Cloud Logging, Monitoring, and Billing**.

Everything can live inside **the same Google Cloud project with Firebase enabled**. The Firebase console and Google Cloud console are **two views/interfaces over one shared project resource boundary sharing identities, IAM, and billing**.

~~~mermaid
flowchart TB
    ORG["Google Cloud Organization / Folders"] --> P["Google Cloud project<br/>shop-prod-001"]
    P --> F["Firebase configuration<br/>Firebase console + Apps"]
    P --> G["Google Cloud resources<br/>IAM, Cloud Run, VPC, SQL, Pub/Sub"]
    F --> WEB["Firebase Web App registration"]
    F --> AND["Firebase Android App registration"]
    F --> AUTH["Firebase Authentication"]
    F --> FS["Cloud Firestore"]
    F --> ST["Cloud Storage for Firebase"]
    G --> RUN["Cloud Run Java backend"]
    RUN --> FS
    WEB --> AUTH
    WEB --> FS
    AND --> AUTH
~~~

**Core principle:** Firebase does not create a nested Google Cloud sub-project; a **Firebase project IS a Google Cloud project with Firebase services/configuration enabled**. When you add Firebase, the **project ID and project number remain unchanged**.

## 2. Resource and Application Hierarchy

| Component | Position in model | Example | Meaning |
|---|---|---|---|
| **Google Cloud organization/folder** | Above projects when centrally managed | org → engineering → prod | Inherits IAM and organization policies |
| **Google Cloud / Firebase project** | Boundary for resources, APIs, billing, permissions | shop-prod-001 | Both consoles inspect the same project |
| **Firebase App registration** | Web/Android/Apple app inside a project | shop-web, shop-android | Configures client SDKs; does not create a new project |
| **Cloud Firestore database** | Database resource belonging to the project | (default), orders-catalog | Collections/documents, location, Security Rules |
| **Firebase Authentication** | Project identity service | Web/mobile end users | App users differ from cloud IAM principals |
| **Cloud Run service** | Compute resource in the Google Cloud project | orders-api | Java server with its own service identity |
| **Cloud Billing account** | Payment account linked to projects | billing-account-A | Can pay for multiple projects |

### 2.1. Firebase project vs Firebase App

One Firebase project can register multiple **Web, Android, and Apple apps** sharing the project's backend resources:

~~~text
Project shop-prod-001
  Firebase Web App: Shop Website (own appId)
  Firebase Android App: com.example.shop
  Firebase Apple App: com.example.shop.ios
  Firebase Authentication: project users
  Cloud Firestore: project data
  Cloud Run: orders-api server
~~~

**Three Firebase Apps do not automatically mean three databases or three bills.** They share the project's backends unless code explicitly targets different resources. When you need isolated data, IAM, and billing across environments, create **separate projects** rather than just adding a Firebase App named "staging."

Firebase documentation limits projects to roughly **30 Firebase Apps per project**. Never use app registrations as a multi-tenant backend isolation mechanism.

### 2.2. Adding Firebase does not initialize every product

Adding Firebase to a Google Cloud project **does not mean** a Firestore database, Authentication user pool, Storage bucket, or Cloud Run service has been created. Each product has its own initialization step, APIs, data location, Security Rules/IAM, and billing. Seeing the project in the Firebase console **is not enough to conclude Firestore is ready**.

## 3. Distinguishing Identifiers

| Name | Hypothetical example | Mutable? | Where used |
|---|---|---|---|
| **Project display name** | Shop Production | Yes | Human-readable label in consoles |
| **Project ID** | shop-prod-001 | **No after provisioning** | gcloud, Firebase CLI, API resource names |
| **Project number** | 123456789012 | No | IAM service agents, Firebase config, certain APIs |
| **Firebase App ID** | 1:123456789012:web:abc123 | Assigned upon app registration | Firebase SDK/app registration |
| **Android package name** | com.example.shop | Bound to registered app | Android builds/SHA setup |
| **Apple bundle ID** | com.example.shop.ios | Bound to registered app | iOS configuration |
| **Web API key** | Value in Firebase config | Can be rotated/restricted | Routes certain Firebase APIs; **not an admin secret** |

**Project ID** is globally unique across Google Cloud/Firebase and cannot be edited once provisioned. Deleting a project **permanently retires that project ID** from reuse. **Project number** is Google-assigned and immutable. Changing the **Display name** does **not change the ID in APIs/CLIs**.

### 3.1. Reading metadata from both consoles and CLI

**Firebase console:** Project settings → **General** displays project name, ID, number, and registered Apps.

**Google Cloud console:** IAM & Admin → Settings/Project info; IAM, Billing, and APIs & Services all bind to the same project.

~~~bash
# Read metadata without modifying resources
gcloud projects describe shop-prod-001 \
  --format="yaml(projectId,projectNumber,name,labels,lifecycleState)"

gcloud config get-value project
firebase projects:list
~~~

If Firebase CLI omits a project that Google Cloud CLI lists, the cause may be **Firebase has not been added yet**, different CLI identities/principals, missing IAM/Terms acceptance, or project state. **Never create a new project with a similar name to "fix" it** before checking.

### 3.2. Web SDK configuration

~~~javascript
// Illustrative data; copy your app's real config from Firebase Project settings.
const firebaseConfig = {
  apiKey: "EXAMPLE_PUBLIC_WEB_API_KEY",
  authDomain: "shop-prod-001.firebaseapp.com",
  projectId: "shop-prod-001",
  appId: "1:123456789012:web:example"
};
~~~

Web/Android/Apple configs help client SDKs locate the right project and app registration. Fields like **apiKey/projectId** do not grant admin privileges, though **API keys need proper restrictions**; Firestore data must still be protected by **Firebase Authentication + Security Rules** or server-side IAM. Never treat a visible API key as proof that a backend is either secure or compromised.

## 4. Create a New Project or Add Firebase to an Existing One?

| Case | Action | Result |
|---|---|---|
| No Google Cloud project exists yet | Firebase console → Create a project; or Firebase CLI create | Creates a new Google Cloud project and adds Firebase |
| Cloud Run/VPC/SQL already exist in a Google Cloud project | Firebase console → Add Firebase to Google Cloud project | **Enables Firebase on the existing project**, keeping resource IDs/IAM/billing |
| Separate dev/prod projects exist | Enable Firebase on each project as needed | Separate environment boundaries |

### 4.1. Pre-flight checks before adding Firebase

1. Confirm **project ID**, organization/folder, owner, and environment.
2. Verify IAM permissions and that **Firebase Terms of Service** are accepted by the account (via Firebase console).
3. Check the Cloud Billing account; linked billing may put the Firebase project on the **Blaze** plan.
4. Inventory existing services (Cloud SQL/Cloud Run/Firestore), data locations, and permissions.
5. Decide whether to enable **Google Analytics**: it is optional during setup and carries location/data-sharing implications.

### 4.2. Adding Firebase via console

1. Sign in to the **Firebase console** with an account holding permissions on the Google Cloud project.
2. Select **Create a project**, then **Add Firebase to Google Cloud project**.
3. Locate and pick the exact prepared project; review **ID and organization**.
4. Accept terms if prompted and review the Google Analytics option.
5. Click **Add Firebase**, then compare ID/number in **Project settings → General** against `gcloud`.

### 4.3. Using Firebase CLI

~~~bash
# List first only
firebase login
firebase projects:list

# IMPACTFUL ACTION: pick an existing project at the prompt.
firebase projects:addfirebase

# Creating a new Google Cloud project and enabling Firebase is a DIFFERENT operation:
# firebase projects:create my-new-firebase-project
~~~

**Do not create a new project** when your goal is reusing existing Cloud Run, IAM, and billing. Programmatically, use the **Firebase Management API `projects.addFirebase`** or Terraform resource **`google_firebase_project`** per IaC workflows.

### 4.4. What happens when you add Firebase?

Per Firebase documentation, adding Firebase can:

- Enable required Firebase-related APIs and backing services.
- Create the project's **Firebase service agent** and Firebase Admin SDK service account.
- Generate a **browser API key** with default restrictions for relevant Firebase APIs.
- Add the project label **firebase:enabled**.

**Never manually add that label to pretend Firebase is enabled.** More importantly, **Add Firebase has no supported full undo**. Manually disabling APIs or deleting service accounts/keys can break dependent services. Review it as a long-term project change.

**Minimum permissions to add Firebase** per documentation include **firebase.projects.update**, **resourcemanager.projects.get**, **serviceusage.services.enable**, and **serviceusage.services.get**. Never grant Owner broadly just to get past this step; assign authorized personnel and confirm the workflow.

## 5. One Shared IAM System and Project Hierarchy

A Firebase project **does not maintain a separate Google Cloud IAM system**. Principal permissions on the Google Cloud project also govern corresponding Firebase resources; roles granted in the Firebase console are reflected in **Google Cloud IAM**.

| User / identity | Typical task | Permission principle |
|---|---|---|
| **Project administrator** | Add Firebase, manage project configuration | Admin roles via IAM, approval, and audit |
| **Firebase developer** | Manage Firebase Apps, Hosting, Rules per task | Product-specific Firebase roles, avoiding broad project roles |
| **Data administrator** | Design Firestore databases/indexes, data migrations | Scoped Firestore/Datastore roles as needed |
| **Cloud Run runtime SA** | Java reading/writing Firestore and calling Google Cloud APIs | Only required permissions on Firestore/Storage |
| **Firebase service agent** | Operates Firebase services behind the scenes | Google-managed service identity; never delete arbitrarily |
| **Mobile/web end user** | Sign in to app and access client data | **Firebase Authentication + Security Rules**, never project IAM |

### 5.1. Firebase console and Cloud console display IAM differently

**Firebase console → Project settings → Users and permissions** shows only a subset of principals holding basic/Firebase roles, not the full Google Cloud project IAM policy. Check **service accounts and broader roles** in **Google Cloud console → IAM & Admin → IAM**.

Read-only command example:

~~~bash
gcloud projects get-iam-policy shop-prod-001 \
  --format="table(bindings.role,bindings.members)"
~~~

This gives an overview of project bindings; to determine **effective permissions**, also inspect inherited org/folder bindings, IAM Conditions, custom roles, resource-level policies, and deny policies. Never conclude a principal lacks access simply because it is absent from Firebase's Users and permissions page.

### 5.2. Organization policies apply to Firebase too

If a project sits under a Google Cloud organization/folder, it **inherits organization policies**—such as allowed resource locations, service-account key creation restrictions, allowed services, or IAM domain restrictions. Using the Firebase console **never bypasses** org policies.

If adding Firebase fails because an API is blocked, never move a production project out of its organization to "work around it"; collaborate with your platform/security team to adjust policies or pick compliant products/locations.

### 5.3. Firebase Authentication user vs Cloud IAM principal

An end user with a **Firebase Auth UID** (e.g., `u_456`) is not a Google Cloud service account or IAM user. Client SDKs send Firebase Auth ID tokens so Security Rules can check **`request.auth.uid`**; never grant **`roles/editor`** or **`roles/datastore.user`** on the project to individual customers.

**Firebase Authentication** handles application user identity. **Google Cloud IAM** governs deployment principals and server API access. Apply each layer in its proper context.

## 6. Firestore Security Rules and IAM Do Not Replace Each Other

Cloud Firestore is a Google Cloud resource inside the Firebase project, yet access control **depends on the access path**.

| Access path | Authentication | Primary authorization control |
|---|---|---|
| **Web/Android/Apple Firebase client SDK** | Firebase Authentication or unauthenticated | **Cloud Firestore Security Rules** |
| **Java server on Cloud Run** using Admin SDK/Google Cloud Firestore server SDK | **ADC**/Cloud Run service identity | **Google Cloud IAM** |
| **GKE Java worker** via server client library | Workload Identity Federation/ADC | **Google Cloud IAM** |
| **Firebase console / Cloud console administrators** | Google accounts with roles | IAM/admin permissions |

**Common confusion:** Server SDKs/Admin SDKs **bypass Cloud Firestore Security Rules** and authorize through IAM. Therefore, a ruleset denying all clients **does not block** a server holding Datastore/Firestore IAM permissions. Conversely, granting IAM to a backend **does not let** web users bypass Security Rules.

### 6.1. Example Rules restricting each user to their own data

~~~text
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /users/{userId} {
      allow read, write: if request.auth != null
                         && request.auth.uid == userId;
    }
  }
}
~~~

This example covers only **/users/{uid}** documents. Other paths are not allowed automatically. Before production, add checks for **schema fields, size limits, roles, update rules**, and test unauthorized access using the **Local Emulator Suite**.

**Never use `allow read, write: if true`** to "fix permission errors" in production. And if a Java server is permitted by IAM, editing Security Rules will not restrict it.

### 6.2. Changing Security Rules can affect all Firebase Apps

If Web and Android both point to **shop-prod-001**, deploying a shared ruleset affects both apps. Via CLI, **`firebase deploy --only firestore`** can overwrite existing rules/index configurations per `firebase.json`. Review diffs, test on emulator/staging, and use an approved pipeline.

When a project hosts multiple Firestore databases, each database's configuration/rules must be managed explicitly. Never assume a ruleset on `(default)` automatically covers every database in the project.

## 7. Shared Billing: Spark, Blaze, and Google Cloud Services

The billing account attaches to the **Google Cloud project**, not to an individual Firebase App. Thus if Cloud Run, Cloud SQL, Firestore, and Hosting share one project, all SKUs bill to that project's billing account.

| Firebase plan | Meaning | Notes |
|---|---|---|
| **Spark** | No-cost plan with free-tier product quotas | Does not unlock paid Google Cloud services; exceeding quotas can halt service |
| **Blaze** | Pay-as-you-go when the project links a Cloud Billing account | Certain products include free allowances, while usage above thresholds is billed |

**Adding Firebase to a Google Cloud project with billing enabled puts Firebase on Blaze.** Linking a Cloud Billing account to a Firebase project can also **automatically upgrade it to Blaze**. There is no separate "Firebase billing" per App registration inside the same project.

### 7.1. Total cost breakdown example

A production project can incur charges across components:

| Component | Cost driver |
|---|---|
| **Cloud Firestore** | Document reads/writes/deletes, storage, network, index-related usage, and plan features |
| **Cloud Storage for Firebase** | Bucket bytes, operations, outbound/egress |
| **Cloud Run/Cloud SQL** | Compute, memory, database storage, networking |
| **Firebase Hosting/App Hosting** | Storage, builds, bandwidth/runtime per product |
| **Cloud Logging/Monitoring** | Ingestion, retention, metrics/alerts per billable tier |
| **Firebase Authentication** | Pricing and limits vary by auth method/identity product |

Never quote a flat price for a "Firebase project" because the bill is driven by **per-service usage** and resource configuration.

### 7.2. Checking billing before enabling Blaze

~~~bash
# Read-only metadata and linked billing status.
gcloud projects describe shop-prod-001 \
  --format="yaml(projectId,projectNumber)"

gcloud billing projects describe shop-prod-001
~~~

You need Cloud Billing view permissions (such as project billing information view permission). If it returns `PERMISSION_DENIED`, never assume the project has no billing; check with your Billing administrator.

**Cloud Billing budget alerts only notify—they do not cap spending or stop Firestore/Cloud Run.** Separating staging/prod projects lets you isolate budgets, IAM, and alerts, though it does not replace quotas and capacity planning.

## 8. Adding Firebase Apps to the Right Project and Platform

After enabling Firebase, register Firebase Apps **inside the chosen project**. Each app receives platform-specific config.

| Platform | Required identifiers | Config file/object |
|---|---|---|
| **Web** | Firebase App nickname/registration | JavaScript `firebaseConfig` |
| **Android** | Package name, optionally SHA fingerprints for auth features | `google-services.json` |
| **Apple** | Bundle ID and product settings | `GoogleService-Info.plist` |

**A Firebase App nickname is not a project ID.** Download config files from the Firebase console; never fabricate dummy App IDs when deploying real apps.

### 8.1. Listing registered apps via CLI

~~~bash
firebase projects:list

# Use the exact project ID of the environment.
firebase apps:list --project shop-dev-001

# Inspect an existing Web app config (replace FIREBASE_APP_ID with the real ID).
firebase apps:sdkconfig WEB FIREBASE_APP_ID \
  --project shop-dev-001
~~~

These commands are read-only. If an app does not exist yet, **register it first** in the Firebase console or via `firebase apps:create` for that platform. **Never pick the production project merely because it appears first in the list.**

### 8.2. A Web API key is not an Admin SDK key

**Web app configs include a public API key by design**; pair it with API/application restrictions per Google Cloud docs and controls like Auth, Firestore Security Rules, and App Check where applicable. This key is **not** a database password or service-account private key. Conversely, a **service-account JSON private key** is a high-risk secret that must never appear in web bundles, mobile APKs/IPAs, Git, or public Hosting.

### 8.3. Google Analytics is a separate linking choice

Creating a Firebase project may ask whether to enable **Google Analytics**. Linking an Analytics property brings its own reporting, location, and data-sharing settings; **never treat a Firestore database as a Google Analytics dataset**. Nor is Analytics a Firestore backup mechanism. You can still use supported Firebase products without enabling Google Analytics.

## 9. Designing Environment Separation: Dev, Staging, and Production

Organizations should treat a **project** as a primary isolation boundary for data, IAM, resource quotas, API keys, and billing:

| Environment | Google Cloud/Firebase project | Data | Permissions and workflow |
|---|---|---|---|
| **Development** | shop-dev-001 | Synthetic/anonymized data | Developers experiment freely, small budgets |
| **Staging** | shop-stage-001 | Production-like sanitized dataset | CI/CD and QA, Rules testing, migrations |
| **Production** | shop-prod-001 | Real customer data | Least privilege, release approvals, backups, alerts |

**Never use one production project and create Firebase apps named dev, stage, and prod as a substitute for environment isolation.** They still share IAM, the Firebase Authentication user store, and backend resources.

### 9.1. Firebase CLI project aliases

Inside a frontend app directory holding Firebase CLI configuration:

~~~bash
firebase use --add
firebase use

# Only after configuring the corresponding alias:
firebase use dev

# Always specify project/alias explicitly when deploying to reduce mistakes.
# After reviewing the ruleset, this modifies the dev environment.
firebase deploy --only firestore:rules --project dev
~~~

Sample `.firebaserc` in an application repo (illustrative; do not create in the lesson repo):

~~~json
{
  "projects": {
    "dev": "shop-dev-001",
    "staging": "shop-stage-001",
    "prod": "shop-prod-001"
  }
}
~~~

Aliases help select the right project, but they **do not grant permissions** and **do not lock down production**. CI pipelines should pass explicit project IDs/aliases with separated credentials and required approvals—never rely on whatever project happens to be active on a laptop.

### 9.2. Mobile/web configuration per build variant

- **Android:** use `google-services.json` per product flavor/build variant; verify package name and SHA certificates.
- **Apple:** use `GoogleService-Info.plist` matching the build target and bundle ID.
- **Web:** use separate `firebaseConfig` objects for dev/prod; `projectId` and `appId` must match the registered app.
- **Java backend:** use the Cloud Run project's service account; configured `projectId` must match the target database.

Mixing up config files causes **dev apps to write into the production project** even when backends are separate. Release reviews must verify the **actual `projectId`/`appId`**, not just domain URLs or `NODE_ENV`/`SPRING_PROFILES_ACTIVE`.

### 9.3. Emulator does not replace production rules testing

**Firebase Local Emulator Suite** lets you test Firestore, Auth, and select Firebase services locally:

~~~bash
# From a source project with firebase.json configured for emulators:
firebase emulators:start --only auth,firestore --project demo-shop-dev
~~~

Using a **`demo-`** prefixed ID for emulated runs lowers the risk of touching real cloud services when running supported emulators. However, **not every product or API is emulated**; if code invokes an unemulated service, verify failure/routing behavior before running tests.

## 10. Java/Cloud Run Backend Sharing the Google Cloud Project

A Java service on Cloud Run can use the **Firebase Admin SDK** to verify Firebase Authentication tokens or read Cloud Firestore. On Google Cloud infrastructure, **Application Default Credentials (ADC)** uses short-lived service identities instead of static JSON service account key files.

### 10.1. Java example initializing the Firebase Admin SDK

Add `com.google.firebase:firebase-admin` to your Java project using a CI-pinned, vulnerability-checked version. Java example:

~~~java
import com.google.auth.oauth2.GoogleCredentials;
import com.google.cloud.firestore.DocumentSnapshot;
import com.google.cloud.firestore.Firestore;
import com.google.firebase.FirebaseApp;
import com.google.firebase.FirebaseOptions;
import com.google.firebase.cloud.FirestoreClient;

public final class FirebaseProjectProbe {
    private FirebaseProjectProbe() {}

    public static void main(String[] args) throws Exception {
        String projectId = "shop-dev-001"; // Choose via environment configuration.

        FirebaseOptions options = FirebaseOptions.builder()
            .setCredentials(GoogleCredentials.getApplicationDefault())
            .setProjectId(projectId)
            .build();

        FirebaseApp app = FirebaseApp.initializeApp(options);
        Firestore firestore = FirestoreClient.getFirestore(app);
        try {
            DocumentSnapshot document = firestore.collection("healthchecks")
                .document("lab-example")
                .get()
                .get();
            System.out.println("Firestore request OK; exists=" + document.exists());
        } finally {
            firestore.close();
            app.delete();
        }
    }
}
~~~

**Prerequisites:** the Firestore database exists, the API is enabled, and the ADC principal holds appropriate IAM permissions. This snippet shows how **`projectId`** is specified; **in real applications**, read project from environment config and initialize the SDK once at startup (never create/delete `FirebaseApp` per HTTP request).

**Never hardcode production service account JSON private keys or point `GOOGLE_APPLICATION_CREDENTIALS` at a key baked into a container image.** On Cloud Run, grant minimal roles to the runtime service account; on GKE, use Workload Identity Federation.

### 10.2. Assigning a service account to Cloud Run

~~~bash
# Read-only inspection of service identity and project before making changes.
gcloud run services describe orders-api \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --format="yaml(spec.template.spec.serviceAccountName,status.url)"

# Impactful action: run only after IAM and environment have been reviewed.
gcloud run services update orders-api \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --service-account=orders-runtime@shop-dev-001.iam.gserviceaccount.com
~~~

If the Java SDK accesses Firestore, the principal needs matching **Firestore IAM permissions**; **`roles/datastore.user`** is a fairly broad predefined read/write role, not least privilege by default. Consider custom roles/permissions or splitting services by use case.

**Important:** the Cloud Run service's project and the Firestore database's project **can be different**. If Java specifies a different `projectId`, verify **cross-project IAM and resource policies** rather than granting Owner across both projects.

### 10.3. Distinguishing client Firebase Auth from server verification

~~~mermaid
sequenceDiagram
    participant U as Mobile/Web app
    participant AUTH as Firebase Authentication
    participant API as Cloud Run Java API
    participant FS as Cloud Firestore
    U->>AUTH: Sign in
    AUTH-->>U: ID token
    U->>API: HTTPS + ID token
    API->>API: Verify signature, issuer, audience/project
    API->>FS: Firestore Admin SDK, ADC/IAM
    FS-->>API: Document response
    API-->>U: Business response
~~~

The server must **verify the Firebase ID token** via the Firebase Admin SDK (signature, issuer, audience/project, and expiry)—never trust a user ID sent in raw JSON. A customer's Firebase Authentication token is **not** a Google Cloud IAM access token. When the Java server calls the Firestore Admin SDK, **Security Rules are not executed**; the backend must check business permissions against verified user ID/claims before querying.

## 11. Project Boundaries Are Not Location Boundaries

**A Firebase/Google Cloud project does not share one single storage location across all products.** Each resource has its own location: Cloud Run region, Cloud SQL region, Firestore database location, Storage bucket location, Analytics reporting location.

| Resource | Location decision | What to evaluate |
|---|---|---|
| **Cloud Firestore database** | Chosen at database creation | Region/multi-region, residency, latency, immutability of location |
| **Cloud Run orders-api** | Chosen per deploy region | Proximity to Firestore/SQL and users |
| **Cloud SQL** | Chosen at instance creation | Private networking, HA, backup/DR |
| **Cloud Storage bucket** | Chosen per bucket | Residency, egress, lifecycle |
| **Google Analytics** | Reporting location/property config | Compliance and data terms |

Naming a Firebase project **`shop-vn-prod`** **does not guarantee** Firestore/Analytics/Storage store data in Vietnam. When data residency is required, verify individual resource locations and organization policies; pick the Firestore database location carefully because it cannot simply be switched after creation.

**Architectural pattern:** Cloud Run Java in `asia-southeast1`, Firestore near the backend in a supported location, Cloud SQL in a matching region, Storage/Analytics per compliance rules. Putting components in different regions adds inter-service latency and data transfer charges. Never assume the Firebase console automatically co-locates all services.

## 12. Project Lifecycle, Changes, and Data Deletion

### 12.1. There are not two separate Delete Project buttons

**Deleting a Firebase project also deletes the underlying Google Cloud project**, including Cloud Run, Cloud SQL, IAM, Storage, and APIs in that project per applicable deletion and retention workflows. Conversely, deleting a Google Cloud project deletes its Firebase project as well.

**Do not confuse three operations:**

| Operation | Impact |
|---|---|
| **Delete a Firebase App registration** | Removes the client app registration; does not delete the project or Firestore data |
| **Delete a Firestore database/bucket** | Deletes that product's resource/data; may impact multiple Firebase Apps |
| **Delete a Firebase / Google Cloud project** | Affects the entire project resource set; risks unrecoverable data loss |

Google Cloud offers a **shutdown/recovery window** for projects pending deletion, but **never treat it as a backup or assume all data is recoverable**. Before any deletion, inventory resources, back up/export, verify owners, check legal retention, review cost and dependencies, and obtain change-control approval.

### 12.2. Can you "remove Firebase" and keep the project?

Once Firebase is added to a Google Cloud project, **there is no supported full "remove Firebase" rollback** to restore the exact prior state. You can stop using Firebase products and perform manual cleanup, though deleting service accounts, APIs, browser keys, or labels can break dependent Firebase/Google Cloud features.

**When unsure of the impact, leave the configuration intact and consult an administrator**, rather than deleting all Firebase service identities simply because a mobile app was retired.

### 12.3. Backups and recovery must be per product

- **Cloud Firestore:** managed backups/exports, PITR where supported, retention, and restore rehearsals.
- **Cloud SQL:** instance-level backups/PITR.
- **Cloud Storage:** versioning/lifecycle/backups per requirements and features.
- **Firebase Authentication:** user records need their own export/restore plan and permissions.
- **Google Analytics:** separate retention/reporting; never replaces application backups.

**A Firestore export does not back up the entire Firebase project**—it omits IAM, Firebase App registrations, Authentication configs, Hosting, Cloud Run, and SQL. Manage configs with IaC, Git reviews, and cross-service recovery runbooks.

## 13. Observing Operations and Cost Across Both Consoles

### 13.1. Which dashboard answers which question?

| Question | Where to look first |
|---|---|
| Which Firebase Apps are registered? | Firebase console → Project settings → General |
| Firestore reads/writes, rules, and indexes? | Firebase console → Firestore; Google Cloud Firestore metrics |
| Who modified project IAM? | Google Cloud IAM & Admin, Cloud Audit Logs |
| Cloud Run Java returning HTTP 5xx? | Cloud Logging/Monitoring, Cloud Run service metrics |
| Billing spike from Firestore or Cloud Run? | Cloud Billing reports (filter by project/service/SKU) |
| Android/iOS app crashes? | Firebase Crashlytics |
| Per-app mobile analytics? | Google Analytics for Firebase, if linked |

**Firebase projects share billing, yet no single dashboard replaces Cloud Monitoring and Cloud Billing.** When investigating an incident, record the project ID, timestamp, service/app registration, and affected users, then switch between consoles while keeping the exact same project selected.

### 13.2. Operational guardrails

1. **Project labels** for env, team, cost-center, and data-classification; separate Google Cloud resources with naming conventions.
2. **Budgets and alerts** per dev/staging/prod, alongside workload-appropriate quotas and API limits.
3. **Least-privilege IAM**, periodic reviews of active service accounts and unused keys, and auditing of Rules/Storage/API changes.
4. **Automated Security Rules tests** via the emulator; verify Java server authorization because Admin SDK bypasses Rules.
5. **Monitoring** for Firestore reads/writes/errors, Cloud Run latency, auth failures, storage usage, and cost.
6. **Release workflows** requiring approval for changes to Firebase rules, Cloud IAM, billing, or data locations.

Never treat **Spark** as a universal financial "hard cap" across all technologies: product quotas and paid Google Cloud service eligibility differ. **Blaze has no unlimited free tier**; usage above free allowances increases the bill.

## 14. Troubleshooting Firebase and Google Cloud Project Relationships

| Symptom | Common cause | Where to check |
|---|---|---|
| Firebase console doesn't show a Google Cloud project | Firebase not added, principal lacks permissions, Terms unaccepted | Project ID, IAM, Terms, use CLI/REST |
| Adding Firebase returns **403 PERMISSION_DENIED** | Missing `firebase.projects.update` or `serviceusage` permissions | Google Cloud IAM, org policies, Firebase Terms |
| Added `firebase:enabled` label manually, no Firebase Apps | Labels do not provision Firebase services | Use Firebase console/CLI/Management API properly |
| Cannot change Project ID | Immutable after provisioning | Use display name or create a new project and migrate |
| Dev Firebase app reads production data | Client config has wrong `projectId`/`appId` or build variant | Env-specific config files, Firebase SDK options |
| User visible in Google Cloud console, missing in Firebase Users and permissions | Firebase console shows only a limited subset of roles/principals | IAM & Admin → IAM, service accounts |
| Firestore client gets **PERMISSION_DENIED** | Unauthenticated or rejected by Security Rules | Firebase Auth UID, Rules simulator, emulator tests |
| Java Admin SDK reads Firestore despite deny Rules | Server SDK uses IAM and bypasses Firestore Rules | Cloud Run runtime SA, backend business auth checks |
| Java server gets 403 in the same project | Runtime SA lacks IAM; not a Firebase user role issue | ADC, effective IAM permissions, API enabled |
| Client uses valid API key yet data leaks | Weak Rules or broken backend access control | Rules tests, App Check/Authentication, server authorization |
| Enabling billing switched Firebase to Blaze | Google Cloud project linked to Cloud Billing | Billing project info, Firebase usage and billing |
| Firebase project still bills after deleting Web App | Cloud Run/SQL/Storage/Firestore still running | Billing by service/SKU, resource inventory |
| CLI Rules deploy breaks another app | Multiple Firebase Apps share one project/ruleset | `firebase.json`, deploy history, staging tests |
| Firestore created in wrong location | Project name does not set resource region | Firestore database location, data migration plan |
| Deleting project wiped Cloud Run/Cloud SQL too | Firebase and Google Cloud share the same project | Project deletion recovery/backup plan |

### Ordered diagnostic runbook

1. **Confirm project ID/number** in both Firebase and Google Cloud consoles.
2. **Confirm the acting identity**: Firebase CLI account, `gcloud` account, Java ADC, or Firebase Auth user—never mix them up.
3. **Confirm resource type**: project, Firebase App registration, Firestore database, Cloud Run service, or Billing account.
4. **Target the right security layer**: Firebase Security Rules for clients, IAM for server/Admin SDKs, App Check/Auth per design.
5. **Check environment and config**: dev/staging/prod aliases, `appId`, service accounts, secrets, API restrictions.
6. **Cross-check billing and logs**, then apply minimal fixes and run negative tests on staging before production.

Never "fix" every 403 by granting **Owner** or opening Firestore Rules publicly. Both shortcuts usually introduce far worse risk than the original error.

## 15. Synthesis Scenario: Java Backend and Mobile App

Team **Sunflower** builds a delivery application:

| Component | Development | Production |
|---|---|---|
| Google Cloud/Firebase project | shop-dev-001 | shop-prod-001 |
| Firebase Web/Android app | Dev build variants | Release builds |
| Firebase Authentication | Test users | Real users |
| Cloud Firestore | Mock documents + restrictive rules | Customer documents + reviewed rules |
| Java/Spring Boot API | Cloud Run dev | Cloud Run prod |
| Cloud SQL | Test orders | Production transactions |
| Billing | Small, low alert thresholds | Budget/SLO/alerts with assigned owner |
| IAM | Developers in dev | Least-privilege runtime SA, release approvers |

### 15.1. Workflow to add Firebase to an existing architecture

~~~mermaid
flowchart TD
    A["Google Cloud project with Cloud Run/SQL"] --> B["Review IAM, org policies, Billing"]
    B --> C["Add Firebase to that same project"]
    C --> D["Verify project ID / number unchanged"]
    D --> E["Register Web/Android Firebase Apps"]
    E --> F["Create Firestore + Authentication config"]
    F --> G["Test client Security Rules with emulator"]
    G --> H["Cloud Run Java Admin SDK via ADC/IAM"]
    H --> I["Verify logs, billing, backups"]
    I --> J["Release staging → production"]
~~~

### 15.2. Pre-production acceptance tests

| Test | Expected |
|---|---|
| GCP project before/after Add Firebase | **Same project ID and number** |
| Firebase project with only a registered web app | Does not auto-create Cloud SQL/Firestore database |
| Dev web app using dev `firebaseConfig` | Cannot read/write production Firestore |
| User A accesses user B's document | Denied by Security Rules |
| Java Admin SDK reads Firestore | Needs runtime IAM; independent of client Security Rules |
| Runtime SA without Firestore IAM | Denied on server API calls |
| CI deploys rules using `dev` alias | Does not alter production rules |
| Linking a Cloud Billing account | Understood and verified upgrade to Blaze |
| Choosing Firestore location | Residency/latency reviewed before creation |
| Deleting a test Firebase App registration | Does not delete the project or backend data |

### 15.3. Consequences of poor design

If a staging app accidentally points to production Firebase, QA writes mock data into the live system, corrupting metrics and inflating bills; worse, client apps could reach sensitive data if Rules are loose. If an admin deletes a "test Firebase project" that is actually the Google Cloud project hosting production Cloud Run, the outage impacts the entire system.

**Key safeguards:** clear environment naming, CI approvals blocking cross-environment deploys, proper use of IAM/Roles and Security Rules, per-service backups, verifying project IDs in release artifacts, and monitoring costs per project/service.

## 16. Exercises and Answers

### Exercise A — One project or two?

**Scenario:** `shop-prod-001` is a Google Cloud project running Cloud Run. The team clicks "Add Firebase" on that project and registers two Firebase Apps.

**Question:** How many extra Google Cloud projects are created? How many Firebase Apps exist?

**Answer:** **Zero new Google Cloud projects**; the original project simply has Firebase enabled. There are **two Firebase App registrations**, not two Firebase projects.

### Exercise B — Project ID vs display name

A team renames the display name from "Shop Test" to "Shop Production," yet CLI commands still reference `shop-test-001`.

**Answer:** Display name does not change **project ID**. To isolate production, create a separate project, migrate/configure resources and client app registrations—never rename a test project and treat it as a fresh production environment.

### Exercise C — Permissions in the Firebase console

A Cloud Run service account does not appear in Firebase Project settings → Users and permissions, yet Java can still read Firestore.

**Answer:** The Firebase console does not show every IAM principal or service account. Inspect **Google Cloud IAM**, runtime ADC identity, and effective roles. The Java server SDK uses IAM, not Firebase client Security Rules.

### Exercise D — 403 error

User A's mobile app is denied reading user B's document, while the Java backend's service account can read both.

**Answer:** If Rules check `request.auth.uid == userId`, that is **working as designed** for clients. The Java backend via Admin SDK bypasses Security Rules, so it must authenticate and authorize each business request itself. Never open Rules broadly so mobile apps can read everything.

### Exercise E — Spark vs Blaze billing

An organization has a Google Cloud project with an active Cloud Billing account and adds Firebase. An engineer assumes it stays on Spark so Cloud Run is always free.

**Answer:** Incorrect. A Google Cloud project linked to Billing runs Firebase on **Blaze**, billed per service; Cloud Run, Cloud SQL, and Firestore each have their own quotas, limits, and pricing tables. **Budget alerts do not automatically stop charges.**

### Exercise F — Separating dev and prod

One Firebase project contains three app registrations named `mobile-dev`, `mobile-stage`, and `mobile-prod`.

**Question:** Are data, IAM, and billing isolated?

**Answer:** **No.** They share one project; create **separate Google Cloud/Firebase projects** for dev/staging/prod and configure Firebase SDKs, CLI aliases, service accounts, and tests accordingly.

### Exercise G — Web API key vs service account key

A review finds a Web `firebaseConfig` containing an API key and `appId`, while a private service-account JSON key was committed into the frontend.

**Answer:** The Firebase Web API key is a public client config needing appropriate API/application restrictions, not an Admin credential. **The service-account private key is a critical secret** that must be revoked/rotated immediately, scrubbed from code and release history, and replaced on the server with ADC/service identity.

### Exercise H — Add Firebase fails

Running `firebase projects:addfirebase` returns **403 PERMISSION_DENIED**, even though `gcloud projects describe` succeeds.

**Answer:** Read metadata access **does not grant** permission to update Firebase projects or enable APIs. Check IAM permissions **`firebase.projects.update`, `resourcemanager.projects.get`, `serviceusage.services.enable/get`**, Firebase Terms acceptance, and organization policies.

### Exercise I — Data residency

A team sets the project display name to "Shop Vietnam" and assumes Firestore and Google Analytics automatically store data in Vietnam.

**Answer:** Incorrect. Project display names do not govern data residency. Select **Firestore database location, Storage bucket region, and Analytics reporting location** per supported regions; evaluate latency, egress, residency, and location-change constraints.

### Exercise J — Removing an app

A team wants to retire an unused Android app. Someone suggests clicking **Delete Firebase project**.

**Answer:** Wrong scope. A Firebase project is the Google Cloud project; deleting it affects all resources. Instead, remove only the **Firebase App registration** and clean up related resources systematically without deleting shared backends. Take backups and verify dependencies before any destructive action.

## 17. Summary and References

**Six key takeaways:**

1. **Firebase project = Google Cloud project with Firebase enabled**, sharing the **same project ID/number, IAM, billing, and organization hierarchy**.
2. **Firebase Apps** are client registrations inside a project; adding an app **does not** create a separate database or billing environment.
3. Adding Firebase to an existing project **does not create a new project**, may enable APIs/service identities, and **has no supported full undo**.
4. **Firebase Security Rules** govern client SDKs, whereas **Java/server Admin SDKs use IAM**; neither layer replaces the other.
5. Projects linked to Cloud Billing run Firebase **Blaze**; monitor costs per service rather than treating plan names or budget alerts as hard caps.
6. Isolate **dev/staging/prod with separate projects**, align Firebase app configs, service identities, and Firestore locations, and verify data/costs before deploying or deleting.

**Official documentation:**

1. [Understand Firebase projects](https://firebase.google.com/docs/projects/learn-more) — structure, IDs, apps, and resource hierarchy.
2. [Use Firebase with an existing Google Cloud project](https://firebase.google.com/docs/projects/use-firebase-with-existing-cloud-project) — Add Firebase workflow, IAM prerequisites, and irreversible changes.
3. [Firebase project management REST API](https://firebase.google.com/docs/reference/firebase-management/rest/v1beta1/projects) — `projects.addFirebase` and identifier mapping.
4. [Firebase CLI reference](https://firebase.google.com/docs/cli) — `projects:addfirebase`, `projects:create`, aliases, `apps:list`.
5. [Firebase project IAM](https://firebase.google.com/docs/projects/iam/overview) — roles, principals, and Google Cloud IAM console.
6. [Firebase pricing plans](https://firebase.google.com/docs/projects/billing/firebase-pricing-plans) — Spark, Blaze, and Cloud Billing.
7. [Configure multiple Firebase projects](https://firebase.google.com/docs/projects/multiprojects) — dev/prod, SDK configs, build variants.
8. [Firebase API keys](https://firebase.google.com/docs/projects/api-keys) — API key restrictions and public config model.
9. [Get started with Cloud Firestore Security Rules](https://firebase.google.com/docs/firestore/security/get-started) — client rules and server IAM.
10. [Firebase Admin SDK setup](https://firebase.google.com/docs/admin/setup) — Java/ADC/Cloud Run.
11. [Firestore server client quickstart](https://firebase.google.com/docs/firestore/quickstart-server) — Java Firestore SDK.
12. [Firebase project setup best practices](https://firebase.google.com/docs/projects/dev-workflows/general-best-practices) — environments, apps, and data boundaries.
