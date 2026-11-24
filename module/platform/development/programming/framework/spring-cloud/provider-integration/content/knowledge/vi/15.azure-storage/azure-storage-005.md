# ETag, điều kiện ghi và kiểm soát cập nhật đồng thời với Azure Blob Storage

## 1. Bối cảnh và mục tiêu

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, chúng ta học tích hợp Spring Boot với dịch vụ managed của **AWS, Azure và Google Cloud**, bao gồm danh tính và phân quyền, truy cập storage, messaging, bảo vệ secret, kiểm thử tích hợp và so sánh cách triển khai giữa các cloud provider. Bài này thuộc chương **Azure Storage**, tập trung vào một vấn đề dễ gặp khi nhiều request cùng đọc và sửa dữ liệu: **tránh mất cập nhật (lost update)**.

Giả sử ứng dụng quản lý hợp đồng lưu nội dung và metadata tài liệu trong **Azure Blob Storage**:

1. Nhân viên A mở tài liệu phiên bản đầu tiên.
2. Nhân viên B cũng mở tài liệu đó.
3. A cập nhật và lưu thành công.
4. B lưu bản sửa dựa trên nội dung cũ, vô tình **ghi đè thay đổi của A**.

Nếu server chỉ gọi upload với `overwrite=true`, thao tác sau cùng có thể thắng dù người thực hiện chưa từng nhìn thấy cập nhật trước đó. **ETag và request condition** cho phép Azure Storage tự kiểm tra phiên bản của blob **ngay tại thời điểm ghi**, từ đó từ chối ghi dựa trên trạng thái đã lỗi thời.

Sau bài học, bạn có thể:

- Giải thích **ETag**, **optimistic concurrency**, **conditional requests** và tại sao một lần gọi `exists()` trước khi ghi không đủ an toàn.
- Phân biệt `If-Match`, `If-None-Match`, các điều kiện theo thời gian và **lease**.
- Viết API Spring Boot sử dụng `BlobRequestConditions` để cập nhật có điều kiện và trả lỗi **HTTP 412 Precondition Failed** đúng ngữ nghĩa.
- Dùng điều kiện tạo mới để tránh ghi đè blob đã tồn tại; lựa chọn cách bảo vệ metadata, xóa và thao tác tệp lớn.
- Xây dựng kiểm thử xung đột, kiểm soát quyền data plane và đánh giá giới hạn khi liên kết Azure Blob với database/queue.

## 2. Vì sao kiểm tra trước khi ghi vẫn có thể mất dữ liệu?

Hãy xem đoạn mã dễ mắc lỗi:

~~~java
BlobClient blob = container.getBlobClient("contracts/contract-42.json");

if (blob.exists()) {
    // Một request khác có thể cập nhật blob ngay sau dòng này.
    blob.upload(input, contentLength, true);
}
~~~

Lệnh `exists()` và lệnh `upload()` là **hai yêu cầu độc lập**. Giữa hai thời điểm đó, một tiến trình khác hoàn toàn có thể thay nội dung. Đây là lỗi **time-of-check to time-of-use (TOCTOU)**. Kể cả gọi `getProperties()` trước khi `upload()`, lỗi vẫn xảy ra nếu lần upload không mang điều kiện phiên bản.

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant B as Client B
    participant S as Azure Blob Storage
    A->>S: GET blob (ETag v1)
    B->>S: GET blob (ETag v1)
    A->>S: PUT nội dung A, không có condition
    S-->>A: Ghi thành công, ETag v2
    B->>S: PUT nội dung B, không có condition
    S-->>B: Ghi thành công, ETag v3
    Note over S: Nội dung A đã bị ghi đè
~~~

Cách giải quyết là đưa **ETag mà client đã đọc** vào **chính request cập nhật** bằng header `If-Match`. Azure Blob Storage đánh giá điều kiện như một phần của thao tác, tránh khoảng hở giữa “kiểm tra” và “ghi”.

## 3. ETag của Azure Blob Storage là gì?

**ETag (entity tag)** là giá trị nhận diện trạng thái của một resource để hỗ trợ điều kiện HTTP và kiểm soát đồng thời. Azure Blob Storage trả ETag khi truy vấn properties hoặc thực hiện nhiều thao tác đọc/ghi; ETag thường thay đổi khi blob được sửa đổi, kể cả một số cập nhật properties và metadata.

Ví dụ minh họa:

~~~http
HTTP/1.1 200 OK
ETag: "0x8E123456789ABCD"
Last-Modified: Tue, 24 Nov 2026 08:30:00 GMT
Content-Type: application/json
~~~

Đây là ETag **giả định** để giải thích cấu trúc; không phải ETag của một tài nguyên thực. **Không tự tạo hoặc suy luận ETag**, hãy lấy giá trị chính xác từ response của Storage SDK.

| Khái niệm | Ý nghĩa | Dùng cho |
|---|---|---|
| **ETag** | Nhận diện trạng thái phiên bản hiện tại của resource | Điều kiện ghi/đọc, optimistic concurrency, cache validation |
| **Last-Modified** | Thời điểm resource được sửa gần nhất | Quan sát thay đổi, một số điều kiện theo thời gian |
| **Version ID** | Định danh một phiên bản khi Blob versioning được bật | Truy cập/khôi phục lịch sử các phiên bản đã lưu |
| **Content hash** | Giá trị tính từ byte nội dung (ví dụ SHA-256 do ứng dụng tính) | Xác minh toàn vẹn, đối chiếu nội dung |
| **Lease ID** | Token của lease đang được giữ trên blob | Phối hợp truy cập theo cơ chế khóa độc quyền có thời hạn |

