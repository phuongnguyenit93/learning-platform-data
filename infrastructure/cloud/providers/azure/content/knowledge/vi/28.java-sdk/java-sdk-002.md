# Đồng bộ và bất đồng bộ trong Azure Java client

## 1. Một bài toán, hai cách gọi Azure

Một ứng dụng Java phục vụ tài liệu cho nhân viên có ba việc:

1. Đọc một tệp trong **Azure Blob Storage** khi người dùng tải trang.
2. Tải lên nhiều tệp PDF cùng lúc từ một hàng đợi.
3. Ghi số liệu về latency, lỗi, dung lượng và chi phí lên **Azure Monitor**.

Người lập trình có thể chọn **Azure SDK client đồng bộ (synchronous)** hoặc **client bất đồng bộ (asynchronous)**. Cả hai đều làm việc với cùng dịch vụ Azure nhưng khác cách quản lý luồng thực thi, phản hồi, tài nguyên và áp lực tải.

Bài học thuộc chương **Azure SDK cho Java** trong module **CLOUD_PROVIDERS_AZURE**, gắn việc sử dụng client vào hành trình học subscription, resource group, Microsoft Entra ID, mạng, tính toán, lưu trữ, dữ liệu, giám sát, bảo mật và kiểm soát chi phí trên Azure. Bài sử dụng **Azure Storage Blobs Java SDK v12** làm ví dụ cụ thể, sau đó khái quát nguyên tắc sang Azure Service Bus, Cosmos DB và các Java SDK khác. **Tên class, API trả về và tùy chọn retry của từng dịch vụ có thể khác nhau; không coi mọi client có cùng signature.**

### Tình huống xuyên suốt

Giả sử dịch vụ **documents-api** chạy trên Azure App Service hoặc AKS, đọc và ghi tệp trong Blob Storage. Ban đầu một endpoint tải một tệp mỗi request; sau đó tăng lên xử lý hàng nghìn tệp theo batch. Lựa chọn sync/async sẽ ảnh hưởng đến số threads, mức sử dụng memory, latency, cách xử lý errors, cancellation, backpressure và tính dễ bảo trì.

## 2. Mục tiêu học tập

Sau khi hoàn thành, bạn có thể:

1. Phân biệt thao tác blocking, nonblocking, concurrency, parallelism và asynchronous.
2. Giải thích cặp sync/async clients trong Azure SDK for Java.
3. Hiểu vai trò của Java Azure SDK v2 libraries, builder, HTTP pipeline, TokenCredential, transport và Reactor.
4. Tạo **BlobServiceClient** và **BlobServiceAsyncClient** bằng cùng cách xác thực.
5. Thực hiện upload/download/list bằng sync API và async API.
6. Giải thích **Mono**, **Flux**, **PagedFlux** và lazy execution.
7. Sử dụng **flatMap concurrency**, timeout, cancellation và error handling đúng cách.
8. Tránh block event-loop, subscribe-and-forget và unbounded concurrency.
9. Phân biệt wrapping blocking code trong Mono với nonblocking I/O thật.
10. Thiết kế retry/backoff phù hợp với 429/503/timeout và idempotency.
11. Chọn sync/async theo Spring MVC, Spring WebFlux, batch, Azure Functions hoặc virtual threads.
12. Quản lý lifecycle, credentials, network connection pools và memory khi tải tệp.
13. Đo p95/p99 latency, throughput, errors, thread usage, costs và quota.
14. Viết unit/integration tests có kiểm soát và một bài lab so sánh hai kiểu client.

## 3. Đồng bộ, bất đồng bộ, blocking và nonblocking

### 3.1. Đồng bộ (synchronous) theo cách gọi phổ biến

Người gọi chờ kết quả rồi mới thực hiện dòng kế tiếp.

~~~java
String content = readBlobSynchronously();
System.out.println(content);
~~~

Nếu lời gọi mất 300 ms, luồng hiện tại thường bị giữ chờ cho tới khi nhận kết quả hoặc lỗi. Đây là điều dễ hiểu trong chương trình imperative.

### 3.2. Bất đồng bộ (asynchronous)

Lời gọi có thể trả về một đại diện cho kết quả tương lai, còn operation thực được kích hoạt/sắp xếp theo API.

~~~java
Mono<String> pending = readBlobAsynchronously();
Mono<String> processed = pending.map(String::trim);
~~~

Nếu **pending** là một publisher cold như thường gặp ở Azure SDK Reactor, chỉ xây dựng pipeline chưa chắc đã phát request. Publisher được kích hoạt khi có subscription từ framework hoặc từ code.

### 3.3. Bốn khái niệm không đồng nghĩa

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Synchronous** | Caller chờ completion trước khi đi tiếp | BlobClient.downloadContent() |
| **Asynchronous** | Caller nhận future/publisher rồi xử lý kết quả sau | BlobAsyncClient.downloadContent() trả Mono |
| **Blocking** | Thread bị giữ chờ operation hoàn tất | Socket read hoặc Mono.block() |
| **Nonblocking** | Thread không phải chờ I/O trong khi chưa có dữ liệu | Reactor + async HTTP transport |
| **Concurrency** | Nhiều việc đang tiến triển cùng lúc | 50 requests in-flight |
| **Parallelism** | Nhiều tác vụ thực thi đồng thời trên nhiều cores | Nhiều CPU tasks trên worker pool |

Một method **trả Mono** nhưng bên trong gọi sync client và chờ trên event-loop vẫn là blocking I/O bị che giấu.

### 3.4. Sơ đồ so sánh

~~~mermaid
sequenceDiagram
    participant A as Application thread
    participant S as Azure SDK
    participant B as Azure Blob Storage
    A->>S: Sync download
    S->>B: HTTP request
    B-->>S: Response
    S-->>A: BinaryData
    Note over A: Caller chờ kết quả
~~~

~~~mermaid
sequenceDiagram
    participant A as Application thread
    participant S as Async SDK/HTTP
    participant B as Azure Blob Storage
    A->>S: Build Mono pipeline
    Note over A: Chưa phải luôn phát HTTP
    A->>S: Subscribe
    S->>B: HTTP request
    Note over A: Có thể xử lý việc khác
    B-->>S: Response event
    S-->>A: onNext/onComplete
~~~

## 4. Azure SDK for Java tổ chức clients ra sao?

Các thư viện Azure Java hiện đại thường có mô hình:

~~~text
Your Java application
       |
    Service Client
       |
 Azure SDK policies / retry / authentication / diagnostics
       |
  HTTP transport + Azure service
~~~

Đối với Storage Blobs:

- **BlobServiceClient**: sync client mức service.
- **BlobServiceAsyncClient**: async client mức service.
- **BlobContainerClient** / **BlobContainerAsyncClient**: mức container.
- **BlobClient** / **BlobAsyncClient**: mức blob.
- **BlobServiceClientBuilder**: cấu hình endpoint, credential, transport và tạo một trong hai kiểu client.

Không phải mọi thư viện có hậu tố AsyncClient tương ứng một-một; phải kiểm tra API của **dịch vụ/phiên bản SDK thực**. Azure SDK for Java cũng có thư viện quản lý ARM và data-plane; các mô hình API không hoàn toàn giống nhau.

### 4.1. Azure SDK v2 là gì?

Trong ngữ cảnh này, “Azure SDK for Java” chỉ nhóm thư viện hiện đại có artifacts thường bắt đầu bằng **com.azure** (ví dụ **azure-storage-blob**, **azure-identity**, **azure-core**), khác với một số SDK cũ/legacy. Không nhầm cách gọi này với version **12.x** của Storage Blob library.

### 4.2. Sync client có nhất thiết dùng HTTP blocking riêng không?

Bên trong implementation có thể dùng transport và cơ chế khác nhau; **hợp đồng quan trọng ở tầng người gọi** là sync method chỉ trả khi hoàn thành. Không cần tự suy rằng mọi sync client dùng một socket/thread riêng theo cùng một implementation.

### 4.3. Không chọn client bằng thói quen

Nếu ứng dụng mỗi phút chỉ chạy một job upload vài files, sync thường đơn giản. Nếu có hàng nghìn operations I/O-bound với HTTP reactive pipeline, async có thể giúp tiết kiệm threads **khi được dùng đúng**.

## 5. Kiến trúc Azure quanh documents-api

~~~mermaid
flowchart LR
    U[Users / Internal apps] --> API[Java documents-api]
    ID[Microsoft Entra ID / Managed identity] --> API
    API --> SDK[Azure Blob Client]
    SDK --> NET[HTTPS / VNet / Private Endpoint]
    NET --> BLOB[(Azure Blob Storage)]
    API --> MON[Azure Monitor / Application Insights]
    BLOB --> MON
~~~

- Resource group/subscription quản lý tài nguyên.
- Microsoft Entra ID xác thực danh tính Java workload.
- Azure RBAC data-plane quản lý quyền trên blobs.
- VNet/private endpoint quyết định đường kết nối được phép.
- App Service/AKS/Functions quản lý compute/lifecycle.
- Azure Monitor/Cost Management dùng để đo hiệu năng và chi phí request, storage, compute.

**Client async không tự tăng throughput của Storage account hoặc tạo thêm network/compute quota.**

## 6. Đặt câu hỏi đúng trước khi chọn sync/async

Cần đo/biết:

1. Một request làm mấy operations Azure?
2. Tỷ lệ thời gian I/O chờ so với CPU xử lý?
3. Có bao nhiêu requests đến đồng thời?
4. Framework xử lý request là blocking (Servlet/MVC) hay reactive (WebFlux)?
5. Có cần streaming dữ liệu lớn không?
6. Service có giới hạn requests/throughput/partitions nào?
7. Cần cancellation và deadline thế nào?
8. Đội phát triển có kinh nghiệm Reactor/debug reactive không?
9. JVM threads, CPU, memory và file-descriptor/connection limits ra sao?
10. Kết quả benchmark thực tế ở cùng SKU/network mới nói gì?

Đừng tuyên bố async luôn nhanh hơn cho một request. Cùng một REST operation với ít contention, latency thường bị chi phối bởi network và service, không phải cách Java biểu diễn kết quả.

## 7. Dependency Maven cho bài thực hành

Ví dụ dự án Java 17 với Azure Blob SDK hiện đại:

~~~xml
<dependencies>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-storage-blob</artifactId>
    <version>YOUR_APPROVED_12_X_VERSION</version>
  </dependency>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
    <version>YOUR_APPROVED_IDENTITY_VERSION</version>
  </dependency>
</dependencies>
~~~

Các version là **placeholders**, phải thay bằng phiên bản được tổ chức phê duyệt, tương thích Java và security scans. Có thể sử dụng **Azure SDK BOM** để thống nhất versions của các Azure libraries nếu phù hợp với dependency management; không trộn ngẫu nhiên các phiên bản azure-core/azure-storage-blob/azure-identity.

### 7.1. Reactor dependency

Các async Azure SDK clients thường sử dụng **Project Reactor**: **Mono<T>**, **Flux<T>** và kiểu paging của Azure. Các dependency liên quan có thể đã được kéo theo, nhưng project production phải kiểm tra dependency tree/BOM và tránh version conflicts.

### 7.2. HTTP transport

Azure SDK dựa trên HTTP client/transport được hỗ trợ (ví dụ Netty transport trong nhiều cấu hình). Trong hệ thống enterprise, phải xem proxy, TLS, connection pooling, observability và native transport nếu custom.

### 7.3. Không cài cả thư viện cũ lẫn mới chỉ vì ví dụ

Một codebase dùng Storage Blob SDK v12 nên nhất quán với API hiện đại; ví dụ cho **CloudBlobClient** từ SDK cũ không thay thế trực tiếp **BlobServiceClient**.

## 8. Xác thực: ưu tiên TokenCredential/managed identity

Trong các môi trường hỗ trợ, nên dùng Microsoft Entra ID và **DefaultAzureCredential** thay vì account key cố định. Với Azure Blob Storage, managed identity hoặc developer principal cần role data-plane như **Storage Blob Data Reader** để đọc, **Storage Blob Data Contributor** để ghi/sửa/xóa theo phạm vi được cấp.

**Azure ARM Contributor/Reader không mặc định đồng nghĩa quyền Blob data-plane.**

### 8.1. Environment

~~~text
AZURE_STORAGE_BLOB_ENDPOINT=https://<storage-account>.blob.core.windows.net
AZURE_STORAGE_CONTAINER=documents
~~~

Endpoint là cấu hình đáng tin, không lấy URL arbitrary từ user input (SSRF). Khi dùng private endpoint cần đảm bảo DNS và network routes phù hợp.

### 8.2. DefaultAzureCredential ở local và cloud

- Local: có thể sử dụng Azure CLI/developer identity đã đăng nhập.
- App Service/Functions: managed identity.
- AKS: Microsoft Entra Workload Identity hoặc cách tổ chức phê duyệt.
- CI/CD: federation/workload identity khi khả thi.

Một application chỉ có managed identity nhưng chưa có **Storage Blob Data Reader/Contributor** sẽ gặp lỗi quyền.

### 8.3. Quyền tối thiểu

Nếu endpoint chỉ đọc một container, không cấp quyền write/delete toàn account. Cần tách credential cho uploader, reader và administrator. Không in OAuth access token, storage key hoặc SAS vào logs.

## 9. Tạo một builder, xây sync và async client

Ví dụ factory dưới sử dụng **BlobServiceClientBuilder** cho cùng Storage account và TokenCredential:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceAsyncClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

public final class BlobClients {
    private BlobClients() { }

    private static String required(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing " + key);
        }
        return value;
    }

    public static TokenCredential credential() {
        return new DefaultAzureCredentialBuilder().build();
    }

    public static BlobServiceClient syncClient() {
        return new BlobServiceClientBuilder()
            .endpoint(required("AZURE_STORAGE_BLOB_ENDPOINT"))
            .credential(credential())
            .buildClient();
    }

    public static BlobServiceAsyncClient asyncClient() {
        return new BlobServiceClientBuilder()
            .endpoint(required("AZURE_STORAGE_BLOB_ENDPOINT"))
            .credential(credential())
            .buildAsyncClient();
    }
}
~~~

### 9.1. Vì sao dùng chung builder concept?

Builder giúp thống nhất endpoint, credential, retry/transport settings và client construction style. Ví dụ tạo hai objects riêng để so sánh; trong service production **chọn và tái sử dụng client** phù hợp, không tạo một client mới cho mỗi request.

### 9.2. Thread-safety và reuse

Các Azure service clients thông thường được thiết kế để dùng lại trong ứng dụng; chúng quản lý HTTP pipeline, credential, connection resources và internal policies. Giữ client như singleton/DI bean được quản lý phù hợp với thư viện.

### 9.3. Credential cũng nên được quản lý lifecycle

Dùng một credential instance qua dependency injection nếu cần, thay vì tạo DefaultAzureCredential liên tục. Credential có thể cache tokens và dùng resources; đối với lifecycle/closeability hãy theo API của implementation thực.

## 10. Sync upload và download tệp nhỏ

Với một blob văn bản nhỏ:

~~~java
import com.azure.core.util.BinaryData;
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;

import java.nio.charset.StandardCharsets;

BlobServiceClient service = BlobClients.syncClient();
BlobContainerClient container =
    service.getBlobContainerClient("documents");

BlobClient blob = container.getBlobClient("sample/hello.txt");

blob.upload(
    BinaryData.fromString("Xin chào Azure SDK for Java!"),
    true // overwrite=true: chỉ dùng khi nghiệp vụ cho phép.
);

byte[] bytes = blob.downloadContent().toBytes();
String result = new String(bytes, StandardCharsets.UTF_8);
System.out.println(result);
~~~

### 10.1. Lời gọi nào giữ thread chờ?

**upload** và **downloadContent** là sync operations. Khi server/network chậm, thread gọi method không được trả về cho đến khi operation hoàn tất hoặc lỗi.

### 10.2. Cẩn thận với overwrite

**overwrite=true** không phù hợp khi mỗi upload phải tạo record duy nhất hoặc không được ghi đè. Với duplicate/retry có thể cần conditional request, ETag hoặc blob naming cố định theo operation ID.

### 10.3. BinaryData.toBytes dùng bộ nhớ

Phương thức **downloadContent()** thuận tiện cho tệp nhỏ, nhưng nó có thể materialize toàn bộ payload. Với tệp lớn hoặc nhiều concurrent requests, dùng streaming download/transfer methods theo API phù hợp, tránh giữ hàng trăm MB cho mỗi request.

## 11. Async upload và download cùng một blob

Với async client, API phổ biến trả về **Mono**:

~~~java
import com.azure.core.util.BinaryData;
import com.azure.storage.blob.BlobAsyncClient;
import com.azure.storage.blob.BlobContainerAsyncClient;
import com.azure.storage.blob.BlobServiceAsyncClient;
import reactor.core.publisher.Mono;

import java.nio.charset.StandardCharsets;

BlobServiceAsyncClient service = BlobClients.asyncClient();
BlobContainerAsyncClient container =
    service.getBlobContainerAsyncClient("documents");

BlobAsyncClient blob =
    container.getBlobAsyncClient("sample/hello.txt");

Mono<String> operation = blob.upload(
    BinaryData.fromString("Xin chào async Azure SDK!"),
    true
).then(
    blob.downloadContent()
        .map(data ->
            new String(data.toBytes(), StandardCharsets.UTF_8))
);

// Spring WebFlux handler có thể return operation;
// tại ranh giới CLI/demo mới dùng block có timeout.
String result = operation.block(java.time.Duration.ofSeconds(30));
System.out.println(result);
~~~

### 11.1. Chưa phải chạy ngay khi tạo Mono

**Mono<String> operation** đại diện pipeline sẽ thực thi khi được subscribe. Với cold publishers của Azure async SDK, việc xây pipeline thường không gửi HTTP trước subscription.

### 11.2. Thứ tự do then bảo đảm

**upload(...).then(download...)** chỉ subscribe phần download sau khi upload hoàn thành thành công. Đây là orchestration kiểu reactive. Nếu upload lỗi, Mono kết thúc bằng error và download không diễn ra.

### 11.3. Chỉ block ở ranh giới imperative

Ở ví dụ CLI, **block(Duration)** giúp main thread chờ kết quả để in ra. Trong WebFlux event-loop, **không dùng block()**; trả Mono cho framework subscribe và quản lý backpressure/cancellation.

### 11.4. Async không giảm request charge

Sync và async cùng gọi Storage service. Pricing/transactions, dữ liệu truyền và bandwidth phụ thuộc workload và dịch vụ, không tự giảm chỉ vì dùng Mono.

## 12. Mono, Flux và PagedFlux cần hiểu điều gì?

