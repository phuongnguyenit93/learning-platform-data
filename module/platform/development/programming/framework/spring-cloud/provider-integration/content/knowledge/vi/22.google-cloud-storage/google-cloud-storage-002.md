# Tích hợp Cloud Storage bằng client và Spring Resource

## 1. Bối cảnh và mục tiêu

Một ứng dụng Spring Boot thường phải đọc hoặc ghi tài liệu, ảnh, báo cáo, tệp xuất dữ liệu và các nội dung nhị phân khác. Trên Google Cloud, **Cloud Storage** cung cấp API object storage; Java client library cung cấp đối tượng `Storage` để thao tác trực tiếp với bucket và object. Spring Framework bổ sung abstraction **`Resource`** để ứng dụng có thể đọc nhiều loại nguồn dữ liệu theo một giao diện thống nhất, chẳng hạn file local, classpath, URL và object trong Cloud Storage.

**Spring Framework on Google Cloud** (trước đây thường được gọi là Spring Cloud GCP) tích hợp hai cách làm này. Starter Storage tự cấu hình `Storage` bean và hỗ trợ resource URI dạng `gs://bucket/object`. Nhờ đó, một service có thể dùng API Cloud Storage khi cần thao tác chuyên biệt, hoặc dùng Spring `Resource`/`WritableResource` khi muốn truyền nội dung qua các API Spring vốn đã nhận Resource.

Bài học thuộc chương **Google Cloud Storage** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**. Module thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng; học danh tính và quyền, storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider. Bài này tập trung vào client Cloud Storage và Spring Resource abstraction.

Sau bài học, bạn có thể:

- Thêm đúng BOM và starter Storage vào ứng dụng Spring Boot.
- Hiểu `Storage`, `Blob`, `BlobInfo`, `BlobId` và vai trò của Google Cloud Storage Java client.
- Cấu hình Application Default Credentials (ADC), project ID và IAM cho môi trường local/production.
- Inject object GCS bằng `@Value("gs://...") Resource` hoặc lấy động qua `ResourceLoader`.
- Đọc bằng `Resource`, ghi qua `WritableResource` và thao tác metadata thông qua `GoogleStorageResource`.
- Chọn giữa Spring Resource và Storage API theo yêu cầu streaming, generation, precondition và metadata.
- Kiểm soát việc tự tạo bucket/object, đóng stream, xử lý lỗi và kiểm thử tích hợp.

> **Phạm vi phiên bản:** Ví dụ sử dụng Java Cloud Storage client và Spring Framework on Google Cloud. Tên package, starter, property và khả năng auto-configuration phụ thuộc release. Hãy dùng BOM của Spring Framework on Google Cloud để khóa version đồng bộ và đối chiếu bảng tương thích Spring Boot/Spring Cloud/JDK của release đang chọn. Không trộn ví dụ từ các thế hệ Spring Cloud GCP cũ với release hiện tại mà chưa kiểm tra migration guide.

## 2. Hai lớp tích hợp: Storage client và Spring Resource

Có hai cách tiếp cận chính khi ứng dụng làm việc với object:

1. **Cloud Storage Java client:** dùng `Storage` và các lớp `Blob`, `BlobInfo`, `BlobId` để thao tác trực tiếp với bucket/object. Cách này phù hợp khi cần generation, metadata, precondition, listing, streaming và các tính năng đặc thù GCS.
2. **Spring Resource abstraction:** biểu diễn object bằng `Resource` hoặc `WritableResource` với URI `gs://bucket/object`. Cách này hữu ích khi một thành phần Spring đã nhận `Resource` làm đầu vào/đầu ra và không cần phụ thuộc trực tiếp vào API GCS.

~~~mermaid
flowchart TD
    APP["Spring Boot application"] --> CHOICE{"Cách truy cập"}
    CHOICE --> CLIENT["Cloud Storage Java client"]
    CHOICE --> RESOURCE["Spring Resource abstraction"]
    CLIENT --> STORAGE["Storage bean"]
    RESOURCE --> RES["Resource / WritableResource<br/>gs://bucket/object"]
    RES --> STORAGE
    STORAGE --> GCS["Google Cloud Storage"]
    IAM["ADC / workload identity"] -. "Cấp credentials" .-> STORAGE
~~~

| Tiêu chí | `Storage` client | `Resource` / `WritableResource` |
| --- | --- | --- |
| API chính | `Storage`, `Blob`, `BlobInfo`, `BlobId` | `Resource`, `InputStreamSource`, `WritableResource` |
| Định danh | Bucket + object name + generation tùy API | URI `gs://bucket/object` |
| Đọc nội dung | `Storage.reader(...)`, `Blob` hoặc API tải nội dung | `getInputStream()` |
| Ghi nội dung | `Storage.create(...)`, `Storage.writer(...)` | `getOutputStream()` |
| Metadata | Truy cập trực tiếp `Blob`/`BlobInfo` | Có thể cast `GoogleStorageResource` để truy cập `Blob` |
| Preconditions/version | Kiểm soát trực tiếp bằng API option | Cần dùng Storage API khi cần điều kiện chi tiết |
| Phụ thuộc Spring | Không bắt buộc | Có, cần resource integration của Spring Framework on Google Cloud |
| Trường hợp phù hợp | Storage adapter, upload lớn, versioning, metadata, IAM-sensitive operation | API Spring nhận Resource, đọc template, cấu hình, file import/export đơn giản |

Hai cách không loại trừ nhau. Một ứng dụng có thể dùng `Resource` cho luồng đọc file đơn giản và dùng `Storage` client cho upload cần precondition, metadata hoặc xử lý generation. Cả hai vẫn dựa trên cùng project, credentials, IAM và bucket.

## 3. Chuẩn bị dependency và phiên bản

### 3.1. Dùng BOM Spring Framework on Google Cloud