Những điều cần nhớ:

- **ETag không phải checksum**. Hai mục tiêu “file không bị hỏng” và “file chưa bị người khác thay đổi” cần cơ chế khác nhau.
- Không dự đoán ETag tiếp theo, không tăng ETag như số nguyên và không sử dụng ETag làm business ID.
- Trong REST, ETag có thể mang dấu nháy kép. Với SDK, nên giữ nguyên chuỗi ETag Azure trả về khi đặt `If-Match`, tránh tự bỏ dấu nháy hoặc thêm tiền tố không đúng.
- ETag chỉ bảo vệ **resource và operation có điều kiện**. Nếu một client khác ghi không có condition, client đó vẫn có thể làm thay đổi blob.
- Azure Blob Storage hỗ trợ mô hình **strong consistency** ở cấp thao tác được dịch vụ xác nhận; tuy nhiên ETag **không tạo transaction chung** cho nhiều blob, database hay queue.

## 4. Các điều kiện HTTP thường gặp

Azure Storage hỗ trợ request condition trên các operation phù hợp; không phải mọi header đều áp dụng cho mọi API và mọi loại blob. Với thao tác Blob phổ biến:

| Điều kiện | Ý nghĩa | Tình huống sử dụng |
|---|---|---|
| `If-Match: "<etag>"` | Chỉ thực hiện nếu ETag hiện tại **khớp** ETag client đang giữ | Chống ghi đè thay đổi của người khác |
| `If-None-Match: *` | Chỉ thực hiện nếu resource **chưa tồn tại** theo ngữ nghĩa condition của operation | Tạo blob mới theo tên cố định, tránh overwrite |
| `If-None-Match: "<etag>"` | Thực hiện khi ETag hiện tại **không khớp**; thường dùng đọc/cache có điều kiện | Tránh gửi lại nội dung không thay đổi |
| `If-Unmodified-Since` | Chỉ thực hiện nếu resource không bị sửa sau mốc thời gian chỉ định | Điều kiện dựa trên thời gian; kém chính xác hơn ETag |
| `If-Modified-Since` | Chỉ thực hiện nếu resource đã sửa sau mốc thời gian chỉ định | Truy vấn/đọc có điều kiện |
| **Lease ID** | Yêu cầu phải mang lease ID khi một blob có active lease mà operation cần nó | Pessimistic concurrency trên blob đã khóa |

Với `If-Match` không đạt, API Blob thông thường trả **HTTP 412 Precondition Failed**. Với `If-None-Match: *` ở operation tạo mới, cách SDK ánh xạ operation có thể dẫn đến **412 hoặc 409** tùy API/tình huống (ví dụ blob đã tồn tại). Ở tầng ứng dụng, hãy đọc `BlobStorageException` và Azure Storage error code để phân biệt **xung đột điều kiện** với lỗi phân quyền, network hoặc blob không tồn tại.

Không nên dựa trên `Last-Modified` nếu chính xác phiên bản là yêu cầu quan trọng: timestamp không đại diện trực tiếp cho token phiên bản mà client đã đọc và có giới hạn về độ phân giải/thứ tự.

## 5. Cơ chế optimistic concurrency với If-Match

Mô hình **optimistic concurrency** giả định tranh chấp không quá thường xuyên, cho phép nhiều bên đọc song song và **chỉ khóa logic tại thời điểm ghi** bằng điều kiện trên ETag.

~~~mermaid
sequenceDiagram
    participant A as Người dùng A
    participant B as Người dùng B
    participant API as Spring Boot API
    participant ST as Azure Blob Storage
    A->>API: GET /documents/42
    API->>ST: Đọc blob và ETag
    ST-->>A: Nội dung + ETag v1 (qua API)
    B->>API: GET /documents/42
    API->>ST: Đọc blob và ETag
    ST-->>B: Nội dung + ETag v1 (qua API)
    A->>API: PUT + If-Match: v1
    API->>ST: Upload có If-Match v1
    ST-->>API: Thành công, ETag v2
    API-->>A: 200 OK / ETag v2
    B->>API: PUT + If-Match: v1
    API->>ST: Upload có If-Match v1
    ST-->>API: 412 Precondition Failed
    API-->>B: 412; cần tải lại hoặc hợp nhất
~~~

**Quy trình ở backend:**

1. Client gọi API đọc và nhận **nội dung + ETag**.
2. Client chỉnh sửa nội dung trên bản đã đọc.
3. Client gửi cập nhật kèm **ETag cũ** trong `If-Match`.
4. Backend kiểm tra authentication/authorization và chuyển ETag vào `BlobRequestConditions` trong **cùng request ghi**.
5. Azure Storage kiểm tra ETag hiện tại. Khớp → ghi; không khớp → từ chối.
6. Nếu lỗi 412, backend trả xung đột điều kiện; client tải bản mới rồi quyết định **ghi đè có chủ đích, hợp nhất hoặc hủy thao tác**.

**Lỗi 412 là một kết quả nghiệp vụ bình thường khi có tranh chấp**, không nhất thiết là lỗi hệ thống. Không tự động retry bằng cách lấy ETag mới rồi ghi lại payload cũ: làm vậy sẽ phá hủy ý nghĩa của optimistic concurrency và có thể làm mất cập nhật của người khác.

## 6. Chuẩn bị Spring Boot và Azure Blob client