| Kiểu | Biểu diễn | Ví dụ |
|---|---|---|
| **Mono<T>** | 0 hoặc 1 giá trị rồi complete/error | Download một blob hoặc upload response |
| **Flux<T>** | 0 đến nhiều phần tử | Luồng chunks/events |
| **PagedFlux<T>** | Kết quả phân trang của Azure async SDK | Liệt kê blobs |
| **PagedIterable<T>** | Iterable phân trang phía sync | Liệt kê blobs |
| **Publisher** | Contract phát dữ liệu theo subscription | Nền tảng Reactive Streams |

### 12.1. Signal model

Một Mono/Flux có thể phát:

- **onNext(value)**: có giá trị.
- **onComplete()**: hoàn tất.
- **onError(error)**: lỗi kết thúc pipeline.
- **cancel**: subscriber hủy subscription, chẳng hạn HTTP client disconnect.

Một publisher không được phát onNext sau terminal event.

### 12.2. Flux không nhất thiết là một network request

Một **PagedFlux** có thể gọi service nhiều lần để lấy các trang tiếp theo. Một **Flux<ByteBuffer>** có thể biểu diễn nhiều chunks từ một download. Đếm onNext events không đồng nghĩa đếm HTTP requests.

### 12.3. Cold và hot publishers

Azure SDK async APIs thường cung cấp cold publisher: mỗi subscription có thể phát một operation mới. Nếu bạn subscribe hai lần vào một Mono từ upload/submit, side effect có thể bị thực hiện hai lần. Không giả định publisher sẽ cache result tự động.

## 13. Sync list blobs: PagedIterable

Một thao tác listing trả nhiều phần tử và có thể lấy pages dần:

~~~java
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.models.BlobItem;

BlobContainerClient container =
    BlobClients.syncClient().getBlobContainerClient("documents");

for (BlobItem item : container.listBlobs()) {
    System.out.println(item.getName());
}
~~~

### 13.1. Listing có thể tốn nhiều service requests

Nếu container có hàng triệu blobs, vòng lặp có thể kéo dài, phát nhiều requests và tốn transactions. Cần giới hạn prefix/filter/paging theo yêu cầu, không liệt kê toàn container cho mỗi HTTP request.

### 13.2. Tại sao code nhìn đơn giản?

**PagedIterable** che phần lấy trang tiếp theo, caller đọc tuần tự và thread có thể block khi cần page mới.

### 13.3. Tránh giữ toàn bộ danh sách trong RAM

Không luôn chuyển listBlobs thành một List chứa mọi blob. Nếu chỉ cần vài tên hoặc cần xử lý từng page, giữ flow phân trang và giới hạn số kết quả.

## 14. Async list blobs: PagedFlux

~~~java
import com.azure.storage.blob.BlobContainerAsyncClient;
import com.azure.storage.blob.models.BlobItem;
import reactor.core.publisher.Flux;

BlobContainerAsyncClient container =
    BlobClients.asyncClient()
        .getBlobContainerAsyncClient("documents");

Flux<String> names = container.listBlobs()
    .map(BlobItem::getName)
    .take(100);

// Ví dụ trong Spring WebFlux: return names;
// Reactor framework subscribe khi có request.
~~~

### 14.1. take(100) giúp gì?

Nó giới hạn tối đa 100 items được chuyển downstream; dịch vụ có thể đã trả một trang nhiều hơn mức cần dùng tùy page size và buffering. Nếu cần giới hạn service-side, dùng list options và paging API đúng version.

### 14.2. PagedFlux và backpressure

Publisher nhận request demand từ subscriber theo Reactive Streams, nhưng cách SDK fetch pages/prefetch còn tùy implementation. Không coi backpressure ở Reactor là một global Azure service rate limiter.

### 14.3. Không subscribe() rồi bỏ kết quả

Một handler sai:

~~~java
public Mono<String> badHandler() {
    container.listBlobs()
        .take(10)
        .subscribe(item -> System.out.println(item.getName()));
    return Mono.just("Done");
}
~~~

Handler có thể trả Done trước khi listing hoàn tất; exceptions có thể không đến request pipeline và cancellation không được quản lý. Hãy **return publisher** hoặc **compose** nó vào pipeline caller đang chờ.

## 15. Chọn sync hay async cho một HTTP API?

| Tình huống | Lựa chọn thường hợp lý | Lý do |
|---|---|---|
| Spring MVC servlet endpoint, vài I/O calls | Sync client | Code đơn giản, framework có worker threads |
| Spring WebFlux reactive endpoint | Async client | Không block event-loop |
| CLI/script chạy theo lượt | Sync client | Dễ đọc, điều khiển và debug |
| Worker ingest nhiều blobs đồng thời | Async hoặc sync với bounded executor | Cần giới hạn concurrency và theo dõi failure |
| Tệp lớn, cần streaming không materialize | Streaming API phù hợp mô hình | Tránh memory pressure |
| Java virtual threads | Sync client có thể phù hợp | Virtual threads giảm chi phí chờ I/O, không tự tăng quota |
| Rất nhiều operations I/O-bound | Async thường đáng đánh giá | Tiết kiệm platform threads khi nonblocking đúng |

**Không có lựa chọn tuyệt đối**: thử nghiệm với số requests, payload và network giống workload thật, đồng thời xét độ phức tạp và cách nhóm quản lý sự cố.
## 16. Spring MVC: khi sync client là lựa chọn tự nhiên

Một Spring MVC/Servlet endpoint có thể gọi BlobClient trên worker thread:

~~~java
import com.azure.core.util.BinaryData;
import com.azure.storage.blob.BlobContainerClient;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import java.nio.charset.StandardCharsets;

@RestController
public final class DocumentMvcController {
    private final BlobContainerClient container;

    public DocumentMvcController(BlobContainerClient container) {
        this.container = container;
    }

    @GetMapping("/api/documents/{name}")
    public ResponseEntity<String> get(@PathVariable String name) {
        if (name == null || !name.matches("[a-zA-Z0-9_-]{1,80}")) {
            throw new IllegalArgumentException("Invalid document name");
        }

        BinaryData data = container.getBlobClient(name + ".txt")
            .downloadContent();

        return ResponseEntity.ok(
            new String(data.toBytes(), StandardCharsets.UTF_8));
    }
}
~~~

Đây chỉ là endpoint **đọc văn bản nhỏ**: thiếu authentication/authorization, size cap, content type và exception mapping; không dùng nguyên mẫu làm production API.

### 16.1. Worker thread là tài nguyên hữu hạn

Một số requests đồng thời, mỗi request chờ Azure Storage vài giây, có thể chiếm hết servlet threads và làm tăng queue latency. Đo workload thực trước khi tăng thread pool hoặc chuyển async.

### 16.2. Vì sao sync thường dễ bảo trì?

Stack trace quen thuộc, try/catch trực quan, thư viện imperative/JDBC tích hợp đơn giản. Với batch tuần tự hoặc các service có tải thấp, sự đơn giản này có giá trị.

### 16.3. Không cho SDK tràn vào controller

Nên đưa Blob operations vào **BlobGateway/DocumentService**. Controller quản lý authz và HTTP status; gateway quản lý SDK, timeout, metrics và exceptions.

## 17. Spring WebFlux: trả Mono cho framework

Trong reactive controller, trả publisher để framework subscribe và quản lý response/cancellation:

~~~java
import com.azure.storage.blob.BlobContainerAsyncClient;
import com.azure.storage.blob.BlobAsyncClient;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public final class DocumentReactiveController {
    private final BlobContainerAsyncClient container;

    public DocumentReactiveController(
            BlobContainerAsyncClient container) {
        this.container = container;
    }

    @GetMapping("/api/documents/{name}")
    public Mono<ResponseEntity<String>> get(
            @PathVariable String name) {

        if (!name.matches("[a-zA-Z0-9_-]{1,80}")) {
            return Mono.error(
                new IllegalArgumentException("Invalid document name"));
        }

        BlobAsyncClient blob =
            container.getBlobAsyncClient(name + ".txt");

        return blob.downloadContent()
            .map(data ->
                ResponseEntity.ok(data.toString()));
    }
}
~~~

### 17.1. Không gọi block trong event-loop

~~~java
// Anti-pattern trong WebFlux event loop:
return Mono.just(syncBlob.downloadContent().toString());
~~~

**syncBlob.downloadContent() đã chạy và chặn thread** trước khi Mono.just được tạo. Với reactive framework, dùng async client hoặc cô lập blocking code.

### 17.2. Async không bảo đảm mọi chặng nonblocking

Nếu lambda trong map gọi JDBC sync, đọc file lớn hoặc gọi một blocking HTTP library, event-loop vẫn bị giữ. Cần kiểm tra toàn pipeline, không chỉ return type.

### 17.3. Đọc file lớn không giống đọc text nhỏ

Cả hai ví dụ materialize payload. Với file lớn, streaming content bằng response body có giới hạn, xử lý Content-Type/Content-Length và backpressure là thiết kế thích hợp hơn.

## 18. Mono.just khác Mono.fromCallable

Một anti-pattern:

~~~java
// getBlobTextSync() chạy ngay lúc tạo Mono:
Mono<String> wrong = Mono.just(getBlobTextSync());
~~~

Nếu phải sử dụng legacy synchronous client từ reactive service, cô lập blocking call:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<String> wrapped = Mono
    .fromCallable(() -> getBlobTextSync())
    .subscribeOn(Schedulers.boundedElastic());
~~~

### 18.1. Bọc Mono không biến I/O thành nonblocking

getBlobTextSync vẫn blocking, chỉ chạy trên scheduler dành cho blocking work. Điều này giúp bảo vệ event-loop nhưng vẫn tiêu tốn worker threads.

### 18.2. boundedElastic không vô hạn