BOM quản lý version cho các module Spring Framework on Google Cloud và dependency liên quan. Maven:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>spring-cloud-gcp-dependencies</artifactId>
            <version>${spring-cloud-gcp.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>spring-cloud-gcp-starter-storage</artifactId>
    </dependency>
</dependencies>
~~~

`spring-cloud-gcp.version` là property do dự án quản lý. Hãy chọn release có trong Maven Central và tương thích với Spring Boot/Spring Cloud đang sử dụng. Tài liệu tương thích của release 7.x hiện hành nêu Spring Boot 3.5.x và Spring Cloud 2025.0.x; các release cũ hơn có ma trận khác. Không nâng riêng starter mà bỏ qua BOM.

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation(
        platform("com.google.cloud:spring-cloud-gcp-dependencies:$springCloudGcpVersion")
    )
    implementation("com.google.cloud:spring-cloud-gcp-starter-storage")
}
~~~

Starter Storage kéo các module cần thiết và tích hợp với core starter. Nếu source code của ứng dụng import trực tiếp lớp Google Cloud Storage Java client mà chính sách dependency yêu cầu khai báo trực tiếp, hãy bổ sung artifact `com.google.cloud:google-cloud-storage` theo cùng BOM; tránh tự gắn một version khác với version mà starter quản lý.

### 3.2. Phân biệt starter và Java client

| Thành phần | Trách nhiệm |
| --- | --- |
| `spring-cloud-gcp-starter` | Cấu hình core Google Cloud như project ID và credentials provider |
| `spring-cloud-gcp-starter-storage` | Tích hợp Cloud Storage và Spring Resource; auto-configure Storage bean |
| `google-cloud-storage` | Java client API để thao tác bucket và object |
| Spring `Resource` | Abstraction đọc tài nguyên |
| Spring `WritableResource` | Mở luồng ghi tài nguyên |

Nếu ứng dụng chỉ dùng `Storage` client thuần, có thể chỉ cần Java client library. Khi cần `gs://` Resource integration và auto-configuration của Spring, dùng starter Storage phù hợp.

### 3.3. Kiểm tra dependency graph

Khi gặp lỗi `NoSuchMethodError`, `ClassNotFoundException` hoặc bean không được tạo, kiểm tra:

- Spring Boot, Spring Cloud release train và Spring Framework on Google Cloud BOM.
- Phiên bản `google-cloud-storage`, `google-auth-library` và các module Google API được resolve.
- Có thư viện cũ kéo thêm phiên bản Spring Cloud GCP khác hay không.
- Starter Storage có trên runtime classpath không, không chỉ compile classpath.
- Có cấu hình loại bỏ auto-configuration hoặc exclude dependency không.

Không giải quyết mismatch bằng cách thêm một version ngẫu nhiên vào dependency. Xác định module nào kéo phiên bản xung đột rồi sửa dependency management.

## 4. Cách Spring Framework on Google Cloud cấu hình Storage

Khi có starter Storage trên classpath và auto-configuration được bật, Spring Framework on Google Cloud tạo bean `Storage` trong ApplicationContext. Bean này dùng credentials provider và project configuration của core starter.

~~~java
import com.google.cloud.storage.Storage;
import org.springframework.stereotype.Service;

@Service
public class DocumentCatalog {

    private final Storage storage;

    public DocumentCatalog(Storage storage) {
        this.storage = storage;
    }
}
~~~

Ứng dụng không cần tự tạo `StorageOptions.getDefaultInstance().getService()` trong mọi service. Inject bean đã được cấu hình giúp các adapter dùng chung project/credentials và đơn giản hóa test.

Nếu cần cấu hình client đặc biệt, có thể tạo `Storage` bean riêng, nhưng phải kiểm tra điều kiện auto-configuration để không có hai bean cạnh tranh hoặc vô tình làm mất cấu hình credentials mặc định. Không khởi tạo một `Storage` client cho mỗi HTTP request.

### 4.1. Project ID

Project ID có thể được cung cấp tường minh:

~~~yaml
spring:
  cloud:
    gcp:
      project-id: training-platform-dev
~~~

Nếu không đặt property, starter có thể khám phá project từ các nguồn môi trường như `GOOGLE_CLOUD_PROJECT`, project trong credentials, Google Cloud SDK hoặc metadata của runtime tùy thứ tự/phiên bản. Trong CI và môi trường triển khai, nên đặt project ID theo cấu hình rõ ràng để tránh chạy nhầm project.

**Project ID không phải bucket name.** Một project có thể có nhiều bucket, và một bucket name không mã hóa đầy đủ project/location/permissions.

## 5. Xác thực: Application Default Credentials và IAM

### 5.1. ADC là gì?

**Application Default Credentials (ADC)** là cơ chế để Google Cloud client libraries tìm credentials theo môi trường. Java client và Spring Framework on Google Cloud có thể dùng ADC mà không cần source code biết credential được cấp theo cách nào.

Các môi trường thường gặp:

| Môi trường | Nguồn danh tính nên dùng |
| --- | --- |
| Laptop developer | ADC do `gcloud auth application-default login` tạo theo chính sách tổ chức |
| CI ngoài Google Cloud | Workload Identity Federation hoặc cơ chế OIDC phù hợp |
| Cloud Run | Service account gắn với service |
| GKE | Workload Identity Federation for GKE |
| Compute Engine | Service account gắn với VM |

Phân biệt hai lệnh:

- `gcloud auth login`: đăng nhập để sử dụng Google Cloud CLI bằng user account.
- `gcloud auth application-default login`: thiết lập ADC cho ứng dụng chạy local.

Đăng nhập CLI thành công không tự động bảo đảm Java process có ADC hợp lệ. Kiểm tra đúng user, credential source, project và quyền của principal mà ứng dụng đang sử dụng.

### 5.2. Không đưa service account key vào source

Ưu tiên workload identity hoặc ADC thay vì tải service account key JSON và đóng gói vào image. Service account key là credential dài hạn; nếu lộ, người khác có thể sử dụng ngoài vòng đời deployment.