### 6.1. Dependency

Spring Cloud Azure giúp Spring Boot cấu hình client với Azure Identity phù hợp. Ví dụ Maven (chọn BOM tương thích với Spring Boot đang dùng):

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

Property `spring-cloud-azure.version` cần được định nghĩa ở POM/build của project. Không lựa chọn phiên bản tùy tiện vì tương thích Spring Boot và Java phụ thuộc BOM.

### 6.2. Cấu hình ứng dụng

~~~yaml
spring:
  cloud:
    azure:
      storage:
        blob:
          account-name: ${AZURE_STORAGE_ACCOUNT_NAME}

app:
  documents:
    container: ${DOCUMENTS_CONTAINER:documents}
~~~

Container `documents` phải được tạo trước, ở chế độ **private**. Trên Azure, ưu tiên **managed identity** và role data-plane `Storage Blob Data Contributor` nếu ứng dụng cần cập nhật blob; máy local có thể dùng developer identity qua Azure CLI theo cấu hình Azure Identity. Cần kiểm tra cả storage firewall, private endpoint và DNS.

Không hardcode account key hoặc SAS token trong mã nguồn; **ETag không phải credential** và không cấp quyền đọc/ghi. Có ETag đúng nhưng không có quyền Blob vẫn bị từ chối.

### 6.3. Client dùng chung

~~~java
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class DocumentBlobContainer {
    private final BlobContainerClient client;

    public DocumentBlobContainer(
            BlobServiceClient blobServiceClient,
            @Value("${app.documents.container}") String containerName) {
        this.client = blobServiceClient
                .getBlobContainerClient(containerName);
    }

    public BlobContainerClient client() {
        return client;
    }
}
~~~

`getBlobContainerClient` chỉ tạo đối tượng SDK trỏ tới container; không tự tạo container trên Azure. Các client SDK có thể dùng lại qua nhiều request và đã được cấu hình HTTP pipeline/credential, nên không cần khởi tạo client mới ở mỗi lần gọi.

## 7. Cập nhật blob có điều kiện bằng Azure SDK for Java

### 7.1. Đọc ETag

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.models.BlobProperties;

BlobClient blob = container.getBlobClient("contracts/contract-42.json");
BlobProperties properties = blob.getProperties();

String currentETag = properties.getETag();
System.out.println("ETag hiện tại: " + currentETag);
~~~

`getProperties()` lấy ETag và metadata hệ thống, nhưng không tự khóa nội dung. Khi client cần đọc **nội dung và ETag thuộc cùng một trạng thái**, phải thiết kế thao tác đọc phù hợp: dùng ETag trả từ response download hoặc dùng điều kiện/phiên bản blob khi tải sau khi đọc properties. Nếu chỉ lấy ETag từ lần HEAD rồi download không điều kiện, blob có thể thay đổi giữa hai request và làm nội dung/ETag không tương ứng.

### 7.2. Upload bằng If-Match

Mẫu dưới đây dùng `BlobParallelUploadOptions` cho upload và `BlobRequestConditions` để Azure kiểm tra ETag. Dữ liệu nhỏ dùng `BinaryData.fromString` để code tập trung vào đồng thời; tài liệu lớn nên sử dụng stream/transfer options, giữ nguyên nguyên tắc condition.

~~~java
import com.azure.core.util.BinaryData;
import com.azure.core.util.Context;
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.models.BlobContentInfo;
import com.azure.storage.blob.models.BlobRequestConditions;
import com.azure.storage.blob.options.BlobParallelUploadOptions;
import java.time.Duration;

public static String replaceIfUnchanged(
        BlobClient blob, String json, String expectedETag) {
    if (expectedETag == null || expectedETag.isBlank()
            || "*".equals(expectedETag.trim())) {
        throw new IllegalArgumentException("Cần ETag cụ thể của bản đã đọc");
    }

    BlobRequestConditions condition = new BlobRequestConditions()
            .setIfMatch(expectedETag);

    BlobParallelUploadOptions options =
            new BlobParallelUploadOptions(BinaryData.fromString(json))
                    .setRequestConditions(condition);

    BlobContentInfo result = blob.uploadWithResponse(
            options, Duration.ofSeconds(60), Context.NONE).getValue();
    return result.getETag();
}
~~~

Điều kiện `setIfMatch(expectedETag)` được gửi **kèm request ghi**; Azure quyết định có cho phép upload hay không bằng ETag đang tồn tại tại thời điểm xử lý. Đây là điểm khác biệt quan trọng so với:

~~~java
// SAI về tính nguyên tử: HEAD và upload là hai yêu cầu riêng.
if (blob.getProperties().getETag().equals(expectedETag)) {
    blob.upload(new java.io.ByteArrayInputStream(bytes), bytes.length, true);
}
~~~

**Về độ dài/streaming:** ví dụ `BinaryData.fromString` chỉ phù hợp dữ liệu nhỏ. Với file lớn cần dùng API upload có `InputStream`/chế độ parallel upload hỗ trợ condition hoặc áp dụng điều kiện ở bước commit block list. Nếu tự `stageBlock` từng phần, đừng chỉ kiểm tra ETag ở đầu job rồi `commitBlockList` **không có condition**: một worker khác có thể sửa blob trong lúc các block đang được tải lên.

### 7.3. Nhận biết xung đột

~~~java
import com.azure.storage.blob.models.BlobStorageException;

