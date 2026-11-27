# Hands-on file upload processing with a Java function on Cloud Run functions and Eventarc

> **Chapter:** Cloud Run functions and Eventarc  
> **Module:** **CLOUD_PROVIDERS_GCP** — Explore Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners select services, protect resources, automate releases, and monitor reliability alongside cost.

**Problem:** a user uploads a **.txt** file to Cloud Storage. The system must automatically read the file, count lines/bytes, compute SHA-256, and write a JSON report to a different bucket without running an always-on server. We implement this using **Cloud Run functions (Java 21)**, **Eventarc Standard**, and **Cloud Storage**. This lesson caps input files at **1 MiB** so the example safely reads contents into memory; production workloads with large files should use streaming or a batch architecture.

Two requirements cannot be overlooked: **Eventarc may deliver the same event multiple times** and **Cloud Storage objects can be overwritten**. Therefore, the function uses **bucket + object name + generation** as the file version identifier and creates the output file with a **does-not-exist precondition** to prevent duplicate writes.

## Learning objectives

After completing this lesson, learners will be able to:

1. Distinguish **Cloud Run functions**, **Functions Framework**, **CloudEvents**, **Eventarc triggers**, and **Cloud Storage object finalized**.
2. Write a Java class implementing **CloudEventsFunction** and parse object metadata.
3. Read the **exact generation** of a file from Cloud Storage, validate type/size, and process UTF-8 text.
4. Write a JSON report with a stable name and a duplicate-preventing precondition.
5. Configure the **build identity**, **runtime service account**, **trigger identity**, and **Cloud Storage service agent** following least privilege.
6. Deploy the function, create the trigger, upload test files, inspect logs/outputs, and troubleshoot common errors.
7. Explain retries, idempotency, trigger loop risks, overwritten data, file security, and costs.
8. Clean up lab resources within proper scope, then extend to image/PDF processing or queues when appropriate.

## 1. Architecture and processing order

~~~mermaid
sequenceDiagram
    participant U as Uploader
    participant IN as Cloud Storage input bucket
    participant EA as Eventarc Standard
    participant FN as Cloud Run function Java
    participant OUT as Cloud Storage output bucket
    U->>IN: Upload incoming/hello.txt
    IN-->>EA: Object finalized event
    EA->>FN: Authenticated HTTP CloudEvent
    FN->>FN: Validate bucket/name/generation
    FN->>IN: Read object@generation
    IN-->>FN: UTF-8 contents
    FN->>FN: Count lines, bytes, SHA-256
    FN->>OUT: Create summary JSON, doesNotExist
    OUT-->>FN: Created or already exists
    FN-->>EA: 2xx success
~~~

**Separating two buckets** is a simple way to avoid loops: an **output** object created after processing does not land in the **input bucket** watched by the trigger. If using the same bucket, you need prefix filters and code guards to stop self-triggering; filtering only in code still generates events and charges.