Các property như `spring.cloud.gcp.credentials.location` hoặc `spring.cloud.gcp.credentials.encoded-key` tồn tại cho trường hợp cần cấu hình credential riêng, nhưng không nên dùng làm lựa chọn mặc định trên Google Cloud runtime. Nếu tổ chức bắt buộc dùng key, phải quản lý qua secret store, giới hạn IAM, bảo vệ file và có quy trình rotation/thu hồi.

### 5.3. IAM tối thiểu cho Cloud Storage

Một số predefined roles thường gặp:

| IAM role | Quyền khái quát | Use case |
| --- | --- | --- |
| `roles/storage.objectViewer` | Đọc object và metadata | Service chỉ tải tài liệu |
| `roles/storage.objectCreator` | Tạo object mới; không mặc nhiên cho phép đọc, xóa hoặc ghi đè object hiện có | Service chỉ upload object mới |
| `roles/storage.objectUser` | Các thao tác object rộng hơn như tạo, đọc, cập nhật và xóa theo định nghĩa role | Service quản lý vòng đời object |
| `roles/storage.objectAdmin` | Quản trị object trong phạm vi được cấp | Công cụ vận hành object |
| `roles/storage.admin` | Quản trị rộng bucket và object | Nhóm quản trị hạ tầng, không phải mặc định cho runtime |

Gán role ở bucket scope khi chỉ cần một bucket; tránh cấp `roles/storage.admin` ở project scope cho ứng dụng chỉ upload. Với nhiều tenant, prefix trong object name không tự tạo ranh giới IAM. Cần thiết kế resource separation, IAM condition hoặc adapter authorization phù hợp.

### 5.4. Cấu hình local và production

Ví dụ cấu hình không chứa key:

~~~yaml
spring:
  cloud:
    gcp:
      project-id: ${GOOGLE_CLOUD_PROJECT}

app:
  storage:
    bucket: ${APP_DOCUMENT_BUCKET}
~~~

Local có thể dùng ADC từ developer; production dùng service account/workload identity gắn với workload. Không đặt JSON private key vào file YAML được commit.

## 6. Dùng Cloud Storage Java client trực tiếp

### 6.1. Các lớp chính

| Lớp | Vai trò |
| --- | --- |
| `Storage` | Client/service interface thao tác Cloud Storage |
| `BlobId` | Định danh bucket, object name và có thể cả generation |
| `BlobInfo` | Mô tả object khi tạo/cập nhật, gồm content type và metadata |
| `Blob` | Object cùng thông tin metadata hiện có |
| `Bucket` | Thông tin bucket |
| `ReadChannel` | Đọc object theo dạng channel, phù hợp streaming/seek |
| `WriteChannel` | Ghi object theo dạng channel |

`Storage` là client đồng bộ của Java library. Nếu gọi trong controller Spring MVC, lời gọi sẽ block thread cho tới khi operation hoàn tất. Không gọi blocking storage API trực tiếp trên event loop của Spring WebFlux; nếu dùng reactive pipeline, hãy cô lập I/O blocking trên scheduler phù hợp hoặc chọn thiết kế client/adapter tương thích.

### 6.2. Tạo object mới

Ví dụ upload nội dung nhỏ:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.springframework.stereotype.Service;

@Service
public class GcsDocumentClient {

    private final Storage storage;

    public GcsDocumentClient(Storage storage) {
        this.storage = storage;
    }

    public long createText(
            String bucket,
            String objectName,
            String content) {

        BlobInfo info = BlobInfo.newBuilder(
                        BlobId.of(bucket, objectName))
                .setContentType("text/plain; charset=utf-8")
                .setMetadata(Map.of(
                        "source-system", "document-api",
                        "classification", "internal"))
                .build();

        Blob created = storage.create(
                info,
                content.getBytes(StandardCharsets.UTF_8),
                Storage.BlobTargetOption.doesNotExist());

        return created.getGeneration();
    }
}
~~~

`doesNotExist()` là precondition: chỉ tạo object khi chưa có live object cùng tên. Nếu object đã tồn tại, thao tác thất bại thay vì âm thầm ghi đè. Đây là cách tránh race condition giữa bước kiểm tra tồn tại và bước upload.

Ví dụ dùng `byte[]` phù hợp với payload nhỏ. Không đọc file vài trăm MB vào heap chỉ để truyền vào `storage.create(...)`; dùng streaming hoặc resumable upload cho file lớn.

### 6.3. Đọc object và metadata

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;

public class GcsObjectReader {

    private final Storage storage;

    public GcsObjectReader(Storage storage) {
        this.storage = storage;
    }

    public Blob describe(String bucket, String objectName) {
        Blob blob = storage.get(BlobId.of(bucket, objectName));
        if (blob == null) {
            throw new IllegalArgumentException("Object không tồn tại");
        }
        return blob;
    }
}
~~~

`storage.get(...)` đọc metadata object; `Blob` có thể cung cấp content type, size, generation, metageneration, custom metadata và các thuộc tính khác. Nội dung bytes là một luồng riêng; không nhầm việc lấy metadata với việc tải toàn bộ object.

### 6.4. Đọc nội dung theo streaming

~~~java
import com.google.cloud.ReadChannel;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.channels.Channels;

public byte[] downloadSmallObject(
        Storage storage,
        String bucket,
        String objectName) throws IOException {

    BlobId id = BlobId.of(bucket, objectName);

    try (ReadChannel channel = storage.reader(id);
         InputStream input = Channels.newInputStream(channel);
         ByteArrayOutputStream output = new ByteArrayOutputStream()) {

        input.transferTo(output);
        return output.toByteArray();
    }
}
~~~

Tên hàm nhấn mạnh `SmallObject`: ví dụ gom toàn bộ bytes vào bộ nhớ để đơn giản. Với object lớn, chuyển trực tiếp `InputStream` tới file hoặc HTTP response theo cơ chế streaming và giới hạn kích thước, không dùng `ByteArrayOutputStream` không giới hạn.