try {
    String newETag = replaceIfUnchanged(blob, newJson, oldETag);
    System.out.println("Lưu thành công, ETag mới: " + newETag);
} catch (BlobStorageException ex) {
    if (ex.getStatusCode() == 412) {
        // Không ghi lại payload cũ bằng overwrite=true.
        System.out.println("Tài liệu đã thay đổi; cần tải lại");
    } else {
        throw ex;
    }
}
~~~

Phân biệt `412` (điều kiện không đạt) với `403` (quyền), `404` (blob không tồn tại) và lỗi tạm thời như `503`. Với operation cụ thể, dùng thêm storage error code khi status HTTP chưa đủ để chẩn đoán.

## 8. Thiết kế REST API Spring Boot có If-Match

Để trình duyệt/ứng dụng mobile tham gia optimistic concurrency, cần đưa ETag ra HTTP response khi đọc và nhận lại ETag trong request cập nhật.

### 8.1. Quy ước API

~~~http
GET /api/documents/42

HTTP/1.1 200 OK
ETag: "0x8E123456789ABCD"
Content-Type: application/json

{"title":"Hợp đồng A","status":"DRAFT"}
~~~

~~~http
PUT /api/documents/42
If-Match: "0x8E123456789ABCD"
Content-Type: application/json

{"title":"Hợp đồng A đã sửa","status":"DRAFT"}
~~~

Khi lưu thành công, API có thể trả `204 No Content` với **ETag mới**. Khi client gửi ETag cũ, trả `412 Precondition Failed`. Nếu client không gửi `If-Match` mà API bắt buộc điều kiện phiên bản, trả `428 Precondition Required`. Phân biệt:

- **409 Conflict**: xung đột quy tắc nghiệp vụ (ví dụ trạng thái hợp đồng không cho chuyển tiếp).
- **412 Precondition Failed**: điều kiện HTTP `If-Match`/`If-None-Match` không đạt.
- **428 Precondition Required**: API yêu cầu một precondition nhưng client chưa gửi.

### 8.2. Controller rút gọn

Ví dụ dùng Spring Boot 3 / Java 17+. `DocumentAuthorization` là dịch vụ nghiệp vụ **giả định**: nó ánh xạ `documentId` sang blob name sau khi xác thực người dùng và kiểm tra tenant/quyền. Không dùng tên blob trực tiếp do client tùy ý truyền.

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.models.BlobStorageException;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/documents")
public class DocumentVersionController {
    private final BlobContainerClient container;
    private final DocumentAuthorization authorization;

    public DocumentVersionController(
            DocumentBlobContainer documentBlobContainer,
            DocumentAuthorization authorization) {
        this.container = documentBlobContainer.client();
        this.authorization = authorization;
    }