Pool và queue có hạn; nếu arrival rate lớn hơn service rate liên tục, queue backlog và latency tăng. Cần limit concurrency/rate và overload policy.

### 18.3. Khi nào đổi sang async SDK thật?

Khi workload chủ yếu là Azure I/O, có nhiều concurrent operations, và framework đã reactive, async Azure client thường đáng thử nghiệm hơn việc bọc sync client trên nhiều threads.

## 19. Reactor operators để điều phối operations

| Operator | Vai trò | Lưu ý |
|---|---|---|
| **map** | Biến đổi giá trị đồng bộ, nhanh | Không block trong lambda |
| **flatMap** | Chuyển một giá trị thành publisher khác | Có thể chạy song song |
| **concatMap** | Giữ thứ tự và xử lý theo tuần tự | Giảm concurrency |
| **flatMapSequential** | Subscribe song song, phát theo thứ tự | Có thể buffer |
| **then** | Bỏ kết quả trước, chờ hoàn tất | Hợp upload rồi read |
| **zip** | Kết hợp hai Mono | Có thể gọi concurrently |
| **onErrorResume** | Fallback theo exception | Không che lỗi |
| **doOnNext** | Ghi metrics/log ngắn gọn | Không dùng làm business pipeline |
| **timeout** | Giới hạn thời gian stage | Không bảo đảm rollback |
| **retryWhen** | Retry có điều kiện | Tránh double-retry |

Ví dụ upload rồi đọc, giữ thứ tự dependency:

~~~java
import com.azure.core.util.BinaryData;
import reactor.core.publisher.Mono;

Mono<String> savedThenRead =
    asyncBlob.upload(BinaryData.fromString("hello"), true)
        .then(asyncBlob.downloadContent())
        .map(BinaryData::toString);
~~~

Nếu cần ETag từ upload, dùng flatMap/compose giữ metadata thay vì then bỏ giá trị. Đừng dùng map trả Mono rồi quên flatten.

## 20. Exception handling đồng bộ và bất đồng bộ

Trong sync code:

~~~java
import com.azure.storage.blob.models.BlobStorageException;

try {
    String text = syncBlob.downloadContent().toString();
    processText(text);
} catch (BlobStorageException e) {
    if (e.getStatusCode() == 404) {
        handleMissingDocument();
    } else {
        throw e;
    }
}
~~~

Trong reactive code:

~~~java
import com.azure.storage.blob.models.BlobStorageException;
import reactor.core.publisher.Mono;

Mono<String> result = asyncBlob.downloadContent()
    .map(BinaryData::toString)
    .onErrorResume(BlobStorageException.class, e -> {
        if (e.getStatusCode() == 404) {
            return Mono.empty();
        }
        return Mono.error(e);
    });
~~~

### 20.1. Mono.empty không tự có nghĩa HTTP 404

Mono.empty chỉ không phát value. Trong một WebFlux endpoint, cần ánh xạ 404 bằng response/error handler rõ ràng; không để request trả 200 với body rỗng một cách mơ hồ.

### 20.2. Transport exception khác service exception

DNS, TLS và timeout có thể xuất hiện dưới các exception không phải BlobStorageException. Phân loại errors theo nguồn trước khi retry hoặc báo lỗi.

### 20.3. Không log payload/credential

Log status, sanitized error code, request ID, duration và operation; không log Blob SAS URL, account keys hoặc nội dung tệp nhạy cảm.

## 21. Lazy execution và subscribe-and-forget

Ví dụ một publisher chưa được thực thi:

~~~java
Mono<?> planned =
    asyncBlob.upload(BinaryData.fromString("hello"), true);

// Không return hoặc subscribe: operation có thể chưa chạy.
~~~

Trong WebFlux, hãy **return publisher**:

~~~java
@PostMapping("/api/hello")
public Mono<ResponseEntity<Void>> uploadHello() {
    return asyncBlob
        .upload(BinaryData.fromString("hello"), true)
        .thenReturn(ResponseEntity.ok().build());
}
~~~

Đây là fragment trong một controller có asyncBlob được inject và imports Spring phù hợp, chỉ minh họa completion behavior.

### 21.1. Anti-pattern fire-and-forget

~~~java
asyncBlob.upload(BinaryData.fromString("hello"), true)
    .subscribe();
return Mono.just("Done");
~~~

Caller có thể thấy Done trước khi upload thành công; cancellation và lỗi bị tách khỏi HTTP request, khó giám sát và retry.

### 21.2. Khi nào subscribe thủ công?

CLI, batch coordinator hoặc worker có subscription lifecycle rõ có thể subscribe với error/completion handlers. Trong reactive frameworks, thường để framework subscribe.

### 21.3. Double subscription và duplicate side effects

Các publisher từ Azure async clients thường cold; subscribe hai lần có thể thực hiện hai calls. Với write operations, cần thiết kế idempotency, không giả định publisher tự cache.

## 22. flatMap concurrency cho batch

Một service cần đọc nhiều blobs nhưng không muốn phát toàn bộ calls đồng thời:

~~~java
import com.azure.storage.blob.BlobContainerAsyncClient;
import reactor.core.publisher.Flux;

import java.util.List;

BlobContainerAsyncClient container =
    BlobClients.asyncClient()
        .getBlobContainerAsyncClient("documents");

List<String> names = List.of(
    "a.txt", "b.txt", "c.txt");

Flux<String> results = Flux.fromIterable(names)
    .flatMap(name ->
        container.getBlobAsyncClient(name)
            .downloadContent()
            .map(body -> name + ": " + body.toString()),
        4 // Giới hạn số operations đồng thời ở đoạn này.
    );

// WebFlux: return results.
// Batch main: chờ có timeout và kiểm tra errors.
~~~

### 22.1. Concurrency không đồng nghĩa requests/giây

Nếu mỗi request hoàn tất nhanh, concurrency nhỏ vẫn có thể tạo hàng nghìn requests/giây. Rate limit theo request/byte/transaction budget là tầng khác.

### 22.2. Nhân tổng số Pods

20 Pods, mỗi Pod flatMap concurrency 16 có thể tạo **320 operations in-flight**, chưa kể SDK multipart transfer. Đặt giới hạn ở toàn cluster/workload khi dùng chung Azure service quota.

### 22.3. Không tăng concurrency mù quáng

DownloadContent materialize payload; ví dụ 100 in-flight downloads × 50 MB có thể vượt vài GB heap. Dùng streaming/range APIs cho tệp lớn và giữ byte/memory budget.

## 23. Giữ thứ tự bằng concatMap và flatMapSequential

Với những operations phụ thuộc thứ tự:

~~~java
Flux<String> ordered = Flux.fromIterable(names)
    .concatMap(name ->
        container.getBlobAsyncClient(name)
            .downloadContent()
            .map(BinaryData::toString));
~~~

**concatMap** thực hiện từng publisher theo thứ tự. **flatMap** có thể cho kết quả theo completion order. **flatMapSequential** có thể subscribe song song nhưng buffer để phát theo thứ tự, vì vậy tốn memory nếu một phần tử trước rất chậm.

### 23.1. Không ép thứ tự nếu workload độc lập

Upload độc lập thường nên sử dụng bounded parallelism. Các events cập nhật cùng một customer có version/ordering constraints nên dùng domain ordering chứ không chỉ operator.

### 23.2. Slow item đầu tiên

flatMapSequential có thể chờ item đầu rất lâu và buffer các kết quả sau; cần timeout và memory cap để tránh head-of-line blocking.

### 23.3. Error isolation

Nếu một item lỗi, default Flux có thể kết thúc pipeline. Thiết kế outcome cho từng item hoặc quarantine đúng semantics, không dùng onErrorContinue vô thức.
## 24. Backpressure khác Azure service rate limit

**Backpressure** kiểm soát demand trong Reactive Streams pipeline. **Rate limiting** kiểm soát số request/byte/transaction gửi tới Azure service theo thời gian. Hai thứ bổ trợ nhau chứ không thay thế nhau.

~~~text
Message source / file queue
       |
   Demand / bounded queue
       |
   Global rate limit
       |
   Max in-flight semaphore
       |
   Azure Blob Async Client
       |
   Azure Storage throughput constraints
~~~

### 24.1. limitRate không tự biết quota Azure

Reactor **limitRate** có thể thay đổi kích thước request demand giữa các operators, nhưng mỗi item có thể tương ứng 1, 10 hoặc nhiều network requests (paging, block upload). Không coi limitRate là limiter Azure transactions/s.

### 24.2. Nếu producer nhanh hơn consumer liên tục

Một queue trong JVM sẽ lớn dần, dẫn tới memory pressure hoặc out-of-memory. Dùng bounded queue, delay/reject policy, lưu công việc bền vững ở Service Bus/Storage Queue khi cần, và scale theo capacity thực.

### 24.3. Công bằng giữa các tenants

Nếu nhiều tenants cùng dùng một Storage account, có thể dùng per-tenant budgets để một tenant lớn không làm tăng latency của phần còn lại. Dùng authorization và tenant identity đáng tin, không theo tenantId do user tự khai.

### 24.4. Các tầng retry nhân nhau

Một message worker retry outer task, async client retry HTTP, cộng một upstream queue retry có thể tạo rất nhiều attempts. Cần đo tổng attempts và có backoff để tránh overload amplification.

## 25. Tải tệp lớn: streaming thay vì materialize

**downloadContent()** và **BinaryData.toBytes()** dễ dùng cho tệp nhỏ nhưng có thể dùng nhiều memory với tệp lớn.

### 25.1. Download stream đồng bộ

Ví dụ với BlobClient sync:

~~~java
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