### 6.5. Ghi file lớn qua WriteChannel

~~~java
import com.google.cloud.WriteChannel;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.io.IOException;
import java.io.InputStream;
import java.nio.channels.Channels;
import java.io.OutputStream;

public void uploadStream(
        Storage storage,
        BlobInfo info,
        InputStream source) throws IOException {

    try (WriteChannel channel = storage.writer(info);
         OutputStream output = Channels.newOutputStream(channel)) {
        source.transferTo(output);
    }
}
~~~

`WriteChannel` giúp truyền dữ liệu theo luồng thay vì giữ toàn bộ object trong heap. Trong production cần xem cấu hình chunk size, retry, resumable upload, checksum và cách xử lý stream nguồn có thể đọc lại hay không. Đóng channel/output stream đúng cách để hoàn tất upload và giải phóng tài nguyên.

### 6.6. Cập nhật metadata

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.util.Map;

public Blob updateClassification(
        Storage storage,
        String bucket,
        String objectName,
        String classification) {

    Blob current = storage.get(
            com.google.cloud.storage.BlobId.of(bucket, objectName));

    if (current == null) {
        throw new IllegalArgumentException("Object không tồn tại");
    }

    Map<String, String> metadata = current.getMetadata() == null
            ? new java.util.HashMap<>()
            : new java.util.HashMap<>(current.getMetadata());

    metadata.put("classification", classification);

    BlobInfo updatedInfo = current.toBuilder()
            .setMetadata(metadata)
            .build();

    return storage.update(
            updatedInfo,
            Storage.BlobTargetOption.metagenerationMatch(
                    current.getMetageneration()));
}
~~~

Ví dụ đọc metadata hiện tại, hợp nhất key rồi cập nhật với `metagenerationMatch`. Nếu một worker khác thay metadata sau lần đọc, precondition thất bại; ứng dụng phải đọc lại và hợp nhất thay vì ghi đè vô điều kiện. Trong mã thực tế nên chuyển lỗi precondition thành conflict/retry có kiểm soát.

## 7. Spring Resource abstraction cho GCS

### 7.1. Resource là gì?

Spring `Resource` là abstraction biểu diễn nguồn dữ liệu. Các implementation phổ biến gồm:

- `ClassPathResource`: file trong classpath.
- `FileSystemResource`: file trên filesystem.
- `UrlResource`: tài nguyên qua URL.
- `ByteArrayResource`: nội dung từ byte array.
- `GoogleStorageResource`: object hoặc bucket Cloud Storage qua `gs://`.

`Resource` cung cấp các thao tác chung như `getInputStream()`, `exists()`, `isReadable()`, `contentLength()` và `getFilename()`. `WritableResource` mở rộng `Resource` với `getOutputStream()` để ghi dữ liệu.

**GCS object không phải file local.** Không giả định `getFile()` trả về một `java.io.File` hoặc `Path` có thể truyền cho `Files.*`. Hãy dùng stream; các method kiểm tra như `exists()` và `contentLength()` có thể phát sinh request mạng và cần IAM permission.

### 7.2. URI gs://bucket/object

Spring Framework on Google Cloud hỗ trợ protocol `gs://` để biểu diễn object:

~~~text
gs://training-documents-dev/reports/2026/summary.pdf
~~~

Khi starter Storage được cấu hình, resource resolver nhận diện scheme `gs` và tạo `GoogleStorageResource`. URI này là định danh Cloud Storage, không phải URL tải công khai.

`GoogleStorageResource` triển khai Spring `WritableResource` và có thể đại diện bucket hoặc blob. Khi URI trỏ đến object, có thể truy cập `Blob` để đọc metadata hoặc gọi các API GCS chuyên biệt.

### 7.3. Inject Resource bằng @Value

Ví dụ cấu hình:

~~~yaml
app:
  gcs:
    bucket: training-documents-dev
    object: reports/2026/summary.pdf
~~~

Inject resource:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Component;

@Component
public class ReportResource {

    private final Resource resource;

    public ReportResource(
            @Value("gs://${app.gcs.bucket}/${app.gcs.object}")
            Resource resource) {
        this.resource = resource;
    }

    public Resource getResource() {
        return resource;
    }
}
~~~

Spring resolve property placeholder trước, sau đó sử dụng resource protocol resolver cho scheme `gs`. Cách này phù hợp khi bucket/object là cấu hình cố định của một bean. Nếu đường dẫn thay đổi theo request/tenant, không nên tạo một bean `@Value` cho từng object; hãy dùng `ResourceLoader` hoặc Storage client với input đã được validate.

### 7.4. Lấy Resource động qua ApplicationContext

Có thể dùng `ResourceLoader`/`ApplicationContext` khi object name được quyết định lúc runtime:

~~~java
import org.springframework.context.ApplicationContext;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Component;

@Component
public class DynamicGcsResourceFactory {

    private final ApplicationContext applicationContext;

    public DynamicGcsResourceFactory(
            ApplicationContext applicationContext) {
        this.applicationContext = applicationContext;
    }

    public Resource get(String bucket, String objectName) {
        validate(bucket, objectName);
        String location = "gs://" + bucket + "/" + objectName;
        return applicationContext.getResource(location);
    }

    private void validate(String bucket, String objectName) {
        if (bucket == null || bucket.isBlank()
                || objectName == null || objectName.isBlank()) {
            throw new IllegalArgumentException("Bucket/object name không hợp lệ");
        }
        if (objectName.startsWith("/") || objectName.contains("../")) {
            throw new IllegalArgumentException("Object name không hợp lệ");
        }
    }
}
~~~

Ví dụ validation chỉ là bước cơ bản, không thay thế quy tắc naming và authorization đầy đủ. Không nối trực tiếp URI từ input không tin cậy rồi cho phép truy cập bucket tùy ý. Ứng dụng cần ràng buộc bucket/prefix theo tenant và quyền nghiệp vụ.

### 7.5. Đọc nội dung qua Resource

