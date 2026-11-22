# Upload và download dữ liệu bằng Blob Storage SDK

> **Chương:** Azure SDK cho Java  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu. Học cách triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng trên Azure.

## Mục tiêu bài học

Sau khi hoàn thành, bạn có thể:

1. Giải thích mô hình **Azure Storage account → container → blob** và phân biệt Block Blob, Append Blob, Page Blob.
2. Cấu hình **Azure Blob Storage SDK cho Java**, BlobServiceClient, BlobContainerClient và BlobClient bằng Maven/Gradle.
3. Xác thực an toàn bằng **Microsoft Entra ID, DefaultAzureCredential và managed identity** thay vì nhúng account key vào ứng dụng.
4. Viết Java để **upload/download file và stream**, đọc properties, ETag, content type và metadata.
5. Hiểu **large-file transfer**, chunking, block staging/commit, parallelism, memory usage, timeout và retry.
6. Ngăn ghi đè nhầm bằng overwrite policy và **ETag/conditional requests**, kiểm tra data integrity, tránh path traversal.
7. Phân loại HTTP 401/403/404/409/412/429/5xx và thiết kế retry/idempotency đúng.
8. Kết hợp RBAC, Private Endpoint, TLS, SAS có thời hạn, soft delete/versioning, logs và kiểm soát chi phí.
9. Đề xuất test cases, runbook xử lý sự cố và checklist vận hành production.

## 1. Bối cảnh: một dịch vụ Java lưu và phục vụ tệp

Giả sử Java Spring Boot API nhận ảnh hóa đơn, PDF và CSV từ người dùng. Mỗi tệp cần được lưu để có thể tải lại, nhưng phải bảo vệ quyền truy cập theo tenant.

~~~mermaid
flowchart LR
    U["Web/mobile client"]
    API["Java API\nAuthenticate + authorize"]
    ID["Microsoft Entra ID\nManaged identity"]
    DB["Metadata database\nOwner, tenant, object ID"]
    ST["Azure Blob Storage\nPrivate container"]
    MON["Azure Monitor\nMetrics + diagnostics"]
    U --> API
    API --> DB
    API -->|"Blob SDK"| ST
    ID -.->|"OAuth token"| API
    API -.-> MON
    ST -.-> MON
~~~

Một quy trình an toàn:

1. Ứng dụng xác thực user, giới hạn kích thước và loại tệp.
2. Server tạo blob name **không phụ thuộc trực tiếp tên file từ client**, ví dụ `tenants/t001/2026/11/<uuid>.pdf`.
3. Java Blob SDK tải tệp lên container private bằng credential ứng dụng.
4. Lưu object ID, blob name, owner, size, ETag và checksum khi cần trong metadata DB.
5. Khi có yêu cầu download, **kiểm tra quyền nghiệp vụ** theo object ID, không tin đường dẫn blob do client tự gửi.
6. Truyền dữ liệu qua API hoặc dùng URL truy cập tạm thời có điều kiện và thời hạn ngắn.

**SDK upload thành công không đồng nghĩa ứng dụng đã đạt yêu cầu production.** Vẫn cần access control, monitoring, reliability, retention và cost budget — đúng mục tiêu học kiến trúc ứng dụng trên Azure.

## 2. Mô hình Blob Storage và loại dữ liệu

### 2.1. Account, container và blob

~~~text
Subscription
  Resource group: rg-files-prod
    Storage account: stfilesprod001
      Container: documents (private)
        tenants/t001/invoices/2026/report.pdf
        tenants/t001/images/1234.png
      Container: exports (private)
        daily/2026-11-20/orders.csv
      Container: audit-archive (private)
        year=2026/month=11/....
~~~

- **Storage account:** định nghĩa region, SKU, replication/redundancy, network rules, encryption và một số policy.
- **Container:** tập blobs, hỗ trợ scope phân quyền data RBAC phù hợp.
- **Blob:** object có nội dung và properties; key của blob là `blobName` trong container.
- **Blob URL:** ví dụ `https://stfilesprod001.blob.core.windows.net/documents/tenants/t001/report.pdf`. URL không có token/credential không tự cấp quyền đọc container private.
- **Properties:** content length, content type, ETag, last modified, access tier và HTTP headers.
- **Metadata:** key-value tùy chỉnh, **không dùng làm bằng chứng quyền truy cập nghiệp vụ** khi chưa xác thực bằng DB/policy.

### 2.2. Ba kiểu blob phổ biến

| Blob type | Phù hợp cho | Cách ghi |
| --- | --- | --- |
| **Block Blob** | PDF, ảnh, CSV, tệp lớn thông dụng | Upload toàn bộ hoặc chia blocks rồi commit |
| **Append Blob** | Luồng append-only có điều kiện | Append blocks theo semantics dịch vụ |
| **Page Blob** | Random-access page storage, ví dụ các use cases đĩa ảo | Ghi các page/ranges theo alignment |

Bài này tập trung **Block Blob**. Không chọn Append Blob chỉ vì tên tệp có đuôi `.log`; workload, khả năng sửa và chi phí mới quyết định loại blob.

### 2.3. Dấu gạch chéo và Azure Data Lake Storage Gen2

Trên Blob Storage với namespace phẳng, `/` có thể chỉ là ký tự trong blob name, tạo hình thức thư mục ảo. Khi Storage account bật **Hierarchical Namespace (HNS)** cho ADLS Gen2, directories có semantics khác và có thể dùng POSIX-like ACL.

Blob SDK sử dụng endpoint `<account>.blob.core.windows.net`; các APIs filesystem/ACL cho HNS thường dùng **Azure Storage Data Lake SDK / DFS endpoint**. Không coi hai SDK là hoán đổi hoàn toàn mà không kiểm tra feature compatibility.

## 3. Chuẩn bị Java, Azure và dependency

### 3.1. Điều kiện cho lab

- JDK **17+**, Maven hoặc Gradle do dự án quản lý.
- Một Storage account và container `documents` **đã tồn tại**, được phép dùng.
- Data-plane principal có **Storage Blob Data Contributor** cho upload hoặc **Storage Blob Data Reader** cho read-only, với scope tối thiểu.
- Entra login được cấu hình ở dev, managed identity/workload identity ở production.
- Network/TLS tới Blob endpoint hoạt động.
- Có giới hạn file size, timeout, retry budget, danh sách content types và owner.
- Chỉ thực hiện thao tác có phí hoặc ghi dữ liệu trên lab/subscription đã được phép.

Không tự tạo/tái cấu hình tài nguyên production để chạy ví dụ.

### 3.2. Maven dependencies

~~~xml
<dependencies>
    <dependency>
        <groupId>com.azure</groupId>
        <artifactId>azure-storage-blob</artifactId>
    </dependency>
    <dependency>
        <groupId>com.azure</groupId>
        <artifactId>azure-identity</artifactId>
    </dependency>
</dependencies>
~~~

Các dependencies ở trên cần **phiên bản** do parent POM/`dependencyManagement` hoặc Azure SDK BOM quản lý. Mẫu BOM:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <azure.sdk.bom.version>REPLACE_WITH_APPROVED_VERSION</azure.sdk.bom.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure</groupId>
            <artifactId>azure-sdk-bom</artifactId>
            <version>${azure.sdk.bom.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Khi chép vào một `pom.xml` hợp lệ, chọn BOM version được tổ chức phê duyệt và dùng Maven property thông thường. Không dùng một version đoán mò: các API/overloads của Azure SDK có thể thay đổi giữa versions.

### 3.3. Các client quan trọng

| Lớp Java SDK | Dùng cho | Ghi chú |
| --- | --- | --- |
| `BlobServiceClient` | Các thao tác phạm vi storage account | Synchronous |
| `BlobContainerClient` | Các thao tác container và liệt kê blob | Synchronous |
| `BlobClient` | Upload/download, properties trên một blob | Synchronous |
| `BlobServiceAsyncClient` | Service-level reactive operations | Non-blocking/reactive |
| `BlobContainerAsyncClient` | Container operations reactive | Cần quản lý concurrency |
| `BlobAsyncClient` | Async upload/download | Backpressure và lifecycle |
| `BlockBlobClient` | Stage block, commit block list thủ công | Chỉ dùng khi thực sự cần |

Spring MVC với blocking I/O có thể dùng sync client. Spring WebFlux nên cân nhắc async client hoặc scheduler riêng nếu có blocking file I/O; không chạy transfer blocking trên event loop chính.

### 3.4. Azure CLI preflight chỉ đọc

~~~bash
az login
az account show --query "{name:name,id:id,tenantId:tenantId}" -o json
az account set --subscription "<SUBSCRIPTION_ID>"

RG="rg-files-lab"
ACCOUNT="stfileslabunique001"
CONTAINER="documents"

az storage account show \
  --resource-group "$RG" \
  --name "$ACCOUNT" \
  --query "{name:name, location:location, sku:sku, publicNetworkAccess:publicNetworkAccess, allowSharedKeyAccess:allowSharedKeyAccess}" \
  -o json
~~~

Không chạy `az storage account keys list` để kiểm tra network hay RBAC; kết quả chứa secrets. Azure management `Reader` không tự là Blob Data Reader khi ứng dụng dùng Microsoft Entra token. Quyền `listKeys` có thể tạo đường truy cập khác bằng Shared Key, phải hạn chế.

## 4. Xác thực bằng Microsoft Entra ID

### 4.1. Luồng token tới Blob Storage

~~~mermaid
sequenceDiagram
    participant J as Java application
    participant E as Entra ID / Managed identity
    participant B as Azure Blob Storage
    J->>E: Request OAuth token
    E-->>J: Token
    J->>B: HTTPS request + token
    B->>B: Evaluate RBAC, network and policies
    B-->>J: Result or 401/403
~~~

`DefaultAzureCredential` thử các credential sources theo cấu hình và Azure Identity SDK version, ví dụ môi trường developer hoặc managed identity. **Không mặc định user `az login` ở laptop và managed identity production là cùng một principal**.

### 4.2. Client factory bằng DefaultAzureCredential

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

public final class BlobClients {
    private BlobClients() {}

    public static BlobContainerClient documents() {
        String account = System.getenv("AZURE_STORAGE_ACCOUNT");
        if (account == null || account.isBlank()) {
            throw new IllegalStateException("AZURE_STORAGE_ACCOUNT is required");
        }

        BlobServiceClient service = new BlobServiceClientBuilder()
            .endpoint("https://" + account + ".blob.core.windows.net")
            .credential(new DefaultAzureCredentialBuilder().build())
            .buildClient();

        return service.getBlobContainerClient("documents");
    }
}
~~~

Điều kiện: account và container có thật, identity đủ data-plane permission, DNS/TLS/network policy hợp lệ. **Không tạo client mới cho mỗi request** trong production: quản lý client như singleton hoặc bean chia sẻ để tận dụng HTTP connections/token caching.

### 4.3. Quyền tối thiểu

- **Storage Blob Data Reader**: đọc blobs tại scope phù hợp.
- **Storage Blob Data Contributor**: nhiều thao tác ghi/đọc/xóa blobs; cấp container scope hoặc hẹp nhất được hỗ trợ, không mặc định toàn subscription.
- **Storage Blob Data Owner**: role mạnh hơn, có khả năng quản trị quyền data khi hỗ trợ; không cấp cho app upload thông thường.
- **Azure Contributor/Owner**: roles quản trị Azure, không thay thế business authorization.

Nếu một upload 403, kiểm tra **tenant/principal object ID, role assignment, scope, RBAC propagation, network rules, đúng Blob endpoint** trước khi tăng quyền. Với container private, SDK không cần container `public access`.

### 4.4. Endpoint và mạng riêng

Ví dụ endpoint:

~~~text
https://stfileslabunique001.blob.core.windows.net/
~~~

Nếu tài khoản dùng **Private Endpoint**, DNS có thể phân giải về IP private, nhưng SDK vẫn sử dụng hostname Blob Storage để giữ TLS hostname verification. Không tự thay SDK URL bằng địa chỉ IP nội bộ và không tắt kiểm tra certificate.


## 5. Upload một file với BlobClient

### 5.1. Chương trình Java upload thực tế

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.models.BlobProperties;

import java.nio.file.Files;
import java.nio.file.Path;

public final class UploadFileExample {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "Usage: UploadFileExample <local-file> <safe-blob-name>"
            );
        }

        Path source = Path.of(args[0]).toAbsolutePath().normalize();
        if (!Files.isRegularFile(source) || !Files.isReadable(source)) {
            throw new IllegalArgumentException("Source not readable");
        }

        String name = args[1];
        if (name.isBlank() || name.startsWith("/")
                || name.contains("..") || name.contains("\\")) {
            throw new IllegalArgumentException("Unsafe blob name");
        }

        BlobContainerClient container = BlobClients.documents();
        BlobClient blob = container.getBlobClient(name);

        // Không ghi đè đối tượng cùng tên đang tồn tại.
        blob.uploadFromFile(source.toString(), false);

        BlobProperties properties = blob.getProperties();
        System.out.println("Uploaded: " + name);
        System.out.println("Size: " + properties.getBlobSize());
        System.out.println("ETag: " + properties.getETag());
    }
}
~~~

