# Event-Driven Image Processing Project with Cloud Storage and Eventarc

## 1. Project Objectives

In this project, learners build an image-processing pipeline on Google Cloud: users upload images to Cloud Storage, Eventarc receives the object-created event, and then delivers a CloudEvent to a Java/Spring Boot service on Cloud Run. The service reads the image, generates a PNG thumbnail, and writes the result to a separate bucket without running a continuously polling server to check for new files.

This is a capstone hands-on project in the **CLOUD_PROVIDERS_GCP** module: applying projects/IAM, Cloud Storage, Cloud Run, Eventarc, Cloud Build, Artifact Registry, logging, security, automation, and cost control.

After completing this project, learners will be able to:

1. Distinguish input buckets, output buckets, trigger identities, and runtime identities.
2. Explain the `google.cloud.storage.object.v1.finalized` event and CloudEvents binary content mode.
3. Build an HTTP receiver with Spring Boot using the Google Cloud Storage Java client.
4. Generate bounded-size thumbnails and store the result only once per object generation.
5. Configure least-privilege IAM for the Cloud Storage service agent, Eventarc trigger, and Cloud Run runtime.
6. Deploy the service, create the trigger, upload images, and verify results via logs and buckets.
7. Handle duplicate deliveries, transient errors, invalid data, and overwritten objects.
8. Design monitoring, testing, cleanup, and extensions for real-world needs.

**Exercise boundaries:** uses **Eventarc Standard** with direct Cloud Storage events, a Cloud Run **service**, Java 21, and Spring Boot. Does not use polling, Cloud Scheduler, or a custom Pub/Sub subscription for the primary flow.

## 2. Business Requirements and Acceptance Criteria

The sample application is named `image-worker`, accepting images from a source bucket and outputting PNG thumbnails with a maximum long edge of 320 pixels to a destination bucket.

| Requirement | Verification Criterion |
|---|---|
| Upload JPEG/PNG image | Generates finalized event and Cloud Run receives it |
| Source restriction | Processes only objects whose name starts with `uploads/` |
| Size limit | Does not process files exceeding 10 MiB |
| Pixel limit | Does not decode images whose dimensions exceed the configured safe limit |
| Preserve aspect ratio | Long edge at most 320 pixels; do not upscale smaller images |
| Output | PNG in output bucket, named deterministically by object and generation |
| Duplicate delivery | Does not create multiple objects or overwrite output with the same key |
| Non-image file | Skipped with logging, avoiding infinite retries |
| Transient Cloud Storage error | Fails with HTTP error so infrastructure can attempt redelivery |
| Security | Do not expose the Cloud Run service to anonymous invokers |

Size and format requirements are choices for this exercise. In production, account for large images, HEIC/WebP, compression quality, EXIF orientation, protection against malicious images, and malware scanning pipelines.

### 2.1. Architecture

~~~mermaid
flowchart LR
    U[Client / CLI upload] --> IN[(Cloud Storage input bucket)]
    IN -->|object finalized| EV[Eventarc Standard trigger]
    EV -->|CloudEvent POST + trigger SA| RUN[Cloud Run image-worker]
    RUN -->|ADC / runtime SA| IN
    RUN -->|PNG thumbnail + create-only| OUT[(Cloud Storage output bucket)]
    RUN -.-> LOG[Cloud Logging / Monitoring]
    EV -.-> OBS[Event delivery metrics]
~~~

An input object traverses a single processing path. We intentionally use **two separate buckets**: output uploads do not trigger additional events on the input trigger, preventing infinite processing loops.

### 2.2. Components and Identities

| Component | Role | Identity |
|---|---|---|
| Cloud Storage input | Receives original files | Uploading user/app with write permission |
| Cloud Storage service agent | Emits notifications for direct events | Google-managed service agent |
| Eventarc trigger | Filters and delivers events | User-managed trigger service account |
| Cloud Run image-worker | HTTP receiver and image processor | User-managed runtime service account |
| Cloud Storage output | Stores thumbnails | Runtime SA with object creation permission |
| Cloud Build/Artifact Registry | Builds and stores image during source deploy | Dedicated build identity per configuration |

Never grant Owner/Editor to the runtime just to access two buckets. Each identity needs permissions scoped only to the job it performs.

## 3. Understanding the Event Mechanism Before Writing Code

### 3.1. What Does Finalized Mean?

The `google.cloud.storage.object.v1.finalized` event fires when a new object is successfully created in a bucket or when an overwrite creates a **new generation**. It is not fired when an upload starts; Cloud Storage only publishes the object after upload completion.

Other events such as `deleted`, `archived`, and `metadataUpdated` have different semantics. In this project, we only use `finalized` to process newly uploaded content, avoiding re-runs when metadata changes.

**Cloud Storage object generation** identifies a specific version of object content. If `uploads/cat.jpg` is overwritten, the new generation is a valid new input; uploads with the same name must not be collapsed into a single job.

### 3.2. How Does Eventarc Deliver CloudEvents?

Eventarc Standard sends HTTP requests to Cloud Run in **CloudEvents binary content mode**:

- Metadata resides in HTTP headers such as `ce-id`, `ce-source`, `ce-type`, and `ce-subject`.
- `Content-Type` describes the event data payload type, here `application/json`.
- The **HTTP body** contains the event `data` payload, rather than always being a JSON wrapper object containing `id/source/type/data`.

Simplified example:

~~~http
POST / HTTP/1.1
Content-Type: application/json
ce-specversion: 1.0
ce-type: google.cloud.storage.object.v1.finalized
ce-id: 1234567890
ce-source: //storage.googleapis.com/projects/_/buckets/example-input
ce-subject: objects/uploads/cat.jpg

