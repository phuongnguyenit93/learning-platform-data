# Tải lên, tải xuống và xử lý tệp lớn theo dạng luồng với Azure Blob Storage

## 1. Mục tiêu bài học

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, chúng ta thực hành tích hợp Spring Boot với dịch vụ managed trên AWS, Azure và Google Cloud, chú trọng cấu hình danh tính, quyền truy cập, bảo vệ secret và kiểm thử tích hợp. Bài này thuộc chương **Azure Storage**, tập trung vào vấn đề rất thực tế: **làm việc với tệp lớn qua luồng dữ liệu (stream)** khi sử dụng Azure Blob Storage.

Giả sử hệ thống cần nhận một video 3 GiB, lưu lên Azure Blob Storage và trả video cho người dùng có quyền. Một cách triển khai sai là gọi `file.getBytes()` rồi giữ toàn bộ video trong `byte[]` trước khi upload. Nếu nhiều người tải lên đồng thời, heap có thể cạn kiệt. Thay vào đó, cần đọc và ghi từng phần dữ liệu, kiểm soát bộ đệm, thời gian xử lý, số kết nối và khả năng khôi phục sau lỗi.

Sau bài này, bạn có thể:

- Phân biệt **streaming**, **buffering toàn bộ tệp**, upload theo block và **resumable upload**.
- Cấu hình Spring Cloud Azure Blob client theo danh tính phù hợp.
- Upload từ `InputStream` hoặc file trên đĩa bằng Azure Storage SDK; hiểu điều kiện cần khi SDK yêu cầu kích thước đầu vào.
- Download blob ra `OutputStream`/HTTP response mà không đưa toàn bộ nội dung vào heap.
- Dùng **stage block → commit block list** để kiểm soát bộ nhớ và tổ chức tải lên từng khối.
- Thiết kế timeout, retry, idempotency, phân quyền, kiểm tra toàn vẹn và kiểm thử khi có tệp lớn hoặc kết nối bị gián đoạn.

## 2. Vì sao cần xử lý theo luồng?

### 2.1. Ba cách tiếp cận

| Cách xử lý | Luồng dữ liệu | Bộ nhớ ứng dụng | Khi nào phù hợp |
|---|---|---|---|
| Đọc toàn bộ vào `byte[]` | File → RAM → Blob | Tỷ lệ với kích thước tệp; dễ gây OOM | Chỉ dữ liệu nhỏ đã có giới hạn nghiêm ngặt |
| Upload/download qua `InputStream` / `OutputStream` | File/HTTP stream → Azure SDK → Blob | Có buffer trong ứng dụng/SDK, không cần giữ nguyên tệp trong RAM | Đa số upload/download thông thường |
| Upload block có kiểm soát | Đọc một chunk → `stageBlock` → lặp → `commitBlockList` | Chủ yếu phụ thuộc kích thước chunk và số khối đang xử lý | Tệp rất lớn, cần kiểm soát khối, retry hoặc tiếp tục từ checkpoint |

Lưu ý: chữ **streaming** không có nghĩa là sử dụng **0 byte RAM**. HTTP client, SSL/TLS, Azure SDK và framework vẫn có bộ đệm. Mục tiêu là **không để lượng RAM tăng tuyến tính theo kích thước toàn tệp**. Nếu tăng `maxConcurrency`, số buffer và kết nối hoạt động cũng có thể tăng.

### 2.2. Stream, MultipartFile và upload trực tiếp

Trong Spring MVC, một endpoint nhận `MultipartFile` thường phải qua bước phân tích multipart của servlet container. Dữ liệu có thể được lưu tạm lên **đĩa** hoặc **RAM**, tùy cấu hình và kích thước file. Sau đó `MultipartFile.getInputStream()` trả luồng đọc từ dữ liệu đã được nhận.

Vì thế:

- Dùng `getInputStream()` tránh biến **thêm một bản sao toàn bộ file** thành `byte[]` trong code nghiệp vụ.
- Điều này **không bảo đảm** truyền thẳng byte từ mạng của trình duyệt sang Azure mà không có file tạm.
- Với upload hàng GiB hoặc số kết nối đồng thời lớn, phải kiểm tra **dung lượng đĩa tạm**, giới hạn multipart, request timeout và sức chứa server.
- Nếu muốn trình duyệt gửi trực tiếp lên Azure, hãy cân nhắc **SAS chỉ cho phép upload một blob** hoặc mô hình ủy quyền có thời hạn; backend kiểm tra danh tính và cấp quyền, sau đó nhận callback/xác nhận hoàn tất theo nghiệp vụ.

### 2.3. Dòng chảy dữ liệu

~~~mermaid
flowchart LR
    C[Client] -->|Multipart upload| M[Spring MVC multipart parser]
    M -->|Đọc InputStream| S[Spring Boot service]
    S -->|Azure Blob SDK| B[(Azure Blob Storage)]
    D[Database] <-->|documentId, blobName, trạng thái| S
    C -->|Yêu cầu tải về| A[Download endpoint]
    A -->|Xác thực và phân quyền| D
    B -->|Luồng byte| A
    A -->|HTTP response stream| C
~~~