`BlobClients` là factory ở mục 4. Đoạn kiểm tra tên blob chỉ đủ cho lab, không phải validator production. Server nên sinh tên từ opaque ID và tenant identity đã xác minh; không nhận tùy ý blob path từ người dùng. `uploadFromFile(path, false)` yêu cầu không overwrite. Nếu tên đã có, request thất bại theo điều kiện dịch vụ; **không tự đổi sang `true` trong catch**.

### 5.2. Sinh blob name không phụ thuộc filename user

~~~java
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;

public final class BlobNames {
    private BlobNames() {}

    public static String newPdfName(String authorizedTenantId) {
        if (!authorizedTenantId.matches("[a-zA-Z0-9-]{1,64}")) {
            throw new IllegalArgumentException("Invalid tenant ID");
        }
        LocalDate day = LocalDate.now(ZoneOffset.UTC);
        return "tenants/" + authorizedTenantId
            + "/" + day.getYear()
            + "/" + String.format("%02d", day.getMonthValue())
            + "/" + UUID.randomUUID() + ".pdf";
    }
}
~~~

Tên unique tránh collisions, nhưng **UUID không thay authorization** và phần đuôi `.pdf` không chứng minh nội dung là PDF. Cần file-size limit, malware scanning, content sniffing, data classification và policy trước khi publish.

### 5.3. Có nên tạo container khi upload?

Không gọi `createBlobContainer` hoặc `createIfNotExists` trong mỗi HTTP request. Provision container bằng IaC/admin workflow trước: runtime upload không nên giữ permission tạo containers rộng hơn cần thiết. `getBlobContainerClient("documents")` chỉ lấy client handle, không đảm bảo container tồn tại.

## 6. Upload headers, metadata và điều kiện không ghi đè

### 6.1. HTTP headers

| Header/property | Công dụng | Cảnh báo |
| --- | --- | --- |
| `Content-Type` | Khai báo MIME, ví dụ `application/pdf` | Không tin duy nhất loại MIME do client gửi |
| `Content-Disposition` | Gợi ý file download/attachment | Giảm nguy cơ render nội dung không an toàn |
| `Cache-Control` | Chỉ dẫn caching | Cẩn trọng tài liệu riêng tư/cache chung |
| `ETag` | Optimistic concurrency / conditional requests | Không phải checksum nội dung |
| User metadata | ID/correlation/business metadata | Không dùng làm nguồn auth |
| Blob index tags | Tìm/filter khi tính năng hỗ trợ | Khác metadata và có billing/permission riêng |

Với file tải lên từ untrusted users, thường đặt `Content-Disposition: attachment` khi phù hợp, không hiển thị HTML/script không kiểm soát trong browser.

### 6.2. Tạo mới bằng If-None-Match

Ví dụ options API của các phiên bản `azure-storage-blob` hỗ trợ:

~~~java
import com.azure.core.util.Context;
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.models.BlobHttpHeaders;
import com.azure.storage.blob.models.BlobRequestConditions;
import com.azure.storage.blob.options.BlobUploadFromFileOptions;

import java.time.Duration;
import java.util.Map;

public final class UploadWithOptions {
    public static void createPdf(
            BlobClient blob, String localPath, String documentId) {

        BlobHttpHeaders headers = new BlobHttpHeaders()
            .setContentType("application/pdf")
            .setContentDisposition("attachment");

        BlobUploadFromFileOptions options =
            new BlobUploadFromFileOptions(localPath)
                .setHeaders(headers)
                .setMetadata(Map.of("documentid", documentId))
                .setRequestConditions(
                    new BlobRequestConditions().setIfNoneMatch("*")
                );

        blob.uploadFromFileWithResponse(
            options, Duration.ofMinutes(10), Context.NONE
        );
    }
}
~~~

**Version note:** xác minh `BlobUploadFromFileOptions` và overload `uploadFromFileWithResponse` của đúng SDK đang dùng trước khi triển khai. `If-None-Match: *` yêu cầu tạo khi blob chưa tồn tại; request có thể thất bại với `412 Precondition Failed` hoặc lỗi điều kiện tương ứng. Đừng xử lý mọi `BlobStorageException` bằng overwrite.

### 6.3. Upload thành công nhưng client timeout

Trường hợp khó:

~~~text
Client gửi upload + conditional create
    → Azure commit blob
    → Phản hồi mạng bị mất
    → Client tưởng upload thất bại
~~~

Cách xử lý:

1. Ghi operation ID/idempotency key trong metadata DB ở trạng thái PENDING.
2. Khi timeout, **không kết luận blob không tồn tại**.
3. Thử đọc properties bằng tên blob đã xác định và quyền hợp lệ.
4. Đối chiếu kích thước, ETag, checksum/manifest hoặc metadata khi được kiểm chứng.
5. Nếu dữ liệu đã commit đúng, đánh dấu hoàn tất; nếu chưa, retry cùng key và conditional create có giới hạn.
6. Không tạo tên mới trong mỗi retry rồi sinh ra nhiều bản sao không chủ đích.

### 6.4. Metadata không phải nơi lưu bí mật

Không lưu raw access token, Storage account key, signed SAS URI, số giấy tờ tùy thân hay các secrets khác trong blob metadata. Metadata có thể được đọc bởi những principals có quyền đọc properties, được ghi lại trong logs hoặc copy cùng blob.

Nếu cập nhật headers sau upload, cần hiểu `setHttpHeaders` có thể thay tập properties: có nguy cơ bỏ mất `Content-Disposition`/`Cache-Control` nếu không giữ các giá trị cần thiết. Ưu tiên thiết lập trong upload options và dùng concurrency conditions khi phù hợp.

## 7. Download blob về file local

### 7.1. Ví dụ download không overwrite local file

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobContainerClient;

import java.nio.file.Files;
import java.nio.file.Path;

public final class DownloadFileExample {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "Usage: DownloadFileExample <authorized-blob-name> <output>"
            );
        }

        // Production: server tra tên blob từ metadata DB
        // sau khi xác thực user/object owner.
        String blobName = args[0];
        Path target = Path.of(args[1]).toAbsolutePath().normalize();
        if (target.getParent() == null) {
            throw new IllegalArgumentException("Invalid destination");
        }

        Files.createDirectories(target.getParent());

        BlobContainerClient container = BlobClients.documents();
        BlobClient blob = container.getBlobClient(blobName);

        // Không ghi đè file local tồn tại.
        blob.downloadToFile(target.toString(), false);

        System.out.println("Downloaded " + Files.size(target) + " bytes");
    }
}
~~~

Không lấy nguyên `blobName` hoặc `output` từ request người dùng trong production: blob name có thể dẫn đến truy cập tài liệu của tenant khác, output path có thể gây **local path traversal**. Backend phải xác thực object ID, kiểm tra quyền, sinh tên local an toàn, thiết lập file permissions và quản lý cache/cleanup.

### 7.2. Giới hạn đường dẫn download

~~~java
import java.nio.file.Path;
import java.util.UUID;

Path root = Path.of("/app/download-cache")
    .toAbsolutePath().normalize();

String safeName = UUID.randomUUID() + ".pdf";
Path target = root.resolve(safeName).normalize();

if (!target.startsWith(root)) {
    throw new SecurityException("Outside allowed directory");
}
~~~

Ở môi trường thực, còn phải quản lý **symlinks, file-system mounts, đồng thời truy cập, quota, race conditions và file cleanup**. Cân nhắc download vào file tạm được tạo an toàn rồi đổi tên sau verify.

### 7.3. Download lớn và Archive tier

Tệp ở online access tier có thể đọc trực tiếp khi được phép. **Archive tier** có thể yêu cầu rehydrate về tier online trước khi download; việc rehydrate và truy xuất có chi phí/độ trễ. Không chọn Archive cho object mà ứng dụng phải phục vụ người dùng theo SLA vài giây.

### 7.4. ETag so với data integrity

ETag giúp biết blob có bị thay đổi theo server version/concurrency, **không phải SHA-256 hash của nội dung**. Content length bằng nhau cũng không đủ chứng minh bytes giống nhau. Với file quan trọng cần checksum/manifest độc lập và verify sau download.

## 8. Upload và download qua streams

### 8.1. Upload InputStream với độ dài chính xác

