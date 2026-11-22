# Dự án xử lý ảnh theo sự kiện Cloud Storage và Eventarc

## 1. Mục tiêu dự án

Trong dự án này, người học xây dựng một pipeline xử lý ảnh trên Google Cloud: người dùng tải ảnh lên Cloud Storage, Eventarc nhận sự kiện object được tạo, sau đó gửi CloudEvent tới một dịch vụ Java/Spring Boot trên Cloud Run. Dịch vụ đọc ảnh, tạo thumbnail PNG và ghi kết quả vào bucket khác mà không cần máy chủ chạy liên tục để kiểm tra file mới.

Đây là một dự án thực hành tổng hợp của module **CLOUD_PROVIDERS_GCP**: áp dụng project/IAM, Cloud Storage, Cloud Run, Eventarc, Cloud Build, Artifact Registry, logging, bảo mật, tự động hóa và kiểm soát chi phí.

Sau khi hoàn thành, người học có thể:

1. Phân biệt input bucket, output bucket, trigger identity và runtime identity.
2. Giải thích sự kiện `google.cloud.storage.object.v1.finalized` và CloudEvents binary content mode.
3. Xây dựng một HTTP receiver bằng Spring Boot sử dụng Google Cloud Storage Java client.
4. Tạo thumbnail có kích thước giới hạn và chỉ lưu kết quả một lần cho mỗi object generation.
5. Cấu hình IAM quyền tối thiểu cho Cloud Storage service agent, Eventarc trigger và Cloud Run runtime.
6. Deploy service, tạo trigger, upload ảnh và xác minh kết quả từ logs và bucket.
7. Xử lý duplicate deliveries, lỗi tạm thời, dữ liệu không hợp lệ và object bị ghi đè.
8. Thiết kế monitoring, kiểm thử, cleanup và mở rộng theo nhu cầu thực tế.

**Ranh giới bài tập:** sử dụng **Eventarc Standard** với direct Cloud Storage events, Cloud Run **service**, Java 21 và Spring Boot. Không dùng polling, Cloud Scheduler hay Pub/Sub subscription tự viết cho luồng chính.

## 2. Yêu cầu nghiệp vụ và tiêu chí hoàn thành

Ứng dụng mẫu có tên `image-worker`, nhận ảnh ở bucket nguồn và xuất thumbnail với cạnh dài tối đa 320 pixel vào bucket đích.

| Yêu cầu | Tiêu chí kiểm tra |
|---|---|
| Upload ảnh JPEG/PNG | Tạo event finalized và Cloud Run nhận được |
| Giới hạn nguồn | Chỉ xử lý object tên bắt đầu bằng `uploads/` |
| Giới hạn dung lượng | Không xử lý tệp vượt 10 MiB |
| Giới hạn pixel | Không decode ảnh có kích thước vượt ngưỡng an toàn được cấu hình |
| Giữ tỷ lệ ảnh | Cạnh dài không quá 320 pixel, không phóng to ảnh nhỏ |
| Kết quả | PNG trong bucket output, tên xác định theo object và generation |
| Giao trùng | Không tạo nhiều object hoặc ghi đè output cùng khóa |
| File không phải ảnh | Bỏ qua có ghi log, tránh retry vô hạn |
| Lỗi Cloud Storage tạm thời | HTTP thất bại để hạ tầng có cơ hội redelivery |
| Bảo mật | Không mở dịch vụ Cloud Run cho invoker ẩn danh |

Các yêu cầu kích thước và định dạng là lựa chọn cho bài tập. Ở production, cần cân nhắc ảnh lớn, HEIC/WebP, chất lượng nén, EXIF orientation, chống ảnh độc hại và pipeline quét malware.

### 2.1. Kiến trúc

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

Một đối tượng đầu vào chỉ đi qua một con đường xử lý. Chúng ta cố ý dùng **hai bucket khác nhau**: output uploads không phát sinh thêm event cho trigger input, tránh vòng lặp xử lý vô hạn.

### 2.2. Thành phần và danh tính

| Thành phần | Vai trò | Danh tính |
|---|---|---|
| Cloud Storage input | Nhận file gốc | Người dùng/ứng dụng upload có quyền ghi |
| Cloud Storage service agent | Phát thông báo phục vụ direct events | Service agent do Google quản lý |
| Eventarc trigger | Lọc và phân phối event | User-managed trigger service account |
| Cloud Run image-worker | HTTP receiver và xử lý ảnh | User-managed runtime service account |
| Cloud Storage output | Lưu thumbnail | Runtime SA có quyền tạo object |
| Cloud Build/Artifact Registry | Build và lưu image khi deploy source | Build identity riêng theo cấu hình |

Không cấp role Owner/Editor cho runtime chỉ để đọc hai bucket. Mỗi identity cần quyền riêng cho công việc thực hiện.

## 3. Hiểu cơ chế sự kiện trước khi viết code

### 3.1. Finalized nghĩa là gì?