Trong luồng tải về, backend có thể proxy dữ liệu; khi có yêu cầu hiệu năng khác, client có thể download trực tiếp từ Azure qua URL SAS ngắn hạn, sau khi backend xác thực quyền.

## 3. Các khái niệm Azure Blob quan trọng với tệp lớn

### 3.1. Account, container, blob và client

Azure Blob Storage tổ chức dữ liệu theo **storage account → container → blob**. Trong SDK Java:

- `BlobServiceClient`: truy cập dịch vụ Blob của một account.
- `BlobContainerClient`: truy cập container, liệt kê blob, lấy blob client.
- `BlobClient`: thao tác một blob; upload, download, properties, delete.
- `BlockBlobClient`: chuyên cho **block blob**, hỗ trợ đưa block lên (`stageBlock`) rồi công bố danh sách khối (`commitBlockList`).

Tên blob như `videos/2026/lecture-123.mp4` chỉ là tên object có prefix trong flat namespace thông thường; không đồng nghĩa với thư mục SMB.

### 3.2. Block blob và dữ liệu chưa commit

Tệp lớn thường lưu dưới dạng **block blob**. Khi tải theo block:

1. Ứng dụng chia dữ liệu thành các block có ID riêng.
2. `stageBlock` gửi từng block vào trạng thái **uncommitted**.
3. `commitBlockList` gửi **danh sách block ID theo đúng thứ tự** để tạo hoặc cập nhật blob được nhìn thấy.

Nếu upload dở dang chưa commit, người đọc chưa thấy phiên bản blob mới từ các block đó. Với blob đã tồn tại, dữ liệu committed trước đó tiếp tục được phục vụ cho đến khi có commit mới. Các uncommitted block có thời hạn lưu giữ hữu hạn do dịch vụ quy định, không nên xem chúng là kho checkpoint lâu dài.

Giới hạn tối đa kích thước block, số block, kích thước blob phụ thuộc **phiên bản API** và loại blob. Khi thiết kế các file nhiều terabyte, hãy đối chiếu tài liệu Azure Storage đang áp dụng, chọn kích thước block để số block không vượt giới hạn và không giả định mọi tài khoản đều hỗ trợ cùng mức trần.

### 3.3. Tải lên một lần so với tiếp tục sau ngắt kết nối

`BlobClient.upload(InputStream, length, false)` là cách đơn giản, nhưng việc retry **một request HTTP nội bộ** khác với khả năng **tiếp tục upload từ lần chạy trước** sau khi tiến trình chết. Resumable upload thực sự đòi hỏi hệ thống biết các block nào đã tải thành công, lưu trạng thái job/checkpoint và có cách commit an toàn. Nếu không xây dựng cơ chế này, hãy mô tả upload của bạn là **streaming với retry ở tầng SDK**, không tuyên bố rằng nó tự khôi phục được sau mọi sự cố.

## 4. Cấu hình Spring Boot và Spring Cloud Azure

### 4.1. Maven và cấu hình storage account

Ví dụ dùng Spring MVC và Spring Cloud Azure Blob starter:

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

Chọn `spring-cloud-azure.version` theo **ma trận tương thích Spring Boot/Spring Cloud Azure** của dự án. Không nên chọn một phiên bản thư viện tùy ý chỉ vì đó là bản mới nhất.

~~~yaml
spring:
  cloud:
    azure:
      storage:
        blob:
          account-name: ${AZURE_STORAGE_ACCOUNT_NAME}
  servlet:
    multipart:
      max-file-size: 1GB
      max-request-size: 1100MB
      file-size-threshold: 0B
      location: ${UPLOAD_TEMP_DIR:/tmp}

app:
  blob:
    container: ${BLOB_CONTAINER:private-documents}
~~~

Đây là cấu hình **minh họa**, cần chỉnh theo hạ tầng:

- Giới hạn multipart phải phù hợp với giới hạn reverse proxy, ingress, load balancer, servlet container và dung lượng file tạm.
- `file-size-threshold: 0B` hướng multipart lớn vào bộ nhớ lưu tạm trên đĩa theo cấu hình servlet thay vì giữ toàn bộ file trong RAM; đường dẫn `UPLOAD_TEMP_DIR` cần tồn tại, đủ dung lượng và có quyền ghi. Trên Windows hoặc container, không mặc định sử dụng `/tmp`.
- Khi triển khai serverless hoặc container có ephemeral storage hạn chế, hãy đánh giá kỹ mô hình upload trực tiếp tới Blob bằng SAS.
- `app.blob.container` là property của ứng dụng; ví dụ giả định container **đã được provision** và để chế độ private.

### 4.2. Identity và quyền dữ liệu

Ưu tiên **managed identity** trong Azure và **Microsoft Entra ID** với quyền **Storage Blob Data Contributor** cho thành phần cần ghi blob, **Storage Blob Data Reader** cho thành phần chỉ tải xuống. Developer có thể dùng danh tính qua Azure CLI ở local. Role cần gán cho **đúng principal** và scope phù hợp; quyền management plane không tự cấp quyền data plane.