~~~java
import java.io.IOException;
import java.io.InputStream;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Service;

@Service
public class GcsResourceReader {

    public byte[] readSmall(Resource resource) throws IOException {
        if (!resource.exists() || !resource.isReadable()) {
            throw new IllegalStateException("Resource không đọc được");
        }

        try (InputStream input = resource.getInputStream()) {
            return input.readAllBytes();
        }
    }
}
~~~

Ví dụ dùng `readAllBytes()` cho tài liệu nhỏ. Với object lớn, hãy stream tới nơi tiêu thụ và giới hạn kích thước. `exists()`/`isReadable()` có thể thực hiện truy vấn Cloud Storage; không gọi lặp lại nhiều lần trong một request nếu đã có kết quả metadata phù hợp.

### 7.6. Ghi nội dung qua WritableResource

~~~java
import java.io.IOException;
import java.io.OutputStream;
import org.springframework.core.io.Resource;
import org.springframework.core.io.WritableResource;
import org.springframework.stereotype.Service;

@Service
public class GcsResourceWriter {

    public void write(Resource resource, byte[] content) throws IOException {
        if (!(resource instanceof WritableResource writable)) {
            throw new IllegalArgumentException(
                    "Resource không hỗ trợ ghi");
        }

        try (OutputStream output = writable.getOutputStream()) {
            output.write(content);
        }
    }
}
~~~

Không phải mọi `Resource` đều ghi được; phải kiểm tra `WritableResource`. Đóng `OutputStream` đúng cách để hoàn tất thao tác ghi. Hãy kiểm tra hành vi auto-create, overwrite và metadata theo phiên bản Spring Framework on Google Cloud đang sử dụng.

## 8. GoogleStorageResource: khi cần truy cập API GCS từ Resource

Nếu cần thao tác chuyên biệt hơn qua resource URI, có thể cast sang `GoogleStorageResource`:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.spring.storage.GoogleStorageResource;
import org.springframework.core.io.Resource;

public Blob getBlobMetadata(Resource resource) {
    if (!(resource instanceof GoogleStorageResource gcsResource)) {
        throw new IllegalArgumentException(
                "Resource không phải GoogleStorageResource");
    }

    Blob blob = gcsResource.getBlob();
    if (blob == null) {
        throw new IllegalStateException("Object không tồn tại");
    }
    return blob;
}
~~~

`GoogleStorageResource` thuộc package `com.google.cloud.spring.storage`. API và constructor cần đối chiếu với version BOM của dự án; không tự tạo object bằng constructor từ release khác.

### 8.1. Đọc metadata

`getBlob()` trả thông tin object nếu resource trỏ tới blob đã tồn tại. Có thể lấy:

- Content type.
- Size.
- Generation và metageneration.
- Custom metadata.
- Storage class và timestamps theo API.

Không gọi `getBlob()` với resource chỉ đại diện bucket rồi giả định nó là object. Phân biệt URI bucket và URI object.

### 8.2. Cập nhật content type

Ví dụ theo API `GoogleStorageResource`:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.spring.storage.GoogleStorageResource;
import org.springframework.core.io.Resource;

public void setContentType(Resource resource, String contentType) {
    if (!(resource instanceof GoogleStorageResource gcsResource)) {
        throw new IllegalArgumentException("Resource không phải GCS resource");
    }

    Blob current = gcsResource.getBlob();
    if (current == null) {
        throw new IllegalStateException("Object không tồn tại");
    }

    current.toBuilder()
            .setContentType(contentType)
            .build()
            .update();
}
~~~

Thao tác này cập nhật metadata trên object thật. Nếu nhiều worker có thể cùng cập nhật metadata, dùng Storage API và metageneration precondition để bảo vệ cập nhật; không giả định mọi helper method của Resource tự áp điều kiện nghiệp vụ bạn cần.

### 8.3. getURI và getURL

Với `GoogleStorageResource`, `getURI()` biểu diễn địa chỉ theo scheme `gs://`. `getURL()` có thể trả về URL self-link của bucket/blob theo phiên bản thư viện; hai giá trị không nên được coi là đồng nghĩa.

Nếu API nghiệp vụ cần định danh GCS, dùng bucket + object name hoặc URI `gs://`. Nếu cần URL cho browser, phải thiết kế cơ chế truy cập riêng như signed URL; không gửi selfLink hay URI `gs://` cho người dùng như thể đó là link tải công khai.

### 8.4. Signed URL

`GoogleStorageResource` có thể hỗ trợ tạo signed URL trong những điều kiện phù hợp. Tạo signed URL cần credential có khả năng ký (thường là service account credential hoặc cơ chế signing được hỗ trợ). ADC dựa trên user token hoặc workload identity không phải mọi trường hợp đều có private key local để ký trực tiếp.

Signed URL là bearer token có thời hạn: người sở hữu URL có thể thực hiện thao tác được ký trong thời gian hiệu lực. Không ghi URL vào log công khai, không đặt thời hạn quá dài và không cho client yêu cầu ký object tùy ý ngoài phạm vi authorization của họ.

## 9. Kiểm soát tự động tạo bucket và object

Spring Framework on Google Cloud Storage có property `spring.cloud.gcp.storage.auto-create-files`. Theo tài liệu của release, property này điều khiển việc tự tạo file/object và bucket khi ghi vào resource chưa tồn tại; giá trị mặc định được công bố là `true` ở cấu hình hiện hành.

Ví dụ cấu hình tường minh:

~~~yaml
spring:
  cloud:
    gcp:
      storage:
        enabled: true
        auto-create-files: false
~~~

Khi tắt auto-create, ứng dụng cần provision bucket/object theo quy trình hạ tầng và bảo đảm bucket tồn tại trước khi ghi. Đây thường là lựa chọn dễ kiểm soát hơn cho production vì việc tạo bucket có thể ảnh hưởng location, storage class, UBLA, public access prevention, retention, lifecycle và billing.

