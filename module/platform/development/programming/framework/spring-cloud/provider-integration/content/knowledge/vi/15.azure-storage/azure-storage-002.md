# Cấu hình Blob client và thao tác container, blob trong Spring Boot

## 1. Mục tiêu và bài toán thực tế

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, mục tiêu là tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud bằng thư viện phù hợp, đồng thời hiểu danh tính, quyền truy cập, bảo vệ secret và kiểm thử tích hợp. Bài này tập trung vào **Azure Blob Storage**: tạo và cấu hình client, truy cập container, upload/download/list/delete blob bằng **Spring Cloud Azure** và **Azure Storage SDK for Java**.

Hãy hình dung một hệ thống quản lý hợp đồng: người dùng tải tệp PDF lên, Spring Boot lưu nội dung tại Azure Blob Storage, database lưu thông tin hợp đồng cùng **tên blob**, và người dùng có quyền có thể tải tài liệu về sau. Để triển khai đúng, chúng ta cần trả lời:

- Cần tạo **storage account**, **container** và **blob** như thế nào?
- **BlobServiceClient**, **BlobContainerClient** và **BlobClient** khác nhau ở đâu?
- Spring Boot lấy thông tin endpoint và credential ra sao, đặc biệt khi chạy bằng **managed identity**?
- Làm thế nào để upload/download một file mà không nhúng account key vào mã nguồn?
- Phải xử lý quyền, ghi trùng, xóa nhầm, lỗi mạng và kiểm thử thế nào?

**Đầu ra mong muốn:** có thể cấu hình client qua Spring Cloud Azure, giải thích được API cơ bản, viết dịch vụ Spring Boot thao tác Blob và nhận diện những phần cần bổ sung khi đưa vào production.

## 2. Mô hình dữ liệu và hệ phân cấp client

Azure Blob Storage lưu **object** (blob), thường là dữ liệu phi cấu trúc như PDF, ảnh, video, file export, sao lưu hoặc dữ liệu sự kiện. Mô hình truy cập cơ bản:

~~~text
Azure subscription
└── Storage account: appstorageprod
    └── Blob service
        ├── Container: documents
        │   ├── contracts/2026/a81f.pdf
        │   └── contracts/2026/b91d.pdf
        └── Container: avatars
            └── users/u42.png
~~~

Đường dẫn thường có dạng:

~~~text
https://<storage-account>.blob.core.windows.net/<container>/<blob-name>
~~~

Ba cấp SDK đồng nhất với cấu trúc này:

| Client Java | Phạm vi | Thao tác tiêu biểu |
|---|---|---|
| `BlobServiceClient` | Dịch vụ Blob của một storage account | Liệt kê container, lấy client container, tạo container |
| `BlobContainerClient` | Một container | Tạo/xóa container, liệt kê blob, lấy client blob |
| `BlobClient` | Một blob cụ thể | Upload, download, đọc properties, metadata, xóa |

**Lưu ý:** `getBlobContainerClient(name)` hoặc `getBlobClient(name)` chỉ tạo đối tượng SDK tham chiếu đến tài nguyên, **không tự tạo container/blob trên Azure**. Tên blob có thể chứa ký tự `/` để giả lập cây thư mục qua prefix như `contracts/2026/a81f.pdf`. Với Blob Storage kiểu flat namespace thông thường, đây chủ yếu là **tên object**, không phải thư mục SMB thực. Tài khoản bật hierarchical namespace (ADLS Gen2) có ngữ nghĩa thư mục khác, nằm ngoài ví dụ chính của bài.

Các ví dụ sau sử dụng **block blob**, loại phù hợp với tài liệu và ảnh thông thường. **Append blob** dành cho một số trường hợp ghi nối tiếp, **page blob** phục vụ truy cập theo trang; không nên cho rằng mọi blob đều có cùng cách ghi hiệu quả.

## 3. Chuẩn bị tài nguyên và cấp quyền

Trước khi chạy ứng dụng, cần có một **Azure Storage account** hỗ trợ Blob, chọn region/replication/networking theo yêu cầu. Ví dụ sử dụng:

- Storage account: giá trị qua biến môi trường `AZURE_STORAGE_ACCOUNT_NAME`.
- Container riêng tư: `documents`.
- Danh tính ứng dụng: developer đăng nhập Azure CLI khi chạy local, **managed identity** khi chạy trong dịch vụ Azure hỗ trợ.
- Vai trò truy cập dữ liệu: tối thiểu là **Storage Blob Data Contributor** khi ứng dụng cần upload/download/delete; nếu chỉ đọc, cân nhắc **Storage Blob Data Reader**.

Vai trò RBAC cần gán cho **đúng principal** và **đúng scope** (storage account hoặc container). Quyền quản lý resource qua Azure Resource Manager như `Reader` hay `Contributor` không mặc nhiên là quyền đọc/ghi blob qua OAuth data plane. Nếu ứng dụng cần **tạo container mới**, hãy kiểm tra scope và quyền quản lý container riêng, vì role chỉ giới hạn vào container chưa tồn tại thường không đáp ứng bước khởi tạo.

Ngoài RBAC, kiểm tra **network access**: storage firewall, private endpoint, DNS và môi trường chạy phải cho phép kết nối đến endpoint Blob. Một principal có RBAC đúng vẫn có thể kết nối thất bại nếu bị chặn mạng.

**Nguyên tắc vận hành:** tạo container bằng bước provision hạ tầng hoặc migration; ứng dụng nghiệp vụ thường chỉ cần quyền thao tác các blob trong container đã có. Không bật public anonymous access cho tài liệu riêng tư.

## 4. Khai báo Spring Cloud Azure và cấu hình Blob client

### 4.1. Dependency

Sử dụng **Spring Cloud Azure Blob Storage starter** và một BOM phù hợp với phiên bản Spring Boot của dự án. Ví dụ Maven:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>${spring-cloud-azure.version}</version>
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
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
    </dependency>
</dependencies>
~~~

`spring-cloud-azure.version` là property cần khai báo ở POM hoặc quản lý version cấp dự án. Không chọn ngẫu nhiên phiên bản mới nhất: hãy dùng **ma trận tương thích Spring Boot ↔ Spring Cloud Azure** ở tài liệu chính thức.

### 4.2. Cấu hình qua `application.yml`

~~~yaml
spring:
  cloud:
    azure:
      storage:
        blob:
          account-name: ${AZURE_STORAGE_ACCOUNT_NAME}

app:
  storage:
    documents-container: ${DOCUMENTS_CONTAINER:documents}
~~~

Ở đây:

- `spring.cloud.azure.storage.blob.account-name` xác định storage account để auto-configuration dựng Blob client.
- `AZURE_STORAGE_ACCOUNT_NAME` được cung cấp ở môi trường deploy; không hardcode tên account cố định vào code.
- `app.storage.documents-container` là property **do ứng dụng tự định nghĩa**, dùng để thay đổi tên container mà không sửa Java.
- Nếu dùng Azure sovereign cloud, endpoint tùy chỉnh hoặc Azurite, cần cấu hình endpoint/credential tương ứng. Với Azure Private Endpoint, ứng dụng thường vẫn dùng hostname Blob chuẩn và **DNS phân giải hostname này về IP private**; không tự thay hostname bằng một địa chỉ IP.

Khi starter phù hợp được bật và cấu hình hợp lệ, Spring Cloud Azure có thể cung cấp bean `BlobServiceClient` để ứng dụng inject qua constructor. Việc tìm credential phụ thuộc cấu hình Azure Identity/Spring Cloud Azure và môi trường. Với phát triển local, có thể dùng `az login`; ở Azure production, ưu tiên managed identity với role data plane đã cấp.

**Không lưu** account key, connection string production, SAS token hoặc client secret trực tiếp trong `application.yml` được commit vào Git.

### 4.3. Ví dụ lấy client từ Spring Boot

~~~java
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class BlobAccess {
    private final BlobServiceClient serviceClient;
    private final BlobContainerClient documents;

    public BlobAccess(
            BlobServiceClient serviceClient,
            @Value("${app.storage.documents-container}") String containerName) {
        this.serviceClient = serviceClient;
        this.documents = serviceClient.getBlobContainerClient(containerName);
    }

    public BlobContainerClient documents() {
        return documents;
    }

    public BlobServiceClient service() {
        return serviceClient;
    }
}
~~~