Không commit account key, connection string production, client secret hoặc SAS vào repository. Kiểm tra thêm firewall, private endpoint/DNS và TLS; lỗi 403/timeout có thể xuất phát từ quyền **hoặc** mạng.

### 4.3. Khởi tạo client dùng chung

Spring Cloud Azure có thể auto-configure `BlobServiceClient` từ starter và cấu hình ở trên:

~~~java
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class StorageClients {
    private final BlobContainerClient container;

    public StorageClients(
            BlobServiceClient blobServiceClient,
            @Value("${app.blob.container}") String containerName) {
        this.container =
                blobServiceClient.getBlobContainerClient(containerName);
    }

    public BlobContainerClient container() {
        return container;
    }
}
~~~

`getBlobContainerClient` **không tạo container trên Azure**. Provision container ở bước hạ tầng/migration; runtime không nên tạo/xóa container mỗi lần nhận request. Các client SDK là đối tượng có thể tái sử dụng qua nhiều request, tránh khởi tạo lại HTTP pipeline và credential liên tục.

## 5. Upload tệp lớn bằng InputStream

### 5.1. Tải từ file trên ổ đĩa

Với file đã nằm trên đĩa, mở `InputStream` và truyền **số byte** đã biết cho SDK:

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobContainerClient;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.stereotype.Service;

@Service
public class BlobTransferService {
    private final BlobContainerClient container;

    public BlobTransferService(StorageClients clients) {
        this.container = clients.container();
    }

    public void upload(Path source, String blobName) throws IOException {
        long length = Files.size(source);
        BlobClient blob = container.getBlobClient(blobName);

        try (InputStream input = Files.newInputStream(source)) {
            // false: không ghi đè blob trùng tên.
            blob.upload(input, length, false);
        }
    }

    public void download(String blobName, Path target) throws IOException {
        BlobClient blob = container.getBlobClient(blobName);
        try (var output = Files.newOutputStream(target)) {
            blob.downloadStream(output);
        }
    }
}
~~~

Trong ví dụ này, `length` là `long`, không nên ép về `int` vì nhiều tệp lớn hơn 2 GiB. SDK có thể chia request thành nhiều phần và sử dụng bộ đệm nội bộ; cấu hình transfer phù hợp nếu cần kiểm soát bộ nhớ và throughput. **Không đổi đoạn này** thành `Files.readAllBytes(source)` rồi gọi upload, vì như vậy sẽ đưa nguyên file vào heap.

Nếu input là file local và không cần thao tác với stream thủ công, Azure SDK cũng hỗ trợ những API chuyên dụng như `uploadFromFile(path, overwrite)` hoặc `downloadToFile(path, overwrite)`. Các API này hữu ích để SDK quản lý việc đọc/ghi từ file, retry và truyền theo khối tùy phiên bản SDK/cấu hình.

### 5.2. Tải từ MultipartFile của Spring MVC

~~~java
import com.azure.storage.blob.BlobClient;
import java.io.IOException;
import java.io.InputStream;
import java.util.UUID;
import org.springframework.web.multipart.MultipartFile;

public String uploadMultipart(MultipartFile file) throws IOException {
    if (file == null || file.isEmpty()) {
        throw new IllegalArgumentException("Không được gửi file rỗng");
    }

    String blobName = "uploads/" + UUID.randomUUID();
    BlobClient client = container.getBlobClient(blobName);

    try (InputStream input = file.getInputStream()) {
        client.upload(input, file.getSize(), false);
    }
    return blobName;
}
~~~

Đây là **phương thức minh họa đặt trong một service có field `container`** như ở mục 5.1. API thực tế phải kiểm tra authorization, kích thước, loại nội dung, malware và quota **trước** khi lưu tài liệu. Tên blob là ID do server tạo; không dùng nguyên `getOriginalFilename()` để đặt tên blob. Nếu cần lưu tên file gốc, hãy lưu như dữ liệu hiển thị đã chuẩn hóa ở database.

Ở bước multipart, server thường đã nhận nội dung lên bộ nhớ/đĩa tạm trước khi service được gọi. Vì thế cấu hình `max-file-size` và dung lượng scratch disk là một phần của thiết kế, không chỉ là chi tiết của Spring.

### 5.3. Khi kích thước stream không biết trước

Không tùy tiện truyền một `length` đoán chừng vào `upload(InputStream, long, ...)`. SDK dùng giá trị này để xác định số byte phải đọc; sai độ dài có thể gây lỗi hoặc nội dung không đúng. Với request HTTP không có Content-Length tin cậy hoặc stream phát sinh theo thời gian, có các hướng xử lý:

1. **Spool tạm** ra file, đo `Files.size` rồi upload theo stream.
2. **Đọc các chunk có giới hạn** và gọi `stageBlock`; không cần biết tổng kích thước trước khi bắt đầu.
3. Thiết kế **direct-to-Blob upload** có session và checkpoint để client kiểm soát các part.

Chọn giải pháp theo giới hạn file, tốc độ mạng, yêu cầu resume và chi phí lưu tạm. Không nên đẩy toàn bộ file vào `ByteArrayOutputStream` chỉ để lấy được độ dài.

## 6. Upload theo block để kiểm soát bộ nhớ

### 6.1. Quy trình stage và commit

