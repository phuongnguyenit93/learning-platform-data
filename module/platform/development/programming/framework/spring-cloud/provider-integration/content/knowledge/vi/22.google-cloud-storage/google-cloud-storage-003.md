# Thao tác tải lên, tải xuống, liệt kê và xóa đối tượng Google Cloud Storage

## 1. Bối cảnh và mục tiêu

Một ứng dụng Spring Boot thường phải lưu file người dùng, tải tài liệu theo yêu cầu, liệt kê file trong một phạm vi nghiệp vụ và xóa dữ liệu khi hết thời hạn lưu giữ. Trên Google Cloud, **Cloud Storage** cung cấp các thao tác này thông qua bucket và object. Java client library cung cấp interface **Storage** cùng các kiểu **BlobInfo**, **BlobId** và **Blob** để ứng dụng thực hiện các thao tác với object.

Bài học thuộc chương **Google Cloud Storage** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**. Module hướng tới thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng; học cấu hình danh tính và quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider. Bài này tập trung vào vòng đời thao tác object: **upload, download, list và delete** bằng Google Cloud Storage Java client trong ứng dụng Spring Boot.

Sau bài học, bạn có thể:

- Cấu hình Google Cloud Storage Java client và inject **Storage** vào Spring service.
- Upload nội dung nhỏ bằng **Storage.create** và file lớn bằng **WriteChannel**.
- Tải object về file hoặc truyền dữ liệu theo luồng bằng **ReadChannel**.
- Liệt kê object theo prefix, phân trang và xử lý danh sách lớn.
- Xóa object có kiểm soát bằng generation precondition.
- Hiểu quyền IAM tương ứng với create/get/list/delete và tránh cấp quyền quá rộng.
- Xử lý lỗi 403, 404, 412, timeout và lỗi mạng theo đúng ngữ nghĩa.
- Viết adapter và integration test an toàn cho môi trường dev/test/production.

> **Phạm vi phiên bản:** Ví dụ dùng Google Cloud Storage Java client (artifact **com.google.cloud:google-cloud-storage**) và phong cách tích hợp Spring Boot. Hãy quản lý phiên bản bằng BOM phù hợp với baseline Java/Spring của dự án. API, transport và một số tùy chọn có thể thay đổi theo release; đối chiếu Javadoc của đúng phiên bản đã resolve. Bucket, project và object name trong ví dụ là dữ liệu minh họa.

## 2. Mô hình thao tác object

Cloud Storage lưu dữ liệu trong bucket. Một object được xác định bởi bucket và object name; generation nhận diện phiên bản dữ liệu cụ thể. Khi thực hiện thao tác, cần phân biệt **metadata của object** với **bytes của object**.

~~~mermaid
flowchart TD
    APP["Spring Boot service"] --> CLIENT["Storage Java client"]
    CLIENT --> CREATE["Upload / create"]
    CLIENT --> READ["Download / read"]
    CLIENT --> LIST["List by bucket / prefix"]
    CLIENT --> DELETE["Delete object"]
    CREATE --> GCS["Google Cloud Storage"]
    READ --> GCS
    LIST --> GCS
    DELETE --> GCS
    IAM["ADC / workload identity + IAM"] -. "Xác thực và cấp quyền" .-> CLIENT
~~~

| Thành phần | Vai trò |
| --- | --- |
| Project | Chứa bucket, IAM, billing và quota |
| Bucket | Container chứa object |
| Object name | Tên định danh object trong bucket |
| BlobId | Định danh bucket/object, có thể kèm generation |
| BlobInfo | Metadata mô tả object khi tạo hoặc cập nhật |
| Blob | Snapshot metadata của object hiện có và các thao tác liên quan |
| Storage | Client thực hiện RPC tới Cloud Storage |
| ReadChannel | Kênh đọc bytes theo luồng |
| WriteChannel | Kênh ghi bytes theo luồng |

URI **gs://training-documents-dev/reports/2026/report.pdf** chỉ mô tả vị trí object. Nó không cấp quyền truy cập và không đồng nghĩa object có URL HTTP public.

### 2.1. Chọn API theo kích thước và use case

| Nhu cầu | API thường dùng | Đặc điểm |
| --- | --- | --- |
| Upload nội dung nhỏ có sẵn trong bộ nhớ | Storage.create với byte array | Đơn giản; toàn bộ nội dung đã nằm trong byte array |
| Upload file lớn/stream | Storage.writer với BlobWriteOption | Ghi qua WriteChannel, phù hợp streaming/resumable upload |
| Đọc metadata | Storage.get với BlobId | Lấy Blob; không tự tải toàn bộ bytes |
| Download về file | Blob.downloadTo hoặc Storage.downloadTo | SDK quản lý thao tác tải |
| Download theo luồng | Storage.reader với BlobId | Dùng ReadChannel, chủ động truyền dữ liệu |
| Liệt kê object | Storage.list với BlobListOption | Trả về Page<Blob>, có prefix và pagination |
| Xóa object | Storage.delete với BlobSourceOption | Có thể dùng generation precondition |

**Không dùng byte array cho file lớn chỉ vì API ngắn hơn.** Việc gom toàn bộ file vào heap có thể làm tăng memory pressure, gây GC dài hoặc OutOfMemoryError khi nhiều request upload/download đồng thời.

## 3. Chuẩn bị dependency, project và credentials

### 3.1. Java client dependency

Nếu dự án dùng Maven và đã import BOM quản lý Google Cloud libraries:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>google-cloud-storage</artifactId>
    </dependency>
</dependencies>
~~~

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("com.google.cloud:google-cloud-storage")
}
~~~