`BlobAccess` dùng để minh họa hai cấp client: từ `BlobServiceClient` đến `BlobContainerClient`. Các client SDK có thể dùng lại qua nhiều lời gọi; nên tạo/inject ở vòng đời application thay vì tự tạo client và credential mới cho mỗi request.

### 4.4. Khi cần cấu hình client thủ công

Không bắt buộc dùng starter trong mọi kiến trúc. Với Azure SDK độc lập, có thể tạo `BlobServiceClient` bằng endpoint và **DefaultAzureCredential**:

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

String account = System.getenv("AZURE_STORAGE_ACCOUNT_NAME");
if (account == null || account.isBlank()) {
    throw new IllegalStateException("Thiếu AZURE_STORAGE_ACCOUNT_NAME");
}

BlobServiceClient serviceClient = new BlobServiceClientBuilder()
        .endpoint("https://" + account + ".blob.core.windows.net")
        .credential(new DefaultAzureCredentialBuilder().build())
        .buildClient();
~~~

Nếu chọn cách này, project cần khai báo dependency Azure SDK `azure-storage-blob` và `azure-identity` với version đồng bộ qua BOM phù hợp. `DefaultAzureCredential` có thể tìm nhiều nguồn danh tính (biến môi trường, managed identity, thông tin đăng nhập công cụ developer, tùy khả năng và phiên bản SDK). Trong production, cần xác định chính xác danh tính nào được phép cấp token; đừng dựa vào credential của máy phát triển.

**Không tự khai báo thêm một bean cùng kiểu** nếu đã để Spring Cloud Azure tạo bean và không có nhu cầu override rõ ràng; điều này dễ gây lỗi inject trùng hoặc sử dụng sai cấu hình.

## 5. Thao tác với container

Container là đơn vị tổ chức blob và thường dùng làm ranh giới phân quyền/vòng đời dữ liệu. Tên container phải tuân thủ quy tắc Azure: chữ thường, chữ số và dấu gạch nối với độ dài hợp lệ (thông dụng 3–63 ký tự); chẳng hạn `documents`, `product-images`. Tên chứa chữ hoa hoặc dấu gạch dưới như `Customer_Files` không hợp lệ.

### 5.1. Lấy container và khởi tạo có kiểm soát

~~~java
BlobContainerClient container =
        serviceClient.getBlobContainerClient("documents");

// Chỉ dùng trong bước provision/migration có đủ quyền:
container.createIfNotExists();

boolean available = container.exists();
System.out.println("Container tồn tại: " + available);
~~~

`createIfNotExists()` có ích khi chạy script khởi tạo lặp lại. Tuy nhiên, ứng dụng chỉ có quyền đọc blob sẽ không thể tạo container; vì vậy **không đưa lệnh này vào mỗi request** hoặc phụ thuộc vào nó để che giấu lỗi thiếu quyền. Nên chạy qua IaC/migration có kiểm soát, sau đó cấu hình application chỉ tham chiếu container có sẵn.

### 5.2. Liệt kê container

~~~java
for (var item : serviceClient.listBlobContainers()) {
    System.out.println(item.getName());
}
~~~

Liệt kê container có thể đòi quyền rộng hơn thao tác một blob trong container đã biết. Nếu kiến trúc giới hạn ứng dụng vào đúng container `documents`, không nên yêu cầu mở rộng quyền chỉ để hỗ trợ một chức năng liệt kê không cần thiết.

### 5.3. Xóa container

~~~java
// Lệnh quản trị có khả năng xóa toàn bộ blob trong container!
boolean deleted = container.deleteIfExists();
~~~

`deleteIfExists()` có tác động đến **toàn bộ nội dung container** và chỉ nên dùng trong công cụ quản trị, môi trường thử nghiệm hoặc quy trình dọn tài nguyên đã được kiểm soát. Đối với chức năng xóa **một tài liệu**, phải thao tác trên `BlobClient` tương ứng, không xóa container.

## 6. Thao tác với blob từ Spring Boot

### 6.1. Upload một tài liệu

Ví dụ service lưu một `MultipartFile` vào container `documents`, tạo tên blob ngẫu nhiên để tránh ghi đè do hai người cùng gửi tên tệp:

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.models.BlobHttpHeaders;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