Với block blob, API mức thấp cho phép đọc **mỗi lần một chunk cố định**, truyền chunk đến Azure và giữ lại block ID. Ví dụ sau dùng chunk 8 MiB, truyền tuần tự; các ID có dạng cố định để tránh trùng:

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.specialized.BlockBlobClient;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;

public void uploadBlocks(
        BlobClient blobClient,
        Path source) throws IOException {

    BlockBlobClient blockBlob = blobClient.getBlockBlobClient();
    final int chunkSize = 8 * 1024 * 1024; // 8 MiB
    byte[] buffer = new byte[chunkSize];
    List<String> blockIds = new ArrayList<>();
    int index = 0;

    try (InputStream input = Files.newInputStream(source)) {
        int read;
        while ((read = input.readNBytes(buffer, 0, buffer.length)) > 0) {
            String rawId = String.format("%08d", index++);
            String blockId = Base64.getEncoder().encodeToString(
                    rawId.getBytes(StandardCharsets.UTF_8));

            try (InputStream chunk = new ByteArrayInputStream(
                    buffer, 0, read)) {
                blockBlob.stageBlock(blockId, chunk, read);
            }
            blockIds.add(blockId);
        }
    }

    // Chỉ commit sau khi mọi block cần thiết đã stage thành công.
    blockBlob.commitBlockList(blockIds);
}
~~~

**Các điểm cần hiểu chính xác:**

- `readNBytes(buffer, 0, chunkSize)` đọc tối đa một chunk. Ví dụ dùng Java 17+; dữ liệu có thể đi hết stream ở lần cuối nên `read` có thể nhỏ hơn 8 MiB.
- `blockId` phải được mã hóa Base64, duy nhất trong một blob; các ID dùng cho cùng blob cần có độ dài nhất quán trước khi mã hóa. Ví dụ dùng số thứ tự 8 ký tự, đủ để minh họa một file thông thường.
- Bộ đệm nội dung của code này là **một mảng 8 MiB** (cộng buffer mạng/SDK). `blockIds` vẫn chiếm RAM tỷ lệ với **số lượng block**, nhỏ hơn nhiều so với giữ toàn bộ file.
- **Thứ tự trong `commitBlockList` quyết định thứ tự ghép dữ liệu.** Commit thiếu một ID hoặc sai thứ tự có thể tạo nội dung thiếu/sai. Không commit khi vẫn còn block thất bại.
- Commit một danh sách mới có thể **thay thế toàn bộ nội dung committed** của blob có cùng tên. Cần blob name duy nhất hoặc ràng buộc điều kiện ghi/ETag khi nghiệp vụ không cho phép ghi đè.
- Với file rỗng, ví dụ này không tạo block; hãy định nghĩa nhánh xử lý riêng và kiểm tra API commit phù hợp nếu hệ thống cho phép file rỗng.

Đây là ví dụ **mức thấp có tính hướng dẫn**, không phải engine resumable upload hoàn chỉnh. Nên ưu tiên API upload cấp cao của SDK nếu chỉ cần tải file lớn một cách thông thường; dùng stage/commit khi thực sự cần tổ chức block, checkpoint và kiểm soát tiến trình.

### 6.2. Muốn resume sau khi tiến trình bị ngắt thì cần gì?

Một hệ thống resumable cần lưu **uploadId/jobId**, blob đích, block size, danh sách block ID/thứ tự, trạng thái đã xác nhận, thời hạn và chủ sở hữu. Khi restart, nó phải xác minh dữ liệu staged còn tồn tại, tải lại các block thiếu và **chỉ commit khi danh sách đầy đủ**. Đừng tin một danh sách block lưu ở client mà không đối chiếu trạng thái trên Azure.

~~~mermaid
flowchart TD
    S[Bắt đầu upload session] --> R[Đọc một chunk]
    R --> T[Stage block với ID ổn định]
    T --> X{Stage thành công?}
    X -->|Không| K[Retry có backoff / ghi trạng thái]
    K --> T
    X -->|Có| P[Lưu checkpoint]
    P --> N{Còn dữ liệu?}
    N -->|Có| R
    N -->|Không| V[Kiểm tra đủ block + thứ tự]
    V --> C[Commit block list]
    C --> F[Đánh dấu hoàn tất và lưu metadata]
~~~

Khi tích hợp queue worker, cần gắn job ID để tránh cùng một tệp bị xử lý hoặc commit nhiều lần không chủ đích. Số phiên xử lý song song phải bị giới hạn theo CPU, RAM, bandwidth và quota của storage account.

### 6.3. Chọn kích thước block và mức song song

Không có một `chunkSize` tốt cho mọi hệ thống:

- Chunk **nhỏ**: tốn ít RAM mỗi worker, nhưng tăng số request và chi phí overhead, có nguy cơ chạm giới hạn số block.
- Chunk **lớn**: thường tăng throughput khi mạng đủ tốt, nhưng RAM, thời gian retry một chunk và độ trễ tăng.
- Concurrency **cao**: cải thiện băng thông tổng nếu đường truyền và service chịu được, nhưng tăng bộ đệm, kết nối và tải upstream.