~~~java
import com.azure.storage.blob.BlobClient;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public final class StreamUploadExample {
    public static void upload(Path source, BlobClient blob) throws Exception {
        long size = Files.size(source);
        try (InputStream in = Files.newInputStream(source)) {
            blob.upload(in, size, false);
        }
    }
}
~~~

`size` phải là tổng số bytes của stream, không được dùng `InputStream.available()` như file length. Với `MultipartFile`, lấy `getSize()` chỉ sau khi server đã áp dụng file-size quota, authentication và validation. Một stream không rewindable làm retry/parallel upload khó hơn; SDK có thể buffer theo configuration, nên phải đo memory/temp usage.

### 8.2. Download vào OutputStream

~~~java
import com.azure.storage.blob.BlobClient;
import java.io.OutputStream;

public final class StreamDownloadExample {
    public static void copyTo(BlobClient blob, OutputStream target)
            throws java.io.IOException {
        blob.downloadStream(target);
        target.flush();
        // Caller sở hữu target, ví dụ Servlet container.
    }
}
~~~

Trong Spring MVC/Servlet, authorize trước khi set response headers và stream. Nếu lỗi xảy ra sau khi đã gửi HTTP headers/bytes, không thể luôn trả JSON `500`: client cần nhận diện transfer bị cắt và có retry/resume strategy. Đo partial downloads/cancellations, không tính mọi response đã có HTTP 200 là thành công.

### 8.3. Tránh đọc toàn tệp lớn vào heap

Giả sử 100 downloads đồng thời, mỗi tệp 200 MiB và đều được đọc hoàn toàn vào byte array:

~~~text
100 × 200 MiB = 20.000 MiB (≈ 19,5 GiB)
chưa tính allocations, HTTP buffers và JVM overhead
~~~

Tránh `readall()`/byte arrays cho file lớn; ưu tiên stream/chunking hoặc SDK async API có backpressure và concurrency cap.

## 9. Đọc blob properties và đồng bộ metadata nghiệp vụ

### 9.1. Đọc HEAD/properties

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.models.BlobProperties;

BlobClient blob = BlobClients.documents()
    .getBlobClient("tenants/t001/reports/report.pdf");

BlobProperties props = blob.getProperties();
System.out.println("Size=" + props.getBlobSize());
System.out.println("ETag=" + props.getETag());
System.out.println("LastModified=" + props.getLastModified());
System.out.println("ContentType=" + props.getContentType());
~~~

`getProperties()` là một request có thể tính phí transaction, trả 403/404 hoặc bị network timeout. Không lặp HEAD cho mỗi buffer chunk nếu không cần.

### 9.2. ETag và version ID khác nhau

- **ETag:** HTTP concurrency validator; có thể đổi sau cập nhật.
- **Version ID:** định danh bản version của blob nếu account bật Blob Versioning và tính năng hỗ trợ.
- **SHA-256/checksum:** giá trị băm dữ liệu giúp kiểm tra nội dung nếu có bản tham chiếu đáng tin.
- **Business object ID:** khóa của ứng dụng để tra metadata và kiểm tra ownership.

Không dùng ETag làm checksum hoặc user authorization. Với trường hợp dữ liệu cần kiểm toán, lưu thông tin traceable của bản upload và checksum từ nguồn tin cậy.

### 9.3. Upload blob và ghi metadata DB không phải một ACID transaction

Một quy trình ổn định:

1. Tạo `upload_intent` ở DB với `PENDING` và một object ID.
2. Upload blob name đã xác định với `overwrite=false` hoặc conditional create.
3. Verify size/checksum/ETag khi policy yêu cầu.
4. Đổi DB status thành `READY` với blob version/ETag đã thu được.
5. Nếu crash giữa bước 2 và 4, reconciliation worker xác minh blob hiện có và trạng thái DB.
6. Cleanup orphan/pending entries sau grace period và audit.
7. Không cho người dùng download tài liệu có trạng thái không hợp lệ.

**Không coi Storage upload và SQL INSERT là transaction phân tán tự động.** Retry cần idempotency key và logic xác nhận theo business intent.


## 10. Tải tệp lớn: block upload, chunking và concurrency

### 10.1. Vì sao không truyền file lớn như byte array?

Giả sử service xử lý 10 uploads đồng thời, mỗi file 2 GiB. Nếu giữ toàn bộ payload trong RAM có thể cần **20 GiB** trước khi tính overhead JVM/HTTP. Với Block Blob, SDK có thể upload theo blocks và commit thành blob hoàn chỉnh.

~~~mermaid
flowchart LR
    F["Large file"]
    S["SDK scheduler\nSplit into blocks"]
    A["Put Block A"]
    B["Put Block B"]
    C["Put Block C"]
    D["Commit Block List"]
    F --> S
    S --> A
    S --> B
    S --> C
    A --> D
    B --> D
    C --> D
~~~

**Ưu tiên phương thức high-level `uploadFromFile`** khi không cần giao thức tải lại đặc biệt. SDK chọn single upload hoặc chia block theo size, options, version và giới hạn dịch vụ. Không giả định một threshold cố định đúng mọi versions.

### 10.2. Single upload và multipart upload

| Thao tác | Nội dung | Khi dùng |
| --- | --- | --- |
| Put Blob | Một request tải nội dung theo giới hạn API | File nhỏ hoặc SDK chọn one-shot |
| Put Block | Stage một chunk được nhận diện bằng block ID | File lớn hoặc resumable |
| Put Block List | Commit danh sách block IDs theo thứ tự | Hoàn tất nội dung mới |
| `uploadFromFile` | SDK tự lập kế hoạch transfer | Đa số ứng dụng |
| `stageBlock` + `commitBlockList` | App quản lý block IDs/chunks | Use case đặc thù cần checkpoints |

Staged blocks chưa commit **không tự đồng nghĩa** file hoàn chỉnh có thể tải. Những limits về block count/block size/retention khác theo REST service version; kiểm tra giới hạn thực khi tải file cực lớn.

### 10.3. Song song không càng nhiều càng tốt

Một số SDK/options cho phép chỉnh:

- Block/chunk size.
- Số request block song song.
- Ngưỡng upload một request.
- HTTP timeout/retry strategy.
- Connection pool và SDK/client lifecycle.

Chọn thông số từ load tests. Tăng concurrency có thể gây throttling, 503, nhiều retries, tăng RAM và ảnh hưởng traffic khác.

Ví dụ giả định:

~~~text
chunk size = 8 MiB
max concurrent block requests per upload = 4
uploads cùng lúc = 6

payload buffer baseline ≈ 8 × 4 × 6 = 192 MiB
~~~

Đây chỉ là **ước lượng**, memory thực còn HTTP buffers, request retry copies, Java heap overhead và ứng dụng. Theo dõi heap, GC, open connections, throughput và 429/503 khi thử tải.

### 10.4. Cấu hình parallel transfer theo SDK version

Trong các phiên bản `azure-storage-blob`, một số transfer options như `ParallelTransferOptions` và `BlobParallelUploadOptions` được hỗ trợ cho các upload APIs. Ví dụ các tham số đáng cân nhắc:

~~~text
block size: 4–8 MiB cho lab để đo
max concurrency: 2–4 làm điểm khởi đầu đo
end-to-end timeout: dựa vào file size và băng thông
retry budget: có giới hạn, exponential backoff
max simultaneous uploads: phải tính cùng max concurrency
~~~

Các giá trị trên là **gợi ý benchmark ban đầu**, không phải defaults hay khuyến cáo toàn dịch vụ. Tên builder/overload khác theo SDK version; phải kiểm tra Javadoc và đo thực tế trước khi đưa vào production.

### 10.5. Ví dụ stage hai blocks và commit

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.specialized.BlockBlobClient;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;

public final class ManualBlockDemo {
    public static void main(String[] args) {
        BlobClient blob = BlobClients.documents()
            .getBlobClient("lab/blocks/demo.txt");
        BlockBlobClient block = blob.getBlockBlobClient();

        byte[][] chunks = {
            "Hello ".getBytes(StandardCharsets.UTF_8),
            "Azure!".getBytes(StandardCharsets.UTF_8)
        };
        List<String> ids = new ArrayList<>();

        for (int i = 0; i < chunks.length; i++) {
            // Raw block IDs có cùng độ dài trước Base64.
            String id = Base64.getEncoder().encodeToString(
                String.format("%06d", i).getBytes(StandardCharsets.UTF_8)
            );
            block.stageBlock(
                id,
                new ByteArrayInputStream(chunks[i]),
                chunks[i].length
            );
            ids.add(id);
        }
        block.commitBlockList(ids);
        System.out.println("Committed blocks=" + ids.size());
    }
}
~~~

**Chỉ chạy với blob lab riêng.** Commit block list có thể thay đổi nội dung blob đã có. Để dùng trên production, phải quản lý upload ID, ordered block IDs, session ownership, concurrency preconditions, integrity, retries và cleanup blocks chưa commit. Không tự viết block scheduler nếu SDK upload high-level đáp ứng nhu cầu.

### 10.6. Resumable khác retry request

**Retry:** khi request lỗi tạm thời, SDK gửi lại operation theo chính sách trong một lượt gọi.

**Resumable:** khi process chết/restart, ứng dụng biết blocks nào đã được staged đúng và chỉ cần tải các phần còn lại, rồi commit một manifest hợp lệ.

Một thiết kế resumable cần giữ:

~~~text
upload_session_id
authorized_tenant_id + object_id
blob_name
expected_file_size + checksum
block_size
ordered_block_ids
staged_block_progress
expiration / cleanup policy
~~~

Không tin manifest do client cung cấp nếu chưa xác thực, không giả định uncommitted blocks tồn tại vô thời hạn hoặc không có giới hạn. Dùng `getBlockList`/API tương đương của version hỗ trợ khi cần xác minh trạng thái staged blocks.

## 11. ETag, optimistic concurrency và conditional download

### 11.1. Kịch bản lost update

~~~text
10:00 Worker A đọc ETag E1
10:01 Worker B đọc ETag E1
10:02 Worker B update blob -> ETag E2
10:03 Worker A upload overwrite từ E1
Kết quả: cập nhật của Worker B có nguy cơ bị mất.
~~~

`If-Match` yêu cầu blob chưa thay đổi so với ETag kỳ vọng. Nếu đã thay đổi, server trả lỗi điều kiện (thường HTTP **412**), phải giải quyết business conflict chứ không remove condition để tiếp tục ghi.

### 11.2. Upload có If-Match

~~~java
import com.azure.core.util.Context;
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.models.BlobRequestConditions;
import com.azure.storage.blob.options.BlobUploadFromFileOptions;
import java.time.Duration;

public final class ConditionalUpdate {
    public static void replaceIfUnchanged(
            BlobClient blob, String file, String expectedETag) {
        BlobUploadFromFileOptions options =
            new BlobUploadFromFileOptions(file)
                .setRequestConditions(
                    new BlobRequestConditions().setIfMatch(expectedETag)
                );

        blob.uploadFromFileWithResponse(
            options, Duration.ofMinutes(10), Context.NONE
        );
    }
}
~~~