@Service
public class DocumentStorageService {
    private final BlobContainerClient container;

    public DocumentStorageService(BlobAccess blobAccess) {
        this.container = blobAccess.documents();
    }

    public String upload(MultipartFile file) throws IOException {
        if (file == null || file.isEmpty()) {
            throw new IllegalArgumentException("Tệp tải lên không được rỗng");
        }

        String blobName = "contracts/" + UUID.randomUUID() + ".bin";
        BlobClient blob = container.getBlobClient(blobName);

        try (InputStream input = file.getInputStream()) {
            // false: không ghi đè nếu blob đã tồn tại.
            blob.upload(input, file.getSize(), false);
        }

        // Chỉ gắn MIME đã xác minh. Ví dụ này dùng loại chung an toàn.
        blob.setHttpHeaders(
                new BlobHttpHeaders().setContentType("application/octet-stream"));
        return blobName;
    }

    public void download(String blobName, OutputStream output) {
        BlobClient blob = container.getBlobClient(blobName);
        blob.downloadStream(output);
    }

    public boolean delete(String blobName) {
        BlobClient blob = container.getBlobClient(blobName);
        return blob.deleteIfExists();
    }
}
~~~

**Giải thích các quyết định:**

- `BlobClient` là tham chiếu đến **một blob name**, có thể dùng ngay để upload dù blob chưa tồn tại.
- `upload(stream, length, false)` gửi nội dung từ stream, chỉ chấp nhận tạo mới và báo lỗi nếu tên đã có. Nếu đặt `true`, SDK được phép ghi đè blob tồn tại; không bật chỉ để xử lý lỗi trùng tên.
- `MultipartFile.getSize()` cung cấp số byte kỳ vọng, cần khớp dữ liệu thực từ input stream.
- `setHttpHeaders` đặt Content-Type **sau khi upload**. Trong thực tế đây là một thao tác mạng riêng; nếu nó thất bại, blob có thể đã tồn tại. Dịch vụ cần log và cơ chế retry/đối soát phù hợp. Có thể dùng API upload options để gắn headers cùng request/luồng upload nếu yêu cầu.
- Chỉ sử dụng `application/pdf` sau khi hệ thống đã kiểm tra tệp thực sự là PDF; không tin ngay MIME do client gửi lên.
- Tên blob được tạo từ UUID, không nối trực tiếp tên tệp do người dùng cung cấp. Nên lưu tên gốc, chủ sở hữu và blob name trong database để quản lý quyền ở tầng nghiệp vụ.

**Giới hạn của ví dụ:** chưa thực hiện xác thực người dùng, giới hạn kích thước tải lên, quét nội dung, kiểm tra loại file, xử lý upload nhiều phần và rollback dữ liệu. Đây là service minh họa API Blob, không phải một endpoint public hoàn chỉnh.

### 6.2. Upload với controller REST

~~~java
import java.io.IOException;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/documents")
public class DocumentController {
    private final DocumentStorageService storage;