    @GetMapping(value = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<String> get(@PathVariable String id) {
        String name = authorization.requireReadAccess(id);
        BlobClient blob = container.getBlobClient(name);

        // Ví dụ dành cho JSON nhỏ: đọc rồi đối chiếu ETag trước/sau.
        // Nếu resource đổi trong lúc đọc, thử lại tối đa ba lần.
        String content = null;
        String etag = null;
        for (int attempt = 0; attempt < 3; attempt++) {
            String before = blob.getProperties().getETag();
            String candidate = blob.downloadContent().toString();
            String after = blob.getProperties().getETag();
            if (before.equals(after)) {
                content = candidate;
                etag = after;
                break;
            }
        }
        if (etag == null) {
            throw new ResponseStatusException(
                    HttpStatus.CONFLICT,
                    "Tài liệu đang thay đổi; hãy tải lại");
        }

        return ResponseEntity.ok()
                .header(HttpHeaders.ETAG, etag)
                .contentType(MediaType.APPLICATION_JSON)
                .body(content);
    }

    @PutMapping(value = "/{id}", consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Void> put(
            @PathVariable String id,
            @RequestHeader(value = HttpHeaders.IF_MATCH, required = false)
                    String expectedETag,
            @RequestBody String json) {
        if (expectedETag == null || expectedETag.isBlank()
                || "*".equals(expectedETag.trim())) {
            throw new ResponseStatusException(
                    HttpStatus.PRECONDITION_REQUIRED,
                    "Cần If-Match với ETag cụ thể");
        }

        String name = authorization.requireWriteAccess(id);
        BlobClient blob = container.getBlobClient(name);
        try {
            String newETag = replaceIfUnchanged(blob, json, expectedETag);
            return ResponseEntity.noContent()
                    .header(HttpHeaders.ETAG, newETag)
                    .build();
        } catch (BlobStorageException ex) {
            if (ex.getStatusCode() == 412) {
                throw new ResponseStatusException(
                        HttpStatus.PRECONDITION_FAILED,
                        "Tài liệu đã được cập nhật bởi tác nhân khác");
            }
            throw ex;
        }
    }
}
~~~

`replaceIfUnchanged` là hàm ở mục 7.2 (trong project thật hãy đưa vào một `@Service` và inject), còn `DocumentAuthorization` và dữ liệu nghiệp vụ phải được triển khai riêng. **GET trên minh họa kỹ thuật đối chiếu ETag trước và sau khi đọc một JSON nhỏ**: nếu blob đổi trong quá trình đọc, request thử lại một số lần hữu hạn rồi trả 409. Cách này tốn nhiều lần gọi Storage và `downloadContent()` tải body vào bộ nhớ; với dữ liệu lớn hoặc hệ thống có mức tranh chấp cao, hãy dùng API tải có **request condition** hoặc truy cập theo **version ID** để gắn nội dung lẫn ETag vào một phiên bản một cách hiệu quả.

Với API thực tế còn cần validate JSON/schema, kiểm soát độ lớn request, lọc dữ liệu được phép chỉnh sửa, kiểm tra Content-Type, ghi audit log và tránh expose nội dung lỗi SDK nhạy cảm. ETag là điều kiện đồng thời, **không thay thế kiểm tra quyền sở hữu tài liệu**.

### 8.3. UX khi nhận 412

Khi xảy ra xung đột, frontend nên:

1. Giữ bản thay đổi chưa lưu của người dùng.
2. Hiển thị rằng tài liệu đã được người khác cập nhật.
3. Tải bản mới nhất và ETag mới.
4. Cho người dùng so sánh, hợp nhất hoặc quyết định ghi đè **sau khi xác nhận rõ ràng**.
5. Gửi request mới với ETag tương ứng bản vừa xem.

Không tự biến 412 thành retry vô điều kiện. Với thao tác có thể hợp nhất tự động (ví dụ sửa các field độc lập), logic merge phải có quy tắc và test phù hợp; Azure chỉ bảo vệ một resource, không hiểu nghiệp vụ JSON.

## 9. Tạo mới mà không ghi đè: If-None-Match

Nhiều request có thể đồng thời cố tạo blob cùng tên, ví dụ `exports/monthly-2026-11.csv`. Cách sai là gọi `exists()` rồi upload. Cách đúng là gửi **điều kiện tạo mới** cùng request:

~~~java
import com.azure.core.util.BinaryData;
import com.azure.core.util.Context;
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.models.BlobRequestConditions;
import com.azure.storage.blob.options.BlobParallelUploadOptions;

BlobRequestConditions createOnly = new BlobRequestConditions()
        .setIfNoneMatch("*");

BlobParallelUploadOptions options = new BlobParallelUploadOptions(
        BinaryData.fromString("month,total\n2026-11,1520\n"))
        .setRequestConditions(createOnly);

blob.uploadWithResponse(options, null, Context.NONE);
~~~

Ý nghĩa: blob chỉ được tạo khi điều kiện **chưa tồn tại** phù hợp. Nếu hai worker cùng cố tạo một tên, server cho phép tối đa một thao tác tạo thành công ở thời điểm cạnh tranh; thao tác còn lại phải xử lý lỗi điều kiện/resource đã tồn tại theo API cụ thể.

Với SDK cấp cao `upload(..., overwrite=false)`, ứng dụng cũng có cơ chế không ghi đè cho trường hợp tạo mới thông thường. Điều kiện `If-None-Match: *` hữu ích khi cần diễn đạt **ý định concurrency** rõ ràng cùng các request options. Một số API upload nhiều block có các bước stage rồi commit; cần bảo đảm điều kiện ràng buộc ở **bước xác nhận cuối** chứ không chỉ ở thao tác chuẩn bị.

## 10. Cập nhật metadata, xóa và download có điều kiện

### 10.1. Metadata và HTTP properties

Các thao tác `setMetadata` hoặc thay đổi HTTP headers của blob có thể làm ETag thay đổi. Do đó nếu người dùng A đang sửa nội dung còn worker B gắn metadata, ETag có thể đổi dù byte nội dung chưa đổi.

Thiết kế phải phân biệt:

- **Dữ liệu blob**: PDF, JSON, ảnh, file xuất.
- **Metadata/HTTP properties của blob**: content type, cache control, custom metadata.
- **Metadata nghiệp vụ trong database**: owner, trạng thái duyệt, quyền và quan hệ với tài liệu.

Với cập nhật metadata cạnh tranh, dùng overload SDK hỗ trợ `BlobRequestConditions.setIfMatch(etag)`. `setMetadata` không mặc nhiên là thao tác cộng thêm một key: nếu truyền map mới, có thể **thay thế toàn bộ custom metadata hiện tại**. Cần đọc/merge và gắn condition khi giữ key cũ là yêu cầu bắt buộc.

### 10.2. Xóa blob có điều kiện

Một API xóa cần cân nhắc tình huống client đọc v1 rồi người khác cập nhật v2. Xóa **không có condition** có thể loại bỏ phiên bản mà client xóa chưa từng thấy. Nguyên tắc:

~~~java
import com.azure.storage.blob.models.BlobRequestConditions;
import com.azure.storage.blob.models.DeleteSnapshotsOptionType;
import com.azure.core.util.Context;

BlobRequestConditions onlyIfUnchanged =
        new BlobRequestConditions().setIfMatch(expectedETag);

// Với SDK hỗ trợ overload này, điều kiện nằm trong request DELETE.
blob.deleteWithResponse(
        DeleteSnapshotsOptionType.INCLUDE,
        onlyIfUnchanged,
        null,
        Context.NONE);
~~~

`DeleteSnapshotsOptionType.INCLUDE` có ý nghĩa khi có snapshot; **Blob versioning, soft delete, immutability policy hoặc legal hold** có thể làm vòng đời xóa khác với “xóa vĩnh viễn ngay lập tức”. Trước khi xóa phải kiểm tra authorization, chính sách retention và trạng thái nghiệp vụ.

### 10.3. Đọc có điều kiện và caching

`If-None-Match` cũng được dùng khi client hỏi liệu bản cache còn mới không. Một API đọc có thể trả **304 Not Modified** nếu resource không đổi, hoặc gửi nội dung mới cùng ETag nếu đã đổi. Đây là **cache validation**, khác với kiểm soát lost update lúc ghi.

Đọc tệp lớn nên dùng **streaming** và có thể dùng các request condition hoặc version ID để giữ dữ liệu nhất quán. Nếu cần HTTP Range để tiếp tục tải, phải hỗ trợ chuẩn `Range`/`If-Range`/`206 Partial Content` tương ứng và bảo đảm byte range đọc từ cùng phiên bản blob; trả cả file vào RAM rồi cắt đoạn không phù hợp cho file lớn.

## 11. Khi nào dùng lease thay vì ETag?

Optimistic concurrency hợp khi số lần ghi trùng ít và chấp nhận người dùng xử lý xung đột. Khi một tác vụ cần quyền ghi độc quyền trong thời gian dài (ví dụ tiến trình cập nhật nhiều phần một blob), có thể xem xét **Blob lease** để thực hiện **pessimistic concurrency**.

| Tiêu chí | ETag / If-Match | Blob lease |
|---|---|---|
| Cách phối hợp | Cho phép nhiều bên đọc/sửa nháp; kiểm tra version khi ghi | Giành một lease trên blob; các thao tác ghi/xóa thuộc diện bảo vệ cần lease ID |
| Phù hợp | Chỉnh sửa tài liệu, JSON, metadata; xung đột hiếm | Một worker cần giữ quyền ghi độc quyền vào một blob trong thời gian xử lý |
| Chi phí | Ít trạng thái điều phối; xử lý 412 khi cạnh tranh | Cần acquire/renew/release lease, xử lý hết hạn/crash |
| Hạn chế | Không khóa và không ngăn client khác gửi ghi thiếu điều kiện | Không thay thế authorization, không tự khóa database hoặc blob khác |

Ví dụ ý tưởng với Azure SDK:

~~~java
import com.azure.storage.blob.specialized.BlobLeaseClient;
import com.azure.storage.blob.specialized.BlobLeaseClientBuilder;

BlobLeaseClient lease = new BlobLeaseClientBuilder()
        .blobClient(blob)
        .buildClient();

String leaseId = lease.acquireLease(30); // 30 giây
try {
    // Mọi thao tác ghi cần kèm request condition có leaseId phù hợp.
    // Nếu xử lý lâu, phải renew lease đúng hạn.
} finally {
    lease.releaseLease();
}
~~~

**Cảnh báo:** lease có thể đã hết hạn hoặc bị thay đổi trước khi vào `finally`, vì vậy `releaseLease()` cũng có thể ném lỗi. Ứng dụng thực tế cần xử lý điều này và dùng `try/finally` có log phù hợp. Lease không ngăn mọi hoạt động **đọc** blob; mục tiêu chính là điều phối các thao tác thuộc diện yêu cầu lease ID. Tên blob đang được xử lý không tự trở thành khóa phân tán cho toàn hệ thống.

Không nên dùng lease chỉ để tránh việc hai nhân viên cùng sửa JSON nếu hệ thống đã có UX xử lý 412. Ngược lại, nếu cần khóa **nhiều blob cùng database**, cả ETag lẫn lease đơn lẻ đều không cung cấp một transaction đa tài nguyên.

## 12. Versioning, snapshots và giới hạn đồng thời nhiều dịch vụ

### 12.1. ETag khác Blob versioning

Khi bật **Blob versioning**, một lần ghi có thể tạo version mới có `versionId`, giúp truy cập hoặc phục hồi nội dung cũ. ETag vẫn là token để kiểm tra liệu resource đích có đổi kể từ lúc client đọc hay chưa.

- **ETag + If-Match**: ngăn ghi dựa trên bản cũ vào blob hiện tại.
- **Versioning/snapshot**: giữ hoặc chỉ rõ phiên bản nội dung lịch sử khi cấu hình hỗ trợ.
- **Soft delete**: hỗ trợ khôi phục trong thời hạn lưu giữ, theo chính sách của account.

Bật versioning **không tự thay thế kiểm tra concurrency**: một request overwrite không điều kiện vẫn có thể thay nội dung hiện hành, dù phiên bản cũ còn được lưu. Cũng không nên dùng version ID thay ETag một cách máy móc, vì ngữ nghĩa điều kiện và cách truy cập phụ thuộc SDK/REST API.

### 12.2. Một ETag chỉ bảo vệ một resource

Giả sử nghiệp vụ “cập nhật hợp đồng” gồm:

1. Ghi JSON hợp đồng vào Blob.
2. Cập nhật record trạng thái trong database.
3. Gửi Azure Queue message cho worker tạo PDF.

`If-Match` chỉ làm cho **bước 1** có điều kiện nguyên tử trên blob. Không có transaction chung giữa Blob Storage, relational database và Storage Queue. Nếu ghi Blob thành công nhưng DB hoặc Queue lỗi, hệ thống có thể có trạng thái không đồng bộ.

Giải pháp ở tầng kiến trúc là một **trạng thái nghiệp vụ** (PENDING/READY/FAILED), một request/job ID ổn định, retry idempotent, outbox hoặc quy trình đối soát. Khi thao tác retry, phải phân biệt:

- Lỗi mạng khi chưa biết ghi thành công: đọc lại trạng thái hoặc ETag để xác minh.
- 412 thực sự vì client khác đã cập nhật: **không** tự bỏ điều kiện ghi.
- Ghi Blob thành công nhưng enqueue Queue lỗi: retry enqueue bằng job ID, tránh ghi lại Blob một cách vô thức.

### 12.3. Những giới hạn cần cân nhắc

- Không cập nhật trực tiếp một phần JSON theo semantics “merge field” chỉ nhờ ETag; ETag bảo vệ **toàn resource**, còn merge là logic nghiệp vụ.
- Nếu nhiều writer cùng tranh chấp một blob, tỷ lệ 412 có thể cao; cân nhắc phân vùng dữ liệu thành các blob riêng, event-driven design hoặc serialization ở tầng nghiệp vụ.
- ETag của blob có thể đổi khi metadata/properties đổi, làm tăng **false conflict ở góc nhìn nghiệp vụ** dù byte nội dung không đổi. Đây là hành vi bảo vệ tính nhất quán cấp resource.
- Với tệp lớn upload nhiều block, gắn condition vào thao tác **commit cuối cùng** để tránh ghi đè một phiên bản đã thay đổi trong lúc upload; lựa chọn API overload của SDK và kiểm thử đúng tình huống đua.
- Khi bật immutable storage hoặc legal hold, quyền và điều kiện ghi không vượt qua được chính sách bất biến/retention.

## 13. Kiểm thử tích hợp và chẩn đoán

### 13.1. Bài test xung đột cơ bản

**Azurite** phù hợp để kiểm tra các API Blob thông thường khi chạy local, nhưng không thay thế Azure thật cho các tình huống RBAC/managed identity, private endpoint, scale hoặc mọi khả năng của Blob service. Test dưới đây dùng hai bản ETag cũ để chứng minh một cập nhật sẽ bị từ chối.

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.models.BlobStorageException;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;

// blob trỏ tới một tên duy nhất trong container test của Azurite/Azure.
byte[] original = "version-1".getBytes(StandardCharsets.UTF_8);
blob.upload(new ByteArrayInputStream(original), original.length, true);

String etagA = blob.getProperties().getETag();
String etagB = blob.getProperties().getETag();

String afterA = replaceIfUnchanged(blob, "version-2-by-A", etagA);
if (afterA.equals(etagA)) {
    throw new AssertionError("ETag mong đợi đổi sau khi ghi");
}

boolean rejected = false;
try {
    replaceIfUnchanged(blob, "version-2-by-B", etagB);
} catch (BlobStorageException ex) {
    if (ex.getStatusCode() == 412) {
        rejected = true;
    } else {
        throw ex;
    }
}
if (!rejected) {
    throw new AssertionError("Phải từ chối ghi dựa trên ETag cũ");
}
~~~

Đây là đoạn mã minh họa đặt trong test class có sẵn `BlobClient blob` và helper `replaceIfUnchanged` ở mục 7.2. Trong JUnit thật nên dùng assertion framework, tạo blob name riêng từng test, xóa dữ liệu trong `finally` và test cả **nội dung cuối vẫn là version-2-by-A**. Không dùng container production để chạy test có overwrite/delete.

### 13.2. Test cạnh tranh thật

Một test tuần tự chỉ kiểm chứng điều kiện ETag cũ. Để test race thực tế, tạo hai task cùng đọc **một ETag**, đồng bộ cho chúng bắt đầu cập nhật gần như đồng thời, sau đó kiểm tra:

- Chỉ **một** thao tác ghi có điều kiện thành công cho một ETag gốc.
- Thao tác còn lại nhận lỗi điều kiện, không ghi đè kết quả thành công.
- Nội dung và ETag sau cùng tương ứng lần ghi được chấp nhận.
- Không có retry tự động nào phá bỏ `If-Match`.

Số lần lặp và mức song song phải phù hợp môi trường test để tránh test flakiness do network; nếu cần kiểm tra tải lớn hoặc latency, dùng tài khoản Azure staging và giám sát.

### 13.3. Ma trận lỗi cần phân biệt

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| **412 Precondition Failed** | ETag đã đổi, điều kiện ghi/đọc không đạt | Tải lại version, merge hoặc yêu cầu người dùng quyết định |
| **428 từ API ứng dụng** | Thiếu `If-Match` nhưng endpoint yêu cầu | Client gửi ETag nhận từ lần đọc |
| **409 Conflict** | Blob đã tồn tại, active lease hoặc xung đột operation tùy API | Xem Azure error code, lease/overwrite setting |
| **404 Not Found** | Blob bị xóa/đổi tên hoặc sai container/account | Kiểm tra resource ID, trạng thái xóa/version |
| **403 Forbidden** | Principal thiếu quyền data plane, SAS sai quyền/hạn, firewall | Kiểm tra identity/RBAC, SAS, network |
| **Timeout/5xx** | Sự cố mạng/service/SDK retry | Đối soát có ghi thành công không trước khi retry |
| **Nhiều 412 dù ít người sửa** | Background worker thường xuyên cập nhật metadata/properties | Xem lại mô hình tài nguyên và tách metadata nghiệp vụ |

### 13.4. Security và observability

Đo **tỷ lệ 412**, số request thành công, latency, retry, kích thước payload, số lượt sửa cùng tài liệu và phân phối lỗi theo operation. Log `documentId`, request ID/correlation ID, version/ETag nếu chính sách logging cho phép, nhưng không log dữ liệu nhạy cảm, JWT, account key hoặc SAS URL.

Khi dùng managed identity, xác thực danh tính ứng dụng và gán **Storage Blob Data Contributor** đúng scope là điều kiện cần cho cập nhật. API vẫn phải kiểm tra **owner/tenant/role nghiệp vụ** trước khi cho phép sửa/xóa blob. ETag không thay thế authentication/authorization.

## 14. Bài tập tình huống và câu hỏi tự kiểm tra

**Tình huống A — Hai người sửa hợp đồng:** Cả A và B đọc cùng một ETag. A lưu trước, B nhận 412. Hãy thiết kế UI hiển thị sự khác biệt và quy trình hợp nhất, đồng thời giải thích vì sao backend không được tự ghi lại payload của B mà bỏ điều kiện.

**Tình huống B — Job xuất báo cáo duy nhất:** Nhiều worker đồng thời tạo `exports/2026-11.csv`. Hãy dùng `If-None-Match: *` hoặc upload không overwrite, bảo đảm chỉ một tác nhân tạo bản committed theo tên cố định; xử lý xung đột mà không xóa dữ liệu đã tạo.

**Tình huống C — Tệp 5 GiB theo block:** Worker A bắt đầu stage, worker B cập nhật blob khi A đang upload. Hãy giải thích **tại sao check ETag đầu job chưa đủ**, và điều kiện nào phải được gắn vào bước commit danh sách block cuối.

**Tình huống D — Lỗi 403 sau khi thêm If-Match:** Ứng dụng local có thể đọc và ghi blob nhưng môi trường Azure không thể sửa. Hãy phân biệt lỗi quyền của **managed identity**, role data plane, container scope và firewall với lỗi 412 do ETag.

**Tình huống E — Triển khai đa cloud:** Khi chuyển từ Azure Blob Storage sang **Amazon S3** hoặc **Google Cloud Storage**, vẫn cần chống lost update nhưng API khác. S3 có các điều kiện HTTP như `If-Match`/`If-None-Match` cho một số operation; GCS dùng điều kiện **generation/metageneration**. Đừng giả định ETag của ba provider có ngữ nghĩa hoặc cách áp dụng hoàn toàn giống nhau.

### Câu hỏi tự kiểm tra

1. **Tại sao gọi `exists()` trước khi upload vẫn có race?** Vì kiểm tra và ghi là hai request độc lập; bên khác có thể thay dữ liệu giữa chúng.
2. **`If-Match` nên chứa ETag nào?** ETag của chính phiên bản mà người dùng đã đọc và đang sửa, không phải ETag vừa được server đọc lại ngay trước khi ghi để “lách” xung đột.
3. **Bị 412 thì có nên retry với ETag mới ngay không?** Không. Cần xem nội dung mới và xử lý xung đột nghiệp vụ.
4. **ETag có phải hash của blob không?** Không; ETag là token trạng thái resource, hash dùng để xác minh byte.
5. **`If-None-Match: *` giải quyết gì?** Điều kiện tạo mới, ngăn request vô tình ghi đè resource đã tồn tại.
6. **Lease có ngăn người khác đọc blob không?** Thông thường không; lease chủ yếu kiểm soát thao tác ghi/xóa thuộc phạm vi lease.
7. **Versioning có thay thế If-Match không?** Không; versioning phục vụ lưu lịch sử/khôi phục, điều kiện ghi giúp tránh lost update.
8. **ETag có giữ database và Queue nhất quán cùng Blob không?** Không; phải dùng trạng thái nghiệp vụ, outbox/retry/đối soát.

## 15. Kết luận và tài liệu tham khảo

Khi nhiều tác nhân cùng sửa một blob, hãy **đọc ETag và gửi lại trong chính request ghi bằng `If-Match`**. Azure Blob Storage kiểm tra điều kiện phía server, nhận cập nhật hợp lệ và trả 412 khi có thay đổi cạnh tranh. Dùng **`If-None-Match: *`** để diễn đạt ý định tạo mới; cân nhắc **lease** khi cần quyền ghi độc quyền; dùng **versioning/snapshot** để giữ lịch sử chứ không thay thế kiểm soát đồng thời.

Trong Spring Boot, Spring Cloud Azure chịu trách nhiệm cấu hình client/credential, còn Azure Storage SDK cung cấp `BlobRequestConditions` và các overload ghi có điều kiện. Kết hợp chúng với **managed identity, RBAC tối thiểu, kiểm tra quyền nghiệp vụ, retry idempotent và integration test**. Đây là nguyên tắc quan trọng khi triển khai object storage trên Azure và khi so sánh với S3/GCS, dù các API cụ thể có khác nhau.

### Tài liệu tham khảo chính thức

- [Microsoft Learn — Manage concurrency in Blob Storage](https://learn.microsoft.com/azure/storage/blobs/concurrency-manage)
- [Microsoft Learn — Specify conditional headers for Blob service operations](https://learn.microsoft.com/rest/api/storageservices/specifying-conditional-headers-for-blob-service-operations)
- [Microsoft Learn — Blob versioning](https://learn.microsoft.com/azure/storage/blobs/versioning-overview)
- [Microsoft Learn — Azure Storage Blob Java client library](https://learn.microsoft.com/azure/storage/blobs/storage-quickstart-blobs-java)
- [Microsoft Learn — Azure Blob Storage authorization with Microsoft Entra ID](https://learn.microsoft.com/azure/storage/blobs/authorize-access-azure-active-directory)
- [Microsoft Learn — Spring Cloud Azure](https://learn.microsoft.com/azure/developer/java/spring-framework/)
- [Microsoft Learn — Use Azurite for local Azure Storage development](https://learn.microsoft.com/azure/storage/common/storage-use-azurite)