{
  "bucket": "example-input",
  "name": "uploads/cat.jpg",
  "generation": "1700000000000000",
  "contentType": "image/jpeg",
  "size": "284391"
}
~~~

In binary mode, a Spring controller can bind headers and body separately. If you use a CloudEvents SDK, the library can reconstruct a CloudEvent object; this lesson's example does not need that extra SDK.

### 3.3. Events Can Arrive Multiple Times and Out of Order

Eventarc Standard provides **at-least-once delivery**. When delivery fails, the system may retry; some events may be delivered more than once. Never rely on ordering of `finalized` events across different generations.

Chosen processing key:

~~~text
source bucket + object name + object generation
~~~

CloudEvents (`ce-source`, `ce-id`) can also be used for event deduplication, but tying output to the **input data version's identity** ensures consistent output even if two distinct events refer to the same object generation.

## 4. Architectural Decisions to Prevent Loops and Overwrites

### 4.1. Two Independent Buckets

Example:

~~~text
gs://PROJECT-images-in-UNIQUE/
  uploads/cat.jpg
  uploads/dog.png

gs://PROJECT-images-out-UNIQUE/
  thumbnails/34be...c01a.png
  thumbnails/0f86...e92d.png
~~~

The output name is the SHA-256 hex digest of `bucket + newline + name + newline + generation`. This avoids using user-supplied filenames directly as destination names, reduces collisions, and avoids exposing original filenames in output paths.

### 4.2. Conditional Output Writes

When uploading thumbnails, use a **generation precondition** via `Storage.BlobTargetOption.doesNotExist()`. Only the first request can create the output object; any subsequent request targeting the same output name receives HTTP 412 from Storage and is treated as **already processed**.

Note: this precondition protects **against overwriting the object**, not against duplicate CPU work. If multiple workers process the event concurrently, both may still decode and resize the image. At larger scale, add a job-state/lease table or appropriate cache.

### 4.3. Reading the Exact Generation

An input object may be overwritten while an event is queued for delivery. Therefore, the worker reads:

~~~java
BlobId.of(bucket, name, generation)
~~~

rather than blindly fetching the latest version. If the older generation is no longer available because Object Versioning/retention is disabled on the bucket and it was overwritten, the worker cannot reconstruct the old data. This exercise logs the condition and acknowledges the event to avoid infinite retries; production systems should record a diagnostic entry or route to an exception queue.

## 5. Preparing the Project and Tools

### 5.1. Prerequisites

- A Google Cloud project with billing enabled and sufficient quotas.
- `gcloud`, `gcloud storage`, and permissions to create buckets, service accounts, Cloud Run services, and Eventarc triggers.
- Java 21 and Maven on a dev machine, or Cloud Shell/Cloud Build for building.
- Controlled IAM permissions; in organizational setups, obtain platform/security approval.
- A small authorized JPEG or PNG image containing no sensitive data.

The Bash examples below target **Google Cloud Shell**. Do not run them verbatim in PowerShell or use placeholders in a production environment. Bucket names must be **globally unique**.

### 5.2. Declaring Environment Variables

~~~bash
export PROJECT_ID="YOUR_PROJECT_ID"
export REGION="asia-southeast1"
export SUFFIX="YOUR_UNIQUE_SUFFIX"

export INPUT_BUCKET="${PROJECT_ID}-images-in-${SUFFIX}"
export OUTPUT_BUCKET="${PROJECT_ID}-images-out-${SUFFIX}"

export RUN_SERVICE="image-worker"
export TRIGGER_NAME="images-finalized"
export RUN_SA="image-worker-sa@${PROJECT_ID}.iam.gserviceaccount.com"
export TRIGGER_SA="eventarc-delivery-sa@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud config set project "$PROJECT_ID"
gcloud config get-value project
~~~

Selecting `asia-southeast1` is only an example deployment region. In this lesson, the **input bucket and trigger must share a compatible location**; Cloud Run is placed in the same region for operational simplicity and lower latency.

### 5.3. Enabling APIs

~~~bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  eventarc.googleapis.com \
  pubsub.googleapis.com \
  storage.googleapis.com \
  iam.googleapis.com \
  --project="$PROJECT_ID"
~~~

The executing account needs permission to enable APIs and create resources. Developer/builder permissions are **not the same** as the runtime service account; never grant all deploy permissions to the runtime just because Cloud Build needs to build images.

## 6. Creating Input and Output Buckets

~~~bash
gcloud storage buckets create "gs://$INPUT_BUCKET" \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --uniform-bucket-level-access

gcloud storage buckets create "gs://$OUTPUT_BUCKET" \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --uniform-bucket-level-access
~~~

Use uniform bucket-level access for clear bucket-level IAM management. Depending on your organization, you may also need policies for public access prevention, retention, soft delete, and CMEK.

Verify:

~~~bash
gcloud storage buckets describe "gs://$INPUT_BUCKET"
gcloud storage buckets describe "gs://$OUTPUT_BUCKET"
~~~

**Do not make the output bucket the same as the input bucket** in this exercise. If a single bucket must be used, carefully design object prefix filters and loop-prevention logic; the default Eventarc direct trigger in this example filters by **bucket + type**, not automatically by the `uploads/` prefix.

## 7. Service Accounts and Least-Privilege IAM

### 7.1. Creating Two User-Managed Service Accounts

~~~bash
gcloud iam service-accounts create image-worker-sa \
  --project="$PROJECT_ID" \
  --display-name="Image processing runtime"

gcloud iam service-accounts create eventarc-delivery-sa \
  --project="$PROJECT_ID" \
  --display-name="Eventarc Cloud Run delivery"
~~~

The two service accounts have distinct responsibilities:

- **RUN_SA:** identity the Java service uses via ADC to read inputs and create outputs.
- **TRIGGER_SA:** identity Eventarc uses to receive events and invoke the protected Cloud Run endpoint.

### 7.2. Cloud Storage Permissions for Runtime

~~~bash
gcloud storage buckets add-iam-policy-binding "gs://$INPUT_BUCKET" \
  --member="serviceAccount:$RUN_SA" \
  --role="roles/storage.objectViewer"

gcloud storage buckets add-iam-policy-binding "gs://$OUTPUT_BUCKET" \
  --member="serviceAccount:$RUN_SA" \
  --role="roles/storage.objectCreator"
~~~

`objectViewer` grants read access to accessible source generations. `objectCreator` suffices for create-only thumbnails without granting permission to delete or overwrite outputs under existing names. Application code handles existing outputs via preconditions.

If reading output metadata, lifecycle management, or file deletion is needed later, evaluate a dedicated role rather than casually escalating to Storage Admin.

### 7.3. Permissions for the Eventarc Trigger

~~~bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$TRIGGER_SA" \
  --role="roles/eventarc.eventReceiver"
~~~

After deploying the Cloud Run service, grant `roles/run.invoker` to `TRIGGER_SA` **on that specific service**. Never grant Invoker broadly at the project level when only one receiver needs to be called.

### 7.4. Cloud Storage Service Agent Must Be Permitted to Publish Events

~~~bash
STORAGE_SERVICE_AGENT="$(gcloud storage service-agent \
  --project="$PROJECT_ID")"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$STORAGE_SERVICE_AGENT" \
  --role="roles/pubsub.publisher"
~~~

This is a Google-managed service agent, distinct from `TRIGGER_SA` and `RUN_SA`. Eventarc Standard uses Pub/Sub as the transport for direct Cloud Storage events.

In very old projects, the Pub/Sub service agent may need `roles/iam.serviceAccountTokenCreator` to authenticate push deliveries. **Only grant this under the specific conditions documented in current guidance**, never blindly on every project.

## 8. Java/Spring Boot Project Structure

A minimal Maven application:

~~~text
image-worker/
  pom.xml
  src/
    main/
      java/com/example/images/
        ImageEventsApplication.java
        StorageObjectData.java
        GcsImageProcessor.java
        ImageEventsController.java
    test/
      java/com/example/images/
        ImageEventsControllerTest.java
~~~

We use Java 21, Spring MVC, and the Google Cloud Storage Java library. The versions below are **pinned dependency examples for reproducing the lesson**; review security updates and compatibility before using in production.

### 8.1. Maven `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>image-worker</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties>
    <java.version>21</java.version>
  </properties>

  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>libraries-bom</artifactId>
        <version>26.93.0</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
    </dependencies>
  </dependencyManagement>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>com.google.cloud</groupId>
      <artifactId>google-cloud-storage</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

The Spring Boot starter manages the HTTP server, Jackson JSON, and logging. `libraries-bom` aligns compatible Google Cloud dependencies. The project does not need to store access tokens or service account keys manually.

### 8.2. Spring Boot Bootstrap and Storage Bean

~~~java
package com.example.images;

import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ImageEventsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ImageEventsApplication.class, args);
    }

    @Bean
    Storage storage() {
        return StorageOptions.getDefaultInstance().getService();
    }
}
~~~

Cloud Run supplies `PORT` and the runtime service account. Spring Boot listens on port 8080 by default; if configuring another port, ensure the app binds `0.0.0.0` and honors the port supplied by Cloud Run.

## 9. Cloud Storage Event Data Model

The finalized event body contains more fields than this project needs. We declare only the fields used directly; Jackson ignores unknown properties.

~~~java
package com.example.images;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record StorageObjectData(
    String bucket,
    String name,
    String generation,
    String contentType,
    String size
) {}
~~~

`generation` and `size` are strings in standard payloads and must be parsed defensively. Never trust `contentType` as proof that the bytes are a safe image; it is merely uploader-supplied metadata.

## 10. GcsImageProcessor: Reading Generation, Resizing, and Writing Output

In this hands-on version, we cap input size at 10 MiB and pixel count at 20 million. Inspecting headers via an ImageIO `ImageReader` before full decoding helps mitigate some memory exhaustion risks, though it **does not replace** sandboxing and deep inspection for untrusted inputs.

### 10.1. Processor Code

~~~java
package com.example.images;

import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import javax.imageio.ImageIO;
import javax.imageio.ImageReader;
import javax.imageio.stream.ImageInputStream;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Iterator;

@Service
public final class GcsImageProcessor {
    private static final long MAX_BYTES = 10L * 1024 * 1024;
    private static final long MAX_PIXELS = 20_000_000L;
    private static final int MAX_EDGE = 320;

    private final Storage storage;
    private final String inputBucket;
    private final String outputBucket;

    public enum Outcome {
        CREATED, ALREADY_EXISTS, SKIPPED, SOURCE_MISSING
    }

    public GcsImageProcessor(
        Storage storage,
        @Value("${INPUT_BUCKET}") String inputBucket,
        @Value("${OUTPUT_BUCKET}") String outputBucket
    ) {
        this.storage = storage;
        this.inputBucket = inputBucket;
        this.outputBucket = outputBucket;
    }