Để ước lượng, nếu có **N upload đồng thời**, mỗi upload giữ **C block cùng lúc**, kích thước **B byte**, riêng buffer payload đã có thể xấp xỉ `N × C × B`, **chưa kể** overhead SDK, servlet và network. Ví dụ N=8, C=4, B=8 MiB thì buffer payload riêng đã khoảng **256 MiB**; cần tính thêm dự phòng và giới hạn worker trước khi deploy.

## 7. Download theo stream

### 7.1. Không gom cả blob vào bộ nhớ

Với file lớn, tránh:

~~~java
// Chỉ nên dùng với file nhỏ đã được giới hạn dung lượng.
byte[] wholeFile = blobClient.downloadContent().toBytes();
~~~

Thay bằng một luồng đầu ra:

~~~java
import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

Path destination = Path.of("report-large.zip");
try (OutputStream output = Files.newOutputStream(destination)) {
    blobClient.downloadStream(output);
}
~~~

Hoặc mở `InputStream` từ blob và copy theo stream:

~~~java
import java.io.InputStream;
import java.io.OutputStream;

try (InputStream input = blobClient.openInputStream();
     OutputStream output = Files.newOutputStream(destination)) {
    input.transferTo(output); // Java 9+
}
~~~

Trong cả hai trường hợp, file không cần hiện diện dưới dạng một `byte[]` lớn. Tuy nhiên SDK vẫn có thể thực hiện các request theo range và dùng buffer/retry bên trong; đọc **luồng một cách tuần tự** không có nghĩa mạng chỉ sử dụng một HTTP request.

### 7.2. Trả tệp từ Spring MVC qua HTTP

Ví dụ endpoint tải file dạng stream. Ở đây `DocumentRepository`, `DocumentRecord` và `CurrentUser` là các thành phần nghiệp vụ **giả định đã có** để kiểm tra quyền:

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.models.BlobProperties;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/documents")
public class DocumentDownloadController {
    private final BlobContainerClient container;
    private final DocumentRepository documents;
    private final CurrentUser currentUser;

    public DocumentDownloadController(
            StorageClients clients,
            DocumentRepository documents,
            CurrentUser currentUser) {
        this.container = clients.container();
        this.documents = documents;
        this.currentUser = currentUser;
    }

    @GetMapping("/{documentId}/download")
    public void download(
            @PathVariable String documentId,
            HttpServletResponse response) throws IOException {

        // Lookup phải kiểm tra quyền owner/tenant và trả 404/403 phù hợp.
        DocumentRecord doc = documents.requireReadableBy(
                documentId, currentUser.id());
        BlobClient blob = container.getBlobClient(doc.blobName());
        BlobProperties properties = blob.getProperties();

        String contentType = properties.getContentType();
        response.setContentType(contentType != null
                ? contentType : MediaType.APPLICATION_OCTET_STREAM_VALUE);
        response.setContentLengthLong(properties.getBlobSize());
        response.setHeader(
                HttpHeaders.CONTENT_DISPOSITION,
                "attachment; filename=\"document.bin\"");

        blob.downloadStream(response.getOutputStream());
        response.flushBuffer();
    }
}
~~~

**Lưu ý triển khai:** ví dụ trên chạy theo **blocking I/O** trên servlet thread; một lượt tải dài có thể giữ thread lâu. Cần giới hạn download đồng thời, cấu hình timeout và giám sát số thread đang bận. Nếu dùng Spring MVC `StreamingResponseBody`, cần cấu hình **TaskExecutor** phù hợp và vẫn phải xử lý các trường hợp client ngắt kết nối. Với WebFlux, cân nhắc Azure **async client** cùng mô hình backpressure, tránh gọi sync SDK trên event loop.

`BlobProperties` được lấy trước khi gửi nội dung để đặt Content-Length/Content-Type. Tuy nhiên blob có thể thay đổi **giữa lần lấy properties và lúc download**. Với tài liệu cần nhất quán tuyệt đối, dùng version ID/ETag và điều kiện truy cập thích hợp, hoặc thiết kế blob bất biến theo phiên bản.

### 7.3. Range download và tiếp tục tải xuống

Trình duyệt hoặc trình phát video thường sử dụng HTTP `Range` để xin **một phần** file, ví dụ `Range: bytes=1048576-2097151`. Đây là nền tảng của resume download và video seek. Một endpoint hỗ trợ Range đúng cách phải:

- Phân tích/kiểm tra `Range`, bao gồm range không hợp lệ, suffix range, giới hạn byte và trường hợp nhiều range.
- Trả **206 Partial Content** và `Content-Range`/`Content-Length` chính xác cho phần được trả; xử lý **416 Range Not Satisfiable** khi thích hợp.
- Bảo đảm byte range thuộc **cùng một phiên bản blob**, sử dụng ETag/If-Range hoặc version ID theo chính sách của API.
- Gọi API SDK hỗ trợ đọc **range cụ thể** (ví dụ `BlobRange` và download options); không tải cả blob rồi cắt trong RAM.