Các class/options có thể thay đổi theo SDK version. Cần test với **tệp lớn/block transfer** xem điều kiện được áp dụng đến commit như thế nào; không suy từ một thử nghiệm small upload rằng toàn bộ multi-stage process có tính nguyên tử với các hệ thống khác.

### 11.3. Download có điều kiện

~~~java
import com.azure.core.util.Context;
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.models.BlobRequestConditions;
import com.azure.storage.blob.options.BlobDownloadToFileOptions;
import java.time.Duration;

public final class ConditionalDownload {
    public static void run(
            BlobClient blob, String target, String expectedETag) {
        BlobDownloadToFileOptions options =
            new BlobDownloadToFileOptions(target)
                .setRequestConditions(
                    new BlobRequestConditions().setIfMatch(expectedETag)
                );

        blob.downloadToFileWithResponse(
            options, Duration.ofMinutes(10), Context.NONE
        );
    }
}
~~~

Đây là ví dụ API có điều kiện trong các phiên bản SDK hỗ trợ. Nếu precondition lỗi, **không tự retry bỏ `If-Match`**. Có thể chuyển sang một **version-specific blob client** nếu versioning bật và nghiệp vụ cần snapshot ổn định; cần kiểm tra version ID, API behavior và policy.

### 11.4. Leases và optimistic concurrency khác nhau

Blob leases có thể dùng để điều phối exclusive writer trong một số tình huống, nhưng có quản lý renew/release, expiration, stale lease và recovery. Trong use case thông thường, **unique blob names + create-only + ETag** thường đơn giản hơn. Nếu dùng lease, phải có runbook và kiểm tra authorization.

## 12. Data integrity, checksums và xác minh kết quả

### 12.1. Khác biệt giữa các lớp xác minh

| Tín hiệu | Có ích cho | Không thay thế |
| --- | --- | --- |
| TLS | Mã hóa/xác minh transport | Authorization hoặc kiểm tra file business |
| Content-Length | Kiểm tra số bytes | Cryptographic integrity |
| ETag | Optimistic concurrency | SHA-256 của nội dung |
| Transactional MD5/CRC64 (khi SDK/API hỗ trợ) | Transfer integrity theo service semantics | Trusted source signature |
| SHA-256 từ manifest đáng tin | So sánh bytes với nguồn tin cậy | Auth/NAC/scan |
| Malware scan | Phát hiện một số file nguy hiểm | Bảo đảm không còn mọi rủi ro |

### 12.2. Java tính SHA-256 không giữ toàn bộ file trong RAM

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;

public final class FileDigest {
    public static String sha256(Path path) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        byte[] buffer = new byte[1024 * 1024];

        try (InputStream in = Files.newInputStream(path)) {
            int n;
            while ((n = in.read(buffer)) != -1) {
                if (n > 0) md.update(buffer, 0, n);
            }
        }
        return HexFormat.of().formatHex(md.digest());
    }
}
~~~

Trong một **lab với file bất biến**:

~~~java
String expected = FileDigest.sha256(sourcePath);
blob.uploadFromFile(sourcePath.toString(), false);
blob.downloadToFile(downloadPath.toString(), false);
String actual = FileDigest.sha256(downloadPath);

if (!expected.equalsIgnoreCase(actual)) {
    throw new IllegalStateException("Content integrity mismatch");
}
~~~

Điều kiện cần: file nguồn không bị thay đổi giữa hash và upload. Production có thể cần snapshot/copy vào file tạm bất biến, hoặc hash trong một luồng upload được kiểm soát. **Không coi SHA-256 lưu trong cùng metadata có thể bị sửa như một manifest chống giả mạo**; nơi lưu expected digest phải có trust boundary phù hợp.

### 12.3. Chi phí của round-trip verify

Upload 100 GiB rồi tự download 100 GiB để verify có thể tốn băng thông, thời gian và tiền egress khi chạy ngoài Azure. Tùy criticality, kết hợp SDK transport checks, ETag/size, signed manifests, sampling và periodic verification; không áp dụng một chiến lược tốn kém cho mọi blob.

### 12.4. Quarantine và kiểm duyệt file tải lên

Với upload từ người dùng không tin cậy:

~~~mermaid
flowchart LR
    IN["Upload"]
    Q["Quarantine container"]
    SCAN["Scan + validate"]
    READY["Approved container"]
    META["Metadata READY"]
    DENY["Reject / investigate"]
    IN --> Q --> SCAN
    SCAN -->|"Pass"| READY --> META
    SCAN -->|"Fail"| DENY
~~~

Chỉ publish object khi scanning/validation policy đáp ứng. Malware scanning là một lớp giảm rủi ro, không biến mọi file thành vô hại. Chú ý data residency, permission và độ trễ của scanner.


## 13. Lỗi Blob Storage SDK và chính sách retry

### 13.1. Không phải lỗi nào cũng cần retry

| HTTP status / triệu chứng | Nguyên nhân khả dĩ | Hành động |
| --- | --- | --- |
| `400 Bad Request` | Tên blob/headers/conditions/size không hợp lệ | Sửa request, không retry y nguyên |
| `401 Unauthorized` | Token/key không hợp lệ/hết hạn | Kiểm tra identity/credential, refresh đúng cơ chế |
| `403 Forbidden` | Thiếu data role, SAS permission, network ACL hoặc policy | Phân loại auth vs firewall trước khi tăng quyền |
| `404 Not Found` | Account/container/blob không tồn tại, sai name | Xác minh URI, casing, object state |
| `409 Conflict` | Lease, immutable policy, blob type, trạng thái bị xung đột | Xem error code, giải quyết điều kiện |
| `412 Precondition Failed` | ETag/If-Match/If-None-Match không còn đúng | Không retry bỏ điều kiện; xử lý concurrency |
| `416 Range Not Satisfiable` | Requested download range không hợp lệ | Kiểm tra file size/version |
| `429 Too Many Requests` | Throttling/limits theo dịch vụ hoặc tầng gateway | Backoff/jitter, giảm tải, kiểm tra quota |
| `500/503` | Lỗi tạm thời, quá tải service hoặc dependency | Retry có giới hạn, xem Azure status/metrics |
| Network timeout/connection reset | Mất kết nối trước/giữa/sau transfer | Trạng thái commit chưa chắc; xác minh idempotency |
| `UnknownHostException` | DNS/Private Endpoint/endpoint sai | Sửa DNS/route, không sửa data role |
| TLS handshake error | CA/hostname/network interception | Sửa trust/DNS; không tắt TLS validation |
| File not writable/`AccessDeniedException` local | Local filesystem permission hoặc path conflict | Sửa môi trường local, không liên quan RBAC Blob |

Một HTTP 403 có thể liên quan firewall/network policy, không chỉ Azure RBAC. Xem error code/substatus và diagnostics, nhưng **không in secrets** vào lỗi.

### 13.2. Java xử lý BlobStorageException

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.models.BlobStorageException;

import java.nio.file.Path;

public final class SafeUploadErrors {
    public static void run(Path source, BlobClient blob) {
        try {
            blob.uploadFromFile(source.toString(), false);
        } catch (BlobStorageException ex) {
            int status = ex.getStatusCode();
            String code = String.valueOf(ex.getErrorCode());

            // Production: dùng structured logs với request ID,
            // không log URL có SAS hoặc headers chứa credentials.
            System.err.println(
                "Blob upload failed: status=" + status
                + " code=" + code
            );

            if (status == 403) {
                throw new SecurityException(
                    "Storage authorization or network policy denied request"
                );
            }
            if (status == 409 || status == 412) {
                throw new IllegalStateException(
                    "Blob exists or precondition not satisfied"
                );
            }
            throw ex;
        }
    }
}
~~~

**Đây là cách minh họa phân loại**, không phải một production exception mapper đầy đủ. Cần xử lý client cancellation, non-storage exceptions, dependency timeouts và operations đã commit nhưng mất response; HTTP status 403 có thể có nhiều Storage error codes.

### 13.3. Retry bên trong SDK và tầng ứng dụng

Azure SDK có **retry policy** cho các lỗi được coi là transient theo version/transport. Trước khi thêm vòng retry bên ngoài:

1. Kiểm tra SDK đang tự retry mấy lần, backoff thế nào.
2. Đặt tổng **deadline** của user request/job.
3. Dùng exponential backoff + jitter theo hướng dẫn dịch vụ.
4. Không retry 401/403 do thiếu quyền hoặc 412 do concurrency như lỗi transient.
5. Không nhân retries ở API gateway × app × SDK vô kiểm soát.
6. Gắn idempotency key cho nghiệp vụ có side effects.
7. Đo số attempts, success-after-retry, retry latency và chi phí requests.

Ví dụ vòng retry theo tầng:

~~~text
API Gateway:    3 retries
Application:    3 retries
SDK:            4 attempts

Worst case (nếu không giới hạn chung):
3 × 3 × 4 = 36 HTTP attempts cho 1 thao tác logic
~~~

Đó là lý do phải có retry budget **toàn request**, không chỉ mỗi thư viện.

### 13.4. Timeout nào cần quan tâm?

- Connection timeout: thiết lập kết nối TCP/TLS.
- Read/response timeout: đợi server trả dữ liệu.
- Per-request timeout: giới hạn một HTTP operation.
- Overall transfer deadline: thời gian toàn upload/download file.
- Business request deadline: thời gian HTTP API được phép trả người dùng.
- Job deadline: giới hạn của một batch/background worker.

Timeout nhỏ có thể làm thất bại upload file hợp lệ; timeout quá lớn dẫn tới resources bị giữ lâu. Với file nhiều GB, cân nhắc **asynchronous job + status polling** thay vì giữ một HTTP request quá dài.

### 13.5. Log có cấu trúc, không để lộ credential

Telemetry nên có:

~~~json
{
  "operation": "blob.upload",
  "container": "documents",
  "blobCategory": "invoice",
  "bytes": 1058576,
  "durationMs": 812,
  "attemptCount": 2,
  "statusCode": 201,
  "result": "success",
  "requestId": "opaque-correlation-id"
}
~~~

Đây là **schema ứng dụng tự định nghĩa**, không phải response JSON mặc định từ Azure SDK. Không log account key, SAS query string, OAuth token, full user-provided file path, PII hoặc byte contents. Nếu log blob name chứa tenant ID, kiểm soát quyền đọc/retention.

## 14. Đồng bộ và bất đồng bộ: chọn đúng cơ chế truyền tệp

### 14.1. Sync BlobClient

Dễ đọc và test:

~~~java
BlobClient blob = BlobClients.documents()
    .getBlobClient("lab/examples/hello.txt");