Nếu giữ auto-create cho local/dev, cần kiểm soát quyền IAM và đặt tên tài nguyên riêng. Không cấp quyền quản trị bucket rộng cho runtime chỉ để starter tự tạo bucket trong production.

## 10. Chọn Resource hay Storage API?

### 10.1. Khi Spring Resource phù hợp

Dùng `Resource` khi:

- Một API Spring nhận `Resource`, `InputStreamSource` hoặc `WritableResource`.
- Muốn inject URI `gs://...` qua `@Value`.
- Đọc template, file cấu hình, nội dung nhỏ hoặc dữ liệu đầu vào từ GCS.
- Muốn viết adapter đơn giản có cùng giao diện với file/classpath resource.
- Không cần kiểm soát sâu generation, metadata concurrency hoặc operation đặc thù.

Ví dụ service có thể nhận `Resource` từ nhiều nguồn mà không cần biết chi tiết GCS:

~~~java
public String loadTemplate(Resource template) throws IOException {
    try (var reader = new java.io.BufferedReader(
            new java.io.InputStreamReader(
                    template.getInputStream(),
                    java.nio.charset.StandardCharsets.UTF_8))) {
        return reader.lines()
                .collect(java.util.stream.Collectors.joining("\n"));
    }
}
~~~

### 10.2. Khi Storage client phù hợp

Dùng `Storage` client khi cần:

- Upload/download file lớn bằng `ReadChannel`/`WriteChannel`.
- Generation/metageneration preconditions.
- Object versioning và đọc generation cụ thể.
- Cập nhật custom metadata có kiểm soát.
- List object theo prefix/delimiter.
- Bucket lifecycle, IAM-related metadata hoặc các operation bucket.
- Signed URL, rewrite/copy, compose hoặc tính năng GCS chuyên biệt.
- Kiểm soát retry, checksum và request option.

### 10.3. Quy tắc kết hợp

| Nhu cầu | Cách ưu tiên | Lý do |
| --- | --- | --- |
| Đọc một template cố định | `Resource` | Code gọn, tương thích Spring |
| Ghi nội dung nhỏ vào object đã xác định | `WritableResource` hoặc `Storage` | Chọn theo yêu cầu precondition/metadata |
| Upload file lớn | `Storage.writer`/streaming API | Kiểm soát stream và tài nguyên tốt hơn |
| Tạo object chỉ khi chưa tồn tại | `Storage` với precondition | Kiểm soát race condition |
| Cập nhật metadata có concurrency | `Storage` với metageneration precondition | Resource helper không thể hiện đủ điều kiện |
| List object theo prefix | `Storage.list(...)` | API trực tiếp và có pagination |
| Tích hợp với API Spring nhận Resource | `Resource` | Dùng abstraction thống nhất |

Không ép mọi thao tác qua Resource chỉ vì đã có starter. Abstraction có ích khi nó đơn giản hóa code; khi cần semantics GCS cụ thể, hãy dùng client API trực tiếp.

## 11. IAM, bucket policy và cấu hình production

### 11.1. Quyền của workload

Ứng dụng cần service account hoặc workload identity có IAM role phù hợp trên bucket/project. Ví dụ:

- Service chỉ đọc tài liệu: `roles/storage.objectViewer`.
- Service chỉ tạo object mới: `roles/storage.objectCreator`.
- Service cần đọc và cập nhật/xóa object: cân nhắc `roles/storage.objectUser` hoặc custom role đúng phạm vi.
- Công cụ quản trị bucket: role quản trị phù hợp, tách khỏi runtime service.

Quyền đọc object không đồng nghĩa quyền list bucket hoặc tạo bucket. Kiểm tra operation thực tế của code và cấp quyền tối thiểu. Khi `Resource.exists()` hoặc `contentLength()` gọi metadata API, principal cần quyền đọc metadata tương ứng.

### 11.2. Không dựa vào object name để cách ly tenant

Nếu tất cả tenant nằm trong cùng bucket, prefix như `tenant-a/` chỉ là quy ước tên object. Nếu service account có quyền đọc toàn bucket, việc code chỉ truyền prefix `tenant-a/` không phải ranh giới bảo mật. Cần authorization tại ứng dụng, IAM condition phù hợp hoặc tách bucket/project khi yêu cầu cô lập cao.

### 11.3. UBLA và Public Access Prevention

Với bucket mới, cân nhắc Uniform bucket-level access (UBLA) để quản lý quyền bằng IAM thay cho ACL object/bucket. Public Access Prevention giúp ngăn việc cấp quyền public ngoài ý muốn. Đây là hai cấu hình khác nhau, có thể được sử dụng cùng nhau theo chính sách tổ chức.

Không biến bucket thành public để giải quyết lỗi tải file. Nếu người dùng cần tải nội dung, có thể cung cấp signed URL có thời hạn sau khi backend kiểm tra quyền nghiệp vụ.

### 11.4. Không để secret trong metadata hoặc URL log

Không lưu password, access token, session token hoặc dữ liệu cá nhân nhạy cảm trong custom metadata. Metadata có thể được đọc bởi principal được phép xem object. Signed URL cũng cần được xem như secret trong thời hạn hiệu lực.

## 12. Kiểm thử tích hợp

### 12.1. Unit test

Unit test tập trung vào logic nghiệp vụ và adapter:

- Validate bucket/object name.
- Mapping document ID thành object name.
- Chọn content type và metadata.
- Xử lý object not found.
- Xử lý lỗi permission/precondition.
- Đảm bảo stream luôn được đóng khi có lỗi.

Mock `Storage` hoặc tạo fake adapter để không cần gọi Google Cloud thật trong unit test.

### 12.2. Integration test trên project riêng

Cloud Storage Java client cần test integration với project/bucket test riêng nếu muốn xác minh semantics thật:

1. Dùng service account hoặc workload identity test có quyền tối thiểu.
2. Tạo bucket theo quy trình provisioning riêng, tránh để application runtime tự tạo bucket không kiểm soát.
3. Đọc và ghi object qua `Storage` client.
4. Đọc object qua Spring `Resource` bằng URI `gs://...`.
5. Ghi qua `WritableResource` và xác minh nội dung qua Storage client.
6. Cập nhật metadata, kiểm tra generation/metageneration.
7. Thử thiếu quyền và object không tồn tại.
8. Dọn object/bucket theo quy trình test, không xóa bucket chia sẻ.

### 12.3. Fake server/emulator

Có thể dùng fake GCS server hoặc emulator bên thứ ba để kiểm thử một số request/object API cục bộ. Nhưng phải xác minh rõ mức độ hỗ trợ và giới hạn của emulator. Không mặc định mọi tính năng như IAM, signed URL, retention, HNS, soft delete, lifecycle hoặc generation preconditions đều được mô phỏng giống production.

Đối với các thuộc tính quan trọng, cần một integration test nhỏ trên project GCP test để kiểm chứng dịch vụ thật. Không dùng project production cho bài test có thể tạo generation, thay metadata hoặc xóa object.

### 12.4. Kiểm thử Spring Resource

Một integration test có thể xác minh cả hai abstraction:

~~~java
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class GcsResourceIntegrationTest {

    @Autowired
    ResourceLoader resourceLoader;

    @Test
    void shouldReadObjectThroughSpringResource() throws Exception {
        Resource resource = resourceLoader.getResource(
                "gs://training-documents-test/fixtures/hello.txt");

        try (InputStream input = resource.getInputStream()) {
            String content = new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8);

            assertEquals("hello from gcs", content);
        }
    }
}
~~~

Ví dụ giả định bucket/object fixture đã tồn tại và Spring Storage starter đã đăng ký protocol resolver. Test cần chạy với ADC/IAM test hợp lệ; không đưa service account key production vào test fixture.

### 12.5. Kiểm tra khác biệt giữa Resource và Storage

Nên có test xác nhận:

- `Resource.exists()` cho object hiện hữu và không hiện hữu.
- `Resource.getInputStream()` đọc đúng bytes.
- `WritableResource.getOutputStream()` ghi đúng object.
- Storage client đọc lại content type và metadata.
- Object chỉ tạo khi precondition phù hợp.
- Permission denied được ánh xạ thành lỗi ứng dụng rõ ràng.

Không chỉ kiểm tra `resource != null`: việc tạo handle `gs://...` không chứng minh object tồn tại hoặc principal có quyền truy cập.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
| --- | --- | --- |
| Không resolve được `gs://...` | Chưa có starter Storage hoặc protocol resolver không được đăng ký | Kiểm tra dependency, auto-configuration và ApplicationContext |
| `NoSuchBeanDefinitionException` cho `Storage` | Starter thiếu, bị exclude hoặc cấu hình disabled | Kiểm tra `spring-cloud-gcp-starter-storage`, property và BOM |
| `403 Forbidden` | ADC principal thiếu IAM permission hoặc bucket policy chặn | Xác minh principal, project/bucket scope và role |
| `401 Unauthorized` | ADC/token không hợp lệ hoặc credential hết hạn | Kiểm tra nguồn ADC và runtime identity |
| `Resource` tạo được nhưng `exists()` false | URI đúng cú pháp nhưng object không tồn tại hoặc sai bucket/key | Đối chiếu bucket/object name và project |
| `getFile()` ném exception | GCS Resource không phải file local | Dùng `getInputStream()`/`getOutputStream()` |
| Ghi object vô tình tạo bucket | `auto-create-files` bật và resource chưa tồn tại | Tắt auto-create nếu cần provision tường minh |
| Metadata không cập nhật như mong muốn | Chỉ cập nhật một phần metadata hoặc thiếu precondition | Đọc Blob, merge metadata và dùng metageneration condition |
| Java dùng ADC khác gcloud CLI | Đăng nhập gcloud user nhưng chưa tạo ADC hoặc workload identity khác | Kiểm tra ADC source và principal của Java process |
| Signed URL không tạo được | Credential hiện tại không hỗ trợ signing | Dùng cơ chế service account signing được hỗ trợ |
| Upload lớn làm tăng heap | Đọc toàn bộ object vào `byte[]` | Chuyển sang channel/streaming/resumable upload |
| Test local pass nhưng GCP thật lỗi | Emulator không mô phỏng IAM hoặc service semantics | Chạy smoke test trên project GCP test |

### 13.1. Chẩn đoán theo thứ tự

1. **Dependency:** starter Storage và Google Cloud client version có được resolve đúng không?
2. **Auto-configuration:** `Storage` bean và `gs://` protocol resolver đã được đăng ký chưa?
3. **Project:** ứng dụng đang nhắm project nào?
4. **Credentials:** Java process đang dùng ADC/service account/workload identity nào?
5. **IAM:** principal có đúng quyền trên bucket/object không?
6. **Resource path:** bucket và object name có chính xác không?
7. **Lifecycle:** bucket/object đã provision chưa; auto-create có được bật không?
8. **Stream:** InputStream/OutputStream đã đóng, kích thước dữ liệu có phù hợp không?
9. **Concurrency:** generation/metageneration precondition có khớp với phiên bản hiện tại không?

Không xử lý 403 bằng cách cấp `roles/storage.admin` ngay. Hãy tìm permission cụ thể mà operation yêu cầu.

## 14. Thiết kế adapter Spring Boot có thể kiểm thử

Controller và domain service nên phụ thuộc interface nghiệp vụ thay vì `Blob`, `Storage` hoặc `GoogleStorageResource`:

~~~java
import java.io.InputStream;

public interface DocumentStorage {
    StoredDocument upload(
            String documentId,
            InputStream content,
            String contentType);

    InputStream open(String documentId);
}

public record StoredDocument(
        String bucket,
        String objectName,
        long generation,
        String contentType,
        long size) {}
~~~

Một adapter GCS triển khai interface bằng `Storage` client; adapter khác có thể dùng `ResourceLoader` nếu use case chủ yếu đọc resource. Unit test có thể fake `DocumentStorage`, còn integration test xác minh adapter GCS trên bucket test.