Nếu ứng dụng dùng Spring Framework on Google Cloud, có thể dùng BOM và starter Storage để auto-configure bean Storage; phần này đã được giới thiệu trong bài tích hợp client và Spring Resource. Khi import trực tiếp lớp Java client trong source, kiểm tra chính sách dependency của dự án và khai báo artifact trực tiếp nếu cần. Không gắn một version riêng không tương thích với BOM.

### 3.2. Application Default Credentials

Java client thường dùng **Application Default Credentials (ADC)**:

~~~java
Storage storage = StorageOptions.getDefaultInstance().getService();
~~~

Trong local development, developer có thể thiết lập ADC bằng:

~~~bash
gcloud auth application-default login
gcloud config set project training-platform-dev
~~~

Hai lệnh có mục đích khác nhau: lệnh đầu tạo credentials cho ứng dụng; lệnh thứ hai đặt project mặc định của CLI. Cấu hình project mà Java client sử dụng vẫn cần được kiểm tra theo StorageOptions, ADC và cấu hình Spring của ứng dụng.

Khi chạy trên Google Cloud, ưu tiên service account gắn với workload hoặc Workload Identity Federation phù hợp. Không đóng gói private key JSON vào source code, container image hoặc artifact.

### 3.3. Tạo Storage bean trong Spring

Nếu Spring Framework on Google Cloud Storage starter đã auto-configure bean Storage, inject bean đó:

~~~java
import com.google.cloud.storage.Storage;
import org.springframework.stereotype.Service;

@Service
public class CloudStorageOperations {

    private final Storage storage;

    public CloudStorageOperations(Storage storage) {
        this.storage = storage;
    }
}
~~~

Nếu tự tạo bean, cấu hình một lần trong ApplicationContext:

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GcsConfiguration {

    @Bean
    Storage storage() {
        return StorageOptions.getDefaultInstance().getService();
    }
}
~~~

Không tạo Storage client mới cho mỗi request. Client có thể được tái sử dụng; quản lý lifecycle theo cấu hình Spring và đóng khi ứng dụng dừng nếu bạn tự sở hữu client.

### 3.4. Cấu hình bucket và project

Đưa bucket name vào property:

~~~yaml
app:
  gcs:
    bucket: APP_DOCUMENT_BUCKET
~~~

**APP_DOCUMENT_BUCKET** là tên biến môi trường mà deployment cung cấp. Giá trị local có thể là **training-documents-dev**; staging và production cần bucket riêng. Bucket name không phải secret, nhưng không nên hard-code bucket production trong source chung hoặc cho phép client request tùy ý chọn bucket.

## 4. IAM permission cho từng thao tác

Cloud Storage dùng IAM để xác định principal có thể thao tác object. Các permission cơ bản cần hiểu:

| Thao tác | Permission chính | Ghi chú |
| --- | --- | --- |
| Upload object mới | storage.objects.create | Cần quyền tạo object trong bucket |
| Download/đọc object | storage.objects.get | Đọc bytes và metadata |
| Liệt kê object | storage.objects.list | Quyền list bucket; prefix trong code không thay IAM |
| Xóa object | storage.objects.delete | Có thể bị retention/hold ngăn |
| Xem bucket metadata | storage.buckets.get | Không đồng nghĩa được đọc object |
| Tạo bucket | storage.buckets.create | Thường thuộc vai trò provisioning, không phải runtime |

Các predefined role thường gặp:

- **roles/storage.objectViewer:** đọc object và metadata trong phạm vi được cấp; phù hợp service chỉ đọc.
- **roles/storage.objectCreator:** tạo object mới; không mặc nhiên có quyền đọc, xóa hoặc ghi đè object hiện có.
- **roles/storage.objectUser:** cung cấp nhóm quyền object rộng hơn theo định nghĩa role hiện hành; phù hợp workload cần nhiều thao tác object.
- **roles/storage.objectAdmin:** quản trị object trong phạm vi cấp quyền.
- **roles/storage.admin:** quản trị bucket/object rộng; dành cho nhiệm vụ quản trị hạ tầng, không phải mặc định cho runtime.

Khi ghi đè object đã tồn tại, Cloud Storage có thể yêu cầu cả quyền tạo và quyền xóa object cũ theo semantics thao tác. Hãy cấp quyền theo operation thật sự và kiểm thử bằng principal runtime. Không dùng roles/storage.admin để giải quyết một lỗi upload đơn lẻ.

### 4.1. Prefix không phải ranh giới bảo mật