| Component | Illustrative lab name | Role |
|---|---|---|
| Project | YOUR_PROJECT_ID | Holds all lab resources |
| Region | asia-southeast1 | Hosts function, buckets, and trigger |
| Input bucket | INPUT_BUCKET_UNIQUE | Stores **incoming/*.txt** |
| Output bucket | OUTPUT_BUCKET_UNIQUE | Stores **summaries/*.json** |
| Cloud Run function | file-upload-java-lab | Event processing code |
| Eventarc trigger | file-upload-finalized-lab | Filters finalized events from the input bucket |
| Runtime service account | fileproc-runtime | Reads input, creates output |
| Trigger service account | fileproc-trigger | Receives events and invokes the function |
| Image repository | cloud-run-source-deploy | Source-built image, potentially shared |

Bucket names must be **globally unique**. In these examples, learners must replace placeholders with real names and record them before running mutating commands.

### 1.1. What does Eventarc send to the function?

Eventarc sends a **CloudEvent** to Cloud Run over HTTP. For Cloud Storage direct events:

- **type:** google.cloud.storage.object.v1.finalized.
- **id:** event ID; usable for tracing/dedup.
- **source:** emitting event source.
- **data.bucket:** bucket name.
- **data.name:** object name, not a VM filesystem path.
- **data.generation:** object content version.
- **data.metageneration:** metadata version, **distinct** from generation.

**Finalized** occurs when a new object is created or overwritten, creating a new generation. It does **not** mean "the file was virus-scanned, has valid MIME, was approved, or will not be modified again." The system must still validate contents before processing.

### 1.2. Cloud Run functions vs. legacy Cloud Functions

The primary deployment method in this lesson is:

~~~bash
gcloud run deploy SERVICE_NAME \
  --source . \
  --function functions.ProcessUpload \
  --base-image java21 \
  --region REGION
~~~

Only afterward do you create the **Eventarc trigger** using **gcloud eventarc triggers create**. Do not use the legacy syntax **gcloud functions deploy --trigger-resource/--trigger-event** to demonstrate the current Cloud Run functions product. **--function** takes the Java class name including its package.

The function is still managed by Cloud Run as a service with a URL and revisions. **Do not grant public unauthenticated access** just so Eventarc can invoke it; configuring a **trigger identity** with Cloud Run Invoker is the right solution.

## 2. Safety decisions before running

**Deployment commands can incur charges** across Cloud Build, Artifact Registry, Cloud Run, Eventarc/Pub/Sub, Cloud Storage, logs, and networking. Run only in an authorized lab project with a budget, and never use someone else's production bucket.

| Risk | Lab guardrail |
|---|---|
| Oversized file | Max **1 MiB**; reject larger files |
| Non-text file | Only **.txt** names, text/plain MIME if present; valid UTF-8 |
| Duplicate processing | Output keyed by **bucket/name/generation**, create-only |
| Overwriting input files | Do not overwrite the same object key during basic lab; see versioning in section 9 |
| Trigger loop | Input and output in **different buckets** |
| Sensitive data | Never log file contents; log only hash, size, line count |
| Overly broad permissions | Runtime only reads input and creates output objects; trigger only invokes/receives |
| Continuous retries | Distinguish permanent vs. transient errors; monitor retries and DLQ |
| Accidentally making public | Keep service authenticated; Eventarc uses a service account |

**Example scope:** computes SHA-256, byte count, and line count; **does not** handle PII, virus scanning, archive extraction, PDFs, or executing uploaded files. If applied to a system accepting files from the Internet, add real content inspection, quotas, rate limiting, antivirus if required, and retention/access policies.

## 3. Preparing the project, APIs, CLI, and IAM

### 3.1. Context check (read-only)

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
REGION="asia-southeast1"
FUNCTION="file-upload-java-lab"
TRIGGER="file-upload-finalized-lab"
INPUT_BUCKET="INPUT_BUCKET_UNIQUE"
OUTPUT_BUCKET="OUTPUT_BUCKET_UNIQUE"

gcloud auth list
gcloud config list project
gcloud projects describe "$PROJECT_ID"

# Inspect enabled APIs.
gcloud services list --enabled --project="$PROJECT_ID"

# Check for naming collisions.
gcloud run services list --project="$PROJECT_ID" --region="$REGION"
gcloud eventarc triggers list --project="$PROJECT_ID" --location="$REGION"
gcloud storage buckets list --project="$PROJECT_ID"
~~~

Do not rely solely on **gcloud config get project** when working across multiple environments: every mutating command should pass **--project** or explicitly scope the project. Bucket names are globally unique; **never create a bucket using someone else's name**.

### 3.2. Required APIs and identities

Core APIs include **run.googleapis.com**, **cloudbuild.googleapis.com**, **artifactregistry.googleapis.com**, **eventarc.googleapis.com**, **eventarcpublishing.googleapis.com**, **pubsub.googleapis.com**, **storage.googleapis.com**, plus supporting logging/IAM services. Check organization policies/quotas before enabling.

~~~bash
# MODIFIES project configuration — only when authorized.
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  eventarc.googleapis.com \
  eventarcpublishing.googleapis.com \
  pubsub.googleapis.com \
  storage.googleapis.com \
  --project="$PROJECT_ID"
~~~

| Principal | Permissions to consider | Purpose |
|---|---|---|
| Deployer | Cloud Run Source Developer, Service Account User on runtime SA; trigger creation, bucket/IAM management per role | Deploy code and create Eventarc trigger |
| Cloud Build identity | Cloud Run Builder and Artifact Registry permissions per build path | Build Java / push image |
| Runtime SA | Storage Object Viewer **on input bucket**, Storage Object Creator **on output bucket** | Read inputs and create new reports only |
| Trigger SA | Eventarc Event Receiver and Cloud Run Invoker on the exact service | Receive events and invoke the authenticated function |
| Cloud Storage service agent | Pub/Sub Publisher per Eventarc direct Storage events guide | Emit events to the transport layer |
| Eventarc service agent | Platform-granted/managed service agent role | Coordinate trigger/transport |

**Do not conflate the runtime SA with the trigger SA**: runtime reads/writes objects; trigger invokes the Cloud Run service. The **Cloud Build SA** is a third identity used during builds and should not hold write access to the output bucket unless needed.

### 3.3. Creating two separate service accounts

~~~bash
# MODIFIES IAM — run only in a lab project.
gcloud iam service-accounts create fileproc-runtime \
  --project="$PROJECT_ID" \
  --display-name="File processor runtime"

gcloud iam service-accounts create fileproc-trigger \
  --project="$PROJECT_ID" \
  --display-name="Eventarc delivery identity"

RUNTIME_SA="fileproc-runtime@$PROJECT_ID.iam.gserviceaccount.com"
TRIGGER_SA="fileproc-trigger@$PROJECT_ID.iam.gserviceaccount.com"

# READ-ONLY confirmation of existence.
gcloud iam service-accounts describe "$RUNTIME_SA" --project="$PROJECT_ID"
gcloud iam service-accounts describe "$TRIGGER_SA" --project="$PROJECT_ID"
~~~

If an SA already exists in the project, **do not recreate it**; verify its owner/IAM instead. In production, use IaC and approvals. Creating a service account does not automatically grant the deployer permission to attach it (**iam.serviceAccounts.actAs**); an administrator grants **roles/iam.serviceAccountUser** at the appropriate SA scope.

## 4. Java project and Maven dependencies

Create a **separate learner lab directory** rather than creating these sample files inside the knowledge repository currently being updated. Structure:

~~~text
file-upload-java-lab/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── functions/
                └── ProcessUpload.java
~~~

### 4.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>dev.example</groupId>
  <artifactId>file-upload-java-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>libraries-bom</artifactId>
        <version>26.32.0</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
    </dependencies>
  </dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.google.cloud.functions</groupId>
      <artifactId>functions-framework-api</artifactId>
      <version>1.1.0</version>
      <scope>provided</scope>
    </dependency>
    <dependency>
      <groupId>com.google.cloud</groupId>
      <artifactId>google-cloudevent-types</artifactId>
      <version>0.14.0</version>
    </dependency>
    <dependency>
      <groupId>com.google.cloud</groupId>
      <artifactId>google-cloud-storage</artifactId>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>com.google.cloud.functions</groupId>
        <artifactId>function-maven-plugin</artifactId>
        <version>0.11.0</version>
        <configuration>
          <functionTarget>functions.ProcessUpload</functionTarget>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**Library versions** are pinned so the example is reproducible, based on published official samples; for production, update the BOM/framework on a security schedule, verify Java runtime compatibility, and run tests/scans. **Functions Framework API** defines the CloudEventsFunction interface; **google-cloudevent-types** defines StorageObjectData; **google-cloud-storage** provides the SDK for reading/writing objects.

### 4.2. Code design rules

The function must:

1. Accept only **google.cloud.storage.object.v1.finalized** and the configured input bucket.
2. Read only **incoming/*.txt**, ignoring objects in other folders.
3. Read the **exact generation**; never fetch the "latest live version" when an older event arrives late.
4. Check the object's actual size before loading into RAM; enforce a 1 MiB limit.
5. Check MIME (when present) and decode UTF-8 strictly.
6. Compute line count, byte count, and SHA-256.
7. Name the output object from the hash of **bucket + name + generation**.
8. Create output with **doesNotExist()** so duplicate deliveries are safe; propagate other errors for retry/investigation.

## 5. Writing the Java file-processing function

Create **src/main/java/functions/ProcessUpload.java**:

~~~java
package functions;

import com.google.cloud.functions.CloudEventsFunction;
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageException;
import com.google.cloud.storage.StorageOptions;
import com.google.events.cloud.storage.v1.StorageObjectData;
import com.google.protobuf.util.JsonFormat;
import io.cloudevents.CloudEvent;

import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Locale;
import java.util.logging.Logger;

public final class ProcessUpload implements CloudEventsFunction {
    private static final Logger LOG =
            Logger.getLogger(ProcessUpload.class.getName());
    private static final long MAX_BYTES = 1024L * 1024L;
    private static final String FINALIZED =
            "google.cloud.storage.object.v1.finalized";

    // SDK uses Application Default Credentials, which on Cloud Run is the runtime SA.
    private final Storage storage =
            StorageOptions.getDefaultInstance().getService();

    @Override
    public void accept(CloudEvent event) throws Exception {
        if (!FINALIZED.equals(event.getType())) {
            LOG.warning("Ignoring non-object.finalized event type");
            return;
        }
        if (event.getData() == null) {
            LOG.warning("Ignoring event with missing data");
            return;
        }

        StorageObjectData.Builder builder = StorageObjectData.newBuilder();
        JsonFormat.parser()
                .ignoringUnknownFields()
                .merge(
                    new String(event.getData().toBytes(),
                               StandardCharsets.UTF_8),
                    builder
                );
        StorageObjectData data = builder.build();

        String inputBucket = requiredEnv("INPUT_BUCKET");
        String outputBucket = requiredEnv("OUTPUT_BUCKET");
        String bucket = data.getBucket();
        String name = data.getName();
        long generation = data.getGeneration();

        // Filter in code to guard against misconfiguration and out-of-scope objects.
        if (!inputBucket.equals(bucket)
                || !name.startsWith("incoming/")
                || !name.toLowerCase(Locale.ROOT).endsWith(".txt")
                || generation <= 0) {
            LOG.info("Ignoring object outside lab scope");
            return;
        }

        // Always pin to the event's generation, never fetch the latest live version.
        Blob blob = storage.get(BlobId.of(bucket, name, generation));
        if (blob == null) {
            // If old version was not retained after overwrite/delete, content
            // cannot be recovered by reading the newer generation.
            LOG.warning("Object generation is no longer available; needs investigation");
            return;
        }

        long size = blob.getSize();
        if (size > MAX_BYTES) {
            LOG.warning("Ignoring file larger than 1 MiB");
            return;
        }

        String mime = blob.getContentType();
        if (mime != null
                && !mime.equals("text/plain")
                && !mime.startsWith("text/plain;")) {
            LOG.warning("Ignoring non-text/plain Content-Type");
            return;
        }

        byte[] bytes = storage.readAllBytes(blob.getBlobId());
        if (bytes.length > MAX_BYTES) {
            LOG.warning("Ignoring file whose actual byte size exceeds limit");
            return;
        }

        // Do not replace malformed bytes with U+FFFD; reject invalid UTF-8 files.
        String text;
        try {
            text = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes))
                    .toString();
        } catch (java.nio.charset.CharacterCodingException e) {
            LOG.warning("Ignoring invalid UTF-8 file");
            return;
        }

        long lines = text.lines().count();
        String contentHash = hexSha256(bytes);

        // Safe output name; never use uploader-supplied object name as an arbitrary write path.
        String identity = bucket + "\n" + name + "\n" + generation;
        String outputName = "summaries/"
                + hexSha256(identity.getBytes(StandardCharsets.UTF_8))
                + ".json";

        String resultJson = String.format(
                Locale.ROOT,
                "{\"generation\":\"%d\",\"bytes\":%d,\"lines\":%d,"
                + "\"sha256\":\"%s\"}%n",
                generation, bytes.length, lines, contentHash
        );

        BlobInfo target = BlobInfo.newBuilder(
                BlobId.of(outputBucket, outputName))
                .setContentType("application/json")
                .build();

        try {
            // Atomic create-if-absent: the same object generation produces at most
            // one summary object, even across concurrent instances.
            storage.create(
                    target,
                    resultJson.getBytes(StandardCharsets.UTF_8),
                    Storage.BlobTargetOption.doesNotExist()
            );
            LOG.info("processed eventId=" + event.getId()
                    + " output=" + outputName);
        } catch (StorageException e) {
            if (e.getCode() == 412) {
                LOG.info("duplicate event: summary already exists "
                        + outputName);
                return;
            }
            // Other IAM/network/quota/transient error: do not fake ACK.
            throw e;
        }
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing environment variable " + name);
        }
        return value;
    }

    private static String hexSha256(byte[] data) throws Exception {
        return HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(data));
    }
}
~~~

### 5.1. Reading the processing flow

- **CloudEventsFunction.accept** is invoked by Functions Framework when Eventarc sends a CloudEvent to Cloud Run. The entry point class is **functions.ProcessUpload**.
- **StorageObjectData** holds event metadata; the **generation** field distinguishes two uploads with the same name.
- **Storage.get(BlobId.of(bucket, name, generation))** fetches the exact object generation; if that version is gone, the example chooses **not** to read the newer version to avoid processing the wrong contents.
- **Blob.getSize** is checked before **readAllBytes** to bound memory. For large files, use streaming and bounded I/O instead of readAllBytes.
- **String.lines()** counts text lines; an empty file has 0 lines. Conventions around blank lines/trailing newlines must be confirmed if used for real business logic.
- **SHA-256** in the output is a checksum of the input bytes, **not** a digital signature or malware-free guarantee.
- **Storage.BlobTargetOption.doesNotExist()** ensures an already-created report is never overwritten; if GCS returns **412 Precondition Failed** on duplicate processing, the function treats it as success.
- If another read/write error occurs and is unhandled, the function throws an exception so Eventarc can retry **according to the trigger's retry policy**.

### 5.2. Why doesn't the code log the filename?

Object names can contain emails, order IDs, or customer details. This example logs only **eventId** and the **hashed output name**, never logging file contents, signed URLs, headers, or tokens. In production, include eventId/traceId in structured logging and enforce sensitive-data redaction policies.

### 5.3. Idempotency conditions and boundaries of this example

For the same **(bucket, name, generation)** tuple, the output object name is identical and the create-only precondition prevents multiple deliveries from creating multiple reports. However, this example **does not guarantee exactly-once execution**: code may execute multiple times, while only **side effects on the output object** are constrained. If you add sending emails, charging payments, writing databases, or publishing Pub/Sub messages, each side effect also needs its own transaction, idempotency key, or outbox.

Events can **arrive out of order**: e.g., generation 3 processed before generation 2. This lesson generates a report per generation so ordering need not be enforced; if your goal is "latest state," you must compare generations and update data conditionally/transactionally.

### 5.4. Maven verification

On a study machine with JDK 21, Maven, and valid Internet/dependency mirror access:

~~~bash
# LOCAL MACHINE COMPILE/TEST ONLY, no cloud deployment.
java -version
mvn -version
mvn -B clean test
~~~

Success criteria: Maven resolves dependencies, compiles the class, and ends with **BUILD SUCCESS**. This lesson does not require modifying the Java learning repository holding this content; learners create a separate lab directory as instructed.

## 6. Creating buckets and granting Storage IAM

### 6.1. Creating two separate buckets (billable)

~~~bash
# REAL MUTATION; bucket names must be globally unique.
gcloud storage buckets create "gs://$INPUT_BUCKET" \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --uniform-bucket-level-access

gcloud storage buckets create "gs://$OUTPUT_BUCKET" \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --uniform-bucket-level-access

# READ-ONLY — check location and policy.
gcloud storage buckets describe "gs://$INPUT_BUCKET"
gcloud storage buckets describe "gs://$OUTPUT_BUCKET"
~~~

**The source bucket and Eventarc trigger must be in the same region or compatible locations per Eventarc rules;** this example places all three in one region. For **Cloud Storage direct events to Cloud Run**, the bucket and destination service belong to the **same Google Cloud project** under the documented setup path. Never move a production bucket to another region just to match a lab; provision fresh lab resources instead.

### 6.2. Granting runtime SA permissions per bucket

~~~bash
# MODIFIES IAM — scoped only to the two lab buckets.
gcloud storage buckets add-iam-policy-binding "gs://$INPUT_BUCKET" \
  --member="serviceAccount:$RUNTIME_SA" \
  --role="roles/storage.objectViewer"

gcloud storage buckets add-iam-policy-binding "gs://$OUTPUT_BUCKET" \
  --member="serviceAccount:$RUNTIME_SA" \
  --role="roles/storage.objectCreator"

# READ-ONLY to verify.
gcloud storage buckets get-iam-policy "gs://$INPUT_BUCKET"
gcloud storage buckets get-iam-policy "gs://$OUTPUT_BUCKET"
~~~

**Object Creator** allows creating new objects without overwriting, reading, or deleting existing objects; it pairs naturally with **doesNotExist()**. If downstream systems later need to read results, grant **Object Viewer** to a separate *reader* per policy rather than expanding the runtime SA by default.

**Versioning note:** soft delete, object versioning, and bucket lifecycle/retention determine whether older generations can be retained and read, and may incur additional charges. Do not disable retention or delete real data just for quick lab cleanup.

## 7. Deploying the Java function

Run from inside the **file-upload-java-lab/** directory containing `pom.xml` and Java source. With Cloud Run functions, source builds use Cloud Build and store images in Artifact Registry; the project must have a properly configured build identity (e.g., **Cloud Run Builder** per function deployment docs).

~~~bash
# MUTATING: create a private Cloud Run function service from source.
gcloud run deploy "$FUNCTION" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --source . \
  --function functions.ProcessUpload \
  --base-image java21 \
  --service-account="$RUNTIME_SA" \
  --no-allow-unauthenticated \
  --memory=512Mi \
  --timeout=120s \
  --max-instances=5 \
  --concurrency=1 \
  --set-env-vars="INPUT_BUCKET=$INPUT_BUCKET,OUTPUT_BUCKET=$OUTPUT_BUCKET"

# READ-ONLY — URL, ready revision, runtime identity.
gcloud run services describe "$FUNCTION" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(metadata.name,status.url,status.latestReadyRevisionName,spec.template)"
~~~

**Configuration explained:** **java21** runtime, **512Mi** RAM, **120-second** timeout, max **5 instances**, and max **1 concurrent request** per instance as configured. These are illustrative limits, not universal defaults for every workload. Cloud Run max instances is **not an absolute cost hard cap** and may be briefly exceeded by service scaling mechanics. If the function must process large files, evaluate timeout, memory, CPU, and batch architecture.

**No trigger exists at this step yet**: the service is Ready, yet uploading a file to the bucket will not invoke Java code until the Eventarc trigger is created and active. If deployment fails, inspect **Cloud Build logs** first; if the build succeeds yet the revision is not Ready, check **Cloud Run logs/runtime settings**.

## 8. Creating the Eventarc trigger and delivery permissions

### 8.1. Trigger identity permissions

Eventarc uses **TRIGGER_SA** to receive events and invoke the authenticated Cloud Run service. Grant **Invoker only on the exact service**, rather than project-wide:

~~~bash
# MODIFIES IAM on the lab project and service.
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$TRIGGER_SA" \
  --role="roles/eventarc.eventReceiver"

gcloud run services add-iam-policy-binding "$FUNCTION" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --member="serviceAccount:$TRIGGER_SA" \
  --role="roles/run.invoker"

# READ-ONLY check of service IAM.
gcloud run services get-iam-policy "$FUNCTION" \
  --project="$PROJECT_ID" --region="$REGION"
~~~

A trigger can be created successfully yet **fail to deliver events to the service** if Invoker is missing. Check logs and Eventarc delivery status instead of enabling public invocation.

### 8.2. Cloud Storage service agent permissions

Direct Cloud Storage events use Pub/Sub as Eventarc Standard's transport layer. The Cloud Storage service agent must hold **roles/pubsub.publisher** per official guidance:

~~~bash
# READ-ONLY — identify the Cloud Storage service agent.
STORAGE_AGENT="$(gcloud storage service-agent --project="$PROJECT_ID")"

# MODIFIES PROJECT IAM — only when needed and approved.
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$STORAGE_AGENT" \
  --role="roles/pubsub.publisher"
~~~

For older projects, the **Pub/Sub service agent** may need **roles/iam.serviceAccountTokenCreator** (especially when the Pub/Sub service agent was enabled before April 8, 2021). Do not grant this role indiscriminately; check the actual service agent and apply only when documented conditions apply.

### 8.3. Creating the trigger

~~~bash
# MUTATING: create an Eventarc Standard trigger filtering finalized events on input.
gcloud eventarc triggers create "$TRIGGER" \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --destination-run-service="$FUNCTION" \
  --destination-run-region="$REGION" \
  --event-filters="type=google.cloud.storage.object.v1.finalized" \
  --event-filters="bucket=$INPUT_BUCKET" \
  --service-account="$TRIGGER_SA"

# READ-ONLY — inspect config and status.
gcloud eventarc triggers describe "$TRIGGER" \
  --project="$PROJECT_ID" --location="$REGION" \
  --format=yaml

gcloud eventarc triggers list \
  --project="$PROJECT_ID" --location="$REGION"
~~~

The trigger must use the **exact input bucket name**, **event type**, and **region**. Filter types cannot be arbitrarily edited after creation; when changing source/type, create a new trigger and handle overlapping events during cutover.

**Activation time:** a trigger can take a few minutes to become ready after creation. Wait for active status before uploading test files; if you upload too early and see no processing, inspect logs and upload **a new object** rather than concluding the system is broken before sync completes.

### 8.4. IAM layers to distinguish

~~~mermaid
flowchart TB
    GCS["Cloud Storage input"] -->|"Storage service agent\nPub/Sub Publisher"| PS["Eventarc/PubSub transport"]
    PS -->|"Trigger SA\nEvent Receiver + Run Invoker"| CR["Cloud Run Java function"]
    CR -->|"Runtime SA\nStorage Object Viewer"| GCS
    CR -->|"Runtime SA\nStorage Object Creator"| OUT["Cloud Storage output"]
    BLD["Cloud Build SA\nBuilder permissions"] --> AR["Artifact Registry"]
    AR --> CR
~~~

These permissions authorize **different calls**; granting bucket Reader to the Runtime SA does not fix an Eventarc 403 Invoker error, and granting Invoker to the Trigger SA does not let Java read files if Runtime lacks Object Viewer.

## 9. Uploading files, inspecting JSON output, and testing edge cases

Sample commands use **bash on Cloud Shell/Linux/macOS/WSL**. If running PowerShell, adjust environment variable syntax before executing. Run inside the lab directory, not inside the knowledge module directory.

### 9.1. Uploading a valid file

~~~bash
# CREATE FILE on lab machine.
printf 'hello\ncloud run\njava eventarc\n' > sample-001.txt

# MODIFIES CLOUD STORAGE: upload as a new object.
gcloud storage cp sample-001.txt \
  "gs://$INPUT_BUCKET/incoming/sample-001.txt"

# READ-ONLY — inspect object metadata and generation.
gcloud storage objects describe \
  "gs://$INPUT_BUCKET/incoming/sample-001.txt" \
  --format="yaml(name,size,contentType,generation)"
~~~

This example uses three lines and a trailing newline. **Expected summary:** **lines=3**, **bytes** matching actual UTF-8 bytes, and the corresponding SHA-256. Do not predict total bytes from Unicode character count if the file contains Vietnamese diacritics; take the byte count from the actual file.

### 9.2. Inspecting events, logs, and outputs

~~~bash
# READ-ONLY — tail Cloud Run service logs.
gcloud run services logs read "$FUNCTION" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --limit=50

# READ-ONLY — list summary objects.
gcloud storage ls "gs://$OUTPUT_BUCKET/summaries/"
~~~

Once you obtain the actual output object name from the listing, inspect the report contents:

~~~bash
# Replace with the actual object path, not the placeholder.
RESULT_OBJECT="summaries/PASTE_REAL_SHA256.json"

gcloud storage cat "gs://$OUTPUT_BUCKET/$RESULT_OBJECT"
~~~

Example JSON output structure:

~~~json
{
  "generation": "1730000000000000",
  "bytes": 33,
  "lines": 3,
  "sha256": "<SHA256_OF_ACTUAL_FILE>"
}
~~~

The **generation, bytes, and sha256** values above only illustrate format, not guaranteed values for your file. Learners must record actual values; the output filename is the **SHA-256 of the identity**, not the SHA-256 of the file contents.

### 9.3. Mandatory test cases

| Input | Expected behavior | What to verify |
|---|---|---|
| **incoming/a.txt**, small UTF-8 | Creates 1 summary | Accurate lines/bytes/SHA-256 |
| **incoming/a.csv** | Ignored | No new summary created |
| **other/a.txt** | Ignored | Prefix guard works |
| **incoming/big.txt** larger than 1 MiB | Ignored | Not loaded into RAM |
| **incoming/binary.txt** with invalid UTF-8 | Ignored | Warning logged |
| Duplicate CloudEvent **same generation** | Output not overwritten | Duplicate/precondition logged |
| Re-upload same filename | New generation; may create new summary | Distinct output per generation |
| Trigger temporarily lacks Invoker | 401/403 delivery failure | IAM on Cloud Run service |
| Runtime SA lacks Object Viewer | Function fails reading | Runtime logs and Storage IAM |

**Do not confuse two uploads of the same name with a duplicate event.** If `gcloud storage cp` overwrites an object at the same key, Cloud Storage creates a **new generation** and by design produces **a new summary**. A true duplicate event is **redelivery of a finalized event for the same generation**; to test it, perform a controlled CloudEvent replay or authorized test injection in a lab environment without altering production producers.

### 9.4. Verifying the content checksum

Inside the lab directory, cross-check the local SHA-256 of **sample-001.txt**:

~~~bash
# READ-ONLY local data check.
sha256sum sample-001.txt
wc -c sample-001.txt
wc -l sample-001.txt
~~~

**wc -l** counts newline characters; for a file without a trailing newline, its result can **differ from String.lines().count()**. This demo includes a trailing newline so results should match. Do not treat this illustrative line-counting function as a valid CSV/JSON parser.

## 10. Idempotency, retries, and permanent error handling

Eventarc Standard delivers events **at least once**, meaning a finalized event can be sent to the function multiple times. Ordering across objects or generations is also not guaranteed like a transaction log.

### 10.1. Decision flow on receiving an event

~~~mermaid
flowchart TD
    E["CloudEvent finalized"] --> F{"Valid bucket, prefix, .txt, and generation?"}
    F -- "No" --> SKIP["Skip, return success"]
    F -- "Yes" --> GET["Read object@generation"]
    GET --> VALID{"MIME, <= 1 MiB, valid UTF-8?"}
    VALID -- "No" --> SKIP
    VALID -- "Yes" --> BUILD["Compute hash, lines, bytes"]
    BUILD --> PUT["Create summary: doesNotExist"]
    PUT --> RESULT{"Write succeeded?"}
    RESULT -- "Newly created" --> ACK["Success"]
    RESULT -- "412 already exists" --> ACK
    RESULT -- "Other transient/IAM error" --> FAIL["Log error and throw"]
    FAIL --> RETRY["Eventarc retry/DLQ per policy"]
~~~

**How ACK works:** when the Java method returns normally, Functions Framework returns a success response to Eventarc. If the method throws an exception, delivery fails and is retried **only if the trigger transport has retries enabled**.

### 10.2. Key facts about retries

- Triggers created with **gcloud CLI** typically enable retries per Pub/Sub transport policy; triggers created from the Cloud Run console may have different defaults.
- In Eventarc Standard, exponential backoff and message retention are typically attached to the Pub/Sub subscription; inspect current settings rather than relying blindly on defaults.
- **Never retry indefinitely in code** on malformed files or permanent errors; this example intentionally logs and ACKs invalid cases.
- Transient infrastructure errors can be retried; persistent missing IAM or missing object generations require investigation/routing to an error flow.
- Configure a **dead-letter topic/subscription policy** per system requirements to analyze persistent failures. Eventarc Standard transports via Pub/Sub; retry/DLQ settings are managed on the Eventarc-created **subscription**, not in a Java variable.
- Keep in mind that retention, retries, and multiple instances can increase costs during downstream outages.

### 10.3. Overwritten objects and missing generations

If an object is re-uploaded under the same name before the older generation's event is processed, reading **object@generation** succeeds only if the old version is retained and readable. Without **Object Versioning**, older generations may no longer be available; this example logs a warning and skips to avoid mistakenly reading the newer generation.

For business requirements that must process *every* version, consider:

1. Enforcing **immutable object names**, never overwriting inputs.
2. Enabling **Object Versioning** and lifecycle policies to retain old generations long enough.
3. Designing appropriate retention/soft delete, cost controls, and read permissions.
4. Using transactional job records/checkpoints or queue/batch systems when strict RPO/RTO applies.
5. Disallowing unnecessary identities from uploading directly to output prefixes/buckets.

**This is an important design boundary**, not a bug that retries can always fix.

## 11. Layered troubleshooting

| Symptom | Possible causes | Where to check |
|---|---|---|
| **Maven BUILD FAILURE** | Missing JDK 21, dependency error, wrong package/class | `java -version`, `pom.xml`, Maven output |
| **Source build 403** | Build SA lacks Builder/Artifact Registry permissions | Cloud Build logs and actual SA |
| **Cloud Run revision not Ready** | Wrong entry point, class doesn't implement CloudEventsFunction, memory/startup | Revision events, runtime logs |
| **Trigger created but inactive** | Eventarc service agent provisioning, wrong filter/location | `describe` trigger, wait for sync, check project |
| **Eventarc delivery 401/403** | Trigger SA lacks **roles/run.invoker**, private service | Service IAM, trigger SA, ingress |
| **Function gets Storage 403** | Runtime SA lacks Object Viewer/Creator or wrong bucket | Runtime SA, bucket IAM, logs |
| **Only skip logs appear** | Name not `incoming/*.txt`, wrong MIME, file >1 MiB | Object name, size, `contentType` |
| **Invalid UTF-8** | Binary file or different encoding | Check file encoding; do not disable validation casually |
| **Generation not found** | Object overwritten/deleted and old version gone | Object Versioning, generations, retention |
| **Duplicate events arrive** | Eventarc at-least-once/retries | Same bucket/name/generation, create-only output |
| **Multiple reports for same filename** | Object got a **new generation** after overwrite | Inspect generation, expected behavior |
| **Continuous retries** | Transient error or long-lived missing permission | Logs, Pub/Sub subscription retry/DLQ |
| **Unusual cost spike** | Trigger loop, retries, heavy uploads, logs, storage | Eventarc metrics, Cloud Run request count, Billing |
| **Output unreadable** | Tester lacks Viewer IAM, not runtime Writer | Caller's output bucket IAM |

### 11.1. Read-only diagnostic commands

~~~bash
# Status of trigger and Cloud Run service.
gcloud eventarc triggers describe "$TRIGGER" \
  --project="$PROJECT_ID" --location="$REGION" \
  --format=yaml

gcloud run services describe "$FUNCTION" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(status.url,status.latestReadyRevisionName,status.conditions,spec.template)"

# Recent logs.
gcloud run services logs read "$FUNCTION" \
  --project="$PROJECT_ID" --region="$REGION" \
  --limit=100

# Inspect trigger and bucket IAM if holding IAM Reader permission.
gcloud run services get-iam-policy "$FUNCTION" \
  --project="$PROJECT_ID" --region="$REGION"

gcloud storage buckets get-iam-policy "gs://$INPUT_BUCKET"
gcloud storage buckets get-iam-policy "gs://$OUTPUT_BUCKET"
~~~

**Separate build errors from event delivery errors.** If Java fails to build, Eventarc is not involved yet. If the Cloud Run service is Ready yet has no request logs, inspect Eventarc/Cloud Storage; if requests arrive yet reading the object returns 403, inspect the **runtime SA** rather than changing trigger SA permissions.

### 11.2. Pre-escalation checklist

1. Confirm the exact **project, region, bucket name, function, and trigger**.
2. Confirm the **object.finalized** event was actually generated *after the trigger became active*.
3. Inspect IAM independently for **trigger SA**, **runtime SA**, and **Cloud Storage service agent**.
4. Read Cloud Run and Eventarc transport logs; record **eventId, generation, and timestamp**, without logging file contents.
5. Classify the error as **permanent** or **transient**, then tune retry/DLQ carefully.
6. Submit tickets only after redacting credentials, signed URLs, and sensitive data.

## 12. Monitoring reliability, security, and cost

### 12.1. Signals to observe

| Group | Metric/log | Why |
|---|---|---|
| Eventarc delivery | Successful/failed event deliveries, retries | Know whether the trigger is delivering events |
| Cloud Run | Invocations, 4xx/5xx, latency, cold starts, instance count | Processing quality |
| Java code | Processed/skip/duplicate/failed; generation, eventId | Diagnose without leaking contents |
| Cloud Storage | Input finalized count, output count, object size | Reconcile events ↔ summaries |
| DLQ | Count of unprocessable events | Avoid silently losing events |
| Cost | Build, Run, Eventarc/Pub/Sub, Storage requests, logging | Analyze spend by SKU |

Count comparisons must account for **at-least-once delivery**: **invocations can outnumber object generations**; a deduplicated ACK still counts as an invocation. Do not equate Cloud Run request count with unique file count.

### 12.2. Securing uploaded files

- Use **Uniform bucket-level access** and bucket/principal IAM; never enable public object reads unless required.
- Avoid giving uploaders write access to the output bucket or permission to alter Eventarc triggers.
- Never place secrets in source code, CloudEvent payloads, or unprotected function environment variables.
- Never trust **file extensions or Content-Type** as complete content validation; production systems may need magic-byte checks, antivirus/DLP, and schema validation.
- Cap object size, concurrency, timeout, and memory to prevent malicious files from exhausting resources.
- Use Cloud Storage **generation preconditions** when updating/transitioning file state to avoid races.
- Never execute uploaded files or extract archives without sandboxing and inspection.
- Store reports/metadata with appropriate retention and permissions; SHA-256 does not anonymize predictable contents.
- For data requiring CMEK or residency, review bucket policies, Cloud Run location, and KMS before deploying.

### 12.3. Cost breakdown

A single upload can incur **Cloud Storage write**, **Eventarc event/transport**, **Cloud Run execution**, **Cloud Storage read + create**, logs, and output storage. Additionally, initial builds/deployments use **Cloud Build/Artifact Registry**. Frequent retries multiply invocations, read requests, and log volume.

Budgeting example, **not listed pricing**:

~~~text
Daily uploads:                     10,000
Average event deliveries:          1.02x per generation
Estimated Cloud Run invocations:   10,200
Max expected JSON outputs:         10,000 if all inputs are valid
Input reads:                       Potentially > 10,000 during retries
Actual charges:                    Check Cloud Billing by Service/SKU/region
~~~

Efficiency is measured not just by **cost per invocation**, but by **cost per successfully processed object generation**. Factor in errors/retention/DLQ and egress charges if producer and consumer sit in different regions.

## 13. Case study: Java document ingestion system

**Hypothetical scenario:** a Java application receives text documents from partners and uploads them to Cloud Storage. A finalized event triggers a Java function to create a summary, and an analytics system reads metadata once output appears.

### 13.1. Minimal design

~~~mermaid
flowchart LR
    PARTNER["Authenticated uploader"] --> IN["GCS input\nincoming/"]
    IN --> EVT["Eventarc finalized"]
    EVT --> FN["Java Cloud Run function"]
    FN --> OUT["GCS output\nsummaries/"]
    OUT --> JOB["Downstream job/indexer"]
    ERR["DLQ + alert"] -. "Persistent failures" .-> EVT
~~~

Key rules:

- Each source file carries an **immutable ID**, avoiding overwrites if every version must be processed.
- Event IDs and object generations are tracked to detect duplicates/delivery delays.
- The function **is not responsible for retaining originals**: the input bucket and its retention policy remain the primary data source.
- Outputs are never overwritten thanks to conditional writes; consumers verify generation/source checksums for reconciliation.
- When handling large images/PDFs, switch to streaming/batch and safe content inspection instead of `readAllBytes`.

### 13.2. Four scenarios requiring decisions

| Scenario | Action |
|---|---|
| Partner re-uploads object with the same name | Generation changes; process each generation or forbid overwrites per business rule |
| Event is redelivered | Write summary create-only; if already present, ACK without duplicating |
| Cloud Storage returns 503 on read | Allow retries with backoff/DLQ per policy |
| Partner sends non-UTF-8 file | Record metric/rejection reason, do not retry forever; notify uploader via a defined workflow |

**The reliability of the demo** covers only the output summary. A complete production system needs a job registry/state tracker, dead-letter handling, slow-processing alerts, and result verification before promising an uploader that a file has finished processing. **A successful upload** only proves the object was stored, not that the entire pipeline processed it successfully.

## 14. Exercises and guided answers

### 14.1. Exercise A — Testing the event path

In an authorized lab:

1. Create two buckets in the same region as the function and trigger.
2. Deploy the Java function with separate runtime/trigger SAs.
3. Upload a three-line UTF-8 file under **incoming/**.
4. Inspect event logs and the JSON output.
5. Record **eventId, generation, line count, byte count, and SHA-256**; compare with local commands.
6. Upload a **.csv** file and a **.txt** file larger than 1 MiB; verify skip logs and absence of outputs.
7. Upload a new object with the same name and compare generations and output names.

**Passing criteria:** valid files create one summary per generation; invalid files are observably skipped; no public Cloud Run invocation or unnecessary admin roles exist.

### 14.2. Exercise B — Reasoning about retries and idempotency

Suppose Eventarc delivers the same finalized event **3 times** to 3 concurrently running instances. All three read the exact same generation. Answers to the questions:

- **How many times can the code execute?** Potentially all 3 times.
- **How many JSON output objects are created with doesNotExist()?** At most **1** for the same output identity.
- **What error do the remaining calls receive if output already exists?** The create precondition returns **412**; the code catches it and ACKs.
- **What happens if you add an email send before the conditional write?** The email could be sent **3 times**. You must design idempotency for that email/side effect.
- **What if the 3 events have different generations?** Those are 3 distinct content versions and can produce 3 summaries.

### 14.3. Exercise C — Modifying the problem

Adapt the design to process an uploaded JPEG image:

- Validate actual MIME/bytes and size limits rather than relying solely on the **.jpg** extension.
- Cap dimensions and pixel counts to defend against decompression bombs.
- Write thumbnails to a **separate output bucket**, never back to the trigger-watched input bucket.
- Include **object generation** in the idempotency key and output name.
- For large images, use streaming or a dedicated job instead of loading the entire image into memory.
- Add unit/integration tests for retries, corrupted images, oversized images, and overwritten objects.

**Guided answer:** the event type and trigger remain **object.finalized**, while the handler/libraries, validation, and output must change. Never treat Cloud Storage object metadata as proof that a file is safe.

### 14.4. Exercise D — Investigating missing reports

A file **incoming/contract.txt** was uploaded, yet no JSON output appeared. Cloud Run logs show **StorageException 403**; the Eventarc trigger is ACTIVE.

**What to check:** the Cloud Run revision's runtime SA, exact input bucket, **roles/storage.objectViewer**, generation read permissions, org policies/VPC-SC (if any), and logs. Do not add Invoker or Pub/Sub Publisher once the event has already reached the function. After fixing IAM, verify retries or upload a new test object; if retention expired, plan a safe replay from the source.

### 14.5. Quick questions

1. Does **object.finalized** fire on overwrite?
2. Does **metageneration** replace **generation** for identifying file contents?
3. How does CloudEventsFunction differ from HttpFunction?
4. Does the runtime SA need Invoker to read Cloud Storage itself?
5. Does the trigger SA need Object Viewer for Java to read files?
6. Why can reading by object name without pinning generation be wrong?
7. Why do two buckets help prevent loops?
8. Can you rely on Eventarc to guarantee exactly-once processing?
9. Why isn't a summary JSON with SHA-256 a malware-free certification?
10. Does deleting the Cloud Run service automatically delete the input/output buckets?

**Answers:** (1) Yes, a new generation. (2) No; metageneration is the metadata version. (3) CloudEventsFunction consumes CloudEvents from event providers; HttpFunction handles direct HTTP requests. (4) No, it needs Storage permissions. (5) No, the trigger SA needs permission to receive events and invoke the service. (6) A delayed event could read a newer version by mistake. (7) Output events do not land in the triggered bucket. (8) No, it is at-least-once. (9) A hash only identifies bytes. (10) No.

### 14.6. Acceptance report template

~~~text
PROJECT_ID / REGION:
INPUT_BUCKET / OUTPUT_BUCKET:
FUNCTION / READY_REVISION:
TRIGGER_NAME / TRIGGER_ACTIVE:
RUNTIME_SA / TRIGGER_SA:
IAM_REVIEW_RESULT:
SOURCE_OBJECT_NAME / GENERATION:
SOURCE_SIZE / CONTENT_TYPE:
CLOUD_EVENT_ID / TYPE:
OUTPUT_OBJECT / CONTENT:
LOCAL_SHA256_MATCH:
DUPLICATE_EVENT_RESULT:
INVALID_FILE_RESULT:
RETRY_POLICY / DLQ:
ERROR_LOGS / ALERT:
ESTIMATED_COST_SOURCES:
CLEANUP_RESULT / OPEN_ISSUES:
~~~

Record **PASS** only for actually observed results. Never put internal files, tokens, signed URLs, or private customer data into a public report.

## 15. Safe cleanup of lab resources

**Logical order:** stop the trigger first, stop the service, inventory objects, and only then consider cleaning up buckets/IAM. The delete commands below perform real mutations and **must be run only on lab resources you own**.

### 15.1. Verifying scope before deletion

~~~bash
# READ-ONLY.
gcloud config list project

gcloud eventarc triggers describe "$TRIGGER" \
  --project="$PROJECT_ID" --location="$REGION"

gcloud run services describe "$FUNCTION" \
  --project="$PROJECT_ID" --region="$REGION"

gcloud storage ls "gs://$INPUT_BUCKET/incoming/"
gcloud storage ls "gs://$OUTPUT_BUCKET/summaries/"
~~~

If any resource is being used by someone else, **do not delete it** just because its name matches an example. Check billing, retention/holds, Object Versioning, and soft delete to see which resources still incur charges after stopping workloads.

### 15.2. Deleting the lab trigger and function

~~~bash
# REAL RESOURCE DELETION — only after owner approval.
gcloud eventarc triggers delete "$TRIGGER" \
  --project="$PROJECT_ID" --location="$REGION"

gcloud run services delete "$FUNCTION" \
  --project="$PROJECT_ID" --region="$REGION"
~~~

**After deletion:** Eventarc stops delivering new events via this trigger, and Cloud Run removes the service revisions; objects, logs, IAM bindings, service accounts, and Pub/Sub resources remain according to their service lifecycle and ownership. Never delete production buckets or shared projects.

### 15.3. Cleaning up Storage and IAM only when approved

- Inventory every object, generation, and retention policy in **both lab buckets**.
- If deleting objects, delete **only the confirmed lab objects**, never running a single recursive delete on a shared bucket.
- Delete a bucket only when certain it was created exclusively for this lesson, is empty/meets retention rules, and has no consumers.
- IAM bindings and **fileproc-runtime / fileproc-trigger** can be revoked/deleted once certain no resources reference them; never delete Google service agents or shared role bindings.
- **cloud-run-source-deploy** may hold images for other functions/services; do not delete this repository by default.
- Reconcile Cloud Billing after data reporting catches up; storage, logs, and retention may continue incurring charges.

## 16. References and takeaways

- [Cloud Run: Trigger functions from Cloud Storage using Eventarc](https://docs.cloud.google.com/run/docs/tutorials/trigger-functions-storage)
- [Cloud Run: Write Cloud Run functions](https://docs.cloud.google.com/run/docs/write-functions)
- [Cloud Run: Deploy a function](https://docs.cloud.google.com/run/docs/deploy-functions)
- [Cloud Run: Java runtimes](https://docs.cloud.google.com/run/docs/runtimes/java)
- [Cloud Run: Function triggers](https://docs.cloud.google.com/run/docs/function-triggers)
- [Eventarc: Cloud Storage trigger event types](https://docs.cloud.google.com/run/docs/triggering/storage-triggers)
- [Eventarc Standard: Retry events](https://docs.cloud.google.com/eventarc/docs/retry-events)
- [Eventarc: Roles and permissions for Cloud Run targets](https://docs.cloud.google.com/eventarc/docs/roles-permissions)
- [Cloud Storage: Object Versioning](https://docs.cloud.google.com/storage/docs/object-versioning)
- [Cloud Storage Java client: BlobTargetOption.doesNotExist](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage.BlobTargetOption)
- [Cloud Run: Local functions development](https://docs.cloud.google.com/run/docs/local-dev-functions)
- [Cloud Run pricing](https://cloud.google.com/run/pricing)
- [Eventarc pricing](https://cloud.google.com/eventarc/pricing)
- [Cloud Storage pricing](https://cloud.google.com/storage/pricing)

**Core checklist:** right project/region → separate input/output → Java CloudEventsFunction and exact generation → minimal runtime SA → private deploy → trigger SA Event Receiver + Invoker → Storage service agent Pub/Sub Publisher → test upload → verify logs/summary/checksum → duplicate-safe write → retry/DLQ/monitoring → scoped cleanup.

**Connection to the CLOUD_PROVIDERS_GCP track:** this example coordinates **Cloud Run functions, Eventarc, Cloud Storage, Artifact Registry/Cloud Build, IAM, and Cloud Logging/Billing**. An event-driven model eliminates managing VMs or GKE nodes, yet reliability still hinges on **durable data, proper identities, idempotent processing, failure controls, and cost observability**.