    public Outcome process(StorageObjectData event) throws IOException {
        if (event == null || event.bucket() == null ||
            !inputBucket.equals(event.bucket()) ||
            event.name() == null ||
            !event.name().startsWith("uploads/") ||
            event.name().length() > 1024) {
            return Outcome.SKIPPED;
        }

        long generation;
        long declaredSize;
        try {
            generation = Long.parseLong(event.generation());
            declaredSize = Long.parseLong(event.size());
        } catch (RuntimeException invalidMetadata) {
            return Outcome.SKIPPED;
        }

        if (generation <= 0 || declaredSize <= 0 ||
            declaredSize > MAX_BYTES) {
            return Outcome.SKIPPED;
        }

        byte[] bytes;
        try {
            bytes = storage.readAllBytes(
                BlobId.of(event.bucket(), event.name(), generation)
            );
        } catch (StorageException e) {
            if (e.getCode() == 404) {
                return Outcome.SOURCE_MISSING;
            }
            throw e;
        }

        if (bytes.length == 0 || bytes.length > MAX_BYTES) {
            return Outcome.SKIPPED;
        }

        BufferedImage original = decodeImage(bytes);
        if (original == null) {
            return Outcome.SKIPPED;
        }

        double factor = Math.min(
            1.0,
            Math.min(
                (double) MAX_EDGE / original.getWidth(),
                (double) MAX_EDGE / original.getHeight()
            )
        );
        int width = Math.max(1,
            (int) Math.round(original.getWidth() * factor));
        int height = Math.max(1,
            (int) Math.round(original.getHeight() * factor));

        BufferedImage thumb = new BufferedImage(
            width, height, BufferedImage.TYPE_INT_ARGB
        );
        Graphics2D graphics = thumb.createGraphics();
        try {
            graphics.setRenderingHint(
                RenderingHints.KEY_INTERPOLATION,
                RenderingHints.VALUE_INTERPOLATION_BILINEAR
            );
            graphics.drawImage(original, 0, 0, width, height, null);
        } finally {
            graphics.dispose();
        }

        ByteArrayOutputStream output = new ByteArrayOutputStream();
        if (!ImageIO.write(thumb, "png", output)) {
            throw new IOException("PNG encoder unavailable");
        }

        String fingerprint = sha256(
            event.bucket() + "\n" + event.name() + "\n" +
            generation
        );
        String outputName = "thumbnails/" + fingerprint + ".png";
        BlobInfo info = BlobInfo.newBuilder(
                BlobId.of(outputBucket, outputName)
            )
            .setContentType("image/png")
            .build();

        try {
            storage.create(
                info,
                output.toByteArray(),
                Storage.BlobTargetOption.doesNotExist()
            );
            return Outcome.CREATED;
        } catch (StorageException e) {
            if (e.getCode() == 412) {
                return Outcome.ALREADY_EXISTS;
            }
            throw e;
        }
    }

    private static BufferedImage decodeImage(byte[] bytes)
            throws IOException {
        try (ImageInputStream stream =
                 ImageIO.createImageInputStream(
                     new ByteArrayInputStream(bytes)
                 )) {
            if (stream == null) {
                return null;
            }
            Iterator<ImageReader> readers =
                ImageIO.getImageReaders(stream);
            if (!readers.hasNext()) {
                return null;
            }

            ImageReader reader = readers.next();
            try {
                reader.setInput(stream, true, true);
                int width = reader.getWidth(0);
                int height = reader.getHeight(0);
                if (width <= 0 || height <= 0 ||
                    ((long) width * height) > MAX_PIXELS) {
                    return null;
                }
                try {
                    return reader.read(0);
                } catch (IOException corruptImage) {
                    return null;
                }
            } finally {
                reader.dispose();
            }
        }
    }