blob.uploadFromFile("data/hello.txt", false);
blob.downloadToFile("data/hello-downloaded.txt", false);
~~~

Trong servlet MVC, upload blocking giữ một thread cho tới khi hoàn tất. Với traffic cao, cần concurrency cap, thread-pool sizing, limits và chuyển long-running uploads sang background workflow.

### 14.2. Tạo async client

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobAsyncClient;
import com.azure.storage.blob.BlobServiceAsyncClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

String account = System.getenv("AZURE_STORAGE_ACCOUNT");

BlobServiceAsyncClient service =
    new BlobServiceClientBuilder()
        .endpoint("https://" + account + ".blob.core.windows.net")
        .credential(new DefaultAzureCredentialBuilder().build())
        .buildAsyncClient();

BlobAsyncClient blob = service
    .getBlobContainerAsyncClient("documents")
    .getBlobAsyncClient("lab/examples/hello.txt");
~~~

Đây là **đoạn tạo client**, chưa thực thi upload. Async APIs thường sử dụng Reactor (`Mono`/`Flux`) và một số data sources phải được biến thành reactive data flows đúng cách. **Không `block()` liên tục trên WebFlux event loop** để “dùng async” theo tên. Check scheduler, bounded concurrency, backpressure và cancellation.

### 14.3. Async không bảo đảm nhanh hơn

Async giúp server dùng ít blocking threads cho nhiều operations I/O-bound, **không tự tăng network băng thông hoặc storage throughput**. Với một tệp đơn lớn, high-level sync transfer có internal parallelism có thể đủ; với hàng nghìn uploads concurrent, reactive workload có thể hữu ích nếu toàn pipeline không-blocking.

So sánh khi benchmark:

- Throughput MB/s và requests/s.
- p95/p99 transfer latency.
- Heap/GC/connection count.
- Thread count, CPU saturation.
- 429/503 và retry rate.
- Client cancellations và backpressure.
- Chi phí transactions/cross-region egress.

### 14.4. Browser direct upload bằng SAS: một phương án khác

Với tệp lớn qua Internet, API proxying mỗi byte có thể tăng tải backend. Có thể:

1. Web client gửi request xin upload.
2. Backend xác thực user, quota, file type và tenant.
3. Backend tạo object ID/blob name an toàn.
4. Backend cấp **SAS token hẹp, thời hạn ngắn** hoặc cơ chế delegated upload được hỗ trợ.
5. Browser upload trực tiếp tới Blob Storage theo quyền SAS và CORS/network policy.
6. Backend xác minh tệp đã commit, size/checksum, scan và metadata.
7. Đánh dấu READY; frontend chỉ được dùng object sau bước xác minh.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant A as Java API
    participant S as Blob Storage
    B->>A: Request upload permission
    A->>A: Auth, tenant, quota, safe name
    A-->>B: Short-lived scoped upload capability
    B->>S: Upload file (HTTPS)
    S-->>B: Upload result
    B->>A: Notify completion
    A->>S: Verify blob/size/metadata
    A-->>B: Object READY or reject
~~~

**Rủi ro:** SAS là bearer credential; ai có URL có thể thử dùng trong giới hạn của token. Scope permission, expiry, start time/clock skew, CORS, network allowlist và max-size enforcement đều cần được đánh giá. SAS có quyền `write` hoặc `create` không tự bảo đảm người dùng không gửi tệp vượt size limit hoặc cố tình tải nội dung sai. Phải kiểm tra server-side sau upload.

### 14.5. User delegation SAS và account SAS

| Loại | Được ký bằng | Đặc điểm |
| --- | --- | --- |
| Service/account SAS | Thường Shared Key | Phụ thuộc account key và access policy |
| **User delegation SAS** | User delegation key liên quan Microsoft Entra | Ưu tiên xem xét khi muốn tránh phát Shared Key |
| URL không SAS | Không có token trong URL | Container private vẫn yêu cầu auth |

Java backend có thể tạo **user delegation SAS** theo APIs/permissions hỗ trợ. Cần identity có role/action cần thiết để lấy user delegation key, và phải giới hạn permissions ở đúng blob/resource/time window. Không dùng SAS rộng cả container khi chỉ một object được phép. Không in full signed URLs vào log.

**Nếu account đã tắt Shared Key authorization**, các loại SAS ký bằng Shared Key có thể không hoạt động; user delegation SAS có điều kiện hỗ trợ riêng. Kiểm tra policy trước khi thiết kế browser upload.

## 15. Security cho upload/download production

### 15.1. Defense in depth

| Lớp | Cơ chế | Không tự thay thế |
| --- | --- | --- |
| Business auth | User/tenant/object permissions trong API | Entra data role cho app |
| Managed identity | OAuth/Entra principal không cần static key | Kiểm tra user nghiệp vụ |
| Azure RBAC data plane | Reader/Contributor tại scope phù hợp | Tenant-level kiểm soát nội dung |
| Private Endpoint/firewall | Hạn chế data path/network | Authentication |
| HTTPS/TLS | Mã hóa truyền và xác minh hostname | Business authorization |
| Content validation/scan | Kiểm tra file upload đáng tin cậy | Network security |
| Versioning/soft delete | Một số phương án hồi phục file sai/xóa nhầm | Chống sửa/xóa đang diễn ra |
| Immutability/retention | Giảm khả năng thay/xóa trong thời hạn policy | Khả năng đọc trái phép |
| Audit/alerts | Theo dõi bất thường | Tự phục hồi dữ liệu |

### 15.2. Private Endpoint và DNS

Một Blob endpoint:

~~~text
stfilesprod001.blob.core.windows.net
~~~

Khi Private Endpoint và Private DNS đúng, hostname có thể đi qua địa chỉ private theo kiến trúc. Zone thường liên quan `privatelink.blob.core.windows.net`. Client phải nằm trong VNet/network có route, hoặc hybrid DNS/forwarding phù hợp.

Linux/macOS:

~~~bash
ACCOUNT="stfilesprod001"
nslookup "$ACCOUNT.blob.core.windows.net"
nc -vz "$ACCOUNT.blob.core.windows.net" 443
~~~

PowerShell:

~~~powershell
Resolve-DnsName stfilesprod001.blob.core.windows.net
Test-NetConnection stfilesprod001.blob.core.windows.net -Port 443
~~~

**Đúng DNS/TCP không đồng nghĩa RBAC đúng**. Storage firewall/public network access policy và Private Endpoint connection approval cần được kiểm tra riêng. Không sửa lỗi private DNS bằng cách tắt TLS certificate validation.

### 15.3. Shared Key và account key rotation

Ưu tiên Entra ID. Khi ứng dụng legacy bắt buộc dùng account key:

- Lưu trong Key Vault/secret manager, không commit vào source.
- Đặt quyền đọc Key Vault tối thiểu và rotation policy.
- Tách keys cho dev/staging/prod.
- Chuẩn bị chuyển đổi primary/secondary keys với kiểm thử.
- Không in `AZURE_STORAGE_CONNECTION_STRING` hoặc full key vào logs.
- Xem khả năng tắt `allowSharedKeyAccess` sau khi đã migrate clients.

Không regenerate key đang được ứng dụng dùng mà chưa có kế hoạch cập nhật clients. Các loại SAS ký bằng account key cũng có thể bị ảnh hưởng khi rotate.

### 15.4. Blob soft delete, versioning và immutable data

**Soft delete** và **versioning** (khi SKU/account features hỗ trợ) giúp recovery khỏi một số thao tác xóa hoặc overwrite, nhưng không thay backup/DR và compliance plan. Cần hiểu retention, restore semantics, additional storage costs và policy của account.

Một số container/blob có **immutability policy/legal hold** để ngăn sửa/xóa theo thời hạn hoặc yêu cầu pháp lý. Điều này có thể làm upload overwrite/delete lỗi 409/403 dù app có RBAC Contributor. **Đừng xóa/thay immutability policy** để “chữa” upload lỗi nếu dữ liệu thuộc yêu cầu giữ chứng từ.

### 15.5. Data classification, scan và Content-Disposition

- Xác thực user trước upload/download.
- Giới hạn MIME, size, extension và kiểm tra file signature.
- Không hiển thị HTML/SVG từ user như nội dung tin cậy nếu không có sanitization.
- Scan malware trước publish.
- Với download tệp không tin cậy, dùng `attachment`/naming policy phù hợp.
- Không ghi secrets/PII vào filename, metadata hoặc SAS logs.
- Theo dõi object expiration/retention theo quy định.
- Khi dữ liệu có tenant isolation mạnh, xem xét container/account separation theo threat model.

### 15.6. Không sử dụng public container để bỏ qua authorization

Container public access làm dữ liệu đọc được mà không cần user token theo những điều kiện account/container policy. **Không bật public container cho hóa đơn, hồ sơ nhân sự hoặc báo cáo nhạy cảm**. Với file public thật, vẫn cần quản lý riêng, lifecycle và quyền upload hạn chế.


## 16. Hiệu năng: latency, throughput và capacity planning

### 16.1. Đo đúng đơn vị

Với thao tác upload/download:

- **End-to-end duration:** từ lúc app bắt đầu transfer đến lúc hoàn tất và xác minh.
- **Payload bytes:** kích thước file thực gửi/nhận.
- **Throughput:** số MiB/s của một transfer hoặc tổng transfers.
- **Concurrent transfers:** số lượng upload/download đang hoạt động.
- **Retry count:** số attempts thêm do lỗi tạm thời.
- **p50/p95/p99 latency:** độ trễ theo cohort file size/region/task.
- **Failure/partial transfer rate:** tệp lỗi hoàn toàn hoặc dở dang.
- **Memory/heap peak:** byte buffers và số file song song.
- **Remote dependency latency:** thời gian Blob service/HTTP operations so với xử lý file local.

Với một tệp 1.024 MiB tải trong 16 giây:

\[
\text{Throughput} = \frac{1024\ \mathrm{MiB}}{16\ \mathrm{s}}=64\ \mathrm{MiB/s}
\]

Đây là phép tính đơn giản của **payload throughput**; chưa gồm retry bytes, encoding, network overhead và thời gian kiểm tra scan/hash nếu mốc đo không bao gồm chúng.

### 16.2. Đo thời gian upload bằng System.nanoTime

~~~java
import com.azure.storage.blob.BlobClient;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;

public final class TimedTransfer {
    public static void upload(Path source, BlobClient blob)
            throws Exception {
        long bytes = Files.size(source);
        long start = System.nanoTime();

        blob.uploadFromFile(source.toString(), false);

        long elapsedNanos = System.nanoTime() - start;
        double seconds = elapsedNanos / 1_000_000_000.0;
        double mibPerSec = (bytes / 1_048_576.0) / seconds;

        System.out.printf(
            "bytes=%d durationMs=%d throughputMiBs=%.2f%n",
            bytes,
            TimeUnit.NANOSECONDS.toMillis(elapsedNanos),
            mibPerSec
        );
    }
}
~~~