Đoạn controller ở mục 7.2 minh họa **full download 200 OK**, **chưa hỗ trợ HTTP Range**. Nếu cần streaming video hoặc resume, hãy dùng thành phần/proxy có hỗ trợ Range chuẩn hoặc bổ sung chức năng range riêng và kiểm thử kỹ; không chỉ thêm header `Accept-Ranges: bytes` rồi cho rằng đã hỗ trợ.

## 8. Xử lý lỗi, timeout và retry

### 8.1. Lỗi có thể xảy ra ở những giai đoạn nào?

| Giai đoạn | Lỗi tiêu biểu | Hướng xử lý |
|---|---|---|
| Nhận multipart | File vượt giới hạn, hết ổ tạm, client hủy request | Trả mã lỗi phù hợp; giới hạn size/concurrency và dọn file tạm |
| Xác thực Azure | Token không hợp lệ, thiếu RBAC | Xác định principal thực tế; sửa role data plane/credential |
| Upload block | Timeout, ngắt mạng, throttle 429/503 | Retry với backoff trên khối idempotent; ghi checkpoint nếu dùng resumable |
| Commit block list | Mất phản hồi sau khi server đã commit | Đọc trạng thái/ETag và đối chiếu trước khi commit lại mù quáng |
| Ghi database | Blob đã có nhưng record chưa có | Retry/đối soát orphan blob và trạng thái job |
| Download | Blob bị xóa/đổi phiên bản, client ngắt kết nối | Bảo đảm version/ETag; log, cleanup; không cố trả JSON lỗi khi response đã gửi byte |
| Kiểm tra checksum | Nội dung nguồn/đích không trùng | Đánh dấu lỗi, không phát hành file; retry hoặc đối soát dữ liệu |

**HTTP đã gửi một phần body thì không thể tùy ý đổi status thành 500 và trả JSON lỗi như trước khi bắt đầu stream.** Khi client ngắt, server có thể gặp `IOException`; log đủ correlation ID và hủy công việc đọc tiếp theo. Tránh ghi stack trace đầy đủ lặp lại cho mọi lần client chủ động hủy tải.

### 8.2. Idempotency và tính nhất quán

Một request upload có thể đã thành công ở Azure nhưng client nhận timeout và gửi lại. Nếu mỗi lần retry tạo UUID mới, kết quả là **nhiều blob trùng nội dung**. Một thiết kế đáng tin cậy cần:

1. Sinh `documentId` hoặc `idempotencyKey` ổn định cho cùng yêu cầu.
2. Lưu trạng thái `PENDING → UPLOADING → READY` trong database/queue theo nhu cầu.
3. Ghi blob name gắn với document ID; chỉ xem là `READY` sau khi upload được xác nhận.
4. Khi retry, kiểm tra trạng thái hiện có hoặc thuộc tính blob, không vô điều kiện tạo bản sao mới.
5. Định kỳ dọn hoặc đối soát blob chưa liên kết sau khi hết thời gian chờ hợp lý.

Blob Storage và database **không có transaction xuyên dịch vụ**. Với block upload, staged block thành công chưa đồng nghĩa blob mới đã được commit. Với download, ETag là phiên bản thay đổi của object, **không phải hash nội dung**.

### 8.3. Kiểm tra toàn vẹn và checksum

Với tài liệu có yêu cầu toàn vẹn cao, backend có thể tính **SHA-256 theo stream**, lưu hash ở metadata nghiệp vụ (database) và kiểm tra lại khi nhận/tải về:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

public static byte[] sha256(Path file)
        throws IOException, NoSuchAlgorithmException {
    MessageDigest digest = MessageDigest.getInstance("SHA-256");
    byte[] buffer = new byte[64 * 1024];

    try (InputStream input = Files.newInputStream(file)) {
        int read;
        while ((read = input.read(buffer)) != -1) {
            digest.update(buffer, 0, read);
        }
    }
    return digest.digest();
}
~~~

Chỉ lưu checksum khi biết chính xác **đối tượng byte nào đã được băm** và cách kiểm chứng: file local trước upload, response sau download, hoặc dữ liệu do client cung cấp. Không đồng nhất ETag với MD5/SHA-256. Azure SDK có cơ chế kiểm tra toàn vẹn ở tầng truyền tải cho các thao tác thích hợp, nhưng mức độ áp dụng phụ thuộc API/loại request và cấu hình; checksum ứng dụng vẫn hữu ích cho xác minh end-to-end.

## 9. Thiết kế bảo mật cho upload/download lớn

### 9.1. Bảo vệ container và dữ liệu riêng tư

- Sử dụng container **private**. Blob name không phải mật khẩu; biết URL có path không đồng nghĩa được quyền tải.
- Backend kiểm tra **người dùng, tenant, quyền sở hữu, trạng thái tệp và giới hạn quota** trước khi upload hoặc tải về.
- Quản lý credential qua Microsoft Entra ID/managed identity khi có thể. Nếu buộc dùng secret, lưu bằng cơ chế quản lý secret như Azure Key Vault và xoay vòng phù hợp.
- Không log raw file content, account key, SAS token hoặc header Authorization.
- Cấu hình TLS, private endpoint/firewall khi phù hợp; CORS chỉ điều khiển chính sách trình duyệt, **không thay thế authentication/authorization**.