Thiết kế interface nên mô tả đúng nghiệp vụ. Nếu ứng dụng cần version token, precondition, metadata hoặc signed URL, hãy đưa các khái niệm cần thiết vào contract một cách có chủ đích thay vì che mất semantics quan trọng trong một interface quá chung.

## 15. Bài tập thực hành tổng hợp

**Bối cảnh:** Một ứng dụng Spring Boot quản lý tài liệu đào tạo. Tài liệu mẫu được lưu ở bucket `training-documents-dev` với object name `lessons/spring-cloud/intro.md`. Một service cần đọc template khi tạo khóa học; service khác upload bản xuất PDF sau khi người dùng yêu cầu.

### Nhiệm vụ A — Cấu hình client

1. Thêm `spring-cloud-gcp-dependencies` BOM và `spring-cloud-gcp-starter-storage`.
2. Giải thích vì sao starter có thể tự tạo `Storage` bean.
3. Cấu hình project ID và bucket qua environment/property.
4. Thiết lập ADC cho local và workload identity cho môi trường triển khai.
5. Nêu IAM role tối thiểu cho service đọc template và service upload PDF.

### Nhiệm vụ B — Dùng Spring Resource

1. Inject `gs://training-documents-dev/lessons/spring-cloud/intro.md` bằng `@Value`.
2. Đọc nội dung qua `getInputStream()` và đóng stream.
3. Dùng `ResourceLoader` khi object name được quyết định theo request.
4. Viết qua `WritableResource` và giải thích khi nào cần cast.
5. Giải thích vì sao `getFile()` không phù hợp với object ở Cloud Storage.

### Nhiệm vụ C — Dùng Storage API

1. Tạo `BlobInfo` với content type `application/pdf` và custom metadata.
2. Upload object chỉ khi chưa tồn tại bằng `doesNotExist()`.
3. Đọc generation và metadata sau khi upload.
4. Cập nhật metadata bằng metageneration precondition.
5. Chọn `WriteChannel` cho file lớn và mô tả cách đóng stream.

### Nhiệm vụ D — Kiểm thử

- Unit test service với fake `DocumentStorage`.
- Integration test `Storage` bean và `gs://` Resource trên bucket test.
- Kiểm tra IAM permission denied.
- Kiểm tra auto-create-files bật/tắt.
- Kiểm tra object không tồn tại và generation conflict.
- So sánh kết quả emulator với smoke test trên GCP test project.

**Tiêu chí đạt:** Người học biết lúc nào dùng `Storage`, lúc nào dùng Spring Resource; cấu hình đúng starter/ADC/IAM; đọc/ghi stream an toàn; xử lý metadata/precondition; và kiểm thử được cả bean auto-configuration lẫn object thật.

## 16. So sánh với AWS S3 và Azure Blob Storage

| Nhu cầu | Google Cloud Storage | Amazon S3 | Azure Blob Storage |
| --- | --- | --- | --- |
| Java service client | `Storage` từ `google-cloud-storage` | `S3Client` từ AWS SDK v2 | `BlobServiceClient`/`BlobContainerClient` từ Azure SDK |
| Spring resource abstraction | `GoogleStorageResource` qua `gs://` | Không mặc định dùng cùng GCS `gs://` Resource; thường tạo adapter riêng | Có thể xây adapter `Resource` trên Azure Blob client |
| Credentials | ADC, service account, Workload Identity | IAM role, AWS SDK credential provider chain | Managed Identity, Entra ID credential chain |
| Resource identifier | `gs://bucket/object` | Bucket + object key / S3 URI | Storage account + container + blob name |
| Version/concurrency | Generation, metageneration, preconditions | Version ID, ETag và conditional request | Version ID, ETag, lease và conditional headers |
| Integration testing | Project/bucket GCP test hoặc emulator có giới hạn | AWS sandbox, LocalStack | Azure test account hoặc Azurite cho Storage |

Điểm chung là cần client SDK, identity, quyền tối thiểu và streaming. Điểm khác là cách biểu diễn resource, version token, conditional operation và Spring integration. Không dùng một `Resource` implementation của GCS để giả định nó hoạt động với S3/Azure; nếu cần abstraction đa cloud, xây interface nghiệp vụ và adapter riêng theo từng provider.

## 17. Ghi nhớ

- **`Storage` client** là API trực tiếp để quản lý bucket/object; **`Resource`** là abstraction Spring để đọc nguồn dữ liệu; **`WritableResource`** bổ sung khả năng ghi.
- Spring Framework on Google Cloud Storage starter auto-configure `Storage` bean và hỗ trợ resource URI `gs://bucket/object`.
- `@Value("gs://...") Resource` phù hợp với resource được cấu hình cố định; `ResourceLoader` phù hợp khi đường dẫn được xác định lúc runtime.
- `GoogleStorageResource` cho phép truy cập `Blob` và các API GCS chuyên biệt; dùng Storage client trực tiếp khi cần generation, precondition, metadata hoặc streaming nâng cao.
- ADC và workload identity giúp tránh lưu service account key dài hạn trong source/image.
- Không giả định GCS Resource là file local; dùng stream và đóng stream đúng cách.
- Kiểm soát `auto-create-files`, IAM và project/bucket để tránh tự tạo tài nguyên ngoài ý muốn.
- Kết hợp unit test, integration test và smoke test trên project riêng để kiểm chứng cả Spring wiring lẫn quyền GCP thật.

### Tài liệu tham khảo

- [Spring Framework on Google Cloud — Cloud Storage](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/#cloud-storage)
- [GoogleStorageResource API](https://googleapis.dev/java/spring-cloud-gcp/latest/com/google/cloud/spring/storage/GoogleStorageResource.html)
- [Google Cloud Storage Java client](https://cloud.google.com/java/docs/reference/google-cloud-storage/latest/overview)
- [Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials)