Sự kiện `google.cloud.storage.object.v1.finalized` xuất hiện khi một object mới được tạo thành công trong bucket hoặc khi việc ghi đè tạo **generation mới**. Đây không phải sự kiện tải file bắt đầu; Cloud Storage chỉ công bố object sau khi upload hoàn thành.

Các event khác như `deleted`, `archived` và `metadataUpdated` có ý nghĩa khác. Trong dự án, chỉ dùng finalized để xử lý dữ liệu có nội dung mới, không chạy lại khi metadata thay đổi.

**Cloud Storage object generation** định danh một phiên bản nội dung. Nếu `uploads/cat.jpg` bị ghi đè, generation mới là một đầu vào mới hợp lệ; không nên gộp mọi lần upload cùng tên thành một tác vụ.

### 3.2. Eventarc giao CloudEvents như thế nào?

Eventarc Standard gửi HTTP request tới Cloud Run ở **CloudEvents binary content mode**:

- Metadata nằm trong các HTTP headers như `ce-id`, `ce-source`, `ce-type`, `ce-subject`.
- `Content-Type` thể hiện kiểu của dữ liệu sự kiện, ở đây là `application/json`.
- **HTTP body** chứa dữ liệu object (`data`) chứ không phải luôn là một JSON object có cả wrapper `id/source/type/data`.

Ví dụ giản lược:

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

Trong mô hình binary mode, Spring controller có thể bind headers và body riêng. Nếu dùng CloudEvents SDK, thư viện có thể dựng lại CloudEvent object; ví dụ bài này không cần thêm SDK đó.

### 3.3. Event có thể đến nhiều lần và không theo thứ tự

Eventarc Standard có cơ chế **at-least-once delivery**. Khi delivery thất bại, hệ thống có thể retry; một số event có thể bị gửi trùng. Không dựa vào thứ tự các event `finalized` của những generation khác nhau.

Chọn khóa xử lý:

~~~text
source bucket + object name + object generation
~~~

CloudEvents (`ce-source`, `ce-id`) cũng có thể dùng để deduplicate sự kiện, nhưng ở đây output được gắn với **identity của bản dữ liệu đầu vào**, giúp kết quả nhất quán cả khi nhận hai event khác nhau về cùng object generation.

## 4. Quyết định kiến trúc chống vòng lặp và ghi đè

### 4.1. Hai bucket độc lập

Ví dụ:

~~~text
gs://PROJECT-images-in-UNIQUE/
  uploads/cat.jpg
  uploads/dog.png

gs://PROJECT-images-out-UNIQUE/
  thumbnails/34be...c01a.png
  thumbnails/0f86...e92d.png
~~~

Tên output là SHA-256 hex của chuỗi `bucket + newline + name + newline + generation`. Điều này tránh phải dùng trực tiếp tên file do người dùng cung cấp làm tên đích, giảm xung đột và không lộ tên file trong output path.

### 4.2. Ghi kết quả có điều kiện

Khi upload thumbnail, dùng **generation precondition** với `Storage.BlobTargetOption.doesNotExist()`. Chỉ một request đầu tiên có thể tạo output object; request tiếp theo cùng output name nhận HTTP 412 từ Storage và được coi là **đã xử lý**.

Lưu ý: precondition này bảo vệ **việc ghi đè object**, không tự đảm bảo tác vụ CPU chỉ chạy một lần. Nếu có nhiều worker cùng xử lý sự kiện, chúng vẫn có thể decode và resize trùng. Ở quy mô lớn, dùng thêm một bảng job state/lease hoặc cache phù hợp.

### 4.3. Đọc đúng generation

Đầu vào có thể bị ghi đè trong lúc event đang chờ giao. Vì thế, worker đọc:

~~~java
BlobId.of(bucket, name, generation)
~~~

thay vì chỉ lấy phiên bản mới nhất. Nếu generation cũ không còn khả dụng do bucket không bật Object Versioning/retention và đã bị ghi đè, worker không thể tự tạo lại dữ liệu cũ. Bài tập ghi log trường hợp này và ack để tránh retry vĩnh viễn; production nên lưu diagnostic record hoặc đưa vào hàng xử lý ngoại lệ.

## 5. Chuẩn bị project và công cụ

### 5.1. Điều kiện tiên quyết

- Một Google Cloud project có billing được bật và quota đủ.
- `gcloud`, `gcloud storage`, quyền tạo bucket, service account, Cloud Run service và Eventarc trigger.
- Java 21 và Maven trên máy dev, hoặc Cloud Shell/Cloud Build cho phần build.
- Quyền cấp IAM có kiểm soát; trong tổ chức cần approval của platform/security.
- Một ảnh JPEG hoặc PNG nhỏ, không chứa dữ liệu nhạy cảm.

Các ví dụ Bash bên dưới dành cho **Google Cloud Shell**. Không chạy nguyên xi trong PowerShell hoặc dùng placeholder trên môi trường production. Bucket name phải **duy nhất toàn cầu**.

### 5.2. Khai báo biến môi trường

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