### 9.2. Direct-to-Blob upload bằng SAS

Đối với file lớn và client web/mobile có đường truyền ổn định tới Azure, có thể tránh cho backend trở thành nút trung chuyển:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Spring Boot API
    participant B as Azure Blob Storage
    participant D as Database
    C->>A: Xin phiên upload (file size, MIME, auth)
    A->>D: Tạo document PENDING / blobName
    A-->>C: Blob URL + SAS giới hạn quyền/thời gian
    C->>B: Upload trực tiếp theo block
    B-->>C: Kết quả upload
    C->>A: Báo hoàn tất upload
    A->>B: Kiểm tra blob tồn tại, size, metadata
    A->>D: Cập nhật READY nếu hợp lệ
    A-->>C: Hoàn tất
~~~

Khi cấp SAS:

- Ràng buộc **đúng blob**, quyền **tạo/ghi** cần thiết và thời hạn ngắn; không cấp delete/list khi không cần.
- Nếu khả thi, ưu tiên **user delegation SAS** thay vì SAS ký bằng account key; kiểm tra giới hạn quyền và thời hạn của cơ chế tương ứng.
- Không tin lời client “đã upload xong”: backend xác minh blob, kích thước, nội dung/metadata cần thiết trước khi công bố.
- Giới hạn tổng size, thời gian, số phiên upload và xử lý dọn upload bỏ dở; cân nhắc kiểm tra malware trước khi chuyển sang trạng thái READY.

SAS là quyền truy cập tạm thời vào resource, không tự chứng thực người dùng cuối. Việc phát hành SAS chỉ diễn ra sau kiểm tra authorization ở backend.

## 10. Kiểm thử tích hợp và quan sát hệ thống

### 10.1. Kiểm thử với Azurite

**Azurite** mô phỏng nhiều API Blob cơ bản để kiểm thử cục bộ. Với các test cần quyền RBAC/managed identity, network/private endpoint, performance hoặc giới hạn thực tế của Azure, vẫn cần storage account thử nghiệm trên Azure.

Ví dụ một đoạn kiểm tra **round-trip bằng file**, tránh so sánh qua `byte[]` toàn tệp:

~~~java
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.UUID;

// Chỉ dùng connection string của Azurite trong môi trường test.
String connection = System.getenv("AZURITE_STORAGE_CONNECTION_STRING");
BlobServiceClient service = new BlobServiceClientBuilder()
        .connectionString(connection)
        .buildClient();

var container = service.getBlobContainerClient("stream-test");
container.createIfNotExists();

String blobName = "roundtrip/" + UUID.randomUUID();
var blob = container.getBlobClient(blobName);
Path source = Path.of("test-data/large-sample.bin");
Path target = Files.createTempFile("blob-roundtrip-", ".bin");
try {
    blob.uploadFromFile(source.toString(), false);
    blob.downloadToFile(target.toString(), true);

    if (Files.size(source) != Files.size(target)
            || !Arrays.equals(sha256(source), sha256(target))) {
        throw new AssertionError("Nội dung tải về không khớp");
    }
} finally {
    blob.deleteIfExists();
    Files.deleteIfExists(target);
}
~~~

`sha256` là hàm ở mục 8.3; đoạn trên là **mẫu tích hợp API** và giả định file `test-data/large-sample.bin` đã được chuẩn bị. Trong bộ test thực, dùng JUnit assertion, quản lý vòng đời Azurite/container riêng, dữ liệu test có giới hạn và cleanup trong `finally`. Việc chạy test SDK trực tiếp chưa kiểm chứng đầy đủ cấu hình Spring Cloud Azure, cần thêm test context Spring Boot khi mục tiêu là auto-configuration.

### 10.2. Ma trận kiểm thử cần có

| Trường hợp | Kết quả cần kiểm chứng |
|---|---|
| File rất nhỏ, file vài trăm MiB/giới hạn cho phép | Upload/download đúng byte, không nhân bản toàn file trong RAM |
| File rỗng | API từ chối hoặc hỗ trợ theo quy tắc nghiệp vụ nhất quán |
| Multipart vượt `max-file-size` | HTTP lỗi phù hợp, không tạo blob mồ côi |
| Tên blob bị trùng, `overwrite=false` | Không âm thầm ghi đè |
| Ngắt mạng khi stage block | Block chưa commit không bị công bố là file hoàn tất |
| Client timeout sau commit | Retry/đối soát không tạo tài liệu trùng |
| Download khi client ngắt kết nối | Không giữ thread/socket vô hạn, có log hữu ích |
| Nhiều upload/download đồng thời | RAM, CPU, ổ tạm, request latency được giữ trong ngưỡng |
| Managed identity thiếu quyền | Lỗi xác thực/ủy quyền được phát hiện, không fallback secret hardcode |
| File bị thay đổi giữa properties và download | Chính sách ETag/version bảo vệ dữ liệu cần nhất quán |
| SHA-256 sau download khác nguồn | Tài liệu bị coi là không hợp lệ, có retry/cảnh báo |

### 10.3. Metrics và vận hành