Path file = Path.of("report-copy.pdf");
try (OutputStream out = Files.newOutputStream(file)) {
    blob.downloadStream(out);
}
~~~

Cần kiểm soát file path, disk quota, permissions và idempotency. Đường dẫn ở ví dụ chỉ phục vụ lab; không chấp nhận trực tiếp user-supplied path để tránh path traversal.

### 25.2. Async streaming

Tùy SDK version, **BlobAsyncClient** có các phương thức hỗ trợ download streaming/ranges và publisher phát các chunks dữ liệu. Một thiết kế đúng:

~~~text
Azure Blob Storage
      |
  network chunks
      |
Flux<ByteBuffer> hoặc API streaming tương thích
      |
bounded buffer + backpressure
      |
HTTP response hoặc file sink
~~~

Không collect toàn bộ chunks thành List chỉ để xây byte[] vài GB. Dùng streaming API và HTTP framework có kiểm soát demand/cancellation end-to-end.

### 25.3. Multipart transfer cũng có concurrency riêng

Một lời gọi upload có thể chia thành nhiều blocks và gửi song song theo SDK configuration. Tổng network concurrency là kết hợp **số operations của ứng dụng** và **số requests/chunks bên trong từng operation**. Đừng suy tổng requests chỉ từ số flatMap.

### 25.4. Tải tệp lớn không chỉ là kỹ thuật I/O

Cần content scanning, MIME validation, max upload size, storage lifecycle, access control, encryption, retry/integrity và chi phí network/storage transactions.

## 26. Retry trong Azure SDK: service errors và transient failures

Azure Java clients thường có retry policies do SDK service library/HTTP pipeline cung cấp. **Cấu hình mặc định và xử lý status phụ thuộc dịch vụ và version**. Không đặt một bảng mặc định chung cho toàn Azure.

| Tình huống | Ý nghĩa thường gặp | Hành động |
|---|---|---|
| **400** | Request sai, unsupported options | Sửa request |
| **401/403** | Credential, RBAC, SAS hoặc policy/network | Kiểm tra identity/quyền |
| **404** | Blob/container không tồn tại | Trả Not Found hoặc xử lý business logic |
| **409** | Conflict | Kiểm tra duplicate/lease/state |
| **412** | ETag/precondition thất bại | Giải quyết optimistic concurrency |
| **429** | Một dạng throttling nếu dịch vụ trả mã này | Backoff và capacity review |
| **503 Server Busy** | Storage có thể bị quá tải tạm thời | Backoff, giảm tải, scale theo bằng chứng |
| **5xx khác** | Service/transport tạm lỗi | Retry có giới hạn theo SDK |
| **Timeout/TLS/DNS** | Network hoặc cấu hình | Phân loại và chẩn đoán |

### 26.1. 429 không phải dấu hiệu duy nhất của throttling

Azure Storage có thể dùng các status/subcodes khác (đặc biệt **503 Server Busy**) khi vượt khả năng hoặc gặp throttling. Không chỉ theo dõi 429 rồi kết luận Storage không hề bị giới hạn.

### 26.2. Double-retry

Nếu SDK đã retry, sau đó Reactor retryWhen và job scheduler tiếp tục replay, tổng số attempts có thể lớn hơn mong đợi. Xác định retry ownership và budget toàn workflow.

### 26.3. Retry write và kết quả không chắc chắn

Sau timeout, server có thể đã ghi xong nhưng client chưa nhận response. Replay phải dùng deterministic blob name/ETag/conditions hoặc business idempotency key thích hợp, không tự tạo tên mới và coi đó là retry an toàn.

## 27. RetryWhen có điều kiện cho read idempotent

Nếu cần thêm **một lớp retry ngoài** cho read request sau khi SDK đã xử lý theo policy của nó, có thể dùng:

~~~java
import com.azure.storage.blob.models.BlobStorageException;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

import java.time.Duration;

Mono<byte[]> readWithBudget = asyncBlob.downloadContent()
    .map(data -> data.toBytes())
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(300))
            .maxBackoff(Duration.ofSeconds(2))
            .jitter(0.3)
            .filter(error -> {
                if (!(error instanceof BlobStorageException ex)) {
                    return false;
                }
                return ex.getStatusCode() == 429
                    || ex.getStatusCode() == 503;
            }))
    .timeout(Duration.ofSeconds(10));
~~~

### 27.1. Đếm retries đúng

**Retry.backoff(2, ...)** cho tối đa 2 retries ngoài initial attempt. SDK đã có retry nội bộ nên latency có thể lớn hơn kỳ vọng; tổng deadline và timeout transport phải được đo.

### 27.2. Lỗi transport có thể khác BlobStorageException

Ví dụ trên chỉ minh họa retry service statuses. Với transient network exceptions, cần classifier phù hợp và không coi mọi Throwable là có thể retry.

### 27.3. Retry-after và jitter

Khi Azure service công bố Retry-After/hướng dẫn delay, ưu tiên policy của SDK hoặc cấu hình tôn trọng delay trước khi thêm outer retry. Outer Retry của Reactor không tự bảo đảm lấy Retry-After từ tất cả headers.

### 27.4. Không dùng retryWhen vô hạn cho batch

Infinite retries dễ làm job treo, tăng phí operations và che lỗi configuration. Có max attempts, alert và dead-letter/quarantine cho những items không xử lý được.

## 28. Timeout, deadline và cancellation

Có nhiều khái niệm:

- **Connect timeout**: thời gian cho việc thiết lập kết nối.
- **Network/read timeout**: tùy HTTP transport và SDK.
- **Azure SDK per-call timeout**: theo options/HTTP policies khi hỗ trợ.
- **Reactor timeout**: thời hạn chờ signal ở một stage.
- **HTTP request deadline**: cam kết thời gian phản hồi user.
- **Job deadline**: thời hạn toàn workflow, kể cả retries.

### 28.1. Reactor timeout

~~~java
Mono<String> response = asyncBlob.downloadContent()
    .map(BinaryData::toString)
    .timeout(Duration.ofSeconds(5));
~~~

Nếu timeout, reactive subscription bị hủy và downstream nhận lỗi timeout theo Reactor. Nhưng **hủy phía client không bảo đảm service đã rollback một request đã nhận**.

### 28.2. Client disconnect

Khi browser đóng tab, WebFlux có thể cancel subscription. Tùy SDK/transport, network request có thể bị hủy hoặc vẫn chạy một phần; không coi cancellation là cơ chế transaction rollback.

### 28.3. Deadline nhiều tầng phải nhất quán

Nếu frontend chờ 3 giây nhưng Java SDK timeout 60 giây và retry thêm, worker có thể vẫn bận sau khi caller không còn chờ. Đặt thời hạn phù hợp SLO và tổng retry budget.

### 28.4. Không nuốt InterruptedException trong sync executor

Khi dùng platform/virtual threads với interruptible blocking operations, phải tôn trọng cancellation/interruption theo contract và không tiếp tục retry vô hạn khi shutdown.

## 29. Java 21 virtual threads có thay async client không?

**Virtual threads** cho phép Java code blocking-style với chi phí chờ I/O thấp hơn so với nhiều platform threads truyền thống, trong những điều kiện phù hợp.

Ví dụ Java 21:

~~~java
import java.util.List;
import java.util.concurrent.Executors;

List<String> names =
    List.of("a.txt", "b.txt", "c.txt");

try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    var tasks = names.stream().map(name ->
        executor.submit(() ->
            container.getBlobClient(name)
                .downloadContent()
                .toString())
    ).toList();

    for (var task : tasks) {
        System.out.println(task.get());
    }
}
~~~

Trong ví dụ Java 21, **container** là BlobContainerClient sync được cấu hình từ trước, và code chưa có exception classification/timeout/quota controls.

### 29.1. Virtual threads vẫn gọi sync API

Code vẫn là blocking-style ở tầng người gọi; runtime có thể quản lý việc chờ I/O hiệu quả hơn. Không phải cùng semantic với Reactor cancellation/backpressure.

### 29.2. Virtual threads không tạo quota Azure

Mở 10.000 virtual threads không đảm bảo Storage account/HTTP transport xử lý 10.000 requests tốt. Cần semaphore, rate limit, connection/memory budgets và benchmark.

### 29.3. Khi nào virtual threads là lựa chọn thực tế?

Một Java MVC-style service có logic imperative/JDBC, cần nhiều concurrent requests nhưng không muốn chuyển toàn codebase sang Reactor có thể thử virtual threads ở JDK/runtime hỗ trợ. Đánh giá library compatibility, pinning, CPU tasks, tracing và thread-local behaviors.

### 29.4. Không coi virtual threads và async là kẻ thắng tuyệt đối

- Virtual threads: code tuần tự, dễ debug, thích hợp migration imperative.
- Async Reactor: nonblocking pipelines, compositional streams, backpressure/cancellation.
- Cả hai: cần controls ở ranh giới external service và có thể phối hợp theo kiến trúc.

## 30. Đưa async Mono sang CompletableFuture

Nếu một library Java khác đang dùng CompletableFuture, Reactor Mono có thể được chuyển sang Future:

~~~java
import java.util.concurrent.CompletableFuture;
import reactor.core.publisher.Mono;

Mono<String> mono =
    asyncBlob.downloadContent()
        .map(BinaryData::toString);

CompletableFuture<String> future = mono.toFuture();

future.thenAccept(System.out::println)
      .exceptionally(error -> {
          System.err.println("Operation failed");
          return null;
      });
~~~

### 30.1. Future có thể chỉ là bridge