Lựa chọn `asia-southeast1` chỉ là ví dụ vùng triển khai. Trong bài, **input bucket và trigger phải ở cùng location**; Cloud Run được đặt cùng region để dễ vận hành và giảm độ trễ.

### 5.3. Bật API

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

Account thực hiện cần quyền bật API và tạo resources. Quyền của developer/builder **không giống** runtime service account; không cấp tất cả quyền deploy cho runtime chỉ vì Cloud Build cần build image.

## 6. Tạo input và output buckets

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

Dùng uniform bucket-level access để quản lý IAM rõ ràng ở cấp bucket. Tùy tổ chức, còn cần policy về public access prevention, retention, soft delete và CMEK.

Kiểm tra:

~~~bash
gcloud storage buckets describe "gs://$INPUT_BUCKET"
gcloud storage buckets describe "gs://$OUTPUT_BUCKET"
~~~

**Không để output bucket là chính input bucket** trong bài tập. Nếu cố dùng một bucket, phải thiết kế bộ lọc object prefix và cơ chế chặn vòng lặp cẩn thận; Eventarc direct trigger mặc định trong ví dụ lọc **bucket + type**, không tự lọc prefix `uploads/`.

## 7. Service accounts và IAM tối thiểu

### 7.1. Tạo hai user-managed service accounts

~~~bash
gcloud iam service-accounts create image-worker-sa \
  --project="$PROJECT_ID" \
  --display-name="Image processing runtime"

gcloud iam service-accounts create eventarc-delivery-sa \
  --project="$PROJECT_ID" \
  --display-name="Eventarc Cloud Run delivery"
~~~

Hai service accounts có trách nhiệm khác nhau:

- **RUN_SA:** danh tính Java service dùng ADC để đọc input và tạo output.
- **TRIGGER_SA:** danh tính Eventarc dùng để nhận event và invoke Cloud Run endpoint được bảo vệ.

### 7.2. Quyền Cloud Storage cho runtime

~~~bash
gcloud storage buckets add-iam-policy-binding "gs://$INPUT_BUCKET" \
  --member="serviceAccount:$RUN_SA" \
  --role="roles/storage.objectViewer"

gcloud storage buckets add-iam-policy-binding "gs://$OUTPUT_BUCKET" \
  --member="serviceAccount:$RUN_SA" \
  --role="roles/storage.objectCreator"
~~~

`objectViewer` cung cấp quyền đọc source generations đang truy cập được. `objectCreator` đủ cho create-only thumbnail, không cho quyền xóa hoặc ghi đè output bằng tên cũ. Mã nguồn dùng precondition để xử lý tình huống đã tồn tại.

Nếu sau này cần đọc output metadata, lifecycle hay xóa file, phải xem xét role riêng, không tự nâng thành Storage Admin một cách tiện tay.

### 7.3. Quyền cho Eventarc trigger

~~~bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$TRIGGER_SA" \
  --role="roles/eventarc.eventReceiver"
~~~

Sau khi deploy Cloud Run service, cấp `roles/run.invoker` cho TRIGGER_SA **trên service đó**. Đừng cấp Invoker rộng ở cấp project khi chỉ cần gọi một receiver.

### 7.4. Cloud Storage service agent phải được publish event

~~~bash
STORAGE_SERVICE_AGENT="$(gcloud storage service-agent \
  --project="$PROJECT_ID")"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$STORAGE_SERVICE_AGENT" \
  --role="roles/pubsub.publisher"
~~~

Đây là service agent do Google quản lý, khác TRIGGER_SA và RUN_SA. Eventarc Standard dùng Pub/Sub làm transport cho direct Cloud Storage events.

Ở các project rất cũ, Pub/Sub service agent có thể cần `roles/iam.serviceAccountTokenCreator` để xác thực push. **Chỉ cấp khi đúng điều kiện theo hướng dẫn hiện hành**, không cấp role nhạy cảm này mặc định cho mọi project.

## 8. Cấu trúc dự án Java/Spring Boot

Một ứng dụng Maven tối giản:

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

Chúng ta sử dụng Java 21, Spring MVC và Google Cloud Storage Java library. Các version dưới đây là **ví dụ khóa dependency để tái lập bài học**, cần được rà soát security updates và tương thích trước khi dùng trong production.

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

Spring Boot starter quản lý HTTP server, Jackson JSON và logging. `libraries-bom` quản lý những dependencies Google Cloud tương thích. Dự án không cần tự lưu access token hoặc service account key.

### 8.2. Spring Boot bootstrap và Storage bean

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

Cloud Run cung cấp `PORT` và service account runtime. Spring Boot mặc định nghe cổng 8080; khi dùng cấu hình cổng khác, cần bảo đảm ứng dụng bind `0.0.0.0` và dùng cổng Cloud Run cung cấp.

## 9. Model dữ liệu Cloud Storage event

Dữ liệu body của finalized event có nhiều trường hơn dự án cần. Ta chỉ khai báo những trường dùng trực tiếp; Jackson bỏ qua thuộc tính không biết.

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