    public DocumentController(DocumentStorageService storage) {
        this.storage = storage;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Map<String, String> upload(
            @RequestParam("file") MultipartFile file) throws IOException {
        String blobName = storage.upload(file);
        return Map.of("blobName", blobName);
    }
}
~~~

Lời gọi ví dụ:

~~~bash
curl -X POST \
  -F "file=@contract.pdf" \
  http://localhost:8080/api/documents
~~~

Ứng dụng thật cần thêm Spring Security, giới hạn request size và kiểm soát quyền tenant/người dùng trước khi cấp quyền truy xuất. Phản hồi chỉ chứa `blobName`, không tự động đồng nghĩa blob được công khai cho bất kỳ người nào biết tên.

### 6.3. Download blob

Đối với file nhỏ, SDK cho phép đọc dữ liệu vào bộ nhớ:

~~~java
BlobClient blob = container.getBlobClient("contracts/example.pdf");
byte[] bytes = blob.downloadContent().toBytes();
~~~

Với file lớn, nên **stream ra output** thay vì gom toàn bộ file vào RAM:

~~~java
import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

Path target = Path.of("downloaded-contract.pdf");
try (OutputStream output = Files.newOutputStream(target)) {
    container.getBlobClient("contracts/example.pdf")
             .downloadStream(output);
}
~~~

Nếu xuất thẳng từ Spring MVC HTTP response, cần xác thực và phân quyền trước khi ghi stream; xử lý Content-Type, Content-Disposition, Content-Length và lỗi kết nối client. Không để API nhận một `blobName` tùy ý rồi download mà không kiểm tra chủ sở hữu; việc blob là private ở Azure không thay thế authorization ở backend.

### 6.4. Liệt kê blob theo prefix

~~~java
import com.azure.storage.blob.models.BlobItem;
import com.azure.storage.blob.models.ListBlobsOptions;
import java.time.Duration;

for (BlobItem item : container.listBlobs(
        new ListBlobsOptions().setPrefix("contracts/"),
        Duration.ofSeconds(30))) {
    System.out.println(item.getName());
}
~~~

Prefix `contracts/` chỉ lọc **tên blob**, không phải truy vấn filesystem hay database. List có thể phân trang; các SDK paging tự lấy trang tiếp theo khi duyệt. Với tập dữ liệu rất lớn, đừng duyệt toàn bộ container để tìm một tài liệu theo ID nếu database đã có blob name; hãy truy cập trực tiếp theo key. Đối với các chức năng tìm kiếm nghiệp vụ, dùng database/index để lọc metadata theo tenant, người tạo, thời gian hoặc trạng thái.

### 6.5. Lấy properties và metadata

~~~java
import java.util.Map;

BlobClient blob = container.getBlobClient("contracts/example.pdf");

var properties = blob.getProperties();
System.out.println("Kích thước: " + properties.getBlobSize());
System.out.println("Content-Type: " + properties.getContentType());
System.out.println("ETag: " + properties.getETag());

blob.setMetadata(Map.of(
        "documentType", "contract",
        "source", "portal"
));
~~~

**Properties** là thuộc tính hệ thống như kích thước, Content-Type, ETag, Last-Modified. **Metadata** là cặp key-value do ứng dụng gắn với blob; không nên lưu bí mật hoặc dữ liệu nhạy cảm vào metadata. Quy tắc ký tự tên metadata cần tương thích với Azure Storage và có thể khác tên cột database. Lệnh `setMetadata` **thay thế bộ metadata hiện có**, nên cần lấy/merge nếu muốn giữ các key cũ.

ETag giúp chống ghi đè khi nhiều tác nhân cập nhật cùng blob. Có thể dùng điều kiện `If-Match` với ETag đã đọc để thao tác chỉ thành công khi blob chưa bị thay đổi; khi không khớp, máy chủ trả lỗi điều kiện (thường HTTP **412**). Điều này phù hợp cho **optimistic concurrency**, tránh kiểu “người ghi cuối cùng luôn thắng” không có kiểm soát.

### 6.6. Xóa blob

~~~java
BlobClient blob = container.getBlobClient("contracts/example.pdf");
boolean existedAndDeleted = blob.deleteIfExists();
~~~

Không xóa blob chỉ dựa trên tên do client gửi lên: phải xác minh quyền, ràng buộc nghiệp vụ và thời hạn lưu trữ. Nếu storage account bật **soft delete**, **versioning** hoặc chính sách retention, việc xóa không nhất thiết khiến dữ liệu biến mất vĩnh viễn ngay lập tức. Với dữ liệu có yêu cầu pháp lý, còn cần xem xét immutability policy/legal hold.

## 7. Luồng xử lý end-to-end

~~~mermaid
flowchart LR
    U[Người dùng đã xác thực] -->|POST file| A[Spring Boot Controller]
    A -->|Kiểm tra quyền và file| S[DocumentStorageService]
    S -->|BlobServiceClient / ContainerClient / BlobClient| B[(Azure Blob Storage)]
    S -->|Lưu blobName + owner + trạng thái| D[(Database)]
    U -->|Yêu cầu tải tài liệu| A
    A -->|Kiểm tra owner/tenant| D
    A -->|Đọc blob theo key| B
~~~

Luồng gợi ý:

1. Backend kiểm tra quyền upload, dung lượng, định dạng và tạo `documentId`/`blobName`.
2. Backend upload Blob vào container private.
3. Backend ghi record chứa `documentId`, `blobName`, `ownerId`, `status` vào database.
4. Khi tải, backend lấy record theo ID nghiệp vụ, kiểm tra người dùng có quyền, rồi stream blob hoặc cấp quyền tải có thời hạn.
5. Hệ thống log `documentId`, request/correlation ID và lỗi SDK; không log nội dung tài liệu hoặc secret.

**Cảnh báo nhất quán:** Blob Storage và database không có transaction chung. Nếu upload thành công nhưng ghi database lỗi, có thể còn **orphan blob**. Nếu DB ghi trước còn upload lỗi, record có thể ở trạng thái `PENDING`. Thiết kế nên có trạng thái nghiệp vụ, retry idempotent và job dọn/đối soát định kỳ cho các tình huống này.

## 8. Danh tính, secret, SAS và an toàn truy cập

### 8.1. Xác thực bằng danh tính Azure

Thứ tự nên ưu tiên khi triển khai hiện đại:

1. **Managed identity** cho ứng dụng chạy trên Azure: không phát hành secret lâu dài cho ứng dụng.
2. **Developer identity** cho máy local thông qua Azure CLI hoặc công cụ IDE khi được tổ chức cho phép.
3. **Service principal** trong CI/CD hoặc môi trường không hỗ trợ managed identity, ưu tiên cơ chế liên kết danh tính/federated credential nếu có; nếu phải dùng client secret, bảo quản bằng kho secret và xoay vòng.

`DefaultAzureCredential` hữu ích vì cùng code có thể hoạt động ở nhiều môi trường, nhưng cần biết nguồn credential nào thực sự đã được chọn. Nếu chạy trên Azure mà principal thiếu RBAC, sửa **role assignment** thay vì chuyển sang hardcode account key. Vai trò `Storage Blob Data Contributor` cho thao tác ghi/xóa; `Storage Blob Data Reader` cho tác vụ chỉ đọc.

### 8.2. Container private và quyền tải ngắn hạn

Không bật public access chỉ để frontend tải tài liệu dễ hơn. Có hai cách thường gặp:

- **Proxy qua backend:** client gọi Spring Boot; backend kiểm tra authorization và stream dữ liệu Blob, phù hợp khi cần audit truy cập chặt chẽ nhưng tăng lưu lượng qua backend.
- **SAS giới hạn:** backend xác thực quyền rồi phát hành URL SAS chỉ đọc, cho **một blob**, với thời hạn ngắn. Ưu tiên **user delegation SAS** khi hệ thống sử dụng Microsoft Entra ID và cấu hình cho phép; SAS không tự là một cơ chế kiểm tra quyền người dùng cuối.

Không nhúng SAS lâu dài vào database public, log hoặc mã frontend được chia sẻ; cũng không phát SAS chứa quyền delete/write khi chỉ cần download.

### 8.3. Các giới hạn ngoài credential

- Dùng HTTPS/TLS, giới hạn public network access và private endpoint khi phù hợp với hạ tầng.
- Kiểm tra CORS nếu trình duyệt truy cập Blob trực tiếp; CORS không cấp quyền, chỉ kiểm soát chính sách cross-origin của browser.
- Giới hạn quyền theo container hoặc storage account và tách danh tính của dịch vụ upload, đọc-only, quản trị nếu có thể.
- Bật logging/metrics phù hợp, versioning hoặc soft delete nếu cần khả năng khôi phục, lifecycle để tránh lưu trữ vô hạn.
- Đừng dùng container name hoặc blob prefix làm biện pháp bảo mật duy nhất; truy cập phải dựa trên credential/RBAC và authorization của ứng dụng.

## 9. Lỗi thường gặp, tính nhất quán và hiệu năng

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| HTTP 403 | Principal thiếu quyền data-plane, SAS hết hạn hoặc storage firewall chặn | Xác minh danh tính thực, role assignment, scope và network |
| HTTP 404 | Sai account/container/blob name; container chưa provision | Kiểm tra endpoint, tên và môi trường; nhớ blob name phân biệt hoa/thường |
| HTTP 409 khi upload | Blob đã tồn tại và `overwrite=false`; hoặc xung đột tài nguyên | Tạo tên duy nhất, xử lý trùng bằng logic nghiệp vụ |
| HTTP 412 | ETag/điều kiện ghi không còn đúng | Đọc trạng thái mới và xử lý concurrent update |
| Timeout hoặc throttling | Network, tải lớn, giới hạn request, kết nối chậm | Dùng retry với backoff, giám sát latency/429/503; tối ưu song song theo tải |
| Local chạy được, Azure lỗi | Local dùng tài khoản developer khác với managed identity | Kiểm tra role assignment của danh tính production và private DNS |
| Upload thành công nhưng app trả lỗi | Một bước sau upload (metadata/DB/API) thất bại | Thiết kế trạng thái và đối soát, tránh upload lặp thiếu idempotency |

**Retry không đồng nghĩa mọi thao tác đều an toàn để lặp.** Với upload có tên mới tạo ngẫu nhiên cho mỗi lần retry, request từ client có thể tạo nhiều blob. Nên gắn một `requestId`/`documentId` ổn định, xây dựng cơ chế phát hiện request trùng và lựa chọn `overwrite`/điều kiện ghi phù hợp.

Về hiệu năng:

- Đối với file lớn, ưu tiên API **streaming**, upload/download theo block hoặc cấu hình parallel transfer được SDK hỗ trợ; không dùng `downloadContent().toBytes()` cho media lớn.
- Tái sử dụng client và kết nối; không tạo credential mới cho từng HTTP request.
- Dùng prefix để sắp xếp tên blob; dùng database/index cho truy vấn nghiệp vụ phức tạp.
- Xem xét access tier, lifecycle và chi phí read/write/egress theo nhu cầu thực tế.
- Nếu ứng dụng dùng WebFlux/Reactor, cân nhắc **BlobServiceAsyncClient/BlobAsyncClient** thay vì gọi sync client chặn event-loop.

## 10. Kiểm thử tích hợp với Azurite và Azure thật

**Azurite** là trình giả lập local cho nhiều thao tác Azure Storage Blob/Queue/Table, hữu ích để kiểm tra upload/list/download/delete cơ bản mà không phải tạo tài nguyên cloud cho mỗi lần chạy test. Tuy nhiên, nó **không mô phỏng đầy đủ** mọi tính năng Azure Blob, RBAC Microsoft Entra ID, private endpoint và cấu hình mạng production.

Một test chạy với Azurite có thể tạo client bằng connection string **chỉ dành cho emulator**:

~~~java
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

String azuriteConnectionString =
        System.getenv("AZURITE_STORAGE_CONNECTION_STRING");
BlobServiceClient testClient = new BlobServiceClientBuilder()
        .connectionString(azuriteConnectionString)
        .buildClient();

String testContainer = "documents-test";
var container = testClient.getBlobContainerClient(testContainer);
container.createIfNotExists();

String key = "integration/sample.txt";
byte[] expected = "hello".getBytes(StandardCharsets.UTF_8);
container.getBlobClient(key)
         .upload(new ByteArrayInputStream(expected), expected.length, true);

byte[] actual = container.getBlobClient(key).downloadContent().toBytes();
if (!Arrays.equals(expected, actual)) {
    throw new IllegalStateException("Blob tải về sai nội dung");
}

container.getBlobClient(key).deleteIfExists();
~~~

Đây là ví dụ ý tưởng để kiểm thử SDK, không phải test class JUnit hoàn chỉnh; trong test thực, sử dụng assertion framework phù hợp, dữ liệu container/tên blob riêng cho mỗi test, và **cleanup** sau khi chạy. Connection string emulator chứa key giả lập chỉ phù hợp môi trường test; không tái sử dụng pattern này với key account production.

Các trường hợp nên kiểm thử:

1. Upload file hợp lệ và download lại đúng byte; headers/metadata được lưu chính xác.
2. Upload cùng blob name với `overwrite=false` phải thất bại đúng cách.
3. List theo prefix chỉ trả tập blob mong đợi.
4. Delete blob rồi truy cập lại tạo kết quả phù hợp với cấu hình soft delete/versioning của môi trường.
5. Tài khoản chỉ đọc bị chặn khi upload, tài khoản có role phù hợp có thể upload.
6. Client bị chặn mạng, thiếu DNS/private endpoint, SAS hết hạn và retry khi có lỗi tạm thời.
7. Lỗi giữa bước upload Blob và ghi database được hệ thống khôi phục/đối soát.

Các test về **managed identity, Azure RBAC, firewall/private endpoint, SAS, chính sách vòng đời và quy mô thực** cần chạy trên **storage account Azure dành riêng cho kiểm thử**, không chỉ Azurite.

## 11. Bài tập thực hành

**Bài 1 — Tạo service lưu ảnh hồ sơ:** Thiết kế Spring Boot service dùng `BlobServiceClient` được inject để upload ảnh vào container `avatars`, đặt tên `users/<userId>/<uuid>.png`. Giải thích tại sao cần kiểm tra quyền của `userId` ở backend và không dùng filename người dùng gửi trực tiếp.

**Bài 2 — API tải hợp đồng riêng tư:** Database có record `contractId` và `blobName`; viết luồng đọc bản ghi, kiểm tra chủ sở hữu, sau đó stream blob về client. So sánh proxy download với URL SAS ngắn hạn, nêu nơi lưu audit log.

**Bài 3 — Phát hiện ghi đè:** Hai tiến trình cùng sửa một tài liệu. Hãy mô tả cách dùng ETag + `If-Match` để phát hiện xung đột, thay vì cứ upload với `overwrite=true`.

**Bài 4 — Chạy trên Azure:** Ứng dụng chạy local thành công nhưng nhận 403 khi deploy. Hãy lập danh sách kiểm tra: tên account/endpoint, danh tính managed identity, data-plane RBAC, scope, network firewall, private endpoint/DNS, và thời gian áp dụng role.

**Tự kiểm tra:** 

- Vì sao có `BlobClient` không có nghĩa blob đã tồn tại? — Vì client là tham chiếu logic; SDK chỉ kết nối khi gọi API.
- Nên dùng client nào để list container? — `BlobServiceClient`.
- Nên dùng client nào để upload vào một blob? — `BlobClient` lấy từ `BlobContainerClient`.
- Tại sao không nên luôn tạo container lúc mỗi request? — Vì việc provision cần quyền và vòng đời quản trị riêng, đồng thời gây phụ thuộc không cần thiết.
- Khi upload thành công mà ghi database thất bại, kết quả gì có thể xảy ra? — Blob mồ côi; cần đối soát hoặc cleanup an toàn.

## 12. Tổng kết và tài liệu tham khảo

Khi tích hợp Azure Blob Storage với Spring Boot, hãy đi theo ba cấp **`BlobServiceClient` → `BlobContainerClient` → `BlobClient`**: client dịch vụ để truy cập account, client container để tổ chức nhóm blob, client blob để đọc/ghi một object. Spring Cloud Azure giúp cấu hình client và credential thống nhất; Azure SDK cung cấp API thao tác chi tiết. Thiết kế tốt đi kèm **managed identity/RBAC**, container private, streaming phù hợp dung lượng, retry/idempotency, quản lý metadata và kiểm thử trên cả Azurite lẫn Azure thật.

Về khái niệm, Blob Storage gần với **Amazon S3** và **Google Cloud Storage** ở mô hình bucket/container + object, nhưng credential, API SDK, IAM và cơ chế vòng đời khác nhau; không nên giả định mã cấu hình Azure áp dụng nguyên vẹn cho AWS/GCP.

**Tài liệu tham khảo chính thức:**

- [Microsoft Learn — Introduction to Azure Blob Storage](https://learn.microsoft.com/azure/storage/blobs/storage-blobs-introduction)
- [Microsoft Learn — Azure Blob Storage client library for Java](https://learn.microsoft.com/azure/storage/blobs/storage-quickstart-blobs-java)
- [Microsoft Learn — Authorize access to Blob data with Microsoft Entra ID](https://learn.microsoft.com/azure/storage/blobs/authorize-access-azure-active-directory)
- [Microsoft Learn — Spring Cloud Azure](https://learn.microsoft.com/azure/developer/java/spring-framework/)
- [Microsoft Learn — Use the Azurite emulator for local Azure Storage development](https://learn.microsoft.com/azure/storage/common/storage-use-azurite)