Sử dụng toFuture giúp nối hai abstractions, không đồng nghĩa bỗng có thêm background worker threads; execution phụ thuộc publisher và transport.

### 30.2. Lifecycle và error propagation

Đảm bảo caller giữ reference future, có timeout/cancellation/exception handler và không làm mất lỗi. Nếu chỉ tạo future rồi bỏ quên, nguy cơ gần giống fire-and-forget.

### 30.3. Đừng cố bridge tất cả bằng block()

Nếu hệ thống đã reactive, chuyển Mono thành Future rồi gọi **join/get** trong event-loop sẽ quay lại blocking. Chỉ bridge tại boundary thực sự cần.

## 31. Context propagation và distributed tracing

Ứng dụng cần correlation giữa inbound HTTP request và outbound Azure SDK call.

~~~text
Incoming HTTP request
   -> correlationId / tenant / auth context
   -> DocumentService
   -> Azure Blob Async Client
   -> HTTP dependency span
   -> Storage response / request ID
~~~

### 31.1. ThreadLocal và reactive pipelines

Reactor operations có thể chuyển qua threads/schedulers. **ThreadLocal/MDC không tự được bảo đảm sẽ theo mọi asynchronous boundary**. Dùng Reactor Context hoặc cơ chế context propagation/instrumentation được framework hỗ trợ.

Ví dụ ý tưởng Reactor Context:

~~~java
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

Mono<String> op = Mono.deferContextual(ctx -> {
    String requestId = ctx.getOrDefault(
        "correlationId", "none");

    return asyncBlob.downloadContent()
        .map(body -> {
            recordSafeMetric(requestId);
            return body.toString();
        });
}).contextWrite(
    Context.of("correlationId", "req-123"));
~~~

**recordSafeMetric** là hàm ứng dụng minh họa, không phải Azure SDK method. Trong production, dùng OpenTelemetry/Application Insights tracing phù hợp; không lưu credential hoặc tenant-sensitive payload vào baggage/traces.

### 31.2. Theo dõi retries và attempts

Một logical operation có thể tạo nhiều HTTP attempts. Nếu chỉ đo thời gian controller mà không đo SDK retries/transport, sẽ khó tìm vì sao p99 tăng.

### 31.3. Diagnostics volume

Không bật body/request-level wire logging cho mọi request production. Nó có thể gây overhead, chi phí ingestion và lộ header/query chứa SAS.

## 32. Tái sử dụng client, HTTP pool và identity lifecycle

| Thành phần | Thực hành | Anti-pattern |
|---|---|---|
| **BlobServiceClient** | Tái sử dụng theo ứng dụng | Tạo trong mỗi HTTP handler |
| **BlobServiceAsyncClient** | Tái sử dụng cùng transport | Tạo trên mỗi Flux item |
| **TokenCredential** | Quản lý qua DI | Refresh key/token bằng tay mỗi call |
| **HTTP client/transport** | Reuse, tune khi có metrics | Tạo hàng nghìn pools |
| **Executor/Scheduler** | Giới hạn và đóng theo lifecycle | new thread per blob không giới hạn |
| **Context** | Request-local context | Mutable static map cho mọi users |

### 32.1. Client construction không phải operation miễn phí

Khởi tạo builder/client và transport repeatedly có thể làm tăng memory, TLS handshakes, connection churn và latency. Thiết kế singleton/bean theo application scope.

### 32.2. Không bắt buộc một account = một client cho mọi tính năng

Mỗi dịch vụ/library có options khác nhau về secondary endpoints, retry, transport và scope. Có thể cần nhiều clients cho mục đích khác nhau, nhưng hãy cấu hình có chủ đích và theo dõi pools.

### 32.3. Shutdown

Nếu ứng dụng tạo custom HTTP clients, schedulers hoặc resources closeable, đóng chúng khi shutdown theo API contract. Không tự giải phóng các shared resources còn được client khác dùng.

## 33. Bảo mật sync và async là cùng một trách nhiệm

Sync/async khác cách thực thi; các vấn đề an toàn giống nhau:

- Authentication bằng Entra managed identity khi hỗ trợ.
- Least-privilege data RBAC trên Storage.
- Private endpoint/firewall/VNet/DNS theo chính sách.
- TLS certificate validation.
- Không log account key/SAS token.
- Không lấy host/path tùy ý từ input không tin cậy.
- Kiểm tra quyền sở hữu blob ở application layer.
- Scan file uploads khi cần.
- Giới hạn file size, request size và content type.
- Mã hóa/retention theo compliance.
- Không tạo public containers hoặc SAS hạn dài để “fix nhanh” lỗi 403.

### 33.1. Async error logs dễ lộ dữ liệu qua callbacks

Khi subscribe/onError callbacks ghi **exception.toString()** hoặc raw HTTP request, có thể làm lộ URL chứa SAS. Dùng structured sanitized logs và correlation IDs.

### 33.2. Managed identity không thay quyền nghiệp vụ

Identity của Java service có thể được quyền đọc container, nhưng end user vẫn cần authorization cho document cụ thể. Không trả mọi blob vì service principal có quyền.

### 33.3. ETag và optimistic concurrency

Khi ghi đè dữ liệu người dùng đồng thời, nên sử dụng conditional requests/ETag hoặc versioning theo API hỗ trợ. Async không tự giải quyết lost updates.

## 34. Observability và metrics nên đo

| Nhóm | Chỉ số | Mục đích |
|---|---|---|
| **API** | p50/p95/p99 latency | Trải nghiệm người dùng |
| **Throughput** | Successful operations/second | Capacity thực |
| **Service errors** | 403/404/409/412/429/503 | Quyền, nghiệp vụ, throttling |
| **Retries** | Attempts, backoff, final error | Phát hiện retry storm |
| **JVM** | CPU, heap, GC pause, threads | Client overload |
| **Concurrency** | In-flight/queued jobs | Phát hiện backpressure |
| **Network** | DNS/TLS latency, connections | Transport bottleneck |
| **Storage** | Request count, bytes, service latency | Khả năng của account |
| **Cost** | Transactions, egress, storage, compute | Giữ ngân sách |

### 34.1. Đo throughput và latency cùng lúc

Một phương án async có thể tăng operations/giây nhưng làm p99 latency tăng nếu concurrency quá cao. Cần so sánh **successful throughput cùng SLO**, không chỉ requests được phát ra.

### 34.2. App Insights/Azure Monitor

Instrument inbound HTTP, Azure SDK dependency spans, exception classification và custom metrics. Khả năng tự instrument và tên fields phụ thuộc OpenTelemetry/Application Insights/SDK version; phải xác minh trong runtime.

### 34.3. Tránh high-cardinality labels

Không đưa blob full path, raw user ID hoặc request ID vào mỗi metric label. Chọn tags như operation, SDK mode, status category và service environment; correlation ID nên nằm ở tracing/logs có retention phù hợp.

## 35. Một bảng so sánh hiệu năng minh họa

Ví dụ bài lab, **không phải benchmark công bố**:

| Phương án | Concurrency cấu hình | Thread behavior | Điều cần quan sát |
|---|---:|---|---|
| Sync, 1 worker | 1 | Caller chờ từng operation | Dễ hiểu nhưng throughput thấp |
| Sync, bounded executor | 8 | Có tối đa 8 blocking workers | Thread/memory overhead |
| Async, flatMap | 8 | Nonblocking I/O theo transport | p95, requests, memory |
| Async, flatMap | 64 | Nhiều in-flight operations | Throttling, retries, memory |
| Java 21 virtual threads | Semaphore 8 | Rất nhiều virtual threads có thể tồn tại | External capacity vẫn bị giới hạn |

**Không so sánh công bằng nếu một biến thể chạy concurrency 1 còn biến thể khác 64.** Với benchmark, giữ dataset, endpoint, payload, warmup, network và concurrency phù hợp; sau đó thay đổi một yếu tố mỗi lần.

### 35.1. Latency thấp không đồng nghĩa chi phí thấp

Một pipeline async tạo nhiều request/giây hơn có thể làm tăng Storage transactions, network egress và compute/logging cost. Chọn capacity theo mục tiêu kinh doanh.

### 35.2. Một request có thể nhanh như nhau

Nếu chỉ download 1 blob nhỏ với network RTT 50 ms, sync và async có thể có latency gần nhau. Async phát huy lợi thế khi có nhiều operations in-flight và thread efficiency quan trọng.

### 35.3. Async code có phí phát triển

Reactor debugging, context propagation, cancellation và error handling có độ phức tạp. Lợi ích performance phải đủ lớn để biện minh chi phí vận hành.
## 36. Kiểm thử sync/async Azure clients

Một ứng dụng sử dụng external Azure services cần **ba mức kiểm thử**:

1. **Unit test:** business service/gateway logic không cần network.
2. **Integration test:** kết nối tới emulator hoặc môi trường Azure lab cho những tính năng tương ứng.
3. **Load/failure test:** đo concurrency, retry, quota, timeout và recovery theo chính sách.

### 36.1. Test tách SDK khỏi business logic

Định nghĩa interface:

~~~java
public interface DocumentGateway {
    String readSmallTextSync(String blobName);

    reactor.core.publisher.Mono<String> readSmallTextAsync(
        String blobName);
}
~~~

Trong unit test, mock hoặc fake implementation của DocumentGateway cho phép thử authorization, fallback và error mapping mà không gọi Azure.

### 36.2. StepVerifier cho reactive results

Với reactor-test dependency phù hợp:

~~~java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

Mono<String> result = Mono.just("hello");

StepVerifier.create(result)
    .expectNext("hello")
    .verifyComplete();
~~~