`generation` và `size` là chuỗi trong payload thông dụng, cần parse có kiểm tra. Không được tin `contentType` để kết luận bytes thật sự là ảnh an toàn; đó chỉ là metadata có thể do uploader khai báo.

## 10. GcsImageProcessor: đọc generation, resize và ghi output

Ở phiên bản thực hành, ta giới hạn input tối đa 10 MiB và số pixel tối đa 20 triệu. Kiểm tra header bằng ImageIO `ImageReader` trước khi decode giúp giảm một số nguy cơ memory exhaustion, nhưng **chưa thay thế** sandbox và kiểm tra chuyên sâu đối với dữ liệu không tin cậy.

### 10.1. Mã xử lý

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

### 10.2. Phân tích các quyết định quan trọng

- `storage.readAllBytes(BlobId.of(bucket, name, generation))` đọc **đúng generation**, không đọc nhầm nội dung mới hơn khi object bị overwrite.
- `MAX_BYTES` giới hạn kích thước data lưu trong memory.
- `MAX_PIXELS` giới hạn kích thước ảnh trước decode. Với ảnh nguồn lớn hoặc format phức tạp, cần pipeline streaming và image library được harden riêng.
- `MAX_EDGE` không phóng to ảnh nhỏ; output giữ tỷ lệ.
- `sha256` tạo output key ổn định theo source identity; không đưa trực tiếp tên người dùng vào path.
- `doesNotExist()` tạo behavior create-only cho output, giúp retry an toàn.
- HTTP 412 trên output được coi là đã có kết quả, **không phải 500 cần retry**.
- Source generation không tồn tại trả `SOURCE_MISSING`; cần quan sát và có thể bổ sung xử lý ngoại lệ ngoài luồng.

Code cố tình không xử lý EXIF orientation, animation, ICC color profiles hoặc HEIC/WebP. Mức này phù hợp bài lab, chưa phải image transcoding service production.

## 11. ImageEventsController: nhận CloudEvent qua HTTP

Eventarc gửi HTTP POST ở path root `/` theo trigger config của bài. Controller nhận headers `ce-*` và JSON body.

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

**HTTP status là một quyết định quan trọng:**

- Trả 2xx khi xử lý thành công hoặc chủ động bỏ qua event không thể phục hồi bằng retry, như file không phải ảnh.
- Không bắt mọi exception rồi trả 2xx, vì điều đó sẽ làm mất cơ hội retry khi Cloud Storage tạm thời lỗi.
- Exception chưa xử lý dẫn tới lỗi 5xx qua Spring/Cloud Run, tạo khả năng redelivery theo chính sách Eventarc/Pub/Sub.
- Nếu payload bị hỏng không bind được JSON, Spring có thể trả 400; cần có dead-letter/quarantine và giới hạn retry để tránh poison message bị thử mãi.
- Với `SOURCE_MISSING`, ví dụ trả 204 sau khi log. Production nên ghi nhận một bản exception/audit riêng để không mất dấu object generation không còn truy xuất được.

Cloud Run IAM và trigger service account bảo vệ receiver khỏi invocation ẩn danh. Header `ce-id` tự nó **không phải chứng thực bảo mật** nếu endpoint được mở cho người bất kỳ; không tắt IAM chỉ vì controller kiểm tra `ce-source`.

## 12. Kiểm thử ứng dụng tại máy phát triển

### 12.1. Unit tests trước khi deploy

Có thể kiểm thử controller mà không cần Cloud Storage hoặc Google Cloud credential bằng Mockito. Ví dụ:

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

Bổ sung test cho `GcsImageProcessor` bằng fake/mock `Storage` để kiểm tra 404, 412, 5xx, input quá lớn, ảnh giả và output key. Không cần ảnh thật trong mọi unit test; có thể tạo `BufferedImage` nhỏ rồi encode JPEG/PNG trong bộ nhớ.

### 12.2. Kiểm tra boundary và security

Những tình huống quan trọng:

| Tình huống | Kết quả mong đợi |
|---|---|
| Source bucket khác | Bỏ qua, không đọc object |
| Object ngoài `uploads/` | Bỏ qua |
| Metadata size không hợp lệ | Bỏ qua và log phù hợp |
| File văn bản giả đuôi JPG | Không tạo thumbnail |
| Ảnh vượt MAX_PIXELS | Bỏ qua |
| Giao lại cùng event | Tên output không thay đổi, không overwrite |
| Source bị ghi đè | Xử lý đúng generation hoặc ghi nhận không còn |
| Storage 503 | Trả lỗi tạm thời để retry |
| Không có token invoke Cloud Run | Bị platform từ chối |
| Runtime mất quyền đọc nguồn | Permission denied có thể quan sát được |

Test idempotency không nên chỉ `verify(processor).process()` mà còn kiểm tra precondition đầu ra thực sự bảo vệ khỏi ghi đè bằng integration test.

## 13. Build và deploy Cloud Run từ source

Sau khi tạo các file Java/Maven ở trên và chạy test:

~~~bash
mvn -B test
mvn -B package
~~~

Các lệnh này là **hướng dẫn cho người học**, không phải thao tác đã thực hiện trong STEP 4.

Tại thư mục chứa `pom.xml`, deploy:

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

Cloud Run source deploy sử dụng build workflow để tạo image và có thể cần Artifact Registry repository hoặc Cloud Build permissions. Người triển khai phải có quyền deploy và `iam.serviceAccounts.actAs` trên RUN_SA; không cấp quyền build cho runtime một cách mặc định.

Với các image được decode trong memory, giới hạn concurrency giúp tránh nhiều ảnh lớn cùng làm vượt memory. Mức 512 MiB chỉ là cấu hình lab; phải đo memory/CPU và điều chỉnh theo dữ liệu thực.

Kiểm tra:

~~~bash
gcloud run services describe "$RUN_SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="value(status.url)"
~~~

Không mở Cloud Run service bằng `--allow-unauthenticated` chỉ để xử lý lỗi IAM của trigger.

## 14. Cấp Invoker và tạo Eventarc trigger

### 14.1. Cấp quyền invoke cho trigger service account

~~~bash
gcloud run services add-iam-policy-binding "$RUN_SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --member="serviceAccount:$TRIGGER_SA" \
  --role="roles/run.invoker"
~~~

Không cấp `roles/run.invoker` cho `allUsers`. Trigger service account có quyền nhận event qua Eventarc ở mức project, và chỉ có quyền invoke đúng service này.

### 14.2. Tạo trigger từ finalized event

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

Điểm cần xác nhận:

- Direct Cloud Storage trigger cùng project và location tương thích với bucket nguồn.
- Cloud Run target có thể ở region khác theo giới hạn sản phẩm, nhưng trong lab đặt cùng region để đơn giản.
- Trigger lọc **type** và **bucket**, không tự bảo vệ prefix; code lọc `uploads/`.
- Phải có `roles/pubsub.publisher` của Cloud Storage service agent.
- Trigger cần quyền `roles/eventarc.eventReceiver`; authenticated Cloud Run cần `roles/run.invoker` cho trigger SA.
- Eventarc service agent/IAM bindings có thể cần thời gian lan truyền.
- Trigger mới tạo có thể mất khoảng vài phút mới bắt đầu nhận event.

Nếu bucket location là multi-region hoặc dual-region, trigger location và Pub/Sub message storage policy phải tuân theo quy tắc tương ứng; đừng chọn ngẫu nhiên một region.

### 14.3. Kiểm tra trigger

~~~bash
gcloud eventarc triggers list \
  --project="$PROJECT_ID" \
  --location="$REGION"

gcloud eventarc triggers describe "$TRIGGER_NAME" \
  --project="$PROJECT_ID" \
  --location="$REGION"
~~~

Xác minh event type, bucket filter, destination service, trigger SA và trạng thái healthy/active trước khi upload dữ liệu thử.

## 15. Chạy end-to-end: upload ảnh và nhận thumbnail

### 15.1. Chuẩn bị ảnh

Dùng ảnh JPEG/PNG nhỏ được phép sử dụng. Trong Google Cloud Shell, giả sử file tên `sample.jpg` nằm ở thư mục hiện tại:

~~~bash
gcloud storage cp ./sample.jpg \
  "gs://$INPUT_BUCKET/uploads/sample.jpg"
~~~

Upload thành công tạo một object generation mới và phát finalized event. Eventarc chuyển event tới Cloud Run; service đọc source và ghi thumbnail.

### 15.2. Xem logs

~~~bash
gcloud run services logs read "$RUN_SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --limit=50
~~~

Tìm thông báo `Image event id=... result=CREATED` hoặc `ALREADY_EXISTS`. Nếu logs chỉ báo `SKIPPED`, kiểm tra prefix, metadata size, format hoặc file quá lớn.

Kiểm tra output:

~~~bash
gcloud storage ls "gs://$OUTPUT_BUCKET/thumbnails/"
~~~

Thumbnail có tên hash nên không giống tên file gốc. Có thể tải một output để mở xem, dựa trên object name thực tế từ lệnh list.

### 15.3. Thử tính idempotent

Gửi lại cùng CloudEvent tới một **môi trường test được xác thực** hoặc dùng integration test giả lập duplicate call. Output name không đổi và ghi thêm lần hai phải bị từ chối bằng precondition 412, được code xử lý như `ALREADY_EXISTS`.

Nếu upload đè `uploads/sample.jpg` bằng một ảnh khác, Cloud Storage tạo **generation mới**, worker sẽ tạo một output key khác. Không nhầm hai generation với retry của cùng một event.

### 15.4. Thử bỏ qua file không hợp lệ

~~~bash
printf 'not an image' > fake.jpg
gcloud storage cp ./fake.jpg \
  "gs://$INPUT_BUCKET/uploads/fake.jpg"
~~~