Ví dụ service chỉ truyền prefix **tenant-a/** vào lệnh list. Điều đó chỉ giới hạn kết quả do code yêu cầu; nếu service account có quyền list/read toàn bucket thì principal vẫn có thể yêu cầu prefix khác. Muốn cách ly tenant, cần authorization ở application, IAM condition phù hợp, hoặc tách bucket/project theo yêu cầu bảo mật.

### 4.2. UBLA và Public Access Prevention

Với bucket dùng Uniform bucket-level access (UBLA), quản lý quyền qua IAM thay vì ACL object/bucket. Public Access Prevention giúp ngăn cấp quyền public ngoài ý muốn. Không tạo ACL public để làm cho upload/download “dễ test”. Nếu người dùng cuối cần tải object, backend có thể cấp signed URL có thời hạn sau khi xác minh quyền nghiệp vụ.

## 5. Upload object nhỏ bằng Storage.create

### 5.1. Tạo BlobInfo

BlobInfo mô tả object trước khi upload. Có thể thiết lập content type, cache control và custom metadata:

~~~java
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import java.util.Map;

BlobInfo blobInfo = BlobInfo.newBuilder(
        BlobId.of(bucket, objectName))
    .setContentType("application/pdf")
    .setCacheControl("private, max-age=0")
    .setMetadata(Map.of(
        "source-system", "document-api",
        "document-id", documentId))
    .build();
~~~

Không đưa secret, access token hoặc dữ liệu nhạy cảm vào custom metadata. Metadata không thay thế database; nếu cần query phức tạp, hãy lưu chỉ mục ở database.

### 5.2. Upload bằng byte array

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.nio.charset.StandardCharsets;

public Blob uploadText(
        Storage storage,
        String bucket,
        String objectName,
        String text) {

    BlobInfo info = BlobInfo.newBuilder(
            BlobId.of(bucket, objectName))
        .setContentType("text/plain; charset=utf-8")
        .build();

    return storage.create(
            info,
            text.getBytes(StandardCharsets.UTF_8),
            Storage.BlobTargetOption.doesNotExist());
}
~~~

doesNotExist là precondition: request chỉ thành công nếu chưa có live object cùng tên. Nếu object đã tồn tại, GCS từ chối thao tác thay vì âm thầm ghi đè. Đây là cách chống race condition tốt hơn việc gọi storage.get để kiểm tra trước rồi upload sau.

Kết quả Blob chứa metadata của object vừa tạo, bao gồm generation. Có thể lưu generation vào database nếu nghiệp vụ cần tham chiếu chính xác phiên bản dữ liệu.

### 5.3. Ghi đè có điều kiện

Nếu nghiệp vụ cho phép thay thế object chỉ khi generation vẫn là giá trị đã đọc:

~~~java
BlobInfo info = BlobInfo.newBuilder(
        BlobId.of(bucket, objectName))
    .setContentType("application/pdf")
    .build();

Blob replaced = storage.create(
        info,
        content,
        Storage.BlobTargetOption.generationMatch(expectedGeneration));
~~~

Nếu một worker khác đã ghi phiên bản mới, generation không còn khớp và request bị từ chối với lỗi precondition. Không bỏ điều kiện để ép ghi thành công; hãy đọc lại trạng thái và quyết định merge hoặc trả conflict.

### 5.4. Content-Type và checksum

- Đặt Content-Type theo nội dung đã xác thực, không chỉ tin extension do người dùng gửi.
- Nếu upload qua API hỗ trợ, dùng CRC32C để kiểm tra tính toàn vẹn dữ liệu.
- Không tự coi ETag luôn là MD5.
- Với dữ liệu nén hoặc file đã mã hóa, cần hiểu checksum đang kiểm tra bytes nào.
- Không ghi payload nhạy cảm vào log khi debug lỗi upload.

## 6. Upload file lớn bằng WriteChannel

Với file lớn hoặc dữ liệu đến từ HTTP request stream, dùng Storage.writer để ghi qua WriteChannel, tránh tạo byte array chứa toàn bộ nội dung.

~~~java
import com.google.cloud.WriteChannel;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.channels.Channels;

public void uploadStream(
        Storage storage,
        BlobInfo blobInfo,
        InputStream source) throws IOException {

    try (WriteChannel writer = storage.writer(
                blobInfo,
                Storage.BlobWriteOption.doesNotExist());
         OutputStream output = Channels.newOutputStream(writer)) {
        source.transferTo(output);
    }
}
~~~

WriteChannel hỗ trợ upload theo luồng/resumable behavior tùy cấu hình client và transport. Đóng channel hoàn tất thao tác và giải phóng tài nguyên. Nếu source do caller sở hữu, quyết định rõ tầng nào đóng source; ví dụ trên chỉ đóng writer/output được tạo trong method, còn source do caller quản lý.

### 6.1. Chọn cách upload theo dữ liệu

| Loại dữ liệu | Cách phù hợp | Lưu ý |
| --- | --- | --- |
| Text/JSON vài KB | Storage.create với byte array | Đơn giản |
| Ảnh hoặc file nhỏ có giới hạn size | Storage.create với byte array | Kiểm tra kích thước trước khi cấp phát |
| Multipart upload từ HTTP | Storage.writer | Stream từ request, không đọc toàn bộ vào heap |
| File local lớn | Files.newInputStream(path) + WriteChannel hoặc API upload phù hợp | Giới hạn concurrency và timeout |
| Dữ liệu cần resume/retry nâng cao | Resumable upload/transfer tooling theo SDK | Kiểm tra version, chunk size, retry và chi phí |

Không tăng số thread upload vô hạn. Mỗi upload đồng thời tiêu thụ connection, buffer, CPU và network; đặt giới hạn concurrency theo tài nguyên của service.

### 6.2. Upload từ file local

~~~java
import com.google.cloud.WriteChannel;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.channels.Channels;
import java.nio.file.Files;
import java.nio.file.Path;

public void uploadFile(
        Storage storage,
        BlobInfo info,
        Path sourceFile) throws Exception {

    try (InputStream input = Files.newInputStream(sourceFile);
         WriteChannel writer = storage.writer(
                 info, Storage.BlobWriteOption.doesNotExist());
         OutputStream output = Channels.newOutputStream(writer)) {
        input.transferTo(output);
    }
}
~~~

Ví dụ trên giả định file đã được kiểm tra quyền truy cập, loại nội dung và kích thước. Nếu file được upload từ người dùng, không dùng filename nguyên bản làm đường dẫn local hoặc object name; tạo ID ổn định và validate nội dung.

## 7. Download object về file

### 7.1. Lấy metadata trước khi tải

Storage.get(BlobId) trả Blob nếu object tồn tại, hoặc null nếu không tìm thấy. Đây là thao tác đọc metadata; không đồng nghĩa bytes đã được tải về.

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;

public Blob findObject(
        Storage storage,
        String bucket,
        String objectName) {

    return storage.get(BlobId.of(bucket, objectName));
}
~~~

Khi Blob là null, trả kết quả not found phù hợp. Khi nhận 403, không được biến thành not found nếu hệ thống cần phân biệt quyền truy cập và dữ liệu không tồn tại.

### 7.2. Download trực tiếp tới Path

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import java.nio.file.Path;

public boolean downloadToFile(
        Storage storage,
        String bucket,
        String objectName,
        Path destination) {

    Blob blob = storage.get(BlobId.of(bucket, objectName));
    if (blob == null) {
        return false;
    }

    blob.downloadTo(destination);
    return true;
}
~~~

downloadTo(Path) là cách đơn giản cho file vừa/nhỏ hoặc khi cần file local. Trong production cần kiểm tra:

- Thư mục đích tồn tại và process có quyền ghi.
- File đích không bị ghi đè ngoài ý muốn.
- Dung lượng đĩa đủ cho object.
- Tên file được sinh từ dữ liệu đã validate, không ghép trực tiếp input không tin cậy.
- File tạm được dọn khi download lỗi giữa chừng.
- Có giới hạn kích thước và thời gian tải.

Nếu cần đọc đúng generation đã lưu, tạo BlobId kèm generation thay vì chỉ dùng object name live.

### 7.3. Download theo generation cụ thể

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import java.nio.file.Path;

public boolean downloadGeneration(
        Storage storage,
        String bucket,
        String objectName,
        long generation,
        Path destination) {

    BlobId versionedId = BlobId.of(bucket, objectName, generation);
    Blob blob = storage.get(versionedId);

    if (blob == null) {
        return false;
    }

    blob.downloadTo(destination);
    return true;
}
~~~

Generation hữu ích khi một quy trình xử lý cần đảm bảo tải đúng bytes mà một bước trước đó đã ghi nhận. Nếu chỉ dùng object name, một lần upload mới có thể khiến ứng dụng tải live generation khác với phiên bản ban đầu.

### 7.4. Không tải toàn bộ file vào heap

API getContent hoặc readAllBytes tiện cho object nhỏ, nhưng trả về byte array. Không dùng cho file lớn không có giới hạn. Với object lớn, stream thẳng tới file hoặc response output stream.

## 8. Download theo luồng bằng ReadChannel

ReadChannel cho phép đọc object từng phần và phù hợp khi dữ liệu cần được truyền tiếp tới HTTP response, file hoặc một xử lý streaming khác.

~~~java
import com.google.cloud.ReadChannel;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.channels.Channels;

public void streamTo(
        Storage storage,
        String bucket,
        String objectName,
        OutputStream destination) throws IOException {

    BlobId blobId = BlobId.of(bucket, objectName);

    try (ReadChannel reader = storage.reader(blobId);
         InputStream input = Channels.newInputStream(reader)) {
        input.transferTo(destination);
    }
}
~~~

Method này không đóng destination, vì output stream thường do controller/HTTP framework quản lý. Nó đóng ReadChannel và input wrapper mà method tạo.

### 8.1. Stream object trong Spring MVC

Một controller có thể trả StreamingResponseBody để không phải giữ toàn bộ nội dung trong heap:

~~~java
import com.google.cloud.ReadChannel;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import java.io.InputStream;
import java.nio.channels.Channels;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@RestController
public class DocumentDownloadController {

    private final Storage storage;

    public DocumentDownloadController(Storage storage) {
        this.storage = storage;
    }

    @GetMapping("/documents/{id}/content")
    public ResponseEntity<StreamingResponseBody> download(
            @PathVariable String id) {

        String bucket = "training-documents-dev";
        String objectName = "documents/" + id + ".pdf";

        StreamingResponseBody body = output -> {
            try (ReadChannel reader = storage.reader(
                        BlobId.of(bucket, objectName));
                 InputStream input = Channels.newInputStream(reader)) {
                input.transferTo(output);
            }
        };

        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_PDF)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"document.pdf\"")
                .body(body);
    }
}
~~~

Đây là ví dụ khung. Trước khi tạo stream, cần xác thực người dùng, kiểm tra quyền truy cập document ID, xác minh object tồn tại và lấy content type/size phù hợp. Không cho phép client truyền bucket tùy ý hoặc truy cập object chỉ bằng cách đoán ID.

Với WebFlux, Storage Java client là API blocking. Không gọi trực tiếp trên event-loop; chuyển tác vụ blocking sang scheduler thích hợp hoặc thiết kế adapter bất đồng bộ riêng.

### 8.2. Range download và resume

Nếu ứng dụng cần tải từng đoạn hoặc tiếp tục download, xem ReadChannel và các API range/seek phù hợp với release client library. Cần xác định generation trước khi tải nhiều đoạn; nếu live object thay đổi giữa các request, dữ liệu ghép có thể không cùng một phiên bản. Dùng generation cụ thể hoặc precondition để giữ tính nhất quán.

## 9. Liệt kê object theo bucket và prefix

### 9.1. Liệt kê object

Storage.list(bucket, BlobListOption...) trả về Page<Blob>. Ví dụ:

~~~java
import com.google.api.gax.paging.Page;
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.Storage;

public void listAll(Storage storage, String bucket) {
    Page<Blob> page = storage.list(
            bucket,
            Storage.BlobListOption.pageSize(100));

    for (Blob blob : page.iterateAll()) {
        System.out.printf(
                "%s | %d bytes | generation=%d%n",
                blob.getName(),
                blob.getSize(),
                blob.getGeneration());
    }
}
~~~

iterateAll() duyệt các trang tiếp theo theo cơ chế paging của client. Cách này thuận tiện cho batch job cần xử lý tất cả kết quả, nhưng không nên gom toàn bộ object vào một List nếu bucket có hàng triệu object. Hãy xử lý từng item, ghi kết quả theo batch hoặc giới hạn phạm vi prefix.

### 9.2. Liệt kê theo prefix

~~~java
Page<Blob> page = storage.list(
        bucket,
        Storage.BlobListOption.prefix("reports/2026/"),
        Storage.BlobListOption.pageSize(100));

for (Blob blob : page.iterateAll()) {
    System.out.println(blob.getName());
}
~~~

Prefix là bộ lọc tên object, không phải thư mục vật lý trong flat namespace và không phải IAM boundary. Dùng prefix để tổ chức dữ liệu, xử lý theo tenant hoặc theo ngày; quyền truy cập vẫn do IAM quyết định.

### 9.3. Chế độ directory-like

Nếu cần hiển thị danh sách theo cấp thư mục, có thể kết hợp BlobListOption.currentDirectory() với prefix:

~~~java
Page<Blob> page = storage.list(
        bucket,
        Storage.BlobListOption.prefix("reports/"),
        Storage.BlobListOption.currentDirectory());

for (Blob blob : page.iterateAll()) {
    System.out.println(blob.getName());
}
~~~

Chế độ này sử dụng delimiter để nhóm kết quả thành object và prefix con theo semantics API. Với flat namespace, prefix con không nhất thiết là folder resource độc lập. Nếu bucket bật hierarchical namespace, cần đọc tài liệu tương ứng và chọn API phù hợp với cấu trúc bucket đó.

### 9.4. Phân trang tường minh

Khi API ứng dụng cần trả từng trang cho người dùng, không nên gọi iterateAll() rồi mới cắt danh sách. Dùng page size và page token/cursor theo API hỗ trợ để lấy từng trang.

~~~java
Page<Blob> page = storage.list(
        bucket,
        Storage.BlobListOption.prefix(prefix),
        Storage.BlobListOption.pageSize(50));

List<BlobSummary> summaries = new ArrayList<>();

for (Blob blob : page.getValues()) {
    summaries.add(new BlobSummary(
            blob.getName(),
            blob.getSize(),
            blob.getGeneration()));
}

String nextPageToken = page.getNextPageToken();
~~~

Trong API web của ứng dụng, có thể trả nextPageToken cho client rồi dùng token đó để lấy trang kế tiếp. Cần xác minh cách truyền page token theo phiên bản BlobListOption đang dùng; không tự tạo token từ object name.

### 9.5. Chỉ lấy metadata cần thiết

List trả về metadata object, không tải bytes của từng object. Vì vậy có thể dùng list để hiển thị tên, size, content type, generation và thời điểm cập nhật mà không download từng file. Nếu cần đọc nội dung, thực hiện operation riêng sau khi xác thực quyền và giới hạn số request.

### 9.6. Tránh list toàn bucket trong request người dùng

List toàn bucket có thể trả rất nhiều kết quả, tiêu thụ quota và tăng latency. Nên:

- Luôn đặt prefix theo phạm vi nghiệp vụ khi có thể.
- Dùng page size phù hợp.
- Không gọi list liên tục cho mỗi lần render màn hình nếu có thể cache metadata/index.
- Không dùng GCS list như truy vấn database theo custom metadata.
- Đặt giới hạn số object trả về trong một HTTP request.
- Dùng database/index nếu cần sort, filter hoặc tìm kiếm phức tạp.

## 10. Xóa object có kiểm soát

### 10.1. Xóa theo bucket và object name

~~~java
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;

public boolean deleteObject(
        Storage storage,
        String bucket,
        String objectName) {

    return storage.delete(BlobId.of(bucket, objectName));
}
~~~

Giá trị true cho biết thao tác xóa thành công; false có thể biểu thị object không tồn tại. Lỗi permission, retention hoặc lỗi dịch vụ có thể được ném dưới dạng StorageException; không bắt tất cả exception rồi trả false vì sẽ che lỗi thật.

### 10.2. Xóa đúng generation

Khi một quy trình đã đọc object generation G1, nhưng object có thể bị thay thế trước khi xóa, hãy dùng generation precondition:

~~~java
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;

public boolean deleteIfUnchanged(
        Storage storage,
        String bucket,
        String objectName,
        long expectedGeneration) {

    return storage.delete(
            BlobId.of(bucket, objectName),
            Storage.BlobSourceOption.generationMatch(
                    expectedGeneration));
}
~~~

Nếu live generation đã thay đổi, request bị từ chối thay vì xóa nhầm phiên bản mới. Đây là cách bảo vệ khi nhiều worker hoặc người dùng có thể cùng thao tác.

### 10.3. Xóa object version cụ thể

Nếu bucket bật Object Versioning và nghiệp vụ cần xóa một generation cụ thể, có thể dùng BlobId chứa generation tương ứng và các option được SDK hỗ trợ. Hãy phân biệt:

- Xóa live object hiện tại.
- Xóa một noncurrent generation.
- Soft delete theo cấu hình bucket.
- Xóa vĩnh viễn khi chính sách retention cho phép.

Đừng giả định một lệnh delete luôn làm bytes biến mất ngay lập tức. Object Versioning, soft delete, retention policy, event-based hold hoặc temporary hold có thể thay đổi kết quả lưu giữ và khả năng khôi phục.

### 10.4. Xóa không phải thao tác rollback

Một khi ứng dụng xóa object, khả năng khôi phục phụ thuộc bucket policy và cấu hình lưu giữ. Trước khi xóa theo yêu cầu người dùng:

1. Xác thực principal và quyền sở hữu tài liệu.
2. Xác định bucket/object/generation đích.
3. Kiểm tra quy tắc retention/hold nếu nghiệp vụ yêu cầu.
4. Ghi audit event theo chính sách, không ghi nội dung nhạy cảm.
5. Dùng generation precondition nếu object có thể bị cập nhật đồng thời.
6. Xử lý kết quả false, 403, 404, 412 và các lỗi dịch vụ riêng biệt.

Không cung cấp API xóa hàng loạt dựa trên prefix tùy ý mà không có giới hạn, xác nhận và audit phù hợp.

## 11. Gộp thao tác thành một Storage adapter

Một service Spring Boot nên đóng gói các thao tác GCS trong adapter, thay vì để controller tự gọi SDK. Ví dụ:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.nio.charset.StandardCharsets;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class DocumentObjectAdapter {

    private final Storage storage;
    private final String bucket;

    public DocumentObjectAdapter(
            Storage storage,
            @Value("${app.gcs.bucket}") String bucket) {
        this.storage = storage;
        this.bucket = bucket;
    }

    public Blob uploadText(String objectName, String text) {
        BlobInfo info = BlobInfo.newBuilder(
                BlobId.of(bucket, objectName))
            .setContentType("text/plain; charset=utf-8")
            .build();

        return storage.create(
                info,
                text.getBytes(StandardCharsets.UTF_8),
                Storage.BlobTargetOption.doesNotExist());
    }

    public Blob find(String objectName) {
        return storage.get(BlobId.of(bucket, objectName));
    }

    public boolean delete(String objectName, long generation) {
        return storage.delete(
                BlobId.of(bucket, objectName),
                Storage.BlobSourceOption.generationMatch(generation));
    }
}
~~~

Ví dụ này tập trung vào upload/find/delete; list nên được cung cấp qua API phân trang thay vì trả toàn bộ object trong một List. Bucket được inject qua property thay vì hard-code. Adapter thực tế cần ánh xạ StorageException sang lỗi ứng dụng có ý nghĩa, kiểm soát object name, giới hạn kích thước và không để người dùng tự chọn bucket ngoài allowlist.

## 12. Ví dụ quy trình end-to-end: upload, list, download và delete

Một luồng quản lý tài liệu có thể thực hiện theo thứ tự:

~~~mermaid
sequenceDiagram
    participant API as Spring Boot API
    participant IAM as Workload identity / IAM
    participant GCS as Cloud Storage

    API->>IAM: Lấy credential của workload
    API->>GCS: Upload object (create + precondition)
    GCS-->>API: Blob metadata + generation
    API->>GCS: List theo prefix
    GCS-->>API: Page<Blob>
    API->>GCS: Download object/generation
    GCS-->>API: Object bytes
    API->>GCS: Delete với generation match
    GCS-->>API: deleted=true/false
~~~

Thiết kế nghiệp vụ nên lưu tối thiểu:

- Document ID của ứng dụng.
- Bucket và object name (hoặc định danh nội bộ ánh xạ sang chúng).
- Generation nếu cần tải/xóa đúng phiên bản.
- Content type và size nếu cần hiển thị.
- Trạng thái nghiệp vụ và audit metadata ở database.

Không nhất thiết lưu toàn bộ Blob metadata trong database; chỉ lưu trường phục vụ nghiệp vụ và khả năng phục hồi.

## 13. Dùng gcloud để kiểm tra nhanh

Java client là cách tích hợp trong ứng dụng; gcloud storage hữu ích khi kiểm tra thủ công hoặc debug.

### 13.1. Upload

~~~bash
gcloud storage cp ./sample.pdf gs://training-documents-dev/reports/sample.pdf
~~~

### 13.2. Download

~~~bash
gcloud storage cp gs://training-documents-dev/reports/sample.pdf ./downloaded-sample.pdf
~~~

### 13.3. List

~~~bash
gcloud storage ls --recursive gs://training-documents-dev/reports/
~~~

### 13.4. Delete

~~~bash
gcloud storage rm gs://training-documents-dev/reports/sample.pdf
~~~

Các lệnh trên dùng project/credentials hiện tại của gcloud. Trước khi thực hiện, kiểm tra project và principal để tránh thao tác nhầm bucket production. CLI thành công không tự động chứng minh Java process dùng cùng ADC hoặc cùng IAM identity.

## 14. Kiểm thử upload/download/list/delete

### 14.1. Unit test

Unit test tập trung vào logic nghiệp vụ và adapter:

- Validate object name và prefix.
- Tạo metadata đúng content type.
- Không upload nếu file vượt giới hạn.
- Xử lý duplicate object khi precondition doesNotExist thất bại.
- Mapping not found, permission denied và precondition conflict.
- Kiểm tra adapter đóng stream đúng cách.
- Xác minh delete chỉ được gọi sau khi quyền nghiệp vụ được xác nhận.

Mock Storage hoặc tạo interface DocumentStorage để test service mà không cần project GCP thật.

### 14.2. Integration test trên project GCP riêng

Một integration test thật có thể kiểm tra:

1. Upload object với tên duy nhất trong bucket test.
2. Đọc lại metadata và generation.
3. Download object và so sánh checksum/bytes.
4. List theo prefix, kiểm tra object xuất hiện.
5. Thử list với prefix khác và xác nhận không trả object không liên quan.
6. Xóa object bằng generation match.
7. Thử xóa lại và xử lý kết quả not found.
8. Thử xóa bằng generation cũ sau khi object được thay thế; kỳ vọng precondition fail.
9. Dọn tài nguyên test theo quy trình riêng.

Không chạy test destructive trên bucket production hoặc bucket dùng chung của nhóm khác. Test cần service account/workload identity riêng với quyền tối thiểu.

### 14.3. Kiểm tra dữ liệu lớn và streaming

Với upload/download lớn, test thêm:

- Dữ liệu lớn hơn giới hạn heap dành cho một request.
- Nhiều upload/download đồng thời trong giới hạn concurrency.
- Mạng bị ngắt giữa luồng.
- Client đóng stream sớm.
- Timeout và retry.
- Checksum/bytes sau khi tải về.
- Disk full hoặc lỗi ghi file đích.

Không chỉ test file vài KB rồi kết luận streaming hoạt động tốt với file hàng GB.

### 14.4. Test IAM

Kiểm tra từng principal có đúng quyền:

| Principal test | Thao tác kỳ vọng |
| --- | --- |
| Upload-only | Tạo object mới; không list hoặc delete nếu không được cấp |
| Read-only | Get object; không upload/delete |
| List/read | List prefix và tải object; không sửa/xóa |
| Cleanup role | Xóa object test trong bucket/prefix riêng |
| Runtime production | Chỉ operation nghiệp vụ được cho phép |

IAM permission test cần được kiểm chứng bằng thao tác thực tế trên resource test. Không giả định Local fake hoặc mock có thể chứng minh policy GCP thật.

## 15. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| 403 Forbidden khi upload | Principal thiếu storage.objects.create hoặc policy chặn | Kiểm tra ADC/workload identity và IAM scope |
| Upload object mới được nhưng ghi đè thất bại | Principal thiếu quyền xóa object cũ hoặc precondition không khớp | Kiểm tra IAM và generation |
| 404 Not Found khi download | Sai bucket/object name hoặc generation không tồn tại | Kiểm tra định danh và object version |
| 403 khi download | Thiếu storage.objects.get | Xác minh principal và role |
| List trả rỗng nhưng get object thành công | Thiếu storage.objects.list, prefix sai hoặc bucket khác | Kiểm tra list permission và prefix |
| List quá chậm | List toàn bucket, quá nhiều object, page size/concurrency không phù hợp | Dùng prefix, paging, index/cache |
| 412 Precondition Failed | Generation/metageneration không còn khớp | Đọc lại trạng thái và xử lý conflict |
| Delete trả false | Object không tồn tại hoặc generation không còn là live object | Xác minh bucket/object/version |
| Delete bị từ chối | Thiếu storage.objects.delete, retention/hold hoặc policy chặn | Kiểm tra IAM, retention và hold |
| Download gây OOM | Tải toàn bộ bytes vào heap | Dùng ReadChannel/streaming |
| Upload lớn bị lỗi giữa chừng | Timeout, stream không replay được, network hoặc chunk configuration | Kiểm tra resumable upload, retry và transport |
| Java và gcloud truy cập khác project | ADC khác CLI config hoặc property project ghi đè | Kiểm tra project ID và principal của Java |
| Object name có dấu / không như mong muốn | Nhầm prefix với thư mục thật hoặc encode sai | Kiểm tra tên đầy đủ và namespace của bucket |

### 15.1. Phân biệt 403, 404 và 412

- **403:** request đã được xác thực nhưng principal không có quyền hoặc policy/condition từ chối.
- **404:** resource/object/version không tồn tại hoặc API trả not found theo ngữ cảnh.
- **412:** precondition không thỏa; trạng thái object đã thay đổi so với giả định của caller.

Không retry vô hạn với 403/412. Với 412, đọc lại generation rồi xử lý conflict. Với 403, sửa IAM đúng permission. Với 404, kiểm tra định danh và vòng đời object.

### 15.2. Log an toàn

Log các trường phục vụ điều tra như operation, bucket alias, object ID nội bộ, generation, status code, latency và request correlation ID. Không log nội dung file, credential, signed URL hoặc metadata nhạy cảm. Nếu object name chứa dữ liệu cá nhân, cân nhắc hash hoặc mã định danh nội bộ trong log.

## 16. Lưu giữ, versioning và chi phí

Xóa object không phải lúc nào cũng có nghĩa dữ liệu bị loại bỏ vĩnh viễn ngay lập tức. Kết quả phụ thuộc:

- Object Versioning.
- Soft delete.
- Retention policy và Bucket Lock.
- Event-based hold hoặc temporary hold.
- Lifecycle rule.
- Generation cụ thể được xóa.

Khi bật versioning, ghi đè hoặc xóa live object có thể để lại generation cũ dưới dạng noncurrent version. Soft delete có thể giữ object đã xóa trong thời gian cấu hình. Retention policy có thể ngăn xóa trước thời hạn. Vì vậy, API delete của ứng dụng cần phản ánh đúng nghiệp vụ: “đánh dấu xóa”, “ẩn khỏi người dùng”, “xóa live object” hay “xóa vĩnh viễn” là các khái niệm khác nhau.

### 16.1. Lifecycle cleanup

Nếu bucket giữ nhiều object/version, thiết kế lifecycle rule để chuyển storage class hoặc xóa object/noncurrent generation theo thời gian. Cần kiểm tra điều kiện rule, thời gian lưu tối thiểu của storage class, retention và yêu cầu pháp lý trước khi áp dụng.

### 16.2. Chi phí operation

Upload, list, get và delete có thể được tính theo nhóm operation/usage của Cloud Storage. List toàn bucket thường xuyên hoặc download file lớn qua nhiều lần có thể làm tăng request và network cost. Đưa prefix, cache/index và download streaming vào thiết kế để giảm chi phí không cần thiết.

## 17. Bài tập thực hành tổng hợp

**Bối cảnh:** Xây ứng dụng Spring Boot document-api quản lý tài liệu của nhiều tenant. File được lưu trong bucket training-documents-dev, với object name theo mẫu documents/{tenantId}/{documentId}/{fileName}. Ứng dụng hỗ trợ upload, xem danh sách tài liệu, tải file và xóa tài liệu.

### Nhiệm vụ A — Upload

1. Tạo Storage bean qua ADC hoặc Spring Framework on Google Cloud starter.
2. Viết API upload với giới hạn kích thước, content type và object name an toàn.
3. Upload file nhỏ bằng Storage.create.
4. Upload file lớn bằng WriteChannel.
5. Dùng doesNotExist để tránh ghi đè object ngoài ý muốn.
6. Lưu generation và metadata cần thiết vào database.

### Nhiệm vụ B — Download

1. Tìm document theo ID và kiểm tra tenant authorization.
2. Lấy Blob metadata và xác định content type/size.
3. Stream bytes bằng ReadChannel tới HTTP response.
4. Nếu cần tải đúng phiên bản đã duyệt, sử dụng generation được lưu.
5. Thiết kế response header an toàn và không lộ bucket/object nội bộ.

### Nhiệm vụ C — List

1. Liệt kê object theo prefix tenant.
2. Dùng pageSize và page token để phân trang.
3. Không tải bytes khi chỉ cần metadata.
4. Giải thích vì sao prefix không tự bảo vệ dữ liệu tenant.
5. Thiết kế index/database nếu cần tìm kiếm theo trạng thái hoặc metadata nghiệp vụ.

### Nhiệm vụ D — Delete

1. Kiểm tra quyền xóa và trạng thái tài liệu.
2. Xóa object với generation match.
3. Xử lý trường hợp generation đã thay đổi.
4. Phân biệt xóa live object với soft delete/version retention.
5. Ghi audit event và xử lý database consistency khi GCS delete thất bại.

### Nhiệm vụ E — Kiểm thử

- Unit test upload, download, list, delete qua fake adapter.
- Integration test trên bucket GCP riêng.
- Test doesNotExist và generation mismatch.
- Test list pagination với nhiều object.
- Test streaming file lớn và giới hạn bộ nhớ.
- Test principal thiếu từng permission.
- Kiểm tra lifecycle/retention trong môi trường test phù hợp.

**Tiêu chí đạt:** Ứng dụng có thể upload/download/list/delete object qua Java client; xử lý streaming và pagination đúng; không ghi đè hoặc xóa nhầm generation; quyền IAM theo operation rõ ràng; và có integration test kiểm tra semantics Cloud Storage thật.

## 18. So sánh với AWS S3 và Azure Blob Storage

| Thao tác | Google Cloud Storage | Amazon S3 | Azure Blob Storage |
| --- | --- | --- | --- |
| Upload | Storage.create, Storage.writer | S3Client.putObject, multipart upload | BlobClient.upload, block blob upload |
| Download | Storage.reader, Blob.downloadTo | getObject, response stream | downloadToFile, openInputStream |
| List | Storage.list với prefix/page | listObjectsV2 với prefix/continuation token | listBlobs với prefix/paging |
| Delete | Storage.delete với generation precondition | deleteObject với version ID/conditional semantics | delete, snapshot/version options |
| Identity | ADC/service account/workload identity | IAM role/credential provider | Managed Identity/Entra ID |
| Version | Generation và metageneration | Version ID/ETag | Version ID/ETag/lease |

Cùng là object storage nhưng pagination token, version identifier, precondition, soft delete và semantics delete không giống nhau. Adapter đa cloud nên chuẩn hóa hành vi nghiệp vụ cần thiết, còn mỗi provider adapter phải giữ đúng API và bảo đảm riêng của dịch vụ.

## 19. Ghi nhớ

- Storage.create phù hợp nội dung nhỏ; Storage.writer và WriteChannel phù hợp upload streaming/file lớn.
- Storage.get đọc metadata; Blob.downloadTo hoặc ReadChannel tải bytes.
- Storage.list trả Page<Blob>; dùng prefix và pagination, không list toàn bucket trong request người dùng.
- Storage.delete có thể dùng generation precondition để tránh xóa phiên bản mới do worker khác tạo.
- IAM phải khớp operation: create, get, list và delete; prefix không phải ranh giới bảo mật.
- Versioning, soft delete, retention và hold ảnh hưởng kết quả xóa và khả năng phục hồi.
- Trong Spring Boot, inject một Storage bean và đóng gói logic trong adapter; không tạo client cho mỗi request.
- Kiểm thử cả logic adapter lẫn IAM/semantics trên project GCP test riêng.

### Tài liệu tham khảo

- [Google Cloud Storage Java client — Storage interface](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage)
- [Google Cloud Storage Java client — Blob class](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Blob)
- [Google Cloud Storage Java client — BlobTargetOption](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage.BlobTargetOption)
- [Google Cloud Storage Java client — BlobWriteOption](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage.BlobWriteOption)
- [Google Cloud Storage — Upload objects](https://cloud.google.com/storage/docs/uploading-objects)
- [Google Cloud Storage — Download objects](https://cloud.google.com/storage/docs/downloading-objects)
- [Google Cloud Storage — List objects](https://cloud.google.com/storage/docs/listing-objects)
- [Google Cloud Storage — Delete objects](https://cloud.google.com/storage/docs/deleting-objects)
- [Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials)