Mẫu code có thể báo `Infinity`/bất thường nếu elapsed gần zero với file quá nhỏ; chỉ dùng cho lab. Production dùng Micrometer/OpenTelemetry histograms và spans, tag bằng file-size bucket/operation, không đặt nguyên filename hoặc user ID làm high-cardinality metric labels.

### 16.3. Benchmark một cách có ý nghĩa

Để so sánh các transfer options:

1. Dùng files đại diện: 64 KiB, 1 MiB, 64 MiB, 1 GiB.
2. Cùng region/network route, kiểm tra RTT và băng thông egress.
3. Ghi JVM version, SDK version, client HTTP transport và app replica count.
4. Test concurrency 1, 4, 8... trong giới hạn an toàn.
5. Ghi p95/p99, throughput, heap/GC, 429/503, retries.
6. Test với network loss/throttling mô phỏng trên staging.
7. Không benchmark trực tiếp bằng cách flood production storage account.
8. So sánh **chi phí và correctness** chứ không chỉ MB/s.

Nếu một thông số nâng throughput 10% nhưng tăng 3× RAM, 429 và cost, nó có thể không phù hợp trong production.

### 16.4. Region affinity

Ứng dụng và Storage ở khác regions có thể tăng network latency, egress, data sovereignty risks và chi phí. Nếu có thể, đặt compute gần Storage theo requirements. Khi cần cross-region replication, đọc đúng **account redundancy model** và RPO/RTO: replication không thay nhiệm vụ kiểm tra xóa nhầm/backup.

### 16.5. Tối ưu download range và resumability

Với các use case tải file lớn, Azure Blob hỗ trợ **range reads** theo API. Một client có thể lưu progress, ETag/version và tải lại những ranges chưa đủ, nhưng phải:

- Cố định phiên bản blob hoặc dùng conditional requests.
- Xác minh offset/length và file size.
- Tránh nối ranges thuộc hai ETag khác nhau.
- Kiểm tra tổng checksum khi hoàn tất.
- Quản lý parallel range downloads và backpressure.
- Tính request transaction cost do nhiều range calls.

Đừng dùng range download để đọc file đã đổi nội dung mà không biết; dữ liệu ghép có thể bị trộn giữa các versions.

### 16.6. Chọn sync/async theo concurrency

| Bối cảnh | Lựa chọn khởi điểm | Vì sao |
| --- | --- | --- |
| CLI utility tải 1–20 files | Sync BlobClient | Dễ lập trình, đủ hiệu quả |
| Spring MVC API upload vừa/nhỏ | Sync với thread pool/quota | Dễ quản lý lifecycle |
| WebFlux reactive pipeline | BlobAsyncClient + reactive stream | Giảm block event loop nếu đúng toàn pipeline |
| Upload nhiều file lớn | High-level parallel upload + scheduler có quota | Kiểm soát concurrent transfers |
| Browser upload nhiều GiB | Scoped SAS + direct-to-Blob, verify server-side | Tránh proxy body qua Java backend |
| Data ingestion liên tục | Batch/event-driven app + checkpoints | Cần idempotency và vận hành dài hạn |

Không dùng async chỉ vì “nhiều” request: performance cần được chứng minh bởi workload test.

## 17. Monitoring, logging và chi phí Blob Storage

### 17.1. Ba lớp quan sát

1. **Application telemetry:** operation, payload size, duration, retries, errors, object ID (opaque), client cancellations.
2. **Azure Storage metrics:** transactions, ingress/egress, latency, availability, error/throttling patterns theo các metrics được dịch vụ hỗ trợ.
3. **Control-plane/security logs:** resource/network/role/key changes, diagnostic settings, access failures và audit.

Azure Monitor không tự biết **user của ứng dụng** là ai và có quyền xem object nào nếu backend không ghi correlation metadata phù hợp. Đồng thời Azure Activity Log **không phải bản sao của mọi data-plane Blob operation**; bật Storage diagnostic categories phù hợp theo policy.

### 17.2. Những chỉ số nên lên dashboard

| Metric | Tín hiệu |
| --- | --- |
| Upload duration p95 theo size bucket | Tệp lớn có chậm bất thường? |
| Download duration p95 | Người dùng chờ bao lâu? |
| MiB/s và operations/s | Có đạt throughput target? |
| 401/403/404/409/412 | Authentication, authorization, path, conflicts |
| 429/503 và retry count | Throttling hoặc service/network load |
| Client cancellations/partial transfers | User bỏ dở hoặc network mất |
| Storage availability | Service có trả lỗi hay không? |
| Success E2E latency / server latency | Độ trễ do service vs client/network |
| Storage capacity, egress | Growth và budget |
| Failed malware scans | Chất lượng/bảo mật nội dung |
| SAS/key/role changes | Truy cập trái policy hoặc drift |
| Soft delete/version counts | Dữ liệu có phát sinh phiên bản/xóa nhiều? |

Tên metrics/dimensions tùy tài nguyên và thời điểm. Dùng `az monitor metrics list-definitions` hoặc Azure Portal để xác minh, không giả định mọi metric có sẵn cho mọi SKU.

### 17.3. Azure CLI đọc metric definitions

~~~bash
STORAGE_ID=$(az storage account show \
  --resource-group "$RG" \
  --name "$ACCOUNT" \
  --query id -o tsv)

az monitor metrics list-definitions \
  --resource "$STORAGE_ID" \
  -o table
~~~

Một số **Blob service metrics** có thể nằm ở child resource scope theo API/provider; xem resource ID/metric definitions thực trước khi dùng tên cụ thể. Không coi output rỗng ở storage account scope là “Storage không có metrics”.

### 17.4. Application Insights và distributed traces

Với Java trên Azure, có thể dùng **Application Insights Java agent**, **OpenTelemetry instrumentation** hoặc integration được phê duyệt. Trace nên liên kết:

~~~text
Trace: POST /documents/upload
  Span: authentication
  Span: validate-file
  Span: blob.upload
    bytes: 157286400
    container: documents
    blobCategory: invoice
    status: success
    durationMs: 1850
    attemptCount: 2
  Span: database.update-metadata
  Span: send-response
~~~

Không ghi blob content, account keys, SAS query string, access tokens hay PII vào span attributes. `attemptCount` cần lấy từ instrumentation thực, không tự gán `1` khi SDK đã retry bên trong mà app không biết.

### 17.5. HTTP logging phải bảo vệ secrets

Azure SDK có thể hỗ trợ HTTP logging configuration. Không bật full request/response body hoặc headers nhạy cảm trên production. Nếu ghi URL, **redact SAS query parameters**. Azure diagnostics có thể lưu IP/client context; giới hạn retention và quyền Log Analytics workspace.

### 17.6. Các nguồn chi phí

| Khoản | Driver |
| --- | --- |
| Stored GiB/month | Capacity, redundancy, access tier |
| Write operations | Put Blob, Put Block, Put Block List và requests khác |
| Read operations | Get Blob/Properties/range operations |
| Data retrieval | Phụ thuộc online/cold tier, operation type |
| Egress | Tải dữ liệu ra Internet/cross-region theo giá |
| Early deletion | Một số cold/archive tiers có minimum retention |
| Versioning/soft delete | Giữ nhiều versions và soft-deleted content |
| Storage transactions | Nhiều files nhỏ, retry hoặc metadata HEADs |
| Monitoring | Diagnostic logs/Log Analytics ingestion |
| Private Endpoint/network | Endpoint/network charge |
| App compute | CPU/RAM, replicas và transfer workers |

**Không dùng số USD cố định** làm giá Azure vì giá phụ thuộc region, tier, redundancy, thời gian và hợp đồng. Dùng Pricing Calculator, Azure Cost Management và metric usage của resource thật.

### 17.7. Công thức ước lượng throughput/cost sơ bộ

Giả sử một ứng dụng nhận 10.000 files/ngày, trung bình 5 MiB mỗi file:

\[
10{,}000 \times 5\ \mathrm{MiB} = 50{,}000\ \mathrm{MiB/ngày}
\]

Tương đương khoảng 48,8 GiB payload/ngày (vì 1 GiB = 1.024 MiB), **chưa tính versions, replication/storage redundancy hoặc metadata**.

Trong 30 ngày không xóa dữ liệu:

\[
48{,}8\ \mathrm{GiB/day} \times 30 \approx 1{,}464\ \mathrm{GiB}
\]

Đây là ví dụ giả định cho capacity planning, không phải hóa đơn. Chi phí còn có writes/reads, retrieval, network, soft delete/versioning và monitoring.

### 17.8. FinOps và bảo mật đi cùng nhau

- Không tắt diagnostic logs quan trọng chỉ để giảm tiền mà chưa xem audit requirements.
- Dùng lifecycle policies khi đã kiểm tra business retention/retrieval SLA.
- Chọn access tier dựa trên frequency of access và rehydration latency.
- Không cấp SAS dài hạn để tiết kiệm một request API.
- Tối ưu số block requests/tệp nhỏ khi nhiều transaction costs.
- Dọn files tạm và orphan uploads sau review, không xóa dữ liệu thuộc legal hold.
- Gắn tags/owner cho storage accounts, budget alerts và capacity forecasts.


## 18. Kiểm thử upload/download trước production

### 18.1. Ma trận test

| Test | Kết quả mong đợi |
| --- | --- |
| Upload file 1 KiB với Blob Data Contributor | Thành công, content length khớp |
| Download file với Blob Data Reader | Bytes đúng |
| Upload lại blob cùng tên với overwrite=false | Bị từ chối, blob ban đầu không đổi |
| Upload bằng identity chỉ có Reader | Bị từ chối |
| Download blob không tồn tại | 404 hoặc lỗi tương ứng |
| Upload với ETag cũ | 412/condition failure |
| Mất network khi upload gần hoàn tất | Không tạo duplicate, reconcile trạng thái |
| File vượt max size | Bị từ chối trước khi tiêu thụ nhiều tài nguyên |
| File `.pdf` chứa nội dung nguy hiểm | Không publish; scan/validation |
| Download tới local file có sẵn với overwrite=false | Không thay file cũ |
| Output path nằm ngoài thư mục được phép | Bị từ chối |
| User A download object của tenant B | Business authorization từ chối |
| Upload file 5 GiB theo stream/file transfer | Không nạp cả file vào heap |
| Tăng concurrency | Throughput cải thiện hoặc được giới hạn an toàn |
| 429/503 tạm thời | Retry có giới hạn; metrics có attempts |
| Permanent 403 | Không retry vô hạn |
| Blob bị archived | Không kỳ vọng download ngay |
| Soft-deleted/versioned object | Recovery theo policy, không tự phá retention |
| Sai checksum sau download | Fail validation, không chuyển READY |
| SAS hết hạn hoặc vượt scope | Bị từ chối |
| Client hủy giữa stream | Ghi partial transfer, cleanup đúng |
| Network chỉ private | DNS/TLS và Private Endpoint hoạt động từ workload |