Worker bỏ qua vì `ImageIO` không tìm thấy image reader phù hợp. Không cần ép retry liên tục với dữ liệu đã xác định không phải ảnh. Có thể mở rộng để ghi trạng thái quarantine và thông báo cho uploader.

## 16. Xử lý lỗi và Eventarc retry

### 16.1. Bảng phân loại

| Triệu chứng | Khả năng | Cách kiểm tra |
|---|---|---|
| Không có Cloud Run request | Trigger chưa active, sai bucket/location, IAM service agent | Eventarc trigger status và filter |
| Eventarc báo 403 khi invoke | Trigger SA thiếu `roles/run.invoker` | Cloud Run IAM policy |
| Event receiver nhận 400 | JSON không bind được hoặc Content-Type/path sai | Controller logs, CloudEvents mode |
| Worker nhận 403 từ Storage | RUN_SA thiếu quyền trên input/output bucket | Bucket IAM và ADC identity |
| Worker nhận 404 từ Storage | Generation đã bị xóa/ghi đè | Object Versioning, name/generation và logs |
| Output nhận 412 | Thumbnail đã có | Hành vi idempotent mong đợi |
| Worker 500/503 | Storage lỗi tạm, decode exception, thiếu memory | Cloud Run logs, memory/timeout |
| Xử lý lặp nhiều lần | At-least-once/redelivery | Output key, retries, dead-letter controls |
| Không thấy ảnh output | Data không nằm dưới `uploads/` hoặc bị skip | Event body, size, ImageIO format |
| Lỗi sau khi đổi IAM | Policy chưa lan truyền hoặc role sai principal | IAM bindings và audit logs |

### 16.2. 2xx và non-2xx

Trong hệ thống dùng delivery có retry, **chỉ trả 2xx sau khi side effects đã đạt trạng thái an toàn** hoặc đã quyết định bỏ qua có kiểm soát. Nếu Cloud Storage tạm thời trả 503, hãy để request thất bại; Eventarc/Pub/Sub có thể redeliver.

Ngược lại, với dữ liệu không hợp lệ cố định, retry không làm nó thành ảnh hợp lệ. Trả 2xx sau khi ghi nhận vào log/quarantine, tránh poison message làm tốn tài nguyên lặp.

Để xử lý lỗi dài hạn, cấu hình retry/backoff và dead-letter policy của Pub/Sub subscription do Eventarc Standard dùng theo khả năng quản trị; không giả định tất cả sự kiện được giữ vô hạn hoặc luôn sẽ được giao lại.

### 16.3. Duplicate, out-of-order và object overwrite

Ba quy tắc giúp pipeline an toàn:

1. Đọc đúng source **generation**.
2. Output key xác định từ source identity.
3. Ghi output bằng `doesNotExist()`.

Nếu nguồn generation không còn vì object đã bị overwritten khi versioning tắt, code không thể phục hồi bản cũ. Muốn giữ lịch sử khi upload cùng tên, cân nhắc Cloud Storage Object Versioning và lifecycle/retention hợp lý; versioning có chi phí thêm và không thay thế soft delete khi cần bảo vệ xóa nhầm.

### 16.4. Chặn vòng lặp sự kiện

Không lưu output vào input bucket nếu trigger bắt toàn bucket mà không có cấu hình tách đường xử lý. Trong bài này, output bucket khác input nên một thumbnail không tạo tiếp event được trigger lắng nghe.

Nếu mở rộng thành pipeline nhiều tầng (thumbnail, OCR, classification), dùng bucket hoặc event type/metadata contracts riêng và một state machine theo dõi mỗi bước, tránh việc mỗi output lại kích hoạt chính nó.

## 17. Bảo mật và least privilege

### 17.1. Danh tính và permission

| Identity | Quyền | Resource |
|---|---|---|
| Người upload | `roles/storage.objectCreator` | Input bucket, nếu chỉ được tạo |
| Cloud Storage service agent | `roles/pubsub.publisher` | Project theo hướng dẫn direct event |
| Trigger SA | `roles/eventarc.eventReceiver` | Fleet/project scope của event receiver |
| Trigger SA | `roles/run.invoker` | Chỉ image-worker Cloud Run service |
| Runtime SA | `roles/storage.objectViewer` | Input bucket |
| Runtime SA | `roles/storage.objectCreator` | Output bucket |
| Developer/deployer | Quyền deploy và `actAs` | Chỉ service accounts/tài nguyên cần thiết |

Đừng dùng một service account chung có mọi quyền. IAM ở bucket kiểm soát quyền object, còn Cloud Run Invoker bảo vệ endpoint. Không lưu JSON key trong image hoặc repository.

### 17.2. Data validation và image hardening

Ảnh từ người dùng là **untrusted input**. Các biện pháp cần xem xét:

- Hạn chế kích thước upload và kích thước sau decode.
- Chỉ dùng decoder được hỗ trợ/cập nhật security patches.
- Kiểm tra MIME và nội dung thực tế, không tin extension.
- Tránh dùng ImageMagick hay tool ngoài để thực thi input qua shell command không kiểm soát.
- Cân nhắc quét malware, giới hạn CPU/memory/time và sandbox.
- Xem xét EXIF, GPS metadata, privacy và xóa metadata khỏi thumbnail khi phù hợp.
- Không đưa bucket data cá nhân hoặc object name nhạy cảm vào logs công khai.
- Với ảnh quá lớn, cân nhắc Cloud Run jobs/Workflows hoặc pipeline xử lý riêng.

Ví dụ dùng Java ImageIO và ảnh nhỏ; production cần đánh giá riêng decoder vulnerabilities, decompression bombs, định dạng animation, color profile và phần mềm bên thứ ba.

### 17.3. Bucket access và retention

Bật public access prevention/UBLA theo yêu cầu tổ chức. Nếu cần bảo vệ ảnh gốc khỏi bị ghi đè/xóa nhầm, đánh giá soft delete, versioning và retention, nhưng cần xem chi phí. Không cấu hình lifecycle xóa bản gốc trước khi chắc rằng event đã được xử lý.

## 18. Monitoring, SLO và kiểm soát chi phí

### 18.1. Các chỉ số

| Chỉ số | Ý nghĩa |
|---|---|
| Event delivery failures | Eventarc không chuyển được event |
| Cloud Run 4xx/5xx | Lỗi payload/IAM/runtime |
| Cloud Run p95 latency | Thời gian xử lý tăng |
| Container memory usage | Ảnh quá lớn hoặc concurrency cao |
| `CREATED` count | Thumbnail được tạo thành công |
| `SKIPPED` count | Input không đủ điều kiện |
| `SOURCE_MISSING` count | Generation không còn để xử lý |
| `ALREADY_EXISTS` count | Retry/duplicate deliveries |
| Age from event time to output creation | Độ trễ end-to-end |
| Cost per processed image | Chi phí storage + event + compute |

Ví dụ SLO của bài tập: **99% ảnh hợp lệ dưới 10 MiB có thumbnail trong vòng 3 phút**. Đây là mục tiêu minh họa; cần đo từ log và output metadata để kiểm tra khả năng đáp ứng.

### 18.2. Những thành phần phát sinh chi phí

- Cloud Storage dung lượng input, output, số operation và khả năng egress.
- Eventarc Standard / Pub/Sub transport và delivery.
- Cloud Run request, CPU, memory, concurrency và thời gian xử lý.
- Cloud Build/Artifact Registry khi deploy source.
- Cloud Logging/Monitoring, retention log và alerting.
- Storage Versioning/soft delete nếu bật cho input/output.

Với ảnh trung bình lớn, tải toàn bộ vào memory có thể tăng chi phí CPU và memory. Bắt đầu với limit nhỏ, đo số lượng ảnh/giây và tính lại cạnh thumbnail, throughput và khả năng dùng streaming.

## 19. CI/CD và Infrastructure as Code

Một pipeline production nên tách:

1. Pull request: compile, unit tests, static analysis, dependency scan.
2. Main branch: build image một lần và đẩy Artifact Registry.
3. Staging: deploy Cloud Run với runtime SA staging.
4. Integration test: upload ảnh vào sandbox input bucket và kiểm tra thumbnail output.
5. Approval: promote cùng image digest vào production.
6. IaC: quản lý bucket, IAM bindings, Cloud Run config, Eventarc trigger và alerts.
7. Post-deploy: kiểm tra trigger health, error rate và rollback.

Tránh cấu hình toàn bộ IAM thủ công ở production mà không lưu trong Git/terraform state được bảo vệ. Với Eventarc, resource dependency order cần được quản lý: service/SA và quyền Invoker trước, trigger sau. Nhớ rằng IAM propagation có thể khiến trigger vừa tạo chưa giao được event ngay.

Khi dùng Terraform, nên có module tách input/output storage, Eventarc trigger, Cloud Run service và IAM. Đừng đưa secret/token tĩnh vào state hoặc `.tfvars` công khai.

## 20. Mở rộng dự án theo cấp độ

### Cấp 1 — thumbnail cơ bản

- Một kích thước 320 px, output PNG.
- Java/Spring HTTP CloudEvents receiver.
- IAM tối thiểu, duplicate-safe output.
- Kiểm thử upload, skip và retry.

### Cấp 2 — nhiều kích thước và metadata

- Tạo thumbnails 160/320/640 px.
- Lưu metadata gồm source generation, target generation và checksum vào Firestore.
- Tạo trạng thái `PENDING / COMPLETE / FAILED` có retry budget.
- Dùng idempotency key ở Firestore transaction để tránh chạy CPU trùng.

### Cấp 3 — pipeline có kiểm soát

- Scan ảnh và kiểm tra content policy trước khi publish.
- Workflow hoặc Cloud Tasks để retry/quarantine có giới hạn.
- Hỗ trợ ảnh HEIC/WebP hoặc thumbnail video bằng container chuyên dụng.
- Truy vết SLO, quota, cost và hỗ trợ reprocessing.
- Cân nhắc GKE hoặc Cloud Run jobs nếu workload batch dài và cần tài nguyên riêng.