Đây là test Reactor đơn giản, không chứng minh Azure operation thật. Với một Mono từ gateway fake, có thể kiểm tra complete/error và một số context behaviors.

### 36.3. Kiểm thử publisher không được subscribe

Nếu code tạo Mono nhưng không return/subscribe, fake có thể ghi nhận không có operation thực. Viết test bảo đảm business handler **trả publisher đúng** hoặc batch runner await completion.

### 36.4. Kiểm tra duplicate subscription

Nếu write publisher cold bị subscribe hai lần, mock nên ghi nhận hai attempts; test idempotency policy hoặc lỗi duplicate theo nghiệp vụ.

### 36.5. Kiểm thử cancellation

Dùng một publisher có delay/test scheduler hoặc test HTTP client disconnect; quan sát callback cancellation và giải phóng resources. Đừng giả định server đã rollback phần upload đang chạy.

## 37. Azurite và kiểm thử trên Azure lab

**Azurite** là trình giả lập Azure Storage hỗ trợ một phần Blob/Queue/Table APIs cho local development. Dùng để thử một số thao tác BlobClient/BlobAsyncClient mà không tạo tài nguyên Azure thật.

### 37.1. Azurite giúp được gì?

- Thử create/read/delete blobs và một số request behaviors hỗ trợ.
- Kiểm tra serialization và tên container/blob.
- Test sync/async code path bằng local endpoint.
- Tạo dữ liệu giả để học paging/listing.

### 37.2. Azurite không giống Azure production

Không coi emulator có cùng:

- Microsoft Entra RBAC/managed identity đầy đủ.
- Azure Private Endpoint, network topology và zone/region.
- Throttling/quota/latency thực.
- Tất cả features/versions của Blob SDK.
- Billing/observability của Azure Storage thật.

### 37.3. Hai loại test khác nhau

- **Local emulator:** kiểm tra hành vi cơ bản, nhanh và ít chi phí.
- **Azure lab account:** kiểm tra identity, TLS/private network, SDK compatibility, service-side pagination/retry, metrics và request limits thật.

### 37.4. Không dùng account key lab như production

Azurite thường dùng development credentials/connection string riêng. Không commit production keys vào tests, không reuse credential của tài khoản thật khi dùng emulator.

## 38. Khi nhiều thao tác thành công một phần

Giả sử batch cần upload 100 blobs. Sau 60 successes, request thứ 61 bị 503 và pipeline kết thúc.

### 38.1. Sync và async đều có partial success

Một Flux thất bại không tự rollback 60 uploads trước. Một vòng for sync có exception ở dòng 61 cũng không rollback 60 dòng trước.

### 38.2. Theo dõi per-item outcome

Ví dụ conceptual:

~~~java
record UploadOutcome(
    String blobName,
    boolean success,
    String errorCode
) {}
~~~

Trong reactive batch, thay vì cho một lỗi ngắt tất cả, có thể chuyển **lỗi dự kiến trên từng item** thành một outcome để ghi checkpoint:

~~~java
Flux<UploadOutcome> outcomes =
    Flux.fromIterable(names)
        .flatMap(name ->
            container.getBlobAsyncClient(name)
                .upload(BinaryData.fromString("demo"), true)
                .map(result ->
                    new UploadOutcome(name, true, ""))
                .onErrorResume(error ->
                    Mono.just(
                        new UploadOutcome(
                            name, false, "UPLOAD_FAILED"))),
            4);
~~~

Đây là demo, **không được nuốt toàn bộ exceptions trong production**: ghi exception classification/metrics an toàn, retry theo policy, chuyển failures sang dead-letter/quarantine và định nghĩa quy trình replay. Chỉ coi batch thành công khi mọi outcomes đạt tiêu chí.

### 38.3. Retry và checksum

Với tệp thật, đặt deterministic blob name, checksum/integrity validation và conditional write khi cần để retry không tạo bản sao hoặc ghi đè dữ liệu mới.

### 38.4. Chọn checkpoint

Checkpoint phải phản ánh uploads đã bền vững, không chỉ tên cuối đã được đưa vào Flux. Khi xử lý out of order, checkpoint theo contiguous completed offset hoặc per-item status, tránh skip failures.

## 39. Chi phí, quota và kiến trúc ứng dụng

Sync/async **không có bảng giá riêng** ở Azure Storage. Chi phí phụ thuộc:

- Storage capacity và tier.
- Số reads/writes/list operations.
- Lượng dữ liệu truyền và egress.
- Tính năng replication, snapshots, lifecycle.
- Azure compute của App Service/AKS/Functions.
- Network gateway, private endpoint/egress khi áp dụng.
- Azure Monitor/Log Analytics ingestion và retention.

### 39.1. Khi async tiết kiệm tài nguyên

Với nhiều I/O-bound concurrent operations, async nonblocking có thể giảm số platform threads cần thiết ở Java. Điều đó *có thể* giảm compute overhead khi benchmark xác nhận, nhưng cần tính thêm complexity và transport/pooling.

### 39.2. Khi async tăng chi phí

Nếu chuyển sang async làm số operations/giây tăng mạnh, Storage transactions, egress và logging có thể tăng; nếu quá tải sẽ có retries, phí và p99 cao. Mục tiêu nên là **cost per successful useful operation**, không phải số requests phát đi.

### 39.3. Nhiều clients tạo nhiều pools

Tạo HTTP client/SDK client liên tục có thể tăng memory, sockets, DNS/TLS overhead và cloud compute. Reuse clients giúp quản lý hiệu quả hơn.

### 39.4. Scale compute không scale service quota

HPA thêm Pods hoặc tăng thread count không làm Storage service có capacity vô hạn. Giám sát account throughput/throttling, request patterns và partition hot spots trước khi tăng tải.

## 40. Runbook khi async workloads bị chậm hoặc lỗi

Một kịch bản:

~~~text
10:00  App p95 = 150 ms, success rate tốt
10:05  Batch ingestion bắt đầu
10:07  In-flight = 2.000, JVM memory tăng
10:08  Azure Storage 503 và retry tăng
10:10  p99 API = 8 giây, download failures tăng
~~~

### Bước 1 — Khoanh vùng

Có vừa tăng Pods/flatMap concurrency, bật multipart transfer hoặc batch job mới không? Chỉ một storage account/container hay toàn hệ thống?

### Bước 2 — Phân loại lỗi

Kiểm tra 403, 404, 409/412, 429/503 và network exceptions riêng. Không điều chỉnh capacity để sửa lỗi RBAC hay blob không tồn tại.

### Bước 3 — Đọc telemetry

Throughput thành công, in-flight, queue size, heap/GC, threads, retry attempts, p95/p99, account service latency và Azure request IDs.

### Bước 4 — Tìm bottleneck

- App threads bị block trong WebFlux?
- Quá nhiều concurrent downloadContent?
- Storage bị throttled hoặc một blob/key quá nóng?
- Network/NAT/proxy connection limits?
- SDK clients đang được tạo liên tục?
- Tệp lớn khiến JVM heap quá tải?

### Bước 5 — Bảo vệ hệ thống

Giảm concurrency, giới hạn incoming jobs, tạm dừng batch không ưu tiên, ưu tiên API tương tác, dùng streaming và bounded queues.

### Bước 6 — Sửa nguyên nhân

Tối ưu request pattern, size, transport/pool, timeout/retry policy hoặc throughput architecture. Tăng capacity chỉ khi có bằng chứng; giữ rollback plan.

### Bước 7 — Đối soát và replay

Xác minh uploads partial, idempotency và per-item statuses. Chạy lại những failures, không tạo duplicate side effects.

## 41. Bài lab 1: chạy cùng thao tác bằng sync và async clients

**Chỉ dùng Azure lab subscription/resource group được cho phép.** Không ghi vào production account và không in keys/tokens.

### A. Chuẩn bị

1. Tạo hoặc dùng Storage account lab hỗ trợ Blob service.
2. Tạo container **documents**.
3. Dùng managed identity/developer identity và cấp quyền Blob data-plane phù hợp.
4. Cấu hình endpoint qua biến **AZURE_STORAGE_BLOB_ENDPOINT**.
5. Kiểm tra HTTPS, DNS, firewall/private network từ nơi chạy Java.
6. Tạo dự án Java 17 với dependencies đã chọn phiên bản được phê duyệt.

### B. Sync

1. Tạo BlobServiceClient qua BlobClients.syncClient().
2. Upload một blob nhỏ bằng BinaryData.
3. Download bằng downloadContent().
4. In nội dung mẫu không nhạy cảm.
5. Bắt lỗi 404 bằng BlobStorageException.
6. Đo start/end time và request latency.

### C. Async

1. Tạo BlobServiceAsyncClient qua BlobClients.asyncClient().
2. Dựng Mono upload().then(downloadContent()).
3. Xác nhận chưa có side effect khi publisher chưa subscribed nếu SDK semantics là cold.
4. Trong CLI, block với timeout tại ranh giới main.
5. Trong WebFlux, return Mono mà không block.
6. Đo tương tự workload sync.

### D. So sánh

| Tiêu chí | Sync | Async |
|---|---|---|
| API return type | BinaryData/response trực tiếp | Mono/Flux/PagedFlux |
| Caller thread | Chờ completion | Không block khi compose đúng |
| Lỗi | Exception | onError signal |
| Concurrency | Bounded threads/virtual threads | Bounded flatMap/subscriptions |
| Cancellation | Qua thread/transport APIs | Qua subscription/transport APIs |
| Memory | Phụ thuộc payload và cách dùng | Phụ thuộc payload/buffers/concurrency |