### 18.2. Unit tests, integration tests, chaos tests

**Unit tests:** mock wrapper quanh Blob client để kiểm tra business authorization, tenant-scope paths, status PENDING/READY, retry decisions, quota và exception mapping. Không coi mocks là bằng chứng Azure networking/RBAC hoạt động.

**Integration tests:** dùng storage account lab thực để kiểm tra upload/download/conditions với đúng Entra identities. Không dùng Shared Key để chứng minh một Blob Data Reader không thể ghi.

**Chaos/performance tests:** network disconnect, 503/throttling mô phỏng, nhiều files đồng thời, limits, memory pressure và recovery. Chỉ chạy trong môi trường và tải được phê duyệt.

### 18.3. Test idempotency

~~~text
Given:
  Object ID O1, blob name tenants/t001/O1.pdf
  Local file content F, upload_intent=PENDING

When:
  Upload lần đầu commit thành công, client mất response

Then:
  Retry không được tạo O2 vô ý
  App kiểm tra O1, đối chiếu size/checksum/properties
  Nếu đúng: PENDING -> READY
  Nếu khác: báo conflict/integrity failure
~~~

### 18.4. Negative authorization bắt buộc

~~~text
Given:
  User A được phép xem O1 thuộc tenant A
  User B không được phép xem O1

When:
  User B gọi GET /documents/O1

Then:
  API từ chối trước khi gọi Blob SDK
  Không lộ account key, signed URL hoặc blob name
~~~

**Một identity ứng dụng có Blob Data Contributor không đồng nghĩa mọi user cuối được download mọi blob.** Business-layer authorization phải đi trước storage access.

### 18.5. Cleanup không được phá dữ liệu chung

Tạo prefix `integration-tests/<run-id>/` và giữ inventory để dọn. Có approval trước khi xóa; nhớ rằng soft delete/versioning có thể vẫn giữ dung lượng tính phí. Không xóa container hoặc resource group production và không tháo legal hold vì test cleanup.

## 19. Runbook xử lý sự cố theo từng lớp

### 19.1. Thu thập sự kiện an toàn

Ghi thông tin không nhạy cảm:

~~~text
timestamp_utc
subscription_id, resource_group
storage_account, container
opaque_object_id, safe_blob_name
auth_mode (Entra / SAS / Shared Key)
principal_object_id (nếu được phép)
sdk_version, app_release
http_status, StorageErrorCode
x-ms-request-id, client_request_id
elapsed_ms, bytes, attempts
~~~

Không dán raw account keys, OAuth tokens, SAS URLs hoặc tài liệu riêng tư vào logs/tickets.

### 19.2. Bước 1 — Kiểm tra đúng Azure account

~~~bash
az account show \
  --query "{name:name,id:id,tenantId:tenantId}" -o json

az storage account show \
  --resource-group "$RG" \
  --name "$ACCOUNT" \
  --query "{name:name,location:location,publicNetworkAccess:publicNetworkAccess,allowSharedKey:allowSharedKeyAccess}" \
  -o json
~~~

CLI trên laptop có thể dùng developer identity, còn app ở AKS/App Service dùng managed identity khác. Không kết luận quyền runtime chỉ từ thành công của local CLI.

### 19.3. Bước 2 — DNS và TCP/TLS

~~~bash
nslookup "$ACCOUNT.blob.core.windows.net"
nc -vz "$ACCOUNT.blob.core.windows.net" 443
~~~

Nếu private-only account, thực hiện kiểm tra từ đúng VNet/Pod/VM. Kiểm tra Private Endpoint approval, Private DNS Zone links, hybrid forwarding, NSG, routes và firewall. DNS/TCP đúng **chưa đủ** để xác nhận quyền đọc/ghi.

### 19.4. Bước 3 — Đọc status và error code

| Tình huống | Tập trung điều tra |
| --- | --- |
| 401 | Identity token/credential |
| 403 | RBAC data role, SAS scope/expiry, network ACL |
| 404 | Container/blob name, case, object state |
| 409 | Lease/immutability/blob type/concurrent operation |
| 412 | ETag/If-Match/If-None-Match |
| 416 | File size/range/version |
| 429/503 | SDK retry, quota, network/service load |
| Timeout | Chưa biết request đã commit hay chưa |
| Local filesystem error | File permission/path/space, không phải Azure RBAC |

Không dùng account primary key hoặc public container làm workaround chung cho 403.

### 19.5. Bước 4 — Xác minh commit khi timeout

1. Giữ object ID/blob name không thay đổi.
2. Truy vấn properties bằng identity hợp lệ.
3. Đối chiếu size, ETag, trusted checksum/manifest và upload intent.
4. Nếu đã commit đúng, đánh dấu READY.
5. Nếu chưa, retry cùng idempotency key và conditional create có deadline.
6. Nếu nội dung khác, dừng và báo integrity conflict.
7. Dọn orphan blocks/files sau grace period và authorization review.

### 19.6. Bước 5 — Điều tra performance

- Blob operations được đo p50/p95/p99 theo kích thước file?
- File có nhiều blocks/range calls quá nhỏ?
- Concurrency/heap/GC/HTTP connections có quá tải?
- Nhiều retries hoặc double retries?
- Client/Storage có cùng region hoặc cần cross-region?
- Tệp có ở Archive/Cold tier hay cần rehydrate?
- Có network/Private Endpoint bottleneck?
- SDK/client có bị tạo mới mỗi request?
- Có malware scan hoặc checksum verification làm tăng end-to-end time?

Sửa bottleneck có bằng chứng; không tự tăng concurrency hoặc giới hạn timeout rất lớn để che lỗi.

### 19.7. Bước 6 — Hậu kiểm

- Upload/download đáp ứng mục tiêu thời gian.
- SHA-256/manifest theo policy khớp.
- RBAC, tenant authorization và private networking còn đúng.
- 429/5xx/retries và partial transfer không tăng bất thường.
- Không có orphan hoặc duplicate object do retry.
- Storage cost/egress/transactions phù hợp dự toán.
- Alerts, audit, soft delete/versioning và retention vẫn hoạt động.


## 20. Lab tổng hợp: upload, download và kiểm tra SHA-256

### 20.1. Môi trường mẫu

~~~text
Module: Azure SDK cho Java
Language: Java 17+
Storage account: stfileslabunique001
Container: documents (private)
Identity: Microsoft Entra ID / managed identity
Azure data role: Storage Blob Data Contributor, scope phù hợp
Local source: data/sample.pdf
Blob: lab/java-sdk/<uuid>.pdf
Download: downloads/sample-copy.pdf
~~~

Các tên tài nguyên là **ví dụ**; người học chỉ chạy nếu có Storage account lab và quyền được phê duyệt. Nếu chưa có Azure access, có thể giải quyết các câu hỏi thiết kế mà không tạo tài nguyên.

### 20.2. Các bước thực hiện

| Bước | Việc làm | Bằng chứng |
| --- | --- | --- |
| 1 | Kiểm tra `az account show`/subscription | Context Azure đúng |
| 2 | Kiểm tra Storage account `show` | Có account/region/network policy |
| 3 | Xác minh `documents` container private | Không có anonymous read |
| 4 | Kiểm tra data-plane role của principal | Reader/Contributor đúng scope |
| 5 | Xác minh DNS/TLS/private route | Kết nối đúng Blob endpoint |
| 6 | Thêm Maven dependencies/BOM | Build resolution thành công |
| 7 | Tạo `BlobClients` dùng DefaultAzureCredential | Không cần account key |
| 8 | Sinh tên object unique | Không trùng, không dùng user filename |
| 9 | Upload bằng `uploadFromFile(..., false)` | ETag/size phản hồi hợp lệ |
| 10 | Đọc BlobProperties | Content type, length, ETag |
| 11 | Download về tên file mới | Không overwrite output cũ |
| 12 | Tính SHA-256 source và downloaded | Hashes giống nhau |
| 13 | Thử upload lại same name | Bị từ chối, không đổi nội dung |
| 14 | Test với Reader identity upload | Bị từ chối |
| 15 | Test download blob không tồn tại | 404 được xử lý đúng |
| 16 | Test update với stale ETag | 412 được xử lý |
| 17 | Xem Azure Monitor/SDK request telemetry | Latency, failures, bytes |
| 18 | Dọn prefix lab khi được phép | Không xóa dữ liệu khác |

### 20.3. Ghép lại các chương trình Java

Dùng cùng một project chứa `BlobClients`, `UploadFileExample`, `DownloadFileExample` và `FileDigest` được minh họa ở các mục trước.

Quy trình:

~~~text
Local source file
  ↓ calculate trusted SHA-256 (source stable)
UploadFileExample: create-only
  ↓ get ETag/size
Metadata DB: mark pending/ready after validation
  ↓
DownloadFileExample: new destination
  ↓ calculate SHA-256
Compare expected vs downloaded
  ↓
Record result and cleanup lab
~~~

Nếu bản checksum khác, bài lab **không đạt**. Không tự chép expected hash từ metadata bị user kiểm soát khi use case yêu cầu integrity đáng tin.

### 20.4. Kiểm chứng throughput

Chọn tệp có kích thước đại diện, ví dụ 1 MiB, 64 MiB, 1 GiB. Dùng `System.nanoTime()` để đo duration, tính:

\[
\text{MiB/s}=\frac{\text{bytes}/1{,}048{,}576}{\text{duration seconds}}
\]

Với một upload 64 MiB trong 4 giây, throughput ≈ **16 MiB/s**. Đây chỉ là phép tính từ kết quả giả định, không thể kết luận SKU/network nào chắc chắn đạt số này.

### 20.5. Tình huống A — OutOfMemoryError khi nhận file lớn

**Triệu chứng:** Spring Boot nhận tệp 5 GiB, gọi `MultipartFile.getBytes()`, nhiều HTTP requests đồng thời làm heap tăng mạnh.

**Giải pháp:** stream/file-backed upload, hạn chế số transfers, giới hạn request size và quotas, đo heap/GC. Với luồng rất lớn, cân nhắc browser direct upload qua SAS có scope ngắn và verify server-side.

### 20.6. Tình huống B — Upload trả timeout nhưng blob đã tồn tại

**Nguyên nhân có thể:** server commit thành công, phản hồi bị mất. **Giải pháp:** dùng cùng upload ID/name, kiểm tra properties/checksum và hoàn tất pending metadata, không tạo một blob khác cho cùng nghiệp vụ.