### Cấp 4 — multi-region và bảo vệ dữ liệu

- Bucket location và Eventarc regionality theo kiến trúc doanh nghiệp.
- Quản lý CMEK, VPC Service Controls và tổ chức IAM.
- Cơ chế khôi phục khi Eventarc/Pub/Sub bị gián đoạn.
- Lifecycle policies và replication cho dữ liệu quan trọng.
- Kiểm thử disaster recovery và quy trình rebuild toàn bộ thumbnails.

## 21. Cleanup sau lab

Chỉ thực hiện cleanup khi đã xác nhận không còn dữ liệu cần giữ và đang ở **project thử nghiệm**. Xóa bucket hoặc service là thao tác phá hủy.

Thứ tự nên là:

1. Xóa Eventarc trigger để ngừng phát event vào receiver.
2. Xóa Cloud Run service nếu không còn sử dụng.
3. Xóa object/bucket sau khi backup dữ liệu cần giữ.
4. Gỡ IAM bindings không còn cần thiết và xóa service accounts đã tạo.
5. Kiểm tra Artifact Registry images, Cloud Build artifacts và logs theo retention.
6. Kiểm tra billing và leftover resources.

Ví dụ các lệnh đầu tiên:

~~~bash
gcloud eventarc triggers delete "$TRIGGER_NAME" \
  --project="$PROJECT_ID" \
  --location="$REGION"

gcloud run services delete "$RUN_SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION"
~~~

Không đưa lệnh xóa recursive buckets vào pipeline mặc định. Khi xóa storage, cần kiểm tra object generations, soft delete, retention locks và xác nhận đúng bucket trước.

## 22. Checklist nghiệm thu

### Hạ tầng

- [ ] Input/output buckets khác nhau, đúng project/location và không public.
- [ ] Eventarc trigger dùng finalized event, lọc đúng input bucket.
- [ ] Trigger location tương thích với bucket.
- [ ] Cloud Run service yêu cầu authentication.
- [ ] Trigger SA có Event Receiver và Invoker trên receiver.
- [ ] Cloud Storage service agent có Pub/Sub Publisher theo hướng dẫn.
- [ ] Runtime SA chỉ có quyền đọc nguồn, tạo output.
- [ ] Không có service account key trong repository.

### Ứng dụng

- [ ] Controller đọc `ce-*` headers và JSON data riêng.
- [ ] Kiểm tra bucket/prefix, generation, size và image format.
- [ ] Đọc đúng generation, không đọc mù bản mới nhất.
- [ ] Giới hạn memory và số pixel.
- [ ] Output PNG giữ tỷ lệ với cạnh dài tối đa 320.
- [ ] Tên output deterministic, create-only và duplicate-safe.
- [ ] Lỗi tạm thời trả non-2xx, dữ liệu bỏ qua có lý do.
- [ ] Logs không chứa token, secret hoặc dữ liệu ảnh.

### Kiểm thử

- [ ] Upload JPEG/PNG hợp lệ có thumbnail.
- [ ] Upload file giả ảnh không tạo output.
- [ ] Upload object ngoài prefix không tạo output.
- [ ] Duplicate event không overwrite thumbnail.
- [ ] New generation tạo output key riêng.
- [ ] 401/403 được kiểm tra khi thiếu Invoker/quyền bucket.
- [ ] Có monitoring logs/error count, latency và cost.
- [ ] Có quy trình cleanup và báo cáo kết quả.

## 23. Câu hỏi tự kiểm tra

1. Vì sao finalized event không phải dấu hiệu upload vừa bắt đầu?
2. Eventarc Standard dùng CloudEvents binary mode, vậy `ce-type` nằm ở đâu?
3. CloudEvent `id` và Cloud Storage `generation` khác nhau như thế nào?
4. Vì sao cần hai bucket input/output?
5. Vì sao đọc `BlobId(bucket,name,generation)` tốt hơn chỉ đọc phiên bản mới nhất?
6. Vai trò của Eventarc trigger service account khác runtime service account ở điểm nào?
7. Vì sao cần cấp Pub/Sub Publisher cho Cloud Storage service agent?
8. Precondition `doesNotExist()` ngăn vấn đề gì và HTTP 412 có nghĩa là gì?
9. Vì sao at-least-once delivery yêu cầu idempotency?
10. Nếu source object bị overwrite khi versioning tắt, worker có thể phục hồi generation cũ không?
11. Tại sao file có MIME `image/jpeg` vẫn phải kiểm tra bytes?
12. Khi nào trả 2xx và khi nào cần non-2xx để retry?
13. Vì sao một service Cloud Run yêu cầu authentication vẫn cần kiểm soát ingress riêng?
14. Vì sao output name nên ổn định theo source identity thay vì random UUID?
15. Làm sao đo SLO từ upload thành công tới thumbnail xuất hiện?
16. Những loại chi phí nào phát sinh ngoài Cloud Run CPU và memory?

## Tài liệu tham khảo

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