    private static String sha256(String input) {
        try {
            byte[] value = MessageDigest.getInstance("SHA-256")
                .digest(input.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(value);
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
    }
}
~~~

### 10.2. Analysis of Key Decisions

- `storage.readAllBytes(BlobId.of(bucket, name, generation))` reads the **exact generation**, avoiding mistakenly reading newer content when an object is overwritten.
- `MAX_BYTES` bounds the byte payload held in memory.
- `MAX_PIXELS` bounds image dimensions prior to decoding. For large source images or complex formats, use a streaming pipeline and a hardened image library.
- `MAX_EDGE` avoids upscaling smaller images; output preserves aspect ratio.
- `sha256` derives a deterministic output key from source identity without embedding raw user filenames in paths.
- `doesNotExist()` enforces create-only output semantics, making retries safe.
- HTTP 412 on output write is treated as already completed, **not a 500 error requiring retry**.
- A missing source generation returns `SOURCE_MISSING`; monitor this and optionally add out-of-band exception handling.

The code intentionally omits EXIF orientation, animation, ICC color profiles, and HEIC/WebP. This level fits the lab, not a production image transcoding service.

## 11. ImageEventsController: Receiving CloudEvents over HTTP

Eventarc sends HTTP POST requests to the root path `/` per this lesson's trigger configuration. The controller reads `ce-*` headers and the JSON body.

~~~java
package com.example.images;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public final class ImageEventsController {
    private static final Logger log =
        LoggerFactory.getLogger(ImageEventsController.class);

    private static final String FINALIZED =
        "google.cloud.storage.object.v1.finalized";

    private final GcsImageProcessor processor;
    private final String expectedBucket;

    public ImageEventsController(
        GcsImageProcessor processor,
        @Value("${INPUT_BUCKET}") String expectedBucket
    ) {
        this.processor = processor;
        this.expectedBucket = expectedBucket;
    }

    @PostMapping(path = "/", consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Void> receive(
        @RequestHeader(value = "ce-id", required = false)
            String eventId,
        @RequestHeader(value = "ce-type", required = false)
            String eventType,
        @RequestHeader(value = "ce-source", required = false)
            String source,
        @RequestBody StorageObjectData data
    ) throws Exception {
        String expectedSource =
            "//storage.googleapis.com/projects/_/buckets/" +
            expectedBucket;

        if (!FINALIZED.equals(eventType) ||
            !expectedSource.equals(source) ||
            data == null ||
            !expectedBucket.equals(data.bucket())) {
            log.warn("Skipping unexpected CloudEvent id={}", eventId);
            return ResponseEntity.noContent().build();
        }

        GcsImageProcessor.Outcome result = processor.process(data);
        log.info("Image event id={} result={}", eventId, result);

        return ResponseEntity.noContent().build();
    }
}
~~~

**The HTTP status code is a critical design decision:**

- Return 2xx when processing succeeds or when deliberately skipping an event that retries cannot fix, such as a non-image file.
- Do not swallow every exception and return 2xx, as that discards retry opportunities during transient Cloud Storage failures.
- Unhandled exceptions surface as 5xx via Spring/Cloud Run, allowing Eventarc/Pub/Sub to redeliver according to its retry policy.
- If a malformed payload fails JSON binding, Spring may return 400; configure dead-letter/quarantine handling and retry limits so poison messages are not retried forever.
- For `SOURCE_MISSING`, the example logs and returns 204. Production should record a dedicated exception/audit entry so lost object generations are never silently forgotten.

Cloud Run IAM and the trigger service account protect the receiver from anonymous invocation. Header `ce-id` by itself is **not a security boundary** if the endpoint is open to anyone; never disable IAM merely because the controller checks `ce-source`.

## 12. Testing the Application Locally

### 12.1. Unit Tests Before Deploying

You can test the controller without Cloud Storage or Google Cloud credentials using Mockito. Example:

~~~java
package com.example.images;

import org.junit.jupiter.api.Test;
import static org.mockito.Mockito.*;

class ImageEventsControllerTest {

    @Test
    void ignoresUnexpectedEventType() throws Exception {
        GcsImageProcessor processor = mock(GcsImageProcessor.class);
        ImageEventsController controller =
            new ImageEventsController(processor, "images-in");

        StorageObjectData payload = new StorageObjectData(
            "images-in", "uploads/a.jpg", "123", "image/jpeg", "1024"
        );

        controller.receive(
            "evt-1",
            "google.cloud.storage.object.v1.metadataUpdated",
            "//storage.googleapis.com/projects/_/buckets/images-in",
            payload
        );

        verifyNoInteractions(processor);
    }

    @Test
    void forwardsFinalizedEvent() throws Exception {
        GcsImageProcessor processor = mock(GcsImageProcessor.class);
        ImageEventsController controller =
            new ImageEventsController(processor, "images-in");

        StorageObjectData payload = new StorageObjectData(
            "images-in", "uploads/a.jpg", "123", "image/jpeg", "1024"
        );

        controller.receive(
            "evt-2",
            "google.cloud.storage.object.v1.finalized",
            "//storage.googleapis.com/projects/_/buckets/images-in",
            payload
        );

        verify(processor).process(payload);
    }
}
~~~

Add unit tests for `GcsImageProcessor` using a fake/mock `Storage` to cover 404, 412, 5xx, oversized inputs, spoofed images, and output keys. You do not need real image files in every unit test; you can construct a small `BufferedImage` and encode it as JPEG/PNG in memory.

### 12.2. Boundary and Security Test Cases

Key scenarios:

| Scenario | Expected Result |
|---|---|
| Different source bucket | Skipped, object not read |
| Object outside `uploads/` | Skipped |
| Invalid metadata size | Skipped and logged appropriately |
| Text file disguised with `.jpg` extension | No thumbnail created |
| Image exceeding `MAX_PIXELS` | Skipped |
| Redelivery of the same event | Output name unchanged, no overwrite |
| Overwritten source | Exact generation processed or missing generation logged |
| Storage 503 | Returns transient error for retry |
| Missing Cloud Run invoke token | Rejected by platform |
| Runtime loses source read permission | Permission denied observable in logs |

Idempotency tests should not stop at `verify(processor).process()`; also verify through integration tests that the output precondition genuinely prevents overwrites.

## 13. Building and Deploying Cloud Run from Source

After creating the Java/Maven files above and running tests:

~~~bash
mvn -B test
mvn -B package
~~~

These commands are **instructions for the learner**, not steps already executed in STEP 4.

From the directory containing `pom.xml`, deploy:

~~~bash
gcloud run deploy "$RUN_SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --source=. \
  --service-account="$RUN_SA" \
  --no-allow-unauthenticated \
  --set-env-vars="INPUT_BUCKET=$INPUT_BUCKET,OUTPUT_BUCKET=$OUTPUT_BUCKET" \
  --memory=512Mi \
  --concurrency=2 \
  --timeout=120
~~~

Cloud Run source deploy uses a build workflow to produce an image and may require an Artifact Registry repository or Cloud Build permissions. The deployer needs deploy permissions and `iam.serviceAccounts.actAs` on `RUN_SA`; do not grant build permissions to the runtime by default.

Because images are decoded in memory, capping concurrency prevents multiple large images from exhausting memory simultaneously. `512Mi` is a lab setting; measure actual memory/CPU and tune for real workloads.

Verify:

~~~bash
gcloud run services describe "$RUN_SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="value(status.url)"
~~~

Never open the Cloud Run service with `--allow-unauthenticated` just to work around trigger IAM errors.

## 14. Granting Invoker and Creating the Eventarc Trigger

### 14.1. Granting Invoke Permission to the Trigger Service Account

~~~bash
gcloud run services add-iam-policy-binding "$RUN_SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --member="serviceAccount:$TRIGGER_SA" \
  --role="roles/run.invoker"
~~~

Do not grant `roles/run.invoker` to `allUsers`. The trigger service account holds Eventarc receiver permission at the project level and invoke permission solely on this service.

### 14.2. Creating a Trigger on the Finalized Event

~~~bash
gcloud eventarc triggers create "$TRIGGER_NAME" \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --destination-run-service="$RUN_SERVICE" \
  --destination-run-region="$REGION" \
  --destination-run-path="/" \
  --event-filters="type=google.cloud.storage.object.v1.finalized" \
  --event-filters="bucket=$INPUT_BUCKET" \
  --service-account="$TRIGGER_SA"
~~~

Points to confirm:

- Direct Cloud Storage triggers reside in the same project and a location compatible with the source bucket.
- The Cloud Run target can be in another region subject to product limits, though placing it in the same region simplifies the lab.
- The trigger filters on **type** and **bucket**, not prefixes; application code enforces `uploads/`.
- The Cloud Storage service agent must hold `roles/pubsub.publisher`.
- The trigger requires `roles/eventarc.eventReceiver`; authenticated Cloud Run requires `roles/run.invoker` for the trigger SA.
- Eventarc service agent/IAM bindings can take time to propagate.
- Newly created triggers may take a couple of minutes before delivering events.

If the bucket location is multi-region or dual-region, the trigger location and Pub/Sub message storage policy must follow the corresponding rules; do not pick a region at random.

### 14.3. Inspecting the Trigger

~~~bash
gcloud eventarc triggers list \
  --project="$PROJECT_ID" \
  --location="$REGION"

gcloud eventarc triggers describe "$TRIGGER_NAME" \
  --project="$PROJECT_ID" \
  --location="$REGION"
~~~

Verify event type, bucket filter, destination service, trigger SA, and healthy/active status before uploading test data.

## 15. End-to-End Run: Uploading an Image and Receiving a Thumbnail

### 15.1. Preparing an Image

Use a small authorized JPEG/PNG image. In Google Cloud Shell, assuming `sample.jpg` is in the current directory:

~~~bash
gcloud storage cp ./sample.jpg \
  "gs://$INPUT_BUCKET/uploads/sample.jpg"
~~~

A successful upload creates a new object generation and emits a finalized event. Eventarc routes the event to Cloud Run; the service reads the source and writes the thumbnail.

### 15.2. Viewing Logs

~~~bash
gcloud run services logs read "$RUN_SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --limit=50
~~~

Look for `Image event id=... result=CREATED` or `ALREADY_EXISTS`. If logs only show `SKIPPED`, check prefix, metadata size, format, or oversized files.

Check output:

~~~bash
gcloud storage ls "gs://$OUTPUT_BUCKET/thumbnails/"
~~~

Thumbnails use hashed names rather than original filenames. You can download an output object to inspect it using the exact object name returned by the `ls` command.

### 15.3. Testing Idempotency

Re-send the same CloudEvent to an **authenticated test environment** or use an integration test simulating duplicate calls. The output name stays identical, and the second write must be rejected with precondition 412, handled in code as `ALREADY_EXISTS`.

If you overwrite `uploads/sample.jpg` with another image, Cloud Storage creates a **new generation**, and the worker creates a new output key. Do not confuse two distinct generations with a retry of the same event.

### 15.4. Testing Invalid File Skipping

~~~bash
printf 'not an image' > fake.jpg
gcloud storage cp ./fake.jpg \
  "gs://$INPUT_BUCKET/uploads/fake.jpg"
~~~

The worker skips it because `ImageIO` finds no suitable image reader. There is no point forcing repeated retries on data already known not to be an image. You can extend this to record a quarantine status and notify the uploader.

## 16. Error Handling and Eventarc Retries

### 16.1. Triage Matrix

| Symptom | Likely Cause | How to Check |
|---|---|---|
| No Cloud Run request | Trigger not yet active, wrong bucket/location, service agent IAM | Eventarc trigger status and filters |
| Eventarc reports 403 on invoke | Trigger SA missing `roles/run.invoker` | Cloud Run IAM policy |
| Event receiver gets 400 | JSON failed to bind or wrong Content-Type/path | Controller logs, CloudEvents mode |
| Worker gets 403 from Storage | `RUN_SA` lacks permissions on input/output bucket | Bucket IAM and ADC identity |
| Worker gets 404 from Storage | Generation was deleted or overwritten | Object Versioning, name/generation, and logs |
| Output write returns 412 | Thumbnail already exists | Expected idempotent behavior |
| Worker 500/503 | Transient Storage error, decode exception, out of memory | Cloud Run logs, memory/timeout |
| Repeated processing | At-least-once / redelivery | Output key, retries, dead-letter controls |
| No output image appears | Object not under `uploads/` or skipped | Event body, size, ImageIO format |
| Errors right after IAM changes | Policy not yet propagated or wrong principal | IAM bindings and audit logs |

### 16.2. 2xx vs. Non-2xx Responses

In a retry-capable delivery system, **return 2xx only after side effects reach a safe state** or an intentional controlled skip occurs. If Cloud Storage transiently returns 503, let the request fail so Eventarc/Pub/Sub can redeliver.

Conversely, for permanently invalid data, retrying will not turn it into a valid image. Return 2xx after recording to logs/quarantine so poison messages do not waste resources in a loop.

For long-term failure handling, configure retry/backoff and dead-letter policies on the Pub/Sub subscription backing Eventarc Standard per governance capabilities; never assume all events are retained indefinitely or guaranteed to be redelivered forever.

### 16.3. Duplicates, Out-of-Order Events, and Object Overwrites

Three rules keep the pipeline safe:

1. Read the exact source **generation**.
2. Derive the output key from source identity.
3. Write output using `doesNotExist()`.

If a source generation disappears because an object was overwritten with versioning disabled, the code cannot recover the older version. To preserve history across same-name uploads, evaluate Cloud Storage Object Versioning alongside sensible lifecycle/retention policies; versioning adds storage cost and does not replace soft delete for accidental deletion protection.

### 16.4. Preventing Event Loops

Never write output into the input bucket if the trigger watches the entire bucket without path separation. In this lesson, the output bucket differs from the input bucket, so thumbnails never emit new events watched by the trigger.

If expanding into a multi-stage pipeline (thumbnails, OCR, classification), use separate buckets or event type/metadata contracts along with a state machine tracking each step so outputs never re-trigger themselves.

## 17. Security and Least Privilege

### 17.1. Identities and Permissions

| Identity | Permission | Resource |
|---|---|---|
| Uploader | `roles/storage.objectCreator` | Input bucket, if create-only |
| Cloud Storage service agent | `roles/pubsub.publisher` | Project per direct-event guidance |
| Trigger SA | `roles/eventarc.eventReceiver` | Event receiver project/fleet scope |
| Trigger SA | `roles/run.invoker` | Only the `image-worker` Cloud Run service |
| Runtime SA | `roles/storage.objectViewer` | Input bucket |
| Runtime SA | `roles/storage.objectCreator` | Output bucket |
| Developer/deployer | Deploy permissions and `actAs` | Only required service accounts/resources |

Never share a single all-powerful service account. Bucket IAM governs object access while Cloud Run Invoker protects the endpoint. Never commit JSON keys into images or repositories.

### 17.2. Data Validation and Image Hardening

User-uploaded images are **untrusted input**. Measures to consider:

- Cap upload size and post-decode dimensions.
- Use only maintained decoders with up-to-date security patches.
- Inspect MIME type and actual byte content rather than trusting file extensions.
- Avoid invoking ImageMagick or external tools over untrusted inputs via uncontrolled shell commands.
- Consider malware scanning, CPU/memory/time limits, and sandboxing.
- Inspect EXIF and GPS metadata for privacy, stripping metadata from thumbnails where appropriate.
- Never log personal bucket data or sensitive object names into public logs.
- For very large images, consider Cloud Run jobs/Workflows or an isolated processing pipeline.

The example uses Java ImageIO and small images; production requires dedicated evaluation of decoder vulnerabilities, decompression bombs, animated formats, color profiles, and third-party libraries.

### 17.3. Bucket Access and Retention

Enable public access prevention and UBLA per organizational standards. To protect original images from accidental overwrite or deletion, evaluate soft delete, versioning, and retention while weighing cost. Never configure lifecycle rules to delete originals before confirming events have been processed.

## 18. Monitoring, SLOs, and Cost Control

### 18.1. Metrics

| Metric | Meaning |
|---|---|
| Event delivery failures | Eventarc failed to deliver events |
| Cloud Run 4xx/5xx | Payload/IAM/runtime errors |
| Cloud Run p95 latency | Rising processing duration |
| Container memory usage | Oversized images or high concurrency |
| `CREATED` count | Thumbnails created successfully |
| `SKIPPED` count | Ineligible inputs |
| `SOURCE_MISSING` count | Generation no longer available for processing |
| `ALREADY_EXISTS` count | Retries / duplicate deliveries |
| Age from event time to output creation | End-to-end processing lag |
| Cost per processed image | Storage + event + compute cost |

Example lab SLO: **99% of valid images under 10 MiB produce a thumbnail within 3 minutes**. This is an illustrative target; measure against logs and output metadata to verify compliance.

### 18.2. Cost-Generating Components

- Cloud Storage input/output capacity, operations, and potential egress.
- Eventarc Standard / Pub/Sub transport and delivery.
- Cloud Run requests, CPU, memory, concurrency, and processing duration.
- Cloud Build/Artifact Registry during source deployments.
- Cloud Logging/Monitoring, log retention, and alerting.
- Storage Versioning/soft delete if enabled on input/output buckets.

For moderately large images, loading entire files into memory can raise CPU and memory costs. Start with tight limits, measure images/second, and revisit thumbnail dimensions, throughput, and streaming support.

## 19. CI/CD and Infrastructure as Code

A production pipeline should separate:

1. Pull request: compile, unit tests, static analysis, dependency scan.
2. Main branch: build the image once and push to Artifact Registry.
3. Staging: deploy Cloud Run with the staging runtime SA.
4. Integration test: upload an image into a sandbox input bucket and verify the output thumbnail.
5. Approval: promote the exact same image digest to production.
6. IaC: manage buckets, IAM bindings, Cloud Run config, Eventarc triggers, and alerts.
7. Post-deploy: monitor trigger health, error rate, and rollback readiness.

Avoid configuring all production IAM manually outside Git and protected Terraform state. With Eventarc, manage resource dependency ordering: service/SA and Invoker permissions first, trigger second. Remember that IAM propagation delays can prevent a brand-new trigger from delivering events immediately.

When using Terraform, modularize input/output storage, Eventarc triggers, Cloud Run services, and IAM separately. Never place static secrets/tokens into state or public `.tfvars` files.

## 20. Extending the Project by Tier

### Tier 1 — Basic Thumbnail

- Single 320 px size, PNG output.
- Java/Spring HTTP CloudEvents receiver.
- Least-privilege IAM, duplicate-safe output.
- Tests for upload, skip, and retry.

### Tier 2 — Multiple Sizes and Metadata

- Generate 160/320/640 px thumbnails.
- Store metadata including source generation, target generation, and checksum in Firestore.
- Track `PENDING / COMPLETE / FAILED` states with a retry budget.
- Use an idempotency key in a Firestore transaction to avoid duplicate CPU work.

### Tier 3 — Controlled Pipeline

- Scan images and enforce content policy before publishing.
- Use Workflows or Cloud Tasks for bounded retries and quarantine.
- Support HEIC/WebP images or video thumbnails via specialized containers.
- Track SLOs, quotas, cost, and support reprocessing.
- Consider GKE or Cloud Run jobs for long-running batch workloads needing dedicated resources.

### Tier 4 — Multi-Region and Data Protection

- Align bucket locations and Eventarc regionality with enterprise architecture.
- Enforce CMEK, VPC Service Controls, and organization-level IAM.
- Build recovery procedures for Eventarc/Pub/Sub disruptions.
- Apply lifecycle policies and replication for critical data.
- Rehearse disaster recovery and full thumbnail rebuild procedures.

## 21. Post-Lab Cleanup

Run cleanup only after confirming no data needs to be kept and that you are in a **sandbox project**. Deleting buckets or services is destructive.

Recommended order:

1. Delete the Eventarc trigger to stop delivering events to the receiver.
2. Delete the Cloud Run service if no longer needed.
3. Delete objects/buckets after backing up any data to retain.
4. Remove unnecessary IAM bindings and delete created service accounts.
5. Inspect Artifact Registry images, Cloud Build artifacts, and logs per retention policies.
6. Check billing and leftover resources.

Example initial commands:

~~~bash
gcloud eventarc triggers delete "$TRIGGER_NAME" \
  --project="$PROJECT_ID" \
  --location="$REGION"

gcloud run services delete "$RUN_SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION"
~~~

Never put recursive bucket deletion commands in a default pipeline. Before deleting storage, verify object generations, soft delete, retention locks, and exact bucket identity.

## 22. Acceptance Checklist

### Infrastructure

- [ ] Input and output buckets are distinct, in the right project/location, and non-public.
- [ ] Eventarc trigger uses the `finalized` event and filters on the right input bucket.
- [ ] Trigger location is compatible with the bucket.
- [ ] Cloud Run service requires authentication.
- [ ] Trigger SA has Event Receiver and Invoker on the receiver service.
- [ ] Cloud Storage service agent has Pub/Sub Publisher per guidance.
- [ ] Runtime SA only has read access on input and create access on output.
- [ ] No service account keys in the repository.

### Application

- [ ] Controller reads `ce-*` headers and JSON data separately.
- [ ] Validates bucket/prefix, generation, size, and image format.
- [ ] Reads exact generation rather than blindly fetching latest.
- [ ] Bounds memory and pixel count.
- [ ] PNG output preserves aspect ratio with max edge 320.
- [ ] Output naming is deterministic, create-only, and duplicate-safe.
- [ ] Transient errors return non-2xx; skipped inputs log clear reasons.
- [ ] Logs contain no tokens, secrets, or raw image data.

### Testing

- [ ] Valid JPEG/PNG upload produces a thumbnail.
- [ ] Spoofed non-image file produces no output.
- [ ] Object outside prefix produces no output.
- [ ] Duplicate event does not overwrite existing thumbnail.
- [ ] New generation produces a distinct output key.
- [ ] 401/403 verified when Invoker or bucket permissions are missing.
- [ ] Monitoring covers logs/error counts, latency, and cost.
- [ ] Cleanup runbook and results report completed.

## 23. Self-Check Questions

1. Why is the `finalized` event not a signal that an upload has just started?
2. Eventarc Standard uses CloudEvents binary mode—where does `ce-type` reside?
3. How do CloudEvent `id` and Cloud Storage `generation` differ?
4. Why are separate input and output buckets needed?
5. Why is reading `BlobId(bucket,name,generation)` better than reading the latest version?
6. How does the Eventarc trigger service account's role differ from the runtime service account?
7. Why must Pub/Sub Publisher be granted to the Cloud Storage service agent?
8. What issue does the `doesNotExist()` precondition prevent, and what does HTTP 412 mean?
9. Why does at-least-once delivery require idempotency?
10. If a source object is overwritten with versioning off, can the worker recover the old generation?
11. Why must a file with MIME type `image/jpeg` still have its bytes inspected?
12. When should the handler return 2xx versus non-2xx for retry?
13. Why does a Cloud Run service requiring authentication still need separate ingress controls?
14. Why should the output name be deterministically derived from source identity rather than a random UUID?
15. How can you measure the SLO from successful upload to thumbnail appearance?
16. What costs accrue beyond Cloud Run CPU and memory?

## References

- [Eventarc Standard: Route Cloud Storage events to Cloud Run](https://docs.cloud.google.com/eventarc/standard/docs/run/route-trigger-cloud-storage)
- [Eventarc Standard: Cloud Storage trigger quickstart](https://docs.cloud.google.com/eventarc/standard/docs/run/create-trigger-storage-gcloud)
- [Eventarc Standard: Event format](https://docs.cloud.google.com/eventarc/standard/docs/event-format)
- [Eventarc: CloudEvents JSON examples](https://docs.cloud.google.com/eventarc/docs/cloudevents-json)
- [Eventarc Standard: Retry events and idempotency](https://docs.cloud.google.com/eventarc/docs/retry-events)
- [Cloud Run: Cloud Storage triggers](https://docs.cloud.google.com/run/docs/triggering/storage-triggers)
- [Cloud Run: Deploy Java Spring Boot services](https://docs.cloud.google.com/run/docs/quickstarts/build-and-deploy/deploy-java-service)
- [Cloud Run: Service-to-service authentication](https://docs.cloud.google.com/run/docs/authenticating/service-to-service)
- [Cloud Storage: Consistency and preconditions](https://docs.cloud.google.com/storage/docs/consistency)
- [Cloud Storage Java SDK: BlobId](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.BlobId)
- [Cloud Storage Java SDK: Storage interface](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage)
- [Cloud Storage: Object Versioning](https://docs.cloud.google.com/storage/docs/object-versioning)
- [Cloud Storage: Soft delete](https://docs.cloud.google.com/storage/docs/soft-delete)
- [Google Cloud Java libraries BOM](https://cloud.google.com/java/docs/bom)