### 20.7. Tình huống C — Client có Azure Reader nhưng không tải được

**Nguyên nhân có thể:** Reader management plane không tự có quyền đọc blob data. Hoặc firewall, SAS, credential sai. **Giải pháp:** kiểm tra auth mode, data RBAC Reader/container scope, endpoint và network. Không phát Shared Key.

### 20.8. Tình huống D — Worker ghi đè mất cập nhật

Hai workers cùng cập nhật một blob. **Giải pháp:** `If-Match` và ETag với optimistic concurrency; xử lý 412 theo business conflict, không retry overwrite vô điều kiện.

### 20.9. Tình huống E — Blob download checksum sai

**Giải pháp:** dừng publish, so expected SHA-256 từ manifest tin cậy với downloaded content. Kiểm tra nguồn file có thay đổi không, ETag/version có đúng không, SDK operation có bị cắt/partial không.

### 20.10. Tình huống F — SAS cho browser vượt quyền

API cấp URL SAS cho cả container thay vì đúng một blob và thời hạn ngắn. **Giải pháp:** xác thực user/tenant, chỉ cấp scope/permissions cần thiết, giới hạn TTL, verify content sau upload và không log signed URI.

### 20.11. Tình huống G — Download từ Archive không thành công

**Giải pháp:** xem access tier, rehydration semantics và early deletion/retrieval cost. Thông báo cho người dùng về tiến trình thay vì retry `downloadToFile` vô hạn.

### 20.12. Tình huống H — Chi phí tăng sau bật versioning

**Nguyên nhân:** overwrite tạo thêm versions, retention giữ thêm soft-deleted content, operations và egress tăng. **Giải pháp:** kiểm kê version counts/usage, lifecycle/retention policy và Cost Management; không xóa dữ liệu pháp lý chỉ để giảm phí.

## 21. Câu hỏi tự kiểm tra

**Câu 1.** `BlobServiceClient`, `BlobContainerClient` và `BlobClient` khác nhau?

**Trả lời:** Client theo cấp service account, container và blob riêng lẻ; thao tác upload/download thường qua BlobClient.

**Câu 2.** Khi nào dùng Block Blob?

**Trả lời:** Cho phần lớn tệp thường như PDF, ảnh, CSV; SDK có thể upload nhiều blocks khi tệp lớn.

**Câu 3.** Append Blob có phải lựa chọn đúng cho mọi file `.log`?

**Trả lời:** Không. Chọn theo cách ghi/append, độ lớn, khả năng cập nhật, API limits và giá.

**Câu 4.** Có thể tạo `BlobClient` mà container chưa tồn tại không?

**Trả lời:** Có thể tạo client handle, nhưng operation sẽ thất bại nếu container không tồn tại hoặc quyền không đủ.

**Câu 5.** Vì sao ưu tiên DefaultAzureCredential/managed identity?

**Trả lời:** Giúp tránh nhúng Storage account keys dài hạn trong ứng dụng, có thể quản trị quyền qua Microsoft Entra và Azure RBAC.

**Câu 6.** Azure management Reader có tự đọc private blobs bằng Entra token không?

**Trả lời:** Không. Cần quyền data-plane phù hợp như Storage Blob Data Reader hoặc đường auth hợp lệ khác.

**Câu 7.** `uploadFromFile(path, false)` có ý nghĩa gì?

**Trả lời:** Upload từ file, yêu cầu không ghi đè blob hiện có; hữu ích khi tránh collisions.

**Câu 8.** Có nên dùng `blob.exists()` rồi upload như khóa chống race duy nhất không?

**Trả lời:** Không. Có thể có request khác tạo blob giữa hai thao tác; dùng create-only/If-None-Match như precondition phía server.

**Câu 9.** `If-None-Match: *` và `If-Match: ETag` khác gì?

**Trả lời:** If-None-Match yêu cầu blob chưa có; If-Match cho update chỉ khi blob vẫn khớp ETag kỳ vọng.

**Câu 10.** Khi nhận HTTP 412 có nên retry bỏ điều kiện không?

**Trả lời:** Không. Đó là xung đột/precondition failure cần xử lý nghiệp vụ.

**Câu 11.** ETag có phải checksum SHA-256 không?

**Trả lời:** Không. ETag hỗ trợ concurrency/caching; hash đáng tin dùng để xác minh bytes.

**Câu 12.** Tại sao không dùng `InputStream.available()` làm content length?

**Trả lời:** Nó mô tả bytes có thể đọc mà không blocking theo stream implementation, không đảm bảo tổng kích thước.

**Câu 13.** Vì sao không đọc cả file 10 GiB vào byte array?

**Trả lời:** Dễ vượt heap, tăng GC và không chịu được nhiều uploads đồng thời; dùng stream hoặc SDK file/chunk transfers.

**Câu 14.** Stage block có đồng nghĩa block blob đã commit chưa?

**Trả lời:** Không. Các block cần được commit theo danh sách/thứ tự để thành nội dung blob.

**Câu 15.** Retry request có đồng nghĩa resumable sau process crash không?

**Trả lời:** Không. Resumable cần checkpoint/manifest và xác minh staged/committed parts qua sessions.

**Câu 16.** Sau khi timeout upload, có thể kết luận blob chưa tồn tại?

**Trả lời:** Không. Azure có thể đã commit; cần kiểm tra object theo idempotency key.

**Câu 17.** `downloadToFile(path, false)` giúp gì?

**Trả lời:** Tránh overwrite file local tồn tại, nhưng ứng dụng vẫn phải kiểm soát path traversal và quyền file system.

**Câu 18.** Khi nào nên dùng BlobAsyncClient?

**Trả lời:** Khi pipeline ứng dụng non-blocking/reactive và concurrent workload hưởng lợi, với quản lý backpressure/lifecycle đúng; không tự bảo đảm nhanh hơn sync.

**Câu 19.** Vì sao không nên log full SAS URL?

**Trả lời:** SAS là bearer credential; URL bị lộ có thể cho phép truy cập trong phạm vi và thời hạn của token.

**Câu 20.** Có nên cấp SAS đọc cả container khi user chỉ được đọc một hóa đơn?

**Trả lời:** Không. Cấp scope/permission/time phù hợp đúng object và kiểm tra business authorization.

**Câu 21.** Vì sao Private Endpoint không thay thế RBAC?

**Trả lời:** Private Endpoint kiểm soát đường mạng; identity/data RBAC vẫn quyết định quyền đọc/ghi.

**Câu 22.** HTTP 403 luôn là thiếu data role?

**Trả lời:** Không. Có thể do network ACL, SAS expiry/scope hoặc policy khác; xem error code và request context.

**Câu 23.** Khi blob ở Archive, làm sao tải về?

**Trả lời:** Theo cơ chế được hỗ trợ phải rehydrate sang online tier khi cần, có thời gian/chi phí; không xem như download tức thời.

**Câu 24.** Blob soft delete/versioning có giúp chống mọi xóa nhầm không?

**Trả lời:** Chúng hỗ trợ một số kịch bản phục hồi khi được bật và trong retention; không thay authorization, backup/DR hoặc immutability policy.

**Câu 25.** Vì sao upload blob và ghi một SQL row có thể không nhất quán?

**Trả lời:** Hai dịch vụ không tham gia một transaction ACID mặc định; cần PENDING/READY, idempotency và reconciliation.

**Câu 26.** Cần theo dõi những chỉ số nào khi upload chậm?

**Trả lời:** Duration theo size, MB/s, concurrency, retries, 429/503, network, heap/GC, SDK version và storage metrics.

**Câu 27.** Đơn giá Storage phụ thuộc chỉ số nào?

**Trả lời:** Capacity, redundancy, tier, read/write transactions, retrieval, network egress, versions/soft-delete và monitoring, tùy region/thời điểm.

**Câu 28.** Khi nào phải dùng user delegation SAS thay vì proxy bytes qua Java API?

**Trả lời:** Khi có use case direct-to-Blob và backend có thể cấp quyền hẹp với Entra/user delegation, kiểm tra file sau upload và đáp ứng network/CORS/security policy.

## 22. Checklist trước production

- [ ] Storage account/container private, correct region và redundancy.
- [ ] Managed identity/Entra được cấu hình; data RBAC theo scope tối thiểu.
- [ ] Không có account key/SAS long-lived trong code, image hoặc logs.
- [ ] Azure Blob SDK/BOM versions được pin và kiểm tra compatibility.
- [ ] BlobServiceClient/BlobContainerClient được tái sử dụng.
- [ ] Blob names sinh server-side, object ID và tenant được ủy quyền.
- [ ] Giới hạn file size/MIME, scan và quarantine theo policy.
- [ ] Upload create-only hoặc update conditional theo business semantics.
- [ ] Idempotency/reconciliation xử lý timeout sau commit.
- [ ] Download path/file output được sandbox và không overwrite tùy ý.
- [ ] Stream/chunking và concurrency có limits tránh OOM.
- [ ] SHA-256/ETag/version được dùng đúng mục đích.
- [ ] Retry budget, timeout, cancellation và partial transfers được thiết kế.
- [ ] Private Endpoint/DNS/TLS và public access policy được kiểm tra.
- [ ] Soft delete/versioning/retention và restore drills theo rủi ro dữ liệu.
- [ ] Metrics/logs/alerts, cost budget và owner đã rõ.
- [ ] Có negative tests cho Reader, cross-tenant access và stale ETag.
- [ ] Có runbook recovery và cleanup an toàn.

## Ghi nhớ

- **Azure Blob Storage SDK cho Java** cung cấp clients theo cấp service/container/blob; **Block Blob** là lựa chọn phổ biến cho tệp.
- **DefaultAzureCredential + managed identity + Storage Blob Data RBAC** giúp tránh secrets hard-code, nhưng ứng dụng vẫn phải kiểm tra quyền user/tenant.
- `uploadFromFile(..., false)`, `downloadToFile(..., false)` và **If-None-Match/If-Match** giúp tránh ghi đè và giải quyết optimistic concurrency theo đúng tình huống.
- **File lớn** cần stream/chunks và concurrency có giới hạn. SDK có thể tự stage blocks/commit; manual block upload chỉ khi cần checkpoint/custom workflow.
- **ETag không phải SHA-256**. Với dữ liệu quan trọng, so bytes với manifest đáng tin và scan khi tệp do người dùng cung cấp.
- Timeout không đồng nghĩa upload thất bại: cần **idempotency, kiểm tra commit và reconciliation**.
- **Private Endpoint, TLS, Azure RBAC, SAS ngắn hạn, soft delete/versioning và audit** là các lớp bảo vệ bổ sung, không thay thế lẫn nhau.
- Production cần **metrics throughput/latency/error, retry budget, cost analysis, test cases, alert, runbook và người chịu trách nhiệm**.