**Kết quả lab không cần chứng minh async luôn nhanh hơn.** Cần giải thích cơ chế và đo được sự khác biệt.

## 42. Bài lab 2: tải nhiều blobs với concurrency có kiểm soát

Dùng **50–100 blobs nhỏ** tạo trong container lab và một script Java riêng cho từng phương án.

### A. Sync baseline

1. Dùng for loop, concurrency = 1.
2. Ghi successful operations/s, p95 và memory.
3. Dùng bounded ExecutorService với 4/8 tasks đồng thời.
4. Giữ cùng dataset/cùng payload.

### B. Async baseline

1. Dùng Flux.fromIterable(names).
2. Dùng flatMap(downloadContent(), concurrency=4).
3. Tăng concurrency lên 8 nếu môi trường cho phép.
4. So sánh p95/p99, success rate, threads và memory.

### C. Thêm lỗi có kiểm soát

1. Yêu cầu đọc một blob không tồn tại.
2. Kiểm tra 404 không bị retry vô hạn.
3. Dùng mock HTTP backend để thử 503/retry-after mà không gây stress tới shared Azure resources.
4. Thử timeout/cancellation và theo dõi final outcomes.
5. Không sử dụng raw blob content nhạy cảm làm log.

### D. Bảng ghi nhận

| Chỉ số | Sync 1 | Sync 8 | Async 4 | Async 8 |
|---|---|---|---|---|
| Successful operations/s | Đo | Đo | Đo | Đo |
| p95 latency | Đo | Đo | Đo | Đo |
| p99 latency | Đo | Đo | Đo | Đo |
| JVM peak threads | Đo | Đo | Đo | Đo |
| JVM heap/GC | Đo | Đo | Đo | Đo |
| Service 429/503 | Đo | Đo | Đo | Đo |
| Retry attempts | Đo | Đo | Đo | Đo |
| Egress/transaction estimate | Đo | Đo | Đo | Đo |

### E. Tiêu chí hoàn thành

Giải thích tại sao một cấu hình đạt nhiều operations/s hơn hoặc ít threads hơn; điều gì xảy ra với memory và p99 khi tăng concurrency; khi nào nên giữ sync vì đơn giản và đủ đáp ứng SLO.

## 43. Bài lab 3: integrate với framework, verify identity và cleanup

### A. MVC

1. Tạo một GET endpoint đọc blob văn bản nhỏ.
2. Dùng sync BlobClient qua một DI-managed service.
3. Map 404 thành HTTP 404.
4. Kiểm tra authz đối với blob của user.
5. Đo thread pool utilization.

### B. WebFlux

1. Tạo GET endpoint trả Mono.
2. Dùng BlobAsyncClient trong service.
3. Không block/subscribe trong controller.
4. Kiểm tra cancellation khi HTTP client disconnect.
5. Thử một blocking call giả để thấy vì sao không nên đưa lên event-loop; không thử trên production.

### C. Security

1. Tạo test principal chỉ có quyền đọc container.
2. Kiểm tra read thành công và write bị từ chối đúng.
3. Xác nhận không có account key/SAS trong logs.
4. Kiểm tra private DNS/network nếu lab có private endpoint.
5. Không sửa firewall thành allow-all để vượt 403.

### D. Cleanup

1. Dừng batch jobs và HTTP app lab.
2. Xóa blobs/container hoặc resource group **chỉ khi đã xác nhận là tài nguyên riêng của lab**.
3. Thu hồi role assignments/keys lab nếu cần.
4. Xem Cost Management để bảo đảm không còn compute/storage không cần thiết.

## 44. Checklist production

- [ ] Đã phân tích workload và chọn sync/async theo framework.
- [ ] SDK versions tương thích, dependencies pin/BOM và CVE scan.
- [ ] Storage account endpoint lấy từ trusted configuration.
- [ ] Dùng Entra/managed identity và least-privilege data RBAC.
- [ ] Network/private DNS/TLS được thử từ runtime thật.
- [ ] Client/credential/HTTP transport được tái sử dụng.
- [ ] Không tạo client mỗi request hoặc mỗi Flux item.
- [ ] Không dùng Mono.just để bọc blocking call.
- [ ] Không block trong Reactor event-loop.
- [ ] Không subscribe-and-forget trong HTTP handlers.
- [ ] Có max in-flight và rate limit theo capacity thật.
- [ ] Có bounded queues, timeouts/deadlines và overload response.
- [ ] Không collect file lớn thành byte[] không giới hạn.
- [ ] PagedFlux listing có giới hạn/paging.
- [ ] Batch xử lý errors per item và checkpoint đúng.
- [ ] Có idempotency/ETag cho writes và replay.
- [ ] Hiểu SDK internal retries và tránh double-retry.
- [ ] Không retry 400/403/404 mù quáng.
- [ ] Theo dõi cả 429 và 503 Storage throttling.
- [ ] Cancellation không được coi là server rollback.
- [ ] Context propagation/tracing hoạt động qua async boundary.
- [ ] Logs không chứa SAS, keys, access tokens, raw blob data.
- [ ] Có metrics p95/p99, throughput thành công, queue, GC và retries.
- [ ] Có runbook cho 403, 404, 409, 412, 429/503 và timeout.
- [ ] Có benchmark sync/async cùng concurrency và dataset.
- [ ] Đã test virtual threads nếu dùng Java 21 thay Reactor.
- [ ] Có cost budget cho Storage, compute, network, logs.
- [ ] Có mock/integration tests và lab cleanup process.

## 45. Câu hỏi tự kiểm tra

1. Đồng bộ và bất đồng bộ khác nhau ở tầng caller ra sao?
2. Blocking I/O khác nonblocking I/O như thế nào?
3. Concurrency có đồng nghĩa với parallelism không?
4. BlobServiceClient khác BlobServiceAsyncClient thế nào?
5. BlobClient.upload trả kết quả khác BlobAsyncClient.upload như thế nào?
6. Vì sao Azure SDK builder cần endpoint và credential?
7. Managed identity có tự có quyền Blob data-plane không?
8. Azure ARM Contributor có mặc nhiên đọc blobs không?
9. Tại sao không tạo Azure client mỗi HTTP request?
10. Mono và Flux khác nhau ở số emissions?
11. PagedFlux có thể phát bao nhiêu HTTP requests?
12. Cold publisher có làm duplicate writes khi subscribe hai lần không?
13. Nếu chỉ tạo Mono mà không return/subscribe, operation có chạy không?
14. Vì sao không gọi block() trong WebFlux event-loop?
15. Mono.just(getSyncResult()) có thật sự nonblocking không?
16. boundedElastic làm I/O blocking trở thành nonblocking thực không?
17. flatMap với concurrency 8 có bảo đảm tối đa 8 requests toàn cluster không?
18. flatMap có bảo đảm thứ tự input không?
19. concatMap và flatMapSequential đánh đổi gì?
20. Vì sao limitRate không thay Azure request rate limiting?
21. DownloadContent của blob 1 GB có nguy cơ gì?
22. SDK multipart transfer ảnh hưởng tổng số operations thế nào?
23. Tại sao Storage throttling không chỉ có mã 429?
24. Điều gì xảy ra khi SDK retry và outer retry cùng hoạt động?
25. Timeout/cancel có bảo đảm upload bị rollback không?
26. Với write timeout, tại sao cần idempotency/ETag?
27. Java 21 virtual threads khác Reactor ở mô hình lập trình nào?
28. Virtual threads có làm tăng Azure Storage quota không?
29. ThreadLocal/MDC có luôn đi theo Reactor scheduler không?
30. Vì sao cần correlation ID và không log SAS?
31. Khi batch 100 files lỗi sau 60 files, có rollback tự động không?
32. Azurite có thay thế được kiểm thử Entra RBAC trên Azure không?
33. Nên dùng metrics nào so sánh sync và async công bằng?
34. Vì sao throughput cao hơn có thể khiến chi phí lớn hơn?
35. Khi nào nên ưu tiên sync vì đơn giản và phù hợp SLO?

## 46. Tổng kết

**Đồng bộ và bất đồng bộ trong Azure Java client** là hai cách sử dụng cùng dịch vụ Azure với hợp đồng thực thi khác nhau. **Sync** trả giá trị hoặc exception sau khi operation hoàn tất, phù hợp với code imperative, MVC và các batch đơn giản. **Async** trả **Mono/Flux/PagedFlux**, cho phép xây nonblocking pipelines hiệu quả với nhiều I/O operations khi framework và toàn bộ dependencies hỗ trợ.

Ví dụ **BlobServiceClient/BlobServiceAsyncClient** cho thấy cách tạo clients qua builder và managed identity, upload/download/list bằng phương thức sync hoặc reactive. Để dùng async đúng, cần hiểu **lazy subscription, flatMap/concatMap/then, error propagation, cancellation và backpressure**; tránh block event-loop, Mono.just bọc sync call và subscribe-and-forget.

Hiệu năng bền vững phụ thuộc **bounded concurrency, rate limiting, streaming file lớn, client reuse, timeout, idempotent writes, SDK retry policy, tracing và benchmark thực tế**. Java 21 virtual threads là một lựa chọn tốt cho một số ứng dụng imperative, nhưng cũng không thể thay quota hoặc thiết kế backpressure bên ngoài.

Kết hợp kiến thức Java này với **Microsoft Entra ID, Azure Blob Storage, App Service/AKS/Functions, Azure networking, Azure Monitor và Cost Management** giúp chọn mô hình client phù hợp: dữ liệu đúng, ứng dụng ổn định, bảo mật và chi phí được kiểm soát.