Nên theo dõi **số upload/download đang hoạt động**, số byte đã truyền, latency theo file size, retry/throttle, tỉ lệ lỗi 403/404/409/412/429/503, thông lượng, heap/GC, disk tạm, thread pool và traffic egress. Phân biệt lỗi thuộc client, app, Azure SDK, network và storage service bằng correlation ID; tránh ghi thông tin nhạy cảm vào logs.

Đối với dữ liệu ít truy cập, xét **access tier và lifecycle policy**; với file tải thường xuyên và lớn, đánh giá egress cost, CDN/caching và yêu cầu truy cập trực tiếp. Không mặc định mọi video nên proxy qua Spring Boot hoặc mọi nội dung phải chuyển sang Archive tier.

## 11. Tình huống thực hành

**Tình huống A — Upload video 2 GiB qua Spring MVC:** Đầu tiên hãy xác định container/ingress có cho request lớn và có ổ tạm đủ dung lượng không. Dùng `MultipartFile.getInputStream()` và `getSize()` để upload, không dùng `getBytes()`. Nếu tải lớn diễn ra thường xuyên, đánh giá direct-to-Blob upload để giảm áp lực lên backend.

**Tình huống B — Mạng chập chờn và cần resume:** Thiết kế session upload với block ID cố định, lưu checkpoint và kiểm tra các block đã stage trước khi tiếp tục. Chỉ commit khi đủ dữ liệu, có cách đối soát khi server đã commit nhưng client chưa nhận được phản hồi.

**Tình huống C — Trả video để tua đến phút thứ 30:** Full download streaming 200 OK chưa đủ. Cần HTTP Range 206 chuẩn, truy xuất range tương ứng từ Azure và giữ đồng nhất một version/ETag.

**Tình huống D — 10 người cùng upload tệp 4 GiB:** Dùng công thức `số upload × số block xử lý song song × block size` để ước lượng RAM cho payload buffer, cộng overhead servlet/SDK; đặt giới hạn đồng thời và đo thật trong load test.

### Câu hỏi tự kiểm tra

1. **Vì sao `getInputStream()` tốt hơn `getBytes()` cho file lớn?** Vì code có thể tiêu thụ dữ liệu tuần tự, không bắt buộc tạo bản sao `byte[]` có kích thước bằng toàn file.
2. **Spring MVC `MultipartFile` có bảo đảm 100% streaming từ socket tới Azure không?** Không. Multipart resolver có thể buffer/spool trước khi service nhận stream.
3. **Upload từng block xong nhưng chưa gọi `commitBlockList` thì sao?** Các block vẫn ở trạng thái uncommitted; không được xem là blob hoàn chỉnh.
4. **Blob ETag có phải SHA-256 của nội dung không?** Không. ETag hỗ trợ điều kiện/phiên bản truy cập; kiểm tra toàn vẹn nội dung cần hash hoặc cơ chế xác minh riêng.
5. **Tại sao nên phân biệt retry request với resumable upload?** Retry xử lý lỗi tạm thời; resume sau restart cần checkpoint, trạng thái block và logic commit.
6. **Vì sao download controller không tự hỗ trợ HTTP Range?** Đọc toàn blob ra `OutputStream` là full download; Range yêu cầu parsing header, chọn byte range và mã phản hồi 206/416 chính xác.

## 12. Tổng kết

Đối với tệp lớn, **stream theo từng phần** là nguyên tắc cốt lõi khi tích hợp Spring Boot với Azure Blob Storage. Dùng `InputStream`/`OutputStream` để tránh giữ cả file trong heap; dùng **block blob** và `stageBlock`/`commitBlockList` khi cần kiểm soát chunk hoặc tự xây resumable upload. Phân biệt rõ **multipart spool**, **SDK retry** và **resume sau sự cố**, đồng thời bảo vệ dữ liệu bằng managed identity/RBAC, container private, ETag/version, idempotency và kiểm thử tải thực tế.

Khi so sánh đa đám mây, mô hình object storage và multipart/block upload có điểm tương đồng với **Amazon S3** và **Google Cloud Storage**, nhưng API, quyền IAM, giao thức resume và giới hạn cụ thể khác nhau. Hãy học nguyên tắc quản lý byte stream, bộ nhớ và trạng thái trước khi chuyển sang thư viện provider khác.

### Tài liệu tham khảo

- [Microsoft Learn — Introduction to Azure Blob Storage](https://learn.microsoft.com/azure/storage/blobs/storage-blobs-introduction)
- [Microsoft Learn — Upload a blob with Java](https://learn.microsoft.com/azure/storage/blobs/storage-blob-upload-java)
- [Microsoft Learn — Download a blob with Java](https://learn.microsoft.com/azure/storage/blobs/storage-blob-download-java)
- [Microsoft Learn — Put Block (REST)](https://learn.microsoft.com/rest/api/storageservices/put-block)
- [Microsoft Learn — Put Block List (REST)](https://learn.microsoft.com/rest/api/storageservices/put-block-list)
- [Microsoft Learn — Spring Cloud Azure](https://learn.microsoft.com/azure/developer/java/spring-framework/)
- [Microsoft Learn — Use Azurite for local Azure Storage development](https://learn.microsoft.com/azure/storage/common/storage-use-azurite)
